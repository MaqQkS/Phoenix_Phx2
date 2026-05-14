"""Stage 17 non-mutation tests: Stage 17 must not write to any DB."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from PHX2.stage17 import cli
from PHX2.tests.stage17.fixtures.builders import seed_canonical_scenario


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _table_counts(db_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        out: dict[str, int] = {}
        for name in (
            "alert_decisions",
            "filter_evaluations",
            "observe_only_policy_evaluations",
            "outcome_windows",
        ):
            row = connection.execute(
                f"SELECT COUNT(*) AS n FROM {name}"
            ).fetchone()
            out[name] = int(row["n"])
        return out
    finally:
        connection.close()


def _sqlite_master_count(db_path: Path) -> int:
    connection = sqlite3.connect(str(db_path))
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master"
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def test_db_sha256_unchanged_after_run(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)
    before = _sha256(stage17_db_path)
    rc = cli.main([
        "--db-path", str(stage17_db_path),
        "--output-dir", str(tmp_path / "out_sha"),
    ])
    assert rc == 0
    after = _sha256(stage17_db_path)
    assert before == after


def test_table_row_counts_unchanged_after_run(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)
    before = _table_counts(stage17_db_path)
    rc = cli.main([
        "--db-path", str(stage17_db_path),
        "--output-dir", str(tmp_path / "out_rc"),
    ])
    assert rc == 0
    after = _table_counts(stage17_db_path)
    assert before == after


def test_sqlite_master_count_unchanged_after_run(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)
    before = _sqlite_master_count(stage17_db_path)
    rc = cli.main([
        "--db-path", str(stage17_db_path),
        "--output-dir", str(tmp_path / "out_sm"),
    ])
    assert rc == 0
    after = _sqlite_master_count(stage17_db_path)
    assert before == after


def test_no_stage17_runs_directory_created_in_repo_working_tree(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    """Stage 17 outputs must land under the requested --output-dir.

    No artifact should leak into the live repo working tree (the
    .gitignore rule ``PHX2/stage17_runs/`` covers the convention but
    Stage 17 itself never creates that directory unless asked to).
    """

    repo_root = Path(__file__).resolve().parents[3]
    leak_dir = repo_root / "PHX2" / "stage17_runs"
    if leak_dir.exists():
        # If it exists from prior local runs, snapshot its mtime so we can
        # detect mutation; we explicitly do NOT delete it from the repo.
        pre_mtime = leak_dir.stat().st_mtime
    else:
        pre_mtime = None

    rc = cli.main([
        "--db-path", str(stage17_db_path),
        "--output-dir", str(tmp_path / "out_leak_check"),
    ])
    assert rc == 0

    if pre_mtime is None:
        assert not leak_dir.exists()
    else:
        assert leak_dir.stat().st_mtime == pre_mtime
