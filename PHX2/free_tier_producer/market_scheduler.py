"""Deadline-aware, source-aware market observation scheduler.

The production runtime has one authoritative observation owner and a bounded
set of provider workers.  Provider work is split into two independent planes:

* ``PRICE_MC`` -- current price / current market-cap observations.
* ``OVERVIEW`` -- liquidity and overview enrichment.

The scheduler never treats concurrency as authorization.  Every result is
mint/candidate/generation bound, sequence ordered, independently timestamped,
and applied by the single result-owner thread.  The final compose/send path
continues to enforce its existing activation, Fee Gate, risk, liquidity, and
delivery contracts.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import queue
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.market_budget import (
    MARKET_REQUEST_CAP_UNBOUNDED,
    ORIGIN_PRIORITY_REFRESH_OVERVIEW,
    ORIGIN_PRIORITY_REFRESH_PRICE,
    ORIGIN_SCHEDULED_OVERVIEW,
    ORIGIN_SCHEDULED_PRICE,
    MarketPhysicalRequestMeter,
    market_budget_status,
    reconcile as reconcile_physical_requests,
)


FIELD_PRICE_MC = "PRICE_MC"
FIELD_OVERVIEW = "OVERVIEW"
FIELD_QUOTE_PRICE = "QUOTE_PRICE"

SOURCE_GRPC = "TRUSTED_PUMPSWAP_GRPC"
SOURCE_PAID_BATCH = "PAID_PRIMARY_BATCH"
SOURCE_PAID_SINGLE = "PAID_PRIMARY_SINGLE"
SOURCE_AUTHENTICATED_RESERVE_FALLBACK = (
    "HELIUS_AUTHENTICATED_PUMPSWAP_ACCOUNTS")

PRIORITY_P0 = 0
PRIORITY_P1 = 1
PRIORITY_P2 = 2
PRIORITY_P3 = 3

PRIORITY_NAMES = {
    PRIORITY_P0: "P0_IMMEDIATE",
    PRIORITY_P1: "P1_ACTIVATED",
    PRIORITY_P2: "P2_NEAR_ACTIVATION",
    PRIORITY_P3: "P3_BACKGROUND",
}

MARKET_SCHEDULER_BACKLOG_HIGH = "MARKET_SCHEDULER_BACKLOG_HIGH"
MARKET_LATENCY_SLO_BREACHED = "MARKET_LATENCY_SLO_BREACHED"
MARKET_PROVIDER_BUDGET_EXHAUSTED = "MARKET_PROVIDER_BUDGET_EXHAUSTED"
MARKET_BATCH_PARTIAL = "MARKET_BATCH_PARTIAL"
MARKET_OBSERVATION_STARVED = "MARKET_OBSERVATION_STARVED"
MARKET_SCHEDULER_OVERLOADED = "MARKET_SCHEDULER_OVERLOADED"
LATENCY_SLO_UNACHIEVABLE = "LATENCY_SLO_UNACHIEVABLE"

# ---- PHX2-E2E-006 P1 service contract tokens (closed set) -----------------

P1_CAPACITY_UNACHIEVABLE = "P1_CAPACITY_UNACHIEVABLE"
P1_DEADLINE_MISSED = "P1_DEADLINE_MISSED"

#: How long one degraded OBSERVATION keeps describing the present.  A reason
#: not re-observed within this window ages out of the reported set, so a
#: scheduler that recovers reports SCHEDULER_READY again instead of carrying a
#: single early breach for the rest of the process lifetime.
DEGRADED_REASON_TTL_SECONDS = 300.0

#: Closed-set outcomes of applying one observation to the stored market state.
#: ``UNCHANGED`` is a SUCCESSFUL provider answer that simply is not newer; it is
#: never a fault and never a malformed response.
APPLY_OUTCOME_APPLIED = "APPLIED"
APPLY_OUTCOME_UNCHANGED = "UNCHANGED"
APPLY_OUTCOME_MALFORMED = "MALFORMED"
APPLY_OUTCOMES = (
    APPLY_OUTCOME_APPLIED, APPLY_OUTCOME_UNCHANGED, APPLY_OUTCOME_MALFORMED)

SCHEDULER_READY = "SCHEDULER_READY"
SCHEDULER_DEGRADED = "SCHEDULER_DEGRADED"
SCHEDULER_CAPACITY_REFUSED = "SCHEDULER_CAPACITY_REFUSED"
SCHEDULER_SHUTTING_DOWN = "SCHEDULER_SHUTTING_DOWN"
SCHEDULER_STOPPED = "SCHEDULER_STOPPED"

P1_RESULT_DISPATCH_EVALUATED = "P1_RESULT_DISPATCH_EVALUATED"
P1_RESULT_TEMP_BLOCKED = "P1_RESULT_TEMP_BLOCKED"
P1_RESULT_PERM_BLOCKED = "P1_RESULT_PERM_BLOCKED"
P1_RESULT_PROVIDER_FAILURE = "P1_RESULT_PROVIDER_FAILURE"
P1_RESULT_DEADLINE_MISSED = "P1_RESULT_DEADLINE_MISSED"
P1_RESULT_SEND_COOLDOWN = "P1_RESULT_SEND_COOLDOWN"

P1_RESULT_TOKENS = frozenset({
    P1_RESULT_DISPATCH_EVALUATED,
    P1_RESULT_TEMP_BLOCKED,
    P1_RESULT_PERM_BLOCKED,
    P1_RESULT_PROVIDER_FAILURE,
    P1_RESULT_DEADLINE_MISSED,
    P1_RESULT_SEND_COOLDOWN,
})

P1_TIERS = ("Tier 1", "Tier 2", "Tier 3")

# Engine per-candidate reasons that prove the dispatch path itself was
# reached (compose/guarded-delivery evaluation happened).  Everything else
# non-empty is a temporary block unless listed permanent.
_P1_DISPATCH_REASONS = frozenset({
    "SENT_OK_COMMITTED", "SEND_ATTEMPTED", "COMPOSED_NO_TRANSPORT",
    "DELIVERY_FAILED_RETRYABLE", "DELIVERY_UNKNOWN", "DELIVERY_RETRY_BACKOFF",
    "NO_SEND_NOT_DISPATCHABLE",
})
_P1_PERMANENT_REASONS = frozenset({
    "NOT_PUMP_SUFFIX",
})
_P1_PROVIDER_REASON_PREFIXES = ("PROVIDER_", "NO_SEND_MARKET_UNAVAILABLE")


def classify_engine_reason_to_p1_outcome(reason: object) -> Optional[str]:
    """Project an engine per-candidate reason to the closed P1 outcome set."""

    if not isinstance(reason, str) or not reason:
        return None
    if reason in _P1_DISPATCH_REASONS:
        return P1_RESULT_DISPATCH_EVALUATED
    if reason in _P1_PERMANENT_REASONS:
        return P1_RESULT_PERM_BLOCKED
    if any(reason.startswith(prefix) for prefix in _P1_PROVIDER_REASON_PREFIXES):
        return P1_RESULT_PROVIDER_FAILURE
    return P1_RESULT_TEMP_BLOCKED

_ACTIVATED_STATES = frozenset({
    "ACTIVATED",
    "ACTIVE_DIP_WATCH",
    "ACTIVATED_WAITING_FOR_FRESH_MARKET",
})
_PENDING_STATES = frozenset({"PENDING_1_20X", "PENDING_BASELINE"})
_TERMINAL_STATES = frozenset({
    "EXPIRED",
    "DROPPED_NON_PUMP",
    "DEDUPE_SUPPRESSED",
    "SEND_ATTEMPTED",
    "SENT_OK_COMMITTED",
})


def _epoch(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number and number not in (float("inf"), float("-inf")) else None
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).timestamp()


def _iso(value: float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _positive_decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _accepts_deadline_kwarg(fetch_fn: object) -> bool:
    """True when a fetch callable takes a ``deadline_monotonic`` keyword."""

    if fetch_fn is None:
        return False
    try:
        import inspect
        parameters = inspect.signature(fetch_fn).parameters
    except (TypeError, ValueError):
        return False
    if "deadline_monotonic" in parameters:
        return True
    return any(parameter.kind == parameter.VAR_KEYWORD
               for parameter in parameters.values())


def candidate_generation(candidate_id: object, seeded_at_utc: object,
                         persisted_generation: object = 0) -> int:
    """Return a deterministic positive generation with an explicit restart bump."""

    try:
        persisted = int(persisted_generation)
    except (TypeError, ValueError):
        persisted = 0
    if persisted > 0:
        return persisted
    seed = f"{candidate_id}|{seeded_at_utc}".encode("utf-8")
    # Never use Python's randomized hash for a cross-process binding.
    return max(1, int.from_bytes(hashlib.sha256(seed).digest()[:8], "big"))


# ---- MarketSchedulerConfig legacy schema (closed set) ---------------------
# Every field named here must be a finite real numeric strictly greater than
# zero, and ``backlog_high_fraction`` must sit inside (0, 1].  bool and
# non-numeric shapes refuse: a misconfigured operator flag fails closed at
# construction, before any provider, scheduler worker, socket or ledger
# object can exist — it never degrades scheduling silently.

TTL_SLO_CONFIG_FIELDS: Tuple[str, ...] = (
    "price_active_ttl_seconds",
    "price_pending_ttl_seconds",
    "overview_active_ttl_seconds",
    "overview_pending_ttl_seconds",
    "grpc_max_age_seconds",
    "grpc_watch_apply_slo_seconds",
    "grpc_decision_slo_seconds",
    "activated_overview_schedule_slo_seconds",
    "recovery_schedule_slo_seconds",
    "pending_price_max_age_seconds",
    "background_starvation_seconds",
    "heartbeat_jitter_slo_seconds",
)

#: Adaptive refresh intervals.  Same schema contract as the TTL fields
#: (finite real > 0); validated separately so a refusal names the exact
#: cadence field rather than a legacy TTL.
CADENCE_CONFIG_FIELDS: Tuple[str, ...] = (
    "price_tier_active_refresh_seconds",
    "overview_tier_active_refresh_seconds",
    "price_near_tier_refresh_seconds",
    "overview_near_tier_refresh_seconds",
    "price_far_refresh_seconds",
    "overview_far_refresh_seconds",
    "price_inactive_refresh_seconds",
    "overview_inactive_refresh_seconds",
)

#: Closed set of adaptive cadence classes.  ``TIER_ACTIVE`` means the
#: candidate is currently inside (or within the near-tier margin of) a
#: closed Tier 1/2/3 band and is therefore one market refresh away from a
#: real dispatch decision.
CADENCE_TIER_ACTIVE = "CADENCE_TIER_ACTIVE"
CADENCE_NEAR_TIER = "CADENCE_NEAR_TIER"
CADENCE_FAR = "CADENCE_FAR"
CADENCE_INACTIVE = "CADENCE_INACTIVE"
CADENCE_CLASSES: Tuple[str, ...] = (
    CADENCE_TIER_ACTIVE, CADENCE_NEAR_TIER, CADENCE_FAR, CADENCE_INACTIVE,
)

# ---- send-time priority refresh (closed result set) --------------------
ACCEPTED_FRESH_OBSERVATION = "ACCEPTED_FRESH_OBSERVATION"
STALE_PROVIDER_TIMESTAMP = "STALE_PROVIDER_TIMESTAMP"
PROVIDER_ERROR = "PROVIDER_ERROR"
BACKOFF_ACTIVE = "BACKOFF_ACTIVE"
ALREADY_IN_FLIGHT = "ALREADY_IN_FLIGHT"
MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
WRONG_MINT = "WRONG_MINT"
OTHER_NAMED_RESULT = "OTHER_NAMED_RESULT"
PRIORITY_REFRESH_RESULTS: Tuple[str, ...] = (
    ACCEPTED_FRESH_OBSERVATION,
    STALE_PROVIDER_TIMESTAMP,
    PROVIDER_ERROR,
    BACKOFF_ACTIVE,
    ALREADY_IN_FLIGHT,
    MISSING_REQUIRED_FIELDS,
    WRONG_MINT,
    OTHER_NAMED_RESULT,
)
# Compatibility aliases retain the import surface while intentionally changing
# the emitted values from generic buckets to the exact closed result above.
REFRESH_SUCCEEDED = ACCEPTED_FRESH_OBSERVATION
REFRESH_RETRYABLE_FAILURE = MISSING_REQUIRED_FIELDS
REFRESH_PERMANENT_FAILURE = OTHER_NAMED_RESULT
REFRESH_RATE_LIMITED = BACKOFF_ACTIVE
REFRESH_ALREADY_IN_FLIGHT = ALREADY_IN_FLIGHT
#: Provider-scoped spacing between two priority refreshes of the SAME mint.
PRIORITY_REFRESH_MIN_SPACING_SECONDS = 2.0
#: Bounded escalating backoff after a rate-limited/failed priority refresh.
PRIORITY_REFRESH_BACKOFF_BASE_SECONDS = 5.0
PRIORITY_REFRESH_BACKOFF_MAX_SECONDS = 120.0
#: A mint that has failed permanently this many times stops being retried
#: within the process lifetime of this scheduler (never an infinite loop).
PRIORITY_REFRESH_MAX_PERMANENT_FAILURES = 3


_RATE_LIMIT_TOKENS = ("429", "TOOMANYREQUESTS", "RATELIMIT", "RATE_LIMIT",
                      "THROTTLE", "QUOTA")


def _looks_rate_limited(exc: BaseException) -> bool:
    """Provider-scoped rate limiting, classified from the exception only.

    Never inspects a URL, header or key: only the exception type name and
    its string form, both of which the redaction scanner already covers.
    """

    probe = f"{type(exc).__name__} {exc}".upper()
    return any(token in probe for token in _RATE_LIMIT_TOKENS)


def _finite_real_number(value: object) -> bool:
    """True only for a bool-free int/float holding a finite value."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


@dataclass(frozen=True)
class MarketSchedulerConfig:
    worker_count: int = 2
    max_inflight: int = 2
    max_queue_size: int = 256
    #: Lifetime ceiling on PHYSICAL provider requests.  ``0`` is the explicit
    #: :data:`MARKET_REQUEST_CAP_UNBOUNDED` sentinel required by RUN_FOREVER;
    #: any positive value is a bounded lifetime cap for tests and one-shot runs.
    provider_request_budget: int = 200000
    provider_min_interval_seconds: float = 1.05
    paid_batch_size: int = 0
    price_active_ttl_seconds: float = 12.0
    price_pending_ttl_seconds: float = 30.0
    overview_active_ttl_seconds: float = 30.0
    overview_pending_ttl_seconds: float = 90.0
    grpc_max_age_seconds: float = 15.0
    grpc_watch_apply_slo_seconds: float = 2.0
    grpc_decision_slo_seconds: float = 5.0
    activated_overview_schedule_slo_seconds: float = 15.0
    recovery_schedule_slo_seconds: float = 15.0
    pending_price_max_age_seconds: float = 30.0
    background_starvation_seconds: float = 120.0
    heartbeat_jitter_slo_seconds: float = 5.0
    backlog_high_fraction: float = 0.75
    near_activation_margin_pct: Decimal = Decimal("10")
    near_tier_margin_pct: Decimal = Decimal("3")
    # ---- 2026-08-02 adaptive refresh cadence ---------------------------
    # The TTL fields above are the HARD freshness contract: a value older
    # than its TTL is stale and can never authorize a send.  They are not,
    # by themselves, a refresh schedule -- before this block the scheduler
    # only re-planned a field once it had ALREADY expired, so the very best
    # achievable state was "fresh for an instant, then stale until the next
    # sweep".  In the 2026-08-02 PHX1_PARITY run the effective per-candidate
    # sweep was ~46 s against a 12 s price TTL: ~12 s dispatchable and ~38 s
    # guaranteed stale per cycle, which is why 1,576 candidate ticks ended
    # MARKET_INCOMPLETE and zero tiers were ever composed.
    #
    # The refresh INTERVAL is therefore a separate, state-dependent value,
    # and the invariant every tier-relevant class must satisfy is:
    #
    #     refresh_interval <= hard_TTL * cadence_headroom_fraction
    #
    # with the fraction at or below one half, so a refreshed field is at
    # most half its TTL old when the next refresh lands.  Candidates far
    # from any tier deliberately move to a SLOWER cadence than the legacy
    # TTL: that is what pays for the faster tier-active cadence inside the
    # same provider budget.
    cadence_headroom_fraction: Decimal = Decimal("0.5")
    price_tier_active_refresh_seconds: float = 5.0
    overview_tier_active_refresh_seconds: float = 12.0
    price_near_tier_refresh_seconds: float = 6.0
    overview_near_tier_refresh_seconds: float = 15.0
    price_far_refresh_seconds: float = 45.0
    overview_far_refresh_seconds: float = 120.0
    price_inactive_refresh_seconds: float = 90.0
    overview_inactive_refresh_seconds: float = 240.0
    #: Maximum spacing between two ``plan()`` sweeps driven by the
    #: scheduler's own planner thread.  ``plan()`` used to be called only
    #: once per producer watch tick, so no TTL shorter than the tick could
    #: ever be honoured.  0 disables the internal planner (the legacy
    #: caller-driven behaviour every existing unit test relies on).
    planner_interval_seconds: float = 0.0
    # ---- PHX2-E2E-006 P1 service contract ------------------------------
    # The class defaults preserve the legacy conservative shape (2 workers,
    # 1.05 s spacing) so a default-constructed config is REFUSED by
    # ``evaluate_p1_capacity`` for the 128-candidate production objective.
    # The production session builds its config through
    # ``free_tier_session.build_production_market_scheduler_config``, which
    # supplies values that pass the same formula it is refused by here.
    p1_deadline_seconds: float = 15.0
    max_active_candidates: int = 128
    healthy_response_budget_seconds: float = 1.5
    dispatch_overhead_budget_seconds: float = 0.5
    p1_max_attempts: int = 2
    p1_request_timeout_seconds: float = 8.0
    p1_reserved_workers: int = 0

    def __post_init__(self) -> None:
        if not (1 <= int(self.worker_count) <= 16):
            raise ValueError("market_scheduler_worker_count_invalid")
        if not (1 <= int(self.max_inflight) <= int(self.worker_count)):
            raise ValueError("market_scheduler_max_inflight_invalid")
        if not (1 <= int(self.max_queue_size) <= 4096):
            raise ValueError("market_scheduler_queue_size_invalid")
        if int(self.provider_request_budget) < MARKET_REQUEST_CAP_UNBOUNDED:
            raise ValueError("market_scheduler_provider_budget_invalid")
        if int(self.paid_batch_size) < 0 or int(self.paid_batch_size) > 500:
            raise ValueError("market_scheduler_batch_size_invalid")
        if not (0.0 < float(self.p1_deadline_seconds) <= 3600.0):
            raise ValueError("market_scheduler_p1_deadline_invalid")
        if not (1 <= int(self.max_active_candidates) <= 4096):
            raise ValueError("market_scheduler_active_cap_invalid")
        if float(self.healthy_response_budget_seconds) <= 0:
            raise ValueError("market_scheduler_response_budget_invalid")
        if float(self.dispatch_overhead_budget_seconds) <= 0:
            raise ValueError("market_scheduler_overhead_budget_invalid")
        if not (1 <= int(self.p1_max_attempts) <= 5):
            raise ValueError("market_scheduler_p1_attempts_invalid")
        if float(self.p1_request_timeout_seconds) <= 0:
            raise ValueError("market_scheduler_p1_timeout_invalid")
        if not (0 <= int(self.p1_reserved_workers)
                <= max(0, int(self.worker_count) - 1)):
            raise ValueError("market_scheduler_p1_reserved_workers_invalid")
        if float(self.provider_min_interval_seconds) < 0:
            raise ValueError("market_scheduler_min_interval_invalid")
        # Legacy TTL/SLO schema contract: finite real numerics > 0 only, and
        # backlog_high_fraction inside (0, 1].  The token prefix is stable;
        # the suffix names the exact refusing field.
        for field_name in TTL_SLO_CONFIG_FIELDS:
            value = getattr(self, field_name)
            if not _finite_real_number(value) or float(value) <= 0:
                raise ValueError(
                    f"market_scheduler_ttl_invalid:{field_name}")
        for field_name in CADENCE_CONFIG_FIELDS:
            value = getattr(self, field_name)
            if not _finite_real_number(value) or float(value) <= 0:
                raise ValueError(
                    f"market_scheduler_cadence_invalid:{field_name}")
        headroom = self.cadence_headroom_fraction
        try:
            headroom_value = Decimal(str(headroom))
        except (InvalidOperation, ValueError):
            raise ValueError(
                "market_scheduler_cadence_headroom_invalid") from None
        if not headroom_value.is_finite() or not (
                Decimal(0) < headroom_value <= Decimal("0.5")):
            raise ValueError("market_scheduler_cadence_headroom_invalid")
        # The cadence/TTL relationship is enforced by CLAMPING at use time
        # (``_refresh_intervals``), not by refusing at construction.  A
        # construction-time refusal would make any config with a very small
        # TTL unconstructible even though the clamp handles it correctly --
        # and an unsatisfiable structural gate is precisely the failure mode
        # this remediation exists to remove.  ``tier_cadence_ceilings``
        # exposes the derived bound so the invariant stays test-pinnable.
        if not _finite_real_number(self.planner_interval_seconds) \
                or float(self.planner_interval_seconds) < 0:
            raise ValueError("market_scheduler_planner_interval_invalid")
        fraction = self.backlog_high_fraction
        if (not _finite_real_number(fraction)
                or not (0 < float(fraction) <= 1)):
            raise ValueError("market_scheduler_backlog_fraction_invalid")

    @property
    def provider_budget_unbounded(self) -> bool:
        """True iff this scheduler has NO lifetime physical-request ceiling.

        Required by RUN_FOREVER.  The 2026-08-02 run carried a finite 5,000
        here and went permanently market-blind 22 minutes after launch.
        """

        return int(self.provider_request_budget) == MARKET_REQUEST_CAP_UNBOUNDED

    def tier_cadence_ceilings(self) -> Dict[str, float]:
        """The derived cadence ceiling every tier-relevant class obeys.

        ``refresh_interval <= hard_TTL * cadence_headroom_fraction``.  The
        scheduler clamps to exactly these values, so a refreshed field is at
        most half its own TTL old when the next refresh lands.
        """

        headroom = float(self.cadence_headroom_fraction)
        return {
            "price_tier_active_ceiling_seconds": (
                float(self.price_active_ttl_seconds) * headroom),
            "price_near_tier_ceiling_seconds": (
                float(self.price_active_ttl_seconds) * headroom),
            "overview_tier_active_ceiling_seconds": (
                float(self.overview_active_ttl_seconds) * headroom),
            "overview_near_tier_ceiling_seconds": (
                float(self.overview_active_ttl_seconds) * headroom),
        }

    def effective_p1_attempt_timeout_seconds(self) -> float:
        """The ONE centralized clamp: no P1 attempt may outlive the deadline."""

        ceiling = max(0.05, float(self.p1_deadline_seconds)
                      - float(self.dispatch_overhead_budget_seconds))
        return min(float(self.p1_request_timeout_seconds), ceiling)


