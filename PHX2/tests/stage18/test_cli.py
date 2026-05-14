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


# ---------------------------------------------------------------------------
# Output-dir provisioning invariants (audit remediation)
# ---------------------------------------------------------------------------


def test_output_dir_parent_missing_yields_b05(
    minimal_stage17_input_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """``--output-dir`` may not name a path whose parent does not
    already exist; Stage 18 refuses to auto-create intermediate
    directories outside the caller-supplied path."""

    out_dir = tmp_path / "missing_parent" / "out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
    ])
    assert rc == EXIT_RUNTIME_ERROR
    assert "B05" in capsys.readouterr().err
    # The non-existent parent must remain non-existent.
    assert not out_dir.exists()
    assert not out_dir.parent.exists()


def test_output_dir_equal_to_input_dir_yields_b05(
    minimal_stage17_input_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(minimal_stage17_input_dir),
    ])
    assert rc == EXIT_RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "B05" in err
    assert "must not equal" in err


def test_output_dir_inside_input_dir_yields_b05(
    minimal_stage17_input_dir: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """``--output-dir`` cannot be a descendant of
    ``--stage17-input-dir``; keeping the input dir read-only
    excludes the possibility of writes landing under it."""

    out_dir = minimal_stage17_input_dir / "nested" / "out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
    ])
    assert rc == EXIT_RUNTIME_ERROR
    err = capsys.readouterr().err
    assert "B05" in err
    assert "must not be inside" in err
    # The input dir must remain unmodified.
    assert not out_dir.exists()


def test_valid_output_dir_with_existing_parent_succeeds(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    """Sanity: the new output-dir invariants don't reject the
    happy case (parent exists, not equal to / inside input dir)."""

    out_dir = tmp_path / "valid_out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK
    assert out_dir.is_dir()


# ---------------------------------------------------------------------------
# Headline descriptive_label validation via CLI (audit remediation)
# ---------------------------------------------------------------------------


def test_b03_unknown_headline_label_leaves_output_dir_absent_and_no_log(
    minimal_stage17_input_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """An unknown ``descriptive_label`` in any
    ``headline_metrics.csv`` row fails the run with B03 BEFORE
    ``output_dir`` is provisioned: the directory must remain
    absent and no stage18_run.log may be left behind. Stderr is
    the only diagnostic surface on this failure mode."""

    headline_path = minimal_stage17_input_dir / "headline_metrics.csv"
    content = headline_path.read_text(encoding="utf-8")
    mutated = content.replace(",HARMFUL\n", ",INVALID_LABEL_VALUE\n")
    assert mutated != content, "fixture mutation did not take effect"
    headline_path.write_text(mutated, encoding="utf-8", newline="")

    out_dir = tmp_path / "out"
    assert not out_dir.exists(), "pre-condition: out_dir absent"

    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
    ])

    assert rc == EXIT_INPUT_ERROR
    err = capsys.readouterr().err
    assert "B03" in err
    assert "INVALID_LABEL_VALUE" in err

    # Strict non-pollution contract: B03 must not provision any
    # on-disk artifact.
    assert not out_dir.exists(), (
        "output_dir must remain absent after B03 (it was not "
        "present before the run)"
    )


def test_b03_unknown_coarse_label_leaves_output_dir_absent_and_no_log(
    minimal_stage17_input_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Mirror of the headline test for the coarse-summary
    descriptive_label. The CLI must reject unknown coarse labels
    with B03 before ``output_dir`` is provisioned."""

    coarse_path = minimal_stage17_input_dir / "coarse_summary.csv"
    content = coarse_path.read_text(encoding="utf-8")
    # The minimal fixture's only coarse data row ends with ",HARMFUL".
    mutated = content.replace(",HARMFUL\n", ",NOT_A_REAL_LABEL\n")
    assert mutated != content, "fixture mutation did not take effect"
    coarse_path.write_text(mutated, encoding="utf-8", newline="")

    out_dir = tmp_path / "out"
    assert not out_dir.exists(), "pre-condition: out_dir absent"

    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
    ])

    assert rc == EXIT_INPUT_ERROR
    err = capsys.readouterr().err
    assert "B03" in err
    assert "NOT_A_REAL_LABEL" in err

    assert not out_dir.exists(), (
        "output_dir must remain absent after B03 (it was not "
        "present before the run)"
    )


# ---------------------------------------------------------------------------
# policy_hash_filter participation in manifest + run_id
# (audit remediation)
# ---------------------------------------------------------------------------


def test_manifest_records_empty_policy_hash_filter_when_unfiltered(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK

    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["policy_hash_filter"] == []


def test_manifest_records_sorted_policy_hash_filter(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--policy-hash", "ph_b",
        "--policy-hash", "ph_a",
        "--quiet",
    ])
    assert rc == EXIT_OK

    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["policy_hash_filter"] == ["ph_a", "ph_b"]


def test_run_id_changes_between_filtered_and_unfiltered_runs(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_unfiltered = tmp_path / "unfiltered"
    out_filtered = tmp_path / "filtered"

    rc_a = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_unfiltered),
        "--quiet",
    ])
    rc_b = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_filtered),
        "--policy-hash", "abc123def456",
        "--quiet",
    ])
    assert rc_a == EXIT_OK
    assert rc_b == EXIT_OK

    a = json.loads(
        (out_unfiltered / "manifest.json").read_text(encoding="utf-8")
    )
    b = json.loads(
        (out_filtered / "manifest.json").read_text(encoding="utf-8")
    )
    assert a["run_id"] != b["run_id"]


def test_run_id_same_when_policy_hash_filter_order_differs(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    """Sorted-deduplicated semantics: the same set of filter
    values produces the same run_id regardless of CLI order."""

    out_ab = tmp_path / "ab"
    out_ba = tmp_path / "ba"

    rc_ab = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_ab),
        "--policy-hash", "alpha",
        "--policy-hash", "beta",
        "--quiet",
    ])
    rc_ba = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_ba),
        "--policy-hash", "beta",
        "--policy-hash", "alpha",
        "--quiet",
    ])
    assert rc_ab == EXIT_OK
    assert rc_ba == EXIT_OK

    a = json.loads((out_ab / "manifest.json").read_text(encoding="utf-8"))
    b = json.loads((out_ba / "manifest.json").read_text(encoding="utf-8"))
    assert a["run_id"] == b["run_id"]
