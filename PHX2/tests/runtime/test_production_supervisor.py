from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from PHX2.runtime import production_supervisor as ps


class FakeScanner:
    def __init__(self, records):
        self.records = list(records)
        self.calls = 0

    def scan(self, run_dir=None, *, owner_pid=None):
        self.calls += 1
        return list(self.records)


def self_record(pid=None):
    return ps.ProcessRecord(
        pid=pid or ps.os.getpid(),
        parent_pid=1,
        name="python.exe",
        role="SELF",
        start_utc="2026-07-16T06:00:00.0000000Z",
    )


def make_config(tmp_path, monkeypatch, *, hours=24.0):
    repo = tmp_path / "repo"
    (repo / "PHX2").mkdir(parents=True)
    python = repo / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    env_file = tmp_path / "phx2.env"
    env_file.write_text(
        "\n".join(
            (
                "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT=https://safe.invalid",
                "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN=token",
                "PHX2_STAGE28_11_ALLOW_LIVE_GRPC=true",
                "PHX2_STAGE29_2_BIRDEYE_API_KEY=key",
                "PHX2_STAGE29_2_ALLOW_LIVE_HTTP=1",
                "PHX2_DELIVERY_TRANSPORT=telegram",
                "PHX2_TELEGRAM_ENABLED=true",
                "PHX2_TELEGRAM_BOT_TOKEN=123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd",
                "PHX2_TELEGRAM_CHAT_ID=-1001234567890",
                "PHX2_TELEGRAM_PARSE_MODE=HTML",
                "PHX2_TELEGRAM_DISABLE_LINK_PREVIEW=true",
                "PHX2_DISCORD_ENABLED=false",
            )
        ),
        encoding="utf-8",
    )
    active = tmp_path / "active.jsonl"
    frozen = tmp_path / "frozen.jsonl"
    active.write_text("active\n", encoding="utf-8")
    frozen.write_text("frozen\n", encoding="utf-8")
    paper = tmp_path / "paper.json"
    paper.write_text("{}\n", encoding="utf-8")
    paths = ps.ProductionPaths(
        repo_root=repo,
        runtime_root=tmp_path,
        lock_path=tmp_path / "session.lock",
        env_file=env_file,
        active_ledger=active,
        frozen_ledger=frozen,
        paper_config=paper,
    )
    monkeypatch.setattr(ps, "EXPECTED_FROZEN_LEDGER", ps.ledger_baseline(frozen).as_tuple())
    return ps.ProductionConfig(run_dir=(tmp_path / "run").resolve(), hours=hours, paths=paths)


def test_process_enumeration_timeout_fails_closed():
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("powershell", 1)

    scanner = ps.ProcessScanner(runner=timeout, timeout_seconds=0.01)
    with pytest.raises(ps.ProcessEnumerationError):
        scanner.scan()


def test_process_enumeration_invalid_json_fails_closed():
    def invalid(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="not-json", stderr="")

    with pytest.raises(ps.ProcessEnumerationError):
        ps.ProcessScanner(runner=invalid).scan()


