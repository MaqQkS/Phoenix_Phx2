"""Tests for PHX2 CurveCaptureService."""

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
    PriceCurvePointRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
)
from PHX2.models import (
    ATHConfidence,
    ATHState,
    ATHStatus,
    DataStatus,
    PriceObservation,
    TokenState,
)
from PHX2.services.curve_capture_service import CurveCaptureService


MIGRATION_TIME = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
OBSERVED_30S = datetime(2026, 5, 8, 8, 0, 30, tzinfo=timezone.utc)
OBSERVED_45S = datetime(2026, 5, 8, 8, 0, 45, tzinfo=timezone.utc)
OBSERVED_120S = datetime(2026, 5, 8, 8, 2, tzinfo=timezone.utc)
ATH_TIME = datetime(2026, 5, 8, 8, 0, 45, tzinfo=timezone.utc)
AS_OF_TIME = datetime(2026, 5, 8, 8, 5, tzinfo=timezone.utc)
FALLBACK_NOW = datetime(2026, 5, 8, 8, 6, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"curve_capture_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, CurveCaptureService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        service = CurveCaptureService(
            TokenSequenceRepository(connection),
            PriceObservationRepository(connection),
            PriceCurvePointRepository(connection),
            ath=ATHRepository(connection),
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
    migration_price: float | None = 0.01,
    migration_mcap: float | None = 10000.0,
    migration_time: datetime | None = MIGRATION_TIME,
    last_migration_event_id: int | None = 42,
) -> None:
    TokenSequenceRepository(connection).upsert(
        TokenState(
            token_address="token",
            migration_time=migration_time,
            migration_price=migration_price,
            migration_mcap=migration_mcap,
            last_migration_event_id=last_migration_event_id,
            sequence_phase="post_migration",
            current_status="tracking",
            data_status=DataStatus.OK,
        )
    )


def _insert_price_observation(
    connection: sqlite3.Connection,
    *,
    observed_at: datetime,
    price: float | None = 0.02,
    mcap: float | None = 25000.0,
) -> int:
    return PriceObservationRepository(connection).insert(
        PriceObservation(
            token_address="token",
            observed_at=observed_at,
            source="unit",
            price=price,
            mcap=mcap,
            liquidity_usd=5000.0,
            data_status=DataStatus.OK if price is not None and mcap is not None else DataStatus.PARTIAL,
        )
    )


def _insert_ath(connection: sqlite3.Connection) -> None:
    ATHRepository(connection).upsert_state(
        ATHState(
            token_address="token",
            ath_time=ATH_TIME,
            ath_price=0.04,
            ath_mcap=50000.0,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            data_status=DataStatus.OK,
        )
    )


def test_capture_migration_curve_point_maps_anchor_bucket_and_returns():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_ath(connection)
        selected_price_id = _insert_price_observation(connection, observed_at=OBSERVED_30S)
        _insert_price_observation(
            connection,
            observed_at=OBSERVED_120S,
            price=0.03,
            mcap=30000.0,
        )

        point = service.capture_migration_curve_point(" token ", 60, AS_OF_TIME)
        stored = PriceCurvePointRepository(connection).get("token", "migration:42", 60)

    assert point.id == stored.id
    assert stored.anchor_type == "migration"
    assert stored.anchor_key == "migration:42"
    assert stored.anchor_ref_id == 42
    assert stored.bucket_seconds == 60
    assert stored.bucket_start_time == MIGRATION_TIME
    assert stored.bucket_end_time == datetime(2026, 5, 8, 8, 1, tzinfo=timezone.utc)
    assert stored.observed_at == OBSERVED_30S
    assert stored.price_observation_id == selected_price_id
    assert stored.price == pytest.approx(0.02)
    assert stored.mcap == pytest.approx(25000.0)
    assert stored.normalized_price == pytest.approx(2.0)
    assert stored.normalized_mcap == pytest.approx(2.5)
    assert stored.return_from_anchor == pytest.approx(1.0)
    assert stored.return_from_migration == pytest.approx(1.0)
    assert stored.drawdown_from_ath == pytest.approx(0.5)
    assert stored.time_since_ath_s == pytest.approx(15.0)
    assert stored.data_status == DataStatus.OK
    assert stored.missing_reasons == []


def test_anchor_key_falls_back_to_token_address_without_migration_event_id():
    with _service_context() as (connection, service):
        _insert_token(connection, last_migration_event_id=None)
        _insert_price_observation(connection, observed_at=MIGRATION_TIME)

        point = service.capture_migration_curve_point("token", 0, AS_OF_TIME)

    assert point.anchor_key == "migration:token"
    assert point.anchor_ref_id is None
    assert point.bucket_start_time == MIGRATION_TIME
    assert point.bucket_end_time == MIGRATION_TIME


