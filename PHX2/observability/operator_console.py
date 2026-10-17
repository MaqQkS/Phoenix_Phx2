"""Read-only, artifact-driven PHX2 live operator console.

The console opens no provider, HTTP, RPC, Discord, ledger, paper-engine, or
dashboard client.  It reads existing JSON/JSONL artifacts with in-memory byte
offsets and renders a concise redaction-safe lifecycle stream.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence


_SAFE_TOKEN_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:+-%"
)
_RISK_LABELS = frozenset(("RISK_LOW", "RISK_MEDIUM", "RISK_HIGH", "RISK_UNKNOWN"))
_SHORT_DISPLAY = False


def abbreviate_mint(value: object, *, short: Optional[bool] = None) -> str:
    mint = value if isinstance(value, str) else ""
    if not mint:
        return "UNKNOWN"
    use_short = _SHORT_DISPLAY if short is None else bool(short)
    if not use_short:
        return mint
    if len(mint) <= 14:
        return mint
    suffix = "pump" if mint.endswith("pump") else mint[-4:]
    return f"{mint[:7]}...{suffix}"


def safe_token(value: object, default: str = "UNKNOWN", limit: int = 80) -> str:
    text = value if isinstance(value, str) else ""
    if 0 < len(text) <= limit and all(char in _SAFE_TOKEN_CHARS for char in text):
        return text
    return default


def safe_number(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def format_money(value: object) -> str:
    number = safe_number(value)
    if number is None:
        return "?"
    absolute = abs(number)
    if absolute >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"${number:,.0f}"
    if absolute >= 1:
        return f"${number:,.2f}"
    return f"${number:.10g}"


def _timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")


class JsonlCursor:
    """Incremental, replacement-aware JSONL reader with no writes."""

    def __init__(self, *, dedupe_limit: int = 8192) -> None:
        self.offsets: Dict[Path, int] = {}
        self.identities: Dict[Path, tuple[int, int]] = {}
        self._seen_order: deque[str] = deque()
        self._seen: set[str] = set()
        self._dedupe_limit = max(32, int(dedupe_limit))

    @staticmethod
    def _identity(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return int(stat.st_dev), int(stat.st_ino)

    def _remember(self, path: Path, raw: bytes) -> bool:
        digest = hashlib.sha256(str(path).encode("utf-8") + b"\0" + raw).hexdigest()
        if digest in self._seen:
            return False
        self._seen.add(digest)
        self._seen_order.append(digest)
        while len(self._seen_order) > self._dedupe_limit:
            self._seen.discard(self._seen_order.popleft())
        return True

    def read(self, path: Path) -> List[Dict[str, Any]]:
        try:
            identity = self._identity(path)
            size = path.stat().st_size
        except OSError:
            return []
        offset = self.offsets.get(path, 0)
        if self.identities.get(path) not in (None, identity) or size < offset:
            offset = 0
        self.identities[path] = identity
        records: List[Dict[str, Any]] = []
        try:
            with path.open("rb") as handle:
                handle.seek(offset)
                while True:
                    raw = handle.readline()
                    if not raw:
                        break
                    if not raw.endswith(b"\n"):
                        break
                    offset += len(raw)
                    stripped = raw.strip()
                    if not stripped or not self._remember(path, stripped):
                        continue
                    try:
                        value = json.loads(stripped.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError, TypeError):
                        continue
                    if isinstance(value, dict):
                        records.append(value)
        except OSError:
            return []
        self.offsets[path] = offset
        return records


class JsonSnapshotCursor:
    def __init__(self) -> None:
        self.fingerprints: Dict[Path, str] = {}

    def read(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        digest = hashlib.sha256(raw).hexdigest()
        if self.fingerprints.get(path) == digest:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError):
            return None
        if not isinstance(value, dict):
            return None
        self.fingerprints[path] = digest
        return value


class OperatorConsole:
    def __init__(
        self,
        run_dir: Path | str,
        *,
        output: Callable[[str], None] = print,
        clock: Callable[[], float] = time.time,
        poll_seconds: float = 0.5,
        status_interval_seconds: float = 60.0,
        stall_after_seconds: float = 120.0,
        stale_heartbeat_seconds: float = 90.0,
    ) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.output = output
        self.clock = clock
        self.poll_seconds = max(0.05, float(poll_seconds))
        self.status_interval_seconds = max(1.0, float(status_interval_seconds))
        self.stall_after_seconds = max(1.0, float(stall_after_seconds))
        self.stale_heartbeat_seconds = max(1.0, float(stale_heartbeat_seconds))
        self.jsonl = JsonlCursor()
        self.snapshots = JsonSnapshotCursor()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._output_lock = threading.Lock()
        self._last_heartbeat: Dict[str, Any] = {}
        self._last_status_at = 0.0
        self._watch_states: Dict[str, str] = {}
        self._market_states: Dict[str, str] = {}
        self._stall_started_at: Optional[float] = None
        self._queue_growth_count = 0
        self._warning_last: Dict[str, float] = {}
        self._frozen_ledger_hash: Optional[str] = None
        self._latest_producer_ath: Dict[str, tuple[object, object]] = {}

    @property
    def producer_dir(self) -> Path:
        return self.run_dir / "producer"

    @property
    def paper_dir(self) -> Path:
        return self.run_dir / "paper_root" / "paper"

    @property
    def control_dir(self) -> Path:
        return self.run_dir / "control"

    def emit(self, tag: str, message: str) -> None:
        clean_tag = safe_token(tag, "STATUS", 24)
        with self._output_lock:
            self.output(f"[{_timestamp()}] [{clean_tag}] {message}")

    def start_background(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self.run,
            name="phx2-read-only-operator-console",
            daemon=True,
        )
        self._thread.start()

    def stop_background(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))

    def run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_seconds)

    def _warning(self, code: str, message: str, *, interval: float = 60.0) -> None:
        now = self.clock()
        if now - self._warning_last.get(code, float("-inf")) < interval:
            return
        self._warning_last[code] = now
        self.emit("WARNING", f"{code} {message}".rstrip())

    def _supervisor(self, record: Mapping[str, Any]) -> None:
        event = safe_token(record.get("event"))
        role = safe_token(record.get("role"))
        pid = int(record.get("pid") or 0)
        reason = safe_token(record.get("reason"))
        if event == "SESSION_STARTING":
            self.emit("START", "PHX2 production session")
            self.emit("START", f"run={self.run_dir}")
        elif event == "SUPERVISOR_STARTED":
            self.emit("PROCESS", f"supervisor started pid={pid}")
        elif event == "OPERATOR_CONSOLE_STARTED":
            self.emit("PROCESS", "operator console started mode=READ_ONLY")
        elif event == "CHILD_STARTED":
            self.emit("PROCESS", f"{role.lower()} started pid={pid}")
        elif event in ("CHILD_STOPPED", "OPERATOR_CONSOLE_STOPPING"):
            label = "operator console" if event.startswith("OPERATOR") else role.lower()
            self.emit("PROCESS", f"{label} stopped")
        elif event in ("OPERATOR_SHUTDOWN_REQUESTED", "COOPERATIVE_SHUTDOWN_REQUESTED"):
            self.emit("STOP", f"cooperative shutdown requested reason={reason}")
        elif event == "CHILD_EXIT_UNEXPECTED":
            self._warning("CHILD_EXIT", f"role={role}")
        elif event == "PAPER_CHILD_FAILED":
            attempt = int(record.get("restart_attempts") or 0)
            category = safe_token(record.get("error_category"))
            self._warning(
                "PAPER_CHILD_FAILED",
                f"restart_attempts={attempt} category={category}",
                interval=0.0,
            )
        elif event == "PAPER_CHILD_RESTART_SCHEDULED":
            attempt = int(record.get("attempt") or 0)
            backoff = safe_number(record.get("backoff_seconds"))
            self.emit(
                "PAPER",
                f"restart scheduled attempt={attempt} backoff={backoff or 0:g}s",
            )
        elif event == "PAPER_CHILD_RESTARTED":
            attempt = int(record.get("attempt") or 0)
            self.emit("PROCESS", f"paper restarted pid={pid} attempt={attempt}")
        elif event == "PAPER_DEGRADED":
            attempts = int(record.get("restart_attempts") or 0)
            self._warning(
                "PAPER_DEGRADED",
                f"simulation disabled for session after attempts={attempts}",
                interval=0.0,
            )
        elif event == "FORCED_TERMINATION":
            self.emit("STOP", f"forced termination role={role} pid={pid}")
        elif event in ("SUPERVISOR_REFUSAL", "SUPERVISOR_EXCEPTION"):
            self._warning(event, f"reason={reason}")

    def _handoff(self, record: Mapping[str, Any]) -> None:
        event = safe_token(record.get("event"))
        mint = abbreviate_mint(record.get("token_mint"))
        depth = int(record.get("queue_depth") or 0)
        age = safe_number(record.get("queue_age_seconds"))
        reason = safe_token(record.get("reason"))
        if event == "CANDIDATE_DECODED":
            self.emit("DISCOVERY", f"DECODED mint={mint} source=GRPC")
        elif event == "CANDIDATE_ACCEPTED":
            self.emit("DISCOVERY", f"ACCEPTED mint={mint} source=GRPC queue={depth}")
        elif event in (
            "CANDIDATE_REJECTED",
            "MALFORMED_EVENT",
            "NON_PUMP_DROPPED",
            "DUPLICATE_EVENT",
            "DUPLICATE_MINT",
            "QUEUE_FULL",
        ):
            self.emit("DISCOVERY", f"DROPPED mint={mint} reason={reason or event}")
        elif event == "CANDIDATE_ENQUEUED":
            self.emit("QUEUE", f"ENQUEUED mint={mint} depth={depth}")
        elif event == "CANDIDATE_DEQUEUED":
            age_text = "?" if age is None else f"{age:.1f}s"
            self.emit("QUEUE", f"DEQUEUED mint={mint} age={age_text} depth={depth}")
        elif event == "RUNNER_RECEIVED":
            self.emit("QUEUE", f"RUNNER_RECEIVED mint={mint} handoff=discovery_fn")
        elif event == "WATCHLIST_ACKNOWLEDGED":
            state = safe_token(record.get("state"))
            self.emit("QUEUE", f"ACK mint={mint} downstream=WATCHLIST state={state}")
        elif event == "WATCHLIST_REJECTED":
            self.emit("WATCHLIST", f"REJECTED mint={mint} reason={reason}")

    def _discovery(self, record: Mapping[str, Any]) -> None:
        accepted = int(record.get("accepted_candidates") or 0)
        telemetry = record.get("provider_telemetry")
        telemetry = telemetry if isinstance(telemetry, dict) else {}
        if accepted:
            self.emit(
                "DISCOVERY",
                f"WINDOW accepted={accepted} queue={int(telemetry.get('queue_depth') or 0)}",
            )

    def _heartbeat(self, record: Mapping[str, Any]) -> None:
        provider = record.get("provider_telemetry")
        provider = provider if isinstance(provider, dict) else {}
        prior_provider = self._last_heartbeat.get("provider_telemetry")
        prior_provider = prior_provider if isinstance(prior_provider, dict) else {}
        status = safe_token(provider.get("status"))
        prior_status = safe_token(prior_provider.get("status"))
        active = int(provider.get("active_streams") or 0)
        maximum = int(provider.get("max_active_streams") or 0)
        attempts = int(provider.get("connect_attempts") or 0)
        primary = provider.get("primary") if isinstance(provider.get("primary"), dict) else provider
        verifier = provider.get("verifier") if isinstance(provider.get("verifier"), dict) else {}
        if status != prior_status:
            if status in ("CONNECTING", "RECONNECTING"):
                self.emit("GRPC", f"{status} attempt={attempts}")
            elif status == "CONNECTED":
                self.emit(
                    "GRPC",
                    f"CONNECTED stream={active} max={maximum} attempt={attempts}",
                )
            elif status in ("STALE", "STOPPED", "AUTH_FAILED"):
                self.emit("GRPC", f"{status} stream={active} max={maximum}")
        reconnects = int(provider.get("reconnects") or 0)
        if reconnects > int(prior_provider.get("reconnects") or 0):
            reason = safe_token(provider.get("last_reconnect_reason"))
            self.emit("GRPC", f"RECONNECT count={reconnects} reason={reason}")
        if verifier and safe_token(verifier.get("status")) == "DISABLED":
            self.emit(
                "GRPC",
                "STATUS single_stream primary_stream=%s total_streams=%s "
                "primary_reconnects=%s verifier_stream_status=DISABLED "
                "lp_integrity_mode=%s"
                % (
                    int(primary.get("active_streams") or 0),
                    int(provider.get("total_active_streams") or 0),
                    int(primary.get("reconnects") or 0),
                    safe_token(provider.get("lp_integrity_mode"),
                               "DISABLED_SINGLE_STREAM"),
                ),
            )
        elif verifier:
            self.emit(
                "GRPC",
                "STATUS primary_stream=%s verifier_stream=%s total_streams=%s "
                "primary_reconnects=%s verifier_reconnects=%s verifier_buffer_events=%s"
                % (
                    int(primary.get("active_streams") or 0),
                    int(verifier.get("active_streams") or 0),
                    int(provider.get("total_active_streams") or 0),
                    int(primary.get("reconnects") or 0),
                    int(verifier.get("reconnects") or 0),
                    int(verifier.get("verifier_buffer_events") or 0),
                ),
            )
        filters = provider.get("security_filters")
        if isinstance(filters, dict):
            filter_values = tuple(int(filters.get(key) or 0) for key in (
                "lp_pass", "lp_warn", "lp_fail", "lp_unknown",
                "fee_scam_likely", "fee_suspicious", "fee_pass", "fee_unknown",
                "blocked_fee_scam_likely", "blocked_lp_integrity", "blocked_composite",
            )) + (int(record.get("sends_total") or 0),)
            self.emit(
                "FILTERS",
                "lp_pass=%s lp_warn=%s lp_fail=%s lp_unknown=%s "
                "fee_scam_likely=%s fee_suspicious=%s fee_pass=%s fee_unknown=%s "
                "blocked_fee_scam_likely=%s blocked_lp_integrity=%s blocked_composite=%s sent=%s"
                % filter_values,
            )
        attempts_history = provider.get("stream_attempts")
        if isinstance(attempts_history, list) and attempts_history:
            latest = attempts_history[-1]
            if isinstance(latest, dict) and latest != prior_provider.get("latest_attempt"):
                category = safe_token(latest.get("sanitized_error_category"), "NONE")
                code = safe_token(latest.get("grpc_status_code"), "NONE")
                if category != "NONE" or code != "NONE":
                    self.emit("GRPC", f"STREAM_ERROR category={category} code={code}")
            provider = {**provider, "latest_attempt": latest}
            record = {**record, "provider_telemetry": provider}
        now = self.clock()
        if not self._last_heartbeat or now - self._last_status_at >= self.status_interval_seconds:
            self._last_status_at = now
            scheduler = record.get("market_scheduler")
            scheduler = scheduler if isinstance(scheduler, dict) else {}
            self.emit(
                "STATUS",
                " ".join(
                    (
                        f"stream={active}",
                        f"updates={int(provider.get('source_updates_scanned') or 0)}",
                        f"tx={int(provider.get('source_transactions_scanned') or 0)}",
                        f"accepted={int(provider.get('candidates_accepted') or 0)}",
                        f"queue={int(provider.get('queue_depth') or 0)}",
                        f"pending_baseline={int(record.get('pending_baseline') or 0)}",
                        f"pending_1_20x={int(record.get('pending_1_20x') or 0)}",
                        f"activated={int(record.get('activated') or 0)}",
                        f"active_dip_watch={int(record.get('active_dip_watch') or 0)}",
                        # Active watches vs archived terminal history are
                        # distinct: terminal candidates are never displayed
                        # as still-tracked work (PHX2-E2E-002).
                        f"active_watches={int(record.get('watchlist_tracked') or 0)}"
                        f"/{int(record.get('watchlist_active_capacity') or 0)}",
                        f"terminal_history={int(record.get('watchlist_terminal_history_total') or 0)}",
                        f"capacity_rejections={int(record.get('watchlist_capacity_rejections') or 0)}",
                        f"market={int(record.get('market_calls_total') or 0)}",
                        f"sent={int(((record.get('credit_budget') or {}) if isinstance(record.get('credit_budget'), dict) else {}).get('sent_ok_count') or 0)}",
                    )
                ),
            )
            if scheduler:
                self.emit(
                    "MARKET",
                    "SCHEDULER queue=%s in_flight=%s oldest_deadline=%ss "
                    "slo_breached=%s price_batches=%s overview_calls=%s "
                    "avoided_by_grpc=%s late_rejected=%s"
                    % (
                        int(scheduler.get("queue") or 0),
                        int(scheduler.get("in_flight") or 0),
                        safe_number(scheduler.get("oldest_deadline_age_seconds")) or 0,
                        bool(scheduler.get("slo_breached")),
                        int(scheduler.get("price_batches") or 0),
                        int(scheduler.get("overview_calls") or 0),
                        int(scheduler.get("requests_avoided_by_grpc") or 0),
                        int(scheduler.get("late_results_rejected") or 0),
                    ),
                )
        self._evaluate_heartbeat_warnings(record)
        self._last_heartbeat = dict(record)

    def _evaluate_heartbeat_warnings(self, record: Mapping[str, Any]) -> None:
        provider = record.get("provider_telemetry")
        provider = provider if isinstance(provider, dict) else {}
        accepted = int(provider.get("candidates_accepted") or 0)
        queue_depth = int(provider.get("queue_depth") or 0)
        watchlist = int(record.get("watchlist_active") or 0)
        market_calls = int(record.get("market_calls_total") or 0)
        oldest = safe_number(provider.get("oldest_queue_age_seconds"))
        now = self.clock()
        stalled = accepted > 0 and queue_depth > 0 and watchlist == 0 and market_calls == 0
        if stalled:
            if self._stall_started_at is None:
                self._stall_started_at = now
            age = oldest if oldest is not None else now - self._stall_started_at
            if age >= self.stall_after_seconds:
                self._warning(
                    "PIPELINE_HANDOFF_STALL",
                    f"accepted={accepted} queue={queue_depth} watchlist=0 market_calls=0 oldest_queue_age={age:.0f}s",
                )
        else:
            self._stall_started_at = None
        previous_provider = self._last_heartbeat.get("provider_telemetry")
        previous_provider = previous_provider if isinstance(previous_provider, dict) else {}
        previous_queue = int(previous_provider.get("queue_depth") or 0)
        self._queue_growth_count = (
            self._queue_growth_count + 1 if queue_depth > previous_queue > 0 else 0
        )
        if self._queue_growth_count >= 2:
            self._warning("QUEUE_GROWTH", f"depth={queue_depth}")
        maximum = int(provider.get("max_active_streams") or 0)
        if maximum > 1 or int(provider.get("active_streams") or 0) > 1:
            self._warning(
                "ACTIVE_STREAMS_EXCEEDED",
                f"active={int(provider.get('active_streams') or 0)} max={maximum}",
            )
        if safe_token(provider.get("status")) not in ("CONNECTED", "CONNECTING"):
            self._warning("GRPC_NOT_CONNECTED", f"status={safe_token(provider.get('status'))}")
        if bool(record.get("public_or_subscriber_routing")):
            self._warning("UNEXPECTED_PUBLIC_ROUTE", "")

    def _watch(self, record: Mapping[str, Any]) -> None:
        mint_full = record.get("token_mint")
        mint = abbreviate_mint(mint_full)
        state = safe_token(record.get("status"))
        previous = self._watch_states.get(str(mint_full))
        if previous is None:
            self.emit("WATCHLIST", f"ADDED mint={mint} state={state}")
            self.emit("DASHBOARD", f"CANDIDATE_VISIBLE mint={mint}")
        elif state != previous:
            self.emit("WATCHLIST", f"TRANSITION mint={mint} {previous}->{state}")
        if state in ("EXPIRED", "EVICTED", "REMOVED", "DROPPED_NON_PUMP"):
            reason = safe_token(record.get("last_reason"))
            self.emit("WATCHLIST", f"REMOVED mint={mint} state={state} reason={reason}")
        self._watch_states[str(mint_full)] = state

    def _watch_event(self, record: Mapping[str, Any]) -> None:
        event = safe_token(record.get("event"))
        mint = abbreviate_mint(record.get("token_mint"))
        reason = safe_token(record.get("reason"))
        move = safe_number(record.get("multiplier"))
        move_text = "?" if move is None else f"{move:.3f}x"
        if event == "THRESHOLD_REACHED":
            legacy_move = "?" if move is None else f"{move:.2f}x"
            self.emit("WATCHLIST", f"THRESHOLD mint={mint} move={legacy_move}")
        elif event == "MIGRATION_DETECTED":
            self.emit("DISCOVERY", f"MIGRATION mint={mint}")
        elif event == "BASELINE_CAPTURED":
            self.emit(
                "BASELINE",
                f"CAPTURED mint={mint} MC={format_money(record.get('migration_market_cap_usd'))} "
                f"source={safe_token(record.get('source'))}",
            )
        elif event == "PENDING_BASELINE":
            self.emit("WATCHLIST", f"PENDING_BASELINE mint={mint}")
        elif event == "PENDING_1_20X":
            self.emit(
                "WATCHLIST",
                f"PENDING_1_20X mint={mint} "
                f"target={format_money(record.get('activation_target_market_cap_usd'))}",
            )
        elif event == "PROGRESS":
            self.emit(
                "WATCHLIST",
                f"PROGRESS mint={mint} current={format_money(record.get('current_market_cap_usd'))} "
                f"move={move_text}",
            )
        elif event == "ACTIVATED":
            self.emit("WATCHLIST", f"ACTIVATED mint={mint} move={move_text}")
        elif event == "ACTIVATED_WAITING_FOR_FRESH_MARKET":
            self.emit(
                "WATCHLIST",
                f"ACTIVATED_WAITING_FOR_FRESH_MARKET mint={mint} current_market=REQUIRED",
            )
        elif event == "ACTIVE_DIP_WATCH":
            self.emit("WATCHLIST", f"ACTIVE_DIP_WATCH mint={mint}")
        elif event in ("EXPIRED", "EVICTED", "REMOVED"):
            self.emit("WATCHLIST", f"{event} mint={mint} reason={reason}")
        else:
            state = safe_token(record.get("state"))
            self.emit("WATCHLIST", f"{event} mint={mint} state={state} reason={reason}")

    def _market(self, record: Mapping[str, Any]) -> None:
        mint_full = record.get("token_mint")
        mint = abbreviate_mint(mint_full)
        state = safe_token(record.get("market_state"))
        previous = self._market_states.get(str(mint_full))
        reason = safe_token(record.get("market_reason_code"))
        if state == "MARKET_READY":
            self.emit(
                "MARKET",
                f"READY mint={mint} MC={format_money(record.get('current_market_cap_usd'))} "
                f"LP={format_money(record.get('liquidity_usd'))} price={format_money(record.get('current_price'))}",
            )
        elif state and (state != previous or state in ("MARKET_STALE", "MARKET_INCOMPLETE")):
            self.emit("MARKET", f"{state} mint={mint} reason={reason}")
        ath = record.get("central_ath")
        ath = ath if isinstance(ath, dict) else {}
        ath_value = ath.get("ath_market_cap") or record.get("ath_market_cap_usd")
        provider = safe_token(ath.get("ath_provider") or record.get("ath_provider"))
        observation = safe_token(
            ath.get("ath_observation_type") or record.get("ath_observation_type")
        )
        confirmed = bool(
            ath.get("ath_confirmed")
            or record.get("ath_discord_eligible")
            or not record.get("ath_provisional_ready")
        )
        if ath_value is not None:
            self.emit(
                "ATH",
                f"OBSERVED mint={mint} ATH={format_money(ath_value)} source={provider} "
                f"type={observation} status={'CONFIRMED' if confirmed else 'PROVISIONAL'}",
            )
            self._latest_producer_ath[str(mint_full)] = (ath_value, provider)
        self._market_states[str(mint_full)] = state

    def _candidate(self, record: Mapping[str, Any]) -> None:
        mint = abbreviate_mint(record.get("token_mint"))
        risk = safe_token(record.get("risk_label"))
        reasons = record.get("risk_reasons")
        reason = "UNKNOWN"
        if isinstance(reasons, list) and reasons:
            reason = safe_token(reasons[0])
        if risk in _RISK_LABELS:
            blocked = risk == "RISK_HIGH" or safe_token(record.get("compose_reason")).startswith(
                "SKIPPED_"
            )
            self.emit(
                "RISK",
                f"{'BLOCKED' if blocked else risk} mint={mint} label={risk} reason={reason} "
                f"stage={'PRE_COMPOSE' if blocked else 'OBSERVE'}",
            )
        compose = safe_token(record.get("compose_reason"))
        if compose and compose != "UNKNOWN":
            self.emit(
                "PING",
                f"{'ELIGIBLE' if compose == 'COMPOSE_DECISION_DISPATCHED' else 'BLOCKED'} "
                f"mint={mint} reason={compose}",
            )
        central = record.get("central_ath")
        if isinstance(central, dict) and central:
            self.emit(
                "ATH",
                f"BOUND mint={mint} ATH={format_money(central.get('ath_market_cap'))} "
                f"source={safe_token(central.get('ath_provider'))}",
            )
        if bool(record.get("transport_attempted")):
            transport = safe_token(record.get("delivery_transport"), "DELIVERY")
            self.emit(transport, f"TRANSPORT_ATTEMPT mint={mint}")
        fee = record.get("fee_gate")
        if isinstance(fee, dict) and fee:
            self.emit(
                "FEE_GATE",
                f"mint={mint} label={safe_token(fee.get('fee_gate_label'))} "
                f"creator={safe_token(fee.get('creator_share'))} "
                f"bribes={safe_token(fee.get('bribe_share_pct'))}",
            )
        lp = record.get("lp_integrity")
        if isinstance(lp, dict) and lp:
            reasons = lp.get("lp_integrity_reasons") or []
            reason = safe_token(reasons[0]) if isinstance(reasons, list) and reasons else "NONE"
            self.emit(
                "LIQUIDITY",
                f"{safe_token(lp.get('lp_integrity'))} mint={mint} reason={reason}",
            )

    def _liquidity(self, record: Mapping[str, Any]) -> None:
        mint = abbreviate_mint(record.get("base_mint"))
        event = safe_token(record.get("event_kind"))
        pool = abbreviate_mint(record.get("pool"), short=True)
        quote = record.get("quote_amount")
        self.emit(
            "LIQUIDITY",
            f"{event} mint={mint} pool={pool} quote={quote} slot={record.get('slot')}",
        )

    def _security(self, record: Mapping[str, Any]) -> None:
        mint = abbreviate_mint(record.get("token_mint"))
        decision = record.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        fee = decision.get("fee_snapshot") if isinstance(decision.get("fee_snapshot"), dict) else {}
        lp = decision.get("lp_snapshot") if isinstance(decision.get("lp_snapshot"), dict) else {}
        lp_disabled = (
            decision.get("lp_snapshot") is None
            and safe_token(decision.get("lp_integrity_mode"))
            == "DISABLED_SINGLE_STREAM")
        verdict = safe_token(decision.get("verdict"))
        fee_reasons = fee.get("fee_gate_reasons") or []
        lp_reasons = lp.get("lp_integrity_reasons") or []
        final_reasons = decision.get("final_block_reasons") or []
        fee_reason_text = ",".join(
            safe_token(value) for value in fee_reasons if isinstance(value, str)) or "NONE"
        lp_reason_text = ",".join(
            safe_token(value) for value in lp_reasons if isinstance(value, str)) or "NONE"
        self.emit(
            "FEE_GATE",
            f"mint={mint} label={safe_token(fee.get('fee_gate_label'))} "
            f"reasons={fee_reason_text}",
        )
        if lp_disabled:
            self.emit("LIQUIDITY", f"DISABLED mint={mint} mode=DISABLED_SINGLE_STREAM")
        else:
            self.emit(
                "LIQUIDITY",
                f"{safe_token(lp.get('lp_integrity'))} mint={mint} reasons={lp_reason_text}",
            )
        if verdict == "HARD_BLOCK":
            if "PHX1_FEE_GATE_SCAM_LIKELY" in final_reasons:
                self.emit(
                    "RISK",
                    f"BLOCKED mint={mint} source=PHX1_FEE_GATE "
                    "reason=PHX1_FEE_GATE_SCAM_LIKELY",
                )
            if any(value in final_reasons for value in (
                    "LP_INTEGRITY_FAIL", "LP_INTEGRITY_UNKNOWN")):
                self.emit(
                    "RISK",
                    f"BLOCKED mint={mint} source=LP_INTEGRITY reason={lp_reason_text}",
                )
            if "LP_AND_FEE_COMPOSITE_BLOCK" in final_reasons:
                self.emit(
                    "RISK",
                    f"BLOCKED mint={mint} source=LP_AND_FEE_COMPOSITE "
                    "reason=LP_AND_FEE_COMPOSITE_BLOCK",
                )

    def _send(self, record: Mapping[str, Any]) -> None:
        mint = abbreviate_mint(record.get("token_mint"))
        sent = bool(record.get("sent_ok"))
        telegram = record.get("telegram")
        telegram = telegram if isinstance(telegram, dict) else {}
        transport = safe_token(
            record.get("delivery_transport") or record.get("transport_kind"),
            "DELIVERY",
        )
        if sent:
            message_id = telegram.get("message_id") or record.get("message_id")
            suffix = f" message_id={message_id}" if message_id is not None else ""
            self.emit(transport, f"SENT_OK mint={mint}{suffix}")
        else:
            category = safe_token(
                telegram.get("result") or record.get("transport_result")
                or record.get("exception_type"),
                "DELIVERY_FAILURE",
            )
            self.emit(transport, f"DELIVERY_FAILURE mint={mint} category={category}")

    def _paper(self, record: Mapping[str, Any]) -> None:
        event = safe_token(record.get("event"))
        mint = abbreviate_mint(record.get("mint"))
        strategy = safe_token(record.get("strategy_name"))
        reason = safe_token(record.get("reason"))
        if event == "POSITION_OPENED":
            self.emit("PAPER", f"POSITION_OPENED mint={mint} strategy={strategy}")
        elif event in ("POSITION_CLOSED", "PARTIAL_EXIT"):
            self.emit("PAPER", f"{event} mint={mint} strategy={strategy} reason={reason}")
        elif event not in ("HEARTBEAT", "UNKNOWN"):
            self.emit("PAPER", f"{event} mint={mint} strategy={strategy}")

    def _monitor(self, record: Mapping[str, Any]) -> None:
        sent = int(record.get("sent_ok_count") or 0)
        delta = int(record.get("active_ledger_delta") or 0)
        if sent != delta:
            code = "DELIVERY_WITHOUT_LEDGER_DELTA" if sent > delta else "LEDGER_DELTA_WITHOUT_SENT_OK"
            self._warning(code, f"sent_ok={sent} ledger_delta={delta}")
        frozen = record.get("frozen_ledger_sha256")
        if isinstance(frozen, str) and frozen:
            if self._frozen_ledger_hash is None:
                self._frozen_ledger_hash = frozen
            elif frozen != self._frozen_ledger_hash:
                self._warning("FROZEN_LEDGER_CHANGE", "")

    def _paper_status(self, record: Mapping[str, Any]) -> None:
        lag = safe_number(record.get("consumer_lag_seconds") or record.get("input_lag_seconds"))
        if lag is not None and lag > self.stall_after_seconds:
            self._warning("PAPER_CONSUMER_LAG", f"age={lag:.0f}s")
        mint = record.get("token_mint") or record.get("mint")
        ath = record.get("ath_market_cap")
        provider = record.get("ath_provider")
        if mint and str(mint) in self._latest_producer_ath and ath is not None:
            expected_ath, expected_provider = self._latest_producer_ath[str(mint)]
            if str(ath) != str(expected_ath):
                self._warning("ATH_NUMERIC_DISAGREEMENT", f"mint={abbreviate_mint(mint)}")
            if provider is not None and str(provider) != str(expected_provider):
                self._warning("ATH_PROVENANCE_DISAGREEMENT", f"mint={abbreviate_mint(mint)}")

    def render_record(self, record: Mapping[str, Any]) -> None:
        kind = safe_token(record.get("kind"))
        event = safe_token(record.get("event"))
        if kind == "PHX2_SUPERVISOR_EVENT":
            self._supervisor(record)
        elif kind == "PHX2_PROVIDER_HANDOFF":
            self._handoff(record)
        elif kind in ("PAID_PROVIDER_DISCOVERY_WINDOW", "FREE_TIER_DISCOVERY_WINDOW"):
            self._discovery(record)
        elif kind == "PRODUCTION_LIVE_HEARTBEAT":
            self._heartbeat(record)
        elif kind == "FREE_TIER_PRICING_TAIL":
            self._market(record)
        elif kind == "BUILD30_CANDIDATE_RECHECK":
            self._candidate(record)
        elif kind == "PHX2_WATCHLIST_EVENT":
            self._watch_event(record)
        elif kind == "PHX2_LIQUIDITY_EVENT":
            self._liquidity(record)
        elif kind == "PHX2_SECURITY_DECISION":
            self._security(record)
        elif kind in ("PHX2_TELEGRAM_SEND_ATTEMPT", "FREE_TIER_PRIVATE_SEND_ATTEMPT",
                      "PRODUCTION_LIVE_SEND_ATTEMPT"):
            self._send(record)
        elif kind == "FREE_TIER_DISCORD_BLOCK":
            self.emit(
                "RISK",
                f"BLOCKED mint={abbreviate_mint(record.get('token_mint'))} "
                f"reason={safe_token(record.get('terminal_decision'))} stage=PRE_RESERVATION",
            )
        elif record.get("checkpoint_kind") is not None:
            self._checkpoint_header(record)
        elif record.get("checkpoint_record_kind") == "PHX2_QUARANTINED_CANDIDATE":
            self._checkpoint_quarantined_candidate(record)
        elif kind in ("PHX2_CHECKPOINT_QUARANTINE", "PHX2_CHECKPOINT_STATUS"):
            self._checkpoint_status(record)
        elif event != "UNKNOWN":
            self._paper(record)
        elif "status" in record and "token_mint" in record:
            self._watch(record)

    # ---- PHX2-E2E-005 authenticated checkpoint visibility ------------------

    def _checkpoint_header(self, record: Mapping[str, Any]) -> None:
        self.emit(
            "CHECKPOINT",
            f"{safe_token(record.get('checkpoint_kind'))} "
            f"schema={safe_token(record.get('schema_version'))} "
            f"generation={safe_number(record.get('generation'))} "
            f"records={safe_number(record.get('record_count'))}",
        )

    def _checkpoint_quarantined_candidate(self, record: Mapping[str, Any]) -> None:
        self._warning(
            "CHECKPOINT_CANDIDATE_QUARANTINED",
            f"mint={abbreviate_mint(record.get('token_mint'))} "
            f"reason={safe_token(record.get('quarantine_reason'))}",
        )

    def _checkpoint_status(self, record: Mapping[str, Any]) -> None:
        """A quarantined checkpoint is surfaced with its exact safe reason —
        never rendered as an empty healthy watchlist."""

        for label in ("watch", "ath"):
            block = record.get(label)
            if not isinstance(block, Mapping):
                continue
            status = safe_token(block.get("checkpoint_status"))
            if block.get("checkpoint_quarantined"):
                self._warning(
                    "CHECKPOINT_QUARANTINED",
                    f"store={label.upper()} "
                    f"reason={safe_token(block.get('checkpoint_quarantine_reason'))}",
                )
            else:
                self.emit(
                    "CHECKPOINT",
                    f"store={label.upper()} status={status} "
                    f"generation={safe_number(block.get('checkpoint_generation'))}",
                )

    def _jsonl_paths(self) -> Iterable[Path]:
        fixed = (
            self.control_dir / "supervisor_events.jsonl",
            self.producer_dir / "provider_handoff.jsonl",
            self.producer_dir / "activation_events.jsonl",
            self.producer_dir / "liquidity_events.jsonl",
            self.producer_dir / "security_decisions.jsonl",
            self.producer_dir / "discovery_windows.jsonl",
            self.producer_dir / "heartbeat.jsonl",
            self.producer_dir / "watch_state.jsonl",
            self.producer_dir / "pricing_tail.jsonl",
            self.producer_dir / "discord_blocks.jsonl",
            self.producer_dir / "sends.jsonl",
            self.producer_dir / "would_ping_records.jsonl",
            self.paper_dir / "paper_events.jsonl",
        )
        yield from fixed
        candidates = self.producer_dir / "candidates"
        try:
            yield from sorted(candidates.glob("*.jsonl"))
        except OSError:
            return

    def poll_once(self) -> None:
        for path in self._jsonl_paths():
            for record in self.jsonl.read(path):
                self.render_record(record)
        for path, handler in (
            (self.control_dir / "monitor_status.json", self._monitor),
            (self.paper_dir / "heartbeat.json", self._paper_status),
            (self.paper_dir / "paper_summary.json", self._paper_status),
        ):
            record = self.snapshots.read(path)
            if record is not None:
                handler(record)
        final = self.snapshots.read(self.control_dir / "supervisor_final.json")
        if final is not None:
            self.emit(
                "STOP",
                f"FINAL reason={safe_token(final.get('stop_reason'))} "
                f"sent={int(final.get('sent_ok_count') or 0)} "
                f"streams={int(final.get('active_streams') or 0)} "
                f"forced={int(final.get('forced_termination_count') or 0)}",
            )
        heartbeat = self.producer_dir / "producer_heartbeat.json"
        if heartbeat.is_file():
            try:
                age = max(0.0, self.clock() - heartbeat.stat().st_mtime)
            except OSError:
                age = 0.0
            if age > self.stale_heartbeat_seconds:
                self._warning("STALE_HEARTBEAT", f"age={age:.0f}s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PHX2 read-only operator console")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--short-display", action="store_true",
                        help="abbreviate public mint addresses in console output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    global _SHORT_DISPLAY
    args = build_parser().parse_args(argv)
    _SHORT_DISPLAY = bool(args.short_display)
    console = OperatorConsole(args.run_dir, poll_seconds=args.poll_seconds)
    print(f"[{_timestamp()}] [START] read-only observer run={console.run_dir}")
    try:
        console.run()
    except KeyboardInterrupt:
        console.stop_background()
        print(f"[{_timestamp()}] [STOP] operator console stopped; production unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "JsonSnapshotCursor",
    "JsonlCursor",
    "OperatorConsole",
    "abbreviate_mint",
    "build_parser",
    "format_money",
    "main",
    "safe_token",
)
