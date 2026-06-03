"""Stage 30.11.5 bounded live runner seam.

The pure, bounded, fail-closed RUNNER that composes the WHOLE committed
dip-gated private dispatch chain over a live candidate source -- the narrowest
end-to-end wiring the prior controlled live ceremony lacked between a real
candidate source and the private operator transport boundary:

    a candidate source (an iterable of existing candidate projections)
      -> the Stage 30.11.5 live-candidate snapshot assembler (per projection;
         a reject never becomes a snapshot)
      -> the committed Stage 30.11.2 runtime gate seam (per assembled snapshot)
        -> the committed Stage 30.11.1 bridge (run BY the seam)
        -> the committed Stage 30.9.3 dip gate (run BY the seam)
        -> the committed Stage 30.11.3 private sink (wrapped for seam
           compatibility, injected as the seam's dispatch sink) ONLY on a gate
           PASS
          -> the Stage 30.11.5 private transport adapter (the sink's injected
             ``transport``)
            -> the INJECTED low-level transport client (a FAKE in this slice)
      -> a Stage 30.11.5 ``Stage30_11_5BoundedRunResult``

The runner enforces HARD bounds so a controlled ceremony cannot run away:
``max_dispatches <= 1`` (the single-send default), ``max_runtime_seconds <= 60``
(measured via an INJECTED clock the committed seam samples; the runner reads no
wall clock), and ``max_candidates <= 10`` (the bounded source pull). A config
above any hard cap fails closed BEFORE composing anything. The source pull is a
single BOUNDED for-loop (it stops at ``max_candidates``); there is NO ``while``
loop, NO daemon, NO background service, NO autorestart loop, and NO routing
beyond the private operator transport boundary -- the only route, reached ONLY
behind a committed dip-gate PASS.

The runner NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER reads a wall clock (``now_seconds`` is
injected), NEVER sends Discord, NEVER reserves a REAL dispatch / performs a real
send, NEVER performs a transport-layer veto, NEVER writes a file, and edits NO
Stage 28 / Stage 29 / Stage 30.3 / Stage 30.4 production file. It composes the
committed Stage 30.11.2 seam + the committed Stage 30.11.3 private sink + the
Stage 30.11.5 assembler / transport adapter (the permitted Stage 30.11 scope
expansion); nothing more. In THIS slice the injected transport client is ALWAYS
a FAKE -- the real private compact dispatch / Discord send is a SEPARATE,
operator-authorized step Stage 30.11.5 does not build.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.5 models + assembler + transport-adapter
    siblings plus the committed Stage 30.11.2 runtime-gate-models + seam and the
    committed Stage 30.11.3 private-sink-adapter siblings the runner composes. No
    other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator /
    Stage 28 suppression / live runner / provider / real transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; the runtime clock is
    injected and timestamps are caller-injected.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Iterable, List, Optional

from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11RuntimeGateConfig,
    is_valid_runtime_gate_config,
)
from PHX2.stage30.stage30_11_2_runtime_gate_seam import (
    run_stage30_11_runtime_gate_seam,
)
from PHX2.stage30.stage30_11_3_private_sink_adapter import (
    build_default_compact_body,
    make_runtime_seam_compatible_sink,
    make_stage30_11_private_dispatch_sink,
)
from PHX2.stage30.stage30_11_5_live_candidate_snapshot_assembler import (
    assemble_stage30_11_5_live_candidate_snapshot,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    ASSEMBLY_DECISION_ASSEMBLED,
    STAGE30_11_5_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_5_DEFAULT_MAX_DISPATCHES,
    STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS,
    STAGE30_11_5_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_5_MAX_DISPATCHES_HARD_CAP,
    STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP,
    Stage30_11_5BoundedRunResult,
    Stage30_11_5BoundedRunSummary,
    Stage30_11_5LiveCandidateAssemblyResult,
)
from PHX2.stage30.stage30_11_5_private_transport_adapter import (
    Stage30_11_5PrivateTransportClient,
    make_stage30_11_5_private_transport_adapter,
)


# The injected runtime clock: a zero-arg callable returning the current
# wall-clock reading in seconds. The runner threads it into the committed Stage
# 30.11.2 seam (which samples it to enforce ``max_runtime_seconds``); the runner
# reads no wall clock of its own.
Stage30_11_5RuntimeClock = Callable[[], Decimal]


# The injected safe compact-body builder the private sink renders the operator
# body with (the committed Stage 30.11.3 ``build_default_compact_body`` default).
Stage30_11_5CompactBodyBuilder = Callable[[Any], str]


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11_5BoundedLiveRunnerError(Exception):
    """Closed-set Stage 30.11.5 bounded live runner error.

    Raised ONLY for a caller-shape failure the runner cannot run with -- a
    runtime config that is not within the HARD bounded-run caps
    (``is_within_bounded_run_caps`` is ``False``): an invalid base config, a
    ``max_dispatches`` above ``1``, a ``max_runtime_seconds`` above ``60``, or a
    ``max_candidates`` above ``10`` would make the bounded controlled run
    undefined, so the runner fails closed BEFORE composing the assembler, the
    seam, the sink, or the transport. Degraded per-candidate VALUES never raise; a
    malformed projection fails closed to an assembler reject. Carries only a
    closed-set reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.5 bounded live runner error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Bounded-run config helpers
