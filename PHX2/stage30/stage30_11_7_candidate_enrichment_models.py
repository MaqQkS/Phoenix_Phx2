"""Stage 30.11.7 candidate dip-enrichment bridge models.

Stage 30.11.7 ships the passive, pure, stdlib-only MODEL layer for the narrowest
remaining blocker the controlled live ceremony retry surfaced: the committed
Stage 30.11.6 harvest seam can capture + project a real assembled candidate's
flat fields, but the committed live chain produces only candidate IDENTITY -- it
does NOT produce the Stage 30 dip / enrichment fields (a ``tier_hint``, a
``current_market_cap_usd``, real migration evidence, an ATH / drawdown). So the
fail-closed Stage 30.11.6 projection correctly rejected the harvested candidate
with ``MISSING_REQUIRED_FIELD`` (rejected field ``tier_hint``), and that safety
behavior MUST remain. Stage 30.11.7 adds the narrow ENRICHMENT bridge that fills
exactly those missing dip fields from INJECTED, offline / fake-first resolvers,
producing a flat enriched candidate the committed Stage 30.11.5 runner / Stage
30.9.3 dip gate consume -- failing closed (never fabricating) when a resolver
cannot supply a usable, present, fresh, confirmed signal.

This module is the MODEL layer ONLY. It implements NO enrichment adapter (that is
``stage30_11_7_candidate_enrichment_adapter``), drives NO resolver, runs NO
bridge / dip gate / runner, calls NO transport / dispatch, wires into NO runtime,
makes NO live provider call, sends NO Discord message, reads NO process
environment, opens NO network connection, opens NO database, writes NO file,
reserves NO dispatch, reads NO wall clock (``created_at_utc`` is caller-injected),
and edits NO Stage 27 / Stage 28 / Stage 29 / Stage 30.3 / Stage 30.4 production
file. Stage 30.11.7 is fake / offline only: the real private compact dispatch /
Discord send remains a SEPARATE, explicitly operator-authorized step this slice
does not build.

The slice owns one closed-set vocabulary:

  * the per-candidate ENRICHMENT decision / reason -- the enrichment adapter emits
    exactly one of ``ENRICHED_DIP_CANDIDATE`` (every injected resolver returned a
    usable signal AND the enriched fields built a clean flat candidate; reason
    ``READY_FOR_LIVE_RUNNER``), or ``REJECTED_ENRICHMENT`` for the FIRST failing
    dimension (a missing / unavailable market context -> ``MISSING_MARKET_CONTEXT``;
    a present-but-malformed / non-positive market cap -> ``INVALID_MARKET_CAP``; a
    missing tier -> ``MISSING_TIER``; a missing migration verdict ->
    ``MISSING_MIGRATION_EVIDENCE``; an UNKNOWN / unconfirmed / contradictory
    migration -> ``UNCONFIRMED_MIGRATION``; a missing / unavailable ATH ->
    ``MISSING_ATH``; a stale ATH -> ``STALE_ATH``; an ATH not verified
    post-migration -> ``PRE_MIGRATION_ATH_NOT_VERIFIED``; a malformed drawdown ->
    ``INVALID_DRAWDOWN``). A ``REJECTED_ENRICHMENT`` outcome carries NO enriched
    candidate, names the offending DIMENSION (``MARKET_CONTEXT`` / ``TIER`` /
    ``MIGRATION`` / ``ATH``), and so NEVER becomes a ``candidate_source`` the
    committed runner could dispatch.

The enrichment FABRICATES nothing: an enriched candidate is built ONLY when each
injected resolver returns an explicit present / confirmed / fresh verdict, and the
enrichment maps those verdicts to the gate's ``PRESENT`` token (a confirmed
verdict is NEVER defaulted; an UNKNOWN / missing / stale verdict fails closed and
can NEVER become ``PRESENT``). The ``tier_hint`` is carried VERBATIM from the tier
resolver: the enrichment computes no tier and NEVER forces dip eligibility -- the
committed Stage 30.10.1 classifier (run LATER inside the committed dip gate)
classifies the tier, so a present-but-non-dip token (``Tier Unknown``) enriches
cleanly yet is suppressed by the gate, NOT here.

The enriched candidate's field NAMES + order equal the committed Stage 30.11.5 /
Stage 30.11.6 flat projection field names BY VALUE (a pin test cross-checks the
equality), so the committed Stage 30.11.5 bounded runner reads it via attribute
access exactly as it reads a flat projection -- no Stage 30.11.6 import is needed
(this slice stays a stdlib-only leaf; the real Stage 30.4 market context / Stage
30.5 migration / Stage 30.7 ATH adapters plug in at the INJECTED resolver seam via
out-of-repo, operator-authorized wrappers, exactly as the Stage 30.11.6 record
flattener wraps the real flattener at the ceremony boundary).

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Imports NO PHX2 module. The Stage 30.11.5 flat projection field names are
    mirrored BY VALUE (a pin test cross-checks they equal the committed Stage
    30.11.6 projection field names); the slice imports NO Stage 21-29 (incl. the
    nested Stage 27 / 28 / 29 live candidate record) / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport /
    Stage 30.11.5 / Stage 30.11.6 module.
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
# Minor version + enrichment schema identity
# ---------------------------------------------------------------------------


STAGE30_11_7_MINOR_VERSION: str = "30.11.7"


# The Stage 30.11.7 candidate dip-enrichment bridge schema version. Names the
# enrichment / resolver-result / enriched-candidate shapes; distinct from the
# Stage 30.11.6 candidate-source schema version and every earlier Stage 30.11
# schema version. Mirrored BY VALUE by the Stage 30.11 manifest section; this
# module imports no Stage 30.11 manifest.
STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION: str = (
    "stage30_11_7_v0_candidate_enrichment"
)


# The safe-shape source-stage provenance token the enrichment bridge stamps onto
# its results (provenance only; names the slice that produced the enrichment,
# never a secret / host / transport destination).
STAGE30_11_7_SOURCE_STAGE: str = "30.11.7"


# ---------------------------------------------------------------------------
# Stage 30.11.5 flat projection field names (mirrored BY VALUE)
# ---------------------------------------------------------------------------
#
# The enrichment bridge fills a harvested candidate into the EXACT Stage 30.11.5 /
# Stage 30.11.6 flat safe-scalar projection shape the committed Stage 30.11.5
# bounded runner consumes. These names equal the committed Stage 30.11.6
# projection field names BY VALUE (a pin test cross-checks the equality against
# the committed Stage 30.11.6 models). This module mirrors them rather than
# importing the Stage 30.11.6 models so it stays a stdlib-only leaf. NONE is a
# secret, a raw payload, a host, or a transport destination.


# Each REQUIRED enriched field must be present + well-shaped, else the enriched
# candidate could not be built. ``drawdown_from_ath`` / ``current_market_cap_usd``
# are finite ``Decimal`` magnitudes; the rest are non-blank strings.
STAGE30_11_7_REQUIRED_ENRICHED_FIELDS: Tuple[str, ...] = (
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


# The optional enriched fields: ``None`` is allowed; a present value is
# well-shaped (``post_migration_ath_verified`` a ``bool``; ``source_ref`` a
# string).
STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS: Tuple[str, ...] = (
    "post_migration_ath_verified",
    "source_ref",
)


# Every enriched-candidate field name (required + optional), in Stage 30.11.5 /
# Stage 30.11.6 snapshot order.
STAGE30_11_7_ENRICHED_FIELDS: Tuple[str, ...] = (
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
# The gate-facing PRESENT token (mirrored BY VALUE)
# ---------------------------------------------------------------------------
#
# A migration / ATH / current-market context is "present" to the committed Stage
# 30.11.1 bridge + Stage 30.9.3 / 30.10.1 dip gate IFF its status token is exactly
# ``PRESENT`` (mirrors the committed Stage 30.10.1 ``MIGRATION_STATUS_PRESENT`` /
# ``ATH_STATUS_PRESENT`` / ``MARKET_CONTEXT_STATUS_PRESENT`` and the Stage 30.11.1
# ``LIVE_CONTEXT_STATUS_PRESENT`` values BY VALUE; this module imports no Stage
# 30.10 / 30.11.1 module). The enrichment maps a confirmed resolver verdict to
# this token; it NEVER fabricates it for a missing / unconfirmed / stale verdict.
STAGE30_11_7_CONTEXT_STATUS_PRESENT: str = "PRESENT"


# ---------------------------------------------------------------------------
# Closed-set: per-candidate enrichment decision
# ---------------------------------------------------------------------------
#
# Exactly one enrichment decision per base candidate. ``ENRICHED_DIP_CANDIDATE``
# is the only decision that carries a built ``Stage30_11_7EnrichedCandidate``;
# ``REJECTED_ENRICHMENT`` carries ``None``. Mirrored BY VALUE by the Stage 30.11
# manifest.


ENRICH_DECISION_ENRICHED: str = "ENRICHED_DIP_CANDIDATE"
ENRICH_DECISION_REJECTED: str = "REJECTED_ENRICHMENT"


STAGE30_11_7_ENRICHMENT_DECISIONS: Tuple[str, ...] = (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
)


# The single decision that yields a built enriched candidate.
STAGE30_11_7_ENRICHMENT_PASS_DECISION: str = ENRICH_DECISION_ENRICHED


def is_enrichment_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set enrichment decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str) and value in STAGE30_11_7_ENRICHMENT_DECISIONS
    )


# ---------------------------------------------------------------------------
# Closed-set: per-candidate enrichment reason
# ---------------------------------------------------------------------------
#
# Exactly one enrichment reason per decision. ``READY_FOR_LIVE_RUNNER`` is the
# only reason that accompanies a built enriched candidate; every other reason
# names the FIRST failing dimension's fail-closed cause. Mirrored BY VALUE by the
# manifest.


ENRICH_REASON_READY_FOR_LIVE_RUNNER: str = "READY_FOR_LIVE_RUNNER"
ENRICH_REASON_MISSING_MARKET_CONTEXT: str = "MISSING_MARKET_CONTEXT"
ENRICH_REASON_INVALID_MARKET_CAP: str = "INVALID_MARKET_CAP"
ENRICH_REASON_MISSING_TIER: str = "MISSING_TIER"
ENRICH_REASON_MISSING_MIGRATION_EVIDENCE: str = "MISSING_MIGRATION_EVIDENCE"
ENRICH_REASON_UNCONFIRMED_MIGRATION: str = "UNCONFIRMED_MIGRATION"
ENRICH_REASON_MISSING_ATH: str = "MISSING_ATH"
ENRICH_REASON_STALE_ATH: str = "STALE_ATH"
ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED: str = (
    "PRE_MIGRATION_ATH_NOT_VERIFIED"
)
ENRICH_REASON_INVALID_DRAWDOWN: str = "INVALID_DRAWDOWN"


STAGE30_11_7_ENRICHMENT_REASONS: Tuple[str, ...] = (
    ENRICH_REASON_READY_FOR_LIVE_RUNNER,
    ENRICH_REASON_MISSING_MARKET_CONTEXT,
    ENRICH_REASON_INVALID_MARKET_CAP,
    ENRICH_REASON_MISSING_TIER,
    ENRICH_REASON_MISSING_MIGRATION_EVIDENCE,
    ENRICH_REASON_UNCONFIRMED_MIGRATION,
    ENRICH_REASON_MISSING_ATH,
    ENRICH_REASON_STALE_ATH,
    ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ENRICH_REASON_INVALID_DRAWDOWN,
)


# The single reason that accompanies the only enriched decision.
STAGE30_11_7_ENRICHMENT_PASS_REASON: str = ENRICH_REASON_READY_FOR_LIVE_RUNNER


def is_enrichment_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set enrichment reason.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str) and value in STAGE30_11_7_ENRICHMENT_REASONS
    )


# ---------------------------------------------------------------------------
# Closed-set: rejected enrichment dimension
# ---------------------------------------------------------------------------
#
# The safe DIMENSION name a reject fails closed on (the four enrichment
# dimensions), or ``""`` when enriched. Mirrored BY VALUE by the manifest.


ENRICH_DIMENSION_NONE: str = ""
ENRICH_DIMENSION_MARKET_CONTEXT: str = "MARKET_CONTEXT"
ENRICH_DIMENSION_TIER: str = "TIER"
ENRICH_DIMENSION_MIGRATION: str = "MIGRATION"
ENRICH_DIMENSION_ATH: str = "ATH"


STAGE30_11_7_ENRICHMENT_DIMENSIONS: Tuple[str, ...] = (
    ENRICH_DIMENSION_MARKET_CONTEXT,
    ENRICH_DIMENSION_TIER,
    ENRICH_DIMENSION_MIGRATION,
    ENRICH_DIMENSION_ATH,
)


def is_enrichment_dimension(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set enrichment dimension (the
    four dip dimensions; the empty ``""`` enriched sentinel is NOT a dimension).

    Pure / total; never raises.
    """
    return (
        isinstance(value, str) and value in STAGE30_11_7_ENRICHMENT_DIMENSIONS
    )


