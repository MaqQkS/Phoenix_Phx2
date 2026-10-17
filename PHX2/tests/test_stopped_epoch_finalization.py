"""Authenticated finalization of a stopped-but-open live epoch.

``HANDOFF_PRIOR_EPOCH_NOT_DEFINITIVELY_CLOSED`` (2026-08-02).  The producer for
epoch ``epoch_478d5a2ae49f452b9f8a`` was force terminated after the watchdog's
bounded cooperative-stop window expired, so the in-process
``LiveEpochManager.close()`` at the tail of the provider stream loop never ran.
The durable document stayed ``EPOCH_HEALTHY`` at generation 134 with an empty
process tree, and no surviving component was allowed to close it -- which made
the next deployment handoff permanently unauthorizable.

These tests pin the contract of the new out-of-process finalization: it needs
zero owners, an explicit operator acknowledgment, a prior run authenticated
against its own preserved startup manifest, and a close time and reason DERIVED
from preserved shutdown evidence.  Everything ambiguous refuses.

Offline only.  No socket is opened, no RPC is issued, no Telegram transport is
constructed, no process is started and the canonical ledger is never written.
"""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from pathlib import Path

import pytest

import PHX2.free_tier_producer.epoch_finalization as finallib
import PHX2.free_tier_producer.live_epoch as epochlib
import PHX2.operator_cli as cli


PRIOR_HEAD = "1" * 40
NEW_HEAD = "2" * 40
PRIOR_LAUNCHER = "a" * 64
NEW_LAUNCHER = "b" * 64
RUN_NONCE = "paid_primary_live_24x7_20260802T061317Z"
RUN_STAMP = "20260802T061317Z"

RUN_STARTED = "2026-08-02T06:13:17Z"
EPOCH_OPENED = "2026-08-02T06:13:18Z"
STOP_MARKER = "2026-08-02T06:24:26Z"
STOP_REQUESTED = "2026-08-02T06:24:34Z"
FORCED_AT = "2026-08-02T06:29:38Z"
WATCHDOG_STOPPED = "2026-08-02T06:29:38Z"

PRODUCER_PID = 38960
WATCHDOG_PID = 38076


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def _identity(root: Path, *, head: str, launcher: str, alert_policy: str):
    state = root / "state"
    return epochlib.build_durable_policy_identity(
        state_dir=state,
        cursor_state_dir=state,
        canonical_ledger_path=root / "ledger" / "ping_dedupe.jsonl",
        repo_head=head,
        launcher_sha256=launcher,
        delivery_policy="TELEGRAM_ONLY",
        telegram_enabled=True,
        discord_enabled=False,
        structural_policy="SHADOW",
        alert_policy=alert_policy,
        dex_backfill_enabled=True,
    )


