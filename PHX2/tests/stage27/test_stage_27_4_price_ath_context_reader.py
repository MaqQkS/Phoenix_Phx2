"""Stage 27.4 price / ATH / migration context reader tests.

Pins:

  * Stage 27.4 source Protocols are injectable (tests substitute
    fakes); no real network is ever reached.
  * The injected clock is the sole source of wall time
    (``observed_at_utc`` / ``staleness_seconds`` /
    ``age_since_migration_seconds`` are clock-driven).
  * Price context covers PRESENT / STALE / UNAVAILABLE /
    SOURCE_ERROR / UNSUPPORTED_PAIR.
  * ATH context covers PRESENT (POST_MIGRATION_ONLY +
    MAY_INCLUDE_PRE_MIGRATION) / UNAVAILABLE / SOURCE_ERROR /
    UNSUPPORTED_PAIR.
  * Migration context covers PRESENT (trusted) / UNTRUSTED /
    MISSING (no event, missing timestamp, malformed timestamp) /
    SOURCE_ERROR / UNSUPPORTED_PAIR.
  * UNKNOWN pair stays LIVE-suppressed; DISAGREE pair stays
    LIVE-suppressed.
  * USDC pair remains observe-only; USDC price/ATH never
    re-attributed to the SOL lane.
  * USDC / UNKNOWN / DISAGREE NEVER map to ``EXISTING_SOL_LANE``.
  * Stale price is explicit (``staleness_seconds`` exceeds
    threshold => ``STALE``).
  * Missing price uses ``None``, NEVER ``0.0``.
  * Missing ATH is explicit.
  * Missing migration timestamp does NOT crash.
  * Pre-migration wick data is NOT merged into post-migration
    ATH; downgrades to ``MAY_INCLUDE_PRE_MIGRATION``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple, Optional

import pytest

from PHX2.stage27 import migration_context_models as mig
from PHX2.stage27 import price_ath_context_contracts as errors
from PHX2.stage27 import price_ath_context_models as m
from PHX2.stage27 import price_ath_context_reader as reader
from PHX2.stage27.pair_detection_constants import (
    BONDING_CURVE_VERSION_SOL_LEGACY,
    BONDING_CURVE_VERSION_USDC_FIXED,
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    KNOWN_USDC_MINT,
    KNOWN_WRAPPED_SOL_MINT,
    LIVE_POLICY_DRY_RUN_ONLY,
    LIVE_POLICY_LIVE_ALLOWED,
    LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
    LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
    PAIR_DETECTION_CONFIDENCE_HIGH,
    PAIR_DETECTION_CONFIDENCE_NONE,
    PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
    PAIR_DETECTION_REASON_NO_EVIDENCE,
    PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE,
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    PAIR_TYPE_PUMP_SOL,
    PAIR_TYPE_PUMP_USDC,
    PAIR_TYPE_UNKNOWN,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_REASON_OK,
    COMPOSITION_STATUS_COMPOSED,
    EVENT_KIND_SWAP,
    ProviderIngestOutputRecord,
    STAGE27_3_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Test fixtures: deterministic clock + fake sources
# ---------------------------------------------------------------------------


_OBSERVED_AT = datetime(2026, 5, 22, 12, 0, 30, tzinfo=timezone.utc)
_OBSERVED_AT_ISO = "2026-05-22T12:00:30+00:00"


def _frozen_clock() -> reader.FrozenStage27_4Clock:
    return reader.FrozenStage27_4Clock(fixed_utc=_OBSERVED_AT)


def _ingest_output_sol_confirmed(
    *,
    token_mint: str = "MintAAA",
) -> ProviderIngestOutputRecord:
    return ProviderIngestOutputRecord(
        provider_id="fake-helius",
        provider_event_id="prov-evt-1",
        normalized_event_id="norm-evt-1",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        pair_quote_asset=QUOTE_ASSET_SOL,
        pair_pair_type=PAIR_TYPE_PUMP_SOL,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_SOL_LEGACY,
        pair_detection_status=PAIR_DETECTION_STATUS_CONFIRMED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
        pair_detection_reason=(
            PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT
        ),
        pair_live_policy=LIVE_POLICY_LIVE_ALLOWED,
        pair_calibration_lane=CALIBRATION_LANE_EXISTING_SOL_LANE,
        raw_capture_ref="rcap-1",
        source_summary="fake summary",
        composition_status=COMPOSITION_STATUS_COMPOSED,
        composition_reason=COMPOSITION_REASON_OK,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


def _ingest_output_usdc_confirmed() -> ProviderIngestOutputRecord:
    return _ingest_output_sol_confirmed()._replace(
        quote_mint=KNOWN_USDC_MINT,
        pair_quote_asset=QUOTE_ASSET_USDC,
        pair_pair_type=PAIR_TYPE_PUMP_USDC,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_USDC_FIXED,
        pair_live_policy=LIVE_POLICY_DRY_RUN_ONLY,
        pair_calibration_lane=CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    )


def _ingest_output_unknown_pair() -> ProviderIngestOutputRecord:
    return _ingest_output_sol_confirmed()._replace(
        quote_mint=None,
        pair_quote_asset=QUOTE_ASSET_UNKNOWN,
        pair_pair_type=PAIR_TYPE_UNKNOWN,
        pair_bonding_curve_version="UNKNOWN",
        pair_detection_status=PAIR_DETECTION_STATUS_UNRESOLVED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_NONE,
        pair_detection_reason=PAIR_DETECTION_REASON_NO_EVIDENCE,
        pair_live_policy=LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
        pair_calibration_lane=CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    )


def _ingest_output_disagree_pair() -> ProviderIngestOutputRecord:
    return _ingest_output_sol_confirmed()._replace(
        quote_mint=None,
        pair_quote_asset=QUOTE_ASSET_UNKNOWN,
        pair_pair_type=PAIR_TYPE_UNKNOWN,
        pair_bonding_curve_version="UNKNOWN",
        pair_detection_status=PAIR_DETECTION_STATUS_DISAGREE,
        pair_detection_confidence="LOW",
        pair_detection_reason=(
            PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE
        ),
        pair_live_policy=LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
        pair_calibration_lane=CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    )


# ---------------------------------------------------------------------------
# Fake source implementations
# ---------------------------------------------------------------------------


class _FakePriceSource(NamedTuple):
    snapshot: Optional[reader.PriceSourceSnapshot]
    raise_source_error: bool = False

    def read_price_snapshot(
        self, token_mint, *, pair_quote_asset
    ):
        if self.raise_source_error:
            raise errors.Stage27PriceSourceError(
                "SOURCE_FAILED", source_label="fake_price"
            )
        return self.snapshot


class _FakeAthSource(NamedTuple):
    snapshot: Optional[reader.AthSourceSnapshot]
    raise_source_error: bool = False

    def read_ath_snapshot(
        self, token_mint, *, pair_quote_asset
    ):
        if self.raise_source_error:
            raise errors.Stage27AthSourceError(
                "SOURCE_FAILED", source_label="fake_ath"
            )
        return self.snapshot


class _FakeMigrationSource(NamedTuple):
    snapshot: Optional[reader.MigrationSourceSnapshot]
    raise_source_error: bool = False

    def read_migration_snapshot(self, token_mint):
        if self.raise_source_error:
            raise errors.Stage27MigrationSourceError(
                "SOURCE_FAILED", source_label="fake_migration"
            )
        return self.snapshot


# ---------------------------------------------------------------------------
# Frozen clock pin
# ---------------------------------------------------------------------------


def test_frozen_clock_returns_fixed_utc():
    clk = _frozen_clock()
    assert clk.utc_now() == _OBSERVED_AT
    assert clk.utc_now().tzinfo is not None


# ---------------------------------------------------------------------------
# Price context: PRESENT
# ---------------------------------------------------------------------------


def test_price_context_present_for_sol_confirmed():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.000123",
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake_birdeye",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot,
        ingest,
        clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_PRESENT
    assert record.price_reason == m.PRICE_REASON_OK
    assert record.price_value == "0.000123"
    assert record.price_unit == m.PRICE_UNIT_SOL
    assert record.staleness_seconds == 5
    assert record.observed_at_utc == _OBSERVED_AT_ISO


def test_price_context_observed_uses_injected_clock():
    """The observed_at_utc field must come from the clock, not from
    ``datetime.now()``.
    """
    clk = reader.FrozenStage27_4Clock(
        fixed_utc=datetime(2099, 1, 1, tzinfo=timezone.utc)
    )
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="1.0",
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake",
        fetched_at_utc="2099-01-01T00:00:00+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=clk, staleness_threshold_seconds=60
    )
    assert record.observed_at_utc == "2099-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Price context: STALE
# ---------------------------------------------------------------------------


def test_price_context_stale_when_threshold_exceeded():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.0001",
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake",
        fetched_at_utc="2026-05-22T11:50:00+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_STALE
    assert (
        record.price_reason == m.PRICE_REASON_STALE_THRESHOLD_EXCEEDED
    )
    assert record.staleness_seconds == 630  # 10m 30s


# ---------------------------------------------------------------------------
# Price context: UNAVAILABLE
# ---------------------------------------------------------------------------


def test_price_context_unavailable_when_value_none():
    """Missing price must use None, NEVER ``0.0``."""
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value=None,
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake",
        fetched_at_utc=None,
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNAVAILABLE
    assert (
        record.price_reason == m.PRICE_REASON_SOURCE_RETURNED_NONE
    )
    assert record.price_value is None


def test_price_context_zero_value_is_present_not_missing():
    """``price_value == "0"`` is NOT the same as missing.

    Stage 27.4 never treats a numeric zero as "unknown".
    """
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0",
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_PRESENT
    assert record.price_value == "0"


# ---------------------------------------------------------------------------
# Price context: SOURCE_ERROR
# ---------------------------------------------------------------------------


def test_read_price_context_translates_source_error():
    ingest = _ingest_output_sol_confirmed()
    source = _FakePriceSource(snapshot=None, raise_source_error=True)
    record = reader.read_price_context(
        source, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_SOURCE_ERROR
    assert record.price_reason == m.PRICE_REASON_SOURCE_FAILED
    assert record.price_value is None
    # No raw payload smuggled into the SOURCE_ERROR record.
    assert record.price_source is None


def test_build_price_context_rejects_non_snapshot_input():
    ingest = _ingest_output_sol_confirmed()
    record = reader.build_price_context_record(
        "not a snapshot",  # type: ignore[arg-type]
        ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_SOURCE_ERROR
    assert (
        record.price_reason == m.PRICE_REASON_INVALID_SOURCE_SNAPSHOT
    )


# ---------------------------------------------------------------------------
# Price context: pair-aware (UNKNOWN / DISAGREE / USDC)
# ---------------------------------------------------------------------------


def test_price_context_unknown_pair_stays_unsupported():
    ingest = _ingest_output_unknown_pair()
    snapshot = reader.PriceSourceSnapshot(
        price_value="999",
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNSUPPORTED_PAIR
    assert (
        record.price_reason
        == m.PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    assert record.price_value is None
    # UNKNOWN pair NEVER routes to SOL lane.
    assert record.quote_asset == QUOTE_ASSET_UNKNOWN
    assert record.pair_type == PAIR_TYPE_UNKNOWN


def test_price_context_disagree_pair_stays_unsupported():
    ingest = _ingest_output_disagree_pair()
    snapshot = reader.PriceSourceSnapshot(
        price_value="999",
        price_unit=m.PRICE_UNIT_SOL,
        source_label="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNSUPPORTED_PAIR
    assert (
        record.price_reason
        == m.PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY
    )


def test_price_context_usdc_stays_usdc_lane():
    """USDC price MUST stay USDC; never re-attributed to SOL lane."""
    ingest = _ingest_output_usdc_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="1.23",
        price_unit=m.PRICE_UNIT_USDC,
        source_label="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_PRESENT
    assert record.price_reason == m.PRICE_REASON_USDC_OBSERVE_ONLY
    assert record.price_unit == m.PRICE_UNIT_USDC
    assert record.quote_asset == QUOTE_ASSET_USDC


def test_price_context_sol_pair_with_usdc_unit_rejected():
    """A SOL pair reporting USDC unit (or vice versa) is rejected.

    USDC price MUST NOT be silently converted into SOL-lane
    semantics.
    """
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.0001",
        price_unit=m.PRICE_UNIT_USDC,
        source_label="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNSUPPORTED_PAIR
    assert (
        record.price_reason
        == m.PRICE_REASON_UNSUPPORTED_QUOTE_ASSET
    )


# ---------------------------------------------------------------------------
# Stage 29.3C: USD price/ATH unit compatibility for SOL pair
# ---------------------------------------------------------------------------
#
# Birdeye returns price/ATH in USD by default. Stage 27.4 admits
# ``PRICE_UNIT_USD`` / ``ATH_UNIT_USD`` on a SOL pair as a Birdeye-
# compatible display unit. The pair's ``quote_asset`` stays SOL;
# only the display unit is USD. USDC and SOL units must still be
# routed through their own lanes; UNKNOWN / DISAGREE pairs stay
# suppressed regardless of unit.


def test_price_context_sol_pair_with_usd_unit_present():
    """SOL pair + Birdeye-style USD price unit MUST render as
    PRESENT, with ``quote_asset`` staying SOL (no silent promotion
    of the pair lane into USDC / UNKNOWN). The display unit stays
    USD; only the lane stays SOL.
    """
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.000036",
        price_unit=m.PRICE_UNIT_USD,
        source_label="birdeye_defi_price",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_PRESENT
    assert record.price_reason == m.PRICE_REASON_OK
    assert record.price_value == "0.000036"
    assert record.price_unit == m.PRICE_UNIT_USD
    # Pair lane is unchanged -- SOL stays SOL.
    assert record.quote_asset == QUOTE_ASSET_SOL
    assert record.pair_type == PAIR_TYPE_PUMP_SOL


def test_price_context_unknown_pair_with_usd_unit_still_suppressed():
    """UNKNOWN pair MUST stay UNSUPPORTED regardless of the
    upstream display unit. USD does NOT unlock UNKNOWN pairs.
    """
    ingest = _ingest_output_unknown_pair()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.000036",
        price_unit=m.PRICE_UNIT_USD,
        source_label="birdeye_defi_price",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNSUPPORTED_PAIR
    assert (
        record.price_reason
        == m.PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    assert record.price_value is None
    assert record.quote_asset == QUOTE_ASSET_UNKNOWN


def test_price_context_disagree_pair_with_usd_unit_still_suppressed():
    """DISAGREE pair MUST stay UNSUPPORTED regardless of the
    upstream display unit. USD does NOT unlock DISAGREE pairs.
    """
    ingest = _ingest_output_disagree_pair()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.000036",
        price_unit=m.PRICE_UNIT_USD,
        source_label="birdeye_defi_price",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNSUPPORTED_PAIR
    assert (
        record.price_reason
        == m.PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY
    )


def test_price_context_usdc_pair_with_usd_unit_stays_observe_only():
    """USDC pair with USD display unit MUST stay USDC observe-only.

    USD is admitted on the USDC pair (since Birdeye reports USD for
    every pair) but the lane stays USDC -- the price is NOT silently
    promoted into the SOL calibration lane.
    """
    ingest = _ingest_output_usdc_confirmed()
    snapshot = reader.PriceSourceSnapshot(
        price_value="0.000036",
        price_unit=m.PRICE_UNIT_USD,
        source_label="birdeye_defi_price",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
    )
    record = reader.build_price_context_record(
        snapshot, ingest, clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_PRESENT
    assert record.price_reason == m.PRICE_REASON_USDC_OBSERVE_ONLY
    assert record.price_unit == m.PRICE_UNIT_USD
    # USDC lane must NEVER be silently promoted into SOL.
    assert record.quote_asset == QUOTE_ASSET_USDC
    assert record.pair_type == PAIR_TYPE_PUMP_USDC


# ---------------------------------------------------------------------------
# ATH context: PRESENT (POST_MIGRATION_ONLY)
# ---------------------------------------------------------------------------


def _present_migration_record() -> mig.MigrationContextRecord:
    return mig.MigrationContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=mig.MIGRATION_STATUS_PRESENT,
        migration_reason=mig.MIGRATION_REASON_OK,
        age_since_migration_seconds=3600,
        observed_at_utc=_OBSERVED_AT_ISO,
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
        schema_version=mig.STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def _present_price_record_sol() -> m.PriceContextRecord:
    return m.PriceContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        price_value="0.0001",
        price_unit=m.PRICE_UNIT_SOL,
        price_source="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
        observed_at_utc=_OBSERVED_AT_ISO,
        staleness_seconds=5,
        price_status=m.PRICE_STATUS_PRESENT,
        price_reason=m.PRICE_REASON_OK,
        schema_version=m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def test_ath_context_post_migration_only_when_window_and_migration_present():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    record = reader.build_ath_context_record(
        snapshot,
        ingest,
        migration_record=_present_migration_record(),
        current_price_record=_present_price_record_sol(),
    )
    assert record.ath_status == m.ATH_STATUS_PRESENT
    assert record.ath_reason == m.ATH_REASON_OK
    assert (
        record.ath_since_migration_status
        == m.ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
    )
    assert record.drawdown_basis == m.DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
    # 0.0009 - 0.0001 = 0.0008
    assert record.drawdown_from_ath == "0.0008"


def test_ath_context_drawdown_is_absolute_delta_at_memecoin_scale():
    """Stage 27.4 keeps ``drawdown_from_ath`` as the ABSOLUTE ``ATH - price``
    delta, even at sub-micro memecoin prices. The Stage 30.1 tier-units fix
    converts to a fraction DOWNSTREAM; Stage 27.4 itself NEVER emits a
    fractional drawdown. Locks the absolute meaning the fix relies on.
    """
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.00000100",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    price = _present_price_record_sol()._replace(price_value="0.00000045")
    record = reader.build_ath_context_record(
        snapshot,
        ingest,
        migration_record=_present_migration_record(),
        current_price_record=price,
    )
    assert record.ath_status == m.ATH_STATUS_PRESENT
    assert record.drawdown_basis == m.DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
    # 0.00000100 - 0.00000045 = 0.00000055 (absolute delta, NOT a fraction).
    assert record.drawdown_from_ath == "0.00000055"
    assert record.drawdown_unit == m.ATH_UNIT_SOL


def test_ath_context_no_drawdown_when_current_price_stale():
    """Stage 30.11.12 fail-closed: a STALE current price preserves the
    PRESENT post-migration ATH (value + window survive) but yields NO
    usable drawdown, so a stale current price can never drive a
    drawdown / tier / private ping. Only ``PRICE_STATUS_PRESENT`` may
    produce a drawdown.
    """
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    stale_price = _present_price_record_sol()._replace(
        price_status=m.PRICE_STATUS_STALE,
        price_reason=m.PRICE_REASON_STALE_THRESHOLD_EXCEEDED,
        staleness_seconds=630,
    )
    record = reader.build_ath_context_record(
        snapshot,
        ingest,
        migration_record=_present_migration_record(),
        current_price_record=stale_price,
    )
    # ATH itself stays PRESENT + POST_MIGRATION_ONLY with its value
    # intact -- only the drawdown is withheld because the current
    # price is stale.
    assert record.ath_status == m.ATH_STATUS_PRESENT
    assert (
        record.ath_since_migration_status
        == m.ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
    )
    assert record.ath_value == "0.0009"
    # Fail closed: NO usable drawdown from a stale current price.
    assert record.drawdown_from_ath is None
    assert record.drawdown_basis == m.DRAWDOWN_BASIS_NOT_APPLICABLE


# ---------------------------------------------------------------------------
# ATH context: pre-migration data rejected
# ---------------------------------------------------------------------------


def test_ath_context_may_include_pre_migration_when_window_unconfirmed():
    """Stage 27.4 NEVER claims POST_MIGRATION_ONLY when the
    upstream window did not promise it.
    """
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=None,
    )
    record = reader.build_ath_context_record(
        snapshot,
        ingest,
        migration_record=_present_migration_record(),
        current_price_record=_present_price_record_sol(),
    )
    assert record.ath_status == m.ATH_STATUS_PRESENT
    assert (
        record.ath_since_migration_status
        == m.ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
    )
    assert (
        record.ath_reason
        == m.ATH_REASON_PRE_MIGRATION_DATA_REJECTED
    )
    # Drawdown is NOT computed for unverified post-migration claim.
    assert record.drawdown_from_ath is None
    assert record.drawdown_basis == m.DRAWDOWN_BASIS_NOT_APPLICABLE


def test_ath_context_may_include_pre_migration_when_migration_absent():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    record = reader.build_ath_context_record(
        snapshot,
        ingest,
        migration_record=None,
        current_price_record=_present_price_record_sol(),
    )
    assert (
        record.ath_since_migration_status
        == m.ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
    )


# ---------------------------------------------------------------------------
# ATH context: UNAVAILABLE / NOT_APPLICABLE
# ---------------------------------------------------------------------------


def test_ath_context_unavailable_when_value_none():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value=None,
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc=None,
        window_starts_post_migration=None,
    )
    record = reader.build_ath_context_record(
        snapshot, ingest,
    )
    assert record.ath_status == m.ATH_STATUS_UNAVAILABLE
    assert record.ath_reason == m.ATH_REASON_NO_OBSERVATIONS
    assert record.ath_value is None


def test_read_ath_context_translates_source_error():
    ingest = _ingest_output_sol_confirmed()
    source = _FakeAthSource(snapshot=None, raise_source_error=True)
    record = reader.read_ath_context(source, ingest)
    assert record.ath_status == m.ATH_STATUS_SOURCE_ERROR
    assert record.ath_reason == m.ATH_REASON_SOURCE_FAILED


# ---------------------------------------------------------------------------
# ATH context: pair-aware
# ---------------------------------------------------------------------------


def test_ath_context_unknown_pair_unsupported():
    ingest = _ingest_output_unknown_pair()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    record = reader.build_ath_context_record(snapshot, ingest)
    assert record.ath_status == m.ATH_STATUS_UNSUPPORTED_PAIR
    assert (
        record.ath_reason == m.ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    assert record.quote_asset == QUOTE_ASSET_UNKNOWN


def test_ath_context_disagree_pair_unsupported():
    ingest = _ingest_output_disagree_pair()
    snapshot = reader.AthSourceSnapshot(
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    record = reader.build_ath_context_record(snapshot, ingest)
    assert record.ath_status == m.ATH_STATUS_UNSUPPORTED_PAIR
    assert (
        record.ath_reason == m.ATH_REASON_DISAGREE_PAIR_OBSERVE_ONLY
    )


def test_ath_context_usdc_stays_observe_only_even_when_present():
    ingest = _ingest_output_usdc_confirmed()
    snapshot = reader.AthSourceSnapshot(
        ath_value="3.5",
        ath_unit=m.ATH_UNIT_USDC,
        source_label="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    record = reader.build_ath_context_record(
        snapshot,
        ingest,
        migration_record=_present_migration_record()._replace(
            pair_type=PAIR_TYPE_PUMP_USDC,
            quote_asset=QUOTE_ASSET_USDC,
        ),
    )
    assert record.ath_reason == m.ATH_REASON_USDC_OBSERVE_ONLY
    assert record.ath_unit == m.ATH_UNIT_USDC
    assert record.quote_asset == QUOTE_ASSET_USDC


# ---------------------------------------------------------------------------
# Migration context: PRESENT (trusted)
# ---------------------------------------------------------------------------


def test_migration_context_present_for_trusted_source():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=(
            mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert record.migration_status == mig.MIGRATION_STATUS_PRESENT
    assert record.migration_reason == mig.MIGRATION_REASON_OK
    assert record.age_since_migration_seconds == 3630  # 1h 30s
    assert record.observed_at_utc == _OBSERVED_AT_ISO


def test_migration_context_operator_override_is_trusted():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=mig.MIGRATION_SOURCE_OPERATOR_OVERRIDE,
        source_event_ref=None,
        raw_capture_ref=None,
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert record.migration_status == mig.MIGRATION_STATUS_PRESENT


# ---------------------------------------------------------------------------
# Migration context: UNTRUSTED
# ---------------------------------------------------------------------------


def test_migration_context_untrusted_for_provider_enriched():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=mig.MIGRATION_SOURCE_PROVIDER_ENRICHED,
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert record.migration_status == mig.MIGRATION_STATUS_UNTRUSTED
    assert (
        record.migration_reason
        == mig.MIGRATION_REASON_SOURCE_NOT_TRUSTED
    )


# ---------------------------------------------------------------------------
# Migration context: MISSING
# ---------------------------------------------------------------------------


def test_migration_context_no_event():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source=mig.MIGRATION_SOURCE_UNKNOWN,
        source_event_ref=None,
        raw_capture_ref=None,
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert record.migration_status == mig.MIGRATION_STATUS_MISSING
    assert (
        record.migration_reason
        == mig.MIGRATION_REASON_NO_MIGRATION_EVENT
    )


def test_migration_context_missing_timestamp_does_not_crash():
    """A missing migration timestamp MUST NOT crash the builder."""
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc=None,
        migration_source=(
            mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert record.migration_status == mig.MIGRATION_STATUS_MISSING
    assert (
        record.migration_reason
        == mig.MIGRATION_REASON_MISSING_TIMESTAMP
    )
    assert record.age_since_migration_seconds is None


def test_migration_context_malformed_timestamp_does_not_crash():
    ingest = _ingest_output_sol_confirmed()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc="not-a-timestamp",
        migration_source=(
            mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert record.migration_status == mig.MIGRATION_STATUS_MISSING
    assert (
        record.migration_reason
        == mig.MIGRATION_REASON_MALFORMED_TIMESTAMP
    )


def test_read_migration_context_translates_source_error():
    ingest = _ingest_output_sol_confirmed()
    source = _FakeMigrationSource(
        snapshot=None, raise_source_error=True
    )
    record = reader.read_migration_context(
        source, ingest, clock=_frozen_clock()
    )
    assert (
        record.migration_status == mig.MIGRATION_STATUS_SOURCE_ERROR
    )
    assert (
        record.migration_reason == mig.MIGRATION_REASON_SOURCE_FAILED
    )


# ---------------------------------------------------------------------------
# Migration context: pair-aware
# ---------------------------------------------------------------------------


def test_migration_context_unknown_pair_unsupported():
    ingest = _ingest_output_unknown_pair()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=(
            mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert (
        record.migration_status
        == mig.MIGRATION_STATUS_UNSUPPORTED_PAIR
    )
    assert (
        record.migration_reason
        == mig.MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY
    )


def test_migration_context_disagree_pair_unsupported():
    ingest = _ingest_output_disagree_pair()
    snapshot = reader.MigrationSourceSnapshot(
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=(
            mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
    )
    record = reader.build_migration_context_record(
        snapshot, ingest, clock=_frozen_clock()
    )
    assert (
        record.migration_status
        == mig.MIGRATION_STATUS_UNSUPPORTED_PAIR
    )
    assert (
        record.migration_reason
        == mig.MIGRATION_REASON_DISAGREE_PAIR_OBSERVE_ONLY
    )


# ---------------------------------------------------------------------------
# USDC / UNKNOWN / DISAGREE NEVER reach EXISTING_SOL_LANE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ingest_builder",
    (
        _ingest_output_usdc_confirmed,
        _ingest_output_unknown_pair,
        _ingest_output_disagree_pair,
    ),
)
def test_non_sol_ingest_never_routes_through_sol_lane(ingest_builder):
    ingest = ingest_builder()
    assert ingest.pair_calibration_lane != CALIBRATION_LANE_EXISTING_SOL_LANE


# ---------------------------------------------------------------------------
# Source snapshots carry no raw-payload-class fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snapshot_cls",
    (
        reader.PriceSourceSnapshot,
        reader.AthSourceSnapshot,
        reader.MigrationSourceSnapshot,
    ),
)
def test_source_snapshots_carry_no_raw_payload_field(snapshot_cls):
    for field in snapshot_cls._fields:
        assert not m.is_forbidden_snapshot_field_name(field), (
            f"{snapshot_cls.__name__} carries forbidden field {field!r}"
        )


# ---------------------------------------------------------------------------
# Empty / missing token mint short-circuits the reader entry points
# ---------------------------------------------------------------------------


def test_read_price_context_short_circuits_when_token_mint_missing():
    ingest = _ingest_output_sol_confirmed()._replace(token_mint=None)
    record = reader.read_price_context(
        _FakePriceSource(snapshot=None),
        ingest,
        clock=_frozen_clock(),
        staleness_threshold_seconds=60,
    )
    assert record.price_status == m.PRICE_STATUS_UNSUPPORTED_PAIR


def test_read_ath_context_short_circuits_when_token_mint_missing():
    ingest = _ingest_output_sol_confirmed()._replace(token_mint="")
    record = reader.read_ath_context(
        _FakeAthSource(snapshot=None), ingest,
    )
    assert record.ath_status == m.ATH_STATUS_UNSUPPORTED_PAIR


def test_read_migration_context_short_circuits_when_token_mint_missing():
    ingest = _ingest_output_sol_confirmed()._replace(token_mint=None)
    record = reader.read_migration_context(
        _FakeMigrationSource(snapshot=None),
        ingest,
        clock=_frozen_clock(),
    )
    assert (
        record.migration_status
        == mig.MIGRATION_STATUS_UNSUPPORTED_PAIR
    )
