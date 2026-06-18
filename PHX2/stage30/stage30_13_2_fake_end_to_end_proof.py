"""Stage 30.13.2 end-to-end fake-send proof.

Offline only. A thin composition that proves the WHOLE Build #24 path -- bounded WS
discovery -> pump-suffix auto-seed -> the existing committed recheck / fake-send chain --
reaches a RECORDED would-send (a FAKE dispatch), NEVER a real send:

    an INJECTED fake Stage29_5WebSocketTransport + clock
      -> the committed Stage 30.13.1 seed-only proof (the real Stage 29.5 Helius WS
         adapter over the injected transport -> the Stage 30.13.0 auto-seeder) -> the
         seeded sanitized summaries (the watchlist)
      -> the committed Stage 30.11.23 fake real-fed dry-run proof (the committed Stage
         30.11.23 bridge -> the committed Stage 30.11.22 dry-run chain over the INJECTED
         price / market-context / ATH sources + clocks + a recording FAKE dispatch client
         + an in-memory dedupe ledger)
      -> a ``Stage30_13_2EndToEndProofResult`` carrying the seed proof (the four counts +
         the seeded watchlist) and the dry-run result (the bridge report + the dry-run
         report + the recording fake client + the ledger)

This proof builds NO real transport, opens NO socket, reads NO env, reads NO wall clock,
sends NO private message, calls NO real dispatch, calls NO Stage 30.11.16 real-send
guard, touches NO durable ledger, and writes NO file. The dispatched mint traces to the
WS-discovered pump-suffix summary -- there is NO hand-fed mint anywhere in the path. The
real read-only Helius WS socket transport + the controlled live send remain a SEPARATE,
operator-authorized step (see the Stage 30.13.3 handoff).

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the Stage 30.13.0 models default + the committed Stage 30.13.1 seed-only
    proof + the committed Stage 30.11.23 fake real-fed dry-run proof -- all Stage 30
    siblings (the discovery currency is reached transitively through the Stage 30.13.1
    proof; this module imports NO Stage 21-29 surface directly). No transport / dispatch /
    runner / real-send guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket (every provider source + the transport are injected); no
    database, no compression.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; the clock + every timestamp are
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from PHX2.stage30.stage30_11_23_fake_migration_evidence_candidate_bridge_proof import (
    Stage30_11_23FakeRealFedDryRunProofResult,
    run_stage30_11_23_fake_real_fed_dry_run_proof,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    STAGE30_13_DEFAULT_MAX_SEED,
)
from PHX2.stage30.stage30_13_1_fake_seed_only_proof import (
    Stage30_13_1SeedOnlyProofResult,
    run_stage30_13_1_fake_seed_only_proof,
)


@dataclass(frozen=True)
class Stage30_13_2EndToEndProofResult:
    """The seed proof + the downstream dry-run proof, so a test can assert that a fresh
    WS-discovered pump-suffix mint flows end-to-end to a RECORDED would-send (a FAKE
    dispatch), NEVER a real send, with the dispatched mint tracing to the discovered
    summary.

      * ``seed_proof`` -- the committed Stage 30.13.1 ``Stage30_13_1SeedOnlyProofResult``
                          (the four-count auto-seed result + the seeded watchlist).
      * ``dry_run``    -- the committed Stage 30.11.23 ``Stage30_11_23FakeRealFedDryRunProofResult``
                          (the bridge inputs + the dry-run report + the recording fake
                          client + the dedupe ledger).
    """

    seed_proof: Stage30_13_1SeedOnlyProofResult
    dry_run: Stage30_11_23FakeRealFedDryRunProofResult


def run_stage30_13_2_fake_end_to_end_proof(
    transport: object,
    *,
    clock: object,
    price_source: object,
    market_context_source: object,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    created_at_utc: str,
    max_seed: int = STAGE30_13_DEFAULT_MAX_SEED,
    ledger: Optional[Any] = None,
    transport_client: Optional[Any] = None,
) -> Stage30_13_2EndToEndProofResult:
    """Run the full Build #24 path: WS discovery -> auto-seed -> the existing recheck /
    fake-send chain, returning the seed proof + the downstream dry-run result.

    Pure / deterministic apart from the injected transport's / sources' / fake client's /
    ledger's own behavior; reads no env, no wall clock, no network; builds no real
    transport, reserves no real dispatch, sends no message, writes no file. The seeded
    summaries (from the Stage 30.13.1 seed-only proof) are fed VERBATIM into the committed
    Stage 30.11.23 fake real-fed dry-run proof -- so the dispatched mint traces to the
    WS-discovered pump-suffix summary, never a hand-fed mint. With ``ledger`` /
    ``transport_client`` defaulted the downstream proof builds a fresh in-memory ledger +
    a fresh recording FAKE client.
    """
    seed_proof = run_stage30_13_1_fake_seed_only_proof(
        transport,
        clock=clock,
        created_at_utc=created_at_utc,
        max_seed=max_seed,
    )
    dry_run = run_stage30_11_23_fake_real_fed_dry_run_proof(
        seed_proof.auto_seed_result.seeded_summaries,
        price_source=price_source,
        market_context_source=market_context_source,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        now_seconds=now_seconds,
        created_at_utc=created_at_utc,
        ledger=ledger,
        transport_client=transport_client,
    )
    return Stage30_13_2EndToEndProofResult(
        seed_proof=seed_proof,
        dry_run=dry_run,
    )


__all__ = (
    "Stage30_13_2EndToEndProofResult",
    "run_stage30_13_2_fake_end_to_end_proof",
)
