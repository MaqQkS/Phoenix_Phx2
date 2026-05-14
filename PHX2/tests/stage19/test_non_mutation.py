"""Stage 19 non-mutation tests.

Confirms that a Stage 19 run leaves every input file
byte-identical (no in-place modification of --stage18-dir or
--prior-ledger-dir contents) and produces only the expected
five output files under --output-dir (no .tmp residue from
atomic writes).
"""

from __future__ import annotations

import hashlib
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


def _hash_dir(d: Path) -> dict[str, str]:
    """Return a dict mapping relative file path -> SHA-256 digest
    for every regular file under ``d``."""

    out: dict[str, str] = {}
    for f in sorted(d.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(d))
            out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


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
# Non-mutation of --stage18-dir
# ===========================================================================


class TestNonMutationStage18Dir:
    def test_stage18_dir_files_unchanged_after_run(
        self, tmp_path: Path
    ) -> None:
        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(op)
        out = tmp_path / "out"

        before = _hash_dir(s18)
        rc = cli.main(_argv(s18, op, out))
        assert rc == 0
        after = _hash_dir(s18)
        assert before == after

    def test_stage18_dir_file_count_unchanged(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(op)
        out = tmp_path / "out"

        before_count = sum(1 for f in s18.rglob("*") if f.is_file())
        cli.main(_argv(s18, op, out))
        after_count = sum(1 for f in s18.rglob("*") if f.is_file())
        assert before_count == after_count


# ===========================================================================
# Non-mutation of --prior-ledger-dir
# ===========================================================================


class TestNonMutationPriorLedgerDir:
    def test_prior_ledger_dir_unchanged_after_extension(
        self, tmp_path: Path
    ) -> None:
        # Build a prior ledger
        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op1 = tmp_path / "op1.csv"
        operator_inputs.write_minimal_valid_operator_input(op1)
        prior_out = tmp_path / "prior_out"
        cli.main(_argv(s18, op1, prior_out))

        before = _hash_dir(prior_out)

        # Run again, extending the prior ledger
        op2 = tmp_path / "op2.csv"
        row = operator_inputs.make_operator_row(
            review_label="WATCHLIST", review_notes="extend"
        )
        operator_inputs.write_minimal_valid_operator_input(op2, rows=[row])
        out2 = tmp_path / "out2"
        rc = cli.main(
            _argv(s18, op2, out2, extra=["--prior-ledger-dir", str(prior_out)])
        )
        assert rc == 0

        after = _hash_dir(prior_out)
        assert before == after


# ===========================================================================
# Non-mutation of --operator-input file
# ===========================================================================


class TestNonMutationOperatorInput:
    def test_operator_input_file_unchanged(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(op)
        out = tmp_path / "out"

        before = hashlib.sha256(op.read_bytes()).hexdigest()
        cli.main(_argv(s18, op, out))
        after = hashlib.sha256(op.read_bytes()).hexdigest()
        assert before == after


# ===========================================================================
# Output dir snapshot: only the 5 expected files, no .tmp residue
# ===========================================================================


class TestOutputDirShape:
    def test_output_dir_contains_exactly_the_5_expected_files(
        self, tmp_path: Path
    ) -> None:
        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(op)
        out = tmp_path / "out"
        rc = cli.main(_argv(s18, op, out))
        assert rc == 0

        files_in_out = sorted(p.name for p in out.iterdir() if p.is_file())
        assert files_in_out == sorted([
            LEDGER_FILENAME,
            SUMMARY_FILENAME,
            MANIFEST_FILENAME,
            README_FILENAME,
            RUN_LOG_FILENAME,
        ])

    def test_no_tmp_residue_in_output_dir(self, tmp_path: Path) -> None:
        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(op)
        out = tmp_path / "out"
        rc = cli.main(_argv(s18, op, out))
        assert rc == 0

        tmp_files = [p for p in out.iterdir() if p.name.endswith(".tmp")]
        assert tmp_files == []


# ===========================================================================
# Repo-root snapshot: no file outside --output-dir was created/modified
# ===========================================================================


class TestNoLeakageOutsideOutputDir:
    def test_only_output_dir_changed_in_workspace(
        self, tmp_path: Path
    ) -> None:
        """Snapshot tmp_path before and after the run; confirm that
        the only change is the appearance of the output_dir."""

        s18 = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(s18)
        op = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(op)
        out = tmp_path / "out"

        # Snapshot everything under tmp_path EXCEPT the not-yet-
        # created out dir
        before = _hash_dir(tmp_path)

        rc = cli.main(_argv(s18, op, out))
        assert rc == 0

        after = _hash_dir(tmp_path)
        # Removed entries (none expected)
        removed = set(before) - set(after)
        # Added entries: only files under out/
        added = set(after) - set(before)
        # Modified entries (same key, different hash): none expected
        modified = {
            k for k in (set(before) & set(after)) if before[k] != after[k]
        }

        assert removed == set(), f"unexpectedly removed: {removed}"
        assert modified == set(), f"unexpectedly modified: {modified}"
        # Every new file should be under out/
        out_rel = "out"
        for added_path in added:
            # On Windows the separator may be \, normalize
            normalized = added_path.replace("\\", "/")
            assert normalized.startswith(f"{out_rel}/"), normalized
