from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import threading
import time

from PHX2.free_tier_producer.market_scheduler import (
    CandidateScheduleView,
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    LATENCY_SLO_UNACHIEVABLE,
    MARKET_BATCH_PARTIAL,
    MARKET_SCHEDULER_BACKLOG_HIGH,
    MarketObservation,
    MarketScheduler,
    MarketSchedulerConfig,
    PRIORITY_P0,
    PRIORITY_P1,
    PRIORITY_P2,
    PRIORITY_P3,
    SOURCE_GRPC,
    SOURCE_PAID_SINGLE,
    offline_grpc_vs_helius_comparison_fixture,
    old_serial_latency_fixture,
    project_closed_tier,
)
from PHX2.free_tier_producer.ath_state import (
    SOURCE_PUMPSWAP_EVENT,
    STATUS_CONFIRMED,
)
from PHX2.tests import test_ath_activation_risk_regression as activation_fixture


NOW = 1_700_000_000.0


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _view(index: int, *, status: str = "PENDING_1_20X", age: float = 1.0,
          next_recovery: float | None = None, near: bool = False,
          quarantined: bool = False, terminal_history: bool = False,
          delivery_due: bool = False,
          market_state: str | None = None) -> CandidateScheduleView:
    return CandidateScheduleView(
        mint=f"mint-{index:03d}-pump",
        candidate_id=f"candidate-{index:03d}",
        generation=index + 1,
        status=status,
        seeded_at_epoch=NOW - age,
        market_state=(market_state or (
            "MARKET_RECOVERY_BACKOFF"
            if status == "MARKET_RECOVERY_BACKOFF" else None)),
        last_observed_epoch=None,
        next_recovery_epoch=next_recovery,
        activation_target_market_cap_usd=("120" if near else "120"),
        last_activation_market_cap_usd=("118" if near else "20"),
        delivery_retry_due=delivery_due,
        quarantined=quarantined,
        terminal_history=terminal_history,
    )


def _scheduler(*, config: MarketSchedulerConfig | None = None,
               price_fetch=None, overview_fetch=None, batch_fetch=None,
               callback=None, failure=None, quote_apply=None) -> MarketScheduler:
    return MarketScheduler(
        price_fetch_fn=price_fetch,
        overview_fetch_fn=overview_fetch,
        batch_price_fetch_fn=batch_fetch,
        config=config or MarketSchedulerConfig(),
        now_fn=lambda: NOW,
        monotonic_fn=time.monotonic,
        apply_callback=callback,
        failure_callback=failure,
        quote_price_apply_fn=quote_apply,
    )


def _observation(view: CandidateScheduleView, *, field=FIELD_PRICE_MC,
                 source=SOURCE_PAID_SINGLE, source_at=NOW, sequence=1,
                 price="1", mc="100", liquidity="5000") -> MarketObservation:
    values = ({"current_price": price, "current_market_cap_usd": mc}
              if field == FIELD_PRICE_MC
              else {"current_market_cap_usd": mc, "liquidity_usd": liquidity})
    return MarketObservation(
        mint=view.mint,
        candidate_id=view.candidate_id,
        generation=view.generation,
        source=source,
        source_timestamp=source_at,
        ingestion_timestamp=source_at,
        field_group=field,
        observation_sequence=sequence,
        source_evidence_digest=hashlib.sha256(
            f"{view.mint}:{field}:{sequence}".encode()).hexdigest(),
        request_id=f"request-{sequence}",
        values=values,
    )


