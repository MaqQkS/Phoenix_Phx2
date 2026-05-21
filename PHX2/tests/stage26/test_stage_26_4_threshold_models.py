"""Stage 26.4 threshold-model tests.

Pins the NamedTuple shape, immutability, and field ordering of the
Stage 26.4 threshold candidate records.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.cohort_models import Stage26CohortKey
from PHX2.stage26.threshold_constants import (
    STAGE26_CANDIDATE_GENERATION_VERSION,
    STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_THRESHOLD_VERSION,
    THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT,
    THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
    THRESHOLD_DIRECTION_MINIMUM,
    THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
    THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
)
from PHX2.stage26.threshold_models import (
    Stage26ThresholdCandidate,
    Stage26ThresholdCandidateConfig,
    Stage26ThresholdCandidateSet,
    Stage26ThresholdEvidenceSummary,
)


# ---------------------------------------------------------------------------
# Sample helpers
# ---------------------------------------------------------------------------


_PIN_HASH: str = "c" * 64


def _sample_key() -> Stage26CohortKey:
    return Stage26CohortKey(
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
        values=("MEASURED",),
    )


def _sample_config() -> Stage26ThresholdCandidateConfig:
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


def _sample_evidence_summary() -> Stage26ThresholdEvidenceSummary:
    return Stage26ThresholdEvidenceSummary(
        cohort_key=_sample_key(),
        row_count=5,
        primary_measured_denominator_count=3,
        threshold_calibration_eligible_count=3,
        measured_count=3,
        partial_count=1,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=1,
        unsupported_count=0,
        rejected_count=0,
        coverage_gap_rate=0.2,
        scope_gap_rate=0.0,
        rejection_rate=0.0,
        source_conflict_rate=0.0,
        ambiguous_rate=0.0,
        observability_rate=0.2,
        stage25_manifest_hash=_PIN_HASH,
    )


def _sample_candidate() -> Stage26ThresholdCandidate:
    return Stage26ThresholdCandidate(
        candidate_id="MEASURED#MIN_PRIMARY_MEASURED_COUNT",
        cohort_key=_sample_key(),
        candidate_kind=(
            THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT
        ),
        threshold_direction=THRESHOLD_DIRECTION_MINIMUM,
        threshold_value=1.0,
        observed_value=3.0,
        candidate_status=THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
        evidence_class=(
            THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE
        ),
        review_readiness=(
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
        ),
        reason="sample reason",
        evidence_summary=_sample_evidence_summary(),
        candidate_only=True,
        operator_approved=False,
        runtime_consumable=False,
        stage25_manifest_hash=_PIN_HASH,
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
    )


# ---------------------------------------------------------------------------
# Stage26ThresholdCandidateConfig
# ---------------------------------------------------------------------------


def test_config_is_immutable_namedtuple():
    config = _sample_config()
    assert isinstance(config, tuple)
    with pytest.raises(AttributeError):
        config.min_total_rows = 9  # type: ignore[misc]


def test_config_field_ordering_is_locked():
    config = _sample_config()
    assert config._fields == (
        "min_total_rows",
        "min_primary_measured_count",
        "min_threshold_eligible_count",
        "max_coverage_gap_rate",
        "max_scope_gap_rate",
        "max_rejection_rate",
        "max_source_conflict_rate",
        "max_ambiguous_rate",
        "min_observability_rate",
        "candidate_generation_version",
    )


# ---------------------------------------------------------------------------
# Stage26ThresholdEvidenceSummary
# ---------------------------------------------------------------------------


def test_evidence_summary_is_immutable_namedtuple():
    summary = _sample_evidence_summary()
    assert isinstance(summary, tuple)
    with pytest.raises(AttributeError):
        summary.row_count = 99  # type: ignore[misc]


def test_evidence_summary_field_ordering_is_locked():
    summary = _sample_evidence_summary()
    assert summary._fields == (
        "cohort_key",
        "row_count",
        "primary_measured_denominator_count",
        "threshold_calibration_eligible_count",
        "measured_count",
        "partial_count",
        "source_conflict_count",
        "ambiguous_count",
        "window_ineligible_count",
        "missing_count",
        "unsupported_count",
        "rejected_count",
        "coverage_gap_rate",
        "scope_gap_rate",
        "rejection_rate",
        "source_conflict_rate",
        "ambiguous_rate",
        "observability_rate",
        "stage25_manifest_hash",
    )


# ---------------------------------------------------------------------------
# Stage26ThresholdCandidate
# ---------------------------------------------------------------------------


def test_candidate_is_immutable_namedtuple():
    candidate = _sample_candidate()
    assert isinstance(candidate, tuple)
    with pytest.raises(AttributeError):
        candidate.candidate_status = "X"  # type: ignore[misc]


def test_candidate_field_ordering_is_locked():
    candidate = _sample_candidate()
    assert candidate._fields == (
        "candidate_id",
        "cohort_key",
        "candidate_kind",
        "threshold_direction",
        "threshold_value",
        "observed_value",
        "candidate_status",
        "evidence_class",
        "review_readiness",
        "reason",
        "evidence_summary",
        "candidate_only",
        "operator_approved",
        "runtime_consumable",
        "stage25_manifest_hash",
        "generation_version",
    )


def test_candidate_carries_candidate_only_marks():
    candidate = _sample_candidate()
    assert candidate.candidate_only is True
    assert candidate.operator_approved is False
    assert candidate.runtime_consumable is False


# ---------------------------------------------------------------------------
# Stage26ThresholdCandidateSet
# ---------------------------------------------------------------------------


def test_candidate_set_is_immutable_namedtuple():
    candidate_set = Stage26ThresholdCandidateSet(
        stage26_threshold_version=STAGE26_THRESHOLD_VERSION,
        deterministic_ordering_version=(
            STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
        ),
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
        stage25_manifest_hash=_PIN_HASH,
        config=_sample_config(),
        candidates=(),
        total_candidates=0,
        ready_for_review_count=0,
        insufficient_measured_count=0,
        suppressed_count=0,
        invalid_cohort_count=0,
    )
    assert isinstance(candidate_set, tuple)
    with pytest.raises(AttributeError):
        candidate_set.total_candidates = 99  # type: ignore[misc]


def test_candidate_set_field_ordering_is_locked():
    candidate_set = Stage26ThresholdCandidateSet(
        stage26_threshold_version=STAGE26_THRESHOLD_VERSION,
        deterministic_ordering_version=(
            STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
        ),
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
        stage25_manifest_hash=_PIN_HASH,
        config=_sample_config(),
        candidates=(),
        total_candidates=0,
        ready_for_review_count=0,
        insufficient_measured_count=0,
        suppressed_count=0,
        invalid_cohort_count=0,
    )
    assert candidate_set._fields == (
        "stage26_threshold_version",
        "deterministic_ordering_version",
        "generation_version",
        "stage25_manifest_hash",
        "config",
        "candidates",
        "total_candidates",
        "ready_for_review_count",
        "insufficient_measured_count",
        "suppressed_count",
        "invalid_cohort_count",
    )


# ---------------------------------------------------------------------------
# Hashability + equality
# ---------------------------------------------------------------------------


def test_candidate_is_structurally_hashable():
    candidate = _sample_candidate()
    # NamedTuple of strings + tuples of strings + bools + floats +
    # nested NamedTuples is hashable.
    {candidate}


def test_repeated_construction_with_identical_fields_compares_equal():
    a = _sample_candidate()
    b = _sample_candidate()
    assert a == b
    assert hash(a) == hash(b)
