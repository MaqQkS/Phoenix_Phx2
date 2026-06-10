"""Stage 30.11.20 current-price enrichment adapter.

The pure, bounded, fail-closed ADAPTER that closes the current_price blocker the
Stage 30.11.18 contract exposed -- by REUSING the already-committed Stage 29.2
``/defi/price`` price source (it builds NO new fetcher and forces NO read() shim):

    an iterable of base Stage30_11_18HarvestedCandidateFacts
      -> for each base fact (a single BOUNDED for-loop; AT MOST ``max_candidates``
         scanned):
           -> Layer-0 enrichment: read ONE price snapshot from the INJECTED,
              duck-typed price source via its NATIVE never-raises surface
              (``price_source.fetch_snapshot(base_mint=token_mint)``); when the
              snapshot status is PRESENT and the price value + fetched-at pass a
              pure presence / shape / positivity check, overwrite ONLY
              ``current_price`` on a COPY of the fact via dataclasses.replace
              (``ENRICHED``); otherwise fail closed to a closed-set ``SKIPPED_*``
              token and leave the fact UN-enriched + NOT forwarded (no silent
              pass-through)
           -> a redaction-safe per-fact ``Stage30_11_20PriceEnrichmentEvent``
      -> the ENRICHED facts (only) run through the committed Stage 30.11.19
         enrichment session (and behind it the Stage 30.11.18 / 30.11.17 sessions)
         over the injected FAKE recording transport client (a RECORDED would-send,
         NEVER a real send)
      -> a rolled-up redaction-safe ``Stage30_11_20PriceEnrichmentSessionReport``
         (the Layer-0 events + counts + the EMBEDDED Stage 30.11.19 report + the
         combined redaction status -- ONE combined nested report)

``market_context_fetched_at_utc`` is NEVER overwritten here (the Stage 30.11.19
bundle owns it; the snapshot's own fetched-at is validated for reading coherence
but written NOWHERE). ``migration_time_utc`` and every other field are carried
through UNCHANGED (the migration-time seam is the next separate slice). The price
source is INJECTED and read DUCK-TYPED (the adapter calls only
``source.fetch_snapshot(base_mint=...)`` and reads the snapshot by attribute);
committed Stage 30.11.20 constructs NO real provider transport, imports the Stage
29.2 price source NOT at all, and reads NO env. The real ``/defi/price`` read (the
operator constructs the committed Stage 29.2 price source over a real transport +
secret) and the controlled live send remain a SEPARATE, ceremony-injected,
operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``). The Layer-0 positivity + ISO-shape
    checks REUSE the committed Stage 30.11.18 predicates (no decimal / datetime).
  * Imports ONLY the committed Stage 30.11.19 enrichment adapter (the session the
    enriched facts run through), the committed Stage 30.11.18 facts models +
    adapter predicates, the committed Stage 30.11.17 models (session config + cap
    validator), and the Stage 30.11.20 models sibling. No other PHX2 module; no
    Stage 21-29 / Stage 29.2 price source / Stage 30.4.3 source / Stage 30.11.16
    real-send guard import.
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
)
from PHX2.stage30.stage30_11_19_market_context_enrichment_adapter import (
    run_stage30_11_19_enriched_session,
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_models import (
    PRICE_ENRICHMENT_DECISION_ENRICHED,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT,
    PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED,
    STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS,
    STAGE30_11_20_PRICE_SOURCE_METHOD,
    STAGE30_11_20_PRICE_STATUS_MISSING,
    STAGE30_11_20_PRICE_STATUS_PRESENT,
    STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR,
    STAGE30_11_20_REDACTED_UNSAFE_ID,
    STAGE30_11_20_REDACTION_STATUS_REDACTED,
    STAGE30_11_20_REDACTION_STATUS_VIOLATION,
    Stage30_11_20PriceEnrichmentEvent,
    Stage30_11_20PriceEnrichmentResult,
    Stage30_11_20PriceEnrichmentSessionReport,
    is_nonblank_str,
    is_safe_echo_id,
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no
# bare needle). Mirrors the committed Stage 30.11.19 / 30.11.18 scan.
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


class Stage30_11_20CurrentPriceEnrichmentError(Exception):
    """Closed-set Stage 30.11.20 current-price enrichment error.

    Raised ONLY for a caller-shape failure the runner cannot run with -- a session
    config that is not within the HARD Stage 30.11.17 session caps
    (``is_within_session_caps`` is ``False``). The runner fails closed BEFORE
    scanning any base fact, mirroring the committed Stage 30.11.19 session. Degraded
    per-fact base facts never raise; a non-facts base or an unusable snapshot fails
    closed to a clean ``SKIPPED_*`` decision. Carries only a closed-set reason
    token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.20 current-price enrichment error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure safe-shape helpers
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_11_20_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the
    committed Stage 30.11.19 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_20_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_20_REDACTED_UNSAFE_ID


