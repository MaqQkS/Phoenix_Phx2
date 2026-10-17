"""Daemon-level proofs for the remaining required offline fault-injection cases.

These complete required tests 7, 11, 12, 15, 19 and 20 at the DAEMON level (the
pure-function halves live in ``test_watchdog_health.py``): the question here is
not "is the classification right?" but "does the running watchdog actually
refuse to restart, and open the circuit exactly once?".

The active recovery episode is built with the producer's OWN
``RpcGapRecoveryStore``, so the on-disk document the watchdog reads is a genuine
authenticated envelope rather than a hand-written imitation.  The store is used
offline against a temporary state directory: no RPC, no provider, no network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from PHX2.tests.watchdog._harness import FakeWorld, make_config, make_watchdog
from PHX2.watchdog.state import load_circuit_state


def _open_active_recovery_episode(state_dir: str, *, completed: int,
                                  total: int) -> None:
    """Persist a genuine RPC_BACKFILL_RUNNING episode with the real store."""

    from PHX2.free_tier_producer.rpc_gap_recovery import (
        RECOVERY_STATE_RPC_BACKFILL_RUNNING,
        RpcGapRecoveryStore,
    )

    store = RpcGapRecoveryStore(state_dir=state_dir)
    store.load()
    state = store.state.clone()
    state.recovery_state = RECOVERY_STATE_RPC_BACKFILL_RUNNING
    state.entry_classification = "REPLAY_REFUSED_OUT_OF_RANGE"
    state.recovery_mode = "rpc_backfill"
    state.authoritative_commitment = "confirmed"
    state.safe_from_slot = 435_085_972
    state.recovery_target_slot = 435_231_678
    state.produced_blocks_total = int(total)
    state.produced_blocks_completed = int(completed)
    state.last_completed_slot = 435_085_972 + int(completed)
    state.episode_generation = 1
    state.subscription_identity_digest = "d" * 64
    store._persist_state_locked(state)          # noqa: SLF001


def _episode_progress(state_dir: str) -> int:
    from PHX2.free_tier_producer.rpc_gap_recovery import RpcGapRecoveryStore
    store = RpcGapRecoveryStore(state_dir=state_dir)
    store.load()
    return int(store.state.produced_blocks_completed)


def test_real_recovery_store_round_trips_for_the_watchdog(tmp_path):
    """Guard the harness itself: the document must read back as VALID_CURRENT."""

    config = make_config(tmp_path)
    _open_active_recovery_episode(config.cursor_state_dir, completed=10,
                                  total=1000)

    from PHX2.free_tier_producer.rpc_gap_recovery import (
        classify_recovery_checkpoint_file,
    )
    classification = classify_recovery_checkpoint_file(
        config.recovery_primary_path)
    assert classification.state == "VALID_CURRENT"
    record = classification.records[0]
    assert record["recovery_state"] == "RPC_BACKFILL_RUNNING"
    assert record["produced_blocks_completed"] == 10


# --- 15. recovery with progress does not restart ------------------------- #

def test_active_recovery_with_progress_is_supervised_not_restarted(tmp_path):
    config = make_config(tmp_path)
    _open_active_recovery_episode(config.cursor_state_dir, completed=100,
                                  total=145_664)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    original_sleep = watchdog._sleep                       # noqa: SLF001
    progress = {"n": 100}

    def advance_recovery(seconds: float) -> None:
        original_sleep(seconds)
        progress["n"] += 25
        _open_active_recovery_episode(config.cursor_state_dir,
                                      completed=progress["n"], total=145_664)
        if world.spawns:
            world.write_heartbeat(world.spawns[0].run_dir)

    watchdog._sleep = advance_recovery                     # noqa: SLF001

    result = watchdog.run(max_cycles=5)

    assert len(world.spawns) == 1, "a progressing recovery was restarted"
    assert result.final_health == "RECOVERING_WITH_PROGRESS"
    assert not load_circuit_state(config.circuit_state_path).is_open
    assert _episode_progress(config.cursor_state_dir) > 100


def test_recovery_stalled_beyond_threshold_opens_circuit_once(tmp_path):
    """No progress for longer than the window: refuse, do not loop."""

    config = make_config(tmp_path, recovery_stall_seconds=300.0,
                         poll_interval_seconds=120.0)
    _open_active_recovery_episode(config.cursor_state_dir, completed=100,
                                  total=145_664)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    original_sleep = watchdog._sleep                       # noqa: SLF001

    def stalled(seconds: float) -> None:
        original_sleep(seconds)
        if world.spawns:
            world.write_heartbeat(world.spawns[0].run_dir)

    watchdog._sleep = stalled                              # noqa: SLF001

    result = watchdog.run(max_cycles=8)

    assert len(world.spawns) == 1, "a stalled recovery was restarted"
    assert result.outcome == "CIRCUIT_OPEN"
    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.open_reason == "RECOVERY_STALLED_NO_PROGRESS"
    assert circuit.integrity_locked is True
    opened = [line for line in
              config.events_path.read_text(encoding="utf-8").splitlines()
              if "CIRCUIT_OPENED" in line]
    assert len(opened) == 1, f"circuit opened {len(opened)} times"
    assert _episode_progress(config.cursor_state_dir) == 100, (
        "the watchdog mutated the recovery episode")


# --- 7. duplicate producer opens the circuit ---------------------------- #

def test_duplicate_logical_producer_opens_circuit_without_launching(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    assert len(world.spawns) == 1

    # A second, independent logical producer appears beside the supervised one.
    world.add_wrapper(pid=61000)
    world.add_reexec_shim_pair(
        shim_pid=61001, real_pid=61002, wrapper_pid=61000,
        run_dir=str(tmp_path / "rogue"), stop_file=str(tmp_path / "rogue_stop"))

    result = watchdog.run(max_cycles=3)

    assert len(world.spawns) == 1, "a duplicate condition triggered a launch"
    assert result.outcome == "CIRCUIT_OPEN"
    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.open_reason == "DUPLICATE_PRODUCER"
    assert circuit.integrity_locked is True


def test_watchdog_does_not_kill_the_rogue_or_the_supervised_producer(tmp_path):
    """Phase 4: never kill an unknown process merely for matching PHX2."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    world.add_wrapper(pid=61000)
    world.add_reexec_shim_pair(
        shim_pid=61001, real_pid=61002, wrapper_pid=61000,
        run_dir=str(tmp_path / "rogue"), stop_file=str(tmp_path / "rogue_stop"))

    watchdog.run(max_cycles=3)

    assert world.terminated == [], (
        "the watchdog force-terminated a process on a duplicate verdict")


