"""Stage 17 determinism tests: two CLI runs on the same DB produce byte-identical artifacts (after zeroing locked manifest fields)."""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.stage17 import cli
from PHX2.tests.stage17.fixtures.builders import (
    insert_alert_decision,
    insert_evaluation,
    insert_outcome_window,
    seed_canonical_scenario,
)


_BYTE_IDENTICAL_ARTIFACTS = (
    "headline_metrics.csv",
    "coarse_summary.csv",
    "unevaluable_breakdown.csv",
    "data_quality_report.csv",
    "README.md",
    "stage17_run.log",
)


# Locked set of manifest fields zeroed before the determinism comparison.
_MANIFEST_VOLATILE_FIELDS = (
    "run_id",
    "run_started_utc",
    "run_finished_utc",
    "db_path",
    "output_dir",
)


def _run_cli(db_path: Path, output_dir: Path) -> int:
    return cli.main([
        "--db-path", str(db_path),
        "--output-dir", str(output_dir),
    ])


def _zero_volatile_manifest_fields(text: str) -> dict:
    body = json.loads(text)
    for field in _MANIFEST_VOLATILE_FIELDS:
        body[field] = "<zeroed>"
    return body


def test_two_runs_produce_byte_identical_csv_and_readme_and_log(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)

    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    rc_a = _run_cli(stage17_db_path, out_a)
    rc_b = _run_cli(stage17_db_path, out_b)
    assert rc_a == 0
    assert rc_b == 0

    for name in _BYTE_IDENTICAL_ARTIFACTS:
        bytes_a = (out_a / name).read_bytes()
        bytes_b = (out_b / name).read_bytes()
        assert bytes_a == bytes_b, (
            f"{name} differs between two runs of the same DB"
        )


def test_two_runs_produce_identical_manifest_after_zeroing_volatile_fields(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)
    out_a = tmp_path / "run_a_m"
    out_b = tmp_path / "run_b_m"
    _run_cli(stage17_db_path, out_a)
    _run_cli(stage17_db_path, out_b)

    text_a = (out_a / "manifest.json").read_text(encoding="utf-8")
    text_b = (out_b / "manifest.json").read_text(encoding="utf-8")

    body_a = _zero_volatile_manifest_fields(text_a)
    body_b = _zero_volatile_manifest_fields(text_b)
    assert body_a == body_b


def test_run_id_stable_across_runs_against_same_db(
    stage17_db_path: Path, tmp_path: Path
) -> None:
    seed_canonical_scenario(stage17_db_path)
    out_a = tmp_path / "run_a_id"
    out_b = tmp_path / "run_b_id"
    _run_cli(stage17_db_path, out_a)
    _run_cli(stage17_db_path, out_b)
    body_a = json.loads((out_a / "manifest.json").read_text(encoding="utf-8"))
    body_b = json.loads((out_b / "manifest.json").read_text(encoding="utf-8"))
    assert body_a["run_id"] == body_b["run_id"]


def test_run_id_changes_when_db_state_changes(
    stage17_db_factory, tmp_path: Path
) -> None:
    """A different DB row count must produce a different run_id."""

    import sqlite3

    db_a = stage17_db_factory("a")
    db_b = stage17_db_factory("b")
    # db_a stays empty; db_b gets one decision/eval.
    connection = sqlite3.connect(str(db_b))
    try:
        insert_alert_decision(connection, decision_id=1)
        insert_evaluation(
            connection,
            alert_decision_id=1,
            policy_hash="ph_q",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_outcome_window(connection, alert_decision_id=1, window_seconds=300)
    finally:
        connection.close()

    out_a = tmp_path / "run_a_idchange"
    out_b = tmp_path / "run_b_idchange"
    _run_cli(db_a, out_a)
    _run_cli(db_b, out_b)
    body_a = json.loads((out_a / "manifest.json").read_text(encoding="utf-8"))
    body_b = json.loads((out_b / "manifest.json").read_text(encoding="utf-8"))
    assert body_a["run_id"] != body_b["run_id"]
