from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import threading
from types import SimpleNamespace

from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.authenticated_market_fallback import (
    FRESH_FALLBACK_ACCEPTED,
    FRESH_FALLBACK_ACCOUNT_DATA,
    FRESH_FALLBACK_CAPABILITY_UNAVAILABLE,
    AuthenticatedPumpSwapMarketFallback,
)
from PHX2.free_tier_producer.liquidity_integrity import b58decode, b58encode
from PHX2.free_tier_producer.market_budget import (
    ORIGIN_FALLBACK,
    PHYSICAL_FRESH_MARKET_FALLBACK,
    MarketPhysicalRequestMeter,
    reconcile,
)
from PHX2.free_tier_producer.market_plane_health import (
    MARKET_PLANE_BLIND,
    MARKET_PLANE_HEALTHY,
    MarketPlaneConfig,
    MarketPlaneWatch,
)
from PHX2.free_tier_producer.market_scheduler import (
    ACCEPTED_FRESH_OBSERVATION,
    ALREADY_IN_FLIGHT,
    BACKOFF_ACTIVE,
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    PRIORITY_REFRESH_RESULTS,
    MISSING_REQUIRED_FIELDS,
    OTHER_NAMED_RESULT,
    PROVIDER_ERROR,
    SOURCE_AUTHENTICATED_RESERVE_FALLBACK,
    STALE_PROVIDER_TIMESTAMP,
    WRONG_MINT,
    MarketScheduler,
    MarketSchedulerConfig,
)
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_PROOF_SOURCE,
    MIGRATION_PROOF_VERSION,
    PUMPFUN_PROGRAM_ID,
    MigrationProofSnapshot,
    MigrationProofStore,
    seal_migration_proof,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.free_tier_producer.pumpswap_reserves import (
    PUMPSWAP_POOL_ACCOUNT_DISCRIMINATOR,
)
from PHX2.free_tier_producer.source_continuity import NO_GAP
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    SPL_TOKEN_PROGRAM_ID,
    USDC_MINT,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.watchdog import operational_health as OH


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
EPOCH = "epoch_phase5"
NOW = 1_785_710_400.0
NOW_ISO = datetime.fromtimestamp(
    NOW, tz=timezone.utc).isoformat().replace("+00:00", "Z")
MINT_RAW = b58decode(MINT)
QUOTE_RAW = b58decode(USDC_MINT)
POOL_RAW = bytes(range(33, 65))
BASE_VAULT_RAW = bytes(range(65, 97))
QUOTE_VAULT_RAW = bytes(range(97, 129))
POOL = b58encode(POOL_RAW)
BASE_VAULT = b58encode(BASE_VAULT_RAW)
QUOTE_VAULT = b58encode(QUOTE_VAULT_RAW)


def _pool_account(*, virtual_quote: int = 2_000_000_000) -> bytes:
    body = bytearray(PUMPSWAP_POOL_ACCOUNT_DISCRIMINATOR)
    body.extend(b"\x01")
    body.extend((7).to_bytes(2, "little"))
    body.extend(bytes((1,)) * 32)  # creator
    body.extend(MINT_RAW)
    body.extend(QUOTE_RAW)
    body.extend(bytes((4,)) * 32)  # LP mint
    body.extend(BASE_VAULT_RAW)
    body.extend(QUOTE_VAULT_RAW)
    body.extend((123).to_bytes(8, "little"))
    body.extend(bytes((7,)) * 32)  # coin creator
    body.extend(b"\x00\x00")
    body.extend(int(virtual_quote).to_bytes(16, "little", signed=True))
    assert len(body) == 261
    return bytes(body)


def _token_account(mint_raw: bytes, amount: int) -> bytes:
    data = bytearray(165)
    data[:32] = mint_raw
    data[32:64] = bytes((9,)) * 32
    data[64:72] = int(amount).to_bytes(8, "little")
    data[108] = 1
    return bytes(data)


def _rpc_account(data: bytes, owner: str) -> dict:
    return {
        "data": [base64.b64encode(data).decode("ascii"), "base64"],
        "executable": False,
        "lamports": 1,
        "owner": owner,
        "rentEpoch": 0,
    }