# ---------------------------------------------------------------------------


def default_bounded_run_config(
    *,
    created_at_utc: str,
) -> Stage30_11RuntimeGateConfig:
    """Build the default bounded-run runtime config: the single-send dispatch
    default, the 60-second wall-clock cap, and the 10-candidate cap -- exactly the
    HARD ceilings the controlled ceremony requires. Pure; no I/O, no clock.
    """
    return Stage30_11RuntimeGateConfig(
        max_runtime_seconds=Decimal(STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS),
        max_candidates=STAGE30_11_5_DEFAULT_MAX_CANDIDATES,
        max_dispatches=STAGE30_11_5_DEFAULT_MAX_DISPATCHES,
        created_at_utc=created_at_utc,
    )


def is_within_bounded_run_caps(config: object) -> bool:
    """Return ``True`` iff ``config`` is a structurally-valid runtime config whose
    bounds are within the HARD bounded-run caps (``max_dispatches <= 1``,
    ``max_runtime_seconds <= 60``, ``max_candidates <= 10``).

    Pure / TOTAL; never raises. A non-config, an invalid base config (a non-finite
    / non-positive bound), or any bound above a hard cap fails closed to
    ``False`` -- so a controlled run can never be parameterized to dispatch more
    than once, run longer than 60 seconds, or evaluate more than ten candidates.
    ``is_valid_runtime_gate_config`` guarantees the bounds are finite + the right
    type BEFORE the ``<=`` comparisons, so no comparison can signal.
    """
    if not is_valid_runtime_gate_config(config):
        return False
    return (
        config.max_dispatches <= STAGE30_11_5_MAX_DISPATCHES_HARD_CAP
        and config.max_runtime_seconds <= STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP
        and config.max_candidates <= STAGE30_11_5_MAX_CANDIDATES_HARD_CAP
    )


# ---------------------------------------------------------------------------
# Public bounded live runner
# ---------------------------------------------------------------------------


