"""Stage 26.6 review packet builder behavior tests.

The tests use synthetic Stage 26.5
``Stage26PolicyCandidateBuildResult`` inputs (built directly with
NamedTuple constructors) so the Stage 26.6 builder is exercised in
isolation. No Stage 25 / Stage 26.1 artifact bytes are touched.
"""

from __future__ import annotations

import pytest

from PHX2.stage26 import review_packet_constants as c
from PHX2.stage26.errors import (
    Stage26Error,
    Stage26ReviewPacketError,
)
from PHX2.stage26.policy_candidate_constants import (
    POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE,
    POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
    POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
    POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW,
    POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE,
    POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE,
    STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION,
    STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_POLICY_CANDIDATE_VERSION,
)
from PHX2.stage26.policy_candidate_models import (
    Stage26PolicyCandidate,
    Stage26PolicyCandidateBuildResult,
    Stage26PolicyCandidateConfig,
    Stage26PolicyCandidateSummary,
)
from PHX2.stage26.review_packet_builder import (
    build_approval_handoff,
    build_review_candidate_from_policy_candidate,
    build_review_packet,
    default_review_packet_config,
    summarize_review_candidates,
)
from PHX2.stage26.review_packet_models import (
    Stage26ApprovalHandoff,
    Stage26ReviewCandidate,
    Stage26ReviewPacket,
    Stage26ReviewPacketBuildResult,
)


# ---------------------------------------------------------------------------
# Synthetic Stage 26.5 fixtures
# ---------------------------------------------------------------------------


_MANIFEST_HASH = "manifest_sha_abc"
_ALT_MANIFEST_HASH = "manifest_sha_xyz"


def _policy_candidate(
    *,
    policy_candidate_id: str = "THRESHOLD_POLICY_CANDIDATE#sig_001",
    candidate_kind: str = (
        POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE
    ),
    candidate_status: str = (
        POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
    ),
    readiness: str = (
        POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW
    ),
    source_threshold_candidate_id: str = "sig_001#MIN_PRIMARY_MEASURED_COUNT",
    source_threshold_candidate_kind: str = "MIN_PRIMARY_MEASURED_COUNT",
    cohort_key_values: tuple[str, ...] = ("MEASURED",),
    threshold_direction: str = "MINIMUM",
    threshold_value: float = 1.0,
    observed_value: float = 2.0,
    evidence_class: str = "PRIMARY_MEASURED_EVIDENCE",
    source_threshold_candidate_status: str = "CANDIDATE_ONLY",
    source_threshold_review_readiness: str = (
        "READY_FOR_POLICY_CANDIDATE_REVIEW"
    ),
    primary_measured: int = 2,
    threshold_eligible: int = 2,
    row_count: int = 4,
    manifest_hash: str = _MANIFEST_HASH,
    candidate_only: bool = True,
    observe_only: bool = True,
    operator_approved: bool = False,
    runtime_consumable: bool = False,
    enforcement_enabled: bool = False,
) -> Stage26PolicyCandidate:
    return Stage26PolicyCandidate(
        policy_candidate_id=policy_candidate_id,
        candidate_kind=candidate_kind,
        candidate_status=candidate_status,
        readiness=readiness,
        source_threshold_candidate_id=source_threshold_candidate_id,
        source_threshold_candidate_kind=source_threshold_candidate_kind,
        cohort_key_dimensions=("MEASUREMENT_TRUTH_CLASS",),
        cohort_key_values=cohort_key_values,
        threshold_direction=threshold_direction,
        threshold_value=threshold_value,
        observed_value=observed_value,
        evidence_class=evidence_class,
        source_threshold_candidate_status=(
            source_threshold_candidate_status
        ),
        source_threshold_review_readiness=(
            source_threshold_review_readiness
        ),
        primary_measured_denominator_count=primary_measured,
        threshold_calibration_eligible_count=threshold_eligible,
        row_count=row_count,
        coverage_gap_rate=0.0,
        scope_gap_rate=0.0,
        rejection_rate=0.0,
        source_conflict_rate=0.0,
        ambiguous_rate=0.0,
        observability_rate=1.0,
        reason="cleared",
        candidate_only=candidate_only,
        observe_only=observe_only,
        operator_approved=operator_approved,
        runtime_consumable=runtime_consumable,
        enforcement_enabled=enforcement_enabled,
        stage25_manifest_hash=manifest_hash,
        stage26_threshold_generation_version=(
            "stage26_threshold_candidate_v0"
        ),
        stage26_policy_candidate_version=(
            STAGE26_POLICY_CANDIDATE_VERSION
        ),
    )


