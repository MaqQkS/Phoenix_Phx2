"""Stage 26.3 cohort-model tests.

Pins the NamedTuple shape, immutability, and field ordering of the
Stage 26.3 cohort records.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.cohort_constants import (
    COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    COHORT_STATUS_VALID_COHORT,
    STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_COHORT_VERSION,
)
from PHX2.stage26.cohort_models import (
    Stage26CohortBuildRequest,
    Stage26CohortBuildResult,
    Stage26CohortKey,
    Stage26CohortMember,
    Stage26CohortSummary,
)
from PHX2.stage26.eligibility_models import (
    Stage26EligibilityResult,
    Stage26EligibilitySummary,
)
from PHX2.stage26.models import Stage25ArtifactReference


# ---------------------------------------------------------------------------
# Sample helpers
# ---------------------------------------------------------------------------


def _sample_pin() -> Stage25ArtifactReference:
    return Stage25ArtifactReference(
        artifact_basename="stage25_manifest.json",
        artifact_sha256="c" * 64,
    )


def _sample_key() -> Stage26CohortKey:
    return Stage26CohortKey(
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
        values=("MEASURED",),
    )


def _sample_member() -> Stage26CohortMember:
    return Stage26CohortMember(
        row_id="MIGRATION_MEASUREMENT#0",
        source_row_id="a" * 64,
        measurement_truth_class="MEASURED",
        denominator_status="PRIMARY_MEASURED_DENOMINATOR",
        outcome_eligibility_status="PRIMARY_OUTCOME_ELIGIBLE",
        primary_denominator_reason="MEASURED_TRUTH",
        eligible_for_threshold_calibration=True,
        eligible_for_primary_metrics=True,
        eligible_for_observability_metrics=True,
        source_artifact_kind="MIGRATION_MEASUREMENT",
        stage25_manifest_hash="b" * 64,
        row_status=COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    )


def _sample_summary() -> Stage26CohortSummary:
    return Stage26CohortSummary(
        cohort_key=_sample_key(),
        row_count=1,
        measured_count=1,
        partial_count=0,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=0,
        unsupported_count=0,
        rejected_count=0,
        not_applicable_count=0,
        primary_measured_denominator_count=1,
        observability_denominator_count=0,
        coverage_gap_denominator_count=0,
        scope_gap_denominator_count=0,
        rejection_denominator_count=0,
        threshold_calibration_eligible_count=1,
        primary_metrics_eligible_count=1,
        observability_metrics_eligible_count=1,
        stage25_manifest_hash="b" * 64,
        cohort_status=COHORT_STATUS_VALID_COHORT,
    )


def _empty_eligibility_summary() -> Stage26EligibilitySummary:
    return Stage26EligibilitySummary(
        row_count=0,
        counts_by_denominator_status=(),
        counts_by_outcome_eligibility_status=(),
        counts_by_primary_denominator_reason=(),
        counts_by_calibration_eligibility_kind=(),
        counts_by_measurement_truth_class=(),
        counts_by_source_artifact_kind=(),
    )


def _sample_eligibility_result() -> Stage26EligibilityResult:
    return Stage26EligibilityResult(
        stage26_eligibility_version="stage26_eligibility_v0",
        stage25_manifest_pin=_sample_pin(),
        rows=(),
        summary=_empty_eligibility_summary(),
    )


# ---------------------------------------------------------------------------
# Stage26CohortKey
# ---------------------------------------------------------------------------


def test_key_is_tuple_namedtuple():
    key = _sample_key()
    assert isinstance(key, tuple)
    assert key._fields == ("dimensions", "values")


def test_key_is_immutable():
    key = _sample_key()
    with pytest.raises(AttributeError):
        key.dimensions = ("OTHER",)   # type: ignore[misc]


def test_key_fields_are_tuples_of_strings():
    key = _sample_key()
    assert isinstance(key.dimensions, tuple)
    assert isinstance(key.values, tuple)
    for token in key.dimensions:
        assert isinstance(token, str)
    for value in key.values:
        assert isinstance(value, str)


def test_key_is_structurally_hashable():
    key_a = Stage26CohortKey(
        dimensions=("DENOMINATOR_STATUS",),
        values=("PRIMARY_MEASURED_DENOMINATOR",),
    )
    key_b = Stage26CohortKey(
        dimensions=("DENOMINATOR_STATUS",),
        values=("PRIMARY_MEASURED_DENOMINATOR",),
    )
    assert hash(key_a) == hash(key_b)
    assert key_a == key_b


# ---------------------------------------------------------------------------
# Stage26CohortMember
# ---------------------------------------------------------------------------


def test_member_is_tuple_namedtuple():
    member = _sample_member()
    assert isinstance(member, tuple)
    assert member._fields == (
        "row_id",
        "source_row_id",
        "measurement_truth_class",
        "denominator_status",
        "outcome_eligibility_status",
        "primary_denominator_reason",
        "eligible_for_threshold_calibration",
        "eligible_for_primary_metrics",
        "eligible_for_observability_metrics",
        "source_artifact_kind",
        "stage25_manifest_hash",
        "row_status",
    )


def test_member_is_immutable():
    member = _sample_member()
    with pytest.raises(AttributeError):
        member.measurement_truth_class = "OTHER"   # type: ignore[misc]


def test_member_carries_no_threshold_or_policy_fields():
    member = _sample_member()
    forbidden_fields = {
        "policy_candidate",
        "policy_state",
        "threshold_candidate",
        "threshold_value",
        "approval_state",
        "approved_by",
        "dispatch_target",
        "enforced_at",
    }
    assert forbidden_fields.isdisjoint(set(member._fields))


def test_member_preserves_truth_class_string_verbatim():
    member = _sample_member()._replace(measurement_truth_class="REJECTED")
    assert member.measurement_truth_class == "REJECTED"


# ---------------------------------------------------------------------------
# Stage26CohortSummary
# ---------------------------------------------------------------------------


def test_summary_is_tuple_namedtuple():
    summary = _sample_summary()
    assert isinstance(summary, tuple)
    assert summary._fields == (
        "cohort_key",
        "row_count",
        "measured_count",
        "partial_count",
        "source_conflict_count",
        "ambiguous_count",
        "window_ineligible_count",
        "missing_count",
        "unsupported_count",
        "rejected_count",
        "not_applicable_count",
        "primary_measured_denominator_count",
        "observability_denominator_count",
        "coverage_gap_denominator_count",
        "scope_gap_denominator_count",
        "rejection_denominator_count",
        "threshold_calibration_eligible_count",
        "primary_metrics_eligible_count",
        "observability_metrics_eligible_count",
        "stage25_manifest_hash",
        "cohort_status",
    )


def test_summary_is_immutable():
    summary = _sample_summary()
    with pytest.raises(AttributeError):
        summary.row_count = 0   # type: ignore[misc]


def test_summary_carries_no_threshold_or_policy_fields():
    summary = _sample_summary()
    forbidden_fields = {
        "policy_candidate",
        "policy_state",
        "threshold_candidate",
        "threshold_value",
        "approval_state",
        "approved_by",
        "dispatch_target",
        "enforced_at",
    }
    assert forbidden_fields.isdisjoint(set(summary._fields))


# ---------------------------------------------------------------------------
# Stage26CohortBuildRequest
# ---------------------------------------------------------------------------


def test_request_is_tuple_namedtuple():
    request = Stage26CohortBuildRequest(
        eligibility_result=_sample_eligibility_result(),
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
    )
    assert isinstance(request, tuple)
    assert request._fields == (
        "eligibility_result",
        "dimensions",
    )


def test_request_is_immutable():
    request = Stage26CohortBuildRequest(
        eligibility_result=_sample_eligibility_result(),
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
    )
    with pytest.raises(AttributeError):
        request.dimensions = ()   # type: ignore[misc]


# ---------------------------------------------------------------------------
# Stage26CohortBuildResult
# ---------------------------------------------------------------------------


def _empty_result() -> Stage26CohortBuildResult:
    return Stage26CohortBuildResult(
        stage26_cohort_version=STAGE26_COHORT_VERSION,
        deterministic_ordering_version=(
            STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION
        ),
        stage25_manifest_hash="c" * 64,
        stage25_manifest_pin=_sample_pin(),
        cohort_dimensions=("MEASUREMENT_TRUTH_CLASS",),
        cohort_summaries=(),
        cohort_members=(),
        total_input_rows=0,
        total_cohorted_rows=0,
        total_invalid_rows=0,
    )


def test_result_is_tuple_namedtuple():
    result = _empty_result()
    assert isinstance(result, tuple)
    assert result._fields == (
        "stage26_cohort_version",
        "deterministic_ordering_version",
        "stage25_manifest_hash",
        "stage25_manifest_pin",
        "cohort_dimensions",
        "cohort_summaries",
        "cohort_members",
        "total_input_rows",
        "total_cohorted_rows",
        "total_invalid_rows",
    )


def test_result_is_immutable():
    result = _empty_result()
    with pytest.raises(AttributeError):
        result.total_input_rows = 5   # type: ignore[misc]


def test_result_summaries_and_members_are_parallel_tuples():
    result = _empty_result()
    assert isinstance(result.cohort_summaries, tuple)
    assert isinstance(result.cohort_members, tuple)
    assert len(result.cohort_summaries) == len(result.cohort_members)
