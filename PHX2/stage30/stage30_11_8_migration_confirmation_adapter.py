"""Stage 30.11.8 narrow migration-confirmation adapter.

The pure, offline CONFIRMATION ADAPTER that fixes the narrowest blocker the
controlled live ceremony retry surfaced: the committed Stage 30.11.7 enrichment
adapter fails a real harvested candidate CLOSED at the MIGRATION dimension
(``UNCONFIRMED_MIGRATION``) because the only committed live migration source
returns an UNKNOWN snapshot for every mint, so nothing committed produces a
``confirmed is True`` result for the Stage 30.11.7 ``migration_resolver`` seam.
This adapter answers exactly one question for one candidate / token mint --

    given a harvested / flat base candidate (a flat MAPPING / dict OR an
    attribute-bearing object carrying the candidate ``token_mint``)
      + an INJECTED, offline / fake-first per-mint migration EVIDENCE SOURCE
      -> read the base's ``token_mint`` (a blank / missing mint fails closed)
      -> look up THAT mint's sanitized migration evidence (a missing / raising /
         non-callable source fails closed; a wrong-mint evidence is never inherited)
      -> map the bound evidence onto a CONFIRMED verdict ONLY when it is
         redaction-safe, an on-chain ``COMPLETE`` reading, not stale, with a valid
         ISO-8601 UTC migration anchor; every other reading fails closed with a
         PRECISE reason (never collapsed into a silent unknown, never fabricated)
      -> a ``Stage30_11_8MigrationResolution`` whose ``confirmed`` the committed
         Stage 30.11.7 adapter reads to clear (or keep failing) the MIGRATION
         dimension

The adapter ONLY confirms a migration; it NEVER runs the Stage 30.11.7 enrichment /
the Stage 30.11.6 projection / the Stage 30.11.5 runner / the Stage 30.9.3 dip gate
/ a transport, NEVER decides dip eligibility, NEVER fabricates evidence (a missing /
mismatched / unsafe / unknown / partial / contradictory / invalid / stale /
mis-anchored reading each fails closed and can NEVER become ``confirmed``), NEVER
reserves a dispatch, NEVER calls a transport, and NEVER sends Discord. It composes
into the Stage 30.11.7 ``migration_resolver`` seam via :func:`build_migration_resolver`,
which returns a duck-typed callable the committed Stage 30.11.7 adapter consumes
exactly as it consumes its own injected fake migration resolver -- so a candidate
that previously died at ``UNCONFIRMED_MIGRATION`` clears the MIGRATION dimension
when (and only when) real evidence confirms it, while the ATH / drawdown dimension
the Stage 30.11.7 adapter checks LATER still independently blocks transport.

The adapter NEVER fetches migration data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (every timestamp is
caller-injected / evidence-carried), and edits NO Stage 27 / Stage 28 / Stage 29 /
Stage 30.3 / Stage 30.4 / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 production
file. It composes ONLY the Stage 30.11.8 confirmation-models sibling plus the
INJECTED evidence source; nothing more. In THIS slice the injected evidence source
is ALWAYS a FAKE -- the real Stage 29.5 side-channel / Stage 30.5 bridge plugs in at
the source seam via out-of-repo, operator-authorized wrappers.

Discipline:

  * Stdlib only (``re`` / ``typing``). ``re`` provides the safe-SHAPE ISO-8601 UTC
    migration-anchor check, derived from the committed Stage 30.5
    ``is_safe_iso8601_utc`` pattern but TIGHTENED for a confirmation: UTC ``Z`` only
    (NOT the ``+00:00`` offset form -- a confirmation is a stronger claim than the
    Stage 30.5 display gate) AND a pure manual calendar check that rejects a
    shape-valid but IMPOSSIBLE instant (month 00 / 13, day 30-Feb, hour 24, minute /
    leap-second 60, ...). A shape match alone never confirms. The pattern text is a
    module-level string literal compiled lazily inside the helper, never at import
    time (so no top-level Call node); the calendar check is pure arithmetic (NO
    ``datetime`` import -- every clock stays caller-injected).
  * Imports ONLY the Stage 30.11.8 confirmation-models sibling. No other PHX2
    module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / transport / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7
    import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected / evidence-carried.
"""

