"""Stage 30.11.1 offline live-candidate assembly bridge models.

Stage 30.11.1 ships the passive, pure, stdlib-only MODEL layer for the offline
live-candidate -> dip-gate-input assembly bridge: the Stage 30.11-owned
already-assembled live candidate / context snapshot the bridge maps FROM (the
bridge input), the per-candidate bridge result the bridge emits (carrying the
committed Stage 30.9.3 live gate input the dip gate later consumes, or
``None``), the rolled-up offline proof summary, and the closed-set bridge
decision / reason vocabularies they share, plus the pure safe-shape helpers
the bridge composes.

This module is the MODEL layer ONLY. It implements NO bridge (that is
``stage30_11_1_live_candidate_bridge``), wires into NO runtime, runs NO dip
gate, makes NO live provider call, sends NO Discord message, reads NO process
environment, opens NO network connection, opens NO database, writes NO file,
reserves NO dispatch, and edits NO Stage 28 / Stage 29 / Stage 30.3 / Stage
30.4 production file. Stage 30.11.1 is fake / offline only.

The bridge decides, per already-assembled live candidate snapshot:

  * ``BRIDGED_TO_LIVE_GATE_INPUT``      -- the candidate carries a usable
    candidate identity AND the required migration / ATH / current-market
    context, so a committed Stage 30.9.3 ``Stage30_9_3LiveGateInput`` is
    assembled FROM its already-present fields (reason ``READY_FOR_DIP_GATE``).
    The bridge does NOT run the dip gate; whether the candidate is an eligible
    dip is decided LATER by the committed Stage 30.9.3 seam.
  * ``SKIPPED_MISSING_REQUIRED_CONTEXT`` -- the candidate identity is usable
    but the migration / ATH / current-market context is not present, so there
    is no assembled context to gate (reason ``MISSING_REQUIRED_CONTEXT``);
    ``live_gate_input`` is ``None``.
  * ``INVALID_BRIDGE_INPUT``            -- the candidate identity itself is
    malformed (a blank candidate id / token mint), so the candidate fails
    closed BEFORE any gate input is built (reason ``INVALID_FIELD_SHAPE``);
    ``live_gate_input`` is ``None``.

Unlike the offline-only Stage 30.9.x / 30.10.x model modules (which import no
PHX2 module), the Stage 30.11.1 bridge models EMBED the committed Stage 30.9.3
``Stage30_9_3LiveGateInput`` on the bridge result, so this module imports that
ONE committed Stage 30.9.3 model type. This is the permitted Stage 30.11 scope
expansion (the wiring slices MAY compose the committed live surfaces behind the
dip gate); it imports no Stage 21-29 production module, no live runner, no
provider, no transport, and no Discord path.

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Imports ONLY the committed Stage 30.9.3 integration models sibling (for
    the embedded ``Stage30_9_3LiveGateInput`` field type); no other PHX2
    module, no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28
    suppression / live runner / provider / transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * ``created_at_utc`` is caller-injected; the model NEVER reads a wall clock
    (no ``datetime.now``).
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Optional, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)


# ---------------------------------------------------------------------------
# Minor version + bridge schema identity
# ---------------------------------------------------------------------------


STAGE30_11_1_MINOR_VERSION: str = "30.11.1"


# The Stage 30.11.1 live-candidate assembly bridge schema version. Names the
# bridge snapshot / result / summary shape; distinct from the Stage 30.9.3
# integration schema version and the Stage 30.10.3 artifact schema version.
# Mirrored BY VALUE by the Stage 30.11 manifest section; this module imports no
# Stage 30.11 manifest.
STAGE30_11_1_BRIDGE_SCHEMA_VERSION: str = (
    "stage30_11_1_v0_live_candidate_bridge"
)


# ---------------------------------------------------------------------------
# Closed-set: bridge decision
# ---------------------------------------------------------------------------
#
# Exactly one bridge decision per candidate. ``BRIDGED_TO_LIVE_GATE_INPUT`` is
# the only decision that carries a built ``Stage30_9_3LiveGateInput``; the
# other two carry ``None``. Mirrored BY VALUE by the Stage 30.11 manifest.


BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT: str = "BRIDGED_TO_LIVE_GATE_INPUT"
BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT: str = (
    "SKIPPED_MISSING_REQUIRED_CONTEXT"
)
BRIDGE_DECISION_INVALID_BRIDGE_INPUT: str = "INVALID_BRIDGE_INPUT"


STAGE30_11_1_BRIDGE_DECISIONS: Tuple[str, ...] = (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
)


# The single decision that yields a built Stage 30.9.3 live gate input.
STAGE30_11_1_BRIDGE_PASS_DECISION: str = (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
)


def is_bridge_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set bridge decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_1_BRIDGE_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: bridge reason
# ---------------------------------------------------------------------------
#
# Exactly one bridge reason per decision. ``READY_FOR_DIP_GATE`` is the only
# reason that accompanies a successful bridge; ``MISSING_REQUIRED_CONTEXT``
# accompanies a clean skip; ``INVALID_FIELD_SHAPE`` accompanies a fail-closed
# invalid input. Mirrored BY VALUE by the Stage 30.11 manifest.


BRIDGE_REASON_READY_FOR_DIP_GATE: str = "READY_FOR_DIP_GATE"
BRIDGE_REASON_MISSING_REQUIRED_CONTEXT: str = "MISSING_REQUIRED_CONTEXT"
BRIDGE_REASON_INVALID_FIELD_SHAPE: str = "INVALID_FIELD_SHAPE"


STAGE30_11_1_BRIDGE_REASONS: Tuple[str, ...] = (
    BRIDGE_REASON_READY_FOR_DIP_GATE,
    BRIDGE_REASON_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_INVALID_FIELD_SHAPE,
)


def is_bridge_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set bridge reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_1_BRIDGE_REASONS


# ---------------------------------------------------------------------------
# Context-present status token + safe-shape helpers
# ---------------------------------------------------------------------------
#
# A live candidate's migration / ATH / current-market context is "present"
# IFF its status token is exactly ``PRESENT`` (mirrors the Stage 30.10.1
# ``MIGRATION_STATUS_PRESENT`` / ``ATH_STATUS_PRESENT`` /
# ``MARKET_CONTEXT_STATUS_PRESENT`` values BY VALUE; this module imports no
# Stage 30.10 module). Anything else (a degraded token, ``None``, a
# non-string) is treated as NOT present and the bridge fails closed to a
# clean skip -- so a candidate with no assembled context can never be bridged
# into a gate input.


LIVE_CONTEXT_STATUS_PRESENT: str = "PRESENT"


def is_context_present(value: object) -> bool:
    """Return ``True`` iff ``value`` exactly equals the PRESENT token.

    Pure / total; never raises. Used by the bridge to decide whether the
    migration / ATH / current-market context is present.
    """
    return isinstance(value, str) and value == LIVE_CONTEXT_STATUS_PRESENT


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape id. Pure / total; never raises. Mirrors the Stage 30.10.1
    classifier's ``candidate_id`` / ``token_mint`` non-blank check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable model: Stage 30.11-owned already-assembled live candidate snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11LiveCandidateSnapshot:
    """Immutable Stage 30.11-owned already-assembled live candidate snapshot.

    A passive carrier of the ALREADY-ASSEMBLED live candidate / context fields
    the live path produces, expressed in the narrowest Stage 30.11-owned shape
    the bridge needs to build a committed Stage 30.9.3 ``Stage30_9_3LiveGateInput``
    (and, downstream, a Stage 30.10.1 eligibility input). It carries ONLY safe
    scalars: opaque ids, closed-set status tokens / a display tier hint,
    ``Decimal`` magnitudes, an optional verified flag, an optional opaque source
    ref, and a caller-injected ISO-8601 UTC timestamp. No secret, no raw
    payload, no host, no transport destination.

    The bridge does NOT fabricate any of these signals: a missing ATH /
    migration / current-market context is left ``None`` (the bridge then fails
    closed to a clean skip), and the snapshot is NEVER populated from a provider
    call here (it is the OUTPUT of the already-assembled live candidate path).

      * ``candidate_id``                -- the safe-shape candidate id.
      * ``token_mint``                  -- the safe-shape token mint.
      * ``pair_type``                   -- the pair type / quote-asset display
                                           context, or ``None`` (provenance
                                           only; not part of the dip-eligibility
                                           mapping).
      * ``tier_hint``                   -- the already-computed Stage 30.1 tier
                                           token (display ``Tier N`` form or the
                                           normalized code), or ``None`` (the
                                           committed gate classifies the tier;
                                           the bridge computes none).
      * ``drawdown_from_ath``           -- the already-computed drawdown
                                           magnitude as a ``Decimal``, or
                                           ``None``.
      * ``migration_status``            -- the migration context status token,
                                           or ``None``.
      * ``ath_status``                  -- the ATH context status token, or
                                           ``None``.
      * ``market_context_status``       -- the current market context status
                                           token, or ``None``.
      * ``current_market_cap_usd``      -- the current market cap as a
                                           ``Decimal``, or ``None``.
      * ``post_migration_ath_verified`` -- whether the ATH is verified to be
                                           post-migration (``True`` / ``False``
                                           / ``None``).
      * ``source_ref``                  -- an OPTIONAL opaque reference to the
                                           original live candidate (a safe id
                                           only; never a raw payload), or
                                           ``None``.
      * ``created_at_utc``              -- a caller-injected ISO-8601 UTC
                                           timestamp for the assembled context;
                                           NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    pair_type: Optional[str]
    tier_hint: Optional[str]
    drawdown_from_ath: Optional[Decimal]
    migration_status: Optional[str]
    ath_status: Optional[str]
    market_context_status: Optional[str]
    current_market_cap_usd: Optional[Decimal]
    post_migration_ath_verified: Optional[bool]
    source_ref: Optional[str]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-candidate bridge result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11BridgeResult:
    """Immutable per-candidate Stage 30.11.1 bridge result.

    The bridge emits exactly one of these per candidate snapshot. It echoes the
    candidate identity, pins the bridge's closed-set ``bridge_decision`` /
    ``bridge_reason``, and carries the built committed Stage 30.9.3
    ``Stage30_9_3LiveGateInput`` (ONLY for a ``BRIDGED_TO_LIVE_GATE_INPUT``
    decision; ``None`` otherwise). Carries only safe scalars + the embedded gate
    input + a caller-injected timestamp; no secret, no raw payload, no host, no
    transport destination, no env value. The bridge does NOT run the gate, does
    NOT reserve a dispatch, and does NOT send Discord -- a downstream caller runs
    the committed Stage 30.9.3 dip gate over ``live_gate_input`` later.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids.
      * ``bridge_decision``               -- one of
                                             ``STAGE30_11_1_BRIDGE_DECISIONS``.
      * ``bridge_reason``                 -- one of
                                             ``STAGE30_11_1_BRIDGE_REASONS``.
      * ``live_gate_input``               -- the built committed Stage 30.9.3
                                             ``Stage30_9_3LiveGateInput`` (only
                                             for ``BRIDGED_TO_LIVE_GATE_INPUT``;
                                             ``None`` for a skip / invalid).
      * ``created_at_utc``                -- a caller-injected ISO-8601 UTC
                                             timestamp for the bridge run; NEVER
                                             a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    bridge_decision: str
    bridge_reason: str
    live_gate_input: Optional[Stage30_9_3LiveGateInput]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: offline bridge proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11BridgeProofSummary:
    """Immutable offline Stage 30.11.1 bridge proof tally.

    A passive summary of one bounded snapshot-stream run through the bridge. It
    proves, by counting, that ONLY candidates with a usable identity + the
    required assembled context are bridged into a committed Stage 30.9.3 live
    gate input, that candidates missing required context are cleanly skipped,
    and that malformed candidates fail closed -- WITHOUT running the dip gate,
    reserving a dispatch, or sending Discord. Carries only non-negative integer
    counts + a caller-injected timestamp; no secret, no payload, no host, no
    transport destination.

      * ``candidates_seen``           -- total candidate snapshots taken from
                                         the stream.
      * ``bridged``                   -- count with
                                         ``BRIDGED_TO_LIVE_GATE_INPUT``.
      * ``skipped_missing_context``   -- count with
                                         ``SKIPPED_MISSING_REQUIRED_CONTEXT``.
      * ``invalid_inputs``            -- count with ``INVALID_BRIDGE_INPUT``.
      * ``created_at_utc``            -- a caller-injected ISO-8601 UTC
                                         timestamp; NEVER a wall-clock read.
    """

    candidates_seen: int
    bridged: int
    skipped_missing_context: int
    invalid_inputs: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def candidate_snapshot_field_names() -> Tuple[str, ...]:
    """Return the candidate snapshot field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11LiveCandidateSnapshot))


