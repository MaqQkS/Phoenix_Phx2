"""Tests for PHX2 AlertEligibilityEngine."""

import socket
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional, Tuple

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import PHX2Connection, get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import (
    ATHRepository,
    AlertDecisionRepository,
    ClockFeatureRepository,
    FieldFeatureRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
    repository_registry,
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
    DecisionType,
    FieldFeatures,
    PriceObservation,
    TokenState,
)
from PHX2.services.alert_eligibility_engine import (
    DEFAULT_ALERT_POLICY,
    AlertEligibilityEngine,
    AlertPolicy,
    AlertTier,
)


TOKEN = "tokenA"
EVAL_TIME = datetime(2026, 5, 8, 10, 0, 0, tzinfo=timezone.utc)
MIG_TIME = EVAL_TIME - timedelta(hours=1)
ATH_TIME = MIG_TIME + timedelta(minutes=10)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"alert_engine_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _engine_context(
    *, policy: Optional[AlertPolicy] = None
) -> Iterator[Tuple[PHX2Connection, AlertEligibilityEngine]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        registry = repository_registry(connection)
        engine = AlertEligibilityEngine(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            alert_decisions=registry.alert_decisions,
            policy=policy,
            current_time_provider=lambda: EVAL_TIME,
        )
        yield connection, engine
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _count(connection: PHX2Connection, table_name: str) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table_name}"
    ).fetchone()
    return int(row["count"])


def _insert_eligible_state(
    connection: PHX2Connection,
    *,
    token: str = TOKEN,
    drawdown: float = 0.60,
    pump: float = 4.0,
    ath_status: ATHStatus = ATHStatus.CONFIRMED,
    ath_confidence: ATHConfidence = ATHConfidence.HIGH,
    observation_age_seconds: float = 60.0,
    include_field: bool = True,
    include_clock: bool = True,
    include_mcap: bool = True,
    include_price: bool = True,
    migration_present: bool = True,
    current_price_override: Optional[float] = None,
    current_mcap_override: Optional[float] = None,
    migration_price_override: Optional[float] = None,
    migration_mcap_override: Optional[float] = None,
    ath_price_override: Optional[float] = None,
    ath_mcap_override: Optional[float] = None,
) -> Tuple[int, int, int, int]:
    """Insert a fully-eligible token fixture and return source ids.

    Returns (price_observation_id, ath_event_id, field_features_id_or_0,
    clock_features_id_or_0).
    """

    ath_price = 100.0
    ath_mcap = 100000.0
    cur_price = ath_price * (1.0 - drawdown)
    cur_mcap = ath_mcap * (1.0 - drawdown)
    mig_price = cur_price / pump
    mig_mcap = cur_mcap / pump
    obs_time = EVAL_TIME - timedelta(seconds=observation_age_seconds)

    # Apply per-test overrides.
    if current_price_override is not None:
        cur_price = current_price_override
    elif not include_price:
        cur_price = None
    if current_mcap_override is not None:
        cur_mcap = current_mcap_override
    elif not include_mcap:
        cur_mcap = None
    if migration_price_override is not None:
        mig_price = migration_price_override
    if migration_mcap_override is not None:
        mig_mcap = migration_mcap_override
    if ath_price_override is not None:
        ath_price = ath_price_override
    if ath_mcap_override is not None:
        ath_mcap = ath_mcap_override

    if not migration_present:
        mig_price = None
        mig_mcap = None

    TokenSequenceRepository(connection).upsert(
        TokenState(
            token_address=token,
            symbol="TST",
            pool_address="pool",
            migration_time=MIG_TIME,
            migration_source="test",
            migration_price=mig_price,
            migration_mcap=mig_mcap,
            current_price=cur_price,
            current_mcap=cur_mcap,
            last_price_update=obs_time,
            data_status=DataStatus.OK,
        )
    )

    price_obs_id = PriceObservationRepository(connection).insert(
        PriceObservation(
            token_address=token,
            observed_at=obs_time,
            source="test",
            price=cur_price,
            mcap=cur_mcap,
            data_status=DataStatus.OK,
        )
    )

    ath_repo = ATHRepository(connection)
    ath_event_id = ath_repo.insert_event(
        ATHEvent(
            token_address=token,
            event_time=ATH_TIME,
            candidate_price=ath_price,
            candidate_mcap=ath_mcap,
            candidate_source="test",
            new_ath_price=ath_price,
            new_ath_mcap=ath_mcap,
            status_before=ATHStatus.UNKNOWN,
            status_after=ath_status,
            confidence_before=ATHConfidence.UNKNOWN,
            confidence_after=ath_confidence,
            mutation_type=ATHEventType.ATH_RAISED,
            accepted=True,
            data_status=DataStatus.OK,
        )
    )
    ath_repo.upsert_state(
        ATHState(
            token_address=token,
            ath_price=ath_price,
            ath_mcap=ath_mcap,
            ath_time=ATH_TIME,
            ath_status=ath_status,
            ath_confidence=ath_confidence,
            ath_source="test",
            last_event_id=ath_event_id,
            data_status=DataStatus.OK,
        )
    )

    field_id = 0
    if include_field:
        field_id = FieldFeatureRepository(connection).upsert(
            FieldFeatures(
                token_address=token,
                as_of_time=obs_time,
                feature_version="field_v0_test",
                data_status=DataStatus.OK,
            )
        )

    clock_id = 0
    if include_clock:
        clock_id = ClockFeatureRepository(connection).upsert(
            ClockFeatures(
                token_address=token,
                as_of_time=obs_time,
                feature_version="clock_v0_test",
                data_status=DataStatus.OK,
            )
        )

    return (price_obs_id, ath_event_id, field_id, clock_id)


