"""Stage 30.11.6 real candidate source / harvest-seam models.

Stage 30.11.6 ships the passive, pure, stdlib-only MODEL layer for the real
candidate source / harvest seam -- the narrowest remaining blocker before the
controlled live ceremony can actually run. The prior Stage 30.11.5 bounded live
runner needs a ``candidate_source`` of already-assembled flat projections, but
the ONLY committed live assembly path (the Stage 28.9 / Stage 29.3 live provider
session) FUSES candidate assembly with its OWN older ungated dispatch and returns
only counters -- never the assembled candidate record. Stage 30.11.6 adds the
seam that HARVESTS an assembled candidate (by driving the existing committed
assembler boundary -- the ``Stage28_9CandidateAssembler.assemble`` protocol --
WITHOUT ever invoking the old ungated dispatch path) and PROJECTS it into the
Stage 30.11.5 flat projection shape the bounded runner consumes.

This module is the MODEL layer ONLY. It implements NO harvest adapter / projection
adapter (those are the sibling logic modules), drives NO assembler, captures NO
record, runs NO bridge / dip gate / seam / runner, calls NO transport / dispatch,
wires into NO runtime, makes NO live provider call, sends NO Discord message,
reads NO process environment, opens NO network connection, opens NO database,
writes NO file, reserves NO real dispatch, reads NO wall clock (``created_at_utc``
is caller-injected), and edits NO Stage 27 / Stage 28 / Stage 29 / Stage 30.3 /
Stage 30.4 production file. Stage 30.11.6 is fake / offline only: the real
private compact dispatch / Discord send remains a SEPARATE, explicitly
operator-authorized step this slice does not build.

The slice owns two closed-set vocabularies:

  * the per-event HARVEST decision / reason -- the harvest adapter emits exactly
    one of ``HARVESTED_LIVE_CANDIDATE`` (the injected assembler returned a record
    AND it projected into a valid Stage 30.11.5 flat projection; reason
    ``HARVESTED_READY_FOR_LIVE_RUNNER``), ``SKIPPED_ASSEMBLY_FAILED`` (the
    injected assembler raised / returned no record; reason
    ``ASSEMBLY_RAISED_OR_EMPTY`` -- a failed assembly NEVER yields a candidate),
    or ``SKIPPED_PROJECTION_REJECTED`` (a record was captured but the flattened
    fields failed the fail-closed projection -- a missing required field / a
    malformed Decimal; reason ``PROJECTION_FAILED_CLOSED`` -- a malformed
    candidate NEVER reaches the Stage 30.11.5 transport). A skipped event NEVER
    yields a ``candidate_source`` projection.
  * the per-record PROJECTION decision / reason -- the projection adapter emits
    exactly one of ``PROJECTED_LIVE_CANDIDATE`` (reason ``READY_FOR_LIVE_RUNNER``
    -- a clean Stage 30.11.5 flat projection was built; it is the INPUT the
    committed Stage 30.11.5 assembler + bridge + dip gate later consume, NOT a
    bypass of them), ``REJECTED_MISSING_REQUIRED_FIELD`` (reason
    ``MISSING_REQUIRED_CANDIDATE_FIELD``), or ``REJECTED_INVALID_FIELD_SHAPE``
    (reason ``INVALID_CANDIDATE_FIELD_SHAPE``). The projection FABRICATES nothing
    (a missing ATH / drawdown / migration / market-context field fails closed; a
    present-but-degraded context token is carried VERBATIM so the committed bridge
    later suppresses it) and PRESERVES candidate identity.

It also pins the hard harvest cap the harvest adapter enforces
(``max_harvest <= 10``, mirroring the Stage 30.11.5 ``max_candidates <= 10``
ceiling) plus the author-verified offline harvest proof baseline.

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Imports NO PHX2 module. The Stage 30.11.5 flat projection field names are
    mirrored BY VALUE (a pin test cross-checks they equal the committed Stage
    30.11.5 projection field names); the slice imports NO Stage 21-29 (incl. the
    nested Stage 27 / 28 / 29 live candidate record) / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport
    module.
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
from decimal import Decimal
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + candidate-source schema identity
# ---------------------------------------------------------------------------


STAGE30_11_6_MINOR_VERSION: str = "30.11.6"


# The Stage 30.11.6 real candidate source / harvest seam schema version. Names
# the projection / harvest-outcome / harvest-result shapes; distinct from the
# Stage 30.11.5 live wiring schema version and every earlier Stage 30.11 schema
# version. Mirrored BY VALUE by the Stage 30.11 manifest section; this module
# imports no Stage 30.11 manifest.
STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION: str = (
    "stage30_11_6_v0_candidate_source"
)


# The safe-shape source-stage provenance token the harvest seam stamps onto its
# results (provenance only; names the slice that produced the projection, never a
# secret / host / transport destination).
STAGE30_11_6_SOURCE_STAGE: str = "30.11.6"


# ---------------------------------------------------------------------------
# Stage 30.11.5 flat projection field names (mirrored BY VALUE)
# ---------------------------------------------------------------------------
#
# The harvest seam projects a harvested candidate into the EXACT Stage 30.11.5
# flat safe-scalar projection shape the committed Stage 30.11.5 bounded runner /
# assembler consumes. These names equal the committed
# ``STAGE30_11_5_*_PROJECTION_FIELDS`` BY VALUE (a pin test cross-checks the
# equality against the committed Stage 30.11.5 models). This module mirrors them
# rather than importing the Stage 30.11.5 models so it stays a stdlib-only leaf.
# NONE is a secret, a raw payload, a host, or a transport destination.


# Each REQUIRED projection field must be present + well-shaped, else the
# projection fails closed. ``drawdown_from_ath`` / ``current_market_cap_usd`` must
# be a finite-coercible ``Decimal`` magnitude; the rest must be a non-blank
# string.
STAGE30_11_6_REQUIRED_PROJECTION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "created_at_utc",
)


# The optional projection fields: ``None`` / absent is allowed; a present value
# must be well-shaped (``post_migration_ath_verified`` a ``bool``; ``source_ref``
# a string).
STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS: Tuple[str, ...] = (
    "post_migration_ath_verified",
    "source_ref",
)


# Every projection field name (required + optional), in Stage 30.11.5 snapshot
# order.
STAGE30_11_6_PROJECTION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "post_migration_ath_verified",
    "source_ref",
    "created_at_utc",
)


# ---------------------------------------------------------------------------
# Closed-set: per-record projection decision
# ---------------------------------------------------------------------------
#
# Exactly one projection decision per harvested record's flattened fields.
# ``PROJECTED_LIVE_CANDIDATE`` is the only decision that carries a built
# ``Stage30_11_6CandidateProjection``; the two reject decisions carry ``None``.
# Mirrored BY VALUE by the Stage 30.11 manifest.


PROJECTION_DECISION_PROJECTED: str = "PROJECTED_LIVE_CANDIDATE"
PROJECTION_DECISION_REJECTED_MISSING_FIELD: str = (
    "REJECTED_MISSING_REQUIRED_FIELD"
)
PROJECTION_DECISION_REJECTED_INVALID_SHAPE: str = "REJECTED_INVALID_FIELD_SHAPE"


STAGE30_11_6_PROJECTION_DECISIONS: Tuple[str, ...] = (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_MISSING_FIELD,
    PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
)


# The single decision that yields a built Stage 30.11.6 flat projection.
STAGE30_11_6_PROJECTION_PASS_DECISION: str = PROJECTION_DECISION_PROJECTED


def is_projection_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set projection decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_6_PROJECTION_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: per-record projection reason
# ---------------------------------------------------------------------------
#
# Exactly one projection reason per decision. ``READY_FOR_LIVE_RUNNER`` is the
# only reason that accompanies a built projection; it names the projection as the
# INPUT the committed Stage 30.11.5 runner / assembler later consume, NEVER a
# bypass of the committed bridge / dip gate. Mirrored BY VALUE by the manifest.


PROJECTION_REASON_READY_FOR_LIVE_RUNNER: str = "READY_FOR_LIVE_RUNNER"
PROJECTION_REASON_MISSING_REQUIRED_FIELD: str = (
    "MISSING_REQUIRED_CANDIDATE_FIELD"
)
PROJECTION_REASON_INVALID_FIELD_SHAPE: str = "INVALID_CANDIDATE_FIELD_SHAPE"


STAGE30_11_6_PROJECTION_REASONS: Tuple[str, ...] = (
    PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
    PROJECTION_REASON_MISSING_REQUIRED_FIELD,
    PROJECTION_REASON_INVALID_FIELD_SHAPE,
)


# The single reason that accompanies the only projected decision.
STAGE30_11_6_PROJECTION_PASS_REASON: str = (
    PROJECTION_REASON_READY_FOR_LIVE_RUNNER
)


def is_projection_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set projection reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_6_PROJECTION_REASONS


# ---------------------------------------------------------------------------
# Closed-set: per-event harvest decision
# ---------------------------------------------------------------------------
#
# Exactly one harvest decision per source event. ``HARVESTED_LIVE_CANDIDATE`` is
# the only decision that yields a ``candidate_source`` projection; the two
# skip decisions yield nothing. Mirrored BY VALUE by the Stage 30.11 manifest.


HARVEST_DECISION_HARVESTED: str = "HARVESTED_LIVE_CANDIDATE"
HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED: str = "SKIPPED_ASSEMBLY_FAILED"
HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED: str = (
    "SKIPPED_PROJECTION_REJECTED"
)


STAGE30_11_6_HARVEST_DECISIONS: Tuple[str, ...] = (
    HARVEST_DECISION_HARVESTED,
    HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
    HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
)


# The single decision that yields a harvested ``candidate_source`` projection.
STAGE30_11_6_HARVEST_PASS_DECISION: str = HARVEST_DECISION_HARVESTED


def is_harvest_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set harvest decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_6_HARVEST_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: per-event harvest reason
# ---------------------------------------------------------------------------


HARVEST_REASON_READY_FOR_LIVE_RUNNER: str = "HARVESTED_READY_FOR_LIVE_RUNNER"
HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY: str = "ASSEMBLY_RAISED_OR_EMPTY"
HARVEST_REASON_PROJECTION_FAILED_CLOSED: str = "PROJECTION_FAILED_CLOSED"


STAGE30_11_6_HARVEST_REASONS: Tuple[str, ...] = (
    HARVEST_REASON_READY_FOR_LIVE_RUNNER,
    HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY,
    HARVEST_REASON_PROJECTION_FAILED_CLOSED,
)


# The single reason that accompanies the only harvested decision.
STAGE30_11_6_HARVEST_PASS_REASON: str = HARVEST_REASON_READY_FOR_LIVE_RUNNER


def is_harvest_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set harvest reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_6_HARVEST_REASONS


# ---------------------------------------------------------------------------
# Hard harvest cap + default + run-scoped candidate-id prefix
# ---------------------------------------------------------------------------
#
# The harvest adapter pulls AT MOST ``max_harvest`` events (a single bounded
# for-loop; no ``while`` loop, no daemon). The hard cap mirrors the Stage 30.11.5
# ``max_candidates <= 10`` ceiling so the harvested ``candidate_source`` can never
# exceed what the bounded runner is allowed to evaluate. A ``max_harvest`` above
# the cap fails closed BEFORE harvesting anything.


STAGE30_11_6_MAX_HARVEST_HARD_CAP: int = 10
STAGE30_11_6_DEFAULT_MAX_HARVEST: int = 10


# The default run-scoped candidate-id prefix the harvest adapter stamps onto each
# event's ``candidate_id`` (the assembler-input id), mirroring the committed Stage
# 28.9 live-session run-scoped id scheme (``stage28_9_<session>_<index:06d>``):
# the harvest adapter supplies ``f"{prefix}{index:06d}"`` to the injected
# assembler exactly as the committed path does, so the harvested candidate's
# identity is a deterministic run-scoped id (the token mint carries the real
# on-chain identity). Safe-shape only; no secret, no host, no transport
# destination.
STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX: str = "stage30_11_6_cand_"


# ---------------------------------------------------------------------------
# Author-verified offline harvest proof baseline
# ---------------------------------------------------------------------------
#
# The Stage 30.11.6 fake candidate source proof drives a deterministic
# FIVE-event fake source through the harvest adapter (an injected fake assembler +
# fake record flattener), then feeds the harvested ``candidate_source`` through
# the committed Stage 30.11.5 bounded runner via the committed Stage 30.11.5 fake
# wiring proof. The harvest baseline: five events seen, exactly three harvested
# (one non-dip + one bridge-suppressed + one Tier 1 dip), exactly one skipped for
# a failed assembly (the injected assembler raised), exactly one skipped for a
# rejected projection (a required field absent). The runner baseline over the
# three harvested projections: three candidates seen, two bridged, one dip-gate
# PASS, exactly one dispatch attempt + accept, exactly one fake transport attempt
# + accept -- for the Tier 1 dip ONLY. The failed-assembly / rejected-projection /
# non-dip / bridge-suppressed candidates never reach the transport; the old
# ungated dispatch path is never invoked. Mirrored BY VALUE by the manifest. NONE
# is a secret, a raw payload, a host, or a transport destination.


STAGE30_11_6_EXPECTED_EVENTS_SEEN: int = 5
STAGE30_11_6_EXPECTED_HARVESTED: int = 3
STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED: int = 1
STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED: int = 1
STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN: int = 3
STAGE30_11_6_EXPECTED_RUNNER_BRIDGED: int = 2
STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED: int = 1
STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED: int = 1
STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED: int = 1
STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS: int = 1


# The exact safe-shape identity of the single dip the fake transport is allowed
# to see. No other candidate id / token mint may reach the transport. The
# candidate id is the deterministic run-scoped id the harvest adapter stamps for
# the dip event (the third event, index 2): the default prefix
# (``stage30_11_6_cand_``) + ``f"{2:06d}"``; the token mint carries the dip's real
# on-chain identity (``mint-tier1``).
STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID: str = "stage30_11_6_cand_000002"
STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT: str = "mint-tier1"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape token. Pure / total; never raises. Mirrors the Stage
    30.11.1 / 30.11.3 / 30.11.4 / 30.11.5 non-blank check BY VALUE; the slice
    consults it to validate ids / status tokens / timestamps.
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable model: the Stage 30.11.5-shaped flat candidate projection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_6CandidateProjection:
    """Immutable Stage 30.11.5-shaped flat candidate projection.

    The harvested + projected candidate the Stage 30.11.6 projection adapter
    builds and the harvest adapter accumulates into a ``candidate_source`` the
    committed Stage 30.11.5 bounded runner consumes. Its field NAMES + order equal
    the committed Stage 30.11.5 projection field names BY VALUE, so the committed
    Stage 30.11.5 assembler reads it via attribute access exactly as it reads a
    flat projection dict. Carries ONLY safe scalars (opaque ids, display tokens,
    finite ``Decimal`` magnitudes, a caller-injected timestamp); no secret, no raw
    provider payload, no host, no transport destination, no env value, and NO
    reference to the deeply-nested committed live candidate RECORD it was
    harvested from (the record is captured transiently and never retained).

      * ``candidate_id`` / ``token_mint``  -- echoed safe-shape ids (identity is
                                              preserved from the harvested record).
      * ``pair_type`` / ``tier_hint``      -- display tokens (carried verbatim; the
                                              committed dip gate decides
                                              eligibility, NOT this projection).
      * ``drawdown_from_ath`` /
        ``current_market_cap_usd``         -- finite ``Decimal`` magnitudes.
      * ``migration_status`` / ``ath_status`` /
        ``market_context_status``          -- context status tokens (carried
                                              VERBATIM; a degraded context is NEVER
                                              forced to the bridge's ``PRESENT``
                                              value, so the committed bridge later
                                              suppresses it).
      * ``post_migration_ath_verified``    -- optional ``bool`` or ``None``.
      * ``source_ref``                     -- optional opaque ref or ``None``.
      * ``created_at_utc``                 -- caller-injected ISO-8601 UTC
                                              timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    pair_type: str
    tier_hint: str
    drawdown_from_ath: Decimal
    migration_status: str
    ath_status: str
    market_context_status: str
    current_market_cap_usd: Decimal
    post_migration_ath_verified: Optional[bool]
    source_ref: Optional[str]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-record projection result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_6CandidateProjectionResult:
    """Immutable per-record Stage 30.11.6 projection result.

    The projection adapter emits exactly one of these per harvested record's
    flattened fields. It echoes the safe-shape candidate identity, pins the
    closed-set ``projection_decision`` / ``projection_reason``, names the first
    offending projection field on a reject (a safe FIELD NAME only, never a field
    VALUE; ``""`` when projected), and carries the built
    ``Stage30_11_6CandidateProjection`` (ONLY for a ``PROJECTED_LIVE_CANDIDATE``
    decision; ``None`` otherwise). Carries only safe scalars + the embedded
    projection + a caller-injected timestamp.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids (``""`` when
                                             unreadable).
      * ``projection_decision``           -- one of
                                             ``STAGE30_11_6_PROJECTION_DECISIONS``.
      * ``projection_reason``             -- one of
                                             ``STAGE30_11_6_PROJECTION_REASONS``.
      * ``rejected_field``                -- the safe field NAME that failed closed
                                             (one of
                                             ``STAGE30_11_6_PROJECTION_FIELDS``),
                                             or ``""`` when projected.
      * ``projection``                    -- the built
                                             ``Stage30_11_6CandidateProjection``
                                             (only for a PROJECTED decision;
                                             ``None`` for a reject).
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    projection_decision: str
    projection_reason: str
    rejected_field: str
    projection: Optional[Stage30_11_6CandidateProjection]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-event harvest outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_6CandidateHarvestOutcome:
    """Immutable per-event Stage 30.11.6 harvest outcome.

    The harvest adapter emits exactly one of these per source event. It echoes the
    safe-shape candidate identity, pins the closed-set ``harvest_decision`` /
    ``harvest_reason`` plus the embedded ``projection_decision`` /
    ``projection_reason`` / ``rejected_field`` (the projection verdict for a
    captured record; the projection tokens are the ``NOT_PROJECTED`` sentinel /
    ``""`` when the assembler raised so no record was captured). Carries ONLY safe
    scalars + a caller-injected timestamp; never the captured deep record, no
    secret, no raw payload, no host, no transport destination.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids (``""`` when
                                             unreadable / no record captured).
      * ``harvest_decision``              -- one of
                                             ``STAGE30_11_6_HARVEST_DECISIONS``.
      * ``harvest_reason``                -- one of
                                             ``STAGE30_11_6_HARVEST_REASONS``.
      * ``projection_decision``           -- the projection verdict for a captured
                                             record (one of
                                             ``STAGE30_11_6_PROJECTION_DECISIONS``),
                                             or ``NOT_PROJECTED`` when the
                                             assembler raised.
      * ``projection_reason``             -- the projection reason, or
                                             ``NOT_PROJECTED`` when the assembler
                                             raised.
      * ``rejected_field``                -- the safe field NAME the projection
                                             failed closed on, or ``""``.
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    harvest_decision: str
    harvest_reason: str
    projection_decision: str
    projection_reason: str
    rejected_field: str
    created_at_utc: str