from __future__ import annotations

import re
from typing import Callable

from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_DECISION_CONFIRMED,
    CONFIRM_DECISION_UNCONFIRMED,
    CONFIRM_REASON_BLANK_CANDIDATE_MINT,
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
    CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE,
    CONFIRM_REASON_EVIDENCE_MINT_MISMATCH,
    CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION,
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
    CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE,
    CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE,
    CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED,
    CONFIRM_REASON_REDACTION_UNSAFE,
    CONFIRM_REASON_STALE_MIGRATION_EVIDENCE,
    CONFIRM_REASON_UNKNOWN_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE30_11_8_MIGRATION_WARNING_STALE,
    STAGE30_11_8_REDACTION_STATUS_SAFE,
    Stage30_11_8MigrationResolution,
    is_nonblank_str,
)


# ---------------------------------------------------------------------------
# Injected evidence-source boundary type (duck-typed; a FAKE in this slice)
# ---------------------------------------------------------------------------
#
# The injected evidence source is an object exposing a single method --
# ``lookup_migration_evidence(token_mint) -> object | None`` -- that returns the
# sanitized migration evidence bound to that mint (or ``None`` -> no evidence). The
# adapter reads the returned evidence duck-typed (via attribute access), so a real
# out-of-repo source may return any object carrying the documented evidence
# attributes; a missing attribute reads as the fail-closed value, and a raising /
# non-callable source fails closed to a missing signal. In THIS slice the source is
# ALWAYS a FAKE; the real Stage 29.5 side-channel / Stage 30.5 bridge plugs in at
# the operator-authorized ceremony.
Stage30_11_8MigrationEvidenceSource = object
Stage30_11_8MigrationResolver = Callable[[object], Stage30_11_8MigrationResolution]


# The safe-SHAPE ISO-8601 UTC migration-anchor pattern. The shape derives from the
# committed Stage 30.5 ``_ISO8601_UTC_PATTERN`` (this module imports no Stage 30.5
# module) but is TIGHTENED for a confirmation: it accepts UTC ``Z`` ONLY (NOT the
# ``+00:00`` offset form -- a confirmation is a stronger claim than the Stage 30.5
# display gate), and it CAPTURES the calendar / time components (year, month, day,
# hour, minute, second) so the semantic check below can reject a shape-valid but
# IMPOSSIBLE instant. A shape match alone never confirms. It is a plain module-level
# STRING literal (not a compiled pattern), so there is no top-level Call node; it is
# compiled lazily inside the helper below.
_ISO8601_UTC_PATTERN_TEXT: str = (
    r"\A(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
    r"(?:\.\d{1,9})?"
    r"Z\Z"
)


# ---------------------------------------------------------------------------
# Pure field readers / validators
# ---------------------------------------------------------------------------


