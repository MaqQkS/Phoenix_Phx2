"""Stage 30.11.20 current-price enrichment models.

Stage 30.11.20 ships the passive, pure, stdlib-only MODEL layer for the committed
OFFLINE current-price enrichment adapter -- the seam that closes the current_price
blocker the Stage 30.11.18 contract exposed by REUSING the already-committed Stage
29.2 ``/defi/price`` price source (it builds NO new fetcher and forces NO read()
shim: the adapter calls the source's NATIVE never-raises surface,
``fetch_snapshot(base_mint=...)``, duck-typed). It ships only the carriers +
closed-set vocabulary + pure safe-shape predicates the adapter composes:

  * the closed-set Layer-0 ENRICHMENT decision vocabulary -- ``ENRICHED`` (ONLY
    ``current_price`` was overwritten on a copy of the facts) or one of the
    ``SKIPPED_*`` presence / shape / status / positivity tokens (the fact is left
    UN-enriched and NOT forwarded; no silent pass-through). These are Layer-0 ONLY
    -- distinct from the Stage 30.11.19 market-context Layer-0 tokens, the Stage
    30.11.18 Layer-1 projection tokens, and the Stage 30.11.13 Layer-2 composer
    reasons;
  * the duck-typed price-source surface pins -- the source method name the adapter
    calls (``fetch_snapshot``), the snapshot attrs it requires, and the closed-set
    snapshot status tokens it consumes (mirrored BY VALUE from the committed Stage
    29.2 snapshot vocabulary; this module imports NO Stage 29 module);
  * the per-fact ENRICHMENT result -- the closed-set decision plus the enriched
    facts (present ONLY on ``ENRICHED``; ``None`` on every skip);
  * the per-fact redaction-safe ENRICHMENT event (a record carrying ONLY the
    zero-based index, the closed-set decision token, the safe-echo ids, and a
    caller-injected timestamp -- never a magnitude, a body, a url, or a secret);
  * the rolled-up SESSION report (the ordered enrichment events + the non-negative
    counts + the EMBEDDED Stage 30.11.19 enrichment session report over the
    price-enriched facts + the combined redaction status + a caller-injected
    timestamp);
  * the pure safe-shape predicates the adapter composes.

This module is the MODEL layer ONLY. It builds NO request, runs NO session, reads
NO price source, constructs NO provider transport, calls NO transport, sends NO
message, reads NO process environment, opens NO network connection, opens NO
database, writes NO file, parses no clock, and edits NO committed source / adapter
/ session / renderer / tier-band file. Stage 30.11.20 is fake / offline / no-send
only: the real ``/defi/price`` read (the operator constructs the committed Stage
29.2 price source over a real transport + secret) and the controlled live send
remain a SEPARATE, explicitly operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.19 / 30.11.18
    model modules). The enriched facts + the embedded downstream report are carried
    duck-typed as ``Any`` -- no committed facts / report type is imported here.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No provider, transport-destination, url, host, or request-metadata reference;
    no wallet / signing / trading surface; no public / subscriber routing.
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


STAGE30_11_20_MINOR_VERSION: str = "30.11.20"


# The Stage 30.11.20 report schema version. Names the enrichment result / event /
# report shapes; distinct from every earlier Stage 30.11 schema version. Mirrored
# BY VALUE by the Stage 30.11 manifest section; this module imports no manifest.
STAGE30_11_20_REPORT_SCHEMA_VERSION: str = (
    "stage30_11_20_v0_current_price_enrichment"
)


# The safe-shape source-stage provenance token (names the slice; never a secret /
# host / transport destination).
STAGE30_11_20_SOURCE_STAGE: str = "30.11.20"


# ---------------------------------------------------------------------------
# Duck-typed price-source surface pins
# ---------------------------------------------------------------------------
#
# The locked key decision: the adapter calls ONLY
# ``price_source.fetch_snapshot(base_mint=token_mint)`` -- the NATIVE never-raises
# surface the committed Stage 29.2 price source already exposes -- and reads the
# returned snapshot by attribute. NO read() shim is forced on the ceremony; the
# committed real price source is injectable DIRECTLY. The snapshot status tokens
# are mirrored BY VALUE from the committed Stage 29.2 snapshot vocabulary (a pin
# test cross-checks the mirror); this module imports NO Stage 29 module.


STAGE30_11_20_PRICE_SOURCE_METHOD: str = "fetch_snapshot"


# The snapshot attrs the enrichment reads off the duck-typed price snapshot. A
# snapshot missing any of them is a wrong shape (``SKIPPED_NOT_A_PRICE_READING``).
STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS: Tuple[str, ...] = (
    "price_value",
    "birdeye_price_status",
    "fetched_at_utc",
)


STAGE30_11_20_PRICE_STATUS_PRESENT: str = "PRESENT"
STAGE30_11_20_PRICE_STATUS_MISSING: str = "MISSING"
STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"


# ---------------------------------------------------------------------------
# Closed-set: Layer-0 enrichment decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per base fact. ``ENRICHED`` is the only decision that
# overwrote ``current_price`` (and ONLY ``current_price``) on a copy of the fact
# and forwards it to the committed Stage 30.11.19 session; every ``SKIPPED_*``
# decision is a fail-closed Layer-0 rejection that leaves the fact UN-enriched and
# NOT forwarded (no silent pass-through). NONE of these is a Stage 30.11.19
# market-context Layer-0 token, a Stage 30.11.18 Layer-1 projection token, or a
# Stage 30.11.13 Layer-2 composer reason. Mirrored BY VALUE by the Stage 30.11
# manifest.


PRICE_ENRICHMENT_DECISION_ENRICHED: str = "ENRICHED"
PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS: str = "SKIPPED_NOT_BASE_FACTS"
PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING: str = (
    "SKIPPED_NO_PRICE_READING"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING: str = (
    "SKIPPED_NOT_A_PRICE_READING"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR: str = (
    "SKIPPED_PRICE_SOURCE_ERROR"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING: str = "SKIPPED_PRICE_MISSING"
PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED: str = (
    "SKIPPED_PRICE_STATUS_UNRECOGNIZED"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE: str = (
    "SKIPPED_MISSING_PRICE_VALUE"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE: str = (
    "SKIPPED_INVALID_PRICE_VALUE"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT: str = (
    "SKIPPED_MISSING_PRICE_FETCHED_AT"
)
PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT: str = (
    "SKIPPED_INVALID_PRICE_FETCHED_AT"
)


STAGE30_11_20_ENRICHMENT_DECISIONS: Tuple[str, ...] = (
    PRICE_ENRICHMENT_DECISION_ENRICHED,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED,
    PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT,
)


def is_price_enrichment_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Layer-0 enrichment decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_20_ENRICHMENT_DECISIONS
    )


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------


STAGE30_11_20_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_20_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_20_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_20_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_20_REDACTION_STATUS_REDACTED,
    STAGE30_11_20_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.19 / 30.11.18 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. It gates the fact ids the adapter echoes into
    its redaction-safe enrichment events -- an unsafe value is replaced by
    ``STAGE30_11_20_REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors the Stage
    30.11.19 ``is_safe_echo_id`` BY VALUE. Pure / total; never raises.
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
class Stage30_11_20PriceEnrichmentResult:
    """Immutable per-fact Layer-0 enrichment result.

    Carries the closed-set ``decision`` and the enriched facts. ``enriched_facts``
    is the current-price-filled ``Stage30_11_18HarvestedCandidateFacts`` ONLY on
    ``ENRICHED`` (carried duck-typed ``Any`` so this module imports no committed
    facts type); on every ``SKIPPED_*`` it is ``None`` -- the base fact is NEVER
    mutated and the skipped fact is NOT forwarded to the Stage 30.11.19 session.

      * ``decision``       -- one of ``STAGE30_11_20_ENRICHMENT_DECISIONS``.
      * ``enriched_facts`` -- the enriched facts on ``ENRICHED``; ``None`` on skip.
    """

    decision: str
    enriched_facts: Any


# ---------------------------------------------------------------------------
# Immutable model: one per-fact enrichment event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_20PriceEnrichmentEvent:
    """Immutable redaction-safe per-fact Layer-0 enrichment event.

    The adapter emits exactly one of these per base fact it scanned. It echoes the
    safe-shape identity and pins the closed-set ``decision``; it carries ONLY safe
    scalars + a closed-set token: NO magnitude (the fetched price text goes ONLY
    into the facts copy, NEVER into an event), NO body, NO url, NO exception text,
    NO secret.

      * ``index``        -- the zero-based position in the scanned order.
      * ``decision``     -- one of ``STAGE30_11_20_ENRICHMENT_DECISIONS``.
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
class Stage30_11_20PriceEnrichmentSessionReport:
    """Immutable rolled-up Stage 30.11.20 current-price enrichment report.

    A passive summary of one bounded enrichment run. It carries the ordered per-fact
    enrichment events, the non-negative counts, the EMBEDDED Stage 30.11.19
    enrichment session report over the price-enriched facts (which itself embeds the
    Stage 30.11.18 / 30.11.17 outcomes -- ONE combined nested report), the combined
    redaction status, and a caller-injected timestamp. Carries ONLY safe scalars +
    the embedded redaction-safe records; no secret, no magnitude, no body, no url.

      * ``enrichment_events`` -- the ordered per-fact Layer-0 events (one per
                                 scanned base fact).
      * ``facts_seen``        -- base facts pulled + scanned (<= the candidate cap).
      * ``enriched``          -- facts whose ``current_price`` was overwritten
                                 (``ENRICHED``).
      * ``skipped``           -- facts skipped at Layer-0 (``facts_seen`` minus
                                 ``enriched``).
      * ``downstream_report`` -- the embedded Stage 30.11.19 enrichment session
                                 report over the price-enriched facts (duck-typed
                                 ``Any``).
      * ``redaction_status``  -- one of ``STAGE30_11_20_REDACTION_STATUSES``
                                 (``REDACTED`` iff the enrichment events AND the
                                 embedded downstream report are both redacted).
      * ``created_at_utc``    -- caller-injected ISO-8601 UTC timestamp.
    """

    enrichment_events: Tuple[Stage30_11_20PriceEnrichmentEvent, ...]
    facts_seen: int
    enriched: int
    skipped: int
    downstream_report: Any
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def price_enrichment_result_field_names() -> Tuple[str, ...]:
    """Return the enrichment result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_20PriceEnrichmentResult))


def price_enrichment_event_field_names() -> Tuple[str, ...]:
    """Return the enrichment event field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_20PriceEnrichmentEvent))


