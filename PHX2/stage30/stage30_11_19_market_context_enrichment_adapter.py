"""Stage 30.11.19 market-context enrichment adapter.

The pure, bounded, fail-closed ADAPTER that closes the liquidity blocker the Stage
30.11.18 contract exposed -- by REUSING the already-committed Stage 30.4.3
token-overview market-context source (it builds NO new fetcher):

    an iterable of base Stage30_11_18HarvestedCandidateFacts
      -> for each base fact (a single BOUNDED for-loop; AT MOST ``max_candidates``
         scanned):
           -> Layer-0 enrichment: read ONE reading from the INJECTED, duck-typed
              market-context source; when MC + LP + observed-at all pass a pure
              presence / shape / positivity check and the reading is not stale,
              fill the COHERENT market-context bundle on a COPY of the fact
              (current_market_cap_usd, liquidity_usd, market_context_fetched_at_utc,
              market_context_status=PRESENT) via dataclasses.replace (``ENRICHED``);
              otherwise fail closed to a closed-set ``SKIPPED_*`` token and leave
              the fact UN-enriched + NOT forwarded (no silent pass-through)
           -> a redaction-safe per-fact ``Stage30_11_19EnrichmentEvent``
      -> the ENRICHED facts (only) run through the committed Stage 30.11.18
         adapter/session (and behind it the Stage 30.11.17 compose/dedupe session)
         over the injected FAKE recording transport client (a RECORDED would-send,
         NEVER a real send)
      -> a rolled-up redaction-safe ``Stage30_11_19EnrichmentSessionReport`` (the
         Layer-0 events + counts + the EMBEDDED Stage 30.11.18 report + the combined
         redaction status)

``current_price`` and ``migration_time_utc`` are carried through UNCHANGED
(separate seams). The market-context source is INJECTED and read DUCK-TYPED (the
adapter calls only ``source.read(token_mint)`` and reads the reading by attribute);
committed Stage 30.11.19 constructs NO real provider transport, imports the Stage
30.4.3 source NOT at all, and reads NO env. The real token-overview read (the
operator constructs the committed Stage 30.4.3 source over a real Stage 29.2
transport) and the controlled live send remain a SEPARATE, ceremony-injected,
operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``). The Layer-0 positivity + ISO-shape
    checks REUSE the committed Stage 30.11.18 predicates (no decimal / datetime).
  * Imports ONLY the committed Stage 30.11.18 facts models + adapter, the committed
    Stage 30.11.17 models (session config + cap validator), and the Stage 30.11.19
    models sibling. No other PHX2 module; no Stage 21-29 / Stage 30.4.3 source /
    Stage 30.11.16 real-send guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; every timestamp / clock is
    caller-injected.
  * No filesystem-write surface (persistence is the injected ledger's job).
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, List, Optional, Tuple

from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
    is_within_session_caps,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_18_harvest_to_curated_adapter import (
    is_iso_utc_shape,
    is_positive_decimal_text,
    run_stage30_11_18_curated_session,
)
from PHX2.stage30.stage30_11_19_market_context_enrichment_models import (
    ENRICHMENT_DECISION_ENRICHED,
    ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD,
    ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP,
    ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT,
    ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD,
    ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP,
    ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT,
    ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING,
    ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING,
    ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT,
    STAGE30_11_19_REDACTED_UNSAFE_ID,
    STAGE30_11_19_REDACTION_STATUS_REDACTED,
    STAGE30_11_19_REDACTION_STATUS_VIOLATION,
    Stage30_11_19EnrichmentEvent,
    Stage30_11_19EnrichmentResult,
    Stage30_11_19EnrichmentSessionReport,
    is_nonblank_str,
    is_safe_echo_id,
)


# The market-context status value the enrichment writes onto the facts on
# ``ENRICHED`` (the committed composer requires exactly ``PRESENT`` to dispatch).
_MARKET_CONTEXT_PRESENT: str = "PRESENT"


# The reading attributes the enrichment reads off the duck-typed source reading. A
# reading missing any of them is a wrong shape (``SKIPPED_NOT_A_MARKET_CONTEXT_READING``).
_REQUIRED_READING_ATTRS: Tuple[str, ...] = (
    "market_cap_usd_value",
    "liquidity_usd_value",
    "observed_at_utc",
    "stale",
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no
# bare needle). Mirrors the committed Stage 30.11.18 / 30.11.17 scan.
# ---------------------------------------------------------------------------


_REDACTION_SCHEME_SEP: str = ":" + "/" + "/"
_REDACTION_NEEDLES: Tuple[str, ...] = (
    "disc" + "ord.com",
    "disc" + "ordapp.com",
    "/web" + "hooks/",
    "web" + "hook url",
    "ap" + "i_key",
    "ap" + "i key",
    "x-api-" + "key",
    "x-" + "token",
    "b" + "earer",
    "author" + "ization",
    "raw" + "_body",
    "response" + "_body",
    "head" + "ers",
    "public-api.bird" + "eye.so",
    "dex" + "screener.com",
    "chain" + "stack",
    "hel" + "ius",
)


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11_19MarketContextEnrichmentError(Exception):
    """Closed-set Stage 30.11.19 market-context enrichment error.

    Raised ONLY for a caller-shape failure the runner cannot run with -- a session
    config that is not within the HARD Stage 30.11.17 session caps
    (``is_within_session_caps`` is ``False``). The runner fails closed BEFORE
    scanning any base fact, mirroring the committed session. Degraded per-fact base
    facts never raise; a non-facts base or an unusable reading fails closed to a
    clean ``SKIPPED_*`` decision. Carries only a closed-set reason token; never a
    raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.19 market-context enrichment error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure safe-shape helpers
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_11_19_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the
    committed Stage 30.11.18 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_19_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_19_REDACTED_UNSAFE_ID


