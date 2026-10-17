from __future__ import annotations

from pathlib import Path

import pytest

import PHX2.operator_cli as cli


def _status(**changes):
    values = dict(
        state="RUNNING",
        health="HEALTHY",
        transport="TELEGRAM",
        discord="DISABLED",
        watchdog_pid=101,
        producer_pid=202,
        yellowstone_owners=1,
        epoch_id="epoch-abcdefghij",
        epoch_status="EPOCH_HEALTHY",
        epoch_start_slot=123,
        epoch_durable=True,
        epoch_identity_matches=True,
        dex_backfill="SUCCESS",
        circuit="CLOSED",
        circuit_reason=None,
        circuit_integrity_locked=False,
        heartbeat_age_seconds=1.0,
        last_telegram_ping=None,
        paid_ledger_lines=9,
        paid_ledger_sha256="a" * 64,
        watchdog_count=1,
        producer_count=1,
        task_state="Running",
        task_present=True,
        task_schema_ok=True,
    )
    values.update(changes)
    return cli.OperatorStatus(**values)


class FakeBackend:
    def __init__(self, *, task_state="Ready"):
        self.repo_root = Path(".")
        self.actions = []
        self.stop_requests = 0
        self.stop_clears = 0
        self.now = 0.0
        self.task_state = task_state
        self.locks_absent = True
        self.handoffs = []

    def task_action(self, action):
        self.actions.append(action)
        if action == "enable":
            self.task_state = "Ready"
        if action == "disable":
            self.task_state = "Disabled"
        return {"_ok": True, "task_state": self.task_state}

    def clear_watchdog_stop(self):
        self.stop_clears += 1

    def request_watchdog_stop(self):
        self.stop_requests += 1
        return True

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def runtime_locks_absent(self):
        return self.locks_absent

    def closed_epoch_deployment_handoff(self, *, record=False):
        self.handoffs.append(bool(record))
        return cli.ClosedEpochDeploymentHandoffVerdict(
            allowed=True,
            existing_record=(
                {"record_digest": "a" * 64} if record else {}),
        )


def _safe_verdict(backend):
    return cli.SafetyVerdict(
        safe=True,
        task={
            "task_state": backend.task_state,
            "task_present": True,
            "managed_schema_ok": True,
        },
        runtime={"circuit_status": "CLOSED"},
    )


def test_no_argument_defaults_to_start(monkeypatch):
    seen = []
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr(cli, "start", lambda backend: seen.append("start") or 0)
    assert cli.main([], backend=FakeBackend(), enforce_venv=False) == 0
    assert seen == ["start"]


@pytest.mark.parametrize("command", cli.COMMANDS)
def test_command_contract_dispatches(monkeypatch, command):
    seen = []
    monkeypatch.setattr(cli.os, "name", "nt")
    if command == "status":
        monkeypatch.setattr(cli, "collect_status", lambda backend: _status())
        monkeypatch.setattr(
            cli, "print_status", lambda status: seen.append("status"))
    else:
        monkeypatch.setattr(
            cli, command,
            lambda backend: seen.append(command) or 0)
    assert cli.main(
        [command], backend=FakeBackend(), enforce_venv=False) == 0
    assert command in seen


def test_invalid_arguments_fail_before_reexec():
    assert cli._safe_command(["start", "--unsafe"]) is None


def test_non_venv_reexecs_once_with_only_safe_arguments(
    tmp_path, monkeypatch,
):
    venv = tmp_path / "python.exe"
    venv.write_bytes(b"stub")
    monkeypatch.setattr(cli, "REPO_VENV_PYTHON", venv)
    monkeypatch.setattr(cli, "REPO_ROOT", str(tmp_path))
    monkeypatch.delenv(cli.REEXEC_MARKER, raising=False)
    monkeypatch.setenv("PHX2_TELEGRAM_BOT_TOKEN", "secret-value")
    captured = {}

    def fake_execve(executable, argv, environment):
        captured.update(
            executable=executable, argv=list(argv), environment=environment)
        raise RuntimeError("exec")

    with pytest.raises(RuntimeError, match="exec"):
        cli._ensure_repo_venv(
            ["status"], executable=str(tmp_path / "system.exe"),
            execve=fake_execve)
    assert captured["argv"] == [
        str(venv), str(tmp_path / "main.py"), "status"]
    assert "secret-value" not in " ".join(captured["argv"])
    assert captured["environment"][cli.REEXEC_MARKER] == "1"


