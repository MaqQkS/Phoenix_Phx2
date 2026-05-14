"""Phase 2 tests: Stage 16B migration creates the observe_only_policy_evaluations table with the locked column shape, CHECK / UNIQUE / FK constraints, and three indexes.

The migration is dual-surfaced: the canonical DDL lives in
``PHX2.db.migrations`` and the Stage 16B-owned ``PHX2.stage16b.migrations``
module re-exports it. Parity tests guarantee both surfaces resolve to the
same object so there is no SQL duplication.

FK runtime rejection is locked to PRAGMA foreign_keys = ON for the
assertion only (the global PHX2 posture is OFF; same as
filter_evaluations and decision_score_features). The FK declaration test
inspects ``PRAGMA foreign_key_list`` and does not require enforcement.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.db.migrations import (
    EXPECTED_STAGE_16B_COLUMNS,
    EXPECTED_STAGE_16B_FOREIGN_KEY,
    EXPECTED_STAGE_16B_INDEXES,
    EXPECTED_STAGE_16B_UNIQUE_COLUMNS,
    STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL,
    STAGE_16B_VERSION,
    Stage16BMigrationError,
    apply_stage11_schema,
    apply_stage16b_observe_only_policy_evaluations,
    apply_stage16b_schema,
)
from PHX2.stage16b import migrations as stage16b_migrations


# ---------------------------------------------------------------------------
# Stage 16B test DB helper
# ---------------------------------------------------------------------------


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"stage16b_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _stage16b_connection() -> Iterator[sqlite3.Connection]:
    """Yield a raw sqlite3.Connection with the full Stage 16B schema applied."""

    path = _temporary_phx2_db_path()
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        apply_stage16b_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


# ---------------------------------------------------------------------------
# Locked column shape
# ---------------------------------------------------------------------------


_LOCKED_COLUMNS: tuple[tuple[str, str, int], ...] = (
    # (name, declared_type, notnull)
    ("id", "INTEGER", 0),
    ("alert_decision_id", "INTEGER", 1),
    ("tier_name_snapshot", "TEXT", 0),
    ("policy_hash", "TEXT", 1),
    ("rule_id", "TEXT", 1),
    ("evaluation_status", "TEXT", 1),
    ("matched", "INTEGER", 1),
    ("would_have_blocked", "INTEGER", 1),
    ("unevaluable_reason", "TEXT", 0),
    ("predicate_snapshot_json", "TEXT", 1),
    ("evaluated_at_utc", "TEXT", 1),
    ("created_at_utc", "TEXT", 1),
)


# ---------------------------------------------------------------------------
# Table existence + column shape
# ---------------------------------------------------------------------------


def test_table_exists() -> None:
    with _stage16b_connection() as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='observe_only_policy_evaluations'"
        ).fetchone()
    assert row is not None


def test_table_has_locked_12_columns_in_order() -> None:
    with _stage16b_connection() as connection:
        rows = list(connection.execute(
            "PRAGMA table_info(observe_only_policy_evaluations)"
        ))

    actual = tuple(
        (row["name"], row["type"], row["notnull"]) for row in rows
    )
    assert actual == _LOCKED_COLUMNS


# ---------------------------------------------------------------------------
# UNIQUE + FK + indexes
# ---------------------------------------------------------------------------


def test_unique_constraint_declared() -> None:
    """UNIQUE(alert_decision_id, policy_hash, rule_id) appears as a unique index."""

    with _stage16b_connection() as connection:
        index_rows = list(connection.execute(
            "PRAGMA index_list(observe_only_policy_evaluations)"
        ))
        unique_indexes = [r for r in index_rows if r["unique"] == 1]
        composite_columns: list[tuple[str, ...]] = []
        for idx in unique_indexes:
            cols = tuple(
                r["name"]
                for r in connection.execute(
                    f"PRAGMA index_info({idx['name']})"
                )
            )
            composite_columns.append(cols)

    assert ("alert_decision_id", "policy_hash", "rule_id") in composite_columns


def test_unique_constraint_enforced() -> None:
    with _stage16b_connection() as connection:
        # Two identical-identity rows. The first must succeed; the second
        # must raise sqlite3.IntegrityError on the UNIQUE violation.
        params = {
            "alert_decision_id": 1,
            "tier_name_snapshot": "T1",
            "policy_hash": "sha256:" + "a" * 64,
            "rule_id": "rule_a",
            "evaluation_status": "NOT_MATCHED",
            "matched": 0,
            "would_have_blocked": 0,
            "unevaluable_reason": None,
            "predicate_snapshot_json": "{}",
            "evaluated_at_utc": "2026-05-13T12:00:00+00:00",
            "created_at_utc": "2026-05-13T12:00:00+00:00",
        }
        _insert_row(connection, **params)
        with pytest.raises(sqlite3.IntegrityError):
            _insert_row(connection, **params)


def test_fk_declared_via_pragma_foreign_key_list() -> None:
    with _stage16b_connection() as connection:
        rows = list(connection.execute(
            "PRAGMA foreign_key_list(observe_only_policy_evaluations)"
        ))

    matching = [
        row
        for row in rows
        if row["table"] == "alert_decisions"
        and row["from"] == "alert_decision_id"
        and row["to"] == "id"
    ]
    assert len(matching) == 1


def test_all_three_indexes_exist() -> None:
    expected = {
        "idx_observe_only_policy_eval_decision",
        "idx_observe_only_policy_eval_policy_rule_time",
        "idx_observe_only_policy_eval_status",
    }
    with _stage16b_connection() as connection:
        rows = list(connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='observe_only_policy_evaluations'"
        ))
        names = {row["name"] for row in rows}

    assert expected.issubset(names)


def test_indexes_target_locked_columns() -> None:
    """The three Stage 16B indexes index exactly the locked column tuples."""

    locked = {
        "idx_observe_only_policy_eval_decision": ("alert_decision_id",),
        "idx_observe_only_policy_eval_policy_rule_time": (
            "policy_hash", "rule_id", "evaluated_at_utc",
        ),
        "idx_observe_only_policy_eval_status": ("evaluation_status",),
    }
    with _stage16b_connection() as connection:
        for index_name, expected_columns in locked.items():
            cols = tuple(
                r["name"]
                for r in connection.execute(f"PRAGMA index_info({index_name})")
            )
            assert cols == expected_columns, (
                f"{index_name} indexes {cols}, expected {expected_columns}"
            )


# ---------------------------------------------------------------------------
# CHECK constraint rejections
# ---------------------------------------------------------------------------


def _insert_row(
    connection: sqlite3.Connection,
    *,
    alert_decision_id: int,
    tier_name_snapshot: str | None,
    policy_hash: str,
    rule_id: str,
    evaluation_status: str,
    matched: int,
    would_have_blocked: int,
    unevaluable_reason: str | None,
    predicate_snapshot_json: str,
    evaluated_at_utc: str,
    created_at_utc: str,
) -> None:
    connection.execute(
        """
        INSERT INTO observe_only_policy_evaluations (
            alert_decision_id, tier_name_snapshot, policy_hash, rule_id,
            evaluation_status, matched, would_have_blocked,
            unevaluable_reason, predicate_snapshot_json, evaluated_at_utc,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alert_decision_id, tier_name_snapshot, policy_hash, rule_id,
            evaluation_status, matched, would_have_blocked,
            unevaluable_reason, predicate_snapshot_json, evaluated_at_utc,
            created_at_utc,
        ),
    )


