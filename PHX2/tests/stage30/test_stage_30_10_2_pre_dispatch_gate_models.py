"""Stage 30.10.2 pre-dispatch tier-dip gate models tests.

Covers the immutable / frozen gate input + record + proof-summary + scenario
models, the closed-set gate decision / gate reason vocabularies + their
predicates, the caller-injected ``created_at_utc``, the pinned field names,
and that no model field carries a secret- / env- / payload-class name.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    DECISION_ELIGIBLE_DIP,
    REASON_TIER_ALLOWED,
    Stage30_10DipEligibilityInput,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    GATE_REASON_ELIGIBLE_DIP,
    GATE_REASON_INVALID_GATE_INPUT,
    GATE_REASON_NOT_DIP,
    STAGE30_10_2_GATE_DECISIONS,
    STAGE30_10_2_GATE_PASS_DECISION,
    STAGE30_10_2_GATE_PASS_REASON,
    STAGE30_10_2_GATE_REASONS,
    STAGE30_10_2_MINOR_VERSION,
    Stage30_10PreDispatchGateInput,
    Stage30_10PreDispatchGateProofSummary,
    Stage30_10PreDispatchGateRecord,
    Stage30_10PreDispatchGateScenario,
    gate_input_field_names,
    gate_record_field_names,
    is_gate_decision,
    is_gate_reason,
    proof_summary_field_names,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"


def _elig_input(**overrides) -> Stage30_10DipEligibilityInput:
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


def _gate_input(**overrides) -> Stage30_10PreDispatchGateInput:
    base = dict(
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_input=_elig_input(),
        candidate_ref="ref-cand-1",
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10PreDispatchGateInput(**base)


def _gate_record(**overrides) -> Stage30_10PreDispatchGateRecord:
    base = dict(
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_decision=DECISION_ELIGIBLE_DIP,
        eligibility_reason=REASON_TIER_ALLOWED,
        send_allowed=True,
        gate_decision=GATE_DECISION_PASS_TO_DISPATCH,
        gate_reason=GATE_REASON_ELIGIBLE_DIP,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10PreDispatchGateRecord(**base)


# ---------------------------------------------------------------------------
# 1. Version
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_10_2_MINOR_VERSION == "30.10.2"


# ---------------------------------------------------------------------------
# 2. Closed-set gate decisions / reasons pinned
# ---------------------------------------------------------------------------


def test_gate_decisions_closed_set_pinned() -> None:
    assert STAGE30_10_2_GATE_DECISIONS == (
        GATE_DECISION_PASS_TO_DISPATCH,
        GATE_DECISION_SKIP_BEFORE_DISPATCH,
        GATE_DECISION_INVALID_INPUT,
    )
    assert STAGE30_10_2_GATE_DECISIONS == (
        "PASS_TO_DISPATCH",
        "SKIP_BEFORE_DISPATCH",
        "INVALID_INPUT",
    )
    for token in STAGE30_10_2_GATE_DECISIONS:
        assert is_gate_decision(token)
    assert not is_gate_decision("NOPE")
    assert not is_gate_decision(None)
    assert not is_gate_decision(123)


def test_pass_decision_is_pass_to_dispatch() -> None:
    assert STAGE30_10_2_GATE_PASS_DECISION == "PASS_TO_DISPATCH"
    assert STAGE30_10_2_GATE_PASS_DECISION == GATE_DECISION_PASS_TO_DISPATCH


def test_gate_reasons_closed_set_pinned() -> None:
    assert STAGE30_10_2_GATE_REASONS == (
        GATE_REASON_ELIGIBLE_DIP,
        GATE_REASON_NOT_DIP,
        GATE_REASON_INVALID_GATE_INPUT,
    )
    assert STAGE30_10_2_GATE_REASONS == (
        "ELIGIBLE_DIP",
        "NOT_DIP",
        "INVALID_GATE_INPUT",
    )
    for token in STAGE30_10_2_GATE_REASONS:
        assert is_gate_reason(token)
    assert not is_gate_reason("NOPE")
    assert not is_gate_reason(None)


def test_pass_reason_is_eligible_dip() -> None:
    assert STAGE30_10_2_GATE_PASS_REASON == "ELIGIBLE_DIP"
    assert STAGE30_10_2_GATE_PASS_REASON == GATE_REASON_ELIGIBLE_DIP


def test_no_payload_refused_token_in_closed_sets() -> None:
    # A normal non-dip skip must NEVER reuse the transport PAYLOAD_REFUSED
    # veto; no gate decision / reason carries such a token.
    joined = " ".join(STAGE30_10_2_GATE_DECISIONS + STAGE30_10_2_GATE_REASONS)
    assert "PAYLOAD_REFUSED" not in joined
    assert "REFUSED" not in joined
    assert "TRANSPORT" not in joined.upper()


# ---------------------------------------------------------------------------
# 3. Models are immutable / frozen
# ---------------------------------------------------------------------------


def test_gate_input_is_frozen() -> None:
    gi = _gate_input()
    with pytest.raises(dataclasses.FrozenInstanceError):
        gi.candidate_id = "other"  # type: ignore[misc]


def test_gate_record_is_frozen() -> None:
    rec = _gate_record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.gate_decision = GATE_DECISION_SKIP_BEFORE_DISPATCH  # type: ignore[misc]


def test_proof_summary_is_frozen() -> None:
    summary = Stage30_10PreDispatchGateProofSummary(
        candidates_seen=9,
        candidates_passed=3,
        candidates_skipped=5,
        invalid_inputs=1,
        dispatch_attempts_reserved=3,
        dispatch_attempts_suppressed_before_reservation=6,
        created_at_utc=_SAFE_CREATED_AT,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.candidates_passed = 0  # type: ignore[misc]


def test_scenario_is_frozen() -> None:
    scenario = Stage30_10PreDispatchGateScenario(
        name="s",
        gate_inputs=(_gate_input(),),
        created_at_utc=_SAFE_CREATED_AT,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        scenario.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. created_at_utc is caller-injected and echoed verbatim
# ---------------------------------------------------------------------------


def test_created_at_utc_is_caller_injected() -> None:
    gi = _gate_input(created_at_utc="2026-05-31T12:34:56Z")
    assert gi.created_at_utc == "2026-05-31T12:34:56Z"
    rec = _gate_record(created_at_utc="2026-05-31T12:34:56Z")
    assert rec.created_at_utc == "2026-05-31T12:34:56Z"


# ---------------------------------------------------------------------------
# 5. Embedded eligibility input preserved verbatim
# ---------------------------------------------------------------------------


def test_embedded_eligibility_input_preserved() -> None:
    elig = _elig_input(candidate_id="embedded", drawdown_from_ath=Decimal("0.6"))
    gi = _gate_input(eligibility_input=elig)
    assert gi.eligibility_input is elig
    assert isinstance(gi.eligibility_input, Stage30_10DipEligibilityInput)
    assert gi.eligibility_input.drawdown_from_ath == Decimal("0.6")


def test_candidate_ref_optional() -> None:
    assert _gate_input(candidate_ref=None).candidate_ref is None
    assert _gate_input(candidate_ref="ref-x").candidate_ref == "ref-x"


# ---------------------------------------------------------------------------
# 6. Field-name helpers pinned + no secret / env / payload field names
# ---------------------------------------------------------------------------


def test_field_name_helpers_pinned() -> None:
    assert gate_input_field_names() == (
        "candidate_id",
        "token_mint",
        "eligibility_input",
        "candidate_ref",
        "created_at_utc",
    )
    assert gate_record_field_names() == (
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "send_allowed",
        "gate_decision",
        "gate_reason",
        "created_at_utc",
    )
    assert proof_summary_field_names() == (
        "candidates_seen",
        "candidates_passed",
        "candidates_skipped",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_attempts_suppressed_before_reservation",
        "created_at_utc",
    )


_FORBIDDEN_FIELD_SUBSTRINGS = (
    "webhook",
    "api_key",
    "apikey",
    "bearer",
    "authorization",
    "secret",
    "password",
    "private_key",
    "privatekey",
    "mnemonic",
    "seed_phrase",
    "credential",
    "raw_payload",
    "payload",
    "getenv",
    "environ",
)


def test_no_secret_or_env_field_names() -> None:
    all_fields = (
        gate_input_field_names()
        + gate_record_field_names()
        + proof_summary_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in _FORBIDDEN_FIELD_SUBSTRINGS:
            assert forbidden not in lower, (
                f"Stage 30.10.2 model field {name!r} carries a forbidden "
                f"secret / env / payload substring {forbidden!r}"
            )