def _proof() -> MigrationProofSnapshot:
    return seal_migration_proof(MigrationProofSnapshot(
        proof_version=MIGRATION_PROOF_VERSION,
        proof_source=MIGRATION_PROOF_SOURCE,
        candidate_mint=MINT,
        pool=POOL,
        base_mint=MINT,
        quote_mint=USDC_MINT,
        base_vault=BASE_VAULT,
        quote_vault=QUOTE_VAULT,
        migration_authority="migration_authority",
        migration_signature="migration_signature",
        migration_slot=101,
        outer_instruction_index=0,
        inner_instruction_index=0,
        flattened_instruction_index=1,
        pumpfun_program_id=PUMPFUN_PROGRAM_ID,
        pumpswap_program_id=PUMPSWAP_PROGRAM_ID,
        canonical_pda_valid=True,
        pool_creation_index_arg=0,
        vault_derivation_valid=True,
        vault_ownership_valid=True,
        quote_deposit_raw=10_000_000_000,
        quote_deposit_decimals=6,
        quote_deposit_sol="10000",
        base_deposit_raw=500_000_000_000,
        base_deposit_decimals=6,
        min_quote_deposit_sol="50",
        mint_suffix_consistent=True,
        observed_at_utc=NOW_ISO,
    ))


def _store() -> CentralAthStateStore:
    store = CentralAthStateStore()
    assert store.bind_live_epoch(EPOCH)
    assert store.observe_authoritative_supply(
        mint=MINT,
        raw_amount="1000000000000",
        decimals=6,
        normalized_supply="1000000",
        rpc_context_slot=100,
        fetched_at_utc=NOW_ISO,
        source="HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY",
        live_epoch_id=EPOCH,
        request_ticket_id="supply_ticket",
        validation_result="SUPPLY_VALID",
    )
    return store


class _RpcFixture:
    def __init__(self, *, malformed_pool: bool = False) -> None:
        self.calls = 0
        self.malformed_pool = malformed_pool

    def __call__(self, _url, payload, _timeout):
        self.calls += 1
        pool = b"bad" if self.malformed_pool else _pool_account()
        return 200, {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {
                "context": {"slot": 222},
                "value": [
                    _rpc_account(pool, PUMPSWAP_PROGRAM_ID),
                    _rpc_account(
                        _token_account(MINT_RAW, 500_000_000_000),
                        SPL_TOKEN_PROGRAM_ID),
                    _rpc_account(
                        _token_account(QUOTE_RAW, 10_000_000_000),
                        SPL_TOKEN_PROGRAM_ID),
                ],
            },
        }


def _fallback(
    tmp_path: Path, *, malformed_pool: bool = False,
) -> tuple[AuthenticatedPumpSwapMarketFallback, MarketPhysicalRequestMeter, _RpcFixture]:
    proofs = MigrationProofStore()
    assert proofs.seal_and_store(_proof())
    meter = MarketPhysicalRequestMeter(
        ticket_artifact=tmp_path / "tickets.jsonl")
    rpc = _RpcFixture(malformed_pool=malformed_pool)
    fallback = AuthenticatedPumpSwapMarketFallback(
        rpc_base_url="https://rpc.invalid",
        api_key="offline-fixture-key",
        proof_store=proofs,
        ath_store=_store(),
        quote_price_fn=None,
        physical_request_meter=meter,
        post_fn=rpc,
        artifact_path=tmp_path / "fallback.jsonl",
        now_fn=lambda: NOW,
    )
    return fallback, meter, rpc


class _InnerBirdeye:
    def __init__(self, provider_epoch: float) -> None:
        self.provider_epoch = provider_epoch

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        del endpoint_secret, timeout_seconds
        if path == BIRDEYE_PATH_PRICE:
            data = {
                "address": query_params["address"],
                "value": "0.024",
                "updateUnixTime": self.provider_epoch,
            }
        else:
            data = {
                "address": query_params["address"],
                "marketCap": "24000",
                "liquidity": "22000",
                "updateUnixTime": self.provider_epoch,
            }
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body={"success": True, "data": data},
            fetched_at_utc=NOW_ISO,
        )


