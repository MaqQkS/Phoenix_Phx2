"""Turn the real world into :class:`~PHX2.watchdog.health.HealthInputs`.

Every read in this module is READ-ONLY.  The cursor and recovery documents are
inspected with the producer's own ``classify_*_checkpoint_file`` helpers, which
open a file, validate an envelope and return -- they never mutate.  The canonical
ledger is opened in binary READ mode only.  There is deliberately no code path in
this package that opens any producer-owned file for writing.

Two measurement lessons from earlier PHX2 ceremonies are honoured here:

* the heartbeat's *lag* figures are snapshot-stale by up to one heartbeat
  interval, so anything positional (recovery progress, unresolved work) is taken
  from the ON-DISK cursor / recovery documents rather than from the heartbeat;
* quarantine, identity-match and durability-status flags are NOT lag-sensitive,
  so those come from the heartbeat's provider telemetry, which is the only place
  the live store publishes them.

A :class:`PreviousObservation` carries the small amount of history needed to say
"did this advance?" -- nothing else is remembered, and it survives a watchdog
restart because the daemon persists it in ``watchdog_status.json``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.free_tier_producer.rpc_gap_recovery import (
    classify_recovery_checkpoint_file,
)
from PHX2.free_tier_producer.stream_cursor import (
    CURSOR_BACKUP_SUFFIX,
    classify_cursor_checkpoint_file,
    cursor_cross_generation_check,
)
from PHX2.free_tier_producer.live_epoch import (
    HISTORICAL_REPLAY_STATUS,
    LEGACY_ALERT_POLICY_BINDING,
    PRODUCTION_MODE as LIVE_EPOCH_PRODUCTION_MODE,
    build_durable_policy_identity,
    classify_live_epoch_document_set,
    closed_epoch_deployment_handoff_is_valid,
    live_epoch_handoff_is_valid,
)
from PHX2.watchdog.config import WatchdogConfig, alert_policy_in_launcher
from PHX2.watchdog.health import (
    CURSOR_DURABILITY_HEALTHY,
    RECOVERY_ACTIVE_STATES,
    RECOVERY_TERMINAL_STATES,
    HealthInputs,
)
from PHX2.watchdog.operational_health import (
    circuit_should_open,
    evaluate_operational_health,
)
from PHX2.models.market_credential import (
    MARKET_CREDENTIAL_FATAL_STATUSES,
    MARKET_CREDENTIAL_STATUSES,
)
from PHX2.watchdog.process import (
    AdoptionVerdict,
    ProcessTable,
    ProducerLockView,
    logical_producer_pids,
)
from PHX2.watchdog.state import (
    file_sha256,
    ledger_identity,
    parse_utc,
    path_digest,
    read_json,
    utc_now_iso,
)

PRODUCER_HEARTBEAT_BASENAME = "producer_heartbeat.json"

#: Top-level heartbeat keys the operational verdict needs but that do NOT live
#: under ``provider_telemetry``: market-plane liveness comes from the session's
#: per-tick watch, the reconciliation block from the market scheduler's stats.
_MARKET_PLANE_HEARTBEAT_KEYS = (
    "market_plane_status",
    "market_plane_reasons",
    "market_plane_blind_age_seconds",
    "market_plane_grace_seconds",
    "scheduler_physical_requests_total",
    "transport_physical_requests_total",
    "reconciled_total",
    "unreconciled_delta",
    "scheduler_charge_delta",
    "reconciliation_reasons",
    "supply_pending",
    "supply_pending_reasons",
    "supply_oldest_pending_age_seconds",
    "supply_systemic_pending_seconds",
    "supply_systemic_failure",
    "supply_successes",
    "supply_central_observations",
)

#: How the heartbeat's source directory relates to the canonical runs root.
HEARTBEAT_SOURCE_CANONICAL = "CANONICAL_RUNS_ROOT_CHILD"
HEARTBEAT_SOURCE_FOREIGN = "FOREIGN_DIRECTORY"
HEARTBEAT_SOURCE_UNKNOWN = "UNKNOWN"

PRODUCTION_POLICY_VALID = "VALID"
PRODUCTION_POLICY_INVALID = "INVALID"
PRODUCTION_POLICY_CONFLICT = "CONFLICT"
PRODUCTION_POLICY_UNRESOLVED = "UNRESOLVED"

PRODUCTION_POLICY_SOURCE_HEARTBEAT = "CURRENT_HEARTBEAT"
PRODUCTION_POLICY_SOURCE_DURABLE = "DURABLE_LIVE_EPOCH"
PRODUCTION_POLICY_SOURCE_NONE = "NONE"

POLICY_REASON_HEARTBEAT = "CURRENT_HEARTBEAT_POLICY_VALID"
POLICY_REASON_DURABLE = "DURABLE_PRESTART_POLICY_VALID"
POLICY_REASON_HEARTBEAT_INVALID = "CURRENT_HEARTBEAT_POLICY_INVALID"
POLICY_REASON_SOURCE_CONFLICT = "HEARTBEAT_DURABLE_POLICY_CONFLICT"
POLICY_REASON_DURABLE_INVALID = "DURABLE_LIVE_EPOCH_POLICY_INVALID"
POLICY_REASON_MISSING = "PRODUCTION_POLICY_UNAVAILABLE"
POLICY_REASON_NONCANONICAL = "NONCANONICAL_POLICY_UNRESOLVED"

# A watchdog poll is measured in seconds, while the observed Windows sharing
# holds during atomic checkpoint replacement are short-lived.  Three complete
# primary+backup reads over 75 ms are enough to span that transient without
# turning observation into an unbounded wait.
CURSOR_SNAPSHOT_MAX_ATTEMPTS = 3
CURSOR_SNAPSHOT_RETRY_DELAYS_SECONDS = (0.025, 0.05)


@dataclass
class PreviousObservation:
    """The minimum history needed for "did it advance?" questions."""

    observed_at_utc: Optional[str] = None
    heartbeat_tick: Optional[int] = None
    heartbeat_ts_utc: Optional[str] = None
    cursor_checkpoint_succeeded_total: Optional[int] = None
    cursor_last_durable_slot: Optional[int] = None
    recovery_episode_generation: Optional[int] = None
    recovery_progress_units: Optional[int] = None
    recovery_last_completed_slot: Optional[int] = None
    recovery_progress_changed_at_utc: Optional[str] = None
    ledger_sha256: Optional[str] = None
    ledger_lines: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observed_at_utc": self.observed_at_utc,
            "heartbeat_tick": self.heartbeat_tick,
            "heartbeat_ts_utc": self.heartbeat_ts_utc,
            "cursor_checkpoint_succeeded_total": (
                self.cursor_checkpoint_succeeded_total),
            "cursor_last_durable_slot": self.cursor_last_durable_slot,
            "recovery_episode_generation": self.recovery_episode_generation,
            "recovery_progress_units": self.recovery_progress_units,
            "recovery_last_completed_slot": self.recovery_last_completed_slot,
            "recovery_progress_changed_at_utc": (
                self.recovery_progress_changed_at_utc),
            "ledger_sha256": self.ledger_sha256,
            "ledger_lines": self.ledger_lines,
        }

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]
                  ) -> "PreviousObservation":
        if not isinstance(data, Mapping):
            return cls()
        def _int(key: str) -> Optional[int]:
            try:
                value = data.get(key)
                return None if value is None else int(value)
            except (TypeError, ValueError):
                return None
        return cls(
            observed_at_utc=data.get("observed_at_utc"),
            heartbeat_tick=_int("heartbeat_tick"),
            heartbeat_ts_utc=data.get("heartbeat_ts_utc"),
            cursor_checkpoint_succeeded_total=_int(
                "cursor_checkpoint_succeeded_total"),
            cursor_last_durable_slot=_int("cursor_last_durable_slot"),
            recovery_episode_generation=_int("recovery_episode_generation"),
            recovery_progress_units=_int("recovery_progress_units"),
            recovery_last_completed_slot=_int("recovery_last_completed_slot"),
            recovery_progress_changed_at_utc=data.get(
                "recovery_progress_changed_at_utc"),
            ledger_sha256=data.get("ledger_sha256"),
            ledger_lines=_int("ledger_lines"),
        )


@dataclass
class Observation:
    """One complete, redaction-safe observation plus its health inputs."""

    inputs: HealthInputs
    previous: PreviousObservation
    facts: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductionPolicyResolution:
    """Authenticated policy source selected for one observation.

    A current live producer heartbeat has precedence, but only when its epoch
    identity agrees with the authenticated durable document.  Before a producer
    exists, the durable live-epoch policy is authoritative.  Canonical
    production never guesses from an absent heartbeat or an unauthenticated
    artifact.
    """

    state: str
    source: str
    production_mode: str
    live_epoch_required: bool
    reason: str
    heartbeat_mode: str = ""
    durable_mode: str = ""


@dataclass(frozen=True)
class CursorSnapshot:
    """One bounded, authenticated logical read of the cursor pair.

    ``facts`` intentionally carries hashes/generations rather than bytes or
    records.  It is therefore safe to persist in watchdog status/incident
    artifacts while still proving whether consecutive reads saw the same file
    identity.
    """

    state: str
    record: Dict[str, Any]
    facts: Dict[str, Any]


def _as_int(value: object) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _cursor_snapshot_from_heartbeat(
    heartbeat: Optional[Mapping[str, Any]]
) -> Dict[str, Any]:
    if not isinstance(heartbeat, Mapping):
        return {}
    telemetry = heartbeat.get("provider_telemetry")
    if not isinstance(telemetry, Mapping):
        return {}
    cursor = telemetry.get("cursor")
    return dict(cursor) if isinstance(cursor, Mapping) else {}


def _provider_telemetry(heartbeat: Optional[Mapping[str, Any]]
                        ) -> Dict[str, Any]:
    if not isinstance(heartbeat, Mapping):
        return {}
    telemetry = heartbeat.get("provider_telemetry")
    return dict(telemetry) if isinstance(telemetry, Mapping) else {}


def _live_epoch_snapshot(
    heartbeat: Optional[Mapping[str, Any]], telemetry: Mapping[str, Any]
) -> Dict[str, Any]:
    direct = (heartbeat or {}).get("live_epoch")
    if isinstance(direct, Mapping):
        return dict(direct)
    nested = telemetry.get("live_epoch")
    if isinstance(nested, Mapping):
        return dict(nested)
    primary = telemetry.get("primary")
    if isinstance(primary, Mapping) and isinstance(primary.get("live_epoch"), Mapping):
        return dict(primary["live_epoch"])
    return {}


def classify_heartbeat_source(run_dir: object,
                             runs_root: object) -> str:
    if run_dir is None:
        return HEARTBEAT_SOURCE_UNKNOWN
    try:
        child = Path(str(run_dir)).expanduser().resolve()
        parent = Path(str(runs_root)).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return HEARTBEAT_SOURCE_UNKNOWN
    return (HEARTBEAT_SOURCE_CANONICAL if parent in child.parents
            else HEARTBEAT_SOURCE_FOREIGN)


def read_heartbeat(run_dir: object) -> Tuple[bool, bool, Optional[Dict[str, Any]]]:
    """``(present, parse_ok, document)`` for one run directory's heartbeat."""

    if run_dir is None:
        return False, True, None
    path = Path(str(run_dir)) / PRODUCER_HEARTBEAT_BASENAME
    if not path.exists():
        return False, True, None
    parse_ok, document = read_json(path)
    if not parse_ok or not isinstance(document, dict):
        return True, False, None
    return True, True, document


