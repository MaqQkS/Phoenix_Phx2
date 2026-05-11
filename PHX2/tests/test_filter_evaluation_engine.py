"""Layer 2 integration tests for FilterEvaluationEngine.

These tests use the real SQLite repositories against a per-test temp
DB. They exercise the engine's contract across single-filter happy
path, multi-filter substrate honesty, per-filter error isolation,
idempotency, UNIQUE-constraint race handling, and validation-failure
return-with-error semantics. Inline fake filters
(``AlwaysNormalFilter``, ``AlwaysRaisesFilter``) are defined locally
so the engine path can be exercised without relying on FeeGateFilter
internals.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import PHX2Connection, get_phx2_connection
from PHX2.db.migrations import apply_stage10_schema
from PHX2.db.repositories import repository_registry
from PHX2.filters.base import Filter, FilterContext
from PHX2.filters.fee_gate import FeeGateFilter
from PHX2.models import (
    ATHConfidence,
    ATHStatus,
    AlertDecision,
    DataStatus,
    DecisionReason,
    DecisionType,
    FieldFeatures,
    FilterLabel,
    FilterResult,
)
from PHX2.services.filter_evaluation_engine import (
    ERROR_ALERT_DECISION_NOT_FOUND,
    ERROR_DECISION_TYPE_NOT_WOULD_ALERT,
    FilterEvaluationEngine,
)


TOKEN = "tokenA"
EVAL_TIME = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Inline fake filters
# ----------------------------------------------------------------------


class AlwaysNormalFilter(Filter):
    """A filter that always returns FilterLabel.NORMAL with score=0.0."""

    NAME = "always_normal"
    VERSION = "always_normal_v1"
    THRESHOLDS = "thresholds_always_normal_v1"

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def filter_version(self) -> str:
        return self.VERSION

    @property
    def threshold_version(self) -> str:
        return self.THRESHOLDS

    @property
    def known_limitations(self) -> List[str]:
        return ["TEST_FAKE"]

    def evaluate(self, context: FilterContext) -> FilterResult:
        return FilterResult(
            token_address=context.token_address,
            filter_name=self.NAME,
            as_of_time=context.as_of_time,
            filter_version=self.VERSION,
            threshold_version=self.THRESHOLDS,
            label=FilterLabel.NORMAL,
            score=0.0,
            would_block=False,
            policy_action="observe",
            reason="always_normal",
            input_snapshot={"fake": True},
            output_reason={"fake": True, "known_limitations": ["TEST_FAKE"]},
            data_status=DataStatus.OK,
            missing_reasons=[],
            alert_decision_id=context.alert_decision_id,
        )


class AlwaysRaisesFilter(Filter):
    """A filter whose evaluate() always raises a deterministic exception."""

    NAME = "always_raises"
    VERSION = "always_raises_v1"
    THRESHOLDS = "thresholds_always_raises_v1"

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def filter_version(self) -> str:
        return self.VERSION

    @property
    def threshold_version(self) -> str:
        return self.THRESHOLDS

    @property
    def known_limitations(self) -> List[str]:
        return ["TEST_RAISES"]

    def evaluate(self, context: FilterContext) -> FilterResult:
        raise RuntimeError("synthetic test failure")


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"filter_engine_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _engine_context(
    *,
    filters: Optional[Tuple[Filter, ...]] = None,
    clock_value: Optional[datetime] = None,
) -> Iterator[Tuple[PHX2Connection, FilterEvaluationEngine]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage10_schema(connection)
        registry = repository_registry(connection)
        kwargs = {}
        if filters is not None:
            kwargs["filters"] = filters
        if clock_value is not None:
            kwargs["current_time_provider"] = lambda: clock_value
        engine = FilterEvaluationEngine(
            alert_decisions=registry.alert_decisions,
            field_features=registry.field_features,
            filter_evaluations=registry.filter_evaluations,
            **kwargs,
        )
        yield connection, engine
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _insert_would_alert_decision(
    connection: PHX2Connection,
    *,
    token_address: str = TOKEN,
    evaluated_at: datetime = EVAL_TIME,
    decision_type: DecisionType = DecisionType.WOULD_ALERT,
    would_alert: bool = True,
) -> int:
    registry = repository_registry(connection)
    decision = AlertDecision(
        token_address=token_address,
        evaluated_at=evaluated_at,
        decision_type=decision_type,
        primary_reason=(
            DecisionReason.WOULD_ALERT
            if decision_type == DecisionType.WOULD_ALERT
            else DecisionReason.MIN_PUMP_NOT_MET
        ),
        reasons=[
            DecisionReason.WOULD_ALERT
            if decision_type == DecisionType.WOULD_ALERT
            else DecisionReason.MIN_PUMP_NOT_MET
        ],
        would_alert=would_alert,
        skipped=not would_alert,
        ath_status=ATHStatus.CONFIRMED,
        ath_confidence=ATHConfidence.HIGH,
        current_price=1.0,
        current_mcap=100.0,
        policy_version="policy_v0_test",
        data_status=DataStatus.OK,
    )
    return registry.alert_decisions.insert(decision)


def _insert_field_features(
    connection: PHX2Connection,
    *,
    token_address: str = TOKEN,
    as_of_time: datetime = EVAL_TIME,
) -> FieldFeatures:
    registry = repository_registry(connection)
    features = FieldFeatures(
        token_address=token_address,
        as_of_time=as_of_time,
        creator_fee_share_5m=0.10,
        lp_fee_share_5m=0.80,
        protocol_fee_share_5m=0.10,
        buy_sell_ratio_5m=1.0,
        event_pace_5m=1.0,
        fee_pace_5m_sol=0.05,
        event_count_5m=600,
        data_status=DataStatus.OK,
    )
    feature_id = registry.field_features.insert(features)
    return registry.field_features.get_by_id(feature_id)


# ----------------------------------------------------------------------
# T2.1 -- Single-filter happy path
# ----------------------------------------------------------------------


def test_t2_1_single_filter_happy_path():
    with _engine_context() as (connection, engine):
        decision_id = _insert_would_alert_decision(connection)
        _insert_field_features(connection)

        result = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)

    assert result.error is None
    assert result.total_filters == 1
    assert result.completed_count == 1
    assert result.missing_inputs_count == 0
    assert result.error_count == 0
    assert result.already_recorded_count == 0
    assert len(result.results) == 1
    row = result.results[0]
    assert row.filter_name == "fee_gate"
    assert row.alert_decision_id == decision_id
    assert row.data_status == DataStatus.OK


# ----------------------------------------------------------------------
# T2.2 -- Multi-filter substrate honesty (real + fake)
# ----------------------------------------------------------------------


def test_t2_2_multi_filter_substrate_honesty():
    with _engine_context(
        filters=(FeeGateFilter(), AlwaysNormalFilter())
    ) as (connection, engine):
        decision_id = _insert_would_alert_decision(connection)
        _insert_field_features(connection)

        result = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)

    assert result.error is None
    assert result.total_filters == 2
    assert result.completed_count == 2
    assert result.error_count == 0
    filter_names = {row.filter_name for row in result.results}
    assert filter_names == {"fee_gate", AlwaysNormalFilter.NAME}


# ----------------------------------------------------------------------
# T2.3 -- Per-filter error isolation
# ----------------------------------------------------------------------


def test_t2_3_per_filter_error_isolation():
    with _engine_context(
        filters=(FeeGateFilter(), AlwaysRaisesFilter())
    ) as (connection, engine):
        decision_id = _insert_would_alert_decision(connection)
        _insert_field_features(connection)

        result = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)

    assert result.error is None
    assert result.total_filters == 2
    assert result.completed_count == 1
    assert result.error_count == 1
    # Fee Gate produces an OK row; the fake produces an ERROR row.
    fee_gate_row = next(r for r in result.results if r.filter_name == "fee_gate")
    fake_row = next(
        r for r in result.results if r.filter_name == AlwaysRaisesFilter.NAME
    )
    assert fee_gate_row.data_status == DataStatus.OK
    assert fake_row.data_status == DataStatus.ERROR
    assert fake_row.label == FilterLabel.UNKNOWN
    assert fake_row.score is None
    assert fake_row.would_block is False
    assert fake_row.output_reason["error"]["exception_class"] == "RuntimeError"


# ----------------------------------------------------------------------
# T2.4 -- Idempotency: second call writes zero new rows
# ----------------------------------------------------------------------


def test_t2_4_idempotency_writes_zero_new_rows_on_second_call():
    with _engine_context() as (connection, engine):
        decision_id = _insert_would_alert_decision(connection)
        _insert_field_features(connection)

        first = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)
        second = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)

        registry = repository_registry(connection)
        all_rows = registry.filter_evaluations.get_by_decision(decision_id)

    assert first.completed_count == 1
    assert first.already_recorded_count == 0
    assert second.completed_count == 0
    assert second.already_recorded_count == 1
    assert len(all_rows) == 1


# ----------------------------------------------------------------------
# T2.5 -- UNIQUE constraint race simulation
# ----------------------------------------------------------------------


def test_t2_5_unique_constraint_race_resolves_as_already_recorded():
    with _engine_context() as (connection, engine):
        decision_id = _insert_would_alert_decision(connection)
        _insert_field_features(connection)
        registry = repository_registry(connection)

        # Hand-insert a row directly. Then patch exists_for_decision so the
        # engine's pre-check skips it, forcing the insert path to hit the
        # UNIQUE-constraint violation.
        fee_gate = FeeGateFilter()
        preset_row = FilterResult(
            token_address=TOKEN,
            filter_name=fee_gate.name,
            as_of_time=EVAL_TIME,
            filter_version=fee_gate.filter_version,
            threshold_version=fee_gate.threshold_version,
            label=FilterLabel.NORMAL,
            score=0.0,
            would_block=False,
            policy_action="observe",
            reason="preset",
            input_snapshot={},
            output_reason=None,
            data_status=DataStatus.OK,
            missing_reasons=[],
            alert_decision_id=decision_id,
        )
        registry.filter_evaluations.insert(preset_row)
        engine.filter_evaluations.exists_for_decision = (
            lambda *args, **kwargs: False
        )

        result = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)

        all_rows = registry.filter_evaluations.get_by_decision(decision_id)

    assert result.error is None
    assert result.already_recorded_count == 1
    assert result.completed_count == 0
    assert len(all_rows) == 1


# ----------------------------------------------------------------------
# T2.6 -- Unknown decision_id returns error result (no raise)
# ----------------------------------------------------------------------


def test_t2_6_unknown_decision_id_returns_error_result_not_raise():
    with _engine_context() as (_, engine):
        result = engine.evaluate_for_decision(99999, as_of_time=EVAL_TIME)

    assert result.error == ERROR_ALERT_DECISION_NOT_FOUND
    assert result.results == []
    assert result.total_filters == 1
    assert result.completed_count == 0
    assert result.missing_inputs_count == 0
    assert result.error_count == 0
    assert result.already_recorded_count == 0


# ----------------------------------------------------------------------
# T2.7 -- Non-WOULD_ALERT decision returns error result (no raise)
# ----------------------------------------------------------------------


def test_t2_7_non_would_alert_decision_returns_error_result_not_raise():
    with _engine_context() as (connection, engine):
        skip_decision_id = _insert_would_alert_decision(
            connection,
            decision_type=DecisionType.SKIP,
            would_alert=False,
        )

        result = engine.evaluate_for_decision(
            skip_decision_id, as_of_time=EVAL_TIME
        )

    assert result.error == ERROR_DECISION_TYPE_NOT_WOULD_ALERT
    assert result.results == []
    assert result.total_filters == 1
    assert result.completed_count == 0


# ----------------------------------------------------------------------
# T2.8 -- Missing field_features produces MISSING rows
# ----------------------------------------------------------------------


def test_t2_8_missing_field_features_produces_missing_rows():
    with _engine_context() as (connection, engine):
        decision_id = _insert_would_alert_decision(connection)
        # No field_features inserted -- get_latest_at_or_before returns None.

        result = engine.evaluate_for_decision(decision_id, as_of_time=EVAL_TIME)

    assert result.error is None
    assert result.total_filters == 1
    assert result.completed_count == 0
    assert result.missing_inputs_count == 1
    assert result.error_count == 0
    assert len(result.results) == 1
    row = result.results[0]
    assert row.data_status == DataStatus.MISSING
    assert row.label == FilterLabel.UNKNOWN
    assert row.score is None
    assert "creator_fee_share_5m" in row.missing_reasons
