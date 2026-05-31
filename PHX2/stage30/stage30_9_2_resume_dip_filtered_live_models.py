"""Stage 30.9.2_RESUME dip-filtered live proof models.

Stage 30.9.2_RESUME unpauses the previously PAUSED Stage 30.9.2 bounded
private live compact proof, but ONLY as a dip-FILTERED live proof path: the
controlled live ceremony may proceed only over candidates the completed
Stage 30.10 dip-gate stack (30.10.1 classifier -> 30.10.2 pre-dispatch gate
-> 30.10.3 artifact projection) has already ruled ``PASS_TO_DISPATCH``. This
module is the passive, pure, stdlib-only MODEL layer for that resume: the
frozen dip-filtered resume PLAN (the planning/readiness carrier), the frozen
per-candidate resume proof RECORD (the dip-filtered audit projection), and
the frozen resume proof SUMMARY (the rolled-up tally), plus the closed-set
required-gate-stack vocabulary and the pure field-name helpers they share.

This is the PLANNING / fake-proof model layer ONLY. It implements NO plan
builder (that is ``stage30_9_2_resume_dip_filtered_live_plan``) and NO
proof / composition (that is ``stage30_9_2_resume_fake_proof``). It runs NO
gate, wires into NO runtime, makes NO live provider call, sends NO Discord
message, reads NO process environment, opens NO network connection, opens NO
database, writes NO file, performs NO transport-layer veto, reserves NO
dispatch, and edits NO Stage 28 suppression / Stage 30.3 / Stage 30.4
runtime orchestrator. Stage 30.9.2_RESUME planning is fake / offline only;
the actual live ceremony remains a SEPARATE, explicitly operator-authorized
step that this slice does NOT perform.

The resume plan pins, in auditable form, that for THIS planning / fake-proof
step every live-affecting axis is held closed:

  * ``live_allowed`` / ``dispatch_allowed`` / ``env_read_allowed`` /
    ``provider_call_allowed`` / ``discord_send_allowed`` -- all ``False``.

so the dip-filtered live proof can be assembled and proven offline BEFORE
the actual ceremony is ever operator-authorized.

The per-candidate proof record echoes the Stage 30.10.1 classifier's
closed-set ``eligibility_decision`` / ``eligibility_reason`` and the Stage
30.10.2 gate's closed-set ``gate_decision`` / ``gate_reason`` verbatim, plus
the Stage 30.10.3 artifact projection's five derived booleans
(``dispatch_reservation_would_be_attempted`` /
``suppressed_before_dispatch_reservation`` / ``dispatch_failure_recorded`` /
``transport_veto_used`` / ``payload_refused_used``) and the source
``artifact_schema_version``. This module does NOT re-pin the Stage 30.10.1 /
30.10.2 / 30.10.3 token sets (they live in those slices' models); it pins
ONLY the resume schema version, the required-gate-stack closed set, and the
resume plan / record / summary field shapes.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.8.1 / 30.9.1 / 30.10.3
    model modules); the records carry only projected safe scalars, not
    embedded Stage 30.10 record types.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No filesystem write.
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
# Minor version + resume identity
# ---------------------------------------------------------------------------


STAGE30_9_2_MINOR_VERSION: str = "30.9.2"


# The Stage 30.9.2_RESUME token. Names that the PAUSED Stage 30.9.2 live
# proof is resuming as a dip-filtered path; mirrors the Stage 30.10.3
# ``STAGE30_10_3_NEXT_ALLOWED_STAGE`` value BY VALUE (this module imports no
# Stage 30.10 manifest).
STAGE30_9_2_RESUME_ID: str = "30.9.2_RESUME"


# The Stage 30.9.2_RESUME dip-filtered resume proof schema version. Names the
# offline resume proof record / summary shape; distinct from the Stage 30.8 /
# 30.9.1 / 30.10.3 schema versions. Mirrored BY VALUE by the Stage 30.9.2
# manifest section; this module imports no Stage 30.9 manifest.
STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION: str = (
    "stage30_9_2_v0_dip_filtered_resume_proof"
)


# The prior stage this resume builds on: the final Stage 30.10 fake / offline
# proof (the gate artifact integration proof).
STAGE30_9_2_PRIOR_STAGE: str = "30.10.3"


# ---------------------------------------------------------------------------
# Required dip-gate stack (closed set)
# ---------------------------------------------------------------------------
#
# The dip-filtered live proof may proceed only AFTER the completed Stage
# 30.10 dip-gate stack has ruled each candidate. The resume plan carries
# exactly these three required gate-stack stages (safe paraphrase labels;
# NOT secret / host / transport forms).


STAGE30_9_2_GATE_STACK_REQUIRED: Tuple[str, ...] = (
    "30.10.1 offline tier-dip eligibility classifier",
    "30.10.2 optional pre-dispatch tier-dip gate",
    "30.10.3 gate artifact projection",
)


# ---------------------------------------------------------------------------
# Immutable model: dip-filtered resume plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9_2DipFilteredResumePlan:
    """Immutable Stage 30.9.2_RESUME dip-filtered live proof plan.

    A passive planning / readiness carrier (never a hidden env read). It
    records WHICH committed gate stack the resume is built against and pins,
    in auditable form, that for the planning / fake-proof step every
    live-affecting axis is held closed. The actual live ceremony is a
    SEPARATE, explicitly operator-authorized step that consumes this plan; it
    is never auto-run from the plan.

      * ``resume_id``             -- the safe resume token (``30.9.2_RESUME``).
      * ``required_head_sha``     -- the committed HEAD the resume plan is
                                     built against (the gate-stack proof
                                     commit); a safe-shape hex id.
      * ``prior_stage``           -- the prior stage this resume builds on
                                     (the final Stage 30.10 fake proof).
      * ``gate_stack_required``   -- the ordered required dip-gate stack
                                     stages (a subset of
                                     ``STAGE30_9_2_GATE_STACK_REQUIRED``).
      * ``live_allowed``          -- whether the live ceremony is allowed in
                                     THIS step (``False`` for planning).
      * ``dispatch_allowed``      -- whether dispatch reservation is allowed
                                     in THIS step (``False`` for planning).
      * ``env_read_allowed``      -- whether an env read is allowed in THIS
                                     step (``False`` for planning).
      * ``provider_call_allowed`` -- whether a live provider call is allowed
                                     in THIS step (``False`` for planning).
      * ``discord_send_allowed``  -- whether a Discord send is allowed in
                                     THIS step (``False`` for planning).
      * ``created_at_utc``        -- caller-injected ISO-8601 UTC timestamp;
                                     NEVER a wall-clock read.
    """

    resume_id: str
    required_head_sha: str
    prior_stage: str
    gate_stack_required: Tuple[str, ...]
    live_allowed: bool
    dispatch_allowed: bool
    env_read_allowed: bool
    provider_call_allowed: bool
    discord_send_allowed: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-candidate dip-filtered resume proof record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9_2DipFilteredCandidateProofRecord:
    """Immutable per-candidate Stage 30.9.2_RESUME dip-filtered proof record.

    The resume fake proof emits exactly one of these per candidate the Stage
    30.10 dip-gate stack evaluated. It echoes the candidate identity, the
    Stage 30.10.1 classifier's closed-set ``eligibility_decision`` /
    ``eligibility_reason``, the Stage 30.10.2 gate's closed-set
    ``gate_decision`` / ``gate_reason``, the source Stage 30.10.3
    ``artifact_schema_version``, and the five Stage 30.10.3 derived booleans
    that make the candidate's pre-dispatch fate auditable. Carries only safe
    scalars + a caller-injected timestamp; no secret, no raw payload, no
    host, no transport destination, no env value.

      * ``candidate_id`` / ``token_mint``  -- echoed safe-shape ids.
      * ``eligibility_decision`` / ``eligibility_reason``
                                           -- echoed Stage 30.10.1 closed-set
                                              tokens.
      * ``gate_decision`` / ``gate_reason``-- echoed Stage 30.10.2 closed-set
                                              tokens.
      * ``artifact_schema_version``        -- the echoed Stage 30.10.3 gate
                                              artifact schema version the
                                              record is projected from.
      * ``dispatch_reservation_would_be_attempted``
                                           -- ``True`` ONLY for a gate
                                              ``PASS_TO_DISPATCH`` candidate
                                              (the only candidate that may
                                              proceed toward the private
                                              compact dispatch).
      * ``suppressed_before_dispatch_reservation``
                                           -- ``True`` for every non-pass
                                              candidate (a clean no-send
                                              BEFORE reservation); the exact
                                              complement of the field above.
      * ``dispatch_failure_recorded``      -- ALWAYS ``False``: a pre-dispatch
                                              skip is NEVER a dispatch failure.
      * ``transport_veto_used``            -- ALWAYS ``False``: the dip gate
                                              is NEVER a transport-layer veto.
      * ``payload_refused_used``           -- ALWAYS ``False``: a normal
                                              non-dip skip NEVER reuses the
                                              transport ``PAYLOAD_REFUSED``
                                              veto.
      * ``created_at_utc``                 -- caller-injected ISO-8601 UTC
                                              timestamp; NEVER a wall-clock
                                              read.
    """

    candidate_id: str
    token_mint: str
    eligibility_decision: str
    eligibility_reason: str
    gate_decision: str
    gate_reason: str
    artifact_schema_version: str
    dispatch_reservation_would_be_attempted: bool
    suppressed_before_dispatch_reservation: bool
    dispatch_failure_recorded: bool
    transport_veto_used: bool
    payload_refused_used: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: dip-filtered resume proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9_2DipFilteredResumeProofSummary:
    """Immutable Stage 30.9.2_RESUME dip-filtered resume proof tally.

    A passive summary of one offline dip-filtered candidate-stream run. It
    proves, by counting, that ONLY eligible dips would proceed toward the
    private compact dispatch and that every non-dip / invalid candidate is
    suppressed BEFORE dispatch reservation -- and that NO candidate is a
    dispatch failure, uses a transport veto, or uses the ``PAYLOAD_REFUSED``
    veto. It also pins, from the resume plan, that the live ceremony / provider
    call / Discord send remain held closed in THIS step. Carries only
    non-negative integer counts + boolean gating flags + a caller-injected
    timestamp; no secret, no payload, no host, no transport destination.

      * ``resume_id``                     -- the safe resume token.
      * ``candidates_seen``               -- total candidates evaluated.
      * ``candidates_passed``             -- count with gate
                                             ``PASS_TO_DISPATCH``.
      * ``candidates_skipped``            -- count with gate
                                             ``SKIP_BEFORE_DISPATCH``.
      * ``invalid_inputs``                -- count with gate ``INVALID_INPUT``.
      * ``dispatch_attempts_reserved``    -- attempts that would be reserved
                                             (equals ``candidates_passed``;
                                             only eligible dips).
      * ``dispatch_attempts_suppressed_before_reservation``
                                          -- attempts suppressed BEFORE
                                             reservation (equals
                                             ``candidates_skipped`` +
                                             ``invalid_inputs``).
      * ``dispatch_failures_recorded``    -- candidates flagged as a dispatch
                                             failure (ALWAYS 0).
      * ``transport_veto_count``          -- candidates flagged as a transport
                                             veto (ALWAYS 0).
      * ``payload_refused_count``         -- candidates flagged as
                                             ``PAYLOAD_REFUSED`` (ALWAYS 0).
      * ``live_allowed``                  -- echoed plan flag (``False`` for
                                             planning / fake proof).
      * ``provider_call_allowed``         -- echoed plan flag (``False`` for
                                             planning / fake proof).
      * ``discord_send_allowed``          -- echoed plan flag (``False`` for
                                             planning / fake proof).
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp.
    """

    resume_id: str
    candidates_seen: int
    candidates_passed: int
    candidates_skipped: int
    invalid_inputs: int
    dispatch_attempts_reserved: int
    dispatch_attempts_suppressed_before_reservation: int
    dispatch_failures_recorded: int
    transport_veto_count: int
    payload_refused_count: int
    live_allowed: bool
    provider_call_allowed: bool
    discord_send_allowed: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def resume_plan_field_names() -> Tuple[str, ...]:
    """Return the resume plan field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9_2DipFilteredResumePlan))


def candidate_proof_record_field_names() -> Tuple[str, ...]:
    """Return the per-candidate proof record field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_9_2DipFilteredCandidateProofRecord)
    )


def resume_proof_summary_field_names() -> Tuple[str, ...]:
    """Return the resume proof summary field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_9_2DipFilteredResumeProofSummary)
    )


__all__ = (
    # Minor version + resume identity.
    "STAGE30_9_2_MINOR_VERSION",
    "STAGE30_9_2_RESUME_ID",
    "STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION",
    "STAGE30_9_2_PRIOR_STAGE",
    # Required dip-gate stack.
    "STAGE30_9_2_GATE_STACK_REQUIRED",
    # Models.
    "Stage30_9_2DipFilteredResumePlan",
    "Stage30_9_2DipFilteredCandidateProofRecord",
    "Stage30_9_2DipFilteredResumeProofSummary",
    # Field-name helpers.
    "resume_plan_field_names",
    "candidate_proof_record_field_names",
    "resume_proof_summary_field_names",
)
