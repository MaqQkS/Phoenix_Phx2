"""Stage 30.11.1 offline live-candidate assembly bridge.

The pure, offline ASSEMBLY BRIDGE that converts an already-assembled live
candidate / context snapshot into the committed Stage 30.9.3 live gate input
the dip gate consumes:

    a Stage 30.11 ``Stage30_11LiveCandidateSnapshot`` (already assembled)
      -> validate the candidate identity (fail closed on a blank id / mint)
      -> require the migration / ATH / current-market context present
         (else a clean skip; there is no assembled context to gate)
      -> map the already-present fields ONE-TO-ONE onto a committed Stage
         30.9.3 ``Stage30_9_3LiveGateInput`` (NO provider call, NO fabrication)
      -> a Stage 30.11 ``Stage30_11BridgeResult``

This bridge is the missing link the prior controlled live ceremony lacked: a
COMMITTED mapping from a real assembled live candidate / context record into
the committed Stage 30.9.3 ``Stage30_9_3LiveGateInput`` -- so the later
operator-authorized ceremony composes committed + tested code instead of
improvising a scratch runner. It ONLY assembles the gate input; it NEVER runs
the dip gate, NEVER decides dip eligibility (that is the committed Stage 30.9.3
seam's job, run LATER), NEVER reserves a dispatch, NEVER calls a dispatch sink,
and NEVER sends Discord.

The bridge NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (both timestamps
are caller-injected), NEVER sends Discord, NEVER reserves / performs a
dispatch, NEVER performs a transport-layer veto, NEVER writes a file, and edits
NO Stage 28 / Stage 29 / Stage 30.3 / Stage 30.4 production file. It composes
exactly one committed surface -- the Stage 30.9.3 ``Stage30_9_3LiveGateInput``
model -- and nothing more.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.11.1 bridge models sibling + the committed Stage
    30.9.3 ``Stage30_9_3LiveGateInput`` model. No other PHX2 module; no Stage
    21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (timestamps are caller-injected).
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_INVALID_FIELD_SHAPE,
    BRIDGE_REASON_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_READY_FOR_DIP_GATE,
    Stage30_11BridgeResult,
    Stage30_11LiveCandidateSnapshot,
    is_context_present,
    is_nonblank_str,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11LiveCandidateBridgeError(Exception):
    """Closed-set Stage 30.11.1 live-candidate bridge error.

    Raised ONLY for a caller-shape failure the bridge cannot map (a
    ``candidate`` that is not a ``Stage30_11LiveCandidateSnapshot`` -- there is
    no assembled candidate to bridge). Degraded / malformed field VALUES never
    raise; a blank candidate id / token mint fails closed to an
    ``INVALID_BRIDGE_INPUT`` result, and missing context fails closed to a
    ``SKIPPED_MISSING_REQUIRED_CONTEXT`` result. Carries only a closed-set
    reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.1 live candidate bridge error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers: result builders
# ---------------------------------------------------------------------------


def _result(
    candidate: Stage30_11LiveCandidateSnapshot,
    decision: str,
    reason: str,
    live_gate_input,
    created_at_utc: str,
) -> Stage30_11BridgeResult:
    """Build a bridge result echoing ``candidate``'s identity with the given
    ``decision`` / ``reason`` / ``live_gate_input``. Pure; no I/O.
    """
    return Stage30_11BridgeResult(
        candidate_id=candidate.candidate_id,
        token_mint=candidate.token_mint,
        bridge_decision=decision,
        bridge_reason=reason,
        live_gate_input=live_gate_input,
        created_at_utc=created_at_utc,
    )


def _has_required_context(
    candidate: Stage30_11LiveCandidateSnapshot,
) -> bool:
    """Return ``True`` iff the candidate carries the required migration / ATH /
    current-market context (each status token exactly PRESENT).

    Pure / total; never raises. The bridge requires all three contexts present
    to assemble a gate input; a missing / degraded context fails closed to a
    clean skip (there is no assembled context to gate). This is the structural
    presence check ONLY -- whether the candidate is an eligible DIP is decided
    LATER by the committed Stage 30.9.3 seam, never here.
    """
    return (
        is_context_present(candidate.migration_status)
        and is_context_present(candidate.ath_status)
        and is_context_present(candidate.market_context_status)
    )


# ---------------------------------------------------------------------------
# Public bridge
# ---------------------------------------------------------------------------


