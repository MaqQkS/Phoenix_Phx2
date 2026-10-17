"""Single-instance, adoption, stale-lock and ambiguity behaviour.

Covers required offline tests 1-8, 14 and 33-34 (sole owners).

Hermetic: fabricated process table, fake spawn, temp paths.  No socket, no
provider, no transport, no real ledger, no real cursor/recovery state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from PHX2.tests.watchdog._harness import (
    HEAD_SHA,
    OTHER_SHA,
    FakeWorld,
    find_dead_pid,
    make_config,
    make_watchdog,
)
from PHX2.watchdog.daemon import ALREADY_RUNNING
from PHX2.watchdog.process import (
    ADOPT_DISCORD_PRESENT,
    ADOPT_DUPLICATE,
    ADOPT_EXECUTABLE_MISMATCH,
    ADOPT_HEAD_MISMATCH,
    ADOPT_LOCK_MALFORMED,
    ADOPT_MODULE_MISMATCH,
    ADOPT_OWNER_DEAD,
    ADOPT_SHADOW_MISSING,
    ADOPT_TELEGRAM_MISMATCH,
    ProcessRecord,
    WatchdogLock,
    evaluate_producer_adoption,
    evaluate_stale_producer_lock,
    logical_producer_pids,
    new_instance_nonce,
    read_producer_lock,
    remove_stale_producer_lock,
)


# --- 1. one watchdog starts one producer ---------------------------------- #

def test_one_watchdog_starts_exactly_one_producer(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    result = watchdog.run(max_cycles=3)

    assert len(world.spawns) == 1, "watchdog launched more than one producer"
    assert result.exit_code == 0
    assert logical_producer_pids(world.table()) == [os.getpid()]


def test_running_producer_is_never_duplicated_across_cycles(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    watchdog.run(max_cycles=8)

    assert len(world.spawns) == 1
    assert len(logical_producer_pids(world.table())) == 1


# --- 2. a second watchdog returns ALREADY_RUNNING ------------------------- #

def test_second_watchdog_returns_already_running_and_does_not_disturb(tmp_path):
    """A lock held by a DIFFERENT live process must stop a second watchdog.

    The two watchdogs in this test share one interpreter, so ``os.getpid()``
    cannot stand in for "another watchdog" -- a self-owned lock is deliberately
    re-entrant.  ``os.getppid()`` is a genuinely different, genuinely live
    process, which is exactly the production shape.
    """

    config = make_config(tmp_path)
    world = FakeWorld(config)
    first = make_watchdog(config, world)
    first.run(max_cycles=1)

    other_watchdog_pid = os.getppid()
    assert other_watchdog_pid != os.getpid()
    from PHX2.watchdog.process import pid_alive as _alive
    assert _alive(other_watchdog_pid), "parent process is expected to be alive"

    config.lock_path.parent.mkdir(parents=True, exist_ok=True)
    config.lock_path.write_text(json.dumps({
        "schema_version": "PHX2_WATCHDOG_LOCK_V1",
        "watchdog_pid": other_watchdog_pid,
        "watchdog_started_at_utc": world.now(),
        "repo_head": HEAD_SHA,
        "launcher_sha256": None,
        "instance_nonce": "foreign-instance-nonce",
    }), encoding="utf-8")
    before = config.lock_path.read_bytes()

    second = make_watchdog(config, world)
    spawns_before = len(world.spawns)
    result = second.run(max_cycles=2)

    assert result.outcome == ALREADY_RUNNING
    assert result.exit_code == 0
    assert len(world.spawns) == spawns_before, (
        "the second watchdog started a producer")
    assert config.lock_path.read_bytes() == before, (
        "the other watchdog's lock was disturbed")


def test_stale_watchdog_lock_is_reclaimed(tmp_path):
    """A lock whose owner is proven dead must not block a new watchdog."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    config.lock_path.parent.mkdir(parents=True, exist_ok=True)
    config.lock_path.write_text(json.dumps({
        "schema_version": "PHX2_WATCHDOG_LOCK_V1",
        "watchdog_pid": find_dead_pid(),
        "instance_nonce": "dead-instance",
    }), encoding="utf-8")

    lock = WatchdogLock(config.lock_path)
    result = lock.acquire(
        repo_head=HEAD_SHA, launcher_sha256=None,
        nonce=new_instance_nonce(), table=world.table(), now_utc=world.now())

    assert result.acquired
    assert result.outcome == "LOCK_RECLAIMED_STALE"
    assert lock.holder_pid() == os.getpid()
    assert lock.release()


