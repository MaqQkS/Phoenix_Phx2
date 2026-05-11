"""Roundtrip tests for PHX2 SQLite repositories."""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import get_phx2_connection
from PHX2.db.migrations import apply_stage9_schema, apply_stage11_schema
from PHX2.db.repositories import (
    ATHRepository,
    AlertDecisionRepository,
    ClockFeatureRepository,
    DecisionScoreFeatureRepository,
    DispatchEventRepository,
    FeeWindowRepository,
    FieldFeatureRepository,
    FilterEvaluationRepository,
    MigrationEventRepository,
    OutcomeWindowRepository,
    PriceCurvePointRepository,
    PriceObservationRepository,
    RawPumpSwapEventRepository,
    ScoreFeatureRepository,
    TokenSequenceRepository,
)
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    AlertDecision,
    ClockFeatures,
    DataStatus,
    DecisionReason,
    DecisionScoreFeatures,
    DecisionType,
    DispatchEvent,
    FeeWindow,
    FieldFeatures,
    FilterLabel,
    FilterResult,
    MigrationEvent,
    OutcomeWindow,
    OutcomeWindowStatus,
    PriceCurvePoint,
    PriceObservation,
    RawPumpSwapEvent,
    ScoreFeatures,
    TokenState,
)


NOW = datetime(2026, 5, 8, 6, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 5, 8, 6, 5, tzinfo=timezone.utc)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"repo_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _repository_connection() -> Iterator[sqlite3.Connection]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage9_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


@contextmanager
def _repository_connection_stage11() -> Iterator[sqlite3.Connection]:
    """Connection with the full Stage 11 schema applied.

    Used for the DecisionScoreFeatureRepository round-trip test, which
    requires ``decision_score_features`` to exist.
    """

    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage11_schema(connection)
        yield connection
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def test_token_sequence_upsert_and_list_recent_roundtrip():
    with _repository_connection() as connection:
        repository = TokenSequenceRepository(connection)
        token = TokenState(
            token_address="token",
            symbol="TOK",
            pool_address="pool",
            migration_time=NOW,
            migration_source="grpc",
            migration_price=0.01,
            migration_mcap=10000.0,
            current_price=0.02,
            current_mcap=20000.0,
            last_price_update=LATER,
            sequence_phase="pullback",
            current_status="tracking",
            last_alerted_tier=1,
            data_status=DataStatus.OK,
        )

        assert repository.upsert(token) == "token"
        fetched = repository.get("token")
        recent = repository.list_recent()

    assert fetched == token
    assert recent == [token]


def test_event_observation_and_feature_repositories_roundtrip_json_fields():
    with _repository_connection() as connection:
        migration_repo = MigrationEventRepository(connection)
        price_repo = PriceObservationRepository(connection)
        fee_repo = FeeWindowRepository(connection)
        field_repo = FieldFeatureRepository(connection)
        score_repo = ScoreFeatureRepository(connection)
        clock_repo = ClockFeatureRepository(connection)
        filter_repo = FilterEvaluationRepository(connection)

        migration_id = migration_repo.insert(
            MigrationEvent(
                token_address="token",
                pool_address="pool",
                migration_time=NOW,
                migration_source="grpc",
                signature="sig",
                slot=123,
                block_time=NOW,
                migration_price=0.01,
                migration_mcap=10000.0,
                raw_payload_json={"source": "test", "nested": {"ok": True}},
                data_status=DataStatus.OK,
            )
        )
        price_id = price_repo.insert(
            PriceObservation(
                token_address="token",
                observed_at=LATER,
                source="dexscreener",
                price=0.02,
                mcap=20000.0,
                liquidity_usd=5000.0,
                source_timestamp=LATER,
                age_seconds=3.0,
                data_status=DataStatus.OK,
            )
        )
        fee_id = fee_repo.insert(
            FeeWindow(
                token_address="token",
                as_of_time=LATER,
                window_seconds=300,
                pool_address="pool",
                event_count=3,
                buy_count=2,
                sell_count=1,
                total_fee_sol=0.6,
                data_status=DataStatus.OK,
            )
        )
        field_id = field_repo.insert(
            FieldFeatures(
                token_address="token",
                as_of_time=LATER,
                liquidity_usd=5000.0,
                fee_gate_label="Normal",
                raw_snapshot={"fee_window_id": fee_id, "labels": ["Normal"]},
                data_status=DataStatus.OK,
            )
        )
        score_id = score_repo.insert(
            ScoreFeatures(
                token_address="token",
                as_of_time=LATER,
                components={"field_features_id": field_id},
                data_status=DataStatus.PARTIAL,
            )
        )
        clock_id = clock_repo.insert(
            ClockFeatures(
                token_address="token",
                as_of_time=LATER,
                migration_time=NOW,
                age_since_migration_s=300.0,
                sequence_phase="pullback",
                phase_reason="test",
                data_status=DataStatus.OK,
            )
        )
        filter_id = filter_repo.insert(
            FilterResult(
                token_address="token",
                as_of_time=LATER,
                filter_name="fee_gate",
                label=FilterLabel.NORMAL,
                input_snapshot={"event_count": 3},
                data_status=DataStatus.OK,
            )
        )

        migrations = migration_repo.list_by_token("token")
        latest_price = price_repo.get_latest("token")
        latest_fee = fee_repo.get("token", LATER, 300)
        latest_field = field_repo.get_latest("token")
        latest_score = score_repo.get_latest("token")
        latest_clock = clock_repo.get_latest("token")
        filters = filter_repo.list_by_token("token")

    assert all(row_id > 0 for row_id in [migration_id, price_id, fee_id, field_id, score_id, clock_id, filter_id])
    assert migrations[0].raw_payload_json["nested"]["ok"] is True
    assert latest_price.price == 0.02
    assert latest_fee.event_count == 3
    assert latest_field.raw_snapshot["labels"] == ["Normal"]
    assert latest_score.components == {"field_features_id": field_id}
    assert latest_clock.phase_reason == "test"
    assert filters[0].input_snapshot == {"event_count": 3}