def _safe_read(market_context_source: object, token_mint: object) -> Any:
    """Call ``market_context_source.read(token_mint)`` total-ly.

    Returns whatever ``read`` returned, or ``None`` when the source is missing a
    callable ``read`` or ``read`` raises. Pure apart from the injected source's own
    read; never raises. A ``None`` result fails closed to
    ``SKIPPED_NO_MARKET_CONTEXT_READING``.
    """
    read_method = getattr(market_context_source, "read", None)
    if not callable(read_method):
        return None
    try:
        return read_method(token_mint)
    except Exception:
        return None


def _is_reading_shape(reading: object) -> bool:
    """Return ``True`` iff ``reading`` exposes the required market-context attrs."""
    for attr in _REQUIRED_READING_ATTRS:
        if not hasattr(reading, attr):
            return False
    return True


# ---------------------------------------------------------------------------
# Layer-0 enrichment: base facts + reading -> enriched facts
# ---------------------------------------------------------------------------


def _skipped(decision: str) -> Stage30_11_19EnrichmentResult:
    """Build a fail-closed Layer-0 skip result (no enriched facts)."""
    return Stage30_11_19EnrichmentResult(decision=decision, enriched_facts=None)


def enrich_facts_with_market_context(
    base_facts: object,
    *,
    market_context_source: object,
) -> Stage30_11_19EnrichmentResult:
    """Enrich ONE base fact's market-context bundle from the injected source.

    Pure / total; never raises. Decision ladder (top-down, first failing check
    wins): non-facts base -> no reading -> wrong reading shape -> stale reading ->
    missing/invalid MC -> missing/invalid LP -> missing/invalid observed-at -> else
    ``ENRICHED``. On ``ENRICHED`` it returns a COPY of the base fact (via
    ``dataclasses.replace``) with ONLY the four market-context fields overwritten
    (``current_market_cap_usd``, ``liquidity_usd``, ``market_context_fetched_at_utc``
    from the reading; ``market_context_status`` set to ``PRESENT``);
    ``current_price`` + ``migration_time_utc`` + every other field are carried
    through UNCHANGED. On any skip the base fact is NEVER mutated and
    ``enriched_facts`` is ``None`` (the runner does not forward it).
    """
    # ---- Base must be a committed facts record ----
    if not isinstance(base_facts, Stage30_11_18HarvestedCandidateFacts):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS)

    # ---- Read from the injected duck-typed market-context source ----
    reading = _safe_read(market_context_source, base_facts.token_mint)
    if reading is None:
        return _skipped(ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING)
    if not _is_reading_shape(reading):
        return _skipped(
            ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING
        )

    # ---- Staleness (the source's own flag; time-based freshness stays Layer-2) --
    if getattr(reading, "stale", True):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT)

    market_cap = getattr(reading, "market_cap_usd_value", None)
    liquidity = getattr(reading, "liquidity_usd_value", None)
    observed_at = getattr(reading, "observed_at_utc", None)

    # ---- Market cap (present + strictly positive) ----
    if not is_nonblank_str(market_cap):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP)
    if not is_positive_decimal_text(market_cap):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP)

    # ---- Liquidity (present + strictly positive) ----
    if not is_nonblank_str(liquidity):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD)
    if not is_positive_decimal_text(liquidity):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD)

    # ---- Observed-at (present + ISO shape; the composer owns time freshness) ----
    if not is_nonblank_str(observed_at):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT)
    if not is_iso_utc_shape(observed_at):
        return _skipped(ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT)

    # ---- All Layer-0 checks passed -> fill the coherent market-context bundle ----
    enriched = replace(
        base_facts,
        current_market_cap_usd=market_cap,
        liquidity_usd=liquidity,
        market_context_fetched_at_utc=observed_at,
        market_context_status=_MARKET_CONTEXT_PRESENT,
    )
    return Stage30_11_19EnrichmentResult(
        decision=ENRICHMENT_DECISION_ENRICHED,
        enriched_facts=enriched,
    )


# ---------------------------------------------------------------------------
# Redaction self-scan over the enrichment events
# ---------------------------------------------------------------------------


def _event_text_fields(
    event: Stage30_11_19EnrichmentEvent,
) -> Tuple[str, ...]:
    """Return the string-typed fields of one enrichment event (the haystack)."""
    return (
        event.decision,
        event.candidate_id,
        event.token_mint,
        event.created_at_utc,
    )


