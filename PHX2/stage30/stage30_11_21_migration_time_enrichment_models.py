"""Stage 30.11.21 migration-time enrichment models.

Stage 30.11.21 ships the passive, pure, stdlib-only MODEL layer for the committed
OFFLINE migration-time enrichment adapter -- the seam that closes the LAST hand-fed
harvested-facts blocker the Stage 30.11.18 contract exposed
(``REJECTED_MIGRATION_NOT_CONFIRMED`` / ``REJECTED_MISSING_MIGRATION_TIME_UTC`` /
``REJECTED_INVALID_MIGRATION_TIME_UTC``) by REUSING the already-committed Stage
30.11.8 migration-confirmation authority (it builds NO new fetcher and COPIES no
bare timestamp: the adapter resolves the migration verdict through the committed
Stage 30.11.8 ``resolve_candidate_migration`` over an injected, duck-typed Stage
30.11.9 ``lookup_migration_evidence`` source, and fills the facts ONLY from a
CONFIRMED resolution). It ships only the carriers + closed-set vocabulary + pure
safe-shape predicates the adapter composes:

  * the closed-set Layer-0 ENRICHMENT decision vocabulary -- ``ENRICHED`` (the
    migration fields were overwritten on a copy of the facts from a CONFIRMED Stage
    30.11.8 resolution) or one of the ``SKIPPED_*`` tokens (the fact is left
    UN-enriched and NOT forwarded; no silent pass-through). The ten evidence /
    anchor ``SKIPPED_*`` tokens MIRROR the committed Stage 30.11.8 fail reasons BY
    VALUE (each ``SKIPPED_<R>`` carries the Stage 30.11.8 reason ``<R>``), so the
    session report shows the PRECISE confirmation cause; ``SKIPPED_NOT_BASE_FACTS``
    is the local non-facts guard. These are Layer-0 ONLY -- distinct from the Stage
    30.11.20 current-price Layer-0 tokens, the Stage 30.11.19 market-context Layer-0
    tokens, the Stage 30.11.18 Layer-1 projection tokens, and the Stage 30.11.13
    Layer-2 composer reasons;
  * the duck-typed evidence-source surface pins -- the method name the committed
    Stage 30.11.8 confirmation calls (``lookup_migration_evidence``), the Stage
    30.11.8 resolution attrs the enrichment reads, and the single confirming
    decision token (mirrored BY VALUE from the committed Stage 30.11.8 vocabulary;
    this module imports NO Stage 30.11.8 module);
  * the per-fact ENRICHMENT result -- the closed-set decision plus the enriched
    facts (present ONLY on ``ENRICHED``; ``None`` on every skip);
  * the per-fact redaction-safe ENRICHMENT event (a record carrying ONLY the
    zero-based index, the closed-set decision token, the safe-echo ids, and a
    caller-injected timestamp -- never a migration anchor, a provenance ref, a body,
    a url, or a secret);
  * the rolled-up SESSION report (the ordered enrichment events + the non-negative
    counts + the EMBEDDED Stage 30.11.20 enrichment session report over the
    migration-enriched facts + the combined redaction status + a caller-injected
    timestamp);
  * the pure safe-shape predicates the adapter composes.

This module is the MODEL layer ONLY. It builds NO request, runs NO session, reads
NO evidence source, runs NO confirmation, constructs NO provider transport, calls
NO transport, sends NO message, reads NO process environment, opens NO network
connection, opens NO database, writes NO file, parses no clock, and edits NO
committed source / adapter / session / renderer / tier-band file. Stage 30.11.21 is
fake / offline / no-send only: the real Stage 29.5 migration evidence (the operator
wraps the committed Stage 29.5 reader behind the injected Stage 30.11.9 provider
seam) and the controlled live send remain a SEPARATE, explicitly
operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.20 / 30.11.19 /
    30.11.18 model modules). The enriched facts + the embedded downstream report are
    carried duck-typed as ``Any`` -- no committed facts / report / resolution type
    is imported here.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No provider, transport-destination, url, host, or request-metadata reference;
    no wallet / signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` / ``re`` import; timestamps are caller-injected.
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


STAGE30_11_21_MINOR_VERSION: str = "30.11.21"


# The Stage 30.11.21 report schema version. Names the enrichment result / event /
# report shapes; distinct from every earlier Stage 30.11 schema version. Mirrored
# BY VALUE by the Stage 30.11 manifest section; this module imports no manifest.
STAGE30_11_21_REPORT_SCHEMA_VERSION: str = (
    "stage30_11_21_v0_migration_time_enrichment"
)


# The safe-shape source-stage provenance token (names the slice; never a secret /
# host / transport destination).
STAGE30_11_21_SOURCE_STAGE: str = "30.11.21"


# ---------------------------------------------------------------------------
# Duck-typed evidence-source + Stage 30.11.8 resolution surface pins
# ---------------------------------------------------------------------------
#
# The locked key decision: the adapter REUSES the committed Stage 30.11.8
# ``resolve_candidate_migration(base, evidence_source)``, which calls ONLY
# ``evidence_source.lookup_migration_evidence(token_mint)`` -- the surface the
# committed Stage 30.11.9 mint-keyed evidence-source adapter already exposes -- and
# returns a Stage 30.11.8 resolution the adapter reads by attribute. The method
# name + the resolution attrs + the confirming decision token are mirrored BY VALUE
# from the committed Stage 30.11.8 / 30.11.9 vocabulary (a manifest pin cross-checks
# the mirror); this module imports NO Stage 30.11.8 / 30.11.9 module.


STAGE30_11_21_EVIDENCE_SOURCE_METHOD: str = "lookup_migration_evidence"


# The Stage 30.11.8 resolution attrs the enrichment reads. ``confirmed`` gates the
# enrichment; ``migration_event_time_utc`` is the confirmed migration anchor written
# to ``migration_time_utc``; ``source_ref`` is the safe-gated provenance written to
# ``migration_source``; ``reason`` is the closed-set Stage 30.11.8 cause the adapter
# maps onto its mirrored ``SKIPPED_*`` token on a fail-closed resolution.
STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS: Tuple[str, ...] = (
    "confirmed",
    "migration_event_time_utc",
    "source_ref",
    "reason",
)


# The single Stage 30.11.8 confirm-pass decision the enrichment treats as the ONLY
# confirmed verdict (mirrored BY VALUE from the committed Stage 30.11.8
# ``CONFIRM_DECISION_CONFIRMED``).
STAGE30_11_21_CONFIRM_DECISION_CONFIRMED: str = "CONFIRMED_MIGRATION"


# ---------------------------------------------------------------------------
# Closed-set: Layer-0 enrichment decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per base fact. ``ENRICHED`` is the only decision that
# overwrote the migration fields (``migration_time_utc`` / ``migration_confirmed`` /
# ``migration_source``) on a copy of the fact and forwards it to the committed Stage
# 30.11.20 session; every ``SKIPPED_*`` decision is a fail-closed Layer-0 rejection
# that leaves the fact UN-enriched and NOT forwarded (no silent pass-through). The
# ten evidence / anchor ``SKIPPED_*`` tokens carry the committed Stage 30.11.8 fail
# reason VERBATIM after the ``SKIPPED_`` prefix; ``SKIPPED_NOT_BASE_FACTS`` is the
# local non-facts guard. NONE is a Stage 30.11.20 / 30.11.19 Layer-0 token, a Stage
# 30.11.18 Layer-1 token, or a Stage 30.11.13 Layer-2 reason. Mirrored BY VALUE by
# the Stage 30.11 manifest.


MIGRATION_ENRICHMENT_DECISION_ENRICHED: str = "ENRICHED"
MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS: str = (
    "SKIPPED_NOT_BASE_FACTS"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT: str = (
    "SKIPPED_BLANK_CANDIDATE_MINT"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE: str = (
    "SKIPPED_MISSING_MIGRATION_EVIDENCE"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH: str = (
    "SKIPPED_EVIDENCE_MINT_MISMATCH"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE: str = (
    "SKIPPED_REDACTION_UNSAFE"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION: str = (
    "SKIPPED_UNKNOWN_MIGRATION"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED: str = (
    "SKIPPED_PARTIAL_MIGRATION_UNVERIFIED"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION: str = (
    "SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE: str = (
    "SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE: str = (
    "SKIPPED_INVALID_MIGRATION_EVIDENCE"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE: str = (
    "SKIPPED_STALE_MIGRATION_EVIDENCE"
)
MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR: str = (
    "SKIPPED_INVALID_MIGRATION_ANCHOR"
)


STAGE30_11_21_ENRICHMENT_DECISIONS: Tuple[str, ...] = (
    MIGRATION_ENRICHMENT_DECISION_ENRICHED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR,
)


def is_migration_enrichment_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Layer-0 enrichment decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_21_ENRICHMENT_DECISIONS
    )


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------


STAGE30_11_21_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_21_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_21_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_21_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_21_REDACTION_STATUS_REDACTED,
    STAGE30_11_21_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.20 / 30.11.19 / 30.11.18
    non-blank check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. It gates the fact ids the adapter echoes into
    its redaction-safe enrichment events AND the ``source_ref`` provenance the
    adapter writes onto ``migration_source`` -- an unsafe value is replaced by
    ``STAGE30_11_21_REDACTED_UNSAFE_ID`` (events) or dropped to ``None`` (the
    migration_source provenance) rather than carried raw. Mirrors the Stage 30.11.20
    ``is_safe_echo_id`` BY VALUE. Pure / total; never raises.
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
# Immutable model: one per-fact enrichment result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_21MigrationEnrichmentResult:
    """Immutable per-fact Layer-0 enrichment result.

    Carries the closed-set ``decision`` and the enriched facts. ``enriched_facts``
    is the migration-filled ``Stage30_11_18HarvestedCandidateFacts`` ONLY on
    ``ENRICHED`` (carried duck-typed ``Any`` so this module imports no committed
    facts type); on every ``SKIPPED_*`` it is ``None`` -- the base fact is NEVER
    mutated and the skipped fact is NOT forwarded to the Stage 30.11.20 session.

      * ``decision``       -- one of ``STAGE30_11_21_ENRICHMENT_DECISIONS``.
      * ``enriched_facts`` -- the enriched facts on ``ENRICHED``; ``None`` on skip.
    """

    decision: str
    enriched_facts: Any


# ---------------------------------------------------------------------------
# Immutable model: one per-fact enrichment event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_21MigrationEnrichmentEvent:
    """Immutable redaction-safe per-fact Layer-0 enrichment event.

    The adapter emits exactly one of these per base fact it scanned. It echoes the
    safe-shape identity and pins the closed-set ``decision``; it carries ONLY safe
    scalars + a closed-set token: NO migration anchor (the confirmed anchor goes
    ONLY into the facts copy, NEVER into an event), NO provenance ref, NO body, NO
    url, NO exception text, NO secret.

      * ``index``        -- the zero-based position in the scanned order.
      * ``decision``     -- one of ``STAGE30_11_21_ENRICHMENT_DECISIONS``.
      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids (``""`` when
                            unreadable; ``REDACTED_UNSAFE_ID`` when present but not
                            a safe-echo token).
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp.
    """

    index: int
    decision: str
    candidate_id: str
    token_mint: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: rolled-up enrichment session report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_21MigrationEnrichmentSessionReport:
    """Immutable rolled-up Stage 30.11.21 migration-time enrichment report.

    A passive summary of one bounded enrichment run. It carries the ordered per-fact
    enrichment events, the non-negative counts, the EMBEDDED Stage 30.11.20
    enrichment session report over the migration-enriched facts (which itself embeds
    the Stage 30.11.19 / 30.11.18 / 30.11.17 outcomes -- ONE combined nested
    report), the combined redaction status, and a caller-injected timestamp. Carries
    ONLY safe scalars + the embedded redaction-safe records; no secret, no anchor, no
    magnitude, no body, no url.

      * ``enrichment_events`` -- the ordered per-fact Layer-0 events (one per
                                 scanned base fact).
      * ``facts_seen``        -- base facts pulled + scanned (<= the candidate cap).
      * ``enriched``          -- facts whose migration fields were overwritten from a
                                 CONFIRMED resolution (``ENRICHED``).
      * ``skipped``           -- facts skipped at Layer-0 (``facts_seen`` minus
                                 ``enriched``).
      * ``downstream_report`` -- the embedded Stage 30.11.20 enrichment session
                                 report over the migration-enriched facts (duck-typed
                                 ``Any``).
      * ``redaction_status``  -- one of ``STAGE30_11_21_REDACTION_STATUSES``
                                 (``REDACTED`` iff the enrichment events AND the
                                 embedded downstream report are both redacted).
      * ``created_at_utc``    -- caller-injected ISO-8601 UTC timestamp.
    """

    enrichment_events: Tuple[Stage30_11_21MigrationEnrichmentEvent, ...]
    facts_seen: int
    enriched: int
    skipped: int
    downstream_report: Any
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def migration_enrichment_result_field_names() -> Tuple[str, ...]:
    """Return the enrichment result field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_21MigrationEnrichmentResult)
    )