# --- 3. a valid existing producer is adopted ------------------------------ #

def test_valid_existing_producer_is_adopted_not_relaunched(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "paid_primary_live_24x7_EXISTING"
    stop_file = tmp_path / "operator_logs" / "EXISTING" / "STOP_REQUESTED"
    world.add_wrapper(pid=31000)
    world.add_producer(pid=os.getpid(), wrapper_pid=31000,
                       run_dir=str(run_dir), stop_file=str(stop_file))
    world.write_producer_lock(os.getpid())
    world.write_heartbeat(str(run_dir))

    watchdog = make_watchdog(config, world)
    result = watchdog.run(max_cycles=3)

    assert world.spawns == [], "an already-valid producer was duplicated"
    assert result.exit_code == 0
    events = config.events_path.read_text(encoding="utf-8")
    assert "PRODUCER_ADOPTED" in events


def test_adoption_predicate_accepts_the_canonical_producer(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"))
    world.write_producer_lock(os.getpid())

    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path, yellowstone_owner_count=1)

    assert verdict.adoptable, verdict.reasons
    assert verdict.producer_pid == os.getpid()


# --- 4. an invalid process is NOT adopted -------------------------------- #

@pytest.mark.parametrize("kwargs,expected", [
    ({"expected_head": OTHER_SHA}, ADOPT_HEAD_MISMATCH),
    ({"telegram": 0}, ADOPT_TELEGRAM_MISMATCH),
    ({"telegram": 2}, ADOPT_TELEGRAM_MISMATCH),
    ({"discord": 1}, ADOPT_DISCORD_PRESENT),
    ({"policy": "enforce"}, ADOPT_SHADOW_MISSING),
])
def test_invalid_producer_is_refused_for_the_exact_reason(tmp_path, kwargs,
                                                         expected):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"), **kwargs)
    world.write_producer_lock(os.getpid())

    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)

    assert not verdict.adoptable
    assert expected in verdict.reasons


