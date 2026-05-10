"""Tests for AlertRenderer purity and decision-type coverage."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from PHX2.models.enums import (
    ATHConfidence,
    ATHStatus,
    DataStatus,
    DecisionReason,
    DecisionType,
)
from PHX2.renderers.alert_renderer import AlertRenderer
from PHX2.renderers.rendered_alert import DRY_RUN_BANNER, RenderedAlert, Severity

from PHX2.tests.renderers._fixtures import (
    EVAL_TIME,
    make_alert_decision,
    make_ath_event,
    make_ath_state,
    make_clock_features,
    make_field_features,
    make_full_context,
    make_price_observation,
    make_token_state,
)


# ---- Clean WOULD_ALERT for each tier ------------------------------------


@pytest.mark.parametrize(
    "tier_index,tier_name",
    [(1, "T1"), (2, "T2"), (3, "T3")],
)
def test_clean_would_alert_renders_with_correct_tier(tier_index, tier_name):
    decision = make_alert_decision(tier_index=tier_index, tier_name=tier_name)
    context = make_full_context(decision=decision)

    rendered = AlertRenderer().render(context)

    assert isinstance(rendered, RenderedAlert)
    assert rendered.severity == Severity.CLEAN
    assert rendered.tier_label == tier_name
    assert rendered.headline == f"WOULD_ALERT — {tier_name}"
    assert rendered.banner == DRY_RUN_BANNER
    assert rendered.decision_type == "would_alert"


def test_clean_would_alert_market_section_populated():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.market_section["current_mc"] == "$847K"
    assert rendered.market_section["migration_mc"] == "$312K"
    assert rendered.market_section["ath_mc"] == "$2.84M"
    assert rendered.market_section["drawdown"] == "70.2%"
    assert rendered.market_section["pump_multiple"] == "2.71x"
    assert rendered.market_section["price_age"] == "2m 22s"
    assert rendered.market_section["calculation_basis"] == "mcap"


def test_clean_would_alert_ath_section_populated():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.ath_section["status"] == "confirmed"
    assert rendered.ath_section["confidence"] == "high"
    assert rendered.ath_section["source"] == "pumpswap_event"
    assert rendered.ath_section["ath_event_time"] == "2026-05-09T14:18:42Z"


def test_clean_would_alert_field_section_populated():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.field_section["liquidity_usd"] == "$125K"
    assert rendered.field_section["lp_floor_label"] == "ok"
    assert rendered.field_section["fee_gate_label"] == "open"


def test_clean_would_alert_clock_section_populated():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.clock_section["time_since_migration"] == "1h 32m"
    assert rendered.clock_section["time_since_ath"] == "14m 22s"
    assert "evaluated_at" not in rendered.clock_section


def test_clean_would_alert_token_section_populated():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.token_section["symbol"] == "BONKINU"
    assert rendered.token_section["address"].startswith("7xKp")
    assert rendered.token_section["address_short"] == "7xKp...0mLq"
    assert rendered.token_section["tier"] == "T2"
    assert rendered.token_section["primary_reason"] == "would_alert"


def test_clean_would_alert_footer_populated():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.footer["policy_version"] == "alert_policy_v0_observe_only"
    assert rendered.footer["evaluated_at"] == "2026-05-09T14:33:04Z"


def test_clean_would_alert_no_missing_section_entries():
    rendered = AlertRenderer().render(make_full_context())
    assert rendered.missing_section == []


# ---- Partial-data WOULD_ALERT -------------------------------------------


def test_partial_data_would_alert_severity_and_headline():
    decision = make_alert_decision(
        data_status=DataStatus.PARTIAL,
        missing_reasons=["field_features_missing"],
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))
    assert rendered.severity == Severity.PARTIAL
    assert "[PARTIAL DATA]" in rendered.headline
    assert "field_features_missing" in rendered.missing_section


# ---- WOULD_ALERT with missing migration price ---------------------------


def test_would_alert_with_missing_migration_price_renders_unknown_pump_multiple():
    decision = make_alert_decision(
        pump_multiple=None,
        data_status=DataStatus.PARTIAL,
        missing_reasons=["missing_pump_multiple"],
    )
    token_state = make_token_state(migration_price=None, migration_mcap=None)
    context = make_full_context(decision=decision, token_state=token_state)

    rendered = AlertRenderer().render(context)

    assert rendered.market_section["pump_multiple"] == "unknown"
    assert rendered.market_section["migration_mc"] == "unknown"
    assert "pump_multiple" in rendered.missing_section
    assert "migration_mcap" in rendered.missing_section


# ---- WOULD_ALERT with missing ATH ---------------------------------------


def test_would_alert_with_ath_unknown_status_marks_section_unknown():
    decision = make_alert_decision(
        data_status=DataStatus.PARTIAL,
        missing_reasons=["ath_unknown"],
    )
    decision = replace(
        decision,
        ath_status=ATHStatus.UNKNOWN,
        ath_confidence=ATHConfidence.UNKNOWN,
        ath_source=None,
    )
    ath_state = make_ath_state(
        ath_status=ATHStatus.UNKNOWN,
        ath_confidence=ATHConfidence.UNKNOWN,
        ath_source=None,
        ath_time=None,
    )
    context = make_full_context(
        decision=decision,
        ath_state=ath_state,
        ath_event=None,
    )

    rendered = AlertRenderer().render(context)

    assert rendered.ath_section["status"] == "unknown"
    assert rendered.ath_section["confidence"] == "unknown"
    assert rendered.ath_section["source"] == "unknown"
    assert rendered.ath_section["ath_event_time"] == "unknown"
    assert "ath_status" in rendered.missing_section
    assert "ath_confidence" in rendered.missing_section
    assert "ath_source" in rendered.missing_section
    assert "ath_event_time" in rendered.missing_section


# ---- SKIP / BLOCK / ERROR -----------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        DecisionReason.MIN_PUMP_NOT_MET,
        DecisionReason.PRICE_STALE,
        DecisionReason.TIER_GAP,
        DecisionReason.ATH_UNKNOWN,
        DecisionReason.MISSING_PRICE_OBSERVATION,
    ],
)
def test_skip_decisions_render_compactly_without_raising(reason):
    decision = make_alert_decision(
        decision_type=DecisionType.SKIP,
        primary_reason=reason,
        tier_index=None,
        tier_name=None,
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))

    assert rendered.severity == Severity.INFO
    assert rendered.market_section == {}
    assert rendered.ath_section == {}
    assert rendered.field_section == {}
    assert rendered.clock_section == {}
    assert rendered.headline.startswith("SKIP — ")
    assert reason.value in rendered.headline
    assert rendered.footer["evaluated_at"] == "2026-05-09T14:33:04Z"


def test_block_decision_renders_compactly():
    decision = make_alert_decision(
        decision_type=DecisionType.BLOCK,
        primary_reason=DecisionReason.POLICY_DISABLED,
        tier_index=None,
        tier_name=None,
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))

    assert rendered.severity == Severity.INFO
    assert rendered.market_section == {}
    assert rendered.headline == "BLOCK — policy_disabled"
    assert rendered.footer["evaluated_at"] == "2026-05-09T14:33:04Z"


def test_error_decision_renders_with_error_severity():
    decision = make_alert_decision(
        decision_type=DecisionType.ERROR,
        primary_reason=DecisionReason.ERROR,
        tier_index=None,
        tier_name=None,
        data_status=DataStatus.ERROR,
        missing_reasons=["error"],
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))

    assert rendered.severity == Severity.ERROR
    assert rendered.headline.startswith("ERROR — ")
    assert "error" in rendered.missing_section
    assert rendered.footer["evaluated_at"] == "2026-05-09T14:33:04Z"


# ---- Determinism --------------------------------------------------------


def test_render_is_deterministic_for_same_context():
    context = make_full_context()
    renderer = AlertRenderer()
    a = renderer.render(context)
    b = renderer.render(context)
    assert a == b


def test_render_missing_section_is_sorted():
    decision = make_alert_decision(
        pump_multiple=None,
        drawdown_from_ath=None,
        data_status=DataStatus.PARTIAL,
        missing_reasons=["missing_pump_multiple", "missing_drawdown"],
    )
    context = make_full_context(decision=decision)
    rendered = AlertRenderer().render(context)
    assert rendered.missing_section == sorted(rendered.missing_section)


# ---- Purity: no clock reads ---------------------------------------------


def test_render_does_not_call_datetime_now(monkeypatch):
    """Render must not consult the wall clock."""

    import PHX2.renderers.alert_renderer as renderer_module

    sentinel_message = "AlertRenderer.render touched the wall clock"

    class _Forbidden:
        @classmethod
        def now(cls, tz=None):
            raise AssertionError(sentinel_message)

        @classmethod
        def utcnow(cls):
            raise AssertionError(sentinel_message)

    monkeypatch.setattr(renderer_module, "datetime", _Forbidden, raising=False)
    rendered = AlertRenderer().render(make_full_context())
    assert isinstance(rendered, RenderedAlert)


def test_render_does_not_use_environment(monkeypatch):
    """Render must not read environment variables."""

    import os

    captured = []
    original = os.environ.get

    def _spy(key, default=None):
        captured.append(key)
        return original(key, default)

    monkeypatch.setattr(os.environ, "get", _spy)
    AlertRenderer().render(make_full_context())
    assert captured == []


# ---- as_of_time wiring --------------------------------------------------


def test_render_uses_as_of_time_for_durations():
    """Token age tracks context.as_of_time, not real time."""

    # MIGRATION_TIME == EVAL_TIME - 1h32m == 2026-05-09T13:01:04Z.
    # later - MIGRATION_TIME == 2h58m56s -> "2h 58m".
    later = datetime(2026, 5, 9, 16, 0, 0, tzinfo=timezone.utc)
    context = make_full_context(as_of_time=later)
    rendered = AlertRenderer().render(context)
    assert rendered.clock_section["token_age"] == "2h 58m"
