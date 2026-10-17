"""Fake-producer harness for the offline watchdog fault-injection tests.

Nothing here connects Yellowstone, connects RPC, sends Telegram, constructs
Discord, touches a real ledger or touches real cursor/recovery state.  Every path
is under pytest's ``tmp_path``; every process is a fabricated
:class:`~PHX2.watchdog.process.ProcessRecord`; the clock, the sleep, the spawn and
the terminate call are all fakes owned by :class:`FakeWorld`.

The one thing that is REAL is process liveness: ``pid_alive`` is exercised against
this test process (alive) and against a pid proven dead by probing.  That keeps
the single most safety-critical primitive honest.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_ALERT_POLICY_CLI,
)
from PHX2.watchdog.config import WatchdogConfig
from PHX2.watchdog.daemon import ChildHandle
from PHX2.watchdog.process import ProcessRecord, pid_alive, read_producer_lock

HEAD_SHA = "beea7c15e11b1a4456472acf790193df242f763f"

#: The harness models the CANONICAL deployment, so it states the same alert
#: policy an armed launcher must state.  Kept as one name so a future canonical
#: change moves the harness with it instead of silently diverging.
HARNESS_ALERT_POLICY_CLI = CANONICAL_ALERT_POLICY_CLI
OTHER_SHA = "eef9ce236176b821e06b511339ef5c3dd2ff86b4"
LEDGER_LINE = ('{"mint":"FAKEmint1111111111111111111111111111111111",'
               '"sent_at_utc":"2026-07-01T00:00:00Z"}')


def find_dead_pid() -> int:
    """A pid this machine proves is not running."""

    for candidate in range(999_999, 900_000, -4):
        if not pid_alive(candidate):
            return candidate
    raise AssertionError("no dead pid could be proven")


def canonical_producer_command(config: WatchdogConfig, *, run_dir: str,
                               stop_file: str,
                               expected_head: str = HEAD_SHA,
                               telegram: int = 1, discord: int = 0,
                               policy: str = "shadow",
                               alert_policy: Optional[str] = (
                                   HARNESS_ALERT_POLICY_CLI),
                               ledger_path: Optional[str] = None,
                               cursor_dir: Optional[str] = None) -> str:
    """The exact command line the canonical launcher produces.

    Parameterised so a test can make ONE field wrong and prove adoption refuses
    for that reason alone.
    """

    parts: List[str] = [
        f'"{config.repo_python}"', "-u", "-m",
        "PHX2.free_tier_producer.free_tier_session", "--run",
    ]
    parts.extend(["--enable-telegram"] * int(telegram))
    parts.extend(["--enable-private-discord"] * int(discord))
    parts.extend([
        "--ack-live-free-tier", "--i-understand-this-can-send",
        "--confirm-token", "NOT-A-REAL-TOKEN",
        "--require-baseline", "0" * 64 + ":1:1",
        "--ledger-path", f'"{ledger_path or config.ledger_path}"',
        "--env", f'"{Path(config.repo_root) / ".env"}"',
        "--expected-head", str(expected_head),
        "--phx1-structural-policy", str(policy),
        *(["--alert-policy", str(alert_policy)]
          if alert_policy is not None else []),
        "--provider-mode", "paid_primary",
        "--discovery-mode", "polling",
        "--require-production-grpc",
        "--cursor-state-dir", f'"{cursor_dir or config.cursor_state_dir}"',
        "--grpc-gap-recovery", "live_epoch",
        "--enable-dexscreener-restart-backfill",
        "--run-forever",
        "--stop-file", f'"{stop_file}"',
        "--out-dir", f'"{run_dir}"',
    ])
    return " ".join(parts)


def canonical_durable_identity(config, *, state_dir=None) -> Dict[str, Any]:
    """The durable identity the watchdog EXPECTS for this config.

    A test whose subject is not policy still needs its epoch to carry the
    policy the watchdog derives from the launcher; otherwise the identity
    comparison fails for a reason the test is not about.
    """

    from PHX2.free_tier_producer.live_epoch import build_durable_policy_identity
    from PHX2.watchdog.observe import expected_alert_policy
    from PHX2.watchdog.state import file_sha256

    return build_durable_policy_identity(
        state_dir=state_dir or config.cursor_state_dir,
        cursor_state_dir=state_dir or config.cursor_state_dir,
        canonical_ledger_path=config.ledger_path,
        repo_head=config.expected_head,
        launcher_sha256=file_sha256(config.launcher_path),
        delivery_policy="TELEGRAM_ONLY",
        telegram_enabled=True,
        discord_enabled=False,
        structural_policy="SHADOW",
        alert_policy=expected_alert_policy(config),
        dex_backfill_enabled=True,
    )


def healthy_heartbeat(*, tick: int, ts_utc: str,
                      owner_count: int = 1, max_streams: int = 1,
                      telegram_enabled: bool = True,
                      discord_enabled: bool = False,
                      cursor_quarantined: bool = False,
                      cursor_identity_match: bool = True,
                      cursor_durability: str = "CHECKPOINT_DURABILITY_HEALTHY",
                      cursor_last_failure_category: Optional[str] = None,
                      checkpoint_attempted: int = 100,
                      checkpoint_succeeded: int = 100,
                      checkpoint_failed: int = 0,
                      last_durable_slot: int = 435_000_000,
                      delivery_unknown_total: int = 0,
                      sent_committed_total: int = 0,
                      **operational: Any) -> Dict[str, Any]:
    """A redaction-safe producer heartbeat with the fields the watchdog reads."""

    document = {
        "kind": "PRODUCTION_LIVE_HEARTBEAT",
        "tick": int(tick),
        "ts_utc": str(ts_utc),
        "telegram_enabled": bool(telegram_enabled),
        "discord_enabled": bool(discord_enabled),
        "delivery_transport": "TELEGRAM",
        "phx1_structural_policy": "SHADOW",
        "delivery_unknown_total": int(delivery_unknown_total),
        "sent_committed_total": int(sent_committed_total),
        "provider_telemetry": {
            "provider_mode": "paid_primary",
            "status": "CONNECTED",
            "transport_connected": True,
            "source_continuity_state": "NO_GAP",
            "grpc_gap_unresolved_slot_total": 0,
            "total_active_streams": int(owner_count),
            "total_max_active_streams": int(max_streams),
            "active_streams": int(owner_count),
            "max_active_streams": int(max_streams),
            "stream_errors": 0,
            "queue_dropped": 0,
            "events_received": 4242,
            "cursor": {
                "grpc_cursor_quarantined": bool(cursor_quarantined),
                "grpc_subscription_identity_match": bool(cursor_identity_match),
                "grpc_cursor_durability_status": str(cursor_durability),
                "grpc_cursor_last_failure_category": cursor_last_failure_category,
                "grpc_cursor_checkpoint_attempted_total": int(
                    checkpoint_attempted),
                "grpc_cursor_checkpoint_succeeded_total": int(
                    checkpoint_succeeded),
                "grpc_cursor_checkpoint_failed_total": int(checkpoint_failed),
                "grpc_cursor_last_durable_slot": int(last_durable_slot),
            },
            "transport_watermark": {
                "transport_last_observed_at_utc": str(ts_utc),
            },
        },
    }
    document.update(operational)
    return document


def make_config(tmp_path: Path, **overrides: Any) -> WatchdogConfig:
    """A fully offline watchdog configuration with production-shaped bounds."""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "HEAD").write_text(HEAD_SHA + "\n", encoding="utf-8")
    (repo / ".env").write_text("PHX2_DELIVERY_TRANSPORT=telegram\n",
                               encoding="utf-8")
    python = repo / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"")

    launcher = tmp_path / "external" / "launch_live_24x7.ps1"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    # The fake launcher states the alert policy exactly as the canonical one
    # does, so the watchdog's launcher-derived expectation and the producer
    # command line built by ``canonical_producer_command_line`` agree by
    # default.  A test that wants a MISMATCH changes one of the two.
    launcher.write_text(
        f'# fake launcher\n$PIN_HEAD = "{HEAD_SHA}"\n"--run-forever"\n'
        f'"--alert-policy", "{HARNESS_ALERT_POLICY_CLI}"\n',
        encoding="utf-8")

    cursor_dir = tmp_path / "producer_state"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    ledger = tmp_path / "producer_ledger" / "ping_dedupe.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(LEDGER_LINE + "\n", encoding="utf-8")

    config = WatchdogConfig(
        repo_root=str(repo),
        repo_python=str(python),
        launcher_path=str(launcher),
        expected_head=HEAD_SHA,
        state_root=str(tmp_path / "watchdog_state"),
        cursor_state_dir=str(cursor_dir),
        ledger_path=str(ledger),
        runs_root=str(tmp_path / "runs"),
        logs_root=str(tmp_path / "operator_logs"),
        poll_interval_seconds=1.0,
        startup_grace_seconds=30.0,
        heartbeat_max_age_seconds=90.0,
        recovery_stall_seconds=300.0,
        cooperative_stop_timeout_seconds=10.0,
        force_termination_grace_seconds=5.0,
        restart_backoff_seconds=(1.0, 2.0, 3.0, 4.0, 5.0),
        circuit_max_restarts=3,
        circuit_window_seconds=600.0,
        stable_run_reset_seconds=600.0,
        strict_canonical=False,
    )
    if overrides:
        from dataclasses import replace
        config = replace(config, **overrides)
    return config


@dataclass
class FakeWorld:
    """Injectable clock, process table, spawn and terminate."""

    config: WatchdogConfig
    records: List[ProcessRecord] = field(default_factory=list)
    spawns: List[ChildHandle] = field(default_factory=list)
    terminated: List[int] = field(default_factory=list)
    slept: List[float] = field(default_factory=list)
    clock: datetime = field(
        default_factory=lambda: datetime(2026, 7, 26, 12, 0, 0,
                                         tzinfo=timezone.utc))
    spawn_should_raise: bool = False
    #: When set, a spawn produces a producer whose command line is wrong.
    spawn_command_kwargs: Dict[str, Any] = field(default_factory=dict)
    #: When True, spawn registers NO process (the launcher never came up).
    spawn_registers_process: bool = True
    heartbeat_tick: int = 0

    # -- clock -------------------------------------------------------------- #

    def now(self) -> str:
        return self.clock.strftime("%Y-%m-%dT%H:%M:%SZ")

    def advance(self, seconds: float) -> None:
        self.clock = self.clock + timedelta(seconds=float(seconds))

    def sleep(self, seconds: float) -> None:
        self.slept.append(float(seconds))
        self.advance(float(seconds))

    def monotonic(self) -> float:
        return self.clock.timestamp()

    # -- process table ------------------------------------------------------ #

    def table(self) -> List[ProcessRecord]:
        return list(self.records)

    def add_producer(self, *, pid: int, wrapper_pid: int, run_dir: str,
                     stop_file: str, **command_kwargs: Any) -> ProcessRecord:
        record = ProcessRecord(
            pid=int(pid), parent_pid=int(wrapper_pid), name="python.exe",
            executable=str(self.config.repo_python),
            command_line=canonical_producer_command(
                self.config, run_dir=run_dir, stop_file=stop_file,
                **command_kwargs),
            create_time_utc=self.now(),
        )
        self.records.append(record)
        return record

    def add_wrapper(self, *, pid: int) -> ProcessRecord:
        record = ProcessRecord(
            pid=int(pid), parent_pid=os.getpid(), name="powershell.exe",
            executable=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            command_line="powershell.exe -File launch_live_24x7.ps1",
            create_time_utc=self.now())
        self.records.append(record)
        return record

    def add_reexec_shim_pair(self, *, shim_pid: int, real_pid: int,
                             wrapper_pid: int, run_dir: str,
                             stop_file: str) -> None:
        """The repo venv python is a re-exec stub: ONE logical producer appears
        as a shim -> real pair with an identical command line."""

        self.add_producer(pid=shim_pid, wrapper_pid=wrapper_pid,
                          run_dir=run_dir, stop_file=stop_file)
        self.add_producer(pid=real_pid, wrapper_pid=shim_pid,
                          run_dir=run_dir, stop_file=stop_file)

    def remove_pid(self, pid: int) -> None:
        self.records = [r for r in self.records if r.pid != int(pid)]

    def clear_producers(self) -> None:
        from PHX2.watchdog.process import matches_producer_module
        self.records = [r for r in self.records
                        if not matches_producer_module(r)]

    # -- producer-owned artefacts (written by the FAKE producer) ------------- #

    def write_producer_lock(self, pid: int) -> None:
        self.config.producer_runtime_lock_path.parent.mkdir(
            parents=True, exist_ok=True)
        self.config.producer_runtime_lock_path.write_text(
            f"{int(pid)}|{self.now()}", encoding="utf-8")

    def remove_producer_lock(self) -> None:
        try:
            self.config.producer_runtime_lock_path.unlink()
        except OSError:
            pass

    def write_heartbeat(self, run_dir: str, **kwargs: Any) -> Dict[str, Any]:
        self.heartbeat_tick += 1
        document = healthy_heartbeat(
            tick=kwargs.pop("tick", self.heartbeat_tick),
            ts_utc=kwargs.pop("ts_utc", self.now()), **kwargs)
        target = Path(run_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "producer_heartbeat.json").write_text(
            json.dumps(document), encoding="utf-8")
        return document

    # -- injected callables ------------------------------------------------- #

    def spawn(self, config: WatchdogConfig, run_stamp: str, manifest_path: str,
              watchdog_pid: int) -> ChildHandle:
        if self.spawn_should_raise:
            raise OSError("fake launcher spawn failure")
        run_dir = Path(config.runs_root) / f"paid_primary_live_24x7_{run_stamp}"
        log_dir = Path(config.logs_root) / f"paid_primary_live_24x7_{run_stamp}"
        stop_file = log_dir / "STOP_REQUESTED"
        run_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
        Path(manifest_path).write_text(json.dumps({
            "kind": "PHX2_LIVE_24X7_STARTUP_MANIFEST",
            "run_id": f"paid_primary_live_24x7_{run_stamp}",
            "run_dir": str(run_dir),
            "log_dir": str(log_dir),
            "stop_file": str(stop_file),
            "delivery_transport": "TELEGRAM",
            "discord_enabled": False,
            "structural_policy": "SHADOW",
            "runtime_contract": "RUN_FOREVER",
        }), encoding="utf-8")

        wrapper_pid = 40000 + len(self.spawns) * 10
        producer_pid = os.getpid()          # a genuinely LIVE pid
        handle = ChildHandle(
            wrapper_pid=wrapper_pid, run_stamp=str(run_stamp),
            manifest_path=str(manifest_path), started_at_utc=self.now(),
            run_dir=str(run_dir), log_dir=str(log_dir),
            stop_file=str(stop_file))
        if self.spawn_registers_process:
            self.add_wrapper(pid=wrapper_pid)
            self.add_producer(pid=producer_pid, wrapper_pid=wrapper_pid,
                              run_dir=str(run_dir), stop_file=str(stop_file),
                              **self.spawn_command_kwargs)
            self.write_producer_lock(producer_pid)
            self.write_heartbeat(str(run_dir))
            handle.producer_pid = producer_pid
            handle.producer_start_utc = self.now()
        self.spawns.append(handle)
        return handle

    def terminate(self, pid: int) -> bool:
        """Emulate a terminated producer: process gone AND its lock released.

        A real producer releases the state-dir runtime lock on exit (``atexit``),
        and a force-killed one leaves a lock whose holder pid is DEAD -- which the
        watchdog then reclaims on proof. This harness cannot make the test
        process's own pid dead, so lock release is emulated here; the
        dead-holder-with-surviving-lock path is covered separately by
        ``test_stale_lock_removed_only_after_owner_dead_proof`` using a pid this
        machine proves is dead.
        """

        self.terminated.append(int(pid))
        lock = read_producer_lock(self.config.producer_runtime_lock_path)
        if lock.holder_pid == int(pid):
            self.remove_producer_lock()
        self.remove_pid(int(pid))
        return True

    def stop_file_honoured(self) -> None:
        """Simulate the producer noticing the stop file and exiting cleanly."""

        self.clear_producers()
        self.remove_producer_lock()


def make_watchdog(config: WatchdogConfig, world: FakeWorld):
    from PHX2.watchdog.daemon import Watchdog
    return Watchdog(
        config,
        process_table_fn=world.table,
        spawn_fn=world.spawn,
        terminate_fn=world.terminate,
        now_fn=world.now,
        sleep_fn=world.sleep,
        monotonic_fn=world.monotonic,
    )


__all__ = (
    "HEAD_SHA", "OTHER_SHA", "LEDGER_LINE",
    "find_dead_pid", "canonical_producer_command", "healthy_heartbeat",
    "make_config", "FakeWorld", "make_watchdog",
)