# ---------------------------------------------------------------------------
# Hard enrichment cap + default + candidate-id prefix
# ---------------------------------------------------------------------------
#
# The bounded enrichment helper enriches AT MOST ``max_enrich`` base candidates (a
# single bounded for-loop; no ``while`` loop, no daemon). The hard cap mirrors the
# Stage 30.11.6 ``max_harvest <= 10`` / Stage 30.11.5 ``max_candidates <= 10``
# ceiling so the enriched ``candidate_source`` can never exceed what the bounded
# runner is allowed to evaluate. A ``max_enrich`` above the cap fails closed BEFORE
# enriching anything.


STAGE30_11_7_MAX_ENRICH_HARD_CAP: int = 10
STAGE30_11_7_DEFAULT_MAX_ENRICH: int = 10


# ---------------------------------------------------------------------------
# Author-verified offline enrichment proof baseline
# ---------------------------------------------------------------------------
#
# The Stage 30.11.7 fake enrichment proof drives a deterministic SIX-base fake
# source through the enrichment bridge (injected fake resolvers): one Tier 1 dip +
# one Tier Unknown non-dip enrich cleanly; one each fails closed on a missing
# market context / a missing tier / an unconfirmed (UNKNOWN) migration / a stale
# ATH. The enriched ``candidate_source`` (two candidates) is then fed -- by the
# Stage 30.11.7 TEST -- through the committed Stage 30.11.5 bounded runner: two
# candidates seen, two bridged, one dip-gate PASS, exactly one fake transport
# attempt + accept -- for the Tier 1 dip ONLY. The non-dip is suppressed by the
# committed dip gate; the four fail-closed candidates never enrich, so none reaches
# the transport; the old ungated dispatch path is never invoked. Mirrored BY VALUE
# by the manifest. NONE is a secret, a raw payload, a host, or a transport
# destination.


