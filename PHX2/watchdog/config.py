"""Watchdog configuration and its fail-closed schema.

Every threshold the watchdog acts on lives here, is bounded, and is validated
before the daemon does anything at all.  An invalid configuration is a REFUSAL,
never a clamp: a watchdog that silently repaired a nonsense restart budget would
be exactly the uncontrolled restart controller Stage 10 exists to prevent.

Nothing in this module reads an environment file, opens a socket, touches a
credential or starts a process.  It resolves paths and validates numbers, so the
whole configuration is checkable offline.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_CURSOR_STATE_DIR,
    CANONICAL_LEDGER_PATH,
    CANONICAL_LOGS_ROOT,
    CANONICAL_RUNS_ROOT,
    REPO_PYTHON,
    REPO_ROOT,
    path_is_ephemeral,
    path_is_forbidden,
)
from PHX2.free_tier_producer.phx1_parity_policy import (
    normalize_alert_policy,
)

WATCHDOG_CONFIG_SCHEMA_V1 = "PHX2_WATCHDOG_CONFIG_V1"

#: The one external launcher the watchdog is allowed to start.  The watchdog
#: does NOT reconstruct the producer argument list; the launcher owns it.
CANONICAL_LIVE_LAUNCHER_DIR = r"C:\Users\BalaC\phx2_production_private_live"
CANONICAL_LIVE_LAUNCHER_BASENAME = "launch_live_24x7.ps1"
CANONICAL_LIVE_LAUNCHER_PATH = str(
    Path(CANONICAL_LIVE_LAUNCHER_DIR) / CANONICAL_LIVE_LAUNCHER_BASENAME)

#: External watchdog state root.  Deliberately OUTSIDE the repository (it is
#: runtime state, never tracked) and outside every producer-owned tree, so the
#: watchdog cannot write into durable producer state even by accident.
DEFAULT_WATCHDOG_STATE_ROOT = r"C:\Users\BalaC\phx2_watchdog"

#: Routes that must never be reachable from the watchdog. Kept as data so a test
#: can assert the watchdog source never names them.
CLOSED_ARMED_ROUTES = (
    "PHX2.runtime.production_supervisor",
    "PHX2/main.py",
    "main.py --hours",
)

# --------------------------------------------------------------------------- #
# closed-set refusal reasons
# --------------------------------------------------------------------------- #

REFUSAL_SCHEMA_VERSION = "WATCHDOG_CONFIG_SCHEMA_VERSION_UNSUPPORTED"
REFUSAL_REPO_ROOT = "WATCHDOG_CONFIG_REPO_ROOT_INVALID"
REFUSAL_REPO_PYTHON = "WATCHDOG_CONFIG_REPO_PYTHON_INVALID"
REFUSAL_LAUNCHER_PATH = "WATCHDOG_CONFIG_LAUNCHER_PATH_NOT_CANONICAL"
REFUSAL_EXPECTED_HEAD = "WATCHDOG_CONFIG_EXPECTED_HEAD_MALFORMED"
REFUSAL_STATE_ROOT_FORBIDDEN = "WATCHDOG_CONFIG_STATE_ROOT_FORBIDDEN"
REFUSAL_STATE_ROOT_EPHEMERAL = "WATCHDOG_CONFIG_STATE_ROOT_EPHEMERAL"
REFUSAL_STATE_ROOT_INSIDE_PRODUCER_STATE = (
    "WATCHDOG_CONFIG_STATE_ROOT_INSIDE_PRODUCER_STATE")
REFUSAL_CURSOR_STATE_DIR = "WATCHDOG_CONFIG_CURSOR_STATE_DIR_NOT_CANONICAL"
REFUSAL_LEDGER_PATH = "WATCHDOG_CONFIG_LEDGER_PATH_NOT_CANONICAL"
REFUSAL_POLL_INTERVAL = "WATCHDOG_CONFIG_POLL_INTERVAL_OUT_OF_RANGE"
REFUSAL_STARTUP_GRACE = "WATCHDOG_CONFIG_STARTUP_GRACE_OUT_OF_RANGE"
REFUSAL_HEARTBEAT_MAX_AGE = "WATCHDOG_CONFIG_HEARTBEAT_MAX_AGE_OUT_OF_RANGE"
REFUSAL_HEARTBEAT_BELOW_CADENCE = (
    "WATCHDOG_CONFIG_HEARTBEAT_MAX_AGE_BELOW_PRODUCER_CADENCE")
REFUSAL_RECOVERY_STALL = "WATCHDOG_CONFIG_RECOVERY_STALL_OUT_OF_RANGE"
REFUSAL_COOPERATIVE_STOP = "WATCHDOG_CONFIG_COOPERATIVE_STOP_OUT_OF_RANGE"
REFUSAL_FORCE_GRACE = "WATCHDOG_CONFIG_FORCE_GRACE_OUT_OF_RANGE"
REFUSAL_BACKOFF_EMPTY = "WATCHDOG_CONFIG_BACKOFF_EMPTY"
REFUSAL_BACKOFF_NOT_ASCENDING = "WATCHDOG_CONFIG_BACKOFF_NOT_ASCENDING"
REFUSAL_BACKOFF_OUT_OF_RANGE = "WATCHDOG_CONFIG_BACKOFF_OUT_OF_RANGE"
REFUSAL_JITTER = "WATCHDOG_CONFIG_JITTER_OUT_OF_RANGE"
REFUSAL_CIRCUIT_MAX_RESTARTS = "WATCHDOG_CONFIG_CIRCUIT_MAX_RESTARTS_OUT_OF_RANGE"
REFUSAL_CIRCUIT_WINDOW = "WATCHDOG_CONFIG_CIRCUIT_WINDOW_OUT_OF_RANGE"
REFUSAL_STABLE_RESET = "WATCHDOG_CONFIG_STABLE_RESET_OUT_OF_RANGE"
REFUSAL_TASK_NAME = "WATCHDOG_CONFIG_TASK_NAME_INVALID"

WATCHDOG_CONFIG_REFUSAL_REASONS = (
    REFUSAL_SCHEMA_VERSION,
    REFUSAL_REPO_ROOT,
    REFUSAL_REPO_PYTHON,
    REFUSAL_LAUNCHER_PATH,
    REFUSAL_EXPECTED_HEAD,
    REFUSAL_STATE_ROOT_FORBIDDEN,
    REFUSAL_STATE_ROOT_EPHEMERAL,
    REFUSAL_STATE_ROOT_INSIDE_PRODUCER_STATE,
    REFUSAL_CURSOR_STATE_DIR,
    REFUSAL_LEDGER_PATH,
    REFUSAL_POLL_INTERVAL,
    REFUSAL_STARTUP_GRACE,
    REFUSAL_HEARTBEAT_MAX_AGE,
    REFUSAL_HEARTBEAT_BELOW_CADENCE,
    REFUSAL_RECOVERY_STALL,
    REFUSAL_COOPERATIVE_STOP,
    REFUSAL_FORCE_GRACE,
    REFUSAL_BACKOFF_EMPTY,
    REFUSAL_BACKOFF_NOT_ASCENDING,
    REFUSAL_BACKOFF_OUT_OF_RANGE,
    REFUSAL_JITTER,
    REFUSAL_CIRCUIT_MAX_RESTARTS,
    REFUSAL_CIRCUIT_WINDOW,
    REFUSAL_STABLE_RESET,
    REFUSAL_TASK_NAME,
)

# --------------------------------------------------------------------------- #
# measured producer facts the thresholds are derived from
# --------------------------------------------------------------------------- #

#: The producer emits one heartbeat per watch tick, and the canonical launcher
#: leaves ``--recheck-interval-seconds`` at its 45 s default.  Measured on run
#: ``paid_primary_soak_02h_01_20260726T025158Z``: 12 heartbeats, inter-heartbeat
#: gap median 45.000 s / max 46.000 s, first heartbeat 45 s after process start.
#: Every heartbeat threshold below is stated as a MULTIPLE of this so a future
#: cadence change cannot silently make the watchdog trigger-happy.
PRODUCER_HEARTBEAT_CADENCE_SECONDS = 45.0

#: A stale-heartbeat verdict must survive several ordinary ticks.  4x cadence
#: plus one whole cadence of slack.
DEFAULT_HEARTBEAT_MAX_AGE_SECONDS = 240.0

#: First heartbeat was measured at 45 s; the producer additionally loads and
#: authenticates four checkpoint documents before its first tick, and a cold
#: provider connect adds more.  300 s is ~6.6x the measured value.
DEFAULT_STARTUP_GRACE_SECONDS = 300.0

#: An unresolved recovery episode may legitimately PAUSE between bounded resume
#: attempts, so "no measurable progress" only becomes a verdict after a window
#: that comfortably exceeds ordinary pause/backoff behaviour.
DEFAULT_RECOVERY_STALL_SECONDS = 1800.0

DEFAULT_RESTART_BACKOFF_SECONDS: Tuple[float, ...] = (
    10.0, 30.0, 60.0, 300.0, 900.0)

DEFAULT_TASK_NAME = "PHX2-Watchdog"

_HEX = set("0123456789abcdef")


def _is_commit_sha(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 40 and all(ch in _HEX for ch in text)


def _same_path(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    try:
        return (Path(str(left)).expanduser().resolve()
                == Path(str(right)).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def _is_under(child: object, parent: object) -> bool:
    try:
        child_path = Path(str(child)).expanduser().resolve()
        parent_path = Path(str(parent)).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    return parent_path == child_path or parent_path in child_path.parents


@dataclass(frozen=True)
class WatchdogConfig:
    """The complete, bounded watchdog contract.

    ``strict_canonical`` is the production posture: paths must be the canonical
    production ones.  Offline tests build a config with ``strict_canonical``
    False so a temporary tree can stand in for the real runtime roots WITHOUT
    weakening any bound -- every numeric bound is validated identically in both
    postures.
    """

    schema_version: str = WATCHDOG_CONFIG_SCHEMA_V1
    repo_root: str = REPO_ROOT
    repo_python: str = REPO_PYTHON
    launcher_path: str = CANONICAL_LIVE_LAUNCHER_PATH
    expected_head: str = ""
    state_root: str = DEFAULT_WATCHDOG_STATE_ROOT
    cursor_state_dir: str = CANONICAL_CURSOR_STATE_DIR
    ledger_path: str = CANONICAL_LEDGER_PATH
    runs_root: str = CANONICAL_RUNS_ROOT
    logs_root: str = CANONICAL_LOGS_ROOT
    task_name: str = DEFAULT_TASK_NAME

    poll_interval_seconds: float = 15.0
    startup_grace_seconds: float = DEFAULT_STARTUP_GRACE_SECONDS
    heartbeat_max_age_seconds: float = DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
    producer_heartbeat_cadence_seconds: float = PRODUCER_HEARTBEAT_CADENCE_SECONDS
    recovery_stall_seconds: float = DEFAULT_RECOVERY_STALL_SECONDS
    cooperative_stop_timeout_seconds: float = 300.0
    force_termination_grace_seconds: float = 60.0
    restart_backoff_seconds: Tuple[float, ...] = DEFAULT_RESTART_BACKOFF_SECONDS
    restart_backoff_jitter_seconds: float = 0.0
    circuit_max_restarts: int = 5
    circuit_window_seconds: float = 1800.0
    stable_run_reset_seconds: float = 1800.0
    strict_canonical: bool = True

    # -- derived state paths (never producer-owned) ------------------------- #

    @property
    def state_root_path(self) -> Path:
        return Path(self.state_root)

    @property
    def lock_path(self) -> Path:
        return self.state_root_path / "watchdog.lock"

    @property
    def status_path(self) -> Path:
        return self.state_root_path / "watchdog_status.json"

    @property
    def heartbeat_path(self) -> Path:
        return self.state_root_path / "watchdog_heartbeat.json"

    @property
    def events_path(self) -> Path:
        return self.state_root_path / "watchdog_events.jsonl"

    @property
    def restart_history_path(self) -> Path:
        return self.state_root_path / "restart_history.jsonl"

    @property
    def current_child_path(self) -> Path:
        return self.state_root_path / "current_child.json"

    @property
    def circuit_state_path(self) -> Path:
        return self.state_root_path / "circuit_state.json"

    @property
    def last_incident_path(self) -> Path:
        return self.state_root_path / "last_incident.json"

    @property
    def service_registration_path(self) -> Path:
        return self.state_root_path / "service_registration.json"

    @property
    def operator_stop_path(self) -> Path:
        """Operator-requested watchdog stop marker (watchdog-owned, not the
        producer's cooperative stop file, which the LAUNCHER names)."""
        return self.state_root_path / "OPERATOR_STOP_REQUESTED"

    @property
    def launch_manifest_dir(self) -> Path:
        """Where the launcher deposits its redaction-safe startup manifest."""
        return self.state_root_path / "launch_manifests"

    @property
    def cursor_primary_path(self) -> Path:
        return Path(self.cursor_state_dir) / "live_epoch_stream_cursor.json"

    @property
    def recovery_primary_path(self) -> Path:
        return Path(self.cursor_state_dir) / "rpc_gap_recovery.json"

    @property
    def live_epoch_primary_path(self) -> Path:
        return Path(self.cursor_state_dir) / "live_epoch_state.json"

    @property
    def live_epoch_deployment_handoff_path(self) -> Path:
        return (
            Path(self.cursor_state_dir)
            / "live_epoch_deployment_handoffs.jsonl")

    @property
    def producer_runtime_lock_path(self) -> Path:
        return Path(self.cursor_state_dir) / "phx2_state_dir_runtime.lock"

    def backoff_for_attempt(self, attempt_index: int) -> float:
        """Deterministic backoff for the Nth restart in the current budget.

        ``attempt_index`` is 0-based.  Past the end of the table the LAST value
        is reused; the table is bounded, so backoff can never grow without
        limit, and the circuit breaker -- not an ever-growing sleep -- is what
        stops a failing producer.
        """

        table = tuple(self.restart_backoff_seconds)
        if not table:
            return 0.0
        index = max(0, int(attempt_index))
        return float(table[min(index, len(table) - 1)])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo_root": self.repo_root,
            "repo_python": self.repo_python,
            "launcher_path": self.launcher_path,
            "expected_head": self.expected_head,
            "state_root": self.state_root,
            "cursor_state_dir": self.cursor_state_dir,
            "ledger_path": self.ledger_path,
            "runs_root": self.runs_root,
            "logs_root": self.logs_root,
            "task_name": self.task_name,
            "poll_interval_seconds": self.poll_interval_seconds,
            "startup_grace_seconds": self.startup_grace_seconds,
            "heartbeat_max_age_seconds": self.heartbeat_max_age_seconds,
            "producer_heartbeat_cadence_seconds": (
                self.producer_heartbeat_cadence_seconds),
            "recovery_stall_seconds": self.recovery_stall_seconds,
            "cooperative_stop_timeout_seconds": (
                self.cooperative_stop_timeout_seconds),
            "force_termination_grace_seconds": (
                self.force_termination_grace_seconds),
            "restart_backoff_seconds": list(self.restart_backoff_seconds),
            "restart_backoff_jitter_seconds": (
                self.restart_backoff_jitter_seconds),
            "circuit_max_restarts": self.circuit_max_restarts,
            "circuit_window_seconds": self.circuit_window_seconds,
            "stable_run_reset_seconds": self.stable_run_reset_seconds,
            "strict_canonical": self.strict_canonical,
        }