# The projection sentinel stamped on a harvest outcome whose assembler RAISED (so
# no record was captured and the projection adapter was never reached). It is NOT
# a member of ``STAGE30_11_6_PROJECTION_DECISIONS`` / ``..._REASONS`` -- it names
# the absence of a projection attempt.
STAGE30_11_6_NOT_PROJECTED: str = "NOT_PROJECTED"


# ---------------------------------------------------------------------------
# Immutable model: harvest proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_6HarvestSummary:
    """Immutable Stage 30.11.6 harvest proof tally.

    A passive summary of one bounded harvest pass. It proves, by counting, that
    ONLY an event whose assembler returned a record AND whose flattened fields
    projected cleanly became a ``candidate_source`` projection, that every
    failed-assembly / rejected-projection event was suppressed cleanly (no
    projection), and that the hard harvest cap held. Carries only non-negative
    integer counts + a caller-injected timestamp.

      * ``events_seen``                 -- source events taken from the bounded
                                           source (<= ``max_harvest``).
      * ``harvested``                   -- count that yielded a
                                           ``candidate_source`` projection.
      * ``skipped_assembly_failed``     -- count the injected assembler raised /
                                           returned no record.
      * ``skipped_projection_rejected`` -- count a record was captured but the
                                           projection failed closed.
      * ``created_at_utc``              -- caller-injected ISO-8601 UTC timestamp.
    """

    events_seen: int
    harvested: int
    skipped_assembly_failed: int
    skipped_projection_rejected: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: harvest result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_6HarvestResult:
    """Immutable Stage 30.11.6 harvest result.

    The harvest adapter emits exactly one of these per bounded harvest pass. It
    carries the ordered per-event harvest outcomes, the harvested
    ``candidate_source`` (a tuple of ``Stage30_11_6CandidateProjection`` the
    committed Stage 30.11.5 bounded runner consumes directly), and the rolled-up
    ``Stage30_11_6HarvestSummary``. Carries only safe scalars + the embedded
    results + a caller-injected timestamp; never a captured deep record, no
    secret, no raw payload, no host, no transport destination.

      * ``outcomes``         -- the ordered per-event harvest outcomes.
      * ``candidate_source`` -- the harvested ``Stage30_11_6CandidateProjection``
                                tuple, ready for the committed Stage 30.11.5
                                bounded runner ``candidate_source``.
      * ``summary``          -- the embedded ``Stage30_11_6HarvestSummary``.
      * ``created_at_utc``   -- caller-injected ISO-8601 UTC timestamp; NEVER a
                                wall-clock read.
    """

    outcomes: Tuple[Stage30_11_6CandidateHarvestOutcome, ...]
    candidate_source: Tuple[Stage30_11_6CandidateProjection, ...]
    summary: Stage30_11_6HarvestSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def candidate_projection_field_names() -> Tuple[str, ...]:
    """Return the candidate projection field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_6CandidateProjection))


def candidate_projection_result_field_names() -> Tuple[str, ...]:
    """Return the candidate projection result field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_6CandidateProjectionResult)
    )


