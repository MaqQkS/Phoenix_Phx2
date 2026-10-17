from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import PHX2.free_tier_producer.live_epoch as epochlib
from PHX2.free_tier_producer.compat import (
    production_live_artifacts as redaction_artifacts,
)
from PHX2.tests.watchdog._harness import FakeWorld, make_config
from PHX2.watchdog.observe import (
    PRODUCTION_POLICY_SOURCE_DURABLE,
    PRODUCTION_POLICY_VALID,
    PreviousObservation,
    build_observation,
    expected_alert_policy,
)
from PHX2.watchdog.process import read_producer_lock
from PHX2.watchdog.state import file_sha256


OLD_HEAD = "1" * 40
NEW_HEAD = "2" * 40
NEXT_HEAD = "3" * 40
OLD_LAUNCHER = "a" * 64
NEW_LAUNCHER = "b" * 64
NEXT_LAUNCHER = "c" * 64
NOW = "2026-07-27T06:00:00Z"


def _identity(
    root: Path,
    *,
    head: str,
    launcher: str,
    state_dir: Path | None = None,
    cursor_dir: Path | None = None,
    ledger_path: Path | None = None,
    **changes,
):
    state = state_dir or root / "state"
    cursor = cursor_dir or state
    ledger = ledger_path or root / "ledger" / "ping_dedupe.jsonl"
    # Canonical production policy (2026-07-30 remediation): bounded six-hour
    # DEX candidate recovery is part of the armed contract, so identities
    # default to enabled unless a test explicitly models a legacy epoch.
    dex_backfill_enabled = bool(
        changes.pop("dex_backfill_enabled", True)
    )
    identity = epochlib.build_durable_policy_identity(
        state_dir=state,
        cursor_state_dir=cursor,
        canonical_ledger_path=ledger,
        repo_head=head,
        launcher_sha256=launcher,
        delivery_policy="TELEGRAM_ONLY",
        telegram_enabled=True,
        discord_enabled=False,
        structural_policy="SHADOW",
        dex_backfill_enabled=dex_backfill_enabled,
    )
    identity.update(changes)
    return identity


def _closed_prior(
    root: Path, *, legacy: bool = True, dex_backfill_enabled: bool = True,
):
    state = root / "state"
    old_identity = _identity(
        root,
        head=OLD_HEAD,
        launcher=OLD_LAUNCHER,
        dex_backfill_enabled=dex_backfill_enabled,
    )
    if legacy:
        for key in (
            "canonical_ledger_path_binding",
            "wallet_enabled_binding",
            "signing_enabled_binding",
            "trading_enabled_binding",
        ):
            old_identity.pop(key)
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-prior-closed",
        durable_policy_identity=old_identity,
        run_instance_identity={"identity_schema":
                               epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
                               "runtime_nonce": "prior"},
    )
    assert manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")
    return state, state / epochlib.LIVE_EPOCH_BASENAME


def _current(root: Path, **changes):
    return _identity(
        root, head=NEW_HEAD, launcher=NEW_LAUNCHER, **changes)


def _context(root: Path, **changes):
    base = epochlib.ClosedEpochDeploymentHandoffContext(
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
        handoff_at_utc=NOW,
    )
    return replace(base, **changes)


def _validate(
    root: Path, *, identity=None, context=None,
    prior_dex_backfill_enabled: bool = True,
):
    _, epoch_path = _closed_prior(
        root, dex_backfill_enabled=prior_dex_backfill_enabled)
    return epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=identity or _current(root),
        context=context or _context(root),
    )


def _rewrite_signed(path: Path, **changes):
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = {
        key: value for key, value in document.items()
        if key != "document_digest"
    }
    payload.update(changes)
    rewritten = {
        **payload,
        "document_digest": epochlib._digest(payload),  # noqa: SLF001
    }
    path.write_bytes(epochlib._canonical(rewritten) + b"\n")  # noqa: SLF001


