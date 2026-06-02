"""Stage 30.11.1 offline fake live-candidate assembly bridge proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.1
live-candidate assembly bridge maps an already-assembled live candidate /
context snapshot onto a committed Stage 30.9.3 ``Stage30_9_3LiveGateInput``,
using fakes / offline snapshots ONLY. It composes the REAL bridge over a
deterministic five-candidate stream and tallies the result:

    a deterministic fake stream of assembled live candidate snapshots
      -> the Stage 30.11.1 bridge (per candidate)
      -> a Stage 30.11.1 ``Stage30_11BridgeResult`` (with a built
         ``Stage30_9_3LiveGateInput`` for the bridged candidates, ``None``
         otherwise)
      -> a rolled-up ``Stage30_11BridgeProofSummary``

An OPTIONAL compatibility proof additionally feeds each BRIDGED candidate's
built ``Stage30_9_3LiveGateInput`` into the committed Stage 30.9.3
``evaluate_dip_filtered_live_gate`` to prove the assembled input is gate-ready
-- WITHOUT reserving a dispatch, calling a dispatch sink, or sending Discord
(it only evaluates the pure gate verdict; the dip decision happens at the gate,
not in the bridge).

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a
dispatch reservation, NOT a transport-layer veto, and NOT a new readiness gate.
It CONSTRUCTS no filesystem I/O, reads no environment, opens no network
connection, and touches no Discord / live provider path.

The deterministic five-candidate default stream isolates exactly one bridge
outcome per candidate:

  1. Tier 1 valid dip-context     -> BRIDGED_TO_LIVE_GATE_INPUT
  2. Tier Unknown non-dip context -> BRIDGED_TO_LIVE_GATE_INPUT
     (note: the NON-DIP decision happens LATER in the Stage 30.9.3 gate, not
     in the bridge -- the bridge only proves the context is assembled)
  3. missing ATH                  -> SKIPPED_MISSING_REQUIRED_CONTEXT
  4. missing migration            -> SKIPPED_MISSING_REQUIRED_CONTEXT
  5. malformed candidate_id       -> INVALID_BRIDGE_INPUT

So the summary has five candidates seen, exactly two bridged, exactly two
skipped for missing context, and exactly one invalid -- and the two bridged
inputs are gate-compatible (the Tier 1 dip would PASS the gate; the Tier
Unknown candidate would SKIP_BEFORE_DISPATCH), with NO dispatch ever reserved.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.1 bridge models + bridge siblings and the
    committed Stage 30.9.3 dip-gate adapter (for the OPTIONAL compatibility
    proof). No other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport
    import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
    evaluate_dip_filtered_live_gate,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateDecision,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge import (
    build_stage30_9_3_live_gate_input_from_candidate,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
    Stage30_11BridgeProofSummary,
    Stage30_11BridgeResult,
    Stage30_11LiveCandidateSnapshot,
)


# The deterministic caller-injected clock for the default scenarios (never a
# wall-clock read). Matches the Stage 30.9.3 / 30.10.2 fake-proof clocks so the
# composed compatibility proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Pure fake builders
# ---------------------------------------------------------------------------


def _snapshot(
    *,
    candidate_id: str,
    token_mint: str,
    tier_hint: Optional[str],
    drawdown_from_ath: object,
    migration_status: Optional[str],
    ath_status: Optional[str],
    market_context_status: Optional[str] = "PRESENT",
    current_market_cap_usd: object = Decimal("12345.67"),
    post_migration_ath_verified: Optional[bool] = True,
) -> Stage30_11LiveCandidateSnapshot:
    """Build a fake already-assembled live candidate snapshot. All non-isolated
    signals default to the fully-present, dip-ready shape so each fake snapshot
    isolates exactly one bridge outcome. Pure; no I/O, no clock, no provider
    call, no fabrication beyond the explicit fake fields.
    """
    return Stage30_11LiveCandidateSnapshot(
        candidate_id=candidate_id,
        token_mint=token_mint,
        pair_type="SOL",
        tier_hint=tier_hint,
        drawdown_from_ath=drawdown_from_ath,  # type: ignore[arg-type]
        migration_status=migration_status,
        ath_status=ath_status,
        market_context_status=market_context_status,
        current_market_cap_usd=current_market_cap_usd,  # type: ignore[arg-type]
        post_migration_ath_verified=post_migration_ath_verified,
        source_ref=("ref-" + candidate_id) if candidate_id else None,
        created_at_utc=_DEFAULT_CREATED_AT,
    )


def _tier1_dip_context() -> Stage30_11LiveCandidateSnapshot:
    # Tier 1 with all context present -> BRIDGED (the gate later PASSES it).
    return _snapshot(
        candidate_id="cand-tier1",
        token_mint="mint-tier1",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _tier_unknown_non_dip_context() -> Stage30_11LiveCandidateSnapshot:
    # Tier Unknown with all context present -> BRIDGED (the gate later SKIPS it
    # as a non-dip; the bridge only proves the context is assembled).
    return _snapshot(
        candidate_id="cand-unknown",
        token_mint="mint-unknown",
        tier_hint="Tier Unknown",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _missing_ath() -> Stage30_11LiveCandidateSnapshot:
    # ATH context not present -> SKIPPED_MISSING_REQUIRED_CONTEXT.
    return _snapshot(
        candidate_id="cand-no-ath",
        token_mint="mint-no-ath",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status=None,
    )


def _missing_migration() -> Stage30_11LiveCandidateSnapshot:
    # Migration context not present -> SKIPPED_MISSING_REQUIRED_CONTEXT.
    return _snapshot(
        candidate_id="cand-no-migration",
        token_mint="mint-no-migration",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status=None,
        ath_status="PRESENT",
    )


def _malformed_candidate_id() -> Stage30_11LiveCandidateSnapshot:
    # Blank candidate_id -> INVALID_BRIDGE_INPUT (every other field present).
    return _snapshot(
        candidate_id="",
        token_mint="mint-invalid",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def default_bridge_scenario_stream() -> (
    Tuple[Stage30_11LiveCandidateSnapshot, ...]
):
    """Build the deterministic five-candidate default bridge stream.

    One valid dip-context candidate, one valid non-dip-context candidate, one
    missing-ATH candidate, one missing-migration candidate, and one malformed
    candidate. Pure; no I/O, no clock, no env.
    """
    return (
        _tier1_dip_context(),
        _tier_unknown_non_dip_context(),
        _missing_ath(),
        _missing_migration(),
        _malformed_candidate_id(),
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_stage30_11_1_fake_bridge_proof(
    *,
    candidates: Optional[
        Tuple[Stage30_11LiveCandidateSnapshot, ...]
    ] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_11BridgeResult, ...],
    Stage30_11BridgeProofSummary,
]:
    """Run the Stage 30.11.1 bridge over ``candidates`` and return
    ``(results, summary)``.

    With ``candidates=None`` the deterministic five-candidate default stream is
    used. Each snapshot is run through the real bridge; the rolled-up
    ``Stage30_11BridgeProofSummary`` tallies seen / bridged / skipped-for-
    missing-context / invalid. Pure / deterministic; reads no clock, no env, no
    network; never runs the dip gate, never reserves a dispatch, never sends
    Discord, never writes a file.
    """
    stream = (
        default_bridge_scenario_stream() if candidates is None else candidates
    )

    results: List[Stage30_11BridgeResult] = []
    bridged = 0
    skipped_missing_context = 0
    invalid_inputs = 0

    for candidate in stream:
        result = build_stage30_9_3_live_gate_input_from_candidate(
            candidate, created_at_utc=created_at_utc
        )
        results.append(result)
        if result.bridge_decision == (
            BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
        ):
            bridged += 1
        elif result.bridge_decision == (
            BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT
        ):
            skipped_missing_context += 1
        elif result.bridge_decision == BRIDGE_DECISION_INVALID_BRIDGE_INPUT:
            invalid_inputs += 1

    summary = Stage30_11BridgeProofSummary(
        candidates_seen=len(results),
        bridged=bridged,
        skipped_missing_context=skipped_missing_context,
        invalid_inputs=invalid_inputs,
        created_at_utc=created_at_utc,
    )
    return tuple(results), summary


def run_stage30_11_1_bridge_then_gate_compatibility_proof(
    *,
    candidates: Optional[
        Tuple[Stage30_11LiveCandidateSnapshot, ...]
    ] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[
        Tuple[Stage30_11BridgeResult, Optional[Stage30_9_3LiveGateDecision]],
        ...,
    ],
    Stage30_11BridgeProofSummary,
]:
    """Run the bridge, then feed each BRIDGED input into the committed Stage
    30.9.3 gate, and return ``(pairs, summary)``.

    For each candidate the bridge result is paired with the committed Stage
    30.9.3 ``Stage30_9_3LiveGateDecision`` obtained by evaluating its built
    ``live_gate_input`` (``None`` for a skipped / invalid candidate, which
    carries no gate input). This PROVES the bridged inputs are gate-compatible
    -- the gate accepts them and rules each verdict -- WITHOUT reserving a
    dispatch, calling any dispatch sink, or sending Discord (it only evaluates
    the pure gate verdict). The dip decision is the GATE's, not the bridge's.
    Pure / deterministic; offline only.
    """
    results, summary = run_stage30_11_1_fake_bridge_proof(
        candidates=candidates,
        created_at_utc=created_at_utc,
    )

    pairs: List[
        Tuple[Stage30_11BridgeResult, Optional[Stage30_9_3LiveGateDecision]]
    ] = []
    for result in results:
        if result.live_gate_input is None:
            pairs.append((result, None))
            continue
        # Evaluate the committed pure dip gate over the bridged input. This
        # returns a verdict ONLY; it reserves no dispatch and calls no sink.
        decision = evaluate_dip_filtered_live_gate(result.live_gate_input)
        pairs.append((result, decision))

    return tuple(pairs), summary


__all__ = (
    "default_bridge_scenario_stream",
    "run_stage30_11_1_fake_bridge_proof",
    "run_stage30_11_1_bridge_then_gate_compatibility_proof",
)
