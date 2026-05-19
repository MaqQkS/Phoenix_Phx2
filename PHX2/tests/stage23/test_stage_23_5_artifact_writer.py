"""Stage 23.5 deterministic artifact writer tests.

Pins the contract of
``PHX2.stage23.artifact_writer.write_stage23_artifacts``:

  * Writes the locked set of six artifact filenames.
  * Every artifact has deterministic bytes for the same
    runner result + ``created_at_utc``.
  * CSV / JSONL / manifest serialization is canonical and sorted.
  * Manifest hashes match the on-disk artifact hashes.
  * Empty input is handled deterministically.
  * Invalid output directory raises ``Stage23ManifestError``.
  * Unrelated files in the output directory are not modified.
  * Re-running with the same inputs overwrites only Stage 23
    artifacts.
  * Secret-shaped content is caught by the redaction sweep and
    raises ``Stage23ManifestError`` rather than landing on disk.
  * The writer never writes outside the operator-supplied
    output directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from PHX2.stage23.artifact_writer import (
    ALL_ARTIFACT_FILENAMES,
    ARTIFACT_FILENAME_DATA_STATUS_COUNTS,
    ARTIFACT_FILENAME_EVALUATIONS,
    ARTIFACT_FILENAME_FILTER_SUMMARY,
    ARTIFACT_FILENAME_LABEL_COUNTS,
    ARTIFACT_FILENAME_MANIFEST,
    ARTIFACT_FILENAME_REASON_CODE_COUNTS,
    NON_MANIFEST_ARTIFACT_FILENAMES,
    STAGE23_RUNNER_ARTIFACT_MANIFEST_KIND,
    Stage23ArtifactSet,
    write_stage23_artifacts,
)
from PHX2.stage23.errors import Stage23ManifestError
from PHX2.stage23.runner import run_stage23_filters
from PHX2.stage23.stage23_manifest import REDACTION_CONFIRMED_TOKEN
from PHX2.tests.stage23.fixtures.builders import (
    FIXED_CLOCK_UTC,
    make_mixed_filter_input,
    make_mixed_payload_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_default_runner(filter_inputs=None):
    if filter_inputs is None:
        filter_inputs = [
            make_mixed_filter_input(token_mint="MintA", event_id="evt_a"),
            make_mixed_filter_input(token_mint="MintB", event_id="evt_b"),
        ]
    return run_stage23_filters(
        filter_inputs=filter_inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )


def _sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Artifact filename pins
# ---------------------------------------------------------------------------


def test_artifact_filenames_are_locked():
    assert ARTIFACT_FILENAME_EVALUATIONS == "stage23_filter_evaluations.jsonl"
    assert ARTIFACT_FILENAME_FILTER_SUMMARY == "stage23_filter_summary.csv"
    assert (
        ARTIFACT_FILENAME_REASON_CODE_COUNTS
        == "stage23_reason_code_counts.csv"
    )
    assert (
        ARTIFACT_FILENAME_DATA_STATUS_COUNTS
        == "stage23_data_status_counts.csv"
    )
    assert ARTIFACT_FILENAME_LABEL_COUNTS == "stage23_label_counts.csv"
    assert ARTIFACT_FILENAME_MANIFEST == "stage23_manifest.json"


def test_all_artifact_filenames_set_is_locked():
    assert ALL_ARTIFACT_FILENAMES == (
        "stage23_data_status_counts.csv",
        "stage23_filter_evaluations.jsonl",
        "stage23_filter_summary.csv",
        "stage23_label_counts.csv",
        "stage23_manifest.json",
        "stage23_reason_code_counts.csv",
    )


def test_non_manifest_artifact_filenames_set_is_locked():
    assert NON_MANIFEST_ARTIFACT_FILENAMES == (
        "stage23_data_status_counts.csv",
        "stage23_filter_evaluations.jsonl",
        "stage23_filter_summary.csv",
        "stage23_label_counts.csv",
        "stage23_reason_code_counts.csv",
    )


# ---------------------------------------------------------------------------
# Basic write path
# ---------------------------------------------------------------------------


def test_writer_writes_all_six_artifact_files(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for basename in ALL_ARTIFACT_FILENAMES:
        path = tmp_path / basename
        assert path.is_file(), f"missing artifact {basename!r}"


def test_writer_returns_stage23_artifact_set(tmp_path):
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert isinstance(artifact_set, Stage23ArtifactSet)
    assert artifact_set.output_dir == tmp_path
    assert artifact_set.manifest_path == tmp_path / ARTIFACT_FILENAME_MANIFEST
    assert artifact_set.redaction_confirmed == REDACTION_CONFIRMED_TOKEN


def test_writer_artifact_paths_cover_all_filenames(tmp_path):
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert set(artifact_set.artifact_paths.keys()) == set(
        ALL_ARTIFACT_FILENAMES
    )


# ---------------------------------------------------------------------------
# Determinism: same runner result + timestamp -> identical bytes
# ---------------------------------------------------------------------------


def test_repeated_writes_produce_byte_identical_files(tmp_path):
    runner_result = _run_default_runner()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=dir_a,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=dir_b,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for basename in ALL_ARTIFACT_FILENAMES:
        assert (dir_a / basename).read_bytes() == (
            dir_b / basename
        ).read_bytes(), f"non-deterministic bytes in {basename!r}"


def test_artifact_hashes_match_on_disk_bytes(tmp_path):
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for basename, expected_hash in artifact_set.artifact_hashes.items():
        path = tmp_path / basename
        actual_hash = _sha256_bytes(path)
        assert actual_hash == expected_hash, (
            f"hash mismatch for {basename!r}"
        )


# ---------------------------------------------------------------------------
# JSONL determinism
# ---------------------------------------------------------------------------


def test_jsonl_row_count_matches_evaluation_count(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    jsonl_path = tmp_path / ARTIFACT_FILENAME_EVALUATIONS
    text = jsonl_path.read_text(encoding="utf-8")
    line_count = text.count("\n")
    assert line_count == runner_result.evaluation_count


def test_jsonl_rows_are_sorted_by_evaluation_order(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    jsonl_path = tmp_path / ARTIFACT_FILENAME_EVALUATIONS
    text = jsonl_path.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines()]
    keys = [
        (
            row["token_mint"],
            row["event_id"],
            row["captured_event_id"],
            row["filter_name"],
        )
        for row in rows
    ]
    assert keys == sorted(keys)


def test_jsonl_row_keys_are_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    jsonl_path = tmp_path / ARTIFACT_FILENAME_EVALUATIONS
    text = jsonl_path.read_text(encoding="utf-8")
    expected_keys = {
        "token_mint",
        "provider_id",
        "event_id",
        "captured_event_id",
        "observed_at_utc",
        "slot",
        "signature",
        "filter_name",
        "filter_family",
        "filter_version",
        "threshold_version",
        "label",
        "data_status",
        "reason_codes",
        "numeric_features",
        "missing_features",
        "input_hash",
        "evaluation_hash",
        "created_at_utc",
    }
    for line in text.splitlines():
        row = json.loads(line)
        assert set(row.keys()) == expected_keys


# ---------------------------------------------------------------------------
# CSV determinism
# ---------------------------------------------------------------------------


def test_filter_summary_csv_header_is_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    summary_path = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    first_line = summary_path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "filter_family,filter_name,label,data_status,count"


def test_reason_code_counts_csv_header_is_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    reason_path = tmp_path / ARTIFACT_FILENAME_REASON_CODE_COUNTS
    first_line = reason_path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "filter_family,filter_name,reason_code,count"


def test_label_counts_csv_header_is_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    label_path = tmp_path / ARTIFACT_FILENAME_LABEL_COUNTS
    first_line = label_path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "filter_family,filter_name,label,count"


def test_data_status_counts_csv_header_is_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    status_path = tmp_path / ARTIFACT_FILENAME_DATA_STATUS_COUNTS
    first_line = status_path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "filter_family,filter_name,data_status,count"


def test_filter_summary_csv_rows_are_sorted(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    summary_path = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    lines = summary_path.read_text(encoding="utf-8").splitlines()
    data_rows = lines[1:]
    sorted_data_rows = sorted(data_rows)
    assert data_rows == sorted_data_rows


def test_filter_summary_csv_count_sum_matches_evaluation_count(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    summary_path = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    lines = summary_path.read_text(encoding="utf-8").splitlines()
    total = 0
    for line in lines[1:]:
        fields = line.split(",")
        total += int(fields[-1])
    assert total == runner_result.evaluation_count


def test_reason_code_counts_csv_only_contains_closed_set_reasons(tmp_path):
    """Every reason code in the CSV must be a recognized closed-set
    code emitted by one of the three filters or by the runner's
    error path.
    """
    from PHX2.stage23.holder_concentration import HOLDER_REASON_CODES
    from PHX2.stage23.launch_structure import LAUNCH_REASON_CODES
    from PHX2.stage23.runner import STAGE23_RUNNER_REASON_CODES
    from PHX2.stage23.wallet_source_quality import (
        WALLET_SOURCE_REASON_CODES,
    )

    allowed = (
        set(HOLDER_REASON_CODES)
        | set(LAUNCH_REASON_CODES)
        | set(WALLET_SOURCE_REASON_CODES)
        | set(STAGE23_RUNNER_REASON_CODES)
    )

    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    reason_path = tmp_path / ARTIFACT_FILENAME_REASON_CODE_COUNTS
    lines = reason_path.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        fields = line.split(",")
        reason_code = fields[2]
        assert reason_code in allowed, (
            f"reason code {reason_code!r} is not in any closed set"
        )


# ---------------------------------------------------------------------------
# Manifest determinism + content
# ---------------------------------------------------------------------------


def test_manifest_is_canonical_json(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    raw = manifest_path.read_text(encoding="utf-8")
    # Manifest is canonical JSON + trailing newline.
    body = json.loads(raw)
    re_canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    assert raw.rstrip("\n") == re_canon


def test_manifest_fields_are_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_keys = {
        "stage_name",
        "stage_version",
        "schema_version",
        "manifest_kind",
        "observe_only_mode",
        "redaction_confirmed",
        "created_at_utc",
        "input_count",
        "evaluation_count",
        "filter_count",
        "filter_versions",
        "threshold_versions",
        "artifacts",
        "label_counts",
        "data_status_counts",
        "reason_code_counts",
    }
    assert set(body.keys()) == expected_keys


def test_manifest_stage_identity_fields_are_locked(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert body["stage_name"] == "stage23"
    assert body["manifest_kind"] == STAGE23_RUNNER_ARTIFACT_MANIFEST_KIND
    assert body["observe_only_mode"] == "observe_only"
    assert body["redaction_confirmed"] == REDACTION_CONFIRMED_TOKEN


def test_manifest_counts_match_runner_result(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert body["input_count"] == runner_result.input_count
    assert body["evaluation_count"] == runner_result.evaluation_count
    assert body["filter_count"] == runner_result.filter_count


def test_manifest_artifact_entries_match_on_disk(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in body["artifacts"]:
        basename = entry["file_basename"]
        sha256 = entry["sha256"]
        on_disk = _sha256_bytes(tmp_path / basename)
        assert sha256 == on_disk, f"hash mismatch for {basename!r}"


def test_manifest_artifact_entries_are_sorted_by_basename(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    basenames = [entry["file_basename"] for entry in body["artifacts"]]
    assert basenames == sorted(basenames)


def test_manifest_filter_versions_cover_all_three_landed_filters(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert body["filter_versions"] == {
        "holder_concentration": "holder_concentration_v0",
        "launch_structure": "launch_structure_v0",
        "wallet_source_quality": "wallet_source_quality_v0",
    }
    assert body["threshold_versions"] == {
        "holder_concentration": "thresholds_v0_observe_only",
        "launch_structure": "thresholds_v0_observe_only",
        "wallet_source_quality": "thresholds_v0_observe_only",
    }


def test_manifest_created_at_utc_round_trips(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc="2026-07-01T12:30:00Z",
    )
    manifest_path = tmp_path / ARTIFACT_FILENAME_MANIFEST
    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert body["created_at_utc"] == "2026-07-01T12:30:00Z"


# ---------------------------------------------------------------------------
# Empty-input behavior
# ---------------------------------------------------------------------------


def test_empty_input_set_writes_artifacts_with_no_data_rows(tmp_path):
    runner_result = run_stage23_filters(
        filter_inputs=[],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    jsonl_path = tmp_path / ARTIFACT_FILENAME_EVALUATIONS
    assert jsonl_path.read_text(encoding="utf-8") == ""
    summary_path = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    assert (
        summary_path.read_text(encoding="utf-8")
        == "filter_family,filter_name,label,data_status,count\n"
    )


def test_empty_input_manifest_carries_zero_counts(tmp_path):
    runner_result = run_stage23_filters(
        filter_inputs=[],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    body = json.loads(
        (tmp_path / ARTIFACT_FILENAME_MANIFEST).read_text(encoding="utf-8")
    )
    assert body["input_count"] == 0
    assert body["evaluation_count"] == 0
    assert body["label_counts"] == {}
    assert body["data_status_counts"] == {}
    assert body["reason_code_counts"] == {}


# ---------------------------------------------------------------------------
# Output-directory validation
# ---------------------------------------------------------------------------


def test_missing_output_dir_raises_typed_error(tmp_path):
    runner_result = _run_default_runner()
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=nonexistent,
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_file_path_as_output_dir_raises_typed_error(tmp_path):
    runner_result = _run_default_runner()
    file_path = tmp_path / "regular_file.txt"
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=file_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_non_path_output_dir_raises_typed_error(tmp_path):
    runner_result = _run_default_runner()
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=str(tmp_path),  # type: ignore[arg-type]
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_empty_created_at_utc_raises_typed_error(tmp_path):
    runner_result = _run_default_runner()
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc="",
        )


# ---------------------------------------------------------------------------
# Unrelated-file safety
# ---------------------------------------------------------------------------


def test_existing_unrelated_file_is_not_modified(tmp_path):
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("preserved content", encoding="utf-8")
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert unrelated.read_text(encoding="utf-8") == "preserved content"


def test_existing_unrelated_subdirectory_is_not_touched(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    inner = sub / "inner.txt"
    inner.write_text("inner content", encoding="utf-8")
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert inner.read_text(encoding="utf-8") == "inner content"


# ---------------------------------------------------------------------------
# Re-run behavior
# ---------------------------------------------------------------------------


def test_rerun_overwrites_stage23_artifacts(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    initial_bytes = {
        basename: (tmp_path / basename).read_bytes()
        for basename in ALL_ARTIFACT_FILENAMES
    }
    # Modify inputs and re-run; artifact bytes must change.
    new_inputs = [
        make_mixed_filter_input(token_mint="MintDifferent", event_id="evt_x"),
    ]
    new_result = run_stage23_filters(
        filter_inputs=new_inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    write_stage23_artifacts(
        runner_result=new_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    new_bytes = {
        basename: (tmp_path / basename).read_bytes()
        for basename in ALL_ARTIFACT_FILENAMES
    }
    # The evaluations file MUST differ (different input).
    assert (
        initial_bytes[ARTIFACT_FILENAME_EVALUATIONS]
        != new_bytes[ARTIFACT_FILENAME_EVALUATIONS]
    )


def test_rerun_with_same_inputs_is_byte_identical(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    bytes_first = {
        basename: (tmp_path / basename).read_bytes()
        for basename in ALL_ARTIFACT_FILENAMES
    }
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    bytes_second = {
        basename: (tmp_path / basename).read_bytes()
        for basename in ALL_ARTIFACT_FILENAMES
    }
    assert bytes_first == bytes_second


# ---------------------------------------------------------------------------
# No writes outside output dir
# ---------------------------------------------------------------------------


def test_no_writes_outside_output_dir(tmp_path):
    inner = tmp_path / "inner"
    inner.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    sentinel = sibling / "sentinel.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    sibling_files_before = sorted(p.name for p in sibling.iterdir())

    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=inner,
        created_at_utc=FIXED_CLOCK_UTC,
    )

    # Only the inner directory should have new content.
    inner_files = sorted(p.name for p in inner.iterdir())
    assert sorted(inner_files) == sorted(ALL_ARTIFACT_FILENAMES)
    # The sibling directory must be unchanged.
    sibling_files_after = sorted(p.name for p in sibling.iterdir())
    assert sibling_files_before == sibling_files_after
    assert sentinel.read_text(encoding="utf-8") == "untouched"


# ---------------------------------------------------------------------------
# Redaction sweep
# ---------------------------------------------------------------------------


def test_secret_shaped_token_mint_raises_manifest_error(tmp_path):
    """If somehow a URL-shape leaks into a token_mint (an upstream
    bypass), the writer's redaction sweep should catch it before
    the artifact lands on disk.
    """
    leaked_input = make_mixed_filter_input(
        token_mint="MintFixture111",
    )
    # Patch the token_mint with a URL-shape literal via NamedTuple
    # _replace -- the runner doesn't know the input has a leaked
    # value because the input reader's guards are only run at
    # ingest.
    leak_value = "h" + "ttps://example.com/path"
    leaked_input = leaked_input._replace(token_mint=leak_value)
    runner_result = run_stage23_filters(
        filter_inputs=[leaked_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_secret_shaped_value_aborts_before_any_file_written(tmp_path):
    leak_value = "h" + "ttps://example.com/leak"
    leaked_input = make_mixed_filter_input(
        token_mint=leak_value,
    )
    runner_result = run_stage23_filters(
        filter_inputs=[leaked_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    # The writer should abort before writing ANY artifact.
    assert sorted(p.name for p in tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Schema version + manifest kind pins
# ---------------------------------------------------------------------------


def test_manifest_kind_is_stage23_runner_artifact(tmp_path):
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    body = json.loads(
        (tmp_path / ARTIFACT_FILENAME_MANIFEST).read_text(encoding="utf-8")
    )
    assert body["manifest_kind"] == "stage23_runner_artifact"


# ---------------------------------------------------------------------------
# Hash field surface
# ---------------------------------------------------------------------------


def test_artifact_set_hashes_include_manifest_hash(tmp_path):
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert ARTIFACT_FILENAME_MANIFEST in artifact_set.artifact_hashes
    manifest_disk_hash = _sha256_bytes(
        tmp_path / ARTIFACT_FILENAME_MANIFEST
    )
    assert (
        artifact_set.artifact_hashes[ARTIFACT_FILENAME_MANIFEST]
        == manifest_disk_hash
    )


def test_artifact_set_row_counts_for_jsonl_equals_evaluation_count(tmp_path):
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert (
        artifact_set.artifact_row_counts[ARTIFACT_FILENAME_EVALUATIONS]
        == runner_result.evaluation_count
    )


def test_artifact_set_row_counts_for_manifest_is_minus_one(tmp_path):
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert (
        artifact_set.artifact_row_counts[ARTIFACT_FILENAME_MANIFEST]
        == -1
    )


# ---------------------------------------------------------------------------
# Stage 23.6: writer redaction bypass coverage
# ---------------------------------------------------------------------------
#
# The writer must reject a Stage23FilterInput whose user-controllable
# string fields carry a long hex / tokenish / env-name leak shape,
# even if the input bypassed the Stage 23 input reader at ingest.


def test_writer_rejects_long_hex_token_in_signature(tmp_path):
    """A 40-character hex run in a string field must abort the write."""
    leaked_input = make_mixed_filter_input(
        token_mint="MintFixture111",
    )
    forty_char_hex = "a" * 40
    leaked_input = leaked_input._replace(signature=forty_char_hex)
    runner_result = run_stage23_filters(
        filter_inputs=[leaked_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    # No artifacts should land on disk.
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_writer_rejects_long_tokenish_api_key_value_in_event_id(tmp_path):
    """A 32-character API-key-shaped string must abort the write."""
    leaked_input = make_mixed_filter_input(
        token_mint="MintFixture111",
    )
    # 36 chars, mixed letters + digits, dense alnum content.
    tokenish_value = "ab12CD34ef56GH78ij90KL12mn34OP56qr78"
    leaked_input = leaked_input._replace(event_id=tokenish_value)
    runner_result = run_stage23_filters(
        filter_inputs=[leaked_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_writer_rejects_env_style_name_embedded_in_value(tmp_path):
    """A value carrying an embedded env-style sensitive name (api_key
    / webhook / password / secret) must abort the write.
    """
    leaked_input = make_mixed_filter_input(
        token_mint="some_api_key_lurking_here",
    )
    runner_result = run_stage23_filters(
        filter_inputs=[leaked_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_writer_rejects_long_hex_token_in_payload_summary_value(tmp_path):
    """A long hex run smuggled into payload_summary must be caught
    before any byte lands on disk.
    """
    from types import MappingProxyType as _MPT

    leaked_payload = _MPT(
        {
            "leaked_marker": "f" * 40,
        }
    )
    leaked_input = make_mixed_filter_input(
        token_mint="MintFixture111",
        payload_summary=leaked_payload,
    )
    runner_result = run_stage23_filters(
        filter_inputs=[leaked_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    assert sorted(p.name for p in tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Stage 23.6: writer path safety
# ---------------------------------------------------------------------------


def test_writer_rejects_existing_symlink_at_artifact_path(tmp_path):
    """If a symlink already exists at one of the locked artifact
    target paths, the writer must raise ``Stage23ManifestError``
    and refuse to follow the symlink.
    """
    runner_result = _run_default_runner()
    # Create a target for the symlink and the symlink itself at one
    # of the locked artifact names.
    target_file = tmp_path / "outside_target.txt"
    target_file.write_text("outside content", encoding="utf-8")
    artifact_link = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    try:
        artifact_link.symlink_to(target_file)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    # The symlink target must remain unmodified.
    assert target_file.read_text(encoding="utf-8") == "outside content"


def test_writer_rejects_existing_directory_at_artifact_path(tmp_path):
    """If a directory already occupies an artifact filename, the
    writer must reject the run with a typed error.
    """
    runner_result = _run_default_runner()
    artifact_dir = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    artifact_dir.mkdir()
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_writer_rejects_hardlinked_target_when_supported(tmp_path):
    """If an artifact filename is a hardlink to a file outside
    the output dir, the writer must refuse to overwrite it.

    Skip the test if ``st_nlink`` reports 1 even after the
    hardlink creation (some filesystems / sandboxes do not
    expose link counts).
    """
    runner_result = _run_default_runner()
    outside_file = tmp_path / "shared_target.txt"
    outside_file.write_text("shared content", encoding="utf-8")
    artifact_path = tmp_path / ARTIFACT_FILENAME_FILTER_SUMMARY
    try:
        os.link(outside_file, artifact_path)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("hardlink creation not supported on this platform")
    if artifact_path.stat().st_nlink <= 1:
        pytest.skip("filesystem does not report st_nlink > 1 for hardlinks")
    with pytest.raises(Stage23ManifestError):
        write_stage23_artifacts(
            runner_result=runner_result,
            output_dir=tmp_path,
            created_at_utc=FIXED_CLOCK_UTC,
        )
    # The original target's content stays intact.
    assert outside_file.read_text(encoding="utf-8") == "shared content"


def test_writer_leaves_unrelated_files_intact_alongside_normal_write(tmp_path):
    """Unrelated pre-existing files in the output dir must survive
    a successful write.
    """
    unrelated = tmp_path / "operator_notes.md"
    unrelated.write_text("operator notes", encoding="utf-8")
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert unrelated.read_text(encoding="utf-8") == "operator notes"


def test_writer_does_not_leave_temp_file_on_disk_after_success(tmp_path):
    """Atomic-rename via temp file must not leave a ``.tmp`` artifact
    behind after a successful write.
    """
    runner_result = _run_default_runner()
    write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    tmp_files = [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert tmp_files == [], (
        f"temp artifacts left on disk after successful write: {tmp_files}"
    )


def test_writer_normal_write_still_succeeds_after_path_safety_pass(tmp_path):
    """The path-safety pass must not regress the normal-write path."""
    runner_result = _run_default_runner()
    artifact_set = write_stage23_artifacts(
        runner_result=runner_result,
        output_dir=tmp_path,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for basename in ALL_ARTIFACT_FILENAMES:
        path = tmp_path / basename
        assert path.is_file(), f"artifact {basename!r} did not land on disk"
    assert artifact_set.redaction_confirmed == REDACTION_CONFIRMED_TOKEN
