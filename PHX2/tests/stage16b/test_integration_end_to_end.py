"""Phase 9 end-to-end integration test: real CLI on a Stage 16B-migrated DB
with a real Stage 16A runtime artifact.

Setup (5 alert_decisions, 2-rule policy):

  D1: WOULD_ALERT, tier T1, FE label=NORMAL
        -> SECOND_RULE (T1+NORMAL) MATCHED
        -> DEFAULT_RULE (T2+SCAM_LIKELY) tier-mismatch -> NOT_MATCHED

  D2: WOULD_ALERT, tier T2, FE label=SCAM_LIKELY
        -> SECOND_RULE tier-mismatch -> NOT_MATCHED
        -> DEFAULT_RULE MATCHED

  D3: WOULD_ALERT, tier T3, FE label=NORMAL
        -> both rules tier-mismatch -> NOT_MATCHED x2

  D4: WOULD_ALERT, tier_name=None, FE label=NORMAL
        -> both rules UNEVALUABLE x2 (tier_name_missing_on_decision)

  D5: SKIP (decision_type='skip', would_alert=0)
        -> excluded by WOULD_ALERT filter; zero telemetry rows

Expected telemetry totals: 4 WOULD_ALERT decisions x 2 rules = 8 rows
  status: MATCHED=2, NOT_MATCHED=4, UNEVALUABLE=2.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from PHX2.stage16b.cli import EXIT_OK, main
from PHX2.tests.fixtures.analysis_fixture_builder import insert_alert_decision
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    SECOND_RULE,
    make_runtime_artifact_path,
)
from PHX2.tests.stage16b.fixtures.builders import (
    insert_canonical_filter_evaluation,
    insert_would_alert_decision,
    make_stage16b_db_path,
    stage16b_phx2_connection,
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


_SKIP_DECISION_TIME = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)


def _setup_e2e_db(tmp_path: Path) -> Path:
    """Build the 5-decision Stage 16B DB documented in this module's docstring."""

    db_path = make_stage16b_db_path(tmp_path)
    with stage16b_phx2_connection(db_path) as connection:
        # D1: WOULD_ALERT T1, FE NORMAL -- matches SECOND_RULE.
        insert_would_alert_decision(connection, decision_id=1, tier_name="T1")
        insert_canonical_filter_evaluation(
            connection, fe_id=1, alert_decision_id=1, label="NORMAL",
        )

        # D2: WOULD_ALERT T2, FE SCAM_LIKELY -- matches DEFAULT_RULE.
        insert_would_alert_decision(connection, decision_id=2, tier_name="T2")
        insert_canonical_filter_evaluation(
            connection, fe_id=2, alert_decision_id=2, label="SCAM_LIKELY",
        )

        # D3: WOULD_ALERT T3, FE NORMAL -- both rules tier-mismatch.
        insert_would_alert_decision(connection, decision_id=3, tier_name="T3")
        insert_canonical_filter_evaluation(
            connection, fe_id=3, alert_decision_id=3, label="NORMAL",
        )

        # D4: WOULD_ALERT tier_name=None, FE NORMAL -- all rules UNEVALUABLE.
        insert_would_alert_decision(connection, decision_id=4, tier_name=None)
        insert_canonical_filter_evaluation(
            connection, fe_id=4, alert_decision_id=4, label="NORMAL",
        )

        # D5: SKIP -- excluded by WOULD_ALERT filter; zero telemetry.
        insert_alert_decision(
            connection,
            decision_id=5,
            token_address="tok_skip",
            evaluated_at=_SKIP_DECISION_TIME,
            decision_type="skip",
            would_alert=False,
            tier_name="T1",
        )
        connection.commit()
    return db_path


def _build_runtime_artifact(tmp_path: Path, name: str = "artifact") -> Path:
    """Build a valid Stage 16A runtime artifact carrying the two canonical rules."""

    return make_runtime_artifact_path(
        tmp_path / name,
        rules=(DEFAULT_RULE, SECOND_RULE),
    )


def _run_cli(artifact: Path, db: Path, limit: int) -> int:
    return main([
        "--runtime-policy-path", str(artifact),
        "--db-path", str(db),
        "--limit", str(limit),
    ])


def _hash_table(connection, table: str) -> str:
    rows = connection.execute(
        f"SELECT * FROM {table} ORDER BY rowid"
    ).fetchall()
    if not rows:
        return "<empty>"
    keys = rows[0].keys()
    canonical = "\n".join(
        "|".join(repr(row[k]) for k in keys) for row in rows
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Row count + per-decision distribution
# ---------------------------------------------------------------------------


def test_e2e_cli_writes_one_row_per_would_alert_decision_per_rule(
    tmp_path, capsys,
) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    exit_code = _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations"
        ).fetchone()[0]
    finally:
        conn.close()

    assert exit_code == EXIT_OK
    # 4 WOULD_ALERT decisions x 2 rules = 8.
    assert total == 8


