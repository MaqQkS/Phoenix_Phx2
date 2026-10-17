"""The observation layer: real read-only readers feeding the health model.

Proves the wiring the pure health tests assume: heartbeat age and monotonicity,
Yellowstone owner count, cursor and recovery documents read through the
PRODUCER's own classifiers, recovery progress measured from the ON-DISK document
(never from the lag-stale heartbeat), and ledger identity read without writing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PHX2.tests.watchdog._harness import (
    FakeWorld,
    canonical_durable_identity,
    healthy_heartbeat,
    make_config,
)
from PHX2.watchdog.observe import (
    HEARTBEAT_SOURCE_CANONICAL,
    HEARTBEAT_SOURCE_FOREIGN,
    HEARTBEAT_SOURCE_UNKNOWN,
    PreviousObservation,
    build_observation,
    classify_heartbeat_source,
    read_heartbeat,
)
from PHX2.watchdog.process import read_producer_lock


def _observe(config, world, *, previous=None, run_dir=None,
             producer_alive=True, producer_start_utc=None, **kwargs):
    return build_observation(
        config=config, table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        adoption=None, run_dir=run_dir,
        producer_pid=os.getpid() if producer_alive else None,
        producer_alive=producer_alive,
        producer_start_utc=producer_start_utc or world.now(),
        operator_stop_requested=False, circuit_open=False,
        producer_expected=True, repo_head_matches=True,
        launcher_identity_matches=True, redaction_exposure=False,
        previous=previous or PreviousObservation(), now_utc=world.now(),
        **kwargs)


# --- heartbeat ----------------------------------------------------------- #

def test_heartbeat_absent_and_present(tmp_path):
    config = make_config(tmp_path)
    run_dir = tmp_path / "runs" / "r1"
    present, parse_ok, document = read_heartbeat(run_dir)
    assert (present, parse_ok, document) == (False, True, None)

    run_dir.mkdir(parents=True)
    (run_dir / "producer_heartbeat.json").write_text(
        json.dumps(healthy_heartbeat(tick=1, ts_utc="2026-07-26T12:00:00Z")),
        encoding="utf-8")
    present, parse_ok, document = read_heartbeat(run_dir)
    assert present and parse_ok
    assert document["tick"] == 1


def test_bom_prefixed_json_is_read(tmp_path):
    """PowerShell 5.1 `Out-File -Encoding utf8` writes a BOM.

    Strict utf-8 decoding leaves a \\ufeff and json.loads raises
    "Unexpected UTF-8 BOM". That silently cost the watchdog the launcher's
    startup manifest -- and with it the producer's run directory -- so the
    heartbeat could never be located and a healthy producer would eventually be
    restarted for a "stale heartbeat" that was never read.
    """

    from PHX2.watchdog.state import read_json

    target = tmp_path / "manifest.json"
    target.write_bytes(b"\xef\xbb\xbf" + b'{"run_dir":"X","ok":true}')
    assert target.read_bytes()[:3] == b"\xef\xbb\xbf"

    parse_ok, document = read_json(target)
    assert parse_ok is True, "a BOM-prefixed JSON document was rejected"
    assert document["run_dir"] == "X"

    plain = tmp_path / "plain.json"
    plain.write_text('{"a":1}', encoding="utf-8")
    assert read_json(plain) == (True, {"a": 1})


def test_launch_manifest_with_bom_is_absorbed(tmp_path):
    """The end-to-end handshake: run_dir must reach the child handle."""

    import json as _json

    from PHX2.watchdog.daemon import ChildHandle, Watchdog
    from PHX2.watchdog.config import ensure_state_root

    config = make_config(tmp_path)
    ensure_state_root(config)
    run_dir = tmp_path / "runs" / "paid_primary_live_24x7_X"
    log_dir = tmp_path / "operator_logs" / "paid_primary_live_24x7_X"
    manifest = config.launch_manifest_dir / "launch_X.json"
    payload = _json.dumps({
        "run_dir": str(run_dir), "log_dir": str(log_dir),
        "stop_file": str(log_dir / "STOP_REQUESTED")})
    manifest.write_bytes(b"\xef\xbb\xbf" + payload.encode("utf-8"))

    watchdog = Watchdog(config)
    child = ChildHandle(wrapper_pid=1, run_stamp="X",
                        manifest_path=str(manifest),
                        started_at_utc="2026-07-26T12:00:00Z")

    assert watchdog._absorb_manifest(child) is True    # noqa: SLF001
    assert child.run_dir == str(run_dir)
    assert child.stop_file == str(log_dir / "STOP_REQUESTED")


def test_unparseable_heartbeat_is_present_but_not_parseable(tmp_path):
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "producer_heartbeat.json").write_text("{partial",
                                                     encoding="utf-8")
    present, parse_ok, document = read_heartbeat(run_dir)
    assert present is True
    assert parse_ok is False
    assert document is None


def test_heartbeat_age_is_measured_against_now(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir), ts_utc="2026-07-26T11:58:00Z")

    observation = _observe(config, world, run_dir=str(run_dir))

    assert observation.inputs.heartbeat_present is True
    assert observation.inputs.heartbeat_age_seconds == 120.0


def test_regressing_heartbeat_is_detected(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir), tick=10,
                          ts_utc="2026-07-26T12:00:00Z")
    first = _observe(config, world, run_dir=str(run_dir))
    assert first.inputs.heartbeat_tick_regressed is False

    world.write_heartbeat(str(run_dir), tick=4,
                          ts_utc="2026-07-26T11:00:00Z")
    second = _observe(config, world, run_dir=str(run_dir),
                      previous=first.previous)
    assert second.inputs.heartbeat_tick_regressed is True


def test_heartbeat_source_classification(tmp_path):
    config = make_config(tmp_path)
    inside = Path(config.runs_root) / "paid_primary_live_24x7_X"
    assert classify_heartbeat_source(inside, config.runs_root) == (
        HEARTBEAT_SOURCE_CANONICAL)
    assert classify_heartbeat_source(tmp_path / "elsewhere",
                                     config.runs_root) == (
        HEARTBEAT_SOURCE_FOREIGN)
    assert classify_heartbeat_source(None, config.runs_root) == (
        HEARTBEAT_SOURCE_UNKNOWN)


# --- source health ------------------------------------------------------- #

def test_yellowstone_owner_count_comes_from_provider_telemetry(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir), owner_count=1, max_streams=1)
    observation = _observe(config, world, run_dir=str(run_dir))
    assert observation.inputs.yellowstone_owner_count == 1
    assert observation.inputs.max_active_streams_observed == 1

    world.write_heartbeat(str(run_dir), owner_count=2, max_streams=2)
    observation = _observe(config, world, run_dir=str(run_dir))
    assert observation.inputs.yellowstone_owner_count == 2


def test_delivery_posture_comes_from_the_heartbeat(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir))
    observation = _observe(config, world, run_dir=str(run_dir))
    assert observation.inputs.telegram_enabled is True
    assert observation.inputs.discord_enabled is False
    assert observation.inputs.send_capable_transport_count == 1

    world.write_heartbeat(str(run_dir), discord_enabled=True)
    observation = _observe(config, world, run_dir=str(run_dir))
    assert observation.inputs.discord_enabled is True
    assert observation.inputs.send_capable_transport_count == 2


def test_delivery_unknown_marks_ambiguity(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir), delivery_unknown_total=1)
    observation = _observe(config, world, run_dir=str(run_dir))
    assert observation.inputs.delivery_state_ambiguous is True


# --- cursor / recovery documents ---------------------------------------- #

def test_absent_cursor_and_recovery_documents_are_MISSING_not_invalid(tmp_path):
    """A fresh install has no documents yet; that is not corruption."""

    config = make_config(tmp_path)
    world = FakeWorld(config)
    observation = _observe(config, world)
    assert observation.inputs.cursor_document_state == "MISSING"
    assert observation.inputs.recovery_document_state == "MISSING"


def test_corrupt_cursor_document_is_reported_as_invalid(tmp_path):
    config = make_config(tmp_path)
    config.cursor_primary_path.write_text("not an envelope", encoding="utf-8")
    world = FakeWorld(config)
    observation = _observe(config, world)
    assert observation.inputs.cursor_document_state not in (
        "VALID_CURRENT", "VALID_LEGACY", "MISSING")


def test_corrupt_recovery_document_is_reported_as_invalid(tmp_path):
    config = make_config(tmp_path)
    config.recovery_primary_path.write_text("{}", encoding="utf-8")
    world = FakeWorld(config)
    observation = _observe(config, world)
    assert observation.inputs.recovery_document_state not in (
        "VALID_CURRENT", "VALID_LEGACY", "MISSING")


def test_live_epoch_retires_prior_terminal_recovery_to_audit_only(tmp_path):
    """The inherited terminal RPC document cannot poison live-only production."""

    from PHX2.free_tier_producer.rpc_gap_recovery import (
        TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED,
        RpcGapRecoveryStore,
    )
    from PHX2.watchdog.health import HEALTHY, evaluate_health

    config = make_config(tmp_path)
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

    from PHX2.free_tier_producer.live_epoch import LiveEpochManager

    manager = LiveEpochManager(
        state_dir=config.cursor_state_dir,
        now_fn=lambda: "2026-07-26T11:59:00Z",
        id_fn=lambda: "epoch-observation",
        durable_policy_identity=canonical_durable_identity(config),
    )
    manager.observe_confirmed_slot(
        435_000_000, observed_at_utc="2026-07-26T11:59:00Z")
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    heartbeat = healthy_heartbeat(
        tick=1, ts_utc="2026-07-26T12:00:00Z")
    heartbeat["production_mode"] = "LIVE_EPOCH_WITH_DEX_BACKFILL"
    heartbeat["live_epoch"] = manager.snapshot()
    run_dir.mkdir(parents=True)
    (run_dir / "producer_heartbeat.json").write_text(
        json.dumps(heartbeat), encoding="utf-8")

    observation = _observe(config, world, run_dir=str(run_dir))

    assert observation.inputs.live_epoch_required is True
    assert observation.inputs.recovery_document_state == "RETIRED_AUDIT_ONLY"
    assert observation.inputs.recovery_state == (
        "HISTORICAL_BLOCK_REPLAY_RETIRED_FROM_PRODUCTION")
    assert observation.inputs.recovery_terminal is False
    assert observation.facts["retired_recovery_audit_document_state"] == (
        "VALID_CURRENT")
    assert observation.facts["retired_recovery_audit_prior_state"] == (
        "RECOVERY_TERMINAL")
    assert observation.facts["retired_recovery_audit_terminal_reason"] == (
        TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)
    assert evaluate_health(observation.inputs).health_class == HEALTHY

def test_live_epoch_disk_corruption_overrides_healthy_heartbeat(tmp_path):
    """A stale healthy heartbeat cannot hide current durable epoch corruption."""

    from PHX2.free_tier_producer.live_epoch import LiveEpochManager
    from PHX2.watchdog.health import (
        NONRESTARTABLE_INTEGRITY_FAILURE,
        evaluate_health,
    )

    config = make_config(tmp_path)
    manager = LiveEpochManager(
        state_dir=config.cursor_state_dir,
        now_fn=lambda: "2026-07-26T11:59:00Z",
        id_fn=lambda: "epoch-corrupt",
    )
    manager.observe_confirmed_slot(
        435_000_000, observed_at_utc="2026-07-26T11:59:00Z")
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    run_dir.mkdir(parents=True)
    heartbeat = healthy_heartbeat(
        tick=1, ts_utc="2026-07-26T12:00:00Z")
    heartbeat["production_mode"] = "LIVE_EPOCH_WITH_DEX_BACKFILL"
    heartbeat["live_epoch"] = manager.snapshot()
    (run_dir / "producer_heartbeat.json").write_text(
        json.dumps(heartbeat), encoding="utf-8")
    config.live_epoch_primary_path.write_text(
        '{"forged":true}', encoding="utf-8")
    config.live_epoch_primary_path.with_name(
        config.live_epoch_primary_path.name + ".bak").write_text(
            '{"forged_backup":true}', encoding="utf-8")

    observation = _observe(config, world, run_dir=str(run_dir))

    assert observation.inputs.epoch_document_state == "IDENTITY_MISMATCH"
    assert observation.inputs.epoch_durable is False
    assert evaluate_health(observation.inputs).health_class == (
        NONRESTARTABLE_INTEGRITY_FAILURE)


def test_authenticated_epoch_rollover_heartbeat_lag_is_not_corruption(tmp_path):
    """A durable rollover may beat the next periodic heartbeat by one sample."""

    from PHX2.free_tier_producer.live_epoch import LiveEpochManager
    from PHX2.watchdog.health import HEALTHY, evaluate_health

    config = make_config(tmp_path)
    ids = iter(["epoch-old", "epoch-new"])
    manager = LiveEpochManager(
        state_dir=config.cursor_state_dir,
        now_fn=lambda: "2026-07-26T11:59:00Z",
        id_fn=lambda: next(ids),
        durable_policy_identity=canonical_durable_identity(config),
    )
    manager.observe_confirmed_slot(
        435_000_000, observed_at_utc="2026-07-26T11:59:00Z")
    old_epoch = manager.snapshot()
    manager.rollover("PROVIDER_ERROR")
    manager.observe_confirmed_slot(
        435_000_100, observed_at_utc="2026-07-26T11:59:30Z")

    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    run_dir.mkdir(parents=True)
    heartbeat = healthy_heartbeat(
        tick=19, ts_utc="2026-07-26T11:59:35Z")
    heartbeat["production_mode"] = "LIVE_EPOCH_WITH_DEX_BACKFILL"
    heartbeat["live_epoch"] = old_epoch
    (run_dir / "producer_heartbeat.json").write_text(
        json.dumps(heartbeat), encoding="utf-8")

    observation = _observe(config, world, run_dir=str(run_dir))

    assert observation.facts["epoch_identity_handoff"] is True
    assert observation.inputs.epoch_document_state == "VALID_CURRENT"
    assert observation.inputs.epoch_durable is True
    assert evaluate_health(observation.inputs).health_class == HEALTHY


def test_cursor_flags_are_taken_from_the_heartbeat_snapshot(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir), cursor_quarantined=True,
                          cursor_identity_match=False,
                          cursor_durability="STRUCTURAL_CHECKPOINT_FAILURE",
                          checkpoint_attempted=7, checkpoint_succeeded=5,
                          checkpoint_failed=2)
    observation = _observe(config, world, run_dir=str(run_dir))
    assert observation.inputs.cursor_quarantined is True
    assert observation.inputs.cursor_identity_match is False
    assert observation.inputs.cursor_durability_status == (
        "STRUCTURAL_CHECKPOINT_FAILURE")
    assert observation.inputs.cursor_checkpoint_attempted_total == 7
    assert observation.inputs.cursor_checkpoint_succeeded_total == 5
    assert observation.inputs.cursor_checkpoint_failed_total == 2


def test_checkpoint_success_advancement_is_measured_across_observations(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    run_dir = tmp_path / "runs" / "r"
    world.write_heartbeat(str(run_dir), checkpoint_succeeded=10)
    first = _observe(config, world, run_dir=str(run_dir))
    assert first.inputs.cursor_succeeded_total_advanced is None

    world.write_heartbeat(str(run_dir), checkpoint_succeeded=12)
    second = _observe(config, world, run_dir=str(run_dir),
                      previous=first.previous)
    assert second.inputs.cursor_succeeded_total_advanced is True

    world.write_heartbeat(str(run_dir), checkpoint_succeeded=12)
    third = _observe(config, world, run_dir=str(run_dir),
                     previous=second.previous)
    assert third.inputs.cursor_succeeded_total_advanced is False


# --- ledger -------------------------------------------------------------- #

def test_ledger_identity_is_carried_and_the_file_is_unchanged(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    before = Path(config.ledger_path).read_bytes()

    observation = _observe(config, world)

    assert observation.inputs.ledger_parse_ok is True
    assert observation.inputs.ledger_truncated_line is False
    assert observation.facts["paid_ledger_lines"] == 1
    assert observation.facts["paid_ledger_sha256"]
    assert Path(config.ledger_path).read_bytes() == before


def test_ledger_change_while_no_producer_is_a_concurrent_writer(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    first = _observe(config, world, producer_alive=False)

    with open(config.ledger_path, "a", encoding="utf-8") as handle:
        handle.write('{"mint":"OTHER"}\n')

    second = _observe(config, world, producer_alive=False,
                      previous=first.previous)
    assert second.inputs.ledger_concurrent_writer is True


def test_ledger_append_while_producer_alive_is_not_a_rewrite(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    first = _observe(config, world, producer_alive=True)

    with open(config.ledger_path, "a", encoding="utf-8") as handle:
        handle.write('{"mint":"NEWSEND"}\n')

    second = _observe(config, world, producer_alive=True,
                      previous=first.previous)
    assert second.inputs.ledger_unexpected_rewrite is False
    assert second.inputs.ledger_concurrent_writer is False


def test_ledger_rewrite_without_growth_is_flagged(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    first = _observe(config, world, producer_alive=True)

    Path(config.ledger_path).write_text('{"mint":"REPLACED"}\n',
                                        encoding="utf-8")

    second = _observe(config, world, producer_alive=True,
                      previous=first.previous)
    assert second.inputs.ledger_unexpected_rewrite is True


# --- uptime -------------------------------------------------------------- #

def test_producer_uptime_is_derived_from_process_start(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    observation = _observe(config, world,
                           producer_start_utc="2026-07-26T11:55:00Z")
    assert observation.inputs.producer_uptime_seconds == 300.0
