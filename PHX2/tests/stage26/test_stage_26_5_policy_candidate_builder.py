"""Stage 26.5 policy candidate builder behavior tests.

The tests use synthetic Stage 26.4 ``Stage26ThresholdCandidateSet``
inputs (built directly with NamedTuple constructors) so the Stage
26.5 builder is exercised in isolation. No Stage 25 / Stage 26.1
artifact bytes are touched.
"""

from __future__ import annotations

import pytest

from PHX2.stage26 import policy_candidate_constants as c
from PHX2.stage26.cohort_models import Stage26CohortKey
from PHX2.stage26.errors import (
    Stage26Error,
    Stage26PolicyCandidateError,
)
from PHX2.stage26.policy_candidate_builder import (
    build_policy_candidate_from_threshold,
    build_policy_candidates,
    default_policy_candidate_config,
    summarize_policy_candidates,
)
from PHX2.stage26.threshold_constants import (
    STAGE26_CANDIDATE_GENERATION_VERSION,
    STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_THRESHOLD_VERSION,
)
from PHX2.stage26.threshold_models import (
    Stage26ThresholdCandidate,
    Stage26ThresholdCandidateConfig,
    Stage26ThresholdCandidateSet,
    Stage26ThresholdEvidenceSummary,
)


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _evidence_summary(
    *,
    cohort_key: Stage26CohortKey,
    row_count: int = 4,
    primary_measured: int = 2,
    threshold_eligible: int = 2,
    coverage_rate: float = 0.0,
    scope_rate: float = 0.0,
    rejection_rate: float = 0.0,
    source_conflict_rate: float = 0.0,
    ambiguous_rate: float = 0.0,
    observability_rate: float = 1.0,
    manifest_hash: str = "manifest_sha_abc",
) -> Stage26ThresholdEvidenceSummary:
    return Stage26ThresholdEvidenceSummary(
        cohort_key=cohort_key,
        row_count=row_count,
        primary_measured_denominator_count=primary_measured,
        threshold_calibration_eligible_count=threshold_eligible,
        measured_count=primary_measured,
        partial_count=0,
        source_conflict_count=0,
        ambiguous_count=0,
        window_ineligible_count=0,
        missing_count=0,
        unsupported_count=0,
        rejected_count=0,
        coverage_gap_rate=coverage_rate,
        scope_gap_rate=scope_rate,
        rejection_rate=rejection_rate,
        source_conflict_rate=source_conflict_rate,
        ambiguous_rate=ambiguous_rate,
        observability_rate=observability_rate,
        stage25_manifest_hash=manifest_hash,
    )


def _threshold_candidate(
    *,
    values: tuple[str, ...] = ("MEASURED",),
    candidate_kind: str = "MIN_PRIMARY_MEASURED_COUNT",
    threshold_direction: str = "MINIMUM",
    threshold_value: float = 1.0,
    observed_value: float = 2.0,
    candidate_status: str = "CANDIDATE_ONLY",
    evidence_class: str = "PRIMARY_MEASURED_EVIDENCE",
    review_readiness: str = "READY_FOR_POLICY_CANDIDATE_REVIEW",
    reason: str = "cleared",
    manifest_hash: str = "manifest_sha_abc",
    candidate_only: bool = True,
    operator_approved: bool = False,
    runtime_consumable: bool = False,
) -> Stage26ThresholdCandidate:
    key = Stage26CohortKey(
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
        values=values,
    )
    summary = _evidence_summary(
        cohort_key=key, manifest_hash=manifest_hash
    )
    return Stage26ThresholdCandidate(
        candidate_id=f"{'|'.join(values)}#{candidate_kind}",
        cohort_key=key,
        candidate_kind=candidate_kind,
        threshold_direction=threshold_direction,
        threshold_value=threshold_value,
        observed_value=observed_value,
        candidate_status=candidate_status,
        evidence_class=evidence_class,
        review_readiness=review_readiness,
        reason=reason,
        evidence_summary=summary,
        candidate_only=candidate_only,
        operator_approved=operator_approved,
        runtime_consumable=runtime_consumable,
        stage25_manifest_hash=manifest_hash,
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
    )


