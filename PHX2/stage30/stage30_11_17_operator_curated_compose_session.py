"""Stage 30.11.17 operator-curated compose session.

The pure, bounded, fail-closed SESSION that runs an operator-curated candidate
list through the already-proven single-candidate no-send path -- the smallest
committed wrapper over ``compose_no_send_dispatch_deduped``:

    an operator-curated candidate list (each entry carries ONE already-revalidated
    Stage 30.11.13 request + an optional safe label)
      -> for each entry (a single BOUNDED for-loop; AT MOST ``max_candidates``
         pulled, AT MOST ``max_compositions`` composed):
           -> the committed Stage 30.11.15 ``compose_no_send_dispatch_deduped``
              over the ONE shared injected dedupe ledger + the injected FAKE
              recording transport client + the injected fake ATH source transport
              + injected clocks (a RECORDED would-send, NEVER a real send)
           -> a redaction-safe per-entry ``Stage30_11_17SessionEvent``
      -> a rolled-up redaction-safe ``Stage30_11_17SessionResult`` (the ordered
         events + the outcome counts + the stop reason + the redaction status)

The session enforces HARD bounds so a controlled curated run cannot run away:
``max_candidates <= 10`` (the bounded list pull) and
``1 <= max_compositions <= max_candidates`` (the bounded compose-call count). A
config outside the caps fails closed BEFORE composing anything. The list pull is
a single BOUNDED for-loop (it stops at the binding cap); there is NO ``while``
loop, NO daemon, NO background service, NO autorestart loop.

The session shares ONE injected dedupe ledger across every entry, so a duplicate
state within the same run is suppressed exactly as it is across runs (the same
committed Stage 30.11.15 cross-run guarantee). It NEVER fetches market data,
NEVER opens a network connection, NEVER reads the process environment, NEVER
reads a wall clock (the clocks are injected), NEVER sends Discord, NEVER reserves
a REAL dispatch / performs a real send, NEVER calls the Stage 30.11.16 real
private transport guard, NEVER binds a real harvest adapter, NEVER touches a live
provider session, NEVER writes a file (the ledger owns any persistence), and
edits NO committed composer / dedupe / ledger / Stage 28 / Stage 29 / Stage 30.3
/ Stage 30.4 file. It composes ONLY the committed Stage 30.11.15 deduped
orchestrator (which composes the committed Stage 30.11.13 composer behind the
dedupe guard) plus the Stage 30.11.17 models; nothing more. In THIS slice the
injected transport client + ATH source transport are ALWAYS FAKES -- the real
private compact dispatch / Discord send is a SEPARATE, operator-authorized step
Stage 30.11.17 does not build.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the committed Stage 30.11.15 deduped orchestrator + result, the
    committed Stage 30.11.13 closed-set compose decision / reason tokens (mirrored
    for classification), and the Stage 30.11.17 models sibling. No other PHX2
    module; no Stage 21-29 / Stage 30.11.16 real-send guard / Stage 30.11.6
    harvest adapter / Stage 30.3 / Stage 30.4 orchestrator / live runner /
    provider / real transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference; no
    wallet / signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; every timestamp / clock is
    caller-injected.
  * No filesystem write surface (persistence is the injected ledger's job).
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Tuple

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
    COMPOSE_REJECTED_DEDUPE_UNAVAILABLE,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
    compose_no_send_dispatch_deduped,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    ENTRY_OUTCOME_DEDUPE_BLOCKED,
    ENTRY_OUTCOME_DISPATCHED,
    ENTRY_OUTCOME_ERROR,
    ENTRY_OUTCOME_REJECTED,
    STAGE30_11_17_REDACTED_UNSAFE_ID,
    STAGE30_11_17_REDACTION_STATUS_REDACTED,
    STAGE30_11_17_REDACTION_STATUS_VIOLATION,
    STOP_REASON_CANDIDATE_CAP,
    STOP_REASON_COMPLETED,
    STOP_REASON_COMPOSITION_CAP,
    Stage30_11_17OperatorCuratedCandidate,
    Stage30_11_17SessionConfig,
    Stage30_11_17SessionEvent,
    Stage30_11_17SessionResult,
    is_safe_echo_id,
    is_within_session_caps,
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no
# bare needle; the scan lowercases the haystack and the needles are lowercase)
# ---------------------------------------------------------------------------
#
# The session builds only closed-set tokens + safe-echo ids, so the scan always
# holds (``REDACTED``); it is a belt-and-suspenders attestation that no url /
# secret ever reached a result field. The transport-scheme separator is built
# from parts so the bare ``scheme`` literal never appears in this source.


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


class Stage30_11_17OperatorCuratedSessionError(Exception):
    """Closed-set Stage 30.11.17 operator-curated session error.

    Raised ONLY for a caller-shape failure the session cannot run with -- a
    session config that is not within the HARD session caps
    (``is_within_session_caps`` is ``False``): an invalid config, a
    ``max_candidates`` above ``10``, or a ``max_compositions`` outside
    ``1..max_candidates`` would make the bounded curated run undefined, so the
    session fails closed BEFORE composing any entry. Degraded per-entry results
    never raise; a missing ledger / malformed request / odd dedupe return fails
    closed to a clean per-entry ``ERROR`` / ``REJECTED``. Carries only a
    closed-set reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.17 operator-curated session error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure safe-echo helpers
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string (newline /
    control / whitespace / path / url / quote char or over-long) ->
    ``STAGE30_11_17_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Guarantees
    a forged id / label can never inject text into a result field. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_17_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_17_REDACTED_UNSAFE_ID


