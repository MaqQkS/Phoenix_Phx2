"""Stage 30.11.9 mint-keyed migration evidence-source models.

Stage 30.11.9 ships the passive, pure, stdlib-only MODEL layer for the narrowest
remaining blocker the Stage 30.11.8 controlled live ceremony surfaced: the committed
Stage 30.11.8 confirmation adapter consumes an INJECTED per-mint evidence source
(``lookup_migration_evidence(token_mint) -> evidence | None``), but NOTHING committed
implements that source over real, recorded migration evidence -- so the only thing
the ceremony could inject was a no-evidence source, and every harvested candidate
died at ``MISSING_MIGRATION_EVIDENCE``. Stage 30.11.9 adds the narrow, mint-keyed
evidence-source ADAPTER (in the sibling adapter module) the Stage 30.11.8 seam was
missing; this module is its MODEL layer.

This module owns ONE thing: the canonical sanitized per-mint evidence RECORD the
adapter routes by mint and hands -- verbatim, unmodified -- to the Stage 30.11.8
confirmation seam. The record's field NAMES equal the Stage 30.11.8 migration
evidence field names BY VALUE (``token_mint`` / ``measurement_status`` /
``migration_event_time_utc`` / ``warnings`` / ``redaction_status`` / ``source_ref``)
so the committed Stage 30.11.8 adapter reads a Stage 30.11.9 record via attribute
access EXACTLY as it reads its own injected fake evidence -- no Stage 30.11.8 import
is needed (and is in fact forbidden: importing the Stage 30.11.8 slice would break
the committed Stage 30.11.8 leaf boundary test, so Stage 30.11.9 stays a clean leaf
and mirrors the shape BY VALUE, exactly as the Stage 30.11.8 slice mirrors the Stage
29.5 measurement-status tokens BY VALUE). Every field defaults to its FAIL-CLOSED
value, so a bare record can NEVER confirm.

The record is the operator's adaptation TARGET: at the SEPARATE, explicitly
operator-authorized live ceremony, an out-of-repo operator wrapper reads the
committed Stage 29.5 migration-evidence reader / offline-integration projection and
maps each per-mint reading onto one of these records (the sibling adapter ships a
pure, rename-only, fail-closed mapper helper for exactly that). Stage 30.11.9
FABRICATES nothing: it carries the measurement status, the redaction status, the
warnings, and the migration anchor VERBATIM (it never normalizes a non-trailing-Z
anchor into a passing one, never invents a redaction-safe claim, never promotes an
UNKNOWN reading), so the Stage 30.11.8 confirmation -- not Stage 30.11.9 -- decides
whether a migration is confirmed.

This module is the MODEL layer ONLY. It implements NO source adapter (that is
``stage30_11_9_migration_evidence_source_adapter``), drives NO reader, runs NO
confirmation / enrichment / projection / runner / dip gate, calls NO transport /
dispatch, wires into NO runtime, makes NO live provider call, sends NO private
message, reads NO process environment, opens NO network connection, opens NO
database, writes NO file, reserves NO dispatch, reads NO wall clock
(``created_at_utc`` is caller-injected), and edits NO Stage 27 / Stage 28 / Stage 29
/ Stage 30.3 / Stage 30.4 / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 / Stage
30.11.8 production file. Stage 30.11.9 is fake / offline only: the real recorded
evidence binds at the injected reader seam via an out-of-repo, operator-authorized
wrapper this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``). NO ``re`` (Stage 30.11.9 never
    inspects the anchor SHAPE -- the Stage 30.11.8 confirmation owns that check; a
    Stage 30.11.9 anchor cleanup would let a bad timestamp pass, which is forbidden).
  * Imports NO PHX2 module. The Stage 30.11.8 evidence field names are mirrored BY
    VALUE; the slice imports NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live
    candidate record) / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression /
    live runner / provider / transport / Stage 30.11.5 / Stage 30.11.6 / Stage
    30.11.7 / Stage 30.11.8 module.
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
# Minor version + evidence-source schema identity
# ---------------------------------------------------------------------------


STAGE30_11_9_MINOR_VERSION: str = "30.11.9"


# The Stage 30.11.9 mint-keyed migration evidence-source schema version. Names the
# sanitized per-mint evidence record + source summary / run-result shapes; distinct
# from the Stage 30.11.8 confirmation schema version and every earlier Stage 30.11
# schema version. Mirrored BY VALUE by the Stage 30.11 manifest section; this module
# imports no Stage 30.11 manifest.
STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION: str = (
    "stage30_11_9_v0_migration_evidence_source"
)


# The safe-shape source-stage provenance token the evidence source stamps onto its
# proof tally (provenance only; names the slice that produced the routing, never a
# secret / host / transport destination).
STAGE30_11_9_SOURCE_STAGE: str = "30.11.9"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape token. Pure / total; never raises. Mirrors the Stage
    30.11.6 / 30.11.7 / 30.11.8 non-blank check BY VALUE; the adapter consults it
    to validate the requested mint and each record's own bound mint (so no record
    is ever bound to a blank mint and no candidate inherits another mint's
    evidence).
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable record: the sanitized per-mint migration evidence the source routes
# ---------------------------------------------------------------------------
#
# The canonical sanitized evidence record the Stage 30.11.9 adapter selects by mint
# and hands VERBATIM to the Stage 30.11.8 confirmation seam. Its field NAMES equal
# the Stage 30.11.8 migration evidence field names BY VALUE, so the committed Stage
# 30.11.8 adapter reads it duck-typed (via attribute access). Every field defaults to
# its FAIL-CLOSED value (``token_mint`` / ``measurement_status`` /
# ``migration_event_time_utc`` / ``redaction_status`` / ``source_ref`` ``None``;
# ``warnings`` ``None`` -- the FAIL-CLOSED sentinel for a MISSING / omitted warnings
# field) -- so a bare record can NEVER route or confirm: the Stage 30.11.9 router
# refuses a missing / ``None`` warnings (an absent field is malformed evidence, NOT
# "no warnings"); a source that means "no warnings" MUST set an explicit ``()`` /
# ``[]``. The carrier deliberately has NO field for a migration signature, raw
# provider payload, host, or any secret -- so a sanitized record can never smuggle a
# raw identifier into the confirmation.


@dataclass(frozen=True)
class Stage30_11_9MigrationEvidenceRecord:
    """Immutable sanitized per-mint migration evidence record.

    The bound, sanitized migration-evidence summary the Stage 30.11.9 source routes
    by mint and hands -- unmodified -- to the Stage 30.11.8 confirmation. Carries
    ONLY the safe summary fields the confirmation consults plus the mint it is bound
    to (so a wrong-mint record is never inherited) and the migration anchor it carries
    (so a confirmed verdict preserves the post-migration anchor the later ATH /
    drawdown step needs). The Stage 30.11.9 adapter reads ONLY ``token_mint`` (to key
    / bind the record); every other field rides through VERBATIM for the Stage
    30.11.8 confirmation -- not Stage 30.11.9 -- to judge.

      * ``token_mint``               -- the mint this record is FOR (identity binding;
                                        a blank / mismatched mint fails closed at the
                                        adapter / confirmation). Defaults to ``None``.
      * ``measurement_status``       -- Stage 29.5 measurement-status token, carried
                                        VERBATIM (the Stage 30.11.8 confirmation
                                        requires ``COMPLETE``; Stage 30.11.9 never
                                        promotes / invents it). Defaults to ``None``.
      * ``migration_event_time_utc`` -- the migration anchor (an ISO-8601 UTC
                                        timestamp string), carried VERBATIM (the Stage
                                        30.11.8 confirmation requires a trailing-Z
                                        anchor; Stage 30.11.9 never normalizes a
                                        non-Z / malformed anchor into a passing one).
                                        Defaults to ``None``.
      * ``warnings``                 -- tuple of Stage 29.5 warning-code tokens,
                                        carried VERBATIM (only ``MIGRATION_STALE`` is
                                        consulted, by the Stage 30.11.8 confirmation).
                                        Defaults to ``None`` -- the FAIL-CLOSED
                                        sentinel: a MISSING / omitted / ``None``
                                        warnings is malformed evidence the Stage
                                        30.11.9 router refuses to route (it is NOT
                                        silently treated as "no warnings"); a source
                                        meaning "no warnings" MUST set an explicit
                                        ``()`` / ``[]``.
      * ``redaction_status``         -- Stage 29.5 redaction token, carried VERBATIM
                                        (the confirmation requires ``SAFE``; Stage
                                        30.11.9 never invents a redaction-safe claim).
                                        Defaults to ``None``.
      * ``source_ref``               -- optional opaque provenance ref carried onto a
                                        confirmed resolution, or ``None``.
    """

    token_mint: Optional[str] = None
    measurement_status: Optional[str] = None
    migration_event_time_utc: Optional[str] = None
    warnings: Optional[Tuple[str, ...]] = None
    redaction_status: Optional[str] = None
    source_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable model: evidence-source proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_9EvidenceSourceSummary:
    """Immutable Stage 30.11.9 evidence-source proof tally.

    A passive summary of one bounded source-probe pass. It proves, by counting, that
    the source returned bound evidence for EXACTLY the mints that have one
    redaction-safe matching record, and ``None`` (fail closed) for every absent /
    wrong-mint / conflicting / source-erroring mint. Carries only non-negative
    integer counts + a caller-injected timestamp.

      * ``probes_seen``      -- mints probed against the bounded source.
      * ``evidence_returned``-- count that yielded a bound evidence record.
      * ``no_evidence``      -- count that returned ``None`` (fail closed).
      * ``created_at_utc``   -- caller-injected ISO-8601 UTC timestamp.
    """

    probes_seen: int
    evidence_returned: int
    no_evidence: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-probe source outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_9EvidenceSourceProbeOutcome:
    """Immutable Stage 30.11.9 per-probe source outcome.

    Records one probe of the source: the probed mint and whether the source returned
    a bound evidence record for it. Carries only the echoed mint (``""`` when blank /
    unreadable) + a boolean; never the record body, never a secret.

      * ``token_mint``        -- the probed mint (echoed; ``""`` when blank).
      * ``evidence_present``  -- ``True`` iff the source returned a bound record.
    """

    token_mint: str
    evidence_present: bool


# ---------------------------------------------------------------------------
# Immutable model: evidence-source run result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_9EvidenceSourceRunResult:
    """Immutable Stage 30.11.9 bounded evidence-source run result.

    The fake evidence-source proof emits exactly one of these per bounded probe pass.
    It carries the ordered per-probe outcomes and the rolled-up
    ``Stage30_11_9EvidenceSourceSummary``. Carries only safe scalars + the embedded
    outcomes + a caller-injected timestamp.

      * ``outcomes``       -- the ordered per-probe source outcomes.
      * ``summary``        -- the embedded ``Stage30_11_9EvidenceSourceSummary``.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp; NEVER a
                              wall-clock read.
    """

    outcomes: Tuple[Stage30_11_9EvidenceSourceProbeOutcome, ...]
    summary: Stage30_11_9EvidenceSourceSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Author-verified offline source-proof baseline
# ---------------------------------------------------------------------------
#
# The Stage 30.11.9 fake evidence-source proof drives a deterministic SEVEN-mint
# probe set through the mint-keyed source adapter over a deterministic fake record
# provider: exactly TWO mints return a bound evidence record (one with a single
# matching record, one whose provider yields a value-identical duplicate that
# collapses to one), and the other five return None (an absent mint, a provider that
# yields only a wrong-mint record, a provider that yields two DISTINCT conflicting
# records for the mint, a provider that raises, and a blank mint). Mirrored BY VALUE
# by the manifest. NONE is a secret, a raw payload, a host, or a transport
# destination.


STAGE30_11_9_EXPECTED_PROBES_SEEN: int = 7
STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED: int = 2
STAGE30_11_9_EXPECTED_NO_EVIDENCE: int = 5


# The exact safe-shape identity of the single mint whose single matching record the
# source returns on the happy path. The token mint carries the candidate's real
# on-chain identity (the source binds + echoes it verbatim).
STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT: str = "mint-present"


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def migration_evidence_record_field_names() -> Tuple[str, ...]:
    """Return the migration evidence record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_9MigrationEvidenceRecord))


