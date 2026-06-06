"""Stage 30.11.10 real ATH-resolver bridge models.

Stage 30.11.10 ships the passive, pure, stdlib-only MODEL layer for the narrowest
remaining blocker the ATH blocker audit surfaced: the committed Stage 30.11.7
enrichment adapter checks an ATH dimension LAST (after market context / tier /
migration), requiring its injected ``ath_resolver`` to return a resolution that is
``present`` + ``fresh`` + ``post_migration_ath_verified`` with a finite
``drawdown_from_ath`` -- but NOTHING committed maps the real post-migration drawdown
brain (the committed Stage 27.4 ``read_ath_context`` / ``_compute_drawdown`` /
``AthContextRecord``, fed by the committed Stage 29.2 Birdeye ATH + current-price
sources) into that exact resolver shape. Only a FAKE ATH resolver currently produces
it, so a real harvested candidate that clears MIGRATION still dies at the ATH
dimension. Stage 30.11.10 adds the narrow real ATH-resolver BRIDGE that maps an
already-committed ``AthContextRecord``-shaped reading onto the Stage 30.11.7 ATH
resolver contract -- failing closed (never fabricating) on every missing migration
anchor / missing or unavailable ATH source / stale / source-error / pre-migration /
missing-or-malformed-drawdown / wrong-mint reading.

This module is the MODEL layer ONLY. It implements NO resolver adapter (that is
``stage30_11_10_ath_resolver_adapter``), drives NO ATH source, recomputes NO
drawdown (the committed Stage 27.4 ``_compute_drawdown`` owns that; this slice reads
the committed ``drawdown_from_ath`` VERBATIM), runs NO enrichment / bridge / dip gate
/ runner, calls NO transport / dispatch, wires into NO runtime, makes NO live
provider call, sends NO live message, reads NO process environment, opens NO network
connection, opens NO database, writes NO file, reserves NO dispatch, reads NO wall
clock (``created_at_utc`` is caller-injected), and edits NO Stage 27 / Stage 28 /
Stage 29 / Stage 30.3 / Stage 30.4 / Stage 30.7 / Stage 30.11.5 / Stage 30.11.6 /
Stage 30.11.7 / Stage 30.11.8 / Stage 30.11.9 production file. Stage 30.11.10 is fake
/ offline only: the real controlled live ceremony remains a SEPARATE, explicitly
operator-authorized step this slice does not build.

The slice owns one closed-set vocabulary:

  * the per-candidate ATH resolver DECISION / REASON -- the resolver adapter emits
    exactly one of ``RESOLVED_ATH`` (the reading is for THIS mint, ATH ``PRESENT``,
    post-migration-verified -- window ``POST_MIGRATION_ONLY`` AND drawdown basis
    ``FROM_POST_MIGRATION_ATH``, both required -- with a drawdown value to hand off;
    reason ``RESOLVED_POST_MIGRATION_ATH``), or
    ``UNRESOLVED_ATH`` for the FIRST failing check (a blank candidate mint ->
    ``BLANK_CANDIDATE_MINT``; no confirmed migration anchor ->
    ``MISSING_MIGRATION_ANCHOR``; a non-callable / absent ATH source ->
    ``MISSING_ATH_SOURCE``; a raising ATH source -> ``ATH_SOURCE_ERROR``; an ATH
    source that returns nothing for the mint -> ``ATH_SOURCE_UNAVAILABLE``; a reading
    bound to a DIFFERENT mint -> ``ATH_MINT_MISMATCH``; an ATH that is not
    ``PRESENT`` -- stale / unavailable / source-error / not-applicable /
    unsupported -- -> ``ATH_NOT_PRESENT``; an ATH not verified post-migration ->
    ``PRE_MIGRATION_ATH_NOT_VERIFIED``; a present + post-migration ATH carrying no
    drawdown -> ``MISSING_DRAWDOWN``).

The resolution's ``present`` / ``fresh`` / ``post_migration_ath_verified`` /
``drawdown_from_ath`` / ``source_ref`` field NAMES equal the Stage 30.11.7 ATH
resolver result fields (``Stage30_11_7AthResolution``) BY VALUE, so the committed
Stage 30.11.7 enrichment adapter reads a Stage 30.11.10 resolution via attribute
access EXACTLY as it reads its own injected fake ATH resolution -- no Stage 30.11.7
import is needed (and is in fact forbidden: importing the Stage 30.11.7 slice would
break the committed Stage 30.11.7 leaf boundary test, so Stage 30.11.10 stays a clean
leaf and mirrors the shape BY VALUE, exactly as the Stage 30.11.8 slice mirrors the
Stage 29.5 measurement-status tokens BY VALUE and the Stage 30.11.9 slice mirrors the
Stage 30.11.8 evidence field names BY VALUE). The committed Stage 27.4
``AthContextRecord`` tokens the resolver consults (``ath_status == PRESENT``,
``drawdown_basis == FROM_POST_MIGRATION_ATH``) are likewise mirrored BY VALUE.

The bridge FABRICATES nothing: ``present`` / ``fresh`` are set ONLY when the committed
reading's ``ath_status`` is ``PRESENT``; ``post_migration_ath_verified`` is set ONLY
when the committed reading's ``ath_since_migration_status`` is ``POST_MIGRATION_ONLY``
AND its ``drawdown_basis`` is ``FROM_POST_MIGRATION_ATH`` (the committed Stage 27.4
brain couples both ONLY for a post-migration-only ATH whose drawdown was computed
against the current price -- a duck-typed reading can decouple them, so the resolver
requires both and requires the window status outright); and ``drawdown_from_ath`` is
carried VERBATIM from the committed reading (NEVER recomputed). A missing / stale /
pre-migration / window-inconsistent / malformed reading can NEVER become a resolved
ATH.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``). NO ``decimal`` (the slice never
    coerces / recomputes the drawdown -- it carries the committed
    ``drawdown_from_ath`` VERBATIM and the committed Stage 30.11.7 enrichment coerces
    it). NO ``re``, NO ``time`` / ``datetime`` (every clock is injected, never read).
  * Imports NO PHX2 module. The Stage 30.11.7 ATH resolver result field names + the
    Stage 27.4 ``AthContextRecord`` tokens are mirrored BY VALUE; the slice imports
    NO Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate record) /
    Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live runner /
    provider / transport / Stage 30.7 display bridge / Stage 30.11.5 / Stage 30.11.6
    / Stage 30.11.7 / Stage 30.11.8 / Stage 30.11.9 module.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; ``created_at_utc`` is
    caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + ATH-resolver schema identity
# ---------------------------------------------------------------------------


STAGE30_11_10_MINOR_VERSION: str = "30.11.10"


# The Stage 30.11.10 real ATH-resolver bridge schema version. Names the ATH context
# record / resolution / summary / run-result shapes; distinct from the Stage 30.11.9
# evidence-source schema version and every earlier Stage 30.11 schema version.
# Mirrored BY VALUE by the Stage 30.11 manifest section; this module imports no Stage
# 30.11 manifest.
STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION: str = (
    "stage30_11_10_v0_ath_resolver"
)


# The safe-shape source-stage provenance token the ATH resolver stamps onto its proof
# tally (provenance only; names the slice that produced the resolution, never a
# secret / host / transport destination).
STAGE30_11_10_SOURCE_STAGE: str = "30.11.10"


# ---------------------------------------------------------------------------
# Stage 27.4 ATH vocabulary (mirrored BY VALUE; NOT imported)
# ---------------------------------------------------------------------------
#
# These mirror the committed Stage 27.4 ``price_ath_context_models`` ``ATH_STATUS`` /
# ``DRAWDOWN_BASIS`` / ``ATH_SINCE_MIGRATION_STATUS`` tokens the committed
# ``read_ath_context`` / ``build_ath_context_record`` stamp onto an
# ``AthContextRecord``. They are duplicated here as plain Stage-30.11.10-owned string
# literals precisely to preserve the no-Stage-27-import boundary: the resolver
# recognizes the Stage 27.4 SHAPE without importing any Stage 27 module. ``PRESENT``
# is the ONLY ``ath_status`` a resolved ATH may carry; ``FROM_POST_MIGRATION_ATH`` is
# the ONLY ``drawdown_basis`` a post-migration-verified ATH may carry (the committed
# Stage 27.4 brain sets it ONLY for a post-migration-only ATH whose drawdown was
# computed against the current price). Every other token fails closed.


STAGE30_11_10_ATH_STATUS_PRESENT: str = "PRESENT"
STAGE30_11_10_ATH_STATUS_STALE: str = "STALE"
STAGE30_11_10_ATH_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
STAGE30_11_10_ATH_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
STAGE30_11_10_ATH_STATUS_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
STAGE30_11_10_ATH_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"


STAGE30_11_10_RECOGNIZED_ATH_STATUS_VALUES: Tuple[str, ...] = (
    STAGE30_11_10_ATH_STATUS_PRESENT,
    STAGE30_11_10_ATH_STATUS_STALE,
    STAGE30_11_10_ATH_STATUS_UNAVAILABLE,
    STAGE30_11_10_ATH_STATUS_NOT_APPLICABLE,
    STAGE30_11_10_ATH_STATUS_UNSUPPORTED_PAIR,
    STAGE30_11_10_ATH_STATUS_SOURCE_ERROR,
)


# The single ATH status that can yield a present / fresh ATH (Stage 27.4 collapses
# staleness into a DISTINCT ``STALE`` status, so a ``PRESENT`` ATH is, by
# construction, fresh -- the resolver maps both ``present`` and ``fresh`` from this
# one token).
STAGE30_11_10_ATH_PRESENT_STATUS: str = STAGE30_11_10_ATH_STATUS_PRESENT


STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH: str = (
    "FROM_POST_MIGRATION_ATH"
)
STAGE30_11_10_DRAWDOWN_BASIS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
STAGE30_11_10_DRAWDOWN_BASIS_UNKNOWN: str = "UNKNOWN"


STAGE30_11_10_RECOGNIZED_DRAWDOWN_BASIS_VALUES: Tuple[str, ...] = (
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE30_11_10_DRAWDOWN_BASIS_NOT_APPLICABLE,
    STAGE30_11_10_DRAWDOWN_BASIS_UNKNOWN,
)


# The single drawdown basis that proves the ATH is verified post-migration (the
# committed Stage 27.4 brain sets it ONLY inside the post-migration-only branch, AND
# only when the drawdown actually computed -- so it doubles as the post-migration
# verification signal).
STAGE30_11_10_POST_MIGRATION_VERIFIED_DRAWDOWN_BASIS: str = (
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
)


# The committed Stage 27.4 ``ath_since_migration_status`` post-migration-only token,
# mirrored BY VALUE. The committed Stage 27.4 brain sets ``drawdown_basis ==
# FROM_POST_MIGRATION_ATH`` ONLY when ``ath_since_migration_status ==
# POST_MIGRATION_ONLY``, so an HONEST reading carries both -- but a duck-typed /
# injected reading can DECOUPLE them. Because this slice consumes duck-typed records,
# the resolver requires BOTH this token AND the post-migration drawdown basis (and
# requires ``ath_since_migration_status`` OUTRIGHT) before setting
# ``post_migration_ath_verified``; neither signal alone suffices.
STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY: str = (
    "POST_MIGRATION_ONLY"
)
STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION: str = (
    "MAY_INCLUDE_PRE_MIGRATION"
)


# ---------------------------------------------------------------------------
# Closed-set: per-candidate ATH resolver decision
# ---------------------------------------------------------------------------
#
# Exactly one resolver decision per candidate. ``RESOLVED_ATH`` is the only decision
# whose resolution clears the Stage 30.11.7 ATH dimension end-to-end (``present`` +
# ``fresh`` + ``post_migration_ath_verified`` + a non-empty drawdown);
# ``UNRESOLVED_ATH`` carries a resolution that fails the Stage 30.11.7 ATH dimension
# closed. Mirrored BY VALUE by the Stage 30.11 manifest.


ATH_DECISION_RESOLVED: str = "RESOLVED_ATH"
ATH_DECISION_UNRESOLVED: str = "UNRESOLVED_ATH"


STAGE30_11_10_ATH_DECISIONS: Tuple[str, ...] = (
    ATH_DECISION_RESOLVED,
    ATH_DECISION_UNRESOLVED,
)


# The single decision that yields a Stage-30.11.7-clearing resolution.
STAGE30_11_10_ATH_PASS_DECISION: str = ATH_DECISION_RESOLVED


def is_ath_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set ATH resolver decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_10_ATH_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: per-candidate ATH resolver reason
# ---------------------------------------------------------------------------
#
# Exactly one resolver reason per decision. ``RESOLVED_POST_MIGRATION_ATH`` is the
# only reason that accompanies a resolved ATH; every other reason names the FIRST
# failing check's precise fail-closed cause (a missing migration anchor / missing or
# unavailable / erroring ATH source / cross-mint / not-present / pre-migration /
# missing-drawdown reading is NEVER collapsed into a single silent unknown). Mirrored
# BY VALUE by the manifest.


ATH_REASON_RESOLVED_POST_MIGRATION_ATH: str = "RESOLVED_POST_MIGRATION_ATH"
ATH_REASON_BLANK_CANDIDATE_MINT: str = "BLANK_CANDIDATE_MINT"
ATH_REASON_MISSING_MIGRATION_ANCHOR: str = "MISSING_MIGRATION_ANCHOR"
ATH_REASON_MISSING_ATH_SOURCE: str = "MISSING_ATH_SOURCE"
ATH_REASON_ATH_SOURCE_ERROR: str = "ATH_SOURCE_ERROR"
ATH_REASON_ATH_SOURCE_UNAVAILABLE: str = "ATH_SOURCE_UNAVAILABLE"
ATH_REASON_ATH_MINT_MISMATCH: str = "ATH_MINT_MISMATCH"
ATH_REASON_ATH_NOT_PRESENT: str = "ATH_NOT_PRESENT"
ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED: str = (
    "PRE_MIGRATION_ATH_NOT_VERIFIED"
)
ATH_REASON_MISSING_DRAWDOWN: str = "MISSING_DRAWDOWN"


STAGE30_11_10_ATH_REASONS: Tuple[str, ...] = (
    ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
    ATH_REASON_BLANK_CANDIDATE_MINT,
    ATH_REASON_MISSING_MIGRATION_ANCHOR,
    ATH_REASON_MISSING_ATH_SOURCE,
    ATH_REASON_ATH_SOURCE_ERROR,
    ATH_REASON_ATH_SOURCE_UNAVAILABLE,
    ATH_REASON_ATH_MINT_MISMATCH,
    ATH_REASON_ATH_NOT_PRESENT,
    ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ATH_REASON_MISSING_DRAWDOWN,
)


# The single reason that accompanies the only resolved decision.
STAGE30_11_10_ATH_PASS_REASON: str = ATH_REASON_RESOLVED_POST_MIGRATION_ATH


# The fail-closed reasons (every reason except the single resolved reason). No
# fail-closed reason ever accompanies a ``RESOLVED_ATH`` decision.
STAGE30_11_10_ATH_FAIL_CLOSED_REASONS: Tuple[str, ...] = (
    ATH_REASON_BLANK_CANDIDATE_MINT,
    ATH_REASON_MISSING_MIGRATION_ANCHOR,
    ATH_REASON_MISSING_ATH_SOURCE,
    ATH_REASON_ATH_SOURCE_ERROR,
    ATH_REASON_ATH_SOURCE_UNAVAILABLE,
    ATH_REASON_ATH_MINT_MISMATCH,
    ATH_REASON_ATH_NOT_PRESENT,
    ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ATH_REASON_MISSING_DRAWDOWN,
)


def is_ath_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set ATH resolver reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_10_ATH_REASONS


# ---------------------------------------------------------------------------
# Author-verified offline ATH-resolver proof baseline
# ---------------------------------------------------------------------------
#
# The Stage 30.11.10 fake ATH-resolver proof drives a deterministic NINE-base fake
# scenario (one resolved + eight DISTINCT fail-closed readings) through the resolver:
# exactly ONE base resolves; the other eight fail closed on eight DISTINCT reasons (a
# blank mint, a missing migration anchor, an unavailable ATH source, a raising ATH
# source, a cross-mint reading, a not-present ATH, a pre-migration ATH, a present ATH
# with no drawdown) -- proving the resolver never collapses a stale / pre-migration /
# malformed reading into a resolved ATH. Mirrored BY VALUE by the manifest. NONE is a
# secret, a raw payload, a host, or a transport destination.


STAGE30_11_10_EXPECTED_BASES_SEEN: int = 9
STAGE30_11_10_EXPECTED_RESOLVED: int = 1
STAGE30_11_10_EXPECTED_UNRESOLVED: int = 8


# The exact safe-shape identity of the single mint whose committed reading is allowed
# to resolve. No other mint may resolve. The token mint carries the candidate's real
# on-chain identity (the resolver echoes the base mint verbatim onto the resolution).
STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT: str = "mint-resolved"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a usable
    safe-shape token. Pure / total; never raises. Mirrors the Stage 30.11.7 / 30.11.8
    / 30.11.9 non-blank check BY VALUE; the resolver consults it to validate the
    candidate mint, the confirmed migration anchor, and the committed reading's own
    bound mint (so no candidate inherits another mint's ATH).
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable input model: the committed Stage 27.4 ATH context reading
# ---------------------------------------------------------------------------
#
# A Stage-30.11.10-owned record whose field NAMES are a SUBSET of the committed Stage
# 27.4 ``AthContextRecord`` field names BY VALUE -- the exact fields the resolver
# reads. The committed reading is what an out-of-repo operator wrapper returns from
# the committed Stage 27.4 ``read_ath_context`` (fed by the committed Stage 29.2
# Birdeye ATH + current-price sources, with the Stage 30.11.8-confirmed migration
# anchor as the migration record); the resolver reads it duck-typed, so a real Stage
# 27.4 ``AthContextRecord`` is consumed via attribute access EXACTLY as this fake
# record is. Every field defaults to its FAIL-CLOSED value (``None``), so a bare
# reading can NEVER resolve. The carrier deliberately has NO field for a raw provider
# payload, host, or any secret -- so a committed reading can never smuggle a raw
# identifier into the resolution.


@dataclass(frozen=True)
class Stage30_11_10AthContextRecord:
    """Immutable committed-shape Stage 27.4 ATH context reading the resolver maps.

    Carries ONLY the committed Stage 27.4 ``AthContextRecord`` fields the resolver
    consults plus the mint the reading is bound to (so a wrong-mint reading is never
    inherited). The resolver reads ``token_mint`` (to bind / cross-check),
    ``ath_status`` (-> ``present`` / ``fresh``), BOTH ``ath_since_migration_status`` AND
    ``drawdown_basis`` (-> ``post_migration_ath_verified``, which requires
    ``POST_MIGRATION_ONLY`` AND ``FROM_POST_MIGRATION_ATH`` together),
    ``drawdown_from_ath`` (carried VERBATIM), and ``ath_source`` (-> provenance
    ``source_ref``). ``ath_since_migration_status`` is the committed Stage 27.4 window
    classification the committed brain couples with ``drawdown_basis``; the resolver
    requires it outright (a duck-typed reading can decouple the two).

      * ``token_mint``                 -- the mint this reading is FOR (identity
                                         binding; a blank / mismatched mint fails
                                         closed). Defaults to ``None``.
      * ``ath_status``                 -- committed Stage 27.4 ``ATH_STATUS`` token,
                                         read VERBATIM (the resolver requires
                                         ``PRESENT``; it never promotes a STALE /
                                         UNAVAILABLE / SOURCE_ERROR reading).
                                         Defaults to ``None``.
      * ``ath_since_migration_status`` -- committed Stage 27.4
                                         ``ATH_SINCE_MIGRATION_STATUS`` token (the
                                         window classification), read VERBATIM (the
                                         resolver requires ``POST_MIGRATION_ONLY``,
                                         together with the ``FROM_POST_MIGRATION_ATH``
                                         basis, to set ``post_migration_ath_verified``).
                                         Defaults to ``None``.
      * ``drawdown_basis``             -- committed Stage 27.4 ``DRAWDOWN_BASIS``
                                         token, read VERBATIM (the resolver requires
                                         ``FROM_POST_MIGRATION_ATH`` to set
                                         ``post_migration_ath_verified``). Defaults to
                                         ``None``.
      * ``drawdown_from_ath``          -- the committed Stage 27.4 drawdown magnitude
                                         (a canonical decimal-text string), carried
                                         VERBATIM (NEVER recomputed); ``None`` when the
                                         committed brain did not compute it. Defaults
                                         to ``None``.
      * ``ath_source``                 -- short safe-to-display source label, carried
                                         onto the resolution as provenance, or
                                         ``None``. Defaults to ``None``.
    """

    token_mint: Optional[str] = None
    ath_status: Optional[str] = None
    ath_since_migration_status: Optional[str] = None
    drawdown_basis: Optional[str] = None
    drawdown_from_ath: Optional[str] = None
    ath_source: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable output model: the ATH resolver resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_10AthResolution:
    """Immutable per-candidate ATH resolver resolution.

    The resolver adapter emits exactly one of these per candidate. Its ``present`` /
    ``fresh`` / ``post_migration_ath_verified`` / ``drawdown_from_ath`` / ``source_ref``
    field NAMES equal the Stage 30.11.7 ATH resolver result fields
    (``Stage30_11_7AthResolution``) BY VALUE, so the committed Stage 30.11.7 enrichment
    adapter reads it duck-typed: it requires ``present is True`` AND ``fresh is True``
    AND ``post_migration_ath_verified is True`` AND a finite-coercible
    ``drawdown_from_ath`` to clear the ATH dimension. An ``UNRESOLVED_ATH`` resolution
    therefore keeps the candidate failing closed at the ATH dimension. Carries only
    safe scalars (an echoed mint, closed-set decision / reason tokens, the booleans
    the gate reads, the VERBATIM committed drawdown, an optional provenance ref); no
    secret, no raw payload, no host, no transport destination.

      * ``present``                     -- ``True`` ONLY when the committed reading's
                                          ``ath_status`` is ``PRESENT`` (the Stage
                                          30.11.7 first ATH check).
      * ``fresh``                       -- ``True`` ONLY when the committed reading's
                                          ``ath_status`` is ``PRESENT`` (Stage 27.4
                                          collapses staleness into a DISTINCT ``STALE``
                                          status, so a ``PRESENT`` ATH is fresh).
      * ``post_migration_ath_verified`` -- ``True`` ONLY when the committed reading's
                                          ``ath_since_migration_status`` is
                                          ``POST_MIGRATION_ONLY`` AND its
                                          ``drawdown_basis`` is
                                          ``FROM_POST_MIGRATION_ATH`` (BOTH required;
                                          a duck-typed reading can decouple the two
                                          committed Stage 27.4 signals, so the window
                                          status is required outright).
      * ``drawdown_from_ath``           -- the committed Stage 27.4 drawdown magnitude
                                          carried VERBATIM (a canonical decimal-text
                                          string), or ``None`` -- the committed Stage
                                          30.11.7 enrichment coerces / validates it
                                          (NEVER this slice).
      * ``token_mint``                  -- the echoed candidate mint (``""`` when the
                                          base mint is blank / unreadable).
      * ``decision``                    -- one of ``STAGE30_11_10_ATH_DECISIONS``.
      * ``reason``                      -- one of ``STAGE30_11_10_ATH_REASONS`` (the
                                          precise resolved / fail-closed cause).
      * ``source_ref``                  -- the carried provenance ref (the committed
                                          reading's ``ath_source``) on a resolution, or
                                          ``None``.
    """

    present: bool
    fresh: bool
    post_migration_ath_verified: bool
    drawdown_from_ath: object
    token_mint: str
    decision: str
    reason: str
    source_ref: Optional[str]


# ---------------------------------------------------------------------------
# Immutable model: ATH-resolver proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_10AthResolverSummary:
    """Immutable Stage 30.11.10 ATH-resolver proof tally.

    A passive summary of one bounded resolver pass. It proves, by counting, that ONLY
    a for-this-mint, ATH-present, post-migration-verified, drawdown-bearing committed
    reading resolved, and that every other reading failed closed. Carries only
    non-negative integer counts + a caller-injected timestamp.

      * ``bases_seen``     -- candidate bases taken from the bounded scenario.
      * ``resolved``       -- count that yielded a resolved ATH.
      * ``unresolved``     -- count that failed closed.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp.
    """

    bases_seen: int
    resolved: int
    unresolved: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: ATH-resolver run result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_10AthResolverRunResult:
    """Immutable Stage 30.11.10 bounded ATH-resolver run result.

    The fake ATH-resolver proof emits exactly one of these per bounded pass. It
    carries the ordered per-candidate resolutions and the rolled-up
    ``Stage30_11_10AthResolverSummary``. Carries only safe scalars + the embedded
    resolutions + a caller-injected timestamp.

      * ``outcomes``       -- the ordered per-candidate ATH resolutions.
      * ``summary``        -- the embedded ``Stage30_11_10AthResolverSummary``.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp; NEVER a
                              wall-clock read.
    """

    outcomes: Tuple[Stage30_11_10AthResolution, ...]
    summary: Stage30_11_10AthResolverSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def ath_context_record_field_names() -> Tuple[str, ...]:
    """Return the committed-shape ATH context record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_10AthContextRecord))


