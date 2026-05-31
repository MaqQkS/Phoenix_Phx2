"""Stage 30.10.2 optional pre-dispatch tier-dip gate models.

Stage 30.10.2 ships the passive, pure, stdlib-only model layer for the
OPTIONAL fake / offline pre-dispatch tier-dip gate: the per-candidate gate
envelope (the input), the per-candidate gate audit record, the offline
proof-summary tally, the offline scenario carrier, and the closed-set gate
decision / gate reason vocabularies they share, plus the pure field-name
helpers.

The gate is the thin PLACEMENT layer over the Stage 30.10.1 eligibility
classifier (Stage 30.10.1 decides dip eligibility; Stage 30.10.2 decides
WHERE that decision is applied -- BEFORE dispatch reservation / the private
send). This module is the MODEL layer ONLY: it implements NO gate function
(that is ``stage30_10_2_pre_dispatch_gate``), runs NO classifier, wires into
NO runtime, makes NO live provider call, sends NO Discord message, reads NO
process environment, opens NO network connection, opens NO database, writes
NO file, performs NO transport-layer veto, and edits NO Stage 28 suppression
/ Stage 30.3 / Stage 30.4 runtime orchestrator. Stage 30.10.2 is fake /
offline only; nothing existing imports it.

The gate maps the Stage 30.10.1 classifier's eight closed-set decisions onto
exactly three gate decisions:

  * ``PASS_TO_DISPATCH``      -- only a true ``ELIGIBLE_DIP`` candidate may
    proceed to dispatch reservation (reason ``ELIGIBLE_DIP``).
  * ``SKIP_BEFORE_DISPATCH``  -- any no-send eligibility skip (``Tier
    Unknown`` / ``Tier Not Applicable`` / missing ATH / missing migration /
    missing market context / missing drawdown / a policy-excluded tier) is
    cleanly suppressed BEFORE reservation (reason ``NOT_DIP``). This is a
    NORMAL no-send: it is NEVER a transport failure, NEVER a
    ``PAYLOAD_REFUSED`` veto, and is NEVER counted as a dispatch failure.
  * ``INVALID_INPUT``         -- a malformed gate envelope fails closed
    (reason ``INVALID_GATE_INPUT``); the candidate never proceeds to
    reservation.

``PASS_TO_DISPATCH`` is the ONLY decision that lets a candidate proceed.

Closed-set vocabularies pinned here (each mirrors the Stage 30.10.2 manifest
BY VALUE; this module imports no Stage 30.10 manifest):

  * gate decision -- ``PASS_TO_DISPATCH`` / ``SKIP_BEFORE_DISPATCH`` /
    ``INVALID_INPUT``.
  * gate reason   -- ``ELIGIBLE_DIP`` / ``NOT_DIP`` / ``INVALID_GATE_INPUT``.

The gate record's ``eligibility_decision`` / ``eligibility_reason`` echo the
Stage 30.10.1 classifier's closed-set tokens verbatim; this module does not
re-pin those (they live in the Stage 30.10.1 models).

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the Stage 30.10.1 models sibling (for the embedded
    ``Stage30_10DipEligibilityInput`` field type); no other PHX2 module, no
    Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28
    suppression / live runner / provider / transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * ``created_at_utc`` is caller-injected; the model NEVER reads a wall
    clock (no ``datetime.now``).
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple

from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    Stage30_10DipEligibilityInput,
)


# ---------------------------------------------------------------------------
# Minor version
# ---------------------------------------------------------------------------


STAGE30_10_2_MINOR_VERSION: str = "30.10.2"


# ---------------------------------------------------------------------------
# Closed-set: gate decision
# ---------------------------------------------------------------------------
#
# Exactly one gate decision per evaluated candidate. ``PASS_TO_DISPATCH`` is
# the only decision that proceeds to dispatch reservation; the others are
# clean no-sends. Mirrors the Stage 30.10.2 manifest
# ``STAGE30_10_2_GATE_DECISIONS`` closed set BY VALUE.


GATE_DECISION_PASS_TO_DISPATCH: str = "PASS_TO_DISPATCH"
GATE_DECISION_SKIP_BEFORE_DISPATCH: str = "SKIP_BEFORE_DISPATCH"
GATE_DECISION_INVALID_INPUT: str = "INVALID_INPUT"


STAGE30_10_2_GATE_DECISIONS: Tuple[str, ...] = (
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    GATE_DECISION_INVALID_INPUT,
)


# The single decision that proceeds to dispatch reservation.
STAGE30_10_2_GATE_PASS_DECISION: str = GATE_DECISION_PASS_TO_DISPATCH


def is_gate_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set gate decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_10_2_GATE_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: gate reason
# ---------------------------------------------------------------------------
#
# Exactly one gate reason per gate decision. ``ELIGIBLE_DIP`` is the only
# reason that accompanies ``PASS_TO_DISPATCH``; ``NOT_DIP`` accompanies a
# normal ``SKIP_BEFORE_DISPATCH`` (a clean no-send, NOT a transport / payload
# refusal); ``INVALID_GATE_INPUT`` accompanies ``INVALID_INPUT``. Mirrors the
# Stage 30.10.2 manifest ``STAGE30_10_2_GATE_REASONS`` closed set BY VALUE.


GATE_REASON_ELIGIBLE_DIP: str = "ELIGIBLE_DIP"
GATE_REASON_NOT_DIP: str = "NOT_DIP"
GATE_REASON_INVALID_GATE_INPUT: str = "INVALID_GATE_INPUT"


STAGE30_10_2_GATE_REASONS: Tuple[str, ...] = (
    GATE_REASON_ELIGIBLE_DIP,
    GATE_REASON_NOT_DIP,
    GATE_REASON_INVALID_GATE_INPUT,
)


# The single reason that accompanies the only pass decision.
STAGE30_10_2_GATE_PASS_REASON: str = GATE_REASON_ELIGIBLE_DIP


def is_gate_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set gate reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_10_2_GATE_REASONS


# ---------------------------------------------------------------------------
# Immutable model: per-candidate gate envelope (the input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10PreDispatchGateInput:
    """Immutable per-candidate pre-dispatch gate envelope.

    A passive carrier the gate evaluates BEFORE dispatch reservation. It
    wraps an already-built Stage 30.10.1 ``Stage30_10DipEligibilityInput``
    (the authoritative dip-eligibility signal source) with the safe-shape
    identity the gate echoes into its record. Carries only safe scalars: an
    opaque candidate id / token mint, the embedded eligibility input, an
    optional opaque candidate ref, and a caller-injected ISO-8601 UTC
    timestamp. No secret, no raw payload, no host, no transport destination.

      * ``candidate_id``      -- the safe-shape candidate id (echoed).
      * ``token_mint``        -- the safe-shape token mint (echoed).
      * ``eligibility_input`` -- the Stage 30.10.1
                                 ``Stage30_10DipEligibilityInput`` the gate
                                 hands to the classifier.
      * ``candidate_ref``     -- an OPTIONAL opaque reference to the original
                                 fake candidate (a safe id only; never a raw
                                 payload), or ``None``.
      * ``created_at_utc``    -- a caller-injected ISO-8601 UTC timestamp;
                                 NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    eligibility_input: Stage30_10DipEligibilityInput
    candidate_ref: Optional[str]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-candidate gate audit record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10PreDispatchGateRecord:
    """Immutable per-candidate pre-dispatch gate audit record.

    The gate emits exactly one of these per evaluated candidate. It echoes
    the candidate identity, the Stage 30.10.1 classifier's closed-set
    ``eligibility_decision`` / ``eligibility_reason`` / ``send_allowed``, and
    pins the gate's own closed-set ``gate_decision`` / ``gate_reason``.
    Carries only safe scalars; no secret, no raw payload, no host, no
    transport destination, no env value.

      * ``candidate_id`` / ``token_mint``  -- echoed safe-shape ids.
      * ``eligibility_decision``           -- the echoed Stage 30.10.1
                                              decision (one of
                                              ``STAGE30_10_1_ELIGIBILITY_DECISIONS``).
      * ``eligibility_reason``             -- the echoed Stage 30.10.1 reason
                                              (one of
                                              ``STAGE30_10_1_ELIGIBILITY_REASONS``).
      * ``send_allowed``                   -- the echoed classifier flag
                                              (``True`` only for an eligible
                                              dip).
      * ``gate_decision``                  -- one of
                                              ``STAGE30_10_2_GATE_DECISIONS``.
      * ``gate_reason``                    -- one of
                                              ``STAGE30_10_2_GATE_REASONS``.
      * ``created_at_utc``                 -- echoed caller-injected ISO-8601
                                              UTC timestamp.
    """

    candidate_id: str
    token_mint: str
    eligibility_decision: str
    eligibility_reason: str
    send_allowed: bool
    gate_decision: str
    gate_reason: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: offline fake-gate proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10PreDispatchGateProofSummary:
    """Immutable offline fake-gate proof tally.

    A passive summary of one offline candidate-stream run through the gate.
    It proves, by counting, that ONLY eligible dips are reserved for dispatch
    and that every non-dip / invalid candidate is suppressed BEFORE
    reservation. Carries only non-negative integer counts plus a
    caller-injected timestamp; no secret, no payload, no host, no transport
    destination.

      * ``candidates_seen``                              -- total candidates
                                                            evaluated.
      * ``candidates_passed``                            -- count with
                                                            ``PASS_TO_DISPATCH``.
      * ``candidates_skipped``                           -- count with
                                                            ``SKIP_BEFORE_DISPATCH``.
      * ``invalid_inputs``                               -- count with
                                                            ``INVALID_INPUT``.
      * ``dispatch_attempts_reserved``                   -- dispatch attempts
                                                            reserved (equals
                                                            ``candidates_passed``;
                                                            only eligible dips).
      * ``dispatch_attempts_suppressed_before_reservation``
                                                         -- attempts suppressed
                                                            BEFORE reservation
                                                            (equals
                                                            ``candidates_skipped``
                                                            + ``invalid_inputs``).
      * ``created_at_utc``                               -- caller-injected
                                                            ISO-8601 UTC
                                                            timestamp.
    """

    candidates_seen: int
    candidates_passed: int
    candidates_skipped: int
    invalid_inputs: int
    dispatch_attempts_reserved: int
    dispatch_attempts_suppressed_before_reservation: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: offline fake-gate scenario carrier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10PreDispatchGateScenario:
    """Immutable offline fake-gate scenario carrier.

    A passive carrier of a deterministic candidate stream (a tuple of gate
    inputs) the offline proof runs through the gate. The concrete default
    scenario is built by the Stage 30.10.2 fake-proof module, never here.

      * ``name``         -- a safe scenario label.
      * ``gate_inputs``  -- the ordered tuple of
                            ``Stage30_10PreDispatchGateInput`` candidates.
      * ``created_at_utc`` -- a caller-injected ISO-8601 UTC timestamp the
                            proof echoes into its summary.
    """

    name: str
    gate_inputs: Tuple[Stage30_10PreDispatchGateInput, ...]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def gate_input_field_names() -> Tuple[str, ...]:
    """Return the gate input field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10PreDispatchGateInput))


def gate_record_field_names() -> Tuple[str, ...]:
    """Return the gate audit record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10PreDispatchGateRecord))