# --- 11. a stale heartbeat causes EXACTLY one restart ------------------- #

def test_stale_heartbeat_causes_exactly_one_restart(tmp_path):
    config = make_config(tmp_path, heartbeat_max_age_seconds=90.0,
                         poll_interval_seconds=60.0,
                         startup_grace_seconds=30.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    # The producer starts, then stops writing heartbeats entirely; the fake
    # clock advances past the stale threshold while the process stays alive.
    original_sleep = watchdog._sleep                       # noqa: SLF001
    child_stop = {"path": None}

    def freeze_heartbeat(seconds: float) -> None:
        original_sleep(seconds)
        if world.spawns and child_stop["path"] is None:
            child_stop["path"] = world.spawns[0].stop_file

    watchdog._sleep = freeze_heartbeat                     # noqa: SLF001

    watchdog.run(max_cycles=4)

    assert len(world.spawns) == 2, (
        f"expected exactly one restart, got {len(world.spawns) - 1}")
    history = [line for line in
               config.restart_history_path.read_text(
                   encoding="utf-8").splitlines() if line.strip()]
    assert len(history) == 1, history
    assert "HEARTBEAT_STALE" in history[0]


# --- 12. a clean exit under operator stop does not restart -------------- #

def test_clean_exit_under_operator_stop_never_restarts(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    child = world.spawns[0]

    original_sleep = watchdog._sleep                       # noqa: SLF001

    def honour_stop(seconds: float) -> None:
        original_sleep(seconds)
        if os.path.exists(child.stop_file):
            world.stop_file_honoured()

    watchdog._sleep = honour_stop                          # noqa: SLF001
    watchdog.request_operator_stop()

    result = watchdog.run(max_cycles=4)

    assert len(world.spawns) == 1, "a restart happened under an operator stop"
    assert result.outcome == "OPERATOR_STOP"
    assert result.exit_code == 0
    assert not config.restart_history_path.exists(), (
        "an operator stop was recorded as a restart")
    assert not load_circuit_state(config.circuit_state_path).is_open


# --- 19. ledger ambiguity never auto-restarts -------------------------- #

def test_malformed_canonical_ledger_opens_circuit_without_restarting(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    assert len(world.spawns) == 1

    Path(config.ledger_path).write_text('{"a":1}\nnot-json\n',
                                        encoding="utf-8")

    result = watchdog.run(max_cycles=3)

    assert len(world.spawns) == 1, "a ledger failure triggered a restart"
    assert result.outcome == "CIRCUIT_OPEN"
    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.open_reason == "LEDGER_UNPARSEABLE"
    assert circuit.integrity_locked is True


def test_truncated_final_ledger_line_opens_circuit(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    # Every line parses; only the trailing newline is missing, which is exactly
    # the "a write was interrupted mid-append" signature.
    Path(config.ledger_path).write_text('{"a":1}\n{"b":2}', encoding="utf-8")

    result = watchdog.run(max_cycles=2)

    assert len(world.spawns) == 1
    assert result.outcome == "CIRCUIT_OPEN"
    assert load_circuit_state(
        config.circuit_state_path).open_reason == "LEDGER_TRUNCATED_LINE"


def test_delivery_unknown_opens_circuit_without_restarting(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    world.write_heartbeat(world.spawns[0].run_dir, delivery_unknown_total=1)

    result = watchdog.run(max_cycles=3)

    assert len(world.spawns) == 1
    assert result.outcome == "CIRCUIT_OPEN"
    assert load_circuit_state(
        config.circuit_state_path).open_reason == "DELIVERY_STATE_AMBIGUITY"


# --- 20. an integrity failure leaves an incident artifact -------------- #

def test_every_integrity_verdict_writes_an_incident_artifact(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    world.write_heartbeat(world.spawns[0].run_dir, cursor_identity_match=False)

    watchdog.run(max_cycles=2)

    import json
    incident = json.loads(
        config.last_incident_path.read_text(encoding="utf-8"))
    assert incident["kind"] == "PHX2_WATCHDOG_INCIDENT"
    assert incident["reason"] == "CURSOR_SUBSCRIPTION_IDENTITY_MISMATCH"
    assert incident["health_class"] == "NONRESTARTABLE_INTEGRITY_FAILURE"
    assert incident["operator_action_required"] is True
    assert "detail" in incident
