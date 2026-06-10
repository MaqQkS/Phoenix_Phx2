"""Stage 30.11.22 real-fed dry-run adapter (bridge + bounded dry-run wrapper).

The pure, bounded, fail-closed ADAPTER that closes the LAST committed gap before an
operator-authorized real-fed dry-run ceremony can run: the committed Stage 30.11.6
harvest seam emits a ``Stage30_11_6CandidateProjection`` tuple, but the committed
enrichment chain consumes a ``Stage30_11_18HarvestedCandidateFacts`` base fact -- a
DIFFERENT shape. Nothing committed maps the one onto the other, so a ceremony had to
hand-build the correctness-critical base fact in out-of-repo glue. This slice ships
that mapping IN-repo + a thin orchestration wrapper:

    a committed Stage 30.11.6 harvest over an INJECTED assembler + record flattener +
    bounded live event source
      -> the Stage 30.11.22 BRIDGE: each harvested projection -> a base
         ``Stage30_11_18HarvestedCandidateFacts`` carrying the REAL ``token_mint`` +
         run-scoped ``candidate_id`` VERBATIM and a sentinel on every field the
         enrichment fills (overwritten on enrich, dropped on skip -- never reaching
         the composer)
      -> the committed Stage 30.11.21 migration-time enriched session (and behind it
         the Stage 30.11.20 price / 30.11.19 market-context / 30.11.18 projection /
         30.11.17 compose-dedupe sessions) over the INJECTED evidence / price /
         market-context sources + ATH source transport + clocks + the injected FAKE
         recording transport client + the injected in-memory dedupe ledger (a
         RECORDED would-send, NEVER a real send)
      -> a rolled-up redaction-safe ``Stage30_11_22RealFedDryRunReport`` (the harvest
         counts + the bridge base-facts-built count + the Layer-0 / Layer-1 / Layer-2
         counts + skip histograms + the EMBEDDED Stage 30.11.21 report + the
         no-real-send attestation + the combined redaction status)

The dry-run defaults are SAFE BY CONSTRUCTION: an absent ``transport_client``
defaults to the committed Stage 30.11.5 recording FAKE client (records a would-send,
opens no socket, imports no real transport), and an absent ``ledger`` defaults to the
committed Stage 30.11.15 IN-MEMORY ledger (no I/O -- it CANNOT touch the durable
one-send ledger). The wrapper NEVER fetches market data, NEVER opens a network
connection, NEVER reads the process environment, NEVER reads a wall clock (every
clock is injected), NEVER sends a private message, NEVER reserves a REAL dispatch /
performs a real send, NEVER calls the Stage 30.11.16 real private transport guard,
NEVER constructs a real provider transport (every provider source is INJECTED), NEVER
writes a file, runs NO daemon / ``while`` loop, and edits NO committed harvest /
enrichment / composer / dedupe / ledger / renderer / tier-band file. The real live
event source + provider sources (the operator constructs them at the ceremony) and
the controlled live send remain a SEPARATE, ceremony-injected, operator-authorized
step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.6 harvest adapter + candidate-source
    models, the committed Stage 30.11.18 facts models (the base-fact type the bridge
    builds), the committed Stage 30.11.21 migration-time enrichment adapter (the
    chain entrypoint), the committed Stage 30.11.17 session config + cap validator +
    default builder, the committed Stage 30.11.15 in-memory ledger (the dry-run
    default), the committed Stage 30.11.5 recording fake transport client (the
    dry-run default), and the Stage 30.11.22 models sibling. No other PHX2 module; no
    Stage 21-29 / Stage 30.4.3 source / Stage 30.11.16 real-send guard / real
    transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; every timestamp / clock is
    caller-injected.
  * No filesystem-write surface (persistence is the injected ledger's job; the
    default in-memory ledger persists nothing).
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_6_candidate_harvest_adapter import (
    harvest_live_candidates,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    STAGE30_11_6_DEFAULT_MAX_HARVEST,
    Stage30_11_6CandidateProjection,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
    default_session_config,
    is_within_session_caps,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_adapter import (
    run_stage30_11_21_migration_time_enriched_session,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    STAGE30_11_22_PENDING_ENRICHMENT,
    STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS,
    STAGE30_11_22_REDACTED_UNSAFE_ID,
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
    STAGE30_11_22_REDACTION_STATUS_VIOLATION,
    Stage30_11_22NoRealSendAttestation,
    Stage30_11_22RealFedDryRunReport,
    is_safe_echo_id,
)


# The SKIPPED token prefix the per-stage skip histograms count (every Stage
# 30.11.21 / 30.11.20 / 30.11.19 Layer-0 skip token starts with it; the single
# enriched pass token does not). The adapter never imports the enrichment
# vocabularies -- it counts the decision strings the embedded report carries.
_SKIPPED_PREFIX: str = "SKIPPED"


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no
# bare needle). Mirrors the committed Stage 30.11.21 / 30.11.20 scan.
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


class Stage30_11_22RealFedDryRunError(Exception):
    """Closed-set Stage 30.11.22 real-fed dry-run error.

    Raised ONLY for a caller-shape failure the wrapper cannot run with -- a session
    config that is not within the HARD Stage 30.11.17 session caps
    (``is_within_session_caps`` is ``False``). The wrapper fails closed BEFORE
    harvesting any event, mirroring the committed downstream sessions. The committed
    Stage 30.11.6 harvest adapter raises its own ``Stage30_11_6CandidateHarvestError``
    on an out-of-bounds ``max_harvest`` (propagated, not swallowed). Degraded per-fact
    facts never raise; an unconfirmed migration / unusable reading fails closed to a
    clean ``SKIPPED_*`` decision downstream. Carries only a closed-set reason token;
    never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.22 real-fed dry-run error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure safe-shape helpers
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_11_22_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the
    committed Stage 30.11.21 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_22_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_22_REDACTED_UNSAFE_ID


