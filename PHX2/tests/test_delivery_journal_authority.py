"""PHX2 delivery-journal authority proofs (PHX2-E2E-001 HIGH + E2E-009 MEDIUM).

Two invariants are proven here, both structurally rather than by convention:

1. NO DURABLE TRANSPORT-START RECORD -> NO TRANSPORT INVOCATION.
   Before the correction, ``execute_guarded_delivery`` discarded the result of
   ``record_transport_started``: a failed durable append still dispatched, the
   remote delivery happened with no durable evidence, restart released the
   lease, and a retry delivered a SECOND time (lifetime transport calls == 2).

2. A receipt is valid ONLY from a durable, binding-consistent
   TRANSPORT_IN_PROGRESS predecessor. Before the correction the journal
   accepted ``LEASED -> RECEIPT`` and restart reconciliation committed it as a
   successful-send ledger row.

Every test uses fake transports, deterministic injected clocks and temporary
journals/ledgers. The real production ping ledgers are never opened.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_selftest as fst
from PHX2.free_tier_producer.compat.build30_watchlist import Watchlist
from PHX2.free_tier_producer.delivery_transaction import (
    COUNTER_DISPATCH_BLOCKED,
    COUNTER_RECEIPT_BINDING_MISMATCH,
    COUNTER_RECEIPT_CONFLICT,
    COUNTER_RECEIPT_PREDECESSOR_INVALID,
    COUNTER_RESTART_INVALID_SEQUENCE,
    COUNTER_RESTART_UNKNOWN_TRANSPORT,
    COUNTER_START_ATTEMPTED,
    COUNTER_START_FAILED,
    COUNTER_START_PERSISTED,
    COUNTER_SUCCESS_COMMIT_RECONCILED,
    DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL,
    DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID,
    DELIVERY_STATE_SENT_OK_COMMITTED,
    DELIVERY_STATE_TRANSPORT_IN_PROGRESS,
    DELIVERY_STATE_UNKNOWN,
    EVENT_DELIVERY_RECEIPT,
    REFUSAL_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH,
    REFUSAL_RECEIPT_CONFLICT,
    REFUSAL_RECEIPT_PREDECESSOR_INVALID,
    REFUSAL_TRANSPORT_START_PERSIST_FAILED,
    RELEASE_REASON_LEASE_EXPIRED_STALE,
    WRITE_BINDING_MISMATCH,
    WRITE_CONFLICT,
    WRITE_ILLEGAL_TRANSITION,
    WRITE_JOURNAL_UNAVAILABLE,
    WRITE_PERSISTED,
    WRITE_READBACK_FAILED,
    DeliveryAttemptJournal,
    JournalWriteResult,
    dedupe_key_to_dict,
    execute_guarded_delivery,
    reconcile_journal_on_restart,
    reconcile_watchlist_delivery,
    resolve_unknown_attempt,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import JsonlPingDedupeLedger
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    STAGE30_11_15_DEFAULT_TTL_SECONDS,
    Stage30_11_15PingDedupeKey,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import make_constant_clock
from PHX2.free_tier_producer.compat.build29_cap1_market_sidecar import (
    Cap1MarketCaps,
    Cap1MarketSidecar,
)

TTL = STAGE30_11_15_DEFAULT_TTL_SECONDS
BODY = "PHOENIX offline authority-proof body"
T0 = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)

KEY = Stage30_11_15PingDedupeKey(
    token_mint=fst.MINT,
    operator_signal_kind="PRIVATE_OPERATOR_DIP_PING",
    tier_token="Tier 2",
    drawdown_band="DD_BAND_060_065",
    post_migration_ath_verified=True,
    ath_source_stage="STAGE_30_8_ANCHORED",
    policy_version="phx2_stage30_11_15_v1",
)

CANDIDATE_ID = "authority-probe"


def _z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip())


def _events(path: Path):
    if not path.exists():
        return []
    return [json.loads(line)["event"]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _deduped():
    snapshot = SimpleNamespace(tier_token=KEY.tier_token)
    compose = SimpleNamespace(token_mint=fst.MINT, candidate_id=CANDIDATE_ID,
                              snapshot=snapshot, dispatched_body=BODY)
    return SimpleNamespace(compose_result=compose)


class CountingGuard:
    """Fake transport seam; counts everything that reaches the wire."""

    def __init__(self, *, ok=True, status="SENT_OK", attempted=True):
        self.calls = 0
        self._ok = ok
        self._status = status
        self._attempted = attempted

    def authorize_and_dispatch(self, deduped, *, authorization, created_at_utc):
        self.calls += 1
        return SimpleNamespace(transport_attempted=self._attempted,
                               transport_ok=self._ok,
                               transport_status=self._status, message_id=4242,
                               reason="GUARD_REFUSED")


class FalseStartJournal(DeliveryAttemptJournal):
    """The durable transport-start append reports failure (disk error)."""

    def record_transport_started(self, attempt_id, **kwargs):
        self._mark_unavailable("JOURNAL_WRITE_FAILED")
        return JournalWriteResult("WRITE_FAILED", "JOURNAL_WRITE_FAILED")


class BareFalseStartJournal(DeliveryAttemptJournal):
    """Legacy-shaped journal returning a bare ``False``."""

    def record_transport_started(self, attempt_id, **kwargs):
        return False


class RaisingStartJournal(DeliveryAttemptJournal):
    def record_transport_started(self, attempt_id, **kwargs):
        raise OSError("synthetic fsync failure")


class ReadbackFailureJournal(DeliveryAttemptJournal):
    """Append lands but the read-back verification does not match."""

    def __init__(self, *, path):
        super().__init__(path=path)
        self._arm = False

    def record_transport_started(self, attempt_id, **kwargs):
        self._arm = True
        try:
            return super().record_transport_started(attempt_id, **kwargs)
        finally:
            self._arm = False

    def _readback_ok(self, offset, line):
        if self._arm:
            return False
        return super()._readback_ok(offset, line)


def _run_delivery(*, journal, ledger, guard, now=T0, lease_seconds=900):
    return execute_guarded_delivery(
        deduped=_deduped(), guard=guard, authorization=SimpleNamespace(),
        created_at_utc=_z(now), journal=journal, ledger=ledger,
        dedupe_key=KEY, snapshot_body=BODY, ttl_seconds=TTL,
        lease_seconds=lease_seconds)


def _lease(journal, *, now=T0, lease_seconds=900, candidate_id=CANDIDATE_ID):
    return journal.acquire_lease(
        key_map=dedupe_key_to_dict(KEY), token_mint=KEY.token_mint,
        candidate_id=candidate_id, tier_token=KEY.tier_token,
        snapshot_body_sha256="a" * 64, now_utc=_z(now),
        lease_seconds=lease_seconds)


# ---------------------------------------------------------------------------
# Engine-path helper (requirements 7, 8: watch terminalization / sent marking)
# ---------------------------------------------------------------------------


def _make_market_sidecar(anchor):
    transport = fst.make_transport(fst.make_fake_urlopen(anchor=anchor))
    secret = fst.build_free_tier_endpoint_secret()
    sidecar = Cap1MarketSidecar(
        transport=transport, endpoint_secret=secret, timeout_seconds=10,
        enabled=True,
        caps=Cap1MarketCaps(max_delayed_refresh_seconds=0,
                            max_calls_per_token=4, max_calls_total=64))
    return transport, secret, sidecar


class EngineSuccessTransport:
    def __init__(self):
        self.calls = 0

    def send_one_audited_post(self, *, webhook_identity, payload):
        self.calls += 1
        return SimpleNamespace(ok=True, transport_status="SENT_OK",
                               message_id=4242)


def _run_engine_candidate(*, ledger, private_transport, journal):
    anchor = datetime.now(timezone.utc) - timedelta(seconds=fst._NOW_OFFSET_S)
    market_transport, secret, sidecar = _make_market_sidecar(anchor)
    now = datetime.now(timezone.utc)
    candidate = {
        "token_mint": fst.MINT,
        "candidate_id": CANDIDATE_ID,
        "migration_time_utc": _z(anchor),
        "source_ref": None,
        "symbol_or_name": None,
    }
    return fst._run_activated_candidates(
        [candidate], sidecar=sidecar, ath_transport=market_transport,
        ath_endpoint_secret=secret, now_utc=now,
        now_seconds=make_constant_clock(fst.Decimal(0)),
        now_iso_fn=lambda: _z(now), sleep_fn=lambda _s: None, ledger=ledger,
        guard=fst.cs.make_guard(transport=private_transport),
        authorization=fst.cs.build_authorization(
            confirm_token=fst.fts.LOCKED_CONFIRM_TOKEN,
            operator_label="OFFLINE_DELIVERY_AUTHORITY_TEST",
            authorization_reason="OFFLINE_FAKE_TRANSPORT",
            created_at_utc=_z(now)),
        created_at_utc=_z(now), pump_required=True, delivery_journal=journal)


# ---------------------------------------------------------------------------
# 1-4: the transport-start append is the sole dispatch authority
# ---------------------------------------------------------------------------


class TestTransportStartIsAuthoritative:
    def test_1_healthy_start_is_required_and_precedes_dispatch(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        guard = CountingGuard()
        out = _run_delivery(
            journal=journal, guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert out["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        assert guard.calls == 1
        # The durable start record exists and PRECEDES the receipt on disk.
        events = _events(outbox)
        assert events.index("TRANSPORT_IN_PROGRESS") < events.index(
            EVENT_DELIVERY_RECEIPT)
        assert journal.counters()[COUNTER_START_PERSISTED] == 1
        assert journal.counters()[COUNTER_START_ATTEMPTED] == 1

    def test_2_false_return_blocks_transport(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        guard = CountingGuard()
        out = _run_delivery(
            journal=FalseStartJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert guard.calls == 0
        assert out["delivery_state"] == DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL
        assert out["transport_invoked"] is False
        assert _events(outbox) == ["ATTEMPT_RESERVED"]

    def test_2b_bare_false_is_not_dispatch_authority(self, tmp_path):
        """A legacy bare ``False`` (or any non-typed truthy value) can never
        authorize dispatch: only an explicit durable result may."""
        guard = CountingGuard()
        out = _run_delivery(
            journal=BareFalseStartJournal(path=tmp_path / "outbox.jsonl"),
            guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert guard.calls == 0
        assert out["delivery_state"] == DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL

    def test_3_raised_write_exception_blocks_transport(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        guard = CountingGuard()
        out = _run_delivery(
            journal=RaisingStartJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert guard.calls == 0
        assert out["delivery_state"] == DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL
        # The raw exception never escapes and never reaches the reason.
        assert out["refusal_reason"] == REFUSAL_TRANSPORT_START_PERSIST_FAILED
        assert "synthetic fsync failure" not in json.dumps(
            {k: v for k, v in out.items() if k != "send_result"})

    def test_4_readback_failure_blocks_transport(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = ReadbackFailureJournal(path=outbox)
        guard = CountingGuard()
        out = _run_delivery(
            journal=journal, guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert guard.calls == 0
        assert out["journal_write_status"] == WRITE_READBACK_FAILED
        assert out["delivery_state"] == DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL
        # In-memory state must NOT claim the transport started.
        assert journal.attempt(out["attempt_id"]).transport_started is False

    def test_4b_truncated_last_line_fails_the_journal_closed(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        raw = outbox.read_text(encoding="utf-8")
        outbox.write_text(raw[:-12], encoding="utf-8")     # partial tail write
        restarted = DeliveryAttemptJournal(path=outbox)
        assert restarted.available is False
        guard = CountingGuard()
        out = _run_delivery(
            journal=restarted, guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert guard.calls == 0
        assert out["refusal_reason"] == "JOURNAL_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 5-10: consequences of a failed transport-start persistence
# ---------------------------------------------------------------------------


class TestFailedStartPersistenceConsequences:
    def _blocked(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = FalseStartJournal(path=outbox)
        guard = CountingGuard()
        out = _run_delivery(journal=journal, guard=guard,
                            ledger=JsonlPingDedupeLedger(path=ledger_path))
        return out, journal, guard, outbox, ledger_path

    def test_5_creates_zero_receipts(self, tmp_path):
        _, _, _, outbox, _ = self._blocked(tmp_path)
        assert EVENT_DELIVERY_RECEIPT not in _events(outbox)

    def test_6_creates_zero_success_rows(self, tmp_path):
        _, _, _, _, ledger_path = self._blocked(tmp_path)
        assert _rows(ledger_path) == 0

    def test_7_does_not_terminalize_the_watch(self, tmp_path):
        out, _, _, _, _ = self._blocked(tmp_path)
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(T0))
        watch.record_recheck(
            mint=fst.MINT,
            reason="NO_SEND_DELIVERY_" + out["delivery_state"],
            observed_at_utc=_z(T0),
            delivery_state=out["delivery_state"])
        assert entry.is_active()
        assert entry.status != "SENT_OK_COMMITTED"
        assert watch.summary()["sent_committed"] == 0

    def test_8_does_not_mark_sent(self, tmp_path):
        out, _, _, _, _ = self._blocked(tmp_path)
        assert out["ledger_committed"] is False
        assert out["delivery_state"] != DELIVERY_STATE_SENT_OK_COMMITTED
        # It is NOT reported as a transport failure either: nothing was sent.
        assert out["delivery_state"] != "DELIVERY_FAILED_RETRYABLE"
        assert out["send_result"] is None

    def test_9_exposes_the_exact_closed_reason(self, tmp_path):
        out, journal, _, _, _ = self._blocked(tmp_path)
        assert out["refusal_reason"] == REFUSAL_TRANSPORT_START_PERSIST_FAILED
        assert journal.counters()[COUNTER_DISPATCH_BLOCKED] == 1
        assert journal.counters()[COUNTER_START_PERSISTED] == 0

    def test_9c_real_persistence_failure_counts_attempt_and_failure(
            self, tmp_path):
        """Counters through the REAL ``record_transport_started`` body (the
        read-back gate), not a whole-method override."""
        journal = ReadbackFailureJournal(path=tmp_path / "outbox.jsonl")
        guard = CountingGuard()
        out = _run_delivery(
            journal=journal, guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"))
        assert guard.calls == 0
        assert out["delivery_state"] == DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL
        assert journal.counters()[COUNTER_START_ATTEMPTED] == 1
        assert journal.counters()[COUNTER_START_FAILED] == 1
        assert journal.counters()[COUNTER_START_PERSISTED] == 0
        assert journal.counters()[COUNTER_DISPATCH_BLOCKED] == 1

    def test_9b_unavailable_journal_has_its_own_reason(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        journal._mark_unavailable("JOURNAL_WRITE_FAILED")
        guard = CountingGuard()
        started = journal.record_transport_started(attempt_id, now_utc=_z(T0))
        assert started.status == WRITE_JOURNAL_UNAVAILABLE
        assert started.dispatch_authorized is False
        assert guard.calls == 0
        from PHX2.free_tier_producer.delivery_transaction import (
            _start_failure_reason,
        )
        assert _start_failure_reason(started) == \
            REFUSAL_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH

    def test_10_does_not_create_a_busy_retry_loop(self, tmp_path):
        """The lease is NOT released on a blocked dispatch: the immediately
        following pass is refused by the still-held lease rather than spinning
        on the transport."""
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        guard = CountingGuard()
        _run_delivery(journal=FalseStartJournal(path=outbox), guard=guard,
                      ledger=JsonlPingDedupeLedger(path=ledger_path))
        for offset in (1, 2, 3):
            again = _run_delivery(
                journal=DeliveryAttemptJournal(path=outbox), guard=guard,
                ledger=JsonlPingDedupeLedger(path=ledger_path),
                now=T0 + timedelta(seconds=offset))
            assert again["refusal_reason"] == "ATTEMPT_LEASE_HELD"
        assert guard.calls == 0
        assert _rows(ledger_path) == 0


# ---------------------------------------------------------------------------
# 11-13, restart prefixes 1 and 2
# ---------------------------------------------------------------------------


class TestRestartPrefixes:
    def test_11_leased_only_releases_safely(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, refusal = _lease(journal)
        assert attempt_id is not None and refusal is None
        restarted = DeliveryAttemptJournal(path=outbox)
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(
                path=tmp_path / "dedupe.jsonl"),
            now_utc=_z(T0 + timedelta(seconds=1000)), ttl_seconds=TTL)
        assert report["leases_released"] == 1
        assert report["commits_completed"] == 0
        assert report["unknown_marked"] == 0
        assert restarted.attempt(attempt_id).release_reason == \
            RELEASE_REASON_LEASE_EXPIRED_STALE
        # A later healthy attempt is permitted and dispatches exactly once.
        guard = CountingGuard()
        out = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            now=T0 + timedelta(seconds=1001))
        assert guard.calls == 1
        assert out["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED

    def test_12_transport_started_only_becomes_operator_held_unknown(
            self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        restarted = DeliveryAttemptJournal(path=outbox)
        assert restarted.attempt(attempt_id).state() == \
            DELIVERY_STATE_TRANSPORT_IN_PROGRESS
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(
                path=tmp_path / "dedupe.jsonl"),
            now_utc=_z(T0 + timedelta(seconds=1000)), ttl_seconds=TTL)
        assert report["unknown_marked"] == 1
        assert report["pending_unknown"] == 1
        assert report["leases_released"] == 0        # never auto-released
        assert report["commits_completed"] == 0
        assert restarted.counters()[COUNTER_RESTART_UNKNOWN_TRANSPORT] == 1
        assert restarted.attempt(attempt_id).state() == DELIVERY_STATE_UNKNOWN

    def test_13_transport_started_only_never_auto_retries(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        restarted = DeliveryAttemptJournal(path=outbox)
        reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=1000)), ttl_seconds=TTL)
        guard = CountingGuard()
        out = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            now=T0 + timedelta(seconds=5000))
        assert guard.calls == 0
        assert out["refusal_reason"] == \
            "DELIVERY_UNKNOWN_PENDING_RECONCILIATION"
        assert _rows(ledger_path) == 0

    def test_transport_in_progress_lease_expiry_release_is_refused(
            self, tmp_path):
        """The duplicate window itself: stale-lease expiry must never release
        an attempt that already authorized a transport call."""
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        refused = journal.release_lease(
            attempt_id, release_reason=RELEASE_REASON_LEASE_EXPIRED_STALE,
            now_utc=_z(T0 + timedelta(seconds=5000)))
        assert refused.status == WRITE_ILLEGAL_TRANSITION
        assert refused.detail == "TRANSPORT_IN_PROGRESS_REQUIRES_OPERATOR"
        assert journal.attempt(attempt_id).released is False


# ---------------------------------------------------------------------------
# 14-21: receipt predecessor validation
# ---------------------------------------------------------------------------


class TestReceiptPredecessorValidation:
    def test_16_success_receipt_requires_transport_in_progress(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        result = journal.record_receipt(
            attempt_id, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0))
        assert result.status == WRITE_ILLEGAL_TRANSITION
        assert result.detail == "REQUIRES_TRANSPORT_IN_PROGRESS"
        assert bool(result) is False

    def test_17_receipt_directly_after_leased_rejects(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert not journal.record_receipt(
            attempt_id, message_id=1, transport_status="SENT_OK",
            now_utc=_z(T0))
        # Nothing durable was written; the attempt stays plainly LEASED.
        assert _events(outbox) == ["ATTEMPT_RESERVED"]
        assert journal.attempt(attempt_id).receipt is None

    def test_18_receipt_with_no_attempt_rejects(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        result = journal.record_receipt(
            "does-not-exist", message_id=1, transport_status="SENT_OK",
            now_utc=_z(T0))
        assert result.status == WRITE_ILLEGAL_TRANSITION
        assert result.detail == "ATTEMPT_NOT_FOUND"

    def test_19_receipt_after_released_lease_rejects(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert journal.release_lease(
            attempt_id, release_reason=RELEASE_REASON_LEASE_EXPIRED_STALE,
            now_utc=_z(T0 + timedelta(seconds=1000)))
        result = journal.record_receipt(
            attempt_id, message_id=1, transport_status="SENT_OK",
            now_utc=_z(T0 + timedelta(seconds=1001)))
        assert result.status == WRITE_ILLEGAL_TRANSITION

    def test_14_20_explicit_failure_receipt_rules(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        # 14: an explicit-failure outcome requires TRANSPORT_IN_PROGRESS.
        leased_only, _ = _lease(journal)
        assert not journal.record_failed_retryable(
            leased_only, transport_status="HTTP_400", now_utc=_z(T0))
        assert journal.attempt(leased_only).failed_retryable is False
        # 20: after an explicit failure, a receipt cannot attach.
        assert journal.record_transport_started(leased_only, now_utc=_z(T0))
        assert journal.record_failed_retryable(
            leased_only, transport_status="HTTP_400", now_utc=_z(T0))
        result = journal.record_receipt(
            leased_only, message_id=1, transport_status="SENT_OK",
            now_utc=_z(T0))
        assert result.status == WRITE_ILLEGAL_TRANSITION

    def test_15_unknown_outcome_requires_transport_in_progress(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert not journal.record_unknown(
            attempt_id, transport_status="TIMEOUT", now_utc=_z(T0))
        assert journal.attempt(attempt_id).unknown is False

    def test_21_receipt_after_unknown_only_via_operator_api(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        assert journal.record_unknown(
            attempt_id, transport_status="TIMEOUT", now_utc=_z(T0))
        # Plain receipt: refused.
        plain = journal.record_receipt(
            attempt_id, message_id=1, transport_status="SENT_OK",
            now_utc=_z(T0))
        assert plain.status == WRITE_ILLEGAL_TRANSITION
        assert plain.detail == "REQUIRES_TRANSPORT_IN_PROGRESS"
        # Explicit operator reconciliation: permitted, exactly one row.
        resolved = resolve_unknown_attempt(
            journal=journal, ledger=JsonlPingDedupeLedger(path=ledger_path),
            attempt_id=attempt_id, resolution="CONFIRMED_DELIVERED",
            now_utc=_z(T0 + timedelta(seconds=1)), ttl_seconds=TTL)
        assert resolved["resolved"] is True
        assert _rows(ledger_path) == 1


# ---------------------------------------------------------------------------
# 22-30: immutable binding validation, idempotence and conflict
# ---------------------------------------------------------------------------


class TestReceiptBindings:
    def _started(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        return journal, attempt_id

    def _receipt(self, journal, attempt_id, **bindings):
        return journal.record_receipt(
            attempt_id, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0), **bindings)

    def test_22_wrong_attempt_id_rejects(self, tmp_path):
        journal, _ = self._started(tmp_path)
        assert self._receipt(journal, "wrong-attempt").status == \
            WRITE_ILLEGAL_TRANSITION

    @pytest.mark.parametrize("binding,value", [
        ("expected_candidate_id", "some-other-candidate"),      # 23
        ("expected_token_mint", "WrongMint1111111111111111111111111111pump"),  # 24
        ("expected_tier_token", "Tier 3"),                      # 25
        ("expected_snapshot_body_sha256", "b" * 64),            # 26
        ("expected_delivery_generation", 7),                    # 28
    ])
    def test_23_to_28_binding_mismatches_reject(self, tmp_path, binding, value):
        journal, attempt_id = self._started(tmp_path)
        result = self._receipt(journal, attempt_id, **{binding: value})
        assert result.status == WRITE_BINDING_MISMATCH
        assert journal.attempt(attempt_id).receipt is None
        assert journal.counters()[COUNTER_RECEIPT_BINDING_MISMATCH] == 1

    def test_27_wrong_ledger_key_rejects(self, tmp_path):
        journal, attempt_id = self._started(tmp_path)
        other = dict(dedupe_key_to_dict(KEY))
        other["drawdown_band"] = "DD_BAND_070_075"
        result = self._receipt(journal, attempt_id, expected_dedupe_key=other)
        assert result.status == WRITE_BINDING_MISMATCH
        assert result.detail == "LEDGER_KEY_MISMATCH"

    def test_29_duplicate_identical_receipt_is_idempotent(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        first = self._receipt(journal, attempt_id)
        assert first.status == WRITE_PERSISTED
        again = journal.record_receipt(
            attempt_id, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0 + timedelta(seconds=30)))     # later clock, same id
        assert bool(again) is True
        assert again.status == "ALREADY_PERSISTED"
        assert _events(outbox).count(EVENT_DELIVERY_RECEIPT) == 1
        reconcile_journal_on_restart(
            journal=DeliveryAttemptJournal(path=outbox),
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=60)), ttl_seconds=TTL)
        assert _rows(ledger_path) == 1

    def test_30_conflicting_duplicate_receipt_fails_closed(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        assert self._receipt(journal, attempt_id).status == WRITE_PERSISTED
        conflict = journal.record_receipt(
            attempt_id, message_id=9999, transport_status="SENT_OK",
            now_utc=_z(T0))
        assert conflict.status == WRITE_CONFLICT
        assert journal.counters()[COUNTER_RECEIPT_CONFLICT] == 1
        assert _events(outbox).count(EVENT_DELIVERY_RECEIPT) == 1

    def test_31_illegal_transition_counter_increments_exactly_once(
            self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert journal.counters()[COUNTER_RECEIPT_PREDECESSOR_INVALID] == 0
        journal.record_receipt(attempt_id, message_id=1,
                               transport_status="SENT_OK", now_utc=_z(T0))
        assert journal.counters()[COUNTER_RECEIPT_PREDECESSOR_INVALID] == 1


# ---------------------------------------------------------------------------
# 32-35: successful-send ledger authority
# ---------------------------------------------------------------------------


class TestSuccessLedgerAuthority:
    def test_32_confirmed_success_commits_exactly_one_row(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        guard = CountingGuard()
        out = _run_delivery(
            journal=DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl"),
            guard=guard, ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert out["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        assert out["ledger_committed"] is True
        assert guard.calls == 1
        assert _rows(ledger_path) == 1

    def test_33_restart_after_receipt_commits_once(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        assert journal.record_receipt(
            attempt_id, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0))
        restarted = DeliveryAttemptJournal(path=outbox)
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=5)), ttl_seconds=TTL)
        assert report["commits_completed"] == 1
        assert restarted.counters()[COUNTER_SUCCESS_COMMIT_RECONCILED] == 1
        assert _rows(ledger_path) == 1

    def test_34_35_restart_after_commit_is_idempotent(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        guard = CountingGuard()
        _run_delivery(journal=DeliveryAttemptJournal(path=outbox), guard=guard,
                      ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert guard.calls == 1 and _rows(ledger_path) == 1
        for offset in (10, 20):
            report = reconcile_journal_on_restart(
                journal=DeliveryAttemptJournal(path=outbox),
                ledger=JsonlPingDedupeLedger(path=ledger_path),
                now_utc=_z(T0 + timedelta(seconds=offset)), ttl_seconds=TTL)
            assert report["commits_completed"] == 0
        assert guard.calls == 1                 # 34: no further transport
        assert _rows(ledger_path) == 1          # 35: no further append


# ---------------------------------------------------------------------------
# 36-40: retry, unknown and operator resolution
# ---------------------------------------------------------------------------


class TestRetryAndUnknownPolicy:
    def test_36_37_explicit_failure_retries_once_when_healthy(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        failing = CountingGuard(ok=False, status="HTTP_400")
        first = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=failing,
            ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert first["delivery_state"] == "DELIVERY_FAILED_RETRYABLE"
        assert failing.calls == 1
        assert _rows(ledger_path) == 0
        healthy = CountingGuard()
        retry = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=healthy,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            now=T0 + timedelta(seconds=60))
        assert healthy.calls == 1
        assert retry["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        assert _rows(ledger_path) == 1

    def test_38_39_delivery_unknown_is_operator_held(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        ambiguous = CountingGuard(ok=False, status="TIMEOUT")
        out = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=ambiguous,
            ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert out["delivery_state"] == DELIVERY_STATE_UNKNOWN
        assert ambiguous.calls == 1
        for offset in (60, 120, 5000):
            again = _run_delivery(
                journal=DeliveryAttemptJournal(path=outbox), guard=ambiguous,
                ledger=JsonlPingDedupeLedger(path=ledger_path),
                now=T0 + timedelta(seconds=offset))
            assert again["refusal_reason"] == \
                "DELIVERY_UNKNOWN_PENDING_RECONCILIATION"
        assert ambiguous.calls == 1             # 39: zero automatic calls
        assert _rows(ledger_path) == 0

    def test_40_operator_release_then_healthy_retry_sends_once(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        ambiguous = CountingGuard(ok=False, status="TIMEOUT")
        _run_delivery(journal=DeliveryAttemptJournal(path=outbox),
                      guard=ambiguous,
                      ledger=JsonlPingDedupeLedger(path=ledger_path))
        journal = DeliveryAttemptJournal(path=outbox)
        pending = journal.all_attempts()[0]
        resolved = resolve_unknown_attempt(
            journal=journal, ledger=JsonlPingDedupeLedger(path=ledger_path),
            attempt_id=pending.attempt_id,
            resolution="CONFIRMED_NOT_DELIVERED",
            now_utc=_z(T0 + timedelta(seconds=60)), ttl_seconds=TTL)
        assert resolved["resolved"] is True
        healthy = CountingGuard()
        retry = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=healthy,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            now=T0 + timedelta(seconds=61))
        assert healthy.calls == 1
        assert retry["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        assert _rows(ledger_path) == 1


# ---------------------------------------------------------------------------
# 41-46: no prefix short of a validated confirmed receipt writes a success row
# ---------------------------------------------------------------------------


class TestZeroSuccessRowsForEveryNonSuccessPrefix:
    def test_41_compose_alone(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        assert _rows(ledger_path) == 0

    def test_42_lease_alone(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        _lease(journal)
        reconcile_journal_on_restart(
            journal=journal, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=1)), ttl_seconds=TTL)
        assert _rows(ledger_path) == 0

    def test_43_transport_start_alone(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        journal.record_transport_started(attempt_id, now_utc=_z(T0))
        reconcile_journal_on_restart(
            journal=journal, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=1)), ttl_seconds=TTL)
        assert _rows(ledger_path) == 0

    def test_44_explicit_failure(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        _run_delivery(journal=DeliveryAttemptJournal(
            path=tmp_path / "outbox.jsonl"),
            guard=CountingGuard(ok=False, status="HTTP_400"),
            ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert _rows(ledger_path) == 0

    def test_45_unknown_outcome(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        _run_delivery(journal=DeliveryAttemptJournal(
            path=tmp_path / "outbox.jsonl"),
            guard=CountingGuard(ok=False, status="TIMEOUT"),
            ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert _rows(ledger_path) == 0

    def test_46_forged_receipt_without_start_is_quarantined(self, tmp_path):
        """Restart prefix 6: a durable LEASED -> RECEIPT sequence already on
        disk (corrupt/forged/legacy) must never commit."""
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        # Forge a validly-digested receipt with NO transport-start predecessor.
        assert journal._append({
            "event": EVENT_DELIVERY_RECEIPT,
            "attempt_id": attempt_id,
            "token_mint": KEY.token_mint,
            "candidate_id": CANDIDATE_ID,
            "tier_token": KEY.tier_token,
            "dedupe_key": dedupe_key_to_dict(KEY),
            "snapshot_body_sha256": "a" * 64,
            "delivery_generation": 0,
            "message_id": 4242,
            "transport_status": "SENT_OK",
            "recorded_at_utc": _z(T0),
        })
        restarted = DeliveryAttemptJournal(path=outbox)
        state = restarted.attempt(attempt_id)
        assert state.receipt is not None
        assert state.receipt_after_start is False
        assert state.invalid_sequence() is True
        assert state.state() == DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=5)), ttl_seconds=TTL)
        assert report["invalid_sequences"] == 1
        assert report["commits_completed"] == 0
        assert report["details"][0]["action"] == "INVALID_SEQUENCE_QUARANTINED"
        assert report["details"][0]["reason"] == \
            REFUSAL_RECEIPT_PREDECESSOR_INVALID
        assert restarted.counters()[COUNTER_RESTART_INVALID_SEQUENCE] == 1
        assert _rows(ledger_path) == 0
        assert restarted.pending_commits() == []
        # The key stays blocked until an operator resolves it: no auto-retry.
        guard = CountingGuard()
        blocked = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            now=T0 + timedelta(seconds=6000))
        assert guard.calls == 0
        assert blocked["refusal_reason"] == \
            "DELIVERY_RECEIPT_SEQUENCE_INVALID_PENDING_RECONCILIATION"
        # An operator cannot promote a quarantined sequence to a success.
        promoted = resolve_unknown_attempt(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            attempt_id=attempt_id, resolution="CONFIRMED_DELIVERED",
            now_utc=_z(T0 + timedelta(seconds=10)), ttl_seconds=TTL)
        assert promoted["resolved"] is False
        assert _rows(ledger_path) == 0

    def test_conflicting_duplicate_receipts_on_disk_fail_closed(self, tmp_path):
        """Restart prefix 7: two conflicting durable receipts pick no winner."""
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        base = {
            "event": EVENT_DELIVERY_RECEIPT, "attempt_id": attempt_id,
            "token_mint": KEY.token_mint, "candidate_id": CANDIDATE_ID,
            "tier_token": KEY.tier_token,
            "dedupe_key": dedupe_key_to_dict(KEY),
            "snapshot_body_sha256": "a" * 64, "delivery_generation": 0,
            "transport_status": "SENT_OK", "recorded_at_utc": _z(T0),
        }
        assert journal._append({**base, "message_id": 1})
        assert journal._append({**base, "message_id": 2})
        restarted = DeliveryAttemptJournal(path=outbox)
        assert restarted.attempt(attempt_id).receipt_conflict is True
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(T0 + timedelta(seconds=5)), ttl_seconds=TTL)
        assert report["invalid_sequences"] == 1
        assert report["details"][0]["reason"] == REFUSAL_RECEIPT_CONFLICT
        assert _rows(ledger_path) == 0


# ---------------------------------------------------------------------------
# 47-48: in-flight expiry and generation binding
# ---------------------------------------------------------------------------


class TestGenerationAndInFlightSafety:
    def test_47_candidate_expiry_during_valid_attempt_stays_safe(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        guard = CountingGuard()
        out = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=ledger_path))
        assert out["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        # The watch entry expired while the attempt was in flight.
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(T0))
        entry.status = "EXPIRED"
        events = reconcile_watchlist_delivery(
            watchlist=watch, journal=DeliveryAttemptJournal(path=outbox),
            now_utc=_z(T0 + timedelta(seconds=10)))
        assert events == []                   # nothing resurrected
        assert guard.calls == 1
        assert _rows(ledger_path) == 1

    def test_48_late_receipt_cannot_attach_to_a_newer_generation(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        first, _ = _lease(journal)
        assert journal.attempt(first).delivery_generation == 0
        assert journal.release_lease(
            first, release_reason=RELEASE_REASON_LEASE_EXPIRED_STALE,
            now_utc=_z(T0 + timedelta(seconds=1000)))
        second, _ = _lease(journal, now=T0 + timedelta(seconds=1001))
        assert second != first
        assert journal.attempt(second).delivery_generation == 1
        assert journal.record_transport_started(
            second, now_utc=_z(T0 + timedelta(seconds=1001)))
        # A receipt from the OLD generation cannot bind to the new attempt.
        stale = journal.record_receipt(
            second, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0 + timedelta(seconds=1002)),
            expected_delivery_generation=0)
        assert stale.status == WRITE_BINDING_MISMATCH
        assert stale.detail == "DELIVERY_GENERATION_MISMATCH"
        # The correct generation binds cleanly.
        good = journal.record_receipt(
            second, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0 + timedelta(seconds=1002)),
            expected_delivery_generation=1)
        assert good.status == WRITE_PERSISTED
        # A receipt can never attach to the released older attempt.
        assert not journal.record_receipt(
            first, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0 + timedelta(seconds=1003)))


# ---------------------------------------------------------------------------
# Engine-path integration (requirements 7, 8) and observability (57)
# ---------------------------------------------------------------------------


class TestEnginePathAndObservability:
    def test_blocked_dispatch_keeps_the_engine_candidate_active(self, tmp_path):
        """Through the REAL engine: a blocked dispatch never sends, never
        commits, never terminalizes, and is never labelled a transport
        failure."""
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        transport = EngineSuccessTransport()
        out = _run_engine_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=transport,
            journal=FalseStartJournal(path=outbox))
        rec = out["per_candidate"][0]
        assert transport.calls == 0
        assert out["outcome"] != "ONE_SEND_COMMITTED"
        assert rec["reason"] == (
            "NO_SEND_DELIVERY_" + DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL)
        assert rec["delivery_refusal_reason"] == \
            REFUSAL_TRANSPORT_START_PERSIST_FAILED
        assert rec["reason"] != "SEND_ATTEMPTED"
        assert rec["reason"] != "DELIVERY_FAILED_RETRYABLE"
        assert _rows(ledger_path) == 0
        # The watch entry survives for a later healthy attempt.
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(T0))
        watch.record_recheck(mint=fst.MINT, reason=rec["reason"],
                             observed_at_utc=_z(T0),
                             delivery_state=rec.get("delivery_state"))
        assert entry.is_active()
        assert watch.summary()["sent_committed"] == 0

    def test_healthy_engine_path_still_commits_exactly_once(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        transport = EngineSuccessTransport()
        out = _run_engine_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=transport,
            journal=DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl"))
        assert out["outcome"] == "ONE_SEND_COMMITTED"
        assert out["per_candidate"][0]["reason"] == "SENT_OK_COMMITTED"
        assert transport.calls == 1
        assert _rows(ledger_path) == 1

    def test_blocked_dispatch_is_distinguishable_in_artifacts(self):
        """Operator/artifact surfaces must separate a journal-persistence
        failure from a transport failure, a sent state and a generic unknown."""
        from PHX2.free_tier_producer.compat.build30_artifacts import (
            B30_DELIVERY_DISPATCH_BLOCKED,
            B30_DELIVERY_FAILED_RETRYABLE,
            B30_SENT_OK_COMMITTED,
            B30_UNKNOWN,
            map_rejection_reason,
        )
        mapped = map_rejection_reason(
            "NO_SEND_DELIVERY_" + DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL)
        assert mapped == B30_DELIVERY_DISPATCH_BLOCKED
        assert mapped not in (B30_DELIVERY_FAILED_RETRYABLE,
                              B30_SENT_OK_COMMITTED, B30_UNKNOWN)
        # The committed tokens keep their existing mappings.
        assert map_rejection_reason("SENT_OK_COMMITTED") == B30_SENT_OK_COMMITTED
        assert map_rejection_reason("DELIVERY_FAILED_RETRYABLE") == \
            B30_DELIVERY_FAILED_RETRYABLE

    def test_quarantined_sequence_can_be_released_by_operator(self, tmp_path):
        """A quarantined receipt sequence blocks retries but is not a permanent
        dead end: an explicit NOT_DELIVERED resolution unblocks the key."""
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        attempt_id, _ = _lease(journal)
        assert journal._append({
            "event": EVENT_DELIVERY_RECEIPT, "attempt_id": attempt_id,
            "token_mint": KEY.token_mint, "candidate_id": CANDIDATE_ID,
            "tier_token": KEY.tier_token,
            "dedupe_key": dedupe_key_to_dict(KEY),
            "snapshot_body_sha256": "a" * 64, "delivery_generation": 0,
            "message_id": 4242, "transport_status": "SENT_OK",
            "recorded_at_utc": _z(T0),
        })
        restarted = DeliveryAttemptJournal(path=outbox)
        resolved = resolve_unknown_attempt(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            attempt_id=attempt_id, resolution="CONFIRMED_NOT_DELIVERED",
            now_utc=_z(T0 + timedelta(seconds=60)), ttl_seconds=TTL)
        assert resolved["resolved"] is True
        assert _rows(ledger_path) == 0
        guard = CountingGuard()
        retry = _run_delivery(
            journal=DeliveryAttemptJournal(path=outbox), guard=guard,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            now=T0 + timedelta(seconds=61))
        assert guard.calls == 1
        assert retry["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        assert _rows(ledger_path) == 1

    def test_57_new_reasons_and_diagnostics_are_redaction_safe(self, tmp_path):
        """Every new closed-set token is an uppercase ASCII identifier and the
        observable surface carries no payload, endpoint or credential."""
        tokens = (
            DELIVERY_STATE_DISPATCH_BLOCKED_JOURNAL,
            DELIVERY_STATE_RECEIPT_SEQUENCE_INVALID,
            REFUSAL_TRANSPORT_START_PERSIST_FAILED,
            REFUSAL_JOURNAL_UNAVAILABLE_BEFORE_DISPATCH,
            REFUSAL_RECEIPT_PREDECESSOR_INVALID,
            REFUSAL_RECEIPT_CONFLICT,
        )
        for token in tokens:
            assert token.replace("_", "").isalnum()
            assert token == token.upper()
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        attempt_id, _ = _lease(journal)
        assert journal.record_transport_started(attempt_id, now_utc=_z(T0))
        assert journal.record_receipt(
            attempt_id, message_id=4242, transport_status="SENT_OK",
            now_utc=_z(T0))
        blob = json.dumps(journal.observable_states()) + json.dumps(
            journal.counters())
        # Needles are assembled from fragments so this negative-control list
        # cannot itself trip the production secret scanner (the failure class
        # that aborted the 2026-07-18 acceptance run).
        banned = ("bot", "http", "Authoriz" + "ation", "web" + "hook",
                  "token" + "=", BODY)
        for needle in banned:
            assert needle not in blob
        state = journal.observable_states()[0]
        assert state["transport_dispatched"] is True
        assert state["receipt_sequence_valid"] is True
        assert state["success_ledger_committed"] is False