def _valid_base(rule_id: str = "rule_a", **overrides) -> dict:
    base = {
        "alert_decision_id": 1,
        "tier_name_snapshot": "T1",
        "policy_hash": "sha256:" + "a" * 64,
        "rule_id": rule_id,
        "evaluation_status": "NOT_MATCHED",
        "matched": 0,
        "would_have_blocked": 0,
        "unevaluable_reason": None,
        "predicate_snapshot_json": "{}",
        "evaluated_at_utc": "2026-05-13T12:00:00+00:00",
        "created_at_utc": "2026-05-13T12:00:00+00:00",
    }
    base.update(overrides)
    return base


def test_invalid_evaluation_status_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(evaluation_status="BOGUS"))


def test_matched_value_2_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(matched=2))


def test_would_have_blocked_value_2_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(would_have_blocked=2))


def test_matched_status_with_matched_zero_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(
            evaluation_status="MATCHED",
            matched=0,
            would_have_blocked=1,
        ))


def test_not_matched_status_with_would_have_blocked_one_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(
            evaluation_status="NOT_MATCHED",
            matched=0,
            would_have_blocked=1,
        ))


def test_unevaluable_status_with_null_reason_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(
            evaluation_status="UNEVALUABLE",
            matched=0,
            would_have_blocked=0,
            unevaluable_reason=None,
        ))


