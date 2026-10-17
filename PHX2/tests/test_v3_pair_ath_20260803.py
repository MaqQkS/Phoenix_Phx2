"""Birdeye V3 pair-history post-migration ATH regression suite (2026-08-03).

The specification is the last real alert (mint ``5MAse…pump``, sent
2026-08-03T17:18:11Z): the displayed Post-mig ATH ($24,536.29) came from
token-level 1m `/defi/ohlcv` candles whose migration-second ``time_from``
silently dropped the partial first candle -- the candle holding the literal
peak (17:15:36Z).  The canonical corrected value is the validated USD high of
the authenticated migration PAIR's V3 candles: $31,997.87.

Every candle value in the shared fixture is verbatim recorded provider
output from the 2026-08-03 capability probe against that exact pair.
"""

from __future__ import annotations

import itertools
import json
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pytest

from PHX2.free_tier_producer.ath_state import (
    ATH_LIVE_TRACKER_ANCHOR_TOLERANCE_SECONDS,
    CentralAthStateStore,
    SOURCE_PAID_V3_PAIR,
    resolved_market_cap_from,
)
from PHX2.free_tier_producer.market_budget import (
    ATH_V3_REQUEST_ORIGINS,
    MarketPhysicalRequestMeter,
    ORIGIN_ATH_V3_PAIR_COARSE,
    ORIGIN_ATH_V3_PAIR_INCREMENTAL,
    ORIGIN_ATH_V3_PAIR_REFINE,
    ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC,
    reconcile,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.models.ath_coverage import (
    ATH_CANONICAL_SOURCE_LIVE_TRACKER,
    ATH_CANONICAL_SOURCE_V3_PAIR,
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_HYDRATION_COMPLETE,
    ATH_HYDRATION_PENDING,
    ATH_V3_PENDING_REASONS,
    ATH_V3_RATE_LIMITED,
    classify_ath_coverage,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_V3_PAIR_OHLCV,
    BIRDEYE_PATH_V3_TOKEN_OHLCV,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage30 import stage30_11_13_committed_no_send_composer as composer

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "v3_pair_ath_last_alert_20260803.json")
FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

MINT = FIXTURE["token_mint"]
PAIR = FIXTURE["pair_address"]
QUOTE = FIXTURE["quote_mint"]
MIGRATION_ISO = FIXTURE["migration_time_utc"]
MIGRATION_UNIX = FIXTURE["migration_unix"]
ANCHOR_ALIGNED = (MIGRATION_UNIX // 15) * 15          # 1785777315
NOW_UNIX = FIXTURE["send_unix"]                        # 1785777491
NOW_ISO = FIXTURE["send_time_utc"]
EPOCH_ID = "epoch_v3_regression_0001"
SUPPLY = FIXTURE["authoritative_supply"]
SUPPLY_DECIMAL = Decimal(SUPPLY["normalized_supply"])
CORRECTED = FIXTURE["corrected"]
OLD_ALERT = FIXTURE["old_alert"]
TRACKING_STARTED = "2026-08-03T17:15:30Z"              # within 90s of anchor


def _slice(series: List[dict], time_from: int, time_to: int,
           address: str) -> List[dict]:
    """Emulate the probed provider range semantics: candles with
    ``time_from <= unix_time <= time_to`` (a candle starting before
    ``time_from`` is NOT returned -- the exact behaviour that dropped the
    migration-minute candle from the old evidence)."""

    out = []
    for row in series:
        when = row.get("unix_time", row.get("unixTime"))
        if when is None or when < time_from or when > time_to:
            continue
        item = {"unix_time": when, "address": address, "h": row["h"]}
        for key in ("o", "l", "c", "v", "v_usd"):
            if key in row:
                item[key] = row[key]
        out.append(item)
    return out


class FakeV3Inner:
    """Deterministic Birdeye fake serving the recorded probe evidence."""

    def __init__(self, *, fail: Optional[Dict[str, int]] = None,
                 token_series_1s: Optional[List[dict]] = None,
                 pair_extra_candles: Optional[List[dict]] = None) -> None:
        #: path (or "path|type") -> HTTP status to fail with.
        self.fail = dict(fail or {})
        self.calls: List[Dict[str, Any]] = []
        self._token_1s = token_series_1s or FIXTURE["token_1s_usd"]
        self._pair_extra = list(pair_extra_candles or ())

    def _refused(self, status: int) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
            http_status_code=status, body=None,
            fetched_at_utc="2026-08-03T17:18:11+00:00")

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        params = dict(query_params)
        self.calls.append({"path": path, "params": params})
        interval = params.get("type")
        for key in (f"{path}|{interval}", path):
            if key in self.fail:
                return self._refused(int(self.fail[key]))
        time_from = int(params.get("time_from", 0) or 0)
        time_to = int(params.get("time_to", 0) or 0)
        requested_address = str(params.get("address") or "")
        if path == BIRDEYE_PATH_V3_PAIR_OHLCV:
            series = (FIXTURE["pair_15s_native"] if interval == "15s"
                      else FIXTURE["pair_1s_native"])
            items = _slice(series, time_from, time_to, requested_address)
            if interval == "15s" and self._pair_extra:
                # A deliberately MISBEHAVING provider: candles outside the
                # requested range are appended verbatim so the transport's
                # window validation is what the test exercises.
                items = [dict(row, address=requested_address)
                         for row in self._pair_extra] + items
        elif path == BIRDEYE_PATH_V3_TOKEN_OHLCV:
            series = (FIXTURE["token_15s_usd"] if interval == "15s"
                      else self._token_1s)
            items = _slice(series, time_from, time_to, requested_address)
        elif path == BIRDEYE_PATH_OHLCV:
            items = _slice(FIXTURE["token_1m_v1_old_evidence"],
                           time_from, time_to, MINT)
        elif path == BIRDEYE_PATH_PRICE:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body={"success": True, "data": {
                    "value": OLD_ALERT["current_price"],
                    "updateUnixTime": NOW_UNIX}},
                fetched_at_utc="2026-08-03T17:18:11+00:00")
        else:
            return self._refused(404)
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body={"success": True, "data": {"items": items}},
            fetched_at_utc="2026-08-03T17:18:11+00:00")