def _policy_candidate_config() -> Stage26PolicyCandidateConfig:
    return Stage26PolicyCandidateConfig(
        min_ready_threshold_candidates=0,
        include_non_ready_candidates=True,
        artifact_schema_version=(
            STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION
        ),
        candidate_generation_version=STAGE26_POLICY_CANDIDATE_VERSION,
        deterministic_ordering_version=(
            STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION
        ),
    )


def _policy_summary(
    candidates: tuple[Stage26PolicyCandidate, ...],
    *,
    manifest_hash: str = _MANIFEST_HASH,
    source_threshold_count: int = 1,
    source_threshold_ready: int = 1,
) -> Stage26PolicyCandidateSummary:
    ready = sum(
        1
        for entry in candidates
        if entry.readiness
        == POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW
    )
    return Stage26PolicyCandidateSummary(
        stage25_manifest_hash=manifest_hash,
        total_policy_candidates=len(candidates),
        ready_for_operator_review_count=ready,
        needs_more_measured_rows_count=0,
        needs_better_coverage_count=0,
        needs_scope_review_count=0,
        needs_rejection_review_count=0,
        invalid_for_operator_review_count=0,
        observe_only_candidate_count=ready,
        blocked_insufficient_evidence_count=0,
        blocked_invalid_threshold_count=0,
        blocked_policy_leak_count=0,
        blocked_runtime_consumable_count=0,
        blocked_approval_leak_count=0,
        threshold_policy_candidate_kind_count=ready,
        coverage_caveat_policy_candidate_kind_count=0,
        observability_caveat_policy_candidate_kind_count=0,
        rejection_caveat_policy_candidate_kind_count=0,
        candidate_only_true_count=len(candidates),
        observe_only_true_count=len(candidates),
        operator_approved_false_count=len(candidates),
        runtime_consumable_false_count=len(candidates),
        enforcement_enabled_false_count=len(candidates),
        operator_approved_count=0,
        runtime_consumable_count=0,
        enforcement_enabled_count=0,
        source_threshold_candidate_count=source_threshold_count,
        source_threshold_ready_count=source_threshold_ready,
        deterministic_ordering_version=(
            STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION
        ),
        candidate_generation_version=STAGE26_POLICY_CANDIDATE_VERSION,
        artifact_schema_version=(
            STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION
        ),
    )


def _policy_build_result(
    candidates: tuple[Stage26PolicyCandidate, ...],
    *,
    manifest_hash: str = _MANIFEST_HASH,
) -> Stage26PolicyCandidateBuildResult:
    summary = _policy_summary(candidates, manifest_hash=manifest_hash)
    return Stage26PolicyCandidateBuildResult(
        stage26_policy_candidate_version=(
            STAGE26_POLICY_CANDIDATE_VERSION
        ),
        deterministic_ordering_version=(
            STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION
        ),
        candidate_generation_version=STAGE26_POLICY_CANDIDATE_VERSION,
        artifact_schema_version=(
            STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION
        ),
        stage25_manifest_hash=manifest_hash,
        stage26_threshold_generation_version=(
            "stage26_threshold_candidate_v0"
        ),
        stage26_threshold_deterministic_ordering_version=(
            "stage26_threshold_ordering_v0"
        ),
        stage26_threshold_version="stage26_threshold_v0",
        config=_policy_candidate_config(),
        policy_candidates=candidates,
        summary=summary,
        source_threshold_candidate_set_size=len(candidates),
    )


# ---------------------------------------------------------------------------
# Default config + handoff
# ---------------------------------------------------------------------------


def test_default_review_packet_config_uses_locked_axes():
    config = default_review_packet_config()
    assert config.include_blocked_candidates is True
    assert (
        config.artifact_schema_version
        == c.STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION
    )
    assert config.review_packet_version == c.STAGE26_REVIEW_PACKET_VERSION
    assert (
        config.deterministic_ordering_version
        == c.STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION
    )