# ---------------------------------------------------------------------------
# 1-3. Tier eligibility happy paths
# ---------------------------------------------------------------------------


def test_eligible_t1_produces_would_alert():
    with _engine_context() as (connection, engine):
        price_obs_id, ath_event_id, _, _ = _insert_eligible_state(
            connection, drawdown=0.60
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 1
        assert decision.tier_name == "T1"
        assert decision.primary_reason == DecisionReason.WOULD_ALERT
        assert decision.would_alert is True
        assert decision.blocked is False
        assert decision.skipped is False
        assert decision.drawdown_from_ath == pytest.approx(0.60)
        assert decision.pump_multiple == pytest.approx(4.0)
        assert decision.price_observation_id == price_obs_id
        assert decision.ath_event_id == ath_event_id
        assert decision.data_status == DataStatus.OK
        assert decision.tier_context["matched_tier"] == "T1"
        assert decision.tier_context["tier_index"] == 1


def test_eligible_t2_produces_would_alert():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.70)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 2
        assert decision.tier_name == "T2"
        assert decision.drawdown_from_ath == pytest.approx(0.70)


def test_eligible_t3_at_max_inclusive_boundary():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.93)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 3
        assert decision.tier_name == "T3"
        assert decision.drawdown_from_ath == pytest.approx(0.93)
        # Confirm policy boundary report says T3 upper bound is inclusive.
        ranges = decision.tier_context["ranges"]
        assert ranges["T3"]["max_inclusive"] is True
        assert ranges["T1"]["max_inclusive"] is False
        assert ranges["T2"]["max_inclusive"] is False
        assert ranges["T1"]["min_inclusive"] is True


# ---------------------------------------------------------------------------
# 4-6. Token / observation / current price missing
# ---------------------------------------------------------------------------


