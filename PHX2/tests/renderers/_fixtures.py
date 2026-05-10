"""Test fixtures for renderer tests.

Pure factory helpers — they construct AlertDecision / context objects with
sensible defaults that individual tests can override. No I/O.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from PHX2.models import (
    AlertDecision,
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    ClockFeatures,
    DataStatus,
    DecisionReason,
    DecisionType,
    FieldFeatures,
    PriceObservation,
    TokenSequenceState,
)
from PHX2.renderers.context import RenderingContext


TOKEN_ADDRESS = "7xKp9aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890mLq"
EVAL_TIME = datetime(2026, 5, 9, 14, 33, 4, tzinfo=timezone.utc)
MIGRATION_TIME = EVAL_TIME - timedelta(hours=1, minutes=32)
ATH_TIME = EVAL_TIME - timedelta(minutes=14, seconds=22)
TOKEN_AGE_TIME = EVAL_TIME - timedelta(hours=1, minutes=47)


def make_token_state(
    *,
    symbol: str = "BONKINU",
    migration_time: Optional[datetime] = MIGRATION_TIME,
    migration_price: Optional[float] = 0.000312,
    migration_mcap: Optional[float] = 312_000.0,
    current_price: Optional[float] = 0.000847,
    current_mcap: Optional[float] = 847_000.0,
) -> TokenSequenceState:
    return TokenSequenceState(
        token_address=TOKEN_ADDRESS,
        symbol=symbol,
        migration_time=migration_time,
        migration_price=migration_price,
        migration_mcap=migration_mcap,
        current_price=current_price,
        current_mcap=current_mcap,
        sequence_phase="post_ath",
        current_status="alive",
        data_status=DataStatus.OK,
    )


def make_price_observation(
    *,
    obs_id: int = 101,
    mcap: Optional[float] = 847_000.0,
    price: Optional[float] = 0.000847,
    observed_at: Optional[datetime] = None,
) -> PriceObservation:
    return PriceObservation(
        id=obs_id,
        token_address=TOKEN_ADDRESS,
        observed_at=observed_at or (EVAL_TIME - timedelta(seconds=142)),
        source="pumpswap_event",
        price=price,
        mcap=mcap,
        liquidity_usd=120_000.0,
        age_seconds=142.0,
        data_status=DataStatus.OK,
    )


def make_ath_state(
    *,
    ath_price: Optional[float] = 0.00284,
    ath_mcap: Optional[float] = 2_840_000.0,
    ath_time: Optional[datetime] = ATH_TIME,
    ath_status: ATHStatus = ATHStatus.CONFIRMED,
    ath_confidence: ATHConfidence = ATHConfidence.HIGH,
    ath_source: Optional[str] = "pumpswap_event",
    last_event_id: Optional[int] = 99,
) -> ATHState:
    return ATHState(
        token_address=TOKEN_ADDRESS,
        ath_price=ath_price,
        ath_mcap=ath_mcap,
        ath_time=ath_time,
        ath_status=ath_status,
        ath_confidence=ath_confidence,
        ath_source=ath_source,
        last_event_id=last_event_id,
        data_status=DataStatus.OK,
    )


def make_ath_event(
    *,
    event_id: int = 99,
    new_ath_mcap: Optional[float] = 2_840_000.0,
    new_ath_price: Optional[float] = 0.00284,
    event_time: Optional[datetime] = ATH_TIME,
) -> ATHEvent:
    return ATHEvent(
        id=event_id,
        token_address=TOKEN_ADDRESS,
        event_time=event_time,
        candidate_price=new_ath_price,
        candidate_mcap=new_ath_mcap,
        candidate_source="pumpswap_event",
        new_ath_price=new_ath_price,
        new_ath_mcap=new_ath_mcap,
        status_after=ATHStatus.CONFIRMED,
        confidence_after=ATHConfidence.HIGH,
        mutation_type=ATHEventType.ATH_RAISED,
        accepted=True,
        data_status=DataStatus.OK,
    )


def make_field_features(
    *,
    features_id: int = 33,
    liquidity_usd: Optional[float] = 125_000.0,
) -> FieldFeatures:
    return FieldFeatures(
        id=features_id,
        token_address=TOKEN_ADDRESS,
        as_of_time=EVAL_TIME,
        liquidity_usd=liquidity_usd,
        lp_floor_label="ok",
        fee_gate_label="open",
        ante_label_5m="elevated",
        ghost_label="alive",
        holder_label="diverse",
        creator_fee_share_5m=0.025,
        data_status=DataStatus.OK,
    )


def make_clock_features(
    *,
    features_id: int = 44,
    age_since_migration_s: Optional[float] = 5520.0,
    time_since_ath_s: Optional[float] = 862.0,
) -> ClockFeatures:
    return ClockFeatures(
        id=features_id,
        token_address=TOKEN_ADDRESS,
        as_of_time=EVAL_TIME,
        migration_time=MIGRATION_TIME,
        age_since_migration_s=age_since_migration_s,
        ath_time=ATH_TIME,
        time_since_ath_s=time_since_ath_s,
        sequence_phase="post_ath",
        data_status=DataStatus.OK,
    )


def make_alert_decision(
    *,
    decision_type: DecisionType = DecisionType.WOULD_ALERT,
    primary_reason: DecisionReason = DecisionReason.WOULD_ALERT,
    tier_index: Optional[int] = 2,
    tier_name: Optional[str] = "T2",
    pump_multiple: Optional[float] = 2.71,
    drawdown_from_ath: Optional[float] = 0.702,
    price_age_seconds: Optional[float] = 142.0,
    data_status: DataStatus = DataStatus.OK,
    missing_reasons: Optional[list] = None,
    price_observation_id: Optional[int] = 101,
    ath_event_id: Optional[int] = 99,
    field_features_id: Optional[int] = 33,
    clock_features_id: Optional[int] = 44,
    tier_context: Optional[Dict[str, Any]] = None,
    key_feature_snapshot: Optional[Dict[str, Any]] = None,
) -> AlertDecision:
    return AlertDecision(
        token_address=TOKEN_ADDRESS,
        evaluated_at=EVAL_TIME,
        decision_type=decision_type,
        tier_index=tier_index,
        tier_name=tier_name,
        primary_reason=primary_reason,
        reasons=[primary_reason],
        would_alert=decision_type == DecisionType.WOULD_ALERT,
        blocked=decision_type == DecisionType.BLOCK,
        skipped=decision_type == DecisionType.SKIP,
        price_observation_id=price_observation_id,
        ath_event_id=ath_event_id,
        field_features_id=field_features_id,
        clock_features_id=clock_features_id,
        ath_price=0.00284,
        ath_status=ATHStatus.CONFIRMED,
        ath_confidence=ATHConfidence.HIGH,
        ath_source="pumpswap_event",
        price_age_seconds=price_age_seconds,
        pump_multiple=pump_multiple,
        drawdown_from_ath=drawdown_from_ath,
        tier_context=tier_context if tier_context is not None else {"drawdown_basis": "mcap"},
        key_feature_snapshot=(
            key_feature_snapshot
            if key_feature_snapshot is not None
            else {"drawdown_basis": "mcap"}
        ),
        policy_version="alert_policy_v0_observe_only",
        data_status=data_status,
        missing_reasons=missing_reasons or [],
    )


_UNSET = object()


def make_full_context(
    *,
    decision: Optional[AlertDecision] = None,
    token_state: Any = _UNSET,
    price_observation: Any = _UNSET,
    ath_state: Any = _UNSET,
    ath_event: Any = _UNSET,
    field_features: Any = _UNSET,
    clock_features: Any = _UNSET,
    as_of_time: Optional[datetime] = None,
) -> RenderingContext:
    """Build a fully-populated context. Pass ``None`` to clear a slot."""

    return RenderingContext(
        alert_decision=decision if decision is not None else make_alert_decision(),
        as_of_time=as_of_time or EVAL_TIME,
        token_sequence_state=(
            make_token_state() if token_state is _UNSET else token_state
        ),
        price_observation=(
            make_price_observation()
            if price_observation is _UNSET
            else price_observation
        ),
        ath_event=make_ath_event() if ath_event is _UNSET else ath_event,
        ath_state=make_ath_state() if ath_state is _UNSET else ath_state,
        field_features=(
            make_field_features() if field_features is _UNSET else field_features
        ),
        clock_features=(
            make_clock_features() if clock_features is _UNSET else clock_features
        ),
    )