def production_p1_scheduler_fields() -> Dict[str, Any]:
    """The one production P1 scheduling shape (PHX2-E2E-006).

    16 bounded workers, 16 max in-flight, request-START spacing 0.09 s
    (~11.1 requests/second — the spacing the operator's paid plan must be
    provisioned for; the credit-budget 429 tripwire stops the run
    observably if the plan disagrees), a 1.5 s healthy-response budget,
    and a 0.5 s scheduler dispatch-overhead budget.  Exact worst-case
    completion for 128 candidates under ``evaluate_p1_capacity``:
    13.85 s <= 15.000 s.
    """

    return {
        "worker_count": 16,
        "max_inflight": 16,
        "provider_min_interval_seconds": 0.09,
        "p1_deadline_seconds": 15.0,
        "healthy_response_budget_seconds": 1.5,
        "dispatch_overhead_budget_seconds": 0.5,
        "p1_max_attempts": 2,
        "p1_request_timeout_seconds": 8.0,
        "p1_reserved_workers": 2,
    }


def project_request_budget(
    config: "MarketSchedulerConfig", *,
    tier_active: int = 0, near_tier: int = 0, far: int = 0,
    inactive: int = 0, horizon_seconds: float = 3600.0,
) -> Dict[str, Any]:
    """Pure steady-state provider demand for one adaptive cadence mix.

    Each candidate contributes ``1/price_interval + 1/overview_interval``
    requests per second in its class.  The result is compared against BOTH
    bounds the runtime actually has: the request-START spacing ceiling
    (``1 / provider_min_interval_seconds``) and the absolute
    ``provider_request_budget`` over the horizon.

    Deliberately arithmetic and provider-free: a fast fake-provider
    benchmark can never substitute for this projection, exactly as with
    ``evaluate_p1_capacity``.
    """

    classes = (
        (CADENCE_TIER_ACTIVE, int(max(0, tier_active)),
         config.price_tier_active_refresh_seconds,
         config.overview_tier_active_refresh_seconds),
        (CADENCE_NEAR_TIER, int(max(0, near_tier)),
         config.price_near_tier_refresh_seconds,
         config.overview_near_tier_refresh_seconds),
        (CADENCE_FAR, int(max(0, far)),
         config.price_far_refresh_seconds,
         config.overview_far_refresh_seconds),
        (CADENCE_INACTIVE, int(max(0, inactive)),
         config.price_inactive_refresh_seconds,
         config.overview_inactive_refresh_seconds),
    )
    per_class: Dict[str, Any] = {}
    total_rps = 0.0
    for name, count, price_interval, overview_interval in classes:
        rate = count * ((1.0 / float(price_interval))
                        + (1.0 / float(overview_interval)))
        per_class[name] = {
            "candidates": count,
            "price_refresh_interval_seconds": float(price_interval),
            "overview_refresh_interval_seconds": float(overview_interval),
            "requests_per_second": round(rate, 6),
        }
        total_rps += rate
    spacing = float(config.provider_min_interval_seconds)
    ceiling_rps = (1.0 / spacing) if spacing > 0 else float("inf")
    horizon = max(0.0, float(horizon_seconds))
    projected = total_rps * horizon
    return {
        "per_class": per_class,
        "total_candidates": sum(row[1] for row in classes),
        "projected_requests_per_second": round(total_rps, 6),
        "projected_requests_per_hour": round(total_rps * 3600.0, 3),
        "horizon_seconds": horizon,
        "projected_requests_in_horizon": round(projected, 3),
        "request_start_spacing_ceiling_rps": (
            round(ceiling_rps, 6) if ceiling_rps != float("inf") else None),
        "provider_request_budget": int(config.provider_request_budget),
        "within_spacing_ceiling": bool(total_rps <= ceiling_rps),
        "within_request_budget": bool(
            projected <= float(config.provider_request_budget)),
        "fits_budget": bool(
            total_rps <= ceiling_rps
            and projected <= float(config.provider_request_budget)),
    }


def evaluate_p1_capacity(config: "MarketSchedulerConfig", *,
                         active_candidates: Optional[int] = None) -> Dict[str, Any]:
    """Pure structural capacity proof for the P1 service objective.

    Deterministic worst-case schedule: ``n`` healthy overview requests,
    every request taking exactly the configured healthy-response budget,
    request STARTS paced at the configured spacing, at most the configured
    concurrency in flight.  The k-th request starts no earlier than
    ``k * spacing`` and no earlier than the completion of request
    ``k - concurrency`` (its worker frees then).  The bound is the last
    completion plus the dispatch-overhead budget.

    This is the SAME configuration object the runtime scheduler consumes;
    a fast fake-provider benchmark can never substitute for this bound.
    Batch mode is intentionally reported at size 0/1: the committed
    provider surface has no multi-token endpoint (birdeye_constants locks
    exactly three single-address paths).
    """

    n = int(config.max_active_candidates
            if active_candidates is None else active_candidates)
    n = max(0, n)
    spacing = float(config.provider_min_interval_seconds)
    concurrency = max(1, min(int(config.worker_count), int(config.max_inflight)))
    response_budget = float(config.healthy_response_budget_seconds)
    overhead = float(config.dispatch_overhead_budget_seconds)
    finish: List[float] = []
    for index in range(n):
        start = index * spacing
        if index >= concurrency:
            start = max(start, finish[index - concurrency])
        finish.append(start + response_budget)
    bound = (finish[-1] if finish else 0.0) + overhead
    achievable = bound <= float(config.p1_deadline_seconds)
    return {
        "p1_capacity_achievable": achievable,
        "refusal_reason": None if achievable else P1_CAPACITY_UNACHIEVABLE,
        "calculated_worst_case_bound_seconds": round(bound, 6),
        "configured_active_cap": n,
        "required_deadline_seconds": float(config.p1_deadline_seconds),
        "configured_concurrency": concurrency,
        "configured_worker_count": int(config.worker_count),
        "batch_size": (int(config.paid_batch_size)
                       if int(config.paid_batch_size) > 1 else 0),
        "request_start_spacing_seconds": spacing,
        "throughput_rps": (round(1.0 / spacing, 6) if spacing > 0 else None),
        "healthy_response_budget_seconds": response_budget,
        "dispatch_overhead_budget_seconds": overhead,
        "max_attempts_in_deadline": int(config.p1_max_attempts),
        "effective_p1_attempt_timeout_seconds": (
            config.effective_p1_attempt_timeout_seconds()),
    }


@dataclass(frozen=True)
class CandidateScheduleView:
    mint: str
    candidate_id: str
    generation: int
    status: str
    seeded_at_epoch: float
    market_state: Optional[str] = None
    market_reason_code: Optional[str] = None
    last_observed_epoch: Optional[float] = None
    next_recovery_epoch: Optional[float] = None
    activation_target_market_cap_usd: Optional[str] = None
    last_activation_market_cap_usd: Optional[str] = None
    delivery_retry_due: bool = False
    compose_near: bool = False
    quarantined: bool = False
    terminal_history: bool = False

    @classmethod
    def from_entry(cls, entry: Any, *, now_epoch: float) -> "CandidateScheduleView":
        mint = str(getattr(entry, "token_mint", "") or "")
        candidate_id = str(getattr(entry, "candidate_id", "") or "")
        seeded_raw = getattr(entry, "seeded_at_utc", None)
        seeded = _epoch(seeded_raw)
        generation = candidate_generation(
            candidate_id,
            seeded_raw,
            getattr(entry, "market_observation_generation", 0),
        )
        retry_at = _epoch(getattr(entry, "delivery_next_retry_at_utc", None))
        return cls(
            mint=mint,
            candidate_id=candidate_id,
            generation=generation,
            status=str(getattr(entry, "status", "") or ""),
            seeded_at_epoch=(float(now_epoch) if seeded is None else seeded),
            market_state=getattr(entry, "market_state", None),
            market_reason_code=getattr(entry, "market_reason_code", None),
            last_observed_epoch=_epoch(getattr(entry, "last_observed_at_utc", None)),
            next_recovery_epoch=_epoch(getattr(entry, "next_market_refresh_at_utc", None)),
            activation_target_market_cap_usd=getattr(
                entry, "activation_target_market_cap_usd", None),
            last_activation_market_cap_usd=getattr(
                entry, "last_activation_progress_market_cap_usd", None),
            delivery_retry_due=(retry_at is not None and retry_at <= float(now_epoch)),
            compose_near=bool(getattr(entry, "market_compose_near", False)),
            quarantined=bool(getattr(entry, "market_scheduler_quarantined", False)),
            terminal_history=bool(getattr(entry, "market_terminal_history", False)),
        )


@dataclass(frozen=True)
class MarketObservation:
    mint: str
    candidate_id: str
    generation: int
    source: str
    source_timestamp: float
    ingestion_timestamp: float
    field_group: str
    observation_sequence: int
    source_evidence_digest: str
    request_id: Optional[str]
    values: Mapping[str, Any]
    source_order: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.mint or not self.candidate_id or self.generation <= 0:
            raise ValueError("market_observation_binding_invalid")
        if self.field_group not in (FIELD_PRICE_MC, FIELD_OVERVIEW):
            raise ValueError("market_observation_field_group_invalid")
        if not isinstance(self.source_evidence_digest, str) or len(
                self.source_evidence_digest) != 64:
            raise ValueError("market_observation_digest_invalid")


@dataclass(order=True, frozen=True)
class MarketJob:
    sort_key: Tuple[int, float, float, str, str, int]
    request_id: str = field(compare=False)
    field_group: str = field(compare=False)
    mints: Tuple[str, ...] = field(compare=False)
    bindings: Tuple[Tuple[str, int], ...] = field(compare=False)
    submitted_at: float = field(compare=False)
    priority: int = field(compare=False)
    # PHX2-E2E-006: monotonic instant after which no provider attempt may
    # START for this job (P1 work only; None = no candidate deadline).
    deadline_mono: Optional[float] = field(default=None, compare=False)


@dataclass
class _P1Window:
    """One open P1 service window for (mint, generation, tier)."""

    mint: str
    generation: int
    tier: str
    evidence_generation: int
    due_epoch: float
    opened_mono: float
    closed: bool = False
    outcome: Optional[str] = None


@dataclass
class _MarketState:
    price: Optional[str] = None
    price_timestamp: Optional[float] = None
    price_source: Optional[str] = None
    price_source_order: Tuple[int, ...] = ()
    market_cap: Optional[str] = None
    market_cap_timestamp: Optional[float] = None
    market_cap_source: Optional[str] = None
    market_cap_source_order: Tuple[int, ...] = ()
    liquidity: Optional[str] = None
    liquidity_timestamp: Optional[float] = None
    liquidity_source: Optional[str] = None
    liquidity_source_order: Tuple[int, ...] = ()
    latest_sequence: Dict[str, int] = field(default_factory=dict)
    last_request_error: Optional[str] = None
    failure_count: int = 0
    projected_tier: Optional[str] = None
    projected_drawdown_pct: Optional[str] = None
    # Which PROVIDER OBSERVATION each field was last written from.  The
    # price and market-cap planes are deliberately independent (an overview
    # may refresh the market cap without touching the price), so the pair
    # (price, market_cap) a snapshot exposes is NOT automatically two halves
    # of one response.  In the 2026-08-02 run April's snapshot carried a
    # 06:08:21Z price beside a 06:08:05Z market cap; feeding that pair to
    # the central ATH store as one "observation" is what produced records
    # whose price maximum and market-cap maximum described different
    # instants -- and, through the derived supply, what made every later
    # candle high unconvertible.  Recording the identity lets a consumer ask
    # for a COHERENT pair instead of guessing.
    price_observation_key: Optional[Tuple[str, int]] = None
    market_cap_observation_key: Optional[Tuple[str, int]] = None
    pumpswap_reserve: Dict[str, Any] = field(default_factory=dict)


def project_closed_tier(*, ath_market_cap_usd: object,
                        current_market_cap_usd: object) -> Tuple[Optional[str], Optional[str]]:
    """Exact Decimal projection using the existing closed Tier 1/2/3 bands."""

    ath = _positive_decimal(ath_market_cap_usd)
    current = _positive_decimal(current_market_cap_usd)
    if ath is None or current is None or current > ath:
        return None, None
    drop = ath - current
    with localcontext() as ctx:
        ctx.prec = max(ctx.prec, len(ath.as_tuple().digits) + 6)
        edges = tuple(ath * boundary for boundary in (
            Decimal("0.50"), Decimal("0.60"), Decimal("0.62"),
            Decimal("0.80"), Decimal("0.82"), Decimal("0.95")))
        pct = (drop / ath) * Decimal(100)
    if drop < edges[0]:
        tier = None
    elif drop <= edges[1]:
        tier = "Tier 1"
    elif drop < edges[2]:
        tier = None
    elif drop <= edges[3]:
        tier = "Tier 2"
    elif drop < edges[4]:
        tier = None
    elif drop <= edges[5]:
        tier = "Tier 3"
    else:
        tier = None
    return tier, _decimal_text(pct)