def test_default_approval_handoff_is_pending_with_none_placeholders():
    handoff = build_approval_handoff()
    assert isinstance(handoff, Stage26ApprovalHandoff)
    assert handoff.approval_required is True
    assert (
        handoff.approval_status
        == c.APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    )
    assert handoff.approval_actor is None
    assert handoff.approval_timestamp_utc is None
    assert handoff.approval_notes is None
    assert handoff.operator_approved is False
    assert handoff.runtime_consumable is False
    assert handoff.enforcement_enabled is False


# ---------------------------------------------------------------------------
# Per-candidate behavior
# ---------------------------------------------------------------------------


def test_ready_policy_candidate_becomes_ready_review_candidate():
    config = default_review_packet_config()
    policy = _policy_candidate()
    review = build_review_candidate_from_policy_candidate(policy, config)
    assert (
        review.review_candidate_status
        == c.REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW
    )


@pytest.mark.parametrize(
    "policy_readiness,expected_review_status",
    [
        (
            POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
            c.REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS,
        ),
        (
            POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
            c.REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE,
        ),
        (
            POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW,
            c.REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW,
        ),
        (
            POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW,
            c.REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW,
        ),
        (
            POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
            c.REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW,
        ),
    ],
)
def test_each_policy_readiness_maps_to_locked_review_status(
    policy_readiness, expected_review_status
):
    config = default_review_packet_config()
    policy = _policy_candidate(
        candidate_status=(
            POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
        ),
        readiness=policy_readiness,
    )
    review = build_review_candidate_from_policy_candidate(policy, config)
    assert review.review_candidate_status == expected_review_status


def test_safety_locks_pinned_on_every_emitted_review_candidate():
    config = default_review_packet_config()
    policy = _policy_candidate()
    review = build_review_candidate_from_policy_candidate(policy, config)
    assert review.review_only is True
    assert review.candidate_only is True
    assert review.observe_only is True
    assert review.operator_approved is False
    assert review.runtime_consumable is False
    assert review.enforcement_enabled is False


def test_review_candidate_carries_pending_handoff_placeholders():
    config = default_review_packet_config()
    policy = _policy_candidate()
    review = build_review_candidate_from_policy_candidate(policy, config)
    handoff = review.handoff
    assert handoff.approval_required is True
    assert (
        handoff.approval_status
        == c.APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    )
    assert handoff.approval_actor is None
    assert handoff.approval_timestamp_utc is None
    assert handoff.approval_notes is None
    assert handoff.operator_approved is False
    assert handoff.runtime_consumable is False
    assert handoff.enforcement_enabled is False


def test_review_candidate_preserves_source_evidence_verbatim():
    config = default_review_packet_config()
    policy = _policy_candidate(
        cohort_key_values=("PARTIAL",),
        candidate_kind=(
            POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE
        ),
        readiness=POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
        candidate_status=(
            POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
        ),
        evidence_class="COVERAGE_CAVEAT",
        threshold_value=0.5,
        observed_value=0.25,
    )
    review = build_review_candidate_from_policy_candidate(policy, config)
    assert review.source_policy_candidate_id == policy.policy_candidate_id
    assert (
        review.source_threshold_candidate_id
        == policy.source_threshold_candidate_id
    )
    assert review.candidate_kind == policy.candidate_kind
    assert review.policy_candidate_status == policy.candidate_status
    assert review.policy_candidate_readiness == policy.readiness
    assert review.cohort_key_dimensions == policy.cohort_key_dimensions
    assert review.cohort_key_values == policy.cohort_key_values
    assert review.threshold_direction == policy.threshold_direction
    assert review.threshold_value == policy.threshold_value
    assert review.observed_value == policy.observed_value
    assert review.evidence_class == policy.evidence_class
    assert review.stage25_manifest_hash == policy.stage25_manifest_hash
    assert (
        review.stage26_policy_candidate_version
        == policy.stage26_policy_candidate_version
    )


def test_review_candidate_id_is_deterministic_from_source_id():
    config = default_review_packet_config()
    policy = _policy_candidate(
        policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#abc"
    )
    review_a = build_review_candidate_from_policy_candidate(policy, config)
    review_b = build_review_candidate_from_policy_candidate(policy, config)
    assert review_a.review_candidate_id == review_b.review_candidate_id
    assert (
        review_a.review_candidate_id
        == "OPERATOR_REVIEW_CANDIDATE#THRESHOLD_POLICY_CANDIDATE#abc"
    )