def run_stage30_11_5_bounded_live_runner(
    candidate_source: Iterable[object],
    *,
    transport_client: Stage30_11_5PrivateTransportClient,
    now_seconds: Stage30_11_5RuntimeClock,
    config: Optional[Stage30_11RuntimeGateConfig] = None,
    compact_body_builder: Stage30_11_5CompactBodyBuilder = build_default_compact_body,
    created_at_utc: str,
) -> Stage30_11_5BoundedRunResult:
    """Run one bounded live pass over ``candidate_source`` and return a
    ``Stage30_11_5BoundedRunResult``.

    Pure / deterministic apart from the injected transport client's recording side
    effects; reads no env, no clock, no network (``now_seconds`` is injected);
    reserves no real dispatch, sends no Discord, writes no file, runs no daemon /
    ``while`` loop.

    Fail closed first: if ``config`` (or the default) is not within the HARD
    bounded-run caps the runner raises ``Stage30_11_5BoundedLiveRunnerError``
    BEFORE composing the assembler, the seam, the sink, or the transport --
    nothing is assembled or dispatched on an out-of-bounds config.

    Otherwise it composes the committed Stage 30.11.3 private sink (its
    ``transport`` is the Stage 30.11.5 transport adapter wrapping the injected
    ``transport_client``; wrapped for committed Stage 30.11.2 seam compatibility),
    pulls AT MOST ``max_candidates`` projections from the source (a single bounded
    for-loop), assembles each into a committed Stage 30.11.1 snapshot (a reject
    never becomes a snapshot and so never reaches the seam / transport), runs the
    committed Stage 30.11.2 seam over the assembled snapshots with the injected
    clock, and rolls up the counts. The transport client is reached ONLY for a
    candidate that assembled, bridged, AND passed the committed dip gate -- every
    assembler-reject / bridge-skip / non-dip candidate is suppressed cleanly
    BEFORE it.
    """
    effective_config = (
        default_bounded_run_config(created_at_utc=created_at_utc)
        if config is None
        else config
    )
    if not is_within_bounded_run_caps(effective_config):
        # Fail closed on an out-of-bounds config: assemble nothing, gate nothing,
        # dispatch nothing. A caller-shape failure, not a per-candidate failure.
        raise Stage30_11_5BoundedLiveRunnerError("INVALID_BOUNDED_RUN_CONFIG")

    # ---- Compose the committed Stage 30.11.3 private sink + transport adapter ----
    transport = make_stage30_11_5_private_transport_adapter(
        transport_client=transport_client,
        created_at_utc=created_at_utc,
    )
    private_sink = make_stage30_11_private_dispatch_sink(
        transport=transport,
        compact_body_builder=compact_body_builder,
        created_at_utc=created_at_utc,
    )
    seam_sink = make_runtime_seam_compatible_sink(
        private_sink=private_sink,
        created_at_utc=created_at_utc,
    )

    # ---- Assemble the bounded source into committed Stage 30.11.1 snapshots ----
    #
    # A single BOUNDED for-loop: it pulls AT MOST ``max_candidates`` projections
    # and stops. No ``while`` loop, no daemon, no autorestart. A rejected
    # projection is recorded but never becomes a snapshot, so it never reaches the
    # seam / transport.
    assembly_outcomes: List[Stage30_11_5LiveCandidateAssemblyResult] = []
    snapshots: List[Any] = []
    source_items_seen = 0
    for candidate in candidate_source:
        if source_items_seen >= effective_config.max_candidates:
            break
        source_items_seen += 1
        result = assemble_stage30_11_5_live_candidate_snapshot(
            candidate, created_at_utc=created_at_utc
        )
        assembly_outcomes.append(result)
        if (
            result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
            and result.snapshot is not None
        ):
            snapshots.append(result.snapshot)

    # ---- Run the committed Stage 30.11.2 seam over the assembled snapshots ----
    outcomes, runtime_summary = run_stage30_11_runtime_gate_seam(
        tuple(snapshots),
        config=effective_config,
        dispatch_sink=seam_sink,
        now_seconds=now_seconds,
        created_at_utc=created_at_utc,
    )

    summary = Stage30_11_5BoundedRunSummary(
        source_items_seen=source_items_seen,
        assembled=len(snapshots),
        assembly_rejected=source_items_seen - len(snapshots),
        candidates_seen=runtime_summary.candidates_seen,
        bridged=runtime_summary.bridged,
        gate_passed=runtime_summary.gate_passed,
        dispatch_attempted=runtime_summary.dispatch_attempted,
        dispatch_accepted=runtime_summary.dispatch_accepted,
        suppressed_by_bridge=runtime_summary.suppressed_by_bridge,
        suppressed_by_gate=runtime_summary.suppressed_by_gate,
        stopped_by_candidate_cap=runtime_summary.stopped_by_candidate_cap,
        stopped_by_dispatch_cap=runtime_summary.stopped_by_dispatch_cap,
        stopped_by_runtime_seconds=runtime_summary.stopped_by_runtime_seconds,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_5BoundedRunResult(
        assembly_outcomes=tuple(assembly_outcomes),
        runtime_outcomes=tuple(outcomes),
        summary=summary,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_5RuntimeClock",
    "Stage30_11_5CompactBodyBuilder",
    "Stage30_11_5BoundedLiveRunnerError",
    "default_bounded_run_config",
    "is_within_bounded_run_caps",
    "run_stage30_11_5_bounded_live_runner",
)