def test_missing_token_state_creates_missing_curve_point():
    with _service_context() as (_, service):
        point = service.capture_migration_curve_point("token", 60, AS_OF_TIME)

    assert point.data_status == DataStatus.MISSING
    assert point.anchor_key == "migration:token"
    assert point.anchor_time == AS_OF_TIME
    assert point.price is None
    assert point.normalized_price is None
    assert "token_state_missing" in point.missing_reasons


def test_missing_price_observation_creates_missing_curve_point_from_token_state():
    with _service_context() as (connection, service):
        _insert_token(connection)

        point = service.capture_migration_curve_point("token", 60, AS_OF_TIME)

    assert point.data_status == DataStatus.MISSING
    assert point.price is None
    assert point.mcap is None
    assert point.normalized_price is None
    assert point.return_from_anchor is None
    assert "price_observation_missing" in point.missing_reasons


def test_missing_migration_time_creates_missing_curve_point():
    with _service_context() as (connection, service):
        _insert_token(connection, migration_time=None)
        _insert_price_observation(connection, observed_at=AS_OF_TIME)

        point = service.capture_migration_curve_point("token", 60, AS_OF_TIME)

    assert point.data_status == DataStatus.MISSING
    assert point.anchor_time == AS_OF_TIME
    assert point.bucket_end_time == datetime(2026, 5, 8, 8, 6, tzinfo=timezone.utc)
    assert point.age_since_migration_s is None
    assert "migration_time_missing" in point.missing_reasons


def test_missing_migration_price_and_mcap_create_partial_without_zeroes():
    with _service_context() as (connection, service):
        _insert_token(connection, migration_price=None, migration_mcap=None)
        _insert_price_observation(connection, observed_at=OBSERVED_30S)

        point = service.capture_migration_curve_point("token", 60, AS_OF_TIME)

    assert point.data_status == DataStatus.PARTIAL
    assert point.normalized_price is None
    assert point.normalized_mcap is None
    assert point.return_from_anchor is None
    assert point.return_from_migration is None
    assert "migration_price_missing" in point.missing_reasons
    assert "migration_mcap_missing" in point.missing_reasons


def test_missing_price_and_mcap_on_observation_create_partial_without_zeroes():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_price_observation(
            connection,
            observed_at=OBSERVED_30S,
            price=None,
            mcap=None,
        )

        point = service.capture_migration_curve_point("token", 60, AS_OF_TIME)

    assert point.data_status == DataStatus.PARTIAL
    assert point.price is None
    assert point.mcap is None
    assert point.normalized_price is None
    assert point.normalized_mcap is None
    assert "price_missing" in point.missing_reasons
    assert "mcap_missing" in point.missing_reasons


def test_standard_migration_buckets_create_expected_points():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_price_observation(connection, observed_at=MIGRATION_TIME)

        points = service.capture_standard_migration_curve_points("token", AS_OF_TIME)
        stored_points = PriceCurvePointRepository(connection).list_by_anchor(
            "token",
            "migration",
            limit=100,
        )

    assert len(points) == 14
    assert [point.bucket_seconds for point in points] == [
        0,
        15,
        30,
        60,
        120,
        180,
        300,
        600,
        900,
        1800,
        3600,
        7200,
        14400,
        86400,
    ]
    assert len(stored_points) == 14


def test_recomputing_same_curve_bucket_upserts_existing_row():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_price_observation(
            connection,
            observed_at=OBSERVED_30S,
            price=0.015,
            mcap=15000.0,
        )
        first = service.capture_migration_curve_point("token", 60, AS_OF_TIME)

        _insert_price_observation(
            connection,
            observed_at=OBSERVED_45S,
            price=0.025,
            mcap=26000.0,
        )
        second = service.capture_migration_curve_point("token", 60, AS_OF_TIME)
        rows = connection.execute(
            "SELECT id, price, normalized_price FROM price_curve_points"
        ).fetchall()

    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0]["price"] == pytest.approx(0.025)
    assert rows[0]["normalized_price"] == pytest.approx(2.5)


def test_curve_capture_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        _insert_token(connection)
        _insert_price_observation(connection, observed_at=OBSERVED_30S)
        token_count_before = _count(connection, "token_sequence_state")

        service.capture_migration_curve_point("token", 60, AS_OF_TIME)

        assert _count(connection, "token_sequence_state") == token_count_before
        assert _count(connection, "field_features") == 0
        assert _count(connection, "clock_features") == 0
        assert _count(connection, "score_features") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "ath_state") == 0
        assert _count(connection, "ath_events") == 0
        assert _count(connection, "fee_windows") == 0


def test_curve_capture_service_makes_no_network_calls(monkeypatch):
    def fail_socket(*_: object, **__: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_socket)

    with _service_context() as (_, service):
        point = service.capture_migration_curve_point("token", 60, None)

    assert point.anchor_time == FALLBACK_NOW
    assert point.data_status == DataStatus.MISSING
