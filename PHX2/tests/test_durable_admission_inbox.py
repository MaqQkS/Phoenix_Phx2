"""Pure offline crash/fault tests for source-to-watch durable ownership."""
from dataclasses import asdict
import json
import socket
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import admission_inbox as inbox_mod
from PHX2.free_tier_producer import helius_source, helius_gap_recovery
from PHX2.free_tier_producer import migration_admission
from PHX2.free_tier_producer.admission_inbox import (
    AdmissionInboxError, DurableAdmissionInbox, validate_admission_receipt,
)
from PHX2.free_tier_producer.compat import build30_watchlist as watch_mod
from PHX2.free_tier_producer.compat.production_live_runner import seed_discovered_candidates
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe, SingleGrpcPumpSwapDiscovery, event_to_candidate,
)
from PHX2.free_tier_producer.source_continuity import SourceContinuityTracker
from PHX2.tests.test_proven_migration_mint_admission import MINTS, NOW, _config, _event
from PHX2.tests.test_migration_admission import build_pool_creation_update
from PHX2.tests.test_helius_developer_shadow_probe import _update_to_helius
from PHX2.tests.test_helius_gap_recovery import _HttpSequence, _response, _open_gap


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN")
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def candidate(index=0, *, slot=101):
    update = build_pool_creation_update(base_mint=MINTS[index])
    update.transaction.slot = slot
    update.transaction.transaction.signature = bytes([20 + index]) * 64
    decision = migration_admission.evaluate_migration_admission(update, observed_at_utc=NOW)
    row = event_to_candidate(_event(decision), migration_proof=decision.proof)
    row["live_epoch_id"] = "epoch-original"
    return row, decision, update


class Epoch:
    def snapshot(self):
        return {"live_epoch_id": "epoch-original", "epoch_start_slot": 100}
    def admit_event(self, slot):
        return slot >= 100, "ADMITTED", "epoch-original"


def owner(inbox, *, queue_max=2):
    return SingleGrpcPumpSwapDiscovery(source_factory=lambda: None,
        dedupe=ProviderCandidateDedupe(), live_epoch_manager=Epoch(),
        admission_inbox=inbox, queue_max=queue_max)


def watches(inbox, tmp_path, *, max_size=2):
    watch = watch_mod.Watchlist(max_size=max_size,
        terminal_history_path=tmp_path / "terminal.jsonl")
    watch.bind_admission_inbox(inbox)
    watch.begin_live_only_epoch("new-epoch", first_eligible_slot=1000,
                               opened_at_utc="2026-08-04T00:00:00Z")
    return watch


@pytest.mark.parametrize("crash_stage", ["before_queue", "queued", "drained"])
def test_restart_replays_until_verified_watch_checkpoint(tmp_path, crash_stage):
    path = tmp_path / "pending.json"
    inbox = DurableAdmissionInbox(path, max_pending=2)
    row, _decision, _update = candidate()
    if crash_stage == "before_queue":
        inbox.put(row, first_eligible_slot=100)
    else:
        provider = owner(inbox)
        assert provider._admit_candidate(row)
        if crash_stage == "drained":
            assert len(provider.drain()) == 1
    restored_inbox = DurableAdmissionInbox(path, max_pending=2)
    watch = watches(restored_inbox, tmp_path)
    seed_discovered_candidates(watchlist=watch, candidates=[],
                              seeded_at_utc="2026-08-04T00:00:00Z")
    entry = watch.get(MINTS[0])
    assert entry.is_active() and entry.live_epoch_id == "epoch-original"
    assert entry.discovery_provenance == row["discovery_provenance"]
    assert entry.seeded_at_utc == NOW
    assert watch.close_live_epochs_except("new-epoch", closed_at_utc=NOW) == 0
    assert restored_inbox.snapshot()["pending"] == 1
    checkpoint = tmp_path / "watch.jsonl"
    watch.persist(checkpoint)
    assert DurableAdmissionInbox(path, max_pending=2).pending() == ()
    again = watch_mod.Watchlist.load(checkpoint, max_size=2)
    again.bind_admission_inbox(DurableAdmissionInbox(path, max_pending=2))
    assert again.begin_live_only_epoch("third-epoch", first_eligible_slot=2000,
                                      opened_at_utc=NOW) == 0
    assert again.get(MINTS[0]).is_active()
    assert again.summary()["historical_candidates_eligible"] == 0