def _int(value: object) -> int:
    """Return ``value`` if it is a non-bool ``int``, else ``0``. Pure / total."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


# ---------------------------------------------------------------------------
# The Stage 30.11.22 bridge: harvested projection -> enrichment base fact
# ---------------------------------------------------------------------------


def project_harvested_candidate_to_base_facts(
    projection: Stage30_11_6CandidateProjection,
    *,
    created_at_utc: str,
) -> Stage30_11_18HarvestedCandidateFacts:
    """Map ONE committed Stage 30.11.6 candidate projection onto a base
    ``Stage30_11_18HarvestedCandidateFacts`` ready for the committed Stage 30.11.21
    enrichment chain.

    Pure / total. It carries the REAL ``token_mint`` (the on-chain identity that
    drives every injected source lookup + the migration-anchored ATH window) and the
    run-scoped ``candidate_id`` VERBATIM, and stamps a sentinel on every field the
    enrichment chain fills:

      * ``migration_time_utc`` / ``current_price`` / ``current_market_cap_usd`` /
        ``liquidity_usd`` / ``market_context_fetched_at_utc`` ->
        ``PENDING_ENRICHMENT`` (a deliberately non-ISO + non-numeric sentinel: the
        committed Stage 30.11.21 / 30.11.20 / 30.11.19 enrichments OVERWRITE it on a
        confirmed / present reading and DROP the fact on a skip -- so it can never
        reach the composer; a bug leak would fail closed at the Stage 30.11.18 Layer-1
        shape / positivity check, never silently dispatch);
      * ``market_context_status`` -> ``PENDING`` (a non-``PRESENT`` status the
        committed Stage 30.11.19 enrichment overwrites to ``PRESENT`` on enrich).

    ``migration_confirmed`` is set ``True`` but is NOT trusted: the committed Stage
    30.11.21 adapter RE-CONFIRMS the migration from the injected evidence source (it
    reads the token mint + evidence, never the base flag) and only forwards a
    confirmed fact. ``symbol_or_name`` / ``migration_source`` / ``age_display`` are
    ``None`` (the harvest projection carries no symbol / provenance / age; the
    enrichment fills the migration provenance on confirm; an age would need clock
    arithmetic this slice never does).
    """
    return Stage30_11_18HarvestedCandidateFacts(
        token_mint=projection.token_mint,
        candidate_id=projection.candidate_id,
        migration_time_utc=STAGE30_11_22_PENDING_ENRICHMENT,
        current_price=STAGE30_11_22_PENDING_ENRICHMENT,
        current_market_cap_usd=STAGE30_11_22_PENDING_ENRICHMENT,
        liquidity_usd=STAGE30_11_22_PENDING_ENRICHMENT,
        market_context_status=STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS,
        market_context_fetched_at_utc=STAGE30_11_22_PENDING_ENRICHMENT,
        created_at_utc=created_at_utc,
        migration_confirmed=True,
        symbol_or_name=None,
        migration_source=None,
        age_display=None,
    )


# ---------------------------------------------------------------------------
# Pure nested-report readers (duck-typed; the committed report types are NEVER
# imported -- the wrapper reads the embedded Stage 30.11.21 -> 30.11.20 ->
# 30.11.19 -> 30.11.18 -> 30.11.17 report by attribute)
# ---------------------------------------------------------------------------


def _skip_histogram(layer: object) -> Tuple[Tuple[str, int], ...]:
    """Return the sorted ``(skip_decision, count)`` histogram for one Layer-0 stage.

    Counts the ``SKIPPED_*`` decision tokens across the stage's ordered enrichment
    events (the single ``ENRICHED`` pass token is excluded). Pure / total; never
    raises -- a degenerate / missing events tuple yields ``()``.
    """
    counts: Dict[str, int] = {}
    events = getattr(layer, "enrichment_events", ())
    if not isinstance(events, (tuple, list)):
        return ()
    for event in events:
        decision = getattr(event, "decision", None)
        if isinstance(decision, str) and decision.startswith(_SKIPPED_PREFIX):
            counts[decision] = counts.get(decision, 0) + 1
    return tuple(sorted(counts.items()))


def _histogram_tokens(*histograms: Tuple[Tuple[str, int], ...]) -> List[str]:
    """Return every decision token across the given histograms (the scan haystack)."""
    tokens: List[str] = []
    for histogram in histograms:
        for token, _count in histogram:
            tokens.append(token)
    return tokens


def _self_scan_safe(texts: Iterable[str]) -> bool:
    """Return ``True`` iff no scanned string carries a transport-scheme separator or
    a forbidden url / secret needle. Pure / total; never raises.
    """
    for text in texts:
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
# Public bounded real-fed dry-run wrapper
# ---------------------------------------------------------------------------


def run_stage30_11_22_real_fed_dry_run(
    events: Iterable[object],
    *,
    assembler: object,
    record_flattener: object,
    evidence_source: object,
    price_source: object,
    market_context_source: object,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    created_at_utc: str,
    config: Optional[Stage30_11_17SessionConfig] = None,
    ledger: Optional[Any] = None,
    transport_client: Optional[Any] = None,
    max_harvest: int = STAGE30_11_6_DEFAULT_MAX_HARVEST,
    candidate_id_prefix: str = STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    ath_timeout_seconds: int = 10,
    market_context_max_age_seconds: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_22RealFedDryRunReport:
    """Run ONE bounded real-fed dry-run and return a
    ``Stage30_11_22RealFedDryRunReport``.

    Fail closed first: if ``config`` (or the default) is not within the HARD Stage
    30.11.17 session caps the wrapper raises ``Stage30_11_22RealFedDryRunError``
    BEFORE harvesting any event. The committed Stage 30.11.6 harvest adapter raises
    its own ``Stage30_11_6CandidateHarvestError`` on an out-of-bounds ``max_harvest``
    (propagated).

    Otherwise it harvests AT MOST ``max_harvest`` candidates from ``events`` through
    the committed Stage 30.11.6 seam over the INJECTED ``assembler`` +
    ``record_flattener`` (a raise / reject yields no candidate), bridges each
    harvested projection into a base fact, and runs the committed Stage 30.11.21
    migration-time enriched session over the base facts + the INJECTED evidence /
    price / market-context sources + ATH source transport + clocks + the (defaulted)
    FAKE recording transport client + the (defaulted) in-memory dedupe ledger -- a
    RECORDED would-send, NEVER a real send. It rolls the harvest counts + the bridge
    base-facts-built count + the embedded nested report's Layer-0 / Layer-1 / Layer-2
    counts + the per-stage skip histograms + the no-real-send attestation + the
    combined redaction status into one report.

    With ``transport_client`` / ``ledger`` / ``config`` defaulted, the wrapper builds
    a fresh committed Stage 30.11.5 recording FAKE client (records would-sends, opens
    no socket), a fresh committed Stage 30.11.15 in-memory ledger (no I/O -- it cannot
    touch the durable one-send ledger), and the default bounded session config
    (``max_candidates=10`` / ``max_compositions=10``). Pure / deterministic apart from
    the injected sources' reads + the injected fake client's + ledger's recording side
    effects; reads no env, no clock, no network; constructs no provider transport,
    reserves no real dispatch, sends no private message, writes no file, runs no daemon
    / ``while`` loop, and NEVER calls the Stage 30.11.16 real private transport guard.
    """
    effective_config = (
        default_session_config(created_at_utc=created_at_utc)
        if config is None
        else config
    )
    if not is_within_session_caps(effective_config):
        # Fail closed on an out-of-bounds config: harvest nothing, enrich nothing.
        raise Stage30_11_22RealFedDryRunError("INVALID_SESSION_CONFIG")

    effective_ledger = (
        InMemoryPingDedupeLedger() if ledger is None else ledger
    )
    effective_client = (
        Stage30_11_5RecordingFakeTransportClient(created_at_utc=created_at_utc)
        if transport_client is None
        else transport_client
    )

    # ---- Harvest the real-fed candidates (the committed Stage 30.11.6 seam) ----
    harvest_result = harvest_live_candidates(
        events,
        assembler=assembler,
        record_flattener=record_flattener,
        created_at_utc=created_at_utc,
        max_harvest=max_harvest,
        candidate_id_prefix=candidate_id_prefix,
    )

    # ---- Bridge each harvested projection into an enrichment base fact ----
    base_facts: List[Stage30_11_18HarvestedCandidateFacts] = [
        project_harvested_candidate_to_base_facts(
            projection, created_at_utc=created_at_utc
        )
        for projection in harvest_result.candidate_source
    ]

    # ---- Run the committed Stage 30.11.21 enrichment chain over the base facts ----
    enrichment_report = run_stage30_11_21_migration_time_enriched_session(
        base_facts,
        evidence_source=evidence_source,
        price_source=price_source,
        market_context_source=market_context_source,
        config=effective_config,
        ledger=effective_ledger,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=effective_client,
        now_seconds=now_seconds,
        ath_timeout_seconds=ath_timeout_seconds,
        market_context_max_age_seconds=market_context_max_age_seconds,
        ttl_seconds=ttl_seconds,
    )

    # ---- Read the embedded nested report (duck-typed by attribute) ----
    migration_layer = enrichment_report
    price_layer = getattr(migration_layer, "downstream_report", None)
    market_layer = getattr(price_layer, "downstream_report", None)
    projection_layer = getattr(market_layer, "downstream_report", None)
    session = getattr(projection_layer, "session_result", None)

    migration_skip_histogram = _skip_histogram(migration_layer)
    price_skip_histogram = _skip_histogram(price_layer)
    market_skip_histogram = _skip_histogram(market_layer)

    would_send_recorded = _int(getattr(session, "would_send_recorded", 0))
    attestation = Stage30_11_22NoRealSendAttestation(
        transport_client_kind=_safe_echo(type(effective_client).__name__),
        ledger_kind=_safe_echo(type(effective_ledger).__name__),
        would_send_recorded=would_send_recorded,
        real_send_performed=False,
        real_send_guard_invoked=False,
    )

    stop_reason = getattr(session, "stop_reason", "")
    if not isinstance(stop_reason, str):
        stop_reason = ""

    # ---- Combined redaction status: this report's own string fields must be safe
    #      AND the embedded Stage 30.11.21 report must itself be redacted ----
    own_safe = _self_scan_safe(
        [
            stop_reason,
            created_at_utc,
            attestation.transport_client_kind,
            attestation.ledger_kind,
        ]
        + _histogram_tokens(
            migration_skip_histogram,
            price_skip_histogram,
            market_skip_histogram,
        )
    )
    embedded_redacted = (
        getattr(enrichment_report, "redaction_status", "")
        == STAGE30_11_22_REDACTION_STATUS_REDACTED
    )
    redaction_status = (
        STAGE30_11_22_REDACTION_STATUS_REDACTED
        if (own_safe and embedded_redacted)
        else STAGE30_11_22_REDACTION_STATUS_VIOLATION
    )

    summary = harvest_result.summary
    return Stage30_11_22RealFedDryRunReport(
        events_seen=_int(getattr(summary, "events_seen", 0)),
        candidates_harvested=_int(getattr(summary, "harvested", 0)),
        harvest_skipped_assembly_failed=_int(
            getattr(summary, "skipped_assembly_failed", 0)
        ),
        harvest_skipped_projection_rejected=_int(
            getattr(summary, "skipped_projection_rejected", 0)
        ),
        base_facts_built=len(base_facts),
        migration_enriched=_int(getattr(migration_layer, "enriched", 0)),
        migration_skipped=_int(getattr(migration_layer, "skipped", 0)),
        migration_skip_histogram=migration_skip_histogram,
        price_enriched=_int(getattr(price_layer, "enriched", 0)),
        price_skipped=_int(getattr(price_layer, "skipped", 0)),
        price_skip_histogram=price_skip_histogram,
        market_enriched=_int(getattr(market_layer, "enriched", 0)),
        market_skipped=_int(getattr(market_layer, "skipped", 0)),
        market_skip_histogram=market_skip_histogram,
        projected=_int(getattr(projection_layer, "projected", 0)),
        rejected_projection=_int(
            getattr(projection_layer, "rejected_projection", 0)
        ),
        composed=_int(getattr(session, "compositions_attempted", 0)),
        dispatched=_int(getattr(session, "dispatched", 0)),
        dedupe_blocked=_int(getattr(session, "dedupe_blocked", 0)),
        would_send_recorded=would_send_recorded,
        stop_reason=stop_reason,
        enrichment_report=enrichment_report,
        attestation=attestation,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_22RealFedDryRunError",
    "project_harvested_candidate_to_base_facts",
    "run_stage30_11_22_real_fed_dry_run",
)
