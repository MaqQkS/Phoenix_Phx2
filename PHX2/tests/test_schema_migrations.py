"""Tests for PHX2 Stage 4A/4B schema migrations."""

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import (
    STAGE_4A_VERSION,
    STAGE_4B_VERSION,
    STAGE_5A_VERSION,
    STAGE_5C1_VERSION,
    STAGE_9A_VERSION,
    STAGE_9B_VERSION,
    STAGE_10A_VERSION,
    STAGE_10B_VERSION,
    apply_stage4_schema,
    apply_stage5a_schema,
    apply_stage5c1_schema,
    apply_stage9_alert_decision_extension,
    apply_stage9_outcome_windows_recreate,
    apply_stage9_schema,
    apply_stage10_field_features_extension,
    apply_stage10_filter_evaluations_recreate,
    apply_stage10_schema,
)


REQUIRED_TABLES = {
    "schema_migrations",
    "token_sequence_state",
    "migration_events",
    "price_observations",
    "ath_state",
    "ath_events",
    "alert_decisions",
    "filter_evaluations",
    "fee_windows",
    "field_features",
    "score_features",
    "clock_features",
    "dispatch_events",
    "outcome_windows",
}

STAGE5A_TABLES = REQUIRED_TABLES | {"raw_pumpswap_events"}
STAGE5C1_TABLES = STAGE5A_TABLES | {"price_curve_points"}


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"stage4_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _phx2_connection(*, migrate: bool) -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        if migrate:
            apply_stage4_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


@contextmanager
def _phx2_connection_stage5a() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5a_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


@contextmanager
def _phx2_connection_stage5c1() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _columns(connection: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    return {
        row["name"]: row
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _index_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA index_list({table_name})")
    }


def _index_columns(connection: sqlite3.Connection, index_name: str) -> list[str]:
    return [
        row["name"]
        for row in connection.execute(f"PRAGMA index_info({index_name})")
    ]


def test_get_phx2_connection_alone_creates_no_schema():
    with _phx2_connection(migrate=False) as connection:
        assert _table_names(connection) == set()


def test_stage4_migration_creates_required_tables():
    with _phx2_connection(migrate=True) as connection:
        assert REQUIRED_TABLES <= _table_names(connection)


def test_stage4_migration_records_stage4a_and_stage4b():
    with _phx2_connection(migrate=True) as connection:
        rows = connection.execute(
            "SELECT version, stage, success FROM schema_migrations ORDER BY stage"
        ).fetchall()

    assert [(row["version"], row["stage"], row["success"]) for row in rows] == [
        (STAGE_4A_VERSION, "4A", 1),
        (STAGE_4B_VERSION, "4B", 1),
    ]


def test_stage4_migration_is_idempotent():
    with _phx2_connection(migrate=True) as connection:
        apply_stage4_schema(connection)
        migration_count = connection.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]
        table_count = len(_table_names(connection))

    assert migration_count == 2
    assert table_count == len(REQUIRED_TABLES)


def test_stage5a_migration_creates_raw_pumpswap_events_table():
    with _phx2_connection_stage5a() as connection:
        assert STAGE5A_TABLES <= _table_names(connection)


def test_stage5a_migration_records_stage5a():
    with _phx2_connection_stage5a() as connection:
        rows = connection.execute(
            "SELECT version, stage, success FROM schema_migrations ORDER BY stage"
        ).fetchall()

    assert [(row["version"], row["stage"], row["success"]) for row in rows] == [
        (STAGE_4A_VERSION, "4A", 1),
        (STAGE_4B_VERSION, "4B", 1),
        (STAGE_5A_VERSION, "5A", 1),
    ]


def test_stage5a_migration_is_idempotent():
    with _phx2_connection_stage5a() as connection:
        apply_stage5a_schema(connection)
        migration_count = connection.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]
        table_count = len(_table_names(connection))

    assert migration_count == 3
    assert table_count == len(STAGE5A_TABLES)


