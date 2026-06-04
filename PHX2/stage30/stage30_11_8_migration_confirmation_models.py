"""Stage 30.11.8 narrow migration-confirmation bridge models.

Stage 30.11.8 ships the passive, pure, stdlib-only MODEL layer for the narrowest
remaining blocker the controlled live ceremony retry surfaced: the committed
Stage 30.11.7 enrichment adapter fails a real harvested candidate CLOSED at the
MIGRATION dimension (``UNCONFIRMED_MIGRATION``) because the only committed live
migration source (``Stage29_3NoMigrationEvidenceSource``) returns an UNKNOWN
snapshot for every mint -- so nothing committed maps real migration evidence into
a ``confirmed is True`` resolver result the Stage 30.11.7 ``migration_resolver``
seam can clear on. Stage 30.11.8 adds the narrow CONFIRMATION bridge that answers
exactly one question for one candidate / token mint: do we have real migration
evidence strong enough to set the migration verdict to ``confirmed`` for the Stage
30.11.7 enrichment? It maps INJECTED, offline / fake-first per-mint migration
evidence onto a ``confirmed``-bearing resolution the Stage 30.11.7 adapter reads
duck-typed -- failing closed (never fabricating) on every missing / mismatched /
unsafe / unknown / partial / contradictory / invalid / stale / mis-anchored
evidence.

This module is the MODEL layer ONLY. It implements NO confirmation adapter (that
is ``stage30_11_8_migration_confirmation_adapter``), drives NO evidence source,
runs NO enrichment / bridge / dip gate / runner, calls NO transport / dispatch,
wires into NO runtime, makes NO live provider call, sends NO Discord message,
reads NO process environment, opens NO network connection, opens NO database,
writes NO file, reserves NO dispatch, reads NO wall clock (``created_at_utc`` is
caller-injected), and edits NO Stage 27 / Stage 28 / Stage 29 / Stage 30.3 / Stage
30.4 / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 production file. Stage 30.11.8
is fake / offline only: the real private compact dispatch / Discord send remains a
SEPARATE, explicitly operator-authorized step this slice does not build.

The slice owns one closed-set vocabulary:

  * the per-candidate CONFIRMATION decision / reason -- the confirmation adapter
    emits exactly one of ``CONFIRMED_MIGRATION`` (the evidence is bound to THIS
    mint, redaction-safe, an on-chain ``COMPLETE`` verdict, not stale, with a valid
    ISO-8601 UTC migration anchor; reason ``CONFIRMED_ON_CHAIN_EVENT``), or
    ``UNCONFIRMED_MIGRATION`` for the FIRST failing check (a blank candidate mint ->
    ``BLANK_CANDIDATE_MINT``; no evidence for the mint -> ``MISSING_MIGRATION_EVIDENCE``;
    evidence bound to a DIFFERENT mint -> ``EVIDENCE_MINT_MISMATCH``; a non-SAFE
    redaction -> ``REDACTION_UNSAFE``; an UNKNOWN / unrecognized status ->
    ``UNKNOWN_MIGRATION``; a partial reading -> ``PARTIAL_MIGRATION_UNVERIFIED``; an
    evidence-reports-no-migration reading -> ``EVIDENCE_REPORTS_NO_MIGRATION``; a
    conflicting reading -> ``CONTRADICTORY_MIGRATION_EVIDENCE``; an invalid reading
    -> ``INVALID_MIGRATION_EVIDENCE``; a stale ``COMPLETE`` reading ->
    ``STALE_MIGRATION_EVIDENCE``; a malformed migration anchor ->
    ``INVALID_MIGRATION_ANCHOR``). An ``UNCONFIRMED_MIGRATION`` resolution carries
    ``confirmed=False`` and NO migration anchor / source ref, so it can NEVER make a
    candidate eligible -- the Stage 30.11.7 adapter reads its ``confirmed`` as not
    ``True`` and keeps failing the candidate closed at MIGRATION.

The confirmation FABRICATES nothing: a ``confirmed=True`` resolution is built ONLY
when the bound, redaction-safe, ``COMPLETE``, fresh, valid-anchor evidence clears
EVERY check; an UNKNOWN / missing / mismatched / partial / contradictory / invalid
/ stale / mis-anchored reading fails closed and can NEVER become ``confirmed``. The
measurement-status vocabulary is mirrored BY VALUE from the Stage 29.5 private-ping
measurement-status tokens (exactly as the committed Stage 30.5.3 bridge mirrors
them): this slice recognizes the Stage 29.5 evidence SHAPE without importing any
Stage 29 module, so the no-Stage-21-29-import boundary holds and an unrecognized
token degrades conservatively to ``UNKNOWN_MIGRATION`` rather than overclaiming.

The resolution's ``confirmed`` / ``source_ref`` field NAMES equal the Stage 30.11.7
``migration_resolver`` result fields BY VALUE, so the committed Stage 30.11.7
adapter reads a Stage 30.11.8 resolution via attribute access exactly as it reads
its own injected migration resolution -- no Stage 30.11.7 import is needed (this
slice stays a stdlib-only leaf; the real Stage 29.5 side-channel / Stage 30.5
bridge plugs in at the INJECTED evidence-source seam via out-of-repo,
operator-authorized wrappers, exactly as the Stage 30.11.7 resolvers do).

Discipline:

  * Stdlib only (``dataclasses`` / ``typing`` / ``re``). ``re`` is used ONLY to
    mirror the committed Stage 30.5 ``is_safe_iso8601_utc`` migration-anchor pattern
    BY VALUE (the pattern text is a module-level string literal; it is compiled
    lazily inside the helper, never at import time).
  * Imports NO PHX2 module. The Stage 29.5 measurement-status tokens + the Stage
    30.11.7 migration-resolver field names are mirrored BY VALUE; the slice imports
    NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate record) /
    Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live runner /
    provider / transport / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 module.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + confirmation schema identity
# ---------------------------------------------------------------------------


STAGE30_11_8_MINOR_VERSION: str = "30.11.8"


# The Stage 30.11.8 narrow migration-confirmation bridge schema version. Names the
# evidence / resolution / confirmation-result shapes; distinct from the Stage
# 30.11.7 candidate-enrichment schema version and every earlier Stage 30.11 schema
# version. Mirrored BY VALUE by the Stage 30.11 manifest section; this module
# imports no Stage 30.11 manifest.
STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION: str = (
    "stage30_11_8_v0_migration_confirmation"
)


# The safe-shape source-stage provenance token the confirmation bridge stamps onto
# its results (provenance only; names the slice that produced the confirmation,
# never a secret / host / transport destination).
STAGE30_11_8_SOURCE_STAGE: str = "30.11.8"


# ---------------------------------------------------------------------------
# Stage 29.5 measurement-status vocabulary (mirrored BY VALUE; NOT imported)
# ---------------------------------------------------------------------------
#
# These mirror the Stage 29.5 private-ping measurement-status tokens the committed
# Stage 30.5.3 bridge consults. They are duplicated here as plain Stage-30.11.8-owned
# string literals precisely to preserve the no-Stage-29-import boundary: the
# confirmation recognizes the Stage 29.5 SHAPE without importing any Stage 29
# module. ``COMPLETE`` is the ONLY status that can confirm (an on-chain-confirmed
# migration, exactly as Stage 30.5.3 maps ``COMPLETE`` -> ``Known``); every other
# recognized status, and any unrecognized / missing token, fails closed.


STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: str = (
    "PARTIAL_MIGRATION_PRESENT"
)
STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION: str = "MISSING_MIGRATION"
STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION: str = "INVALID_MIGRATION"
STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION: str = (
    "CONFLICTING_MIGRATION"
)


STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES: Tuple[str, ...] = (
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
)


# The single measurement-status token that can yield a confirmed migration.
STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS: str = (
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE
)


# The single Stage 29.5 warning token the confirmation consults: a ``MIGRATION_STALE``
# warning degrades an otherwise-confirmable ``COMPLETE`` reading to a fail-closed
# stale verdict.
STAGE30_11_8_MIGRATION_WARNING_STALE: str = "MIGRATION_STALE"


# The Stage 29.5 redaction-safe token. The confirmation REQUIRES the evidence to be
# redaction-safe (``redaction_status == SAFE``); a missing / non-SAFE redaction
# fails closed (a confirmation is a stronger claim than the Stage 30.5.1 display
# word, so an unknown-safety reading is never trusted to confirm).
STAGE30_11_8_REDACTION_STATUS_SAFE: str = "SAFE"


def is_recognized_measurement_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a recognized Stage 29.5 measurement-status
    token. Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: per-candidate confirmation decision
# ---------------------------------------------------------------------------
#
# Exactly one confirmation decision per candidate. ``CONFIRMED_MIGRATION`` is the
# only decision that carries a ``confirmed=True`` resolution (with a bound migration
# anchor + provenance); ``UNCONFIRMED_MIGRATION`` carries ``confirmed=False`` and no
# anchor. Mirrored BY VALUE by the Stage 30.11 manifest.


CONFIRM_DECISION_CONFIRMED: str = "CONFIRMED_MIGRATION"
CONFIRM_DECISION_UNCONFIRMED: str = "UNCONFIRMED_MIGRATION"


STAGE30_11_8_CONFIRMATION_DECISIONS: Tuple[str, ...] = (
    CONFIRM_DECISION_CONFIRMED,
    CONFIRM_DECISION_UNCONFIRMED,
)


# The single decision that yields a confirmed (confirmed=True) resolution.
STAGE30_11_8_CONFIRMATION_PASS_DECISION: str = CONFIRM_DECISION_CONFIRMED


def is_confirmation_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set confirmation decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_8_CONFIRMATION_DECISIONS
    )


# ---------------------------------------------------------------------------
# Closed-set: per-candidate confirmation reason
# ---------------------------------------------------------------------------
#
# Exactly one confirmation reason per decision. ``CONFIRMED_ON_CHAIN_EVENT`` is the
# only reason that accompanies a confirmed resolution; every other reason names the
# FIRST failing check's precise fail-closed cause (a contradictory / invalid /
# partial / stale / missing reading is NEVER collapsed into a single silent
# unknown). Mirrored BY VALUE by the manifest.


CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT: str = "CONFIRMED_ON_CHAIN_EVENT"
CONFIRM_REASON_BLANK_CANDIDATE_MINT: str = "BLANK_CANDIDATE_MINT"
CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE: str = "MISSING_MIGRATION_EVIDENCE"
CONFIRM_REASON_EVIDENCE_MINT_MISMATCH: str = "EVIDENCE_MINT_MISMATCH"
CONFIRM_REASON_REDACTION_UNSAFE: str = "REDACTION_UNSAFE"
CONFIRM_REASON_UNKNOWN_MIGRATION: str = "UNKNOWN_MIGRATION"
CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED: str = (
    "PARTIAL_MIGRATION_UNVERIFIED"
)
CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION: str = (
    "EVIDENCE_REPORTS_NO_MIGRATION"
)
CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE: str = (
    "CONTRADICTORY_MIGRATION_EVIDENCE"
)
CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE: str = "INVALID_MIGRATION_EVIDENCE"
CONFIRM_REASON_STALE_MIGRATION_EVIDENCE: str = "STALE_MIGRATION_EVIDENCE"
CONFIRM_REASON_INVALID_MIGRATION_ANCHOR: str = "INVALID_MIGRATION_ANCHOR"


STAGE30_11_8_CONFIRMATION_REASONS: Tuple[str, ...] = (
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
    CONFIRM_REASON_BLANK_CANDIDATE_MINT,
    CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE,
    CONFIRM_REASON_EVIDENCE_MINT_MISMATCH,
    CONFIRM_REASON_REDACTION_UNSAFE,
    CONFIRM_REASON_UNKNOWN_MIGRATION,
    CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED,
    CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION,
    CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE,
    CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE,
    CONFIRM_REASON_STALE_MIGRATION_EVIDENCE,
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
)


# The single reason that accompanies the only confirmed decision.
STAGE30_11_8_CONFIRMATION_PASS_REASON: str = (
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT
)


# The fail-closed reasons (every reason except the single confirmed reason). No
# fail-closed reason ever accompanies a ``confirmed=True`` resolution.
STAGE30_11_8_FAIL_CLOSED_REASONS: Tuple[str, ...] = (
    CONFIRM_REASON_BLANK_CANDIDATE_MINT,
    CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE,
    CONFIRM_REASON_EVIDENCE_MINT_MISMATCH,
    CONFIRM_REASON_REDACTION_UNSAFE,
    CONFIRM_REASON_UNKNOWN_MIGRATION,
    CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED,
    CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION,
    CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE,
    CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE,
    CONFIRM_REASON_STALE_MIGRATION_EVIDENCE,
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
)


def is_confirmation_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set confirmation reason.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str) and value in STAGE30_11_8_CONFIRMATION_REASONS
    )


# ---------------------------------------------------------------------------
# Author-verified offline confirmation proof baseline
# ---------------------------------------------------------------------------
#
# The Stage 30.11.8 fake confirmation proof drives a deterministic ELEVEN-base fake
# source (one bound, redaction-safe, COMPLETE, fresh, valid-anchor evidence + ten
# distinct fail-closed readings) through the confirmation resolver: exactly ONE base
# confirms; the other ten fail closed on ten DISTINCT reasons (a missing evidence,
# a mismatched mint, an unsafe redaction, an unknown status, a partial reading, an
# evidence-reports-no-migration reading, a conflicting reading, an invalid reading,
# a stale reading, a malformed anchor) -- proving the confirmation never collapses a
# contradictory / invalid reading into a silent unknown. Mirrored BY VALUE by the
# manifest. NONE is a secret, a raw payload, a host, or a transport destination.


STAGE30_11_8_EXPECTED_BASES_SEEN: int = 11
STAGE30_11_8_EXPECTED_CONFIRMED: int = 1
STAGE30_11_8_EXPECTED_UNCONFIRMED: int = 10


# The exact safe-shape identity of the single mint whose evidence is allowed to
# confirm. No other mint may confirm. The token mint carries the candidate's real
# on-chain identity (the confirmation echoes the base mint verbatim onto the
# resolution).
STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT: str = "mint-confirmed"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape token. Pure / total; never raises. Mirrors the Stage
    30.11.6 / 30.11.7 non-blank check BY VALUE; the slice consults it to validate
    the candidate mint, the evidence mint, and the carried provenance ref.
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable input model: the sanitized per-mint migration evidence
# ---------------------------------------------------------------------------
#
# The canonical artifact-shaped input the confirmation reads. Every field defaults
# to its FAIL-CLOSED value (``token_mint`` / ``measurement_status`` ``None``;
# ``migration_event_time_utc`` / ``redaction_status`` / ``source_ref`` ``None``;
# ``warnings`` ``()``) -- so a bare evidence object can NEVER confirm. The
# confirmation reads these duck-typed (via attribute access), so a real out-of-repo
# evidence carrier may return any object exposing the same attributes; a missing
# attribute reads as the fail-closed value. The carrier deliberately has NO field
# for a migration signature, raw provider payload, host, or any secret -- so a
# sanitized artifact can never smuggle a raw identifier into the confirmation.


@dataclass(frozen=True)
class Stage30_11_8MigrationEvidence:
    """Immutable sanitized per-mint migration evidence.

    The bound, sanitized migration-evidence summary the confirmation maps onto a
    ``confirmed`` verdict. Carries ONLY the safe summary fields the confirmation
    consults plus the mint it is bound to (so a wrong-mint evidence can never be
    inherited) and the migration anchor it carries (so a confirmed verdict preserves
    the post-migration anchor the later ATH / drawdown step needs).

      * ``token_mint``               -- the mint this evidence is FOR (identity
                                        binding; a blank / mismatched mint fails
                                        closed). Defaults to ``None``.
      * ``measurement_status``       -- Stage 29.5 measurement-status token (or any
                                        value; an unrecognized / ``None`` value fails
                                        closed to ``UNKNOWN_MIGRATION``). Defaults to
                                        ``None``.
      * ``migration_event_time_utc`` -- the migration anchor (an ISO-8601 UTC
                                        timestamp string); a missing / malformed
                                        anchor fails closed to
                                        ``INVALID_MIGRATION_ANCHOR``. Defaults to
                                        ``None``.
      * ``warnings``                 -- tuple of Stage 29.5 warning-code tokens. Only
                                        ``MIGRATION_STALE`` is consulted. Defaults to
                                        ``()``.
      * ``redaction_status``         -- Stage 29.5 redaction token; a missing /
                                        non-``SAFE`` value fails closed to
                                        ``REDACTION_UNSAFE``. Defaults to ``None``.
      * ``source_ref``               -- optional opaque provenance ref carried onto a
                                        confirmed resolution, or ``None``.
    """

    token_mint: Optional[str] = None
    measurement_status: Optional[str] = None
    migration_event_time_utc: Optional[str] = None
    warnings: Tuple[str, ...] = ()
    redaction_status: Optional[str] = None
    source_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable output model: the migration confirmation resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_8MigrationResolution:
    """Immutable per-candidate migration confirmation resolution.

    The confirmation adapter emits exactly one of these per candidate. Its
    ``confirmed`` / ``source_ref`` field NAMES equal the Stage 30.11.7
    ``migration_resolver`` result fields BY VALUE, so the committed Stage 30.11.7
    adapter reads it via attribute access: it requires ``confirmed is True`` to map
    the candidate's ``migration_status`` to the gate's ``PRESENT`` token, so an
    ``UNCONFIRMED_MIGRATION`` resolution (``confirmed=False``) keeps the candidate
    failing closed at the MIGRATION dimension. Carries only safe scalars (an echoed
    mint, closed-set decision / reason tokens, an optional bound migration anchor +
    provenance ref); no secret, no raw payload, no host, no transport destination.

      * ``confirmed``                -- ``True`` ONLY for a fully-checked, bound,
                                        on-chain ``COMPLETE`` migration; ``False``
                                        otherwise (the Stage 30.11.7 gate-clearing
                                        field).
      * ``decision``                 -- one of
                                        ``STAGE30_11_8_CONFIRMATION_DECISIONS``.
      * ``reason``                   -- one of
                                        ``STAGE30_11_8_CONFIRMATION_REASONS`` (the
                                        precise confirmed / fail-closed cause).
      * ``token_mint``               -- the echoed candidate mint (``""`` when the
                                        base mint is blank / unreadable).
      * ``migration_event_time_utc`` -- the bound migration anchor carried onto a
                                        confirmed resolution (for the later ATH /
                                        drawdown step + audit); ``None`` on a
                                        fail-closed resolution.
      * ``source_ref``               -- the carried provenance ref on a confirmed
                                        resolution; ``None`` on a fail-closed
                                        resolution.
    """

    confirmed: bool
    decision: str
    reason: str
    token_mint: str
    migration_event_time_utc: Optional[str]
    source_ref: Optional[str]


# ---------------------------------------------------------------------------
# Immutable model: confirmation proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_8ConfirmationSummary:
    """Immutable Stage 30.11.8 confirmation proof tally.

    A passive summary of one bounded confirmation pass. It proves, by counting, that
    ONLY a bound, redaction-safe, on-chain ``COMPLETE``, fresh, valid-anchor base
    confirmed, and that every other base failed closed. Carries only non-negative
    integer counts + a caller-injected timestamp.

      * ``bases_seen``   -- candidate bases taken from the bounded source.
      * ``confirmed``    -- count that yielded a confirmed migration.
      * ``unconfirmed``  -- count that failed closed.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp.
    """

    bases_seen: int
    confirmed: int
    unconfirmed: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: confirmation run result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_8ConfirmationRunResult:
    """Immutable Stage 30.11.8 bounded confirmation run result.

    The fake confirmation proof emits exactly one of these per bounded pass. It
    carries the ordered per-candidate resolutions and the rolled-up
    ``Stage30_11_8ConfirmationSummary``. Carries only safe scalars + the embedded
    resolutions + a caller-injected timestamp.

      * ``outcomes``       -- the ordered per-candidate confirmation resolutions.
      * ``summary``        -- the embedded ``Stage30_11_8ConfirmationSummary``.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp; NEVER a
                              wall-clock read.
    """

    outcomes: Tuple[Stage30_11_8MigrationResolution, ...]
    summary: Stage30_11_8ConfirmationSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def migration_evidence_field_names() -> Tuple[str, ...]:
    """Return the migration evidence field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_8MigrationEvidence))


