"""RUN_FOREVER market-budget semantics and the ONE physical-request counter.

Two defects proven by the 2026-08-02 five-hour production run live here.

**1. A lifetime cap on an indefinite deployment.**  The managed 24/7 launcher
states ``--run-forever`` and the explicit ``--max-sends-per-run 0`` UNBOUNDED
send sentinel, but said nothing at all about the market-request cap, so the
producer silently inherited the bounded base default of 5,000.  A monotonic,
never-refilling counter reached it ~22 minutes after launch; for the remaining
4h38m no market job could be enqueued, ``priority_refresh`` answered
``MARKET_PROVIDER_BUDGET_EXHAUSTED`` 15,523 times, 15,419 of 15,770 parity
evaluations ended ``NO_SEND_MARKET_INCOMPLETE`` -- and the producer went on
reporting itself alive.  A run with no clock boundary must not carry a
lifetime spend boundary; :data:`MARKET_REQUEST_CAP_UNBOUNDED` is the explicit
sentinel that says so, deliberately shaped exactly like the send-cap sentinel
it sits beside.

**2. The budget was charged for work that never cost anything.**  The scheduler
charged one unit when it *dequeued* a job, before the provider client was even
called.  That client caches (8 s TTL), skips on provider backoff, and refuses
past a deadline -- all of which return without dialling anything.  So the run
burned 5,000 budget units while the transport made 3,472 HTTP calls, and the
mismatch ran in BOTH directions:

    scheduler charged            5,000   (4,498 price + 502 overview)
    of which reached HTTP        1,647   (1,190 price + 457 overview)
    charged but never dialled    3,353   (paid-client cache hits)
    dialled but never charged    1,825   (OHLCV ATH hydration)
    transport HTTP total         3,472

Charging at dequeue is what made a 5,000-unit budget die in 22 minutes.  This
module's :class:`MarketPhysicalRequestMeter` is the single authoritative ticket
ledger for work that crossed the physical provider dispatch boundary.  Every
dialled request receives an immutable identity carrying its exact scheduler job
and origin; every early return that dialled nothing is counted separately.  A
cache hit therefore costs zero, a coalesced request costs one, and OHLCV
hydration is a first-class origin rather than an unexplained delta.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

# --------------------------------------------------------------------------- #
# budget modes (closed set)
# --------------------------------------------------------------------------- #

#: Explicit "no lifetime market-request ceiling" sentinel.  Zero, not a large
#: number: an arbitrary bigger cap is still a cap, and still expires -- it only
#: moves the outage further from the change that caused it.  Mirrors
#: ``free_tier_credit_budget.SEND_CAP_UNBOUNDED`` on purpose so the managed
#: launcher states both boundaries the same way.
MARKET_REQUEST_CAP_UNBOUNDED = 0

MARKET_BUDGET_MODE_UNBOUNDED = "UNBOUNDED"
MARKET_BUDGET_MODE_BOUNDED_LIFETIME = "BOUNDED_LIFETIME"
MARKET_BUDGET_MODES = (
    MARKET_BUDGET_MODE_UNBOUNDED,
    MARKET_BUDGET_MODE_BOUNDED_LIFETIME,
)


def market_budget_mode(limit: object) -> str:
    """Classify a configured market-request limit."""

    return (MARKET_BUDGET_MODE_UNBOUNDED
            if _is_unbounded(limit) else MARKET_BUDGET_MODE_BOUNDED_LIFETIME)


def _is_unbounded(limit: object) -> bool:
    return (isinstance(limit, int) and not isinstance(limit, bool)
            and int(limit) == MARKET_REQUEST_CAP_UNBOUNDED)


def market_budget_status(limit: object, consumed: object = 0) -> Dict[str, Any]:
    """The operator-facing budget block carried by status and heartbeat.

    ``reset_window_seconds`` is always ``None``: the selected design is the
    unbounded sentinel, not a refilling window, so there is no window to
    report.  The key is present anyway so a future windowed mode does not
    change the shape of the contract.
    """

    mode = market_budget_mode(limit)
    unbounded = mode == MARKET_BUDGET_MODE_UNBOUNDED
    used = _nonneg(consumed)
    return {
        "market_budget_mode": mode,
        "market_budget_limit": (
            None if unbounded else _nonneg(limit)),
        "market_budget_limit_display": (
            MARKET_BUDGET_MODE_UNBOUNDED if unbounded else str(_nonneg(limit))),
        "market_budget_reset_window_seconds": None,
        "market_budget_physical_requests_consumed": used,
        "market_budget_remaining": (
            None if unbounded else max(0, _nonneg(limit) - used)),
    }


def _nonneg(value: object) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return number if number >= 0 else 0


# --------------------------------------------------------------------------- #
# RUN_FOREVER contract
# --------------------------------------------------------------------------- #

REFUSAL_RUN_FOREVER_BOUNDED_MARKET_BUDGET = (
    "RUN_FOREVER_MARKET_BUDGET_BOUNDED")


def run_forever_market_budget_refusal(
    *, run_forever: bool, max_market_requests_total: object,
) -> Optional[str]:
    """The one predicate that decides whether this combination may start.

    A bounded one-shot or test run keeps its finite lifetime cap; that is the
    protective default and nothing here changes it.  What is refused is the
    exact production combination that failed: no clock boundary plus a
    non-refilling lifetime spend boundary.
    """

    if not run_forever:
        return None
    if _is_unbounded(max_market_requests_total):
        return None
    return REFUSAL_RUN_FOREVER_BOUNDED_MARKET_BUDGET


# --------------------------------------------------------------------------- #
# the one authoritative physical-request counter
# --------------------------------------------------------------------------- #

#: Endpoint-shaped physical categories.  Scheduler-initiated work is the price
#: and overview planes; OHLCV is ATH hydration, which is physical spend the
#: scheduler never initiates and therefore must never be charged for.
PHYSICAL_PRICE = "PRICE"
PHYSICAL_OVERVIEW = "OVERVIEW"
PHYSICAL_ATH_OHLCV = "ATH_HYDRATION_OHLCV"
PHYSICAL_ATH_V3_PAIR_OHLCV = "ATH_V3_PAIR_OHLCV"
PHYSICAL_ATH_V3_TOKEN_OHLCV = "ATH_V3_TOKEN_OHLCV_DIAGNOSTIC"
PHYSICAL_AUTHORITATIVE_SUPPLY = "AUTHORITATIVE_TOKEN_SUPPLY"
PHYSICAL_FRESH_MARKET_FALLBACK = "FRESH_MARKET_FALLBACK"
PHYSICAL_OTHER = "OTHER"
PHYSICAL_CATEGORIES = (
    PHYSICAL_PRICE, PHYSICAL_OVERVIEW, PHYSICAL_ATH_OHLCV,
    PHYSICAL_ATH_V3_PAIR_OHLCV, PHYSICAL_ATH_V3_TOKEN_OHLCV,
    PHYSICAL_AUTHORITATIVE_SUPPLY, PHYSICAL_FRESH_MARKET_FALLBACK,
    PHYSICAL_OTHER)

#: Documented categories of physical spend that the scheduler does NOT drive.
#: A delta explained entirely by these reconciles; anything left over does not.
NON_SCHEDULER_PHYSICAL_CATEGORIES = (
    PHYSICAL_ATH_OHLCV, PHYSICAL_ATH_V3_PAIR_OHLCV,
    PHYSICAL_ATH_V3_TOKEN_OHLCV, PHYSICAL_AUTHORITATIVE_SUPPLY,
    PHYSICAL_FRESH_MARKET_FALLBACK)

#: Why a dispatch returned without crossing the physical boundary.  Each of
#: these was silently charged a full budget unit before this module existed.
NON_PHYSICAL_CACHE_HIT = "CACHE_HIT"
NON_PHYSICAL_RATE_LIMIT_BACKOFF = "RATE_LIMIT_BACKOFF_SKIPPED"
NON_PHYSICAL_DEADLINE_EXHAUSTED = "DEADLINE_EXHAUSTED"
NON_PHYSICAL_CAP_REACHED = "TRANSPORT_CAP_REACHED"
NON_PHYSICAL_NO_FETCH = "NO_FETCH_CONFIGURED"
NON_PHYSICAL_REASONS = (
    NON_PHYSICAL_CACHE_HIT, NON_PHYSICAL_RATE_LIMIT_BACKOFF,
    NON_PHYSICAL_DEADLINE_EXHAUSTED, NON_PHYSICAL_CAP_REACHED,
    NON_PHYSICAL_NO_FETCH,
)

_ENDPOINT_CATEGORIES = {
    "/defi/price": PHYSICAL_PRICE,
    "/defi/token_overview": PHYSICAL_OVERVIEW,
    "/defi/ohlcv": PHYSICAL_ATH_OHLCV,
    "/defi/v3/ohlcv/pair": PHYSICAL_ATH_V3_PAIR_OHLCV,
    "/defi/v3/ohlcv": PHYSICAL_ATH_V3_TOKEN_OHLCV,
    "helius:getTokenSupply": PHYSICAL_AUTHORITATIVE_SUPPLY,
    "helius:getMultipleAccounts": PHYSICAL_FRESH_MARKET_FALLBACK,
}

# A physical request has one immutable provenance origin.  These values are
# intentionally more specific than the endpoint categories above: endpoint is
# what was called; origin is why it was called.
ORIGIN_SCHEDULED_PRICE = "SCHEDULED_PRICE"
ORIGIN_SCHEDULED_OVERVIEW = "SCHEDULED_OVERVIEW"
ORIGIN_ATH_HYDRATION_OHLCV = "ATH_HYDRATION_OHLCV"
# V3 post-migration pair-ATH work, one origin per algorithm stage so the
# ticket ledger names WHY each request was dialled, not merely what path.
ORIGIN_ATH_V3_PAIR_COARSE = "ATH_V3_PAIR_COARSE"
ORIGIN_ATH_V3_PAIR_REFINE = "ATH_V3_PAIR_REFINE"
ORIGIN_ATH_V3_PAIR_INCREMENTAL = "ATH_V3_PAIR_INCREMENTAL"
ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC = "ATH_V3_TOKEN_DIAGNOSTIC"
ORIGIN_AUTHORITATIVE_SUPPLY = "AUTHORITATIVE_TOKEN_SUPPLY"
ORIGIN_PRIORITY_REFRESH_PRICE = "PRIORITY_REFRESH_PRICE"
ORIGIN_PRIORITY_REFRESH_OVERVIEW = "PRIORITY_REFRESH_OVERVIEW"
ORIGIN_FALLBACK = "FALLBACK"
ORIGIN_OTHER_NAMED = "OTHER_NAMED_ORIGIN"
# Compatibility name for callers that only need the generic named-other
# bucket; emitted tickets use the explicit contract value above.
ORIGIN_OTHER = ORIGIN_OTHER_NAMED
ATH_V3_REQUEST_ORIGINS = (
    ORIGIN_ATH_V3_PAIR_COARSE,
    ORIGIN_ATH_V3_PAIR_REFINE,
    ORIGIN_ATH_V3_PAIR_INCREMENTAL,
    ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC,
)
PHYSICAL_REQUEST_ORIGINS = (
    ORIGIN_SCHEDULED_PRICE,
    ORIGIN_SCHEDULED_OVERVIEW,
    ORIGIN_ATH_HYDRATION_OHLCV,
    ORIGIN_ATH_V3_PAIR_COARSE,
    ORIGIN_ATH_V3_PAIR_REFINE,
    ORIGIN_ATH_V3_PAIR_INCREMENTAL,
    ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC,
    ORIGIN_AUTHORITATIVE_SUPPLY,
    ORIGIN_PRIORITY_REFRESH_PRICE,
    ORIGIN_PRIORITY_REFRESH_OVERVIEW,
    ORIGIN_FALLBACK,
    ORIGIN_OTHER_NAMED,
)


def default_origin(endpoint: object) -> str:
    category = classify_endpoint(endpoint)
    if category == PHYSICAL_PRICE:
        return ORIGIN_SCHEDULED_PRICE
    if category == PHYSICAL_OVERVIEW:
        return ORIGIN_SCHEDULED_OVERVIEW
    if category == PHYSICAL_ATH_OHLCV:
        return ORIGIN_ATH_HYDRATION_OHLCV
    if category == PHYSICAL_ATH_V3_PAIR_OHLCV:
        # Stage-less V3 pair call: the transport is expected to scope every
        # production call to an explicit stage origin; a bare call still
        # lands in the named V3 family rather than the generic bucket.
        return ORIGIN_ATH_V3_PAIR_COARSE
    if category == PHYSICAL_ATH_V3_TOKEN_OHLCV:
        return ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC
    if category == PHYSICAL_AUTHORITATIVE_SUPPLY:
        return ORIGIN_AUTHORITATIVE_SUPPLY
    if category == PHYSICAL_FRESH_MARKET_FALLBACK:
        return ORIGIN_FALLBACK
    return ORIGIN_OTHER


@dataclass(frozen=True)
class PhysicalRequestTicket:
    """Immutable proof for one request that crossed the dispatch boundary."""

    request_id: str
    producer_generation: Optional[int]
    epoch_id: Optional[str]
    scheduler_job_id: Optional[str]
    mint: Optional[str]
    endpoint: str
    origin: str
    priority: Optional[str]
    retry_index: int
    dispatched_at_unix: float
    response_at_unix: float
    physical_dispatch: bool
    http_status_class: str
    provider_outcome: str
    observation_accepted: Optional[bool]
    observation_acceptance_outcome: str
    rejection_reason: Optional[str]
    scheduler_owner: Optional[str]
    batch_size: int


@dataclass(frozen=True)
class _RequestOwnership:
    origin: str
    producer_generation: Optional[int] = None
    epoch_id: Optional[str] = None
    scheduler_job_id: Optional[str] = None
    mint: Optional[str] = None
    priority: Optional[str] = None
    scheduler_owner: Optional[str] = None
    batch_size: int = 1


@dataclass(frozen=True)
class _PendingPhysicalRequest:
    request_id: str
    endpoint: str
    retry_index: int
    dispatched_at_unix: float
    ownership: _RequestOwnership


def classify_endpoint(path: object) -> str:
    """Map a provider path onto its physical category."""

    return _ENDPOINT_CATEGORIES.get(str(path or ""), PHYSICAL_OTHER)


class MarketPhysicalRequestMeter:
    """Authoritative immutable-ticket ledger at the provider boundary.

    The former global ``before/after`` counter was inherently racy: another
    worker could complete inside that interval and its request would be
    charged to the wrong job.  A transport now allocates a unique ticket at
    the exact dispatch boundary, while scheduler ownership is carried in a
    thread-local scope.  Accounting reads those ticket identities directly.
    """

    __slots__ = (
        "_lock", "_total", "_by_category", "_by_endpoint", "_by_origin", "_non_physical",
        "_pending", "_tickets", "_ticket_ids_by_job", "_local",
        "_ticket_artifact", "_producer_generation", "_epoch_id",
        "_scheduler_job_owned_total",
    )

    def __init__(
        self,
        *,
        ticket_artifact: Optional[object] = None,
        producer_generation: Optional[int] = None,
        epoch_id: Optional[str] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._by_category: Dict[str, int] = {
            name: 0 for name in PHYSICAL_CATEGORIES}
        self._by_endpoint: Dict[str, int] = {}
        self._by_origin: Dict[str, int] = {
            name: 0 for name in PHYSICAL_REQUEST_ORIGINS}
        self._non_physical: Dict[str, int] = {
            name: 0 for name in NON_PHYSICAL_REASONS}
        self._pending: Dict[str, _PendingPhysicalRequest] = {}
        self._tickets: Dict[str, PhysicalRequestTicket] = {}
        self._ticket_ids_by_job: Dict[str, List[str]] = {}
        self._local = threading.local()
        self._ticket_artifact = (
            Path(ticket_artifact) if ticket_artifact is not None else None)
        self._producer_generation = (
            int(producer_generation) if producer_generation is not None else None)
        self._epoch_id = str(epoch_id) if epoch_id else None
        self._scheduler_job_owned_total = 0

    def set_runtime_identity(
        self, *, producer_generation: Optional[int] = None,
        epoch_id: Optional[str] = None,
    ) -> None:
        """Set defaults copied into subsequently allocated tickets."""

        with self._lock:
            if producer_generation is not None:
                self._producer_generation = int(producer_generation)
            if epoch_id is not None:
                self._epoch_id = str(epoch_id)

    @contextmanager
    def ownership(
        self,
        *,
        origin: str,
        producer_generation: Optional[int] = None,
        epoch_id: Optional[str] = None,
        scheduler_job_id: Optional[object] = None,
        mint: Optional[object] = None,
        priority: Optional[object] = None,
        scheduler_owner: Optional[object] = None,
        batch_size: object = 1,
    ) -> Iterator[None]:
        """Attach exact provenance to physical work in the current thread."""

        origin_name = str(origin or ORIGIN_OTHER)
        if origin_name not in PHYSICAL_REQUEST_ORIGINS:
            # Other physical callers remain named instead of disappearing into
            # an unexplainable aggregate.
            origin_name = f"{ORIGIN_OTHER_NAMED}:{origin_name}"
        stack = getattr(self._local, "ownership_stack", None)
        parent = stack[-1] if stack else None
        owner = _RequestOwnership(
            origin=origin_name,
            producer_generation=(
                int(producer_generation)
                if producer_generation is not None
                else (parent.producer_generation if parent else None)),
            epoch_id=(
                str(epoch_id) if epoch_id
                else (parent.epoch_id if parent else None)),
            scheduler_job_id=(
                str(scheduler_job_id) if scheduler_job_id is not None
                else (parent.scheduler_job_id if parent else None)),
            mint=(
                str(mint) if mint is not None
                else (parent.mint if parent else None)),
            priority=(
                str(priority) if priority is not None
                else (parent.priority if parent else None)),
            scheduler_owner=(
                str(scheduler_owner) if scheduler_owner is not None
                else (parent.scheduler_owner if parent else None)),
            batch_size=(
                max(1, _nonneg(batch_size))
                if batch_size != 1 or parent is None else parent.batch_size),
        )
        if stack is None:
            stack = []
            self._local.ownership_stack = stack
        stack.append(owner)
        try:
            yield
        finally:
            popped = stack.pop()
            if popped is not owner:
                raise RuntimeError("physical request ownership stack corrupted")

    def _current_ownership(self, endpoint: object) -> _RequestOwnership:
        stack = getattr(self._local, "ownership_stack", None)
        if stack:
            return stack[-1]
        return _RequestOwnership(origin=default_origin(endpoint))

    # -- transport-side writes --------------------------------------------
    def begin_physical(self, endpoint: object, *, retry_index: object = 0) -> str:
        """Allocate ownership immediately before the real network call."""

        endpoint_name = str(endpoint or "")
        category = classify_endpoint(endpoint)
        owner = self._current_ownership(endpoint)
        ticket_id = f"provider_{uuid.uuid4().hex}"
        pending = _PendingPhysicalRequest(
            request_id=ticket_id,
            endpoint=endpoint_name,
            retry_index=_nonneg(retry_index),
            dispatched_at_unix=time.time(),
            ownership=owner,
        )
        with self._lock:
            self._total += 1
            self._by_category[category] = self._by_category.get(category, 0) + 1
            self._by_endpoint[endpoint_name] = (
                self._by_endpoint.get(endpoint_name, 0) + 1)
            self._by_origin[owner.origin] = self._by_origin.get(owner.origin, 0) + 1
            self._pending[ticket_id] = pending
            if owner.scheduler_job_id:
                self._scheduler_job_owned_total += 1
                self._ticket_ids_by_job.setdefault(
                    owner.scheduler_job_id, []).append(ticket_id)
        return ticket_id

    def complete_physical(
        self,
        request_id: object,
        *,
        http_status_class: object,
        provider_outcome: object,
        observation_accepted: Optional[bool] = None,
        rejection_reason: Optional[object] = None,
    ) -> PhysicalRequestTicket:
        """Freeze a pending request ticket exactly once."""

        key = str(request_id)
        with self._lock:
            pending = self._pending.pop(key, None)
            if pending is None:
                existing = self._tickets.get(key)
                if existing is not None:
                    return existing
                raise KeyError(f"unknown physical request ticket: {key}")
            owner = pending.ownership
            ticket = PhysicalRequestTicket(
                request_id=pending.request_id,
                producer_generation=(
                    owner.producer_generation
                    if owner.producer_generation is not None
                    else self._producer_generation),
                epoch_id=(owner.epoch_id or self._epoch_id),
                scheduler_job_id=owner.scheduler_job_id,
                mint=owner.mint,
                endpoint=pending.endpoint,
                origin=owner.origin,
                priority=owner.priority,
                retry_index=pending.retry_index,
                dispatched_at_unix=pending.dispatched_at_unix,
                response_at_unix=time.time(),
                physical_dispatch=True,
                http_status_class=str(http_status_class or "UNKNOWN"),
                provider_outcome=str(provider_outcome or "UNKNOWN"),
                observation_accepted=observation_accepted,
                observation_acceptance_outcome=(
                    "ACCEPTED" if observation_accepted is True
                    else "REJECTED" if observation_accepted is False
                    else "NOT_APPLICABLE"),
                rejection_reason=(
                    str(rejection_reason) if rejection_reason else None),
                scheduler_owner=owner.scheduler_owner,
                batch_size=owner.batch_size,
            )
            self._tickets[key] = ticket
            artifact = self._ticket_artifact
            if artifact is not None:
                artifact.parent.mkdir(parents=True, exist_ok=True)
                with artifact.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(
                        asdict(ticket), sort_keys=True, separators=(",", ":")))
                    stream.write("\n")
            return ticket

    def record_physical(self, endpoint: object) -> int:
        """Compatibility helper for synchronous/manual physical callers."""

        ticket_id = self.begin_physical(endpoint)
        self.complete_physical(
            ticket_id,
            http_status_class="UNKNOWN",
            provider_outcome="RECORDED",
        )
        return self.total

    def record_non_physical(self, reason: object) -> None:
        """A dispatch returned without dialling anything (never charged)."""

        name = str(reason or "")
        if name not in self._non_physical:
            return
        with self._lock:
            self._non_physical[name] += 1

    # -- scheduler-side reads ---------------------------------------------
    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    def category_total(self, category: str) -> int:
        with self._lock:
            return int(self._by_category.get(str(category), 0))

    def origin_total(self, origin: str) -> int:
        with self._lock:
            return int(self._by_origin.get(str(origin), 0))

    @property
    def scheduler_job_owned_total(self) -> int:
        """All physical tickets allocated inside a scheduler-job scope."""

        with self._lock:
            return self._scheduler_job_owned_total

    def tickets_for_job(self, scheduler_job_id: object) -> Tuple[PhysicalRequestTicket, ...]:
        key = str(scheduler_job_id)
        with self._lock:
            return tuple(
                self._tickets[ticket_id]
                for ticket_id in self._ticket_ids_by_job.get(key, ())
                if ticket_id in self._tickets)

    def ticket_count_for_job(
        self, scheduler_job_id: object, *, include_pending: bool = False,
    ) -> int:
        key = str(scheduler_job_id)
        with self._lock:
            ticket_ids = self._ticket_ids_by_job.get(key, ())
            if include_pending:
                return len(ticket_ids)
            return sum(1 for ticket_id in ticket_ids
                       if ticket_id in self._tickets)

    @property
    def non_scheduler_total(self) -> int:
        """Physical spend the scheduler never initiates."""

        with self._lock:
            return sum(int(self._by_category.get(name, 0))
                       for name in NON_SCHEDULER_PHYSICAL_CATEGORIES)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            by_generation: Dict[str, int] = {}
            accepted = 0
            rejected = 0
            retries = 0
            for ticket in self._tickets.values():
                generation = (
                    str(ticket.producer_generation)
                    if ticket.producer_generation is not None else "UNKNOWN")
                by_generation[generation] = by_generation.get(generation, 0) + 1
                if ticket.observation_accepted is True:
                    accepted += 1
                elif ticket.observation_accepted is False:
                    rejected += 1
                if ticket.retry_index > 0:
                    retries += 1
            return {
                "transport_physical_requests_total": self._total,
                "completed_physical_request_tickets": len(self._tickets),
                "pending_physical_request_tickets": len(self._pending),
                "physical_by_category": dict(self._by_category),
                "physical_by_endpoint": dict(self._by_endpoint),
                "physical_by_origin": dict(self._by_origin),
                "physical_by_generation": by_generation,
                "accepted_observations": accepted,
                "rejected_observations": rejected,
                "physical_retries": retries,
                "scheduler_job_owned_physical_total": (
                    self._scheduler_job_owned_total),
                "non_physical_by_reason": dict(self._non_physical),
            }


def reconcile(
    *,
    scheduler_physical_requests_total: object,
    meter: Optional[MarketPhysicalRequestMeter] = None,
    transport_snapshot: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Reconcile scheduler-charged physical work against transport reality.

    ``reconciled_total`` is scheduler-attributed physical requests plus the
    documented non-scheduler categories.  ``unreconciled_delta`` is whatever
    that fails to explain -- and it is deliberately not smoothed by a
    tolerance, because a tolerance is how a 1,528-request discrepancy stayed
    invisible for a whole run.
    """

    scheduler_total = _nonneg(scheduler_physical_requests_total)
    if meter is not None:
        snapshot = meter.snapshot()
    elif transport_snapshot is not None:
        snapshot = dict(transport_snapshot)
    else:
        # No counter installed means there is nothing to reconcile AGAINST.
        # Reporting a delta of 0 here would read as "verified clean" on a
        # surface that verified nothing -- so the delta is explicitly unknown
        # and the health dimension answers NOT_APPLICABLE rather than HEALTHY.
        return {
            "scheduler_physical_requests_total": scheduler_total,
            "transport_physical_requests_total": None,
            "reconciled_total": None,
            "unreconciled_delta": None,
            "reconciled": None,
            "reconciliation_reasons": {
                "NO_PHYSICAL_REQUEST_METER_INSTALLED": 1},
        }

    transport_total = _nonneg(snapshot.get("transport_physical_requests_total"))
    exposed_ticket_aggregates = {
        "physical_requests_by_endpoint": dict(
            snapshot.get("physical_by_endpoint") or {}),
        "physical_requests_by_origin": dict(
            snapshot.get("physical_by_origin") or {}),
        "physical_requests_by_generation": dict(
            snapshot.get("physical_by_generation") or {}),
        "accepted_observations": _nonneg(
            snapshot.get("accepted_observations")),
        "rejected_observations": _nonneg(
            snapshot.get("rejected_observations")),
        "physical_retries": _nonneg(snapshot.get("physical_retries")),
        "nonphysical_outcomes": dict(
            snapshot.get("non_physical_by_reason") or {}),
        "pending_physical_request_tickets": _nonneg(
            snapshot.get("pending_physical_request_tickets")),
    }
    by_origin_raw = snapshot.get("physical_by_origin")
    by_origin = (
        dict(by_origin_raw) if isinstance(by_origin_raw, Mapping) else {})
    scheduler_job_owned = _nonneg(
        snapshot.get("scheduler_job_owned_physical_total"))
    # Backward-compatible reconciliation for imported incident snapshots and
    # small offline harnesses that predate ticket ownership.  Production
    # scheduler dispatches always carry a job ID and therefore use the exact
    # ticket branch below; this path never infers a worker's ownership.
    if scheduler_job_owned == 0 and scheduler_total > 0:
        by_category_raw = snapshot.get("physical_by_category")
        by_category = (
            dict(by_category_raw)
            if isinstance(by_category_raw, Mapping) else {})
        non_scheduler = sum(
            _nonneg(by_category.get(name))
            for name in NON_SCHEDULER_PHYSICAL_CATEGORIES)
        reconciled_total = scheduler_total + non_scheduler
        delta = transport_total - reconciled_total
        reasons: Dict[str, int] = {"LEGACY_SCHEDULER_INITIATED": scheduler_total}
        for name in NON_SCHEDULER_PHYSICAL_CATEGORIES:
            reasons[name] = _nonneg(by_category.get(name))
        non_physical = snapshot.get("non_physical_by_reason")
        if isinstance(non_physical, Mapping):
            for name, count in non_physical.items():
                if _nonneg(count):
                    reasons[f"NOT_DISPATCHED_{name}"] = _nonneg(count)
        return {
            "scheduler_physical_requests_total": scheduler_total,
            "scheduler_job_owned_physical_total": None,
            "scheduler_charge_delta": None,
            "transport_physical_requests_total": transport_total,
            "reconciled_total": reconciled_total,
            "unreconciled_delta": delta,
            "reconciled": delta == 0,
            "reconciliation_reasons": reasons,
            **exposed_ticket_aggregates,
        }
    scheduler_origins = (
        ORIGIN_SCHEDULED_PRICE,
        ORIGIN_SCHEDULED_OVERVIEW,
        ORIGIN_PRIORITY_REFRESH_PRICE,
        ORIGIN_PRIORITY_REFRESH_OVERVIEW,
    )
    scheduler_owned = sum(_nonneg(by_origin.get(name))
                          for name in scheduler_origins)
    ath_hydration = _nonneg(by_origin.get(ORIGIN_ATH_HYDRATION_OHLCV))
    ath_v3_by_stage = {name: _nonneg(by_origin.get(name))
                       for name in ATH_V3_REQUEST_ORIGINS}
    ath_v3 = sum(ath_v3_by_stage.values())
    fallback = _nonneg(by_origin.get(ORIGIN_FALLBACK))
    other = sum(
        _nonneg(count) for name, count in by_origin.items()
        if name not in scheduler_origins
        and name not in (ORIGIN_ATH_HYDRATION_OHLCV, ORIGIN_FALLBACK)
        and name not in ATH_V3_REQUEST_ORIGINS)
    reconciled_total = (
        scheduler_owned + ath_hydration + ath_v3 + fallback + other)
    delta = transport_total - reconciled_total
    scheduler_charge_delta = scheduler_total - scheduler_job_owned
    reasons: Dict[str, int] = {
        "SCHEDULER_OWNED": scheduler_owned,
        ORIGIN_ATH_HYDRATION_OHLCV: ath_hydration,
        "ATH_V3_REQUESTS": ath_v3,
        **{name: count for name, count in ath_v3_by_stage.items() if count},
        ORIGIN_FALLBACK: fallback,
        ORIGIN_OTHER: other,
    }
    non_physical = snapshot.get("non_physical_by_reason")
    if isinstance(non_physical, Mapping):
        for name, count in non_physical.items():
            if _nonneg(count):
                reasons[f"NOT_DISPATCHED_{name}"] = _nonneg(count)
    return {
        "scheduler_physical_requests_total": scheduler_total,
        "scheduler_job_owned_physical_total": scheduler_job_owned,
        "scheduler_charge_delta": scheduler_charge_delta,
        "transport_physical_requests_total": transport_total,
        "reconciled_total": reconciled_total,
        "unreconciled_delta": delta,
        "reconciled": delta == 0 and scheduler_charge_delta == 0,
        "reconciliation_reasons": reasons,
        **exposed_ticket_aggregates,
    }


