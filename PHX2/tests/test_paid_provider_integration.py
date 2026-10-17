"""Offline proofs for the paid-provider discovery and enrichment boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import threading
import time
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer import paid_grpc_source as paid_grpc_source_module
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.free_tier_producer.market_scheduler import (
    MarketScheduler,
    MarketSchedulerConfig,
    ScheduledMarketSidecar,
)
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.paid_market_readiness import (
    GRACE_EXHAUSTION_ATTEMPTS,
    MARKET_INCOMPLETE,
    MARKET_INDEXING,
    MARKET_INVALID,
    MARKET_READY,
    MARKET_RECOVERY_BACKOFF,
    MARKET_STALE,
    MARKET_UNAVAILABLE,
    RECOVERY_BACKOFF_NOT_DUE,
    PaidMarketReadinessConfig,
    PaidMarketReadinessTracker,
)
from PHX2.free_tier_producer.paid_grpc_source import (
    PaidCreatePoolYellowstoneSource,
    _base58_decode,
    extract_create_pool_quartet,
)
from PHX2.free_tier_producer.paid_provider import (
    PROVIDER_MODE_PAID_PRIMARY,
    STREAM_STATUS_AUTH_FAILED,
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
    build_live_source_factory,
    event_to_candidate,
    normalize_provider_mode,
)
from PHX2.free_tier_producer.free_tier_credit_budget import (
    BUDGET_STOP_SEND_CAP,
    BUDGET_STOP_CANDIDATES,
    FreeTierCreditBudget,
    FreeTierCreditBudgetCaps,
    FreeTierBudgetExhausted,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeHttpResult
from PHX2.stage29.stage29_2_birdeye_readiness import Stage29_2BirdeyeEndpointSecret
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
OTHER_MINT = "k85BpCNVEcLGCzwgKTi3ho3fRjg5Do8Xpo9VrcMpump"
POOL = "D" * 44
QUOTE = "So11111111111111111111111111111111111111112"
PROGRAM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
CREATE_POOL_DISCRIMINATOR = bytes((233, 146, 209, 142, 207, 104, 64, 188))


def _eligible_activation_gate(_candidate, _context):
    proof = {
        "migration_market_cap_usd": "100",
        "migration_market_cap_source": "GRPC_EVENT",
        "migration_baseline_status": "CAPTURED",
        "activation_multiplier": "1.20",
        "activation_target_market_cap_usd": "120.00",
        "activation_state": "ACTIVE_DIP_WATCH",
        "activated_at_utc": "2026-07-15T12:00:00Z",
        "activation_observation_source": "PAID_MARKET_PRIMARY",
        "activation_current_market_cap_usd": "120.00",
        "activation_observation_fresh": True,
        "activation_proven": True,
    }
    return {"activation": proof, "eligible": True, "just_activated": False,
            "events": [], "reason": "ACTIVE_DIP_WATCH"}


def _event(*, mint=MINT, base_mint=MINT, event_id="evt-1"):
    return SimpleNamespace(
        base_mint=base_mint,
        mint=mint,
        pool_account=POOL,
        pool_program_id=PROGRAM,
        quote_mint=QUOTE,
        event_id=event_id,
        provider_event_id="sig-" + event_id,
        observed_at_utc="2026-07-15T12:00:00Z",
        raw_event_hash="hash-" + event_id,
    )


def _result(body=None, *, refusal=BIRDEYE_REFUSAL_REASON_NONE, status=200):
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=refusal,
        http_status_code=status,
        body=body,
        fetched_at_utc="1970-01-01T00:16:40Z",
    )


def _endpoint_secret():
    return Stage29_2BirdeyeEndpointSecret(
        _api_key="offline-test-key-12345678",
        _base_url="https://offline.test.invalid",
    )


def _create_pool_update(*, data=CREATE_POOL_DISCRIMINATOR, mint_a=MINT, mint_b=QUOTE,
                        pool=POOL):
    key_text = [pool, "1" * 32, "2" * 32, mint_a, mint_b, PROGRAM]
    keys = [_base58_decode(value) for value in key_text]
    instruction = SimpleNamespace(
        program_id_index=5, accounts=bytes((0, 1, 2, 3, 4)), data=data)
    message = SimpleNamespace(account_keys=keys, instructions=[instruction])
    transaction = SimpleNamespace(message=message)
    meta = SimpleNamespace(
        log_messages=["Program log: Instruction: CreatePool"],
        loaded_writable_addresses=[], loaded_readonly_addresses=[], inner_instructions=[])
    info = SimpleNamespace(transaction=transaction, meta=meta)
    return SimpleNamespace(transaction=SimpleNamespace(transaction=info))


class _SequenceTransport:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


def test_provider_modes_are_explicit_closed_set():
    assert normalize_provider_mode("paid-primary") == PROVIDER_MODE_PAID_PRIMARY
    try:
        normalize_provider_mode("paid_and_send")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown provider mode must refuse")


def test_paid_queue_handoff_uses_watch_tick_without_changing_free_tier_cadence():
    bounds = producer_session.ProductionBounds(
        recheck_interval_seconds=45.0,
        reseed_interval_seconds=240.0,
    )
    paid = producer_session._bounds_with_provider_handoff_cadence(
        bounds, PROVIDER_MODE_PAID_PRIMARY)
    free = producer_session._bounds_with_provider_handoff_cadence(
        bounds, producer_session.PROVIDER_MODE_FREE_TIER)

    assert paid.reseed_interval_seconds == 45.0
    assert paid.recheck_interval_seconds == 45.0
    assert free is bounds
    assert free.reseed_interval_seconds == 240.0


def test_accepted_paid_candidate_drains_into_existing_watchlist_market_loop():
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: pytest.fail("queue drain must not create another provider"),
        dedupe=ProviderCandidateDedupe(),
    )
    watchlist = producer_session.Watchlist(max_size=4)
    clock = {"value": 0.0, "queued": False}
    engine_inputs = []
    sidecar_calls = []

    class Sidecar:
        def stats(self):
            return {"market_attempts_total": 1}

    def sleep_fn(seconds):
        clock["value"] += float(seconds)
        if not clock["queued"]:
            owner._handle_event(_event(event_id="handoff"))
            clock["queued"] = True

    def run_engine(candidates, **_kwargs):
        engine_inputs.extend(candidates)
        return {
            "outcome": "ZERO_SEND",
            "per_candidate": [{
                "token_mint": candidates[0]["token_mint"],
                "reason": "NO_SEND_MARKET_UNAVAILABLE",
                "market_state": MARKET_UNAVAILABLE,
                "market_reason_code": "OFFLINE_HANDOFF_PROOF",
            }],
        }

    bounds = producer_session._bounds_with_provider_handoff_cadence(
        producer_session.ProductionBounds(
            recheck_interval_seconds=45.0,
            reseed_interval_seconds=240.0,
            max_total_ticks=2,
            max_candidate_age_seconds=3600,
            max_rechecks_per_candidate=10,
        ),
        PROVIDER_MODE_PAID_PRIMARY,
    )
    result = producer_session.run_production_live_watch(
        watchlist=watchlist,
        axiom_source=producer_session.axiomgate.NullAxiomFeeSource(),
        axiom_config=producer_session._strict_axiom_config(),
        sidecar_factory=lambda tick: sidecar_calls.append(tick) or Sidecar(),
        ath_transport=object(),
        ath_endpoint_secret=object(),
        ledger=object(),
        guard_factory=object,
        authorization=object(),
        now_dt_fn=lambda: datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
        now_iso_fn=lambda: "2026-07-15T12:00:00Z",
        now_seconds=lambda: Decimal(0),
        sleep_fn=sleep_fn,
        monotonic_fn=lambda: clock["value"],
        bounds=bounds,
        run_cap1_candidates_fn=run_engine,
        ledger_line_count_fn=lambda: 0,
        discovery_fn=lambda: owner.drain(max_candidates=10),
    )

    entry = watchlist.get(MINT)
    assert result["stop_reason"] == "TICK_BUDGET"
    assert result["reseeds"] == 2
    assert owner.snapshot()["queue_depth"] == 0
    assert entry is not None and entry.status == "PENDING_BASELINE"
    assert entry.recheck_count == 1
    assert [candidate["token_mint"] for candidate in engine_inputs] == [MINT]
    assert sidecar_calls == [2]
    assert result["market_calls"] == 1


def test_provider_job_does_not_block_handoff_heartbeat_or_checkpoint(tmp_path):
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: pytest.fail("offline queue drain must not open a source"),
        dedupe=ProviderCandidateDedupe(),
    )
    watchlist = producer_session.Watchlist(max_size=4)
    began = threading.Event()
    release = threading.Event()
    provider_calls = []

    def blocked_provider(mint):
        provider_calls.append(mint)
        began.set()
        release.wait(2.0)
        return None

    scheduler = MarketScheduler(
        price_fetch_fn=blocked_provider,
        overview_fetch_fn=blocked_provider,
        config=MarketSchedulerConfig(
            worker_count=1, max_inflight=1, max_queue_size=8,
            provider_min_interval_seconds=0),
        now_fn=time.time,
        monotonic_fn=time.monotonic,
    )
    scheduler.start()
    clock = {"value": 0.0, "queued": False}
    engine_inputs = []
    heartbeat_while_blocked = []
    checkpoint_while_blocked = []
    checkpoint = tmp_path / "watch_state.jsonl"

    def sleep_fn(seconds):
        clock["value"] += float(seconds)
        if not clock["queued"]:
            owner._handle_event(_event(event_id="nonblocking-handoff"))
            clock["queued"] = True

    def run_engine(candidates, **_kwargs):
        engine_inputs.extend(candidates)
        return {
            "outcome": "ZERO_SEND",
            "per_candidate": [{
                "token_mint": candidates[0]["token_mint"],
                "reason": "NO_SEND_MARKET_INCOMPLETE",
                "market_state": MARKET_INCOMPLETE,
                "market_reason_code": "FAKE_PROVIDER_STILL_IN_FLIGHT",
            }],
        }

    def on_heartbeat(_record):
        if began.wait(timeout=0.5):
            heartbeat_while_blocked.append(not release.is_set())
            checkpoint_while_blocked.append(checkpoint.is_file())

    bounds = producer_session._bounds_with_provider_handoff_cadence(
        producer_session.ProductionBounds(
            recheck_interval_seconds=45.0,
            reseed_interval_seconds=240.0,
            max_total_ticks=2,
            max_candidate_age_seconds=3600,
            max_rechecks_per_candidate=10,
        ),
        PROVIDER_MODE_PAID_PRIMARY,
    )
    try:
        result = producer_session.run_production_live_watch(
            watchlist=watchlist,
            axiom_source=producer_session.axiomgate.NullAxiomFeeSource(),
            axiom_config=producer_session._strict_axiom_config(),
            sidecar_factory=lambda _tick: ScheduledMarketSidecar(scheduler),
            ath_transport=object(),
            ath_endpoint_secret=object(),
            ledger=object(),
            guard_factory=object,
            authorization=object(),
            now_dt_fn=lambda: datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
            now_iso_fn=lambda: "2026-07-15T12:00:00Z",
            now_seconds=lambda: Decimal(0),
            sleep_fn=sleep_fn,
            monotonic_fn=lambda: clock["value"],
            bounds=bounds,
            run_cap1_candidates_fn=run_engine,
            ledger_line_count_fn=lambda: 0,
            discovery_fn=lambda: owner.drain(max_candidates=10),
            watch_state_path=str(checkpoint),
            on_heartbeat=on_heartbeat,
            market_scheduler=scheduler,
        )
    finally:
        release.set()
        assert scheduler.stop(timeout_seconds=2.0)

    assert result["stop_reason"] == "TICK_BUDGET"
    assert began.is_set() and provider_calls
    assert [candidate["token_mint"] for candidate in engine_inputs] == [MINT]
    assert owner.snapshot()["queue_depth"] == 0
    assert any(heartbeat_while_blocked)
    assert any(checkpoint_while_blocked)


def test_event_projection_uses_actual_base_mint_not_pool_program_or_quote():
    candidate = event_to_candidate(_event())
    assert candidate["token_mint"] == MINT
    assert candidate["token_mint"] not in (POOL, PROGRAM, QUOTE)
    assert event_to_candidate(_event(mint=POOL, base_mint=MINT)) is None
    assert event_to_candidate(_event(mint=POOL, base_mint=POOL)) is None


def test_grpc_create_pool_extraction_is_discriminator_bound():
    assert extract_create_pool_quartet(_create_pool_update()) == (POOL, MINT, QUOTE)
    assert extract_create_pool_quartet(
        _create_pool_update(data=b"ordinary-swap-data")) is None


def test_grpc_create_pool_extraction_is_quote_orientation_agnostic():
    assert extract_create_pool_quartet(
        _create_pool_update(mint_a=QUOTE, mint_b=MINT)) == (POOL, MINT, QUOTE)


def test_grpc_create_pool_never_promotes_pool_address_as_mint():
    pool_ending_pump = "E" * 40 + "pump"
    quartet = extract_create_pool_quartet(_create_pool_update(pool=pool_ending_pump))
    assert quartet == (pool_ending_pump, MINT, QUOTE)
    assert quartet[1] != pool_ending_pump


def test_shared_dedupe_blocks_duplicate_signature_and_cross_source_mint():
    dedupe = ProviderCandidateDedupe()
    assert dedupe.accept(event_id="sig-1", mint=MINT)
    assert not dedupe.accept(event_id="sig-1", mint=OTHER_MINT)
    assert not dedupe.accept(event_id="fallback-ref", mint=MINT)
    snap = dedupe.snapshot()
    assert snap["duplicate_events_dropped"] == 1
    assert snap["duplicate_mints_dropped"] == 1


def test_paid_primary_candidates_consume_the_shared_run_budget():
    budget = FreeTierCreditBudget(
        FreeTierCreditBudgetCaps(max_candidates_total=2), discord_enabled=False)
    budget.record_provider_candidates(2)
    assert budget.snapshot()["candidate_count"] == 2
    assert budget.stop_reason == BUDGET_STOP_CANDIDATES


def test_single_grpc_owner_never_overlaps_and_drops_non_pump_before_queue():
    calls = {"n": 0}

    class Source:
        last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            assert max_events == 256
            calls["n"] += 1
            if calls["n"] == 1:
                yield _event()
            elif calls["n"] == 2:
                yield _event(mint="N" * 44, base_mint="N" * 44, event_id="evt-nonpump")

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0.002,
        stale_after_seconds=30,
    )
    owner.start()
    deadline = time.time() + 1.0
    while owner.snapshot()["connect_attempts"] < 3 and time.time() < deadline:
        time.sleep(0.005)
    owner.stop(timeout_seconds=1.0)
    queued = owner.drain(10)
    snap = owner.snapshot()
    assert [row["token_mint"] for row in queued] == [MINT]
    assert snap["non_pump_dropped"] == 1
    assert snap["max_active_streams"] == 1
    assert snap["active_streams"] == 0
    assert snap["stream_capacity"] == 1


def test_grpc_auth_failure_is_terminal_and_never_reconnects():
    class Source:
        last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            assert max_events == 256
            self.last_refusal_reason = "STREAM_ERROR:UNAUTHENTICATED"
            if False:
                yield None

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0,
    )
    owner.start()
    deadline = time.time() + 1.0
    while owner.snapshot()["status"] != STREAM_STATUS_AUTH_FAILED and time.time() < deadline:
        time.sleep(0.005)
    owner.stop(timeout_seconds=1.0)
    snap = owner.snapshot()
    assert snap["status"] == STREAM_STATUS_AUTH_FAILED
    assert snap["terminal_auth_failure"] is True
    assert snap["connect_attempts"] == 1
    assert snap["reconnects"] == 0
    assert snap["active_streams"] == 0
    assert snap["max_active_streams"] == 1


def test_single_grpc_owner_cancels_the_active_source_on_stop():
    entered = threading.Event()
    closed = threading.Event()

    class Source:
        last_refusal_reason = "NONE"

        def iter_events(self, *, max_events):
            assert max_events == 256
            entered.set()
            closed.wait(timeout=2.0)
            if False:
                yield None

        def close(self):
            closed.set()

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0,
    )
    owner.start()
    assert entered.wait(timeout=1.0)
    owner.stop(timeout_seconds=1.0)
    snap = owner.snapshot()
    assert closed.is_set()
    assert snap["connect_attempts"] == 1
    assert snap["reconnects"] == 0
    assert snap["active_streams"] == 0
    assert snap["max_active_streams"] == 1


def test_live_factory_removes_the_ordinary_message_scan_ceiling(monkeypatch):
    from PHX2.stage28 import chainstack_yellowstone_grpc_readiness as readiness

    runtime = SimpleNamespace()
    monkeypatch.setattr(
        readiness, "build_runtime_config_from_env", lambda **_kw: runtime)
    source = build_live_source_factory()()
    assert isinstance(source, PaidCreatePoolYellowstoneSource)
    assert source._runtime_config is runtime
    assert source._max_messages is None


def test_unbounded_live_source_can_reach_create_pool_after_more_than_64_updates(monkeypatch):
    ordinary = _create_pool_update()
    target = _create_pool_update()
    ordinary.HasField = lambda name: name == "transaction"
    target.HasField = lambda name: name == "transaction"
    response = iter([ordinary] * 64 + [target])
    cancelled = {"value": False}

    class CancellableResponse:
        def __next__(self):
            return next(response)

        def cancel(self):
            cancelled["value"] = True

    cancellable = CancellableResponse()

    class ChannelContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    class Stub:
        def Subscribe(self, *_args, **_kwargs):
            return cancellable

    runtime = SimpleNamespace(
        timeout_seconds=10,
        safe_config=SimpleNamespace(provider_id="TEST_PROVIDER"),
    )
    monkeypatch.setattr(
        paid_grpc_source_module, "_open_channel", lambda *_a, **_kw: ChannelContext())
    monkeypatch.setattr(
        paid_grpc_source_module.geyser_pb2_grpc, "GeyserStub", lambda _channel: Stub())
    monkeypatch.setattr(
        paid_grpc_source_module.geyser_pb2, "SubscribeUpdate", SimpleNamespace)
    monkeypatch.setattr(paid_grpc_source_module, "_build_metadata", lambda _cfg: ())
    monkeypatch.setattr(
        paid_grpc_source_module,
        "decode_create_pool_update",
        lambda update, **_kw: (_event() if update is target else None),
    )
    source = PaidCreatePoolYellowstoneSource(
        runtime_config=runtime, max_messages_to_scan=None)
    assert list(source.iter_events(max_events=1)) == [_event()]
    assert source.events_scanned == 65
    assert source.create_pool_yielded == 1
    assert isinstance(source.last_update_epoch, float)
    assert cancelled["value"] is True


def test_provider_health_uses_raw_subscription_updates_not_only_create_pool_events():
    entered = threading.Event()
    closed = threading.Event()

    class Source:
        last_refusal_reason = "NONE"
        last_update_epoch = time.time()
        events_scanned = 65
        transactions_scanned = 64
        create_pool_yielded = 0

        def iter_events(self, *, max_events):
            assert max_events == 256
            entered.set()
            closed.wait(timeout=2.0)
            if False:
                yield None

        def close(self):
            closed.set()

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0,
        stale_after_seconds=30,
    )
    owner.start()
    assert entered.wait(timeout=1.0)
    snap = owner.snapshot()
    assert snap["status"] == "CONNECTED"
    assert snap["source_updates_scanned"] == 65
    assert snap["source_transactions_scanned"] == 64
    assert snap["source_create_pool_yielded"] == 0
    owner.stop(timeout_seconds=1.0)
    stopped = owner.snapshot()
    assert stopped["source_updates_scanned"] == 65
    assert stopped["source_transactions_scanned"] == 64


def test_birdeye_primary_backs_off_on_429_then_recovers_and_caches():
    """429 handling, 2026-07-31 restart-state remediation.

    PREVIOUS behaviour (asserted here until 2026-07-31): a 429 was retried
    immediately inside the same ``get``. That is exactly what escalates a
    transient burst -- and once seven of them crossed ``max_429_total=5`` the
    whole producer was stopped and a restart destroyed the tracked candidate
    state. A 429 now STOPS retrying and opens a bounded, jittered,
    provider-scoped backoff window: further requests are refused without being
    dialled, and the first served response closes the window.
    """

    clock = {"t": 0.0}
    inner = _SequenceTransport([
        _result(None, refusal=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, status=429),
        _result({"success": True, "data": {"value": "2.5", "updateUnixTime": 1000}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=30, max_attempts=2, backoff_seconds=(0,), now_fn=lambda: 1000,
        monotonic_fn=lambda: clock["t"],
    )
    kwargs = dict(endpoint_secret=object(), path="/defi/price",
                  query_params={"address": MINT}, timeout_seconds=1)

    throttled = transport.get(**kwargs)
    assert throttled.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE
    assert len(inner.calls) == 1                 # the retry was NOT burned
    assert transport.rate_limit_backoff.should_skip() is True

    # Inside the window: refused without touching the provider, and reported as
    # a throttle rather than a generic failure.
    suppressed = transport.get(**kwargs)
    assert suppressed.http_status_code == 429
    assert len(inner.calls) == 1
    assert transport.stats()["rate_limit_backoff_skipped"] == 1

    # Window elapses -> one probe -> success clears the backoff and caches.
    clock["t"] += transport.rate_limit_backoff.backoff_ceiling_seconds + 1.0
    recovered = transport.get(**kwargs)
    cached = transport.get(**kwargs)
    assert recovered.refusal_reason == cached.refusal_reason \
        == BIRDEYE_REFUSAL_REASON_NONE
    assert len(inner.calls) == 2

    stats = transport.stats()
    assert stats["http_429"] == 1
    assert stats["cache_hits"] == 1
    assert stats["rate_limit_status"] == "PROVIDER_RATE_LIMIT_OK"
    assert stats["provider_backoff"]["recoveries_total"] == 1
    # PHX2-E2E-006: request_concurrency now reports the CONFIGURED bounded
    # overlap (default 4); a single-threaded caller still observes at most
    # one in-flight request.
    assert stats["max_inflight"] == 1 and stats["request_concurrency"] == 4


def test_birdeye_stale_price_fails_closed():
    inner = _SequenceTransport([
        _result({"success": True, "data": {"value": "2.5", "updateUnixTime": 900}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        max_attempts=1, max_data_age_seconds=10, now_fn=lambda: 1000,
    )
    result = transport.get(
        endpoint_secret=object(), path="/defi/price",
        query_params={"address": MINT}, timeout_seconds=1)
    assert result.refusal_reason == BIRDEYE_REFUSAL_REASON_HTTP_FAILED
    assert transport.stats()["stale_refusals"] == 1


def test_birdeye_total_call_cap_refuses_before_overshoot():
    inner = _SequenceTransport([
        _result(None, refusal=BIRDEYE_REFUSAL_REASON_HTTP_FAILED, status=0),
        _result({"success": True, "data": {"value": "2.5", "updateUnixTime": 1000}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        max_attempts=3, max_calls_total=1, backoff_seconds=(0,), now_fn=lambda: 1000,
    )
    result = transport.get(endpoint_secret=object(), path="/defi/price",
                           query_params={"address": MINT}, timeout_seconds=1)
    assert result.refusal_reason == BIRDEYE_REFUSAL_REASON_HTTP_FAILED
    assert len(inner.calls) == 1
    assert transport.stats()["capped"] == 1


def test_birdeye_ath_is_monotonic_and_keeps_observation_provenance():
    inner = _SequenceTransport([
        _result({"success": True, "data": {"value": "10", "updateUnixTime": 1000}}),
        _result({"success": True, "data": {"value": "9", "updateUnixTime": 1001}}),
        _result({"success": True, "data": {"items": [
            {"h": "12", "unixTime": 1002}, {"h": "11", "unixTime": 1003}
        ]}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, ohlcv_cache_ttl_seconds=0, max_attempts=1,
        max_data_age_seconds=30, now_fn=lambda: 1003,
    )
    transport.get(endpoint_secret=object(), path="/defi/price",
                  query_params={"address": MINT, "sample": "1"}, timeout_seconds=1)
    transport.get(endpoint_secret=object(), path="/defi/price",
                  query_params={"address": MINT, "sample": "2"}, timeout_seconds=1)
    transport.get(endpoint_secret=object(), path="/defi/ohlcv",
                  query_params={"address": MINT, "type": "1m", "time_from": "900",
                                "time_to": "1003"}, timeout_seconds=1)
    ath = transport.ath_snapshot(MINT)
    assert ath["ath_price_usd"] == "12"
    assert ath["observed_at_utc"] == "1970-01-01T00:16:42Z"
    assert ath["provider"] == "PAID_MARKET_PRIMARY"
    # HTTP 200 plus a partial timestamp range is not historical confirmation.
    assert ath["observation_type"] == "ATH_PAID_OHLCV_INCOMPLETE"
    assert ath["discord_eligible"] is False


def test_birdeye_simple_market_carries_provider_and_ath_provenance():
    inner = _SequenceTransport([
        _result({"success": True, "data": {"value": "4.25", "updateUnixTime": 1000}}),
        _result({"success": True, "data": {"mc": "50000", "liquidity": "9000"}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        max_attempts=1, now_fn=lambda: 1000,
    )
    market = transport.fetch_simple_market(MINT, timeout_seconds=1)
    assert market["current_price"] == "4.25"
    assert market["current_market_cap_usd"] == "50000"
    assert market["liquidity_usd"] == "9000"
    assert market["market_provider"] == "PAID_MARKET_PRIMARY"
    assert market["ath_price_usd"] == "4.25"
    assert market["ath_observation_type"] == "ATH_PROVISIONAL_LIVE_OBSERVED"
    assert market["ath_discord_eligible"] is False


def test_birdeye_scheduler_planes_use_only_their_documented_endpoint_shapes():
    inner = _SequenceTransport([
        _result({"success": True, "data": {
            "address": MINT, "value": "4.25", "marketCap": "50000",
            "updateUnixTime": 1000,
        }}),
        _result({"success": True, "data": {
            "address": MINT, "mc": "50010", "liquidity": "9000",
            "updateUnixTime": 1001,
        }}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, max_attempts=1, now_fn=lambda: 1001,
    )
    price = transport.fetch_price_plane(MINT, timeout_seconds=1)
    overview = transport.fetch_overview_plane(MINT, timeout_seconds=1)
    assert price["current_price"] == "4.25"
    assert price["current_market_cap_usd"] == "50000"
    assert "liquidity_usd" not in price
    assert overview["current_market_cap_usd"] == "50010"
    assert overview["liquidity_usd"] == "9000"
    assert "current_price" not in overview
    assert [call["path"] for call in inner.calls] == [
        "/defi/price", "/defi/token_overview"]
    assert transport.stats()["price_batch_supported"] is False
    assert transport.stats()["price_batch_size"] == 0


def test_birdeye_scheduler_planes_reject_cross_mint_responses():
    inner = _SequenceTransport([
        _result({"success": True, "data": {
            "address": OTHER_MINT, "value": "4.25", "updateUnixTime": 1000,
        }}),
        _result({"success": True, "data": {
            "address": OTHER_MINT, "mc": "50010", "liquidity": "9000",
        }}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, max_attempts=1, now_fn=lambda: 1000,
    )
    assert transport.fetch_price_plane(MINT, timeout_seconds=1) == {
        "mint": MINT, "_market_failure_reason": "PROVIDER_WRONG_MINT"}
    assert transport.fetch_overview_plane(MINT, timeout_seconds=1) == {
        "mint": MINT, "_market_failure_reason": "PROVIDER_WRONG_MINT"}


@pytest.mark.parametrize(("refusal", "status", "expected"), (
    (BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, 429, "PROVIDER_RATE_LIMIT"),
    (BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT, 0, "PROVIDER_TIMEOUT"),
    (BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, 503, "PROVIDER_5XX"),
    (BIRDEYE_REFUSAL_REASON_BODY_MALFORMED, 200, "PROVIDER_MALFORMED"),
    (BIRDEYE_REFUSAL_REASON_HTTP_FAILED, 0, "PROVIDER_HTTP_FAILED"),
))
def test_birdeye_scheduler_failure_classification_is_closed_and_redacted(
    refusal, status, expected,
):
    inner = _SequenceTransport([_result(None, refusal=refusal, status=status)])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        max_attempts=1, now_fn=lambda: 1000,
    )
    assert transport.fetch_price_plane(MINT, timeout_seconds=1) == {
        "mint": MINT, "_market_failure_reason": expected}


def test_birdeye_transport_bounds_concurrent_callers_to_configured_gate():
    """PHX2-E2E-006: overlap is BOUNDED, not forbidden.

    The pre-fix transport serialized every caller behind one global lock
    (the audited 133.35 s / 128-candidate floor).  The contract now is a
    bounded concurrency gate: concurrent callers overlap up to the
    configured ``max_concurrency`` and never beyond it.
    """

    class SlowInner:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def get(self, **kwargs):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.05)
            with self.lock:
                self.active -= 1
            return _result({"success": True, "data": {"value": "1", "updateUnixTime": 1000}})

    inner = SlowInner()
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, max_attempts=1, now_fn=lambda: 1000,
        max_concurrency=3,
    )
    threads = [threading.Thread(target=transport.get, kwargs={
        "endpoint_secret": object(), "path": "/defi/price",
        "query_params": {"address": MINT, "sample": str(i)}, "timeout_seconds": 1,
    }) for i in range(9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert 2 <= inner.max_active <= 3, (
        f"nine concurrent callers must overlap up to the configured gate of "
        f"3 (observed {inner.max_active})")
    assert transport.stats()["max_inflight"] <= 3
    assert transport.stats()["request_concurrency"] == 3


def _arm_args(*, ledger_path, baseline):
    return SimpleNamespace(
        provider_mode="paid_primary",
        ack_live_free_tier=True,
        i_understand_this_can_send=True,
        confirm_token=producer_session.LOCKED_CONFIRM_TOKEN,
        require_baseline=baseline,
        ledger_path=str(ledger_path),
    )


def test_paid_mode_requires_every_existing_private_arm_gate(tmp_path, monkeypatch):
    ledger = tmp_path / "paid-ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    baseline = producer_session.ledgerlib.compute_baseline(str(ledger)).as_token()
    monkeypatch.setenv(producer_session.ENV_WEBHOOK, "present-for-offline-test")
    assert producer_session.verify_discord_arm(
        _arm_args(ledger_path=ledger, baseline=baseline)) is None

    cases = (
        ("ack_live_free_tier", False, "MISSING_ACK_FLAG"),
        ("i_understand_this_can_send", False, "MISSING_ACK_FLAG"),
        ("confirm_token", "wrong", "CONFIRM_TOKEN_MISMATCH"),
        ("require_baseline", None, "MISSING_REQUIRE_BASELINE"),
    )
    for field, value, expected in cases:
        args = _arm_args(ledger_path=ledger, baseline=baseline)
        setattr(args, field, value)
        assert producer_session.verify_discord_arm(args).startswith(expected)

    monkeypatch.delenv(producer_session.ENV_WEBHOOK)
    assert producer_session.verify_discord_arm(
        _arm_args(ledger_path=ledger, baseline=baseline)) == "WEBHOOK_MISSING"


def test_paid_primary_private_mode_reuses_send_path_and_never_enables_polling():
    assert producer_session._producer_mode_label(
        PROVIDER_MODE_PAID_PRIMARY, True) == "PAID_PRIMARY_PRIVATE_DISCORD"
    assert producer_session._polling_required(PROVIDER_MODE_PAID_PRIMARY, "polling") is False


def test_paid_provider_safety_auto_stops_overlap_auth_and_reconnect_storm():
    assert producer_session.paid_provider_safety_error(
        {"max_active_streams": 2}, max_reconnects=5) == "PAID_PROVIDER_STREAM_OVERLAP"
    assert producer_session.paid_provider_safety_error(
        {"status": STREAM_STATUS_AUTH_FAILED},
        max_reconnects=5) == "PAID_PROVIDER_AUTH_FAILURE"
    assert producer_session.paid_provider_safety_error(
        {"reconnects": 6}, max_reconnects=5) == "PAID_PROVIDER_RECONNECT_STORM"
    assert producer_session.paid_provider_safety_error(
        {"max_active_streams": 1, "reconnects": 1, "status": "CONNECTED"},
        max_reconnects=5) is None


class _PaidRisk:
    def __init__(self, label):
        self.label = label

    def observe_market_sample(self, mint, market):
        return None

    def assess(self, mint):
        return {
            "risk_label": self.label,
            "risk_reasons": (["POOL_TOO_HOT"] if self.label == "RISK_HIGH" else []),
        }


class _FreshPaidSidecar:
    def resolve(self, mint, **kwargs):
        return {
            "current_price": "0.001",
            "current_market_cap_usd": "45000",
            "liquidity_usd": "15000",
            "market_context_fetched_at_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "all_present": True,
            "basis": "REAL_MARKET_PRESENT",
            "attempts": [],
        }


class _NoErrors:
    count = 0

    def log(self, *args, **kwargs):
        self.count += 1


def _run_paid_gate_candidate(tmp_path, monkeypatch, *, risk_label):
    compose_calls = {"count": 0}

    def compose_stub(*args, **kwargs):
        compose_calls["count"] += 1
        return {
            "compose_decision": "NO_SEND_DISPATCHED",
            "compose_reason": "DISPATCHABLE",
            "eligible": True,
            "send_result": object(),
            "delivery": {"delivery_state": "SENT_OK_COMMITTED",
                         "attempt_id": "stub-attempt", "message_id": None,
                         "ledger_committed": True},
        }

    monkeypatch.setattr(
        producer_session.sess.cs, "compose_and_maybe_send", compose_stub)
    gate = producer_session.make_discord_risk_gate(
        risk_engine=_PaidRisk(risk_label),
        discord_block_ledger=producer_session.DiscordBlockLedger(),
        discord_blocks_path=tmp_path / "paid-discord-blocks.jsonl",
        min_liquidity_usd=Decimal("4500"),
        mode="PAID_PRIMARY_PRIVATE_DISCORD",
        errors=_NoErrors(),
    )
    result = producer_session.sess.run_cap1_candidates(
        [{
            "token_mint": MINT,
            "candidate_id": "paid-candidate",
            "migration_time_utc": "2026-07-15T12:00:00Z",
            "source_ref": "paid-grpc",
            "symbol_or_name": None,
        }],
        sidecar=_FreshPaidSidecar(),
        ath_transport=object(),
        ath_endpoint_secret=object(),
        now_utc=datetime.now(timezone.utc),
        now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sleep_fn=lambda _seconds: None,
        ledger=object(),
        guard=object(),
        authorization=object(),
        created_at_utc="2026-07-15T12:00:00Z",
        pre_reserve_gate_fn=gate,
        activation_gate_fn=_eligible_activation_gate,
    )
    return result, compose_calls["count"]


def test_paid_risk_high_blocks_before_compose_reserve_cap_and_transport(tmp_path, monkeypatch):
    result, compose_calls = _run_paid_gate_candidate(
        tmp_path, monkeypatch, risk_label="RISK_HIGH")
    assert result["outcome"] == "ZERO_SEND"
    assert result["sent_attempt"] is None
    assert compose_calls == 0
    assert not (tmp_path / "paid-ledger.jsonl").exists()


def test_valid_paid_low_risk_candidate_reaches_existing_send_seam(tmp_path, monkeypatch):
    result, compose_calls = _run_paid_gate_candidate(
        tmp_path, monkeypatch, risk_label="RISK_LOW")
    assert result["outcome"] == "ONE_SEND_COMMITTED"
    assert result["per_candidate"][0]["reason"] == "SENT_OK_COMMITTED"
    assert compose_calls == 1


def test_compose_binds_fresh_central_ath_not_older_selected_market_attempt(monkeypatch):
    stale = {
        "ath_price": "0.0000329", "ath_market_cap": "32900",
        "ath_timestamp": "2026-07-15T12:01:00Z",
        "ath_provider": "PUMPSWAP_EVENT_EFFECTIVE_RESERVES",
        "ath_observation_type": "PUMPSWAP_BUY_EFFECTIVE_RESERVES",
        "ath_status": "CONFIRMED",
    }
    fresh = {
        **stale,
        "ath_price": "0.00003670855210594000685964273593",
        "ath_market_cap": "36708.55210594000685964273593",
        "ath_timestamp": "2026-07-15T12:02:00Z",
        "ath_observation_type": "PUMPSWAP_SELL_EFFECTIVE_RESERVES",
    }

    class Sidecar(_FreshPaidSidecar):
        def resolve(self, *args, **kwargs):
            return {**super().resolve(*args, **kwargs), "central_ath": stale}

        def central_ath_snapshot(self, _mint):
            return dict(fresh)

    captured = {}

    def compose_stub(request, **_kwargs):
        captured["market_cap"] = request.authoritative_ath_market_cap_usd
        return {
            "compose_decision": "NO_SEND_DISPATCHED",
            "compose_reason": "DISPATCHABLE",
            "compose_anchored_ath_mc": "$36.7k",
            "central_ath": stale,
            "eligible": True,
            "send_result": object(),
        }

    monkeypatch.setattr(
        producer_session.sess.cs, "compose_and_maybe_send", compose_stub)
    result = producer_session.sess.run_cap1_candidates(
        [{"token_mint": MINT, "candidate_id": "fresh-ath",
          "migration_time_utc": "2026-07-15T12:00:00Z"}],
        sidecar=Sidecar(), ath_transport=object(), ath_endpoint_secret=object(),
        now_utc=datetime.now(timezone.utc), now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: "2026-07-15T12:03:00Z", sleep_fn=lambda _seconds: None,
        ledger=object(), guard=object(), authorization=object(),
        created_at_utc="2026-07-15T12:03:00Z",
        activation_gate_fn=_eligible_activation_gate,
    )
    rec = result["per_candidate"][0]
    assert captured["market_cap"] == fresh["ath_market_cap"]
    assert rec["central_ath"] == fresh
    assert rec["market_context"]["central_ath"] == fresh
    assert rec["compose_anchored_ath_mc"] == "$36.7k"


def test_stale_paid_birdeye_data_cannot_reach_send_seam(tmp_path, monkeypatch):
    secret = _endpoint_secret()
    inner = _SequenceTransport([
        _result({"success": True, "data": {"value": "2.5", "updateUnixTime": 900}}),
        _result({"success": True, "data": {"mc": "50000", "liquidity": "9000"}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner,
        endpoint_secret=secret,
        min_interval_seconds=0,
        max_attempts=1,
        max_data_age_seconds=10,
        now_fn=lambda: 1000,
    )
    sidecar = producer_session.Cap1MarketSidecar(
        transport=transport,
        endpoint_secret=secret,
        timeout_seconds=1,
        caps=producer_session.Cap1MarketCaps(
            max_delayed_refresh_seconds=0,
            max_calls_per_token=1,
            max_calls_total=1,
        ),
    )
    compose_calls = {"count": 0}
    monkeypatch.setattr(
        producer_session.sess.cs,
        "compose_and_maybe_send",
        lambda *args, **kwargs: compose_calls.__setitem__("count", compose_calls["count"] + 1),
    )
    result = producer_session.sess.run_cap1_candidates(
        [{"token_mint": MINT, "candidate_id": "stale", "migration_time_utc": None}],
        sidecar=sidecar,
        ath_transport=transport,
        ath_endpoint_secret=secret,
        now_utc=datetime.now(timezone.utc),
        now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: "1970-01-01T00:16:40Z",
        sleep_fn=lambda _seconds: None,
        ledger=object(),
        guard=object(),
        authorization=object(),
        created_at_utc="1970-01-01T00:16:40Z",
        activation_gate_fn=_eligible_activation_gate,
    )
    assert result["outcome"] == "ZERO_SEND"
    assert result["per_candidate"][0]["reason"] == "NO_SEND_MARKET_STALE"
    assert compose_calls["count"] == 0
    assert transport.stats()["stale_refusals"] == 1


def test_paid_private_send_cap_one_latches_after_first_attempt():
    budget = FreeTierCreditBudget(
        FreeTierCreditBudgetCaps(max_sends_per_run=1), discord_enabled=True)
    budget.record_send_attempt(sent_ok=True)
    snap = budget.snapshot()
    assert snap["send_attempts"] == 1
    assert snap["sent_ok_count"] == 1
    assert snap["private_ping_count"] == 1
    assert snap["budget_stop_reason"] == BUDGET_STOP_SEND_CAP
    with pytest.raises(FreeTierBudgetExhausted):
        budget.check_and_raise()


def test_market_tracker_transient_miss_recovers_same_candidate_after_backoff():
    now = {"value": "2026-07-15T12:00:00Z"}
    attempts = [
        {
            "attempt_at_utc": now["value"], "price_value": "1", "mc_value": None,
            "lp_value": "9000", "all_present": False, "basis": "REAL_MARKET_INCOMPLETE",
            "provider_market_state": MARKET_INCOMPLETE,
            "provider_reason_code": "MARKET_CAP_MISSING",
        },
        {
            "attempt_at_utc": "2026-07-15T12:00:05Z", "price_value": "1",
            "mc_value": "50000", "lp_value": "9000", "all_present": True,
            "basis": "REAL_MARKET_PRESENT", "provider_market_state": MARKET_READY,
            "provider_reason_code": "REQUIRED_FIELDS_FRESH",
            "provider_timestamp_utc": "2026-07-15T12:00:05Z",
        },
    ]
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(5,), max_transient_attempts=3,
    ))
    fetched = {"count": 0}

    def fetch(_at):
        fetched["count"] += 1
        return attempts.pop(0)

    first = tracker.resolve(
        MINT, migration_time_utc=now["value"], now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=fetch)
    assert first["market_state"] == MARKET_INCOMPLETE
    assert first["all_present"] is False
    now["value"] = "2026-07-15T12:00:01Z"
    backoff = tracker.resolve(
        MINT, migration_time_utc=None, now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=fetch)
    assert backoff["market_state"] == MARKET_INCOMPLETE
    assert backoff["basis"] == "MARKET_BACKOFF"
    assert fetched["count"] == 1
    now["value"] = "2026-07-15T12:00:05Z"
    recovered = tracker.resolve(
        MINT, migration_time_utc=None, now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=fetch)
    assert recovered["market_state"] == MARKET_READY
    assert recovered["all_present"] is True
    assert recovered["market_attempt_count"] == 2
    assert len(tracker.snapshot()["per_mint"]) == 1
    now["value"] = "2026-07-15T12:00:06Z"
    cached_ready = tracker.resolve(
        MINT, migration_time_utc=None, now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=fetch)
    assert cached_ready["market_state"] == MARKET_READY
    assert cached_ready["all_present"] is True
    assert cached_ready["basis"] == "MARKET_BACKOFF"
    assert fetched["count"] == 2


def test_market_tracker_exhaustion_enters_recovery_backoff_not_terminal():
    # PHX2-E2E-004: grace exhaustion must enter a bounded, recoverable backoff
    # (NOT permanent MARKET_UNAVAILABLE/MARKET_TERMINAL). Before the fix this
    # returned MARKET_TERMINAL forever and never called fetch again.
    now = {"value": "2026-07-15T12:00:00Z"}
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0,), max_transient_attempts=2,
    ))
    fetched = {"count": 0}

    def missing(at):
        fetched["count"] += 1
        return {
            "attempt_at_utc": at, "price_value": None, "mc_value": None,
            "lp_value": None, "all_present": False,
            "basis": "REAL_MARKET_INCOMPLETE",
            "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "PROVIDER_NOT_INDEXED",
        }
    first = tracker.resolve(MINT, migration_time_utc=now["value"],
                            now_iso_fn=lambda: now["value"], fetch_attempt_fn=missing)
    assert first["market_state"] == MARKET_INDEXING
    now["value"] = "2026-07-15T12:00:01Z"
    exhausted = tracker.resolve(MINT, migration_time_utc=None,
                                now_iso_fn=lambda: now["value"], fetch_attempt_fn=missing)
    # Recovery backoff, not permanent terminalization.
    assert exhausted["market_state"] == MARKET_RECOVERY_BACKOFF
    assert exhausted["market_reason_code"] == GRACE_EXHAUSTION_ATTEMPTS
    assert exhausted["all_present"] is False
    # A concrete next recovery probe is scheduled (never None-forever).
    assert exhausted["next_market_refresh_at_utc"] is not None
    assert exhausted["market_next_recovery_probe_at_utc"] == "2026-07-15T12:01:01Z"
    assert fetched["count"] == 2

    # Before the probe is due the provider is NOT called and the reason is an
    # explicit temporary NOT_DUE (candidate stays active, not terminal).
    now["value"] = "2026-07-15T12:00:30Z"
    not_due = tracker.resolve(
        MINT, migration_time_utc=None, now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=lambda _at: pytest.fail("recovery backoff fetched before due"),
    )
    assert not_due["market_state"] == MARKET_RECOVERY_BACKOFF
    assert not_due["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
    assert not_due["attempts"] == []
    assert fetched["count"] == 2

    # When due, a single healthy fetch recovers the candidate to MARKET_READY.
    now["value"] = "2026-07-15T12:01:01Z"
    recovered = tracker.resolve(
        MINT, migration_time_utc=None, now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=lambda at: {
            "attempt_at_utc": at, "price_value": "1", "mc_value": "50000",
            "lp_value": "9000", "all_present": True,
            "provider_market_state": MARKET_READY,
            "provider_reason_code": "REQUIRED_FIELDS_FRESH",
            "provider_timestamp_utc": at,
        })
    assert recovered["market_state"] == MARKET_READY
    assert recovered["all_present"] is True
    assert recovered["market_recovered_at_utc"] == "2026-07-15T12:01:01Z"
    snap = tracker.snapshot()
    assert snap["counters"]["market_terminal_candidate_state_reached"] == 0
    assert snap["counters"]["market_recovery_succeeded"] == 1

    invalid_tracker = PaidMarketReadinessTracker()
    invalid = invalid_tracker.resolve(
        OTHER_MINT, migration_time_utc=now["value"], now_iso_fn=lambda: now["value"],
        fetch_attempt_fn=lambda at: {
            "attempt_at_utc": at, "price_value": None, "mc_value": "50000",
            "lp_value": "9000", "all_present": False,
            "provider_market_state": MARKET_INVALID,
            "provider_reason_code": "PRICE_INVALID",
        })
    assert invalid["market_state"] == MARKET_INVALID
    assert invalid["all_present"] is False


def test_one_incomplete_mint_cannot_cap_or_starve_the_next_candidate(monkeypatch):
    class PathTransport:
        def get(self, **kwargs):
            mint = kwargs["query_params"]["address"]
            if kwargs["path"] == "/defi/price":
                return _result({"success": True, "data": {
                    "value": "1", "updateUnixTime": 1000,
                }})
            if mint == MINT:
                return _result({"success": True, "data": {"liquidity": "9000"}})
            return _result({"success": True, "data": {
                "mc": "50000", "liquidity": "9000",
            }})

    secret = _endpoint_secret()
    transport = PaidBirdeyeMarketTransport(
        inner_transport=PathTransport(), endpoint_secret=secret, min_interval_seconds=0,
        cache_ttl_seconds=0, max_attempts=1, now_fn=lambda: 1000,
    )
    sidecar = producer_session.Cap1MarketSidecar(
        transport=transport, endpoint_secret=secret, timeout_seconds=1,
        caps=producer_session.Cap1MarketCaps(
            max_delayed_refresh_seconds=0, max_calls_per_token=1,
            max_calls_total=10, max_consecutive_failures=1,
        ),
    )
    monkeypatch.setattr(producer_session.sess.cs, "compose_and_maybe_send", lambda *_a, **_kw: {
        "compose_decision": "NO_SEND_DISPATCHED", "eligible": True,
        "send_result": object(),
        "delivery": {"delivery_state": "SENT_OK_COMMITTED",
                     "attempt_id": "stub-attempt", "message_id": None,
                     "ledger_committed": True},
    })
    result = producer_session.sess.run_cap1_candidates(
        [
            {"token_mint": MINT, "candidate_id": "one", "migration_time_utc": None},
            {"token_mint": OTHER_MINT, "candidate_id": "two", "migration_time_utc": None},
        ],
        sidecar=sidecar, ath_transport=transport, ath_endpoint_secret=secret,
        now_utc=datetime.now(timezone.utc), now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: "1970-01-01T00:16:40Z", sleep_fn=lambda _s: None,
        ledger=object(), guard=object(), authorization=object(),
        created_at_utc="1970-01-01T00:16:40Z",
        activation_gate_fn=_eligible_activation_gate,
    )
    assert result["per_candidate"][0]["reason"] == "NO_SEND_MARKET_INCOMPLETE"
    assert result["per_candidate"][1]["reason"] == "SENT_OK_COMMITTED"
    assert result["outcome"] == "ONE_SEND_COMMITTED"


def test_provisional_ath_never_decreases_and_missing_ohlcv_does_not_erase_it():
    clock = {"value": 1000.0}
    inner = _SequenceTransport([
        _result({"success": True, "data": {"value": "10", "updateUnixTime": 1000}}),
        _result({"success": True, "data": {"value": "9", "updateUnixTime": 1030}}),
        _result({"success": True, "data": {"value": "8", "updateUnixTime": 1061}}),
        _result({"success": True, "data": {"items": []}}),
        _result({"success": True, "data": {"items": [
            {"h": "12", "unixTime": 1062},
        ]}}),
    ])
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, ohlcv_cache_ttl_seconds=0, max_attempts=1,
        max_data_age_seconds=100, now_fn=lambda: clock["value"],
    )
    for i, epoch in enumerate((1000, 1030, 1061), 1):
        clock["value"] = float(epoch)
        transport.get(endpoint_secret=object(), path="/defi/price",
                      query_params={"address": MINT, "sample": str(i)}, timeout_seconds=1)
    provisional = transport.ath_snapshot(MINT)
    assert provisional["ath_price_usd"] == "10"
    assert provisional["observation_type"] == "ATH_PROVISIONAL_LIVE_OBSERVED"
    assert provisional["sample_count"] == 3
    assert provisional["provisional_ready"] is True
    transport.get(endpoint_secret=object(), path="/defi/ohlcv",
                  query_params={"address": MINT, "type": "1m", "time_from": "1000",
                                "time_to": "1061", "sample": "missing"}, timeout_seconds=1)
    assert transport.ath_snapshot(MINT)["ath_price_usd"] == "10"
    assert transport.ath_snapshot(MINT)["observation_type"] == "ATH_PROVISIONAL_LIVE_OBSERVED"
    transport.get(endpoint_secret=object(), path="/defi/ohlcv",
                  query_params={"address": MINT, "type": "1m", "time_from": "1000",
                                "time_to": "1062", "sample": "confirmed"}, timeout_seconds=1)
    confirmed = transport.ath_snapshot(MINT)
    assert confirmed["ath_price_usd"] == "12"
    assert confirmed["observation_type"] == "ATH_PAID_OHLCV_INCOMPLETE"
    assert confirmed["discord_eligible"] is False
    assert producer_session.artifacts.scan_value_safe(
        json.dumps(confirmed, sort_keys=True)
    )


class _V3RoutedInner:
    """Route V3 pair/token candle requests over a fixed 1:1-quoted series.

    The fictional pool is quoted 1:1 with USD (implied ratio 1, inside the
    structural sanity band), so pair-native highs ARE the USD highs.
    ``candles`` maps 15s bucket start -> high; 1s requests serve the bucket's
    high on its first second.  ``fail_from``/``fail_to`` mark an inclusive
    15s-request range that always answers HTTP 500.
    """

    def __init__(self, candles, *, fail_from=None):
        self.candles = dict(candles)
        self.fail_from = fail_from
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(kwargs)
        params = dict(kwargs["query_params"])
        path = kwargs["path"]
        start = int(params["time_from"])
        end = int(params["time_to"])
        interval = params.get("type")
        if path == "/defi/v3/ohlcv/pair" and interval == "15s" \
                and self.fail_from is not None and start >= self.fail_from:
            return _result(None, status=500,
                           refusal=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED)
        address = str(params["address"])
        items = []
        if interval == "15s":
            for bucket, high in sorted(self.candles.items()):
                if start <= bucket <= end:
                    items.append({"h": high, "unix_time": bucket,
                                  "address": address})
        else:  # 1s refinement / valuation
            for bucket, high in sorted(self.candles.items()):
                if start <= bucket <= end:
                    items.append({"h": high, "unix_time": bucket,
                                  "address": address})
        return _result({"success": True, "data": {"items": items}})


def test_creation_anchored_ohlcv_paginates_through_in_progress_candle(tmp_path):
    store = CentralAthStateStore(tmp_path)
    assert store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:01:00Z")
    inner = _V3RoutedInner({60: "10", 120: "12"})
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, ohlcv_cache_ttl_seconds=0, max_attempts=1,
        now_fn=lambda: 179.0, ath_store=store, v3_page_candles=1,
    )
    outcome = transport.refresh_ath_history(MINT, timeout_seconds=1)
    assert outcome["complete"] is True
    coarse = [dict(call["query_params"]) for call in inner.calls
              if call["path"] == "/defi/v3/ohlcv/pair"
              and call["query_params"]["type"] == "15s"]
    # Deterministic contiguous 15s chunks tiling [anchor, now] exactly,
    # including the in-progress candle.
    assert coarse[0]["time_from"] == "60"
    assert coarse[-1]["time_to"] == "179"
    for previous, current in zip(coarse, coarse[1:]):
        assert int(current["time_from"]) == int(previous["time_to"]) + 1
    snap = store.snapshot(MINT)
    assert snap["ath_price"] == "12"
    assert snap["price_provenance"]["status"] == "CONFIRMED"
    persisted = json.loads((tmp_path / "ath_state.json").read_text(encoding="utf-8"))
    v3 = persisted["mints"][MINT]["ath_v3_pair"]
    assert v3["history_complete"] is True
    assert v3["window_from_unix"] == 60
    assert v3["window_to_unix"] == 179


def test_complete_first_page_does_not_confirm_when_later_page_is_incomplete(tmp_path):
    store = CentralAthStateStore(tmp_path)
    assert store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:01:00Z")
    inner = _V3RoutedInner({60: "10"}, fail_from=75)
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, ohlcv_cache_ttl_seconds=0, max_attempts=1,
        now_fn=lambda: 179.0, ath_store=store, v3_page_candles=1,
    )
    outcome = transport.refresh_ath_history(MINT, timeout_seconds=1)
    assert outcome["complete"] is False
    snap = store.snapshot(MINT)
    assert snap["ath_price"] == "10"
    assert snap["price_provenance"]["status"] == "PROVISIONAL"
    assert snap["ath_v3_pair"]["history_complete"] is False
    assert transport.ath_snapshot(MINT)["central_ath"][
        "ath_post_migration_complete"] is False


def test_incomplete_newborn_ohlcv_is_retried_not_permanently_cached(tmp_path):
    mono = {"value": 0.0}
    store = CentralAthStateStore(tmp_path)
    store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:01:00Z")
    inner = _V3RoutedInner({})              # provider has indexed nothing yet
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(), min_interval_seconds=0,
        cache_ttl_seconds=0, ohlcv_cache_ttl_seconds=25, max_attempts=1,
        now_fn=lambda: 119.0, monotonic_fn=lambda: mono["value"],
        ath_store=store,
    )
    first = transport.refresh_ath_history(MINT, timeout_seconds=1)
    # A fully-covered but EMPTY window is a newborn indexing lag, never a
    # completed (frozen-empty) history.
    assert first["complete"] is False
    assert store.snapshot(MINT) is None
    inner.candles[60] = "12"                # the provider catches up
    mono["value"] = 30.0
    second = transport.refresh_ath_history(MINT, timeout_seconds=1)
    assert second["complete"] is True
    assert store.snapshot(MINT)["ath_price"] == "12"


def test_subscribe_has_no_total_deadline_and_outlives_unary_timeout(monkeypatch):
    update = _create_pool_update()
    update.HasField = lambda name: name == "transaction"
    kwargs_seen = {}

    class Response:
        def __init__(self):
            self.done = False

        def __next__(self):
            if self.done:
                raise StopIteration
            self.done = True
            time.sleep(0.05)
            return update

        def cancel(self):
            return None

    class Context:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    class Stub:
        def Subscribe(self, *_args, **kwargs):
            kwargs_seen.update(kwargs)
            return Response()

    runtime = SimpleNamespace(
        timeout_seconds=0.01, safe_config=SimpleNamespace(provider_id="TEST_PROVIDER"),
    )
    monkeypatch.setattr(paid_grpc_source_module, "_open_channel", lambda *_a, **_kw: Context())
    monkeypatch.setattr(paid_grpc_source_module.geyser_pb2_grpc, "GeyserStub", lambda _c: Stub())
    monkeypatch.setattr(paid_grpc_source_module.geyser_pb2, "SubscribeUpdate", SimpleNamespace)
    monkeypatch.setattr(paid_grpc_source_module, "_build_metadata", lambda _cfg: ())
    monkeypatch.setattr(paid_grpc_source_module, "decode_create_pool_update",
                        lambda *_a, **_kw: _event())
    source = PaidCreatePoolYellowstoneSource(runtime_config=runtime, max_messages_to_scan=None)
    assert list(source.iter_events(max_events=1)) == [_event()]
    assert "timeout" not in kwargs_seen


def test_watchdog_replaces_one_stale_stream_without_overlap():
    made = []

    class Source:
        last_refusal_reason = "NONE"
        last_update_epoch = None

        def __init__(self):
            self.closed = threading.Event()
            made.append(self)

        def iter_events(self, *, max_events):
            self.closed.wait(timeout=2.0)
            if False:
                yield None

        def close(self):
            self.closed.set()

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source, dedupe=ProviderCandidateDedupe(), stale_after_seconds=0.05,
        reconnect_backoff_seconds=0, random_fn=lambda: 0.5,
    )
    owner.start()
    deadline = time.time() + 1.0
    while owner.snapshot()["connect_attempts"] < 2 and time.time() < deadline:
        time.sleep(0.005)
    snap = owner.snapshot()
    owner.stop(timeout_seconds=1.0)
    assert snap["connect_attempts"] == 2
    assert snap["watchdog_reconnects"] == 1
    assert snap["max_active_streams"] == 1
    assert made[0].closed.is_set()


def test_normal_raw_updates_prevent_watchdog_and_shutdown_is_clean():
    class Source:
        last_refusal_reason = "NONE"

        def __init__(self):
            self.last_update_epoch = time.time()
            self.closed = threading.Event()

        def iter_events(self, *, max_events):
            while not self.closed.wait(0.01):
                self.last_update_epoch = time.time()
            if False:
                yield None

        def close(self):
            self.closed.set()

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=Source, dedupe=ProviderCandidateDedupe(), stale_after_seconds=0.05,
        reconnect_backoff_seconds=0, random_fn=lambda: 0.5,
    )
    owner.start()
    time.sleep(0.15)
    before = owner.snapshot()
    owner.stop(timeout_seconds=1.0)
    after = owner.snapshot()
    assert before["connect_attempts"] == 1
    assert before["watchdog_reconnects"] == 0
    assert before["max_active_streams"] == 1
    assert after["active_streams"] == 0
    assert after["operator_shutdowns"] == 1


def test_cooperative_stop_returns_and_flushes_a_final_shape():
    flushes = []
    heartbeats = []
    watchlist = producer_session.Watchlist(max_size=4)
    result = producer_session.run_production_live_watch(
        watchlist=watchlist,
        axiom_source=producer_session.axiomgate.NullAxiomFeeSource(),
        axiom_config=producer_session._strict_axiom_config(),
        sidecar_factory=lambda _tick: object(),
        ath_transport=object(),
        ath_endpoint_secret=object(),
        ledger=object(),
        guard_factory=lambda: object(),
        authorization=object(),
        now_dt_fn=lambda: datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
        now_iso_fn=lambda: "2026-07-15T12:00:00Z",
        now_seconds=lambda: Decimal(0),
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
        bounds=producer_session.ProductionBounds(max_runtime_seconds=60),
        run_cap1_candidates_fn=lambda *_a, **_kw: pytest.fail("engine must not run"),
        ledger_line_count_fn=lambda: 0,
        on_heartbeat=heartbeats.append,
        partial_flush_fn=flushes.append,
        stop_requested_fn=lambda: True,
    )
    assert result["stop_reason"] == "OPERATOR_REQUESTED"
    assert result["outcome"] == "ZERO_SEND"
    assert result["interrupted"] is False
    assert flushes and flushes[-1]["stop_reason"] == "OPERATOR_REQUESTED"
    assert heartbeats and heartbeats[-1]["stop_reason"] == "OPERATOR_REQUESTED"