def test_raw_pumpswap_event_repository_roundtrip_and_window_queries():
    with _repository_connection() as connection:
        repository = RawPumpSwapEventRepository(connection)
        first = RawPumpSwapEvent(
            observed_at=NOW,
            source="grpc",
            subscription="pumpswap",
            signature="sig-1",
            slot=100,
            block_time=NOW,
            transaction_index=0,
            instruction_index=1,
            inner_instruction_index=2,
            event_index=0,
            dedupe_key="sig-1:0:1:2:0",
            pool_address="pool",
            token_address="token",
            base_mint="base",
            quote_mint="quote",
            user_address="user",
            event_type="buy",
            base_amount_raw="1000",
            quote_amount_raw="2000",
            base_amount_token=1000.0,
            quote_amount_sol=2.0,
            price_sol=0.002,
            price_usd=0.3,
            mcap=30000.0,
            lp_fee_sol=0.01,
            protocol_fee_sol=0.02,
            creator_fee_sol=0.03,
            total_fee_sol=0.06,
            fee_unit="sol",
            fee_invariant_ok=True,
            decoder_name="test_decoder",
            decoder_version="v0",
            raw_payload={"nested": {"ok": True}},
            data_status=DataStatus.OK,
        )
        second = RawPumpSwapEvent(
            observed_at=LATER,
            source="grpc",
            signature="sig-2",
            slot=101,
            block_time=LATER,
            dedupe_key="sig-2:0:1:2:0",
            pool_address="pool",
            token_address="token",
            event_type="sell",
            raw_payload={"side": "sell"},
            data_status=DataStatus.PARTIAL,
        )

        first_id = repository.insert(first)
        second_id = repository.insert(second)
        fetched = repository.get_by_dedupe_key(first.dedupe_key)
        by_token = repository.list_by_token("token")
        in_window = repository.list_window("token", NOW, LATER)
        limited_window = repository.list_window("token", NOW, LATER, limit=1)
        count = repository.count_by_token("token")

    assert first_id > 0
    assert second_id > first_id
    assert fetched.id == first_id
    assert fetched.raw_payload == {"nested": {"ok": True}}
    assert fetched.fee_invariant_ok is True
    assert [event.dedupe_key for event in by_token] == [
        "sig-2:0:1:2:0",
        "sig-1:0:1:2:0",
    ]
    assert [event.dedupe_key for event in in_window] == [
        "sig-1:0:1:2:0",
        "sig-2:0:1:2:0",
    ]
    assert [event.dedupe_key for event in limited_window] == ["sig-1:0:1:2:0"]
    assert count == 2


