"""Stage 30.10.3 pre-dispatch gate artifact integration proof models.

Stage 30.10.3 ships the passive, pure, stdlib-only model layer for the
fake / offline ARTIFACT integration proof over the Stage 30.10.2 optional
pre-dispatch tier-dip gate: the per-candidate gate artifact (audit) record,
the offline gate artifact batch (the rolled-up tally + the per-candidate
records), and the in-memory artifact sink result, plus the artifact schema
version + the pure field-name helpers they share.

Stage 30.10.3 proves -- with fakes / offline only -- that EVERY candidate the
Stage 30.10.2 gate evaluates gets an auditable artifact record showing:

  * who it was (``candidate_id`` / ``token_mint``),
  * why the Stage 30.10.1 classifier ruled the way it did
    (``eligibility_decision`` / ``eligibility_reason``),
  * what the Stage 30.10.2 gate decided (``gate_decision`` / ``gate_reason``
    / ``send_allowed``),
  * whether a dispatch reservation WOULD be attempted
    (``dispatch_reservation_would_be_attempted``),
  * whether the candidate was suppressed BEFORE dispatch reservation
    (``suppressed_before_dispatch_reservation``), and
  * the three transport-safety negatives the gate slice must NEVER trip for a
    normal non-dip skip: ``dispatch_failure_recorded`` (a pre-dispatch skip is
    NEVER a dispatch failure), ``transport_veto_used`` (the gate is NEVER a
    transport-layer veto), and ``payload_refused_used`` (a normal non-dip skip
    NEVER reuses the transport ``PAYLOAD_REFUSED`` veto).

The artifact makes it IMPOSSIBLE to confuse a candidate that was *skipped
before dispatch* with one that *failed during dispatch*: a pre-dispatch skip
always carries ``suppressed_before_dispatch_reservation=True`` and
``dispatch_failure_recorded=False``; the gate never records a dispatch
failure / transport veto / payload-refused for any candidate.

This module is the MODEL layer ONLY: it implements NO projector (that is
``stage30_10_3_gate_artifact_projector``) and NO proof / sink (that is
``stage30_10_3_fake_artifact_proof``). It runs NO gate, wires into NO
runtime, makes NO live provider call, sends NO Discord message, reads NO
process environment, opens NO network connection, opens NO database, writes
NO file, performs NO transport-layer veto, and edits NO Stage 28 suppression
/ Stage 30.3 / Stage 30.4 runtime orchestrator. Stage 30.10.3 is fake /
offline only; nothing existing imports it.

The artifact record echoes the Stage 30.10.1 classifier's closed-set
``eligibility_decision`` / ``eligibility_reason`` and the Stage 30.10.2 gate's
closed-set ``gate_decision`` / ``gate_reason`` tokens verbatim; this module
does not re-pin those (they live in the Stage 30.10.1 / 30.10.2 models). It
pins ONLY the artifact schema version + the artifact record / batch / sink
field shapes.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.8.1 / 30.9.1 model modules);
    the artifact records carry only projected safe scalars, not embedded
    Stage 30.10.1 / 30.10.2 record types.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No filesystem write (the only sink is the in-memory fake writer in the
    proof module; this models module writes nothing).
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * ``created_at_utc`` is caller-injected; the model NEVER reads a wall
    clock (no ``datetime.now``).
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Tuple


# ---------------------------------------------------------------------------
# Minor version + artifact schema identity
# ---------------------------------------------------------------------------


STAGE30_10_3_MINOR_VERSION: str = "30.10.3"


# The Stage 30.10.3 gate artifact schema version. Names the offline gate
# artifact record / batch shape; distinct from the Stage 30.8 / 30.9 artifact
# schema versions and from the Stage 30.10.0 spec version. Mirrored BY VALUE
# by the Stage 30.10.3 manifest; this module imports no Stage 30.10 manifest.
STAGE30_10_3_ARTIFACT_SCHEMA_VERSION: str = "stage30_10_v0_gate_artifact"


# ---------------------------------------------------------------------------
# Immutable model: per-candidate gate artifact record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10GateArtifactRecord:
    """Immutable per-candidate pre-dispatch gate artifact (audit) record.

    The Stage 30.10.3 projector emits exactly one of these per candidate the
    Stage 30.10.2 gate evaluated. It echoes the candidate identity, the Stage
    30.10.1 classifier's closed-set ``eligibility_decision`` /
    ``eligibility_reason``, and the Stage 30.10.2 gate's closed-set
    ``gate_decision`` / ``gate_reason`` / ``send_allowed``; and it pins the
    five derived booleans that make the candidate's pre-dispatch fate
    auditable. Carries only safe scalars + a caller-injected artifact
    timestamp; no secret, no raw payload, no host, no transport destination,
    no env value.

      * ``proof_id``                                -- the safe proof-run id
                                                       this record belongs to.
      * ``candidate_id`` / ``token_mint``           -- echoed safe-shape ids.
      * ``eligibility_decision`` / ``eligibility_reason``
                                                    -- echoed Stage 30.10.1
                                                       closed-set tokens.
      * ``gate_decision`` / ``gate_reason``         -- echoed Stage 30.10.2
                                                       closed-set tokens.
      * ``send_allowed``                            -- echoed gate flag.
      * ``dispatch_reservation_would_be_attempted`` -- ``True`` ONLY for a
                                                       gate ``PASS_TO_DISPATCH``
                                                       (the only candidate that
                                                       would proceed to dispatch
                                                       reservation).
      * ``suppressed_before_dispatch_reservation``  -- ``True`` for every
                                                       non-pass candidate (a
                                                       clean no-send BEFORE
                                                       reservation); the exact
                                                       complement of
                                                       ``dispatch_reservation_would_be_attempted``.
      * ``dispatch_failure_recorded``               -- ALWAYS ``False``: a
                                                       pre-dispatch skip is
                                                       NEVER a dispatch failure.
      * ``transport_veto_used``                     -- ALWAYS ``False``: the
                                                       gate is NEVER a
                                                       transport-layer veto.
      * ``payload_refused_used``                    -- ALWAYS ``False``: a
                                                       normal non-dip skip
                                                       NEVER reuses the
                                                       transport
                                                       ``PAYLOAD_REFUSED`` veto.
      * ``created_at_utc``                          -- caller-injected ISO-8601
                                                       UTC artifact timestamp;
                                                       NEVER a wall-clock read.
    """

    proof_id: str
    candidate_id: str
    token_mint: str
    eligibility_decision: str
    eligibility_reason: str
    gate_decision: str
    gate_reason: str
    send_allowed: bool
    dispatch_reservation_would_be_attempted: bool
    suppressed_before_dispatch_reservation: bool
    dispatch_failure_recorded: bool
    transport_veto_used: bool
    payload_refused_used: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: offline gate artifact batch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10GateArtifactBatch:
    """Immutable offline gate artifact batch (the rolled-up audit tally).

    A passive carrier of one offline candidate-stream run's worth of gate
    artifact records plus the rolled-up counts the proof reports. The counts
    are derived from the records, so the batch proves, by counting, that ONLY
    eligible dips would reserve a dispatch and that every non-dip / invalid is
    suppressed BEFORE reservation -- and that NO candidate is a dispatch
    failure, uses a transport veto, or uses the ``PAYLOAD_REFUSED`` veto.
    Carries only records + non-negative integer counts + a caller-injected
    timestamp; no secret, no payload, no host, no transport destination.

      * ``proof_id``                  -- the safe proof-run id.
      * ``records``                   -- the ordered per-candidate artifact
                                         records.
      * ``candidates_seen``           -- total candidates (equals
                                         ``len(records)``).
      * ``candidates_passed``         -- records whose gate decision is
                                         ``PASS_TO_DISPATCH``.
      * ``candidates_skipped``        -- records whose gate decision is
                                         ``SKIP_BEFORE_DISPATCH``.
      * ``invalid_inputs``            -- records whose gate decision is
                                         ``INVALID_INPUT`` (or any unrecognized
                                         decision -- fail closed into invalid).
      * ``dispatch_attempts_reserved``-- records that would attempt dispatch
                                         reservation (equals
                                         ``candidates_passed``).
      * ``dispatch_attempts_suppressed_before_reservation``
                                      -- records suppressed BEFORE reservation
                                         (equals ``candidates_skipped`` +
                                         ``invalid_inputs``).
      * ``dispatch_failures_recorded``-- records flagged as a dispatch failure
                                         (ALWAYS 0).
      * ``transport_veto_count``      -- records flagged as a transport veto
                                         (ALWAYS 0).
      * ``payload_refused_count``     -- records flagged as ``PAYLOAD_REFUSED``
                                         (ALWAYS 0).
      * ``created_at_utc``            -- caller-injected ISO-8601 UTC
                                         timestamp.
    """

    proof_id: str
    records: Tuple[Stage30_10GateArtifactRecord, ...]
    candidates_seen: int
    candidates_passed: int
    candidates_skipped: int
    invalid_inputs: int
    dispatch_attempts_reserved: int
    dispatch_attempts_suppressed_before_reservation: int
    dispatch_failures_recorded: int
    transport_veto_count: int
    payload_refused_count: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: in-memory artifact sink result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10GateArtifactSinkResult:
    """Immutable in-memory artifact sink result (a passive verdict record).

    Returned by the Stage 30.10.3 fake / in-memory artifact sink after it
    accepts ONE gate artifact batch. The sink writes nothing to disk / DB /
    network -- it only records the batch in memory -- so this result simply
    attests how many records + which batch were retained, plus the pinned
    artifact schema version. Carries only counts / flags / a safe schema id /
    a caller-injected timestamp; no secret, no payload, no host, no path.

      * ``proof_id``                -- the proof-run id (echoed from batch).
      * ``records_written``         -- number of artifact records the sink
                                       retained in memory.
      * ``batch_written``           -- ``True`` iff the single batch was
                                       retained.
      * ``artifact_schema_version`` -- the pinned Stage 30.10.3 artifact
                                       schema version.
      * ``created_at_utc``          -- caller-injected ISO-8601 UTC timestamp.
    """

    proof_id: str
    records_written: int
    batch_written: bool
    artifact_schema_version: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def gate_artifact_record_field_names() -> Tuple[str, ...]:
    """Return the gate artifact record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10GateArtifactRecord))


def gate_artifact_batch_field_names() -> Tuple[str, ...]:
    """Return the gate artifact batch field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10GateArtifactBatch))


def gate_artifact_sink_result_field_names() -> Tuple[str, ...]:
    """Return the in-memory artifact sink result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10GateArtifactSinkResult))


__all__ = (
    # Minor version + artifact schema identity.
    "STAGE30_10_3_MINOR_VERSION",
    "STAGE30_10_3_ARTIFACT_SCHEMA_VERSION",
    # Models.
    "Stage30_10GateArtifactRecord",
    "Stage30_10GateArtifactBatch",
    "Stage30_10GateArtifactSinkResult",
    # Field-name helpers.
    "gate_artifact_record_field_names",
    "gate_artifact_batch_field_names",
    "gate_artifact_sink_result_field_names",
)
