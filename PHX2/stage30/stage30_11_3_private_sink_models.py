"""Stage 30.11.3 private sink adapter models.

Stage 30.11.3 ships the passive, pure, stdlib-only MODEL layer for the private
sink adapter boundary: the adapter-side private sink REQUEST derived from a
committed Stage 30.9.3 ``Stage30_9_3LiveGateInput`` (the
``PASS_TO_DISPATCH`` candidate the Stage 30.11.2 runtime seam reached), the
per-call private sink RESULT the adapter emits, the rolled-up offline proof
SUMMARY, and the closed-set sink decision / reason vocabularies they share,
plus the pure safe-shape helpers the adapter composes.

This module is the MODEL layer ONLY. It implements NO adapter (that is
``stage30_11_3_private_sink_adapter``), builds NO request, calls NO transport,
wires into NO runtime, runs NO bridge / dip gate, makes NO live provider call,
sends NO Discord message, reads NO process environment, opens NO network
connection, opens NO database, writes NO file, reserves NO real dispatch, reads
NO wall clock (``created_at_utc`` is caller-injected), and edits NO Stage 28 /
Stage 29 / Stage 30.3 / Stage 30.4 production file. Stage 30.11.3 is fake /
offline only: the real private compact dispatch / Discord send remains a
SEPARATE, explicitly operator-authorized step this slice does not build.

The private sink decides, per ``PASS_TO_DISPATCH`` gate input it is handed,
exactly one of three closed-set sink decisions:

  * ``PRIVATE_SINK_ACCEPTED``               -- the gate input is a well-shaped
    ``Stage30_9_3LiveGateInput`` AND the INJECTED fake transport accepted the
    built private sink request (reason
    ``WOULD_SEND_PRIVATE_OPERATOR_MESSAGE`` -- a recorded would-send, NEVER a
    real send).
  * ``PRIVATE_SINK_REJECTED_INVALID_INPUT`` -- the handed input is not a usable
    ``Stage30_9_3LiveGateInput`` (a wrong record type or a blank candidate id /
    token mint), so the adapter fails closed BEFORE building a request and
    BEFORE touching the transport (reason ``INVALID_SINK_INPUT``).
  * ``PRIVATE_SINK_TRANSPORT_FAILED``       -- the request was built and handed
    to the injected fake transport, but the fake transport did NOT accept it
    (reason ``FAKE_TRANSPORT_REJECTED``). This is the fake-transport reject
    path; it is NEVER a real transport failure and NEVER a real send.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.9.3 / 30.11.2 model modules);
    the records carry only safe scalars / closed-set tokens, not embedded
    Stage 30.9 / 30.11 record types.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; ``created_at_utc`` is caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + private sink schema identity
# ---------------------------------------------------------------------------


STAGE30_11_3_MINOR_VERSION: str = "30.11.3"


# The Stage 30.11.3 private sink adapter schema version. Names the request /
# result / summary shape; distinct from the Stage 30.11.2 runtime gate schema
# version, the Stage 30.11.1 bridge schema version, and the Stage 30.9.3
# integration schema version. Mirrored BY VALUE by the Stage 30.11 manifest
# section; this module imports no Stage 30.11 manifest.
STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION: str = (
    "stage30_11_3_v0_private_sink_adapter"
)


# The safe-shape source-stage token stamped onto every built private sink
# request (provenance only; names the adapter slice that produced the request,
# never a secret / host / transport destination).
STAGE30_11_3_SOURCE_STAGE: str = "30.11.3"


# ---------------------------------------------------------------------------
# Closed-set: private sink decision
# ---------------------------------------------------------------------------
#
# Exactly one sink decision per recorded result. ``PRIVATE_SINK_ACCEPTED`` is
# the only decision on which the injected fake transport accepted a built
# request. Mirrored BY VALUE by the Stage 30.11 manifest.


PRIVATE_SINK_DECISION_ACCEPTED: str = "PRIVATE_SINK_ACCEPTED"
PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT: str = (
    "PRIVATE_SINK_REJECTED_INVALID_INPUT"
)
PRIVATE_SINK_DECISION_TRANSPORT_FAILED: str = "PRIVATE_SINK_TRANSPORT_FAILED"


STAGE30_11_3_PRIVATE_SINK_DECISIONS: Tuple[str, ...] = (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
)


# The single decision on which the injected fake transport accepted a built
# request (a recorded would-send).
STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION: str = PRIVATE_SINK_DECISION_ACCEPTED


def is_private_sink_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set private sink decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_3_PRIVATE_SINK_DECISIONS
    )


# ---------------------------------------------------------------------------
# Closed-set: private sink reason
# ---------------------------------------------------------------------------
#
# Exactly one sink reason per sink decision.
# ``WOULD_SEND_PRIVATE_OPERATOR_MESSAGE`` is the only reason that accompanies an
# accepted result; it names a RECORDED would-send (the fake transport recorded
# the request), NEVER a real send. Mirrored BY VALUE by the Stage 30.11
# manifest.


PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE: str = (
    "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE"
)
PRIVATE_SINK_REASON_INVALID_SINK_INPUT: str = "INVALID_SINK_INPUT"
PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED: str = "FAKE_TRANSPORT_REJECTED"


STAGE30_11_3_PRIVATE_SINK_REASONS: Tuple[str, ...] = (
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
    PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
    PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
)


# The single reason that accompanies the only accept decision.
STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON: str = (
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
)


def is_private_sink_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set private sink reason.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_3_PRIVATE_SINK_REASONS
    )


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape id. Pure / total; never raises. Mirrors the Stage 30.11.1
    / Stage 30.10.1 non-blank id check BY VALUE; the adapter consults it to fail
    closed on a malformed sink input.
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable model: private sink request (adapter-side, derived from gate input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11PrivateSinkRequest:
    """Immutable adapter-side private sink request.

    A passive carrier of the SAFE fields the private sink adapter derives from a
    committed Stage 30.9.3 ``Stage30_9_3LiveGateInput`` (the
    ``PASS_TO_DISPATCH`` candidate the Stage 30.11.2 runtime seam reached) plus
    the rendered compact body the injected builder produced. It is the shape the
    injected fake transport records a would-send for; it carries only safe
    scalars: opaque ids, an optional opaque candidate ref, the display tier
    token, the rendered compact body, a caller-injected timestamp, and the
    source-stage provenance token. No secret, no raw provider payload, no host,
    no transport destination, no env value.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids.
      * ``candidate_ref``                 -- the OPTIONAL opaque candidate ref
                                             echoed from the gate input, or
                                             ``None``.
      * ``tier_token``                    -- the echoed Stage 30.1 display tier
                                             token, or ``None``.
      * ``compact_body``                  -- the rendered compact operator body
                                             the INJECTED builder produced (a
                                             safe display string only; never a
                                             secret / host / transport
                                             destination).
      * ``created_at_utc``                -- a caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
      * ``source_stage``                  -- the safe-shape source-stage
                                             provenance token (``30.11.3``).
    """

    candidate_id: str
    token_mint: str
    candidate_ref: Optional[str]
    tier_token: Optional[str]
    compact_body: str
    created_at_utc: str
    source_stage: str


# ---------------------------------------------------------------------------
# Immutable model: per-call private sink result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11PrivateSinkResult:
    """Immutable per-call Stage 30.11.3 private sink result.

    The private sink emits exactly one of these per ``PASS_TO_DISPATCH`` gate
    input it is handed (and the injected fake transport returns one of these
    too -- the adapter normalizes the transport's verdict into the closed sink
    vocabulary). It echoes the candidate identity, pins the closed-set
    ``sink_decision`` / ``sink_reason``, and records whether the injected fake
    transport was attempted / accepted. Carries only safe scalars + a
    caller-injected timestamp; no secret, no raw payload, no host, no transport
    destination, no env value.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids.
      * ``sink_decision``                 -- one of
                                             ``STAGE30_11_3_PRIVATE_SINK_DECISIONS``.
      * ``sink_reason``                   -- one of
                                             ``STAGE30_11_3_PRIVATE_SINK_REASONS``.
      * ``transport_attempted``           -- ``True`` ONLY when the injected
                                             fake transport was called (a
                                             well-shaped input that built a
                                             request). ``False`` for an invalid
                                             input that failed closed BEFORE the
                                             transport.
      * ``transport_accepted``            -- ``True`` ONLY when the injected fake
                                             transport accepted the attempt.
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    sink_decision: str
    sink_reason: str
    transport_attempted: bool
    transport_accepted: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: private sink proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11PrivateSinkProofSummary:
    """Immutable offline Stage 30.11.3 private sink proof tally.

    A passive summary of one bounded run of private sink results. It proves, by
    counting, that ONLY a well-shaped ``PASS_TO_DISPATCH`` gate input whose
    request the injected fake transport accepted produced an accepted result,
    that an invalid input failed closed BEFORE the transport, and that a
    fake-transport reject is a clean transport-failed result -- with NO real
    dispatch ever reserved and NO Discord ever sent. Carries only non-negative
    integer counts + a caller-injected timestamp; no secret, no payload, no
    host, no transport destination.

      * ``requests_seen``        -- total private sink results tallied.
      * ``accepted``             -- count with ``PRIVATE_SINK_ACCEPTED``.
      * ``rejected_invalid``     -- count with
                                    ``PRIVATE_SINK_REJECTED_INVALID_INPUT``.
      * ``transport_failed``     -- count with
                                    ``PRIVATE_SINK_TRANSPORT_FAILED``.
      * ``transport_attempted``  -- count where the injected fake transport was
                                    called.
      * ``transport_accepted``   -- count where the injected fake transport
                                    accepted.
      * ``created_at_utc``       -- caller-injected ISO-8601 UTC timestamp.
    """

    requests_seen: int
    accepted: int
    rejected_invalid: int
    transport_failed: int
    transport_attempted: int
    transport_accepted: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def private_sink_request_field_names() -> Tuple[str, ...]:
    """Return the private sink request field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11PrivateSinkRequest))


def private_sink_result_field_names() -> Tuple[str, ...]:
    """Return the private sink result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11PrivateSinkResult))


def private_sink_proof_summary_field_names() -> Tuple[str, ...]:
    """Return the private sink proof summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11PrivateSinkProofSummary))


__all__ = (
    # Minor version + private sink schema identity.
    "STAGE30_11_3_MINOR_VERSION",
    "STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION",
    "STAGE30_11_3_SOURCE_STAGE",
    # Sink decisions.
    "PRIVATE_SINK_DECISION_ACCEPTED",
    "PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT",
    "PRIVATE_SINK_DECISION_TRANSPORT_FAILED",
    "STAGE30_11_3_PRIVATE_SINK_DECISIONS",
    "STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION",
    "is_private_sink_decision",
    # Sink reasons.
    "PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE",
    "PRIVATE_SINK_REASON_INVALID_SINK_INPUT",
    "PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED",
    "STAGE30_11_3_PRIVATE_SINK_REASONS",
    "STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON",
    "is_private_sink_reason",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11PrivateSinkRequest",
    "Stage30_11PrivateSinkResult",
    "Stage30_11PrivateSinkProofSummary",
    # Field-name helpers.
    "private_sink_request_field_names",
    "private_sink_result_field_names",
    "private_sink_proof_summary_field_names",
)