def test_matched_status_with_non_null_reason_rejected() -> None:
    with _stage16b_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        _insert_row(connection, **_valid_base(
            evaluation_status="MATCHED",
            matched=1,
            would_have_blocked=1,
            unevaluable_reason="some_reason",
        ))


def test_three_valid_postures_accepted() -> None:
    """Sanity: each of the three CHECK-conforming postures inserts cleanly."""

    with _stage16b_connection() as connection:
        _insert_row(connection, **_valid_base(
            rule_id="matched_row",
            evaluation_status="MATCHED",
            matched=1,
            would_have_blocked=1,
            unevaluable_reason=None,
        ))
        _insert_row(connection, **_valid_base(
            rule_id="not_matched_row",
            evaluation_status="NOT_MATCHED",
            matched=0,
            would_have_blocked=0,
            unevaluable_reason=None,
        ))
        _insert_row(connection, **_valid_base(
            rule_id="unevaluable_row",
            evaluation_status="UNEVALUABLE",
            matched=0,
            would_have_blocked=0,
            unevaluable_reason="tier_name_missing_on_decision",
        ))
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM observe_only_policy_evaluations"
        ).fetchone()["c"]
    assert count == 3


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_apply_stage16b_schema_is_idempotent() -> None:
    path = _temporary_phx2_db_path()
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        apply_stage16b_schema(connection)
        apply_stage16b_schema(connection)

        columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(observe_only_policy_evaluations)"
            )
        ]
        version_count = connection.execute(
            "SELECT COUNT(*) AS c FROM schema_migrations WHERE version = ?",
            (STAGE_16B_VERSION,),
        ).fetchone()["c"]
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)

    assert {name for name, _, _ in _LOCKED_COLUMNS}.issubset(set(columns))
    assert version_count == 1


def test_apply_stage16b_observe_only_policy_evaluations_is_rerunnable() -> None:
    """Re-apply the per-table function on an already-migrated DB; must not
    raise, alter the table, or duplicate the schema_migrations row."""

    with _stage16b_connection() as connection:
        apply_stage16b_observe_only_policy_evaluations(connection)
        columns = [
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(observe_only_policy_evaluations)"
            )
        ]
        version_count = connection.execute(
            "SELECT COUNT(*) AS c FROM schema_migrations WHERE version = ?",
            (STAGE_16B_VERSION,),
        ).fetchone()["c"]

    assert {name for name, _, _ in _LOCKED_COLUMNS}.issubset(set(columns))
    assert version_count == 1


def test_stage16b_migration_records_schema_row() -> None:
    with _stage16b_connection() as connection:
        rows = list(connection.execute(
            "SELECT version, stage, success FROM schema_migrations "
            "WHERE stage = '16B'"
        ))

    assert len(rows) == 1
    assert rows[0]["version"] == STAGE_16B_VERSION
    assert rows[0]["stage"] == "16B"
    assert rows[0]["success"] == 1