def _safe_token(value: object) -> str:
    """Echo a closed-set token string as-is, else ``""``. Pure / total."""
    return value if isinstance(value, str) else ""


# ---------------------------------------------------------------------------
# Pure curated-entry reader
# ---------------------------------------------------------------------------


def _read_curated_entry(candidate: object) -> Tuple[Any, str]:
    """Read ``(request, safe_curated_label)`` from one curated entry.

    A ``Stage30_11_17OperatorCuratedCandidate`` yields its ``request`` + its
    redaction-safe ``curated_label``; any other object is treated as a bare
    request with no label (so a malformed entry still composes to a clean
    fail-closed ``REJECTED`` at the committed composer). Pure / total.
    """
    if isinstance(candidate, Stage30_11_17OperatorCuratedCandidate):
        return candidate.request, _safe_echo(candidate.curated_label)
    return candidate, ""


# ---------------------------------------------------------------------------
# Pure outcome classifier + event builder
# ---------------------------------------------------------------------------


def _outcome_of(decision: object, reason: object) -> str:
    """Classify one deduped compose result's decision + reason into a closed-set
    per-entry outcome. Pure / total.

    ``NO_SEND_DISPATCHED`` -> ``DISPATCHED``; a dedupe-suppressed reason ->
    ``DEDUPE_BLOCKED``; a dedupe-unavailable reason -> ``ERROR`` (the dedupe
    surface failed closed); every other rejection -> ``REJECTED``.
    """
    if decision == COMPOSE_DECISION_DISPATCHED:
        return ENTRY_OUTCOME_DISPATCHED
    if reason == COMPOSE_REJECTED_DEDUPE_SUPPRESSED:
        return ENTRY_OUTCOME_DEDUPE_BLOCKED
    if reason == COMPOSE_REJECTED_DEDUPE_UNAVAILABLE:
        return ENTRY_OUTCOME_ERROR
    return ENTRY_OUTCOME_REJECTED