def build_stage30_9_3_live_gate_input_from_candidate(
    candidate: Stage30_11LiveCandidateSnapshot,
    *,
    created_at_utc: str,
) -> Stage30_11BridgeResult:
    """Bridge ONE already-assembled live candidate snapshot into a committed
    Stage 30.9.3 live gate input.

    Pure / deterministic / no I/O, no provider call, no Discord send, no env
    read, no dispatch reservation. Decision precedence (top-down, first match
    wins):

      1. ``candidate`` is not a ``Stage30_11LiveCandidateSnapshot``  -> raise
         ``Stage30_11LiveCandidateBridgeError`` (a caller-shape failure: there
         is no assembled candidate to bridge).
      2. blank ``candidate_id`` / ``token_mint``  -> ``INVALID_BRIDGE_INPUT`` /
         ``INVALID_FIELD_SHAPE`` (``live_gate_input`` is ``None``).
      3. migration / ATH / current-market context not all PRESENT  ->
         ``SKIPPED_MISSING_REQUIRED_CONTEXT`` / ``MISSING_REQUIRED_CONTEXT``
         (``live_gate_input`` is ``None``).
      4. otherwise  -> ``BRIDGED_TO_LIVE_GATE_INPUT`` / ``READY_FOR_DIP_GATE``,
         with ``live_gate_input`` a committed Stage 30.9.3
         ``Stage30_9_3LiveGateInput`` assembled from the candidate's already-
         present fields.

    The mapping is one-to-one and fabricates nothing: ``tier_hint`` ->
    ``tier_token`` (the committed gate classifies the tier; the bridge computes
    none), ``source_ref`` -> ``candidate_ref``, and the candidate's own
    ``created_at_utc`` -> the gate input's ``created_at_utc`` (the gate evaluates
    the candidate AS ASSEMBLED). The ``created_at_utc`` keyword stamps the
    bridge RESULT (when the bridge ran); both are caller-injected, never a
    wall-clock read.

    The bridge does NOT run the dip gate over the built input, does NOT reserve
    a dispatch, and does NOT call any dispatch sink -- a downstream caller runs
    the committed Stage 30.9.3 ``evaluate_dip_filtered_live_gate`` later.
    """
    # ---- Caller-shape guard: must have an assembled candidate to bridge ----
    if not isinstance(candidate, Stage30_11LiveCandidateSnapshot):
        raise Stage30_11LiveCandidateBridgeError(
            "INVALID_CANDIDATE_RECORD_TYPE"
        )

    # ---- Invalid candidate identity -> fail closed (no gate input) ----
    if not is_nonblank_str(candidate.candidate_id) or not is_nonblank_str(
        candidate.token_mint
    ):
        return _result(
            candidate,
            BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
            BRIDGE_REASON_INVALID_FIELD_SHAPE,
            None,
            created_at_utc,
        )

    # ---- Missing required context -> clean skip (no gate input) ----
    if not _has_required_context(candidate):
        return _result(
            candidate,
            BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
            BRIDGE_REASON_MISSING_REQUIRED_CONTEXT,
            None,
            created_at_utc,
        )

    # ---- Assemble the committed Stage 30.9.3 live gate input ----
    #
    # One-to-one mapping of already-present fields; no provider call, no
    # fabrication. The gate input carries the candidate's OWN assembled-context
    # timestamp (the gate evaluates the candidate as assembled); the dip
    # decision is made LATER by the committed Stage 30.9.3 seam, not here.
    live_gate_input = Stage30_9_3LiveGateInput(
        candidate_id=candidate.candidate_id,
        token_mint=candidate.token_mint,
        tier_token=candidate.tier_hint,
        drawdown_from_ath=candidate.drawdown_from_ath,
        migration_status=candidate.migration_status,
        ath_status=candidate.ath_status,
        market_context_status=candidate.market_context_status,
        current_market_cap_usd=candidate.current_market_cap_usd,
        post_migration_ath_verified=candidate.post_migration_ath_verified,
        candidate_ref=candidate.source_ref,
        created_at_utc=candidate.created_at_utc,
    )
    return _result(
        candidate,
        BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
        BRIDGE_REASON_READY_FOR_DIP_GATE,
        live_gate_input,
        created_at_utc,
    )


__all__ = (
    "Stage30_11LiveCandidateBridgeError",
    "build_stage30_9_3_live_gate_input_from_candidate",
)
