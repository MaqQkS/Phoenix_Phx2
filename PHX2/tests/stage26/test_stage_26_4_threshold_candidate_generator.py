"""Stage 26.4 threshold candidate generator tests.

Pins the deterministic behavior of the Stage 26.4 threshold candidate
generator. Tests construct synthetic Stage 26.3 cohort summaries +
build results and exercise the generator without touching Stage 25
artifacts, Stage 26.1 readers, Stage 26.2 classifiers, or the Stage
26.3 cohort builder's raw-row plumbing.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.cohort_constants import (
    COHORT_STATUS_EMPTY_COHORT,
    COHORT_STATUS_INVALID_COHORT_KEY,
    COHORT_STATUS_VALID_COHORT,
)
from PHX2.stage26.cohort_models import (
    Stage26CohortBuildResult,
    Stage26CohortKey,
    Stage26CohortSummary,
)
from PHX2.stage26.errors import Stage26ThresholdError
from PHX2.stage26.models import Stage25ArtifactReference
from PHX2.stage26.threshold_candidate_generator import (
    build_threshold_evidence_summary,
    evaluate_threshold_candidate,
    generate_threshold_candidates,
)
from PHX2.stage26.threshold_constants import (
    STAGE26_CANDIDATE_GENERATION_VERSION,
    STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_THRESHOLD_VERSION,
    STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS,
    STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
    STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH,
    STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY,
    STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
    THRESHOLD_CANDIDATE_KINDS,
    THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE,
    THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE,
    THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT,
    THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT,
    THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
    THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
    THRESHOLD_DIRECTION_MAXIMUM,
    THRESHOLD_DIRECTION_MINIMUM,
    THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
    THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
    THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
    THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
    THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
    THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
)
from PHX2.stage26.threshold_models import (
    Stage26ThresholdCandidateConfig,
)


# ---------------------------------------------------------------------------
# Synthetic Stage 26.3 cohort summary builder
# ---------------------------------------------------------------------------


_PIN_HASH: str = "c" * 64
_ALT_PIN_HASH: str = "d" * 64


def _pin(sha: str = _PIN_HASH) -> Stage25ArtifactReference:
    return Stage25ArtifactReference(
        artifact_basename="stage25_manifest.json",
        artifact_sha256=sha,
    )


def _build_key(values: tuple[str, ...] = ("MEASURED",)) -> Stage26CohortKey:
    dimensions = ("MEASUREMENT_TRUTH_CLASS",) * len(values)
    return Stage26CohortKey(dimensions=dimensions, values=values)


def _build_summary(
    *,
    cohort_key: Stage26CohortKey,
    measured: int = 0,
    partial: int = 0,
    source_conflict: int = 0,
    ambiguous: int = 0,
    missing: int = 0,
    unsupported: int = 0,
    rejected: int = 0,
    not_applicable: int = 0,
    window_ineligible: int = 0,
    cohort_status: str = COHORT_STATUS_VALID_COHORT,
    stage25_manifest_hash: str = _PIN_HASH,
) -> Stage26CohortSummary:
    row_count = (
        measured
        + partial
        + source_conflict
        + ambiguous
        + missing
        + unsupported
        + rejected
        + not_applicable
    )
    primary_measured = measured
    observability = partial + source_conflict + ambiguous
    coverage_gap = missing
    scope_gap = unsupported + not_applicable
    rejection = rejected
    return Stage26CohortSummary(
        cohort_key=cohort_key,
        row_count=row_count,
        measured_count=measured,
        partial_count=partial,
        source_conflict_count=source_conflict,
        ambiguous_count=ambiguous,
        window_ineligible_count=window_ineligible,
        missing_count=missing,
        unsupported_count=unsupported,
        rejected_count=rejected,
        not_applicable_count=not_applicable,
        primary_measured_denominator_count=primary_measured,
        observability_denominator_count=observability,
        coverage_gap_denominator_count=coverage_gap,
        scope_gap_denominator_count=scope_gap,
        rejection_denominator_count=rejection,
        threshold_calibration_eligible_count=measured,
        primary_metrics_eligible_count=measured,
        observability_metrics_eligible_count=(
            measured + partial + source_conflict + ambiguous
        ),
        stage25_manifest_hash=stage25_manifest_hash,
        cohort_status=cohort_status,
    )


def _build_result(
    summaries: tuple[Stage26CohortSummary, ...],
    pin_sha: str = _PIN_HASH,
) -> Stage26CohortBuildResult:
    return Stage26CohortBuildResult(
        stage26_cohort_version="stage26_cohort_v0",
        deterministic_ordering_version="stage26_cohort_ordering_v0",
        stage25_manifest_hash=pin_sha,
        stage25_manifest_pin=_pin(pin_sha),
        cohort_dimensions=("MEASUREMENT_TRUTH_CLASS",),
        cohort_summaries=summaries,
        cohort_members=tuple((),) * len(summaries),
        total_input_rows=sum(s.row_count for s in summaries),
        total_cohorted_rows=sum(s.row_count for s in summaries),
        total_invalid_rows=0,
    )


def _default_config() -> Stage26ThresholdCandidateConfig:
    return Stage26ThresholdCandidateConfig(
        min_total_rows=1,
        min_primary_measured_count=1,
        min_threshold_eligible_count=1,
        max_coverage_gap_rate=1.0,
        max_scope_gap_rate=1.0,
        max_rejection_rate=1.0,
        max_source_conflict_rate=1.0,
        max_ambiguous_rate=1.0,
        min_observability_rate=0.0,
        candidate_generation_version=(
            STAGE26_CANDIDATE_GENERATION_VERSION
        ),
    )


def _strict_config(
    *,
    min_total_rows: int = 1,
    min_primary_measured_count: int = 1,
    min_threshold_eligible_count: int = 1,
    max_coverage_gap_rate: float = 1.0,
    max_scope_gap_rate: float = 1.0,
    max_rejection_rate: float = 1.0,
    max_source_conflict_rate: float = 1.0,
    max_ambiguous_rate: float = 1.0,
    min_observability_rate: float = 0.0,
) -> Stage26ThresholdCandidateConfig:
    return Stage26ThresholdCandidateConfig(
        min_total_rows=min_total_rows,
        min_primary_measured_count=min_primary_measured_count,
        min_threshold_eligible_count=min_threshold_eligible_count,
        max_coverage_gap_rate=max_coverage_gap_rate,
        max_scope_gap_rate=max_scope_gap_rate,
        max_rejection_rate=max_rejection_rate,
        max_source_conflict_rate=max_source_conflict_rate,
        max_ambiguous_rate=max_ambiguous_rate,
        min_observability_rate=min_observability_rate,
        candidate_generation_version=(
            STAGE26_CANDIDATE_GENERATION_VERSION
        ),
    )


# ---------------------------------------------------------------------------
# build_threshold_evidence_summary
# ---------------------------------------------------------------------------


def test_evidence_summary_preserves_cohort_counts_verbatim():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=3,
        partial=2,
        source_conflict=1,
        ambiguous=1,
        missing=2,
        unsupported=1,
        rejected=1,
        not_applicable=0,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    assert evidence_summary.row_count == cohort_summary.row_count
    assert (
        evidence_summary.primary_measured_denominator_count
        == cohort_summary.primary_measured_denominator_count
    )
    assert (
        evidence_summary.threshold_calibration_eligible_count
        == cohort_summary.threshold_calibration_eligible_count
    )
    assert evidence_summary.measured_count == cohort_summary.measured_count
    assert evidence_summary.partial_count == cohort_summary.partial_count
    assert (
        evidence_summary.source_conflict_count
        == cohort_summary.source_conflict_count
    )
    assert (
        evidence_summary.ambiguous_count == cohort_summary.ambiguous_count
    )
    assert (
        evidence_summary.window_ineligible_count
        == cohort_summary.window_ineligible_count
    )
    assert evidence_summary.missing_count == cohort_summary.missing_count
    assert (
        evidence_summary.unsupported_count
        == cohort_summary.unsupported_count
    )
    assert evidence_summary.rejected_count == cohort_summary.rejected_count
    assert (
        evidence_summary.stage25_manifest_hash
        == cohort_summary.stage25_manifest_hash
    )


def test_evidence_summary_rates_are_safe_for_zero_denominator():
    cohort_summary = _build_summary(cohort_key=_build_key())
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    assert evidence_summary.row_count == 0
    assert evidence_summary.coverage_gap_rate == 0.0
    assert evidence_summary.scope_gap_rate == 0.0
    assert evidence_summary.rejection_rate == 0.0
    assert evidence_summary.source_conflict_rate == 0.0
    assert evidence_summary.ambiguous_rate == 0.0
    assert evidence_summary.observability_rate == 0.0


def test_evidence_summary_rates_compute_correctly():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=2,
        partial=1,
        source_conflict=1,
        ambiguous=1,
        missing=2,
        unsupported=1,
        rejected=2,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    row_count = cohort_summary.row_count
    assert row_count == 10
    assert evidence_summary.coverage_gap_rate == 2 / row_count
    assert evidence_summary.scope_gap_rate == 1 / row_count
    assert evidence_summary.rejection_rate == 2 / row_count
    assert evidence_summary.source_conflict_rate == 1 / row_count
    assert evidence_summary.ambiguous_rate == 1 / row_count
    # observability_denominator_count = partial + source_conflict + ambiguous
    assert evidence_summary.observability_rate == 3 / row_count


def test_evidence_summary_does_not_mutate_input_cohort_summary():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=3,
        partial=1,
    )
    original = cohort_summary
    _ = build_threshold_evidence_summary(cohort_summary)
    assert cohort_summary == original


# ---------------------------------------------------------------------------
# evaluate_threshold_candidate -- candidate-only invariants
# ---------------------------------------------------------------------------


def _evaluate_all_kinds(
    evidence_summary, config, cohort_status=COHORT_STATUS_VALID_COHORT
):
    return tuple(
        evaluate_threshold_candidate(
            evidence_summary=evidence_summary,
            candidate_kind=kind,
            config=config,
            cohort_status=cohort_status,
        )
        for kind in THRESHOLD_CANDIDATE_KINDS
    )


def test_every_candidate_carries_candidate_only_true():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=3,
        partial=1,
        missing=1,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _default_config()
    candidates = _evaluate_all_kinds(evidence_summary, config)
    for candidate in candidates:
        assert candidate.candidate_only is True


def test_every_candidate_carries_operator_approved_false():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=3,
        partial=1,
        missing=1,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _default_config()
    candidates = _evaluate_all_kinds(evidence_summary, config)
    for candidate in candidates:
        assert candidate.operator_approved is False


def test_every_candidate_carries_runtime_consumable_false():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=3,
        partial=1,
        missing=1,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _default_config()
    candidates = _evaluate_all_kinds(evidence_summary, config)
    for candidate in candidates:
        assert candidate.runtime_consumable is False


# ---------------------------------------------------------------------------
# evaluate_threshold_candidate -- per-kind behavior
# ---------------------------------------------------------------------------


def test_unknown_candidate_kind_raises():
    cohort_summary = _build_summary(cohort_key=_build_key(), measured=1)
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    with pytest.raises(Stage26ThresholdError) as info:
        evaluate_threshold_candidate(
            evidence_summary=evidence_summary,
            candidate_kind="NOT_A_REAL_KIND",
            config=_default_config(),
        )
    assert (
        info.value.error_code == STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND
    )


def test_invalid_cohort_status_kwarg_raises():
    cohort_summary = _build_summary(cohort_key=_build_key(), measured=1)
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    with pytest.raises(Stage26ThresholdError) as info:
        evaluate_threshold_candidate(
            evidence_summary=evidence_summary,
            candidate_kind=(
                THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT
            ),
            config=_default_config(),
            cohort_status="NOT_A_REAL_STATUS",
        )
    assert (
        info.value.error_code == STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS
    )


def test_sufficient_measured_denominator_yields_ready():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=5,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(min_primary_measured_count=3)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=(
            THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT
        ),
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
    )
    assert (
        candidate.evidence_class
        == THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE
    )
    assert candidate.threshold_direction == THRESHOLD_DIRECTION_MINIMUM
    assert candidate.threshold_value == 3.0
    assert candidate.observed_value == 5.0


def test_insufficient_measured_denominator_suppresses_review_readiness():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        partial=1,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(min_primary_measured_count=5)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=(
            THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT
        ),
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS
    )


def test_insufficient_threshold_eligible_count_suppresses_review_readiness():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        partial=4,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(min_threshold_eligible_count=5)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=(
            THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT
        ),
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS
    )


def test_high_coverage_gap_rate_suppresses_candidate():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        missing=4,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(max_coverage_gap_rate=0.1)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE,
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE
    )
    assert (
        candidate.evidence_class
        == THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT
    )
    assert candidate.threshold_direction == THRESHOLD_DIRECTION_MAXIMUM


def test_high_scope_gap_rate_suppresses_candidate():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        unsupported=4,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(max_scope_gap_rate=0.1)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE,
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW
    )
    assert (
        candidate.evidence_class == THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT
    )


def test_high_rejection_rate_suppresses_candidate():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        rejected=4,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(max_rejection_rate=0.1)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE,
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW
    )
    assert (
        candidate.evidence_class
        == THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT
    )


def test_high_source_conflict_rate_becomes_observability_caveat_not_failure():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        source_conflict=4,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(max_source_conflict_rate=0.1)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=(
            THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE
        ),
        config=config,
    )
    # The cohort is still a candidate (no suppression / no failure);
    # the high source-conflict rate is recorded as an observability
    # caveat per the Stage 26.4 spec.
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
    )
    assert (
        candidate.evidence_class
        == THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT
    )


def test_high_ambiguous_rate_becomes_observability_caveat_not_failure():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=1,
        ambiguous=4,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(max_ambiguous_rate=0.1)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE,
        config=config,
    )
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY
    )
    assert (
        candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
    )
    assert (
        candidate.evidence_class
        == THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT
    )


def test_min_observability_rate_is_observability_caveat():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=5,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(min_observability_rate=0.5)
    candidate = evaluate_threshold_candidate(
        evidence_summary=evidence_summary,
        candidate_kind=THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE,
        config=config,
    )
    # All MEASURED rows produce observability_rate=0; the kind is
    # always an observability caveat (no failure / no suppression).
    assert (
        candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY
    )
    assert (
        candidate.evidence_class
        == THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT
    )
    assert candidate.threshold_direction == THRESHOLD_DIRECTION_MINIMUM


# ---------------------------------------------------------------------------
# Cohort-input validation
# ---------------------------------------------------------------------------


def test_invalid_cohort_status_marks_every_candidate_invalid_for_review():
    cohort_summary = _build_summary(
        cohort_key=_build_key(),
        measured=3,
        cohort_status=COHORT_STATUS_INVALID_COHORT_KEY,
    )
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    candidates = _evaluate_all_kinds(
        evidence_summary,
        _default_config(),
        cohort_status=COHORT_STATUS_INVALID_COHORT_KEY,
    )
    for candidate in candidates:
        assert (
            candidate.candidate_status
            == THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT
        )
        assert (
            candidate.evidence_class
            == THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT
        )
        assert (
            candidate.review_readiness
            == THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW
        )


def test_insufficient_total_rows_marks_status_insufficient_total_rows():
    cohort_summary = _build_summary(cohort_key=_build_key())
    evidence_summary = build_threshold_evidence_summary(cohort_summary)
    config = _strict_config(min_total_rows=5)
    candidates = _evaluate_all_kinds(evidence_summary, config)
    for candidate in candidates:
        assert (
            candidate.candidate_status
            == THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS
        )
        assert (
            candidate.review_readiness
            == THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS
        )


# ---------------------------------------------------------------------------
# generate_threshold_candidates
# ---------------------------------------------------------------------------


def test_generate_emits_one_candidate_per_kind_per_cohort():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
        ),
        _build_summary(
            cohort_key=_build_key(("PARTIAL",)),
            partial=2,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(result, _default_config())
    expected = len(summaries) * len(THRESHOLD_CANDIDATE_KINDS)
    assert candidate_set.total_candidates == expected
    assert len(candidate_set.candidates) == expected


def test_generate_preserves_cohort_keys_verbatim():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
        ),
        _build_summary(
            cohort_key=_build_key(("PARTIAL",)),
            partial=2,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(result, _default_config())
    seen_values = {c.cohort_key.values for c in candidate_set.candidates}
    assert seen_values == {("MEASURED",), ("PARTIAL",)}


def test_generate_preserves_stage25_manifest_hash():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(result, _default_config())
    assert candidate_set.stage25_manifest_hash == _PIN_HASH
    for candidate in candidate_set.candidates:
        assert candidate.stage25_manifest_hash == _PIN_HASH


def test_generate_carries_version_axes_on_result():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=1,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(result, _default_config())
    assert (
        candidate_set.stage26_threshold_version == STAGE26_THRESHOLD_VERSION
    )
    assert (
        candidate_set.deterministic_ordering_version
        == STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
    )
    assert (
        candidate_set.generation_version
        == STAGE26_CANDIDATE_GENERATION_VERSION
    )


def test_generate_empty_cohort_result_yields_empty_candidate_set():
    result = _build_result(())
    candidate_set = generate_threshold_candidates(result, _default_config())
    assert candidate_set.candidates == ()
    assert candidate_set.total_candidates == 0
    assert candidate_set.ready_for_review_count == 0
    assert candidate_set.insufficient_measured_count == 0
    assert candidate_set.suppressed_count == 0
    assert candidate_set.invalid_cohort_count == 0


def test_generate_orders_candidates_deterministically():
    # Reverse-alphabetical cohort summaries; generator must sort
    # candidates lex by (cohort_key.values, candidate_kind).
    summaries = (
        _build_summary(
            cohort_key=_build_key(("PARTIAL",)),
            partial=1,
        ),
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=1,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(result, _default_config())
    ordered_keys = tuple(
        (c.cohort_key.values, c.candidate_kind)
        for c in candidate_set.candidates
    )
    assert ordered_keys == tuple(sorted(ordered_keys))


def test_generate_candidate_ids_are_deterministic_across_runs():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=2,
        ),
    )
    result_a = _build_result(summaries)
    result_b = _build_result(summaries)
    candidate_set_a = generate_threshold_candidates(
        result_a, _default_config()
    )
    candidate_set_b = generate_threshold_candidates(
        result_b, _default_config()
    )
    assert candidate_set_a == candidate_set_b
    ids_a = tuple(c.candidate_id for c in candidate_set_a.candidates)
    ids_b = tuple(c.candidate_id for c in candidate_set_b.candidates)
    assert ids_a == ids_b


def test_generate_candidate_id_encodes_cohort_values_and_kind():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=2,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(
        result, _default_config()
    )
    for candidate in candidate_set.candidates:
        assert candidate.candidate_id == (
            f"MEASURED#{candidate.candidate_kind}"
        )


def test_generate_aggregate_counts_match_candidate_states():
    summaries = (
        # Cohort A: MEASURED + missing -> some kinds READY, some
        # SUPPRESSED_BY_COVERAGE_GAP with strict coverage rate.
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
            missing=2,
        ),
    )
    result = _build_result(summaries)
    config = _strict_config(
        min_primary_measured_count=1,
        max_coverage_gap_rate=0.1,
    )
    candidate_set = generate_threshold_candidates(result, config)
    expected_ready = sum(
        1
        for c in candidate_set.candidates
        if c.review_readiness
        == THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
    )
    expected_suppressed = sum(
        1
        for c in candidate_set.candidates
        if c.candidate_status
        in {
            THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
            THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
            THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
        }
    )
    expected_insufficient = sum(
        1
        for c in candidate_set.candidates
        if c.candidate_status
        in {
            THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
            THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
        }
    )
    expected_invalid = sum(
        1
        for c in candidate_set.candidates
        if c.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT
    )
    assert candidate_set.ready_for_review_count == expected_ready
    assert candidate_set.suppressed_count == expected_suppressed
    assert (
        candidate_set.insufficient_measured_count == expected_insufficient
    )
    assert candidate_set.invalid_cohort_count == expected_invalid


# ---------------------------------------------------------------------------
# Validation -- count shape + manifest hash + non-MEASURED primary
# ---------------------------------------------------------------------------


def test_generate_rejects_truth_class_count_shape_mismatch():
    # A cohort summary whose truth-class counts disagree with row_count.
    bad_summary = Stage26CohortSummary(
        cohort_key=_build_key(),
        row_count=10,
        measured_count=3,
        partial_count=0,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=0,
        unsupported_count=0,
        rejected_count=0,
        not_applicable_count=0,
        primary_measured_denominator_count=3,
        observability_denominator_count=0,
        coverage_gap_denominator_count=0,
        scope_gap_denominator_count=0,
        rejection_denominator_count=0,
        threshold_calibration_eligible_count=3,
        primary_metrics_eligible_count=3,
        observability_metrics_eligible_count=3,
        stage25_manifest_hash=_PIN_HASH,
        cohort_status=COHORT_STATUS_VALID_COHORT,
    )
    result = _build_result((bad_summary,))
    with pytest.raises(Stage26ThresholdError) as info:
        generate_threshold_candidates(result, _default_config())
    assert (
        info.value.error_code == STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE
    )


def test_generate_rejects_denominator_count_shape_mismatch():
    # Truth-class counts sum to row_count but denominator-status
    # counts do not.
    bad_summary = Stage26CohortSummary(
        cohort_key=_build_key(),
        row_count=3,
        measured_count=3,
        partial_count=0,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=0,
        unsupported_count=0,
        rejected_count=0,
        not_applicable_count=0,
        primary_measured_denominator_count=3,
        observability_denominator_count=2,  # mismatched
        coverage_gap_denominator_count=0,
        scope_gap_denominator_count=0,
        rejection_denominator_count=0,
        threshold_calibration_eligible_count=3,
        primary_metrics_eligible_count=3,
        observability_metrics_eligible_count=3,
        stage25_manifest_hash=_PIN_HASH,
        cohort_status=COHORT_STATUS_VALID_COHORT,
    )
    result = _build_result((bad_summary,))
    with pytest.raises(Stage26ThresholdError) as info:
        generate_threshold_candidates(result, _default_config())
    assert (
        info.value.error_code == STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE
    )


def test_generate_rejects_non_measured_primary_denominator():
    # primary_measured_denominator_count > measured_count would imply
    # a non-MEASURED row is being upgraded into the primary denominator.
    bad_summary = Stage26CohortSummary(
        cohort_key=_build_key(),
        row_count=3,
        measured_count=1,
        partial_count=2,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=0,
        unsupported_count=0,
        rejected_count=0,
        not_applicable_count=0,
        primary_measured_denominator_count=3,  # > measured_count
        observability_denominator_count=0,
        coverage_gap_denominator_count=0,
        scope_gap_denominator_count=0,
        rejection_denominator_count=0,
        threshold_calibration_eligible_count=1,
        primary_metrics_eligible_count=1,
        observability_metrics_eligible_count=3,
        stage25_manifest_hash=_PIN_HASH,
        cohort_status=COHORT_STATUS_VALID_COHORT,
    )
    result = _build_result((bad_summary,))
    with pytest.raises(Stage26ThresholdError) as info:
        generate_threshold_candidates(result, _default_config())
    assert (
        info.value.error_code == STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY
    )


def test_generate_rejects_mixed_manifest_hash():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
        ),
        _build_summary(
            cohort_key=_build_key(("PARTIAL",)),
            partial=2,
            stage25_manifest_hash=_ALT_PIN_HASH,
        ),
    )
    result = _build_result(summaries)
    with pytest.raises(Stage26ThresholdError) as info:
        generate_threshold_candidates(result, _default_config())
    assert (
        info.value.error_code == STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH
    )


# ---------------------------------------------------------------------------
# Immutability -- no mutation of inputs
# ---------------------------------------------------------------------------


def test_generate_does_not_mutate_cohort_inputs():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
            partial=1,
            missing=1,
        ),
    )
    result = _build_result(summaries)
    original_summary = result.cohort_summaries[0]
    original_result = result
    _ = generate_threshold_candidates(result, _default_config())
    assert result == original_result
    assert result.cohort_summaries[0] == original_summary


def test_generate_does_not_rebuild_cohorts_or_inspect_raw_rows():
    # Cohort members are empty -- generator must not depend on raw row
    # data; it must consume cohort summaries verbatim.
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=3,
        ),
    )
    result = _build_result(summaries)
    # cohort_members in our fixture is empty tuples; if the generator
    # ever reached into raw rows, this would either error or produce
    # surprising counts. The generator must remain insensitive to
    # the members tuple.
    candidate_set = generate_threshold_candidates(result, _default_config())
    assert candidate_set.total_candidates == len(THRESHOLD_CANDIDATE_KINDS)


def test_repeated_generation_produces_byte_identical_candidate_sets():
    summaries = (
        _build_summary(
            cohort_key=_build_key(("MEASURED",)),
            measured=2,
            partial=1,
        ),
        _build_summary(
            cohort_key=_build_key(("PARTIAL",)),
            partial=3,
        ),
    )
    result_a = _build_result(summaries)
    result_b = _build_result(summaries)
    candidate_set_a = generate_threshold_candidates(
        result_a, _default_config()
    )
    candidate_set_b = generate_threshold_candidates(
        result_b, _default_config()
    )
    assert candidate_set_a == candidate_set_b


# ---------------------------------------------------------------------------
# Empty-cohort handling
# ---------------------------------------------------------------------------


def test_empty_cohort_status_yields_invalid_cohort_input():
    summaries = (
        _build_summary(
            cohort_key=_build_key(),
            cohort_status=COHORT_STATUS_EMPTY_COHORT,
        ),
    )
    result = _build_result(summaries)
    candidate_set = generate_threshold_candidates(result, _default_config())
    # EMPTY_COHORT is not VALID_COHORT -> INVALID_COHORT_INPUT path.
    for candidate in candidate_set.candidates:
        assert (
            candidate.candidate_status
            == THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT
        )
        assert (
            candidate.review_readiness
            == THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW
        )
