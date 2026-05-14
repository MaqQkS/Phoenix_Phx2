"""Stage 19 determinism tests.

Two consecutive CLI runs with identical inputs (including
--run-timestamp) must produce byte-identical output files.
git_commit is monkeypatched to a frozen value across tests so
the manifest is also byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage19 import cli
from PHX2.stage19.constants import (
    LEDGER_FILENAME,
    MANIFEST_FILENAME,
    README_FILENAME,
    RUN_LOG_FILENAME,
    SUMMARY_FILENAME,
)
from PHX2.tests.stage19.fixtures import operator_inputs, stage18_outputs


_FROZEN_GIT_SHA: str = "0123456789abcdef0123456789abcdef01234567"
_FROZEN_TS: str = "2026-05-14T05:00:00Z"


@pytest.fixture(autouse=True)
def _freeze_git_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "PHX2.stage19.cli.get_git_commit", lambda: _FROZEN_GIT_SHA
    )


def _setup_inputs(base: Path, slot: str) -> tuple[Path, Path, Path]:
    """Create a Stage 18 dir + operator input + output dir under
    ``base/<slot>/``. The Stage 18 dir contents are byte-identical
    across slots (default minimal write)."""

    root = base / slot
    root.mkdir(parents=True, exist_ok=True)
    s18 = root / "stage18_run"
    stage18_outputs.write_minimal_valid_stage18_output(s18)
    op = root / "operator_review_input.csv"
    operator_inputs.write_minimal_valid_operator_input(op)
    out = root / "stage19_out"
    return s18, op, out


def _argv(s18: Path, op: Path, out: Path, **kw) -> list[str]:
    extra = kw.get("extra") or []
    return [
        "--stage18-dir", str(s18),
        "--operator-input", str(op),
        "--output-dir", str(out),
        "--operator-id", "alice",
        "--run-timestamp", _FROZEN_TS,
        "--quiet",
    ] + extra


# ===========================================================================
# Two-run byte-identical comparison
# ===========================================================================


class TestDeterminismTwoRuns:
    def test_ledger_csv_byte_identical(self, tmp_path: Path) -> None:
        s18a, opa, outa = _setup_inputs(tmp_path, "a")
        s18b, opb, outb = _setup_inputs(tmp_path, "b")
        cli.main(_argv(s18a, opa, outa))
        cli.main(_argv(s18b, opb, outb))
        assert (
            (outa / LEDGER_FILENAME).read_bytes()
            == (outb / LEDGER_FILENAME).read_bytes()
        )

    def test_summary_csv_byte_identical(self, tmp_path: Path) -> None:
        s18a, opa, outa = _setup_inputs(tmp_path, "a")
        s18b, opb, outb = _setup_inputs(tmp_path, "b")
        cli.main(_argv(s18a, opa, outa))
        cli.main(_argv(s18b, opb, outb))
        assert (
            (outa / SUMMARY_FILENAME).read_bytes()
            == (outb / SUMMARY_FILENAME).read_bytes()
        )

    def test_run_log_byte_identical(self, tmp_path: Path) -> None:
        s18a, opa, outa = _setup_inputs(tmp_path, "a")
        s18b, opb, outb = _setup_inputs(tmp_path, "b")
        cli.main(_argv(s18a, opa, outa))
        cli.main(_argv(s18b, opb, outb))
        # Note: run_log contains absolute paths which differ between
        # tmp_path/a and tmp_path/b. So the log will NOT be
        # byte-identical across slots. Compare each slot to itself
        # by re-running into the same output dir? That requires
        # cleaning first. Instead use a single-slot rerun pattern.

        # Build slot c, run into outc1; clear; run into outc2
        # (separate output dirs are required since output_dir must be
        # empty/non-existent).
        s18c, opc, _ = _setup_inputs(tmp_path, "c")
        outc1 = tmp_path / "c1"
        outc2 = tmp_path / "c2"
        cli.main(_argv(s18c, opc, outc1))
        cli.main(_argv(s18c, opc, outc2))
        # These both reference the same s18c path so logs are
        # byte-identical.
        assert (
            (outc1 / RUN_LOG_FILENAME).read_bytes()
            == (outc2 / RUN_LOG_FILENAME).read_bytes()
        )

    def test_readme_byte_identical(self, tmp_path: Path) -> None:
        # Same single-slot pattern -- README contains absolute paths
        s18, op, _ = _setup_inputs(tmp_path, "c")
        out1 = tmp_path / "rd1"
        out2 = tmp_path / "rd2"
        cli.main(_argv(s18, op, out1))
        cli.main(_argv(s18, op, out2))
        assert (
            (out1 / README_FILENAME).read_bytes()
            == (out2 / README_FILENAME).read_bytes()
        )

    def test_manifest_byte_identical(self, tmp_path: Path) -> None:
        s18, op, _ = _setup_inputs(tmp_path, "c")
        out1 = tmp_path / "m1"
        out2 = tmp_path / "m2"
        cli.main(_argv(s18, op, out1))
        cli.main(_argv(s18, op, out2))
        assert (
            (out1 / MANIFEST_FILENAME).read_bytes()
            == (out2 / MANIFEST_FILENAME).read_bytes()
        )


class TestDeterminismWithPriorLedger:
    def test_two_runs_with_prior_ledger_byte_identical(
        self, tmp_path: Path
    ) -> None:
        # Build a prior ledger first
        s18, op, prior_out = _setup_inputs(tmp_path, "prior")
        cli.main(_argv(s18, op, prior_out))

        # Now run twice with the same prior ledger and same new input
        op2_a = tmp_path / "a_op.csv"
        op2_b = tmp_path / "b_op.csv"
        row = operator_inputs.make_operator_row(
            review_label="WATCHLIST", review_notes="extend"
        )
        operator_inputs.write_minimal_valid_operator_input(op2_a, rows=[row])
        operator_inputs.write_minimal_valid_operator_input(op2_b, rows=[row])

        out_a = tmp_path / "a_out"
        out_b = tmp_path / "b_out"
        # Both runs must use the same operator_input PATH for byte
        # identity (operator_input_path appears in manifest/log).
        # So use a single op file but two different output dirs.
        cli.main(
            _argv(s18, op2_a, out_a, extra=["--prior-ledger-dir", str(prior_out)])
        )
        cli.main(
            _argv(s18, op2_a, out_b, extra=["--prior-ledger-dir", str(prior_out)])
        )
        for fname in (LEDGER_FILENAME, SUMMARY_FILENAME, MANIFEST_FILENAME, README_FILENAME, RUN_LOG_FILENAME):
            assert (out_a / fname).read_bytes() == (out_b / fname).read_bytes(), fname


# ===========================================================================
# Sort-order invariants
# ===========================================================================


class TestDeterminismSortOrder:
    def test_d3_sort_uses_int_window_seconds(self, tmp_path: Path) -> None:
        """Three slices with window_seconds 60, 300, 3600 must
        appear in numeric order (60 < 300 < 3600), not lexicographic
        order ("3600" < "300" < "60")."""

        s18 = tmp_path / "s18"
        s18.mkdir()
        stage18_outputs.write_manifest(s18 / "manifest.json")
        rows = [
            stage18_outputs.make_review_row(window_seconds="3600"),
            stage18_outputs.make_review_row(window_seconds="60"),
            stage18_outputs.make_review_row(window_seconds="300"),
        ]
        stage18_outputs.write_review_matrix(s18 / "review_matrix.csv", rows)

        op = tmp_path / "op.csv"
        op_rows = [
            operator_inputs.make_operator_row(window_seconds="3600"),
            operator_inputs.make_operator_row(window_seconds="60"),
            operator_inputs.make_operator_row(window_seconds="300"),
        ]
        operator_inputs.write_minimal_valid_operator_input(op, rows=op_rows)

        out = tmp_path / "out"
        cli.main(_argv(s18, op, out))

        ledger = (out / LEDGER_FILENAME).read_text(encoding="utf-8")
        data_lines = ledger.splitlines()[1:]  # skip header
        # window_seconds is column 5 (0-indexed)
        windows = [int(line.split(",")[5]) for line in data_lines]
        assert windows == [60, 300, 3600]
