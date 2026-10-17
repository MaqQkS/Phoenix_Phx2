"""The inherited rpc_backfill episode must be SUPERVISED, not refused.

Regression for two false positives that made the watchdog refuse to run the
accepted producer at all.  Both were observed against the real durable state at
``C:\\Users\\BalaC\\phx2_paid_primary_runtime\\state`` on 2026-07-26, and the
literal values from that state are used here as the fixture.

1. ``cursor.recovery_terminal = True`` was read as a terminal recovery.  It is
   not: it records that the provider terminally refused *gRPC replay*
   (``GRPC_REPLAY_POSITION_TOO_OLD``), which is precisely the condition the
   bounded ``rpc_backfill`` mode exists to work around.  With a resumable episode
   open (``RPC_BACKFILL_RUNNING`` is in ``RESUMABLE_RECOVERY_STATES``) this is the
   NORMAL inherited state of this deployment.

2. ``unresolved_work_crossed`` compared ``last_durable_slot`` against the episode
   target.  While a gap is backfilled the live stream keeps running and its
   events are quarantined, so the processed high-water mark legitimately sits
   ahead of the target.  The invariant is about the PROVEN REPLAY BOUNDARY.
"""

from __future__ import annotations

import os

import pytest

from PHX2.tests.watchdog._harness import FakeWorld, make_config, make_watchdog
from PHX2.watchdog.health import (
    NONRESTARTABLE_INTEGRITY_FAILURE,
    RECOVERING_WITH_PROGRESS,
    REASON_RECOVERY_TERMINAL,
    REASON_UNRESOLVED_WORK_CROSSED,
    HealthInputs,
    evaluate_health,
)

# --- the exact live values the watchdog first refused on ------------------- #
LIVE_SAFE_FROM_SLOT = 435_085_972
LIVE_TARGET_SLOT = 435_231_678
LIVE_LAST_DURABLE_SLOT = 435_233_755          # ahead of target: quarantined live
LIVE_BLOCKS_COMPLETED = 2_310
LIVE_BLOCKS_TOTAL = 145_664
LIVE_PRIOR_TERMINAL_REASON = "RPC_BACKFILL_TIMEOUT"


def test_rpc_backfill_running_is_a_resumable_state():
    from PHX2.free_tier_producer.rpc_gap_recovery import (
        RECOVERY_STATE_RPC_BACKFILL_RUNNING,
        RESUMABLE_RECOVERY_STATES,
    )
    assert RECOVERY_STATE_RPC_BACKFILL_RUNNING in RESUMABLE_RECOVERY_STATES


def test_inherited_episode_is_recovering_not_an_integrity_failure():
    """The health model must classify the real inherited state as work."""

    verdict = evaluate_health(HealthInputs(
        producer_alive=True, producer_pid=1234, logical_producer_count=1,
        producer_uptime_seconds=600.0,
        heartbeat_present=True, heartbeat_age_seconds=20.0,
        yellowstone_owner_count=1, max_active_streams_observed=1,
        recovery_state="RPC_BACKFILL_RUNNING",
        recovery_terminal=False,                 # derived from the RECOVERY doc
        recovery_progress_units=LIVE_BLOCKS_COMPLETED,
        recovery_progress_advanced=True,
        recovery_no_progress_seconds=30.0,
        unresolved_work_crossed=False,           # safe boundary, not durable slot
    ))
    assert verdict.health_class == RECOVERING_WITH_PROGRESS
    assert not verdict.integrity_failure


def test_recovery_document_terminal_state_is_still_an_integrity_failure():
    """The genuine terminal case must NOT have been weakened."""

    verdict = evaluate_health(HealthInputs(
        producer_alive=True, producer_pid=1, logical_producer_count=1,
        producer_uptime_seconds=600.0, heartbeat_present=True,
        heartbeat_age_seconds=10.0, yellowstone_owner_count=1,
        recovery_state="RECOVERY_TERMINAL", recovery_terminal=True))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_RECOVERY_TERMINAL in verdict.reasons


def test_safe_boundary_past_the_target_is_still_unresolved_work_crossed():
    verdict = evaluate_health(HealthInputs(
        producer_alive=True, producer_pid=1, logical_producer_count=1,
        producer_uptime_seconds=600.0, heartbeat_present=True,
        heartbeat_age_seconds=10.0, yellowstone_owner_count=1,
        recovery_state="RPC_BACKFILL_RUNNING", unresolved_work_crossed=True))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_UNRESOLVED_WORK_CROSSED in verdict.reasons


# --- the observation layer, against real authenticated documents ---------- #

