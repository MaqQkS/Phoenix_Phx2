"""Deterministic regression contract for the recurring-console remediation.

No test opens a real ledger, provider or transport.  The only live observation
is the read-only in-process Win32 snapshot used by production itself.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import subprocess
from pathlib import Path

import pytest

import PHX2.operator_cli as operator_cli
from PHX2.tests.watchdog._harness import make_config
from PHX2.watchdog import daemon
from PHX2.watchdog import process
from PHX2.watchdog.windows_launch import hidden_startupinfo


REPO_ROOT = Path(__file__).resolve().parents[3]
TASK_TOOL = REPO_ROOT / "PHX2" / "scripts" / "phx2_watchdog_task.ps1"
STARTUP_PYTHON = (
    REPO_ROOT / "main.py",
    REPO_ROOT / "PHX2" / "operator_cli.py",
    *(REPO_ROOT / "PHX2" / "watchdog").glob("*.py"),
)


def _assert_hidden(startupinfo) -> None:
    if os.name != "nt":
        assert startupinfo is None
        return
    assert startupinfo is not None
    assert startupinfo.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startupinfo.wShowWindow == subprocess.SW_HIDE


def _subprocess_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Attribute) \
                and isinstance(node.func.value, ast.Name):
            name = f"{node.func.value.id}.{node.func.attr}"
        if name in ("subprocess.run", "subprocess.Popen"):
            yield node


@pytest.mark.skipif(os.name != "nt", reason="native Win32 process snapshot")
def test_recurring_process_observation_is_native_and_spawns_no_shell(
        monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("recurring observation attempted a child process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    table = process.default_process_table()
    current = next((record for record in table
                    if record.pid == os.getpid()), None)
    assert current is not None
    assert current.command_line
    assert current.executable
    assert current.create_time_utc

    source = inspect.getsource(process.default_process_table)
    native = inspect.getsource(process._windows_process_table)
    assert "subprocess" not in source + native
    assert "_PROCESS_QUERY = (" not in source + native
    assert "subprocess.run" not in source + native


@pytest.mark.skipif(os.name != "nt", reason="native Win32 process snapshot")
def test_watchdog_health_snapshot_does_not_create_a_console_child(
        tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("health observation attempted a child process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    watchdog = daemon.Watchdog(
        make_config(tmp_path), process_table_fn=process.default_process_table)
    snapshot = watchdog.status_snapshot()
    assert snapshot["watchdog_running"] is False
    assert snapshot["producer_running"] is False


def test_process_counting_and_cursor_epoch_observation_are_shell_free():
    table = [
        process.ProcessRecord(
            pid=10, parent_pid=1, name="python.exe",
            command_line=(
                "python.exe -m "
                "PHX2.free_tier_producer.free_tier_session --run")),
        process.ProcessRecord(
            pid=11, parent_pid=10, name="python.exe",
            command_line=(
                "python.exe -m "
                "PHX2.free_tier_producer.free_tier_session --run")),
    ]
    assert process.logical_producer_pids(table) == [10]
    assert process.producer_process_pids(table) == [10, 11]

    observed = (
        REPO_ROOT / "PHX2" / "watchdog" / "observe.py",
        REPO_ROOT / "PHX2" / "watchdog" / "health.py",
        REPO_ROOT / "PHX2" / "free_tier_producer" / "stream_cursor.py",
        REPO_ROOT / "PHX2" / "free_tier_producer" / "live_epoch.py",
    )
    forbidden = re.compile(
        r"subprocess|os\.system|powershell(?:\.exe)?|pwsh(?:\.exe)?|"
        r"cmd(?:\.exe)?|schtasks(?:\.exe)?|wmic(?:\.exe)?",
        re.IGNORECASE,
    )
    assert not [
        str(path) for path in observed
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]


def test_operator_task_poll_is_one_time_and_fully_hidden(monkeypatch,
                                                         tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = dict(kwargs)
        return subprocess.CompletedProcess(
            argv, 0,
            stdout=(
                "task_present=True\nmanaged_schema_ok=True\n"
                "watchdog_exe_exists=True\ntask_state=Ready\n"),
            stderr="",
        )

    monkeypatch.setattr(operator_cli.subprocess, "run", fake_run)
    backend = operator_cli.OperatorBackend(repo_root=tmp_path)
    status = backend.task_status()
    assert status["task_present"] is True
    command = captured["argv"]
    assert command[0].lower() == "powershell.exe"
    for argument in (
            "-NoLogo", "-NoProfile", "-NonInteractive",
            "-WindowStyle", "Hidden"):
        assert argument in command
    assert "-File" in command
    assert captured["kwargs"]["creationflags"] == (
        getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    _assert_hidden(captured["kwargs"]["startupinfo"])
    assert "shell" not in captured["kwargs"]


def test_all_python_startup_children_use_argv_and_never_shell_true_or_cmd():
    violations = []
    for path in STARTUP_PYTHON:
        for call in _subprocess_calls(path):
            for keyword in call.keywords:
                if keyword.arg == "shell" \
                        and isinstance(keyword.value, ast.Constant) \
                        and keyword.value.value is True:
                    violations.append(f"{path}:shell=True")
            if call.args and isinstance(call.args[0], (ast.List, ast.Tuple)):
                literals = [
                    item.value for item in call.args[0].elts
                    if isinstance(item, ast.Constant)
                    and isinstance(item.value, str)
                ]
                lowered = [item.lower() for item in literals]
                if "cmd.exe" in lowered or "/c" in lowered:
                    violations.append(f"{path}:cmd-wrapper")
    assert violations == []


def test_every_required_powershell_launch_is_hidden_and_no_detached_process():
    daemon_source = Path(daemon.__file__).read_text(encoding="utf-8")
    operator_source = Path(operator_cli.__file__).read_text(encoding="utf-8")
    for source in (daemon_source, operator_source):
        assert '"-NoLogo"' in source
        assert '"-NoProfile"' in source
        assert '"-NonInteractive"' in source
        assert '"-WindowStyle", "Hidden"' in source
    assert "creationflags=LAUNCHER_CREATION_FLAGS" in daemon_source
    assert "startupinfo=hidden_startupinfo()" in daemon_source
    assert "| subprocess.DETACHED_PROCESS" not in daemon_source


def test_hidden_startupinfo_is_fresh_and_requests_sw_hide():
    first = hidden_startupinfo()
    second = hidden_startupinfo()
    _assert_hidden(first)
    _assert_hidden(second)
    if os.name == "nt":
        assert first is not second


def test_task_action_is_direct_pythonw_hidden_single_instance_and_nonrecurring():
    text = TASK_TOOL.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#"))
    assert '.venv\\Scripts\\pythonw.exe"' in code
    assert '$ModuleArgs   = "-m PHX2.watchdog run"' in code
    assert "New-ScheduledTaskAction -Execute $WatchdogExe" in code
    assert "-WorkingDirectory $RepoRoot" in code
    assert "-MultipleInstances IgnoreNew" in code
    assert "-StartWhenAvailable -Hidden" in code
    assert "RestartCount = 0" in code
    assert "New-ScheduledTaskTrigger -AtLogOn" in code
    assert "RepetitionInterval" not in code
    assert "PT10S" not in code
    assert "cmd.exe" not in code.lower()
    assert "powershell.exe" not in code.lower()


def test_main_status_path_remains_read_only_and_main_is_a_thin_entrypoint():
    main_source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    operator_source = Path(operator_cli.__file__).read_text(encoding="utf-8")
    assert main_source.count("from PHX2.operator_cli import main") == 1
    status_branch = operator_source[
        operator_source.index('if command == "status":'):
        operator_source.index('if command == "stop":')
    ]
    assert "collect_status(active)" in status_branch
    assert "print_status" in status_branch
    assert ".write" not in status_branch
    assert "task_action(\"enable\")" not in status_branch
    assert "task_action(\"start\")" not in status_branch


def test_production_startup_command_sources_contain_no_secret_literal():
    token_pattern = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b")
    command_sources = (
        REPO_ROOT / "main.py",
        REPO_ROOT / "PHX2" / "operator_cli.py",
        REPO_ROOT / "PHX2" / "watchdog" / "daemon.py",
        REPO_ROOT / "PHX2" / "watchdog" / "process.py",
        REPO_ROOT / "PHX2" / "watchdog" / "windows_launch.py",
        TASK_TOOL,
    )
    for path in command_sources:
        text = path.read_text(encoding="utf-8")
        assert token_pattern.search(text) is None, str(path)
