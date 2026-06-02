"""Stage 30.11.2 offline runtime gate seam models.

Stage 30.11.2 ships the passive, pure, stdlib-only MODEL layer for the offline
runtime gate seam: the bounded-runtime config the seam is parameterized by, the
per-candidate runtime outcome the seam emits, the rolled-up offline proof
summary, the fake dispatch-acknowledgement result the injected fake sink
returns, and the closed-set runtime decision / reason vocabularies they share,
plus the pure safe-shape / validation helpers the seam composes.

This module is the MODEL layer ONLY. It implements NO seam (that is
``stage30_11_2_runtime_gate_seam``), runs NO bridge, runs NO dip gate, calls NO
dispatch sink, wires into NO runtime, makes NO live provider call, sends NO
Discord message, reads NO process environment, opens NO network connection,
opens NO database, writes NO file, reserves NO real dispatch, reads NO wall
clock (the seam injects its clock), and edits NO Stage 28 / Stage 29 / Stage
30.3 / Stage 30.4 production file. Stage 30.11.2 is fake / offline only.

The runtime seam decides, per already-assembled live candidate snapshot, one of
exactly seven closed-set runtime decisions:

  * ``DISPATCHED_AFTER_DIP_GATE_PASS`` -- the candidate bridged into a committed
    Stage 30.9.3 live gate input AND the committed dip gate ruled
    ``PASS_TO_DISPATCH``, so the injected FAKE dispatch sink was called (reason
    ``PASS_TO_FAKE_DISPATCH``). This is the ONLY decision that calls the sink.
  * ``SUPPRESSED_BY_BRIDGE`` -- the Stage 30.11.1 bridge skipped (missing
    context) or failed closed (invalid identity), so there is no gate input and
    no dispatch (reason ``BRIDGE_SKIPPED_OR_INVALID``).
  * ``SUPPRESSED_BY_DIP_GATE`` -- the candidate bridged but the committed dip
    gate did NOT rule ``PASS_TO_DISPATCH`` (a normal non-dip skip / invalid gate
    verdict), so it is suppressed cleanly BEFORE dispatch (reason
    ``DIP_GATE_SKIPPED``).
  * ``STOPPED_BY_CANDIDATE_CAP`` -- the bounded candidate cap was reached, so the
    cut-off candidate is recorded and processing stops (reason
    ``CANDIDATE_CAP_REACHED``).
  * ``STOPPED_BY_DISPATCH_CAP`` -- the bounded dispatch cap was reached, so the
    cut-off candidate is recorded and processing stops (reason
    ``DISPATCH_CAP_REACHED``).
  * ``STOPPED_BY_RUNTIME_SECONDS`` -- the wall-clock ``max_runtime_seconds`` bound
    elapsed (measured via the injected clock), so the cut-off candidate is
    recorded and processing stops (reason ``RUNTIME_SECONDS_REACHED``).
  * ``INVALID_RUNTIME_INPUT`` -- a non-conforming stream item (not a
    ``Stage30_11LiveCandidateSnapshot``) fails closed BEFORE any bridge / gate /
    dispatch (reason ``INVALID_CONFIG_OR_INPUT``). The same reason names an
    invalid runtime config the seam rejects up front.

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.9.3 / 30.10.1 / 30.10.3 model
    modules); the records carry only safe scalars / closed-set tokens, not
    embedded Stage 30.9 / 30.10 / 30.11 record types.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; ``created_at_utc`` is caller-injected and
    the runtime clock is injected into the seam, never read here.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Tuple


# ---------------------------------------------------------------------------
# Minor version + runtime gate schema identity
# ---------------------------------------------------------------------------


STAGE30_11_2_MINOR_VERSION: str = "30.11.2"


# The Stage 30.11.2 runtime gate seam schema version. Names the config /
# outcome / summary / fake-result shape; distinct from the Stage 30.11.1 bridge
# schema version, the Stage 30.9.3 integration schema version, and the Stage
# 30.10.3 artifact schema version. Mirrored BY VALUE by the Stage 30.11
# manifest section; this module imports no Stage 30.11 manifest.
STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION: str = (
    "stage30_11_2_v0_runtime_gate_seam"
)


# ---------------------------------------------------------------------------
# Closed-set: runtime decision
# ---------------------------------------------------------------------------
#
# Exactly one runtime decision per recorded outcome.
# ``DISPATCHED_AFTER_DIP_GATE_PASS`` is the only decision on which the injected
# fake dispatch sink was called. Mirrored BY VALUE by the Stage 30.11 manifest.


RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS: str = (
    "DISPATCHED_AFTER_DIP_GATE_PASS"
)
RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE: str = "SUPPRESSED_BY_BRIDGE"
RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE: str = "SUPPRESSED_BY_DIP_GATE"
RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP: str = "STOPPED_BY_CANDIDATE_CAP"
RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP: str = "STOPPED_BY_DISPATCH_CAP"
RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS: str = "STOPPED_BY_RUNTIME_SECONDS"
RUNTIME_DECISION_INVALID_RUNTIME_INPUT: str = "INVALID_RUNTIME_INPUT"


STAGE30_11_2_RUNTIME_DECISIONS: Tuple[str, ...] = (
    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
    RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
    RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP,
    RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP,
    RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS,
    RUNTIME_DECISION_INVALID_RUNTIME_INPUT,
)


# The single decision on which the injected fake dispatch sink was called.
STAGE30_11_2_RUNTIME_DISPATCH_DECISION: str = (
    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS
)


def is_runtime_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set runtime decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_2_RUNTIME_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: runtime reason
# ---------------------------------------------------------------------------
#
# Exactly one runtime reason per runtime decision. ``PASS_TO_FAKE_DISPATCH`` is
# the only reason that accompanies a dispatched candidate. Mirrored BY VALUE by
# the Stage 30.11 manifest.


RUNTIME_REASON_PASS_TO_FAKE_DISPATCH: str = "PASS_TO_FAKE_DISPATCH"
RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID: str = "BRIDGE_SKIPPED_OR_INVALID"
RUNTIME_REASON_DIP_GATE_SKIPPED: str = "DIP_GATE_SKIPPED"
RUNTIME_REASON_CANDIDATE_CAP_REACHED: str = "CANDIDATE_CAP_REACHED"
RUNTIME_REASON_DISPATCH_CAP_REACHED: str = "DISPATCH_CAP_REACHED"
RUNTIME_REASON_RUNTIME_SECONDS_REACHED: str = "RUNTIME_SECONDS_REACHED"
RUNTIME_REASON_INVALID_CONFIG_OR_INPUT: str = "INVALID_CONFIG_OR_INPUT"


STAGE30_11_2_RUNTIME_REASONS: Tuple[str, ...] = (
    RUNTIME_REASON_PASS_TO_FAKE_DISPATCH,
    RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID,
    RUNTIME_REASON_DIP_GATE_SKIPPED,
    RUNTIME_REASON_CANDIDATE_CAP_REACHED,
    RUNTIME_REASON_DISPATCH_CAP_REACHED,
    RUNTIME_REASON_RUNTIME_SECONDS_REACHED,
    RUNTIME_REASON_INVALID_CONFIG_OR_INPUT,
)


# The single reason that accompanies the only dispatch decision.
STAGE30_11_2_RUNTIME_DISPATCH_REASON: str = RUNTIME_REASON_PASS_TO_FAKE_DISPATCH


def is_runtime_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set runtime reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_2_RUNTIME_REASONS


# ---------------------------------------------------------------------------
# Not-evaluated sentinel (runtime-local)
# ---------------------------------------------------------------------------
#
# A runtime-local sentinel for the ``bridge_decision`` / ``gate_decision`` axes
# of an outcome where the bridge / gate was NOT run for that candidate (a cap /
# runtime stop, or a non-conforming stream item). It is intentionally NOT a
# Stage 30.11.1 bridge decision nor a Stage 30.9.3 / 30.10.2 gate decision, so a
# reader can never mistake a not-evaluated axis for a real verdict.


STAGE30_11_2_NOT_EVALUATED: str = "NOT_EVALUATED"


# ---------------------------------------------------------------------------
# Pure safe-shape / validation helpers
# ---------------------------------------------------------------------------


def _is_positive_number(value: object) -> bool:
    """Return ``True`` iff ``value`` is a strictly-positive, FINITE ``Decimal``
    / ``int`` (and NOT a ``bool``).

    Pure / TOTAL; never raises. Non-finite ``Decimal`` values (``NaN`` /
    ``sNaN`` / ``Infinity`` / ``-Infinity``) are rejected up front via the
    non-signaling ``Decimal.is_finite`` -- so a signaling ``sNaN`` never reaches
    a comparison and no ``decimal.InvalidOperation`` can escape, and an
    ``Infinity`` is never mistaken for a valid positive bound. ``float`` (incl.
    ``float('nan')`` / ``float('inf')``) and every other type are rejected by
    ``isinstance``. Only a finite ``Decimal`` / ``int`` reaches the ``> 0``
    comparison, where it cannot signal.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        # Plain ``int`` is always finite; the comparison cannot signal.
        return value > 0
    if isinstance(value, Decimal):
        # ``is_finite`` is non-signaling (safe even for ``sNaN``); guard the
        # comparison so only a finite Decimal reaches ``> 0``.
        return value.is_finite() and value > 0
    return False


