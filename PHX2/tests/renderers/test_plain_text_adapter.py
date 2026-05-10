"""Tests for PlainTextAdapter."""

from dataclasses import replace

from PHX2.models.enums import DataStatus, DecisionReason, DecisionType
from PHX2.renderers.adapters.plain_text import PlainTextAdapter
from PHX2.renderers.alert_renderer import AlertRenderer
from PHX2.renderers.rendered_alert import DRY_RUN_BANNER

from PHX2.tests.renderers._fixtures import (
    make_alert_decision,
    make_full_context,
)


# ---- banner placement ---------------------------------------------------


def test_banner_appears_at_top_and_bottom():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)

    lines = output.splitlines()
    assert lines[0] == DRY_RUN_BANNER
    assert lines[-1] == DRY_RUN_BANNER


def test_banner_appears_exactly_twice():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)
    assert output.count(DRY_RUN_BANNER) == 2


# ---- WOULD_ALERT layout -------------------------------------------------


def test_would_alert_contains_all_section_headers():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)

    for header in ("Token:", "Market:", "ATH:", "Field:", "Clock:"):
        assert header in output, f"missing {header} in:\n{output}"


def test_would_alert_includes_market_values():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)

    assert "$847K" in output
    assert "$2.84M" in output
    assert "70.2%" in output
    assert "2.71x" in output


def test_would_alert_evaluated_at_renders_in_footer_not_clock_section():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)

    timestamp = "2026-05-09T14:33:04Z"
    assert timestamp in output

    clock_index = output.index("Clock:")
    next_blank = output.index("\n\n", clock_index)
    clock_block = output[clock_index:next_blank]
    assert timestamp not in clock_block

    footer_index = output.index("Evaluated at:")
    assert timestamp in output[footer_index:]


def test_would_alert_with_partial_data_includes_missing_section():
    decision = make_alert_decision(
        data_status=DataStatus.PARTIAL,
        missing_reasons=["field_features_missing"],
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))
    output = PlainTextAdapter().format(rendered)

    assert "Missing:" in output
    assert "field_features_missing" in output


def test_clean_would_alert_omits_missing_section():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)
    assert "Missing:" not in output


# ---- compact layout for SKIP / BLOCK / ERROR ----------------------------


def test_skip_omits_market_ath_field_clock_sections():
    decision = make_alert_decision(
        decision_type=DecisionType.SKIP,
        primary_reason=DecisionReason.MIN_PUMP_NOT_MET,
        tier_index=None,
        tier_name=None,
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))
    output = PlainTextAdapter().format(rendered)

    assert "Market:" not in output
    assert "ATH:" not in output
    assert "Field:" not in output
    assert "Clock:" not in output
    assert "Token:" in output  # token block still rendered
    assert "SKIP — min_pump_not_met" in output


def test_block_omits_full_sections():
    decision = make_alert_decision(
        decision_type=DecisionType.BLOCK,
        primary_reason=DecisionReason.POLICY_DISABLED,
        tier_index=None,
        tier_name=None,
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))
    output = PlainTextAdapter().format(rendered)

    assert "Market:" not in output
    assert "BLOCK — policy_disabled" in output


def test_error_omits_full_sections():
    decision = make_alert_decision(
        decision_type=DecisionType.ERROR,
        primary_reason=DecisionReason.ERROR,
        data_status=DataStatus.ERROR,
        missing_reasons=["error"],
        tier_index=None,
        tier_name=None,
    )
    rendered = AlertRenderer().render(make_full_context(decision=decision))
    output = PlainTextAdapter().format(rendered)

    assert "Market:" not in output
    assert "ERROR — " in output


def test_compact_decisions_render_evaluated_at_in_footer():
    """SKIP/BLOCK/ERROR strip the Clock section but must still surface the
    evaluated_at timestamp via the footer."""

    timestamp = "2026-05-09T14:33:04Z"
    cases = [
        (DecisionType.SKIP, DecisionReason.MIN_PUMP_NOT_MET, DataStatus.OK, []),
        (DecisionType.BLOCK, DecisionReason.POLICY_DISABLED, DataStatus.OK, []),
        (
            DecisionType.ERROR,
            DecisionReason.ERROR,
            DataStatus.ERROR,
            ["error"],
        ),
    ]
    for decision_type, reason, data_status, missing_reasons in cases:
        decision = make_alert_decision(
            decision_type=decision_type,
            primary_reason=reason,
            tier_index=None,
            tier_name=None,
            data_status=data_status,
            missing_reasons=missing_reasons,
        )
        rendered = AlertRenderer().render(make_full_context(decision=decision))
        output = PlainTextAdapter().format(rendered)

        assert "Clock:" not in output, f"{decision_type} should not have Clock section"
        assert timestamp in output, (
            f"{decision_type} output missing evaluated_at timestamp:\n{output}"
        )
        assert "Evaluated at:" in output, (
            f"{decision_type} output missing footer Evaluated at line:\n{output}"
        )


# ---- determinism --------------------------------------------------------


def test_format_is_deterministic_byte_identical():
    rendered = AlertRenderer().render(make_full_context())
    a = PlainTextAdapter().format(rendered)
    b = PlainTextAdapter().format(rendered)
    assert a == b


# ---- robustness ---------------------------------------------------------


def test_long_token_symbol_does_not_break_layout():
    from PHX2.tests.renderers._fixtures import make_token_state

    long_symbol = "A" * 80 + "🦊✨"
    token_state = make_token_state(symbol=long_symbol)
    context = make_full_context(token_state=token_state)
    rendered = AlertRenderer().render(context)
    output = PlainTextAdapter().format(rendered)

    assert long_symbol in output
    # Banner placement still intact.
    lines = output.splitlines()
    assert lines[0] == DRY_RUN_BANNER
    assert lines[-1] == DRY_RUN_BANNER


def test_unicode_dashes_in_banner_round_trip():
    rendered = AlertRenderer().render(make_full_context())
    output = PlainTextAdapter().format(rendered)
    assert "—" in output  # em dash in banner survives encoding.


# ---- regression: structural alert_decision_id surfaces in footer --------


def test_decision_id_renders_as_integer_not_unknown_when_present():
    """Regression: the prior implementation read decision_id from
    AlertDecision.key_feature_snapshot, a dict key the engine never set.
    Every preview rendered "Decision: unknown" until View B moved the field
    to RenderedAlert as a structural field.
    """

    base_rendered = AlertRenderer().render(make_full_context())
    rendered = replace(base_rendered, alert_decision_id=42)
    output = PlainTextAdapter().format(rendered)
    assert "Decision:     42" in output
    assert "Decision:     unknown" not in output


def test_decision_id_renders_unknown_when_none():
    base_rendered = AlertRenderer().render(make_full_context())
    rendered = replace(base_rendered, alert_decision_id=None)
    output = PlainTextAdapter().format(rendered)
    assert "Decision:     unknown" in output