def _write_manifest(watchdog_root: Path, **changes) -> tuple[Path, str]:
    """Write one launch manifest and return ``(path, sha256)``."""

    document = {
        "kind": "PHX2_LIVE_24X7_STARTUP_MANIFEST",
        "schema_version": "PHX2_LIVE_24X7_MANIFEST_V2",
        "run_id": RUN_NONCE,
        "run_stamp": RUN_STAMP,
        "started_at_utc": RUN_STARTED,
        "wrapper_pid": 24308,
        "watchdog_parent_pid": WATCHDOG_PID,
        "pinned_repo_head": PRIOR_HEAD,
        "launcher_sha256": PRIOR_LAUNCHER,
        "alert_policy": "PHX1_PARITY",
    }
    document.update(changes)
    directory = watchdog_root / "launch_manifests"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"launch_{document['run_stamp']}.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _write_watchdog_evidence(
    watchdog_root: Path,
    *,
    marker_at: str = STOP_MARKER,
    requested_at: str = STOP_REQUESTED,
    forced_at: str | None = FORCED_AT,
    completed_at: str | None = None,
    watchdog_stop_at: str | None = WATCHDOG_STOPPED,
    outcome: str = "OPERATOR_STOP",
    extra_events: tuple = (),
    producer_pid: int = PRODUCER_PID,
    run_stamp: str = RUN_STAMP,
) -> None:
    watchdog_root.mkdir(parents=True, exist_ok=True)
    if marker_at:
        (watchdog_root / "OPERATOR_STOP_REQUESTED").write_text(
            f"requested_at_utc={marker_at}\n", encoding="utf-8")
    events = [
        # A prior run's tail, so the scan proves it scopes to THIS run's window
        # instead of reading ordinary restart history as a re-arm.
        {"at_utc": "2026-08-01T06:55:24Z", "kind": "WATCHDOG_STOP",
         "outcome": "OPERATOR_STOP"},
        {"at_utc": "2026-08-02T06:13:17Z", "kind": "RESTART_COMPLETED"},
        {"at_utc": "2026-08-02T06:20:00Z", "kind": "HEALTH_EVALUATED"},
    ]
    if marker_at:
        events.append(
            {"at_utc": marker_at, "kind": "OPERATOR_STOP_MARKER_CREATED"})
    if requested_at:
        events.append(
            {"at_utc": requested_at, "kind": "COOPERATIVE_STOP_REQUESTED"})
    if completed_at:
        events.append(
            {"at_utc": completed_at, "kind": "COOPERATIVE_STOP_COMPLETED"})
    if forced_at:
        events.append({"at_utc": forced_at, "kind": "FORCE_TERMINATION",
                       "target_count": 4})
    if watchdog_stop_at:
        events.append({"at_utc": watchdog_stop_at, "kind": "WATCHDOG_STOP",
                       "outcome": outcome, "cycles": 451})
    events.extend(dict(item) for item in extra_events)
    (watchdog_root / "watchdog_events.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in events), encoding="utf-8")
    (watchdog_root / "current_child.json").write_text(
        json.dumps({
            "kind": "PHX2_WATCHDOG_CURRENT_CHILD",
            "producer_pid": producer_pid,
            "run_stamp": run_stamp,
            "started_at_utc": RUN_STARTED,
        }), encoding="utf-8")


def _open_epoch(root: Path, *, manifest_sha: str, nonce: str = RUN_NONCE):
    """Build an armed, still-open EPOCH_HEALTHY document, as the run left it."""

    state = root / "state"
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: EPOCH_OPENED,
        id_fn=lambda: "epoch_478d5a2ae49f452b9f8a",
        durable_policy_identity=_identity(
            root, head=PRIOR_HEAD, launcher=PRIOR_LAUNCHER,
            alert_policy="PHX1_PARITY"),
        run_instance_identity=epochlib.build_run_instance_identity(
            producer_pid=PRODUCER_PID,
            process_start_utc=RUN_STARTED,
            run_dir=root / "runs" / nonce,
            startup_manifest_digest=manifest_sha,
            watchdog_pid=WATCHDOG_PID,
            launcher_wrapper_pid=15792,
            runtime_nonce=nonce,
        ),
    )
    assert manager.observe_confirmed_slot(436_712_588)
    snapshot = manager.snapshot()
    assert snapshot["epoch_status"] == epochlib.EPOCH_HEALTHY
    return state, state / epochlib.LIVE_EPOCH_BASENAME


@pytest.fixture
def world(tmp_path):
    """A stopped runtime whose epoch is still open, exactly as observed live."""

    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(watchdog_root)
    state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    return {
        "root": root,
        "watchdog_root": watchdog_root,
        "state": state,
        "epoch_path": epoch_path,
        "manifest_sha": manifest_sha,
    }


def _evidence(world_, **changes):
    base = finallib.read_stopped_runtime_shutdown_evidence(
        runtime_nonce=changes.pop("runtime_nonce", RUN_NONCE),
        startup_manifest_binding=changes.pop(
            "startup_manifest_binding", world_["manifest_sha"]),
        watchdog_state_root=world_["watchdog_root"],
        launch_manifest_dir=world_["watchdog_root"] / "launch_manifests",
        operator_stop_marker_path=(
            world_["watchdog_root"] / "OPERATOR_STOP_REQUESTED"),
        events_path=world_["watchdog_root"] / "watchdog_events.jsonl",
        current_child_path=world_["watchdog_root"] / "current_child.json",
    )
    if changes:
        from dataclasses import replace
        base = replace(base, **changes)
    return base


def _context(**changes):
    values = dict(
        operator_acknowledged=True,
        watchdog_count=0,
        producer_count=0,
        yellowstone_owner_count=0,
        telegram_delivery_owner_count=0,
        canonical_ledger_writer_count=0,
        live_or_ambiguous_lock_count=0,
    )
    values.update(changes)
    return finallib.StoppedEpochFinalizationContext(**values)


def _handoff_context(root: Path, **changes):
    values = dict(
        current_repository_head=NEW_HEAD,
        current_launcher_sha256=NEW_LAUNCHER,
        repository_head_is_descendant=True,
        git_clean_and_complete=True,
        current_launcher_canonical=True,
        current_launcher_head_pin_count=1,
        current_launcher_ledger_pin_count=1,
        current_launcher_contract_refusals=(),
        prior_launcher_canonical=True,
        canonical_ledger_path_digest=epochlib._path_digest(  # noqa: SLF001
            root / "ledger" / "ping_dedupe.jsonl"),
        watchdog_count=0,
        producer_count=0,
        yellowstone_owner_count=0,
        telegram_delivery_owner_count=0,
        canonical_ledger_writer_count=0,
        live_or_ambiguous_lock_count=0,
        handoff_at_utc="2026-08-02T07:00:00Z",
    )
    values.update(changes)
    return epochlib.ClosedEpochDeploymentHandoffContext(**values)


