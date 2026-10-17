from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.free_tier_producer.ath_state import (
    SUPPLY_BASIS_AUTHORITATIVE_RPC,
    CentralAthStateStore,
)
from PHX2.free_tier_producer.authoritative_supply import (
    SUPPLY_PENDING_AMOUNT_INVALID,
    SUPPLY_PENDING_CONTEXT_SLOT_INVALID,
    SUPPLY_PENDING_DECIMALS_INVALID,
    SUPPLY_PENDING_EPOCH_MISMATCH,
    SUPPLY_PENDING_MINT_MISMATCH,
    SUPPLY_PENDING_PRE_BOUNDARY,
    SUPPLY_PENDING_RESPONSE_ID,
    SUPPLY_PENDING_TRANSPORT,
    SUPPLY_VALID,
    AuthoritativeSupplyBridge,
    HeliusTokenSupplyClient,
)
from PHX2.free_tier_producer.market_budget import (
    ORIGIN_AUTHORITATIVE_SUPPLY,
    PHYSICAL_AUTHORITATIVE_SUPPLY,
    MarketPhysicalRequestMeter,
)
from PHX2.watchdog.health import (
    HEALTHY,
    RESTARTABLE_PROCESS_FAILURE,
    HealthVerdict,
    canonicalize_health,
)
from PHX2.watchdog.operational_health import (
    DEGRADED_AUTHORITATIVE_SUPPLY,
    DIM_UNHEALTHY,
    UNHEALTHY_AUTHORITATIVE_SUPPLY,
    evaluate_authoritative_supply,
)
from PHX2.free_tier_producer import helius_source
from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_MIGRATION_SOURCE_MODE,
    canonical_launcher_arguments,
)
from PHX2.models.ath_coverage import ATH_COVERAGE_COMPLETE_LIVE
from PHX2.stage30 import stage30_11_13_committed_no_send_composer as composer


MINT = "7YttLkHDoNj9wyDur5U4DqA4AwT3N8X9psJf7GmZpump"
EPOCH = "epoch_authoritative_supply"


def _response(payload, *, mint=None, amount="123456789", decimals=6, slot=991):
    return 200, {
        "jsonrpc": "2.0",
        "id": payload["id"],
        "result": {
            "context": {"slot": slot},
            "value": {
                "amount": amount,
                "decimals": decimals,
                "uiAmountString": format(
                    Decimal(amount) / (Decimal(10) ** decimals), "f"),
                **({"requestedMint": mint} if mint is not None else {}),
            },
        },
    }


def _client(tmp_path, post_fn, *, clock=lambda: 10.0, ttl=3600.0):
    meter = MarketPhysicalRequestMeter(
        ticket_artifact=tmp_path / "provider_request_tickets.jsonl")
    client = HeliusTokenSupplyClient(
        rpc_base_url="https://mainnet.helius-rpc.com",
        api_key="test-secret-never-artifacted",
        physical_request_meter=meter,
        post_fn=post_fn,
        cache_ttl_seconds=ttl,
        artifact_path=tmp_path / "authoritative_supply.jsonl",
        monotonic_fn=clock,
    )
    return client, meter