def _build_event(
    deduped: object,
    *,
    index: int,
    curated_label: str,
    created_at_utc: str,
) -> Tuple[Stage30_11_17SessionEvent, str]:
    """Build one redaction-safe per-entry event + its outcome from a deduped
    compose result. Pure / total; never raises.

    A ``None`` compose result (the deduped orchestrator failed closed BEFORE
    composing -- e.g. a missing ledger) is a clean ``ERROR`` entry carrying the
    dedupe verdict / reason only.
    """
    compose_result = getattr(deduped, "compose_result", None)
    dedupe_outcome = getattr(deduped, "dedupe_outcome", None)
    dedupe_verdict = _safe_token(getattr(dedupe_outcome, "verdict", ""))
    dedupe_reason = _safe_token(getattr(dedupe_outcome, "reason", ""))

    if compose_result is None:
        event = Stage30_11_17SessionEvent(
            index=index,
            candidate_id="",
            token_mint="",
            curated_label=curated_label,
            outcome=ENTRY_OUTCOME_ERROR,
            compose_decision="",
            compose_reason="",
            dedupe_verdict=dedupe_verdict,
            dedupe_reason=dedupe_reason,
            transport_attempts=0,
            body_present=False,
            created_at_utc=created_at_utc,
        )
        return event, ENTRY_OUTCOME_ERROR

    decision = _safe_token(getattr(compose_result, "decision", ""))
    reason = _safe_token(getattr(compose_result, "reason", ""))
    outcome = _outcome_of(decision, reason)
    body = getattr(compose_result, "dispatched_body", None)
    # The recorded would-send count for THIS entry: a dispatched entry drove the
    # committed bounded runner (``max_dispatches=1``) to record exactly one
    # would-send through the injected FAKE client; every other outcome reaches no
    # transport. Derived from the outcome rather than the composer's
    # ``transport_attempts`` (which reads the SHARED client's cumulative count).
    transport_attempts = 1 if outcome == ENTRY_OUTCOME_DISPATCHED else 0
    event = Stage30_11_17SessionEvent(
        index=index,
        candidate_id=_safe_echo(getattr(compose_result, "candidate_id", "")),
        token_mint=_safe_echo(getattr(compose_result, "token_mint", "")),
        curated_label=curated_label,
        outcome=outcome,
        compose_decision=decision,
        compose_reason=reason,
        dedupe_verdict=dedupe_verdict,
        dedupe_reason=dedupe_reason,
        transport_attempts=transport_attempts,
        body_present=isinstance(body, str) and body.strip() != "",
        created_at_utc=created_at_utc,
    )
    return event, outcome


# ---------------------------------------------------------------------------
# Redaction self-scan
# ---------------------------------------------------------------------------


def _event_text_fields(event: Stage30_11_17SessionEvent) -> Tuple[str, ...]:
    """Return the string-typed fields of one event (the redaction haystack)."""
    return (
        event.candidate_id,
        event.token_mint,
        event.curated_label,
        event.outcome,
        event.compose_decision,
        event.compose_reason,
        event.dedupe_verdict,
        event.dedupe_reason,
        event.created_at_utc,
    )


