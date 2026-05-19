"""Stage 23.2 holder-concentration filter tests.

Pins:

  * Filter identity strings (name / family / version /
    threshold_version) are locked.
  * Reason-code closed-set is locked.
  * Label / data_status routing for the major cases:
      - normal broad distribution -> NORMAL / COMPLETE
      - elevated concentration -> ELEVATED
      - suspicious concentration -> SUSPICIOUS
      - extreme concentration -> SCAM_LIKELY
      - missing holder snapshot -> MISSING_INPUT / MISSING
      - partial holder snapshot -> INSUFFICIENT_DATA / PARTIAL
        when the required concentration primitives are absent
      - unsupported primitive marker -> UNKNOWN / UNSUPPORTED
      - low holder count -> INSUFFICIENT_DATA + reason
      - creator / dev retained high -> SUSPICIOUS / SCAM_LIKELY
  * Determinism: same input -> same evaluation_hash; key reorder
    does not change the hash; reorder of missing_features does
    not change the hash because the filter sorts the missing
    tuple deterministically.
  * Threshold-version separation: a (hypothetical) bump of
    ``threshold_version`` changes the hash; the test exercises
    the underlying invariant by mutating a result and re-hashing.
  * Reason codes are a closed-set.
  * Filter satisfies the ``Stage23Filter`` Protocol surface (a
    class-shape with an ``evaluate`` method).
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_UNSUPPORTED,
    FILTER_FAMILY_HOLDER_CONCENTRATION,
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
from PHX2.stage23.holder_concentration import (
    FILTER_NAME,
    FILTER_VERSION,
    HOLDER_PRIMITIVE_KEYS,
    HOLDER_REASON_CODES,
    HolderConcentrationFilter,
    PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND,
    PRIMITIVE_CREATOR_RETAINED_PCT,
    PRIMITIVE_DEV_RELATED_RETAINED_PCT,
    PRIMITIVE_POOL_RELATED_PCT,
    PRIMITIVE_SNAPSHOT_AGE_SECONDS,
    PRIMITIVE_TOP_1_HOLDER_PCT,
    PRIMITIVE_TOP_5_HOLDER_PCT,
    PRIMITIVE_TOP_10_HOLDER_PCT,
    PRIMITIVE_TOP_20_HOLDER_PCT,
    PRIMITIVE_TOP_50_HOLDER_PCT,
    PRIMITIVE_UNIQUE_HOLDER_COUNT,
    REASON_CREATOR_RETAINED_HIGH,
    REASON_DEV_RELATED_RETAINED_HIGH,
    REASON_HOLDER_CONCENTRATION_NORMAL,
    REASON_HOLDER_PRIMITIVE_UNSUPPORTED,
    REASON_HOLDER_SNAPSHOT_MISSING,
    REASON_HOLDER_SNAPSHOT_PARTIAL,
    REASON_HOLDER_SNAPSHOT_TOO_OLD,
    REASON_INSUFFICIENT_HOLDER_COUNT,
    REASON_LOW_HOLDER_BREADTH,
    REASON_POOL_RELATED_CONCENTRATION_HIGH,
    REASON_REQUIRED_HOLDER_FEATURE_MISSING,
    REASON_TOP_1_CONCENTRATION_ELEVATED,
    REASON_TOP_10_CONCENTRATION_HIGH,
    REASON_TOP_20_CONCENTRATION_HIGH,
    REASON_TOP_50_CONCENTRATION_HIGH,
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
    make_holder_filter_input,
    make_holder_payload_summary,
    make_unsupported_holder_payload_summary,
)


# ---------------------------------------------------------------------------
# Filter identity
# ---------------------------------------------------------------------------


def test_filter_name_is_locked():
    assert FILTER_NAME == "holder_concentration"


def test_filter_version_is_locked():
    assert FILTER_VERSION == "holder_concentration_v0"


def test_threshold_version_is_locked():
    assert THRESHOLD_VERSION == "thresholds_v0_observe_only"


def test_filter_family_is_holder_concentration():
    assert FILTER_FAMILY_HOLDER_CONCENTRATION == "HOLDER_CONCENTRATION"


def test_filter_family_member_of_closed_set():
    assert Stage23FilterFamily.contains(FILTER_FAMILY_HOLDER_CONCENTRATION)


def test_filter_version_and_threshold_version_are_different_strings():
    assert FILTER_VERSION != THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Reason-code closed set
# ---------------------------------------------------------------------------


def test_holder_reason_codes_are_locked():
    expected = (
        "HOLDER_CONCENTRATION_NORMAL",
        "TOP_1_CONCENTRATION_ELEVATED",
        "TOP_10_CONCENTRATION_HIGH",
        "TOP_20_CONCENTRATION_HIGH",
        "TOP_50_CONCENTRATION_HIGH",
        "LOW_HOLDER_BREADTH",
        "CREATOR_RETAINED_HIGH",
        "DEV_RELATED_RETAINED_HIGH",
        "POOL_RELATED_CONCENTRATION_HIGH",
        "HOLDER_SNAPSHOT_MISSING",
        "HOLDER_SNAPSHOT_PARTIAL",
        "HOLDER_SNAPSHOT_TOO_OLD",
        "HOLDER_PRIMITIVE_UNSUPPORTED",
        "INSUFFICIENT_HOLDER_COUNT",
        "REQUIRED_HOLDER_FEATURE_MISSING",
    )
    assert HOLDER_REASON_CODES == expected


def test_holder_reason_codes_have_no_duplicates():
    assert len(HOLDER_REASON_CODES) == len(set(HOLDER_REASON_CODES))


def test_holder_primitive_keys_are_locked():
    expected = (
        "unique_holder_count",
        "top_1_holder_pct",
        "top_5_holder_pct",
        "top_10_holder_pct",
        "top_20_holder_pct",
        "top_50_holder_pct",
        "creator_retained_pct",
        "dev_related_retained_pct",
        "pool_related_pct",
        "snapshot_age_seconds",
    )
    assert HOLDER_PRIMITIVE_KEYS == expected


# ---------------------------------------------------------------------------
# Normal broad distribution
# ---------------------------------------------------------------------------


def test_normal_distribution_yields_normal_label_and_complete_data_status():
    filter_input = make_holder_filter_input()
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_NORMAL
    assert result.data_status == DATA_STATUS_COMPLETE
    assert REASON_HOLDER_CONCENTRATION_NORMAL in result.reason_codes


def test_normal_distribution_reason_codes_subset_of_closed_set():
    result = evaluate(filter_input=make_holder_filter_input())
    for code in result.reason_codes:
        assert code in HOLDER_REASON_CODES


def test_normal_distribution_carries_filter_identity():
    result = evaluate(filter_input=make_holder_filter_input())
    assert result.filter_name == FILTER_NAME
    assert result.filter_family == FILTER_FAMILY_HOLDER_CONCENTRATION
    assert result.filter_version == FILTER_VERSION
    assert result.threshold_version == THRESHOLD_VERSION


def test_normal_distribution_has_no_missing_features():
    result = evaluate(filter_input=make_holder_filter_input())
    assert result.missing_features == ()


# ---------------------------------------------------------------------------
# Elevated concentration
# ---------------------------------------------------------------------------


def test_top_1_elevated_yields_elevated_label():
    payload = make_holder_payload_summary(top_1_holder_pct=0.20)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_TOP_1_CONCENTRATION_ELEVATED in result.reason_codes


def test_top_10_elevated_yields_elevated_label():
    payload = make_holder_payload_summary(
        top_1_holder_pct=0.05,
        top_10_holder_pct=0.55,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_TOP_10_CONCENTRATION_HIGH in result.reason_codes


def test_top_50_elevated_alone_yields_elevated_label():
    payload = make_holder_payload_summary(
        top_50_holder_pct=0.75,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_ELEVATED
    assert REASON_TOP_50_CONCENTRATION_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Suspicious concentration
# ---------------------------------------------------------------------------


def test_top_1_suspicious_yields_suspicious_label():
    payload = make_holder_payload_summary(top_1_holder_pct=0.35)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_TOP_1_CONCENTRATION_ELEVATED in result.reason_codes


def test_top_10_suspicious_yields_suspicious_label():
    payload = make_holder_payload_summary(top_10_holder_pct=0.85)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_TOP_10_CONCENTRATION_HIGH in result.reason_codes


def test_top_20_suspicious_yields_suspicious_label():
    payload = make_holder_payload_summary(top_20_holder_pct=0.92)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_TOP_20_CONCENTRATION_HIGH in result.reason_codes


def test_pool_related_high_yields_suspicious_label():
    payload = make_holder_payload_summary(pool_related_pct=0.65)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_POOL_RELATED_CONCENTRATION_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Extreme / scam-likely concentration
# ---------------------------------------------------------------------------


def test_top_1_extreme_yields_scam_likely_label():
    payload = make_holder_payload_summary(top_1_holder_pct=0.65)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_TOP_1_CONCENTRATION_ELEVATED in result.reason_codes


def test_top_10_extreme_yields_scam_likely_label():
    payload = make_holder_payload_summary(top_10_holder_pct=0.98)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_TOP_10_CONCENTRATION_HIGH in result.reason_codes


def test_creator_retained_extreme_yields_scam_likely_label():
    payload = make_holder_payload_summary(creator_retained_pct=0.60)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_CREATOR_RETAINED_HIGH in result.reason_codes


def test_dev_related_retained_extreme_yields_scam_likely_label():
    payload = make_holder_payload_summary(
        dev_related_retained_pct=0.60,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SCAM_LIKELY
    assert REASON_DEV_RELATED_RETAINED_HIGH in result.reason_codes


def test_creator_retained_suspicious_yields_suspicious_label():
    payload = make_holder_payload_summary(creator_retained_pct=0.30)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_CREATOR_RETAINED_HIGH in result.reason_codes


def test_dev_related_retained_suspicious_yields_suspicious_label():
    payload = make_holder_payload_summary(dev_related_retained_pct=0.30)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_SUSPICIOUS
    assert REASON_DEV_RELATED_RETAINED_HIGH in result.reason_codes


# ---------------------------------------------------------------------------
# Missing snapshot -- not NORMAL
# ---------------------------------------------------------------------------


def test_completely_empty_payload_yields_missing_input_label():
    filter_input = make_filter_input(
        payload_summary=empty_payload_summary()
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_MISSING_INPUT
    assert result.data_status == DATA_STATUS_MISSING
    assert REASON_HOLDER_SNAPSHOT_MISSING in result.reason_codes


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
    assert set(result.missing_features) == set(HOLDER_PRIMITIVE_KEYS)


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
# Partial snapshot -- INSUFFICIENT_DATA / PARTIAL with explicit reason
# ---------------------------------------------------------------------------


def test_partial_snapshot_missing_required_features_yields_insufficient_data():
    payload = make_holder_payload_summary(
        unique_holder_count=300,
        top_1_holder_pct=0.05,
        top_5_holder_pct=0.10,
        top_10_holder_pct=None,
        top_20_holder_pct=None,
        top_50_holder_pct=0.40,
        creator_retained_pct=0.10,
        dev_related_retained_pct=0.10,
        pool_related_pct=0.20,
        snapshot_age_seconds=30.0,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert result.data_status == DATA_STATUS_PARTIAL
    assert REASON_REQUIRED_HOLDER_FEATURE_MISSING in result.reason_codes
    assert REASON_HOLDER_SNAPSHOT_PARTIAL in result.reason_codes


def test_partial_snapshot_carries_missing_feature_names_sorted():
    payload = make_holder_payload_summary(
        top_10_holder_pct=None,
        top_20_holder_pct=None,
        creator_retained_pct=None,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert PRIMITIVE_CREATOR_RETAINED_PCT in result.missing_features
    assert PRIMITIVE_TOP_10_HOLDER_PCT in result.missing_features
    assert PRIMITIVE_TOP_20_HOLDER_PCT in result.missing_features
    assert result.missing_features == tuple(
        sorted(result.missing_features)
    )


def test_partial_snapshot_with_required_present_yields_partial_status():
    payload = make_holder_payload_summary(
        top_50_holder_pct=None,
        snapshot_age_seconds=None,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.data_status == DATA_STATUS_PARTIAL
    assert REASON_HOLDER_SNAPSHOT_PARTIAL in result.reason_codes


# ---------------------------------------------------------------------------
# Unsupported primitive family
# ---------------------------------------------------------------------------


def test_unsupported_primitive_yields_unknown_and_unsupported():
    filter_input = make_holder_filter_input(
        payload_summary=make_unsupported_holder_payload_summary(),
    )
    result = evaluate(filter_input=filter_input)
    assert result.label == LABEL_UNKNOWN
    assert result.data_status == DATA_STATUS_UNSUPPORTED
    assert result.reason_codes == (REASON_HOLDER_PRIMITIVE_UNSUPPORTED,)


# ---------------------------------------------------------------------------
# Low holder count
# ---------------------------------------------------------------------------


def test_very_low_holder_count_yields_insufficient_data():
    payload = make_holder_payload_summary(unique_holder_count=2)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert result.label == LABEL_INSUFFICIENT_DATA
    assert REASON_INSUFFICIENT_HOLDER_COUNT in result.reason_codes


def test_low_holder_breadth_adds_breadth_reason_code():
    payload = make_holder_payload_summary(unique_holder_count=10)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    # Low breadth contributes; the label should escalate at least
    # to ELEVATED but never default to NORMAL.
    assert result.label != LABEL_NORMAL
    assert REASON_LOW_HOLDER_BREADTH in result.reason_codes


# ---------------------------------------------------------------------------
# Snapshot age
# ---------------------------------------------------------------------------


def test_old_snapshot_adds_too_old_reason_code():
    payload = make_holder_payload_summary(snapshot_age_seconds=7200.0)
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    assert REASON_HOLDER_SNAPSHOT_TOO_OLD in result.reason_codes


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_yields_same_evaluation_hash():
    a = evaluate(filter_input=make_holder_filter_input())
    b = evaluate(filter_input=make_holder_filter_input())
    assert isinstance(a, Stage23FilterResult)
    assert isinstance(b, Stage23FilterResult)
    h_a = compute_evaluation_hash(
        filter_input=make_holder_filter_input(),
        filter_result=a,
    )
    h_b = compute_evaluation_hash(
        filter_input=make_holder_filter_input(),
        filter_result=b,
    )
    assert h_a == h_b


def test_numeric_feature_key_order_does_not_change_hash():
    payload_a = MappingProxyType(
        {
            PRIMITIVE_UNIQUE_HOLDER_COUNT: 300,
            PRIMITIVE_TOP_1_HOLDER_PCT: 0.05,
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.25,
            PRIMITIVE_TOP_20_HOLDER_PCT: 0.35,
        }
    )
    payload_b = MappingProxyType(
        {
            PRIMITIVE_TOP_20_HOLDER_PCT: 0.35,
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.25,
            PRIMITIVE_TOP_1_HOLDER_PCT: 0.05,
            PRIMITIVE_UNIQUE_HOLDER_COUNT: 300,
        }
    )
    input_a = make_holder_filter_input(payload_summary=payload_a)
    input_b = make_holder_filter_input(payload_summary=payload_b)
    res_a = evaluate(filter_input=input_a)
    res_b = evaluate(filter_input=input_b)
    h_a = compute_evaluation_hash(filter_input=input_a, filter_result=res_a)
    h_b = compute_evaluation_hash(filter_input=input_b, filter_result=res_b)
    assert h_a == h_b


def test_missing_feature_order_is_deterministic_under_payload_reorder():
    """Missing features list is sorted regardless of payload iteration order."""
    payload_a = MappingProxyType(
        {
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.25,
            PRIMITIVE_CREATOR_RETAINED_PCT: 0.05,
        }
    )
    payload_b = MappingProxyType(
        {
            PRIMITIVE_CREATOR_RETAINED_PCT: 0.05,
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.25,
        }
    )
    res_a = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload_a)
    )
    res_b = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload_b)
    )
    assert res_a.missing_features == res_b.missing_features


def test_evaluation_hash_changes_when_threshold_version_changes_via_result():
    """A bumped ``threshold_version`` changes the evaluation hash.

    Verifies the underlying hash invariant: the filter pins
    ``threshold_version`` on every emitted record, and a future
    bump cascades into a different evaluation hash even if every
    other field is identical.
    """
    filter_input = make_holder_filter_input()
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
    filter_input = make_holder_filter_input()
    base = evaluate(filter_input=filter_input)
    bumped = base._replace(filter_version="holder_concentration_v_other")
    h_base = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=base,
    )
    h_bumped = compute_evaluation_hash(
        filter_input=filter_input,
        filter_result=bumped,
    )
    assert h_base != h_bumped


def test_input_hash_is_stable_for_repeated_holder_inputs():
    a = make_holder_filter_input()
    b = make_holder_filter_input()
    assert compute_input_hash(a) == compute_input_hash(b)


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
        lambda: make_holder_payload_summary(),
        lambda: make_holder_payload_summary(top_1_holder_pct=0.20),
        lambda: make_holder_payload_summary(top_1_holder_pct=0.35),
        lambda: make_holder_payload_summary(top_1_holder_pct=0.65),
        lambda: make_holder_payload_summary(top_10_holder_pct=0.55),
        lambda: make_holder_payload_summary(top_10_holder_pct=0.85),
        lambda: make_holder_payload_summary(top_10_holder_pct=0.98),
        lambda: make_holder_payload_summary(top_20_holder_pct=0.62),
        lambda: make_holder_payload_summary(top_20_holder_pct=0.92),
        lambda: make_holder_payload_summary(top_50_holder_pct=0.75),
        lambda: make_holder_payload_summary(creator_retained_pct=0.30),
        lambda: make_holder_payload_summary(creator_retained_pct=0.60),
        lambda: make_holder_payload_summary(dev_related_retained_pct=0.30),
        lambda: make_holder_payload_summary(dev_related_retained_pct=0.60),
        lambda: make_holder_payload_summary(pool_related_pct=0.65),
        lambda: make_holder_payload_summary(unique_holder_count=2),
        lambda: make_holder_payload_summary(unique_holder_count=10),
        lambda: make_holder_payload_summary(snapshot_age_seconds=7200.0),
        lambda: empty_payload_summary(),
        lambda: make_unsupported_holder_payload_summary(),
    ],
)
def test_every_verdict_uses_closed_set_label_and_data_status(payload_factory):
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload_factory())
    )
    assert result.label in _LOCKED_LABELS_FOR_FILTER
    assert result.data_status in _LOCKED_DATA_STATUSES_FOR_FILTER


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda: make_holder_payload_summary(),
        lambda: make_holder_payload_summary(top_1_holder_pct=0.35),
        lambda: make_holder_payload_summary(top_1_holder_pct=0.65),
        lambda: make_holder_payload_summary(creator_retained_pct=0.60),
        lambda: make_holder_payload_summary(unique_holder_count=2),
        lambda: make_holder_payload_summary(snapshot_age_seconds=7200.0),
        lambda: empty_payload_summary(),
        lambda: make_unsupported_holder_payload_summary(),
    ],
)
def test_every_verdict_uses_closed_set_reason_codes(payload_factory):
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload_factory())
    )
    for code in result.reason_codes:
        assert code in HOLDER_REASON_CODES, (
            f"reason code {code!r} is not in the holder closed set"
        )


# ---------------------------------------------------------------------------
# Reason-code emit order is canonical
# ---------------------------------------------------------------------------


def test_reason_codes_are_in_canonical_order_when_multiple_triggers():
    payload = make_holder_payload_summary(
        top_10_holder_pct=0.85,
        top_20_holder_pct=0.92,
        creator_retained_pct=0.30,
        snapshot_age_seconds=7200.0,
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    ranks = [HOLDER_REASON_CODES.index(code) for code in result.reason_codes]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# Protocol surface
# ---------------------------------------------------------------------------


def test_holder_concentration_filter_class_has_evaluate_method():
    instance = HolderConcentrationFilter()
    assert hasattr(instance, "evaluate")


def test_holder_concentration_filter_class_produces_matching_result():
    instance = HolderConcentrationFilter()
    direct = evaluate(filter_input=make_holder_filter_input())
    via_class = instance.evaluate(filter_input=make_holder_filter_input())
    assert direct == via_class


def test_holder_concentration_filter_class_exposes_filter_identity():
    instance = HolderConcentrationFilter()
    assert instance.filter_name == FILTER_NAME
    assert instance.filter_family == FILTER_FAMILY_HOLDER_CONCENTRATION
    assert instance.filter_version == FILTER_VERSION
    assert instance.threshold_version == THRESHOLD_VERSION


# ---------------------------------------------------------------------------
# Defensive contract violations
# ---------------------------------------------------------------------------


def test_negative_holder_count_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_UNIQUE_HOLDER_COUNT: -5,
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.20,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


def test_non_finite_pct_is_rejected():
    payload = MappingProxyType(
        {
            PRIMITIVE_TOP_10_HOLDER_PCT: float("inf"),
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


# ---------------------------------------------------------------------------
# Stage 23.6: bounded pct primitive validation
# ---------------------------------------------------------------------------
#
# The filter must refuse pct primitives outside [0.0, 1.0]. Without
# the bound the filter would otherwise classify a malformed -0.1
# or 1.5 as NORMAL because each threshold check is one-sided.


_HOLDER_PCT_PRIMITIVES: tuple[str, ...] = (
    PRIMITIVE_TOP_1_HOLDER_PCT,
    PRIMITIVE_TOP_5_HOLDER_PCT,
    PRIMITIVE_TOP_10_HOLDER_PCT,
    PRIMITIVE_TOP_20_HOLDER_PCT,
    PRIMITIVE_TOP_50_HOLDER_PCT,
    PRIMITIVE_CREATOR_RETAINED_PCT,
    PRIMITIVE_DEV_RELATED_RETAINED_PCT,
    PRIMITIVE_POOL_RELATED_PCT,
)


@pytest.mark.parametrize("primitive_key", _HOLDER_PCT_PRIMITIVES)
def test_holder_pct_primitive_below_zero_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: -0.1})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


@pytest.mark.parametrize("primitive_key", _HOLDER_PCT_PRIMITIVES)
def test_holder_pct_primitive_above_one_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: 1.5})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


def test_holder_malformed_pct_cannot_produce_normal_complete():
    """Each pct primitive should refuse a -0.1 input rather than
    silently producing NORMAL/COMPLETE.
    """
    for primitive_key in _HOLDER_PCT_PRIMITIVES:
        payload = MappingProxyType({primitive_key: -0.1})
        with pytest.raises(Stage23ContractError):
            evaluate(
                filter_input=make_holder_filter_input(
                    payload_summary=payload,
                )
            )


@pytest.mark.parametrize("primitive_key", _HOLDER_PCT_PRIMITIVES)
def test_holder_pct_primitive_nan_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: float("nan")})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


@pytest.mark.parametrize("primitive_key", _HOLDER_PCT_PRIMITIVES)
def test_holder_pct_primitive_positive_inf_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: float("inf")})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


@pytest.mark.parametrize("primitive_key", _HOLDER_PCT_PRIMITIVES)
def test_holder_pct_primitive_negative_inf_is_rejected(primitive_key):
    payload = MappingProxyType({primitive_key: float("-inf")})
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


# ---------------------------------------------------------------------------
# Stage 23.6: closed unsupported-marker vocabulary
# ---------------------------------------------------------------------------


def test_holder_invalid_unsupported_marker_value_is_rejected():
    """Marker key present with a non-closed-set value must NOT
    silently fall through to normal classification.
    """
    payload = MappingProxyType(
        {
            PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND: "definitely_not_supported",
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.20,
        }
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


def test_holder_invalid_marker_cannot_produce_normal_complete():
    """An invalid marker value must not yield NORMAL/COMPLETE via the
    runner's catch-all path. Calling ``evaluate`` directly raises
    ``Stage23ContractError`` rather than returning a NORMAL result.
    """
    payload = MappingProxyType(
        {PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND: "bogus_marker"}
    )
    with pytest.raises(Stage23ContractError):
        evaluate(
            filter_input=make_holder_filter_input(payload_summary=payload)
        )


def test_holder_supported_marker_value_is_accepted():
    """The closed-set ``"supported"`` token must pass through
    without raising.
    """
    from PHX2.stage23.holder_concentration import (
        HOLDER_PRIMITIVE_KIND_SUPPORTED,
    )

    payload = MappingProxyType(
        {
            PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND: HOLDER_PRIMITIVE_KIND_SUPPORTED,
            PRIMITIVE_TOP_10_HOLDER_PCT: 0.20,
        }
    )
    result = evaluate(
        filter_input=make_holder_filter_input(payload_summary=payload)
    )
    # supported = primitives are usable; should not flip to UNSUPPORTED.
    assert result.data_status != DATA_STATUS_UNSUPPORTED


# ---------------------------------------------------------------------------
# Sanity: 23.1 input_hash semantics still apply to holder inputs
# ---------------------------------------------------------------------------


def test_input_hash_changes_when_payload_holder_value_changes():
    a = make_holder_filter_input()
    b = make_holder_filter_input(
        payload_summary=make_holder_payload_summary(top_10_holder_pct=0.40),
    )
    assert compute_input_hash(a) != compute_input_hash(b)


def test_evaluate_does_not_mutate_filter_input():
    payload = make_holder_payload_summary()
    filter_input = make_holder_filter_input(payload_summary=payload)
    snapshot_before = dict(filter_input.payload_summary)
    evaluate(filter_input=filter_input)
    snapshot_after = dict(filter_input.payload_summary)
    assert snapshot_before == snapshot_after
