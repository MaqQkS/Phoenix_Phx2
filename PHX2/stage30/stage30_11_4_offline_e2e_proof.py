"""Stage 30.11.4 offline end-to-end proof.

A pure, deterministic, fail-closed helper that PROVES the WHOLE committed
dip-gated private sink chain works offline, by COMPOSING the already-committed
slices (it reimplements none of them):

    the committed Stage 30.11.2 deterministic live-candidate stream
      -> the committed Stage 30.11.1 live candidate bridge (run BY the seam)
      -> the committed Stage 30.11.2 runtime gate seam
      -> the committed Stage 30.9.3 dip-filtered live gate (run BY the seam)
      -> the committed Stage 30.11.3 private sink adapter (wrapped for seam
         compatibility, injected as the seam's dispatch sink)
      -> an INJECTED in-memory recording FAKE private transport
      -> exactly one would-send -- for the PASS dip ONLY

This is the final fake / offline proof before the controlled live ceremony. It
composes the committed modules end to end and asserts, by counting, that the
single Tier 1 dip in the committed default stream bridged, passed the committed
dip gate, drove the private sink, and reached the INJECTED fake transport for an
accepted would-send -- while every non-dip / bridge-skip / invalid candidate was
suppressed cleanly BEFORE the sink and NEVER reached the transport. The Stage
30.11.1 bridge and the Stage 30.9.3 dip gate are exercised TRANSITIVELY (the
committed Stage 30.11.2 seam runs them); this proof reaches them only through the
committed seam, never by reimplementing them.

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a real
dispatch reservation, NOT a real transport, and NOT a new readiness gate / runtime
seam / sink adapter / gate. It constructs no filesystem I/O, reads no environment,
opens no network connection, reads no wall clock (every clock is injected), runs
no daemon / background loop / while loop, and touches no Discord / live provider /
real transport path. The real private compact dispatch / Discord send remains a
SEPARATE, explicitly operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.4 models sibling plus the committed Stage
    30.11.2 runtime seam + fake-proof siblings (for the seam + its deterministic
    default stream / config / clock) and the committed Stage 30.11.3 private sink
    adapter + fake-proof + models siblings (for the private sink factory + the
    seam-compat wrapper + the compact body builder + the result fold + the
    recording fake transport + the result type). No other PHX2 module; no Stage
    21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / real transport / Discord import. The Stage 30.11.1 bridge
    + Stage 30.9.3 gate are composed transitively through the committed seam.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO ``time`` / wall clock / random, NO direct filesystem
    primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    default_runtime_gate_candidate_stream,
    default_runtime_gate_config,
    make_constant_clock,
)
from PHX2.stage30.stage30_11_2_runtime_gate_seam import (
    run_stage30_11_runtime_gate_seam,
)
from PHX2.stage30.stage30_11_3_fake_private_sink_proof import (
    Stage30_11RecordingFakePrivateTransport,
)
from PHX2.stage30.stage30_11_3_private_sink_adapter import (
    build_default_compact_body,
    make_runtime_seam_compatible_sink,
    make_stage30_11_private_dispatch_sink,
    summarize_private_sink_results,
)
from PHX2.stage30.stage30_11_3_private_sink_models import (
    Stage30_11PrivateSinkResult,
)
from PHX2.stage30.stage30_11_4_offline_e2e_proof_models import (
    OFFLINE_E2E_PROOF_FAILED,
    OFFLINE_E2E_PROOF_PASSED,
    PROOF_REASON_INVALID_PROOF_INPUT,
    PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    PROOF_REASON_UNEXPECTED_E2E_COUNTS,
    PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES,
    STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_4_EXPECTED_GATE_PASSES,
    STAGE30_11_4_EXPECTED_GATE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_SINK_ACCEPTS,
    STAGE30_11_4_EXPECTED_SINK_ATTEMPTS,
    STAGE30_11_4_EXPECTED_SINK_FAILURES,
    STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS,
    Stage30_11OfflineE2EProofResult,
    Stage30_11OfflineE2EProofSummary,
    is_nonblank_str,
)


# The deterministic caller-injected timestamp for the default scenario (never a
# wall-clock read). Matches the Stage 30.11.2 / 30.11.3 fake-proof clocks so the
# composed proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Pure shape predicates (for the fail-closed INVALID_PROOF_INPUT guard)
# ---------------------------------------------------------------------------


def _is_nonnegative_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-negative ``int`` (and NOT a
    ``bool``). Pure / total; never raises.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_str_sequence(value: object) -> bool:
    """Return ``True`` iff ``value`` is a list / tuple of ``str``. Pure / total;
    never raises.
    """
    return isinstance(value, (list, tuple)) and all(
        isinstance(item, str) for item in value
    )


# ---------------------------------------------------------------------------
# Recording wrapper around the committed Stage 30.11.3 private dispatch sink
# ---------------------------------------------------------------------------


class _RecordingPrivateSink:
    """A thin recording decorator around a committed Stage 30.11.3 private
    dispatch sink.

    It delegates EVERY call to the wrapped committed sink, records each
    ``Stage30_11PrivateSinkResult`` the committed sink returns, and returns that
    result UNCHANGED. It reimplements NO bridge / gate / sink logic -- it only
    OBSERVES the committed sink, so the rolled-up private sink summary survives
    the Stage 30.11.3 seam-compat wrapper's conversion to the seam's
    fake-dispatch-result type. Pure apart from the wrapped sink's injected
    transport side effects; reads no env, no clock, no network.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.results: List[Stage30_11PrivateSinkResult] = []

    def __call__(self, gate_input) -> Stage30_11PrivateSinkResult:
        result = self._inner(gate_input)
        self.results.append(result)
        return result