def _threshold_config() -> Stage26ThresholdCandidateConfig:
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
        candidate_generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
    )


def _candidate_set(
    candidates: tuple[Stage26ThresholdCandidate, ...],
    *,
    manifest_hash: str = "manifest_sha_abc",
    ready_count: int = -1,
) -> Stage26ThresholdCandidateSet:
    if ready_count == -1:
        ready_count = sum(
            1
            for entry in candidates
            if entry.review_readiness
            == "READY_FOR_POLICY_CANDIDATE_REVIEW"
        )
    return Stage26ThresholdCandidateSet(
        stage26_threshold_version=STAGE26_THRESHOLD_VERSION,
        deterministic_ordering_version=(
            STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
        ),
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
        stage25_manifest_hash=manifest_hash,
        config=_threshold_config(),
        candidates=candidates,
        total_candidates=len(candidates),
        ready_for_review_count=ready_count,
        insufficient_measured_count=0,
        suppressed_count=0,
        invalid_cohort_count=0,
    )


# ---------------------------------------------------------------------------
# Per-candidate builder behavior
# ---------------------------------------------------------------------------


def test_ready_candidate_becomes_ready_observe_only_policy_candidate():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate()
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_kind
        == c.POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE
    )
    assert (
        candidate.candidate_status
        == c.POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
    )
    assert (
        candidate.readiness
        == c.POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW
    )


def test_safety_locks_pinned_on_every_emitted_candidate():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate()
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert candidate.candidate_only is True
    assert candidate.observe_only is True
    assert candidate.operator_approved is False
    assert candidate.runtime_consumable is False
    assert candidate.enforcement_enabled is False


def test_policy_candidate_id_is_deterministic():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate()
    a = build_policy_candidate_from_threshold(threshold, config)
    b = build_policy_candidate_from_threshold(threshold, config)
    assert a.policy_candidate_id == b.policy_candidate_id
    assert a.policy_candidate_id == (
        f"{c.POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE}"
        f"#MEASURED#MIN_PRIMARY_MEASURED_COUNT"
    )


def test_preserves_threshold_evidence_verbatim():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate()
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert candidate.cohort_key_dimensions == ("MEASUREMENT_TRUTH_CLASS",)
    assert candidate.cohort_key_values == ("MEASURED",)
    assert candidate.threshold_value == 1.0
    assert candidate.observed_value == 2.0
    assert candidate.evidence_class == "PRIMARY_MEASURED_EVIDENCE"
    assert candidate.source_threshold_candidate_id == (
        "MEASURED#MIN_PRIMARY_MEASURED_COUNT"
    )
    assert candidate.source_threshold_candidate_kind == (
        "MIN_PRIMARY_MEASURED_COUNT"
    )
    assert candidate.source_threshold_candidate_status == "CANDIDATE_ONLY"
    assert (
        candidate.source_threshold_review_readiness
        == "READY_FOR_POLICY_CANDIDATE_REVIEW"
    )
    assert candidate.stage25_manifest_hash == "manifest_sha_abc"
    assert candidate.primary_measured_denominator_count == 2
    assert candidate.threshold_calibration_eligible_count == 2
    assert candidate.row_count == 4
    assert candidate.observability_rate == 1.0
    assert "cleared" in candidate.reason


def test_insufficient_measured_threshold_becomes_blocked_needs_more_rows():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(
        candidate_status=(
            "INSUFFICIENT_MEASURED_DENOMINATOR"
        ),
        review_readiness="NEEDS_MORE_MEASURED_ROWS",
        reason="below min",
    )
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_status
        == c.POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    )
    assert (
        candidate.readiness
        == c.POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS
    )