__all__ = (
    "MARKET_REQUEST_CAP_UNBOUNDED",
    "MARKET_BUDGET_MODE_UNBOUNDED",
    "MARKET_BUDGET_MODE_BOUNDED_LIFETIME",
    "MARKET_BUDGET_MODES",
    "REFUSAL_RUN_FOREVER_BOUNDED_MARKET_BUDGET",
    "PHYSICAL_PRICE", "PHYSICAL_OVERVIEW", "PHYSICAL_ATH_OHLCV",
    "PHYSICAL_ATH_V3_PAIR_OHLCV", "PHYSICAL_ATH_V3_TOKEN_OHLCV",
    "PHYSICAL_AUTHORITATIVE_SUPPLY",
    "PHYSICAL_FRESH_MARKET_FALLBACK",
    "PHYSICAL_OTHER", "PHYSICAL_CATEGORIES",
    "NON_SCHEDULER_PHYSICAL_CATEGORIES",
    "NON_PHYSICAL_CACHE_HIT", "NON_PHYSICAL_RATE_LIMIT_BACKOFF",
    "NON_PHYSICAL_DEADLINE_EXHAUSTED", "NON_PHYSICAL_CAP_REACHED",
    "NON_PHYSICAL_NO_FETCH", "NON_PHYSICAL_REASONS",
    "ORIGIN_SCHEDULED_PRICE", "ORIGIN_SCHEDULED_OVERVIEW",
    "ORIGIN_ATH_HYDRATION_OHLCV",
    "ORIGIN_ATH_V3_PAIR_COARSE", "ORIGIN_ATH_V3_PAIR_REFINE",
    "ORIGIN_ATH_V3_PAIR_INCREMENTAL", "ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC",
    "ATH_V3_REQUEST_ORIGINS",
    "ORIGIN_AUTHORITATIVE_SUPPLY",
    "ORIGIN_PRIORITY_REFRESH_PRICE",
    "ORIGIN_PRIORITY_REFRESH_OVERVIEW", "ORIGIN_FALLBACK",
    "ORIGIN_OTHER_NAMED", "ORIGIN_OTHER",
    "PHYSICAL_REQUEST_ORIGINS", "PhysicalRequestTicket",
    "MarketPhysicalRequestMeter",
    "classify_endpoint",
    "default_origin",
    "market_budget_mode",
    "market_budget_status",
    "reconcile",
    "run_forever_market_budget_refusal",
)
