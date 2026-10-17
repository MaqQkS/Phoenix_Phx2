"""RUN_FOREVER market-scheduling remediation (2026-08-02 five-hour failure).

The failure this pins: a ``--run-forever`` production deployment silently
inherited the bounded base market-request cap of 5,000, exhausted it 22 minutes
after launch, and then spent 4h38m unable to observe the market at all while
still reporting itself alive.  15,523 priority refreshes were rejected, 15,419
of 15,770 parity evaluations ended ``NO_SEND_MARKET_INCOMPLETE``, and zero
candidates reached delivery.

Three separate defects made that possible and each has tests here:

1. RUN_FOREVER accepted a finite, non-refilling lifetime market budget.
2. The budget was charged at DEQUEUE, not at physical dispatch -- so cache
   hits, backoff skips and deadline refusals all cost a full unit (5,000
   charged against 3,472 real HTTP calls) while OHLCV hydration (1,825 real
   calls) was charged nothing at all.
3. Nothing turned sustained market blindness into an unhealthy verdict or a
   fail-closed action.
"""

from __future__ import annotations

import time

import pytest

from PHX2.free_tier_producer.free_tier_credit_budget import (
    BUDGET_STOP_MARKET_PLANE_BLIND,
    BUDGET_STOP_MARKET_REQUESTS,
    MARKET_CAP_UNBOUNDED,
    FreeTierCreditBudget,
    FreeTierCreditBudgetCaps,
)
from PHX2.free_tier_producer.market_budget import (
    MARKET_BUDGET_MODE_BOUNDED_LIFETIME,
    MARKET_BUDGET_MODE_UNBOUNDED,
    MARKET_REQUEST_CAP_UNBOUNDED,
    NON_PHYSICAL_CACHE_HIT,
    PHYSICAL_ATH_OHLCV,
    REFUSAL_RUN_FOREVER_BOUNDED_MARKET_BUDGET,
    MarketPhysicalRequestMeter,
    market_budget_mode,
    market_budget_status,
    reconcile,
    run_forever_market_budget_refusal,
)
from PHX2.free_tier_producer.market_plane_health import (
    MARKET_PLANE_BLIND,
    MARKET_PLANE_DEGRADED,
    MARKET_PLANE_HEALTHY,
    MARKET_PLANE_IDLE,
    REASON_BUDGET_EXHAUSTED,
    REASON_OBSERVATIONS_STALE,
    MarketPlaneConfig,
    MarketPlaneWatch,
    classify,
)
from PHX2.free_tier_producer.market_scheduler import (
    FIELD_PRICE_MC,
    MARKET_PROVIDER_BUDGET_EXHAUSTED,
    MarketScheduler,
    MarketSchedulerConfig,
    PRIORITY_P1,
    PRIORITY_P3,
)
from PHX2.watchdog import operational_health as oh
from PHX2.watchdog.launcher_template import (
    REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED,
    deployment_specification,
    render_live_launcher,
    validate_live_launcher_text,
)

from PHX2.tests.test_market_scheduler import (
    NOW,
    _observation,
    _view,
)

HEAD = "71baad5bc0037317b09621868d02d2543aee5d33"
BASELINE = "a" * 64 + ":9164:25"


# --------------------------------------------------------------------------- #
# 1-3. RUN_FOREVER budget contract
# --------------------------------------------------------------------------- #

def test_1_run_forever_rejects_a_finite_lifetime_provider_budget():
    """The exact production combination that failed on 2026-08-02."""

    assert run_forever_market_budget_refusal(
        run_forever=True, max_market_requests_total=5000
    ) == REFUSAL_RUN_FOREVER_BOUNDED_MARKET_BUDGET
    # Bigger arbitrary numbers are still finite, and still expire.
    for arbitrary in (50000, 200000, 1_000_000):
        assert run_forever_market_budget_refusal(
            run_forever=True, max_market_requests_total=arbitrary
        ) == REFUSAL_RUN_FOREVER_BOUNDED_MARKET_BUDGET


def test_2_run_forever_accepts_the_unbounded_sentinel():
    assert run_forever_market_budget_refusal(
        run_forever=True,
        max_market_requests_total=MARKET_REQUEST_CAP_UNBOUNDED) is None
    assert market_budget_mode(MARKET_REQUEST_CAP_UNBOUNDED) == \
        MARKET_BUDGET_MODE_UNBOUNDED
    caps = FreeTierCreditBudgetCaps(
        max_market_requests_total=MARKET_CAP_UNBOUNDED)
    assert caps.market_requests_unbounded is True
    config = MarketSchedulerConfig(
        provider_request_budget=MARKET_REQUEST_CAP_UNBOUNDED)
    assert config.provider_budget_unbounded is True