STAGE30_11_7_EXPECTED_BASES_SEEN: int = 6
STAGE30_11_7_EXPECTED_ENRICHED: int = 2
STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT: int = 1
STAGE30_11_7_EXPECTED_REJECTED_TIER: int = 1
STAGE30_11_7_EXPECTED_REJECTED_MIGRATION: int = 1
STAGE30_11_7_EXPECTED_REJECTED_ATH: int = 1
STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN: int = 2
STAGE30_11_7_EXPECTED_RUNNER_BRIDGED: int = 2
STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED: int = 1
STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS: int = 1


# The exact safe-shape identity of the single dip the fake transport is allowed to
# see. No other candidate id / token mint may reach the transport. The candidate
# id / token mint are carried VERBATIM from the dip base candidate (the enrichment
# stamps no run-scoped id -- the base already carries the harvested identity).
STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID: str = "stage30_11_7_cand_dip"
STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT: str = "mint-dip"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape token. Pure / total; never raises. Mirrors the Stage
    30.11.1 / 30.11.5 / 30.11.6 non-blank check BY VALUE; the slice consults it to
    validate ids / status tokens / timestamps / the carried-verbatim tier token.
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable resolver-result carriers (the INJECTED resolvers return these)
# ---------------------------------------------------------------------------
#
# Each injected resolver returns one of these (or ``None`` -> a missing signal,
# the strongest fail-closed posture). Every field defaults to its FAIL-CLOSED
# value (``present`` / ``confirmed`` / ``fresh`` ``False``; every magnitude /
# token ``None``) -- mirroring the Stage 30.7 ATH evidence ``redaction_safe=False``
# default -- so a bare resolution can NEVER enrich. The enrichment reads these
# duck-typed (via attribute access), so a real out-of-repo resolver may return any
# object carrying the same attributes; a missing attribute reads as the fail-closed
# value. NONE carries a secret, a raw payload, a host, or a transport destination.