@dataclass
class ConfigVerdict:
    valid: bool
    refusals: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)


def _range_check(value: object, low: float, high: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if number != number:                        # NaN
        return False
    return low <= number <= high


def validate_watchdog_config(config: WatchdogConfig) -> ConfigVerdict:
    """List every violation at once.  Empty refusals means safe to run."""

    refusals: List[str] = []
    checks: Dict[str, Any] = {}

    if config.schema_version != WATCHDOG_CONFIG_SCHEMA_V1:
        refusals.append(REFUSAL_SCHEMA_VERSION)

    if not str(config.repo_root or "").strip():
        refusals.append(REFUSAL_REPO_ROOT)
    if not str(config.repo_python or "").strip():
        refusals.append(REFUSAL_REPO_PYTHON)

    if not _is_commit_sha(config.expected_head):
        refusals.append(REFUSAL_EXPECTED_HEAD)
    checks["expected_head_wellformed"] = _is_commit_sha(config.expected_head)

    # -- the watchdog state root may never sit in a protected historical tree,
    #    a disposable location, or inside producer-owned durable state.
    state_forbidden = path_is_forbidden(config.state_root)
    checks["state_root_forbidden"] = state_forbidden
    if state_forbidden:
        refusals.append(REFUSAL_STATE_ROOT_FORBIDDEN)
    if path_is_ephemeral(config.state_root) and config.strict_canonical:
        refusals.append(REFUSAL_STATE_ROOT_EPHEMERAL)
    if _is_under(config.state_root, config.cursor_state_dir) \
            or _same_path(config.state_root, config.cursor_state_dir):
        refusals.append(REFUSAL_STATE_ROOT_INSIDE_PRODUCER_STATE)

    if config.strict_canonical:
        if not _same_path(config.launcher_path, CANONICAL_LIVE_LAUNCHER_PATH):
            refusals.append(REFUSAL_LAUNCHER_PATH)
        if not _same_path(config.cursor_state_dir, CANONICAL_CURSOR_STATE_DIR):
            refusals.append(REFUSAL_CURSOR_STATE_DIR)
        if not _same_path(config.ledger_path, CANONICAL_LEDGER_PATH):
            refusals.append(REFUSAL_LEDGER_PATH)
    else:
        if not str(config.launcher_path or "").strip():
            refusals.append(REFUSAL_LAUNCHER_PATH)
        if not str(config.cursor_state_dir or "").strip():
            refusals.append(REFUSAL_CURSOR_STATE_DIR)
        if not str(config.ledger_path or "").strip():
            refusals.append(REFUSAL_LEDGER_PATH)

    if not str(config.task_name or "").strip() \
            or any(ch in str(config.task_name) for ch in "\\/:*?\"<>|"):
        refusals.append(REFUSAL_TASK_NAME)

    if not _range_check(config.poll_interval_seconds, 1.0, 300.0):
        refusals.append(REFUSAL_POLL_INTERVAL)
    if not _range_check(config.startup_grace_seconds, 30.0, 3600.0):
        refusals.append(REFUSAL_STARTUP_GRACE)
    if not _range_check(config.heartbeat_max_age_seconds, 30.0, 7200.0):
        refusals.append(REFUSAL_HEARTBEAT_MAX_AGE)
    elif not _range_check(config.producer_heartbeat_cadence_seconds,
                          1.0, 3600.0) \
            or float(config.heartbeat_max_age_seconds) < 2.0 * float(
                config.producer_heartbeat_cadence_seconds):
        # One missed tick is normal jitter, never proof of a hung producer.
        refusals.append(REFUSAL_HEARTBEAT_BELOW_CADENCE)
    if not _range_check(config.recovery_stall_seconds, 300.0, 86400.0):
        refusals.append(REFUSAL_RECOVERY_STALL)
    if not _range_check(config.cooperative_stop_timeout_seconds, 10.0, 3600.0):
        refusals.append(REFUSAL_COOPERATIVE_STOP)
    if not _range_check(config.force_termination_grace_seconds, 5.0, 600.0):
        refusals.append(REFUSAL_FORCE_GRACE)

    table = tuple(config.restart_backoff_seconds or ())
    checks["backoff_table"] = list(table)
    if not table:
        refusals.append(REFUSAL_BACKOFF_EMPTY)
    else:
        if any(not _range_check(value, 1.0, 3600.0) for value in table):
            refusals.append(REFUSAL_BACKOFF_OUT_OF_RANGE)
        elif any(float(table[i]) < float(table[i - 1])
                 for i in range(1, len(table))):
            refusals.append(REFUSAL_BACKOFF_NOT_ASCENDING)
    if not _range_check(config.restart_backoff_jitter_seconds, 0.0, 60.0):
        refusals.append(REFUSAL_JITTER)

    try:
        max_restarts = int(config.circuit_max_restarts)
    except (TypeError, ValueError):
        max_restarts = -1
    if not 1 <= max_restarts <= 100:
        refusals.append(REFUSAL_CIRCUIT_MAX_RESTARTS)
    if not _range_check(config.circuit_window_seconds, 60.0, 86400.0):
        refusals.append(REFUSAL_CIRCUIT_WINDOW)
    if not _range_check(config.stable_run_reset_seconds, 60.0, 86400.0):
        refusals.append(REFUSAL_STABLE_RESET)

    checks["refusal_count"] = len(refusals)
    return ConfigVerdict(valid=not refusals, refusals=refusals, checks=checks)


def resolve_repo_head(repo_root: object) -> Optional[str]:
    """The checked-out commit, read straight from ``.git`` (no subprocess).

    A watchdog that shelled out to ``git`` for this would depend on a PATH it
    does not control, so the two files that define HEAD are read directly.
    """

    git_dir = Path(str(repo_root)) / ".git"
    head_file = git_dir / "HEAD"
    try:
        head_text = head_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if head_text.startswith("ref:"):
        ref = head_text.split(":", 1)[1].strip()
        try:
            return (git_dir / ref).read_text(encoding="utf-8").strip().lower()
        except OSError:
            pass
        # Packed refs fallback.
        try:
            packed = (git_dir / "packed-refs").read_text(encoding="utf-8")
        except OSError:
            return None
        for line in packed.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].strip() == ref:
                return parts[0].strip().lower()
        return None
    return head_text.lower() if _is_commit_sha(head_text) else None


