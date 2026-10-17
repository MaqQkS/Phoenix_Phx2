"""2026-07-29 final Telegram cleanup + Global Fee Support v1.

Locks the final operator-surface contract proven against the real Juan
($JUAN) alert regression (3G2At3nh…pump):

1. Participation renders NOWHERE in Telegram; the full raw telemetry stays
   in the compose artifact (presentation-only removal).
2. No internal reason code, nested ``UNKNOWN (...)`` fallback, raw enum
   identifier, or snake_case token can reach the body — the presentation
   boundary classifies every field (AVAILABLE / UNAVAILABLE /
   NOT_APPLICABLE / HIDDEN_INTERNAL) and only AVAILABLE values render.
3. Unavailable evidence never renders as an authentic zero; an authentic
   measured zero renders only with valid evidence status.
4. Structure carries operator conclusions only; Ante renders only when at
   least one meaningful group is valid; Builder Read renders only approved
   sentences.
5. Global Fee Support v1 (observe-only):
   ``fee_support_per_10k = global_fees_paid_sol / (market_cap_usd/10000)``
   in Decimal; below 1.0 → MANIPULATED (the only Telegram label), 1.0 to
   below 2.0 → WEAK (artifact-only), 2.0+ → SUPPORTED (artifact-only);
   rejected inputs stay UNAVAILABLE and never delay dispatch.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from PHX2.delivery.global_fee_support import (
    FEE_SUPPORT_CALCULATED,
    FEE_SUPPORT_MANIPULATED,
    FEE_SUPPORT_REJECTED,
    FEE_SUPPORT_SUPPORTED,
    FEE_SUPPORT_UNAVAILABLE,
    FEE_SUPPORT_WEAK,
    GLOBAL_FEE_SUPPORT_RULE_VERSION,
    REASON_FEES_INTERVAL_UNSUPPORTED,
    REASON_FEES_MINT_MISMATCH,
    REASON_FEES_OBSERVATION_STALE,
    REASON_FEES_SNAPSHOT_MISSING,
    REASON_FEES_STALE,
    REASON_FEES_UNAVAILABLE,
    REASON_FEES_UNIT_CONTRACT_UNPROVEN,
    REASON_FEES_VALUE_INVALID,
    REASON_MARKET_CAP_NOT_POSITIVE,
    REASON_MARKET_CAP_OBSERVATION_STALE,
    REASON_MARKET_CAP_UNAVAILABLE,
    classify_fee_support_per_10k,
    evaluate_global_fee_support,
)
from PHX2.delivery.telegram_adapter import (
    BUILDER_NO_RULE_REASON,
    TelegramDeliveryAdapter,
    build_ping_data,
)
from PHX2.delivery.telegram_composer import (
    FIELD_AVAILABLE,
    FIELD_HIDDEN_INTERNAL,
    FIELD_NOT_APPLICABLE,
    FIELD_UNAVAILABLE,
    TELEGRAM_INTERNAL_MAX_CHARACTERS,
    TelegramMessageTooLong,
    TelegramPingData,
    classify_operator_display,
    compose_telegram_ping,
)
from PHX2.free_tier_producer.compat import production_live_artifacts


JUAN_MINT = "3G2At3nh674eLVjfRXnJw3HGsgQQAWMXCsPvt9tBpump"
APPA_MINT = "38K55aqSCMrahqPBTZLLa9DvKygaSG4NqhxXvGE4pump"
LIVE_MINT = "335SdxzgdttfbNyKWzkdphiCWKTZduK7XJE8rL6Spump"

NOW = "2026-07-29T12:00:00Z"
NOW_DT = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


FEES_OBSERVED = _iso(NOW_DT - timedelta(seconds=90))
MARKET_FETCHED = _iso(NOW_DT - timedelta(seconds=120))

#: Internal implementation strings that must never reach any operator body.
BANNED_BODY_STRINGS = (
    "PARTICIPATION_OBSERVATION_WINDOW_UNAVAILABLE",
    "FEE_GATE_SCORE_UNAVAILABLE",
    "ANTE_LAST20_UNAVAILABLE",
    "ANTE_5M_UNAVAILABLE",
    "BASE_FEE_COVERAGE_UNAVAILABLE",
    "PRIORITY_FEE_MEDIAN_UNAVAILABLE",
    "MARKET_INCOMPLETE_REPEATED",
    "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE",
    "NO APPROVED SHAPE RULE",
    "NO APPROVED LIQUIDITY QUALITY RULE",
    "phx1_fee_gate_data_stale",
    "ORGANICITY_UNVERIFIED",
    "MANUAL_REVIEW_REQUIRED",
    "UNKNOWN (",
    "UNKNOWN",
    "RISK_MEDIUM",
    "RISK_HIGH",
    "RISK_LOW",
    "sticky_lock",
    "balanced_fees",
    "thin_sample",
    "SCAM Likely",
    "Participation",
    "SOL/min",
    "ev/min",
    "Events:",
    "LP Integrity",
    "Composite",
    "MANIPULATED",
    "SUPPORTED",
    "WEAK",
    "GLOBAL_FEE_SUPPORT",
)


def _assert_operator_clean(body: str) -> None:
    for banned in BANNED_BODY_STRINGS:
        assert banned not in body, banned
    assert production_live_artifacts.scan_text(body) == []


def _stale_unknown_fee(mint: str, *, event_pace: str = "0"):
    """The exact Juan evidence shape: a stale PHX1 fee gate whose snapshot
    carries synthetic zeroes, no score, and no observation window."""

    return SimpleNamespace(
        candidate_mint=mint, proof_digest="fee-proof",
        total_fees="0", lp_fees="0", protocol_fees="0", creator_fees="0",
        event_pace_per_minute=event_pace, event_count=0,
        fee_gate_label="UNKNOWN", fee_gate_score=None,
        fee_gate_reasons=("PHX1_FEE_GATE_DATA_STALE",),
        missing_data_reasons=(), stale_data_reasons=(
            "PHX1_FEE_GATE_DATA_STALE",),
        malformed_data_reasons=(), insufficient_sample_reasons=(),
        balanced_fees=False,
        bribe_share_pct="0", creator_share="0", bribes_per_transaction="0",
        first_observed_at_utc=None, last_observed_at_utc=None,
        ante_last20_median=None, ante_last20_p25=None, ante_last20_p75=None,
        ante_last20_sample_count=0,
        ante_5m_median=None, ante_5m_p25=None, ante_5m_p75=None,
        ante_5m_sample_count=0, ante_5m_base_fee_coverage=None,
        priority_fee_median_lamports=None, priority_fee_sample_count=0,
        ante_5m_shape=None, ante_5m_shape_rule=None,
        ante_last20_shape=None, ante_last20_shape_rule=None,
    )


def _measured_fee(mint: str, *, migration: datetime, now: datetime,
                  bribe_share="5.21", creator_share="0.522",
                  bribes_per_tx="0.000278478", label="Elevated", score=1,
                  reasons=("sticky_lock",), balanced=False):
    return SimpleNamespace(
        candidate_mint=mint, proof_digest="fee-proof",
        total_fees=Decimal("9.67"), lp_fees=Decimal("0.90"),
        protocol_fees=Decimal("3.72"), creator_fees=Decimal("5.05"),
        event_pace_per_minute=Decimal("27"), event_count=1809,
        fee_gate_label=label, fee_gate_score=score,
        fee_gate_reasons=tuple(reasons),
        missing_data_reasons=(), stale_data_reasons=(),
        malformed_data_reasons=(), insufficient_sample_reasons=(),
        balanced_fees=balanced,
        bribe_share_pct=Decimal(bribe_share),
        creator_share=Decimal(creator_share),
        bribes_per_transaction=Decimal(bribes_per_tx),
        first_observed_at_utc=_iso(migration),
        last_observed_at_utc=_iso(now),
        ante_last20_median=Decimal("0.000058"),
        ante_last20_p25=Decimal("0.000028"),
        ante_last20_p75=Decimal("0.000551"),
        ante_last20_sample_count=20,
        ante_5m_median=Decimal("0.000029"),
        ante_5m_p25=Decimal("0.000018"),
        ante_5m_p75=Decimal("0.0000594"),
        ante_5m_sample_count=322,
        ante_5m_base_fee_coverage=Decimal("1"),
        priority_fee_median_lamports=11574,
        priority_fee_sample_count=20,
        ante_5m_shape=None, ante_5m_shape_rule=None,
        ante_last20_shape=None, ante_last20_shape_rule=None,
    )


def _security(fee, *, shadow_reasons=(), manual_review=False):
    if manual_review:
        return SimpleNamespace(
            fee_snapshot=fee, lp_snapshot=None,
            lp_integrity_mode="DISABLED_SINGLE_STREAM",
            verdict="ALLOW", proof_digest="security-proof",
            phx1_structural_policy="SHADOW",
            original_phx1_structural_verdict="HARD_BLOCK",
            effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
            shadow_warning_reason_tokens=tuple(shadow_reasons),
            organicity_status="UNVERIFIED",
            manual_review_required=True,
            phx1_policy_digest="policy-digest",
        )
    return SimpleNamespace(
        fee_snapshot=fee, lp_snapshot=None,
        lp_integrity_mode="DISABLED_SINGLE_STREAM",
        verdict="ALLOW", proof_digest="security-proof",
        phx1_structural_policy="SHADOW",
        original_phx1_structural_verdict="PASS",
        effective_phx1_policy_verdict="PASS",
        shadow_warning_reason_tokens=(),
        organicity_status="UNVERIFIED",
        manual_review_required=False,
        phx1_policy_digest="policy-digest",
    )


def _global_fees_snapshot(*, mint, value, observed_at=FEES_OBSERVED,
                          status="VALID", interval="alltime",
                          schema="phx2_global_fees_v1"):
    return {
        "schema_version": schema,
        "token_mint": mint,
        "global_fees_status": status,
        "global_fees_paid_sol": value,
        "global_fees_interval": interval,
        "global_fees_source": "PAID_MARKET_PRIMARY",
        "global_fees_endpoint_source": "TOKEN_OVERVIEW",
        "global_fees_observed_at_utc": observed_at,
        "global_fees_request_reused": True,
        "observe_only": True,
    }


def _juan_context(*, global_fees_value="20.7", market_cap="45900",
                  market_fetched=MARKET_FETCHED, global_fees=None):
    migration = NOW_DT - timedelta(minutes=50)
    fee = _stale_unknown_fee(JUAN_MINT)
    security = _security(
        fee, shadow_reasons=("PHX1_FEE_GATE_DATA_STALE",),
        manual_review=True)
    if global_fees is None:
        global_fees = _global_fees_snapshot(
            mint=JUAN_MINT, value=global_fees_value)
    candidate = {
        "token_mint": JUAN_MINT,
        "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
        "token_name": "Juan",
        "symbol_or_name": "JUAN",
        "migration_time_utc": _iso(migration),
        "canonical_volume_5m": {
            "schema_version": "phx2_canonical_swap_volume_v1",
            "status": "INSUFFICIENT_DATA",
            "mint": JUAN_MINT,
            "window_seconds": 300,
            "gross_volume_usd": None,
            "net_quote_flow_usd": None,
            "sample_count": 0,
            "observe_only": True,
        },
        "global_fees": global_fees,
        "fee_gate_lifecycle": {
            "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
            "lifecycle_state": "TEMPORARILY_STALE",
            "evidence_proof_digest": "fee-proof",
        },
    }
    delivery_context = {
        "candidate": candidate,
        "market_context": {
            "current_market_cap_usd": market_cap,
            "market_context_fetched_at_utc": market_fetched,
            "central_ath": {"ath_market_cap": "100000"},
            "risk_assessment": {
                "risk_label": "RISK_MEDIUM",
                "risk_reasons": ["LP_FALLING", "MARKET_INCOMPLETE_REPEATED"],
            },
        },
        "activation": {"migration_market_cap_usd": "30200"},
        "security_decision": security,
    }
    snapshot = SimpleNamespace(
        token_mint=JUAN_MINT, tier_token="Tier 2",
        current_market_cap_usd=market_cap)
    return snapshot, delivery_context


JUAN_GOLDEN = """<b>🔥 PHOENIX — Juan ($JUAN) [Tier 2]</b>
<code>3G2At3nh674eLVjfRXnJw3HGsgQQAWMXCsPvt9tBpump</code>

