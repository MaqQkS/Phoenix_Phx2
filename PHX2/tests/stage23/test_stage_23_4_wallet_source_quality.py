"""Stage 23.4 wallet / source-quality filter tests.

Pins:

  * Filter identity strings (name / family / version /
    threshold_version) are locked.
  * Reason-code closed-set is locked.
  * Label / data_status routing for the major cases:
      - broad mature low-risk profile -> NORMAL / COMPLETE
      - high fresh-wallet density -> ELEVATED / SUSPICIOUS
      - repeated source wallets -> ELEVATED / SUSPICIOUS
      - high common-funder cluster count -> SUSPICIOUS
      - high largest-funder-cluster concentration -> SUSPICIOUS
      - extreme largest-funder-cluster concentration -> SCAM_LIKELY
      - known bad source present -> SUSPICIOUS
      - known bad source dense / extreme -> SCAM_LIKELY
      - dev wallet too fresh -> ELEVATED / SUSPICIOUS
      - creator wallet too fresh -> ELEVATED / SUSPICIOUS
      - missing wallet-source input -> MISSING_INPUT / MISSING
      - partial wallet-source input -> PARTIAL with explicit reason
      - overall unsupported marker -> UNKNOWN / UNSUPPORTED
      - wallet-age sub-family unsupported -> UNKNOWN / UNSUPPORTED
      - funding-graph sub-family unsupported -> UNKNOWN / UNSUPPORTED
      - provenance sub-family unsupported -> UNKNOWN / UNSUPPORTED
      - too few wallets sampled -> INSUFFICIENT_DATA with reason
  * Determinism: same input -> same evaluation_hash; key reorder
    does not change the hash; reorder of missing_features does
    not change the hash because the filter sorts the missing
    tuple deterministically.
  * Threshold-version separation: a (hypothetical) bump of
    ``threshold_version`` changes the hash.
  * Reason codes are a closed-set.
  * Filter satisfies the ``Stage23Filter`` Protocol surface (a
    class-shape with an ``evaluate`` method).
  * No label or reason code claims organic / scam ground truth.
    The filter is honest about what it does not know.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_UNSUPPORTED,
    FILTER_FAMILY_WALLET_SOURCE_QUALITY,
    LABEL_ELEVATED,
    LABEL_INSUFFICIENT_DATA,
    LABEL_MISSING_INPUT,
    LABEL_NORMAL,
    LABEL_SCAM_LIKELY,
    LABEL_SUSPICIOUS,
    LABEL_UNKNOWN,
)
from PHX2.stage23.errors import Stage23ContractError
from PHX2.stage23.filter_contracts import Stage23FilterFamily
from PHX2.stage23.models import (
    Stage23FilterResult,
    compute_evaluation_hash,
    compute_input_hash,
)
from PHX2.stage23.wallet_source_quality import (
    FILTER_NAME,
    FILTER_VERSION,
    PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND,
    PAYLOAD_MARKER_PROVENANCE_PRIMITIVE_KIND,
    PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND,
    PAYLOAD_MARKER_WALLET_SOURCE_PRIMITIVE_KIND,
    PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT,
    PRIMITIVE_CREATOR_WALLET_AGE_DAYS,
    PRIMITIVE_DEV_WALLET_AGE_DAYS,
    PRIMITIVE_EARLY_WALLET_COUNT,
    PRIMITIVE_FRESH_WALLET_PCT,
    PRIMITIVE_KNOWN_BAD_SOURCE_COUNT,
    PRIMITIVE_KNOWN_BAD_SOURCE_PCT,
    PRIMITIVE_LARGEST_COMMON_FUNDER_CLUSTER_PCT,
    PRIMITIVE_MATURE_WALLET_PCT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_PCT,
    PRIMITIVE_WALLET_AGE_KNOWN_PCT,
    PRIMITIVE_YOUNG_WALLET_PCT,
    REASON_COMMON_FUNDER_CLUSTER_HIGH,
    REASON_CREATOR_WALLET_TOO_FRESH,
    REASON_DEV_WALLET_TOO_FRESH,
    REASON_FRESH_WALLET_DENSITY_ELEVATED,
    REASON_FRESH_WALLET_DENSITY_HIGH,
    REASON_FUNDING_GRAPH_UNSUPPORTED,
    REASON_INSUFFICIENT_WALLET_SAMPLE,
    REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH,
    REASON_KNOWN_BAD_SOURCE_PRESENT,
    REASON_KNOWN_GOOD_SOURCE_DENSITY_LOW,
    REASON_LARGEST_FUNDER_CLUSTER_HIGH,
    REASON_PROVENANCE_UNSUPPORTED,
    REASON_REPEATED_SOURCE_WALLETS,
    REASON_REQUIRED_WALLET_SOURCE_FEATURE_MISSING,
    REASON_SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED,
    REASON_WALLET_AGE_COVERAGE_LOW,
    REASON_WALLET_AGE_UNSUPPORTED,
    REASON_WALLET_SOURCE_INPUT_MISSING,
    REASON_WALLET_SOURCE_INPUT_PARTIAL,
    REASON_WALLET_SOURCE_QUALITY_NORMAL,
    REASON_YOUNG_WALLET_SHARE_HIGH,
    THRESHOLD_VERSION,
    WALLET_SOURCE_PRIMITIVE_KEYS,
    WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED,
    WALLET_SOURCE_REASON_CODES,
    WalletSourceQualityFilter,
    evaluate,
)
from PHX2.tests.stage23.fixtures.builders import (
    empty_payload_summary,
    make_filter_input,
    make_unsupported_funding_graph_payload_summary,
    make_unsupported_provenance_payload_summary,
    make_unsupported_wallet_age_payload_summary,
    make_unsupported_wallet_source_payload_summary,
    make_wallet_source_filter_input,
    make_wallet_source_payload_summary,
)


# ---------------------------------------------------------------------------
# Filter identity
# ---------------------------------------------------------------------------


def test_filter_name_is_locked():
    assert FILTER_NAME == "wallet_source_quality"


def test_filter_version_is_locked():
    assert FILTER_VERSION == "wallet_source_quality_v0"


def test_threshold_version_is_locked():
    assert THRESHOLD_VERSION == "thresholds_v0_observe_only"


def test_filter_family_is_wallet_source_quality():
    assert FILTER_FAMILY_WALLET_SOURCE_QUALITY == "WALLET_SOURCE_QUALITY"


def test_filter_family_member_of_closed_set():
    assert Stage23FilterFamily.contains(FILTER_FAMILY_WALLET_SOURCE_QUALITY)


def test_filter_version_and_threshold_version_are_different_strings():
    assert FILTER_VERSION != THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Reason-code closed set
# ---------------------------------------------------------------------------


def test_wallet_source_reason_codes_are_locked():
    expected = (
        "WALLET_SOURCE_QUALITY_NORMAL",
        "FRESH_WALLET_DENSITY_ELEVATED",
        "FRESH_WALLET_DENSITY_HIGH",
        "REPEATED_SOURCE_WALLETS",
        "COMMON_FUNDER_CLUSTER_HIGH",
        "LARGEST_FUNDER_CLUSTER_HIGH",
        "WALLET_AGE_COVERAGE_LOW",
        "YOUNG_WALLET_SHARE_HIGH",
        "KNOWN_BAD_SOURCE_PRESENT",
        "KNOWN_BAD_SOURCE_DENSITY_HIGH",
        "KNOWN_GOOD_SOURCE_DENSITY_LOW",
        "DEV_WALLET_TOO_FRESH",
        "CREATOR_WALLET_TOO_FRESH",
        "SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED",
        "FUNDING_GRAPH_UNSUPPORTED",
        "WALLET_AGE_UNSUPPORTED",
        "PROVENANCE_UNSUPPORTED",
        "WALLET_SOURCE_INPUT_MISSING",
        "WALLET_SOURCE_INPUT_PARTIAL",
        "REQUIRED_WALLET_SOURCE_FEATURE_MISSING",
        "INSUFFICIENT_WALLET_SAMPLE",
    )
    assert WALLET_SOURCE_REASON_CODES == expected


def test_wallet_source_reason_codes_have_no_duplicates():
    assert len(WALLET_SOURCE_REASON_CODES) == len(
        set(WALLET_SOURCE_REASON_CODES)
    )


def test_wallet_source_primitive_keys_are_locked():
    expected = (
        "early_wallet_count",
        "fresh_wallet_count",
        "fresh_wallet_pct",
        "repeated_source_wallet_count",
        "repeated_source_wallet_pct",
        "common_funder_cluster_count",
        "largest_common_funder_cluster_pct",
        "wallet_age_known_count",
        "wallet_age_unknown_count",
        "wallet_age_known_pct",
        "young_wallet_pct",
        "mature_wallet_pct",
        "known_bad_source_count",
        "known_bad_source_pct",
        "known_good_source_count",
        "known_good_source_pct",
        "dev_wallet_age_days",
        "creator_wallet_age_days",
        "source_quality_known_pct",
    )
    assert WALLET_SOURCE_PRIMITIVE_KEYS == expected


# ---------------------------------------------------------------------------
# Broad mature low-risk profile
# ---------------------------------------------------------------------------


def test_normal_profile_yields_normal_label_and_complete_data_status():
    filter_input = make_wallet_source_filter_input()
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_NORMAL
    assert result.data_status == DATA_STATUS_COMPLETE
    assert REASON_WALLET_SOURCE_QUALITY_NORMAL in result.reason_codes


def test_normal_profile_reason_codes_subset_of_closed_set():
    result = evaluate(filter_input=make_wallet_source_filter_input())
    for code in result.reason_codes:
        assert code in WALLET_SOURCE_REASON_CODES


def test_normal_profile_carries_filter_identity():
    result = evaluate(filter_input=make_wallet_source_filter_input())
    assert result.filter_name == FILTER_NAME
    assert result.filter_family == FILTER_FAMILY_WALLET_SOURCE_QUALITY
    assert result.filter_version == FILTER_VERSION
    assert result.threshold_version == THRESHOLD_VERSION


def test_normal_profile_has_no_missing_features():
    result = evaluate(filter_input=make_wallet_source_filter_input())
    assert result.missing_features == ()


# ---------------------------------------------------------------------------
# Fresh-wallet density
# ---------------------------------------------------------------------------


def test_elevated_fresh_wallet_density_yields_elevated_label():
    payload = make_wallet_source_payload_summary(fresh_wallet_pct=0.45)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_FRESH_WALLET_DENSITY_ELEVATED in result.reason_codes


def test_high_fresh_wallet_density_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(fresh_wallet_pct=0.80)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_FRESH_WALLET_DENSITY_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Repeated source wallets
# ---------------------------------------------------------------------------


def test_repeated_source_wallets_elevated_yields_elevated_label():
    payload = make_wallet_source_payload_summary(
        repeated_source_wallet_pct=0.25,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_REPEATED_SOURCE_WALLETS in result.reason_codes


def test_repeated_source_wallets_suspicious_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(
        repeated_source_wallet_pct=0.60,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_REPEATED_SOURCE_WALLETS in result.reason_codes


def test_repeated_source_wallets_via_count_yields_elevated_label():
    """When the percentage primitive is absent but the count is
    elevated, the filter should still surface REPEATED_SOURCE_WALLETS.
    """
    payload = make_wallet_source_payload_summary(
        repeated_source_wallet_pct=None,
        repeated_source_wallet_count=4,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label in {LABEL_ELEVATED, LABEL_SUSPICIOUS}
    assert REASON_REPEATED_SOURCE_WALLETS in result.reason_codes


# ---------------------------------------------------------------------------
# Common-funder clustering
# ---------------------------------------------------------------------------


def test_common_funder_cluster_high_count_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(
        common_funder_cluster_count=5,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_COMMON_FUNDER_CLUSTER_HIGH in result.reason_codes


def test_largest_funder_cluster_suspicious_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(
        largest_common_funder_cluster_pct=0.50,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_LARGEST_FUNDER_CLUSTER_HIGH in result.reason_codes


def test_largest_funder_cluster_scam_likely_yields_scam_likely_label():
    payload = make_wallet_source_payload_summary(
        largest_common_funder_cluster_pct=0.80,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_LARGEST_FUNDER_CLUSTER_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Known bad source
# ---------------------------------------------------------------------------


def test_known_bad_source_present_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(known_bad_source_count=1)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_KNOWN_BAD_SOURCE_PRESENT in result.reason_codes


def test_known_bad_source_dense_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(
        known_bad_source_count=2,
        known_bad_source_pct=0.30,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH in result.reason_codes


def test_known_bad_source_extreme_yields_scam_likely_label():
    payload = make_wallet_source_payload_summary(
        known_bad_source_count=4,
        known_bad_source_pct=0.60,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_KNOWN_BAD_SOURCE_DENSITY_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Dev / creator wallet too fresh
# ---------------------------------------------------------------------------


def test_dev_wallet_too_fresh_yields_elevated_label():
    payload = make_wallet_source_payload_summary(dev_wallet_age_days=3.0)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_DEV_WALLET_TOO_FRESH in result.reason_codes


def test_dev_wallet_very_fresh_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(dev_wallet_age_days=0.5)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_DEV_WALLET_TOO_FRESH in result.reason_codes


def test_creator_wallet_too_fresh_yields_elevated_label():
    payload = make_wallet_source_payload_summary(
        creator_wallet_age_days=3.0,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_CREATOR_WALLET_TOO_FRESH in result.reason_codes


def test_creator_wallet_very_fresh_yields_suspicious_label():
    payload = make_wallet_source_payload_summary(
        creator_wallet_age_days=0.5,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_CREATOR_WALLET_TOO_FRESH in result.reason_codes


# ---------------------------------------------------------------------------
# Wallet-age coverage / young-wallet share contributing signals
# ---------------------------------------------------------------------------


def test_low_wallet_age_coverage_adds_reason_and_escalates_label():
    payload = make_wallet_source_payload_summary(wallet_age_known_pct=0.10)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label != LABEL_NORMAL
    assert REASON_WALLET_AGE_COVERAGE_LOW in result.reason_codes


def test_young_wallet_share_high_yields_at_least_elevated_label():
    payload = make_wallet_source_payload_summary(young_wallet_pct=0.65)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label in {
        LABEL_ELEVATED,
        LABEL_SUSPICIOUS,
        LABEL_SCAM_LIKELY,
    }
    assert REASON_YOUNG_WALLET_SHARE_HIGH in result.reason_codes


def test_low_known_good_density_contributes_reason():
    payload = make_wallet_source_payload_summary(
        known_good_source_pct=0.05,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert REASON_KNOWN_GOOD_SOURCE_DENSITY_LOW in result.reason_codes


# ---------------------------------------------------------------------------
# Missing wallet-source input
# ---------------------------------------------------------------------------


def test_completely_empty_payload_yields_missing_input_label():
    filter_input = make_filter_input(
        payload_summary=empty_payload_summary()
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_MISSING_INPUT
    assert result.data_status == DATA_STATUS_MISSING
    assert REASON_WALLET_SOURCE_INPUT_MISSING in result.reason_codes


def test_missing_input_label_is_not_normal():
    result = evaluate(
        filter_input=make_filter_input(
            payload_summary=empty_payload_summary()
        )
    )
    assert result.label != LABEL_NORMAL


def test_missing_input_missing_features_lists_all_primitives():
    result = evaluate(
        filter_input=make_filter_input(
            payload_summary=empty_payload_summary()
        )
    )
    assert set(result.missing_features) == set(WALLET_SOURCE_PRIMITIVE_KEYS)


def test_missing_input_missing_features_is_sorted():
    result = evaluate(
        filter_input=make_filter_input(
            payload_summary=empty_payload_summary()
        )
    )
    assert result.missing_features == tuple(
        sorted(result.missing_features)
    )


# ---------------------------------------------------------------------------
# Partial wallet-source input
# ---------------------------------------------------------------------------


def test_partial_payload_missing_required_features_yields_insufficient_data():
    """If none of the required source-quality primitives are
    present but some wallet-source primitives are, we cannot
    reach a concrete severity verdict -- the result is
    INSUFFICIENT_DATA / PARTIAL with REQUIRED_WALLET_SOURCE_FEATURE_MISSING.
    """
    payload = make_wallet_source_payload_summary(
        fresh_wallet_pct=None,
        repeated_source_wallet_pct=None,
        common_funder_cluster_count=None,
        largest_common_funder_cluster_pct=None,
        mature_wallet_pct=None,
        known_bad_source_count=None,
        known_bad_source_pct=None,
        # Keep some optional primitives to avoid MISSING_INPUT path.
        wallet_age_known_count=10,
        wallet_age_known_pct=0.50,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert result.data_status == DATA_STATUS_PARTIAL
    assert REASON_REQUIRED_WALLET_SOURCE_FEATURE_MISSING in result.reason_codes
    assert REASON_WALLET_SOURCE_INPUT_PARTIAL in result.reason_codes


def test_partial_payload_with_required_present_yields_partial_status():
    """If at least one required primitive is present but other
    optional primitives are missing, the verdict reaches a label
    but the data_status is PARTIAL with
    WALLET_SOURCE_INPUT_PARTIAL in reason_codes.
    """
    payload = make_wallet_source_payload_summary(
        wallet_age_unknown_count=None,
        common_funder_cluster_count=None,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.data_status == DATA_STATUS_PARTIAL
    assert REASON_WALLET_SOURCE_INPUT_PARTIAL in result.reason_codes


def test_partial_payload_carries_missing_feature_names_sorted():
    payload = make_wallet_source_payload_summary(
        common_funder_cluster_count=None,
        wallet_age_unknown_count=None,
        creator_wallet_age_days=None,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert PRIMITIVE_COMMON_FUNDER_CLUSTER_COUNT in result.missing_features
    assert PRIMITIVE_CREATOR_WALLET_AGE_DAYS in result.missing_features
    assert result.missing_features == tuple(
        sorted(result.missing_features)
    )


# ---------------------------------------------------------------------------
# Unsupported primitive markers
# ---------------------------------------------------------------------------


def test_overall_unsupported_primitive_yields_unknown_and_unsupported():
    filter_input = make_wallet_source_filter_input(
        payload_summary=make_unsupported_wallet_source_payload_summary(),
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert (
        REASON_SOURCE_QUALITY_PRIMITIVE_UNSUPPORTED in result.reason_codes
    )


def test_unsupported_wallet_age_primitive_yields_unknown():
    filter_input = make_wallet_source_filter_input(
        payload_summary=make_unsupported_wallet_age_payload_summary(),
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert REASON_WALLET_AGE_UNSUPPORTED in result.reason_codes


def test_unsupported_funding_graph_primitive_yields_unknown():
    filter_input = make_wallet_source_filter_input(
        payload_summary=make_unsupported_funding_graph_payload_summary(),
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert REASON_FUNDING_GRAPH_UNSUPPORTED in result.reason_codes


def test_unsupported_provenance_primitive_yields_unknown():
    filter_input = make_wallet_source_filter_input(
        payload_summary=make_unsupported_provenance_payload_summary(),
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert REASON_PROVENANCE_UNSUPPORTED in result.reason_codes


def test_multiple_sub_family_unsupported_emits_all_reasons():
    """If multiple sub-family markers are unsupported, the filter
    emits all matching reason codes in canonical order under a
    single UNKNOWN / UNSUPPORTED verdict.
    """
    payload = MappingProxyType(
        {
            PAYLOAD_MARKER_WALLET_AGE_PRIMITIVE_KIND: (
                WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED
            ),
            PAYLOAD_MARKER_FUNDING_GRAPH_PRIMITIVE_KIND: (
                WALLET_SOURCE_PRIMITIVE_KIND_UNSUPPORTED
            ),
        }
    )
    filter_input = make_wallet_source_filter_input(payload_summary=payload)
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert REASON_WALLET_AGE_UNSUPPORTED in result.reason_codes
    assert REASON_FUNDING_GRAPH_UNSUPPORTED in result.reason_codes


# ---------------------------------------------------------------------------
# Insufficient wallet sample
# ---------------------------------------------------------------------------


def test_too_few_early_wallets_yields_insufficient_data():
    payload = make_wallet_source_payload_summary(early_wallet_count=2)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert REASON_INSUFFICIENT_WALLET_SAMPLE in result.reason_codes


def test_zero_early_wallets_yields_insufficient_data():
    payload = make_wallet_source_payload_summary(early_wallet_count=0)
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert REASON_INSUFFICIENT_WALLET_SAMPLE in result.reason_codes


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_yields_same_evaluation_hash():
    a = evaluate(filter_input=make_wallet_source_filter_input())
    b = evaluate(filter_input=make_wallet_source_filter_input())
    assert isinstance(a, Stage23FilterResult)
    assert isinstance(b, Stage23FilterResult)
    h_a = compute_evaluation_hash(
        filter_input=make_wallet_source_filter_input(),
        filter_result=a,
    )
    h_b = compute_evaluation_hash(
        filter_input=make_wallet_source_filter_input(),
        filter_result=b,
    )
    assert h_a == h_b


def test_numeric_feature_key_order_does_not_change_hash():
    payload_a = MappingProxyType(
        {
            PRIMITIVE_EARLY_WALLET_COUNT: 50,
            PRIMITIVE_FRESH_WALLET_PCT: 0.10,
            PRIMITIVE_MATURE_WALLET_PCT: 0.60,
            PRIMITIVE_REPEATED_SOURCE_WALLET_PCT: 0.05,
        }
    )
    payload_b = MappingProxyType(
        {
            PRIMITIVE_REPEATED_SOURCE_WALLET_PCT: 0.05,
            PRIMITIVE_MATURE_WALLET_PCT: 0.60,
            PRIMITIVE_FRESH_WALLET_PCT: 0.10,
            PRIMITIVE_EARLY_WALLET_COUNT: 50,
        }
    )
    input_a = make_wallet_source_filter_input(payload_summary=payload_a)
    input_b = make_wallet_source_filter_input(payload_summary=payload_b)
    res_a = evaluate(filter_input=input_a)
    res_b = evaluate(filter_input=input_b)
    h_a = compute_evaluation_hash(filter_input=input_a, filter_result=res_a)
    h_b = compute_evaluation_hash(filter_input=input_b, filter_result=res_b)
    assert h_a == h_b


def test_missing_feature_order_is_deterministic_under_payload_reorder():
    """Missing features list is sorted regardless of payload iteration order."""
    payload_a = MappingProxyType(
        {
            PRIMITIVE_FRESH_WALLET_PCT: 0.10,
            PRIMITIVE_MATURE_WALLET_PCT: 0.60,
        }
    )
    payload_b = MappingProxyType(
        {
            PRIMITIVE_MATURE_WALLET_PCT: 0.60,
            PRIMITIVE_FRESH_WALLET_PCT: 0.10,
        }
    )
    res_a = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload_a)
    )
    res_b = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload_b)
    )
    assert res_a.missing_features == res_b.missing_features


def test_evaluation_hash_changes_when_threshold_version_changes_via_result():
    """A bumped ``threshold_version`` changes the evaluation hash."""
    filter_input = make_wallet_source_filter_input()
    base = evaluate(filter_input=filter_input)
    bumped = base._replace(
        threshold_version="thresholds_v_other_observe_only",
    )
    h_base = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=base,
    )
    h_bumped = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=bumped,
    )
    assert h_base != h_bumped


def test_evaluation_hash_changes_when_filter_version_changes_via_result():
    filter_input = make_wallet_source_filter_input()
    base = evaluate(filter_input=filter_input)
    bumped = base._replace(filter_version="wallet_source_quality_v_other")
    h_base = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=base,
    )
    h_bumped = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=bumped,
    )
    assert h_base != h_bumped


def test_input_hash_is_stable_for_repeated_wallet_source_inputs():
    a = make_wallet_source_filter_input()
    b = make_wallet_source_filter_input()
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_changes_when_payload_wallet_source_value_changes():
    a = make_wallet_source_filter_input()
    b = make_wallet_source_filter_input(
        payload_summary=make_wallet_source_payload_summary(
            fresh_wallet_pct=0.80,
        ),
    )
    assert compute_input_hash(a) != compute_input_hash(b)


# ---------------------------------------------------------------------------
# Closed-set guarantees
# ---------------------------------------------------------------------------


_LOCKED_LABELS_FOR_FILTER = frozenset(
    {
        LABEL_NORMAL,
        LABEL_ELEVATED,
        LABEL_SUSPICIOUS,
        LABEL_SCAM_LIKELY,
        LABEL_UNKNOWN,
        LABEL_INSUFFICIENT_DATA,
        LABEL_MISSING_INPUT,
    }
)


_LOCKED_DATA_STATUSES_FOR_FILTER = frozenset(
    {
        DATA_STATUS_COMPLETE,
        DATA_STATUS_PARTIAL,
        DATA_STATUS_MISSING,
        DATA_STATUS_UNSUPPORTED,
    }
)


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda: make_wallet_source_payload_summary(),
        lambda: make_wallet_source_payload_summary(fresh_wallet_pct=0.45),
        lambda: make_wallet_source_payload_summary(fresh_wallet_pct=0.80),
        lambda: make_wallet_source_payload_summary(
            repeated_source_wallet_pct=0.25,
        ),
        lambda: make_wallet_source_payload_summary(
            repeated_source_wallet_pct=0.60,
        ),
        lambda: make_wallet_source_payload_summary(
            common_funder_cluster_count=5,
        ),
        lambda: make_wallet_source_payload_summary(
            largest_common_funder_cluster_pct=0.50,
        ),
        lambda: make_wallet_source_payload_summary(
            largest_common_funder_cluster_pct=0.80,
        ),
        lambda: make_wallet_source_payload_summary(known_bad_source_count=1),
        lambda: make_wallet_source_payload_summary(
            known_bad_source_count=2,
            known_bad_source_pct=0.30,
        ),
        lambda: make_wallet_source_payload_summary(
            known_bad_source_count=4,
            known_bad_source_pct=0.60,
        ),
        lambda: make_wallet_source_payload_summary(dev_wallet_age_days=3.0),
        lambda: make_wallet_source_payload_summary(dev_wallet_age_days=0.5),
        lambda: make_wallet_source_payload_summary(
            creator_wallet_age_days=3.0,
        ),
        lambda: make_wallet_source_payload_summary(
            creator_wallet_age_days=0.5,
        ),
        lambda: make_wallet_source_payload_summary(
            wallet_age_known_pct=0.10,
        ),
        lambda: make_wallet_source_payload_summary(young_wallet_pct=0.65),
        lambda: make_wallet_source_payload_summary(early_wallet_count=2),
        lambda: empty_payload_summary(),
        lambda: make_unsupported_wallet_source_payload_summary(),
        lambda: make_unsupported_wallet_age_payload_summary(),
        lambda: make_unsupported_funding_graph_payload_summary(),
        lambda: make_unsupported_provenance_payload_summary(),
    ],
)
def test_every_verdict_uses_closed_set_label_and_data_status(payload_factory):
    result = evaluate(
        filter_input=make_wallet_source_filter_input(
            payload_summary=payload_factory()
        )
    )
    assert result.label in _LOCKED_LABELS_FOR_FILTER
    assert result.data_status in _LOCKED_DATA_STATUSES_FOR_FILTER


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda: make_wallet_source_payload_summary(),
        lambda: make_wallet_source_payload_summary(fresh_wallet_pct=0.80),
        lambda: make_wallet_source_payload_summary(
            largest_common_funder_cluster_pct=0.80,
        ),
        lambda: make_wallet_source_payload_summary(
            known_bad_source_count=4,
            known_bad_source_pct=0.60,
        ),
        lambda: make_wallet_source_payload_summary(early_wallet_count=2),
        lambda: empty_payload_summary(),
        lambda: make_unsupported_wallet_source_payload_summary(),
        lambda: make_unsupported_wallet_age_payload_summary(),
        lambda: make_unsupported_funding_graph_payload_summary(),
        lambda: make_unsupported_provenance_payload_summary(),
    ],
)
def test_every_verdict_uses_closed_set_reason_codes(payload_factory):
    result = evaluate(
        filter_input=make_wallet_source_filter_input(
            payload_summary=payload_factory()
        )
    )
    for code in result.reason_codes:
        assert code in WALLET_SOURCE_REASON_CODES, (
            f"reason code {code!r} is not in the wallet-source closed set"
        )


# ---------------------------------------------------------------------------
# Reason-code emit order is canonical
# ---------------------------------------------------------------------------


def test_reason_codes_are_in_canonical_order_when_multiple_triggers():
    payload = make_wallet_source_payload_summary(
        fresh_wallet_pct=0.45,
        repeated_source_wallet_pct=0.25,
        common_funder_cluster_count=5,
        largest_common_funder_cluster_pct=0.50,
        wallet_age_known_pct=0.10,
        known_bad_source_count=1,
    )
    result = evaluate(
        filter_input=make_wallet_source_filter_input(payload_summary=payload)
    )
    ranks = [
        WALLET_SOURCE_REASON_CODES.index(code) for code in result.reason_codes
    ]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Protocol surface
# ---------------------------------------------------------------------------


def test_wallet_source_quality_filter_class_has_evaluate_method():
    instance = WalletSourceQualityFilter()
    assert hasattr(instance, "evaluate")


def test_wallet_source_quality_filter_class_produces_matching_result():
    instance = WalletSourceQualityFilter()
    direct = evaluate(filter_input=make_wallet_source_filter_input())
    via_class = instance.evaluate(
        filter_input=make_wallet_source_filter_input(),
    )
    assert direct == via_class


def test_wallet_source_quality_filter_class_exposes_filter_identity():
    instance = WalletSourceQualityFilter()
    assert instance.filter_name == FILTER_NAME
    assert instance.filter_family == FILTER_FAMILY_WALLET_SOURCE_QUALITY
    assert instance.filter_version == FILTER_VERSION
    assert instance.threshold_version == THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Defensive contract violations
# ---------------------------------------------------------------------------


def test_negative_early_wallet_count_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_EARLY_WALLET_COUNT: -3,
            PRIMITIVE_FRESH_WALLET_PCT: 0.10,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_wallet_source_filter_input(
                payload_summary=payload,
            )
        )


def test_negative_wallet_age_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_DEV_WALLET_AGE_DAYS: -1.0,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_wallet_source_filter_input(
                payload_summary=payload,
            )
        )


def test_non_finite_pct_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_FRESH_WALLET_PCT: float("inf"),
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_wallet_source_filter_input(
                payload_summary=payload,
            )
        )


def test_evaluate_does_not_mutate_filter_input():
    payload = make_wallet_source_payload_summary()
    filter_input = make_wallet_source_filter_input(payload_summary=payload)
    snapshot_before = dict(filter_input.payload_summary)
    evaluate(filter_input=filter_input)
    snapshot_after = dict(filter_input.payload_summary)
    assert snapshot_before == snapshot_after


# ---------------------------------------------------------------------------
# No organic / scam / parity ground-truth claim
# ---------------------------------------------------------------------------


def test_no_reason_code_claims_ground_truth():
    """The reason-code closed set must never claim
    ``organic`` / ``scam`` / ``ground truth`` / ``parity``
    certainty. The filter is observe-only and honest about what
    it does not know.
    """
    forbidden_substrings = (
        "ORGANIC",
        "GROUND_TRUTH",
        "GROUND-TRUTH",
        "PARITY",
        "ANTE",
    )
    for code in WALLET_SOURCE_REASON_CODES:
        upper = code.upper()
        for needle in forbidden_substrings:
            assert needle not in upper, (
                f"reason code {code!r} contains forbidden ground-truth "
                f"substring {needle!r}"
            )


def test_no_label_claims_ground_truth():
    for label in _LOCKED_LABELS_FOR_FILTER:
        upper = label.upper()
        for needle in ("ORGANIC", "GROUND_TRUTH", "PARITY", "ANTE"):
            assert needle not in upper


def test_filter_identity_strings_make_no_ground_truth_claim():
    for token in (FILTER_NAME, FILTER_VERSION, THRESHOLD_VERSION):
        upper = token.upper()
        for needle in ("ORGANIC", "GROUND_TRUTH", "PARITY", "ANTE"):
            assert needle not in upper
