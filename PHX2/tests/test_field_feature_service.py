"""Tests for PHX2 FieldFeatureService."""

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
from PHX2.db.repositories import FeeWindowRepository, FieldFeatureRepository
from PHX2.models import DataStatus, FeeWindow
from PHX2.services.field_feature_service import FieldFeatureService


AS_OF_TIME = datetime(2026, 5, 8, 8, 10, tzinfo=timezone.utc)
FALLBACK_NOW = datetime(2026, 5, 8, 8, 11, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"field_feature_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, FieldFeatureService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        service = FieldFeatureService(
            FeeWindowRepository(connection),
            FieldFeatureRepository(connection),
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


def _fee_window(
    window_seconds: int,
    *,
    events_per_min: float | None = None,
    fees_per_min_sol: float | None = None,
    creator_fee_share: float | None = None,
    lp_fee_share: float | None = None,
    protocol_fee_share: float | None = None,
    buy_sell_count_ratio: float | None = None,
    data_status: DataStatus = DataStatus.OK,
    missing_reasons: list[str] | None = None,
) -> FeeWindow:
    return FeeWindow(
        token_address="token",
        as_of_time=AS_OF_TIME,
        window_seconds=window_seconds,
        event_count=3 if data_status != DataStatus.NO_EVENTS else 0,
        buy_count=2,
        sell_count=1,
        total_fee_sol=0.10,
        lp_fee_sol=0.025,
        protocol_fee_sol=0.033,
        creator_fee_sol=0.042,
        creator_fee_share=creator_fee_share,
        lp_fee_share=lp_fee_share,
        protocol_fee_share=protocol_fee_share,
        events_per_min=events_per_min,
        fees_per_min_sol=fees_per_min_sol,
        buy_sell_count_ratio=buy_sell_count_ratio,
        data_status=data_status,
        missing_reasons=missing_reasons or [],
    )


def _insert_standard_windows(connection: sqlite3.Connection) -> dict[int, int]:
    repository = FeeWindowRepository(connection)
    ids: dict[int, int] = {}
    for window_seconds in [60, 300, 900, 1800, 3600]:
        window = _fee_window(window_seconds)
        if window_seconds == 300:
            window = _fee_window(
                300,
                events_per_min=0.6,
                fees_per_min_sol=0.02,
                creator_fee_share=0.42,
                lp_fee_share=0.25,
                protocol_fee_share=0.33,
                buy_sell_count_ratio=2.0,
            )
        ids[window_seconds] = repository.insert(window)
    return ids


def test_build_field_features_maps_complete_300s_window_and_snapshot_ids():
    with _service_context() as (connection, service):
        fee_window_ids = _insert_standard_windows(connection)

        features = service.build_field_features(" token ", AS_OF_TIME)
        stored = FieldFeatureRepository(connection).get_latest("token")
        raw = connection.execute(
            """
            SELECT fee_window_60s_id, fee_window_300s_id, fee_window_900s_id,
                   fee_window_1800s_id, fee_window_3600s_id
            FROM field_features
            WHERE token_address = 'token'
            """
        ).fetchone()

    assert features.id == stored.id
    assert stored.event_pace_5m == pytest.approx(0.6)
    assert stored.fee_pace_5m_sol == pytest.approx(0.02)
    assert stored.creator_fee_share_5m == pytest.approx(0.42)
    assert stored.lp_fee_share_5m == pytest.approx(0.25)
    assert stored.protocol_fee_share_5m == pytest.approx(0.33)
    assert stored.buy_sell_ratio_5m == pytest.approx(2.0)
    assert stored.data_status == DataStatus.OK
    assert stored.missing_reasons == []
    assert raw["fee_window_60s_id"] == fee_window_ids[60]
    assert raw["fee_window_300s_id"] == fee_window_ids[300]
    assert raw["fee_window_900s_id"] == fee_window_ids[900]
    assert raw["fee_window_1800s_id"] == fee_window_ids[1800]
    assert raw["fee_window_3600s_id"] == fee_window_ids[3600]
    assert stored.fee_window_300s_id == fee_window_ids[300]
    assert stored.raw_snapshot["fee_window_300s_id"] == fee_window_ids[300]
    assert stored.raw_snapshot["fee_window_300s_metrics"] == {
        "events_per_min": 0.6,
        "fees_per_min_sol": 0.02,
        "creator_fee_share": 0.42,
        "lp_fee_share": 0.25,
        "protocol_fee_share": 0.33,
        "buy_sell_count_ratio": 2.0,
        "data_status": "ok",
        "missing_reasons": [],
    }


def test_missing_300s_window_creates_missing_snapshot():
    with _service_context() as (connection, service):
        FeeWindowRepository(connection).insert(_fee_window(60))

        features = service.build_field_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.MISSING
    assert features.event_pace_5m is None
    assert features.fee_pace_5m_sol is None
    assert features.raw_snapshot["fee_window_300s_id"] is None
    assert "fee_window_300s_missing" in features.missing_reasons


def test_no_events_300s_window_creates_no_events_snapshot():
    with _service_context() as (connection, service):
        FeeWindowRepository(connection).insert(
            _fee_window(
                300,
                data_status=DataStatus.NO_EVENTS,
                missing_reasons=["no_raw_events_in_window"],
            )
        )

        features = service.build_field_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.NO_EVENTS
    assert "fee_window_300s_no_events" in features.missing_reasons
    assert features.raw_snapshot["fee_window_300s_metrics"]["data_status"] == "no_events"


def test_partial_300s_window_creates_partial_snapshot():
    with _service_context() as (connection, service):
        FeeWindowRepository(connection).insert(
            _fee_window(
                300,
                events_per_min=0.4,
                fees_per_min_sol=None,
                creator_fee_share=None,
                lp_fee_share=None,
                protocol_fee_share=None,
                buy_sell_count_ratio=None,
                data_status=DataStatus.PARTIAL,
                missing_reasons=["fee_fields_missing"],
            )
        )

        features = service.build_field_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.PARTIAL
    assert features.event_pace_5m == pytest.approx(0.4)
    assert features.fee_pace_5m_sol is None
    assert features.creator_fee_share_5m is None
    assert "fee_window_300s_partial" in features.missing_reasons
    assert (
        features.raw_snapshot["fee_window_300s_metrics"]["missing_reasons"]
        == ["fee_fields_missing"]
    )


def test_missing_noncritical_windows_add_reasons_but_do_not_block_300s_snapshot():
    with _service_context() as (connection, service):
        FeeWindowRepository(connection).insert(
            _fee_window(
                300,
                events_per_min=0.6,
                fees_per_min_sol=0.02,
                creator_fee_share=0.42,
                lp_fee_share=0.25,
                protocol_fee_share=0.33,
                buy_sell_count_ratio=2.0,
            )
        )

        features = service.build_field_features("token", AS_OF_TIME)

    assert features.data_status == DataStatus.OK
    assert features.event_pace_5m == pytest.approx(0.6)
    assert "fee_window_60s_missing" in features.missing_reasons
    assert "fee_window_900s_missing" in features.missing_reasons
    assert "fee_window_1800s_missing" in features.missing_reasons
    assert "fee_window_3600s_missing" in features.missing_reasons


def test_recomputing_same_snapshot_upserts_existing_row():
    with _service_context() as (connection, service):
        repository = FeeWindowRepository(connection)
        repository.insert(
            _fee_window(
                300,
                events_per_min=0.6,
                fees_per_min_sol=0.02,
                creator_fee_share=0.42,
                lp_fee_share=0.25,
                protocol_fee_share=0.33,
                buy_sell_count_ratio=2.0,
            )
        )
        first = service.build_field_features("token", AS_OF_TIME)

        repository.insert(
            _fee_window(
                300,
                events_per_min=1.2,
                fees_per_min_sol=0.04,
                creator_fee_share=0.4,
                lp_fee_share=0.3,
                protocol_fee_share=0.3,
                buy_sell_count_ratio=3.0,
            )
        )
        second = service.build_field_features("token", AS_OF_TIME)
        rows = connection.execute(
            "SELECT id, event_pace_5m FROM field_features"
        ).fetchall()

    assert second.id == first.id
    assert len(rows) == 1
    assert rows[0]["id"] == first.id
    assert rows[0]["event_pace_5m"] == pytest.approx(1.2)


def test_field_feature_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        FeeWindowRepository(connection).insert(
            _fee_window(
                300,
                events_per_min=0.6,
                fees_per_min_sol=0.02,
                creator_fee_share=0.42,
                lp_fee_share=0.25,
                protocol_fee_share=0.33,
                buy_sell_count_ratio=2.0,
            )
        )
        fee_count_before = _count(connection, "fee_windows")

        service.build_field_features("token", AS_OF_TIME)

        assert _count(connection, "fee_windows") == fee_count_before
        assert _count(connection, "score_features") == 0
        assert _count(connection, "clock_features") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "ath_state") == 0
        assert _count(connection, "ath_events") == 0
        assert _count(connection, "token_sequence_state") == 0
        assert _count(connection, "price_curve_points") == 0


