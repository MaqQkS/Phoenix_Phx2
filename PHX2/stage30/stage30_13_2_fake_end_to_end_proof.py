"""Stage 30.13.2 end-to-end fake-send proof.

Offline only. A thin composition that proves the WHOLE Build #24 path -- bounded WS
discovery -> pump-suffix auto-seed -> the existing committed recheck / fake-send chain --
reaches a RECORDED would-send (a FAKE dispatch), NEVER a real send:

    an INJECTED fake Stage29_5WebSocketTransport + clock + INJECTED fake price /
    market-context / ATH sources -- EACH of which MUST be a fake-only marked component
    (``Stage30_13_2FakeOnly``); a non-fake / live-looking injected component is rejected
    with a ``Stage30_13_2FakeProofError`` BEFORE anything is driven
      -> the committed Stage 30.13.1 seed-only proof (the real Stage 29.5 Helius WS
         adapter over the injected transport -> the Stage 30.13.0 auto-seeder) -> the
         seeded sanitized summaries (the watchlist)
      -> the committed Stage 30.11.23 fake real-fed dry-run proof (the committed Stage
         30.11.23 bridge -> the committed Stage 30.11.22 dry-run chain over the INJECTED
         fake price / market-context / ATH sources + clocks) -- which ALWAYS builds a
         FRESH in-memory dedupe ledger + a FRESH recording FAKE dispatch client internally
      -> a ``Stage30_13_2EndToEndProofResult`` carrying the seed proof (the four counts +
         the seeded watchlist) and the dry-run result (the bridge report + the dry-run
         report + the recording fake client + the ledger)

Stage 30.13.4 hardening (after the blind-audit FAIL): the public proof exposes NO
dispatch-client and NO durable-ledger injection knob at all -- there is no ``ledger`` and
no ``transport_client`` parameter, so a fake-seeded candidate can NEVER reach a non-fake
dispatch client or a durable ledger through accidental caller injection; the downstream
proof always constructs a fresh in-memory ledger + a fresh recording FAKE client. The
remaining injected read components (the WS transport + the price / market-context / ATH
sources) MUST carry the ``Stage30_13_2FakeOnly`` marker -- a live-capable object that does
not is refused before the seed -> recheck -> fake-dispatch chain runs.

This proof builds NO real transport, opens NO socket, reads NO env, reads NO wall clock,
sends NO private message, calls NO real dispatch, calls NO Stage 30.11.16 real-send guard,
touches NO durable ledger, and writes NO file. The dispatched mint traces to the
WS-discovered pump-suffix summary -- there is NO hand-fed mint anywhere in the path. The
real read-only Helius WS socket transport + the controlled live send remain a SEPARATE,
operator-authorized step (see the Stage 30.13.3 handoff).

Discipline:

  * Stdlib only (``dataclasses``).
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


# ---------------------------------------------------------------------------
# Fake-only marker + closed-set role tokens + the non-fake rejection error
# ---------------------------------------------------------------------------
#
# Stage 30.13.4 hardening. The public proof accepts an injected WS transport + price /
# market-context / ATH source ONLY when each is a fake-only marked component -- a test /
# in-memory fake inherits this marker; NO real provider source, real transport, real
# dispatch client, or durable-ledger production class does. So a live-capable object can
# never be accidentally injected into the fake end-to-end proof.


class Stage30_13_2FakeOnly:
    """Marker base class for the in-memory / fake proof components the public Stage
    30.13.2 end-to-end proof accepts as injected inputs.

    A fake transport / price source / market-context source / ATH transport built by the
    offline proof tests inherits this marker. The public proof enforces it on every
    injected read component BEFORE driving the seed -> recheck -> fake-dispatch chain, so
    a live-capable object can never be accidentally injected into the fake proof. Empty
    by design -- it carries no behavior, only identity.
    """


# Closed-set role tokens carried by a rejection (never a raw object repr / payload / url /
# secret). Exactly one per marker-checked injected component.
STAGE30_13_2_ROLE_TRANSPORT: str = "NON_FAKE_TRANSPORT"
STAGE30_13_2_ROLE_PRICE_SOURCE: str = "NON_FAKE_PRICE_SOURCE"
STAGE30_13_2_ROLE_MARKET_CONTEXT_SOURCE: str = "NON_FAKE_MARKET_CONTEXT_SOURCE"
STAGE30_13_2_ROLE_ATH_TRANSPORT: str = "NON_FAKE_ATH_TRANSPORT"


class Stage30_13_2FakeProofError(Exception):
    """Raised when a non-fake (live-capable) component is injected into the public Stage
    30.13.2 fake end-to-end proof.

    Carries ONLY a closed-set role token (one of ``NON_FAKE_TRANSPORT`` /
    ``NON_FAKE_PRICE_SOURCE`` / ``NON_FAKE_MARKET_CONTEXT_SOURCE`` /
    ``NON_FAKE_ATH_TRANSPORT``); never a raw object repr, payload, url, or secret.
    """

    def __init__(self, role: str) -> None:
        self.role: str = role
        super().__init__(
            f"Stage 30.13.2 fake end-to-end proof rejected a non-fake injected "
            f"component: role={role!r}"
        )


def _require_fake_only(component: object, role: str) -> None:
    """Raise ``Stage30_13_2FakeProofError(role)`` unless ``component`` is a fake-only
    marked proof component. Pure guard; no I/O.
    """
    if not isinstance(component, Stage30_13_2FakeOnly):
        raise Stage30_13_2FakeProofError(role)


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
) -> Stage30_13_2EndToEndProofResult:
    """Run the full Build #24 path: WS discovery -> auto-seed -> the existing recheck /
    fake-send chain, returning the seed proof + the downstream dry-run result.

    Stage 30.13.4 hardening: the injected ``transport`` + ``price_source`` +
    ``market_context_source`` + ``ath_transport`` MUST each be a fake-only marked
    component (``Stage30_13_2FakeOnly``); a non-fake / live-looking component is rejected
    with ``Stage30_13_2FakeProofError`` BEFORE anything is driven. There is NO ``ledger``
    and NO ``transport_client`` parameter -- the downstream proof ALWAYS builds a fresh
    in-memory dedupe ledger + a fresh recording FAKE dispatch client, so a fake-seeded
    candidate can never reach a non-fake dispatch client or a durable ledger through
    accidental caller injection.

    Pure / deterministic apart from the injected (fake) transport's / sources' own
    behavior; reads no env, no wall clock, no network; builds no real transport, reserves
    no real dispatch, sends no message, writes no file. The seeded summaries (from the
    Stage 30.13.1 seed-only proof) are fed VERBATIM into the committed Stage 30.11.23 fake
    real-fed dry-run proof -- so the dispatched mint traces to the WS-discovered
    pump-suffix summary, never a hand-fed mint.
    """
    # Fail closed FIRST: refuse any non-fake / live-looking injected component before the
    # seed -> recheck -> fake-dispatch chain runs.
    _require_fake_only(transport, STAGE30_13_2_ROLE_TRANSPORT)
    _require_fake_only(price_source, STAGE30_13_2_ROLE_PRICE_SOURCE)
    _require_fake_only(
        market_context_source, STAGE30_13_2_ROLE_MARKET_CONTEXT_SOURCE
    )
    _require_fake_only(ath_transport, STAGE30_13_2_ROLE_ATH_TRANSPORT)

    seed_proof = run_stage30_13_1_fake_seed_only_proof(
        transport,
        clock=clock,
        created_at_utc=created_at_utc,
        max_seed=max_seed,
    )
    # No ``ledger`` / ``transport_client`` are threaded through: the committed Stage
    # 30.11.23 proof builds a FRESH in-memory ledger + a FRESH recording FAKE client.
    dry_run = run_stage30_11_23_fake_real_fed_dry_run_proof(
        seed_proof.auto_seed_result.seeded_summaries,
        price_source=price_source,
        market_context_source=market_context_source,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        now_seconds=now_seconds,
        created_at_utc=created_at_utc,
    )
    return Stage30_13_2EndToEndProofResult(
        seed_proof=seed_proof,
        dry_run=dry_run,
    )


__all__ = (
    "Stage30_13_2FakeOnly",
    "Stage30_13_2FakeProofError",
    "STAGE30_13_2_ROLE_TRANSPORT",
    "STAGE30_13_2_ROLE_PRICE_SOURCE",
    "STAGE30_13_2_ROLE_MARKET_CONTEXT_SOURCE",
    "STAGE30_13_2_ROLE_ATH_TRANSPORT",
    "Stage30_13_2EndToEndProofResult",
    "run_stage30_13_2_fake_end_to_end_proof",
)