def make_store(path=None, *, epoch: Optional[str] = EPOCH_ID,
               now_iso: str = NOW_ISO) -> CentralAthStateStore:
    store = CentralAthStateStore(path, hydration_now_fn=lambda: now_iso)
    if epoch is not None:
        assert store.bind_live_epoch(epoch)
    return store


def seed_candidate(store: CentralAthStateStore, *, mint: str = MINT,
                   pair: str = PAIR, supply: bool = True,
                   epoch: str = EPOCH_ID) -> None:
    assert store.register_migration_pair(
        mint=mint, pool_address=pair, quote_mint=QUOTE,
        anchor_utc=MIGRATION_ISO,
        tracking_started_at_utc=TRACKING_STARTED)
    store.schedule_hydration(mint, anchor_utc=MIGRATION_ISO,
                             scheduled_at_utc=TRACKING_STARTED)
    if supply:
        assert store.observe_authoritative_supply(
            mint=mint,
            raw_amount=SUPPLY["raw_amount"],
            decimals=SUPPLY["decimals"],
            normalized_supply=SUPPLY["normalized_supply"],
            rpc_context_slot=SUPPLY["rpc_context_slot"],
            fetched_at_utc="2026-08-03T17:16:08Z",
            source=SUPPLY["source"],
            live_epoch_id=epoch,
            request_ticket_id=f"provider_seed_{mint[:8]}",
            validation_result="SUPPLY_VALID",
        )


def make_transport(store, *, inner=None, meter=None, page_candles: int = 900,
                   ohlcv_ttl: float = 0.0,
                   mono_step: float = 0.25) -> PaidBirdeyeMarketTransport:
    mono = itertools.count(start=1)
    return PaidBirdeyeMarketTransport(
        inner_transport=inner if inner is not None else FakeV3Inner(),
        endpoint_secret=object(),
        min_interval_seconds=0.0,
        cache_ttl_seconds=0.0,
        ohlcv_cache_ttl_seconds=ohlcv_ttl,
        max_attempts=1,
        backoff_seconds=(),
        now_fn=lambda: float(NOW_UNIX),
        monotonic_fn=lambda: float(next(mono)) * mono_step,
        sleep_fn=lambda _s: None,
        ath_store=store,
        v3_page_candles=page_candles,
        physical_request_meter=meter,
    )


def hydrate(store, *, inner=None, meter=None, page_candles: int = 900):
    transport = make_transport(store, inner=inner, meter=meter,
                               page_candles=page_candles)
    outcome = transport.refresh_ath_history(MINT, timeout_seconds=5)
    return transport, outcome


# ---------------------------------------------------------------------------
# 1-2: pair identity + pre-migration exclusion
# ---------------------------------------------------------------------------

