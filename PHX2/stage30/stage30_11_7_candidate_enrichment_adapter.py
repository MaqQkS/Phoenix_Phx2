"""Stage 30.11.7 candidate dip-enrichment adapter.

The pure, offline ENRICHMENT ADAPTER that fixes the narrowest blocker the
controlled live ceremony retry surfaced: a real harvested candidate carries
IDENTITY but not the Stage 30 dip fields, so the committed Stage 30.11.6
projection fails closed (``MISSING_REQUIRED_FIELD`` -> ``tier_hint``). This
adapter fills exactly those missing dip fields from INJECTED, offline / fake-first
resolvers and produces a flat enriched candidate the committed Stage 30.11.5
bounded runner / Stage 30.9.3 dip gate consume:

    a harvested / flat base candidate (a flat MAPPING / dict OR an
    attribute-bearing object whose keys / attributes carry the candidate IDENTITY
    -- ``candidate_id`` / ``token_mint`` / ``pair_type`` / ``source_ref`` /
    ``created_at_utc``)
      + four INJECTED resolvers (market context / tier / migration / ATH)
      -> resolve each dip dimension IN ORDER, failing closed on the FIRST dimension
         that cannot supply a usable, present, fresh, confirmed signal (a missing /
         unavailable / stale / unconfirmed / malformed signal is NEVER fabricated)
      -> map each CONFIRMED verdict to the gate's ``PRESENT`` token + a finite
         (market cap strictly positive) ``Decimal`` magnitude; carry the tier token
         VERBATIM (the committed dip gate classifies it later)
      -> build a Stage 30.11.5-shaped ``Stage30_11_7EnrichedCandidate``
      -> a ``Stage30_11_7EnrichmentResult``

The adapter ONLY enriches a candidate; it NEVER runs the assembler / bridge / dip
gate / runner / transport, NEVER decides dip eligibility (that is the committed
Stage 30.9.3 / Stage 30.10.1 gate's job, run LATER -- so a present-but-non-dip
tier like ``Tier Unknown`` enriches cleanly yet the gate suppresses it, NOT this
adapter), NEVER fabricates a missing context (a missing / unavailable market
context, a missing tier, an UNKNOWN / unconfirmed migration, or a missing / stale
/ pre-migration / malformed ATH each fails closed and can NEVER become eligible),
NEVER reserves a dispatch, NEVER calls a transport, and NEVER sends Discord.

The adapter NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (``created_at_utc`` is
caller-injected), and edits NO Stage 27 / Stage 28 / Stage 29 / Stage 30.3 / Stage
30.4 / Stage 30.11.5 / Stage 30.11.6 production file. It composes ONLY the Stage
30.11.7 models sibling plus the INJECTED resolvers; nothing more. In THIS slice
the injected resolvers are ALWAYS FAKES -- the real Stage 30.4 market context /
Stage 30.5 migration / Stage 30.7 ATH adapters plug in at the resolver seam via
out-of-repo, operator-authorized wrappers, exactly as the Stage 30.11.6 record
flattener wraps the real flattener at the ceremony boundary.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports ONLY the Stage 30.11.7 candidate-enrichment-models sibling. No other
    PHX2 module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / transport / Stage 30.11.5 / Stage 30.11.6 import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable, List, Optional

from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
    ENRICH_DIMENSION_ATH,
    ENRICH_DIMENSION_MARKET_CONTEXT,
    ENRICH_DIMENSION_MIGRATION,
    ENRICH_DIMENSION_NONE,
    ENRICH_DIMENSION_TIER,
    ENRICH_REASON_INVALID_DRAWDOWN,
    ENRICH_REASON_INVALID_MARKET_CAP,
    ENRICH_REASON_MISSING_ATH,
    ENRICH_REASON_MISSING_MARKET_CONTEXT,
    ENRICH_REASON_MISSING_MIGRATION_EVIDENCE,
    ENRICH_REASON_MISSING_TIER,
    ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ENRICH_REASON_READY_FOR_LIVE_RUNNER,
    ENRICH_REASON_STALE_ATH,
    ENRICH_REASON_UNCONFIRMED_MIGRATION,
    STAGE30_11_7_CONTEXT_STATUS_PRESENT,
    STAGE30_11_7_DEFAULT_MAX_ENRICH,
    STAGE30_11_7_MAX_ENRICH_HARD_CAP,
    Stage30_11_7EnrichedCandidate,
    Stage30_11_7EnrichmentResult,
    Stage30_11_7EnrichmentRunResult,
    Stage30_11_7EnrichmentSummary,
    is_nonblank_str,
)


# ---------------------------------------------------------------------------
# Injected resolver boundary types (duck-typed; a FAKE in this slice)
# ---------------------------------------------------------------------------
#
# Each injected resolver is a callable that, given the base candidate (so a real
# resolver may read its ``token_mint`` to query its source), returns ONE resolver
# result carrier (or ``None`` -> a missing signal). The adapter reads the result
# duck-typed (via attribute access), so a real out-of-repo resolver may return any
# object carrying the documented attributes; a missing attribute reads as the
# fail-closed value, and a raising resolver fails closed to a missing signal. In
# THIS slice every injected resolver is a FAKE; the real Stage 30.4 / 30.5 / 30.7
# adapter wrappers are injected at the operator-authorized ceremony.
Stage30_11_7MarketContextResolver = Callable[[object], object]
Stage30_11_7TierResolver = Callable[[object], object]
Stage30_11_7MigrationResolver = Callable[[object], object]
Stage30_11_7AthResolver = Callable[[object], object]


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11_7CandidateEnrichmentError(Exception):
    """Closed-set Stage 30.11.7 candidate enrichment error.

    Raised ONLY for a caller-shape failure the bounded enrichment helper cannot
    run with -- a ``max_enrich`` that is not a positive ``int`` within the HARD
    enrichment cap (``1 <= max_enrich <= STAGE30_11_7_MAX_ENRICH_HARD_CAP``): an
    out-of-bounds enrichment budget would make the bounded pass undefined, so the
    helper fails closed BEFORE enriching any base. Degraded per-candidate outcomes
    never raise; a raising resolver and a malformed resolution fail closed to a
    clean reject. Carries only a closed-set reason token; never a raw record or any
    secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.7 candidate enrichment error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure field readers / coercers
