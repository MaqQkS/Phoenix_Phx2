"""Tests for PHX2 typed models."""

from datetime import datetime, timezone

import pytest

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
    DispatchEvent,
    DispatchMode,
    FeeWindow,
    FieldFeatures,
    FilterResult,
    MigrationEvent,
    OutcomeWindow,
    PriceCurvePoint,
    PriceObservation,
    RawPumpSwapEvent,
    ScoreFeatures,
    TokenState,
)


def test_every_model_instantiates_with_minimal_required_fields():
    now = datetime(2026, 5, 8, 1, 30, tzinfo=timezone.utc)
    models = [
        TokenState(token_address="token"),
        MigrationEvent(token_address="token"),
        PriceObservation(token_address="token"),
        ATHState(token_address="token"),
        ATHEvent(token_address="token"),
        AlertDecision(token_address="token"),
        DispatchEvent(token_address="token"),
        FeeWindow(token_address="token"),
        RawPumpSwapEvent(
            observed_at=now,
            source="grpc",
            signature="sig",
            dedupe_key="sig:0",
            event_type="buy",
        ),
        PriceCurvePoint(
            token_address="token",
            anchor_type="migration",
            anchor_key="migration:token",
            anchor_time=now,
            bucket_seconds=60,
            bucket_start_time=now,
            bucket_end_time=now,
        ),
        FilterResult(token_address="token", filter_name="fee_gate"),
        FieldFeatures(token_address="token"),
        ScoreFeatures(token_address="token"),
        ClockFeatures(token_address="token"),
        OutcomeWindow(window_seconds=300),
    ]

    assert all(model is not None for model in models)


def test_every_model_serializes_to_json_safe_dict():
    now = datetime(2026, 5, 8, 1, 30, tzinfo=timezone.utc)
    models = [
        TokenState(token_address="token", migration_time=now),
        MigrationEvent(token_address="token", migration_time=now),
        PriceObservation(token_address="token", observed_at=now),
        ATHState(token_address="token", ath_status=ATHStatus.CONFIRMED),
        ATHEvent(token_address="token", event_time=now),
        AlertDecision(
            token_address="token",
            evaluated_at=now,
            decision_type=DecisionType.SKIP,
            primary_reason=DecisionReason.PRICE_STALE,
        ),
        DispatchEvent(token_address="token", created_at=now),
        FeeWindow(token_address="token", as_of_time=now),
        RawPumpSwapEvent(
            observed_at=now,
            source="grpc",
            signature="sig",
            dedupe_key="sig:0",
            event_type="buy",
            raw_payload={"nested": {"ok": True}},
        ),
        PriceCurvePoint(
            token_address="token",
            anchor_type="migration",
            anchor_key="migration:1",
            anchor_time=now,
            anchor_ref_id=1,
            bucket_seconds=60,
            bucket_start_time=now,
            bucket_end_time=now,
            normalized_price=1.0,
            return_from_anchor=0.0,
        ),
        FilterResult(token_address="token", filter_name="fee_gate", as_of_time=now),
        FieldFeatures(token_address="token", as_of_time=now),
        ScoreFeatures(token_address="token", as_of_time=now),
        ClockFeatures(token_address="token", as_of_time=now),
        OutcomeWindow(window_seconds=300, window_start_time=now),
    ]

    for model in models:
        payload = model.to_dict()
        assert isinstance(payload, dict)

    assert models[0].to_dict()["migration_time"] == now.isoformat()
    assert models[3].to_dict()["ath_status"] == "confirmed"
    assert models[5].to_dict()["decision_type"] == "skip"
    assert models[5].to_dict()["primary_reason"] == "price_stale"
    assert models[9].to_dict()["anchor_type"] == "migration"
    assert models[9].to_dict()["anchor_key"] == "migration:1"


