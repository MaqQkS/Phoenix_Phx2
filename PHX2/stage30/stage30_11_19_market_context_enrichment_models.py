"""Stage 30.11.19 market-context enrichment models.

Stage 30.11.19 ships the passive, pure, stdlib-only MODEL layer for the committed
OFFLINE market-context enrichment adapter -- the seam that closes the liquidity
blocker the Stage 30.11.18 contract exposed by REUSING the already-committed Stage
30.4.3 token-overview market-context source (it builds NO new fetcher). It ships
only the carriers + closed-set vocabulary + pure safe-shape predicates the adapter
composes:

  * the closed-set Layer-0 ENRICHMENT decision vocabulary -- ``ENRICHED`` (the
    market-context bundle was filled) or one of the ``SKIPPED_*`` presence / shape /
    positivity / staleness tokens (the fact is left UN-enriched and NOT forwarded;
    no silent pass-through). These are Layer-0 ONLY -- distinct from the Stage
    30.11.18 Layer-1 projection tokens and the Stage 30.11.13 Layer-2 composer
    reasons;
  * the per-fact ENRICHMENT result -- the closed-set decision plus the enriched
    facts (present ONLY on ``ENRICHED``; ``None`` on every skip);
  * the per-fact redaction-safe ENRICHMENT event (a record carrying ONLY the
    zero-based index, the closed-set decision token, the safe-echo ids, and a
    caller-injected timestamp -- never a magnitude, a body, a url, or a secret);
  * the rolled-up SESSION report (the ordered enrichment events + the non-negative
    counts + the EMBEDDED Stage 30.11.18 session report over the enriched facts +
    the combined redaction status + a caller-injected timestamp);
  * the pure safe-shape predicates the adapter composes.

This module is the MODEL layer ONLY. It builds NO request, runs NO session, reads
NO market-context source, constructs NO provider transport, calls NO transport,
sends NO message, reads NO process environment, opens NO network connection, opens
NO database, writes NO file, parses no clock, and edits NO committed source /
adapter / session / renderer / tier-band file. Stage 30.11.19 is fake / offline /
no-send only: the real token-overview read (the operator constructs the committed
Stage 30.4.3 source over a real Stage 29.2 transport) and the controlled live send
remain a SEPARATE, explicitly operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.18 / 30.11.17
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


STAGE30_11_19_MINOR_VERSION: str = "30.11.19"


# The Stage 30.11.19 report schema version. Names the enrichment result / event /
# report shapes; distinct from every earlier Stage 30.11 schema version. Mirrored
# BY VALUE by the Stage 30.11 manifest section; this module imports no manifest.
STAGE30_11_19_REPORT_SCHEMA_VERSION: str = (
    "stage30_11_19_v0_market_context_enrichment"
)


# The safe-shape source-stage provenance token (names the slice; never a secret /
# host / transport destination).
STAGE30_11_19_SOURCE_STAGE: str = "30.11.19"


# ---------------------------------------------------------------------------
# Closed-set: Layer-0 enrichment decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per base fact. ``ENRICHED`` is the only decision that filled
# the coherent market-context bundle (current_market_cap_usd, liquidity_usd,
# market_context_fetched_at_utc, market_context_status=PRESENT) on a copy of the
# fact and forwards it to the committed Stage 30.11.18 session; every ``SKIPPED_*``
# decision is a fail-closed Layer-0 rejection that leaves the fact UN-enriched and
# NOT forwarded (no silent pass-through). NONE of these is a Stage 30.11.18 Layer-1
# projection token or a Stage 30.11.13 Layer-2 composer reason. Mirrored BY VALUE
# by the Stage 30.11 manifest.


ENRICHMENT_DECISION_ENRICHED: str = "ENRICHED"
ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS: str = "SKIPPED_NOT_BASE_FACTS"
ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING: str = (
    "SKIPPED_NO_MARKET_CONTEXT_READING"
)
ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING: str = (
    "SKIPPED_NOT_A_MARKET_CONTEXT_READING"
)
ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT: str = (
    "SKIPPED_STALE_MARKET_CONTEXT"
)
ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP: str = (
    "SKIPPED_MISSING_MARKET_CAP"
)
ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP: str = (
    "SKIPPED_INVALID_MARKET_CAP"
)
ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD: str = (
    "SKIPPED_MISSING_LIQUIDITY_USD"
)
ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD: str = (
    "SKIPPED_INVALID_LIQUIDITY_USD"
)
ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT: str = (
    "SKIPPED_MISSING_OBSERVED_AT"
)
ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT: str = (
    "SKIPPED_INVALID_OBSERVED_AT"
)


STAGE30_11_19_ENRICHMENT_DECISIONS: Tuple[str, ...] = (
    ENRICHMENT_DECISION_ENRICHED,
    ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING,
    ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING,
    ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT,
    ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP,
    ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP,
    ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD,
    ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD,
    ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT,
    ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT,
)


def is_enrichment_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Layer-0 enrichment decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_11_19_ENRICHMENT_DECISIONS
    )


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------


STAGE30_11_19_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_19_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_19_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_19_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_19_REDACTION_STATUS_REDACTED,
    STAGE30_11_19_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.18 / 30.11.17 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. It gates the fact ids the adapter echoes into
    its redaction-safe enrichment events -- an unsafe value is replaced by
    ``STAGE30_11_19_REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors the Stage
    30.11.18 ``is_safe_echo_id`` BY VALUE. Pure / total; never raises.
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
class Stage30_11_19EnrichmentResult:
    """Immutable per-fact Layer-0 enrichment result.

    Carries the closed-set ``decision`` and the enriched facts. ``enriched_facts``
    is the market-context-filled ``Stage30_11_18HarvestedCandidateFacts`` ONLY on
    ``ENRICHED`` (carried duck-typed ``Any`` so this module imports no committed
    facts type); on every ``SKIPPED_*`` it is ``None`` -- the base fact is NEVER
    mutated and the skipped fact is NOT forwarded to the Stage 30.11.18 session.

      * ``decision``       -- one of ``STAGE30_11_19_ENRICHMENT_DECISIONS``.
      * ``enriched_facts`` -- the enriched facts on ``ENRICHED``; ``None`` on skip.
    """

    decision: str
    enriched_facts: Any


# ---------------------------------------------------------------------------
# Immutable model: one per-fact enrichment event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_19EnrichmentEvent:
    """Immutable redaction-safe per-fact Layer-0 enrichment event.

    The adapter emits exactly one of these per base fact it scanned. It echoes the
    safe-shape identity and pins the closed-set ``decision``; it carries ONLY safe
    scalars + a closed-set token: NO magnitude, NO body, NO url, NO exception text,
    NO secret.

      * ``index``        -- the zero-based position in the scanned order.
      * ``decision``     -- one of ``STAGE30_11_19_ENRICHMENT_DECISIONS``.
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
class Stage30_11_19EnrichmentSessionReport:
    """Immutable rolled-up Stage 30.11.19 market-context enrichment report.

    A passive summary of one bounded enrichment run. It carries the ordered per-fact
    enrichment events, the non-negative counts, the EMBEDDED Stage 30.11.18 session
    report over the enriched facts (the Layer-1 / Layer-2 outcome), the combined
    redaction status, and a caller-injected timestamp. Carries ONLY safe scalars +
    the embedded redaction-safe records; no secret, no magnitude, no body, no url.

      * ``enrichment_events`` -- the ordered per-fact Layer-0 events (one per
                                 scanned base fact).
      * ``facts_seen``        -- base facts pulled + scanned (<= the candidate cap).
      * ``enriched``          -- facts that filled the bundle (``ENRICHED``).
      * ``skipped``           -- facts skipped at Layer-0 (``facts_seen`` minus
                                 ``enriched``).
      * ``downstream_report`` -- the embedded Stage 30.11.18 session report over the
                                 enriched facts (duck-typed ``Any``).
      * ``redaction_status``  -- one of ``STAGE30_11_19_REDACTION_STATUSES``
                                 (``REDACTED`` iff the enrichment events AND the
                                 embedded downstream report are both redacted).
      * ``created_at_utc``    -- caller-injected ISO-8601 UTC timestamp.
    """

    enrichment_events: Tuple[Stage30_11_19EnrichmentEvent, ...]
    facts_seen: int
    enriched: int
    skipped: int
    downstream_report: Any
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def enrichment_result_field_names() -> Tuple[str, ...]:
    """Return the enrichment result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_19EnrichmentResult))


def enrichment_event_field_names() -> Tuple[str, ...]:
    """Return the enrichment event field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_19EnrichmentEvent))


def enrichment_session_report_field_names() -> Tuple[str, ...]:
    """Return the enrichment session report field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_11_19EnrichmentSessionReport)
    )


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_19_MINOR_VERSION",
    "STAGE30_11_19_REPORT_SCHEMA_VERSION",
    "STAGE30_11_19_SOURCE_STAGE",
    # Layer-0 enrichment decisions.
    "ENRICHMENT_DECISION_ENRICHED",
    "ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS",
    "ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING",
    "ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING",
    "ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT",
    "ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP",
    "ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP",
    "ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD",
    "ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD",
    "ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT",
    "ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT",
    "STAGE30_11_19_ENRICHMENT_DECISIONS",
    "is_enrichment_decision",
    # Redaction.
    "STAGE30_11_19_REDACTION_STATUS_REDACTED",
    "STAGE30_11_19_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_19_REDACTED_UNSAFE_ID",
    "STAGE30_11_19_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_19EnrichmentResult",
    "Stage30_11_19EnrichmentEvent",
    "Stage30_11_19EnrichmentSessionReport",
    # Field-name helpers.
    "enrichment_result_field_names",
    "enrichment_event_field_names",
    "enrichment_session_report_field_names",
)
