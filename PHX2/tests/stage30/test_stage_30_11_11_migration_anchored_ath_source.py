"""Stage 30.11.11 migration-anchored ATH source behaviour tests.

Offline / fake-provider only. Proves the committed migration-anchored ATH source:

  * anchors the OHLCV window at ``time_from == migration_unix`` (NEVER the sliding
    ``now - floor(elapsed_h)*3600`` window that clipped the audit's real peak);
  * selects the finest interval whose candle count fits the provider cap;
  * resolves the EARLY post-migration peak (0.000028368813970331733) over a later
    lower candle (0.0000133474);
  * yields the correct fractional drop (~0.8924) and tier (Tier 3, NOT Tier 2)
    through the committed Stage 30.1 ``decide_tier``;
  * produces a committed Stage 27.4 ``AthContextRecord`` that is PRESENT +
    POST_MIGRATION_ONLY + FROM_POST_MIGRATION_ATH;
  * fails closed (read_ath_context -> None) on missing / future / unparseable
    anchor, empty OHLCV, and an uncoverable (too-long) window.

No live call, no provider, no env read, no Discord / webhook / transport.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Optional

import pytest

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_PRESENT,
    MigrationContextRecord,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    AthContextRecord,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    DRAWDOWN_BASIS_NOT_APPLICABLE,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    TIER_REASON_TIER_3_IN_BAND,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
)
from PHX2.stage30.tier_decision_projector import decide_tier
from PHX2.stage30.stage30_11_11_migration_anchored_ath_source import (
    ANCHORED_ATH_REASON_ATH_SOURCE_EMPTY,
    ANCHORED_ATH_REASON_BLANK_CANDIDATE_MINT,
    ANCHORED_ATH_REASON_MIGRATION_ANCHOR_IN_FUTURE,
    ANCHORED_ATH_REASON_MISSING_MIGRATION_ANCHOR,
    ANCHORED_ATH_REASON_NOT_POST_MIGRATION_ONLY,
    ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
    ANCHORED_ATH_REASON_UNPARSEABLE_MIGRATION_ANCHOR,
    ANCHORED_ATH_REASON_WINDOW_TOO_LONG,
    Stage30_11_11MigrationAnchoredAthContextSource,
    build_migration_anchored_ath_context_source,
    select_anchored_ohlcv_type,
)


# Real Pump.fun migrated mint (matches the audit + prior ceremonies).
MINT = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
GOOD_KEY = "abcd1234efgh5678ijkl9012mnop3456"
GOOD_URL = "https://aaaa-bbbb.example"

MIGRATION_ANCHOR = "2026-06-06T06:14:10Z"
NOW = datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)

CURRENT_PRICE = "0.000003053202401565669"
PEAK_ATH = "0.000028368813970331733"          # ~06:16Z, the real early peak
LATER_LOWER = "0.0000133474"                   # ~07:30Z, the clipped-window value


def _secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=GOOD_KEY, _base_url=GOOD_URL)


def _unix(iso: str) -> int:
    return int(
        datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    )


MIGRATION_UNIX = _unix(MIGRATION_ANCHOR)
NOW_UNIX = int(NOW.timestamp())
PEAK_UNIX = int(datetime(2026, 6, 6, 6, 15, 0, tzinfo=timezone.utc).timestamp())
LATER_UNIX = int(datetime(2026, 6, 6, 7, 30, 0, tzinfo=timezone.utc).timestamp())


def _price_body() -> dict:
    return {
        "success": True,
        "data": {"value": CURRENT_PRICE, "updateUnixTime": NOW_UNIX},
    }


def _ohlcv_body_with_peak() -> dict:
    return {
        "success": True,
        "data": {
            "items": [
                {"h": PEAK_ATH, "unixTime": PEAK_UNIX},
                {"h": LATER_LOWER, "unixTime": LATER_UNIX},
            ]
        },
    }


def _empty_ohlcv_body() -> dict:
    return {"success": True, "data": {"items": []}}


class FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed fake transport: /defi/price -> price body, /defi/ohlcv ->
    ohlcv body (or a refusal). Records every call so the anchored window params
    can be asserted. NEVER opens a socket.
    """

    def __init__(
        self,
        *,
        price_body: Optional[dict],
        ohlcv_body: Optional[dict],
        ohlcv_refusal: Optional[str] = None,
        fetched_at_utc: str = "2026-06-07T07:06:40+00:00",
    ) -> None:
        self._price_body = price_body
        self._ohlcv_body = ohlcv_body
        self._ohlcv_refusal = ohlcv_refusal
        self._fetched_at_utc = fetched_at_utc
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            {"path": path, "query_params": dict(query_params)}
        )
        if path == BIRDEYE_PATH_PRICE:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body=self._price_body,
                fetched_at_utc=self._fetched_at_utc,
            )
        if path == BIRDEYE_PATH_OHLCV:
            if self._ohlcv_refusal is not None:
                return Stage29_2BirdeyeHttpResult(
                    refusal_reason=self._ohlcv_refusal,
                    http_status_code=0,
                    body=None,
                    fetched_at_utc=self._fetched_at_utc,
                )
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body=self._ohlcv_body,
                fetched_at_utc=self._fetched_at_utc,
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=self._fetched_at_utc,
        )


