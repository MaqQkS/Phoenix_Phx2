"""Stage 30.11.22 real-fed dry-run models.

Stage 30.11.22 ships the passive, pure, stdlib-only MODEL layer for the committed
OFFLINE real-fed dry-run wrapper -- the smallest committed bridge that lets a
ceremony feed REAL harvested candidates (the committed Stage 30.11.6 harvest seam's
``Stage30_11_6CandidateProjection`` tuple) through the already-proven Stage 30.11.21
-> 30.11.20 -> 30.11.19 -> 30.11.18 -> 30.11.17 enrichment / compose / dedupe chain
to a RECORDED would-send, NEVER a real send. It ships only the carriers + the
placeholder sentinels + the closed-set redaction vocabulary + pure safe-shape
predicates the adapter composes:

  * the placeholder sentinels the bridge stamps onto the to-be-enriched fields of a
    base ``Stage30_11_18HarvestedCandidateFacts`` (overwritten on enrich, dropped on
    skip -- they never reach the composer): ``PENDING_ENRICHMENT`` for the magnitude /
    anchor fields (a deliberately non-ISO, non-numeric value so a leak would fail
    closed at Stage 30.11.18 Layer-1 rather than silently dispatch) and ``PENDING``
    for ``market_context_status`` (a non-``PRESENT`` value the committed Stage
    30.11.19 enrichment overwrites to ``PRESENT`` on enrich);
  * the no-real-send ATTESTATION -- a record pinning the recording fake transport
    client kind, the in-memory ledger kind, the recorded would-send tally, and the
    two pinned ``False`` flags (``real_send_performed`` / ``real_send_guard_invoked``)
    the path can never flip (it builds NO real transport and imports NO Stage 30.11.16
    real-send guard; the boundary test proves the import discipline);
  * the rolled-up DRY-RUN report -- the harvest front-end counts, the bridge
    base-facts-built count, the Layer-0 enrichment enriched / skipped counts + skip
    histograms (Stage 30.11.21 migration / 30.11.20 price / 30.11.19 market-context),
    the Layer-1 projection counts (Stage 30.11.18), the Layer-2 compose / dispatch /
    dedupe-blocked / would-send counts + stop reason (Stage 30.11.17), the EMBEDDED
    Stage 30.11.21 session report (the full combined nested report -- nothing is
    lost), the attestation, the combined redaction status, and a caller-injected
    timestamp;
  * the pure safe-shape predicates the adapter composes.

This module is the MODEL layer ONLY. It builds NO base fact, runs NO harvest, runs
NO session, drives NO ledger, calls NO transport, sends NO message, reads NO process
environment, opens NO network connection, opens NO database, writes NO file, parses
no clock, and edits NO committed harvest / enrichment / composer / dedupe / ledger /
renderer / tier-band file. Stage 30.11.22 is fake / offline / no-send only: the real
live event source + provider sources (the operator constructs them at the
ceremony) and the controlled live send remain a SEPARATE, explicitly
operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.21 / 30.11.20 /
    30.11.19 / 30.11.18 / 30.11.17 model modules). The embedded Stage 30.11.21
    session report is carried duck-typed as ``Any`` -- the committed report type is
    NEVER imported here.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, url, host, or request-metadata
    reference; no wallet / signing / trading surface; no public / subscriber
    routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_11_22_MINOR_VERSION: str = "30.11.22"


# The Stage 30.11.22 report schema version. Names the dry-run report / attestation
# shapes; distinct from every earlier Stage 30.11 schema version. Mirrored BY VALUE
# by the Stage 30.11 manifest section; this module imports no manifest.
STAGE30_11_22_REPORT_SCHEMA_VERSION: str = (
    "stage30_11_22_v0_real_fed_dry_run"
)


# The safe-shape source-stage provenance token (names the slice; never a secret /
# host / transport destination).
STAGE30_11_22_SOURCE_STAGE: str = "30.11.22"


# ---------------------------------------------------------------------------
# Bridge placeholder sentinels
# ---------------------------------------------------------------------------
#
# The Stage 30.11.22 bridge maps a committed Stage 30.11.6 candidate projection onto
# a base Stage 30.11.18 facts record, carrying the REAL ``token_mint`` + run-scoped
# ``candidate_id`` VERBATIM and stamping these sentinels onto every field the
# enrichment chain fills. The enrichment overwrites a sentinel on enrich and DROPS
# the fact on skip (no silent pass-through), so a sentinel can NEVER reach the
# committed composer. ``PENDING_ENRICHMENT`` is deliberately non-ISO + non-numeric:
# a (bug) leak past the enrichment would fail closed at the Stage 30.11.18 Layer-1
# shape / positivity check, never silently dispatch. ``PENDING`` is a non-``PRESENT``
# market-context status the committed Stage 30.11.19 enrichment overwrites to
# ``PRESENT`` on enrich. Mirrored BY VALUE by the Stage 30.11 manifest.


STAGE30_11_22_PENDING_ENRICHMENT: str = "PENDING_ENRICHMENT"
STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS: str = "PENDING"


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------


STAGE30_11_22_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_22_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_22_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_22_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
    STAGE30_11_22_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.21 / 30.11.18 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. It gates the transport-client / ledger kind
    tokens the adapter echoes into the redaction-safe attestation -- an unsafe value
    is replaced by ``STAGE30_11_22_REDACTED_UNSAFE_ID`` rather than echoed raw.
    Mirrors the Stage 30.11.21 ``is_safe_echo_id`` BY VALUE. Pure / total; never
    raises.
    """
    if not isinstance(value, str):
        return False
    if value == "" or len(value) > 128:
        return False
    for ch in value:
        if "A" <= ch <= "Z":
            continue
        if "a" <= ch <= "z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_" or ch == "-":
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Immutable model: no-real-send attestation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_22NoRealSendAttestation:
    """Immutable redaction-safe no-real-send attestation.

    Pins, for one dry-run, that the path RECORDED would-sends through a fake
    transport client and performed NO real send. Carries ONLY safe scalars + safe-echo
    kind tokens: NO body, NO url, NO secret.

      * ``transport_client_kind`` -- the safe-echo class-name token of the recording
                                     fake transport client (``REDACTED_UNSAFE_ID``
                                     when not a safe-echo token).
      * ``ledger_kind``           -- the safe-echo class-name token of the dedupe
                                     ledger (the in-memory ledger by default).
      * ``would_send_recorded``   -- the recorded would-send count (FAKE client) --
                                     NEVER a real send.
      * ``real_send_performed``   -- pinned ``False``: the committed chain opens no
                                     socket + the transport is recording-only.
      * ``real_send_guard_invoked`` -- pinned ``False``: the path imports NO Stage
                                     30.11.16 real-send guard (the boundary test
                                     proves the import discipline).
    """

    transport_client_kind: str
    ledger_kind: str
    would_send_recorded: int
    real_send_performed: bool
    real_send_guard_invoked: bool


