"""Stage 17 CLI integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from PHX2.stage17 import cli
from PHX2.tests.stage17.fixtures.builders import seed_canonical_scenario


def _run_cli(argv: list[str]) -> int:
    """Run the CLI within-process and return the exit code."""

    return cli.main(argv)


def test_make_parser_requires_db_path_and_output_dir(tmp_path: Path) -> None:
    parser = cli.make_parser()
    # Both flags missing -> SystemExit(2).
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args([])
    assert excinfo.value.code == 2


def test_cli_clean_run_on_empty_db(
    stage17_db_path: Path, tmp_path: Path, capsys
) -> None:
    out_dir = tmp_path / "out_empty"
    rc = _run_cli(
        ["--db-path", str(stage17_db_path), "--output-dir", str(out_dir)]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("stage17_run ")
    # All seven artifacts present.
    for name in (
        "headline_metrics.csv",
        "coarse_summary.csv",
        "unevaluable_breakdown.csv",
        "data_quality_report.csv",
        "manifest.json",
        "README.md",
        "stage17_run.log",
    ):
        assert (out_dir / name).exists(), f"missing artifact: {name}"


def test_cli_summary_line_format(
    stage17_db_path: Path, tmp_path: Path, capsys
) -> None:
    out_dir = tmp_path / "out_summary"
    rc = _run_cli(
        ["--db-path", str(stage17_db_path), "--output-dir", str(out_dir)]
    )
    assert rc == 0
    summary = capsys.readouterr().out.strip()
    # Locked tokens (substring checks; values vary by inputs).
    for token in ("stage17_run", "run_id=", "output_dir=", "headline_rows=",
                  "min_n=", "policy_hashes="):
        assert token in summary, f"summary missing token {token!r}: {summary!r}"


def test_cli_exit_3_when_db_missing_required_tables(tmp_path: Path) -> None:
    """A DB lacking the required tables surfaces exit 3."""

    bad_db = tmp_path / "bad.db"
    connection = sqlite3.connect(str(bad_db))
    try:
        connection.executescript("CREATE TABLE foo (id INTEGER PRIMARY KEY);")
        connection.commit()
    finally:
        connection.close()

    out_dir = tmp_path / "out_bad"
    rc = _run_cli(["--db-path", str(bad_db), "--output-dir", str(out_dir)])
    assert rc == 3


def test_cli_exit_3_when_db_path_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no_such.db"
    out_dir = tmp_path / "out_missing"
    rc = _run_cli(["--db-path", str(missing), "--output-dir", str(out_dir)])
    assert rc == 3


def test_cli_exit_4_when_output_dir_already_exists(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    existing = tmp_path / "already"
    existing.mkdir()
    (existing / "sentinel.txt").write_text("preserved", encoding="utf-8")
    rc = _run_cli(
        ["--db-path", str(stage17_db_path), "--output-dir", str(existing)]
    )
    assert rc == 4
    # Sentinel content untouched.
    assert (existing / "sentinel.txt").read_text(encoding="utf-8") == "preserved"


def test_cli_policy_hash_filter_restricts_to_given_hash(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(
        stage17_db_path,
        policy_hash="ph_alpha",
        matched_ids=range(1, 6),
        not_matched_ids=range(101, 106),
    )
    seed_canonical_scenario(
        stage17_db_path,
        policy_hash="ph_beta",
        matched_ids=range(201, 206),
        not_matched_ids=range(301, 306),
    )

    out_dir = tmp_path / "out_filtered"
    rc = _run_cli(
        [
            "--db-path", str(stage17_db_path),
            "--output-dir", str(out_dir),
            "--policy-hash", "ph_alpha",
        ]
    )
    assert rc == 0

    # Verify the manifest mentions only the filtered hash.
    manifest_text = (out_dir / "manifest.json").read_text(encoding="utf-8")
    assert "ph_alpha" in manifest_text
    assert "ph_beta" not in manifest_text


def test_cli_writes_seven_artifacts_with_real_data(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)
    out_dir = tmp_path / "out_real"
    rc = _run_cli(
        ["--db-path", str(stage17_db_path), "--output-dir", str(out_dir)]
    )
    assert rc == 0
    for name in (
        "headline_metrics.csv",
        "coarse_summary.csv",
        "unevaluable_breakdown.csv",
        "data_quality_report.csv",
        "manifest.json",
        "README.md",
        "stage17_run.log",
    ):
        assert (out_dir / name).exists()


def test_cli_argparse_missing_required_flag_exits_2(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    with pytest.raises(SystemExit) as excinfo:
        _run_cli(["--db-path", str(tmp_path / "x.db")])  # missing --output-dir
    assert excinfo.value.code == 2


def test_cli_min_n_negative_exits_3(stage17_db_path: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out_negmn"
    rc = _run_cli(
        [
            "--db-path", str(stage17_db_path),
            "--output-dir", str(out_dir),
            "--min-n", "-1",
        ]
    )
    assert rc == 3
