"""Stage 30.11.2 offline runtime gate seam.

The pure, bounded, fail-closed RUNTIME SEAM that composes the committed live
surfaces behind the committed dip gate over a stream of already-assembled live
candidate snapshots:

    a stream of Stage 30.11 ``Stage30_11LiveCandidateSnapshot`` (already
    assembled)
      -> the Stage 30.11.1 bridge (per candidate) -> a committed Stage 30.9.3
         ``Stage30_9_3LiveGateInput`` (or a clean skip / invalid)
      -> the committed Stage 30.9.3 dip-filtered live gate (per bridged input)
      -> the INJECTED fake dispatch sink ONLY when the gate ruled
         ``PASS_TO_DISPATCH``
      -> a tuple of Stage 30.11.2 ``Stage30_11RuntimeGateCandidateOutcome`` plus
         a rolled-up ``Stage30_11RuntimeGateSummary``

This is the Stage 30.11.2 runtime seam: it adds the wall-clock
``max_runtime_seconds`` bound the bounded session lacked (measured via an
INJECTED clock callable, never a wall-clock read here), composes with the
``max_candidates`` / ``max_dispatches`` count bounds, and proves -- with fakes
only -- that the injected dispatch sink is reachable ONLY behind a committed dip
gate ``PASS_TO_DISPATCH``. There is NO other call site for the sink: a bridge
skip / invalid, a non-dip gate skip, a non-conforming stream item, and every
cap / runtime stop all suppress cleanly BEFORE the sink.

The seam NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER reads a wall clock (``now_seconds`` is
injected; both timestamps are caller-injected), NEVER sends Discord, NEVER
reserves a REAL dispatch / performs a real send, NEVER imports a real Discord /
webhook / transport path, NEVER performs a transport-layer veto, NEVER writes a
file, runs NO daemon / background loop / autorestart, and edits NO Stage 28 /
Stage 29 / Stage 30.3 / Stage 30.4 production file. It composes the committed
Stage 30.11.1 bridge + the committed Stage 30.9.3 dip gate (the permitted Stage
30.11 scope expansion) and an injected fake sink; nothing more.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.2 models sibling + the committed Stage 30.11.1
    bridge / bridge-models siblings + the committed Stage 30.9.3 dip-gate
    adapter / gate-models siblings + the committed Stage 30.10.2 gate-decision
    token. No other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport
    import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; the runtime clock is
    injected and timestamps are caller-injected.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Iterable, List, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
    evaluate_dip_filtered_live_gate,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_PASS_TO_DISPATCH,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge import (
    build_stage30_9_3_live_gate_input_from_candidate,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    Stage30_11LiveCandidateSnapshot,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
    RUNTIME_DECISION_INVALID_RUNTIME_INPUT,
    RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP,
    RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP,
    RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS,
    RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
    RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID,
    RUNTIME_REASON_CANDIDATE_CAP_REACHED,
    RUNTIME_REASON_DIP_GATE_SKIPPED,
    RUNTIME_REASON_DISPATCH_CAP_REACHED,
    RUNTIME_REASON_INVALID_CONFIG_OR_INPUT,
    RUNTIME_REASON_PASS_TO_FAKE_DISPATCH,
    RUNTIME_REASON_RUNTIME_SECONDS_REACHED,
    STAGE30_11_2_NOT_EVALUATED,
    Stage30_11FakeDispatchResult,
    Stage30_11RuntimeGateCandidateOutcome,
    Stage30_11RuntimeGateConfig,
    Stage30_11RuntimeGateSummary,
    is_valid_runtime_gate_config,
)


# The injected fake dispatch sink: a callable that, given the bridged committed
# Stage 30.9.3 live gate input of a gate-PASS candidate, returns a
# ``Stage30_11FakeDispatchResult`` ack. In tests this is an in-memory recording
# fake; the real private compact dispatch path is a SEPARATE, operator-
# authorized step Stage 30.11.2 does not build. The seam calls it ONLY inside
# the gate-PASS branch.
Stage30_11FakeDispatchSink = Callable[
    [Stage30_9_3LiveGateInput], Stage30_11FakeDispatchResult
]


# The injected runtime clock: a zero-arg callable returning the current
# wall-clock reading in seconds (a ``Decimal`` in the fakes; an ``int`` also
# works). The seam samples it to enforce ``max_runtime_seconds`` and NEVER reads
# a wall clock of its own.
Stage30_11RuntimeClock = Callable[[], Decimal]


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11RuntimeGateError(Exception):
    """Closed-set Stage 30.11.2 runtime gate seam error.

    Raised ONLY for a caller-shape failure the seam cannot run with -- an
    invalid runtime config (``is_valid_runtime_gate_config`` is ``False``): a
    non-positive ``max_runtime_seconds`` / ``max_candidates`` or a negative
    ``max_dispatches`` would make the bounded run undefined, so the seam fails
    closed BEFORE touching the stream, the bridge, the gate, or the dispatch
    sink. Degraded / malformed per-candidate VALUES never raise; a non-conforming
    stream item fails closed to an ``INVALID_RUNTIME_INPUT`` outcome. Carries
    only a closed-set reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.2 runtime gate error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _safe_ids(candidate: object) -> Tuple[str, str]:
    """Return ``(candidate_id, token_mint)`` for ``candidate`` if it is a
    snapshot, else ``("", "")``. Pure / total; never raises, never reads an
    arbitrary object's attributes unsafely.
    """
    if isinstance(candidate, Stage30_11LiveCandidateSnapshot):
        return candidate.candidate_id, candidate.token_mint
    return "", ""


