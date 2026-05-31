"""Stage 30.10.2 optional pre-dispatch tier-dip gate.

Pure, offline gate that wraps the Stage 30.10.1 eligibility classifier and
decides, per candidate, whether it may proceed to dispatch reservation /
the private send. The gate is evaluated BEFORE dispatch reservation: a
non-dip candidate is skipped cleanly here, so it never becomes a dispatch
attempt; an eligible dip passes through unchanged.

The gate is a thin PLACEMENT layer; it owns NO eligibility logic of its own.
It maps the Stage 30.10.1 classifier's eight closed-set decisions onto the
three Stage 30.10.2 gate decisions:

  * a true ``ELIGIBLE_DIP`` (``send_allowed=True``)
        -> ``PASS_TO_DISPATCH`` / ``ELIGIBLE_DIP`` (the candidate may proceed
           to dispatch reservation);
  * any classifier no-send skip (``SKIPPED_*``)
        -> ``SKIP_BEFORE_DISPATCH`` / ``NOT_DIP`` (a NORMAL no-send: the
           candidate is suppressed BEFORE reservation, is NOT counted as a
           dispatch failure, does NOT use a transport veto, and does NOT
           return ``PAYLOAD_REFUSED``);
  * an ``INVALID_INPUT`` classification, or a malformed gate envelope
        -> ``INVALID_INPUT`` / ``INVALID_GATE_INPUT`` (fail closed; the
           candidate never proceeds to reservation).

``PASS_TO_DISPATCH`` is reachable ONLY for a classifier ``ELIGIBLE_DIP``;
no no-send candidate can pass, and no skipped candidate is counted as a
dispatch failure.

The gate NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (the clock is
caller-injected on the input), NEVER sends Discord, NEVER reserves a real
dispatch / performs a real send, NEVER performs a transport-layer veto, and
NEVER wires into the live runtime / Stage 28 suppression / Stage 30.3 /
Stage 30.4 orchestrators. Stage 30.10.2 is fake / offline only; nothing
existing imports it.

Deterministic decision precedence (top-down, first match wins):

  1. ``input_record`` is not a ``Stage30_10PreDispatchGateInput``  -> raise
     ``Stage30_10PreDispatchGateError`` (a caller-shape failure: there is no
     gate envelope to echo).
  2. blank gate ``candidate_id``   -> ``INVALID_INPUT`` /
     ``INVALID_GATE_INPUT`` (eligibility echo ``INVALID_INPUT`` /
     ``INVALID_CANDIDATE_ID``).
  3. blank gate ``token_mint``     -> ``INVALID_INPUT`` /
     ``INVALID_GATE_INPUT`` (eligibility echo ``INVALID_INPUT`` /
     ``INVALID_TOKEN_MINT``).
  4. unsafe gate ``created_at_utc`` -> ``INVALID_INPUT`` /
     ``INVALID_GATE_INPUT`` (eligibility echo ``INVALID_INPUT`` /
     ``INVALID_CREATED_AT_UTC``).
  5. ``eligibility_input`` is not a ``Stage30_10DipEligibilityInput``
     -> ``INVALID_INPUT`` / ``INVALID_GATE_INPUT`` (eligibility echo
     ``INVALID_INPUT`` / ``INVALID_CANDIDATE_ID``); the classifier is not
     consulted (there is no input to classify).
  6. classify the ``eligibility_input``:
       * classifier ``INVALID_INPUT``  -> ``INVALID_INPUT`` /
         ``INVALID_GATE_INPUT``;
       * classifier ``send_allowed``   -> ``PASS_TO_DISPATCH`` /
         ``ELIGIBLE_DIP``;
       * any other classifier no-send  -> ``SKIP_BEFORE_DISPATCH`` /
         ``NOT_DIP``.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.10.2 gate-models sibling + the Stage 30.10.1
    models + classifier siblings (no other PHX2 module; no Stage 21-29 /
    Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / transport import).
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (``created_at_utc`` is caller-injected).
"""

from __future__ import annotations

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier import (
    classify_tier_dip_eligibility,
)
from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    DECISION_INVALID_INPUT,
    DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY,
    REASON_INVALID_CANDIDATE_ID,
    REASON_INVALID_CREATED_AT_UTC,
    REASON_INVALID_TOKEN_MINT,
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
    is_safe_created_at_utc,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    GATE_REASON_ELIGIBLE_DIP,
    GATE_REASON_INVALID_GATE_INPUT,
    GATE_REASON_NOT_DIP,
    Stage30_10PreDispatchGateInput,
    Stage30_10PreDispatchGateRecord,
)


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_10PreDispatchGateError(Exception):
    """Closed-set Stage 30.10.2 pre-dispatch gate error.

    Raised ONLY for a caller-shape failure the gate cannot classify (an
    ``input_record`` that is not a ``Stage30_10PreDispatchGateInput`` --
    there is no gate envelope to echo). Degraded / invalid input VALUES
    never raise; they fail closed to an ``INVALID_INPUT`` gate record.
    Carries only a closed-set reason token; never a raw payload or any
    secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.10.2 pre-dispatch gate error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string."""
    return isinstance(value, str) and value.strip() != ""


