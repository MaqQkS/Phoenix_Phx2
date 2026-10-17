"""Pre-start live-epoch policy resolution for retired recovery evidence.

All files live below ``tmp_path``.  The suite never opens a production ledger,
loads an environment file, connects a provider, or constructs a transport.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

from PHX2.free_tier_producer.live_epoch import (
    HISTORICAL_REPLAY_STATUS,
    PRODUCTION_MODE,
    LiveEpochManager,
    build_durable_policy_identity,
)
from PHX2.free_tier_producer.rpc_gap_recovery import (
    TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED,
    RpcGapRecoveryStore,
)
from PHX2.tests.watchdog._harness import (
    FakeWorld,
    find_dead_pid,
    healthy_heartbeat,
    make_config,
    make_watchdog,
)
from PHX2.watchdog.health import (
    NONRESTARTABLE_INTEGRITY_FAILURE,
    RESTARTABLE_PROCESS_FAILURE,
    REASON_EPOCH_DOCUMENT_INVALID,
    REASON_LAUNCHER_IDENTITY_MISMATCH,
    REASON_RECOVERY_DOCUMENT_INVALID,
    REASON_RECOVERY_TERMINAL,
    REASON_REPO_HEAD_MISMATCH,
    evaluate_health,
)
from PHX2.watchdog.observe import (
    POLICY_REASON_DURABLE,
    PRODUCTION_POLICY_CONFLICT,
    PRODUCTION_POLICY_INVALID,
    PRODUCTION_POLICY_SOURCE_DURABLE,
    PRODUCTION_POLICY_SOURCE_HEARTBEAT,
    PRODUCTION_POLICY_VALID,
    PreviousObservation,
    build_observation,
    expected_alert_policy,
)
from PHX2.watchdog.process import read_producer_lock
from PHX2.watchdog.state import file_sha256


def _strict_config(tmp_path):
    return replace(make_config(tmp_path), strict_canonical=True)


def _durable_identity(config, *, state_dir=None):
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
        # Must match the watchdog's expected durable policy, which derives the
        # alert policy from the launcher this config points at.
        alert_policy=expected_alert_policy(config),
        # Canonical production policy (2026-07-30 remediation): bounded DEX
        # candidate recovery enabled; must match the watchdog's expected
        # durable policy.
        dex_backfill_enabled=True,
    )


def _write_healthy_epoch(config, *, identity=None):
    manager = LiveEpochManager(
        state_dir=config.cursor_state_dir,
        now_fn=lambda: "2026-07-27T04:50:00Z",
        id_fn=lambda: "epoch-prestart-policy",
        durable_policy_identity=identity or _durable_identity(config),
    )
    assert manager.observe_confirmed_slot(
        435_462_546, observed_at_utc="2026-07-27T04:50:01Z")
    return manager


def _write_terminal_recovery(config):
    recovery = RpcGapRecoveryStore(state_dir=config.cursor_state_dir)
    recovery.load()
    active = recovery.state.clone()
    active.recovery_state = "RPC_BACKFILL_RUNNING"
    active.entry_classification = "REPLAY_REFUSED_OUT_OF_RANGE"
    active.recovery_mode = "rpc_backfill"
    active.authoritative_commitment = "confirmed"
    active.safe_from_slot = 435_085_972
    active.recovery_target_slot = 435_231_678
    active.produced_blocks_total = 145_707
    active.produced_blocks_completed = 1
    active.last_completed_slot = 435_085_973
    active.episode_generation = 1
    active.subscription_identity_digest = "d" * 64
    recovery._persist_state_locked(active)  # noqa: SLF001
    recovery.mark_terminal(
        reason=TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)


def _observe(
    config,
    world,
    *,
    run_dir=None,
    producer_alive=False,
    repo_head_matches=True,
    launcher_identity_matches=True,
):
    return build_observation(
        config=config,
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        adoption=None,
        run_dir=run_dir,
        producer_pid=os.getpid() if producer_alive else None,
        producer_alive=producer_alive,
        producer_start_utc=world.now(),
        operator_stop_requested=False,
        circuit_open=False,
        producer_expected=True,
        repo_head_matches=repo_head_matches,
        launcher_identity_matches=launcher_identity_matches,
        redaction_exposure=False,
        previous=PreviousObservation(),
        now_utc=world.now(),
    )


def _write_current_heartbeat(config, world, manager, **overrides):
    run_dir = Path(config.runs_root) / "current"
    heartbeat = healthy_heartbeat(
        tick=1, ts_utc="2026-07-26T12:00:00Z")
    heartbeat["production_mode"] = PRODUCTION_MODE
    heartbeat["live_epoch"] = manager.snapshot()
    heartbeat.update(overrides)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "producer_heartbeat.json").write_text(
        json.dumps(heartbeat), encoding="utf-8")
    return str(run_dir)


def _rewrite_authenticated_epoch(config, **updates):
    primary = config.live_epoch_primary_path
    document = json.loads(primary.read_text(encoding="utf-8"))
    payload = {key: value for key, value in document.items()
               if key != "document_digest"}
    payload.update(updates)
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()
    body = json.dumps(
        {**payload, "document_digest": digest},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    primary.write_text(body, encoding="utf-8")
    primary.with_name(primary.name + ".bak").write_text(
        body, encoding="utf-8")


def test_no_heartbeat_uses_authenticated_durable_policy_and_retires_audit(
        tmp_path):
    config = _strict_config(tmp_path)
    _write_healthy_epoch(config)
    _write_terminal_recovery(config)
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_VALID)
    assert observation.facts["production_policy_source"] == (
        PRODUCTION_POLICY_SOURCE_DURABLE)
    assert observation.facts["production_policy_reason"] == (
        POLICY_REASON_DURABLE)
    assert observation.facts["production_mode"] == PRODUCTION_MODE
    assert observation.inputs.live_epoch_required is True
    assert observation.inputs.epoch_document_state == "VALID_CURRENT"
    assert observation.inputs.epoch_durable is True
    assert observation.inputs.recovery_document_state == "RETIRED_AUDIT_ONLY"
    assert observation.inputs.recovery_state == HISTORICAL_REPLAY_STATUS
    assert observation.inputs.recovery_terminal is False
    assert verdict.health_class == RESTARTABLE_PROCESS_FAILURE


def test_current_identity_valid_heartbeat_has_precedence(tmp_path):
    config = _strict_config(tmp_path)
    manager = _write_healthy_epoch(config)
    world = FakeWorld(config)
    run_dir = _write_current_heartbeat(config, world, manager)

    observation = _observe(
        config, world, run_dir=run_dir, producer_alive=True)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_VALID)
    assert observation.facts["production_policy_source"] == (
        PRODUCTION_POLICY_SOURCE_HEARTBEAT)
    assert observation.inputs.epoch_durable is True


def test_current_heartbeat_and_durable_policy_conflict_fails_closed(tmp_path):
    config = _strict_config(tmp_path)
    manager = _write_healthy_epoch(config)
    world = FakeWorld(config)
    run_dir = _write_current_heartbeat(
        config, world, manager,
        historical_rpc_backfill_enabled=True)

    observation = _observe(
        config, world, run_dir=run_dir, producer_alive=True)
    verdict = evaluate_health(observation.inputs)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_CONFLICT)
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_DOCUMENT_INVALID in verdict.reasons


def test_invalid_durable_epoch_fails_closed_before_start(tmp_path):
    config = _strict_config(tmp_path)
    _write_healthy_epoch(config)
    config.live_epoch_primary_path.write_text("{forged", encoding="utf-8")
    config.live_epoch_primary_path.with_name(
        config.live_epoch_primary_path.name + ".bak").write_text(
            "{forged-backup", encoding="utf-8")
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_INVALID)
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_DOCUMENT_INVALID in verdict.reasons


def test_missing_heartbeat_and_missing_durable_policy_fail_closed(tmp_path):
    config = _strict_config(tmp_path)
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_INVALID)
    assert observation.inputs.live_epoch_required is True
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_DOCUMENT_INVALID in verdict.reasons


def test_historical_replay_unexpectedly_enabled_fails_closed(tmp_path):
    config = _strict_config(tmp_path)
    _write_healthy_epoch(config)
    _rewrite_authenticated_epoch(
        config, historical_rpc_backfill_enabled=True)
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_INVALID)
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_DOCUMENT_INVALID in verdict.reasons


def test_genuine_active_recovery_terminal_remains_blocking(tmp_path):
    config = make_config(tmp_path)
    _write_terminal_recovery(config)
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.inputs.live_epoch_required is False
    assert observation.inputs.recovery_state == "RECOVERY_TERMINAL"
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_RECOVERY_TERMINAL in verdict.reasons


def test_invalid_retired_recovery_audit_remains_blocking(tmp_path):
    config = _strict_config(tmp_path)
    _write_healthy_epoch(config)
    config.recovery_primary_path.write_text("{}", encoding="utf-8")
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.inputs.recovery_document_state != "RETIRED_AUDIT_ONLY"
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_RECOVERY_DOCUMENT_INVALID in verdict.reasons


def test_repository_and_launcher_identity_mismatches_still_block(tmp_path):
    config = _strict_config(tmp_path)
    _write_healthy_epoch(config)
    world = FakeWorld(config)

    observation = _observe(
        config, world, repo_head_matches=False,
        launcher_identity_matches=False)
    verdict = evaluate_health(observation.inputs)

    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_REPO_HEAD_MISMATCH in verdict.reasons
    assert REASON_LAUNCHER_IDENTITY_MISMATCH in verdict.reasons


def test_durable_policy_state_directory_mismatch_fails_closed(tmp_path):
    config = _strict_config(tmp_path)
    wrong_state = tmp_path / "wrong_state"
    identity = _durable_identity(config, state_dir=wrong_state)
    _write_healthy_epoch(config, identity=identity)
    world = FakeWorld(config)

    observation = _observe(config, world)
    verdict = evaluate_health(observation.inputs)

    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_INVALID)
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_EPOCH_DOCUMENT_INVALID in verdict.reasons


def test_prestart_policy_reaches_tested_dead_lock_reclamation_path(tmp_path):
    config = make_config(tmp_path)
    _write_healthy_epoch(config)
    _write_terminal_recovery(config)
    world = FakeWorld(config)
    dead_pid = find_dead_pid()
    world.write_producer_lock(dead_pid)
    watchdog = make_watchdog(config, world)

    result = watchdog.run(max_cycles=1)

    assert result.exit_code == 0
    assert len(world.spawns) == 1
    assert not config.producer_runtime_lock_path.read_text(
        encoding="utf-8").startswith(f"{dead_pid}|")
    events = config.events_path.read_text(encoding="utf-8")
    assert "STALE_PRODUCER_LOCK_REMOVED" in events
    assert "STALE_LOCK_OWNER_PROVEN_DEAD" in events
