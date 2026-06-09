"""Stage 30.11.18 harvested-facts curated compose session models.

Stage 30.11.18 ships the passive, pure, stdlib-only MODEL layer for the committed
OFFLINE harvested-facts -> curated compose session adapter -- the smallest
committed bridge that lets a ceremony feed already-harvested + enriched candidate
FACTS (rather than hand-built requests) into the already-proven Stage 30.11.17
operator-curated compose session. It ships only the carriers + closed-set
vocabularies + pure safe-shape predicates the adapter composes:

  * the harvested-candidate FACTS carrier -- a flat record of the SAME 13
    revalidated inputs the committed Stage 30.11.13 composer consumes (so the
    adapter is a near 1:1 map); a ceremony / enricher produces it from a real
    harvest source. ``liquidity_usd`` and ``market_context_fetched_at_utc`` are
    REQUIRED here (the composer fails closed without them), so a fact missing
    either is rejected EARLY with a precise Layer-1 token rather than buried in a
    composer reason;
  * the closed-set Layer-1 PROJECTION decision vocabulary -- ``PROJECTED`` (a
    well-formed request was built) or one of the ``REJECTED_*`` presence / shape /
    positivity tokens (the fact never reaches the composer). These are Layer-1
    ONLY: freshness / ATH / tier / gate stay the committed composer's authoritative
    Layer-2 reasons, surfaced VERBATIM in the embedded session result;
  * the per-fact redaction-safe PROJECTION event (a record carrying ONLY the
    zero-based index, the closed-set decision token, the safe-echo ids, and a
    caller-injected timestamp -- never a magnitude, a body, a url, or a secret);
  * the rolled-up SESSION report (the ordered projection events + the non-negative
    Layer-1 counts + the embedded Stage 30.11.17 session result + the redaction
    status + a caller-injected timestamp);
  * the pure safe-shape predicates the adapter composes.

This module is the MODEL layer ONLY. It builds NO request, runs NO session, drives
NO ledger, calls NO transport, sends NO message, reads NO process environment,
opens NO network connection, opens NO database, writes NO file, signs nothing,
trades nothing, parses no clock, and edits NO composer / dedupe / ledger /
session / renderer / tier-band file. Stage 30.11.18 is fake / offline / no-send
only: the real harvest + market-context enrichment that produces the facts, and
the controlled live send, remain a SEPARATE, explicitly operator-authorized step
this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.17 / 30.11.16 /
    30.11.15 model modules). The embedded Stage 30.11.17 session result is carried
    duck-typed as ``Any`` -- the committed result type is NEVER imported here.
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
from typing import Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_11_18_MINOR_VERSION: str = "30.11.18"


# The Stage 30.11.18 report schema version. Names the facts / projection-event /
# report shapes; distinct from every earlier Stage 30.11 schema version. Mirrored
# BY VALUE by the Stage 30.11 manifest section; this module imports no manifest.
STAGE30_11_18_REPORT_SCHEMA_VERSION: str = (
    "stage30_11_18_v0_harvested_facts_curated_session"
)


# The safe-shape source-stage provenance token (names the slice; never a secret /
# host / transport destination).
STAGE30_11_18_SOURCE_STAGE: str = "30.11.18"


# ---------------------------------------------------------------------------
# Closed-set: Layer-1 projection decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per harvested fact. ``PROJECTED`` is the only decision on
# which the adapter built a committed Stage 30.11.13 revalidation request from the
# fact; every ``REJECTED_*`` decision is a fail-closed Layer-1 presence / shape /
# positivity rejection that NEVER reaches the composer. NONE of these is a Layer-2
# composer reason -- freshness / ATH / tier / gate stay the committed composer's
# authoritative reasons (surfaced VERBATIM in the embedded session result), so the
# adapter never re-implements the freshness clock here. Mirrored BY VALUE by the
# Stage 30.11 manifest.


PROJECTION_DECISION_PROJECTED: str = "PROJECTED"
PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD: str = (
    "REJECTED_NOT_A_FACTS_RECORD"
)
PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT: str = (
    "REJECTED_MISSING_TOKEN_MINT"
)
PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT: str = (
    "REJECTED_INVALID_TOKEN_MINT"
)
PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID: str = (
    "REJECTED_MISSING_CANDIDATE_ID"
)
PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID: str = (
    "REJECTED_INVALID_CANDIDATE_ID"
)
PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED: str = (
    "REJECTED_MIGRATION_NOT_CONFIRMED"
)
PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC: str = (
    "REJECTED_MISSING_MIGRATION_TIME_UTC"
)
PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC: str = (
    "REJECTED_INVALID_MIGRATION_TIME_UTC"
)
PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT: str = (
    "REJECTED_MISSING_CREATED_AT"
)
PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT: str = (
    "REJECTED_INVALID_CREATED_AT"
)
PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT: str = (
    "REJECTED_MARKET_CONTEXT_NOT_PRESENT"
)
PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP: str = (
    "REJECTED_MISSING_MARKET_CAP"
)
PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP: str = (
    "REJECTED_INVALID_MARKET_CAP"
)
PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE: str = (
    "REJECTED_MISSING_CURRENT_PRICE"
)
PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE: str = (
    "REJECTED_INVALID_CURRENT_PRICE"
)
PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD: str = (
    "REJECTED_MISSING_LIQUIDITY_USD"
)
PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD: str = (
    "REJECTED_INVALID_LIQUIDITY_USD"
)
PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT: str = (
    "REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT"
)
PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT: str = (
    "REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT"
)


STAGE30_11_18_PROJECTION_DECISIONS: Tuple[str, ...] = (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD,
    PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT,
    PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT,
    PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID,
    PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID,
    PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED,
    PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC,
    PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC,
    PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT,
    PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT,
    PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT,
    PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP,
    PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP,
    PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE,
    PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE,
    PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD,
    PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD,
    PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT,
    PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT,
)


def is_projection_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Layer-1 projection decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_18_PROJECTION_DECISIONS


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------
#
# The adapter self-scans its own projection-event string fields and combines the
# verdict with the embedded session result's redaction status: ``REDACTED`` when
# every field is safe (the normal path -- the adapter builds only closed-set tokens
# + safe-echo ids) AND the session result is redacted, else ``REDACTION_VIOLATION``.
# A fact id that is not a safe-echo token is replaced by ``REDACTED_UNSAFE_ID``
# rather than echoed raw, so a forged id can never smuggle injected text into the
# report.


STAGE30_11_18_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_18_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_18_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_18_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_18_REDACTION_STATUS_REDACTED,
    STAGE30_11_18_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.17 / 30.11.16 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint and an underscore
    candidate id both pass; any newline / control char / whitespace / path / url /
    quote character (or an over-long value) fails. It gates the fact ids the
    adapter echoes into its redaction-safe projection events -- an unsafe value is
    replaced by ``STAGE30_11_18_REDACTED_UNSAFE_ID`` rather than echoed raw.
    Mirrors the Stage 30.11.17 ``is_safe_echo_id`` BY VALUE. Pure / total; never
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
# Immutable model: one harvested-candidate facts record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_18HarvestedCandidateFacts:
    """Immutable flat carrier of ONE harvested + enriched candidate's facts.

    Carries the SAME 13 revalidated inputs the committed Stage 30.11.13 composer
    consumes, so the adapter maps it near 1:1 into a committed revalidation
    request. Carries ONLY safe scalars (decimal-text magnitudes, ISO-8601 UTC
    timestamps, opaque ids, display tokens); no secret, no raw provider payload,
    no host, no transport destination. A ceremony / enricher produces it from a
    real harvest source; this slice never harvests.

    The REQUIRED fields (a missing / malformed value yields a fail-closed Layer-1
    ``REJECTED_*`` at the adapter, never a crash):

      * ``token_mint`` / ``candidate_id``  -- safe-shape identity.
      * ``migration_time_utc``             -- the confirmed migration anchor
                                              (ISO-8601 UTC).
      * ``current_price`` /
        ``current_market_cap_usd`` /
        ``liquidity_usd``                  -- decimal text, strictly positive to
                                              project. ``liquidity_usd`` is
                                              REQUIRED here even though the request
                                              types it optional -- the composer
                                              fails closed without it.
      * ``market_context_status``          -- must be ``PRESENT`` to project.
      * ``market_context_fetched_at_utc``  -- ISO-8601 UTC time the market context
                                              was fetched (the adapter checks
                                              presence + shape ONLY; the committed
                                              composer owns the freshness clock).
      * ``created_at_utc``                 -- caller-injected ISO-8601 UTC.

    The OPTIONAL fields (absent -> no rejection; carried through to the request):

      * ``migration_confirmed`` -- ``True`` for a confirmed migration; a non-``True``
                                   value yields ``REJECTED_MIGRATION_NOT_CONFIRMED``.
      * ``symbol_or_name``      -- optional display symbol.
      * ``migration_source``    -- optional opaque migration provenance ref.
      * ``age_display``         -- optional age display string.
    """

    token_mint: str
    candidate_id: str
    migration_time_utc: str
    current_price: str
    current_market_cap_usd: str
    liquidity_usd: str
    market_context_status: str
    market_context_fetched_at_utc: str
    created_at_utc: str
    migration_confirmed: bool = True
    symbol_or_name: Optional[str] = None
    migration_source: Optional[str] = None
    age_display: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable model: one per-fact Layer-1 projection event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_18ProjectionEvent:
    """Immutable redaction-safe per-fact Layer-1 projection event.

    The adapter emits exactly one of these per harvested fact it scanned. It
    echoes the safe-shape identity and pins the closed-set Layer-1 ``decision``;
    it carries ONLY safe scalars + a closed-set token: NO magnitude, NO body, NO
    url, NO exception text, NO secret.

      * ``index``        -- the zero-based position in the scanned order.
      * ``decision``     -- one of ``STAGE30_11_18_PROJECTION_DECISIONS``.
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
# Immutable model: rolled-up session report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_18SessionReport:
    """Immutable rolled-up Stage 30.11.18 harvested-facts session report.

    A passive summary of one bounded run. It carries the ordered per-fact Layer-1
    projection events, the non-negative Layer-1 counts, the EMBEDDED Stage 30.11.17
    session result (the Layer-2 outcome -- dispatched / rejected / dedupe-blocked /
    errors, the would-send tally, the stop reason, and the mirrored composer
    reasons), the combined redaction status, and a caller-injected timestamp.
    Carries ONLY safe scalars + the embedded redaction-safe records; no secret, no
    body, no url, no transport destination.

      * ``projection_events``   -- the ordered per-fact Layer-1 events (one per
                                   scanned fact).
      * ``facts_seen``          -- facts pulled + scanned (<= the candidate cap).
      * ``projected``           -- facts that built a request (``PROJECTED``).
      * ``rejected_projection`` -- facts rejected at Layer-1 (``facts_seen`` minus
                                   ``projected``).
      * ``session_result``      -- the embedded Stage 30.11.17 session result over
                                   the projected entries (duck-typed ``Any``).
      * ``redaction_status``    -- one of ``STAGE30_11_18_REDACTION_STATUSES``
                                   (``REDACTED`` iff the projection events AND the
                                   embedded session result are both redacted).
      * ``created_at_utc``      -- caller-injected ISO-8601 UTC timestamp.
    """

    projection_events: Tuple[Stage30_11_18ProjectionEvent, ...]
    facts_seen: int
    projected: int
    rejected_projection: int
    session_result: Any
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def harvested_facts_field_names() -> Tuple[str, ...]:
    """Return the harvested-candidate facts field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_18HarvestedCandidateFacts))


def projection_event_field_names() -> Tuple[str, ...]:
    """Return the projection event field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_18ProjectionEvent))


def session_report_field_names() -> Tuple[str, ...]:
    """Return the session report field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_18SessionReport))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_18_MINOR_VERSION",
    "STAGE30_11_18_REPORT_SCHEMA_VERSION",
    "STAGE30_11_18_SOURCE_STAGE",
    # Layer-1 projection decisions.
    "PROJECTION_DECISION_PROJECTED",
    "PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD",
    "PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT",
    "PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT",
    "PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID",
    "PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID",
    "PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED",
    "PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC",
    "PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC",
    "PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT",
    "PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT",
    "PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT",
    "PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP",
    "PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP",
    "PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE",
    "PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE",
    "PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD",
    "PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD",
    "PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT",
    "PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT",
    "STAGE30_11_18_PROJECTION_DECISIONS",
    "is_projection_decision",
    # Redaction.
    "STAGE30_11_18_REDACTION_STATUS_REDACTED",
    "STAGE30_11_18_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_18_REDACTED_UNSAFE_ID",
    "STAGE30_11_18_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_18HarvestedCandidateFacts",
    "Stage30_11_18ProjectionEvent",
    "Stage30_11_18SessionReport",
    # Field-name helpers.
    "harvested_facts_field_names",
    "projection_event_field_names",
    "session_report_field_names",
)