def _is_positive_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a strictly-positive ``int`` (and NOT a
    ``bool``). Pure / total; never raises.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-negative ``int`` (and NOT a
    ``bool``). Pure / total; never raises.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


# ---------------------------------------------------------------------------
# Immutable model: bounded runtime gate config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11RuntimeGateConfig:
    """Immutable bounded-runtime config the Stage 30.11.2 seam is parameterized
    by.

    A passive carrier of the three hard bounds the runtime seam enforces plus a
    caller-injected provenance timestamp. Carries only safe scalars; no secret,
    no payload, no host, no transport destination.

      * ``max_runtime_seconds`` -- the wall-clock cap (a positive ``Decimal`` /
                                    ``int``); the seam stops cleanly once the
                                    INJECTED clock reports this many seconds have
                                    elapsed. The seam NEVER reads a wall clock
                                    itself.
      * ``max_candidates``      -- the positive cap on candidates evaluated
                                    through the pipeline.
      * ``max_dispatches``      -- the non-negative cap on fake dispatch
                                    attempts; once reached the seam stops cleanly.
      * ``created_at_utc``      -- a caller-injected ISO-8601 UTC provenance
                                    timestamp for the config; NEVER a wall-clock
                                    read.

    The model is passive: it performs NO validation in ``__init__`` and raises
    nothing. ``is_valid_runtime_gate_config`` is the pure validator the seam
    consults to fail closed on an invalid config.
    """

    max_runtime_seconds: Decimal
    max_candidates: int
    max_dispatches: int
    created_at_utc: str