def test_01_exact_migration_pair_is_used() -> None:
    store = make_store()
    seed_candidate(store)
    inner = FakeV3Inner()
    _, outcome = hydrate(store, inner=inner)
    assert outcome["complete"] is True
    pair_calls = [c for c in inner.calls
                  if c["path"] == BIRDEYE_PATH_V3_PAIR_OHLCV]
    assert pair_calls, "no pair request was made"
    assert all(c["params"]["address"] == PAIR for c in pair_calls)
    v3 = store.v3_pair_state(MINT)
    assert v3["pair_address"] == PAIR
    assert v3["quote_mint"] == QUOTE


def test_02_pre_migration_candles_are_excluded() -> None:
    """A candle before the anchored window start poisons nothing."""

    store = make_store()
    seed_candidate(store)
    rogue = [{"unix_time": ANCHOR_ALIGNED - 15, "h": 999.0}]
    inner = FakeV3Inner(pair_extra_candles=rogue)
    _, outcome = hydrate(store, inner=inner)
    # The provider violated the requested range: the page fails closed with
    # a named reason and the rogue high never becomes an observation.
    assert outcome["complete"] is False
    assert outcome["reason"] in ATH_V3_PENDING_REASONS
    snap = store.snapshot(MINT)
    assert snap is None or snap.get("ath_price") is None
    # First coarse request itself began AT the aligned anchor, never later.
    first = next(c for c in inner.calls
                 if c["path"] == BIRDEYE_PATH_V3_PAIR_OHLCV)
    assert int(first["params"]["time_from"]) == ANCHOR_ALIGNED


# ---------------------------------------------------------------------------
# 3-4: inversion validation
# ---------------------------------------------------------------------------

def test_03_correct_inversion_derived_from_pool_identity() -> None:
    store = make_store()
    seed_candidate(store)
    _, outcome = hydrate(store)
    assert outcome["complete"] is True
    v3 = store.v3_pair_state(MINT)
    usd = v3["usd_peak"]
    assert usd["validated"] is True
    assert usd["method"] == "SAME_SECOND_PROVIDER_USD"
    ratio = Decimal(usd["implied_quote_usd"])
    # The implied WSOL/USD rate of the NON-inverted orientation (~73.6).
    assert Decimal("50") < ratio < Decimal("120")


def test_04_wrong_inversion_fails_with_named_reason() -> None:
    inverted = [{"unix_time": row["unix_time"],
                 "h": 1.0 / row["h"]}
                for row in FIXTURE["token_1s_usd"]]
    store = make_store()
    seed_candidate(store)
    _, outcome = hydrate(store, inner=FakeV3Inner(token_series_1s=inverted))
    assert outcome["reason"] == "ATH_V3_INVERSION_UNRESOLVED"
    hydration = store.hydration(MINT)
    assert hydration["status"] == ATH_HYDRATION_PENDING
    assert hydration["reason"] == "ATH_V3_INVERSION_UNRESOLVED"


# ---------------------------------------------------------------------------
# 5-7: coarse peak, refinement, refinement fallback
# ---------------------------------------------------------------------------

def test_05_coarse_15s_peak_is_found() -> None:
    store = make_store()
    seed_candidate(store)
    hydrate(store)
    v3 = store.v3_pair_state(MINT)
    assert v3["coarse_peak"]["unix_time"] == CORRECTED["coarse_peak_unix"]
    assert Decimal(v3["coarse_peak"]["native_high"]) == Decimal(
        CORRECTED["coarse_native_high"])


def test_06_peak_is_refined_with_1s_candles() -> None:
    store = make_store()
    seed_candidate(store)
    hydrate(store)
    v3 = store.v3_pair_state(MINT)
    refined = v3["refined_peak"]
    assert refined["refined"] is True
    assert refined["interval"] == "1s"
    assert refined["unix_time"] == CORRECTED["refined_peak_unix"]
    assert Decimal(refined["native_high"]) == Decimal(
        CORRECTED["pair_native_high"])


def test_07_no_1s_data_retains_valid_coarse_precision() -> None:
    store = make_store()
    seed_candidate(store)
    inner = FakeV3Inner(fail={f"{BIRDEYE_PATH_V3_PAIR_OHLCV}|1s": 404})
    _, outcome = hydrate(store, inner=inner)
    assert outcome["complete"] is True
    v3 = store.v3_pair_state(MINT)
    refined = v3["refined_peak"]
    assert refined["refined"] is False
    assert refined["interval"] == "15s"
    assert Decimal(refined["native_high"]) == Decimal(
        CORRECTED["coarse_native_high"])
    # Valued from the provider's 15s USD candle of the SAME bucket.
    usd = v3["usd_peak"]
    assert usd["interval"] == "15s"
    assert Decimal(usd["price_usd"]) == Decimal(CORRECTED["usd_high"])


