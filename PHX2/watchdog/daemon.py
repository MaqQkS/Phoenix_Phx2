"""The watchdog daemon: one supervisor, one producer, bounded restarts.

Everything with a side effect is injected -- the process table, the child spawn,
the clock, the sleep and the terminate call -- so the whole control flow
(adoption, restart, backoff, breaker, cooperative stop, force termination) is
exercised offline against a fake producer with no network, no provider, no
transport, no real ledger and no real durable state.

What the daemon may do is deliberately narrow:

* acquire ONE watchdog lock;
* start ``launch_live_24x7.ps1`` -- and nothing else -- at most once at a time;
* read producer-owned state, always read-only;
* create the producer's own cooperative stop file to ask it to finish;
* write its own observability files.

What it may never do: construct a transport, send anything, open the canonical
ledger writable, mutate cursor or recovery state, own a Yellowstone stream, or
reach the deliberately closed ``main.py``/supervisor armed route.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from PHX2.watchdog import WATCHDOG_PACKAGE_VERSION
from PHX2.watchdog import operational_health as operational_health
from PHX2.watchdog.config import (
    WatchdogConfig,
    apply_overrides,
    default_production_config,
    ensure_state_root,
    load_config_overrides,
    pinned_head_in_launcher,
    resolve_repo_head,
    validate_watchdog_config,
)
from PHX2.watchdog.health import (
    CIRCUIT_OPEN,
    HEALTHY,
    RECOVERING_WITH_PROGRESS,
    RESTARTABLE_PROCESS_FAILURE,
    STARTING,
    STOPPED_BY_OPERATOR,
    HealthVerdict,
    canonicalize_health,
    evaluate_health,
    restart_is_permitted,
)
from PHX2.watchdog.observe import (
    PreviousObservation,
    build_observation,
    expected_alert_policy,
)
from PHX2.watchdog.process import (
    ALREADY_RUNNING,
    ProcessRecord,
    ProcessTable,
    WatchdogLock,
    default_process_table,
    descendants_of,
    evaluate_producer_adoption,
    evaluate_stale_producer_lock,
    logical_producer_pids,
    matches_producer_module,
    new_instance_nonce,
    pid_alive,
    producer_process_pids,
    read_producer_lock,
    remove_stale_producer_lock,
)
from PHX2.watchdog.state import (
    CIRCUIT_CLOSED,
    CIRCUIT_OPEN_STATUS,
    CircuitState,
    RedactionViolation,
    append_jsonl,
    attempts_in_window,
    file_sha256,
    load_circuit_state,
    parse_utc,
    path_digest,
    positive_control_ok,
    prune_attempts,
    read_json,
    save_circuit_state,
    scan_payload,
    utc_now_iso,
    write_json_atomic,
)
from PHX2.watchdog.windows_launch import (
    hidden_startupinfo,
    no_window_creation_flags,
)

# --------------------------------------------------------------------------- #
# producer exit-code policy
# --------------------------------------------------------------------------- #

#: Clean postflight. Under ``--run-forever`` and WITHOUT an operator stop this
#: means a bounded read/tick budget ended the run at a tick boundary, which a
#: fresh process legitimately resets.
EXIT_CLEAN = 0
#: Pre-work refusal (arm gate, path isolation, gRPC contract, gap-recovery
#: config, quarantined checkpoint, state-dir lock held). Configuration or
#: integrity: a restart re-runs the identical refusal, so it must not.
EXIT_REFUSED = 2
#: Postflight failure -- a safety breaker or an ambiguous ledger/delivery state.
#: The producer's own contract says an operator must investigate and never
#: auto-rerun.
EXIT_POSTFLIGHT_FAILED = 3

EXIT_RESTARTABLE = "RESTARTABLE"
EXIT_NONRESTARTABLE = "NONRESTARTABLE"
EXIT_OPERATOR_CLEAN = "OPERATOR_CLEAN"


def classify_producer_exit(exit_code: object, *,
                           operator_stop_requested: bool) -> str:
    """Map a producer exit code onto the restart policy."""

    try:
        code = int(exit_code)
    except (TypeError, ValueError):
        return EXIT_RESTARTABLE
    if code == EXIT_CLEAN:
        return EXIT_OPERATOR_CLEAN if operator_stop_requested else EXIT_RESTARTABLE
    if code in (EXIT_REFUSED, EXIT_POSTFLIGHT_FAILED):
        return EXIT_NONRESTARTABLE
    return EXIT_RESTARTABLE


# --------------------------------------------------------------------------- #
# child handle / spawn
# --------------------------------------------------------------------------- #

@dataclass
class ChildHandle:
    """The launcher wrapper process the watchdog started."""

    wrapper_pid: Optional[int]
    run_stamp: str
    manifest_path: str
    started_at_utc: str
    popen: Any = None
    run_dir: Optional[str] = None
    log_dir: Optional[str] = None
    stop_file: Optional[str] = None
    producer_pid: Optional[int] = None
    producer_start_utc: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        """Redaction-safe: digests and classifications, never raw paths."""

        return {
            "kind": "PHX2_WATCHDOG_CURRENT_CHILD",
            "wrapper_pid": self.wrapper_pid,
            "producer_pid": self.producer_pid,
            "run_stamp": self.run_stamp,
            "started_at_utc": self.started_at_utc,
            "producer_start_utc": self.producer_start_utc,
            "run_dir_digest": path_digest(self.run_dir) if self.run_dir else None,
            "log_dir_digest": path_digest(self.log_dir) if self.log_dir else None,
            "stop_file_digest": (
                path_digest(self.stop_file) if self.stop_file else None),
            "manifest_digest": path_digest(self.manifest_path),
        }


SpawnFn = Callable[[WatchdogConfig, str, str, int], ChildHandle]


# Windows creation flags for the ONE launcher child.  CREATE_NO_WINDOW gives the
# launcher -- powershell.exe, a CONSOLE application -- its OWN windowless console,
# so it actually runs while being isolated from the task's console; and
# CREATE_NEW_PROCESS_GROUP puts it in its own process group.  DETACHED_PROCESS is
# deliberately NOT used: it gives a console application NO console at all, and
# powershell then exits immediately without running a single line (the launcher
# never comes up, so the producer never launches -- a Stage-11 regression proven
# by test_watchdog_process_isolation).  Under the Task Scheduler launch path the
# watchdog, launcher and producer would otherwise share ONE console/process-group;
# a single console or session control event then fells the whole tree at once with
# STATUS_CONTROL_C_EXIT (0xC000013A), observed ~1 min into every scheduled start.
# The watchdog is itself made consoleless by running under pythonw.exe (see the
# scheduled-task tooling); with the launcher on its own windowless console and
# process group, no console control event can reach any part of the supervised
# tree.  Zero on non-Windows: POSIX behaviour is unchanged, and these subprocess
# constants only exist on Windows.
if os.name == "nt":
    LAUNCHER_CREATION_FLAGS = (
        subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    )
else:  # pragma: no cover - POSIX has neither flag and is never the live target
    LAUNCHER_CREATION_FLAGS = 0


def default_spawn(config: WatchdogConfig, run_stamp: str, manifest_path: str,
                  watchdog_pid: int) -> ChildHandle:
    """Start the canonical launcher.  This is the ONLY spawn in the package.

    The producer argument vector is NOT reconstructed here: the launcher owns it.
    Nothing secret is passed on this command line.

    On Windows the launcher is started on its OWN windowless console
    (``CREATE_NO_WINDOW``) and in its own process group
    (``LAUNCHER_CREATION_FLAGS``) so a Task-Scheduler console or session control
    event cannot terminate the whole supervised tree, while powershell still has
    the console it needs to run.  The stdin/stdout/stderr redirection to
    ``DEVNULL`` is preserved, and process identity, adoption, heartbeat and
    cooperative stop-file behaviour are unchanged -- the watchdog tracks the child
    through the process table and the producer's own artifacts, never through this
    handle's console.
    """

    command: List[str] = [
        "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
        "-WindowStyle", "Hidden",
        "-ExecutionPolicy", "Bypass",
        "-File", str(config.launcher_path),
        "-RunStamp", str(run_stamp),
        "-ManifestPath", str(manifest_path),
        "-WatchdogPid", str(int(watchdog_pid)),
    ]
    popen = subprocess.Popen(
        command, cwd=str(config.repo_root),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=LAUNCHER_CREATION_FLAGS,
        startupinfo=hidden_startupinfo(),
    )
    return ChildHandle(
        wrapper_pid=int(popen.pid), run_stamp=str(run_stamp),
        manifest_path=str(manifest_path), started_at_utc=utc_now_iso(),
        popen=popen)


def default_terminate(pid: int) -> bool:
    """Bounded force termination.  Recorded as an incident by the caller."""

    try:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True, text=True, timeout=60.0, check=False,
            creationflags=no_window_creation_flags(),
            startupinfo=hidden_startupinfo())
    except (OSError, subprocess.SubprocessError):
        return False
    return True


# --------------------------------------------------------------------------- #
# events
# --------------------------------------------------------------------------- #

EVENT_WATCHDOG_START = "WATCHDOG_START"
EVENT_WATCHDOG_STOP = "WATCHDOG_STOP"
EVENT_ALREADY_RUNNING = "WATCHDOG_ALREADY_RUNNING"
EVENT_CONFIG_REFUSED = "WATCHDOG_CONFIG_REFUSED"
EVENT_PRODUCER_ADOPTED = "PRODUCER_ADOPTED"
EVENT_PRODUCER_ADOPTION_REFUSED = "PRODUCER_ADOPTION_REFUSED"
EVENT_PRODUCER_LAUNCHED = "PRODUCER_LAUNCHED"
EVENT_PRODUCER_LAUNCH_SUPPRESSED = "PRODUCER_LAUNCH_SUPPRESSED"
EVENT_HEALTH = "HEALTH_EVALUATED"
EVENT_RESTART_REQUESTED = "RESTART_REQUESTED"
EVENT_RESTART_COMPLETED = "RESTART_COMPLETED"
EVENT_RESTART_BLOCKED = "RESTART_BLOCKED"
EVENT_CIRCUIT_OPENED = "CIRCUIT_OPENED"
EVENT_CIRCUIT_CLEARED = "CIRCUIT_CLEARED"
EVENT_RESTART_BUDGET_RESET = "RESTART_BUDGET_RESET"
EVENT_STALE_LOCK_REMOVED = "STALE_PRODUCER_LOCK_REMOVED"
EVENT_STALE_LOCK_REFUSED = "STALE_PRODUCER_LOCK_REMOVAL_REFUSED"
EVENT_COOPERATIVE_STOP_REQUESTED = "COOPERATIVE_STOP_REQUESTED"
EVENT_COOPERATIVE_STOP_COMPLETED = "COOPERATIVE_STOP_COMPLETED"
EVENT_FORCE_TERMINATION = "FORCE_TERMINATION"
EVENT_INCIDENT = "INCIDENT"
EVENT_REDACTION_FAILURE = "REDACTION_FAILURE"


@dataclass
class WatchdogRunResult:
    exit_code: int
    outcome: str
    cycles: int = 0
    final_health: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class Watchdog:
    """One supervised producer, one lock, one bounded restart controller."""

    def __init__(
        self,
        config: WatchdogConfig,
        *,
        process_table_fn: Optional[Callable[[], ProcessTable]] = None,
        spawn_fn: Optional[SpawnFn] = None,
        terminate_fn: Optional[Callable[[int], bool]] = None,
        now_fn: Optional[Callable[[], str]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
        monotonic_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self.config = config
        self._process_table_fn = process_table_fn or default_process_table
        self._spawn_fn = spawn_fn or default_spawn
        self._terminate_fn = terminate_fn or default_terminate
        self._now = now_fn or utc_now_iso
        self._sleep = sleep_fn or time.sleep
        self._monotonic = monotonic_fn or time.monotonic
        self._lock = WatchdogLock(config.lock_path)
        self._child: Optional[ChildHandle] = None
        self._previous = PreviousObservation()
        self._started_at_utc: Optional[str] = None
        self._stable_since_utc: Optional[str] = None
        # Deployment-level market fault clock. Producer generations may
        # restart; a continuing starvation/blindness cause may not earn a new
        # grace window merely because generation-local counters reset.
        self._market_fault_since: Optional[datetime] = None
        self._market_fault_reasons: set[str] = set()
        self._restart_index = 0
        #: True once this watchdog has launched or adopted a producer, so a
        #: later absence is a FAILURE to restart rather than a first start.
        self._ever_launched = False
        self._last_verdict: Optional[HealthVerdict] = None
        #: The most recent real observation, so the final status on exit reports
        #: what was last SEEN rather than an empty document.
        self._last_facts: Dict[str, Any] = {}
        self._launcher_sha256: Optional[str] = None
        self._repo_head: Optional[str] = None
        self._events: List[str] = []

    # -- observability ----------------------------------------------------- #

    def _event(self, kind: str, **fields: Any) -> None:
        record = {"kind": str(kind), "at_utc": self._now(),
                  "watchdog_pid": os.getpid()}
        record.update(fields)
        self._events.append(str(kind))
        try:
            append_jsonl(self.config.events_path, record)
        except RedactionViolation as exc:
            # An event that cannot be written safely is itself an incident, and
            # the SAFE half (the rule labels) is what gets recorded.
            append_jsonl(self.config.events_path, {
                "kind": EVENT_REDACTION_FAILURE, "at_utc": self._now(),
                "original_kind": str(kind), "rule_hits": list(exc.hits)})
        except OSError:
            pass

    def _write_incident(self, *, reason: str, health_class: str,
                        detail: Mapping[str, Any]) -> None:
        payload = {
            "kind": "PHX2_WATCHDOG_INCIDENT",
            "at_utc": self._now(),
            "watchdog_pid": os.getpid(),
            "reason": str(reason),
            "health_class": str(health_class),
            "detail": dict(detail),
            "operator_action_required": True,
        }
        try:
            write_json_atomic(self.config.last_incident_path, payload)
        except (RedactionViolation, OSError):
            pass
        self._event(EVENT_INCIDENT, reason=str(reason),
                    health_class=str(health_class))

    def _write_status(self, *, verdict: Optional[HealthVerdict],
                      facts: Mapping[str, Any], circuit: CircuitState,
                      outcome: str) -> None:
        now = self._now()
        uptime = None
        if self._started_at_utc:
            start = parse_utc(self._started_at_utc)
            end = parse_utc(now)
            if start is not None and end is not None:
                uptime = max(0.0, (end - start).total_seconds())
        payload: Dict[str, Any] = {
            "kind": "PHX2_WATCHDOG_STATUS",
            "schema_version": WATCHDOG_PACKAGE_VERSION,
            "updated_at_utc": now,
            "outcome": str(outcome),
            "watchdog_pid": os.getpid(),
            "watchdog_started_at_utc": self._started_at_utc,
            "watchdog_uptime_seconds": uptime,
            "repo_head": self._repo_head,
            "launcher_sha256": self._launcher_sha256,
            "launcher_path_digest": path_digest(self.config.launcher_path),
            "health_class": verdict.health_class if verdict else None,
            "health_control_class": (
                verdict.control_health_class if verdict else None),
            "health_reasons": list(verdict.reasons) if verdict else [],
            "restart_count_total": int(circuit.restart_count_total),
            "restart_attempts_in_window": attempts_in_window(
                circuit, now_utc=now,
                window_seconds=self.config.circuit_window_seconds),
            "current_backoff_seconds": self.config.backoff_for_attempt(
                self._restart_index),
            "circuit_status": circuit.status,
            "circuit_integrity_locked": bool(circuit.integrity_locked),
            "circuit_open_reason": circuit.open_reason,
            "last_failure_reason": circuit.last_failure_reason,
            "last_successful_health_check_utc": (
                self._stable_since_utc if verdict and verdict.stable else None),
            "stable_since_utc": self._stable_since_utc,
            "producer": self._child.to_payload() if self._child else None,
            "observation": dict(facts),
            "previous_observation": self._previous.to_dict(),
            "redaction_positive_control_ok": positive_control_ok(),
        }
        try:
            write_json_atomic(self.config.status_path, payload)
        except RedactionViolation as exc:
            self._event(EVENT_REDACTION_FAILURE, rule_hits=list(exc.hits),
                        artifact="watchdog_status.json")
            return
        except OSError:
            return
        heartbeat = {
            "kind": "PHX2_WATCHDOG_HEARTBEAT",
            "at_utc": now,
            "watchdog_pid": os.getpid(),
            "health_class": verdict.health_class if verdict else None,
            "health_control_class": (
                verdict.control_health_class if verdict else None),
            "producer_pid": self._child.producer_pid if self._child else None,
            "heartbeat_age_seconds": facts.get("heartbeat_age_seconds"),
            "heartbeat_source": facts.get("heartbeat_source"),
            "circuit_status": circuit.status,
        }
        try:
            write_json_atomic(self.config.heartbeat_path, heartbeat)
        except (RedactionViolation, OSError):
            pass
        if self._child is not None:
            try:
                write_json_atomic(self.config.current_child_path,
                                  self._child.to_payload())
            except (RedactionViolation, OSError):
                pass

    # -- manifest handshake ------------------------------------------------- #

    def _manifest_path_for(self, run_stamp: str) -> Path:
        return self.config.launch_manifest_dir / f"launch_{run_stamp}.json"

    def _absorb_manifest(self, child: ChildHandle) -> bool:
        """Read the launcher's startup manifest to locate its run artifacts."""

        parse_ok, document = read_json(child.manifest_path)
        if not parse_ok or not isinstance(document, dict):
            return False
        child.run_dir = document.get("run_dir") or child.run_dir
        child.log_dir = document.get("log_dir") or child.log_dir
        child.stop_file = document.get("stop_file") or child.stop_file
        return bool(child.run_dir)

    # -- ownership ---------------------------------------------------------- #

    def _table(self) -> List[ProcessRecord]:
        try:
            return list(self._process_table_fn())
        except Exception:
            return []

    def _refresh_producer_identity(self, table: ProcessTable) -> None:
        """Bind the authoritative producer PID from the runtime lock."""

        if self._child is None:
            return
        lock = read_producer_lock(self.config.producer_runtime_lock_path)
        if lock.present and lock.holder_pid is not None \
                and pid_alive(int(lock.holder_pid)):
            self._child.producer_pid = int(lock.holder_pid)
            record = next((item for item in table
                           if item.pid == int(lock.holder_pid)), None)
            if record is not None and record.create_time_utc:
                self._child.producer_start_utc = record.create_time_utc
            elif self._child.producer_start_utc is None:
                self._child.producer_start_utc = lock.acquired_at_utc

    def _adopt_existing(self, table: ProcessTable) -> Optional[ChildHandle]:
        """Adopt a valid canonical producer, or refuse and return None."""

        lock = read_producer_lock(self.config.producer_runtime_lock_path)
        if not lock.present:
            return None
        adoption = evaluate_producer_adoption(
            table=table, lock=lock, repo_python=self.config.repo_python,
            expected_head=str(self._repo_head or self.config.expected_head),
            cursor_state_dir=self.config.cursor_state_dir,
            ledger_path=self.config.ledger_path,
            expected_alert_policy=expected_alert_policy(self.config),
        )
        if not adoption.adoptable:
            self._event(EVENT_PRODUCER_ADOPTION_REFUSED,
                        refusals=list(adoption.reasons),
                        producer_pid=adoption.producer_pid)
            return None
        record = next((item for item in table
                       if item.pid == adoption.producer_pid), None)
        handle = ChildHandle(
            wrapper_pid=record.parent_pid if record else None,
            run_stamp="ADOPTED",
            manifest_path=str(self._manifest_path_for("ADOPTED")),
            started_at_utc=self._now(),
            producer_pid=adoption.producer_pid,
            producer_start_utc=record.create_time_utc if record else
            lock.acquired_at_utc,
        )
        # An adopted producer has no launch manifest of ours, so its run
        # directory AND its cooperative stop file are recovered from its own
        # command line. Without the stop file an adopted producer could only ever
        # be force-killed, which Phase 8 forbids as a first resort.
        handle.run_dir = self._discover_producer_flag(
            adoption.producer_pid, table, "--out-dir")
        handle.stop_file = self._discover_producer_flag(
            adoption.producer_pid, table, "--stop-file")
        self._event(EVENT_PRODUCER_ADOPTED, producer_pid=adoption.producer_pid,
                    run_dir_digest=path_digest(handle.run_dir)
                    if handle.run_dir else None,
                    stop_file_recovered=handle.stop_file is not None)
        return handle

    def _discover_producer_flag(self, pid: Optional[int], table: ProcessTable,
                                flag: str) -> Optional[str]:
        """Recover one valued flag from an adopted producer's command line.

        The value is used in memory only (to locate the heartbeat, or to create
        the producer's own stop file); artifacts record only its digest.  The
        command line itself is never logged -- it carries the confirm token.
        """

        if pid is None:
            return None
        from PHX2.watchdog.process import _command_flag_value
        record = next((item for item in table if item.pid == int(pid)), None)
        if record is None:
            return None
        value = _command_flag_value(record.command_line, str(flag))
        return str(value) if value else None

    # -- lifecycle ---------------------------------------------------------- #

    def _preflight(self) -> Optional[WatchdogRunResult]:
        verdict = validate_watchdog_config(self.config)
        if not verdict.valid:
            self._event(EVENT_CONFIG_REFUSED, refusals=list(verdict.refusals))
            return WatchdogRunResult(
                2, "CONFIG_REFUSED",
                details={"refusals": list(verdict.refusals)})
        if not positive_control_ok():
            self._event(EVENT_REDACTION_FAILURE,
                        rule_hits=["POSITIVE_CONTROL_FAILED"])
            return WatchdogRunResult(2, "REDACTION_POSITIVE_CONTROL_FAILED")
        launcher = Path(self.config.launcher_path)
        if not launcher.exists():
            self._event(EVENT_CONFIG_REFUSED,
                        refusals=["LIVE_LAUNCHER_NOT_DEPLOYED"])
            return WatchdogRunResult(2, "LAUNCHER_NOT_DEPLOYED")
        self._launcher_sha256 = file_sha256(launcher)
        try:
            launcher_text = launcher.read_text(encoding="utf-8")
        except OSError:
            return WatchdogRunResult(2, "LAUNCHER_UNREADABLE")
        pinned = pinned_head_in_launcher(launcher_text)
        self._repo_head = resolve_repo_head(self.config.repo_root)
        if pinned is None:
            self._event(EVENT_CONFIG_REFUSED,
                        refusals=["LAUNCHER_HEAD_PIN_NOT_UNIQUE"])
            return WatchdogRunResult(2, "LAUNCHER_HEAD_PIN_NOT_UNIQUE")
        if self._repo_head is None or pinned != self._repo_head:
            self._event(EVENT_CONFIG_REFUSED,
                        refusals=["LAUNCHER_HEAD_PIN_MISMATCH"],
                        pinned_head=pinned, repo_head=self._repo_head)
            return WatchdogRunResult(2, "LAUNCHER_HEAD_PIN_MISMATCH")
        if str(self.config.expected_head).strip().lower() != self._repo_head:
            self._event(EVENT_CONFIG_REFUSED,
                        refusals=["CONFIG_EXPECTED_HEAD_MISMATCH"])
            return WatchdogRunResult(2, "CONFIG_EXPECTED_HEAD_MISMATCH")
        return None

    def run(self, *, max_cycles: Optional[int] = None,
            max_seconds: Optional[float] = None) -> WatchdogRunResult:
        """The supervision loop.  ``max_cycles``/``max_seconds`` bound tests and
        the bounded live smoke; production passes neither."""

        ensure_state_root(self.config)
        self._started_at_utc = self._now()

        refusal = self._preflight()
        if refusal is not None:
            return refusal

        table = self._table()
        lock_result = self._lock.acquire(
            repo_head=str(self._repo_head or ""),
            launcher_sha256=self._launcher_sha256,
            nonce=new_instance_nonce(), table=table, now_utc=self._started_at_utc)
        if not lock_result.acquired:
            if lock_result.outcome == ALREADY_RUNNING:
                self._event(EVENT_ALREADY_RUNNING,
                            holder_pid=lock_result.holder_pid)
                return WatchdogRunResult(
                    0, ALREADY_RUNNING,
                    details={"holder_pid": lock_result.holder_pid})
            self._event(EVENT_CONFIG_REFUSED, refusals=[lock_result.outcome])
            return WatchdogRunResult(2, lock_result.outcome)

        self._event(EVENT_WATCHDOG_START, launcher_sha256=self._launcher_sha256,
                    repo_head=self._repo_head)
        circuit = load_circuit_state(self.config.circuit_state_path)
        outcome = "STOPPED"
        cycles = 0
        started_mono = self._monotonic()
        try:
            # Adopt before ever launching: a valid producer already running is
            # monitored, never duplicated.
            self._child = self._adopt_existing(table)
            if self._child is not None:
                self._absorb_manifest(self._child)
                self._ever_launched = True

            while True:
                if max_cycles is not None and cycles >= int(max_cycles):
                    outcome = "CYCLE_BUDGET_REACHED"
                    break
                if max_seconds is not None \
                        and (self._monotonic() - started_mono) >= float(max_seconds):
                    outcome = "TIME_BUDGET_REACHED"
                    break
                cycles += 1
                table = self._table()
                operator_stop = self.config.operator_stop_path.exists()
                if self._child is None and not operator_stop \
                        and not circuit.is_open:
                    adopted = self._adopt_existing(table)
                    if adopted is not None:
                        self._child = adopted
                        self._absorb_manifest(self._child)
                        self._ever_launched = True

                if self._child is not None:
                    self._absorb_manifest(self._child)
                    self._refresh_producer_identity(table)

                verdict, facts = self._evaluate(
                    table=table, operator_stop=operator_stop, circuit=circuit)
                self._last_verdict = verdict
                self._last_facts = dict(facts)
                self._event(EVENT_HEALTH, health_class=verdict.health_class,
                            control_class=verdict.control_health_class,
                            reasons=list(verdict.reasons))
                self._track_stability(verdict)
                # Evaluate THIS cycle before a budget reset. A fault arriving
                # at the exact stability boundary must suppress the reset.
                circuit = self._maybe_reset_budget(circuit)
                self._write_status(verdict=verdict, facts=facts,
                                   circuit=circuit, outcome="RUNNING")

                if verdict.control_health_class == STOPPED_BY_OPERATOR \
                        and operator_stop:
                    circuit = self._cooperative_stop(table=table,
                                                     circuit=circuit)
                    outcome = "OPERATOR_STOP"
                    break

                if verdict.integrity_failure \
                        or bool(facts.get("circuit_should_open_operational")):
                    reason = (
                        facts.get("circuit_should_open_operational_reason")
                        or (verdict.reasons or ["UNKNOWN"])[0])
                    circuit = self._open_circuit(
                        circuit, reason=str(reason),
                        integrity=True, health_class=verdict.health_class,
                        detail=dict(facts))
                    self._write_status(verdict=verdict, facts=facts,
                                       circuit=circuit, outcome="CIRCUIT_OPEN")
                    outcome = "CIRCUIT_OPEN"
                    break

                if verdict.control_health_class == CIRCUIT_OPEN:
                    outcome = "CIRCUIT_OPEN"
                    break

                if restart_is_permitted(verdict):
                    # The FIRST launch of a supervision session is not a
                    # restart: it must not consume the restart budget and must
                    # not wait a backoff. Only a producer this watchdog was
                    # already supervising can fail and be restarted.
                    first_launch = (self._child is None
                                    and not self._ever_launched)
                    circuit, launched = self._restart(
                        table=table, circuit=circuit, verdict=verdict,
                        facts=facts, first_launch=first_launch)
                    if not launched:
                        outcome = "CIRCUIT_OPEN"
                        break
                    self._ever_launched = True

                self._sleep(float(self.config.poll_interval_seconds))
        finally:
            save_circuit_state(self.config.circuit_state_path, circuit)
            self._write_status(verdict=self._last_verdict,
                               facts=self._last_facts,
                               circuit=circuit, outcome=outcome)
            self._event(EVENT_WATCHDOG_STOP, outcome=outcome, cycles=cycles)
            self._lock.release()

        return WatchdogRunResult(
            0 if outcome in ("OPERATOR_STOP", "CYCLE_BUDGET_REACHED",
                             "TIME_BUDGET_REACHED") else 3,
            outcome, cycles,
            self._last_verdict.health_class if self._last_verdict else None)

    # -- evaluation --------------------------------------------------------- #

    def _apply_deployment_health_memory(
        self, facts: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Carry one market fault grace clock across producer generations."""

        record = dict(facts)
        dimensions_raw = record.get("dimensions")
        dimensions = [dict(item) for item in dimensions_raw
                      if isinstance(item, Mapping)] \
            if isinstance(dimensions_raw, (list, tuple)) else []
        market = next((item for item in dimensions
                       if item.get("name") == "market_plane"), None)
        if market is None:
            return record
        detail = dict(market.get("detail") or {})
        status = detail.get("market_plane_status")
        reasons_raw = detail.get("market_plane_reasons")
        reasons = {str(item) for item in reasons_raw
                   if isinstance(item, str) and item} \
            if isinstance(reasons_raw, (list, tuple)) else set()
        now = parse_utc(self._now())
        if now is None:
            return record

        if status in ("MARKET_PLANE_HEALTHY", "MARKET_PLANE_IDLE"):
            self._market_fault_since = None
            self._market_fault_reasons.clear()
            record["deployment_market_fault_age_seconds"] = 0.0
            record["deployment_market_fault_reasons"] = []
            return record

        if status not in ("MARKET_PLANE_DEGRADED", "MARKET_PLANE_BLIND") \
                or not reasons:
            # Missing telemetry during process startup does not erase a proven
            # deployment fault and does not by itself escalate it.
            if self._market_fault_since is not None:
                record["deployment_market_fault_age_seconds"] = max(
                    0.0, (now - self._market_fault_since).total_seconds())
                record["deployment_market_fault_reasons"] = sorted(
                    self._market_fault_reasons)
            return record

        if self._market_fault_since is None:
            reported_age = detail.get("blind_age_seconds")
            reported_age = (float(reported_age)
                            if isinstance(reported_age, (int, float))
                            and not isinstance(reported_age, bool) else 0.0)
            self._market_fault_since = now - timedelta(
                seconds=max(0.0, reported_age))
        self._market_fault_reasons.update(reasons)
        age = max(0.0, (now - self._market_fault_since).total_seconds())
        grace = detail.get("grace_seconds")
        grace = (float(grace) if isinstance(grace, (int, float))
                 and not isinstance(grace, bool) else 300.0)
        record["deployment_market_fault_age_seconds"] = age
        record["deployment_market_fault_reasons"] = sorted(
            self._market_fault_reasons)

        if status != "MARKET_PLANE_DEGRADED" or age < grace:
            return record

        # The producer-local clock reset, but the deployment fault did not.
        detail["market_plane_status"] = "MARKET_PLANE_BLIND"
        detail["blind_age_seconds"] = age
        detail["deployment_grace_carried_across_generation"] = True
        market["verdict"] = operational_health.DIM_UNHEALTHY
        market["causes"] = [
            operational_health.CAUSE_MARKET_PLANE_BLIND,
            *sorted(self._market_fault_reasons),
        ]
        market["detail"] = detail
        record["market_plane_status"] = "MARKET_PLANE_BLIND"
        record["market_plane_blind_age_seconds"] = age
        record["dimensions"] = dimensions

        unhealthy = [item for item in dimensions
                     if item.get("verdict") == operational_health.DIM_UNHEALTHY]
        degraded = [item for item in dimensions
                    if item.get("verdict") == operational_health.DIM_DEGRADED]
        causes: List[str] = []
        for item in unhealthy + degraded:
            causes.extend(str(cause) for cause in (item.get("causes") or []))
        record["operational_status"] = (
            operational_health.UNHEALTHY_MULTIPLE_CAUSES
            if len(unhealthy) > 1
            else operational_health.UNHEALTHY_MARKET_PLANE_BLIND)
        record["primary_cause"] = causes[0] if causes else None
        record["secondary_causes"] = causes[1:]
        return record

    def _evaluate(self, *, table: ProcessTable, operator_stop: bool,
                  circuit: CircuitState):
        lock = read_producer_lock(self.config.producer_runtime_lock_path)
        producer_pid = self._child.producer_pid if self._child else None
        # Liveness needs BOTH a live pid AND that pid still being a matching
        # producer process. A pid alone is not enough: Windows recycles pids, and
        # an unrelated program inheriting the old pid would otherwise read as a
        # healthy producer. An EMPTY table means the process query FAILED (a real
        # table always has many entries), and a failed query must never be
        # mistaken for a dead producer -- that would restart a healthy one.
        table_observed = len(list(table)) > 0
        if producer_pid is None or not pid_alive(int(producer_pid)):
            producer_alive = False
        elif table_observed:
            producer_alive = any(
                record.pid == int(producer_pid)
                and matches_producer_module(record) for record in table)
        else:
            producer_alive = True
        adoption = None
        if producer_alive:
            adoption = evaluate_producer_adoption(
                table=table, lock=lock, repo_python=self.config.repo_python,
                expected_head=str(self._repo_head or self.config.expected_head),
                cursor_state_dir=self.config.cursor_state_dir,
                ledger_path=self.config.ledger_path,
                expected_alert_policy=expected_alert_policy(self.config),
            )
        observation = build_observation(
            config=self.config, table=table, lock=lock, adoption=adoption,
            run_dir=self._child.run_dir if self._child else None,
            producer_pid=producer_pid, producer_alive=producer_alive,
            producer_start_utc=(self._child.producer_start_utc
                                if self._child else None),
            operator_stop_requested=bool(operator_stop),
            circuit_open=bool(circuit.is_open),
            producer_expected=True,
            repo_head_matches=bool(
                self._repo_head is not None
                and self._repo_head == str(
                    self.config.expected_head).strip().lower()),
            launcher_identity_matches=bool(
                self._launcher_sha256
                == file_sha256(self.config.launcher_path)),
            redaction_exposure=False,
            previous=self._previous, now_utc=self._now(),
        )
        self._previous = observation.previous
        base = evaluate_health(observation.inputs)
        facts = self._apply_deployment_health_memory(observation.facts)
        verdict = canonicalize_health(base, facts)
        facts["legacy_health_class"] = base.health_class
        facts["canonical_health_class"] = verdict.health_class
        facts["canonical_control_class"] = verdict.control_health_class
        facts["operational_status"] = verdict.health_class
        facts["canonical_health"] = verdict.to_dict()
        return verdict, facts

    def _track_stability(self, verdict: HealthVerdict) -> None:
        if verdict.stable:
            if self._stable_since_utc is None:
                self._stable_since_utc = self._now()
        else:
            self._stable_since_utc = None

    def _maybe_reset_budget(self, circuit: CircuitState) -> CircuitState:
        """A long healthy run earns a fresh restart budget."""

        if circuit.is_open or self._stable_since_utc is None:
            return circuit
        start = parse_utc(self._stable_since_utc)
        now = parse_utc(self._now())
        if start is None or now is None:
            return circuit
        if (now - start).total_seconds() < float(
                self.config.stable_run_reset_seconds):
            return circuit
        if not circuit.attempts_utc and self._restart_index == 0:
            return circuit
        circuit.attempts_utc = []
        self._restart_index = 0
        circuit.last_failure_reason = None
        save_circuit_state(self.config.circuit_state_path, circuit)
        self._event(EVENT_RESTART_BUDGET_RESET,
                    stable_seconds=float(self.config.stable_run_reset_seconds))
        return circuit

    # -- circuit ------------------------------------------------------------ #

    def _open_circuit(self, circuit: CircuitState, *, reason: str,
                      integrity: bool, health_class: str,
                      detail: Mapping[str, Any]) -> CircuitState:
        circuit.status = CIRCUIT_OPEN_STATUS
        circuit.opened_at_utc = self._now()
        circuit.open_reason = str(reason)
        circuit.integrity_locked = bool(integrity) or circuit.integrity_locked
        circuit.last_failure_reason = str(reason)
        save_circuit_state(self.config.circuit_state_path, circuit)
        self._event(EVENT_CIRCUIT_OPENED, reason=str(reason),
                    integrity_locked=bool(circuit.integrity_locked))
        self._write_incident(reason=str(reason), health_class=str(health_class),
                             detail=detail)
        return circuit

    # -- restart ------------------------------------------------------------ #

    def _restart(self, *, table: ProcessTable, circuit: CircuitState,
                 verdict: HealthVerdict, facts: Mapping[str, Any],
                 first_launch: bool = False):
        """The full Phase-6 restart sequence.  Returns ``(circuit, launched)``."""

        now = self._now()
        reason = (verdict.reasons or ["UNKNOWN"])[0]
        if not first_launch:
            self._event(EVENT_RESTART_REQUESTED, reason=reason,
                        health_class=verdict.health_class)

        prune_attempts(circuit, now_utc=now,
                       window_seconds=self.config.circuit_window_seconds)
        if not first_launch:
            in_window = attempts_in_window(
                circuit, now_utc=now,
                window_seconds=self.config.circuit_window_seconds)
            if in_window >= int(self.config.circuit_max_restarts):
                circuit = self._open_circuit(
                    circuit, reason="RESTART_BUDGET_EXHAUSTED", integrity=False,
                    health_class=verdict.health_class, detail=dict(facts))
                self._event(EVENT_RESTART_BLOCKED,
                            reason="RESTART_BUDGET_EXHAUSTED")
                return circuit, False

        # 2-4. cooperative stop, then PROVE the old producer is gone.
        if self._child is not None:
            stopped = self._stop_producer(table=table)
            if not stopped:
                circuit = self._open_circuit(
                    circuit, reason="PRODUCER_WOULD_NOT_STOP", integrity=False,
                    health_class=verdict.health_class, detail=dict(facts))
                self._event(EVENT_RESTART_BLOCKED,
                            reason="PRODUCER_WOULD_NOT_STOP")
                return circuit, False

        table = self._table()
        surviving = producer_process_pids(table)
        if surviving:
            # NEVER restart over a still-live producer.
            circuit = self._open_circuit(
                circuit, reason="PRODUCER_STILL_ALIVE_BEFORE_RESTART",
                integrity=False, health_class=verdict.health_class,
                detail={"surviving_producer_pids": surviving})
            self._event(EVENT_RESTART_BLOCKED,
                        reason="PRODUCER_STILL_ALIVE_BEFORE_RESTART")
            return circuit, False

        # 5-6. owner count zero + producer lock released (or proven stale).
        lock = read_producer_lock(self.config.producer_runtime_lock_path)
        if lock.present:
            stale = evaluate_stale_producer_lock(
                lock=lock, table=table, yellowstone_owner_count=0)
            if stale.removable:
                if remove_stale_producer_lock(
                        self.config.producer_runtime_lock_path, verdict=stale):
                    self._event(EVENT_STALE_LOCK_REMOVED, reason=stale.reason,
                                evidence=dict(stale.evidence))
                else:
                    self._event(EVENT_STALE_LOCK_REFUSED,
                                reason="LOCK_UNLINK_FAILED")
                    circuit = self._open_circuit(
                        circuit, reason="STALE_LOCK_UNREMOVABLE",
                        integrity=False, health_class=verdict.health_class,
                        detail=dict(stale.evidence))
                    return circuit, False
            else:
                self._event(EVENT_STALE_LOCK_REFUSED, reason=stale.reason,
                            evidence=dict(stale.evidence))
                circuit = self._open_circuit(
                    circuit, reason="AMBIGUOUS_PRODUCER_LOCK_OWNERSHIP",
                    integrity=True, health_class=verdict.health_class,
                    detail=dict(stale.evidence))
                return circuit, False

        # 7. the ledger must not be left ambiguous.
        if not bool(facts.get("paid_ledger_parse_ok", True)):
            circuit = self._open_circuit(
                circuit, reason="LEDGER_AMBIGUOUS_BEFORE_RESTART",
                integrity=True, health_class=verdict.health_class,
                detail=dict(facts))
            return circuit, False

        # 8. backoff.
        if not first_launch:
            delay = self.config.backoff_for_attempt(self._restart_index)
            jitter = float(self.config.restart_backoff_jitter_seconds or 0.0)
            self._sleep(delay + jitter)

        # 9. launch exactly one replacement.
        table = self._table()
        if producer_process_pids(table):
            self._event(EVENT_PRODUCER_LAUNCH_SUPPRESSED,
                        reason="PRODUCER_APPEARED_DURING_BACKOFF")
            return circuit, False
        run_stamp = self._run_stamp()
        manifest = self._manifest_path_for(run_stamp)
        try:
            child = self._spawn_fn(self.config, run_stamp, str(manifest),
                                   os.getpid())
        except Exception:
            circuit = self._open_circuit(
                circuit, reason="LAUNCHER_SPAWN_FAILED", integrity=False,
                health_class=verdict.health_class, detail={})
            return circuit, False
        self._child = child
        self._previous = PreviousObservation()
        self._stable_since_utc = None
        self._event(EVENT_PRODUCER_LAUNCHED, wrapper_pid=child.wrapper_pid,
                    run_stamp=run_stamp, first_launch=bool(first_launch))

        # 11. restart accounting (a first launch is not a restart).
        if not first_launch:
            circuit.attempts_utc.append(self._now())
            circuit.restart_count_total = int(circuit.restart_count_total) + 1
            circuit.last_restart_utc = self._now()
            circuit.last_failure_reason = reason
            self._restart_index += 1
            save_circuit_state(self.config.circuit_state_path, circuit)
            try:
                append_jsonl(self.config.restart_history_path, {
                    "kind": "PHX2_WATCHDOG_RESTART",
                    "at_utc": circuit.last_restart_utc,
                    "reason": reason,
                    "health_class": verdict.health_class,
                    "restart_index": self._restart_index,
                    "restart_count_total": circuit.restart_count_total,
                    "backoff_seconds": self.config.backoff_for_attempt(
                        max(0, self._restart_index - 1)),
                    "wrapper_pid": child.wrapper_pid,
                })
            except (RedactionViolation, OSError):
                pass
            self._event(EVENT_RESTART_COMPLETED, reason=reason,
                        restart_index=self._restart_index)
        return circuit, True

    def _run_stamp(self) -> str:
        stamp = parse_utc(self._now()) or datetime.now(timezone.utc)
        return stamp.strftime("%Y%m%dT%H%M%SZ")

    # -- cooperative stop --------------------------------------------------- #

    def _stop_producer(self, *, table: ProcessTable) -> bool:
        """Ask the producer to finish, then PROVE it did.

        Force termination is a last resort after the bounded cooperative window
        AND is always recorded as an incident.
        """

        child = self._child
        if child is None:
            return True
        stop_file = child.stop_file
        if stop_file:
            try:
                Path(stop_file).parent.mkdir(parents=True, exist_ok=True)
                Path(stop_file).write_text(
                    f"stop_requested_at_utc={self._now()}\n", encoding="utf-8")
                self._event(EVENT_COOPERATIVE_STOP_REQUESTED,
                            stop_file_digest=path_digest(stop_file))
            except OSError:
                self._event(EVENT_COOPERATIVE_STOP_REQUESTED,
                            stop_file_digest=None, write_failed=True)
        else:
            # Without the producer's own stop file the only remaining lever is
            # bounded force termination, which is an incident, not a routine
            # shutdown. Record it as such rather than letting it look normal.
            self._event(EVENT_COOPERATIVE_STOP_REQUESTED,
                        stop_file_digest=None, stop_file_unknown=True)
            self._write_incident(
                reason="COOPERATIVE_STOP_FILE_UNKNOWN",
                health_class="STOPPED_BY_OPERATOR",
                detail={"producer_pid": child.producer_pid,
                        "note": ("the producer's --stop-file could not be "
                                 "recovered, so a cooperative stop was not "
                                 "possible")})

        deadline = self._monotonic() + float(
            self.config.cooperative_stop_timeout_seconds)
        while self._monotonic() < deadline:
            table = self._table()
            if not producer_process_pids(table):
                self._event(EVENT_COOPERATIVE_STOP_COMPLETED, forced=False)
                self._child = None
                return True
            self._sleep(min(float(self.config.poll_interval_seconds), 5.0))

        # bounded force termination
        table = self._table()
        pids = producer_process_pids(table)
        wrapper = child.wrapper_pid
        targets: List[int] = list(pids)
        if wrapper is not None and pid_alive(int(wrapper)):
            targets.append(int(wrapper))
            targets.extend(descendants_of(table, int(wrapper)))
        forced_any = False
        for pid in sorted(set(targets)):
            if self._terminate_fn(int(pid)):
                forced_any = True
        if forced_any:
            self._event(EVENT_FORCE_TERMINATION, target_count=len(set(targets)))
            self._write_incident(
                reason="FORCE_TERMINATION_AFTER_COOPERATIVE_TIMEOUT",
                health_class="STOPPED_BY_OPERATOR",
                detail={"target_count": len(set(targets)),
                        "cooperative_timeout_seconds": float(
                            self.config.cooperative_stop_timeout_seconds)})
        grace_deadline = self._monotonic() + float(
            self.config.force_termination_grace_seconds)
        while self._monotonic() < grace_deadline:
            if not producer_process_pids(self._table()):
                self._child = None
                return True
            self._sleep(1.0)
        return not producer_process_pids(self._table())

    def _cooperative_stop(self, *, table: ProcessTable,
                          circuit: CircuitState) -> CircuitState:
        stopped = self._stop_producer(table=table)
        if not stopped:
            circuit = self._open_circuit(
                circuit, reason="PRODUCER_WOULD_NOT_STOP_ON_OPERATOR_REQUEST",
                integrity=False, health_class=STOPPED_BY_OPERATOR, detail={})
        else:
            lock = read_producer_lock(self.config.producer_runtime_lock_path)
            if lock.present:
                stale = evaluate_stale_producer_lock(
                    lock=lock, table=self._table(), yellowstone_owner_count=0)
                if stale.removable:
                    remove_stale_producer_lock(
                        self.config.producer_runtime_lock_path, verdict=stale)
                    self._event(EVENT_STALE_LOCK_REMOVED, reason=stale.reason,
                                evidence=dict(stale.evidence))
        return circuit

    # -- operator commands -------------------------------------------------- #

    def status_snapshot(self) -> Dict[str, Any]:
        parse_ok, document = read_json(self.config.status_path)
        circuit = load_circuit_state(self.config.circuit_state_path)
        lock_present, lock_document = self._lock.read()
        producer_lock = read_producer_lock(
            self.config.producer_runtime_lock_path)
        holder = None
        if isinstance(lock_document, dict):
            holder = lock_document.get("watchdog_pid")
        return {
            "kind": "PHX2_WATCHDOG_STATUS_QUERY",
            "at_utc": self._now(),
            "status_file_present": bool(parse_ok),
            "status": document if isinstance(document, dict) else None,
            "watchdog_lock_present": bool(lock_present),
            "watchdog_lock_holder_pid": holder,
            "watchdog_running": bool(
                holder is not None and pid_alive(int(holder))),
            "producer_lock_present": bool(producer_lock.present),
            "producer_lock_holder_pid": producer_lock.holder_pid,
            "producer_running": bool(
                producer_lock.holder_pid is not None
                and pid_alive(int(producer_lock.holder_pid))),
            "circuit_status": circuit.status,
            "circuit_integrity_locked": bool(circuit.integrity_locked),
            "circuit_open_reason": circuit.open_reason,
            "circuit_document_state": circuit.document_state,
            "restart_count_total": int(circuit.restart_count_total),
            "operator_stop_requested": (
                self.config.operator_stop_path.exists()),
        }

    def request_operator_stop(self) -> Dict[str, Any]:
        ensure_state_root(self.config)
        self.config.operator_stop_path.write_text(
            f"requested_at_utc={self._now()}\n", encoding="utf-8")
        self._event("OPERATOR_STOP_MARKER_CREATED")
        return {"operator_stop_requested": True}

    def clear_operator_stop(self) -> Dict[str, Any]:
        try:
            self.config.operator_stop_path.unlink()
        except OSError:
            pass
        return {"operator_stop_requested": False}

    def clear_circuit(self, *, acknowledge_integrity: bool = False
                      ) -> Dict[str, Any]:
        """Explicit operator clear.  An integrity lock needs an explicit ack."""

        circuit = load_circuit_state(self.config.circuit_state_path)
        if circuit.integrity_locked and not acknowledge_integrity:
            return {
                "cleared": False,
                "reason": "INTEGRITY_LOCK_REQUIRES_EXPLICIT_ACKNOWLEDGEMENT",
                "open_reason": circuit.open_reason,
            }
        circuit.status = CIRCUIT_CLOSED
        circuit.opened_at_utc = None
        circuit.open_reason = None
        circuit.integrity_locked = False
        circuit.attempts_utc = []
        save_circuit_state(self.config.circuit_state_path, circuit)
        self._restart_index = 0
        self._event(EVENT_CIRCUIT_CLEARED,
                    acknowledged_integrity=bool(acknowledge_integrity))
        return {"cleared": True, "circuit_status": circuit.status}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _resolve_config(args: argparse.Namespace) -> WatchdogConfig:
    head = (str(getattr(args, "expected_head", "") or "").strip().lower()
            or (resolve_repo_head(
                getattr(args, "repo_root", None) or None) or ""))
    if not head:
        from PHX2.free_tier_producer.launcher_contract import REPO_ROOT
        head = resolve_repo_head(REPO_ROOT) or ""
    config = default_production_config(expected_head=head)
    override_path = getattr(args, "config", None)
    if override_path:
        config = apply_overrides(config, load_config_overrides(override_path))
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m PHX2.watchdog",
        description=("PHX2 watchdog: keeps ONE armed Telegram-only producer "
                     "alive via the canonical launch_live_24x7.ps1. Never "
                     "sends, never writes the ledger, never owns Yellowstone."))
    parser.add_argument("action", choices=(
        "run", "status", "stop", "restart", "validate", "clear-circuit"))
    parser.add_argument("--config", default=None,
                        help="optional JSON override document")
    parser.add_argument("--expected-head", default=None,
                        help="pin the repository commit (defaults to HEAD)")
    parser.add_argument("--max-cycles", type=int, default=None,
                        help="bound the supervision loop (tests / smoke)")
    parser.add_argument("--max-seconds", type=float, default=None,
                        help="bound the supervision loop by wall clock")
    parser.add_argument("--i-understand-integrity-risk", action="store_true",
                        dest="acknowledge_integrity",
                        help="required to clear an integrity-locked circuit")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = _resolve_config(args)
    except (OSError, ValueError) as exc:
        print(f"[refused] WATCHDOG_CONFIG_UNREADABLE: {type(exc).__name__}")
        return 2

    verdict = validate_watchdog_config(config)
    if args.action == "validate":
        print(f"config_valid={verdict.valid}")
        for reason in verdict.refusals:
            print(f"  refusal={reason}")
        print(f"expected_head={config.expected_head}")
        print(f"redaction_positive_control_ok={positive_control_ok()}")
        return 0 if verdict.valid else 2
    if not verdict.valid:
        print("[refused] WATCHDOG_CONFIG_REFUSED: "
              + ", ".join(verdict.refusals))
        return 2

    watchdog = Watchdog(config)

    if args.action == "run":
        result = watchdog.run(max_cycles=args.max_cycles,
                              max_seconds=args.max_seconds)
        print(f"outcome={result.outcome} cycles={result.cycles} "
              f"final_health={result.final_health} exit={result.exit_code}")
        return int(result.exit_code)

    if args.action == "status":
        snapshot = watchdog.status_snapshot()
        for key in ("watchdog_running", "watchdog_lock_holder_pid",
                    "producer_running", "producer_lock_holder_pid",
                    "circuit_status", "circuit_integrity_locked",
                    "circuit_open_reason", "restart_count_total",
                    "operator_stop_requested", "status_file_present"):
            print(f"{key}={snapshot.get(key)}")
        status = snapshot.get("status") or {}
        for key in ("health_class", "health_reasons", "updated_at_utc"):
            print(f"{key}={status.get(key)}")
        observation = status.get("observation") or {}
        for key in (
            "primary_migration_source",
            "primary_recovery",
            "shadow_source",
            "chainstack_configured_for_runtime",
            "chainstack_connected",
            "chainstack_comparator",
            "telegram_enabled",
            "discord_enabled",
        ):
            print(f"{key}={observation.get(key)}")
        return 0

    if args.action == "stop":
        watchdog.request_operator_stop()
        print("operator_stop_requested=True")
        print("note=the watchdog stops the producer cooperatively, then exits")
        return 0

    if args.action == "restart":
        # An operator restart is stop-then-let-the-service-start-again, never a
        # second producer beside the first.
        watchdog.request_operator_stop()
        print("operator_stop_requested=True")
        print("note=re-run `python -m PHX2.watchdog run` (or re-enable the "
              "scheduled task) once the producer has stopped")
        return 0

    if args.action == "clear-circuit":
        result = watchdog.clear_circuit(
            acknowledge_integrity=bool(args.acknowledge_integrity))
        for key, value in result.items():
            print(f"{key}={value}")
        return 0 if result.get("cleared") else 2

    return 2


__all__ = (
    "EXIT_CLEAN", "EXIT_REFUSED", "EXIT_POSTFLIGHT_FAILED",
    "EXIT_RESTARTABLE", "EXIT_NONRESTARTABLE", "EXIT_OPERATOR_CLEAN",
    "classify_producer_exit",
    "ChildHandle", "SpawnFn", "default_spawn", "default_terminate",
    "Watchdog", "WatchdogRunResult",
    "build_parser", "main",
)