def _safe_fetch(price_source: object, token_mint: object) -> Any:
    """Call ``price_source.fetch_snapshot(base_mint=token_mint)`` total-ly.

    Returns whatever ``fetch_snapshot`` returned, or ``None`` when the source is
    missing a callable ``fetch_snapshot`` or the call raises. The committed Stage
    29.2 price source's ``fetch_snapshot`` never raises by contract; the try guard
    keeps the Layer-0 ladder total against any foreign injected object. Pure apart
    from the injected source's own read; never raises. A ``None`` result fails
    closed to ``SKIPPED_NO_PRICE_READING``.
    """
    fetch_method = getattr(price_source, STAGE30_11_20_PRICE_SOURCE_METHOD, None)
    if not callable(fetch_method):
        return None
    try:
        return fetch_method(base_mint=token_mint)
    except Exception:
        return None


def _is_snapshot_shape(snapshot: object) -> bool:
    """Return ``True`` iff ``snapshot`` exposes the required price-snapshot attrs."""
    for attr in STAGE30_11_20_PRICE_SNAPSHOT_REQUIRED_ATTRS:
        if not hasattr(snapshot, attr):
            return False
    return True


# ---------------------------------------------------------------------------
# Layer-0 enrichment: base facts + price snapshot -> enriched facts
# ---------------------------------------------------------------------------


def _skipped(decision: str) -> Stage30_11_20PriceEnrichmentResult:
    """Build a fail-closed Layer-0 skip result (no enriched facts)."""
    return Stage30_11_20PriceEnrichmentResult(
        decision=decision, enriched_facts=None
    )


def enrich_facts_with_current_price(
    base_facts: object,
    *,
    price_source: object,
) -> Stage30_11_20PriceEnrichmentResult:
    """Enrich ONE base fact's ``current_price`` from the injected price source.

    Pure / total; never raises. Decision ladder (top-down, first failing check
    wins): non-facts base -> no snapshot -> wrong snapshot shape -> status
    SOURCE_ERROR -> status MISSING -> status unrecognized -> missing price value ->
    invalid / non-positive price value -> missing fetched-at -> invalid fetched-at
    -> else ``ENRICHED``. On ``ENRICHED`` it returns a COPY of the base fact (via
    ``dataclasses.replace``) with ONLY ``current_price`` overwritten from the
    snapshot's ``price_value``; ``market_context_fetched_at_utc`` is NEVER
    overwritten (the snapshot's fetched-at is a coherence gate ONLY -- a PRESENT
    price with a missing / garbage timestamp is a degenerate reading and skips);
    ``migration_time_utc`` + every other field are carried through UNCHANGED. A
    literal-zero price (a valid PRESENT reading at the source) can never dispatch,
    so it fails closed HERE to ``SKIPPED_INVALID_PRICE_VALUE`` with a precise token
    rather than burying the rejection at Layer-1. On any skip the base fact is
    NEVER mutated and ``enriched_facts`` is ``None`` (the runner does not forward
    it).
    """
    # ---- Base must be a committed facts record ----
    if not isinstance(base_facts, Stage30_11_18HarvestedCandidateFacts):
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS)

    # ---- Read from the injected duck-typed price source ----
    snapshot = _safe_fetch(price_source, base_facts.token_mint)
    if snapshot is None:
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING)
    if not _is_snapshot_shape(snapshot):
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING)

    # ---- Snapshot status (the source's own closed-set verdict) ----
    status = getattr(snapshot, "birdeye_price_status", None)
    if status == STAGE30_11_20_PRICE_STATUS_SOURCE_ERROR:
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR)
    if status == STAGE30_11_20_PRICE_STATUS_MISSING:
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING)
    if status != STAGE30_11_20_PRICE_STATUS_PRESENT:
        return _skipped(
            PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED
        )

    price_value = getattr(snapshot, "price_value", None)
    fetched_at = getattr(snapshot, "fetched_at_utc", None)

    # ---- Price value (present + strictly positive) ----
    if not is_nonblank_str(price_value):
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE)
    if not is_positive_decimal_text(price_value):
        return _skipped(PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE)

    # ---- Fetched-at (present + ISO shape; a coherence gate ONLY -- the value is
    #      written NOWHERE and market_context_fetched_at_utc stays untouched) ----
    if not is_nonblank_str(fetched_at):
        return _skipped(
            PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT
        )
    if not is_iso_utc_shape(fetched_at):
        return _skipped(
            PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT
        )

    # ---- All Layer-0 checks passed -> overwrite ONLY current_price ----
    enriched = replace(base_facts, current_price=price_value)
    return Stage30_11_20PriceEnrichmentResult(
        decision=PRICE_ENRICHMENT_DECISION_ENRICHED,
        enriched_facts=enriched,
    )


# ---------------------------------------------------------------------------
# Redaction self-scan over the enrichment events
# ---------------------------------------------------------------------------


def _event_text_fields(
    event: Stage30_11_20PriceEnrichmentEvent,
) -> Tuple[str, ...]:
    """Return the string-typed fields of one enrichment event (the haystack)."""
    return (
        event.decision,
        event.candidate_id,
        event.token_mint,
        event.created_at_utc,
    )


def _enrichment_events_redaction_safe(
    events: Iterable[Stage30_11_20PriceEnrichmentEvent],
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


def run_stage30_11_20_price_enriched_session(
    base_facts: Iterable[object],
    *,
    price_source: object,
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
) -> Stage30_11_20PriceEnrichmentSessionReport:
    """Run ONE bounded current-price enrichment session and return a
    ``Stage30_11_20PriceEnrichmentSessionReport``.

    Fail closed first: if ``config`` is not within the HARD Stage 30.11.17 session
    caps the runner raises ``Stage30_11_20CurrentPriceEnrichmentError`` BEFORE
    scanning any base fact.

    Otherwise it scans AT MOST ``config.max_candidates`` base facts (a single
    BOUNDED for-loop), enriches each at Layer-0 (overwriting ONLY ``current_price``
    or failing closed to a ``SKIPPED_*`` token), records a redaction-safe per-fact
    event, then runs the committed Stage 30.11.19 enrichment session over the
    ENRICHED facts ONLY (skipped facts are NOT forwarded) -- driving behind it the
    Stage 30.11.18 projection + the Stage 30.11.17 compose/dedupe session over the
    injected market-context source + injected dedupe ledger + injected FAKE
    recording transport client + injected fake ATH source transport + injected
    clocks (a RECORDED would-send, NEVER a real send). The rolled-up report carries
    the Layer-0 enrichment events + counts, the embedded Stage 30.11.19 report
    (ONE combined nested report), and the combined redaction status.

    Pure / deterministic apart from the injected sources' reads + the injected fake
    transport client's + ledger's recording side effects; reads no env, no clock,
    no network; constructs no provider transport, reserves no real dispatch, sends
    no Discord, writes no file, runs no daemon / ``while`` loop.
    """
    if not is_within_session_caps(config):
        # Fail closed on an out-of-bounds config: scan nothing.
        raise Stage30_11_20CurrentPriceEnrichmentError("INVALID_SESSION_CONFIG")

    created_at_utc = config.created_at_utc
    max_candidates = config.max_candidates

    enrichment_events: List[Stage30_11_20PriceEnrichmentEvent] = []
    enriched_facts: List[Any] = []
    facts_seen = 0
    enriched = 0

    for base in base_facts:
        if facts_seen >= max_candidates:
            break
        index = facts_seen
        facts_seen += 1

        result = enrich_facts_with_current_price(
            base, price_source=price_source
        )
        enrichment_events.append(
            Stage30_11_20PriceEnrichmentEvent(
                index=index,
                decision=result.decision,
                candidate_id=_safe_echo(getattr(base, "candidate_id", None)),
                token_mint=_safe_echo(getattr(base, "token_mint", None)),
                created_at_utc=created_at_utc,
            )
        )
        if result.decision == PRICE_ENRICHMENT_DECISION_ENRICHED:
            enriched += 1
            enriched_facts.append(result.enriched_facts)

    skipped = facts_seen - enriched

    # Run the committed Stage 30.11.19 session over the ENRICHED facts ONLY.
    downstream_report = run_stage30_11_19_enriched_session(
        enriched_facts,
        market_context_source=market_context_source,
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
    # Stage 30.11.19 report must itself be redacted.
    events_safe = _enrichment_events_redaction_safe(enrichment_events)
    downstream_redacted = (
        getattr(downstream_report, "redaction_status", "")
        == STAGE30_11_20_REDACTION_STATUS_REDACTED
    )
    redaction_status = (
        STAGE30_11_20_REDACTION_STATUS_REDACTED
        if (events_safe and downstream_redacted)
        else STAGE30_11_20_REDACTION_STATUS_VIOLATION
    )

    return Stage30_11_20PriceEnrichmentSessionReport(
        enrichment_events=tuple(enrichment_events),
        facts_seen=facts_seen,
        enriched=enriched,
        skipped=skipped,
        downstream_report=downstream_report,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_20CurrentPriceEnrichmentError",
    "enrich_facts_with_current_price",
    "run_stage30_11_20_price_enriched_session",
)
