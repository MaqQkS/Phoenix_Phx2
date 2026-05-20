"""Stage 24.6 artifact writer tests.

Pins:

  * Writes the eleven locked Stage 24.6 artifact filenames into
    a caller-supplied directory.
  * JSONL bodies are deterministic byte-for-byte across two
    runs over the same inputs and injected clock.
  * Manifest row counts and sha256 hashes match the files on
    disk.
  * Summary counters match the runner result.
  * Decoder coverage CSV is deterministic and sorted.
  * Router-fee candidates are emitted separately from confirmed
    router-fee results.
  * Confirmed router-fee results file is empty at Stage 24.6
    (Path B lock).
  * Manifest carries the Stage 24.5 lock markers.
  * Redaction sweep rejects unsafe value shapes.
  * Unsafe output paths (missing / not a directory / symlink)
    are rejected.
  * Atomic write: a leftover ``.tmp`` from an aborted run is
    cleaned up before the final write.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from PHX2.stage24.artifact_writer import (
    Stage24ArtifactFileRecord,
    Stage24ArtifactSet,
    Stage24WriterError,
    write_stage24_artifacts,
)
from PHX2.stage24.constants import (
    ALL_STAGE24_ARTIFACT_FILENAMES,
    ARTIFACT_FILENAME_DECODER_COVERAGE,
    ARTIFACT_FILENAME_EXECUTION_PRIMITIVES,
    ARTIFACT_FILENAME_MANIFEST,
    ARTIFACT_FILENAME_REJECTIONS,
    ARTIFACT_FILENAME_ROUTER_FEE_CANDIDATES,
    ARTIFACT_FILENAME_ROUTER_FEE_RESULTS,
    ARTIFACT_FILENAME_SUMMARY,
    STAGE_24_5_CONFIRMED_LAYOUT_COUNT,
    STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER,
    STAGE_24_5_REAL_FIXTURE_COUNT,
)
from PHX2.stage24.runner import (
    Stage24RejectionRecord,
    run_stage24_decoders,
)
from PHX2.tests.stage24.fixtures.builders import (
    FIXED_CLOCK_UTC,
    make_axiom_flashx8_instruction,
    make_compute_budget_set_unit_limit_instruction,
    make_compute_budget_set_unit_price_instruction,
    make_execution_input,
    make_jito_tip_instruction,
    make_router_like_execution_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _two_input_runner_result():
    plain = make_execution_input(
        signature="sig_writer_plain_001",
        top_level_instructions=(
            make_compute_budget_set_unit_limit_instruction(units=200_000),
            make_compute_budget_set_unit_price_instruction(
                micro_lamports_per_compute_unit=1_000,
            ),
            make_jito_tip_instruction(lamports=20_000),
        ),
        meta=MappingProxyType(
            {"compute_units_consumed": 50_000, "fee": 5000}
        ),
    )
    router_candidate = make_router_like_execution_input(
        signature="sig_writer_router_001",
        top_level_instructions=(make_axiom_flashx8_instruction(),),
    )
    return run_stage24_decoders(
        execution_inputs=(plain, router_candidate),
        created_at_utc=FIXED_CLOCK_UTC,
    )


def _read_jsonl(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if text == "":
        return []
    return [json.loads(line) for line in text.splitlines() if line]


# ---------------------------------------------------------------------------
# Writes all locked filenames
# ---------------------------------------------------------------------------


def test_writer_emits_every_locked_artifact_file(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    artifact_set = write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    on_disk = sorted(p.name for p in tmp_path.iterdir())
    assert set(ALL_STAGE24_ARTIFACT_FILENAMES).issubset(set(on_disk))
    written = {r.file_basename for r in artifact_set.artifact_records}
    assert written == set(ALL_STAGE24_ARTIFACT_FILENAMES)


def test_writer_returns_artifact_set(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    artifact_set = write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert isinstance(artifact_set, Stage24ArtifactSet)
    for record in artifact_set.artifact_records:
        assert isinstance(record, Stage24ArtifactFileRecord)


# ---------------------------------------------------------------------------
# Determinism: identical input + clock -> identical bytes
# ---------------------------------------------------------------------------


def test_writer_is_byte_deterministic_across_runs(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    write_stage24_artifacts(
        output_dir=dir_a,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    write_stage24_artifacts(
        output_dir=dir_b,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for filename in ALL_STAGE24_ARTIFACT_FILENAMES:
        bytes_a = (dir_a / filename).read_bytes()
        bytes_b = (dir_b / filename).read_bytes()
        assert bytes_a == bytes_b, (
            f"non-deterministic content for {filename}"
        )


# ---------------------------------------------------------------------------
# Manifest row counts and sha256 match files
# ---------------------------------------------------------------------------


def test_manifest_row_counts_and_hashes_match_files_on_disk(
    tmp_path: Path,
):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest = json.loads(
        (tmp_path / ARTIFACT_FILENAME_MANIFEST).read_text(
            encoding="utf-8"
        )
    )
    entries_by_name = {e["file_basename"]: e for e in manifest["files"]}
    for filename in ALL_STAGE24_ARTIFACT_FILENAMES:
        if filename == ARTIFACT_FILENAME_MANIFEST:
            # Manifest covers other artifacts; it does not list
            # itself in its own files block.
            assert filename not in entries_by_name
            continue
        path = tmp_path / filename
        entry = entries_by_name[filename]
        on_disk_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["sha256"] == on_disk_hash
        assert entry["bytes_written"] == path.stat().st_size


# ---------------------------------------------------------------------------
# Summary counters match runner result
# ---------------------------------------------------------------------------


def test_summary_counters_match_runner_result(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    summary = json.loads(
        (tmp_path / ARTIFACT_FILENAME_SUMMARY).read_text(
            encoding="utf-8"
        )
    )
    assert summary["input_count"] == runner_result.input_count
    assert summary["compute_budget_result_count"] == len(
        runner_result.compute_budget_results
    )
    assert summary["priority_fee_result_count"] == len(
        runner_result.priority_fee_results
    )
    assert summary["jito_tip_result_count"] == len(
        runner_result.jito_tip_results
    )
    assert summary["execution_quality_result_count"] == len(
        runner_result.execution_quality_results
    )
    assert summary["execution_primitive_count"] == len(
        runner_result.execution_primitives
    )
    assert summary["rejection_count"] == len(rejections)


# ---------------------------------------------------------------------------
# Decoder coverage CSV is deterministic and sorted
# ---------------------------------------------------------------------------


def test_decoder_coverage_csv_is_deterministic_and_sorted(
    tmp_path: Path,
):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    text = (tmp_path / ARTIFACT_FILENAME_DECODER_COVERAGE).read_text(
        encoding="utf-8"
    )
    lines = text.splitlines()
    assert lines[0] == "primitive_family,decoder_status,data_status,row_count"
    body = lines[1:]
    parsed_keys = [tuple(line.split(",")[:3]) for line in body]
    assert parsed_keys == sorted(parsed_keys)


# ---------------------------------------------------------------------------
# Router-fee partitioning
# ---------------------------------------------------------------------------


def test_router_fee_candidates_emitted_separately_from_results(
    tmp_path: Path,
):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    confirmed_rows = _read_jsonl(
        tmp_path / ARTIFACT_FILENAME_ROUTER_FEE_RESULTS
    )
    candidate_rows = _read_jsonl(
        tmp_path / ARTIFACT_FILENAME_ROUTER_FEE_CANDIDATES
    )
    # Stage 24.5 Path B: no confirmed router-fee rows ever.
    assert confirmed_rows == []
    # At least one candidate (the FLASHX8 + ABSENT pair).
    assert len(candidate_rows) >= 1


def test_router_fee_results_file_amount_lamports_field_unused(
    tmp_path: Path,
):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    confirmed_rows = _read_jsonl(
        tmp_path / ARTIFACT_FILENAME_ROUTER_FEE_RESULTS
    )
    # Stage 24.5 Path B: file is empty.
    assert confirmed_rows == []
    # All candidate rows have amount_lamports None too.
    candidate_rows = _read_jsonl(
        tmp_path / ARTIFACT_FILENAME_ROUTER_FEE_CANDIDATES
    )
    for row in candidate_rows:
        assert row["amount_lamports"] is None
        assert row["amount_token"] is None


# ---------------------------------------------------------------------------
# Manifest carries Stage 24.5 lock markers
# ---------------------------------------------------------------------------


def test_manifest_includes_stage_24_5_lock_values(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    manifest = json.loads(
        (tmp_path / ARTIFACT_FILENAME_MANIFEST).read_text(
            encoding="utf-8"
        )
    )
    assert (
        manifest["stage_24_5_has_confirmed_router_fee_decoder"]
        == STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER
    )
    assert (
        manifest["stage_24_5_real_fixture_count"]
        == STAGE_24_5_REAL_FIXTURE_COUNT
    )
    assert (
        manifest["stage_24_5_confirmed_layout_count"]
        == STAGE_24_5_CONFIRMED_LAYOUT_COUNT
    )


# ---------------------------------------------------------------------------
# Redaction sweep rejects unsafe values
# ---------------------------------------------------------------------------


def test_writer_rejects_url_shape_in_summary(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    # Inject a poisoned rejection record that carries an unsafe
    # error_class value.
    poisoned = Stage24RejectionRecord(
        input_id="sig_writer_plain_001",
        payload_hash="x" * 64,
        decoder_name="compute_budget",
        primitive_family="COMPUTE_BUDGET",
        reason="DECODER_TYPED_ERROR",
        error_class="https" + "://leaky.example/" + "Error",
    )
    with pytest.raises(Stage24WriterError):
        write_stage24_artifacts(
            output_dir=tmp_path,
            runner_result=runner_result,
            rejections=(poisoned,),
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_writer_rejects_long_hex_run_in_non_hash_field(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    # ``error_class`` is NOT a writer-computed hash field, so a
    # long-hex-run there should trigger the leak-shape detector
    # even though the same shape inside ``payload_hash`` /
    # ``input_hash`` / ``sha256`` is whitelisted.
    poisoned = Stage24RejectionRecord(
        input_id="sig_writer_plain_001",
        payload_hash="payload_hash_token",
        decoder_name="compute_budget",
        primitive_family="COMPUTE_BUDGET",
        reason="DECODER_TYPED_ERROR",
        # 60 contiguous hex characters: long-hex-run shape.
        error_class="abcdef" * 11,
    )
    with pytest.raises(Stage24WriterError):
        write_stage24_artifacts(
            output_dir=tmp_path,
            runner_result=runner_result,
            rejections=(poisoned,),
            created_at_utc=FIXED_CLOCK_UTC,
        )


# ---------------------------------------------------------------------------
# Unsafe output paths
# ---------------------------------------------------------------------------


def test_writer_rejects_nonexistent_output_dir(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(Stage24WriterError):
        write_stage24_artifacts(
            output_dir=nonexistent,
            runner_result=runner_result,
            rejections=rejections,
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_writer_rejects_file_path_as_output_dir(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_bytes(b"hello")
    with pytest.raises(Stage24WriterError):
        write_stage24_artifacts(
            output_dir=file_path,
            runner_result=runner_result,
            rejections=rejections,
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_writer_rejects_non_path_output_dir(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    with pytest.raises(Stage24WriterError):
        write_stage24_artifacts(
            output_dir=str(tmp_path),  # type: ignore[arg-type]
            runner_result=runner_result,
            rejections=rejections,
            created_at_utc=FIXED_CLOCK_UTC,
        )


# ---------------------------------------------------------------------------
# Atomic write: leftover .tmp gets cleaned up
# ---------------------------------------------------------------------------


def test_writer_cleans_up_leftover_temp_file(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    # Simulate a leftover .tmp from a prior aborted run.
    leftover_temp = tmp_path / (ARTIFACT_FILENAME_SUMMARY + ".tmp")
    leftover_temp.write_bytes(b"stale-content")
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    # The leftover temp file is gone (replaced -> final name).
    assert not leftover_temp.exists()
    # The final artifact is written and parseable.
    summary = json.loads(
        (tmp_path / ARTIFACT_FILENAME_SUMMARY).read_text(
            encoding="utf-8"
        )
    )
    assert "input_count" in summary


# ---------------------------------------------------------------------------
# Empty input produces empty artifact rows
# ---------------------------------------------------------------------------


def test_writer_handles_zero_input_run(tmp_path: Path):
    runner_result, rejections = run_stage24_decoders(
        execution_inputs=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    artifact_set = write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    # Manifest still written.
    assert (tmp_path / ARTIFACT_FILENAME_MANIFEST).is_file()
    # All JSONL data files are empty (no data rows).
    for filename in ALL_STAGE24_ARTIFACT_FILENAMES:
        if filename in (
            ARTIFACT_FILENAME_MANIFEST,
            ARTIFACT_FILENAME_SUMMARY,
            ARTIFACT_FILENAME_DECODER_COVERAGE,
        ):
            continue
        text = (tmp_path / filename).read_text(encoding="utf-8")
        assert text == ""
    # Summary recorded zero counts.
    summary = json.loads(
        (tmp_path / ARTIFACT_FILENAME_SUMMARY).read_text(
            encoding="utf-8"
        )
    )
    assert summary["input_count"] == 0
    assert summary["execution_primitive_count"] == 0
    # Records carried back to caller, all 11 filenames.
    assert len(artifact_set.artifact_records) == 11


# ---------------------------------------------------------------------------
# Execution primitives sort order
# ---------------------------------------------------------------------------


def test_execution_primitives_are_sorted_by_signature_family_source(
    tmp_path: Path,
):
    runner_result, rejections = _two_input_runner_result()
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    rows = _read_jsonl(tmp_path / ARTIFACT_FILENAME_EXECUTION_PRIMITIVES)
    keys = [
        (r["tx_signature"], r["primitive_family"], r["fee_source"])
        for r in rows
    ]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Rejection emission
# ---------------------------------------------------------------------------


def test_rejection_rows_round_trip_through_artifact(tmp_path: Path):
    runner_result, _ = _two_input_runner_result()
    rejection = Stage24RejectionRecord(
        input_id="sig_writer_plain_001",
        payload_hash="payload_hash_token",
        decoder_name="compute_budget",
        primitive_family="COMPUTE_BUDGET",
        reason="DECODER_TYPED_ERROR",
        error_class="Stage24DecoderError",
    )
    write_stage24_artifacts(
        output_dir=tmp_path,
        runner_result=runner_result,
        rejections=(rejection,),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    rows = _read_jsonl(tmp_path / ARTIFACT_FILENAME_REJECTIONS)
    assert len(rows) == 1
    assert rows[0]["decoder_name"] == "compute_budget"
    assert rows[0]["reason"] == "DECODER_TYPED_ERROR"
    assert rows[0]["error_class"] == "Stage24DecoderError"


# ---------------------------------------------------------------------------
# Cross-run hash stability for a single file
# ---------------------------------------------------------------------------


def test_manifest_hash_is_stable_across_runs(tmp_path: Path):
    runner_result, rejections = _two_input_runner_result()
    dir_a = tmp_path / "ra"
    dir_b = tmp_path / "rb"
    dir_a.mkdir()
    dir_b.mkdir()
    set_a = write_stage24_artifacts(
        output_dir=dir_a,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    set_b = write_stage24_artifacts(
        output_dir=dir_b,
        runner_result=runner_result,
        rejections=rejections,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    by_name_a = {r.file_basename: r.sha256 for r in set_a.artifact_records}
    by_name_b = {r.file_basename: r.sha256 for r in set_b.artifact_records}
    assert by_name_a == by_name_b