# ---------------------------------------------------------------------------
# Immutable model: rolled-up real-fed dry-run report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_22RealFedDryRunReport:
    """Immutable rolled-up Stage 30.11.22 real-fed dry-run report.

    A passive summary of one bounded dry-run: real harvested candidates -> the
    Stage 30.11.22 bridge -> the committed Stage 30.11.21 -> 30.11.20 -> 30.11.19 ->
    30.11.18 -> 30.11.17 chain -> a RECORDED would-send. It carries the harvest
    front-end counts, the bridge base-facts-built count, the per-stage Layer-0
    enriched / skipped counts + skip histograms, the Layer-1 projection counts, the
    Layer-2 compose / dispatch / dedupe-blocked / would-send counts + stop reason,
    the EMBEDDED Stage 30.11.21 session report (the full combined nested report), the
    no-real-send attestation, the combined redaction status, and a caller-injected
    timestamp. Carries ONLY safe scalars + the embedded redaction-safe records; no
    secret, no magnitude, no body, no url, no transport destination.

      * ``events_seen``                       -- raw source events the harvest pulled
                                                 (<= ``max_harvest``).
      * ``candidates_harvested``              -- events that yielded a candidate
                                                 projection.
      * ``harvest_skipped_assembly_failed`` /
        ``harvest_skipped_projection_rejected`` -- the harvest skip tallies.
      * ``base_facts_built``                  -- candidate projections the bridge
                                                 mapped onto base facts (1:1).
      * ``migration_enriched`` / ``migration_skipped`` /
        ``migration_skip_histogram``          -- Stage 30.11.21 Layer-0 tally + the
                                                 sorted ``(decision, count)``
                                                 histogram.
      * ``price_enriched`` / ``price_skipped`` /
        ``price_skip_histogram``              -- Stage 30.11.20 Layer-0 tally +
                                                 histogram.
      * ``market_enriched`` / ``market_skipped`` /
        ``market_skip_histogram``             -- Stage 30.11.19 Layer-0 tally +
                                                 histogram.
      * ``projected`` / ``rejected_projection`` -- Stage 30.11.18 Layer-1 counts.
      * ``composed``                          -- Stage 30.11.17 compositions attempted.
      * ``dispatched`` / ``dedupe_blocked``   -- Stage 30.11.17 outcome counts.
      * ``would_send_recorded``               -- Stage 30.11.17 recorded would-send
                                                 tally (FAKE client; == ``dispatched``).
      * ``stop_reason``                       -- the Stage 30.11.17 session stop reason.
      * ``enrichment_report``                 -- the embedded Stage 30.11.21 session
                                                 report (duck-typed ``Any``).
      * ``attestation``                       -- the no-real-send attestation.
      * ``redaction_status``                  -- one of
                                                 ``STAGE30_11_22_REDACTION_STATUSES``
                                                 (``REDACTED`` iff this report's own
                                                 fields AND the embedded session
                                                 report are both redacted).
      * ``created_at_utc``                    -- caller-injected ISO-8601 UTC.
    """

    events_seen: int
    candidates_harvested: int
    harvest_skipped_assembly_failed: int
    harvest_skipped_projection_rejected: int
    base_facts_built: int
    migration_enriched: int
    migration_skipped: int
    migration_skip_histogram: Tuple[Tuple[str, int], ...]
    price_enriched: int
    price_skipped: int
    price_skip_histogram: Tuple[Tuple[str, int], ...]
    market_enriched: int
    market_skipped: int
    market_skip_histogram: Tuple[Tuple[str, int], ...]
    projected: int
    rejected_projection: int
    composed: int
    dispatched: int
    dedupe_blocked: int
    would_send_recorded: int
    stop_reason: str
    enrichment_report: Any
    attestation: Stage30_11_22NoRealSendAttestation
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def no_real_send_attestation_field_names() -> Tuple[str, ...]:
    """Return the no-real-send attestation field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_22NoRealSendAttestation))


def real_fed_dry_run_report_field_names() -> Tuple[str, ...]:
    """Return the real-fed dry-run report field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_22RealFedDryRunReport))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_22_MINOR_VERSION",
    "STAGE30_11_22_REPORT_SCHEMA_VERSION",
    "STAGE30_11_22_SOURCE_STAGE",
    # Bridge placeholder sentinels.
    "STAGE30_11_22_PENDING_ENRICHMENT",
    "STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS",
    # Redaction.
    "STAGE30_11_22_REDACTION_STATUS_REDACTED",
    "STAGE30_11_22_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_22_REDACTED_UNSAFE_ID",
    "STAGE30_11_22_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_22NoRealSendAttestation",
    "Stage30_11_22RealFedDryRunReport",
    # Field-name helpers.
    "no_real_send_attestation_field_names",
    "real_fed_dry_run_report_field_names",
)