def _record(
    input_record: Stage30_10PreDispatchGateInput,
    *,
    eligibility_decision: str,
    eligibility_reason: str,
    send_allowed: bool,
    gate_decision: str,
    gate_reason: str,
) -> Stage30_10PreDispatchGateRecord:
    """Build a gate record echoing ``input_record``'s identity / clock with
    the given eligibility + gate decision / reason. Pure; no I/O.
    """
    return Stage30_10PreDispatchGateRecord(
        candidate_id=input_record.candidate_id,
        token_mint=input_record.token_mint,
        eligibility_decision=eligibility_decision,
        eligibility_reason=eligibility_reason,
        send_allowed=send_allowed,
        gate_decision=gate_decision,
        gate_reason=gate_reason,
        created_at_utc=input_record.created_at_utc,
    )


def _invalid(
    input_record: Stage30_10PreDispatchGateInput,
    eligibility_reason: str,
) -> Stage30_10PreDispatchGateRecord:
    """Build an ``INVALID_INPUT`` / ``INVALID_GATE_INPUT`` gate record (a
    fail-closed no-send) echoing the matching Stage 30.10.1 invalid
    eligibility reason. Pure; no I/O.
    """
    return _record(
        input_record,
        eligibility_decision=DECISION_INVALID_INPUT,
        eligibility_reason=eligibility_reason,
        send_allowed=False,
        gate_decision=GATE_DECISION_INVALID_INPUT,
        gate_reason=GATE_REASON_INVALID_GATE_INPUT,
    )


# ---------------------------------------------------------------------------
# Public gate
# ---------------------------------------------------------------------------


def evaluate_pre_dispatch_tier_dip_gate(
    input_record: Stage30_10PreDispatchGateInput,
    policy: Stage30_10DipEligibilityPolicy = (
        DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY
    ),
) -> Stage30_10PreDispatchGateRecord:
    """Evaluate the OPTIONAL pre-dispatch tier-dip gate for one candidate.

    Pure / deterministic / no I/O. Returns a
    ``Stage30_10PreDispatchGateRecord`` whose ``gate_decision`` is
    ``PASS_TO_DISPATCH`` ONLY for a Stage 30.10.1 ``ELIGIBLE_DIP`` candidate
    (the only candidate that may proceed to dispatch reservation). A normal
    non-dip skip is ``SKIP_BEFORE_DISPATCH`` (a clean no-send, NEVER a
    transport failure / ``PAYLOAD_REFUSED`` veto, NEVER counted as a dispatch
    failure); a malformed gate envelope is ``INVALID_INPUT``. Raises
    ``Stage30_10PreDispatchGateError`` only when ``input_record`` is not a
    ``Stage30_10PreDispatchGateInput`` (a caller-shape failure with no
    envelope to echo). See the module docstring for the full precedence.
    """
    # ---- Caller-shape guard: must have a gate envelope to echo ----
    if not isinstance(input_record, Stage30_10PreDispatchGateInput):
        raise Stage30_10PreDispatchGateError("INVALID_GATE_INPUT_RECORD_TYPE")

    # ---- Malformed gate envelope -> fail closed (no classify) ----
    if not _is_nonblank_str(input_record.candidate_id):
        return _invalid(input_record, REASON_INVALID_CANDIDATE_ID)
    if not _is_nonblank_str(input_record.token_mint):
        return _invalid(input_record, REASON_INVALID_TOKEN_MINT)
    if not is_safe_created_at_utc(input_record.created_at_utc):
        return _invalid(input_record, REASON_INVALID_CREATED_AT_UTC)
    if not isinstance(
        input_record.eligibility_input, Stage30_10DipEligibilityInput
    ):
        # No eligibility input to classify -> fail closed before reservation.
        return _invalid(input_record, REASON_INVALID_CANDIDATE_ID)

    # ---- Delegate dip eligibility to the Stage 30.10.1 classifier ----
    elig = classify_tier_dip_eligibility(input_record.eligibility_input, policy)

    # ---- Map the classifier decision onto the gate decision ----
    if elig.decision == DECISION_INVALID_INPUT:
        # An invalid eligibility input fails closed before reservation; echo
        # the classifier's specific invalid reason.
        return _record(
            input_record,
            eligibility_decision=elig.decision,
            eligibility_reason=elig.reason,
            send_allowed=False,
            gate_decision=GATE_DECISION_INVALID_INPUT,
            gate_reason=GATE_REASON_INVALID_GATE_INPUT,
        )

    if elig.send_allowed:
        # The ONLY pass: a true ELIGIBLE_DIP may proceed to reservation.
        return _record(
            input_record,
            eligibility_decision=elig.decision,
            eligibility_reason=elig.reason,
            send_allowed=True,
            gate_decision=GATE_DECISION_PASS_TO_DISPATCH,
            gate_reason=GATE_REASON_ELIGIBLE_DIP,
        )

    # A normal classifier no-send skip: suppress cleanly BEFORE reservation.
    # This is NOT a dispatch failure, NOT a transport veto, NOT PAYLOAD_REFUSED.
    return _record(
        input_record,
        eligibility_decision=elig.decision,
        eligibility_reason=elig.reason,
        send_allowed=False,
        gate_decision=GATE_DECISION_SKIP_BEFORE_DISPATCH,
        gate_reason=GATE_REASON_NOT_DIP,
    )


__all__ = (
    "Stage30_10PreDispatchGateError",
    "evaluate_pre_dispatch_tier_dip_gate",
)
