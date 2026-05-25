"""Stage 29.4 short-session private soak orchestrator.

Bounded outer-loop entry point that wraps the Stage 29.3 single-
shot first-private-tradeable-smoke orchestrator. The orchestrator
runs the Stage 29.3 chain up to the operator-supplied caps,
maintains a cross-pass in-memory dedupe index, and emits the
four Stage 29.4 acceptance artifacts.

The orchestrator NEVER:

  * loops without bounds (every axis is capped),
  * runs unattended (the operator drives the ceremony),
  * activates Stage 26 / Stage 29 enforcement,
  * routes to public / subscriber / paid-tier audiences,
  * sends a Telegram or X / social message,
  * touches a wallet / private-key / signer surface,
  * sizes or executes a trade,
  * imports a Pump.fun bonding-curve decoder,
  * uses Dexscreener as a dispatch authority,
  * uses Helius as a price source,
  * introduces a daemon / watchdog / autorestart loop,
  * uses ``time.sleep`` for pacing, threading, asyncio, subprocess,
    multiprocessing, or signal handlers,
  * persists the dedupe index to disk,
  * reads ``os.environ`` / ``os.getenv`` / ``os.environb``
    directly. Env access flows through the unchanged Stage 28.11
    + Stage 29.2 readiness boundaries via the operator-supplied
    Stage 29.3 entry point.

Dependency injection (DI) seam:

  The orchestrator delegates the per-pass Stage 29.3 single-shot
  ceremony to a caller-supplied ``pass_entrypoint`` callable that
  returns a ``Stage29_4PassResult`` envelope. Tests inject fakes
  that return controlled outcomes; production wiring builds a
  wrapper around ``run_stage29_3_first_private_tradeable_smoke``
  that derives the Stage 29.4 cross-pass dedupe key from the
  candidate the Stage 29.3 chain processed. The orchestrator is
  agnostic to the pass implementation; it consumes only the
  closed-set Stage 29.3 outcome token + the optional dedupe key
  candidate.

Discipline:

  * Stdlib only (``dataclasses`` / ``datetime`` / ``pathlib`` /
    ``typing``). No third-party HTTP / RPC / Discord library.
  * The orchestrator never composes Stage 29.3 / 29.2 / 29.1 / 27
    surfaces directly; every external touch is delegated to the
    operator-supplied ``pass_entrypoint``.
  * The orchestrator never fabricates a price, ATH, hint, base
    mint, or candidate verdict; every axis flows from the
    per-pass entrypoint's returned smoke result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol

from PHX2.stage29.stage29_4_dedupe_index import (
    Stage29_4SoakDedupeIndex,
    build_dedupe_index,
)
from PHX2.stage29.stage29_4_soak_artifact_writer import (
    append_heartbeat_artifact,
    write_health_snapshot_artifact,
    write_soak_summary_bundle,
)
from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    DEDUPE_OUTCOME_NEW,
    PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN,
    SOAK_OUTCOME_BROKE_ON_FAILED_PASS,
    SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS,
    SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT,
    SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP,
    SOAK_OUTCOME_COMPLETED_AT_PASS_CAP,
    SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK,
    SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS,
    SOAK_OUTCOME_REFUSED_INVALID_BOUNDS,
    Stage29_4PassResult,
    Stage29_4SoakBounds,
    Stage29_4SoakDedupeKey,
    Stage29_4SoakError,
    Stage29_4SoakSummary,
    bounds_within_recommended_ranges,
    build_pass_record,
    build_soak_summary,
)


# ---------------------------------------------------------------------------
# Closed-set Stage 29.3 outcome tokens the orchestrator observes
# ---------------------------------------------------------------------------


# The orchestrator never imports the Stage 29.3 smoke-models
# module; instead it pins the closed-set token strings it reacts
# to. This keeps the orchestrator decoupled from the Stage 29.3
# implementation surface (tests inject fakes that return arbitrary
# smoke-result-shaped objects).
_STAGE29_3_OUTCOME_DISPATCHED: str = "DISPATCHED"
_STAGE29_3_OUTCOME_NO_EVENT_RECEIVED: str = "NO_EVENT_RECEIVED"
_STAGE29_3_OUTCOME_REFUSED: str = "REFUSED"
_STAGE29_3_OUTCOME_FAILED: str = "FAILED"


_STAGE29_3_OUTCOME_SUPPRESSED_UNKNOWN_PAIR: str = (
    "SUPPRESSED_UNKNOWN_PAIR"
)
_STAGE29_3_OUTCOME_SUPPRESSED_DISAGREE_PAIR: str = (
    "SUPPRESSED_DISAGREE_PAIR"
)
_STAGE29_3_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY: str = (
    "SUPPRESSED_USDC_OBSERVE_ONLY"
)
_STAGE29_3_OUTCOME_SUPPRESSED_MISSING_PRICE: str = (
    "SUPPRESSED_MISSING_PRICE"
)
_STAGE29_3_OUTCOME_SUPPRESSED_STALE_PRICE: str = (
    "SUPPRESSED_STALE_PRICE"
)
_STAGE29_3_OUTCOME_SUPPRESSED_MALFORMED: str = (
    "SUPPRESSED_MALFORMED"
)


_SUPPRESSED_OUTCOME_TOKENS: tuple[str, ...] = (
    _STAGE29_3_OUTCOME_SUPPRESSED_UNKNOWN_PAIR,
    _STAGE29_3_OUTCOME_SUPPRESSED_DISAGREE_PAIR,
    _STAGE29_3_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY,
    _STAGE29_3_OUTCOME_SUPPRESSED_MISSING_PRICE,
    _STAGE29_3_OUTCOME_SUPPRESSED_STALE_PRICE,
    _STAGE29_3_OUTCOME_SUPPRESSED_MALFORMED,
)


_SUPPRESSED_OUTCOME_TO_COUNTER_NAME: dict[str, str] = {
    _STAGE29_3_OUTCOME_SUPPRESSED_UNKNOWN_PAIR: (
        "suppressed_unknown_pair_count"
    ),
    _STAGE29_3_OUTCOME_SUPPRESSED_DISAGREE_PAIR: (
        "suppressed_disagree_pair_count"
    ),
    _STAGE29_3_OUTCOME_SUPPRESSED_USDC_OBSERVE_ONLY: (
        "suppressed_usdc_observe_only_count"
    ),
    _STAGE29_3_OUTCOME_SUPPRESSED_MISSING_PRICE: (
        "suppressed_missing_price_count"
    ),
    _STAGE29_3_OUTCOME_SUPPRESSED_STALE_PRICE: (
        "suppressed_stale_price_count"
    ),
    _STAGE29_3_OUTCOME_SUPPRESSED_MALFORMED: (
        "suppressed_malformed_count"
    ),
}


# Closed-set refusal reason that maps Stage 29.3 ``REFUSED`` to
# the Stage 29.4 ``BROKE_ON_REFUSED_READINESS`` outcome on the
# soak's first pass.
_REFUSAL_REASON_NONE: str = "NONE"


# ---------------------------------------------------------------------------
# Clock Protocol
# ---------------------------------------------------------------------------


class Stage29_4Clock(Protocol):
    """Clock Protocol the orchestrator uses for wall-clock checks
    and UTC ISO-8601 timestamp generation.

    The orchestrator never imports ``time``; it relies entirely
    on this Protocol. Tests inject a deterministic fake clock that
    returns a pre-configured sequence of times; production wiring
    uses a real UTC clock.

    Implementations MUST satisfy:

      * ``utc_now() -> datetime`` -- the current UTC ``datetime``
        (tz-aware, ``tzinfo=timezone.utc``).
      * ``now_utc_iso() -> str`` -- the current UTC time as a
        safe-shape ISO-8601 string.
    """

    def utc_now(self) -> datetime:  # pragma: no cover - Protocol
        ...

    def now_utc_iso(self) -> str:  # pragma: no cover - Protocol
        ...


class Stage29_4UtcClock:
    """Reference Stage 29.4 UTC clock implementation.

    Pure stdlib (``datetime.datetime.now(timezone.utc)``). Tests
    typically inject a deterministic fake clock instead.
    """

    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_utc_iso(self) -> str:
        return self.utc_now().isoformat()


# ---------------------------------------------------------------------------
# Pass-entrypoint Protocol (the DI seam)
# ---------------------------------------------------------------------------


class Stage29_4PassEntrypoint(Protocol):
    """Stage 29.4 per-pass entrypoint Protocol.

    Each pass invocation runs the Stage 29.3 single-shot ceremony
    once and returns a ``Stage29_4PassResult`` envelope carrying
    the Stage 29.3 smoke result plus the optional cross-pass
    dedupe key candidate the entrypoint derived for the candidate
    that was processed on this pass (``None`` when no dispatchable
    candidate was observed).

    Tests inject fakes that return controlled envelopes; the
    operator-driven production wiring builds a thin wrapper around
    ``run_stage29_3_first_private_tradeable_smoke``.
    """

    def __call__(
        self,
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ) -> Stage29_4PassResult:  # pragma: no cover - Protocol
        ...


# ---------------------------------------------------------------------------
# Internal soak-state record (mutable across the loop)
# ---------------------------------------------------------------------------


@dataclass
class _SoakState:
    """Mutable per-soak state the orchestrator updates each pass.

    Internal; not exported. Final values are projected onto the
    immutable ``Stage29_4SoakSummary`` at soak stop.
    """

    passes_attempted: int = 0
    dispatch_success_total: int = 0
    dispatch_failure_total: int = 0
    duplicate_suppressed_soak_count: int = 0
    events_seen_total: int = 0
    suppressed_unknown_pair_count: int = 0
    suppressed_disagree_pair_count: int = 0
    suppressed_usdc_observe_only_count: int = 0
    suppressed_missing_price_count: int = 0
    suppressed_stale_price_count: int = 0
    suppressed_malformed_count: int = 0
    no_event_received_count: int = 0
    consecutive_suppression_streak: int = 0
    consecutive_suppression_streak_max: int = 0
    last_dedupe_outcome: Optional[str] = None
    last_stage29_3_outcome: Optional[str] = None


# ---------------------------------------------------------------------------
# Smoke-result projection (duck-typed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SmokeResultProjection:
    """Internal projection of the duck-typed smoke result fields
    the orchestrator reads.

    Tests can pass any object exposing these attributes; production
    Stage 29.3 ``Stage29_3TradeableSmokeResult`` records satisfy
    the projection by construction.
    """

    tradeable_smoke_outcome: str
    tradeable_smoke_refusal_reason: str
    events_seen: int
    candidates_dispatched: int
    candidates_suppressed: int
    dispatch_success: int
    dispatch_failure: int


def _project_smoke_result(
    smoke_result: object,
) -> _SmokeResultProjection:
    """Project a duck-typed smoke result onto the closed-set
    projection.

    Raises ``Stage29_4SoakError`` when a required field is missing
    or has the wrong type.
    """
    fields = (
        "tradeable_smoke_outcome",
        "tradeable_smoke_refusal_reason",
        "events_seen",
        "candidates_dispatched",
        "candidates_suppressed",
        "dispatch_success",
        "dispatch_failure",
    )
    for name in fields:
        if not hasattr(smoke_result, name):
            raise Stage29_4SoakError(
                f"SMOKE_RESULT_MISSING_FIELD::{name}",
            )
    outcome = getattr(smoke_result, "tradeable_smoke_outcome")
    refusal = getattr(
        smoke_result, "tradeable_smoke_refusal_reason",
    )
    if not isinstance(outcome, str):
        raise Stage29_4SoakError(
            "SMOKE_RESULT_OUTCOME_NOT_STR",
        )
    if not isinstance(refusal, str):
        raise Stage29_4SoakError(
            "SMOKE_RESULT_REFUSAL_REASON_NOT_STR",
        )
    counters: dict[str, int] = {}
    for name in (
        "events_seen",
        "candidates_dispatched",
        "candidates_suppressed",
        "dispatch_success",
        "dispatch_failure",
    ):
        value = getattr(smoke_result, name)
        if isinstance(value, bool) or not isinstance(
            value, int,
        ) or value < 0:
            raise Stage29_4SoakError(
                f"SMOKE_RESULT_COUNTER_NOT_NONNEG_INT::{name}",
            )
        counters[name] = value
    return _SmokeResultProjection(
        tradeable_smoke_outcome=outcome,
        tradeable_smoke_refusal_reason=refusal,
        events_seen=counters["events_seen"],
        candidates_dispatched=counters["candidates_dispatched"],
        candidates_suppressed=counters["candidates_suppressed"],
        dispatch_success=counters["dispatch_success"],
        dispatch_failure=counters["dispatch_failure"],
    )


# ---------------------------------------------------------------------------
# Bounds validation
# ---------------------------------------------------------------------------


def _bounds_are_valid(bounds: object) -> bool:
    """Return ``True`` iff ``bounds`` is a ``Stage29_4SoakBounds``
    instance constructed via the locked validator. Defensive
    because the bounds record is the public API axis.
    """
    return isinstance(bounds, Stage29_4SoakBounds)


# ---------------------------------------------------------------------------
# Public soak entrypoint
# ---------------------------------------------------------------------------


def run_stage29_4_short_session_private_soak(
    *,
    bounds: Stage29_4SoakBounds,
    output_dir: Path,
    pass_entrypoint: Stage29_4PassEntrypoint,
    mode: str = (
        PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN
    ),
    clock: Optional[Stage29_4Clock] = None,
    dedupe_index: Optional[Stage29_4SoakDedupeIndex] = None,
    write_artifacts: bool = True,
) -> Stage29_4SoakSummary:
    """Run one Stage 29.4 bounded short-session private soak
    ceremony.

    The orchestrator validates the operator-supplied bounds,
    drives the per-pass entrypoint in a bounded outer loop,
    maintains a cross-pass in-memory dedupe index, and (when
    ``write_artifacts=True``) writes the four Stage 29.4
    acceptance artifacts into ``output_dir`` at soak stop.

    Returns an immutable ``Stage29_4SoakSummary`` carrying one of
    the closed-set Stage 29.4 soak outcomes:

      * ``COMPLETED_AT_DISPATCH_CAP``
      * ``COMPLETED_AT_WALL_CLOCK``
      * ``COMPLETED_AT_PASS_CAP``
      * ``BROKE_ON_SUPPRESSION_CIRCUIT``
      * ``BROKE_ON_REFUSED_READINESS``
      * ``BROKE_ON_FAILED_PASS``
      * ``NO_DISPATCHES_NO_EVENTS``
      * ``REFUSED_INVALID_BOUNDS``

    Discipline:

      * The orchestrator NEVER raises an exception out of the
        loop; every refusal / failure projects onto a closed-set
        soak outcome and a well-formed summary record.
      * The orchestrator NEVER sleeps or yields control; it
        polls the clock between passes and exits when any bound
        fires.
      * The dedupe index is local to this call and is garbage-
        collected at function return.
    """
    resolved_clock = (
        clock if clock is not None else Stage29_4UtcClock()
    )

    # The orchestrator accepts only mode 3
    # (``SHORT_SESSION_PRIVATE_SOAK_DRY_RUN``). Modes 1 / 2 are
    # documented as aliases of the Stage 29.3 single-shot modes;
    # the operator calls the Stage 29.3 entrypoint directly for
    # those modes. A call against an unrecognized mode token
    # projects onto ``REFUSED_INVALID_BOUNDS`` for compatibility.
    if mode != PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN:
        return _build_invalid_bounds_summary(
            bounds=bounds,
            clock=resolved_clock,
        )

    if not _bounds_are_valid(bounds):
        return _build_invalid_bounds_summary(
            bounds=bounds,
            clock=resolved_clock,
        )

    if not isinstance(output_dir, Path):
        return _build_invalid_bounds_summary(
            bounds=bounds,
            clock=resolved_clock,
        )

    if pass_entrypoint is None or not callable(
        pass_entrypoint,
    ):
        return _build_invalid_bounds_summary(
            bounds=bounds,
            clock=resolved_clock,
        )

    index = (
        dedupe_index
        if dedupe_index is not None
        else build_dedupe_index()
    )
    state = _SoakState()
    start_dt = resolved_clock.utc_now()
    start_iso = resolved_clock.now_utc_iso()

    soak_outcome: Optional[str] = None
    last_pass_record = None

    for pass_index in range(1, bounds.max_passes + 1):
        # Wall-clock pre-check: if elapsed >= wall_clock_seconds
        # the soak completes with COMPLETED_AT_WALL_CLOCK BEFORE
        # running another pass.
        now_dt = resolved_clock.utc_now()
        elapsed = (now_dt - start_dt).total_seconds()
        if elapsed >= float(bounds.wall_clock_seconds):
            soak_outcome = SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK
            break

        state.passes_attempted += 1
        try:
            pass_result = pass_entrypoint(
                pass_index=pass_index,
                bounds=bounds,
                soak_output_dir=output_dir,
            )
        except Stage29_4SoakError:
            soak_outcome = SOAK_OUTCOME_BROKE_ON_FAILED_PASS
            break
        if not isinstance(pass_result, Stage29_4PassResult):
            soak_outcome = SOAK_OUTCOME_BROKE_ON_FAILED_PASS
            break

        try:
            projection = _project_smoke_result(
                pass_result.smoke_result,
            )
        except Stage29_4SoakError:
            soak_outcome = SOAK_OUTCOME_BROKE_ON_FAILED_PASS
            break

        # Aggregate Stage 29.3 counter axes.
        state.events_seen_total += projection.events_seen
        state.dispatch_failure_total += (
            projection.dispatch_failure
        )

        dedupe_outcome_for_pass: Optional[str] = None

        outcome = projection.tradeable_smoke_outcome
        if outcome == _STAGE29_3_OUTCOME_FAILED:
            state.last_stage29_3_outcome = outcome
            state.consecutive_suppression_streak = 0
            now_iso = resolved_clock.now_utc_iso()
            pass_elapsed = (
                resolved_clock.utc_now() - start_dt
            ).total_seconds()
            last_pass_record = build_pass_record(
                pass_index=pass_index,
                stage29_3_outcome=outcome,
                stage29_3_refusal_reason=(
                    projection.tradeable_smoke_refusal_reason
                ),
                dedupe_outcome=None,
                events_seen=projection.events_seen,
                candidates_dispatched=(
                    projection.candidates_dispatched
                ),
                candidates_suppressed=(
                    projection.candidates_suppressed
                ),
                dispatch_success=projection.dispatch_success,
                dispatch_failure=projection.dispatch_failure,
                consecutive_suppression_streak=(
                    state.consecutive_suppression_streak
                ),
                dispatch_success_total_at_tick=(
                    state.dispatch_success_total
                ),
                duplicate_suppressed_soak_count_at_tick=(
                    state.duplicate_suppressed_soak_count
                ),
                elapsed_at_tick_seconds=pass_elapsed,
                utc_iso_timestamp=now_iso,
            )
            if write_artifacts:
                _safe_append_heartbeat(
                    output_dir=output_dir,
                    record=last_pass_record,
                )
                _safe_write_health_snapshot(
                    output_dir=output_dir,
                    record=last_pass_record,
                    bounds_within_recommended=(
                        bounds_within_recommended_ranges(
                            bounds
                        )
                    ),
                )
            soak_outcome = SOAK_OUTCOME_BROKE_ON_FAILED_PASS
            break

        if outcome == _STAGE29_3_OUTCOME_REFUSED:
            state.last_stage29_3_outcome = outcome
            state.consecutive_suppression_streak = 0
            now_iso = resolved_clock.now_utc_iso()
            pass_elapsed = (
                resolved_clock.utc_now() - start_dt
            ).total_seconds()
            last_pass_record = build_pass_record(
                pass_index=pass_index,
                stage29_3_outcome=outcome,
                stage29_3_refusal_reason=(
                    projection.tradeable_smoke_refusal_reason
                ),
                dedupe_outcome=None,
                events_seen=projection.events_seen,
                candidates_dispatched=(
                    projection.candidates_dispatched
                ),
                candidates_suppressed=(
                    projection.candidates_suppressed
                ),
                dispatch_success=projection.dispatch_success,
                dispatch_failure=projection.dispatch_failure,
                consecutive_suppression_streak=(
                    state.consecutive_suppression_streak
                ),
                dispatch_success_total_at_tick=(
                    state.dispatch_success_total
                ),
                duplicate_suppressed_soak_count_at_tick=(
                    state.duplicate_suppressed_soak_count
                ),
                elapsed_at_tick_seconds=pass_elapsed,
                utc_iso_timestamp=now_iso,
            )
            if write_artifacts:
                _safe_append_heartbeat(
                    output_dir=output_dir,
                    record=last_pass_record,
                )
                _safe_write_health_snapshot(
                    output_dir=output_dir,
                    record=last_pass_record,
                    bounds_within_recommended=(
                        bounds_within_recommended_ranges(
                            bounds
                        )
                    ),
                )
            if pass_index == 1:
                soak_outcome = (
                    SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS
                )
            else:
                soak_outcome = (
                    SOAK_OUTCOME_BROKE_ON_FAILED_PASS
                )
            break

        if outcome == _STAGE29_3_OUTCOME_DISPATCHED:
            state.consecutive_suppression_streak = 0
            if pass_result.dedupe_key is None:
                # Defensive: a DISPATCHED outcome should always
                # come with a dedupe key candidate. Treat the
                # missing-key case as DUPLICATE_SUPPRESSED so the
                # soak does not double-count an undeduplicated
                # dispatch toward the dispatch cap.
                dedupe_outcome_for_pass = (
                    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK
                )
                state.duplicate_suppressed_soak_count += 1
            else:
                if not isinstance(
                    pass_result.dedupe_key,
                    Stage29_4SoakDedupeKey,
                ):
                    soak_outcome = (
                        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
                    )
                    break
                consumed = index.consume(
                    pass_result.dedupe_key,
                )
                dedupe_outcome_for_pass = consumed
                if consumed == DEDUPE_OUTCOME_NEW:
                    state.dispatch_success_total += 1
                else:
                    state.duplicate_suppressed_soak_count += 1
        elif outcome == _STAGE29_3_OUTCOME_NO_EVENT_RECEIVED:
            state.no_event_received_count += 1
            state.consecutive_suppression_streak = 0
        elif outcome in _SUPPRESSED_OUTCOME_TOKENS:
            counter_name = _SUPPRESSED_OUTCOME_TO_COUNTER_NAME[
                outcome
            ]
            setattr(
                state,
                counter_name,
                getattr(state, counter_name) + 1,
            )
            state.consecutive_suppression_streak += 1
            if (
                state.consecutive_suppression_streak
                > state.consecutive_suppression_streak_max
            ):
                state.consecutive_suppression_streak_max = (
                    state.consecutive_suppression_streak
                )
        else:
            # Unknown / non-closed-set outcome token: treat as
            # FAILED defensively.
            soak_outcome = SOAK_OUTCOME_BROKE_ON_FAILED_PASS
            # Still emit a heartbeat record below.
            state.last_stage29_3_outcome = outcome
            now_iso = resolved_clock.now_utc_iso()
            pass_elapsed = (
                resolved_clock.utc_now() - start_dt
            ).total_seconds()
            last_pass_record = build_pass_record(
                pass_index=pass_index,
                stage29_3_outcome=outcome,
                stage29_3_refusal_reason=(
                    projection.tradeable_smoke_refusal_reason
                ),
                dedupe_outcome=None,
                events_seen=projection.events_seen,
                candidates_dispatched=(
                    projection.candidates_dispatched
                ),
                candidates_suppressed=(
                    projection.candidates_suppressed
                ),
                dispatch_success=projection.dispatch_success,
                dispatch_failure=projection.dispatch_failure,
                consecutive_suppression_streak=(
                    state.consecutive_suppression_streak
                ),
                dispatch_success_total_at_tick=(
                    state.dispatch_success_total
                ),
                duplicate_suppressed_soak_count_at_tick=(
                    state.duplicate_suppressed_soak_count
                ),
                elapsed_at_tick_seconds=pass_elapsed,
                utc_iso_timestamp=now_iso,
            )
            if write_artifacts:
                _safe_append_heartbeat(
                    output_dir=output_dir,
                    record=last_pass_record,
                )
                _safe_write_health_snapshot(
                    output_dir=output_dir,
                    record=last_pass_record,
                    bounds_within_recommended=(
                        bounds_within_recommended_ranges(
                            bounds
                        )
                    ),
                )
            break

        # Update streak max (covers SUPPRESSED_* branch above).
        if (
            state.consecutive_suppression_streak
            > state.consecutive_suppression_streak_max
        ):
            state.consecutive_suppression_streak_max = (
                state.consecutive_suppression_streak
            )

        # Emit heartbeat + health snapshot.
        state.last_dedupe_outcome = dedupe_outcome_for_pass
        state.last_stage29_3_outcome = outcome
        now_iso = resolved_clock.now_utc_iso()
        pass_elapsed = (
            resolved_clock.utc_now() - start_dt
        ).total_seconds()
        last_pass_record = build_pass_record(
            pass_index=pass_index,
            stage29_3_outcome=outcome,
            stage29_3_refusal_reason=(
                projection.tradeable_smoke_refusal_reason
            ),
            dedupe_outcome=dedupe_outcome_for_pass,
            events_seen=projection.events_seen,
            candidates_dispatched=(
                projection.candidates_dispatched
            ),
            candidates_suppressed=(
                projection.candidates_suppressed
            ),
            dispatch_success=projection.dispatch_success,
            dispatch_failure=projection.dispatch_failure,
            consecutive_suppression_streak=(
                state.consecutive_suppression_streak
            ),
            dispatch_success_total_at_tick=(
                state.dispatch_success_total
            ),
            duplicate_suppressed_soak_count_at_tick=(
                state.duplicate_suppressed_soak_count
            ),
            elapsed_at_tick_seconds=pass_elapsed,
            utc_iso_timestamp=now_iso,
        )
        if write_artifacts:
            _safe_append_heartbeat(
                output_dir=output_dir,
                record=last_pass_record,
            )
            _safe_write_health_snapshot(
                output_dir=output_dir,
                record=last_pass_record,
                bounds_within_recommended=(
                    bounds_within_recommended_ranges(bounds)
                ),
            )

        # Post-pass cap checks.
        if (
            state.dispatch_success_total
            >= bounds.max_dispatches
        ):
            soak_outcome = SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
            break
        if (
            state.consecutive_suppression_streak
            >= bounds.max_consecutive_suppressions
        ):
            soak_outcome = (
                SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT
            )
            break

        # Wall-clock post-pass check.
        now_dt = resolved_clock.utc_now()
        elapsed = (now_dt - start_dt).total_seconds()
        if elapsed >= float(bounds.wall_clock_seconds):
            soak_outcome = SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK
            break

    # Final outcome classification when the loop ran to completion
    # without an early break.
    if soak_outcome is None:
        if state.dispatch_success_total >= bounds.max_dispatches:
            soak_outcome = (
                SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
            )
        elif (
            state.events_seen_total == 0
            and state.dispatch_success_total == 0
        ):
            soak_outcome = SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS
        else:
            soak_outcome = SOAK_OUTCOME_COMPLETED_AT_PASS_CAP

    end_iso = resolved_clock.now_utc_iso()
    end_dt = resolved_clock.utc_now()
    elapsed_wall_clock = (end_dt - start_dt).total_seconds()

    summary = build_soak_summary(
        soak_outcome=soak_outcome,
        bounds=bounds,
        passes_attempted=state.passes_attempted,
        dispatch_success_total=state.dispatch_success_total,
        dispatch_failure_total=state.dispatch_failure_total,
        duplicate_suppressed_soak_count=(
            state.duplicate_suppressed_soak_count
        ),
        events_seen_total=state.events_seen_total,
        suppressed_unknown_pair_count=(
            state.suppressed_unknown_pair_count
        ),
        suppressed_disagree_pair_count=(
            state.suppressed_disagree_pair_count
        ),
        suppressed_usdc_observe_only_count=(
            state.suppressed_usdc_observe_only_count
        ),
        suppressed_missing_price_count=(
            state.suppressed_missing_price_count
        ),
        suppressed_stale_price_count=(
            state.suppressed_stale_price_count
        ),
        suppressed_malformed_count=(
            state.suppressed_malformed_count
        ),
        no_event_received_count=(
            state.no_event_received_count
        ),
        consecutive_suppression_streak_max=(
            state.consecutive_suppression_streak_max
        ),
        elapsed_wall_clock_seconds=elapsed_wall_clock,
        start_utc_iso=start_iso,
        end_utc_iso=end_iso,
        bounds_within_recommended_ranges=(
            bounds_within_recommended_ranges(bounds)
        ),
    )

    if write_artifacts and isinstance(output_dir, Path) and (
        output_dir.is_dir()
    ):
        try:
            write_soak_summary_bundle(
                output_dir=output_dir, summary=summary,
            )
        except Stage29_4SoakError:
            # Artifact write failure is a degraded outcome but
            # does not change the soak outcome; the operator can
            # re-run the ceremony.
            pass

    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_append_heartbeat(
    *,
    output_dir: Path,
    record,
) -> None:
    """Append a heartbeat record swallowing artifact-write
    failures. The orchestrator never raises out of the loop body.
    """
    try:
        append_heartbeat_artifact(
            output_dir=output_dir, record=record,
        )
    except Stage29_4SoakError:
        pass
    except OSError:
        pass


def _safe_write_health_snapshot(
    *,
    output_dir: Path,
    record,
    bounds_within_recommended: bool,
) -> None:
    """Write a health snapshot swallowing artifact-write failures.
    The orchestrator never raises out of the loop body.
    """
    try:
        write_health_snapshot_artifact(
            output_dir=output_dir,
            record=record,
            bounds_within_recommended_ranges=(
                bounds_within_recommended
            ),
        )
    except Stage29_4SoakError:
        pass
    except OSError:
        pass


def _build_invalid_bounds_summary(
    *,
    bounds: object,
    clock: Stage29_4Clock,
) -> Stage29_4SoakSummary:
    """Build the closed-set ``REFUSED_INVALID_BOUNDS`` soak summary
    used when the orchestrator refuses the call at the boundary.

    The bounds field on the summary is required to be a valid
    ``Stage29_4SoakBounds`` instance; when the caller-supplied
    bounds are themselves invalid, we substitute a locked
    safe-shape sentinel bounds record so the summary still meets
    the locked schema.
    """
    if isinstance(bounds, Stage29_4SoakBounds):
        echoed_bounds = bounds
    else:
        # Locked sentinel bounds for the REFUSED_INVALID_BOUNDS
        # path. Every axis is at the minimum positive value;
        # max_total_retries=0 per the Stage 29.4 invariant.
        echoed_bounds = Stage29_4SoakBounds(
            wall_clock_seconds=1,
            max_dispatches=1,
            max_passes=1,
            max_total_retries=0,
            max_consecutive_suppressions=1,
            heartbeat_cadence_seconds=1,
        )
    now_iso = clock.now_utc_iso()
    return build_soak_summary(
        soak_outcome=SOAK_OUTCOME_REFUSED_INVALID_BOUNDS,
        bounds=echoed_bounds,
        passes_attempted=0,
        dispatch_success_total=0,
        dispatch_failure_total=0,
        duplicate_suppressed_soak_count=0,
        events_seen_total=0,
        no_event_received_count=0,
        consecutive_suppression_streak_max=0,
        elapsed_wall_clock_seconds=0.0,
        start_utc_iso=now_iso,
        end_utc_iso=now_iso,
        bounds_within_recommended_ranges=(
            isinstance(bounds, Stage29_4SoakBounds)
            and bounds_within_recommended_ranges(bounds)
        ),
    )


__all__ = (
    "Stage29_4Clock",
    "Stage29_4UtcClock",
    "Stage29_4PassEntrypoint",
    "run_stage29_4_short_session_private_soak",
)