def test_foreign_python_process_is_not_adopted(tmp_path):
    """A live python process at the lock's pid that is NOT the producer."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.records.append(ProcessRecord(
        pid=os.getpid(), parent_pid=1, name="python.exe",
        executable=r"C:\Program Files\Python312\python.exe",
        command_line='"python.exe" -m some.other.tool --run',
        create_time_utc=world.now()))
    world.write_producer_lock(os.getpid())

    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)

    assert not verdict.adoptable
    assert ADOPT_EXECUTABLE_MISMATCH in verdict.reasons
    assert ADOPT_MODULE_MISMATCH in verdict.reasons


# --- 5. a stale lock is removed ONLY on owner-dead proof ----------------- #

def test_stale_lock_removed_only_after_owner_dead_proof(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    dead = find_dead_pid()
    world.write_producer_lock(dead)

    verdict = evaluate_stale_producer_lock(
        lock=read_producer_lock(config.producer_runtime_lock_path),
        table=world.table(), yellowstone_owner_count=0)

    assert verdict.removable
    assert verdict.reason == "STALE_LOCK_OWNER_PROVEN_DEAD"
    assert verdict.evidence["holder_alive"] is False
    assert verdict.evidence["matching_producer_pids"] == []
    assert remove_stale_producer_lock(
        config.producer_runtime_lock_path, verdict=verdict)
    assert not config.producer_runtime_lock_path.exists()


def test_live_owner_lock_is_never_removed(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.write_producer_lock(os.getpid())

    verdict = evaluate_stale_producer_lock(
        lock=read_producer_lock(config.producer_runtime_lock_path),
        table=world.table(), yellowstone_owner_count=0)

    assert not verdict.removable
    assert verdict.reason == "LOCK_OWNER_ALIVE"
    assert not remove_stale_producer_lock(
        config.producer_runtime_lock_path, verdict=verdict)
    assert config.producer_runtime_lock_path.exists()


def test_dead_owner_but_surviving_producer_process_refuses_removal(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"))
    world.write_producer_lock(find_dead_pid())

    verdict = evaluate_stale_producer_lock(
        lock=read_producer_lock(config.producer_runtime_lock_path),
        table=world.table(), yellowstone_owner_count=0)

    assert not verdict.removable
    assert verdict.reason == "MATCHING_PRODUCER_PROCESS_STILL_PRESENT"


def test_unknown_owner_count_is_not_proof_of_zero(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.write_producer_lock(find_dead_pid())

    verdict = evaluate_stale_producer_lock(
        lock=read_producer_lock(config.producer_runtime_lock_path),
        table=world.table(), yellowstone_owner_count=None)

    assert not verdict.removable
    assert verdict.reason == "YELLOWSTONE_OWNER_COUNT_UNKNOWN"


# --- 6. ambiguous producer ownership fails closed ------------------------ #

def test_malformed_producer_lock_fails_closed(tmp_path):
    config = make_config(tmp_path)
    config.producer_runtime_lock_path.parent.mkdir(parents=True, exist_ok=True)
    config.producer_runtime_lock_path.write_text("not-a-pid", encoding="utf-8")
    world = FakeWorld(config)

    lock = read_producer_lock(config.producer_runtime_lock_path)
    assert lock.malformed

    adoption = evaluate_producer_adoption(
        table=world.table(), lock=lock, repo_python=config.repo_python,
        expected_head=HEAD_SHA, cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)
    assert not adoption.adoptable
    assert ADOPT_LOCK_MALFORMED in adoption.reasons

    stale = evaluate_stale_producer_lock(
        lock=lock, table=world.table(), yellowstone_owner_count=0)
    assert not stale.removable, "a malformed lock must never be removed blindly"


def test_ambiguous_ownership_opens_circuit_without_launching(tmp_path):
    """A malformed producer lock present at startup must NOT lead to a launch."""

    config = make_config(tmp_path)
    config.producer_runtime_lock_path.parent.mkdir(parents=True, exist_ok=True)
    config.producer_runtime_lock_path.write_text("garbage", encoding="utf-8")
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)

    result = watchdog.run(max_cycles=2)

    assert world.spawns == [], "launched a producer over an ambiguous lock"
    assert result.outcome == "CIRCUIT_OPEN"
    incident = config.last_incident_path.read_text(encoding="utf-8")
    assert "AMBIGUOUS_PRODUCER_LOCK_OWNERSHIP" in incident


def test_lock_owner_dead_reason_is_reported(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.write_producer_lock(find_dead_pid())

    adoption = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)

    assert not adoption.adoptable
    assert ADOPT_OWNER_DEAD in adoption.reasons


# --- 7. duplicate producer detection ------------------------------------- #

def test_reexec_shim_pair_counts_as_one_logical_producer(tmp_path):
    """The repo venv python is a re-exec stub; a naive count would say two."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_wrapper(pid=5000)
    world.add_reexec_shim_pair(
        shim_pid=5001, real_pid=5002, wrapper_pid=5000,
        run_dir=str(tmp_path / "r"), stop_file=str(tmp_path / "s"))

    assert logical_producer_pids(world.table()) == [5001]


def test_reexec_real_half_holding_the_lock_is_adoptable(tmp_path):
    """The venv re-exec stub: the LOCK HOLDER reports the BASE interpreter.

    Measured live on 2026-07-26 during the first Stage-10 smoke:

        pid 49628  <repo>\\.venv\\Scripts\\python.exe        (shim, logical root)
        pid 40588  C:\\Program Files\\Python312\\python.exe   (real, lock holder)

    Comparing the lock holder's executable against the venv path alone refused a
    valid canonical producer with PRODUCER_EXECUTABLE_NOT_REPO_VENV and opened the
    circuit as AMBIGUOUS_PRODUCER_OWNERSHIP.
    """

    config = make_config(tmp_path)
    base_python = tmp_path / "BasePython" / "python.exe"
    base_python.parent.mkdir(parents=True, exist_ok=True)
    base_python.write_bytes(b"")
    venv_root = Path(config.repo_python).parent.parent
    (venv_root / "pyvenv.cfg").write_text(
        f"home = {base_python.parent}\n"
        "include-system-site-packages = false\n"
        f"executable = {base_python}\n", encoding="utf-8")

    from PHX2.watchdog.process import acceptable_producer_executables
    accepted = acceptable_producer_executables(config.repo_python)
    assert len(accepted) == 2, accepted

    world = FakeWorld(config)
    world.add_wrapper(pid=59144)
    # shim: the logical root, venv path
    world.add_producer(pid=49628, wrapper_pid=59144,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"))
    # real: the lock holder, BASE interpreter path
    real = ProcessRecord(
        pid=os.getpid(), parent_pid=49628, name="python.exe",
        executable=str(base_python),
        command_line=world.records[-1].command_line,
        create_time_utc=world.now())
    world.records.append(real)
    world.write_producer_lock(os.getpid())

    assert logical_producer_pids(world.table()) == [49628], (
        "the shim/real pair must still collapse to ONE logical producer")

    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path, yellowstone_owner_count=1)

    assert verdict.adoptable, verdict.reasons
    assert verdict.checks["executable_accepted"] is True