def proof_summary_field_names() -> Tuple[str, ...]:
    """Return the proof summary field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_10PreDispatchGateProofSummary)
    )


__all__ = (
    # Minor version.
    "STAGE30_10_2_MINOR_VERSION",
    # Gate decisions.
    "GATE_DECISION_PASS_TO_DISPATCH",
    "GATE_DECISION_SKIP_BEFORE_DISPATCH",
    "GATE_DECISION_INVALID_INPUT",
    "STAGE30_10_2_GATE_DECISIONS",
    "STAGE30_10_2_GATE_PASS_DECISION",
    "is_gate_decision",
    # Gate reasons.
    "GATE_REASON_ELIGIBLE_DIP",
    "GATE_REASON_NOT_DIP",
    "GATE_REASON_INVALID_GATE_INPUT",
    "STAGE30_10_2_GATE_REASONS",
    "STAGE30_10_2_GATE_PASS_REASON",
    "is_gate_reason",
    # Models.
    "Stage30_10PreDispatchGateInput",
    "Stage30_10PreDispatchGateRecord",
    "Stage30_10PreDispatchGateProofSummary",
    "Stage30_10PreDispatchGateScenario",
    # Field-name helpers.
    "gate_input_field_names",
    "gate_record_field_names",
    "proof_summary_field_names",
)