def test_2b_unbounded_budget_never_stops_the_run_or_exhausts_the_scheduler():
    budget = FreeTierCreditBudget(
        FreeTierCreditBudgetCaps(
            max_market_requests_total=MARKET_CAP_UNBOUNDED),
        delivery_enabled=False)
    # Far past the old 5,000 ceiling.
    budget.observe_market({"http_calls_total": 500_000, "http_429": 0})
    assert budget.stop_requested is False
    assert budget.stop_reason is None

    meter = MarketPhysicalRequestMeter()
    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint: None,
        overview_fetch_fn=None,
        config=MarketSchedulerConfig(
            provider_request_budget=MARKET_REQUEST_CAP_UNBOUNDED),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    scheduler._scheduler_physical_requests = 10_000_000
    with scheduler._lock:
        assert scheduler._budget_exhausted_locked() is False
    stats = scheduler.stats()
    assert stats["market_budget_mode"] == MARKET_BUDGET_MODE_UNBOUNDED
    assert stats["market_budget_limit"] is None
    assert stats["market_provider_budget_remaining"] is None
    assert MARKET_PROVIDER_BUDGET_EXHAUSTED not in (
        stats["market_scheduler_degraded_reasons"])


def test_3_bounded_one_shot_mode_still_enforces_finite_caps():
    """Invariants 4 and 5: bounded runs keep exactly their old behaviour."""

    caps = FreeTierCreditBudgetCaps(max_market_requests_total=2000)
    assert caps.market_requests_unbounded is False
    budget = FreeTierCreditBudget(caps, delivery_enabled=False)
    budget.observe_market({"http_calls_total": 1999, "http_429": 0})
    assert budget.stop_requested is False
    budget.observe_market({"http_calls_total": 2000, "http_429": 0})
    assert budget.stop_requested is True
    assert budget.stop_reason == BUDGET_STOP_MARKET_REQUESTS
    # Defaults are unchanged: the default run is still capped.
    assert FreeTierCreditBudgetCaps().max_market_requests_total == 5000
    assert market_budget_mode(5000) == MARKET_BUDGET_MODE_BOUNDED_LIFETIME
    # Negative/nonsense still fails closed.
    with pytest.raises(ValueError):
        FreeTierCreditBudgetCaps(max_market_requests_total=-1)
    with pytest.raises(ValueError):
        MarketSchedulerConfig(provider_request_budget=-1)


def test_3b_budget_status_block_reports_mode_limit_window_and_remaining():
    unbounded = market_budget_status(MARKET_REQUEST_CAP_UNBOUNDED, 1234)
    assert unbounded["market_budget_mode"] == MARKET_BUDGET_MODE_UNBOUNDED
    assert unbounded["market_budget_limit"] is None
    assert unbounded["market_budget_limit_display"] == "UNBOUNDED"
    assert unbounded["market_budget_reset_window_seconds"] is None
    assert unbounded["market_budget_physical_requests_consumed"] == 1234
    assert unbounded["market_budget_remaining"] is None

    bounded = market_budget_status(5000, 4998)
    assert bounded["market_budget_mode"] == MARKET_BUDGET_MODE_BOUNDED_LIFETIME
    assert bounded["market_budget_limit"] == 5000
    assert bounded["market_budget_remaining"] == 2


# --------------------------------------------------------------------------- #
# 4-8. Budget is charged ONLY at physical dispatch
# --------------------------------------------------------------------------- #

def _metered_scheduler(price_fetch, meter, *, budget=100, overview_fetch=None):
    return MarketScheduler(
        price_fetch_fn=price_fetch,
        overview_fetch_fn=overview_fetch,
        config=MarketSchedulerConfig(provider_request_budget=budget),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)


def test_4_budget_is_charged_only_at_physical_dispatch():
    meter = MarketPhysicalRequestMeter()
    view = _view(0)

    def price_fetch(mint, **_kw):
        meter.record_physical("/defi/price")
        return _observation(view)

    scheduler = _metered_scheduler(price_fetch, meter)
    scheduler.update_candidates([view])
    jobs = scheduler.plan(enqueue=False)
    job = next(j for j in jobs if j.field_group == FIELD_PRICE_MC)
    before = scheduler._scheduler_physical_requests
    scheduler._charge_job_tickets(job)
    assert scheduler._scheduler_physical_requests == before  # nothing dialled
    with scheduler._ticket_ownership(job):
        price_fetch(job.mints[0])
    assert scheduler._charge_job_tickets(job) == 1
    assert scheduler._scheduler_physical_requests == 1
    assert meter.total == 1


