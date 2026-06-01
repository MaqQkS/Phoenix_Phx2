"""Stage 30.9.3 dip-filtered live gate models unit tests.

Pins the three frozen Stage 30.9.3 integration models (the assembled
live-candidate input, the per-candidate live gate decision, the rolled-up
integration result): their field names + order, their immutability, their
field-name helpers, and the integration schema version. Fake / offline only;
no live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    STAGE30_9_3_INTEGRATION_SCHEMA_VERSION,
    STAGE30_9_3_MINOR_VERSION,
    Stage30_9_3LiveGateDecision,
    Stage30_9_3LiveGateInput,
    Stage30_9_3LiveGateIntegrationResult,
    integration_result_field_names,
    live_gate_decision_field_names,
    live_gate_input_field_names,
)


def _live_input() -> Stage30_9_3LiveGateInput:
    return Stage30_9_3LiveGateInput(
        candidate_id="cand-1",
        token_mint="mint-1",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref="ref-cand-1",
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _decision() -> Stage30_9_3LiveGateDecision:
    return Stage30_9_3LiveGateDecision(
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_decision="ELIGIBLE_DIP",
        eligibility_reason="TIER_ALLOWED",
        gate_decision="PASS_TO_DISPATCH",
        gate_reason="ELIGIBLE_DIP",
        artifact_schema_version="stage30_10_v0_gate_artifact",
        dispatch_reservation_allowed=True,
        suppressed_before_dispatch_reservation=False,
        dispatch_failure_recorded=False,
        transport_veto_used=False,
        payload_refused_used=False,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _result() -> Stage30_9_3LiveGateIntegrationResult:
    return Stage30_9_3LiveGateIntegrationResult(
        candidates_seen=9,
        candidates_evaluated=9,
        candidates_passed_gate=3,
        candidates_skipped_before_dispatch=5,
        invalid_inputs=1,
        dispatch_attempts_reserved=3,
        dispatch_failures_recorded=0,
        transport_veto_count=0,
        payload_refused_count=0,
        would_send_private_discord_count=3,
        created_at_utc="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_9_3_MINOR_VERSION == "30.9.3"


def test_integration_schema_version_pinned() -> None:
    assert STAGE30_9_3_INTEGRATION_SCHEMA_VERSION == (
        "stage30_9_3_v0_dip_filtered_live_gate"
    )


# ---------------------------------------------------------------------------
# Field names (order matters)
# ---------------------------------------------------------------------------


def test_live_gate_input_field_names() -> None:
    assert live_gate_input_field_names() == (
        "candidate_id",
        "token_mint",
        "tier_token",
        "drawdown_from_ath",
        "migration_status",
        "ath_status",
        "market_context_status",
        "current_market_cap_usd",
        "post_migration_ath_verified",
        "candidate_ref",
        "created_at_utc",
    )


def test_live_gate_decision_field_names() -> None:
    assert live_gate_decision_field_names() == (
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "gate_decision",
        "gate_reason",
        "artifact_schema_version",
        "dispatch_reservation_allowed",
        "suppressed_before_dispatch_reservation",
        "dispatch_failure_recorded",
        "transport_veto_used",
        "payload_refused_used",
        "created_at_utc",
    )


def test_integration_result_field_names() -> None:
    assert integration_result_field_names() == (
        "candidates_seen",
        "candidates_evaluated",
        "candidates_passed_gate",
        "candidates_skipped_before_dispatch",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
        "would_send_private_discord_count",
        "created_at_utc",
    )


# ---------------------------------------------------------------------------
# Construction echoes + immutability
# ---------------------------------------------------------------------------


def test_live_input_echoes_fields() -> None:
    rec = _live_input()
    assert rec.candidate_id == "cand-1"
    assert rec.token_mint == "mint-1"
    assert rec.drawdown_from_ath == Decimal("0.55")
    assert rec.current_market_cap_usd == Decimal("12345.67")
    assert rec.post_migration_ath_verified is True
    assert rec.candidate_ref == "ref-cand-1"


def test_live_input_allows_optional_none_values() -> None:
    rec = Stage30_9_3LiveGateInput(
        candidate_id="c",
        token_mint="m",
        tier_token=None,
        drawdown_from_ath=None,
        migration_status=None,
        ath_status=None,
        market_context_status=None,
        current_market_cap_usd=None,
        post_migration_ath_verified=None,
        candidate_ref=None,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert rec.tier_token is None
    assert rec.drawdown_from_ath is None
    assert rec.candidate_ref is None


def test_decision_carries_always_false_transport_safety_flags() -> None:
    dec = _decision()
    assert dec.dispatch_failure_recorded is False
    assert dec.transport_veto_used is False
    assert dec.payload_refused_used is False


@pytest.mark.parametrize("model", [_live_input(), _decision(), _result()])
def test_models_are_frozen(model: object) -> None:
    # A frozen dataclass raises FrozenInstanceError on any attribute set.
    with pytest.raises(FrozenInstanceError):
        setattr(model, "candidate_id", "mutated")
