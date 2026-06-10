"""Stage 30.11.22 fake real-fed dry-run proof.

Offline only. A thin, transport-AGNOSTIC driver for the committed Stage 30.11.22
real-fed dry-run wrapper: it builds the default bounded session config + a fresh
in-memory dedupe ledger + a fresh committed Stage 30.11.5 recording FAKE dispatch
client (unless injected) and runs an INJECTED bounded event source through the
committed Stage 30.11.6 harvest seam (over an INJECTED, duck-typed assembler +
record flattener) -> the Stage 30.11.22 bridge -> the committed Stage 30.11.21 ->
30.11.20 -> 30.11.19 -> 30.11.18 -> 30.11.17 chain (over an INJECTED, duck-typed
migration evidence source + price source + market-context source + ATH source
transport + clocks) -- proving a REAL-fed harvested candidate flows end-to-end to a
RECORDED would-send, NEVER a real send, and that the rolled-up report carries the
harvest / bridge / Layer-0 / Layer-1 / Layer-2 counts + skip histograms + the
no-real-send attestation.

The assembler + record flattener (the harvest front-end), the migration evidence
source (the committed Stage 30.11.9 adapter the test builds over a FAKE record
provider), the price source (the committed Stage 29.2 source over a FAKE transport),
the market-context source (the committed Stage 30.4.3 source over the same FAKE
transport), the ATH source transport, the clocks, and the bounded event source are
INJECTED, NOT built here -- so this committed proof imports NO Stage 21-29 module, NO
Stage 30.4.3 source, NO Stage 30.11.9 source, and NO Stage 30.11.6 harvest internals,
and stays inside the closed Stage 30.11 dependency boundary. It opens NO socket,
reads NO env, sends NO private message, calls NO real transport, calls NO Stage
30.11.16 real-send guard, and writes NO file (the proof uses the in-memory ledger).
The real live event source + provider sources + the controlled live send remain a
SEPARATE, operator-authorized step this proof does NOT build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.5 recording fake transport client, the
    committed Stage 30.11.15 in-memory ledger, the committed Stage 30.11.17 session
    config + default builder, and the Stage 30.11.22 adapter + models siblings. No
    other PHX2 module; no Stage 21-29 / Stage 30.4.3 source / Stage 30.11.6 harvest /
    Stage 30.11.9 source / Stage 30.11.16 real-send guard import.
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
from PHX2.stage30.stage30_11_22_real_fed_dry_run_adapter import (
    run_stage30_11_22_real_fed_dry_run,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    Stage30_11_22RealFedDryRunReport,
)


@dataclass(frozen=True)
class Stage30_11_22FakeRealFedDryRunProofResult:
    """The rolled-up dry-run report + the recording FAKE client + the shared ledger,
    so a test can assert the harvest counts, the bridge base-facts-built count, the
    embedded Layer-0 / Layer-1 / Layer-2 outcomes, the recorded would-send tally
    (NEVER a real send), and that the ONE shared ledger suppressed any in-run
    duplicate.
    """

    report: Stage30_11_22RealFedDryRunReport
    client: Any
    ledger: Any


def run_stage30_11_22_fake_real_fed_dry_run_proof(
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
    max_harvest: Optional[int] = None,
    candidate_id_prefix: Optional[str] = None,
    ath_timeout_seconds: int = 10,
    market_context_max_age_seconds: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_22FakeRealFedDryRunProofResult:
    """Run the committed Stage 30.11.22 real-fed dry-run wrapper over the INJECTED
    bounded event source + INJECTED harvest front-end + INJECTED provider sources +
    a recording FAKE dispatch client + the ONE shared in-memory ledger; return
    ``(report, client, ledger)``.

    With ``config`` / ``ledger`` / ``transport_client`` defaulted, the default bounded
    session config (``max_candidates=10`` / ``max_compositions=10``), a fresh in-memory
    dedupe ledger, and a fresh recording FAKE client are built here. Pure /
    deterministic apart from the injected sources' reads + the injected fake client's +
    ledger's recording side effects; reads no clock, no env, no network; constructs no
    provider transport, reserves no real dispatch, sends no private message, writes no
    file, runs no daemon / ``while`` loop.
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
    harvest_kwargs = {}
    if max_harvest is not None:
        harvest_kwargs["max_harvest"] = max_harvest
    if candidate_id_prefix is not None:
        harvest_kwargs["candidate_id_prefix"] = candidate_id_prefix

    report = run_stage30_11_22_real_fed_dry_run(
        events,
        assembler=assembler,
        record_flattener=record_flattener,
        evidence_source=evidence_source,
        price_source=price_source,
        market_context_source=market_context_source,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        now_seconds=now_seconds,
        created_at_utc=created_at_utc,
        config=effective_config,
        ledger=effective_ledger,
        transport_client=effective_client,
        ath_timeout_seconds=ath_timeout_seconds,
        market_context_max_age_seconds=market_context_max_age_seconds,
        ttl_seconds=ttl_seconds,
        **harvest_kwargs,
    )
    return Stage30_11_22FakeRealFedDryRunProofResult(
        report=report,
        client=effective_client,
        ledger=effective_ledger,
    )


__all__ = (
    "Stage30_11_22FakeRealFedDryRunProofResult",
    "run_stage30_11_22_fake_real_fed_dry_run_proof",
)