# ---------------------------------------------------------------------------
# Dual-migration parity: PHX2.db.migrations is the single source of truth;
# PHX2.stage16b.migrations re-exports the same objects.
# ---------------------------------------------------------------------------


def test_dual_migration_parity_apply_schema_function() -> None:
    assert stage16b_migrations.apply_stage16b_schema is apply_stage16b_schema


def test_dual_migration_parity_per_table_function() -> None:
    assert (
        stage16b_migrations.apply_stage16b_observe_only_policy_evaluations
        is apply_stage16b_observe_only_policy_evaluations
    )


def test_dual_migration_parity_sql_constant() -> None:
    assert (
        stage16b_migrations.STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL
        == STAGE_16B_OBSERVE_ONLY_POLICY_EVALUATIONS_SQL
    )


def test_dual_migration_parity_version_constant() -> None:
    assert stage16b_migrations.STAGE_16B_VERSION == STAGE_16B_VERSION


# ---------------------------------------------------------------------------
# Migration is NOT auto-applied: a Stage 11 DB has alert_decisions and
# filter_evaluations but does NOT have observe_only_policy_evaluations
# until apply_stage16b_schema is called.
# ---------------------------------------------------------------------------


def test_stage11_db_does_not_create_observe_only_policy_evaluations() -> None:
    path = _temporary_phx2_db_path()
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        apply_stage11_schema(connection)
        row = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='observe_only_policy_evaluations'"
        ).fetchone()
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)

    assert row is None


# ---------------------------------------------------------------------------
# FK runtime rejection -- conditional on PRAGMA foreign_keys ON
# ---------------------------------------------------------------------------
#
# The global PHX2 posture is PRAGMA foreign_keys = OFF (V5 finding;
# documented in PHX2/db/migrations.py and existing test_schema_migrations.py
# at lines 968 and 1379). Stage 16B inherits that posture.
#
# This test toggles PRAGMA foreign_keys = ON for the assertion only,
# proving the FK declaration is well-formed and would reject an orphan
# insert if global enforcement were ever flipped on. It does not change
# the global posture.


def test_fk_runtime_rejection_when_enforcement_enabled() -> None:
    with _stage16b_connection() as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        # Sanity-check the toggle took effect.
        fk_pragma = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        if not fk_pragma:
            pytest.skip("PRAGMA foreign_keys could not be enabled in this SQLite build")

        with pytest.raises(sqlite3.IntegrityError):
            _insert_row(connection, **_valid_base(
                alert_decision_id=99999,  # no such row in alert_decisions
            ))


# ---------------------------------------------------------------------------
# Audit MEDIUM fix: harden migration against malformed pre-existing tables.
# ---------------------------------------------------------------------------
#
# Locked invariant: a table named ``observe_only_policy_evaluations``
# that exists but does not match the locked Stage 16B schema MUST cause
# ``apply_stage16b_observe_only_policy_evaluations`` to raise
# ``Stage16BMigrationError`` BEFORE recording a successful migration
# row. The CLI's M01/M02/M03 existence check is not sufficient on its
# own -- it would otherwise pass on a table with the right name but
# missing UNIQUE / FK / column shape.


def _stage11_connection_with_extra_table(
    extra_table_sql: str,
):
    """Open a fresh Stage-11-migrated sqlite3.Connection and execute
    ``extra_table_sql`` on top.

    Returned as a context manager so tests can ``with ... as connection:``
    and write follow-up assertions on the same connection.
    """

    @contextmanager
    def _ctx() -> Iterator[sqlite3.Connection]:
        path = _temporary_phx2_db_path()
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        try:
            apply_stage11_schema(connection)
            connection.executescript(extra_table_sql)
            yield connection
        finally:
            connection.close()
            _cleanup_temporary_phx2_db(path)

    return _ctx()


