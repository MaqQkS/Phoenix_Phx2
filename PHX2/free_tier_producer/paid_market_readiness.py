"""Per-candidate paid-market readiness state and bounded, recoverable retry policy.

The tracker is deliberately independent of HTTP and dispatch.  A caller supplies one
redaction-safe market attempt; the tracker classifies it, schedules the next per-mint
refresh, and keeps transient newborn-token states recoverable without ever making them
eligible for compose/reserve/send.

PHX2-E2E-004 correction: exhausting the initial readiness grace period (too many
transient attempts or too much grace time) no longer terminalizes a candidate.  It
enters ``MARKET_RECOVERY_BACKOFF`` — a bounded, observable, recoverable state that stops
aggressive polling, schedules a future recovery probe, retains all candidate state, and
fully recovers to ``MARKET_READY`` on the next complete fresh market observation.  The
old permanent ``MARKET_UNAVAILABLE``/``MARKET_TERMINAL`` behavior, which returned
``MARKET_TERMINAL`` forever and never invoked the fetch function again, is gone.  The
candidate remains active until the independent watch-expiration policy expires it or an
independent permanent blocker terminalizes it — market readiness itself never does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from PHX2.free_tier_producer.phx1_parity_policy import (
    adaptive_refresh_interval_seconds,
    current_alert_policy,
    is_phx1_parity,
)


MARKET_PENDING = "MARKET_PENDING"
MARKET_READY = "MARKET_READY"
MARKET_INDEXING = "MARKET_INDEXING"
MARKET_INCOMPLETE = "MARKET_INCOMPLETE"
MARKET_STALE = "MARKET_STALE"
MARKET_INVALID = "MARKET_INVALID"
MARKET_RECOVERY_BACKOFF = "MARKET_RECOVERY_BACKOFF"
# Backward-compatibility only.  A candidate may no longer reach this state merely
# because transient attempts or grace time were exhausted; grace exhaustion now enters
# MARKET_RECOVERY_BACKOFF.  The token is retained so legacy checkpoints/imports remain
# importable and can be visibly migrated (see ``classify_legacy_market_state``).
MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"

_TRANSIENT = (MARKET_INDEXING, MARKET_INCOMPLETE)

# Grace-exhaustion reasons recorded when a candidate enters recovery backoff.
GRACE_EXHAUSTION_ATTEMPTS = "ATTEMPT_LIMIT_EXHAUSTED"
GRACE_EXHAUSTION_TIME = "GRACE_TIME_EXHAUSTED"
GRACE_EXHAUSTION_BOTH = "ATTEMPT_AND_GRACE_TIME_EXHAUSTED"

# Recovery reason codes (candidate-local, redaction-safe, closed set).
RECOVERY_BACKOFF_NOT_DUE = "MARKET_RECOVERY_BACKOFF_NOT_DUE"
RECOVERY_PROBE_ATTEMPTED = "MARKET_RECOVERY_PROBE_ATTEMPTED"
RECOVERY_PROBE_FAILED = "MARKET_RECOVERY_PROBE_FAILED"
RECOVERY_SUCCEEDED = "MARKET_RECOVERED"

# Legacy-terminal migration markers (build30 checkpoint restore / tracker seeding).
LEGACY_TERMINAL_MIGRATED = "LEGACY_MARKET_TERMINAL_MIGRATED_TO_RECOVERY"
LEGACY_TERMINAL_UNCLASSIFIED = "MARKET_LEGACY_TERMINAL_UNCLASSIFIED"

# Legacy reason codes that unambiguously identify transient grace/attempt exhaustion.
# Only these may be auto-migrated into recovery backoff; anything else fails closed.
_LEGACY_TRANSIENT_EXHAUSTION_REASONS = frozenset((
    "MARKET_GRACE_EXHAUSTED",
    GRACE_EXHAUSTION_ATTEMPTS,
    GRACE_EXHAUSTION_TIME,
    GRACE_EXHAUSTION_BOTH,
))


def _parse_epoch(value: object) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).timestamp()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def classify_legacy_market_state(
    market_state: object, reason_code: object
) -> Tuple[bool, str]:
    """Classify a restored legacy market-readiness state for E2E-004 migration.

    Returns ``(migratable, marker)``.

    ``migratable`` is True only when the legacy state is a market-unavailable
    terminal whose reason unambiguously identifies transient grace/attempt
    exhaustion — the exact class the old code turned permanent.  Such a state is
    safely converted to ``MARKET_RECOVERY_BACKOFF`` with the
    ``LEGACY_MARKET_TERMINAL_MIGRATED_TO_RECOVERY`` marker.

    Any other legacy market-unavailable state (unknown/empty reason, or a
    non-exhaustion reason) is ambiguous and must fail closed visibly with the
    ``MARKET_LEGACY_TERMINAL_UNCLASSIFIED`` marker — it is NOT guessed into
    recovery and is left for the separate checkpoint-remediation task
    (PHX2-E2E-005).  Non-terminal states are never migrated.
    """

    if market_state != MARKET_UNAVAILABLE:
        return (False, "")
    reason = str(reason_code or "")
    if reason in _LEGACY_TRANSIENT_EXHAUSTION_REASONS:
        return (True, LEGACY_TERMINAL_MIGRATED)
    return (False, LEGACY_TERMINAL_UNCLASSIFIED)


@dataclass(frozen=True)
class PaidMarketReadinessConfig:
    indexing_grace_seconds: float = 1800.0
    max_transient_attempts: int = 30
    retry_backoff_seconds: Tuple[float, ...] = (5.0, 10.0, 20.0, 40.0, 60.0)
    ready_refresh_seconds: float = 30.0
    stale_refresh_seconds: float = 15.0
    invalid_refresh_seconds: float = 60.0
    # Bounded recovery-backoff schedule entered after grace exhaustion.
    # 60 -> 120 -> 240 -> 480 -> 900 -> 900 ... (doubling, capped).
    recovery_initial_delay_seconds: float = 60.0
    recovery_backoff_multiplier: float = 2.0
    recovery_max_delay_seconds: float = 900.0

    def __post_init__(self) -> None:
        if self.indexing_grace_seconds <= 0:
            raise ValueError("indexing_grace_seconds must be positive")
        if isinstance(self.max_transient_attempts, bool) or self.max_transient_attempts <= 0:
            raise ValueError("max_transient_attempts must be positive")
        if not self.retry_backoff_seconds or any(v < 0 for v in self.retry_backoff_seconds):
            raise ValueError("retry_backoff_seconds must be non-empty and non-negative")
        if self.recovery_initial_delay_seconds <= 0:
            raise ValueError("recovery_initial_delay_seconds must be positive")
        if self.recovery_backoff_multiplier < 1.0:
            raise ValueError("recovery_backoff_multiplier must be >= 1.0")
        if self.recovery_max_delay_seconds < self.recovery_initial_delay_seconds:
            raise ValueError(
                "recovery_max_delay_seconds must be >= recovery_initial_delay_seconds")

    def next_recovery_delay(self, current: float) -> float:
        """Next bounded recovery delay from the current one (doubling, capped)."""

        if current <= 0:
            return float(self.recovery_initial_delay_seconds)
        return float(min(
            current * self.recovery_backoff_multiplier,
            self.recovery_max_delay_seconds,
        ))


class PaidMarketReadinessTracker:
    """Mint-keyed bounded, recoverable retry state.

    Never reserves, dispatches, or mutates a ledger.  Never permanently
    terminalizes a candidate for transient market-data failure; grace
    exhaustion enters an observable recovery backoff that probes the provider
    again on a bounded schedule and recovers on complete fresh data.
    """

    def __init__(self, config: Optional[PaidMarketReadinessConfig] = None) -> None:
        self.config = config or PaidMarketReadinessConfig()
        self._mints: Dict[str, Dict[str, Any]] = {}
        self._counters: Dict[str, int] = {
            "market_grace_exhausted_total": 0,
            "market_recovery_backoff_entered": 0,
            "market_recovery_probe_skipped_not_due": 0,
            "market_recovery_probe_attempted": 0,
            "market_recovery_probe_failed": 0,
            "market_recovery_succeeded": 0,
            "market_recovery_state_reset": 0,
            "market_legacy_terminal_migrated": 0,
            # Invariant: this must remain 0 for candidate-local transient
            # readiness failures under the new production path.
            "market_terminal_candidate_state_reached": 0,
        }

    # ------------------------------------------------------------------ state
    def _new_state(self, first_epoch: float) -> Dict[str, Any]:
        return {
            "first_seen_epoch": first_epoch,
            # Resettable grace anchor: a successful recovery starts a fresh
            # normal grace/recovery cycle for a later transient failure.
            "grace_started_epoch": first_epoch,
            "attempt_count": 0,
            "transient_attempt_count": 0,
            "consecutive_failure_count": 0,
            "state": MARKET_PENDING,
            "reason_code": "MARKET_NOT_QUERIED",
            "next_retry_epoch": first_epoch,
            "transitions": [],
            "last_attempt_at_utc": None,
            "last_success_at_utc": None,
            "last_failure_at_utc": None,
            "last_provider_status": None,
            "first_ready_at_utc": None,
            "last_ready_attempt": None,
            # Recovery-backoff sub-state.
            "recovery_active": False,
            "recovery_attempt_count": 0,
            "recovery_attempt_count_history": 0,
            "recovery_backoff_seconds": 0.0,
            "next_recovery_probe_epoch": None,
            "grace_exhaustion_reason": None,
            "recovered_at_utc": None,
            "legacy_terminal_migrated": False,
            # Adaptive-cadence heat anchor (PHX1_PARITY only; LEGACY ignores it).
            "last_activity_epoch": first_epoch,
            "is_active_dip": False,
        }

    def resolve(
        self,
        mint: str,
        *,
        migration_time_utc: Optional[str],
        now_iso_fn: Callable[[], str],
        fetch_attempt_fn: Callable[[str], Mapping[str, Any]],
    ) -> Dict[str, Any]:
        now_iso = now_iso_fn()
        now_epoch = _parse_epoch(now_iso)
        if now_epoch is None:
            # A malformed clock is unsafe market data, not an indexing miss.
            return self._result(
                mint, self._mints.get(mint), MARKET_INVALID, "MARKET_CLOCK_INVALID",
                now_iso, attempts=[], next_epoch=None,
            )
        state = self._mints.get(mint)
        if state is None:
            first_epoch = _parse_epoch(migration_time_utc) or now_epoch
            state = self._new_state(first_epoch)
            self._mints[mint] = state

        # ---- RECOVERY BACKOFF PHASE ---------------------------------------
        # Entered after grace exhaustion.  Aggressive polling has stopped; we
        # probe the provider exactly once per due recovery evaluation.  The
        # candidate is retained and active the whole time.
        if state["recovery_active"]:
            probe_at = float(state["next_recovery_probe_epoch"] or 0.0)
            if now_epoch < probe_at:
                # Not due: do NOT call the provider; keep the candidate active.
                self._counters["market_recovery_probe_skipped_not_due"] += 1
                return self._result(
                    mint, state, MARKET_RECOVERY_BACKOFF, RECOVERY_BACKOFF_NOT_DUE,
                    now_iso, attempts=[], next_epoch=probe_at,
                    basis=MARKET_RECOVERY_BACKOFF, fetch_performed=False,
                    fetch_due=False,
                )
            return self._probe_recovery(mint, state, now_iso, now_epoch, fetch_attempt_fn)

        # ---- NORMAL / GRACE PHASE -----------------------------------------
        next_retry = float(state.get("next_retry_epoch") or 0.0)
        if now_epoch < next_retry:
            cached_ready = (state.get("last_ready_attempt")
                            if state.get("state") == MARKET_READY else None)
            return self._result(
                mint, state, str(state["state"]), str(state["reason_code"]), now_iso,
                attempts=[], next_epoch=next_retry, basis="MARKET_BACKOFF",
                attempt=cached_ready, fetch_performed=False, fetch_due=False,
            )

        attempt = dict(fetch_attempt_fn(now_iso))
        state["attempt_count"] += 1
        state["last_attempt_at_utc"] = now_iso
        state["last_provider_status"] = attempt.get("provider_market_state")
        market_state, reason_code = self._classify(attempt)

        if market_state in _TRANSIENT:
            state["transient_attempt_count"] += 1
            state["consecutive_failure_count"] += 1
            state["last_failure_at_utc"] = now_iso
            grace_age = max(0.0, now_epoch - float(state["grace_started_epoch"]))
            attempts_exhausted = (
                state["transient_attempt_count"] >= self.config.max_transient_attempts)
            time_exhausted = grace_age >= self.config.indexing_grace_seconds
            if attempts_exhausted or time_exhausted:
                # PHX2-E2E-004: enter recovery backoff instead of terminalizing.
                if attempts_exhausted and time_exhausted:
                    exhaustion = GRACE_EXHAUSTION_BOTH
                elif attempts_exhausted:
                    exhaustion = GRACE_EXHAUSTION_ATTEMPTS
                else:
                    exhaustion = GRACE_EXHAUSTION_TIME
                self._enter_recovery_backoff(state, now_epoch, exhaustion)
                market_state = MARKET_RECOVERY_BACKOFF
                reason_code = exhaustion
        elif market_state == MARKET_READY:
            state["transient_attempt_count"] = 0
            state["consecutive_failure_count"] = 0
            state["last_ready_attempt"] = dict(attempt)
            state["last_success_at_utc"] = now_iso
            if state.get("first_ready_at_utc") is None:
                state["first_ready_at_utc"] = now_iso
        else:
            # STALE / INVALID: recoverable per existing classification, own cadence.
            state["consecutive_failure_count"] += 1
            state["last_failure_at_utc"] = now_iso

        self._record_transition(state, market_state, now_iso, reason_code)
        state["state"] = market_state
        state["reason_code"] = reason_code
        if market_state == MARKET_RECOVERY_BACKOFF:
            next_epoch = state["next_recovery_probe_epoch"]
        else:
            delay = self._retry_delay(state, market_state)
            state["next_retry_epoch"] = now_epoch + delay
            next_epoch = state["next_retry_epoch"]
        return self._result(
            mint, state, market_state, reason_code, now_iso,
            attempts=[attempt], next_epoch=next_epoch, attempt=attempt,
            fetch_performed=True, fetch_due=True,
        )

    # ------------------------------------------------------------- recovery
    def _enter_recovery_backoff(
        self, state: Dict[str, Any], now_epoch: float, exhaustion: str
    ) -> None:
        state["recovery_active"] = True
        state["grace_exhaustion_reason"] = exhaustion
        state["recovery_attempt_count"] = 0
        state["recovery_backoff_seconds"] = float(
            self.config.recovery_initial_delay_seconds)
        state["next_recovery_probe_epoch"] = (
            now_epoch + float(self.config.recovery_initial_delay_seconds))
        # Recovery replaces the normal aggressive schedule entirely.
        state["next_retry_epoch"] = None
        self._counters["market_grace_exhausted_total"] += 1
        self._counters["market_recovery_backoff_entered"] += 1
        # Failure history is deliberately NOT reset when entering recovery.

    def _probe_recovery(
        self,
        mint: str,
        state: Dict[str, Any],
        now_iso: str,
        now_epoch: float,
        fetch_attempt_fn: Callable[[str], Mapping[str, Any]],
    ) -> Dict[str, Any]:
        # Exactly one provider call per due recovery evaluation.
        self._counters["market_recovery_probe_attempted"] += 1
        attempt = dict(fetch_attempt_fn(now_iso))
        state["attempt_count"] += 1
        state["last_attempt_at_utc"] = now_iso
        state["last_provider_status"] = attempt.get("provider_market_state")
        market_state, reason_code = self._classify(attempt)

        if market_state == MARKET_READY:
            # Full recovery: only complete fresh data under the existing
            # production contract (all_present) reaches MARKET_READY here.
            state["recovery_active"] = False
            state["transient_attempt_count"] = 0
            state["consecutive_failure_count"] = 0
            state["recovery_backoff_seconds"] = 0.0
            state["next_recovery_probe_epoch"] = None
            state["grace_exhaustion_reason"] = None
            state["legacy_terminal_migrated"] = False
            # Archive the spent recovery attempts as historical telemetry, then
            # reset the active counter.
            state["recovery_attempt_count_history"] += state["recovery_attempt_count"]
            state["recovery_attempt_count"] = 0
            state["recovered_at_utc"] = now_iso
            state["last_success_at_utc"] = now_iso
            state["last_ready_attempt"] = dict(attempt)
            if state.get("first_ready_at_utc") is None:
                state["first_ready_at_utc"] = now_iso
            # A later transient failure begins a fresh normal grace cycle.
            state["grace_started_epoch"] = now_epoch
            self._counters["market_recovery_succeeded"] += 1
            self._counters["market_recovery_state_reset"] += 1
            self._record_transition(state, MARKET_READY, now_iso, reason_code)
            state["state"] = MARKET_READY
            state["reason_code"] = reason_code
            state["next_retry_epoch"] = now_epoch + self.config.ready_refresh_seconds
            return self._result(
                mint, state, MARKET_READY, reason_code, now_iso,
                attempts=[attempt], next_epoch=state["next_retry_epoch"],
                attempt=attempt, fetch_performed=True, fetch_due=True,
            )

        # Failed recovery probe: remain in backoff, schedule the next bounded delay.
        state["recovery_attempt_count"] += 1
        state["consecutive_failure_count"] += 1
        state["last_failure_at_utc"] = now_iso
        self._counters["market_recovery_probe_failed"] += 1
        state["recovery_backoff_seconds"] = self.config.next_recovery_delay(
            float(state["recovery_backoff_seconds"]))
        state["next_recovery_probe_epoch"] = (
            now_epoch + float(state["recovery_backoff_seconds"]))
        self._record_transition(
            state, MARKET_RECOVERY_BACKOFF, now_iso, reason_code)
        state["state"] = MARKET_RECOVERY_BACKOFF
        state["reason_code"] = reason_code
        return self._result(
            mint, state, MARKET_RECOVERY_BACKOFF, reason_code, now_iso,
            attempts=[attempt], next_epoch=state["next_recovery_probe_epoch"],
            attempt=attempt, fetch_performed=True, fetch_due=True,
        )

    def seed_recovery_state(
        self,
        mint: str,
        *,
        now_iso: str,
        next_recovery_probe_at_utc: Optional[str] = None,
        recovery_backoff_seconds: Optional[float] = None,
        recovery_attempt_count: int = 0,
        grace_exhaustion_reason: Optional[str] = None,
        legacy_migrated: bool = False,
        migration_time_utc: Optional[str] = None,
    ) -> bool:
        """Restore a candidate directly into recovery backoff.

        Used on restart so a candidate whose persisted market-readiness state is
        recovery backoff (or a migrated legacy terminal) does NOT immediately
        hammer the provider: the next ``resolve`` before ``next_recovery_probe``
        returns ``MARKET_RECOVERY_BACKOFF_NOT_DUE`` with zero fetches.  Returns
        True when the candidate was seeded.
        """

        now_epoch = _parse_epoch(now_iso)
        if now_epoch is None:
            return False
        state = self._mints.get(mint)
        if state is None:
            first_epoch = _parse_epoch(migration_time_utc) or now_epoch
            state = self._new_state(first_epoch)
            self._mints[mint] = state
        backoff = (float(recovery_backoff_seconds)
                   if recovery_backoff_seconds and recovery_backoff_seconds > 0
                   else float(self.config.recovery_initial_delay_seconds))
        backoff = min(backoff, float(self.config.recovery_max_delay_seconds))
        probe_epoch = _parse_epoch(next_recovery_probe_at_utc)
        if probe_epoch is None:
            probe_epoch = now_epoch + backoff
        state["recovery_active"] = True
        state["recovery_backoff_seconds"] = backoff
        state["next_recovery_probe_epoch"] = probe_epoch
        state["next_retry_epoch"] = None
        state["recovery_attempt_count"] = max(0, int(recovery_attempt_count))
        state["grace_exhaustion_reason"] = (
            grace_exhaustion_reason or state.get("grace_exhaustion_reason"))
        state["state"] = MARKET_RECOVERY_BACKOFF
        state["reason_code"] = (
            LEGACY_TERMINAL_MIGRATED if legacy_migrated else RECOVERY_BACKOFF_NOT_DUE)
        state["legacy_terminal_migrated"] = bool(legacy_migrated)
        if legacy_migrated:
            self._counters["market_legacy_terminal_migrated"] += 1
        return True

    def observe_scheduled_attempt(
        self,
        mint: str,
        *,
        migration_time_utc: Optional[str],
        now_iso: str,
        attempt: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Apply an already-completed scheduler attempt to the existing policy.

        The deadline scheduler owns when HTTP work starts; this tracker remains
        the sole owner of readiness/recovery transitions.  A successful late
        result may recover immediately. A failed parallel-field result that
        arrives while an ordinary retry or recovery probe is not due is
        observed without creating an extra retry or advancing bounded backoff.
        """

        now_epoch = _parse_epoch(now_iso)
        if now_epoch is None:
            return self._result(
                mint, self._mints.get(mint), MARKET_INVALID,
                "MARKET_CLOCK_INVALID", now_iso, attempts=[], next_epoch=None)
        state = self._mints.get(mint)
        if state is None:
            first_epoch = _parse_epoch(migration_time_utc) or now_epoch
            state = self._new_state(first_epoch)
            self._mints[mint] = state
        ready = bool(attempt.get("all_present"))
        if state.get("recovery_active"):
            probe_epoch = float(state.get("next_recovery_probe_epoch") or 0.0)
            if not ready and now_epoch < probe_epoch:
                return self._result(
                    mint, state, MARKET_RECOVERY_BACKOFF,
                    RECOVERY_BACKOFF_NOT_DUE, now_iso, attempts=[],
                    next_epoch=probe_epoch, basis=MARKET_RECOVERY_BACKOFF,
                    fetch_performed=False, fetch_due=False)
            # A fresh complete result that was already in flight is allowed to
            # recover; a due failure is one ordinary bounded recovery probe.
            state["next_recovery_probe_epoch"] = now_epoch
        else:
            next_retry = float(state.get("next_retry_epoch") or 0.0)
            if not ready and now_epoch < next_retry:
                return self._result(
                    mint, state, str(state["state"]), str(state["reason_code"]),
                    now_iso, attempts=[], next_epoch=next_retry,
                    basis="MARKET_BACKOFF", fetch_performed=False,
                    fetch_due=False)
            # The scheduler has already performed this request, so its result
            # is due by construction even if another field updated recently.
            state["next_retry_epoch"] = now_epoch
        return self.resolve(
            mint,
            migration_time_utc=migration_time_utc,
            now_iso_fn=lambda: now_iso,
            fetch_attempt_fn=lambda _attempt_at: dict(attempt),
        )

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _record_transition(
        state: Dict[str, Any], market_state: str, now_iso: str, reason_code: str
    ) -> None:
        if market_state != state.get("state"):
            transitions = state["transitions"]
            transitions.append({
                "from": state.get("state"),
                "to": market_state,
                "at_utc": now_iso,
                "reason_code": reason_code,
            })
            del transitions[:-32]
            # A readiness transition IS activity: reset the adaptive-cadence
            # heat anchor so a candidate that just came back to life is polled
            # at the fast cadence again rather than at its aged spacing.
            epoch = _parse_epoch(now_iso)
            if epoch is not None:
                state["last_activity_epoch"] = epoch

    def snapshot(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        recovering = 0
        rows = []
        for mint, state in self._mints.items():
            key = str(state.get("state") or MARKET_PENDING)
            counts[key] = counts.get(key, 0) + 1
            if state.get("recovery_active"):
                recovering += 1
            probe_epoch = state.get("next_recovery_probe_epoch")
            rows.append({
                "token_mint": mint,
                "market_state": key,
                "market_reason_code": state.get("reason_code"),
                "attempt_count": state.get("attempt_count"),
                "transient_attempt_count": state.get("transient_attempt_count"),
                "consecutive_failure_count": state.get("consecutive_failure_count"),
                "recovery_active": bool(state.get("recovery_active")),
                "recovery_attempt_count": state.get("recovery_attempt_count"),
                "recovery_backoff_seconds": state.get("recovery_backoff_seconds"),
                "grace_exhaustion_reason": state.get("grace_exhaustion_reason"),
                "next_refresh_at_utc": (
                    _iso(float(state["next_retry_epoch"]))
                    if state.get("next_retry_epoch") is not None else None
                ),
                "next_recovery_probe_at_utc": (
                    _iso(float(probe_epoch)) if probe_epoch is not None else None
                ),
                "last_attempt_at_utc": state.get("last_attempt_at_utc"),
                "last_success_at_utc": state.get("last_success_at_utc"),
                "last_failure_at_utc": state.get("last_failure_at_utc"),
                "recovered_at_utc": state.get("recovered_at_utc"),
                "first_ready_at_utc": state.get("first_ready_at_utc"),
                "legacy_terminal_migrated": bool(state.get("legacy_terminal_migrated")),
                "transitions": list(state.get("transitions") or ()),
            })
        counters = dict(self._counters)
        counters["market_candidates_currently_recovering"] = recovering
        return {
            "tracked": len(rows),
            "by_state": counts,
            "counters": counters,
            "per_mint": rows[:128],
        }

    @staticmethod
    def _classify(attempt: Mapping[str, Any]) -> Tuple[str, str]:
        provider_state = str(attempt.get("provider_market_state") or "")
        provider_reason = str(attempt.get("provider_reason_code") or "")
        if provider_state in (MARKET_INVALID, MARKET_STALE):
            return provider_state, provider_reason or provider_state
        if bool(attempt.get("all_present")):
            return MARKET_READY, "REQUIRED_FIELDS_FRESH"
        if provider_state in (MARKET_INDEXING, MARKET_INCOMPLETE):
            return provider_state, provider_reason or provider_state
        present = sum(
            attempt.get(key) is not None for key in ("price_value", "mc_value", "lp_value")
        )
        if present:
            missing = []
            if attempt.get("price_value") is None:
                missing.append("PRICE")
            if attempt.get("mc_value") is None:
                missing.append("MARKET_CAP")
            if attempt.get("lp_value") is None:
                missing.append("LIQUIDITY")
            return MARKET_INCOMPLETE, "MISSING_" + "_".join(missing)
        return MARKET_INDEXING, provider_reason or "PROVIDER_NOT_INDEXED"

    def _retry_delay(self, state: Mapping[str, Any], market_state: str) -> float:
        base = self._base_retry_delay(state, market_state)
        return self._adapt_delay(state, market_state, base)

    def _base_retry_delay(
        self, state: Mapping[str, Any], market_state: str
    ) -> float:
        if market_state in _TRANSIENT:
            index = max(0, int(state.get("transient_attempt_count") or 1) - 1)
            return float(self.config.retry_backoff_seconds[
                min(index, len(self.config.retry_backoff_seconds) - 1)
            ])
        if market_state == MARKET_READY:
            return self.config.ready_refresh_seconds
        if market_state == MARKET_STALE:
            return self.config.stale_refresh_seconds
        if market_state == MARKET_INVALID:
            return self.config.invalid_refresh_seconds
        return self.config.ready_refresh_seconds

    def _adapt_delay(
        self, state: Mapping[str, Any], market_state: str, base: float
    ) -> float:
        """Heat-aware spacing for the extended PHX1_PARITY watch.

        A six-hour watch polled at the flat READY cadence would multiply
        per-candidate provider volume sixfold.  Under PHX1_PARITY a candidate
        that has gone quiet steps down a bounded ladder while a hot or
        recently-active one keeps the committed cadence; any renewed activity
        (a state change, or a successful observation) resets the heat anchor,
        so a reactivated candidate is back at full speed on its next turn.

        LEGACY is untouched: the base delay is returned verbatim.
        """

        active_policy = current_alert_policy()
        if not is_phx1_parity(active_policy):
            return base
        # A candidate that is not yet READY is still being established; its own
        # transient/recovery schedules already bound it, so never slow those.
        if market_state != MARKET_READY:
            return base
        anchor = state.get("last_activity_epoch")
        last_attempt = _parse_epoch(state.get("last_attempt_at_utc"))
        if anchor is None or last_attempt is None:
            return base
        return adaptive_refresh_interval_seconds(
            base_interval_seconds=base,
            seconds_since_activity=max(0.0, last_attempt - float(anchor)),
            is_active_dip=bool(state.get("is_active_dip")),
            policy=active_policy,
        )

    def note_candidate_activity(
        self, mint: str, *, now_iso: str, is_active_dip: bool = False
    ) -> None:
        """Reset a candidate's heat anchor.

        Called by the watch loop whenever a candidate shows renewed life -- an
        activation transition, a tier change, or entering an active dip -- so
        the adaptive cadence returns it to the fast lane immediately.  A mint
        this tracker has never seen is ignored; nothing is created here.
        """

        state = self._mints.get(mint)
        if state is None:
            return
        epoch = _parse_epoch(now_iso)
        if epoch is not None:
            state["last_activity_epoch"] = epoch
        state["is_active_dip"] = bool(is_active_dip)

    @staticmethod
    def _result(
        mint: str,
        state: Optional[Mapping[str, Any]],
        market_state: str,
        reason_code: str,
        now_iso: str,
        *,
        attempts: list,
        next_epoch: Optional[float],
        attempt: Optional[Mapping[str, Any]] = None,
        basis: Optional[str] = None,
        fetch_performed: bool = False,
        fetch_due: bool = False,
    ) -> Dict[str, Any]:
        selected = dict(attempt or {})
        ready = market_state == MARKET_READY and bool(selected.get("all_present"))
        st: Mapping[str, Any] = state or {}
        probe_epoch = st.get("next_recovery_probe_epoch")
        return {
            # Preserve partial field presence for diagnostics/risk observation.  The
            # separate all_present flag remains the only compose/send admission seam.
            "current_price": selected.get("price_value"),
            "current_market_cap_usd": selected.get("mc_value"),
            "liquidity_usd": selected.get("lp_value"),
            "market_context_fetched_at_utc": (
                selected.get("provider_timestamp_utc")
                or selected.get("attempt_at_utc")
                or now_iso
            ),
            "provider_timestamp_utc": selected.get("provider_timestamp_utc"),
            "all_present": ready,
            "basis": basis or selected.get("basis") or market_state,
            "attempts": attempts,
            "market_state": market_state,
            "market_reason_code": reason_code,
            "next_market_refresh_at_utc": (
                _iso(next_epoch) if next_epoch is not None else None
            ),
            "market_attempt_count": int(st.get("attempt_count") or 0),
            "market_state_transitions": list(st.get("transitions") or ()),
            "endpoint_attempts": selected.get("endpoint_attempts") or {},
            # 2026-07-28 liquidity remediation: preserve the selected attempt's
            # exact-pair reserve telemetry; dropping it here forced the
            # delivery layer's actual-LP verification to fail closed for every
            # candidate resolved through the readiness tracker.
            "pumpswap_reserve": selected.get("pumpswap_reserve") or {},
            # --- PHX2-E2E-004 observability (redaction-safe: tokens/ints/ISO) ---
            "market_readiness_state": market_state,
            "market_readiness_reason": reason_code,
            "market_normal_attempt_count": int(st.get("transient_attempt_count") or 0),
            "market_consecutive_failure_count": int(
                st.get("consecutive_failure_count") or 0),
            "market_recovery_attempt_count": int(st.get("recovery_attempt_count") or 0),
            "market_recovery_backoff_seconds": float(
                st.get("recovery_backoff_seconds") or 0.0),
            "market_next_recovery_probe_at_utc": (
                _iso(float(probe_epoch)) if probe_epoch is not None else None),
            "market_last_attempt_at_utc": st.get("last_attempt_at_utc"),
            "market_last_success_at_utc": st.get("last_success_at_utc"),
            "market_last_failure_at_utc": st.get("last_failure_at_utc"),
            "market_recovered_at_utc": st.get("recovered_at_utc"),
            "market_provider_fetch_due": bool(fetch_due),
            "market_provider_fetch_performed": bool(fetch_performed),
            "market_grace_exhaustion_reason": st.get("grace_exhaustion_reason"),
            "market_legacy_terminal_migrated": bool(
                st.get("legacy_terminal_migrated")),
        }


__all__ = (
    "MARKET_PENDING", "MARKET_READY", "MARKET_INDEXING", "MARKET_INCOMPLETE",
    "MARKET_STALE", "MARKET_INVALID", "MARKET_RECOVERY_BACKOFF", "MARKET_UNAVAILABLE",
    "GRACE_EXHAUSTION_ATTEMPTS", "GRACE_EXHAUSTION_TIME", "GRACE_EXHAUSTION_BOTH",
    "RECOVERY_BACKOFF_NOT_DUE", "RECOVERY_PROBE_ATTEMPTED", "RECOVERY_PROBE_FAILED",
    "RECOVERY_SUCCEEDED", "LEGACY_TERMINAL_MIGRATED", "LEGACY_TERMINAL_UNCLASSIFIED",
    "classify_legacy_market_state",
    "PaidMarketReadinessConfig", "PaidMarketReadinessTracker",
)
