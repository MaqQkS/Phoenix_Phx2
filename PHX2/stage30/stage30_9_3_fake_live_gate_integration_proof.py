"""Stage 30.9.3 offline fake dip-filtered live gate integration proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.9.3
dip-filtered live dispatch integration seam is correctly dip-FILTERED, using
fakes / offline candidates + an injected in-memory dispatch sink ONLY. It
composes the REAL seam end to end:

    a deterministic fake stream of assembled live candidates
      -> the Stage 30.9.3 orchestrator
      -> (per candidate) the Stage 30.9.3 adapter -> the committed Stage 30.10
         dip-gate stack -> a Stage 30.9.3 live gate decision
      -> ONLY ``PASS_TO_DISPATCH`` candidates call the in-memory recording
         sink (the stand-in for the later private compact dispatch)

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a
real dispatch reservation, NOT a transport-layer veto, and NOT a new readiness
gate. It CONSTRUCTS no filesystem I/O, reads no environment, opens no network
connection, and touches no Discord / live provider path. The dispatch sink is
an explicitly in-memory recorder; nothing leaves the process.

The default scenario reuses the SAME deterministic nine-candidate shape as the
Stage 30.10.2 / 30.9.2 fake proofs, so the seam's classification matches the
committed gate stack exactly:

  1. Tier 1 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  2. Tier 2 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  3. Tier 3 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  4. Tier Unknown          -> SKIP_BEFORE_DISPATCH  (suppressed before)
  5. Tier Not Applicable   -> SKIP_BEFORE_DISPATCH  (suppressed before)
  6. missing ATH           -> SKIP_BEFORE_DISPATCH  (suppressed before)
  7. missing migration     -> SKIP_BEFORE_DISPATCH  (suppressed before)
  8. malformed drawdown    -> SKIP_BEFORE_DISPATCH  (suppressed before)
  9. invalid candidate_id  -> INVALID_INPUT         (suppressed before)

The ``no_dip`` scenario drops the three dips, leaving five non-dip skips + one
invalid -- a stream where no eligible dip ever appears (the
``NO_DIP_FOUND_BUT_SAFE`` shape).

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.9.3 models + orchestrator siblings. No other
    PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage
    28 suppression / live runner / provider / transport import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateDecision,
    Stage30_9_3LiveGateInput,
    Stage30_9_3LiveGateIntegrationResult,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator import (
    run_dip_filtered_live_gate_integration,
)


# The deterministic caller-injected clock for the default scenarios (never a
# wall-clock read). Matches the Stage 30.10.2 / 30.9.2 fake-proof clocks so the
# composed proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"

# The default safe proof-run id (a safe-shape opaque label; never a secret).
_DEFAULT_PROOF_ID: str = "stage30_9_3_fake_live_gate_integration_proof"


# ---------------------------------------------------------------------------
# In-memory recording dispatch sink (the fake stand-in for the private send)
# ---------------------------------------------------------------------------


class Stage30_9_3RecordingDispatchSink:
    """In-memory fake dispatch sink for the Stage 30.9.3 integration proof.

    Records each Stage 30.9.3 live gate decision the orchestrator hands it.
    Opens NO network connection, sends NO Discord message, performs NO real
    dispatch, writes NO file -- it only appends the decision to an in-memory
    list. Used to prove the orchestrator calls the sink EXACTLY for
    ``PASS_TO_DISPATCH`` candidates (and never for a non-dip / invalid skip).
    """

    def __init__(self) -> None:
        self.calls: List[Stage30_9_3LiveGateDecision] = []

    def __call__(self, decision: Stage30_9_3LiveGateDecision) -> None:
        self.calls.append(decision)

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ---------------------------------------------------------------------------
# Pure fake builders
# ---------------------------------------------------------------------------


def _live_input(
    *,
    candidate_id: str,
    token_mint: str,
    tier_token: Optional[str],
    drawdown_from_ath: object,
    migration_status: Optional[str],
    ath_status: Optional[str],
) -> Stage30_9_3LiveGateInput:
    """Build a fake assembled live candidate. All non-isolated signals default
    to the fully-present, dip-eligible shape so each fake candidate isolates
    exactly one rule. Pure; no I/O, no clock, no provider call.
    """
    return Stage30_9_3LiveGateInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        tier_token=tier_token,
        drawdown_from_ath=drawdown_from_ath,  # type: ignore[arg-type]
        migration_status=migration_status,
        ath_status=ath_status,
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref=("ref-" + candidate_id) if candidate_id else None,
        created_at_utc=_DEFAULT_CREATED_AT,
    )


def _tier1_dip() -> Stage30_9_3LiveGateInput:
    return _live_input(
        candidate_id="cand-tier1",
        token_mint="mint-tier1",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _tier2_dip() -> Stage30_9_3LiveGateInput:
    return _live_input(
        candidate_id="cand-tier2",
        token_mint="mint-tier2",
        tier_token="Tier 2",
        drawdown_from_ath=Decimal("0.70"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _tier3_dip() -> Stage30_9_3LiveGateInput:
    return _live_input(
        candidate_id="cand-tier3",
        token_mint="mint-tier3",
        tier_token="Tier 3",
        drawdown_from_ath=Decimal("0.90"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _non_dip_skips() -> Tuple[Stage30_9_3LiveGateInput, ...]:
    """The five deterministic non-dip skips (each isolates one no-send rule)."""
    return (
        # Tier Unknown -> SKIP_BEFORE_DISPATCH.
        _live_input(
            candidate_id="cand-unknown",
            token_mint="mint-unknown",
            tier_token="Tier Unknown",
            drawdown_from_ath=Decimal("0.55"),
            migration_status="PRESENT",
            ath_status="PRESENT",
        ),
        # Tier Not Applicable -> SKIP_BEFORE_DISPATCH.
        _live_input(
            candidate_id="cand-na",
            token_mint="mint-na",
            tier_token="Tier Not Applicable",
            drawdown_from_ath=Decimal("0.55"),
            migration_status="PRESENT",
            ath_status="PRESENT",
        ),
        # missing ATH -> SKIP_BEFORE_DISPATCH.
        _live_input(
            candidate_id="cand-no-ath",
            token_mint="mint-no-ath",
            tier_token="Tier 1",
            drawdown_from_ath=Decimal("0.55"),
            migration_status="PRESENT",
            ath_status="MISSING",
        ),
        # missing migration -> SKIP_BEFORE_DISPATCH.
        _live_input(
            candidate_id="cand-no-migration",
            token_mint="mint-no-migration",
            tier_token="Tier 1",
            drawdown_from_ath=Decimal("0.55"),
            migration_status="MISSING",
            ath_status="PRESENT",
        ),
        # malformed drawdown -> SKIP_BEFORE_DISPATCH (not a confirmed dip).
        _live_input(
            candidate_id="cand-bad-drawdown",
            token_mint="mint-bad-drawdown",
            tier_token="Tier 1",
            drawdown_from_ath="0.55",  # non-Decimal: fails closed.
            migration_status="PRESENT",
            ath_status="PRESENT",
        ),
    )


def _invalid_candidate() -> Stage30_9_3LiveGateInput:
    # invalid candidate_id -> INVALID_INPUT (blank id).
    return _live_input(
        candidate_id="",
        token_mint="mint-invalid",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def default_live_gate_scenario_stream() -> Tuple[Stage30_9_3LiveGateInput, ...]:
    """Build the deterministic nine-candidate default live-gate stream.

    Three eligible dips (Tier 1 / 2 / 3) FIRST, then five non-dip skips, then
    one invalid candidate. Pure; no I/O, no clock, no env.
    """
    return (
        _tier1_dip(),
        _tier2_dip(),
        _tier3_dip(),
        *_non_dip_skips(),
        _invalid_candidate(),
    )


def no_dip_live_gate_scenario_stream() -> Tuple[Stage30_9_3LiveGateInput, ...]:
    """Build the deterministic six-candidate NO-DIP live-gate stream.

    Five non-dip skips + one invalid candidate; NO eligible dip ever appears
    (the ``NO_DIP_FOUND_BUT_SAFE`` shape). Pure; no I/O, no clock, no env.
    """
    return (
        *_non_dip_skips(),
        _invalid_candidate(),
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_stage30_9_3_fake_live_gate_integration_proof(
    *,
    live_inputs: Tuple[Stage30_9_3LiveGateInput, ...],
    max_candidates_evaluated: int,
    max_dispatches: int,
    max_private_discord_sends: int,
    created_at_utc: str = _DEFAULT_CREATED_AT,
    proof_id: str = _DEFAULT_PROOF_ID,
) -> Tuple[
    Tuple[Stage30_9_3LiveGateDecision, ...],
    Stage30_9_3LiveGateIntegrationResult,
    int,
]:
    """Run the Stage 30.9.3 orchestrator over ``live_inputs`` with an in-memory
    recording sink and return ``(decisions, result, dispatch_sink_call_count)``.

    Pure / deterministic; reads no clock, no env, no network; never sends
    Discord, never calls a live provider, never reserves a real dispatch,
    never writes a file. The returned ``dispatch_sink_call_count`` is the
    number of times the orchestrator handed an eligible dip to the in-memory
    sink (always == ``result.would_send_private_discord_count``).
    """
    sink = Stage30_9_3RecordingDispatchSink()
    decisions, result = run_dip_filtered_live_gate_integration(
        live_inputs=live_inputs,
        dispatch_sink=sink,
        max_candidates_evaluated=max_candidates_evaluated,
        max_dispatches=max_dispatches,
        max_private_discord_sends=max_private_discord_sends,
        created_at_utc=created_at_utc,
        proof_id=proof_id,
    )
    return decisions, result, sink.call_count


def run_stage30_9_3_full_gate_classification_proof(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_9_3LiveGateDecision, ...],
    Stage30_9_3LiveGateIntegrationResult,
    int,
]:
    """Run the full nine-candidate stream with caps high enough to evaluate
    every candidate (no early cap stop).

    Proves the seam's end-to-end classification: three eligible dips PASS (and
    drive three sink calls), five non-dips are suppressed BEFORE reservation,
    one invalid is suppressed -- with zero dispatch failures / transport vetoes
    / ``PAYLOAD_REFUSED`` uses. Pure / deterministic; offline only.
    """
    return run_stage30_9_3_fake_live_gate_integration_proof(
        live_inputs=default_live_gate_scenario_stream(),
        max_candidates_evaluated=16,
        max_dispatches=9,
        max_private_discord_sends=9,
        created_at_utc=created_at_utc,
    )


def run_stage30_9_3_dip_present_controlled_proof(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_9_3LiveGateDecision, ...],
    Stage30_9_3LiveGateIntegrationResult,
    int,
]:
    """Run the nine-candidate stream under the CONTROLLED ceremony caps
    (``max_dispatches=1`` / ``max_private_discord_sends=1``).

    Proves the ``DISPATCHED_OK`` shape: the first eligible dip reserves exactly
    one dispatch, drives exactly one sink call, and the run stops -- no second
    dispatch. Pure / deterministic; offline only.
    """
    return run_stage30_9_3_fake_live_gate_integration_proof(
        live_inputs=default_live_gate_scenario_stream(),
        max_candidates_evaluated=16,
        max_dispatches=1,
        max_private_discord_sends=1,
        created_at_utc=created_at_utc,
    )


def run_stage30_9_3_no_dip_controlled_proof(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_9_3LiveGateDecision, ...],
    Stage30_9_3LiveGateIntegrationResult,
    int,
]:
    """Run the NO-DIP stream under the CONTROLLED ceremony caps.

    Proves the ``NO_DIP_FOUND_BUT_SAFE`` shape: no eligible dip appears, so no
    dispatch is reserved and the sink is never called; every candidate is
    suppressed BEFORE reservation, and zero dispatch failures / transport
    vetoes / ``PAYLOAD_REFUSED`` uses are recorded. Pure / deterministic;
    offline only.
    """
    return run_stage30_9_3_fake_live_gate_integration_proof(
        live_inputs=no_dip_live_gate_scenario_stream(),
        max_candidates_evaluated=16,
        max_dispatches=1,
        max_private_discord_sends=1,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_9_3RecordingDispatchSink",
    "default_live_gate_scenario_stream",
    "no_dip_live_gate_scenario_stream",
    "run_stage30_9_3_fake_live_gate_integration_proof",
    "run_stage30_9_3_full_gate_classification_proof",
    "run_stage30_9_3_dip_present_controlled_proof",
    "run_stage30_9_3_no_dip_controlled_proof",
)