def _handoff(world_, **changes):
    return epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=world_["epoch_path"],
        current_policy_identity=_identity(
            world_["root"], head=NEW_HEAD, launcher=NEW_LAUNCHER,
            alert_policy="PHX1_PARITY"),
        context=_handoff_context(world_["root"], **changes),
        handoff_path=(
            world_["state"]
            / epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME),
    )


# --------------------------------------------------------------------------- #
# 1-2: the refusal itself, and what an empty process tree does NOT prove
# --------------------------------------------------------------------------- #


def test_open_healthy_epoch_refuses_deployment_handoff(world):
    """The exact production refusal, reproduced from an open document."""

    verdict = _handoff(world)
    assert not verdict.allowed
    assert epochlib.HANDOFF_PRIOR_NOT_CLOSED in verdict.refusals
    assert verdict.checks["prior_document_state"] == "VALID_CURRENT"
    assert verdict.checks["prior_selected"] == "primary"


def test_zero_live_owners_alone_does_not_satisfy_definitive_closure(world):
    """Every owner count zero, every other predicate met -- still refused."""

    verdict = _handoff(world)
    for key in (
        "watchdog_count",
        "producer_count",
        "yellowstone_owner_count",
        "telegram_delivery_owner_count",
        "canonical_ledger_writer_count",
        "live_or_ambiguous_lock_count",
    ):
        assert verdict.checks[key] == 0
    # Nothing about ownership appears in the refusal; the ONLY thing missing is
    # the definitive close, and an empty process tree may not stand in for it.
    assert verdict.refusals == [epochlib.HANDOFF_PRIOR_NOT_CLOSED]
    assert epochlib._definitive_closed_epoch(  # noqa: SLF001
        json.loads(world["epoch_path"].read_text(encoding="utf-8"))) is None


def test_finalization_still_refuses_without_shutdown_evidence(world):
    """Zero owners does not authorize the close either."""

    (world["watchdog_root"] / "watchdog_events.jsonl").unlink()
    (world["watchdog_root"] / "OPERATOR_STOP_REQUESTED").unlink()
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_MISSING in verdict.refusals


# --------------------------------------------------------------------------- #
# 3-5: the sanctioned finalization
# --------------------------------------------------------------------------- #


def test_stopped_runtime_with_authenticated_evidence_finalizes(world):
    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert verdict.allowed, verdict.refusals
    assert verdict.written
    assert verdict.refusals == []
    assert verdict.close_record["reason"] == finallib.FINALIZED_FORCED
    # Derived from evidence, never "now".
    assert verdict.close_record["closed_at_utc"] == FORCED_AT