def test_checkpoint_before_ack_crash_is_idempotent(tmp_path, monkeypatch):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    row, _d, _u = candidate()
    receipt = inbox.put(row, first_eligible_slot=100)
    watch = watches(inbox, tmp_path)
    assert watch.seed_pending_admission(receipt, seeded_at_utc=NOW)[1] == "ADMITTED"
    def failed_ack(*args):
        raise AdmissionInboxError("FAULT_BEFORE_ACK")
    monkeypatch.setattr(inbox, "acknowledge_checkpoint", failed_ack)
    path = tmp_path / "watch.jsonl"
    with pytest.raises(AdmissionInboxError):
        watch.persist(path)
    fresh = DurableAdmissionInbox(tmp_path / "pending.json")
    restored = watch_mod.Watchlist.load(path, max_size=2)
    restored.bind_admission_inbox(fresh)
    restored.begin_live_only_epoch("new-epoch", first_eligible_slot=2000, opened_at_utc=NOW)
    assert restored.seed_pending_admission(fresh.pending()[0], seeded_at_utc=NOW)[1] == "EXISTING"
    restored.persist(path)
    assert fresh.pending() == () and restored.active_count() == 1


def test_checkpoint_failure_does_not_ack(tmp_path, monkeypatch):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    row, _d, _u = candidate()
    receipt = inbox.put(row, first_eligible_slot=100)
    watch = watches(inbox, tmp_path)
    watch.seed_pending_admission(receipt, seeded_at_utc=NOW)
    def failure(**kwargs):
        raise OSError("FAULT")
    monkeypatch.setattr(watch_mod._cpe, "write_checkpoint_generation_resilient", failure)
    with pytest.raises(OSError):
        watch.persist(tmp_path / "watch.jsonl")
    assert len(DurableAdmissionInbox(tmp_path / "pending.json").pending()) == 1