def test_field_feature_service_makes_no_network_calls(monkeypatch):
    def fail_socket(*_: object, **__: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_socket)

    with _service_context() as (_, service):
        features = service.build_field_features("token", None)

    assert features.as_of_time == FALLBACK_NOW
    assert features.data_status == DataStatus.MISSING


# ----------------------------------------------------------------------
# Stage 10 -- event_count_5m wiring
# ----------------------------------------------------------------------


# T6.1
def test_t6_1_field_features_schema_has_event_count_5m_column():
    with _service_context() as (connection, _):
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(field_features)")
        }

    assert "event_count_5m" in columns


# T6.2 -- handled by Layer 5 model tests and dataclass annotation; this test
# documents the binding from the service-test perspective.
def test_t6_2_field_features_dataclass_has_event_count_5m_field():
    from PHX2.models import FieldFeatures
    from dataclasses import fields

    field_names = {f.name for f in fields(FieldFeatures)}

    assert "event_count_5m" in field_names


# T6.3
def test_t6_3_build_field_features_populates_event_count_5m_from_300s_window():
    with _service_context() as (connection, service):
        # Build the standard set then overwrite the 300s window with an
        # explicit event_count so the test does not rely on the helper's
        # internal default. The helper does NOT pass event_count for the
        # 300s window, so we replace it.
        repository = FeeWindowRepository(connection)
        for window_seconds in [60, 900, 1800, 3600]:
            repository.insert(_fee_window(window_seconds))
        repository.upsert(
            FeeWindow(
                token_address="token",
                as_of_time=AS_OF_TIME,
                window_seconds=300,
                event_count=480,
                buy_count=240,
                sell_count=240,
                total_fee_sol=0.10,
                lp_fee_sol=0.05,
                protocol_fee_sol=0.03,
                creator_fee_sol=0.02,
                creator_fee_share=0.20,
                lp_fee_share=0.50,
                protocol_fee_share=0.30,
                events_per_min=2.0,
                fees_per_min_sol=0.05,
                buy_sell_count_ratio=1.0,
                data_status=DataStatus.OK,
            )
        )

        features = service.build_field_features("token", AS_OF_TIME)

    assert features.event_count_5m == 480


def test_t6_3_build_field_features_event_count_5m_is_none_when_300s_window_absent():
    with _service_context() as (_, service):
        features = service.build_field_features("token", AS_OF_TIME)

    assert features.event_count_5m is None
    assert features.data_status == DataStatus.MISSING


# T6.4 -- existing field_features round-trip continues to function with
# the new column included; covered by the schema and roundtrip suites that
# already insert and read FieldFeatures rows.
def test_t6_4_existing_field_features_roundtrip_carries_event_count_5m():
    from PHX2.models import FieldFeatures

    with _service_context() as (connection, _):
        repository = FieldFeatureRepository(connection)
        repository.insert(
            FieldFeatures(
                token_address="token",
                as_of_time=AS_OF_TIME,
                event_count_5m=321,
                data_status=DataStatus.OK,
            )
        )
        latest = repository.get_latest("token")

    assert latest is not None
    assert latest.event_count_5m == 321
