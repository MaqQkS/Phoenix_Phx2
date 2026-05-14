"""Stage 19 CLI tests.

Covers end-to-end happy paths (no prior, with prior, empty
operator input, --quiet, --run-timestamp), all 21 E-code
exit-code paths, partial-output cleanup, and stdout summary
formatting.

git_commit is monkeypatched to a frozen value across tests so
output is deterministic regardless of repo state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from PHX2.stage19 import cli
from PHX2.stage19.constants import (
    LABELS,
    LEDGER_FILENAME,
    MANIFEST_FILENAME,
    OPERATOR_INPUT_COLUMNS,
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


def _build_happy_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a minimal valid Stage 18 dir + operator input file +
    output dir path. Returns (stage18_dir, operator_input,
    output_dir)."""

    s18 = tmp_path / "stage18_run"
    stage18_outputs.write_minimal_valid_stage18_output(s18)
    op = tmp_path / "operator_review_input.csv"
    operator_inputs.write_minimal_valid_operator_input(op)
    out = tmp_path / "stage19_out"
    return s18, op, out


def _argv_happy(
    s18: Path,
    op: Path,
    out: Path,
    *,
    operator_id: str = "alice",
    extra: list[str] | None = None,
) -> list[str]:
    base = [
        "--stage18-dir", str(s18),
        "--operator-input", str(op),
        "--output-dir", str(out),
        "--operator-id", operator_id,
        "--run-timestamp", _FROZEN_TS,
    ]
    if extra:
        base.extend(extra)
    return base


# ===========================================================================
# Happy paths
# ===========================================================================


