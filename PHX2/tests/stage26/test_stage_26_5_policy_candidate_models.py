"""Stage 26.5 policy candidate model immutability + shape tests."""

from __future__ import annotations

import pytest

from PHX2.stage26 import policy_candidate_constants as c
from PHX2.stage26.policy_candidate_models import (
    Stage26PolicyCandidate,
    Stage26PolicyCandidateArtifactReference,
    Stage26PolicyCandidateArtifactSet,
    Stage26PolicyCandidateBuildResult,
    Stage26PolicyCandidateConfig,
    Stage26PolicyCandidateSummary,
    preserve_threshold_evidence,
)


def _make_config() -> Stage26PolicyCandidateConfig:
    return Stage26PolicyCandidateConfig(
        min_ready_threshold_candidates=0,
        include_non_ready_candidates=True,
        artifact_schema_version=c.STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION,
        candidate_generation_version=c.STAGE26_POLICY_CANDIDATE_VERSION,
        deterministic_ordering_version=(
            c.STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION
        ),
    )


def _make_candidate(
    *,
    candidate_kind: str = c.POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE,
    candidate_status: str = c.POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE,
    readiness: str = c.POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
) -> Stage26PolicyCandidate:
    return Stage26PolicyCandidate(
        policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#x|y#MIN",
        candidate_kind=candidate_kind,
        candidate_status=candidate_status,
        readiness=readiness,
        source_threshold_candidate_id="x|y#MIN",
        source_threshold_candidate_kind="MIN_PRIMARY_MEASURED_COUNT",
        cohort_key_dimensions=("MEASUREMENT_TRUTH_CLASS",),
        cohort_key_values=("MEASURED",),
        threshold_direction="MINIMUM",
        threshold_value=1.0,
        observed_value=2.0,
        evidence_class="PRIMARY_MEASURED_EVIDENCE",
        source_threshold_candidate_status="CANDIDATE_ONLY",
        source_threshold_review_readiness=(
            "READY_FOR_POLICY_CANDIDATE_REVIEW"
        ),
        primary_measured_denominator_count=2,
        threshold_calibration_eligible_count=2,
        row_count=4,
        coverage_gap_rate=0.0,
        scope_gap_rate=0.0,
        rejection_rate=0.0,
        source_conflict_rate=0.0,
        ambiguous_rate=0.0,
        observability_rate=1.0,
        reason="synthetic",
        candidate_only=True,
        observe_only=True,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
        stage25_manifest_hash="abc123",
        stage26_threshold_generation_version=(
            "stage26_threshold_generation_v0"
        ),
        stage26_policy_candidate_version=(
            c.STAGE26_POLICY_CANDIDATE_VERSION
        ),
    )


def test_config_is_named_tuple_immutable():
    config = _make_config()
    assert isinstance(config, tuple)
    with pytest.raises(AttributeError):
        config.min_ready_threshold_candidates = 99  # type: ignore[misc]


def test_policy_candidate_is_named_tuple_immutable():
    candidate = _make_candidate()
    assert isinstance(candidate, tuple)
    with pytest.raises(AttributeError):
        candidate.operator_approved = True  # type: ignore[misc]


def test_summary_is_named_tuple_immutable():
    summary = Stage26PolicyCandidateSummary(
        stage25_manifest_hash="abc",
        total_policy_candidates=0,
        ready_for_operator_review_count=0,
        needs_more_measured_rows_count=0,
        needs_better_coverage_count=0,
        needs_scope_review_count=0,
        needs_rejection_review_count=0,
        invalid_for_operator_review_count=0,
        observe_only_candidate_count=0,
        blocked_insufficient_evidence_count=0,
        blocked_invalid_threshold_count=0,
        blocked_policy_leak_count=0,
        blocked_runtime_consumable_count=0,
        blocked_approval_leak_count=0,
        threshold_policy_candidate_kind_count=0,
        coverage_caveat_policy_candidate_kind_count=0,
        observability_caveat_policy_candidate_kind_count=0,
        rejection_caveat_policy_candidate_kind_count=0,
        candidate_only_true_count=0,
        observe_only_true_count=0,
        operator_approved_false_count=0,
        runtime_consumable_false_count=0,
        enforcement_enabled_false_count=0,
        operator_approved_count=0,
        runtime_consumable_count=0,
        enforcement_enabled_count=0,
        source_threshold_candidate_count=0,
        source_threshold_ready_count=0,
        deterministic_ordering_version="v0",
        candidate_generation_version="v0",
        artifact_schema_version="v0",
    )
    assert isinstance(summary, tuple)
    with pytest.raises(AttributeError):
        summary.total_policy_candidates = 1  # type: ignore[misc]