def test_invalid_cohort_threshold_becomes_blocked_invalid_threshold():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(
        candidate_status="INVALID_COHORT_INPUT",
        evidence_class="INVALID_INPUT_CAVEAT",
        review_readiness="INVALID_FOR_REVIEW",
        reason="invalid",
    )
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_status
        == c.POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD
    )
    assert (
        candidate.readiness
        == c.POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW
    )
    # INVALID_INPUT_CAVEAT maps onto the observability caveat kind so
    # the operator review surface still has a known kind to filter on.
    assert candidate.candidate_kind in c.POLICY_CANDIDATE_KINDS


def test_coverage_caveat_becomes_coverage_caveat_policy_candidate():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(
        candidate_kind="MAX_COVERAGE_GAP_RATE",
        threshold_direction="MAXIMUM",
        threshold_value=0.1,
        observed_value=0.5,
        candidate_status="SUPPRESSED_BY_COVERAGE_GAP",
        evidence_class="COVERAGE_CAVEAT",
        review_readiness="NEEDS_BETTER_COVERAGE",
        reason="coverage gap too wide",
    )
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_kind
        == c.POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE
    )
    assert (
        candidate.candidate_status
        == c.POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    )
    assert (
        candidate.readiness
        == c.POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE
    )


def test_scope_caveat_collapses_onto_observability_caveat_kind():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(
        candidate_kind="MAX_SCOPE_GAP_RATE",
        threshold_direction="MAXIMUM",
        threshold_value=0.1,
        observed_value=0.5,
        candidate_status="SUPPRESSED_BY_SCOPE_GAP",
        evidence_class="SCOPE_CAVEAT",
        review_readiness="NEEDS_SCOPE_REVIEW",
        reason="scope gap too wide",
    )
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_kind
        == c.POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE
    )
    assert (
        candidate.readiness
        == c.POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW
    )


def test_rejection_caveat_becomes_rejection_caveat_policy_candidate():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(
        candidate_kind="MAX_REJECTION_RATE",
        threshold_direction="MAXIMUM",
        threshold_value=0.1,
        observed_value=0.5,
        candidate_status="SUPPRESSED_BY_REJECTION_GAP",
        evidence_class="REJECTION_CAVEAT",
        review_readiness="NEEDS_REJECTION_REVIEW",
        reason="rejection rate too high",
    )
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_kind
        == c.POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE
    )
    assert (
        candidate.readiness
        == c.POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW
    )


def test_observability_caveat_becomes_observability_caveat_policy_candidate():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(
        candidate_kind="MAX_SOURCE_CONFLICT_RATE",
        threshold_direction="MAXIMUM",
        threshold_value=1.0,
        observed_value=0.5,
        candidate_status="CANDIDATE_ONLY",
        evidence_class="OBSERVABILITY_CAVEAT",
        review_readiness="READY_FOR_POLICY_CANDIDATE_REVIEW",
        reason="observability caveat recorded",
    )
    candidate = build_policy_candidate_from_threshold(threshold, config)
    assert (
        candidate.candidate_kind
        == c.POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE
    )
    assert (
        candidate.candidate_status
        == c.POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
    )


# ---------------------------------------------------------------------------
# Defensive safety-flag checks
# ---------------------------------------------------------------------------


def test_builder_rejects_flipped_candidate_only_input():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(candidate_only=False)
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        build_policy_candidate_from_threshold(threshold, config)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK
    )


def test_builder_rejects_flipped_operator_approved_input():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(operator_approved=True)
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        build_policy_candidate_from_threshold(threshold, config)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK
    )


def test_builder_rejects_flipped_runtime_consumable_input():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(runtime_consumable=True)
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        build_policy_candidate_from_threshold(threshold, config)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK
    )


def test_builder_rejects_unknown_candidate_kind():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(candidate_kind="BOGUS_KIND")
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        build_policy_candidate_from_threshold(threshold, config)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD
    )


