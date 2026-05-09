"""Tests for PHX2 ATHService."""

import socket
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import ATHRepository, PriceObservationRepository
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHStatus,
    DataStatus,
    PriceObservation,
)
from PHX2.services.ath_service import ATHService


BASE_TIME = datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc)
OBSERVED_AT = BASE_TIME + timedelta(seconds=5)
SOURCE_TIME = BASE_TIME + timedelta(seconds=3)
FALLBACK_NOW = BASE_TIME + timedelta(minutes=10)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"ath_service_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _service_context() -> Iterator[tuple[sqlite3.Connection, ATHService]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        service = ATHService(
            ATHRepository(connection),
            PriceObservationRepository(connection),
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


def _insert_observation(
    connection: sqlite3.Connection,
    *,
    token_address: str = "token",
    observed_at: datetime = OBSERVED_AT,
    source_timestamp: datetime | None = SOURCE_TIME,
    source: str = "unit",
    price: float | None = 0.02,
    mcap: float | None = 20000.0,
    data_status: DataStatus = DataStatus.OK,
) -> PriceObservation:
    repository = PriceObservationRepository(connection)
    observation_id = repository.insert(
        PriceObservation(
            token_address=token_address,
            observed_at=observed_at,
            source=source,
            price=price,
            mcap=mcap,
            source_timestamp=source_timestamp,
            data_status=data_status,
        )
    )
    stored = repository.get_latest(token_address.strip())
    assert stored is not None
    assert stored.id == observation_id
    return stored


def _latest_event_row(connection: sqlite3.Connection) -> sqlite3.Row:
    return connection.execute(
        "SELECT * FROM ath_events ORDER BY id DESC LIMIT 1"
    ).fetchone()


def test_first_valid_price_observation_seeds_ath_state_and_event():
    with _service_context() as (connection, service):
        observation = _insert_observation(connection)

        state = service.evaluate_price_observation(observation)
        ath_row = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()
        event_row = _latest_event_row(connection)
        ath_count = _count(connection, "ath_state")
        event_count = _count(connection, "ath_events")

    assert state.token_address == "token"
    assert state.ath_price == pytest.approx(0.02)
    assert state.ath_mcap == pytest.approx(20000.0)
    assert state.ath_time == SOURCE_TIME
    assert state.ath_status == ATHStatus.SEEDED
    assert state.ath_confidence == ATHConfidence.MEDIUM
    assert state.ath_source == "unit"
    assert state.data_status == DataStatus.OK
    assert state.last_event_id == event_row["id"]
    assert ath_row["last_event_id"] == event_row["id"]
    assert event_row["price_observation_id"] == observation.id
    assert event_row["mutation_type"] == ATHEventType.ATH_RAISED.value
    assert event_row["accepted"] == 1
    assert event_row["data_limited"] == 0
    assert ath_count == 1
    assert event_count == 1


def test_higher_candidate_raises_and_lower_candidate_is_rejected():
    with _service_context() as (connection, service):
        service.evaluate_price_observation(_insert_observation(connection))
        higher = _insert_observation(
            connection,
            observed_at=OBSERVED_AT + timedelta(seconds=30),
            source_timestamp=SOURCE_TIME + timedelta(seconds=30),
            price=0.03,
            mcap=30000.0,
        )
        raised_state = service.evaluate_price_observation(higher)
        lower = _insert_observation(
            connection,
            observed_at=OBSERVED_AT + timedelta(seconds=60),
            source_timestamp=SOURCE_TIME + timedelta(seconds=60),
            price=0.025,
            mcap=25000.0,
        )
        final_state = service.evaluate_price_observation(lower)
        events = ATHRepository(connection).list_events_chronological("token")
        latest_event = _latest_event_row(connection)

    assert raised_state.ath_price == pytest.approx(0.03)
    assert raised_state.ath_status == ATHStatus.CONFIRMED
    assert raised_state.ath_confidence == ATHConfidence.MEDIUM
    assert final_state.ath_price == pytest.approx(0.03)
    assert final_state.ath_mcap == pytest.approx(30000.0)
    assert final_state.last_event_id == latest_event["id"]
    assert [event.mutation_type for event in events] == [
        ATHEventType.ATH_RAISED,
        ATHEventType.ATH_RAISED,
        ATHEventType.ATH_REJECTED_LOWER,
    ]
    assert latest_event["accepted"] == 0
    assert latest_event["new_ath_price"] == pytest.approx(0.03)
    assert latest_event["prior_ath_price"] == pytest.approx(0.03)


