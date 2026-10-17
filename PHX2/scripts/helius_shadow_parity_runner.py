"""Bounded isolated Chainstack/Helius migration parity runner.

This operator tool is no-send by construction: it instantiates the two source
adapters directly, never the production discovery owner, scheduler, delivery
transaction, Telegram transport, or paid ledger.  Chainstack remains the
comparison authority.  Helius WSS and its bounded HTTP gap recovery write only
sanitized parity/continuity evidence below ``artifacts/helius_shadow_parity``.

The runner is not invoked by any production launcher or scheduled task.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Optional

from PHX2.free_tier_producer.helius_gap_recovery import (
    HeliusRecoveryConfig,
    HeliusSlotGapRecoverer,
)
from PHX2.free_tier_producer.helius_byte_budget import HeliusByteBudget
from PHX2.free_tier_producer.helius_shadow_parity import (
    DEFAULT_LATE_MATCH_SECONDS,
    HeliusParityArtifactWriter,
    HeliusShadowParityAccumulator,
    MATCH_STATUSES,
    PROVIDER_CHAINSTACK,
    PROVIDER_HELIUS_HTTP,
    PROVIDER_HELIUS_WSS,
    ParityObservation,
    VERDICT_ADMITTED,
)
from PHX2.free_tier_producer.helius_source import (
    HELIUS_SHADOW,
    HeliusEnhancedWssSource,
    load_source_selection,
)
from PHX2.free_tier_producer.migration_admission import MigrationProofStore
from PHX2.free_tier_producer.paid_provider import build_live_source_factory
from PHX2.free_tier_producer.source_continuity import SourceContinuityTracker
from PHX2.shadow_probes.helius_developer import estimated_stream_credits
from PHX2.shadow_probes.helius_developer import DEFAULT_MAX_RAW_BYTES
from PHX2.scripts.helius_shadow_parity_config import (
    load_shadow_parity_configuration,
)
from PHX2.scripts.helius_shadow_parity_preflight import (
    ShadowParityPreflightReport,
    run_preflight,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPOSITORY_ROOT / ".env"
PARITY_ROOT = REPOSITORY_ROOT / "artifacts" / "helius_shadow_parity"
MAX_DURATION_SECONDS = 3600
MAX_MIGRATION_EVENTS_PER_SOURCE = 10_000


@dataclass(frozen=True)
class RunnerSummary:
    duration_seconds: float
    task_state: str
    control_subscription_started: bool
    control_updates: int
    control_transactions: int
    control_status: str
    control_observations: int
    shadow_connected: bool
    shadow_notifications: int
    shadow_observations: int
    shadow_bytes: int
    shadow_stream_bytes: int
    shadow_fetch_bytes: int
    shadow_byte_ceiling: int
    shadow_byte_ceiling_reached: bool
    parity_records: int
    match_status_counts: dict[str, int]
    source_errors: tuple[str, ...]
    shadow_status: str
    shadow_continuity_state: str
    late_match_grace_seconds: float
    output: str


class ProviderLifecycle:
    """Shared shutdown plus provider-local failure facts.

    A provider failure is evidence about that provider only. It never sets the
    shared stop event; the supervisor owns shared shutdown after the bounded
    observation window or an explicit global safety condition.
    """

    def __init__(self) -> None:
        self.shared_stop = threading.Event()
        self._failed: set[str] = set()
        self._lock = threading.Lock()

    def note_provider_failure(self, provider: str) -> None:
        with self._lock:
            self._failed.add(str(provider))

    def provider_failed(self, provider: str) -> bool:
        with self._lock:
            return str(provider) in self._failed


def _request_shared_stop(
    lifecycle: ProviderLifecycle, sources: tuple[object, ...],
) -> None:
    """Publish shared stop before closing either active source."""

    lifecycle.shared_stop.set()
    for active in sources:
        close = getattr(active, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


def _safe_exception_name(exc: BaseException) -> str:
    name = type(exc).__name__
    if name and len(name) <= 64 and all(
        character.isalnum() or character == "_" for character in name
    ):
        return name
    return "UNSAFE_EXCEPTION_CLASS"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_shadow_parity(
    *,
    duration_seconds: int,
    max_events_per_source: int,
    output: Path,
    env_path: Optional[Path] = None,
    max_helius_bytes: int = DEFAULT_MAX_RAW_BYTES,
    late_match_grace_seconds: float = DEFAULT_LATE_MATCH_SECONDS,
    preflight_runner: Callable[
        [], ShadowParityPreflightReport
    ] = run_preflight,
    status_sink: Optional[Callable[[str], None]] = None,
) -> RunnerSummary:
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int)
        or not 1 <= duration_seconds <= MAX_DURATION_SECONDS
    ):
        raise ValueError("duration_seconds is out of range")
    if (
        isinstance(max_events_per_source, bool)
        or not isinstance(max_events_per_source, int)
        or not 1 <= max_events_per_source <= MAX_MIGRATION_EVENTS_PER_SOURCE
    ):
        raise ValueError("max_events_per_source is out of range")
    if (
        isinstance(max_helius_bytes, bool)
        or not isinstance(max_helius_bytes, int)
        or not 1 <= max_helius_bytes <= 10_000_000_000
    ):
        raise ValueError("max_helius_bytes is out of range")
    if (
        isinstance(late_match_grace_seconds, bool)
        or not isinstance(late_match_grace_seconds, (int, float))
        or not 0 <= float(late_match_grace_seconds) <= 60
    ):
        raise ValueError("late_match_grace_seconds is out of range")
    try:
        selection = load_source_selection()
    except ValueError as exc:
        raise RuntimeError(
            "PHX2_MIGRATION_SOURCE_MODE must be HELIUS_SHADOW"
        ) from exc
    if selection.mode != HELIUS_SHADOW:
        raise RuntimeError(
            "PHX2_MIGRATION_SOURCE_MODE must be HELIUS_SHADOW"
        )
    if (
        selection.helius_send_capable
        or selection.helius_delivery_reservation_capable
        or selection.helius_ledger_write_capable
        or not selection.chainstack_production_authority
    ):
        raise RuntimeError("Helius shadow ownership policy is unsafe")

    resolved_output = output.resolve()
    allowed_root = PARITY_ROOT.resolve()
    writer = HeliusParityArtifactWriter(
        resolved_output,
        allowed_root=allowed_root,
    )
    preflight = preflight_runner()
    if status_sink is not None:
        for line in preflight.sanitized_lines():
            status_sink(line)
    configuration = load_shadow_parity_configuration(
        env_path=env_path,
        max_helius_raw_bytes=max_helius_bytes,
    )
    byte_budget = HeliusByteBudget(max_helius_bytes)
    if status_sink is not None:
        for name, state in configuration.sanitized_readiness().items():
            status_sink(f"{name}={state}")
        status_sink("HELIUS_PRIMARY=DISABLED")
        status_sink(f"HELIUS_BYTE_CEILING={max_helius_bytes}")
    writer.initialize()
    state_dir = resolved_output.parent / "state"
    continuity = SourceContinuityTracker(
        state_path=state_dir / "helius_source_continuity.json"
    )
    continuity.load()
    observations: queue.Queue[ParityObservation] = queue.Queue(
        maxsize=max(
            1024,
            min(100_000, max_events_per_source * 64),
        )
    )
    lifecycle = ProviderLifecycle()
    stop = lifecycle.shared_stop
    errors: list[str] = []
    error_lock = threading.Lock()
    counts = {
        PROVIDER_CHAINSTACK: 0,
        PROVIDER_HELIUS_WSS: 0,
        PROVIDER_HELIUS_HTTP: 0,
    }
    match_counts = {status: 0 for status in MATCH_STATUSES}

    def record_error(provider: str, exc: BaseException) -> None:
        lifecycle.note_provider_failure(provider)
        with error_lock:
            errors.append(provider + ":" + _safe_exception_name(exc))

    def enqueue(provider: str, observation: ParityObservation) -> None:
        try:
            observations.put(observation, timeout=0.25)
            counts[provider] += 1
        except queue.Full:
            with error_lock:
                errors.append(provider + ":PARITY_QUEUE_FULL")
            stop.set()

    def chainstack_rejection_sink(record: dict) -> None:
        signature = record.get("transaction_signature")
        slot = record.get("slot")
        if (
            not isinstance(signature, str)
            or not signature
            or isinstance(slot, bool)
            or not isinstance(slot, int)
            or slot < 0
        ):
            return
        reasons = record.get("reason_codes")
        reason = (
            ",".join(str(value) for value in reasons)
            if isinstance(reasons, list) and reasons
            else "LOCAL_DECODER_REJECTED"
        )
        enqueue(
            PROVIDER_CHAINSTACK,
            ParityObservation(
                provider_label=PROVIDER_CHAINSTACK,
                signature_or_hash=signature,
                slot=slot,
                receive_timestamp=_utc_now(),
                migration_type=record.get("migration_version"),
                mint=record.get("token_mint"),
                pool=record.get("pool"),
                local_decoder_verdict="REJECTED",
                rejection_reason=reason,
                bytes=0,
                estimated_credits=0.0,
            ),
        )

    def helius_rejection_sink(record: dict) -> None:
        if record.get("local_decoder_verdict") == VERDICT_ADMITTED:
            return
        snapshot = continuity.snapshot()
        recovery_status = getattr(
            helius.last_recovery_outcome,
            "coverage_status",
            "NOT_REQUESTED",
        )
        enqueue(
            PROVIDER_HELIUS_WSS,
            ParityObservation(
                provider_label=PROVIDER_HELIUS_WSS,
                signature_or_hash=str(record["signature_or_hash"]),
                slot=int(record["slot"]),
                receive_timestamp=str(record["receive_timestamp"]),
                migration_type=record.get("migration_type"),
                mint=record.get("mint"),
                pool=record.get("pool"),
                local_decoder_verdict=str(
                    record["local_decoder_verdict"]
                ),
                rejection_reason=record.get("rejection_reason"),
                bytes=int(record["bytes"]),
                estimated_credits=float(record["estimated_credits"]),
                reconnect_count=helius.metrics.reconnects,
                gap_state=str(snapshot["continuity_state"]),
                recovery_state=str(recovery_status),
            ),
        )

    def helius_recovery_sink(outcome: Any) -> None:
        migrations = tuple(getattr(outcome, "migrations", ()) or ())
        migration_types = tuple(
            getattr(outcome, "migration_types", ()) or ()
        )
        signatures = tuple(
            getattr(outcome, "recovered_signatures", ()) or ()
        )
        slots = tuple(getattr(outcome, "recovered_slots", ()) or ())
        slot_by_signature = dict(zip(signatures, slots))
        metrics = getattr(outcome, "metrics", {}) or {}
        total_credits = float(metrics.get("estimated_credits", 0))
        per_migration_credits = (
            total_credits / len(migrations) if migrations else 0.0
        )
        snapshot = continuity.snapshot()
        for event, migration_type in zip(migrations, migration_types):
            signature = str(event.provider_event_id)
            slot = slot_by_signature.get(signature)
            if not isinstance(slot, int):
                continue
            enqueue(
                PROVIDER_HELIUS_HTTP,
                ParityObservation(
                    provider_label=PROVIDER_HELIUS_HTTP,
                    signature_or_hash=signature,
                    slot=slot,
                    receive_timestamp=str(event.observed_at_utc),
                    migration_type=str(migration_type),
                    mint=str(event.mint),
                    pool=str(event.pool_account),
                    local_decoder_verdict=VERDICT_ADMITTED,
                    rejection_reason=None,
                    bytes=0,
                    estimated_credits=per_migration_credits,
                    reconnect_count=helius.metrics.reconnects,
                    gap_state=str(snapshot["continuity_state"]),
                    recovery_state=str(outcome.coverage_status),
                ),
            )

    recoverer = HeliusSlotGapRecoverer(
        source_config=configuration.helius,
        recovery_config=HeliusRecoveryConfig(),
        continuity=continuity,
        byte_budget=byte_budget,
    )
    helius = HeliusEnhancedWssSource(
        config=configuration.helius,
        continuity=continuity,
        gap_recoverer=recoverer,
        decoder_observer=helius_rejection_sink,
        recovery_observer=helius_recovery_sink,
        byte_budget=byte_budget,
    )
    proof_store = MigrationProofStore()
    chainstack = build_live_source_factory(
        proof_store=proof_store,
        admission_sink=chainstack_rejection_sink,
        runtime_config=configuration.chainstack,
    )()

    def chainstack_worker() -> None:
        try:
            for event in chainstack.iter_events(
                max_events=max_events_per_source
            ):
                if stop.is_set():
                    break
                proof = proof_store.get(str(event.mint))
                if proof is None:
                    continue
                observation = ParityObservation(
                    provider_label=PROVIDER_CHAINSTACK,
                    signature_or_hash=proof.migration_signature,
                    slot=int(proof.migration_slot),
                    receive_timestamp=str(event.observed_at_utc),
                    migration_type=proof.migration_instruction_version,
                    mint=str(event.mint),
                    pool=str(event.pool_account),
                    local_decoder_verdict=VERDICT_ADMITTED,
                    rejection_reason=None,
                    bytes=0,
                    estimated_credits=0.0,
                )
                enqueue(PROVIDER_CHAINSTACK, observation)
        except Exception as exc:
            record_error(PROVIDER_CHAINSTACK, exc)

    def helius_worker() -> None:
        try:
            for event in helius.iter_events(
                max_events=max_events_per_source
            ):
                if stop.is_set():
                    break
                context = helius.last_event_context
                if context is None:
                    continue
                snapshot = continuity.snapshot()
                recovery_status = getattr(
                    helius.last_recovery_outcome,
                    "coverage_status",
                    "NOT_REQUESTED",
                )
                observation = ParityObservation(
                    provider_label=PROVIDER_HELIUS_WSS,
                    signature_or_hash=context.signature,
                    slot=context.source_slot,
                    receive_timestamp=context.received_at_utc,
                    migration_type=helius.last_migration_type,
                    mint=str(event.mint),
                    pool=str(event.pool_account),
                    local_decoder_verdict=VERDICT_ADMITTED,
                    rejection_reason=None,
                    bytes=context.raw_uncompressed_bytes,
                    estimated_credits=estimated_stream_credits(
                        context.raw_uncompressed_bytes
                    ),
                    reconnect_count=helius.metrics.reconnects,
                    gap_state=str(snapshot["continuity_state"]),
                    recovery_state=str(recovery_status),
                )
                enqueue(PROVIDER_HELIUS_WSS, observation)
        except Exception as exc:
            record_error(PROVIDER_HELIUS_WSS, exc)

    threads = (
        threading.Thread(
            target=chainstack_worker,
            name="phx2-shadow-chainstack",
            daemon=True,
        ),
        threading.Thread(
            target=helius_worker,
            name="phx2-shadow-helius",
            daemon=True,
        ),
    )
    accumulator = HeliusShadowParityAccumulator()
    started = time.monotonic()
    deadline = started + duration_seconds
    records = 0
    pending_identities: set[str] = set()

    def consume(observation: ParityObservation) -> None:
        nonlocal records
        identity = observation.signature_or_hash
        pending_identities.add(identity)
        record = accumulator.observe(observation)
        if record is None:
            return
        writer.write(record)
        records += 1
        match_counts[record.match_status] += 1
        pending_identities.discard(identity)

    for thread in threads:
        thread.start()
    try:
        while time.monotonic() < deadline:
            if byte_budget.reached or stop.is_set():
                break
            try:
                observation = observations.get(timeout=0.25)
            except queue.Empty:
                if all(not thread.is_alive() for thread in threads):
                    break
                continue
            consume(observation)
        late_pending = set(pending_identities)
        late_deadline = time.monotonic() + float(
            late_match_grace_seconds
        )
        while (
            late_pending
            and time.monotonic() < late_deadline
            and not byte_budget.reached
            and not stop.is_set()
        ):
            try:
                observation = observations.get(timeout=0.1)
            except queue.Empty:
                if all(not thread.is_alive() for thread in threads):
                    break
                continue
            identity = observation.signature_or_hash
            if identity not in late_pending:
                continue
            consume(observation)
            if identity not in pending_identities:
                late_pending.discard(identity)
    finally:
        _request_shared_stop(lifecycle, (helius, chainstack))
        for thread in threads:
            thread.join(timeout=15)
    while True:
        try:
            observation = observations.get_nowait()
        except queue.Empty:
            break
        if observation.signature_or_hash in late_pending:
            consume(observation)
            if observation.signature_or_hash not in pending_identities:
                late_pending.discard(observation.signature_or_hash)
    for record in accumulator.finalize_unmatched():
        writer.write(record)
        records += 1
        match_counts[record.match_status] += 1
    chainstack_diagnostic = chainstack.diagnostic_snapshot()
    chainstack_status = str(
        chainstack_diagnostic.get("iterator_end_kind") or "UNKNOWN"
    )
    if chainstack_status in ("GRPC_ERROR", "LOCAL_ERROR"):
        with error_lock:
            errors.append(PROVIDER_CHAINSTACK + ":" + chainstack_status)
    if helius.status in ("AUTH_FAILED", "FAILED"):
        with error_lock:
            errors.append(PROVIDER_HELIUS_WSS + ":" + helius.status)
    elapsed = max(0.0, time.monotonic() - started)
    byte_snapshot = byte_budget.snapshot()
    relative = resolved_output.relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    return RunnerSummary(
        duration_seconds=elapsed,
        task_state=preflight.task_state,
        control_subscription_started=(
            chainstack.stream_phase not in ("NOT_STARTED", "CHANNEL_OPEN")
        ),
        control_updates=int(chainstack.events_scanned),
        control_transactions=int(chainstack.transactions_scanned),
        control_status=chainstack_status,
        control_observations=counts[PROVIDER_CHAINSTACK],
        shadow_connected=helius.metrics.connections_established > 0,
        shadow_notifications=int(helius.metrics.notifications_received),
        shadow_observations=(
            counts[PROVIDER_HELIUS_WSS]
            + counts[PROVIDER_HELIUS_HTTP]
        ),
        shadow_bytes=int(byte_snapshot["used_bytes"]),
        shadow_stream_bytes=int(byte_snapshot["wss_bytes"]),
        shadow_fetch_bytes=int(byte_snapshot["http_bytes"]),
        shadow_byte_ceiling=max_helius_bytes,
        shadow_byte_ceiling_reached=bool(byte_snapshot["reached"]),
        parity_records=records,
        match_status_counts=match_counts,
        source_errors=tuple(errors),
        shadow_status=helius.status,
        shadow_continuity_state=continuity.continuity_state(),
        late_match_grace_seconds=float(late_match_grace_seconds),
        output=relative,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded no-send Chainstack/Helius shadow parity run"
    )
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--max-events", type=int, default=1000)
    parser.add_argument(
        "--max-helius-bytes",
        type=int,
        default=DEFAULT_MAX_RAW_BYTES,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    try:
        summary = run_shadow_parity(
            duration_seconds=args.seconds,
            max_events_per_source=args.max_events,
            output=args.output,
            env_path=args.env_file,
            max_helius_bytes=args.max_helius_bytes,
            status_sink=lambda line: print(line, flush=True),
        )
    except Exception as exc:
        reason = getattr(exc, "reason", _safe_exception_name(exc))
        print(
            json.dumps(
                {
                    "runner_status": "REFUSED",
                    "reason": str(reason),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 2
    print(json.dumps(summary.__dict__, sort_keys=True, indent=2))
    return 0 if not summary.source_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