def test_builder_rejects_unknown_evidence_class():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(evidence_class="BOGUS_EVIDENCE")
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        build_policy_candidate_from_threshold(threshold, config)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS
    )


def test_builder_error_is_stage26_error_subclass():
    config = default_policy_candidate_config()
    threshold = _threshold_candidate(candidate_only=False)
    with pytest.raises(Stage26Error):
        build_policy_candidate_from_threshold(threshold, config)


# ---------------------------------------------------------------------------
# Orchestrator behavior
# ---------------------------------------------------------------------------


def test_build_policy_candidates_emits_one_per_input():
    config = default_policy_candidate_config()
    inputs = (
        _threshold_candidate(values=("MEASURED",)),
        _threshold_candidate(
            values=("PARTIAL",),
            candidate_status="INSUFFICIENT_MEASURED_DENOMINATOR",
            review_readiness="NEEDS_MORE_MEASURED_ROWS",
            reason="below min",
        ),
    )
    result = build_policy_candidates(
        _candidate_set(inputs), config
    )
    assert len(result.policy_candidates) == 2
    assert (
        result.source_threshold_candidate_set_size == 2
    )


def test_build_policy_candidates_deterministic_ordering():
    config = default_policy_candidate_config()
    inputs = (
        _threshold_candidate(
            values=("REJECTED",),
            candidate_kind="MIN_THRESHOLD_ELIGIBLE_COUNT",
        ),
        _threshold_candidate(
            values=("MEASURED",),
            candidate_kind="MIN_PRIMARY_MEASURED_COUNT",
        ),
        _threshold_candidate(
            values=("MEASURED",),
            candidate_kind="MIN_THRESHOLD_ELIGIBLE_COUNT",
        ),
    )
    result_a = build_policy_candidates(
        _candidate_set(inputs), config
    )
    result_b = build_policy_candidates(
        _candidate_set(inputs), config
    )
    assert result_a == result_b
    # MEASURED < REJECTED lexicographically.
    ordered_values = tuple(
        candidate.cohort_key_values
        for candidate in result_a.policy_candidates
    )
    assert ordered_values == (
        ("MEASURED",),
        ("MEASURED",),
        ("REJECTED",),
    )
    # Within a cohort key, kinds are ordered ascending.
    assert (
        result_a.policy_candidates[0].candidate_kind
        <= result_a.policy_candidates[1].candidate_kind
    )


def test_build_policy_candidates_preserves_manifest_pin():
    config = default_policy_candidate_config()
    inputs = (_threshold_candidate(),)
    result = build_policy_candidates(
        _candidate_set(inputs, manifest_hash="manifest_sha_abc"),
        config,
    )
    assert result.stage25_manifest_hash == "manifest_sha_abc"
    assert result.summary.stage25_manifest_hash == "manifest_sha_abc"
    assert (
        result.policy_candidates[0].stage25_manifest_hash
        == "manifest_sha_abc"
    )


def test_build_policy_candidates_rejects_mixed_manifest_hash():
    config = default_policy_candidate_config()
    drift = _threshold_candidate(
        values=("PARTIAL",), manifest_hash="drifted"
    )
    pin = _threshold_candidate(values=("MEASURED",))
    candidate_set = _candidate_set(
        (pin, drift), manifest_hash="manifest_sha_abc"
    )
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        build_policy_candidates(candidate_set, config)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH
    )