def test_exact_rpc_binding_decimal_ticket_and_cache(tmp_path):
    calls = []

    def post(url, payload, timeout):
        calls.append((url, payload, timeout))
        return _response(payload, mint=payload["params"][0])

    client, meter = _client(tmp_path, post)
    first = client.fetch(mint=MINT, live_epoch_id=EPOCH)
    second = client.fetch(mint=MINT, live_epoch_id=EPOCH)

    assert first.accepted and second.accepted
    assert first.record is not None and second.record is not None
    assert first.record.raw_amount == "123456789"
    assert first.record.normalized_supply == "123.456789"
    assert first.record.rpc_context_slot == 991
    assert first.record.live_epoch_id == EPOCH
    assert first.record.request_ticket_id.startswith("provider_")
    assert second.record.cache_hit is True
    assert second.record.request_ticket_id == first.record.request_ticket_id
    assert len(calls) == 1
    assert calls[0][1]["method"] == "getTokenSupply"
    assert calls[0][1]["params"] == [MINT, {"commitment": "confirmed"}]
    assert meter.category_total(PHYSICAL_AUTHORITATIVE_SUPPLY) == 1
    assert meter.origin_total(ORIGIN_AUTHORITATIVE_SUPPLY) == 1
    ticket = json.loads(
        (tmp_path / "provider_request_tickets.jsonl").read_text().splitlines()[0])
    assert ticket["mint"] == MINT
    assert ticket["epoch_id"] == EPOCH
    assert ticket["observation_accepted"] is True
    supply = json.loads(
        (tmp_path / "authoritative_supply.jsonl").read_text().splitlines()[0])
    assert supply["mint"] == MINT
    assert supply["normalized_supply"] == "123.456789"
    assert "test-secret-never-artifacted" not in json.dumps(ticket)
    assert "test-secret-never-artifacted" not in json.dumps(supply)
    assert "test-secret-never-artifacted" not in repr(client)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda payload, response: response.update(id="wrong"),
         SUPPLY_PENDING_RESPONSE_ID),
        (lambda payload, response: response["result"]["value"].update(
            requestedMint="CrossBound1111111111111111111111111pump"),
         SUPPLY_PENDING_MINT_MISMATCH),
        (lambda payload, response: response["result"]["value"].update(
            amount="-1"), SUPPLY_PENDING_AMOUNT_INVALID),
        (lambda payload, response: response["result"]["value"].update(
            decimals=256), SUPPLY_PENDING_DECIMALS_INVALID),
        (lambda payload, response: response["result"]["context"].update(
            slot=None), SUPPLY_PENDING_CONTEXT_SLOT_INVALID),
    ],
)
def test_malformed_or_cross_bound_response_never_yields_supply(
    tmp_path, mutation, reason,
):
    def post(url, payload, timeout):
        status, response = _response(payload)
        mutation(payload, response)
        return status, response

    client, meter = _client(tmp_path, post)
    outcome = client.fetch(mint=MINT, live_epoch_id=EPOCH)
    assert outcome.record is None
    assert outcome.reason == reason
    assert meter.total == 1
    assert client.stats()["supply_successes"] == 0
    assert not (tmp_path / "authoritative_supply.jsonl").exists()


def test_transport_failure_is_named_and_ticket_is_completed(tmp_path):
    def post(url, payload, timeout):
        raise OSError("synthetic transport failure")

    client, meter = _client(tmp_path, post)
    outcome = client.fetch(mint=MINT, live_epoch_id=EPOCH)
    assert outcome.reason == SUPPLY_PENDING_TRANSPORT
    assert outcome.record is None
    assert meter.snapshot()["pending_physical_request_tickets"] == 0
    ticket = json.loads(
        (tmp_path / "provider_request_tickets.jsonl").read_text().splitlines()[0])
    assert ticket["provider_outcome"] == SUPPLY_PENDING_TRANSPORT
    assert ticket["observation_accepted"] is False


def test_cache_is_epoch_bound_and_concurrent_mints_never_cross_contaminate(tmp_path):
    calls = []

    def post(url, payload, timeout):
        mint = payload["params"][0]
        calls.append(mint)
        raw = str(10_000 + int(mint[1:3]))
        return _response(payload, mint=mint, amount=raw, decimals=2)

    client, meter = _client(tmp_path, post)
    mints = [f"M{i:02d}Concurrent11111111111111111111111pump" for i in range(32)]
    with ThreadPoolExecutor(max_workers=16) as pool:
        outcomes = list(pool.map(
            lambda mint: client.fetch(mint=mint, live_epoch_id=EPOCH), mints))
    assert all(item.accepted for item in outcomes)
    records = [item.record for item in outcomes]
    assert all(record is not None for record in records)
    assert {record.mint for record in records if record is not None} == set(mints)
    for record in records:
        assert record is not None
        assert record.raw_amount == str(10_000 + int(record.mint[1:3]))
    assert len(calls) == 32
    assert meter.total == 32

    # A record from a prior live epoch is never reused as current proof.
    again = client.fetch(mint=mints[0], live_epoch_id="epoch_next")
    assert again.accepted
    assert len(calls) == 33
    assert again.record is not None and again.record.live_epoch_id == "epoch_next"


