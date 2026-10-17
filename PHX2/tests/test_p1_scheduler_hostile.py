"""PHX2-E2E-006 hostile scheduler proofs + capacity boundaries.

Every scenario the remediation contract requires under failure, overload,
shutdown, restart and misconfiguration.  All offline: deterministic fake
providers, synthetic candidate views, no network, no env, no ledger.
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone

import pytest

from PHX2.free_tier_producer.market_scheduler import (
    CandidateScheduleView,
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    MARKET_SCHEDULER_OVERLOADED,
    MarketObservation,
    MarketScheduler,
    MarketSchedulerConfig,
    P1_CAPACITY_UNACHIEVABLE,
    P1_RESULT_DISPATCH_EVALUATED,
    PRIORITY_P0,
    SCHEDULER_CAPACITY_REFUSED,
    SCHEDULER_READY,
    SCHEDULER_STOPPED,
    SOURCE_GRPC,
    classify_engine_reason_to_p1_outcome,
    evaluate_p1_capacity,
    production_p1_scheduler_fields,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport


NOW = 1_750_000_000.0


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _mint(index: int) -> str:
    return f"host{index:04d}" + "y" * 35 + "pump"


def _view(index: int, *, status: str = "ACTIVE_DIP_WATCH", now: float = NOW,
          generation: int | None = None) -> CandidateScheduleView:
    return CandidateScheduleView(
        mint=_mint(index),
        candidate_id=f"hostile-{index:04d}",
        generation=(index + 1 if generation is None else generation),
        status=status,
        seeded_at_epoch=now - 5.0,
    )


def _grpc(view: CandidateScheduleView, *, now: float, sequence: int) -> MarketObservation:
    return MarketObservation(
        mint=view.mint,
        candidate_id=view.candidate_id,
        generation=view.generation,
        source=SOURCE_GRPC,
        source_timestamp=now,
        ingestion_timestamp=now,
        field_group=FIELD_PRICE_MC,
        observation_sequence=sequence,
        source_evidence_digest=hashlib.sha256(
            f"{view.mint}:{sequence}".encode()).hexdigest(),
        request_id=f"grpc-{sequence}",
        values={"current_price": "1", "current_market_cap_usd": "100"},
        source_order=(sequence, 0, -1, 0, 0),
    )


def _overview(view: CandidateScheduleView, *, now: float, sequence: int,
              mint_override: str | None = None) -> MarketObservation:
    return MarketObservation(
        mint=mint_override or view.mint,
        candidate_id=view.candidate_id,
        generation=view.generation,
        source="PAID_PRIMARY_SINGLE",
        source_timestamp=now,
        ingestion_timestamp=now,
        field_group=FIELD_OVERVIEW,
        observation_sequence=sequence,
        source_evidence_digest=hashlib.sha256(
            f"{mint_override or view.mint}:ov:{sequence}".encode()).hexdigest(),
        request_id=f"ov-{sequence}",
        values={"current_market_cap_usd": "100", "liquidity_usd": "9000"},
    )


def _scheduler(*, overview_fetch=None, price_fetch=None, config=None,
               apply_callback=None, failure_callback=None,
               now_fn=None) -> MarketScheduler:
    return MarketScheduler(
        price_fetch_fn=price_fetch,
        overview_fetch_fn=overview_fetch,
        config=config or MarketSchedulerConfig(
            worker_count=4, max_inflight=4, max_queue_size=64,
            provider_min_interval_seconds=0.0),
        now_fn=now_fn or time.time,
        monotonic_fn=time.monotonic,
        apply_callback=apply_callback,
        failure_callback=failure_callback,
    )


# ---------------------------------------------------------------------------
# 1 + 2 — provider failures stay isolated; no worker-pool collapse.
# ---------------------------------------------------------------------------


def test_one_timeout_isolates_and_never_authorizes():
    now = time.time()
    views = [_view(index, now=now) for index in range(8)]
    failing = views[0].mint
    failures = []
    applied = []
    done = threading.Event()

    def fetch(mint, deadline_monotonic=None):
        if mint == failing:
            return {"mint": mint, "_market_failure_reason": "PROVIDER_TIMEOUT"}
        return {"mint": mint, "current_market_cap_usd": "100",
                "liquidity_usd": "9000", "provider_timestamp_utc": _iso(time.time())}

    def _apply(observation, snapshot):
        if observation.field_group == FIELD_OVERVIEW:
            applied.append(observation.mint)
            if len(applied) >= len(views) - 1:
                done.set()

    scheduler = _scheduler(
        overview_fetch=fetch, apply_callback=_apply,
        failure_callback=lambda mint, group, reason: failures.append(
            (mint, group, reason)))
    scheduler.update_candidates(views, now_epoch=now)
    sequence = 1
    for view in views:
        assert scheduler.apply_observation(_grpc(view, now=time.time(),
                                                 sequence=sequence))
        sequence += 1
    scheduler.plan()
    scheduler.start()
    try:
        assert done.wait(5.0)
        deadline = time.monotonic() + 2.0
        while not failures and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        scheduler.request_stop()
        assert scheduler.stop(timeout_seconds=3.0)
    assert sorted(applied) == sorted(v.mint for v in views[1:])
    assert failures and failures[0][0] == failing
    assert failures[0][2] == "PROVIDER_TIMEOUT"
    assert scheduler.snapshot(failing)["liquidity_usd"] is None, (
        "a provider failure must never leave authorizable market state")
    assert scheduler.stats()["provider_timeout_total"] >= 1


def test_several_failures_do_not_collapse_worker_pool():
    now = time.time()
    views = [_view(index, now=now) for index in range(20)]
    failing = {views[i].mint for i in (0, 3, 7, 11, 15)}
    applied = []
    done = threading.Event()

    def fetch(mint, deadline_monotonic=None):
        if mint in failing:
            raise RuntimeError("boom")
        return {"mint": mint, "current_market_cap_usd": "100",
                "liquidity_usd": "9000", "provider_timestamp_utc": _iso(time.time())}

    def _apply(observation, snapshot):
        if observation.field_group == FIELD_OVERVIEW:
            applied.append(observation.mint)
            if len(applied) >= len(views) - len(failing):
                done.set()

    scheduler = _scheduler(overview_fetch=fetch, apply_callback=_apply)
    scheduler.update_candidates(views, now_epoch=now)
    sequence = 1
    for view in views:
        assert scheduler.apply_observation(_grpc(view, now=time.time(),
                                                 sequence=sequence))
        sequence += 1
    scheduler.plan()
    scheduler.start()
    try:
        assert done.wait(5.0), f"only {len(applied)} healthy completed"
        stats = scheduler.stats()
        assert stats["active_worker_count"] == 4, "no worker-pool collapse"
    finally:
        scheduler.request_stop()
        assert scheduler.stop(timeout_seconds=3.0)
    assert len(applied) == 15
    assert scheduler.stats()["provider_error_total"] >= 5


# ---------------------------------------------------------------------------
# 3 / 4 / 5 — wrong mint, stale generation, duplicate results.
# ---------------------------------------------------------------------------


def test_wrong_mint_result_cannot_cross_apply():
    now = NOW
    views = [_view(0), _view(1)]
    scheduler = _scheduler(now_fn=lambda: now)
    scheduler.update_candidates(views, now_epoch=now)
    job_views = scheduler.plan(now_epoch=now, enqueue=False)
    overview_job = next(job for job in job_views
                        if job.field_group == FIELD_OVERVIEW
                        and job.mints[0] == views[0].mint)
    scheduler._consume_result(overview_job, {
        "mint": views[1].mint, "current_market_cap_usd": "999",
        "liquidity_usd": "99999"}, None)
    assert scheduler.snapshot(views[0].mint)["liquidity_usd"] is None
    assert scheduler.snapshot(views[1].mint)["liquidity_usd"] is None
    assert scheduler.stats()["market_wrong_mint_rejected"] == 1


def test_stale_generation_result_is_quarantined():
    now = NOW
    view = _view(0)
    scheduler = _scheduler(now_fn=lambda: now)
    scheduler.update_candidates([view], now_epoch=now)
    stale = MarketObservation(**{
        **_overview(view, now=now, sequence=5).__dict__,
        "generation": view.generation + 7})
    assert not scheduler.apply_observation(stale)
    assert scheduler.stats()["stale_result_total"] == 1
    assert scheduler.snapshot(view.mint)["liquidity_usd"] is None


def test_duplicate_result_applies_once():
    now = NOW
    view = _view(0)
    scheduler = _scheduler(now_fn=lambda: now)
    scheduler.update_candidates([view], now_epoch=now)
    first = _overview(view, now=now, sequence=3)
    assert scheduler.apply_observation(first)
    assert not scheduler.apply_observation(first)
    assert scheduler.stats()["duplicate_result_total"] == 1
    assert scheduler.snapshot(view.mint)["liquidity_usd"] == "9000"


# ---------------------------------------------------------------------------
# 6 — the production shape carries NO bulk mode; batch semantics stay tested
#     for the explicitly configured batch path only.
# ---------------------------------------------------------------------------


def test_production_shape_has_no_bulk_and_batch_partial_isolates():
    fields = production_p1_scheduler_fields()
    production = MarketSchedulerConfig(
        worker_count=fields["worker_count"],
        max_inflight=fields["max_inflight"],
        provider_min_interval_seconds=fields["provider_min_interval_seconds"],
        p1_reserved_workers=fields["p1_reserved_workers"])
    verdict = evaluate_p1_capacity(production, active_candidates=128)
    assert verdict["batch_size"] == 0, (
        "the committed provider surface has no multi-token endpoint; the "
        "capacity proof must not assume one")
    # Explicit batch configuration (non-production) still isolates partial
    # responses per mint — proven by the committed scheduler suite; here we
    # assert the partial counter contract survives the P1 rework.
    config = MarketSchedulerConfig(paid_batch_size=10)
    scheduler = MarketScheduler(
        price_fetch_fn=None, overview_fetch_fn=None,
        batch_price_fetch_fn=lambda mints: {},
        config=config, now_fn=lambda: NOW, monotonic_fn=time.monotonic)
    views = [_view(0), _view(1)]
    scheduler.update_candidates(views, now_epoch=NOW)
    job = next(job for job in scheduler.plan(now_epoch=NOW, enqueue=False)
               if job.field_group == FIELD_PRICE_MC and len(job.mints) == 2)
    scheduler._consume_result(job, {
        views[0].mint: {"mint": views[0].mint, "current_price": "1",
                        "current_market_cap_usd": "100",
                        "provider_timestamp_utc": _iso(NOW)},
    }, None)
    assert scheduler.snapshot(views[0].mint)["current_price"] == "1"
    assert scheduler.snapshot(views[1].mint)["current_price"] is None
    assert scheduler.stats()["market_batch_partial"] == 1


# ---------------------------------------------------------------------------
# 7 — queue saturation is explicit and bounded.
# ---------------------------------------------------------------------------


def test_queue_saturation_is_explicit_never_silent():
    config = MarketSchedulerConfig(
        worker_count=2, max_inflight=2, max_queue_size=4,
        provider_min_interval_seconds=0.0)
    scheduler = _scheduler(config=config, now_fn=lambda: NOW)
    views = [_view(index) for index in range(20)]
    scheduler.update_candidates(views, now_epoch=NOW)
    accepted = scheduler.plan(now_epoch=NOW, enqueue=True)
    stats = scheduler.stats()
    assert len(accepted) <= 8, "both lanes stay bounded"
    assert stats["market_scheduler_queue_depth"] <= 8
    assert MARKET_SCHEDULER_OVERLOADED in stats[
        "market_scheduler_degraded_reasons"], "overload is an explicit reason"
    # Nothing was silently lost: every due job is accepted, coalesced-on-
    # requeue, or refused with the explicit overload reason; the next plan
    # pass re-plans the remainder.
    assert scheduler.stop(timeout_seconds=1.0)


# ---------------------------------------------------------------------------
# 8 — deterministic shutdown with requests in flight.
# ---------------------------------------------------------------------------


def test_shutdown_with_inflight_is_deterministic_no_orphans():
    now = time.time()
    began = threading.Event()
    release = threading.Event()
    applied = []

    def slow_fetch(mint, deadline_monotonic=None):
        began.set()
        release.wait(2.0)
        return {"mint": mint, "current_market_cap_usd": "100",
                "liquidity_usd": "9000", "provider_timestamp_utc": _iso(time.time())}

    scheduler = _scheduler(
        overview_fetch=slow_fetch,
        apply_callback=lambda observation, snapshot: applied.append(
            observation.mint))
    views = [_view(index, now=now) for index in range(4)]
    scheduler.update_candidates(views, now_epoch=now)
    sequence = 1
    for view in views:
        assert scheduler.apply_observation(_grpc(view, now=time.time(),
                                                 sequence=sequence))
        sequence += 1
    applied.clear()
    scheduler.plan()
    scheduler.start()
    assert began.wait(2.0)
    scheduler.request_stop()
    release.set()
    assert scheduler.stop(timeout_seconds=3.0), "deterministic stop"
    assert scheduler.scheduler_state() == SCHEDULER_STOPPED
    post_stop = list(applied)
    time.sleep(0.05)
    assert applied == post_stop, "no post-shutdown mutation"
    assert not any(worker.is_alive() for worker in scheduler._workers)
    late = _overview(views[0], now=time.time(), sequence=99)
    assert not scheduler.apply_observation(late), "late results are rejected"


# ---------------------------------------------------------------------------
# 9 — priority: new P1 dispatches before an existing P3 backlog.
# ---------------------------------------------------------------------------


def test_new_p1_dispatches_before_p3_backlog():
    now = time.time()
    order = []
    gate = threading.Event()
    p1_done = threading.Event()

    def fetch(mint, deadline_monotonic=None):
        order.append(mint)
        if mint.startswith("p1mint"):
            p1_done.set()
        return {"mint": mint, "current_market_cap_usd": "100",
                "liquidity_usd": "9000", "provider_timestamp_utc": _iso(time.time())}

    background = [CandidateScheduleView(
        mint=f"bg{index:04d}" + "z" * 37 + "pump",
        candidate_id=f"bg-{index}", generation=index + 1,
        status="PENDING_BASELINE", seeded_at_epoch=now - 5.0)
        for index in range(30)]
    p1_view = CandidateScheduleView(
        mint="p1mint" + "z" * 33 + "pump", candidate_id="p1-c",
        generation=500, status="ACTIVE_DIP_WATCH", seeded_at_epoch=now - 5.0)
    config = MarketSchedulerConfig(
        worker_count=1, max_inflight=1, max_queue_size=64,
        provider_min_interval_seconds=0.0)
    scheduler = MarketScheduler(
        price_fetch_fn=fetch, overview_fetch_fn=fetch, config=config,
        now_fn=time.time, monotonic_fn=time.monotonic)
    scheduler.update_candidates(background + [p1_view], now_epoch=now)
    assert scheduler.apply_observation(_grpc(p1_view, now=now, sequence=1))
    # Queue the P3 backlog BEFORE the worker starts, then open the P1 window.
    scheduler.plan()
    assert scheduler.mark_p1_due(p1_view.mint, tier="Tier 1", now_epoch=now)
    scheduler.start()
    try:
        assert p1_done.wait(5.0), "P1 work never dispatched"
    finally:
        scheduler.request_stop()
        assert scheduler.stop(timeout_seconds=3.0)
    gate.set()
    p1_position = order.index(p1_view.mint)
    assert p1_position <= 1, (
        f"P1 dispatched at position {p1_position} behind the P3 backlog "
        f"(first five: {order[:5]})")


# ---------------------------------------------------------------------------
# 10 — supersession: newer generation invalidates queued work.
# ---------------------------------------------------------------------------


def test_newer_generation_supersedes_queued_work():
    now = time.time()
    calls = []
    view_g1 = _view(0, now=now, generation=1)
    view_g2 = _view(0, now=now, generation=2)

    def fetch(mint, deadline_monotonic=None):
        calls.append(mint)
        return {"mint": mint, "current_market_cap_usd": "100",
                "liquidity_usd": "9000", "provider_timestamp_utc": _iso(time.time())}

    scheduler = _scheduler(overview_fetch=fetch)
    scheduler.update_candidates([view_g1], now_epoch=now)
    assert scheduler.apply_observation(_grpc(view_g1, now=now, sequence=1))
    scheduler.plan()  # queues the overview job bound to generation 1
    scheduler.update_candidates([view_g2], now_epoch=now)  # rebuild/restart
    scheduler.start()
    try:
        deadline = time.monotonic() + 2.0
        while scheduler.stats()["superseded_work_total"] == 0 and (
                time.monotonic() < deadline):
            time.sleep(0.01)
    finally:
        scheduler.request_stop()
        assert scheduler.stop(timeout_seconds=3.0)
    assert scheduler.stats()["superseded_work_total"] >= 1, (
        "stale-generation queued work must be superseded, not spent")
    assert calls in ([], [view_g2.mint]), (
        f"no provider call may run under the stale binding: {calls}")


# ---------------------------------------------------------------------------
# 11 — deadline exhausted before request start.
# ---------------------------------------------------------------------------


def test_deadline_exhausted_before_start_never_requests():
    now = time.time()
    calls = []
    failures = []

    def fetch(mint, deadline_monotonic=None):
        calls.append(mint)
        return {"mint": mint, "current_market_cap_usd": "100",
                "liquidity_usd": "9000", "provider_timestamp_utc": _iso(time.time())}

    view = _view(0, now=now)
    scheduler = _scheduler(
        overview_fetch=fetch,
        failure_callback=lambda mint, group, reason: failures.append(reason))
    scheduler.update_candidates([view], now_epoch=now)
    assert scheduler.apply_observation(_grpc(view, now=now, sequence=1))
    # The tier-entry evidence is already 20 s old: the 15 s window has passed
    # before any request could start.
    assert scheduler.mark_p1_due(view.mint, tier="Tier 2",
                                 due_epoch=now - 20.0, now_epoch=now)
    scheduler.start()
    try:
        deadline = time.monotonic() + 2.0
        while not failures and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        scheduler.request_stop()
        assert scheduler.stop(timeout_seconds=3.0)
    assert calls == [], "no provider request may start after the deadline"
    assert failures and failures[0] == "P1_DEADLINE_EXHAUSTED"
    missed = scheduler.sweep_p1_deadlines()
    assert missed == 1, "the overdue window transitions to the explicit miss"
    assert scheduler.stats()["p1_deadline_missed_total"] == 1


# ---------------------------------------------------------------------------
# 12 — cache: only valid fresh overview skips the provider.
# ---------------------------------------------------------------------------


def test_fresh_overview_cache_skips_provider_stale_misses():
    now = NOW
    fresh = _view(0)
    stale = _view(1)
    scheduler = _scheduler(now_fn=lambda: now)
    scheduler.update_candidates([fresh, stale], now_epoch=now)
    assert scheduler.apply_observation(_overview(fresh, now=now, sequence=1))
    assert scheduler.apply_observation(_grpc(fresh, now=now, sequence=2))
    assert scheduler.apply_observation(_grpc(stale, now=now, sequence=3))
    assert scheduler.apply_observation(_overview(
        stale, now=now - 31.0, sequence=4))  # beyond the 30 s active TTL
    assert scheduler.mark_p1_due(fresh.mint, tier="Tier 1", now_epoch=now)
    assert scheduler.mark_p1_due(stale.mint, tier="Tier 1", now_epoch=now)
    stats = scheduler.stats()
    assert stats["cache_hit_total"] == 1, "fresh overview = no provider job"
    assert stats["cache_miss_total"] == 1, "stale overview = provider job"
    assert stats["p1_queue_depth"] == 1
    assert scheduler.stop(timeout_seconds=1.0)


# ---------------------------------------------------------------------------
# 13 — restart with 128 P1-due watches.
# ---------------------------------------------------------------------------


def test_restart_128_p1_due_reconstructs_promptly_without_duplicates():
    from types import SimpleNamespace
    now = time.time()

    def _entry(index: int, *, age: float):
        return SimpleNamespace(
            token_mint=_mint(index), candidate_id=f"hostile-{index:04d}",
            status="ACTIVE_DIP_WATCH", seeded_at_utc=_iso(now - 600),
            market_observation_generation=index + 1,
            market_latest_tier="Tier 1",
            market_market_cap_observed_at_utc=_iso(now - age),
            market_price_observed_at_utc=_iso(now - age),
            market_state=None, market_reason_code=None,
            last_observed_at_utc=_iso(now - age),
            next_market_refresh_at_utc=None,
            activation_target_market_cap_usd="120",
            last_activation_progress_market_cap_usd="118",
            delivery_next_retry_at_utc=None, market_compose_near=False,
            market_scheduler_quarantined=False, market_terminal_history=False)

    entries = [_entry(index, age=(2.0 if index else 20.0))
               for index in range(128)]
    scheduler = _scheduler(now_fn=lambda: now, config=MarketSchedulerConfig(
        worker_count=4, max_inflight=4, max_queue_size=256,
        provider_min_interval_seconds=0.0))
    scheduler.update_candidates(entries, now_epoch=now)
    first = scheduler.reconstruct_p1_from_watch(entries, now_epoch=now)
    again = scheduler.reconstruct_p1_from_watch(entries, now_epoch=now)
    assert first == {"reconstructed": 128, "already_overdue": 1}
    assert again == {"reconstructed": 0, "already_overdue": 0}, (
        "reconstruction must be idempotent — no duplicate windows, no "
        "duplicate provider work")
    stats = scheduler.stats()
    assert stats["p1_enqueued_total"] == 128
    assert stats["p1_queue_depth"] == 128
    assert stats["oldest_p1_age_seconds"] >= 19.0
    assert scheduler.sweep_p1_deadlines(now_epoch=now) == 1
    assert scheduler.stop(timeout_seconds=1.0)


# ---------------------------------------------------------------------------
# 14 / 15 / 16 — configuration refusals and the centralized clamp.
# ---------------------------------------------------------------------------


def test_reduced_throughput_refuses_before_network():
    fields = production_p1_scheduler_fields()
    slowed = MarketSchedulerConfig(
        worker_count=fields["worker_count"],
        max_inflight=fields["max_inflight"],
        provider_min_interval_seconds=1.05,   # throughput reduced
        p1_reserved_workers=fields["p1_reserved_workers"])
    verdict = evaluate_p1_capacity(slowed, active_candidates=128)
    assert verdict["p1_capacity_achievable"] is False
    assert verdict["refusal_reason"] == P1_CAPACITY_UNACHIEVABLE
    scheduler = _scheduler(now_fn=lambda: NOW)
    scheduler.note_capacity_proof(verdict)
    assert scheduler.scheduler_state() == SCHEDULER_CAPACITY_REFUSED
    assert scheduler.stats()["capacity_proof_result"] == P1_CAPACITY_UNACHIEVABLE
    assert scheduler.stop(timeout_seconds=1.0)


@pytest.mark.parametrize("kwargs", (
    {"worker_count": 0},
    {"worker_count": -3},
    {"worker_count": 17},
    {"worker_count": 4, "max_inflight": 0},
    {"worker_count": 4, "max_inflight": 5},
    {"worker_count": 4, "p1_reserved_workers": 4},
    {"worker_count": 4, "p1_reserved_workers": -1},
    {"p1_deadline_seconds": 0.0},
    {"p1_deadline_seconds": -15.0},
    {"healthy_response_budget_seconds": 0.0},
    {"p1_max_attempts": 0},
    {"p1_max_attempts": 6},
    {"p1_request_timeout_seconds": 0.0},
    {"provider_min_interval_seconds": -0.1},
))
def test_invalid_concurrency_and_budget_configuration_rejects(kwargs):
    with pytest.raises(ValueError):
        MarketSchedulerConfig(**kwargs)


def test_transport_concurrency_bounds_reject():
    for bad in (0, -1, 65):
        with pytest.raises(ValueError):
            PaidBirdeyeMarketTransport(
                inner_transport=object(), endpoint_secret=object(),
                max_concurrency=bad)


def test_request_timeout_clamps_through_one_centralized_rule():
    config = MarketSchedulerConfig(
        p1_request_timeout_seconds=30.0, p1_deadline_seconds=15.0,
        dispatch_overhead_budget_seconds=0.5)
    assert config.effective_p1_attempt_timeout_seconds() == 14.5
    small = MarketSchedulerConfig(
        p1_request_timeout_seconds=4.0, p1_deadline_seconds=15.0)
    assert small.effective_p1_attempt_timeout_seconds() == 4.0
    verdict = evaluate_p1_capacity(config, active_candidates=1)
    assert verdict["effective_p1_attempt_timeout_seconds"] == 14.5


# ---------------------------------------------------------------------------
# Boundaries: 0 / 1 / concurrency-1 / concurrency / concurrency+1 / 127 /
# 128 / 129 under the exact production formula.
# ---------------------------------------------------------------------------


def _production_config() -> MarketSchedulerConfig:
    fields = production_p1_scheduler_fields()
    return MarketSchedulerConfig(
        worker_count=fields["worker_count"],
        max_inflight=fields["max_inflight"],
        provider_min_interval_seconds=fields["provider_min_interval_seconds"],
        p1_deadline_seconds=fields["p1_deadline_seconds"],
        healthy_response_budget_seconds=fields["healthy_response_budget_seconds"],
        dispatch_overhead_budget_seconds=fields["dispatch_overhead_budget_seconds"],
        p1_max_attempts=fields["p1_max_attempts"],
        p1_request_timeout_seconds=fields["p1_request_timeout_seconds"],
        p1_reserved_workers=fields["p1_reserved_workers"],
    )


@pytest.mark.parametrize("count", (0, 1, 15, 16, 17, 127, 128, 129))
def test_capacity_boundaries_are_exact_and_monotonic(count):
    config = _production_config()
    verdict = evaluate_p1_capacity(config, active_candidates=count)
    assert verdict["configured_active_cap"] == count
    if count == 0:
        assert verdict["calculated_worst_case_bound_seconds"] == 0.5
    if count <= 16:
        # Inside one concurrency wave: pacing + one response budget.
        expected = (max(0, count - 1) * 0.09 + (1.5 if count else 0.0) + 0.5)
        assert abs(verdict["calculated_worst_case_bound_seconds"]
                   - expected) < 1e-6
    assert verdict["p1_capacity_achievable"] is True
    if count:
        smaller = evaluate_p1_capacity(config, active_candidates=count - 1)
        assert (smaller["calculated_worst_case_bound_seconds"]
                <= verdict["calculated_worst_case_bound_seconds"])


def test_128_bound_is_13_85_and_129th_is_watch_capacity_rejected(tmp_path):
    config = _production_config()
    verdict = evaluate_p1_capacity(config, active_candidates=128)
    assert abs(verdict["calculated_worst_case_bound_seconds"] - 13.85) < 1e-6
    assert verdict["p1_capacity_achievable"] is True
    # The 129th candidate is refused by the ACTIVE-WATCH capacity contract
    # (PHX2-E2E-002) with the explicit closed-set reason — never admitted,
    # never silently lost — so the first 128 keep their deadline guarantee.
    from PHX2.free_tier_producer.compat.build30_watchlist import (
        SEED_OUTCOME_ADMITTED,
        SEED_OUTCOME_CAPACITY,
        Watchlist,
    )
    watch = Watchlist(max_size=128,
                      terminal_history_path=tmp_path / "history.jsonl")
    for index in range(128):
        entry, outcome = watch.seed_with_outcome(
            {"token_mint": _mint(index), "candidate_id": f"cap-{index}"},
            seeded_at_utc=_iso(NOW))
        assert entry is not None and outcome == SEED_OUTCOME_ADMITTED
    extra, outcome = watch.seed_with_outcome(
        {"token_mint": _mint(128), "candidate_id": "cap-128"},
        seeded_at_utc=_iso(NOW))
    assert extra is None
    assert outcome == SEED_OUTCOME_CAPACITY == "ACTIVE_WATCH_CAPACITY_REACHED"
    assert watch.active_count() == 128, "the first 128 keep their slots"


# ---------------------------------------------------------------------------
# Engine-reason projection stays a closed set.
# ---------------------------------------------------------------------------


def test_engine_reason_projection_is_total_and_closed():
    assert classify_engine_reason_to_p1_outcome(
        "SENT_OK_COMMITTED") == P1_RESULT_DISPATCH_EVALUATED
    assert classify_engine_reason_to_p1_outcome(
        "DELIVERY_FAILED_RETRYABLE") == P1_RESULT_DISPATCH_EVALUATED
    assert classify_engine_reason_to_p1_outcome("PROVIDER_TIMEOUT") == (
        "P1_RESULT_PROVIDER_FAILURE")
    assert classify_engine_reason_to_p1_outcome("RISK_HIGH_BLOCKED") == (
        "P1_RESULT_TEMP_BLOCKED")
    assert classify_engine_reason_to_p1_outcome("NOT_PUMP_SUFFIX") == (
        "P1_RESULT_PERM_BLOCKED")
    assert classify_engine_reason_to_p1_outcome(None) is None
    assert classify_engine_reason_to_p1_outcome("") is None
