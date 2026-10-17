"""Thin, redaction-safe operator control over the PHX2 watchdog service.

This module never constructs a delivery transport, Yellowstone client or
producer command.  The tracked Task Scheduler tool starts the windowless
watchdog, and the watchdog remains the sole authority that may launch or stop
the canonical producer.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.delivery.telegram_config import (
    TELEGRAM_ENV_NAMES,
    TelegramConfig,
    TelegramConfigError,
)
from PHX2.free_tier_producer.live_epoch import (
    ClosedEpochDeploymentHandoffContext,
    ClosedEpochDeploymentHandoffVerdict,
    EPOCH_HEALTHY,
    EPOCH_STARTING,
    HISTORICAL_REPLAY_STATUS,
    build_durable_policy_identity,
    classify_live_epoch_document_set,
    record_closed_epoch_deployment_handoff,
    validate_closed_epoch_deployment_handoff,
)
from PHX2.free_tier_producer.epoch_finalization import (
    StoppedEpochFinalizationContext,
    StoppedEpochFinalizationVerdict,
    finalize_stopped_epoch,
    read_stopped_runtime_shutdown_evidence,
    validate_stopped_epoch_finalization,
)
from PHX2.free_tier_producer.rpc_gap_recovery import (
    classify_recovery_checkpoint_file,
)
from PHX2.free_tier_producer.stream_cursor import (
    classify_cursor_checkpoint_file,
)
from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_ALERT_POLICY,
    CANONICAL_LEDGER_PATH,
    CANONICAL_MIGRATION_SOURCE_MODE,
    REPO_PYTHON,
    REPO_ROOT,
)
from PHX2.watchdog.config import (
    default_production_config,
    pinned_head_in_launcher,
    resolve_repo_head,
    validate_watchdog_config,
)
from PHX2.watchdog.daemon import Watchdog
from PHX2.watchdog.process import (
    ProcessRecord,
    default_process_table,
    evaluate_stale_producer_lock,
    logical_producer_pids,
    pid_alive,
    producer_process_pids,
    read_producer_lock,
    WatchdogLock,
)
from PHX2.watchdog.launcher_template import (
    render_live_launcher_bytes,
    validate_live_launcher_text,
)
from PHX2.watchdog.state import (
    file_sha256,
    ledger_identity,
    parse_utc,
    read_json,
)
from PHX2.watchdog.windows_launch import (
    hidden_startupinfo,
    no_window_creation_flags,
)


COMMANDS = ("start", "status", "stop", "restart")
#: Recovery command, deliberately NOT in ``COMMANDS``: it takes an argument and
#: is never the default, so it can only be reached by typing it in full.
FINALIZE_STOPPED_EPOCH_COMMAND = "finalize-stopped-epoch"
#: The one acknowledgment token that authorizes a durable close.  Typing the
#: command without it is a supported, informative dry run.
FINALIZE_ACKNOWLEDGMENT_FLAG = "--acknowledge-stopped-epoch-finalization"
ACCEPTED_HEALTH = ("HEALTHY", "STARTING")
FREE_LEDGER_PATH = (
    r"C:\Users\BalaC\phx2_live_free_tier\ping_dedupe.jsonl")
FROZEN_LEDGER_PATH = (
    r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl")
TASK_TOOL = Path(REPO_ROOT) / "PHX2" / "scripts" / "phx2_watchdog_task.ps1"
REPO_VENV_PYTHON = Path(REPO_PYTHON)
REEXEC_MARKER = "PHX2_OPERATOR_REEXEC"
DEFAULT_START_TIMEOUT_SECONDS = 360.0
DEFAULT_STOP_TIMEOUT_SECONDS = 360.0
POLL_SECONDS = 2.0


def _creation_flags() -> int:
    return no_window_creation_flags()


def _same_path(left: object, right: object) -> bool:
    try:
        return Path(str(left)).resolve() == Path(str(right)).resolve()
    except (OSError, ValueError, RuntimeError):
        return False


def _parse_bool(value: object) -> bool:
    return str(value or "").strip().lower() == "true"


def _parse_key_values(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and not key.startswith("  "):
            values[key.strip()] = value.strip()
    return values


def _pinned_ledger_baseline(launcher_text: str) -> Optional[str]:
    found = sorted(set(re.findall(
        r"\b[0-9a-f]{64}:[0-9]+:[0-9]+\b",
        str(launcher_text or "").lower(),
    )))
    return found[0] if len(found) == 1 else None


def _read_env_file(path: Path) -> Dict[str, str]:
    """Parse only the known transport keys without exporting or printing them."""

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return {}
    wanted = set(TELEGRAM_ENV_NAMES)
    values: Dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in wanted:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] \
                and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def _watchdog_process_pids(table: Sequence[ProcessRecord]) -> List[int]:
    """Return distinct watchdog roots, collapsing a Windows venv shim pair."""

    matching: Dict[int, ProcessRecord] = {}
    for record in table:
        if record.image_name not in ("python.exe", "pythonw.exe"):
            continue
        command = str(record.command_line or "")
        if "PHX2.watchdog" in command and " run" in command:
            matching[int(record.pid)] = record
    return sorted(
        pid for pid, record in matching.items()
        if int(record.parent_pid) not in matching
    )


@dataclass
class SafetyVerdict:
    safe: bool
    reasons: List[str] = field(default_factory=list)
    task: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    handoff_required: bool = False
    handoff_checks: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OperatorStatus:
    state: str
    health: str
    transport: str
    discord: str
    watchdog_pid: Optional[int]
    producer_pid: Optional[int]
    yellowstone_owners: Optional[int]
    epoch_id: Optional[str]
    epoch_status: str
    epoch_start_slot: Optional[int]
    epoch_durable: bool
    epoch_identity_matches: bool
    dex_backfill: str
    circuit: str
    circuit_reason: Optional[str]
    circuit_integrity_locked: bool
    heartbeat_age_seconds: Optional[float]
    last_telegram_ping: Optional[str]
    paid_ledger_lines: Optional[int]
    paid_ledger_sha256: Optional[str]
    historical_rpc_replay: str = "DISABLED"
    structural_policy: str = "SHADOW"
    #: The EFFECTIVE alert policy bound into the durable epoch identity, not
    #: the canonical deployment value: status must disclose what is actually
    #: bound so a mismatch is visible rather than assumed away.
    alert_policy: str = "UNKNOWN"
    watchdog_count: int = 0
    producer_count: int = 0
    task_state: str = "UNKNOWN"
    task_present: bool = False
    task_schema_ok: bool = False
    #: When STOPPED, a persisted watchdog observation claiming live
    #: Yellowstone owners is HISTORICAL evidence, not current truth; the
    #: claimed count is preserved here for disclosure while
    #: ``yellowstone_owners`` reports the process-truth 0.
    stale_yellowstone_owners: Optional[int] = None
    epoch_document_state: str = "MISSING"
    #: The single operational verdict computed by the watchdog observation.
    #: Surfaced verbatim so ``main.py status`` cannot disagree with what the
    #: watchdog recorded -- the 2026-07-29 run's status read healthy while its
    #: own observation held every fact needed to say otherwise.
    operational_status: str = "UNKNOWN"
    operational_primary_cause: Optional[str] = None
    #: Market-plane liveness and the market-budget contract this deployment
    #: actually selected.  Both are read off the watchdog's observation: a
    #: producer can be alive, connected and completely unable to see the
    #: market, which is exactly what happened for 4h38m on 2026-08-02 with
    #: nothing on this surface saying so.
    market_plane_status: str = "UNKNOWN"
    market_plane_reasons: Tuple[str, ...] = ()
    market_budget_mode: str = "UNKNOWN"
    market_budget_limit_display: str = "UNKNOWN"
    market_physical_requests: Optional[int] = None
    market_request_unreconciled_delta: Optional[int] = None
    source_continuity: str = "UNKNOWN"
    source_unresolved_slots: Optional[int] = None
    #: Continuous-discovery projection (closed-set tokens from
    #: ``PHX2.free_tier_producer.discovery_status``), read off the heartbeat.
    live_source_state: str = "UNKNOWN"
    gap_recovery_state: str = "UNKNOWN"
    migration_journal_records: int = 0
    migration_journal_confirmed_slot: Optional[int] = None
    curated_coverage_claim: str = "UNKNOWN"
    watch_checkpoint_durability: str = "UNKNOWN"
    primary_migration_source: str = "UNKNOWN"
    primary_source_state: str = "UNKNOWN"
    primary_continuity: str = "UNKNOWN"
    primary_recovery: str = "UNKNOWN"
    primary_last_slot: Optional[int] = None
    primary_estimated_credits: Optional[float] = None
    shadow_source: str = "DISABLED"
    shadow_state: str = "DISABLED"
    chainstack_configured_for_runtime: bool = False
    chainstack_connected: bool = False
    chainstack_comparator: bool = False
    parity_matches: int = 0
    parity_chainstack_only: int = 0
    parity_helius_only: int = 0
    parity_slot_mismatches: int = 0
    parity_decode_mismatches: int = 0
    post_boundary_candidates_admitted: int = 0
    pre_boundary_candidates_ignored: int = 0
    restored_diagnostic_records: int = 0
    dex_diagnostic_records: int = 0
    historical_candidates_eligible: int = 0
    dex_restart_backfill_mode: str = "UNKNOWN"

    @property
    def accepted_running(self) -> bool:
        return (
            self.state == "RUNNING"
            and self.health in ACCEPTED_HEALTH
            and self.epoch_status in (EPOCH_STARTING, EPOCH_HEALTHY)
            and self.circuit == "CLOSED"
            and self.watchdog_count == 1
            and self.producer_count == 1
            and self.yellowstone_owners in (None, 1)
            # Coverage that cannot be proven continuous is never an accepted
            # running state, however healthy every process-level fact looks.
            and self.source_continuity in ("NO_GAP", "UNKNOWN")
        )


class OperatorBackend:
    """All OS-facing seams, kept injectable for deterministic offline tests."""

    def __init__(
        self,
        *,
        repo_root: object = REPO_ROOT,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        process_table_fn: Callable[[], Sequence[ProcessRecord]] = (
            default_process_table),
    ) -> None:
        self.repo_root = Path(repo_root)
        self.sleep = sleep_fn
        self.monotonic = monotonic_fn
        self.process_table_fn = process_table_fn

    def _run(self, argv: Sequence[str], *, timeout: float = 60.0
             ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv), cwd=str(self.repo_root), capture_output=True, text=True,
            check=False, timeout=timeout, creationflags=_creation_flags(),
            startupinfo=hidden_startupinfo())

    def task_action(self, action: str) -> Dict[str, Any]:
        completed = self._run([
            "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
            "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(TASK_TOOL), action,
        ])
        values = _parse_key_values(completed.stdout)
        values["_returncode"] = completed.returncode
        values["_ok"] = (
            completed.returncode == 0
            and not values.get("refusal")
            and not completed.stderr.strip())
        return values

    def task_status(self) -> Dict[str, Any]:
        values = self.task_action("status")
        return {
            **values,
            "task_present": _parse_bool(values.get("task_present")),
            "managed_schema_ok": _parse_bool(
                values.get("managed_schema_ok")),
            "watchdog_exe_exists": _parse_bool(
                values.get("watchdog_exe_exists")),
            "task_state": str(values.get("task_state") or "UNKNOWN"),
        }

    def process_table(self) -> List[ProcessRecord]:
        return list(self.process_table_fn())

    def watchdog_snapshot(self) -> Dict[str, Any]:
        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        return Watchdog(config).status_snapshot()

    def request_watchdog_stop(self) -> bool:
        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        return bool(Watchdog(config).request_operator_stop().get(
            "operator_stop_requested"))

    def clear_watchdog_stop(self) -> None:
        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        Watchdog(config).clear_operator_stop()

    def git_clean_and_complete(self) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        git_dir = self.repo_root / ".git"
        for relative, label in (
            ("MERGE_HEAD", "GIT_MERGE_IN_PROGRESS"),
            ("CHERRY_PICK_HEAD", "GIT_CHERRY_PICK_IN_PROGRESS"),
            ("BISECT_LOG", "GIT_BISECT_IN_PROGRESS"),
            ("rebase-merge", "GIT_REBASE_IN_PROGRESS"),
            ("rebase-apply", "GIT_REBASE_IN_PROGRESS"),
        ):
            if (git_dir / relative).exists():
                reasons.append(label)
        completed = self._run([
            "git", "status", "--porcelain=v1", "--untracked-files=all"])
        if completed.returncode != 0:
            reasons.append("GIT_STATUS_UNREADABLE")
        elif completed.stdout.strip():
            reasons.append("REPOSITORY_NOT_CLEAN")
        return not reasons, sorted(set(reasons))

    def git_ancestry(
        self, prior_head: str, current_head: str
    ) -> tuple[bool, bool]:
        """Return ``(current_descends_from_prior, current_is_rollback)``."""

        forward = self._run([
            "git", "merge-base", "--is-ancestor",
            str(prior_head), str(current_head),
        ])
        reverse = self._run([
            "git", "merge-base", "--is-ancestor",
            str(current_head), str(prior_head),
        ])
        return forward.returncode == 0, reverse.returncode == 0

    def closed_epoch_deployment_handoff(
        self, *, record: bool = False
    ) -> ClosedEpochDeploymentHandoffVerdict:
        """Validate, and optionally record, the one CLOSED-epoch transition."""

        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        epoch_state, epoch, _ = classify_live_epoch_document_set(
            config.live_epoch_primary_path)
        launcher_path = Path(config.launcher_path)
        try:
            launcher_bytes = launcher_path.read_bytes()
            launcher_text = launcher_bytes.decode("utf-8")
        except (OSError, UnicodeError):
            launcher_bytes = b""
            launcher_text = ""
        baseline = _pinned_ledger_baseline(launcher_text) or ""
        current_sha = (
            hashlib.sha256(launcher_bytes).hexdigest()
            if launcher_bytes else "")
        current_identity = build_durable_policy_identity(
            state_dir=config.cursor_state_dir,
            cursor_state_dir=config.cursor_state_dir,
            canonical_ledger_path=config.ledger_path,
            repo_head=head,
            launcher_sha256=current_sha,
            delivery_policy="TELEGRAM_ONLY",
            telegram_enabled=True,
            discord_enabled=False,
            structural_policy="SHADOW",
            # The handoff authorizes the CANONICAL deployment about to be run.
            alert_policy=CANONICAL_ALERT_POLICY,
            # Bounded six-hour DEX candidate recovery is part of the armed
            # production contract (_CANONICAL_SEMANTIC_POLICY).  Building the
            # CURRENT identity with False made canonical_semantics fail, so the
            # sanctioned dex_backfill_reinstated arm could never fire.
            dex_backfill_enabled=True,
        )
        prior_identity = epoch.get("durable_policy_identity")
        if not isinstance(prior_identity, Mapping):
            prior_identity = {}
        prior_head = str(
            prior_identity.get("repo_head_binding") or "").lower()
        prior_launcher = str(
            prior_identity.get("launcher_sha256_binding") or "").lower()
        descends, rollback = self.git_ancestry(prior_head, head)
        clean, _ = self.git_clean_and_complete()
        rendered_current = (
            render_live_launcher_bytes(
                expected_head=head, ledger_baseline=baseline)
            if len(head) == 40 and baseline else b"")
        rendered_prior = (
            render_live_launcher_bytes(
                expected_head=prior_head, ledger_baseline=baseline)
            if len(prior_head) == 40 and baseline else b"")
        contract_refusals = (
            validate_live_launcher_text(
                launcher_text,
                expected_head=head,
                ledger_baseline=baseline,
            )
            if baseline else ["LIVE_LAUNCHER_BASELINE_UNRESOLVED"])

        table = self.process_table()
        watchdog_count, producer_count, live_or_ambiguous_locks = (
            self._live_owner_counts(config, table))

        context = ClosedEpochDeploymentHandoffContext(
            current_repository_head=head,
            current_launcher_sha256=current_sha,
            repository_head_is_descendant=descends,
            repository_rollback=bool(rollback and prior_head != head),
            git_clean_and_complete=clean,
            current_launcher_canonical=bool(
                launcher_bytes and launcher_bytes == rendered_current),
            current_launcher_head_pin_count=launcher_text.count(head),
            current_launcher_ledger_pin_count=(
                launcher_text.count(baseline) if baseline else 0),
            current_launcher_contract_refusals=tuple(contract_refusals),
            prior_launcher_canonical=bool(
                rendered_prior
                and hashlib.sha256(rendered_prior).hexdigest()
                == prior_launcher),
            canonical_ledger_path_digest=str(
                current_identity.get("canonical_ledger_path_binding") or ""),
            watchdog_count=watchdog_count,
            producer_count=producer_count,
            # The tracked architecture has no independent owner constructors:
            # with zero producer processes and no live/ambiguous runtime lock,
            # each in-process owner count is proven zero.
            yellowstone_owner_count=producer_count,
            telegram_delivery_owner_count=producer_count,
            canonical_ledger_writer_count=producer_count,
            live_or_ambiguous_lock_count=live_or_ambiguous_locks,
            handoff_at_utc=datetime.now(
                tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        call = (
            record_closed_epoch_deployment_handoff
            if record else validate_closed_epoch_deployment_handoff)
        return call(
            epoch_path=config.live_epoch_primary_path,
            current_policy_identity=current_identity,
            context=context,
            handoff_path=config.live_epoch_deployment_handoff_path,
        )

    def _live_owner_counts(
        self, config: Any, table: Sequence[ProcessRecord]
    ) -> tuple[int, int, int]:
        """``(watchdog_count, producer_count, live_or_ambiguous_locks)``."""

        watchdog_count = len(_watchdog_process_pids(table))
        producer_count = len(logical_producer_pids(table))
        live_or_ambiguous_locks = 0
        watchdog_lock = WatchdogLock(config.lock_path)
        watchdog_lock_present, watchdog_document = watchdog_lock.read()
        if watchdog_lock_present:
            holder = watchdog_lock.holder_pid()
            if watchdog_document is None \
                    or (holder is not None and pid_alive(holder)):
                live_or_ambiguous_locks += 1
        producer_lock = read_producer_lock(config.producer_runtime_lock_path)
        if producer_lock.present:
            if producer_lock.malformed \
                    or producer_lock.holder_pid is None \
                    or pid_alive(producer_lock.holder_pid):
                live_or_ambiguous_locks += 1
            else:
                stale = evaluate_stale_producer_lock(
                    lock=producer_lock,
                    table=table,
                    yellowstone_owner_count=(
                        0 if producer_count == 0 else None),
                )
                if not stale.removable:
                    live_or_ambiguous_locks += 1
        return watchdog_count, producer_count, live_or_ambiguous_locks

    def stopped_epoch_finalization(
        self, *, acknowledged: bool = False, write: bool = False
    ) -> StoppedEpochFinalizationVerdict:
        """Validate, and optionally perform, the stopped-epoch finalization.

        Collects only preserved evidence and current ownership.  Nothing here
        arms, starts, restarts or clears anything, and the canonical ledger is
        never opened.
        """

        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        _state, epoch, _facts = classify_live_epoch_document_set(
            config.live_epoch_primary_path)
        run_identity = epoch.get("run_instance_identity")
        if not isinstance(run_identity, Mapping):
            run_identity = {}
        evidence = read_stopped_runtime_shutdown_evidence(
            runtime_nonce=run_identity.get("runtime_nonce"),
            startup_manifest_binding=run_identity.get(
                "startup_manifest_binding"),
            watchdog_state_root=config.state_root_path,
            launch_manifest_dir=config.launch_manifest_dir,
            operator_stop_marker_path=config.operator_stop_path,
            events_path=config.events_path,
            current_child_path=config.current_child_path,
        )
        table = self.process_table()
        watchdog_count, producer_count, locks = self._live_owner_counts(
            config, table)
        context = StoppedEpochFinalizationContext(
            operator_acknowledged=bool(acknowledged),
            watchdog_count=watchdog_count,
            producer_count=producer_count,
            # Same reasoning as the deployment handoff: the tracked
            # architecture has no owner constructor outside the producer, so
            # zero producer processes proves each in-process owner count zero.
            yellowstone_owner_count=producer_count,
            telegram_delivery_owner_count=producer_count,
            canonical_ledger_writer_count=producer_count,
            live_or_ambiguous_lock_count=locks,
        )
        call = (
            finalize_stopped_epoch if write
            else validate_stopped_epoch_finalization)
        return call(
            epoch_path=config.live_epoch_primary_path,
            evidence=evidence,
            context=context,
        )

    def transport_valid(self) -> tuple[bool, Optional[str]]:
        try:
            TelegramConfig.from_mapping(
                _read_env_file(self.repo_root / ".env"))
        except TelegramConfigError as exc:
            return False, exc.reason
        return True, None

    def helius_source_valid(self) -> tuple[bool, Optional[str]]:
        """Validate source configuration shape without opening a socket."""

        from PHX2.free_tier_producer.helius_source import (
            load_helius_source_config,
        )

        try:
            load_helius_source_config(env_path=self.repo_root / ".env")
        except ValueError:
            return False, "HELIUS_CONFIGURATION_INVALID"
        return True, None

    def latest_heartbeat(self) -> Dict[str, Any]:
        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        candidates: List[Path] = []
        try:
            for run_dir in Path(config.runs_root).iterdir():
                heartbeat = run_dir / "producer_heartbeat.json"
                if heartbeat.is_file():
                    candidates.append(heartbeat)
        except OSError:
            return {}
        candidates.sort(
            key=lambda item: item.stat().st_mtime if item.exists() else 0.0,
            reverse=True)
        for path in candidates[:3]:
            ok, document = read_json(path)
            if ok and isinstance(document, dict):
                return document
        return {}

    def runtime_locks_absent(self) -> bool:
        head = resolve_repo_head(self.repo_root) or ""
        config = default_production_config(expected_head=head)
        return (
            not read_producer_lock(config.producer_runtime_lock_path).present
            and not config.lock_path.exists()
        )


def _last_ledger_timestamp(path: object) -> Optional[str]:
    try:
        lines = Path(str(path)).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
    except (ValueError, TypeError):
        return None
    if not isinstance(record, dict):
        return None
    for key in ("delivered_at_utc", "sent_at_utc", "reserved_at_utc",
                "created_at_utc"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _bound_alert_policy(*sources: object) -> str:
    """The effective alert policy, read from the first source that states one.

    Preference order is durable-first: the epoch's ``durable_policy_identity``
    is the binding that actually authorizes a run, and the producer heartbeat /
    telemetry only corroborate it.  An unstated policy reports UNKNOWN rather
    than defaulting to a value the deployment never bound -- a silent default
    here is exactly the gap this binding exists to close.
    """

    for source in sources:
        if not isinstance(source, Mapping):
            continue
        identity = source.get("durable_policy_identity")
        if isinstance(identity, Mapping) and identity.get(
                "alert_policy_binding"):
            return str(identity["alert_policy_binding"])
        if source.get("alert_policy"):
            return str(source["alert_policy"])
    return "UNKNOWN"


def dex_backfill_status_text(dex: object, *, enabled: object = None) -> str:
    """One-line Dex restart-backfill status for ``main.py status``.

    A PARTIAL sweep must name the coverage it lost. Every preserved sweep
    was PARTIAL and none said which source failed.  Only sources that were
    actually requested and failed are "lost"; a retired source is out of the
    source set (its versioned disposition stays in ``retired_sources`` on the
    heartbeat snapshot) and never renders as lost coverage.

    A deliberately-off backfill and a broken one are different facts:
    ``enabled is False`` with no snapshot renders the closed-set state
    ``DISABLED``; ``enabled is True`` with no snapshot (or a snapshot that has
    not completed a sweep yet) renders ``STARTING``.  ``UNAVAILABLE`` remains
    the conservative rendering only when the enabled fact itself is unknown.
    """

    if not isinstance(dex, Mapping) or not isinstance(dex.get("status"), str):
        if enabled is False:
            return "DISABLED"
        if enabled is True:
            return "STARTING"
        return "UNAVAILABLE"
    text = str(dex["status"])
    if text == "NOT_RUN":
        return "STARTING"
    if text.startswith("DEX_BACKFILL_"):
        text = text.removeprefix("DEX_BACKFILL_")
    operational = dex.get("operational_state")
    if isinstance(operational, str) and operational and \
            operational not in ("HEALTHY",):
        text = f"{operational}: {text}"
    failed_sources = dex.get("sources_failed")
    if isinstance(failed_sources, (list, tuple)) and failed_sources:
        text += " (lost: " + ", ".join(
            str(name) for name in failed_sources) + ")"
    # A successful curated request is NOT six-hour completeness.  The coverage
    # claim rides alongside the request status so no operator can read one as
    # the other.
    coverage = dex.get("dex_safety_net_coverage")
    if isinstance(coverage, str) and coverage:
        text += f" [coverage: {coverage}]"
    return text


def collect_status(backend: OperatorBackend) -> OperatorStatus:
    task = backend.task_status()
    snapshot = backend.watchdog_snapshot()
    table = backend.process_table()
    watchdog_pids = _watchdog_process_pids(table)
    producer_roots = logical_producer_pids(table)
    producer_processes = producer_process_pids(table)
    status_document = snapshot.get("status")
    if not isinstance(status_document, Mapping):
        status_document = {}
    observation = status_document.get("observation")
    if not isinstance(observation, Mapping):
        observation = {}

    head = resolve_repo_head(backend.repo_root) or ""
    config = default_production_config(expected_head=head)
    epoch_state, epoch, _epoch_facts = classify_live_epoch_document_set(
        config.live_epoch_primary_path)
    if epoch_state not in ("VALID_CURRENT", "VALID_BACKUP"):
        epoch = {}

    heartbeat = backend.latest_heartbeat()
    telemetry = heartbeat.get("provider_telemetry")
    if not isinstance(telemetry, Mapping):
        telemetry = {}
    parity = telemetry.get("parity")
    if not isinstance(parity, Mapping):
        parity = {}
    dex = heartbeat.get("dexscreener_restart_backfill")
    if not isinstance(dex, Mapping):
        dex = telemetry.get("dexscreener_restart_backfill")
    dex_enabled = heartbeat.get("dexscreener_restart_backfill_enabled")
    if not isinstance(dex_enabled, bool):
        dex_enabled = telemetry.get("dexscreener_restart_backfill_enabled")
    dex_status = dex_backfill_status_text(
        dex,
        enabled=dex_enabled if isinstance(dex_enabled, bool) else None)
    dex_mode = str(
        heartbeat.get("dex_restart_backfill_mode") or "UNKNOWN")
    if dex_mode == "DIAGNOSTIC_ONLY":
        dex_status = f"DIAGNOSTIC_ONLY: {dex_status}"
    discovery = heartbeat.get("continuous_discovery")
    if not isinstance(discovery, Mapping):
        discovery = telemetry.get("continuous_discovery")
    if not isinstance(discovery, Mapping):
        discovery = {}
    journal = heartbeat.get("migration_journal")
    if not isinstance(journal, Mapping):
        journal = telemetry.get("migration_journal")
    if not isinstance(journal, Mapping):
        journal = {}

    paid = ledger_identity(CANONICAL_LEDGER_PATH)
    heartbeat_age = observation.get("heartbeat_age_seconds")
    if not isinstance(heartbeat_age, (int, float)):
        heartbeat_age = None
    yellowstone = observation.get("yellowstone_owner_count")
    if not isinstance(yellowstone, int) or isinstance(yellowstone, bool):
        yellowstone = None
    producer_holder = snapshot.get("producer_lock_holder_pid")
    producer_running = bool(
        isinstance(producer_holder, int) and pid_alive(producer_holder))
    watchdog_holder = snapshot.get("watchdog_lock_holder_pid")
    watchdog_running = bool(
        isinstance(watchdog_holder, int) and pid_alive(watchdog_holder))
    watchdog_count = len(watchdog_pids)
    producer_count = len(producer_roots)
    # A restricted process query can be empty; authenticated live locks still
    # establish one owner for concise status, but never establish absence.
    if watchdog_running and watchdog_count == 0:
        watchdog_count = 1
    if producer_running and producer_count == 0:
        producer_count = 1

    health = str(status_document.get("health_class") or "UNKNOWN")
    # Never default to EPOCH_STARTING.  With no authenticated document and no
    # recorded observation there is no evidence of ANY epoch, and printing
    # "starting" invents a live-looking one; say UNKNOWN instead.  The durable
    # document stays first so a finalized EPOCH_CLOSED is reported as closed
    # even while a stale observation still claims the run was healthy.
    epoch_status = str(
        epoch.get("epoch_status")
        or observation.get("epoch_status")
        or "UNKNOWN")
    state = (
        "RUNNING" if watchdog_running and producer_running
        else "STARTING" if watchdog_running
        else "STOPPED")
    # With zero live watchdog/producer processes, the persisted watchdog
    # observation is a snapshot of the LAST run, not current ownership: a
    # stale heartbeat-derived owner count must never present a stopped
    # system as still owning a Yellowstone stream (proven live 2026-07-27:
    # "Yellowstone owners: 1" after a verified full stop).  The stale claim
    # is preserved for disclosure; current truth is zero owners.
    stale_owner_claim: Optional[int] = None
    if state == "STOPPED" and isinstance(yellowstone, int) and yellowstone > 0:
        stale_owner_claim = int(yellowstone)
        yellowstone = 0
    primary_source_state = str(
        telemetry.get("primary_source_state")
        or telemetry.get("status")
        or "UNKNOWN"
    )
    shadow_state = str(telemetry.get("shadow_state") or "DISABLED")
    if state == "STOPPED":
        # Provider telemetry is an immutable snapshot of the last run.  Once
        # process and lock ownership prove the runtime stopped, do not render
        # that historical connection state as current operator truth.
        primary_source_state = "STOPPED"
        shadow_state = "DISABLED"
    planned_helius_only = CANONICAL_MIGRATION_SOURCE_MODE == "HELIUS_PRIMARY"
    primary_migration_source = str(
        telemetry.get("primary_migration_source")
        if state == "RUNNING" and telemetry.get("primary_migration_source")
        else "HELIUS" if planned_helius_only else "UNKNOWN"
    )
    primary_recovery = str(
        telemetry.get("primary_recovery")
        if state == "RUNNING" and telemetry.get("primary_recovery")
        else "HELIUS_HTTP" if planned_helius_only else "UNKNOWN"
    )
    shadow_source = str(
        telemetry.get("shadow_source")
        if state == "RUNNING" and telemetry.get("shadow_source")
        else "DISABLED" if planned_helius_only else "UNKNOWN"
    )
    parity_current = (
        parity if state == "RUNNING" and shadow_source != "DISABLED" else {}
    )
    # An ABSENT observation is not a passing one.  Defaulting the claim to True
    # meant a stopped runtime with no recorded observation printed "Epoch
    # identity matches: True" on no evidence at all; require the watchdog to
    # have actually stated it, alongside an authenticated document.
    identity_matches = bool(
        observation.get("epoch_identity_matches") is True
        and epoch_state in ("VALID_CURRENT", "VALID_BACKUP"))
    epoch_durable = bool(
        epoch_state in ("VALID_CURRENT", "VALID_BACKUP")
        and (
            observation.get("epoch_durable") is True
            or not producer_running))
    return OperatorStatus(
        state=state,
        health=health,
        transport="TELEGRAM",
        discord="DISABLED",
        watchdog_pid=(
            int(watchdog_holder) if watchdog_running
            and isinstance(watchdog_holder, int)
            else watchdog_pids[0] if len(watchdog_pids) == 1 else None),
        producer_pid=(
            int(producer_holder) if producer_running
            and isinstance(producer_holder, int)
            else producer_roots[0] if len(producer_roots) == 1 else None),
        yellowstone_owners=yellowstone,
        epoch_id=(
            str(epoch.get("live_epoch_id"))
            if epoch.get("live_epoch_id") else None),
        epoch_status=epoch_status,
        epoch_start_slot=(
            int(epoch["epoch_start_slot"])
            if isinstance(epoch.get("epoch_start_slot"), int) else None),
        epoch_durable=epoch_durable,
        epoch_identity_matches=identity_matches,
        dex_backfill=dex_status,
        dex_restart_backfill_mode=dex_mode,
        post_boundary_candidates_admitted=int(
            heartbeat.get("post_boundary_candidates_admitted") or 0),
        pre_boundary_candidates_ignored=int(
            heartbeat.get("pre_boundary_candidates_ignored") or 0),
        restored_diagnostic_records=int(
            heartbeat.get("restored_diagnostic_records") or 0),
        dex_diagnostic_records=int(
            heartbeat.get("dex_diagnostic_records") or 0),
        historical_candidates_eligible=int(
            heartbeat.get("historical_candidates_eligible") or 0),
        alert_policy=_bound_alert_policy(epoch, heartbeat, telemetry),
        circuit=str(snapshot.get("circuit_status") or "UNKNOWN"),
        circuit_reason=(
            str(snapshot.get("circuit_open_reason"))
            if snapshot.get("circuit_open_reason") else None),
        circuit_integrity_locked=bool(
            snapshot.get("circuit_integrity_locked")),
        heartbeat_age_seconds=float(heartbeat_age)
        if heartbeat_age is not None else None,
        last_telegram_ping=_last_ledger_timestamp(CANONICAL_LEDGER_PATH),
        paid_ledger_lines=(
            int(paid["lines"]) if isinstance(paid.get("lines"), int)
            else None),
        paid_ledger_sha256=(
            str(paid["sha256"]) if paid.get("sha256") else None),
        watchdog_count=watchdog_count,
        producer_count=producer_count,
        task_state=str(task.get("task_state") or "UNKNOWN"),
        task_present=bool(task.get("task_present")),
        task_schema_ok=bool(task.get("managed_schema_ok")),
        stale_yellowstone_owners=stale_owner_claim,
        epoch_document_state=str(epoch_state),
        # Read from the watchdog's own recorded observation, never recomputed
        # here: one evaluation, four surfaces.
        operational_status=str(
            observation.get("operational_status") or "UNKNOWN"),
        operational_primary_cause=(
            str(observation["primary_cause"])
            if observation.get("primary_cause") else None),
        market_plane_status=str(
            (heartbeat or {}).get("market_plane_status") or "UNKNOWN"),
        market_plane_reasons=tuple(
            str(reason) for reason in (
                (heartbeat or {}).get("market_plane_reasons") or [])),
        market_budget_mode=str(
            (heartbeat or {}).get("market_budget_mode") or "UNKNOWN"),
        market_budget_limit_display=str(
            (heartbeat or {}).get("market_budget_limit_display") or "UNKNOWN"),
        market_physical_requests=(
            int((heartbeat or {})["transport_physical_requests_total"])
            if isinstance((heartbeat or {}).get(
                "transport_physical_requests_total"), int) else None),
        market_request_unreconciled_delta=(
            int((heartbeat or {})["unreconciled_delta"])
            if isinstance((heartbeat or {}).get("unreconciled_delta"), int)
            else None),
        live_source_state=str(
            discovery.get("live_source_state") or "UNKNOWN"),
        gap_recovery_state=str(
            discovery.get("gap_recovery_state") or "UNKNOWN"),
        migration_journal_records=int(journal.get("record_count") or 0),
        migration_journal_confirmed_slot=(
            int(journal["last_confirmed_slot"])
            if isinstance(journal.get("last_confirmed_slot"), int)
            and not isinstance(journal.get("last_confirmed_slot"), bool)
            else None),
        curated_coverage_claim=str(
            discovery.get("curated_coverage_claim") or "UNKNOWN"),
        source_continuity=str(
            observation.get("source_continuity_state") or "UNKNOWN"),
        source_unresolved_slots=(
            int(observation["source_unresolved_slot_total"])
            if isinstance(observation.get("source_unresolved_slot_total"), int)
            and not isinstance(
                observation.get("source_unresolved_slot_total"), bool)
            else None),
        watch_checkpoint_durability=str(
            observation.get("watch_checkpoint_durability_status")
            or "UNKNOWN"),
        primary_migration_source=primary_migration_source,
        primary_source_state=primary_source_state,
        primary_continuity=str(
            telemetry.get("source_continuity_state")
            or observation.get("source_continuity_state")
            or "UNKNOWN"
        ),
        primary_recovery=primary_recovery,
        primary_last_slot=(
            int(telemetry["primary_last_slot"])
            if isinstance(telemetry.get("primary_last_slot"), int)
            and not isinstance(telemetry.get("primary_last_slot"), bool)
            else None
        ),
        primary_estimated_credits=(
            float(telemetry["primary_estimated_credits"])
            if isinstance(
                telemetry.get("primary_estimated_credits"),
                (int, float),
            )
            and not isinstance(
                telemetry.get("primary_estimated_credits"),
                bool,
            )
            else None
        ),
        shadow_source=shadow_source,
        shadow_state=shadow_state,
        chainstack_configured_for_runtime=bool(
            telemetry.get("chainstack_configured_for_runtime", False)
            if state == "RUNNING" else False
        ),
        chainstack_connected=bool(
            telemetry.get("chainstack_connected", False)
            if state == "RUNNING" else False
        ),
        chainstack_comparator=bool(
            telemetry.get("chainstack_comparator", False)
            if state == "RUNNING" else False
        ),
        parity_matches=int(parity_current.get("matches") or 0),
        parity_chainstack_only=int(
            parity_current.get("chainstack_only") or 0
        ),
        parity_helius_only=int(parity_current.get("helius_only") or 0),
        parity_slot_mismatches=int(
            parity_current.get("slot_mismatches") or 0
        ),
        parity_decode_mismatches=int(
            parity_current.get("decode_mismatches") or 0
        ),
    )


def safety_check(
    backend: OperatorBackend,
    *,
    require_clean_git: bool = True,
) -> SafetyVerdict:
    reasons: List[str] = []
    handoff_required = False
    handoff_checks: Dict[str, Any] = {}
    head = resolve_repo_head(backend.repo_root)
    if not head:
        reasons.append("REPOSITORY_IDENTITY_UNREADABLE")
        return SafetyVerdict(False, reasons)
    config = default_production_config(expected_head=head)
    config_verdict = validate_watchdog_config(config)
    reasons.extend(config_verdict.refusals)
    if require_clean_git:
        clean, git_reasons = backend.git_clean_and_complete()
        if not clean:
            reasons.extend(git_reasons)

    task = backend.task_status()
    if not task.get("task_present"):
        reasons.append("MANAGED_TASK_ABSENT")
    elif not task.get("managed_schema_ok"):
        reasons.append("MANAGED_TASK_SCHEMA_INVALID")
    if not task.get("watchdog_exe_exists"):
        reasons.append("REPO_VENV_PYTHONW_NOT_FOUND")

    transport_ok, transport_reason = backend.transport_valid()
    if not transport_ok:
        reasons.append(str(transport_reason or "TELEGRAM_CONFIG_INVALID"))
    helius_check = getattr(backend, "helius_source_valid", None)
    if callable(helius_check):
        helius_ok, helius_reason = helius_check()
        if not helius_ok:
            reasons.append(
                str(helius_reason or "HELIUS_CONFIGURATION_INVALID")
            )

    snapshot = backend.watchdog_snapshot()
    circuit = str(snapshot.get("circuit_status") or "UNKNOWN")
    if circuit != "CLOSED":
        reasons.append("CIRCUIT_OPEN")

    table = backend.process_table()
    watchdog_pids = _watchdog_process_pids(table)
    producer_roots = logical_producer_pids(table)
    if len(watchdog_pids) > 1:
        reasons.append("DUPLICATE_WATCHDOG")
    if len(producer_roots) > 1:
        reasons.append("DUPLICATE_PRODUCER")

    observation = ((snapshot.get("status") or {}).get("observation") or {})
    yellowstone = observation.get("yellowstone_owner_count")
    if isinstance(yellowstone, int) and yellowstone > 1:
        reasons.append("DUPLICATE_YELLOWSTONE_OWNER")

    lock = read_producer_lock(config.producer_runtime_lock_path)
    if lock.present and not (
            lock.holder_pid is not None and pid_alive(lock.holder_pid)):
        zero_owner = 0 if not producer_roots else yellowstone
        stale = evaluate_stale_producer_lock(
            lock=lock, table=table, yellowstone_owner_count=zero_owner)
        if not stale.removable:
            reasons.append("AMBIGUOUS_PRODUCER_LOCK")

    launcher = Path(config.launcher_path)
    launcher_sha = ""
    try:
        launcher_text = launcher.read_text(encoding="utf-8")
        launcher_bytes = launcher.read_bytes()
    except (OSError, UnicodeError):
        reasons.append("CANONICAL_LIVE_LAUNCHER_UNREADABLE")
    else:
        launcher_sha = hashlib.sha256(launcher_bytes).hexdigest()
        if pinned_head_in_launcher(launcher_text) != head:
            reasons.append("LAUNCHER_HEAD_PIN_MISMATCH")
        baseline = _pinned_ledger_baseline(launcher_text)
        if baseline is None:
            reasons.append("LAUNCHER_LEDGER_BASELINE_PIN_INVALID")
        else:
            launcher_refusals = validate_live_launcher_text(
                launcher_text,
                expected_head=head,
                ledger_baseline=baseline,
            )
            reasons.extend(launcher_refusals)
            if launcher_bytes != render_live_launcher_bytes(
                    expected_head=head, ledger_baseline=baseline):
                reasons.append("LAUNCHER_NOT_CANONICALLY_GENERATED")

    for label, path in (
        ("PAID_LEDGER", CANONICAL_LEDGER_PATH),
        ("FREE_LEDGER", FREE_LEDGER_PATH),
        ("FROZEN_LEDGER", FROZEN_LEDGER_PATH),
    ):
        identity = ledger_identity(path)
        if not identity.get("parse_ok"):
            reasons.append(label + "_INVALID")

    epoch_state, epoch, _facts = classify_live_epoch_document_set(
        config.live_epoch_primary_path)
    if epoch_state not in ("VALID_CURRENT", "VALID_BACKUP", "MISSING"):
        reasons.append("EPOCH_DOCUMENT_INVALID")
    elif epoch_state in ("VALID_CURRENT", "VALID_BACKUP"):
        expected_identity = build_durable_policy_identity(
            state_dir=config.cursor_state_dir,
            cursor_state_dir=config.cursor_state_dir,
            canonical_ledger_path=config.ledger_path,
            repo_head=head,
            launcher_sha256=launcher_sha,
            delivery_policy="TELEGRAM_ONLY",
            telegram_enabled=True,
            discord_enabled=False,
            structural_policy="SHADOW",
            # Mirrors the armed production contract; see the handoff builder.
            alert_policy=CANONICAL_ALERT_POLICY,
            dex_backfill_enabled=True,
        )
        stored_identity = epoch.get("durable_policy_identity")
        if isinstance(stored_identity, Mapping) \
                and dict(stored_identity) != expected_identity:
            handoff = backend.closed_epoch_deployment_handoff(record=False)
            handoff_checks = dict(handoff.checks)
            if handoff.allowed:
                handoff_required = True
            else:
                reasons.extend(handoff.refusals)
    try:
        cursor = classify_cursor_checkpoint_file(config.cursor_primary_path)
        if str(cursor.state) not in ("VALID_CURRENT", "MISSING"):
            reasons.append("CURSOR_DOCUMENT_INVALID")
    except Exception:
        reasons.append("CURSOR_DOCUMENT_INVALID")
    try:
        recovery = classify_recovery_checkpoint_file(
            config.recovery_primary_path)
        if str(recovery.state) not in (
                "VALID_CURRENT", "VALID_LEGACY", "MISSING"):
            reasons.append("RECOVERY_DOCUMENT_INVALID")
    except Exception:
        reasons.append("RECOVERY_DOCUMENT_INVALID")

    return SafetyVerdict(
        safe=not reasons,
        reasons=sorted(set(reasons)),
        task=dict(task),
        runtime=dict(snapshot),
        handoff_required=handoff_required,
        handoff_checks=handoff_checks,
    )


def print_status(status: OperatorStatus) -> None:
    short_epoch = (
        status.epoch_id[:18] + "…" if status.epoch_id
        and len(status.epoch_id) > 18 else status.epoch_id or "NONE")
    heartbeat = (
        f"{status.heartbeat_age_seconds:.1f}s"
        if status.heartbeat_age_seconds is not None else "UNKNOWN")
    print("PHX2 STATUS")
    print(f"State: {status.state}")
    print(f"Health: {status.health}")
    print(f"Transport: {status.transport}")
    print(f"Discord: {status.discord}")
    print(f"Watchdog PID: {status.watchdog_pid or 'NONE'}")
    print(f"Producer PID: {status.producer_pid or 'NONE'}")
    owners_text = (
        str(status.yellowstone_owners)
        if status.yellowstone_owners is not None else "UNKNOWN")
    if status.stale_yellowstone_owners is not None:
        owners_text += (
            f" (stale heartbeat claimed {status.stale_yellowstone_owners}; "
            "no live process — historical evidence only)")
    print(f"Yellowstone owners: {owners_text}")
    print(f"Primary migration source: {status.primary_migration_source}")
    print(f"Primary source state: {status.primary_source_state}")
    print(f"Primary continuity: {status.primary_continuity}")
    print(f"Primary recovery: {status.primary_recovery}")
    print(
        "Primary last slot: "
        + (
            str(status.primary_last_slot)
            if status.primary_last_slot is not None else "NONE"
        )
    )
    print(
        "Primary estimated credits: "
        + (
            str(status.primary_estimated_credits)
            if status.primary_estimated_credits is not None else "UNKNOWN"
        )
    )
    print(f"Shadow source: {status.shadow_source}")
    print(f"Shadow state: {status.shadow_state}")
    print(
        "Chainstack configured for runtime: "
        f"{str(status.chainstack_configured_for_runtime).lower()}"
    )
    print(
        "Chainstack connected: "
        f"{str(status.chainstack_connected).lower()}"
    )
    print(
        "Chainstack comparator: "
        f"{str(status.chainstack_comparator).lower()}"
    )
    print(f"Parity matches: {status.parity_matches}")
    print(f"Chainstack-only: {status.parity_chainstack_only}")
    print(f"Helius-only: {status.parity_helius_only}")
    print(f"Slot mismatches: {status.parity_slot_mismatches}")
    print(f"Decode mismatches: {status.parity_decode_mismatches}")
    # Coverage and durability sit directly under ownership because a connected,
    # singly-owned stream says nothing about either.
    continuity_text = status.source_continuity
    if status.source_unresolved_slots:
        continuity_text += f" ({status.source_unresolved_slots} slots unproven)"
    print(f"Source continuity: {continuity_text}")
    # Continuous-discovery facts, each stated separately so none is inferred
    # from another: live-source state, exact-gap recovery state, the durable
    # migration-journal position, and the curated safety net's HONEST coverage
    # claim (which never says "complete").
    print(f"Live source: {status.live_source_state}")
    print(f"Gap recovery: {status.gap_recovery_state}")
    print("Migration journal: "
          + (f"{status.migration_journal_records} records, "
             f"last confirmed slot "
             + (str(status.migration_journal_confirmed_slot)
                if status.migration_journal_confirmed_slot is not None
                else "NONE")))
    print("Curated coverage claim: "
          f"{status.curated_coverage_claim}")
    print(f"Watch checkpoint durability: {status.watch_checkpoint_durability}")
    print(f"Operational: {status.operational_status}")
    if status.operational_primary_cause:
        print(f"Operational cause: {status.operational_primary_cause}")
    print(f"Market plane: {status.market_plane_status}")
    if status.market_plane_reasons:
        print("Market plane reasons: "
              + ", ".join(status.market_plane_reasons))
    print(f"Market budget mode: {status.market_budget_mode} "
          f"(limit {status.market_budget_limit_display})")
    print("Market physical requests: "
          + (str(status.market_physical_requests)
             if status.market_physical_requests is not None else "UNKNOWN"))
    print("Market request reconciliation: "
          + ("UNKNOWN" if status.market_request_unreconciled_delta is None
             else ("RECONCILED"
                   if status.market_request_unreconciled_delta == 0
                   else f"UNRECONCILED delta="
                        f"{status.market_request_unreconciled_delta}")))
    print(f"Epoch: {short_epoch}")
    print(f"Epoch status: {status.epoch_status}")
    print("Epoch start slot: "
          + (str(status.epoch_start_slot)
             if status.epoch_start_slot is not None else "NONE"))
    print(f"Epoch durable: {status.epoch_durable}")
    print(f"Epoch identity matches: {status.epoch_identity_matches}")
    print(f"Dex backfill: {status.dex_backfill}")
    print("Post-boundary candidates admitted: "
          f"{status.post_boundary_candidates_admitted}")
    print("Pre-boundary candidates ignored: "
          f"{status.pre_boundary_candidates_ignored}")
    print("Restored diagnostic records: "
          f"{status.restored_diagnostic_records}")
    print(f"DEX diagnostic records: {status.dex_diagnostic_records}")
    print("Historical candidates eligible: "
          f"{status.historical_candidates_eligible}")
    print(f"Historical RPC replay: {status.historical_rpc_replay}")
    print(f"Structural policy: {status.structural_policy}")
    print(f"Alert policy: {status.alert_policy}")
    print(f"Circuit: {status.circuit}")
    if status.circuit_reason:
        print(f"Circuit reason: {status.circuit_reason}")
        print(f"Integrity locked: {status.circuit_integrity_locked}")
    print(f"Heartbeat age: {heartbeat}")
    print(f"Last Telegram ping: {status.last_telegram_ping or 'NONE'}")
    print("Paid ledger lines: "
          + (str(status.paid_ledger_lines)
             if status.paid_ledger_lines is not None else "UNKNOWN"))


def _print_refusal(verdict: SafetyVerdict) -> None:
    runtime = verdict.runtime
    if "CIRCUIT_OPEN" in verdict.reasons:
        print(f"Circuit: {runtime.get('circuit_status')}")
        print(f"Circuit reason: {runtime.get('circuit_open_reason')}")
        print("Integrity locked: "
              f"{bool(runtime.get('circuit_integrity_locked'))}")
        print("Operator action: resolve the integrity cause, then use the "
              "guarded watchdog clear-circuit command.")
    print("PHX2 START REFUSED: " + ", ".join(verdict.reasons))


def start(
    backend: OperatorBackend,
    *,
    timeout_seconds: float = DEFAULT_START_TIMEOUT_SECONDS,
) -> int:
    verdict = safety_check(backend)
    if not verdict.safe:
        _print_refusal(verdict)
        return 2
    current = collect_status(backend)
    if current.accepted_running:
        print_status(current)
        return 0
    if current.watchdog_count > 1 or current.producer_count > 1:
        print("PHX2 START REFUSED: ambiguous runtime ownership")
        return 2

    if verdict.handoff_required:
        handoff = backend.closed_epoch_deployment_handoff(record=True)
        if not handoff.allowed or not handoff.existing_record:
            print("PHX2 START REFUSED: closed-epoch deployment handoff "
                  + ", ".join(handoff.refusals or ["AUDIT_WRITE_FAILED"]))
            return 2
        print("Closed-epoch deployment handoff: AUTHENTICATED")

    backend.clear_watchdog_stop()
    if str(verdict.task.get("task_state")) == "Disabled":
        enabled = backend.task_action("enable")
        if not enabled.get("_ok"):
            print("PHX2 START REFUSED: managed task could not be enabled")
            return 2
    started = backend.task_action("start")
    if not started.get("_ok"):
        print("PHX2 START REFUSED: managed watchdog task did not start")
        return 2

    deadline = backend.monotonic() + float(timeout_seconds)
    latest = current
    while backend.monotonic() <= deadline:
        latest = collect_status(backend)
        if latest.circuit != "CLOSED":
            print_status(latest)
            return 2
        if latest.accepted_running:
            print_status(latest)
            return 0
        backend.sleep(POLL_SECONDS)
    print_status(latest)
    print("PHX2 START REFUSED: startup health timeout")
    return 2


def stop(
    backend: OperatorBackend,
    *,
    timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS,
) -> int:
    current = collect_status(backend)
    if current.state != "STOPPED" and not backend.request_watchdog_stop():
        print("PHX2 STOP FAILED: cooperative stop request was not accepted")
        return 2
    deadline = backend.monotonic() + float(timeout_seconds)
    latest = current
    while backend.monotonic() <= deadline:
        latest = collect_status(backend)
        if latest.state == "STOPPED" and latest.producer_count == 0 \
                and latest.watchdog_count == 0 \
                and backend.runtime_locks_absent():
            disabled = backend.task_action("disable")
            if not disabled.get("_ok"):
                print("PHX2 STOP FAILED: managed task could not be disabled")
                return 2
            # STOPPED CLEANLY only after the FINAL process/task/epoch/status
            # invariants agree: zero owners by process truth, and any VALID
            # epoch document durable and identity-matching.  An INVALID epoch
            # document, a live owner claim, or a lingering process prints the
            # contradicting status instead of a clean-stop claim.  This never
            # clears or hides the runtime circuit.
            final = collect_status(backend)
            epoch_ok = (
                final.epoch_document_state == "MISSING"
                or (final.epoch_durable and final.epoch_identity_matches))
            if not (final.state == "STOPPED"
                    and final.producer_count == 0
                    and final.watchdog_count == 0
                    and final.yellowstone_owners in (None, 0)
                    and epoch_ok):
                print_status(final)
                print("PHX2 STOP FAILED: final status invariants disagree "
                      "after shutdown")
                return 2
            print("PHX2 STOPPED CLEANLY")
            return 0
        backend.sleep(POLL_SECONDS)
    print_status(latest)
    print("PHX2 STOP FAILED: cooperative shutdown timed out; no force "
          "termination was attempted")
    return 2


def _print_finalization(verdict: StoppedEpochFinalizationVerdict) -> None:
    checks = verdict.checks
    print("PHX2 STOPPED-EPOCH FINALIZATION")
    print(f"Epoch: {checks.get('epoch_id') or 'NONE'}")
    print(f"Epoch status: {checks.get('epoch_status') or 'UNKNOWN'}")
    print(f"Prior runtime nonce: {checks.get('prior_runtime_nonce') or 'NONE'}")
    print("Prior repository head: "
          f"{checks.get('prior_repository_head') or 'NONE'}")
    print("Derived close time: "
          f"{checks.get('derived_closed_at_utc') or 'NONE'}")
    print("Derived close reason: "
          f"{checks.get('derived_close_reason') or 'NONE'}")
    print(f"Watchdog processes: {checks.get('watchdog_count')}")
    print(f"Producer processes: {checks.get('producer_count')}")
    print("Live or ambiguous locks: "
          f"{checks.get('live_or_ambiguous_lock_count')}")
    print(f"Later re-arm observed: {bool(checks.get('later_rearm_observed'))}")


def finalize_stopped_epoch_command(
    backend: OperatorBackend, *, acknowledged: bool = False
) -> int:
    """Close an already-stopped epoch so a deployment handoff can proceed.

    Without the acknowledgment flag this is a dry run: it reports the close it
    WOULD derive and refuses.  PHX2 is never started, the circuit is never
    cleared and the canonical ledger is never touched by either path.
    """

    preview = backend.stopped_epoch_finalization(
        acknowledged=acknowledged, write=False)
    _print_finalization(preview)
    if preview.already_final:
        print("PHX2 STOPPED-EPOCH FINALIZATION: ALREADY FINALIZED")
        return 0
    if not acknowledged:
        print("PHX2 STOPPED-EPOCH FINALIZATION REFUSED: "
              + ", ".join(preview.refusals))
        print("Operator action: re-run with "
              + FINALIZE_ACKNOWLEDGMENT_FLAG
              + " to write this close.")
        return 2
    if not preview.allowed:
        print("PHX2 STOPPED-EPOCH FINALIZATION REFUSED: "
              + ", ".join(preview.refusals))
        return 2
    verdict = backend.stopped_epoch_finalization(
        acknowledged=True, write=True)
    if not verdict.allowed:
        print("PHX2 STOPPED-EPOCH FINALIZATION REFUSED: "
              + ", ".join(verdict.refusals))
        return 2
    if verdict.already_final:
        print("PHX2 STOPPED-EPOCH FINALIZATION: ALREADY FINALIZED")
        return 0
    print("Finalized generation: "
          f"{verdict.checks.get('finalized_generation')}")
    print("Primary and backup identical: "
          f"{bool(verdict.checks.get('primary_backup_identical'))}")
    print("Preserved prior document: "
          f"{verdict.checks.get('preserved_prior_document_sha256') or 'NONE'}")
    print("PHX2 STOPPED-EPOCH FINALIZED")
    return 0


def restart(
    backend: OperatorBackend,
    *,
    stop_timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    start_timeout_seconds: float = DEFAULT_START_TIMEOUT_SECONDS,
) -> int:
    before = collect_status(backend).epoch_id
    stopped = stop(backend, timeout_seconds=stop_timeout_seconds)
    if stopped != 0:
        return stopped
    started = start(backend, timeout_seconds=start_timeout_seconds)
    if started != 0:
        return started
    after = collect_status(backend)
    if before and after.epoch_id == before:
        print("PHX2 RESTART FAILED: a fresh live epoch was not observed")
        return 2
    return 0


def _safe_command(argv: Sequence[str]) -> Optional[str]:
    if len(argv) == 0:
        return "start"
    if len(argv) == 1 and argv[0] in COMMANDS:
        return str(argv[0])
    # The one argument-bearing command, matched as a closed set rather than
    # parsed: the acknowledgment token is the ONLY accepted second argument, so
    # nothing else can reach the process even before the venv re-exec.
    if argv[0] == FINALIZE_STOPPED_EPOCH_COMMAND and (
            len(argv) == 1
            or (len(argv) == 2 and argv[1] == FINALIZE_ACKNOWLEDGMENT_FLAG)):
        return FINALIZE_STOPPED_EPOCH_COMMAND
    return None


def _ensure_repo_venv(
    argv: Sequence[str],
    *,
    executable: Optional[str] = None,
    execve: Callable[[str, Sequence[str], Mapping[str, str]], Any] = os.execve,
) -> Optional[int]:
    current = executable or sys.executable
    if _same_path(current, REPO_VENV_PYTHON):
        return None
    if not REPO_VENV_PYTHON.is_file():
        print("PHX2 ERROR: repository virtual environment is unavailable.")
        return 2
    if os.environ.get(REEXEC_MARKER) == "1":
        print("PHX2 ERROR: repository virtual environment re-exec failed.")
        return 2
    environment = dict(os.environ)
    environment[REEXEC_MARKER] = "1"
    safe_argv = [
        str(REPO_VENV_PYTHON),
        str(Path(REPO_ROOT) / "main.py"),
        *list(argv),
    ]
    execve(str(REPO_VENV_PYTHON), safe_argv, environment)
    return 2


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    backend: Optional[OperatorBackend] = None,
    enforce_venv: bool = True,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = _safe_command(arguments)
    if command is None:
        print("Usage: python main.py [start|status|stop|restart]")
        print("       python main.py " + FINALIZE_STOPPED_EPOCH_COMMAND
              + " [" + FINALIZE_ACKNOWLEDGMENT_FLAG + "]")
        return 2
    if enforce_venv:
        reexec_result = _ensure_repo_venv(arguments)
        if reexec_result is not None:
            return reexec_result
    if os.name != "nt":
        print("PHX2 ERROR: managed operator startup requires Windows.")
        return 2
    active = backend or OperatorBackend()
    if command == "status":
        print_status(collect_status(active))
        return 0
    if command == "stop":
        return stop(active)
    if command == "restart":
        return restart(active)
    if command == FINALIZE_STOPPED_EPOCH_COMMAND:
        return finalize_stopped_epoch_command(
            active,
            acknowledged=FINALIZE_ACKNOWLEDGMENT_FLAG in arguments)
    return start(active)


__all__ = (
    "COMMANDS",
    "FINALIZE_STOPPED_EPOCH_COMMAND",
    "FINALIZE_ACKNOWLEDGMENT_FLAG",
    "OperatorBackend",
    "OperatorStatus",
    "SafetyVerdict",
    "collect_status",
    "safety_check",
    "print_status",
    "start",
    "stop",
    "restart",
    "finalize_stopped_epoch_command",
    "main",
)