def test_an_unrelated_interpreter_is_still_refused(tmp_path):
    """The allow-list is exactly two known binaries, not "any python"."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"))
    world.records[-1] = ProcessRecord(
        pid=os.getpid(), parent_pid=1, name="python.exe",
        executable=r"C:\SomeOther\Python\python.exe",
        command_line=world.records[-1].command_line,
        create_time_utc=world.now())
    world.write_producer_lock(os.getpid())

    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)

    assert not verdict.adoptable
    assert ADOPT_EXECUTABLE_MISMATCH in verdict.reasons


def test_real_repo_venv_accepts_its_own_base_interpreter():
    """Against the ACTUAL repository venv, both halves must be accepted."""

    from PHX2.free_tier_producer.launcher_contract import REPO_PYTHON
    from PHX2.watchdog.process import acceptable_producer_executables

    accepted = acceptable_producer_executables(REPO_PYTHON)
    assert any("\\.venv\\" in path.lower() for path in accepted), accepted
    assert len(accepted) >= 2, (
        f"the venv base interpreter was not resolved: {accepted}")


def test_two_independent_producers_are_detected_as_duplicates(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_wrapper(pid=5000)
    world.add_wrapper(pid=6000)
    world.add_reexec_shim_pair(
        shim_pid=5001, real_pid=5002, wrapper_pid=5000,
        run_dir=str(tmp_path / "r1"), stop_file=str(tmp_path / "s1"))
    world.add_reexec_shim_pair(
        shim_pid=6001, real_pid=6002, wrapper_pid=6000,
        run_dir=str(tmp_path / "r2"), stop_file=str(tmp_path / "s2"))

    assert logical_producer_pids(world.table()) == [5001, 6001]

    world.write_producer_lock(os.getpid())
    world.add_producer(pid=os.getpid(), wrapper_pid=5000,
                       run_dir=str(tmp_path / "r1"),
                       stop_file=str(tmp_path / "s1"))
    adoption = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)
    assert ADOPT_DUPLICATE in adoption.reasons


# --- 8 / 14. restart never happens over a live producer ------------------ #

def test_restart_is_refused_while_a_producer_is_still_alive(tmp_path):
    """Force the stop path to fail and prove no replacement is launched."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    assert len(world.spawns) == 1

    # The producer ignores the stop file and never exits; terminate is a no-op.
    world.terminate = lambda pid: False        # type: ignore[assignment]
    watchdog._terminate_fn = world.terminate   # noqa: SLF001
    from PHX2.watchdog.health import (
        REASON_HEARTBEAT_STALE,
        RESTARTABLE_STALE_HEARTBEAT,
        HealthVerdict,
    )
    circuit, launched = watchdog._restart(       # noqa: SLF001
        table=world.table(),
        circuit=__import__(
            "PHX2.watchdog.state", fromlist=["load_circuit_state"]
        ).load_circuit_state(config.circuit_state_path),
        verdict=HealthVerdict(RESTARTABLE_STALE_HEARTBEAT,
                              [REASON_HEARTBEAT_STALE]),
        facts={"paid_ledger_parse_ok": True})

    assert launched is False
    assert len(world.spawns) == 1, "a second producer was launched"
    assert circuit.is_open
    assert circuit.open_reason == "PRODUCER_WOULD_NOT_STOP"