# ---------------------------------------------------------------------------
# 8-11: request shape, chunking, idempotence, incremental
# ---------------------------------------------------------------------------

def test_08_padded_candles_are_never_requested() -> None:
    store = make_store()
    seed_candidate(store)
    inner = FakeV3Inner()
    hydrate(store, inner=inner)
    v3_calls = [c for c in inner.calls if c["path"] in (
        BIRDEYE_PATH_V3_PAIR_OHLCV, BIRDEYE_PATH_V3_TOKEN_OHLCV)]
    assert v3_calls
    for call in v3_calls:
        assert call["params"]["padding"] == "false"
        assert call["params"]["mode"] == "range"
        assert "outlier" not in call["params"]


def test_09_long_ranges_are_chunked_without_gaps() -> None:
    store = make_store()
    seed_candidate(store)
    inner = FakeV3Inner()
    _, outcome = hydrate(store, inner=inner, page_candles=4)
    assert outcome["complete"] is True
    coarse = [c["params"] for c in inner.calls
              if c["path"] == BIRDEYE_PATH_V3_PAIR_OHLCV
              and c["params"]["type"] == "15s"]
    assert len(coarse) >= 3
    assert int(coarse[0]["time_from"]) == ANCHOR_ALIGNED
    for previous, current in zip(coarse, coarse[1:]):
        assert int(current["time_from"]) == int(previous["time_to"]) + 1
    assert int(coarse[-1]["time_to"]) == NOW_UNIX


def test_10_duplicate_boundary_candles_are_idempotent() -> None:
    store = make_store()
    seed_candidate(store)
    transport = make_transport(store)
    first = transport.refresh_ath_history(MINT, timeout_seconds=5)
    snap_first = store.snapshot(MINT)
    second = transport.refresh_ath_history(MINT, timeout_seconds=5)
    snap_second = store.snapshot(MINT)
    assert first["complete"] is True and second["complete"] is True
    for key in ("resolved_ath_price", "resolved_ath_market_cap",
                "resolved_supply", "ath_timestamp", "ath_evidence_digest"):
        assert snap_first[key] == snap_second[key]
    v3 = store.v3_pair_state(MINT)
    assert v3["refined_peak"]["unix_time"] == CORRECTED["refined_peak_unix"]


def test_11_incremental_hydration_begins_after_last_accepted_candle() -> None:
    store = make_store()
    seed_candidate(store)
    inner = FakeV3Inner()
    meter = MarketPhysicalRequestMeter()
    transport = make_transport(store, inner=inner, meter=meter)
    assert transport.refresh_ath_history(MINT, timeout_seconds=5)["complete"]
    cursor = store.v3_pair_state(MINT)["cursor_unix"]
    calls_before = len(inner.calls)
    transport.refresh_ath_history(MINT, timeout_seconds=5)
    incremental = [c["params"] for c in inner.calls[calls_before:]
                   if c["path"] == BIRDEYE_PATH_V3_PAIR_OHLCV
                   and c["params"]["type"] == "15s"]
    assert incremental, "no incremental request was made"
    assert int(incremental[0]["time_from"]) == cursor + 15
    snapshot = meter.snapshot()
    assert snapshot["physical_by_origin"][ORIGIN_ATH_V3_PAIR_INCREMENTAL] >= 1


# ---------------------------------------------------------------------------
# 12-14: labeling, Decimal arithmetic, wrong-mint supply
# ---------------------------------------------------------------------------

def test_12_literal_and_filtered_ath_are_labeled_distinctly() -> None:
    """The probe proved outlier unset/true/false byte-identical for this
    pair, so production pins the provider default and records the mode: the
    retained value IS the literal chart ATH.  A filtered variant, were the
    provider ever to diverge, would carry a different mode token -- the two
    can never be conflated under one label."""

    store = make_store()
    seed_candidate(store)
    hydrate(store)
    v3 = store.v3_pair_state(MINT)
    assert v3["outlier_mode"] == "PROVIDER_DEFAULT_UNSET"
    hydration = store.hydration(MINT)
    assert hydration["v3_outlier_mode"] == "PROVIDER_DEFAULT_UNSET"
    # The canonical resolved tuple is the literal peak, not a filtered one.
    snap = store.snapshot(MINT)
    assert Decimal(snap["resolved_ath_price"]) == Decimal(
        CORRECTED["usd_high"])