def test_reexec_loop_fails_closed(tmp_path, monkeypatch, capsys):
    venv = tmp_path / "python.exe"
    venv.write_bytes(b"stub")
    monkeypatch.setattr(cli, "REPO_VENV_PYTHON", venv)
    monkeypatch.setenv(cli.REEXEC_MARKER, "1")
    assert cli._ensure_repo_venv(
        ["start"], executable=str(tmp_path / "system.exe")) == 2
    assert "re-exec failed" in capsys.readouterr().out


def test_missing_venv_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "REPO_VENV_PYTHON", tmp_path / "missing.exe")
    monkeypatch.delenv(cli.REEXEC_MARKER, raising=False)
    assert cli._ensure_repo_venv(
        [], executable=str(tmp_path / "system.exe")) == 2
    assert "virtual environment is unavailable" in capsys.readouterr().out


def test_already_running_is_idempotent(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(cli, "safety_check", lambda _: _safe_verdict(backend))
    monkeypatch.setattr(cli, "collect_status", lambda _: _status())
    assert cli.start(backend, timeout_seconds=0) == 0
    assert backend.actions == []
    assert backend.stop_clears == 0


def test_watchdog_process_count_collapses_windows_venv_shim_pair():
    command = (
        r'"C:\repo\.venv\Scripts\pythonw.exe" -m PHX2.watchdog run')
    table = [
        cli.ProcessRecord(
            pid=101, parent_pid=50, name="pythonw.exe",
            executable=r"C:\repo\.venv\Scripts\pythonw.exe",
            command_line=command,
        ),
        cli.ProcessRecord(
            pid=102, parent_pid=101, name="pythonw.exe",
            executable=r"C:\Program Files\Python312\pythonw.exe",
            command_line=command,
        ),
    ]
    assert cli._watchdog_process_pids(table) == [101]


def test_watchdog_process_count_preserves_distinct_logical_owners():
    command = (
        r'"C:\repo\.venv\Scripts\pythonw.exe" -m PHX2.watchdog run')
    table = [
        cli.ProcessRecord(
            pid=101, parent_pid=50, name="pythonw.exe",
            command_line=command,
        ),
        cli.ProcessRecord(
            pid=102, parent_pid=101, name="pythonw.exe",
            command_line=command,
        ),
        cli.ProcessRecord(
            pid=201, parent_pid=60, name="pythonw.exe",
            command_line=command,
        ),
        cli.ProcessRecord(
            pid=202, parent_pid=201, name="pythonw.exe",
            command_line=command,
        ),
    ]
    assert cli._watchdog_process_pids(table) == [101, 201]


def test_disabled_task_is_enabled_then_started(monkeypatch):
    backend = FakeBackend(task_state="Disabled")
    states = iter([
        _status(state="STOPPED", health="UNKNOWN", watchdog_pid=None,
                producer_pid=None, yellowstone_owners=None,
                watchdog_count=0, producer_count=0, task_state="Disabled"),
        _status(task_state="Running"),
    ])
    monkeypatch.setattr(cli, "safety_check", lambda _: _safe_verdict(backend))
    monkeypatch.setattr(cli, "collect_status", lambda _: next(states))
    assert cli.start(backend, timeout_seconds=5) == 0
    assert backend.actions == ["enable", "start"]
    assert backend.stop_clears == 1


@pytest.mark.parametrize("epoch_status", ["EPOCH_STARTING", "EPOCH_HEALTHY"])
def test_start_accepts_epoch_starting_and_healthy(monkeypatch, epoch_status):
    backend = FakeBackend()
    states = iter([
        _status(state="STOPPED", health="UNKNOWN", watchdog_pid=None,
                producer_pid=None, yellowstone_owners=None,
                watchdog_count=0, producer_count=0),
        _status(
            health="STARTING" if epoch_status == "EPOCH_STARTING"
            else "HEALTHY",
            epoch_status=epoch_status),
    ])
    monkeypatch.setattr(cli, "safety_check", lambda _: _safe_verdict(backend))
    monkeypatch.setattr(cli, "collect_status", lambda _: next(states))
    assert cli.start(backend, timeout_seconds=5) == 0
    assert backend.actions == ["start"]


def test_start_records_closed_epoch_handoff_before_managed_task(monkeypatch):
    backend = FakeBackend()
    states = iter([
        _status(state="STOPPED", health="UNKNOWN", watchdog_pid=None,
                producer_pid=None, yellowstone_owners=None,
                watchdog_count=0, producer_count=0),
        _status(),
    ])
    verdict = _safe_verdict(backend)
    verdict.handoff_required = True
    monkeypatch.setattr(cli, "safety_check", lambda _: verdict)
    monkeypatch.setattr(cli, "collect_status", lambda _: next(states))
    assert cli.start(backend, timeout_seconds=5) == 0
    assert backend.handoffs == [True]
    assert backend.actions == ["start"]


def test_second_start_is_idempotent_after_handoff(monkeypatch):
    backend = FakeBackend()
    states = iter([
        _status(state="STOPPED", health="UNKNOWN", watchdog_pid=None,
                producer_pid=None, yellowstone_owners=None,
                watchdog_count=0, producer_count=0),
        _status(),
        _status(),
    ])
    verdicts = iter([
        cli.SafetyVerdict(
            safe=True,
            task=_safe_verdict(backend).task,
            runtime={"circuit_status": "CLOSED"},
            handoff_required=True,
        ),
        _safe_verdict(backend),
    ])
    monkeypatch.setattr(cli, "safety_check", lambda _: next(verdicts))
    monkeypatch.setattr(cli, "collect_status", lambda _: next(states))
    assert cli.start(backend, timeout_seconds=5) == 0
    assert cli.start(backend, timeout_seconds=5) == 0
    assert backend.handoffs == [True]
    assert backend.actions == ["start"]


@pytest.mark.parametrize(
    "reason",
    [
        "CIRCUIT_OPEN",
        "AMBIGUOUS_PRODUCER_LOCK",
        "DUPLICATE_WATCHDOG",
        "DUPLICATE_PRODUCER",
        "DUPLICATE_YELLOWSTONE_OWNER",
        "TELEGRAM_CONFIG_INVALID",
        "DUAL_TRANSPORT_FORBIDDEN",
        "MANAGED_TASK_ABSENT",
        "MANAGED_TASK_SCHEMA_INVALID",
    ],
)
def test_start_safety_refusals_never_start(monkeypatch, reason):
    backend = FakeBackend()
    runtime = {
        "circuit_status": "OPEN",
        "circuit_open_reason": "EPOCH_DOCUMENT_INVALID",
        "circuit_integrity_locked": True,
    }
    monkeypatch.setattr(
        cli, "safety_check",
        lambda _: cli.SafetyVerdict(False, [reason], runtime=runtime))
    assert cli.start(backend, timeout_seconds=0) == 2
    assert backend.actions == []
    assert backend.stop_clears == 0


def test_stop_is_cooperative_and_disables_task(monkeypatch):
    backend = FakeBackend(task_state="Running")
    stopped = dict(
        state="STOPPED", health="STOPPED_BY_OPERATOR",
        watchdog_pid=None, producer_pid=None, yellowstone_owners=0,
        watchdog_count=0, producer_count=0, task_state="Ready")
    states = iter([
        _status(),
        _status(**stopped),
        # STOPPED CLEANLY prints only after a FINAL post-disable status
        # re-check agrees (2026-07-27 shutdown/status remediation).
        _status(**stopped),
    ])
    monkeypatch.setattr(cli, "collect_status", lambda _: next(states))
    assert cli.stop(backend, timeout_seconds=5) == 0
    assert backend.stop_requests == 1
    assert backend.actions == ["disable"]


def test_stop_never_force_kills_on_timeout(monkeypatch, capsys):
    backend = FakeBackend()
    monkeypatch.setattr(cli, "collect_status", lambda _: _status())
    assert cli.stop(backend, timeout_seconds=0) == 2
    assert "no force termination was attempted" in capsys.readouterr().out
    assert backend.actions == []


def test_restart_stops_before_start_and_requires_new_epoch(monkeypatch):
    backend = FakeBackend()
    calls = []
    statuses = iter([
        _status(epoch_id="epoch-old"),
        _status(epoch_id="epoch-new"),
    ])
    monkeypatch.setattr(cli, "collect_status", lambda _: next(statuses))
    monkeypatch.setattr(
        cli, "stop", lambda backend, timeout_seconds: calls.append("stop") or 0)
    monkeypatch.setattr(
        cli, "start", lambda backend, timeout_seconds: calls.append("start") or 0)
    assert cli.restart(backend) == 0
    assert calls == ["stop", "start"]


def test_restart_refuses_same_epoch(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(cli, "collect_status", lambda _: _status(
        epoch_id="same"))
    monkeypatch.setattr(cli, "stop", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cli, "start", lambda *args, **kwargs: 0)
    assert cli.restart(backend) == 2


def test_status_output_is_concise_and_redacted(capsys):
    cli.print_status(_status(
        primary_migration_source="HELIUS",
        primary_source_state="CONNECTED",
        primary_continuity="NO_GAP",
        primary_recovery="COMPLETE",
        primary_last_slot=435_500_123,
        primary_estimated_credits=12.5,
        shadow_source="CHAINSTACK",
        shadow_state="CONNECTED",
        chainstack_configured_for_runtime=True,
        chainstack_connected=True,
        chainstack_comparator=True,
        parity_matches=3,
        dex_backfill="DIAGNOSTIC_ONLY: SUCCESS",
        post_boundary_candidates_admitted=7,
        pre_boundary_candidates_ignored=11,
        restored_diagnostic_records=5,
        dex_diagnostic_records=6,
        historical_candidates_eligible=0,
    ))
    output = capsys.readouterr().out
    assert "PHX2 STATUS" in output
    assert "Transport: TELEGRAM" in output
    assert "Discord: DISABLED" in output
    assert "api.telegram.org" not in output
    assert "chat_id" not in output.lower()
    assert "outbound" not in output.lower()
    assert "a" * 64 not in output
    assert "Primary migration source: HELIUS" in output
    assert "Primary continuity: NO_GAP" in output
    assert "Shadow source: CHAINSTACK" in output
    assert "Chainstack configured for runtime: true" in output
    assert "Chainstack connected: true" in output
    assert "Chainstack comparator: true" in output
    assert "Parity matches: 3" in output
    assert "Dex backfill: DIAGNOSTIC_ONLY: SUCCESS" in output
    assert "Post-boundary candidates admitted: 7" in output
    assert "Pre-boundary candidates ignored: 11" in output
    assert "Restored diagnostic records: 5" in output
    assert "DEX diagnostic records: 6" in output
    assert "Historical candidates eligible: 0" in output


def test_operator_source_never_constructs_runtime_owners():
    source = Path(cli.__file__).read_text(encoding="utf-8")
    forbidden = (
        "TelegramTransport(",
        "TelegramDeliveryAdapter(",
        "DiscordTransport(",
        "SingleGrpcPumpSwapDiscovery(",
        "free_tier_session.main(",
        "production_supervisor",
        "remove_stale_producer_lock(",
    )
    assert not [token for token in forbidden if token in source]


def test_operator_source_has_no_direct_state_or_ledger_writes():
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert "open(CANONICAL_LEDGER_PATH" not in source
    assert "live_epoch_primary_path.write" not in source
    assert "cursor_primary_path.write" not in source
    assert "recovery_primary_path.write" not in source
    assert "clear_circuit(" not in source


def test_root_main_is_thin_operator_entrypoint():
    root = Path(cli.REPO_ROOT) / "main.py"
    source = root.read_text(encoding="utf-8")
    assert "from PHX2.operator_cli import main" in source
    assert "production_entrypoint" not in source


def test_non_windows_behavior_is_explicit(monkeypatch, capsys):
    monkeypatch.setattr(cli.os, "name", "posix")
    assert cli.main([], backend=FakeBackend(), enforce_venv=False) == 2
    assert "requires Windows" in capsys.readouterr().out