def test_bridge_rejects_preboundary_and_wrong_epoch_before_any_rpc(tmp_path):
    calls = []

    def post(url, payload, timeout):
        calls.append(payload)
        return _response(payload)

    client, _ = _client(tmp_path, post)
    store = CentralAthStateStore(str(tmp_path / "ath"))
    bridge = AuthoritativeSupplyBridge(client=client, ath_store=store)
    entry = SimpleNamespace(
        token_mint=MINT, live_epoch_id=EPOCH, migration_slot=99)
    assert bridge.observe_entry(
        entry, current_epoch_id=EPOCH, first_eligible_slot=100,
    ) == SUPPLY_PENDING_PRE_BOUNDARY
    assert calls == []
    entry.migration_slot = 101
    assert bridge.observe_entry(
        entry, current_epoch_id="another_epoch", first_eligible_slot=100,
    ) == SUPPLY_PENDING_EPOCH_MISMATCH
    assert calls == []
    assert store.snapshot(MINT) is None


def test_bridge_retry_then_supply_to_ohlcv_to_resolved_tuple_is_durable(tmp_path):
    now = [100.0]
    outcomes = ["fail", "success"]

    def post(url, payload, timeout):
        if outcomes.pop(0) == "fail":
            raise OSError("synthetic")
        return _response(payload, mint=MINT, amount="7654321", decimals=3)

    client, meter = _client(tmp_path, post, clock=lambda: now[0])
    ath_dir = tmp_path / "ath"
    store = CentralAthStateStore(str(ath_dir))
    bridge = AuthoritativeSupplyBridge(
        client=client,
        ath_store=store,
        backoff_base_seconds=5,
        monotonic_fn=lambda: now[0],
    )
    entry = SimpleNamespace(
        token_mint=MINT, live_epoch_id=EPOCH, migration_slot=101)
    assert bridge.observe_entry(
        entry, current_epoch_id=EPOCH, first_eligible_slot=100,
    ) == SUPPLY_PENDING_TRANSPORT
    assert bridge.due(MINT) is False
    now[0] += 5
    assert bridge.observe_entry(
        entry, current_epoch_id=EPOCH, first_eligible_slot=100,
    ) == SUPPLY_VALID
    assert meter.total == 2
    assert bridge.stats()["supply_retries"] == 1
    assert bridge.stats()["supply_central_observations"] == 1

    assert store.observe_ohlcv_high(
        mint=MINT,
        high_price_usd="0.125",
        candle_timestamp="2026-08-03T01:00:00Z",
        history_complete=True,
        interval="1m",
        time_from_unix=1,
        time_to_unix=2,
    )
    snapshot = store.snapshot(MINT)
    assert snapshot is not None
    assert snapshot["resolved"] is True
    assert snapshot["resolved_supply"] == "7654.321"
    assert snapshot["resolved_supply_basis"] == SUPPLY_BASIS_AUTHORITATIVE_RPC
    assert snapshot["resolved_ath_market_cap"] == "956.790125"
    assert snapshot["ath_resolved_valid"] is True
    assert bridge.stats()["supply_resolved_tuples"] == 1

    restored = CentralAthStateStore(str(ath_dir))
    replay = restored.snapshot(MINT)
    assert replay is not None
    assert replay["resolved_ath_market_cap"] == "956.790125"
    assert replay["resolved_supply_basis"] == SUPPLY_BASIS_AUTHORITATIVE_RPC


@pytest.mark.parametrize(
    "label,mint",
    [
        ("CRAB", "849MT7F6MwVGjDtrbVD2Bt6RoUjwtJoM64Dasmuqpump"),
        ("Meatspin", "473iKvEcGgY4seyxqf9gxdXVQLr3yqaXGQFkMqL2pump"),
    ],
)
def test_incident_preboundary_diagnostics_never_become_supply_eligible(
    tmp_path, label, mint,
):
    """07_per_mint_trace rows remain diagnostic under live-only policy."""

    calls = []
    client, _ = _client(
        tmp_path,
        lambda url, payload, timeout: calls.append(payload) or _response(payload),
    )
    store = CentralAthStateStore(str(tmp_path / "ath"))
    bridge = AuthoritativeSupplyBridge(client=client, ath_store=store)
    incident = SimpleNamespace(
        token_mint=mint,
        live_epoch_id="epoch_f7038281e1de483f8071",
        # Diagnostic replay slot deliberately precedes authenticated boundary.
        migration_slot=9_999,
        token_name=label,
    )
    reason = bridge.observe_entry(
        incident,
        current_epoch_id="epoch_f7038281e1de483f8071",
        first_eligible_slot=10_000,
    )
    assert reason == SUPPLY_PENDING_PRE_BOUNDARY
    assert calls == []
    assert store.snapshot(mint) is None


