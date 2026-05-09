"""Tests for PHX2 ClockFeatureService."""

import socket
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import (
    ATHRepository,
    ClockFeatureRepository,
    FeeWindowRepository,
    TokenSequenceRepository,
)
from PHX2.models import (
    ATHConfidence,
    ATHState,
    ATHStatus,
    DataStatus,
    FeeWindow,
    TokenState,
)
from PHX2.services.clock_feature_service import ClockFeatureService


MIGRATION_TIME = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
ATH_TIME = datetime(2026, 5, 8, 8, 4, tzinfo=timezone.utc)
LAST_FEE_TIME = datetime(2026, 5, 8, 8, 9, tzinfo=timezone.utc)
AS_OF_TIME = datetime(2026, 5, 8, 8, 10, tzinfo=timezone.utc)
FALLBACK_NOW = datetime(2026, 5, 8, 8, 11, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"clock_feature_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, ClockFeatureService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        service = ClockFeatureService(
            TokenSequenceRepository(connection),
            ClockFeatureRepository(connection),
            ath=ATHRepository(connection),
            fee_windows=FeeWindowRepository(connection),
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


def _insert_token(
    connection: sqlite3.Connection,
    *,
    migration_time: datetime | None = MIGRATION_TIME,
    data_status: DataStatus = DataStatus.OK,
) -> None:
    TokenSequenceRepository(connection).upsert(
        TokenState(
            token_address="token",
            migration_time=migration_time,
            sequence_phase="post_migration",
            current_status="tracking",
            data_status=data_status,
        )
    )


def _insert_ath(
    connection: sqlite3.Connection,
    *,
    ath_time: datetime | None = ATH_TIME,
) -> None:
    ATHRepository(connection).upsert_state(
        ATHState(
            token_address="token",
            ath_time=ath_time,
            ath_price=0.02,
            ath_mcap=20000.0,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            data_status=DataStatus.OK,
        )
    )


def _insert_fee_window(
    connection: sqlite3.Connection,
    *,
    window_seconds: int = 300,
    as_of_time: datetime = AS_OF_TIME,
    last_event_time: datetime | None = LAST_FEE_TIME,
) -> int:
    return FeeWindowRepository(connection).insert(
        FeeWindow(
            token_address="token",
            as_of_time=as_of_time,
            window_seconds=window_seconds,
            event_count=3,
            last_event_time=last_event_time,
            data_status=DataStatus.OK,
        )
    )


def test_build_clock_features_maps_migration_ath_and_fee_timing():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_ath(connection)
        _insert_fee_window(connection)

        features = service.build_clock_features(" token ", AS_OF_TIME)
        stored = ClockFeatureRepository(connection).get_latest("token")

    assert features.id == stored.id
    assert stored.migration_time == MIGRATION_TIME
    assert stored.age_since_migration_s == pytest.approx(600.0)
    assert stored.ath_time == ATH_TIME
    assert stored.time_to_ath_s == pytest.approx(240.0)
    assert stored.time_since_ath_s == pytest.approx(360.0)
    assert stored.last_fee_event_time == LAST_FEE_TIME
    assert stored.time_since_last_fee_event_s == pytest.approx(60.0)
    assert stored.sequence_phase == "post_ath"
    assert stored.phase_reason == "ath_time_present"
    assert stored.data_status == DataStatus.OK
    assert stored.missing_reasons == []


def test_missing_token_state_creates_missing_clock_features():
    with _service_context() as (_, service):
        features = service.build_clock_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.MISSING
    assert features.sequence_phase == "unknown"
    assert features.phase_reason == "token_state_missing"
    assert "token_state_missing" in features.missing_reasons


def test_missing_migration_time_creates_partial_pre_migration_snapshot():
    with _service_context() as (connection, service):
        _insert_token(connection, migration_time=None, data_status=DataStatus.PARTIAL)
        _insert_ath(connection)

        features = service.build_clock_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.PARTIAL
    assert features.migration_time is None
    assert features.age_since_migration_s is None
    assert features.time_to_ath_s is None
    assert features.sequence_phase == "pre_migration"
    assert "migration_time_missing" in features.missing_reasons


def test_missing_ath_is_partial_and_awaiting_ath():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_fee_window(connection)

        features = service.build_clock_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.PARTIAL
    assert features.sequence_phase == "awaiting_ath"
    assert features.ath_time is None
    assert features.time_to_ath_s is None
    assert features.time_since_ath_s is None
    assert "ath_state_missing" in features.missing_reasons


def test_fee_timing_uses_latest_300s_window_when_exact_window_missing():
    latest_300s_as_of = datetime(2026, 5, 8, 8, 9, tzinfo=timezone.utc)
    latest_300s_event = datetime(2026, 5, 8, 8, 8, tzinfo=timezone.utc)
    latest_60s_event = datetime(2026, 5, 8, 8, 9, 30, tzinfo=timezone.utc)
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_ath(connection)
        _insert_fee_window(
            connection,
            window_seconds=300,
            as_of_time=latest_300s_as_of,
            last_event_time=latest_300s_event,
        )
        _insert_fee_window(
            connection,
            window_seconds=60,
            as_of_time=AS_OF_TIME,
            last_event_time=latest_60s_event,
        )

        features = service.build_clock_features("token", AS_OF_TIME)

    assert features.last_fee_event_time == latest_300s_event
    assert features.time_since_last_fee_event_s == pytest.approx(120.0)


def test_missing_fee_timing_does_not_fail_and_records_reason():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_ath(connection)

        features = service.build_clock_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.PARTIAL
    assert features.last_fee_event_time is None
    assert features.time_since_last_fee_event_s is None
    assert "fee_window_timing_missing" in features.missing_reasons


def test_recomputing_same_snapshot_upserts_existing_row():
    updated_fee_time = datetime(2026, 5, 8, 8, 8, tzinfo=timezone.utc)
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_ath(connection)
        _insert_fee_window(connection)
        first = service.build_clock_features("token", AS_OF_TIME)

        _insert_fee_window(connection, last_event_time=updated_fee_time)
        second = service.build_clock_features("token", AS_OF_TIME)
        rows = connection.execute(
            "SELECT id, time_since_last_fee_event_s FROM clock_features"
        ).fetchall()

    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0]["id"] == first.id
    assert rows[0]["time_since_last_fee_event_s"] == pytest.approx(120.0)


def test_clock_feature_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_ath(connection)
        _insert_fee_window(connection)
        token_count_before = _count(connection, "token_sequence_state")
        ath_count_before = _count(connection, "ath_state")
        fee_count_before = _count(connection, "fee_windows")

        service.build_clock_features("token", AS_OF_TIME)

        assert _count(connection, "token_sequence_state") == token_count_before
        assert _count(connection, "ath_state") == ath_count_before
        assert _count(connection, "fee_windows") == fee_count_before
        assert _count(connection, "field_features") == 0
        assert _count(connection, "score_features") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "ath_events") == 0
        assert _count(connection, "price_curve_points") == 0


def test_clock_feature_service_makes_no_network_calls(monkeypatch):
    def fail_socket(*_: object, **__: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_socket)

    with _service_context() as (_, service):
        features = service.build_clock_features("token", None)

    assert features.as_of_time == FALLBACK_NOW
    assert features.data_status == DataStatus.MISSING
