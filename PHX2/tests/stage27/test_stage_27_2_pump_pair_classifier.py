"""Stage 27.2 pump pair classifier tests.

Every test uses obvious synthetic / fake records. No live network
call is ever made and no provider payload blob is ever passed into
the classifier.

Pins (full coverage of the Stage 27.2 hard requirements):

  * Known SOL quote mint -> SOL / PUMP_SOL / SOL_LEGACY /
    CONFIRMED / HIGH / LIVE_ALLOWED / EXISTING_SOL_LANE.
  * Known USDC quote mint -> USDC / PUMP_USDC / USDC_FIXED /
    CONFIRMED / HIGH / DRY_RUN_ONLY / USDC_OBSERVE_ONLY (NOT the
    SOL lane).
  * Missing quote mint + no evidence -> UNKNOWN / UNRESOLVED /
    NONE / LIVE_SUPPRESS_UNKNOWN / UNKNOWN_PAIR_OBSERVE_ONLY.
  * Malformed quote mint -> UNKNOWN / UNRESOLVED (never defaults
    to SOL).
  * Provider-only SOL -> PROVIDER_ONLY / MEDIUM / LIVE_ALLOWED /
    EXISTING_SOL_LANE.
  * Provider-only USDC -> PROVIDER_ONLY / MEDIUM / DRY_RUN_ONLY /
    USDC_OBSERVE_ONLY (NOT the SOL lane).
  * Quote-mint SOL + provider says USDC -> DISAGREE / LOW /
    LIVE_SUPPRESS_DISAGREE / DISAGREE_PAIR_OBSERVE_ONLY.
  * Quote-mint USDC + provider says SOL -> DISAGREE / LOW /
    LIVE_SUPPRESS_DISAGREE / DISAGREE_PAIR_OBSERVE_ONLY.
  * Bonding-curve metadata agreement keeps confidence HIGH.
  * Bonding-curve metadata disagreement with quote-mint ->
    DISAGREE / LOW.
  * UNKNOWN never maps to EXISTING_SOL_LANE.
  * USDC never maps to EXISTING_SOL_LANE.
  * All classifier outputs are immutable.
  * Structurally invalid input raises ``Stage27InvalidPairInputError``.
  * ``gather_evidence`` is pure / deterministic.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import pair_detection_constants as c
from PHX2.stage27 import pair_detection_contracts as errors
from PHX2.stage27 import pair_detection_models as m
from PHX2.stage27 import pump_pair_classifier as classifier


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _input(**kwargs) -> m.PairDetectionInputRecord:
    return m.PairDetectionInputRecord(**kwargs)


# ---------------------------------------------------------------------------
# Known SOL / USDC quote-mint classification
# ---------------------------------------------------------------------------


def test_known_sol_quote_mint_classifies_as_sol_pump_sol_legacy():
    result = classifier.classify_pair(
        _input(
            event_id="evt-sol-1",
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_SOL
    assert result.pair_type == c.PAIR_TYPE_PUMP_SOL
    assert (
        result.bonding_curve_version
        == c.BONDING_CURVE_VERSION_SOL_LEGACY
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_CONFIRMED
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_HIGH
    )
    assert result.live_policy == c.LIVE_POLICY_LIVE_ALLOWED
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert result.evidence_count == 1
    assert result.disagreement_count == 0
    assert result.quote_mint == c.KNOWN_WRAPPED_SOL_MINT


def test_known_usdc_quote_mint_classifies_as_usdc_pump_usdc_fixed():
    result = classifier.classify_pair(
        _input(
            event_id="evt-usdc-1",
            quote_mint=c.KNOWN_USDC_MINT,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_USDC
    assert result.pair_type == c.PAIR_TYPE_PUMP_USDC
    assert (
        result.bonding_curve_version
        == c.BONDING_CURVE_VERSION_USDC_FIXED
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_CONFIRMED
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_HIGH
    )
    # USDC must be DRY_RUN_ONLY / USDC_OBSERVE_ONLY, NOT the SOL lane.
    assert result.live_policy == c.LIVE_POLICY_DRY_RUN_ONLY
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )
    assert (
        result.calibration_lane
        != c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


# ---------------------------------------------------------------------------
# Unresolved / UNKNOWN paths
# ---------------------------------------------------------------------------


def test_missing_quote_mint_and_no_evidence_classifies_as_unresolved():
    result = classifier.classify_pair(_input())
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN
    assert result.pair_type == c.PAIR_TYPE_UNKNOWN
    assert (
        result.bonding_curve_version
        == c.BONDING_CURVE_VERSION_UNKNOWN
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_UNRESOLVED
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_NONE
    )
    assert (
        result.pair_detection_reason
        == c.PAIR_DETECTION_REASON_NO_EVIDENCE
    )
    assert result.evidence_count == 0
    assert result.disagreement_count == 0
    assert (
        result.live_policy == c.LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    assert result.quote_mint is None


def test_malformed_quote_mint_does_not_default_to_sol():
    result = classifier.classify_pair(
        _input(quote_mint="garbage_string_not_a_real_mint")
    )
    # The classifier must NEVER promote an unrecognized quote-mint
    # string to SOL.
    assert result.quote_asset != c.QUOTE_ASSET_SOL
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN
    # It also must not silently pick a CONFIRMED status for a
    # malformed quote mint.
    assert result.pair_detection_status in (
        c.PAIR_DETECTION_STATUS_UNRESOLVED,
        c.PAIR_DETECTION_STATUS_DISAGREE,
    )
    assert result.pair_detection_confidence in (
        c.PAIR_DETECTION_CONFIDENCE_LOW,
        c.PAIR_DETECTION_CONFIDENCE_NONE,
    )
    # The malformed quote mint must NOT win the SOL lane.
    assert (
        result.calibration_lane
        != c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_malformed_quote_mint_raises_no_typed_error():
    """The classifier must NEVER raise for an Optional[str] field
    that is merely an unrecognized mint string.
    """
    # Must not raise.
    classifier.classify_pair(_input(quote_mint="not_a_real_mint"))
    classifier.classify_pair(_input(quote_mint=""))


# ---------------------------------------------------------------------------
# Provider-only paths
# ---------------------------------------------------------------------------


def test_provider_only_sol_classifies_as_provider_only_medium():
    result = classifier.classify_pair(
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_SOL,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_SOL
    assert result.pair_type == c.PAIR_TYPE_PUMP_SOL
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_PROVIDER_ONLY
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_MEDIUM
    )
    assert result.live_policy == c.LIVE_POLICY_LIVE_ALLOWED
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_provider_only_usdc_classifies_as_provider_only_medium_usdc_lane():
    result = classifier.classify_pair(
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_USDC
    assert result.pair_type == c.PAIR_TYPE_PUMP_USDC
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_PROVIDER_ONLY
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_MEDIUM
    )
    # USDC provider-only must be DRY_RUN_ONLY / USDC_OBSERVE_ONLY.
    assert result.live_policy == c.LIVE_POLICY_DRY_RUN_ONLY
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )
    assert (
        result.calibration_lane
        != c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


# ---------------------------------------------------------------------------
# DISAGREE paths
# ---------------------------------------------------------------------------


def test_quote_mint_sol_plus_provider_usdc_classifies_as_disagree():
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        )
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_DISAGREE
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_LOW
    )
    assert (
        result.live_policy
        == c.LIVE_POLICY_LIVE_SUPPRESS_DISAGREE
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )
    # The directional fields must collapse to UNKNOWN -- the
    # classifier must NOT silently choose the provider's verdict
    # over the on-chain quote mint, nor pretend the quote-mint
    # answer is canonical.
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN
    assert result.pair_type == c.PAIR_TYPE_UNKNOWN
    assert result.disagreement_count >= 1


def test_quote_mint_usdc_plus_provider_sol_classifies_as_disagree():
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_USDC_MINT,
            provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_SOL,
        )
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_DISAGREE
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_LOW
    )
    assert (
        result.live_policy
        == c.LIVE_POLICY_LIVE_SUPPRESS_DISAGREE
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN


def test_pool_quote_mint_sol_plus_bcv_usdc_classifies_as_disagree():
    """Strong vs strong disagreement (POOL_QUOTE_MINT says SOL, BCV
    metadata says USDC_FIXED) -> DISAGREE.
    """
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_USDC_FIXED
            ),
        )
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_DISAGREE
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_LOW
    )
    assert (
        result.live_policy
        == c.LIVE_POLICY_LIVE_SUPPRESS_DISAGREE
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )


def test_pool_quote_mint_usdc_plus_bcv_sol_classifies_as_disagree():
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_USDC_MINT,
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_SOL_LEGACY
            ),
        )
    )
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_DISAGREE
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_LOW
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )


# ---------------------------------------------------------------------------
# BCV agreement boost
# ---------------------------------------------------------------------------


def test_bonding_curve_metadata_agreement_keeps_high_confidence():
    """When POOL_QUOTE_MINT and BCV agree, confidence stays HIGH and
    disagreement_count stays 0; evidence_count grows to 2.
    """
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_SOL_LEGACY
            ),
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_SOL
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_CONFIRMED
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_HIGH
    )
    assert result.evidence_count == 2
    assert result.disagreement_count == 0
    # The two-strong-source agreement should be tagged as
    # CONFIRMED_AGREEMENT in the reason field.
    assert (
        result.pair_detection_reason
        == c.PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT
    )


def test_bonding_curve_metadata_alone_yields_high_confidence():
    """A single strong source still produces CONFIRMED + HIGH; the
    reason is SINGLE_STRONG_SOURCE rather than CONFIRMED_AGREEMENT.
    """
    result = classifier.classify_pair(
        _input(
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_USDC_FIXED
            )
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_USDC
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_CONFIRMED
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_HIGH
    )
    assert (
        result.pair_detection_reason
        == c.PAIR_DETECTION_REASON_SINGLE_STRONG_SOURCE
    )
    # USDC always observe-only / never SOL lane.
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )


# ---------------------------------------------------------------------------
# Migration-event evidence
# ---------------------------------------------------------------------------


def test_migration_event_only_sol_classifies_as_provider_only_medium_sol_lane():
    result = classifier.classify_pair(
        _input(
            migration_event_quote_asset_hint=c.QUOTE_ASSET_SOL,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_SOL
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_PROVIDER_ONLY
    )
    assert (
        result.pair_detection_confidence
        == c.PAIR_DETECTION_CONFIDENCE_MEDIUM
    )
    assert (
        result.pair_detection_reason
        == c.PAIR_DETECTION_REASON_MIGRATION_HINT_ONLY
    )


def test_migration_event_only_usdc_classifies_as_provider_only_medium_usdc_lane():
    result = classifier.classify_pair(
        _input(
            migration_event_quote_asset_hint=c.QUOTE_ASSET_USDC,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_USDC
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )
    assert result.live_policy == c.LIVE_POLICY_DRY_RUN_ONLY


# ---------------------------------------------------------------------------
# UNKNOWN must never map to EXISTING_SOL_LANE
# ---------------------------------------------------------------------------


def test_unknown_never_maps_to_existing_sol_lane_for_unresolved():
    result = classifier.classify_pair(_input())
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN
    assert (
        result.calibration_lane
        != c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )


def test_unknown_never_maps_to_existing_sol_lane_for_disagree():
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN
    assert (
        result.calibration_lane
        != c.CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )


def test_usdc_never_maps_to_existing_sol_lane_across_every_status():
    for input_record in (
        _input(quote_mint=c.KNOWN_USDC_MINT),
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        ),
        _input(
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_USDC_FIXED
            )
        ),
        _input(
            migration_event_quote_asset_hint=c.QUOTE_ASSET_USDC,
        ),
    ):
        result = classifier.classify_pair(input_record)
        assert result.quote_asset == c.QUOTE_ASSET_USDC
        assert (
            result.calibration_lane
            != c.CALIBRATION_LANE_EXISTING_SOL_LANE
        )
        assert (
            result.live_policy != c.LIVE_POLICY_LIVE_ALLOWED
        )


# ---------------------------------------------------------------------------
# Output is immutable
# ---------------------------------------------------------------------------


def test_classifier_output_is_immutable():
    result = classifier.classify_pair(
        _input(quote_mint=c.KNOWN_WRAPPED_SOL_MINT)
    )
    assert isinstance(result, tuple)
    with pytest.raises(AttributeError):
        result.quote_asset = "USDC"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_classifier_is_deterministic_for_identical_input():
    record = _input(
        event_id="evt-deterministic",
        quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
        bonding_curve_version_hint=c.BONDING_CURVE_VERSION_SOL_LEGACY,
        provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
    )
    a = classifier.classify_pair(record)
    b = classifier.classify_pair(record)
    assert a == b


def test_classifier_output_carries_only_closed_set_tokens():
    """Spot-check that every closed-set field on the output is a
    member of the corresponding locked vocabulary.
    """
    cases = [
        _input(),
        _input(quote_mint=c.KNOWN_WRAPPED_SOL_MINT),
        _input(quote_mint=c.KNOWN_USDC_MINT),
        _input(quote_mint="garbage"),
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_SOL,
        ),
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        ),
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        ),
        _input(
            quote_mint=c.KNOWN_USDC_MINT,
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_SOL_LEGACY
            ),
        ),
        _input(
            migration_event_quote_asset_hint=c.QUOTE_ASSET_USDC,
        ),
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        ),
    ]
    for input_record in cases:
        result = classifier.classify_pair(input_record)
        assert result.quote_asset in c.QUOTE_ASSET_VALUES
        assert result.pair_type in c.PAIR_TYPE_VALUES
        assert (
            result.bonding_curve_version
            in c.BONDING_CURVE_VERSION_VALUES
        )
        assert (
            result.pair_detection_status
            in c.PAIR_DETECTION_STATUS_VALUES
        )
        assert (
            result.pair_detection_confidence
            in c.PAIR_DETECTION_CONFIDENCE_VALUES
        )
        assert (
            result.pair_detection_reason
            in c.PAIR_DETECTION_REASON_VALUES
        )
        assert result.live_policy in c.LIVE_POLICY_VALUES
        assert (
            result.calibration_lane in c.CALIBRATION_LANE_VALUES
        )


# ---------------------------------------------------------------------------
# Structural-error path
# ---------------------------------------------------------------------------


def test_classify_pair_raises_on_non_record_input():
    with pytest.raises(errors.Stage27InvalidPairInputError):
        classifier.classify_pair(None)  # type: ignore[arg-type]
    with pytest.raises(errors.Stage27InvalidPairInputError):
        classifier.classify_pair(
            {"quote_mint": c.KNOWN_WRAPPED_SOL_MINT}
        )  # type: ignore[arg-type]
    with pytest.raises(errors.Stage27InvalidPairInputError):
        classifier.classify_pair("string")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# gather_evidence
# ---------------------------------------------------------------------------


def test_gather_evidence_empty_input_yields_empty_tuple():
    assert classifier.gather_evidence(_input()) == ()


def test_gather_evidence_emits_one_record_per_meaningful_source():
    evidence = classifier.gather_evidence(
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            bonding_curve_version_hint=(
                c.BONDING_CURVE_VERSION_SOL_LEGACY
            ),
            migration_event_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_SOL,
        )
    )
    sources = [r.source for r in evidence]
    assert sources == [
        c.PAIR_DETECTION_SOURCE_POOL_QUOTE_MINT,
        c.PAIR_DETECTION_SOURCE_BONDING_CURVE_METADATA,
        c.PAIR_DETECTION_SOURCE_MIGRATION_EVENT,
        c.PAIR_DETECTION_SOURCE_PROVIDER_PAYLOAD,
    ]
    # Every evidence record agrees on SOL.
    for record in evidence:
        assert record.quote_asset_verdict == c.QUOTE_ASSET_SOL


def test_gather_evidence_raises_on_non_record_input():
    with pytest.raises(errors.Stage27InvalidPairInputError):
        classifier.gather_evidence(
            None  # type: ignore[arg-type]
        )


def test_gather_evidence_records_are_immutable():
    evidence = classifier.gather_evidence(
        _input(quote_mint=c.KNOWN_WRAPPED_SOL_MINT)
    )
    assert evidence
    record = evidence[0]
    with pytest.raises(AttributeError):
        record.source = "PROVIDER_PAYLOAD"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Provider internal inconsistency
# ---------------------------------------------------------------------------


def test_provider_internal_inconsistency_drops_to_unresolved():
    """Provider says SOL for quote-asset hint but PUMP_USDC for
    pair-type hint -> provider verdict collapses to UNKNOWN. With
    no other evidence, the classifier resolves to UNRESOLVED.
    """
    result = classifier.classify_pair(
        _input(
            provider_quote_asset_hint=c.QUOTE_ASSET_SOL,
            provider_pair_type_hint=c.PAIR_TYPE_PUMP_USDC,
        )
    )
    assert result.quote_asset == c.QUOTE_ASSET_UNKNOWN
    assert (
        result.pair_detection_status
        == c.PAIR_DETECTION_STATUS_UNRESOLVED
    )
    assert (
        result.live_policy
        == c.LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN
    )
    assert (
        result.calibration_lane
        == c.CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )


# ---------------------------------------------------------------------------
# Reason codes are restricted to the closed set per status
# ---------------------------------------------------------------------------


def test_unresolved_reason_is_no_evidence():
    result = classifier.classify_pair(_input())
    assert (
        result.pair_detection_reason
        == c.PAIR_DETECTION_REASON_NO_EVIDENCE
    )


def test_disagree_reason_is_a_disagree_token():
    result = classifier.classify_pair(
        _input(
            quote_mint=c.KNOWN_WRAPPED_SOL_MINT,
            provider_quote_asset_hint=c.QUOTE_ASSET_USDC,
        )
    )
    assert result.pair_detection_reason in (
        c.PAIR_DETECTION_REASON_QUOTE_MINT_VS_PROVIDER_DISAGREE,
        c.PAIR_DETECTION_REASON_BONDING_CURVE_VS_QUOTE_MINT_DISAGREE,
        c.PAIR_DETECTION_REASON_STRONG_SOURCE_DISAGREE,
    )
