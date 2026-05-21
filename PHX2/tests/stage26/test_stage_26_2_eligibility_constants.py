"""Stage 26.2 eligibility-constants tests.

Pins the locked Stage 26.2 closed sets and the truth-class to
eligibility-decision mapping in
``PHX2/stage26/eligibility_constants.py``.
"""

from __future__ import annotations


from PHX2.stage26.constants import MEASUREMENT_TRUTH_CLASSES
from PHX2.stage26.eligibility_constants import (
    CALIBRATION_ELIGIBILITY_KIND_COVERAGE_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_REJECTION_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE,
    CALIBRATION_ELIGIBILITY_KINDS,
    DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR,
    DENOMINATOR_STATUS_EXCLUDED_FROM_PRIMARY_DENOMINATOR,
    DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
    DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR,
    DENOMINATOR_STATUS_REJECTION_DENOMINATOR,
    DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR,
    DENOMINATOR_STATUSES,
    ELIGIBILITY_DECISION_BY_TRUTH_CLASS,
    OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_INELIGIBLE_INVALID_INPUT,
    OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE,
    OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY,
    OUTCOME_ELIGIBILITY_STATUSES,
    PRIMARY_DENOMINATOR_REASON_INVALID_INPUT_RECORD,
    PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH,
    PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_WINDOW_INELIGIBLE,
    PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASONS,
    STAGE26_ELIGIBILITY_VERSION,
)


# ---------------------------------------------------------------------------
# Closed-set shape
# ---------------------------------------------------------------------------


def _assert_closed_set(tokens: tuple[str, ...]) -> None:
    assert isinstance(tokens, tuple), "closed sets must be tuples"
    assert len(tokens) > 0, "closed sets must be non-empty"
    assert len(set(tokens)) == len(tokens), "no duplicate tokens"
    for token in tokens:
        assert isinstance(token, str)
        assert token != ""
        assert token == token.upper(), f"{token!r} must be uppercase"
        assert " " not in token


def test_denominator_statuses_closed_set_shape():
    _assert_closed_set(DENOMINATOR_STATUSES)


def test_outcome_eligibility_statuses_closed_set_shape():
    _assert_closed_set(OUTCOME_ELIGIBILITY_STATUSES)


def test_primary_denominator_reasons_closed_set_shape():
    _assert_closed_set(PRIMARY_DENOMINATOR_REASONS)


def test_calibration_eligibility_kinds_closed_set_shape():
    _assert_closed_set(CALIBRATION_ELIGIBILITY_KINDS)


# ---------------------------------------------------------------------------
# Closed-set membership (locked tokens are present)
# ---------------------------------------------------------------------------


def test_denominator_statuses_lock_membership():
    assert set(DENOMINATOR_STATUSES) == {
        DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR,
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
        DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR,
        DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR,
        DENOMINATOR_STATUS_REJECTION_DENOMINATOR,
        DENOMINATOR_STATUS_EXCLUDED_FROM_PRIMARY_DENOMINATOR,
    }


def test_outcome_eligibility_statuses_lock_membership():
    assert set(OUTCOME_ELIGIBILITY_STATUSES) == {
        OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE,
        OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
        OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY,
        OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY,
        OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY,
        OUTCOME_ELIGIBILITY_STATUS_INELIGIBLE_INVALID_INPUT,
    }


def test_primary_denominator_reasons_lock_membership():
    assert set(PRIMARY_DENOMINATOR_REASONS) == {
        PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_WINDOW_INELIGIBLE,
        PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT,
        PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT,
        PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT,
        PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT,
        PRIMARY_DENOMINATOR_REASON_INVALID_INPUT_RECORD,
    }


def test_calibration_eligibility_kinds_lock_membership():
    assert set(CALIBRATION_ELIGIBILITY_KINDS) == {
        CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE,
        CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY,
        CALIBRATION_ELIGIBILITY_KIND_COVERAGE_CONTEXT_ONLY,
        CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY,
        CALIBRATION_ELIGIBILITY_KIND_REJECTION_CONTEXT_ONLY,
        "INVALID_CONTEXT_ONLY",
    }


# ---------------------------------------------------------------------------
# Eligibility-decision mapping
# ---------------------------------------------------------------------------


def test_mapping_is_immutable_tuple_of_tuples():
    assert isinstance(ELIGIBILITY_DECISION_BY_TRUTH_CLASS, tuple)
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        assert isinstance(entry, tuple)
        assert len(entry) == 8


def test_mapping_truth_class_column_matches_stage26_truth_classes():
    """Every Stage 26.1 MEASUREMENT_TRUTH_CLASS has an explicit mapping."""
    mapped_truth_classes = {entry[0] for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS}
    assert mapped_truth_classes == set(MEASUREMENT_TRUTH_CLASSES), (
        "Stage 26.2 eligibility mapping must cover every Stage 26.1 "
        "MEASUREMENT_TRUTH_CLASS exactly once."
    )


def test_mapping_has_no_duplicate_truth_class_rows():
    seen: set[str] = set()
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        truth_class = entry[0]
        assert truth_class not in seen, (
            f"truth class {truth_class!r} appears more than once"
        )
        seen.add(truth_class)