def _enrichment_events_redaction_safe(
    events: Iterable[Stage30_11_19EnrichmentEvent],
) -> bool:
    """Return ``True`` iff no enrichment-event string field carries a
    transport-scheme separator or a forbidden url / secret needle. Pure / total.
    """
    for event in events:
        for text in _event_text_fields(event):
            if not isinstance(text, str):
                continue
            lowered = text.lower()
            if _REDACTION_SCHEME_SEP in lowered:
                return False
            for needle in _REDACTION_NEEDLES:
                if needle in lowered:
                    return False
    return True


# ---------------------------------------------------------------------------
# Public bounded enrichment session
# ---------------------------------------------------------------------------


def run_stage30_11_19_enriched_session(
    base_facts: Iterable[object],
    *,
    market_context_source: object,
    config: Stage30_11_17SessionConfig,
    ledger: object,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    transport_client: object,
    now_seconds: object,
    ath_timeout_seconds: int = 10,
    market_context_max_age_seconds: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_19EnrichmentSessionReport:
    """Run ONE bounded market-context enrichment session and return a
    ``Stage30_11_19EnrichmentSessionReport``.

    Fail closed first: if ``config`` is not within the HARD Stage 30.11.17 session
    caps the runner raises ``Stage30_11_19MarketContextEnrichmentError`` BEFORE
    scanning any base fact.

    Otherwise it scans AT MOST ``config.max_candidates`` base facts (a single
    BOUNDED for-loop), enriches each at Layer-0 (filling the market-context bundle
    or failing closed to a ``SKIPPED_*`` token), records a redaction-safe per-fact
    event, then runs the committed Stage 30.11.18 curated session over the
    ENRICHED facts ONLY (skipped facts are NOT forwarded) -- driving behind it the
    Stage 30.11.17 compose/dedupe session over the injected dedupe ledger + injected
    FAKE recording transport client + injected fake ATH source transport + injected
    clocks (a RECORDED would-send, NEVER a real send). The rolled-up report carries
    the Layer-0 enrichment events + counts, the embedded Stage 30.11.18 report, and
    the combined redaction status.

    Pure / deterministic apart from the injected source's read + the injected fake
    transport client's + ledger's recording side effects; reads no env, no clock,
    no network; constructs no provider transport, reserves no real dispatch, sends
    no Discord, writes no file, runs no daemon / ``while`` loop.
    """
    if not is_within_session_caps(config):
        # Fail closed on an out-of-bounds config: scan nothing.
        raise Stage30_11_19MarketContextEnrichmentError("INVALID_SESSION_CONFIG")

    created_at_utc = config.created_at_utc
    max_candidates = config.max_candidates

    enrichment_events: List[Stage30_11_19EnrichmentEvent] = []
    enriched_facts: List[Any] = []
    facts_seen = 0
    enriched = 0

    for base in base_facts:
        if facts_seen >= max_candidates:
            break
        index = facts_seen
        facts_seen += 1

        result = enrich_facts_with_market_context(
            base, market_context_source=market_context_source
        )
        enrichment_events.append(
            Stage30_11_19EnrichmentEvent(
                index=index,
                decision=result.decision,
                candidate_id=_safe_echo(getattr(base, "candidate_id", None)),
                token_mint=_safe_echo(getattr(base, "token_mint", None)),
                created_at_utc=created_at_utc,
            )
        )
        if result.decision == ENRICHMENT_DECISION_ENRICHED:
            enriched += 1
            enriched_facts.append(result.enriched_facts)

    skipped = facts_seen - enriched

    # Run the committed Stage 30.11.18 session over the ENRICHED facts ONLY.
    downstream_report = run_stage30_11_18_curated_session(
        enriched_facts,
        config=config,
        ledger=ledger,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=transport_client,
        now_seconds=now_seconds,
        ath_timeout_seconds=ath_timeout_seconds,
        market_context_max_age_seconds=market_context_max_age_seconds,
        ttl_seconds=ttl_seconds,
    )

    # Combined redaction status: the Layer-0 events must be safe AND the embedded
    # Stage 30.11.18 report must itself be redacted.
    events_safe = _enrichment_events_redaction_safe(enrichment_events)
    downstream_redacted = (
        getattr(downstream_report, "redaction_status", "")
        == STAGE30_11_19_REDACTION_STATUS_REDACTED
    )
    redaction_status = (
        STAGE30_11_19_REDACTION_STATUS_REDACTED
        if (events_safe and downstream_redacted)
        else STAGE30_11_19_REDACTION_STATUS_VIOLATION
    )

    return Stage30_11_19EnrichmentSessionReport(
        enrichment_events=tuple(enrichment_events),
        facts_seen=facts_seen,
        enriched=enriched,
        skipped=skipped,
        downstream_report=downstream_report,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_19MarketContextEnrichmentError",
    "enrich_facts_with_market_context",
    "run_stage30_11_19_enriched_session",
)
