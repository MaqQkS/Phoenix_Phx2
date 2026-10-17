"""Restart sequencing, deterministic backoff, and the circuit breaker.

Covers required offline tests 13, 21-25 and the ordering guarantee from 14.

The clock, the sleep, the spawn and the terminate call are fakes, so backoff is
asserted on the exact sequence of sleep durations rather than on wall time.
"""

from __future__ import annotations

import os

from PHX2.tests.watchdog._harness import (
    FakeWorld,
    make_config,
    make_watchdog,
)
from PHX2.watchdog.daemon import (
    EXIT_NONRESTARTABLE,
    EXIT_OPERATOR_CLEAN,
    EXIT_RESTARTABLE,
    classify_producer_exit,
)
from PHX2.watchdog.health import (
    REASON_HEARTBEAT_STALE,
    REASON_PRODUCER_EXITED,
    RESTARTABLE_PROCESS_FAILURE,
    HealthVerdict,
)
from PHX2.watchdog.state import (
    CIRCUIT_CLOSED,
    CIRCUIT_OPEN_STATUS,
    CircuitState,
    attempts_in_window,
    load_circuit_state,
    save_circuit_state,
)


def _dead_verdict() -> HealthVerdict:
    return HealthVerdict(RESTARTABLE_PROCESS_FAILURE, [REASON_PRODUCER_EXITED])


# --- exit-code policy ----------------------------------------------------- #

def test_exit_code_policy():
    assert classify_producer_exit(0, operator_stop_requested=True) == (
        EXIT_OPERATOR_CLEAN)
    # Under --run-forever a clean stop with no operator request means a bounded
    # read/tick budget ended the run; a fresh process legitimately resets it.
    assert classify_producer_exit(0, operator_stop_requested=False) == (
        EXIT_RESTARTABLE)
    # 2 = pre-work refusal, 3 = postflight failure: both re-run identically.
    assert classify_producer_exit(2, operator_stop_requested=False) == (
        EXIT_NONRESTARTABLE)
    assert classify_producer_exit(3, operator_stop_requested=False) == (
        EXIT_NONRESTARTABLE)
    assert classify_producer_exit(1, operator_stop_requested=False) == (
        EXIT_RESTARTABLE)
    assert classify_producer_exit(-1, operator_stop_requested=False) == (
        EXIT_RESTARTABLE)
    assert classify_producer_exit(None, operator_stop_requested=False) == (
        EXIT_RESTARTABLE)


# --- 13. unexpected exit restarts, after backoff ------------------------- #