# ---------------------------------------------------------------------------
# Pure proof decision
# ---------------------------------------------------------------------------


def decide_stage30_11_4_offline_e2e_proof(
    *,
    candidates_seen: int,
    bridge_successes: int,
    bridge_suppressed: int,
    gate_passes: int,
    gate_suppressed: int,
    sink_attempts: int,
    sink_accepts: int,
    sink_failures: int,
    transport_attempts: int,
    transport_accepts: int,
    runtime_stopped_by_candidate_cap: int,
    runtime_stopped_by_dispatch_cap: int,
    runtime_stopped_by_runtime_seconds: int,
    transport_candidate_ids: Tuple[str, ...],
    transport_token_mints: Tuple[str, ...],
    created_at_utc: str,
) -> Tuple[str, str]:
    """Decide the closed-set ``(proof_decision, proof_reason)`` from the composed
    chain counters.

    Pure / deterministic / total; never raises. Decision precedence (top-down,
    first match wins):

      1. a caller-shape failure (a blank ``created_at_utc``, a malformed count,
         or a malformed transport candidate-id / token-mint sequence) ->
         ``OFFLINE_E2E_PROOF_FAILED`` / ``INVALID_PROOF_INPUT`` (fail closed
         BEFORE judging counts).
      2. the INJECTED fake transport saw an attempt it must never see -- more
         than the one expected dip attempt, or an attempt whose candidate id OR
         token mint is not EXACTLY the expected dip identity ->
         ``OFFLINE_E2E_PROOF_FAILED`` / ``UNEXPECTED_TRANSPORT_ATTEMPT`` (a
         non-dip / bridge-skip / invalid must NEVER reach the transport, and the
         dip's identity is pinned on BOTH the candidate-id and token-mint axes).
      3. any other chain counter did not match the author-verified baseline EXACTLY
         (``candidates_seen`` must equal the pinned baseline -- never merely a
         minimum -- and, for example, the fake transport rejected the dip so the
         accept counts are short) -> ``OFFLINE_E2E_PROOF_FAILED`` /
         ``UNEXPECTED_E2E_COUNTS``.
      4. otherwise -> ``OFFLINE_E2E_PROOF_PASSED`` /
         ``PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY``.
    """
    # ---- 1. Fail closed on a caller-shape failure ----
    if not is_nonblank_str(created_at_utc):
        return OFFLINE_E2E_PROOF_FAILED, PROOF_REASON_INVALID_PROOF_INPUT
    counts = (
        candidates_seen,
        bridge_successes,
        bridge_suppressed,
        gate_passes,
        gate_suppressed,
        sink_attempts,
        sink_accepts,
        sink_failures,
        transport_attempts,
        transport_accepts,
        runtime_stopped_by_candidate_cap,
        runtime_stopped_by_dispatch_cap,
        runtime_stopped_by_runtime_seconds,
    )
    if not all(_is_nonnegative_int(count) for count in counts):
        return OFFLINE_E2E_PROOF_FAILED, PROOF_REASON_INVALID_PROOF_INPUT
    if not _is_str_sequence(transport_candidate_ids):
        return OFFLINE_E2E_PROOF_FAILED, PROOF_REASON_INVALID_PROOF_INPUT
    if not _is_str_sequence(transport_token_mints):
        return OFFLINE_E2E_PROOF_FAILED, PROOF_REASON_INVALID_PROOF_INPUT

    # ---- 2. The fake transport must have seen EXACTLY the one expected dip ----
    #
    # The dip identity is pinned on BOTH the candidate-id AND the token-mint
    # axis: a wrong candidate id OR a wrong token mint (or an extra attempt) is
    # an UNEXPECTED_TRANSPORT_ATTEMPT.
    if (
        transport_attempts != STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS
        or tuple(transport_candidate_ids)
        != (STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,)
        or tuple(transport_token_mints)
        != (STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,)
    ):
        return (
            OFFLINE_E2E_PROOF_FAILED,
            PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
        )

    # ---- 3. Every other chain counter must match the baseline EXACTLY ----
    if (
        candidates_seen != STAGE30_11_4_EXPECTED_CANDIDATES_SEEN
        or bridge_successes != STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES
        or bridge_suppressed != STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED
        or gate_passes != STAGE30_11_4_EXPECTED_GATE_PASSES
        or gate_suppressed != STAGE30_11_4_EXPECTED_GATE_SUPPRESSED
        or sink_attempts != STAGE30_11_4_EXPECTED_SINK_ATTEMPTS
        or sink_accepts != STAGE30_11_4_EXPECTED_SINK_ACCEPTS
        or sink_failures != STAGE30_11_4_EXPECTED_SINK_FAILURES
        or transport_accepts != STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS
        or runtime_stopped_by_candidate_cap != 0
        or runtime_stopped_by_dispatch_cap != 0
        or runtime_stopped_by_runtime_seconds != 0
    ):
        return OFFLINE_E2E_PROOF_FAILED, PROOF_REASON_UNEXPECTED_E2E_COUNTS

    # ---- 4. The whole committed chain matched the baseline ----
    return (
        OFFLINE_E2E_PROOF_PASSED,
        PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    )