def test_self_process_is_not_classified_as_old_phoenix(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    result = ps.bounded_preflight(
        config, scanner=FakeScanner([self_record()]), offline_preflight=lambda _: True
    )
    assert result.active_ledger.line_count == 1


def test_old_phoenix_process_refusal(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    old = ps.ProcessRecord(99, 1, "python.exe", "OLD_PHOENIX", "start")
    with pytest.raises(ps.ProductionRefusal, match="OLD_PHOENIX_ACTIVE"):
        ps.bounded_preflight(
            config,
            scanner=FakeScanner([self_record(), old]),
            offline_preflight=lambda _: True,
        )


@pytest.mark.parametrize("role", ("SUPERVISOR", "PRODUCER", "PAPER", "DASHBOARD"))
def test_duplicate_phx2_process_refusal(tmp_path, monkeypatch, role):
    config = make_config(tmp_path, monkeypatch)
    other = ps.ProcessRecord(99, 1, "python.exe", role, "start")
    with pytest.raises(ps.ProductionRefusal, match="PHX2_RUNTIME_PROCESS_ACTIVE"):
        ps.bounded_preflight(
            config,
            scanner=FakeScanner([self_record(), other]),
            offline_preflight=lambda _: True,
        )


def test_incomplete_environment_refuses(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    config.paths.env_file.write_text("PHX2_STAGE28_11_ALLOW_LIVE_GRPC=true\n", encoding="utf-8")
    with pytest.raises(ps.ProductionRefusal, match="PRODUCTION_CONFIGURATION_INCOMPLETE"):
        ps.bounded_preflight(
            config, scanner=FakeScanner([self_record()]), offline_preflight=lambda _: True
        )


def test_offline_preflight_refusal_has_no_fallback(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    with pytest.raises(ps.ProductionRefusal, match="PRODUCTION_OFFLINE_PREFLIGHT_FAILED"):
        ps.bounded_preflight(
            config, scanner=FakeScanner([self_record()]), offline_preflight=lambda _: False
        )


def test_active_lock_is_protected(tmp_path):
    lock_path = tmp_path / "lock"
    record = self_record(pid=123)
    lock_path.write_text(
        json.dumps(
            {
                "supervisor_pid": 123,
                "supervisor_start_utc": record.start_utc,
                "owner_nonce": "owner",
            }
        ),
        encoding="utf-8",
    )
    lock = ps.SessionLock(lock_path)
    assert lock.inspect([record])[0] == "ACTIVE"
    with pytest.raises(ps.ProductionRefusal, match="PHX2_SESSION_ALREADY_ACTIVE"):
        lock.acquire(run_dir=tmp_path / "run", records=[record])
    assert lock_path.exists()


def test_stale_lock_is_cleaned_only_during_acquire(tmp_path):
    lock_path = tmp_path / "lock"
    lock_path.write_text('{"supervisor_pid": 9, "supervisor_start_utc": "old"}', encoding="utf-8")
    lock = ps.SessionLock(lock_path)
    record = self_record()
    assert lock.inspect([record])[0] == "STALE"
    payload = lock.acquire(run_dir=tmp_path / "run", records=[record])
    assert payload["supervisor_pid"] == ps.os.getpid()
    lock.release()
    assert not lock_path.exists()


def test_reused_pid_does_not_make_stale_lock_active(tmp_path):
    lock_path = tmp_path / "lock"
    lock_path.write_text(
        json.dumps({"supervisor_pid": 123, "supervisor_start_utc": "old"}),
        encoding="utf-8",
    )
    current = ps.ProcessRecord(123, 1, "python.exe", "SUPERVISOR", "new")
    assert ps.SessionLock(lock_path).inspect([current])[0] == "STALE"


def test_bounded_preflight_refuses_matching_root_main_lock_owner(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    config.paths.lock_path.write_text(
        json.dumps({"supervisor_pid": 123, "supervisor_start_utc": "same"}),
        encoding="utf-8",
    )
    candidate = ps.ProcessRecord(123, 1, "python.exe", "LOCK_OWNER_CANDIDATE", "same")
    with pytest.raises(ps.ProductionRefusal, match="PHX2_SESSION_ALREADY_ACTIVE"):
        ps.bounded_preflight(
            config,
            scanner=FakeScanner([self_record(), candidate]),
            offline_preflight=lambda _: True,
        )


def test_bounded_preflight_ignores_reused_lock_pid_with_new_start(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    config.paths.lock_path.write_text(
        json.dumps({"supervisor_pid": 123, "supervisor_start_utc": "old"}),
        encoding="utf-8",
    )
    reused = ps.ProcessRecord(123, 1, "python.exe", "LOCK_OWNER_CANDIDATE", "new")
    result = ps.bounded_preflight(
        config,
        scanner=FakeScanner([self_record(), reused]),
        offline_preflight=lambda _: True,
    )
    assert result.active_ledger.line_count == 1


def test_child_commands_launch_full_pipeline_without_disarmed_mode(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    commands = ps.build_child_commands(config)
    assert set(commands) == {"producer", "paper", "dashboard"}
    assert "PHX2.runtime.production_supervisor" in commands["producer"]
    assert "PHX2.scripts.phx2_live_paper_trade" in commands["paper"]
    assert "PHX2.dashboard.server" in commands["dashboard"]
    joined = " ".join(sum(commands.values(), []))
    assert "paid_with_fallback" not in joined
    assert "no-send" not in joined
    assert "dry-run" not in joined
    assert str(config.stop_file) in joined
    assert "127.0.0.1" in commands["dashboard"]


def test_producer_child_refuses_to_arm_even_with_valid_config(tmp_path, monkeypatch, capsys):
    """M-2: the supervisor producer child is a non-arming route. Even with a
    fully valid production config and a matching baseline it refuses (exit 2),
    never calls the armed session entry, and names the canonical launchers."""
    config = make_config(tmp_path, monkeypatch)
    config.control_dir.mkdir(parents=True)
    ps.atomic_json(
        config.control_dir / "production_config.json",
        {
            "provider_mode": "PAID_PRIMARY",
            "market_provider": "BIRDEYE_PRIMARY",
            "delivery_transport": "TELEGRAM",
            "telegram_enabled": True,
            "discord_enabled": False,
            "private_discord_enabled": False,
            "polling_fallback_enabled": False,
                "primary_max_grpc_streams": 1,
                "verifier_max_grpc_streams": 0,
                "max_grpc_streams": 1,
                "lp_integrity_mode": "DISABLED_SINGLE_STREAM",
                "migration_activation_multiplier": "1.20",
            "active_ledger_baseline": ps.ledger_baseline(config.paths.active_ledger).as_token(),
        },
    )
    from PHX2.free_tier_producer import free_tier_session

    def _boom(argv):
        raise AssertionError("the supervisor route must never arm a send")

    monkeypatch.setattr(free_tier_session, "main", _boom)
    assert ps.run_producer_child(config) == 2
    out = capsys.readouterr().out
    assert ps.ARMED_ROUTE_REFUSAL in out
    assert any(name in out for name in ps.CANONICAL_ARMED_LAUNCHERS)


def test_producer_child_refuses_before_reading_any_config(tmp_path, monkeypatch):
    """The refusal precedes construction: it holds even with no runtime config
    written and no session module reachable to arm."""
    config = make_config(tmp_path, monkeypatch)
    config.control_dir.mkdir(parents=True)
    from PHX2.free_tier_producer import free_tier_session

    monkeypatch.setattr(
        free_tier_session, "main",
        lambda argv: (_ for _ in ()).throw(AssertionError("armed send reached")))
    assert ps.run_producer_child(config) == 2


class FakeConsole:
    def __init__(self, run_dir):
        self.started = False
        self.stopped = False

    def start_background(self):
        self.started = True

    def stop_background(self):
        self.stopped = True


class FakeProcess:
    next_pid = 5000

    def __init__(self, *, force=False):
        FakeProcess.next_pid += 1
        self.pid = FakeProcess.next_pid
        self.code = None
        self.force = force
        self.signals = []

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        if self.force and self.code is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        self.code = 0 if self.code is None else self.code
        return self.code

    def send_signal(self, value):
        self.signals.append(value)

    def terminate(self):
        self.code = -15

    def kill(self):
        self.code = -9


def child_role(command):
    joined = " ".join(str(part) for part in command)
    if "--child-role producer" in joined:
        return "producer"
    if "phx2_live_paper_trade" in joined:
        return "paper"
    if "PHX2.dashboard.server" in joined:
        return "dashboard"
    raise AssertionError(f"unexpected child command: {joined}")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


def run_interrupt_supervisor(tmp_path, monkeypatch, *, force=False):
    config = make_config(tmp_path, monkeypatch)
    scanner = FakeScanner([self_record()])
    processes = []

    def popen(*args, **kwargs):
        proc = FakeProcess(force=force)
        processes.append(proc)
        return proc

    sleeps = {"count": 0}

    def interrupt_after_launch(seconds):
        sleeps["count"] += 1
        if sleeps["count"] >= 4:
            raise KeyboardInterrupt

    supervisor = ps.ProductionSupervisor(
        config,
        scanner=scanner,
        offline_preflight=lambda _: True,
        popen_factory=popen,
        console_factory=FakeConsole,
        sleep=interrupt_after_launch,
    )
    return supervisor, supervisor.run(), processes


def test_ctrl_c_cooperative_shutdown_writes_final_summary(tmp_path, monkeypatch):
    supervisor, result, processes = run_interrupt_supervisor(tmp_path, monkeypatch)
    assert result.stop_reason == "OPERATOR_REQUESTED"
    assert result.exit_code == 0
    assert result.forced_termination_count == 0
    assert all(proc.poll() == 0 for proc in processes)
    final = ps.read_json(supervisor.config.control_dir / "supervisor_final.json")
    assert final["active_streams"] == 0
    assert final["forced_termination_count"] == 0
    assert not supervisor.config.paths.lock_path.exists()


def test_forced_termination_is_reported_after_cooperative_timeout(tmp_path, monkeypatch):
    supervisor, result, processes = run_interrupt_supervisor(tmp_path, monkeypatch, force=True)
    assert result.exit_code == 2
    assert result.forced_termination_count == 3
    assert all(proc.poll() == -15 for proc in processes)
    final = ps.read_json(supervisor.config.control_dir / "supervisor_final.json")
    assert sorted(final["forced_termination_processes"]) == ["dashboard", "paper", "producer"]


def test_paper_child_exit_restarts_without_stopping_critical_pipeline(
    tmp_path, monkeypatch
):
    config = make_config(tmp_path, monkeypatch)
    active_before = ps.ledger_baseline(config.paths.active_ledger)
    frozen_before = ps.ledger_baseline(config.paths.frozen_ledger)
    clock = FakeClock()
    by_role = {"producer": [], "paper": [], "dashboard": []}
    maximum_paper_children = 0
    holder = {}
    evidence = {}

    def popen(command, **kwargs):
        nonlocal maximum_paper_children
        role = child_role(command)
        if role == "paper":
            assert sum(proc.poll() is None for proc in by_role[role]) == 0
        process = FakeProcess()
        if role == "paper" and not by_role[role]:
            process.code = 5
        by_role[role].append(process)
        maximum_paper_children = max(
            maximum_paper_children,
            sum(proc.poll() is None for proc in by_role["paper"]),
        )
        return process

    def sleep(seconds):
        clock.advance(seconds)
        if len(by_role["paper"]) < 2 or float(seconds) != 1.0:
            return
        supervisor = holder["supervisor"]
        producer = by_role["producer"][0]
        paper = by_role["paper"][-1]
        dashboard = by_role["dashboard"][0]
        ps.atomic_json(
            config.producer_dir / "producer_heartbeat.json",
            {
                "provider_telemetry": {
                    "status": "CONNECTED",
                    "total_active_streams": 1,
                    "total_max_active_streams": 1,
                    "primary_stream_status": "CONNECTED",
                    "verifier_stream_status": "DISABLED",
                    "lp_integrity_mode": "DISABLED_SINGLE_STREAM",
                    "primary": {"status": "CONNECTED"},
                    "verifier": {"status": "DISABLED"},
                },
                "credit_budget": {"send_attempts": 0, "sent_ok_count": 0},
            },
        )
        records = [
            self_record(),
            ps.ProcessRecord(
                producer.pid, ps.os.getpid(), "python.exe", "PRODUCER", "p",
                str(config.run_dir),
            ),
            ps.ProcessRecord(
                paper.pid, ps.os.getpid(), "python.exe", "PAPER", "p",
                str(config.run_dir),
            ),
            ps.ProcessRecord(
                dashboard.pid, ps.os.getpid(), "python.exe", "DASHBOARD", "p",
                str(config.run_dir),
            ),
        ]
        status = ps.read_status(
            config.paths,
            run_dir=config.run_dir,
            scanner=FakeScanner(records),
        )
        evidence.update(
            producer_running=producer.poll() is None,
            paper_running=paper.poll() is None,
            dashboard_running=dashboard.poll() is None,
            status=status,
            paper_status=supervisor.paper_status,
        )
        raise KeyboardInterrupt

    supervisor = ps.ProductionSupervisor(
        config,
        scanner=FakeScanner([self_record()]),
        offline_preflight=lambda _: True,
        popen_factory=popen,
        console_factory=FakeConsole,
        sleep=sleep,
        monotonic=clock.monotonic,
    )
    holder["supervisor"] = supervisor
    result = supervisor.run()

    assert result.stop_reason == "OPERATOR_REQUESTED"
    assert result.exit_code == 0
    assert evidence["producer_running"] is True
    assert evidence["paper_running"] is True
    assert evidence["dashboard_running"] is True
    assert evidence["paper_status"] == "RUNNING"
    assert evidence["status"]["primary_stream_status"] == "CONNECTED"
    assert evidence["status"]["grpc_status"] == "CONNECTED"
    assert evidence["status"]["verifier_stream_status"] == "DISABLED"
    assert evidence["status"]["lp_integrity_mode"] == "DISABLED_SINGLE_STREAM"
    assert evidence["status"]["total_active_streams"] == 1
    assert evidence["status"]["max_active_streams"] == 1
    assert evidence["status"]["verifier_active_streams"] == 0
    assert evidence["status"]["telegram_configured"] is True
    assert evidence["status"]["telegram_attempts"] == 0
    assert evidence["status"]["discord_attempts"] == 0
    assert evidence["status"]["paper_status"] == "RUNNING"
    assert evidence["status"]["paper_restart_attempts"] == 1
    assert maximum_paper_children == 1
    assert len(by_role["paper"]) == 2
    assert all(proc.poll() is not None for values in by_role.values() for proc in values)
    assert ps.ledger_baseline(config.paths.active_ledger) == active_before
    assert ps.ledger_baseline(config.paths.frozen_ledger) == frozen_before
    assert not list(config.run_dir.rglob("telegram_attempts.jsonl"))
    assert not list(config.run_dir.rglob("*discord*attempt*"))
    events = ps.read_jsonl(supervisor.event_path)
    assert any(row["event"] == "PAPER_CHILD_FAILED" for row in events)
    assert any(row["event"] == "PAPER_CHILD_RECONCILED" for row in events)
    assert any(row["event"] == "PAPER_CHILD_RESTARTED" for row in events)
    final = ps.read_json(config.control_dir / "supervisor_final.json")
    assert final["paper_restart_attempts"] == 1
    assert final["paper_status"] == "STOPPED"


def test_repeated_paper_restart_failures_degrade_without_stopping_producer(
    tmp_path, monkeypatch
):
    config = make_config(tmp_path, monkeypatch)
    active_before = ps.ledger_baseline(config.paths.active_ledger)
    frozen_before = ps.ledger_baseline(config.paths.frozen_ledger)
    clock = FakeClock()
    by_role = {"producer": [], "paper": [], "dashboard": []}
    holder = {}
    producer_running_when_degraded = []

    def popen(command, **kwargs):
        role = child_role(command)
        if role == "paper":
            assert sum(proc.poll() is None for proc in by_role[role]) == 0
        process = FakeProcess()
        if role == "paper":
            process.code = 5
        by_role[role].append(process)
        return process

    def sleep(seconds):
        clock.advance(seconds)
        supervisor = holder.get("supervisor")
        if (
            supervisor is not None
            and supervisor.paper_status == "DEGRADED"
            and float(seconds) == 1.0
        ):
            producer_running_when_degraded.append(
                by_role["producer"][0].poll() is None
            )
            raise KeyboardInterrupt

    supervisor = ps.ProductionSupervisor(
        config,
        scanner=FakeScanner([self_record()]),
        offline_preflight=lambda _: True,
        popen_factory=popen,
        console_factory=FakeConsole,
        sleep=sleep,
        monotonic=clock.monotonic,
    )
    holder["supervisor"] = supervisor
    result = supervisor.run()

    assert result.exit_code == 0
    assert result.stop_reason == "OPERATOR_REQUESTED"
    assert producer_running_when_degraded == [True]
    assert len(by_role["paper"]) == 1 + ps.PAPER_RESTART_MAX_ATTEMPTS
    assert ps.ledger_baseline(config.paths.active_ledger) == active_before
    assert ps.ledger_baseline(config.paths.frozen_ledger) == frozen_before
    events = ps.read_jsonl(supervisor.event_path)
    assert sum(row["event"] == "PAPER_CHILD_FAILED" for row in events) == 4
    assert sum(row["event"] == "PAPER_DEGRADED" for row in events) == 1
    final = ps.read_json(config.control_dir / "supervisor_final.json")
    assert final["paper_status"] == "DEGRADED"
    assert final["paper_restart_attempts"] == ps.PAPER_RESTART_MAX_ATTEMPTS
    assert final["safety_violation"] is None


def test_producer_failure_remains_fatal_after_paper_isolation(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    clock = FakeClock()
    by_role = {"producer": [], "paper": [], "dashboard": []}
    failed = []

    def popen(command, **kwargs):
        role = child_role(command)
        process = FakeProcess()
        by_role[role].append(process)
        return process

    def sleep(seconds):
        clock.advance(seconds)
        if float(seconds) == 1.0 and not failed:
            by_role["producer"][0].code = 7
            failed.append(True)

    supervisor = ps.ProductionSupervisor(
        config,
        scanner=FakeScanner([self_record()]),
        offline_preflight=lambda _: True,
        popen_factory=popen,
        console_factory=FakeConsole,
        sleep=sleep,
        monotonic=clock.monotonic,
    )
    result = supervisor.run()

    assert result.exit_code == 2
    final = ps.read_json(config.control_dir / "supervisor_final.json")
    assert final["safety_violation"] == "PRODUCER_PROCESS_FAILURE"
    assert all(proc.poll() is not None for values in by_role.values() for proc in values)


def test_status_reads_process_and_telemetry_without_writes(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    config.control_dir.mkdir(parents=True)
    config.producer_dir.mkdir(parents=True)
    lock = {
        "supervisor_pid": 123,
        "supervisor_start_utc": "same",
        "run_dir": str(config.run_dir),
    }
    config.paths.lock_path.write_text(json.dumps(lock), encoding="utf-8")
    ps.atomic_json(
        config.control_dir / "processes.json",
        {"processes": {"producer": {"pid": 201}, "paper": {"pid": 202}, "dashboard": {"pid": 203}}},
    )
    ps.atomic_json(
        config.control_dir / "production_config.json",
        {
            "delivery_transport": "TELEGRAM",
            "telegram_enabled": True,
            "telegram_token_configured": True,
            "telegram_chat_configured": True,
            "discord_enabled": False,
        },
    )
    ps.atomic_json(
        config.producer_dir / "producer_heartbeat.json",
        {
            "provider_telemetry": {
                "status": "CONNECTED", "active_streams": 1, "max_active_streams": 1,
                "total_active_streams": 1, "total_max_active_streams": 1,
                "primary_stream_status": "CONNECTED",
                "verifier_stream_status": "DISABLED",
                "lp_integrity_mode": "DISABLED_SINGLE_STREAM",
                "candidates_accepted": 2, "queue_depth": 1,
                "primary": {"status": "CONNECTED"},
                "verifier": {"status": "DISABLED"},
                "pipeline_counters": {
                    "baselines_captured": 1, "candidates_activated": 1,
                    "liquidity_floor_pass": 1, "liquidity_floor_fail": 1,
                },
                "migration_admission": {
                    "migration_v1_admitted": 0, "migration_v2_admitted": 1,
                },
                "security_filters": {
                    "fee_scam_likely": 1, "fee_suspicious": 2, "fee_pass": 3,
                    "lp_pass": 0, "lp_warn": 0, "lp_fail": 0, "lp_disabled": 6,
                    "blocked_composite": 0,
                },
            },
            "watchlist_active": 1,
            "market_calls_total": 4,
            "market_scheduler": {
                "queue": 7, "in_flight": 2,
                "oldest_deadline_age_seconds": 3.5,
                "slo_breached": False, "price_batches": 0,
                "overview_calls": 11, "requests_avoided_by_grpc": 19,
                "late_results_rejected": 1,
            },
            "credit_budget": {"send_attempts": 1, "sent_ok_count": 1},
        },
    )
    ps.append_jsonl(
        config.producer_dir / "telegram_attempts.jsonl",
        {"result": "SENT_OK", "message_id": 100},
    )
    ps.append_jsonl(
        config.producer_dir / "telegram_attempts.jsonl",
        {"result": "RATE_LIMITED", "message_id": None},
    )
    records = [
        ps.ProcessRecord(123, 1, "python.exe", "SUPERVISOR", "same"),
        ps.ProcessRecord(201, 123, "python.exe", "PRODUCER", "p"),
        ps.ProcessRecord(202, 123, "python.exe", "PAPER", "p"),
        ps.ProcessRecord(203, 123, "python.exe", "DASHBOARD", "p"),
    ]
    before = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in config.run_dir.rglob("*") if path.is_file()
    }
    status = ps.read_status(config.paths, scanner=FakeScanner(records))
    after = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in config.run_dir.rglob("*") if path.is_file()
    }
    assert status["active"] is True
    assert status["grpc_status"] == "CONNECTED"
    assert status["queue_depth"] == 1
    assert status["sent_ok_count"] == 1
    assert status["delivery_transport"] == "TELEGRAM"
    assert status["telegram_configured"] is True
    assert status["telegram_attempts"] == 2
    assert status["telegram_sent_ok"] == 1
    assert status["telegram_failures"] == 1
    assert status["discord_attempts"] == 0
    assert status["paper_status"] == "RUNNING"
    assert status["paper_restart_attempts"] == 0
    assert status["paper_restart_limit"] == ps.PAPER_RESTART_MAX_ATTEMPTS
    assert status["primary_stream_status"] == "CONNECTED"
    assert status["verifier_stream_status"] == "DISABLED"
    assert status["lp_integrity_mode"] == "DISABLED_SINGLE_STREAM"
    assert status["total_active_streams"] == 1
    assert status["verifier_active_streams"] == 0
    assert status["fee_gate_counts"]["scam_likely"] == 1
    assert status["lp_integrity_counts"]["fail"] == 0
    assert status["composite_blocks"] == 0
    assert status["pipeline_counters"]["liquidity_floor_pass"] == 1
    assert status["migration_admission_counts"]["migration_v2_admitted"] == 1
    assert status["market_scheduler"]["queue"] == 7
    assert status["market_scheduler"]["requests_avoided_by_grpc"] == 19
    assert before == after


def test_status_finds_latest_managed_final_run_without_mutation(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    config = ps.ProductionConfig(
        run_dir=tmp_path / "phx2_live_test",
        hours=config.hours,
        paths=config.paths,
    )
    config.control_dir.mkdir(parents=True)
    ps.atomic_json(
        config.control_dir / "processes.json",
        {
            "schema_version": 1,
            "processes": {},
            "operator_console": {"pid": 999, "state": "RUNNING"},
        },
    )
    ps.atomic_json(
        config.control_dir / "supervisor_final.json",
        {"stop_reason": "MAX_RUNTIME", "active_streams": 0, "max_active_streams": 1},
    )
    status = ps.read_status(config.paths, scanner=FakeScanner([self_record()]))
    assert status["active"] is False
    assert status["run_dir"] == str(config.run_dir)
    assert status["stop_reason"] == "MAX_RUNTIME"
    assert status["operator_console"]["state"] == "EXITED"


def test_frozen_ledger_change_fails_final_verification(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    supervisor = ps.ProductionSupervisor(config, scanner=FakeScanner([self_record()]))
    before = ps.PreflightState(
        processes=[self_record()],
        active_ledger=ps.ledger_baseline(config.paths.active_ledger),
        frozen_ledger=ps.ledger_baseline(config.paths.frozen_ledger),
    )
    config.paths.frozen_ledger.write_text("changed\n", encoding="utf-8")
    assert supervisor._verify_final_safety(before)[3] == "FROZEN_LEDGER_CHANGED"


def test_secret_values_never_enter_child_command_lines(tmp_path, monkeypatch):
    config = make_config(tmp_path, monkeypatch)
    secret_names = {
        "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
        "PHX2_STAGE29_2_BIRDEYE_API_KEY",
        "PHX2_TELEGRAM_BOT_TOKEN",
        "PHX2_TELEGRAM_CHAT_ID",
    }
    secret_values = {
        value
        for line in config.paths.env_file.read_text(encoding="utf-8").splitlines()
        for name, separator, value in (line.partition("="),)
        if separator and name in secret_names
    }
    joined = " ".join(sum(ps.build_child_commands(config).values(), []))
    assert all(value not in joined for value in secret_values)