def _migration_row_recorded(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT COUNT(*) AS c FROM schema_migrations WHERE version = ?",
        (STAGE_16B_VERSION,),
    ).fetchone()
    return row["c"] >= 1


def test_existing_table_with_only_one_column_raises_and_does_not_record() -> None:
    """Pre-existing single-column ``observe_only_policy_evaluations``
    raises Stage16BMigrationError; no migration row is recorded."""

    bad_sql = (
        "CREATE TABLE observe_only_policy_evaluations (id INTEGER PRIMARY KEY);"
    )
    with _stage11_connection_with_extra_table(bad_sql) as connection:
        with pytest.raises(Stage16BMigrationError) as exc_info:
            apply_stage16b_observe_only_policy_evaluations(connection)

        assert "columns drift" in str(exc_info.value)
        assert not _migration_row_recorded(connection)


def test_existing_table_missing_unique_raises_and_does_not_record() -> None:
    """Table with correct column shape but no UNIQUE constraint."""

    columns_sql_parts = [
        f"{name} {type_} {'NOT NULL' if notnull else ''}".strip()
        for name, type_, notnull in EXPECTED_STAGE_16B_COLUMNS
    ]
    bad_sql = (
        "CREATE TABLE observe_only_policy_evaluations (\n"
        + ",\n".join("    " + p for p in columns_sql_parts)
        + ",\n    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)\n"
        + ");"
    )
    with _stage11_connection_with_extra_table(bad_sql) as connection:
        with pytest.raises(Stage16BMigrationError) as exc_info:
            apply_stage16b_observe_only_policy_evaluations(connection)

        assert "UNIQUE" in str(exc_info.value)
        assert not _migration_row_recorded(connection)


def test_existing_table_missing_fk_raises_and_does_not_record() -> None:
    """Table with correct column shape + UNIQUE but no FK declaration."""

    columns_sql_parts = [
        f"{name} {type_} {'NOT NULL' if notnull else ''}".strip()
        for name, type_, notnull in EXPECTED_STAGE_16B_COLUMNS
    ]
    bad_sql = (
        "CREATE TABLE observe_only_policy_evaluations (\n"
        + ",\n".join("    " + p for p in columns_sql_parts)
        + ",\n    UNIQUE(alert_decision_id, policy_hash, rule_id)\n"
        + ");"
    )
    with _stage11_connection_with_extra_table(bad_sql) as connection:
        with pytest.raises(Stage16BMigrationError) as exc_info:
            apply_stage16b_observe_only_policy_evaluations(connection)

        assert "FOREIGN KEY" in str(exc_info.value)
        assert not _migration_row_recorded(connection)


def test_existing_table_missing_indexes_is_repaired(tmp_path) -> None:
    """A compatible table that has lost one or more indexes is repaired
    via CREATE INDEX IF NOT EXISTS; the migration succeeds and indexes
    are present afterwards."""

    with _stage16b_connection() as connection:
        # Drop two of the three locked indexes to simulate drift.
        connection.execute("DROP INDEX idx_observe_only_policy_eval_decision")
        connection.execute("DROP INDEX idx_observe_only_policy_eval_status")
        connection.commit()

        # Re-apply the migration: should succeed and re-create the indexes.
        apply_stage16b_observe_only_policy_evaluations(connection)

        present = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='observe_only_policy_evaluations'"
            )
        }

    assert set(EXPECTED_STAGE_16B_INDEXES).issubset(present)


def test_compatible_existing_table_idempotent_records_migration_once() -> None:
    """A correctly-shaped existing table is accepted; the migration row
    is recorded but not duplicated across re-applies."""

    with _stage16b_connection() as connection:
        # First re-apply already recorded migration; do it again.
        apply_stage16b_observe_only_policy_evaluations(connection)
        apply_stage16b_observe_only_policy_evaluations(connection)
        version_count = connection.execute(
            "SELECT COUNT(*) AS c FROM schema_migrations WHERE version = ?",
            (STAGE_16B_VERSION,),
        ).fetchone()["c"]

    assert version_count == 1


