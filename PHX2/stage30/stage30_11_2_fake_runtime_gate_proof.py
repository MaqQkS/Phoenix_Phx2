"""Stage 30.11.2 offline fake runtime gate seam proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.2 runtime
gate seam composes the committed Stage 30.11.1 bridge + the committed Stage
30.9.3 dip gate behind a bounded runtime, using fakes / offline snapshots + an
injected in-memory recording sink + an injected fake clock ONLY. It runs the
REAL seam over a deterministic five-candidate stream and tallies the result:

    a deterministic fake stream of assembled live candidate snapshots
      -> the Stage 30.11.2 runtime gate seam (bridge -> committed dip gate ->
         injected fake sink ONLY on a gate PASS)
      -> a tuple of ``Stage30_11RuntimeGateCandidateOutcome`` + a rolled-up
         ``Stage30_11RuntimeGateSummary`` + the recording fake sink

The deterministic five-candidate default stream isolates exactly one runtime
outcome per candidate:

  1. Tier 1 valid dip-context     -> bridge BRIDGED -> gate PASS ->
                                     DISPATCHED_AFTER_DIP_GATE_PASS (the ONLY
                                     candidate the injected fake sink is called
                                     for)
  2. Tier Unknown non-dip context -> bridge BRIDGED -> gate SKIP ->
                                     SUPPRESSED_BY_DIP_GATE (no dispatch)
  3. missing ATH                  -> bridge SKIP -> SUPPRESSED_BY_BRIDGE
  4. missing migration            -> bridge SKIP -> SUPPRESSED_BY_BRIDGE
  5. malformed candidate_id       -> bridge INVALID -> SUPPRESSED_BY_BRIDGE
                                     (also counted as an invalid input)

So a permissive-bounds baseline run sees five candidates, bridges exactly two,
passes exactly one, attempts + accepts exactly one fake dispatch, suppresses
three by the bridge (one of them an invalid input) and one by the gate -- with
NO real dispatch ever reserved and NO Discord ever sent. Injected fake clocks +
tight caps additionally prove the wall-clock / candidate / dispatch bounds stop
the run deterministically.

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a real
dispatch reservation, NOT a transport-layer veto, and NOT a new readiness gate.
It CONSTRUCTS no filesystem I/O, reads no environment, opens no network
connection, reads no wall clock (every clock is injected), and touches no
Discord / live provider path.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.2 models + seam siblings, the committed Stage
    30.11.1 bridge-models sibling (for the candidate snapshot type), and the
    committed Stage 30.9.3 gate-models sibling (for the injected sink's gate-
    input type). No other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport
    import.
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
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    Stage30_11LiveCandidateSnapshot,
)
from PHX2.stage30.stage30_11_2_runtime_gate_seam import (
    run_stage30_11_runtime_gate_seam,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11FakeDispatchResult,
    Stage30_11RuntimeGateCandidateOutcome,
    Stage30_11RuntimeGateConfig,
    Stage30_11RuntimeGateSummary,
)


# The deterministic caller-injected timestamp for the default scenarios (never
# a wall-clock read). Matches the Stage 30.9.3 / 30.10.2 / 30.11.1 fake-proof
# clocks so the composed proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Injected fake clocks (no wall-clock read)
# ---------------------------------------------------------------------------


class _ConstantClock:
    """A zero-arg callable that always returns the same injected reading."""

    def __init__(self, value: Decimal) -> None:
        self._value = value

    def __call__(self) -> Decimal:
        return self._value


class _SequenceClock:
    """A zero-arg callable that returns each injected reading once, in order,
    then clamps to the last reading. Deterministic; reads no wall clock.
    """

    def __init__(self, values: Tuple[Decimal, ...]) -> None:
        self._values: Tuple[Decimal, ...] = tuple(values)
        self._idx = 0

    def __call__(self) -> Decimal:
        if not self._values:
            return Decimal(0)
        i = self._idx
        if i < len(self._values):
            self._idx += 1
            return self._values[i]
        return self._values[-1]


def make_constant_clock(value: Decimal) -> _ConstantClock:
    """Return an injected clock that always reports ``value`` seconds (so a
    permissive ``max_runtime_seconds`` is never tripped). Pure builder.
    """
    return _ConstantClock(value)


def make_sequence_clock(values: Tuple[Decimal, ...]) -> _SequenceClock:
    """Return an injected clock that reports ``values`` in order (clamping to the
    last). Used to drive a deterministic wall-clock stop. Pure builder.
    """
    return _SequenceClock(values)


# ---------------------------------------------------------------------------
# Injected in-memory recording fake dispatch sink
# ---------------------------------------------------------------------------


class Stage30_11RecordingFakeDispatchSink:
    """An in-memory recording fake dispatch sink for tests / proof ONLY.

    Callable as the seam's injected ``dispatch_sink``. It records the number of
    attempts, the number it accepted, and the candidate ids / token mints it was
    called with, then returns a ``Stage30_11FakeDispatchResult`` ack. It is NOT
    a real dispatch path: it sends NO Discord message, imports NO webhook /
    transport module, writes NO file, reads NO environment, and opens NO network
    connection. The real private compact dispatch path is a SEPARATE, operator-
    authorized step Stage 30.11.2 does not build.

      * ``attempted``     -- count of sink calls.
      * ``accepted``      -- count of accepted attempts.
      * ``candidate_ids`` -- the ordered candidate ids the sink saw.
      * ``token_mints``   -- the ordered token mints the sink saw.
    """

    def __init__(
        self,
        *,
        created_at_utc: str = _DEFAULT_CREATED_AT,
        accept: bool = True,
    ) -> None:
        self._created_at_utc = created_at_utc
        self._accept = accept
        self.attempted: int = 0
        self.accepted: int = 0
        self.candidate_ids: List[str] = []
        self.token_mints: List[str] = []

    def __call__(
        self, gate_input: Stage30_9_3LiveGateInput
    ) -> Stage30_11FakeDispatchResult:
        self.attempted += 1
        self.candidate_ids.append(gate_input.candidate_id)
        self.token_mints.append(gate_input.token_mint)
        accepted = bool(self._accept)
        if accepted:
            self.accepted += 1
        return Stage30_11FakeDispatchResult(
            accepted=accepted,
            candidate_id=gate_input.candidate_id,
            token_mint=gate_input.token_mint,
            created_at_utc=self._created_at_utc,
        )


# ---------------------------------------------------------------------------
# Pure fake snapshot builders
# ---------------------------------------------------------------------------


def _snapshot(
    *,
    candidate_id: str,
    token_mint: str,
    tier_hint: Optional[str],
    drawdown_from_ath: object,
    migration_status: Optional[str],
    ath_status: Optional[str],
    market_context_status: Optional[str] = "PRESENT",
    current_market_cap_usd: object = Decimal("12345.67"),
    post_migration_ath_verified: Optional[bool] = True,
) -> Stage30_11LiveCandidateSnapshot:
    """Build a fake already-assembled live candidate snapshot. All non-isolated
    signals default to the fully-present, dip-ready shape so each fake snapshot
    isolates exactly one runtime outcome. Pure; no I/O, no clock, no provider
    call, no fabrication beyond the explicit fake fields.
    """
    return Stage30_11LiveCandidateSnapshot(
        candidate_id=candidate_id,
        token_mint=token_mint,
        pair_type="SOL",
        tier_hint=tier_hint,
        drawdown_from_ath=drawdown_from_ath,  # type: ignore[arg-type]
        migration_status=migration_status,
        ath_status=ath_status,
        market_context_status=market_context_status,
        current_market_cap_usd=current_market_cap_usd,  # type: ignore[arg-type]
        post_migration_ath_verified=post_migration_ath_verified,
        source_ref=("ref-" + candidate_id) if candidate_id else None,
        created_at_utc=_DEFAULT_CREATED_AT,
    )


def _tier1_dip_context() -> Stage30_11LiveCandidateSnapshot:
    # Tier 1, all context present -> bridge BRIDGED -> gate PASS -> dispatched.
    return _snapshot(
        candidate_id="cand-tier1",
        token_mint="mint-tier1",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _tier_unknown_non_dip_context() -> Stage30_11LiveCandidateSnapshot:
    # Tier Unknown, all context present -> bridge BRIDGED -> gate SKIP (the
    # NON-DIP decision is the gate's, made LATER, not the bridge's).
    return _snapshot(
        candidate_id="cand-unknown",
        token_mint="mint-unknown",
        tier_hint="Tier Unknown",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def _missing_ath() -> Stage30_11LiveCandidateSnapshot:
    # ATH context not present -> bridge SKIP -> SUPPRESSED_BY_BRIDGE.
    return _snapshot(
        candidate_id="cand-no-ath",
        token_mint="mint-no-ath",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status=None,
    )


def _missing_migration() -> Stage30_11LiveCandidateSnapshot:
    # Migration context not present -> bridge SKIP -> SUPPRESSED_BY_BRIDGE.
    return _snapshot(
        candidate_id="cand-no-migration",
        token_mint="mint-no-migration",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status=None,
        ath_status="PRESENT",
    )


def _malformed_candidate_id() -> Stage30_11LiveCandidateSnapshot:
    # Blank candidate_id -> bridge INVALID -> SUPPRESSED_BY_BRIDGE + invalid.
    return _snapshot(
        candidate_id="",
        token_mint="mint-invalid",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
    )


def default_runtime_gate_candidate_stream() -> (
    Tuple[Stage30_11LiveCandidateSnapshot, ...]
):
    """Build the deterministic five-candidate default runtime stream.

    One valid dip-context candidate, one valid non-dip-context candidate, one
    missing-ATH candidate, one missing-migration candidate, and one malformed
    candidate. Pure; no I/O, no clock, no env.
    """
    return (
        _tier1_dip_context(),
        _tier_unknown_non_dip_context(),
        _missing_ath(),
        _missing_migration(),
        _malformed_candidate_id(),
    )


def default_runtime_gate_config(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_11RuntimeGateConfig:
    """Build a permissive baseline runtime config: a large wall-clock cap, a
    candidate cap above the default stream length, and a dispatch cap above the
    one eligible dip -- so the baseline run processes the whole stream and the
    bounds are never tripped. Pure; no I/O, no clock.
    """
    return Stage30_11RuntimeGateConfig(
        max_runtime_seconds=Decimal("3600"),
        max_candidates=100,
        max_dispatches=100,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_2_fake_runtime_gate_proof(
    *,
    candidates: Optional[Tuple[Stage30_11LiveCandidateSnapshot, ...]] = None,
    config: Optional[Stage30_11RuntimeGateConfig] = None,
    sink: Optional[Stage30_11RecordingFakeDispatchSink] = None,
    now_seconds: object = None,
    accept: bool = True,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_11RuntimeGateCandidateOutcome, ...],
    Stage30_11RuntimeGateSummary,
    Stage30_11RecordingFakeDispatchSink,
]:
    """Run the Stage 30.11.2 runtime gate seam over ``candidates`` and return
    ``(outcomes, summary, sink)``.

    With every argument defaulted, the deterministic five-candidate default
    stream is run through the REAL seam with a permissive baseline config, an
    injected constant clock (so the wall-clock bound is never tripped), and a
    fresh in-memory recording sink that accepts every attempt. The returned sink
    exposes the attempts / accepted counts / candidate ids it recorded, proving
    the sink was called ONLY for the single gate-PASS candidate. Pure /
    deterministic; reads no clock, no env, no network; reserves no real dispatch,
    sends no Discord, writes no file.
    """
    stream = (
        default_runtime_gate_candidate_stream()
        if candidates is None
        else candidates
    )
    effective_config = (
        default_runtime_gate_config(created_at_utc=created_at_utc)
        if config is None
        else config
    )
    effective_sink = (
        Stage30_11RecordingFakeDispatchSink(
            created_at_utc=created_at_utc, accept=accept
        )
        if sink is None
        else sink
    )
    clock = (
        make_constant_clock(Decimal(0)) if now_seconds is None else now_seconds
    )

    outcomes, summary = run_stage30_11_runtime_gate_seam(
        stream,
        config=effective_config,
        dispatch_sink=effective_sink,
        now_seconds=clock,
        created_at_utc=created_at_utc,
    )
    return outcomes, summary, effective_sink


__all__ = (
    "make_constant_clock",
    "make_sequence_clock",
    "Stage30_11RecordingFakeDispatchSink",
    "default_runtime_gate_candidate_stream",
    "default_runtime_gate_config",
    "run_stage30_11_2_fake_runtime_gate_proof",
)