def pinned_head_in_launcher(launcher_text: str) -> Optional[str]:
    """The single 40-hex commit a launcher pins, or None when it is not unique.

    A launcher that pins two different commits, or none, is not a launcher the
    watchdog may start: ambiguity about WHICH tree is running is exactly the
    class of failure Stage 10 must fail closed on.
    """

    found: set = set()
    token: List[str] = []
    for char in str(launcher_text or "") + "\n":
        if char.lower() in _HEX:
            token.append(char.lower())
            continue
        if len(token) == 40:
            found.add("".join(token))
        token = []
    if len(found) != 1:
        return None
    return next(iter(found))


def alert_policy_in_launcher(launcher_text: str) -> Optional[str]:
    """The single alert policy a launcher states, or None when not unique.

    Mirrors :func:`pinned_head_in_launcher`: ambiguity about WHICH policy is
    about to run is the same class of failure as ambiguity about which tree is
    running, so zero or several distinct values both return None.  A launcher
    that states no policy is not "LEGACY by default" here -- the caller decides
    what an unstated policy means for its own surface.
    """

    values = re.findall(
        r'"--alert-policy"\s*,\s*"([^"]*)"', str(launcher_text or ""))
    normalized: set = set()
    for value in values:
        try:
            normalized.add(normalize_alert_policy(str(value).strip()))
        except ValueError:
            return None
    if len(normalized) != 1 or len(values) != 1:
        return None
    return next(iter(normalized))


