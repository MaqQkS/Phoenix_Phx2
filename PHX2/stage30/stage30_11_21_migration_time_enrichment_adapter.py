"""Stage 30.11.21 migration-time enrichment adapter.

The pure, bounded, fail-closed ADAPTER that closes the LAST hand-fed harvested-facts
blocker the Stage 30.11.18 contract exposed (``REJECTED_MIGRATION_NOT_CONFIRMED`` /
``REJECTED_MISSING_MIGRATION_TIME_UTC`` / ``REJECTED_INVALID_MIGRATION_TIME_UTC``) --
by REUSING the already-committed Stage 30.11.8 migration-confirmation authority (it
builds NO new fetcher and COPIES no bare timestamp):

    an iterable of base Stage30_11_18HarvestedCandidateFacts
      -> for each base fact (a single BOUNDED for-loop; AT MOST ``max_candidates``
         scanned):
           -> Layer-0 enrichment: resolve the candidate's migration verdict through
              the committed Stage 30.11.8 ``resolve_candidate_migration(base,
              evidence_source)`` over the INJECTED, duck-typed Stage 30.11.9
              ``lookup_migration_evidence`` source; ONLY on a CONFIRMED resolution
              (redaction-SAFE + on-chain COMPLETE + not-stale + strict trailing-Z
              calendar-valid anchor -- the committed confirmation owns every one of
              those checks) overwrite ``migration_time_utc`` (from the confirmed
              ``migration_event_time_utc``), set ``migration_confirmed=True``, and
              write a safe-gated ``migration_source`` (from the confirmed
              ``source_ref``, or ``None`` if unsafe) on a COPY of the fact via
              dataclasses.replace (``ENRICHED``); otherwise fail closed to a
              closed-set ``SKIPPED_*`` token that MIRRORS the committed Stage 30.11.8
              fail reason and leave the fact UN-enriched + NOT forwarded (no silent
              pass-through)
           -> a redaction-safe per-fact ``Stage30_11_21MigrationEnrichmentEvent``
      -> the ENRICHED facts (only) run through the committed Stage 30.11.20
         enrichment session (and behind it the Stage 30.11.19 / 30.11.18 / 30.11.17
         sessions) over the injected FAKE recording transport client (a RECORDED
         would-send, NEVER a real send)
      -> a rolled-up redaction-safe ``Stage30_11_21MigrationEnrichmentSessionReport``
         (the Layer-0 events + counts + the EMBEDDED Stage 30.11.20 report + the
         combined redaction status -- ONE combined nested report)

``current_price`` and the Stage 30.11.19 market-context bundle
(``current_market_cap_usd`` / ``liquidity_usd`` / ``market_context_fetched_at_utc``
/ ``market_context_status``) are carried through UNCHANGED (separate seams).
``age_display`` is carried through UNCHANGED and is NEVER derived here -- deriving an
age would need ``now - migration_time`` clock arithmetic, and this slice imports no
clock. The migration verdict + anchor are the committed Stage 30.11.8 confirmation's
to decide; this adapter NEVER re-implements the COMPLETE / SAFE / staleness / anchor
checks, NEVER confirms from a bare timestamp, and NEVER promotes an unconfirmed
reading. The evidence source is INJECTED and read DUCK-TYPED (the committed Stage
30.11.8 confirmation calls only ``evidence_source.lookup_migration_evidence(...)``);
committed Stage 30.11.21 constructs NO real provider transport, imports NO Stage
30.11.9 source module, imports NO Stage 30.11.11 migration-anchored ATH source, and
reads NO env. The real Stage 29.5 migration evidence (the operator wraps the
committed Stage 29.5 reader behind the injected Stage 30.11.9 provider seam) and the
controlled live send remain a SEPARATE, ceremony-injected, operator-authorized step
this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``). The confirmation + anchor validation
    REUSE the committed Stage 30.11.8 authority (no decimal / datetime / re).
  * Imports ONLY the committed Stage 30.11.20 enrichment adapter (the session the
    enriched facts run through), the committed Stage 30.11.8 migration-confirmation
    adapter (``resolve_candidate_migration``) + models (the fail-reason tokens it
    maps), the committed Stage 30.11.18 facts models (the facts type), the committed
    Stage 30.11.17 models (session config + cap validator), and the Stage 30.11.21
    models sibling. No other PHX2 module; no Stage 21-29 / Stage 30.11.9 source /
    Stage 30.11.11 ATH source / Stage 30.11.16 real-send guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` / ``re`` import; every timestamp /
    clock is caller-injected / evidence-carried.
  * No filesystem-write surface (persistence is the injected ledger's job).
  * No module-level Call node (no implicit I/O at import time; the module-level
    reason map is a Dict literal, not a Call).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
    is_within_session_caps,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_adapter import (
    resolve_candidate_migration,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_REASON_BLANK_CANDIDATE_MINT,
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
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_adapter import (
    run_stage30_11_20_price_enriched_session,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_models import (
    MIGRATION_ENRICHMENT_DECISION_ENRICHED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION,
    STAGE30_11_21_REDACTED_UNSAFE_ID,
    STAGE30_11_21_REDACTION_STATUS_REDACTED,
    STAGE30_11_21_REDACTION_STATUS_VIOLATION,
    Stage30_11_21MigrationEnrichmentEvent,
    Stage30_11_21MigrationEnrichmentResult,
    Stage30_11_21MigrationEnrichmentSessionReport,
    is_nonblank_str,
    is_safe_echo_id,
)


# ---------------------------------------------------------------------------
# Fail-closed reason map: committed Stage 30.11.8 reason -> Stage 30.11.21 SKIPPED
# ---------------------------------------------------------------------------
#
# A pure Dict LITERAL (not a Call -> no top-level Call node). Every committed Stage
# 30.11.8 fail-closed confirmation reason maps to the Stage 30.11.21 ``SKIPPED_*``
# token that carries it VERBATIM after the ``SKIPPED_`` prefix, so the session
# report surfaces the PRECISE confirmation cause. An unrecognized / missing reason
# (which the committed confirmation never emits for a fail-closed resolution) falls
# through to ``SKIPPED_UNKNOWN_MIGRATION`` -- the conservative bucket.
_REASON_TO_SKIPPED: Dict[str, str] = {
    CONFIRM_REASON_BLANK_CANDIDATE_MINT: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_BLANK_CANDIDATE_MINT
    ),
    CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE
    ),
    CONFIRM_REASON_EVIDENCE_MINT_MISMATCH: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_MINT_MISMATCH
    ),
    CONFIRM_REASON_REDACTION_UNSAFE: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_REDACTION_UNSAFE
    ),
    CONFIRM_REASON_UNKNOWN_MIGRATION: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION
    ),
    CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_PARTIAL_MIGRATION_UNVERIFIED
    ),
    CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_EVIDENCE_REPORTS_NO_MIGRATION
    ),
    CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_CONTRADICTORY_MIGRATION_EVIDENCE
    ),
    CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_EVIDENCE
    ),
    CONFIRM_REASON_STALE_MIGRATION_EVIDENCE: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE
    ),
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR: (
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR
    ),
}


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no
# bare needle). Mirrors the committed Stage 30.11.20 / 30.11.19 scan.
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


class Stage30_11_21MigrationTimeEnrichmentError(Exception):
    """Closed-set Stage 30.11.21 migration-time enrichment error.

    Raised ONLY for a caller-shape failure the runner cannot run with -- a session
    config that is not within the HARD Stage 30.11.17 session caps
    (``is_within_session_caps`` is ``False``). The runner fails closed BEFORE
    scanning any base fact, mirroring the committed Stage 30.11.20 session. Degraded
    per-fact base facts never raise; a non-facts base or an unconfirmed migration
    fails closed to a clean ``SKIPPED_*`` decision. Carries only a closed-set reason
    token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.21 migration-time enrichment error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure safe-shape helpers
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_11_21_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the
    committed Stage 30.11.20 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_21_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_21_REDACTED_UNSAFE_ID


