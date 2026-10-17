"""Read-only, no-send safety preflight for the standalone parity runner."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import subprocess
from typing import Callable, Sequence

from PHX2.watchdog.process import (
    ProcessRecord,
    default_process_table,
)


TASK_ABSENT = "ABSENT"
TASK_DISABLED = "DISABLED"
TASK_ENABLED = "ENABLED"
TASK_RUNNING = "RUNNING"
TASK_UNKNOWN = "UNKNOWN"
TASK_STATES = (
    TASK_ABSENT,
    TASK_DISABLED,
    TASK_ENABLED,
    TASK_RUNNING,
    TASK_UNKNOWN,
)

_TASK_QUERY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'PHX2-Watchdog' -ErrorAction SilentlyContinue
if ($null -eq $task) {
    [pscustomobject]@{ state = 'ABSENT' } | ConvertTo-Json -Compress
    exit 0
}
if ([string]$task.State -eq 'Running') {
    [pscustomobject]@{ state = 'RUNNING' } | ConvertTo-Json -Compress
    exit 0
}
if (-not [bool]$task.Settings.Enabled -or
        [string]$task.State -eq 'Disabled') {
    [pscustomobject]@{ state = 'DISABLED' } | ConvertTo-Json -Compress
    exit 0
}
[pscustomobject]@{ state = 'ENABLED' } | ConvertTo-Json -Compress
"""

_WATCHDOG_PROCESS_TOKENS = (
    "phx2.watchdog",
    "phx2_watchdog_task.ps1",
)
_PRODUCER_PROCESS_TOKENS = (
    "phx2.free_tier_producer.free_tier_session",
    "phx2.runtime.production_supervisor",
    "phx2.runtime.production_entrypoint",
)
_YELLOWSTONE_OWNER_TOKENS = (
    "paid_grpc_source",
    "chainstack_yellowstone",
    "yellowstone_grpc_probe",
)


class ShadowParityPreflightError(RuntimeError):
    """Closed-set safety refusal with no raw process or configuration text."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason)
        super().__init__(f"shadow parity preflight refused: {self.reason}")


@dataclass(frozen=True)
class ShadowParityCapabilities:
    telegram_capable: bool = False
    production_ledger_capable: bool = False
    production_launcher_capable: bool = False


@dataclass(frozen=True)
class ShadowParityPreflightFacts:
    task_state: str
    process_enumeration_verified: bool
    watchdog_processes: int
    producer_processes: int
    yellowstone_owners: int
    capabilities: ShadowParityCapabilities = ShadowParityCapabilities()


@dataclass(frozen=True)
class ShadowParityPreflightReport:
    task_state: str
    watchdog_processes: int
    producer_processes: int
    yellowstone_owners: int

    def sanitized_lines(self) -> tuple[str, ...]:
        return (
            f"TASK_STATE={self.task_state}_SAFE",
            f"WATCHDOG_PROCESSES={self.watchdog_processes}",
            f"PRODUCER_PROCESSES={self.producer_processes}",
            f"YELLOWSTONE_OWNERS={self.yellowstone_owners}",
            "TELEGRAM_CONSTRUCTION=DISABLED",
            "PRODUCTION_LEDGER_WRITE=DISABLED",
            "PRODUCTION_LAUNCHER=DISABLED",
        )


def read_watchdog_task_state(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Read task state without changing, deleting, or recreating the task."""

    if os.name != "nt":
        return TASK_ABSENT
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _TASK_QUERY_SCRIPT,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ShadowParityPreflightError("TASK_STATE_UNVERIFIED") from exc
    if completed.returncode != 0:
        raise ShadowParityPreflightError("TASK_STATE_UNVERIFIED")
    try:
        decoded = json.loads(completed.stdout or "{}")
        state = str(decoded.get("state") or TASK_UNKNOWN).upper()
    except (AttributeError, TypeError, ValueError):
        state = TASK_UNKNOWN
    return state if state in TASK_STATES else TASK_UNKNOWN


def _has_token(record: ProcessRecord, tokens: Sequence[str]) -> bool:
    command = str(record.command_line or "").lower()
    return any(token in command for token in tokens)


def collect_preflight_facts(
    *,
    task_state_reader: Callable[[], str] = read_watchdog_task_state,
    process_table_reader: Callable[[], Sequence[ProcessRecord]] = (
        default_process_table
    ),
    capabilities: ShadowParityCapabilities = ShadowParityCapabilities(),
) -> ShadowParityPreflightFacts:
    task_state = str(task_state_reader()).upper()
    table = tuple(process_table_reader())
    current_pid = os.getpid()
    verified = os.name != "nt" or any(
        record.pid == current_pid for record in table
    )
    others = tuple(record for record in table if record.pid != current_pid)
    return ShadowParityPreflightFacts(
        task_state=task_state,
        process_enumeration_verified=verified,
        watchdog_processes=sum(
            _has_token(record, _WATCHDOG_PROCESS_TOKENS)
            for record in others
        ),
        producer_processes=sum(
            _has_token(record, _PRODUCER_PROCESS_TOKENS)
            for record in others
        ),
        yellowstone_owners=sum(
            _has_token(record, _YELLOWSTONE_OWNER_TOKENS)
            for record in others
        ),
        capabilities=capabilities,
    )


def evaluate_preflight(
    facts: ShadowParityPreflightFacts,
) -> ShadowParityPreflightReport:
    if facts.task_state not in (TASK_ABSENT, TASK_DISABLED):
        reason = (
            "TASK_RUNNING"
            if facts.task_state == TASK_RUNNING
            else "TASK_ENABLED"
            if facts.task_state == TASK_ENABLED
            else "TASK_STATE_UNVERIFIED"
        )
        raise ShadowParityPreflightError(reason)
    if not facts.process_enumeration_verified:
        raise ShadowParityPreflightError("PROCESS_ENUMERATION_UNVERIFIED")
    if facts.watchdog_processes:
        raise ShadowParityPreflightError("WATCHDOG_PROCESS_PRESENT")
    if facts.producer_processes:
        raise ShadowParityPreflightError("PRODUCER_PROCESS_PRESENT")
    if facts.yellowstone_owners:
        raise ShadowParityPreflightError("YELLOWSTONE_OWNER_PRESENT")
    if facts.capabilities.telegram_capable:
        raise ShadowParityPreflightError("TELEGRAM_CONSTRUCTION_CAPABLE")
    if facts.capabilities.production_ledger_capable:
        raise ShadowParityPreflightError("PRODUCTION_LEDGER_WRITE_CAPABLE")
    if facts.capabilities.production_launcher_capable:
        raise ShadowParityPreflightError("PRODUCTION_LAUNCHER_CAPABLE")
    return ShadowParityPreflightReport(
        task_state=facts.task_state,
        watchdog_processes=facts.watchdog_processes,
        producer_processes=facts.producer_processes,
        yellowstone_owners=facts.yellowstone_owners,
    )


def run_preflight(
    *,
    facts_reader: Callable[[], ShadowParityPreflightFacts] = (
        collect_preflight_facts
    ),
) -> ShadowParityPreflightReport:
    return evaluate_preflight(facts_reader())


__all__ = (
    "ShadowParityCapabilities",
    "ShadowParityPreflightError",
    "ShadowParityPreflightFacts",
    "ShadowParityPreflightReport",
    "TASK_ABSENT",
    "TASK_DISABLED",
    "TASK_ENABLED",
    "TASK_RUNNING",
    "collect_preflight_facts",
    "evaluate_preflight",
    "read_watchdog_task_state",
    "run_preflight",
)
