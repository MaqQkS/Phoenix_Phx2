"""Stage 30.10.2 offline fake pre-dispatch tier-dip gate proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.10.2
optional pre-dispatch gate is correctly placed and behaved using fakes /
offline candidates only:

    a fake candidate stream (Stage 30.10.1 eligibility inputs wrapped in
    Stage 30.10.2 gate envelopes)
      -> the Stage 30.10.2 pre-dispatch gate  (evaluated BEFORE reservation)
      -> a Stage 30.10.2 proof-summary tally

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a
dispatch reservation / real send, NOT a transport-layer veto, and NOT a new
readiness gate. It CONSTRUCTS no filesystem I/O, reads no environment, opens
no network connection, and touches no Discord / live provider path. It only
constructs in-memory fakes, runs them through the real Stage 30.10.2 gate,
and tallies the gate decisions.

The default scenario is a deterministic nine-candidate stream that exercises
every gate outcome:

  1. Tier 1 valid dip             -> PASS_TO_DISPATCH
  2. Tier 2 valid dip             -> PASS_TO_DISPATCH
  3. Tier 3 valid dip             -> PASS_TO_DISPATCH
  4. Tier Unknown                 -> SKIP_BEFORE_DISPATCH
  5. Tier Not Applicable          -> SKIP_BEFORE_DISPATCH
  6. missing ATH                  -> SKIP_BEFORE_DISPATCH
  7. missing migration            -> SKIP_BEFORE_DISPATCH
  8. malformed drawdown           -> SKIP_BEFORE_DISPATCH
  9. invalid candidate_id         -> INVALID_INPUT

So ``dispatch_attempts_reserved`` counts ONLY the three eligible dips, and
``dispatch_attempts_suppressed_before_reservation`` counts the five non-dip
skips plus the one invalid -- every non-dip / invalid is suppressed BEFORE
reservation, and no transport / ``PAYLOAD_REFUSED`` / Discord / live-provider
path is ever touched.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.10.2 gate-models + gate siblings + the Stage
    30.10.1 models sibling (to build the fake eligibility inputs). No other
    PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator /
    Stage 28 suppression / live runner / provider / transport import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY,
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate import (
    evaluate_pre_dispatch_tier_dip_gate,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    Stage30_10PreDispatchGateInput,
    Stage30_10PreDispatchGateProofSummary,
    Stage30_10PreDispatchGateScenario,
)


# The deterministic caller-injected clock for the default scenario (never a
# wall-clock read).
_DEFAULT_SCENARIO_CREATED_AT: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Pure fake builders
# ---------------------------------------------------------------------------


def _eligibility_input(
    *,
    candidate_id: str,
    token_mint: str,
    tier_token: Optional[str],
    drawdown_from_ath: object,
    migration_status: Optional[str],
    ath_status: Optional[str],
) -> Stage30_10DipEligibilityInput:
    """Build a fake Stage 30.10.1 eligibility input. All non-isolated
    signals default to the fully-present, dip-eligible shape so each fake
    candidate isolates exactly one rule. Pure; no I/O, no clock.
    """
    return Stage30_10DipEligibilityInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        tier_token=tier_token,
        drawdown_from_ath=drawdown_from_ath,  # type: ignore[arg-type]
        migration_status=migration_status,
        ath_status=ath_status,
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        created_at_utc=_DEFAULT_SCENARIO_CREATED_AT,
    )


def _gate_input(
    *,
    candidate_id: str,
    token_mint: str,
    eligibility_input: Stage30_10DipEligibilityInput,
) -> Stage30_10PreDispatchGateInput:
    """Wrap a fake eligibility input in a gate envelope whose identity
    matches the embedded input. Pure; no I/O, no clock.
    """
    return Stage30_10PreDispatchGateInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        eligibility_input=eligibility_input,
        candidate_ref=f"ref-{candidate_id}" if candidate_id else None,
        created_at_utc=_DEFAULT_SCENARIO_CREATED_AT,
    )


def default_pre_dispatch_gate_scenario() -> Stage30_10PreDispatchGateScenario:
    """Build the deterministic nine-candidate default gate scenario.

    Exercises every gate outcome: three eligible dips (Tier 1 / 2 / 3), five
    non-dip skips (Tier Unknown / Tier Not Applicable / missing ATH / missing
    migration / malformed drawdown), and one invalid candidate (blank id).
    Pure; no I/O, no clock, no env.
    """
    inputs = (
        # 1. Tier 1 valid dip -> PASS_TO_DISPATCH.
        _gate_input(
            candidate_id="cand-tier1",
            token_mint="mint-tier1",
            eligibility_input=_eligibility_input(
                candidate_id="cand-tier1",
                token_mint="mint-tier1",
                tier_token="Tier 1",
                drawdown_from_ath=Decimal("0.55"),
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
        # 2. Tier 2 valid dip -> PASS_TO_DISPATCH.
        _gate_input(
            candidate_id="cand-tier2",
            token_mint="mint-tier2",
            eligibility_input=_eligibility_input(
                candidate_id="cand-tier2",
                token_mint="mint-tier2",
                tier_token="Tier 2",
                drawdown_from_ath=Decimal("0.70"),
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
        # 3. Tier 3 valid dip -> PASS_TO_DISPATCH.
        _gate_input(
            candidate_id="cand-tier3",
            token_mint="mint-tier3",
            eligibility_input=_eligibility_input(
                candidate_id="cand-tier3",
                token_mint="mint-tier3",
                tier_token="Tier 3",
                drawdown_from_ath=Decimal("0.90"),
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
        # 4. Tier Unknown -> SKIP_BEFORE_DISPATCH.
        _gate_input(
            candidate_id="cand-unknown",
            token_mint="mint-unknown",
            eligibility_input=_eligibility_input(
                candidate_id="cand-unknown",
                token_mint="mint-unknown",
                tier_token="Tier Unknown",
                drawdown_from_ath=Decimal("0.55"),
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
        # 5. Tier Not Applicable -> SKIP_BEFORE_DISPATCH.
        _gate_input(
            candidate_id="cand-na",
            token_mint="mint-na",
            eligibility_input=_eligibility_input(
                candidate_id="cand-na",
                token_mint="mint-na",
                tier_token="Tier Not Applicable",
                drawdown_from_ath=Decimal("0.55"),
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
        # 6. missing ATH -> SKIP_BEFORE_DISPATCH.
        _gate_input(
            candidate_id="cand-no-ath",
            token_mint="mint-no-ath",
            eligibility_input=_eligibility_input(
                candidate_id="cand-no-ath",
                token_mint="mint-no-ath",
                tier_token="Tier 1",
                drawdown_from_ath=Decimal("0.55"),
                migration_status="PRESENT",
                ath_status="MISSING",
            ),
        ),
        # 7. missing migration -> SKIP_BEFORE_DISPATCH.
        _gate_input(
            candidate_id="cand-no-migration",
            token_mint="mint-no-migration",
            eligibility_input=_eligibility_input(
                candidate_id="cand-no-migration",
                token_mint="mint-no-migration",
                tier_token="Tier 1",
                drawdown_from_ath=Decimal("0.55"),
                migration_status="MISSING",
                ath_status="PRESENT",
            ),
        ),
        # 8. malformed drawdown -> SKIP_BEFORE_DISPATCH (not a confirmed dip).
        _gate_input(
            candidate_id="cand-bad-drawdown",
            token_mint="mint-bad-drawdown",
            eligibility_input=_eligibility_input(
                candidate_id="cand-bad-drawdown",
                token_mint="mint-bad-drawdown",
                tier_token="Tier 1",
                drawdown_from_ath="0.55",  # non-Decimal: fails closed.
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
        # 9. invalid candidate_id -> INVALID_INPUT (blank id, gate + input).
        _gate_input(
            candidate_id="",
            token_mint="mint-invalid",
            eligibility_input=_eligibility_input(
                candidate_id="",
                token_mint="mint-invalid",
                tier_token="Tier 1",
                drawdown_from_ath=Decimal("0.55"),
                migration_status="PRESENT",
                ath_status="PRESENT",
            ),
        ),
    )
    return Stage30_10PreDispatchGateScenario(
        name="default_pre_dispatch_gate_stream",
        gate_inputs=inputs,
        created_at_utc=_DEFAULT_SCENARIO_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_stage30_10_2_fake_gate_proof(
    scenario: Optional[Stage30_10PreDispatchGateScenario] = None,
    policy: Stage30_10DipEligibilityPolicy = (
        DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY
    ),
) -> Stage30_10PreDispatchGateProofSummary:
    """Run the offline fake pre-dispatch gate proof over a candidate stream.

    With ``scenario=None`` the deterministic nine-candidate default scenario
    is used. Each candidate is run through the real Stage 30.10.2 gate; the
    summary tallies how many would PASS to dispatch reservation vs be
    suppressed BEFORE reservation. ``dispatch_attempts_reserved`` equals the
    eligible-dip pass count; ``dispatch_attempts_suppressed_before_reservation``
    equals the non-dip skips plus the invalids. Pure / deterministic; reads
    no clock, no env, no network; never sends Discord, never calls a live
    provider, never performs a transport veto; never raises (a defensive
    backstop returns an all-zero summary).
    """
    try:
        return _run_fake_gate_proof(scenario, policy)
    except Exception:  # pragma: no cover - total fail-closed backstop
        return Stage30_10PreDispatchGateProofSummary(
            candidates_seen=0,
            candidates_passed=0,
            candidates_skipped=0,
            invalid_inputs=0,
            dispatch_attempts_reserved=0,
            dispatch_attempts_suppressed_before_reservation=0,
            created_at_utc="",
        )


def _run_fake_gate_proof(
    scenario: Optional[Stage30_10PreDispatchGateScenario],
    policy: Stage30_10DipEligibilityPolicy,
) -> Stage30_10PreDispatchGateProofSummary:
    """Proof body (see ``run_stage30_10_2_fake_gate_proof``)."""
    if scenario is None:
        scenario = default_pre_dispatch_gate_scenario()

    passed = 0
    skipped = 0
    invalid = 0
    for gate_input in scenario.gate_inputs:
        record = evaluate_pre_dispatch_tier_dip_gate(gate_input, policy)
        if record.gate_decision == GATE_DECISION_PASS_TO_DISPATCH:
            passed += 1
        elif record.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH:
            skipped += 1
        elif record.gate_decision == GATE_DECISION_INVALID_INPUT:
            invalid += 1

    seen = len(scenario.gate_inputs)
    # Only eligible dips are reserved for dispatch; every non-dip / invalid
    # is suppressed BEFORE reservation.
    reserved = passed
    suppressed_before_reservation = skipped + invalid
    return Stage30_10PreDispatchGateProofSummary(
        candidates_seen=seen,
        candidates_passed=passed,
        candidates_skipped=skipped,
        invalid_inputs=invalid,
        dispatch_attempts_reserved=reserved,
        dispatch_attempts_suppressed_before_reservation=(
            suppressed_before_reservation
        ),
        created_at_utc=scenario.created_at_utc,
    )


__all__ = (
    "default_pre_dispatch_gate_scenario",
    "run_stage30_10_2_fake_gate_proof",
)