def test_locked_schema_constants_match_documented_shape() -> None:
    """Documentation test: pin the expected-schema constants so a future
    change to the locked Stage 16B shape surfaces as a deliberate test
    update."""

    assert len(EXPECTED_STAGE_16B_COLUMNS) == 12
    assert EXPECTED_STAGE_16B_COLUMNS[0] == ("id", "INTEGER", 0)
    assert EXPECTED_STAGE_16B_COLUMNS[-1] == ("created_at_utc", "TEXT", 1)
    assert EXPECTED_STAGE_16B_UNIQUE_COLUMNS == (
        "alert_decision_id", "policy_hash", "rule_id",
    )
    assert EXPECTED_STAGE_16B_FOREIGN_KEY == (
        "alert_decisions", "alert_decision_id", "id",
    )
    assert set(EXPECTED_STAGE_16B_INDEXES) == {
        "idx_observe_only_policy_eval_decision",
        "idx_observe_only_policy_eval_policy_rule_time",
        "idx_observe_only_policy_eval_status",
    }


# ---------------------------------------------------------------------------
# Audit re-finding MEDIUM: same-name index with wrong columns must raise.
# ---------------------------------------------------------------------------


def _columns_sql_block() -> str:
    """Render the 12 locked Stage 16B columns as a CREATE TABLE column list."""

    parts = [
        f"{name} {type_} {'NOT NULL' if notnull else ''}".strip()
        for name, type_, notnull in EXPECTED_STAGE_16B_COLUMNS
    ]
    return ",\n".join("    " + p for p in parts)


def _bad_index_table_sql(wrong_index_ddl: str) -> str:
    """Build a Stage-16B-locked-shape table SQL whose only defect is the
    ``wrong_index_ddl`` (which carries a same-name index on the wrong
    column tuple)."""

    return (
        "CREATE TABLE observe_only_policy_evaluations (\n"
        + _columns_sql_block()
        + ",\n    UNIQUE(alert_decision_id, policy_hash, rule_id),"
        + "\n    FOREIGN KEY (alert_decision_id) REFERENCES alert_decisions(id)\n"
        + ");\n"
        + wrong_index_ddl
    )


def test_existing_idx_decision_wrong_column_raises_and_no_migration_row() -> None:
    """idx_observe_only_policy_eval_decision on rule_id instead of
    alert_decision_id raises Stage16BMigrationError."""

    bad_sql = _bad_index_table_sql(
        "CREATE INDEX idx_observe_only_policy_eval_decision "
        "ON observe_only_policy_evaluations(rule_id);"
    )
    with _stage11_connection_with_extra_table(bad_sql) as connection:
        with pytest.raises(Stage16BMigrationError) as exc_info:
            apply_stage16b_observe_only_policy_evaluations(connection)

        message = str(exc_info.value)
        assert "idx_observe_only_policy_eval_decision" in message
        assert "drifted columns" in message
        assert not _migration_row_recorded(connection)


def test_existing_idx_policy_rule_time_wrong_column_order_raises() -> None:
    """idx_observe_only_policy_eval_policy_rule_time with the three
    correct columns but in the wrong order raises
    Stage16BMigrationError."""

    bad_sql = _bad_index_table_sql(
        "CREATE INDEX idx_observe_only_policy_eval_policy_rule_time "
        "ON observe_only_policy_evaluations(rule_id, policy_hash, evaluated_at_utc);"
    )
    with _stage11_connection_with_extra_table(bad_sql) as connection:
        with pytest.raises(Stage16BMigrationError) as exc_info:
            apply_stage16b_observe_only_policy_evaluations(connection)

        message = str(exc_info.value)
        assert "idx_observe_only_policy_eval_policy_rule_time" in message
        assert not _migration_row_recorded(connection)