def test_no_rpc_proof_means_no_conventional_billion_supply(tmp_path):
    client, _ = _client(
        tmp_path,
        lambda url, payload, timeout: (_ for _ in ()).throw(OSError("offline")),
    )
    store = CentralAthStateStore(str(tmp_path / "ath"))
    bridge = AuthoritativeSupplyBridge(client=client, ath_store=store)
    entry = SimpleNamespace(
        token_mint=MINT, live_epoch_id=EPOCH, migration_slot=101)
    assert bridge.observe_entry(
        entry, current_epoch_id=EPOCH, first_eligible_slot=100,
    ) == SUPPLY_PENDING_TRANSPORT
    store.observe_ohlcv_high(
        mint=MINT,
        high_price_usd="0.1",
        candle_timestamp="2026-08-03T01:00:00Z",
        history_complete=True,
        interval="1m",
        time_from_unix=1,
        time_to_unix=2,
    )
    snapshot = store.snapshot(MINT)
    assert snapshot is not None
    assert snapshot["resolved"] is False
    assert snapshot["resolved_supply"] is None
    assert snapshot["resolved_ath_market_cap"] is None
    assert "1000000000" not in json.dumps(snapshot)


def test_prior_epoch_supply_is_not_rebound_into_current_epoch(tmp_path):
    store = CentralAthStateStore(str(tmp_path / "ath"))
    assert store.observe_authoritative_supply(
        mint=MINT,
        raw_amount="111000",
        decimals=3,
        normalized_supply="111",
        rpc_context_slot=100,
        fetched_at_utc="2026-08-03T00:00:00Z",
        source="HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY",
        live_epoch_id="epoch_old",
        request_ticket_id="provider_old",
        validation_result=SUPPLY_VALID,
    )
    store.observe_ohlcv_high(
        mint=MINT,
        high_price_usd="2",
        candle_timestamp="2026-08-03T00:01:00Z",
        history_complete=True,
        interval="1m",
        time_from_unix=1,
        time_to_unix=2,
    )
    assert store.snapshot(MINT)["resolved"] is True

    assert store.bind_live_epoch("epoch_new") is True
    rebound = store.snapshot(MINT)
    assert rebound is not None
    assert rebound["resolved"] is False
    assert rebound["resolved_supply"] is None

    assert store.observe_authoritative_supply(
        mint=MINT,
        raw_amount="222000",
        decimals=3,
        normalized_supply="222",
        rpc_context_slot=200,
        fetched_at_utc="2026-08-03T00:02:00Z",
        source="HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY",
        live_epoch_id="epoch_new",
        request_ticket_id="provider_new",
        validation_result=SUPPLY_VALID,
    )
    current = store.snapshot(MINT)
    assert current is not None
    assert current["resolved"] is True
    assert current["resolved_supply"] == "222"


def test_supply_pending_and_systemic_failure_feed_canonical_health():
    transient = evaluate_authoritative_supply({
        "supply_systemic_failure": False,
        "supply_pending": 2,
        "supply_pending_reasons": {SUPPLY_PENDING_TRANSPORT: 2},
        "supply_oldest_pending_age_seconds": 10.0,
        "supply_systemic_pending_seconds": 900.0,
    })
    assert transient.verdict != DIM_UNHEALTHY

    systemic = evaluate_authoritative_supply({
        "supply_systemic_failure": True,
        "supply_pending": 2,
        "supply_pending_reasons": {SUPPLY_PENDING_TRANSPORT: 2},
        "supply_oldest_pending_age_seconds": 901.0,
        "supply_systemic_pending_seconds": 900.0,
    })
    assert systemic.verdict == DIM_UNHEALTHY
    record = {
        "operational_status": UNHEALTHY_AUTHORITATIVE_SUPPLY,
        "primary_cause": systemic.causes[0],
        "secondary_causes": [],
        "dimensions": [{
            "name": systemic.name,
            "verdict": systemic.verdict,
            "causes": systemic.causes,
            "detail": systemic.detail,
        }],
    }
    verdict = canonicalize_health(
        HealthVerdict(HEALTHY, ["all checks passed"]), record)
    assert verdict.health_class == UNHEALTHY_AUTHORITATIVE_SUPPLY
    assert verdict.control_health_class == RESTARTABLE_PROCESS_FAILURE

    transient_record = {
        "operational_status": DEGRADED_AUTHORITATIVE_SUPPLY,
        "primary_cause": transient.causes[0],
        "secondary_causes": [],
        "dimensions": [{
            "name": transient.name,
            "verdict": transient.verdict,
            "causes": transient.causes,
            "detail": transient.detail,
        }],
    }
    transient_verdict = canonicalize_health(
        HealthVerdict(HEALTHY, ["all checks passed"]), transient_record)
    assert transient_verdict.health_class == DEGRADED_AUTHORITATIVE_SUPPLY
    assert transient_verdict.stable is False