def test_stage5c1_migration_creates_price_curve_points_table():
    with _phx2_connection_stage5c1() as connection:
        assert STAGE5C1_TABLES <= _table_names(connection)


def test_stage5c1_migration_records_stage5c1():
    with _phx2_connection_stage5c1() as connection:
        rows = connection.execute(
            "SELECT version, stage, success FROM schema_migrations ORDER BY applied_at"
        ).fetchall()

    assert [(row["version"], row["stage"], row["success"]) for row in rows] == [
        (STAGE_4A_VERSION, "4A", 1),
        (STAGE_4B_VERSION, "4B", 1),
        (STAGE_5A_VERSION, "5A", 1),
        (STAGE_5C1_VERSION, "5C.1", 1),
    ]


def test_stage5c1_migration_is_idempotent():
    with _phx2_connection_stage5c1() as connection:
        apply_stage5c1_schema(connection)
        migration_count = connection.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations"
        ).fetchone()["count"]
        table_count = len(_table_names(connection))

    assert migration_count == 4
    assert table_count == len(STAGE5C1_TABLES)


def test_raw_pumpswap_events_required_columns_exist():
    with _phx2_connection_stage5a() as connection:
        columns = _columns(connection, "raw_pumpswap_events")

    for column_name in [
        "id",
        "observed_at",
        "source",
        "signature",
        "dedupe_key",
        "event_type",
        "raw_payload_json",
        "created_at",
        "data_status",
        "missing_reasons_json",
    ]:
        assert column_name in columns

    assert columns["observed_at"]["notnull"] == 1
    assert columns["source"]["notnull"] == 1
    assert columns["signature"]["notnull"] == 1
    assert columns["dedupe_key"]["notnull"] == 1
    assert columns["event_type"]["notnull"] == 1
    assert columns["price_sol"]["notnull"] == 0
    assert columns["total_fee_sol"]["notnull"] == 0


def test_raw_pumpswap_events_critical_indexes_exist():
    with _phx2_connection_stage5a() as connection:
        indexes = _index_names(connection, "raw_pumpswap_events")

    assert "sqlite_autoindex_raw_pumpswap_events_1" in indexes
    assert "idx_raw_pumpswap_events_token_block_time" in indexes
    assert "idx_raw_pumpswap_events_pool_block_time" in indexes
    assert "idx_raw_pumpswap_events_signature" in indexes
    assert "idx_raw_pumpswap_events_slot" in indexes
    assert "idx_raw_pumpswap_events_event_type" in indexes
    assert "idx_raw_pumpswap_events_created_at" in indexes