def _write_inherited_state(config, monkeypatch, *,
                           blocks_completed=LIVE_BLOCKS_COMPLETED,
                           recovery_state="RPC_BACKFILL_RUNNING",
                           terminal_reason=None,
                           cursor_replay_terminal=True,
                           safe_boundary=None):
    """Set up the inherited episode as the watchdog actually sees it.

    The RECOVERY half is persisted with the producer's OWN authenticated store,
    so the document the watchdog classifies is genuine.

    The CURSOR half is injected through ``observe._cursor_record`` rather than
    written: the cursor store applies cross-field validation and correctly
    REFUSES a hand-assembled record (``CURSOR_READBACK_FAILED``), and forging a
    valid one would mean driving the whole disconnect/gap/recovery state machine.
    The values below are the literal ones read from the live state dir, so this
    still pins the exact condition the watchdog first refused on.
    """

    from PHX2.free_tier_producer.rpc_gap_recovery import RpcGapRecoveryStore
    from PHX2.watchdog import observe as observe_module

    recovery = RpcGapRecoveryStore(state_dir=config.cursor_state_dir)
    recovery.load()
    state = recovery.state.clone()
    state.recovery_state = recovery_state
    state.entry_classification = "REPLAY_REFUSED_OUT_OF_RANGE"
    state.recovery_mode = "rpc_backfill"
    state.authoritative_commitment = "confirmed"
    state.safe_from_slot = LIVE_SAFE_FROM_SLOT
    state.recovery_target_slot = LIVE_TARGET_SLOT
    state.produced_blocks_total = LIVE_BLOCKS_TOTAL
    state.produced_blocks_completed = int(blocks_completed)
    state.last_completed_slot = LIVE_SAFE_FROM_SLOT + int(blocks_completed)
    state.episode_generation = 1
    state.prior_terminal_reason = LIVE_PRIOR_TERMINAL_REASON
    state.terminal_upgrade_count = 1
    state.terminal_reason = terminal_reason
    state.subscription_identity_digest = "d" * 64
    recovery._persist_state_locked(state)          # noqa: SLF001

    live_cursor_record = {
        "record_kind": "PHX2_GRPC_STREAM_CURSOR",
        "last_durable_slot": LIVE_LAST_DURABLE_SLOT,
        "last_proven_replay_boundary_slot": safe_boundary,
        "recovery_terminal": bool(cursor_replay_terminal),
        "recovery_required": True,
        "recovery_status": "RECOVERY_FAILED",
        "recovery_reason": "GRPC_REPLAY_POSITION_TOO_OLD",
        "recovery_from_slot": None,
        "recovery_target_slot": None,
        "recovery_generation": 0,
        "attempt_generation": 2,
        "attempt_open": True,
    }
    monkeypatch.setattr(
        observe_module, "_cursor_record",
        lambda cfg: ("VALID_CURRENT", dict(live_cursor_record)))


def _observe(config, world, run_dir, previous=None):
    from PHX2.watchdog.observe import PreviousObservation, build_observation
    from PHX2.watchdog.process import read_producer_lock
    return build_observation(
        config=config, table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        adoption=None, run_dir=run_dir, producer_pid=os.getpid(),
        producer_alive=True, producer_start_utc=world.now(),
        operator_stop_requested=False, circuit_open=False,
        producer_expected=True, repo_head_matches=True,
        launcher_identity_matches=True, redaction_exposure=False,
        previous=previous or PreviousObservation(), now_utc=world.now())


def test_observation_of_the_real_inherited_state_is_not_terminal(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    _write_inherited_state(config, monkeypatch)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir))

    observation = _observe(config, world, str(run_dir))

    assert observation.inputs.recovery_state == "RPC_BACKFILL_RUNNING"
    assert observation.inputs.recovery_terminal is False, (
        "a resumable rpc_backfill episode was read as terminal")
    assert observation.inputs.unresolved_work_crossed is False, (
        "quarantined live progress ahead of the target was read as a crossing")
    assert observation.facts["cursor_replay_terminal"] is True
    assert observation.facts["recovery_resumable_episode_open"] is True

    verdict = evaluate_health(observation.inputs)
    assert verdict.health_class == RECOVERING_WITH_PROGRESS


def test_replay_terminal_with_no_open_episode_is_still_terminal(tmp_path, monkeypatch):
    """Nothing would ever close the gap: that IS a stuck state."""

    config = make_config(tmp_path)
    _write_inherited_state(config, monkeypatch, recovery_state="IDLE")
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir))

    observation = _observe(config, world, str(run_dir))

    assert observation.inputs.recovery_terminal is True
    assert evaluate_health(observation.inputs).health_class == (
        NONRESTARTABLE_INTEGRITY_FAILURE)


def test_recovery_document_terminal_reason_is_read_as_terminal(tmp_path, monkeypatch):
    """A terminal reason only ever appears WITH a terminal state.

    The recovery store's cross-field validation refuses a ``terminal_reason`` set
    on a running episode, so this asserts the reachable shape. The extra
    ``terminal_reason is not None`` clause in the watchdog is a belt-and-braces
    guard rather than the primary path.
    """

    config = make_config(tmp_path)
    _write_inherited_state(config, monkeypatch,
                           recovery_state="RECOVERY_TERMINAL",
                           terminal_reason="RPC_BACKFILL_TIMEOUT")
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir))

    observation = _observe(config, world, str(run_dir))
    assert observation.inputs.recovery_terminal is True


def test_safe_boundary_beyond_the_target_is_detected(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    _write_inherited_state(config, monkeypatch, safe_boundary=LIVE_TARGET_SLOT + 1)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir))

    observation = _observe(config, world, str(run_dir))
    assert observation.inputs.unresolved_work_crossed is True


def test_watchdog_supervises_the_inherited_episode_end_to_end(tmp_path, monkeypatch):
    """The daemon-level proof: it LAUNCHES and keeps supervising."""

    config = make_config(tmp_path)
    _write_inherited_state(config, monkeypatch)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    original_sleep = watchdog._sleep                       # noqa: SLF001
    progress = {"n": LIVE_BLOCKS_COMPLETED}

    def advance(seconds: float) -> None:
        original_sleep(seconds)
        progress["n"] += 30
        _write_inherited_state(config, monkeypatch, blocks_completed=progress["n"])
        if world.spawns:
            world.write_heartbeat(world.spawns[0].run_dir)

    watchdog._sleep = advance                              # noqa: SLF001

    result = watchdog.run(max_cycles=4)

    assert len(world.spawns) == 1, "the inherited episode blocked the launch"
    assert result.final_health == RECOVERING_WITH_PROGRESS
    from PHX2.watchdog.state import load_circuit_state
    assert not load_circuit_state(config.circuit_state_path).is_open