def test_canonical_helius_only_launcher_session_graph_drives_supply_before_ohlcv():
    argv = canonical_launcher_arguments(
        launcher="launch_pressure_24h_01.ps1",
        expected_head="a" * 40,
        ledger_baseline=("b" * 64) + ":9164:25",
    )
    assert CANONICAL_MIGRATION_SOURCE_MODE == helius_source.HELIUS_PRIMARY
    assert not any(str(token).startswith("--chainstack") for token in argv)
    plan = helius_source.build_production_source_runtime_plan(
        helius_source.load_source_selection(
            {helius_source.MIGRATION_SOURCE_ENV: helius_source.HELIUS_PRIMARY},
            explicit_mode=helius_source.HELIUS_PRIMARY,
        ),
        http_recovery_enabled=True,
    )
    assert plan.construct_helius_source is True
    assert plan.construct_chainstack_source is False
    assert plan.construct_chainstack_grpc_channel is False
    assert plan.source_owner_count == 1

    session_source = Path(
        "PHX2/free_tier_producer/free_tier_session.py").read_text(
            encoding="utf-8")
    assert "if helius_primary and helius_source_config is not None:" in session_source
    assert "HeliusTokenSupplyClient(" in session_source
    assert "AuthoritativeSupplyBridge(" in session_source
    cycle = session_source[session_source.index("    def on_cycle(**_kw):"):]
    assert cycle.index("_sweep_authoritative_supply()") < cycle.index(
        "_sweep_ath_hydration()")


class _ComposerMarketTransport:
    def __init__(self, mint: str, current_price: str) -> None:
        from PHX2.stage29.stage29_2_birdeye_models import (
            BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            BIRDEYE_REFUSAL_REASON_NONE,
        )

        self.mint = mint
        self.current_price = current_price
        self.none = BIRDEYE_REFUSAL_REASON_NONE
        self.timeout = BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        from PHX2.stage29.birdeye_constants import (
            BIRDEYE_PATH_OHLCV, BIRDEYE_PATH_PRICE,
        )
        from PHX2.stage29.stage29_2_birdeye_http_transport import (
            Stage29_2BirdeyeHttpResult,
        )

        if path == BIRDEYE_PATH_PRICE:
            body = {"success": True, "data": {
                "value": self.current_price,
                "updateUnixTime": 1_785_652_200,
            }}
        elif path == BIRDEYE_PATH_OHLCV:
            body = {"success": True, "data": {"items": [
                {"h": "10", "unixTime": 1_785_651_300},
                {"h": self.current_price, "unixTime": 1_785_652_140},
            ]}}
        else:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=self.timeout,
                http_status_code=0,
                body=None,
                fetched_at_utc="2026-08-02T06:29:50+00:00",
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=self.none,
            http_status_code=200,
            body=body,
            fetched_at_utc="2026-08-02T06:29:50+00:00",
        )