def bridge_result_field_names() -> Tuple[str, ...]:
    """Return the bridge result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11BridgeResult))


def bridge_proof_summary_field_names() -> Tuple[str, ...]:
    """Return the bridge proof summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11BridgeProofSummary))


__all__ = (
    # Minor version + bridge schema identity.
    "STAGE30_11_1_MINOR_VERSION",
    "STAGE30_11_1_BRIDGE_SCHEMA_VERSION",
    # Bridge decisions.
    "BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT",
    "BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT",
    "BRIDGE_DECISION_INVALID_BRIDGE_INPUT",
    "STAGE30_11_1_BRIDGE_DECISIONS",
    "STAGE30_11_1_BRIDGE_PASS_DECISION",
    "is_bridge_decision",
    # Bridge reasons.
    "BRIDGE_REASON_READY_FOR_DIP_GATE",
    "BRIDGE_REASON_MISSING_REQUIRED_CONTEXT",
    "BRIDGE_REASON_INVALID_FIELD_SHAPE",
    "STAGE30_11_1_BRIDGE_REASONS",
    "is_bridge_reason",
    # Context-present token + safe-shape helpers.
    "LIVE_CONTEXT_STATUS_PRESENT",
    "is_context_present",
    "is_nonblank_str",
    # Models.
    "Stage30_11LiveCandidateSnapshot",
    "Stage30_11BridgeResult",
    "Stage30_11BridgeProofSummary",
    # Field-name helpers.
    "candidate_snapshot_field_names",
    "bridge_result_field_names",
    "bridge_proof_summary_field_names",
)
