"""Stage 26.6 review packet writer behavior tests.

Exercises the deterministic offline review-only writer end-to-end
using synthetic Stage 26.5 inputs from
``test_stage_26_6_review_packet_builder``. The tests confirm
deterministic byte equality, manifest hash / byte_count / row_count
correctness, the redaction sweep, and the runtime-filename guard.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from PHX2.stage26 import review_packet_constants as c
from PHX2.stage26.errors import Stage26ReviewPacketError
from PHX2.stage26.policy_candidate_constants import (
    POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE,
    POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
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
    build_review_packet,
    default_review_packet_config,
)
from PHX2.stage26.review_packet_writer import (
    write_review_packet_artifacts,
)


_MANIFEST_HASH = "manifest_sha_abc"


# ---------------------------------------------------------------------------
# Fixtures (mirror the builder test fixtures)
# ---------------------------------------------------------------------------


def _policy_candidate(
    *,
    policy_candidate_id: str = "THRESHOLD_POLICY_CANDIDATE#sig_001",
    cohort_key_values: tuple[str, ...] = ("MEASURED",),
    threshold_value: float = 1.0,
    observed_value: float = 2.0,
) -> Stage26PolicyCandidate:
    return Stage26PolicyCandidate(
        policy_candidate_id=policy_candidate_id,
        candidate_kind=POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE,
        candidate_status=POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE,
        readiness=POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
        source_threshold_candidate_id=(
            f"{'|'.join(cohort_key_values)}#MIN_PRIMARY_MEASURED_COUNT"
        ),
        source_threshold_candidate_kind="MIN_PRIMARY_MEASURED_COUNT",
        cohort_key_dimensions=("MEASUREMENT_TRUTH_CLASS",),
        cohort_key_values=cohort_key_values,
        threshold_direction="MINIMUM",
        threshold_value=threshold_value,
        observed_value=observed_value,
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
        reason="cleared",
        candidate_only=True,
        observe_only=True,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
        stage25_manifest_hash=_MANIFEST_HASH,
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
) -> Stage26PolicyCandidateSummary:
    return Stage26PolicyCandidateSummary(
        stage25_manifest_hash=_MANIFEST_HASH,
        total_policy_candidates=len(candidates),
        ready_for_operator_review_count=len(candidates),
        needs_more_measured_rows_count=0,
        needs_better_coverage_count=0,
        needs_scope_review_count=0,
        needs_rejection_review_count=0,
        invalid_for_operator_review_count=0,
        observe_only_candidate_count=len(candidates),
        blocked_insufficient_evidence_count=0,
        blocked_invalid_threshold_count=0,
        blocked_policy_leak_count=0,
        blocked_runtime_consumable_count=0,
        blocked_approval_leak_count=0,
        threshold_policy_candidate_kind_count=len(candidates),
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
        source_threshold_candidate_count=len(candidates),
        source_threshold_ready_count=len(candidates),
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
) -> Stage26PolicyCandidateBuildResult:
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
        stage25_manifest_hash=_MANIFEST_HASH,
        stage26_threshold_generation_version=(
            "stage26_threshold_candidate_v0"
        ),
        stage26_threshold_deterministic_ordering_version=(
            "stage26_threshold_ordering_v0"
        ),
        stage26_threshold_version="stage26_threshold_v0",
        config=_policy_candidate_config(),
        policy_candidates=candidates,
        summary=_policy_summary(candidates),
        source_threshold_candidate_set_size=len(candidates),
    )


def _build_review_packet_result(
    policies: tuple[Stage26PolicyCandidate, ...] = (),
):
    if policies == ():
        policies = (_policy_candidate(),)
    return build_review_packet(
        _policy_build_result(policies),
        default_review_packet_config(),
    )


# ---------------------------------------------------------------------------
# Successful write
# ---------------------------------------------------------------------------


def test_writer_emits_four_locked_basenames(tmp_path: Path):
    result = _build_review_packet_result()
    artifact_set = write_review_packet_artifacts(result, tmp_path)
    basenames = sorted(
        ref.basename for ref in artifact_set.artifact_references
    )
    assert basenames == [
        "stage26_operator_review_candidates.jsonl",
        "stage26_operator_review_manifest.json",
        "stage26_operator_review_packet.json",
        "stage26_operator_review_summary.json",
    ]
    # All four files exist on disk.
    for basename in basenames:
        assert (tmp_path / basename).is_file()


def test_writer_records_redaction_confirmed_true(tmp_path: Path):
    result = _build_review_packet_result()
    artifact_set = write_review_packet_artifacts(result, tmp_path)
    assert artifact_set.redaction_confirmed is True
    for ref in artifact_set.artifact_references:
        assert ref.redaction_confirmed is True


def test_writer_sha256_byte_count_row_count_match_disk(tmp_path: Path):
    result = _build_review_packet_result()
    artifact_set = write_review_packet_artifacts(result, tmp_path)
    for ref in artifact_set.artifact_references:
        on_disk = (tmp_path / ref.basename).read_bytes()
        assert ref.byte_count == len(on_disk)
        assert ref.sha256 == hashlib.sha256(on_disk).hexdigest()
        if ref.basename.endswith(".jsonl"):
            non_blank = sum(
                1
                for line in on_disk.decode("utf-8").split("\n")
                if line.strip() != ""
            )
            assert ref.row_count == non_blank
        else:
            assert ref.row_count == -1


def test_writer_manifest_carries_self_entry_sentinel(tmp_path: Path):
    result = _build_review_packet_result()
    write_review_packet_artifacts(result, tmp_path)
    manifest_path = (
        tmp_path / c.STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["files"]
    self_entry = next(
        (
            entry
            for entry in entries
            if entry["basename"]
            == c.STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME
        ),
        None,
    )
    assert self_entry is not None
    assert (
        self_entry["sha256"]
        == c.STAGE26_REVIEW_PACKET_SELF_REFERENTIAL_MANIFEST_SHA256
    )
    assert self_entry["byte_count"] == -1
    assert self_entry["row_count"] == -1


def test_writer_is_deterministic_across_runs(tmp_path: Path):
    result = _build_review_packet_result()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    write_review_packet_artifacts(result, dir_a)
    write_review_packet_artifacts(result, dir_b)
    for basename in c.STAGE26_REVIEW_PACKET_ARTIFACT_FILENAMES:
        a_bytes = (dir_a / basename).read_bytes()
        b_bytes = (dir_b / basename).read_bytes()
        assert a_bytes == b_bytes, (
            f"{basename}: writer produced non-deterministic output"
        )


# ---------------------------------------------------------------------------
# Output-dir validation
# ---------------------------------------------------------------------------


def test_writer_refuses_missing_output_dir(tmp_path: Path):
    result = _build_review_packet_result()
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        write_review_packet_artifacts(result, missing_dir)
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID"
    )


def test_writer_refuses_file_as_output_dir(tmp_path: Path):
    result = _build_review_packet_result()
    file_path = tmp_path / "afile"
    file_path.write_bytes(b"")
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        write_review_packet_artifacts(result, file_path)
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID"
    )


def test_writer_refuses_non_path_output_dir():
    result = _build_review_packet_result()
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        write_review_packet_artifacts(result, "/tmp/somewhere")  # type: ignore[arg-type]
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_OUTPUT_DIR_INVALID"
    )


# ---------------------------------------------------------------------------
# Redaction sweep
# ---------------------------------------------------------------------------


def test_writer_redaction_sweep_catches_api_key_in_reason(tmp_path: Path):
    # Embed an api_key fragment into the policy candidate's reason
    # via the upstream Stage 26.5 candidate's reason field; the
    # builder copies that into the review candidate's caveat_summary.
    bad_policy = _policy_candidate()._replace(
        reason="evidence carries api_key=hunter2 fragment",
    )
    result = build_review_packet(
        _policy_build_result((bad_policy,)),
        default_review_packet_config(),
    )
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        write_review_packet_artifacts(result, tmp_path)
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_REDACTION_FAILED"
    )


def test_writer_redaction_sweep_catches_webhook_url(tmp_path: Path):
    bad_policy = _policy_candidate()._replace(
        reason="cleared via " + "h" + "ttps://discord" + ".com/api",
    )
    result = build_review_packet(
        _policy_build_result((bad_policy,)),
        default_review_packet_config(),
    )
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        write_review_packet_artifacts(result, tmp_path)
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_REDACTION_FAILED"
    )


def test_writer_redaction_sweep_catches_runtime_consumable_leak(
    tmp_path: Path,
):
    bad_policy = _policy_candidate()._replace(
        reason="hint: runtime_consumable=true",
    )
    result = build_review_packet(
        _policy_build_result((bad_policy,)),
        default_review_packet_config(),
    )
    with pytest.raises(Stage26ReviewPacketError) as excinfo:
        write_review_packet_artifacts(result, tmp_path)
    assert (
        excinfo.value.error_code
        == "STG26_CAL_REVIEW_PACKET_REDACTION_FAILED"
    )


# ---------------------------------------------------------------------------
# Manifest body confirms locked tokens
# ---------------------------------------------------------------------------


def test_writer_manifest_body_includes_review_only_marker(tmp_path: Path):
    result = _build_review_packet_result()
    write_review_packet_artifacts(result, tmp_path)
    manifest_path = (
        tmp_path / c.STAGE26_OPERATOR_REVIEW_MANIFEST_FILENAME
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert (
        manifest["review_only_mode"]
        == c.STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE
    )
    assert (
        manifest["redaction_confirmed"]
        == c.STAGE26_REVIEW_PACKET_REDACTION_CONFIRMED_TOKEN
    )
    assert manifest["stage25_manifest_hash"] == _MANIFEST_HASH
    assert (
        manifest["stage26_review_packet_version"]
        == c.STAGE26_REVIEW_PACKET_VERSION
    )


def test_writer_packet_body_includes_pending_handoff(tmp_path: Path):
    result = _build_review_packet_result()
    write_review_packet_artifacts(result, tmp_path)
    packet_path = (
        tmp_path / c.STAGE26_OPERATOR_REVIEW_PACKET_FILENAME
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert (
        packet["approval_handoff_status"]
        == c.APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    )
    handoff = packet["approval_handoff"]
    assert handoff["approval_required"] is True
    assert (
        handoff["approval_status"]
        == c.APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    )
    assert handoff["approval_actor"] is None
    assert handoff["approval_timestamp_utc"] is None
    assert handoff["approval_notes"] is None
    assert handoff["operator_approved"] is False
    assert handoff["runtime_consumable"] is False
    assert handoff["enforcement_enabled"] is False
    assert packet["review_only"] is True
    assert packet["operator_approved"] is False
    assert packet["runtime_consumable"] is False
    assert packet["enforcement_enabled"] is False


def test_writer_summary_body_includes_review_only_marker(tmp_path: Path):
    result = _build_review_packet_result()
    write_review_packet_artifacts(result, tmp_path)
    summary_path = (
        tmp_path / c.STAGE26_OPERATOR_REVIEW_SUMMARY_FILENAME
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert (
        summary["review_only_mode"]
        == c.STAGE26_REVIEW_PACKET_REVIEW_ONLY_MODE
    )
    assert summary["stage25_manifest_hash"] == _MANIFEST_HASH


# ---------------------------------------------------------------------------
# Empty build
# ---------------------------------------------------------------------------


def test_writer_handles_empty_review_candidates(tmp_path: Path):
    result = build_review_packet(
        _policy_build_result(()),
        default_review_packet_config(),
    )
    artifact_set = write_review_packet_artifacts(result, tmp_path)
    # Empty JSONL is zero bytes (no trailing newline) per the
    # writer's canonical-JSONL contract.
    rows_path = (
        tmp_path / c.STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME
    )
    assert rows_path.read_bytes() == b""
    rows_ref = next(
        ref
        for ref in artifact_set.artifact_references
        if ref.basename
        == c.STAGE26_OPERATOR_REVIEW_CANDIDATES_FILENAME
    )
    assert rows_ref.row_count == 0
    assert rows_ref.byte_count == 0