def test_13_decimal_supply_multiplication_is_exact() -> None:
    store = make_store()
    seed_candidate(store)
    hydrate(store)
    snap = store.snapshot(MINT)
    price = Decimal(snap["resolved_ath_price"])
    supply = Decimal(snap["resolved_supply"])
    market_cap = Decimal(snap["resolved_ath_market_cap"])
    assert supply == SUPPLY_DECIMAL
    assert market_cap == resolved_market_cap_from(price, supply)
    assert snap["resolved_ath_market_cap"] == CORRECTED["ath_market_cap"]


def test_14_wrong_mint_supply_is_rejected() -> None:
    other_mint = "9" * 40 + "pump"
    store = make_store()
    seed_candidate(store, supply=False)
    # Authoritative supply recorded for a DIFFERENT mint only.
    assert store.observe_authoritative_supply(
        mint=other_mint, raw_amount="1000000000000000", decimals=6,
        normalized_supply="1000000000", rpc_context_slot=1,
        fetched_at_utc=NOW_ISO,
        source="HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY",
        live_epoch_id=EPOCH_ID, request_ticket_id="provider_wrongmint",
        validation_result="SUPPLY_VALID")
    _, outcome = hydrate(store)
    # Coverage completes but the tuple cannot resolve without OUR supply.
    hydration = store.hydration(MINT)
    assert hydration["status"] == ATH_HYDRATION_PENDING
    assert hydration["reason"] == "ATH_HYDRATION_MARKET_CAP_UNCONVERTED"
    assert store.authoritative_supply_record(MINT) is None


# ---------------------------------------------------------------------------
# compose harness (15-18, 26)
# ---------------------------------------------------------------------------

class _ComposeFreshnessTransport:
    """Serves the composer's independent V1 anchored freshness gate."""

    def __init__(self, *, current_price: str, ath_price: str) -> None:
        self._current = current_price
        self._ath = ath_price
        self.calls: List[str] = []

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        self.calls.append(path)
        if path == BIRDEYE_PATH_PRICE:
            body = {"success": True, "data": {
                "value": self._current, "updateUnixTime": NOW_UNIX}}
        elif path == BIRDEYE_PATH_OHLCV:
            body = {"success": True, "data": {"items": [
                {"h": self._ath, "unixTime": NOW_UNIX - 120},
                {"h": self._current, "unixTime": NOW_UNIX - 60},
            ]}}
        else:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
                http_status_code=404, body=None,
                fetched_at_utc="2026-08-03T17:18:11+00:00")
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200, body=body,
            fetched_at_utc="2026-08-03T17:18:11+00:00")


def _compose_from_store(store, *, current_market_cap: Decimal):
    from PHX2.stage29.stage29_2_birdeye_readiness import (
        Stage29_2BirdeyeEndpointSecret,
    )
    from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
        make_constant_clock,
    )
    from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
        Stage30_11_5RecordingFakeTransportClient,
    )

    snap = store.snapshot(MINT)
    assert snap is not None
    current_price = (current_market_cap / SUPPLY_DECIMAL).quantize(
        Decimal("1E-21"))
    coverage = classify_ath_coverage(
        discovery_provenance="LIVE_HELIUS",
        ath_hydration_status=snap["ath_hydration_status"])
    request = composer.Stage30_11_13RevalidationRequest(
        token_mint=MINT,
        candidate_id="cand_v3_fixture",
        migration_time_utc=MIGRATION_ISO,
        current_price=str(current_price),
        current_market_cap_usd=str(current_market_cap),
        created_at_utc=NOW_ISO,
        migration_confirmed=True,
        symbol_or_name="shit",
        migration_source="V3_PAIR_FIXTURE",
        liquidity_usd="13701.503851485248",
        age_display="2m",
        market_context_status="PRESENT",
        market_context_fetched_at_utc="2026-08-03T17:18:07Z",
        authoritative_ath_price=snap["ath_price"],
        authoritative_ath_market_cap_usd=snap["ath_market_cap"],
        authoritative_ath_timestamp=snap["ath_timestamp"],
        authoritative_ath_provider=snap["ath_provider"],
        authoritative_ath_observation_type=snap["ath_observation_type"],
        authoritative_ath_status=snap["ath_status"],
        authoritative_ath_market_cap_evidence_price_usd=snap[
            "ath_market_cap_evidence_price_usd"],
        ath_coverage=coverage,
        resolved_ath_price=snap["resolved_ath_price"],
        resolved_supply=snap["resolved_supply"],
        resolved_supply_basis=snap["resolved_supply_basis"],
        resolved_ath_market_cap_usd=snap["resolved_ath_market_cap"],
        resolved_observed_at_utc=snap["resolved_observed_at_utc"],
        resolved_ath_source=snap["resolved_source"],
        resolved_ath_observation_type=snap["resolved_observation_type"],
        resolved_ath_status=snap["resolved_status"],
        resolved_evidence_digest=snap["resolved_evidence_digest"],
        resolution_method=snap["resolution_method"],
    )
    client = Stage30_11_5RecordingFakeTransportClient(created_at_utc=NOW_ISO)
    result = composer.compose_no_send_dispatch(
        request,
        ath_transport=_ComposeFreshnessTransport(
            current_price=str(current_price),
            ath_price=snap["resolved_ath_price"]),
        ath_endpoint_secret=Stage29_2BirdeyeEndpointSecret(
            _api_key="abcd1234efgh5678ijkl9012mnop3456",
            _base_url="https://aaaa-bbbb.example"),
        now_utc=datetime(2026, 8, 3, 17, 18, 11, tzinfo=timezone.utc),
        transport_client=client,
        now_seconds=make_constant_clock(Decimal(0)),
        market_context_max_age_seconds=3600,
    )
    return result, client, snap