def test_finalization_preserves_the_original_open_evidence(world):
    before = json.loads(world["epoch_path"].read_text(encoding="utf-8"))
    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    after = json.loads(world["epoch_path"].read_text(encoding="utf-8"))
    for key in (
        "live_epoch_id",
        "epoch_start_slot",
        "observed_confirmed_boundary_slot",
        "epoch_started_at_utc",
        "epoch_armed_at_utc",
        "rollover_count",
        "durable_policy_identity",
        "run_instance_identity",
        "last_continuity_break",
    ):
        assert after[key] == before[key], key
    # And the exact pre-finalization bytes are archived, not overwritten away.
    prior_sha = hashlib.sha256(
        json.dumps(before, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8")).hexdigest()
    assert prior_sha  # digest computed over the parsed document
    archive_dir = (
        world["state"] / epochlib.LIVE_EPOCH_CLOSED_ARCHIVE_DIRNAME)
    archived = list(archive_dir.glob("*.json"))
    assert len(archived) == 1
    assert json.loads(
        archived[0].read_text(encoding="utf-8")) == before


def test_finalization_invents_no_end_slot_or_timestamp(world):
    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    record = verdict.close_record
    assert set(record) == {
        "live_epoch_id", "epoch_status", "reason", "closed_at_utc",
        "epoch_start_slot", "finalization",
    }
    # The start slot is CARRIED, and no end slot field is invented at all.
    assert record["epoch_start_slot"] == 436_712_589
    assert "epoch_end_slot" not in record
    assert record["closed_at_utc"] in (
        FORCED_AT, STOP_MARKER, STOP_REQUESTED, WATCHDOG_STOPPED)


def test_primary_and_backup_become_identically_closed(world):
    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    primary = world["epoch_path"]
    backup = primary.with_name(
        primary.name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX)
    assert primary.read_bytes() == backup.read_bytes()
    state, document, facts = epochlib.classify_live_epoch_document_set(primary)
    assert state == "VALID_CURRENT"
    assert facts["selected"] == "primary"
    assert facts["generation_conflict"] is False
    assert document["epoch_status"] == epochlib.EPOCH_CLOSED
    backup_state, backup_document = epochlib.classify_live_epoch_document(
        backup)
    assert backup_state == "VALID_CURRENT"
    assert backup_document["epoch_status"] == epochlib.EPOCH_CLOSED
    assert backup_document["generation"] == document["generation"]


def test_epoch_history_receives_the_matching_close_transition(world):
    before = json.loads(world["epoch_path"].read_text(encoding="utf-8"))
    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    after = json.loads(world["epoch_path"].read_text(encoding="utf-8"))
    assert len(after["epoch_history"]) == len(before["epoch_history"]) + 1
    closed = after["epoch_history"][-1]
    assert closed == verdict.close_record
    assert closed["live_epoch_id"] == after["live_epoch_id"]
    assert closed["epoch_status"] == epochlib.EPOCH_CLOSED
    assert closed["epoch_start_slot"] == after["epoch_start_slot"]
    # This is precisely what the handoff's definitive-close predicate reads.
    payload = {k: v for k, v in after.items() if k != "document_digest"}
    assert epochlib._definitive_closed_epoch(payload) is not None  # noqa: SLF001


def test_close_record_binds_nonce_head_and_launcher(world):
    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    attestation = verdict.close_record["finalization"]
    assert attestation["schema_version"] == (
        finallib.STOPPED_EPOCH_FINALIZATION_SCHEMA)
    assert attestation["event_type"] == (
        finallib.STOPPED_EPOCH_FINALIZATION_EVENT)
    assert attestation["prior_runtime_nonce"] == RUN_NONCE
    assert attestation["prior_repository_head"] == PRIOR_HEAD
    assert attestation["prior_launcher_sha256"] == PRIOR_LAUNCHER
    assert attestation["startup_manifest_sha256"] == world["manifest_sha"]
    assert attestation["prior_producer_pid"] == PRODUCER_PID
    assert attestation["prior_watchdog_pid"] == WATCHDOG_PID
    assert attestation["operator_stop_requested_at_utc"] == STOP_MARKER
    assert attestation["watchdog_stop_outcome"] == "OPERATOR_STOP"


def test_cooperative_exit_derives_its_own_close_reason(tmp_path):
    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(
        watchdog_root, forced_at=None, completed_at="2026-08-02T06:25:10Z")
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    world_ = {
        "root": root, "watchdog_root": watchdog_root,
        "epoch_path": epoch_path, "manifest_sha": manifest_sha,
    }
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path,
        evidence=_evidence(world_),
        context=_context(),
    )
    assert verdict.allowed, verdict.refusals
    assert verdict.close_record["reason"] == finallib.FINALIZED_COOPERATIVE
    assert verdict.close_record["closed_at_utc"] == "2026-08-02T06:25:10Z"


# --------------------------------------------------------------------------- #
# 6: idempotence
# --------------------------------------------------------------------------- #


def test_repeating_finalization_is_idempotent(world):
    first = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert first.written
    after_first = world["epoch_path"].read_bytes()
    second = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert second.allowed
    assert second.already_final
    assert not second.written
    assert second.refusals == []
    assert world["epoch_path"].read_bytes() == after_first
    assert second.close_record == first.close_record


def test_idempotent_replay_still_requires_zero_owners(world):
    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(producer_count=1),
    )
    assert verdict.already_final
    assert not verdict.allowed
    assert finallib.FINALIZE_ACTIVE_PRODUCER in verdict.refusals


# --------------------------------------------------------------------------- #
# 7-11: refusal coverage
# --------------------------------------------------------------------------- #


def test_missing_shutdown_evidence_refuses(world):
    (world["watchdog_root"] / "OPERATOR_STOP_REQUESTED").unlink()
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_MISSING in verdict.refusals
    assert verdict.close_record == {}


def test_missing_terminal_watchdog_stop_refuses(tmp_path):
    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(watchdog_root, watchdog_stop_at=None)
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path,
        evidence=_evidence({
            "root": root, "watchdog_root": watchdog_root,
            "epoch_path": epoch_path, "manifest_sha": manifest_sha}),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_MISSING in verdict.refusals


def test_non_operator_watchdog_outcome_refuses(tmp_path):
    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(watchdog_root, outcome="CIRCUIT_OPEN")
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path,
        evidence=_evidence({
            "root": root, "watchdog_root": watchdog_root,
            "epoch_path": epoch_path, "manifest_sha": manifest_sha}),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_MISSING in verdict.refusals


def test_conflicting_shutdown_timestamps_refuse(tmp_path):
    """Termination recorded BEFORE the stop was ever requested."""

    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(
        watchdog_root, forced_at="2026-08-02T06:20:00Z")
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path,
        evidence=_evidence({
            "root": root, "watchdog_root": watchdog_root,
            "epoch_path": epoch_path, "manifest_sha": manifest_sha}),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_CONFLICT in verdict.refusals