def test_raw_pumpswap_nullable_numerics_remain_null_and_duplicate_dedupe_raises():
    with _repository_connection() as connection:
        repository = RawPumpSwapEventRepository(connection)
        event = RawPumpSwapEvent(
            observed_at=NOW,
            source="grpc",
            signature="sig-null",
            dedupe_key="sig-null:0",
            event_type="buy",
            token_address="token",
            block_time=NOW,
            data_status=DataStatus.MISSING,
        )

        repository.insert(event)
        raw = connection.execute(
            """
            SELECT price_sol, price_usd, mcap, total_fee_sol, raw_payload_json,
                   missing_reasons_json
            FROM raw_pumpswap_events
            WHERE dedupe_key = 'sig-null:0'
            """
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            repository.insert(event)

    assert raw["price_sol"] is None
    assert raw["price_usd"] is None
    assert raw["mcap"] is None
    assert raw["total_fee_sol"] is None
    assert raw["raw_payload_json"] == "{}"
    assert raw["missing_reasons_json"] == "[]"


def test_price_curve_point_repository_roundtrip_and_bucket_queries():
    with _repository_connection() as connection:
        repository = PriceCurvePointRepository(connection)
        first = PriceCurvePoint(
            token_address="token",
            anchor_type="migration",
            anchor_key="migration:1",
            anchor_time=NOW,
            anchor_ref_id=1,
            bucket_seconds=60,
            bucket_start_time=NOW,
            bucket_end_time=LATER,
            observed_at=LATER,
            price_observation_id=10,
            price=0.02,
            mcap=20000.0,
            liquidity_usd=5000.0,
            normalized_price=2.0,
            normalized_mcap=2.0,
            return_from_anchor=1.0,
            return_from_migration=1.0,
            drawdown_from_ath=0.2,
            age_since_migration_s=300.0,
            time_since_ath_s=120.0,
            data_status=DataStatus.OK,
        )
        second = PriceCurvePoint(
            token_address="token",
            anchor_type="ath",
            anchor_key="ath:2",
            anchor_time=LATER,
            anchor_ref_id=2,
            bucket_seconds=60,
            bucket_start_time=LATER,
            bucket_end_time=LATER,
            observed_at=LATER,
            normalized_price=1.0,
            data_status=DataStatus.PARTIAL,
            missing_reasons=["limited_price_history"],
        )

        first_id = repository.insert(first)
        second_id = repository.insert(second)
        fetched = repository.get("token", "migration:1", 60)
        by_token = repository.list_by_token("token")
        migration_points = repository.list_by_anchor("token", "migration")
        bucket_points = repository.list_bucket("migration", 60)

    assert first_id > 0
    assert second_id > first_id
    assert fetched.id == first_id
    assert fetched.price == 0.02
    assert fetched.normalized_price == 2.0
    assert fetched.data_status == DataStatus.OK
    assert [point.anchor_type for point in by_token] == ["ath", "migration"]
    assert [point.anchor_type for point in migration_points] == ["migration"]
    assert [point.token_address for point in bucket_points] == ["token"]


def test_price_curve_point_nullable_numerics_remain_null_and_duplicate_upserts():
    with _repository_connection() as connection:
        repository = PriceCurvePointRepository(connection)
        point = PriceCurvePoint(
            token_address="token",
            anchor_type="alert",
            anchor_key="alert:token",
            anchor_time=NOW,
            bucket_seconds=300,
            bucket_start_time=NOW,
            bucket_end_time=LATER,
            data_status=DataStatus.MISSING,
            missing_reasons=["price_missing", "mcap_missing"],
        )

        first_id = repository.insert(point)
        raw = connection.execute(
            """
            SELECT price, mcap, normalized_price, normalized_mcap,
                   return_from_anchor, missing_reasons_json
            FROM price_curve_points
            WHERE token_address = 'token'
              AND anchor_type = 'alert'
              AND anchor_key = 'alert:token'
              AND anchor_ref_id IS NULL
              AND bucket_seconds = 300
            """
        ).fetchone()
        fetched = repository.get("token", "alert:token", 300)
        second_id = repository.insert(point)
        row_count = connection.execute(
            "SELECT COUNT(*) AS count FROM price_curve_points"
        ).fetchone()["count"]

    assert second_id == first_id
    assert row_count == 1
    assert raw["price"] is None
    assert raw["mcap"] is None
    assert raw["normalized_price"] is None
    assert raw["normalized_mcap"] is None
    assert raw["return_from_anchor"] is None
    assert raw["missing_reasons_json"] == '["price_missing","mcap_missing"]'
    assert fetched.missing_reasons == ["price_missing", "mcap_missing"]


def test_nullable_scores_remain_null_in_storage_and_model():
    with _repository_connection() as connection:
        repository = ScoreFeatureRepository(connection)
        repository.insert(
            ScoreFeatures(
                token_address="token",
                as_of_time=NOW,
                data_status=DataStatus.MISSING,
            )
        )
        raw = connection.execute(
            """
            SELECT field_score, setup_score, clock_score, risk_score, composite_score
            FROM score_features
            WHERE token_address = 'token'
            """
        ).fetchone()
        fetched = repository.get_latest("token")

    assert raw["field_score"] is None
    assert raw["setup_score"] is None
    assert raw["clock_score"] is None
    assert raw["risk_score"] is None
    assert raw["composite_score"] is None
    assert fetched.field_score is None
    assert fetched.composite_score is None


def test_fee_window_insert_upserts_duplicate_windows():
    with _repository_connection() as connection:
        repository = FeeWindowRepository(connection)
        window = FeeWindow(
            token_address="token",
            as_of_time=NOW,
            window_seconds=300,
            data_status=DataStatus.NO_EVENTS,
        )
        updated = FeeWindow(
            token_address="token",
            as_of_time=NOW,
            window_seconds=300,
            event_count=2,
            total_fee_sol=0.05,
            data_status=DataStatus.OK,
        )

        first_id = repository.insert(window)
        second_id = repository.insert(updated)
        rows = connection.execute("SELECT id, event_count FROM fee_windows").fetchall()

    assert second_id == first_id
    assert len(rows) == 1
    assert rows[0]["event_count"] == 2


def test_ath_state_upsert_and_event_list_roundtrip():
    with _repository_connection() as connection:
        repository = ATHRepository(connection)
        initial_state = ATHState(
            token_address="token",
            ath_price=0.02,
            ath_mcap=20000.0,
            ath_time=NOW,
            ath_status=ATHStatus.PROVISIONAL,
            ath_confidence=ATHConfidence.LOW,
            ath_source="running_max",
            data_status=DataStatus.PARTIAL,
        )
        updated_state = ATHState(
            token_address="token",
            ath_price=0.03,
            ath_mcap=30000.0,
            ath_time=LATER,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            ath_source="birdeye",
            data_status=DataStatus.OK,
        )
        event = ATHEvent(
            token_address="token",
            event_time=LATER,
            candidate_price=0.03,
            candidate_mcap=30000.0,
            candidate_source="birdeye",
            prior_ath_price=0.02,
            prior_ath_mcap=20000.0,
            new_ath_price=0.03,
            new_ath_mcap=30000.0,
            status_before=ATHStatus.PROVISIONAL,
            status_after=ATHStatus.CONFIRMED,
            confidence_before=ATHConfidence.LOW,
            confidence_after=ATHConfidence.HIGH,
            mutation_type=ATHEventType.ATH_RAISED,
            reason="higher_candidate",
            accepted=True,
            data_limited=False,
            input_snapshot={"source": "test"},
        )

        repository.upsert_state(initial_state)
        repository.upsert_state(updated_state)
        event_id = repository.insert_event(event)
        fetched_state = repository.get_state("token")
        events = repository.list_events("token")

    assert event_id > 0
    assert fetched_state.ath_price == 0.03
    assert fetched_state.ath_status == ATHStatus.CONFIRMED
    assert events == [event]


def test_alert_decision_would_alert_dispatch_and_outcome_roundtrip():
    with _repository_connection() as connection:
        decision_repo = AlertDecisionRepository(connection)
        dispatch_repo = DispatchEventRepository(connection)
        outcome_repo = OutcomeWindowRepository(connection)

        decision = AlertDecision(
            token_address="token",
            evaluated_at=NOW,
            decision_type=DecisionType.WOULD_ALERT,
            tier_index=1,
            tier_name="T1",
            primary_reason=DecisionReason.WOULD_ALERT,
            reasons=[DecisionReason.WOULD_ALERT],
            would_alert=True,
            blocked=False,
            skipped=False,
            field_score=None,
            setup_score=None,
            clock_score=None,
            risk_score=None,
            composite_score=None,
            ath_price=0.03,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            ath_source="birdeye",
            price_age_seconds=4.0,
            pump_multiple=3.0,
            drawdown_from_ath=0.6,
            filter_labels={"fee_gate": "Normal"},
            tier_context={"tier": "T1"},
            key_feature_snapshot={"liquidity_usd": 5000.0},
            policy_version="policy_v0_test",
        )

        decision_id = decision_repo.insert(decision)
        dispatch_event = DispatchEvent(
            id="evt-1",
            alert_decision_id=decision_id,
            dispatch_run_id="run-1",
            target="file_preview",
            status="pending",
            decision_type="would_alert",
            severity="CLEAN",
            tier_label="T1",
            attempted_at=NOW,
            payload_ref="preview.txt",
        )
        dispatch_repo.create(dispatch_event)
        dispatch_repo.update_status(
            event_id="evt-1",
            status="sent",
            completed_at=LATER,
            payload_ref="preview.txt",
            error_message=None,
        )
        outcome_id = outcome_repo.insert(
            OutcomeWindow(
                alert_decision_id=decision_id,
                token_address="token",
                window_seconds=300,
                window_start_time=NOW,
                window_end_time=LATER,
                alert_price=0.01,
                alert_mcap=5000.0,
                max_price=0.03,
                max_mcap=15000.0,
                max_observation_time=LATER,
                min_price=0.01,
                min_mcap=5000.0,
                min_observation_time=NOW,
                max_return_multiple=3.0,
                max_return_pct=200.0,
                min_return_multiple=1.0,
                min_return_pct=0.0,
                max_drawdown_from_peak_pct=0.0,
                time_to_max_return_seconds=300.0,
                hit_2x=True,
                hit_3x=True,
                hit_5x=False,
                observations_count=2,
                first_observation_time=NOW,
                last_observation_time=LATER,
                data_status=OutcomeWindowStatus.COMPLETE,
            )
        )

        fetched = decision_repo.get(decision_id)
        would_alerts = decision_repo.list_would_alert()
        dispatches = dispatch_repo.list_by_decision(decision_id)
        outcomes = outcome_repo.get_all_for_decision(decision_id)

    assert decision_id > 0
    assert outcome_id > 0
    assert fetched.filter_labels == {"fee_gate": "Normal"}
    assert fetched.key_feature_snapshot == {"liquidity_usd": 5000.0}
    assert would_alerts == [decision]
    assert dispatches[0].id == "evt-1"
    assert dispatches[0].status == "sent"
    assert dispatches[0].payload_ref == "preview.txt"
    assert dispatches[0].completed_at == LATER
    assert outcomes[0].hit_2x is True
    assert outcomes[0].hit_5x is False
    assert outcomes[0].alert_price == 0.01
    assert outcomes[0].max_return_multiple == 3.0
    assert outcomes[0].observations_count == 2
    assert outcomes[0].data_status == OutcomeWindowStatus.COMPLETE


NOW_PLUS_60 = datetime(2026, 5, 8, 6, 1, tzinfo=timezone.utc)
NOW_PLUS_120 = datetime(2026, 5, 8, 6, 2, tzinfo=timezone.utc)
NOW_PLUS_300 = LATER


def test_alert_decision_round_trips_price_observation_id_when_set():
    with _repository_connection() as connection:
        repository = AlertDecisionRepository(connection)
        decision = AlertDecision(
            token_address="token",
            evaluated_at=NOW,
            price_observation_id=42,
        )
        decision_id = repository.insert(decision)
        fetched = repository.get(decision_id)

    assert fetched is not None
    assert fetched.price_observation_id == 42


def test_alert_decision_round_trips_ath_event_id_when_set():
    with _repository_connection() as connection:
        repository = AlertDecisionRepository(connection)
        decision = AlertDecision(
            token_address="token",
            evaluated_at=NOW,
            ath_event_id=99,
        )
        decision_id = repository.insert(decision)
        fetched = repository.get(decision_id)

    assert fetched is not None
    assert fetched.ath_event_id == 99


def test_alert_decision_round_trips_data_status_when_set():
    with _repository_connection() as connection:
        repository = AlertDecisionRepository(connection)
        decision = AlertDecision(
            token_address="token",
            evaluated_at=NOW,
            data_status=DataStatus.OK,
        )
        decision_id = repository.insert(decision)
        fetched = repository.get(decision_id)

    assert fetched is not None
    assert fetched.data_status == DataStatus.OK


def test_alert_decision_round_trips_missing_reasons_preserving_order():
    with _repository_connection() as connection:
        repository = AlertDecisionRepository(connection)
        reasons = ["price_missing", "ath_missing", "liquidity_missing"]
        decision = AlertDecision(
            token_address="token",
            evaluated_at=NOW,
            missing_reasons=list(reasons),
        )
        decision_id = repository.insert(decision)
        fetched = repository.get(decision_id)

    assert fetched is not None
    assert fetched.missing_reasons == reasons


def test_alert_decision_audit_fields_omitted_persist_defaults():
    with _repository_connection() as connection:
        repository = AlertDecisionRepository(connection)
        decision = AlertDecision(token_address="token", evaluated_at=NOW)
        decision_id = repository.insert(decision)
        raw = connection.execute(
            """
            SELECT price_observation_id, ath_event_id, data_status,
                   missing_reasons_json
            FROM alert_decisions WHERE id = ?
            """,
            (decision_id,),
        ).fetchone()
        fetched = repository.get(decision_id)

    assert raw["price_observation_id"] is None
    assert raw["ath_event_id"] is None
    assert fetched is not None
    assert fetched.price_observation_id is None
    assert fetched.ath_event_id is None
    assert raw["data_status"] == "missing"
    assert raw["missing_reasons_json"] == "[]"
    assert fetched.data_status == DataStatus.MISSING
    assert fetched.missing_reasons == []


def test_filter_evaluation_round_trips_alert_decision_id_when_set():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        result = FilterResult(
            token_address="token",
            filter_name="fee_gate",
            as_of_time=NOW,
            alert_decision_id=77,
        )
        repository.insert(result)
        fetched = repository.list_by_token("token")

    assert len(fetched) == 1
    assert fetched[0].alert_decision_id == 77


def test_filter_evaluation_round_trips_alert_decision_id_as_none_when_omitted():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        result = FilterResult(
            token_address="token",
            filter_name="fee_gate",
            as_of_time=NOW,
        )
        repository.insert(result)
        fetched = repository.list_by_token("token")

    assert len(fetched) == 1
    assert fetched[0].alert_decision_id is None


def test_field_features_get_latest_at_or_before_returns_most_recent_at_or_before():
    with _repository_connection() as connection:
        repository = FieldFeatureRepository(connection)
        repository.insert(FieldFeatures(token_address="token", as_of_time=NOW))
        repository.insert(
            FieldFeatures(token_address="token", as_of_time=NOW_PLUS_60)
        )
        repository.insert(
            FieldFeatures(token_address="token", as_of_time=NOW_PLUS_300)
        )

        fetched = repository.get_latest_at_or_before("token", NOW_PLUS_120)

    assert fetched is not None
    assert fetched.as_of_time == NOW_PLUS_60


def test_field_features_get_latest_at_or_before_breaks_ties_by_higher_id():
    with _repository_connection() as connection:
        repository = FieldFeatureRepository(connection)
        first_id = repository.insert(
            FieldFeatures(
                token_address="token",
                as_of_time=NOW,
                feature_version="field_v0_a",
            )
        )
        second_id = repository.insert(
            FieldFeatures(
                token_address="token",
                as_of_time=NOW,
                feature_version="field_v0_b",
            )
        )

        fetched = repository.get_latest_at_or_before("token", NOW)

    assert second_id > first_id
    assert fetched is not None
    assert fetched.id == second_id


def test_field_features_get_latest_at_or_before_returns_none_when_no_row_qualifies():
    with _repository_connection() as connection:
        repository = FieldFeatureRepository(connection)
        repository.insert(
            FieldFeatures(token_address="token", as_of_time=NOW_PLUS_300)
        )

        fetched = repository.get_latest_at_or_before("token", NOW)

    assert fetched is None


def test_field_features_get_latest_at_or_before_other_tokens_do_not_match():
    with _repository_connection() as connection:
        repository = FieldFeatureRepository(connection)
        repository.insert(
            FieldFeatures(token_address="other_token", as_of_time=NOW)
        )

        fetched = repository.get_latest_at_or_before("token", NOW_PLUS_300)

    assert fetched is None


def test_score_features_get_latest_at_or_before_returns_most_recent_at_or_before():
    with _repository_connection() as connection:
        repository = ScoreFeatureRepository(connection)
        repository.insert(ScoreFeatures(token_address="token", as_of_time=NOW))
        repository.insert(
            ScoreFeatures(token_address="token", as_of_time=NOW_PLUS_60)
        )
        repository.insert(
            ScoreFeatures(token_address="token", as_of_time=NOW_PLUS_300)
        )

        fetched = repository.get_latest_at_or_before("token", NOW_PLUS_120)

    assert fetched is not None
    assert fetched.as_of_time == NOW_PLUS_60


def test_score_features_get_latest_at_or_before_breaks_ties_by_higher_id():
    with _repository_connection() as connection:
        repository = ScoreFeatureRepository(connection)
        first_id = repository.insert(
            ScoreFeatures(
                token_address="token",
                as_of_time=NOW,
                score_version="score_v0_a",
            )
        )
        second_id = repository.insert(
            ScoreFeatures(
                token_address="token",
                as_of_time=NOW,
                score_version="score_v0_b",
            )
        )

        fetched = repository.get_latest_at_or_before("token", NOW)

    assert second_id > first_id
    assert fetched is not None
    assert fetched.score_version == "score_v0_b"


def test_score_features_get_latest_at_or_before_returns_none_when_no_row_qualifies():
    with _repository_connection() as connection:
        repository = ScoreFeatureRepository(connection)
        repository.insert(
            ScoreFeatures(token_address="token", as_of_time=NOW_PLUS_300)
        )

        fetched = repository.get_latest_at_or_before("token", NOW)

    assert fetched is None


def test_score_features_get_latest_at_or_before_other_tokens_do_not_match():
    with _repository_connection() as connection:
        repository = ScoreFeatureRepository(connection)
        repository.insert(
            ScoreFeatures(token_address="other_token", as_of_time=NOW)
        )

        fetched = repository.get_latest_at_or_before("token", NOW_PLUS_300)

    assert fetched is None


def test_clock_features_get_latest_at_or_before_returns_most_recent_at_or_before():
    with _repository_connection() as connection:
        repository = ClockFeatureRepository(connection)
        repository.insert(ClockFeatures(token_address="token", as_of_time=NOW))
        repository.insert(
            ClockFeatures(token_address="token", as_of_time=NOW_PLUS_60)
        )
        repository.insert(
            ClockFeatures(token_address="token", as_of_time=NOW_PLUS_300)
        )

        fetched = repository.get_latest_at_or_before("token", NOW_PLUS_120)

    assert fetched is not None
    assert fetched.as_of_time == NOW_PLUS_60


def test_clock_features_get_latest_at_or_before_breaks_ties_by_higher_id():
    with _repository_connection() as connection:
        repository = ClockFeatureRepository(connection)
        first_id = repository.insert(
            ClockFeatures(
                token_address="token",
                as_of_time=NOW,
                feature_version="clock_v0_a",
            )
        )
        second_id = repository.insert(
            ClockFeatures(
                token_address="token",
                as_of_time=NOW,
                feature_version="clock_v0_b",
            )
        )

        fetched = repository.get_latest_at_or_before("token", NOW)

    assert second_id > first_id
    assert fetched is not None
    assert fetched.id == second_id


def test_clock_features_get_latest_at_or_before_returns_none_when_no_row_qualifies():
    with _repository_connection() as connection:
        repository = ClockFeatureRepository(connection)
        repository.insert(
            ClockFeatures(token_address="token", as_of_time=NOW_PLUS_300)
        )

        fetched = repository.get_latest_at_or_before("token", NOW)

    assert fetched is None


def test_clock_features_get_latest_at_or_before_other_tokens_do_not_match():
    with _repository_connection() as connection:
        repository = ClockFeatureRepository(connection)
        repository.insert(
            ClockFeatures(token_address="other_token", as_of_time=NOW)
        )

        fetched = repository.get_latest_at_or_before("token", NOW_PLUS_300)

    assert fetched is None


# ---------------------------------------------------------------------------
# AlertDecisionRepository.list_would_alerts_for_token (Stage 7.1 — HIGH fix)
# ---------------------------------------------------------------------------


def _insert_decision(
    repo: AlertDecisionRepository,
    *,
    token: str,
    evaluated_at: datetime,
    would_alert: bool,
    tier_index: int,
) -> int:
    return repo.insert(
        AlertDecision(
            token_address=token,
            evaluated_at=evaluated_at,
            decision_type=(
                DecisionType.WOULD_ALERT if would_alert else DecisionType.SKIP
            ),
            tier_index=tier_index if would_alert else None,
            tier_name=f"T{tier_index}" if would_alert else None,
            primary_reason=(
                DecisionReason.WOULD_ALERT
                if would_alert
                else DecisionReason.MIN_PUMP_NOT_MET
            ),
            reasons=[
                DecisionReason.WOULD_ALERT
                if would_alert
                else DecisionReason.MIN_PUMP_NOT_MET
            ],
            would_alert=would_alert,
            blocked=False,
            skipped=not would_alert,
            policy_version="filter_test",
            data_status=DataStatus.OK,
        )
    )


def test_list_would_alerts_for_token_filters_by_as_of_time_inclusive():
    t_minus_100 = NOW
    t_minus_50 = NOW + timedelta(seconds=50)
    t = NOW + timedelta(seconds=100)
    t_plus_50 = NOW + timedelta(seconds=150)
    t_plus_100 = NOW + timedelta(seconds=200)

    with _repository_connection() as connection:
        repo = AlertDecisionRepository(connection)

        # Five WOULD_ALERTs for the same token straddling t.
        _insert_decision(repo, token="token", evaluated_at=t_minus_100, would_alert=True, tier_index=2)
        _insert_decision(repo, token="token", evaluated_at=t_minus_50, would_alert=True, tier_index=2)
        _insert_decision(repo, token="token", evaluated_at=t, would_alert=True, tier_index=2)
        _insert_decision(repo, token="token", evaluated_at=t_plus_50, would_alert=True, tier_index=2)
        _insert_decision(repo, token="token", evaluated_at=t_plus_100, would_alert=True, tier_index=2)

        # A non-WOULD_ALERT row before t — must be excluded by the
        # would_alert=1 filter regardless of time.
        _insert_decision(
            repo,
            token="token",
            evaluated_at=t_minus_100 - timedelta(seconds=10),
            would_alert=False,
            tier_index=0,
        )

        # A WOULD_ALERT row for a different token before t — must be
        # excluded by the token filter when querying "token".
        _insert_decision(
            repo,
            token="other_token",
            evaluated_at=t_minus_100,
            would_alert=True,
            tier_index=2,
        )

        # as_of_time=t returns exactly the three rows at t-100, t-50, t.
        bounded = repo.list_would_alerts_for_token("token", as_of_time=t)
        assert [d.evaluated_at for d in bounded] == [
            t_minus_100,
            t_minus_50,
            t,
        ]

        # as_of_time=None returns all five same-token WOULD_ALERTs.
        unbounded = repo.list_would_alerts_for_token("token", as_of_time=None)
        assert [d.evaluated_at for d in unbounded] == [
            t_minus_100,
            t_minus_50,
            t,
            t_plus_50,
            t_plus_100,
        ]

        # other_token at t-100 only.
        other_bounded = repo.list_would_alerts_for_token("other_token", as_of_time=t)
        assert len(other_bounded) == 1
        assert other_bounded[0].evaluated_at == t_minus_100


# ---------------------------------------------------------------------------
# ATHRepository.get_state_at_or_before (Stage 7.1 — MEDIUM fix)
# ---------------------------------------------------------------------------


def _insert_ath_raise(
    repo: ATHRepository,
    *,
    token: str,
    event_time: datetime,
    new_ath_price: float,
    new_ath_mcap: float,
    prior_ath_price: Optional[float] = None,
    prior_ath_mcap: Optional[float] = None,
    status_after: ATHStatus = ATHStatus.CONFIRMED,
    confidence_after: ATHConfidence = ATHConfidence.HIGH,
    candidate_source: str = "test",
) -> int:
    return repo.insert_event(
        ATHEvent(
            token_address=token,
            event_time=event_time,
            candidate_price=new_ath_price,
            candidate_mcap=new_ath_mcap,
            candidate_source=candidate_source,
            prior_ath_price=prior_ath_price,
            prior_ath_mcap=prior_ath_mcap,
            new_ath_price=new_ath_price,
            new_ath_mcap=new_ath_mcap,
            status_before=ATHStatus.UNKNOWN,
            status_after=status_after,
            confidence_before=ATHConfidence.UNKNOWN,
            confidence_after=confidence_after,
            mutation_type=ATHEventType.ATH_RAISED,
            accepted=True,
            data_status=DataStatus.OK,
        )
    )


def test_get_state_at_or_before_returns_state_from_latest_qualifying_raise():
    t_minus_100 = NOW
    t_minus_50 = NOW + timedelta(seconds=50)
    t = NOW + timedelta(seconds=100)
    t_plus_50 = NOW + timedelta(seconds=150)

    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        first_id = _insert_ath_raise(
            repo, token="token", event_time=t_minus_100,
            new_ath_price=1.0, new_ath_mcap=1000.0,
        )
        second_id = _insert_ath_raise(
            repo, token="token", event_time=t_minus_50,
            new_ath_price=2.0, new_ath_mcap=2000.0,
            prior_ath_price=1.0, prior_ath_mcap=1000.0,
        )
        boundary_id = _insert_ath_raise(
            repo, token="token", event_time=t,
            new_ath_price=2.5, new_ath_mcap=2500.0,
            prior_ath_price=2.0, prior_ath_mcap=2000.0,
        )
        future_id = _insert_ath_raise(
            repo, token="token", event_time=t_plus_50,
            new_ath_price=3.0, new_ath_mcap=3000.0,
            prior_ath_price=2.5, prior_ath_mcap=2500.0,
        )

        result = repo.get_state_at_or_before("token", t)

    assert result is not None
    assert result.ath_price == pytest.approx(2.5)
    assert result.ath_mcap == pytest.approx(2500.0)
    assert result.ath_time == t
    assert result.last_event_id == boundary_id
    assert result.last_event_id != future_id
    # And earlier raises are not selected.
    assert result.last_event_id != second_id
    assert result.last_event_id != first_id
    assert result.ath_status == ATHStatus.CONFIRMED
    assert result.ath_confidence == ATHConfidence.HIGH


def test_get_state_at_or_before_returns_none_when_no_event_qualifies():
    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        _insert_ath_raise(
            repo, token="token", event_time=NOW + timedelta(seconds=200),
            new_ath_price=1.0, new_ath_mcap=1000.0,
        )

        result = repo.get_state_at_or_before("token", NOW)

    assert result is None


def test_get_state_at_or_before_after_all_events_returns_latest_state():
    t_first = NOW
    t_second = NOW + timedelta(seconds=100)
    t_query = NOW + timedelta(seconds=300)

    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        _insert_ath_raise(
            repo, token="token", event_time=t_first,
            new_ath_price=1.0, new_ath_mcap=1000.0,
        )
        latest_id = _insert_ath_raise(
            repo, token="token", event_time=t_second,
            new_ath_price=3.0, new_ath_mcap=3000.0,
            prior_ath_price=1.0, prior_ath_mcap=1000.0,
        )

        result = repo.get_state_at_or_before("token", t_query)

    assert result is not None
    assert result.ath_price == pytest.approx(3.0)
    assert result.ath_mcap == pytest.approx(3000.0)
    assert result.last_event_id == latest_id


def test_get_state_at_or_before_unknown_token_returns_none():
    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        _insert_ath_raise(
            repo, token="token", event_time=NOW,
            new_ath_price=1.0, new_ath_mcap=1000.0,
        )

        result = repo.get_state_at_or_before("unknown_token", NOW + timedelta(seconds=100))

    assert result is None


def test_get_state_at_or_before_none_as_of_time_raises_value_error():
    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        with pytest.raises(ValueError):
            repo.get_state_at_or_before("token", None)  # type: ignore[arg-type]


def test_get_state_at_or_before_other_token_raise_does_not_leak():
    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        _insert_ath_raise(
            repo, token="other_token", event_time=NOW,
            new_ath_price=99.0, new_ath_mcap=99000.0,
        )

        result = repo.get_state_at_or_before("token", NOW + timedelta(seconds=100))

    assert result is None


def test_get_state_at_or_before_non_raise_event_only_yields_unknown_state():
    """When only rejection events exist, ATH numerics are unknown but the
    first event's data_status / missing_reasons are preserved (matches
    ATHService's "first rejection sets state, subsequent rejections preserve"
    behavior)."""

    t_first_reject = NOW
    t_second_reject = NOW + timedelta(seconds=50)
    t_query = NOW + timedelta(seconds=100)

    with _repository_connection() as connection:
        repo = ATHRepository(connection)

        first_event_id = repo.insert_event(
            ATHEvent(
                token_address="token",
                event_time=t_first_reject,
                candidate_price=None,
                candidate_mcap=None,
                candidate_source="test",
                new_ath_price=None,
                new_ath_mcap=None,
                status_before=ATHStatus.UNKNOWN,
                status_after=ATHStatus.UNKNOWN,
                confidence_before=ATHConfidence.UNKNOWN,
                confidence_after=ATHConfidence.UNKNOWN,
                mutation_type=ATHEventType.ATH_REJECTED_INVALID,
                accepted=False,
                data_limited=True,
                data_status=DataStatus.ERROR,
                missing_reasons=["price_invalid"],
            )
        )
        latest_event_id = repo.insert_event(
            ATHEvent(
                token_address="token",
                event_time=t_second_reject,
                candidate_price=None,
                candidate_mcap=None,
                candidate_source="test",
                new_ath_price=None,
                new_ath_mcap=None,
                status_before=ATHStatus.UNKNOWN,
                status_after=ATHStatus.UNKNOWN,
                confidence_before=ATHConfidence.UNKNOWN,
                confidence_after=ATHConfidence.UNKNOWN,
                mutation_type=ATHEventType.ATH_REJECTED_INVALID,
                accepted=False,
                data_limited=True,
                data_status=DataStatus.ERROR,
                missing_reasons=["price_invalid"],
            )
        )

        result = repo.get_state_at_or_before("token", t_query)

    assert result is not None
    assert result.ath_price is None
    assert result.ath_mcap is None
    assert result.ath_status == ATHStatus.UNKNOWN
    assert result.ath_confidence == ATHConfidence.UNKNOWN
    assert result.ath_source is None
    # last_event_id tracks the latest event of any type.
    assert result.last_event_id == latest_event_id
    assert result.last_event_id != first_event_id
    # data_status / missing_reasons come from the FIRST event.
    assert result.data_status == DataStatus.ERROR
    assert result.missing_reasons == ["price_invalid"]


# ----------------------------------------------------------------------
# Stage 10 -- FilterEvaluationRepository extensions
# ----------------------------------------------------------------------


def _foreign_keys_enabled(connection) -> bool:
    row = connection.execute("PRAGMA foreign_keys").fetchone()
    if row is None:
        return False
    value = row[0]
    return bool(value) if value is not None else False


def _stage10_filter_result(
    *,
    alert_decision_id: int = 1001,
    filter_name: str = "fee_gate",
    filter_version: str = "fee_gate_v1_no_bribes",
    threshold_version: str = "thresholds_v0_observe_only",
    label: FilterLabel = FilterLabel.NORMAL,
    score: Optional[float] = 0.20,
    output_reason: Optional[dict] = None,
) -> FilterResult:
    return FilterResult(
        token_address="token",
        filter_name=filter_name,
        as_of_time=NOW,
        filter_version=filter_version,
        threshold_version=threshold_version,
        label=label,
        score=score,
        would_block=False,
        policy_action="observe",
        reason="round-trip",
        input_snapshot={"payload": {"creator_fee_share_5m": 0.55}},
        output_reason=output_reason if output_reason is not None else {
            "score_components": {"R1_creator_dominance": 0.20},
            "raw_score": 0.20,
            "normalized_score": 0.20,
            "reason_codes": ["CREATOR_FEE_SHARE_ELEVATED"],
            "known_limitations": ["BRIBES_SIGNAL_UNAVAILABLE"],
        },
        data_status=DataStatus.OK,
        missing_reasons=[],
        alert_decision_id=alert_decision_id,
    )


# T3.1
def test_t3_1_insert_round_trip_with_threshold_version_and_output_reason_json():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        repository.insert(_stage10_filter_result())
        fetched = repository.list_by_token("token")

    assert len(fetched) == 1
    row = fetched[0]
    assert row.threshold_version == "thresholds_v0_observe_only"
    assert row.label == FilterLabel.NORMAL
    assert row.output_reason is not None
    assert row.output_reason["reason_codes"] == ["CREATOR_FEE_SHARE_ELEVATED"]


# T3.2
def test_t3_2_get_by_decision_returns_all_rows_for_decision():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        repository.insert(
            _stage10_filter_result(filter_name="fee_gate", alert_decision_id=42)
        )
        repository.insert(
            _stage10_filter_result(
                filter_name="other_filter",
                filter_version="other_v1",
                threshold_version="thresholds_other_v1",
                alert_decision_id=42,
            )
        )
        repository.insert(
            _stage10_filter_result(filter_name="fee_gate", alert_decision_id=43)
        )

        rows = repository.get_by_decision(42)

    assert len(rows) == 2
    assert {r.filter_name for r in rows} == {"fee_gate", "other_filter"}


# T3.3
def test_t3_3_get_by_decision_returns_empty_for_decision_with_no_rows():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        repository.insert(_stage10_filter_result(alert_decision_id=42))

        rows = repository.get_by_decision(99)

    assert rows == []


# T3.4
def test_t3_4_exists_for_decision_true_case():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        repository.insert(_stage10_filter_result(alert_decision_id=42))

        present = repository.exists_for_decision(
            42, "fee_gate", "fee_gate_v1_no_bribes", "thresholds_v0_observe_only"
        )

    assert present is True


# T3.5
def test_t3_5_exists_for_decision_false_cases_for_each_varied_component():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        repository.insert(_stage10_filter_result(alert_decision_id=42))

        assert (
            repository.exists_for_decision(
                99,
                "fee_gate",
                "fee_gate_v1_no_bribes",
                "thresholds_v0_observe_only",
            )
            is False
        )
        assert (
            repository.exists_for_decision(
                42,
                "other_filter",
                "fee_gate_v1_no_bribes",
                "thresholds_v0_observe_only",
            )
            is False
        )
        assert (
            repository.exists_for_decision(
                42,
                "fee_gate",
                "other_v1",
                "thresholds_v0_observe_only",
            )
            is False
        )
        assert (
            repository.exists_for_decision(
                42,
                "fee_gate",
                "fee_gate_v1_no_bribes",
                "thresholds_other_v1",
            )
            is False
        )


# T3.6
def test_t3_6_unique_constraint_enforced_at_db_level():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)
        repository.insert(_stage10_filter_result(alert_decision_id=42))

        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            repository.insert(_stage10_filter_result(alert_decision_id=42))

    assert "UNIQUE constraint failed" in str(exc_info.value)