def default_production_config(*, expected_head: str) -> WatchdogConfig:
    """The canonical production configuration for this repository."""

    return WatchdogConfig(expected_head=str(expected_head).strip().lower())


def load_config_overrides(path: object) -> Mapping[str, Any]:
    """Read an optional JSON override document.

    Only keys that already exist on :class:`WatchdogConfig` are honoured; an
    unknown key is ignored rather than silently redefining behaviour, and a
    malformed document raises so the caller can refuse.
    """

    text = Path(str(path)).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("WATCHDOG_CONFIG_OVERRIDE_NOT_AN_OBJECT")
    known = set(WatchdogConfig().to_dict().keys())
    return {key: value for key, value in data.items() if key in known}


def apply_overrides(config: WatchdogConfig,
                    overrides: Mapping[str, Any]) -> WatchdogConfig:
    """Return a copy with ``overrides`` applied (validated by the caller)."""

    updates: Dict[str, Any] = {}
    for key, value in dict(overrides).items():
        if key == "restart_backoff_seconds":
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                updates[key] = ()
            else:
                coerced: List[float] = []
                for item in value:
                    try:
                        coerced.append(float(item))
                    except (TypeError, ValueError):
                        coerced.append(float("nan"))
                updates[key] = tuple(coerced)
            continue
        updates[key] = value
    return replace(config, **updates)