def test_5_cache_hits_consume_zero_provider_budget():
    meter = MarketPhysicalRequestMeter()
    scheduler = _metered_scheduler(lambda mint, **_kw: None, meter)
    meter.record_non_physical(NON_PHYSICAL_CACHE_HIT)   # served from cache
    assert scheduler._scheduler_physical_requests == 0
    snapshot = meter.snapshot()
    assert snapshot["transport_physical_requests_total"] == 0
    assert snapshot["non_physical_by_reason"][NON_PHYSICAL_CACHE_HIT] == 1


def test_6_coalesced_requests_consume_one_physical_request():
    """Two enqueues for the same (mint, field) => one dispatch, one charge."""

    meter = MarketPhysicalRequestMeter()
    view = _view(0)
    scheduler = _metered_scheduler(lambda mint, **_kw: None, meter)
    scheduler.update_candidates([view])
    first = scheduler.plan(enqueue=True)
    assert first, "first plan must enqueue work"
    coalesced_before = scheduler.stats()["coalesced_work_total"]
    second = scheduler.plan(enqueue=True)
    assert second == [], "identical work must coalesce, not double-enqueue"
    assert scheduler.stats()["coalesced_work_total"] > coalesced_before
    # One physical dispatch for the one surviving job.
    job = next(j for j in first if j.field_group == FIELD_PRICE_MC)
    with scheduler._ticket_ownership(job):
        meter.record_physical("/defi/price")
    assert scheduler._charge_job_tickets(job) == 1
    assert meter.total == 1


def test_7_refused_enqueue_consumes_zero_provider_budget():
    meter = MarketPhysicalRequestMeter()
    views = [_view(index) for index in range(6)]
    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint, **_kw: None, overview_fetch_fn=None,
        config=MarketSchedulerConfig(provider_request_budget=1),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    scheduler._scheduler_physical_requests = 1     # budget already spent
    scheduler.update_candidates(views)
    accepted = scheduler.plan(enqueue=True)
    assert accepted == [], "an exhausted budget must refuse every enqueue"
    assert MARKET_PROVIDER_BUDGET_EXHAUSTED in (
        scheduler.stats()["market_scheduler_degraded_reasons"])
    # Refusals are free: nothing crossed the boundary.
    assert meter.total == 0
    assert scheduler._scheduler_physical_requests == 1


def test_8_cancelled_before_dispatch_consumes_zero_provider_budget():
    meter = MarketPhysicalRequestMeter()
    view = _view(0)
    scheduler = _metered_scheduler(lambda mint, **_kw: None, meter)
    scheduler.update_candidates([view])
    scheduler.plan(enqueue=True)
    scheduler.request_stop()                      # cancel before any dispatch
    assert meter.total == 0
    assert scheduler._scheduler_physical_requests == 0
    assert scheduler.stats()["scheduler_physical_requests_total"] == 0


# --------------------------------------------------------------------------- #
# 9-10. Batching
# --------------------------------------------------------------------------- #

def test_9_one_batch_of_n_mints_consumes_one_physical_request():
    meter = MarketPhysicalRequestMeter()
    views = [_view(index) for index in range(5)]
    seen = {}

    def batch_fetch(mints):
        meter.record_physical("/defi/price")      # ONE provider request
        seen["mints"] = tuple(mints)
        return {mint: {"mint": mint, "current_price": "1",
                       "current_market_cap_usd": "100"} for mint in mints}

    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint, **_kw: None, overview_fetch_fn=None,
        batch_price_fetch_fn=batch_fetch,
        config=MarketSchedulerConfig(paid_batch_size=5,
                                     provider_request_budget=100),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    scheduler.update_candidates(views)
    jobs = [j for j in scheduler.plan(enqueue=False)
            if j.field_group == FIELD_PRICE_MC]
    assert len(jobs) == 1 and len(jobs[0].mints) == 5

    with scheduler._ticket_ownership(jobs[0]):
        batch_fetch(jobs[0].mints)
    assert scheduler._charge_job_tickets(jobs[0]) == 1
    assert meter.total == 1, "5 mints must cost ONE physical request"
    assert len(seen["mints"]) == 5


def test_9b_batches_never_mix_priority_classes():
    """A P1 candidate must not ride inside a background batch."""

    meter = MarketPhysicalRequestMeter()
    activated = [_view(index, status="ACTIVATED") for index in range(2)]
    background = [_view(50 + index) for index in range(6)]
    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint, **_kw: None, overview_fetch_fn=None,
        batch_price_fetch_fn=lambda mints: {},
        config=MarketSchedulerConfig(paid_batch_size=10,
                                     provider_request_budget=100),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    scheduler.update_candidates(activated + background)
    price_jobs = [j for j in scheduler.plan(enqueue=False)
                  if j.field_group == FIELD_PRICE_MC]
    # batch_size 10 would have swallowed all 8 into one chunk before the fix.
    assert len(price_jobs) >= 2
    priorities = {job.priority for job in price_jobs}
    assert len(priorities) >= 2
    for job in price_jobs:
        views = [scheduler._views[mint] for mint in job.mints]
        statuses = {view.status for view in views}
        assert len(statuses) == 1, (
            "one batch must contain a single priority class, got "
            f"{statuses}")