def test_both_terminations_recorded_refuses(tmp_path):
    """A cooperative exit AND a forced kill cannot both have happened."""

    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(
        watchdog_root, completed_at="2026-08-02T06:25:10Z",
        forced_at=FORCED_AT)
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path,
        evidence=_evidence({
            "root": root, "watchdog_root": watchdog_root,
            "epoch_path": epoch_path, "manifest_sha": manifest_sha}),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_CONFLICT in verdict.refusals


def test_stale_operator_stop_marker_refuses(world):
    """The marker file survives across runs; a stale one closes nothing.

    ``OPERATOR_STOP_REQUESTED`` is one unversioned file, so a marker left by an
    EARLIER stop is still on disk.  Paired with this run's own termination
    events it would otherwise look like a complete timeline.
    """

    (world["watchdog_root"] / "OPERATOR_STOP_REQUESTED").write_text(
        "requested_at_utc=2026-08-01T00:00:00Z\n", encoding="utf-8")
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_CONFLICT in verdict.refusals


def test_evidence_outside_this_runs_window_is_never_used(tmp_path):
    """Shutdown events belonging to some earlier run are not this run's."""

    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(
        watchdog_root,
        marker_at="2026-08-01T00:00:00Z",
        requested_at="2026-08-01T00:00:01Z",
        forced_at="2026-08-01T00:05:00Z",
        watchdog_stop_at="2026-08-01T00:05:00Z")
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    evidence = _evidence({
        "root": root, "watchdog_root": watchdog_root,
        "epoch_path": epoch_path, "manifest_sha": manifest_sha})
    # Everything before the manifest's own start timestamp is filtered out, so
    # no timeline is derived at all rather than an earlier run's being adopted.
    assert evidence.cooperative_stop_requested_at_utc == ""
    assert evidence.forced_termination_at_utc == ""
    assert evidence.watchdog_stop_at_utc == ""
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path, evidence=evidence, context=_context())
    assert not verdict.allowed
    assert finallib.FINALIZE_EVIDENCE_MISSING in verdict.refusals


def test_wrong_runtime_nonce_refuses(world):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world, manifest_run_id="some_other_run"),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_NONCE_MISMATCH in verdict.refusals


def test_wrong_watchdog_pid_refuses(world):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world, manifest_watchdog_pid=999),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_NONCE_MISMATCH in verdict.refusals


def test_wrong_prior_head_refuses(world):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world, manifest_repository_head="9" * 40),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_HEAD_MISMATCH in verdict.refusals


def test_wrong_prior_launcher_refuses(world):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world, manifest_launcher_sha256="9" * 64),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_LAUNCHER_MISMATCH in verdict.refusals


def test_absent_startup_manifest_refuses(tmp_path):
    """The manifest is selected by CONTENT: no file hashes to the binding."""

    root = tmp_path / "runtime"
    watchdog_root = tmp_path / "watchdog"
    _path, manifest_sha = _write_manifest(watchdog_root)
    _write_watchdog_evidence(watchdog_root)
    _state, epoch_path = _open_epoch(root, manifest_sha=manifest_sha)
    _path.unlink()
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=epoch_path,
        evidence=_evidence({
            "root": root, "watchdog_root": watchdog_root,
            "epoch_path": epoch_path, "manifest_sha": manifest_sha}),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_MANIFEST_UNAVAILABLE in verdict.refusals


def test_tampered_startup_manifest_is_not_selected(world):
    """One edited byte and the manifest no longer authenticates the run."""

    manifest = next(
        (world["watchdog_root"] / "launch_manifests").glob("*.json"))
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["pinned_repo_head"] = "9" * 40
    manifest.write_text(json.dumps(document, indent=2), encoding="utf-8")
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_MANIFEST_UNAVAILABLE in verdict.refusals


def test_later_rearm_refuses_stale_finalization(world):
    """A launch after the terminal stop makes this evidence stale."""

    _write_watchdog_evidence(
        world["watchdog_root"],
        extra_events=(
            {"at_utc": "2026-08-02T07:10:00Z", "kind": "PRODUCER_LAUNCHED"},
        ),
    )
    evidence = _evidence(world)
    assert evidence.later_rearm_observed is True
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=evidence,
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_LATER_REARM in verdict.refusals


def test_later_child_run_stamp_refuses(world):
    _write_watchdog_evidence(
        world["watchdog_root"], run_stamp="20260803T010101Z")
    evidence = _evidence(world)
    assert evidence.later_rearm_observed is True
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=evidence,
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_LATER_REARM in verdict.refusals


def test_ordinary_restart_history_is_not_a_rearm(world):
    """The prior run's own stop + relaunch must not read as a re-arm."""

    evidence = _evidence(world)
    assert evidence.later_rearm_observed is False
    assert evidence.watchdog_stop_at_utc == WATCHDOG_STOPPED
    assert evidence.manifest_started_at_utc == RUN_STARTED


