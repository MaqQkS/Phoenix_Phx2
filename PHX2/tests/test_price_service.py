"""Tests for PHX2 PriceService."""

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
from PHX2.db.repositories import (
    MigrationEventRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
)
from PHX2.models import DataStatus, MigrationEvent, PriceObservation
from PHX2.services.migration_service import MigrationService
from PHX2.services.price_service import PriceService


MIGRATION_TIME = datetime(2026, 5, 8, 7, 0, tzinfo=timezone.utc)
OBSERVED_AT = datetime(2026, 5, 8, 7, 5, tzinfo=timezone.utc)
FALLBACK_NOW = datetime(2026, 5, 8, 7, 6, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"price_service_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, PriceService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5a_schema(connection)
        service = PriceService(
            PriceObservationRepository(connection),
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


def _create_migrated_token(connection: sqlite3.Connection) -> None:
    service = MigrationService(
        MigrationEventRepository(connection),
        TokenSequenceRepository(connection),
        current_time_provider=lambda: MIGRATION_TIME,
    )
    service.ingest_migration(
        MigrationEvent(
            token_address="token",
            pool_address="pool",
            migration_time=MIGRATION_TIME,
            migration_source="test",
            signature="sig-migration",
            migration_price=0.01,
            migration_mcap=10000.0,
            data_status=DataStatus.OK,
        )
    )


def test_ingest_complete_price_updates_existing_token_state():
    with _service_context() as (connection, service):
        _create_migrated_token(connection)
        token_state = service.ingest_price_observation(
            PriceObservation(
                token_address=" token ",
                observed_at=OBSERVED_AT,
                source="dexscreener",
                price=0.02,
                mcap=20000.0,
                liquidity_usd=5000.0,
                source_timestamp=OBSERVED_AT,
                age_seconds=2.0,
                data_status=DataStatus.OK,
            )
        )
        price_row = connection.execute(
            "SELECT * FROM price_observations WHERE token_address = 'token'"
        ).fetchone()
        token_row = connection.execute(
            "SELECT * FROM token_sequence_state WHERE token_address = 'token'"
        ).fetchone()

    assert token_state.token_address == "token"
    assert token_state.current_price == 0.02
    assert token_state.current_mcap == 20000.0
    assert token_state.last_price_update == OBSERVED_AT
    assert token_state.last_price_observation_id == price_row["id"]
    assert token_state.data_status == DataStatus.OK
    assert price_row["liquidity_usd"] == 5000.0
    assert token_row["current_price"] == 0.02
    assert token_row["current_mcap"] == 20000.0
    assert token_row["last_price_update"] == OBSERVED_AT.isoformat()
    assert token_row["last_price_observation_id"] == price_row["id"]


def test_missing_price_and_mcap_remain_null_and_are_explicit():
    with _service_context() as (connection, service):
        _create_migrated_token(connection)
        service.ingest_price_observation(
            PriceObservation(
                token_address="token",
                observed_at=OBSERVED_AT,
                source="dexscreener",
                price=0.02,
                mcap=20000.0,
                data_status=DataStatus.OK,
            )
        )
        token_state = service.ingest_price_observation(
            PriceObservation(
                token_address="token",
                observed_at=FALLBACK_NOW,
                source="dexscreener",
                data_status=DataStatus.PARTIAL,
            )
        )
        price_row = connection.execute(
            """
            SELECT price, mcap, data_status, missing_reasons_json
            FROM price_observations
            WHERE token_address = 'token'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        token_row = connection.execute(
            """
            SELECT current_price, current_mcap, data_status, missing_reasons_json
            FROM token_sequence_state
            WHERE token_address = 'token'
            """
        ).fetchone()

    assert price_row["price"] is None
    assert price_row["mcap"] is None
    assert price_row["data_status"] == "missing"
    assert token_state.current_price == 0.02
    assert token_state.current_mcap == 20000.0
    assert token_state.data_status == DataStatus.MISSING
    assert token_row["current_price"] == 0.02
    assert token_row["current_mcap"] == 20000.0
    assert "price_missing" in token_row["missing_reasons_json"]
    assert "mcap_missing" in token_row["missing_reasons_json"]


def test_missing_observed_at_and_source_fallbacks_are_deterministic():
    with _service_context() as (connection, service):
        _create_migrated_token(connection)
        token_state = service.ingest_price_observation(
            PriceObservation(
                token_address="token",
                price=0.02,
                mcap=20000.0,
                data_status=DataStatus.OK,
            )
        )
        price_row = connection.execute(
            "SELECT observed_at, source, missing_reasons_json FROM price_observations"
        ).fetchone()

    assert token_state.last_price_update == FALLBACK_NOW
    assert "observed_at_missing" in token_state.missing_reasons
    assert "source_missing" in token_state.missing_reasons
    assert price_row["observed_at"] == FALLBACK_NOW.isoformat()
    assert price_row["source"] == "unknown"
    assert "observed_at_missing" in price_row["missing_reasons_json"]
    assert "source_missing" in price_row["missing_reasons_json"]


def test_price_for_unknown_token_creates_partial_token_state():
    with _service_context() as (connection, service):
        token_state = service.ingest_price_observation(
            PriceObservation(
                token_address="orphan",
                observed_at=OBSERVED_AT,
                source="dexscreener",
                price=0.03,
                mcap=30000.0,
                data_status=DataStatus.OK,
            )
        )
        token_row = connection.execute(
            "SELECT * FROM token_sequence_state WHERE token_address = 'orphan'"
        ).fetchone()

    assert token_state.token_address == "orphan"
    assert token_state.sequence_phase == "price_observed"
    assert token_state.current_status == "tracking"
    assert token_state.current_price == 0.03
    assert token_state.current_mcap == 30000.0
    assert token_state.data_status == DataStatus.PARTIAL
    assert "token_state_missing_before_price" in token_state.missing_reasons
    assert token_row["migration_price"] is None
    assert token_row["current_price"] == 0.03


def test_invalid_token_address_raises_value_error():
    with _service_context() as (_, service):
        try:
            service.ingest_price_observation(PriceObservation(token_address=" "))
        except ValueError as exc:
            message = str(exc)
        else:
            message = ""

    assert message == "PriceObservation.token_address is required"


def test_ingest_price_observation_rolls_back_when_token_state_upsert_fails(monkeypatch):
    with _service_context() as (connection, service):
        _create_migrated_token(connection)
        prices_before = _count(connection, "price_observations")

        original_upsert = TokenSequenceRepository.upsert

        def failing_upsert(self, token_state):
            raise RuntimeError("simulated token_sequence upsert failure")

        monkeypatch.setattr(TokenSequenceRepository, "upsert", failing_upsert)
        try:
            with pytest.raises(RuntimeError, match="simulated token_sequence upsert failure"):
                service.ingest_price_observation(
                    PriceObservation(
                        token_address="token",
                        observed_at=OBSERVED_AT,
                        source="dexscreener",
                        price=0.02,
                        mcap=20000.0,
                        data_status=DataStatus.OK,
                    )
                )
        finally:
            monkeypatch.setattr(TokenSequenceRepository, "upsert", original_upsert)

        prices_after = _count(connection, "price_observations")

    assert prices_after == prices_before, (
        "price_observations row count must be unchanged after rollback"
    )
    assert connection.in_transaction is False


def test_price_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        _create_migrated_token(connection)
        service.ingest_price_observation(
            PriceObservation(
                token_address="token",
                observed_at=OBSERVED_AT,
                source="dexscreener",
                price=0.02,
                mcap=20000.0,
                data_status=DataStatus.OK,
            )
        )

        assert _count(connection, "ath_state") == 0
        assert _count(connection, "ath_events") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "raw_pumpswap_events") == 0