def price_enrichment_session_report_field_names() -> Tuple[str, ...]:
    """Return the enrichment session report field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_20PriceEnrichmentSessionReport)
    )


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_20_MINOR_VERSION",
    "STAGE30_11_20_REPORT_SCHEMA_VERSION",
    "STAGE30_11_20_SOURCE_STAGE",
    # Duck-typed price-source surface pins.
    "STAGE30_11_20_PRICE_SOURCE_METHOD",
    "STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS",
    "STAGE30_11_20_PRICE_STATUS_PRESENT",
    "STAGE30_11_20_PRICE_STATUS_MISSING",
    "STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR",
    # Layer-0 enrichment decisions.
    "PRICE_ENRICHMENT_DECISION_ENRICHED",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT",
    "PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT",
    "STAGE30_11_20_ENRICHMENT_DECISIONS",
    "is_price_enrichment_decision",
    # Redaction.
    "STAGE30_11_20_REDACTION_STATUS_REDACTED",
    "STAGE30_11_20_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_20_REDACTED_UNSAFE_ID",
    "STAGE30_11_20_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_20PriceEnrichmentResult",
    "Stage30_11_20PriceEnrichmentEvent",
    "Stage30_11_20PriceEnrichmentSessionReport",
    # Field-name helpers.
    "price_enrichment_result_field_names",
    "price_enrichment_event_field_names",
    "price_enrichment_session_report_field_names",
)