def test_mapping_columns_belong_to_locked_closed_sets():
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        (
            _truth_class,
            denominator_status,
            outcome_status,
            reason,
            calibration_kind,
            thr_elig,
            primary_elig,
            obs_elig,
        ) = entry
        assert denominator_status in DENOMINATOR_STATUSES
        assert outcome_status in OUTCOME_ELIGIBILITY_STATUSES
        assert reason in PRIMARY_DENOMINATOR_REASONS
        assert calibration_kind in CALIBRATION_ELIGIBILITY_KINDS
        assert isinstance(thr_elig, bool)
        assert isinstance(primary_elig, bool)
        assert isinstance(obs_elig, bool)


def test_measured_row_is_primary_and_threshold_eligible():
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    entry = mapping["MEASURED"]
    assert entry[1] == DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR
    assert entry[2] == OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE
    assert entry[3] == PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH
    assert entry[4] == (
        CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE
    )
    assert entry[5] is True   # threshold eligible
    assert entry[6] is True   # primary metrics eligible
    assert entry[7] is True   # observability eligible


def test_only_measured_row_is_threshold_eligible():
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        threshold_eligible = entry[5]
        if entry[0] == "MEASURED":
            assert threshold_eligible is True
        else:
            assert threshold_eligible is False, (
                f"non-MEASURED truth class {entry[0]!r} must NEVER be "
                f"threshold eligible"
            )


def test_only_measured_row_is_primary_metrics_eligible():
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        primary_eligible = entry[6]
        if entry[0] == "MEASURED":
            assert primary_eligible is True
        else:
            assert primary_eligible is False, (
                f"non-MEASURED truth class {entry[0]!r} must NEVER be "
                f"primary-metrics eligible"
            )


def test_partial_source_conflict_ambiguous_are_observability_only():
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    for truth_class, reason in (
        ("PARTIAL", PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL),
        (
            "SOURCE_CONFLICT",
            PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT,
        ),
        (
            "AMBIGUOUS",
            PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS,
        ),
    ):
        entry = mapping[truth_class]
        assert entry[1] == DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR
        assert entry[2] == OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY
        assert entry[3] == reason
        assert entry[5] is False   # not threshold
        assert entry[6] is False   # not primary
        assert entry[7] is True    # observability eligible


def test_missing_maps_to_coverage_gap_only():
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    entry = mapping["MISSING"]
    assert entry[1] == DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR
    assert entry[2] == OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY
    assert entry[3] == PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT
    assert entry[5] is False
    assert entry[6] is False
    assert entry[7] is False


def test_unsupported_maps_to_scope_gap_only():
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    entry = mapping["UNSUPPORTED"]
    assert entry[1] == DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR
    assert entry[2] == OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY
    assert entry[3] == PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT
    assert entry[5] is False
    assert entry[6] is False
    assert entry[7] is False


def test_rejected_maps_to_rejection_only():
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    entry = mapping["REJECTED"]
    assert entry[1] == DENOMINATOR_STATUS_REJECTION_DENOMINATOR
    assert entry[2] == OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY
    assert entry[3] == PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT
    assert entry[5] is False
    assert entry[6] is False
    assert entry[7] is False


def test_not_applicable_maps_to_scope_gap_only_with_distinct_reason():
    """NOT_APPLICABLE shares the scope-gap bucket with UNSUPPORTED but
    carries its own distinct ``PRIMARY_DENOMINATOR_REASON`` so Stage
    26.2 does not collapse two Stage 25 truth classes.
    """
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    entry = mapping["NOT_APPLICABLE"]
    assert entry[1] == DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR
    assert entry[2] == OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY
    assert (
        entry[3] == PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT
    )
    # Distinct from UNSUPPORTED.
    assert (
        PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT
        != PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT
    )


def test_version_axis_is_stage26_eligibility_v0():
    assert STAGE26_ELIGIBILITY_VERSION == "stage26_eligibility_v0"


def test_missing_is_not_the_same_as_unsupported():
    """MISSING and UNSUPPORTED must NEVER collapse to the same bucket
    or share a denominator-reason token.
    """
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    missing_entry = mapping["MISSING"]
    unsupported_entry = mapping["UNSUPPORTED"]
    assert missing_entry[1] != unsupported_entry[1], (
        "MISSING (coverage gap) and UNSUPPORTED (scope gap) must "
        "carry distinct denominator buckets"
    )
    assert missing_entry[2] != unsupported_entry[2]
    assert missing_entry[3] != unsupported_entry[3]


def test_unsupported_is_not_the_same_as_rejected():
    """UNSUPPORTED and REJECTED must NEVER collapse to the same bucket
    or share a denominator-reason token.
    """
    mapping = {
        entry[0]: entry
        for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS
    }
    unsupported_entry = mapping["UNSUPPORTED"]
    rejected_entry = mapping["REJECTED"]
    assert unsupported_entry[1] != rejected_entry[1]
    assert unsupported_entry[2] != rejected_entry[2]
    assert unsupported_entry[3] != rejected_entry[3]
