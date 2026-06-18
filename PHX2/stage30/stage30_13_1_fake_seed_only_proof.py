"""Stage 30.13.1 seed-only fake proof.

Offline only. A thin driver that proves the bounded WS auto-seeder discovers + seeds
fresh pump-suffix migrated mints from the REAL committed Stage 29.5
``Stage29_5HeliusWebSocketAdapter`` driven over an INJECTED fake WebSocket transport --
and STOPS at the seeded watchlist, BEFORE any recheck / fake-send:

    an INJECTED fake Stage29_5WebSocketTransport (deterministic fixture bytes, a
    raising / malformed transport in the error case) + an INJECTED clock
      -> the committed Stage 29.5 Helius WS adapter (the real adapter; it consumes the
         injected transport and never opens a socket) -> a bounded migration-evidence
         batch
      -> the committed Stage 30.13.0 auto-seeder
      -> a ``Stage30_13_1SeedOnlyProofResult`` carrying the auto-seed result (the four
         counts + the seeded sanitized summaries) and the seeded token mints

This proof builds NO runtime gate, NO bridge, NO transport client, NO dispatch sink, NO
composer, NO ledger -- it ends at the seeded watchlist. The end-to-end flow through the
committed recheck / fake-send chain is the SEPARATE Stage 30.13.2 proof. The real
read-only Helius WS socket transport (a concrete transport behind the committed Stage
29.5 transport Protocol) remains a SEPARATE, operator-authorized step (see the Stage
30.13.3 handoff).

The transport + clock are INJECTED, NOT built here. This proof opens NO socket, reads NO
env, reads NO wall clock, sends NO message, calls NO transport client, touches NO durable
ledger, and writes NO file.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 29.5 Helius WS adapter (the discovery currency) +
    the Stage 30.13.0 auto-seeder + models siblings. No other Stage 21-29 import (no
    Birdeye, no Stage 27 / 28); no Stage 30.11 runtime / transport / dispatch import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket (the transport is injected); no database, no compression.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; the clock + ``created_at_utc`` are
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PHX2.stage29.stage29_5_helius_ws_adapter import (
    Stage29_5HeliusWebSocketAdapter,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    STAGE30_13_DEFAULT_MAX_SEED,
    Stage30_13AutoSeedResult,
)
from PHX2.stage30.stage30_13_0_ws_auto_seeder import (
    build_seeded_watchlist_from_ws_discovery,
)


@dataclass(frozen=True)
class Stage30_13_1SeedOnlyProofResult:
    """The seed-only proof result.

    Carries the auto-seed result (the ordered seed outcomes + the four-count summary +
    the seeded sanitized summaries + the redaction status) and the seeded token mints
    (the safe-shape base mints that became the seeded watchlist), so a test can assert
    the counts AND that a fresh pump-suffix mint was discovered + seeded -- WITHOUT any
    recheck / fake-send having run.

      * ``auto_seed_result``   -- the committed Stage 30.13.0 ``Stage30_13AutoSeedResult``.
      * ``seeded_token_mints`` -- the seeded summaries' token mints (the watchlist).
    """

    auto_seed_result: Stage30_13AutoSeedResult
    seeded_token_mints: Tuple[str, ...]


def _summary_token_mint(summary: object) -> str:
    """Read a sanitized summary's ``token_mint`` as a safe string, else ``""``. Pure."""
    mint = getattr(summary, "token_mint", None)
    return mint if isinstance(mint, str) else ""


def run_stage30_13_1_fake_seed_only_proof(
    transport: object,
    *,
    clock: object,
    created_at_utc: str,
    max_seed: int = STAGE30_13_DEFAULT_MAX_SEED,
) -> Stage30_13_1SeedOnlyProofResult:
    """Drive the committed Stage 29.5 Helius WS adapter (over the INJECTED ``transport``
    + ``clock``) through the committed Stage 30.13.0 auto-seeder and return the seeded
    watchlist + counts.

    Pure / deterministic apart from the injected transport's + clock's behavior; reads no
    env, no wall clock, no network; builds no runtime gate / bridge / transport client /
    dispatch sink / ledger, sends no message, writes no file. It STOPS at the seeded
    watchlist -- the recheck / fake-send chain is the separate Stage 30.13.2 proof.

    A malformed / raising transport surfaces through the adapter as a fail-closed
    ``WS_CAPTURE_FAILED`` error in the auto-seed result (the auto-seeder never raises for
    a degraded capture). The caller-shape ``max_seed`` validation is the auto-seeder's
    (it raises ``Stage30_13AutoSeedError`` on an out-of-bounds budget).
    """
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=clock,
    )
    auto_seed_result = build_seeded_watchlist_from_ws_discovery(
        adapter,
        created_at_utc=created_at_utc,
        max_seed=max_seed,
    )
    seeded_token_mints = tuple(
        _summary_token_mint(summary)
        for summary in auto_seed_result.seeded_summaries
    )
    return Stage30_13_1SeedOnlyProofResult(
        auto_seed_result=auto_seed_result,
        seeded_token_mints=seeded_token_mints,
    )


__all__ = (
    "Stage30_13_1SeedOnlyProofResult",
    "run_stage30_13_1_fake_seed_only_proof",
)