def _recovery_record(config: WatchdogConfig) -> Tuple[str, Dict[str, Any]]:
    try:
        classification = classify_recovery_checkpoint_file(
            config.recovery_primary_path)
    except Exception:
        return "INVALID", {}
    record = (classification.records or [{}])
    return str(classification.state), dict(record[0]) if record else {}


def _cursor_file_identity(
    classification: _cpe.FileClassification,
) -> Dict[str, Any]:
    """Redaction-safe identity for one independently authenticated file read."""

    return {
        "state": str(classification.state),
        "reason": str(classification.reason or ""),
        "generation": classification.generation,
        "envelope_digest": classification.envelope_digest,
        "byte_digest": classification.byte_digest,
        "byte_count": (
            len(classification.raw_bytes)
            if classification.raw_bytes is not None else None),
    }


def _classify_cursor_no_raise(
    path: Path,
    classifier: Callable[..., _cpe.FileClassification],
) -> _cpe.FileClassification:
    try:
        return classifier(path)
    except Exception:
        # The producer classifier already converts filesystem OSError into
        # INVALID.  This final boundary also keeps a monkeypatched/provider
        # classifier exception from crashing the watchdog.
        return _cpe.FileClassification(
            path=path,
            state=_cpe.FILE_INVALID,
            reason=_cpe.QUARANTINE_JSON_INVALID,
        )


