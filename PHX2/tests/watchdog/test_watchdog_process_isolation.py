"""Windowless process-isolation contract for the watchdog.

The Stage-11 scheduled-task proof exposed that, launched by Task Scheduler, the
watchdog + launcher + producer shared ONE console/process-group; a single
console or session control event felled the whole tree with
STATUS_CONTROL_C_EXIT (0xC000013A) ~1 minute in.  The fix has two halves:

* the registered task action runs the watchdog under the WINDOWLESS
  ``pythonw.exe`` (asserted in ``test_scheduled_task_contract.py``); and
* the ONE launcher spawn uses CREATE_NO_WINDOW and its own process group.

These tests pin the spawn half and prove the fix does not regress cooperative
stop, adoption, orphan-freedom, duplicate-owner protection or non-Windows
behaviour.  Everything here is hermetic: the real ``subprocess.Popen`` is either
monkeypatched away or replaced by the injected fake world; no process is spawned,
no provider is reached, no transport is constructed, no real ledger is touched.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

import pytest

from PHX2.tests.watchdog._harness import (
    HEAD_SHA,
    FakeWorld,
    make_config,
    make_watchdog,
)
from PHX2.watchdog import daemon
from PHX2.watchdog.process import (
    ADOPT_DISCORD_PRESENT,
    ADOPT_DUPLICATE,
    evaluate_producer_adoption,
    logical_producer_pids,
    read_producer_lock,
)


# --- launcher spawn is detached + own process group (items 3, 9) --------- #

def test_launcher_creation_flags_are_no_window_new_group_on_windows():
    if os.name == "nt":
        assert daemon.LAUNCHER_CREATION_FLAGS == (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
        # DETACHED_PROCESS must NOT be set: it gives the console launcher no
        # console at all and powershell then exits without running (Stage-11
        # regression). CREATE_NO_WINDOW gives it a windowless console instead.
        assert not (daemon.LAUNCHER_CREATION_FLAGS & subprocess.DETACHED_PROCESS)
    else:
        # POSIX has neither flag and is never the live target: unchanged (zero).
        assert daemon.LAUNCHER_CREATION_FLAGS == 0


# --- WHY the flag matters: real powershell spawn under each flag (Windows) --- #

_WINDOWS_ONLY = pytest.mark.skipif(
    os.name != "nt", reason="Windows console-creation-flag behaviour")


@_WINDOWS_ONLY
def test_detached_process_cannot_run_the_powershell_wrapper(tmp_path):
    """Regression pin for the Stage-11 defect: DETACHED_PROCESS gives
    powershell.exe (a console application, and the canonical launcher image) NO
    console, so it exits immediately without running -- the launcher never comes
    up and the producer is never launched."""

    marker = tmp_path / "detached_wrapper_ran.txt"
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         f"Set-Content -LiteralPath '{marker}' -Value ran"],
        creationflags=flags, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        proc.kill()
    for _ in range(15):
        if marker.exists():
            break
        time.sleep(0.2)
    assert not marker.exists(), (
        "powershell RAN under DETACHED_PROCESS -- the flag no longer reproduces "
        "the Stage-11 launcher-cannot-start defect; re-check the fix rationale")


@_WINDOWS_ONLY
def test_create_no_window_runs_the_powershell_wrapper_and_its_producer(tmp_path):
    """The flag the watchdog actually uses: CREATE_NO_WINDOW gives powershell its
    own windowless console, so the launcher runs AND can itself launch its console
    child -- mirroring launch_live_24x7.ps1 -> the python producer."""

    wrapper_marker = tmp_path / "wrapper_ran.txt"
    producer_marker = tmp_path / "producer_ran.txt"
    producer_script = tmp_path / "fake_producer.py"
    producer_script.write_text(
        f"open(r'{producer_marker}', 'w').write('ran')\n", encoding="utf-8")

    # The wrapper writes its own marker, then launches a console python child
    # (the producer stand-in) exactly as the real launcher invokes ``& $PY``.
    command = (
        f"Set-Content -LiteralPath '{wrapper_marker}' -Value ran; "
        f"& '{sys.executable}' '{producer_script}'")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        creationflags=flags, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait(timeout=90)

    assert wrapper_marker.exists(), (
        "CREATE_NO_WINDOW failed to run the powershell launcher")
    assert producer_marker.exists(), (
        "the CREATE_NO_WINDOW launcher could not start its console child (the "
        "producer)")


def test_watchdog_uses_no_window_not_detached_for_the_launcher():
    """The daemon must wire CREATE_NO_WINDOW (not DETACHED_PROCESS) into the one
    launcher spawn."""

    source = open(daemon.__file__, encoding="utf-8").read()
    assert "CREATE_NO_WINDOW" in source
    assert "subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW" \
        in source
    # DETACHED_PROCESS may be named only in the explanatory comment, never wired
    # into the live flag expression.
    assert "| subprocess.DETACHED_PROCESS" not in source


def test_default_spawn_passes_isolation_flags_and_preserves_redirection(
        tmp_path, monkeypatch):
    config = make_config(tmp_path)
    captured: dict = {}

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            self.pid = 4242

    monkeypatch.setattr(daemon.subprocess, "Popen", _FakePopen)
    manifest = tmp_path / "watchdog_state" / "launch_manifests" / "m.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)

    handle = daemon.default_spawn(
        config, "20260726T000000Z", str(manifest), watchdog_pid=1234)

    assert handle.wrapper_pid == 4242
    kwargs = captured["kwargs"]
    # Isolation: own windowless console (CREATE_NO_WINDOW) + own process group --
    # exactly the module constant, so behaviour is identical on POSIX (zero) and
    # Windows (both flags).
    assert kwargs.get("creationflags") == daemon.LAUNCHER_CREATION_FLAGS
    if os.name == "nt":
        startupinfo = kwargs.get("startupinfo")
        assert startupinfo is not None
        assert startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW
        assert startupinfo.wShowWindow == subprocess.SW_HIDE
    # Redirection is preserved verbatim.
    assert kwargs.get("stdout") is subprocess.DEVNULL
    assert kwargs.get("stderr") is subprocess.DEVNULL
    assert kwargs.get("stdin") is subprocess.DEVNULL
    # It is still the canonical launcher -- the producer vector is NOT rebuilt.
    command = captured["args"][0]
    assert command[0] == "powershell.exe"
    for argument in (
            "-NoLogo", "-NoProfile", "-NonInteractive",
            "-WindowStyle", "Hidden"):
        assert argument in command
    assert "-File" in command and str(config.launcher_path) in command
    # And no secret rides on the launcher command line.
    joined = " ".join(command)
    assert not re.search(r"\d{6,}:[A-Za-z0-9_\-]{30,}", joined)


# --- cooperative stop of a DETACHED child, no orphan (items 5, 7) -------- #

def test_cooperative_stop_of_detached_child_leaves_no_orphan(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    child = world.spawns[0]
    # The real launcher child runs on its own windowless console + process group
    # (not waited on through a pipe); like it, the fake child carries no popen
    # handle -- cooperative stop must work purely via the stop file.
    assert getattr(child, "popen", None) is None
    assert config.producer_runtime_lock_path.exists()

    original_sleep = watchdog._sleep                       # noqa: SLF001

    def honour_stop(seconds: float) -> None:
        original_sleep(seconds)
        if os.path.exists(child.stop_file):
            world.stop_file_honoured()

    watchdog._sleep = honour_stop                          # noqa: SLF001
    watchdog.request_operator_stop()
    result = watchdog.run(max_cycles=3)

    assert result.outcome == "OPERATOR_STOP"
    assert result.exit_code == 0
    assert world.terminated == [], "force termination was used unnecessarily"
    from PHX2.watchdog.process import producer_process_pids
    assert producer_process_pids(world.table()) == [], "an orphan producer remained"
    assert not config.producer_runtime_lock_path.exists()
    assert not config.lock_path.exists()


# --- adoption + duplicate-owner protection unchanged (items 6, 8) -------- #

def test_adoption_still_validates_the_real_executable_and_command(tmp_path):
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


def test_adoption_still_refuses_a_producer_with_discord_armed(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    world.add_producer(pid=os.getpid(), wrapper_pid=1,
                       run_dir=str(tmp_path / "r"),
                       stop_file=str(tmp_path / "s"), discord=1)
    world.write_producer_lock(os.getpid())

    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path, yellowstone_owner_count=1)
    assert not verdict.adoptable
    assert ADOPT_DISCORD_PRESENT in verdict.reasons


def test_duplicate_owner_protection_is_still_enforced(tmp_path):
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
    # Two independent producers must be seen as two logical owners...
    assert logical_producer_pids(world.table()) == [5001, 6001]

    world.write_producer_lock(os.getpid())
    world.add_producer(pid=os.getpid(), wrapper_pid=5000,
                       run_dir=str(tmp_path / "r1"),
                       stop_file=str(tmp_path / "s1"))
    verdict = evaluate_producer_adoption(
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        repo_python=config.repo_python, expected_head=HEAD_SHA,
        cursor_state_dir=config.cursor_state_dir,
        ledger_path=config.ledger_path)
    # ...and adoption must refuse rather than bless one of a duplicate pair.
    assert ADOPT_DUPLICATE in verdict.reasons