# ---------------------------------------------------------------------------


def _read_field(source: object, key: str) -> object:
    """Read field ``key`` from ``source``.

    Pure / total; never raises. ``source`` may be a flat MAPPING (read via
    ``.get``) or any attribute-bearing object (read via ``getattr``). A missing
    key / attribute (or a non-mapping / non-object) yields ``None``.
    """
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _is_true(value: object) -> bool:
    """Return ``True`` iff ``value`` is exactly the boolean ``True``.

    Pure / total; never raises. Mirrors the committed Stage 30.10.1 dip gate's
    ``is True`` discipline: a missing (``None``) / falsey / truthy-but-not-``True``
    verdict fails closed, so an absent resolver flag can never read as a confirmed
    signal.
    """
    return value is True


def _coerce_decimal(value: object) -> Optional[Decimal]:
    """Coerce ``value`` to a finite ``Decimal``, or return ``None`` if it cannot.

    Pure / total; never raises -- a ``bool``, a ``float`` (incl. ``nan`` / ``inf``),
    a non-numeric string, a non-finite ``Decimal`` (``NaN`` / ``sNaN`` /
    ``Infinity``), or any other malformed value fails closed to ``None`` without a
    ``decimal.InvalidOperation`` / ``TypeError`` / ``ValueError`` escaping. Only a
    finite ``Decimal`` is ever returned (so a fabricated non-finite magnitude can
    never reach the enriched candidate). A ``bool`` is rejected up front (``True`` /
    ``False`` are not magnitudes); a plain ``int`` and a safe decimal string are
    accepted. Mirrors the committed Stage 30.11.5 / 30.11.6 coercion BY VALUE.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        try:
            result = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
        return result if result.is_finite() else None
    return None


def _coerce_positive_decimal(value: object) -> Optional[Decimal]:
    """Coerce ``value`` to a finite, strictly-positive ``Decimal``, else ``None``.

    Pure / total; never raises. Builds on ``_coerce_decimal`` and additionally
    requires the magnitude to be ``> 0`` -- mirrors the committed Stage 30.10.1 dip
    gate's positive-market-cap requirement, so a zero / negative / malformed market
    cap fails closed and can never reach an enriched (eligible) candidate.
    """
    coerced = _coerce_decimal(value)
    if coerced is None:
        return None
    return coerced if coerced > 0 else None


def _echo_id(value: object) -> str:
    """Return ``value`` if it is a non-blank string, else ``""`` (for echoing the
    candidate identity onto the result even on a reject). Pure / total.
    """
    return value if is_nonblank_str(value) else ""


def _safe_resolve(resolver: object, base: object) -> object:
    """Call ``resolver(base)`` inside a fail-closed guard; return its result, or
    ``None`` if it is not callable or raises.

    Pure apart from the injected resolver's own behavior; never lets a resolver
    exception escape (``KeyboardInterrupt`` / ``SystemExit`` -- ``BaseException`` --
    are NOT swallowed). A non-callable resolver or a raising resolver yields
    ``None`` -- a missing signal the dimension check then fails closed on.
    """
    if not callable(resolver):
        return None
    try:
        return resolver(base)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _rejected(
    base: object,
    *,
    reason: str,
    dimension: str,
    created_at_utc: str,
) -> Stage30_11_7EnrichmentResult:
    """Build a fail-closed (no enriched candidate) result echoing whatever
    candidate identity is readable. Pure; no I/O.
    """
    return Stage30_11_7EnrichmentResult(
        candidate_id=_echo_id(_read_field(base, "candidate_id")),
        token_mint=_echo_id(_read_field(base, "token_mint")),
        enrichment_decision=ENRICH_DECISION_REJECTED,
        enrichment_reason=reason,
        rejected_dimension=dimension,
        enriched_candidate=None,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public enrichment adapter (per candidate)
# ---------------------------------------------------------------------------


def enrich_harvested_candidate(
    base: object,
    *,
    market_context_resolver: Stage30_11_7MarketContextResolver,
    tier_resolver: Stage30_11_7TierResolver,
    migration_resolver: Stage30_11_7MigrationResolver,
    ath_resolver: Stage30_11_7AthResolver,
    created_at_utc: str,
) -> Stage30_11_7EnrichmentResult:
    """Enrich ONE harvested / flat base candidate into a Stage 30.11.5-shaped flat
    enriched candidate, or fail closed.

    Pure / deterministic apart from the injected resolvers' own behavior / total /
    no I/O, no provider call, no Discord send, no env read, no wall-clock read
    (``created_at_utc`` stamps the result; the base's own ``created_at_utc`` flows
    onto the enriched candidate). Never raises for a malformed input / resolver --
    a non-mapping / non-object base, a ``None`` / raising resolver, or a malformed
    resolution all fail closed to a reject result (no enriched candidate).

    Resolution precedence (top-down, first failing dimension wins; mirrors the
    Stage 30 enrichment dimension order 1. market context, 2. tier, 3. migration,
    4. ATH):

      1. MARKET CONTEXT -- the resolver must return ``present is True`` AND a
         finite, strictly-positive ``current_market_cap_usd`` magnitude. A missing /
         unavailable context -> ``MISSING_MARKET_CONTEXT``; a malformed / non-
         positive cap -> ``INVALID_MARKET_CAP`` (dimension ``MARKET_CONTEXT``).
      2. TIER -- the resolver must return a non-blank ``tier_hint`` string (carried
         VERBATIM; the gate classifies it later). A missing / blank tier ->
         ``MISSING_TIER`` (dimension ``TIER``).
      3. MIGRATION -- the resolver must return ``confirmed is True`` (a trusted
         migration). A missing verdict -> ``MISSING_MIGRATION_EVIDENCE``; an UNKNOWN
         / unconfirmed verdict -> ``UNCONFIRMED_MIGRATION`` (dimension
         ``MIGRATION``).
      4. ATH -- the resolver must return ``present is True``, ``fresh is True``,
         ``post_migration_ath_verified is True``, AND a finite ``drawdown_from_ath``
         magnitude. A missing / unavailable ATH -> ``MISSING_ATH``; a stale ATH ->
         ``STALE_ATH``; a pre-migration ATH -> ``PRE_MIGRATION_ATH_NOT_VERIFIED``; a
         malformed drawdown -> ``INVALID_DRAWDOWN`` (dimension ``ATH``).
      5. otherwise -> ``ENRICHED_DIP_CANDIDATE`` / ``READY_FOR_LIVE_RUNNER`` with the
         built ``Stage30_11_7EnrichedCandidate``.

    The enrichment fabricates nothing: each ``migration_status`` / ``ath_status`` /
    ``market_context_status`` is set to the gate's ``PRESENT`` token ONLY when the
    corresponding resolver CONFIRMED presence; the ``tier_hint`` is carried verbatim
    (no parallel tier model); identity (``candidate_id`` / ``token_mint`` /
    ``pair_type`` / ``source_ref`` / ``created_at_utc``) is carried verbatim from
    the base (a blank id rides through to the committed Stage 30.11.5 assembler,
    which fails it closed there). Candidate identity is preserved.
    """
    # ---- 1. Market context: present + finite, strictly-positive market cap ----
    market = _safe_resolve(market_context_resolver, base)
    if not _is_true(_read_field(market, "present")):
        return _rejected(
            base,
            reason=ENRICH_REASON_MISSING_MARKET_CONTEXT,
            dimension=ENRICH_DIMENSION_MARKET_CONTEXT,
            created_at_utc=created_at_utc,
        )
    market_cap = _coerce_positive_decimal(
        _read_field(market, "current_market_cap_usd")
    )
    if market_cap is None:
        return _rejected(
            base,
            reason=ENRICH_REASON_INVALID_MARKET_CAP,
            dimension=ENRICH_DIMENSION_MARKET_CONTEXT,
            created_at_utc=created_at_utc,
        )

    # ---- 2. Tier: a non-blank token carried verbatim ----
    tier = _safe_resolve(tier_resolver, base)
    tier_hint = _read_field(tier, "tier_hint")
    if not is_nonblank_str(tier_hint):
        return _rejected(
            base,
            reason=ENRICH_REASON_MISSING_TIER,
            dimension=ENRICH_DIMENSION_TIER,
            created_at_utc=created_at_utc,
        )

    # ---- 3. Migration: an explicit confirmed verdict (UNKNOWN fails closed) ----
    migration = _safe_resolve(migration_resolver, base)
    if migration is None:
        return _rejected(
            base,
            reason=ENRICH_REASON_MISSING_MIGRATION_EVIDENCE,
            dimension=ENRICH_DIMENSION_MIGRATION,
            created_at_utc=created_at_utc,
        )
    if not _is_true(_read_field(migration, "confirmed")):
        return _rejected(
            base,
            reason=ENRICH_REASON_UNCONFIRMED_MIGRATION,
            dimension=ENRICH_DIMENSION_MIGRATION,
            created_at_utc=created_at_utc,
        )

    # ---- 4. ATH: present + fresh + post-migration-verified + finite drawdown ----
    ath = _safe_resolve(ath_resolver, base)
    if not _is_true(_read_field(ath, "present")):
        return _rejected(
            base,
            reason=ENRICH_REASON_MISSING_ATH,
            dimension=ENRICH_DIMENSION_ATH,
            created_at_utc=created_at_utc,
        )
    if not _is_true(_read_field(ath, "fresh")):
        return _rejected(
            base,
            reason=ENRICH_REASON_STALE_ATH,
            dimension=ENRICH_DIMENSION_ATH,
            created_at_utc=created_at_utc,
        )
    if not _is_true(_read_field(ath, "post_migration_ath_verified")):
        return _rejected(
            base,
            reason=ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
            dimension=ENRICH_DIMENSION_ATH,
            created_at_utc=created_at_utc,
        )
    drawdown = _coerce_decimal(_read_field(ath, "drawdown_from_ath"))
    if drawdown is None:
        return _rejected(
            base,
            reason=ENRICH_REASON_INVALID_DRAWDOWN,
            dimension=ENRICH_DIMENSION_ATH,
            created_at_utc=created_at_utc,
        )

    # ---- 5. Build the Stage 30.11.5-shaped flat enriched candidate ----
    #
    # Identity carried verbatim from the base; each context status set to the
    # gate's PRESENT token ONLY because the resolver CONFIRMED it (never
    # fabricated); the tier token carried verbatim (the committed dip gate
    # classifies it); the magnitudes the validated finite (cap strictly positive)
    # Decimals; ``post_migration_ath_verified`` the confirmed ``True``. An optional
    # ``source_ref`` is carried from the base if it is a string, else ``None``.
    base_source_ref = _read_field(base, "source_ref")
    source_ref = base_source_ref if isinstance(base_source_ref, str) else None
    enriched = Stage30_11_7EnrichedCandidate(
        candidate_id=_read_field(base, "candidate_id"),
        token_mint=_read_field(base, "token_mint"),
        pair_type=_read_field(base, "pair_type"),
        tier_hint=tier_hint,
        drawdown_from_ath=drawdown,
        migration_status=STAGE30_11_7_CONTEXT_STATUS_PRESENT,
        ath_status=STAGE30_11_7_CONTEXT_STATUS_PRESENT,
        market_context_status=STAGE30_11_7_CONTEXT_STATUS_PRESENT,
        current_market_cap_usd=market_cap,
        post_migration_ath_verified=True,
        source_ref=source_ref,
        created_at_utc=_read_field(base, "created_at_utc"),
    )
    return Stage30_11_7EnrichmentResult(
        candidate_id=_echo_id(enriched.candidate_id),
        token_mint=_echo_id(enriched.token_mint),
        enrichment_decision=ENRICH_DECISION_ENRICHED,
        enrichment_reason=ENRICH_REASON_READY_FOR_LIVE_RUNNER,
        rejected_dimension=ENRICH_DIMENSION_NONE,
        enriched_candidate=enriched,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Bounded-enrich config helper
# ---------------------------------------------------------------------------


def is_within_enrich_cap(max_enrich: object) -> bool:
    """Return ``True`` iff ``max_enrich`` is a positive ``int`` within the HARD
    enrichment cap (``1 <= max_enrich <= STAGE30_11_7_MAX_ENRICH_HARD_CAP``).

    Pure / TOTAL; never raises. A non-int, a ``bool`` (``True`` / ``False`` are not
    budgets), a non-positive value, or a value above the hard cap fails closed to
    ``False`` -- so an enrichment pass can never be parameterized to produce more
    than the committed Stage 30.11.5 ``max_candidates <= 10`` ceiling allows.
    """
    if isinstance(max_enrich, bool):
        return False
    if not isinstance(max_enrich, int):
        return False
    return 1 <= max_enrich <= STAGE30_11_7_MAX_ENRICH_HARD_CAP


# ---------------------------------------------------------------------------
# Public bounded enrichment helper (a candidate_source for the committed runner)
# ---------------------------------------------------------------------------


def enrich_candidate_source(
    bases: Iterable[object],
    *,
    market_context_resolver: Stage30_11_7MarketContextResolver,
    tier_resolver: Stage30_11_7TierResolver,
    migration_resolver: Stage30_11_7MigrationResolver,
    ath_resolver: Stage30_11_7AthResolver,
    created_at_utc: str,
    max_enrich: int = STAGE30_11_7_DEFAULT_MAX_ENRICH,
) -> Stage30_11_7EnrichmentRunResult:
    """Enrich AT MOST ``max_enrich`` base candidates into a Stage 30.11.5-ready
    enriched ``candidate_source``.

    Pure / deterministic apart from the injected resolvers' own behavior; reads no
    env, no clock, no network (``created_at_utc`` is injected); reserves no
    dispatch, sends no Discord, writes no file, runs no daemon / ``while`` loop, and
    NEVER constructs a runner / transport / dispatch sink -- so it can never reach
    a send surface. The enriched ``candidate_source`` is the INPUT the committed
    Stage 30.11.5 bounded runner (and behind it the committed Stage 30.11.1 bridge +
    Stage 30.9.3 dip gate + Stage 30.11.3 private sink) gate; producing it is never
    a bypass of them.

    Fail closed first: if ``max_enrich`` is not a positive ``int`` within the HARD
    cap the helper raises ``Stage30_11_7CandidateEnrichmentError`` BEFORE enriching
    any base.

    Otherwise it pulls AT MOST ``max_enrich`` bases (a single BOUNDED for-loop; it
    stops at the cap), enriches each via ``enrich_harvested_candidate``, accumulates
    every ``ENRICHED_DIP_CANDIDATE`` into the ``candidate_source``, tallies each
    fail-closed dimension, and rolls up the counts. A rejected base never becomes a
    candidate, so it never reaches the Stage 30.11.5 runner / transport.
    """
    if not is_within_enrich_cap(max_enrich):
        # Fail closed on an out-of-bounds enrichment budget: enrich nothing.
        raise Stage30_11_7CandidateEnrichmentError("INVALID_MAX_ENRICH")

    outcomes: List[Stage30_11_7EnrichmentResult] = []
    candidate_source: List[Stage30_11_7EnrichedCandidate] = []
    bases_seen = 0
    rejected_market_context = 0
    rejected_tier = 0
    rejected_migration = 0
    rejected_ath = 0

    for base in bases:
        if bases_seen >= max_enrich:
            break
        bases_seen += 1

        result = enrich_harvested_candidate(
            base,
            market_context_resolver=market_context_resolver,
            tier_resolver=tier_resolver,
            migration_resolver=migration_resolver,
            ath_resolver=ath_resolver,
            created_at_utc=created_at_utc,
        )
        outcomes.append(result)
        if (
            result.enrichment_decision == ENRICH_DECISION_ENRICHED
            and result.enriched_candidate is not None
        ):
            candidate_source.append(result.enriched_candidate)
            continue

        # A fail-closed reject: tally the offending dimension. It never becomes a
        # candidate, so it never reaches the Stage 30.11.5 runner / transport.
        if result.rejected_dimension == ENRICH_DIMENSION_MARKET_CONTEXT:
            rejected_market_context += 1
        elif result.rejected_dimension == ENRICH_DIMENSION_TIER:
            rejected_tier += 1
        elif result.rejected_dimension == ENRICH_DIMENSION_MIGRATION:
            rejected_migration += 1
        elif result.rejected_dimension == ENRICH_DIMENSION_ATH:
            rejected_ath += 1

    summary = Stage30_11_7EnrichmentSummary(
        bases_seen=bases_seen,
        enriched=len(candidate_source),
        rejected_market_context=rejected_market_context,
        rejected_tier=rejected_tier,
        rejected_migration=rejected_migration,
        rejected_ath=rejected_ath,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_7EnrichmentRunResult(
        outcomes=tuple(outcomes),
        candidate_source=tuple(candidate_source),
        summary=summary,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_7MarketContextResolver",
    "Stage30_11_7TierResolver",
    "Stage30_11_7MigrationResolver",
    "Stage30_11_7AthResolver",
    "Stage30_11_7CandidateEnrichmentError",
    "is_within_enrich_cap",
    "enrich_harvested_candidate",
    "enrich_candidate_source",
)