def read_cursor_checkpoint_snapshot(
    primary_path: object,
    *,
    max_attempts: int = CURSOR_SNAPSHOT_MAX_ATTEMPTS,
    retry_delays_seconds: Tuple[float, ...] = (
        CURSOR_SNAPSHOT_RETRY_DELAYS_SECONDS),
    sleep_fn: Callable[[float], None] = time.sleep,
    classifier: Callable[..., _cpe.FileClassification] = (
        classify_cursor_checkpoint_file),
) -> CursorSnapshot:
    """Read primary+backup as one logical snapshot with bounded stabilization.

    A usable primary plus either a missing backup (the first generation) or a
    cross-generation-consistent authenticated backup is a committed snapshot.
    Any INVALID file or inconsistent generation pair is reread as a whole.
    Only a later fully authenticated pair resolves the transient; repeated
    corruption never inherits validity from an old backup and fails closed.

    The writer's ``.next.tmp`` is deliberately never considered.  It is
    private, pre-commit evidence and cannot authorize a watchdog decision.
    """

    primary = Path(primary_path)
    backup = primary.with_name(primary.name + CURSOR_BACKUP_SUFFIX)
    attempts = max(1, int(max_attempts))
    history: List[Dict[str, Any]] = []

    for attempt_index in range(attempts):
        primary_read = _classify_cursor_no_raise(primary, classifier)
        backup_read = _classify_cursor_no_raise(backup, classifier)
        decision = _cpe.resolve_checkpoint_pair(
            primary_read,
            backup_read,
            cross_generation_check=cursor_cross_generation_check,
        )
        history.append({
            "attempt": attempt_index + 1,
            "primary": _cursor_file_identity(primary_read),
            "backup": _cursor_file_identity(backup_read),
            "pair_status": str(decision.status),
            "selected": decision.selected,
            "quarantine_reason": decision.quarantine_reason,
        })

        both_missing = (
            primary_read.state == _cpe.FILE_MISSING
            and backup_read.state == _cpe.FILE_MISSING)
        backup_acceptable = backup_read.state != _cpe.FILE_INVALID
        committed = bool(
            primary_read.usable
            and backup_acceptable
            and not decision.quarantined
            and decision.selected in ("primary", "backup"))

        if both_missing:
            return CursorSnapshot(
                state=_cpe.FILE_MISSING,
                record={},
                facts={
                    "cursor_snapshot_status": "MISSING",
                    "cursor_snapshot_attempts": attempt_index + 1,
                    "cursor_snapshot_history": history,
                    "cursor_snapshot_selected": None,
                },
            )

        if committed:
            selected = (
                primary_read if decision.selected == "primary" else backup_read)
            records = selected.records or [{}]
            return CursorSnapshot(
                state=str(selected.state),
                record=dict(records[0]) if records else {},
                facts={
                    "cursor_snapshot_status": (
                        "STABLE_AUTHENTICATED"
                        if attempt_index == 0
                        else "CHECKPOINT_ROTATION_IN_PROGRESS_RESOLVED"),
                    "cursor_snapshot_attempts": attempt_index + 1,
                    "cursor_snapshot_history": history,
                    "cursor_snapshot_selected": decision.selected,
                },
            )

        if attempt_index + 1 < attempts:
            delay_index = min(
                attempt_index, max(0, len(retry_delays_seconds) - 1))
            delay = (
                float(retry_delays_seconds[delay_index])
                if retry_delays_seconds else 0.0)
            if delay > 0.0:
                sleep_fn(delay)

    fingerprints = [
        (
            item["primary"]["state"],
            item["primary"]["reason"],
            item["primary"]["byte_digest"],
            item["backup"]["state"],
            item["backup"]["reason"],
            item["backup"]["byte_digest"],
            item["pair_status"],
        )
        for item in history
    ]
    stable = len(set(fingerprints)) == 1
    return CursorSnapshot(
        state="INVALID",
        record={},
        facts={
            "cursor_snapshot_status": (
                "STABLE_INVALID" if stable else "UNRESOLVED_INVALID"),
            "cursor_snapshot_attempts": len(history),
            "cursor_snapshot_history": history,
            "cursor_snapshot_selected": None,
        },
    )


