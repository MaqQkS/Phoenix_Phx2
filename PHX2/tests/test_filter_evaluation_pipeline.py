"""Layer 7 E2E tests for the FilterEvaluation pipeline.

These tests wire AlertEligibilityEngine and FilterEvaluationEngine
against the same fresh-DB connection and verify three invariants:

 - T7.1: full happy path (WOULD_ALERT decision -> filter_evaluations row).
 - T7.2: AlertDecision row produced by Stage 7 is byte-for-byte unchanged
   after Stage 10's evaluate_for_decision call.
 - T7.3: Stage 10 writes only filter_evaluations -- every other observed
   table's row count is unchanged across the engine call. Mirrors the
   AlertEligibilityEngine's _OBSERVED_TABLES style.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Tuple

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import PHX2Connection, get_phx2_connection
from PHX2.db.migrations import apply_stage10_schema
from PHX2.db.repositories import repository_registry
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    DataStatus,
    DecisionType,
    FeeWindow,
    FieldFeatures,
    PriceObservation,
    TokenState,
)
from PHX2.services.alert_eligibility_engine import AlertEligibilityEngine
from PHX2.services.filter_evaluation_engine import FilterEvaluationEngine


TOKEN = "tokenA"
EVAL_TIME = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
MIG_TIME = EVAL_TIME - timedelta(hours=1)
ATH_TIME = EVAL_TIME - timedelta(minutes=20)
OBS_TIME = EVAL_TIME - timedelta(seconds=60)


_OBSERVED_TABLES = (
    "token_sequence_state",
    "price_observations",
    "ath_state",
    "ath_events",
    "field_features",
    "clock_features",
    "score_features",
    "dispatch_events",
    "outcome_windows",
    "price_curve_points",
    "fee_windows",
    "raw_pumpswap_events",
    "migration_events",
    "alert_decisions",
)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"e2e_filters_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _pipeline_context() -> Iterator[Tuple[PHX2Connection, AlertEligibilityEngine, FilterEvaluationEngine]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage10_schema(connection)
        registry = repository_registry(connection)
        alert_engine = AlertEligibilityEngine(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            alert_decisions=registry.alert_decisions,
            current_time_provider=lambda: EVAL_TIME,
        )
        filter_engine = FilterEvaluationEngine(
            alert_decisions=registry.alert_decisions,
            field_features=registry.field_features,
            filter_evaluations=registry.filter_evaluations,
            current_time_provider=lambda: EVAL_TIME,
        )
        yield connection, alert_engine, filter_engine
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _insert_eligible_state(connection: PHX2Connection) -> None:
    """Set up a fully-eligible token state that produces a T1 WOULD_ALERT.

    Mirrors PHX2/tests/test_alert_eligibility_engine.py::_insert_eligible_state
    at drawdown=0.60, pump=4.0. Also seeds field_features with the four
    Fee Gate required primitives so the OK row is producible.
    """

    registry = repository_registry(connection)

    ath_price = 100.0
    ath_mcap = 100_000.0
    cur_price = ath_price * (1.0 - 0.60)  # 60% drawdown
    cur_mcap = ath_mcap * (1.0 - 0.60)
    mig_price = cur_price / 4.0  # 4x pump
    mig_mcap = cur_mcap / 4.0

    registry.token_sequence.upsert(
        TokenState(
            token_address=TOKEN,
            symbol="TST",
            pool_address="pool",
            migration_time=MIG_TIME,
            migration_source="test",
            migration_price=mig_price,
            migration_mcap=mig_mcap,
            current_price=cur_price,
            current_mcap=cur_mcap,
            last_price_update=OBS_TIME,
            data_status=DataStatus.OK,
        )
    )
    registry.price_observations.insert(
        PriceObservation(
            token_address=TOKEN,
            observed_at=OBS_TIME,
            source="test",
            price=cur_price,
            mcap=cur_mcap,
            data_status=DataStatus.OK,
        )
    )
    ath_event_id = registry.ath.insert_event(
        ATHEvent(
            token_address=TOKEN,
            event_time=ATH_TIME,
            candidate_price=ath_price,
            candidate_mcap=ath_mcap,
            candidate_source="test",
            new_ath_price=ath_price,
            new_ath_mcap=ath_mcap,
            status_before=ATHStatus.UNKNOWN,
            status_after=ATHStatus.CONFIRMED,
            confidence_before=ATHConfidence.UNKNOWN,
            confidence_after=ATHConfidence.HIGH,
            mutation_type=ATHEventType.ATH_RAISED,
            accepted=True,
            data_status=DataStatus.OK,
        )
    )
    registry.ath.upsert_state(
        ATHState(
            token_address=TOKEN,
            ath_price=ath_price,
            ath_mcap=ath_mcap,
            ath_time=ATH_TIME,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            ath_source="test",
            last_event_id=ath_event_id,
            data_status=DataStatus.OK,
        )
    )
    # Field features carrying the four Fee Gate required primitives so the
    # filter row is producible (and OK).
    registry.field_features.upsert(
        FieldFeatures(
            token_address=TOKEN,
            as_of_time=OBS_TIME,
            feature_version="field_v0_test",
            creator_fee_share_5m=0.10,
            lp_fee_share_5m=0.80,
            protocol_fee_share_5m=0.10,
            buy_sell_ratio_5m=1.0,
            event_pace_5m=1.0,
            fee_pace_5m_sol=0.05,
            event_count_5m=600,
            data_status=DataStatus.OK,
        )
    )


def _count(connection: PHX2Connection, table_name: str) -> int:
    return int(
        connection.execute(
            f"SELECT COUNT(*) AS count FROM {table_name}"
        ).fetchone()["count"]
    )


def _fetch_alert_decision_row(connection: PHX2Connection, decision_id: int):
    row = connection.execute(
        "SELECT * FROM alert_decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    return None if row is None else dict(row)


# ----------------------------------------------------------------------
# T7.1 -- Full pipeline happy path
# ----------------------------------------------------------------------


def test_t7_1_full_pipeline_writes_filter_evaluation_for_would_alert():
    with _pipeline_context() as (connection, alert_engine, filter_engine):
        _insert_eligible_state(connection)

        decision = alert_engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.WOULD_ALERT

        # Fetch the decision id.
        decision_id_row = connection.execute(
            "SELECT id FROM alert_decisions WHERE token_address = ? "
            "ORDER BY id DESC LIMIT 1",
            (TOKEN,),
        ).fetchone()
        assert decision_id_row is not None
        decision_id = int(decision_id_row["id"])

        result = filter_engine.evaluate_for_decision(decision_id, EVAL_TIME)

        assert result.error is None
        assert result.completed_count == 1
        assert len(result.results) == 1

        fe_rows = list(
            connection.execute(
                "SELECT * FROM filter_evaluations WHERE alert_decision_id = ?",
                (decision_id,),
            )
        )

    assert len(fe_rows) == 1
    assert fe_rows[0]["filter_name"] == "fee_gate"


# ----------------------------------------------------------------------
# T7.2 -- AlertDecision row unchanged after Stage 10 call
# ----------------------------------------------------------------------


def test_t7_2_alert_decision_row_unchanged_after_filter_evaluation():
    with _pipeline_context() as (connection, alert_engine, filter_engine):
        _insert_eligible_state(connection)
        alert_engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        decision_id_row = connection.execute(
            "SELECT id FROM alert_decisions WHERE token_address = ? "
            "ORDER BY id DESC LIMIT 1",
            (TOKEN,),
        ).fetchone()
        decision_id = int(decision_id_row["id"])

        before = _fetch_alert_decision_row(connection, decision_id)
        filter_engine.evaluate_for_decision(decision_id, EVAL_TIME)
        after = _fetch_alert_decision_row(connection, decision_id)

    assert before is not None
    assert after is not None
    assert before == after


# ----------------------------------------------------------------------
# T7.3 -- Stage 10 writes only filter_evaluations
# ----------------------------------------------------------------------


def test_t7_3_filter_evaluation_engine_writes_only_filter_evaluations_table():
    with _pipeline_context() as (connection, alert_engine, filter_engine):
        _insert_eligible_state(connection)
        alert_engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        decision_id_row = connection.execute(
            "SELECT id FROM alert_decisions WHERE token_address = ? "
            "ORDER BY id DESC LIMIT 1",
            (TOKEN,),
        ).fetchone()
        decision_id = int(decision_id_row["id"])

        before_observed = {t: _count(connection, t) for t in _OBSERVED_TABLES}
        before_filter_evaluations = _count(connection, "filter_evaluations")

        filter_engine.evaluate_for_decision(decision_id, EVAL_TIME)

        after_observed = {t: _count(connection, t) for t in _OBSERVED_TABLES}
        after_filter_evaluations = _count(connection, "filter_evaluations")

    for table in _OBSERVED_TABLES:
        assert before_observed[table] == after_observed[table], (
            f"{table} changed: {before_observed[table]} -> "
            f"{after_observed[table]}"
        )
    assert after_filter_evaluations == before_filter_evaluations + 1