# ---------------------------------------------------------------------------
# Pure builder: the fail-closed INVALID_PROOF_INPUT result
# ---------------------------------------------------------------------------


def _invalid_input_result(created_at_utc: object) -> Stage30_11OfflineE2EProofResult:
    """Build the fail-closed ``INVALID_PROOF_INPUT`` result WITHOUT composing the
    chain. Pure; no I/O. Used when ``created_at_utc`` is not a usable timestamp,
    so nothing is bridged / gated / dispatched.
    """
    safe_created = created_at_utc if isinstance(created_at_utc, str) else ""
    summary = Stage30_11OfflineE2EProofSummary(
        candidates_seen=0,
        bridge_successes=0,
        bridge_suppressed=0,
        gate_passes=0,
        gate_suppressed=0,
        sink_attempts=0,
        sink_accepts=0,
        sink_failures=0,
        transport_attempts=0,
        transport_accepts=0,
        runtime_stopped_by_candidate_cap=0,
        runtime_stopped_by_dispatch_cap=0,
        runtime_stopped_by_runtime_seconds=0,
        proof_decision=OFFLINE_E2E_PROOF_FAILED,
        proof_reason=PROOF_REASON_INVALID_PROOF_INPUT,
        created_at_utc=safe_created,
    )
    return Stage30_11OfflineE2EProofResult(
        proof_decision=OFFLINE_E2E_PROOF_FAILED,
        proof_reason=PROOF_REASON_INVALID_PROOF_INPUT,
        summary=summary,
        runtime_outcomes=(),
        transport_candidate_ids=(),
        transport_token_mints=(),
        created_at_utc=safe_created,
    )


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_4_offline_e2e_proof(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
    transport: Optional[Stage30_11RecordingFakePrivateTransport] = None,
    candidates: Optional[Tuple[object, ...]] = None,
) -> Stage30_11OfflineE2EProofResult:
    """Compose the committed chain end to end over the committed default stream
    and return a ``Stage30_11OfflineE2EProofResult``.

    With every argument defaulted, the committed Stage 30.11.2 deterministic
    five-candidate default stream is run through the committed Stage 30.11.2
    runtime seam with the committed Stage 30.11.3 private sink (wrapped for seam
    compatibility) injected as the dispatch sink, an injected constant clock (so
    the wall-clock bound is never tripped), and a fresh in-memory recording FAKE
    private transport (default empty reject set -> accepts the dip). The composed
    run drives EXACTLY one fake transport attempt -- for the Tier 1 dip
    (``cand-tier1`` / ``mint-tier1``) ONLY; the non-dip is suppressed by the
    committed dip gate and the two bridge-skips + the invalid candidate by the
    bridge, so none reaches the transport.

    Optional ``transport`` injects a different recording fake transport (for the
    negative proof a rejecting transport drives an ``UNEXPECTED_E2E_COUNTS``
    failure); optional ``candidates`` overrides the stream. A blank
    ``created_at_utc`` fails closed to an ``INVALID_PROOF_INPUT`` result WITHOUT
    composing the chain.

    Pure / deterministic apart from the injected fake transport's recording side
    effects; reads no clock, no env, no network; reserves no real dispatch, sends
    no Discord, writes no file, runs no daemon / while loop. The Stage 30.11.1
    bridge + Stage 30.9.3 dip gate are exercised TRANSITIVELY through the
    committed seam; this proof reimplements none of the composed slices.
    """
    # ---- Fail closed on a caller-shape failure BEFORE composing anything ----
    if not is_nonblank_str(created_at_utc):
        return _invalid_input_result(created_at_utc)

    # ---- Compose the committed Stage 30.11.3 private sink + fake transport ----
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
    recording_sink = _RecordingPrivateSink(private_sink)
    seam_sink = make_runtime_seam_compatible_sink(
        private_sink=recording_sink,
        created_at_utc=created_at_utc,
    )

    # ---- Compose the committed Stage 30.11.2 runtime seam over the stream ----
    stream = (
        default_runtime_gate_candidate_stream()
        if candidates is None
        else candidates
    )
    config = default_runtime_gate_config(created_at_utc=created_at_utc)
    clock = make_constant_clock(Decimal(0))
    outcomes, runtime_summary = run_stage30_11_runtime_gate_seam(
        stream,
        config=config,
        dispatch_sink=seam_sink,
        now_seconds=clock,
        created_at_utc=created_at_utc,
    )

    # ---- Fold the recorded committed private sink results ----
    sink_summary = summarize_private_sink_results(
        recording_sink.results, created_at_utc=created_at_utc
    )
    sink_attempts = sink_summary.requests_seen
    sink_accepts = sink_summary.accepted
    sink_failures = sink_summary.rejected_invalid + sink_summary.transport_failed

    transport_candidate_ids = tuple(effective_transport.candidate_ids)
    transport_token_mints = tuple(effective_transport.token_mints)

    # ---- Judge the composed run ----
    proof_decision, proof_reason = decide_stage30_11_4_offline_e2e_proof(
        candidates_seen=runtime_summary.candidates_seen,
        bridge_successes=runtime_summary.bridged,
        bridge_suppressed=runtime_summary.suppressed_by_bridge,
        gate_passes=runtime_summary.gate_passed,
        gate_suppressed=runtime_summary.suppressed_by_gate,
        sink_attempts=sink_attempts,
        sink_accepts=sink_accepts,
        sink_failures=sink_failures,
        transport_attempts=effective_transport.attempted,
        transport_accepts=effective_transport.accepted,
        runtime_stopped_by_candidate_cap=(
            runtime_summary.stopped_by_candidate_cap
        ),
        runtime_stopped_by_dispatch_cap=runtime_summary.stopped_by_dispatch_cap,
        runtime_stopped_by_runtime_seconds=(
            runtime_summary.stopped_by_runtime_seconds
        ),
        transport_candidate_ids=transport_candidate_ids,
        transport_token_mints=transport_token_mints,
        created_at_utc=created_at_utc,
    )

    summary = Stage30_11OfflineE2EProofSummary(
        candidates_seen=runtime_summary.candidates_seen,
        bridge_successes=runtime_summary.bridged,
        bridge_suppressed=runtime_summary.suppressed_by_bridge,
        gate_passes=runtime_summary.gate_passed,
        gate_suppressed=runtime_summary.suppressed_by_gate,
        sink_attempts=sink_attempts,
        sink_accepts=sink_accepts,
        sink_failures=sink_failures,
        transport_attempts=effective_transport.attempted,
        transport_accepts=effective_transport.accepted,
        runtime_stopped_by_candidate_cap=(
            runtime_summary.stopped_by_candidate_cap
        ),
        runtime_stopped_by_dispatch_cap=runtime_summary.stopped_by_dispatch_cap,
        runtime_stopped_by_runtime_seconds=(
            runtime_summary.stopped_by_runtime_seconds
        ),
        proof_decision=proof_decision,
        proof_reason=proof_reason,
        created_at_utc=created_at_utc,
    )
    return Stage30_11OfflineE2EProofResult(
        proof_decision=proof_decision,
        proof_reason=proof_reason,
        summary=summary,
        runtime_outcomes=tuple(outcomes),
        transport_candidate_ids=transport_candidate_ids,
        transport_token_mints=transport_token_mints,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "decide_stage30_11_4_offline_e2e_proof",
    "run_stage30_11_4_offline_e2e_proof",
)