def test_10_partial_batch_responses_retain_per_mint_correctness():
    meter = MarketPhysicalRequestMeter()
    views = [_view(index) for index in range(4)]
    resolved = [v.mint for v in views[:2]]
    failures = []

    def batch_fetch(mints):
        meter.record_physical("/defi/price")
        return {mint: {"mint": mint, "current_price": "1",
                       "current_market_cap_usd": "100"}
                for mint in mints if mint in resolved}

    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint, **_kw: None, overview_fetch_fn=None,
        batch_price_fetch_fn=batch_fetch,
        config=MarketSchedulerConfig(paid_batch_size=4,
                                     provider_request_budget=100),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        failure_callback=lambda mint, group, reason: failures.append(
            (mint, reason)),
        physical_request_meter=meter)
    scheduler.update_candidates(views)
    job = next(j for j in scheduler.plan(enqueue=False)
               if j.field_group == FIELD_PRICE_MC)
    scheduler._consume_result(job, batch_fetch(job.mints), None)

    stats = scheduler.stats()
    assert stats["market_batch_mints_requested"] == 0  # planner counts on dispatch
    assert stats["market_batch_mints_resolved"] == 2
    assert stats["market_batches_partial"] == 1
    # Missing members are explicitly unresolved, never fabricated.
    missing = {mint for mint, _ in failures}
    assert missing == {v.mint for v in views[2:]}
    for mint in resolved:
        assert scheduler.snapshot(mint).get("current_price") == "1"
    for view in views[2:]:
        assert scheduler.snapshot(view.mint).get("current_price") is None


def test_10b_a_failed_batch_fabricates_success_for_no_member():
    meter = MarketPhysicalRequestMeter()
    views = [_view(index) for index in range(3)]
    failures = []
    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint, **_kw: None, overview_fetch_fn=None,
        batch_price_fetch_fn=lambda mints: None,
        config=MarketSchedulerConfig(paid_batch_size=3,
                                     provider_request_budget=100),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        failure_callback=lambda mint, group, reason: failures.append(mint),
        physical_request_meter=meter)
    scheduler.update_candidates(views)
    job = next(j for j in scheduler.plan(enqueue=False)
               if j.field_group == FIELD_PRICE_MC)
    scheduler._consume_result(job, None, None)
    assert sorted(failures) == sorted(v.mint for v in views)
    assert scheduler.stats()["market_batches_failed"] == 1
    for view in views:
        assert scheduler.snapshot(view.mint).get("current_price") is None


# --------------------------------------------------------------------------- #
# 11-12. Scheduler/transport reconciliation
# --------------------------------------------------------------------------- #

def test_11_reconciliation_is_zero_under_normal_operation():
    meter = MarketPhysicalRequestMeter()
    for _ in range(7):
        meter.record_physical("/defi/price")
    for _ in range(3):
        meter.record_physical("/defi/token_overview")
    for _ in range(4):
        meter.record_physical("/defi/ohlcv")       # ATH hydration
    meter.record_non_physical(NON_PHYSICAL_CACHE_HIT)

    result = reconcile(scheduler_physical_requests_total=10, meter=meter)
    assert result["scheduler_physical_requests_total"] == 10
    assert result["transport_physical_requests_total"] == 14
    assert result["reconciled_total"] == 14
    assert result["unreconciled_delta"] == 0
    assert result["reconciled"] is True
    # OHLCV is a NAMED category, not a silent tolerance.
    assert result["reconciliation_reasons"][PHYSICAL_ATH_OHLCV] == 4
    assert result["reconciliation_reasons"][
        f"NOT_DISPATCHED_{NON_PHYSICAL_CACHE_HIT}"] == 1


def test_12_unexplained_delta_is_surfaced_and_fails_health():
    meter = MarketPhysicalRequestMeter()
    for _ in range(9):
        meter.record_physical("/defi/price")
    result = reconcile(scheduler_physical_requests_total=4, meter=meter)
    assert result["unreconciled_delta"] == 5
    assert result["reconciled"] is False

    dimension = oh.evaluate_request_accounting(result)
    assert dimension.verdict == oh.DIM_UNHEALTHY
    assert oh.CAUSE_REQUEST_ACCOUNTING_UNRECONCILED in dimension.causes

    verdict = oh.evaluate_operational_health(
        telemetry={"transport_connected": True,
                   "source_continuity_state": "NO_GAP", **result},
        watchlist_summary={})
    assert verdict.status == oh.UNHEALTHY_REQUEST_ACCOUNTING
    assert verdict.healthy is False