def is_valid_runtime_gate_config(config: object) -> bool:
    """Return ``True`` iff ``config`` is a structurally-valid runtime gate
    config: a ``Stage30_11RuntimeGateConfig`` with a positive, FINITE
    ``max_runtime_seconds``, a positive ``int`` ``max_candidates``, and a
    non-negative ``int`` ``max_dispatches``.

    Pure / TOTAL; never raises -- a non-finite ``Decimal`` (``NaN`` / ``sNaN`` /
    ``Infinity`` / ``-Infinity``), a ``float``, a ``bool``, or any other malformed
    field fails closed to ``False`` without a ``decimal.InvalidOperation`` /
    ``TypeError`` / ``ValueError`` escaping (so the deterministic
    ``max_runtime_seconds`` bound can never be a non-finite value). The seam
    consults this BEFORE processing any candidate and fails closed (raises its
    own caller-shape error, dispatches nothing) when it returns ``False``.
    """
    if not isinstance(config, Stage30_11RuntimeGateConfig):
        return False
    return (
        _is_positive_number(config.max_runtime_seconds)
        and _is_positive_int(config.max_candidates)
        and _is_nonnegative_int(config.max_dispatches)
    )


# ---------------------------------------------------------------------------
# Immutable model: per-candidate runtime outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11RuntimeGateCandidateOutcome:
    """Immutable per-candidate Stage 30.11.2 runtime outcome.

    The seam emits exactly one of these per recorded candidate (an evaluated
    candidate OR the single cut-off candidate that triggered a cap / runtime
    stop). It echoes the candidate identity, pins the closed-set
    ``runtime_decision`` / ``runtime_reason``, carries the upstream bridge /
    gate decision (or the ``NOT_EVALUATED`` sentinel where the bridge / gate was
    not run), and records whether the FAKE dispatch was attempted / accepted.
    Carries only safe scalars + a caller-injected timestamp; no secret, no raw
    payload, no host, no transport destination, no env value.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids (empty for a
                                             non-conforming stream item).
      * ``bridge_decision``               -- the Stage 30.11.1 bridge decision,
                                             or ``NOT_EVALUATED``.
      * ``gate_decision``                 -- the Stage 30.9.3 / 30.10.2 gate
                                             decision, or ``NOT_EVALUATED``.
      * ``runtime_decision``              -- one of
                                             ``STAGE30_11_2_RUNTIME_DECISIONS``.
      * ``runtime_reason``                -- one of
                                             ``STAGE30_11_2_RUNTIME_REASONS``.
      * ``dispatch_attempted``            -- ``True`` ONLY when the injected fake
                                             dispatch sink was called (a gate
                                             ``PASS_TO_DISPATCH`` candidate).
      * ``dispatch_accepted``             -- ``True`` ONLY when the fake sink
                                             acknowledged the attempt.
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    bridge_decision: str
    gate_decision: str
    runtime_decision: str
    runtime_reason: str
    dispatch_attempted: bool
    dispatch_accepted: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: runtime gate proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11RuntimeGateSummary:
    """Immutable offline Stage 30.11.2 runtime gate proof tally.

    A passive summary of one bounded candidate-stream run through the seam. It
    proves, by counting, that ONLY a candidate that bridged AND passed the
    committed dip gate drove a FAKE dispatch, that every bridge skip / non-dip /
    invalid candidate was suppressed cleanly BEFORE dispatch, and that the
    candidate / dispatch / wall-clock bounds stopped the run cleanly. Carries
    only non-negative integer counts + a caller-injected timestamp; no secret,
    no payload, no host, no transport destination.

      * ``candidates_seen``           -- candidates actually evaluated through
                                         the pipeline (a cap / runtime cut-off
                                         candidate is NOT counted here).
      * ``bridged``                   -- count the Stage 30.11.1 bridge
                                         BRIDGED_TO_LIVE_GATE_INPUT.
      * ``gate_passed``               -- count the committed dip gate ruled
                                         PASS_TO_DISPATCH.
      * ``dispatch_attempted``        -- count the injected fake sink was called.
      * ``dispatch_accepted``         -- count the fake sink acknowledged.
      * ``suppressed_by_bridge``      -- count the bridge skipped / failed closed
                                         (SUPPRESSED_BY_BRIDGE).
      * ``suppressed_by_gate``        -- count bridged but the gate did NOT pass
                                         (SUPPRESSED_BY_DIP_GATE).
      * ``stopped_by_candidate_cap``  -- 1 iff the candidate cap stopped the run.
      * ``stopped_by_dispatch_cap``   -- 1 iff the dispatch cap stopped the run.
      * ``stopped_by_runtime_seconds``-- 1 iff the wall-clock bound stopped the
                                         run.
      * ``invalid_inputs``            -- count of bridge INVALID_BRIDGE_INPUT
                                         results plus non-conforming stream items
                                         (INVALID_RUNTIME_INPUT).
      * ``created_at_utc``            -- caller-injected ISO-8601 UTC timestamp.
    """

    candidates_seen: int
    bridged: int
    gate_passed: int
    dispatch_attempted: int
    dispatch_accepted: int
    suppressed_by_bridge: int
    suppressed_by_gate: int
    stopped_by_candidate_cap: int
    stopped_by_dispatch_cap: int
    stopped_by_runtime_seconds: int
    invalid_inputs: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: fake dispatch acknowledgement result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11FakeDispatchResult:
    """Immutable fake dispatch acknowledgement result.

    The return value of the INJECTED fake dispatch sink: a passive ack that
    records whether the fake dispatch was accepted plus the echoed candidate
    identity. It is NOT a real transport result -- it carries no status code, no
    response body, no host, no transport destination, no secret. The real
    private compact dispatch path is a SEPARATE, operator-authorized step that
    Stage 30.11.2 does not build.

      * ``accepted``        -- whether the fake sink accepted the attempt.
      * ``candidate_id``    -- echoed safe-shape candidate id.
      * ``token_mint``      -- echoed safe-shape token mint.
      * ``created_at_utc``  -- caller-injected ISO-8601 UTC timestamp; NEVER a
                               wall-clock read.
    """

    accepted: bool
    candidate_id: str
    token_mint: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def runtime_gate_config_field_names() -> Tuple[str, ...]:
    """Return the runtime gate config field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11RuntimeGateConfig))