def _bridge_to_compose(tmp_path, *, mint: str, current_price: str):
    from PHX2.stage29.stage29_2_birdeye_readiness import (
        Stage29_2BirdeyeEndpointSecret,
    )
    from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
        make_constant_clock,
    )
    from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
        Stage30_11_5RecordingFakeTransportClient,
    )

    def post(url, payload, timeout):
        return _response(
            payload, mint=mint, amount="100000", decimals=2, slot=550)

    client, _meter = _client(tmp_path, post)
    store = CentralAthStateStore(str(tmp_path / "ath"))
    bridge = AuthoritativeSupplyBridge(client=client, ath_store=store)
    entry = SimpleNamespace(
        token_mint=mint, live_epoch_id=EPOCH, migration_slot=501)
    assert bridge.observe_entry(
        entry, current_epoch_id=EPOCH, first_eligible_slot=500,
    ) == SUPPLY_VALID
    # No pool registration and no reserve-stream observation exists: the
    # authenticated supply bridge alone makes this candle convertible.
    assert store.observe_ohlcv_high(
        mint=mint,
        high_price_usd="10",
        candle_timestamp="2026-08-02T06:15:00Z",
        history_complete=True,
        interval="1m",
        time_from_unix=1_785_651_300,
        time_to_unix=1_785_652_200,
    )
    central = store.snapshot(mint)
    assert central is not None and central["resolved"] is True
    current_mc = format(Decimal(current_price) * Decimal("1000"), "f")
    request = composer.Stage30_11_13RevalidationRequest(
        token_mint=mint,
        candidate_id=f"candidate_{mint[:8]}",
        migration_time_utc="2026-08-02T06:00:00Z",
        current_price=current_price,
        current_market_cap_usd=current_mc,
        created_at_utc="2026-08-02T06:30:00Z",
        migration_confirmed=True,
        symbol_or_name="SUPPLY",
        migration_source="HELIUS_AUTHENTICATED_LIVE_PROOF",
        liquidity_usd="9000",
        age_display="30m",
        market_context_status="PRESENT",
        market_context_fetched_at_utc="2026-08-02T06:29:50+00:00",
        authoritative_ath_price=central["ath_price"],
        authoritative_ath_market_cap_usd=central["ath_market_cap"],
        authoritative_ath_timestamp=central["ath_timestamp"],
        authoritative_ath_provider=central["ath_provider"],
        authoritative_ath_observation_type=central["ath_observation_type"],
        authoritative_ath_status=central["ath_status"],
        authoritative_ath_market_cap_evidence_price_usd=central[
            "ath_market_cap_evidence_price_usd"],
        ath_coverage=ATH_COVERAGE_COMPLETE_LIVE,
        resolved_ath_price=central["resolved_ath_price"],
        resolved_supply=central["resolved_supply"],
        resolved_supply_basis=central["resolved_supply_basis"],
        resolved_ath_market_cap_usd=central["resolved_ath_market_cap"],
        resolved_observed_at_utc=central["resolved_observed_at_utc"],
        resolved_ath_source=central["resolved_source"],
        resolved_ath_observation_type=central["resolved_observation_type"],
        resolved_ath_status=central["resolved_status"],
        resolved_evidence_digest=central["resolved_evidence_digest"],
        resolution_method=central["resolution_method"],
    )
    fake = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc="2026-08-02T06:30:00Z")
    result = composer.compose_no_send_dispatch(
        request,
        ath_transport=_ComposerMarketTransport(mint, current_price),
        ath_endpoint_secret=Stage29_2BirdeyeEndpointSecret(
            _api_key="abcd1234efgh5678ijkl9012mnop3456",
            _base_url="https://aaaa-bbbb.example",
        ),
        now_utc=datetime(2026, 8, 2, 6, 30, tzinfo=timezone.utc),
        transport_client=fake,
        now_seconds=make_constant_clock(Decimal(0)),
        market_context_max_age_seconds=3600,
    )
    return result, fake, central, current_mc


@pytest.mark.parametrize(
    "suffix,current_price,expected_tier,expected_drawdown_pct",
    [
        ("T1", "4.5", "Tier 1", Decimal("55")),
        ("T2", "3", "Tier 2", Decimal("70")),
        ("T3", "1", "Tier 3", Decimal("90")),
    ],
)
def test_production_supply_ohlcv_drawdown_tiers_reach_fake_compose(
    tmp_path, suffix, current_price, expected_tier, expected_drawdown_pct,
):
    mint = MINT
    result, fake, central, current_mc = _bridge_to_compose(
        tmp_path, mint=mint, current_price=current_price)
    assert central["resolved_supply_basis"] == SUPPLY_BASIS_AUTHORITATIVE_RPC
    calculated = (
        (Decimal(central["resolved_ath_market_cap"]) - Decimal(current_mc))
        / Decimal(central["resolved_ath_market_cap"]) * Decimal(100))
    assert calculated == expected_drawdown_pct
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, result.reason
    assert result.snapshot.tier_token == expected_tier
    assert fake.bodies
    assert f"CA: {mint}" in fake.bodies[-1]