def test_token_not_found():
    with _engine_context() as (_connection, engine):
        decision = engine.evaluate_token("does-not-exist", as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.TOKEN_NOT_FOUND
        assert decision.skipped is True
        assert decision.would_alert is False
        assert decision.data_status == DataStatus.MISSING
        assert "token_not_found" in decision.missing_reasons


def test_no_price_observation():
    with _engine_context() as (connection, engine):
        TokenSequenceRepository(connection).upsert(
            TokenState(
                token_address=TOKEN,
                migration_time=MIG_TIME,
                migration_price=10.0,
                migration_mcap=10000.0,
                data_status=DataStatus.OK,
            )
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MISSING_PRICE_OBSERVATION
        assert decision.data_status == DataStatus.MISSING
        assert "missing_price_observation" in decision.missing_reasons


def test_current_price_and_mcap_missing():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(
            connection,
            include_price=False,
            include_mcap=False,
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MISSING_CURRENT_PRICE
        assert decision.data_status == DataStatus.MISSING
        assert "missing_current_price" in decision.missing_reasons


# ---------------------------------------------------------------------------
# 7. mcap missing but price present -> price fallback
# ---------------------------------------------------------------------------


def test_mcap_missing_uses_price_fallback():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(
            connection,
            drawdown=0.60,
            include_mcap=False,
            current_mcap_override=None,
            migration_mcap_override=None,
            ath_mcap_override=None,
        )
        # Force mcaps None on token + observation + ath_state + ath_events.
        # The engine reads ATH via ath_events (Stage 7.1), so the underlying
        # ATH_RAISED event must be kept consistent with ath_state.
        connection.execute(
            "UPDATE token_sequence_state SET migration_mcap = NULL, current_mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.execute(
            "UPDATE price_observations SET mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.execute(
            "UPDATE ath_state SET ath_mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.execute(
            "UPDATE ath_events SET new_ath_mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.commit()

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 1
        assert decision.key_feature_snapshot["pump_multiple_basis"] == "price"
        assert decision.key_feature_snapshot["drawdown_basis"] == "price"


# ---------------------------------------------------------------------------
# 8. Migration price/mcap missing
# ---------------------------------------------------------------------------


def test_migration_price_and_mcap_missing():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, migration_present=False)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MISSING_MIGRATION_PRICE
        assert decision.data_status == DataStatus.MISSING
        assert "missing_migration_price" in decision.missing_reasons


# ---------------------------------------------------------------------------
# 9-11. ATH missing / data_limited / low confidence
# ---------------------------------------------------------------------------


def test_ath_state_missing():
    with _engine_context() as (connection, engine):
        # Set up token + observation but no ATH state.
        TokenSequenceRepository(connection).upsert(
            TokenState(
                token_address=TOKEN,
                migration_time=MIG_TIME,
                migration_price=10.0,
                migration_mcap=10000.0,
                current_price=40.0,
                current_mcap=40000.0,
                data_status=DataStatus.OK,
            )
        )
        PriceObservationRepository(connection).insert(
            PriceObservation(
                token_address=TOKEN,
                observed_at=EVAL_TIME - timedelta(seconds=60),
                source="test",
                price=40.0,
                mcap=40000.0,
                data_status=DataStatus.OK,
            )
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MISSING_ATH
        assert decision.data_status == DataStatus.MISSING
        assert "missing_ath" in decision.missing_reasons


def test_ath_status_data_limited():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, ath_status=ATHStatus.DATA_LIMITED)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.ATH_DATA_LIMITED
        assert decision.data_status == DataStatus.MISSING
        assert "ath_data_limited" in decision.missing_reasons


def test_ath_confidence_low_proceeds_partial():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, ath_confidence=ATHConfidence.LOW)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 1
        assert decision.data_status == DataStatus.PARTIAL
        assert "ath_confidence_too_low" in decision.missing_reasons


# ---------------------------------------------------------------------------
# 12-13. Price age boundary
# ---------------------------------------------------------------------------


def test_price_age_300_is_fresh():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, observation_age_seconds=300.0)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.price_age_seconds == pytest.approx(300.0)


def test_price_age_301_is_stale():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, observation_age_seconds=301.0)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.PRICE_STALE
        assert decision.data_status == DataStatus.PARTIAL
        assert "price_stale" in decision.missing_reasons


# ---------------------------------------------------------------------------
# 14-16. Pump / drawdown availability
# ---------------------------------------------------------------------------


def test_pump_multiple_below_min():
    with _engine_context() as (connection, engine):
        # drawdown = 0.88 (T3 territory), pump = 1.20 (below 1.30)
        _insert_eligible_state(connection, drawdown=0.88, pump=1.20)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MIN_PUMP_NOT_MET
        assert decision.pump_multiple == pytest.approx(1.20)
        assert decision.data_status == DataStatus.OK