def test_12c_no_meter_reports_unknown_not_clean():
    """A surface that verified nothing must not read as 'reconciled'."""

    result = reconcile(scheduler_physical_requests_total=17)
    assert result["unreconciled_delta"] is None
    assert result["reconciled"] is None
    assert result["reconciliation_reasons"] == {
        "NO_PHYSICAL_REQUEST_METER_INSTALLED": 1}
    dimension = oh.evaluate_request_accounting(result)
    assert dimension.verdict == oh.DIM_NOT_APPLICABLE


def test_12b_the_2026_08_02_run_would_now_be_reported_unreconciled():
    """The real numbers: 5,000 charged, 3,472 dialled, 1,825 uncharged OHLCV."""

    meter = MarketPhysicalRequestMeter()
    for _ in range(1190):
        meter.record_physical("/defi/price")
    for _ in range(457):
        meter.record_physical("/defi/token_overview")
    for _ in range(1825):
        meter.record_physical("/defi/ohlcv")
    assert meter.total == 3472

    # What the old accounting believed it had spent.
    old = reconcile(scheduler_physical_requests_total=5000, meter=meter)
    assert old["unreconciled_delta"] == 3472 - (5000 + 1825)
    assert old["reconciled"] is False

    # What physical charging actually produces: price+overview only.
    fixed = reconcile(scheduler_physical_requests_total=1647, meter=meter)
    assert fixed["unreconciled_delta"] == 0
    assert fixed["reconciled"] is True


# --------------------------------------------------------------------------- #
# 13-15. Market-plane fail-closed behaviour
# --------------------------------------------------------------------------- #

def _watch(grace=300.0):
    return MarketPlaneWatch(MarketPlaneConfig(grace_seconds=grace))


def test_13_transient_scheduler_starvation_recovers_within_grace():
    watch = _watch(grace=300.0)
    first = watch.observe(now_monotonic=0.0, active_candidates=4,
                          budget_exhausted=True)
    assert first.status == MARKET_PLANE_DEGRADED
    assert REASON_BUDGET_EXHAUSTED in first.reasons
    assert classify(first) == (False, "")

    mid = watch.observe(now_monotonic=120.0, active_candidates=4,
                        budget_exhausted=True)
    assert mid.status == MARKET_PLANE_DEGRADED, "still inside grace"

    recovered = watch.observe(now_monotonic=200.0, active_candidates=4,
                              budget_exhausted=False,
                              successful_refresh_total=5)
    assert recovered.status == MARKET_PLANE_HEALTHY
    assert classify(recovered) == (False, "")
    # The clock is genuinely released, not merely masked.
    again = watch.observe(now_monotonic=400.0, active_candidates=4,
                          budget_exhausted=True)
    assert again.status == MARKET_PLANE_DEGRADED
    assert again.blind_age_seconds == 0.0


def test_14_sustained_market_blindness_fails_closed_after_grace():
    watch = _watch(grace=300.0)
    watch.observe(now_monotonic=0.0, active_candidates=4,
                  budget_exhausted=True)
    verdict = watch.observe(now_monotonic=300.0, active_candidates=4,
                            budget_exhausted=True)
    assert verdict.status == MARKET_PLANE_BLIND
    assert verdict.blind == True  # noqa: E712  (explicit property assertion)
    should_stop, reason = classify(verdict)
    assert should_stop is True
    assert reason == REASON_BUDGET_EXHAUSTED

    # The canonical fail-closed action, on the existing cooperative stop.
    budget = FreeTierCreditBudget(
        FreeTierCreditBudgetCaps(
            max_market_requests_total=MARKET_CAP_UNBOUNDED),
        delivery_enabled=False)
    budget.request_stop(BUDGET_STOP_MARKET_PLANE_BLIND)
    assert budget.stop_requested is True
    assert budget.stop_reason == BUDGET_STOP_MARKET_PLANE_BLIND

    # ...and the operator surface says so.
    dimension = oh.evaluate_market_plane(verdict.to_record())
    assert dimension.verdict == oh.DIM_UNHEALTHY
    assert oh.CAUSE_MARKET_PLANE_BLIND in dimension.causes


