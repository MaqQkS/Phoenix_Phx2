"""Stage 23.3 launch-structure filter tests.

Pins:

  * Filter identity strings (name / family / version /
    threshold_version) are locked.
  * Reason-code closed-set is locked.
  * Label / data_status routing for the major cases:
      - broad organic-looking launch -> NORMAL / COMPLETE
      - same-slot clustering -> ELEVATED / SUSPICIOUS / SCAM_LIKELY
      - near-slot clustering -> ELEVATED / SUSPICIOUS
      - low unique buyer count -> ELEVATED / SUSPICIOUS
      - low unique funder count -> ELEVATED / SUSPICIOUS
      - large buyer-cluster concentration -> SUSPICIOUS / SCAM_LIKELY
      - large funder-cluster concentration -> SUSPICIOUS / SCAM_LIKELY
      - high first-N holder concentration -> SUSPICIOUS / SCAM_LIKELY
      - repeated source wallets -> SUSPICIOUS
      - combined repeated source wallets + high buyer-cluster
        concentration -> BUNDLE_LIKE_LAUNCH_PATTERN and at
        least SUSPICIOUS
      - extreme bundle-like combination -> SCAM_LIKELY
      - missing launch window -> MISSING_INPUT / MISSING
      - partial launch window -> PARTIAL with explicit reason
      - unsupported primitive marker -> UNKNOWN / UNSUPPORTED
      - too few launch events -> INSUFFICIENT_DATA with reason
      - launch window too small -> contributes LAUNCH_WINDOW_TOO_SMALL
  * Determinism: same input -> same evaluation_hash; key reorder
    does not change the hash; reorder of missing_features does
    not change the hash because the filter sorts the missing
    tuple deterministically.
  * Threshold-version separation: a (hypothetical) bump of
    ``threshold_version`` changes the hash.
  * Reason codes are a closed-set.
  * Filter satisfies the ``Stage23Filter`` Protocol surface (a
    class-shape with an ``evaluate`` method).
  * No label or reason code claims Ante parity. The filter is
    PHX2-native and emits bundle-like labels from synthetic
    primitives only.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_UNSUPPORTED,
    FILTER_FAMILY_LAUNCH_STRUCTURE,
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
from PHX2.stage23.launch_structure import (
    FILTER_NAME,
    FILTER_VERSION,
    LAUNCH_PRIMITIVE_KEYS,
    LAUNCH_REASON_CODES,
    LaunchStructureFilter,
    PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND,
    PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT,
    PRIMITIVE_FIRST_N_BUYERS_COUNT,
    PRIMITIVE_FIRST_N_EVENTS_OBSERVED,
    PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
    PRIMITIVE_FIRST_N_UNIQUE_BUYERS,
    PRIMITIVE_FIRST_N_UNIQUE_FUNDERS,
    PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT,
    PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT,
    PRIMITIVE_LAUNCH_SLOT,
    PRIMITIVE_LAUNCH_WINDOW_SECONDS,
    PRIMITIVE_NEAR_SLOT_BUYER_COUNT,
    PRIMITIVE_OBSERVED_SLOT_SPAN,
    PRIMITIVE_REPEATED_BUYER_WALLET_COUNT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
    PRIMITIVE_SAME_SLOT_BUYER_COUNT,
    REASON_BUNDLE_LIKE_LAUNCH_PATTERN,
    REASON_BUYER_CLUSTER_CONCENTRATION_HIGH,
    REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH,
    REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH,
    REASON_INSUFFICIENT_LAUNCH_EVENTS,
    REASON_LAUNCH_PRIMITIVE_UNSUPPORTED,
    REASON_LAUNCH_STRUCTURE_NORMAL,
    REASON_LAUNCH_WINDOW_MISSING,
    REASON_LAUNCH_WINDOW_PARTIAL,
    REASON_LAUNCH_WINDOW_TOO_SMALL,
    REASON_LOW_UNIQUE_BUYER_COUNT,
    REASON_LOW_UNIQUE_FUNDER_COUNT,
    REASON_NEAR_SLOT_BUYER_CLUSTER,
    REASON_REPEATED_BUYER_WALLETS,
    REASON_REPEATED_SOURCE_WALLETS,
    REASON_REQUIRED_LAUNCH_FEATURE_MISSING,
    REASON_SAME_SLOT_BUYER_CLUSTER,
    THRESHOLD_VERSION,
    evaluate,
)
from PHX2.stage23.models import (
    Stage23FilterResult,
    compute_evaluation_hash,
    compute_input_hash,
)
from PHX2.tests.stage23.fixtures.builders import (
    empty_payload_summary,
    make_filter_input,
    make_launch_filter_input,
    make_launch_payload_summary,
    make_unsupported_launch_payload_summary,
)


# ---------------------------------------------------------------------------
# Filter identity
# ---------------------------------------------------------------------------


def test_filter_name_is_locked():
    assert FILTER_NAME == "launch_structure"


def test_filter_version_is_locked():
    assert FILTER_VERSION == "launch_structure_v0"


def test_threshold_version_is_locked():
    assert THRESHOLD_VERSION == "thresholds_v0_observe_only"


def test_filter_family_is_launch_structure():
    assert FILTER_FAMILY_LAUNCH_STRUCTURE == "LAUNCH_STRUCTURE"


def test_filter_family_member_of_closed_set():
    assert Stage23FilterFamily.contains(FILTER_FAMILY_LAUNCH_STRUCTURE)


def test_filter_version_and_threshold_version_are_different_strings():
    assert FILTER_VERSION != THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Reason-code closed set
# ---------------------------------------------------------------------------


def test_launch_reason_codes_are_locked():
    expected = (
        "LAUNCH_STRUCTURE_NORMAL",
        "SAME_SLOT_BUYER_CLUSTER",
        "NEAR_SLOT_BUYER_CLUSTER",
        "LOW_UNIQUE_BUYER_COUNT",
        "LOW_UNIQUE_FUNDER_COUNT",
        "BUYER_CLUSTER_CONCENTRATION_HIGH",
        "FUNDER_CLUSTER_CONCENTRATION_HIGH",
        "FIRST_N_HOLDER_CONCENTRATION_HIGH",
        "REPEATED_SOURCE_WALLETS",
        "REPEATED_BUYER_WALLETS",
        "BUNDLE_LIKE_LAUNCH_PATTERN",
        "LAUNCH_WINDOW_MISSING",
        "LAUNCH_WINDOW_PARTIAL",
        "LAUNCH_WINDOW_TOO_SMALL",
        "LAUNCH_PRIMITIVE_UNSUPPORTED",
        "REQUIRED_LAUNCH_FEATURE_MISSING",
        "INSUFFICIENT_LAUNCH_EVENTS",
    )
    assert LAUNCH_REASON_CODES == expected


def test_launch_reason_codes_have_no_duplicates():
    assert len(LAUNCH_REASON_CODES) == len(set(LAUNCH_REASON_CODES))


def test_launch_primitive_keys_are_locked():
    expected = (
        "first_n_buyers_count",
        "first_n_unique_buyers",
        "first_n_unique_funders",
        "same_slot_buyer_count",
        "near_slot_buyer_count",
        "buyer_source_cluster_count",
        "largest_buyer_cluster_pct",
        "largest_funder_cluster_pct",
        "first_n_holder_concentration_pct",
        "repeated_source_wallet_count",
        "repeated_buyer_wallet_count",
        "launch_window_seconds",
        "launch_slot",
        "observed_slot_span",
        "first_n_events_observed",
    )
    assert LAUNCH_PRIMITIVE_KEYS == expected


# ---------------------------------------------------------------------------
# Normal broad distribution
# ---------------------------------------------------------------------------


def test_normal_distribution_yields_normal_label_and_complete_data_status():
    filter_input = make_launch_filter_input()
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_NORMAL
    assert result.data_status == DATA_STATUS_COMPLETE
    assert REASON_LAUNCH_STRUCTURE_NORMAL in result.reason_codes


def test_normal_distribution_reason_codes_subset_of_closed_set():
    result = evaluate(filter_input=make_launch_filter_input())
    for code in result.reason_codes:
        assert code in LAUNCH_REASON_CODES


def test_normal_distribution_carries_filter_identity():
    result = evaluate(filter_input=make_launch_filter_input())
    assert result.filter_name == FILTER_NAME
    assert result.filter_family == FILTER_FAMILY_LAUNCH_STRUCTURE
    assert result.filter_version == FILTER_VERSION
    assert result.threshold_version == THRESHOLD_VERSION


def test_normal_distribution_has_no_missing_features():
    result = evaluate(filter_input=make_launch_filter_input())
    assert result.missing_features == ()


# ---------------------------------------------------------------------------
# Same-slot clustering
# ---------------------------------------------------------------------------


def test_same_slot_cluster_elevated_yields_elevated_label():
    payload = make_launch_payload_summary(same_slot_buyer_count=2)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_SAME_SLOT_BUYER_CLUSTER in result.reason_codes


def test_same_slot_cluster_suspicious_yields_suspicious_label():
    payload = make_launch_payload_summary(same_slot_buyer_count=5)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_SAME_SLOT_BUYER_CLUSTER in result.reason_codes


def test_same_slot_cluster_extreme_yields_scam_likely_label():
    payload = make_launch_payload_summary(same_slot_buyer_count=8)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_SAME_SLOT_BUYER_CLUSTER in result.reason_codes


# ---------------------------------------------------------------------------
# Near-slot clustering
# ---------------------------------------------------------------------------


def test_near_slot_cluster_elevated_yields_elevated_label():
    payload = make_launch_payload_summary(near_slot_buyer_count=5)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_NEAR_SLOT_BUYER_CLUSTER in result.reason_codes


def test_near_slot_cluster_suspicious_yields_suspicious_label():
    payload = make_launch_payload_summary(near_slot_buyer_count=10)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_NEAR_SLOT_BUYER_CLUSTER in result.reason_codes


# ---------------------------------------------------------------------------
# Low unique buyer / funder counts
# ---------------------------------------------------------------------------


def test_low_unique_buyer_count_elevated_yields_elevated_label():
    payload = make_launch_payload_summary(first_n_unique_buyers=4)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_LOW_UNIQUE_BUYER_COUNT in result.reason_codes


def test_very_low_unique_buyer_count_yields_suspicious_label():
    payload = make_launch_payload_summary(first_n_unique_buyers=2)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_LOW_UNIQUE_BUYER_COUNT in result.reason_codes


def test_low_unique_funder_count_elevated_yields_elevated_label():
    payload = make_launch_payload_summary(first_n_unique_funders=4)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_LOW_UNIQUE_FUNDER_COUNT in result.reason_codes


def test_very_low_unique_funder_count_yields_suspicious_label():
    payload = make_launch_payload_summary(first_n_unique_funders=2)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_LOW_UNIQUE_FUNDER_COUNT in result.reason_codes


# ---------------------------------------------------------------------------
# Buyer / funder cluster concentration
# ---------------------------------------------------------------------------


def test_large_buyer_cluster_concentration_yields_suspicious_label():
    payload = make_launch_payload_summary(largest_buyer_cluster_pct=0.50)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_BUYER_CLUSTER_CONCENTRATION_HIGH in result.reason_codes


def test_extreme_buyer_cluster_concentration_yields_scam_likely_label():
    payload = make_launch_payload_summary(largest_buyer_cluster_pct=0.80)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_BUYER_CLUSTER_CONCENTRATION_HIGH in result.reason_codes


def test_large_funder_cluster_concentration_yields_suspicious_label():
    payload = make_launch_payload_summary(largest_funder_cluster_pct=0.50)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH in result.reason_codes


def test_extreme_funder_cluster_concentration_yields_scam_likely_label():
    payload = make_launch_payload_summary(largest_funder_cluster_pct=0.80)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_FUNDER_CLUSTER_CONCENTRATION_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# First-N holder concentration
# ---------------------------------------------------------------------------


def test_high_first_n_holder_concentration_yields_suspicious_label():
    payload = make_launch_payload_summary(
        first_n_holder_concentration_pct=0.70,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH in result.reason_codes


def test_extreme_first_n_holder_concentration_yields_scam_likely_label():
    payload = make_launch_payload_summary(
        first_n_holder_concentration_pct=0.90,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_FIRST_N_HOLDER_CONCENTRATION_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Repeated wallets
# ---------------------------------------------------------------------------


def test_repeated_source_wallets_yields_suspicious_label():
    # repeated source wallets alone, with default (low) buyer
    # cluster concentration, should escalate to SUSPICIOUS but
    # NOT trigger the bundle-like reason on its own.
    payload = make_launch_payload_summary(repeated_source_wallet_count=3)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_REPEATED_SOURCE_WALLETS in result.reason_codes
    assert REASON_BUNDLE_LIKE_LAUNCH_PATTERN not in result.reason_codes


def test_repeated_buyer_wallets_yields_at_least_elevated_label():
    payload = make_launch_payload_summary(repeated_buyer_wallet_count=4)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label in {
        LABEL_ELEVATED,
        LABEL_SUSPICIOUS,
        LABEL_SCAM_LIKELY,
    }
    assert REASON_REPEATED_BUYER_WALLETS in result.reason_codes


# ---------------------------------------------------------------------------
# Bundle-like composite signature
# ---------------------------------------------------------------------------


def test_repeated_sources_plus_high_cluster_yields_bundle_like_and_suspicious():
    payload = make_launch_payload_summary(
        repeated_source_wallet_count=3,
        largest_buyer_cluster_pct=0.45,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label in {LABEL_SUSPICIOUS, LABEL_SCAM_LIKELY}
    assert REASON_BUNDLE_LIKE_LAUNCH_PATTERN in result.reason_codes
    assert REASON_REPEATED_SOURCE_WALLETS in result.reason_codes


def test_bundle_like_does_not_trigger_without_repeated_sources():
    """High buyer cluster concentration alone does not imply
    a bundle-like launch pattern.
    """
    payload = make_launch_payload_summary(
        repeated_source_wallet_count=0,
        largest_buyer_cluster_pct=0.45,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert REASON_BUNDLE_LIKE_LAUNCH_PATTERN not in result.reason_codes


def test_bundle_like_does_not_trigger_without_high_cluster_concentration():
    payload = make_launch_payload_summary(
        repeated_source_wallet_count=3,
        largest_buyer_cluster_pct=0.10,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert REASON_BUNDLE_LIKE_LAUNCH_PATTERN not in result.reason_codes


def test_extreme_bundle_like_combination_yields_scam_likely_label():
    """Same-slot clustering + repeated source wallets + very high
    first-N holder concentration must escalate to SCAM_LIKELY.
    """
    payload = make_launch_payload_summary(
        same_slot_buyer_count=5,
        repeated_source_wallet_count=4,
        first_n_holder_concentration_pct=0.90,
        largest_buyer_cluster_pct=0.45,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_BUNDLE_LIKE_LAUNCH_PATTERN in result.reason_codes


# ---------------------------------------------------------------------------
# Missing launch window -- not NORMAL
# ---------------------------------------------------------------------------


def test_completely_empty_payload_yields_missing_input_label():
    filter_input = make_filter_input(
        payload_summary=empty_payload_summary()
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_MISSING_INPUT
    assert result.data_status == DATA_STATUS_MISSING
    assert REASON_LAUNCH_WINDOW_MISSING in result.reason_codes


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
    assert set(result.missing_features) == set(LAUNCH_PRIMITIVE_KEYS)


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
# Partial launch window
# ---------------------------------------------------------------------------


def test_partial_payload_missing_required_features_yields_insufficient_data():
    """If none of the required structural primitives are present
    but some launch primitives are, we cannot reach a concrete
    severity verdict -- the result is INSUFFICIENT_DATA / PARTIAL
    with REQUIRED_LAUNCH_FEATURE_MISSING.
    """
    payload = make_launch_payload_summary(
        first_n_buyers_count=20,
        first_n_unique_buyers=None,
        first_n_unique_funders=15,
        same_slot_buyer_count=None,
        near_slot_buyer_count=None,
        buyer_source_cluster_count=None,
        largest_buyer_cluster_pct=None,
        largest_funder_cluster_pct=None,
        first_n_holder_concentration_pct=None,
        repeated_source_wallet_count=None,
        repeated_buyer_wallet_count=None,
        launch_window_seconds=120.0,
        launch_slot=1000,
        observed_slot_span=None,
        first_n_events_observed=20,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert result.data_status == DATA_STATUS_PARTIAL
    assert REASON_REQUIRED_LAUNCH_FEATURE_MISSING in result.reason_codes
    assert REASON_LAUNCH_WINDOW_PARTIAL in result.reason_codes


def test_partial_payload_with_required_present_yields_partial_status():
    """If at least one required primitive is present but other
    optional primitives are missing, the verdict reaches a label
    but the data_status is PARTIAL with
    LAUNCH_WINDOW_PARTIAL in reason_codes.
    """
    payload = make_launch_payload_summary(
        buyer_source_cluster_count=None,
        observed_slot_span=None,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.data_status == DATA_STATUS_PARTIAL
    assert REASON_LAUNCH_WINDOW_PARTIAL in result.reason_codes


def test_partial_payload_carries_missing_feature_names_sorted():
    payload = make_launch_payload_summary(
        buyer_source_cluster_count=None,
        observed_slot_span=None,
        repeated_source_wallet_count=None,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT in result.missing_features
    assert PRIMITIVE_OBSERVED_SLOT_SPAN in result.missing_features
    assert (
        PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT in result.missing_features
    )
    assert result.missing_features == tuple(
        sorted(result.missing_features)
    )


# ---------------------------------------------------------------------------
# Unsupported primitive marker
# ---------------------------------------------------------------------------


def test_unsupported_primitive_yields_unknown_and_unsupported():
    filter_input = make_launch_filter_input(
        payload_summary=make_unsupported_launch_payload_summary(),
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert result.reason_codes == (REASON_LAUNCH_PRIMITIVE_UNSUPPORTED,)


# ---------------------------------------------------------------------------
# Insufficient launch events
# ---------------------------------------------------------------------------


def test_too_few_launch_events_yields_insufficient_data():
    payload = make_launch_payload_summary(first_n_events_observed=1)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert REASON_INSUFFICIENT_LAUNCH_EVENTS in result.reason_codes


def test_too_few_launch_events_with_zero_events_yields_insufficient_data():
    payload = make_launch_payload_summary(first_n_events_observed=0)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert REASON_INSUFFICIENT_LAUNCH_EVENTS in result.reason_codes


# ---------------------------------------------------------------------------
# Launch window too small
# ---------------------------------------------------------------------------


def test_launch_window_too_small_adds_too_small_reason_code():
    """A launch window below the placeholder threshold contributes
    a LAUNCH_WINDOW_TOO_SMALL reason and nudges the label off
    NORMAL.
    """
    payload = make_launch_payload_summary(launch_window_seconds=5.0)
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert REASON_LAUNCH_WINDOW_TOO_SMALL in result.reason_codes
    assert result.label != LABEL_NORMAL


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_yields_same_evaluation_hash():
    a = evaluate(filter_input=make_launch_filter_input())
    b = evaluate(filter_input=make_launch_filter_input())
    assert isinstance(a, Stage23FilterResult)
    assert isinstance(b, Stage23FilterResult)
    h_a = compute_evaluation_hash(
        filter_input=make_launch_filter_input(),
        filter_result=a,
    )
    h_b = compute_evaluation_hash(
        filter_input=make_launch_filter_input(),
        filter_result=b,
    )
    assert h_a == h_b


def test_numeric_feature_key_order_does_not_change_hash():
    payload_a = MappingProxyType(
        {
            PRIMITIVE_FIRST_N_UNIQUE_BUYERS: 18,
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
            PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT: 0.10,
            PRIMITIVE_LAUNCH_WINDOW_SECONDS: 120.0,
        }
    )
    payload_b = MappingProxyType(
        {
            PRIMITIVE_LAUNCH_WINDOW_SECONDS: 120.0,
            PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT: 0.10,
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
            PRIMITIVE_FIRST_N_UNIQUE_BUYERS: 18,
        }
    )
    input_a = make_launch_filter_input(payload_summary=payload_a)
    input_b = make_launch_filter_input(payload_summary=payload_b)
    res_a = evaluate(filter_input=input_a)
    res_b = evaluate(filter_input=input_b)
    h_a = compute_evaluation_hash(filter_input=input_a, filter_result=res_a)
    h_b = compute_evaluation_hash(filter_input=input_b, filter_result=res_b)
    assert h_a == h_b


def test_missing_feature_order_is_deterministic_under_payload_reorder():
    """Missing features list is sorted regardless of payload iteration order."""
    payload_a = MappingProxyType(
        {
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
            PRIMITIVE_FIRST_N_UNIQUE_BUYERS: 18,
        }
    )
    payload_b = MappingProxyType(
        {
            PRIMITIVE_FIRST_N_UNIQUE_BUYERS: 18,
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
        }
    )
    res_a = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload_a)
    )
    res_b = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload_b)
    )
    assert res_a.missing_features == res_b.missing_features


def test_evaluation_hash_changes_when_threshold_version_changes_via_result():
    """A bumped ``threshold_version`` changes the evaluation hash.

    Verifies the underlying hash invariant: the filter pins
    ``threshold_version`` on every emitted record, and a future
    bump cascades into a different evaluation hash even if every
    other field is identical.
    """
    filter_input = make_launch_filter_input()
    base = evaluate(filter_input=filter_input)
    bumped = base._replace(threshold_version="thresholds_v_other_observe_only")
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
    filter_input = make_launch_filter_input()
    base = evaluate(filter_input=filter_input)
    bumped = base._replace(filter_version="launch_structure_v_other")
    h_base = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=base,
    )
    h_bumped = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=bumped,
    )
    assert h_base != h_bumped


def test_input_hash_is_stable_for_repeated_launch_inputs():
    a = make_launch_filter_input()
    b = make_launch_filter_input()
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_changes_when_payload_launch_value_changes():
    a = make_launch_filter_input()
    b = make_launch_filter_input(
        payload_summary=make_launch_payload_summary(same_slot_buyer_count=5),
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
        lambda: make_launch_payload_summary(),
        lambda: make_launch_payload_summary(same_slot_buyer_count=2),
        lambda: make_launch_payload_summary(same_slot_buyer_count=5),
        lambda: make_launch_payload_summary(same_slot_buyer_count=8),
        lambda: make_launch_payload_summary(near_slot_buyer_count=5),
        lambda: make_launch_payload_summary(near_slot_buyer_count=10),
        lambda: make_launch_payload_summary(first_n_unique_buyers=2),
        lambda: make_launch_payload_summary(first_n_unique_buyers=4),
        lambda: make_launch_payload_summary(first_n_unique_funders=2),
        lambda: make_launch_payload_summary(first_n_unique_funders=4),
        lambda: make_launch_payload_summary(largest_buyer_cluster_pct=0.50),
        lambda: make_launch_payload_summary(largest_buyer_cluster_pct=0.80),
        lambda: make_launch_payload_summary(largest_funder_cluster_pct=0.50),
        lambda: make_launch_payload_summary(largest_funder_cluster_pct=0.80),
        lambda: make_launch_payload_summary(
            first_n_holder_concentration_pct=0.70,
        ),
        lambda: make_launch_payload_summary(
            first_n_holder_concentration_pct=0.90,
        ),
        lambda: make_launch_payload_summary(repeated_source_wallet_count=3),
        lambda: make_launch_payload_summary(repeated_buyer_wallet_count=4),
        lambda: make_launch_payload_summary(launch_window_seconds=5.0),
        lambda: make_launch_payload_summary(first_n_events_observed=1),
        lambda: empty_payload_summary(),
        lambda: make_unsupported_launch_payload_summary(),
    ],
)
def test_every_verdict_uses_closed_set_label_and_data_status(payload_factory):
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload_factory())
    )
    assert result.label in _LOCKED_LABELS_FOR_FILTER
    assert result.data_status in _LOCKED_DATA_STATUSES_FOR_FILTER


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda: make_launch_payload_summary(),
        lambda: make_launch_payload_summary(same_slot_buyer_count=5),
        lambda: make_launch_payload_summary(near_slot_buyer_count=10),
        lambda: make_launch_payload_summary(largest_buyer_cluster_pct=0.80),
        lambda: make_launch_payload_summary(
            first_n_holder_concentration_pct=0.90,
        ),
        lambda: make_launch_payload_summary(repeated_source_wallet_count=3),
        lambda: make_launch_payload_summary(first_n_events_observed=1),
        lambda: make_launch_payload_summary(launch_window_seconds=5.0),
        lambda: empty_payload_summary(),
        lambda: make_unsupported_launch_payload_summary(),
    ],
)
def test_every_verdict_uses_closed_set_reason_codes(payload_factory):
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload_factory())
    )
    for code in result.reason_codes:
        assert code in LAUNCH_REASON_CODES, (
            f"reason code {code!r} is not in the launch closed set"
        )


# ---------------------------------------------------------------------------
# Reason-code emit order is canonical
# ---------------------------------------------------------------------------


def test_reason_codes_are_in_canonical_order_when_multiple_triggers():
    payload = make_launch_payload_summary(
        same_slot_buyer_count=5,
        near_slot_buyer_count=6,
        largest_buyer_cluster_pct=0.50,
        first_n_holder_concentration_pct=0.70,
        repeated_source_wallet_count=3,
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    ranks = [LAUNCH_REASON_CODES.index(code) for code in result.reason_codes]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Protocol surface
# ---------------------------------------------------------------------------


def test_launch_structure_filter_class_has_evaluate_method():
    instance = LaunchStructureFilter()
    assert hasattr(instance, "evaluate")


def test_launch_structure_filter_class_produces_matching_result():
    instance = LaunchStructureFilter()
    direct = evaluate(filter_input=make_launch_filter_input())
    via_class = instance.evaluate(filter_input=make_launch_filter_input())
    assert direct == via_class


def test_launch_structure_filter_class_exposes_filter_identity():
    instance = LaunchStructureFilter()
    assert instance.filter_name == FILTER_NAME
    assert instance.filter_family == FILTER_FAMILY_LAUNCH_STRUCTURE
    assert instance.filter_version == FILTER_VERSION
    assert instance.threshold_version == THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Defensive contract violations
# ---------------------------------------------------------------------------


def test_negative_buyer_count_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_FIRST_N_UNIQUE_BUYERS: -3,
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


def test_negative_launch_window_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_LAUNCH_WINDOW_SECONDS: -10.0,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


def test_non_finite_pct_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT: float("inf"),
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


def test_evaluate_does_not_mutate_filter_input():
    payload = make_launch_payload_summary()
    filter_input = make_launch_filter_input(payload_summary=payload)
    snapshot_before = dict(filter_input.payload_summary)
    evaluate(filter_input=filter_input)
    snapshot_after = dict(filter_input.payload_summary)
    assert snapshot_before == snapshot_after


# ---------------------------------------------------------------------------
# No Ante parity claim
# ---------------------------------------------------------------------------


def test_no_reason_code_implies_exact_ante_parity():
    """The reason-code closed set must never imply exact parity
    with any external classifier. The filter is PHX2-native and
    emits bundle-like labels from synthetic primitives only.
    """
    for code in LAUNCH_REASON_CODES:
        upper = code.upper()
        assert "ANTE" not in upper, (
            f"reason code {code!r} must not reference Ante parity"
        )
        assert "PARITY" not in upper, (
            f"reason code {code!r} must not claim parity"
        )
        assert "EQUIVALENT" not in upper


def test_no_label_implies_exact_ante_parity():
    """The verdict-label set is the Stage 23 closed set and
    contains no Ante-equivalence label.
    """
    for label in _LOCKED_LABELS_FOR_FILTER:
        upper = label.upper()
        assert "ANTE" not in upper
        assert "PARITY" not in upper


def test_filter_identity_strings_make_no_ante_parity_claim():
    for token in (FILTER_NAME, FILTER_VERSION, THRESHOLD_VERSION):
        upper = token.upper()
        assert "ANTE" not in upper
        assert "PARITY" not in upper


# ---------------------------------------------------------------------------
# Bundle-like reason emerges only when the composite signature fires
# ---------------------------------------------------------------------------


def test_normal_payload_does_not_emit_bundle_like_reason():
    result = evaluate(filter_input=make_launch_filter_input())
    assert REASON_BUNDLE_LIKE_LAUNCH_PATTERN not in result.reason_codes


# ---------------------------------------------------------------------------
# Stage 23.6: bounded pct primitive validation
# ---------------------------------------------------------------------------


_LAUNCH_PCT_PRIMITIVES: tuple[str, ...] = (
    PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT,
    PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT,
    PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
)


@pytest.mark.parametrize("primitive_key", _LAUNCH_PCT_PRIMITIVES)
def test_launch_pct_primitive_below_zero_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: -0.05})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


@pytest.mark.parametrize("primitive_key", _LAUNCH_PCT_PRIMITIVES)
def test_launch_pct_primitive_above_one_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: 1.2})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


def test_launch_malformed_pct_cannot_produce_normal_complete():
    """Each pct primitive should refuse a -0.1 input rather than
    silently producing NORMAL/COMPLETE.
    """
    for primitive_key in _LAUNCH_PCT_PRIMITIVES:
        payload = MappingProxyType({primitive_key: -0.1})
        with pytest.raises(Stage23ContractError):
            evaluate(
                filter_input=make_launch_filter_input(
                    payload_summary=payload,
                )
            )


@pytest.mark.parametrize("primitive_key", _LAUNCH_PCT_PRIMITIVES)
def test_launch_pct_primitive_nan_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: float("nan")})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


@pytest.mark.parametrize("primitive_key", _LAUNCH_PCT_PRIMITIVES)
def test_launch_pct_primitive_positive_inf_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: float("inf")})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


@pytest.mark.parametrize("primitive_key", _LAUNCH_PCT_PRIMITIVES)
def test_launch_pct_primitive_negative_inf_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: float("-inf")})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


# ---------------------------------------------------------------------------
# Stage 23.6: closed unsupported-marker vocabulary
# ---------------------------------------------------------------------------


def test_launch_invalid_unsupported_marker_value_is_rejected():
    payload = MappingProxyType(
        {
            PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND: "off-the-vocabulary",
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


def test_launch_invalid_marker_cannot_produce_normal_complete():
    payload = MappingProxyType(
        {PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND: "bogus_marker"}
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_launch_filter_input(payload_summary=payload)
        )


def test_launch_supported_marker_value_is_accepted():
    from PHX2.stage23.launch_structure import LAUNCH_PRIMITIVE_KIND_SUPPORTED

    payload = MappingProxyType(
        {
            PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND: LAUNCH_PRIMITIVE_KIND_SUPPORTED,
            PRIMITIVE_SAME_SLOT_BUYER_COUNT: 1,
            PRIMITIVE_FIRST_N_UNIQUE_BUYERS: 10,
        }
    )
    result = evaluate(
        filter_input=make_launch_filter_input(payload_summary=payload)
    )
    assert result.data_status != DATA_STATUS_UNSUPPORTED
