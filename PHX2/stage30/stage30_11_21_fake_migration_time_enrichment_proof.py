"""Stage 30.11.21 fake migration-time enrichment proof.

Offline only. A thin, transport-AGNOSTIC driver for the committed Stage 30.11.21
migration-time enrichment adapter: it builds the default bounded session config + a
fresh in-memory dedupe ledger + a fresh committed Stage 30.11.5 recording FAKE
dispatch client (unless injected) and runs an INJECTED iterable of base harvested
facts through the enrichment adapter over an INJECTED, duck-typed migration evidence
source + an INJECTED, duck-typed price source + an INJECTED, duck-typed
market-context source + an INJECTED fake ATH source transport + clocks -- proving the
adapter overwrites ONLY the three migration fields (``migration_time_utc`` /
``migration_confirmed`` / ``migration_source``) on each ENRICHED fact from a CONFIRMED
Stage 30.11.8 resolution (a placeholder base migration_time becomes the confirmed
anchor), fails closed to a precise ``SKIPPED_*`` token on an unconfirmed migration,
forwards ONLY the enriched facts to the committed Stage 30.11.20 session (and behind
it the Stage 30.11.19 / 30.11.18 / 30.11.17 sessions), and rolls up ONE combined
nested redaction-safe report, all with NO real send.

The migration evidence source (the committed Stage 30.11.9 mint-keyed evidence-source
adapter the test builds over a FAKE record provider, OR any duck-typed
``lookup_migration_evidence`` source), the price source (the committed Stage 29.2
price source the test builds over a FAKE transport), the market-context source (the
committed Stage 30.4.3 source over the same FAKE transport), the ATH source
transport, the clocks, and the base facts are injected, NOT built here -- so this
committed proof imports NO Stage 21-29 module, NO Stage 30.11.8 / 30.11.9 confirmation
module, NO Stage 29.2 price source, and NO Stage 30.4.3 source, and stays inside the
closed Stage 30 dependency boundary. It opens NO socket, reads NO env, sends NO
Discord, calls NO real transport, calls NO Stage 30.11.16 real-send guard, and writes
NO file (the proof uses the in-memory ledger). The real Stage 29.5 migration evidence
read and the controlled live send remain a SEPARATE, operator-authorized step this
proof does NOT build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.5 recording fake transport client, the
    committed Stage 30.11.15 in-memory ledger, the committed Stage 30.11.17 session
    config + default builder, and the Stage 30.11.21 adapter + models siblings. No
    other PHX2 module; no Stage 21-29 / Stage 30.11.8 / 30.11.9 confirmation / Stage
    29.2 price source / Stage 30.4.3 source / Stage 30.11.16 real-send guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No provider, transport-destination, or request-metadata reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; every timestamp / clock is
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
    default_session_config,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_adapter import (
    run_stage30_11_21_migration_time_enriched_session,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_models import (
    Stage30_11_21MigrationEnrichmentSessionReport,
)


@dataclass(frozen=True)
class Stage30_11_21FakeMigrationEnrichmentSessionProofResult:
    """The rolled-up enrichment session report + the recording FAKE client + the
    shared ledger, so a test can assert the Layer-0 enrichment outcomes, the
    embedded Stage 30.11.20 / 30.11.19 / 30.11.18 / 30.11.17 outcomes, the recorded
    would-send tally (NEVER a real send), the rolled-up counts, and that the ONE
    shared ledger suppressed any in-run duplicate.
    """

    report: Stage30_11_21MigrationEnrichmentSessionReport
    client: Any
    ledger: Any


def run_stage30_11_21_fake_migration_time_enrichment_proof(
    base_facts: Iterable[object],
    *,
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
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_21FakeMigrationEnrichmentSessionProofResult:
    """Run the committed Stage 30.11.21 enrichment adapter over the INJECTED base
    facts + INJECTED migration evidence source + INJECTED price source + INJECTED
    market-context source + INJECTED fake ATH source transport + a recording FAKE
    dispatch client + the ONE shared in-memory ledger; return
    ``(report, client, ledger)``.

    With ``config`` / ``ledger`` / ``transport_client`` defaulted, the default
    bounded session config (``max_candidates=10`` / ``max_compositions=10``), a
    fresh in-memory dedupe ledger, and a fresh recording FAKE client are built here.
    Each base fact is migration-enriched at Layer-0 (the migration verdict is the
    committed Stage 30.11.8 confirmation's to decide); only the ENRICHED facts are
    composed through the committed Stage 30.11.20 / 30.11.19 / 30.11.18 / 30.11.17
    session chain (a RECORDED would-send, NEVER a real send). Pure / deterministic
    apart from the injected sources' reads + the injected fake client's + ledger's
    recording side effects; reads no clock, no env, no network; constructs no
    provider transport, reserves no real dispatch, sends no Discord, writes no file,
    runs no daemon / ``while`` loop.
    """
    effective_config = (
        default_session_config(created_at_utc=created_at_utc)
        if config is None
        else config
    )
    effective_ledger = (
        InMemoryPingDedupeLedger() if ledger is None else ledger
    )
    effective_client = (
        Stage30_11_5RecordingFakeTransportClient(created_at_utc=created_at_utc)
        if transport_client is None
        else transport_client
    )
    ttl_kwargs = {} if ttl_seconds is None else {"ttl_seconds": ttl_seconds}

    report = run_stage30_11_21_migration_time_enriched_session(
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
        **ttl_kwargs,
    )
    return Stage30_11_21FakeMigrationEnrichmentSessionProofResult(
        report=report,
        client=effective_client,
        ledger=effective_ledger,
    )


__all__ = (
    "Stage30_11_21FakeMigrationEnrichmentSessionProofResult",
    "run_stage30_11_21_fake_migration_time_enrichment_proof",
)