@dataclass(frozen=True)
class Stage30_11_7MarketContextResolution:
    """Immutable market-context resolver result.

    The injected market-context resolver returns this (or ``None``). The
    enrichment requires ``present is True`` AND a finite, strictly-positive
    ``current_market_cap_usd`` magnitude to map to ``market_context_status =
    PRESENT`` + a finite-positive ``Decimal``; a missing / unavailable context
    (``present`` not ``True`` / ``None`` resolution) fails closed to
    ``MISSING_MARKET_CONTEXT``, and a malformed / non-positive cap fails closed to
    ``INVALID_MARKET_CAP``.

      * ``present``                -- ``True`` iff a usable present market context.
      * ``current_market_cap_usd`` -- the current market cap magnitude (an ``int``
                                      / ``Decimal`` / safe decimal-text ``str``),
                                      or ``None``.
      * ``source_ref``             -- optional opaque provenance ref, or ``None``.
    """

    present: bool = False
    current_market_cap_usd: object = None
    source_ref: Optional[str] = None


@dataclass(frozen=True)
class Stage30_11_7TierResolution:
    """Immutable tier resolver result.

    The injected tier resolver returns this (or ``None``). The enrichment requires
    a non-blank string ``tier_hint`` to carry VERBATIM (a missing / blank tier
    fails closed to ``MISSING_TIER``); it does NOT classify or normalize the tier
    -- the committed Stage 30.10.1 classifier (run LATER in the dip gate) decides
    dip eligibility, so a present-but-non-dip token (``Tier Unknown``) enriches
    cleanly and the gate suppresses it, NOT this enrichment.

      * ``tier_hint`` -- the Stage 30.1 tier token (display ``Tier N`` form or the
                        normalized code), carried verbatim, or ``None``.
    """

    tier_hint: object = None