def _read_field(source: object, key: str) -> object:
    """Read field ``key`` from ``source``.

    Pure / total; never raises. ``source`` may be a flat MAPPING (read via
    ``.get``) or any attribute-bearing object (read via ``getattr``). A missing
    key / attribute (or a non-mapping / non-object) yields ``None``. Mirrors the
    Stage 30.11.7 ``_read_field`` discipline BY VALUE.
    """
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _is_leap_year(year: int) -> bool:
    """Return ``True`` iff ``year`` is a Gregorian leap year. Pure / total."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in ``month`` (1-based, assumed already range-checked
    to 1..12) of ``year``; February gains a 29th day in a leap year. Pure / total.
    """
    if month == 2:
        return 29 if _is_leap_year(year) else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def _is_valid_iso8601_utc(value: object) -> bool:
    """Return ``True`` iff ``value`` is a strict-shape AND semantically valid
    ISO-8601 UTC migration anchor.

    Pure / total; never raises. Fails closed to ``False`` for a non-string, an empty
    / whitespace-padded string, a wrong-shape string (a naive timestamp, a ``+00:00``
    / non-UTC offset, a single-digit field), OR -- the gap the regex-only check left
    open -- a shape-valid string naming an IMPOSSIBLE calendar instant (month 00 / 13
    / 99, day 00 / 30-Feb / 99, hour 24 / 99, minute 60 / 99, leap-second 60 / 99).
    So a migration can NEVER be confirmed from a string that merely matches the anchor
    SHAPE; the captured year / month / day / hour / minute / second must form a real
    UTC calendar instant.

    The shape check (UTC ``Z`` only) is compiled lazily here (no top-level Call); the
    calendar check is pure arithmetic with NO ``datetime`` import (every clock stays
    caller-injected). ``int`` parsing cannot raise -- each captured group is a
    guaranteed all-digit run -- so there is no parser exception to fail open on.
    """
    if not isinstance(value, str):
        return False
    match = re.fullmatch(_ISO8601_UTC_PATTERN_TEXT, value)
    if match is None:
        return False
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))
    second = int(match.group(6))
    if not 1 <= month <= 12:
        return False
    if not 0 <= hour <= 23:
        return False
    if not 0 <= minute <= 59:
        return False
    if not 0 <= second <= 59:  # reject leap seconds (60) for now
        return False
    return 1 <= day <= _days_in_month(year, month)


def _stale_in_warnings(warnings: object) -> bool:
    """Return ``True`` iff the ``MIGRATION_STALE`` warning token is present in a
    tuple / list / set / frozenset of warning codes.

    A non-collection input (including a bare ``str``, to avoid character-iteration)
    returns ``False``. Pure / total; never raises. Mirrors the Stage 30.5.3
    ``_stale_in_warnings`` discipline BY VALUE.
    """
    if isinstance(warnings, (tuple, list, set, frozenset)):
        return STAGE30_11_8_MIGRATION_WARNING_STALE in warnings
    return False


def _safe_lookup(evidence_source: object, token_mint: str) -> object:
    """Call ``evidence_source.lookup_migration_evidence(token_mint)`` inside a
    fail-closed guard; return its result, or ``None`` if the source is ``None`` /
    has no callable lookup / raises.

    Pure apart from the injected source's own behavior; never lets a source
    exception escape (``KeyboardInterrupt`` / ``SystemExit`` -- ``BaseException`` --
    are NOT swallowed). A ``None`` / non-conforming / raising source yields ``None``
    -- a missing signal the confirmation then fails closed on. Mirrors the Stage
    30.11.7 ``_safe_resolve`` discipline BY VALUE.
    """
    lookup = getattr(evidence_source, "lookup_migration_evidence", None)
    if not callable(lookup):
        return None
    try:
        return lookup(token_mint)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _unconfirmed(
    *, reason: str, token_mint: str
) -> Stage30_11_8MigrationResolution:
    """Build a fail-closed (``confirmed=False``) resolution carrying a precise
    reason and the echoed candidate mint -- NO migration anchor, NO provenance ref.
    Pure; no I/O.
    """
    return Stage30_11_8MigrationResolution(
        confirmed=False,
        decision=CONFIRM_DECISION_UNCONFIRMED,
        reason=reason,
        token_mint=token_mint,
        migration_event_time_utc=None,
        source_ref=None,
    )


def _confirmed(
    *, token_mint: str, migration_event_time_utc: str, source_ref: object
) -> Stage30_11_8MigrationResolution:
    """Build a confirmed (``confirmed=True``) resolution carrying the bound
    migration anchor + provenance ref (a non-string ``source_ref`` becomes
    ``None``). Pure; no I/O. Built ONLY when every confirmation check cleared.
    """
    safe_ref = source_ref if isinstance(source_ref, str) else None
    return Stage30_11_8MigrationResolution(
        confirmed=True,
        decision=CONFIRM_DECISION_CONFIRMED,
        reason=CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
        token_mint=token_mint,
        migration_event_time_utc=migration_event_time_utc,
        source_ref=safe_ref,
    )