def test_review_candidate_caveat_summary_includes_upstream_chain():
    config = default_review_packet_config()
    policy = _policy_candidate()
    review = build_review_candidate_from_policy_candidate(policy, config)
    assert "stage26_6_review_status=" in review.caveat_summary
    assert "stage26_5_status=" in review.caveat_summary
    assert "stage26_5_readiness=" in review.caveat_summary
    assert "upstream_reason=" in review.caveat_summary


# ---------------------------------------------------------------------------
# Builder rejects upstream safety leaks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,bad_value,expected_code",
    [
        ("operator_approved", True, "STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK"),
        ("runtime_consumable", True, "STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK"),
        ("enforcement_enabled", True, "STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK"),
        ("candidate_only", False, "STG26_CAL_REVIEW_PACKET_INVALID_INPUT"),
        ("observe_only", False, "STG26_CAL_REVIEW_PACKET_INVALID_INPUT"),
    ],
)
def test_builder_rejects_upstream_safety_flag_flip(
    field, bad_value, expected_code
):
    config = default_review_packet_config()
    kwargs = {field: bad_value}
    policy = _policy_candidate(**kwargs)
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        build_review_candidate_from_policy_candidate(policy, config)
    assert excinfo.value.error_code == expected_code


def test_stage26_review_packet_error_subclasses_stage26_error():
    assert issubclass(Stage26ReviewPacketError, Stage26Error)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_build_review_packet_emits_one_review_candidate_per_policy_candidate():
    config = default_review_packet_config()
    policies = (
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#sig_001",
            source_threshold_candidate_id="sig_001#k",
            cohort_key_values=("MEASURED",),
        ),
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#sig_002",
            source_threshold_candidate_id="sig_002#k",
            cohort_key_values=("PARTIAL",),
            readiness=POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
            candidate_status=(
                POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
            ),
        ),
    )
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    assert isinstance(result, Stage26ReviewPacketBuildResult)
    assert len(result.review_packet.review_candidates) == 2


def test_build_review_packet_ordering_is_deterministic_by_cohort_then_kind():
    config = default_review_packet_config()
    # Build with reversed input order; output should still sort
    # ascending by (cohort_key_values, candidate_kind,
    # source_threshold_candidate_id).
    policies = (
        _policy_candidate(
            policy_candidate_id=(
                "THRESHOLD_POLICY_CANDIDATE#zzz"
            ),
            source_threshold_candidate_id="zzz#k",
            cohort_key_values=("ZZZZ",),
        ),
        _policy_candidate(
            policy_candidate_id=(
                "THRESHOLD_POLICY_CANDIDATE#aaa"
            ),
            source_threshold_candidate_id="aaa#k",
            cohort_key_values=("AAAA",),
        ),
    )
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    ordered_values = tuple(
        candidate.cohort_key_values
        for candidate in result.review_packet.review_candidates
    )
    assert ordered_values == (("AAAA",), ("ZZZZ",))


def test_build_review_packet_is_deterministic_across_runs():
    config = default_review_packet_config()
    policies = (
        _policy_candidate(),
    )
    build_result = _policy_build_result(policies)
    a = build_review_packet(build_result, config)
    b = build_review_packet(build_result, config)
    assert a == b
    assert a.review_packet == b.review_packet
    assert (
        a.review_packet.source_policy_candidate_build_hash
        == b.review_packet.source_policy_candidate_build_hash
    )


def test_build_review_packet_pins_packet_id_to_manifest_hash():
    config = default_review_packet_config()
    policies = (_policy_candidate(),)
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    packet = result.review_packet
    assert (
        packet.packet_id
        == f"OPERATOR_REVIEW_PACKET#{_MANIFEST_HASH}"
    )
    assert packet.stage25_manifest_hash == _MANIFEST_HASH


