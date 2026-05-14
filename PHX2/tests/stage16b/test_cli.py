"""Phase 7 tests: Stage 16B CLI.

Locks tested here:

  * argparse rejects missing/invalid required flags with SystemExit(2).
  * --limit < 0 exits 3 with M08 in stderr.
  * Nonexistent --runtime-policy-path / --db-path exits 3; no DB writes;
    no DB file is silently created.
  * Missing tables surface M01 / M02 / M03 (exit 3); no DB writes.
  * Unsafe policy (Stage 16A R03) exits 3 with M04; no DB writes.
  * Clean run exits 0, writes telemetry, emits the locked summary line.
  * Empty policy exits 0 with zero rows written.
  * ``--limit 0`` exits 0 with zero rows written.
  * Rerun is idempotent (no new rows on second invocation).
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from PHX2.db.migrations import (
    STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL,
    apply_stage11_schema,
)
from PHX2.stage16b.cli import (
    EXIT_CLI_ARG_ERROR,
    EXIT_LOAD_ERROR,
    EXIT_OK,
    main,
)
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    make_runtime_artifact_path,
)
from PHX2.tests.stage16b.fixtures.builders import (
    insert_canonical_filter_evaluation,
    insert_would_alert_decision,
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _build_empty_stage16b_db(tmp_path: Path) -> Path:
    """Fresh Stage 16B-migrated DB with no test data."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        connection.commit()
    return db_path


