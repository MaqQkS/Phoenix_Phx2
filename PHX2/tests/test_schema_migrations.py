"""Tests for PHX2 Stage 4A/4B schema migrations."""

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import (
    STAGE_4A_VERSION,
    STAGE_4B_VERSION,
    STAGE_5A_VERSION,
    STAGE_5C1_VERSION,
    apply_stage4_schema,
    apply_stage5a_schema,
    apply_stage5c1_schema,
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
