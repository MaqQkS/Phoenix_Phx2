"""Tests for PHX2 PumpSwapEventIngestionService."""

import sqlite3
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import RawPumpSwapEventRepository
from PHX2.models import DataStatus, RawPumpSwapEvent
from PHX2.services.pumpswap_event_ingestion_service import (
    PumpSwapEventIngestionService,
)


OBSERVED_AT = datetime(2026, 5, 8, 8, 0, tzinfo=timezone.utc)
BLOCK_TIME = datetime(2026, 5, 8, 8, 0, 5, tzinfo=timezone.utc)
FALLBACK_NOW = datetime(2026, 5, 8, 8, 1, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"pumpswap_ingestion_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[
    tuple[sqlite3.Connection, PumpSwapEventIngestionService]
]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        service = PumpSwapEventIngestionService(
            RawPumpSwapEventRepository(connection),
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


def _complete_event(**overrides: object) -> RawPumpSwapEvent:
    values = {
        "observed_at": OBSERVED_AT,
        "source": "grpc",
        "signature": "sig-complete",
        "dedupe_key": "sig-complete:0",
        "event_type": "buy",
        "subscription": "pumpswap",
        "slot": 123,
        "block_time": BLOCK_TIME,
        "transaction_index": 1,
        "instruction_index": 2,
        "inner_instruction_index": 3,
        "event_index": 4,
        "pool_address": "pool",
        "token_address": "token",
        "base_mint": "base",
        "quote_mint": "quote",
        "user_address": "user",
        "base_amount_raw": "1000000",
        "quote_amount_raw": "2000000",
        "base_amount_token": 1.0,
        "quote_amount_sol": 2.0,
        "price_sol": 0.02,
        "price_usd": 3.0,
        "mcap": 30000.0,
        "lp_fee_sol": 0.001,
        "protocol_fee_sol": 0.002,
        "creator_fee_sol": 0.003,
        "total_fee_sol": 0.006,
        "fee_unit": "sol",
        "fee_invariant_ok": True,
        "decoder_name": "unit_decoder",
        "decoder_version": "v0",
        "raw_payload": {"nested": {"ok": True}, "items": [1, 2]},
        "data_status": DataStatus.OK,
    }
    values.update(overrides)
    return RawPumpSwapEvent(**values)


def test_ingest_complete_event_writes_raw_row_and_roundtrips_payload():
    with _service_context() as (connection, service):
        row_id = service.ingest_event(_complete_event())
        row = connection.execute(
            "SELECT * FROM raw_pumpswap_events WHERE id = ?",
            (row_id,),
        ).fetchone()
        fetched = RawPumpSwapEventRepository(connection).get_by_dedupe_key(
            "sig-complete:0"
        )

    assert row_id == row["id"]
    assert row["token_address"] == "token"
    assert row["pool_address"] == "pool"
    assert row["data_status"] == "ok"
    assert row["raw_payload_json"] == '{"items":[1,2],"nested":{"ok":true}}'
    assert fetched.id == row_id
    assert fetched.raw_payload == {"items": [1, 2], "nested": {"ok": True}}


def test_nullable_numeric_fields_remain_null_not_zero():
    with _service_context() as (connection, service):
        row_id = service.ingest_event(
            _complete_event(
                signature="sig-null",
                dedupe_key="sig-null:0",
                base_amount_token=None,
                quote_amount_sol=None,
                price_sol=None,
                price_usd=None,
                mcap=None,
                lp_fee_sol=None,
                protocol_fee_sol=None,
                creator_fee_sol=None,
                total_fee_sol=None,
                fee_invariant_ok=None,
            )
        )
        row = connection.execute(
            """
            SELECT base_amount_token, quote_amount_sol, price_sol, price_usd,
                   mcap, lp_fee_sol, protocol_fee_sol, creator_fee_sol,
                   total_fee_sol, fee_invariant_ok, data_status,
                   missing_reasons_json
            FROM raw_pumpswap_events
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()

    assert row["base_amount_token"] is None
    assert row["quote_amount_sol"] is None
    assert row["price_sol"] is None
    assert row["price_usd"] is None
    assert row["mcap"] is None
    assert row["lp_fee_sol"] is None
    assert row["protocol_fee_sol"] is None
    assert row["creator_fee_sol"] is None
    assert row["total_fee_sol"] is None
    assert row["fee_invariant_ok"] is None
    assert row["data_status"] == "partial"
    assert "fee_fields_missing" in row["missing_reasons_json"]


def test_missing_token_and_pool_are_partial_but_allowed():
    with _service_context() as (connection, service):
        row_id = service.ingest_event(
            _complete_event(
                signature="sig-missing-addresses",
                dedupe_key="sig-missing-addresses:0",
                token_address=None,
                pool_address=" ",
            )
        )
        row = connection.execute(
            """
            SELECT token_address, pool_address, data_status, missing_reasons_json
            FROM raw_pumpswap_events
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()

    assert row["token_address"] is None
    assert row["pool_address"] is None
    assert row["data_status"] == "partial"
    assert "token_address_missing" in row["missing_reasons_json"]
    assert "pool_address_missing" in row["missing_reasons_json"]


def test_missing_observed_at_and_source_fallbacks_are_deterministic():
    with _service_context() as (connection, service):
        row_id = service.ingest_event(
            _complete_event(
                signature="sig-fallback",
                dedupe_key="sig-fallback:0",
                observed_at=None,
                source=" ",
            )
        )
        row = connection.execute(
            """
            SELECT observed_at, source, data_status, missing_reasons_json
            FROM raw_pumpswap_events
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()

    assert row["observed_at"] == FALLBACK_NOW.isoformat()
    assert row["source"] == "unknown"
    assert row["data_status"] == "partial"
    assert "observed_at_missing" in row["missing_reasons_json"]
    assert "source_missing" in row["missing_reasons_json"]


def test_duplicate_dedupe_key_returns_existing_id():
    with _service_context() as (connection, service):
        first_id = service.ingest_event(_complete_event())
        duplicate_id = service.ingest_event(
            _complete_event(
                signature="sig-complete-replay",
                event_index=99,
                raw_payload={"replay": True},
            )
        )
        row_count = _count(connection, "raw_pumpswap_events")
        row = connection.execute(
            "SELECT signature, event_index, raw_payload_json FROM raw_pumpswap_events"
        ).fetchone()

    assert duplicate_id == first_id
    assert row_count == 1
    assert row["signature"] == "sig-complete"
    assert row["event_index"] == 4
    assert row["raw_payload_json"] == '{"items":[1,2],"nested":{"ok":true}}'


def test_invalid_required_fields_raise_value_error():
    with _service_context() as (_, service):
        for field_name in ["dedupe_key", "signature", "event_type"]:
            event = _complete_event(**{field_name: " "})
            with pytest.raises(
                ValueError,
                match=f"RawPumpSwapEvent.{field_name} is required",
            ):
                service.ingest_event(event)


def test_ingestion_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        service.ingest_event(_complete_event())

        assert _count(connection, "fee_windows") == 0
        assert _count(connection, "field_features") == 0
        assert _count(connection, "score_features") == 0
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "ath_events") == 0
        assert _count(connection, "token_sequence_state") == 0
        assert _count(connection, "price_curve_points") == 0


def test_ingestion_service_makes_no_network_calls(monkeypatch):
    def fail_socket(*_: object, **__: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_socket)

    with _service_context() as (_, service):
        row_id = service.ingest_event(_complete_event())

    assert row_id == 1