def ensure_state_root(config: WatchdogConfig) -> Path:
    """Create the watchdog state root (and manifest dir) if absent."""

    root = config.state_root_path
    root.mkdir(parents=True, exist_ok=True)
    config.launch_manifest_dir.mkdir(parents=True, exist_ok=True)
    return root


def state_root_is_writable(config: WatchdogConfig) -> bool:
    probe = config.state_root_path / ".watchdog_write_probe"
    try:
        config.state_root_path.mkdir(parents=True, exist_ok=True)
        handle = os.open(str(probe), os.O_CREAT | os.O_WRONLY)
        os.close(handle)
        probe.unlink()
    except OSError:
        return False
    return True


__all__ = (
    "WATCHDOG_CONFIG_SCHEMA_V1",
    "CANONICAL_LIVE_LAUNCHER_DIR",
    "CANONICAL_LIVE_LAUNCHER_BASENAME",
    "CANONICAL_LIVE_LAUNCHER_PATH",
    "CLOSED_ARMED_ROUTES",
    "DEFAULT_WATCHDOG_STATE_ROOT",
    "DEFAULT_HEARTBEAT_MAX_AGE_SECONDS",
    "DEFAULT_STARTUP_GRACE_SECONDS",
    "DEFAULT_RECOVERY_STALL_SECONDS",
    "DEFAULT_RESTART_BACKOFF_SECONDS",
    "DEFAULT_TASK_NAME",
    "PRODUCER_HEARTBEAT_CADENCE_SECONDS",
    "WATCHDOG_CONFIG_REFUSAL_REASONS",
    "WatchdogConfig",
    "ConfigVerdict",
    "validate_watchdog_config",
    "resolve_repo_head",
    "pinned_head_in_launcher",
    "default_production_config",
    "load_config_overrides",
    "apply_overrides",
    "ensure_state_root",
    "state_root_is_writable",
)
