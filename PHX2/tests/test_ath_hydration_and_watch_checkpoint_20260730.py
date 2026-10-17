"""Deterministic regression for the two 2026-07-30 canary defects.

Both are pinned to the EXACT preserved values of the affected mint
``DKDjfsrv...pump`` ("wen") from run ``paid_primary_live_24x7_20260730T222054Z``
(public mint / pool addresses and market numbers only -- no secret, no
transport, no network, no real send).

DEFECT A -- incorrect restart-backfill ATH hydration
    The alert reported an observed ATH of $46,686.30 and drawdown -57.4%
    (Tier 1).  The authoritative chart peak was ~$67k, i.e. -70.3% (Tier 2).

    PHX2 held BOTH numbers.  ``ath_price`` was 0.00006922487377706038 -- the
    TRUE post-migration 1m candle high, returned by the provider for the
    correctly migration-anchored window [22:13:40Z, 22:26:36Z].  But
    ``observe_ohlcv_high`` could only convert a candle high into a market cap
    through an EVENT-sourced supply, and a bounded restart-backfill candidate
    has no swap events of its own (``supply_observations`` was empty), so
    ``ath_market_cap`` stayed pinned at the highest CURRENT market cap observed
    since admission -- a spot tick at 22:21:39Z, 31% below the real peak.  The
    price maximum and the market-cap maximum therefore described two DIFFERENT
    observations, and the composer bound the tier to the stale one.
    ``0.00006922487377706038 x (46686.30495467755 / 0.00004817365131189636)``
    = $67,087.58 -- the operator's ~$67k.

    Nothing gated on completeness: ``ath_coverage`` existed only in the Telegram
    renderer, which honestly printed "Coverage: Partial (restart backfill)"
    while the alert went out anyway.

DEFECT B -- WATCH_CHECKPOINT_STRUCTURAL_FAILURE / CHECKPOINT_NUMERIC_INVALID
    ``project_closed_tier`` returns the drawdown "0" when a mint's current
    market cap equals its own ATH -- which is exactly what EVERY mint looks
    like on the tick that first establishes its ATH from a spot observation.
    ``market_latest_drawdown_pct`` was validated as a STRICTLY POSITIVE
    decimal, so that legitimate zero was rejected as CHECKPOINT_NUMERIC_INVALID
    at record level.  The value is a plain JSON string, so
    ``_unserializable_field_path`` found nothing and the diagnostic degraded to
    the bare ``field_path="record"``.  The failure category is STRUCTURAL and
    is never retried, so the durable watch checkpoint stopped being written:
    17 attempted, 2 succeeded, 15 consecutive structural failures.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.ath_state import (
    ATH_HYDRATION_ANCHOR_TOLERANCE_SECONDS,
    CentralAthStateStore,
    SUPPLY_BASIS_PROVIDER,
    ath_hydration_backoff_seconds,
    evaluate_ath_hydration,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    WatchEntry,
    Watchlist,
    canonicalize_watch_checkpoint_records,
    describe_checkpoint_records,
    validate_watch_checkpoint_record,
)
from PHX2.free_tier_producer.market_scheduler import project_closed_tier
from PHX2.models.ath_coverage import (
    ATH_COVERAGE_COMPLETE_HYDRATED,
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_COVERAGE_UNKNOWN,
    ATH_HYDRATION_COMPLETE,
    ATH_HYDRATION_MARKET_CAP_UNCONVERTED,
    ATH_HYDRATION_NEVER_ATTEMPTED,
    ATH_HYDRATION_PENDING,
    ATH_HYDRATION_WINDOW_INCOMPLETE,
    ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION,
    ath_coverage_is_complete,
    classify_ath_coverage,
)
from PHX2.models.discovery_provenance import (
    DISCOVERY_PROVENANCE_DEX_BACKFILL,
    DISCOVERY_PROVENANCE_LIVE_HELIUS,
)

# --- Preserved "wen" facts (public values) ---------------------------------

WEN_MINT = "DKDjfsrv2bhBQVuT7ePDZDup2KJbQwNvNPBWtNjVpump"
WEN_POOL = "ErSiDywTsWrSh6KG4Z7sj26mBbrCNFeabh9dKYLnQXAe"
WSOL = "So11111111111111111111111111111111111111112"

#: Authoritative migration anchor (== pool creation, DEXSCREENER pairCreatedAt).
MIGRATION_UTC = "2026-07-30T22:13:40Z"
MIGRATION_UNIX = 1785449620
#: The compose instant of the real send (Telegram message_id 5413).
COMPOSE_UTC = "2026-07-30T22:26:36Z"
COMPOSE_UNIX = 1785450396

#: The spot CURRENT observation that (wrongly) became the reported ATH.
SPOT_AT_UTC = "2026-07-30T22:21:39Z"
SPOT_PRICE = "0.00004817365131189636"
SPOT_MARKET_CAP = "46686.30495467755"

#: The TRUE post-migration 1m candle high the provider returned.
PEAK_HIGH_PRICE = "0.00006922487377706038"
PEAK_CANDLE_UTC = "2026-07-30T22:18:00Z"
PEAK_CANDLE_UNIX = 1785449880
#: Provider-implied circulating supply (market cap / price of ONE observation).
PROVIDER_SUPPLY = Decimal(SPOT_MARKET_CAP) / Decimal(SPOT_PRICE)
#: Complete-hydration expectations from the operator's authoritative chart.
EXPECTED_ATH_MARKET_CAP = Decimal("67087.57753653611989498962777")
CURRENT_MARKET_CAP = "19900"
#: 2026-08-03 canonical V3 window anchor: the coarse-interval floor of the
#: migration instant, so the partial first candle is never dropped.
ANCHOR_ALIGNED_UNIX = (MIGRATION_UNIX // 15) * 15


def _compose_send_module():
    """The compat compose/send glue imports its siblings by bare name."""

    import sys
    from pathlib import Path

    compat = str(Path(__file__).resolve().parents[1]
                 / "free_tier_producer" / "compat")
    if compat not in sys.path:
        sys.path.insert(0, compat)
    import PHX2.free_tier_producer.compat.build29_cap1_compose_send as cs
    return cs


def _store(**kwargs) -> CentralAthStateStore:
    """In-memory store on a pinned evaluation clock (no disk, no clock skew)."""

    kwargs.setdefault("hydration_now_fn", lambda: COMPOSE_UTC)
    return CentralAthStateStore(path=None, **kwargs)


def _registered(store: CentralAthStateStore) -> None:
    assert store.register_pool(
        mint=WEN_MINT, pool_address=WEN_POOL, quote_mint=WSOL,
        creation_timestamp=MIGRATION_UTC)


def _observe_spot(store: CentralAthStateStore) -> None:
    """The single provider CURRENT observation the real run made."""

    assert store.observe_provider_current(
        mint=WEN_MINT, price_usd=SPOT_PRICE, market_cap_usd=SPOT_MARKET_CAP,
        observed_at=SPOT_AT_UTC)


def _hydrate(
    store: CentralAthStateStore, *, complete: bool = True,
    time_from_unix: int = ANCHOR_ALIGNED_UNIX,
    time_to_unix: int = COMPOSE_UNIX, mint: str = WEN_MINT,
    pool: str = WEN_POOL,
) -> None:
    """Commit the canonical V3 pair-history evidence (2026-08-03 contract).

    The economics are byte-identical to the old V1 fixture -- the same true
    peak high at the same candle instant, converted through the same
    provider-implied supply -- only the SOURCE is now the authenticated
    migration pair's V3 history, which is the sole candle path that can
    complete hydration.
    """

    assert store.observe_v3_pair_ath(
        mint=mint, pair_address=pool, quote_mint=WSOL,
        anchor_unix=ANCHOR_ALIGNED_UNIX,
        window_from_unix=time_from_unix, window_to_unix=time_to_unix,
        cursor_unix=max(time_from_unix, time_to_unix - 15),
        history_complete=complete, candles_received=13,
        coarse_peak_native=PEAK_HIGH_PRICE,
        coarse_peak_unix=PEAK_CANDLE_UNIX,
        refined_peak_native=PEAK_HIGH_PRICE,
        refined_peak_unix=PEAK_CANDLE_UNIX,
        refine_interval="1s", refined=True,
        usd_peak_price=PEAK_HIGH_PRICE, usd_peak_unix=PEAK_CANDLE_UNIX,
        usd_valuation_interval="1s",
        usd_valuation_method="SAME_SECOND_PROVIDER_USD",
        implied_quote_usd="1",
    ) is not None


def _partial_store() -> CentralAthStateStore:
    """The exact state the canary composed and sent from."""

    store = _store()
    _registered(store)
    _observe_spot(store)
    return store


def _hydrated_store() -> CentralAthStateStore:
    store = _partial_store()
    _hydrate(store)
    return store


# ===========================================================================
# DEFECT A -- restart-backfill ATH hydration
# ===========================================================================


def test_1_history_is_requested_from_migration_not_restart_admission():
    """The hydration window anchors at migration, never at PHX2 admission.

    The canary's admission was 22:20:55Z and its first observation 22:21:39Z;
    a window starting at either would have begun AFTER the 22:18 peak candle.
    """

    store = _partial_store()
    assert store.pool_created_at(WEN_MINT) == MIGRATION_UTC

    _hydrate(store)
    v3 = store.v3_pair_state(WEN_MINT)
    assert v3["window_from_unix"] == ANCHOR_ALIGNED_UNIX
    assert v3["window_from_unix"] <= MIGRATION_UNIX
    assert store.snapshot(WEN_MINT)["ath_hydration_status"] == (
        ATH_HYDRATION_COMPLETE)

    # A window anchored at admission instead is refused, however complete the
    # provider claims it to be.
    late = _partial_store()
    admission_unix = MIGRATION_UNIX + 479          # 22:21:39Z
    _hydrate(late, time_from_unix=admission_unix)
    snapshot = late.snapshot(WEN_MINT)
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_PENDING
    assert snapshot["ath_hydration_reason"] == (
        ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION)


def test_2_candle_highs_not_closes_determine_post_migration_ath():
    """The ATH follows the intracandle HIGH even when every close is lower."""

    store = _partial_store()
    # A close-based maximum would land at the spot price; the high is 1.44x it.
    close_like = SPOT_PRICE
    assert Decimal(PEAK_HIGH_PRICE) > Decimal(close_like)
    _hydrate(store)
    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_price"] == PEAK_HIGH_PRICE
    assert snapshot["ath_market_cap_evidence_price_usd"] == PEAK_HIGH_PRICE
    assert Decimal(snapshot["ath_market_cap"]) > Decimal(SPOT_MARKET_CAP)


class _OhlcvSecret:
    def reveal_api_key(self) -> str:
        return "k" * 32

    def reveal_base_url(self) -> str:
        return "https://market.invalid"


class _PagedOhlcvInner:
    """Offline inner transport serving V3 pair/token candles over a window.

    The fictional pool is quoted 1:1 with USD (implied ratio 1 -- inside the
    structural sanity band), so the native pair highs ARE the USD highs and
    every economic expectation of the original fixture is preserved.
    """

    def __init__(self, *, drop_pages: tuple = (), page_candles: int = 5):
        from PHX2.stage29.birdeye_constants import (
            BIRDEYE_PATH_V3_PAIR_OHLCV,
            BIRDEYE_PATH_V3_TOKEN_OHLCV,
        )
        self.pair_path = BIRDEYE_PATH_V3_PAIR_OHLCV
        self.token_path = BIRDEYE_PATH_V3_TOKEN_OHLCV
        self.drop_pages = set(drop_pages)
        self.page_candles = page_candles
        self.requested: list = []

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        from PHX2.stage29.stage29_2_birdeye_models import (
            BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
            BIRDEYE_REFUSAL_REASON_NONE,
        )

        class _Result:
            def __init__(self, body, status=200,
                         refusal=BIRDEYE_REFUSAL_REASON_NONE):
                self.http_status_code = status
                self.body = body
                self.refusal_reason = refusal
                self.fetched_at_utc = COMPOSE_UTC

        if path not in (self.pair_path, self.token_path):
            return _Result({"success": True, "data": {}})
        address = str(query_params["address"])
        interval = str(query_params["type"])
        start = int(query_params["time_from"])
        end = int(query_params["time_to"])
        if path == self.pair_path and interval == "15s":
            self.requested.append((start, end))
            # Failures are keyed by the RANGE's page number (not by call
            # index) so the transport's bounded in-call retries see the same
            # deterministic provider failure every time.
            page_number = max(0, start - ANCHOR_ALIGNED_UNIX) // (
                self.page_candles * 15)
            if page_number in self.drop_pages:
                # A dropped page is a PROVIDER FAILURE (5xx), not an empty
                # bucket: with padding=false an empty bucket is legitimate
                # "no trades" and would not interrupt coverage.
                return _Result(None, status=500,
                               refusal=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED)
        step = 1 if interval == "1s" else 15
        items = []
        candle = ((start + step - 1) // step) * step
        while candle <= end:
            in_peak_bucket = (
                candle == PEAK_CANDLE_UNIX if step == 15
                else PEAK_CANDLE_UNIX <= candle < PEAK_CANDLE_UNIX + 15)
            high = PEAK_HIGH_PRICE if in_peak_bucket else SPOT_PRICE
            items.append({"h": high, "c": SPOT_PRICE, "unix_time": candle,
                          "address": address})
            candle += step
        return _Result({"success": True, "data": {"items": items}})


def _paged_transport(store, *, drop_pages=(), page_candles=5):
    from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport

    inner = _PagedOhlcvInner(drop_pages=drop_pages, page_candles=page_candles)
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_OhlcvSecret(),
        min_interval_seconds=0, cache_ttl_seconds=0,
        ohlcv_cache_ttl_seconds=0, v3_page_candles=page_candles,
        now_fn=lambda: float(COMPOSE_UNIX), ath_store=store)
    return inner, transport


def test_3_all_expected_pages_are_consumed():
    """The real paged refresh tiles [aligned migration, now] and completes."""

    store = _partial_store()
    inner, transport = _paged_transport(store)
    outcome = transport.refresh_ath_history(WEN_MINT)

    assert outcome["attempted"] is True
    # The window starts at the coarse-interval FLOOR of migration, so the
    # partial first candle can never be dropped (the 2026-08-03 defect).
    assert outcome["time_from_unix"] == ANCHOR_ALIGNED_UNIX
    assert outcome["time_to_unix"] == COMPOSE_UNIX
    assert outcome["complete"] is True
    window_seconds = COMPOSE_UNIX - ANCHOR_ALIGNED_UNIX
    expected_pages = -(-(window_seconds + 1) // (5 * 15))   # ceil division
    assert outcome["pages"] == expected_pages == 11
    # Pages tile the window contiguously: no gap, no overlap, no truncation.
    assert inner.requested[0][0] == ANCHOR_ALIGNED_UNIX
    assert inner.requested[-1][1] == COMPOSE_UNIX
    for (_, prev_end), (next_start, _) in zip(inner.requested,
                                              inner.requested[1:]):
        assert next_start == prev_end + 1

    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_price"] == PEAK_HIGH_PRICE
    assert Decimal(snapshot["ath_market_cap"]) == EXPECTED_ATH_MARKET_CAP
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_COMPLETE


def test_3b_a_dropped_page_never_completes_the_window():
    """A single failed page keeps the candidate PENDING and retryable."""

    store = _partial_store()
    inner, transport = _paged_transport(store, drop_pages=(1,))
    outcome = transport.refresh_ath_history(WEN_MINT)

    assert outcome["attempted"] is True
    assert outcome["complete"] is False
    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_v3_pair"]["history_complete"] is False
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_PENDING
    assert snapshot["ath_hydration_reason"] == "ATH_V3_CANDLE_GAP"
    # A partially-covered window may still RAISE the monotonic maximum -- the
    # candles it did return are real observations and discarding them would
    # lose evidence.  What it may NOT do is be presented as the FINAL
    # post-migration ATH: the status stays PENDING, so the coverage token
    # stays partial and the candidate cannot be tiered, composed or sent.
    assert classify_ath_coverage(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_hydration_status=snapshot["ath_hydration_status"],
    ) == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    assert ath_coverage_is_complete(
        ATH_COVERAGE_PARTIAL_SINCE_ADMISSION) is False
    assert snapshot["ath_post_migration_complete"] is False


def test_3c_ttl_suppressed_refresh_is_not_charged_as_an_attempt():
    """A TTL no-op must not advance the bounded hydration backoff."""

    from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport

    store = _partial_store()
    inner = _PagedOhlcvInner(drop_pages=(0, 1, 2))
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_OhlcvSecret(),
        min_interval_seconds=0, cache_ttl_seconds=0,
        ohlcv_cache_ttl_seconds=3600, v3_page_candles=5,
        now_fn=lambda: float(COMPOSE_UNIX), ath_store=store)
    first = transport.refresh_ath_history(WEN_MINT)
    second = transport.refresh_ath_history(WEN_MINT)
    assert first["attempted"] is True
    assert second["attempted"] is False
    assert second["reason"] == "OHLCV_REFRESH_TTL_ACTIVE"


def test_4_missing_pages_produce_pending_status():
    """An incomplete window is PENDING with a named reason, never complete."""

    store = _partial_store()
    _hydrate(store, complete=False)
    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_PENDING
    assert snapshot["ath_hydration_reason"] == "ATH_V3_HISTORY_INCOMPLETE"
    assert classify_ath_coverage(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_hydration_status=snapshot["ath_hydration_status"],
    ) == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION


def test_4b_partial_maximum_is_never_substituted_as_the_final_ath():
    """The exact canary state: a partial maximum stays explicitly unproven."""

    snapshot = _partial_store().snapshot(WEN_MINT)
    assert snapshot["ath_market_cap"] == SPOT_MARKET_CAP
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_PENDING
    assert snapshot["ath_post_migration_complete"] is False

    # And a record whose two maxima come from different observations -- the
    # 2026-07-30 shape -- can never be promoted, even with a complete window.
    torn = dict(snapshot)
    torn["ath_price"] = PEAK_HIGH_PRICE
    torn["ath_market_cap_evidence_price_usd"] = SPOT_PRICE
    torn["ath_v3_pair"] = {
        "schema_version": "phx2_ath_v3_pair_v1",
        "pair_address": WEN_POOL, "quote_mint": WSOL,
        "live_epoch_id": None, "anchor_unix": ANCHOR_ALIGNED_UNIX,
        "coarse_interval": "15s",
        "window_from_unix": ANCHOR_ALIGNED_UNIX,
        "window_to_unix": COMPOSE_UNIX, "history_complete": True,
        "usd_peak": {"price_usd": PEAK_HIGH_PRICE,
                     "unix_time": PEAK_CANDLE_UNIX}}
    status, reason = evaluate_ath_hydration(torn, now_utc=COMPOSE_UTC)
    assert (status, reason) == (
        ATH_HYDRATION_PENDING, ATH_HYDRATION_MARKET_CAP_UNCONVERTED)


def test_5_partial_ath_coverage_cannot_reach_compose():
    """The pre-compose gate refuses a pending candidate before composing."""

    cs = _compose_send_module()

    snapshot = _partial_store().snapshot(WEN_MINT)
    request = cs.build_revalidation_request(
        token_mint=WEN_MINT, candidate_id="dex_restart_wen",
        migration_time_utc=MIGRATION_UTC, migration_source="dex_restart:wen",
        current_price="0.00002053", current_market_cap_usd=CURRENT_MARKET_CAP,
        liquidity_usd="9000", market_context_fetched_at_utc=COMPOSE_UTC,
        created_at_utc=COMPOSE_UTC, central_ath=snapshot,
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL)
    assert request.ath_coverage == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION

    class _ExplodingTransport:
        def get(self, *_args, **_kwargs):        # pragma: no cover - must not run
            raise AssertionError("COMPOSE_REACHED_ATH_TRANSPORT")

    result = cs.compose_and_maybe_send(
        request,
        ath_transport=_ExplodingTransport(), ath_endpoint_secret=object(),
        now_utc=COMPOSE_UTC, now_seconds=lambda: Decimal(0),
        ledger=None, guard=None, authorization=None,
        created_at_utc=COMPOSE_UTC,
        activation_proof={
            "activation_state": "ACTIVE_DIP_WATCH", "activation_proven": True},
    )
    assert result["compose_reason"] == "ATH_COVERAGE_INCOMPLETE"
    assert result["eligible"] is False
    assert result["compose_decision"] is None
    assert result["compose_tier"] is None
    assert result["compose_drawdown_pct"] is None
    assert result["send_result"] is None


def test_6_partial_ath_coverage_cannot_send_telegram():
    """Even reaching the composer, a partial coverage token never dispatches."""

    from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
        COMPOSE_DECISION_REJECTED,
        COMPOSE_REJECTED_ATH_COVERAGE_INCOMPLETE,
        Stage30_11_13RevalidationRequest,
        compose_no_send_dispatch,
    )

    from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
        Stage30_11_5RecordingFakeTransportClient,
    )

    snapshot = _partial_store().snapshot(WEN_MINT)
    request = Stage30_11_13RevalidationRequest(
        token_mint=WEN_MINT, candidate_id="dex_restart_wen",
        migration_time_utc=MIGRATION_UTC, current_price="0.00002053",
        current_market_cap_usd=CURRENT_MARKET_CAP, created_at_utc=COMPOSE_UTC,
        migration_confirmed=True, liquidity_usd="9000",
        market_context_fetched_at_utc=COMPOSE_UTC,
        authoritative_ath_price=snapshot["ath_price"],
        authoritative_ath_market_cap_usd=snapshot["ath_market_cap"],
        authoritative_ath_timestamp=snapshot["ath_timestamp"],
        authoritative_ath_provider=snapshot["ath_provider"],
        authoritative_ath_observation_type=snapshot["ath_observation_type"],
        authoritative_ath_status=snapshot["ath_status"],
        authoritative_ath_market_cap_evidence_price_usd=snapshot[
            "ath_market_cap_evidence_price_usd"],
        ath_coverage=ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    )
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=COMPOSE_UTC)

    class _NoCallTransport:
        def get(self, *_args, **_kwargs):        # pragma: no cover
            raise AssertionError("ATH_TRANSPORT_REACHED")

    result = compose_no_send_dispatch(
        request, ath_transport=_NoCallTransport(),
        ath_endpoint_secret=object(),
        now_utc=datetime(2026, 7, 30, 22, 26, 36, tzinfo=timezone.utc),
        transport_client=client, now_seconds=lambda: Decimal(0))
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_ATH_COVERAGE_INCOMPLETE
    assert client.attempted == 0
    assert client.bodies == []


def test_7_complete_hydration_restores_the_67k_ath_fixture():
    """After complete hydration the maximum IS the real ~$67k peak."""

    snapshot = _hydrated_store().snapshot(WEN_MINT)
    assert snapshot["ath_price"] == PEAK_HIGH_PRICE
    assert Decimal(snapshot["ath_market_cap"]) == EXPECTED_ATH_MARKET_CAP
    assert Decimal("66500") < Decimal(snapshot["ath_market_cap"]) < Decimal("67500")
    # The market cap is the market cap OF the ATH price observation.
    assert snapshot["ath_market_cap_evidence_price_usd"] == PEAK_HIGH_PRICE
    assert snapshot["ath_supply_basis"] == SUPPLY_BASIS_PROVIDER
    assert Decimal(snapshot["ath_supply_at_observation"]) == PROVIDER_SUPPLY
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_COMPLETE
    assert snapshot["ath_post_migration_complete"] is True
    assert classify_ath_coverage(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_hydration_status=snapshot["ath_hydration_status"],
    ) == ATH_COVERAGE_COMPLETE_HYDRATED


def test_8_19_9k_against_67k_evaluates_minus_70_3_percent():
    snapshot = _hydrated_store().snapshot(WEN_MINT)
    _, drawdown = project_closed_tier(
        ath_market_cap_usd=snapshot["ath_market_cap"],
        current_market_cap_usd=CURRENT_MARKET_CAP)
    assert Decimal("70.2") < Decimal(drawdown) < Decimal("70.5")
    # The shipped alert computed -57.4% from the partial maximum.
    _, shipped = project_closed_tier(
        ath_market_cap_usd=SPOT_MARKET_CAP,
        current_market_cap_usd=CURRENT_MARKET_CAP)
    assert Decimal("57.3") < Decimal(shipped) < Decimal("57.5")


def test_9_fixture_enters_tier_2_not_tier_1():
    snapshot = _hydrated_store().snapshot(WEN_MINT)
    tier, _ = project_closed_tier(
        ath_market_cap_usd=snapshot["ath_market_cap"],
        current_market_cap_usd=CURRENT_MARKET_CAP)
    assert tier == "Tier 2"
    shipped_tier, _ = project_closed_tier(
        ath_market_cap_usd=SPOT_MARKET_CAP,
        current_market_cap_usd=CURRENT_MARKET_CAP)
    assert shipped_tier == "Tier 1"          # the defect, pinned


def test_10_no_historical_tier_replay_flood_on_bulk_hydration():
    """Hydrating a restored backlog projects each mint at most once.

    A completed hydration must not replay the mint's whole post-migration tier
    history: the tier is a function of the CURRENT market cap against the
    proven maximum, so one hydration yields one projection per mint.
    """

    store = _store()
    projections = []
    for index in range(25):
        mint = "%s%spump" % ("Flood", str(index).rjust(38, "0"))
        store.register_pool(mint=mint, pool_address=WEN_POOL + str(index),
                            quote_mint=WSOL, creation_timestamp=MIGRATION_UTC)
        store.observe_provider_current(
            mint=mint, price_usd=SPOT_PRICE, market_cap_usd=SPOT_MARKET_CAP,
            observed_at=SPOT_AT_UTC)
        _hydrate(store, mint=mint, pool=WEN_POOL + str(index))
        snapshot = store.snapshot(mint)
        assert snapshot["ath_hydration_status"] == ATH_HYDRATION_COMPLETE
        tier, _ = project_closed_tier(
            ath_market_cap_usd=snapshot["ath_market_cap"],
            current_market_cap_usd=CURRENT_MARKET_CAP)
        projections.append((mint, tier))
    assert len(projections) == 25
    assert len({mint for mint, _ in projections}) == 25
    assert {tier for _, tier in projections} == {"Tier 2"}


def test_11_backfill_candidate_remains_retryable_while_pending():
    """Pending hydration retries on a BOUNDED backoff and is never terminal."""

    now = {"value": COMPOSE_UTC}
    store = CentralAthStateStore(path=None,
                                 hydration_now_fn=lambda: now["value"])
    _registered(store)
    _observe_spot(store)
    assert store.hydration_due(WEN_MINT) is True

    first = store.note_hydration_attempt(
        WEN_MINT, attempted_at_utc=COMPOSE_UTC)
    assert first["status"] == ATH_HYDRATION_PENDING
    assert first["attempt_count"] == 1
    assert first["next_attempt_at_utc"] is not None
    # Immediately after an attempt the candidate is NOT due again.
    assert store.hydration_due(WEN_MINT, now_utc=COMPOSE_UTC) is False
    # ...and is due again once the bounded backoff elapses.
    assert store.hydration_due(
        WEN_MINT, now_utc="2026-07-30T23:59:00Z") is True

    second = store.note_hydration_attempt(
        WEN_MINT, attempted_at_utc="2026-07-30T23:59:00Z")
    assert second["attempt_count"] == 2
    assert ath_hydration_backoff_seconds(1) < ath_hydration_backoff_seconds(2)
    assert ath_hydration_backoff_seconds(999) == ath_hydration_backoff_seconds(
        1000)                                    # bounded ceiling

    # The candidate itself is untouched: still a live, retryable watch row.
    assert _watch_entry().is_active()

    # A completed hydration stops the retry loop.
    _hydrate(store)
    done = store.note_hydration_attempt(
        WEN_MINT, attempted_at_utc="2026-07-31T00:05:00Z")
    assert done["status"] == ATH_HYDRATION_COMPLETE
    assert done["next_attempt_at_utc"] is None
    assert store.hydration_due(WEN_MINT) is False


def test_12_live_helius_candidates_remain_unaffected():
    """Live coverage follows the hydration verdict; legacy callers hold.

    2026-08-03 correction: "live" no longer means "complete by discovery".
    The last real alert proved a live candidate's sampled maximum can miss
    the literal first-seconds peak, so a live candidate is COMPLETE only
    when the central verdict says so (canonical V3 pair history, or the
    uninterrupted live tracker).  Callers that supply NO verdict -- legacy
    artifacts that predate it -- keep the historical reading.
    """

    for status in (None, ATH_HYDRATION_COMPLETE):
        assert classify_ath_coverage(
            discovery_provenance=DISCOVERY_PROVENANCE_LIVE_HELIUS,
            ath_hydration_status=status) == ATH_COVERAGE_COMPLETE_LIVE
    assert classify_ath_coverage(
        discovery_provenance=DISCOVERY_PROVENANCE_LIVE_HELIUS,
        ath_hydration_status=ATH_HYDRATION_PENDING,
    ) == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION
    assert ath_coverage_is_complete(ATH_COVERAGE_COMPLETE_LIVE) is True
    assert ath_coverage_is_complete(ATH_COVERAGE_COMPLETE_HYDRATED) is True
    assert ath_coverage_is_complete(ATH_COVERAGE_PARTIAL_SINCE_ADMISSION) is False
    # An unclassifiable provenance fails closed.
    assert classify_ath_coverage(
        discovery_provenance="SOMETHING_ELSE") == ATH_COVERAGE_UNKNOWN
    assert ath_coverage_is_complete(ATH_COVERAGE_UNKNOWN) is False


# ===========================================================================
# DEFECT B -- watch checkpoint CHECKPOINT_NUMERIC_INVALID
# ===========================================================================


def _watch_entry(mint: str = WEN_MINT, candidate_id: str = "dex_restart_wen"):
    """A plain PENDING_BASELINE watch row: the checkpoint defect is orthogonal
    to activation state, so the fixture carries no activation proof."""

    return WatchEntry(
        token_mint=mint, candidate_id=candidate_id,
        migration_time_utc=MIGRATION_UTC, source_ref="dex_restart:wen",
        seeded_at_utc="2026-07-30T22:20:55Z")


def _watch_record(**overrides) -> dict:
    record = {
        key: value for key, value in _watch_entry().__dict__.items()
        if not key.startswith("_")}
    record.update(overrides)
    return record


def test_13_exact_checkpoint_invalid_record_reproduces_the_failure():
    """The rejected value: ``market_latest_drawdown_pct`` == "0".

    ``project_closed_tier`` produces it whenever a mint's current market cap
    equals its own ATH -- true for EVERY mint on the tick that first sets its
    ATH from a spot observation, which is what happened at 22:21:42Z, two
    seconds after the last successful checkpoint write at 22:21:41Z.
    """

    tier, drawdown = project_closed_tier(
        ath_market_cap_usd=SPOT_MARKET_CAP,
        current_market_cap_usd=SPOT_MARKET_CAP)
    assert tier is None
    assert drawdown == "0"                    # the exact rejected raw value

    # The value is finite, JSON-safe and schema-shaped: not NaN, not Infinity,
    # not a float, not a Decimal object, not null, not negative, not a
    # non-string.  Only the strictly-positive rule rejected it.
    assert isinstance(drawdown, str)
    assert json.dumps({"market_latest_drawdown_pct": drawdown})

    # PRE-FIX behaviour, pinned by re-applying the old strictly-positive rule.
    from PHX2.free_tier_producer.compat.build30_watchlist import _decimal
    assert _decimal(drawdown) is None                     # strictly positive
    assert _decimal(drawdown, positive=False) == Decimal(0)   # non-negative

    for bad in ("NaN", "Infinity", "-1", "-0.5", "", "abc"):
        assert _decimal(bad, positive=False) is None or Decimal(bad) < 0


def test_14_the_fixed_record_serializes_and_restores(tmp_path):
    """The zero-drawdown record now writes and reads back intact."""

    record = _watch_record(market_latest_tier=None,
                           market_latest_drawdown_pct="0")
    ok, reason = validate_watch_checkpoint_record(record)
    assert (ok, reason) == (True, "")
    canonical, conflicts = canonicalize_watch_checkpoint_records([record])
    assert conflicts == []
    assert describe_checkpoint_records(canonical) is None

    watchlist = Watchlist(max_size=8,
                          terminal_history_path=tmp_path / "terminal.jsonl")
    entry = _watch_entry()
    assert entry.set_market_tier_projection(tier=None, drawdown_pct="0")
    assert entry.market_latest_drawdown_pct == "0"
    watchlist._entries[entry.token_mint] = entry
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)

    restored = Watchlist.load(
        path, max_size=8,
        terminal_history_path=tmp_path / "terminal2.jsonl")
    assert restored.checkpoint.checkpoint_quarantined is False
    assert restored.get(WEN_MINT).market_latest_drawdown_pct == "0"


def test_15_all_persisted_numeric_values_are_finite():
    """No non-finite / float / negative value can survive validation."""

    from PHX2.free_tier_producer.compat.build30_watchlist import (
        _WATCH_DECIMAL_FIELDS, _WATCH_NONNEGATIVE_DECIMAL_FIELDS,
    )
    for field_name in _WATCH_DECIMAL_FIELDS + _WATCH_NONNEGATIVE_DECIMAL_FIELDS:
        for bad in ("NaN", "Infinity", "-Infinity", "-1", 1.5, Decimal("1")):
            ok, reason = validate_watch_checkpoint_record(
                _watch_record(**{field_name: bad}))
            assert ok is False, (field_name, bad)
            assert reason == cpe.QUARANTINE_NUMERIC_INVALID

    # Zero is legitimate ONLY for the non-negative group.
    for field_name in _WATCH_NONNEGATIVE_DECIMAL_FIELDS:
        ok, _ = validate_watch_checkpoint_record(
            _watch_record(**{field_name: "0"}))
        assert ok is True, field_name


def test_16_repeated_checkpoint_writes_succeed(tmp_path):
    """17 consecutive writes of the once-fatal record all commit."""

    watchlist = Watchlist(max_size=16,
                          terminal_history_path=tmp_path / "terminal.jsonl")
    entry = _watch_entry()
    entry.set_market_tier_projection(tier=None, drawdown_pct="0")
    watchlist._entries[entry.token_mint] = entry
    path = tmp_path / "watch_state.jsonl"
    for _ in range(17):                       # the run's 17 attempted writes
        watchlist.persist(path)
    summary = watchlist.checkpoint_summary()
    assert summary["checkpoint_write_attempted_total"] == 17
    assert summary["checkpoint_write_succeeded_total"] == 17
    assert summary["checkpoint_structural_failed_total"] == 0
    assert summary["checkpoint_write_permanent_failed_total"] == 0


def test_17_circuit_does_not_open_under_valid_checkpoint_writes(tmp_path):
    watchlist = Watchlist(max_size=16,
                          terminal_history_path=tmp_path / "terminal.jsonl")
    for index in range(11):                   # the failing write's 11 records
        mint = "%s%spump" % ("Circuit", str(index).rjust(37, "0"))
        entry = _watch_entry(mint=mint,
                             candidate_id="dex_restart_%d" % index)
        entry.set_market_tier_projection(tier=None, drawdown_pct="0")
        watchlist._entries[mint] = entry
    path = tmp_path / "watch_state.jsonl"
    for _ in range(5):
        watchlist.persist(path)
    summary = watchlist.checkpoint_summary()
    assert summary["checkpoint_consecutive_failures"] == 0
    assert summary["checkpoint_durability_status"] == (
        cpe.CHECKPOINT_DURABILITY_HEALTHY)
    assert summary["checkpoint_last_failure_detail"] is None
    assert summary["checkpoint_durable_candidate_count"] == 11


def test_18_corrupt_records_still_fail_closed():
    """The schema was NOT weakened: genuine corruption still refuses."""

    for bad in (float("nan"), float("inf"), -1, "-3", "NaN", 2.5, None):
        if bad is None:
            continue
        record = _watch_record(market_latest_drawdown_pct=bad)
        ok, reason = validate_watch_checkpoint_record(record)
        assert ok is False, bad
        assert reason == cpe.QUARANTINE_NUMERIC_INVALID
        detail = describe_checkpoint_records([record])
        assert detail["failure_category"] == cpe.CHECKPOINT_FAILURE_STRUCTURAL
        assert detail["reason"] == cpe.QUARANTINE_NUMERIC_INVALID
        # The diagnostic now NAMES the field instead of the useless "record".
        assert detail["field_path"] in (
            "market_latest_drawdown_pct", "<root>")

    # A strictly-positive field still refuses zero.
    ok, reason = validate_watch_checkpoint_record(
        _watch_record(migration_market_cap_usd="0"))
    assert (ok, reason) == (False, cpe.QUARANTINE_NUMERIC_INVALID)
    detail = describe_checkpoint_records(
        [_watch_record(migration_market_cap_usd="0")])
    assert detail["field_path"] == "migration_market_cap_usd"


def test_18b_invalid_optional_telemetry_is_excluded_not_written_through():
    """Unusable optional telemetry never corrupts the required record."""

    entry = _watch_entry()
    assert entry.set_market_tier_projection(
        tier="Tier 2", drawdown_pct="-4") is False
    assert entry.market_latest_drawdown_pct is None
    assert entry.market_latest_tier == "Tier 2"
    record = {k: v for k, v in entry.__dict__.items()
              if not k.startswith("_")}
    assert validate_watch_checkpoint_record(record)[0] is True


# ===========================================================================
# Cross-cutting
# ===========================================================================


def test_19_telegram_and_ledger_behaviour_otherwise_unchanged():
    """Only the incomplete-ATH case changes; every other body path holds."""

    from PHX2.delivery.telegram_composer import (
        ATH_COVERAGE_COMPLETE_HYDRATED as BODY_HYDRATED,
        ATH_COVERAGE_COMPLETE_LIVE as BODY_LIVE,
        ATH_COVERAGE_PARTIAL_SINCE_ADMISSION as BODY_PARTIAL,
        compose_telegram_ping,
    )
    from PHX2.tests.delivery.test_telegram_composer import _sample

    def body_for(**updates) -> str:
        return compose_telegram_ping(replace(_sample(), **updates)).text

    live = body_for(discovery_provenance="HELIUS_LIVE",
                    ath_coverage=BODY_LIVE)
    assert "Post-mig ATH: $57k" in live
    assert "Coverage:" not in live

    partial = body_for(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_coverage=BODY_PARTIAL)
    assert "Obs ATH: $57k" in partial
    assert "• Coverage: Partial (restart backfill)" in partial.splitlines()

    hydrated = body_for(
        discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
        ath_coverage=BODY_HYDRATED)
    assert "Post-mig ATH: $57k" in hydrated
    assert "• Coverage: Complete (restart backfill hydrated)" in (
        hydrated.splitlines())
    # Internal schema tokens and the provider name stay artifact-only.
    for banned in ("COMPLETE_HYDRATED", "DEXSCREENER", "RESTART_BACKFILL"):
        assert banned not in hydrated

    # A backfill admission can never claim LIVE coverage.
    with pytest.raises(ValueError, match="ATH_COVERAGE_PROOF_INCONSISTENT"):
        body_for(discovery_provenance=DISCOVERY_PROVENANCE_DEX_BACKFILL,
                 ath_coverage=BODY_LIVE)
    # ...and a live candidate can never claim HYDRATED coverage.
    with pytest.raises(ValueError, match="ATH_COVERAGE_PROOF_INCONSISTENT"):
        body_for(discovery_provenance="HELIUS_LIVE",
                 ath_coverage=BODY_HYDRATED)


def test_20_no_real_telegram_send_occurs_in_these_tests(monkeypatch):
    """Offline guarantee: nothing in this module can open a socket."""

    import socket

    def _refuse(*_args, **_kwargs):           # pragma: no cover
        raise AssertionError("NETWORK_ACCESS_ATTEMPTED")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)

    store = _hydrated_store()
    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_COMPLETE
    tier, _ = project_closed_tier(
        ath_market_cap_usd=snapshot["ath_market_cap"],
        current_market_cap_usd=CURRENT_MARKET_CAP)
    assert tier == "Tier 2"


def test_anchor_tolerance_is_one_candle():
    """One minute of provider boundary alignment, never more."""

    assert ATH_HYDRATION_ANCHOR_TOLERANCE_SECONDS == 60.0
    store = _partial_store()
    _hydrate(store, time_from_unix=MIGRATION_UNIX + 60)
    assert store.snapshot(WEN_MINT)["ath_hydration_status"] == (
        ATH_HYDRATION_COMPLETE)
    late = _partial_store()
    _hydrate(late, time_from_unix=MIGRATION_UNIX + 61)
    assert late.snapshot(WEN_MINT)["ath_hydration_status"] == (
        ATH_HYDRATION_PENDING)


def test_supply_invariance_disproven_leaves_a_price_only_maximum():
    """A changed provider supply refuses conversion instead of guessing."""

    store = _store()
    _registered(store)
    _observe_spot(store)
    store.observe_provider_current(
        mint=WEN_MINT, price_usd=SPOT_PRICE,
        market_cap_usd=str(Decimal(SPOT_MARKET_CAP) * 2),
        observed_at="2026-07-30T22:23:00Z")
    _hydrate(store)
    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_price"] == PEAK_HIGH_PRICE          # price still wins
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_PENDING
    assert snapshot["ath_hydration_reason"] == (
        ATH_HYDRATION_MARKET_CAP_UNCONVERTED)


def test_partial_observation_never_downgrades_a_proven_window():
    """A later partial observation cannot un-hydrate a verified record."""

    store = _hydrated_store()
    assert store.snapshot(WEN_MINT)["ath_hydration_status"] == (
        ATH_HYDRATION_COMPLETE)
    # A legacy partial token-OHLCV observation contributes nothing canonical.
    store.observe_ohlcv_high(
        mint=WEN_MINT, high_price_usd=SPOT_PRICE,
        candle_timestamp=PEAK_CANDLE_UTC, history_complete=False,
        interval="1m", time_from_unix=MIGRATION_UNIX + 300,
        time_to_unix=COMPOSE_UNIX)
    # And a failed later V3 attempt only names its reason; it can never
    # regress the proven window, cursor or peaks.
    store.note_v3_pending(WEN_MINT, "ATH_V3_RATE_LIMITED")
    snapshot = store.snapshot(WEN_MINT)
    assert snapshot["ath_hydration_status"] == ATH_HYDRATION_COMPLETE
    assert snapshot["ath_v3_pair"]["window_from_unix"] == ANCHOR_ALIGNED_UNIX
    assert snapshot["ath_v3_pair"]["history_complete"] is True
    assert Decimal(snapshot["ath_market_cap"]) == EXPECTED_ATH_MARKET_CAP