def _birdeye(provider_epoch: float, meter=None) -> PaidBirdeyeMarketTransport:
    return PaidBirdeyeMarketTransport(
        inner_transport=_InnerBirdeye(provider_epoch),
        endpoint_secret=object(),
        min_interval_seconds=0,
        cache_ttl_seconds=0,
        max_attempts=1,
        max_data_age_seconds=300,
        now_fn=lambda: NOW,
        monotonic_fn=lambda: NOW,
        sleep_fn=lambda _seconds: None,
        physical_request_meter=meter,
    )


def _entry() -> SimpleNamespace:
    return SimpleNamespace(
        token_mint=MINT,
        candidate_id="candidate-phase5",
        generation=1,
        status="ACTIVE_DIP_WATCH",
        seeded_at_utc=NOW_ISO,
        migration_time_utc=NOW_ISO,
        market_state=None,
        market_reason_code=None,
        last_observed_at_utc=None,
        next_market_refresh_at_utc=None,
        activation_target_market_cap_usd=None,
        last_activation_progress_market_cap_usd=None,
        delivery_retry_at_utc=None,
        market_compose_near=False,
        market_scheduler_quarantined=False,
        market_terminal_history=False,
    )


def test_fresh_birdeye_provider_timestamp_is_accepted() -> None:
    transport = _birdeye(NOW - 10)
    result = transport.fetch_price_plane(MINT)
    assert result is not None
    assert result["current_price"] == "0.024"
    assert result["provider_timestamp_utc"] == datetime.fromtimestamp(
        NOW - 10, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert "_market_failure_reason" not in result


def test_priority_refresh_result_contract_is_exact_and_closed() -> None:
    assert PRIORITY_REFRESH_RESULTS == (
        ACCEPTED_FRESH_OBSERVATION,
        STALE_PROVIDER_TIMESTAMP,
        PROVIDER_ERROR,
        BACKOFF_ACTIVE,
        ALREADY_IN_FLIGHT,
        MISSING_REQUIRED_FIELDS,
        WRONG_MINT,
        OTHER_NAMED_RESULT,
    )


def test_stale_birdeye_is_rejected_with_exact_persisted_evidence(tmp_path) -> None:
    meter = MarketPhysicalRequestMeter(
        ticket_artifact=tmp_path / "tickets.jsonl")
    transport = _birdeye(NOW - 900, meter=meter)
    result = transport.fetch_price_plane(MINT)
    assert result is not None
    assert result["_market_failure_reason"] == "PROVIDER_STALE"
    endpoint = transport.market_diagnostic(MINT)["endpoints"][BIRDEYE_PATH_PRICE]
    assert endpoint["state"] == "MARKET_STALE"
    assert endpoint["provider_timestamp_utc"] != endpoint["fetched_at_utc"]
    assert endpoint["provider_age_seconds"] == 900
    assert endpoint["configured_freshness_ttl_seconds"] == 300
    assert endpoint["endpoint"] == BIRDEYE_PATH_PRICE
    assert endpoint["request_ticket_id"].startswith("provider_")
    assert endpoint["rejection_reason"] == "PRICE_PROVIDER_TIMESTAMP_STALE"
    assert endpoint["stale_responses"][0]["provider_timestamp_utc"] \
        == endpoint["provider_timestamp_utc"]
    persisted = transport.stats()["stale_provider_responses"]
    assert persisted == [{"mint": MINT, **endpoint["stale_responses"][0]}]
    ticket = meter.snapshot()
    assert ticket["rejected_observations"] == 1
    assert ticket["accepted_observations"] == 0


def test_authenticated_snapshot_reuses_virtual_reserve_and_is_coherent(tmp_path) -> None:
    fallback, meter, rpc = _fallback(tmp_path)
    result = fallback.fetch(MINT)
    assert result.accepted
    assert result.reason == FRESH_FALLBACK_ACCEPTED
    assert rpc.calls == 1
    observation = dict(result.observation or {})
    assert observation["current_price"] == "0.024"
    assert observation["current_market_cap_usd"] == "24000.000"
    assert observation["liquidity_usd"] == "22000.000"
    reserve = observation["pumpswap_reserve"]
    assert reserve["raw_quote_reserves"] == "10000000000"
    assert reserve["virtual_quote_reserves"] == "2000000000"
    assert reserve["effective_quote_reserves"] == "12000000000"
    assert reserve["authoritative_supply_record"]["normalized_supply"] == "1000000"
    assert reserve["account_context_slot"] == 222
    assert reserve["program_id"] == PUMPSWAP_PROGRAM_ID
    assert reserve["request_ticket_ids"] == list(result.request_ticket_ids)
    snapshot = meter.snapshot()
    assert snapshot["physical_by_category"][PHYSICAL_FRESH_MARKET_FALLBACK] == 1
    assert snapshot["physical_by_origin"][ORIGIN_FALLBACK] == 1
    assert snapshot["accepted_observations"] == 1


def test_malformed_authenticated_snapshot_is_named_and_rejected(tmp_path) -> None:
    fallback, meter, _rpc = _fallback(tmp_path, malformed_pool=True)
    result = fallback.fetch(MINT)
    assert not result.accepted
    assert result.reason == FRESH_FALLBACK_ACCOUNT_DATA
    assert meter.snapshot()["rejected_observations"] == 1


def test_stale_primary_then_authenticated_fallback_is_same_evaluation(tmp_path) -> None:
    fallback, meter, _rpc = _fallback(tmp_path)
    primary = _birdeye(NOW - 900)
    scheduler = MarketScheduler(
        price_fetch_fn=primary.fetch_price_plane,
        overview_fetch_fn=primary.fetch_overview_plane,
        config=MarketSchedulerConfig(
            worker_count=1, max_inflight=1, p1_reserved_workers=0),
        now_fn=lambda: NOW,
        monotonic_fn=lambda: NOW,
        fresh_fallback_fetch_fn=fallback.fetch,
        physical_request_meter=meter,
    )
    scheduler.update_candidates([_entry()], now_epoch=NOW)
    result = scheduler.priority_refresh(MINT)
    assert result["priority_refresh_result"] == ACCEPTED_FRESH_OBSERVATION
    assert result["priority_refresh_result"] in PRIORITY_REFRESH_RESULTS
    assert result["all_present"] is True
    assert result["current_price"] == "0.024"
    assert result["current_market_cap_usd"] == "24000"
    assert result["liquidity_usd"] == "22000"
    assert result["market_pair_coherent"] is True
    assert result["price_source"] == SOURCE_AUTHENTICATED_RESERVE_FALLBACK
    assert result["market_cap_source"] == SOURCE_AUTHENTICATED_RESERVE_FALLBACK
    assert result["liquidity_source"] == SOURCE_AUTHENTICATED_RESERVE_FALLBACK
    # An independent read in this exact caller cycle sees the same fields.
    assert scheduler.snapshot(MINT)["pumpswap_reserve"][
        "virtual_quote_reserves"] == "2000000000"
    accounting = reconcile(
        scheduler_physical_requests_total=scheduler.stats()[
            "scheduler_physical_requests_total"], meter=meter)
    assert accounting["unreconciled_delta"] == 0
    assert accounting["reconciled"] is True


def test_scheduled_stale_primary_also_uses_authenticated_fallback(tmp_path) -> None:
    fallback, meter, _rpc = _fallback(tmp_path)
    primary = _birdeye(NOW - 900)
    complete = threading.Event()

    def applied(_observation, snapshot):
        if snapshot.get("all_present"):
            complete.set()

    scheduler = MarketScheduler(
        price_fetch_fn=primary.fetch_price_plane,
        overview_fetch_fn=primary.fetch_overview_plane,
        config=MarketSchedulerConfig(
            worker_count=2, max_inflight=2, p1_reserved_workers=0),
        now_fn=lambda: NOW,
        monotonic_fn=lambda: NOW,
        apply_callback=applied,
        fresh_fallback_fetch_fn=fallback.fetch,
        physical_request_meter=meter,
    )
    scheduler.update_candidates([_entry()], now_epoch=NOW)
    scheduler.start()
    try:
        assert len(scheduler.plan(now_epoch=NOW)) == 2
        assert complete.wait(timeout=3)
        snapshot = scheduler.snapshot(MINT)
        assert snapshot["all_present"] is True
        assert snapshot["price_source"] == SOURCE_AUTHENTICATED_RESERVE_FALLBACK
        assert snapshot["pumpswap_reserve"]["account_context_slot"] == 222
        assert scheduler.stats()["fresh_market_fallback_succeeded_total"] == 1
        accounting = reconcile(
            scheduler_physical_requests_total=scheduler.stats()[
                "scheduler_physical_requests_total"], meter=meter)
        assert accounting["reconciled"] is True
        assert accounting["unreconciled_delta"] == 0
    finally:
        assert scheduler.stop(timeout_seconds=3)


def test_no_fallback_capability_is_explicit_not_generic() -> None:
    primary = _birdeye(NOW - 900)
    scheduler = MarketScheduler(
        price_fetch_fn=primary.fetch_price_plane,
        overview_fetch_fn=primary.fetch_overview_plane,
        config=MarketSchedulerConfig(
            worker_count=1, max_inflight=1, p1_reserved_workers=0),
        now_fn=lambda: NOW,
        monotonic_fn=lambda: NOW,
    )
    scheduler.update_candidates([_entry()], now_epoch=NOW)
    result = scheduler.priority_refresh(MINT)
    assert result["priority_refresh_result"] == STALE_PROVIDER_TIMESTAMP
    assert result["priority_refresh_detail"] \
        == FRESH_FALLBACK_CAPABILITY_UNAVAILABLE
    assert result["priority_refresh_detail"] != "PRIORITY_REFRESH_NO_OBSERVATION"
    stats = scheduler.stats()
    assert stats["fresh_market_fallback_capability_available"] is False
    assert stats["fresh_market_fallback_capability_unavailable_total"] == 1


def test_persistent_primary_and_fallback_failure_reaches_canonical_unhealthy() -> None:
    watch = MarketPlaneWatch(MarketPlaneConfig(
        grace_seconds=10,
        no_refresh_bound_seconds=10,
        stale_observation_seconds=10,
        priority_rejection_streak=2,
    ))
    watch.observe(
        now_monotonic=0, active_candidates=1,
        successful_refresh_total=0,
        priority_refresh_attempts_total=2,
        priority_refresh_served_total=0,
        max_observation_age_seconds=20,
    )
    plane = watch.observe(
        now_monotonic=11, active_candidates=1,
        successful_refresh_total=0,
        priority_refresh_attempts_total=3,
        priority_refresh_served_total=0,
        max_observation_age_seconds=31,
    )
    assert plane.status == MARKET_PLANE_BLIND
    telemetry = {
        "transport_connected": True,
        "source_continuity_state": NO_GAP,
        "unreconciled_delta": 0,
        "scheduler_charge_delta": 0,
        "supply_systemic_failure": False,
        "supply_pending": 0,
        **plane.to_record(),
    }
    verdict = OH.evaluate_operational_health(
        telemetry=telemetry,
        watchlist_summary={},
        scheduler_state="SCHEDULER_READY",
        epoch_healthy=True,
    )
    assert verdict.status == OH.UNHEALTHY_MARKET_PLANE_BLIND
    assert next(d for d in verdict.dimensions if d.name == "market_plane").verdict \
        == OH.DIM_UNHEALTHY


def test_temporary_stale_primary_with_working_fallback_remains_healthy(tmp_path) -> None:
    fallback, _meter, _rpc = _fallback(tmp_path)
    assert fallback.fetch(MINT).accepted
    watch = MarketPlaneWatch(MarketPlaneConfig(grace_seconds=10))
    plane = watch.observe(
        now_monotonic=1,
        active_candidates=1,
        successful_refresh_total=1,
        priority_refresh_attempts_total=1,
        priority_refresh_served_total=1,
        max_observation_age_seconds=0,
    )
    assert plane.status == MARKET_PLANE_HEALTHY


def test_session_graph_wires_authenticated_fallback_without_chainstack() -> None:
    source = Path(
        "PHX2/free_tier_producer/free_tier_session.py").read_text(
            encoding="utf-8")
    assert "AuthenticatedPumpSwapMarketFallback(" in source
    assert "proof_store=proof_store" in source
    assert "ath_store=ath_store" in source
    assert "quote_price_fn=reserve_index.quote_price_snapshot" in source
    assert "fresh_fallback_fetch_fn=" in source
    assert "fresh_market_fallback.fetch" in source
    assert "CHAINSTACK" not in source[source.index(
        "AuthenticatedPumpSwapMarketFallback("):
        source.index("AuthenticatedPumpSwapMarketFallback(") + 900]
