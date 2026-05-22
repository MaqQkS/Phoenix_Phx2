"""Stage 27.4 combined live measurement context tests.

Pins:

  * Combined context covers COMPLETE / PARTIAL / MISSING_PRICE /
    MISSING_ATH / MISSING_MIGRATION / UNSUPPORTED_PAIR /
    SOURCE_ERROR.
  * SOL pair with all sub-contexts present + POST_MIGRATION_ONLY ATH
    + PRESENT migration -> COMPLETE.
  * USDC pair stays PARTIAL with the
    ``USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION`` warning.
  * UNKNOWN pair stays UNSUPPORTED_PAIR with the
    ``UNKNOWN_PAIR_SUPPRESSED_IN_LIVE`` warning.
  * DISAGREE pair stays UNSUPPORTED_PAIR with the
    ``DISAGREE_PAIR_SUPPRESSED_IN_LIVE`` warning.
  * STALE / UNAVAILABLE / SOURCE_ERROR sub-contexts surface the
    correct combined status and warning constant.
  * Closed-set vocabularies are stable.
  * ``LiveMeasurementContextRecord`` is an immutable NamedTuple.
  * ``measurement_warnings`` is a tuple of closed-set constants.
  * ``context_schema_version`` is the locked Stage 27.4
    measurement schema version.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from PHX2.stage27 import live_measurement_context as combined
from PHX2.stage27 import migration_context_models as mig
from PHX2.stage27 import price_ath_context_models as m
from PHX2.stage27 import price_ath_context_reader as reader
from PHX2.stage27.pair_detection_constants import (
    BONDING_CURVE_VERSION_SOL_LEGACY,
    BONDING_CURVE_VERSION_USDC_FIXED,
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    KNOWN_USDC_MINT,
    KNOWN_WRAPPED_SOL_MINT,
    LIVE_POLICY_DRY_RUN_ONLY,
    LIVE_POLICY_LIVE_ALLOWED,
    LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
    LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
    PAIR_DETECTION_CONFIDENCE_HIGH,
    PAIR_DETECTION_CONFIDENCE_LOW,
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
    COMPOSITION_REASON_MISSING_TOKEN_MINT,
    COMPOSITION_REASON_OK,
    COMPOSITION_REASON_PAIR_DISAGREE,
    COMPOSITION_REASON_PAIR_UNRESOLVED,
    COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND,
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    EVENT_KIND_SWAP,
    EVENT_KIND_UNKNOWN,
    ProviderIngestOutputRecord,
    STAGE27_3_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


_OBSERVED_AT = datetime(2026, 5, 22, 12, 0, 30, tzinfo=timezone.utc)
_OBSERVED_AT_ISO = "2026-05-22T12:00:30+00:00"


def _ingest_sol_composed() -> ProviderIngestOutputRecord:
    return ProviderIngestOutputRecord(
        provider_id="fake-helius",
        provider_event_id="prov-1",
        normalized_event_id="norm-1",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint="MintAAA",
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        pair_quote_asset=QUOTE_ASSET_SOL,
        pair_pair_type=PAIR_TYPE_PUMP_SOL,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_SOL_LEGACY,
        pair_detection_status=PAIR_DETECTION_STATUS_CONFIRMED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
        pair_detection_reason=PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
        pair_live_policy=LIVE_POLICY_LIVE_ALLOWED,
        pair_calibration_lane=CALIBRATION_LANE_EXISTING_SOL_LANE,
        raw_capture_ref="rcap-1",
        source_summary="fake",
        composition_status=COMPOSITION_STATUS_COMPOSED,
        composition_reason=COMPOSITION_REASON_OK,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


def _ingest_usdc_composed() -> ProviderIngestOutputRecord:
    return _ingest_sol_composed()._replace(
        quote_mint=KNOWN_USDC_MINT,
        pair_quote_asset=QUOTE_ASSET_USDC,
        pair_pair_type=PAIR_TYPE_PUMP_USDC,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_USDC_FIXED,
        pair_live_policy=LIVE_POLICY_DRY_RUN_ONLY,
        pair_calibration_lane=CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    )


def _ingest_unknown_classified() -> ProviderIngestOutputRecord:
    return _ingest_sol_composed()._replace(
        quote_mint=None,
        pair_quote_asset=QUOTE_ASSET_UNKNOWN,
        pair_pair_type=PAIR_TYPE_UNKNOWN,
        pair_bonding_curve_version="UNKNOWN",
        pair_detection_status=PAIR_DETECTION_STATUS_UNRESOLVED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_NONE,
        pair_detection_reason=PAIR_DETECTION_REASON_NO_EVIDENCE,
        pair_live_policy=LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
        pair_calibration_lane=CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
        composition_status=COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
        composition_reason=COMPOSITION_REASON_PAIR_UNRESOLVED,
    )


def _ingest_disagree_classified() -> ProviderIngestOutputRecord:
    return _ingest_sol_composed()._replace(
        quote_mint=None,
        pair_quote_asset=QUOTE_ASSET_UNKNOWN,
        pair_pair_type=PAIR_TYPE_UNKNOWN,
        pair_bonding_curve_version="UNKNOWN",
        pair_detection_status=PAIR_DETECTION_STATUS_DISAGREE,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_LOW,
        pair_detection_reason=PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE,
        pair_live_policy=LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
        pair_calibration_lane=CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
        composition_status=COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
        composition_reason=COMPOSITION_REASON_PAIR_DISAGREE,
    )


def _ingest_skipped_unsupported_event() -> ProviderIngestOutputRecord:
    return _ingest_unknown_classified()._replace(
        event_kind=EVENT_KIND_UNKNOWN,
        composition_status=COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
        composition_reason=COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND,
    )


def _ingest_skipped_missing_token() -> ProviderIngestOutputRecord:
    return _ingest_unknown_classified()._replace(
        token_mint=None,
        composition_status=COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
        composition_reason=COMPOSITION_REASON_MISSING_TOKEN_MINT,
    )


def _present_price(*, sol: bool = True) -> m.PriceContextRecord:
    if sol:
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
    return m.PriceContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_USDC,
        quote_asset=QUOTE_ASSET_USDC,
        quote_mint=KNOWN_USDC_MINT,
        price_value="1.23",
        price_unit=m.PRICE_UNIT_USDC,
        price_source="fake",
        fetched_at_utc="2026-05-22T12:00:25+00:00",
        observed_at_utc=_OBSERVED_AT_ISO,
        staleness_seconds=5,
        price_status=m.PRICE_STATUS_PRESENT,
        price_reason=m.PRICE_REASON_USDC_OBSERVE_ONLY,
        schema_version=m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _stale_price() -> m.PriceContextRecord:
    return _present_price()._replace(
        price_status=m.PRICE_STATUS_STALE,
        price_reason=m.PRICE_REASON_STALE_THRESHOLD_EXCEEDED,
        staleness_seconds=630,
    )


def _unavailable_price() -> m.PriceContextRecord:
    return _present_price()._replace(
        price_value=None,
        price_status=m.PRICE_STATUS_UNAVAILABLE,
        price_reason=m.PRICE_REASON_SOURCE_RETURNED_NONE,
        staleness_seconds=None,
    )


def _source_error_price() -> m.PriceContextRecord:
    return _present_price()._replace(
        price_value=None,
        price_unit=m.PRICE_UNIT_UNKNOWN,
        price_source=None,
        fetched_at_utc=None,
        staleness_seconds=None,
        price_status=m.PRICE_STATUS_SOURCE_ERROR,
        price_reason=m.PRICE_REASON_SOURCE_FAILED,
    )


def _present_ath_post_migration() -> m.AthContextRecord:
    return m.AthContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        ath_source="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        ath_since_migration_status=m.ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
        drawdown_from_ath="0.0008",
        drawdown_unit=m.ATH_UNIT_SOL,
        drawdown_basis=m.DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=m.ATH_STATUS_PRESENT,
        ath_reason=m.ATH_REASON_OK,
        schema_version=m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _present_ath_may_include_pre_migration() -> m.AthContextRecord:
    return _present_ath_post_migration()._replace(
        ath_since_migration_status=(
            m.ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
        ),
        drawdown_from_ath=None,
        drawdown_basis=m.DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_reason=m.ATH_REASON_PRE_MIGRATION_DATA_REJECTED,
    )


def _unavailable_ath() -> m.AthContextRecord:
    return _present_ath_post_migration()._replace(
        ath_value=None,
        ath_since_migration_status=m.ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE,
        drawdown_from_ath=None,
        drawdown_basis=m.DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_status=m.ATH_STATUS_UNAVAILABLE,
        ath_reason=m.ATH_REASON_NO_OBSERVATIONS,
    )


def _source_error_ath() -> m.AthContextRecord:
    return _present_ath_post_migration()._replace(
        ath_value=None,
        ath_unit=m.ATH_UNIT_UNKNOWN,
        ath_source=None,
        ath_observed_at_utc=None,
        ath_since_migration_status=m.ATH_SINCE_MIGRATION_STATUS_UNKNOWN,
        drawdown_from_ath=None,
        drawdown_unit=m.ATH_UNIT_UNKNOWN,
        drawdown_basis=m.DRAWDOWN_BASIS_UNKNOWN,
        ath_status=m.ATH_STATUS_SOURCE_ERROR,
        ath_reason=m.ATH_REASON_SOURCE_FAILED,
    )


def _present_migration() -> mig.MigrationContextRecord:
    return mig.MigrationContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=mig.MIGRATION_STATUS_PRESENT,
        migration_reason=mig.MIGRATION_REASON_OK,
        age_since_migration_seconds=3630,
        observed_at_utc=_OBSERVED_AT_ISO,
        source_event_ref="ref-1",
        raw_capture_ref="cap-1",
        schema_version=mig.STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def _missing_migration() -> mig.MigrationContextRecord:
    return _present_migration()._replace(
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source=mig.MIGRATION_SOURCE_UNKNOWN,
        migration_status=mig.MIGRATION_STATUS_MISSING,
        migration_reason=mig.MIGRATION_REASON_NO_MIGRATION_EVENT,
        age_since_migration_seconds=None,
        source_event_ref=None,
        raw_capture_ref=None,
    )


def _untrusted_migration() -> mig.MigrationContextRecord:
    return _present_migration()._replace(
        migration_source=mig.MIGRATION_SOURCE_PROVIDER_ENRICHED,
        migration_status=mig.MIGRATION_STATUS_UNTRUSTED,
        migration_reason=mig.MIGRATION_REASON_SOURCE_NOT_TRUSTED,
    )


def _source_error_migration() -> mig.MigrationContextRecord:
    return _present_migration()._replace(
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source=mig.MIGRATION_SOURCE_UNKNOWN,
        migration_status=mig.MIGRATION_STATUS_SOURCE_ERROR,
        migration_reason=mig.MIGRATION_REASON_SOURCE_FAILED,
        age_since_migration_seconds=None,
        source_event_ref=None,
        raw_capture_ref=None,
    )


def _unsupported_pair_price() -> m.PriceContextRecord:
    return _present_price()._replace(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_UNKNOWN,
        quote_asset=QUOTE_ASSET_UNKNOWN,
        quote_mint=None,
        price_value=None,
        price_unit=m.PRICE_UNIT_UNKNOWN,
        price_source=None,
        fetched_at_utc=None,
        staleness_seconds=None,
        price_status=m.PRICE_STATUS_UNSUPPORTED_PAIR,
        price_reason=m.PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    )


def _unsupported_pair_ath() -> m.AthContextRecord:
    return _present_ath_post_migration()._replace(
        pair_type=PAIR_TYPE_UNKNOWN,
        quote_asset=QUOTE_ASSET_UNKNOWN,
        ath_value=None,
        ath_unit=m.ATH_UNIT_UNKNOWN,
        ath_source=None,
        ath_observed_at_utc=None,
        ath_since_migration_status=m.ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE,
        drawdown_from_ath=None,
        drawdown_unit=m.ATH_UNIT_UNKNOWN,
        drawdown_basis=m.DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_status=m.ATH_STATUS_UNSUPPORTED_PAIR,
        ath_reason=m.ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    )


def _unsupported_pair_migration() -> mig.MigrationContextRecord:
    return _present_migration()._replace(
        pair_type=PAIR_TYPE_UNKNOWN,
        quote_asset=QUOTE_ASSET_UNKNOWN,
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source=mig.MIGRATION_SOURCE_UNKNOWN,
        migration_status=mig.MIGRATION_STATUS_UNSUPPORTED_PAIR,
        migration_reason=mig.MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        age_since_migration_seconds=None,
        source_event_ref=None,
        raw_capture_ref=None,
    )


# ---------------------------------------------------------------------------
# Closed-set vocabulary pins
# ---------------------------------------------------------------------------


def test_measurement_status_values_locked_closed_set():
    assert combined.MEASUREMENT_STATUS_VALUES == (
        "COMPLETE",
        "PARTIAL",
        "MISSING_PRICE",
        "MISSING_ATH",
        "MISSING_MIGRATION",
        "UNSUPPORTED_PAIR",
        "SOURCE_ERROR",
    )


@pytest.mark.parametrize(
    "expected",
    (
        "USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION",
        "UNKNOWN_PAIR_SUPPRESSED_IN_LIVE",
        "DISAGREE_PAIR_SUPPRESSED_IN_LIVE",
        "PRICE_STALE",
        "PRICE_UNAVAILABLE",
        "ATH_UNAVAILABLE",
        "MIGRATION_MISSING",
        "POST_MIGRATION_ATH_UNVERIFIED",
    ),
)
def test_measurement_warning_values_include_brief_set(expected):
    assert expected in combined.MEASUREMENT_WARNING_VALUES


def test_measurement_schema_version_handle():
    assert (
        combined.STAGE27_4_MEASUREMENT_SCHEMA_VERSION
        == "stage27_v0_measurement_context"
    )


# ---------------------------------------------------------------------------
# Record shape pins
# ---------------------------------------------------------------------------


def test_live_measurement_context_record_is_namedtuple_and_immutable():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.measurement_status = "PARTIAL"


def test_live_measurement_context_record_field_set_locked():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert set(record._fields) == {
        "provider_id",
        "provider_event_id",
        "normalized_event_id",
        "event_kind",
        "observed_at_utc",
        "token_mint",
        "quote_mint",
        "pair_quote_asset",
        "pair_pair_type",
        "pair_bonding_curve_version",
        "pair_detection_status",
        "pair_detection_confidence",
        "pair_detection_reason",
        "pair_live_policy",
        "pair_calibration_lane",
        "composition_status",
        "composition_reason",
        "price_context",
        "ath_context",
        "migration_context",
        "measurement_status",
        "measurement_warnings",
        "raw_capture_ref",
        "source_summary",
        "context_schema_version",
    }


def test_combined_record_carries_schema_version():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert (
        record.context_schema_version
        == combined.STAGE27_4_MEASUREMENT_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# Status: COMPLETE
# ---------------------------------------------------------------------------


def test_sol_pair_all_present_yields_complete():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert record.measurement_status == combined.MEASUREMENT_STATUS_COMPLETE
    assert record.measurement_warnings == ()


# ---------------------------------------------------------------------------
# Status: PARTIAL
# ---------------------------------------------------------------------------


def test_stale_price_yields_partial():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _stale_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert record.measurement_status == combined.MEASUREMENT_STATUS_PARTIAL
    assert combined.WARNING_PRICE_STALE in record.measurement_warnings


def test_may_include_pre_migration_ath_yields_partial():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_may_include_pre_migration(),
        _present_migration(),
    )
    assert record.measurement_status == combined.MEASUREMENT_STATUS_PARTIAL
    assert (
        combined.WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in record.measurement_warnings
    )


def test_untrusted_migration_yields_partial():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _untrusted_migration(),
    )
    assert record.measurement_status == combined.MEASUREMENT_STATUS_PARTIAL
    assert (
        combined.WARNING_MIGRATION_UNTRUSTED in record.measurement_warnings
    )


# ---------------------------------------------------------------------------
# Status: MISSING_*
# ---------------------------------------------------------------------------


def test_unavailable_price_yields_missing_price():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _unavailable_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_MISSING_PRICE
    )
    assert (
        combined.WARNING_PRICE_UNAVAILABLE in record.measurement_warnings
    )


def test_unavailable_ath_yields_missing_ath():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _unavailable_ath(),
        _present_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_MISSING_ATH
    )
    assert (
        combined.WARNING_ATH_UNAVAILABLE in record.measurement_warnings
    )


def test_missing_migration_yields_missing_migration():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _missing_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_MISSING_MIGRATION
    )
    assert (
        combined.WARNING_MIGRATION_MISSING in record.measurement_warnings
    )


# ---------------------------------------------------------------------------
# Status: SOURCE_ERROR
# ---------------------------------------------------------------------------


def test_price_source_error_yields_source_error_status():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _source_error_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_SOURCE_ERROR
    )
    assert (
        combined.WARNING_PRICE_SOURCE_ERROR in record.measurement_warnings
    )


def test_ath_source_error_yields_source_error_status():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _source_error_ath(),
        _present_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_SOURCE_ERROR
    )
    assert (
        combined.WARNING_ATH_SOURCE_ERROR in record.measurement_warnings
    )


def test_migration_source_error_yields_source_error_status():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price(),
        _present_ath_post_migration(),
        _source_error_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_SOURCE_ERROR
    )
    assert (
        combined.WARNING_MIGRATION_SOURCE_ERROR
        in record.measurement_warnings
    )


# ---------------------------------------------------------------------------
# Status: UNSUPPORTED_PAIR (USDC, UNKNOWN, DISAGREE)
# ---------------------------------------------------------------------------


def test_usdc_pair_is_partial_with_observe_only_warning():
    """USDC pair stays PARTIAL with the USDC_OBSERVE_ONLY warning;
    NEVER routed to SOL lane.
    """
    record = combined.assemble_measurement_context(
        _ingest_usdc_composed(),
        _present_price(sol=False),
        _present_ath_post_migration()._replace(
            pair_type=PAIR_TYPE_PUMP_USDC,
            quote_asset=QUOTE_ASSET_USDC,
            ath_unit=m.ATH_UNIT_USDC,
            drawdown_unit=m.ATH_UNIT_USDC,
            ath_reason=m.ATH_REASON_USDC_OBSERVE_ONLY,
        ),
        _present_migration()._replace(
            pair_type=PAIR_TYPE_PUMP_USDC,
            quote_asset=QUOTE_ASSET_USDC,
        ),
    )
    assert record.measurement_status == combined.MEASUREMENT_STATUS_PARTIAL
    assert (
        combined.WARNING_USDC_OBSERVE_ONLY_NO_SOL_CALIBRATION
        in record.measurement_warnings
    )
    # USDC NEVER reaches SOL lane.
    assert (
        record.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_unknown_pair_yields_unsupported_with_warning():
    record = combined.assemble_measurement_context(
        _ingest_unknown_classified(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    )
    assert (
        combined.WARNING_UNKNOWN_PAIR_SUPPRESSED_IN_LIVE
        in record.measurement_warnings
    )
    assert (
        record.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_disagree_pair_yields_unsupported_with_warning():
    record = combined.assemble_measurement_context(
        _ingest_disagree_classified(),
        _unsupported_pair_price()._replace(
            price_reason=m.PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
        ),
        _unsupported_pair_ath()._replace(
            ath_reason=m.ATH_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
        ),
        _unsupported_pair_migration()._replace(
            migration_reason=mig.MIGRATION_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
        ),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    )
    assert (
        combined.WARNING_DISAGREE_PAIR_SUPPRESSED_IN_LIVE
        in record.measurement_warnings
    )
    assert (
        record.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_skipped_unsupported_event_yields_unsupported_pair():
    record = combined.assemble_measurement_context(
        _ingest_skipped_unsupported_event(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    )
    assert (
        combined.WARNING_COMPOSITION_SKIPPED_UNSUPPORTED_EVENT
        in record.measurement_warnings
    )


def test_skipped_missing_token_yields_unsupported_pair():
    record = combined.assemble_measurement_context(
        _ingest_skipped_missing_token(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )
    assert (
        record.measurement_status
        == combined.MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    )
    assert (
        combined.WARNING_COMPOSITION_SKIPPED_MISSING_TOKEN
        in record.measurement_warnings
    )


# ---------------------------------------------------------------------------
# Assembler input-shape guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_kwarg",
    (
        "ingest_output",
        "price_context",
        "ath_context",
        "migration_context",
    ),
)
def test_assembler_rejects_wrong_input_type(bad_kwarg):
    kwargs = {
        "ingest_output": _ingest_sol_composed(),
        "price_context": _present_price(),
        "ath_context": _present_ath_post_migration(),
        "migration_context": _present_migration(),
    }
    kwargs[bad_kwarg] = object()
    with pytest.raises(TypeError):
        combined.assemble_measurement_context(**kwargs)


# ---------------------------------------------------------------------------
# Pair-mirroring guarantees
# ---------------------------------------------------------------------------


def test_combined_record_mirrors_ingest_pair_fields():
    ingest = _ingest_sol_composed()
    record = combined.assemble_measurement_context(
        ingest,
        _present_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert record.pair_quote_asset == ingest.pair_quote_asset
    assert record.pair_pair_type == ingest.pair_pair_type
    assert (
        record.pair_bonding_curve_version
        == ingest.pair_bonding_curve_version
    )
    assert (
        record.pair_detection_status == ingest.pair_detection_status
    )
    assert (
        record.pair_detection_confidence
        == ingest.pair_detection_confidence
    )
    assert (
        record.pair_detection_reason
        == ingest.pair_detection_reason
    )
    assert record.pair_live_policy == ingest.pair_live_policy
    assert (
        record.pair_calibration_lane == ingest.pair_calibration_lane
    )
    assert record.composition_status == ingest.composition_status
    assert record.composition_reason == ingest.composition_reason


def test_combined_record_preserves_provider_provenance():
    ingest = _ingest_sol_composed()
    record = combined.assemble_measurement_context(
        ingest,
        _present_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )
    assert record.provider_id == ingest.provider_id
    assert record.provider_event_id == ingest.provider_event_id
    assert record.normalized_event_id == ingest.normalized_event_id
    assert record.raw_capture_ref == ingest.raw_capture_ref
    assert record.source_summary == ingest.source_summary
    assert record.observed_at_utc == ingest.observed_at_utc


def test_combined_record_carries_sub_records():
    price = _present_price()
    ath = _present_ath_post_migration()
    migration = _present_migration()
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(), price, ath, migration
    )
    assert record.price_context is price
    assert record.ath_context is ath
    assert record.migration_context is migration


# ---------------------------------------------------------------------------
# measurement_warnings is a closed-set tuple
# ---------------------------------------------------------------------------


def test_measurement_warnings_membership_is_closed_set():
    record = combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _stale_price(),
        _present_ath_may_include_pre_migration(),
        _untrusted_migration(),
    )
    assert isinstance(record.measurement_warnings, tuple)
    for warning in record.measurement_warnings:
        assert warning in combined.MEASUREMENT_WARNING_VALUES