# T3.7 (conditional on PRAGMA foreign_keys per C1)
def test_t3_7_fk_runtime_enforcement_if_pragma_on():
    with _repository_connection() as connection:
        if not _foreign_keys_enabled(connection):
            pytest.skip(
                "PRAGMA foreign_keys is OFF for Stage 10 per locked design "
                "(C1). FK on filter_evaluations.alert_decision_id is "
                "declared but inert; this test enables only when enforcement "
                "is enabled by a future stage."
            )
        repository = FilterEvaluationRepository(connection)
        with pytest.raises(sqlite3.IntegrityError):
            repository.insert(_stage10_filter_result(alert_decision_id=999_999))


# T3.8
def test_t3_8_label_check_constraint_rejects_invalid_label():
    with _repository_connection() as connection:
        # Bypass the dataclass enum constraint by inserting raw SQL.
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            connection.execute(
                """
                INSERT INTO filter_evaluations (
                    token_address, as_of_time, alert_decision_id, filter_name,
                    filter_version, threshold_version, label, score, would_block,
                    policy_action, reason, input_snapshot_json,
                    output_reason_json, created_at, data_status,
                    missing_reasons_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "token",
                    NOW.isoformat(),
                    1,
                    "fee_gate",
                    "fee_gate_v1_no_bribes",
                    "thresholds_v0_observe_only",
                    "not_a_real_label",
                    0.1,
                    0,
                    "observe",
                    None,
                    "{}",
                    None,
                    NOW.isoformat(),
                    "ok",
                    "[]",
                ),
            )

    assert "CHECK constraint failed" in str(exc_info.value)


# T3.9
def test_t3_9_score_check_constraint_rejects_out_of_range():
    with _repository_connection() as connection:
        repository = FilterEvaluationRepository(connection)

        # Accept NULL.
        repository.insert(
            _stage10_filter_result(alert_decision_id=1, score=None)
        )
        # Accept 0.0, 0.5, 1.0.
        repository.insert(
            _stage10_filter_result(alert_decision_id=2, score=0.0)
        )
        repository.insert(
            _stage10_filter_result(alert_decision_id=3, score=0.5)
        )
        repository.insert(
            _stage10_filter_result(alert_decision_id=4, score=1.0)
        )

        # Reject out-of-range.
        with pytest.raises(sqlite3.IntegrityError):
            repository.insert(
                _stage10_filter_result(alert_decision_id=5, score=-0.01)
            )
        with pytest.raises(sqlite3.IntegrityError):
            repository.insert(
                _stage10_filter_result(alert_decision_id=6, score=1.01)
            )


# ----------------------------------------------------------------------
# Stage 11 -- DecisionScoreFeatures round-trip
# ----------------------------------------------------------------------


def _full_decision_score_features(
    alert_decision_id: int = 1,
    feature_version: str = "decision_features_v0_observe_only",
    schema_version: str = "schema_v0",
) -> DecisionScoreFeatures:
    return DecisionScoreFeatures(
        alert_decision_id=alert_decision_id,
        feature_version=feature_version,
        schema_version=schema_version,
        token_address="token-aaa",
        token_symbol="TOK",
        decision_time=NOW,
        as_of_time=NOW,
        tier_index=2,
        tier_name="tier_2",
        alert_price=0.0123,
        alert_market_cap=12345.6,
        ath_price=0.0500,
        ath_market_cap=50000.0,
        ath_time=NOW,
        migration_price=0.001,
        migration_market_cap=1000.0,
        migration_time=NOW,
        drop_from_ath=-0.75,
        multiple_from_migration=12.3,
        time_since_migration_seconds=300.0,
        time_since_ath_seconds=60.0,
        time_from_migration_to_ath_seconds=240.0,
        liquidity_usd=5000.0,
        event_count_5m=42,
        total_fee_5m=0.6,
        lp_fee_5m=0.2,
        protocol_fee_5m=0.1,
        creator_fee_5m=0.3,
        creator_fee_share_5m=0.5,
        lp_fee_share_5m=0.33,
        protocol_fee_share_5m=0.17,
        fee_per_event_5m=0.0143,
        events_per_minute_5m=8.4,
        fees_per_minute_5m=0.12,
        source_snapshot={
            "envelope": {"feature_version": feature_version},
            "upstream_refs": {"alert_decision_id": alert_decision_id},
            "ath_provenance": {"ath_status": "confirmed"},
            "basis_flags": {"pump_multiple_basis": "mcap"},
            "aux_windows": {"60s": {"event_count": 9}},
            "clock_aux": {"sequence_phase": "pullback"},
        },
        created_at=LATER,
        data_status=DataStatus.OK,
        missing_reasons=("liquidity_usd_unpopulated",),
    )


def test_decision_score_features_roundtrip_full_row():
    snapshot = _full_decision_score_features()
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(snapshot)
        loaded = repository.get_by_id(new_id)

    assert loaded is not None
    assert loaded.id == new_id
    # Compare every field by reconstructing the dataclass minus the
    # service-assigned id (which the input had as None).
    expected = DecisionScoreFeatures(
        **{**snapshot.__dict__, "id": new_id}
    )
    assert loaded == expected


def test_decision_score_features_roundtrip_partial_with_nulls():
    """A PARTIAL snapshot with NULL measurements survives round-trip."""

    snapshot = DecisionScoreFeatures(
        alert_decision_id=2,
        feature_version="decision_features_v0_observe_only",
        schema_version="schema_v0",
        token_address="token-bbb",
        decision_time=NOW,
        as_of_time=NOW,
        # Every measurement column intentionally None.
        source_snapshot={"envelope": {"note": "partial fixture"}},
        created_at=LATER,
        data_status=DataStatus.PARTIAL,
        missing_reasons=("field_features_missing", "clock_features_missing"),
    )
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(snapshot)
        loaded = repository.get_by_id(new_id)

    assert loaded is not None
    assert loaded.alert_price is None
    assert loaded.event_count_5m is None
    assert loaded.total_fee_5m is None
    assert loaded.tier_index is None
    assert loaded.token_symbol is None
    assert loaded.data_status == DataStatus.PARTIAL
    assert loaded.missing_reasons == (
        "field_features_missing",
        "clock_features_missing",
    )


def test_decision_score_features_get_by_decision_and_version_returns_existing():
    snapshot = _full_decision_score_features(alert_decision_id=11)
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(snapshot)
        existing = repository.get_by_decision_and_version(
            11, "decision_features_v0_observe_only"
        )

    assert existing is not None
    assert existing.id == new_id


def test_decision_score_features_get_by_decision_and_version_returns_none_when_absent():
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        result = repository.get_by_decision_and_version(
            999, "decision_features_v0_observe_only"
        )

    assert result is None


def test_decision_score_features_get_all_for_decision_orders_by_id_asc():
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        v0_id = repository.insert(
            _full_decision_score_features(
                alert_decision_id=7,
                feature_version="decision_features_v0_observe_only",
            )
        )
        v1_id = repository.insert(
            _full_decision_score_features(
                alert_decision_id=7,
                feature_version="decision_features_v1_observe_only",
            )
        )
        rows = repository.get_all_for_decision(7)

    assert [row.id for row in rows] == [v0_id, v1_id]
    assert [row.feature_version for row in rows] == [
        "decision_features_v0_observe_only",
        "decision_features_v1_observe_only",
    ]


def test_decision_score_features_list_by_token_chronological_capped():
    earlier = NOW - timedelta(hours=2)
    middle = NOW - timedelta(hours=1)
    later = NOW
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        for index, when in enumerate((earlier, middle, later), start=1):
            row = _full_decision_score_features(alert_decision_id=index)
            repository.insert(
                DecisionScoreFeatures(**{**row.__dict__, "decision_time": when})
            )
        recent = repository.list_by_token("token-aaa", limit=2)

    assert len(recent) == 2
    assert recent[0].decision_time == later
    assert recent[1].decision_time == middle


def test_decision_score_features_unique_race_raises_integrity_error():
    """The repository surfaces the UNIQUE-constraint violation directly.

    Stage 11's service layer (``DecisionFeatureSnapshotService``) catches
    this, re-probes via ``get_by_decision_and_version``, and treats the
    second insert as already_recorded. The repository itself does not
    swallow the error.
    """

    snapshot = _full_decision_score_features(alert_decision_id=33)
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        repository.insert(snapshot)
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            # Re-insert the same (decision, feature_version) -> duplicate.
            repository.insert(
                _full_decision_score_features(alert_decision_id=33)
            )

    assert "UNIQUE constraint failed" in str(exc_info.value)


def test_decision_score_features_source_snapshot_json_round_trips_compact_sorted():
    """The ``source_snapshot`` dict survives the JSON round-trip via the
    standard ``_json_dict`` helper (which serializes with sorted keys
    and ``(",", ":")`` separators).
    """

    snapshot = _full_decision_score_features(alert_decision_id=44)
    with _repository_connection_stage11() as connection:
        repository = DecisionScoreFeatureRepository(connection)
        new_id = repository.insert(snapshot)
        # Inspect the raw JSON to verify the on-disk shape.
        raw_json = connection.execute(
            "SELECT source_snapshot_json FROM decision_score_features "
            "WHERE id = ?",
            (new_id,),
        ).fetchone()["source_snapshot_json"]
        loaded = repository.get_by_id(new_id)

    # Compact serialization: no whitespace.
    assert " " not in raw_json
    # Sorted keys at the top level (envelope < upstream_refs < ...).
    assert raw_json.index('"envelope"') < raw_json.index('"upstream_refs"')
    # The deserialized dict matches the input.
    assert loaded is not None
    assert loaded.source_snapshot == snapshot.source_snapshot


def test_fee_window_get_by_id_returns_existing_row():
    """The Stage 11 ride-along addition. Round-trip via id."""

    with _repository_connection_stage11() as connection:
        repository = FeeWindowRepository(connection)
        new_id = repository.insert(
            FeeWindow(
                token_address="token",
                as_of_time=LATER,
                window_seconds=300,
                pool_address="pool",
                event_count=5,
                total_fee_sol=0.5,
                lp_fee_sol=0.2,
                protocol_fee_sol=0.1,
                creator_fee_sol=0.2,
                avg_fee_per_event_sol=0.1,
                events_per_min=1.0,
                fees_per_min_sol=0.1,
                data_status=DataStatus.OK,
            )
        )
        loaded = repository.get_by_id(new_id)
        missing = repository.get_by_id(99999)

    assert loaded is not None
    assert loaded.id == new_id
    assert loaded.token_address == "token"
    assert loaded.window_seconds == 300
    assert loaded.event_count == 5
    assert loaded.total_fee_sol == 0.5
    assert missing is None
