from __future__ import annotations

import json

from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_LIVE,
    WATCH_EXPIRED,
    Watchlist,
)
from PHX2.free_tier_producer.live_epoch import (
    CLEAN_RESTART_EPOCH_ROLLOVER,
    EPOCH_EVENT_ADMITTED,
    EPOCH_EVENT_BEFORE_START_REJECTED,
    EPOCH_EVENT_PRE_ARM_REJECTED,
    EPOCH_HEALTHY,
    EPOCH_INTEGRITY_FAILURE,
    EPOCH_STARTING,
    HISTORICAL_REPLAY_STATUS,
    LIVE_EPOCH_BASENAME,
    LiveEpochManager,
    build_durable_policy_identity,
    build_run_instance_identity,
    classify_live_epoch_document,
    classify_live_epoch_document_set,
    live_epoch_handoff_is_valid,
)
from PHX2.free_tier_producer.paid_provider import ProviderCandidateDedupe
from PHX2.free_tier_producer.ping_quality_review import (
    build_ping_quality_record,
    ping_quality_record_is_redaction_safe,
)
from PHX2.watchdog.health import (
    HEALTHY,
    NONRESTARTABLE_INTEGRITY_FAILURE,
    RESTARTABLE_PROCESS_FAILURE,
    STARTING,
    HealthInputs,
    evaluate_health,
)


def _clock(values):
    iterator = iter(values)
    last = values[-1]

    def now():
        nonlocal last
        try:
            last = next(iterator)
        except StopIteration:
            pass
        return last

    return now


def test_startup_arms_h_plus_one_and_rejects_prearm(tmp_path):
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=_clock([
            "2026-07-26T23:00:00Z",
            "2026-07-26T23:00:01Z",
            "2026-07-26T23:00:02Z",
            "2026-07-26T23:00:03Z",
        ]),
        id_fn=lambda: "epoch-a",
    )
    assert manager.snapshot()["epoch_status"] == EPOCH_STARTING
    assert manager.admit_event(100)[:2] == (
        False, EPOCH_EVENT_PRE_ARM_REJECTED)
    assert manager.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:03Z") is True
    snapshot = manager.snapshot()
    assert snapshot["epoch_status"] == EPOCH_HEALTHY
    assert snapshot["observed_confirmed_boundary_slot"] == 100
    assert snapshot["epoch_start_slot"] == 101
    assert snapshot["historical_rpc_backfill_enabled"] is False
    assert snapshot["historical_completeness_required"] is False
    assert snapshot["historical_recovery_status"] == HISTORICAL_REPLAY_STATUS
    assert manager.admit_event(100)[:2] == (
        False, EPOCH_EVENT_BEFORE_START_REJECTED)
    assert manager.admit_event(101)[:2] == (True, EPOCH_EVENT_ADMITTED)


def test_rollover_closes_old_epoch_and_starts_fresh_unarmed_epoch(tmp_path):
    ids = iter(["epoch-a", "epoch-b"])
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: next(ids),
    )
    manager.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    assert manager.rollover("STREAM_CONTINUITY_BREAK") == "epoch-a"
    snapshot = manager.snapshot()
    assert snapshot["live_epoch_id"] == "epoch-b"
    assert snapshot["epoch_status"] == EPOCH_STARTING
    assert snapshot["epoch_start_slot"] is None
    assert snapshot["rollover_count"] == 1
    closed = manager.drain_closed_epochs()
    assert len(closed) == 1
    assert closed[0]["live_epoch_id"] == "epoch-a"
    assert manager.admit_event(200)[0] is False
    assert manager.observe_confirmed_slot(
        200, observed_at_utc="2026-07-26T23:00:00Z")
    assert manager.snapshot()["epoch_start_slot"] == 201


def test_restart_queues_prior_epoch_for_candidate_closure(tmp_path):
    first = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: "epoch-a",
    )
    first.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    second = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:01:00Z",
        id_fn=lambda: "epoch-b",
    )
    assert second.drain_closed_epochs()[0]["live_epoch_id"] == "epoch-a"
    assert second.snapshot()["live_epoch_id"] == "epoch-b"


