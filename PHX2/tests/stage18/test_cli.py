"""Phase 18.3 CLI tests.

End-to-end tests that invoke ``PHX2.stage18.cli.main`` directly
with synthesized argv. Uses the minimal Stage 17 fixture from
conftest; mutator helpers cover policy_hash filtering and
output-dir contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage18.cli import (
    EXIT_INPUT_ERROR,
    EXIT_OK,
    EXIT_RUNTIME_ERROR,
    main,
)


_EXPECTED_OUTPUT_FILES: frozenset[str] = frozenset({
    "classification_summary.csv",
    "review_matrix.csv",
    "data_quality_blockers.csv",
    "rule_review_cards.md",
    "manifest.json",
    "README.md",
    "stage18_run.log",
})


# ---------------------------------------------------------------------------
# argparse error paths
# ---------------------------------------------------------------------------


def test_missing_stage17_input_dir_arg_errors(tmp_path: Path) -> None:
    """argparse exits 2 on a missing required argument."""

    with pytest.raises(SystemExit) as exc_info:
        main(["--output-dir", str(tmp_path / "out")])
    assert exc_info.value.code == 2


def test_missing_output_dir_arg_errors(minimal_stage17_input_dir: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--stage17-input-dir", str(minimal_stage17_input_dir)])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Input contract failure paths
# ---------------------------------------------------------------------------


def test_nonexistent_stage17_input_dir_yields_b01(
    tmp_path: Path, capsys: pytest.CaptureFixture,
) -> None:
    rc = main([
        "--stage17-input-dir", str(tmp_path / "does_not_exist"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert rc == EXIT_INPUT_ERROR
    assert "B01" in capsys.readouterr().err


def test_existing_output_dir_yields_b04(
    minimal_stage17_input_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    out_dir = tmp_path / "already_exists"
    out_dir.mkdir()
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
    ])
    assert rc == EXIT_RUNTIME_ERROR
    assert "B04" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_emits_all_seven_artifacts(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK
    actual = {p.name for p in out_dir.iterdir() if p.is_file()}
    assert actual == _EXPECTED_OUTPUT_FILES


def test_happy_path_stdout_summary_includes_run_id_and_all_counts(
    minimal_stage17_input_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
    ])
    assert rc == EXIT_OK

    out = capsys.readouterr().out
    assert out.startswith("stage18 run_id=")
    for label in ("harmful", "promising", "blocked", "mixed", "weak", "insufficient"):
        assert f"{label}=" in out


def test_quiet_suppresses_stdout(
    minimal_stage17_input_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# --policy-hash filter
# ---------------------------------------------------------------------------


def test_policy_hash_filter_matching_lets_row_through(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--policy-hash", "abc123def456",  # the minimal fixture's policy
        "--quiet",
    ])
    assert rc == EXIT_OK

    review = (out_dir / "review_matrix.csv").read_text(encoding="utf-8")
    lines = review.splitlines()
    assert len(lines) == 2  # header + one row


def test_policy_hash_filter_nonmatching_yields_header_only_review_matrix(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--policy-hash", "no_such_policy",
        "--quiet",
    ])
    assert rc == EXIT_OK

    review = (out_dir / "review_matrix.csv").read_text(encoding="utf-8")
    lines = review.splitlines()
    assert len(lines) == 1  # header only


# ---------------------------------------------------------------------------
# Manifest + log content sanity
# ---------------------------------------------------------------------------


def test_manifest_carries_locked_metadata(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK

    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "stage18_run_manifest_v0"
    assert manifest["stage18_version"] == "stage18_review_v0_observe_only"
    assert (
        manifest["stage17_manifest"]["schema_version"]
        == "stage17_run_manifest_v0"
    )
    assert "gates" in manifest
    assert "input_row_counts" in manifest
    assert "output_row_counts" in manifest
    assert "classification_counts" in manifest
    assert "git_commit" in manifest


def test_log_step_order_matches_spec(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK

    log = (out_dir / "stage18_run.log").read_text(encoding="utf-8")
    lines = log.splitlines()
    expected = [
        "start",
        "inputs_loaded",
        "gates_evaluated",
        "classification_complete",
        "review_matrix_written",
        "data_quality_blockers_written",
        "classification_summary_written",
        "rule_review_cards_written",
        "manifest_written",
        "done",
    ]
    actual = [line.split()[0].removeprefix("step=") for line in lines]
    assert actual == expected


def test_classification_summary_emits_six_rows_via_cli(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "stage18_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK

    content = (out_dir / "classification_summary.csv").read_text(
        encoding="utf-8"
    )
    lines = content.splitlines()
    # 1 header + 6 bucket rows
    assert len(lines) == 7