def test_build_result_is_named_tuple_immutable():
    config = _make_config()
    candidate = _make_candidate()
    summary = Stage26PolicyCandidateSummary(
        stage25_manifest_hash="abc",
        total_policy_candidates=1,
        ready_for_operator_review_count=1,
        needs_more_measured_rows_count=0,
        needs_better_coverage_count=0,
        needs_scope_review_count=0,
        needs_rejection_review_count=0,
        invalid_for_operator_review_count=0,
        observe_only_candidate_count=1,
        blocked_insufficient_evidence_count=0,
        blocked_invalid_threshold_count=0,
        blocked_policy_leak_count=0,
        blocked_runtime_consumable_count=0,
        blocked_approval_leak_count=0,
        threshold_policy_candidate_kind_count=1,
        coverage_caveat_policy_candidate_kind_count=0,
        observability_caveat_policy_candidate_kind_count=0,
        rejection_caveat_policy_candidate_kind_count=0,
        candidate_only_true_count=1,
        observe_only_true_count=1,
        operator_approved_false_count=1,
        runtime_consumable_false_count=1,
        enforcement_enabled_false_count=1,
        operator_approved_count=0,
        runtime_consumable_count=0,
        enforcement_enabled_count=0,
        source_threshold_candidate_count=1,
        source_threshold_ready_count=1,
        deterministic_ordering_version="v0",
        candidate_generation_version="v0",
        artifact_schema_version="v0",
    )
    result = Stage26PolicyCandidateBuildResult(
        stage26_policy_candidate_version=(
            c.STAGE26_POLICY_CANDIDATE_VERSION
        ),
        deterministic_ordering_version="v0",
        candidate_generation_version="v0",
        artifact_schema_version="v0",
        stage25_manifest_hash="abc",
        stage26_threshold_generation_version="t0",
        stage26_threshold_deterministic_ordering_version="t0",
        stage26_threshold_version="t0",
        config=config,
        policy_candidates=(candidate,),
        summary=summary,
        source_threshold_candidate_set_size=1,
    )
    assert isinstance(result, tuple)
    with pytest.raises(AttributeError):
        result.source_threshold_candidate_set_size = 99  # type: ignore[misc]


def test_artifact_reference_is_immutable():
    ref = Stage26PolicyCandidateArtifactReference(
        artifact_kind="POLICY_CANDIDATE_ROWS",
        basename="stage26_policy_candidates.jsonl",
        sha256="a" * 64,
        byte_count=0,
        row_count=0,
        redaction_confirmed=True,
    )
    assert isinstance(ref, tuple)
    with pytest.raises(AttributeError):
        ref.redaction_confirmed = False  # type: ignore[misc]


def test_artifact_set_is_immutable():
    ref = Stage26PolicyCandidateArtifactReference(
        artifact_kind="POLICY_CANDIDATE_ROWS",
        basename="stage26_policy_candidates.jsonl",
        sha256="a" * 64,
        byte_count=0,
        row_count=0,
        redaction_confirmed=True,
    )
    artifact_set = Stage26PolicyCandidateArtifactSet(
        output_dir="/tmp",
        rows_path="/tmp/r",
        summary_path="/tmp/s",
        manifest_path="/tmp/m",
        artifact_references=(ref,),
        manifest_hash="a" * 64,
        redaction_confirmed=True,
    )
    assert isinstance(artifact_set, tuple)
    with pytest.raises(AttributeError):
        artifact_set.redaction_confirmed = False  # type: ignore[misc]


def test_candidate_carries_all_safety_locks():
    candidate = _make_candidate()
    assert candidate.candidate_only is True
    assert candidate.observe_only is True
    assert candidate.operator_approved is False
    assert candidate.runtime_consumable is False
    assert candidate.enforcement_enabled is False


def test_candidate_cohort_key_fields_are_tuples():
    candidate = _make_candidate()
    assert isinstance(candidate.cohort_key_dimensions, tuple)
    assert isinstance(candidate.cohort_key_values, tuple)


def test_preserve_threshold_evidence_returns_rate_tuple():
    from PHX2.stage26.cohort_models import Stage26CohortKey
    from PHX2.stage26.threshold_models import (
        Stage26ThresholdCandidate,
        Stage26ThresholdEvidenceSummary,
    )

    key = Stage26CohortKey(
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
        values=("MEASURED",),
    )
    evidence = Stage26ThresholdEvidenceSummary(
        cohort_key=key,
        row_count=4,
        primary_measured_denominator_count=2,
        threshold_calibration_eligible_count=2,
        measured_count=2,
        partial_count=0,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=0,
        unsupported_count=0,
        rejected_count=0,
        coverage_gap_rate=0.1,
        scope_gap_rate=0.2,
        rejection_rate=0.3,
        source_conflict_rate=0.4,
        ambiguous_rate=0.5,
        observability_rate=0.6,
        stage25_manifest_hash="abc",
    )
    threshold = Stage26ThresholdCandidate(
        candidate_id="x#k",
        cohort_key=key,
        candidate_kind="MIN_PRIMARY_MEASURED_COUNT",
        threshold_direction="MINIMUM",
        threshold_value=1.0,
        observed_value=2.0,
        candidate_status="CANDIDATE_ONLY",
        evidence_class="PRIMARY_MEASURED_EVIDENCE",
        review_readiness="READY_FOR_POLICY_CANDIDATE_REVIEW",
        reason="ok",
        evidence_summary=evidence,
        candidate_only=True,
        operator_approved=False,
        runtime_consumable=False,
        stage25_manifest_hash="abc",
        generation_version="t0",
    )
    rates = preserve_threshold_evidence(threshold)
    assert rates == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)


def test_config_default_factory_matches_locked_defaults():
    from PHX2.stage26.policy_candidate_builder import (
        default_policy_candidate_config,
    )

    config = default_policy_candidate_config()
    assert config.min_ready_threshold_candidates == 0
    assert config.include_non_ready_candidates is True
    assert config.artifact_schema_version == (
        c.STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION
    )
    assert config.candidate_generation_version == (
        c.STAGE26_POLICY_CANDIDATE_VERSION
    )
    assert config.deterministic_ordering_version == (
        c.STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION
    )