@dataclass(frozen=True)
class Stage30_11_7MigrationResolution:
    """Immutable migration resolver result.

    The injected migration resolver returns this (or ``None``). The enrichment
    requires ``confirmed is True`` (a trusted / on-chain-confirmed migration) to
    map to ``migration_status = PRESENT``; a missing verdict (``None`` resolution)
    fails closed to ``MISSING_MIGRATION_EVIDENCE``, and an UNKNOWN / unconfirmed /
    contradictory verdict (``confirmed`` not ``True``) fails closed to
    ``UNCONFIRMED_MIGRATION`` -- an UNKNOWN migration can NEVER become eligible.

      * ``confirmed``  -- ``True`` ONLY for a trusted / confirmed migration.
      * ``source_ref`` -- optional opaque provenance ref, or ``None``.
    """

    confirmed: bool = False
    source_ref: Optional[str] = None


@dataclass(frozen=True)
class Stage30_11_7AthResolution:
    """Immutable ATH / drawdown resolver result.

    The injected ATH resolver returns this (or ``None``). The enrichment requires
    ALL of ``present is True`` (a present, non-errored ATH source), ``fresh is
    True`` (not stale), ``post_migration_ath_verified is True`` (the ATH is
    verified post-migration), AND a finite ``drawdown_from_ath`` magnitude to map
    to ``ath_status = PRESENT`` + a finite ``Decimal`` drawdown + ``True``. A
    missing / unavailable ATH fails closed to ``MISSING_ATH``; a stale ATH to
    ``STALE_ATH``; a pre-migration ATH to ``PRE_MIGRATION_ATH_NOT_VERIFIED``; a
    malformed drawdown to ``INVALID_DRAWDOWN`` -- a missing / stale / pre-migration
    / malformed ATH can NEVER become eligible.

      * ``present``                     -- ``True`` iff a present ATH source.
      * ``fresh``                       -- ``True`` iff the ATH is fresh (not
                                          stale).
      * ``post_migration_ath_verified`` -- ``True`` iff the ATH is verified
                                          post-migration.
      * ``drawdown_from_ath``           -- the drawdown magnitude (an ``int`` /
                                          ``Decimal`` / safe decimal-text ``str``),
                                          or ``None``.
      * ``source_ref``                  -- optional opaque provenance ref, or
                                          ``None``.
    """

    present: bool = False
    fresh: bool = False
    post_migration_ath_verified: object = None
    drawdown_from_ath: object = None
    source_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Immutable model: the Stage 30.11.5-shaped flat enriched candidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_7EnrichedCandidate:
    """Immutable Stage 30.11.5-shaped flat enriched candidate.

    The enriched candidate the Stage 30.11.7 enrichment adapter builds and the
    bounded enrichment helper accumulates into a ``candidate_source`` the committed
    Stage 30.11.5 bounded runner consumes directly. Its field NAMES + order equal
    the committed Stage 30.11.5 / Stage 30.11.6 projection field names BY VALUE, so
    the committed Stage 30.11.5 assembler reads it via attribute access exactly as
    it reads a flat projection. Carries ONLY safe scalars (opaque ids, display
    tokens, finite ``Decimal`` magnitudes, a caller-injected timestamp); no secret,
    no raw provider payload, no host, no transport destination, no env value, and
    NO reference to the deeply-nested live candidate record the harvested base was
    flattened from.

      * ``candidate_id`` / ``token_mint``  -- echoed safe-shape ids (carried
                                              VERBATIM from the harvested base;
                                              identity is preserved).
      * ``pair_type``                      -- display token (carried verbatim from
                                              the base).
      * ``tier_hint``                      -- the tier resolver's token (carried
                                              VERBATIM; the committed dip gate
                                              decides eligibility, NOT this
                                              enrichment).
      * ``drawdown_from_ath`` /
        ``current_market_cap_usd``         -- finite ``Decimal`` magnitudes from the
                                              ATH / market-context resolvers
                                              (market cap strictly positive).
      * ``migration_status`` / ``ath_status`` /
        ``market_context_status``          -- the gate's ``PRESENT`` token, set ONLY
                                              when the corresponding resolver
                                              CONFIRMED presence (never fabricated).
      * ``post_migration_ath_verified``    -- ``True`` (the ATH resolver verified
                                              post-migration; required to enrich) or
                                              ``None``.
      * ``source_ref``                     -- optional opaque provenance ref, or
                                              ``None``.
      * ``created_at_utc``                 -- caller-injected ISO-8601 UTC
                                              timestamp (carried from the base);
                                              NEVER a wall-clock read.
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
# Immutable model: per-candidate enrichment result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_7EnrichmentResult:
    """Immutable per-candidate Stage 30.11.7 enrichment result.

    The enrichment adapter emits exactly one of these per base candidate. It
    echoes the safe-shape candidate identity, pins the closed-set
    ``enrichment_decision`` / ``enrichment_reason``, names the FIRST offending
    DIMENSION on a reject (a safe dimension NAME only, never a field VALUE; ``""``
    when enriched), and carries the built ``Stage30_11_7EnrichedCandidate`` (ONLY
    for an ``ENRICHED_DIP_CANDIDATE`` decision; ``None`` otherwise). Carries only
    safe scalars + the embedded enriched candidate + a caller-injected timestamp.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids (``""`` when
                                             unreadable).
      * ``enrichment_decision``           -- one of
                                             ``STAGE30_11_7_ENRICHMENT_DECISIONS``.
      * ``enrichment_reason``             -- one of
                                             ``STAGE30_11_7_ENRICHMENT_REASONS``.
      * ``rejected_dimension``            -- the safe dimension NAME that failed
                                             closed (one of
                                             ``STAGE30_11_7_ENRICHMENT_DIMENSIONS``),
                                             or ``""`` when enriched.
      * ``enriched_candidate``            -- the built
                                             ``Stage30_11_7EnrichedCandidate``
                                             (only for an ENRICHED decision;
                                             ``None`` for a reject).
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    enrichment_decision: str
    enrichment_reason: str
    rejected_dimension: str
    enriched_candidate: Optional[Stage30_11_7EnrichedCandidate]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: enrichment proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_7EnrichmentSummary:
    """Immutable Stage 30.11.7 enrichment proof tally.

    A passive summary of one bounded enrichment pass. It proves, by counting, that
    ONLY a base whose every injected resolver returned a usable signal became an
    enriched ``candidate_source`` candidate, that each fail-closed dimension was
    suppressed cleanly (no enriched candidate), and that the hard enrichment cap
    held. Carries only non-negative integer counts + a caller-injected timestamp.

      * ``bases_seen``                -- base candidates taken from the bounded
                                         source (<= ``max_enrich``).
      * ``enriched``                  -- count that yielded an enriched candidate.
      * ``rejected_market_context``   -- count failed closed on the market context.
      * ``rejected_tier``             -- count failed closed on the tier.
      * ``rejected_migration``        -- count failed closed on the migration.
      * ``rejected_ath``              -- count failed closed on the ATH.
      * ``created_at_utc``            -- caller-injected ISO-8601 UTC timestamp.
    """

    bases_seen: int
    enriched: int
    rejected_market_context: int
    rejected_tier: int
    rejected_migration: int
    rejected_ath: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: enrichment run result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_7EnrichmentRunResult:
    """Immutable Stage 30.11.7 bounded enrichment run result.

    The bounded enrichment helper emits exactly one of these per bounded pass. It
    carries the ordered per-candidate enrichment results, the enriched
    ``candidate_source`` (a tuple of ``Stage30_11_7EnrichedCandidate`` the
    committed Stage 30.11.5 bounded runner consumes directly), and the rolled-up
    ``Stage30_11_7EnrichmentSummary``. Carries only safe scalars + the embedded
    results + a caller-injected timestamp.

      * ``outcomes``         -- the ordered per-candidate enrichment results.
      * ``candidate_source`` -- the enriched ``Stage30_11_7EnrichedCandidate``
                                tuple, ready for the committed Stage 30.11.5
                                bounded runner ``candidate_source``.
      * ``summary``          -- the embedded ``Stage30_11_7EnrichmentSummary``.
      * ``created_at_utc``   -- caller-injected ISO-8601 UTC timestamp; NEVER a
                                wall-clock read.
    """

    outcomes: Tuple[Stage30_11_7EnrichmentResult, ...]
    candidate_source: Tuple[Stage30_11_7EnrichedCandidate, ...]
    summary: Stage30_11_7EnrichmentSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def enriched_candidate_field_names() -> Tuple[str, ...]:
    """Return the enriched candidate field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7EnrichedCandidate))


def enrichment_result_field_names() -> Tuple[str, ...]:
    """Return the enrichment result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7EnrichmentResult))