def _outcome(
    candidate: object,
    *,
    bridge_decision: str,
    gate_decision: str,
    runtime_decision: str,
    runtime_reason: str,
    dispatch_attempted: bool,
    dispatch_accepted: bool,
    created_at_utc: str,
) -> Stage30_11RuntimeGateCandidateOutcome:
    """Build a runtime outcome echoing ``candidate``'s safe-shape identity with
    the given closed-set decision / reason and dispatch flags. Pure; no I/O.
    """
    candidate_id, token_mint = _safe_ids(candidate)
    return Stage30_11RuntimeGateCandidateOutcome(
        candidate_id=candidate_id,
        token_mint=token_mint,
        bridge_decision=bridge_decision,
        gate_decision=gate_decision,
        runtime_decision=runtime_decision,
        runtime_reason=runtime_reason,
        dispatch_attempted=dispatch_attempted,
        dispatch_accepted=dispatch_accepted,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public runtime seam
# ---------------------------------------------------------------------------


def run_stage30_11_runtime_gate_seam(
    candidates: Iterable[Stage30_11LiveCandidateSnapshot],
    *,
    config: Stage30_11RuntimeGateConfig,
    dispatch_sink: Stage30_11FakeDispatchSink,
    now_seconds: Stage30_11RuntimeClock,
    created_at_utc: str,
) -> Tuple[
    Tuple[Stage30_11RuntimeGateCandidateOutcome, ...],
    Stage30_11RuntimeGateSummary,
]:
    """Run one bounded, offline runtime gate pass over a candidate stream and
    return ``(outcomes, summary)``.

    Pure / deterministic / no I/O, no provider call, no Discord send, no env
    read, no wall-clock read (``now_seconds`` is injected). The seam returns the
    ordered per-candidate outcomes (mirroring the committed Stage 30.9.3
    orchestrator's ``(decisions, result)`` shape) plus a rolled-up
    ``Stage30_11RuntimeGateSummary``.

    Fail closed first: if ``config`` is not a valid
    ``Stage30_11RuntimeGateConfig`` the seam raises
    ``Stage30_11RuntimeGateError`` BEFORE touching the stream, the bridge, the
    gate, or the dispatch sink -- nothing is dispatched on an invalid config.

    For each candidate (top-down, first match wins), with ``start`` sampled from
    the injected clock once before the loop:

      1. ``now_seconds() - start >= max_runtime_seconds`` -> record the cut-off
         candidate as ``STOPPED_BY_RUNTIME_SECONDS`` and stop.
      2. ``candidates_seen >= max_candidates`` -> record the cut-off candidate as
         ``STOPPED_BY_CANDIDATE_CAP`` and stop.
      3. ``dispatch_attempted >= max_dispatches`` -> record the cut-off candidate
         as ``STOPPED_BY_DISPATCH_CAP`` and stop.
      4. a non-conforming stream item (not a ``Stage30_11LiveCandidateSnapshot``)
         -> ``INVALID_RUNTIME_INPUT`` (no bridge / gate / sink).
      5. the Stage 30.11.1 bridge skips / fails closed -> ``SUPPRESSED_BY_BRIDGE``
         (no gate / sink; an ``INVALID_BRIDGE_INPUT`` also counts as an invalid
         input).
      6. the committed dip gate does NOT rule ``PASS_TO_DISPATCH`` ->
         ``SUPPRESSED_BY_DIP_GATE`` (no sink).
      7. the committed dip gate rules ``PASS_TO_DISPATCH`` -> call the INJECTED
         ``dispatch_sink`` (the ONLY sink call site) ->
         ``DISPATCHED_AFTER_DIP_GATE_PASS``.

    A cap / runtime cut-off candidate is recorded as a STOPPED outcome and is
    NOT counted in ``candidates_seen`` (it was never evaluated). No exception
    escapes for a normal per-candidate validation failure; the seam uses closed
    outcomes for those. The dispatch / candidate / runtime caps each stop the run
    cleanly with no daemon, no retry, no background loop.
    """
    if not is_valid_runtime_gate_config(config):
        # Fail closed on an invalid config: dispatch nothing, gate nothing,
        # bridge nothing. This is a caller-shape failure, not a per-candidate
        # validation failure.
        raise Stage30_11RuntimeGateError(RUNTIME_REASON_INVALID_CONFIG_OR_INPUT)

    outcomes: List[Stage30_11RuntimeGateCandidateOutcome] = []

    seen = 0
    bridged = 0
    gate_passed = 0
    dispatch_attempted = 0
    dispatch_accepted = 0
    suppressed_by_bridge = 0
    suppressed_by_gate = 0
    invalid_inputs = 0
    stopped_by_candidate_cap = 0
    stopped_by_dispatch_cap = 0
    stopped_by_runtime_seconds = 0

    # Sample the injected clock once before the loop; all elapsed checks are
    # relative to this start. The seam reads NO wall clock of its own.
    start_seconds = now_seconds()

    for candidate in candidates:
        # ---- 1. Wall-clock runtime bound (injected clock only) ----
        if (now_seconds() - start_seconds) >= config.max_runtime_seconds:
            outcomes.append(
                _outcome(
                    candidate,
                    bridge_decision=STAGE30_11_2_NOT_EVALUATED,
                    gate_decision=STAGE30_11_2_NOT_EVALUATED,
                    runtime_decision=RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS,
                    runtime_reason=RUNTIME_REASON_RUNTIME_SECONDS_REACHED,
                    dispatch_attempted=False,
                    dispatch_accepted=False,
                    created_at_utc=created_at_utc,
                )
            )
            stopped_by_runtime_seconds = 1
            break

        # ---- 2. Candidate cap ----
        if seen >= config.max_candidates:
            outcomes.append(
                _outcome(
                    candidate,
                    bridge_decision=STAGE30_11_2_NOT_EVALUATED,
                    gate_decision=STAGE30_11_2_NOT_EVALUATED,
                    runtime_decision=RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP,
                    runtime_reason=RUNTIME_REASON_CANDIDATE_CAP_REACHED,
                    dispatch_attempted=False,
                    dispatch_accepted=False,
                    created_at_utc=created_at_utc,
                )
            )
            stopped_by_candidate_cap = 1
            break

        # ---- 3. Dispatch cap ----
        if dispatch_attempted >= config.max_dispatches:
            outcomes.append(
                _outcome(
                    candidate,
                    bridge_decision=STAGE30_11_2_NOT_EVALUATED,
                    gate_decision=STAGE30_11_2_NOT_EVALUATED,
                    runtime_decision=RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP,
                    runtime_reason=RUNTIME_REASON_DISPATCH_CAP_REACHED,
                    dispatch_attempted=False,
                    dispatch_accepted=False,
                    created_at_utc=created_at_utc,
                )
            )
            stopped_by_dispatch_cap = 1
            break

        # ---- This candidate is evaluated ----
        seen += 1

        # ---- 4. Non-conforming stream item -> fail closed (no bridge) ----
        if not isinstance(candidate, Stage30_11LiveCandidateSnapshot):
            invalid_inputs += 1
            outcomes.append(
                _outcome(
                    candidate,
                    bridge_decision=STAGE30_11_2_NOT_EVALUATED,
                    gate_decision=STAGE30_11_2_NOT_EVALUATED,
                    runtime_decision=RUNTIME_DECISION_INVALID_RUNTIME_INPUT,
                    runtime_reason=RUNTIME_REASON_INVALID_CONFIG_OR_INPUT,
                    dispatch_attempted=False,
                    dispatch_accepted=False,
                    created_at_utc=created_at_utc,
                )
            )
            continue

        # ---- 5. Stage 30.11.1 bridge ----
        bridge_result = build_stage30_9_3_live_gate_input_from_candidate(
            candidate, created_at_utc=created_at_utc
        )
        if (
            bridge_result.bridge_decision
            != BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
        ):
            # The bridge skipped (missing context) or failed closed (invalid
            # identity): there is no gate input, so the candidate is suppressed
            # BEFORE the gate and BEFORE the sink.
            suppressed_by_bridge += 1
            if (
                bridge_result.bridge_decision
                == BRIDGE_DECISION_INVALID_BRIDGE_INPUT
            ):
                invalid_inputs += 1
            outcomes.append(
                _outcome(
                    candidate,
                    bridge_decision=bridge_result.bridge_decision,
                    gate_decision=STAGE30_11_2_NOT_EVALUATED,
                    runtime_decision=RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
                    runtime_reason=RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID,
                    dispatch_attempted=False,
                    dispatch_accepted=False,
                    created_at_utc=created_at_utc,
                )
            )
            continue

        # ---- 6. Committed Stage 30.9.3 dip-filtered live gate ----
        bridged += 1
        live_gate_input = bridge_result.live_gate_input
        gate_decision = evaluate_dip_filtered_live_gate(live_gate_input)
        if gate_decision.gate_decision != GATE_DECISION_PASS_TO_DISPATCH:
            # A normal non-dip skip (or any non-PASS verdict) is suppressed
            # cleanly BEFORE the dispatch sink; it is NEVER a dispatch failure
            # and NEVER a transport veto.
            suppressed_by_gate += 1
            outcomes.append(
                _outcome(
                    candidate,
                    bridge_decision=bridge_result.bridge_decision,
                    gate_decision=gate_decision.gate_decision,
                    runtime_decision=RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
                    runtime_reason=RUNTIME_REASON_DIP_GATE_SKIPPED,
                    dispatch_attempted=False,
                    dispatch_accepted=False,
                    created_at_utc=created_at_utc,
                )
            )
            continue

        # ---- 7. Gate PASS -> the ONLY injected-sink call site ----
        gate_passed += 1
        dispatch_attempted += 1
        result = dispatch_sink(live_gate_input)
        accepted = (
            bool(result.accepted)
            if isinstance(result, Stage30_11FakeDispatchResult)
            else False
        )
        if accepted:
            dispatch_accepted += 1
        outcomes.append(
            _outcome(
                candidate,
                bridge_decision=bridge_result.bridge_decision,
                gate_decision=gate_decision.gate_decision,
                runtime_decision=(
                    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS
                ),
                runtime_reason=RUNTIME_REASON_PASS_TO_FAKE_DISPATCH,
                dispatch_attempted=True,
                dispatch_accepted=accepted,
                created_at_utc=created_at_utc,
            )
        )

    summary = Stage30_11RuntimeGateSummary(
        candidates_seen=seen,
        bridged=bridged,
        gate_passed=gate_passed,
        dispatch_attempted=dispatch_attempted,
        dispatch_accepted=dispatch_accepted,
        suppressed_by_bridge=suppressed_by_bridge,
        suppressed_by_gate=suppressed_by_gate,
        stopped_by_candidate_cap=stopped_by_candidate_cap,
        stopped_by_dispatch_cap=stopped_by_dispatch_cap,
        stopped_by_runtime_seconds=stopped_by_runtime_seconds,
        invalid_inputs=invalid_inputs,
        created_at_utc=created_at_utc,
    )
    return tuple(outcomes), summary


__all__ = (
    "Stage30_11FakeDispatchSink",
    "Stage30_11RuntimeClock",
    "Stage30_11RuntimeGateError",
    "run_stage30_11_runtime_gate_seam",
)
