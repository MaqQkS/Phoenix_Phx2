"""Stage 30.9.3 dip-filtered live gate adapter unit tests.

Pins that the adapter composes the committed Stage 30.10 dip-gate stack
correctly: it builds the Stage 30.10.1 eligibility input from the assembled
live context, runs the Stage 30.10.2 gate (which runs the Stage 30.10.1
classifier) and the Stage 30.10.3 projection, and returns a Stage 30.9.3 live
gate decision whose ``dispatch_reservation_allowed`` is ``True`` ONLY for a
gate ``PASS_TO_DISPATCH`` candidate. Every non-pass candidate is suppressed
BEFORE reservation; the three transport-safety negatives are ALWAYS ``False``.
Fake / offline only; no live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
    Stage30_9_3DipFilteredLiveGateError,
    build_eligibility_input,
    build_gate_input,
    evaluate_dip_filtered_live_gate,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    Stage30_10PreDispatchGateInput,
)

_CREATED_AT: str = "2026-01-01T00:00:00Z"


def _mk(**overrides: object) -> Stage30_9_3LiveGateInput:
    base = dict(
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
        created_at_utc=_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_9_3LiveGateInput(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def test_build_eligibility_input_maps_fields() -> None:
    elig = build_eligibility_input(_mk())
    assert isinstance(elig, Stage30_10DipEligibilityInput)
    assert elig.candidate_id == "cand-1"
    assert elig.token_mint == "mint-1"
    assert elig.tier_token == "Tier 1"
    assert elig.drawdown_from_ath == Decimal("0.55")
    assert elig.migration_status == "PRESENT"
    assert elig.ath_status == "PRESENT"
    assert elig.market_context_status == "PRESENT"
    assert elig.current_market_cap_usd == Decimal("12345.67")
    assert elig.post_migration_ath_verified is True
    assert elig.created_at_utc == _CREATED_AT


def test_build_gate_input_wraps_with_matching_identity() -> None:
    gate_input = build_gate_input(_mk())
    assert isinstance(gate_input, Stage30_10PreDispatchGateInput)
    assert gate_input.candidate_id == "cand-1"
    assert gate_input.token_mint == "mint-1"
    assert gate_input.candidate_ref == "ref-cand-1"
    assert gate_input.created_at_utc == _CREATED_AT
    assert isinstance(
        gate_input.eligibility_input, Stage30_10DipEligibilityInput
    )
    assert gate_input.eligibility_input.candidate_id == "cand-1"


def test_builders_reject_wrong_type() -> None:
    for bad in (None, "not-a-record", 123, object()):
        with pytest.raises(Stage30_9_3DipFilteredLiveGateError):
            build_eligibility_input(bad)  # type: ignore[arg-type]
        with pytest.raises(Stage30_9_3DipFilteredLiveGateError):
            build_gate_input(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# evaluate_dip_filtered_live_gate -- decision mapping
# ---------------------------------------------------------------------------


def test_eligible_dip_passes_to_dispatch() -> None:
    dec = evaluate_dip_filtered_live_gate(_mk())
    assert dec.gate_decision == "PASS_TO_DISPATCH"
    assert dec.gate_reason == "ELIGIBLE_DIP"
    assert dec.eligibility_decision == "ELIGIBLE_DIP"
    assert dec.eligibility_reason == "TIER_ALLOWED"
    assert dec.dispatch_reservation_allowed is True
    assert dec.suppressed_before_dispatch_reservation is False
    assert dec.artifact_schema_version == "stage30_10_v0_gate_artifact"
    assert dec.created_at_utc == _CREATED_AT


@pytest.mark.parametrize(
    "overrides, expected_elig_decision, expected_elig_reason",
    [
        ({"tier_token": "Tier Unknown"}, "SKIPPED_TIER_UNKNOWN", "TIER_UNKNOWN"),
        (
            {"tier_token": "Tier Not Applicable"},
            "SKIPPED_TIER_NOT_APPLICABLE",
            "TIER_NOT_APPLICABLE",
        ),
        ({"ath_status": "MISSING"}, "SKIPPED_MISSING_ATH", "MISSING_ATH"),
        (
            {"migration_status": "MISSING"},
            "SKIPPED_MISSING_MIGRATION",
            "MISSING_MIGRATION",
        ),
        ({"drawdown_from_ath": "0.55"}, "SKIPPED_NOT_DIP", "MISSING_DRAWDOWN"),
    ],
)
def test_non_dip_skips_before_dispatch(
    overrides: dict,
    expected_elig_decision: str,
    expected_elig_reason: str,
) -> None:
    dec = evaluate_dip_filtered_live_gate(_mk(**overrides))
    assert dec.gate_decision == "SKIP_BEFORE_DISPATCH"
    assert dec.gate_reason == "NOT_DIP"
    assert dec.eligibility_decision == expected_elig_decision
    assert dec.eligibility_reason == expected_elig_reason
    assert dec.dispatch_reservation_allowed is False
    assert dec.suppressed_before_dispatch_reservation is True


def test_invalid_candidate_is_invalid_input() -> None:
    dec = evaluate_dip_filtered_live_gate(_mk(candidate_id=""))
    assert dec.gate_decision == "INVALID_INPUT"
    assert dec.gate_reason == "INVALID_GATE_INPUT"
    assert dec.eligibility_decision == "INVALID_INPUT"
    assert dec.dispatch_reservation_allowed is False
    assert dec.suppressed_before_dispatch_reservation is True


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"tier_token": "Tier Unknown"},
        {"ath_status": "MISSING"},
        {"drawdown_from_ath": "0.55"},
        {"candidate_id": ""},
    ],
)
def test_transport_safety_flags_always_false(overrides: dict) -> None:
    dec = evaluate_dip_filtered_live_gate(_mk(**overrides))
    assert dec.dispatch_failure_recorded is False
    assert dec.transport_veto_used is False
    assert dec.payload_refused_used is False


def test_dispatch_reservation_allowed_is_complement_of_suppressed() -> None:
    for overrides in ({}, {"tier_token": "Tier Unknown"}, {"candidate_id": ""}):
        dec = evaluate_dip_filtered_live_gate(_mk(**overrides))
        assert dec.dispatch_reservation_allowed == (
            not dec.suppressed_before_dispatch_reservation
        )


def test_only_pass_allows_reservation() -> None:
    # The ONLY decision with dispatch_reservation_allowed True is a true dip.
    dip = evaluate_dip_filtered_live_gate(_mk())
    assert dip.dispatch_reservation_allowed is True
    for overrides in (
        {"tier_token": "Tier Unknown"},
        {"tier_token": "Tier Not Applicable"},
        {"ath_status": "MISSING"},
        {"migration_status": "MISSING"},
        {"drawdown_from_ath": "0.55"},
        {"candidate_id": ""},
    ):
        dec = evaluate_dip_filtered_live_gate(_mk(**overrides))
        assert dec.dispatch_reservation_allowed is False


# ---------------------------------------------------------------------------
# Policy + wrong-type
# ---------------------------------------------------------------------------


def test_restrictive_policy_can_suppress_a_dip() -> None:
    # A policy that allows only Tier 2/3 turns a Tier 1 dip into a no-send,
    # proving the adapter forwards the policy to the gate stack.
    policy = Stage30_10DipEligibilityPolicy(allowed_tiers=("TIER_2", "TIER_3"))
    dec = evaluate_dip_filtered_live_gate(_mk(tier_token="Tier 1"), policy=policy)
    assert dec.gate_decision == "SKIP_BEFORE_DISPATCH"
    assert dec.dispatch_reservation_allowed is False
    # The same Tier 1 candidate passes under the default policy.
    assert evaluate_dip_filtered_live_gate(
        _mk(tier_token="Tier 1")
    ).gate_decision == "PASS_TO_DISPATCH"


def test_evaluate_rejects_wrong_type() -> None:
    for bad in (None, "x", 7, object()):
        with pytest.raises(Stage30_9_3DipFilteredLiveGateError):
            evaluate_dip_filtered_live_gate(bad)  # type: ignore[arg-type]


def test_evaluate_is_deterministic() -> None:
    a = evaluate_dip_filtered_live_gate(_mk())
    b = evaluate_dip_filtered_live_gate(_mk())
    assert a == b
