"""Stage 30.11.3 offline fake private sink proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.3 private
sink adapter translates a committed ``PASS_TO_DISPATCH`` gate input into the
private sink request shape and hands it to an INJECTED, in-memory recording FAKE
transport -- and that the committed Stage 30.11.2 runtime seam reaches that sink
ONLY for the dip. It uses fakes / offline gate inputs + an injected recording
fake transport ONLY:

    1. a direct three-call sink proof:
         valid gate input + transport accepts  -> PRIVATE_SINK_ACCEPTED
         invalid gate input (blank id)         -> PRIVATE_SINK_REJECTED_INVALID_INPUT
                                                  (transport NOT attempted)
         valid gate input + transport rejects  -> PRIVATE_SINK_TRANSPORT_FAILED
       so the rolled-up summary sees three requests, one accepted, one
       rejected-invalid, one transport-failed, two transport attempts, one
       transport accept.

    2. a runtime seam integration proof: the committed Stage 30.11.2 seam runs
       over a three-candidate stream (one valid dip, one non-dip, one
       bridge-skip) with the Stage 30.11.3 private sink (wrapped for seam
       compatibility) injected as the dispatch sink -- and the recording fake
       transport records EXACTLY one attempt, for the dip only. Non-dips and
       bridge skips never reach the transport.

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a real
dispatch reservation, NOT a real transport, and NOT a new readiness gate. It
constructs no filesystem I/O, reads no environment, opens no network connection,
reads no wall clock (every clock is injected), and touches no Discord / live
provider / real transport path. The real private compact dispatch / Discord send
remains a SEPARATE, explicitly operator-authorized step this slice does not
build.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.3 models + adapter siblings, the committed
    Stage 30.9.3 gate-models sibling (for the gate-input type), and the
    committed Stage 30.11.2 runtime-gate-models + seam + fake-proof siblings
    (for the seam + its deterministic candidate stream / clock / config). No
    other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator /
    Stage 28 suppression / live runner / provider / real transport import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO ``time`` / wall clock / random, NO direct filesystem
    primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11RuntimeGateCandidateOutcome,
    Stage30_11RuntimeGateSummary,
)
from PHX2.stage30.stage30_11_2_runtime_gate_seam import (
    run_stage30_11_runtime_gate_seam,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    default_runtime_gate_candidate_stream,
    default_runtime_gate_config,
    make_constant_clock,
)
from PHX2.stage30.stage30_11_3_private_sink_adapter import (
    build_default_compact_body,
    make_runtime_seam_compatible_sink,
    make_stage30_11_private_dispatch_sink,
    summarize_private_sink_results,
)
from PHX2.stage30.stage30_11_3_private_sink_models import (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
    PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
    Stage30_11PrivateSinkProofSummary,
    Stage30_11PrivateSinkRequest,
    Stage30_11PrivateSinkResult,
)


# The deterministic caller-injected timestamp for the default scenarios (never
# a wall-clock read). Matches the Stage 30.9.3 / 30.11.1 / 30.11.2 fake-proof
# clocks so the composed proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# The deterministic candidate ids the direct three-call sink proof drives. The
# accept id is accepted by the recording fake transport; the reject id is in the
# transport's reject set; the invalid scenario uses a blank candidate id (the
# adapter fails it closed BEFORE the transport).
DIRECT_PROOF_ACCEPT_CANDIDATE_ID: str = "cand-accept"
DIRECT_PROOF_REJECT_CANDIDATE_ID: str = "cand-reject"


# ---------------------------------------------------------------------------
# Injected in-memory recording fake private transport
# ---------------------------------------------------------------------------


class Stage30_11RecordingFakePrivateTransport:
    """An in-memory recording fake private transport for tests / proof ONLY.

    Callable as the private sink adapter's injected ``transport``. It records the
    number of attempts, the number it accepted / rejected, and the candidate ids
    / token mints / compact bodies it was handed, then returns a
    ``Stage30_11PrivateSinkResult`` verdict. It is NOT a real transport: it sends
    NO Discord message, imports NO webhook / transport module, writes NO file,
    reads NO environment, and opens NO network connection. The real private
    compact dispatch path is a SEPARATE, operator-authorized step Stage 30.11.3
    does not build.

    A request whose ``candidate_id`` is in ``reject_candidate_ids`` is rejected
    (``transport_accepted`` is ``False``); every other request is accepted. With
    the default empty reject set the transport accepts every request it is
    handed.

      * ``attempted``      -- count of transport calls.
      * ``accepted``       -- count of accepted requests.
      * ``rejected``       -- count of rejected requests.
      * ``candidate_ids``  -- the ordered candidate ids the transport saw.
      * ``token_mints``    -- the ordered token mints the transport saw.
      * ``compact_bodies`` -- the ordered compact bodies the transport saw.
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
        self.compact_bodies: List[str] = []

    def __call__(
        self, request: Stage30_11PrivateSinkRequest
    ) -> Stage30_11PrivateSinkResult:
        self.attempted += 1
        self.candidate_ids.append(request.candidate_id)
        self.token_mints.append(request.token_mint)
        self.compact_bodies.append(request.compact_body)
        accept = request.candidate_id not in self._reject_candidate_ids
        if accept:
            self.accepted += 1
        else:
            self.rejected += 1
        return Stage30_11PrivateSinkResult(
            candidate_id=request.candidate_id,
            token_mint=request.token_mint,
            sink_decision=(
                PRIVATE_SINK_DECISION_ACCEPTED
                if accept
                else PRIVATE_SINK_DECISION_TRANSPORT_FAILED
            ),
            sink_reason=(
                PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
                if accept
                else PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED
            ),
            transport_attempted=True,
            transport_accepted=accept,
            created_at_utc=self._created_at_utc,
        )