def test_missing_price_and_mcap_logs_data_limited_and_preserves_state():
    with _service_context() as (connection, service):
        seeded = service.evaluate_price_observation(_insert_observation(connection))
        missing = _insert_observation(
            connection,
            observed_at=OBSERVED_AT + timedelta(minutes=1),
            source_timestamp=SOURCE_TIME + timedelta(minutes=1),
            price=None,
            mcap=None,
            data_status=DataStatus.MISSING,
        )

        state = service.evaluate_price_observation(missing)
        event_row = _latest_event_row(connection)
        ath_row = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()

    assert seeded.ath_price == pytest.approx(0.02)
    assert state.ath_price == pytest.approx(0.02)
    assert state.ath_mcap == pytest.approx(20000.0)
    assert state.ath_status == ATHStatus.SEEDED
    assert state.ath_confidence == ATHConfidence.MEDIUM
    assert state.last_event_id == event_row["id"]
    assert ath_row["last_event_id"] == event_row["id"]
    assert event_row["mutation_type"] == ATHEventType.ATH_DATA_LIMITED.value
    assert event_row["accepted"] == 0
    assert event_row["data_limited"] == 1
    assert event_row["candidate_price"] is None
    assert event_row["candidate_mcap"] is None
    assert event_row["new_ath_price"] == pytest.approx(0.02)


def test_invalid_numeric_candidate_logs_rejected_invalid_without_lowering_state():
    with _service_context() as (connection, service):
        service.evaluate_price_observation(_insert_observation(connection))
        invalid = _insert_observation(
            connection,
            observed_at=OBSERVED_AT + timedelta(minutes=1),
            source_timestamp=SOURCE_TIME + timedelta(minutes=1),
            price=0.0,
            mcap=-1.0,
            data_status=DataStatus.ERROR,
        )

        state = service.evaluate_price_observation(invalid)
        event_row = _latest_event_row(connection)

    assert state.ath_price == pytest.approx(0.02)
    assert state.ath_mcap == pytest.approx(20000.0)
    assert event_row["mutation_type"] == ATHEventType.ATH_REJECTED_INVALID.value
    assert event_row["accepted"] == 0
    assert event_row["data_status"] == DataStatus.ERROR.value
    assert "price_invalid" in event_row["missing_reasons_json"]
    assert "mcap_invalid" in event_row["missing_reasons_json"]


def test_rebuild_from_price_observations_returns_highest_ath_and_ordered_events():
    with _service_context() as (connection, service):
        _insert_observation(connection, observed_at=BASE_TIME, source_timestamp=BASE_TIME)
        _insert_observation(
            connection,
            observed_at=BASE_TIME + timedelta(seconds=10),
            source_timestamp=BASE_TIME + timedelta(seconds=10),
            price=0.015,
            mcap=15000.0,
        )
        _insert_observation(
            connection,
            observed_at=BASE_TIME + timedelta(seconds=20),
            source_timestamp=BASE_TIME + timedelta(seconds=20),
            price=0.04,
            mcap=40000.0,
        )
        _insert_observation(
            connection,
            observed_at=BASE_TIME + timedelta(seconds=30),
            source_timestamp=BASE_TIME + timedelta(seconds=30),
            price=None,
            mcap=None,
            data_status=DataStatus.MISSING,
        )
        _insert_observation(
            connection,
            observed_at=BASE_TIME + timedelta(seconds=40),
            source_timestamp=BASE_TIME + timedelta(seconds=40),
            price=0.03,
            mcap=30000.0,
        )

        state = service.rebuild_from_price_observations(" token ")
        event_rows = connection.execute(
            """
            SELECT mutation_type, accepted, candidate_price, new_ath_price
            FROM ath_events
            WHERE token_address = 'token'
            ORDER BY event_time ASC, id ASC
            """
        ).fetchall()

    assert state.ath_price == pytest.approx(0.04)
    assert state.ath_mcap == pytest.approx(40000.0)
    assert [row["mutation_type"] for row in event_rows] == [
        ATHEventType.ATH_RAISED.value,
        ATHEventType.ATH_REJECTED_LOWER.value,
        ATHEventType.ATH_RAISED.value,
        ATHEventType.ATH_DATA_LIMITED.value,
        ATHEventType.ATH_REJECTED_LOWER.value,
    ]
    reconstructed_price = None
    for row in event_rows:
        if row["accepted"]:
            reconstructed_price = row["new_ath_price"]
    assert reconstructed_price == pytest.approx(0.04)