def test_missing_reasons_default_to_empty_lists():
    now = datetime(2026, 5, 8, 1, 30, tzinfo=timezone.utc)
    models = [
        TokenState(token_address="token"),
        MigrationEvent(token_address="token"),
        PriceObservation(token_address="token"),
        ATHState(token_address="token"),
        DispatchEvent(token_address="token"),
        FeeWindow(token_address="token"),
        RawPumpSwapEvent(
            observed_at=now,
            source="grpc",
            signature="sig",
            dedupe_key="sig:0",
            event_type="buy",
        ),
        PriceCurvePoint(
            token_address="token",
            anchor_type="migration",
            anchor_key="migration:token",
            anchor_time=now,
            bucket_seconds=60,
            bucket_start_time=now,
            bucket_end_time=now,
        ),
        FilterResult(token_address="token", filter_name="fee_gate"),
        FieldFeatures(token_address="token"),
        ScoreFeatures(token_address="token"),
        ClockFeatures(token_address="token"),
        OutcomeWindow(window_seconds=300),
    ]

    for model in models:
        assert model.missing_reasons == []


def test_price_curve_point_requires_and_serializes_anchor_key():
    now = datetime(2026, 5, 8, 1, 30, tzinfo=timezone.utc)

    with pytest.raises(TypeError):
        PriceCurvePoint(
            token_address="token",
            anchor_type="migration",
            anchor_time=now,
            bucket_seconds=60,
            bucket_start_time=now,
            bucket_end_time=now,
        )

    with pytest.raises(ValueError):
        PriceCurvePoint(
            token_address="token",
            anchor_type="migration",
            anchor_key="",
            anchor_time=now,
            bucket_seconds=60,
            bucket_start_time=now,
            bucket_end_time=now,
        )

    point = PriceCurvePoint(
        token_address="token",
        anchor_type="migration",
        anchor_key="migration:token",
        anchor_time=now,
        bucket_seconds=60,
        bucket_start_time=now,
        bucket_end_time=now,
    )

    assert point.to_dict()["anchor_key"] == "migration:token"


def test_required_enum_values_match_stage3_contract():
    assert [status.value for status in DataStatus] == [
        "ok",
        "partial",
        "missing",
        "no_events",
        "data_limited",
        "source_unavailable",
        "error",
    ]
    assert [status.value for status in ATHStatus] == [
        "unknown",
        "provisional",
        "seeded",
        "reseeded",
        "confirmed",
        "data_limited",
        "stale",
        "invalid",
    ]
    assert [confidence.value for confidence in ATHConfidence] == [
        "unknown",
        "low",
        "medium",
        "high",
        "final",
    ]
    assert [event_type.value for event_type in ATHEventType] == [
        "ath_raised",
        "ath_no_change",
        "ath_confidence_changed",
        "ath_rejected_lower",
        "ath_rejected_invalid",
        "ath_data_limited",
        "ath_source_conflict",
        "ath_correction",
    ]
    assert [decision_type.value for decision_type in DecisionType] == [
        "would_alert",
        "skip",
        "block",
        "error",
    ]
    assert [reason.value for reason in DecisionReason] == [
        "would_alert",
        "price_stale",
        "ath_unknown",
        "ath_data_limited",
        "ath_confidence_too_low",
        "min_pump_not_met",
        "tier_gap",
        "duplicate_tier",
        "filter_blocked",
        "drawdown_below_first_tier",
        "drawdown_beyond_max_tier",
        "missing_migration_price",
        "missing_current_price",
        "token_not_active",
        "token_not_found",
        "missing_price_observation",
        "missing_ath",
        "missing_pump_multiple",
        "missing_drawdown",
        "lower_or_equal_tier_already_alerted",
        "invalid_current_price",
        "invalid_migration_price",
        "policy_disabled",
        "cooldown_active",
        "error",
    ]
    assert [mode.value for mode in DispatchMode] == [
        "disabled",
        "file_preview",
        "console",
        "telegram_private",
        "discord_private",
        "telegram_live",
        "discord_live",
        "multi",
    ]


def test_alert_decision_constructs_with_audit_field_defaults():
    decision = AlertDecision(token_address="token")

    assert decision.price_observation_id is None
    assert decision.ath_event_id is None
    assert decision.data_status == DataStatus.MISSING
    assert decision.missing_reasons == []


def test_alert_decision_constructs_with_audit_fields_set():
    decision = AlertDecision(
        token_address="token",
        price_observation_id=10,
        ath_event_id=20,
        data_status=DataStatus.OK,
        missing_reasons=["price_missing"],
    )

    assert decision.price_observation_id == 10
    assert decision.ath_event_id == 20
    assert decision.data_status == DataStatus.OK
    assert decision.missing_reasons == ["price_missing"]