def test_14b_watchdog_cannot_call_a_blind_producer_healthy():
    """A live PID and a connected socket are not market observability."""

    watch = _watch(grace=60.0)
    watch.observe(now_monotonic=0.0, active_candidates=8,
                  budget_exhausted=True)
    blind = watch.observe(now_monotonic=61.0, active_candidates=8,
                          budget_exhausted=True)
    verdict = oh.evaluate_operational_health(
        telemetry={
            "transport_connected": True,          # Helius up
            "source_continuity_state": "NO_GAP",  # ingestion fine
            **blind.to_record(),
        },
        watchlist_summary={},
        process_ownership_ok=True,                # PID owned
    )
    assert verdict.status == oh.UNHEALTHY_MARKET_PLANE_BLIND
    assert verdict.healthy is False
    assert oh.CAUSE_MARKET_PLANE_BLIND in (
        [verdict.primary_cause] + verdict.secondary_causes)


def test_14c_degraded_within_grace_does_not_kill_production():
    watch = _watch(grace=300.0)
    watch.observe(now_monotonic=0.0, active_candidates=3,
                  budget_exhausted=True)
    degraded = watch.observe(now_monotonic=10.0, active_candidates=3,
                             budget_exhausted=True)
    verdict = oh.evaluate_operational_health(
        telemetry={"transport_connected": True,
                   "source_continuity_state": "NO_GAP",
                   **degraded.to_record()},
        watchlist_summary={})
    assert verdict.status == oh.DEGRADED_MARKET_PLANE
    assert verdict.status in oh.DEGRADED_STATUSES
    assert verdict.status not in oh.UNHEALTHY_STATUSES


def test_14d_the_real_2026_08_02_timeline_fails_closed_five_minutes_in():
    """Replays the run's shape: healthy to T+22m, then nothing served.

    The live run stayed nominally healthy for 278 minutes after the budget
    died. With the bounded grace it goes explicitly unhealthy 5 minutes after,
    and asks for the canonical cooperative stop.
    """

    watch = MarketPlaneWatch(MarketPlaneConfig())      # 300 s grace
    first_blind_minute = None
    verdict = None
    served = attempts = 0
    for minute in range(0, 300):
        exhausted = minute >= 22
        attempts += 51                                 # the run's real rate
        if not exhausted:
            served += 51
        verdict = watch.observe(
            now_monotonic=float(minute * 60), active_candidates=12,
            budget_exhausted=exhausted,
            starved_age_seconds=(
                float((minute - 22) * 60) if exhausted else 1.0),
            starvation_bound_seconds=900.0,
            successful_refresh_total=served,
            priority_refresh_attempts_total=attempts,
            priority_refresh_served_total=served,
            max_observation_age_seconds=(
                float((minute - 22) * 60) if exhausted else 5.0))
        if verdict.status == MARKET_PLANE_BLIND and first_blind_minute is None:
            first_blind_minute = minute
    assert first_blind_minute == 27, (
        "must fail closed exactly one grace period after the budget died, "
        f"got T+{first_blind_minute}m")
    assert classify(verdict)[0] is True
    # Healthy the whole way to exhaustion: no false trip on a working plane.
    quiet = MarketPlaneWatch(MarketPlaneConfig())
    served = attempts = 0
    for minute in range(0, 22):
        attempts += 51
        served += 51
        healthy = quiet.observe(
            now_monotonic=float(minute * 60), active_candidates=12,
            budget_exhausted=False, starved_age_seconds=1.0,
            starvation_bound_seconds=900.0,
            successful_refresh_total=served,
            priority_refresh_attempts_total=attempts,
            priority_refresh_served_total=served,
            max_observation_age_seconds=5.0)
        assert healthy.status == MARKET_PLANE_HEALTHY, f"T+{minute}m"


def test_15_zero_active_candidates_does_not_trigger_starvation():
    """A quiet watchlist means no market work is DUE. Silence proves nothing."""

    watch = _watch(grace=60.0)
    verdict = None
    for tick in range(0, 3600, 60):
        verdict = watch.observe(
            now_monotonic=float(tick), active_candidates=0,
            budget_exhausted=True,             # even with every alarm set
            starved_age_seconds=99999.0,
            starvation_bound_seconds=900.0,
            max_observation_age_seconds=99999.0)
    assert verdict.status == MARKET_PLANE_IDLE
    assert verdict.reasons == []
    assert classify(verdict) == (False, "")


def test_15d_a_producer_with_no_market_scheduler_never_trips():
    """Free-tier posture: no scheduler, so no scheduler telemetry.

    The session feeds ``active_candidates=0`` when ``scheduler_state`` is
    absent.  Without that gate every liveness input reads as zero and a
    free-tier run with a busy watchlist would fail closed on a market plane it
    never had.
    """

    watch = _watch(grace=60.0)
    verdict = None
    for tick in range(0, 7200, 60):
        verdict = watch.observe(
            now_monotonic=float(tick),
            active_candidates=0,          # what the gate substitutes
            successful_refresh_total=0,   # no scheduler => no refreshes ever
            priority_refresh_attempts_total=0,
            priority_refresh_served_total=0)
    assert verdict.status == MARKET_PLANE_IDLE
    assert classify(verdict) == (False, "")
    # And the health surface calls it not-applicable, not unhealthy.
    dimension = oh.evaluate_market_plane({})
    assert dimension.verdict == oh.DIM_NOT_APPLICABLE