def test_verdict_names_which_evidence_artifacts_were_read(world):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert set(verdict.checks["evidence_sources"]) == {
        "startup_manifest", "operator_stop_marker", "watchdog_events",
        "current_child",
    }
    (world["watchdog_root"] / "OPERATOR_STOP_REQUESTED").unlink()
    refused = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert "operator_stop_marker" not in refused.checks["evidence_sources"]
    assert finallib.FINALIZE_EVIDENCE_MISSING in refused.refusals


def test_missing_operator_acknowledgment_refuses(world):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(operator_acknowledged=False),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_ACK_MISSING in verdict.refusals


@pytest.mark.parametrize("field,refusal", [
    ("watchdog_count", finallib.FINALIZE_ACTIVE_WATCHDOG),
    ("producer_count", finallib.FINALIZE_ACTIVE_PRODUCER),
    ("yellowstone_owner_count", finallib.FINALIZE_ACTIVE_YELLOWSTONE_OWNER),
    ("telegram_delivery_owner_count", finallib.FINALIZE_ACTIVE_TELEGRAM_OWNER),
    ("canonical_ledger_writer_count", finallib.FINALIZE_ACTIVE_LEDGER_WRITER),
    ("live_or_ambiguous_lock_count", finallib.FINALIZE_LIVE_OR_AMBIGUOUS_LOCK),
])
def test_any_live_owner_refuses(world, field, refusal):
    verdict = finallib.validate_stopped_epoch_finalization(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(**{field: 1}),
    )
    assert not verdict.allowed
    assert refusal in verdict.refusals


def test_refused_finalization_writes_nothing(world):
    before = world["epoch_path"].read_bytes()
    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(operator_acknowledged=False),
    )
    assert not verdict.allowed
    assert not verdict.written
    assert world["epoch_path"].read_bytes() == before


def test_producer_written_close_is_never_re_finalized(world):
    """A normal in-process ``close()`` already closed it; leave it alone.

    Its history record carries no finalization attestation, so it is not the
    idempotent replay of THIS path -- and the document is no longer open.  The
    producer's own OPERATOR_SHUTDOWN close must survive byte-for-byte.
    """

    manager = epochlib.LiveEpochManager(
        state_dir=world["state"],
        now_fn=lambda: "2026-08-02T06:24:40Z",
        durable_policy_identity=_identity(
            world["root"], head=PRIOR_HEAD, launcher=PRIOR_LAUNCHER,
            alert_policy="PHX1_PARITY"),
        run_instance_identity=json.loads(
            world["epoch_path"].read_text(
                encoding="utf-8"))["run_instance_identity"],
    )
    manager.close("OPERATOR_SHUTDOWN")
    before = world["epoch_path"].read_bytes()

    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert not verdict.allowed
    assert not verdict.written
    assert not verdict.already_final
    assert finallib.FINALIZE_EPOCH_NOT_OPEN in verdict.refusals
    assert world["epoch_path"].read_bytes() == before
    history = json.loads(
        world["epoch_path"].read_text(encoding="utf-8"))["epoch_history"]
    assert history[-1]["reason"] == "OPERATOR_SHUTDOWN"
    assert "finalization" not in history[-1]


def test_integrity_failure_document_is_never_finalized(world):
    """A corrupt document is not evidence and may not be laundered closed."""

    world["epoch_path"].write_text("{not json", encoding="utf-8")
    backup = world["epoch_path"].with_name(
        world["epoch_path"].name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX)
    backup.write_text("{not json", encoding="utf-8")
    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert not verdict.allowed
    assert finallib.FINALIZE_DOCUMENT_INVALID in verdict.refusals
    assert not verdict.written


# --------------------------------------------------------------------------- #
# 12-13: the handoff after finalization
# --------------------------------------------------------------------------- #


def test_definitively_closed_epoch_allows_the_deployment_handoff(world):
    assert not _handoff(world).allowed
    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    verdict = _handoff(world)
    assert verdict.allowed, verdict.refusals
    assert verdict.refusals == []
    assert verdict.audit_payload["prior_closure_status"] == (
        epochlib.EPOCH_CLOSED)
    assert verdict.audit_payload["prior_closure_reason"] == (
        finallib.FINALIZED_FORCED)


def test_the_new_deployment_binds_phx1_parity(world):
    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    verdict = _handoff(world)
    assert verdict.allowed, verdict.refusals
    assert verdict.checks["prior_alert_policy"] == "PHX1_PARITY"
    assert verdict.checks["current_alert_policy"] == "PHX1_PARITY"
    assert verdict.checks["alert_policy_changed"] is False
    assert verdict.audit_payload["new_alert_policy"] == "PHX1_PARITY"
    assert cli.CANONICAL_ALERT_POLICY == "PHX1_PARITY"


