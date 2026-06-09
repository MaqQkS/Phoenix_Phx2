"""Stage 30.11.17 fake operator-curated compose session proof.

Offline only. A thin, transport-AGNOSTIC driver for the committed Stage 30.11.17
operator-curated compose session: it builds the default bounded session config +
a fresh in-memory dedupe ledger + a fresh committed Stage 30.11.5 recording FAKE
dispatch client (unless injected) and runs an INJECTED operator-curated candidate
list through the session over an INJECTED fake ATH source transport + endpoint
secret + clocks -- proving the bounded curated session composes each eligible
entry once over the ONE shared ledger, suppresses an in-run duplicate, and rolls
up a redaction-safe summary, all with NO real send.

The ATH source transport (and the clocks + the curated list itself) are injected,
NOT built here -- the stage29-shaped fake Birdeye transport + the coherent
revalidation requests live in the Stage 30.11.17 test (tests may build provider
fakes), so this committed proof imports NO Stage 29 provider module and stays
inside the closed Stage 30 dependency boundary. It opens NO socket, reads NO env,
sends NO Discord, calls NO real transport, calls NO Stage 30.11.16 real-send
guard, and writes NO file (the proof uses the in-memory ledger; the JSONL
cross-run replay is proven in the committed Stage 30.11.15 ledger test on a temp
path). The real private compact dispatch / Discord send remains a SEPARATE,
explicitly operator-authorized step this proof does NOT build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.5 recording fake transport client, the
    committed Stage 30.11.15 in-memory ledger, and the Stage 30.11.17 session +
    models siblings. No other PHX2 module; no Stage 21-29 / Stage 30.11.16
    real-send guard / Stage 30.11.6 harvest adapter / live runner / provider /
    real transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
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
    Stage30_11_17SessionResult,
    default_session_config,
)
from PHX2.stage30.stage30_11_17_operator_curated_compose_session import (
    run_stage30_11_17_operator_curated_compose_session,
)


@dataclass(frozen=True)
class Stage30_11_17FakeCuratedSessionProofResult:
    """The bounded session result + the recording FAKE client + the shared
    ledger, so a test can assert the per-entry outcomes, the recorded would-send
    tally (NEVER a real send), the rolled-up counts + stop reason, and that the
    ONE shared ledger suppressed the in-run duplicate.
    """

    result: Stage30_11_17SessionResult
    client: Any
    ledger: Any


def run_stage30_11_17_fake_curated_session_proof(
    candidates: Iterable[object],
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
) -> Stage30_11_17FakeCuratedSessionProofResult:
    """Run the committed Stage 30.11.17 operator-curated compose session over the
    INJECTED curated list + INJECTED fake ATH source transport + a recording FAKE
    dispatch client + the ONE shared in-memory ledger; return
    ``(result, client, ledger)``.

    With ``config`` / ``ledger`` / ``transport_client`` defaulted, the default
    bounded session config (``max_candidates=10`` / ``max_compositions=10``), a
    fresh in-memory dedupe ledger, and a fresh recording FAKE client are built
    here. Every entry is composed through the committed Stage 30.11.15 deduped
    orchestrator (a RECORDED would-send, NEVER a real send); the shared ledger
    suppresses any in-run duplicate. Pure / deterministic apart from the injected
    fake client's + ledger's recording side effects; reads no clock, no env, no
    network; reserves no real dispatch, sends no Discord, writes no file, runs no
    daemon / ``while`` loop.
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

    result = run_stage30_11_17_operator_curated_compose_session(
        candidates,
        config=effective_config,
        ledger=effective_ledger,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=effective_client,
        now_seconds=now_seconds,
        **ttl_kwargs,
    )
    return Stage30_11_17FakeCuratedSessionProofResult(
        result=result,
        client=effective_client,
        ledger=effective_ledger,
    )


__all__ = (
    "Stage30_11_17FakeCuratedSessionProofResult",
    "run_stage30_11_17_fake_curated_session_proof",
)