def test_valid_authenticated_closed_epoch_permits_handoff(tmp_path):
    verdict = _validate(tmp_path)
    assert verdict.allowed is True
    assert verdict.refusals == []
    # Steady state under the 2026-07-30 contract: prior and current epochs
    # both carry the enabled DEX-backfill binding, so the semantic policy is
    # simply equal and neither sanctioned transition arm is engaged.
    assert verdict.checks["semantic_policy_equal"] is True
    assert verdict.checks["dex_candidate_authority_retired"] is False
    assert verdict.checks["dex_backfill_reinstated"] is False


def test_dex_backfill_reinstatement_is_the_sanctioned_transition(tmp_path):
    """A prior epoch written before the remediation (binding False) hands off
    to the enabled contract through exactly one sanctioned binding flip; any
    additional simultaneous policy change still refuses."""

    verdict = _validate(tmp_path, prior_dex_backfill_enabled=False)
    assert verdict.allowed is True
    assert verdict.refusals == []
    assert verdict.checks["semantic_policy_equal"] is False
    assert verdict.checks["dex_backfill_reinstated"] is True
    assert verdict.checks["dex_candidate_authority_retired"] is False
    record_root = tmp_path / "record"
    _, path = _closed_prior(record_root, dex_backfill_enabled=False)
    audit = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(record_root),
        context=_context(record_root),
    ).existing_record
    assert audit["validation_outcome"] == "ACCEPTED"
    assert audit["semantic_policy_digest_before"] != (
        audit["semantic_policy_digest_after"])


def test_prior_closed_epoch_bytes_are_immutable_when_handoff_is_recorded(
        tmp_path):
    _, epoch_path = _closed_prior(tmp_path)
    before = epoch_path.read_bytes()
    result = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=epoch_path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert result.allowed and result.existing_record
    assert epoch_path.read_bytes() == before


def test_descendant_repository_history_is_accepted(tmp_path):
    assert _validate(tmp_path).allowed


def test_repository_rollback_is_rejected(tmp_path):
    verdict = _validate(
        tmp_path,
        context=_context(
            tmp_path,
            repository_head_is_descendant=False,
            repository_rollback=True),
    )
    assert epochlib.HANDOFF_REPOSITORY_ROLLBACK in verdict.refusals


def test_unrelated_repository_history_is_rejected(tmp_path):
    verdict = _validate(
        tmp_path,
        context=_context(
            tmp_path, repository_head_is_descendant=False),
    )
    assert epochlib.HANDOFF_REPOSITORY_UNRELATED in verdict.refusals


def test_dirty_or_unfinished_git_is_rejected(tmp_path):
    verdict = _validate(
        tmp_path, context=_context(
            tmp_path, git_clean_and_complete=False))
    assert epochlib.HANDOFF_GIT_NOT_CLEAN in verdict.refusals


def test_current_launcher_must_be_canonically_generated(tmp_path):
    verdict = _validate(
        tmp_path, context=_context(
            tmp_path, current_launcher_canonical=False))
    assert epochlib.HANDOFF_CURRENT_LAUNCHER_NONCANONICAL in verdict.refusals


@pytest.mark.parametrize("count", [0, 2])
def test_current_launcher_must_pin_head_exactly_once(tmp_path, count):
    verdict = _validate(
        tmp_path,
        context=_context(
            tmp_path, current_launcher_head_pin_count=count),
    )
    assert epochlib.HANDOFF_CURRENT_LAUNCHER_HEAD_PIN in verdict.refusals


@pytest.mark.parametrize("count", [0, 2])
def test_current_launcher_must_pin_ledger_exactly_once(tmp_path, count):
    verdict = _validate(
        tmp_path,
        context=_context(
            tmp_path, current_launcher_ledger_pin_count=count),
    )
    assert epochlib.HANDOFF_CURRENT_LAUNCHER_LEDGER_PIN in verdict.refusals


