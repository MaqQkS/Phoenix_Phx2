"""Tests for PHX2 MigrationService."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage5a_schema
from PHX2.db.repositories import MigrationEventRepository, TokenSequenceRepository
from PHX2.models import DataStatus, MigrationEvent
from PHX2.services.migration_service import MigrationService


NOW = datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc)
FALLBACK_NOW = datetime(2026, 5, 8, 7, 1, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"migration_service_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, MigrationService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5a_schema(connection)
        service = MigrationService(
            MigrationEventRepository(connection),
            TokenSequenceRepository(connection),
            current_time_provider=lambda: FALLBACK_NOW,
        )
        yield connection, service
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    return int(
        connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()[
            "count"
        ]
    )


def test_ingest_complete_migration_writes_event_and_token_state():
    with _service_context() as (connection, service):
        token_state = service.ingest_migration(
            MigrationEvent(
                token_address=" token ",
                pool_address="pool",
                migration_time=NOW,
                migration_source="normalized_test",
                signature="sig-complete",
                slot=123,
                block_time=NOW,
                migration_price=0.01,
                migration_mcap=10000.0,
                raw_payload_json={"source": "unit"},
                data_status=DataStatus.OK,
            )
        )
        event_row = connection.execute(
            "SELECT * FROM migration_events WHERE signature = 'sig-complete'"
        ).fetchone()
        token_row = connection.execute(
            "SELECT * FROM token_sequence_state WHERE token_address = 'token'"
        ).fetchone()

    assert token_state.token_address == "token"
    assert token_state.pool_address == "pool"
    assert token_state.migration_time == NOW
    assert token_state.migration_source == "normalized_test"
    assert token_state.migration_price == 0.01
    assert token_state.migration_mcap == 10000.0
    assert token_state.sequence_phase == "post_migration"
    assert token_state.current_status == "tracking"
    assert token_state.data_status == DataStatus.OK
    assert token_state.last_migration_event_id == event_row["id"]
    assert token_row["last_migration_event_id"] == event_row["id"]
    assert token_row["migration_price"] == 0.01
    assert token_row["migration_mcap"] == 10000.0


def test_missing_price_mcap_and_time_are_explicit_and_remain_null():
    with _service_context() as (connection, service):
        token_state = service.ingest_migration(
            MigrationEvent(
                token_address="token",
                pool_address="pool",
                migration_source="normalized_test",
                signature="sig-missing",
                data_status=DataStatus.PARTIAL,
            )
        )
        token_row = connection.execute(
            """
            SELECT migration_time, migration_price, migration_mcap, data_status,
                   missing_reasons_json
            FROM token_sequence_state
            WHERE token_address = 'token'
            """
        ).fetchone()

    assert token_state.migration_time == FALLBACK_NOW
    assert token_state.migration_price is None
    assert token_state.migration_mcap is None
    assert token_state.data_status == DataStatus.MISSING
    assert token_row["migration_time"] == FALLBACK_NOW.isoformat()
    assert token_row["migration_price"] is None
    assert token_row["migration_mcap"] is None
    assert token_row["data_status"] == "missing"
    assert "migration_time_missing" in token_row["missing_reasons_json"]
    assert "migration_price_missing" in token_row["missing_reasons_json"]
    assert "migration_mcap_missing" in token_row["missing_reasons_json"]


def test_block_time_is_used_when_migration_time_is_missing():
    with _service_context() as (_, service):
        token_state = service.ingest_migration(
            MigrationEvent(
                token_address="token",
                pool_address="pool",
                block_time=NOW,
                signature="sig-block-time",
                migration_price=0.01,
                migration_mcap=10000.0,
                data_status=DataStatus.OK,
            )
        )

    assert token_state.migration_time == NOW
    assert "migration_time_missing" in token_state.missing_reasons
    assert token_state.data_status == DataStatus.PARTIAL


def test_duplicate_token_migration_is_deterministic_and_does_not_insert_again():
    with _service_context() as (connection, service):
        first = service.ingest_migration(
            MigrationEvent(
                token_address="token",
                pool_address="pool",
                migration_time=NOW,
                signature="sig-first",
                migration_price=0.01,
                migration_mcap=10000.0,
                data_status=DataStatus.OK,
            )
        )
        duplicate = service.ingest_migration(
            MigrationEvent(
                token_address="token",
                pool_address="pool-duplicate",
                migration_time=NOW,
                signature="sig-second",
                migration_price=0.02,
                migration_mcap=20000.0,
                data_status=DataStatus.OK,
            )
        )
        token_count = _count(connection, "token_sequence_state")
        migration_count = _count(connection, "migration_events")
        stored = TokenSequenceRepository(connection).get("token")

    assert token_count == 1
    assert migration_count == 1
    assert duplicate.last_migration_event_id == first.last_migration_event_id
    assert duplicate.migration_price == 0.01
    assert duplicate.data_status == DataStatus.PARTIAL
    assert "duplicate_token_migration" in duplicate.missing_reasons
    assert stored.missing_reasons == duplicate.missing_reasons


def test_invalid_token_address_raises_value_error():
    with _service_context() as (_, service):
        try:
            service.ingest_migration(MigrationEvent(token_address=" "))
        except ValueError as exc:
            message = str(exc)
        else:
            message = ""

    assert message == "MigrationEvent.token_address is required"


def test_ingest_migration_rolls_back_when_token_state_upsert_fails(monkeypatch):
    with _service_context() as (connection, service):
        events_before = _count(connection, "migration_events")
        token_count_before = _count(connection, "token_sequence_state")

        original_upsert = TokenSequenceRepository.upsert

        def failing_upsert(self, token_state):
            raise RuntimeError("simulated token_sequence upsert failure")

        monkeypatch.setattr(TokenSequenceRepository, "upsert", failing_upsert)
        try:
            with pytest.raises(RuntimeError, match="simulated token_sequence upsert failure"):
                service.ingest_migration(
                    MigrationEvent(
                        token_address="token",
                        pool_address="pool",
                        migration_time=NOW,
                        signature="sig-rollback",
                        migration_price=0.01,
                        migration_mcap=10000.0,
                        data_status=DataStatus.OK,
                    )
                )
        finally:
            monkeypatch.setattr(TokenSequenceRepository, "upsert", original_upsert)

        events_after = _count(connection, "migration_events")
        token_count_after = _count(connection, "token_sequence_state")

    assert events_after == events_before, (
        "migration_events row count must be unchanged after rollback"
    )
    assert token_count_after == token_count_before, (
        "token_sequence_state row count must be unchanged after rollback"
    )
    assert connection.in_transaction is False


def test_duplicate_signature_path_completes_atomically_for_new_token():
    with _service_context() as (connection, service):
        first = service.ingest_migration(
            MigrationEvent(
                token_address="token-A",
                pool_address="pool-A",
                migration_time=NOW,
                signature="sig-shared",
                migration_price=0.01,
                migration_mcap=10000.0,
                data_status=DataStatus.OK,
            )
        )
        events_after_first = _count(connection, "migration_events")

        duplicate = service.ingest_migration(
            MigrationEvent(
                token_address="token-B",
                pool_address="pool-B",
                migration_time=NOW,
                signature="sig-shared",
                migration_price=0.02,
                migration_mcap=20000.0,
                data_status=DataStatus.OK,
            )
        )

        events_after_duplicate = _count(connection, "migration_events")
        token_a_row = connection.execute(
            "SELECT * FROM token_sequence_state WHERE token_address = 'token-A'"
        ).fetchone()
        token_b_row = connection.execute(
            "SELECT * FROM token_sequence_state WHERE token_address = 'token-B'"
        ).fetchone()

    assert events_after_first == 1
    assert events_after_duplicate == 1, (
        "duplicate-signature path must not insert a second migration_events row"
    )
    assert duplicate.token_address == "token-B"
    assert duplicate.last_migration_event_id is None
    assert "duplicate_migration_signature" in duplicate.missing_reasons
    assert token_a_row is not None
    assert token_a_row["last_migration_event_id"] == first.last_migration_event_id
    assert token_b_row is not None
    assert token_b_row["last_migration_event_id"] is None
    assert "duplicate_migration_signature" in token_b_row["missing_reasons_json"]
    assert connection.in_transaction is False


def test_migration_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        service.ingest_migration(
            MigrationEvent(
                token_address="token",
                migration_time=NOW,
                signature="sig-clean",
                migration_price=0.01,
                migration_mcap=10000.0,
                data_status=DataStatus.OK,
            )
        )

        assert _count(connection, "raw_pumpswap_events") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "ath_events") == 0