ATH_MC = Decimal(CORRECTED["ath_market_cap"])


@pytest.mark.parametrize("fraction,expected_tier", [
    (Decimal("0.45"), "Tier 1"),   # 55% drawdown
    (Decimal("0.30"), "Tier 2"),   # 70% drawdown
    (Decimal("0.12"), "Tier 3"),   # 88% drawdown
])
def test_15_16_17_v3_complete_reaches_tier_compose(
        fraction: Decimal, expected_tier: str) -> None:
    store = make_store()
    seed_candidate(store)
    _, outcome = hydrate(store)
    assert outcome["complete"] is True
    result, client, snap = _compose_from_store(
        store, current_market_cap=(ATH_MC * fraction).quantize(
            Decimal("0.000001")))
    assert snap["ath_canonical_source"] == ATH_CANONICAL_SOURCE_V3_PAIR
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, (
        result.reason)
    assert result.snapshot.tier_token == expected_tier
    assert client.bodies, "no fake delivery reservation was made"


def test_18_v3_down_with_complete_live_tracker_still_composes() -> None:
    store = make_store()
    seed_candidate(store)
    # Every V3 surface refuses; the live tracker carries the evidence.
    inner = FakeV3Inner(fail={BIRDEYE_PATH_V3_PAIR_OHLCV: 429,
                              BIRDEYE_PATH_V3_TOKEN_OHLCV: 429})
    assert store.observe_provider_current(
        mint=MINT, price_usd=CORRECTED["usd_high"],
        observed_at="2026-08-03T17:15:36Z", confirmed=False)
    _, outcome = hydrate(store, inner=inner)
    assert outcome["complete"] is False
    hydration = store.hydration(MINT)
    assert hydration["status"] == ATH_HYDRATION_COMPLETE
    assert hydration["ath_canonical_source"] == (
        ATH_CANONICAL_SOURCE_LIVE_TRACKER)
    result, client, snap = _compose_from_store(
        store, current_market_cap=(ATH_MC * Decimal("0.30")).quantize(
            Decimal("0.000001")))
    assert snap["ath_canonical_source"] == ATH_CANONICAL_SOURCE_LIVE_TRACKER
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, (
        result.reason)
    assert client.bodies


def test_19_v3_and_live_both_incomplete_yields_one_named_blocker() -> None:
    store = make_store(now_iso=NOW_ISO)
    # Tracking begun far after the anchor: the live tracker is NOT complete.
    assert store.register_migration_pair(
        mint=MINT, pool_address=PAIR, quote_mint=QUOTE,
        anchor_utc=MIGRATION_ISO,
        tracking_started_at_utc="2026-08-03T17:17:50Z")
    store.schedule_hydration(MINT, anchor_utc=MIGRATION_ISO)
    inner = FakeV3Inner(fail={BIRDEYE_PATH_V3_PAIR_OHLCV: 429})
    _, outcome = hydrate(store, inner=inner)
    hydration = store.hydration(MINT)
    assert hydration["status"] == ATH_HYDRATION_PENDING
    assert hydration["reason"] == ATH_V3_RATE_LIMITED
    assert hydration["reason"] in ATH_V3_PENDING_REASONS
    started = datetime.fromisoformat(
        "2026-08-03T17:17:50+00:00").timestamp()
    anchor = datetime.fromisoformat(
        MIGRATION_ISO.replace("Z", "+00:00")).timestamp()
    assert started - anchor > ATH_LIVE_TRACKER_ANCHOR_TOLERANCE_SECONDS