def test_e2e_cli_status_distribution_matches_expected(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        status_rows = conn.execute(
            "SELECT evaluation_status, COUNT(*) AS c "
            "FROM observe_only_policy_evaluations "
            "GROUP BY evaluation_status ORDER BY evaluation_status"
        ).fetchall()
    finally:
        conn.close()

    counts = {row[0]: row[1] for row in status_rows}
    assert counts == {
        "MATCHED": 2,
        "NOT_MATCHED": 4,
        "UNEVALUABLE": 2,
    }


def test_e2e_cli_per_decision_row_breakdown(tmp_path, capsys) -> None:
    """Each WOULD_ALERT decision contributes exactly len(policy.rules)=2 rows."""

    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT alert_decision_id, COUNT(*) AS c "
            "FROM observe_only_policy_evaluations "
            "GROUP BY alert_decision_id ORDER BY alert_decision_id"
        ).fetchall()
    finally:
        conn.close()

    # Only D1..D4 (the WOULD_ALERTs) get 2 rows each; D5 (SKIP) gets none.
    assert [(r[0], r[1]) for r in rows] == [(1, 2), (2, 2), (3, 2), (4, 2)]


def test_e2e_cli_d1_matched_row_is_for_t1_normal_rule(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT rule_id, matched, would_have_blocked "
            "FROM observe_only_policy_evaluations "
            "WHERE alert_decision_id = 1 AND evaluation_status = 'MATCHED'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == SECOND_RULE["rule_id"]  # rule_t1_fee_gate_normal
    assert (row[1], row[2]) == (1, 1)


def test_e2e_cli_d2_matched_row_is_for_t2_scam_likely_rule(
    tmp_path, capsys,
) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT rule_id "
            "FROM observe_only_policy_evaluations "
            "WHERE alert_decision_id = 2 AND evaluation_status = 'MATCHED'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == DEFAULT_RULE["rule_id"]  # rule_t2_fee_gate_scam_likely


def test_e2e_cli_d4_unevaluable_reason_is_tier_name_missing(
    tmp_path, capsys,
) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT unevaluable_reason "
            "FROM observe_only_policy_evaluations "
            "WHERE alert_decision_id = 4"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert all(r[0] == "tier_name_missing_on_decision" for r in rows)


def test_e2e_cli_skip_decision_gets_zero_rows(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations "
            "WHERE alert_decision_id = 5"
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 0


# ---------------------------------------------------------------------------
# Summary line + report counters via CLI
# ---------------------------------------------------------------------------


def test_e2e_cli_summary_reports_counters_correctly(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    out = capsys.readouterr().out

    assert "rules=2" in out
    assert "evaluated=4" in out
    assert "inserted=8" in out
    assert "matched=2" in out
    assert "not_matched=4" in out
    assert "unevaluable=2" in out
    assert "skipped=0" in out


# ---------------------------------------------------------------------------
# Rerun idempotency via CLI
# ---------------------------------------------------------------------------


def test_e2e_cli_rerun_writes_zero_new_rows(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    try:
        first_run_count = conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations"
        ).fetchone()[0]
    finally:
        conn.close()

    # Rerun
    exit_code_2 = _run_cli(artifact, db, limit=100)
    second_out = capsys.readouterr().out

    conn = sqlite3.connect(str(db))
    try:
        second_run_count = conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations"
        ).fetchone()[0]
    finally:
        conn.close()

    assert exit_code_2 == EXIT_OK
    assert first_run_count == 8
    assert second_run_count == 8
    assert "evaluated=0" in second_out
    assert "inserted=0" in second_out


# ---------------------------------------------------------------------------
# Upstream-table non-mutation via CLI
# ---------------------------------------------------------------------------


def test_e2e_cli_does_not_mutate_alert_decisions(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        before = _hash_table(conn, "alert_decisions")
    finally:
        conn.close()

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        after = _hash_table(conn, "alert_decisions")
    finally:
        conn.close()

    assert before == after


def test_e2e_cli_does_not_mutate_filter_evaluations(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        before = _hash_table(conn, "filter_evaluations")
    finally:
        conn.close()

    _run_cli(artifact, db, limit=100)
    capsys.readouterr()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        after = _hash_table(conn, "filter_evaluations")
    finally:
        conn.close()

    assert before == after


# ---------------------------------------------------------------------------
# limit + empty policy via CLI
# ---------------------------------------------------------------------------


def test_e2e_cli_limit_caps_evaluated_decisions(tmp_path, capsys) -> None:
    """limit=2 processes exactly the lowest-id 2 WOULD_ALERT decisions
    (= D1, D2) and writes 4 telemetry rows total."""

    db = _setup_e2e_db(tmp_path)
    artifact = _build_runtime_artifact(tmp_path)

    _run_cli(artifact, db, limit=2)
    out = capsys.readouterr().out

    conn = sqlite3.connect(str(db))
    try:
        per_decision = list(conn.execute(
            "SELECT DISTINCT alert_decision_id "
            "FROM observe_only_policy_evaluations "
            "ORDER BY alert_decision_id"
        ))
        evaluated_ids = [r[0] for r in per_decision]
        total = conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations"
        ).fetchone()[0]
    finally:
        conn.close()

    assert evaluated_ids == [1, 2]
    assert total == 4
    assert "evaluated=2" in out


def test_e2e_cli_empty_policy_writes_zero_rows(tmp_path, capsys) -> None:
    db = _setup_e2e_db(tmp_path)
    empty_artifact = make_runtime_artifact_path(
        tmp_path / "empty_artifact", rules=(),
    )

    exit_code = _run_cli(empty_artifact, db, limit=100)
    out = capsys.readouterr().out

    conn = sqlite3.connect(str(db))
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM observe_only_policy_evaluations"
        ).fetchone()[0]
    finally:
        conn.close()

    assert exit_code == EXIT_OK
    assert total == 0
    assert "rules=0" in out
    assert "evaluated=0" in out
