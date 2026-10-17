"""Stable fail-closed supervisor for the PHX2 Telegram production pipeline.

This module owns process lifecycle only.  The producer, paper engine, dashboard,
and Telegram implementation remain the existing checked-in PHX2
components.  Secrets are loaded only inside the producer child and never placed
on an operating-system command line or in supervisor artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from PHX2.delivery.telegram_config import TelegramConfig, TelegramConfigError
from PHX2.models.artifact_source_labels import SOURCE_ROLE_PAID_MARKET_PRIMARY


DEFAULT_HOURS = 24.0
DEFAULT_RUNTIME_ROOT = Path(r"C:\tmp" if os.name == "nt" else "/tmp")
DEFAULT_LOCK_PATH = DEFAULT_RUNTIME_ROOT / "phx2_production_session.lock"
DEFAULT_ENV_FILE = Path(r"C:\Users\BalaC\Documents\phx2.env")
DEFAULT_ACTIVE_LEDGER = Path(r"C:\Users\BalaC\phx2_live_free_tier\ping_dedupe.jsonl")
DEFAULT_FROZEN_LEDGER = Path(
    r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl"
)
DEFAULT_PAPER_CONFIG = Path(r"C:\Users\BalaC\phx2_paper_trading\paper_config.json")
EXPECTED_FROZEN_LEDGER = (
    16,
    5849,
    "fa7eb26080bb45d82ce583341b3eea1eb3c712ec3dc9555f876eb8ce1a8926fd",
)
PROCESS_ENUMERATION_TIMEOUT_SECONDS = 12.0
OFFLINE_PREFLIGHT_TIMEOUT_SECONDS = 25.0
COOPERATIVE_PRODUCER_TIMEOUT_SECONDS = 60.0
COOPERATIVE_CHILD_TIMEOUT_SECONDS = 20.0
FORCE_TIMEOUT_SECONDS = 10.0
MIGRATION_ACTIVATION_MULTIPLIER = Decimal("1.20")
# The armed private-live send path is the three canonical PowerShell launchers,
# and ONLY those. ``main.py --hours`` / the supervisor producer child is a
# non-arming route: it never sends and refuses before constructing any source,
# channel, transport, writable ledger or cursor. Operator arm acknowledgement
# lives exclusively at the canonical launcher.
CANONICAL_ARMED_LAUNCHERS = (
    "launch_pressure_24h_01.ps1",
    "launch_soak_02h_01.ps1",
    "launch_window_04.ps1",
)
ARMED_ROUTE_REFUSAL = "ARMED_PRIVATE_LIVE_REFUSED_USE_CANONICAL_LAUNCHERS"
PAPER_RESTART_MAX_ATTEMPTS = 3
PAPER_RESTART_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
# Single-stream production topology: one primary Yellowstone subscription,
# no liquidity-verifier stream, LP Integrity removed from send authorization.
PRIMARY_MAX_GRPC_STREAMS = 1
VERIFIER_MAX_GRPC_STREAMS = 0
MAX_GRPC_STREAMS = 1
LP_INTEGRITY_MODE = "DISABLED_SINGLE_STREAM"
VERIFIER_STREAM_STATUS_DISABLED = "DISABLED"

_SAFE_REASON_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.:-"
)
_REQUIRED_ENV_NAMES = (
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE29_2_BIRDEYE_API_KEY",
    "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
    "PHX2_DELIVERY_TRANSPORT",
    "PHX2_TELEGRAM_ENABLED",
    "PHX2_TELEGRAM_BOT_TOKEN",
    "PHX2_TELEGRAM_CHAT_ID",
    "PHX2_TELEGRAM_PARSE_MODE",
    "PHX2_TELEGRAM_DISABLE_LINK_PREVIEW",
    "PHX2_DISCORD_ENABLED",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_reason(value: object, default: str = "UNKNOWN") -> str:
    text = value if isinstance(value, str) else ""
    if 0 < len(text) <= 96 and all(char in _SAFE_REASON_CHARS for char in text):
        return text
    return default


class ProductionRefusal(RuntimeError):
    """A closed-set production preflight or lifecycle refusal."""

    def __init__(self, reason: str) -> None:
        self.reason = safe_reason(reason, "PRODUCTION_REFUSED")
        super().__init__(self.reason)


class ProcessEnumerationError(ProductionRefusal):
    def __init__(self, reason: str = "PROCESS_ENUMERATION_FAILED_CLOSED") -> None:
        super().__init__(reason)


@dataclass(frozen=True)
class LedgerBaseline:
    line_count: int
    size_bytes: int
    sha256: str

    def as_token(self) -> str:
        return f"{self.sha256}:{self.size_bytes}:{self.line_count}"

    def as_tuple(self) -> tuple[int, int, str]:
        return self.line_count, self.size_bytes, self.sha256


def ledger_baseline(path: Path) -> LedgerBaseline:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ProductionRefusal("LEDGER_BASELINE_UNAVAILABLE") from exc
    return LedgerBaseline(
        line_count=data.count(b"\n"),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: List[Dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    parent_pid: int
    name: str
    role: str
    start_utc: str
    run_dir: Optional[str] = None


_PROCESS_SCAN_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$selfPid = [int]$env:PHX2_SCAN_SELF_PID
$lockOwnerPid = [int]$env:PHX2_SCAN_LOCK_OWNER_PID
$targetRun = [string]$env:PHX2_SCAN_RUN_DIR
$rows = @()
foreach ($p in @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate)) {
    $pidValue = [int]$p.ProcessId
    $name = [string]$p.Name
    $isPython = $name -match '^(?i:python|pythonw|py)(\.exe)?$'
    if (-not $isPython) { continue }
    $cmd = [string]$p.CommandLine
    $lower = $cmd.ToLowerInvariant()
    $role = $null
    if ($pidValue -eq $selfPid) {
        $role = 'SELF'
    } elseif (([string]$p.ExecutablePath -match '(?i)\\Phoenix_Bot\\') -or
              ($cmd -match '(?i)(?:^|[\\/])Phoenix_Bot(?:[\\/]|\s)')) {
        $role = 'OLD_PHOENIX'
    } elseif ($lower.Contains('phx2.runtime.production_supervisor')) {
        if ($lower.Contains('--child-role producer')) { $role = 'PRODUCER' }
        else { $role = 'SUPERVISOR' }
    } elseif ($lower.Contains('phx2.free_tier_producer.free_tier_session') -or
              $lower.Contains('producer_entry.py')) {
        $role = 'PRODUCER'
    } elseif ($lower.Contains('phx2.scripts.phx2_live_paper_trade')) {
        $role = 'PAPER'
    } elseif ($lower.Contains('phx2.dashboard.server')) {
        $role = 'DASHBOARD'
    } elseif ($lower.Contains('phx2.observability.operator_console')) {
        $role = 'OPERATOR_CONSOLE'
    } elseif ($lower.Contains('phx2.runtime.production_entrypoint')) {
        $role = 'SUPERVISOR'
    } elseif ($lockOwnerPid -gt 0 -and $pidValue -eq $lockOwnerPid) {
        $role = 'LOCK_OWNER_CANDIDATE'
    }
    if ($null -eq $role) { continue }
    $ownedRun = $null
    if ($targetRun -and $lower.Contains($targetRun.ToLowerInvariant())) {
        $ownedRun = $targetRun
    }
    $started = ''
    if ($null -ne $p.CreationDate) {
        $started = $p.CreationDate.ToUniversalTime().ToString('o')
    }
    $rows += [pscustomobject]@{
        pid = $pidValue
        parent_pid = [int]$p.ParentProcessId
        name = $name
        role = $role
        start_utc = $started
        run_dir = $ownedRun
    }
}
@($rows) | ConvertTo-Json -Compress
"""


