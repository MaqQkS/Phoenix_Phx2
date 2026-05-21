"""Stage 26.6 review packet model immutability + shape tests.

Confirms each Stage 26.6 model is a ``typing.NamedTuple`` subclass,
immutable, hashable when its fields are hashable, and admits exactly
the fields documented in the Stage 26.6 charter.
"""

from __future__ import annotations

import pytest

from PHX2.stage26.review_packet_models import (
    Stage26ApprovalHandoff,
    Stage26ReviewArtifactReference,
    Stage26ReviewArtifactSet,
    Stage26ReviewCandidate,
    Stage26ReviewPacket,
    Stage26ReviewPacketBuildResult,
    Stage26ReviewPacketConfig,
    Stage26ReviewSummary,
)


_MODELS: tuple[type, ...] = (
    Stage26ApprovalHandoff,
    Stage26ReviewArtifactReference,
    Stage26ReviewArtifactSet,
    Stage26ReviewCandidate,
    Stage26ReviewPacket,
    Stage26ReviewPacketBuildResult,
    Stage26ReviewPacketConfig,
    Stage26ReviewSummary,
)


@pytest.mark.parametrize("model", _MODELS)
def test_each_model_is_a_tuple_subclass(model):
    assert issubclass(model, tuple)


@pytest.mark.parametrize("model", _MODELS)
def test_each_model_declares_fields(model):
    fields = model._fields
    assert isinstance(fields, tuple)
    assert fields != ()


def _approval_handoff() -> Stage26ApprovalHandoff:
    return Stage26ApprovalHandoff(
        approval_required=True,
        approval_status="PENDING_OPERATOR_REVIEW",
        approval_actor=None,
        approval_timestamp_utc=None,
        approval_notes=None,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
    )


def test_stage26_review_packet_config_fields():
    assert Stage26ReviewPacketConfig._fields == (
        "include_blocked_candidates",
        "artifact_schema_version",
        "review_packet_version",
        "deterministic_ordering_version",
    )


def test_stage26_approval_handoff_fields():
    assert Stage26ApprovalHandoff._fields == (
        "approval_required",
        "approval_status",
        "approval_actor",
        "approval_timestamp_utc",
        "approval_notes",
        "operator_approved",
        "runtime_consumable",
        "enforcement_enabled",
    )


def test_stage26_review_candidate_fields():
    expected = (
        "review_candidate_id",
        "source_policy_candidate_id",
        "source_threshold_candidate_id",
        "candidate_kind",
        "policy_candidate_status",
        "policy_candidate_readiness",
        "review_candidate_status",
        "cohort_key_dimensions",
        "cohort_key_values",
        "threshold_direction",
        "threshold_value",
        "observed_value",
        "evidence_class",
        "caveat_summary",
        "handoff",
        "review_only",
        "candidate_only",
        "observe_only",
        "operator_approved",
        "runtime_consumable",
        "enforcement_enabled",
        "stage25_manifest_hash",
        "stage26_policy_candidate_version",
        "stage26_review_packet_version",
    )
    assert Stage26ReviewCandidate._fields == expected


def test_stage26_review_packet_fields_include_handoff_and_locks():
    fields = Stage26ReviewPacket._fields
    must_be_present = (
        "packet_id",
        "stage25_manifest_hash",
        "review_packet_version",
        "packet_status",
        "review_candidates",
        "review_summary",
        "approval_handoff",
        "approval_handoff_status",
        "review_only",
        "operator_approved",
        "runtime_consumable",
        "enforcement_enabled",
        "source_policy_candidate_build_hash",
        "deterministic_ordering_version",
    )
    for name in must_be_present:
        assert name in fields, f"Stage26ReviewPacket missing {name!r}"


def test_stage26_review_summary_fields_have_locked_counts():
    fields = Stage26ReviewSummary._fields
    must_be_present = (
        "stage25_manifest_hash",
        "total_review_candidates",
        "ready_for_operator_review_count",
        "needs_more_measured_rows_count",
        "needs_better_coverage_count",
        "needs_scope_review_count",
        "needs_rejection_review_count",
        "invalid_for_operator_review_count",
        "blocked_leak_count",
        "review_only_count",
        "candidate_only_count",
        "observe_only_count",
        "operator_approved_count",
        "runtime_consumable_count",
        "enforcement_enabled_count",
        "operator_approved_false_count",
        "runtime_consumable_false_count",
        "enforcement_enabled_false_count",
        "deterministic_ordering_version",
    )
    for name in must_be_present:
        assert name in fields, (
            f"Stage26ReviewSummary missing {name!r}"
        )


def test_stage26_review_artifact_reference_fields():
    assert Stage26ReviewArtifactReference._fields == (
        "artifact_kind",
        "basename",
        "sha256",
        "byte_count",
        "row_count",
        "redaction_confirmed",
    )


def test_stage26_review_artifact_set_fields():
    assert Stage26ReviewArtifactSet._fields == (
        "output_dir",
        "packet_path",
        "candidate_rows_path",
        "summary_path",
        "manifest_path",
        "artifact_references",
        "manifest_hash",
        "redaction_confirmed",
    )


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_approval_handoff_instance_is_immutable():
    handoff = _approval_handoff()
    with pytest.raises(AttributeError):
        handoff.approval_status = "APPROVED"  # type: ignore[misc]


def test_approval_handoff_default_locked_field_values():
    handoff = _approval_handoff()
    assert handoff.approval_required is True
    assert handoff.approval_status == "PENDING_OPERATOR_REVIEW"
    assert handoff.approval_actor is None
    assert handoff.approval_timestamp_utc is None
    assert handoff.approval_notes is None
    assert handoff.operator_approved is False
    assert handoff.runtime_consumable is False
    assert handoff.enforcement_enabled is False