def test_current_launcher_contract_refusal_blocks(tmp_path):
    verdict = _validate(
        tmp_path,
        context=_context(tmp_path, current_launcher_contract_refusals=(
            "LIVE_LAUNCHER_STRUCTURAL_SHADOW_MISSING",)),
    )
    assert epochlib.HANDOFF_CURRENT_LAUNCHER_REFUSED in verdict.refusals


def test_legacy_prior_policy_requires_exact_prior_launcher_proof(tmp_path):
    verdict = _validate(
        tmp_path, context=_context(
            tmp_path, prior_launcher_canonical=False))
    assert epochlib.HANDOFF_SEMANTIC_POLICY_INVALID in verdict.refusals


@pytest.mark.parametrize(
    "status",
    [
        epochlib.EPOCH_STARTING,
        epochlib.EPOCH_HEALTHY,
        epochlib.EPOCH_CONTINUITY_BROKEN,
    ],
)
def test_nonclosed_prior_epoch_is_rejected(tmp_path, status):
    _, path = _closed_prior(tmp_path)
    _rewrite_signed(path, epoch_status=status)
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert epochlib.HANDOFF_PRIOR_NOT_CLOSED in verdict.refusals


def test_invalid_prior_digest_is_rejected_without_repair(tmp_path):
    _, path = _closed_prior(tmp_path)
    before = path.read_bytes()
    path.write_bytes(before.replace(b"OPERATOR_SHUTDOWN", b"OPERATOR_SHUTD0WN"))
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert epochlib.HANDOFF_PRIOR_DOCUMENT_INVALID in verdict.refusals
    assert path.read_bytes() != before


def test_malformed_prior_document_is_rejected(tmp_path):
    _, path = _closed_prior(tmp_path)
    path.write_text("{", encoding="utf-8")
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert epochlib.HANDOFF_PRIOR_DOCUMENT_INVALID in verdict.refusals


def test_prior_generation_regression_is_rejected(tmp_path):
    _, path = _closed_prior(tmp_path)
    primary = json.loads(path.read_text(encoding="utf-8"))
    backup = path.with_name(path.name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX)
    _rewrite_signed(backup, generation=int(primary["generation"]) + 1)
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert epochlib.HANDOFF_PRIOR_DOCUMENT_INVALID in verdict.refusals


def test_conflicting_primary_and_backup_are_rejected(tmp_path):
    _, path = _closed_prior(tmp_path)
    primary = json.loads(path.read_text(encoding="utf-8"))
    backup = path.with_name(path.name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX)
    _rewrite_signed(
        backup,
        generation=int(primary["generation"]),
        rollover_count=int(primary["rollover_count"]) + 1,
    )
    verdict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert epochlib.HANDOFF_PRIOR_DOCUMENT_INVALID in verdict.refusals


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("state_directory_binding", "d" * 64),
        ("cursor_state_directory_binding", "e" * 64),
        ("telegram_enabled_binding", False),
        ("delivery_policy_binding", "NO_SEND"),
        ("discord_enabled_binding", True),
        ("structural_policy_binding", "ENFORCE"),
        ("historical_rpc_backfill_enabled_binding", True),
        ("canonical_ledger_path_binding", "f" * 64),
        ("wallet_enabled_binding", True),
        ("signing_enabled_binding", True),
        ("trading_enabled_binding", True),
        ("production_mode_binding", "OTHER_MODE"),
    ],
)
def test_unknown_or_changed_semantic_policy_is_rejected(
        tmp_path, field, value):
    identity = _current(tmp_path)
    identity[field] = value
    verdict = _validate(tmp_path, identity=identity)
    assert epochlib.HANDOFF_SEMANTIC_POLICY_CHANGED in verdict.refusals


