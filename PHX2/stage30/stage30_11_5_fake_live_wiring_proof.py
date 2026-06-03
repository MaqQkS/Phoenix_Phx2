"""Stage 30.11.5 offline fake live wiring proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.5 bounded
live runner composes the WHOLE committed dip-gated private dispatch chain over a
live candidate source -- using fakes / offline projections + an INJECTED
in-memory recording FAKE transport client + an injected fake clock ONLY:

    a deterministic FOUR-candidate fake source (flat candidate projections)
      -> the committed Stage 30.11.5 bounded live runner
        -> the Stage 30.11.5 assembler (one projection is rejected: a required
           field is absent)
        -> the committed Stage 30.11.2 runtime seam (bridge -> committed dip gate
           -> committed Stage 30.11.3 private sink -> Stage 30.11.5 transport
           adapter)
        -> the INJECTED recording FAKE transport client (reached for the dip ONLY)
      -> a Stage 30.11.5 ``Stage30_11_5BoundedRunResult`` + the recording client

The deterministic four-candidate fake source isolates exactly one outcome per
candidate:

  1. non-dip context (Tier Unknown, all context present) -> assembled -> bridged
     -> gate SKIP -> suppressed by the dip gate (no transport)
  2. bridge-suppressed (a present-but-not-``PRESENT`` ATH context) -> assembled
     -> bridge SKIP -> suppressed by the bridge (no transport)
  3. Tier 1 dip (all context present) -> assembled -> bridged -> gate PASS ->
     the private sink -> the transport adapter -> the INJECTED fake client (the
     ONLY candidate the client is reached for) -> an accepted would-deliver
  4. assembler-rejected (a required field absent) -> NOT assembled -> never a
     snapshot -> never reaches the seam / transport

So a baseline run sees four source items, assembles three (the rejected one
never becomes a snapshot), the committed seam sees three, bridges two, passes
one, attempts + accepts one dispatch, and the recording fake client records
EXACTLY one attempt -- for the dip (``cand-tier1`` / ``mint-tier1``) ONLY -- with
NO real dispatch ever reserved and NO Discord ever sent.

It is NOT a live runner driver, NOT a live provider run, NOT a Discord send, NOT
a real dispatch reservation, NOT a real transport, and NOT a new readiness gate.
It CONSTRUCTS no filesystem I/O, reads no environment, opens no network
connection, reads no wall clock (every clock is injected), runs no daemon /
``while`` loop, and touches no Discord / live provider / real transport path. The
real private compact dispatch / Discord send remains a SEPARATE, explicitly
operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.5 models + bounded-runner siblings and the
    committed Stage 30.11.2 fake-proof sibling (for the injected constant clock).
    No other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator /
    Stage 28 suppression / live runner / provider / real transport import. The
    assembler / transport adapter / committed seam / committed private sink are
    composed TRANSITIVELY through the committed bounded runner.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO ``time`` / wall clock / random, NO direct filesystem
    primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_bounded_live_runner import (
    run_stage30_11_5_bounded_live_runner,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT,
    TRANSPORT_STATUS_REJECTED,
    TRANSPORT_STATUS_WOULD_DELIVER,
    Stage30_11_5BoundedRunResult,
    Stage30_11_5PrivateOperatorPayload,
    Stage30_11_5TransportClientResult,
)


# The deterministic caller-injected timestamp for the default scenario (never a
# wall-clock read). Matches the Stage 30.9.3 / 30.11.1 / 30.11.2 / 30.11.3 /
# 30.11.4 fake-proof clocks so the composed proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# A context-present-but-not-``PRESENT`` ATH token: a present field value the
# Stage 30.11.5 assembler accepts (the field is present) but the committed Stage
# 30.11.1 bridge later treats as NOT present (so it suppresses the candidate
# BEFORE the gate). Proves the assembler never forces a degraded context to the
# bridge's ``PRESENT`` value.
_DEGRADED_CONTEXT_STATUS: str = "DEGRADED"


# ---------------------------------------------------------------------------
# Injected in-memory recording fake low-level transport client
# ---------------------------------------------------------------------------


class Stage30_11_5RecordingFakeTransportClient:
    """An in-memory recording fake low-level transport client for tests / proof
    ONLY.

    Callable as the Stage 30.11.5 private transport adapter's injected
    ``transport_client``. It records the number of attempts, the number it
    accepted / rejected, and the candidate ids / token mints / operator bodies it
    was handed, then returns a ``Stage30_11_5TransportClientResult`` verdict. It is
    NOT a real transport: it sends NO Discord message, imports NO webhook /
    transport module, writes NO file, reads NO environment, and opens NO network
    connection. The real private compact dispatch path is a SEPARATE,
    operator-authorized step Stage 30.11.5 does not build.

    A payload whose ``candidate_id`` is in ``reject_candidate_ids`` is rejected
    (``accepted`` is ``False``); every other payload is accepted. With the default
    empty reject set the client accepts every payload it is handed (a RECORDED
    would-deliver, NEVER a real send).

      * ``attempted``     -- count of client calls.
      * ``accepted``      -- count of accepted payloads.
      * ``rejected``      -- count of rejected payloads.
      * ``candidate_ids`` -- the ordered candidate ids the client saw.
      * ``token_mints``   -- the ordered token mints the client saw.
      * ``bodies``        -- the ordered operator bodies the client saw.
    """

    def __init__(
        self,
        *,
        created_at_utc: str = _DEFAULT_CREATED_AT,
        reject_candidate_ids: Tuple[str, ...] = (),
    ) -> None:
        self._created_at_utc = created_at_utc
        self._reject_candidate_ids = frozenset(reject_candidate_ids)
        self.attempted: int = 0
        self.accepted: int = 0
        self.rejected: int = 0
        self.candidate_ids: List[str] = []
        self.token_mints: List[str] = []
        self.bodies: List[str] = []

    def __call__(
        self, payload: Stage30_11_5PrivateOperatorPayload
    ) -> Stage30_11_5TransportClientResult:
        self.attempted += 1
        self.candidate_ids.append(payload.candidate_id)
        self.token_mints.append(payload.token_mint)
        self.bodies.append(payload.body)
        accept = payload.candidate_id not in self._reject_candidate_ids
        if accept:
            self.accepted += 1
        else:
            self.rejected += 1
        return Stage30_11_5TransportClientResult(
            accepted=accept,
            transport_status=(
                TRANSPORT_STATUS_WOULD_DELIVER
                if accept
                else TRANSPORT_STATUS_REJECTED
            ),
            candidate_id=payload.candidate_id,
            token_mint=payload.token_mint,
            created_at_utc=self._created_at_utc,
        )


# ---------------------------------------------------------------------------
# Pure fake candidate-projection builders (the live INPUT shape the assembler
# reads FROM)
# ---------------------------------------------------------------------------


def _projection(
    *,
    candidate_id: str,
    token_mint: str,
    tier_hint: str,
    ath_status: str,
    omit_market_cap: bool = False,
) -> Dict[str, object]:
    """Build a flat fake candidate projection (a dict). All non-isolated signals
    default to the fully-present, dip-ready shape so each fake projection isolates
    exactly one outcome. Pure; no I/O, no clock, no provider call, no fabrication
    beyond the explicit fake fields. When ``omit_market_cap`` is set the required
    ``current_market_cap_usd`` field is ABSENT (the assembler rejects it closed).
    """
    projection: Dict[str, object] = {
        "candidate_id": candidate_id,
        "token_mint": token_mint,
        "pair_type": "SOL",
        "tier_hint": tier_hint,
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": ath_status,
        "market_context_status": "PRESENT",
        "post_migration_ath_verified": True,
        "source_ref": "ref-" + candidate_id,
        "created_at_utc": _DEFAULT_CREATED_AT,
    }
    if not omit_market_cap:
        projection["current_market_cap_usd"] = "12345.67"
    return projection


def _non_dip_projection() -> Dict[str, object]:
    # Tier Unknown, all context present -> assembled -> bridged -> gate SKIP.
    return _projection(
        candidate_id="cand-unknown",
        token_mint="mint-unknown",
        tier_hint="Tier Unknown",
        ath_status="PRESENT",
    )


def _bridge_suppressed_projection() -> Dict[str, object]:
    # ATH context present-but-not-``PRESENT`` -> assembled (the field is present)
    # -> bridge SKIP (the committed bridge treats it as NOT present).
    return _projection(
        candidate_id="cand-no-ath",
        token_mint="mint-no-ath",
        tier_hint="Tier 1",
        ath_status=_DEGRADED_CONTEXT_STATUS,
    )


def _dip_projection() -> Dict[str, object]:
    # Tier 1, all context present -> assembled -> bridged -> gate PASS -> the
    # ONLY candidate the transport client is reached for.
    return _projection(
        candidate_id=STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID,
        token_mint=STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT,
        tier_hint="Tier 1",
        ath_status="PRESENT",
    )


def _assembler_rejected_projection() -> Dict[str, object]:
    # Required ``current_market_cap_usd`` absent -> the assembler rejects it
    # closed -> never a snapshot -> never reaches the seam / transport.
    return _projection(
        candidate_id="cand-invalid",
        token_mint="mint-invalid",
        tier_hint="Tier 1",
        ath_status="PRESENT",
        omit_market_cap=True,
    )


def default_fake_live_wiring_source() -> Tuple[Dict[str, object], ...]:
    """Build the deterministic four-candidate default fake source.

    One non-dip projection, one bridge-suppressed projection, one Tier 1 dip
    projection, and one assembler-rejected projection (a required field absent).
    Pure; no I/O, no clock, no env.
    """
    return (
        _non_dip_projection(),
        _bridge_suppressed_projection(),
        _dip_projection(),
        _assembler_rejected_projection(),
    )


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_5_fake_live_wiring_proof(
    *,
    transport_client: Optional[Stage30_11_5RecordingFakeTransportClient] = None,
    now_seconds: object = None,
    candidate_source: Optional[Tuple[object, ...]] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Stage30_11_5BoundedRunResult,
    Stage30_11_5RecordingFakeTransportClient,
]:
    """Run the Stage 30.11.5 bounded live runner over the deterministic fake
    source and return ``(result, transport_client)``.

    With every argument defaulted, the deterministic four-candidate default fake
    source is run through the committed bounded runner with a fresh in-memory
    recording FAKE transport client (default empty reject set -> accepts the dip),
    an injected constant clock (so the wall-clock bound is never tripped), and the
    default bounded-run config (``max_dispatches=1`` / ``max_runtime_seconds=60``
    / ``max_candidates=10``). The composed run drives EXACTLY one fake transport
    attempt -- for the Tier 1 dip (``cand-tier1`` / ``mint-tier1``) ONLY; the
    non-dip is suppressed by the committed dip gate, the bridge-suppressed by the
    committed bridge, and the assembler-rejected candidate never becomes a
    snapshot, so none reaches the transport.

    Optional ``transport_client`` injects a different recording fake client (for a
    rejecting-transport proof); optional ``candidate_source`` overrides the source.
    Pure / deterministic apart from the injected fake client's recording side
    effects; reads no clock, no env, no network; reserves no real dispatch, sends
    no Discord, writes no file, runs no daemon / ``while`` loop. The assembler /
    transport adapter / committed seam / committed dip gate / committed private
    sink are exercised TRANSITIVELY through the committed bounded runner; this
    proof reimplements none of the composed slices.
    """
    effective_client = (
        Stage30_11_5RecordingFakeTransportClient(created_at_utc=created_at_utc)
        if transport_client is None
        else transport_client
    )
    clock = (
        make_constant_clock(Decimal(0)) if now_seconds is None else now_seconds
    )
    source = (
        default_fake_live_wiring_source()
        if candidate_source is None
        else candidate_source
    )
    result = run_stage30_11_5_bounded_live_runner(
        source,
        transport_client=effective_client,
        now_seconds=clock,
        created_at_utc=created_at_utc,
    )
    return result, effective_client


__all__ = (
    "Stage30_11_5RecordingFakeTransportClient",
    "default_fake_live_wiring_source",
    "run_stage30_11_5_fake_live_wiring_proof",
)
