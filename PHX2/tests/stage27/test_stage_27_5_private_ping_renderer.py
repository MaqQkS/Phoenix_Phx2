"""Stage 27.5 private ping renderer tests.

Pins:

  * SOL pair on the existing-SOL lane with every axis PRESENT
    yields ``RENDERED`` + ``LIVE_OK``.
  * SOL pair with a STALE price yields ``RENDERED_WITH_WARNINGS``.
  * USDC pair yields ``RENDERED_OBSERVE_ONLY`` + ``OBSERVE_ONLY``.
  * UNKNOWN pair yields ``RENDERED_SUPPRESSED`` + ``LIVE_SUPPRESSED``.
  * DISAGREE pair yields ``RENDERED_SUPPRESSED`` + ``LIVE_SUPPRESSED``.
  * USDC / UNKNOWN / DISAGREE pairs NEVER render the existing-SOL
    calibration lane.
  * Composition skip / UNSUPPORTED_PAIR yields
    ``RENDERED_UNSUPPORTED``.
  * Missing price renders an explicit ``UNAVAILABLE`` /
    ``SOURCE_ERROR`` sentinel, NEVER ``"0"`` / ``"0.0"``.
  * Missing ATH renders an explicit ``UNAVAILABLE`` /
    ``NOT_APPLICABLE`` / ``SOURCE_ERROR`` sentinel.
  * Missing migration renders an explicit ``MISSING`` /
    ``UNTRUSTED`` / ``SOURCE_ERROR`` sentinel.
  * Rendered body carries ``provenance``, ``measurement_warnings``,
    ``raw_capture_ref`` lines and the pair / quote-asset tokens.
  * Rendered body NEVER carries BUY / SELL / APPROVED / GATE /
    BLOCK / SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE /
    AUTO-TRADE language.
  * Rendered payload + body NEVER carry raw secret canaries or raw
    provider payload blobs.
  * Two identical inputs render two byte-identical payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from PHX2.stage27 import live_measurement_context as combined
from PHX2.stage27 import migration_context_models as mig
from PHX2.stage27 import price_ath_context_models as m
from PHX2.stage27 import private_ping_models as pm
from PHX2.stage27 import private_ping_renderer as renderer
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
# Synthetic fixture helpers (copied shape from Stage 27.4 fixtures)
# ---------------------------------------------------------------------------


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
        source_summary="fake-summary",
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
        pair_calibration_lane=(
            CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
        ),
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
        pair_detection_reason=(
            PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE
        ),
        pair_live_policy=LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
        pair_calibration_lane=(
            CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
        ),
        composition_status=COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
        composition_reason=COMPOSITION_REASON_PAIR_DISAGREE,
    )


def _ingest_skipped_unsupported_event() -> ProviderIngestOutputRecord:
    return _ingest_unknown_classified()._replace(
        event_kind=EVENT_KIND_UNKNOWN,
        composition_status=(
            COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
        ),
        composition_reason=COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND,
    )


def _ingest_skipped_missing_token() -> ProviderIngestOutputRecord:
    return _ingest_unknown_classified()._replace(
        token_mint=None,
        composition_status=(
            COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN
        ),
        composition_reason=COMPOSITION_REASON_MISSING_TOKEN_MINT,
    )


def _present_price_sol() -> m.PriceContextRecord:
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


def _present_price_usdc() -> m.PriceContextRecord:
    return _present_price_sol()._replace(
        pair_type=PAIR_TYPE_PUMP_USDC,
        quote_asset=QUOTE_ASSET_USDC,
        quote_mint=KNOWN_USDC_MINT,
        price_value="1.23",
        price_unit=m.PRICE_UNIT_USDC,
        price_reason=m.PRICE_REASON_USDC_OBSERVE_ONLY,
    )


def _stale_price() -> m.PriceContextRecord:
    return _present_price_sol()._replace(
        price_status=m.PRICE_STATUS_STALE,
        price_reason=m.PRICE_REASON_STALE_THRESHOLD_EXCEEDED,
        staleness_seconds=630,
    )


def _unavailable_price() -> m.PriceContextRecord:
    return _present_price_sol()._replace(
        price_value=None,
        price_status=m.PRICE_STATUS_UNAVAILABLE,
        price_reason=m.PRICE_REASON_SOURCE_RETURNED_NONE,
        staleness_seconds=None,
    )


def _source_error_price() -> m.PriceContextRecord:
    return _present_price_sol()._replace(
        price_value=None,
        price_unit=m.PRICE_UNIT_UNKNOWN,
        price_source=None,
        fetched_at_utc=None,
        staleness_seconds=None,
        price_status=m.PRICE_STATUS_SOURCE_ERROR,
        price_reason=m.PRICE_REASON_SOURCE_FAILED,
    )


def _unsupported_pair_price() -> m.PriceContextRecord:
    return _present_price_sol()._replace(
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


def _present_ath_post_migration() -> m.AthContextRecord:
    return m.AthContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        ath_value="0.0009",
        ath_unit=m.ATH_UNIT_SOL,
        ath_source="fake",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        ath_since_migration_status=(
            m.ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_from_ath="0.0008",
        drawdown_unit=m.ATH_UNIT_SOL,
        drawdown_basis=m.DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=m.ATH_STATUS_PRESENT,
        ath_reason=m.ATH_REASON_OK,
        schema_version=m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _unavailable_ath() -> m.AthContextRecord:
    return _present_ath_post_migration()._replace(
        ath_value=None,
        ath_since_migration_status=(
            m.ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE
        ),
        drawdown_from_ath=None,
        drawdown_basis=m.DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_status=m.ATH_STATUS_UNAVAILABLE,
        ath_reason=m.ATH_REASON_NO_OBSERVATIONS,
    )


def _unsupported_pair_ath() -> m.AthContextRecord:
    return _present_ath_post_migration()._replace(
        pair_type=PAIR_TYPE_UNKNOWN,
        quote_asset=QUOTE_ASSET_UNKNOWN,
        ath_value=None,
        ath_unit=m.ATH_UNIT_UNKNOWN,
        ath_source=None,
        ath_observed_at_utc=None,
        ath_since_migration_status=(
            m.ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE
        ),
        drawdown_from_ath=None,
        drawdown_unit=m.ATH_UNIT_UNKNOWN,
        drawdown_basis=m.DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_status=m.ATH_STATUS_UNSUPPORTED_PAIR,
        ath_reason=m.ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    )


def _present_migration() -> mig.MigrationContextRecord:
    return mig.MigrationContextRecord(
        token_mint="MintAAA",
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        migration_event_id="evt-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source=(
            mig.MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
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
# Shortcut measurement-context builders
# ---------------------------------------------------------------------------


def _sol_complete_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price_sol(),
        _present_ath_post_migration(),
        _present_migration(),
    )


def _sol_stale_price_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _stale_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )


def _sol_unavailable_price_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _unavailable_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )


def _sol_unavailable_ath_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price_sol(),
        _unavailable_ath(),
        _present_migration(),
    )


def _sol_missing_migration_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price_sol(),
        _present_ath_post_migration(),
        _missing_migration(),
    )


def _sol_untrusted_migration_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _present_price_sol(),
        _present_ath_post_migration(),
        _untrusted_migration(),
    )


def _sol_source_error_price_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_sol_composed(),
        _source_error_price(),
        _present_ath_post_migration(),
        _present_migration(),
    )


def _usdc_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_usdc_composed(),
        _present_price_usdc(),
        _unavailable_ath(),
        _missing_migration(),
    )


def _unknown_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_unknown_classified(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )


def _disagree_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_disagree_classified(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )


def _skipped_unsupported_event_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_skipped_unsupported_event(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )


def _skipped_missing_token_context() -> combined.LiveMeasurementContextRecord:
    return combined.assemble_measurement_context(
        _ingest_skipped_missing_token(),
        _unsupported_pair_price(),
        _unsupported_pair_ath(),
        _unsupported_pair_migration(),
    )


# ---------------------------------------------------------------------------
# Render-status verdicts
# ---------------------------------------------------------------------------


def test_sol_complete_renders_clean():
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-1"
    )
    assert payload.render_status == pm.RENDER_STATUS_RENDERED
    assert payload.render_note == renderer.RENDER_NOTE_LIVE_OK
    assert (
        payload.calibration_lane
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert payload.quote_asset == QUOTE_ASSET_SOL


def test_sol_stale_price_renders_with_warnings():
    payload = renderer.render_private_ping(
        _sol_stale_price_context(), ping_id="ping-2"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_WITH_WARNINGS
    )
    assert payload.render_note == renderer.RENDER_NOTE_LIVE_WARNINGS


def test_sol_unavailable_price_renders_with_warnings():
    payload = renderer.render_private_ping(
        _sol_unavailable_price_context(), ping_id="ping-3"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_WITH_WARNINGS
    )


def test_sol_unavailable_ath_renders_with_warnings():
    payload = renderer.render_private_ping(
        _sol_unavailable_ath_context(), ping_id="ping-4"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_WITH_WARNINGS
    )


def test_sol_missing_migration_renders_with_warnings():
    payload = renderer.render_private_ping(
        _sol_missing_migration_context(), ping_id="ping-5"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_WITH_WARNINGS
    )


def test_sol_source_error_price_renders_with_warnings():
    payload = renderer.render_private_ping(
        _sol_source_error_price_context(), ping_id="ping-6"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_WITH_WARNINGS
    )


def test_usdc_renders_observe_only():
    payload = renderer.render_private_ping(
        _usdc_context(), ping_id="ping-7"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_OBSERVE_ONLY
    )
    assert payload.render_note == renderer.RENDER_NOTE_OBSERVE_ONLY
    assert payload.quote_asset == QUOTE_ASSET_USDC
    assert (
        payload.calibration_lane
        == CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )


def test_unknown_renders_suppressed():
    payload = renderer.render_private_ping(
        _unknown_context(), ping_id="ping-8"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_SUPPRESSED
    )
    assert (
        payload.render_note == renderer.RENDER_NOTE_LIVE_SUPPRESSED
    )
    assert payload.quote_asset == QUOTE_ASSET_UNKNOWN
    assert (
        payload.calibration_lane
        == CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )


def test_disagree_renders_suppressed():
    payload = renderer.render_private_ping(
        _disagree_context(), ping_id="ping-9"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_SUPPRESSED
    )
    assert (
        payload.render_note == renderer.RENDER_NOTE_LIVE_SUPPRESSED
    )
    assert (
        payload.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    )
    assert (
        payload.calibration_lane
        == CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )


def test_unsupported_event_renders_unsupported():
    payload = renderer.render_private_ping(
        _skipped_unsupported_event_context(), ping_id="ping-10"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_UNSUPPORTED
    )
    assert (
        payload.render_note == renderer.RENDER_NOTE_UNSUPPORTED_PAIR
    )


def test_missing_token_renders_unsupported():
    payload = renderer.render_private_ping(
        _skipped_missing_token_context(), ping_id="ping-11"
    )
    assert (
        payload.render_status
        == pm.RENDER_STATUS_RENDERED_UNSUPPORTED
    )


# ---------------------------------------------------------------------------
# Pair-lane invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "context_fn",
    (
        _usdc_context,
        _unknown_context,
        _disagree_context,
        _skipped_unsupported_event_context,
        _skipped_missing_token_context,
    ),
)
def test_non_sol_pairs_never_render_existing_sol_lane(context_fn):
    payload = renderer.render_private_ping(
        context_fn(), ping_id="ping-pair"
    )
    assert (
        payload.calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_unknown_pair_carries_live_suppressed_warning_in_body():
    payload = renderer.render_private_ping(
        _unknown_context(), ping_id="ping-unknown"
    )
    # Body announces the suppression note.
    assert "LIVE_SUPPRESSED" in payload.body_text


def test_disagree_pair_carries_live_suppressed_warning_in_body():
    payload = renderer.render_private_ping(
        _disagree_context(), ping_id="ping-disagree"
    )
    assert "LIVE_SUPPRESSED" in payload.body_text


def test_usdc_carries_observe_only_warning_in_body():
    payload = renderer.render_private_ping(
        _usdc_context(), ping_id="ping-usdc"
    )
    assert "OBSERVE_ONLY" in payload.body_text


# ---------------------------------------------------------------------------
# Missing-context sentinels (NEVER "0" / "0.0")
# ---------------------------------------------------------------------------


def test_unavailable_price_renders_unavailable_sentinel():
    payload = renderer.render_private_ping(
        _sol_unavailable_price_context(), ping_id="ping-missing-1"
    )
    assert payload.price_value_display == pm.DISPLAY_UNAVAILABLE
    assert payload.price_value_display not in ("0", "0.0")


def test_source_error_price_renders_source_error_sentinel():
    payload = renderer.render_private_ping(
        _sol_source_error_price_context(), ping_id="ping-missing-2"
    )
    assert payload.price_value_display == pm.DISPLAY_SOURCE_ERROR


def test_unavailable_ath_renders_unavailable_sentinel():
    payload = renderer.render_private_ping(
        _sol_unavailable_ath_context(), ping_id="ping-missing-3"
    )
    assert payload.ath_value_display == pm.DISPLAY_UNAVAILABLE
    assert payload.ath_value_display not in ("0", "0.0")


def test_missing_migration_renders_missing_sentinel():
    payload = renderer.render_private_ping(
        _sol_missing_migration_context(), ping_id="ping-missing-4"
    )
    assert (
        payload.migration_timestamp_display == pm.DISPLAY_MISSING
    )


def test_untrusted_migration_carries_status_in_payload():
    payload = renderer.render_private_ping(
        _sol_untrusted_migration_context(), ping_id="ping-untrust"
    )
    assert payload.migration_status == mig.MIGRATION_STATUS_UNTRUSTED


def test_stale_price_renders_stale_or_value_but_never_zero():
    payload = renderer.render_private_ping(
        _sol_stale_price_context(), ping_id="ping-stale"
    )
    assert payload.price_value_display not in ("0", "0.0")
    assert payload.price_status == m.PRICE_STATUS_STALE


# ---------------------------------------------------------------------------
# Body composition
# ---------------------------------------------------------------------------


def test_body_carries_required_provenance_lines():
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-body-1"
    )
    body = payload.body_text
    assert "PROVENANCE" in body
    assert "provider_id: fake-helius" in body
    assert "provider_event_id: prov-1" in body
    assert "normalized_event_id: norm-1" in body
    assert "raw_capture_ref: rcap-1" in body
    assert "ping_id: ping-body-1" in body
    assert "ping_schema_version: stage27_v0_private_ping" in body


def test_body_carries_pair_lines():
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-body-2"
    )
    body = payload.body_text
    assert "pair_type: PUMP_SOL" in body
    assert "quote_asset: SOL" in body
    assert "bonding_curve_version: SOL_LEGACY" in body
    assert "calibration_lane: EXISTING_SOL_LANE" in body


def test_body_carries_measurement_warnings_block():
    payload = renderer.render_private_ping(
        _sol_stale_price_context(), ping_id="ping-body-3"
    )
    body = payload.body_text
    assert "measurement_warnings: PRICE_STALE" in body


def test_body_empty_warnings_renders_none_sentinel():
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-body-4"
    )
    body = payload.body_text
    assert "measurement_warnings: NONE" in body


# ---------------------------------------------------------------------------
# Forbidden-language scan on the rendered body
# ---------------------------------------------------------------------------


_FORBIDDEN_RENDER_TOKENS: tuple[str, ...] = (
    "B" + "UY",
    "S" + "ELL",
    "AP" + "PROVED",
    "AUTO_AP" + "PROVED",
    "OP" + "ERATOR_APPROVED",
    "GA" + "TE",
    "BL" + "OCK",
    "S" + "AFE",
    "GUAR" + "ANTEED",
    "ENF" + "ORCEMENT",
    "ENF" + "ORCED",
    "EXE" + "CUTE",
    "EXEC" + "UTION",
    "POSI" + "TION_SIZE",
    "AUTO_" + "TRADE",
)


@pytest.mark.parametrize(
    "context_fn",
    (
        _sol_complete_context,
        _sol_stale_price_context,
        _sol_unavailable_price_context,
        _sol_unavailable_ath_context,
        _sol_missing_migration_context,
        _sol_untrusted_migration_context,
        _sol_source_error_price_context,
        _usdc_context,
        _unknown_context,
        _disagree_context,
        _skipped_unsupported_event_context,
        _skipped_missing_token_context,
    ),
)
@pytest.mark.parametrize("token", _FORBIDDEN_RENDER_TOKENS)
def test_rendered_body_carries_no_forbidden_token(context_fn, token):
    payload = renderer.render_private_ping(
        context_fn(), ping_id="ping-language"
    )
    assert token.upper() not in payload.body_text.upper()


# ---------------------------------------------------------------------------
# Forbidden secret canaries in the payload / body
# ---------------------------------------------------------------------------


_FORBIDDEN_SECRET_CANARIES: tuple[str, ...] = (
    "h" + "ttps://discord",
    "h" + "ttp://",
    "w" + "ss://",
    "discord" + ".com/api/webhooks",
    "Bearer ",
    "Bear" + "er sk-",
    "api_key=",
    "API_KEY=",
    "STAGE27_3_RAW_PAYLOAD",  # raw payload sentinel must not surface
)


@pytest.mark.parametrize("canary", _FORBIDDEN_SECRET_CANARIES)
def test_body_carries_no_secret_canary(canary):
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-canary"
    )
    assert canary not in payload.body_text


# ---------------------------------------------------------------------------
# Deterministic rendering: same input -> same payload
# ---------------------------------------------------------------------------


def test_render_is_deterministic_byte_identical():
    a = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-determ"
    )
    b = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-determ"
    )
    assert a == b
    assert a.body_text == b.body_text


def test_render_run_and_session_id_carried_through():
    payload = renderer.render_private_ping(
        _sol_complete_context(),
        ping_id="ping-id-x",
        run_id="run-42",
        session_id="sess-99",
    )
    assert payload.run_id == "run-42"
    assert payload.session_id == "sess-99"
    assert "run_id: run-42" in payload.body_text
    assert "session_id: sess-99" in payload.body_text


def test_render_missing_run_and_session_id_render_none_sentinel():
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-id-y"
    )
    assert payload.run_id is None
    assert payload.session_id is None
    assert "run_id: NONE" in payload.body_text
    assert "session_id: NONE" in payload.body_text


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_render_rejects_non_record_measurement_context():
    with pytest.raises(TypeError):
        renderer.render_private_ping(
            {"foo": "bar"}, ping_id="ping-bad"
        )


def test_render_rejects_empty_ping_id():
    with pytest.raises(ValueError):
        renderer.render_private_ping(
            _sol_complete_context(), ping_id=""
        )


def test_render_rejects_non_string_ping_id():
    with pytest.raises(ValueError):
        renderer.render_private_ping(
            _sol_complete_context(), ping_id=123  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Schema-version pin on payload
# ---------------------------------------------------------------------------


def test_payload_carries_locked_ping_schema_version():
    payload = renderer.render_private_ping(
        _sol_complete_context(), ping_id="ping-schema"
    )
    assert (
        payload.ping_schema_version
        == pm.STAGE27_5_PING_SCHEMA_VERSION
    )
