"""Stage 30.11.18 fake harvested-facts curated session proof.

Offline only. A thin, transport-AGNOSTIC driver for the committed Stage 30.11.18
harvested-facts -> curated compose session adapter: it builds the default bounded
session config + a fresh in-memory dedupe ledger + a fresh committed Stage 30.11.5
recording FAKE dispatch client (unless injected) and runs an INJECTED iterable of
harvested-candidate facts through the adapter over an INJECTED fake ATH source
transport + endpoint secret + clocks -- proving the adapter projects each
well-formed fact into a committed revalidation request (Layer-1), fails closed to
a precise ``REJECTED_*`` token on a malformed fact, runs the bounded Stage 30.11.17
session over the projected entries, suppresses an in-run duplicate over the ONE
shared ledger, and rolls up a redaction-safe report, all with NO real send.

The ATH source transport (and the clocks + the facts list itself) are injected,
NOT built here -- the stage29-shaped fake transport + the coherent harvested facts
live in the Stage 30.11.18 test (tests may build provider fakes), so this committed
proof imports NO Stage 29 provider module and stays inside the closed Stage 30
dependency boundary. It opens NO socket, reads NO env, sends NO Discord, calls NO
real transport, calls NO Stage 30.11.16 real-send guard, and writes NO file (the
proof uses the in-memory ledger). The real harvest + market-context enrichment that
produces the facts, and the controlled live send, remain a SEPARATE,
operator-authorized step this proof does NOT build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.5 recording fake transport client, the
    committed Stage 30.11.15 in-memory ledger, the committed Stage 30.11.17 session
    config + default builder, and the Stage 30.11.18 adapter + models siblings. No
    other PHX2 module; no Stage 21-29 / Stage 30.11.16 real-send guard / Stage
    30.11.6 harvest adapter / live provider / real transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, or request-metadata reference; no
    wallet / signing / trading surface; no public / subscriber routing.
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
from PHX2.stage30.stage30_11_18_harvest_to_curated_adapter import (
    run_stage30_11_18_curated_session,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18SessionReport,
)


@dataclass(frozen=True)
class Stage30_11_18FakeHarvestSessionProofResult:
    """The rolled-up session report + the recording FAKE client + the shared
    ledger, so a test can assert the Layer-1 projection outcomes, the Layer-2
    per-entry outcomes, the recorded would-send tally (NEVER a real send), the
    rolled-up counts + stop reason, and that the ONE shared ledger suppressed the
    in-run duplicate.
    """

    report: Stage30_11_18SessionReport
    client: Any
    ledger: Any


def run_stage30_11_18_fake_harvest_session_proof(
    facts: Iterable[object],
    *,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    created_at_utc: str,
    config: Optional[Stage30_11_17SessionConfig] = None,
    ledger: Optional[Any] = None,
    transport_client: Optional[Any] = None,
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_18FakeHarvestSessionProofResult:
    """Run the committed Stage 30.11.18 adapter over the INJECTED facts list +
    INJECTED fake ATH source transport + a recording FAKE dispatch client + the ONE
    shared in-memory ledger; return ``(report, client, ledger)``.

    With ``config`` / ``ledger`` / ``transport_client`` defaulted, the default
    bounded session config (``max_candidates=10`` / ``max_compositions=10``), a
    fresh in-memory dedupe ledger, and a fresh recording FAKE client are built
    here. Each well-formed fact is projected into a committed revalidation request
    and composed through the committed Stage 30.11.17 session (a RECORDED
    would-send, NEVER a real send); the shared ledger suppresses any in-run
    duplicate. Pure / deterministic apart from the injected fake client's + ledger's
    recording side effects; reads no clock, no env, no network; reserves no real
    dispatch, sends no Discord, writes no file, runs no daemon / ``while`` loop.
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

    report = run_stage30_11_18_curated_session(
        facts,
        config=effective_config,
        ledger=effective_ledger,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=effective_client,
        now_seconds=now_seconds,
        **ttl_kwargs,
    )
    return Stage30_11_18FakeHarvestSessionProofResult(
        report=report,
        client=effective_client,
        ledger=effective_ledger,
    )


__all__ = (
    "Stage30_11_18FakeHarvestSessionProofResult",
    "run_stage30_11_18_fake_harvest_session_proof",
)