def test_same_run_restore_preserves_the_active_epoch(tmp_path):
    durable = build_durable_policy_identity(
        state_dir=tmp_path, repo_head="a" * 40,
        launcher_sha256="b" * 64)
    run = build_run_instance_identity(
        producer_pid=101,
        process_start_utc="2026-07-26T23:00:00Z",
        run_dir=tmp_path / "run-a",
        startup_manifest_digest="c" * 64,
        watchdog_pid=202,
        launcher_wrapper_pid=303,
        runtime_nonce="same-run",
    )
    first = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: "epoch-a",
        durable_policy_identity=durable,
        run_instance_identity=run,
    )
    first.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    second = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:01Z",
        id_fn=lambda: "must-not-be-used",
        durable_policy_identity=durable,
        run_instance_identity=run,
    )
    assert second.integrity_failure is False
    assert second.snapshot()["live_epoch_id"] == "epoch-a"
    assert second.snapshot()["epoch_status"] == EPOCH_HEALTHY
    assert second.drain_closed_epochs() == []


def test_clean_reboot_changes_run_identity_and_rolls_h_plus_one(tmp_path):
    durable = build_durable_policy_identity(
        state_dir=tmp_path, repo_head="a" * 40,
        launcher_sha256="b" * 64)
    old_run = build_run_instance_identity(
        producer_pid=101,
        process_start_utc="2026-07-26T23:00:00Z",
        run_dir=tmp_path / "run-a",
        startup_manifest_digest="c" * 64,
        watchdog_pid=202,
        launcher_wrapper_pid=303,
        runtime_nonce="old-run",
    )
    new_run = build_run_instance_identity(
        producer_pid=404,
        process_start_utc="2026-07-27T00:00:00Z",
        run_dir=tmp_path / "run-b",
        startup_manifest_digest="d" * 64,
        watchdog_pid=505,
        launcher_wrapper_pid=606,
        runtime_nonce="new-run",
    )
    ids = iter(["epoch-old", "epoch-new"])
    first = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: next(ids),
        durable_policy_identity=durable,
        run_instance_identity=old_run,
    )
    first.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    second = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-27T00:00:00Z",
        id_fn=lambda: next(ids),
        durable_policy_identity=durable,
        run_instance_identity=new_run,
    )
    starting = second.snapshot()
    assert starting["live_epoch_id"] == "epoch-new"
    assert starting["epoch_status"] == EPOCH_STARTING
    assert starting["epoch_start_slot"] is None
    assert starting["epoch_history"][-1]["live_epoch_id"] == "epoch-old"
    assert starting["epoch_history"][-1]["reason"] == (
        CLEAN_RESTART_EPOCH_ROLLOVER)
    assert second.observe_confirmed_slot(
        200, observed_at_utc="2026-07-27T00:00:01Z")
    assert second.snapshot()["epoch_start_slot"] == 201


def test_durable_policy_change_is_corruption_not_restart(tmp_path):
    old_policy = build_durable_policy_identity(
        state_dir=tmp_path, repo_head="a" * 40,
        launcher_sha256="b" * 64)
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: "epoch-a",
        durable_policy_identity=old_policy,
    )
    manager.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    changed = dict(old_policy)
    changed["repo_head_binding"] = "f" * 40
    restored = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:01:00Z",
        id_fn=lambda: "unused",
        durable_policy_identity=changed,
    )
    assert restored.integrity_failure is True
    assert restored.snapshot()["epoch_status"] == EPOCH_INTEGRITY_FAILURE
    assert restored.snapshot()["epoch_document_state"] == (
        "POLICY_IDENTITY_MISMATCH")