def _safe_migration_source(value: object) -> Optional[str]:
    """Return ``value`` as a safe ``migration_source`` provenance ref, or ``None``.

    The committed Stage 30.11.8 confirmation carries ``source_ref`` VERBATIM (only
    coercing a non-string to ``None``); this gate additionally drops a present-but-
    unsafe ref (one carrying a url / scheme / control char -- anything ``is_safe_echo_id``
    rejects) to ``None`` rather than write it onto the facts, so an out-of-repo
    provider can never smuggle a host into the migration provenance. ``None`` / a
    non-safe token -> ``None``; a safe-echo token -> itself. Pure / total.
    """
    return value if is_safe_echo_id(value) else None


# ---------------------------------------------------------------------------
# Layer-0 enrichment: base facts + confirmed resolution -> enriched facts
# ---------------------------------------------------------------------------


def _skipped(decision: str) -> Stage30_11_21MigrationEnrichmentResult:
    """Build a fail-closed Layer-0 skip result (no enriched facts)."""
    return Stage30_11_21MigrationEnrichmentResult(
        decision=decision, enriched_facts=None
    )


def enrich_facts_with_migration_time(
    base_facts: object,
    *,
    evidence_source: object,
) -> Stage30_11_21MigrationEnrichmentResult:
    """Enrich ONE base fact's migration fields from a CONFIRMED Stage 30.11.8
    resolution over the injected evidence source.

    Pure / total; never raises. Decision ladder (top-down, first failing check
    wins): non-facts base -> resolve the migration verdict via the committed Stage
    30.11.8 ``resolve_candidate_migration`` -> on an UNCONFIRMED resolution, fail
    closed to the ``SKIPPED_*`` token that mirrors the committed Stage 30.11.8 fail
    reason -> on a CONFIRMED resolution with a (defensively re-checked) non-blank
    anchor, ``ENRICHED``. On ``ENRICHED`` it returns a COPY of the base fact (via
    ``dataclasses.replace``) with ONLY the three migration fields overwritten
    (``migration_time_utc`` from the confirmed ``migration_event_time_utc``;
    ``migration_confirmed`` set to ``True``; ``migration_source`` set to the
    safe-gated ``source_ref`` or ``None``); ``current_price`` + the Stage 30.11.19
    market-context bundle + ``age_display`` + every other field are carried through
    UNCHANGED. The committed Stage 30.11.8 confirmation owns every migration check
    (redaction-SAFE / on-chain COMPLETE / staleness / strict trailing-Z anchor); this
    adapter re-implements none of them and confirms from no bare timestamp. On any
    skip the base fact is NEVER mutated and ``enriched_facts`` is ``None`` (the
    runner does not forward it).
    """
    # ---- Base must be a committed facts record ----
    if not isinstance(base_facts, Stage30_11_18HarvestedCandidateFacts):
        return _skipped(MIGRATION_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS)

    # ---- Resolve the migration verdict through the committed Stage 30.11.8
    #      confirmation authority (never raises; always returns a resolution) ----
    resolution = resolve_candidate_migration(base_facts, evidence_source)

    # ---- Unconfirmed -> mirror the committed Stage 30.11.8 fail reason ----
    if resolution.confirmed is not True:
        decision = _REASON_TO_SKIPPED.get(
            resolution.reason,
            MIGRATION_ENRICHMENT_DECISION_SKIPPED_UNKNOWN_MIGRATION,
        )
        return _skipped(decision)

    # ---- Confirmed: defensively re-check the bound anchor is non-blank (the
    #      committed confirmation guarantees a strict trailing-Z anchor on confirm;
    #      this guard keeps the Layer-0 ladder total against a degenerate carrier) --
    anchor = resolution.migration_event_time_utc
    if not is_nonblank_str(anchor):
        return _skipped(
            MIGRATION_ENRICHMENT_DECISION_SKIPPED_INVALID_MIGRATION_ANCHOR
        )

    # ---- All checks passed -> overwrite ONLY the three migration fields ----
    enriched = replace(
        base_facts,
        migration_time_utc=anchor,
        migration_confirmed=True,
        migration_source=_safe_migration_source(resolution.source_ref),
    )
    return Stage30_11_21MigrationEnrichmentResult(
        decision=MIGRATION_ENRICHMENT_DECISION_ENRICHED,
        enriched_facts=enriched,
    )