class MarketScheduler:
    """Bounded provider workers plus one authoritative observation owner."""

    def __init__(
        self,
        *,
        price_fetch_fn: Optional[Callable[[str], Optional[Mapping[str, Any]]]],
        overview_fetch_fn: Optional[Callable[[str], Optional[Mapping[str, Any]]]],
        batch_price_fetch_fn: Optional[
            Callable[[Sequence[str]], Mapping[str, Mapping[str, Any]]]] = None,
        config: Optional[MarketSchedulerConfig] = None,
        now_fn: Callable[[], float] = time.time,
        monotonic_fn: Callable[[], float] = time.monotonic,
        apply_callback: Optional[
            Callable[[MarketObservation, Mapping[str, Any]], None]] = None,
        failure_callback: Optional[
            Callable[[str, str, str], None]] = None,
        quote_price_apply_fn: Optional[
            Callable[[str, str, str], None]] = None,
        physical_request_meter: Optional[MarketPhysicalRequestMeter] = None,
        fresh_fallback_fetch_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config or MarketSchedulerConfig()
        self._price_fetch = price_fetch_fn
        self._overview_fetch = overview_fetch_fn
        self._batch_price_fetch = batch_price_fetch_fn
        self._now = now_fn
        self._mono = monotonic_fn
        self._apply_callback = apply_callback
        self._failure_callback = failure_callback
        self._quote_price_apply = quote_price_apply_fn
        self._fresh_fallback_fetch = fresh_fallback_fetch_fn
        # PHX2-E2E-006 priority lanes: the fast lane carries P0/P1 alert
        # work, the general lane carries P2/P3 background work.  Reserved
        # workers drain ONLY the fast lane, so a hung background request can
        # never occupy every worker that tier-due work depends on.
        self._jobs: queue.PriorityQueue[MarketJob] = queue.PriorityQueue(
            maxsize=self.config.max_queue_size)
        self._jobs_general: queue.PriorityQueue[MarketJob] = queue.PriorityQueue(
            maxsize=self.config.max_queue_size)
        self._results: queue.Queue[Optional[Tuple[MarketJob, Any, Optional[str]]]] = queue.Queue(
            maxsize=(self.config.max_queue_size * 2) + self.config.max_inflight)
        self._stop = threading.Event()
        self._accepting = True
        self._started = False
        self._workers: List[threading.Thread] = []
        self._owner: Optional[threading.Thread] = None
        self._planner: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._inflight_gate = threading.BoundedSemaphore(self.config.max_inflight)
        self._views: Dict[str, CandidateScheduleView] = {}
        self._candidate_views: Dict[str, CandidateScheduleView] = {}
        self._paper_views: Dict[str, CandidateScheduleView] = {}
        self._state: Dict[str, _MarketState] = {}
        self._queued_keys: set[Tuple[str, str]] = set()
        self._inflight_keys: set[Tuple[str, str]] = set()
        self._queued_by_priority: Dict[int, int] = {
            PRIORITY_P0: 0, PRIORITY_P1: 0, PRIORITY_P2: 0, PRIORITY_P3: 0}
        self._sequence = 0
        self._request_sequence = 0
        # LOGICAL dispatches: jobs this scheduler handed to a fetch function.
        # Kept for capacity/inflight observability -- it is NOT the budget.
        self._provider_requests_started = 0
        # PHYSICAL requests: increments observed on the shared meter across
        # this scheduler's own fetch calls.  THIS is what the budget charges.
        # A cache hit, a backoff skip and a deadline refusal all move the
        # logical counter and leave this one alone, which is exactly the
        # distinction the 2026-08-02 run did not make.
        self._physical_meter = physical_request_meter
        self._scheduler_physical_requests = 0
        self._charged_ticket_count_by_job: Dict[str, int] = {}
        self._non_physical_dispatches = 0
        self._provider_requests_inflight = 0
        self._max_observed_inflight = 0
        self._capacity_limiting_resource: Optional[str] = None
        self._capacity_pacing_floor_seconds = 0.0
        self._last_heartbeat_due: Optional[float] = None
        self._last_heartbeat_actual: Optional[float] = None
        # Degraded reasons are OBSERVATIONS WITH AN AGE, never a lifetime
        # latch. This was a set that only ever grew: one transient breach at
        # any point in a run pinned SCHEDULER_DEGRADED for the whole process
        # lifetime, so the signal could neither clear when the scheduler
        # recovered nor distinguish a current problem from an old one (the
        # 2026-07-29 run ended DEGRADED with an empty queue and nothing in
        # flight). Each reason now records WHEN it was last observed and ages
        # out of the reported set; the lifetime tally is kept separately so no
        # evidence is lost.
        self._degraded_seen_epoch: Dict[str, float] = {}
        self._degraded_lifetime: Dict[str, int] = {}
        # ---- P1 window state (PHX2-E2E-006) ----
        self._p1_windows: Dict[Tuple[str, int, str], _P1Window] = {}
        self._p1_evidence_counter = 0
        self._p1_latencies: List[float] = []
        self._p1_cooldown_active = False
        self._capacity_proof: Optional[Dict[str, Any]] = None
        self._capacity_refused = False
        self._dispatch_waker: Optional[Callable[[], None]] = None
        self._handoff_depth = 0
        self._handoff_oldest_age = 0.0
        # Deadline-aware fetchers are detected once; legacy single-argument
        # fetch callables keep working unchanged.
        self._overview_accepts_deadline = _accepts_deadline_kwarg(overview_fetch_fn)
        self._price_accepts_deadline = _accepts_deadline_kwarg(price_fetch_fn)
        self._counters: Dict[str, int] = {
            "market_scheduler_jobs_submitted": 0,
            "market_scheduler_jobs_completed": 0,
            "market_scheduler_jobs_settled": 0,
            "market_scheduler_jobs_cancelled": 0,
            "market_scheduler_late_results_rejected": 0,
            "market_scheduler_generation_mismatch_rejected": 0,
            "market_price_batch_requests": 0,
            "market_price_batch_mints": 0,
            "market_price_single_requests": 0,
            "market_overview_requests": 0,
            "market_requests_coalesced": 0,
            "market_requests_avoided_by_grpc": 0,
            "market_grpc_price_observations": 0,
            "market_grpc_observations_rejected": 0,
            "market_batch_partial": 0,
            "market_wrong_mint_rejected": 0,
            "market_malformed_results_rejected": 0,
            "market_results_unchanged": 0,
            "market_expired_results_rejected": 0,
            "market_terminal_results_rejected": 0,
            "market_quarantined_results_rejected": 0,
            # ---- PHX2-E2E-006 P1 lane counters ----
            "p1_enqueued_total": 0,
            "p1_completed_total": 0,
            "p1_deadline_met_total": 0,
            "p1_deadline_missed_total": 0,
            "p1_temporary_failures_total": 0,
            "p1_permanent_blocks_total": 0,
            "p1_provider_jobs_enqueued_total": 0,
            "provider_timeout_total": 0,
            "provider_error_total": 0,
            "cache_hit_total": 0,
            "cache_miss_total": 0,
            "superseded_work_total": 0,
            "stale_result_total": 0,
            "duplicate_result_total": 0,
            "handoff_drained_total": 0,
            "handoff_rejected_total": 0,
            # ---- send-time priority refresh (2026-08-02 remediation) ----
            "priority_refresh_requested_total": 0,
            "priority_refresh_succeeded_total": 0,
            "priority_refresh_retryable_total": 0,
            "priority_refresh_permanent_total": 0,
            "priority_refresh_rate_limited_total": 0,
            "priority_refresh_coalesced_total": 0,
            "priority_refresh_provider_requests_total": 0,
            "fresh_market_fallback_attempts_total": 0,
            "fresh_market_fallback_succeeded_total": 0,
            "fresh_market_fallback_failed_total": 0,
            "fresh_market_fallback_capability_unavailable_total": 0,
            "scheduler_physical_requests_total": 0,
            "market_non_physical_dispatches": 0,
            "market_price_batch_mints_resolved": 0,
            "market_price_batch_partial": 0,
            "market_price_batch_failed": 0,
        }
        # Per-mint priority-refresh bookkeeping.  Coalescing is keyed on the
        # mint so two candidate evaluations racing the same send decision
        # make ONE provider request, not two.
        self._priority_refresh_inflight: set[str] = set()
        self._priority_refresh_next_allowed: Dict[str, float] = {}
        self._priority_refresh_failures: Dict[str, int] = {}
        self._priority_refresh_permanent: Dict[str, int] = {}
        self._fresh_fallback_last_result: Dict[str, str] = {}
        self._latencies: Dict[str, List[float]] = {
            "market_grpc_to_watch_latency_ms": [],
            "market_due_recovery_probe_latency_ms": [],
        }

    # ---- lifecycle -----------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self._stop.is_set():
                raise RuntimeError("market_scheduler_already_stopped")
            self._started = True
            self._owner = threading.Thread(
                target=self._owner_loop, name="phx2-market-owner", daemon=True)
            self._owner.start()
            for index in range(self.config.worker_count):
                # Workers below the reserved count drain ONLY the fast
                # (P0/P1) lane; the rest prefer the fast lane but also keep
                # P2/P3 from starving.
                worker = threading.Thread(
                    target=self._worker_loop,
                    args=(index,),
                    name=f"phx2-market-worker-{index}", daemon=True)
                self._workers.append(worker)
                worker.start()
            # The planner sweep used to belong to the producer's watch tick.
            # A tick is ~46 s in production, so a 12 s TTL could never be
            # honoured no matter how idle the workers were.  When an
            # interval is configured the scheduler owns its own bounded
            # sweep; ``plan()`` stays idempotent and caller-drivable, so
            # every existing caller and unit test is unaffected.
            if float(self.config.planner_interval_seconds) > 0:
                self._planner = threading.Thread(
                    target=self._planner_loop, name="phx2-market-planner",
                    daemon=True)
                self._planner.start()

    def _planner_loop(self) -> None:
        interval = max(0.01, float(self.config.planner_interval_seconds))
        while not self._stop.wait(interval):
            try:
                self.plan()
            except Exception:
                # Planning is best-effort background scheduling: a planning
                # fault must never kill the thread that keeps tier-active
                # candidates fresh, and never propagates to the producer.
                self._note_degraded(MARKET_SCHEDULER_OVERLOADED)

    def request_stop(self) -> None:
        with self._lock:
            self._accepting = False
            self._stop.set()

    def stop(self, *, timeout_seconds: float = 10.0) -> bool:
        self.request_stop()
        # Remove jobs that have not begun. No provider call may start after the
        # stop flag is visible.
        for lane in (self._jobs, self._jobs_general):
            while True:
                try:
                    job = lane.get_nowait()
                except queue.Empty:
                    break
                self._release_job_keys(job, inflight=False)
                self._note_dequeued(job)
                self._counters["market_scheduler_jobs_cancelled"] += 1
                lane.task_done()
        deadline = self._mono() + max(0.0, float(timeout_seconds))
        # The planner blocks on the stop event, so it returns within one
        # interval.  Joined first so no further work can be planned while
        # the workers are draining.
        if self._planner is not None:
            self._planner.join(max(0.0, deadline - self._mono()))
        for worker in self._workers:
            remaining = max(0.0, deadline - self._mono())
            worker.join(remaining)
        # Results that completed before stop are rejected by the owner policy;
        # let the owner observe them before its sentinel.
        workers_stopped = not any(worker.is_alive() for worker in self._workers)
        if self._owner is not None and workers_stopped:
            try:
                self._results.put_nowait(None)
            except queue.Full:
                pass
            remaining = max(0.0, deadline - self._mono())
            self._owner.join(remaining)
        return workers_stopped and not (
            self._owner is not None and self._owner.is_alive())

    # ---- candidate planning -------------------------------------------

    def update_candidates(self, entries: Iterable[Any], *, now_epoch: Optional[float] = None) -> None:
        now = float(self._now() if now_epoch is None else now_epoch)
        views: Dict[str, CandidateScheduleView] = {}
        for entry in entries:
            view = (entry if isinstance(entry, CandidateScheduleView)
                    else CandidateScheduleView.from_entry(entry, now_epoch=now))
            if view.mint:
                views[view.mint] = view
        with self._lock:
            self._candidate_views = views
            self._views = {**self._paper_views, **views}
            for mint in views:
                self._state.setdefault(mint, _MarketState())

    def update_paper_candidates(self, entries: Iterable[Any], *, max_tracked: int = 32) -> None:
        """Bounded quote demand for paper continuity; never changes watch eligibility."""
        now = float(self._now())
        views = {}
        for entry in entries:
            view = CandidateScheduleView.from_entry(entry, now_epoch=now)
            if view.mint and not view.quarantined:
                views[view.mint] = replace(view, status="PAPER_PRICE_WATCH",
                    terminal_history=False, compose_near=False, delivery_retry_due=False)
            if len(views) > max_tracked:
                raise ValueError("PAPER_PRICE_CAPACITY_EXCEEDED")
        with self._lock:
            self._paper_views = views
            self._views = {**views, **self._candidate_views}
            for mint in views:
                self._state.setdefault(mint, _MarketState())

    def _priority(self, view: CandidateScheduleView, *, now: float) -> int:
        if view.status == "PAPER_PRICE_WATCH":
            return PRIORITY_P2
        if view.delivery_retry_due or view.compose_near:
            return PRIORITY_P0
        if view.market_state == "MARKET_RECOVERY_BACKOFF" and (
                view.next_recovery_epoch is None or view.next_recovery_epoch <= now):
            return PRIORITY_P0
        with self._lock:
            state = self._state.get(view.mint)
            drawdown = (_positive_decimal(state.projected_drawdown_pct)
                        if state is not None else None)
            liquidity = (_positive_decimal(state.liquidity)
                         if state is not None else None)
        if view.status in _ACTIVATED_STATES and drawdown is not None:
            boundaries = tuple(Decimal(value) for value in (50, 60, 62, 80, 82, 95))
            if any(abs(drawdown - boundary) <= self.config.near_tier_margin_pct
                   for boundary in boundaries):
                return PRIORITY_P0
        # Liquidity proximity changes scheduling only. Exact compose-time
        # authorization continues to use the existing $4,500 Decimal floor.
        if liquidity is not None:
            distance_pct = abs(liquidity - Decimal("4500")) / Decimal("4500") * 100
            if distance_pct <= self.config.near_activation_margin_pct:
                return PRIORITY_P0
        if view.status in _ACTIVATED_STATES:
            return PRIORITY_P1
        target = _positive_decimal(view.activation_target_market_cap_usd)
        current = _positive_decimal(view.last_activation_market_cap_usd)
        if view.status == "PENDING_1_20X" and target is not None and current is not None:
            proximity = (abs(target - current) / target) * Decimal(100)
            if proximity <= self.config.near_activation_margin_pct:
                return PRIORITY_P2
        if view.status == "PENDING_BASELINE":
            return PRIORITY_P2
        if now - view.seeded_at_epoch >= self.config.background_starvation_seconds:
            return PRIORITY_P0
        return PRIORITY_P3

    def _ttls(self, view: CandidateScheduleView) -> Tuple[float, float]:
        """The HARD freshness contract for one candidate (unchanged).

        A value older than these bounds is stale and can never authorize a
        send.  Scheduling cadence is a separate, stricter question -- see
        ``_refresh_intervals``.
        """

        if view.status in _ACTIVATED_STATES:
            return (self.config.price_active_ttl_seconds,
                    self.config.overview_active_ttl_seconds)
        return (self.config.price_pending_ttl_seconds,
                self.config.overview_pending_ttl_seconds)

    def cadence_class(self, view: CandidateScheduleView) -> str:
        """Which adaptive cadence class one candidate is currently in.

        Pure classification over already-observed state; makes no provider
        request and never mutates anything.  The projected drawdown is the
        SAME value the tier projection publishes, so a candidate the tier
        math considers in-band is exactly the candidate this class speeds
        up.
        """

        if view.status == "PAPER_PRICE_WATCH":
            return CADENCE_FAR
        if view.quarantined or view.terminal_history \
                or view.status in _TERMINAL_STATES:
            return CADENCE_INACTIVE
        if view.delivery_retry_due or view.compose_near:
            return CADENCE_TIER_ACTIVE
        state = self._state.get(view.mint)
        drawdown = (_positive_decimal(state.projected_drawdown_pct)
                    if state is not None else None)
        projected_tier = (state.projected_tier if state is not None else None)
        # Liquidity hovering at the hard $4,500 floor is already a P0
        # SCHEDULING signal (see ``_priority``); the cadence class mirrors it
        # so a candidate whose authorization could flip on the next overview
        # is not slowed down.  Exact compose-time authorization continues to
        # use the same Decimal floor and is untouched by scheduling.
        liquidity = (_positive_decimal(state.liquidity)
                     if state is not None else None)
        liquidity_near_floor = bool(
            liquidity is not None
            and (abs(liquidity - Decimal("4500")) / Decimal("4500")
                 * Decimal(100)) <= self.config.near_activation_margin_pct)
        if view.status in _ACTIVATED_STATES:
            if projected_tier is not None:
                return CADENCE_TIER_ACTIVE
            if drawdown is not None:
                margin = self.config.near_tier_margin_pct
                if any(abs(drawdown - Decimal(boundary)) <= margin
                       for boundary in (50, 60, 62, 80, 82, 95)):
                    return CADENCE_TIER_ACTIVE
                # An activated candidate whose drawdown is inside the
                # widest band edge is still meaningfully approaching a
                # tier; anything shallower is far from every band.
                if drawdown >= (Decimal(50) - self.config.
                                near_activation_margin_pct):
                    return CADENCE_NEAR_TIER
            else:
                # Activated but no projection yet: treat as approaching so
                # the first tier projection is not delayed by a slow poll.
                return CADENCE_NEAR_TIER
            return CADENCE_NEAR_TIER if liquidity_near_floor else CADENCE_FAR
        if view.status in _PENDING_STATES:
            if liquidity_near_floor:
                return CADENCE_NEAR_TIER
            target = _positive_decimal(view.activation_target_market_cap_usd)
            current = _positive_decimal(view.last_activation_market_cap_usd)
            if (view.status == "PENDING_1_20X" and target is not None
                    and current is not None):
                proximity = (abs(target - current) / target) * Decimal(100)
                if proximity <= self.config.near_activation_margin_pct:
                    return CADENCE_NEAR_TIER
            return CADENCE_FAR
        return CADENCE_INACTIVE

    def _refresh_intervals(
        self, view: CandidateScheduleView
    ) -> Tuple[float, float, str]:
        """(price_interval, overview_interval, cadence_class) for one view.

        A tier-relevant interval is additionally clamped to the configured
        headroom inside the candidate's own hard TTL, so the invariant holds
        even if an operator supplies a longer interval than the TTL allows.
        """

        cadence = self.cadence_class(view)
        config = self.config
        if cadence == CADENCE_TIER_ACTIVE:
            price = config.price_tier_active_refresh_seconds
            overview = config.overview_tier_active_refresh_seconds
        elif cadence == CADENCE_NEAR_TIER:
            price = config.price_near_tier_refresh_seconds
            overview = config.overview_near_tier_refresh_seconds
        elif cadence == CADENCE_FAR:
            price = config.price_far_refresh_seconds
            overview = config.overview_far_refresh_seconds
        else:
            price = config.price_inactive_refresh_seconds
            overview = config.overview_inactive_refresh_seconds
        if cadence in (CADENCE_TIER_ACTIVE, CADENCE_NEAR_TIER):
            price_ttl, overview_ttl = self._ttls(view)
            headroom = float(config.cadence_headroom_fraction)
            price = min(float(price), float(price_ttl) * headroom)
            overview = min(float(overview), float(overview_ttl) * headroom)
        return float(price), float(overview), cadence

    def _field_due(self, view: CandidateScheduleView, field_group: str,
                   *, now: float) -> Tuple[bool, float, float]:
        state = self._state.setdefault(view.mint, _MarketState())
        price_ttl, overview_ttl = self._refresh_intervals(view)[:2]
        if field_group == FIELD_PRICE_MC:
            timestamps = (state.price_timestamp, state.market_cap_timestamp)
            last = min((value for value in timestamps if value is not None), default=None)
            # Both fast-plane fields must be fresh independently.
            fresh = all(value is not None and now - value <= price_ttl for value in timestamps)
            deadline = (view.seeded_at_epoch if last is None else last + price_ttl)
            return (not fresh, deadline, view.seeded_at_epoch if last is None else last)
        last = state.liquidity_timestamp
        fresh = last is not None and now - last <= overview_ttl
        deadline = view.seeded_at_epoch if last is None else last + overview_ttl
        return (not fresh, deadline, view.seeded_at_epoch if last is None else last)

    def plan(self, *, now_epoch: Optional[float] = None,
             enqueue: bool = True) -> List[MarketJob]:
        now = float(self._now() if now_epoch is None else now_epoch)
        # Deadline misses become explicit before any new work is planned.
        self.sweep_p1_deadlines(now_epoch=now)
        singles: List[Tuple[CandidateScheduleView, str, int, float, float]] = []
        with self._lock:
            views = list(self._views.values())
        for view in views:
            if view.quarantined or view.terminal_history or view.status in _TERMINAL_STATES:
                continue
            # The existing readiness owner persists both ordinary retry and
            # recovery-probe deadlines in this field. Neither phase may be
            # polled before its authoritative deadline.
            if (view.market_state not in (None, "MARKET_READY")
                    and view.next_recovery_epoch is not None
                    and view.next_recovery_epoch > now):
                continue
            priority = self._priority(view, now=now)
            for group in (FIELD_PRICE_MC, FIELD_OVERVIEW):
                due, deadline, last = self._field_due(view, group, now=now)
                if due:
                    overdue = max(0.0, now - deadline)
                    if (group == FIELD_OVERVIEW
                            and view.status in _ACTIVATED_STATES
                            and overdue > self.config.activated_overview_schedule_slo_seconds):
                        self._note_degraded(MARKET_LATENCY_SLO_BREACHED)
                    if (view.market_state == "MARKET_RECOVERY_BACKOFF"
                            and overdue > self.config.recovery_schedule_slo_seconds):
                        self._note_degraded(MARKET_LATENCY_SLO_BREACHED)
                    if (group == FIELD_PRICE_MC
                            and view.status == "PENDING_1_20X"
                            and last is not None
                            and now - last > self.config.pending_price_max_age_seconds):
                        self._note_degraded(MARKET_LATENCY_SLO_BREACHED)
                    if (view.status not in _ACTIVATED_STATES
                            and view.market_state != "MARKET_RECOVERY_BACKOFF"
                            and now - last > self.config.background_starvation_seconds):
                        self._note_degraded(MARKET_OBSERVATION_STARVED)
                    singles.append((view, group, priority, deadline, last))
        singles.sort(key=lambda item: (
            item[2], item[3], item[4], item[0].mint, item[0].candidate_id, item[1]))

        jobs: List[MarketJob] = []
        batch_enabled = bool(
            self._batch_price_fetch is not None and self.config.paid_batch_size > 1)
        if batch_enabled:
            price_rows = [row for row in singles if row[1] == FIELD_PRICE_MC]
            overview_rows = [row for row in singles if row[1] == FIELD_OVERVIEW]
            # Chunked WITHIN a priority class, never across one.  A batch is a
            # single physical request that occupies a worker for its whole
            # duration, so a mixed chunk would drag one alert-critical
            # candidate along at the speed of up to 49 background mints -- and
            # a job takes the priority of its first row, which would also route
            # the whole background chunk into the reserved fast lane.
            by_priority: Dict[int, List[Any]] = {}
            for row in price_rows:
                by_priority.setdefault(row[2], []).append(row)
            for priority in sorted(by_priority):
                rows = by_priority[priority]
                for index in range(0, len(rows), self.config.paid_batch_size):
                    chunk = rows[index:index + self.config.paid_batch_size]
                    if not chunk:
                        continue
                    jobs.append(self._make_job(chunk, now=now))
            jobs.extend(self._make_job([row], now=now) for row in overview_rows)
        else:
            jobs.extend(self._make_job([row], now=now) for row in singles)
        jobs.sort()
        self._assess_planned_capacity(len(jobs))
        if enqueue:
            accepted: List[MarketJob] = []
            for job in jobs:
                if self._enqueue(job):
                    accepted.append(job)
                    with self._lock:
                        due_views = [self._views.get(mint) for mint in job.mints]
                    for due_view in due_views:
                        if (due_view is not None
                                and due_view.market_state == "MARKET_RECOVERY_BACKOFF"
                                and due_view.next_recovery_epoch is not None):
                            latency_ms = max(
                                0.0, (now - due_view.next_recovery_epoch) * 1000.0)
                            self._latencies[
                                "market_due_recovery_probe_latency_ms"].append(latency_ms)
                            del self._latencies[
                                "market_due_recovery_probe_latency_ms"][:-256]
                            if latency_ms > (
                                    self.config.recovery_schedule_slo_seconds * 1000.0):
                                self._note_degraded(MARKET_LATENCY_SLO_BREACHED)
            return accepted
        return jobs

    def _assess_planned_capacity(self, request_count: int) -> None:
        pacing_floor = max(
            0, int(request_count) - 1) * self.config.provider_min_interval_seconds
        with self._lock:
            self._capacity_pacing_floor_seconds = max(
                self._capacity_pacing_floor_seconds, pacing_floor)
            if pacing_floor > self.config.pending_price_max_age_seconds:
                self._capacity_limiting_resource = (
                    "PAID_PRIMARY_GLOBAL_REQUEST_SPACING")
                self._note_degraded(LATENCY_SLO_UNACHIEVABLE)

    def _make_job(self, rows: Sequence[
            Tuple[CandidateScheduleView, str, int, float, float]], *, now: float) -> MarketJob:
        self._request_sequence += 1
        first = rows[0]
        mints = tuple(row[0].mint for row in rows)
        bindings = tuple((row[0].candidate_id, row[0].generation) for row in rows)
        return MarketJob(
            sort_key=(first[2], first[3], first[4], mints[0], first[1], self._request_sequence),
            request_id=f"market-{self._request_sequence:012d}",
            field_group=first[1],
            mints=mints,
            bindings=bindings,
            submitted_at=now,
            priority=first[2],
        )

    def _lane_for(self, priority: int) -> "queue.PriorityQueue[MarketJob]":
        return self._jobs if priority <= PRIORITY_P1 else self._jobs_general

    # ---- budget accounting (physical dispatch only) ----------------------
    def _budget_charged_locked(self) -> int:
        """Requests charged against the lifetime budget so far.

        With a shared meter installed this is the count of requests that
        genuinely crossed the physical provider boundary.  Without one (offline
        callers that wire plain callables and no transport) it degrades to the
        legacy logical count, so existing bounded harnesses keep their exact
        previous semantics.
        """

        if self._physical_meter is None:
            return self._provider_requests_started
        return max(
            self._scheduler_physical_requests,
            self._physical_meter.scheduler_job_owned_total,
        )

    def _budget_exhausted_locked(self, *, pending: int = 0) -> bool:
        """True iff another physical request would exceed the lifetime cap.

        Under the UNBOUNDED sentinel there is no cap, so this is always False
        and ``MARKET_PROVIDER_BUDGET_EXHAUSTED`` can never be raised -- the
        condition that blinded the market plane for 4h38m on 2026-08-02.
        """

        if self.config.provider_budget_unbounded:
            return False
        return (self._budget_charged_locked() + int(pending)
                >= int(self.config.provider_request_budget))

    def _ticket_ownership(self, job: MarketJob, *, priority_refresh: bool = False) -> Any:
        """Bind transport tickets to one immutable scheduler job identity."""

        if self._physical_meter is None:
            return nullcontext()
        if priority_refresh:
            origin = (
                ORIGIN_PRIORITY_REFRESH_PRICE
                if job.field_group in (FIELD_PRICE_MC, FIELD_QUOTE_PRICE)
                else ORIGIN_PRIORITY_REFRESH_OVERVIEW)
        else:
            origin = (
                ORIGIN_SCHEDULED_PRICE
                if job.field_group in (FIELD_PRICE_MC, FIELD_QUOTE_PRICE)
                else ORIGIN_SCHEDULED_OVERVIEW)
        return self._physical_meter.ownership(
            origin=origin,
            scheduler_job_id=job.request_id,
            mint=(job.mints[0] if len(job.mints) == 1 else None),
            priority=PRIORITY_NAMES.get(job.priority, str(job.priority)),
            scheduler_owner="MARKET_SCHEDULER",
            batch_size=len(job.mints),
        )

    def _charge_job_tickets(self, job: MarketJob) -> int:
        """Charge only completed tickets carrying this exact job ID."""

        if self._physical_meter is None:
            return 0
        current = self._physical_meter.ticket_count_for_job(job.request_id)
        with self._lock:
            previous = self._charged_ticket_count_by_job.get(job.request_id, 0)
            charged = max(0, current - previous)
            self._charged_ticket_count_by_job[job.request_id] = current
            # The ledger total changes at the exact dispatch boundary, even
            # while this job is still in flight.  Mirror that source of truth
            # instead of accumulating a second independently timed counter.
            self._scheduler_physical_requests = max(
                self._scheduler_physical_requests,
                self._physical_meter.scheduler_job_owned_total,
            )
            if charged == 0:
                self._non_physical_dispatches += 1
                self._counters["market_non_physical_dispatches"] += 1
            self._counters["scheduler_physical_requests_total"] = (
                self._scheduler_physical_requests)
        return charged

    def _batch_telemetry_locked(self) -> Dict[str, Any]:
        """Batching posture and what it actually saved. Caller holds the lock."""

        enabled = bool(self._batch_price_fetch is not None
                       and int(self.config.paid_batch_size) > 1)
        batches = int(self._counters["market_price_batch_requests"])
        mints_requested = int(self._counters["market_price_batch_mints"])
        mints_resolved = int(self._counters["market_price_batch_mints_resolved"])
        return {
            "market_batch_enabled": enabled,
            "market_batch_configured_size": (
                int(self.config.paid_batch_size) if enabled else 0),
            "market_batches_issued": batches,
            "market_batch_mints_requested": mints_requested,
            "market_batch_mints_resolved": mints_resolved,
            "market_batch_mints_unresolved": max(
                0, mints_requested - mints_resolved),
            "market_batches_partial": int(
                self._counters["market_price_batch_partial"]),
            "market_batches_failed": int(
                self._counters["market_price_batch_failed"]),
            # One batch is one physical request; N single-mint calls would
            # have been N.  The saving is stated, never assumed.
            "market_batch_physical_requests_saved": max(
                0, mints_requested - batches),
        }

    def _note_dequeued(self, job: MarketJob) -> None:
        with self._lock:
            count = self._queued_by_priority.get(job.priority, 0)
            self._queued_by_priority[job.priority] = max(0, count - 1)

    def _enqueue(self, job: MarketJob) -> bool:
        with self._lock:
            if not self._accepting or self._stop.is_set():
                self._counters["market_scheduler_jobs_cancelled"] += 1
                return False
            keys = {(mint, job.field_group) for mint in job.mints}
            if any(key in self._queued_keys or key in self._inflight_keys for key in keys):
                self._counters["market_requests_coalesced"] += len(keys)
                return False
            lane = self._lane_for(job.priority)
            if self._budget_exhausted_locked(
                    pending=self._jobs.qsize() + self._jobs_general.qsize()):
                self._note_degraded(MARKET_PROVIDER_BUDGET_EXHAUSTED)
                return False
            try:
                lane.put_nowait(job)
            except queue.Full:
                self._note_degraded(MARKET_SCHEDULER_OVERLOADED)
                return False
            self._queued_keys.update(keys)
            self._queued_by_priority[job.priority] = (
                self._queued_by_priority.get(job.priority, 0) + 1)
            self._counters["market_scheduler_jobs_submitted"] += 1
            if lane.qsize() >= int(
                    self.config.max_queue_size * self.config.backlog_high_fraction):
                self._note_degraded(MARKET_SCHEDULER_BACKLOG_HIGH)
            return True

    def request_quote_price(self, quote_mint: str) -> bool:
        """Schedule one shared paid quote-price refresh at immediate priority."""

        if not isinstance(quote_mint, str) or not quote_mint or self._price_fetch is None:
            return False
        now = float(self._now())
        with self._lock:
            self._request_sequence += 1
            request_sequence = self._request_sequence
        job = MarketJob(
            sort_key=(PRIORITY_P0, now, now, quote_mint,
                      FIELD_QUOTE_PRICE, request_sequence),
            request_id=f"market-quote-{request_sequence:012d}",
            field_group=FIELD_QUOTE_PRICE,
            mints=(quote_mint,),
            bindings=(("SHARED_QUOTE_PRICE", 1),),
            submitted_at=now,
            priority=PRIORITY_P0,
        )
        return self._enqueue(job)

    # ---- P1 service windows (PHX2-E2E-006) ----------------------------

    def set_dispatch_waker(self, waker: Optional[Callable[[], None]]) -> None:
        """Install the event that wakes the watch loop for P1 work."""

        self._dispatch_waker = waker

    def _fire_waker(self) -> None:
        waker = self._dispatch_waker
        if waker is None:
            return
        try:
            waker()
        except Exception:
            pass

    def mark_p1_due(self, mint: str, *, tier: str,
                    due_epoch: Optional[float] = None,
                    now_epoch: Optional[float] = None) -> bool:
        """Open one P1 window at the FIRST valid tier-entry evidence.

        The deadline clock starts at ``due_epoch`` (the evidence
        timestamp), never at scheduler poll time.  Equivalent marks for the
        same (mint, generation, tier) coalesce into the already-open
        window; the targeted overview job is enqueued immediately when the
        liquidity plane is stale, without waiting for the next watch tick.
        """

        if tier not in P1_TIERS or not isinstance(mint, str) or not mint:
            return False
        now = float(self._now() if now_epoch is None else now_epoch)
        due = float(due_epoch) if due_epoch is not None else now
        due = min(due, now)
        job: Optional[MarketJob] = None
        with self._lock:
            view = self._views.get(mint)
            if view is None or view.status not in _ACTIVATED_STATES:
                return False
            if view.quarantined or view.terminal_history:
                return False
            key = (mint, view.generation, tier)
            window = self._p1_windows.get(key)
            if window is not None and not window.closed:
                return False
            self._p1_evidence_counter += 1
            self._p1_windows[key] = _P1Window(
                mint=mint,
                generation=view.generation,
                tier=tier,
                evidence_generation=self._p1_evidence_counter,
                due_epoch=due,
                opened_mono=float(self._mono()) - max(0.0, now - due),
            )
            # Bounded window registry: closed windows beyond twice the
            # active cap are pruned oldest-first.
            if len(self._p1_windows) > self.config.max_active_candidates * 2:
                for old_key in [k for k, w in sorted(
                        self._p1_windows.items(),
                        key=lambda item: item[1].opened_mono)
                        if self._p1_windows[k].closed][
                        :len(self._p1_windows)
                        - self.config.max_active_candidates * 2]:
                    self._p1_windows.pop(old_key, None)
            self._counters["p1_enqueued_total"] += 1
            due_overview, deadline, last = self._field_due(
                view, FIELD_OVERVIEW, now=now)
            if due_overview:
                self._counters["cache_miss_total"] += 1
                self._request_sequence += 1
                job = MarketJob(
                    sort_key=(PRIORITY_P0, due, last, mint, FIELD_OVERVIEW,
                              self._request_sequence),
                    request_id=f"market-p1-{self._request_sequence:012d}",
                    field_group=FIELD_OVERVIEW,
                    mints=(mint,),
                    bindings=((view.candidate_id, view.generation),),
                    submitted_at=now,
                    priority=PRIORITY_P0,
                    deadline_mono=(
                        float(self._mono()) - max(0.0, now - due)
                        + float(self.config.p1_deadline_seconds)),
                )
            else:
                self._counters["cache_hit_total"] += 1
        if job is not None:
            if self._enqueue(job):
                with self._lock:
                    self._counters["p1_provider_jobs_enqueued_total"] += 1
        self._fire_waker()
        return True

    def note_p1_result(self, mint: str, *, outcome: str,
                       now_epoch: Optional[float] = None) -> int:
        """Close every open P1 window for ``mint`` with a closed-set result."""

        if outcome not in P1_RESULT_TOKENS:
            outcome = P1_RESULT_TEMP_BLOCKED
        closed = 0
        mono_now = float(self._mono())
        with self._lock:
            for window in self._p1_windows.values():
                if window.closed or window.mint != mint:
                    continue
                window.closed = True
                window.outcome = outcome
                elapsed = max(0.0, mono_now - window.opened_mono)
                self._p1_latencies.append(elapsed)
                del self._p1_latencies[:-512]
                self._counters["p1_completed_total"] += 1
                if elapsed <= float(self.config.p1_deadline_seconds):
                    self._counters["p1_deadline_met_total"] += 1
                else:
                    self._counters["p1_deadline_missed_total"] += 1
                    self._note_degraded(P1_DEADLINE_MISSED)
                if outcome == P1_RESULT_PERM_BLOCKED:
                    self._counters["p1_permanent_blocks_total"] += 1
                elif outcome in (P1_RESULT_TEMP_BLOCKED,
                                 P1_RESULT_PROVIDER_FAILURE,
                                 P1_RESULT_SEND_COOLDOWN):
                    self._counters["p1_temporary_failures_total"] += 1
                closed += 1
        return closed

    def sweep_p1_deadlines(self, now_epoch: Optional[float] = None) -> int:
        """Explicitly transition every overdue open window to DEADLINE_MISSED.

        A candidate may not remain silently pending past the deadline: the
        miss is counted, surfaced through the degraded reasons, and the
        window closes with the explicit result token.
        """

        _ = now_epoch
        mono_now = float(self._mono())
        missed = 0
        with self._lock:
            if self._p1_cooldown_active:
                return 0
            for window in self._p1_windows.values():
                if window.closed:
                    continue
                elapsed = mono_now - window.opened_mono
                if elapsed > float(self.config.p1_deadline_seconds):
                    window.closed = True
                    window.outcome = P1_RESULT_DEADLINE_MISSED
                    self._p1_latencies.append(max(0.0, elapsed))
                    del self._p1_latencies[:-512]
                    self._counters["p1_completed_total"] += 1
                    self._counters["p1_deadline_missed_total"] += 1
                    self._note_degraded(P1_DEADLINE_MISSED)
                    missed += 1
        return missed

    def note_send_cooldown(self, active: bool) -> None:
        """Explicit cooldown accounting: open windows close as TEMP results.

        While the send cooldown holds, the engine cannot evaluate anyone;
        that is an explicit temporary block, never a silent pending state.
        When the cooldown releases, candidates still projecting a tier are
        re-marked due with a fresh deadline origin (the moment they became
        serviceable again).
        """

        remark: List[Tuple[str, str]] = []
        with self._lock:
            was_active = self._p1_cooldown_active
            self._p1_cooldown_active = bool(active)
            if active and not was_active:
                for window in self._p1_windows.values():
                    if window.closed:
                        continue
                    window.closed = True
                    window.outcome = P1_RESULT_SEND_COOLDOWN
                    self._counters["p1_completed_total"] += 1
                    self._counters["p1_temporary_failures_total"] += 1
            elif was_active and not active:
                for (mint, _generation, tier), window in list(
                        self._p1_windows.items()):
                    if window.closed and window.outcome == P1_RESULT_SEND_COOLDOWN:
                        state = self._state.get(mint)
                        if state is not None and state.projected_tier == tier:
                            remark.append((mint, tier))
        for mint, tier in remark:
            self.mark_p1_due(mint, tier=tier)
        if remark:
            self._fire_waker()

    def reconstruct_p1_from_watch(self, entries: Iterable[Any], *,
                                  now_epoch: Optional[float] = None) -> Dict[str, Any]:
        """Rebuild P1 windows after restart from durable watch evidence.

        The deadline age comes from the persisted evidence timestamps, so a
        candidate that was already overdue restarts as explicitly overdue
        (serviced first by deadline order, or transitioned to the explicit
        missed state by the next sweep) — never as silently fresh.
        """

        now = float(self._now() if now_epoch is None else now_epoch)
        reconstructed = 0
        already_overdue = 0
        for entry in entries:
            status = str(getattr(entry, "status", "") or "")
            if status not in _ACTIVATED_STATES:
                continue
            tier = getattr(entry, "market_latest_tier", None)
            if tier not in P1_TIERS:
                continue
            mint = str(getattr(entry, "token_mint", "") or "")
            evidence = (
                _epoch(getattr(entry, "market_market_cap_observed_at_utc", None))
                or _epoch(getattr(entry, "market_price_observed_at_utc", None))
                or _epoch(getattr(entry, "last_observed_at_utc", None))
                or now)
            if self.mark_p1_due(mint, tier=str(tier), due_epoch=evidence,
                                now_epoch=now):
                reconstructed += 1
                if now - evidence > float(self.config.p1_deadline_seconds):
                    already_overdue += 1
        return {
            "reconstructed": reconstructed,
            "already_overdue": already_overdue,
        }

    def note_capacity_proof(self, verdict: Mapping[str, Any]) -> None:
        with self._lock:
            self._capacity_proof = dict(verdict)
            self._capacity_refused = not bool(
                verdict.get("p1_capacity_achievable"))

    def note_handoff(self, *, depth: Optional[int] = None,
                     oldest_age_seconds: Optional[float] = None,
                     drained: int = 0, rejected: int = 0) -> None:
        with self._lock:
            if depth is not None:
                self._handoff_depth = max(0, int(depth))
            if oldest_age_seconds is not None:
                self._handoff_oldest_age = max(0.0, float(oldest_age_seconds))
            self._counters["handoff_drained_total"] += max(0, int(drained))
            self._counters["handoff_rejected_total"] += max(0, int(rejected))

    def p1_backlog_pending(self) -> bool:
        """Cheap predicate for background work to yield to P1 pressure."""

        with self._lock:
            if any(not window.closed for window in self._p1_windows.values()):
                return True
        return self._jobs.qsize() > 0

    def _scheduler_state_locked(self) -> str:
        if self._capacity_refused:
            return SCHEDULER_CAPACITY_REFUSED
        if self._stop.is_set():
            workers_alive = any(w.is_alive() for w in self._workers)
            owner_alive = self._owner is not None and self._owner.is_alive()
            return (SCHEDULER_SHUTTING_DOWN
                    if workers_alive or owner_alive else SCHEDULER_STOPPED)
        if self._active_degraded_reasons():
            return SCHEDULER_DEGRADED
        return SCHEDULER_READY

    def scheduler_state(self) -> str:
        with self._lock:
            return self._scheduler_state_locked()

    def _note_degraded(self, reason: str) -> None:
        """Record ONE observation of ``reason`` at the current time.

        Replaces an append-only set.  The lifetime tally is kept so a run that
        recovered still discloses that it was degraded, without that history
        pinning the CURRENT state.
        """

        self._degraded_seen_epoch[str(reason)] = self._now()
        self._degraded_lifetime[str(reason)] = (
            self._degraded_lifetime.get(str(reason), 0) + 1)

    def _active_degraded_reasons(self) -> set:
        """Reasons observed recently enough to still describe the present."""

        cutoff = self._now() - DEGRADED_REASON_TTL_SECONDS
        return {reason for reason, seen in self._degraded_seen_epoch.items()
                if seen >= cutoff}

    # ---- worker and result owner --------------------------------------

    def _next_job(self, worker_index: int) -> Optional[Tuple[
            MarketJob, "queue.PriorityQueue[MarketJob]"]]:
        """Two-lane dispatch: P1 always first; P2/P3 never starve.

        Reserved workers block only on the fast lane.  General workers try
        the fast lane first (newly queued P1 work dispatches before any
        newly queued P2/P3 work), then serve the general lane with a short
        bounded wait — no busy spin, no indefinite starvation.
        """

        if worker_index < int(self.config.p1_reserved_workers):
            try:
                return self._jobs.get(timeout=0.1), self._jobs
            except queue.Empty:
                return None
        try:
            return self._jobs.get_nowait(), self._jobs
        except queue.Empty:
            pass
        try:
            return self._jobs_general.get(timeout=0.05), self._jobs_general
        except queue.Empty:
            pass
        try:
            return self._jobs.get(timeout=0.05), self._jobs
        except queue.Empty:
            return None

    def _job_superseded(self, job: MarketJob) -> bool:
        """Skip work whose binding is no longer the current candidate."""

        if job.field_group == FIELD_QUOTE_PRICE:
            return False
        with self._lock:
            for index, mint in enumerate(job.mints):
                view = self._views.get(mint)
                if view is None:
                    continue
                if view.quarantined or view.terminal_history or (
                        view.status in _TERMINAL_STATES):
                    continue
                if (view.candidate_id, view.generation) == job.bindings[index]:
                    return False
            return True

    def _worker_loop(self, worker_index: int = 0) -> None:
        while not self._stop.is_set():
            picked = self._next_job(worker_index)
            if picked is None:
                continue
            job, lane = picked
            self._note_dequeued(job)
            with self._lock:
                for mint in job.mints:
                    key = (mint, job.field_group)
                    self._queued_keys.discard(key)
                    self._inflight_keys.add(key)
            if self._stop.is_set():
                self._release_job_keys(job, inflight=True)
                self._counters["market_scheduler_jobs_cancelled"] += 1
                lane.task_done()
                continue
            # A newer generation supersedes stale queued work: never spend a
            # provider request on a binding that is no longer current.
            if self._job_superseded(job):
                self._release_job_keys(job, inflight=True)
                with self._lock:
                    self._counters["superseded_work_total"] += 1
                    self._counters["market_scheduler_jobs_cancelled"] += 1
                lane.task_done()
                continue
            # No P1 request may START after its candidate deadline.
            if job.deadline_mono is not None and self._mono() >= job.deadline_mono:
                self._release_job_keys(job, inflight=True)
                with self._lock:
                    self._counters["market_scheduler_jobs_cancelled"] += 1
                try:
                    self._results.put(
                        (job, None, "P1_DEADLINE_EXHAUSTED"), timeout=0.5)
                except queue.Full:
                    self._note_degraded(MARKET_SCHEDULER_OVERLOADED)
                lane.task_done()
                continue
            error: Optional[str] = None
            result: Any = None
            with self._inflight_gate:
                # Check again after waiting for the bounded in-flight permit.
                if self._stop.is_set():
                    self._release_job_keys(job, inflight=True)
                    self._counters["market_scheduler_jobs_cancelled"] += 1
                    lane.task_done()
                    continue
                with self._lock:
                    self._provider_requests_started += 1
                    self._provider_requests_inflight += 1
                    self._max_observed_inflight = max(
                        self._max_observed_inflight,
                        self._provider_requests_inflight)
                try:
                    with self._ticket_ownership(job):
                        if job.field_group == FIELD_PRICE_MC and len(job.mints) > 1:
                            self._counters["market_price_batch_requests"] += 1
                            self._counters["market_price_batch_mints"] += len(job.mints)
                            result = self._batch_price_fetch(job.mints)  # type: ignore[misc]
                        elif job.field_group in (FIELD_PRICE_MC, FIELD_QUOTE_PRICE):
                            self._counters["market_price_single_requests"] += 1
                            result = self._call_fetch(
                                self._price_fetch, job,
                                accepts_deadline=self._price_accepts_deadline)
                        else:
                            self._counters["market_overview_requests"] += 1
                            result = self._call_fetch(
                                self._overview_fetch, job,
                                accepts_deadline=self._overview_accepts_deadline)
                except BaseException as exc:
                    error = f"PROVIDER_{type(exc).__name__.upper()}"
                finally:
                    self._charge_job_tickets(job)
                    with self._lock:
                        self._provider_requests_inflight -= 1
            # Scheduled stale-price work gets the same authenticated fallback
            # as send-time priority work.  This happens after the primary
            # ticket-ownership scope has closed, so the Helius account ticket
            # remains the separately reconciled FALLBACK origin and can never
            # be charged to this Birdeye scheduler job.
            if (job.field_group == FIELD_PRICE_MC
                    and isinstance(result, Mapping)
                    and result.get("_market_failure_reason") == "PROVIDER_STALE"):
                with self._lock:
                    self._counters["fresh_market_fallback_attempts_total"] += 1
                if self._fresh_fallback_fetch is None:
                    result = {
                        **dict(result),
                        "_fresh_fallback_reason": (
                            "FRESH_FALLBACK_CAPABILITY_UNAVAILABLE"),
                    }
                    with self._lock:
                        self._counters[
                            "fresh_market_fallback_capability_unavailable_total"] += 1
                        self._counters[
                            "fresh_market_fallback_failed_total"] += 1
                else:
                    try:
                        fallback_outcome = self._fresh_fallback_fetch(
                            job.mints[0],
                            timeout_seconds=max(
                                0.05,
                                self.config.effective_p1_attempt_timeout_seconds()),
                        )
                    except BaseException as exc:
                        fallback_outcome = None
                        fallback_reason = (
                            f"FRESH_FALLBACK_{type(exc).__name__.upper()}")
                    else:
                        fallback_reason = str(
                            getattr(fallback_outcome, "reason", None)
                            or (fallback_outcome.get("reason")
                                if isinstance(fallback_outcome, Mapping) else None)
                            or "FRESH_FALLBACK_OTHER_FAILURE")
                    fallback_observation = (
                        getattr(fallback_outcome, "observation", None)
                        if fallback_outcome is not None
                        and not isinstance(fallback_outcome, Mapping)
                        else (fallback_outcome.get("observation", fallback_outcome)
                              if isinstance(fallback_outcome, Mapping) else None))
                    fallback_accepted = bool(
                        getattr(fallback_outcome, "accepted", False)
                        if fallback_outcome is not None
                        and not isinstance(fallback_outcome, Mapping)
                        else (fallback_outcome.get("accepted")
                              if isinstance(fallback_outcome, Mapping) else False))
                    if fallback_accepted and isinstance(
                            fallback_observation, Mapping):
                        result = {
                            "_fresh_fallback_observation": dict(
                                fallback_observation),
                            "_fresh_fallback_reason": fallback_reason,
                        }
                    else:
                        result = {
                            **dict(result),
                            "_fresh_fallback_reason": fallback_reason,
                        }
                        with self._lock:
                            self._counters[
                                "fresh_market_fallback_failed_total"] += 1
                with self._lock:
                    self._fresh_fallback_last_result[job.mints[0]] = str(
                        result.get("_fresh_fallback_reason"))
            # Bounded result queue. A full result queue is an overload failure,
            # never permission to block a worker forever.
            try:
                self._results.put((job, result, error), timeout=0.5)
            except queue.Full:
                self._note_degraded(MARKET_SCHEDULER_OVERLOADED)
                self._release_job_keys(job, inflight=True)
            finally:
                lane.task_done()

    def _call_fetch(self, fetch_fn: Optional[Callable[..., Any]],
                    job: MarketJob, *, accepts_deadline: bool) -> Any:
        if fetch_fn is None:
            return None
        if accepts_deadline and job.deadline_mono is not None:
            return fetch_fn(job.mints[0], deadline_monotonic=job.deadline_mono)
        return fetch_fn(job.mints[0])

    def _owner_loop(self) -> None:
        while True:
            try:
                item = self._results.get(timeout=0.1)
            except queue.Empty:
                if self._stop.is_set() and not any(worker.is_alive() for worker in self._workers):
                    return
                continue
            if item is None:
                self._results.task_done()
                return
            job, result, error = item
            try:
                self._consume_result(job, result, error)
            finally:
                # Every job that reaches the owner is SETTLED here, exactly
                # once, whatever its outcome. Only the success paths bump
                # jobs_completed, so before this counter existed a provider
                # error or a malformed response left a job counted as
                # submitted and nothing else -- 293 of 1,131 jobs in the
                # 2026-07-29 run looked lost when they had in fact all been
                # answered and rejected.
                self._counters["market_scheduler_jobs_settled"] += 1
                self._release_job_keys(job, inflight=True)
                self._results.task_done()

    def _consume_result(self, job: MarketJob, result: Any, error: Optional[str]) -> None:
        if self._stop.is_set():
            self._counters["market_scheduler_late_results_rejected"] += len(job.mints)
            return
        if isinstance(result, MarketObservation):
            self.apply_observation(result)
            return
        if error is not None:
            for mint in job.mints:
                self._record_failure(mint, job.field_group, error)
            return
        if isinstance(result, Mapping) and isinstance(
                result.get("_fresh_fallback_observation"), Mapping):
            accepted = self._apply_authenticated_fallback(
                job.mints[0], job.bindings[0],
                result["_fresh_fallback_observation"])
            if accepted:
                with self._lock:
                    self._counters[
                        "fresh_market_fallback_succeeded_total"] += 1
                return
            with self._lock:
                self._counters[
                    "fresh_market_fallback_failed_total"] += 1
            self._record_failure(
                job.mints[0], job.field_group,
                "FRESH_FALLBACK_OBSERVATION_REJECTED")
            return
        if isinstance(result, Mapping) and isinstance(
                result.get("_market_failure_reason"), str):
            reason = str(result["_market_failure_reason"])
            for mint in job.mints:
                self._record_failure(mint, job.field_group, reason)
            return
        if job.field_group == FIELD_QUOTE_PRICE:
            if not isinstance(result, Mapping):
                self._record_failure(job.mints[0], FIELD_QUOTE_PRICE,
                                     "PROVIDER_RESULT_MISSING")
                return
            price = _positive_decimal(result.get("current_price"))
            if price is None or result.get("mint") not in (None, job.mints[0]):
                self._record_failure(job.mints[0], FIELD_QUOTE_PRICE,
                                     "PROVIDER_WRONG_OR_MALFORMED_QUOTE")
                return
            observed_at = str(
                result.get("provider_timestamp_utc")
                or result.get("fetched_at_utc") or _iso(self._now()))
            if self._quote_price_apply is not None:
                try:
                    self._quote_price_apply(
                        job.mints[0], _decimal_text(price) or "", observed_at)
                except Exception:
                    self._record_failure(job.mints[0], FIELD_QUOTE_PRICE,
                                         "QUOTE_PRICE_APPLY_FAILED")
                    return
            self._counters["market_scheduler_jobs_completed"] += 1
            return
        if len(job.mints) > 1:
            if not isinstance(result, Mapping):
                # A failed batch fabricates success for NO member: every mint
                # is recorded as an explicit failure and stays unresolved.
                for mint in job.mints:
                    self._record_failure(mint, job.field_group, MARKET_BATCH_PARTIAL)
                self._counters["market_batch_partial"] += 1
                self._counters["market_price_batch_failed"] += 1
                return
            requested = set(job.mints)
            for response_mint in result:
                if response_mint not in requested:
                    self._counters["market_wrong_mint_rejected"] += 1
            missing: List[str] = []
            for index, mint in enumerate(job.mints):
                row = result.get(mint)
                if not isinstance(row, Mapping):
                    missing.append(mint)
                    continue
                if row.get("mint") not in (None, mint):
                    self._counters["market_wrong_mint_rejected"] += 1
                    continue
                self._apply_provider_mapping(job, index, mint, row, SOURCE_PAID_BATCH)
                self._counters["market_price_batch_mints_resolved"] += 1
            if missing:
                self._counters["market_batch_partial"] += 1
                self._counters["market_price_batch_partial"] += 1
                self._note_degraded(MARKET_BATCH_PARTIAL)
                # Each omitted mint remains explicitly pending. The next
                # planner pass creates a targeted single fallback after this
                # batch releases its in-flight keys; it can never overlap the
                # batch for the same deadline.
                for mint in missing:
                    self._record_failure(mint, FIELD_PRICE_MC, MARKET_BATCH_PARTIAL)
            return
        if not isinstance(result, Mapping):
            self._record_failure(job.mints[0], job.field_group, "PROVIDER_RESULT_MISSING")
            return
        if result.get("mint") not in (None, job.mints[0]):
            self._counters["market_wrong_mint_rejected"] += 1
            self._record_failure(job.mints[0], job.field_group, "PROVIDER_WRONG_MINT")
            return
        self._apply_provider_mapping(job, 0, job.mints[0], result, SOURCE_PAID_SINGLE)

    def _apply_provider_mapping(self, job: MarketJob, index: int, mint: str,
                                result: Mapping[str, Any], source: str) -> None:
        source_ts = (_epoch(result.get("provider_timestamp_utc"))
                     or _epoch(result.get("fetched_at_utc")) or self._now())
        ingestion = self._now()
        values = dict(result)
        evidence = _digest({
            "mint": mint,
            "candidate_id": job.bindings[index][0],
            "generation": job.bindings[index][1],
            "source": source,
            "source_timestamp": source_ts,
            "field_group": job.field_group,
            "request_id": job.request_id,
            "values": values,
        })
        observation = MarketObservation(
            mint=mint,
            candidate_id=job.bindings[index][0],
            generation=job.bindings[index][1],
            source=source,
            source_timestamp=source_ts,
            ingestion_timestamp=ingestion,
            field_group=job.field_group,
            observation_sequence=self._next_sequence(),
            source_evidence_digest=evidence,
            request_id=job.request_id,
            values=values,
        )
        self.apply_observation(observation)

    def _record_failure(self, mint: str, field_group: str, reason: str) -> None:
        with self._lock:
            state = self._state.setdefault(mint, _MarketState())
            state.failure_count += 1
            state.last_request_error = str(reason)
            if "TIMEOUT" in str(reason) or str(reason) == "P1_DEADLINE_EXHAUSTED":
                self._counters["provider_timeout_total"] += 1
            else:
                self._counters["provider_error_total"] += 1
        if self._failure_callback is not None:
            try:
                self._failure_callback(mint, field_group, str(reason))
            except Exception:
                pass

    def _release_job_keys(self, job: MarketJob, *, inflight: bool) -> None:
        with self._lock:
            target = self._inflight_keys if inflight else self._queued_keys
            for mint in job.mints:
                target.discard((mint, job.field_group))

    # ---- observation application -------------------------------------

    def _next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def submit_grpc(self, observation: MarketObservation) -> bool:
        if observation.source != SOURCE_GRPC or observation.field_group != FIELD_PRICE_MC:
            self._counters["market_grpc_observations_rejected"] += 1
            return False
        if self._stop.is_set() or not self._accepting:
            self._counters["market_grpc_observations_rejected"] += 1
            return False
        if self._started:
            # The gRPC source never performs watch mutation itself. It hands the
            # sealed observation to the same authoritative result owner.
            pseudo = MarketJob(
                sort_key=(PRIORITY_P0, observation.source_timestamp,
                          observation.source_timestamp, observation.mint,
                          FIELD_PRICE_MC, observation.observation_sequence),
                request_id=observation.request_id or "grpc-event",
                field_group=FIELD_PRICE_MC,
                mints=(observation.mint,),
                bindings=((observation.candidate_id, observation.generation),),
                submitted_at=observation.ingestion_timestamp,
                priority=PRIORITY_P0,
            )
            try:
                self._results.put_nowait((pseudo, observation, None))
                return True
            except queue.Full:
                self._note_degraded(MARKET_SCHEDULER_OVERLOADED)
                self._counters["market_grpc_observations_rejected"] += 1
                return False
        return self.apply_observation(observation)

    def submit_trusted_reserve(self, payload: Mapping[str, Any]) -> bool:
        """Validate the reserve seal and bind it to the current candidate.

        The gRPC decoder supplies source-event identity and reserve trust; this
        boundary adds the current candidate/generation binding.  A wrong or
        stale candidate can therefore never receive an otherwise valid event.
        """

        if not isinstance(payload, Mapping):
            self._counters["market_grpc_observations_rejected"] += 1
            return False
        mint = payload.get("mint")
        evidence = payload.get("source_evidence_digest")
        seal = payload.get("observation_seal_digest")
        ingestion_iso = payload.get("ingestion_timestamp")
        outer_instruction = payload.get("outer_instruction_index")
        inner_instruction = payload.get("inner_instruction_index")
        flattened_instruction = payload.get("flattened_instruction_index")
        slot = payload.get("slot")
        event_index = payload.get("event_index")
        transaction_signature = payload.get("transaction_signature")
        expected_evidence = _digest({
            "schema_version": payload.get("schema_version"),
            "mint": mint,
            "pool_address": payload.get("pool_address"),
            "base_vault": payload.get("base_vault"),
            "quote_vault": payload.get("quote_vault"),
            "quote_mint": payload.get("quote_mint"),
            "base_decimals": payload.get("base_decimals"),
            "quote_decimals": payload.get("quote_decimals"),
            "base_supply": payload.get("base_supply"),
            "raw_quote_reserves": payload.get("raw_quote_reserves"),
            "virtual_quote_reserves": payload.get("virtual_quote_reserves"),
            "effective_quote_reserves": payload.get("effective_quote_reserves"),
            "base_reserves": payload.get("base_reserves"),
            "transaction_signature": transaction_signature,
            "slot": slot,
            "outer_instruction_index": outer_instruction,
            "inner_instruction_index": inner_instruction,
            "flattened_instruction_index": flattened_instruction,
            "event_index": event_index,
            "source_timestamp": payload.get("source_timestamp"),
            "migration_proof_digest": payload.get("migration_proof_digest"),
            "transaction_succeeded": payload.get("transaction_succeeded"),
            "source_event_proven": payload.get("source_event_proven"),
        })
        expected_seal = _digest({
            "seal_version": payload.get("observation_seal_version"),
            "source_evidence_digest": evidence,
            "ingestion_timestamp": ingestion_iso,
        })
        if not (
            isinstance(mint, str) and mint
            and payload.get("reserve_trusted_for_routing") is True
            and payload.get("transaction_succeeded") is True
            and payload.get("source_event_proven") is True
            and payload.get("pool_replacement_conflict") is False
            and isinstance(transaction_signature, str) and transaction_signature
            and isinstance(slot, int) and not isinstance(slot, bool) and slot >= 0
            and isinstance(event_index, int) and not isinstance(event_index, bool)
            and event_index >= 0
            and isinstance(evidence, str) and evidence == expected_evidence
            and isinstance(seal, str) and seal == expected_seal
            and isinstance(outer_instruction, int)
            and not isinstance(outer_instruction, bool) and outer_instruction >= 0
            and (inner_instruction is None
                 or (isinstance(inner_instruction, int)
                     and not isinstance(inner_instruction, bool)
                     and inner_instruction >= 0))
            and isinstance(flattened_instruction, int)
            and not isinstance(flattened_instruction, bool)
            and flattened_instruction >= 0
            and _positive_decimal(payload.get("current_price")) is not None
            and _positive_decimal(payload.get("current_market_cap_usd")) is not None
        ):
            self._counters["market_grpc_observations_rejected"] += 1
            return False
        with self._lock:
            view = self._views.get(mint)
        if view is None:
            self._counters["market_grpc_observations_rejected"] += 1
            return False
        source_ts = _epoch(payload.get("source_timestamp"))
        ingestion_ts = _epoch(ingestion_iso)
        if source_ts is None or ingestion_ts is None:
            self._counters["market_grpc_observations_rejected"] += 1
            return False
        observation = MarketObservation(
            mint=mint,
            candidate_id=view.candidate_id,
            generation=view.generation,
            source=SOURCE_GRPC,
            source_timestamp=source_ts,
            ingestion_timestamp=ingestion_ts,
            field_group=FIELD_PRICE_MC,
            observation_sequence=self._next_sequence(),
            source_evidence_digest=evidence,
            request_id=(f"grpc:{slot}:{transaction_signature}:"
                        f"{outer_instruction}:{inner_instruction}:"
                        f"{flattened_instruction}:{event_index}"),
            values={
                "current_price": payload.get("current_price"),
                "current_market_cap_usd": payload.get("current_market_cap_usd"),
                "pumpswap_reserve": dict(payload),
            },
            source_order=(
                int(slot),
                int(outer_instruction),
                -1 if inner_instruction is None else int(inner_instruction),
                int(flattened_instruction),
                int(event_index),
            ),
        )
        return self.submit_grpc(observation)

    def _consume_grpc_direct(self, observation: MarketObservation) -> bool:
        return self.apply_observation(observation)

    def apply_observation(self, observation: MarketObservation) -> bool:
        now = float(self._now())
        with self._lock:
            view = self._views.get(observation.mint)
            if view is None:
                self._counters["market_expired_results_rejected"] += 1
                return False
            if view.quarantined:
                self._counters["market_quarantined_results_rejected"] += 1
                return False
            if view.terminal_history or view.status in _TERMINAL_STATES:
                self._counters["market_terminal_results_rejected"] += 1
                return False
            if (view.candidate_id != observation.candidate_id
                    or view.generation != observation.generation):
                self._counters["market_scheduler_generation_mismatch_rejected"] += 1
                self._counters["stale_result_total"] += 1
                return False
            if self._stop.is_set():
                self._counters["market_scheduler_late_results_rejected"] += 1
                return False
            if observation.source == SOURCE_GRPC and (
                    now - observation.source_timestamp > self.config.grpc_max_age_seconds
                    or observation.source_timestamp > now + 2.0):
                self._counters["market_grpc_observations_rejected"] += 1
                return False
            state = self._state.setdefault(observation.mint, _MarketState())
            latest_seq = state.latest_sequence.get(observation.field_group, -1)
            if observation.observation_sequence <= latest_seq:
                self._counters["market_scheduler_late_results_rejected"] += 1
                self._counters["duplicate_result_total"] += 1
                return False
            outcome = self._apply_values_locked(state, observation)
            if outcome == APPLY_OUTCOME_MALFORMED:
                self._counters["market_malformed_results_rejected"] += 1
                if observation.source == SOURCE_GRPC:
                    self._counters["market_grpc_observations_rejected"] += 1
                return False
            if outcome == APPLY_OUTCOME_UNCHANGED:
                # A valid response that is not NEWER than what is stored.  The
                # provider answered correctly, so the job is COMPLETE and the
                # failure streak clears -- that is the whole fix: a quiet token
                # whose provider timestamp never advances used to accumulate
                # "malformed" rejections and get driven into recovery backoff
                # while the provider was perfectly healthy.
                #
                # Nothing was applied, so the observation is NOT propagated and
                # the caller still sees False -- an out-of-order or duplicate
                # value must never look applied.  No timestamp is written, so
                # freshness, all_present, market_state and every eligibility
                # decision derived from them stay byte-identical to before.
                self._counters["market_results_unchanged"] += 1
                self._counters["market_scheduler_jobs_completed"] += 1
                state.failure_count = 0
                state.last_request_error = None
                return False
            state.latest_sequence[observation.field_group] = observation.observation_sequence
            state.failure_count = 0
            state.last_request_error = None
            snapshot = self._snapshot_locked(observation.mint, now=now)
            if observation.source == SOURCE_GRPC:
                self._counters["market_grpc_price_observations"] += 1
            self._counters["market_scheduler_jobs_completed"] += 1
        if self._apply_callback is not None:
            try:
                self._apply_callback(observation, snapshot)
            except Exception:
                # Application callbacks never crash the owner. The cache stays
                # valid and the callback can consume it on the next heartbeat.
                return False
        if observation.source == SOURCE_GRPC:
            completed_at = float(self._now())
            latency_ms = max(0.0, (completed_at - observation.source_timestamp) * 1000.0)
            with self._lock:
                self._latencies["market_grpc_to_watch_latency_ms"].append(latency_ms)
                del self._latencies["market_grpc_to_watch_latency_ms"][:-256]
                if latency_ms > self.config.grpc_watch_apply_slo_seconds * 1000.0:
                    self._note_degraded(MARKET_LATENCY_SLO_BREACHED)
            self.note_grpc_avoidance(1)
        if observation.field_group == FIELD_OVERVIEW:
            # A fresh overview may complete an open P1 window's evidence:
            # wake the dispatch loop instead of waiting out the watch sleep.
            with self._lock:
                p1_waiting = any(
                    not window.closed and window.mint == observation.mint
                    for window in self._p1_windows.values())
            if p1_waiting:
                self._fire_waker()
        return True

    def _apply_values_locked(self, state: _MarketState,
                             observation: MarketObservation) -> str:
        """Classify one observation against the stored state.

        Returns a closed-set outcome, never a bare bool.  ``UNCHANGED`` and
        ``MALFORMED`` are FUNDAMENTALLY different answers that this function
        used to collapse into ``False``:

        - ``MALFORMED`` -- the response carried no usable positive value at all.
          A real provider/schema fault.
        - ``UNCHANGED`` -- the response carried valid values that are simply not
          NEWER than what is already stored.  This is the normal answer for a
          token that has not traded since the last poll: the provider timestamp
          does not advance, so ``_newer`` is False.  The provider is HEALTHY and
          the job is COMPLETE; only the data is not fresher.

        Collapsing the second case into ``False`` made 326 successful polls in
        the 2026-07-31 run count as ``market_malformed_results_rejected`` and
        skipped the apply callback entirely, so nothing ever recorded a
        successful attempt for a quiet token.  Freshness itself is NOT decided
        here -- no timestamp is written for UNCHANGED, so an genuinely stale
        token stays stale and stays unsendable.
        """

        values = observation.values
        changed = False
        observation_key = (
            observation.source_evidence_digest,
            int(observation.observation_sequence),
        )
        if observation.field_group == FIELD_PRICE_MC:
            price = _positive_decimal(values.get("current_price"))
            market_cap = _positive_decimal(values.get("current_market_cap_usd"))
            if price is None and market_cap is None:
                return APPLY_OUTCOME_MALFORMED
            if price is not None and self._newer(
                    observation, state.price_timestamp, state.price_source,
                    state.price_source_order):
                state.price = _decimal_text(price)
                state.price_timestamp = observation.source_timestamp
                state.price_source = observation.source
                state.price_source_order = observation.source_order
                state.price_observation_key = observation_key
                changed = True
            if market_cap is not None and self._newer(
                    observation, state.market_cap_timestamp, state.market_cap_source,
                    state.market_cap_source_order):
                state.market_cap = _decimal_text(market_cap)
                state.market_cap_timestamp = observation.source_timestamp
                state.market_cap_source = observation.source
                state.market_cap_source_order = observation.source_order
                state.market_cap_observation_key = observation_key
                changed = True
        else:
            # Overview may refresh market cap and liquidity, but it never
            # freshens or overwrites the independent price timestamp.
            market_cap = _positive_decimal(values.get("current_market_cap_usd"))
            liquidity = _positive_decimal(values.get("liquidity_usd"))
            if market_cap is None and liquidity is None:
                return APPLY_OUTCOME_MALFORMED
            if market_cap is not None and self._newer(
                    observation, state.market_cap_timestamp, state.market_cap_source,
                    state.market_cap_source_order):
                state.market_cap = _decimal_text(market_cap)
                state.market_cap_timestamp = observation.source_timestamp
                state.market_cap_source = observation.source
                state.market_cap_source_order = observation.source_order
                state.market_cap_observation_key = observation_key
                changed = True
            if liquidity is not None and self._newer(
                    observation, state.liquidity_timestamp, state.liquidity_source,
                    state.liquidity_source_order):
                state.liquidity = _decimal_text(liquidity)
                state.liquidity_timestamp = observation.source_timestamp
                state.liquidity_source = observation.source
                state.liquidity_source_order = observation.source_order
                changed = True
        reserve_payload = values.get("pumpswap_reserve")
        if isinstance(reserve_payload, Mapping):
            state.pumpswap_reserve = dict(reserve_payload)
        return APPLY_OUTCOME_APPLIED if changed else APPLY_OUTCOME_UNCHANGED

    @staticmethod
    def _newer(observation: MarketObservation, current_timestamp: Optional[float],
               current_source: Optional[str],
               current_source_order: Tuple[int, ...]) -> bool:
        if current_timestamp is None or observation.source_timestamp > current_timestamp:
            return True
        if observation.source_timestamp < current_timestamp:
            return False
        # Equal event time: trusted gRPC price wins over a paid response; an
        # overview remains independent because it never writes price.
        if observation.source == SOURCE_GRPC and current_source != SOURCE_GRPC:
            return True
        return bool(
            observation.source == SOURCE_GRPC
            and current_source == SOURCE_GRPC
            and observation.source_order
            and observation.source_order > current_source_order)

    # ---- snapshots / observability ------------------------------------

    def _snapshot_locked(self, mint: str, *, now: float) -> Dict[str, Any]:
        state = self._state.setdefault(mint, _MarketState())
        view = self._views.get(mint)
        if view is None:
            return {"token_mint": mint, "all_present": False,
                    "market_state": "MARKET_UNAVAILABLE"}
        price_ttl, overview_ttl = self._ttls(view)
        price_fresh = bool(
            state.price is not None and state.price_timestamp is not None
            and now - state.price_timestamp <= price_ttl)
        mc_fresh = bool(
            state.market_cap is not None and state.market_cap_timestamp is not None
            and now - state.market_cap_timestamp <= price_ttl)
        liquidity_fresh = bool(
            state.liquidity is not None and state.liquidity_timestamp is not None
            and now - state.liquidity_timestamp <= overview_ttl)
        complete = price_fresh and mc_fresh and liquidity_fresh
        recovery_wait = bool(
            not complete and view.market_state == "MARKET_RECOVERY_BACKOFF")
        # True only when the exposed price and market cap are two halves of
        # ONE provider response.  Any consumer that treats the pair as a
        # single economic observation (the central ATH store, and through it
        # every derived supply) must read this first.
        pair_coherent = bool(
            state.price_observation_key is not None
            and state.price_observation_key == state.market_cap_observation_key)
        price_interval, overview_interval, cadence = self._refresh_intervals(view)
        return {
            "token_mint": mint,
            "current_price": state.price,
            "current_market_cap_usd": state.market_cap,
            "liquidity_usd": state.liquidity,
            "market_pair_coherent": pair_coherent,
            "market_cadence_class": cadence,
            "market_price_refresh_interval_seconds": price_interval,
            "market_overview_refresh_interval_seconds": overview_interval,
            "market_price_ttl_seconds": price_ttl,
            "market_overview_ttl_seconds": overview_ttl,
            "price_observed_at_utc": (
                _iso(state.price_timestamp) if state.price_timestamp is not None else None),
            "market_cap_observed_at_utc": (
                _iso(state.market_cap_timestamp)
                if state.market_cap_timestamp is not None else None),
            "liquidity_observed_at_utc": (
                _iso(state.liquidity_timestamp)
                if state.liquidity_timestamp is not None else None),
            "price_source": state.price_source,
            "market_cap_source": state.market_cap_source,
            "liquidity_source": state.liquidity_source,
            "price_fresh": price_fresh,
            "market_cap_fresh": mc_fresh,
            "liquidity_fresh": liquidity_fresh,
            "all_present": complete,
            "market_state": (
                "MARKET_READY" if complete
                else "MARKET_RECOVERY_BACKOFF" if recovery_wait
                else "MARKET_INCOMPLETE"),
            "market_reason_code": (
                "REQUIRED_FIELDS_FRESH" if complete
                else view.market_reason_code if recovery_wait
                else "INDEPENDENT_FIELD_STALE"),
            "next_market_refresh_at_utc": (
                _iso(view.next_recovery_epoch)
                if recovery_wait and view.next_recovery_epoch is not None else None),
            "market_context_fetched_at_utc": (
                _iso(min(timestamp for timestamp in (
                    state.price_timestamp,
                    state.market_cap_timestamp,
                    state.liquidity_timestamp,
                ) if timestamp is not None))
                if any(timestamp is not None for timestamp in (
                    state.price_timestamp,
                    state.market_cap_timestamp,
                    state.liquidity_timestamp,
                )) else None),
            "provider_timestamp_utc": (
                _iso(state.price_timestamp) if state.price_timestamp is not None else None),
            "basis": "SCHEDULED_MARKET_PRESENT" if complete else "SCHEDULED_MARKET_INCOMPLETE",
            "last_request_error": state.last_request_error,
            "projected_tier": state.projected_tier,
            "projected_drawdown_pct": state.projected_drawdown_pct,
            "attempts": [],
            "endpoint_attempts": {},
            "pumpswap_reserve": dict(state.pumpswap_reserve),
        }

    def snapshot(self, mint: str, *, now_epoch: Optional[float] = None) -> Dict[str, Any]:
        now = float(self._now() if now_epoch is None else now_epoch)
        with self._lock:
            return dict(self._snapshot_locked(str(mint), now=now))

    # ---- send-time priority refresh ------------------------------------

    def priority_refresh(
        self, mint: str, *, timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """ONE bounded, single-candidate provider refresh for send authorization.

        The maintenance planner deliberately honours TTLs and recovery
        backoff, which is correct for background polling and wrong for a
        candidate that is otherwise fully dispatchable RIGHT NOW.  This
        performs at most one request per required field plane, on the
        CALLING thread, so the refreshed values are visible to the same
        candidate evaluation that asked for them (the async worker pool
        cannot make that guarantee).

        It changes nothing else about the contract:

        * results are applied through the ordinary ``apply_observation``
          path, so every mint/candidate/generation binding, sequence
          ordering and freshness rule still applies;
        * it never composes, never renders, never reserves a ledger line
          and never reaches a transport;
        * a failure leaves the candidate RETAINED -- no terminal
          transition, and ATH, provenance, tier history and watch state are
          untouched.

        Returns a closed-set result plus the post-refresh snapshot.
        """

        token = str(mint or "")
        deadline = float(
            self.config.effective_p1_attempt_timeout_seconds()
            if timeout_seconds is None else timeout_seconds)
        now_mono = float(self._mono())
        with self._lock:
            self._counters["priority_refresh_requested_total"] += 1
            if token in self._priority_refresh_inflight:
                self._counters["priority_refresh_coalesced_total"] += 1
                return self._priority_refresh_result(
                    token, REFRESH_ALREADY_IN_FLIGHT, requests=0)
            if self._stop.is_set() or not self._accepting:
                return self._priority_refresh_result(
                    token, REFRESH_PERMANENT_FAILURE, requests=0,
                    detail="SCHEDULER_STOPPED")
            if int(self._priority_refresh_permanent.get(token, 0)) >= (
                    PRIORITY_REFRESH_MAX_PERMANENT_FAILURES):
                # Bounded by construction: a mint whose refresh is
                # structurally impossible is never retried in a loop.
                return self._priority_refresh_result(
                    token, REFRESH_PERMANENT_FAILURE, requests=0,
                    detail="PERMANENT_FAILURE_LIMIT_REACHED")
            view = self._views.get(token)
            if view is None or self._price_fetch is None:
                self._priority_refresh_permanent[token] = int(
                    self._priority_refresh_permanent.get(token, 0)) + 1
                self._counters["priority_refresh_permanent_total"] += 1
                return self._priority_refresh_result(
                    token, REFRESH_PERMANENT_FAILURE, requests=0,
                    detail=("CANDIDATE_NOT_TRACKED" if view is None
                            else "PRICE_FETCH_UNAVAILABLE"))
            next_allowed = self._priority_refresh_next_allowed.get(token)
            if next_allowed is not None and now_mono < next_allowed:
                self._counters["priority_refresh_rate_limited_total"] += 1
                return self._priority_refresh_result(
                    token, REFRESH_RATE_LIMITED, requests=0,
                    retry_after_seconds=max(0.0, next_allowed - now_mono))
            if self._budget_exhausted_locked():
                self._note_degraded(MARKET_PROVIDER_BUDGET_EXHAUSTED)
                self._counters["priority_refresh_rate_limited_total"] += 1
                return self._priority_refresh_result(
                    token, REFRESH_RATE_LIMITED, requests=0,
                    detail=MARKET_PROVIDER_BUDGET_EXHAUSTED)
            self._priority_refresh_inflight.add(token)
            binding = (view.candidate_id, view.generation)
        requests = 0
        rate_limited = False
        failure_outcomes: List[str] = []
        failure_details: List[str] = []
        fresh_price_accepted = False
        fallback_reason: Optional[str] = None
        try:
            for field_group, fetch_fn in (
                (FIELD_PRICE_MC, self._price_fetch),
                (FIELD_OVERVIEW, self._overview_fetch),
            ):
                if fetch_fn is None:
                    continue
                job = self._priority_job(
                    token, field_group, binding, deadline=deadline)
                with self._lock:
                    self._provider_requests_started += 1
                    self._counters[
                        "priority_refresh_provider_requests_total"] += 1
                    if field_group == FIELD_PRICE_MC:
                        self._counters["market_price_single_requests"] += 1
                    else:
                        self._counters["market_overview_requests"] += 1
                requests += 1
                try:
                    with self._ticket_ownership(job, priority_refresh=True):
                        result = self._call_fetch(
                            fetch_fn, job,
                            accepts_deadline=(
                                self._price_accepts_deadline
                                if field_group == FIELD_PRICE_MC
                                else self._overview_accepts_deadline))
                except BaseException as exc:  # provider fault, not ours
                    self._charge_job_tickets(job)
                    detail = f"PROVIDER_{type(exc).__name__.upper()}"
                    if _looks_rate_limited(exc):
                        rate_limited = True
                        failure_outcomes.append(BACKOFF_ACTIVE)
                    else:
                        failure_outcomes.append(PROVIDER_ERROR)
                    failure_details.append(detail)
                    self._record_failure(token, field_group, detail)
                    continue
                self._charge_job_tickets(job)
                if isinstance(result, MarketObservation):
                    # The ONE authoritative apply path: same binding,
                    # sequence and freshness rules as any worker result.
                    self.apply_observation(result)
                    if result.field_group == FIELD_PRICE_MC:
                        fresh_price_accepted = True
                elif isinstance(result, Mapping):
                    failure = result.get("_market_failure_reason")
                    if isinstance(failure, str):
                        if failure == "PROVIDER_STALE":
                            classified = STALE_PROVIDER_TIMESTAMP
                        elif "WRONG_MINT" in failure or "MINT_MISMATCH" in failure:
                            classified = WRONG_MINT
                        elif ("MALFORMED" in failure or "MISSING" in failure
                              or failure == "PROVIDER_RESULT_MISSING"):
                            classified = MISSING_REQUIRED_FIELDS
                        elif ("RATE_LIMIT" in failure or "BACKOFF" in failure
                              or "BUDGET" in failure):
                            classified = BACKOFF_ACTIVE
                            rate_limited = True
                        else:
                            classified = PROVIDER_ERROR
                        failure_outcomes.append(classified)
                        failure_details.append(failure)
                        self._record_failure(token, field_group, failure)
                    else:
                        # Synchronous priority work must use the same mapping
                        # -> observation -> apply path as the async owner.  The
                        # former generic NO_OBSERVATION branch discarded every
                        # real production transport mapping here.
                        self._consume_result(job, result, None)
                        if field_group == FIELD_PRICE_MC:
                            fresh_price_accepted = True
                else:
                    failure_outcomes.append(MISSING_REQUIRED_FIELDS)
                    failure_details.append("PROVIDER_RESULT_MISSING")
                    self._record_failure(
                        token, field_group, "PROVIDER_RESULT_MISSING")

            # A stale primary price is evidence, not a generic provider miss.
            # It triggers exactly one authenticated account snapshot before
            # any per-mint backoff is installed.
            if STALE_PROVIDER_TIMESTAMP in failure_outcomes:
                with self._lock:
                    self._counters["fresh_market_fallback_attempts_total"] += 1
                fetch_fallback = self._fresh_fallback_fetch
                if fetch_fallback is None:
                    fallback_reason = "FRESH_FALLBACK_CAPABILITY_UNAVAILABLE"
                    with self._lock:
                        self._counters[
                            "fresh_market_fallback_capability_unavailable_total"] += 1
                        self._counters[
                            "fresh_market_fallback_failed_total"] += 1
                else:
                    try:
                        fallback_outcome = fetch_fallback(
                            token, timeout_seconds=max(0.05, deadline))
                    except BaseException as exc:
                        fallback_outcome = None
                        fallback_reason = (
                            f"FRESH_FALLBACK_{type(exc).__name__.upper()}")
                    if fallback_outcome is not None:
                        fallback_reason = str(
                            getattr(fallback_outcome, "reason", None)
                            or (fallback_outcome.get("reason")
                                if isinstance(fallback_outcome, Mapping) else None)
                            or "FRESH_FALLBACK_OTHER_FAILURE")
                        fallback_observation = (
                            getattr(fallback_outcome, "observation", None)
                            if not isinstance(fallback_outcome, Mapping)
                            else fallback_outcome.get("observation", fallback_outcome))
                        fallback_accepted = bool(
                            getattr(fallback_outcome, "accepted", False)
                            if not isinstance(fallback_outcome, Mapping)
                            else fallback_outcome.get("accepted"))
                        ticket_ids = (
                            getattr(fallback_outcome, "request_ticket_ids", ())
                            if not isinstance(fallback_outcome, Mapping)
                            else fallback_outcome.get("request_ticket_ids", ()))
                        if isinstance(ticket_ids, (list, tuple)):
                            requests += len(ticket_ids)
                        if fallback_accepted and isinstance(
                                fallback_observation, Mapping):
                            if self._apply_authenticated_fallback(
                                    token, binding, fallback_observation):
                                fresh_price_accepted = True
                                with self._lock:
                                    self._counters[
                                        "fresh_market_fallback_succeeded_total"] += 1
                            else:
                                fallback_reason = (
                                    "FRESH_FALLBACK_OBSERVATION_REJECTED")
                    if not fresh_price_accepted:
                        with self._lock:
                            self._counters[
                                "fresh_market_fallback_failed_total"] += 1
                with self._lock:
                    self._fresh_fallback_last_result[token] = str(fallback_reason)
        finally:
            with self._lock:
                self._priority_refresh_inflight.discard(token)
        snapshot = self.snapshot(token)
        if fresh_price_accepted and bool(snapshot.get("all_present")):
            with self._lock:
                self._counters["priority_refresh_succeeded_total"] += 1
                self._priority_refresh_failures.pop(token, None)
                self._priority_refresh_permanent.pop(token, None)
                self._priority_refresh_next_allowed[token] = (
                    float(self._mono()) + PRIORITY_REFRESH_MIN_SPACING_SECONDS)
                self._clear_recovery_state_locked(token)
            return self._priority_refresh_result(
                token, REFRESH_SUCCEEDED, requests=requests, snapshot=None)
        with self._lock:
            attempts = int(self._priority_refresh_failures.get(token, 0)) + 1
            self._priority_refresh_failures[token] = attempts
            backoff = min(
                PRIORITY_REFRESH_BACKOFF_MAX_SECONDS,
                PRIORITY_REFRESH_BACKOFF_BASE_SECONDS * (2.0 ** (attempts - 1)))
            self._priority_refresh_next_allowed[token] = (
                float(self._mono()) + backoff)
            if rate_limited or BACKOFF_ACTIVE in failure_outcomes:
                self._counters["priority_refresh_rate_limited_total"] += 1
                outcome = BACKOFF_ACTIVE
            else:
                self._counters["priority_refresh_retryable_total"] += 1
                if STALE_PROVIDER_TIMESTAMP in failure_outcomes:
                    outcome = STALE_PROVIDER_TIMESTAMP
                elif WRONG_MINT in failure_outcomes:
                    outcome = WRONG_MINT
                elif MISSING_REQUIRED_FIELDS in failure_outcomes:
                    outcome = MISSING_REQUIRED_FIELDS
                elif PROVIDER_ERROR in failure_outcomes:
                    outcome = PROVIDER_ERROR
                else:
                    outcome = OTHER_NAMED_RESULT
        return self._priority_refresh_result(
            token, outcome, requests=requests,
            retry_after_seconds=backoff,
            detail=(fallback_reason or (
                failure_details[-1] if failure_details else None)))

    def _apply_authenticated_fallback(
        self,
        mint: str,
        binding: Tuple[str, int],
        result: Mapping[str, Any],
    ) -> bool:
        """Apply one coherent pool snapshot to both independent field planes."""

        if result.get("mint") != mint or result.get("accepted") is not True:
            return False
        source_ts = _epoch(result.get("accepted_at_utc"))
        now = float(self._now())
        if source_ts is None or source_ts > now + 2.0 \
                or now - source_ts > self.config.pending_price_max_age_seconds:
            return False
        price = _positive_decimal(result.get("current_price"))
        market_cap = _positive_decimal(result.get("current_market_cap_usd"))
        liquidity = _positive_decimal(result.get("liquidity_usd"))
        reserve = result.get("pumpswap_reserve")
        if price is None or market_cap is None or liquidity is None \
                or not isinstance(reserve, Mapping):
            return False
        sequence = self._next_sequence()
        evidence = _digest({
            "source": SOURCE_AUTHENTICATED_RESERVE_FALLBACK,
            "mint": mint,
            "candidate_id": binding[0],
            "generation": binding[1],
            "source_timestamp": source_ts,
            "current_price": _decimal_text(price),
            "current_market_cap_usd": _decimal_text(market_cap),
            "liquidity_usd": _decimal_text(liquidity),
            "pumpswap_reserve": dict(reserve),
        })
        common = dict(
            mint=mint,
            candidate_id=binding[0],
            generation=binding[1],
            source=SOURCE_AUTHENTICATED_RESERVE_FALLBACK,
            source_timestamp=source_ts,
            ingestion_timestamp=now,
            observation_sequence=sequence,
            source_evidence_digest=evidence,
            request_id=("fresh-fallback:"
                        + str(reserve.get("account_context_slot") or "unknown")),
        )
        price_observation = MarketObservation(
            **common,
            field_group=FIELD_PRICE_MC,
            values={
                "mint": mint,
                "current_price": _decimal_text(price),
                "current_market_cap_usd": _decimal_text(market_cap),
                "pumpswap_reserve": dict(reserve),
            },
        )
        overview_observation = MarketObservation(
            **common,
            field_group=FIELD_OVERVIEW,
            values={
                "mint": mint,
                "current_market_cap_usd": _decimal_text(market_cap),
                "liquidity_usd": _decimal_text(liquidity),
                "pumpswap_reserve": dict(reserve),
            },
        )
        price_ok = self.apply_observation(price_observation)
        overview_ok = self.apply_observation(overview_observation)
        snapshot = self.snapshot(mint)
        return bool((price_ok or snapshot.get("price_fresh"))
                    and (overview_ok or snapshot.get("liquidity_fresh"))
                    and snapshot.get("market_pair_coherent"))

    def _priority_job(self, mint: str, field_group: str,
                      binding: Tuple[str, int], *, deadline: float) -> MarketJob:
        with self._lock:
            self._request_sequence += 1
            sequence = self._request_sequence
        return MarketJob(
            sort_key=(PRIORITY_P0, 0.0, 0.0, mint, field_group, sequence),
            request_id=f"priority-{sequence:012d}",
            field_group=field_group,
            mints=(mint,),
            bindings=(binding,),
            submitted_at=float(self._now()),
            priority=PRIORITY_P0,
            deadline_mono=float(self._mono()) + max(0.05, float(deadline)),
        )

    def _clear_recovery_state_locked(self, mint: str) -> None:
        """A proven-fresh candidate is no longer in recovery backoff."""

        state = self._state.get(mint)
        if state is not None:
            state.last_request_error = None
            state.failure_count = 0
        view = self._views.get(mint)
        if view is not None and (
                view.market_state == "MARKET_RECOVERY_BACKOFF"
                or view.next_recovery_epoch is not None):
            self._views[mint] = replace(
                view, market_state="MARKET_READY",
                market_reason_code="REQUIRED_FIELDS_FRESH",
                next_recovery_epoch=None)

    def _priority_refresh_result(
        self, mint: str, outcome: str, *, requests: int,
        retry_after_seconds: Optional[float] = None,
        detail: Optional[str] = None,
        snapshot: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(self.snapshot(mint) if snapshot is None else snapshot)
        payload["priority_refresh_result"] = outcome
        payload["priority_refresh_provider_requests"] = int(requests)
        payload["priority_refresh_retry_after_seconds"] = retry_after_seconds
        payload["priority_refresh_detail"] = detail
        return payload

    def record_tier_projection(self, mint: str, *, ath_market_cap_usd: object) -> None:
        entered_tier: Optional[str] = None
        evidence_epoch: Optional[float] = None
        with self._lock:
            state = self._state.get(str(mint))
            if state is None:
                return
            previous_tier = state.projected_tier
            tier, drawdown = project_closed_tier(
                ath_market_cap_usd=ath_market_cap_usd,
                current_market_cap_usd=state.market_cap)
            state.projected_tier = tier
            state.projected_drawdown_pct = drawdown
            # PHX2-E2E-006: entering a tier band is the P1-due transition.
            # The deadline origin is the market-cap evidence timestamp that
            # produced this projection, never the projection call time.
            if tier in P1_TIERS and tier != previous_tier:
                entered_tier = tier
                evidence_epoch = state.market_cap_timestamp
        if entered_tier is not None:
            self.mark_p1_due(str(mint), tier=entered_tier,
                             due_epoch=evidence_epoch)

    def note_grpc_avoidance(self, count: int = 1) -> None:
        self._counters["market_requests_avoided_by_grpc"] += max(0, int(count))

    def note_heartbeat(self, *, due_epoch: float, actual_epoch: float) -> None:
        self._last_heartbeat_due = float(due_epoch)
        self._last_heartbeat_actual = float(actual_epoch)
        if abs(float(actual_epoch) - float(due_epoch)) > self.config.heartbeat_jitter_slo_seconds:
            self._note_degraded(MARKET_LATENCY_SLO_BREACHED)

    def capacity_assessment(self, *, active_candidates: int,
                            grpc_price_candidates: int,
                            overview_due_candidates: int) -> Dict[str, Any]:
        fallback_price = max(0, int(active_candidates) - int(grpc_price_candidates))
        batch_size = (self.config.paid_batch_size if self._batch_price_fetch is not None
                      and self.config.paid_batch_size > 1 else 1)
        price_requests = (fallback_price + batch_size - 1) // batch_size
        requests = price_requests + max(0, int(overview_due_candidates))
        pacing_floor = max(0, requests - 1) * self.config.provider_min_interval_seconds
        achievable = pacing_floor <= self.config.pending_price_max_age_seconds
        if not achievable:
            self._note_degraded(LATENCY_SLO_UNACHIEVABLE)
            self._capacity_limiting_resource = "PAID_PRIMARY_GLOBAL_REQUEST_SPACING"
        self._capacity_pacing_floor_seconds = max(
            self._capacity_pacing_floor_seconds, pacing_floor)
        return {
            "market_latency_slo_unachievable": not achievable,
            "limiting_resource": (None if achievable else "PAID_PRIMARY_GLOBAL_REQUEST_SPACING"),
            "planned_provider_requests": requests,
            "provider_pacing_floor_seconds": pacing_floor,
            "batch_supported": batch_size > 1,
            "batch_size": batch_size,
        }

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            deadlines: List[float] = []
            #: Deadlines the PLANNER would actually act on this cycle. A view
            #: the planner skips -- terminal, quarantined, or inside a
            #: recovery backoff that is not yet due -- is waiting BY DESIGN,
            #: and counting it as overdue is what made a healthy backoff read
            #: as starvation.
            starved_deadlines: List[float] = []
            deferred_deadlines: List[float] = []
            now = self._now()
            for view in self._views.values():
                planner_skips = bool(
                    view.quarantined or view.terminal_history
                    or view.status in _TERMINAL_STATES
                    or (view.market_state not in (None, "MARKET_READY")
                        and view.next_recovery_epoch is not None
                        and view.next_recovery_epoch > now))
                for group in (FIELD_PRICE_MC, FIELD_OVERVIEW):
                    due, deadline, _last = self._field_due(view, group, now=now)
                    if due:
                        deadlines.append(deadline)
                        (deferred_deadlines if planner_skips
                         else starved_deadlines).append(deadline)
            oldest_age = max((max(0.0, now - value) for value in deadlines), default=0.0)
            starved_age = max(
                (max(0.0, now - value) for value in starved_deadlines),
                default=0.0)
            deferred_age = max(
                (max(0.0, now - value) for value in deferred_deadlines),
                default=0.0)
            active_degraded = self._active_degraded_reasons()
            active_ages = []
            background_ages = []
            for mint, view in self._views.items():
                state = self._state.get(mint)
                if state is None:
                    continue
                timestamps = [value for value in (
                    state.price_timestamp, state.market_cap_timestamp)
                    if value is not None]
                age = max((max(0.0, now - value) for value in timestamps), default=0.0)
                (active_ages if view.status in _ACTIVATED_STATES else background_ages).append(age)
            grpc_latencies = self._latencies["market_grpc_to_watch_latency_ms"]
            recovery_latencies = self._latencies["market_due_recovery_probe_latency_ms"]
            queue_depth = self._jobs.qsize() + self._jobs_general.qsize()
            inflight = self._provider_requests_inflight
            scheduler_physical_total = self._budget_charged_locked()
            mono_now = float(self._mono())
            open_ages = [max(0.0, mono_now - window.opened_mono)
                         for window in self._p1_windows.values()
                         if not window.closed]
            p1_sorted = sorted(self._p1_latencies)

            def _p1_pct(fraction: float) -> Optional[float]:
                if not p1_sorted:
                    return None
                index = max(0, min(len(p1_sorted) - 1, int(round(
                    fraction * (len(p1_sorted) - 1)))))
                return round(p1_sorted[index], 6)

            return {
                **self._counters,
                "fresh_market_fallback_capability_available": (
                    self._fresh_fallback_fetch is not None),
                "fresh_market_fallback_last_results": dict(
                    self._fresh_fallback_last_result),
                "market_scheduler_queue_depth": queue_depth,
                "market_scheduler_inflight": inflight,
                "market_scheduler_worker_count": self.config.worker_count,
                # ---- PHX2-E2E-006 P1 observability (closed-set tokens,
                # bounded numeric summaries only) ----
                "scheduler_state": self._scheduler_state_locked(),
                "configured_p1_deadline_seconds": float(
                    self.config.p1_deadline_seconds),
                "capacity_proof_result": (
                    None if self._capacity_proof is None else (
                        "ACHIEVABLE"
                        if self._capacity_proof.get("p1_capacity_achievable")
                        else P1_CAPACITY_UNACHIEVABLE)),
                "calculated_capacity_bound_seconds": (
                    None if self._capacity_proof is None else
                    self._capacity_proof.get(
                        "calculated_worst_case_bound_seconds")),
                "active_worker_count": sum(
                    1 for worker in self._workers if worker.is_alive()),
                "maximum_observed_worker_count": self._max_observed_inflight,
                "configured_concurrency": min(
                    int(self.config.worker_count), int(self.config.max_inflight)),
                "p1_queue_depth": (self._queued_by_priority.get(PRIORITY_P0, 0)
                                   + self._queued_by_priority.get(PRIORITY_P1, 0)),
                "p2_queue_depth": self._queued_by_priority.get(PRIORITY_P2, 0),
                "p3_queue_depth": self._queued_by_priority.get(PRIORITY_P3, 0),
                "oldest_p1_age_seconds": round(max(open_ages), 3) if open_ages else 0.0,
                "p1_open_windows": len(open_ages),
                "provider_logical_items_total": (
                    self._counters["market_price_single_requests"]
                    + self._counters["market_price_batch_mints"]
                    + self._counters["market_overview_requests"]),
                # Dispatches this scheduler MADE. Before the physical meter
                # existed this key was published as "physical", which is how
                # 5,000 charged units passed for 5,000 HTTP calls when the
                # transport had made 3,472.
                "provider_logical_dispatches_total": (
                    self._counters["market_price_single_requests"]
                    + self._counters["market_price_batch_requests"]
                    + self._counters["market_overview_requests"]),
                "provider_physical_requests_total": (
                    scheduler_physical_total
                    if self._physical_meter is not None else (
                        self._counters["market_price_single_requests"]
                        + self._counters["market_price_batch_requests"]
                        + self._counters["market_overview_requests"])),
                "market_non_physical_dispatches": self._non_physical_dispatches,
                **self._batch_telemetry_locked(),
                **market_budget_status(
                    self.config.provider_request_budget,
                    scheduler_physical_total),
                **reconcile_physical_requests(
                    scheduler_physical_requests_total=(
                        scheduler_physical_total),
                    meter=self._physical_meter),
                "coalesced_work_total": self._counters["market_requests_coalesced"],
                "handoff_queue_depth": self._handoff_depth,
                "handoff_oldest_age_seconds": round(self._handoff_oldest_age, 3),
                "scheduler_p50_seconds": _p1_pct(0.50),
                "scheduler_p95_seconds": _p1_pct(0.95),
                "scheduler_p99_seconds": _p1_pct(0.99),
                "scheduler_max_seconds": (
                    round(p1_sorted[-1], 6) if p1_sorted else None),
                "market_scheduler_oldest_deadline_age_seconds": round(oldest_age, 3),
                # Work the planner would ACTUALLY pick up right now. The
                # deadline age above counts every due field group including
                # candidates the planner deliberately defers (a recovery
                # backoff whose next probe is not yet due), so on its own it
                # cannot distinguish "starved" from "waiting on purpose" --
                # the 2026-07-29 run reported 2,909 s of oldest deadline with
                # an empty queue and 8 candidates legitimately backing off.
                "market_scheduler_starved_age_seconds": round(starved_age, 3),
                # submitted == settled + cancelled + queued + inflight. A
                # non-zero remainder is genuinely unaccounted work, which is
                # what this identity exists to make visible.
                "market_scheduler_jobs_unaccounted": max(0, (
                    self._counters["market_scheduler_jobs_submitted"]
                    - self._counters["market_scheduler_jobs_settled"]
                    - self._counters["market_scheduler_jobs_cancelled"]
                    - queue_depth - self._provider_requests_inflight)),
                "market_scheduler_jobs_settled_without_completion": max(0, (
                    self._counters["market_scheduler_jobs_settled"]
                    - self._counters["market_scheduler_jobs_completed"])),
                "market_scheduler_deferred_age_seconds": round(deferred_age, 3),
                "market_scheduler_backlog_high": (
                    MARKET_SCHEDULER_BACKLOG_HIGH in active_degraded),
                "market_scheduler_slo_breached": bool(
                    active_degraded & {
                        MARKET_LATENCY_SLO_BREACHED,
                        MARKET_OBSERVATION_STARVED,
                        LATENCY_SLO_UNACHIEVABLE,
                    }),
                "market_grpc_to_watch_latency_ms": (
                    max(grpc_latencies) if grpc_latencies else None),
                "market_due_recovery_probe_latency_ms": (
                    max(recovery_latencies) if recovery_latencies else None),
                "market_active_candidate_max_observation_age_seconds": (
                    max(active_ages) if active_ages else 0.0),
                "market_background_candidate_max_observation_age_seconds": (
                    max(background_ages) if background_ages else 0.0),
                "market_latency_slo_unachievable": (
                    LATENCY_SLO_UNACHIEVABLE in active_degraded),
                "market_latency_slo_limiting_resource": self._capacity_limiting_resource,
                "market_provider_pacing_floor_seconds": round(
                    self._capacity_pacing_floor_seconds, 3),
                "market_provider_budget_remaining": (
                    None if self.config.provider_budget_unbounded else max(
                        0, int(self.config.provider_request_budget)
                        - self._budget_charged_locked())),
                "market_scheduler_degraded_reasons": sorted(active_degraded),
                # Nothing is lost by ageing the reported set: every reason ever
                # observed is still disclosed here, with its observation count.
                "market_scheduler_degraded_reasons_lifetime": {
                    reason: int(count) for reason, count
                    in sorted(self._degraded_lifetime.items())},
            }


class ScheduledMarketSidecar:
    """Non-blocking compatibility facade for ``run_cap1_candidates``."""

    def __init__(self, scheduler: MarketScheduler,
                 central_ath_snapshot_fn: Optional[Callable[[str], Any]] = None,
                 reserve_index: Any = None) -> None:
        self._scheduler = scheduler
        self._central_ath_snapshot = central_ath_snapshot_fn
        self._reserve_index = reserve_index

    def resolve(self, mint: str, *, migration_time_utc: Optional[str],
                now_iso_fn: Callable[[], str],
                sleep_fn: Callable[[float], None]) -> Dict[str, Any]:
        _ = migration_time_utc, now_iso_fn, sleep_fn
        snapshot = self._scheduler.snapshot(mint)
        snapshot["central_ath"] = self.central_ath_snapshot(mint)
        # 2026-07-28 liquidity remediation: the compose/delivery context must
        # carry the same exact-pair actual-reserve telemetry the pricing-tail
        # path already computes; without it every alert rendered actual LP as
        # unavailable.  Pure in-memory read (cached quote price); priced with
        # THIS context's current price so the delivery-layer exact-recompute
        # verification can hold.  Any error leaves the mapping empty and the
        # delivery layer fails closed to the unavailable display.
        if self._reserve_index is not None:
            try:
                if self._reserve_index.latest(mint) is not None:
                    snapshot["pumpswap_reserve"] = (
                        self._reserve_index.compare_market(
                            mint,
                            birdeye_price_usd=snapshot.get("current_price"),
                        ))
            except Exception:
                pass
        return snapshot

    def priority_refresh(
        self,
        mint: str,
        *,
        migration_time_utc: Optional[str] = None,
        now_iso_fn: Optional[Callable[[], str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """ONE bounded send-time refresh for an otherwise-ready candidate.

        THIS is the method production actually reaches.  Until 2026-08-02 it
        existed only on the retired ``Cap1MarketSidecar``, while the paid
        runtime runs ``ScheduledMarketSidecar``; the runner's
        ``getattr(sidecar, "priority_refresh", None)`` therefore resolved to
        ``None`` on every single attempt.  The PHX1_PARITY run recorded
        2,068 attempted refreshes and 0 successes for exactly that reason --
        the refresh was never made at all.

        The signature mirrors the legacy sidecar so the caller is unchanged.
        ``migration_time_utc`` is accepted for call compatibility; the
        scheduled topology anchors its own bookkeeping on the tracked
        candidate view rather than re-deriving it here.
        """

        del migration_time_utc, now_iso_fn
        token = str(mint or "")
        context = self._scheduler.priority_refresh(
            token, timeout_seconds=timeout_seconds)
        context["central_ath"] = self.central_ath_snapshot(token)
        if self._reserve_index is not None:
            try:
                if self._reserve_index.latest(token) is not None:
                    context["pumpswap_reserve"] = (
                        self._reserve_index.compare_market(
                            token,
                            birdeye_price_usd=context.get("current_price"),
                        ))
            except Exception:
                pass
        return context

    def central_ath_snapshot(self, mint: str) -> Dict[str, Any]:
        if self._central_ath_snapshot is None:
            return {}
        try:
            return dict(self._central_ath_snapshot(mint) or {})
        except Exception:
            return {}

    def stats(self) -> Dict[str, Any]:
        stats = self._scheduler.stats()
        return {
            **stats,
            "market_attempts_total": (
                stats["market_price_single_requests"]
                + stats["market_price_batch_requests"]
                + stats["market_overview_requests"]),
        }


def old_serial_latency_fixture(*, candidate_count: int = 128,
                               requests_per_candidate: int = 2,
                               min_spacing_seconds: float = 1.05,
                               final_watch_sleep_seconds: float = 45.0) -> Dict[str, Any]:
    """Pure hostile baseline used to retain the PHX2-E2E-006 reproduction."""

    calls = int(candidate_count) * int(requests_per_candidate)
    pacing = max(0, calls - 1) * float(min_spacing_seconds)
    return {
        "candidate_count": int(candidate_count),
        "provider_calls": calls,
        "pacing_floor_seconds": pacing,
        "final_watch_sleep_seconds": float(final_watch_sleep_seconds),
        "total_floor_seconds": pacing + float(final_watch_sleep_seconds),
    }


def offline_grpc_vs_helius_comparison_fixture() -> Dict[str, Any]:
    """Data-completeness comparison only; makes no latency claim.

    The PHX1-shaped input begins with a log notification and therefore needs
    one transaction lookup before instruction/CPI and reserve data are
    available. The PHX2-shaped Yellowstone transaction already contains that
    transaction context. Both paths still require independently fresh paid
    liquidity/overview authorization before send.
    """

    return {
        "phx1_additional_transaction_rpc_lookups": 1,
        "phx2_additional_price_mc_lookups": 0,
        "phx2_paid_enrichment_lookups_before_send": 1,
        "phx2_event_fields": (
            "transaction_identity", "instruction_cpi_context", "pool_vault_bindings",
            "effective_reserves", "price_market_cap_derivation", "ath_input",
            "candidate_route",
        ),
        "empirical_latency_claimed": False,
    }


__all__ = (
    "FIELD_PRICE_MC", "FIELD_OVERVIEW", "FIELD_QUOTE_PRICE", "SOURCE_GRPC", "SOURCE_PAID_BATCH",
    "SOURCE_PAID_SINGLE", "SOURCE_AUTHENTICATED_RESERVE_FALLBACK",
    "PRIORITY_P0", "PRIORITY_P1", "PRIORITY_P2",
    "PRIORITY_P3", "PRIORITY_NAMES", "MARKET_SCHEDULER_BACKLOG_HIGH",
    "MARKET_LATENCY_SLO_BREACHED", "MARKET_PROVIDER_BUDGET_EXHAUSTED",
    "MARKET_BATCH_PARTIAL", "MARKET_OBSERVATION_STARVED",
    "MARKET_SCHEDULER_OVERLOADED", "LATENCY_SLO_UNACHIEVABLE",
    "P1_CAPACITY_UNACHIEVABLE", "P1_DEADLINE_MISSED",
    "CADENCE_CONFIG_FIELDS", "CADENCE_TIER_ACTIVE", "CADENCE_NEAR_TIER",
    "CADENCE_FAR", "CADENCE_INACTIVE", "CADENCE_CLASSES",
    "REFRESH_SUCCEEDED", "REFRESH_RETRYABLE_FAILURE",
    "REFRESH_PERMANENT_FAILURE", "REFRESH_RATE_LIMITED",
    "REFRESH_ALREADY_IN_FLIGHT", "PRIORITY_REFRESH_RESULTS",
    "ACCEPTED_FRESH_OBSERVATION", "STALE_PROVIDER_TIMESTAMP",
    "PROVIDER_ERROR", "BACKOFF_ACTIVE", "ALREADY_IN_FLIGHT",
    "MISSING_REQUIRED_FIELDS", "WRONG_MINT", "OTHER_NAMED_RESULT",
    "PRIORITY_REFRESH_MIN_SPACING_SECONDS",
    "PRIORITY_REFRESH_BACKOFF_BASE_SECONDS",
    "PRIORITY_REFRESH_BACKOFF_MAX_SECONDS",
    "PRIORITY_REFRESH_MAX_PERMANENT_FAILURES",
    "SCHEDULER_READY", "SCHEDULER_DEGRADED", "SCHEDULER_CAPACITY_REFUSED",
    "SCHEDULER_SHUTTING_DOWN", "SCHEDULER_STOPPED",
    "P1_RESULT_DISPATCH_EVALUATED", "P1_RESULT_TEMP_BLOCKED",
    "P1_RESULT_PERM_BLOCKED", "P1_RESULT_PROVIDER_FAILURE",
    "P1_RESULT_DEADLINE_MISSED", "P1_RESULT_SEND_COOLDOWN",
    "P1_RESULT_TOKENS", "P1_TIERS",
    "classify_engine_reason_to_p1_outcome",
    "evaluate_p1_capacity", "production_p1_scheduler_fields",
    "project_request_budget",
    "MarketSchedulerConfig", "CandidateScheduleView", "MarketObservation",
    "MarketJob", "MarketScheduler", "ScheduledMarketSidecar",
    "candidate_generation", "project_closed_tier", "old_serial_latency_fixture",
    "offline_grpc_vs_helius_comparison_fixture",
)
