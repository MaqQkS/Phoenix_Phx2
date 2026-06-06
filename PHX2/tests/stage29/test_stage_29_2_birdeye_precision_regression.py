"""Stage 29.2 Birdeye sub-microdollar precision regression tests.

Root cause pinned by the Stage 30.11.10 real-data ATH/drawdown proof: the committed
``_format_decimal`` in both Stage 29.2 Birdeye source modules rendered FLOAT inputs
via ``format(value, "f")``, which defaults to 6 decimal places. A real Birdeye price
such as ``3.9914185551409724e-07`` therefore collapsed to ``"0.000000"`` -> ``"0.0"``,
and the matching OHLCV high ``4.2789e-07`` collapsed to ``"0.0"`` too -- so the real
post-migration drawdown (~-6.72%) was reported as ``"0.0"``.

The fix renders the float via ``Decimal(repr(value))`` -> ``format(Decimal, "f")``,
preserving FULL precision as plain (non-exponent) decimal text. These tests pin the
preserved values end to end through the committed Stage 29.2 sources and the committed
Stage 27.4 drawdown brain.

Pure / offline: a deterministic in-memory fake transport; NO network, NO env read, NO
real API key, NO Discord / transport / wallet surface. Touches NO Stage 30 module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_REPORTING_UNIT_USD,
)
from PHX2.stage29.stage29_2_birdeye_ath_source import (
    Stage29_2BirdeyeAthSource,
    fetch_birdeye_ath_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_MISSING,
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_PRICE_STATUS_MISSING,
    BIRDEYE_PRICE_STATUS_PRESENT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
    fetch_birdeye_price_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)

# The real values Birdeye returned for the proven migrated mint
# (k85BpCNVEcLGCzwgKTi3ho3fRjg5Do8Xpo9VrcMpump) during the Stage 30.11.10 proof.
GOOD_MINT = "k85BpCNVEcLGCzwgKTi3ho3fRjg5Do8Xpo9VrcMpump"
REAL_PRICE_FLOAT = 3.9914185551409724e-07
# Expected canonical text after the fix (Decimal(repr(float)) -> plain decimal):
REAL_PRICE_TEXT = "0.00000039914185551409724"
# OHLCV high per the patch spec example.
HIGH_FLOAT = 4.2789e-07
HIGH_TEXT = "0.00000042789"
# Exact drawdown (HIGH_TEXT - REAL_PRICE_TEXT) via Decimal math.
DRAWDOWN_TEXT = "0.00000002874814448590276"


def _secret() -> Stage29_2BirdeyeEndpointSecret:
    # Safe-shape fake secret (never a real key); shape mirrors the readiness tests.
    return Stage29_2BirdeyeEndpointSecret(
        _api_key="abcd1234efgh5678ijkl9012mnop3456",
        _base_url="https://public-api.birdeye.so",
    )


class _FakeTransport:
    """Deterministic Stage 29.2 transport returning one pinned JSON body.

    No network. Mirrors the committed transport's success-result shape.
    """

    def __init__(self, body: dict) -> None:
        self._body = body

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=self._body,
            fetched_at_utc="2026-06-06T04:43:51+00:00",
        )


class _FixedClock:
    def utc_now(self) -> datetime:
        return datetime(2026, 6, 6, 4, 43, 51, tzinfo=timezone.utc)


class _PresentMigration:
    migration_status = "PRESENT"


def _sol_confirmed_ingest(token_mint: str):
    from PHX2.stage27.pair_detection_constants import (
        BONDING_CURVE_VERSION_SOL_LEGACY,
        CALIBRATION_LANE_EXISTING_SOL_LANE,
        KNOWN_WRAPPED_SOL_MINT,
        LIVE_POLICY_LIVE_ALLOWED,
        PAIR_DETECTION_CONFIDENCE_HIGH,
        PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
        PAIR_DETECTION_STATUS_CONFIRMED,
        PAIR_TYPE_PUMP_SOL,
        QUOTE_ASSET_SOL,
    )
    from PHX2.stage27.provider_ingest_models import (
        COMPOSITION_REASON_OK,
        COMPOSITION_STATUS_COMPOSED,
        EVENT_KIND_SWAP,
        ProviderIngestOutputRecord,
        STAGE27_3_SCHEMA_VERSION,
    )

    return ProviderIngestOutputRecord(
        provider_id="p",
        provider_event_id="pe",
        normalized_event_id="ne",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-06-06T04:43:50+00:00",
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        pair_quote_asset=QUOTE_ASSET_SOL,
        pair_pair_type=PAIR_TYPE_PUMP_SOL,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_SOL_LEGACY,
        pair_detection_status=PAIR_DETECTION_STATUS_CONFIRMED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
        pair_detection_reason=PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
        pair_live_policy=LIVE_POLICY_LIVE_ALLOWED,
        pair_calibration_lane=CALIBRATION_LANE_EXISTING_SOL_LANE,
        raw_capture_ref="r",
        source_summary="s",
        composition_status=COMPOSITION_STATUS_COMPOSED,
        composition_reason=COMPOSITION_REASON_OK,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# 1. Birdeye PRICE source: sub-micro float preserves precision (was "0.0")
# ---------------------------------------------------------------------------


def test_price_sub_micro_float_preserves_precision() -> None:
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport(
            {"success": True, "data": {"value": REAL_PRICE_FLOAT}}
        ),
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_PRESENT
    assert snap.price_value is not None
    assert snap.price_value != "0.0"  # the bug
    assert snap.price_value == REAL_PRICE_TEXT
    assert Decimal(snap.price_value) == Decimal(repr(REAL_PRICE_FLOAT))
    assert snap.price_unit == BIRDEYE_REPORTING_UNIT_USD


def test_price_normal_float_unchanged() -> None:
    # Regression guard: a normal-magnitude float still renders exactly as before.
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport({"success": True, "data": {"value": 0.5}}),
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.price_value == "0.5"


# ---------------------------------------------------------------------------
# 2. Birdeye ATH source: sub-micro OHLCV high float preserves precision
# ---------------------------------------------------------------------------


def test_ath_sub_micro_high_float_preserves_precision() -> None:
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": HIGH_FLOAT, "unixTime": 1780632000},  # max
                {"h": REAL_PRICE_FLOAT, "unixTime": 1780633000},
            ]
        },
    }
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport(body),
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=25,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_PRESENT
    assert snap.ath_value is not None
    assert snap.ath_value != "0.0"  # the bug
    assert snap.ath_value == HIGH_TEXT
    assert Decimal(snap.ath_value) == Decimal(repr(HIGH_FLOAT))


# ---------------------------------------------------------------------------
# 3. Drawdown through committed Stage 27.4 preserves sub-micro precision
# ---------------------------------------------------------------------------


def test_drawdown_through_stage27_4_preserves_sub_micro_precision() -> None:
    from PHX2.stage27 import price_ath_context_reader as reader

    ingest = _sol_confirmed_ingest(GOOD_MINT)

    price_source = Stage29_2BirdeyePriceSource(
        transport=_FakeTransport(
            {"success": True, "data": {"value": REAL_PRICE_FLOAT}}
        ),
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    ath_source = Stage29_2BirdeyeAthSource(
        transport=_FakeTransport(
            {"success": True, "data": {"items": [{"h": HIGH_FLOAT, "unixTime": 1780632000}]}}
        ),
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        # Far-past anchor so the bounded window deterministically starts
        # post-migration (this test pins PRECISION, not migration semantics).
        migration_timestamp_utc="2020-01-01T00:00:00Z",
    )

    price_ctx = reader.read_price_context(
        price_source, ingest, clock=_FixedClock(), staleness_threshold_seconds=300
    )
    ath_rec = reader.read_ath_context(
        ath_source,
        ingest,
        migration_record=_PresentMigration(),
        current_price_record=price_ctx,
    )

    assert price_ctx.price_value == REAL_PRICE_TEXT
    assert ath_rec.ath_value == HIGH_TEXT
    assert ath_rec.ath_status == "PRESENT"
    assert ath_rec.ath_since_migration_status == "POST_MIGRATION_ONLY"
    assert ath_rec.drawdown_basis == "FROM_POST_MIGRATION_ATH"
    assert ath_rec.drawdown_from_ath is not None
    assert ath_rec.drawdown_from_ath != "0.0"  # the bug
    assert ath_rec.drawdown_from_ath == DRAWDOWN_TEXT
    assert Decimal(ath_rec.drawdown_from_ath) == (
        Decimal(HIGH_TEXT) - Decimal(REAL_PRICE_TEXT)
    )


# ---------------------------------------------------------------------------
# 4. Zero still canonical (current policy: a true 0 is a valid PRESENT price)
# ---------------------------------------------------------------------------


def test_zero_price_float_remains_canonical_zero() -> None:
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport({"success": True, "data": {"value": 0.0}}),
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_PRESENT
    assert snap.price_value == "0.0"


def test_zero_ath_high_float_remains_canonical_zero() -> None:
    body = {"success": True, "data": {"items": [{"h": 0.0, "unixTime": 1780632000}]}}
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport(body),
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_PRESENT
    assert snap.ath_value == "0.0"


# ---------------------------------------------------------------------------
# 5. NaN / Infinity still rejected (fail closed -> MISSING), unchanged
# ---------------------------------------------------------------------------


def test_nan_inf_price_floats_still_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        snap = fetch_birdeye_price_snapshot(
            base_mint=GOOD_MINT,
            transport=_FakeTransport({"success": True, "data": {"value": bad}}),
            endpoint_secret=_secret(),
            timeout_seconds=10,
        )
        assert snap.price_value is None, bad
        assert snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING, bad


def test_nan_inf_ath_highs_still_rejected() -> None:
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": float("nan"), "unixTime": 1780632000},
                {"h": float("inf"), "unixTime": 1780632900},
                {"h": float("-inf"), "unixTime": 1780633800},
            ]
        },
    }
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport(body),
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
    )
    assert snap.ath_value is None
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_MISSING


def test_negative_price_float_still_rejected() -> None:
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=_FakeTransport({"success": True, "data": {"value": -1.0}}),
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.price_value is None
    assert snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING
