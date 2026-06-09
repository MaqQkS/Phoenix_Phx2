"""Stage 30.11.18 harvested-facts -> curated compose session adapter.

The pure, bounded, fail-closed ADAPTER that lets a ceremony feed already-harvested
+ enriched candidate FACTS (rather than hand-built requests) into the
already-proven Stage 30.11.17 operator-curated compose session:

    an iterable of harvested-candidate facts records
      -> for each fact (a single BOUNDED for-loop; AT MOST ``max_candidates``
         scanned):
           -> Layer-1 projection: a pure presence / shape / positivity check that
              either builds ONE committed Stage 30.11.13 revalidation request
              (``PROJECTED``) or fails closed to a closed-set ``REJECTED_*`` token
              (the fact never reaches the composer)
           -> a redaction-safe per-fact ``Stage30_11_18ProjectionEvent``
      -> the projected facts, wrapped as ``Stage30_11_17OperatorCuratedCandidate``
         entries, run through the committed Stage 30.11.17 operator-curated compose
         session over the injected dedupe ledger + injected FAKE recording
         transport client + injected fake ATH source transport + injected clocks (a
         RECORDED would-send, NEVER a real send)
      -> a rolled-up redaction-safe ``Stage30_11_18SessionReport`` (the Layer-1
         projection events + counts + the EMBEDDED Stage 30.11.17 session result +
         the combined redaction status)

Two validation layers, no overlap. Stage 30.11.18 owns ONLY Layer-1: presence /
shape / positivity of the scalar inputs it can check WITHOUT a clock or a
transport. The committed Stage 30.11.13 composer remains AUTHORITATIVE for Layer-2:
freshness (stale / future fetch), ATH resolution, tier eligibility, and the dip
gate. A projected fact can still be rejected at Layer-2 -- that verdict is surfaced
VERBATIM in the embedded session result's mirrored compose reason (e.g.
``MARKET_CONTEXT_STALE``); the adapter never re-implements the freshness clock.

The adapter enforces the SAME hard bound as the committed Stage 30.11.17 session
(``max_candidates <= 10``): it scans AT MOST ``config.max_candidates`` facts in a
single BOUNDED for-loop (a larger input is bounded -- ``facts_seen`` equal to the
cap signals the scan stopped early); there is NO ``while`` loop, NO daemon, NO
background service, NO autorestart loop. It NEVER harvests, NEVER fetches market
data, NEVER opens a network connection, NEVER reads the process environment, NEVER
reads a clock (the clocks are injected; the composer owns the Layer-2 freshness
clock), NEVER sends Discord, NEVER reserves a REAL dispatch / performs a real send,
NEVER calls the Stage 30.11.16 real private transport guard, NEVER binds a real
harvest adapter, NEVER touches a live provider session, NEVER writes a file (the
ledger owns any persistence), and edits NO committed composer / session / dedupe /
ledger / renderer / tier-band file. The real harvest + market-context enrichment
that produces the facts, and the controlled live send, remain a SEPARATE,
ceremony-injected, operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing`` / ``decimal``). ``decimal`` parses
    the decimal-text magnitudes for the Layer-1 positivity check.
  * Imports ONLY the committed Stage 30.11.13 revalidation request, the committed
    Stage 30.11.17 models + session, and the Stage 30.11.18 models sibling. No
    other PHX2 module; no Stage 21-29 / Stage 30.11.16 real-send guard / Stage
    30.11.6 harvest adapter / live provider / real transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; every timestamp / clock is
    caller-injected.
  * No filesystem-write surface (persistence is the injected ledger's job).
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, List, Optional, Tuple

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    Stage30_11_13RevalidationRequest,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17OperatorCuratedCandidate,
    Stage30_11_17SessionConfig,
    is_within_session_caps,
)
from PHX2.stage30.stage30_11_17_operator_curated_compose_session import (
    run_stage30_11_17_operator_curated_compose_session,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID,
    PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT,
    PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE,
    PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD,
    PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP,
    PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT,
    PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC,
    PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT,
    PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT,
    PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED,
    PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID,
    PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT,
    PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE,
    PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD,
    PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP,
    PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT,
    PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC,
    PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT,
    PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD,
    STAGE30_11_18_REDACTED_UNSAFE_ID,
    STAGE30_11_18_REDACTION_STATUS_REDACTED,
    STAGE30_11_18_REDACTION_STATUS_VIOLATION,
    Stage30_11_18HarvestedCandidateFacts,
    Stage30_11_18ProjectionEvent,
    Stage30_11_18SessionReport,
    is_nonblank_str,
    is_safe_echo_id,
)


# The Stage 30.11.14 market-context status the committed composer requires to
# dispatch (the adapter checks the operator-asserted status equals it; the
# composer owns the freshness clock).
_MARKET_CONTEXT_PRESENT: str = "PRESENT"


# The conservative-lax ISO-8601 UTC shape charset (digits + date / time / offset
# separators). The Layer-1 shape check is intentionally laxer than the committed
# composer's parser: it rejects obvious non-timestamp garbage (alpha text) so the
# adapter can emit a precise REJECTED_INVALID_* token, while NEVER rejecting a
# value the composer would accept -- a shape-valid-but-unparseable / future / stale
# value is left to the composer's authoritative Layer-2 reason.
_ISO_ALLOWED_CHARS: str = "0123456789-:T.Z+ "


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no
# bare needle; the scan lowercases the haystack and the needles are lowercase).
# Mirrors the committed Stage 30.11.17 session scan.
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
    "public-api.birdeye" + ".so",
    "dex" + "screener.com",
    "chain" + "stack",
    "hel" + "ius",
)


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11_18HarvestAdapterError(Exception):
    """Closed-set Stage 30.11.18 harvest adapter error.

    Raised ONLY for a caller-shape failure the adapter cannot run with -- a session
    config that is not within the HARD Stage 30.11.17 session caps
    (``is_within_session_caps`` is ``False``). The adapter fails closed BEFORE
    scanning any fact, mirroring the committed session. Degraded per-fact facts
    never raise; a malformed / non-facts record fails closed to a clean
    ``REJECTED_*`` projection decision. Carries only a closed-set reason token;
    never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.18 harvest adapter error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Immutable Layer-1 projection result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_18ProjectionResult:
    """The result of projecting ONE harvested fact at Layer-1.

    Carries the closed-set ``decision``, the built committed Stage 30.11.13
    revalidation ``request`` (only on ``PROJECTED``; ``None`` otherwise -- carried
    duck-typed ``Any`` so this module need not re-spell the request type), and the
    safe-echo identity (``""`` when unreadable; ``REDACTED_UNSAFE_ID`` when present
    but unsafe -- the raw magnitudes are NEVER carried here).
    """

    decision: str
    request: Any
    candidate_id: str
    token_mint: str


# ---------------------------------------------------------------------------
# Pure safe-shape helpers
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_11_18_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the
    committed Stage 30.11.17 session ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_18_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_18_REDACTED_UNSAFE_ID


def is_iso_utc_shape(value: object) -> bool:
    """Return ``True`` iff ``value`` is shaped like an ISO-8601 UTC timestamp.

    Conservative-lax: a non-blank string of length 8..64 made ONLY of digits +
    ISO date / time / offset separators, with at least six digits. It rejects
    obvious non-timestamp garbage (alpha text) but NEVER rejects a real ISO value
    the committed composer would accept (the composer owns the authoritative parse
    + freshness check). Pure / total; never raises.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if len(stripped) < 8 or len(stripped) > 64:
        return False
    digit_count = 0
    for ch in stripped:
        if ch not in _ISO_ALLOWED_CHARS:
            return False
        if "0" <= ch <= "9":
            digit_count += 1
    return digit_count >= 6


def is_positive_decimal_text(value: object) -> bool:
    """Return ``True`` iff ``value`` is finite, strictly-positive decimal text.

    Pure / total; never raises. A non-string / blank / non-numeric / non-finite /
    non-positive value fails closed -- so a dispatch-eligible magnitude (current
    price / market cap / liquidity) is proven positive BEFORE a request is built.
    """
    if not isinstance(value, str) or value.strip() == "":
        return False
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return False
    if not parsed.is_finite():
        return False
    return parsed > 0


# ---------------------------------------------------------------------------
# Layer-1 projection: harvested facts -> committed revalidation request
# ---------------------------------------------------------------------------


def _rejected(
    decision: str, *, candidate_id: str, token_mint: str
) -> Stage30_11_18ProjectionResult:
    """Build a fail-closed Layer-1 rejection result (no request)."""
    return Stage30_11_18ProjectionResult(
        decision=decision,
        request=None,
        candidate_id=candidate_id,
        token_mint=token_mint,
    )


def project_harvested_facts_to_request(
    facts: object,
) -> Stage30_11_18ProjectionResult:
    """Project ONE harvested fact into a committed Stage 30.11.13 revalidation
    request at Layer-1 (presence / shape / positivity only).

    Pure / total; never raises. Decision precedence (top-down, first failing check
    wins) mirrors the committed composer's request-validation order so a projected
    fact is never trivially rejected at the composer for something Layer-1 could
    have caught: identity -> migration -> created-at -> market-context status ->
    market cap -> current price -> liquidity -> market-context fetched-at. A fact
    that passes every Layer-1 check yields ``PROJECTED`` with the built request;
    freshness / ATH / tier / gate stay the committed composer's authoritative
    Layer-2 reasons.
    """
    if not isinstance(facts, Stage30_11_18HarvestedCandidateFacts):
        return _rejected(
            PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD,
            candidate_id="",
            token_mint="",
        )

    safe_token_mint = _safe_echo(facts.token_mint)
    safe_candidate_id = _safe_echo(facts.candidate_id)

    # ---- Identity ----
    if not is_nonblank_str(facts.token_mint):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_safe_echo_id(facts.token_mint):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_nonblank_str(facts.candidate_id):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_safe_echo_id(facts.candidate_id):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Migration ----
    if facts.migration_confirmed is not True:
        return _rejected(
            PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_nonblank_str(facts.migration_time_utc):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_iso_utc_shape(facts.migration_time_utc):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Created-at ----
    if not is_nonblank_str(facts.created_at_utc):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_iso_utc_shape(facts.created_at_utc):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Market-context status (must be PRESENT) ----
    if facts.market_context_status != _MARKET_CONTEXT_PRESENT:
        return _rejected(
            PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Market cap (strictly positive) ----
    if not is_nonblank_str(facts.current_market_cap_usd):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_positive_decimal_text(facts.current_market_cap_usd):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Current price (strictly positive) ----
    if not is_nonblank_str(facts.current_price):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_positive_decimal_text(facts.current_price):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Liquidity (REQUIRED here; the composer fails closed without it) ----
    if not is_nonblank_str(facts.liquidity_usd):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_positive_decimal_text(facts.liquidity_usd):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- Market-context fetched-at (presence + shape ONLY; the composer owns
    #      the freshness clock -> stale / future are Layer-2 reasons) ----
    if not is_nonblank_str(facts.market_context_fetched_at_utc):
        return _rejected(
            PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )
    if not is_iso_utc_shape(facts.market_context_fetched_at_utc):
        return _rejected(
            PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT,
            candidate_id=safe_candidate_id,
            token_mint=safe_token_mint,
        )

    # ---- All Layer-1 checks passed -> build the committed request ----
    request = Stage30_11_13RevalidationRequest(
        token_mint=facts.token_mint,
        candidate_id=facts.candidate_id,
        migration_time_utc=facts.migration_time_utc,
        current_price=facts.current_price,
        current_market_cap_usd=facts.current_market_cap_usd,
        created_at_utc=facts.created_at_utc,
        migration_confirmed=True,
        symbol_or_name=facts.symbol_or_name,
        migration_source=facts.migration_source,
        liquidity_usd=facts.liquidity_usd,
        age_display=facts.age_display,
        market_context_status=facts.market_context_status,
        market_context_fetched_at_utc=facts.market_context_fetched_at_utc,
    )
    return Stage30_11_18ProjectionResult(
        decision=PROJECTION_DECISION_PROJECTED,
        request=request,
        candidate_id=safe_candidate_id,
        token_mint=safe_token_mint,
    )


# ---------------------------------------------------------------------------
# Redaction self-scan over the projection events
# ---------------------------------------------------------------------------


def _event_text_fields(event: Stage30_11_18ProjectionEvent) -> Tuple[str, ...]:
    """Return the string-typed fields of one projection event (the haystack)."""
    return (
        event.decision,
        event.candidate_id,
        event.token_mint,
        event.created_at_utc,
    )


def _projection_events_redaction_safe(
    events: Iterable[Stage30_11_18ProjectionEvent],
) -> bool:
    """Return ``True`` iff no projection-event string field carries a
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
# Public bounded harvested-facts curated session
# ---------------------------------------------------------------------------


