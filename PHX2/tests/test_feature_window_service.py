"""Tests for PHX2 FeatureWindowService."""

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
from PHX2.db.repositories import FeeWindowRepository, RawPumpSwapEventRepository
from PHX2.models import DataStatus, RawPumpSwapEvent
from PHX2.services.feature_window_service import FeatureWindowService
from PHX2.services.pumpswap_event_ingestion_service import (
    PumpSwapEventIngestionService,
)


OUTSIDE_TIME = datetime(2026, 5, 8, 7, 59, 59, tzinfo=timezone.utc)
AS_OF_TIME = datetime(2026, 5, 8, 8, 5, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"feature_window_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, FeatureWindowService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        service = FeatureWindowService(
            RawPumpSwapEventRepository(connection),
            FeeWindowRepository(connection),
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


def _time(minute: int) -> datetime:
    return datetime(2026, 5, 8, 8, minute, tzinfo=timezone.utc)


def _raw_event(
    signature: str,
    *,
    event_type: str,
    block_time: datetime,
    total_fee_sol: float | None,
    lp_fee_sol: float | None,
    protocol_fee_sol: float | None,
    creator_fee_sol: float | None,
    token_address: str = "token",
) -> RawPumpSwapEvent:
    return RawPumpSwapEvent(
        observed_at=block_time,
        source="grpc",
        signature=signature,
        dedupe_key=f"{signature}:0",
        event_type=event_type,
        block_time=block_time,
        pool_address="pool",
        token_address=token_address,
        total_fee_sol=total_fee_sol,
        lp_fee_sol=lp_fee_sol,
        protocol_fee_sol=protocol_fee_sol,
        creator_fee_sol=creator_fee_sol,
        data_status=DataStatus.OK,
    )


def _ingest(
    connection: sqlite3.Connection,
    *events: RawPumpSwapEvent,
) -> None:
    service = PumpSwapEventIngestionService(RawPumpSwapEventRepository(connection))
    for event in events:
        service.ingest_event(event)


def test_materialize_fee_window_aggregates_counts_fees_rates_and_sources():
    with _service_context() as (connection, service):
        _ingest(
            connection,
            _raw_event(
                "sig-outside",
                event_type="buy",
                block_time=OUTSIDE_TIME,
                total_fee_sol=1.0,
                lp_fee_sol=1.0,
                protocol_fee_sol=1.0,
                creator_fee_sol=1.0,
            ),
            _raw_event(
                "sig-buy",
                event_type="BUY",
                block_time=_time(1),
                total_fee_sol=0.06,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.02,
                creator_fee_sol=0.03,
            ),
            _raw_event(
                "sig-sell",
                event_type="sell",
                block_time=_time(2),
                total_fee_sol=0.03,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.01,
                creator_fee_sol=0.01,
            ),
            _raw_event(
                "sig-other",
                event_type="swap",
                block_time=_time(3),
                total_fee_sol=0.01,
                lp_fee_sol=0.005,
                protocol_fee_sol=0.003,
                creator_fee_sol=0.002,
            ),
        )

        window = service.materialize_fee_window("token", AS_OF_TIME, 300)
        stored = FeeWindowRepository(connection).get("token", AS_OF_TIME, 300)

    assert stored.event_count == 3
    assert stored.buy_count == 1
    assert stored.sell_count == 1
    assert stored.total_fee_sol == pytest.approx(0.10)
    assert stored.lp_fee_sol == pytest.approx(0.025)
    assert stored.protocol_fee_sol == pytest.approx(0.033)
    assert stored.creator_fee_sol == pytest.approx(0.042)
    assert stored.creator_fee_share == pytest.approx(0.42)
    assert stored.lp_fee_share == pytest.approx(0.25)
    assert stored.protocol_fee_share == pytest.approx(0.33)
    assert stored.avg_fee_per_event_sol == pytest.approx(0.10 / 3)
    assert stored.median_fee_per_event_sol == pytest.approx(0.03)
    assert stored.max_fee_event_sol == pytest.approx(0.06)
    assert stored.events_per_min == pytest.approx(0.6)
    assert stored.fees_per_min_sol == pytest.approx(0.02)
    assert stored.buy_sell_count_ratio == pytest.approx(1.0)
    assert stored.buy_sell_fee_ratio == pytest.approx(2.0)
    assert stored.first_event_time == _time(1)
    assert stored.last_event_time == _time(3)
    assert stored.source_min_id == 2
    assert stored.source_max_id == 4
    assert stored.source_row_count == 3
    assert stored.data_status == DataStatus.OK
    assert stored.missing_reasons == []
    assert window.event_count == stored.event_count


def test_zero_sell_denominators_store_null_ratios_with_reasons_but_ok_status():
    with _service_context() as (connection, service):
        _ingest(
            connection,
            _raw_event(
                "sig-buy-only",
                event_type="buy",
                block_time=_time(4),
                total_fee_sol=0.05,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.02,
                creator_fee_sol=0.02,
            ),
        )

        window = service.materialize_fee_window("token", AS_OF_TIME, 300)

    assert window.buy_count == 1
    assert window.sell_count == 0
    assert window.buy_sell_count_ratio is None
    assert window.buy_sell_fee_ratio is None
    assert window.data_status == DataStatus.OK
    assert "buy_sell_ratio_denominator_zero" in window.missing_reasons
    assert "buy_sell_fee_denominator_zero" in window.missing_reasons


def test_no_events_window_is_no_events_with_zero_counts_and_totals():
    with _service_context() as (_, service):
        window = service.materialize_fee_window("token", AS_OF_TIME, 300)

    assert window.event_count == 0
    assert window.buy_count == 0
    assert window.sell_count == 0
    assert window.total_fee_sol == 0.0
    assert window.lp_fee_sol == 0.0
    assert window.protocol_fee_sol == 0.0
    assert window.creator_fee_sol == 0.0
    assert window.median_fee_per_event_sol is None
    assert window.data_status == DataStatus.NO_EVENTS
    assert window.missing_reasons == ["no_raw_events_in_window"]


def test_partial_fee_data_keeps_aggregates_explicit_and_marks_partial():
    with _service_context() as (connection, service):
        _ingest(
            connection,
            _raw_event(
                "sig-partial",
                event_type="sell",
                block_time=_time(4),
                total_fee_sol=None,
                lp_fee_sol=None,
                protocol_fee_sol=None,
                creator_fee_sol=None,
            ),
        )

        window = service.materialize_fee_window("token", AS_OF_TIME, 300)

    assert window.event_count == 1
    assert window.total_fee_sol == 0.0
    assert window.lp_fee_sol == 0.0
    assert window.protocol_fee_sol == 0.0
    assert window.creator_fee_sol == 0.0
    assert window.avg_fee_per_event_sol == 0.0
    assert window.median_fee_per_event_sol == 0.0
    assert window.max_fee_event_sol == 0.0
    assert window.creator_fee_share is None
    assert window.data_status == DataStatus.PARTIAL
    assert "fee_fields_missing" in window.missing_reasons
    assert "fee_share_denominator_zero" in window.missing_reasons


def test_materialize_standard_windows_creates_default_five_windows():
    with _service_context() as (connection, service):
        _ingest(
            connection,
            _raw_event(
                "sig-standard",
                event_type="buy",
                block_time=_time(4),
                total_fee_sol=0.05,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.02,
                creator_fee_sol=0.02,
            ),
        )

        windows = service.materialize_standard_windows("token", AS_OF_TIME)
        stored_windows = FeeWindowRepository(connection).list_by_token("token")

    assert [window.window_seconds for window in windows] == [60, 300, 900, 1800, 3600]
    assert len(stored_windows) == 5


def test_recomputing_same_window_upserts_existing_row():
    with _service_context() as (connection, service):
        _ingest(
            connection,
            _raw_event(
                "sig-first",
                event_type="buy",
                block_time=_time(4),
                total_fee_sol=0.05,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.02,
                creator_fee_sol=0.02,
            ),
        )
        service.materialize_fee_window("token", AS_OF_TIME, 300)
        first_row = connection.execute("SELECT id FROM fee_windows").fetchone()

        _ingest(
            connection,
            _raw_event(
                "sig-second",
                event_type="sell",
                block_time=_time(4),
                total_fee_sol=0.03,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.01,
                creator_fee_sol=0.01,
            ),
        )
        window = service.materialize_fee_window("token", AS_OF_TIME, 300)
        rows = connection.execute("SELECT id, event_count FROM fee_windows").fetchall()

    assert len(rows) == 1
    assert rows[0]["id"] == first_row["id"]
    assert rows[0]["event_count"] == 2
    assert window.event_count == 2


def test_feature_window_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        _ingest(
            connection,
            _raw_event(
                "sig-clean",
                event_type="buy",
                block_time=_time(4),
                total_fee_sol=0.05,
                lp_fee_sol=0.01,
                protocol_fee_sol=0.02,
                creator_fee_sol=0.02,
            ),
        )
        raw_count_before = _count(connection, "raw_pumpswap_events")

        service.materialize_fee_window("token", AS_OF_TIME, 300)

        assert _count(connection, "raw_pumpswap_events") == raw_count_before
        assert _count(connection, "field_features") == 0
        assert _count(connection, "score_features") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "ath_state") == 0
        assert _count(connection, "ath_events") == 0
        assert _count(connection, "token_sequence_state") == 0
        assert _count(connection, "price_curve_points") == 0


def test_feature_window_service_makes_no_network_calls(monkeypatch):
    def fail_socket(*_: object, **__: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_socket)

    with _service_context() as (_, service):
        window = service.materialize_fee_window("token", AS_OF_TIME, 300)

    assert window.data_status == DataStatus.NO_EVENTS
