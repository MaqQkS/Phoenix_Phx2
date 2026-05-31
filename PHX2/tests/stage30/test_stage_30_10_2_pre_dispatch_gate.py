"""Stage 30.10.2 pre-dispatch tier-dip gate tests.

Proves the optional pre-dispatch gate is correctly placed + behaved:

  * Tier 1 / Tier 2 / Tier 3 eligible dips -> PASS_TO_DISPATCH (the ONLY
    decision that proceeds to dispatch reservation);
  * Tier Unknown / Tier Not Applicable / missing ATH / missing migration /
    malformed drawdown -> SKIP_BEFORE_DISPATCH (a normal no-send: NOT a
    transport failure, NOT PAYLOAD_REFUSED, NOT counted as a dispatch
    failure);
  * invalid candidate id / token mint / created_at_utc / eligibility input
    -> INVALID_INPUT (fail closed; never proceeds to reservation);
  * NO no-send candidate can pass; NO skipped candidate is a dispatch
    failure; and the gate emits only closed-set tokens and is deterministic.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    DECISION_ELIGIBLE_DIP,
    DECISION_INVALID_INPUT,
    REASON_INVALID_CANDIDATE_ID,
    REASON_INVALID_CREATED_AT_UTC,
    REASON_INVALID_TOKEN_MINT,
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate import (
    Stage30_10PreDispatchGateError,
    evaluate_pre_dispatch_tier_dip_gate,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    GATE_REASON_ELIGIBLE_DIP,
    GATE_REASON_INVALID_GATE_INPUT,
    GATE_REASON_NOT_DIP,
    STAGE30_10_2_GATE_DECISIONS,
    STAGE30_10_2_GATE_REASONS,
    Stage30_10PreDispatchGateInput,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"


def _elig_input(**overrides) -> Stage30_10DipEligibilityInput:
    """A fully dip-eligible base eligibility input; overrides isolate one
    rule.
    """
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
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10DipEligibilityInput(**base)


def _gate_input(
    *,
    candidate_id="cand-1",
    token_mint="mint-1",
    created_at_utc=_SAFE_CREATED_AT,
    candidate_ref="ref-cand-1",
    **elig_overrides,
) -> Stage30_10PreDispatchGateInput:
    """Build a gate envelope wrapping an eligibility input; ``elig_overrides``
    isolate one eligibility rule, while the gate identity stays valid unless
    explicitly overridden.
    """
    elig = _elig_input(
        candidate_id=candidate_id,
        token_mint=token_mint,
        **elig_overrides,
    )
    return Stage30_10PreDispatchGateInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        eligibility_input=elig,
        candidate_ref=candidate_ref,
        created_at_utc=created_at_utc,
    )


def _gate(**kwargs):
    return evaluate_pre_dispatch_tier_dip_gate(_gate_input(**kwargs))


# ---------------------------------------------------------------------------
# 1. Eligible dips PASS_TO_DISPATCH
# ---------------------------------------------------------------------------


def test_tier_1_passes_to_dispatch() -> None:
    rec = _gate(tier_token="Tier 1")
    assert rec.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    assert rec.gate_reason == GATE_REASON_ELIGIBLE_DIP
    assert rec.eligibility_decision == DECISION_ELIGIBLE_DIP
    assert rec.send_allowed is True


def test_tier_2_passes_to_dispatch() -> None:
    rec = _gate(tier_token="Tier 2", drawdown_from_ath=Decimal("0.70"))
    assert rec.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    assert rec.gate_reason == GATE_REASON_ELIGIBLE_DIP
    assert rec.send_allowed is True


def test_tier_3_passes_to_dispatch() -> None:
    rec = _gate(tier_token="Tier 3", drawdown_from_ath=Decimal("0.90"))
    assert rec.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    assert rec.gate_reason == GATE_REASON_ELIGIBLE_DIP
    assert rec.send_allowed is True


def test_pass_record_echoes_identity_and_clock() -> None:
    rec = evaluate_pre_dispatch_tier_dip_gate(
        _gate_input(
            candidate_id="cand-echo",
            token_mint="mint-echo",
            created_at_utc="2026-05-31T12:34:56Z",
            tier_token="Tier 2",
            drawdown_from_ath=Decimal("0.66"),
        )
    )
    assert rec.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    assert rec.candidate_id == "cand-echo"
    assert rec.token_mint == "mint-echo"
    assert rec.created_at_utc == "2026-05-31T12:34:56Z"


# ---------------------------------------------------------------------------
# 2. Non-dips SKIP_BEFORE_DISPATCH (normal no-send, never a dispatch failure)
# ---------------------------------------------------------------------------


def test_tier_unknown_skips_before_dispatch() -> None:
    rec = _gate(tier_token="Tier Unknown")
    assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    assert rec.gate_reason == GATE_REASON_NOT_DIP
    assert rec.send_allowed is False


def test_tier_not_applicable_skips_before_dispatch() -> None:
    rec = _gate(tier_token="Tier Not Applicable")
    assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    assert rec.gate_reason == GATE_REASON_NOT_DIP
    assert rec.send_allowed is False


def test_missing_ath_skips_before_dispatch() -> None:
    rec = _gate(ath_status="MISSING")
    assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    assert rec.gate_reason == GATE_REASON_NOT_DIP
    assert rec.send_allowed is False


def test_missing_migration_skips_before_dispatch() -> None:
    rec = _gate(migration_status="MISSING")
    assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    assert rec.gate_reason == GATE_REASON_NOT_DIP
    assert rec.send_allowed is False


def test_malformed_drawdown_skips_before_dispatch() -> None:
    # A non-Decimal / non-finite drawdown is not a confirmed dip; it is a
    # normal skip, NOT an invalid input and NOT a dispatch failure.
    for bad in ("0.55", 0.55, object(), Decimal("NaN"), Decimal("Infinity")):
        rec = _gate(tier_token="Tier 1", drawdown_from_ath=bad)
        assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH, (
            f"malformed drawdown {bad!r} must SKIP_BEFORE_DISPATCH"
        )
        assert rec.gate_reason == GATE_REASON_NOT_DIP
        assert rec.send_allowed is False


def test_policy_excluded_tier_skips_before_dispatch() -> None:
    # An in-band tier the policy excludes is a normal non-dip skip.
    policy = Stage30_10DipEligibilityPolicy(allowed_tiers=("TIER_1", "TIER_2"))
    rec = evaluate_pre_dispatch_tier_dip_gate(
        _gate_input(tier_token="Tier 3", drawdown_from_ath=Decimal("0.9")),
        policy,
    )
    assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    assert rec.gate_reason == GATE_REASON_NOT_DIP
    assert rec.send_allowed is False


def test_skip_is_not_a_transport_or_payload_refused_path() -> None:
    # The normal non-dip skip reasons never carry a PAYLOAD_REFUSED / transport
    # veto token; the skip is a clean no-send.
    for overrides in (
        {"tier_token": "Tier Unknown"},
        {"tier_token": "Tier Not Applicable"},
        {"ath_status": "MISSING"},
        {"migration_status": "MISSING"},
        {"drawdown_from_ath": "0.55"},
    ):
        rec = _gate(**overrides)
        assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
        assert "PAYLOAD_REFUSED" not in rec.gate_reason
        assert "REFUSED" not in rec.gate_reason
        # A skip is never the pass decision (never reserved for dispatch).
        assert rec.gate_decision != GATE_DECISION_PASS_TO_DISPATCH


# ---------------------------------------------------------------------------
# 3. Invalid gate envelope -> INVALID_INPUT (fail closed)
# ---------------------------------------------------------------------------


def test_invalid_candidate_id_is_invalid_input() -> None:
    for cid in ("", "   "):
        rec = _gate(candidate_id=cid)
        assert rec.gate_decision == GATE_DECISION_INVALID_INPUT
        assert rec.gate_reason == GATE_REASON_INVALID_GATE_INPUT
        assert rec.eligibility_decision == DECISION_INVALID_INPUT
        assert rec.eligibility_reason == REASON_INVALID_CANDIDATE_ID
        assert rec.send_allowed is False


def test_invalid_token_mint_is_invalid_input() -> None:
    for mint in ("", "  "):
        rec = _gate(token_mint=mint)
        assert rec.gate_decision == GATE_DECISION_INVALID_INPUT
        assert rec.gate_reason == GATE_REASON_INVALID_GATE_INPUT
        assert rec.eligibility_reason == REASON_INVALID_TOKEN_MINT
        assert rec.send_allowed is False


def test_invalid_created_at_is_invalid_input() -> None:
    for ts in ("", "not-a-time", "2026-01-01T00:00:00"):
        rec = _gate(created_at_utc=ts)
        assert rec.gate_decision == GATE_DECISION_INVALID_INPUT
        assert rec.gate_reason == GATE_REASON_INVALID_GATE_INPUT
        assert rec.eligibility_reason == REASON_INVALID_CREATED_AT_UTC
        assert rec.send_allowed is False


def test_wrong_type_eligibility_input_is_invalid_input() -> None:
    # A gate envelope whose eligibility_input is not a real input fails closed
    # before reservation; the classifier is never consulted.
    for bogus in (None, "not-an-input", 123, {"candidate_id": "c"}):
        gi = Stage30_10PreDispatchGateInput(
            candidate_id="cand-1",
            token_mint="mint-1",
            eligibility_input=bogus,  # type: ignore[arg-type]
            candidate_ref=None,
            created_at_utc=_SAFE_CREATED_AT,
        )
        rec = evaluate_pre_dispatch_tier_dip_gate(gi)
        assert rec.gate_decision == GATE_DECISION_INVALID_INPUT
        assert rec.gate_reason == GATE_REASON_INVALID_GATE_INPUT
        assert rec.send_allowed is False


def test_classifier_invalid_input_maps_to_invalid_input() -> None:
    # A well-typed eligibility input with a blank embedded candidate id is
    # classified INVALID_INPUT and surfaces as gate INVALID_INPUT (here the
    # gate identity is valid but the embedded input is not).
    gi = Stage30_10PreDispatchGateInput(
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_input=_elig_input(candidate_id=""),
        candidate_ref=None,
        created_at_utc=_SAFE_CREATED_AT,
    )
    rec = evaluate_pre_dispatch_tier_dip_gate(gi)
    assert rec.gate_decision == GATE_DECISION_INVALID_INPUT
    assert rec.gate_reason == GATE_REASON_INVALID_GATE_INPUT
    assert rec.eligibility_decision == DECISION_INVALID_INPUT
    assert rec.send_allowed is False


def test_non_gate_input_object_raises() -> None:
    for bogus in (None, "not-an-input", 123, {"candidate_id": "c"}):
        with pytest.raises(Stage30_10PreDispatchGateError):
            evaluate_pre_dispatch_tier_dip_gate(bogus)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. No no-send candidate can pass; no skip is a dispatch failure
# ---------------------------------------------------------------------------


def test_no_no_send_candidate_can_pass() -> None:
    no_send_overrides = (
        {"tier_token": "Tier Unknown"},
        {"tier_token": "Tier Not Applicable"},
        {"tier_token": None},
        {"tier_token": "garbage"},
        {"migration_status": None},
        {"migration_status": "MISSING"},
        {"ath_status": None},
        {"ath_status": "UNAVAILABLE"},
        {"post_migration_ath_verified": False},
        {"market_context_status": None},
        {"current_market_cap_usd": None},
        {"current_market_cap_usd": Decimal("0")},
        {"drawdown_from_ath": None},
        {"drawdown_from_ath": "0.55"},
        {"drawdown_from_ath": Decimal("NaN")},
    )
    for overrides in no_send_overrides:
        rec = _gate(**overrides)
        assert rec.gate_decision != GATE_DECISION_PASS_TO_DISPATCH, (
            f"no-send candidate {overrides!r} must not PASS_TO_DISPATCH"
        )
        assert rec.send_allowed is False
        # Every no-send is either a clean skip or an invalid input -- never a
        # dispatch failure / transport veto.
        assert rec.gate_decision in (
            GATE_DECISION_SKIP_BEFORE_DISPATCH,
            GATE_DECISION_INVALID_INPUT,
        )


def test_no_skip_or_invalid_carries_a_pass_reason() -> None:
    for overrides in (
        {"tier_token": "Tier Unknown"},
        {"ath_status": "MISSING"},
        {"candidate_id": ""},
    ):
        rec = _gate(**overrides)
        assert rec.gate_reason != GATE_REASON_ELIGIBLE_DIP


# ---------------------------------------------------------------------------
# 5. Purity + closed-set output invariants
# ---------------------------------------------------------------------------


def test_gate_is_deterministic() -> None:
    gi = _gate_input(tier_token="Tier 1")
    first = evaluate_pre_dispatch_tier_dip_gate(gi)
    second = evaluate_pre_dispatch_tier_dip_gate(gi)
    assert first == second


def test_all_outcomes_emit_closed_set_tokens() -> None:
    sweep = (
        {"tier_token": "Tier 1"},
        {"tier_token": "Tier 2", "drawdown_from_ath": Decimal("0.7")},
        {"tier_token": "Tier 3", "drawdown_from_ath": Decimal("0.9")},
        {"tier_token": "Tier Unknown"},
        {"tier_token": "Tier Not Applicable"},
        {"ath_status": None},
        {"migration_status": None},
        {"drawdown_from_ath": "0.55"},
        {"candidate_id": ""},
        {"token_mint": ""},
        {"created_at_utc": "bad"},
    )
    for overrides in sweep:
        rec = _gate(**overrides)
        assert rec.gate_decision in STAGE30_10_2_GATE_DECISIONS
        assert rec.gate_reason in STAGE30_10_2_GATE_REASONS
        # send_allowed is True iff the gate passed to dispatch.
        assert rec.send_allowed == (
            rec.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
        )