def test_unknown_durable_policy_field_is_rejected(tmp_path):
    identity = _current(tmp_path)
    identity["unapproved_policy_axis"] = True
    verdict = _validate(tmp_path, identity=identity)
    assert epochlib.HANDOFF_SEMANTIC_POLICY_INVALID in verdict.refusals


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("watchdog_count", epochlib.HANDOFF_ACTIVE_WATCHDOG),
        ("producer_count", epochlib.HANDOFF_ACTIVE_PRODUCER),
        ("yellowstone_owner_count",
         epochlib.HANDOFF_ACTIVE_YELLOWSTONE_OWNER),
        ("telegram_delivery_owner_count",
         epochlib.HANDOFF_ACTIVE_TELEGRAM_OWNER),
        ("canonical_ledger_writer_count",
         epochlib.HANDOFF_ACTIVE_LEDGER_WRITER),
        ("live_or_ambiguous_lock_count",
         epochlib.HANDOFF_LIVE_OR_AMBIGUOUS_LOCK),
    ],
)
def test_each_active_owner_or_ambiguous_lock_blocks(
        tmp_path, field, reason):
    verdict = _validate(
        tmp_path, context=_context(tmp_path, **{field: 1}))
    assert reason in verdict.refusals


def test_valid_handoff_records_authenticated_digest_chained_audit(tmp_path):
    _, path = _closed_prior(tmp_path)
    result = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    audit = result.existing_record
    assert result.allowed
    assert audit["validation_outcome"] == "ACCEPTED"
    # Steady state: prior and current semantic policy are equal, and the
    # audit records identical before/after digests to prove exactly that.
    assert audit["semantic_policy_digest_before"] == (
        audit["semantic_policy_digest_after"])
    state, records, facts = epochlib.classify_deployment_handoff_log(
        path.with_name(epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME))
    assert state == "VALID"
    assert records == [audit]
    assert facts["last_record_digest"] == audit["record_digest"]


def test_repeated_handoff_recording_is_idempotent(tmp_path):
    _, path = _closed_prior(tmp_path)
    kwargs = dict(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    first = epochlib.record_closed_epoch_deployment_handoff(**kwargs)
    audit_path = path.with_name(
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME)
    before = audit_path.read_bytes()
    second = epochlib.record_closed_epoch_deployment_handoff(**kwargs)
    assert first.allowed and second.allowed
    assert second.existing_record["record_digest"] == (
        first.existing_record["record_digest"])
    assert audit_path.read_bytes() == before


def test_conflicting_handoff_record_is_rejected(tmp_path):
    _, path = _closed_prior(tmp_path)
    first = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert first.allowed
    conflicting_identity = _identity(
        tmp_path, head=NEXT_HEAD, launcher=NEXT_LAUNCHER)
    conflict = epochlib.validate_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=conflicting_identity,
        context=_context(
            tmp_path,
            current_repository_head=NEXT_HEAD,
            current_launcher_sha256=NEXT_LAUNCHER),
    )
    assert epochlib.HANDOFF_AUDIT_CONFLICT in conflict.refusals


def test_corrupt_handoff_audit_digest_fails_closed(tmp_path):
    _, path = _closed_prior(tmp_path)
    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    audit_path = path.with_name(
        epochlib.LIVE_EPOCH_DEPLOYMENT_HANDOFF_BASENAME)
    audit_path.write_bytes(
        audit_path.read_bytes().replace(b'"ACCEPTED"', b'"REJECTED"'))
    assert not epochlib.closed_epoch_deployment_handoff_is_valid(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
    )


def test_handoff_creates_fresh_unarmed_epoch_without_candidate_activation(
        tmp_path):
    state, path = _closed_prior(tmp_path)
    prior_bytes = path.read_bytes()
    result = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert result.allowed
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-current-fresh",
        durable_policy_identity=_current(tmp_path),
        run_instance_identity={"identity_schema":
                               epochlib.LIVE_EPOCH_RUN_IDENTITY_SCHEMA,
                               "runtime_nonce": "current"},
    )
    snapshot = manager.snapshot()
    assert snapshot["live_epoch_id"] == "epoch-current-fresh"
    assert snapshot["epoch_status"] == epochlib.EPOCH_STARTING
    assert snapshot["epoch_start_slot"] is None
    assert snapshot["deployment_handoff_applied"] is True
    assert manager.drain_closed_epochs() == []
    assert path.with_name(
        path.name + epochlib.LIVE_EPOCH_BACKUP_SUFFIX).read_bytes() == prior_bytes