def test_valid_backup_is_selected_but_newer_backup_fails_closed(tmp_path):
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: "epoch-a",
    )
    manager.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    primary = tmp_path / LIVE_EPOCH_BASENAME
    backup = primary.with_name(primary.name + ".bak")
    primary.write_text('{"forged":true}', encoding="utf-8")
    state, payload, facts = classify_live_epoch_document_set(primary)
    assert state == "VALID_BACKUP"
    assert payload["live_epoch_id"] == "epoch-a"
    assert facts["recovered_from_backup"] is True

    # Restore the valid newer primary, then place it behind an older primary.
    newer = backup.read_bytes()
    primary.write_bytes(newer)
    old_document = json.loads(newer)
    old_payload = {
        key: value for key, value in old_document.items()
        if key != "document_digest"
    }
    old_payload["generation"] = 99
    import hashlib
    body = json.dumps(
        old_payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")
    forged_newer = {
        **old_payload,
        "document_digest": hashlib.sha256(body).hexdigest(),
    }
    backup.write_text(
        json.dumps(forged_newer, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    state, _, facts = classify_live_epoch_document_set(primary)
    assert state == "INVALID"
    assert facts["generation_conflict"] is True


def test_authenticated_epoch_handoff_accepts_only_latest_closure(tmp_path):
    ids = iter(["epoch-old", "epoch-new"])
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: next(ids),
    )
    manager.observe_confirmed_slot(
        100, observed_at_utc="2026-07-26T23:00:00Z")
    old_snapshot = manager.snapshot()
    manager.rollover("PROVIDER_ERROR")
    manager.observe_confirmed_slot(
        200, observed_at_utc="2026-07-26T23:00:01Z")
    new_snapshot = manager.snapshot()
    assert live_epoch_handoff_is_valid(old_snapshot, new_snapshot) is True
    forged = dict(old_snapshot)
    forged["live_epoch_id"] = "epoch-unrelated"
    assert live_epoch_handoff_is_valid(forged, new_snapshot) is False


def test_corrupt_epoch_fails_closed_without_rewriting_evidence(tmp_path):
    path = tmp_path / LIVE_EPOCH_BASENAME
    original = b'{"schema_version":"forged"}\n'
    path.write_bytes(original)
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-26T23:00:00Z",
        id_fn=lambda: "unused",
    )
    assert manager.integrity_failure is True
    assert manager.snapshot()["epoch_status"] == EPOCH_INTEGRITY_FAILURE
    assert manager.admit_event(1)[0] is False
    assert path.read_bytes() == original


def test_gap_crossing_live_candidate_is_terminalized(tmp_path):
    watch = Watchlist(
        max_size=4, terminal_history_path=tmp_path / "terminal.jsonl")
    live = {
        "token_mint": "11111111111111111111111111111111pump",
        "candidate_id": "live-1",
        "migration_time_utc": "2026-07-26T23:00:00Z",
        "source_ref": "live",
        "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
        "live_epoch_id": "epoch-a",
    }
    entry, _ = watch.seed_with_outcome(
        live, seeded_at_utc="2026-07-26T23:00:00Z")
    assert watch.close_live_epoch(
        "epoch-a", closed_at_utc="2026-07-26T23:01:00Z") == 1
    assert entry.status == WATCH_EXPIRED
    assert watch.get(live["token_mint"]) is None
    assert watch.summary()["epoch_gap_candidates_closed"] == 1



def test_restart_closes_all_restored_noncurrent_live_candidates(tmp_path):
    watch = Watchlist(
        max_size=5, terminal_history_path=tmp_path / "terminal.jsonl")

    def live(mint: str, epoch_id):
        return {
            "token_mint": mint,
            "candidate_id": "candidate-" + mint[:4],
            "migration_time_utc": "2026-07-26T23:00:00Z",
            "source_ref": "live",
            "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
            "live_epoch_id": epoch_id,
        }

    stale = "11111111111111111111111111111111pump"
    current = "22222222222222222222222222222222pump"
    legacy = "33333333333333333333333333333333pump"
    for candidate in (live(stale, "epoch-old"),
                      live(current, "epoch-current"),
                      live(legacy, None)):
        assert watch.seed_with_outcome(
            candidate, seeded_at_utc="2026-07-26T23:00:00Z")[1] == "ADMITTED"

    assert watch.close_live_epochs_except(
        "epoch-current", closed_at_utc="2026-07-26T23:01:00Z") == 2
    assert watch.get(stale) is None
    assert watch.get(legacy) is None
    assert watch.get(current) is not None
    assert watch.summary()["epoch_gap_candidates_closed"] == 2

def test_shared_mint_dedupe_is_global_across_sources():
    dedupe = ProviderCandidateDedupe(max_entries=8)
    assert dedupe.accept(event_id="dex-1", mint="mint-a") is True
    accepted, reason = dedupe.accept_with_reason(
        event_id="live-1", mint="mint-a")
    assert accepted is False
    assert reason == "DUPLICATE_MINT"


def _healthy_inputs(**changes):
    values = dict(
        producer_expected=True,
        producer_pid=123,
        producer_alive=True,
        producer_identity_ok=True,
        producer_identity_observed=True,
        logical_producer_count=1,
        heartbeat_present=True,
        heartbeat_parse_ok=True,
        heartbeat_age_seconds=1,
        yellowstone_owner_count=1,
        max_active_streams_observed=1,
        cursor_document_state="VALID_CURRENT",
        cursor_quarantined=False,
        cursor_identity_match=True,
        recovery_document_state="RETIRED_AUDIT_ONLY",
        recovery_state=HISTORICAL_REPLAY_STATUS,
        recovery_terminal=False,
        live_epoch_required=True,
        epoch_document_state="VALID_CURRENT",
        epoch_status=EPOCH_HEALTHY,
        epoch_durable=True,
        epoch_age_seconds=10,
        telegram_enabled=True,
        discord_enabled=False,
        send_capable_transport_count=1,
        ledger_parse_ok=True,
        ledger_path_matches=True,
    )
    values.update(changes)
    return HealthInputs(**values)


def test_watchdog_accepts_retired_historical_recovery():
    verdict = evaluate_health(_healthy_inputs())
    assert verdict.health_class == HEALTHY
    assert "RECOVERY_TERMINAL" not in verdict.reasons


def test_watchdog_epoch_starting_grace_and_failure_classes():
    starting = evaluate_health(_healthy_inputs(
        epoch_status=EPOCH_STARTING, epoch_age_seconds=10))
    assert starting.health_class == STARTING
    stalled = evaluate_health(_healthy_inputs(
        epoch_status=EPOCH_STARTING, epoch_age_seconds=301))
    assert stalled.health_class == RESTARTABLE_PROCESS_FAILURE
    corrupt = evaluate_health(_healthy_inputs(
        epoch_status=EPOCH_INTEGRITY_FAILURE, epoch_durable=False))
    assert corrupt.health_class == NONRESTARTABLE_INTEGRITY_FAILURE


def test_ping_quality_review_is_redaction_safe_and_has_required_nulls():
    record = build_ping_quality_record(
        candidate={
            "candidate_id": "candidate-1",
            "token_mint": "mint-a",
            "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
            "live_epoch_id": "epoch-a",
        },
        recheck={
            "reason": "NO_SEND_PENDING",
            "market_context": {"current_market_cap_usd": "100"},
            "activation": {"migration_market_cap_usd": "50"},
        },
        security={
            "original_phx1_structural_verdict": "ORIGINAL_STRUCTURAL_HARD_BLOCK",
            "effective_phx1_policy_verdict": "ALLOW_WITH_SHADOW_WARNING",
            "shadow_warning_reason_tokens": ["PHX1_FEE_GATE_NO_DATA"],
            "non_shadowable_safety_reason_tokens": [],
        },
        observed_at_utc="2026-07-26T23:00:00Z",
    )
    assert ping_quality_record_is_redaction_safe(record)
    assert record["shadow_reasons"] == ["PHX1_FEE_GATE_NO_DATA"]
    assert record["safety_reasons"] == []
    assert record["operator_label"] is None
    assert record["operator_notes"] is None
    assert record["later_outcome"] is None
    assert "outbound_body" not in record
    assert "signature" not in record