def test_pump_multiple_missing_due_to_mismatched_basis():
    """cur_price valid but cur_mcap missing; mig_price missing but mig_mcap valid.
    No common basis so pump cannot be computed, but drawdown can (price basis)."""

    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)
        # Wipe cur_mcap and mig_price to break both calculation bases for pump.
        connection.execute(
            "UPDATE token_sequence_state SET migration_price = NULL, current_mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.execute(
            "UPDATE price_observations SET mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.commit()

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MISSING_PUMP_MULTIPLE
        assert decision.pump_multiple is None
        assert decision.drawdown_from_ath == pytest.approx(0.60)
        assert "missing_pump_multiple" in decision.missing_reasons


def test_drawdown_missing():
    """Pump valid but ATH price/mcap both None -> drawdown cannot be computed."""

    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)
        # Wipe ATH numerics. Status stays CONFIRMED so engine doesn't short-circuit
        # at step 6. The engine reads ATH via ath_events (Stage 7.1), so the
        # underlying ATH_RAISED event must be wiped alongside ath_state.
        connection.execute(
            "UPDATE ath_state SET ath_price = NULL, ath_mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.execute(
            "UPDATE ath_events SET new_ath_price = NULL, new_ath_mcap = NULL WHERE token_address = ?",
            (TOKEN,),
        )
        connection.commit()

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.MISSING_DRAWDOWN
        assert decision.drawdown_from_ath is None
        assert "missing_drawdown" in decision.missing_reasons


# ---------------------------------------------------------------------------
# 17-18. Drawdown out of policy range
# ---------------------------------------------------------------------------


def test_drawdown_below_first_tier():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.50)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.DRAWDOWN_BELOW_FIRST_TIER
        assert decision.drawdown_from_ath == pytest.approx(0.50)


def test_drawdown_beyond_max_tier():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.95)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.DRAWDOWN_BEYOND_MAX_TIER
        assert decision.drawdown_from_ath == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# 19-21. Duplicate-tier and tier-progression
# ---------------------------------------------------------------------------


def _insert_prior_would_alert(
    connection: PHX2Connection,
    *,
    tier_index: int,
    tier_name: str,
    evaluated_at: datetime,
) -> int:
    return AlertDecisionRepository(connection).insert(
        AlertDecision(
            token_address=TOKEN,
            evaluated_at=evaluated_at,
            decision_type=DecisionType.WOULD_ALERT,
            tier_index=tier_index,
            tier_name=tier_name,
            primary_reason=DecisionReason.WOULD_ALERT,
            reasons=[DecisionReason.WOULD_ALERT],
            would_alert=True,
            blocked=False,
            skipped=False,
            policy_version="prior_test",
            data_status=DataStatus.OK,
        )
    )


def test_duplicate_tier_skip():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.70)
        _insert_prior_would_alert(
            connection,
            tier_index=2,
            tier_name="T2",
            evaluated_at=EVAL_TIME - timedelta(minutes=5),
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.DUPLICATE_TIER
        # Prior tier match is recorded in tier_context for transparency.
        assert decision.tier_context["matched_tier"] == "T2"
        assert decision.tier_index == 2


def test_prior_higher_tier_skips_lower_or_equal():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)  # T1
        _insert_prior_would_alert(
            connection,
            tier_index=3,
            tier_name="T3",
            evaluated_at=EVAL_TIME - timedelta(minutes=5),
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert (
            decision.primary_reason
            == DecisionReason.LOWER_OR_EQUAL_TIER_ALREADY_ALERTED
        )
        assert decision.tier_index == 1


def test_prior_lower_tier_allows_upward():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.70)  # T2
        _insert_prior_would_alert(
            connection,
            tier_index=1,
            tier_name="T1",
            evaluated_at=EVAL_TIME - timedelta(minutes=5),
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 2
        assert decision.primary_reason == DecisionReason.WOULD_ALERT


# ---------------------------------------------------------------------------
# 22. Policy disabled
# ---------------------------------------------------------------------------


def test_policy_disabled_blocks():
    disabled_policy = replace(DEFAULT_ALERT_POLICY, enabled=False)
    with _engine_context(policy=disabled_policy) as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.BLOCK
        assert decision.primary_reason == DecisionReason.POLICY_DISABLED
        assert decision.blocked is True
        assert decision.would_alert is False


# ---------------------------------------------------------------------------
# 23-24. Field/clock features missing -> partial, not skip
# ---------------------------------------------------------------------------


def test_field_features_missing_marks_partial():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60, include_field=False)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.field_features_id is None
        assert decision.data_status == DataStatus.PARTIAL
        assert "field_features_missing" in decision.missing_reasons


