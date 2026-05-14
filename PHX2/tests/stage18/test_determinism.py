"""Phase 18.3 determinism tests.

Two runs of Stage 18 against the same Stage 17 input directory
must produce:

  * byte-identical content for the six non-manifest artifacts
    (classification_summary.csv, review_matrix.csv,
     data_quality_blockers.csv, rule_review_cards.md,
     README.md, stage18_run.log)
  * byte-identical manifest.json after zeroing the five volatile
    fields (run_id, run_started_utc, run_finished_utc,
    stage17_input_dir, output_dir) plus git_commit (which can
    legitimately differ if the git binary becomes available
    between runs).
  * the same run_id (deterministic from the canonical input set)
  * a different run_id when input row counts change.
"""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.stage18.cli import EXIT_OK, main


_VOLATILE_MANIFEST_FIELDS: frozenset[str] = frozenset({
    "run_id",
    "run_started_utc",
    "run_finished_utc",
    "stage17_input_dir",
    "output_dir",
    "git_commit",
})


_NON_MANIFEST_ARTIFACTS: tuple[str, ...] = (
    "classification_summary.csv",
    "review_matrix.csv",
    "data_quality_blockers.csv",
    "rule_review_cards.md",
    "README.md",
    "stage18_run.log",
)


def _run_stage18(input_dir: Path, output_dir: Path) -> int:
    return main([
        "--stage17-input-dir", str(input_dir),
        "--output-dir", str(output_dir),
        "--quiet",
    ])


def _zero_volatile(manifest: dict) -> dict:
    out = dict(manifest)
    for field in _VOLATILE_MANIFEST_FIELDS:
        if field in out:
            out[field] = ""
    return out


def test_two_runs_produce_byte_identical_non_manifest_artifacts(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    assert _run_stage18(minimal_stage17_input_dir, out_a) == EXIT_OK
    assert _run_stage18(minimal_stage17_input_dir, out_b) == EXIT_OK

    for name in _NON_MANIFEST_ARTIFACTS:
        bytes_a = (out_a / name).read_bytes()
        bytes_b = (out_b / name).read_bytes()
        assert bytes_a == bytes_b, (
            f"{name} not byte-identical across runs"
        )


def test_two_runs_produce_byte_identical_manifest_after_volatile_zeroing(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    assert _run_stage18(minimal_stage17_input_dir, out_a) == EXIT_OK
    assert _run_stage18(minimal_stage17_input_dir, out_b) == EXIT_OK

    a = json.loads((out_a / "manifest.json").read_text(encoding="utf-8"))
    b = json.loads((out_b / "manifest.json").read_text(encoding="utf-8"))
    assert _zero_volatile(a) == _zero_volatile(b)


def test_run_id_identical_across_two_runs_of_same_input(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"

    assert _run_stage18(minimal_stage17_input_dir, out_a) == EXIT_OK
    assert _run_stage18(minimal_stage17_input_dir, out_b) == EXIT_OK

    a = json.loads((out_a / "manifest.json").read_text(encoding="utf-8"))
    b = json.loads((out_b / "manifest.json").read_text(encoding="utf-8"))
    assert a["run_id"] == b["run_id"]


def test_run_id_changes_when_input_row_counts_change(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    """Appending a coarse-summary row changes the input row counts
    that go into the run_id derivation, and therefore changes the
    run_id."""

    out_original = tmp_path / "run_original"
    assert _run_stage18(minimal_stage17_input_dir, out_original) == EXIT_OK
    original = json.loads(
        (out_original / "manifest.json").read_text(encoding="utf-8")
    )

    # Mutate the input by appending one valid coarse row.
    coarse_path = minimal_stage17_input_dir / "coarse_summary.csv"
    original_text = coarse_path.read_text(encoding="utf-8")
    new_row = (
        "abc123def456,rule_second,300,5min,50,20,30,50,"
        "0.300000,0.250000,0.050000,WEAK\n"
    )
    coarse_path.write_text(
        original_text + new_row, encoding="utf-8", newline=""
    )

    out_changed = tmp_path / "run_changed"
    assert _run_stage18(minimal_stage17_input_dir, out_changed) == EXIT_OK
    changed = json.loads(
        (out_changed / "manifest.json").read_text(encoding="utf-8")
    )

    assert original["run_id"] != changed["run_id"]