def migration_enrichment_event_field_names() -> Tuple[str, ...]:
    """Return the enrichment event field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_21MigrationEnrichmentEvent)
    )


def migration_enrichment_session_report_field_names() -> Tuple[str, ...]:
    """Return the enrichment session report field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_21MigrationEnrichmentSessionReport)
    )


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_21_MINOR_VERSION",
    "STAGE30_11_21_REPORT_SCHEMA_VERSION",
    "STAGE30_11_21_SOURCE_STAGE",
    # Duck-typed evidence-source + resolution surface pins.
    "STAGE30_11_21_EVIDENCE_SOURCE_METHOD",
    "STAGE30_11_21_MIGRATION_RESOLUTION_REQUIRED_ATTRS",
    "STAGE30_11_21_CONFIRM_DECISION_CONFIRMED",
    # Layer-0 enrichment decisions.
    "MIGRATION_ENRICHMENT_DECISION_ENRICHED",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE",
    "MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR",
    "STAGE30_11_21_ENRICHMENT_DECISIONS",
    "is_migration_enrichment_decision",
    # Redaction.
    "STAGE30_11_21_REDACTION_STATUS_REDACTED",
    "STAGE30_11_21_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_21_REDACTED_UNSAFE_ID",
    "STAGE30_11_21_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_21MigrationEnrichmentResult",
    "Stage30_11_21MigrationEnrichmentEvent",
    "Stage30_11_21MigrationEnrichmentSessionReport",
    # Field-name helpers.
    "migration_enrichment_result_field_names",
    "migration_enrichment_event_field_names",
    "migration_enrichment_session_report_field_names",
)