def test_handoff_waits_for_confirmed_h_and_begins_at_h_plus_one(tmp_path):
    state, path = _closed_prior(tmp_path)
    prior_bytes = path.read_bytes()
    recorded = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-current-boundary",
        durable_policy_identity=_current(tmp_path),
    )
    assert manager.snapshot()["epoch_status"] == epochlib.EPOCH_STARTING
    observed_h = 435_600_123
    assert manager.observe_confirmed_slot(observed_h)
    snapshot = manager.snapshot()
    assert snapshot["observed_confirmed_boundary_slot"] == observed_h
    assert snapshot["epoch_start_slot"] == observed_h + 1
    assert snapshot["epoch_status"] == epochlib.EPOCH_HEALTHY
    archive = epochlib.closed_epoch_archive_path(
        path, recorded.existing_record["prior_epoch_file_sha256"])
    assert archive.read_bytes() == prior_bytes


def test_new_epoch_is_durable_and_uses_current_deployment_identity(tmp_path):
    state, path = _closed_prior(tmp_path)
    current = _current(tmp_path)
    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=current,
        context=_context(tmp_path),
    )
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-current-identity",
        durable_policy_identity=current,
    )
    snapshot = manager.snapshot()
    assert snapshot["epoch_durable"] is True
    assert snapshot["durable_policy_identity"] == current
    assert snapshot["durable_policy_identity"]["repo_head_binding"] == NEW_HEAD
    assert snapshot["durable_policy_identity"][
        "launcher_sha256_binding"] == NEW_LAUNCHER


@pytest.mark.parametrize("name", ["candidate_tracker.json", "queue.jsonl"])
def test_prior_trackers_and_queue_items_remain_inactive(tmp_path, name):
    state, path = _closed_prior(tmp_path)
    sentinel = state / name
    sentinel.write_bytes(b'{"active":false,"prior_epoch":true}\n')
    before = sentinel.read_bytes()
    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        durable_policy_identity=_current(tmp_path),
    )
    assert sentinel.read_bytes() == before
    assert manager.drain_closed_epochs() == []


@pytest.mark.parametrize("name", ["global_dedupe.jsonl", "paid_ledger.jsonl"])
def test_global_dedupe_and_paid_history_persist_byte_for_byte(tmp_path, name):
    state, path = _closed_prior(tmp_path)
    sentinel = tmp_path / name
    sentinel.write_bytes(b'{"historical":true}\n')
    before = (
        hashlib.sha256(sentinel.read_bytes()).hexdigest(),
        sentinel.stat().st_size,
    )
    epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    epochlib.LiveEpochManager(
        state_dir=state,
        durable_policy_identity=_current(tmp_path),
    )
    after = (
        hashlib.sha256(sentinel.read_bytes()).hexdigest(),
        sentinel.stat().st_size,
    )
    assert after == before


