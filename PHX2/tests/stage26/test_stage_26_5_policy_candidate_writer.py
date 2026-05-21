"""Stage 26.5 policy candidate writer behavior tests.

The tests use synthetic Stage 26.4 ``Stage26ThresholdCandidateSet``
inputs (via the Stage 26.5 builder) and a pytest ``tmp_path`` to
exercise the deterministic offline writer. The writer must NEVER
touch live Stage 25 artifacts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from PHX2.stage26 import policy_candidate_constants as c
from PHX2.stage26.cohort_models import Stage26CohortKey
from PHX2.stage26.errors import Stage26PolicyCandidateError
from PHX2.stage26.policy_candidate_builder import (
    build_policy_candidates,
    default_policy_candidate_config,
)
from PHX2.stage26.policy_candidate_writer import (
    write_policy_candidate_artifacts,
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


def _evidence(key: Stage26CohortKey) -> Stage26ThresholdEvidenceSummary:
    return Stage26ThresholdEvidenceSummary(
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
        coverage_gap_rate=0.0,
        scope_gap_rate=0.0,
        rejection_rate=0.0,
        source_conflict_rate=0.0,
        ambiguous_rate=0.0,
        observability_rate=1.0,
        stage25_manifest_hash="manifest_sha_abc",
    )


def _threshold(
    *,
    values: tuple[str, ...] = ("MEASURED",),
    candidate_kind: str = "MIN_PRIMARY_MEASURED_COUNT",
    reason: str = "cleared",
) -> Stage26ThresholdCandidate:
    key = Stage26CohortKey(
        dimensions=("MEASUREMENT_TRUTH_CLASS",),
        values=values,
    )
    return Stage26ThresholdCandidate(
        candidate_id=f"{'|'.join(values)}#{candidate_kind}",
        cohort_key=key,
        candidate_kind=candidate_kind,
        threshold_direction="MINIMUM",
        threshold_value=1.0,
        observed_value=2.0,
        candidate_status="CANDIDATE_ONLY",
        evidence_class="PRIMARY_MEASURED_EVIDENCE",
        review_readiness="READY_FOR_POLICY_CANDIDATE_REVIEW",
        reason=reason,
        evidence_summary=_evidence(key),
        candidate_only=True,
        operator_approved=False,
        runtime_consumable=False,
        stage25_manifest_hash="manifest_sha_abc",
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
) -> Stage26ThresholdCandidateSet:
    return Stage26ThresholdCandidateSet(
        stage26_threshold_version=STAGE26_THRESHOLD_VERSION,
        deterministic_ordering_version=(
            STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
        ),
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
        stage25_manifest_hash="manifest_sha_abc",
        config=_threshold_config(),
        candidates=candidates,
        total_candidates=len(candidates),
        ready_for_review_count=len(candidates),
        insufficient_measured_count=0,
        suppressed_count=0,
        invalid_cohort_count=0,
    )


def _build_default_result():
    inputs = (
        _threshold(values=("MEASURED",)),
        _threshold(
            values=("MEASURED",),
            candidate_kind="MIN_THRESHOLD_ELIGIBLE_COUNT",
        ),
    )
    return build_policy_candidates(
        _candidate_set(inputs), default_policy_candidate_config()
    )


# ---------------------------------------------------------------------------
# Happy-path writer behavior
# ---------------------------------------------------------------------------


def test_writer_emits_three_locked_basenames(tmp_path: Path):
    result = _build_default_result()
    artifact_set = write_policy_candidate_artifacts(result, tmp_path)
    on_disk = sorted(p.name for p in tmp_path.iterdir())
    assert on_disk == [
        "stage26_policy_candidate_manifest.json",
        "stage26_policy_candidate_summary.json",
        "stage26_policy_candidates.jsonl",
    ]
    assert artifact_set.output_dir == str(tmp_path)
    assert artifact_set.redaction_confirmed is True


def test_writer_jsonl_rows_match_candidate_count(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    rows_text = (
        tmp_path / "stage26_policy_candidates.jsonl"
    ).read_text(encoding="utf-8")
    line_count = sum(
        1 for line in rows_text.split("\n") if line.strip() != ""
    )
    assert line_count == len(result.policy_candidates)


def test_writer_jsonl_rows_are_canonical_json(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    rows_text = (
        tmp_path / "stage26_policy_candidates.jsonl"
    ).read_text(encoding="utf-8")
    for line in rows_text.split("\n"):
        if line.strip() == "":
            continue
        parsed = json.loads(line)
        # Canonical JSON has sorted keys and minimal separators.
        roundtrip = json.dumps(
            parsed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        assert roundtrip == line


def test_writer_summary_carries_observe_only_mode(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    summary_body = json.loads(
        (tmp_path / "stage26_policy_candidate_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary_body["observe_only_mode"] == (
        c.STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE
    )
    assert (
        summary_body["stage26_policy_candidate_version"]
        == c.STAGE26_POLICY_CANDIDATE_VERSION
    )
    assert summary_body["stage25_manifest_hash"] == "manifest_sha_abc"


def test_writer_manifest_has_self_entry_sentinel(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    manifest_body = json.loads(
        (tmp_path / "stage26_policy_candidate_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    self_entry = None
    for entry in manifest_body["files"]:
        if entry["basename"] == (
            "stage26_policy_candidate_manifest.json"
        ):
            self_entry = entry
            break
    assert self_entry is not None
    assert self_entry["sha256"] == (
        c.STAGE26_POLICY_CANDIDATE_SELF_REFERENTIAL_MANIFEST_SHA256
    )
    assert self_entry["byte_count"] == -1
    assert self_entry["row_count"] == -1


def test_writer_manifest_entries_record_real_sha256_byte_row_counts(
    tmp_path: Path,
):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    manifest_body = json.loads(
        (tmp_path / "stage26_policy_candidate_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    rows_bytes = (
        tmp_path / "stage26_policy_candidates.jsonl"
    ).read_bytes()
    summary_bytes = (
        tmp_path / "stage26_policy_candidate_summary.json"
    ).read_bytes()
    entries = {entry["basename"]: entry for entry in manifest_body["files"]}
    rows_entry = entries["stage26_policy_candidates.jsonl"]
    assert rows_entry["sha256"] == hashlib.sha256(rows_bytes).hexdigest()
    assert rows_entry["byte_count"] == len(rows_bytes)
    assert rows_entry["row_count"] == len(result.policy_candidates)
    summary_entry = entries["stage26_policy_candidate_summary.json"]
    assert summary_entry["sha256"] == hashlib.sha256(
        summary_bytes
    ).hexdigest()
    assert summary_entry["byte_count"] == len(summary_bytes)
    assert summary_entry["row_count"] == -1


def test_writer_artifact_set_records_returned_hashes(tmp_path: Path):
    result = _build_default_result()
    artifact_set = write_policy_candidate_artifacts(result, tmp_path)
    on_disk_manifest = (
        tmp_path / "stage26_policy_candidate_manifest.json"
    ).read_bytes()
    assert artifact_set.manifest_hash == hashlib.sha256(
        on_disk_manifest
    ).hexdigest()
    for ref in artifact_set.artifact_references:
        path = tmp_path / ref.basename
        assert ref.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        assert ref.byte_count == len(path.read_bytes())


def test_writer_is_deterministic(tmp_path: Path):
    result = _build_default_result()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    write_policy_candidate_artifacts(result, dir_a)
    write_policy_candidate_artifacts(result, dir_b)
    for basename in c.STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES:
        assert (dir_a / basename).read_bytes() == (
            dir_b / basename
        ).read_bytes()


# ---------------------------------------------------------------------------
# Output-dir validation
# ---------------------------------------------------------------------------


def test_writer_rejects_missing_output_dir(tmp_path: Path):
    result = _build_default_result()
    missing = tmp_path / "does_not_exist"
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, missing)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID
    )


def test_writer_rejects_non_directory_path(tmp_path: Path):
    result = _build_default_result()
    file_path = tmp_path / "not_a_dir"
    file_path.write_bytes(b"")
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, file_path)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID
    )


def test_writer_rejects_non_path_argument(tmp_path: Path):
    result = _build_default_result()
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, str(tmp_path))  # type: ignore[arg-type]
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_OUTPUT_DIR_INVALID
    )


# ---------------------------------------------------------------------------
# Redaction sweep
# ---------------------------------------------------------------------------


def test_writer_redaction_sweep_catches_fake_api_key_token(
    tmp_path: Path,
):
    threshold = _threshold(reason="leaks api_key=AKIATESTSECRETSHAPE0000")
    result = build_policy_candidates(
        _candidate_set((threshold,)),
        default_policy_candidate_config(),
    )
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, tmp_path)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED
    )


def test_writer_redaction_sweep_catches_webhook_url(tmp_path: Path):
    bad_reason = "trigger webhook " + "h" + "ttps://example.invalid/x"
    threshold = _threshold(reason=bad_reason)
    result = build_policy_candidates(
        _candidate_set((threshold,)),
        default_policy_candidate_config(),
    )
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, tmp_path)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED
    )


def test_writer_redaction_sweep_catches_discord_host(tmp_path: Path):
    bad_reason = "leak " + "discord" + ".com/path"
    threshold = _threshold(reason=bad_reason)
    result = build_policy_candidates(
        _candidate_set((threshold,)),
        default_policy_candidate_config(),
    )
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, tmp_path)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED
    )


def test_writer_redaction_sweep_catches_approval_leak_marker(
    tmp_path: Path,
):
    threshold = _threshold(reason="hint operator_approved=true ahead")
    result = build_policy_candidates(
        _candidate_set((threshold,)),
        default_policy_candidate_config(),
    )
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, tmp_path)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED
    )


def test_writer_redaction_sweep_catches_secret_field(tmp_path: Path):
    threshold = _threshold(reason="check secret_key=ABC")
    result = build_policy_candidates(
        _candidate_set((threshold,)),
        default_policy_candidate_config(),
    )
    with pytest.raises(Stage26PolicyCandidateError) as excinfo:
        write_policy_candidate_artifacts(result, tmp_path)
    assert excinfo.value.error_code == (
        c.STG26_CAL_POLICY_CANDIDATE_REDACTION_FAILED
    )


# ---------------------------------------------------------------------------
# Locked basename + runtime guard
# ---------------------------------------------------------------------------


def test_writer_never_emits_runtime_policy_basenames(tmp_path: Path):
    """Stage 26.5 outputs must NOT carry runtime-policy fragments."""
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    for entry in tmp_path.iterdir():
        lower = entry.name.lower()
        for fragment in (
            c.STAGE26_POLICY_CANDIDATE_FORBIDDEN_RUNTIME_BASENAME_SUBSTRINGS
        ):
            assert fragment not in lower, (
                f"forbidden runtime fragment {fragment!r} in "
                f"{entry.name!r}"
            )


def test_writer_locked_basename_constants_match_filenames(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    on_disk = {p.name for p in tmp_path.iterdir()}
    assert on_disk == set(c.STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES)


# ---------------------------------------------------------------------------
# Empty candidate set
# ---------------------------------------------------------------------------


def test_writer_handles_empty_candidate_set(tmp_path: Path):
    empty_set = _candidate_set(())
    result = build_policy_candidates(
        empty_set, default_policy_candidate_config()
    )
    artifact_set = write_policy_candidate_artifacts(result, tmp_path)
    rows_bytes = (
        tmp_path / "stage26_policy_candidates.jsonl"
    ).read_bytes()
    assert rows_bytes == b""
    assert artifact_set.redaction_confirmed is True


# ---------------------------------------------------------------------------
# Manifest body discipline
# ---------------------------------------------------------------------------


def test_manifest_body_lists_all_three_basenames_sorted(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    manifest_body = json.loads(
        (tmp_path / "stage26_policy_candidate_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    basenames = [entry["basename"] for entry in manifest_body["files"]]
    assert basenames == sorted(basenames)
    assert set(basenames) == set(
        c.STAGE26_POLICY_CANDIDATE_ARTIFACT_FILENAMES
    )


def test_manifest_body_carries_pinned_versions(tmp_path: Path):
    result = _build_default_result()
    write_policy_candidate_artifacts(result, tmp_path)
    manifest_body = json.loads(
        (tmp_path / "stage26_policy_candidate_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        manifest_body["stage26_policy_candidate_version"]
        == c.STAGE26_POLICY_CANDIDATE_VERSION
    )
    assert (
        manifest_body["artifact_schema_version"]
        == c.STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION
    )
    assert manifest_body["observe_only_mode"] == (
        c.STAGE26_POLICY_CANDIDATE_OBSERVE_ONLY_MODE
    )
    assert manifest_body["redaction_confirmed"] == (
        c.STAGE26_POLICY_CANDIDATE_REDACTION_CONFIRMED_TOKEN
    )