def test_finalization_does_not_authorize_a_semantic_policy_change(world):
    """Closing an epoch never widens what the handoff will accept."""

    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=world["epoch_path"],
        current_policy_identity=_identity(
            world["root"], head=NEW_HEAD, launcher=NEW_LAUNCHER,
            alert_policy="PHX1_PARITY") | {"structural_policy_binding": "LIVE"},
        context=_handoff_context(world["root"]),
        handoff_path=(
            world["state"]
            / epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME),
    )
    assert not verdict.allowed


# --------------------------------------------------------------------------- #
# 14-16: what finalization must NOT touch
# --------------------------------------------------------------------------- #


def test_circuit_and_ledger_are_untouched(tmp_path, world):
    circuit = tmp_path / "circuit_state.json"
    circuit.write_text(json.dumps({"payload": {"status": "CLOSED"}}),
                       encoding="utf-8")
    ledger = world["root"] / "ledger" / "ping_dedupe.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("".join(
        json.dumps({"line": index}) + "\n" for index in range(25)),
        encoding="utf-8")
    circuit_before = circuit.read_bytes()
    ledger_before = ledger.read_bytes()

    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )

    assert circuit.read_bytes() == circuit_before
    assert json.loads(circuit.read_text(
        encoding="utf-8"))["payload"]["status"] == "CLOSED"
    assert ledger.read_bytes() == ledger_before
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 25


def test_watchdog_shutdown_evidence_is_never_rewritten(world):
    watchdog_root = world["watchdog_root"]
    before = {
        path.name: path.read_bytes()
        for path in sorted(watchdog_root.rglob("*")) if path.is_file()}
    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    after = {
        path.name: path.read_bytes()
        for path in sorted(watchdog_root.rglob("*")) if path.is_file()}
    assert after == before


def test_finalization_opens_no_socket_and_starts_no_process(
    world, monkeypatch,
):
    def refuse_socket(*_args, **_kwargs):
        raise AssertionError("network call attempted")

    def refuse_spawn(*_args, **_kwargs):
        raise AssertionError("process start attempted")

    monkeypatch.setattr(socket, "socket", refuse_socket)
    monkeypatch.setattr(socket, "create_connection", refuse_socket)
    monkeypatch.setattr(subprocess, "run", refuse_spawn)
    monkeypatch.setattr(subprocess, "Popen", refuse_spawn)

    verdict = finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )
    assert verdict.written
    assert _handoff(world).allowed


# --------------------------------------------------------------------------- #
# 17-18: honest operator status
# --------------------------------------------------------------------------- #


class _StatusBackend:
    """Minimal backend: durable documents and a stale watchdog observation."""

    def __init__(self, epoch_path: Path, *, observation=None, config=None):
        self.repo_root = Path(".")
        self.epoch_path = epoch_path
        self._observation = (
            {} if observation is None else dict(observation))
        self._config = config

    def task_status(self):
        return {"task_state": "Disabled", "task_present": True,
                "managed_schema_ok": True}

    def watchdog_snapshot(self):
        return {
            "circuit_status": "CLOSED",
            "status": {"health_class": "STOPPED_BY_OPERATOR",
                       "observation": self._observation},
        }

    def process_table(self):
        return []

    def latest_heartbeat(self):
        return {}


def _status(world, monkeypatch, *, observation=None):
    class _Config:
        live_epoch_primary_path = world["epoch_path"]
        cursor_primary_path = world["state"] / "missing_cursor.json"
        recovery_primary_path = world["state"] / "missing_recovery.json"
        cursor_state_dir = str(world["state"])
        ledger_path = str(world["root"] / "ledger" / "ping_dedupe.jsonl")

    monkeypatch.setattr(cli, "resolve_repo_head", lambda root: NEW_HEAD)
    monkeypatch.setattr(
        cli, "default_production_config", lambda **_kwargs: _Config())
    monkeypatch.setattr(
        cli, "ledger_identity", lambda path: {"lines": 25, "sha256": "0" * 64,
                                              "parse_ok": True})
    monkeypatch.setattr(cli, "_last_ledger_timestamp", lambda path: None)
    return cli.collect_status(
        _StatusBackend(world["epoch_path"], observation=observation))


def test_stopped_status_reports_epoch_closed_after_finalization(
    world, monkeypatch,
):
    stale = {"epoch_status": "EPOCH_HEALTHY", "epoch_durable": True,
             "epoch_identity_matches": True, "yellowstone_owner_count": 1}
    before = _status(world, monkeypatch, observation=stale)
    assert before.state == "STOPPED"
    assert before.epoch_status == "EPOCH_HEALTHY"

    finallib.finalize_stopped_epoch(
        epoch_path=world["epoch_path"],
        evidence=_evidence(world),
        context=_context(),
    )

    after = _status(world, monkeypatch, observation=stale)
    assert after.state == "STOPPED"
    # The durable document is authoritative: a stale observation still claiming
    # EPOCH_HEALTHY must not override an authenticated closed document.
    assert after.epoch_status == epochlib.EPOCH_CLOSED
    assert after.epoch_durable is True
    assert after.epoch_document_state == "VALID_CURRENT"
    assert after.accepted_running is False