def test_existing_idx_status_wrong_column_raises() -> None:
    """idx_observe_only_policy_eval_status on matched instead of
    evaluation_status raises Stage16BMigrationError."""

    bad_sql = _bad_index_table_sql(
        "CREATE INDEX idx_observe_only_policy_eval_status "
        "ON observe_only_policy_evaluations(matched);"
    )
    with _stage11_connection_with_extra_table(bad_sql) as connection:
        with pytest.raises(Stage16BMigrationError) as exc_info:
            apply_stage16b_observe_only_policy_evaluations(connection)

        message = str(exc_info.value)
        assert "idx_observe_only_policy_eval_status" in message
        assert not _migration_row_recorded(connection)


def test_wrong_index_does_not_re_record_migration_row() -> None:
    """A correctly-installed Stage 16B DB whose index then drifts to the
    wrong column raises on re-apply and the migration row count stays
    at exactly 1 (no duplicate, no removal)."""

    with _stage16b_connection() as connection:
        # First apply succeeded -> migration row exists.
        before = connection.execute(
            "SELECT COUNT(*) AS c FROM schema_migrations WHERE version = ?",
            (STAGE_16B_VERSION,),
        ).fetchone()["c"]
        assert before == 1

        # Drift an index post-install: drop the correct one, recreate with
        # the wrong column.
        connection.execute("DROP INDEX idx_observe_only_policy_eval_status")
        connection.execute(
            "CREATE INDEX idx_observe_only_policy_eval_status "
            "ON observe_only_policy_evaluations(matched)"
        )
        connection.commit()

        # Re-apply: must raise.
        with pytest.raises(Stage16BMigrationError):
            apply_stage16b_observe_only_policy_evaluations(connection)

        # Migration row count is unchanged: no spurious second row,
        # and the original row was not touched.
        after = connection.execute(
            "SELECT COUNT(*) AS c FROM schema_migrations WHERE version = ?",
            (STAGE_16B_VERSION,),
        ).fetchone()["c"]
        assert after == 1


def test_existing_table_missing_indexes_still_repairs() -> None:
    """Pin: missing indexes (with NO same-name drifted entries) remain
    a repair case, not a refuse. Same as Phase 4 existing test, but
    re-asserted here next to the wrong-column tests to make the
    behavior contract explicit."""

    with _stage16b_connection() as connection:
        for index_name in EXPECTED_STAGE_16B_INDEXES:
            connection.execute(f"DROP INDEX {index_name}")
        connection.commit()

        # Re-apply must succeed (missing indexes are repaired).
        apply_stage16b_observe_only_policy_evaluations(connection)

        present = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='observe_only_policy_evaluations'"
            )
        }

    assert set(EXPECTED_STAGE_16B_INDEXES).issubset(present)


def test_dual_migration_parity_error_class_and_expected_constants() -> None:
    """Stage 16B re-exports the new Stage16BMigrationError + expected-shape
    constants so callers can reference them through the Stage 16B-owned
    import surface."""

    assert stage16b_migrations.Stage16BMigrationError is Stage16BMigrationError
    assert (
        stage16b_migrations.EXPECTED_STAGE_16B_COLUMNS
        is EXPECTED_STAGE_16B_COLUMNS
    )
    assert (
        stage16b_migrations.EXPECTED_STAGE_16B_UNIQUE_COLUMNS
        is EXPECTED_STAGE_16B_UNIQUE_COLUMNS
    )
    assert (
        stage16b_migrations.EXPECTED_STAGE_16B_FOREIGN_KEY
        is EXPECTED_STAGE_16B_FOREIGN_KEY
    )
    assert (
        stage16b_migrations.EXPECTED_STAGE_16B_INDEXES
        is EXPECTED_STAGE_16B_INDEXES
    )
