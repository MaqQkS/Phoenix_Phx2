"""Stage 26.3 cohort-builder tests.

Pins the deterministic behavior of the Stage 26.3 calibration cohort
builder. Tests construct synthetic Stage 26.2 ``Stage26EligibilityRow``
inputs and exercise the builder without touching Stage 25 artifacts
or invoking the Stage 26.1 / 26.2 readers / classifiers.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.cohort_builder import (
    build_cohort_key,
    build_cohort_member,
    build_cohorts,
    summarize_cohort,
)
from PHX2.stage26.cohort_constants import (
    COHORT_BOOL_VALUE_FALSE,
    COHORT_BOOL_VALUE_TRUE,
    COHORT_DIMENSION_DENOMINATOR_STATUS,
    COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS,
    COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY,
    COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS,
    COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON,
    COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY,
    COHORT_DIMENSION_SOURCE_ARTIFACT_KIND,
    COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY,
    COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    COHORT_STATUS_VALID_COHORT,
    STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_COHORT_VERSION,
    STG26_CAL_COHORT_EMPTY_INPUT,
    STG26_CAL_COHORT_MIXED_MANIFEST_HASH,
    STG26_CAL_COHORT_UNKNOWN_DIMENSION,
)
from PHX2.stage26.cohort_models import Stage26CohortKey
from PHX2.stage26.eligibility_classifier import (
    classify_measurement_truth_class,
)
from PHX2.stage26.eligibility_models import (
    Stage26EligibilityResult,
    Stage26EligibilityRow,
    Stage26EligibilitySummary,
)
from PHX2.stage26.errors import Stage26CohortError
from PHX2.stage26.models import Stage25ArtifactReference


# ---------------------------------------------------------------------------
# Synthetic Stage 26.2 row builder (handcrafted -- no Stage 25 reads)
# ---------------------------------------------------------------------------


_PIN_HASH: str = "c" * 64
_ALT_PIN_HASH: str = "d" * 64


def _pin(sha: str = _PIN_HASH) -> Stage25ArtifactReference:
    return Stage25ArtifactReference(
        artifact_basename="stage25_manifest.json",
        artifact_sha256=sha,
    )


def _build_row(
    *,
    row_id: str,
    measurement_truth_class: str,
    source_artifact_kind: str = "MIGRATION_MEASUREMENT",
    source_row_id: str = "0" * 64,
    mint: str = "MintAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    stage25_manifest_hash: str = _PIN_HASH,
) -> Stage26EligibilityRow:
    decision = classify_measurement_truth_class(measurement_truth_class)
    return Stage26EligibilityRow(
        row_id=row_id,
        source_row_id=source_row_id,
        mint=mint,
        measurement_truth_class=measurement_truth_class,
        denominator_status=decision.denominator_status,
        outcome_eligibility_status=decision.outcome_eligibility_status,
        primary_denominator_reason=decision.primary_denominator_reason,
        calibration_eligibility_kind=decision.calibration_eligibility_kind,
        eligible_for_threshold_calibration=(
            decision.eligible_for_threshold_calibration
        ),
        eligible_for_primary_metrics=(
            decision.eligible_for_primary_metrics
        ),
        eligible_for_observability_metrics=(
            decision.eligible_for_observability_metrics
        ),
        source_artifact_kind=source_artifact_kind,
        stage25_manifest_hash=stage25_manifest_hash,
    )


def _empty_summary() -> Stage26EligibilitySummary:
    return Stage26EligibilitySummary(
        row_count=0,
        counts_by_denominator_status=(),
        counts_by_outcome_eligibility_status=(),
        counts_by_primary_denominator_reason=(),
        counts_by_calibration_eligibility_kind=(),
        counts_by_measurement_truth_class=(),
        counts_by_source_artifact_kind=(),
    )


def _build_result(
    rows: tuple[Stage26EligibilityRow, ...],
    pin_sha: str = _PIN_HASH,
) -> Stage26EligibilityResult:
    return Stage26EligibilityResult(
        stage26_eligibility_version="stage26_eligibility_v0",
        stage25_manifest_pin=_pin(pin_sha),
        rows=rows,
        summary=_empty_summary(),
    )


_MIXED_ROWS: tuple[Stage26EligibilityRow, ...] = (
    _build_row(
        row_id="MIGRATION_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
    ),
    _build_row(
        row_id="MIGRATION_MEASUREMENT#1",
        measurement_truth_class="PARTIAL",
    ),
    _build_row(
        row_id="MIGRATION_MEASUREMENT#2",
        measurement_truth_class="MEASURED",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#1",
        measurement_truth_class="SOURCE_CONFLICT",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#2",
        measurement_truth_class="MISSING",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#3",
        measurement_truth_class="REJECTED",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#4",
        measurement_truth_class="UNSUPPORTED",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#5",
        measurement_truth_class="NOT_APPLICABLE",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
    _build_row(
        row_id="ATH_MEASUREMENT#6",
        measurement_truth_class="AMBIGUOUS",
        source_artifact_kind="ATH_MEASUREMENT",
    ),
)


# ---------------------------------------------------------------------------
# Dimension validation
# ---------------------------------------------------------------------------


def test_build_cohort_key_rejects_empty_dimensions():
    row = _build_row(
        row_id="MIGRATION_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
    )
    with pytest.raises(Stage26CohortError) as info:
        build_cohort_key(row, ())
    assert info.value.error_code == STG26_CAL_COHORT_EMPTY_INPUT


def test_build_cohort_key_rejects_unknown_dimension():
    row = _build_row(
        row_id="MIGRATION_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
    )
    with pytest.raises(Stage26CohortError) as info:
        build_cohort_key(row, ("NOT_A_REAL_DIMENSION",))
    assert info.value.error_code == STG26_CAL_COHORT_UNKNOWN_DIMENSION


def test_build_cohorts_rejects_empty_dimensions():
    result = _build_result(_MIXED_ROWS)
    with pytest.raises(Stage26CohortError) as info:
        build_cohorts(result, ())
    assert info.value.error_code == STG26_CAL_COHORT_EMPTY_INPUT


def test_build_cohorts_rejects_unknown_dimension():
    result = _build_result(_MIXED_ROWS)
    with pytest.raises(Stage26CohortError) as info:
        build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS", "OOPS"))
    assert info.value.error_code == STG26_CAL_COHORT_UNKNOWN_DIMENSION


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_build_cohorts_empty_rows_yields_deterministic_empty_result():
    result = _build_result(())
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    assert cohorts.cohort_summaries == ()
    assert cohorts.cohort_members == ()
    assert cohorts.total_input_rows == 0
    assert cohorts.total_cohorted_rows == 0
    assert cohorts.total_invalid_rows == 0
    assert cohorts.stage25_manifest_hash == _PIN_HASH
    assert cohorts.cohort_dimensions == ("MEASUREMENT_TRUTH_CLASS",)


# ---------------------------------------------------------------------------
# build_cohort_member projection
# ---------------------------------------------------------------------------


def test_build_cohort_member_preserves_eligibility_row_fields():
    row = _build_row(
        row_id="MIGRATION_MEASUREMENT#0",
        measurement_truth_class="PARTIAL",
    )
    member = build_cohort_member(row)
    assert member.row_id == row.row_id
    assert member.source_row_id == row.source_row_id
    assert member.measurement_truth_class == row.measurement_truth_class
    assert member.denominator_status == row.denominator_status
    assert (
        member.outcome_eligibility_status
        == row.outcome_eligibility_status
    )
    assert (
        member.primary_denominator_reason
        == row.primary_denominator_reason
    )
    assert (
        member.eligible_for_threshold_calibration
        == row.eligible_for_threshold_calibration
    )
    assert (
        member.eligible_for_primary_metrics
        == row.eligible_for_primary_metrics
    )
    assert (
        member.eligible_for_observability_metrics
        == row.eligible_for_observability_metrics
    )
    assert member.source_artifact_kind == row.source_artifact_kind
    assert member.stage25_manifest_hash == row.stage25_manifest_hash
    assert member.row_status == COHORT_ROW_STATUS_INCLUDED_IN_COHORT


# ---------------------------------------------------------------------------
# Single-dimension grouping
# ---------------------------------------------------------------------------


def test_grouping_by_truth_class_produces_one_cohort_per_class():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    seen_keys = {
        summary.cohort_key.values[0]
        for summary in cohorts.cohort_summaries
    }
    assert seen_keys == {
        "MEASURED",
        "PARTIAL",
        "SOURCE_CONFLICT",
        "AMBIGUOUS",
        "MISSING",
        "REJECTED",
        "UNSUPPORTED",
        "NOT_APPLICABLE",
    }


def test_grouping_by_denominator_status_preserves_eligibility_counts():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("DENOMINATOR_STATUS",))
    by_status: dict[str, int] = {}
    for summary in cohorts.cohort_summaries:
        by_status[summary.cohort_key.values[0]] = summary.row_count
    expected: dict[str, int] = {}
    for row in _MIXED_ROWS:
        expected[row.denominator_status] = (
            expected.get(row.denominator_status, 0) + 1
        )
    assert by_status == expected


def test_grouping_by_outcome_eligibility_status_preserves_counts():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("OUTCOME_ELIGIBILITY_STATUS",))
    by_status: dict[str, int] = {}
    for summary in cohorts.cohort_summaries:
        by_status[summary.cohort_key.values[0]] = summary.row_count
    expected: dict[str, int] = {}
    for row in _MIXED_ROWS:
        expected[row.outcome_eligibility_status] = (
            expected.get(row.outcome_eligibility_status, 0) + 1
        )
    assert by_status == expected


def test_grouping_by_primary_denominator_reason_preserves_counts():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("PRIMARY_DENOMINATOR_REASON",))
    by_reason: dict[str, int] = {}
    for summary in cohorts.cohort_summaries:
        by_reason[summary.cohort_key.values[0]] = summary.row_count
    expected: dict[str, int] = {}
    for row in _MIXED_ROWS:
        expected[row.primary_denominator_reason] = (
            expected.get(row.primary_denominator_reason, 0) + 1
        )
    assert by_reason == expected


# ---------------------------------------------------------------------------
# Multi-dimension grouping + determinism
# ---------------------------------------------------------------------------


def test_multi_dimension_grouping_produces_deterministic_keys():
    result = _build_result(_MIXED_ROWS)
    dimensions = (
        "MEASUREMENT_TRUTH_CLASS",
        "SOURCE_ARTIFACT_KIND",
    )
    cohorts = build_cohorts(result, dimensions)
    # Every emitted key matches the requested dimensions tuple.
    for summary in cohorts.cohort_summaries:
        assert summary.cohort_key.dimensions == dimensions
        assert len(summary.cohort_key.values) == len(dimensions)


def test_cohort_summaries_are_sorted_deterministically_by_key():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(
        result,
        ("MEASUREMENT_TRUTH_CLASS", "SOURCE_ARTIFACT_KIND"),
    )
    values_in_order = [s.cohort_key.values for s in cohorts.cohort_summaries]
    assert values_in_order == sorted(values_in_order)


def test_cohort_members_preserve_input_row_order():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    measured_rows = [
        row
        for row in _MIXED_ROWS
        if row.measurement_truth_class == "MEASURED"
    ]
    measured_summary_index = next(
        i
        for i, summary in enumerate(cohorts.cohort_summaries)
        if summary.cohort_key.values == ("MEASURED",)
    )
    measured_members = cohorts.cohort_members[measured_summary_index]
    assert tuple(m.row_id for m in measured_members) == tuple(
        row.row_id for row in measured_rows
    )


def test_repeated_builds_over_identical_inputs_produce_identical_results():
    result_a = _build_result(_MIXED_ROWS)
    result_b = _build_result(_MIXED_ROWS)
    dimensions = (
        "MEASUREMENT_TRUTH_CLASS",
        "DENOMINATOR_STATUS",
    )
    cohorts_a = build_cohorts(result_a, dimensions)
    cohorts_b = build_cohorts(result_b, dimensions)
    assert cohorts_a == cohorts_b


# ---------------------------------------------------------------------------
# Manifest hash discipline
# ---------------------------------------------------------------------------


def test_mixed_manifest_hash_is_rejected():
    mixed = list(_MIXED_ROWS)
    # Override one row's manifest hash so it disagrees with the
    # bundle's pin.
    mixed[2] = mixed[2]._replace(stage25_manifest_hash=_ALT_PIN_HASH)
    result = _build_result(tuple(mixed))
    with pytest.raises(Stage26CohortError) as info:
        build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    assert info.value.error_code == STG26_CAL_COHORT_MIXED_MANIFEST_HASH


def test_manifest_hash_is_carried_through_result_and_summaries():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    assert cohorts.stage25_manifest_hash == _PIN_HASH
    assert cohorts.stage25_manifest_pin.artifact_sha256 == _PIN_HASH
    for summary in cohorts.cohort_summaries:
        assert summary.stage25_manifest_hash == _PIN_HASH


# ---------------------------------------------------------------------------
# Truth-class preservation
# ---------------------------------------------------------------------------


def test_non_measured_rows_remain_non_threshold_eligible():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    for index, summary in enumerate(cohorts.cohort_summaries):
        truth_class = summary.cohort_key.values[0]
        members = cohorts.cohort_members[index]
        for member in members:
            if truth_class == "MEASURED":
                assert member.eligible_for_threshold_calibration is True
            else:
                assert (
                    member.eligible_for_threshold_calibration is False
                ), (
                    f"non-MEASURED truth class {truth_class!r} must "
                    "NEVER be threshold eligible"
                )


def test_no_non_measured_category_is_labeled_failure():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    for summary in cohorts.cohort_summaries:
        # Every emitted cohort is a VALID_COHORT; Stage 26.3 never
        # labels a non-MEASURED truth class as a failure cohort.
        assert summary.cohort_status == COHORT_STATUS_VALID_COHORT


# ---------------------------------------------------------------------------
# Count discipline
# ---------------------------------------------------------------------------


def test_truth_class_counts_sum_to_row_count():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("SOURCE_ARTIFACT_KIND",))
    for summary in cohorts.cohort_summaries:
        truth_sum = (
            summary.measured_count
            + summary.partial_count
            + summary.source_conflict_count
            + summary.ambiguous_count
            + summary.missing_count
            + summary.unsupported_count
            + summary.rejected_count
            + summary.not_applicable_count
        )
        assert truth_sum == summary.row_count, (
            f"truth-class counts must sum to row_count: "
            f"{truth_sum} != {summary.row_count}"
        )


def test_denominator_status_counts_sum_to_row_count():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("SOURCE_ARTIFACT_KIND",))
    for summary in cohorts.cohort_summaries:
        denom_sum = (
            summary.primary_measured_denominator_count
            + summary.observability_denominator_count
            + summary.coverage_gap_denominator_count
            + summary.scope_gap_denominator_count
            + summary.rejection_denominator_count
        )
        assert denom_sum == summary.row_count, (
            f"denominator-status counts must sum to row_count: "
            f"{denom_sum} != {summary.row_count}"
        )


def test_total_cohorted_rows_equals_input_rows_for_valid_input():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    assert cohorts.total_input_rows == len(_MIXED_ROWS)
    assert cohorts.total_cohorted_rows == len(_MIXED_ROWS)
    assert cohorts.total_invalid_rows == 0


# ---------------------------------------------------------------------------
# Builder must not dedupe or join
# ---------------------------------------------------------------------------


def test_builder_does_not_dedupe_duplicate_source_rows():
    # Two rows with identical source_row_id (would suggest the same
    # Stage 25 row) but distinct Stage 26.2 row_id; the builder MUST
    # keep both in the cohort.
    row_a = _build_row(
        row_id="MIGRATION_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
        source_row_id="dup" + "0" * 61,
    )
    row_b = _build_row(
        row_id="MIGRATION_MEASUREMENT#1",
        measurement_truth_class="MEASURED",
        source_row_id="dup" + "0" * 61,
    )
    result = _build_result((row_a, row_b))
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    assert cohorts.total_cohorted_rows == 2
    members = cohorts.cohort_members[0]
    assert len(members) == 2
    assert {m.row_id for m in members} == {row_a.row_id, row_b.row_id}


def test_builder_does_not_join_rows_by_mint():
    # Two rows for the same mint but with different
    # source_artifact_kind values; grouping by SOURCE_ARTIFACT_KIND
    # must keep them in separate cohorts.
    row_a = _build_row(
        row_id="MIGRATION_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
        mint="MintXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )
    row_b = _build_row(
        row_id="ATH_MEASUREMENT#0",
        measurement_truth_class="MEASURED",
        mint="MintXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        source_artifact_kind="ATH_MEASUREMENT",
    )
    result = _build_result((row_a, row_b))
    cohorts = build_cohorts(result, ("SOURCE_ARTIFACT_KIND",))
    assert len(cohorts.cohort_summaries) == 2
    seen_kinds = {
        summary.cohort_key.values[0]
        for summary in cohorts.cohort_summaries
    }
    assert seen_kinds == {"MIGRATION_MEASUREMENT", "ATH_MEASUREMENT"}


# ---------------------------------------------------------------------------
# Boolean flag dimension encoding
# ---------------------------------------------------------------------------


def test_threshold_eligibility_dimension_encodes_uppercase_bool_tokens():
    rows = (
        _build_row(
            row_id="MIGRATION_MEASUREMENT#0",
            measurement_truth_class="MEASURED",
        ),
        _build_row(
            row_id="MIGRATION_MEASUREMENT#1",
            measurement_truth_class="PARTIAL",
        ),
    )
    result = _build_result(rows)
    cohorts = build_cohorts(
        result,
        ("THRESHOLD_CALIBRATION_ELIGIBILITY",),
    )
    seen_values = {
        summary.cohort_key.values[0]
        for summary in cohorts.cohort_summaries
    }
    assert seen_values == {COHORT_BOOL_VALUE_TRUE, COHORT_BOOL_VALUE_FALSE}


# ---------------------------------------------------------------------------
# Result metadata
# ---------------------------------------------------------------------------


def test_result_carries_version_axes():
    result = _build_result(_MIXED_ROWS)
    cohorts = build_cohorts(result, ("MEASUREMENT_TRUTH_CLASS",))
    assert cohorts.stage26_cohort_version == STAGE26_COHORT_VERSION
    assert (
        cohorts.deterministic_ordering_version
        == STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION
    )


def test_result_carries_requested_dimensions():
    result = _build_result(_MIXED_ROWS)
    dimensions = (
        "MEASUREMENT_TRUTH_CLASS",
        "SOURCE_ARTIFACT_KIND",
    )
    cohorts = build_cohorts(result, dimensions)
    assert cohorts.cohort_dimensions == dimensions


# ---------------------------------------------------------------------------
# summarize_cohort directly
# ---------------------------------------------------------------------------


def test_summarize_cohort_over_empty_member_tuple_is_zero():
    summary = summarize_cohort(
        key=Stage26CohortKey(
            dimensions=("MEASUREMENT_TRUTH_CLASS",),
            values=("MEASURED",),
        ),
        members=(),
        stage25_manifest_hash=_PIN_HASH,
    )
    assert summary.row_count == 0
    assert summary.measured_count == 0
    assert summary.cohort_status == COHORT_STATUS_VALID_COHORT
    assert summary.stage25_manifest_hash == _PIN_HASH


def test_summarize_cohort_keeps_per_truth_class_counts_distinct():
    members = tuple(
        build_cohort_member(_build_row(
            row_id=f"MIGRATION_MEASUREMENT#{index}",
            measurement_truth_class=truth_class,
        ))
        for index, truth_class in enumerate(
            (
                "MEASURED",
                "PARTIAL",
                "SOURCE_CONFLICT",
                "AMBIGUOUS",
                "MISSING",
                "UNSUPPORTED",
                "REJECTED",
                "NOT_APPLICABLE",
            )
        )
    )
    summary = summarize_cohort(
        key=Stage26CohortKey(
            dimensions=("SOURCE_ARTIFACT_KIND",),
            values=("MIGRATION_MEASUREMENT",),
        ),
        members=members,
        stage25_manifest_hash=_PIN_HASH,
    )
    assert summary.measured_count == 1
    assert summary.partial_count == 1
    assert summary.source_conflict_count == 1
    assert summary.ambiguous_count == 1
    assert summary.missing_count == 1
    assert summary.unsupported_count == 1
    assert summary.rejected_count == 1
    assert summary.not_applicable_count == 1
    assert summary.row_count == 8