def test_raw_pumpswap_events_dedupe_key_is_unique():
    with _phx2_connection_stage5a() as connection:
        values = (
            "2026-05-08T00:00:00+00:00",
            "grpc",
            "sig",
            "sig:0",
            "buy",
            "2026-05-08T00:00:00+00:00",
            "partial",
        )
        connection.execute(
            """
            INSERT INTO raw_pumpswap_events (
                observed_at,
                source,
                signature,
                dedupe_key,
                event_type,
                created_at,
                data_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        try:
            connection.execute(
                """
                INSERT INTO raw_pumpswap_events (
                    observed_at,
                    source,
                    signature,
                    dedupe_key,
                    event_type,
                    created_at,
                    data_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        except sqlite3.IntegrityError:
            duplicate_blocked = True
        else:
            duplicate_blocked = False

    assert duplicate_blocked is True


def test_price_curve_points_required_columns_exist():
    with _phx2_connection_stage5c1() as connection:
        columns = _columns(connection, "price_curve_points")

    for column_name in [
        "id",
        "token_address",
        "anchor_type",
        "anchor_key",
        "anchor_time",
        "anchor_ref_id",
        "bucket_seconds",
        "bucket_start_time",
        "bucket_end_time",
        "observed_at",
        "price_observation_id",
        "price",
        "mcap",
        "liquidity_usd",
        "normalized_price",
        "normalized_mcap",
        "return_from_anchor",
        "return_from_migration",
        "drawdown_from_ath",
        "age_since_migration_s",
        "time_since_ath_s",
        "data_status",
        "missing_reasons_json",
        "created_at",
    ]:
        assert column_name in columns

    assert columns["token_address"]["notnull"] == 1
    assert columns["anchor_type"]["notnull"] == 1
    assert columns["anchor_key"]["notnull"] == 1
    assert columns["anchor_time"]["notnull"] == 1
    assert columns["bucket_seconds"]["notnull"] == 1
    assert columns["price"]["notnull"] == 0
    assert columns["normalized_price"]["notnull"] == 0


def test_price_curve_points_critical_indexes_exist():
    with _phx2_connection_stage5c1() as connection:
        indexes = _index_names(connection, "price_curve_points")
        index_columns = {
            index_name: _index_columns(connection, index_name)
            for index_name in indexes
        }

    assert "sqlite_autoindex_price_curve_points_1" in indexes
    assert ["token_address", "anchor_key", "bucket_seconds"] in index_columns.values()
    assert "idx_price_curve_points_token_anchor_bucket" in indexes
    assert "idx_price_curve_points_anchor_bucket" in indexes
    assert "idx_price_curve_points_data_status" in indexes


def test_price_curve_points_unique_anchor_key_bucket_works_with_null_anchor_ref_id():
    with _phx2_connection_stage5c1() as connection:
        values = (
            "token",
            "migration",
            "migration:token",
            "2026-05-08T00:00:00+00:00",
            None,
            60,
            "2026-05-08T00:00:00+00:00",
            "2026-05-08T00:01:00+00:00",
            "2026-05-08T00:00:00+00:00",
            "missing",
        )
        connection.execute(
            """
            INSERT INTO price_curve_points (
                token_address,
                anchor_type,
                anchor_key,
                anchor_time,
                anchor_ref_id,
                bucket_seconds,
                bucket_start_time,
                bucket_end_time,
                created_at,
                data_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        try:
            connection.execute(
                """
                INSERT INTO price_curve_points (
                    token_address,
                    anchor_type,
                    anchor_key,
                    anchor_time,
                    anchor_ref_id,
                    bucket_seconds,
                    bucket_start_time,
                    bucket_end_time,
                    created_at,
                    data_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        except sqlite3.IntegrityError:
            duplicate_blocked = True
        else:
            duplicate_blocked = False

    assert duplicate_blocked is True


def test_critical_columns_are_present_and_nullable_where_expected():
    with _phx2_connection(migrate=True) as connection:
        score_columns = _columns(connection, "score_features")
        filter_columns = _columns(connection, "filter_evaluations")
        ath_columns = _columns(connection, "ath_events")
        alert_columns = _columns(connection, "alert_decisions")

    for column_name in [
        "field_score",
        "setup_score",
        "clock_score",
        "risk_score",
        "composite_score",
    ]:
        assert score_columns[column_name]["type"] == "REAL"
        assert score_columns[column_name]["notnull"] == 0

    assert filter_columns["alert_decision_id"]["notnull"] == 0
    assert ath_columns["mutation_type"]["notnull"] == 1
    assert ath_columns["data_limited"]["notnull"] == 1
    assert alert_columns["decision_type"]["notnull"] == 1
    assert alert_columns["primary_reason"]["notnull"] == 1


def test_critical_indexes_are_present():
    with _phx2_connection(migrate=True) as connection:
        fee_indexes = _index_names(connection, "fee_windows")
        alert_indexes = _index_names(connection, "alert_decisions")
        ath_indexes = _index_names(connection, "ath_events")
        outcome_indexes = _index_names(connection, "outcome_windows")

    assert "sqlite_autoindex_fee_windows_1" in fee_indexes
    assert "idx_fee_windows_token_window_time" in fee_indexes
    assert "idx_alert_decisions_token_eval" in alert_indexes
    assert "idx_alert_decisions_decision_type" in alert_indexes
    assert "idx_ath_events_token_time" in ath_indexes
    assert "idx_ath_events_mutation_type" in ath_indexes
    assert "ux_outcome_windows_decision_window" in outcome_indexes
    assert "ux_outcome_windows_baseline_window" in outcome_indexes


def test_score_features_nullable_scores_remain_null():
    with _phx2_connection(migrate=True) as connection:
        connection.execute(
            """
            INSERT INTO score_features (
                token_address,
                as_of_time,
                score_version,
                created_at,
                data_status
            )
            VALUES ('token', '2026-05-08T00:00:00+00:00', 'score_v0_observe_only',
                    '2026-05-08T00:00:00+00:00', 'missing')
            """
        )
        row = connection.execute(
            """
            SELECT field_score, setup_score, clock_score, risk_score, composite_score
            FROM score_features
            WHERE token_address = 'token'
            """
        ).fetchone()

    assert row["field_score"] is None
    assert row["setup_score"] is None
    assert row["clock_score"] is None
    assert row["risk_score"] is None
    assert row["composite_score"] is None


def test_ath_events_store_core_mutation_cases():
    mutation_types = [
        "ath_raised",
        "ath_no_change",
        "ath_rejected_lower",
        "ath_confidence_changed",
        "ath_data_limited",
    ]
    with _phx2_connection(migrate=True) as connection:
        for mutation_type in mutation_types:
            connection.execute(
                """
                INSERT INTO ath_events (
                    token_address,
                    event_time,
                    status_before,
                    status_after,
                    confidence_before,
                    confidence_after,
                    mutation_type,
                    accepted,
                    data_limited,
                    created_at,
                    data_status
                )
                VALUES (?, '2026-05-08T00:00:00+00:00', 'unknown', 'provisional',
                        'unknown', 'low', ?, 0, ?, '2026-05-08T00:00:00+00:00',
                        'partial')
                """,
                ("token", mutation_type, 1 if mutation_type == "ath_data_limited" else 0),
            )
        stored = {
            row["mutation_type"]
            for row in connection.execute("SELECT mutation_type FROM ath_events")
        }

    assert stored == set(mutation_types)


def test_alert_decisions_store_would_alert_skip_block_and_error():
    decision_rows = [
        ("would_alert", "would_alert", 1, 0, 0),
        ("skip", "price_stale", 0, 0, 1),
        ("block", "filter_blocked", 0, 1, 0),
        ("error", "error", 0, 0, 0),
    ]
    with _phx2_connection(migrate=True) as connection:
        for decision_type, reason, would_alert, blocked, skipped in decision_rows:
            connection.execute(
                """
                INSERT INTO alert_decisions (
                    token_address,
                    evaluated_at,
                    decision_type,
                    primary_reason,
                    would_alert,
                    blocked,
                    skipped,
                    ath_status,
                    ath_confidence,
                    policy_version,
                    created_at,
                    data_status
                )
                VALUES ('token', '2026-05-08T00:00:00+00:00', ?, ?, ?, ?, ?,
                        'unknown', 'unknown', 'policy_v0_placeholder',
                        '2026-05-08T00:00:00+00:00', 'partial')
                """,
                (decision_type, reason, would_alert, blocked, skipped),
            )
        stored = {
            row["decision_type"]
            for row in connection.execute("SELECT decision_type FROM alert_decisions")
        }

    assert stored == {"would_alert", "skip", "block", "error"}


# ---------------------------------------------------------------------------
# Stage 9 migrations
# ---------------------------------------------------------------------------


@contextmanager
def _phx2_connection_stage9() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage9_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def test_stage9_migration_creates_new_outcome_windows_schema():
    with _phx2_connection_stage9() as connection:
        columns = _columns(connection, "outcome_windows")

    expected_columns = {
        "id",
        "alert_decision_id",
        "token_address",
        "window_seconds",
        "window_start_time",
        "window_end_time",
        "alert_price",
        "alert_mcap",
        "max_price",
        "max_mcap",
        "max_observation_time",
        "min_price",
        "min_mcap",
        "min_observation_time",
        "max_return_multiple",
        "max_return_pct",
        "min_return_multiple",
        "min_return_pct",
        "max_drawdown_from_peak_pct",
        "time_to_max_return_seconds",
        "hit_2x",
        "hit_3x",
        "hit_5x",
        "observations_count",
        "first_observation_time",
        "last_observation_time",
        "data_status",
        "created_at",
    }
    assert expected_columns <= set(columns)
    # Stage 4B scaffolding columns must be gone.
    assert "decision_id" not in columns
    assert "baseline_alert_id" not in columns
    assert "entry_price" not in columns
    assert "activity_status" not in columns
    assert "death_label" not in columns
    assert "missing_reasons_json" not in columns


def test_stage9_migration_creates_alert_decision_current_price_columns():
    with _phx2_connection_stage9() as connection:
        columns = _columns(connection, "alert_decisions")

    assert "current_price" in columns
    assert "current_mcap" in columns
    assert columns["current_price"]["type"] == "REAL"
    assert columns["current_mcap"]["type"] == "REAL"
    # Stage 9 fields are nullable — backfill is out of scope for v0.
    assert columns["current_price"]["notnull"] == 0
    assert columns["current_mcap"]["notnull"] == 0


def test_stage9_migration_records_stage9a_and_stage9b():
    with _phx2_connection_stage9() as connection:
        rows = connection.execute(
            "SELECT version, stage, success FROM schema_migrations "
            "ORDER BY applied_at"
        ).fetchall()

    versions = [(row["version"], row["stage"], row["success"]) for row in rows]
    assert (STAGE_9A_VERSION, "9A", 1) in versions
    assert (STAGE_9B_VERSION, "9B", 1) in versions


def test_stage9_migration_is_idempotent():
    with _phx2_connection_stage9() as connection:
        # Re-running on a freshly migrated DB must succeed (outcome_windows is
        # empty, alert_decisions columns exist) and leave the schema intact.
        apply_stage9_alert_decision_extension(connection)
        apply_stage9_outcome_windows_recreate(connection)

        # Columns still exactly two of each.
        columns = _columns(connection, "alert_decisions")
        assert "current_price" in columns
        assert "current_mcap" in columns


def test_stage9_recreate_refuses_when_outcome_windows_has_rows():
    # Scaffold-with-rows safety case: the table has Stage 4B's shape (the
    # scaffold uses ``decision_id``, not ``alert_decision_id``) and contains
    # real rows. Stage 9 must refuse to drop because the scaffold's columns
    # are incompatible with the new schema.
    with _phx2_connection_stage5c1() as connection:
        connection.execute(
            """
            INSERT INTO outcome_windows (
                decision_id, token_address, window_seconds,
                window_start_time, window_end_time, data_status, created_at
            )
            VALUES (1, 'token', 300, '2026-05-08T00:00:00+00:00',
                    '2026-05-08T00:05:00+00:00', 'partial',
                    '2026-05-08T00:05:01+00:00')
            """
        )
        connection.commit()

        with pytest.raises(RuntimeError, match="safety check"):
            apply_stage9_outcome_windows_recreate(connection)

        # Table must still exist with the row preserved.
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM outcome_windows"
        ).fetchone()["count"]
        assert count == 1


def test_stage9_recreate_is_noop_on_already_stage9_db():
    # Operational idempotency: Stage 9B may be re-applied against a populated
    # Stage 9 DB without dropping the table. Existing Stage 9 rows must
    # survive the second call. This is the path future stages (10+) will hit
    # whenever migrate_phx2_schema runs against a DB where Stage 9 has
    # already been applied.
    with _phx2_connection_stage9() as connection:
        connection.execute(
            """
            INSERT INTO outcome_windows (
                alert_decision_id, token_address, window_seconds,
                window_start_time, window_end_time, data_status, created_at
            )
            VALUES (1, 'token', 300, '2026-05-08T00:00:00+00:00',
                    '2026-05-08T00:05:00+00:00', 'COMPLETE',
                    '2026-05-08T00:05:01+00:00')
            """
        )
        connection.commit()
        before_rowid = connection.execute(
            "SELECT id FROM outcome_windows"
        ).fetchone()["id"]

        # Re-apply: must not raise, must not drop the table.
        apply_stage9_outcome_windows_recreate(connection)

        rows = connection.execute(
            "SELECT id, alert_decision_id, data_status FROM outcome_windows"
        ).fetchall()
        assert len(rows) == 1
        # Same id proves the table wasn't dropped and recreated.
        assert rows[0]["id"] == before_rowid
        assert rows[0]["alert_decision_id"] == 1
        assert rows[0]["data_status"] == "COMPLETE"
        # Stage 9B version row is still present (INSERT OR IGNORE — exactly
        # one row regardless of how many times the migration is run).
        version_count = connection.execute(
            "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
            (STAGE_9B_VERSION,),
        ).fetchone()["count"]
        assert version_count == 1


def test_stage9_outcome_windows_unique_index_prevents_duplicate_rows():
    with _phx2_connection_stage9() as connection:
        sql = """
            INSERT INTO outcome_windows (
                alert_decision_id, token_address, window_seconds,
                window_start_time, window_end_time, data_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            1,
            "token",
            300,
            "2026-05-08T00:00:00+00:00",
            "2026-05-08T00:05:00+00:00",
            "COMPLETE",
            "2026-05-08T00:05:01+00:00",
        )
        connection.execute(sql, params)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(sql, params)


# ----------------------------------------------------------------------
# Stage 10 -- filter_evaluations extension + field_features.event_count_5m
# ----------------------------------------------------------------------


@contextmanager
def _phx2_connection_stage10() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage10_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


# T4.1
def test_t4_1_filter_evaluations_has_threshold_version_and_output_reason_json():
    with _phx2_connection_stage10() as connection:
        columns = _columns(connection, "filter_evaluations")

    assert "threshold_version" in columns
    assert "output_reason_json" in columns


# T4.2
def test_t4_2_threshold_version_is_not_null():
    with _phx2_connection_stage10() as connection:
        columns = _columns(connection, "filter_evaluations")
        threshold_version_col = columns["threshold_version"]

    # PRAGMA table_info: notnull column == 1 means NOT NULL.
    assert threshold_version_col["notnull"] == 1


# T4.3
def test_t4_3_output_reason_json_is_nullable():
    with _phx2_connection_stage10() as connection:
        columns = _columns(connection, "filter_evaluations")
        output_reason_col = columns["output_reason_json"]

    assert output_reason_col["notnull"] == 0


def _insert_filter_evaluation_raw(
    connection: sqlite3.Connection,
    *,
    label: str = "NORMAL",
    score: float = 0.10,
    alert_decision_id: int = 1,
    filter_version: str = "fee_gate_v1_no_bribes",
    threshold_version: str = "thresholds_v0_observe_only",
) -> None:
    connection.execute(
        """
        INSERT INTO filter_evaluations (
            token_address, as_of_time, alert_decision_id, filter_name,
            filter_version, threshold_version, label, score, would_block,
            policy_action, reason, input_snapshot_json, output_reason_json,
            created_at, data_status, missing_reasons_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "token",
            "2026-05-10T14:30:00+00:00",
            alert_decision_id,
            "fee_gate",
            filter_version,
            threshold_version,
            label,
            score,
            0,
            "observe",
            None,
            "{}",
            None,
            "2026-05-10T14:30:00+00:00",
            "ok",
            "[]",
        ),
    )


# T4.4
def test_t4_4_label_check_accepts_five_values_and_rejects_others():
    with _phx2_connection_stage10() as connection:
        # Accept each of the five enum values.
        for i, label in enumerate(
            ["NORMAL", "ELEVATED", "SUSPICIOUS", "SCAM_LIKELY", "UNKNOWN"]
        ):
            _insert_filter_evaluation_raw(
                connection, label=label, alert_decision_id=i + 1
            )
        # Reject a different label.
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            _insert_filter_evaluation_raw(
                connection, label="Normal", alert_decision_id=10
            )

    assert "CHECK constraint failed" in str(exc_info.value)


# T4.5
def test_t4_5_score_check_rejects_out_of_range_accepts_valid_and_null():
    with _phx2_connection_stage10() as connection:
        _insert_filter_evaluation_raw(connection, score=0.0, alert_decision_id=1)
        _insert_filter_evaluation_raw(connection, score=0.5, alert_decision_id=2)
        _insert_filter_evaluation_raw(connection, score=1.0, alert_decision_id=3)
        # NULL score:
        connection.execute(
            """
            INSERT INTO filter_evaluations (
                token_address, as_of_time, alert_decision_id, filter_name,
                filter_version, threshold_version, label, score, would_block,
                policy_action, reason, input_snapshot_json, output_reason_json,
                created_at, data_status, missing_reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "token",
                "2026-05-10T14:30:00+00:00",
                4,
                "fee_gate",
                "fee_gate_v1_no_bribes",
                "thresholds_v0_observe_only",
                "UNKNOWN",
                None,
                0,
                "observe",
                None,
                "{}",
                None,
                "2026-05-10T14:30:00+00:00",
                "missing",
                "[]",
            ),
        )

        # Reject negative.
        with pytest.raises(sqlite3.IntegrityError):
            _insert_filter_evaluation_raw(
                connection, score=-0.001, alert_decision_id=5
            )
        # Reject > 1.0.
        with pytest.raises(sqlite3.IntegrityError):
            _insert_filter_evaluation_raw(
                connection, score=1.001, alert_decision_id=6
            )


# T4.6
def test_t4_6_unique_constraint_on_four_tuple():
    with _phx2_connection_stage10() as connection:
        _insert_filter_evaluation_raw(connection, alert_decision_id=42)

        # Same four-tuple -> rejected.
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            _insert_filter_evaluation_raw(connection, alert_decision_id=42)

        # Different threshold_version -> accepted.
        _insert_filter_evaluation_raw(
            connection,
            alert_decision_id=42,
            threshold_version="thresholds_other_v1",
        )

    assert "UNIQUE constraint failed" in str(exc_info.value)


# T4.7 (unconditional per C1 -- declaration introspection only)
def test_t4_7_fk_declaration_present_via_pragma_foreign_key_list():
    with _phx2_connection_stage10() as connection:
        rows = list(
            connection.execute("PRAGMA foreign_key_list(filter_evaluations)")
        )

    matching = [
        row
        for row in rows
        if row["table"] == "alert_decisions" and row["from"] == "alert_decision_id"
    ]
    assert len(matching) == 1, (
        "Expected exactly one FK declaration on filter_evaluations.alert_decision_id "
        "referencing alert_decisions(id); declaration is required even though "
        "PRAGMA foreign_keys is OFF in Stage 10."
    )


# Stage 10 migration housekeeping tests


def test_stage10_migration_records_stage10a_and_stage10b():
    with _phx2_connection_stage10() as connection:
        rows = connection.execute(
            "SELECT version, stage, success FROM schema_migrations "
            "WHERE stage IN ('10A', '10B') ORDER BY stage"
        ).fetchall()

    assert [(row["version"], row["stage"], row["success"]) for row in rows] == [
        (STAGE_10A_VERSION, "10A", 1),
        (STAGE_10B_VERSION, "10B", 1),
    ]


def test_stage10_migration_is_idempotent():
    # Follows the Stage 9 pattern (test_stage9_migration_is_idempotent):
    # re-apply the individual Stage 10 sub-functions on an already-migrated
    # Stage 10 DB. Re-running the full apply_stage10_schema chain would
    # transit INDEX_SQL over the renamed outcome_windows.alert_decision_id
    # column -- a pre-existing apply_stage9_schema limitation also avoided
    # by the Stage 9 idempotency test.
    with _phx2_connection_stage10() as connection:
        apply_stage10_field_features_extension(connection)
        apply_stage10_filter_evaluations_recreate(connection)

        rows = list(
            connection.execute(
                "SELECT stage, COUNT(*) AS n FROM schema_migrations "
                "WHERE stage IN ('10A', '10B') GROUP BY stage ORDER BY stage"
            )
        )
        columns = _columns(connection, "filter_evaluations")

    assert [(row["stage"], row["n"]) for row in rows] == [("10A", 1), ("10B", 1)]
    assert "threshold_version" in columns


_STAGE_4_FILTER_EVALUATIONS_SQL = """
DROP TABLE IF EXISTS filter_evaluations;
CREATE TABLE filter_evaluations (
    id INTEGER PRIMARY KEY,
    token_address TEXT NOT NULL,
    as_of_time TEXT NOT NULL,
    alert_decision_id INTEGER,
    filter_name TEXT NOT NULL,
    filter_version TEXT NOT NULL,
    label TEXT NOT NULL,
    score REAL,
    would_block INTEGER NOT NULL,
    policy_action TEXT NOT NULL,
    reason TEXT,
    input_snapshot_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    data_status TEXT NOT NULL,
    missing_reasons_json TEXT NOT NULL DEFAULT '[]'
);
"""


def test_stage10_recreate_refuses_when_filter_evaluations_has_rows():
    # Hand-build the pre-Stage-10 (Stage 4) shape -- no threshold_version
    # column, no CHECK/UNIQUE/FK -- and seed it with one row. Then call the
    # recreate function and assert it refuses with the safety-check error.
    with _phx2_connection(migrate=False) as connection:
        apply_stage9_schema(connection)
        connection.executescript(_STAGE_4_FILTER_EVALUATIONS_SQL)
        connection.execute(
            """
            INSERT INTO filter_evaluations (
                token_address, as_of_time, alert_decision_id, filter_name,
                filter_version, label, score, would_block, policy_action,
                reason, input_snapshot_json, created_at, data_status,
                missing_reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "token",
                "2026-05-10T14:30:00+00:00",
                1,
                "fee_gate",
                "fee_gate_v0_placeholder",
                "Normal",
                0.0,
                0,
                "observe",
                None,
                "{}",
                "2026-05-10T14:30:00+00:00",
                "ok",
                "[]",
            ),
        )

        with pytest.raises(RuntimeError) as exc_info:
            apply_stage10_filter_evaluations_recreate(connection)

        # The original row must still be present (refusal did not drop).
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM filter_evaluations"
        ).fetchone()["count"]

    assert "refused to drop filter_evaluations" in str(exc_info.value)
    assert count == 1


def test_stage10_field_features_event_count_5m_column_is_nullable():
    with _phx2_connection_stage10() as connection:
        columns = _columns(connection, "field_features")

    assert "event_count_5m" in columns
    assert columns["event_count_5m"]["notnull"] == 0


def test_stage10_field_features_extension_is_idempotent():
    with _phx2_connection_stage10() as connection:
        apply_stage10_field_features_extension(connection)
        apply_stage10_field_features_extension(connection)
        columns = _columns(connection, "field_features")

    assert "event_count_5m" in columns
    # Idempotent: the column is not duplicated.
    matching = [name for name in columns if name == "event_count_5m"]
    assert len(matching) == 1


def test_apply_stage10_schema_is_rerunnable():
    """Calling apply_stage10_schema() twice on the same DB must succeed.

    S1 fix: the migration chain transits INDEX_SQL via apply_stage4_schema
    on every entry. On a second call, outcome_windows has already been
    recreated to the Stage 9B shape, which lacks decision_id /
    baseline_alert_id / death_label. Pre-S1, INDEX_SQL would fail at the
    first stale outcome_windows DDL on the rebuilt table. Post-S1, those
    three DDLs live in _apply_outcome_windows_scaffold_indexes which
    skips any whose referenced column is absent.
    """

    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage10_schema(connection)
        apply_stage10_schema(connection)

        filter_columns = _columns(connection, "filter_evaluations")
        field_columns = _columns(connection, "field_features")
        migrations = {
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations"
            )
        }
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)

    assert "threshold_version" in filter_columns
    assert "event_count_5m" in field_columns
    assert STAGE_10A_VERSION in migrations
    assert STAGE_10B_VERSION in migrations