def _source(transport: FakeBirdeyeTransport, *, now_utc: datetime = NOW):
    return build_migration_anchored_ath_context_source(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        now_utc=now_utc,
    )


def _ohlcv_call(transport: FakeBirdeyeTransport) -> dict:
    return next(c for c in transport.calls if c["path"] == BIRDEYE_PATH_OHLCV)


# ---------------------------------------------------------------------------
# Interval selection (unit)
# ---------------------------------------------------------------------------


def test_select_interval_picks_5m_for_the_et9km9_span() -> None:
    span = NOW_UNIX - MIGRATION_UNIX  # ~89550s
    # 1m would need ~1493 candles (> 1000 cap); 5m needs ~299 (<= cap).
    assert select_anchored_ohlcv_type(span) == "5m"


def test_select_interval_picks_1m_for_a_short_window() -> None:
    assert select_anchored_ohlcv_type(3600) == "1m"  # 1h -> 61 candles


def test_select_interval_none_for_uncoverable_window() -> None:
    # ~19 years: even 1D needs > 1000 candles.
    assert select_anchored_ohlcv_type(600_000_000) is None


def test_select_interval_none_for_nonpositive_span() -> None:
    assert select_anchored_ohlcv_type(0) is None
    assert select_anchored_ohlcv_type(-5) is None


# ---------------------------------------------------------------------------
# 1. Anchored time_from == migration (NOT the sliding now-lookback window)
# ---------------------------------------------------------------------------


def test_ohlcv_window_is_anchored_at_migration_not_sliding() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    src = _source(transport)
    src.read_ath_context(MINT, migration_event_time_utc=MIGRATION_ANCHOR)
    call = _ohlcv_call(transport)
    # ANCHORED at migration, NOT now - floor(elapsed_h)*3600.
    assert call["query_params"]["time_from"] == str(MIGRATION_UNIX)
    assert call["query_params"]["time_to"] == str(NOW_UNIX)
    sliding_time_from = NOW_UNIX - 24 * 3600  # floor(24.875h) lookback
    assert call["query_params"]["time_from"] != str(sliding_time_from)
    # The selected finest covering interval for the ~24.9h span.
    assert call["query_params"]["type"] == "5m"


# ---------------------------------------------------------------------------
# 2 + 11. Anchored window includes the early peak the sliding window clipped
# ---------------------------------------------------------------------------


def test_anchored_resolves_early_peak_over_later_lower_candle() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    src = _source(transport)
    result = src.resolve_anchored_ath(MINT, MIGRATION_ANCHOR)
    assert result.resolved is True
    assert result.reason == ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH
    # The true early peak wins, NOT the later lower candle the clipped window saw.
    assert result.ath_value == PEAK_ATH
    assert result.ath_value != LATER_LOWER


def test_live_gate_cannot_use_a_sliding_window_that_clips_the_peak() -> None:
    # The sliding window [now-24h, now] would START after the peak candle and
    # therefore EXCLUDE it; the anchored window [migration, now] includes it.
    sliding_time_from = NOW_UNIX - 24 * 3600
    assert MIGRATION_UNIX <= PEAK_UNIX < sliding_time_from
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    result = _source(transport).resolve_anchored_ath(MINT, MIGRATION_ANCHOR)
    assert result.time_from_unix == MIGRATION_UNIX
    assert result.ath_value == PEAK_ATH


