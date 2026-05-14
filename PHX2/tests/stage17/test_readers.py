"""Stage 17 reader-layer tests.

Each test focuses on a single locked behavior of PHX2/stage17/readers.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from PHX2.stage17.errors import Stage17Error
from PHX2.stage17.readers import (
    count_orphan_evaluations,
    count_orphan_outcomes,
    fetch_evaluation_rows,
    fetch_outcome_rows_for_decisions,
    list_distinct_policy_hashes,
    list_schema_migrations,
    open_db_readonly,
    verify_required_tables,
)
from PHX2.tests.stage17.fixtures.builders import (
    insert_alert_decision,
    insert_evaluation,
    insert_outcome_window,
)


# ---------------------------------------------------------------------------
# open_db_readonly
# ---------------------------------------------------------------------------


def test_open_db_readonly_returns_connection_with_row_factory(
    stage17_db_path: Path,
) -> None:
    connection = open_db_readonly(stage17_db_path)
    try:
        assert connection.row_factory is sqlite3.Row
    finally:
        connection.close()


def test_open_db_readonly_blocks_writes(stage17_db_path: Path) -> None:
    """A write against the read-only connection raises OperationalError."""

    connection = open_db_readonly(stage17_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                "INSERT INTO alert_decisions ("
                "id, token_address, evaluated_at, decision_type, primary_reason, "
                "would_alert, blocked, skipped, ath_status, ath_confidence, "
                "policy_version, created_at, data_status) "
                "VALUES (999, 't', 't', 'would_alert', 'r', 1, 0, 0, 'unknown', "
                "'low', 'pv', 't', 'COMPLETE')"
            )
    finally:
        connection.close()


def test_open_db_readonly_missing_file_raises_a01(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(Stage17Error) as excinfo:
        open_db_readonly(missing)
    assert excinfo.value.code == "A01"


# ---------------------------------------------------------------------------
# verify_required_tables
# ---------------------------------------------------------------------------


def test_verify_required_tables_passes_on_full_schema(
    stage17_db_path: Path,
) -> None:
    connection = open_db_readonly(stage17_db_path)
    try:
        verify_required_tables(connection)
    finally:
        connection.close()


def test_verify_required_tables_raises_a02_with_missing_table_name(
    tmp_path: Path,
) -> None:
    """A DB lacking observe_only_policy_evaluations surfaces A02 with the name."""

    db_path = tmp_path / "missing_obs.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript(
            """
            CREATE TABLE alert_decisions (id INTEGER PRIMARY KEY);
            CREATE TABLE outcome_windows (id INTEGER PRIMARY KEY);
            """
        )
        connection.commit()
    finally:
        connection.close()

    ro = open_db_readonly(db_path)
    try:
        with pytest.raises(Stage17Error) as excinfo:
            verify_required_tables(ro)
    finally:
        ro.close()
    assert excinfo.value.code == "A02"
    assert "observe_only_policy_evaluations" in str(excinfo.value)


# ---------------------------------------------------------------------------
# list_distinct_policy_hashes
# ---------------------------------------------------------------------------


def test_list_distinct_policy_hashes_returns_sorted_distinct(
    stage17_db_path: Path,
) -> None:
    """In-scope policy_hashes are returned, distinct, ascending."""

    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(writable, decision_id=1)
        insert_alert_decision(writable, decision_id=2)
        # Three evaluations across two in-scope decisions cover the
        # distinct + sort + multi-rule cases together.
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_b",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_a",
            rule_id="r1",
            evaluation_status="NOT_MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_b",
            rule_id="r2",
            evaluation_status="MATCHED",
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        hashes = list_distinct_policy_hashes(ro)
    finally:
        ro.close()
    assert hashes == ("ph_a", "ph_b")


def test_list_distinct_policy_hashes_empty_db_returns_empty(
    stage17_db_path: Path,
) -> None:
    ro = open_db_readonly(stage17_db_path)
    try:
        hashes = list_distinct_policy_hashes(ro)
    finally:
        ro.close()
    assert hashes == ()


def test_list_distinct_policy_hashes_excludes_decision_type_not_would_alert(
    stage17_db_path: Path,
) -> None:
    """A policy_hash whose only evaluations point at decision_type != 'would_alert' is excluded."""

    writable = sqlite3.connect(str(stage17_db_path))
    try:
        # In-scope decision for ph_in.
        insert_alert_decision(
            writable,
            decision_id=1,
            decision_type="would_alert",
            would_alert=1,
        )
        # Out-of-scope decision (decision_type != 'would_alert') for ph_skip.
        insert_alert_decision(
            writable,
            decision_id=2,
            decision_type="skip",
            would_alert=1,
        )
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_in",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_skip",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        hashes = list_distinct_policy_hashes(ro)
    finally:
        ro.close()
    assert hashes == ("ph_in",)


def test_list_distinct_policy_hashes_excludes_would_alert_zero(
    stage17_db_path: Path,
) -> None:
    """A policy_hash whose only evaluations point at would_alert = 0 is excluded."""

    writable = sqlite3.connect(str(stage17_db_path))
    try:
        # In-scope decision for ph_in.
        insert_alert_decision(
            writable,
            decision_id=1,
            decision_type="would_alert",
            would_alert=1,
        )
        # Out-of-scope decision (would_alert = 0) for ph_wa0.
        insert_alert_decision(
            writable,
            decision_id=2,
            decision_type="would_alert",
            would_alert=0,
        )
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_in",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_wa0",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        hashes = list_distinct_policy_hashes(ro)
    finally:
        ro.close()
    assert hashes == ("ph_in",)


def test_list_distinct_policy_hashes_in_scope_only_when_mixed(
    stage17_db_path: Path,
) -> None:
    """A policy_hash that has BOTH in-scope and out-of-scope evaluations
    appears exactly once (distinct + in-scope filter compose cleanly).

    Also pins ascending sort across a mix of in-scope and out-of-scope
    rows: the surviving hashes must be returned in ascending order
    regardless of insertion order.
    """

    writable = sqlite3.connect(str(stage17_db_path))
    try:
        # Two in-scope decisions, one out-of-scope.
        insert_alert_decision(
            writable, decision_id=1, decision_type="would_alert", would_alert=1
        )
        insert_alert_decision(
            writable, decision_id=2, decision_type="skip", would_alert=1
        )
        insert_alert_decision(
            writable, decision_id=3, decision_type="would_alert", would_alert=1
        )
        # ph_b: in-scope eval on decision 1 + out-of-scope eval on decision 2.
        # Should still appear (distinct), and only the in-scope evaluation
        # contributes to the decision.
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_b",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_b",
            rule_id="r2",
            evaluation_status="MATCHED",
        )
        # ph_a: in-scope eval on decision 3.
        insert_evaluation(
            writable,
            alert_decision_id=3,
            policy_hash="ph_a",
            rule_id="r1",
            evaluation_status="NOT_MATCHED",
        )
        # ph_z_orphan: only out-of-scope evaluations -> excluded entirely.
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_z_orphan",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        hashes = list_distinct_policy_hashes(ro)
    finally:
        ro.close()
    assert hashes == ("ph_a", "ph_b")


# ---------------------------------------------------------------------------
# fetch_evaluation_rows
# ---------------------------------------------------------------------------


def test_fetch_evaluation_rows_respects_decision_type_clause(
    stage17_db_path: Path,
) -> None:
    """A row with decision_type='would_alert' but would_alert=0 is excluded."""

    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(
            writable,
            decision_id=1,
            decision_type="would_alert",
            would_alert=1,
        )
        insert_alert_decision(
            writable,
            decision_id=2,
            decision_type="would_alert",
            would_alert=0,  # excluded by AND clause
        )
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_x",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_x",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_evaluation_rows(ro, "ph_x")
    finally:
        ro.close()
    assert len(rows) == 1
    assert rows[0].alert_decision_id == 1


def test_fetch_evaluation_rows_respects_would_alert_clause(
    stage17_db_path: Path,
) -> None:
    """A row with decision_type='skip' and would_alert=1 is excluded."""

    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(
            writable,
            decision_id=1,
            decision_type="would_alert",
            would_alert=1,
        )
        insert_alert_decision(
            writable,
            decision_id=2,
            decision_type="skip",
            would_alert=1,  # excluded by decision_type clause
        )
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_y",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_y",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_evaluation_rows(ro, "ph_y")
    finally:
        ro.close()
    assert len(rows) == 1
    assert rows[0].alert_decision_id == 1


def test_fetch_evaluation_rows_handles_null_tier_snapshot(
    stage17_db_path: Path,
) -> None:
    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(writable, decision_id=1, tier_name=None)
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_null",
            rule_id="r1",
            evaluation_status="NOT_MATCHED",
            tier_name_snapshot=None,
        )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_evaluation_rows(ro, "ph_null")
    finally:
        ro.close()
    assert len(rows) == 1
    assert rows[0].tier_name_snapshot is None


def test_fetch_evaluation_rows_orders_by_id_ascending(
    stage17_db_path: Path,
) -> None:
    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(writable, decision_id=1)
        insert_alert_decision(writable, decision_id=2)
        insert_alert_decision(writable, decision_id=3)
        for did in (3, 1, 2):
            insert_evaluation(
                writable,
                alert_decision_id=did,
                policy_hash="ph_ord",
                rule_id="r1",
                evaluation_status="MATCHED",
            )
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_evaluation_rows(ro, "ph_ord")
    finally:
        ro.close()
    ids = [r.id for r in rows]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# fetch_outcome_rows_for_decisions
# ---------------------------------------------------------------------------


def test_fetch_outcome_rows_for_empty_input_returns_empty(
    stage17_db_path: Path,
) -> None:
    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_outcome_rows_for_decisions(ro, [])
    finally:
        ro.close()
    assert rows == ()


def test_fetch_outcome_rows_returns_only_matching_ids(
    stage17_db_path: Path,
) -> None:
    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(writable, decision_id=10)
        insert_alert_decision(writable, decision_id=11)
        insert_alert_decision(writable, decision_id=12)
        insert_outcome_window(writable, alert_decision_id=10, window_seconds=300)
        insert_outcome_window(writable, alert_decision_id=11, window_seconds=300)
        insert_outcome_window(writable, alert_decision_id=12, window_seconds=300)
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_outcome_rows_for_decisions(ro, [10, 12])
    finally:
        ro.close()
    ids = sorted(r.alert_decision_id for r in rows)
    assert ids == [10, 12]


def test_fetch_outcome_rows_orders_by_decision_then_window(
    stage17_db_path: Path,
) -> None:
    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(writable, decision_id=1)
        insert_alert_decision(writable, decision_id=2)
        insert_outcome_window(writable, alert_decision_id=2, window_seconds=900)
        insert_outcome_window(writable, alert_decision_id=2, window_seconds=300)
        insert_outcome_window(writable, alert_decision_id=1, window_seconds=900)
        insert_outcome_window(writable, alert_decision_id=1, window_seconds=300)
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        rows = fetch_outcome_rows_for_decisions(ro, [1, 2])
    finally:
        ro.close()
    keys = [(r.alert_decision_id, r.window_seconds) for r in rows]
    assert keys == [(1, 300), (1, 900), (2, 300), (2, 900)]


# ---------------------------------------------------------------------------
# Orphan counts
# ---------------------------------------------------------------------------


def test_count_orphan_evaluations_counts_missing_or_out_of_scope(
    stage17_db_path: Path,
) -> None:
    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(
            writable, decision_id=1, decision_type="would_alert", would_alert=1
        )
        insert_alert_decision(
            writable, decision_id=2, decision_type="skip", would_alert=1
        )
        insert_alert_decision(
            writable, decision_id=3, decision_type="would_alert", would_alert=0
        )

        # In-scope eval: not orphan.
        insert_evaluation(
            writable,
            alert_decision_id=1,
            policy_hash="ph_q",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        # Eval pointing at a row failing the scope (decision_type=skip): orphan.
        insert_evaluation(
            writable,
            alert_decision_id=2,
            policy_hash="ph_q",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        # Eval pointing at would_alert=0: orphan.
        insert_evaluation(
            writable,
            alert_decision_id=3,
            policy_hash="ph_q",
            rule_id="r1",
            evaluation_status="MATCHED",
        )
        # Eval pointing at a non-existent decision id: orphan.
        # We bypass the helper because the foreign key is inert by
        # default at runtime.
        writable.execute(
            "INSERT INTO observe_only_policy_evaluations ("
            "alert_decision_id, tier_name_snapshot, policy_hash, rule_id, "
            "evaluation_status, matched, would_have_blocked, unevaluable_reason, "
            "predicate_snapshot_json, evaluated_at_utc, created_at_utc) "
            "VALUES (999, NULL, 'ph_q', 'r1', 'MATCHED', 1, 1, NULL, '{}', "
            "'2026-05-13T12:00:00+00:00', '2026-05-13T12:00:00+00:00')"
        )
        writable.commit()
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        n = count_orphan_evaluations(ro)
    finally:
        ro.close()
    assert n == 3


def test_count_orphan_outcomes_counts_missing_decisions(
    stage17_db_path: Path,
) -> None:
    writable = sqlite3.connect(str(stage17_db_path))
    try:
        insert_alert_decision(writable, decision_id=1)
        insert_outcome_window(writable, alert_decision_id=1, window_seconds=300)
        # Outcome row pointing at a non-existent decision id: orphan.
        writable.execute(
            "INSERT INTO outcome_windows ("
            "alert_decision_id, token_address, window_seconds, "
            "window_start_time, window_end_time, data_status, created_at"
            ") VALUES (777, 'T', 300, 't', 't', 'COMPLETE', 't')"
        )
        writable.commit()
    finally:
        writable.close()

    ro = open_db_readonly(stage17_db_path)
    try:
        n = count_orphan_outcomes(ro)
    finally:
        ro.close()
    assert n == 1


# ---------------------------------------------------------------------------
# schema_migrations passthrough
# ---------------------------------------------------------------------------


def test_list_schema_migrations_handles_missing_table(tmp_path: Path) -> None:
    """A DB without a schema_migrations table returns an empty tuple."""

    db_path = tmp_path / "no_sm.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript("CREATE TABLE x (id INTEGER PRIMARY KEY);")
        connection.commit()
    finally:
        connection.close()

    ro = open_db_readonly(db_path)
    try:
        result = list_schema_migrations(ro)
    finally:
        ro.close()
    assert result == ()