def test_15b_active_candidates_with_stale_observations_trip_starvation():
    watch = _watch(grace=120.0)
    watch.observe(now_monotonic=0.0, active_candidates=5,
                  max_observation_age_seconds=1200.0)
    verdict = watch.observe(now_monotonic=121.0, active_candidates=5,
                            max_observation_age_seconds=1200.0)
    assert verdict.status == MARKET_PLANE_BLIND
    assert REASON_OBSERVATIONS_STALE in verdict.reasons


def test_15c_run_forever_unbounded_mode_does_not_falsely_trip():
    """The remediated posture: unbounded budget, work being served."""

    watch = _watch(grace=60.0)
    verdict = None
    for index, tick in enumerate(range(0, 3600, 30)):
        verdict = watch.observe(
            now_monotonic=float(tick), active_candidates=12,
            budget_exhausted=False,                 # UNBOUNDED: never true
            starved_age_seconds=1.0, starvation_bound_seconds=900.0,
            successful_refresh_total=index + 1,     # work is being served
            priority_refresh_attempts_total=index + 1,
            priority_refresh_served_total=index + 1,
            max_observation_age_seconds=5.0)
    assert verdict.status == MARKET_PLANE_HEALTHY
    assert classify(verdict) == (False, "")


# --------------------------------------------------------------------------- #
# 16-18. Untouched contracts
# --------------------------------------------------------------------------- #