def test_summary_counts_match_emitted_candidates():
    config = default_policy_candidate_config()
    inputs = (
        _threshold_candidate(values=("MEASURED",)),
        _threshold_candidate(
            values=("MISSING",),
            candidate_kind="MAX_COVERAGE_GAP_RATE",
            threshold_direction="MAXIMUM",
            threshold_value=0.0,
            observed_value=0.5,
            candidate_status="SUPPRESSED_BY_COVERAGE_GAP",
            evidence_class="COVERAGE_CAVEAT",
            review_readiness="NEEDS_BETTER_COVERAGE",
            reason="coverage too wide",
        ),
        _threshold_candidate(
            values=("REJECTED",),
            candidate_kind="MAX_REJECTION_RATE",
            threshold_direction="MAXIMUM",
            threshold_value=0.0,
            observed_value=0.5,
            candidate_status="SUPPRESSED_BY_REJECTION_GAP",
            evidence_class="REJECTION_CAVEAT",
            review_readiness="NEEDS_REJECTION_REVIEW",
            reason="rejection too high",
        ),
    )
    result = build_policy_candidates(
        _candidate_set(inputs), config
    )
    summary = result.summary
    assert summary.total_policy_candidates == 3
    assert summary.ready_for_operator_review_count == 1
    assert summary.needs_better_coverage_count == 1
    assert summary.needs_rejection_review_count == 1
    assert summary.observe_only_candidate_count == 1
    assert summary.blocked_insufficient_evidence_count == 2
    assert summary.threshold_policy_candidate_kind_count == 1
    assert summary.coverage_caveat_policy_candidate_kind_count == 1
    assert summary.rejection_caveat_policy_candidate_kind_count == 1
    assert summary.candidate_only_true_count == 3
    assert summary.observe_only_true_count == 3
    assert summary.operator_approved_false_count == 3
    assert summary.runtime_consumable_false_count == 3
    assert summary.enforcement_enabled_false_count == 3
    assert summary.operator_approved_count == 0
    assert summary.runtime_consumable_count == 0
    assert summary.enforcement_enabled_count == 0


def test_build_policy_candidates_repeated_call_is_deterministic():
    config = default_policy_candidate_config()
    inputs = (
        _threshold_candidate(values=("MEASURED",)),
        _threshold_candidate(
            values=("PARTIAL",),
            candidate_status="INSUFFICIENT_MEASURED_DENOMINATOR",
            review_readiness="NEEDS_MORE_MEASURED_ROWS",
        ),
    )
    a = build_policy_candidates(_candidate_set(inputs), config)
    b = build_policy_candidates(_candidate_set(inputs), config)
    assert a == b


def test_summarize_policy_candidates_round_trips_counts():
    config = default_policy_candidate_config()
    inputs = (_threshold_candidate(),)
    result = build_policy_candidates(_candidate_set(inputs), config)
    explicit = summarize_policy_candidates(
        result.policy_candidates,
        stage25_manifest_hash=result.stage25_manifest_hash,
        source_threshold_candidate_count=(
            result.source_threshold_candidate_set_size
        ),
        source_threshold_ready_count=1,
        config=config,
    )
    assert explicit == result.summary


# ---------------------------------------------------------------------------
# Defensive output-side leak checks
# ---------------------------------------------------------------------------


def test_no_emitted_candidate_carries_operator_approved_true():
    config = default_policy_candidate_config()
    inputs = (_threshold_candidate(),)
    result = build_policy_candidates(_candidate_set(inputs), config)
    for candidate in result.policy_candidates:
        assert candidate.operator_approved is False


def test_no_emitted_candidate_carries_runtime_consumable_true():
    config = default_policy_candidate_config()
    inputs = (_threshold_candidate(),)
    result = build_policy_candidates(_candidate_set(inputs), config)
    for candidate in result.policy_candidates:
        assert candidate.runtime_consumable is False


def test_no_emitted_candidate_carries_enforcement_enabled_true():
    config = default_policy_candidate_config()
    inputs = (_threshold_candidate(),)
    result = build_policy_candidates(_candidate_set(inputs), config)
    for candidate in result.policy_candidates:
        assert candidate.enforcement_enabled is False


def test_every_emitted_candidate_carries_candidate_only_and_observe_only_true():
    config = default_policy_candidate_config()
    inputs = (_threshold_candidate(),)
    result = build_policy_candidates(_candidate_set(inputs), config)
    for candidate in result.policy_candidates:
        assert candidate.candidate_only is True
        assert candidate.observe_only is True