def _trusted_payload(view: CandidateScheduleView, *, source_at=NOW,
                     price="1", mc="100", slot=1) -> dict:
    ingestion = _iso(source_at)
    evidence_payload = {
        "schema_version": "phx2_trusted_reserve_market_v1",
        "mint": view.mint,
        "pool_address": "pool",
        "base_vault": "base-vault",
        "quote_vault": "quote-vault",
        "quote_mint": "quote-mint",
        "base_decimals": 6,
        "quote_decimals": 6,
        "base_supply": "1000000",
        "raw_quote_reserves": "100",
        "virtual_quote_reserves": "0",
        "effective_quote_reserves": "100",
        "base_reserves": "100",
        "transaction_signature": "signature",
        "slot": slot,
        "outer_instruction_index": 1,
        "inner_instruction_index": 2,
        "flattened_instruction_index": 3,
        "event_index": 0,
        "source_timestamp": _iso(source_at),
        "migration_proof_digest": "a" * 64,
        "transaction_succeeded": True,
        "source_event_proven": True,
    }
    evidence = hashlib.sha256(json.dumps(
        evidence_payload, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    seal_payload = {
        "seal_version": "phx2_trusted_reserve_seal_v1",
        "source_evidence_digest": evidence,
        "ingestion_timestamp": ingestion,
    }
    seal = hashlib.sha256(json.dumps(
        seal_payload, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return {
        **evidence_payload,
        "reserve_trusted_for_routing": True,
        "pool_replacement_conflict": False,
        "source_evidence_digest": evidence,
        "observation_seal_version": "phx2_trusted_reserve_seal_v1",
        "observation_seal_digest": seal,
        "ingestion_timestamp": ingestion,
        "current_price": price,
        "current_market_cap_usd": mc,
    }


def _apply_fresh(scheduler: MarketScheduler, view: CandidateScheduleView,
                 *, price=True, overview=True, sequence=1) -> int:
    if price:
        assert scheduler.apply_observation(_observation(view, sequence=sequence))
        sequence += 1
    if overview:
        assert scheduler.apply_observation(_observation(
            view, field=FIELD_OVERVIEW, sequence=sequence))
        sequence += 1
    return sequence


def test_old_128_mint_serial_fixture_exceeds_safe_latency_bound():
    result = old_serial_latency_fixture()
    assert result == {
        "candidate_count": 128,
        "provider_calls": 256,
        "pacing_floor_seconds": 267.75,
        "final_watch_sleep_seconds": 45.0,
        "total_floor_seconds": 312.75,
    }


def test_scheduler_priority_is_not_insertion_order_and_p0_precedes_all():
    scheduler = _scheduler()
    scheduler.update_candidates([
        _view(3, status="PENDING_1_20X"),
        _view(2, status="PENDING_1_20X", near=True),
        _view(1, status="ACTIVE_DIP_WATCH"),
        _view(0, status="MARKET_RECOVERY_BACKOFF", next_recovery=NOW - 1),
    ], now_epoch=NOW)
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    first_by_mint = {}
    for job in jobs:
        first_by_mint.setdefault(job.mints[0], job.priority)
    assert list(first_by_mint.values()) == [PRIORITY_P0, PRIORITY_P1,
                                            PRIORITY_P2, PRIORITY_P3]


def test_aging_promotes_background_and_prevents_starvation():
    scheduler = _scheduler()
    old = _view(1, age=121)
    scheduler.update_candidates([old], now_epoch=NOW)
    assert {job.priority for job in scheduler.plan(
        now_epoch=NOW, enqueue=False)} == {PRIORITY_P0}
    assert "MARKET_OBSERVATION_STARVED" in scheduler.stats()[
        "market_scheduler_degraded_reasons"]


def test_deadline_order_and_stable_mint_tie_break_are_deterministic():
    scheduler = _scheduler()
    views = [_view(2, age=10), _view(0, age=10), _view(1, age=10)]
    scheduler.update_candidates(views, now_epoch=NOW)
    jobs = [job for job in scheduler.plan(now_epoch=NOW, enqueue=False)
            if job.field_group == FIELD_PRICE_MC]
    assert [job.mints[0] for job in jobs] == sorted(view.mint for view in views)


def test_trusted_grpc_updates_price_mc_and_avoids_paid_price_call():
    applied = []
    view = _view(1, status="ACTIVE_DIP_WATCH")
    scheduler = _scheduler(callback=lambda obs, snap: applied.append((obs, snap)))
    scheduler.update_candidates([view], now_epoch=NOW)
    assert scheduler.submit_trusted_reserve(_trusted_payload(view))
    snapshot = scheduler.snapshot(view.mint, now_epoch=NOW)
    assert snapshot["current_price"] == "1"
    assert snapshot["current_market_cap_usd"] == "100"
    assert snapshot["price_source"] == SOURCE_GRPC
    assert applied and applied[0][0].source == SOURCE_GRPC
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert not [job for job in jobs if job.field_group == FIELD_PRICE_MC]
    assert scheduler.stats()["market_requests_avoided_by_grpc"] == 1


def test_untrusted_stale_wrong_mint_and_nonfinite_grpc_fail_closed():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    untrusted = _trusted_payload(view)
    untrusted["reserve_trusted_for_routing"] = False
    assert not scheduler.submit_trusted_reserve(untrusted)
    assert not scheduler.submit_trusted_reserve(
        _trusted_payload(view, source_at=NOW - 16))
    wrong = _trusted_payload(view)
    wrong["mint"] = "wrong-mint-pump"
    assert not scheduler.submit_trusted_reserve(wrong)
    nonfinite = _trusted_payload(view, price="NaN")
    assert not scheduler.submit_trusted_reserve(nonfinite)
    assert scheduler.snapshot(view.mint)["current_price"] is None


def test_bad_observation_seal_fails_closed():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    payload = _trusted_payload(view)
    payload["observation_seal_digest"] = "0" * 64
    assert not scheduler.submit_trusted_reserve(payload)


def test_lower_out_of_order_paid_result_cannot_overwrite_newer_grpc():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    assert scheduler.submit_trusted_reserve(_trusted_payload(view))
    assert not scheduler.apply_observation(_observation(
        view, source_at=NOW - 1, sequence=10, price="9", mc="900"))
    snapshot = scheduler.snapshot(view.mint)
    assert (snapshot["current_price"], snapshot["current_market_cap_usd"]) == ("1", "100")


def test_same_second_grpc_events_use_exact_slot_instruction_order():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    first = _trusted_payload(view, price="2", mc="200", slot=10)
    assert scheduler.submit_trusted_reserve(first)
    later = _trusted_payload(view, price="3", mc="300", slot=11)
    assert scheduler.submit_trusted_reserve(later)
    older = _trusted_payload(view, price="1", mc="100", slot=9)
    assert not scheduler.submit_trusted_reserve(older)
    assert scheduler.snapshot(view.mint)["current_price"] == "3"


def test_price_and_overview_freshness_are_independent():
    view = _view(1, status="ACTIVE_DIP_WATCH")
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    assert scheduler.apply_observation(_observation(view, sequence=1))
    price_only = scheduler.snapshot(view.mint)
    assert price_only["price_fresh"] and price_only["market_cap_fresh"]
    assert not price_only["liquidity_fresh"] and not price_only["all_present"]
    assert scheduler.apply_observation(_observation(
        view, field=FIELD_OVERVIEW, source_at=NOW, sequence=2))
    complete = scheduler.snapshot(view.mint)
    assert complete["all_present"]
    old_price_at = complete["price_observed_at_utc"]
    assert scheduler.apply_observation(_observation(
        view, field=FIELD_OVERVIEW, source_at=NOW + 1, sequence=3,
        mc="101", liquidity="5100"))
    assert scheduler.snapshot(view.mint, now_epoch=NOW + 1)[
        "price_observed_at_utc"] == old_price_at


def test_stale_liquidity_blocks_complete_snapshot_and_targets_overview_only():
    view = _view(1, status="ACTIVE_DIP_WATCH")
    config = MarketSchedulerConfig(
        overview_active_ttl_seconds=30, price_active_ttl_seconds=12)
    scheduler = _scheduler(config=config)
    scheduler.update_candidates([view], now_epoch=NOW)
    scheduler.apply_observation(_observation(view, source_at=NOW, sequence=1))
    scheduler.apply_observation(_observation(
        view, field=FIELD_OVERVIEW, source_at=NOW - 31, sequence=2))
    snapshot = scheduler.snapshot(view.mint, now_epoch=NOW)
    assert not snapshot["liquidity_fresh"] and not snapshot["all_present"]
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert [job.field_group for job in jobs] == [FIELD_OVERVIEW]


def test_complete_fresh_candidate_makes_no_unnecessary_call():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    _apply_fresh(scheduler, view)
    assert scheduler.plan(now_epoch=NOW, enqueue=False) == []


def test_duplicate_price_and_overview_requests_coalesce():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    first = scheduler.plan(now_epoch=NOW, enqueue=True)
    second = scheduler.plan(now_epoch=NOW, enqueue=True)
    assert len(first) == 2 and second == []
    assert scheduler.stats()["market_requests_coalesced"] == 2
    scheduler.stop(timeout_seconds=0.1)


def test_batch_size_splits_deterministically_and_preserves_bindings():
    config = MarketSchedulerConfig(paid_batch_size=3)
    scheduler = _scheduler(config=config, batch_fetch=lambda mints: {})
    views = [_view(index) for index in range(7)]
    scheduler.update_candidates(list(reversed(views)), now_epoch=NOW)
    batches = [job for job in scheduler.plan(now_epoch=NOW, enqueue=False)
               if job.field_group == FIELD_PRICE_MC]
    assert [len(job.mints) for job in batches] == [3, 3, 1]
    assert [mint for job in batches for mint in job.mints] == sorted(
        view.mint for view in views)


def test_partial_batch_applies_valid_mint_only_and_leaves_missing_pending():
    config = MarketSchedulerConfig(paid_batch_size=10)
    scheduler = _scheduler(config=config, batch_fetch=lambda mints: {})
    views = [_view(0), _view(1)]
    scheduler.update_candidates(views, now_epoch=NOW)
    job = next(job for job in scheduler.plan(now_epoch=NOW, enqueue=False)
               if job.field_group == FIELD_PRICE_MC)
    scheduler._consume_result(job, {
        views[0].mint: {"mint": views[0].mint, "current_price": "1",
                        "current_market_cap_usd": "100",
                        "provider_timestamp_utc": _iso(NOW)},
    }, None)
    assert scheduler.snapshot(views[0].mint)["current_price"] == "1"
    assert scheduler.snapshot(views[1].mint)["current_price"] is None
    assert scheduler.stats()["market_batch_partial"] == 1
    assert MARKET_BATCH_PARTIAL in scheduler.stats()["market_scheduler_degraded_reasons"]


def test_wrong_mint_batch_result_does_not_cross_apply():
    config = MarketSchedulerConfig(paid_batch_size=10)
    scheduler = _scheduler(config=config, batch_fetch=lambda mints: {})
    views = [_view(0), _view(1)]
    scheduler.update_candidates(views, now_epoch=NOW)
    job = next(job for job in scheduler.plan(now_epoch=NOW, enqueue=False)
               if job.field_group == FIELD_PRICE_MC and len(job.mints) == 2)
    scheduler._consume_result(job, {
        views[0].mint: {"mint": "wrong-mint-pump", "current_price": "9",
                        "current_market_cap_usd": "900"},
        views[1].mint: {"mint": views[1].mint, "current_price": "1",
                        "current_market_cap_usd": "100"},
    }, None)
    assert scheduler.snapshot(views[0].mint)["current_price"] is None
    assert scheduler.snapshot(views[1].mint)["current_price"] == "1"
    assert scheduler.stats()["market_wrong_mint_rejected"] == 1


def test_expired_terminal_quarantined_and_generation_mismatch_reject_results():
    active = _view(0)
    scheduler = _scheduler()
    scheduler.update_candidates([active], now_epoch=NOW)
    bad_generation = MarketObservation(**{
        **_observation(active).__dict__, "generation": active.generation + 1})
    assert not scheduler.apply_observation(bad_generation)
    scheduler.update_candidates([], now_epoch=NOW)
    assert not scheduler.apply_observation(_observation(active, sequence=2))

    terminal = _view(1, status="SENT_OK_COMMITTED")
    quarantined = _view(2, quarantined=True)
    history = _view(3, terminal_history=True)
    scheduler.update_candidates([terminal, quarantined, history], now_epoch=NOW)
    assert not scheduler.apply_observation(_observation(terminal, sequence=3))
    assert not scheduler.apply_observation(_observation(quarantined, sequence=4))
    assert not scheduler.apply_observation(_observation(history, sequence=5))


def test_due_recovery_is_p0_and_not_due_recovery_has_zero_jobs():
    due = _view(0, status="MARKET_RECOVERY_BACKOFF", next_recovery=NOW - 1)
    not_due = _view(1, status="MARKET_RECOVERY_BACKOFF", next_recovery=NOW + 1)
    scheduler = _scheduler()
    scheduler.update_candidates([not_due, due], now_epoch=NOW)
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert jobs and {job.mints[0] for job in jobs} == {due.mint}
    assert {job.priority for job in jobs} == {PRIORITY_P0}


def test_not_due_normal_market_retry_also_performs_zero_provider_calls():
    waiting = _view(
        2, status="PENDING_1_20X", market_state="MARKET_INDEXING",
        next_recovery=NOW + 10)
    scheduler = _scheduler()
    scheduler.update_candidates([waiting], now_epoch=NOW)
    assert scheduler.plan(now_epoch=NOW, enqueue=False) == []


def test_recovery_market_state_is_distinct_from_activation_status_and_records_latency():
    due = _view(
        0, status="PENDING_1_20X", market_state="MARKET_RECOVERY_BACKOFF",
        next_recovery=NOW - 10)
    not_due = _view(
        1, status="ACTIVE_DIP_WATCH", market_state="MARKET_RECOVERY_BACKOFF",
        next_recovery=NOW + 1)
    scheduler = _scheduler()
    scheduler.update_candidates([not_due, due], now_epoch=NOW)
    jobs = scheduler.plan(now_epoch=NOW, enqueue=True)
    assert jobs and {mint for job in jobs for mint in job.mints} == {due.mint}
    assert scheduler.stats()["market_due_recovery_probe_latency_ms"] == 10000.0
    scheduler.stop(timeout_seconds=0.1)


def test_near_tier_and_liquidity_floor_affect_priority_not_authorization():
    tier_view = _view(0, status="ACTIVE_DIP_WATCH")
    liquidity_view = _view(1, status="PENDING_1_20X")
    scheduler = _scheduler()
    scheduler.update_candidates([tier_view, liquidity_view], now_epoch=NOW)
    scheduler.apply_observation(_observation(
        tier_view, source_at=NOW - 13, sequence=1, mc="40"))
    scheduler.apply_observation(_observation(
        tier_view, field=FIELD_OVERVIEW, source_at=NOW, sequence=2,
        mc="40", liquidity="6000"))
    scheduler.record_tier_projection(tier_view.mint, ath_market_cap_usd="100")
    scheduler.apply_observation(_observation(
        liquidity_view, source_at=NOW, sequence=3))
    scheduler.apply_observation(_observation(
        liquidity_view, field=FIELD_OVERVIEW, source_at=NOW - 91, sequence=4,
        liquidity="4501"))
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert {job.mints[0]: job.priority for job in jobs} == {
        tier_view.mint: PRIORITY_P0, liquidity_view.mint: PRIORITY_P0}
    assert scheduler.snapshot(liquidity_view.mint)["all_present"] is False


def test_heartbeat_and_schedule_slo_breaches_are_explicit_without_terminalizing():
    view = _view(0, status="ACTIVE_DIP_WATCH")
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    scheduler.note_heartbeat(due_epoch=NOW, actual_epoch=NOW + 4.9)
    assert not scheduler.stats()["market_scheduler_slo_breached"]
    scheduler.note_heartbeat(due_epoch=NOW, actual_epoch=NOW + 5.1)
    assert scheduler.stats()["market_scheduler_slo_breached"]
    assert scheduler.snapshot(view.mint)["market_state"] == "MARKET_INCOMPLETE"


def test_default_latency_objectives_and_sync_grpc_decision_path_are_bounded():
    config = MarketSchedulerConfig()
    assert config.grpc_watch_apply_slo_seconds == 2.0
    assert config.grpc_decision_slo_seconds == 5.0
    assert config.activated_overview_schedule_slo_seconds == 15.0
    assert config.recovery_schedule_slo_seconds == 15.0
    assert config.pending_price_max_age_seconds == 30.0
    assert config.background_starvation_seconds == 120.0
    assert config.heartbeat_jitter_slo_seconds == 5.0

    evaluated = []
    view = _view(0, status="ACTIVE_DIP_WATCH")
    scheduler = _scheduler(callback=lambda observation, snapshot: evaluated.append(
        (observation.source, snapshot["current_market_cap_usd"])))
    scheduler.update_candidates([view], now_epoch=NOW)
    assert scheduler.submit_trusted_reserve(_trusted_payload(view))
    latency_ms = scheduler.stats()["market_grpc_to_watch_latency_ms"]
    assert latency_ms <= config.grpc_watch_apply_slo_seconds * 1000
    assert evaluated == [(SOURCE_GRPC, "100")]
    assert latency_ms <= config.grpc_decision_slo_seconds * 1000


def test_closed_tier_projection_uses_exact_existing_bands_and_gaps():
    assert project_closed_tier(ath_market_cap_usd="100", current_market_cap_usd="50")[0] == "Tier 1"
    assert project_closed_tier(ath_market_cap_usd="100", current_market_cap_usd="39")[0] is None
    assert project_closed_tier(ath_market_cap_usd="100", current_market_cap_usd="38")[0] == "Tier 2"
    assert project_closed_tier(ath_market_cap_usd="100", current_market_cap_usd="19")[0] is None
    assert project_closed_tier(ath_market_cap_usd="100", current_market_cap_usd="18")[0] == "Tier 3"
    assert project_closed_tier(ath_market_cap_usd="100", current_market_cap_usd="4")[0] is None


def test_trusted_grpc_reserve_crossing_activates_but_only_later_tick_projects_tier():
    entry = activation_fixture._entry()
    crossing_ath = activation_fixture._central_evidence(
        activation_fixture.ACTIVATING_HIGH,
        source=SOURCE_PUMPSWAP_EVENT,
        status=STATUS_CONFIRMED,
        event_at=activation_fixture.ACTED_AT,
        ingested_at=activation_fixture.ACTED_AT,
    )
    reserve = {"reserve_trusted_for_routing": True, "base_supply": "1000000000"}
    crossing = entry.observe_market(
        current_market_cap_usd=activation_fixture.ACTIVATING_HIGH,
        current_price=activation_fixture._price_for_market_cap(
            activation_fixture.ACTIVATING_HIGH),
        current_supply="1000000000",
        provider_timestamp_utc=activation_fixture.ACTED_AT,
        observed_at_utc=activation_fixture.ACTED_AT,
        observation_source="CHAINSTACK_GRPC_EVENT",
        max_age_seconds=15,
        central_ath=crossing_ath,
        pumpswap_reserve=reserve,
    )
    assert crossing["just_activated"] is True
    assert crossing["eligible"] is False
    assert crossing["reason"] == "ACTIVATION_CROSSING_TICK_BLOCKED"

    later_ath = activation_fixture._central_evidence(
        activation_fixture.LATEST_ATH,
        event_at=activation_fixture.LATEST_ATH_AT,
        ingested_at=activation_fixture.LATEST_INGESTED_AT,
    )
    later = entry.observe_market(
        current_market_cap_usd=activation_fixture.TIER1_MC,
        current_price=activation_fixture._price_for_market_cap(
            activation_fixture.TIER1_MC),
        current_supply="1000000000",
        provider_timestamp_utc=activation_fixture.TIER1_AT,
        observed_at_utc=activation_fixture.TIER1_AT,
        observation_source="CHAINSTACK_GRPC_EVENT",
        max_age_seconds=15,
        central_ath=later_ath,
        pumpswap_reserve=reserve,
    )
    assert later["just_activated"] is False
    assert later["eligible"] is True
    assert project_closed_tier(
        ath_market_cap_usd=activation_fixture.LATEST_ATH,
        current_market_cap_usd=activation_fixture.TIER1_MC)[0] == "Tier 1"


def test_capacity_refuses_to_claim_unachievable_no_batch_slo():
    scheduler = _scheduler()
    result = scheduler.capacity_assessment(
        active_candidates=128, grpc_price_candidates=0,
        overview_due_candidates=128)
    assert result["market_latency_slo_unachievable"]
    assert result["planned_provider_requests"] == 256
    assert result["provider_pacing_floor_seconds"] == 267.75
    assert LATENCY_SLO_UNACHIEVABLE in scheduler.stats()[
        "market_scheduler_degraded_reasons"]


def test_queue_is_bounded_and_overload_is_explicit():
    config = MarketSchedulerConfig(max_queue_size=2)
    scheduler = _scheduler(config=config)
    scheduler.update_candidates([_view(0), _view(1)], now_epoch=NOW)
    accepted = scheduler.plan(now_epoch=NOW, enqueue=True)
    assert len(accepted) == 2
    stats = scheduler.stats()
    assert stats["market_scheduler_queue_depth"] == 2
    assert MARKET_SCHEDULER_BACKLOG_HIGH in stats["market_scheduler_degraded_reasons"]
    scheduler.stop(timeout_seconds=0.1)


def test_worker_and_inflight_counts_are_bounded_and_stop_prevents_new_calls():
    began = threading.Event()
    release = threading.Event()
    calls = []

    def slow_price(mint):
        calls.append(mint)
        began.set()
        release.wait(1.0)
        return {"mint": mint, "current_price": "1",
                "current_market_cap_usd": "100",
                "provider_timestamp_utc": _iso(time.time())}

    config = MarketSchedulerConfig(worker_count=2, max_inflight=1, max_queue_size=8)
    scheduler = MarketScheduler(
        price_fetch_fn=slow_price,
        overview_fetch_fn=lambda mint: None,
        config=config,
        now_fn=time.time,
        monotonic_fn=time.monotonic,
    )
    now = time.time()
    view = CandidateScheduleView(
        mint="bounded-pump", candidate_id="bounded", generation=1,
        status="ACTIVE_DIP_WATCH", seeded_at_epoch=now)
    scheduler.update_candidates([view], now_epoch=now)
    scheduler.plan(now_epoch=now)
    scheduler.start()
    assert began.wait(1.0)
    stats = scheduler.stats()
    assert stats["market_scheduler_worker_count"] == 2
    assert stats["market_scheduler_inflight"] <= 1
    scheduler.request_stop()
    release.set()
    assert scheduler.stop(timeout_seconds=2.0)
    before = len(calls)
    assert scheduler.plan(now_epoch=time.time()) == []
    time.sleep(0.02)
    assert len(calls) == before == 1


def test_two_field_groups_apply_without_lost_update():
    view = _view(1)
    scheduler = _scheduler()
    scheduler.update_candidates([view], now_epoch=NOW)
    scheduler.apply_observation(_observation(
        view, field=FIELD_OVERVIEW, sequence=2, mc="100", liquidity="5000"))
    scheduler.apply_observation(_observation(
        view, field=FIELD_PRICE_MC, sequence=1, price="1", mc="100"))
    snapshot = scheduler.snapshot(view.mint)
    assert (snapshot["current_price"], snapshot["current_market_cap_usd"],
            snapshot["liquidity_usd"]) == ("1", "100", "5000")


def test_quote_price_request_is_shared_and_applied_once():
    applied = []
    scheduler = _scheduler(
        price_fetch=lambda mint: {"mint": mint, "current_price": "150",
                                  "provider_timestamp_utc": _iso(NOW)},
        overview_fetch=lambda mint: None,
        quote_apply=lambda mint, price, observed: applied.append((mint, price, observed)))
    assert scheduler.request_quote_price("quote-mint")
    assert not scheduler.request_quote_price("quote-mint")
    scheduler.start()
    deadline = time.time() + 1.0
    while not applied and time.time() < deadline:
        time.sleep(0.01)
    assert scheduler.stop(timeout_seconds=1.0)
    assert applied == [("quote-mint", "150", _iso(NOW))]


def test_mixed_128_fixture_has_priority_freshness_and_bounded_78_call_plan():
    views = []
    for index in range(128):
        if index < 16:
            status, near = "ACTIVE_DIP_WATCH", False
        elif index < 32:
            status, near = "ACTIVATED_WAITING_FOR_FRESH_MARKET", False
        elif index < 64:
            status, near = "PENDING_1_20X", True
        elif index < 96:
            status, near = "PENDING_1_20X", False
        elif index < 112:
            status, near = "MARKET_RECOVERY_BACKOFF", False
        else:
            status, near = "PENDING_BASELINE", False
        next_recovery = None
        if status == "MARKET_RECOVERY_BACKOFF":
            next_recovery = NOW - 1 if index < 104 else NOW + 60
        views.append(_view(
            index, status=status, near=near, next_recovery=next_recovery,
            quarantined=(index == 127)))
    scheduler = _scheduler()
    scheduler.update_candidates(views, now_epoch=NOW)
    sequence = 1
    # 64 trusted gRPC price/MC observations; no paid price calls for them.
    for view in views[:64]:
        assert scheduler.apply_observation(_observation(
            view, source=SOURCE_GRPC, sequence=sequence))
        sequence += 1
    # Another 32 have a fresh paid fast-plane result.
    for view in views[64:96]:
        assert scheduler.apply_observation(_observation(view, sequence=sequence))
        sequence += 1
    # Only the first 64 have fresh overview/liquidity enrichment.
    for view in views[:64]:
        assert scheduler.apply_observation(_observation(
            view, field=FIELD_OVERVIEW, sequence=sequence))
        sequence += 1
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert len(jobs) == 78
    assert len([job for job in jobs if job.field_group == FIELD_PRICE_MC]) == 23
    assert len([job for job in jobs if job.field_group == FIELD_OVERVIEW]) == 55
    assert jobs[0].priority == PRIORITY_P0
    assert not any("mint-127" in job.mints[0] for job in jobs)
    assert not any(view.mint in {mint for job in jobs for mint in job.mints}
                   for view in views[104:112])
    assert len(jobs) < 256
    stats = scheduler.stats()
    assert stats["market_latency_slo_unachievable"] is True
    assert stats["market_latency_slo_limiting_resource"] == (
        "PAID_PRIMARY_GLOBAL_REQUEST_SPACING")
    assert stats["market_provider_pacing_floor_seconds"] == 80.85


def test_all_128_trusted_grpc_observations_require_zero_paid_price_calls():
    views = [_view(index, status="ACTIVE_DIP_WATCH") for index in range(128)]
    scheduler = _scheduler()
    scheduler.update_candidates(views, now_epoch=NOW)
    for index, view in enumerate(views, start=1):
        assert scheduler.submit_trusted_reserve(
            _trusted_payload(view, slot=index))
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert not [job for job in jobs if job.field_group == FIELD_PRICE_MC]
    assert scheduler.stats()["market_requests_avoided_by_grpc"] == 128


def test_six_mint_shape_applies_grpc_without_a_serial_price_sweep():
    views = [_view(index, status="ACTIVE_DIP_WATCH") for index in range(6)]
    scheduler = _scheduler()
    scheduler.update_candidates(views, now_epoch=NOW)
    for view in views:
        assert scheduler.submit_trusted_reserve(_trusted_payload(view))
    jobs = scheduler.plan(now_epoch=NOW, enqueue=False)
    assert len([job for job in jobs if job.field_group == FIELD_PRICE_MC]) == 0
    assert len([job for job in jobs if job.field_group == FIELD_OVERVIEW]) == 6


def test_offline_phx1_helius_vs_yellowstone_lookup_comparison_is_bounded():
    result = offline_grpc_vs_helius_comparison_fixture()
    assert result["phx1_additional_transaction_rpc_lookups"] == 1
    assert result["phx2_additional_price_mc_lookups"] == 0
    assert result["phx2_paid_enrichment_lookups_before_send"] == 1
    assert not result["empirical_latency_claimed"]