def test_status_does_not_default_epoch_fields_when_evidence_is_absent(
    world, monkeypatch,
):
    world["epoch_path"].unlink()
    world["epoch_path"].with_name(
        world["epoch_path"].name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX).unlink()
    status = _status(world, monkeypatch, observation={})
    assert status.epoch_document_state == "MISSING"
    # Previously defaulted to EPOCH_STARTING and identity-matches True, i.e. a
    # live-looking epoch invented out of no evidence at all.
    assert status.epoch_status == "UNKNOWN"
    assert status.epoch_id is None
    assert status.epoch_start_slot is None
    assert status.epoch_durable is False
    assert status.epoch_identity_matches is False
    assert status.accepted_running is False


def test_status_does_not_claim_identity_match_without_an_observation(
    world, monkeypatch,
):
    status = _status(world, monkeypatch, observation={})
    assert status.epoch_document_state == "VALID_CURRENT"
    assert status.epoch_identity_matches is False


# --------------------------------------------------------------------------- #
# operator CLI surface
# --------------------------------------------------------------------------- #


class _FinalizeBackend:
    def __init__(self, verdicts):
        self.repo_root = Path(".")
        self.calls = []
        self._verdicts = verdicts

    def stopped_epoch_finalization(self, *, acknowledged=False, write=False):
        self.calls.append((bool(acknowledged), bool(write)))
        return self._verdicts(acknowledged, write)


def _verdict(**changes):
    values = dict(
        allowed=True, refusals=[], checks={}, close_record={},
        already_final=False, written=False)
    values.update(changes)
    return finallib.StoppedEpochFinalizationVerdict(**values)


def test_cli_requires_the_acknowledgment_token():
    backend = _FinalizeBackend(
        lambda ack, write: _verdict(
            allowed=False, refusals=[finallib.FINALIZE_ACK_MISSING]))
    assert cli.finalize_stopped_epoch_command(
        backend, acknowledged=False) == 2
    # A dry run validates and reports; it NEVER writes.
    assert backend.calls == [(False, False)]


def test_cli_writes_only_after_acknowledgment():
    def verdicts(ack, write):
        return _verdict(written=bool(write),
                        checks={"finalized_generation": 3,
                                "primary_backup_identical": True})

    backend = _FinalizeBackend(verdicts)
    assert cli.finalize_stopped_epoch_command(backend, acknowledged=True) == 0
    assert backend.calls == [(True, False), (True, True)]


def test_cli_reports_an_already_finalized_epoch_without_writing():
    backend = _FinalizeBackend(
        lambda ack, write: _verdict(already_final=True))
    assert cli.finalize_stopped_epoch_command(backend, acknowledged=True) == 0
    assert backend.calls == [(True, False)]


def test_cli_command_parsing_is_a_closed_set():
    assert cli._safe_command(  # noqa: SLF001
        [cli.FINALIZE_STOPPED_EPOCH_COMMAND]) == (
            cli.FINALIZE_STOPPED_EPOCH_COMMAND)
    assert cli._safe_command([  # noqa: SLF001
        cli.FINALIZE_STOPPED_EPOCH_COMMAND,
        cli.FINALIZE_ACKNOWLEDGMENT_FLAG]) == (
            cli.FINALIZE_STOPPED_EPOCH_COMMAND)
    for argv in (
        [cli.FINALIZE_STOPPED_EPOCH_COMMAND, "--force"],
        [cli.FINALIZE_STOPPED_EPOCH_COMMAND,
         cli.FINALIZE_ACKNOWLEDGMENT_FLAG, "extra"],
        ["finalize", cli.FINALIZE_ACKNOWLEDGMENT_FLAG],
        ["start", cli.FINALIZE_ACKNOWLEDGMENT_FLAG],
    ):
        assert cli._safe_command(argv) is None, argv  # noqa: SLF001


def test_cli_finalization_never_starts_phx2(monkeypatch):
    started = []
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr(
        cli, "start", lambda backend, **_: started.append("start") or 0)
    monkeypatch.setattr(
        cli, "finalize_stopped_epoch_command",
        lambda backend, *, acknowledged: 0)
    backend = _FinalizeBackend(lambda ack, write: _verdict())
    assert cli.main(
        [cli.FINALIZE_STOPPED_EPOCH_COMMAND,
         cli.FINALIZE_ACKNOWLEDGMENT_FLAG],
        backend=backend, enforce_venv=False) == 0
    assert started == []