def enrichment_summary_field_names() -> Tuple[str, ...]:
    """Return the enrichment summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7EnrichmentSummary))


def enrichment_run_result_field_names() -> Tuple[str, ...]:
    """Return the enrichment run result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7EnrichmentRunResult))


def market_context_resolution_field_names() -> Tuple[str, ...]:
    """Return the market-context resolution field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7MarketContextResolution))


def tier_resolution_field_names() -> Tuple[str, ...]:
    """Return the tier resolution field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7TierResolution))


def migration_resolution_field_names() -> Tuple[str, ...]:
    """Return the migration resolution field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7MigrationResolution))


def ath_resolution_field_names() -> Tuple[str, ...]:
    """Return the ATH resolution field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_7AthResolution))


__all__ = (
    # Minor version + enrichment schema identity.
    "STAGE30_11_7_MINOR_VERSION",
    "STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION",
    "STAGE30_11_7_SOURCE_STAGE",
    # Enriched field names.
    "STAGE30_11_7_REQUIRED_ENRICHED_FIELDS",
    "STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS",
    "STAGE30_11_7_ENRICHED_FIELDS",
    # Gate-facing PRESENT token.
    "STAGE30_11_7_CONTEXT_STATUS_PRESENT",
    # Enrichment decisions.
    "ENRICH_DECISION_ENRICHED",
    "ENRICH_DECISION_REJECTED",
    "STAGE30_11_7_ENRICHMENT_DECISIONS",
    "STAGE30_11_7_ENRICHMENT_PASS_DECISION",
    "is_enrichment_decision",
    # Enrichment reasons.
    "ENRICH_REASON_READY_FOR_LIVE_RUNNER",
    "ENRICH_REASON_MISSING_MARKET_CONTEXT",
    "ENRICH_REASON_INVALID_MARKET_CAP",
    "ENRICH_REASON_MISSING_TIER",
    "ENRICH_REASON_MISSING_MIGRATION_EVIDENCE",
    "ENRICH_REASON_UNCONFIRMED_MIGRATION",
    "ENRICH_REASON_MISSING_ATH",
    "ENRICH_REASON_STALE_ATH",
    "ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED",
    "ENRICH_REASON_INVALID_DRAWDOWN",
    "STAGE30_11_7_ENRICHMENT_REASONS",
    "STAGE30_11_7_ENRICHMENT_PASS_REASON",
    "is_enrichment_reason",
    # Rejected dimensions.
    "ENRICH_DIMENSION_NONE",
    "ENRICH_DIMENSION_MARKET_CONTEXT",
    "ENRICH_DIMENSION_TIER",
    "ENRICH_DIMENSION_MIGRATION",
    "ENRICH_DIMENSION_ATH",
    "STAGE30_11_7_ENRICHMENT_DIMENSIONS",
    "is_enrichment_dimension",
    # Hard cap + default.
    "STAGE30_11_7_MAX_ENRICH_HARD_CAP",
    "STAGE30_11_7_DEFAULT_MAX_ENRICH",
    # Enrichment proof baseline.
    "STAGE30_11_7_EXPECTED_BASES_SEEN",
    "STAGE30_11_7_EXPECTED_ENRICHED",
    "STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT",
    "STAGE30_11_7_EXPECTED_REJECTED_TIER",
    "STAGE30_11_7_EXPECTED_REJECTED_MIGRATION",
    "STAGE30_11_7_EXPECTED_REJECTED_ATH",
    "STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN",
    "STAGE30_11_7_EXPECTED_RUNNER_BRIDGED",
    "STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED",
    "STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT",
    # Safe-shape helper.
    "is_nonblank_str",
    # Resolver-result carriers.
    "Stage30_11_7MarketContextResolution",
    "Stage30_11_7TierResolution",
    "Stage30_11_7MigrationResolution",
    "Stage30_11_7AthResolution",
    # Models.
    "Stage30_11_7EnrichedCandidate",
    "Stage30_11_7EnrichmentResult",
    "Stage30_11_7EnrichmentSummary",
    "Stage30_11_7EnrichmentRunResult",
    # Field-name helpers.
    "enriched_candidate_field_names",
    "enrichment_result_field_names",
    "enrichment_summary_field_names",
    "enrichment_run_result_field_names",
    "market_context_resolution_field_names",
    "tier_resolution_field_names",
    "migration_resolution_field_names",
    "ath_resolution_field_names",
)