<b>🧠 State</b>
• MC: $45.9k | Obs ATH: $100k | Mig: $30.2k
• Floor: -54% | Age: 50m | Vol 5m: —
• LP: —
• Coverage: Partial (restart backfill)

💸 Global Fees: 20.7 SOL

<b>🛑 Structure</b>
• Fee Gate: —
• Risk: Medium — LP falling
• Read: fee data stale
• Policy: SHADOW BLOCK — fee data stale

<b>🏗️ Builder Read</b>
• Attention is weak"""


def _live_context(*, global_fees=None, market_cap="86400",
                  risk_label="RISK_LOW", risk_reasons=()):
    migration = NOW_DT - timedelta(minutes=41)
    fee = _measured_fee(LIVE_MINT, migration=migration, now=NOW_DT)
    security = _security(fee)
    candidate = {
        "token_mint": LIVE_MINT,
        "discovery_provenance": "LIVE_YELLOWSTONE",
        "token_name": "Three Three Five",
        "token_symbol": "TTF",
        "symbol_or_name": "TTF",
        "migration_time_utc": _iso(migration),
        "canonical_volume_5m": {
            "schema_version": "phx2_canonical_swap_volume_v1",
            "status": "VALID",
            "mint": LIVE_MINT,
            "window_seconds": 300,
            "gross_volume_usd": "2700",
            "net_quote_flow_usd": "-843",
            "sample_count": 48,
            "observe_only": True,
        },
        "fee_gate_lifecycle": {
            "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
            "lifecycle_state": "FRESH_CONFIRMED",
            "evidence_proof_digest": "fee-proof",
        },
    }
    if global_fees is not None:
        candidate["global_fees"] = global_fees
    delivery_context = {
        "candidate": candidate,
        "market_context": {
            "current_market_cap_usd": market_cap,
            "market_context_fetched_at_utc": MARKET_FETCHED,
            "central_ath": {"ath_market_cap": "179400"},
            "risk_assessment": {
                "risk_label": risk_label,
                "risk_reasons": list(risk_reasons),
            },
        },
        "activation": {"migration_market_cap_usd": "30020"},
        "security_decision": security,
    }
    snapshot = SimpleNamespace(
        token_mint=LIVE_MINT, tier_token="Tier 1",
        current_market_cap_usd=market_cap)
    return snapshot, delivery_context


def _compose_body(snapshot, delivery_context, *, now_utc=NOW):
    data = build_ping_data(
        mint=str(snapshot.token_mint), composed_snapshot=snapshot,
        delivery_context=delivery_context, now_utc=now_utc)
    return data, compose_telegram_ping(data)


# =========================================================================
# 1. Juan regression: the exact final operator body
# =========================================================================


def test_juan_regression_renders_the_exact_clean_body():
    snapshot, delivery_context = _juan_context()
    data, composed = _compose_body(snapshot, delivery_context)
    assert composed.text == JUAN_GOLDEN
    assert composed.rendered_character_count \
        <= TELEGRAM_INTERNAL_MAX_CHARACTERS
    _assert_operator_clean(composed.text)
    # The withheld evidence is disclosed on the artifact surface.
    assert data.field_reason_codes["fee_gate"] == (
        "PHX1_FEE_GATE_DATA_STALE",)
    assert data.field_reason_codes["fee_breakdown"] == (
        "PHX1_FEE_GATE_DATA_STALE",)
    assert data.field_reason_codes["participation_pace"] == (
        "PARTICIPATION_OBSERVATION_WINDOW_UNAVAILABLE",)
    assert composed.field_presentation["fee_gate"] == FIELD_UNAVAILABLE
    assert composed.field_presentation["fee_breakdown"] == FIELD_UNAVAILABLE
    assert composed.field_presentation["ante_last20"] == FIELD_UNAVAILABLE
    assert composed.field_presentation["shape_5m"] == FIELD_NOT_APPLICABLE
    assert composed.field_presentation["global_fees"] == FIELD_AVAILABLE


def test_juan_unavailable_evidence_never_renders_as_zero():
    snapshot, delivery_context = _juan_context()
    _data, composed = _compose_body(snapshot, delivery_context)
    body = composed.text
    assert "0.00 SOL" not in body
    assert "0%" not in body
    assert "0 lamports" not in body
    assert "(0)" not in body
    assert "n=0" not in body
    assert "• Fee Gate: —" in body


def test_juan_omits_participation_and_ante_sections_entirely():
    snapshot, delivery_context = _juan_context()
    _data, composed = _compose_body(snapshot, delivery_context)
    assert "Participation" not in composed.text
    assert "Ante" not in composed.text
    assert "Median" not in composed.text
    assert "Priority Fee" not in composed.text
    assert "Width" not in composed.text


# =========================================================================
# 2. Complete-live fixture: authentic values render, PASS footer omitted
# =========================================================================


def test_complete_live_body_renders_measured_values_without_internal_text():
    snapshot, delivery_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="20.7"))
    data, composed = _compose_body(snapshot, delivery_context)
    lines = composed.text.splitlines()
    assert lines[0] == "<b>🔥 PHOENIX — Three Three Five ($TTF) [Tier 1]</b>"
    assert "• MC: $86.4k | Post-mig ATH: $179.4k | Mig: $30k" in lines
    assert "• Floor: -52% | Age: 41m | Vol 5m: $2.7k gross | -$843 net (n=48)" \
        in lines
    assert "💸 Global Fees: 20.7 SOL" in lines
    assert "• Fee Gate: Elevated (1)" in lines
    assert ("• Bribes/AMM: 5.2% | Creator: 52.2% | "
            "Bribes/tx: 278,478 lamports") in lines
    assert "• Read: sticky lock" in lines
    assert "Policy:" not in composed.text
    assert "• Risk:" not in composed.text
    assert "• Median last-20sw: 0.000058 SOL | p25/p75: 0.000028 / 0.000551" \
        in lines
    assert "• Median 5m: 0.000029 SOL (n=322) | base-fee cov: 100%" in lines
    assert "⛽️ Priority Fee: 11,574 lam (n=20)" in lines
    assert "• Late-sequence stress state" in lines
    assert "Coverage:" not in composed.text
    _assert_operator_clean(composed.text)
    # 20.7 SOL against $86.4k MC is 2.395… SOL per $10k: SUPPORTED, no label.
    assert data.global_fee_support["classification"] == FEE_SUPPORT_SUPPORTED
    assert "Manipulated" not in composed.text


def test_authentic_measured_zero_renders_with_valid_evidence():
    migration = NOW_DT - timedelta(minutes=41)
    fee = _measured_fee(
        LIVE_MINT, migration=migration, now=NOW_DT,
        bribe_share="0", creator_share="0", bribes_per_tx="0",
        label="Normal", score=0, reasons=(), balanced=False)
    snapshot, delivery_context = _live_context()
    delivery_context["security_decision"] = _security(fee)
    _data, composed = _compose_body(snapshot, delivery_context)
    lines = composed.text.splitlines()
    # Evidence status is valid, so exact zeroes are authentic measurements.
    assert "• Fee Gate: Normal (0)" in lines
    assert "• Bribes/AMM: 0% | Creator: 0% | Bribes/tx: 0 lamports" in lines
    assert production_live_artifacts.scan_text(composed.text) == []


# =========================================================================
# 3. Restart-backfill fixture and partial Ante
# =========================================================================


def test_restart_backfill_fixture_keeps_coverage_and_obs_ath():
    snapshot, delivery_context = _juan_context()
    _data, composed = _compose_body(snapshot, delivery_context)
    lines = composed.text.splitlines()
    assert "• Coverage: Partial (restart backfill)" in lines
    assert "Obs ATH: $100k" in composed.text
    assert "Post-mig ATH" not in composed.text
    assert "PARTIAL_SINCE_ADMISSION" not in composed.text
    assert "DEXSCREENER" not in composed.text


def test_partial_ante_renders_only_the_valid_groups():
    migration = NOW_DT - timedelta(minutes=41)
    fee = _measured_fee(LIVE_MINT, migration=migration, now=NOW_DT)
    fee.ante_last20_median = None
    fee.ante_last20_p25 = None
    fee.ante_last20_p75 = None
    fee.ante_5m_median = None
    fee.ante_5m_p25 = None
    fee.ante_5m_p75 = None
    fee.ante_5m_base_fee_coverage = None
    snapshot, delivery_context = _live_context()
    delivery_context["security_decision"] = _security(fee)
    _data, composed = _compose_body(snapshot, delivery_context)
    lines = composed.text.splitlines()
    assert "<b>🎲 Ante (observe-only)</b>" in lines
    assert "⛽️ Priority Fee: 11,574 lam (n=20)" in lines
    assert "Median" not in composed.text
    assert "Width" not in composed.text
    assert "base-fee cov" not in composed.text
    _assert_operator_clean(composed.text)


def test_fully_unavailable_ante_omits_the_section():
    snapshot, delivery_context = _juan_context()
    _data, composed = _compose_body(snapshot, delivery_context)
    assert "🎲" not in composed.text
    assert "observe-only" not in composed.text


# =========================================================================
# 4. Presentation boundary
# =========================================================================


@pytest.mark.parametrize("value", [
    "UNKNOWN (PARTICIPATION_OBSERVATION_WINDOW_UNAVAILABLE)",
    "UNKNOWN (UNKNOWN (FEE_GATE_SCORE_UNAVAILABLE))",
    "UNKNOWN",
    "RISK_MEDIUM",
    "RISK_MEDIUM — LP falling",
    "phx1_fee_gate_data_stale",
    "sticky_lock",
    "thin_sample",
    "MARKET_INCOMPLETE_REPEATED",
    "NO APPROVED SHAPE RULE",
    "NO APPROVED LIQUIDITY QUALITY RULE",
])
def test_boundary_hides_internal_fallback_values(value):
    status, display = classify_operator_display(value)
    assert status == FIELD_HIDDEN_INTERNAL
    assert display == ""


@pytest.mark.parametrize("value", [
    "Medium — LP falling",
    "fee data stale",
    "sticky lock",
    "20.7 SOL",
    "2 SOL (Manipulated)",
    "$45.9k",
    "-54%",
    "278,478",
    "0",
])
def test_boundary_passes_operator_values(value):
    status, display = classify_operator_display(value)
    assert status == FIELD_AVAILABLE
    assert display == value


def test_boundary_classifies_empty_and_marker_as_unavailable():
    assert classify_operator_display("")[0] == FIELD_UNAVAILABLE
    assert classify_operator_display(None)[0] == FIELD_UNAVAILABLE
    assert classify_operator_display("—")[0] == FIELD_UNAVAILABLE


def test_boundary_suppresses_nested_leak_end_to_end():
    """Even if an upstream regression feeds a raw fallback into a display
    field, the body renders the unavailable marker — never the string."""

    snapshot, delivery_context = _juan_context()
    data, _composed = _compose_body(snapshot, delivery_context)
    poisoned = replace(
        data,
        floor="UNKNOWN (ATH_FLOOR_UNAVAILABLE)",
        structure_read="phx1_fee_gate_data_stale",
        risk_warning="RISK_MEDIUM — LP falling",
    )
    composed = compose_telegram_ping(poisoned)
    assert "UNKNOWN" not in composed.text
    assert "ATH_FLOOR_UNAVAILABLE" not in composed.text
    assert "RISK_MEDIUM" not in composed.text
    assert "phx1_fee_gate_data_stale" not in composed.text
    assert "• Floor: — | Age: 50m | Vol 5m: —" in composed.text
    assert "• Read:" not in composed.text
    assert "• Risk:" not in composed.text
    assert composed.field_presentation["floor"] == FIELD_HIDDEN_INTERNAL
    assert composed.field_presentation["structure_read"] \
        == FIELD_HIDDEN_INTERNAL
    assert composed.field_presentation["risk"] == FIELD_HIDDEN_INTERNAL


# =========================================================================
# 5. Global Fee Support v1: exact formula and thresholds
# =========================================================================


def _support(*, fees="2", market_cap="100000", mint=LIVE_MINT,
             snapshot=None, market_fetched=MARKET_FETCHED, now=NOW,
             token_age=2460.0):
    if snapshot is None:
        snapshot = _global_fees_snapshot(mint=mint, value=fees)
    return evaluate_global_fee_support(
        mint=LIVE_MINT,
        global_fees_snapshot=snapshot,
        market_cap_usd=market_cap,
        market_cap_observed_at_utc=market_fetched,
        now_utc=now,
        token_age_seconds=token_age,
    )


def test_formula_is_exact_decimal_per_10k():
    result = _support(fees="2", market_cap="100000")
    assert result.calculation_status == FEE_SUPPORT_CALCULATED
    assert result.fee_support_per_10k_sol == "0.2"
    assert result.classification == FEE_SUPPORT_MANIPULATED

    assert _support(fees="10", market_cap="100000").fee_support_per_10k_sol \
        == "1"
    assert _support(fees="10", market_cap="100000").classification \
        == FEE_SUPPORT_WEAK
    assert _support(fees="15", market_cap="100000").fee_support_per_10k_sol \
        == "1.5"
    assert _support(fees="15", market_cap="100000").classification \
        == FEE_SUPPORT_WEAK
    assert _support(fees="20", market_cap="100000").fee_support_per_10k_sol \
        == "2"
    assert _support(fees="20", market_cap="100000").classification \
        == FEE_SUPPORT_SUPPORTED


def test_juan_values_classify_supported():
    result = _support(fees="20.7", market_cap="45900")
    assert result.classification == FEE_SUPPORT_SUPPORTED
    ratio = Decimal(result.fee_support_per_10k_sol)
    with localcontext() as context:
        context.prec = 34
        expected = (Decimal("20.7") * 10000) / Decimal("45900")
    assert ratio == expected
    assert result.fee_support_per_10k_sol.startswith("4.50980392156862745")
    assert abs(ratio - Decimal("4.5098")) < Decimal("0.0001")


def test_threshold_boundaries_are_exact():
    assert classify_fee_support_per_10k(
        Decimal("0.999999999")) == FEE_SUPPORT_MANIPULATED
    assert classify_fee_support_per_10k(Decimal("1.0")) == FEE_SUPPORT_WEAK
    assert classify_fee_support_per_10k(
        Decimal("1.999999999")) == FEE_SUPPORT_WEAK
    assert classify_fee_support_per_10k(Decimal("2.0")) \
        == FEE_SUPPORT_SUPPORTED
    assert classify_fee_support_per_10k(Decimal("0")) \
        == FEE_SUPPORT_MANIPULATED


@pytest.mark.parametrize("kwargs,reason", [
    ({"snapshot": {}}, REASON_FEES_MINT_MISMATCH),
    ({"snapshot": _global_fees_snapshot(mint=APPA_MINT, value="2")},
     REASON_FEES_MINT_MISMATCH),
    ({"snapshot": _global_fees_snapshot(
        mint=LIVE_MINT, value="2", schema="unknown_schema_v9")},
     REASON_FEES_UNIT_CONTRACT_UNPROVEN),
    ({"snapshot": _global_fees_snapshot(
        mint=LIVE_MINT, value="2", interval="24h")},
     REASON_FEES_INTERVAL_UNSUPPORTED),
    ({"snapshot": _global_fees_snapshot(
        mint=LIVE_MINT, value="2", status="STALE")}, REASON_FEES_STALE),
    ({"snapshot": _global_fees_snapshot(
        mint=LIVE_MINT, value="2", status="PROVIDER_ERROR")},
     REASON_FEES_UNAVAILABLE),
    ({"snapshot": _global_fees_snapshot(mint=LIVE_MINT, value="NaN")},
     REASON_FEES_VALUE_INVALID),
    ({"snapshot": _global_fees_snapshot(mint=LIVE_MINT, value="-1")},
     REASON_FEES_VALUE_INVALID),
    ({"snapshot": _global_fees_snapshot(mint=LIVE_MINT, value=None)},
     REASON_FEES_VALUE_INVALID),
    ({"snapshot": _global_fees_snapshot(
        mint=LIVE_MINT, value="2",
        observed_at=_iso(NOW_DT - timedelta(seconds=301)))},
     REASON_FEES_OBSERVATION_STALE),
    ({"market_cap": None}, REASON_MARKET_CAP_UNAVAILABLE),
    ({"market_cap": "not-a-number"}, REASON_MARKET_CAP_UNAVAILABLE),
    ({"market_cap": "NaN"}, REASON_MARKET_CAP_UNAVAILABLE),
    ({"market_cap": "0"}, REASON_MARKET_CAP_NOT_POSITIVE),
    ({"market_cap": "-45900"}, REASON_MARKET_CAP_NOT_POSITIVE),
    ({"market_fetched": None}, REASON_MARKET_CAP_OBSERVATION_STALE),
    ({"market_fetched": _iso(NOW_DT - timedelta(seconds=301))},
     REASON_MARKET_CAP_OBSERVATION_STALE),
])
def test_rejections_stay_unavailable_with_exact_reason(kwargs, reason):
    result = _support(**kwargs)
    assert result.calculation_status == FEE_SUPPORT_REJECTED
    assert result.classification == FEE_SUPPORT_UNAVAILABLE
    assert result.failure_reason == reason
    assert result.fee_support_per_10k_sol is None


def test_missing_snapshot_rejects():
    result = evaluate_global_fee_support(
        mint=LIVE_MINT, global_fees_snapshot=None,
        market_cap_usd="100000", market_cap_observed_at_utc=MARKET_FETCHED,
        now_utc=NOW)
    assert result.failure_reason == REASON_FEES_SNAPSHOT_MISSING
    assert result.classification == FEE_SUPPORT_UNAVAILABLE


def test_artifact_retains_every_input_and_result():
    result = _support(fees="2", market_cap="100000")
    artifact = result.to_artifact(
        rendered_label="Manipulated", rendered_in_telegram=True)
    assert artifact == {
        "rule_version": GLOBAL_FEE_SUPPORT_RULE_VERSION,
        "token_mint": LIVE_MINT,
        "mint_match": True,
        "classification": FEE_SUPPORT_MANIPULATED,
        "calculation_status": FEE_SUPPORT_CALCULATED,
        "failure_reason": None,
        "global_fees_paid_sol": "2",
        "market_cap_usd": "100000",
        "fee_support_per_10k_sol": "0.2",
        "threshold_manipulated_per_10k_sol": "1",
        "threshold_supported_per_10k_sol": "2",
        "global_fees_observed_at_utc": FEES_OBSERVED,
        "market_cap_observed_at_utc": MARKET_FETCHED,
        "input_age_seconds": 120.0,
        "token_age_seconds": 2460.0,
        "rendered_label": "Manipulated",
        "rendered_in_telegram": True,
        "observe_only": True,
    }


# =========================================================================
# 6. Global Fee Support in the Telegram body
# =========================================================================


def test_manipulated_fixture_appends_the_label():
    snapshot, delivery_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="2"),
        market_cap="100000")
    data, composed = _compose_body(snapshot, delivery_context)
    assert "💸 Global Fees: 2 SOL (Manipulated)" in composed.text.splitlines()
    support = data.global_fee_support
    assert support["classification"] == FEE_SUPPORT_MANIPULATED
    assert support["fee_support_per_10k_sol"] == "0.2"
    assert support["rendered_label"] == "Manipulated"
    assert support["rendered_in_telegram"] is True
    assert support["observe_only"] is True
    _assert_operator_clean(composed.text)


def test_weak_fixture_renders_no_label():
    snapshot, delivery_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="15"),
        market_cap="100000")
    data, composed = _compose_body(snapshot, delivery_context)
    assert "💸 Global Fees: 15 SOL" in composed.text.splitlines()
    assert "Manipulated" not in composed.text
    assert data.global_fee_support["classification"] == FEE_SUPPORT_WEAK
    assert data.global_fee_support["rendered_label"] is None
    assert data.global_fee_support["rendered_in_telegram"] is True


def test_supported_fixture_renders_no_label():
    snapshot, delivery_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="20"),
        market_cap="100000")
    data, composed = _compose_body(snapshot, delivery_context)
    assert "💸 Global Fees: 20 SOL" in composed.text.splitlines()
    assert "Manipulated" not in composed.text
    assert data.global_fee_support["classification"] == FEE_SUPPORT_SUPPORTED
    assert data.global_fee_support["fee_support_per_10k_sol"] == "2"


def test_unclassifiable_fixture_shows_the_valid_value_without_label():
    # Market-cap observation timestamp missing: the fees line still renders,
    # the classification stays UNAVAILABLE, and dispatch is not delayed.
    snapshot, delivery_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="2"),
        market_cap="100000")
    del delivery_context["market_context"]["market_context_fetched_at_utc"]
    data, composed = _compose_body(snapshot, delivery_context)
    assert "💸 Global Fees: 2 SOL" in composed.text.splitlines()
    assert "Manipulated" not in composed.text
    support = data.global_fee_support
    assert support["classification"] == FEE_SUPPORT_UNAVAILABLE
    assert support["failure_reason"] == REASON_MARKET_CAP_OBSERVATION_STALE
    assert support["rendered_label"] is None
    assert support["rendered_in_telegram"] is True


def test_invalid_fee_value_omits_the_line_and_stays_unavailable():
    snapshot, delivery_context = _live_context(
        global_fees=_global_fees_snapshot(
            mint=LIVE_MINT, value="2", status="STALE"),
        market_cap="100000")
    data, composed = _compose_body(snapshot, delivery_context)
    assert "Global Fees" not in composed.text
    assert data.global_fee_support["classification"] \
        == FEE_SUPPORT_UNAVAILABLE
    assert data.global_fee_support["rendered_in_telegram"] is False
    assert data.global_fee_support["rendered_label"] is None


def test_classification_is_observe_only_and_never_changes_dispatch_inputs():
    manipulated_snapshot, manipulated_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="2"),
        market_cap="100000")
    supported_snapshot, supported_context = _live_context(
        global_fees=_global_fees_snapshot(mint=LIVE_MINT, value="20"),
        market_cap="100000")
    manipulated, _ = _compose_body(manipulated_snapshot, manipulated_context)
    supported, _ = _compose_body(supported_snapshot, supported_context)
    for field in dataclass_fields(TelegramPingData):
        if field.name in ("global_fees_display", "global_fee_support"):
            continue
        assert getattr(manipulated, field.name) \
            == getattr(supported, field.name), field.name
    # Eligibility, tier, structural verdicts, and dedupe axes are untouched.
    assert manipulated.tier == supported.tier
    assert manipulated.effective_phx1_policy_verdict \
        == supported.effective_phx1_policy_verdict
    assert manipulated.manual_review_required \
        == supported.manual_review_required
    from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
        ping_dedupe_key_field_names,
    )
    assert "global_fee_support" not in ping_dedupe_key_field_names()
    assert "global_fees_display" not in ping_dedupe_key_field_names()


# =========================================================================
# 7. Compose artifact preservation
# =========================================================================


def test_compose_artifact_preserves_participation_and_support_blocks():
    snapshot, delivery_context = _juan_context()
    composed_artifacts = []
    adapter = TelegramDeliveryAdapter(
        transport=SimpleNamespace(send_html=None, close=lambda: None),
        compose_sink=composed_artifacts.append, console_sink=None)
    adapter.bind_delivery(
        body="bound-body", mint=JUAN_MINT, composed_snapshot=snapshot,
        delivery_context=delivery_context, created_at_utc=NOW)
    assert adapter.last_compose_artifact is not None
    assert len(composed_artifacts) == 1
    telemetry = adapter.last_compose_artifact["observe_only_telemetry"]
    participation = telemetry["participation"]
    assert participation == {
        "total_fees_sol": "0",
        "lp_fees_sol": "0",
        "protocol_fees_sol": "0",
        "creator_fees_sol": "0",
        "participation_pace_sol_per_minute": None,
        "observation_window_minutes": None,
        "event_pace_per_minute": "0",
        "event_count": 0,
        "first_observed_at_utc": None,
        "last_observed_at_utc": None,
        "fee_evidence_valid": False,
        "rendered_in_telegram": False,
    }
    support = telemetry["global_fee_support"]
    assert support["rule_version"] == GLOBAL_FEE_SUPPORT_RULE_VERSION
    assert support["classification"] == FEE_SUPPORT_SUPPORTED
    assert support["mint_match"] is True
    assert support["token_age_seconds"] == 3000.0
    structure = telemetry["structure_evidence"]
    assert structure["fee_gate_label"] == "UNKNOWN"
    assert structure["fee_gate_score"] is None
    assert structure["fee_gate_reasons"] == ["PHX1_FEE_GATE_DATA_STALE"]
    assert structure["fee_evidence_valid"] is False
    assert structure["structure_read_source"] == "phx1_fee_gate_data_stale"
    presentation = adapter.last_compose_artifact["field_presentation"]
    assert presentation["fee_gate"] == FIELD_UNAVAILABLE
    assert presentation["global_fees"] == FIELD_AVAILABLE
    # The raw Global Fees observation is preserved unchanged alongside.
    assert telemetry["global_fees"]["global_fees_paid_sol"] == "20.7"
    assert telemetry["global_fees"]["global_fees_status"] == "VALID"


def test_builder_no_match_omits_section_and_records_reason():
    snapshot, delivery_context = _juan_context()
    fee = delivery_context["security_decision"].fee_snapshot
    fee.event_pace_per_minute = "3"  # not weak, not attention-present
    data, composed = _compose_body(snapshot, delivery_context)
    assert data.builder_read == ()
    assert "Builder Read" not in composed.text
    assert data.field_reason_codes["builder_read"] == (
        BUILDER_NO_RULE_REASON,)


# =========================================================================
# 8. Length contract stays fail-closed
# =========================================================================


def test_overlength_body_still_refuses_compose():
    snapshot, delivery_context = _juan_context()
    data, _composed = _compose_body(snapshot, delivery_context)
    with pytest.raises(TelegramMessageTooLong):
        compose_telegram_ping(replace(data, structure_read="x" * 4200))