def test_16_priority_refresh_still_executes_a_real_provider_request():
    """One physical request per plane, visible to the SAME evaluation."""

    meter = MarketPhysicalRequestMeter()
    view = _view(0)
    calls = []

    def price_fetch(mint, **_kw):
        calls.append(mint)
        meter.record_physical("/defi/price")
        return _observation(view, price="7", mc="700")

    scheduler = MarketScheduler(
        price_fetch_fn=price_fetch, overview_fetch_fn=None,
        config=MarketSchedulerConfig(
            provider_request_budget=MARKET_REQUEST_CAP_UNBOUNDED),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    scheduler.update_candidates([view])

    result = scheduler.priority_refresh(view.mint)
    assert calls == [view.mint], "a real provider request must be issued"
    assert result["priority_refresh_provider_requests"] == 1
    assert meter.total == 1
    # Charged exactly once, at the physical boundary.
    assert scheduler._scheduler_physical_requests == 1
    # Refreshed values are visible to the evaluation that asked for them.
    assert scheduler.snapshot(view.mint).get("current_price") == "7"


def test_16b_priority_refresh_under_unbounded_budget_is_never_budget_rejected():
    """15,523 rejections in the failed run; zero possible under UNBOUNDED."""

    meter = MarketPhysicalRequestMeter()
    view = _view(0)
    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint, **_kw: _observation(view),
        overview_fetch_fn=None,
        config=MarketSchedulerConfig(
            provider_request_budget=MARKET_REQUEST_CAP_UNBOUNDED),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    scheduler.update_candidates([view])
    scheduler._scheduler_physical_requests = 5000   # past the old ceiling
    result = scheduler.priority_refresh(view.mint)
    assert result["priority_refresh_detail"] != MARKET_PROVIDER_BUDGET_EXHAUSTED
    assert MARKET_PROVIDER_BUDGET_EXHAUSTED not in (
        scheduler.stats()["market_scheduler_degraded_reasons"])


def test_16c_the_watchdog_actually_reads_the_market_plane_keys():
    """The 'module exists and nothing imports it' failure, pre-empted.

    Market-plane and reconciliation fields are published at the heartbeat's
    TOP level, not under ``provider_telemetry``.  If the observation layer
    read them from the wrong place both dimensions would report
    NOT_APPLICABLE forever and the remediation would be inert in production.
    """

    from PHX2.watchdog.observe import _MARKET_PLANE_HEARTBEAT_KEYS

    watch = _watch(grace=1.0)
    watch.observe(now_monotonic=0.0, active_candidates=5,
                  budget_exhausted=True)
    blind = watch.observe(now_monotonic=10.0, active_candidates=5,
                          budget_exhausted=True)
    record = blind.to_record()
    for key in ("market_plane_status", "market_plane_reasons",
                "market_plane_blind_age_seconds", "market_plane_grace_seconds"):
        assert key in record, f"{key} must be published by the watch"
        assert key in _MARKET_PLANE_HEARTBEAT_KEYS, (
            f"{key} must be carried into the operational verdict")

    meter = MarketPhysicalRequestMeter()
    meter.record_physical("/defi/price")
    stats_like = reconcile(scheduler_physical_requests_total=0, meter=meter)
    for key in ("scheduler_physical_requests_total",
                "transport_physical_requests_total",
                "reconciled_total", "unreconciled_delta",
                "reconciliation_reasons"):
        assert key in stats_like
        assert key in _MARKET_PLANE_HEARTBEAT_KEYS

    # And the scheduler really does publish them on its own stats surface.
    scheduler = MarketScheduler(
        price_fetch_fn=None, overview_fetch_fn=None,
        config=MarketSchedulerConfig(
            provider_request_budget=MARKET_REQUEST_CAP_UNBOUNDED),
        now_fn=lambda: NOW, monotonic_fn=time.monotonic,
        physical_request_meter=meter)
    stats = scheduler.stats()
    for key in ("scheduler_physical_requests_total",
                "transport_physical_requests_total", "unreconciled_delta",
                "market_budget_mode", "market_batch_enabled"):
        assert key in stats, f"{key} missing from scheduler stats"


def test_17_phx1_parity_warning_conditions_remain_shadow_only():
    from PHX2.free_tier_producer.phx1_parity_policy import (
        is_phx1_parity, normalize_alert_policy, policy_matrix,
    )
    policy = normalize_alert_policy("phx1_parity")
    assert is_phx1_parity(policy)
    matrix = policy_matrix(policy)
    conditions = matrix["conditions"]
    shadowed = {key for key, value in conditions.items() if value == "SHADOW"}
    # The exact conditions PHX1_PARITY demotes to shadow annotations.
    assert {"activation_proven", "fee_gate_lifecycle_immature",
            "fee_proof_missing", "structural_policy"} <= shadowed
    # ...and the hard gates it does NOT touch stay hard.
    for hard in ("liquidity_floor", "dedupe", "migration_proven",
                 "tier_lifetime_monotonicity", "compose_authorization",
                 "ath_coverage_complete",
                 # These two are what make delivery IMPOSSIBLE while the
                 # market plane is blind: a stale or absent observation is a
                 # hard refusal at send, whatever the parity policy says.
                 "market_freshness", "market_recovery_backoff"):
        assert conditions[hard].startswith("HARD"), (
            f"{hard} must remain a hard gate, got {conditions[hard]}")
    # Nothing in this remediation touched the parity matrix.
    assert policy_matrix(normalize_alert_policy("legacy")) != matrix


def test_18_launcher_states_the_unbounded_market_budget_explicitly():
    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    assert '"--max-market-requests-total", "0"' in text
    assert 'market_budget_mode      = "UNBOUNDED"' in text
    assert validate_live_launcher_text(
        text, expected_head=HEAD, ledger_baseline=BASELINE) == []

    spec = deployment_specification(
        expected_head=HEAD, ledger_baseline=BASELINE)
    assert spec["runtime_contract"] == "RUN_FOREVER"
    assert spec["market_budget_mode"] == MARKET_BUDGET_MODE_UNBOUNDED
    assert spec["contract_refusals"] == []


def test_18b_a_launcher_that_omits_the_market_budget_is_refused():
    """The exact 2026-08-02 launcher shape: silent inheritance of 5,000."""

    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    omitted = text.replace('  "--max-market-requests-total", "0",\n', "")
    assert REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED in validate_live_launcher_text(
        omitted, expected_head=HEAD, ledger_baseline=BASELINE)


def test_18c_a_launcher_with_a_bounded_market_budget_is_refused():
    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    for arbitrary in ("5000", "50000", "200000"):
        bounded = text.replace(
            '"--max-market-requests-total", "0"',
            f'"--max-market-requests-total", "{arbitrary}"')
        assert REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED in (
            validate_live_launcher_text(
                bounded, expected_head=HEAD, ledger_baseline=BASELINE)), (
            f"a bounded cap of {arbitrary} must be refused")


def test_18d_hard_safety_gates_are_untouched_by_this_remediation():
    """LP floor, migration proof, freshness, dedupe, credentials, ATH."""

    from PHX2.free_tier_producer.compat.production_live_runner import (
        MIN_LIQUIDITY_USD,
    )
    assert int(MIN_LIQUIDITY_USD) == 4500

    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    # Delivery identity, integrity and credential posture unchanged.
    assert '"--require-baseline"' in text
    assert '"--expected-head"' in text
    assert '"--enable-telegram"' in text
    assert "--enable-private-discord" not in text
    assert '"--phx1-structural-policy", "shadow"' in text
    assert '"--require-production-grpc"' in text
