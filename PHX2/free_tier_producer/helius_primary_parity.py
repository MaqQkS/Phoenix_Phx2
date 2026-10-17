"""Production Helius-primary / Chainstack-shadow comparison boundary.

The shadow side owns only a provider iterator, a private in-memory proof store,
and a sanitized parity writer.  It receives no canonical candidate queue,
reserve index, fee index, continuity tracker, transport, reservation seam, or
runtime ledger path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any, Callable, Dict, Mapping, Optional

from PHX2.free_tier_producer.helius_shadow_parity import (
    CHAINSTACK_ONLY,
    DECODE_MISMATCH,
    DEFAULT_LATE_MATCH_SECONDS,
    HELIUS_ONLY,
    MATCH,
    MATCH_STATUSES,
    PROVIDER_CHAINSTACK,
    PROVIDER_HELIUS_HTTP,
    PROVIDER_HELIUS_WSS,
    RECOVERED_BY_HELIUS_HTTP,
    SLOT_MISMATCH,
    UNRESOLVED,
    HeliusParityArtifactWriter,
    HeliusShadowParityAccumulator,
    ParityObservation,
    ParityRecord,
    VERDICT_ADMITTED,
)
from PHX2.free_tier_producer.migration_admission import MigrationProofStore
from PHX2.free_tier_producer.migration_admission import (
    POOL_CREATION_MIGRATION_CPI,
)
from PHX2.free_tier_producer.launcher_contract import (
    PAID_PRIMARY_RUNTIME_ROOT,
)
from PHX2.free_tier_producer.paid_provider import build_live_source_factory


CANARY_PARITY_ROOT = str(
    Path(PAID_PRIMARY_RUNTIME_ROOT).parent / "phx2_helius_primary_parity"
)
SHADOW_STOP_CHAINSTACK_ONLY = "UNEXPLAINED_CHAINSTACK_ONLY_MIGRATION"
SHADOW_STOP_SLOT_MISMATCH = "SLOT_MISMATCH"
SHADOW_STOP_DECODE_MISMATCH = "DECODE_MISMATCH"
PARITY_STOP_STATUSES = frozenset(
    {CHAINSTACK_ONLY, SLOT_MISMATCH, DECODE_MISMATCH}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProductionParityMonitor:
    """Thread-safe late-match accumulator and canary stop classifier."""

    def __init__(
        self,
        *,
        output_path: Path,
        allowed_root: Path,
        late_match_seconds: float = DEFAULT_LATE_MATCH_SECONDS,
        now_fn: Callable[[], str] = _utc_now,
    ) -> None:
        self._lock = threading.RLock()
        self._now = now_fn
        self._accumulator = HeliusShadowParityAccumulator(
            late_match_seconds=late_match_seconds
        )
        self._writer = HeliusParityArtifactWriter(
            output_path,
            allowed_root=allowed_root,
        )
        self._writer.initialize()
        self._counts = {status: 0 for status in MATCH_STATUSES}
        self._records = 0
        self._stop_reason: Optional[str] = None

    def _commit(self, record: ParityRecord) -> None:
        self._writer.write(record)
        self._records += 1
        self._counts[record.match_status] += 1
        if record.match_status == CHAINSTACK_ONLY:
            self._stop_reason = SHADOW_STOP_CHAINSTACK_ONLY
        elif record.match_status == SLOT_MISMATCH:
            self._stop_reason = SHADOW_STOP_SLOT_MISMATCH
        elif record.match_status == DECODE_MISMATCH:
            self._stop_reason = SHADOW_STOP_DECODE_MISMATCH

    def observe(self, observation: ParityObservation) -> None:
        with self._lock:
            record = self._accumulator.observe(observation)
            if record is not None:
                self._commit(record)

    def expire(self) -> None:
        with self._lock:
            for record in self._accumulator.finalize_expired(
                now_timestamp=self._now()
            ):
                self._commit(record)

    def finalize(self) -> None:
        with self._lock:
            for record in self._accumulator.finalize_unmatched():
                self._commit(record)

    def stop_reason(self) -> Optional[str]:
        self.expire()
        with self._lock:
            return self._stop_reason

    def snapshot(self) -> Dict[str, Any]:
        self.expire()
        with self._lock:
            return {
                "records": self._records,
                "matches": self._counts[MATCH],
                "chainstack_only": self._counts[CHAINSTACK_ONLY],
                "helius_only": self._counts[HELIUS_ONLY],
                "slot_mismatches": self._counts[SLOT_MISMATCH],
                "decode_mismatches": self._counts[DECODE_MISMATCH],
                "late_matches": self._counts["LATE_MATCH"],
                "recovered_by_helius_http": self._counts[
                    RECOVERED_BY_HELIUS_HTTP
                ],
                "unresolved": self._counts[UNRESOLVED],
                "stop_reason": self._stop_reason,
            }

    def observe_helius_decoder(
        self,
        record: Mapping[str, object],
        *,
        reconnect_count: int,
        gap_state: str,
        recovery_state: str,
    ) -> None:
        # The tight transport filter still carries ordinary Pump/PumpSwap
        # transactions.  Parity is defined over decoded migrations, not over
        # every filtered transaction, so non-migration decoder diagnostics
        # remain source telemetry and never become HELIUS_ONLY rows.
        if record.get("migration_comparison_scope") is not True:
            return
        self.observe(
            ParityObservation(
                provider_label=PROVIDER_HELIUS_WSS,
                signature_or_hash=str(record["signature_or_hash"]),
                slot=int(record["slot"]),
                receive_timestamp=str(record["receive_timestamp"]),
                migration_type=record.get("migration_type"),  # type: ignore[arg-type]
                mint=record.get("mint"),  # type: ignore[arg-type]
                pool=record.get("pool"),  # type: ignore[arg-type]
                local_decoder_verdict=str(record["local_decoder_verdict"]),
                rejection_reason=record.get("rejection_reason"),  # type: ignore[arg-type]
                bytes=int(record["bytes"]),
                estimated_credits=float(record["estimated_credits"]),
                reconnect_count=int(reconnect_count),
                gap_state=str(gap_state),
                recovery_state=str(recovery_state),
            )
        )

    def observe_helius_recovery(self, outcome: object) -> None:
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
        per_migration = total_credits / len(migrations) if migrations else 0.0
        for event, migration_type in zip(migrations, migration_types):
            signature = str(event.provider_event_id)
            slot = slot_by_signature.get(signature)
            if not isinstance(slot, int):
                continue
            self.observe(
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
                    estimated_credits=per_migration,
                    gap_state="NO_GAP",
                    recovery_state=str(
                        getattr(outcome, "coverage_status", "NOT_REQUESTED")
                    ),
                )
            )


class ChainstackShadowComparator:
    """One isolated comparison iterator with zero production authority."""

    candidate_authority = False
    canonical_state_authority = False
    source_recovery_authority = False
    send_authority = False
    reservation_authority = False
    ledger_authority = False

    def __init__(
        self,
        *,
        monitor: ProductionParityMonitor,
        runtime_config: Any = None,
        max_events: int = 1_000_000,
    ) -> None:
        self._monitor = monitor
        self._proofs = MigrationProofStore()
        self._max_events = max(1, int(max_events))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._source: Any = None
        self._runtime_config = runtime_config
        self._state = "STOPPED"
        self._error_class: Optional[str] = None
        self._observations = 0

    def _rejection(self, record: Dict[str, Any]) -> None:
        # Direct pool creations and unrelated filtered transactions are not
        # migration parity observations.  A proven migration CPI that one
        # decoder rejects is comparison evidence and must be allowed to pair
        # into DECODE_MISMATCH.
        if record.get("classification") != POOL_CREATION_MIGRATION_CPI:
            return
        signature = record.get("transaction_signature")
        slot = record.get("slot")
        if (
            not isinstance(signature, str)
            or not signature
            or isinstance(slot, bool)
            or not isinstance(slot, int)
        ):
            return
        reasons = record.get("reason_codes")
        reason = (
            ",".join(str(value) for value in reasons)
            if isinstance(reasons, list) and reasons
            else "LOCAL_DECODER_REJECTED"
        )
        self._monitor.observe(
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
            )
        )

    def _run(self) -> None:
        self._state = "CONNECTING"
        try:
            factory = build_live_source_factory(
                proof_store=self._proofs,
                runtime_config=self._runtime_config,
                admission_sink=self._rejection,
            )
            source = factory()
            self._source = source
            for event in source.iter_events(max_events=self._max_events):
                if self._stop.is_set():
                    break
                proof = self._proofs.get(str(event.mint))
                if proof is None:
                    continue
                self._state = "CONNECTED"
                self._observations += 1
                self._monitor.observe(
                    ParityObservation(
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
                )
            if not self._stop.is_set():
                self._state = "DEGRADED"
        except Exception as exc:
            name = type(exc).__name__
            self._error_class = (
                name
                if 0 < len(name) <= 64
                and all(char.isalnum() or char == "_" for char in name)
                else "UNSAFE_EXCEPTION_CLASS"
            )
            self._state = "DEGRADED"
        finally:
            self._source = None
            if self._stop.is_set():
                self._state = "STOPPED"

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="phx2-chainstack-shadow-comparator",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 10.0) -> None:
        self._stop.set()
        source = self._source
        close = getattr(source, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, float(timeout_seconds)))
        self._monitor.finalize()
        self._state = "STOPPED"

    def snapshot(self) -> Dict[str, Any]:
        source = self._source
        if self._state == "CONNECTING" and int(
            getattr(source, "events_scanned", 0) or 0
        ) > 0:
            state = "CONNECTED"
        else:
            state = self._state
        return {
            "source": "CHAINSTACK",
            "state": state,
            "observations": self._observations,
            "error_class": self._error_class,
            "candidate_authority": False,
            "canonical_state_authority": False,
            "send_authority": False,
            "reservation_authority": False,
            "ledger_authority": False,
        }


__all__ = (
    "CANARY_PARITY_ROOT",
    "ChainstackShadowComparator",
    "PARITY_STOP_STATUSES",
    "ProductionParityMonitor",
    "SHADOW_STOP_CHAINSTACK_ONLY",
    "SHADOW_STOP_DECODE_MISMATCH",
    "SHADOW_STOP_SLOT_MISMATCH",
)