def test_ath_service_does_not_write_unrelated_tables():
    with _service_context() as (connection, service):
        observation = _insert_observation(connection)
        token_count_before = _count(connection, "token_sequence_state")
        price_count_before = _count(connection, "price_observations")

        service.evaluate_price_observation(observation)

        assert _count(connection, "token_sequence_state") == token_count_before
        assert _count(connection, "price_observations") == price_count_before
        assert _count(connection, "alert_decisions") == 0
        assert _count(connection, "field_features") == 0
        assert _count(connection, "score_features") == 0
        assert _count(connection, "clock_features") == 0
        assert _count(connection, "price_curve_points") == 0


def test_ath_service_makes_no_network_calls(monkeypatch):
    def fail_socket(*_: object, **__: object) -> socket.socket:
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_socket)

    with _service_context() as (connection, service):
        state = service.evaluate_price_observation(_insert_observation(connection))

    assert state.ath_price == pytest.approx(0.02)


def test_persist_rolls_back_event_when_state_upsert_fails(monkeypatch):
    with _service_context() as (connection, service):
        seeded = _insert_observation(connection)
        service.evaluate_price_observation(seeded)

        events_before = _count(connection, "ath_events")
        state_row_before = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()
        assert state_row_before is not None

        higher = _insert_observation(
            connection,
            observed_at=OBSERVED_AT + timedelta(seconds=30),
            source_timestamp=SOURCE_TIME + timedelta(seconds=30),
            price=0.05,
            mcap=50000.0,
        )

        original_upsert_state = ATHRepository.upsert_state

        def failing_upsert_state(self, ath_state):
            raise RuntimeError("simulated upsert_state failure")

        monkeypatch.setattr(ATHRepository, "upsert_state", failing_upsert_state)
        try:
            with pytest.raises(RuntimeError, match="simulated upsert_state failure"):
                service.evaluate_price_observation(higher)
        finally:
            monkeypatch.setattr(ATHRepository, "upsert_state", original_upsert_state)

        events_after = _count(connection, "ath_events")
        state_row_after = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()

    assert events_after == events_before, (
        "ath_events row count must be unchanged after rollback"
    )
    assert state_row_after is not None
    assert dict(state_row_after) == dict(state_row_before), (
        "ath_state must be unchanged after rollback"
    )


def test_equal_candidate_records_no_change_event_and_preserves_state():
    with _service_context() as (connection, service):
        seeded_state = service.evaluate_price_observation(_insert_observation(connection))
        events_before = _count(connection, "ath_events")
        ath_row_before = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()

        equal = _insert_observation(
            connection,
            observed_at=OBSERVED_AT + timedelta(seconds=15),
            source_timestamp=SOURCE_TIME + timedelta(seconds=15),
            price=0.02,
            mcap=20000.0,
        )

        state = service.evaluate_price_observation(equal)
        events_after = _count(connection, "ath_events")
        latest_event = _latest_event_row(connection)
        ath_row_after = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()

    assert state.ath_price == pytest.approx(seeded_state.ath_price)
    assert state.ath_mcap == pytest.approx(seeded_state.ath_mcap)
    assert state.ath_time == seeded_state.ath_time
    assert state.ath_status == seeded_state.ath_status
    assert state.ath_confidence == seeded_state.ath_confidence
    assert state.ath_source == seeded_state.ath_source
    assert ath_row_after["ath_price"] == ath_row_before["ath_price"]
    assert ath_row_after["ath_mcap"] == ath_row_before["ath_mcap"]
    assert ath_row_after["ath_time"] == ath_row_before["ath_time"]
    assert ath_row_after["ath_status"] == ath_row_before["ath_status"]
    assert ath_row_after["ath_confidence"] == ath_row_before["ath_confidence"]
    assert events_after == events_before + 1, "audit row must still be written"
    assert latest_event["mutation_type"] == ATHEventType.ATH_NO_CHANGE.value
    assert latest_event["accepted"] == 0
    assert state.last_event_id == latest_event["id"]
    assert ath_row_after["last_event_id"] == latest_event["id"]


