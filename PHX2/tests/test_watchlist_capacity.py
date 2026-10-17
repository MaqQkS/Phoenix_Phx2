"""PHX2-E2E-002 active-watch capacity and terminal-history proofs.

Reproduces the 2026-07-18 end-to-end audit defect (128 EXPIRED historical
entries permanently exhausted the configured capacity and silently rejected
candidate 129 with zero tracked work) and proves the corrected semantics:

- the configured capacity bounds *concurrently active* candidates only;
- terminal candidates are archived durably (append-only, digest-sealed,
  idempotent transition keys) and release their slot;
- a full watchlist rejects a new mint with the explicit observable reason
  ``ACTIVE_WATCH_CAPACITY_REACHED`` — never a silent drop;
- ``DELIVERY_UNKNOWN`` keeps its fa6022d unresolved-state semantics;
- restart restores active entries only and migrates legacy mixed checkpoints
  idempotently, without recreating capacity pressure.

Every test uses deterministic offline fixtures, fake transports, and temporary
files only; the real production ping ledgers are never opened for writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_selftest as fst
from PHX2.free_tier_producer.compat.build30_watchlist import (
    ACTIVE_WATCH_STATES,
    CAPACITY_REJECTION_REASON,
    SCHEDULABLE_WATCH_STATES,
    SEED_OUTCOME_ADMITTED,
    SEED_OUTCOME_CAPACITY,
    SEED_OUTCOME_DROPPED_NON_PUMP,
    SEED_OUTCOME_EXISTING,
    SEED_OUTCOME_TERMINAL_DUPLICATE,
    TERMINAL_WATCH_STATES,
    WATCH_ACTIVE_DIP,
    WATCH_DEDUPE_SUPPRESSED,
    WATCH_DELIVERY_UNKNOWN,
    WATCH_DROPPED_NON_PUMP,
    WATCH_EXPIRED,
    WATCH_PENDING_1_20X,
    WATCH_PENDING_BASELINE,
    WATCH_SEND_ATTEMPTED,
    WATCH_SENT_OK_COMMITTED,
    Watchlist,
    is_active_watch_state,
    is_schedulable_watch_state,
    is_terminal_watch_state,
)
from PHX2.free_tier_producer.compat.production_live_runner import (
    ProductionBounds,
    run_production_live_watch,
    seed_discovered_candidates,
)
from PHX2.free_tier_producer.compat import (
    production_live_axiom_gate as axiomgate,
)
from PHX2.free_tier_producer.compat.watch_terminal_history import (
    TERMINAL_HISTORY_SCHEMA_VERSION,
    TerminalHistoryArchive,
    TerminalHistoryCorruptionError,
    build_terminal_history_key,
    validate_terminal_history_record,
)
from PHX2.runtime import production_supervisor as ps
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import make_constant_clock

NOW = "2026-07-18T00:00:00Z"
LATER = "2026-07-18T01:00:00Z"
RESTART_AT = "2026-07-18T02:00:00Z"


def _mint(index: int) -> str:
    return f"CapFixture{index:04d}pump"


def _cand(index: int) -> dict:
    return {"token_mint": _mint(index), "candidate_id": f"cap{index}"}


def _watch(tmp_path: Path, capacity: int, name: str = "terminal_history.jsonl") -> Watchlist:
    return Watchlist(max_size=capacity, terminal_history_path=tmp_path / name)


def _seed_admitted(watch: Watchlist, count: int, *, start: int = 0) -> None:
    for index in range(start, start + count):
        entry, outcome = watch.seed_with_outcome(_cand(index), seeded_at_utc=NOW)
        assert entry is not None and outcome == SEED_OUTCOME_ADMITTED, (index, outcome)


def _expire_all(watch: Watchlist) -> list:
    return watch.expire_stale_entries(
        now_age_seconds_fn=lambda _seeded: 999999.0,
        max_age_seconds=1,
        max_rechecks=999999,
        now_utc=LATER,
    )


def _sent_ok(watch: Watchlist, mint: str) -> None:
    watch.record_recheck(
        mint=mint, reason="SENT_OK_COMMITTED", observed_at_utc=LATER,
        delivery_state="SENT_OK_COMMITTED",
        delivery_ledger_key="offline-fixture-ledger-key",
        delivery_receipt_digest="d" * 64,
    )


def _history_lines(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


class FlakyArchive(TerminalHistoryArchive):
    """Injects transient durable-append failures for retry-path proofs."""

    def __init__(self, path, *, fail_appends: int = 0):
        super().__init__(path)
        self.fail_appends = fail_appends
        self.failed = 0

    def archive(self, record):
        if self.fail_appends > 0 and not self.has_key(
                record.get("terminal_history_key")):
            self.fail_appends -= 1
            self.failed += 1
            return False, "ARCHIVE_WRITE_FAILED:InjectedOSError"
        return super().archive(record)


# ---------------------------------------------------------------------------
# Centralized classification contract
# ---------------------------------------------------------------------------


class TestStateClassification:
    def test_every_known_state_classifies_exactly_once(self):
        for status in SCHEDULABLE_WATCH_STATES:
            assert is_schedulable_watch_state(status)
            assert is_active_watch_state(status)
            assert not is_terminal_watch_state(status)
        for status in ACTIVE_WATCH_STATES:
            assert is_active_watch_state(status)
            assert not is_terminal_watch_state(status)
        for status in TERMINAL_WATCH_STATES:
            assert is_terminal_watch_state(status)
            assert not is_active_watch_state(status)
            assert not is_schedulable_watch_state(status)

    def test_delivery_unknown_is_active_but_not_schedulable(self):
        assert is_active_watch_state(WATCH_DELIVERY_UNKNOWN)
        assert not is_schedulable_watch_state(WATCH_DELIVERY_UNKNOWN)
        assert not is_terminal_watch_state(WATCH_DELIVERY_UNKNOWN)

    def test_sent_ok_committed_and_expired_are_terminal(self):
        assert is_terminal_watch_state(WATCH_SENT_OK_COMMITTED)
        assert is_terminal_watch_state(WATCH_EXPIRED)
        assert is_terminal_watch_state(WATCH_DROPPED_NON_PUMP)
        assert is_terminal_watch_state(WATCH_DEDUPE_SUPPRESSED)
        assert is_terminal_watch_state(WATCH_SEND_ATTEMPTED)

    def test_ambiguous_status_fails_closed_as_neither(self):
        assert not is_active_watch_state("SOME_FUTURE_STATE")
        assert not is_terminal_watch_state("SOME_FUTURE_STATE")


# ---------------------------------------------------------------------------
# Capacity semantics (required tests 1-7, 13, 27)
# ---------------------------------------------------------------------------


class TestActiveCapacity:
    def test_capacity_counts_only_active_candidates(self, tmp_path):
        watch = _watch(tmp_path, 2)
        _seed_admitted(watch, 2)
        _sent_ok(watch, _mint(0))
        assert watch.active_count() == 1
        entry, outcome = watch.seed_with_outcome(_cand(2), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None
        assert watch.active_count() == 2
        assert watch.terminal_history_count() == 1

    def test_128_active_candidates_fill_capacity_128(self, tmp_path):
        watch = _watch(tmp_path, 128)
        _seed_admitted(watch, 128)
        assert watch.active_count() == 128
        assert watch.summary()["active_capacity_remaining"] == 0

    def test_candidate_129_rejected_while_all_128_active(self, tmp_path):
        watch = _watch(tmp_path, 128)
        _seed_admitted(watch, 128)
        entry, outcome = watch.seed_with_outcome(_cand(128), seeded_at_utc=LATER)
        assert entry is None
        assert outcome == SEED_OUTCOME_CAPACITY

    def test_rejection_reason_is_active_watch_capacity_reached(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        entry, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert entry is None
        assert outcome == "ACTIVE_WATCH_CAPACITY_REACHED"
        records = watch.capacity_rejection_records()
        assert len(records) == 1
        rejection = records[0]
        assert rejection["reason"] == CAPACITY_REJECTION_REASON
        assert rejection["token_mint"] == _mint(1)
        assert rejection["active_count"] == 1
        assert rejection["active_capacity"] == 1
        assert rejection["observed_at_utc"] == LATER

    def test_expiring_one_active_candidate_releases_one_slot(self, tmp_path):
        watch = _watch(tmp_path, 128)
        _seed_admitted(watch, 128)
        watch.record_recheck(
            mint=_mint(0), reason="RECHECKED", observed_at_utc=NOW)
        expired = watch.expire_stale_entries(
            now_age_seconds_fn=lambda _seeded: 0.0,
            max_age_seconds=999999,
            max_rechecks=1,
            now_utc=LATER,
        )
        assert [e.token_mint for e in expired] == [_mint(0)]
        assert watch.active_count() == 127
        assert watch.summary()["active_capacity_remaining"] == 1

    def test_candidate_129_admitted_after_one_slot_released(self, tmp_path):
        watch = _watch(tmp_path, 128)
        _seed_admitted(watch, 128)
        blocked, blocked_outcome = watch.seed_with_outcome(
            _cand(128), seeded_at_utc=LATER)
        assert blocked is None and blocked_outcome == SEED_OUTCOME_CAPACITY
        _sent_ok(watch, _mint(5))
        entry, outcome = watch.seed_with_outcome(_cand(128), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None
        assert watch.active_count() == 128

    def test_hostile_fixture_expiring_all_128_admits_candidate_129(self, tmp_path):
        """The exact audit reproduction, corrected end to end."""
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=128, terminal_history_path=history)
        _seed_admitted(watch, 128)
        expired = _expire_all(watch)
        assert len(expired) == 128
        summary = watch.summary()
        assert summary["active"] == 0
        assert summary["tracked"] == 0
        assert summary["terminal_history"] == 128
        assert summary["active_capacity_remaining"] == 128
        assert summary["by_status"]["EXPIRED"] == 128
        entry, outcome = watch.seed_with_outcome(_cand(128), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None
        assert entry.is_active()
        after = watch.summary()
        assert after["active"] == 1
        assert after["terminal_history"] == 128
        assert after["total"] == 129
        # terminal history remains queryable; no expired candidate re-enters
        assert len(_history_lines(history)) == 128
        assert watch.get(_mint(0)) is None
        assert all(e.token_mint == _mint(128) for e in watch.tracked_entries())
        # restart reproduces the same active and terminal counts
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        restored = Watchlist.load(
            state, max_size=128, terminal_history_path=history)
        rs = restored.summary()
        assert rs["active"] == 1
        assert rs["terminal_history"] == 128
        assert rs["total"] == 129

    def test_duplicate_seed_for_active_mint_does_not_consume_slot(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        entry, outcome = watch.seed_with_outcome(_cand(0), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_EXISTING
        assert entry is watch.get(_mint(0))
        assert watch.active_count() == 1
        assert watch.summary()["capacity_rejections"] == 0

    def test_capacity_rejection_counter_increments_once_per_rejected_mint(
            self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert watch.summary()["capacity_rejections"] == 1
        # duplicate seed of the existing ACTIVE mint never counts as rejection
        watch.seed_with_outcome(_cand(0), seeded_at_utc=LATER)
        assert watch.summary()["capacity_rejections"] == 1


# ---------------------------------------------------------------------------
# Delivery states and slot lifetimes (required tests 8-12, 14, 29)
# ---------------------------------------------------------------------------


class TestDeliveryStateSlots:
    def test_sent_ok_committed_releases_active_slot(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        _sent_ok(watch, _mint(0))
        assert watch.active_count() == 0
        assert watch.terminal_history_count() == 1
        entry, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None

    def test_permanently_dropped_candidate_releases_active_slot(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        watch.record_recheck(
            mint=_mint(0), reason="NOT_PUMP_SUFFIX", observed_at_utc=LATER)
        assert watch.active_count() == 0
        assert watch.terminal_history_count() == 1
        entry, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None

    def test_dedupe_suppressed_releases_active_slot(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        watch.mark_dedupe_suppressed(_mint(0), now_utc=LATER)
        assert watch.active_count() == 0
        assert watch.terminal_history_count() == 1

    def test_delivery_failed_retryable_does_not_release_slot(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        watch.record_recheck(
            mint=_mint(0), reason="DELIVERY_FAILED_RETRYABLE",
            observed_at_utc=LATER,
            delivery_state="DELIVERY_FAILED_RETRYABLE",
            delivery_failure_reason="FAKE_TRANSIENT_FAILURE",
            delivery_next_retry_at_utc=RESTART_AT,
        )
        entry = watch.get(_mint(0))
        assert entry is not None and entry.is_active()
        assert entry.delivery_state == "DELIVERY_FAILED_RETRYABLE"
        assert entry.delivery_retry_count == 1
        assert watch.active_count() == 1
        assert watch.terminal_history_count() == 0
        blocked, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert blocked is None and outcome == SEED_OUTCOME_CAPACITY

    def test_active_delivery_attempt_lease_does_not_release_slot(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        watch.record_recheck(
            mint=_mint(0), reason="DELIVERY_ATTEMPT_IN_PROGRESS",
            observed_at_utc=LATER,
            delivery_state="ATTEMPT_RESERVED",
            delivery_attempt_id="attempt-0001",
        )
        entry = watch.get(_mint(0))
        assert entry is not None and entry.is_active()
        assert entry.delivery_attempt_id == "attempt-0001"
        assert watch.active_count() == 1
        blocked, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert blocked is None and outcome == SEED_OUTCOME_CAPACITY

    def test_delivery_unknown_keeps_fa6022d_semantics_and_holds_slot(
            self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=1, terminal_history_path=history)
        _seed_admitted(watch, 1)
        watch.record_recheck(
            mint=_mint(0), reason="DELIVERY_UNKNOWN", observed_at_utc=LATER,
            delivery_state="DELIVERY_UNKNOWN",
            delivery_failure_reason="TIMEOUT",
        )
        entry = watch.get(_mint(0))
        assert entry is not None
        assert entry.status == WATCH_DELIVERY_UNKNOWN
        # unresolved: NOT schedulable, NOT terminal, NOT silently retryable
        assert not entry.is_active()
        assert not is_terminal_watch_state(entry.status)
        assert watch.tracked_entries() == []
        # it is not archived away and it holds its active slot
        assert watch.terminal_history_count() == 0
        assert watch.active_count() == 1
        blocked, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert blocked is None and outcome == SEED_OUTCOME_CAPACITY
        # restart preserves the observable unresolved state exactly
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        restored = Watchlist.load(
            state, max_size=1, terminal_history_path=history)
        restored_entry = restored.get(_mint(0))
        assert restored_entry is not None
        assert restored_entry.status == WATCH_DELIVERY_UNKNOWN
        assert restored.active_count() == 1
        assert restored.terminal_history_count() == 0

    def test_duplicate_seed_for_terminal_mint_does_not_resurrect(self, tmp_path):
        watch = _watch(tmp_path, 4)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        entry, outcome = watch.seed_with_outcome(_cand(0), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_TERMINAL_DUPLICATE
        assert entry is None
        assert watch.get(_mint(0)) is None
        assert watch.active_count() == 0
        assert watch.terminal_history_count() == 1

    def test_failed_delivery_keeps_zero_ledger_rows_and_zero_history_rows(
            self, tmp_path):
        """fa6022d regression shape: an explicit transient failure neither
        burns a successful-send ledger row nor terminalizes the watch."""
        history = tmp_path / "terminal_history.jsonl"
        ledger = tmp_path / "dedupe.jsonl"
        watch = Watchlist(max_size=4, terminal_history_path=history)
        _seed_admitted(watch, 1)
        watch.record_recheck(
            mint=_mint(0), reason="DELIVERY_FAILED_RETRYABLE",
            observed_at_utc=LATER,
            delivery_state="DELIVERY_FAILED_RETRYABLE")
        assert not ledger.exists()
        assert not history.exists()
        entry = watch.get(_mint(0))
        assert entry is not None and entry.is_active()


# ---------------------------------------------------------------------------
# Terminal history artifact (required tests 15, 20, 21, 22, 26, 28)
# ---------------------------------------------------------------------------


class TestTerminalHistoryArtifact:
    def test_terminal_history_count_reports_archived_records(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 3)
        _expire_all(watch)
        assert watch.terminal_history_count() == 3
        assert watch.summary()["terminal_history"] == 3
        lines = _history_lines(history)
        assert len(lines) == 3
        for record in lines:
            ok, reason = validate_terminal_history_record(record)
            assert ok, reason
            assert record["schema_version"] == TERMINAL_HISTORY_SCHEMA_VERSION
            assert record["terminal_status"] == WATCH_EXPIRED
            assert record["terminal_at_utc"] == LATER
            assert record["seeded_at_utc"] == NOW

    def test_terminal_record_preserves_audit_evidence(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        watch.set_terminal_context_fn(lambda entry: {
            "latest_ath_market_cap_usd": "41493.0192585132",
            "latest_ath_observed_at_utc": "2026-07-18T00:11:00Z",
            "latest_tier": "Tier 2",
            "fee_gate_lifecycle_state": "FRESH_CONFIRMED",
            "risk_label": "RISK_MEDIUM",
        })
        _seed_admitted(watch, 1)
        _sent_ok(watch, _mint(0))
        (record,) = _history_lines(history)
        assert record["token_mint"] == _mint(0)
        assert record["candidate_id"] == "cap0"
        assert record["terminal_status"] == WATCH_SENT_OK_COMMITTED
        assert record["latest_ath_market_cap_usd"] == "41493.0192585132"
        assert record["latest_tier"] == "Tier 2"
        assert record["fee_gate_lifecycle_state"] == "FRESH_CONFIRMED"
        assert record["risk_label"] == "RISK_MEDIUM"
        assert record["delivery_state"] == "SENT_OK_COMMITTED"
        assert record["delivery_ledger_key"] == "offline-fixture-ledger-key"
        assert record["delivery_receipt_digest"] == "d" * 64
        assert record["terminal_history_key"] == build_terminal_history_key(
            candidate_id="cap0", token_mint=_mint(0),
            terminal_status=WATCH_SENT_OK_COMMITTED)

    def test_duplicate_terminal_transition_creates_exactly_one_record(
            self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        assert len(_history_lines(history)) == 1
        # replay the same terminal transition from a stale checkpoint copy
        stale = tmp_path / "stale_watch_state.jsonl"
        entry_row = {
            "token_mint": _mint(0), "candidate_id": "cap0",
            "migration_time_utc": None, "source_ref": None,
            "seeded_at_utc": NOW, "status": "EXPIRED",
            "last_reason": "NEVER_REACHED_ACTIVATION_THRESHOLD",
        }
        stale.write_text(json.dumps(entry_row) + "\n", encoding="utf-8")
        reloaded = Watchlist.load(
            stale, max_size=8, terminal_history_path=history)
        assert reloaded.terminal_history_count() == 1
        assert len(_history_lines(history)) == 1

    def test_terminal_history_corruption_fails_closed_and_visible(
            self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        original = history.read_text(encoding="utf-8")
        history.write_text(
            original.replace("EXPIRED", "EXPIRED_TAMPERED"), encoding="utf-8")
        with pytest.raises(TerminalHistoryCorruptionError):
            TerminalHistoryArchive(history)
        with pytest.raises(TerminalHistoryCorruptionError):
            Watchlist.load(
                tmp_path / "watch_state.jsonl", max_size=8,
                terminal_history_path=history)
        # unparseable line fails closed the same way
        history.write_text(original + "{not json\n", encoding="utf-8")
        with pytest.raises(TerminalHistoryCorruptionError):
            TerminalHistoryArchive(history)

    def test_archive_write_failure_does_not_silently_lose_state(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        archive = FlakyArchive(history, fail_appends=1)
        watch = Watchlist(max_size=1, terminal_history=archive)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        # archive append failed: candidate is NOT discarded — it stays in the
        # durable map with its terminal status, visibly pending
        summary = watch.summary()
        assert summary["terminal_archive_failed"] == 1
        assert summary["terminal_pending_archive"] == 1
        assert summary["terminal_history"] == 0
        assert summary["terminal_archive_last_error"] \
            == "ARCHIVE_WRITE_FAILED:InjectedOSError"
        entry = watch.get(_mint(0))
        assert entry is not None and entry.status == WATCH_EXPIRED
        # the failed-archive terminal entry holds NO active slot
        assert watch.active_count() == 0
        admitted, outcome = watch.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and admitted is not None
        # persist retries the archive: exactly one row, slot released, no dupe
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        assert watch.summary()["terminal_pending_archive"] == 0
        assert watch.terminal_history_count() == 1
        assert len(_history_lines(history)) == 1
        assert watch.get(_mint(0)) is None

    def test_checkpoint_write_failure_does_not_duplicate_terminal_history(
            self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 2)
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)   # checkpoint still contains both as ACTIVE
        _expire_all(watch)     # archive succeeds (2 rows), entries evicted
        assert len(_history_lines(history)) == 2
        # simulate the checkpoint rewrite failing/crashing AFTER archive:
        # the stale checkpoint still holds both entries; a restart must
        # migrate them idempotently without duplicating history rows.
        reloaded = Watchlist.load(
            state, max_size=8, terminal_history_path=history)
        assert reloaded.active_count() == 2   # stale checkpoint rows were ACTIVE
        assert reloaded.terminal_history_count() == 2
        assert len(_history_lines(history)) == 2
        # and a checkpoint that captured them EXPIRED migrates to the same rows
        rows = [json.dumps({
            "token_mint": _mint(i), "candidate_id": f"cap{i}",
            "migration_time_utc": None, "source_ref": None,
            "seeded_at_utc": NOW, "status": "EXPIRED",
            "last_reason": "NEVER_REACHED_ACTIVATION_THRESHOLD",
        }) for i in range(2)]
        state.write_text("\n".join(rows) + "\n", encoding="utf-8")
        migrated = Watchlist.load(
            state, max_size=8, terminal_history_path=history)
        assert migrated.active_count() == 0
        assert migrated.terminal_history_count() == 2
        assert len(_history_lines(history)) == 2

    def test_successful_send_ledger_is_not_terminal_history_storage(
            self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        ledger = tmp_path / "dedupe.jsonl"
        ledger.write_text("", encoding="utf-8")
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 2)
        _sent_ok(watch, _mint(0))
        _expire_all(watch)
        # terminalization wrote history rows and touched the ledger ZERO times
        assert len(_history_lines(history)) == 2
        assert ledger.read_text(encoding="utf-8") == ""
        for record in _history_lines(history):
            assert record["schema_version"] == TERMINAL_HISTORY_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Restart and legacy checkpoint migration (required tests 16-19)
# ---------------------------------------------------------------------------


class TestRestartAndMigration:
    def test_restart_restores_active_entries_only(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 4)
        _sent_ok(watch, _mint(0))
        watch.record_recheck(
            mint=_mint(1), reason="NOT_PUMP_SUFFIX", observed_at_utc=LATER)
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        restored = Watchlist.load(
            state, max_size=8, terminal_history_path=history)
        assert sorted(e.token_mint for e in restored.all_entries()) \
            == [_mint(2), _mint(3)]
        assert restored.active_count() == 2
        assert restored.terminal_history_count() == 2

    def test_restart_does_not_restore_expired_entries_as_active(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 2)
        _expire_all(watch)
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        restored = Watchlist.load(
            state, max_size=8, terminal_history_path=history)
        assert restored.active_count() == 0
        assert restored.tracked_entries() == []
        assert restored.get(_mint(0)) is None
        assert restored.summary()["by_status"].get("EXPIRED", 0) == 2

    def test_restart_does_not_restore_successful_sends_as_active(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        state = tmp_path / "watch_state.jsonl"
        # legacy-style checkpoint captured BEFORE eviction existed: the
        # committed send is still a row in watch_state
        state.write_text(json.dumps({
            "token_mint": _mint(0), "candidate_id": "cap0",
            "migration_time_utc": None, "source_ref": None,
            "seeded_at_utc": NOW, "status": "SENT_OK_COMMITTED",
            "last_reason": "SENT_OK_COMMITTED",
            "delivery_state": "SENT_OK_COMMITTED",
        }) + "\n", encoding="utf-8")
        restored = Watchlist.load(
            state, max_size=8, terminal_history_path=history)
        assert restored.active_count() == 0
        assert restored.tracked_entries() == []
        assert restored.get(_mint(0)) is None
        assert restored.terminal_history_count() == 1
        (record,) = _history_lines(history)
        assert record["terminal_status"] == "SENT_OK_COMMITTED"

    def test_legacy_mixed_checkpoint_migrates_correctly(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        state = tmp_path / "watch_state.jsonl"
        rows = [
            {"token_mint": _mint(0), "candidate_id": "cap0",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "EXPIRED",
             "last_reason": "NEVER_REACHED_ACTIVATION_THRESHOLD"},
            {"token_mint": _mint(1), "candidate_id": "cap1",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "SENT_OK_COMMITTED",
             "last_reason": "SENT_OK_COMMITTED"},
            {"token_mint": _mint(2), "candidate_id": "cap2",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "DEDUPE_SUPPRESSED",
             "last_reason": "DEDUPE_SUPPRESSED"},
            {"token_mint": _mint(3), "candidate_id": "cap3",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "SEND_ATTEMPTED",
             "last_reason": "SEND_ATTEMPTED"},
            {"token_mint": _mint(4), "candidate_id": "cap4",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "PENDING_BASELINE",
             "last_reason": "PENDING_MIGRATION_BASELINE"},
            {"token_mint": _mint(5), "candidate_id": "cap5",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "DELIVERY_UNKNOWN",
             "last_reason": "DELIVERY_UNKNOWN",
             "delivery_state": "DELIVERY_UNKNOWN"},
            {"token_mint": _mint(6), "candidate_id": "cap6",
             "migration_time_utc": None, "source_ref": None,
             "seeded_at_utc": NOW, "status": "SOME_FUTURE_STATE",
             "last_reason": "AMBIGUOUS"},
        ]
        state.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        restored = Watchlist.load(
            state, max_size=4, terminal_history_path=history)
        summary = restored.summary()
        # terminal rows migrated out; active/unresolved preserved
        assert summary["legacy_terminal_migrated"] == 4
        assert restored.terminal_history_count() == 4
        assert sorted(e.token_mint for e in restored.all_entries()) \
            == [_mint(4), _mint(5)]
        # capacity pressure comes ONLY from non-terminal entries
        assert restored.active_count() == 2
        assert restored.tracked_entries()[0].token_mint == _mint(4)
        assert len(restored.tracked_entries()) == 1
        # PHX2-E2E-005: an unsupported legacy status fails closed into the
        # durable QUARANTINE set — visible, unscheduled, never erased, and
        # never resurrectable by re-seeding.
        assert restored.get(_mint(6)) is None
        quarantined = restored.quarantined_candidate_records()
        assert _mint(6) in quarantined
        assert quarantined[_mint(6)]["quarantine_reason"] \
            == "CHECKPOINT_LEGACY_STATUS_UNSUPPORTED"
        assert summary["checkpoint_quarantined_candidates"] == 1
        blocked, outcome = restored.seed_with_outcome(
            {"token_mint": _mint(6), "candidate_id": "cap6b"},
            seeded_at_utc=LATER)
        assert blocked is None and outcome == "CHECKPOINT_QUARANTINED"
        # migrated terminal rows do not resurrect
        for index in range(4):
            assert restored.get(_mint(index)) is None
        # migration is idempotent across a second restart
        restored.persist(state)
        again = Watchlist.load(
            state, max_size=4, terminal_history_path=history)
        assert again.terminal_history_count() == 4
        assert len(_history_lines(history)) == 4
        assert again.active_count() == 2
        assert _mint(6) in again.quarantined_candidate_records()

    def test_over_capacity_checkpoint_restores_all_actives_fail_closed(
            self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=8, terminal_history_path=history)
        _seed_admitted(watch, 8)
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        # capacity later lowered: nothing is silently dropped; admissions block
        restored = Watchlist.load(
            state, max_size=2, terminal_history_path=history)
        assert restored.active_count() == 8
        assert restored.summary()["active_capacity_remaining"] == 0
        rejected, r_outcome = restored.seed_with_outcome(
            _cand(9), seeded_at_utc=LATER)
        assert rejected is None and r_outcome == SEED_OUTCOME_CAPACITY

    def test_repeated_restart_counts_stay_deterministic(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        state = tmp_path / "watch_state.jsonl"
        watch = Watchlist(max_size=2, terminal_history_path=history)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        watch.persist(state)
        # restart 1: admit a replacement, terminalize it
        restart1 = Watchlist.load(
            state, max_size=2, terminal_history_path=history)
        assert restart1.active_count() == 0
        assert restart1.terminal_history_count() == 1
        entry, outcome = restart1.seed_with_outcome(_cand(1), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None
        _expire_all(restart1)
        restart1.persist(state)
        # restart 2: both terminal, zero active, capacity fully free
        restart2 = Watchlist.load(
            state, max_size=2, terminal_history_path=history)
        summary = restart2.summary()
        assert summary["active"] == 0
        assert summary["terminal_history"] == 2
        assert summary["active_capacity_remaining"] == 2
        assert summary["total"] == 2
        assert len(_history_lines(history)) == 2


# ---------------------------------------------------------------------------
# Scheduler isolation and observability (required tests 23-25)
# ---------------------------------------------------------------------------


def _run_bounded_watch(watch, *, max_ticks, on_heartbeat=None):
    mono = {"t": 0.0}
    engine_calls = []

    def stub_engine(cands, **_kw):
        engine_calls.append([c.get("token_mint") for c in cands])
        return {
            "per_candidate": [
                {"token_mint": c.get("token_mint"),
                 "reason": "MARKET_NOT_READY",
                 "compose_attempted": False,
                 "market_context": {}}
                for c in cands
            ],
            "sent_attempt": None,
            "eligible_candidate": None,
            "outcome": "ZERO_SEND",
        }

    result = run_production_live_watch(
        watchlist=watch,
        axiom_source=axiomgate.NullAxiomFeeSource(),
        axiom_config=fst.fts._strict_axiom_config(),
        sidecar_factory=lambda _t: SimpleNamespace(
            stats=lambda: {"market_attempts_total": 0}),
        ath_transport=object(), ath_endpoint_secret=object(),
        ledger=object(),
        guard_factory=lambda: object(),
        authorization=object(),
        now_dt_fn=lambda: datetime.now(timezone.utc),
        now_iso_fn=lambda: LATER,
        now_seconds=make_constant_clock(fst.Decimal(0)),
        sleep_fn=lambda s: mono.__setitem__("t", mono["t"] + s),
        monotonic_fn=lambda: mono["t"],
        bounds=ProductionBounds(
            recheck_interval_seconds=1.0,
            max_candidate_age_seconds=99999999,
            max_rechecks_per_candidate=999999,
            max_runtime_seconds=999999.0,
            min_seconds_between_sends=0.0,
            max_total_ticks=max_ticks,
        ),
        run_cap1_candidates_fn=stub_engine,
        ledger_line_count_fn=lambda: 0,
        on_heartbeat=on_heartbeat,
    )
    return result, engine_calls


class TestSchedulerIsolation:
    def test_terminal_candidates_receive_zero_market_refresh_calls(
            self, tmp_path):
        watch = _watch(tmp_path, 8)
        _seed_admitted(watch, 3)
        _sent_ok(watch, _mint(0))
        _expire_all(watch)   # expires 1 and 2
        entry, outcome = watch.seed_with_outcome(_cand(3), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None
        result, engine_calls = _run_bounded_watch(watch, max_ticks=3)
        assert result["stop_reason"] == "TICK_BUDGET"
        assert engine_calls, "engine must run for the active candidate"
        for tick_mints in engine_calls:
            assert tick_mints == [_mint(3)], (
                "terminal candidates must never enter market/engine work")

    def test_terminal_candidates_receive_zero_compose_attempts(self, tmp_path):
        watch = _watch(tmp_path, 8)
        _seed_admitted(watch, 2)
        _expire_all(watch)
        # nothing active: the engine (the only compose path) never runs
        result, engine_calls = _run_bounded_watch(watch, max_ticks=3)
        assert result["stop_reason"] == "WATCHLIST_EMPTY"
        assert engine_calls == []
        assert result["sends"] == 0

    def test_watchlist_count_reports_active_count(self, tmp_path):
        watch = _watch(tmp_path, 8)
        _seed_admitted(watch, 3)
        _sent_ok(watch, _mint(0))
        summary = watch.summary()
        assert summary["watchlist_count"] == 2
        assert summary["watchlist_count"] == summary["tracked"]
        heartbeats = []
        result, _calls = _run_bounded_watch(
            watch, max_ticks=2, on_heartbeat=heartbeats.append)
        del result
        assert heartbeats
        hb = heartbeats[-1]
        assert hb["watchlist_count"] == 2
        assert hb["watchlist_terminal_history_total"] == 1
        assert hb["watchlist_active_capacity"] == 8
        assert hb["watchlist_capacity_rejections"] == 0
        # terminal history is reported separately, never as tracked work
        assert hb["watchlist_tracked"] == 2
        assert hb["sent_committed_total"] == 1

    def test_observe_market_on_pending_archive_terminal_is_inert(self, tmp_path):
        archive = FlakyArchive(
            tmp_path / "terminal_history.jsonl", fail_appends=1)
        watch = Watchlist(max_size=4, terminal_history=archive)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        entry = watch.get(_mint(0))
        assert entry is not None and entry.status == WATCH_EXPIRED
        out = entry.observe_market(
            current_market_cap_usd="1000", current_price="1",
            current_supply="1000", provider_timestamp_utc=LATER,
            observed_at_utc=LATER, observation_source="PAID_MARKET_PRIMARY",
            max_age_seconds=120.0)
        assert out["reason"] == "TERMINAL_STATE"
        assert out["eligible"] is False


class TestSeedHandoffEvents:
    def test_capacity_rejection_emits_explicit_diagnostic_event(self, tmp_path):
        watch = _watch(tmp_path, 1)
        _seed_admitted(watch, 1)
        events = []
        seed_discovered_candidates(
            watchlist=watch,
            candidates=[_cand(1)],
            seeded_at_utc=LATER,
            on_handoff_event=events.append,
        )
        assert [e["event"] for e in events] \
            == ["RUNNER_RECEIVED", "WATCHLIST_REJECTED"]
        rejection = events[-1]
        assert rejection["reason"] == "ACTIVE_WATCH_CAPACITY_REACHED"
        assert rejection["token_mint"] == _mint(1)
        assert rejection["candidate_id"] == "cap1"
        assert rejection["active_count"] == 1
        assert rejection["active_capacity"] == 1
        assert rejection["observed_at_utc"] == LATER

    def test_invalid_candidate_rejection_stays_distinct(self, tmp_path):
        watch = _watch(tmp_path, 1)
        events = []
        seed_discovered_candidates(
            watchlist=watch,
            candidates=[{"candidate_id": "no-mint"}],
            seeded_at_utc=LATER,
            on_handoff_event=events.append,
        )
        assert events[-1]["event"] == "WATCHLIST_REJECTED"
        assert events[-1]["reason"] == "INVALID_CANDIDATE"

    def test_terminal_duplicate_seed_is_acknowledged_not_rejected(
            self, tmp_path):
        watch = _watch(tmp_path, 2)
        _seed_admitted(watch, 1)
        _expire_all(watch)
        events = []
        seed_discovered_candidates(
            watchlist=watch,
            candidates=[_cand(0)],
            seeded_at_utc=LATER,
            on_handoff_event=events.append,
        )
        assert events[-1]["event"] == "WATCHLIST_ACKNOWLEDGED"
        assert events[-1]["admission"] == "TERMINAL_HISTORY_DUPLICATE"
        assert watch.get(_mint(0)) is None

    def test_admitted_candidate_still_emits_added(self, tmp_path):
        watch = _watch(tmp_path, 2)
        events = []
        activation_events = []
        seed_discovered_candidates(
            watchlist=watch,
            candidates=[_cand(0)],
            seeded_at_utc=NOW,
            on_handoff_event=events.append,
            on_activation_event=activation_events.append,
        )
        assert events[-1]["event"] == "WATCHLIST_ACKNOWLEDGED"
        assert events[-1]["admission"] == "ADDED"
        assert any(e.get("event") == "MIGRATION_DETECTED"
                   for e in activation_events)


# ---------------------------------------------------------------------------
# Boundary capacities and scale
# ---------------------------------------------------------------------------


class TestBoundaryCapacities:
    def test_negative_capacity_fails_validation(self, tmp_path):
        with pytest.raises(ValueError):
            Watchlist(max_size=-1,
                      terminal_history_path=tmp_path / "history.jsonl")

    def test_zero_capacity_rejects_all_explicitly(self, tmp_path):
        watch = _watch(tmp_path, 0)
        entry, outcome = watch.seed_with_outcome(_cand(0), seeded_at_utc=NOW)
        assert entry is None and outcome == SEED_OUTCOME_CAPACITY
        assert watch.summary()["capacity_rejections"] == 1
        assert watch.summary()["active_capacity"] == 0

    @pytest.mark.parametrize("capacity", [1, 2, 127, 128, 129])
    def test_capacity_boundary_fill_reject_release_admit(self, tmp_path, capacity):
        watch = _watch(tmp_path, capacity)
        _seed_admitted(watch, capacity)
        assert watch.active_count() == capacity
        blocked, outcome = watch.seed_with_outcome(
            _cand(capacity), seeded_at_utc=LATER)
        assert blocked is None and outcome == SEED_OUTCOME_CAPACITY
        _sent_ok(watch, _mint(0))
        admitted, admit_outcome = watch.seed_with_outcome(
            _cand(capacity), seeded_at_utc=LATER)
        assert admit_outcome == SEED_OUTCOME_ADMITTED and admitted is not None
        assert watch.active_count() == capacity
        assert watch.terminal_history_count() == 1

    def test_configured_production_default_capacity_is_128(self):
        parser = argparse.ArgumentParser()
        fst.fts._add_args(parser)
        args = parser.parse_args([])
        assert int(args.max_watchlist_size) == 128


class TestLifecycleScale:
    def test_1000_sequential_expiring_candidates_stay_bounded(self, tmp_path):
        history = tmp_path / "terminal_history.jsonl"
        watch = Watchlist(max_size=2, terminal_history_path=history)
        max_in_map = 0
        for index in range(1000):
            entry, outcome = watch.seed_with_outcome(
                _cand(index), seeded_at_utc=NOW)
            assert outcome == SEED_OUTCOME_ADMITTED and entry is not None, index
            _expire_all(watch)
            # the active scheduling map stays bounded — terminal history
            # never lingers inside it (no O(N)-history scan per tick)
            max_in_map = max(max_in_map, len(watch.all_entries()))
        assert max_in_map <= 2
        assert watch.active_count() == 0
        assert watch.terminal_history_count() == 1000
        entry, outcome = watch.seed_with_outcome(_cand(1000), seeded_at_utc=LATER)
        assert outcome == SEED_OUTCOME_ADMITTED and entry is not None
        summary = watch.summary()
        assert summary["active"] == 1
        assert summary["by_status"]["EXPIRED"] == 1000
        assert summary["total"] == 1001
        # history remains queryable and restart-deterministic
        assert len(_history_lines(history)) == 1000
        state = tmp_path / "watch_state.jsonl"
        watch.persist(state)
        restored = Watchlist.load(
            state, max_size=2, terminal_history_path=history)
        assert restored.active_count() == 1
        assert restored.terminal_history_count() == 1000


# ---------------------------------------------------------------------------
# Real ledgers are never touched (required test 30)
# ---------------------------------------------------------------------------


class TestRealLedgersUntouched:
    def test_real_production_ledgers_unchanged_by_capacity_suite(self, tmp_path):
        active = ps.DEFAULT_ACTIVE_LEDGER
        frozen = ps.DEFAULT_FROZEN_LEDGER
        if not (active.is_file() and frozen.is_file()):
            pytest.skip("real operator ledgers not present on this machine")
        before_active = hashlib.sha256(active.read_bytes()).hexdigest()
        before_frozen = hashlib.sha256(frozen.read_bytes()).hexdigest()
        watch = _watch(tmp_path, 128)
        _seed_admitted(watch, 128)
        _expire_all(watch)
        watch.seed_with_outcome(_cand(128), seeded_at_utc=LATER)
        watch.persist(tmp_path / "watch_state.jsonl")
        Watchlist.load(tmp_path / "watch_state.jsonl", max_size=128,
                       terminal_history_path=tmp_path / "terminal_history.jsonl")
        assert hashlib.sha256(active.read_bytes()).hexdigest() == before_active
        assert hashlib.sha256(frozen.read_bytes()).hexdigest() == before_frozen
