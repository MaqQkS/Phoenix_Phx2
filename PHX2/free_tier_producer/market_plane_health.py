"""Bounded-grace fail-closed detection for a blind market plane.

The 2026-08-02 five-hour run is the specification for this module.  Twenty-two
minutes in, the market-request budget was exhausted; from then on no market job
could be enqueued, 15,523 priority refreshes were rejected, 15,419 of 15,770
parity evaluations ended ``NO_SEND_MARKET_INCOMPLETE`` and no candidate ever
reached delivery.  The producer reported itself alive for the remaining four
and a half hours, because the PID was up and the Helius socket was connected.

A market plane that cannot answer is not a degraded producer, it is a producer
that cannot do its job.  This module makes that a bounded, explicit condition:

* a short outage is ``DEGRADED`` and must NOT kill production -- providers
  throttle, caches miss, a single tick can legitimately serve nothing;
* the same condition sustained past :data:`DEFAULT_GRACE_SECONDS` is
  ``BLIND``, which is explicitly unhealthy and fails closed;
* no active candidates means no market work is DUE, which is idle, not blind
  -- a quiet watchlist must never trip this.

The fail-closed action is the architecture's existing one: a cooperative
``request_stop`` that ends the run at a tick boundary with a named reason.
Nothing here opens a circuit directly.  If the condition is genuinely
persistent the watchdog's existing restart circuit (``circuit_max_restarts``)
opens on its own after the bounded restart budget, which is the canonical
operator path -- and no evidence is erased on the way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# -- statuses (closed set) --------------------------------------------------
MARKET_PLANE_HEALTHY = "MARKET_PLANE_HEALTHY"
#: A blind condition is currently true but has not yet outlived its grace.
MARKET_PLANE_DEGRADED = "MARKET_PLANE_DEGRADED"
#: Sustained beyond grace. Explicitly unhealthy; fails closed.
MARKET_PLANE_BLIND = "MARKET_PLANE_BLIND"
#: No active candidates: no market work is due, so silence proves nothing.
MARKET_PLANE_IDLE = "MARKET_PLANE_IDLE"

MARKET_PLANE_STATUSES = (
    MARKET_PLANE_HEALTHY, MARKET_PLANE_DEGRADED,
    MARKET_PLANE_BLIND, MARKET_PLANE_IDLE,
)

# -- blind reasons (closed set) --------------------------------------------
REASON_BUDGET_EXHAUSTED = "MARKET_PROVIDER_BUDGET_EXHAUSTED"
REASON_STARVED_BEYOND_BOUND = "MARKET_OBSERVATION_STARVED_BEYOND_BOUND"
REASON_NO_SUCCESSFUL_REFRESH = "MARKET_REFRESH_ABSENT_BEYOND_BOUND"
REASON_PRIORITY_REFRESH_ALL_REJECTED = "MARKET_PRIORITY_REFRESH_ALL_REJECTED"
REASON_OBSERVATIONS_STALE = "MARKET_OBSERVATIONS_STALE_WITH_ACTIVE_CANDIDATES"
#: Candidates have been waiting on canonical V3 pair-ATH history beyond the
#: bounded grace while nothing completed.  This reason feeds the canonical
#: health verdict but is deliberately DEGRADED-ONLY: a V3 outage impairs ATH
#: accuracy for waiting candidates while the LIVE_TRACKER path keeps eligible
#: candidates alertable, so it must never become a producer-stopping (BLIND)
#: condition -- that would be exactly the new universal blocker the V3
#: rollout is forbidden to create.
REASON_ATH_V3_STARVED = "ATH_V3_HISTORY_STARVED_BEYOND_BOUND"

MARKET_PLANE_BLIND_REASONS = (
    REASON_BUDGET_EXHAUSTED,
    REASON_STARVED_BEYOND_BOUND,
    REASON_NO_SUCCESSFUL_REFRESH,
    REASON_PRIORITY_REFRESH_ALL_REJECTED,
    REASON_OBSERVATIONS_STALE,
)

#: Reasons that surface in the verdict but can never escalate DEGRADED to
#: BLIND (and therefore can never fail the deployment closed on their own).
MARKET_PLANE_DEGRADED_ONLY_REASONS = (
    REASON_ATH_V3_STARVED,
)

#: How long a blind condition may persist before the deployment fails closed.
#: Five minutes: long enough that a provider hiccup, a throttle window or a
#: slow tick never kills a healthy 24/7 producer, short enough that the
#: 4h38m silent outage of 2026-08-02 could not repeat.
DEFAULT_GRACE_SECONDS = 300.0

#: No successful market refresh for this long, while candidates are active, is
#: itself a blind condition -- the plane may be "working" and still answering
#: nothing.  Deliberately longer than the grace so the two bounds compose
#: rather than double-count.
DEFAULT_NO_REFRESH_BOUND_SECONDS = 600.0

#: Observations older than this, on active candidates, cannot authorize a send
#: and mean the plane is not serving the work that matters.
DEFAULT_STALE_OBSERVATION_SECONDS = 600.0

#: A priority-refresh rejection streak this long (every attempt rejected, none
#: served) is the exact shape of the failed run: 2,068 attempts, 0 successes.
DEFAULT_PRIORITY_REJECTION_STREAK = 25

#: Bounded grace before candidates waiting on V3 pair-ATH history feed the
#: canonical health verdict.  Long enough that a short 429/5xx window rides
#: the transport's bounded retry/backoff invisibly; short enough that a
#: sustained V3 outage with stuck candidates is an operator-visible
#: degradation within one status glance.
DEFAULT_ATH_V3_STARVED_BOUND_SECONDS = 900.0


@dataclass
class MarketPlaneVerdict:
    status: str
    reasons: List[str] = field(default_factory=list)
    blind_age_seconds: float = 0.0
    grace_seconds: float = DEFAULT_GRACE_SECONDS
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def blind(self) -> bool:
        return self.status == MARKET_PLANE_BLIND

    @property
    def healthy(self) -> bool:
        return self.status in (MARKET_PLANE_HEALTHY, MARKET_PLANE_IDLE)

    def to_record(self) -> Dict[str, Any]:
        return {
            "market_plane_status": self.status,
            "market_plane_reasons": list(self.reasons),
            "market_plane_blind_age_seconds": round(
                float(self.blind_age_seconds), 3),
            "market_plane_grace_seconds": float(self.grace_seconds),
            "market_plane_detail": dict(self.detail),
        }


@dataclass(frozen=True)
class MarketPlaneConfig:
    grace_seconds: float = DEFAULT_GRACE_SECONDS
    no_refresh_bound_seconds: float = DEFAULT_NO_REFRESH_BOUND_SECONDS
    stale_observation_seconds: float = DEFAULT_STALE_OBSERVATION_SECONDS
    priority_rejection_streak: int = DEFAULT_PRIORITY_REJECTION_STREAK

    def __post_init__(self) -> None:
        for name in ("grace_seconds", "no_refresh_bound_seconds",
                     "stale_observation_seconds"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) \
                    or float(value) <= 0:
                raise ValueError(f"market_plane_config_invalid:{name}")
        if not isinstance(self.priority_rejection_streak, int) \
                or isinstance(self.priority_rejection_streak, bool) \
                or self.priority_rejection_streak < 1:
            raise ValueError(
                "market_plane_config_invalid:priority_rejection_streak")


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, int(value))


class MarketPlaneWatch:
    """Deterministic bounded-grace observer over market-plane liveness.

    Pure state machine: every decision is a function of the values handed to
    :meth:`observe` plus the monotonic clock supplied by the caller.  No
    provider, no thread, no I/O -- so the transient-recovers case and the
    sustained-fails-closed case are both exactly reproducible offline.
    """

    def __init__(self, config: Optional[MarketPlaneConfig] = None) -> None:
        self.config = config or MarketPlaneConfig()
        self._blind_since: Optional[float] = None
        self._last_refresh_total = 0
        self._last_refresh_progress_at: Optional[float] = None
        self._priority_rejection_streak = 0
        # Cumulative readings, kept so the streak is built from PER-TICK
        # deltas.  Differencing the two lifetime totals instead would add the
        # whole standing gap on every single tick and trip within seconds.
        self._last_priority_attempts = 0
        self._last_priority_served = 0
        self._last_verdict = MarketPlaneVerdict(
            MARKET_PLANE_IDLE, [], 0.0, self.config.grace_seconds)

    @property
    def verdict(self) -> MarketPlaneVerdict:
        return self._last_verdict

    def observe(
        self,
        *,
        now_monotonic: float,
        active_candidates: int,
        budget_exhausted: bool = False,
        starved_age_seconds: Optional[float] = None,
        starvation_bound_seconds: Optional[float] = None,
        successful_refresh_total: int = 0,
        priority_refresh_attempts_total: int = 0,
        priority_refresh_served_total: int = 0,
        max_observation_age_seconds: Optional[float] = None,
        ath_v3_waiting_candidates: int = 0,
        ath_v3_oldest_wait_seconds: Optional[float] = None,
        ath_v3_starved_bound_seconds: float = (
            DEFAULT_ATH_V3_STARVED_BOUND_SECONDS),
    ) -> MarketPlaneVerdict:
        """Fold one tick of market-plane evidence into the running verdict."""

        now = _num(now_monotonic)
        active = _count(active_candidates)

        # Track refresh progress regardless of the active count so a plane
        # that recovers while idle does not carry a stale "no refresh" clock.
        served = _count(successful_refresh_total)
        if self._last_refresh_progress_at is None or served > self._last_refresh_total:
            self._last_refresh_total = served
            self._last_refresh_progress_at = now

        # Priority-refresh rejection streak, built from per-tick DELTAS: how
        # many attempts have been made since the last one was actually served.
        # A single rejection is normal back-pressure; an unbroken run of them
        # is the plane refusing every request, which is the exact shape of the
        # failed run (2,068 attempts, 0 successes).  Any served refresh clears
        # the streak outright.
        attempts_now = _count(priority_refresh_attempts_total)
        served_now = _count(priority_refresh_served_total)
        attempts_delta = max(0, attempts_now - self._last_priority_attempts)
        served_delta = max(0, served_now - self._last_priority_served)
        self._last_priority_attempts = attempts_now
        self._last_priority_served = served_now

        if active <= 0:
            # No candidates => no market work is DUE.  Silence here is not
            # evidence of anything, so the blind clock is released rather
            # than allowed to accumulate against a quiet watchlist.
            self._blind_since = None
            self._priority_rejection_streak = 0
            self._last_verdict = MarketPlaneVerdict(
                MARKET_PLANE_IDLE, [], 0.0, self.config.grace_seconds,
                {"active_candidates": 0})
            return self._last_verdict

        reasons: List[str] = []
        if bool(budget_exhausted):
            reasons.append(REASON_BUDGET_EXHAUSTED)

        bound = (_num(starvation_bound_seconds)
                 if starvation_bound_seconds is not None else 0.0)
        starved = _num(starved_age_seconds, -1.0)
        if bound > 0 and starved >= bound:
            reasons.append(REASON_STARVED_BEYOND_BOUND)

        since_refresh = (
            now - self._last_refresh_progress_at
            if self._last_refresh_progress_at is not None else 0.0)
        if since_refresh >= self.config.no_refresh_bound_seconds:
            reasons.append(REASON_NO_SUCCESSFUL_REFRESH)

        if served_delta > 0:
            self._priority_rejection_streak = 0
        else:
            self._priority_rejection_streak += attempts_delta
        if self._priority_rejection_streak >= self.config.priority_rejection_streak:
            reasons.append(REASON_PRIORITY_REFRESH_ALL_REJECTED)

        observation_age = _num(max_observation_age_seconds, -1.0)
        if observation_age >= self.config.stale_observation_seconds:
            reasons.append(REASON_OBSERVATIONS_STALE)

        v3_waiting = _count(ath_v3_waiting_candidates)
        v3_wait_age = _num(ath_v3_oldest_wait_seconds, -1.0)
        v3_bound = _num(ath_v3_starved_bound_seconds,
                        DEFAULT_ATH_V3_STARVED_BOUND_SECONDS)
        if v3_waiting > 0 and v3_bound > 0 and v3_wait_age >= v3_bound:
            reasons.append(REASON_ATH_V3_STARVED)

        detail: Dict[str, Any] = {
            "active_candidates": active,
            "seconds_since_successful_refresh": round(since_refresh, 3),
            "priority_refresh_rejection_streak": self._priority_rejection_streak,
            "max_observation_age_seconds": (
                round(observation_age, 3) if observation_age >= 0 else None),
            "starved_age_seconds": round(starved, 3) if starved >= 0 else None,
            "ath_v3_waiting_candidates": v3_waiting,
            "ath_v3_oldest_wait_seconds": (
                round(v3_wait_age, 3) if v3_wait_age >= 0 else None),
        }

        if not reasons:
            self._blind_since = None
            self._last_verdict = MarketPlaneVerdict(
                MARKET_PLANE_HEALTHY, [], 0.0, self.config.grace_seconds, detail)
            return self._last_verdict

        # The blind clock runs only while an ESCALATABLE reason is present:
        # a degraded-only condition (V3 starvation) surfaces immediately in
        # the verdict but can never accumulate toward a fail-closed stop.
        escalatable = [reason for reason in reasons
                       if reason not in MARKET_PLANE_DEGRADED_ONLY_REASONS]
        if escalatable:
            if self._blind_since is None:
                self._blind_since = now
            age = max(0.0, now - self._blind_since)
            status = (MARKET_PLANE_BLIND if age >= self.config.grace_seconds
                      else MARKET_PLANE_DEGRADED)
        else:
            self._blind_since = None
            age = 0.0
            status = MARKET_PLANE_DEGRADED
        self._last_verdict = MarketPlaneVerdict(
            status, sorted(set(reasons)), age, self.config.grace_seconds, detail)
        return self._last_verdict

    def snapshot(self) -> Dict[str, Any]:
        return self._last_verdict.to_record()


def classify(verdict: MarketPlaneVerdict) -> Tuple[bool, str]:
    """(should_fail_closed, reason) for the canonical cooperative stop."""

    if verdict.blind:
        return True, (verdict.reasons[0] if verdict.reasons
                      else REASON_STARVED_BEYOND_BOUND)
    return False, ""


__all__ = (
    "MARKET_PLANE_HEALTHY", "MARKET_PLANE_DEGRADED", "MARKET_PLANE_BLIND",
    "MARKET_PLANE_IDLE", "MARKET_PLANE_STATUSES",
    "REASON_BUDGET_EXHAUSTED", "REASON_STARVED_BEYOND_BOUND",
    "REASON_NO_SUCCESSFUL_REFRESH",
    "REASON_PRIORITY_REFRESH_ALL_REJECTED", "REASON_OBSERVATIONS_STALE",
    "REASON_ATH_V3_STARVED",
    "MARKET_PLANE_BLIND_REASONS", "MARKET_PLANE_DEGRADED_ONLY_REASONS",
    "DEFAULT_GRACE_SECONDS", "DEFAULT_NO_REFRESH_BOUND_SECONDS",
    "DEFAULT_STALE_OBSERVATION_SECONDS", "DEFAULT_PRIORITY_REJECTION_STREAK",
    "DEFAULT_ATH_V3_STARVED_BOUND_SECONDS",
    "MarketPlaneConfig", "MarketPlaneVerdict", "MarketPlaneWatch",
    "classify",
)
