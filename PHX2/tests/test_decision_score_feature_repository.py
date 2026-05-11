"""Repository tests for DecisionScoreFeatureRepository (Stage 11).

These tests cover the repository surface in isolation -- no service
layer involvement. They verify insert / get_by_id / probe /
list-by-decision / list-by-token / UNIQUE-race surfacing / JSON
round-trip. Service-layer tests live in
``test_decision_feature_snapshot_service.py``.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage11_schema
from PHX2.db.repositories import DecisionScoreFeatureRepository
from PHX2.models import DataStatus, DecisionScoreFeatures


_NOW = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
_LATER = _NOW + timedelta(seconds=30)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"stage11_repo_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage11_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _snapshot(
    *,
    alert_decision_id: int = 1,
    feature_version: str = "decision_features_v0_observe_only",
    schema_version: str = "schema_v0",
    token_address: str = "token-aaa",
    decision_time: datetime = _NOW,
    data_status: DataStatus = DataStatus.OK,
    missing_reasons=(),
) -> DecisionScoreFeatures:
    return DecisionScoreFeatures(
        alert_decision_id=alert_decision_id,
        feature_version=feature_version,
        schema_version=schema_version,
        token_address=token_address,
        token_symbol="TOK",
        decision_time=decision_time,
        as_of_time=decision_time,
        tier_index=1,
        tier_name="tier_1",
        alert_price=0.01,
        alert_market_cap=10000.0,
        ath_price=0.05,
        ath_market_cap=50000.0,
        ath_time=decision_time,
        migration_price=0.001,
        migration_market_cap=1000.0,
        migration_time=decision_time - timedelta(minutes=5),
        drop_from_ath=-0.8,
        multiple_from_migration=10.0,
        time_since_migration_seconds=300.0,
        time_since_ath_seconds=60.0,
        time_from_migration_to_ath_seconds=240.0,
        liquidity_usd=None,
        event_count_5m=20,
        total_fee_5m=0.4,
        lp_fee_5m=0.1,
        protocol_fee_5m=0.1,
        creator_fee_5m=0.2,
        creator_fee_share_5m=0.5,
        lp_fee_share_5m=0.25,
        protocol_fee_share_5m=0.25,
        fee_per_event_5m=0.02,
        events_per_minute_5m=4.0,
        fees_per_minute_5m=0.08,
        source_snapshot={"envelope": {"feature_version": feature_version}},
        created_at=_LATER,
        data_status=data_status,
        missing_reasons=missing_reasons,
    )


def test_insert_returns_new_id_and_round_trips_full_dataclass():
    snapshot = _snapshot(alert_decision_id=42)
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(snapshot)
        loaded = repository.get_by_id(new_id)

    assert new_id > 0
    assert loaded is not None
    assert loaded.id == new_id
    assert loaded.alert_decision_id == 42
    assert loaded.token_symbol == "TOK"
    assert loaded.decision_time == _NOW
    assert loaded.tier_index == 1
    assert loaded.alert_price == 0.01
    assert loaded.event_count_5m == 20
    assert loaded.total_fee_5m == 0.4
    assert loaded.data_status == DataStatus.OK
    assert loaded.source_snapshot == {
        "envelope": {"feature_version": "decision_features_v0_observe_only"}
    }


def test_insert_preserves_nulls_for_partial_rows():
    snapshot = DecisionScoreFeatures(
        alert_decision_id=1,
        feature_version="decision_features_v0_observe_only",
        schema_version="schema_v0",
        token_address="token-bbb",
        decision_time=_NOW,
        as_of_time=_NOW,
        # Every measurement column intentionally None.
        source_snapshot={},
        created_at=_LATER,
        data_status=DataStatus.PARTIAL,
        missing_reasons=("field_features_missing",),
    )
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(snapshot)
        loaded = repository.get_by_id(new_id)

    assert loaded is not None
    assert loaded.alert_price is None
    assert loaded.alert_market_cap is None
    assert loaded.event_count_5m is None
    assert loaded.fee_per_event_5m is None
    assert loaded.tier_index is None
    assert loaded.token_symbol is None
    assert loaded.data_status == DataStatus.PARTIAL
    assert loaded.missing_reasons == ("field_features_missing",)


def test_get_by_decision_and_version_returns_existing():
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(_snapshot(alert_decision_id=11))
        existing = repository.get_by_decision_and_version(
            11, "decision_features_v0_observe_only"
        )

    assert existing is not None
    assert existing.id == new_id


def test_get_by_decision_and_version_returns_none_when_absent():
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        absent = repository.get_by_decision_and_version(
            999, "decision_features_v0_observe_only"
        )

    assert absent is None


def test_get_all_for_decision_returns_all_versions_in_id_asc():
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        v0_id = repository.insert(
            _snapshot(
                alert_decision_id=7,
                feature_version="decision_features_v0_observe_only",
            )
        )
        v1_id = repository.insert(
            _snapshot(
                alert_decision_id=7,
                feature_version="decision_features_v1_observe_only",
            )
        )
        rows = repository.get_all_for_decision(7)

    assert [row.id for row in rows] == [v0_id, v1_id]


def test_list_by_token_returns_chronological_capped():
    earlier = _NOW - timedelta(hours=2)
    middle = _NOW - timedelta(hours=1)
    later = _NOW

    def at(when: datetime, decision_id: int) -> DecisionScoreFeatures:
        return DecisionScoreFeatures(
            **{**_snapshot(alert_decision_id=decision_id).__dict__,
               "decision_time": when}
        )

    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        repository.insert(at(earlier, 1))
        repository.insert(at(middle, 2))
        repository.insert(at(later, 3))
        recent = repository.list_by_token("token-aaa", limit=2)

    assert len(recent) == 2
    assert [row.decision_time for row in recent] == [later, middle]


def test_unique_race_raises_integrity_error_at_repository_layer():
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        repository.insert(_snapshot(alert_decision_id=99))
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            repository.insert(_snapshot(alert_decision_id=99))

    assert "UNIQUE constraint failed" in str(exc_info.value)


def test_source_snapshot_dict_round_trips_through_compact_sorted_json():
    fixture = _snapshot(alert_decision_id=44)
    fixture = DecisionScoreFeatures(
        **{
            **fixture.__dict__,
            "source_snapshot": {
                "envelope": {"x": 1, "a": 2},
                "upstream_refs": {"alert_decision_id": 44},
                "ath_provenance": {"status": "confirmed"},
                "basis_flags": {"pump_multiple_basis": "mcap"},
                "aux_windows": {"60s": {"event_count": 9}},
                "clock_aux": {"sequence_phase": "pullback"},
            },
        }
    )
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(fixture)
        raw_json = connection.execute(
            "SELECT source_snapshot_json FROM decision_score_features "
            "WHERE id = ?",
            (new_id,),
        ).fetchone()["source_snapshot_json"]
        loaded = repository.get_by_id(new_id)

    # Compact: no spaces between separators.
    assert ", " not in raw_json
    assert ": " not in raw_json
    # Sorted keys: 'a' precedes 'x' inside envelope.
    envelope_section = raw_json[
        raw_json.index('"envelope"') : raw_json.index('"upstream_refs"')
    ]
    assert envelope_section.index('"a"') < envelope_section.index('"x"')
    # Round-trip dict equality.
    assert loaded is not None
    assert loaded.source_snapshot == fixture.source_snapshot


def test_get_by_id_returns_none_for_unknown_id():
    with _connection() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        assert repository.get_by_id(987654) is None