def ath_resolution_field_names() -> Tuple[str, ...]:
    """Return the ATH resolution field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_10AthResolution))


def ath_resolver_summary_field_names() -> Tuple[str, ...]:
    """Return the ATH-resolver summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_10AthResolverSummary))


def ath_resolver_run_result_field_names() -> Tuple[str, ...]:
    """Return the ATH-resolver run result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_10AthResolverRunResult))


__all__ = (
    # Minor version + ATH-resolver schema identity.
    "STAGE30_11_10_MINOR_VERSION",
    "STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION",
    "STAGE30_11_10_SOURCE_STAGE",
    # Stage 27.4 ATH vocabulary (mirrored BY VALUE).
    "STAGE30_11_10_ATH_STATUS_PRESENT",
    "STAGE30_11_10_ATH_STATUS_STALE",
    "STAGE30_11_10_ATH_STATUS_UNAVAILABLE",
    "STAGE30_11_10_ATH_STATUS_NOT_APPLICABLE",
    "STAGE30_11_10_ATH_STATUS_UNSUPPORTED_PAIR",
    "STAGE30_11_10_ATH_STATUS_SOURCE_ERROR",
    "STAGE30_11_10_RECOGNIZED_ATH_STATUS_VALUES",
    "STAGE30_11_10_ATH_PRESENT_STATUS",
    "STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH",
    "STAGE30_11_10_DRAWDOWN_BASIS_NOT_APPLICABLE",
    "STAGE30_11_10_DRAWDOWN_BASIS_UNKNOWN",
    "STAGE30_11_10_RECOGNIZED_DRAWDOWN_BASIS_VALUES",
    "STAGE30_11_10_POST_MIGRATION_VERIFIED_DRAWDOWN_BASIS",
    "STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY",
    "STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION",
    # ATH resolver decisions.
    "ATH_DECISION_RESOLVED",
    "ATH_DECISION_UNRESOLVED",
    "STAGE30_11_10_ATH_DECISIONS",
    "STAGE30_11_10_ATH_PASS_DECISION",
    "is_ath_decision",
    # ATH resolver reasons.
    "ATH_REASON_RESOLVED_POST_MIGRATION_ATH",
    "ATH_REASON_BLANK_CANDIDATE_MINT",
    "ATH_REASON_MISSING_MIGRATION_ANCHOR",
    "ATH_REASON_MISSING_ATH_SOURCE",
    "ATH_REASON_ATH_SOURCE_ERROR",
    "ATH_REASON_ATH_SOURCE_UNAVAILABLE",
    "ATH_REASON_ATH_MINT_MISMATCH",
    "ATH_REASON_ATH_NOT_PRESENT",
    "ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED",
    "ATH_REASON_MISSING_DRAWDOWN",
    "STAGE30_11_10_ATH_REASONS",
    "STAGE30_11_10_ATH_PASS_REASON",
    "STAGE30_11_10_ATH_FAIL_CLOSED_REASONS",
    "is_ath_reason",
    # ATH-resolver proof baseline.
    "STAGE30_11_10_EXPECTED_BASES_SEEN",
    "STAGE30_11_10_EXPECTED_RESOLVED",
    "STAGE30_11_10_EXPECTED_UNRESOLVED",
    "STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11_10AthContextRecord",
    "Stage30_11_10AthResolution",
    "Stage30_11_10AthResolverSummary",
    "Stage30_11_10AthResolverRunResult",
    # Field-name helpers.
    "ath_context_record_field_names",
    "ath_resolution_field_names",
    "ath_resolver_summary_field_names",
    "ath_resolver_run_result_field_names",
)