# The fail-closed measurement-status -> reason map (every recognized non-confirming
# status maps to its OWN precise reason; an unrecognized / missing status falls
# through to ``UNKNOWN_MIGRATION``). A contradictory / invalid reading is NEVER
# collapsed into a silent unknown.
_MEASUREMENT_STATUS_FAIL_REASON = {
    STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: (
        CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED
    ),
    STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION: (
        CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION
    ),
    STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION: (
        CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE
    ),
    STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION: (
        CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE
    ),
}


# ---------------------------------------------------------------------------
# Public confirmation adapter (per candidate)
# ---------------------------------------------------------------------------


def resolve_candidate_migration(
    base: object, evidence_source: object
) -> Stage30_11_8MigrationResolution:
    """Resolve ONE candidate's migration verdict against the injected evidence
    source, returning a ``Stage30_11_8MigrationResolution``.

    Pure / deterministic apart from the injected source's own behavior / total /
    no I/O, no provider call, no Discord send, no env read, no wall-clock read.
    Never raises for a malformed base / source -- a non-mapping / non-object base,
    a ``None`` / raising / non-conforming source, or a malformed evidence all fail
    closed to an ``UNCONFIRMED_MIGRATION`` resolution. ALWAYS returns a resolution
    (never ``None``), so the confirmation outcome is total and talliable.

    Confirmation precedence (top-down, FIRST failing check wins):

      1. CANDIDATE MINT -- the base must carry a non-blank ``token_mint``. A blank /
         missing mint -> ``BLANK_CANDIDATE_MINT``.
      2. EVIDENCE PRESENCE -- the source must return evidence for THAT mint. A
         missing / raising / non-conforming source (or no evidence) ->
         ``MISSING_MIGRATION_EVIDENCE``.
      3. MINT BINDING -- the evidence must be bound to the SAME mint (its
         ``token_mint`` must be non-blank AND equal the base mint). A mismatched /
         blank evidence mint -> ``EVIDENCE_MINT_MISMATCH`` (no cross-mint
         inheritance).
      4. REDACTION -- the evidence must be redaction-safe (``redaction_status ==
         SAFE``). A missing / non-SAFE redaction -> ``REDACTION_UNSAFE``.
      5. MEASUREMENT STATUS -- the evidence must report ``COMPLETE`` (an on-chain
         migration). A ``PARTIAL_MIGRATION_PRESENT`` / ``MISSING_MIGRATION`` /
         ``CONFLICTING_MIGRATION`` / ``INVALID_MIGRATION`` reading maps to its OWN
         precise reason; an unrecognized / missing status -> ``UNKNOWN_MIGRATION``.
      6. FRESHNESS -- a ``COMPLETE`` reading carrying a ``MIGRATION_STALE`` warning
         -> ``STALE_MIGRATION_EVIDENCE``.
      7. ANCHOR -- the ``COMPLETE`` reading must carry a strict-shape AND
         semantically valid ISO-8601 UTC ``migration_event_time_utc`` (UTC ``Z``
         only; the captured calendar / time fields must form a REAL instant). A
         missing / malformed / impossible anchor (e.g. month 13, day 30-Feb, hour
         24, a ``+00:00`` offset, a naive timestamp) -> ``INVALID_MIGRATION_ANCHOR``.
      8. otherwise -> ``CONFIRMED_MIGRATION`` / ``CONFIRMED_ON_CHAIN_EVENT`` with the
         bound anchor + carried provenance ref.

    The confirmation fabricates nothing: ``confirmed`` is ``True`` ONLY when every
    check cleared; the migration anchor + provenance ref are carried ONLY onto a
    confirmed resolution. Candidate identity (the echoed ``token_mint``) is
    preserved on every resolution.
    """
    # ---- 1. Candidate mint: a non-blank token, else fail closed ----
    base_mint = _read_field(base, "token_mint")
    if not is_nonblank_str(base_mint):
        return _unconfirmed(
            reason=CONFIRM_REASON_BLANK_CANDIDATE_MINT, token_mint=""
        )
    # ``base_mint`` is a non-blank str past this guard.
    candidate_mint: str = base_mint  # type: ignore[assignment]

    # ---- 2. Evidence presence: the source must answer for THIS mint ----
    evidence = _safe_lookup(evidence_source, candidate_mint)
    if evidence is None:
        return _unconfirmed(
            reason=CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE,
            token_mint=candidate_mint,
        )

    # ---- 3. Mint binding: the evidence must be bound to the SAME mint ----
    evidence_mint = _read_field(evidence, "token_mint")
    if not is_nonblank_str(evidence_mint) or evidence_mint != candidate_mint:
        return _unconfirmed(
            reason=CONFIRM_REASON_EVIDENCE_MINT_MISMATCH,
            token_mint=candidate_mint,
        )

    # ---- 4. Redaction: the evidence must be redaction-safe ----
    redaction_status = _read_field(evidence, "redaction_status")
    if redaction_status != STAGE30_11_8_REDACTION_STATUS_SAFE:
        return _unconfirmed(
            reason=CONFIRM_REASON_REDACTION_UNSAFE, token_mint=candidate_mint
        )

    # ---- 5. Measurement status: ONLY an on-chain COMPLETE can confirm ----
    measurement_status = _read_field(evidence, "measurement_status")
    if measurement_status != STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE:
        reason = _MEASUREMENT_STATUS_FAIL_REASON.get(
            measurement_status, CONFIRM_REASON_UNKNOWN_MIGRATION
        )
        return _unconfirmed(reason=reason, token_mint=candidate_mint)

    # ---- 6. Freshness: a stale COMPLETE reading fails closed ----
    if _stale_in_warnings(_read_field(evidence, "warnings")):
        return _unconfirmed(
            reason=CONFIRM_REASON_STALE_MIGRATION_EVIDENCE,
            token_mint=candidate_mint,
        )

    # ---- 7. Anchor: the COMPLETE reading must carry a valid UTC anchor ----
    anchor = _read_field(evidence, "migration_event_time_utc")
    if not _is_valid_iso8601_utc(anchor):
        return _unconfirmed(
            reason=CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
            token_mint=candidate_mint,
        )
    # ``anchor`` is a valid ISO-8601 UTC string past this guard.
    confirmed_anchor: str = anchor  # type: ignore[assignment]

    # ---- 8. Confirmed: bind the anchor + carry provenance ----
    return _confirmed(
        token_mint=candidate_mint,
        migration_event_time_utc=confirmed_anchor,
        source_ref=_read_field(evidence, "source_ref"),
    )