def test_20_one_candidates_v3_failure_does_not_block_another() -> None:
    other = "B" * 39 + "pump"
    store = make_store()
    seed_candidate(store)
    seed_candidate(store, mint=other, pair="PairB" + "1" * 39)
    # Mint A fails hard on the pair surface...
    inner_fail = FakeV3Inner(fail={BIRDEYE_PATH_V3_PAIR_OHLCV: 429})
    transport = make_transport(store, inner=inner_fail)
    outcome_a = transport.refresh_ath_history(MINT, timeout_seconds=5)
    assert outcome_a["complete"] is False
    # ...while mint B (same store, healthy transport) completes.  The fake
    # serves the recorded pair candles for whichever pair is asked, which is
    # exactly the isolation property under test: nothing about A's failure
    # is consulted.
    transport_ok = make_transport(store)
    outcome_b = transport_ok.refresh_ath_history(other, timeout_seconds=5)
    assert outcome_b["complete"] is True
    assert store.hydration(MINT)["status"] == ATH_HYDRATION_PENDING
    assert store.hydration(other)["status"] == ATH_HYDRATION_COMPLETE


def test_21_request_tickets_reconcile_exactly_under_concurrency() -> None:
    mints = [chr(ord("C") + idx) * 39 + "pump" for idx in range(4)]
    store = make_store()
    for idx, mint in enumerate(mints):
        seed_candidate(store, mint=mint, pair=f"Pair{idx}" + "9" * 38)
    meter = MarketPhysicalRequestMeter()
    transports = [make_transport(store, meter=meter) for _ in mints]
    errors: List[BaseException] = []

    def run(transport, mint):
        try:
            transport.refresh_ath_history(mint, timeout_seconds=5)
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(transport, mint))
               for transport, mint in zip(transports, mints)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    outcome = reconcile(scheduler_physical_requests_total=0, meter=meter)
    assert outcome["unreconciled_delta"] == 0
    assert outcome["reconciled"] is True
    v3_total = sum(
        outcome["physical_requests_by_origin"].get(origin, 0)
        for origin in ATH_V3_REQUEST_ORIGINS)
    assert outcome["reconciliation_reasons"]["ATH_V3_REQUESTS"] == v3_total
    assert v3_total == meter.total  # every request in this test is V3 work
    assert outcome["physical_requests_by_origin"][
        ORIGIN_ATH_V3_PAIR_COARSE] == len(mints)
    assert outcome["physical_requests_by_origin"][
        ORIGIN_ATH_V3_PAIR_REFINE] == len(mints)
    assert outcome["physical_requests_by_origin"][
        ORIGIN_ATH_V3_TOKEN_DIAGNOSTIC] == len(mints)


def test_22_429_retry_backoff_is_bounded() -> None:
    store = make_store()
    seed_candidate(store)
    inner = FakeV3Inner(fail={BIRDEYE_PATH_V3_PAIR_OHLCV: 429})
    meter = MarketPhysicalRequestMeter()
    # A near-frozen monotonic clock keeps the provider-scoped backoff window
    # open across both refreshes, so the second one must not dial at all.
    transport = make_transport(store, inner=inner, meter=meter,
                               mono_step=0.001)
    transport.refresh_ath_history(MINT, timeout_seconds=5)
    dialled_first = meter.total
    # One throttled dial, zero retries hammered into the open window.
    assert dialled_first == 1
    # While the provider-scoped backoff window is open, another refresh
    # dials NOTHING at all.
    transport.refresh_ath_history(MINT, timeout_seconds=5)
    assert meter.total == dialled_first
    stats = transport.stats()
    assert stats["rate_limit_backoff_skipped"] >= 1
    assert stats["v3_pair_rate_limited"] == 1
    assert store.hydration(MINT)["reason"] == ATH_V3_RATE_LIMITED


def test_23_complete_v3_ath_cannot_be_overwritten_by_provisional() -> None:
    store = make_store()
    seed_candidate(store)
    hydrate(store)
    before = store.snapshot(MINT)
    assert before["ath_canonical_source"] == ATH_CANONICAL_SOURCE_V3_PAIR
    # A lower provisional live tick changes nothing.
    store.observe_provider_current(
        mint=MINT, price_usd="0.000001", observed_at=NOW_ISO,
        confirmed=False)
    # A lower direct V3 commit attempt cannot regress the stored peaks.
    store.observe_v3_pair_ath(
        mint=MINT, pair_address=PAIR, quote_mint=QUOTE,
        anchor_unix=ANCHOR_ALIGNED, window_from_unix=ANCHOR_ALIGNED,
        window_to_unix=NOW_UNIX, cursor_unix=NOW_UNIX - 15,
        history_complete=True, candles_received=1,
        coarse_peak_native="0.0000001", coarse_peak_unix=ANCHOR_ALIGNED,
        refined_peak_native="0.0000001", refined_peak_unix=ANCHOR_ALIGNED,
        refine_interval="1s", refined=True,
        usd_peak_price="0.000001", usd_peak_unix=ANCHOR_ALIGNED,
        usd_valuation_interval="1s",
        usd_valuation_method="SAME_SECOND_PROVIDER_USD",
        implied_quote_usd="73")
    after = store.snapshot(MINT)
    for key in ("resolved_ath_price", "resolved_ath_market_cap",
                "ath_timestamp"):
        assert after[key] == before[key]
    v3 = store.v3_pair_state(MINT)
    assert Decimal(v3["refined_peak"]["native_high"]) == Decimal(
        CORRECTED["pair_native_high"])