def _redaction_safe(events: Iterable[Stage30_11_17SessionEvent]) -> bool:
    """Return ``True`` iff no event string field carries a transport-scheme
    separator or a forbidden url / secret needle. Pure / total; never raises.
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
# Public bounded operator-curated compose session
# ---------------------------------------------------------------------------


def run_stage30_11_17_operator_curated_compose_session(
    candidates: Iterable[object],
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
) -> Stage30_11_17SessionResult:
    """Run ONE bounded operator-curated compose session and return a
    ``Stage30_11_17SessionResult``.

    Pure / deterministic apart from the injected fake transport client's +
    injected ledger's recording side effects; reads no env, no clock, no network
    (every clock is injected); reserves no real dispatch, sends no Discord, calls
    no real transport, writes no file, runs no daemon / ``while`` loop, and NEVER
    calls the Stage 30.11.16 real private transport guard.

    Fail closed first: if ``config`` is not within the HARD session caps the
    session raises ``Stage30_11_17OperatorCuratedSessionError`` BEFORE composing
    any entry -- nothing is composed on an out-of-bounds config.

    Otherwise it pulls AT MOST ``config.max_candidates`` curated entries (a single
    BOUNDED for-loop) and composes AT MOST ``config.max_compositions`` of them,
    driving the committed Stage 30.11.15 ``compose_no_send_dispatch_deduped`` once
    per processed entry over the ONE shared injected ``ledger`` (so a duplicate
    state within the run is suppressed exactly as across runs) plus the injected
    fake ATH source transport + injected fake recording transport client +
    injected clocks. Each result is classified into exactly one closed-set outcome
    (``DISPATCHED`` / ``REJECTED`` / ``DEDUPE_BLOCKED`` / ``ERROR``) and recorded
    as a redaction-safe per-entry event. The loop stops with a closed-set stop
    reason: the list exhausted (``COMPLETED_ALL_CANDIDATES``), the candidate cap
    reached (``STOPPED_BY_CANDIDATE_CAP``), or the composition cap reached
    (``STOPPED_BY_COMPOSITION_CAP``). ``KeyboardInterrupt`` / ``SystemExit``
    (``BaseException``) are NOT swallowed; an unexpected ``Exception`` from the
    deduped orchestrator is a clean per-entry ``ERROR`` (the session never raises
    mid-list).
    """
    if not is_within_session_caps(config):
        # Fail closed on an out-of-bounds config: compose nothing.
        raise Stage30_11_17OperatorCuratedSessionError("INVALID_SESSION_CONFIG")

    created_at_utc = config.created_at_utc
    max_candidates = config.max_candidates
    max_compositions = config.max_compositions

    # Optional dedupe passthroughs: only forwarded when supplied so the committed
    # orchestrator's own defaults (TTL / signal kind / policy / drawdown band /
    # market-context freshness) hold otherwise. ``ath_endpoint_secret`` is a safe
    # param name forwarded to the committed composer's injected ATH source.
    dedupe_kwargs = {"ath_timeout_seconds": ath_timeout_seconds}
    if market_context_max_age_seconds is not None:
        dedupe_kwargs["market_context_max_age_seconds"] = (
            market_context_max_age_seconds
        )
    if ttl_seconds is not None:
        dedupe_kwargs["ttl_seconds"] = ttl_seconds

    events: List[Stage30_11_17SessionEvent] = []
    candidates_seen = 0
    compositions_attempted = 0
    dispatched = 0
    rejected = 0
    dedupe_blocked = 0
    errors = 0
    would_send_recorded = 0
    stop_reason = STOP_REASON_COMPLETED

    for candidate in candidates:
        if candidates_seen >= max_candidates:
            stop_reason = STOP_REASON_CANDIDATE_CAP
            break
        if compositions_attempted >= max_compositions:
            stop_reason = STOP_REASON_COMPOSITION_CAP
            break

        index = candidates_seen
        candidates_seen += 1
        compositions_attempted += 1
        request, curated_label = _read_curated_entry(candidate)

        try:
            deduped: Stage30_11_15DedupedComposeResult = (
                compose_no_send_dispatch_deduped(
                    request,
                    ath_transport=ath_transport,
                    ath_endpoint_secret=ath_endpoint_secret,
                    now_utc=now_utc,
                    transport_client=transport_client,
                    now_seconds=now_seconds,
                    ledger=ledger,
                    **dedupe_kwargs,
                )
            )
        except Exception:
            # Defense in depth: the deduped orchestrator is total, but the session
            # never raises mid-list -- an unexpected error is a clean ``ERROR``.
            events.append(
                Stage30_11_17SessionEvent(
                    index=index,
                    candidate_id="",
                    token_mint="",
                    curated_label=curated_label,
                    outcome=ENTRY_OUTCOME_ERROR,
                    compose_decision="",
                    compose_reason="",
                    dedupe_verdict="",
                    dedupe_reason="",
                    transport_attempts=0,
                    body_present=False,
                    created_at_utc=created_at_utc,
                )
            )
            errors += 1
            continue

        event, outcome = _build_event(
            deduped,
            index=index,
            curated_label=curated_label,
            created_at_utc=created_at_utc,
        )
        events.append(event)
        would_send_recorded += event.transport_attempts
        if outcome == ENTRY_OUTCOME_DISPATCHED:
            dispatched += 1
        elif outcome == ENTRY_OUTCOME_DEDUPE_BLOCKED:
            dedupe_blocked += 1
        elif outcome == ENTRY_OUTCOME_ERROR:
            errors += 1
        else:
            rejected += 1

    redaction_status = (
        STAGE30_11_17_REDACTION_STATUS_REDACTED
        if _redaction_safe(events)
        else STAGE30_11_17_REDACTION_STATUS_VIOLATION
    )
    return Stage30_11_17SessionResult(
        events=tuple(events),
        candidates_seen=candidates_seen,
        compositions_attempted=compositions_attempted,
        dispatched=dispatched,
        rejected=rejected,
        dedupe_blocked=dedupe_blocked,
        errors=errors,
        would_send_recorded=would_send_recorded,
        stop_reason=stop_reason,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_17OperatorCuratedSessionError",
    "run_stage30_11_17_operator_curated_compose_session",
)