def test_watchdog_prestart_observation_recognizes_authorized_handoff(tmp_path):
    config = make_config(tmp_path)
    state = Path(config.cursor_state_dir)
    prior = _identity(
        tmp_path,
        head=OLD_HEAD,
        launcher=OLD_LAUNCHER,
        state_dir=state,
        cursor_dir=state,
        ledger_path=Path(config.ledger_path),
        dex_backfill_enabled=True,
    )
    for key in (
        "canonical_ledger_path_binding",
        "wallet_enabled_binding",
        "signing_enabled_binding",
        "trading_enabled_binding",
    ):
        prior.pop(key)
    manager = epochlib.LiveEpochManager(
        state_dir=state,
        now_fn=lambda: NOW,
        id_fn=lambda: "epoch-watchdog-prior",
        durable_policy_identity=prior,
    )
    manager.observe_confirmed_slot(435_500_000)
    manager.close("OPERATOR_SHUTDOWN")
    current = epochlib.build_durable_policy_identity(
        state_dir=state,
        cursor_state_dir=state,
        canonical_ledger_path=config.ledger_path,
        repo_head=config.expected_head,
        launcher_sha256=file_sha256(config.launcher_path),
        delivery_policy="TELEGRAM_ONLY",
        telegram_enabled=True,
        discord_enabled=False,
        structural_policy="SHADOW",
        # The authorized deployment is the one the watchdog will supervise, so
        # the CURRENT identity must carry the policy the watchdog expects.
        alert_policy=expected_alert_policy(config),
        dex_backfill_enabled=True,
    )
    context = _context(
        tmp_path,
        current_repository_head=config.expected_head,
        current_launcher_sha256=file_sha256(config.launcher_path),
        canonical_ledger_path_digest=str(
            current["canonical_ledger_path_binding"]),
    )
    recorded = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=config.live_epoch_primary_path,
        current_policy_identity=current,
        context=context,
        handoff_path=config.live_epoch_deployment_handoff_path,
    )
    assert recorded.allowed
    world = FakeWorld(config)
    observation = build_observation(
        config=config,
        table=world.table(),
        lock=read_producer_lock(config.producer_runtime_lock_path),
        adoption=None,
        run_dir=None,
        producer_pid=None,
        producer_alive=False,
        producer_start_utc=None,
        operator_stop_requested=False,
        circuit_open=False,
        producer_expected=True,
        repo_head_matches=True,
        launcher_identity_matches=True,
        redaction_exposure=False,
        previous=PreviousObservation(),
        now_utc=NOW,
    )
    assert observation.facts["production_policy_state"] == (
        PRODUCTION_POLICY_VALID)
    assert observation.facts["production_policy_source"] == (
        PRODUCTION_POLICY_SOURCE_DURABLE)
    assert observation.facts[
        "closed_epoch_deployment_handoff_authorized"] is True
    assert observation.inputs.epoch_durable is True


def test_safe_handoff_artifact_passes_redaction_scan(tmp_path):
    _, path = _closed_prior(tmp_path)
    result = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    )
    assert result.allowed
    report = redaction_artifacts.run_redaction_scan(tmp_path)
    assert report["redaction_status"] == "REDACTED"
    assert report["total_unsafe_hits"] == 0


def test_handoff_audit_contains_only_safe_digest_identity_fields(tmp_path):
    _, path = _closed_prior(tmp_path)
    record = epochlib.record_closed_epoch_deployment_handoff(
        epoch_path=path,
        current_policy_identity=_current(tmp_path),
        context=_context(tmp_path),
    ).existing_record
    serialized = json.dumps(record, sort_keys=True).lower()
    for forbidden in (
        "telegram_bot_token",
        "chat_id",
        "provider_key",
        "provider_endpoint",
        "discord_webhook",
        "outbound_message",
        "api_response",
    ):
        assert forbidden not in serialized


def test_redaction_positive_control_remains_effective():
    assert not redaction_artifacts.scan_value_safe(
        "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")


def test_transport_recovery_and_backfill_semantics_remain_locked(tmp_path):
    identity = _current(tmp_path)
    assert identity["delivery_policy_binding"] == "TELEGRAM_ONLY"
    assert identity["telegram_enabled_binding"] is True
    assert identity["discord_enabled_binding"] is False
    assert identity["historical_rpc_backfill_enabled_binding"] is False
    # Bounded six-hour DEX candidate recovery is part of the armed contract;
    # historical RPC replay above stays retired and disabled.
    assert identity["dexscreener_restart_backfill_enabled_binding"] is True
    assert identity["structural_policy_binding"] == "SHADOW"
    assert identity["wallet_enabled_binding"] is False
    assert identity["signing_enabled_binding"] is False
    assert identity["trading_enabled_binding"] is False
