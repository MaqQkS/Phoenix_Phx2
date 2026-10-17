"""Named, explicit alert policy: ``LEGACY`` and ``PHX1_PARITY``.

The 2026-08-01 live run proved PHX2's discovery, restart retention, checkpoint
durability, provider isolation, ATH and tier calculations all correct -- and
for every mint both bots evaluated, PHX2's tier matched PHX1's.  PHX1 still
produced eight unique alerts where PHX2 produced zero.  The whole difference
lived in candidate-universe and eligibility policy, never in tier maths:

* 11 of 18 tracked candidates sat in ``PENDING_1_20X`` -- the activation proof
  is a HARD Telegram prerequisite, so a tier-eligible mint that never crossed
  1.20x could not alert at all;
* the 6 that DID prove activation were all blocked on market state
  (``MARKET_INCOMPLETE`` / ``MARKET_RECOVERY_BACKOFF``) with no send-time
  priority refresh to clear it;
* 34 candidates reached the 60-minute watch TTL and expired, several of them
  before PHX1 alerted on the same mint.

This module owns the closed set of alert-policy decisions.  It NEVER computes a
tier, a drawdown, an ATH, a liquidity value or a delivery verdict; it only
answers "is this condition enforced, and how" for one named policy.  Unknown
policies and unknown conditions fail closed.

Enforcement vocabulary (the observability contract):

``HARD``
    Blocks before compose.  Never relaxed by any policy here.
``HARD_AT_SEND``
    Evaluated with fresh evidence immediately before compose; a failure keeps
    the candidate and retries, it never discards.
``SHADOW``
    Recorded, counted and annotated -- never a blocker.
``PRESENTATION``
    Affects the rendered message only.

A shadow condition is NEVER labelled blocked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Tuple


POLICY_SCHEMA_VERSION = "PHX2_ALERT_POLICY_V1"

# --- Policy names (closed set) --------------------------------------------

ALERT_POLICY_LEGACY = "LEGACY"
ALERT_POLICY_PHX1_PARITY = "PHX1_PARITY"
ALERT_POLICY_MODES: Tuple[str, ...] = (
    ALERT_POLICY_LEGACY,
    ALERT_POLICY_PHX1_PARITY,
)
#: Exactly the two documented CLI spellings.  Mixed-case aliases fail closed.
ALERT_POLICY_CLI_VALUES: Tuple[str, ...] = ("legacy", "phx1_parity")

ALERT_POLICY_INVALID = "ALERT_POLICY_INVALID"

# --- Enforcement vocabulary (closed set) ----------------------------------

ENFORCEMENT_HARD = "HARD"
ENFORCEMENT_HARD_AT_SEND = "HARD_AT_SEND"
ENFORCEMENT_SHADOW = "SHADOW"
ENFORCEMENT_PRESENTATION = "PRESENTATION"
ENFORCEMENT_LEVELS: Tuple[str, ...] = (
    ENFORCEMENT_HARD,
    ENFORCEMENT_HARD_AT_SEND,
    ENFORCEMENT_SHADOW,
    ENFORCEMENT_PRESENTATION,
)

#: Enforcement levels that may stop a candidate reaching compose.
BLOCKING_ENFORCEMENT_LEVELS: Tuple[str, ...] = (
    ENFORCEMENT_HARD,
    ENFORCEMENT_HARD_AT_SEND,
)

# --- Conditions (closed set) ----------------------------------------------
# Every production condition capable of preventing an otherwise tier-eligible
# candidate from reaching compose.  Names are the audit's condition names, not
# the internal reason tokens, so one condition can cover several tokens.

CONDITION_ACTIVATION_PROVEN = "activation_proven"
CONDITION_ACTIVATION_MULTIPLIER_LIVE = "activation_multiplier_live"
CONDITION_ACTIVATION_MULTIPLIER_BACKFILL = "activation_multiplier_backfill"
CONDITION_ACTIVATION_CROSSING_TICK = "activation_crossing_tick_blocked"
CONDITION_FEE_GATE_LIFECYCLE_IMMATURE = "fee_gate_lifecycle_immature"
CONDITION_FEE_PROOF_MISSING = "fee_proof_missing"
CONDITION_FEE_GATE_SCAM_LIKELY = "phx1_fee_gate_scam_likely"
CONDITION_GLOBAL_FEE_SUPPORT = "global_fee_support"
CONDITION_STRUCTURAL_POLICY = "structural_policy"
CONDITION_ATH_COVERAGE = "ath_coverage_complete"
CONDITION_MARKET_FRESHNESS = "market_freshness"
CONDITION_MARKET_RECOVERY_BACKOFF = "market_recovery_backoff"
CONDITION_LIQUIDITY_FLOOR = "liquidity_floor"
CONDITION_CANDIDATE_WATCH_TTL = "candidate_watch_ttl"
CONDITION_CANDIDATE_EXPIRY = "candidate_expiry"
CONDITION_METADATA_READINESS = "metadata_readiness"
CONDITION_TIER_LIFETIME_MONOTONICITY = "tier_lifetime_monotonicity"
CONDITION_DEDUPE = "dedupe"
CONDITION_COMPOSE_AUTHORIZATION = "compose_authorization"
CONDITION_MIGRATION_PROVEN = "migration_proven"
CONDITION_CURRENT_MARKET_CAP_VALID = "current_market_cap_valid"
CONDITION_CANDIDATE_IDENTITY = "candidate_identity"
CONDITION_DELIVERY_RESERVATION = "delivery_reservation"
CONDITION_CREDENTIALS = "credentials"
CONDITION_CHECKPOINT_INTEGRITY = "checkpoint_integrity"
CONDITION_OWNERSHIP_DUPLICATION = "ownership_duplication"

ALERT_POLICY_CONDITIONS: Tuple[str, ...] = (
    CONDITION_ACTIVATION_PROVEN,
    CONDITION_ACTIVATION_MULTIPLIER_LIVE,
    CONDITION_ACTIVATION_MULTIPLIER_BACKFILL,
    CONDITION_ACTIVATION_CROSSING_TICK,
    CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
    CONDITION_FEE_PROOF_MISSING,
    CONDITION_FEE_GATE_SCAM_LIKELY,
    CONDITION_GLOBAL_FEE_SUPPORT,
    CONDITION_STRUCTURAL_POLICY,
    CONDITION_ATH_COVERAGE,
    CONDITION_MARKET_FRESHNESS,
    CONDITION_MARKET_RECOVERY_BACKOFF,
    CONDITION_LIQUIDITY_FLOOR,
    CONDITION_CANDIDATE_WATCH_TTL,
    CONDITION_CANDIDATE_EXPIRY,
    CONDITION_METADATA_READINESS,
    CONDITION_TIER_LIFETIME_MONOTONICITY,
    CONDITION_DEDUPE,
    CONDITION_COMPOSE_AUTHORIZATION,
    CONDITION_MIGRATION_PROVEN,
    CONDITION_CURRENT_MARKET_CAP_VALID,
    CONDITION_CANDIDATE_IDENTITY,
    CONDITION_DELIVERY_RESERVATION,
    CONDITION_CREDENTIALS,
    CONDITION_CHECKPOINT_INTEGRITY,
    CONDITION_OWNERSHIP_DUPLICATION,
)

#: The core safety conditions no policy in this module may relax.  Listed
#: explicitly so a future policy addition that tries to soften one is a test
#: failure rather than a silent regression.
NON_RELAXABLE_CONDITIONS: Tuple[str, ...] = (
    CONDITION_MIGRATION_PROVEN,
    CONDITION_ATH_COVERAGE,
    CONDITION_CURRENT_MARKET_CAP_VALID,
    CONDITION_LIQUIDITY_FLOOR,
    CONDITION_CANDIDATE_IDENTITY,
    CONDITION_DELIVERY_RESERVATION,
    CONDITION_CREDENTIALS,
    CONDITION_CHECKPOINT_INTEGRITY,
    CONDITION_OWNERSHIP_DUPLICATION,
    CONDITION_DEDUPE,
    CONDITION_TIER_LIFETIME_MONOTONICITY,
)

_LEGACY_ENFORCEMENT: Dict[str, str] = {
    CONDITION_ACTIVATION_PROVEN: ENFORCEMENT_HARD,
    CONDITION_ACTIVATION_MULTIPLIER_LIVE: ENFORCEMENT_HARD,
    CONDITION_ACTIVATION_MULTIPLIER_BACKFILL: ENFORCEMENT_HARD,
    CONDITION_ACTIVATION_CROSSING_TICK: ENFORCEMENT_HARD,
    CONDITION_FEE_GATE_LIFECYCLE_IMMATURE: ENFORCEMENT_HARD,
    CONDITION_FEE_PROOF_MISSING: ENFORCEMENT_HARD,
    CONDITION_FEE_GATE_SCAM_LIKELY: ENFORCEMENT_HARD,
    CONDITION_GLOBAL_FEE_SUPPORT: ENFORCEMENT_PRESENTATION,
    CONDITION_STRUCTURAL_POLICY: ENFORCEMENT_HARD,
    CONDITION_ATH_COVERAGE: ENFORCEMENT_HARD,
    CONDITION_MARKET_FRESHNESS: ENFORCEMENT_HARD_AT_SEND,
    CONDITION_MARKET_RECOVERY_BACKOFF: ENFORCEMENT_HARD_AT_SEND,
    CONDITION_LIQUIDITY_FLOOR: ENFORCEMENT_HARD,
    CONDITION_CANDIDATE_WATCH_TTL: ENFORCEMENT_HARD,
    CONDITION_CANDIDATE_EXPIRY: ENFORCEMENT_HARD,
    CONDITION_METADATA_READINESS: ENFORCEMENT_SHADOW,
    CONDITION_TIER_LIFETIME_MONOTONICITY: ENFORCEMENT_HARD,
    CONDITION_DEDUPE: ENFORCEMENT_HARD,
    CONDITION_COMPOSE_AUTHORIZATION: ENFORCEMENT_HARD,
    CONDITION_MIGRATION_PROVEN: ENFORCEMENT_HARD,
    CONDITION_CURRENT_MARKET_CAP_VALID: ENFORCEMENT_HARD,
    CONDITION_CANDIDATE_IDENTITY: ENFORCEMENT_HARD,
    CONDITION_DELIVERY_RESERVATION: ENFORCEMENT_HARD,
    CONDITION_CREDENTIALS: ENFORCEMENT_HARD,
    CONDITION_CHECKPOINT_INTEGRITY: ENFORCEMENT_HARD,
    CONDITION_OWNERSHIP_DUPLICATION: ENFORCEMENT_HARD,
}

#: PHX1_PARITY relaxes EXACTLY these conditions and nothing else.  Every other
#: condition inherits its legacy enforcement verbatim.
_PHX1_PARITY_OVERRIDES: Dict[str, str] = {
    CONDITION_ACTIVATION_PROVEN: ENFORCEMENT_SHADOW,
    CONDITION_ACTIVATION_MULTIPLIER_LIVE: ENFORCEMENT_SHADOW,
    CONDITION_ACTIVATION_MULTIPLIER_BACKFILL: ENFORCEMENT_SHADOW,
    CONDITION_ACTIVATION_CROSSING_TICK: ENFORCEMENT_SHADOW,
    CONDITION_FEE_GATE_LIFECYCLE_IMMATURE: ENFORCEMENT_SHADOW,
    CONDITION_FEE_PROOF_MISSING: ENFORCEMENT_SHADOW,
    CONDITION_FEE_GATE_SCAM_LIKELY: ENFORCEMENT_SHADOW,
    CONDITION_STRUCTURAL_POLICY: ENFORCEMENT_SHADOW,
}

_PHX1_PARITY_ENFORCEMENT: Dict[str, str] = {
    **_LEGACY_ENFORCEMENT, **_PHX1_PARITY_OVERRIDES,
}

_ENFORCEMENT_BY_POLICY: Dict[str, Dict[str, str]] = {
    ALERT_POLICY_LEGACY: _LEGACY_ENFORCEMENT,
    ALERT_POLICY_PHX1_PARITY: _PHX1_PARITY_ENFORCEMENT,
}

#: Conditions PHX1_PARITY moves off the blocking path.  Derived, not hand
#: maintained, so it can never drift from the matrix above.
PHX1_PARITY_RELAXED_CONDITIONS: Tuple[str, ...] = tuple(
    condition for condition in ALERT_POLICY_CONDITIONS
    if _LEGACY_ENFORCEMENT[condition] in BLOCKING_ENFORCEMENT_LEVELS
    and _PHX1_PARITY_ENFORCEMENT[condition] not in BLOCKING_ENFORCEMENT_LEVELS
)


# --- Watch lifetime --------------------------------------------------------

LEGACY_WATCH_TTL_SECONDS = 3600
#: Six hours.  PHX1 alerted on mints PHX2 had already expired at 60 minutes.
PHX1_PARITY_WATCH_TTL_SECONDS = 21600

_WATCH_TTL_BY_POLICY: Dict[str, int] = {
    ALERT_POLICY_LEGACY: LEGACY_WATCH_TTL_SECONDS,
    ALERT_POLICY_PHX1_PARITY: PHX1_PARITY_WATCH_TTL_SECONDS,
}

# --- Activation multipliers ------------------------------------------------

LIVE_ACTIVATION_MULTIPLIER = Decimal("1.20")
#: PHX1's own restart-backfill threshold.  Under PHX1_PARITY a backfill
#: candidate carries NO additional activation penalty: it uses the same
#: informational contract as a live candidate.  Provenance itself is never
#: rewritten.
LEGACY_BACKFILL_ACTIVATION_MULTIPLIER = Decimal("1.39")

# --- Adaptive refresh cadence ---------------------------------------------
# A six-hour watch at the 45 s maintenance cadence would multiply per-candidate
# provider work sixfold.  Cadence therefore follows candidate heat, not age
# alone: a hot or recently active candidate keeps the fast cadence, a quiet one
# steps down through a bounded ladder, and ANY renewed activity puts it
# straight back on the fast cadence.

HEAT_HOT = "HOT"
HEAT_WARM = "WARM"
HEAT_COOL = "COOL"
HEAT_COLD = "COLD"
REFRESH_HEAT_LEVELS: Tuple[str, ...] = (HEAT_HOT, HEAT_WARM, HEAT_COOL, HEAT_COLD)

#: Seconds since the candidate last showed activity (activation progress, a
#: tier change, a market-state change, or entering an active dip) that define
#: each heat band, with the cadence multiplier applied to the base interval.
_HEAT_LADDER: Tuple[Tuple[str, float, float], ...] = (
    (HEAT_HOT, 900.0, 1.0),      # first 15 min, or any active dip: full speed
    (HEAT_WARM, 3600.0, 2.0),    # 15-60 min quiet
    (HEAT_COOL, 10800.0, 4.0),   # 1-3 h quiet
    (HEAT_COLD, float("inf"), 8.0),   # 3 h+ quiet
)

MAX_ADAPTIVE_REFRESH_SECONDS = 600.0


def normalize_alert_policy(value: object = None) -> str:
    """Normalize only the documented spellings; anything else fails closed."""

    if value is None:
        return ALERT_POLICY_LEGACY
    if value in (ALERT_POLICY_LEGACY, "legacy"):
        return ALERT_POLICY_LEGACY
    if value in (ALERT_POLICY_PHX1_PARITY, "phx1_parity"):
        return ALERT_POLICY_PHX1_PARITY
    raise ValueError(ALERT_POLICY_INVALID)


def is_phx1_parity(policy: object = None) -> bool:
    return normalize_alert_policy(policy) == ALERT_POLICY_PHX1_PARITY


def enforcement_for(condition: object, *, policy: object = None) -> str:
    """Enforcement level for one closed-set condition under one policy.

    An unknown condition is NOT silently permitted: it fails closed as HARD, so
    a new gate added elsewhere without a policy entry keeps blocking until it is
    deliberately classified here.
    """

    mode = normalize_alert_policy(policy)
    table = _ENFORCEMENT_BY_POLICY[mode]
    if not isinstance(condition, str) or condition not in table:
        return ENFORCEMENT_HARD
    return table[condition]


def blocks_compose(condition: object, *, policy: object = None) -> bool:
    """True when this condition may stop the candidate reaching compose."""

    return enforcement_for(condition, policy=policy) in BLOCKING_ENFORCEMENT_LEVELS


def watch_ttl_seconds(policy: object = None) -> int:
    """Candidate watch TTL in seconds for the given policy."""

    return _WATCH_TTL_BY_POLICY[normalize_alert_policy(policy)]


def expected_activation_multiplier(
    *, discovery_provenance_is_backfill: bool, policy: object = None
) -> Decimal:
    """Multiplier the activation proof is expected to carry.

    Under PHX1_PARITY a DEX-backfill candidate is held to the SAME 1.20x
    contract as a live candidate -- backfill provenance must not create an
    additional activation penalty.  Provenance itself is untouched.
    """

    if not discovery_provenance_is_backfill:
        return LIVE_ACTIVATION_MULTIPLIER
    if is_phx1_parity(policy):
        return LIVE_ACTIVATION_MULTIPLIER
    return LEGACY_BACKFILL_ACTIVATION_MULTIPLIER


def refresh_heat(
    *,
    seconds_since_activity: object,
    is_active_dip: bool = False,
) -> str:
    """Closed-set heat band for one candidate.

    An active dip candidate is ALWAYS hot: it is the one state from which a
    send can actually happen, so it never steps down.  A missing or unparseable
    age is treated as hot (fail fast, never fail slow).
    """

    if is_active_dip:
        return HEAT_HOT
    try:
        age = float(seconds_since_activity)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return HEAT_HOT
    if age != age or age < 0.0:      # NaN or a clock that ran backwards
        return HEAT_HOT
    for level, ceiling, _multiplier in _HEAT_LADDER:
        if age < ceiling:
            return level
    return HEAT_COLD


def adaptive_refresh_interval_seconds(
    *,
    base_interval_seconds: float,
    seconds_since_activity: object = None,
    is_active_dip: bool = False,
    policy: object = None,
) -> float:
    """Per-candidate refresh spacing.

    LEGACY keeps the flat base interval exactly as committed.  PHX1_PARITY
    applies the heat ladder so a six-hour watch does not multiply provider
    volume; a reactivated candidate returns to the base interval immediately.
    """

    base = max(0.0, float(base_interval_seconds))
    if not is_phx1_parity(policy):
        return base
    heat = refresh_heat(
        seconds_since_activity=seconds_since_activity,
        is_active_dip=is_active_dip,
    )
    multiplier = next(m for level, _c, m in _HEAT_LADDER if level == heat)
    return min(base * multiplier, MAX_ADAPTIVE_REFRESH_SECONDS)


def heat_interval_seconds(
    heat: object, *, base_interval_seconds: float, policy: object = None
) -> float:
    """Refresh spacing for one heat band."""

    base = max(1e-9, float(base_interval_seconds))
    if not is_phx1_parity(policy):
        return base
    multiplier = next(
        (m for level, _c, m in _HEAT_LADDER if level == heat), 1.0)
    return min(base * multiplier, MAX_ADAPTIVE_REFRESH_SECONDS)


def project_market_requests_per_hour(
    *,
    candidates_by_heat: Mapping[str, int],
    base_interval_seconds: float,
    requests_per_refresh: int = 1,
    policy: object = None,
) -> float:
    """Projected provider requests per hour for a heat-distributed watchlist.

    The startup budget proof compares the six-hour PHX1_PARITY watch against the
    committed one-hour LEGACY watch at the SAME watchlist capacity: the extended
    TTL is only admissible if the adaptive ladder keeps projected volume at or
    below what the flat cadence already spends.
    """

    base = max(1e-9, float(base_interval_seconds))
    per_refresh = max(1, int(requests_per_refresh))
    total = 0.0
    for heat, count in (candidates_by_heat or {}).items():
        n = max(0, int(count))
        if not n:
            continue
        interval = heat_interval_seconds(
            heat, base_interval_seconds=base, policy=policy)
        total += (3600.0 / max(1e-9, interval)) * n * per_refresh
    return total


def project_watchlist_heat_distribution(
    *, watchlist_size: int, watch_ttl_seconds_value: float
) -> Dict[str, int]:
    """Conservative steady-state heat mix for a full watchlist.

    Assumes a uniform arrival distribution across the TTL and treats every
    candidate's seeded age as its quiet age -- the WORST case for the ladder,
    since any renewed activity only moves candidates back toward HOT.
    """

    size = max(0, int(watchlist_size))
    ttl = max(1e-9, float(watch_ttl_seconds_value))
    distribution: Dict[str, int] = {}
    assigned = 0
    previous = 0.0
    for index, (level, ceiling, _multiplier) in enumerate(_HEAT_LADDER):
        upper = min(ceiling, ttl)
        if index == len(_HEAT_LADDER) - 1:
            share = size - assigned
        else:
            share = int(round(size * max(0.0, upper - previous) / ttl))
        share = max(0, min(share, size - assigned))
        distribution[level] = share
        assigned += share
        previous = upper
        if previous >= ttl:
            break
    for level, _c, _m in _HEAT_LADDER:
        distribution.setdefault(level, 0)
    return distribution


# --- Send-time bounded market refresh -------------------------------------

SEND_TIME_REFRESH_MAX_ATTEMPTS = 1
REFRESH_NOT_REQUIRED = "SEND_TIME_REFRESH_NOT_REQUIRED"
REFRESH_NOT_ENABLED = "SEND_TIME_REFRESH_NOT_ENABLED"
REFRESH_BUDGET_EXHAUSTED = "SEND_TIME_REFRESH_BUDGET_EXHAUSTED"
REFRESH_ELIGIBLE = "SEND_TIME_REFRESH_ELIGIBLE"


def send_time_refresh_decision(
    *,
    market_all_present: bool,
    attempts_used: int,
    policy: object = None,
    max_attempts: int = SEND_TIME_REFRESH_MAX_ATTEMPTS,
) -> str:
    """Whether ONE bounded priority refresh may run before compose.

    Stale market data can never compose either way; this only decides whether
    the candidate gets one priority attempt to become fresh before the tick
    gives up on it.  A refusal never discards the candidate.
    """

    if bool(market_all_present):
        return REFRESH_NOT_REQUIRED
    if not is_phx1_parity(policy):
        return REFRESH_NOT_ENABLED
    try:
        used = int(attempts_used)
    except (TypeError, ValueError):
        used = max_attempts
    if used >= max(0, int(max_attempts)):
        return REFRESH_BUDGET_EXHAUSTED
    return REFRESH_ELIGIBLE


# --- Counters --------------------------------------------------------------

COUNTER_NAMES: Tuple[str, ...] = (
    "would_have_blocked_under_legacy_activation",
    "sent_without_activation_proof",
    "fee_lifecycle_shadow_warnings",
    "send_time_refresh_attempted",
    "send_time_refresh_succeeded",
    "send_time_refresh_failed",
    "extended_watch_candidates",
    "candidates_reactivated_after_one_hour",
)


@dataclass
class Phx1ParityCounters:
    """Closed-set counters for the parity policy.  Never raises."""

    policy: str = ALERT_POLICY_LEGACY
    _counts: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.policy = normalize_alert_policy(self.policy)
        self._counts = {name: 0 for name in COUNTER_NAMES}

    def increment(self, name: object, amount: int = 1) -> None:
        if not isinstance(name, str) or name not in self._counts:
            return
        try:
            step = int(amount)
        except (TypeError, ValueError):
            return
        self._counts[name] += step

    def get(self, name: object) -> int:
        if not isinstance(name, str):
            return 0
        return int(self._counts.get(name, 0))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "PHX2_ALERT_POLICY_COUNTERS",
            "schema_version": POLICY_SCHEMA_VERSION,
            "alert_policy": self.policy,
            **{name: int(self._counts[name]) for name in COUNTER_NAMES},
        }


# --- Observability projection ---------------------------------------------

STATUS_NOT_PROVEN = "NOT_PROVEN"
STATUS_PROVEN = "PROVEN"
STATUS_COMPLETE = "COMPLETE"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_FRESH = "FRESH"
STATUS_STALE = "STALE"


def condition_record(
    condition: object, status: object, *, policy: object = None
) -> Dict[str, str]:
    """One ``{status, enforcement}`` row.

    The enforcement label comes from the policy matrix, NEVER from the status
    text, so a shadow condition can never be rendered as blocked.
    """

    return {
        "status": str(status),
        "enforcement": enforcement_for(condition, policy=policy),
    }


def observability_matrix(
    *,
    activation_status: object,
    fee_lifecycle_status: object,
    ath_coverage_status: object,
    market_freshness_status: object,
    policy: object = None,
) -> Dict[str, Dict[str, str]]:
    """The internal per-candidate enforcement view used by artifacts."""

    return {
        "activation": condition_record(
            CONDITION_ACTIVATION_PROVEN, activation_status, policy=policy),
        "fee_lifecycle": condition_record(
            CONDITION_FEE_GATE_LIFECYCLE_IMMATURE,
            fee_lifecycle_status, policy=policy),
        "ath_coverage": condition_record(
            CONDITION_ATH_COVERAGE, ath_coverage_status, policy=policy),
        "market_freshness": condition_record(
            CONDITION_MARKET_FRESHNESS, market_freshness_status, policy=policy),
    }


def policy_matrix(policy: object = None) -> Dict[str, Any]:
    """Full closed-set hard/shadow/presentation matrix for artifacts."""

    mode = normalize_alert_policy(policy)
    return {
        "kind": "PHX2_ALERT_POLICY_MATRIX",
        "schema_version": POLICY_SCHEMA_VERSION,
        "alert_policy": mode,
        "watch_ttl_seconds": watch_ttl_seconds(mode),
        "conditions": {
            condition: enforcement_for(condition, policy=mode)
            for condition in ALERT_POLICY_CONDITIONS
        },
        "relaxed_versus_legacy": list(
            PHX1_PARITY_RELAXED_CONDITIONS
            if mode == ALERT_POLICY_PHX1_PARITY else ()),
        "non_relaxable_conditions": list(NON_RELAXABLE_CONDITIONS),
    }


# --- Process-wide binding --------------------------------------------------
# ``activation_proof_is_eligible`` is called deep inside the committed compose
# path with no policy argument available at the call site, and WatchEntry is a
# persisted dataclass whose schema must not gain a field.  The session binds the
# selected policy exactly once at startup; everything else defaults to LEGACY,
# so an unbound process behaves byte-identically to the committed build.

_BOUND_POLICY: str = ALERT_POLICY_LEGACY


def bind_alert_policy(value: object) -> str:
    """Bind the process-wide alert policy.  Validated; returns the normalized name."""

    global _BOUND_POLICY
    _BOUND_POLICY = normalize_alert_policy(value)
    return _BOUND_POLICY


def current_alert_policy() -> str:
    return _BOUND_POLICY


def resolve_policy(policy: object = None) -> str:
    """Explicit argument wins; otherwise the process binding; otherwise LEGACY."""

    if policy is None:
        return _BOUND_POLICY
    return normalize_alert_policy(policy)


__all__ = (
    "POLICY_SCHEMA_VERSION",
    "ALERT_POLICY_LEGACY",
    "ALERT_POLICY_PHX1_PARITY",
    "ALERT_POLICY_MODES",
    "ALERT_POLICY_CLI_VALUES",
    "ALERT_POLICY_INVALID",
    "ENFORCEMENT_HARD",
    "ENFORCEMENT_HARD_AT_SEND",
    "ENFORCEMENT_SHADOW",
    "ENFORCEMENT_PRESENTATION",
    "ENFORCEMENT_LEVELS",
    "BLOCKING_ENFORCEMENT_LEVELS",
    "ALERT_POLICY_CONDITIONS",
    "NON_RELAXABLE_CONDITIONS",
    "PHX1_PARITY_RELAXED_CONDITIONS",
    "CONDITION_ACTIVATION_PROVEN",
    "CONDITION_ACTIVATION_MULTIPLIER_LIVE",
    "CONDITION_ACTIVATION_MULTIPLIER_BACKFILL",
    "CONDITION_ACTIVATION_CROSSING_TICK",
    "CONDITION_FEE_GATE_LIFECYCLE_IMMATURE",
    "CONDITION_FEE_PROOF_MISSING",
    "CONDITION_FEE_GATE_SCAM_LIKELY",
    "CONDITION_GLOBAL_FEE_SUPPORT",
    "CONDITION_STRUCTURAL_POLICY",
    "CONDITION_ATH_COVERAGE",
    "CONDITION_MARKET_FRESHNESS",
    "CONDITION_MARKET_RECOVERY_BACKOFF",
    "CONDITION_LIQUIDITY_FLOOR",
    "CONDITION_CANDIDATE_WATCH_TTL",
    "CONDITION_CANDIDATE_EXPIRY",
    "CONDITION_METADATA_READINESS",
    "CONDITION_TIER_LIFETIME_MONOTONICITY",
    "CONDITION_DEDUPE",
    "CONDITION_COMPOSE_AUTHORIZATION",
    "CONDITION_MIGRATION_PROVEN",
    "CONDITION_CURRENT_MARKET_CAP_VALID",
    "CONDITION_CANDIDATE_IDENTITY",
    "CONDITION_DELIVERY_RESERVATION",
    "CONDITION_CREDENTIALS",
    "CONDITION_CHECKPOINT_INTEGRITY",
    "CONDITION_OWNERSHIP_DUPLICATION",
    "LEGACY_WATCH_TTL_SECONDS",
    "PHX1_PARITY_WATCH_TTL_SECONDS",
    "LIVE_ACTIVATION_MULTIPLIER",
    "LEGACY_BACKFILL_ACTIVATION_MULTIPLIER",
    "HEAT_HOT", "HEAT_WARM", "HEAT_COOL", "HEAT_COLD",
    "REFRESH_HEAT_LEVELS",
    "MAX_ADAPTIVE_REFRESH_SECONDS",
    "SEND_TIME_REFRESH_MAX_ATTEMPTS",
    "REFRESH_NOT_REQUIRED",
    "REFRESH_NOT_ENABLED",
    "REFRESH_BUDGET_EXHAUSTED",
    "REFRESH_ELIGIBLE",
    "COUNTER_NAMES",
    "Phx1ParityCounters",
    "STATUS_NOT_PROVEN", "STATUS_PROVEN", "STATUS_COMPLETE",
    "STATUS_INCOMPLETE", "STATUS_FRESH", "STATUS_STALE",
    "normalize_alert_policy",
    "is_phx1_parity",
    "enforcement_for",
    "blocks_compose",
    "watch_ttl_seconds",
    "expected_activation_multiplier",
    "refresh_heat",
    "adaptive_refresh_interval_seconds",
    "heat_interval_seconds",
    "project_market_requests_per_hour",
    "project_watchlist_heat_distribution",
    "send_time_refresh_decision",
    "condition_record",
    "observability_matrix",
    "policy_matrix",
    "bind_alert_policy",
    "current_alert_policy",
    "resolve_policy",
)
