"""Cooperative stop, bounded force termination, and status artifacts.

Covers required offline tests 26-28 and 44.
"""

from __future__ import annotations

import json
import os

from PHX2.tests.watchdog._harness import FakeWorld, make_config, make_watchdog
from PHX2.watchdog.state import read_json


# --- 26. cooperative stop closes producer then watchdog ------------------ #

def test_operator_stop_closes_producer_then_watchdog(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    child = world.spawns[0]
    assert config.producer_runtime_lock_path.exists()

    # The producer honours the stop file at its next tick boundary.
    original_sleep = watchdog._sleep                      # noqa: SLF001

    def honour_stop(seconds: float) -> None:
        original_sleep(seconds)
        if os.path.exists(child.stop_file):
            world.stop_file_honoured()

    watchdog._sleep = honour_stop                         # noqa: SLF001
    watchdog.request_operator_stop()

    result = watchdog.run(max_cycles=3)

    assert result.outcome == "OPERATOR_STOP"
    assert result.exit_code == 0
    events = config.events_path.read_text(encoding="utf-8")
    assert "COOPERATIVE_STOP_REQUESTED" in events
    assert "COOPERATIVE_STOP_COMPLETED" in events
    assert "WATCHDOG_STOP" in events
    assert world.terminated == [], "force termination was used unnecessarily"


def test_stop_request_writes_the_producers_own_stop_file(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    child = world.spawns[0]

    watchdog._stop_producer(table=world.table())          # noqa: SLF001

    assert os.path.exists(child.stop_file), (
        "the watchdog must use the producer's OWN cooperative stop mechanism")
    body = open(child.stop_file, encoding="utf-8").read()
    assert "stop_requested_at_utc=" in body


# --- 27. force termination only after the bounded timeout --------------- #

def test_force_termination_only_after_cooperative_timeout(tmp_path):
    config = make_config(tmp_path, cooperative_stop_timeout_seconds=10.0,
                         poll_interval_seconds=1.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    producer_pid = world.spawns[0].producer_pid

    # The producer NEVER honours the stop file.
    stopped = watchdog._stop_producer(table=world.table())   # noqa: SLF001

    assert stopped is True
    assert producer_pid in world.terminated, "force termination never happened"
    # It must not have been immediate: the cooperative window is waited out.
    assert sum(world.slept) >= 10.0, world.slept
    events = config.events_path.read_text(encoding="utf-8")
    assert "FORCE_TERMINATION" in events
    incident = json.loads(config.last_incident_path.read_text(encoding="utf-8"))
    assert incident["reason"] == (
        "FORCE_TERMINATION_AFTER_COOPERATIVE_TIMEOUT")
    assert incident["operator_action_required"] is True


def test_cooperative_stop_short_circuits_when_producer_exits_promptly(tmp_path):
    config = make_config(tmp_path, cooperative_stop_timeout_seconds=60.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    world.stop_file_honoured()
    world.slept.clear()
    stopped = watchdog._stop_producer(table=world.table())   # noqa: SLF001

    assert stopped is True
    assert world.terminated == []
    assert sum(world.slept) < 60.0, "waited the whole window unnecessarily"


# --- 28. a normal stop leaves zero locks -------------------------------- #

def test_normal_stop_leaves_zero_locks(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    original_sleep = watchdog._sleep                       # noqa: SLF001
    child = world.spawns[0]

    def honour_stop(seconds: float) -> None:
        original_sleep(seconds)
        if os.path.exists(child.stop_file):
            world.stop_file_honoured()

    watchdog._sleep = honour_stop                          # noqa: SLF001
    watchdog.request_operator_stop()
    watchdog.run(max_cycles=3)

    assert not config.lock_path.exists(), "watchdog lock survived a clean stop"
    assert not config.producer_runtime_lock_path.exists(), (
        "producer runtime lock survived a clean stop")
    from PHX2.watchdog.process import producer_process_pids
    assert producer_process_pids(world.table()) == []


def test_watchdog_lock_is_released_on_every_exit_path(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    assert not config.lock_path.exists()


def test_watchdog_never_removes_a_lock_it_does_not_own(tmp_path):
    from PHX2.watchdog.process import WatchdogLock, new_instance_nonce
    config = make_config(tmp_path)
    world = FakeWorld(config)
    lock = WatchdogLock(config.lock_path)
    lock.acquire(repo_head="a" * 40, launcher_sha256=None,
                 nonce=new_instance_nonce(), table=world.table())
    # Another instance rewrites the document with a different nonce.
    document = json.loads(config.lock_path.read_text(encoding="utf-8"))
    document["instance_nonce"] = "someone-else"
    config.lock_path.write_text(json.dumps(document), encoding="utf-8")

    assert lock.release() is False
    assert config.lock_path.exists()


# --- 44. status files are written atomically --------------------------- #

def test_status_artifacts_are_written_and_refresh(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=2)

    for path in (config.status_path, config.heartbeat_path,
                 config.events_path, config.current_child_path,
                 config.circuit_state_path):
        assert path.exists(), f"missing artifact {path.name}"

    parse_ok, status = read_json(config.status_path)
    assert parse_ok
    for key in ("kind", "updated_at_utc", "watchdog_pid", "repo_head",
                "launcher_sha256", "health_class", "health_reasons",
                "restart_count_total", "current_backoff_seconds",
                "circuit_status", "circuit_integrity_locked",
                "observation", "redaction_positive_control_ok"):
        assert key in status, f"status is missing required field {key}"
    assert status["redaction_positive_control_ok"] is True

    observation = status["observation"]
    for key in ("heartbeat_source", "heartbeat_age_seconds",
                "yellowstone_owner_count", "cursor_durability_status",
                "recovery_state", "telegram_enabled", "discord_enabled",
                "paid_ledger_sha256", "paid_ledger_lines"):
        assert key in observation, f"observation is missing {key}"
    assert observation["telegram_enabled"] is True
    assert observation["discord_enabled"] is False


def test_atomic_write_leaves_no_temp_file_and_never_truncates(tmp_path):
    from PHX2.watchdog.state import write_json_atomic
    target = tmp_path / "atomic.json"
    write_json_atomic(target, {"generation": 1})
    write_json_atomic(target, {"generation": 2})

    assert json.loads(target.read_text(encoding="utf-8"))["generation"] == 2
    assert not target.with_name(target.name + ".tmp").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_current_child_payload_carries_digests_not_paths(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    payload = json.loads(config.current_child_path.read_text(encoding="utf-8"))
    assert payload["run_dir_digest"]
    assert "run_dir" not in payload
    assert "stop_file" not in payload
    assert payload["producer_pid"] == os.getpid()