def _build_stage16b_db_with_t2_scam_decision(tmp_path: Path) -> Path:
    """Stage 16B DB with one WOULD_ALERT decision matching the Stage 16A
    DEFAULT_RULE (tier T2 + filter_label SCAM_LIKELY)."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        insert_would_alert_decision(connection, decision_id=1, tier_name="T2")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="SCAM_LIKELY",
        )
        connection.commit()
    return db_path


def _build_stage11_db(tmp_path: Path) -> Path:
    """Stage 11 DB (alert_decisions + filter_evaluations exist, Stage 16B
    table does NOT).

    Sets ``row_factory = sqlite3.Row`` because the migration chain reads
    ``PRAGMA table_info`` rows by column name.
    """

    db_path = tmp_path / f"stage11_{uuid.uuid4().hex}.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        apply_stage11_schema(connection)
    finally:
        connection.close()
    return db_path


def _build_stage16b_db_dropping_table(tmp_path: Path, drop_table: str) -> Path:
    """Stage 16B DB then drop the named upstream table.

    Used to construct minimal scenarios for the M02 / M03 missing-table
    checks (Stage 4 unconditionally creates alert_decisions and
    filter_evaluations, so they have to be removed post-migration to
    reproduce the missing state).
    """

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        connection.execute(f"DROP TABLE {drop_table}")
        connection.commit()
    return db_path


def _count_telemetry_rows(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='observe_only_policy_evaluations'"
        ).fetchone()
        if row is None:
            return 0
        return conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations"
        ).fetchone()[0]
    finally:
        conn.close()


def _build_clean_artifact(tmp_path: Path) -> Path:
    """Valid Stage 16A runtime artifact carrying DEFAULT_RULE (T2 + SCAM_LIKELY)."""

    return make_runtime_artifact_path(tmp_path / "artifact_clean")


# ---------------------------------------------------------------------------
# Section A -- argparse errors (exit 2)
# ---------------------------------------------------------------------------


def test_cli_no_args_exits_argparse(tmp_path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == EXIT_CLI_ARG_ERROR


def test_cli_missing_runtime_policy_path_exits_argparse(tmp_path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([
            "--db-path", str(tmp_path / "db.sqlite"),
            "--limit", "10",
        ])
    assert exc_info.value.code == EXIT_CLI_ARG_ERROR


def test_cli_missing_db_path_exits_argparse(tmp_path) -> None:
    artifact = _build_clean_artifact(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main([
            "--runtime-policy-path", str(artifact),
            "--limit", "10",
        ])
    assert exc_info.value.code == EXIT_CLI_ARG_ERROR


def test_cli_missing_limit_exits_argparse(tmp_path) -> None:
    artifact = _build_clean_artifact(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main([
            "--runtime-policy-path", str(artifact),
            "--db-path", str(tmp_path / "db.sqlite"),
        ])
    assert exc_info.value.code == EXIT_CLI_ARG_ERROR


def test_cli_non_integer_limit_exits_argparse(tmp_path) -> None:
    artifact = _build_clean_artifact(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main([
            "--runtime-policy-path", str(artifact),
            "--db-path", str(tmp_path / "db.sqlite"),
            "--limit", "abc",
        ])
    assert exc_info.value.code == EXIT_CLI_ARG_ERROR


# ---------------------------------------------------------------------------
# Section B -- semantic argument errors (exit 3)
# ---------------------------------------------------------------------------


def test_cli_negative_limit_exits_load_error_m08(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_empty_stage16b_db(tmp_path)

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "-1",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "[M08]" in err
    assert _count_telemetry_rows(db) == 0


# ---------------------------------------------------------------------------
# Section C -- file existence errors (exit 3)
# ---------------------------------------------------------------------------


def test_cli_nonexistent_policy_file_exits_load_error(tmp_path, capsys) -> None:
    db = _build_empty_stage16b_db(tmp_path)

    exit_code = main([
        "--runtime-policy-path", str(tmp_path / "nope.json"),
        "--db-path", str(db),
        "--limit", "10",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "does not exist" in err
    assert _count_telemetry_rows(db) == 0


def test_cli_nonexistent_db_exits_load_error(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    nonexistent_db = tmp_path / "nonexistent.db"

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(nonexistent_db),
        "--limit", "10",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "does not exist" in err
    # CRITICAL: the CLI must NOT silently create a fresh DB.
    assert not nonexistent_db.exists()


# ---------------------------------------------------------------------------
# Section D -- missing tables (exit 3)
# ---------------------------------------------------------------------------


def test_cli_missing_observe_only_policy_evaluations_table_exits_m01(
    tmp_path, capsys,
) -> None:
    """A Stage 11 DB lacks observe_only_policy_evaluations -> exit 3 M01."""

    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage11_db(tmp_path)

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "[M01]" in err
    # The CLI must NOT have created the missing table as a side effect.
    conn = sqlite3.connect(str(db))
    try:
        present = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='observe_only_policy_evaluations'"
        ).fetchone()
    finally:
        conn.close()
    assert present is None


def test_cli_missing_alert_decisions_table_exits_m02(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_dropping_table(tmp_path, "alert_decisions")

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "[M02]" in err
    assert _count_telemetry_rows(db) == 0


def test_cli_missing_filter_evaluations_table_exits_m03(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_dropping_table(tmp_path, "filter_evaluations")

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "[M03]" in err
    assert _count_telemetry_rows(db) == 0


# ---------------------------------------------------------------------------
# Section E -- unsafe policy (exit 3, M04)
# ---------------------------------------------------------------------------


def test_cli_unsafe_policy_exits_load_error_m04(tmp_path, capsys) -> None:
    """A Stage 16A runtime artifact with a corrupted safety_surface
    triggers R03 in the loader; the CLI maps this to exit 3 with M04."""

    db = _build_empty_stage16b_db(tmp_path)
    unsafe_artifact = make_runtime_artifact_path(
        tmp_path / "unsafe",
        safety_surface_override={},  # missing all keys -> R03
    )

    exit_code = main([
        "--runtime-policy-path", str(unsafe_artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    err = capsys.readouterr().err
    assert exit_code == EXIT_LOAD_ERROR
    assert "[M04]" in err
    assert _count_telemetry_rows(db) == 0


def test_cli_no_writes_when_unsafe_policy(tmp_path, capsys) -> None:
    """Even with valid WOULD_ALERT decisions queued, an unsafe policy
    aborts before any rows are written."""

    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)
    unsafe_artifact = make_runtime_artifact_path(
        tmp_path / "unsafe2",
        safety_surface_override={},
    )

    exit_code = main([
        "--runtime-policy-path", str(unsafe_artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    capsys.readouterr()
    assert exit_code == EXIT_LOAD_ERROR
    assert _count_telemetry_rows(db) == 0


# ---------------------------------------------------------------------------
# Section F -- clean runs (exit 0)
# ---------------------------------------------------------------------------


def test_cli_clean_run_exits_zero(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    assert exit_code == EXIT_OK


def test_cli_clean_run_writes_telemetry(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)

    main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])
    capsys.readouterr()

    # DEFAULT_RULE matches the decision -> exactly 1 MATCHED row.
    assert _count_telemetry_rows(db) == 1

    # Verify the row's status posture.
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT evaluation_status, matched, would_have_blocked "
            "FROM observe_only_policy_evaluations"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("MATCHED", 1, 1)


def test_cli_clean_run_summary_line_format(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)

    main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    out = capsys.readouterr().out.strip()
    assert out.startswith("stage16b observer: ")
    for token in (
        "policy_hash=",
        "rules=",
        "evaluated=",
        "inserted=",
        "ignored=",
        "matched=",
        "not_matched=",
        "unevaluable=",
        "skipped=",
        "duration=",
    ):
        assert token in out, f"summary missing token {token!r}: {out!r}"
    assert out.endswith("s"), f"summary should end with duration suffix 's': {out!r}"
    # Single line -- no embedded newlines.
    assert "\n" not in out


def test_cli_empty_policy_exits_zero(tmp_path, capsys) -> None:
    """Stage 16A runtime artifact with an empty rules list is a clean
    short-circuit at the observer."""

    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)
    empty_artifact = make_runtime_artifact_path(tmp_path / "empty", rules=())

    exit_code = main([
        "--runtime-policy-path", str(empty_artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    capsys.readouterr()
    assert exit_code == EXIT_OK


def test_cli_empty_policy_writes_zero_rows(tmp_path, capsys) -> None:
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)
    empty_artifact = make_runtime_artifact_path(tmp_path / "empty2", rules=())

    main([
        "--runtime-policy-path", str(empty_artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])
    capsys.readouterr()

    assert _count_telemetry_rows(db) == 0


def test_cli_empty_policy_summary_reports_zero_rule_count(
    tmp_path, capsys,
) -> None:
    db = _build_empty_stage16b_db(tmp_path)
    empty_artifact = make_runtime_artifact_path(tmp_path / "empty3", rules=())

    main([
        "--runtime-policy-path", str(empty_artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])

    out = capsys.readouterr().out
    assert "rules=0" in out
    assert "evaluated=0" in out
    assert "inserted=0" in out


def test_cli_limit_zero_exits_zero(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "0",
    ])

    capsys.readouterr()
    assert exit_code == EXIT_OK


def test_cli_limit_zero_writes_zero_rows(tmp_path, capsys) -> None:
    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)

    main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "0",
    ])
    capsys.readouterr()

    assert _count_telemetry_rows(db) == 0


def test_cli_rerun_idempotent(tmp_path, capsys) -> None:
    """A second CLI invocation against the same DB + policy is a no-op
    for telemetry row count -- list_missing excludes already-evaluated
    decisions, so the rerun emits zero new rows."""

    artifact = _build_clean_artifact(tmp_path)
    db = _build_stage16b_db_with_t2_scam_decision(tmp_path)

    exit_code_1 = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])
    capsys.readouterr()
    count_after_first = _count_telemetry_rows(db)

    exit_code_2 = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", "10",
    ])
    out_second = capsys.readouterr().out
    count_after_second = _count_telemetry_rows(db)

    assert exit_code_1 == EXIT_OK
    assert exit_code_2 == EXIT_OK
    assert count_after_first == 1
    assert count_after_second == 1
    # Second run's summary should reflect zero new work.
    assert "evaluated=0" in out_second
    assert "inserted=0" in out_second


# ---------------------------------------------------------------------------
# Section G -- multi-decision + limit observation through the CLI
# ---------------------------------------------------------------------------


def test_cli_multi_decision_run_writes_one_row_per_decision(
    tmp_path, capsys,
) -> None:
    """Three matching decisions -> three MATCHED rows; CLI summary
    reflects the counts."""

    artifact = _build_clean_artifact(tmp_path)

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        for decision_id in (1, 2, 3):
            insert_would_alert_decision(
                connection, decision_id=decision_id, tier_name="T2",
            )
            insert_canonical_filter_evaluation(
                connection, fe_id=decision_id,
                alert_decision_id=decision_id, label="SCAM_LIKELY",
            )
        connection.commit()

    exit_code = main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db_path),
        "--limit", "100",
    ])

    out = capsys.readouterr().out
    assert exit_code == EXIT_OK
    assert _count_telemetry_rows(db_path) == 3
    assert "evaluated=3" in out
    assert "inserted=3" in out
    assert "matched=3" in out