class ProcessScanner:
    """Bounded, redaction-safe Windows process enumeration.

    Raw command lines exist only inside the PowerShell process.  Its JSON output
    contains a closed-set role, PID metadata, and an optional caller-supplied run
    directory; raw command lines and executable arguments are never returned.
    """

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout_seconds: float = PROCESS_ENUMERATION_TIMEOUT_SECONDS,
    ) -> None:
        self._runner = runner
        self._timeout = float(timeout_seconds)

    def scan(
        self, run_dir: Optional[Path] = None, *, owner_pid: Optional[int] = None
    ) -> List[ProcessRecord]:
        if os.name != "nt":
            return [
                ProcessRecord(
                    pid=os.getpid(),
                    parent_pid=os.getppid(),
                    name=Path(sys.executable).name,
                    role="SELF",
                    start_utc="",
                    run_dir=str(run_dir) if run_dir else None,
                )
            ]
        env = dict(os.environ)
        env["PHX2_SCAN_SELF_PID"] = str(os.getpid())
        env["PHX2_SCAN_LOCK_OWNER_PID"] = str(int(owner_pid or 0))
        env["PHX2_SCAN_RUN_DIR"] = str(run_dir or "")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = self._runner(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    _PROCESS_SCAN_SCRIPT,
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=env,
                creationflags=flags,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProcessEnumerationError() from exc
        if completed.returncode != 0:
            raise ProcessEnumerationError()
        try:
            decoded = json.loads(completed.stdout or "[]")
        except (TypeError, ValueError) as exc:
            raise ProcessEnumerationError("PROCESS_ENUMERATION_INVALID") from exc
        rows = decoded if isinstance(decoded, list) else [decoded]
        records: List[ProcessRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ProcessEnumerationError("PROCESS_ENUMERATION_INVALID")
            try:
                role = safe_reason(row.get("role"), "UNCLASSIFIED")
                records.append(
                    ProcessRecord(
                        pid=int(row["pid"]),
                        parent_pid=int(row.get("parent_pid") or 0),
                        name=Path(str(row.get("name") or "python")).name,
                        role=role,
                        start_utc=str(row.get("start_utc") or ""),
                        run_dir=(
                            str(row.get("run_dir")) if row.get("run_dir") else None
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ProcessEnumerationError("PROCESS_ENUMERATION_INVALID") from exc
        return records


@dataclass(frozen=True)
class ProductionPaths:
    repo_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    lock_path: Path = DEFAULT_LOCK_PATH
    env_file: Path = DEFAULT_ENV_FILE
    active_ledger: Path = DEFAULT_ACTIVE_LEDGER
    frozen_ledger: Path = DEFAULT_FROZEN_LEDGER
    paper_config: Path = DEFAULT_PAPER_CONFIG
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8642

    @property
    def python_executable(self) -> Path:
        if os.name == "nt":
            candidate = self.repo_root / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = self.repo_root / ".venv" / "bin" / "python"
        # Keep the authoritative entrypoint usable from a checkout that relies
        # on the interpreter which launched ``python main.py``.
        return candidate if candidate.is_file() else Path(sys.executable).resolve()


@dataclass(frozen=True)
class ProductionConfig:
    run_dir: Path
    hours: float = DEFAULT_HOURS
    paths: ProductionPaths = field(default_factory=ProductionPaths)
    migration_activation_multiplier: Decimal = MIGRATION_ACTIVATION_MULTIPLIER

    def __post_init__(self) -> None:
        if (not isinstance(self.migration_activation_multiplier, Decimal)
                or self.migration_activation_multiplier
                != MIGRATION_ACTIVATION_MULTIPLIER):
            raise ValueError("production migration activation multiplier is pinned to Decimal('1.20')")

    @property
    def runtime_seconds(self) -> float:
        return float(self.hours) * 3600.0

    @property
    def producer_dir(self) -> Path:
        return self.run_dir / "producer"

    @property
    def paper_root(self) -> Path:
        return self.run_dir / "paper_root"

    @property
    def paper_dir(self) -> Path:
        return self.paper_root / "paper"

    @property
    def control_dir(self) -> Path:
        return self.run_dir / "control"

    @property
    def log_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def stop_file(self) -> Path:
        return self.control_dir / "STOP_REQUESTED"


def fresh_run_dir(
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    *,
    now: Optional[datetime] = None,
) -> Path:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    return runtime_root / f"phx2_live_{stamp}"


def _parse_env_file(path: Path) -> Dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ProductionRefusal("ENV_FILE_UNAVAILABLE") from exc
    values: Dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name.replace("_", "a").isalnum() or name[0].isdigit():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[name] = value
    return values


def validate_production_environment(path: Path) -> None:
    values = _parse_env_file(path)
    if any(not values.get(name, "").strip() for name in _REQUIRED_ENV_NAMES):
        raise ProductionRefusal("PRODUCTION_CONFIGURATION_INCOMPLETE")
    for name in (
        "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
        "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
    ):
        if values[name].strip().lower() not in ("1", "true", "yes", "on"):
            raise ProductionRefusal("PRODUCTION_CONFIGURATION_DISARMED")
    try:
        TelegramConfig.from_mapping(values)
    except TelegramConfigError as exc:
        raise ProductionRefusal(exc.reason) from exc
    except Exception as exc:
        raise ProductionRefusal("TELEGRAM_CONFIGURATION_INVALID") from exc


def _record_matches_owner(record: ProcessRecord, lock: Mapping[str, Any]) -> bool:
    try:
        return (
            record.pid == int(lock.get("supervisor_pid"))
            and bool(record.start_utc)
            and record.start_utc == str(lock.get("supervisor_start_utc") or "")
        )
    except (TypeError, ValueError):
        return False


def _int_or_zero(value: object) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return 0
    return parsed if parsed > 0 else 0


class SessionLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.owner_nonce: Optional[str] = None

    def inspect(self, records: Iterable[ProcessRecord]) -> tuple[str, Optional[Dict[str, Any]]]:
        if not self.path.exists():
            return "ABSENT", None
        lock = read_json(self.path)
        if lock is None:
            return "STALE", None
        if any(_record_matches_owner(record, lock) for record in records):
            return "ACTIVE", lock
        return "STALE", lock

    def acquire(
        self,
        *,
        run_dir: Path,
        records: Sequence[ProcessRecord],
    ) -> Dict[str, Any]:
        state, lock = self.inspect(records)
        if state == "ACTIVE":
            raise ProductionRefusal("PHX2_SESSION_ALREADY_ACTIVE")
        if state == "STALE":
            try:
                self.path.unlink()
            except OSError as exc:
                raise ProductionRefusal("STALE_SESSION_LOCK_UNCLEANABLE") from exc
        self_record = next((record for record in records if record.role == "SELF"), None)
        if self_record is None or not self_record.start_utc:
            raise ProcessEnumerationError("CURRENT_PROCESS_IDENTITY_UNPROVEN")
        nonce = secrets.token_hex(16)
        payload = {
            "schema_version": 1,
            "supervisor_pid": os.getpid(),
            "supervisor_start_utc": self_record.start_utc,
            "owner_nonce": nonce,
            "run_dir": str(run_dir),
            "created_at_utc": utc_now(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(str(self.path), flags, 0o600)
        except FileExistsError as exc:
            raise ProductionRefusal("PHX2_SESSION_ALREADY_ACTIVE") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        except BaseException:
            try:
                self.path.unlink()
            except OSError:
                pass
            raise
        self.owner_nonce = nonce
        return payload

    def release(self) -> None:
        if self.owner_nonce is None:
            return
        lock = read_json(self.path)
        if lock is None or lock.get("owner_nonce") != self.owner_nonce:
            return
        try:
            self.path.unlink()
        except OSError:
            pass


def _default_offline_preflight(config: ProductionConfig) -> bool:
    command = [
        str(config.paths.python_executable),
        "-B",
        "-m",
        "PHX2.free_tier_producer.free_tier_session",
        "--preflight",
        "--env",
        str(config.paths.env_file),
        "--provider-mode",
        "paid_primary",
        "--enable-telegram",
        "--ledger-path",
        str(config.paths.active_ledger),
        "--out-dir",
        str(config.producer_dir),
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            command,
            cwd=config.paths.repo_root,
            capture_output=True,
            text=True,
            timeout=OFFLINE_PREFLIGHT_TIMEOUT_SECONDS,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _validate_paths(config: ProductionConfig) -> None:
    paths = config.paths
    if not paths.repo_root.is_dir() or not (paths.repo_root / "PHX2").is_dir():
        raise ProductionRefusal("REPOSITORY_BINDING_INVALID")
    if not paths.python_executable.is_file():
        raise ProductionRefusal("WORKSPACE_PYTHON_MISSING")
    if not paths.paper_config.is_file():
        raise ProductionRefusal("PAPER_CONFIGURATION_MISSING")
    try:
        from PHX2.paper_trading.config import load_config

        load_config(str(paths.paper_config))
    except Exception as exc:
        raise ProductionRefusal("PAPER_CONFIGURATION_INVALID") from exc
    if not paths.active_ledger.is_file():
        raise ProductionRefusal("ACTIVE_LEDGER_MISSING")
    if not paths.frozen_ledger.is_file():
        raise ProductionRefusal("FROZEN_LEDGER_MISSING")
    if not config.run_dir.is_absolute():
        raise ProductionRefusal("RUN_DIRECTORY_NOT_ABSOLUTE")
    if config.hours <= 0 or config.hours > 168:
        raise ProductionRefusal("RUNTIME_HOURS_OUT_OF_RANGE")


@dataclass
class PreflightState:
    processes: List[ProcessRecord]
    active_ledger: LedgerBaseline
    frozen_ledger: LedgerBaseline


def bounded_preflight(
    config: ProductionConfig,
    *,
    scanner: Optional[ProcessScanner] = None,
    offline_preflight: Callable[[ProductionConfig], bool] = _default_offline_preflight,
) -> PreflightState:
    _validate_paths(config)
    validate_production_environment(config.paths.env_file)
    process_scanner = scanner or ProcessScanner()
    existing_lock = read_json(config.paths.lock_path)
    owner_pid = _int_or_zero(
        existing_lock.get("supervisor_pid") if isinstance(existing_lock, dict) else None
    )
    records = process_scanner.scan(config.run_dir, owner_pid=owner_pid)
    foreign = [
        record
        for record in records
        if record.role not in ("SELF",) and record.pid != os.getpid()
    ]
    if any(record.role == "OLD_PHOENIX" for record in foreign):
        raise ProductionRefusal("OLD_PHOENIX_ACTIVE")
    if isinstance(existing_lock, dict) and any(
        _record_matches_owner(record, existing_lock) for record in foreign
    ):
        raise ProductionRefusal("PHX2_SESSION_ALREADY_ACTIVE")
    if any(
        record.role
        in ("SUPERVISOR", "PRODUCER", "PAPER", "DASHBOARD", "OPERATOR_CONSOLE")
        for record in foreign
    ):
        raise ProductionRefusal("PHX2_RUNTIME_PROCESS_ACTIVE")
    active = ledger_baseline(config.paths.active_ledger)
    frozen = ledger_baseline(config.paths.frozen_ledger)
    if frozen.as_tuple() != EXPECTED_FROZEN_LEDGER:
        raise ProductionRefusal("FROZEN_LEDGER_BASELINE_MISMATCH")
    if config.stop_file.exists():
        raise ProductionRefusal("STALE_STOP_REQUEST_PRESENT")
    if (config.control_dir / "supervisor_final.json").exists():
        raise ProductionRefusal("RUN_DIRECTORY_ALREADY_FINALIZED")
    if not offline_preflight(config):
        raise ProductionRefusal("PRODUCTION_OFFLINE_PREFLIGHT_FAILED")
    return PreflightState(processes=records, active_ledger=active, frozen_ledger=frozen)


def _child_environment() -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )


def build_child_commands(config: ProductionConfig) -> Dict[str, List[str]]:
    python = str(config.paths.python_executable)
    return {
        "producer": [
            python,
            "-B",
            "-m",
            "PHX2.runtime.production_supervisor",
            "--child-role",
            "producer",
            "--run-dir",
            str(config.run_dir),
            "--hours",
            f"{config.hours:g}",
        ],
        "paper": [
            python,
            "-B",
            "-m",
            "PHX2.scripts.phx2_live_paper_trade",
            "--config",
            str(config.paths.paper_config),
            "--inputs",
            str(config.producer_dir),
            "--run-id",
            "paper",
            "--out-root",
            str(config.paper_root),
            "--poll-seconds",
            "5",
            "--max-runtime-seconds",
            f"{config.runtime_seconds + 600:g}",
            "--heartbeat-seconds",
            "60",
            "--stop-file",
            str(config.stop_file),
            "--quiet",
        ],
        "dashboard": [
            python,
            "-B",
            "-m",
            "PHX2.dashboard.server",
            "--host",
            config.paths.dashboard_host,
            "--port",
            str(config.paths.dashboard_port),
            "--producer-dir",
            str(config.producer_dir),
            "--paper-dir",
            str(config.paper_dir),
            "--ledger-path",
            str(config.paths.active_ledger),
            "--stop-file",
            str(config.stop_file),
        ],
    }


def run_producer_child(config: ProductionConfig) -> int:
    """Fail closed: this route never arms and never sends.

    The armed private-live send path is exclusively the three canonical
    PowerShell launchers, which run the tracked module from the repository root
    with the complete production-gRPC contract (``--require-production-grpc`` plus
    a stable ``--cursor-state-dir``).  ``python main.py --hours`` reaches this
    producer child, which previously built an armed vector -- ``--enable-telegram
    --ack-live-free-tier --i-understand-this-can-send --confirm-token <locked>
    --provider-mode paid_primary`` -- and called ``free_tier_session.main`` with
    **neither** the production-gRPC contract **nor** a durable cursor, standing as
    an undocumented fourth armed owner (residual re-audit finding M-2).

    It now refuses outright.  Nothing is read from ``config`` and no session
    module is imported, so the refusal precedes any source, channel, transport,
    writable ledger or cursor construction.  The supervisor's read-only status
    path is unaffected; only the armed producer path is closed.  This route never
    silently delegates to a launcher -- operator arm acknowledgement stays at the
    canonical launcher.
    """
    del config  # nothing is consulted before the refusal
    print(f"[refused] {ARMED_ROUTE_REFUSAL}")
    print("[refused] the armed private-live send path is the three canonical "
          "launchers, and only those:")
    for launcher in CANONICAL_ARMED_LAUNCHERS:
        print(f"[refused]   {launcher}")
    print("[refused] python main.py --hours is a non-arming supervisor; it never "
          "arms and never sends. Run one of the launchers above to send.")
    return 2


@dataclass
class SupervisorResult:
    exit_code: int
    stop_reason: str
    run_dir: Path
    sent_ok_count: int
    active_streams: int
    max_active_streams: int
    forced_termination_count: int


class ProductionSupervisor:
    def __init__(
        self,
        config: ProductionConfig,
        *,
        scanner: Optional[ProcessScanner] = None,
        offline_preflight: Callable[[ProductionConfig], bool] = _default_offline_preflight,
        popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        console_factory: Optional[Callable[[Path], Any]] = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.scanner = scanner or ProcessScanner()
        self.offline_preflight = offline_preflight
        self.popen_factory = popen_factory
        self.console_factory = console_factory
        self.sleep = sleep
        self.monotonic = monotonic
        self.lock = SessionLock(config.paths.lock_path)
        self.processes: Dict[str, subprocess.Popen[Any]] = {}
        self.logs: Dict[str, Any] = {}
        self.forced: List[str] = []
        self.console: Any = None
        self.start_utc = utc_now()
        self.started_monotonic = self.monotonic()
        self.paper_status = "STARTING"
        self.paper_restart_attempts = 0
        self.paper_last_exit_code: Optional[int] = None
        self.paper_restart_due: Optional[float] = None

    @property
    def event_path(self) -> Path:
        return self.config.control_dir / "supervisor_events.jsonl"

    def event(self, event: str, **fields: Any) -> None:
        payload = {
            "kind": "PHX2_SUPERVISOR_EVENT",
            "event": safe_reason(event),
            "at_utc": utc_now(),
            **fields,
        }
        append_jsonl(self.event_path, payload)

    def _prepare_run_directory(self) -> None:
        if self.config.run_dir.exists():
            if not self.config.run_dir.is_dir():
                raise ProductionRefusal("RUN_DIRECTORY_INVALID")
        else:
            self.config.run_dir.mkdir(parents=True, exist_ok=False)
        for path in (
            self.config.control_dir,
            self.config.log_dir,
            self.config.producer_dir,
            self.config.paper_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _write_runtime_config(self, preflight: PreflightState) -> None:
        atomic_json(
            self.config.control_dir / "production_config.json",
            {
                "schema_version": 1,
                "run_dir": str(self.config.run_dir),
                "duration_hours": self.config.hours,
                "provider_mode": "PAID_PRIMARY",
                # Role-based, artifact-safe (2026-07-31 redaction cleanup): the
                # provider PRODUCT name is a scanner danger needle and this
                # document is written into the scanned control directory.
                "market_provider": SOURCE_ROLE_PAID_MARKET_PRIMARY,
                "polling_fallback_enabled": False,
                "delivery_transport": "TELEGRAM",
                "telegram_enabled": True,
                "telegram_token_configured": True,
                "telegram_chat_configured": True,
                "discord_enabled": False,
                "private_discord_enabled": False,
                "primary_max_grpc_streams": PRIMARY_MAX_GRPC_STREAMS,
                "verifier_max_grpc_streams": VERIFIER_MAX_GRPC_STREAMS,
                "max_grpc_streams": MAX_GRPC_STREAMS,
                "lp_integrity_mode": LP_INTEGRITY_MODE,
                "verifier_stream_status": VERIFIER_STREAM_STATUS_DISABLED,
                "migration_activation_multiplier": format(
                    self.config.migration_activation_multiplier, "f"),
                "dashboard_host": self.config.paths.dashboard_host,
                "dashboard_loopback_only": True,
                "paper_simulation_only": True,
                "active_ledger": str(self.config.paths.active_ledger),
                "active_ledger_baseline": preflight.active_ledger.as_token(),
                "frozen_ledger": str(self.config.paths.frozen_ledger),
                "frozen_ledger_baseline": preflight.frozen_ledger.as_token(),
                "created_at_utc": utc_now(),
            },
        )

    def _start_console(self) -> None:
        if self.console_factory is None:
            from PHX2.observability.operator_console import OperatorConsole

            self.console = OperatorConsole(self.config.run_dir)
        else:
            self.console = self.console_factory(self.config.run_dir)
        self.console.start_background()

    def _registry_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "run_dir": str(self.config.run_dir),
            "start_utc": self.start_utc,
            "supervisor_pid": os.getpid(),
            "operator_console": {
                "mode": "IN_PROCESS_READ_ONLY",
                "pid": os.getpid(),
                "state": "RUNNING" if self.console is not None else "STARTING",
            },
            "paper_child": {
                "status": self.paper_status,
                "restart_attempts": self.paper_restart_attempts,
                "restart_limit": PAPER_RESTART_MAX_ATTEMPTS,
                "last_exit_code": self.paper_last_exit_code,
            },
            "processes": {
                name: {
                    "pid": process.pid,
                    "state": "RUNNING" if process.poll() is None else "EXITED",
                    "exit_code": process.poll(),
                }
                for name, process in self.processes.items()
            },
        }

    def _write_registry(self) -> None:
        atomic_json(self.config.control_dir / "processes.json", self._registry_payload())

    def _launch(self, name: str, command: Sequence[str]) -> None:
        self._close_log(name)
        log = (self.config.log_dir / f"{name}.log").open(
            "a", encoding="utf-8", buffering=1
        )
        self.logs[name] = log
        process = self.popen_factory(
            list(command),
            cwd=self.config.paths.repo_root,
            env=_child_environment(),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=_creation_flags(),
        )
        self.processes[name] = process
        self.event("CHILD_STARTED", role=name.upper(), pid=process.pid)
        self._write_registry()

    def _close_log(self, name: str) -> None:
        log = self.logs.pop(name, None)
        if log is None:
            return
        try:
            log.close()
        except OSError:
            pass

    def _set_paper_degraded(self, reason: str) -> None:
        self.paper_status = "DEGRADED"
        self.paper_restart_due = None
        self.event(
            "PAPER_DEGRADED",
            reason=safe_reason(reason, "PAPER_RESTARTS_EXHAUSTED"),
            restart_attempts=self.paper_restart_attempts,
            restart_limit=PAPER_RESTART_MAX_ATTEMPTS,
        )
        self._write_registry()

    def _schedule_paper_restart(self) -> None:
        if self.paper_restart_attempts >= PAPER_RESTART_MAX_ATTEMPTS:
            self._set_paper_degraded("PAPER_RESTARTS_EXHAUSTED")
            return
        delay = PAPER_RESTART_BACKOFF_SECONDS[self.paper_restart_attempts]
        self.paper_status = "RESTART_PENDING"
        self.paper_restart_due = self.monotonic() + delay
        self.event(
            "PAPER_CHILD_RESTART_SCHEDULED",
            attempt=self.paper_restart_attempts + 1,
            restart_limit=PAPER_RESTART_MAX_ATTEMPTS,
            backoff_seconds=delay,
        )
        self._write_registry()

    def _record_paper_failure(
        self,
        process: Optional[subprocess.Popen[Any]],
        *,
        error_category: str,
    ) -> None:
        exit_code = process.poll() if process is not None else None
        self.paper_last_exit_code = exit_code
        self.event(
            "PAPER_CHILD_FAILED",
            exit_code=exit_code,
            error_category=safe_reason(error_category, "PAPER_PROCESS_FAILURE"),
            restart_attempts=self.paper_restart_attempts,
            restart_limit=PAPER_RESTART_MAX_ATTEMPTS,
        )
        if process is not None:
            try:
                process.wait(timeout=0.0)
            except (OSError, subprocess.TimeoutExpired):
                self._set_paper_degraded("PAPER_RECONCILE_FAILED")
                return
            self.event(
                "PAPER_CHILD_RECONCILED",
                exit_code=process.poll(),
                restart_attempts=self.paper_restart_attempts,
            )
        self._close_log("paper")
        self._schedule_paper_restart()

    def _launch_initial_paper(self, command: Sequence[str]) -> None:
        try:
            self._launch("paper", command)
        except OSError:
            self._close_log("paper")
            self._record_paper_failure(None, error_category="LAUNCH_ERROR")
            return
        self.sleep(0.25)
        process = self.processes["paper"]
        if process.poll() is not None:
            self._record_paper_failure(process, error_category="PROCESS_EXIT")
            return
        self.paper_status = "RUNNING"
        self._write_registry()

    def _restart_paper_if_due(
        self, command: Sequence[str]
    ) -> None:
        if (
            self.paper_status != "RESTART_PENDING"
            or self.paper_restart_due is None
            or self.monotonic() < self.paper_restart_due
        ):
            return
        self.paper_restart_attempts += 1
        self.paper_status = "RESTARTING"
        self.paper_restart_due = None
        self.event(
            "PAPER_CHILD_RESTART_ATTEMPT",
            attempt=self.paper_restart_attempts,
            restart_limit=PAPER_RESTART_MAX_ATTEMPTS,
        )
        try:
            self._launch("paper", command)
        except OSError:
            self._close_log("paper")
            self._record_paper_failure(None, error_category="RESTART_LAUNCH_ERROR")
            return
        self.sleep(0.25)
        process = self.processes["paper"]
        if process.poll() is not None:
            self._record_paper_failure(process, error_category="RESTART_PROCESS_EXIT")
            return
        self.paper_status = "RUNNING"
        self.event(
            "PAPER_CHILD_RESTARTED",
            pid=process.pid,
            attempt=self.paper_restart_attempts,
        )
        self._write_registry()

    def _wait(self, process: subprocess.Popen[Any], timeout: float) -> bool:
        try:
            process.wait(timeout=max(0.0, float(timeout)))
            return True
        except subprocess.TimeoutExpired:
            return False

    def _cooperative_stop(self, name: str, timeout: float) -> None:
        process = self.processes.get(name)
        if process is None or process.poll() is not None:
            return
        if self._wait(process, timeout):
            self.event("CHILD_STOPPED", role=name.upper(), exit_code=process.poll())
            return
        signaled = False
        if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                signaled = True
            except (OSError, ValueError):
                signaled = False
        elif os.name != "nt":
            try:
                process.send_signal(signal.SIGINT)
                signaled = True
            except (OSError, ValueError):
                signaled = False
        if signaled and self._wait(process, COOPERATIVE_CHILD_TIMEOUT_SECONDS):
            self.event("CHILD_STOPPED", role=name.upper(), exit_code=process.poll())
            return
        self.forced.append(name)
        self.event("FORCED_TERMINATION", role=name.upper(), pid=process.pid)
        try:
            process.terminate()
        except OSError:
            pass
        if not self._wait(process, FORCE_TIMEOUT_SECONDS):
            try:
                process.kill()
            except OSError:
                pass
            self._wait(process, FORCE_TIMEOUT_SECONDS)

    def _force_run_orphans(self) -> None:
        try:
            records = self.scanner.scan(self.config.run_dir)
        except ProcessEnumerationError:
            self.event("FINAL_PROCESS_ENUMERATION_FAILED")
            raise
        orphans = [
            record
            for record in records
            if record.pid != os.getpid()
            and record.run_dir == str(self.config.run_dir)
            and record.role
            in ("PRODUCER", "PAPER", "DASHBOARD", "OPERATOR_CONSOLE")
        ]
        for record in orphans:
            label = f"{record.role.lower()}:{record.pid}"
            self.forced.append(label)
            self.event("FORCED_TERMINATION", role=record.role, pid=record.pid)
            if os.name == "nt":
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                try:
                    subprocess.run(
                        ["taskkill.exe", "/PID", str(record.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=FORCE_TIMEOUT_SECONDS,
                        creationflags=flags,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass
            else:
                try:
                    os.kill(record.pid, signal.SIGKILL)
                except OSError:
                    pass
        final_records = self.scanner.scan(self.config.run_dir)
        if any(
            record.pid != os.getpid()
            and record.run_dir == str(self.config.run_dir)
            for record in final_records
        ):
            raise ProductionRefusal("ORPHAN_PROCESS_REMAINS")

    def _terminal_provider_state(self) -> tuple[int, int, int, str]:
        summary = read_json(self.config.producer_dir / "producer_summary.json") or {}
        telemetry = summary.get("provider_telemetry")
        telemetry = telemetry if isinstance(telemetry, dict) else {}
        budget = summary.get("credit_budget")
        budget = budget if isinstance(budget, dict) else {}
        return (
            int(telemetry.get("total_active_streams")
                if telemetry.get("total_active_streams") is not None
                else telemetry.get("active_streams") or 0),
            int(telemetry.get("total_max_active_streams")
                if telemetry.get("total_max_active_streams") is not None
                else telemetry.get("max_active_streams") or 0),
            int(budget.get("sent_ok_count") or 0),
            safe_reason(summary.get("stop_reason"), "PRODUCER_STOPPED"),
        )

    def _verify_final_safety(
        self, preflight: PreflightState
    ) -> tuple[int, int, int, Optional[str]]:
        active_streams, maximum_streams, sent_ok, _ = self._terminal_provider_state()
        if active_streams != 0:
            return active_streams, maximum_streams, sent_ok, "ACTIVE_STREAMS_NONZERO"
        summary = read_json(self.config.producer_dir / "producer_summary.json") or {}
        telemetry = summary.get("provider_telemetry")
        telemetry = telemetry if isinstance(telemetry, dict) else {}
        if (int(telemetry.get("primary_max_active_streams")
                if telemetry.get("primary_max_active_streams") is not None
                else telemetry.get("max_active_streams") or 0) > PRIMARY_MAX_GRPC_STREAMS
                or int(telemetry.get("verifier_max_active_streams") or 0)
                > VERIFIER_MAX_GRPC_STREAMS
                or maximum_streams > MAX_GRPC_STREAMS):
            return active_streams, maximum_streams, sent_ok, "GRPC_STREAM_OVERLAP"
        frozen_after = ledger_baseline(self.config.paths.frozen_ledger)
        if frozen_after != preflight.frozen_ledger:
            return active_streams, maximum_streams, sent_ok, "FROZEN_LEDGER_CHANGED"
        active_after = ledger_baseline(self.config.paths.active_ledger)
        line_delta = active_after.line_count - preflight.active_ledger.line_count
        if line_delta != sent_ok:
            return active_streams, maximum_streams, sent_ok, "ACTIVE_LEDGER_SENT_OK_MISMATCH"
        return active_streams, maximum_streams, sent_ok, None

    def _close_logs(self) -> None:
        for name in list(self.logs):
            self._close_log(name)

    def run(self) -> SupervisorResult:
        preflight = bounded_preflight(
            self.config,
            scanner=self.scanner,
            offline_preflight=self.offline_preflight,
        )
        self.lock.acquire(run_dir=self.config.run_dir, records=preflight.processes)
        stop_reason = "SUPERVISOR_EXCEPTION"
        violation: Optional[str] = None
        active_streams = 0
        maximum_streams = 0
        sent_ok = 0
        try:
            self._prepare_run_directory()
            self._write_runtime_config(preflight)
            self.event("SESSION_STARTING", run_dir=str(self.config.run_dir))
            self.event("SUPERVISOR_STARTED", pid=os.getpid())
            self._start_console()
            self.event("OPERATOR_CONSOLE_STARTED", mode="IN_PROCESS_READ_ONLY")
            commands = build_child_commands(self.config)
            self._launch("producer", commands["producer"])
            self.sleep(0.25)
            if self.processes["producer"].poll() is not None:
                raise ProductionRefusal("PRODUCER_START_FAILURE")
            self._launch_initial_paper(commands["paper"])
            self._launch("dashboard", commands["dashboard"])
            self.sleep(0.25)
            if self.processes["dashboard"].poll() is not None:
                raise ProductionRefusal("DASHBOARD_START_FAILURE")
            deadline = self.started_monotonic + self.config.runtime_seconds + 120.0
            while True:
                producer = self.processes["producer"]
                producer_code = producer.poll()
                if producer_code is not None:
                    _, _, _, producer_reason = self._terminal_provider_state()
                    stop_reason = producer_reason
                    if producer_code != 0:
                        violation = "PRODUCER_PROCESS_FAILURE"
                    break
                if self.processes["dashboard"].poll() is not None:
                    stop_reason = "CHILD_EXIT_UNEXPECTED"
                    violation = "CHILD_EXIT_UNEXPECTED"
                    self.event(
                        "CHILD_EXIT_UNEXPECTED",
                        role="DASHBOARD",
                        exit_code=self.processes["dashboard"].poll(),
                    )
                    break
                paper = self.processes.get("paper")
                if (
                    self.paper_status == "RUNNING"
                    and paper is not None
                    and paper.poll() is not None
                ):
                    self._record_paper_failure(paper, error_category="PROCESS_EXIT")
                self._restart_paper_if_due(commands["paper"])
                if self.monotonic() >= deadline:
                    stop_reason = "SUPERVISOR_RUNTIME_BOUNDARY"
                    break
                self._write_registry()
                self.sleep(1.0)
        except KeyboardInterrupt:
            stop_reason = "OPERATOR_REQUESTED"
            self.event("OPERATOR_SHUTDOWN_REQUESTED")
        except ProductionRefusal as exc:
            stop_reason = exc.reason
            violation = exc.reason
            self.event("SUPERVISOR_REFUSAL", reason=exc.reason)
        except BaseException as exc:
            stop_reason = "SUPERVISOR_EXCEPTION"
            violation = "SUPERVISOR_EXCEPTION"
            self.event("SUPERVISOR_EXCEPTION", error_class=type(exc).__name__)
        finally:
            if self.config.control_dir.exists():
                self.config.stop_file.touch(exist_ok=True)
                self.event("COOPERATIVE_SHUTDOWN_REQUESTED", reason=stop_reason)
            self._cooperative_stop("producer", COOPERATIVE_PRODUCER_TIMEOUT_SECONDS)
            self._cooperative_stop("paper", COOPERATIVE_CHILD_TIMEOUT_SECONDS)
            self._cooperative_stop("dashboard", COOPERATIVE_CHILD_TIMEOUT_SECONDS)
            try:
                self._force_run_orphans()
            except ProductionRefusal as exc:
                violation = violation or exc.reason
            try:
                active_streams, maximum_streams, sent_ok, final_violation = (
                    self._verify_final_safety(preflight)
                )
                violation = violation or final_violation
            except ProductionRefusal as exc:
                violation = violation or exc.reason
            if self.console is not None:
                self.event("OPERATOR_CONSOLE_STOPPING")
                self.console.stop_background()
            final_paper_status = (
                "DEGRADED" if self.paper_status == "DEGRADED" else "STOPPED"
            )
            final = {
                "schema_version": 1,
                "start_utc": self.start_utc,
                "end_utc": utc_now(),
                "runtime_seconds": round(
                    max(0.0, self.monotonic() - self.started_monotonic), 3
                ),
                "stop_reason": stop_reason,
                "safety_violation": violation,
                "forced_termination_processes": sorted(set(self.forced)),
                "forced_termination_count": len(set(self.forced)),
                "process_exit_codes": {
                    name: process.poll() for name, process in self.processes.items()
                },
                "sent_ok_count": sent_ok,
                "active_streams": active_streams,
                "max_active_streams": maximum_streams,
                "paper_status": final_paper_status,
                "paper_restart_attempts": self.paper_restart_attempts,
                "paper_restart_limit": PAPER_RESTART_MAX_ATTEMPTS,
                "paper_last_exit_code": self.paper_last_exit_code,
                "run_dir": str(self.config.run_dir),
            }
            if self.config.control_dir.exists():
                atomic_json(self.config.control_dir / "supervisor_final.json", final)
            self._close_logs()
            self.lock.release()
        exit_code = 0 if violation is None and not self.forced else 2
        return SupervisorResult(
            exit_code=exit_code,
            stop_reason=stop_reason,
            run_dir=self.config.run_dir,
            sent_ok_count=sent_ok,
            active_streams=active_streams,
            max_active_streams=maximum_streams,
            forced_termination_count=len(set(self.forced)),
        )


def read_status(
    paths: ProductionPaths,
    *,
    run_dir: Optional[Path] = None,
    scanner: Optional[ProcessScanner] = None,
) -> Dict[str, Any]:
    """Read status without creating, cleaning, or modifying any state."""
    process_scanner = scanner or ProcessScanner()
    lock = read_json(paths.lock_path)
    owner_pid = _int_or_zero(lock.get("supervisor_pid") if lock else None)
    records = process_scanner.scan(run_dir, owner_pid=owner_pid)
    lock_active = bool(
        lock and any(_record_matches_owner(record, lock) for record in records)
    )
    selected = run_dir
    if selected is None and lock and isinstance(lock.get("run_dir"), str):
        selected = Path(lock["run_dir"])
    if selected is None:
        try:
            candidates = sorted(
                (path for path in paths.runtime_root.glob("phx2_live_*") if path.is_dir()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            candidates = []
        for candidate in candidates:
            candidate_registry = read_json(candidate / "control" / "processes.json")
            if candidate_registry and candidate_registry.get("schema_version") == 1:
                selected = candidate
                break
    registry = read_json(selected / "control" / "processes.json") if selected else None
    final = read_json(selected / "control" / "supervisor_final.json") if selected else None
    heartbeat_path = selected / "producer" / "producer_heartbeat.json" if selected else None
    summary_path = selected / "producer" / "producer_summary.json" if selected else None
    heartbeat = read_json(heartbeat_path) if heartbeat_path else None
    summary = read_json(summary_path) if summary_path else None
    runtime_config = (
        read_json(selected / "control" / "production_config.json") if selected else None)
    source = heartbeat if lock_active and heartbeat else (summary or heartbeat or {})
    market_scheduler = source.get("market_scheduler")
    market_scheduler = market_scheduler if isinstance(market_scheduler, dict) else {}
    provider = source.get("provider_telemetry")
    provider = provider if isinstance(provider, dict) else {}
    budget = source.get("credit_budget")
    budget = budget if isinstance(budget, dict) else {}
    security = provider.get("security_filters")
    security = security if isinstance(security, dict) else {}
    fee_lifecycle = provider.get("fee_lifecycle")
    fee_lifecycle = fee_lifecycle if isinstance(fee_lifecycle, dict) else {}
    primary = provider.get("primary")
    primary = primary if isinstance(primary, dict) else {}
    verifier = provider.get("verifier")
    verifier = verifier if isinstance(verifier, dict) else {}
    telegram_records = (
        read_jsonl(selected / "producer" / "telegram_attempts.jsonl")
        if selected else [])
    telegram_sent = sum(
        1 for record in telegram_records
        if record.get("result") == "SENT_OK"
        and isinstance(record.get("message_id"), int)
        and not isinstance(record.get("message_id"), bool))
    process_states: Dict[str, Dict[str, Any]] = {}
    registry_processes = registry.get("processes") if isinstance(registry, dict) else {}
    registry_processes = registry_processes if isinstance(registry_processes, dict) else {}
    live_by_pid = {record.pid: record for record in records}
    for role in ("producer", "paper", "dashboard"):
        entry = registry_processes.get(role)
        if isinstance(entry, dict):
            pid = int(entry.get("pid") or 0)
        else:
            pid = int(entry or 0) if entry else 0
        live_record = live_by_pid.get(pid)
        process_states[role] = {
            "pid": pid or None,
            "state": (
                "RUNNING"
                if live_record is not None and live_record.role == role.upper()
                else "EXITED"
            ),
        }
    registered_console = (
        (registry or {}).get("operator_console")
        if isinstance(registry, dict) else None
    )
    registered_console = (
        registered_console if isinstance(registered_console, dict) else {})
    console_pid = int(registered_console.get("pid") or 0)
    console_state = (
        "RUNNING"
        if lock_active and console_pid == int(lock.get("supervisor_pid") or 0)
        else "EXITED"
    )
    registered_paper = (
        (registry or {}).get("paper_child")
        if isinstance(registry, dict) else None
    )
    registered_paper = registered_paper if isinstance(registered_paper, dict) else {}
    if not lock_active and isinstance(final, dict):
        paper_status = final.get("paper_status")
        paper_restart_attempts = final.get("paper_restart_attempts")
        paper_restart_limit = final.get("paper_restart_limit")
        paper_last_exit_code = final.get("paper_last_exit_code")
    else:
        paper_status = registered_paper.get("status")
        paper_restart_attempts = registered_paper.get("restart_attempts")
        paper_restart_limit = registered_paper.get("restart_limit")
        paper_last_exit_code = registered_paper.get("last_exit_code")
    if not paper_status:
        paper_status = process_states["paper"]["state"]
    heartbeat_age: Optional[float] = None
    if heartbeat_path and heartbeat_path.is_file():
        try:
            heartbeat_age = round(max(0.0, time.time() - heartbeat_path.stat().st_mtime), 1)
        except OSError:
            heartbeat_age = None
    return {
        "active": lock_active,
        "lock_state": "ACTIVE" if lock_active else ("STALE" if lock else "ABSENT"),
        "run_dir": str(selected) if selected else None,
        "supervisor_pid": int(lock.get("supervisor_pid") or 0) if lock else None,
        "processes": process_states,
        "operator_console": {
            **registered_console,
            "pid": console_pid or None,
            "state": console_state,
        },
        "paper_status": paper_status,
        "paper_restart_attempts": int(paper_restart_attempts or 0),
        "paper_restart_limit": int(
            paper_restart_limit or PAPER_RESTART_MAX_ATTEMPTS
        ),
        "paper_last_exit_code": paper_last_exit_code,
        # Overall gRPC health is the PRIMARY stream's health: with the
        # verifier removed there is no second connection to fold in, so gRPC
        # is CONNECTED exactly when the one primary stream is healthy.
        "grpc_status": (
            provider.get("primary_stream_status")
            or primary.get("status")
            or provider.get("status")),
        "delivery_transport": (
            (runtime_config or {}).get("delivery_transport")
            or source.get("delivery_transport")),
        "telegram_configured": bool(
            (runtime_config or {}).get("telegram_enabled") is True
            and (runtime_config or {}).get("telegram_token_configured") is True
            and (runtime_config or {}).get("telegram_chat_configured") is True),
        "telegram_attempts": len(telegram_records),
        "telegram_sent_ok": telegram_sent,
        "telegram_failures": max(0, len(telegram_records) - telegram_sent),
        "discord_attempts": 0,
        "primary_stream_status": primary.get("status") or provider.get("status"),
        "verifier_stream_status": (
            provider.get("verifier_stream_status")
            or verifier.get("status")
            or VERIFIER_STREAM_STATUS_DISABLED),
        "lp_integrity_mode": (
            (runtime_config or {}).get("lp_integrity_mode")
            or provider.get("lp_integrity_mode")
            or source.get("lp_integrity_mode")
            or LP_INTEGRITY_MODE),
        "active_streams": int(provider.get("total_active_streams")
                              if provider.get("total_active_streams") is not None
                              else provider.get("active_streams") or 0),
        "max_active_streams": int(
            (runtime_config or {}).get("max_grpc_streams")
            if isinstance((runtime_config or {}).get("max_grpc_streams"), int)
            else provider.get("total_max_active_streams")
            if provider.get("total_max_active_streams") is not None
            else provider.get("max_active_streams") or 0),
        "primary_active_streams": int(provider.get("primary_active_streams")
                                      if provider.get("primary_active_streams") is not None
                                      else provider.get("active_streams") or 0),
        "verifier_active_streams": int(provider.get("verifier_active_streams") or 0),
        "total_active_streams": int(provider.get("total_active_streams")
                                    if provider.get("total_active_streams") is not None
                                    else provider.get("active_streams") or 0),
        "accepted_candidates": int(provider.get("candidates_accepted") or 0),
        "queue_depth": int(provider.get("queue_depth") or 0),
        "migration_admission_counts": (
            provider.get("migration_admission")
            if isinstance(provider.get("migration_admission"), dict) else {}),
        "pipeline_counters": (
            provider.get("pipeline_counters")
            if isinstance(provider.get("pipeline_counters"), dict)
            else source.get("pipeline_counters")
            if isinstance(source.get("pipeline_counters"), dict) else {}),
        # WATCHLIST_COUNT is explicitly the active/tracked count. Terminal
        # history and capacity rejections are separate observability counts
        # and are never folded back into the tracked number (PHX2-E2E-002).
        "watchlist_count": int(
            source.get("watchlist_count")
            if source.get("watchlist_count") is not None
            else source.get("watchlist_tracked")
            if source.get("watchlist_tracked") is not None
            else source.get("watchlist_active") or 0),
        "watchlist_active_capacity": int(
            source.get("watchlist_active_capacity") or 0),
        "watchlist_terminal_history": int(
            source.get("watchlist_terminal_history_total") or 0),
        "watchlist_capacity_rejections": int(
            source.get("watchlist_capacity_rejections") or 0),
        "market_calls": int(source.get("market_calls_total") or source.get("market_calls") or 0),
        "market_scheduler": market_scheduler,
        "send_attempts": int(budget.get("send_attempts") or 0),
        "sent_ok_count": int(budget.get("sent_ok_count") or 0),
        "fee_gate_counts": {
            "scam_likely": int(security.get("fee_scam_likely") or 0),
            "suspicious": int(security.get("fee_suspicious") or 0),
            "pass": int(security.get("fee_pass") or 0),
            "unknown": int(security.get("fee_unknown") or 0),
        },
        "fee_lifecycle_counts": {
            "immature": int(fee_lifecycle.get("fee_gate_immature") or 0),
            "fresh_provisional": int(
                fee_lifecycle.get("fee_gate_fresh_provisional") or 0),
            "fresh_confirmed": int(
                fee_lifecycle.get("fee_gate_fresh_confirmed") or 0),
            "temporarily_stale": int(
                fee_lifecycle.get("fee_gate_temporarily_stale") or 0),
            "durable_scam_locked": int(
                fee_lifecycle.get("fee_gate_durable_scam_locked") or 0),
            "recovered_from_stale": int(
                fee_lifecycle.get("fee_gate_recovered_from_stale") or 0),
            "provisional_scam_recovered": int(
                fee_lifecycle.get("fee_gate_provisional_scam_recovered") or 0),
            "send_time_stale_blocks": int(
                fee_lifecycle.get("fee_gate_send_time_stale_blocks") or 0),
            "send_time_scam_blocks": int(
                fee_lifecycle.get("fee_gate_send_time_scam_blocks") or 0),
        },
        "lp_integrity_counts": {
            "pass": int(security.get("lp_pass") or 0),
            "warn": int(security.get("lp_warn") or 0),
            "fail": int(security.get("lp_fail") or 0),
            "unknown": int(security.get("lp_unknown") or 0),
        },
        "composite_blocks": int(security.get("blocked_composite") or 0),
        "latest_heartbeat_age_s": heartbeat_age,
        "stop_reason": (
            (final or {}).get("stop_reason")
            or source.get("stop_reason")
            or (
                "STOP_REQUESTED"
                if selected and (selected / "control" / "STOP_REQUESTED").exists()
                else None
            )
            or None
        ),
    }


def child_main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--child-role", choices=("producer",), required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    args = parser.parse_args(argv)
    config = ProductionConfig(run_dir=args.run_dir, hours=args.hours)
    return run_producer_child(config)


if __name__ == "__main__":
    raise SystemExit(child_main())


__all__ = (
    "ARMED_ROUTE_REFUSAL",
    "CANONICAL_ARMED_LAUNCHERS",
    "DEFAULT_HOURS",
    "EXPECTED_FROZEN_LEDGER",
    "PRIMARY_MAX_GRPC_STREAMS",
    "VERIFIER_MAX_GRPC_STREAMS",
    "MAX_GRPC_STREAMS",
    "LP_INTEGRITY_MODE",
    "VERIFIER_STREAM_STATUS_DISABLED",
    "LedgerBaseline",
    "PreflightState",
    "ProcessEnumerationError",
    "ProcessRecord",
    "ProcessScanner",
    "ProductionConfig",
    "ProductionPaths",
    "ProductionRefusal",
    "ProductionSupervisor",
    "SessionLock",
    "SupervisorResult",
    "bounded_preflight",
    "build_child_commands",
    "fresh_run_dir",
    "ledger_baseline",
    "read_status",
    "run_producer_child",
    "validate_production_environment",
)