# ---------------------------------------------------------------------------
# Pure fake gate-input builders
# ---------------------------------------------------------------------------


def _valid_gate_input(
    *, candidate_id: str, token_mint: str
) -> Stage30_9_3LiveGateInput:
    """Build a fully-present, well-shaped committed gate input (the
    ``PASS_TO_DISPATCH`` candidate shape the seam hands the sink). Pure; no I/O,
    no clock, no provider call.
    """
    return Stage30_9_3LiveGateInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref="ref-" + candidate_id,
        created_at_utc=_DEFAULT_CREATED_AT,
    )


def _invalid_gate_input() -> Stage30_9_3LiveGateInput:
    """Build an INVALID sink input: a well-typed gate input with a BLANK
    candidate id (the adapter fails it closed BEFORE the transport). Pure; no
    I/O, no clock.
    """
    return Stage30_9_3LiveGateInput(
        candidate_id="",
        token_mint="mint-invalid",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref=None,
        created_at_utc=_DEFAULT_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# Public proof entry point: direct three-call sink proof
# ---------------------------------------------------------------------------


def run_stage30_11_3_direct_sink_proof(
    *,
    transport: Optional[Stage30_11RecordingFakePrivateTransport] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_11PrivateSinkResult, ...],
    Stage30_11PrivateSinkProofSummary,
    Stage30_11RecordingFakePrivateTransport,
]:
    """Run the direct three-call private sink proof and return ``(results,
    summary, transport)``.

    With every argument defaulted, a fresh recording fake transport (configured
    to reject the one ``DIRECT_PROOF_REJECT_CANDIDATE_ID`` request) drives the
    Stage 30.11.3 private sink over three deterministic gate inputs: a valid
    accept, a blank-id invalid, and a valid reject. The returned summary tallies
    three requests, one accepted, one rejected-invalid, one transport-failed,
    two transport attempts, one transport accept -- proving the transport is
    reached ONLY for a well-shaped input and that the fake reject is a clean
    transport-failed. Pure / deterministic; reads no clock, no env, no network;
    reserves no real dispatch, sends no Discord, writes no file.
    """
    effective_transport = (
        Stage30_11RecordingFakePrivateTransport(
            created_at_utc=created_at_utc,
            reject_candidate_ids=(DIRECT_PROOF_REJECT_CANDIDATE_ID,),
        )
        if transport is None
        else transport
    )
    sink = make_stage30_11_private_dispatch_sink(
        transport=effective_transport,
        compact_body_builder=build_default_compact_body,
        created_at_utc=created_at_utc,
    )
    inputs = (
        _valid_gate_input(
            candidate_id=DIRECT_PROOF_ACCEPT_CANDIDATE_ID,
            token_mint="mint-accept",
        ),
        _invalid_gate_input(),
        _valid_gate_input(
            candidate_id=DIRECT_PROOF_REJECT_CANDIDATE_ID,
            token_mint="mint-reject",
        ),
    )
    results = tuple(sink(gate_input) for gate_input in inputs)
    summary = summarize_private_sink_results(
        results, created_at_utc=created_at_utc
    )
    return results, summary, effective_transport


# ---------------------------------------------------------------------------
# Public proof entry point: runtime seam integration proof
# ---------------------------------------------------------------------------


def run_stage30_11_3_runtime_integration_proof(
    *,
    transport: Optional[Stage30_11RecordingFakePrivateTransport] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_11RuntimeGateCandidateOutcome, ...],
    Stage30_11RuntimeGateSummary,
    Stage30_11RecordingFakePrivateTransport,
]:
    """Run the committed Stage 30.11.2 runtime seam with the Stage 30.11.3
    private sink injected and return ``(outcomes, summary, transport)``.

    The committed seam runs over the first three candidates of the committed
    Stage 30.11.2 deterministic stream -- a valid dip, a non-dip, and a
    bridge-skip (missing ATH) -- with the Stage 30.11.3 private sink (wrapped for
    seam compatibility) injected as the dispatch sink and an injected constant
    clock (so the wall-clock bound is never tripped). The recording fake
    transport (default empty reject set -> accepts the dip) records EXACTLY one
    attempt, for the dip only: the non-dip is suppressed by the dip gate and the
    bridge-skip by the bridge, so neither reaches the transport. Pure /
    deterministic; reads no clock, no env, no network; reserves no real
    dispatch, sends no Discord, writes no file.
    """
    effective_transport = (
        Stage30_11RecordingFakePrivateTransport(created_at_utc=created_at_utc)
        if transport is None
        else transport
    )
    private_sink = make_stage30_11_private_dispatch_sink(
        transport=effective_transport,
        compact_body_builder=build_default_compact_body,
        created_at_utc=created_at_utc,
    )
    seam_sink = make_runtime_seam_compatible_sink(
        private_sink=private_sink,
        created_at_utc=created_at_utc,
    )
    stream = default_runtime_gate_candidate_stream()[:3]
    config = default_runtime_gate_config(created_at_utc=created_at_utc)
    clock = make_constant_clock(Decimal(0))
    outcomes, summary = run_stage30_11_runtime_gate_seam(
        stream,
        config=config,
        dispatch_sink=seam_sink,
        now_seconds=clock,
        created_at_utc=created_at_utc,
    )
    return outcomes, summary, effective_transport


__all__ = (
    "DIRECT_PROOF_ACCEPT_CANDIDATE_ID",
    "DIRECT_PROOF_REJECT_CANDIDATE_ID",
    "Stage30_11RecordingFakePrivateTransport",
    "run_stage30_11_3_direct_sink_proof",
    "run_stage30_11_3_runtime_integration_proof",
)