def test_terminal_history_never_resurrects_pending_receipt(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    row, _d, _u = candidate()
    receipt = inbox.put(row, first_eligible_slot=100)
    watch = watches(inbox, tmp_path)
    entry, _ = watch.seed_pending_admission(receipt, seeded_at_utc=NOW)
    entry.status = watch_mod.WATCH_EXPIRED
    assert watch._terminalize(entry, terminal_at_utc=NOW)
    assert watch.seed_pending_admission(receipt, seeded_at_utc=NOW)[1] == "TERMINAL_HISTORY_DUPLICATE"
    watch.persist(tmp_path / "watch.jsonl")
    assert watch.active_count() == 0 and inbox.pending() == ()


def test_full_watch_retains_pending_and_retries(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    first, _d, _u = candidate()
    second, _d, _u = candidate(1)
    inbox.put(first, first_eligible_slot=100)
    inbox.put(second, first_eligible_slot=100)
    watch = watches(inbox, tmp_path, max_size=1)
    seed_discovered_candidates(watchlist=watch, candidates=[], seeded_at_utc=NOW)
    watch.persist(tmp_path / "watch.jsonl")
    assert len(inbox.pending()) == 1 and watch.active_count() == 1
    entry = watch.get(MINTS[0])
    entry.status = watch_mod.WATCH_EXPIRED
    assert watch._terminalize(entry, terminal_at_utc=NOW)
    seed_discovered_candidates(watchlist=watch, candidates=[], seeded_at_utc=NOW)
    watch.persist(tmp_path / "watch.jsonl")
    assert inbox.pending() == () and watch.get(MINTS[1]).is_active()


def test_inbox_failure_does_not_consume_dedupe(tmp_path, monkeypatch):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    row, _d, _u = candidate()
    provider = owner(inbox)
    real_commit = inbox._commit
    monkeypatch.setattr(inbox, "_commit", lambda *_: (_ for _ in ()).throw(OSError("FAULT")))
    with pytest.raises(OSError):
        provider._admit_candidate(row)
    assert provider._dedupe.snapshot()["mints_tracked"] == 0
    assert not provider._last_handoff_was_durable() and provider._stop.is_set()
    assert provider.snapshot()["admission_inbox_commit_failed"] is True
    monkeypatch.setattr(inbox, "_commit", real_commit)
    assert provider._admit_candidate(row)
    assert len(inbox.pending()) == 1


def test_bounded_inbox_full_does_not_consume_second_identity(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json", max_pending=1)
    provider = owner(inbox)
    assert provider._admit_candidate(candidate()[0])
    with pytest.raises(AdmissionInboxError, match="FULL"):
        provider._admit_candidate(candidate(1)[0])
    assert provider._dedupe.snapshot()["mints_tracked"] == 1
    assert len(inbox.pending()) == 1


def test_memory_queue_overflow_keeps_durable_candidate(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json", max_pending=2)
    provider = owner(inbox, queue_max=1)
    assert provider._admit_candidate(candidate()[0])
    assert provider._admit_candidate(candidate(1)[0])
    assert provider._last_handoff_was_durable()
    assert len(provider.drain()) == 1 and len(inbox.pending()) == 2


def test_legacy_queue_overflow_remains_retryable():
    provider = SingleGrpcPumpSwapDiscovery(source_factory=lambda: None,
        dedupe=ProviderCandidateDedupe(), queue_max=1)
    first = {"token_mint": "firstpump", "provider_event_id": "first"}
    second = {"token_mint": "secondpump", "provider_event_id": "second"}
    assert provider._admit_candidate(first)
    assert not provider._admit_candidate(second)
    assert len(provider.drain()) == 1
    assert provider._admit_candidate(second)


@pytest.mark.parametrize("change", ["proof", "epoch", "slot", "digest"])
def test_invalid_receipts_fail_closed(tmp_path, change):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    receipt = inbox.put(candidate()[0], first_eligible_slot=100)
    if change == "proof":
        receipt["candidate"]["migration_proof"]["canonical_pda_valid"] = False
    elif change == "epoch":
        receipt["candidate"]["live_epoch_id"] = ""
    elif change == "slot":
        receipt["first_eligible_slot"] = 102
    else:
        receipt["receipt_id"] = "wrong"
    assert not validate_admission_receipt(receipt)
    watch = watches(inbox, tmp_path)
    assert watch.seed_pending_admission(receipt, seeded_at_utc=NOW)[0] is None


def test_candidate_label_and_unowned_sealed_receipt_cannot_bypass_epoch(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    row, _d, _u = candidate()
    receipt = inbox.put(row, first_eligible_slot=100)
    empty = DurableAdmissionInbox(tmp_path / "empty.json")
    watch = watches(empty, tmp_path)
    row["admission_receipt"] = receipt
    row["replay"] = True
    assert watch.seed_with_outcome(row, seeded_at_utc=NOW)[1] == "PRE_BOUNDARY_NOT_ELIGIBLE"
    assert watch.seed_pending_admission(receipt, seeded_at_utc=NOW)[0] is None


def test_corrupt_or_oversized_inbox_is_not_silently_reset(tmp_path):
    path = tmp_path / "pending.json"
    path.write_text('{"schema":', encoding="utf-8")
    with pytest.raises(AdmissionInboxError):
        DurableAdmissionInbox(path, max_pending=1)
    path.write_bytes(b" " * (inbox_mod.MAX_RECEIPT_BYTES + 4097))
    with pytest.raises(AdmissionInboxError):
        DurableAdmissionInbox(path, max_pending=1)


def test_public_projection_excludes_credentials_and_raw_envelopes(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    row, _d, _u = candidate()
    row.update(api_key="do-not-persist", raw_transaction={"secret": "do-not-persist"},
               source_ref="https://example.invalid/?api-key=do-not-persist")
    inbox.put(row, first_eligible_slot=100)
    assert "do-not-persist" not in inbox.path.read_text()


def test_helius_source_commits_full_candidate_before_processed_ack(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    provider = owner(inbox)
    continuity = SourceContinuityTracker()
    journal_order = []
    journal = SimpleNamespace(
        append=lambda record: (journal_order.append(bool(inbox.pending())),
                               SimpleNamespace(outcome="COMMITTED"))[1],
        commit_cursor=lambda slot: journal_order.append(bool(inbox.pending())))
    def commit(event, **context):
        assert continuity.snapshot()["last_processed_slot"] is None
        assert provider._commit_source_candidate(event, **context)
        assert len(DurableAdmissionInbox(inbox.path).pending()) == 1
        return True
    source = helius_source.HeliusEnhancedWssSource(config=_config(),
        continuity=continuity, candidate_commit_fn=commit, journal=journal,
        now_fn=lambda: NOW)
    _row, _d, update = candidate()
    raw = json.dumps({"jsonrpc": "2.0", "method": "transactionNotification",
        "params": {"subscription": 77, "result": _update_to_helius(update)}})
    assert source._decode_notification(raw, subscription_id=77) is not None
    assert continuity.snapshot()["last_processed_slot"] == 101
    assert len(provider.drain()) == 1
    assert journal_order == [True, True]


def test_helius_commit_failure_does_not_ack_or_remember(tmp_path):
    continuity = SourceContinuityTracker()
    source = helius_source.HeliusEnhancedWssSource(config=_config(), continuity=continuity,
        candidate_commit_fn=lambda *a, **k: False, now_fn=lambda: NOW)
    _row, _d, update = candidate()
    raw = json.dumps({"jsonrpc": "2.0", "method": "transactionNotification",
        "params": {"subscription": 77, "result": _update_to_helius(update)}})
    with pytest.raises(helius_source.HeliusSourceProtocolError, match="INBOX_COMMIT_FAILED"):
        source._decode_notification(raw, subscription_id=77)
    assert continuity.snapshot()["last_processed_slot"] is None
    assert not source._seen and source._closed.is_set()


@pytest.mark.parametrize("success", [True, False])
def test_http_coverage_waits_for_durable_candidate(tmp_path, success):
    tracker, gap = _open_gap()
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    provider = owner(inbox)
    journal_order = []
    journal = SimpleNamespace(
        append=lambda record: (journal_order.append(bool(inbox.pending())),
                               SimpleNamespace(outcome="COMMITTED"))[1],
        commit_cursor=lambda slot: journal_order.append(bool(inbox.pending())))
    _row, _d, update = candidate()
    http = _HttpSequence(lambda request: _response(request["id"], [_update_to_helius(update)]))
    def commit(event, **context):
        assert tracker.open_gaps()
        return provider._commit_source_candidate(event, **context) if success else False
    recoverer = helius_gap_recovery.HeliusSlotGapRecoverer(source_config=_config(),
        continuity=tracker, http_call=http, candidate_commit_fn=commit,
        journal=journal, now_fn=lambda: NOW)
    result = recoverer.recover(gap_id=gap.gap_id, gap_from_slot=101, gap_to_slot=101)
    assert result.complete_range_proven is success
    assert bool(inbox.pending()) is success
    assert bool(tracker.open_gaps()) is not success
    assert journal_order == ([True, True] if success else [])


def test_primary_factory_threads_commit_callback_without_network(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    tracker = SourceContinuityTracker()
    factory = helius_source.build_helius_primary_source_factory(config=_config(), continuity=tracker)
    provider = SingleGrpcPumpSwapDiscovery(source_factory=factory,
        dedupe=ProviderCandidateDedupe(), live_epoch_manager=Epoch(), admission_inbox=inbox)
    source = provider._build_source(None, 1)
    assert source.candidate_handoff_owned
    assert source._candidate_commit_fn == provider._commit_source_candidate
    assert source._gap_recoverer._candidate_commit_fn == provider._commit_source_candidate


@pytest.mark.parametrize("fault", ["fsync", "replace"])
def test_actual_inbox_write_failure_preserves_prior_generation(tmp_path, monkeypatch, fault):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    first, _d, _u = candidate()
    second, _d, _u = candidate(1)
    inbox.put(first, first_eligible_slot=100)
    original = getattr(inbox_mod.os, fault)
    monkeypatch.setattr(inbox_mod.os, fault,
        lambda *a, **k: (_ for _ in ()).throw(OSError("FAULT")))
    with pytest.raises(AdmissionInboxError):
        inbox.put(second, first_eligible_slot=100)
    assert inbox.snapshot()["pending"] == 1
    assert len(DurableAdmissionInbox(inbox.path).pending()) == 1
    monkeypatch.setattr(inbox_mod.os, fault, original)
    inbox = DurableAdmissionInbox(inbox.path)
    inbox.put(second, first_eligible_slot=100)
    assert len(DurableAdmissionInbox(inbox.path).pending()) == 2


def test_failed_source_does_not_advance_owner_finalization_cursor():
    tracker = SourceContinuityTracker()
    tracker.note_slot(100, processed=True, durable=True)
    source = SimpleNamespace(highest_slot_observed=101,
        admission_commit_failed=True, last_refusal_reason="MIGRATION_PROOF_COMMIT_FAILED",
        first_update_epoch=101.0, last_update_epoch=101.0,
        iter_events=lambda **kwargs: iter(()), close=lambda: None)
    provider = SingleGrpcPumpSwapDiscovery(source_factory=lambda: source,
        dedupe=ProviderCandidateDedupe(), continuity=tracker, now_fn=lambda: 101.0)
    provider._run()
    assert provider._stop.is_set()
    assert provider.snapshot()["admission_inbox_commit_failed"] is True
    assert tracker.snapshot()["last_processed_slot"] == 100


def test_invalid_checkpoint_receipt_cannot_survive_restart(tmp_path):
    inbox = DurableAdmissionInbox(tmp_path / "pending.json")
    receipt = inbox.put(candidate()[0], first_eligible_slot=100)
    watch = watches(inbox, tmp_path)
    entry, _ = watch.seed_pending_admission(receipt, seeded_at_utc=NOW)
    entry.admission_receipt["first_eligible_slot"] = 102
    valid, _reason = watch_mod.validate_watch_checkpoint_record({
        **asdict(entry), "record_digest": "invalid"})
    assert not valid
    assert not watch._entry_has_durable_admission(entry)


def test_uncertain_replace_cannot_be_overwritten_by_old_watch_ack(tmp_path, monkeypatch):
    path = tmp_path / "pending.json"
    inbox = DurableAdmissionInbox(path)
    receipt_a = inbox.put(candidate()[0], first_eligible_slot=100)
    monkeypatch.setattr(inbox, "_read",
        lambda: (_ for _ in ()).throw(OSError("FAULT_AFTER_REPLACE")))
    with pytest.raises(AdmissionInboxError):
        inbox.put(candidate(1)[0], first_eligible_slot=100)
    assert inbox.snapshot()["reload_required"] is True
    with pytest.raises(AdmissionInboxError, match="RELOAD_REQUIRED"):
        inbox.acknowledge_checkpoint([receipt_a])
    with pytest.raises(AdmissionInboxError, match="RELOAD_REQUIRED"):
        inbox.put(candidate()[0], first_eligible_slot=100)
    fresh = DurableAdmissionInbox(path)
    assert len(fresh.pending()) == 2
    fresh.acknowledge_checkpoint([receipt_a])
    assert [r["candidate"]["token_mint"] for r in fresh.pending()] == [MINTS[1]]