class TestCliHappyPath:
    def test_no_prior_ledger_writes_all_5_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 0
        assert (out / LEDGER_FILENAME).is_file()
        assert (out / SUMMARY_FILENAME).is_file()
        assert (out / MANIFEST_FILENAME).is_file()
        assert (out / README_FILENAME).is_file()
        assert (out / RUN_LOG_FILENAME).is_file()

    def test_stdout_summary_matches_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 0
        captured = capsys.readouterr()
        line = captured.out.strip()
        # Format: stage19 run_id=<hex> new_rows=<N> total_rows=<N> labels=...
        m = re.match(
            r"^stage19 run_id=[0-9a-f]{16} new_rows=\d+ "
            r"total_rows=\d+ labels=.+$",
            line,
        )
        assert m, line
        # All 6 labels present in the summary line
        for label in LABELS:
            assert label in line

    def test_quiet_suppresses_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out, extra=["--quiet"]))
        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_run_timestamp_override_used_in_manifest(
        self, tmp_path: Path
    ) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 0
        manifest = json.loads(
            (out / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        assert manifest["run_timestamp_utc"] == _FROZEN_TS

    def test_manifest_contains_frozen_git_commit(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 0
        manifest = json.loads(
            (out / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        assert manifest["git_commit"] == _FROZEN_GIT_SHA

    def test_label_counts_total_matches_new_rows(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 0
        manifest = json.loads(
            (out / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        assert sum(manifest["label_counts"].values()) == manifest["new_row_count"]


class TestCliWithPriorLedger:
    def test_prior_ledger_rows_preserved_in_final_ledger(
        self, tmp_path: Path
    ) -> None:
        # First run -- creates a prior ledger
        s18, op1, out1 = _build_happy_inputs(tmp_path)
        rc1 = cli.main(_argv_happy(s18, op1, out1))
        assert rc1 == 0
        prior_ledger = (out1 / LEDGER_FILENAME).read_bytes()

        # Second run -- with different operator_id, same slice
        op2 = tmp_path / "op2.csv"
        row = operator_inputs.make_operator_row(
            review_label="WATCHLIST", review_notes="bob's take"
        )
        operator_inputs.write_minimal_valid_operator_input(op2, rows=[row])
        out2 = tmp_path / "stage19_out_2"
        argv = _argv_happy(
            s18, op2, out2,
            operator_id="bob",
            extra=["--prior-ledger-dir", str(out1)],
        )
        rc2 = cli.main(argv)
        assert rc2 == 0

        # Final ledger should include both alice's row and bob's row
        text2 = (out2 / LEDGER_FILENAME).read_text(encoding="utf-8")
        assert "alice" in text2
        assert "bob" in text2
        # Row counts: 1 prior + 1 new = 2 total
        manifest = json.loads(
            (out2 / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        assert manifest["prior_row_count"] == 1
        assert manifest["new_row_count"] == 1
        assert manifest["total_ledger_row_count"] == 2

    def test_revisit_increments_review_sequence(self, tmp_path: Path) -> None:
        # Run 1: alice reviews
        s18, op1, out1 = _build_happy_inputs(tmp_path)
        cli.main(_argv_happy(s18, op1, out1))
        # Run 2: alice revisits same slice
        op2 = tmp_path / "op2.csv"
        row = operator_inputs.make_operator_row(
            review_label="WATCHLIST", review_notes="changed mind"
        )
        operator_inputs.write_minimal_valid_operator_input(op2, rows=[row])
        out2 = tmp_path / "out2"
        argv = _argv_happy(
            s18, op2, out2,
            operator_id="alice",
            extra=["--prior-ledger-dir", str(out1)],
        )
        rc = cli.main(argv)
        assert rc == 0
        # The newly added row should have review_sequence=2
        text = (out2 / LEDGER_FILENAME).read_text(encoding="utf-8")
        # Find the WATCHLIST row
        for line in text.splitlines()[1:]:
            if "WATCHLIST" in line:
                # Format: review_sequence is column 7 (0-indexed)
                cols = line.split(",")
                assert cols[7] == "2"
                break
        else:
            pytest.fail("WATCHLIST row not found")


class TestCliEmptyOperatorInput:
    def test_header_only_succeeds_with_zero_new_rows(
        self, tmp_path: Path
    ) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "empty_op.csv"
        operator_inputs.write_header_only_operator_input(op)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 0
        manifest = json.loads(
            (out / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        assert manifest["new_row_count"] == 0
        assert all(v == 0 for v in manifest["label_counts"].values())
        # Ledger CSV is header-only
        ledger_text = (out / LEDGER_FILENAME).read_text(encoding="utf-8")
        assert ledger_text.count("\n") == 1


# ===========================================================================
# E-code paths -- each should yield exit code 10
# ===========================================================================


def _common_argv(s18: Path, op: Path, out: Path, **kw) -> list[str]:
    """Variant of _argv_happy that doesn't auto-add --run-timestamp,
    used for E19 tests."""
    extra = kw.get("extra") or []
    op_id = kw.get("operator_id", "alice")
    base = [
        "--stage18-dir", str(s18),
        "--operator-input", str(op),
        "--output-dir", str(out),
        "--operator-id", op_id,
    ]
    base.extend(extra)
    return base


class TestCliECodePathsE01_E05:
    def test_e01_non_existent_stage18_dir(self, tmp_path: Path) -> None:
        _, op, out = _build_happy_inputs(tmp_path)
        bogus = tmp_path / "missing_stage18"
        rc = cli.main(_argv_happy(bogus, op, out))
        assert rc == 10

    def test_e02_missing_stage18_manifest(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18_no_manifest"
        s18.mkdir()
        # Write a review_matrix.csv but no manifest.json
        stage18_outputs.write_review_matrix(
            s18 / "review_matrix.csv",
            [stage18_outputs.make_review_row()],
        )
        _, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e03_missing_review_matrix(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18_no_matrix"
        s18.mkdir()
        stage18_outputs.write_manifest(s18 / "manifest.json")
        _, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e04_malformed_manifest_json(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        s18.mkdir()
        stage18_outputs.write_manifest(
            s18 / "manifest.json", raw_text="not json {{{"
        )
        stage18_outputs.write_review_matrix(
            s18 / "review_matrix.csv",
            [stage18_outputs.make_review_row()],
        )
        _, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e05_wrong_schema_version(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        s18.mkdir()
        stage18_outputs.write_manifest(
            s18 / "manifest.json", schema_version="stage18_run_manifest_v9"
        )
        stage18_outputs.write_review_matrix(
            s18 / "review_matrix.csv",
            [stage18_outputs.make_review_row()],
        )
        _, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10


class TestCliECodePathsE06_E09:
    def test_e06_missing_operator_input(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        bogus_op = tmp_path / "missing_op.csv"
        rc = cli.main(_argv_happy(s18, bogus_op, out))
        assert rc == 10

    def test_e07_bad_operator_header(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        operator_inputs.write_operator_input_with_header(
            op, OPERATOR_INPUT_COLUMNS + ("extra",)
        )
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e08_bad_operator_row(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        bad = operator_inputs.make_operator_row(window_seconds="not_an_int")
        operator_inputs.write_minimal_valid_operator_input(op, rows=[bad])
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e09_bad_label(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        bad = operator_inputs.make_operator_row(review_label="AGREE")
        operator_inputs.write_minimal_valid_operator_input(op, rows=[bad])
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10


class TestCliECodePathsE10_E13:
    def test_e10_run_id_mismatch(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        bad = operator_inputs.make_mismatched_run_id_row()
        operator_inputs.write_minimal_valid_operator_input(op, rows=[bad])
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e11_identity_not_in_review_matrix(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        bad = operator_inputs.make_operator_row(rule_id="not_in_matrix")
        operator_inputs.write_minimal_valid_operator_input(op, rows=[bad])
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e12_duplicate_identity(self, tmp_path: Path) -> None:
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        rows = list(operator_inputs.make_duplicate_identity_rows())
        operator_inputs.write_minimal_valid_operator_input(op, rows=rows)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e13_bad_review_notes_oversize(self, tmp_path: Path) -> None:
        import csv as csvmod
        s18, _, out = _build_happy_inputs(tmp_path)
        op = tmp_path / "op.csv"
        notes = operator_inputs.make_oversize_review_notes(length=2001)
        with op.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10


class TestCliECodePathsE14_E15:
    def test_e14_bad_operator_id(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out, operator_id="bad,id"))
        assert rc == 10

    def test_e15_output_dir_non_empty(self, tmp_path: Path) -> None:
        s18, op, _ = _build_happy_inputs(tmp_path)
        out = tmp_path / "non_empty_out"
        out.mkdir()
        (out / "preexisting.txt").write_text("hi")
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e15_output_dir_parent_does_not_exist(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """F01 regression: ``--output-dir`` whose parent directory
        does not exist on disk must be rejected with exit code 10
        and an [E15] error surfaced on stderr. Stage 19 must not
        create the missing parent."""

        s18, op, _ = _build_happy_inputs(tmp_path)
        missing_parent = tmp_path / "no_such_parent"
        out = missing_parent / "stage19_out"
        assert not missing_parent.exists()
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10
        captured = capsys.readouterr()
        assert "E15" in captured.err
        assert not missing_parent.exists()
        assert not out.exists()


class TestCliECodePathsE16_E18:
    def test_e16_missing_prior_ledger_files(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        empty_prior = tmp_path / "empty_prior"
        empty_prior.mkdir()  # exists but missing both required files
        rc = cli.main(
            _argv_happy(s18, op, out, extra=["--prior-ledger-dir", str(empty_prior)])
        )
        assert rc == 10

    def test_e17_bad_prior_schema(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        prior = tmp_path / "prior"
        prior.mkdir()
        # Build a prior dir with a bad schema version
        from PHX2.stage19.constants import LEDGER_COLUMNS
        (prior / "manifest.json").write_text(
            json.dumps({"stage19_schema_version": "stage19_ledger_v0"}),
            encoding="utf-8",
        )
        (prior / "operator_review_ledger.csv").write_text(
            ",".join(LEDGER_COLUMNS) + "\n", encoding="utf-8"
        )
        rc = cli.main(
            _argv_happy(s18, op, out, extra=["--prior-ledger-dir", str(prior)])
        )
        assert rc == 10

    def test_e18_bad_prior_row(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        prior = tmp_path / "prior"
        prior.mkdir()
        from PHX2.stage19.constants import LEDGER_COLUMNS
        (prior / "manifest.json").write_text(
            json.dumps({"stage19_schema_version": "stage19_ledger_v1"}),
            encoding="utf-8",
        )
        # Header but bad row (wrong column count)
        text = ",".join(LEDGER_COLUMNS) + "\n" + "only,three,cells\n"
        (prior / "operator_review_ledger.csv").write_text(
            text, encoding="utf-8"
        )
        rc = cli.main(
            _argv_happy(s18, op, out, extra=["--prior-ledger-dir", str(prior)])
        )
        assert rc == 10


class TestCliECodePathsE19:
    def test_e19_bad_run_timestamp(self, tmp_path: Path) -> None:
        s18, op, out = _build_happy_inputs(tmp_path)
        argv = _common_argv(s18, op, out, extra=["--run-timestamp", "bad-ts"])
        rc = cli.main(argv)
        assert rc == 10


class TestCliECodePathsE20_E21:
    def test_e20_bad_review_matrix_header(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        s18.mkdir()
        stage18_outputs.write_manifest(s18 / "manifest.json")
        # Write a bad header (missing tier_coverage)
        from PHX2.stage19.constants import (
            STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS,
        )
        bad_header = tuple(
            c for c in STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS
            if c != "tier_coverage"
        )
        stage18_outputs.write_review_matrix_with_header(
            s18 / "review_matrix.csv", bad_header
        )
        _, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10

    def test_e21_bad_review_matrix_row(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        s18.mkdir()
        stage18_outputs.write_manifest(s18 / "manifest.json")
        bad_row = stage18_outputs.make_review_row(window_seconds="abc")
        stage18_outputs.write_review_matrix(
            s18 / "review_matrix.csv", [bad_row]
        )
        _, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10


# ===========================================================================
# Partial-output cleanup
# ===========================================================================


class TestCliPartialOutputCleanup:
    def test_validation_failure_creates_no_output_dir(
        self, tmp_path: Path
    ) -> None:
        """E01-E14 validation failures happen before output_dir is
        created; the output dir must not exist after a failed run."""

        s18, op, out = _build_happy_inputs(tmp_path)
        rc = cli.main(_argv_happy(s18, op, out, operator_id="bad,id"))
        assert rc == 10
        assert not out.exists()

    def test_e15_does_not_clean_up_pre_existing_dir_contents(
        self, tmp_path: Path
    ) -> None:
        """E15 fires when --output-dir is already non-empty. The
        pre-existing contents must be preserved (CLI must not rmtree
        before validating)."""

        s18, op, _ = _build_happy_inputs(tmp_path)
        out = tmp_path / "non_empty_out"
        out.mkdir()
        preserved = out / "preserved.txt"
        preserved.write_text("important", encoding="utf-8")
        rc = cli.main(_argv_happy(s18, op, out))
        assert rc == 10
        assert preserved.exists()
        assert preserved.read_text(encoding="utf-8") == "important"