def _cursor_record(
    config: WatchdogConfig,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    snapshot = read_cursor_checkpoint_snapshot(config.cursor_primary_path)
    return snapshot.state, snapshot.record, snapshot.facts


def _epoch_record(config: WatchdogConfig) -> Tuple[str, Dict[str, Any]]:
    try:
        state, record, _facts = classify_live_epoch_document_set(
            config.live_epoch_primary_path)
    except Exception:
        return "INVALID", {}
    if state == "VALID_BACKUP":
        state = "VALID_CURRENT"
    return str(state), dict(record) if isinstance(record, Mapping) else {}


def expected_alert_policy(config: WatchdogConfig) -> str:
    """The alert policy the watchdog expects its producer to be running.

    Read from the launcher the watchdog will actually execute, NOT hardcoded to
    the canonical deployment value.  That is what makes "watchdog expected
    policy matches the producer" a real comparison rather than a restatement of
    a constant: the launcher contract independently refuses any production
    launcher that does not carry exactly one canonical ``--alert-policy``, so
    the two checks are separate and both have to hold.

    A launcher that states no policy (or states it ambiguously) yields the
    committed LEGACY default, which is exactly what such a producer would run.
    """

    try:
        text = Path(config.launcher_path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return LEGACY_ALERT_POLICY_BINDING
    return alert_policy_in_launcher(text) or LEGACY_ALERT_POLICY_BINDING


def _expected_durable_policy(config: WatchdogConfig) -> Dict[str, Any]:
    return build_durable_policy_identity(
        state_dir=config.cursor_state_dir,
        cursor_state_dir=config.cursor_state_dir,
        canonical_ledger_path=config.ledger_path,
        repo_head=config.expected_head,
        launcher_sha256=file_sha256(config.launcher_path),
        delivery_policy="TELEGRAM_ONLY",
        telegram_enabled=True,
        discord_enabled=False,
        structural_policy="SHADOW",
        # Derived from the launcher this watchdog will run, so a producer whose
        # durable identity records a different alert policy fails the
        # identity comparison instead of being silently accepted.
        alert_policy=expected_alert_policy(config),
        # Bounded six-hour DEX candidate recovery is part of the armed
        # Helius-primary production contract (live_epoch canonical policy).
        dex_backfill_enabled=True,
    )


def _durable_policy_valid(
    config: WatchdogConfig,
    *,
    epoch_state: str,
    epoch: Mapping[str, Any],
) -> bool:
    """Validate the policy-bearing portion of an authenticated epoch.

    Older authenticated epoch documents do not have
    ``durable_policy_identity``.  Their explicit policy fields remain a valid
    migration source.  When the identity is present, every safety-bearing
    binding must agree with the current canonical deployment.
    """

    if str(epoch_state) != "VALID_CURRENT":
        return False
    if epoch.get("production_mode") != LIVE_EPOCH_PRODUCTION_MODE:
        return False
    if epoch.get("historical_completeness_required") is not False:
        return False
    if epoch.get("historical_rpc_backfill_enabled") is not False:
        return False
    if epoch.get("historical_recovery_status") != HISTORICAL_REPLAY_STATUS:
        return False

    identity = epoch.get("durable_policy_identity")
    if identity is None:
        return True
    if not isinstance(identity, Mapping):
        return False
    expected = _expected_durable_policy(config)
    if dict(identity) == expected:
        return True
    if not config.strict_canonical:
        # Hermetic watchdog tests and noncanonical offline probes predate the
        # ledger/wallet bindings and deliberately use temporary stand-ins.
        # Production is always strict and does not take this compatibility arm.
        required = (
            "identity_schema",
            "state_directory_binding",
            "cursor_state_directory_binding",
            "production_mode_binding",
            "delivery_policy_binding",
            "telegram_enabled_binding",
            "discord_enabled_binding",
            "structural_policy_binding",
            "alert_policy_binding",
            "historical_rpc_backfill_enabled_binding",
            "dexscreener_restart_backfill_enabled_binding",
        )
        if all(identity.get(key) == expected.get(key) for key in required):
            optional_match = all(
                identity.get(key) is None
                or identity.get(key) == expected.get(key)
                for key in ("repo_head_binding", "launcher_sha256_binding"))
            if optional_match:
                return True
    # Identity portability is NEVER general.  The one exception is an exact,
    # authenticated audit record bound to this definitively CLOSED document.
    # STARTING/HEALTHY/OPEN documents therefore continue to fail closed.
    return closed_epoch_deployment_handoff_is_valid(
        epoch_path=config.live_epoch_primary_path,
        current_policy_identity=expected,
    )


def _heartbeat_policy_values(
    heartbeat: Optional[Mapping[str, Any]],
    telemetry: Mapping[str, Any],
    epoch: Mapping[str, Any],
) -> Tuple[str, object, object, object]:
    """Read current policy fields with explicit heartbeat-first precedence."""

    heartbeat_map = heartbeat if isinstance(heartbeat, Mapping) else {}

    def _value(key: str) -> object:
        for source in (heartbeat_map, telemetry, epoch):
            if key in source:
                return source.get(key)
        return None

    return (
        str(_value("production_mode") or ""),
        _value("historical_completeness_required"),
        _value("historical_rpc_backfill_enabled"),
        _value("historical_recovery_status"),
    )


def resolve_production_policy(
    *,
    config: WatchdogConfig,
    heartbeat_present: bool,
    heartbeat_parse_ok: bool,
    heartbeat: Optional[Mapping[str, Any]],
    telemetry: Mapping[str, Any],
    heartbeat_epoch: Mapping[str, Any],
    producer_alive: bool,
    epoch_disk_state: str,
    epoch_disk_record: Mapping[str, Any],
    epoch_identity_matches: bool,
) -> ProductionPolicyResolution:
    """Resolve canonical recovery policy without trusting heartbeat absence.

    Precedence is deterministic:

    1. a parseable current producer heartbeat whose policy and epoch identity
       agree with authenticated durable state;
    2. authenticated durable live-epoch policy before producer startup;
    3. fail closed for canonical production when neither source is valid.
    """

    heartbeat_mode, heartbeat_completeness, heartbeat_historical_rpc, \
        heartbeat_recovery = _heartbeat_policy_values(
            heartbeat, telemetry, heartbeat_epoch)
    durable_mode = str(epoch_disk_record.get("production_mode") or "")
    durable_valid = _durable_policy_valid(
        config, epoch_state=epoch_disk_state, epoch=epoch_disk_record)
    current_heartbeat = bool(producer_alive and heartbeat_present)

    if current_heartbeat and not bool(config.strict_canonical) \
            and not heartbeat_mode and str(epoch_disk_state) == "MISSING":
        return ProductionPolicyResolution(
            PRODUCTION_POLICY_UNRESOLVED,
            PRODUCTION_POLICY_SOURCE_NONE,
            "",
            False,
            POLICY_REASON_NONCANONICAL,
            heartbeat_mode,
            durable_mode,
        )

    if current_heartbeat:
        if not heartbeat_parse_ok or not isinstance(heartbeat, Mapping):
            return ProductionPolicyResolution(
                PRODUCTION_POLICY_INVALID,
                PRODUCTION_POLICY_SOURCE_HEARTBEAT,
                heartbeat_mode,
                True,
                POLICY_REASON_HEARTBEAT_INVALID,
                heartbeat_mode,
                durable_mode,
            )
        heartbeat_shape_valid = bool(
            heartbeat_mode == LIVE_EPOCH_PRODUCTION_MODE
            and heartbeat_completeness is False
            and heartbeat_historical_rpc is False
            and heartbeat_recovery == HISTORICAL_REPLAY_STATUS
            and epoch_identity_matches
        )
        heartbeat_identity = heartbeat_epoch.get("durable_policy_identity")
        durable_identity = epoch_disk_record.get("durable_policy_identity")
        identity_conflict = bool(
            isinstance(heartbeat_identity, Mapping)
            and isinstance(durable_identity, Mapping)
            and dict(heartbeat_identity) != dict(durable_identity))
        source_conflict = bool(
            durable_valid
            and (
                heartbeat_mode != durable_mode
                or heartbeat_completeness
                != epoch_disk_record.get("historical_completeness_required")
                or heartbeat_historical_rpc
                != epoch_disk_record.get("historical_rpc_backfill_enabled")
                or heartbeat_recovery
                != epoch_disk_record.get("historical_recovery_status")
                or identity_conflict
            ))
        if source_conflict:
            return ProductionPolicyResolution(
                PRODUCTION_POLICY_CONFLICT,
                PRODUCTION_POLICY_SOURCE_HEARTBEAT,
                heartbeat_mode,
                True,
                POLICY_REASON_SOURCE_CONFLICT,
                heartbeat_mode,
                durable_mode,
            )
        if not durable_valid or not heartbeat_shape_valid:
            return ProductionPolicyResolution(
                PRODUCTION_POLICY_INVALID,
                PRODUCTION_POLICY_SOURCE_HEARTBEAT,
                heartbeat_mode,
                True,
                POLICY_REASON_HEARTBEAT_INVALID,
                heartbeat_mode,
                durable_mode,
            )
        return ProductionPolicyResolution(
            PRODUCTION_POLICY_VALID,
            PRODUCTION_POLICY_SOURCE_HEARTBEAT,
            heartbeat_mode,
            True,
            POLICY_REASON_HEARTBEAT,
            heartbeat_mode,
            durable_mode,
        )

    if durable_valid:
        return ProductionPolicyResolution(
            PRODUCTION_POLICY_VALID,
            PRODUCTION_POLICY_SOURCE_DURABLE,
            durable_mode,
            True,
            POLICY_REASON_DURABLE,
            heartbeat_mode,
            durable_mode,
        )

    policy_evidence_present = bool(
        str(epoch_disk_state) != "MISSING"
        or durable_mode
        or heartbeat_mode)
    if bool(config.strict_canonical) or policy_evidence_present:
        return ProductionPolicyResolution(
            PRODUCTION_POLICY_INVALID,
            PRODUCTION_POLICY_SOURCE_DURABLE,
            durable_mode or heartbeat_mode,
            True,
            POLICY_REASON_DURABLE_INVALID
            if policy_evidence_present else POLICY_REASON_MISSING,
            heartbeat_mode,
            durable_mode,
        )

    # Noncanonical offline harnesses may deliberately exercise legacy recovery
    # without a live-epoch policy.  Production configs never take this branch.
    return ProductionPolicyResolution(
        PRODUCTION_POLICY_UNRESOLVED,
        PRODUCTION_POLICY_SOURCE_NONE,
        "",
        False,
        POLICY_REASON_NONCANONICAL,
        heartbeat_mode,
        durable_mode,
    )


def build_observation(
    *,
    config: WatchdogConfig,
    table: ProcessTable,
    lock: ProducerLockView,
    adoption: Optional[AdoptionVerdict],
    run_dir: Optional[str],
    producer_pid: Optional[int],
    producer_alive: bool,
    producer_start_utc: Optional[str],
    operator_stop_requested: bool,
    circuit_open: bool,
    producer_expected: bool,
    repo_head_matches: bool,
    launcher_identity_matches: bool,
    redaction_exposure: bool,
    previous: PreviousObservation,
    now_utc: Optional[str] = None,
) -> Observation:
    """Assemble the full health input set from read-only observations."""

    now = str(now_utc or utc_now_iso())
    now_dt = parse_utc(now)

    present, parse_ok, heartbeat = read_heartbeat(run_dir)
    telemetry = _provider_telemetry(heartbeat)
    cursor_hb = _cursor_snapshot_from_heartbeat(heartbeat)
    epoch_heartbeat = _live_epoch_snapshot(heartbeat, telemetry)
    epoch_disk_state, epoch_disk_record = _epoch_record(config)
    expected_durable_identity = _expected_durable_policy(config)
    stored_durable_identity = epoch_disk_record.get(
        "durable_policy_identity")
    deployment_handoff_authorized = bool(
        epoch_disk_state == "VALID_CURRENT"
        and isinstance(stored_durable_identity, Mapping)
        and dict(stored_durable_identity) != expected_durable_identity
        and closed_epoch_deployment_handoff_is_valid(
            epoch_path=config.live_epoch_primary_path,
            current_policy_identity=expected_durable_identity,
        ))
    heartbeat_epoch_id = epoch_heartbeat.get("live_epoch_id")
    disk_epoch_id = epoch_disk_record.get("live_epoch_id")
    exact_epoch_identity_match = bool(
        isinstance(heartbeat_epoch_id, str) and heartbeat_epoch_id
        and isinstance(disk_epoch_id, str) and disk_epoch_id
        and heartbeat_epoch_id == disk_epoch_id)
    epoch_identity_handoff = bool(
        epoch_disk_state == "VALID_CURRENT"
        and live_epoch_handoff_is_valid(
            epoch_heartbeat, epoch_disk_record))
    current_epoch_identity_matches = bool(
        exact_epoch_identity_match or epoch_identity_handoff)
    policy = resolve_production_policy(
        config=config,
        heartbeat_present=present,
        heartbeat_parse_ok=parse_ok,
        heartbeat=heartbeat,
        telemetry=telemetry,
        heartbeat_epoch=epoch_heartbeat,
        producer_alive=producer_alive,
        epoch_disk_state=epoch_disk_state,
        epoch_disk_record=epoch_disk_record,
        epoch_identity_matches=current_epoch_identity_matches,
    )
    production_mode = policy.production_mode
    live_epoch_required = policy.live_epoch_required
    epoch_identity_matches = True
    if live_epoch_required:
        epoch_record = epoch_disk_record
        durable_prestart = bool(
            policy.state == PRODUCTION_POLICY_VALID
            and policy.source == PRODUCTION_POLICY_SOURCE_DURABLE)
        epoch_identity_matches = bool(
            durable_prestart
            or (
                policy.state == PRODUCTION_POLICY_VALID
                and current_epoch_identity_matches
            ))
        if policy.state == PRODUCTION_POLICY_VALID \
                and epoch_identity_matches:
            epoch_document_state = epoch_disk_state
        elif policy.state == PRODUCTION_POLICY_CONFLICT:
            epoch_document_state = "POLICY_CONFLICT"
        elif producer_alive and present \
                and epoch_disk_state != "VALID_CURRENT":
            epoch_document_state = "IDENTITY_MISMATCH"
        elif epoch_disk_state != "VALID_CURRENT":
            epoch_document_state = epoch_disk_state
        else:
            epoch_document_state = "POLICY_INVALID"
        epoch_status = str(
            epoch_disk_record.get("epoch_status") or "EPOCH_STARTING")
        epoch_durable = bool(
            policy.state == PRODUCTION_POLICY_VALID
            and epoch_disk_state == "VALID_CURRENT"
            and epoch_identity_matches
            and (
                durable_prestart
                or (
                    epoch_heartbeat.get("epoch_durable") is True
                    and (
                        epoch_identity_handoff
                        or epoch_heartbeat.get("epoch_status") == epoch_status)
                )
            ))
        if not epoch_durable and policy.state == PRODUCTION_POLICY_VALID \
                and epoch_disk_state == "VALID_CURRENT" \
                and epoch_identity_matches \
                and epoch_status == "EPOCH_CLOSED":
            # An authenticated, policy-valid, identity-matching CLOSED
            # document IS the durable terminal state -- the close was
            # atomically persisted or the document would not classify
            # VALID_CURRENT.  The producer's heartbeat lags the close by up
            # to a full tick during its own shutdown, and treating that lag
            # as EPOCH_NOT_DURABLE opened an integrity circuit against a
            # cleanly closing producer (2026-07-27T13:13:43Z: disk
            # EPOCH_CLOSED at 13:13:41, heartbeat 3 s stale, circuit
            # integrity-locked while the producer finished its own clean
            # shutdown at 13:13:54).
            epoch_durable = True
    else:
        epoch_identity_handoff = False
        epoch_record = epoch_heartbeat
        epoch_document_state = str(
            epoch_record.get("epoch_document_state") or "MISSING")
        epoch_status = str(
            epoch_record.get("epoch_status") or "EPOCH_STARTING")
        epoch_durable = epoch_record.get("epoch_durable") is True
    epoch_age: Optional[float] = None
    if now_dt is not None:
        epoch_started = parse_utc(epoch_record.get("epoch_started_at_utc"))
        if epoch_started is not None:
            epoch_age = max(0.0, (now_dt - epoch_started).total_seconds())
    # -- heartbeat age / monotonicity ------------------------------------------
    heartbeat_age: Optional[float] = None
    heartbeat_tick = _as_int((heartbeat or {}).get("tick"))
    heartbeat_ts = (heartbeat or {}).get("ts_utc")
    if heartbeat is not None:
        stamp = parse_utc(heartbeat_ts)
        if stamp is not None and now_dt is not None:
            heartbeat_age = max(0.0, (now_dt - stamp).total_seconds())
    tick_regressed = False
    if heartbeat_tick is not None and previous.heartbeat_tick is not None \
            and heartbeat_tick < previous.heartbeat_tick:
        tick_regressed = True
    if heartbeat_ts and previous.heartbeat_ts_utc:
        current_stamp = parse_utc(heartbeat_ts)
        previous_stamp = parse_utc(previous.heartbeat_ts_utc)
        if current_stamp is not None and previous_stamp is not None \
                and current_stamp < previous_stamp:
            tick_regressed = True

    # -- source health ---------------------------------------------------------
    owner_count = _as_int(telemetry.get("total_active_streams"))
    if owner_count is None:
        owner_count = _as_int(telemetry.get("active_streams"))
    max_streams = _as_int(telemetry.get("total_max_active_streams"))
    if max_streams is None:
        max_streams = _as_int(telemetry.get("max_active_streams"))

    watermark = telemetry.get("transport_watermark")
    watermark_age: Optional[float] = None
    if isinstance(watermark, Mapping) and now_dt is not None:
        stamp = parse_utc(watermark.get("transport_last_observed_at_utc")
                          or watermark.get("updated_at_utc"))
        if stamp is not None:
            watermark_age = max(0.0, (now_dt - stamp).total_seconds())

    # -- cursor health ---------------------------------------------------------
    cursor_result = _cursor_record(config)
    if len(cursor_result) == 2:
        # Compatibility for hermetic legacy tests/integrators that monkeypatch
        # the former private two-tuple helper.  The real helper always returns
        # authenticated snapshot facts.
        cursor_state, cursor_record = cursor_result
        cursor_snapshot_facts = {
            "cursor_snapshot_status": "LEGACY_TEST_ADAPTER",
            "cursor_snapshot_attempts": 1,
            "cursor_snapshot_history": [],
            "cursor_snapshot_selected": None,
        }
    else:
        cursor_state, cursor_record, cursor_snapshot_facts = cursor_result
    cursor_attempted = _as_int(cursor_hb.get(
        "grpc_cursor_checkpoint_attempted_total"))
    cursor_succeeded = _as_int(cursor_hb.get(
        "grpc_cursor_checkpoint_succeeded_total"))
    cursor_failed = _as_int(cursor_hb.get(
        "grpc_cursor_checkpoint_failed_total"))
    cursor_advanced: Optional[bool] = None
    if cursor_succeeded is not None \
            and previous.cursor_checkpoint_succeeded_total is not None:
        cursor_advanced = (
            cursor_succeeded > previous.cursor_checkpoint_succeeded_total)
    cursor_durability = str(
        cursor_hb.get("grpc_cursor_durability_status")
        or CURSOR_DURABILITY_HEALTHY)
    cursor_failure_category = cursor_hb.get("grpc_cursor_last_failure_category")
    cursor_last_durable = _as_int(cursor_record.get("last_durable_slot"))

    # -- source continuity -----------------------------------------------------
    # The canonical continuity answer, read from the SAME provider telemetry
    # the producer publishes.  This block is the repair for the observation
    # half of the 2026-07-29 defect: every one of these facts was present in
    # the heartbeat and none of them reached a verdict.
    continuity_state = telemetry.get("source_continuity_state")
    if not isinstance(continuity_state, str):
        nested = telemetry.get("source_continuity")
        continuity_state = (nested.get("continuity_state")
                            if isinstance(nested, Mapping) else None)
    if not isinstance(continuity_state, str):
        continuity_state = None
    coverage_proven = telemetry.get("coverage_proven_continuous")
    if not isinstance(coverage_proven, bool):
        coverage_proven = None
    unresolved_slots = _as_int(telemetry.get("grpc_gap_unresolved_slot_total"))

    # -- watch-checkpoint durability -------------------------------------------
    # A DIFFERENT owner from the cursor checkpoint above, and healthy in the
    # same run this one failed 61 of 63 writes.
    watch_durability = heartbeat.get("checkpoint_durability_status") \
        if isinstance(heartbeat, Mapping) else None
    if not isinstance(watch_durability, str):
        watch_durability = None
    watch_consecutive = _as_int(
        (heartbeat or {}).get("checkpoint_consecutive_failures"))
    watch_structural = _as_int(
        (heartbeat or {}).get("checkpoint_structural_failed_total"))
    watch_quarantined = bool(
        (heartbeat or {}).get("checkpoint_quarantined", False))

    # -- recovery health -------------------------------------------------------
    recovery_audit_state, recovery_audit_record = _recovery_record(config)
    retired_recovery_policy = bool(
        policy.state == PRODUCTION_POLICY_VALID
        and live_epoch_required
        and recovery_audit_state in (
            "VALID_CURRENT", "VALID_LEGACY", "MISSING"))
    if retired_recovery_policy:
        recovery_state_label = "RETIRED_AUDIT_ONLY"
        recovery_record: Dict[str, Any] = {}
        recovery_state = HISTORICAL_REPLAY_STATUS
    else:
        recovery_state_label = recovery_audit_state
        recovery_record = recovery_audit_record
        recovery_state = str(recovery_record.get("recovery_state") or "IDLE")
    recovery_target = _as_int(recovery_record.get("recovery_target_slot"))
    recovery_completed = _as_int(recovery_record.get("produced_blocks_completed"))
    recovery_total = _as_int(recovery_record.get("produced_blocks_total"))
    recovery_last_slot = _as_int(recovery_record.get("last_completed_slot"))
    episode_generation = _as_int(recovery_record.get("episode_generation"))

    # A TERMINAL recovery is one the RECOVERY document itself declares terminal.
    #
    # The cursor's ``recovery_terminal`` flag must NOT be read that way. It records
    # that the provider terminally refused *gRPC replay* from the required
    # boundary (``GRPC_REPLAY_POSITION_TOO_OLD``) -- which is the exact condition
    # the bounded ``rpc_backfill`` recovery mode exists to work around, and the
    # normal inherited state of this deployment. Treating it as an integrity
    # failure would make the watchdog refuse to run the accepted producer at all.
    resumable_episode = recovery_state in RECOVERY_ACTIVE_STATES
    cursor_replay_terminal = bool(
        not live_epoch_required
        and cursor_record.get("recovery_terminal") is True)
    recovery_terminal = bool(
        recovery_state in RECOVERY_TERMINAL_STATES
        or recovery_record.get("terminal_reason") is not None
        # A terminally refused replay with NO open episode to work it IS stuck:
        # nothing will close the gap, and coverage stays unproven forever.
        or (cursor_replay_terminal and not resumable_episode))

    progress_units = recovery_completed
    progress_advanced: Optional[bool] = None
    progress_changed_at = previous.recovery_progress_changed_at_utc
    same_episode = (episode_generation is not None
                    and previous.recovery_episode_generation == episode_generation)
    if progress_units is not None and previous.recovery_progress_units is not None \
            and same_episode:
        progress_advanced = progress_units > previous.recovery_progress_units
        if progress_advanced:
            progress_changed_at = now
    elif progress_units is not None:
        # First sighting of this episode: treat now as the progress epoch so a
        # stall is only ever measured against an interval this watchdog watched.
        progress_changed_at = now
        progress_advanced = None
    no_progress_seconds: Optional[float] = None
    if progress_changed_at is not None and now_dt is not None \
            and recovery_state in RECOVERY_ACTIVE_STATES:
        stamp = parse_utc(progress_changed_at)
        if stamp is not None:
            no_progress_seconds = max(0.0, (now_dt - stamp).total_seconds())

    false_advancement = False
    if same_episode and recovery_last_slot is not None \
            and previous.recovery_last_completed_slot is not None \
            and recovery_last_slot < previous.recovery_last_completed_slot:
        false_advancement = True
    # "Unresolved work crossed" must be measured against the SAFE RESUME
    # boundary, never against ``last_durable_slot``.
    #
    # While a gap is being backfilled the LIVE stream keeps running and its
    # events are QUARANTINED, so the processed high-water mark legitimately sits
    # AHEAD of the backfill target (here: durable 435233755 vs target 435231678,
    # with 167 quarantine segments buffered from 435231678). The invariant that
    # actually matters is that the PROVEN replay boundary stays pinned behind the
    # unresolved episode -- if that advanced past the target, a window the
    # operator believes is covered would have been silently skipped.
    safe_boundary = _as_int(
        cursor_record.get("last_proven_replay_boundary_slot"))
    unresolved_crossed = bool(
        resumable_episode
        and recovery_target is not None
        and safe_boundary is not None
        and safe_boundary > recovery_target)

    # -- delivery health -------------------------------------------------------
    telegram_enabled = bool((heartbeat or {}).get("telegram_enabled", True))
    discord_enabled = bool((heartbeat or {}).get("discord_enabled", False))
    send_capable = (1 if telegram_enabled else 0) + (1 if discord_enabled else 0)
    delivery_unknown = _as_int((heartbeat or {}).get("delivery_unknown_total")) or 0
    delivery_ambiguous = delivery_unknown > 0

    # -- ledger health ---------------------------------------------------------
    ledger = ledger_identity(config.ledger_path)
    ledger_lines = _as_int(ledger.get("lines"))
    ledger_sha = ledger.get("sha256")
    unexpected_rewrite = bool(
        previous.ledger_sha256 is not None and ledger_sha is not None
        and ledger_sha != previous.ledger_sha256
        and ledger_lines is not None and previous.ledger_lines is not None
        and ledger_lines <= previous.ledger_lines)
    concurrent_writer = bool(
        not producer_alive
        and previous.ledger_sha256 is not None and ledger_sha is not None
        and ledger_sha != previous.ledger_sha256)

    ledger_path_matches = True
    if adoption is not None:
        from PHX2.watchdog.process import ADOPT_LEDGER_PATH_MISMATCH
        ledger_path_matches = ADOPT_LEDGER_PATH_MISMATCH not in adoption.reasons

    identity_ok = True
    identity_observed = True
    if adoption is not None:
        identity_ok = bool(adoption.adoptable)
        identity_observed = adoption.producer_pid is not None

    uptime: Optional[float] = None
    if producer_start_utc and now_dt is not None:
        stamp = parse_utc(producer_start_utc)
        if stamp is not None:
            uptime = max(0.0, (now_dt - stamp).total_seconds())

    logical = logical_producer_pids(table)

    inputs = HealthInputs(
        operator_stop_requested=bool(operator_stop_requested),
        circuit_open=bool(circuit_open),
        producer_expected=bool(producer_expected),
        producer_pid=producer_pid,
        producer_alive=bool(producer_alive),
        producer_identity_ok=identity_ok,
        producer_identity_observed=identity_observed,
        logical_producer_count=len(logical),
        unexpected_child_topology=False,
        producer_uptime_seconds=uptime,
        heartbeat_present=present,
        heartbeat_parse_ok=parse_ok,
        heartbeat_age_seconds=heartbeat_age,
        heartbeat_tick_regressed=tick_regressed,
        yellowstone_owner_count=owner_count,
        max_active_streams_observed=max_streams,
        cursor_document_state=cursor_state,
        cursor_quarantined=bool(cursor_hb.get("grpc_cursor_quarantined", False)),
        cursor_identity_match=bool(
            cursor_hb.get("grpc_subscription_identity_match", True)),
        cursor_durability_status=cursor_durability,
        cursor_last_failure_category=cursor_failure_category,
        cursor_checkpoint_attempted_total=cursor_attempted,
        cursor_checkpoint_succeeded_total=cursor_succeeded,
        cursor_checkpoint_failed_total=cursor_failed,
        cursor_succeeded_total_advanced=cursor_advanced,
        source_continuity_state=continuity_state,
        source_coverage_proven_continuous=coverage_proven,
        source_unresolved_slot_total=unresolved_slots,
        watch_checkpoint_durability_status=watch_durability,
        watch_checkpoint_consecutive_failures=watch_consecutive,
        watch_checkpoint_structural_failed_total=watch_structural,
        watch_checkpoint_quarantined=watch_quarantined,
        recovery_document_state=recovery_state_label,
        recovery_state=recovery_state,
        recovery_terminal=recovery_terminal,
        recovery_progress_units=progress_units,
        recovery_progress_advanced=progress_advanced,
        recovery_no_progress_seconds=no_progress_seconds,
        recovery_false_advancement=false_advancement,
        unresolved_work_crossed=unresolved_crossed,
        live_epoch_required=live_epoch_required,
        epoch_document_state=epoch_document_state,
        epoch_status=epoch_status,
        epoch_durable=epoch_durable,
        epoch_age_seconds=epoch_age,
        telegram_enabled=telegram_enabled,
        discord_enabled=discord_enabled,
        send_capable_transport_count=send_capable,
        delivery_state_ambiguous=delivery_ambiguous,
        ledger_parse_ok=bool(ledger.get("parse_ok")),
        ledger_truncated_line=bool(ledger.get("truncated_final_line")),
        ledger_unexpected_rewrite=unexpected_rewrite,
        ledger_concurrent_writer=concurrent_writer,
        ledger_path_matches=ledger_path_matches,
        repo_head_matches=bool(repo_head_matches),
        launcher_identity_matches=bool(launcher_identity_matches),
        redaction_exposure=bool(redaction_exposure),
        unknown_integrity_failure=False,
        startup_grace_seconds=float(config.startup_grace_seconds),
        heartbeat_max_age_seconds=float(config.heartbeat_max_age_seconds),
        recovery_stall_seconds=float(config.recovery_stall_seconds),
    )

    facts: Dict[str, Any] = {
        "observed_at_utc": now,
        "heartbeat_source": classify_heartbeat_source(run_dir, config.runs_root),
        "heartbeat_present": present,
        "heartbeat_parse_ok": parse_ok,
        "heartbeat_age_seconds": heartbeat_age,
        "heartbeat_tick": heartbeat_tick,
        "yellowstone_owner_count": owner_count,
        "max_active_streams_observed": max_streams,
        "transport_watermark_age_seconds": watermark_age,
        "stream_errors_total": _as_int(telemetry.get("stream_errors")),
        "queue_dropped_total": _as_int(telemetry.get("queue_dropped")),
        "events_received_total": _as_int(telemetry.get("events_received")),
        "migration_source_mode": telemetry.get("migration_source_mode"),
        "primary_migration_source": telemetry.get(
            "primary_migration_source"
        ),
        "primary_recovery": telemetry.get("primary_recovery"),
        "shadow_source": telemetry.get("shadow_source"),
        "chainstack_configured_for_runtime": telemetry.get(
            "chainstack_configured_for_runtime"
        ),
        "chainstack_connected": telemetry.get("chainstack_connected"),
        "chainstack_comparator": telemetry.get("chainstack_comparator"),
        "cursor_document_state": cursor_state,
        **cursor_snapshot_facts,
        "cursor_durability_status": cursor_durability,
        "cursor_last_failure_category": cursor_failure_category,
        "cursor_checkpoint_attempted_total": cursor_attempted,
        "cursor_checkpoint_succeeded_total": cursor_succeeded,
        "cursor_checkpoint_failed_total": cursor_failed,
        "cursor_last_durable_slot": cursor_last_durable,
        "source_continuity_state": continuity_state,
        "coverage_proven_continuous": coverage_proven,
        "source_unresolved_slot_total": unresolved_slots,
        "gap_from_slot": telemetry.get("grpc_gap_from_slot"),
        "gap_to_slot": telemetry.get("grpc_gap_to_slot"),
        "gap_size_slots": telemetry.get("grpc_gap_size_slots"),
        "watch_checkpoint_durability_status": watch_durability,
        "watch_checkpoint_consecutive_failures": watch_consecutive,
        "watch_checkpoint_structural_failed_total": watch_structural,
        "watch_checkpoint_quarantined": watch_quarantined,
        "watch_checkpoint_last_failure_detail": (
            heartbeat or {}).get("checkpoint_last_failure_detail"),
        "scheduler_state": (heartbeat or {}).get("scheduler_state"),
        "scheduler_starved_age_seconds": (
            heartbeat or {}).get("market_scheduler_starved_age_seconds"),
        "scheduler_degraded_reasons": (
            heartbeat or {}).get("market_scheduler_degraded_reasons"),
        "dex_backfill_status": (
            (heartbeat or {}).get("dexscreener_restart_backfill") or {}
        ).get("status") if isinstance(
            (heartbeat or {}).get("dexscreener_restart_backfill"),
            Mapping) else None,
        "production_mode": production_mode,
        "production_policy_state": policy.state,
        "production_policy_source": policy.source,
        "production_policy_reason": policy.reason,
        "heartbeat_production_mode": policy.heartbeat_mode,
        "durable_production_mode": policy.durable_mode,
        "live_epoch_required": live_epoch_required,
        "epoch_document_state": epoch_document_state,
        "epoch_status": epoch_status,
        "epoch_durable": epoch_durable,
        "epoch_age_seconds": epoch_age,
        "epoch_identity_matches": epoch_identity_matches,
        "epoch_identity_handoff": epoch_identity_handoff,
        "closed_epoch_deployment_handoff_authorized":
            deployment_handoff_authorized,
        "recovery_document_state": recovery_state_label,
        "recovery_state": recovery_state,
        "retired_recovery_audit_document_state": recovery_audit_state,
        "retired_recovery_audit_prior_state": recovery_audit_record.get(
            "recovery_state"),
        "retired_recovery_audit_terminal_reason": recovery_audit_record.get(
            "terminal_reason"),
        "recovery_episode_generation": episode_generation,
        "recovery_progress_units": progress_units,
        "recovery_progress_total": recovery_total,
        "recovery_progress_advanced": progress_advanced,
        "recovery_no_progress_seconds": no_progress_seconds,
        "recovery_target_slot": recovery_target,
        "recovery_last_completed_slot": recovery_last_slot,
        "recovery_resumable_episode_open": resumable_episode,
        "recovery_prior_terminal_reason": recovery_record.get(
            "prior_terminal_reason"),
        "recovery_terminal_reason": recovery_record.get("terminal_reason"),
        # Observability only: a terminally refused gRPC replay is what
        # rpc_backfill handles, and is NOT by itself an integrity failure.
        "cursor_replay_terminal": cursor_replay_terminal,
        "cursor_safe_resume_boundary_slot": safe_boundary,
        "telegram_enabled": telegram_enabled,
        "discord_enabled": discord_enabled,
        "send_capable_transport_count": send_capable,
        "delivery_unknown_total": delivery_unknown,
        "sent_committed_total": _as_int(
            (heartbeat or {}).get("sent_committed_total")),
        "paid_ledger_sha256": ledger_sha,
        "paid_ledger_bytes": ledger.get("bytes"),
        "paid_ledger_lines": ledger_lines,
        "paid_ledger_parse_ok": bool(ledger.get("parse_ok")),
        "paid_ledger_path_digest": path_digest(config.ledger_path),
        "cursor_state_dir_digest": path_digest(config.cursor_state_dir),
        "logical_producer_pids": logical,
        "producer_lock_present": bool(lock.present),
        "producer_lock_holder_pid": lock.holder_pid,
        "adoption_refusals": list(adoption.reasons) if adoption else [],
    }

    # ONE operational verdict, computed here from the facts above and carried
    # on the observation, so the heartbeat-derived view, ``main.py status``,
    # the watchdog's own observation record and the circuit input all read the
    # SAME evaluation rather than four independent opinions.  Before this the
    # module existed and nothing imported it.
    # Market-plane liveness and request-accounting reconciliation are
    # published at the heartbeat's TOP level (the runner merges the market
    # scheduler's stats there), not inside ``provider_telemetry``.  Overlaid
    # explicitly rather than read from ``telemetry``, which would silently
    # find nothing and report both dimensions NOT_APPLICABLE forever -- the
    # same "the module exists and nothing feeds it" failure this file's own
    # comment below records.
    operational_telemetry = dict(telemetry)
    for key in _MARKET_PLANE_HEARTBEAT_KEYS:
        if key in (heartbeat or {}):
            operational_telemetry[key] = (heartbeat or {})[key]
    _market_credential_status = (heartbeat or {}).get(
        "market_credential_status")
    if _market_credential_status not in MARKET_CREDENTIAL_STATUSES:
        _market_credential_status = None

    operational = evaluate_operational_health(
        telemetry=operational_telemetry,
        watchlist_summary=(heartbeat or {}),
        process_ownership_ok=bool(identity_ok and identity_observed),
        telegram_owner_ok=bool(send_capable <= 1 and not discord_enabled),
        circuit_closed=not bool(circuit_open),
        scheduler_state=(heartbeat or {}).get("scheduler_state"),
        scheduler_starved_age_seconds=(
            heartbeat or {}).get("market_scheduler_starved_age_seconds"),
        ledger_ok=bool(ledger.get("parse_ok"))
        and not bool(ledger.get("truncated_final_line")),
        credentials_integrity_ok=bool(
            repo_head_matches and launcher_identity_matches
            and not redaction_exposure
            and _market_credential_status
            not in MARKET_CREDENTIAL_FATAL_STATUSES),
        credentials_integrity_status=_market_credential_status,
        epoch_healthy=(epoch_status == "EPOCH_HEALTHY" and epoch_durable)
        if live_epoch_required else None,
        stopped=not producer_alive,
    )
    facts.update(operational.to_record())
    _operational_open, _operational_open_reason = circuit_should_open(
        operational)
    facts["circuit_should_open_operational"] = _operational_open
    facts["circuit_should_open_operational_reason"] = (
        _operational_open_reason or None)

    updated_previous = PreviousObservation(
        observed_at_utc=now,
        heartbeat_tick=heartbeat_tick if heartbeat_tick is not None
        else previous.heartbeat_tick,
        heartbeat_ts_utc=heartbeat_ts or previous.heartbeat_ts_utc,
        cursor_checkpoint_succeeded_total=(
            cursor_succeeded if cursor_succeeded is not None
            else previous.cursor_checkpoint_succeeded_total),
        cursor_last_durable_slot=(
            cursor_last_durable if cursor_last_durable is not None
            else previous.cursor_last_durable_slot),
        recovery_episode_generation=(
            episode_generation if episode_generation is not None
            else previous.recovery_episode_generation),
        recovery_progress_units=(
            progress_units if progress_units is not None
            else previous.recovery_progress_units),
        recovery_last_completed_slot=(
            recovery_last_slot if recovery_last_slot is not None
            else previous.recovery_last_completed_slot),
        recovery_progress_changed_at_utc=progress_changed_at,
        ledger_sha256=ledger_sha or previous.ledger_sha256,
        ledger_lines=(ledger_lines if ledger_lines is not None
                      else previous.ledger_lines),
    )

    return Observation(inputs=inputs, previous=updated_previous, facts=facts)


__all__ = (
    "PRODUCER_HEARTBEAT_BASENAME",
    "HEARTBEAT_SOURCE_CANONICAL",
    "HEARTBEAT_SOURCE_FOREIGN",
    "HEARTBEAT_SOURCE_UNKNOWN",
    "PRODUCTION_POLICY_VALID",
    "PRODUCTION_POLICY_INVALID",
    "PRODUCTION_POLICY_CONFLICT",
    "PRODUCTION_POLICY_UNRESOLVED",
    "PRODUCTION_POLICY_SOURCE_HEARTBEAT",
    "PRODUCTION_POLICY_SOURCE_DURABLE",
    "PRODUCTION_POLICY_SOURCE_NONE",
    "PreviousObservation",
    "Observation",
    "ProductionPolicyResolution",
    "classify_heartbeat_source",
    "read_heartbeat",
    "resolve_production_policy",
    "build_observation",
)