def test_build_review_packet_defaults_to_pending_handoff():
    config = default_review_packet_config()
    policies = (_policy_candidate(),)
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    packet = result.review_packet
    assert (
        packet.approval_handoff_status
        == c.APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    )
    handoff = packet.approval_handoff
    assert handoff.approval_required is True
    assert (
        handoff.approval_status
        == c.APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    )
    assert handoff.approval_actor is None
    assert handoff.approval_timestamp_utc is None
    assert handoff.approval_notes is None
    assert handoff.operator_approved is False
    assert handoff.runtime_consumable is False
    assert handoff.enforcement_enabled is False


def test_build_review_packet_top_level_safety_locks_pinned():
    config = default_review_packet_config()
    policies = (_policy_candidate(),)
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    packet = result.review_packet
    assert packet.review_only is True
    assert packet.operator_approved is False
    assert packet.runtime_consumable is False
    assert packet.enforcement_enabled is False
    assert (
        packet.packet_status
        == c.REVIEW_PACKET_STATUS_REVIEW_ONLY_PACKET
    )


def test_build_review_packet_rejects_mixed_manifest_hash():
    config = default_review_packet_config()
    policies = (
        _policy_candidate(manifest_hash=_MANIFEST_HASH),
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#alt",
            source_threshold_candidate_id="alt#k",
            manifest_hash=_ALT_MANIFEST_HASH,
        ),
    )
    build_result = _policy_build_result(policies)  # pins _MANIFEST_HASH
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        build_review_packet(build_result, config)
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH"
    )


def test_build_review_packet_filters_blocked_when_knob_is_false():
    config = default_review_packet_config()._replace(
        include_blocked_candidates=False
    )
    policies = (
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#ok",
            source_threshold_candidate_id="ok#k",
        ),
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#bad",
            source_threshold_candidate_id="bad#k",
            cohort_key_values=("PARTIAL",),
            readiness=POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
            candidate_status=(
                POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
            ),
        ),
    )
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    # Only the OBSERVE_ONLY_CANDIDATE entry survives.
    assert len(result.review_packet.review_candidates) == 1
    surviving = result.review_packet.review_candidates[0]
    assert (
        surviving.policy_candidate_status
        == POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_counts_match_review_candidate_statuses():
    config = default_review_packet_config()
    policies = (
        _policy_candidate(),
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#more",
            source_threshold_candidate_id="more#k",
            cohort_key_values=("PARTIAL",),
            readiness=POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
            candidate_status=(
                POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
            ),
        ),
        _policy_candidate(
            policy_candidate_id="THRESHOLD_POLICY_CANDIDATE#bad_input",
            source_threshold_candidate_id="bad_input#k",
            cohort_key_values=("REJECTED",),
            readiness=POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
            candidate_status=(
                POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
            ),
        ),
    )
    result = build_review_packet(
        _policy_build_result(policies), config
    )
    summary = result.review_packet.review_summary
    assert summary.total_review_candidates == 3
    assert summary.ready_for_operator_review_count == 1
    assert summary.needs_more_measured_rows_count == 1
    assert summary.invalid_for_operator_review_count == 1
    assert summary.review_only_count == 3
    assert summary.candidate_only_count == 3
    assert summary.observe_only_count == 3
    assert summary.operator_approved_count == 0
    assert summary.runtime_consumable_count == 0
    assert summary.enforcement_enabled_count == 0
    assert summary.operator_approved_false_count == 3
    assert summary.runtime_consumable_false_count == 3
    assert summary.enforcement_enabled_false_count == 3


def test_summarize_returns_zero_counts_on_empty_candidates():
    config = default_review_packet_config()
    summary = summarize_review_candidates(
        (),
        stage25_manifest_hash=_MANIFEST_HASH,
        source_policy_candidate_count=0,
        source_policy_ready_count=0,
        config=config,
    )
    assert summary.total_review_candidates == 0
    assert summary.ready_for_operator_review_count == 0
    assert summary.review_only_count == 0
    assert summary.operator_approved_count == 0
    assert summary.runtime_consumable_count == 0
    assert summary.enforcement_enabled_count == 0


# ---------------------------------------------------------------------------
# Empty build result
# ---------------------------------------------------------------------------


def test_build_review_packet_handles_empty_input():
    config = default_review_packet_config()
    build_result = _policy_build_result(())
    result = build_review_packet(build_result, config)
    packet = result.review_packet
    assert packet.review_candidates == ()
    assert packet.review_summary.total_review_candidates == 0
    assert packet.review_only is True