def test_24_restart_creates_new_empty_live_only_v3_domain(tmp_path) -> None:
    state_dir = tmp_path / "state"
    store = CentralAthStateStore(
        tmp_path / "run", checkpoint_dir=state_dir,
        hydration_now_fn=lambda: NOW_ISO)
    assert store.bind_live_epoch(EPOCH_ID)
    seed_candidate(store)
    _, outcome = hydrate(store)
    assert outcome["complete"] is True
    assert store.hydration(MINT)["status"] == ATH_HYDRATION_COMPLETE
    # Restart: a NEW process restores the checkpoint and binds a NEW epoch.
    restarted = CentralAthStateStore(
        tmp_path / "run2", checkpoint_dir=state_dir,
        hydration_now_fn=lambda: NOW_ISO)
    assert restarted.bind_live_epoch("epoch_v3_regression_0002")
    # Prior-epoch V3 state is a different eligibility domain...
    assert restarted.v3_pair_state(MINT) is None
    # ...and the process-scoped live tracker starts empty.
    assert restarted.live_tracker_coverage(MINT) is None
    hydration = restarted.hydration(MINT)
    assert hydration["status"] == ATH_HYDRATION_PENDING


def test_25_historical_dex_diagnostic_records_remain_ineligible() -> None:
    assert classify_ath_coverage(
        discovery_provenance="DEXSCREENER_RESTART_BACKFILL",
        ath_hydration_status=ATH_HYDRATION_PENDING,
    ) == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    # A LIVE candidate still hydrating is partial too (the 2026-08-03 fix);
    # a legacy caller that supplies no verdict keeps the historical reading.
    assert classify_ath_coverage(
        discovery_provenance="LIVE_HELIUS",
        ath_hydration_status=ATH_HYDRATION_PENDING,
    ) == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    assert classify_ath_coverage(
        discovery_provenance="LIVE_HELIUS",
    ) == ATH_COVERAGE_COMPLETE_LIVE


def test_26_composer_consumes_the_canonical_v3_resolved_tuple() -> None:
    store = make_store()
    seed_candidate(store)
    hydrate(store)
    result, client, snap = _compose_from_store(
        store, current_market_cap=Decimal(
            OLD_ALERT["current_market_cap_usd"]))
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, (
        result.reason)
    assert snap["resolved_source"] == SOURCE_PAID_V3_PAIR
    body = client.bodies[-1]
    # The committed composer body renders the CORRECTED canonical maximum
    # ($31.9k), not the old alert's understated one ($24.5k).
    assert "ATH MC: $31.9k" in body
    assert "$24.5k" not in body
    # And the tier is bound to the same resolved tuple the body renders.
    assert result.snapshot.tier_token == "Tier 2"


def test_27_last_real_alert_fixture_reproduces_the_corrected_ath() -> None:
    store = make_store()
    seed_candidate(store)
    _, outcome = hydrate(store)
    assert outcome["complete"] is True
    snap = store.snapshot(MINT)
    # The corrected canonical tuple, exactly.
    assert snap["resolved_ath_price"] == "0.000032175704027720083"
    assert snap["resolved_ath_market_cap"] == CORRECTED["ath_market_cap"]
    assert snap["resolved_supply"] == SUPPLY["normalized_supply"]
    assert snap["ath_timestamp"] == "2026-08-03T17:15:36Z"
    assert snap["ath_provider"] == SOURCE_PAID_V3_PAIR
    assert snap["ath_canonical_source"] == ATH_CANONICAL_SOURCE_V3_PAIR
    # And it corrects the old alert: same supply, higher literal peak.
    assert Decimal(snap["resolved_ath_market_cap"]) > Decimal(
        OLD_ALERT["ath_market_cap"])
    assert Decimal(snap["resolved_ath_price"]) > Decimal(
        OLD_ALERT["ath_price"])
