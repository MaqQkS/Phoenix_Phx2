"""Stage 14 CLI tests.

Covers:
  * argparse plumbing for required + optional flags.
  * nonexistent --stage13-run path -> exit code 2.
  * nonexistent --stage12-run override -> exit code 2.
  * Loader validation error -> exit code 3.
  * Happy path prints the run directory path on stdout and exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from PHX2.stage14 import cli as stage14_cli
from PHX2.tests.fixtures.stage14.stage14_fixture_writer import (
    Stage12LongRow,
    build_default_bundle,
    write_stage12_run,
)


def test_make_parser_required_stage13_flag() -> None:
    parser = stage14_cli.make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_make_parser_accepts_only_stage13(tmp_path: Path) -> None:
    parser = stage14_cli.make_parser()
    args = parser.parse_args(["--stage13-run", str(tmp_path)])
    assert args.stage13_run == tmp_path
    assert args.stage12_run is None
    assert args.output_root is not None


def test_make_parser_accepts_full_arguments(tmp_path: Path) -> None:
    parser = stage14_cli.make_parser()
    args = parser.parse_args(
        [
            "--stage13-run",
            str(tmp_path / "s13"),
            "--stage12-run",
            str(tmp_path / "s12"),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert args.stage13_run == tmp_path / "s13"
    assert args.stage12_run == tmp_path / "s12"
    assert args.output_root == tmp_path / "out"


def test_main_returns_2_for_missing_stage13_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = stage14_cli.main(
        [
            "--stage13-run",
            str(tmp_path / "does_not_exist"),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_main_returns_2_for_missing_stage12_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_default_bundle(tmp_path)
    rc = stage14_cli.main(
        [
            "--stage13-run",
            str(bundle.stage13_run_path),
            "--stage12-run",
            str(tmp_path / "missing_stage12"),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_main_returns_3_for_invariant_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_default_bundle(tmp_path, safe_for_live=True)
    rc = stage14_cli.main(
        [
            "--stage13-run",
            str(bundle.stage13_run_path),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    assert "validation failed" in err


def test_main_returns_3_for_hash_mismatch_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_default_bundle(tmp_path)
    other = write_stage12_run(
        tmp_path / "other_stage12",
        long_rows=[Stage12LongRow(alert_decision_id="x")],
        run_id="20260601T000000Z_aaa000",
    )
    rc = stage14_cli.main(
        [
            "--stage13-run",
            str(bundle.stage13_run_path),
            "--stage12-run",
            str(other),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    assert "hash mismatch" in err


def test_main_happy_path_prints_output_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = build_default_bundle(tmp_path)
    rc = stage14_cli.main(
        [
            "--stage13-run",
            str(bundle.stage13_run_path),
            "--output-root",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    stdout = capsys.readouterr().out.strip()
    printed = Path(stdout)
    assert printed.exists()
    assert (printed / "manifest.json").exists()