def migration_resolution_field_names() -> Tuple[str, ...]:
    """Return the migration resolution field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_8MigrationResolution))


def confirmation_summary_field_names() -> Tuple[str, ...]:
    """Return the confirmation summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_8ConfirmationSummary))


def confirmation_run_result_field_names() -> Tuple[str, ...]:
    """Return the confirmation run result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_8ConfirmationRunResult))


__all__ = (
    # Minor version + confirmation schema identity.
    "STAGE30_11_8_MINOR_VERSION",
    "STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION",
    "STAGE30_11_8_SOURCE_STAGE",
    # Measurement-status vocabulary (mirrored BY VALUE).
    "STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE",
    "STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT",
    "STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION",
    "STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION",
    "STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION",
    "STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES",
    "STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS",
    "STAGE30_11_8_MIGRATION_WARNING_STALE",
    "STAGE30_11_8_REDACTION_STATUS_SAFE",
    "is_recognized_measurement_status",
    # Confirmation decisions.
    "CONFIRM_DECISION_CONFIRMED",
    "CONFIRM_DECISION_UNCONFIRMED",
    "STAGE30_11_8_CONFIRMATION_DECISIONS",
    "STAGE30_11_8_CONFIRMATION_PASS_DECISION",
    "is_confirmation_decision",
    # Confirmation reasons.
    "CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT",
    "CONFIRM_REASON_BLANK_CANDIDATE_MINT",
    "CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE",
    "CONFIRM_REASON_EVIDENCE_MINT_MISMATCH",
    "CONFIRM_REASON_REDACTION_UNSAFE",
    "CONFIRM_REASON_UNKNOWN_MIGRATION",
    "CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED",
    "CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION",
    "CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE",
    "CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE",
    "CONFIRM_REASON_STALE_MIGRATION_EVIDENCE",
    "CONFIRM_REASON_INVALID_MIGRATION_ANCHOR",
    "STAGE30_11_8_CONFIRMATION_REASONS",
    "STAGE30_11_8_CONFIRMATION_PASS_REASON",
    "STAGE30_11_8_FAIL_CLOSED_REASONS",
    "is_confirmation_reason",
    # Confirmation proof baseline.
    "STAGE30_11_8_EXPECTED_BASES_SEEN",
    "STAGE30_11_8_EXPECTED_CONFIRMED",
    "STAGE30_11_8_EXPECTED_UNCONFIRMED",
    "STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11_8MigrationEvidence",
    "Stage30_11_8MigrationResolution",
    "Stage30_11_8ConfirmationSummary",
    "Stage30_11_8ConfirmationRunResult",
    # Field-name helpers.
    "migration_evidence_field_names",
    "migration_resolution_field_names",
    "confirmation_summary_field_names",
    "confirmation_run_result_field_names",
)