def evidence_source_summary_field_names() -> Tuple[str, ...]:
    """Return the evidence-source summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_9EvidenceSourceSummary))


def evidence_source_probe_outcome_field_names() -> Tuple[str, ...]:
    """Return the per-probe source outcome field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_9EvidenceSourceProbeOutcome)
    )


def evidence_source_run_result_field_names() -> Tuple[str, ...]:
    """Return the evidence-source run result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_9EvidenceSourceRunResult))


__all__ = (
    # Minor version + evidence-source schema identity.
    "STAGE30_11_9_MINOR_VERSION",
    "STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION",
    "STAGE30_11_9_SOURCE_STAGE",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11_9MigrationEvidenceRecord",
    "Stage30_11_9EvidenceSourceSummary",
    "Stage30_11_9EvidenceSourceProbeOutcome",
    "Stage30_11_9EvidenceSourceRunResult",
    # Source-proof baseline.
    "STAGE30_11_9_EXPECTED_PROBES_SEEN",
    "STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED",
    "STAGE30_11_9_EXPECTED_NO_EVIDENCE",
    "STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT",
    # Field-name helpers.
    "migration_evidence_record_field_names",
    "evidence_source_summary_field_names",
    "evidence_source_probe_outcome_field_names",
    "evidence_source_run_result_field_names",
)
