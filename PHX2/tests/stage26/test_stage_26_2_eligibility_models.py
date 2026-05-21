"""Stage 26.2 eligibility-model tests.

Pins the NamedTuple shape, immutability, and field ordering of the
Stage 26.2 eligibility records.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.eligibility_models import (
    Stage26EligibilityDecision,
    Stage26EligibilityResult,
    Stage26EligibilityRow,
    Stage26EligibilitySummary,
)
from PHX2.stage26.models import Stage25ArtifactReference


# ---------------------------------------------------------------------------
# Stage26EligibilityDecision
# ---------------------------------------------------------------------------


def _sample_decision() -> Stage26EligibilityDecision:
    return Stage26EligibilityDecision(
        denominator_status="PRIMARY_MEASURED_DENOMINATOR",
        outcome_eligibility_status="PRIMARY_OUTCOME_ELIGIBLE",
        primary_denominator_reason="MEASURED_TRUTH",
        calibration_eligibility_kind="THRESHOLD_CALIBRATION_ELIGIBLE",
        eligible_for_threshold_calibration=True,
        eligible_for_primary_metrics=True,
        eligible_for_observability_metrics=True,
    )


def test_decision_is_tuple_namedtuple():
    decision = _sample_decision()
    assert isinstance(decision, tuple)
    assert decision._fields == (
        "denominator_status",
        "outcome_eligibility_status",
        "primary_denominator_reason",
        "calibration_eligibility_kind",
        "eligible_for_threshold_calibration",
        "eligible_for_primary_metrics",
        "eligible_for_observability_metrics",
    )


def test_decision_is_immutable():
    decision = _sample_decision()
    with pytest.raises(AttributeError):
        decision.denominator_status = "OTHER"   # type: ignore[misc]


def test_decision_carries_no_policy_or_threshold_fields():
    decision = _sample_decision()
    forbidden_fields = {
        "policy_candidate",
        "policy_state",
        "threshold_candidate",
        "threshold_value",
        "approval_state",
        "approved_by",
        "cohort_id",
        "dispatch_target",
        "enforced_at",
    }
    assert forbidden_fields.isdisjoint(set(decision._fields))


# ---------------------------------------------------------------------------
# Stage26EligibilityRow
# ---------------------------------------------------------------------------


def _sample_row() -> Stage26EligibilityRow:
    return Stage26EligibilityRow(
        row_id="MIGRATION_MEASUREMENT#0",
        source_row_id="a" * 64,
        mint="MintAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        measurement_truth_class="MEASURED",
        denominator_status="PRIMARY_MEASURED_DENOMINATOR",
        outcome_eligibility_status="PRIMARY_OUTCOME_ELIGIBLE",
        primary_denominator_reason="MEASURED_TRUTH",
        calibration_eligibility_kind="THRESHOLD_CALIBRATION_ELIGIBLE",
        eligible_for_threshold_calibration=True,
        eligible_for_primary_metrics=True,
        eligible_for_observability_metrics=True,
        source_artifact_kind="MIGRATION_MEASUREMENT",
        stage25_manifest_hash="b" * 64,
    )


def test_row_is_tuple_namedtuple():
    row = _sample_row()
    assert isinstance(row, tuple)
    assert row._fields == (
        "row_id",
        "source_row_id",
        "mint",
        "measurement_truth_class",
        "denominator_status",
        "outcome_eligibility_status",
        "primary_denominator_reason",
        "calibration_eligibility_kind",
        "eligible_for_threshold_calibration",
        "eligible_for_primary_metrics",
        "eligible_for_observability_metrics",
        "source_artifact_kind",
        "stage25_manifest_hash",
    )


def test_row_is_immutable():
    row = _sample_row()
    with pytest.raises(AttributeError):
        row.denominator_status = "OTHER"   # type: ignore[misc]


def test_row_carries_no_policy_or_threshold_fields():
    row = _sample_row()
    forbidden_fields = {
        "policy_candidate",
        "policy_state",
        "threshold_candidate",
        "threshold_value",
        "approval_state",
        "approved_by",
        "cohort_id",
        "dispatch_target",
        "enforced_at",
    }
    assert forbidden_fields.isdisjoint(set(row._fields))


def test_row_preserves_truth_class_string_verbatim():
    row = _sample_row()._replace(measurement_truth_class="REJECTED")
    assert row.measurement_truth_class == "REJECTED"


# ---------------------------------------------------------------------------
# Stage26EligibilitySummary
# ---------------------------------------------------------------------------


def _sample_summary() -> Stage26EligibilitySummary:
    return Stage26EligibilitySummary(
        row_count=0,
        counts_by_denominator_status=(),
        counts_by_outcome_eligibility_status=(),
        counts_by_primary_denominator_reason=(),
        counts_by_calibration_eligibility_kind=(),
        counts_by_measurement_truth_class=(),
        counts_by_source_artifact_kind=(),
    )


def test_summary_is_tuple_namedtuple():
    summary = _sample_summary()
    assert isinstance(summary, tuple)
    assert summary._fields == (
        "row_count",
        "counts_by_denominator_status",
        "counts_by_outcome_eligibility_status",
        "counts_by_primary_denominator_reason",
        "counts_by_calibration_eligibility_kind",
        "counts_by_measurement_truth_class",
        "counts_by_source_artifact_kind",
    )


def test_summary_count_maps_are_tuples_of_pairs():
    summary = Stage26EligibilitySummary(
        row_count=1,
        counts_by_denominator_status=(("A", 1), ("B", 0)),
        counts_by_outcome_eligibility_status=(("C", 1),),
        counts_by_primary_denominator_reason=(("D", 1),),
        counts_by_calibration_eligibility_kind=(("E", 1),),
        counts_by_measurement_truth_class=(("F", 1),),
        counts_by_source_artifact_kind=(("G", 1),),
    )
    assert isinstance(summary.counts_by_denominator_status, tuple)
    for pair in summary.counts_by_denominator_status:
        assert isinstance(pair, tuple)
        assert len(pair) == 2
        assert isinstance(pair[0], str)
        assert isinstance(pair[1], int)


# ---------------------------------------------------------------------------
# Stage26EligibilityResult
# ---------------------------------------------------------------------------


def _sample_pin() -> Stage25ArtifactReference:
    return Stage25ArtifactReference(
        artifact_basename="stage25_manifest.json",
        artifact_sha256="c" * 64,
    )


def test_result_is_tuple_namedtuple():
    result = Stage26EligibilityResult(
        stage26_eligibility_version="stage26_eligibility_v0",
        stage25_manifest_pin=_sample_pin(),
        rows=(),
        summary=_sample_summary(),
    )
    assert isinstance(result, tuple)
    assert result._fields == (
        "stage26_eligibility_version",
        "stage25_manifest_pin",
        "rows",
        "summary",
    )


def test_result_rows_field_is_tuple_of_rows():
    row = _sample_row()
    result = Stage26EligibilityResult(
        stage26_eligibility_version="stage26_eligibility_v0",
        stage25_manifest_pin=_sample_pin(),
        rows=(row,),
        summary=_sample_summary(),
    )
    assert isinstance(result.rows, tuple)
    assert result.rows[0] is row