def test_unexpected_producer_exit_restarts_after_backoff(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    watchdog.run(max_cycles=1)
    assert len(world.spawns) == 1

    # The producer vanishes without an operator stop.
    world.clear_producers()
    world.remove_producer_lock()
    world.slept.clear()

    watchdog.run(max_cycles=1)

    assert len(world.spawns) == 2, "no replacement producer was launched"
    assert 1.0 in world.slept, f"first backoff not applied: {world.slept}"
    history = config.restart_history_path.read_text(encoding="utf-8")
    assert "PHX2_WATCHDOG_RESTART" in history
    assert '"restart_index": 1' in history, (
        "the first launch must not have consumed the restart budget")
    assert any(reason in history for reason in
               (REASON_PRODUCER_EXITED, "PRODUCER_PROCESS_ABSENT"))


def test_producer_death_mid_loop_is_recorded_as_an_exit(tmp_path):
    """A producer that dies WHILE being supervised (one continuous run)."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    died = {"yet": False}

    def sleep_then_die(seconds: float) -> None:
        # The producer dies during the ordinary inter-cycle wait, while the
        # watchdog is still supervising it and still holds its child handle.
        world.sleep(seconds)
        if not died["yet"] and world.spawns:
            died["yet"] = True
            world.clear_producers()
            world.remove_producer_lock()

    watchdog._sleep = sleep_then_die               # noqa: SLF001

    watchdog.run(max_cycles=3)

    history = config.restart_history_path.read_text(encoding="utf-8")
    assert REASON_PRODUCER_EXITED in history, history
    assert len(world.spawns) == 2


def test_transient_process_query_failure_never_restarts(tmp_path):
    """An empty process table means the QUERY failed, not that the producer died."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    assert len(world.spawns) == 1

    watchdog._process_table_fn = lambda: []        # noqa: SLF001
    watchdog.run(max_cycles=3)

    assert len(world.spawns) == 1, (
        "a failed process query was mistaken for a dead producer")


def test_recycled_pid_is_not_mistaken_for_a_live_producer(tmp_path):
    """The recorded pid is alive but is no longer the producer."""

    from PHX2.watchdog.process import ProcessRecord

    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    producer_pid = world.spawns[0].producer_pid

    # The producer is gone; an unrelated program now holds that pid.
    world.clear_producers()
    world.remove_producer_lock()
    world.records.append(ProcessRecord(
        pid=int(producer_pid), parent_pid=1, name="notepad.exe",
        executable=r"C:\Windows\System32\notepad.exe",
        command_line="notepad.exe", create_time_utc=world.now()))

    watchdog.run(max_cycles=1)

    assert len(world.spawns) == 2, (
        "a recycled pid was treated as a healthy producer")


# --- 21. backoff sequence is exactly the configured table ---------------- #

def test_backoff_table_is_deterministic_and_bounded(tmp_path):
    config = make_config(tmp_path)
    assert [config.backoff_for_attempt(i) for i in range(7)] == [
        1.0, 2.0, 3.0, 4.0, 5.0, 5.0, 5.0], (
        "past the table end the LAST value must repeat, never grow")


def test_production_backoff_defaults_are_the_documented_sequence():
    from PHX2.watchdog.config import DEFAULT_RESTART_BACKOFF_SECONDS
    assert DEFAULT_RESTART_BACKOFF_SECONDS == (10.0, 30.0, 60.0, 300.0, 900.0)


def test_successive_restarts_walk_the_backoff_table(tmp_path):
    config = make_config(tmp_path, circuit_max_restarts=10)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    applied = []
    for _ in range(3):
        world.clear_producers()
        world.remove_producer_lock()
        world.slept.clear()
        watchdog.run(max_cycles=1)
        backoffs = [s for s in world.slept if s in (1.0, 2.0, 3.0, 4.0, 5.0)]
        applied.append(backoffs[0] if backoffs else None)

    assert applied == [1.0, 2.0, 3.0], applied


# --- 22. rolling restart limit opens the circuit ------------------------- #

def test_rolling_restart_limit_opens_the_circuit(tmp_path):
    config = make_config(tmp_path, circuit_max_restarts=2,
                         circuit_window_seconds=600.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    outcomes = []
    for _ in range(4):
        world.clear_producers()
        world.remove_producer_lock()
        outcomes.append(watchdog.run(max_cycles=1).outcome)

    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.status == CIRCUIT_OPEN_STATUS
    assert circuit.open_reason == "RESTART_BUDGET_EXHAUSTED"
    assert circuit.integrity_locked is False, (
        "a crash-loop breaker must not claim an integrity lock")
    assert circuit.restart_count_total == 2, circuit.restart_count_total
    assert "CIRCUIT_OPEN" in outcomes
    incident = config.last_incident_path.read_text(encoding="utf-8")
    assert "RESTART_BUDGET_EXHAUSTED" in incident


def test_attempts_outside_the_window_do_not_count(tmp_path):
    state = CircuitState(attempts_utc=[
        "2026-07-26T10:00:00Z", "2026-07-26T11:50:00Z", "2026-07-26T11:59:00Z"])
    assert attempts_in_window(
        state, now_utc="2026-07-26T12:00:00Z", window_seconds=1800.0) == 2


# --- 23. a stable interval resets the restart budget -------------------- #

def test_stable_run_resets_the_restart_budget(tmp_path):
    config = make_config(tmp_path, circuit_max_restarts=3,
                         stable_run_reset_seconds=60.0,
                         poll_interval_seconds=30.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    world.clear_producers()
    world.remove_producer_lock()
    watchdog.run(max_cycles=1)
    assert load_circuit_state(
        config.circuit_state_path).restart_count_total == 1

    # Now stay healthy long enough. A live producer writes a heartbeat every
    # tick, so the fake one must too -- otherwise it would go stale mid-window
    # and the run under test would no longer be a STABLE run at all.
    original_sleep = watchdog._sleep                       # noqa: SLF001

    def healthy_tick(seconds: float) -> None:
        original_sleep(seconds)
        if world.spawns:
            world.write_heartbeat(world.spawns[-1].run_dir)

    watchdog._sleep = healthy_tick                         # noqa: SLF001
    watchdog.run(max_cycles=6)

    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.attempts_utc == [], "restart budget was not reset"
    assert len(world.spawns) == 2, (
        "a heart-beating producer was restarted during the stable window")
    assert circuit.restart_count_total == 1, (
        "the lifetime counter must NOT be reset -- only the rolling budget")
    events = config.events_path.read_text(encoding="utf-8")
    assert "RESTART_BUDGET_RESET" in events


# --- 24. circuit state survives a watchdog restart ---------------------- #

def test_circuit_state_survives_watchdog_restart(tmp_path):
    config = make_config(tmp_path)
    state = CircuitState(status=CIRCUIT_OPEN_STATUS,
                         opened_at_utc="2026-07-26T12:00:00Z",
                         open_reason="CURSOR_QUARANTINED",
                         integrity_locked=True, restart_count_total=4)
    save_circuit_state(config.circuit_state_path, state)

    reloaded = load_circuit_state(config.circuit_state_path)
    assert reloaded.status == CIRCUIT_OPEN_STATUS
    assert reloaded.integrity_locked is True
    assert reloaded.open_reason == "CURSOR_QUARANTINED"
    assert reloaded.restart_count_total == 4
    assert reloaded.document_state == "VALID_PRIMARY"

    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    result = watchdog.run(max_cycles=2)
    assert world.spawns == [], "an open circuit still launched a producer"
    assert result.outcome == "CIRCUIT_OPEN"


def test_corrupt_circuit_document_fails_closed(tmp_path):
    config = make_config(tmp_path)
    config.circuit_state_path.parent.mkdir(parents=True, exist_ok=True)
    config.circuit_state_path.write_text("{not json", encoding="utf-8")

    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.is_open
    assert circuit.integrity_locked is True
    assert circuit.open_reason == "CIRCUIT_STATE_DOCUMENT_INVALID"


def test_circuit_backup_is_accepted_when_primary_is_lost(tmp_path):
    config = make_config(tmp_path)
    save_circuit_state(config.circuit_state_path,
                       CircuitState(restart_count_total=7))
    config.circuit_state_path.unlink()

    reloaded = load_circuit_state(config.circuit_state_path)
    assert reloaded.document_state == "VALID_BACKUP"
    assert reloaded.restart_count_total == 7


def test_tampered_circuit_payload_is_rejected(tmp_path):
    import json
    config = make_config(tmp_path)
    save_circuit_state(config.circuit_state_path,
                       CircuitState(restart_count_total=1))
    for path in (config.circuit_state_path,
                 config.circuit_state_path.with_name(
                     config.circuit_state_path.name + ".bak")):
        document = json.loads(path.read_text(encoding="utf-8"))
        document["payload"]["restart_count_total"] = 999
        path.write_text(json.dumps(document), encoding="utf-8")

    reloaded = load_circuit_state(config.circuit_state_path)
    assert reloaded.integrity_locked is True
    assert reloaded.open_reason == "CIRCUIT_STATE_DOCUMENT_INVALID"


# --- 25. operator clear-circuit ---------------------------------------- #

def test_operator_can_clear_a_crash_loop_circuit(tmp_path):
    config = make_config(tmp_path)
    save_circuit_state(config.circuit_state_path, CircuitState(
        status=CIRCUIT_OPEN_STATUS, open_reason="RESTART_BUDGET_EXHAUSTED",
        integrity_locked=False, attempts_utc=["2026-07-26T12:00:00Z"]))
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    result = watchdog.clear_circuit()

    assert result["cleared"] is True
    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.status == CIRCUIT_CLOSED
    assert circuit.attempts_utc == []


def test_integrity_lock_is_not_cleared_without_explicit_acknowledgement(tmp_path):
    config = make_config(tmp_path)
    save_circuit_state(config.circuit_state_path, CircuitState(
        status=CIRCUIT_OPEN_STATUS, open_reason="CURSOR_QUARANTINED",
        integrity_locked=True))
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    refused = watchdog.clear_circuit()
    assert refused["cleared"] is False
    assert refused["reason"] == (
        "INTEGRITY_LOCK_REQUIRES_EXPLICIT_ACKNOWLEDGEMENT")
    assert load_circuit_state(config.circuit_state_path).is_open

    allowed = watchdog.clear_circuit(acknowledge_integrity=True)
    assert allowed["cleared"] is True
    assert not load_circuit_state(config.circuit_state_path).is_open


# --- integrity verdict never loops ------------------------------------- #

def test_cursor_quarantine_opens_circuit_and_never_relaunches(tmp_path):
    """The daemon-level proof for offline tests 17-18: zero extra spawns."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    assert len(world.spawns) == 1

    # The live producer now reports a quarantined cursor.
    world.write_heartbeat(world.spawns[0].run_dir, cursor_quarantined=True)

    result = watchdog.run(max_cycles=4)

    assert len(world.spawns) == 1, "an integrity failure triggered a restart"
    assert result.outcome == "CIRCUIT_OPEN"
    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.integrity_locked is True
    assert circuit.open_reason == "CURSOR_QUARANTINED"
    incident = config.last_incident_path.read_text(encoding="utf-8")
    assert "CURSOR_QUARANTINED" in incident
    assert "operator_action_required" in incident


def test_structural_checkpoint_failure_opens_circuit_once(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    # A structural failure is signalled by the failure CATEGORY plus an actually
    # failed write -- not by the durability status, and not by a flat counter.
    world.write_heartbeat(
        world.spawns[0].run_dir,
        cursor_durability="CHECKPOINT_DURABILITY_DEGRADED",
        cursor_last_failure_category="STRUCTURAL_CHECKPOINT_FAILURE",
        checkpoint_attempted=48, checkpoint_succeeded=34,
        checkpoint_failed=14)

    watchdog.run(max_cycles=5)

    assert len(world.spawns) == 1
    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.open_reason == "CURSOR_STRUCTURAL_CHECKPOINT_FAILURE"
    opened = [line for line in
              config.events_path.read_text(encoding="utf-8").splitlines()
              if "CIRCUIT_OPENED" in line]
    assert len(opened) == 1, f"circuit opened {len(opened)} times (looping)"


def test_duplicate_yellowstone_owner_opens_circuit(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    world.write_heartbeat(world.spawns[0].run_dir, owner_count=2,
                          max_streams=2)

    result = watchdog.run(max_cycles=3)

    assert len(world.spawns) == 1
    assert result.outcome == "CIRCUIT_OPEN"
    assert load_circuit_state(
        config.circuit_state_path).open_reason == "DUPLICATE_YELLOWSTONE_OWNER"


def test_launcher_spawn_failure_opens_circuit_without_looping(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.spawn_should_raise = True
    watchdog = make_watchdog(config, world)

    result = watchdog.run(max_cycles=3)

    assert world.spawns == []
    assert result.outcome == "CIRCUIT_OPEN"
    assert load_circuit_state(
        config.circuit_state_path).open_reason == "LAUNCHER_SPAWN_FAILED"