# ---------------------------------------------------------------------------
# Public resolver factory (the drop-in for the Stage 30.11.7 migration seam)
# ---------------------------------------------------------------------------


def build_migration_resolver(
    evidence_source: object,
) -> Stage30_11_8MigrationResolver:
    """Build a duck-typed migration resolver over the injected evidence source.

    The returned callable is the drop-in object the committed Stage 30.11.7
    enrichment adapter's ``migration_resolver`` seam consumes: given a base
    candidate it returns a ``Stage30_11_8MigrationResolution`` whose ``confirmed``
    the Stage 30.11.7 adapter reads (requiring ``confirmed is True`` to clear the
    MIGRATION dimension). The closure holds the evidence source and looks up each
    base candidate's OWN ``token_mint`` -- so no candidate inherits another mint's
    migration evidence.

    Pure apart from the injected source's behavior; reserves no dispatch, calls no
    transport, sends no Discord, writes no file, reads no env / clock / network, and
    NEVER constructs a runner / transport / dispatch sink -- so it can never reach a
    send surface. Producing a confirmed verdict is never a bypass of the committed
    Stage 30.11.7 enrichment / Stage 30.11.6 projection / Stage 30.11.5 runner /
    Stage 30.9.3 dip gate; the Stage 30.11.7 adapter still checks the ATH / drawdown
    dimension LATER, so a confirmed migration alone never reaches transport.
    """

    def _resolver(base: object) -> Stage30_11_8MigrationResolution:
        return resolve_candidate_migration(base, evidence_source)

    return _resolver


__all__ = (
    "Stage30_11_8MigrationEvidenceSource",
    "Stage30_11_8MigrationResolver",
    "resolve_candidate_migration",
    "build_migration_resolver",
)
