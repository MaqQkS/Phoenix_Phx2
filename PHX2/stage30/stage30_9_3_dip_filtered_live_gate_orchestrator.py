"""Stage 30.9.3 dip-filtered live gate orchestrator.

The pure, bounded, fail-closed ORCHESTRATOR that drives the dip-filtered live
dispatch integration seam over a stream of assembled live candidates. For each
candidate it runs the Stage 30.9.3 adapter (the committed Stage 30.10 dip-gate
stack) and acts on the verdict:

  * ``PASS_TO_DISPATCH`` (an eligible dip) -- reserve ONE dispatch attempt,
    call the caller-injected dispatch sink (a fake in tests; the real private
    compact dispatch path in the later operator-authorized ceremony), and
    increment the would-send count -- THEN stop once the dispatch / private-
    send cap is reached.
  * ``SKIP_BEFORE_DISPATCH`` (a normal non-dip) -- do NOT reserve a dispatch,
    do NOT call the sink, count it skipped. It is NEVER a dispatch failure.
  * ``INVALID_INPUT`` (or any non-conforming stream item) -- do NOT reserve a
    dispatch, do NOT call the sink, count it invalid. It is NEVER a dispatch
    failure and NEVER reuses ``PAYLOAD_REFUSED``.

The dispatch sink is invoked ONLY inside the ``PASS_TO_DISPATCH`` branch and
ONLY within the dispatch / private-send caps: there is NO bypass path on which
the sink is called for a non-pass candidate. The integration result's
``dispatch_failures_recorded`` / ``transport_veto_count`` /
``payload_refused_count`` are ALWAYS 0 -- this seam gates BEFORE dispatch
reservation and owns no transport-failure accounting.

This is the SAME logic the later controlled live ceremony will reuse; in THIS
slice it is exercised with fakes / offline candidates + an injected fake sink
ONLY. The orchestrator NEVER opens a network connection, NEVER reads the
process environment, NEVER calls ``datetime.now`` (the result timestamp is
caller-injected), NEVER sends Discord, NEVER reserves a REAL dispatch, NEVER
performs a transport-layer veto, NEVER writes a file, and edits NO Stage 28
suppression / Stage 30.3 / Stage 30.4 runtime orchestrator.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.9.3 models + adapter siblings and the committed
    Stage 30.10.2 gate-decision tokens. No other PHX2 module; no Stage 21-29 /
    Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live runner
    / provider / transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (``created_at_utc`` is caller-injected).
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
    evaluate_dip_filtered_live_gate,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateDecision,
    Stage30_9_3LiveGateInput,
    Stage30_9_3LiveGateIntegrationResult,
)
from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    Stage30_10DipEligibilityPolicy,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
)


# The dispatch sink the orchestrator calls for EACH eligible dip that is
# reserved for dispatch. In tests this is an in-memory fake that records the
# decision; in the later operator-authorized ceremony it is the real private
# compact dispatch path. It returns nothing the orchestrator depends on.
DipFilteredDispatchSink = Callable[[Stage30_9_3LiveGateDecision], object]


# The default safe run id stamped onto each candidate's projected Stage
# 30.10.3 artifact (a safe-shape opaque label; never a secret).
STAGE30_9_3_DEFAULT_RUN_PROOF_ID: str = "stage30_9_3_dip_filtered_live_gate_run"


def run_dip_filtered_live_gate_integration(
    *,
    live_inputs: Iterable[Stage30_9_3LiveGateInput],
    dispatch_sink: DipFilteredDispatchSink,
    max_candidates_evaluated: int,
    max_dispatches: int,
    max_private_discord_sends: int,
    created_at_utc: str,
    policy: Optional[Stage30_10DipEligibilityPolicy] = None,
    proof_id: str = STAGE30_9_3_DEFAULT_RUN_PROOF_ID,
) -> Tuple[
    Tuple[Stage30_9_3LiveGateDecision, ...],
    Stage30_9_3LiveGateIntegrationResult,
]:
    """Run one bounded dip-filtered live gate integration over a candidate
    stream.

    Pure / deterministic / no I/O. For each candidate (up to
    ``max_candidates_evaluated``) the dip gate is run; ONLY a
    ``PASS_TO_DISPATCH`` candidate reserves a dispatch attempt and calls
    ``dispatch_sink`` (and only within ``max_dispatches`` /
    ``max_private_discord_sends``); the run stops once the dispatch / private-
    send cap is reached. Every ``SKIP_BEFORE_DISPATCH`` / ``INVALID_INPUT``
    candidate is suppressed cleanly BEFORE reservation -- never reserved, never
    handed to the sink, never counted as a dispatch failure. Returns the
    ordered per-candidate decisions plus a rolled-up
    ``Stage30_9_3LiveGateIntegrationResult`` whose
    ``dispatch_failures_recorded`` / ``transport_veto_count`` /
    ``payload_refused_count`` are always 0. ``created_at_utc`` is the caller-
    injected result timestamp (never a wall-clock read).
    """
    decisions: List[Stage30_9_3LiveGateDecision] = []

    seen = 0
    evaluated = 0
    passed = 0
    skipped = 0
    invalid = 0
    reserved = 0
    would_send = 0

    for live_input in live_inputs:
        # Bounded evaluation cap: stop cleanly once reached.
        if evaluated >= max_candidates_evaluated:
            break
        seen += 1

        # Defensive fail-closed: a non-conforming stream item is counted
        # invalid, never gated to a decision, never reserved, never dispatched.
        if not isinstance(live_input, Stage30_9_3LiveGateInput):
            evaluated += 1
            invalid += 1
            continue

        evaluated += 1
        decision = evaluate_dip_filtered_live_gate(
            live_input, policy=policy, proof_id=proof_id
        )
        decisions.append(decision)

        if decision.gate_decision == GATE_DECISION_PASS_TO_DISPATCH:
            passed += 1
            # ONLY an eligible dip may reserve a dispatch / call the sink, and
            # only within the dispatch + private-send caps. There is no other
            # call site for the sink in this orchestrator.
            if (
                reserved < max_dispatches
                and would_send < max_private_discord_sends
            ):
                reserved += 1
                dispatch_sink(decision)
                would_send += 1
                # Stop once the dispatch / private-send cap is reached.
                if (
                    reserved >= max_dispatches
                    or would_send >= max_private_discord_sends
                ):
                    break
            else:
                # Dispatch / private-send cap already reached: stop cleanly.
                break
        elif decision.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH:
            # A normal non-dip skip: suppressed BEFORE reservation. NOT a
            # dispatch failure, NOT a transport veto, NOT PAYLOAD_REFUSED.
            skipped += 1
        else:
            # GATE_DECISION_INVALID_INPUT (or any unrecognized decision -> fail
            # closed into invalid). Never reserved, never dispatched.
            invalid += 1

    result = Stage30_9_3LiveGateIntegrationResult(
        candidates_seen=seen,
        candidates_evaluated=evaluated,
        candidates_passed_gate=passed,
        candidates_skipped_before_dispatch=skipped,
        invalid_inputs=invalid,
        dispatch_attempts_reserved=reserved,
        # This seam gates BEFORE dispatch reservation; it records no dispatch
        # failure, no transport veto, and no PAYLOAD_REFUSED for any candidate.
        dispatch_failures_recorded=0,
        transport_veto_count=0,
        payload_refused_count=0,
        would_send_private_discord_count=would_send,
        created_at_utc=created_at_utc,
    )
    return tuple(decisions), result


__all__ = (
    "DipFilteredDispatchSink",
    "STAGE30_9_3_DEFAULT_RUN_PROOF_ID",
    "run_dip_filtered_live_gate_integration",
)
