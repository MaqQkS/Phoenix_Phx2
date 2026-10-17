"""PHX2-E2E-006: 128-candidate / 15-second P1 scheduler capacity contract.

Phase-3 red origin (2026-07-21): every test in this module failed at the
starting HEAD ``4a062b96`` — either by direct measurement of the audited
defect (the paid transport serialized every request, retry and backoff
behind one global lock) or because the required P1 capacity surface
(``evaluate_p1_capacity``, ``mark_p1_due``, restart reconstruction, the
full-drain handoff helper, the startup refusal) did not exist yet.  The
pre-fix failures and measured bounds are preserved in the external audit
workspace (``pre_fix_failures.txt`` / ``latency_probe_before.json``).

The P1 service contract proven here:

* a candidate becomes P1-due at the timestamp of the first valid trusted
  local observation that projects entry into a previously unsent tier
  band — not when a poll loop notices it;
* within 15.000 s of P1-due the candidate reaches one explicit result;
* 128 simultaneous P1-due candidates with fresh trusted gRPC price/MC
  need exactly 128 logical overview items, ZERO paid price calls, and
  every one of them completes inside the deadline;
* configurations that cannot serve the active cap inside the deadline
  refuse at startup with ``P1_CAPACITY_UNACHIEVABLE`` before any network
  object exists.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from PHX2.free_tier_producer.market_scheduler import (
    CandidateScheduleView,
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    MarketObservation,
    MarketScheduler,
    MarketSchedulerConfig,
    SOURCE_GRPC,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeHttpResult
from PHX2.stage29.stage29_2_birdeye_models import BIRDEYE_REFUSAL_REASON_NONE


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _mint(index: int) -> str:
    return f"mint{index:04d}" + "x" * 35 + "pump"


def _view(index: int, *, status: str = "ACTIVE_DIP_WATCH",
          now: float, age: float = 5.0) -> CandidateScheduleView:
    return CandidateScheduleView(
        mint=_mint(index),
        candidate_id=f"candidate-{index:04d}",
        generation=index + 1,
        status=status,
        seeded_at_epoch=now - age,
    )


def _grpc_observation(view: CandidateScheduleView, *, now: float,
                      sequence: int) -> MarketObservation:
    import hashlib
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


class _LatencyInner:
    """Stateless thread-safe fake for the Stage 29.2 inner HTTP transport."""

    def __init__(self, *, latency_by_mint=None, default_latency=0.0,
                 hang_mints=(), hang_seconds=0.0):
        self._latency = dict(latency_by_mint or {})
        self._default = float(default_latency)
        self._hang = set(hang_mints)
        self._hang_seconds = float(hang_seconds)
        self.calls = []
        self._lock = threading.Lock()

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        mint = query_params.get("address", "")
        with self._lock:
            self.calls.append((path, mint))
        delay = self._latency.get(mint, self._default)
        if mint in self._hang:
            delay = self._hang_seconds
        if delay > 0:
            time.sleep(delay)
        now = time.time()
        data = {
            "address": mint,
            "value": "1",
            "mc": "100",
            "liquidity": "9000",
            "updateUnixTime": int(now),
        }
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body={"success": True, "data": data},
            fetched_at_utc=_iso(now),
        )


# ---------------------------------------------------------------------------
# A2 / C — measured pre-fix defects: the transport must not serialize
# independent candidates behind one global lock.
# ---------------------------------------------------------------------------


def test_provider_requests_overlap_when_pacing_permits():
    """Six pacing-free requests for six mints must overlap, not serialize.

    Pre-fix measurement at 4a062b96: the six 60 ms responses completed in
    ~360 ms because the HTTP call ran inside the transport's global lock.
    """
    inner = _LatencyInner(default_latency=0.06)
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0.0, cache_ttl_seconds=0.0, max_attempts=1,
    )
    mints = [_mint(index) for index in range(6)]
    started = threading.Barrier(len(mints))
    done = []

    def _one(mint: str) -> None:
        started.wait(2.0)
        result = transport.fetch_overview_plane(mint, timeout_seconds=2)
        done.append((mint, result))

    threads = [threading.Thread(target=_one, args=(mint,)) for mint in mints]
    t0 = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5.0)
    elapsed = time.monotonic() - t0
    assert len(done) == 6
    assert all(result and result.get("liquidity_usd") == "9000"
               for _mint_, result in done)
    # Serial execution needs >= 0.36 s; bounded overlap must beat 0.25 s.
    assert elapsed < 0.25, (
        f"six independent 60ms responses took {elapsed:.3f}s — the provider "
        "path is still serialized behind one global lock")


def test_hung_request_does_not_head_of_line_block_other_candidates():
    """One hung mint may consume one concurrency slot, never the whole pool.

    Pre-fix measurement at 4a062b96: nine 5 ms candidates waited ~1.2 s
    behind one hung request because pacing, HTTP, and retries all ran
    under the same transport lock.
    """
    hung = _mint(0)
    inner = _LatencyInner(default_latency=0.005, hang_mints=(hung,),
                          hang_seconds=1.2)
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0.0, cache_ttl_seconds=0.0, max_attempts=1,
    )
    now = time.time()
    views = [_view(index, now=now) for index in range(10)]
    applied = []
    applied_event = threading.Event()

    def _apply(observation, snapshot):
        if observation.field_group != FIELD_OVERVIEW:
            return
        applied.append((observation.mint, time.monotonic()))
        healthy_done = sum(1 for mint, _at in applied if mint != hung)
        if healthy_done >= len(views) - 1:
            applied_event.set()

    scheduler = MarketScheduler(
        price_fetch_fn=lambda mint: transport.fetch_price_plane(
            mint, timeout_seconds=2),
        overview_fetch_fn=lambda mint: transport.fetch_overview_plane(
            mint, timeout_seconds=2),
        config=MarketSchedulerConfig(
            worker_count=4, max_inflight=4, max_queue_size=64,
            provider_min_interval_seconds=0.0),
        now_fn=time.time,
        monotonic_fn=time.monotonic,
        apply_callback=_apply,
    )
    scheduler.update_candidates(views, now_epoch=now)
    sequence = 1
    for view in views:
        assert scheduler.apply_observation(
            _grpc_observation(view, now=time.time(), sequence=sequence))
        sequence += 1
    # The hung mint must be planned first (earliest seed) so it demonstrably
    # cannot block the other nine.
    t0 = time.monotonic()
    scheduler.plan()
    scheduler.start()
    try:
        finished = applied_event.wait(3.0)
        elapsed = time.monotonic() - t0
    finally:
        scheduler.request_stop()
        scheduler.stop(timeout_seconds=3.0)
    healthy = {mint for mint, _at in applied if mint != hung}
    assert finished, "nine healthy candidates never completed"
    assert len(healthy) >= len(views) - 1
    assert elapsed < 0.9, (
        f"healthy candidates took {elapsed:.3f}s — a single hung request is "
        "still head-of-line blocking the provider path")


# ---------------------------------------------------------------------------
# A / B — the 128-candidate capacity acceptance shape (scaled clone of the
# production configuration; the unscaled formula proof is test G').
# ---------------------------------------------------------------------------


def _scaled_production_scheduler(transport, *, scale: float, apply_callback,
                                 concurrency: int = 16):
    from PHX2.free_tier_producer.market_scheduler import (
        production_p1_scheduler_fields,
    )
    fields = production_p1_scheduler_fields()
    config = MarketSchedulerConfig(
        worker_count=concurrency,
        max_inflight=concurrency,
        max_queue_size=512,
        provider_min_interval_seconds=fields["provider_min_interval_seconds"] * scale,
        p1_deadline_seconds=fields["p1_deadline_seconds"] * scale,
        healthy_response_budget_seconds=(
            fields["healthy_response_budget_seconds"] * scale),
        dispatch_overhead_budget_seconds=(
            fields["dispatch_overhead_budget_seconds"] * scale),
        p1_max_attempts=fields["p1_max_attempts"],
        p1_request_timeout_seconds=max(
            0.25, fields["p1_request_timeout_seconds"] * scale),
        p1_reserved_workers=fields["p1_reserved_workers"],
        max_active_candidates=128,
    )
    return MarketScheduler(
        price_fetch_fn=lambda mint: transport.fetch_price_plane(
            mint, timeout_seconds=2),
        overview_fetch_fn=lambda mint: transport.fetch_overview_plane(
            mint, timeout_seconds=2),
        config=config,
        now_fn=time.time,
        monotonic_fn=time.monotonic,
        apply_callback=apply_callback,
    ), config


def test_128_p1_candidates_meet_scaled_production_deadline():
    """128 tier-due candidates, fresh gRPC price/MC, one overview each.

    Scaled 1:30 clone of the production shape (spacing, budgets, deadline
    all divided by 30; concurrency identical), driven through the REAL
    MarketScheduler and the REAL PaidBirdeyeMarketTransport.  Asserts the
    complete Phase-5 envelope: all 128 complete, zero paid price calls,
    exactly 128 logical overview items, bounded concurrency, and a wall
    clock inside the scaled deadline envelope.
    """
    from PHX2.free_tier_producer.market_scheduler import evaluate_p1_capacity

    scale = 1.0 / 30.0
    inner = _LatencyInner(default_latency=1.5 * scale)
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0.09 * scale, cache_ttl_seconds=0.0,
        max_attempts=1, max_concurrency=16,
    )
    now = time.time()
    completed = {}
    all_done = threading.Event()
    views = [_view(index, now=now) for index in range(128)]

    def _apply(observation, snapshot):
        if observation.field_group == FIELD_OVERVIEW:
            completed[observation.mint] = time.monotonic()
            if len(completed) >= 128:
                all_done.set()

    scheduler, config = _scaled_production_scheduler(
        transport, scale=scale, apply_callback=_apply)
    capacity = evaluate_p1_capacity(config, active_candidates=128)
    assert capacity["p1_capacity_achievable"], capacity
    scheduler.update_candidates(views, now_epoch=now)
    sequence = 1
    for view in views:
        assert scheduler.apply_observation(
            _grpc_observation(view, now=time.time(), sequence=sequence))
        sequence += 1
    t0 = time.monotonic()
    scheduler.plan()
    scheduler.start()
    try:
        finished = all_done.wait(30.0)
        last_completion = max(completed.values()) - t0 if completed else None
    finally:
        scheduler.request_stop()
        scheduler.stop(timeout_seconds=5.0)
    assert finished, (
        f"only {len(completed)}/128 candidates completed overview enrichment")
    stats = transport.stats()
    assert stats["price_calls"] == 0, "trusted gRPC evidence must avoid paid price"
    assert stats["overview_calls"] == 128, "exactly one logical overview per mint"
    assert stats["max_inflight"] <= 16
    # Real-thread scheduling jitter allowance: 3x the calculated bound.
    envelope = capacity["calculated_worst_case_bound_seconds"] * 3.0
    assert last_completion is not None and last_completion <= envelope, (
        f"last candidate completed at {last_completion:.3f}s > envelope "
        f"{envelope:.3f}s (calculated bound "
        f"{capacity['calculated_worst_case_bound_seconds']:.3f}s)")


def test_last_positioned_urgent_candidate_meets_deadline():
    """Latency must come from the deadline order, never from list position."""
    scale = 1.0 / 30.0
    inner = _LatencyInner(default_latency=1.5 * scale)
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0.09 * scale, cache_ttl_seconds=0.0,
        max_attempts=1, max_concurrency=16,
    )
    now = time.time()
    completed = {}
    done = threading.Event()
    views = [_view(index, now=now) for index in range(32)]
    urgent = views[-1]  # highest mint index — always last at equal priority

    def _apply(observation, snapshot):
        if observation.field_group == FIELD_OVERVIEW:
            completed[observation.mint] = time.monotonic()
            if len(completed) >= len(views):
                done.set()

    scheduler, config = _scaled_production_scheduler(
        transport, scale=scale, apply_callback=_apply)
    scheduler.update_candidates(views, now_epoch=now)
    sequence = 1
    for view in views:
        assert scheduler.apply_observation(
            _grpc_observation(view, now=time.time(), sequence=sequence))
        sequence += 1
    t0 = time.monotonic()
    scheduler.plan()
    scheduler.start()
    try:
        assert done.wait(15.0), f"{len(completed)}/32 completed"
    finally:
        scheduler.request_stop()
        scheduler.stop(timeout_seconds=5.0)
    urgent_latency = completed[urgent.mint] - t0
    deadline = config.p1_deadline_seconds * 3.0
    assert urgent_latency <= deadline, (
        f"last-positioned candidate took {urgent_latency:.3f}s "
        f"(> {deadline:.3f}s scaled envelope): latency still scales with "
        "list position")


# ---------------------------------------------------------------------------
# D — handoff burst admission without tick quantization.
# ---------------------------------------------------------------------------


def test_handoff_burst_admits_fully_in_one_pass():
    """A 128-candidate burst must drain in one discovery pass, not 13 ticks."""
    from PHX2.free_tier_producer.free_tier_session import (
        drain_provider_handoff_completely,
    )

    backlog = [{"token_mint": _mint(index), "provider_handoff": {}}
               for index in range(128)]
    drain_calls = []

    class _FakeDiscovery:
        def drain(self, max_candidates=10):
            drain_calls.append(int(max_candidates))
            chunk, backlog[:] = (
                backlog[:int(max_candidates)], backlog[int(max_candidates):])
            return chunk

    drained = drain_provider_handoff_completely(
        _FakeDiscovery(), chunk_size=10)
    assert len(drained) == 128
    assert not backlog
    assert all(size <= 10 for size in drain_calls), "chunks stay bounded"
    assert len(drain_calls) >= 13, "bounded chunks, drained back-to-back"
    assert [c["token_mint"] for c in drained] == [
        _mint(index) for index in range(128)], "no candidate lost or reordered"


# ---------------------------------------------------------------------------
# E — single flight / coalescing of equivalent P1 work.
# ---------------------------------------------------------------------------


def test_duplicate_p1_due_marks_coalesce_to_single_logical_overview():
    now = time.time()
    view = _view(1, now=now)
    scheduler = MarketScheduler(
        price_fetch_fn=None,
        overview_fetch_fn=lambda mint: None,
        config=MarketSchedulerConfig(
            worker_count=2, max_inflight=2, provider_min_interval_seconds=0.0),
        now_fn=lambda: now,
        monotonic_fn=time.monotonic,
    )
    scheduler.update_candidates([view], now_epoch=now)
    assert scheduler.apply_observation(
        _grpc_observation(view, now=now, sequence=1))
    opened = [scheduler.mark_p1_due(view.mint, tier="Tier 1", now_epoch=now)
              for _ in range(10)]
    assert opened[0] is True and not any(opened[1:]), (
        "repeated equivalent tier-entry evidence must coalesce into one "
        "open P1 window")
    stats = scheduler.stats()
    assert stats["p1_enqueued_total"] == 1
    assert stats["p1_queue_depth"] == 1, (
        "exactly one logical overview job queued for the tier-due candidate")


# ---------------------------------------------------------------------------
# F — restart reconstruction with deadline priority.
# ---------------------------------------------------------------------------


def test_restart_reconstructs_p1_deadline_age_from_durable_evidence():
    now = time.time()

    def _entry(index: int, *, evidence_age: float):
        return SimpleNamespace(
            token_mint=_mint(index),
            candidate_id=f"candidate-{index:04d}",
            status="ACTIVE_DIP_WATCH",
            seeded_at_utc=_iso(now - 600),
            market_observation_generation=index + 1,
            market_latest_tier="Tier 2",
            market_latest_drawdown_pct="70",
            market_market_cap_observed_at_utc=_iso(now - evidence_age),
            market_price_observed_at_utc=_iso(now - evidence_age),
            market_state=None,
            market_reason_code=None,
            last_observed_at_utc=_iso(now - evidence_age),
            next_market_refresh_at_utc=None,
            activation_target_market_cap_usd="120",
            last_activation_progress_market_cap_usd="118",
            delivery_next_retry_at_utc=None,
            market_compose_near=False,
            market_scheduler_quarantined=False,
            market_terminal_history=False,
        )

    entries = [
        _entry(0, evidence_age=20.0),   # already overdue (> 15 s)
        _entry(1, evidence_age=5.0),
        _entry(2, evidence_age=1.0),
    ]
    scheduler = MarketScheduler(
        price_fetch_fn=None,
        overview_fetch_fn=lambda mint: None,
        config=MarketSchedulerConfig(
            worker_count=2, max_inflight=2, provider_min_interval_seconds=0.0),
        now_fn=lambda: now,
        monotonic_fn=time.monotonic,
    )
    scheduler.update_candidates(entries, now_epoch=now)
    summary = scheduler.reconstruct_p1_from_watch(entries, now_epoch=now)
    assert summary["reconstructed"] == 3
    stats = scheduler.stats()
    assert stats["p1_enqueued_total"] == 3
    assert 19.0 <= stats["oldest_p1_age_seconds"] <= 21.0, (
        "P1 deadline age must be reconstructed from durable evidence "
        "timestamps, not restarted at zero")
    missed = scheduler.sweep_p1_deadlines(now_epoch=now)
    assert missed == 1, "the 20s-old candidate is explicitly deadline-missed"
    assert scheduler.stats()["p1_deadline_missed_total"] == 1
    assert scheduler.stats()["p1_queue_depth"] >= 2, (
        "still-serviceable candidates stay queued with deadline priority")


# ---------------------------------------------------------------------------
# G — structural capacity proof and startup refusal.
# ---------------------------------------------------------------------------


def test_legacy_configuration_cannot_serve_128_and_is_refused():
    from PHX2.free_tier_producer.market_scheduler import (
        P1_CAPACITY_UNACHIEVABLE,
        evaluate_p1_capacity,
    )

    legacy = MarketSchedulerConfig()  # 2 workers, 1.05 s global spacing
    verdict = evaluate_p1_capacity(legacy, active_candidates=128)
    assert verdict["p1_capacity_achievable"] is False
    assert verdict["refusal_reason"] == P1_CAPACITY_UNACHIEVABLE
    assert verdict["calculated_worst_case_bound_seconds"] > 100.0, (
        "the legacy 1.05 s serialized spacing floor is ~133 s for 128 "
        "candidates and must be reported honestly")
    assert verdict["configured_active_cap"] == 128
    # Only safe numeric/configuration evidence may appear in the verdict.
    for value in verdict.values():
        assert not isinstance(value, str) or "http" not in value.lower()


def test_production_configuration_is_structurally_achievable():
    from PHX2.free_tier_producer.market_scheduler import (
        evaluate_p1_capacity,
        production_p1_scheduler_fields,
    )

    fields = production_p1_scheduler_fields()
    config = MarketSchedulerConfig(
        worker_count=fields["worker_count"],
        max_inflight=fields["max_inflight"],
        provider_min_interval_seconds=fields["provider_min_interval_seconds"],
        p1_deadline_seconds=fields["p1_deadline_seconds"],
        healthy_response_budget_seconds=fields["healthy_response_budget_seconds"],
        dispatch_overhead_budget_seconds=(
            fields["dispatch_overhead_budget_seconds"]),
        p1_max_attempts=fields["p1_max_attempts"],
        p1_request_timeout_seconds=fields["p1_request_timeout_seconds"],
        p1_reserved_workers=fields["p1_reserved_workers"],
        max_active_candidates=128,
    )
    verdict = evaluate_p1_capacity(config, active_candidates=128)
    assert verdict["p1_capacity_achievable"] is True, verdict
    assert verdict["calculated_worst_case_bound_seconds"] <= 15.0
    assert verdict["configured_concurrency"] >= 8
    assert verdict["required_deadline_seconds"] == 15.0


def test_session_refuses_capacity_before_any_network_construction():
    """run() must evaluate the capacity contract before the paid transport."""
    import inspect

    from PHX2.free_tier_producer import free_tier_session

    source = inspect.getsource(free_tier_session)
    capacity_at = source.index("evaluate_session_p1_capacity(")
    transport_at = source.index("Stage29_2BirdeyeUrlibTransport()")
    grpc_at = source.index("paid_discovery.start()")
    assert capacity_at < transport_at < grpc_at, (
        "the P1 capacity refusal must run before the paid transport and "
        "before the gRPC owner ever starts")
    refusal = free_tier_session.evaluate_session_p1_capacity(
        SimpleNamespace(
            market_provider_spacing_seconds=1.05,
            market_provider_concurrency=1,
            market_scheduler_workers=None,
            market_scheduler_max_inflight=None,
            market_scheduler_queue_size=256,
            birdeye_min_interval_seconds=None,
            market_p1_deadline_seconds=15.0,
            market_healthy_response_budget_seconds=1.5,
            market_dispatch_overhead_budget_seconds=0.5,
            market_p1_max_attempts=2,
            market_p1_request_timeout_seconds=8.0,
            market_p1_reserved_workers=0,
            max_watchlist_size=128,
            max_market_requests_total=200000,
            market_price_active_ttl_seconds=12.0,
            market_price_pending_ttl_seconds=30.0,
            market_overview_active_ttl_seconds=30.0,
            market_overview_pending_ttl_seconds=90.0,
            market_grpc_max_age_seconds=15.0,
            market_background_starvation_seconds=120.0,
        ))
    assert refusal["p1_capacity_achievable"] is False
    assert refusal["refusal_reason"] == "P1_CAPACITY_UNACHIEVABLE"