# ---------------------------------------------------------------------------
# 3 + 4 + 5. Drawdown + tier correction + Stage 27.4 compatibility
# ---------------------------------------------------------------------------


def _present_migration_record() -> MigrationContextRecord:
    return MigrationContextRecord(
        token_mint=MINT,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        migration_event_id=None,
        migration_timestamp_utc=MIGRATION_ANCHOR,
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=None,
        observed_at_utc="2026-06-07T07:06:40Z",
        source_event_ref=None,
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def test_resolved_reading_is_present_post_migration_with_drawdown() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    reading = _source(transport).read_ath_context(
        MINT, migration_event_time_utc=MIGRATION_ANCHOR
    )
    assert isinstance(reading, AthContextRecord)
    assert reading.ath_status == ATH_STATUS_PRESENT
    assert (
        reading.ath_since_migration_status
        == ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
    )
    assert reading.drawdown_basis == DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
    assert reading.ath_value == PEAK_ATH
    assert reading.drawdown_from_ath is not None
    # Drawdown is the absolute delta abs(ATH - current), computed by Stage 27.4.
    expected_dd = Decimal(PEAK_ATH) - Decimal(CURRENT_PRICE)
    assert Decimal(reading.drawdown_from_ath) == expected_dd


def test_fractional_drop_is_about_0_8924() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    reading = _source(transport).read_ath_context(
        MINT, migration_event_time_utc=MIGRATION_ANCHOR
    )
    frac = Decimal(reading.drawdown_from_ath) / Decimal(reading.ath_value)
    assert Decimal("0.89") < frac < Decimal("0.90")
    assert abs(frac - Decimal("0.8924")) < Decimal("0.001")


def test_tier_is_tier_3_not_tier_2_with_the_corrected_ath() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    reading = _source(transport).read_ath_context(
        MINT, migration_event_time_utc=MIGRATION_ANCHOR
    )
    decision = decide_tier(
        ath_record=reading,
        migration_record=_present_migration_record(),
        basis=BASIS_PRICE,
        created_at_utc="2026-06-07T07:06:40Z",
        mint=MINT,
    )
    assert decision.tier_token == TIER_TOKEN_TIER_3
    assert decision.tier_reason == TIER_REASON_TIER_3_IN_BAND
    assert decision.tier_token != TIER_TOKEN_TIER_2


def test_tier_would_be_tier_2_with_the_clipped_ath_regression_guard() -> None:
    # Sanity: with the WRONG (clipped) ATH the committed tier is Tier 2 -- this
    # is exactly the bug Stage 30.11.11 fixes by anchoring the window. Build an
    # ATH record carrying the clipped value and confirm it mis-tiers to Tier 2,
    # proving the tier swing is driven entirely by the ATH value.
    clipped = AthContextRecord(
        token_mint=MINT,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        ath_value=LATER_LOWER,
        ath_unit="USD",
        ath_source="birdeye_defi_ohlcv",
        ath_observed_at_utc="2026-06-06T07:30:00Z",
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_from_ath=str(Decimal(LATER_LOWER) - Decimal(CURRENT_PRICE)),
        drawdown_unit="USD",
        drawdown_basis=DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=ATH_STATUS_PRESENT,
        ath_reason="OK",
        schema_version="stage27_v0_price_ath_context",
    )
    decision = decide_tier(
        ath_record=clipped,
        migration_record=_present_migration_record(),
        basis=BASIS_PRICE,
        created_at_utc="2026-06-07T07:06:40Z",
        mint=MINT,
    )
    assert decision.tier_token == TIER_TOKEN_TIER_2


# ---------------------------------------------------------------------------
# 6-9. Fail-closed paths
# ---------------------------------------------------------------------------


def test_fail_closed_missing_anchor() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    src = _source(transport)
    result = src.resolve_anchored_ath(MINT, None)
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_MISSING_MIGRATION_ANCHOR
    assert src.read_ath_context(MINT, migration_event_time_utc=None) is None
    # No provider call on a missing anchor.
    assert transport.calls == []


def test_fail_closed_unparseable_anchor() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    result = _source(transport).resolve_anchored_ath(MINT, "not-a-timestamp")
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_UNPARSEABLE_MIGRATION_ANCHOR


def test_fail_closed_future_anchor() -> None:
    future = (NOW + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    src = _source(transport)
    result = src.resolve_anchored_ath(MINT, future)
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_MIGRATION_ANCHOR_IN_FUTURE
    assert src.read_ath_context(MINT, migration_event_time_utc=future) is None


def test_fail_closed_blank_mint() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    result = _source(transport).resolve_anchored_ath("  ", MIGRATION_ANCHOR)
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_BLANK_CANDIDATE_MINT


def test_fail_closed_empty_ohlcv() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_empty_ohlcv_body()
    )
    src = _source(transport)
    result = src.resolve_anchored_ath(MINT, MIGRATION_ANCHOR)
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_ATH_SOURCE_EMPTY
    assert (
        src.read_ath_context(MINT, migration_event_time_utc=MIGRATION_ANCHOR)
        is None
    )


def test_fail_closed_window_too_long() -> None:
    # Migration ~19 years before now: no allowed interval can cover the window.
    old_anchor = "2007-01-01T00:00:00Z"
    transport = FakeBirdeyeTransport(
        price_body=_price_body(), ohlcv_body=_ohlcv_body_with_peak()
    )
    src = _source(transport)
    result = src.resolve_anchored_ath(MINT, old_anchor)
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_WINDOW_TOO_LONG
    # Fail closed BEFORE any provider call (no silent truncation).
    assert transport.calls == []
    assert (
        src.read_ath_context(MINT, migration_event_time_utc=old_anchor) is None
    )


def test_read_ath_context_returns_none_on_source_error() -> None:
    transport = FakeBirdeyeTransport(
        price_body=_price_body(),
        ohlcv_body=None,
        ohlcv_refusal=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    )
    src = _source(transport)
    assert (
        src.read_ath_context(MINT, migration_event_time_utc=MIGRATION_ANCHOR)
        is None
    )


def test_stale_current_price_fails_closed_no_resolution() -> None:
    """Stage 30.11.12: a current price fetched OLDER than the staleness
    threshold makes the committed Stage 27.4 price STALE, so
    ``_compute_drawdown`` yields no drawdown and the anchored source
    fails closed -- no usable drawdown, no RESOLVED_ATH, no private
    ping. The anchored OHLCV peak is otherwise valid, proving it is the
    STALE CURRENT PRICE (not a missing ATH) that closes the gate.
    """
    # fetched_at_utc is ~1h before NOW (2026-06-07T07:06:40Z), far past
    # the 300s default staleness threshold -> Stage 27.4 PRICE_STATUS_STALE.
    transport = FakeBirdeyeTransport(
        price_body=_price_body(),
        ohlcv_body=_ohlcv_body_with_peak(),
        fetched_at_utc="2026-06-07T06:00:00+00:00",
    )
    src = _source(transport)
    result = src.resolve_anchored_ath(MINT, MIGRATION_ANCHOR)

    # Fail closed: NOT resolved, surfaced reason is the basis flip
    # (drawdown withheld -> basis NOT_APPLICABLE -> not post-migration-only).
    assert result.resolved is False
    assert result.reason == ANCHORED_ATH_REASON_NOT_POST_MIGRATION_ONLY

    # The ATH itself rode through PRESENT with its value intact: it is the
    # stale CURRENT price, not a missing/absent ATH, that closes the gate.
    assert result.ath_status == ATH_STATUS_PRESENT
    assert result.ath_value == PEAK_ATH

    # No usable drawdown can come from a stale current price.
    assert result.drawdown_from_ath is None
    assert result.drawdown_basis == DRAWDOWN_BASIS_NOT_APPLICABLE

    # The resolver-facing reading is suppressed to None when unresolved,
    # so Stage 30.11.10 can never bind a RESOLVED_ATH from a stale price.
    assert (
        src.read_ath_context(MINT, migration_event_time_utc=MIGRATION_ANCHOR)
        is None
    )