def test_last_event_id_matches_inserted_event_after_successful_evaluate():
    with _service_context() as (connection, service):
        observation = _insert_observation(connection)

        state = service.evaluate_price_observation(observation)
        latest_event = _latest_event_row(connection)
        ath_row = connection.execute(
            "SELECT * FROM ath_state WHERE token_address = 'token'"
        ).fetchone()

    assert state.last_event_id == latest_event["id"]
    assert ath_row["last_event_id"] == latest_event["id"]


def test_connection_transaction_commits_writes_across_repositories():
    with _service_context() as (connection, service):
        price_repo = PriceObservationRepository(connection)
        ath_repo = ATHRepository(connection)
        prices_before = _count(connection, "price_observations")
        events_before = _count(connection, "ath_events")

        with connection.transaction():
            price_repo.insert(
                PriceObservation(
                    token_address="token",
                    observed_at=OBSERVED_AT,
                    source="unit",
                    price=0.04,
                    mcap=40000.0,
                    source_timestamp=SOURCE_TIME,
                )
            )
            ath_repo.insert_event(
                ATHEvent(
                    token_address="token",
                    event_time=SOURCE_TIME,
                    candidate_price=0.04,
                    candidate_mcap=40000.0,
                    candidate_source="unit",
                    new_ath_price=0.04,
                    new_ath_mcap=40000.0,
                    status_after=ATHStatus.SEEDED,
                    confidence_after=ATHConfidence.MEDIUM,
                    mutation_type=ATHEventType.ATH_RAISED,
                    reason="cross_repo_commit_test",
                    accepted=True,
                    data_status=DataStatus.OK,
                )
            )

        prices_after = _count(connection, "price_observations")
        events_after = _count(connection, "ath_events")

    assert prices_after == prices_before + 1
    assert events_after == events_before + 1


def test_connection_transaction_rolls_back_writes_across_repositories():
    with _service_context() as (connection, service):
        price_repo = PriceObservationRepository(connection)
        ath_repo = ATHRepository(connection)
        prices_before = _count(connection, "price_observations")
        events_before = _count(connection, "ath_events")

        with pytest.raises(RuntimeError, match="forced rollback"):
            with connection.transaction():
                price_repo.insert(
                    PriceObservation(
                        token_address="token",
                        observed_at=OBSERVED_AT,
                        source="unit",
                        price=0.04,
                        mcap=40000.0,
                        source_timestamp=SOURCE_TIME,
                    )
                )
                ath_repo.insert_event(
                    ATHEvent(
                        token_address="token",
                        event_time=SOURCE_TIME,
                        candidate_price=0.04,
                        candidate_mcap=40000.0,
                        candidate_source="unit",
                        new_ath_price=0.04,
                        new_ath_mcap=40000.0,
                        status_after=ATHStatus.SEEDED,
                        confidence_after=ATHConfidence.MEDIUM,
                        mutation_type=ATHEventType.ATH_RAISED,
                        reason="cross_repo_rollback_test",
                        accepted=True,
                        data_status=DataStatus.OK,
                    )
                )
                raise RuntimeError("forced rollback")

        prices_after = _count(connection, "price_observations")
        events_after = _count(connection, "ath_events")

    assert prices_after == prices_before, (
        "price_observations row count must be unchanged after rollback"
    )
    assert events_after == events_before, (
        "ath_events row count must be unchanged after rollback"
    )
    assert connection.in_transaction is False


def test_connection_transaction_raises_on_nested():
    with _service_context() as (connection, service):
        with connection.transaction():
            with pytest.raises(RuntimeError, match="nested transactions not supported"):
                with connection.transaction():
                    pass
        assert connection.in_transaction is False