def runtime_gate_candidate_outcome_field_names() -> Tuple[str, ...]:
    """Return the runtime gate candidate outcome field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11RuntimeGateCandidateOutcome)
    )


def runtime_gate_summary_field_names() -> Tuple[str, ...]:
    """Return the runtime gate summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11RuntimeGateSummary))


def fake_dispatch_result_field_names() -> Tuple[str, ...]:
    """Return the fake dispatch result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11FakeDispatchResult))


__all__ = (
    # Minor version + runtime gate schema identity.
    "STAGE30_11_2_MINOR_VERSION",
    "STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION",
    # Runtime decisions.
    "RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS",
    "RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE",
    "RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE",
    "RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP",
    "RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP",
    "RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS",
    "RUNTIME_DECISION_INVALID_RUNTIME_INPUT",
    "STAGE30_11_2_RUNTIME_DECISIONS",
    "STAGE30_11_2_RUNTIME_DISPATCH_DECISION",
    "is_runtime_decision",
    # Runtime reasons.
    "RUNTIME_REASON_PASS_TO_FAKE_DISPATCH",
    "RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID",
    "RUNTIME_REASON_DIP_GATE_SKIPPED",
    "RUNTIME_REASON_CANDIDATE_CAP_REACHED",
    "RUNTIME_REASON_DISPATCH_CAP_REACHED",
    "RUNTIME_REASON_RUNTIME_SECONDS_REACHED",
    "RUNTIME_REASON_INVALID_CONFIG_OR_INPUT",
    "STAGE30_11_2_RUNTIME_REASONS",
    "STAGE30_11_2_RUNTIME_DISPATCH_REASON",
    "is_runtime_reason",
    # Not-evaluated sentinel.
    "STAGE30_11_2_NOT_EVALUATED",
    # Config + validator.
    "Stage30_11RuntimeGateConfig",
    "is_valid_runtime_gate_config",
    # Models.
    "Stage30_11RuntimeGateCandidateOutcome",
    "Stage30_11RuntimeGateSummary",
    "Stage30_11FakeDispatchResult",
    # Field-name helpers.
    "runtime_gate_config_field_names",
    "runtime_gate_candidate_outcome_field_names",
    "runtime_gate_summary_field_names",
    "fake_dispatch_result_field_names",
)
