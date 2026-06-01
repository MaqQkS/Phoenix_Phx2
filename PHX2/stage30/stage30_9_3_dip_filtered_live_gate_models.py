"""Stage 30.9.3 dip-filtered live dispatch integration models.

Stage 30.9.3 ships the passive, pure, stdlib-only MODEL layer for the
dip-filtered live dispatch integration SEAM: the per-candidate assembled
live-context carrier the seam evaluates (the input), the per-candidate
live-gate decision the seam emits (the projected verdict), and the rolled-up
integration result the orchestrator tallies. Stage 30.9.3 is the REAL
integration seam the later controlled live ceremony will reuse -- but in THIS
slice it is exercised with fakes / offline candidates + an injected fake
dispatch sink ONLY. It runs NO live provider call, sends NO Discord message,
reads NO process environment, opens NO network connection, opens NO database,
writes NO file, performs NO transport-layer veto, reserves NO real dispatch,
and edits NO Stage 28 suppression / Stage 30.3 / Stage 30.4 runtime
orchestrator.

The decision record echoes the Stage 30.10.1 classifier's closed-set
``eligibility_decision`` / ``eligibility_reason`` and the Stage 30.10.2 gate's
closed-set ``gate_decision`` / ``gate_reason`` verbatim, plus the Stage
30.10.3 artifact projection's derived booleans and the source
``artifact_schema_version``. This module does NOT re-pin the Stage 30.10.1 /
30.10.2 / 30.10.3 token sets (they live in those slices' models); it pins
ONLY the Stage 30.9.3 integration schema version and the input / decision /
result field shapes.

Two transport-safety invariants are carried verbatim from the Stage 30.10.3
projection and are ALWAYS held for every candidate:

  * a candidate may proceed toward the private compact dispatch ONLY when its
    gate decision is ``PASS_TO_DISPATCH`` (``dispatch_reservation_allowed`` is
    ``True`` IFF that holds); every non-pass candidate is suppressed cleanly
    BEFORE dispatch reservation (``suppressed_before_dispatch_reservation`` is
    its exact complement); and
  * a pre-dispatch gate skip is NEVER a dispatch failure
    (``dispatch_failure_recorded``), NEVER a transport-layer veto
    (``transport_veto_used``), and NEVER a transport ``PAYLOAD_REFUSED`` veto
    (``payload_refused_used``) -- all three are ALWAYS ``False``.

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.9.2 / 30.10.1 / 30.10.3
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
from decimal import Decimal
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + integration schema identity
# ---------------------------------------------------------------------------


STAGE30_9_3_MINOR_VERSION: str = "30.9.3"


# The Stage 30.9.3 dip-filtered live gate integration schema version. Names
# the live-gate decision / integration-result shape; distinct from the Stage
# 30.9.2 resume proof schema version and the Stage 30.10.3 artifact schema
# version. Mirrored BY VALUE by the Stage 30.9.3 manifest section; this module
# imports no Stage 30.9 manifest.
STAGE30_9_3_INTEGRATION_SCHEMA_VERSION: str = (
    "stage30_9_3_v0_dip_filtered_live_gate"
)


# ---------------------------------------------------------------------------
# Immutable model: assembled live candidate / context input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9_3LiveGateInput:
    """Immutable assembled live candidate / context carrier the seam evaluates.

    A passive carrier of the ALREADY-ASSEMBLED live candidate signals the
    Stage 30.9.3 adapter turns into a Stage 30.10.1 eligibility input WITHOUT
    any provider call. Carries only safe scalars: opaque ids, closed-set
    status tokens / display tier token, ``Decimal`` magnitudes, an optional
    verified flag, an optional opaque candidate ref, and a caller-injected
    ISO-8601 UTC timestamp. No secret, no raw payload, no host, no transport
    destination.

      * ``candidate_id``                -- the safe-shape candidate id.
      * ``token_mint``                  -- the safe-shape token mint.
      * ``tier_token``                  -- the Stage 30.1 tier token (display
                                           ``Tier N`` form or the normalized
                                           code), or ``None``.
      * ``drawdown_from_ath``           -- the drawdown magnitude as a
                                           ``Decimal``, or ``None``.
      * ``migration_status``            -- the migration status token, or
                                           ``None``.
      * ``ath_status``                  -- the ATH status token, or ``None``.
      * ``market_context_status``       -- the current market context status
                                           token, or ``None``.
      * ``current_market_cap_usd``      -- the current market cap as a
                                           ``Decimal``, or ``None``.
      * ``post_migration_ath_verified`` -- whether the ATH is verified to be
                                           post-migration (``True`` /
                                           ``False`` / ``None``).
      * ``candidate_ref``               -- an OPTIONAL opaque reference to the
                                           original live candidate (a safe id
                                           only; never a raw payload), or
                                           ``None``.
      * ``created_at_utc``              -- a caller-injected ISO-8601 UTC
                                           timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    tier_token: Optional[str]
    drawdown_from_ath: Optional[Decimal]
    migration_status: Optional[str]
    ath_status: Optional[str]
    market_context_status: Optional[str]
    current_market_cap_usd: Optional[Decimal]
    post_migration_ath_verified: Optional[bool]
    candidate_ref: Optional[str]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-candidate live gate decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9_3LiveGateDecision:
    """Immutable per-candidate Stage 30.9.3 dip-filtered live gate decision.

    The Stage 30.9.3 adapter emits exactly one of these per candidate the
    Stage 30.10 dip-gate stack evaluated. It echoes the candidate identity,
    the Stage 30.10.1 classifier's closed-set ``eligibility_decision`` /
    ``eligibility_reason``, the Stage 30.10.2 gate's closed-set
    ``gate_decision`` / ``gate_reason``, the source Stage 30.10.3
    ``artifact_schema_version``, and the derived pre-dispatch booleans that
    make the candidate's fate auditable. Carries only safe scalars + a
    caller-injected timestamp; no secret, no raw payload, no host, no
    transport destination, no env value.

      * ``candidate_id`` / ``token_mint``  -- echoed safe-shape ids.
      * ``eligibility_decision`` / ``eligibility_reason``
                                           -- echoed Stage 30.10.1 closed-set
                                              tokens.
      * ``gate_decision`` / ``gate_reason``-- echoed Stage 30.10.2 closed-set
                                              tokens.
      * ``artifact_schema_version``        -- the echoed Stage 30.10.3 gate
                                              artifact schema version the
                                              decision is projected from.
      * ``dispatch_reservation_allowed``   -- ``True`` ONLY for a gate
                                              ``PASS_TO_DISPATCH`` candidate
                                              (the only candidate that may
                                              reserve a dispatch / proceed
                                              toward the private compact send).
      * ``suppressed_before_dispatch_reservation``
                                           -- ``True`` for every non-pass
                                              candidate (a clean no-send
                                              BEFORE reservation); the exact
                                              complement of the field above.
      * ``dispatch_failure_recorded``      -- ALWAYS ``False``: a pre-dispatch
                                              skip is NEVER a dispatch failure.
      * ``transport_veto_used``            -- ALWAYS ``False``: the dip gate is
                                              NEVER a transport-layer veto.
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
    dispatch_reservation_allowed: bool
    suppressed_before_dispatch_reservation: bool
    dispatch_failure_recorded: bool
    transport_veto_used: bool
    payload_refused_used: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: dip-filtered live gate integration result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_9_3LiveGateIntegrationResult:
    """Immutable Stage 30.9.3 dip-filtered live gate integration tally.

    A passive summary of one bounded candidate-stream run through the Stage
    30.9.3 orchestrator. It proves, by counting, that ONLY eligible dips would
    reserve a dispatch / drive the private compact send and that every non-dip
    / invalid candidate is suppressed BEFORE dispatch reservation -- and that
    NO candidate is a dispatch failure, uses a transport veto, or uses the
    ``PAYLOAD_REFUSED`` veto. Carries only non-negative integer counts + a
    caller-injected timestamp; no secret, no payload, no host, no transport
    destination.

      * ``candidates_seen``                  -- total candidates taken from the
                                                stream.
      * ``candidates_evaluated``             -- candidates actually run through
                                                the dip gate.
      * ``candidates_passed_gate``           -- count with gate
                                                ``PASS_TO_DISPATCH``.
      * ``candidates_skipped_before_dispatch``
                                             -- count with gate
                                                ``SKIP_BEFORE_DISPATCH``.
      * ``invalid_inputs``                   -- count with gate
                                                ``INVALID_INPUT`` (plus any
                                                non-conforming stream item --
                                                fail closed into invalid).
      * ``dispatch_attempts_reserved``       -- dispatch attempts reserved
                                                (only eligible dips, bounded by
                                                the dispatch cap).
      * ``dispatch_failures_recorded``       -- candidates flagged as a
                                                dispatch failure (ALWAYS 0).
      * ``transport_veto_count``             -- candidates flagged as a
                                                transport veto (ALWAYS 0).
      * ``payload_refused_count``            -- candidates flagged as
                                                ``PAYLOAD_REFUSED`` (ALWAYS 0).
      * ``would_send_private_discord_count`` -- private compact dispatch sink
                                                calls made (only eligible dips,
                                                bounded by the private-send
                                                cap).
      * ``created_at_utc``                   -- caller-injected ISO-8601 UTC
                                                timestamp.
    """

    candidates_seen: int
    candidates_evaluated: int
    candidates_passed_gate: int
    candidates_skipped_before_dispatch: int
    invalid_inputs: int
    dispatch_attempts_reserved: int
    dispatch_failures_recorded: int
    transport_veto_count: int
    payload_refused_count: int
    would_send_private_discord_count: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def live_gate_input_field_names() -> Tuple[str, ...]:
    """Return the live gate input field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9_3LiveGateInput))


def live_gate_decision_field_names() -> Tuple[str, ...]:
    """Return the live gate decision field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9_3LiveGateDecision))


def integration_result_field_names() -> Tuple[str, ...]:
    """Return the integration result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_9_3LiveGateIntegrationResult))


__all__ = (
    # Minor version + integration schema identity.
    "STAGE30_9_3_MINOR_VERSION",
    "STAGE30_9_3_INTEGRATION_SCHEMA_VERSION",
    # Models.
    "Stage30_9_3LiveGateInput",
    "Stage30_9_3LiveGateDecision",
    "Stage30_9_3LiveGateIntegrationResult",
    # Field-name helpers.
    "live_gate_input_field_names",
    "live_gate_decision_field_names",
    "integration_result_field_names",
)