def candidate_harvest_outcome_field_names() -> Tuple[str, ...]:
    """Return the candidate harvest outcome field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_6CandidateHarvestOutcome))


def harvest_summary_field_names() -> Tuple[str, ...]:
    """Return the harvest summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_6HarvestSummary))


def harvest_result_field_names() -> Tuple[str, ...]:
    """Return the harvest result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_6HarvestResult))


__all__ = (
    # Minor version + candidate-source schema identity.
    "STAGE30_11_6_MINOR_VERSION",
    "STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION",
    "STAGE30_11_6_SOURCE_STAGE",
    # Projection field names.
    "STAGE30_11_6_REQUIRED_PROJECTION_FIELDS",
    "STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS",
    "STAGE30_11_6_PROJECTION_FIELDS",
    # Projection decisions.
    "PROJECTION_DECISION_PROJECTED",
    "PROJECTION_DECISION_REJECTED_MISSING_FIELD",
    "PROJECTION_DECISION_REJECTED_INVALID_SHAPE",
    "STAGE30_11_6_PROJECTION_DECISIONS",
    "STAGE30_11_6_PROJECTION_PASS_DECISION",
    "is_projection_decision",
    # Projection reasons.
    "PROJECTION_REASON_READY_FOR_LIVE_RUNNER",
    "PROJECTION_REASON_MISSING_REQUIRED_FIELD",
    "PROJECTION_REASON_INVALID_FIELD_SHAPE",
    "STAGE30_11_6_PROJECTION_REASONS",
    "STAGE30_11_6_PROJECTION_PASS_REASON",
    "is_projection_reason",
    # Harvest decisions.
    "HARVEST_DECISION_HARVESTED",
    "HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED",
    "HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED",
    "STAGE30_11_6_HARVEST_DECISIONS",
    "STAGE30_11_6_HARVEST_PASS_DECISION",
    "is_harvest_decision",
    # Harvest reasons.
    "HARVEST_REASON_READY_FOR_LIVE_RUNNER",
    "HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY",
    "HARVEST_REASON_PROJECTION_FAILED_CLOSED",
    "STAGE30_11_6_HARVEST_REASONS",
    "STAGE30_11_6_HARVEST_PASS_REASON",
    "is_harvest_reason",
    # Not-projected sentinel.
    "STAGE30_11_6_NOT_PROJECTED",
    # Hard cap + default + candidate-id prefix.
    "STAGE30_11_6_MAX_HARVEST_HARD_CAP",
    "STAGE30_11_6_DEFAULT_MAX_HARVEST",
    "STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX",
    # Harvest proof baseline.
    "STAGE30_11_6_EXPECTED_EVENTS_SEEN",
    "STAGE30_11_6_EXPECTED_HARVESTED",
    "STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED",
    "STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED",
    "STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN",
    "STAGE30_11_6_EXPECTED_RUNNER_BRIDGED",
    "STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED",
    "STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED",
    "STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED",
    "STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11_6CandidateProjection",
    "Stage30_11_6CandidateProjectionResult",
    "Stage30_11_6CandidateHarvestOutcome",
    "Stage30_11_6HarvestSummary",
    "Stage30_11_6HarvestResult",
    # Field-name helpers.
    "candidate_projection_field_names",
    "candidate_projection_result_field_names",
    "candidate_harvest_outcome_field_names",
    "harvest_summary_field_names",
    "harvest_result_field_names",
)
