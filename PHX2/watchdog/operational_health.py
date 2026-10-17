"""Operational health matrix: what an operator is told, dimension by dimension.

This module owns the dimension matrix consumed by the canonical watchdog
verdict.  The verdict also carries a control action (continue, bounded restart,
or circuit), but there is no second opinion that can label the system healthy
while these dimensions disagree.  Its central rule is the one the
2026-07-29 acceptance run violated:

    A connected socket is not continuous ingestion, and an in-memory
    watchlist is not durable state.

That run reported ``HEALTHY`` continuously while the live stream had silently
skipped 2,184 slots and 61 consecutive watch-checkpoint writes had failed.
Both facts were present in telemetry; nothing combined them into the operator's
verdict.  Every mandatory dimension below must be healthy for the overall
verdict to be ``HEALTHY``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer import market_plane_health as _mp
from PHX2.free_tier_producer import market_scheduler as _ms
from PHX2.free_tier_producer import provider_backoff as _pb
from PHX2.free_tier_producer import source_continuity as _sc

# -- overall verdicts (closed set) -----------------------------------------
HEALTHY = "HEALTHY"
DEGRADED_RECOVERING = "DEGRADED_RECOVERING"
DEGRADED_TRANSIENT_DURABILITY = "DEGRADED_TRANSIENT_DURABILITY"
#: Sustained provider throttling. Visible, bounded, self-clearing -- and
#: explicitly NOT a reason to stop or restart the producer: the 2026-07-31
#: retest proved that killing a healthy producer over a market-data throttle
#: costs far more than the throttle does.
DEGRADED_PROVIDER_RATE_LIMITED = "DEGRADED_PROVIDER_RATE_LIMITED"
#: Market plane unusable but still INSIDE its bounded grace. Visible and not
#: fatal: short transient degradation must never kill production.
DEGRADED_MARKET_PLANE = "DEGRADED_MARKET_PLANE"
DEGRADED_AUTHORITATIVE_SUPPLY = "DEGRADED_AUTHORITATIVE_SUPPLY"
UNHEALTHY_GAP_UNRESOLVED = "UNHEALTHY_GAP_UNRESOLVED"
UNHEALTHY_CHECKPOINT_DURABILITY = "UNHEALTHY_CHECKPOINT_DURABILITY"
UNHEALTHY_SCHEDULER_STARVATION = "UNHEALTHY_SCHEDULER_STARVATION"
#: The market plane has been unusable past its bounded grace.  A live PID and
#: a connected Helius socket say nothing about whether market data is arriving;
#: on 2026-08-02 both were true for 4h38m while every candidate was refused.
UNHEALTHY_MARKET_PLANE_BLIND = "UNHEALTHY_MARKET_PLANE_BLIND"
#: Scheduler-charged and transport-dialled request counts disagree by an amount
#: no documented category explains.  Never smoothed by a tolerance.
UNHEALTHY_REQUEST_ACCOUNTING = "UNHEALTHY_REQUEST_ACCOUNTING"
UNHEALTHY_CREDENTIALS_OR_INTEGRITY = "UNHEALTHY_CREDENTIALS_OR_INTEGRITY"
UNHEALTHY_AUTHORITATIVE_SUPPLY = "UNHEALTHY_AUTHORITATIVE_SUPPLY"
UNHEALTHY_DELIVERY_OWNER = "UNHEALTHY_DELIVERY_OWNER"
UNHEALTHY_LEDGER = "UNHEALTHY_LEDGER"
UNHEALTHY_MULTIPLE_CAUSES = "UNHEALTHY_MULTIPLE_CAUSES"
UNHEALTHY_TRANSPORT_DISCONNECTED = "UNHEALTHY_TRANSPORT_DISCONNECTED"
STOPPED = "STOPPED"

OPERATIONAL_STATUSES = (
    HEALTHY, DEGRADED_RECOVERING, DEGRADED_TRANSIENT_DURABILITY,
    DEGRADED_PROVIDER_RATE_LIMITED, DEGRADED_MARKET_PLANE,
    DEGRADED_AUTHORITATIVE_SUPPLY,
    UNHEALTHY_GAP_UNRESOLVED, UNHEALTHY_CHECKPOINT_DURABILITY,
    UNHEALTHY_SCHEDULER_STARVATION, UNHEALTHY_DELIVERY_OWNER,
    UNHEALTHY_LEDGER, UNHEALTHY_MULTIPLE_CAUSES,
    UNHEALTHY_TRANSPORT_DISCONNECTED,
    UNHEALTHY_MARKET_PLANE_BLIND, UNHEALTHY_REQUEST_ACCOUNTING,
    UNHEALTHY_CREDENTIALS_OR_INTEGRITY,
    UNHEALTHY_AUTHORITATIVE_SUPPLY, STOPPED,
)

DEGRADED_STATUSES = frozenset(
    {DEGRADED_RECOVERING, DEGRADED_TRANSIENT_DURABILITY,
     DEGRADED_PROVIDER_RATE_LIMITED, DEGRADED_MARKET_PLANE,
     DEGRADED_AUTHORITATIVE_SUPPLY})
UNHEALTHY_STATUSES = frozenset({
    UNHEALTHY_GAP_UNRESOLVED, UNHEALTHY_CHECKPOINT_DURABILITY,
    UNHEALTHY_SCHEDULER_STARVATION, UNHEALTHY_DELIVERY_OWNER,
    UNHEALTHY_LEDGER, UNHEALTHY_MULTIPLE_CAUSES,
    UNHEALTHY_TRANSPORT_DISCONNECTED,
    UNHEALTHY_MARKET_PLANE_BLIND, UNHEALTHY_REQUEST_ACCOUNTING,
    UNHEALTHY_CREDENTIALS_OR_INTEGRITY,
    UNHEALTHY_AUTHORITATIVE_SUPPLY,
})

#: Which single-unhealthy dimension produces which overall status. Stated as
#: one mapping so a new dimension cannot silently fall through to
#: UNHEALTHY_MULTIPLE_CAUSES when it is the only failure.
_SOLE_UNHEALTHY_STATUS = {
    "source_continuity": UNHEALTHY_GAP_UNRESOLVED,
    "watch_checkpoint_durability": UNHEALTHY_CHECKPOINT_DURABILITY,
    "transport_connection": UNHEALTHY_TRANSPORT_DISCONNECTED,
    "scheduler": UNHEALTHY_SCHEDULER_STARVATION,
    "market_plane": UNHEALTHY_MARKET_PLANE_BLIND,
    "request_accounting": UNHEALTHY_REQUEST_ACCOUNTING,
    "credentials_integrity": UNHEALTHY_CREDENTIALS_OR_INTEGRITY,
    "authoritative_supply": UNHEALTHY_AUTHORITATIVE_SUPPLY,
    "telegram_ownership": UNHEALTHY_DELIVERY_OWNER,
    "ledger": UNHEALTHY_LEDGER,
}

# -- dimension verdicts ----------------------------------------------------
DIM_HEALTHY = "HEALTHY"
DIM_DEGRADED = "DEGRADED"
DIM_UNHEALTHY = "UNHEALTHY"
DIM_NOT_APPLICABLE = "NOT_APPLICABLE"

# -- causes (closed set) ---------------------------------------------------
CAUSE_TRANSPORT_DISCONNECTED = "TRANSPORT_DISCONNECTED"
CAUSE_SOURCE_GAP_RECOVERING = "SOURCE_GAP_RECOVERING"
CAUSE_SOURCE_GAP_UNRESOLVED = "SOURCE_GAP_UNRESOLVED"
CAUSE_CHECKPOINT_RETRYING = "WATCH_CHECKPOINT_RETRYING"
CAUSE_CHECKPOINT_STRUCTURAL = "WATCH_CHECKPOINT_STRUCTURAL_FAILURE"
CAUSE_CHECKPOINT_CONSECUTIVE = "WATCH_CHECKPOINT_CONSECUTIVE_FAILURES"
CAUSE_STATE_NOT_DURABLE = "TRACKED_STATE_NOT_CHECKPOINTED"
CAUSE_CURSOR_DURABILITY = "CURSOR_CHECKPOINT_DURABILITY_DEGRADED"
CAUSE_EPOCH_NOT_HEALTHY = "EPOCH_NOT_HEALTHY"
CAUSE_CIRCUIT_OPEN = "CIRCUIT_OPEN"
CAUSE_SCHEDULER_DEGRADED = "MARKET_SCHEDULER_DEGRADED"
CAUSE_SCHEDULER_STARVED = "MARKET_OBSERVATION_STARVED_BEYOND_BOUND"
CAUSE_MARKET_PLANE_BLIND = "MARKET_PLANE_BLIND_BEYOND_GRACE"
CAUSE_MARKET_PLANE_DEGRADED = "MARKET_PLANE_DEGRADED_WITHIN_GRACE"
CAUSE_REQUEST_ACCOUNTING_UNRECONCILED = (
    "MARKET_REQUEST_ACCOUNTING_UNRECONCILED")
CAUSE_CREDENTIALS_OR_INTEGRITY = "CREDENTIALS_OR_INTEGRITY_FAILURE"
CAUSE_AUTHORITATIVE_SUPPLY_PENDING = "AUTHORITATIVE_SUPPLY_PENDING"
CAUSE_AUTHORITATIVE_SUPPLY_SYSTEMIC = (
    "AUTHORITATIVE_SUPPLY_UNAVAILABLE_BEYOND_GRACE")
CAUSE_OWNERSHIP_AMBIGUOUS = "PRODUCER_OWNERSHIP_AMBIGUOUS"
CAUSE_DELIVERY_OWNER_AMBIGUOUS = "TELEGRAM_OWNERSHIP_AMBIGUOUS"
CAUSE_LEDGER_INTEGRITY = "LEDGER_INTEGRITY_FAILURE"
CAUSE_PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMIT_DEGRADED"
CAUSE_PROVIDER_RATE_LIMIT_BACKOFF = "PROVIDER_RATE_LIMIT_BACKOFF"

#: A scheduler may be DEGRADED indefinitely without being broken -- a provider
#: throttling for a while is degraded, not unhealthy.  Work the planner would
#: act on and has not served for THIS long is starvation, and starvation must
#: not be allowed to report healthy indefinitely.
SCHEDULER_STARVATION_BOUND_SECONDS = 900.0

#: A single transient checkpoint write failure is DEGRADED, not fatal -- the
#: prior valid generation always survives. This many CONSECUTIVE transient
#: failures means the state genuinely is not being made durable any more.
CONSECUTIVE_CHECKPOINT_FAILURE_LIMIT = 5


@dataclass
class DimensionVerdict:
    name: str
    verdict: str
    causes: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return self.verdict in (DIM_HEALTHY, DIM_NOT_APPLICABLE)


@dataclass
class OperationalVerdict:
    status: str
    primary_cause: Optional[str]
    secondary_causes: List[str]
    dimensions: List[DimensionVerdict]

    @property
    def healthy(self) -> bool:
        return self.status == HEALTHY

    def dimension(self, name: str) -> Optional[DimensionVerdict]:
        for item in self.dimensions:
            if item.name == name:
                return item
        return None

    def to_record(self) -> Dict[str, Any]:
        return {
            "operational_status": self.status,
            "primary_cause": self.primary_cause,
            "secondary_causes": list(self.secondary_causes),
            "dimensions": [
                {"name": d.name, "verdict": d.verdict,
                 "causes": list(d.causes), "detail": dict(d.detail)}
                for d in self.dimensions],
        }


def _flag(value: object, default: bool = False) -> bool:
    return bool(value) if isinstance(value, bool) else default


def _int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) \
        else default


def evaluate_source_continuity(telemetry: Mapping[str, Any]) -> DimensionVerdict:
    """Source continuity is independent of whether the socket is up."""

    state = telemetry.get("source_continuity_state")
    if not isinstance(state, str) or state not in _sc.CONTINUITY_STATES:
        snap = telemetry.get("source_continuity")
        state = (snap.get("continuity_state")
                 if isinstance(snap, Mapping) else None)
    if not isinstance(state, str) or state not in _sc.CONTINUITY_STATES:
        # Absent continuity evidence is never treated as proof of continuity.
        return DimensionVerdict(
            "source_continuity", DIM_UNHEALTHY,
            [CAUSE_SOURCE_GAP_UNRESOLVED],
            {"continuity_state": "UNKNOWN"})
    detail = {
        "continuity_state": state,
        "gap_from_slot": telemetry.get("grpc_gap_from_slot"),
        "gap_to_slot": telemetry.get("grpc_gap_to_slot"),
        "gap_size_slots": telemetry.get("grpc_gap_size_slots"),
        "unresolved_slot_total": telemetry.get(
            "grpc_gap_unresolved_slot_total"),
    }
    if state == _sc.NO_GAP:
        return DimensionVerdict("source_continuity", DIM_HEALTHY, [], detail)
    if state in _sc.TERMINAL_GAP_STATES:
        return DimensionVerdict(
            "source_continuity", DIM_UNHEALTHY,
            [CAUSE_SOURCE_GAP_UNRESOLVED], detail)
    return DimensionVerdict(
        "source_continuity", DIM_DEGRADED,
        [CAUSE_SOURCE_GAP_RECOVERING], detail)


def evaluate_watch_checkpoint(summary: Mapping[str, Any]) -> DimensionVerdict:
    """Watch-checkpoint durability, including 'is current state durable'."""

    structural = _int(summary.get("checkpoint_structural_failed_total"))
    consecutive = _int(summary.get("checkpoint_consecutive_failures"))
    durable_count = _int(summary.get("checkpoint_durable_candidate_count"), -1)
    tracked = _int(summary.get("watchlist_count"), -1)
    detail = {
        "attempts": _int(summary.get("checkpoint_write_attempted_total")),
        "successes": _int(summary.get("checkpoint_write_succeeded_total")),
        "transient_failures": _int(
            summary.get("checkpoint_write_retryable_failed_total")),
        "structural_failures": structural,
        "consecutive_failures": consecutive,
        "last_success_utc": summary.get("checkpoint_last_success_utc"),
        "last_failure_detail": summary.get("checkpoint_last_failure_detail"),
        "durable_candidate_count": (
            durable_count if durable_count >= 0 else None),
        "current_candidate_count": tracked if tracked >= 0 else None,
        "latest_verified_generation": _int(
            summary.get("checkpoint_last_verified_generation")),
    }
    if durable_count >= 0 and tracked >= 0:
        detail["checkpoint_lag_candidates"] = max(0, tracked - durable_count)

    causes: List[str] = []
    if structural > 0:
        causes.append(CAUSE_CHECKPOINT_STRUCTURAL)
    if consecutive >= CONSECUTIVE_CHECKPOINT_FAILURE_LIMIT:
        causes.append(CAUSE_CHECKPOINT_CONSECUTIVE)
    if causes:
        return DimensionVerdict(
            "watch_checkpoint_durability", DIM_UNHEALTHY, causes, detail)
    # Tracked state that no verified generation represents is not durable,
    # even when the last write "succeeded" long ago.
    if consecutive > 0:
        return DimensionVerdict(
            "watch_checkpoint_durability", DIM_DEGRADED,
            [CAUSE_CHECKPOINT_RETRYING], detail)
    if tracked > 0 and durable_count == 0 \
            and _int(summary.get("checkpoint_write_succeeded_total")) == 0:
        return DimensionVerdict(
            "watch_checkpoint_durability", DIM_UNHEALTHY,
            [CAUSE_STATE_NOT_DURABLE], detail)
    return DimensionVerdict(
        "watch_checkpoint_durability", DIM_HEALTHY, [], detail)


def evaluate_provider_rate_limit(
    telemetry: Mapping[str, Any],
    heartbeat: Optional[Mapping[str, Any]] = None,
) -> DimensionVerdict:
    """Provider throttling: visible, bounded, NEVER unhealthy.

    A provider answering "slow down" is a recoverable condition local to that
    provider. It says nothing about ingestion continuity, durability, or the
    candidates already being watched, so it can be DEGRADED but is never
    allowed to reach UNHEALTHY and never opens the circuit. Absent telemetry
    is treated as "no throttle observed": unlike continuity, a missing
    throttle record is not evidence of a hidden failure.
    """

    block: Any = None
    for source in (telemetry, heartbeat or {}):
        if not isinstance(source, Mapping):
            continue
        candidate = source.get("rate_limit")
        if not isinstance(candidate, Mapping):
            budget = source.get("credit_budget")
            candidate = (budget.get("rate_limit")
                         if isinstance(budget, Mapping) else None)
        if isinstance(candidate, Mapping):
            block = candidate
            break
    if not isinstance(block, Mapping):
        return DimensionVerdict("market_provider", DIM_NOT_APPLICABLE, [], {})
    status = block.get("status")
    detail = {
        "status": status,
        "observed_429_total": _int(block.get("observed_429_total")),
        "degradation_threshold": _int(block.get("degradation_threshold")),
    }
    for scope in ("market_primary", "discovery_polling"):
        snapshot = block.get(scope)
        if isinstance(snapshot, Mapping):
            detail[scope] = {
                "status": snapshot.get("status"),
                "consecutive_throttles": _int(
                    snapshot.get("consecutive_throttles")),
                "throttles_total": _int(snapshot.get("throttles_total")),
                "recoveries_total": _int(snapshot.get("recoveries_total")),
                "requests_skipped_total": _int(
                    snapshot.get("requests_skipped_total")),
                "backoff_remaining_seconds": snapshot.get(
                    "backoff_remaining_seconds"),
            }
    if _flag(block.get("degraded")) or status == _pb.PROVIDER_RATE_LIMIT_DEGRADED:
        return DimensionVerdict(
            "market_provider", DIM_DEGRADED,
            [CAUSE_PROVIDER_RATE_LIMITED], detail)
    if status == _pb.PROVIDER_RATE_LIMIT_BACKOFF:
        # Inside a bounded window and expected to clear on its own: reported,
        # not escalated.
        return DimensionVerdict("market_provider", DIM_HEALTHY, [], detail)
    return DimensionVerdict("market_provider", DIM_HEALTHY, [], detail)


def evaluate_market_plane(telemetry: Mapping[str, Any]) -> DimensionVerdict:
    """Can this producer still observe the market at all?

    This is the dimension whose absence let the 2026-08-02 run report itself
    healthy for four and a half hours on the strength of a live PID and a
    connected Helius socket.  A producer whose market plane is blind past its
    bounded grace is UNHEALTHY, full stop -- ingestion continuity and process
    ownership say nothing about it.

    Absent telemetry is NOT treated as blindness: an older producer that never
    publishes the field would otherwise be declared unhealthy for a condition
    it cannot report.  It is treated as not-applicable, exactly like the
    scheduler dimension handles a missing state.
    """

    status = telemetry.get("market_plane_status")
    if not isinstance(status, str) or status not in _mp.MARKET_PLANE_STATUSES:
        return DimensionVerdict(
            "market_plane", DIM_NOT_APPLICABLE, [],
            {"market_plane_status": None})
    reasons = telemetry.get("market_plane_reasons")
    reasons = [str(r) for r in reasons] if isinstance(reasons, (list, tuple)) else []
    detail = {
        "market_plane_status": status,
        "market_plane_reasons": reasons,
        "blind_age_seconds": telemetry.get("market_plane_blind_age_seconds"),
        "grace_seconds": telemetry.get("market_plane_grace_seconds"),
    }
    if status == _mp.MARKET_PLANE_BLIND:
        return DimensionVerdict(
            "market_plane", DIM_UNHEALTHY,
            [CAUSE_MARKET_PLANE_BLIND] + reasons, detail)
    if status == _mp.MARKET_PLANE_DEGRADED:
        # Inside grace: visible, bounded, and explicitly NOT fatal. A provider
        # hiccup must not kill a healthy 24/7 producer.
        return DimensionVerdict(
            "market_plane", DIM_DEGRADED,
            [CAUSE_MARKET_PLANE_DEGRADED], detail)
    return DimensionVerdict("market_plane", DIM_HEALTHY, [], detail)


def evaluate_request_accounting(telemetry: Mapping[str, Any]) -> DimensionVerdict:
    """Scheduler-charged vs transport-dialled requests must reconcile exactly.

    ``unreconciled_delta`` is whatever the documented categories fail to
    explain.  A nonzero value means the budget is being spent somewhere nobody
    is counting -- which is precisely how a 5,000-unit budget expired against
    3,472 HTTP calls -- so it degrades health rather than being absorbed by a
    tolerance.
    """

    delta = telemetry.get("unreconciled_delta")
    scheduler_delta = telemetry.get("scheduler_charge_delta")
    if (not isinstance(delta, int) or isinstance(delta, bool)) \
            and (not isinstance(scheduler_delta, int)
                 or isinstance(scheduler_delta, bool)):
        return DimensionVerdict(
            "request_accounting", DIM_NOT_APPLICABLE, [],
            {"unreconciled_delta": None, "scheduler_charge_delta": None})
    provider_delta = int(delta) if isinstance(delta, int) \
        and not isinstance(delta, bool) else 0
    charge_delta = int(scheduler_delta) if isinstance(scheduler_delta, int) \
        and not isinstance(scheduler_delta, bool) else 0
    detail = {
        "unreconciled_delta": provider_delta,
        "scheduler_charge_delta": charge_delta,
        "scheduler_physical_requests_total": telemetry.get(
            "scheduler_physical_requests_total"),
        "transport_physical_requests_total": telemetry.get(
            "transport_physical_requests_total"),
        "reconciled_total": telemetry.get("reconciled_total"),
        "reconciliation_reasons": telemetry.get("reconciliation_reasons"),
    }
    if provider_delta != 0 or charge_delta != 0:
        return DimensionVerdict(
            "request_accounting", DIM_UNHEALTHY,
            [CAUSE_REQUEST_ACCOUNTING_UNRECONCILED], detail)
    return DimensionVerdict("request_accounting", DIM_HEALTHY, [], detail)


def evaluate_authoritative_supply(
    telemetry: Mapping[str, Any],
) -> DimensionVerdict:
    """Authenticated supply is required only when its bridge is published."""

    systemic = telemetry.get("supply_systemic_failure")
    if not isinstance(systemic, bool):
        return DimensionVerdict(
            "authoritative_supply", DIM_NOT_APPLICABLE, [],
            {"supply_systemic_failure": None})
    pending = _int(telemetry.get("supply_pending"))
    detail = {
        "supply_pending": pending,
        "supply_pending_reasons": telemetry.get("supply_pending_reasons"),
        "supply_oldest_pending_age_seconds": telemetry.get(
            "supply_oldest_pending_age_seconds"),
        "supply_systemic_pending_seconds": telemetry.get(
            "supply_systemic_pending_seconds"),
        "supply_systemic_failure": systemic,
        "supply_successes": _int(telemetry.get("supply_successes")),
        "supply_central_observations": _int(
            telemetry.get("supply_central_observations")),
    }
    if systemic:
        return DimensionVerdict(
            "authoritative_supply", DIM_UNHEALTHY,
            [CAUSE_AUTHORITATIVE_SUPPLY_SYSTEMIC], detail)
    if pending > 0:
        return DimensionVerdict(
            "authoritative_supply", DIM_DEGRADED,
            [CAUSE_AUTHORITATIVE_SUPPLY_PENDING], detail)
    return DimensionVerdict("authoritative_supply", DIM_HEALTHY, [], detail)


def evaluate_operational_health(
    *,
    telemetry: Mapping[str, Any],
    watchlist_summary: Mapping[str, Any],
    process_ownership_ok: bool = True,
    telegram_owner_ok: bool = True,
    circuit_closed: bool = True,
    scheduler_state: Optional[str] = None,
    scheduler_starved_age_seconds: Optional[float] = None,
    ledger_ok: bool = True,
    credentials_integrity_ok: bool = True,
    credentials_integrity_status: Optional[str] = None,
    epoch_healthy: Optional[bool] = None,
    stopped: bool = False,
) -> OperationalVerdict:
    """Combine every dimension into ONE operator-facing verdict."""

    dims: List[DimensionVerdict] = []
    if stopped:
        return OperationalVerdict(STOPPED, None, [], dims)

    dims.append(DimensionVerdict(
        "process_ownership",
        DIM_HEALTHY if process_ownership_ok else DIM_UNHEALTHY,
        [] if process_ownership_ok else [CAUSE_OWNERSHIP_AMBIGUOUS]))

    transport_connected = _flag(telemetry.get("transport_connected"))
    dims.append(DimensionVerdict(
        "transport_connection",
        DIM_HEALTHY if transport_connected else DIM_UNHEALTHY,
        [] if transport_connected else [CAUSE_TRANSPORT_DISCONNECTED],
        {"status": telemetry.get("status")}))

    continuity = evaluate_source_continuity(telemetry)
    dims.append(continuity)
    dims.append(DimensionVerdict(
        "recovery_status", DIM_HEALTHY, [],
        {"recovery_status": telemetry.get("recovery_status")}))

    cursor_ok = str(telemetry.get("cursor_durability_status")
                    or "CHECKPOINT_DURABILITY_HEALTHY") \
        == "CHECKPOINT_DURABILITY_HEALTHY"
    dims.append(DimensionVerdict(
        "cursor_durability",
        DIM_HEALTHY if cursor_ok else DIM_DEGRADED,
        [] if cursor_ok else [CAUSE_CURSOR_DURABILITY]))

    dims.append(evaluate_watch_checkpoint(watchlist_summary))

    # ``SCHEDULER_READY`` is the real healthy token, imported rather than
    # restated: this compared against a literal "SCHEDULER_HEALTHY" that no
    # owner has ever produced, so every healthy scheduler classified DEGRADED.
    starved_age = (float(scheduler_starved_age_seconds)
                   if isinstance(scheduler_starved_age_seconds, (int, float))
                   and not isinstance(scheduler_starved_age_seconds, bool)
                   else None)
    scheduler_detail = {
        "scheduler_state": scheduler_state,
        "starved_age_seconds": starved_age,
        "starvation_bound_seconds": SCHEDULER_STARVATION_BOUND_SECONDS,
    }
    if scheduler_state is None:
        dims.append(DimensionVerdict(
            "scheduler", DIM_NOT_APPLICABLE, [], scheduler_detail))
    elif starved_age is not None \
            and starved_age >= SCHEDULER_STARVATION_BOUND_SECONDS:
        # Work the planner would serve and has not: never healthy, and never
        # merely degraded forever.
        dims.append(DimensionVerdict(
            "scheduler", DIM_UNHEALTHY,
            [CAUSE_SCHEDULER_STARVED], scheduler_detail))
    elif str(scheduler_state) == _ms.SCHEDULER_READY:
        dims.append(DimensionVerdict(
            "scheduler", DIM_HEALTHY, [], scheduler_detail))
    else:
        dims.append(DimensionVerdict(
            "scheduler", DIM_DEGRADED,
            [CAUSE_SCHEDULER_DEGRADED], scheduler_detail))

    dims.append(evaluate_market_plane(telemetry))
    dims.append(evaluate_request_accounting(telemetry))
    dims.append(evaluate_authoritative_supply(telemetry))

    dims.append(DimensionVerdict(
        "telegram_ownership",
        DIM_HEALTHY if telegram_owner_ok else DIM_UNHEALTHY,
        [] if telegram_owner_ok else [CAUSE_DELIVERY_OWNER_AMBIGUOUS]))

    dims.append(DimensionVerdict(
        "ledger",
        DIM_HEALTHY if ledger_ok else DIM_UNHEALTHY,
        [] if ledger_ok else [CAUSE_LEDGER_INTEGRITY]))

    dims.append(DimensionVerdict(
        "credentials_integrity",
        DIM_HEALTHY if credentials_integrity_ok else DIM_UNHEALTHY,
        [] if credentials_integrity_ok
        else [CAUSE_CREDENTIALS_OR_INTEGRITY],
        {"market_credential_status": credentials_integrity_status}))

    dims.append(DimensionVerdict(
        "epoch",
        DIM_NOT_APPLICABLE if epoch_healthy is None
        else (DIM_HEALTHY if epoch_healthy else DIM_UNHEALTHY),
        [] if epoch_healthy in (None, True) else [CAUSE_EPOCH_NOT_HEALTHY]))

    dims.append(DimensionVerdict(
        "circuit",
        DIM_HEALTHY if circuit_closed else DIM_UNHEALTHY,
        [] if circuit_closed else [CAUSE_CIRCUIT_OPEN]))

    # Appended last on purpose: an existing degraded dimension keeps naming the
    # overall status exactly as it did before, so a throttle can never mask a
    # continuity or durability problem.
    dims.append(evaluate_provider_rate_limit(telemetry, watchlist_summary))

    unhealthy = [d for d in dims if d.verdict == DIM_UNHEALTHY]
    degraded = [d for d in dims if d.verdict == DIM_DEGRADED]
    causes: List[str] = []
    for d in unhealthy + degraded:
        causes.extend(d.causes)

    if len(unhealthy) > 1:
        status = UNHEALTHY_MULTIPLE_CAUSES
    elif unhealthy:
        status = _SOLE_UNHEALTHY_STATUS.get(
            unhealthy[0].name, UNHEALTHY_MULTIPLE_CAUSES)
    elif degraded:
        first = degraded[0].name
        if first == "source_continuity":
            status = DEGRADED_RECOVERING
        elif first == "market_provider":
            status = DEGRADED_PROVIDER_RATE_LIMITED
        elif first == "market_plane":
            status = DEGRADED_MARKET_PLANE
        elif first == "authoritative_supply":
            status = DEGRADED_AUTHORITATIVE_SUPPLY
        else:
            status = DEGRADED_TRANSIENT_DURABILITY
    else:
        status = HEALTHY

    primary = causes[0] if causes else None
    return OperationalVerdict(status, primary, causes[1:], dims)


def circuit_should_open(verdict: OperationalVerdict) -> Tuple[bool, str]:
    """Immediate circuit decision consumed by :class:`Watchdog` control.

    Durability loss opens immediately because restarting could resurrect stale
    state. Market blindness, scheduler starvation and request-accounting faults
    instead select the daemon's existing bounded restart action; persistence
    exhausts that durable budget and opens the circuit without an unbounded
    restart loop. An unresolved historical gap remains unhealthy but is not
    repairable by restarting at live head.
    """

    checkpoint = verdict.dimension("watch_checkpoint_durability")
    if checkpoint is not None and checkpoint.verdict == DIM_UNHEALTHY:
        return True, (checkpoint.causes[0] if checkpoint.causes
                      else CAUSE_STATE_NOT_DURABLE)
    return False, ""
