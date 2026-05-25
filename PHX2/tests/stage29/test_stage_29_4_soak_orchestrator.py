"""Stage 29.4 soak orchestrator focused tests.

Covers each closed-set soak outcome via a fake Stage 29.3 pass
entrypoint and a deterministic fake clock:

  1. ``REFUSED_INVALID_BOUNDS`` -- invalid bounds rejected at the
     boundary.
  2. ``COMPLETED_AT_DISPATCH_CAP`` -- the soak stops once
     ``max_dispatches`` private dispatches succeed.
  3. ``COMPLETED_AT_WALL_CLOCK`` -- the soak stops at the
     wall-clock cap.
  4. ``COMPLETED_AT_PASS_CAP`` -- the soak runs to ``max_passes``
     without reaching the dispatch cap.
  5. ``BROKE_ON_SUPPRESSION_CIRCUIT`` -- consecutive
     ``SUPPRESSED_*`` outcomes trip the circuit breaker.
  6. ``BROKE_ON_FAILED_PASS`` -- the first ``FAILED`` outcome
     stops the soak.
  7. ``BROKE_ON_REFUSED_READINESS`` -- the soak's first pass
     returned ``REFUSED``.
  8. ``NO_DISPATCHES_NO_EVENTS`` -- every pass returned
     ``NO_EVENT_RECEIVED``.

Other behavior pins:

  * the cross-pass in-memory dedupe suppresses a duplicate event;
    the duplicate is counted in
    ``duplicate_suppressed_soak_count`` and does NOT increment
    ``dispatch_success_total``.
  * suppression streak counter resets on a dispatch.
  * artifact writes are deterministic and redaction-safe.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import pytest

from PHX2.stage29.stage29_4_dedupe_index import (
    build_dedupe_index,
)
from PHX2.stage29.stage29_4_soak_artifact_writer import (
    STAGE29_4_HEALTH_SNAPSHOT_BASENAME,
    STAGE29_4_HEARTBEAT_BASENAME,
    STAGE29_4_REDACTION_SCAN_BASENAME,
    STAGE29_4_SOAK_SUMMARY_BASENAME,
    read_heartbeat_artifact_lines,
)
from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    DEDUPE_OUTCOME_NEW,
    REDACTION_STATUS_SAFE,
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
    build_pass_result,
    build_soak_bounds,
    build_soak_dedupe_key,
)
from PHX2.stage29.stage29_4_soak_orchestrator import (
    Stage29_4UtcClock,
    run_stage29_4_short_session_private_soak,
)


# ---------------------------------------------------------------------------
# Fake clock + fake smoke result
# ---------------------------------------------------------------------------


class _FakeClock:
    """Deterministic clock returning a pre-configured sequence of
    UTC datetimes.

    The clock is stepped manually; ``utc_now()`` returns the next
    queued value (or the last value once the queue is exhausted).
    """

    def __init__(self, *, start: datetime, step_seconds: float = 1.0):
        self._values: List[datetime] = [start]
        self._step_seconds = step_seconds

    def push_step(self, seconds: float) -> None:
        last = self._values[-1]
        self._values.append(
            last + timedelta(seconds=seconds),
        )

    def utc_now(self) -> datetime:
        # Advance by ``_step_seconds`` on each call so the clock
        # always moves forward; the orchestrator calls ``utc_now``
        # multiple times per pass.
        last = self._values[-1]
        self._values.append(
            last + timedelta(seconds=self._step_seconds),
        )
        return last

    def now_utc_iso(self) -> str:
        return self.utc_now().isoformat()


class _FastClock:
    """Deterministic clock that returns a fixed time on every
    call. Wall-clock checks never fire when this clock is used.
    """

    def __init__(self, *, start: datetime):
        self._t = start

    def utc_now(self) -> datetime:
        return self._t

    def now_utc_iso(self) -> str:
        return self._t.isoformat()


class _BurnClock:
    """Deterministic clock that burns wall-clock seconds quickly
    once a configured pass count is reached.
    """

    def __init__(
        self, *, start: datetime, burn_after_calls: int,
        burn_seconds: float,
    ):
        self._start = start
        self._now = start
        self._calls = 0
        self._burn_after_calls = burn_after_calls
        self._burn_seconds = burn_seconds

    def utc_now(self) -> datetime:
        self._calls += 1
        if self._calls > self._burn_after_calls:
            # Add a big delta on the next call so the wall-clock
            # check triggers.
            self._now = self._now + timedelta(
                seconds=self._burn_seconds,
            )
            # Reset the trigger so subsequent calls don't keep
            # burning.
            self._burn_after_calls = 10_000
        return self._now

    def now_utc_iso(self) -> str:
        return self.utc_now().isoformat()


class _FakeSmokeResult:
    """Lightweight stand-in for a Stage 29.3 smoke result with
    only the fields the Stage 29.4 orchestrator reads.
    """

    def __init__(
        self,
        *,
        outcome: str,
        refusal_reason: str = "NONE",
        events_seen: int = 0,
        candidates_dispatched: int = 0,
        candidates_suppressed: int = 0,
        dispatch_success: int = 0,
        dispatch_failure: int = 0,
    ):
        self.tradeable_smoke_outcome = outcome
        self.tradeable_smoke_refusal_reason = refusal_reason
        self.events_seen = events_seen
        self.candidates_dispatched = candidates_dispatched
        self.candidates_suppressed = candidates_suppressed
        self.dispatch_success = dispatch_success
        self.dispatch_failure = dispatch_failure


# ---------------------------------------------------------------------------
# Fake pass entrypoint factories
# ---------------------------------------------------------------------------


def _make_dispatched_pass_result(
    *, mint_suffix: str,
) -> Stage29_4PassResult:
    return build_pass_result(
        smoke_result=_FakeSmokeResult(
            outcome="DISPATCHED",
            refusal_reason="NONE",
            events_seen=1,
            candidates_dispatched=1,
            dispatch_success=1,
        ),
        dedupe_key=build_soak_dedupe_key(
            token_mint=f"SoMint_{mint_suffix}",
            pair_quote_asset="SOL",
            event_kind="pumpswap_swap",
            ping_type="tradeable_private_ping",
            normalized_event_id=f"evt_{mint_suffix}",
        ),
    )


def _make_suppressed_pass_result(
    *, kind: str = "SUPPRESSED_UNKNOWN_PAIR",
) -> Stage29_4PassResult:
    return build_pass_result(
        smoke_result=_FakeSmokeResult(
            outcome=kind,
            refusal_reason="NONE",
            events_seen=1,
            candidates_suppressed=1,
        ),
    )


def _make_no_event_pass_result() -> Stage29_4PassResult:
    return build_pass_result(
        smoke_result=_FakeSmokeResult(
            outcome="NO_EVENT_RECEIVED",
            refusal_reason="NONE",
        ),
    )


def _make_failed_pass_result() -> Stage29_4PassResult:
    return build_pass_result(
        smoke_result=_FakeSmokeResult(
            outcome="FAILED",
            refusal_reason="SESSION_FAILED",
            dispatch_failure=1,
        ),
    )


def _make_refused_pass_result() -> Stage29_4PassResult:
    return build_pass_result(
        smoke_result=_FakeSmokeResult(
            outcome="REFUSED",
            refusal_reason="CHAINSTACK_READINESS_FAILED",
        ),
    )


def _make_pass_sequence_entrypoint(
    sequence: Sequence[Stage29_4PassResult],
) -> Callable:
    """Build a per-pass entrypoint that returns the supplied
    sequence in order. After the sequence is exhausted the
    entrypoint returns the last element repeatedly.
    """
    state = {"idx": 0}

    def _entry(
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ) -> Stage29_4PassResult:
        idx = state["idx"]
        if idx >= len(sequence):
            idx = len(sequence) - 1
        result = sequence[idx]
        state["idx"] = idx + 1
        return result

    return _entry


def _default_bounds(
    *,
    wall_clock_seconds: int = 900,
    max_dispatches: int = 3,
    max_passes: int = 10,
    max_consecutive_suppressions: int = 5,
    heartbeat_cadence_seconds: int = 30,
) -> Stage29_4SoakBounds:
    return build_soak_bounds(
        wall_clock_seconds=wall_clock_seconds,
        max_dispatches=max_dispatches,
        max_passes=max_passes,
        max_consecutive_suppressions=(
            max_consecutive_suppressions
        ),
        heartbeat_cadence_seconds=heartbeat_cadence_seconds,
    )


# ---------------------------------------------------------------------------
# 1. REFUSED_INVALID_BOUNDS
# ---------------------------------------------------------------------------


def test_invalid_bounds_object_returns_REFUSED_INVALID_BOUNDS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint(
        [_make_dispatched_pass_result(mint_suffix="a")],
    )
    summary = run_stage29_4_short_session_private_soak(
        bounds="not a bounds",  # type: ignore[arg-type]
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_REFUSED_INVALID_BOUNDS
    )
    assert summary.passes_attempted == 0


def test_invalid_output_dir_returns_REFUSED_INVALID_BOUNDS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint(
        [_make_dispatched_pass_result(mint_suffix="a")],
    )
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir="not a path",  # type: ignore[arg-type]
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_REFUSED_INVALID_BOUNDS
    )


def test_unknown_mode_returns_REFUSED_INVALID_BOUNDS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint(
        [_make_dispatched_pass_result(mint_suffix="a")],
    )
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        mode="UNKNOWN_MODE",
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_REFUSED_INVALID_BOUNDS
    )


def test_readiness_only_mode_alias_refused(tmp_path: Path):
    # READINESS_ONLY / CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY are
    # documented Stage 29.3 single-shot aliases; the Stage 29.4
    # orchestrator refuses them via REFUSED_INVALID_BOUNDS.
    entry = _make_pass_sequence_entrypoint(
        [_make_dispatched_pass_result(mint_suffix="a")],
    )
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        mode="READINESS_ONLY",
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_REFUSED_INVALID_BOUNDS
    )


# ---------------------------------------------------------------------------
# 2. COMPLETED_AT_DISPATCH_CAP
# ---------------------------------------------------------------------------


def test_dispatch_cap_returns_COMPLETED_AT_DISPATCH_CAP(
    tmp_path: Path,
):
    # max_dispatches=2; supply 3 distinct DISPATCHED passes. The
    # soak should stop after the second NEW dispatch.
    entry = _make_pass_sequence_entrypoint([
        _make_dispatched_pass_result(mint_suffix="a"),
        _make_dispatched_pass_result(mint_suffix="b"),
        _make_dispatched_pass_result(mint_suffix="c"),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=2, max_passes=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
    )
    assert summary.dispatch_success_total == 2
    assert summary.passes_attempted == 2


# ---------------------------------------------------------------------------
# 3. COMPLETED_AT_WALL_CLOCK
# ---------------------------------------------------------------------------


def test_wall_clock_cap_returns_COMPLETED_AT_WALL_CLOCK(
    tmp_path: Path,
):
    # wall_clock_seconds=10; the BurnClock burns 20 seconds after
    # the first pass so the wall-clock check fires before pass 2.
    entry = _make_pass_sequence_entrypoint([
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            wall_clock_seconds=10, max_dispatches=3,
            max_passes=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_BurnClock(
            start=datetime(
                2026, 5, 25, 17, 0, tzinfo=timezone.utc,
            ),
            burn_after_calls=5,
            burn_seconds=15.0,
        ),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK
    )


# ---------------------------------------------------------------------------
# 4. COMPLETED_AT_PASS_CAP
# ---------------------------------------------------------------------------


def test_pass_cap_returns_COMPLETED_AT_PASS_CAP(
    tmp_path: Path,
):
    # max_passes=3, max_dispatches=10 (never reached);
    # SUPPRESSED outcomes that don't trip the circuit breaker.
    entry = _make_pass_sequence_entrypoint([
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_passes=3,
            max_dispatches=10,
            max_consecutive_suppressions=100,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_COMPLETED_AT_PASS_CAP
    )
    assert summary.passes_attempted == 3


# ---------------------------------------------------------------------------
# 5. BROKE_ON_SUPPRESSION_CIRCUIT
# ---------------------------------------------------------------------------


def test_suppression_circuit_returns_BROKE_ON_SUPPRESSION_CIRCUIT(
    tmp_path: Path,
):
    # max_consecutive_suppressions=3; supply 5 SUPPRESSED passes.
    entry = _make_pass_sequence_entrypoint([
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_consecutive_suppressions=3,
            max_passes=10,
            max_dispatches=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT
    )
    assert summary.consecutive_suppression_streak_max == 3


# ---------------------------------------------------------------------------
# 6. BROKE_ON_FAILED_PASS
# ---------------------------------------------------------------------------


def test_failed_pass_returns_BROKE_ON_FAILED_PASS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_no_event_pass_result(),
        _make_failed_pass_result(),
        _make_no_event_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
    )
    assert summary.passes_attempted == 2
    assert summary.dispatch_failure_total == 1


def test_failed_first_pass_returns_BROKE_ON_FAILED_PASS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_failed_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
    )


# ---------------------------------------------------------------------------
# 7. BROKE_ON_REFUSED_READINESS
# ---------------------------------------------------------------------------


def test_refused_first_pass_returns_BROKE_ON_REFUSED_READINESS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_refused_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS
    )


def test_refused_subsequent_pass_returns_BROKE_ON_FAILED_PASS(
    tmp_path: Path,
):
    # REFUSED on pass 2+ is unusual; the orchestrator routes it
    # to BROKE_ON_FAILED_PASS rather than to refused-readiness.
    entry = _make_pass_sequence_entrypoint([
        _make_no_event_pass_result(),
        _make_refused_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
    )


# ---------------------------------------------------------------------------
# 8. NO_DISPATCHES_NO_EVENTS
# ---------------------------------------------------------------------------


def test_no_events_returns_NO_DISPATCHES_NO_EVENTS(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_passes=3,
            max_dispatches=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS
    )
    assert summary.events_seen_total == 0
    assert summary.no_event_received_count == 3


def test_no_event_periods_do_not_crash(tmp_path: Path):
    entry = _make_pass_sequence_entrypoint([
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_passes=5, max_dispatches=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    # Should complete cleanly with NO_DISPATCHES_NO_EVENTS.
    assert summary.soak_outcome == (
        SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS
    )


def test_suppressions_do_not_crash(tmp_path: Path):
    # All Stage 29.3 SUPPRESSED_* variants must be aggregated
    # cleanly without crashing.
    entry = _make_pass_sequence_entrypoint([
        _make_suppressed_pass_result(
            kind="SUPPRESSED_UNKNOWN_PAIR",
        ),
        _make_suppressed_pass_result(
            kind="SUPPRESSED_DISAGREE_PAIR",
        ),
        _make_suppressed_pass_result(
            kind="SUPPRESSED_USDC_OBSERVE_ONLY",
        ),
        _make_suppressed_pass_result(
            kind="SUPPRESSED_MISSING_PRICE",
        ),
        _make_suppressed_pass_result(
            kind="SUPPRESSED_STALE_PRICE",
        ),
        _make_suppressed_pass_result(
            kind="SUPPRESSED_MALFORMED",
        ),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_passes=6, max_dispatches=10,
            max_consecutive_suppressions=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.suppressed_unknown_pair_count == 1
    assert summary.suppressed_disagree_pair_count == 1
    assert summary.suppressed_usdc_observe_only_count == 1
    assert summary.suppressed_missing_price_count == 1
    assert summary.suppressed_stale_price_count == 1
    assert summary.suppressed_malformed_count == 1


# ---------------------------------------------------------------------------
# Cross-pass dedupe: duplicate suppressed
# ---------------------------------------------------------------------------


def test_duplicate_dispatch_suppressed_by_dedupe_index(
    tmp_path: Path,
):
    # Pass 1 + Pass 2 both yield DISPATCHED with the SAME dedupe
    # key. The dedupe index records pass 1 as NEW and pass 2 as
    # DUPLICATE_SUPPRESSED_SOAK. The dispatch_success_total
    # remains 1; duplicate_suppressed_soak_count = 1.
    dispatched = _make_dispatched_pass_result(
        mint_suffix="same",
    )
    duplicate = _make_dispatched_pass_result(
        mint_suffix="same",
    )
    entry = _make_pass_sequence_entrypoint([
        dispatched, duplicate,
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=5,
            max_passes=2,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    # max_passes=2 and we ran both; dispatch cap not reached;
    # COMPLETED_AT_PASS_CAP since events were seen.
    assert summary.soak_outcome == (
        SOAK_OUTCOME_COMPLETED_AT_PASS_CAP
    )
    assert summary.dispatch_success_total == 1
    assert summary.duplicate_suppressed_soak_count == 1
    assert summary.passes_attempted == 2


def test_two_distinct_dispatches_both_count_as_NEW(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_dispatched_pass_result(mint_suffix="a"),
        _make_dispatched_pass_result(mint_suffix="b"),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=5, max_passes=2,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.dispatch_success_total == 2
    assert summary.duplicate_suppressed_soak_count == 0


def test_duplicate_dispatch_does_not_trigger_dispatch_cap(
    tmp_path: Path,
):
    # max_dispatches=1; first pass dispatches NEW (cap should
    # fire); but let's verify duplicate doesn't double-count.
    # Use max_dispatches=2 + sequence: NEW, DUPLICATE, NEW. The
    # NEW twice should reach the cap; duplicate shouldn't count.
    entry = _make_pass_sequence_entrypoint([
        _make_dispatched_pass_result(mint_suffix="a"),
        _make_dispatched_pass_result(mint_suffix="a"),
        _make_dispatched_pass_result(mint_suffix="b"),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=2, max_passes=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
    )
    assert summary.dispatch_success_total == 2
    assert summary.duplicate_suppressed_soak_count == 1
    assert summary.passes_attempted == 3


# ---------------------------------------------------------------------------
# Streak reset on DISPATCHED
# ---------------------------------------------------------------------------


def test_streak_resets_on_dispatched_pass(tmp_path: Path):
    # 2 SUPPRESSED, then 1 DISPATCHED (streak resets), then 2
    # SUPPRESSED. max_consecutive_suppressions=3; the streak
    # never reaches 3 because the DISPATCHED in the middle
    # resets the counter. So no circuit breaker.
    entry = _make_pass_sequence_entrypoint([
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
        _make_dispatched_pass_result(mint_suffix="reset"),
        _make_suppressed_pass_result(),
        _make_suppressed_pass_result(),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_passes=5,
            max_dispatches=10,
            max_consecutive_suppressions=3,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    # No circuit-breaker firing; the streak max was 2.
    assert summary.soak_outcome != (
        SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT
    )
    assert summary.consecutive_suppression_streak_max == 2


# ---------------------------------------------------------------------------
# Artifact writes: deterministic + redaction-safe
# ---------------------------------------------------------------------------


def test_artifacts_are_written_when_write_artifacts_is_true(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_dispatched_pass_result(mint_suffix="a"),
        _make_no_event_pass_result(),
        _make_dispatched_pass_result(mint_suffix="b"),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=10, max_passes=3,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=True,
    )
    assert (
        tmp_path / STAGE29_4_SOAK_SUMMARY_BASENAME
    ).is_file()
    assert (tmp_path / STAGE29_4_HEARTBEAT_BASENAME).is_file()
    assert (
        tmp_path / STAGE29_4_HEALTH_SNAPSHOT_BASENAME
    ).is_file()
    assert (
        tmp_path / STAGE29_4_REDACTION_SCAN_BASENAME
    ).is_file()


def test_heartbeat_artifact_has_one_record_per_pass(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
        _make_no_event_pass_result(),
    ])
    run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_passes=3, max_dispatches=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=True,
    )
    lines = read_heartbeat_artifact_lines(
        output_dir=tmp_path,
    )
    assert len(lines) == 3
    assert [line["pass_index"] for line in lines] == [1, 2, 3]


def test_soak_summary_artifact_carries_locked_axes(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_dispatched_pass_result(mint_suffix="a"),
    ])
    run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=1, max_passes=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=True,
    )
    payload = json.loads(
        (
            tmp_path / STAGE29_4_SOAK_SUMMARY_BASENAME
        ).read_text(encoding="utf-8")
    )
    assert payload["filter_enforcement_status"] == (
        "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert payload["redaction_status"] == REDACTION_STATUS_SAFE


def test_redaction_scan_returns_SAFE_after_clean_soak(
    tmp_path: Path,
):
    entry = _make_pass_sequence_entrypoint([
        _make_dispatched_pass_result(mint_suffix="a"),
        _make_dispatched_pass_result(mint_suffix="b"),
    ])
    run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=2, max_passes=10,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=True,
    )
    payload = json.loads(
        (
            tmp_path / STAGE29_4_REDACTION_SCAN_BASENAME
        ).read_text(encoding="utf-8")
    )
    assert payload["redaction_status"] == REDACTION_STATUS_SAFE


def test_artifacts_are_deterministic_across_two_runs(
    tmp_path: Path,
):
    # Two runs with identical clocks + entrypoints must produce
    # byte-identical soak-summary artifact bodies.
    def _run(dir_: Path) -> bytes:
        entry = _make_pass_sequence_entrypoint([
            _make_dispatched_pass_result(mint_suffix="a"),
        ])
        run_stage29_4_short_session_private_soak(
            bounds=_default_bounds(
                max_dispatches=1, max_passes=10,
            ),
            output_dir=dir_,
            pass_entrypoint=entry,
            clock=_FastClock(start=datetime(
                2026, 5, 25, 17, 0, tzinfo=timezone.utc,
            )),
            write_artifacts=True,
        )
        return (
            dir_ / STAGE29_4_SOAK_SUMMARY_BASENAME
        ).read_bytes()

    dir_a = tmp_path / "run_a"
    dir_a.mkdir()
    dir_b = tmp_path / "run_b"
    dir_b.mkdir()
    assert _run(dir_a) == _run(dir_b)


# ---------------------------------------------------------------------------
# Entrypoint defensive paths
# ---------------------------------------------------------------------------


def test_pass_entrypoint_returning_non_envelope_is_treated_as_failed(
    tmp_path: Path,
):
    def _bad_entry(
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ):
        return "not a pass result"

    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=_bad_entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
    )


def test_pass_entrypoint_raising_returns_BROKE_ON_FAILED_PASS(
    tmp_path: Path,
):
    # The Stage 29.4 orchestrator never propagates a per-pass
    # Stage29_4SoakError; it converts to BROKE_ON_FAILED_PASS.
    from PHX2.stage29.stage29_4_soak_models import (
        Stage29_4SoakError,
    )

    def _raising(
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ):
        raise Stage29_4SoakError("FAKE_FAIL")

    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(),
        output_dir=tmp_path,
        pass_entrypoint=_raising,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.soak_outcome == (
        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
    )


def test_dispatched_outcome_without_dedupe_key_is_suppressed(
    tmp_path: Path,
):
    # Defensive: DISPATCHED outcome with a missing dedupe_key
    # candidate is treated as DUPLICATE_SUPPRESSED so the soak
    # does not double-count an undeduplicated dispatch toward
    # the dispatch cap.
    entry = _make_pass_sequence_entrypoint([
        build_pass_result(
            smoke_result=_FakeSmokeResult(
                outcome="DISPATCHED",
                refusal_reason="NONE",
                events_seen=1,
                dispatch_success=1,
            ),
            dedupe_key=None,
        ),
    ])
    summary = run_stage29_4_short_session_private_soak(
        bounds=_default_bounds(
            max_dispatches=2, max_passes=1,
        ),
        output_dir=tmp_path,
        pass_entrypoint=entry,
        clock=_FastClock(start=datetime(
            2026, 5, 25, 17, 0, tzinfo=timezone.utc,
        )),
        write_artifacts=False,
    )
    assert summary.dispatch_success_total == 0
    assert summary.duplicate_suppressed_soak_count == 1


# ---------------------------------------------------------------------------
# Stage29_4UtcClock reference clock
# ---------------------------------------------------------------------------


def test_stage29_4_utc_clock_is_tz_aware():
    clk = Stage29_4UtcClock()
    now = clk.utc_now()
    assert now.tzinfo is not None
    iso = clk.now_utc_iso()
    assert isinstance(iso, str)
    assert "+00:00" in iso or iso.endswith("Z")