def test_clock_features_missing_marks_partial():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60, include_clock=False)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.clock_features_id is None
        assert decision.data_status == DataStatus.PARTIAL
        assert "clock_features_missing" in decision.missing_reasons


# ---------------------------------------------------------------------------
# 25. Exact as_of_time match in feature row is not future leakage
# ---------------------------------------------------------------------------


def test_exact_as_of_time_match_is_used():
    with _engine_context() as (connection, engine):
        # Insert eligible state but skip the helper field/clock so we can
        # control timing precisely.
        _insert_eligible_state(
            connection,
            drawdown=0.60,
            include_field=False,
            include_clock=False,
        )

        field_repo = FieldFeatureRepository(connection)
        early_id = field_repo.upsert(
            FieldFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME - timedelta(seconds=10),
                feature_version="v_pre",
                data_status=DataStatus.OK,
            )
        )
        exact_id = field_repo.upsert(
            FieldFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME,
                feature_version="v_exact",
                data_status=DataStatus.OK,
            )
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        # Exact-time match is the latest at-or-before, so its id wins.
        assert decision.field_features_id == exact_id
        assert decision.field_features_id != early_id


# ---------------------------------------------------------------------------
# 26. No future-row leakage
# ---------------------------------------------------------------------------


def test_no_future_row_leakage_for_field_and_clock():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(
            connection,
            drawdown=0.60,
            include_field=False,
            include_clock=False,
        )

        field_repo = FieldFeatureRepository(connection)
        early_field_id = field_repo.upsert(
            FieldFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME - timedelta(seconds=10),
                feature_version="v_pre",
                data_status=DataStatus.OK,
            )
        )
        exact_field_id = field_repo.upsert(
            FieldFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME,
                feature_version="v_exact",
                data_status=DataStatus.OK,
            )
        )
        future_field_id = field_repo.upsert(
            FieldFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME + timedelta(seconds=10),
                feature_version="v_future",
                data_status=DataStatus.OK,
            )
        )

        clock_repo = ClockFeatureRepository(connection)
        early_clock_id = clock_repo.upsert(
            ClockFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME - timedelta(seconds=10),
                feature_version="c_pre",
                data_status=DataStatus.OK,
            )
        )
        exact_clock_id = clock_repo.upsert(
            ClockFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME,
                feature_version="c_exact",
                data_status=DataStatus.OK,
            )
        )
        future_clock_id = clock_repo.upsert(
            ClockFeatures(
                token_address=TOKEN,
                as_of_time=EVAL_TIME + timedelta(seconds=10),
                feature_version="c_future",
                data_status=DataStatus.OK,
            )
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.field_features_id == exact_field_id
        assert decision.field_features_id != future_field_id
        assert decision.field_features_id != early_field_id
        assert decision.clock_features_id == exact_clock_id
        assert decision.clock_features_id != future_clock_id
        assert decision.clock_features_id != early_clock_id


# ---------------------------------------------------------------------------
# 26b. No future-row leakage for price observations (Stage 7.1)
# ---------------------------------------------------------------------------


def test_no_future_row_leakage_for_price_observation():
    with _engine_context() as (connection, engine):
        # Helper inserts an eligible state plus one observation at
        # EVAL_TIME - 60s. Skip field/clock so we keep this test focused on
        # price observations.
        _insert_eligible_state(
            connection,
            drawdown=0.60,
            include_field=False,
            include_clock=False,
        )

        price_repo = PriceObservationRepository(connection)
        # Reuse the eligibility-friendly price/mcap so the engine still
        # passes earlier checks regardless of which observation it picks.
        cur_price = 40.0
        cur_mcap = 40000.0
        early_id = price_repo.insert(
            PriceObservation(
                token_address=TOKEN,
                observed_at=EVAL_TIME - timedelta(seconds=10),
                source="test",
                price=cur_price,
                mcap=cur_mcap,
                data_status=DataStatus.OK,
            )
        )
        exact_id = price_repo.insert(
            PriceObservation(
                token_address=TOKEN,
                observed_at=EVAL_TIME,
                source="test",
                price=cur_price,
                mcap=cur_mcap,
                data_status=DataStatus.OK,
            )
        )
        future_id = price_repo.insert(
            PriceObservation(
                token_address=TOKEN,
                observed_at=EVAL_TIME + timedelta(seconds=10),
                source="test",
                price=cur_price,
                mcap=cur_mcap,
                data_status=DataStatus.OK,
            )
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        # PriceObservationRepository.get_latest_at_or_before orders by
        # observed_at DESC, id DESC, so the exact-time match wins over the
        # earlier helper observation, and the future row is excluded.
        assert decision.price_observation_id == exact_id
        assert decision.price_observation_id != future_id
        assert decision.price_observation_id != early_id


# ---------------------------------------------------------------------------
# 26c. Future WOULD_ALERTs do not leak into historical duplicate-tier checks
#      (Stage 7.1 — HIGH fix)
# ---------------------------------------------------------------------------


def _insert_future_would_alert(
    connection: PHX2Connection,
    *,
    tier_index: int,
    tier_name: str,
    evaluated_at: datetime,
) -> int:
    return AlertDecisionRepository(connection).insert(
        AlertDecision(
            token_address=TOKEN,
            evaluated_at=evaluated_at,
            decision_type=DecisionType.WOULD_ALERT,
            tier_index=tier_index,
            tier_name=tier_name,
            primary_reason=DecisionReason.WOULD_ALERT,
            reasons=[DecisionReason.WOULD_ALERT],
            would_alert=True,
            blocked=False,
            skipped=False,
            policy_version="future_test",
            data_status=DataStatus.OK,
        )
    )


def test_future_would_alert_does_not_block_historical_evaluation():
    with _engine_context() as (connection, engine):
        # T2-eligible token at EVAL_TIME.
        _insert_eligible_state(connection, drawdown=0.70)

        # A WOULD_ALERT row at the same tier evaluated AFTER EVAL_TIME must
        # not influence the historical evaluation.
        _insert_future_would_alert(
            connection,
            tier_index=2,
            tier_name="T2",
            evaluated_at=EVAL_TIME + timedelta(seconds=100),
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 2
        assert decision.primary_reason == DecisionReason.WOULD_ALERT
        assert decision.primary_reason != DecisionReason.DUPLICATE_TIER
        assert (
            decision.primary_reason
            != DecisionReason.LOWER_OR_EQUAL_TIER_ALREADY_ALERTED
        )


def test_future_higher_tier_would_alert_does_not_block_historical_lower_tier_evaluation():
    with _engine_context() as (connection, engine):
        # T1-eligible token at EVAL_TIME.
        _insert_eligible_state(connection, drawdown=0.60)

        # A higher-tier WOULD_ALERT evaluated AFTER EVAL_TIME must not block
        # the historical lower-tier eligibility.
        _insert_future_would_alert(
            connection,
            tier_index=3,
            tier_name="T3",
            evaluated_at=EVAL_TIME + timedelta(seconds=100),
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 1
        assert decision.primary_reason == DecisionReason.WOULD_ALERT
        assert (
            decision.primary_reason
            != DecisionReason.LOWER_OR_EQUAL_TIER_ALREADY_ALERTED
        )


def test_exact_boundary_would_alert_at_evaluated_at_blocks_duplicate():
    with _engine_context() as (connection, engine):
        # T2-eligible token at EVAL_TIME.
        _insert_eligible_state(connection, drawdown=0.70)

        # Prior WOULD_ALERT at exactly evaluated_at == EVAL_TIME must still be
        # visible — proves the <= filter is inclusive on the boundary.
        _insert_future_would_alert(
            connection,
            tier_index=2,
            tier_name="T2",
            evaluated_at=EVAL_TIME,
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.SKIP
        assert decision.primary_reason == DecisionReason.DUPLICATE_TIER


# ---------------------------------------------------------------------------
# 26d. Future ATH raises do not leak into historical drawdown
#      (Stage 7.1 — MEDIUM fix)
# ---------------------------------------------------------------------------


def _overwrite_ath_state_and_event_to_future_raise(
    connection: PHX2Connection,
    *,
    event_time: datetime,
    new_ath_price: float,
    new_ath_mcap: float,
) -> int:
    """Insert a future ATH_RAISED event AND overwrite ath_state to it.

    Simulates the live database's "current state has moved past as_of_time"
    condition during a historical replay.
    """

    ath_repo = ATHRepository(connection)
    event_id = ath_repo.insert_event(
        ATHEvent(
            token_address=TOKEN,
            event_time=event_time,
            candidate_price=new_ath_price,
            candidate_mcap=new_ath_mcap,
            candidate_source="test",
            prior_ath_price=100.0,
            prior_ath_mcap=100000.0,
            new_ath_price=new_ath_price,
            new_ath_mcap=new_ath_mcap,
            status_before=ATHStatus.CONFIRMED,
            status_after=ATHStatus.CONFIRMED,
            confidence_before=ATHConfidence.HIGH,
            confidence_after=ATHConfidence.HIGH,
            mutation_type=ATHEventType.ATH_RAISED,
            accepted=True,
            data_status=DataStatus.OK,
        )
    )
    ath_repo.upsert_state(
        ATHState(
            token_address=TOKEN,
            ath_price=new_ath_price,
            ath_mcap=new_ath_mcap,
            ath_time=event_time,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            ath_source="test",
            last_event_id=event_id,
            data_status=DataStatus.OK,
        )
    )
    return event_id


def test_future_ath_raise_does_not_affect_historical_drawdown():
    with _engine_context() as (connection, engine):
        # Helper inserts the historical ATH event at ATH_TIME (= EVAL_TIME
        # - 50min) with ath_price=100, ath_mcap=100000, current price/mcap
        # 40/40000 → drawdown 0.60 (T1).
        _, historical_ath_event_id, _, _ = _insert_eligible_state(
            connection, drawdown=0.60
        )

        # A FUTURE ATH raise at EVAL_TIME + 100s pushes ATH to 200/200000.
        # If the engine read this future state, drawdown would jump to
        # 1 - 40/200 = 0.80 (T2) and the test would catch it.
        future_ath_event_id = _overwrite_ath_state_and_event_to_future_raise(
            connection,
            event_time=EVAL_TIME + timedelta(seconds=100),
            new_ath_price=200.0,
            new_ath_mcap=200000.0,
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.tier_index == 1
        assert decision.tier_name == "T1"
        assert decision.drawdown_from_ath == pytest.approx(0.60)
        # Historical ATH event used, not the future raise.
        assert decision.ath_event_id == historical_ath_event_id
        assert decision.ath_event_id != future_ath_event_id
        assert decision.ath_price == pytest.approx(100.0)


def test_exact_boundary_ath_event_at_evaluated_at_is_visible():
    with _engine_context() as (connection, engine):
        # Helper inserts the historical ATH event at ATH_TIME (= EVAL_TIME -
        # 50min). Add another ATH_RAISED at exactly EVAL_TIME with a higher
        # ATH so we can detect which event the engine picks.
        _, prior_ath_event_id, _, _ = _insert_eligible_state(
            connection, drawdown=0.60
        )

        boundary_ath_event_id = _overwrite_ath_state_and_event_to_future_raise(
            connection,
            event_time=EVAL_TIME,
            new_ath_price=125.0,
            new_ath_mcap=125000.0,
        )

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        # The boundary event at event_time == EVAL_TIME wins on the latest
        # ordering (event_time DESC, id DESC), proving the <= filter is
        # inclusive. drawdown = 1 - 40/125 = 0.68 → T2.
        assert decision.ath_event_id == boundary_ath_event_id
        assert decision.ath_event_id != prior_ath_event_id
        assert decision.drawdown_from_ath == pytest.approx(1.0 - 40.0 / 125.0)
        assert decision.ath_price == pytest.approx(125.0)


# ---------------------------------------------------------------------------
# 27. Deterministic replay across two databases
# ---------------------------------------------------------------------------


def test_deterministic_replay_across_databases():
    decisions = []
    for _ in range(2):
        with _engine_context() as (connection, engine):
            _insert_eligible_state(connection, drawdown=0.70)
            decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
            decisions.append(decision)

    a, b = decisions
    assert a.decision_type == b.decision_type
    assert a.tier_index == b.tier_index
    assert a.tier_name == b.tier_name
    assert a.primary_reason == b.primary_reason
    assert set(a.reasons) == set(b.reasons)
    assert a.pump_multiple == pytest.approx(b.pump_multiple)
    assert a.drawdown_from_ath == pytest.approx(b.drawdown_from_ath)
    assert a.price_age_seconds == pytest.approx(b.price_age_seconds)
    assert a.policy_version == b.policy_version
    assert a.data_status == b.data_status
    assert a.evaluated_at == b.evaluated_at


# ---------------------------------------------------------------------------
# 28. Engine writes only alert_decisions
# ---------------------------------------------------------------------------


_OBSERVED_TABLES = (
    "token_sequence_state",
    "price_observations",
    "ath_state",
    "ath_events",
    "field_features",
    "clock_features",
    "score_features",
    "filter_evaluations",
    "dispatch_events",
    "outcome_windows",
    "price_curve_points",
    "fee_windows",
    "raw_pumpswap_events",
    "migration_events",
)


def test_evaluate_only_writes_alert_decisions_table():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)
        before = {t: _count(connection, t) for t in _OBSERVED_TABLES}
        before_alerts = _count(connection, "alert_decisions")

        engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        after = {t: _count(connection, t) for t in _OBSERVED_TABLES}
        after_alerts = _count(connection, "alert_decisions")

    for t in _OBSERVED_TABLES:
        assert before[t] == after[t], f"{t} changed: {before[t]} -> {after[t]}"
    assert after_alerts == before_alerts + 1


# ---------------------------------------------------------------------------
# 29. Engine does not open a connection-level transaction
# ---------------------------------------------------------------------------


def test_engine_does_not_open_a_transaction():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)

        assert connection.in_transaction is False
        engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert connection.in_transaction is False


# ---------------------------------------------------------------------------
# 30. Engine makes no network calls
# ---------------------------------------------------------------------------


def test_engine_makes_no_network_calls(monkeypatch):
    def _no_socket(*args, **kwargs):  # pragma: no cover - guard
        raise AssertionError("AlertEligibilityEngine attempted to open a socket")

    monkeypatch.setattr(socket, "socket", _no_socket)

    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

    assert decision.decision_type == DecisionType.WOULD_ALERT


# ---------------------------------------------------------------------------
# 31. Exception path writes ERROR audit row and re-raises
# ---------------------------------------------------------------------------


class _BoomError(RuntimeError):
    """Synthetic error injected via monkeypatch to test the exception path."""


def test_exception_during_evaluation_records_error_audit_and_reraises():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection, drawdown=0.60)

        original = engine.field_features.get_latest_at_or_before

        def _boom(*args, **kwargs):
            raise _BoomError("synthetic field-feature failure")

        engine.field_features.get_latest_at_or_before = _boom  # type: ignore[assignment]

        try:
            with pytest.raises(_BoomError):
                engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

            error_rows = AlertDecisionRepository(connection).list_by_token(TOKEN)
            assert len(error_rows) == 1
            audit = error_rows[0]
            assert audit.decision_type == DecisionType.ERROR
            assert audit.primary_reason == DecisionReason.ERROR
            assert audit.data_status == DataStatus.ERROR
            joined = " ".join(audit.missing_reasons)
            assert "_BoomError" in joined
            assert "synthetic field-feature failure" in joined
            snapshot = audit.key_feature_snapshot
            assert snapshot.get("exception_type") == "_BoomError"
            assert "synthetic field-feature failure" in snapshot.get(
                "exception_message", ""
            )
        finally:
            engine.field_features.get_latest_at_or_before = original  # type: ignore[assignment]