# ---------------------------------------------------------------------------
# Redaction self-scan over the enrichment events
# ---------------------------------------------------------------------------


def _event_text_fields(
    event: Stage30_11_21MigrationEnrichmentEvent,
) -> Tuple[str, ...]:
    """Return the string-typed fields of one enrichment event (the haystack)."""
    return (
        event.decision,
        event.candidate_id,
        event.token_mint,
        event.created_at_utc,
    )


def _enrichment_events_redaction_safe(
    events: Iterable[Stage30_11_21MigrationEnrichmentEvent],
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


def run_stage30_11_21_migration_time_enriched_session(
    base_facts: Iterable[object],
    *,
    evidence_source: object,
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
) -> Stage30_11_21MigrationEnrichmentSessionReport:
    """Run ONE bounded migration-time enrichment session and return a
    ``Stage30_11_21MigrationEnrichmentSessionReport``.

    Fail closed first: if ``config`` is not within the HARD Stage 30.11.17 session
    caps the runner raises ``Stage30_11_21MigrationTimeEnrichmentError`` BEFORE
    scanning any base fact.

    Otherwise it scans AT MOST ``config.max_candidates`` base facts (a single
    BOUNDED for-loop), enriches each at Layer-0 (overwriting the three migration
    fields from a CONFIRMED Stage 30.11.8 resolution or failing closed to a
    ``SKIPPED_*`` token), records a redaction-safe per-fact event, then runs the
    committed Stage 30.11.20 enrichment session over the ENRICHED facts ONLY
    (skipped facts are NOT forwarded) -- driving behind it the Stage 30.11.19
    market-context enrichment + the Stage 30.11.18 projection + the Stage 30.11.17
    compose/dedupe session over the injected price source + market-context source +
    dedupe ledger + injected FAKE recording transport client + injected fake ATH
    source transport + injected clocks (a RECORDED would-send, NEVER a real send).
    The rolled-up report carries the Layer-0 enrichment events + counts, the embedded
    Stage 30.11.20 report (ONE combined nested report), and the combined redaction
    status.

    Pure / deterministic apart from the injected sources' reads + the injected fake
    transport client's + ledger's recording side effects; reads no env, no clock, no
    network; constructs no provider transport, reserves no real dispatch, sends no
    Discord, writes no file, runs no daemon / ``while`` loop, and NEVER calls the
    Stage 30.11.16 real private transport guard.
    """
    if not is_within_session_caps(config):
        # Fail closed on an out-of-bounds config: scan nothing.
        raise Stage30_11_21MigrationTimeEnrichmentError("INVALID_SESSION_CONFIG")

    created_at_utc = config.created_at_utc
    max_candidates = config.max_candidates

    enrichment_events: List[Stage30_11_21MigrationEnrichmentEvent] = []
    enriched_facts: List[Any] = []
    facts_seen = 0
    enriched = 0

    for base in base_facts:
        if facts_seen >= max_candidates:
            break
        index = facts_seen
        facts_seen += 1

        result = enrich_facts_with_migration_time(
            base, evidence_source=evidence_source
        )
        enrichment_events.append(
            Stage30_11_21MigrationEnrichmentEvent(
                index=index,
                decision=result.decision,
                candidate_id=_safe_echo(getattr(base, "candidate_id", None)),
                token_mint=_safe_echo(getattr(base, "token_mint", None)),
                created_at_utc=created_at_utc,
            )
        )
        if result.decision == MIGRATION_ENRICHMENT_DECISION_ENRICHED:
            enriched += 1
            enriched_facts.append(result.enriched_facts)

    skipped = facts_seen - enriched

    # Run the committed Stage 30.11.20 session over the ENRICHED facts ONLY.
    downstream_report = run_stage30_11_20_price_enriched_session(
        enriched_facts,
        price_source=price_source,
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
    # Stage 30.11.20 report must itself be redacted.
    events_safe = _enrichment_events_redaction_safe(enrichment_events)
    downstream_redacted = (
        getattr(downstream_report, "redaction_status", "")
        == STAGE30_11_21_REDACTION_STATUS_REDACTED
    )
    redaction_status = (
        STAGE30_11_21_REDACTION_STATUS_REDACTED
        if (events_safe and downstream_redacted)
        else STAGE30_11_21_REDACTION_STATUS_VIOLATION
    )

    return Stage30_11_21MigrationEnrichmentSessionReport(
        enrichment_events=tuple(enrichment_events),
        facts_seen=facts_seen,
        enriched=enriched,
        skipped=skipped,
        downstream_report=downstream_report,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_21MigrationTimeEnrichmentError",
    "enrich_facts_with_migration_time",
    "run_stage30_11_21_migration_time_enriched_session",
)