def run_stage30_11_18_curated_session(
    facts: Iterable[object],
    *,
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
) -> Stage30_11_18SessionReport:
    """Run ONE bounded harvested-facts curated session and return a
    ``Stage30_11_18SessionReport``.

    Fail closed first: if ``config`` is not within the HARD Stage 30.11.17 session
    caps the adapter raises ``Stage30_11_18HarvestAdapterError`` BEFORE scanning
    any fact.

    Otherwise it scans AT MOST ``config.max_candidates`` facts (a single BOUNDED
    for-loop), projects each at Layer-1 (building a committed Stage 30.11.13
    request or failing closed to a ``REJECTED_*`` token), records a redaction-safe
    per-fact event, then runs the committed Stage 30.11.17 operator-curated compose
    session over the PROJECTED entries (wrapped as
    ``Stage30_11_17OperatorCuratedCandidate``) -- driving the committed composer
    (Layer-2: freshness / ATH / tier / gate) behind the shared injected dedupe
    ledger + injected FAKE recording transport client + injected fake ATH source
    transport + injected clocks (a RECORDED would-send, NEVER a real send). The
    rolled-up report carries the Layer-1 projection events + counts, the embedded
    session result (the Layer-2 outcome + mirrored composer reasons), and the
    combined redaction status.

    Pure / deterministic apart from the injected fake transport client's + injected
    ledger's recording side effects; reads no env, no clock, no network; reserves
    no real dispatch, sends no Discord, writes no file, runs no daemon / ``while``
    loop, and NEVER calls the Stage 30.11.16 real private transport guard.
    """
    if not is_within_session_caps(config):
        # Fail closed on an out-of-bounds config: scan nothing.
        raise Stage30_11_18HarvestAdapterError("INVALID_SESSION_CONFIG")

    created_at_utc = config.created_at_utc
    max_candidates = config.max_candidates

    projection_events: List[Stage30_11_18ProjectionEvent] = []
    curated: List[Stage30_11_17OperatorCuratedCandidate] = []
    facts_seen = 0
    projected = 0

    for fact in facts:
        if facts_seen >= max_candidates:
            break
        index = facts_seen
        facts_seen += 1

        result = project_harvested_facts_to_request(fact)
        projection_events.append(
            Stage30_11_18ProjectionEvent(
                index=index,
                decision=result.decision,
                candidate_id=result.candidate_id,
                token_mint=result.token_mint,
                created_at_utc=created_at_utc,
            )
        )
        if result.decision == PROJECTION_DECISION_PROJECTED:
            projected += 1
            curated.append(
                Stage30_11_17OperatorCuratedCandidate(
                    request=result.request, curated_label=None
                )
            )

    rejected_projection = facts_seen - projected

    # Optional dedupe / freshness passthroughs: only forwarded when supplied so the
    # committed session's own defaults hold otherwise.
    session_kwargs = {"ath_timeout_seconds": ath_timeout_seconds}
    if market_context_max_age_seconds is not None:
        session_kwargs["market_context_max_age_seconds"] = (
            market_context_max_age_seconds
        )
    if ttl_seconds is not None:
        session_kwargs["ttl_seconds"] = ttl_seconds

    session_result = run_stage30_11_17_operator_curated_compose_session(
        curated,
        config=config,
        ledger=ledger,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=transport_client,
        now_seconds=now_seconds,
        **session_kwargs,
    )

    # Combined redaction status: the Layer-1 events must be safe AND the embedded
    # Stage 30.11.17 session result must itself be redacted.
    events_safe = _projection_events_redaction_safe(projection_events)
    session_redacted = (
        getattr(session_result, "redaction_status", "")
        == STAGE30_11_18_REDACTION_STATUS_REDACTED
    )
    redaction_status = (
        STAGE30_11_18_REDACTION_STATUS_REDACTED
        if (events_safe and session_redacted)
        else STAGE30_11_18_REDACTION_STATUS_VIOLATION
    )

    return Stage30_11_18SessionReport(
        projection_events=tuple(projection_events),
        facts_seen=facts_seen,
        projected=projected,
        rejected_projection=rejected_projection,
        session_result=session_result,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_18HarvestAdapterError",
    "Stage30_11_18ProjectionResult",
    "is_iso_utc_shape",
    "is_positive_decimal_text",
    "project_harvested_facts_to_request",
    "run_stage30_11_18_curated_session",
)
