"""PHX2-E2E-001 delivery transaction proofs.

Reproduces the 2026-07-18 end-to-end audit probe (a fake transient Telegram
failure must NOT burn the durable successful-send dedupe row or terminalize the
watch) and then proves the corrected delivery transaction state machine:

    ATTEMPT_RESERVED -> TRANSPORT_IN_PROGRESS
        -> { SENT_OK_COMMITTED | DELIVERY_FAILED_RETRYABLE | DELIVERY_UNKNOWN }

The durable successful-send ledger is appended ONLY after confirmed
``transport_ok=True`` (or during restart reconciliation from a durable
confirmed-success receipt). Every test uses fake transports and temporary
ledgers/journals only; the real production ping ledgers are never opened.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_selftest as fst
from PHX2.free_tier_producer.compat.build30_watchlist import Watchlist
from PHX2.free_tier_producer.delivery_transaction import (
    CLASSIFY_CONFIRMED_OK,
    CLASSIFY_FAILED_RETRYABLE,
    CLASSIFY_NOT_ATTEMPTED,
    CLASSIFY_UNKNOWN,
    DELIVERY_STATE_SENT_OK_COMMITTED,
    DELIVERY_STATE_UNKNOWN,
    DeliveryAttemptJournal,
    classify_transport_result,
    compute_retry_backoff_seconds,
    reconcile_journal_on_restart,
    reconcile_watchlist_delivery,
    resolve_unknown_attempt,
)
from PHX2.runtime import production_supervisor as ps
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
    JsonlPingDedupeLedger,
    PeekOnlyPingDedupeLedgerView,
)
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

KEY = Stage30_11_15PingDedupeKey(
    token_mint=fst.MINT,
    operator_signal_kind="PRIVATE_OPERATOR_DIP_PING",
    tier_token="Tier 2",
    drawdown_band="DD_BAND_060_065",
    post_migration_ath_verified=True,
    ath_source_stage="STAGE_30_8_ANCHORED",
    policy_version="phx2_stage30_11_15_v1",
)


def _z(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ledger_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip())


def _make_market_sidecar(anchor: datetime):
    transport = fst.make_transport(fst.make_fake_urlopen(anchor=anchor))
    secret = fst.build_free_tier_endpoint_secret()
    sidecar = Cap1MarketSidecar(
        transport=transport,
        endpoint_secret=secret,
        timeout_seconds=10,
        enabled=True,
        caps=Cap1MarketCaps(
            max_delayed_refresh_seconds=0,
            max_calls_per_token=4,
            max_calls_total=64,
        ),
    )
    return transport, secret, sidecar


class FailedTransport:
    """Explicit transient transport failure (the audit probe's fake)."""

    def __init__(self):
        self.calls = 0

    def send_one_audited_post(self, *, webhook_identity, payload):
        self.calls += 1
        return SimpleNamespace(ok=False, transport_status="FAKE_TRANSIENT_FAILURE")


class SuccessTransport:
    def __init__(self):
        self.calls = 0
        self.last_payload = None

    def send_one_audited_post(self, *, webhook_identity, payload):
        self.calls += 1
        self.last_payload = dict(payload)
        return SimpleNamespace(
            ok=True, transport_status="SENT_OK", message_id=4242)


class AmbiguousTimeoutTransport:
    """Dispatch began but the outcome is ambiguous (client-side timeout)."""

    def __init__(self):
        self.calls = 0

    def send_one_audited_post(self, *, webhook_identity, payload):
        self.calls += 1
        return SimpleNamespace(ok=False, transport_status="TIMEOUT")


def _run_candidate(*, ledger, private_transport, anchor, journal=None,
                   candidate_extra=None, guard=None, evidence=None):
    market_transport, secret, sidecar = _make_market_sidecar(anchor)
    now = datetime.now(timezone.utc)
    candidate = {
        "token_mint": fst.MINT,
        "candidate_id": "delivery-txn-test",
        "migration_time_utc": _z(anchor),
        "source_ref": None,
        "symbol_or_name": None,
    }
    if candidate_extra:
        candidate.update(candidate_extra)
    kwargs = {}
    if journal is not None:
        kwargs["delivery_journal"] = journal
    if evidence is not None:
        kwargs["axiom_fee_appender"] = evidence
    return fst._run_activated_candidates(
        [candidate],
        sidecar=sidecar,
        ath_transport=market_transport,
        ath_endpoint_secret=secret,
        now_utc=now,
        now_seconds=make_constant_clock(fst.Decimal(0)),
        now_iso_fn=lambda: _z(now),
        sleep_fn=lambda _seconds: None,
        ledger=ledger,
        guard=(guard if guard is not None
               else fst.cs.make_guard(transport=private_transport)),
        authorization=fst.cs.build_authorization(
            confirm_token=fst.fts.LOCKED_CONFIRM_TOKEN,
            operator_label="OFFLINE_DELIVERY_TXN_TEST",
            authorization_reason="OFFLINE_FAKE_TRANSPORT",
            created_at_utc=_z(now),
        ),
        created_at_utc=_z(now),
        pump_required=True,
        **kwargs,
    )


def _anchor():
    return datetime.now(timezone.utc) - timedelta(seconds=fst._NOW_OFFSET_S)


# ---------------------------------------------------------------------------
# PHX2-E2E-001 audit-probe reproduction (MUST fail before the correction)
# ---------------------------------------------------------------------------


class TestAuditProbeReproduction:
    """The exact audit failure-ordering probe, asserted against the REQUIRED
    (corrected) contract. At the defective HEAD these assertions fail: the
    fake transient failure left one durable ledger row, labelled the candidate
    SEND_ATTEMPTED (terminal), and suppressed the healthy retry."""

    def test_fake_transient_failure_appends_zero_successful_send_rows(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        anchor = _anchor()
        failed = FailedTransport()
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=failed,
            anchor=anchor,
        )
        assert failed.calls == 1
        send_result = out["sent_attempt"]["send_result"]
        assert send_result.transport_ok is False
        # REQUIRED: a failed delivery must not append the successful-send ledger.
        assert _ledger_lines(ledger_path) == 0

    def test_fake_transient_failure_is_not_terminal_send_attempted(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        anchor = _anchor()
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=FailedTransport(),
            anchor=anchor,
        )
        reason = out["per_candidate"][0]["reason"]
        assert reason != "SEND_ATTEMPTED"
        watch = Watchlist(max_size=4)
        entry = watch.seed(
            {"token_mint": fst.MINT, "candidate_id": "terminal-probe"},
            seeded_at_utc=_z(datetime.now(timezone.utc)))
        watch.record_recheck(
            mint=fst.MINT,
            reason=reason,
            observed_at_utc=_z(datetime.now(timezone.utc)),
        )
        # REQUIRED: an explicit transport failure keeps the watch active.
        assert entry.is_active()

    def test_healthy_retry_after_failure_reaches_transport_and_commits_once(
            self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        anchor = _anchor()
        _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=FailedTransport(),
            anchor=anchor,
        )
        assert _ledger_lines(ledger_path) == 0
        healthy = SuccessTransport()
        retry = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy,
            anchor=anchor,
        )
        # REQUIRED: the healthy retry is NOT dedupe-suppressed; it calls the
        # transport, succeeds, and commits exactly one successful-send row.
        assert healthy.calls == 1
        assert retry["sent_attempt"]["send_result"].transport_ok is True
        assert _ledger_lines(ledger_path) == 1

    def test_crash_after_reservation_before_transport_does_not_burn_alert(
            self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        anchor = _anchor()

        class CrashBeforeTransportGuard:
            def authorize_and_dispatch(self, *args, **kwargs):
                raise RuntimeError(
                    "synthetic crash after reservation before transport")

        with pytest.raises(RuntimeError):
            _run_candidate(
                ledger=JsonlPingDedupeLedger(path=ledger_path),
                private_transport=None,
                anchor=anchor,
                guard=CrashBeforeTransportGuard(),
            )
        # REQUIRED: the crash between attempt reservation and transport leaves
        # no successful-send ledger row ...
        assert _ledger_lines(ledger_path) == 0
        # ... and the restart retry is permitted (transport is called).
        healthy = SuccessTransport()
        retry = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy,
            anchor=anchor,
        )
        assert healthy.calls == 1
        assert retry["sent_attempt"]["send_result"].transport_ok is True
        assert _ledger_lines(ledger_path) == 1


# ---------------------------------------------------------------------------
# Transport classification (closed set; never fabricates success)
# ---------------------------------------------------------------------------


class TestTransportClassification:
    def _result(self, **kw):
        base = {"transport_attempted": True, "dispatch_forwarded": True,
                "transport_ok": False, "transport_status": None,
                "message_id": None}
        base.update(kw)
        return SimpleNamespace(**base)

    def test_confirmed_ok(self):
        assert classify_transport_result(self._result(
            transport_ok=True, transport_status="SENT_OK")) \
            == CLASSIFY_CONFIRMED_OK

    def test_explicit_failures_are_retryable(self):
        for status in ("RATE_LIMITED", "AUTHENTICATION_FAILED",
                       "CHAT_NOT_FOUND", "BOT_NOT_ALLOWED", "MESSAGE_REJECTED",
                       "MESSAGE_TOO_LONG", "TRANSPORT_CLOSED",
                       "FAKE_TRANSIENT_FAILURE"):
            assert classify_transport_result(self._result(
                transport_status=status)) == CLASSIFY_FAILED_RETRYABLE, status

    def test_ambiguous_statuses_are_unknown(self):
        for status in ("TIMEOUT", "NETWORK_ERROR", "MALFORMED_RESPONSE",
                       "UNKNOWN_FAILURE"):
            assert classify_transport_result(self._result(
                transport_status=status)) == CLASSIFY_UNKNOWN, status

    def test_attempted_with_no_verdict_is_unknown(self):
        assert classify_transport_result(self._result(
            transport_ok=None, transport_status=None)) == CLASSIFY_UNKNOWN

    def test_not_attempted(self):
        assert classify_transport_result(None) == CLASSIFY_NOT_ATTEMPTED
        assert classify_transport_result(self._result(
            transport_attempted=False)) == CLASSIFY_NOT_ATTEMPTED

    def test_backoff_is_bounded_and_deterministic(self):
        assert compute_retry_backoff_seconds(0) == 60
        assert compute_retry_backoff_seconds(1) == 120
        assert compute_retry_backoff_seconds(2) == 240
        assert compute_retry_backoff_seconds(99) == 3600


# ---------------------------------------------------------------------------
# Explicit-failure path (tests 1-7, 10)
# ---------------------------------------------------------------------------


class TestExplicitFailureRetryPath:
    def test_failure_schedules_bounded_retry(self, tmp_path):
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            private_transport=FailedTransport(),
            anchor=_anchor(),
        )
        rec = out["per_candidate"][0]
        assert out["outcome"] == "ONE_SEND_FAILED_RETRYABLE"
        assert rec["reason"] == "DELIVERY_FAILED_RETRYABLE"
        assert rec["delivery_retry_count"] == 1
        assert rec["delivery_failure_reason"] == "FAKE_TRANSIENT_FAILURE"
        scheduled = datetime.fromisoformat(
            rec["delivery_next_retry_at_utc"].replace("Z", "+00:00"))
        assert scheduled > datetime.now(timezone.utc)
        assert scheduled <= datetime.now(timezone.utc) + timedelta(hours=2)

    def test_backoff_skips_candidate_before_any_market_call(self, tmp_path):
        class BoomSidecar:
            def resolve(self, *a, **k):
                raise AssertionError("market must not be called during backoff")

        future = _z(datetime.now(timezone.utc) + timedelta(minutes=10))
        now = datetime.now(timezone.utc)
        out = fst._run_activated_candidates(
            [{"token_mint": fst.MINT, "candidate_id": "backoff-1",
              "migration_time_utc": _z(_anchor()), "source_ref": None,
              "symbol_or_name": None,
              "delivery_next_retry_at_utc": future,
              "delivery_retry_count": 1}],
            sidecar=BoomSidecar(),
            ath_transport=object(), ath_endpoint_secret=object(),
            now_utc=now, now_seconds=make_constant_clock(fst.Decimal(0)),
            now_iso_fn=lambda: _z(now), sleep_fn=lambda _s: None,
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            guard=object(), authorization=object(),
            created_at_utc=_z(now), pump_required=True)
        assert out["outcome"] == "ZERO_SEND"
        assert out["per_candidate"][0]["reason"] == "DELIVERY_RETRY_BACKOFF"

    def test_duplicate_after_committed_retry_is_suppressed(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        anchor = _anchor()
        _run_candidate(ledger=JsonlPingDedupeLedger(path=ledger_path),
                       private_transport=FailedTransport(), anchor=anchor)
        healthy = SuccessTransport()
        committed = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=anchor)
        assert committed["outcome"] == "ONE_SEND_COMMITTED"
        assert committed["per_candidate"][0]["reason"] == "SENT_OK_COMMITTED"
        assert _ledger_lines(ledger_path) == 1
        late = SuccessTransport()
        duplicate = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=late, anchor=anchor)
        assert duplicate["outcome"] == "ZERO_SEND"
        assert late.calls == 0
        assert duplicate["per_candidate"][0].get("compose_reason") \
            == "DEDUPE_SUPPRESSED_DUPLICATE"
        assert _ledger_lines(ledger_path) == 1

    def test_failure_reason_flows_into_active_watch_retry_metadata(self, tmp_path):
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            private_transport=FailedTransport(), anchor=_anchor())
        rec = out["per_candidate"][0]
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(datetime.now(timezone.utc)))
        watch.record_recheck(
            mint=fst.MINT, reason=rec["reason"],
            observed_at_utc=_z(datetime.now(timezone.utc)),
            delivery_state=rec.get("delivery_state"),
            delivery_failure_reason=rec.get("delivery_failure_reason"),
            delivery_next_retry_at_utc=rec.get("delivery_next_retry_at_utc"),
            delivery_retry_count=rec.get("delivery_retry_count"),
            delivery_attempt_id=rec.get("delivery_attempt_id"),
        )
        assert entry.is_active()
        assert entry.status != "SEND_ATTEMPTED"
        assert entry.delivery_state == "DELIVERY_FAILED_RETRYABLE"
        assert entry.delivery_retry_count == 1
        assert entry.delivery_last_failure_reason == "FAKE_TRANSIENT_FAILURE"
        assert entry.delivery_next_retry_at_utc \
            == rec["delivery_next_retry_at_utc"]
        assert entry.delivery_attempt_id == rec["delivery_attempt_id"]
        # The retry metadata round-trips into the next engine candidate.
        cand = entry.to_candidate()
        assert cand["delivery_retry_count"] == 1
        assert cand["delivery_next_retry_at_utc"] \
            == rec["delivery_next_retry_at_utc"]


# ---------------------------------------------------------------------------
# Confirmed success (tests 5, 6, 11, 16)
# ---------------------------------------------------------------------------


class TestConfirmedSuccessCommit:
    def test_confirmed_success_commits_once_and_terminalizes(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        healthy = SuccessTransport()
        # The delivery adapter exposes the Telegram message id via last_result
        # (the committed evidence surface the receipt binds where available).
        adapter_evidence = SimpleNamespace(
            last_result=SimpleNamespace(message_id=4242))
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=_anchor(), journal=journal,
            evidence=adapter_evidence)
        rec = out["per_candidate"][0]
        assert out["outcome"] == "ONE_SEND_COMMITTED"
        assert rec["reason"] == "SENT_OK_COMMITTED"
        assert rec["delivery_receipt_message_id"] == 4242
        assert healthy.calls == 1
        assert _ledger_lines(ledger_path) == 1
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(datetime.now(timezone.utc)))
        watch.record_recheck(
            mint=fst.MINT, reason=rec["reason"],
            observed_at_utc=_z(datetime.now(timezone.utc)),
            delivery_state=rec.get("delivery_state"),
            delivery_receipt_message_id=rec.get("delivery_receipt_message_id"),
        )
        assert entry.status == "SENT_OK_COMMITTED"
        assert not entry.is_active()
        assert watch.summary()["sent_committed"] == 1
        assert watch.summary()["sent"] == 1

    def test_committed_receipt_binds_the_exact_dispatched_body(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        healthy = SuccessTransport()
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            private_transport=healthy, anchor=_anchor(), journal=journal)
        deduped = out["sent_attempt"]["deduped"]
        dispatched_body = deduped.compose_result.dispatched_body
        assert healthy.last_payload["content"] == dispatched_body
        states = journal.all_attempts()
        assert len(states) == 1
        receipt = states[0].receipt
        assert receipt is not None
        assert receipt["snapshot_body_sha256"] == hashlib.sha256(
            dispatched_body.encode("utf-8")).hexdigest()
        assert states[0].committed is True
        assert states[0].state() == DELIVERY_STATE_SENT_OK_COMMITTED


# ---------------------------------------------------------------------------
# Crash windows A/B + lease semantics (tests 8, 9, 19)
# ---------------------------------------------------------------------------


class TestLeaseAndCrashWindows:
    def _lease(self, journal, *, now_utc, lease_seconds=900):
        from PHX2.free_tier_producer.delivery_transaction import (
            dedupe_key_to_dict,
        )
        return journal.acquire_lease(
            key_map=dedupe_key_to_dict(KEY),
            token_mint=KEY.token_mint,
            candidate_id="lease-test",
            tier_token=KEY.tier_token,
            snapshot_body_sha256="a" * 64,
            now_utc=now_utc,
            lease_seconds=lease_seconds,
        )

    def test_crash_window_A_before_reservation_leaves_nothing(self, tmp_path):
        # Window A: nothing durable exists before the lease; a later retry is
        # a plain first attempt.
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        ledger_path = tmp_path / "dedupe.jsonl"
        assert journal.all_attempts() == []
        assert _ledger_lines(ledger_path) == 0
        healthy = SuccessTransport()
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=_anchor(), journal=journal)
        assert out["outcome"] == "ONE_SEND_COMMITTED"
        assert healthy.calls == 1

    def test_crash_window_B_stale_lease_recovers_on_restart(self, tmp_path):
        # Window B: crash after the temporary reservation, before transport.
        path = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=path)
        now = datetime.now(timezone.utc)
        attempt_id, refusal = self._lease(
            journal, now_utc=_z(now), lease_seconds=900)
        assert attempt_id is not None and refusal is None
        # Process crash here: nothing else recorded. Restart later:
        restarted = DeliveryAttemptJournal(path=path)
        ledger = InMemoryPingDedupeLedger()
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=ledger,
            now_utc=_z(now + timedelta(seconds=1000)), ttl_seconds=TTL)
        assert report["leases_released"] == 1
        assert report["commits_completed"] == 0
        # No successful-send row was ever written for the crashed attempt.
        assert ledger.check_only(
            key=KEY, now_utc=_z(now + timedelta(seconds=1000)),
            ttl_seconds=TTL).allowed
        # The later retry is permitted: a fresh lease acquires cleanly.
        attempt2, refusal2 = self._lease(
            restarted, now_utc=_z(now + timedelta(seconds=1001)))
        assert attempt2 is not None and refusal2 is None

    def test_concurrent_duplicate_attempts_single_active_lease(self, tmp_path):
        path = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=path)
        now = _z(datetime.now(timezone.utc))
        first, refusal_first = self._lease(journal, now_utc=now)
        assert first is not None and refusal_first is None
        second, refusal_second = self._lease(journal, now_utc=now)
        assert second is None
        assert refusal_second == "ATTEMPT_LEASE_HELD"
        # A second worker replaying the same durable journal is also refused.
        other_worker = DeliveryAttemptJournal(path=path)
        third, refusal_third = self._lease(other_worker, now_utc=now)
        assert third is None
        assert refusal_third == "ATTEMPT_LEASE_HELD"


# ---------------------------------------------------------------------------
# Crash window D + ambiguous outcomes (tests 13, 14, 15)
# ---------------------------------------------------------------------------


class TestDeliveryUnknown:
    def test_ambiguous_timeout_becomes_delivery_unknown(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=AmbiguousTimeoutTransport(),
            anchor=_anchor(), journal=journal)
        rec = out["per_candidate"][0]
        assert out["outcome"] == "ONE_SEND_UNKNOWN"
        assert rec["reason"] == "DELIVERY_UNKNOWN"
        # Never a false SENT_OK claim, never a successful-send ledger row.
        assert _ledger_lines(ledger_path) == 0
        assert out["sent_attempt"]["delivery"].get("ledger_committed") is not True

    def test_delivery_unknown_is_observable_in_status_and_watch(self, tmp_path):
        journal = DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl")
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            private_transport=AmbiguousTimeoutTransport(),
            anchor=_anchor(), journal=journal)
        rec = out["per_candidate"][0]
        states = journal.observable_states()
        assert len(states) == 1
        assert states[0]["delivery_state"] == DELIVERY_STATE_UNKNOWN
        assert states[0]["transport_status"] == "TIMEOUT"
        assert states[0]["token_mint"] == fst.MINT
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(datetime.now(timezone.utc)))
        watch.record_recheck(
            mint=fst.MINT, reason=rec["reason"],
            observed_at_utc=_z(datetime.now(timezone.utc)),
            delivery_state=rec.get("delivery_state"),
            delivery_failure_reason=rec.get("delivery_failure_reason"),
        )
        assert entry.status == "DELIVERY_UNKNOWN"
        assert not entry.is_active()          # never silently retried
        assert watch.summary()["delivery_unknown"] == 1
        assert watch.summary()["sent_committed"] == 0

    def test_crash_window_D_interrupted_transport_reconciles_to_unknown(
            self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)

        class CrashDuringDispatchGuard:
            def authorize_and_dispatch(self, *args, **kwargs):
                raise RuntimeError("synthetic crash during dispatch")

        with pytest.raises(RuntimeError):
            _run_candidate(
                ledger=JsonlPingDedupeLedger(path=ledger_path),
                private_transport=None, anchor=_anchor(), journal=journal,
                guard=CrashDuringDispatchGuard())
        assert _ledger_lines(ledger_path) == 0
        # Restart: the dangling TRANSPORT_IN_PROGRESS becomes DELIVERY_UNKNOWN.
        restarted = DeliveryAttemptJournal(path=outbox)
        ledger = JsonlPingDedupeLedger(path=ledger_path)
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=ledger,
            now_utc=_z(datetime.now(timezone.utc)), ttl_seconds=TTL)
        assert report["unknown_marked"] == 1
        assert report["pending_unknown"] == 1
        assert _ledger_lines(ledger_path) == 0
        # No uncontrolled automatic duplicate: a healthy retry over the SAME
        # durable journal is refused while the ambiguity is unresolved.
        healthy = SuccessTransport()
        blocked = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=_anchor(), journal=restarted)
        assert healthy.calls == 0
        assert blocked["outcome"] == "ZERO_SEND"
        assert blocked["per_candidate"][0]["reason"].startswith(
            "NO_SEND_DELIVERY_")
        # Explicit operator reconciliation (NOT_DELIVERED) re-enables retry.
        pending = restarted.all_attempts()[0]
        resolved = resolve_unknown_attempt(
            journal=restarted, ledger=ledger, attempt_id=pending.attempt_id,
            resolution="CONFIRMED_NOT_DELIVERED",
            now_utc=_z(datetime.now(timezone.utc)), ttl_seconds=TTL)
        assert resolved["resolved"] is True
        retry = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=_anchor(), journal=restarted)
        assert healthy.calls == 1
        assert retry["outcome"] == "ONE_SEND_COMMITTED"
        assert _ledger_lines(ledger_path) == 1

    def test_operator_confirmed_delivered_commits_without_transport(
            self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=AmbiguousTimeoutTransport(),
            anchor=_anchor(), journal=journal)
        assert _ledger_lines(ledger_path) == 0
        pending = journal.all_attempts()[0]
        ledger = JsonlPingDedupeLedger(path=ledger_path)
        resolved = resolve_unknown_attempt(
            journal=journal, ledger=ledger, attempt_id=pending.attempt_id,
            resolution="CONFIRMED_DELIVERED",
            now_utc=_z(datetime.now(timezone.utc)), ttl_seconds=TTL)
        assert resolved["resolved"] is True
        assert resolved["delivery_state"] == DELIVERY_STATE_SENT_OK_COMMITTED
        assert _ledger_lines(ledger_path) == 1
        # The committed row suppresses any later duplicate attempt.
        late = SuccessTransport()
        duplicate = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=late, anchor=_anchor(),
            journal=DeliveryAttemptJournal(path=outbox))
        assert late.calls == 0
        assert duplicate["outcome"] == "ZERO_SEND"


# ---------------------------------------------------------------------------
# Crash windows E/F: confirmed success then crash (tests 12)
# ---------------------------------------------------------------------------


class TestConfirmedSuccessCrashWindows:
    def test_window_F_receipt_without_commit_resumes_on_restart(self, tmp_path):
        # Confirmed delivery, durable receipt written, but the ledger commit
        # could not complete before the crash.
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)

        class FailingCommitLedger:
            """check/peek healthy; the successful-send commit write fails."""

            def __init__(self, inner):
                self._inner = inner

            def check_only(self, **kw):
                return self._inner.check_only(**kw)

            def check_and_reserve(self, **kw):
                return self._inner.check_and_reserve(**kw)

            def commit_confirmed_send(self, **kw):
                from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
                    DEDUPE_REASON_LEDGER_WRITE_FAILED,
                    unavailable_outcome,
                )
                return unavailable_outcome(DEDUPE_REASON_LEDGER_WRITE_FAILED)

        healthy = SuccessTransport()
        out = _run_candidate(
            ledger=FailingCommitLedger(JsonlPingDedupeLedger(path=ledger_path)),
            private_transport=healthy, anchor=_anchor(), journal=journal)
        assert out["outcome"] == "ONE_SEND_COMMIT_PENDING"
        assert out["per_candidate"][0]["reason"] == "SENT_OK_COMMIT_PENDING"
        assert healthy.calls == 1
        assert _ledger_lines(ledger_path) == 0
        # Restart with a healthy ledger: the durable receipt finishes the
        # commit; Telegram is NOT called again.
        restarted = DeliveryAttemptJournal(path=outbox)
        assert len(restarted.pending_commits()) == 1
        report = reconcile_journal_on_restart(
            journal=restarted, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(datetime.now(timezone.utc)), ttl_seconds=TTL)
        assert report["commits_completed"] == 1
        assert healthy.calls == 1              # no second transport call
        assert _ledger_lines(ledger_path) == 1
        assert restarted.all_attempts()[0].committed is True
        # Replaying reconciliation is idempotent: still exactly one row.
        again = DeliveryAttemptJournal(path=outbox)
        reconcile_journal_on_restart(
            journal=again, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(datetime.now(timezone.utc)), ttl_seconds=TTL)
        assert _ledger_lines(ledger_path) == 1

    def test_window_E_committed_delivery_terminalizes_watch_on_restart(
            self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        ledger_path = tmp_path / "dedupe.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        healthy = SuccessTransport()
        out = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=_anchor(), journal=journal)
        assert out["outcome"] == "ONE_SEND_COMMITTED"
        # Crash BEFORE the watch update: restart restores a still-active watch.
        watch = Watchlist(max_size=4)
        entry = watch.seed({"token_mint": fst.MINT, "candidate_id": "w1"},
                           seeded_at_utc=_z(datetime.now(timezone.utc)))
        assert entry.is_active()
        restarted = DeliveryAttemptJournal(path=outbox)
        events = reconcile_watchlist_delivery(
            watchlist=watch, journal=restarted,
            now_utc=_z(datetime.now(timezone.utc)))
        assert events == [{"token_mint": fst.MINT,
                           "action": "TERMINALIZED_FROM_RECEIPT"}]
        assert entry.status == "SENT_OK_COMMITTED"
        assert not entry.is_active()
        # No second transport call happened during reconstruction ...
        assert healthy.calls == 1
        # ... and a later engine pass suppresses the duplicate.
        late = SuccessTransport()
        duplicate = _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=late, anchor=_anchor(),
            journal=restarted)
        assert late.calls == 0
        assert duplicate["outcome"] == "ZERO_SEND"
        assert _ledger_lines(ledger_path) == 1


# ---------------------------------------------------------------------------
# Fail-closed receipt/journal integrity (tests 17, 18)
# ---------------------------------------------------------------------------


class TestReceiptIntegrityFailsClosed:
    def test_wrong_binding_receipt_fails_closed(self, tmp_path):
        from PHX2.free_tier_producer.delivery_transaction import (
            EVENT_DELIVERY_RECEIPT,
            dedupe_key_to_dict,
        )
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        now = _z(datetime.now(timezone.utc))
        attempt_id, _ = journal.acquire_lease(
            key_map=dedupe_key_to_dict(KEY), token_mint=KEY.token_mint,
            candidate_id="c1", tier_token=KEY.tier_token,
            snapshot_body_sha256="a" * 64, now_utc=now)
        journal.record_transport_started(attempt_id, now_utc=now)
        # Forge a validly-digested receipt bound to a DIFFERENT mint/tier.
        journal._append({
            "event": EVENT_DELIVERY_RECEIPT,
            "attempt_id": attempt_id,
            "token_mint": "WrongMint11111111111111111111111111111pump",
            "candidate_id": "c1",
            "tier_token": "Tier 3",
            "dedupe_key": dedupe_key_to_dict(KEY),
            "snapshot_body_sha256": "a" * 64,
            "message_id": 1,
            "transport_status": "SENT_OK",
            "recorded_at_utc": now,
        })
        ledger = InMemoryPingDedupeLedger()
        report = reconcile_journal_on_restart(
            journal=DeliveryAttemptJournal(path=outbox), ledger=ledger,
            now_utc=now, ttl_seconds=TTL)
        assert report["commits_failed"] == 1
        assert report["commits_completed"] == 0
        assert report["details"][0]["reason"] == "RECEIPT_MINT_MISMATCH"
        # No successful-send row was appended from the mismatched receipt.
        assert ledger.check_only(key=KEY, now_utc=now, ttl_seconds=TTL).allowed

    def test_tampered_outbox_digest_fails_closed(self, tmp_path):
        outbox = tmp_path / "outbox.jsonl"
        journal = DeliveryAttemptJournal(path=outbox)
        healthy = SuccessTransport()
        ledger_path = tmp_path / "dedupe.jsonl"
        _run_candidate(
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            private_transport=healthy, anchor=_anchor(), journal=journal)
        # Tamper one byte of the mint inside a journal record WITHOUT
        # recomputing its self-digest.
        lines = outbox.read_text(encoding="utf-8").splitlines()
        tampered = [ln.replace(fst.MINT, "X" + fst.MINT[1:], 1)
                    if fst.MINT in ln else ln for ln in lines]
        assert tampered != lines
        outbox.write_text("\n".join(tampered) + "\n", encoding="utf-8")
        reloaded = DeliveryAttemptJournal(path=outbox)
        assert reloaded.available is False
        assert reloaded.unavailable_reason == "JOURNAL_CORRUPT"
        # Mutations fail closed; reconciliation refuses to commit from it.
        attempt_id, refusal = reloaded.acquire_lease(
            key_map={"token_mint": "x"}, token_mint="x", candidate_id="x",
            tier_token="Tier 1", snapshot_body_sha256=None,
            now_utc=_z(datetime.now(timezone.utc)))
        assert attempt_id is None and refusal == "JOURNAL_UNAVAILABLE"
        before = _ledger_lines(ledger_path)
        report = reconcile_journal_on_restart(
            journal=reloaded, ledger=JsonlPingDedupeLedger(path=ledger_path),
            now_utc=_z(datetime.now(timezone.utc)), ttl_seconds=TTL)
        assert report["journal_available"] is False
        assert _ledger_lines(ledger_path) == before


# ---------------------------------------------------------------------------
# Peek-only compose view + real-ledger safety (test 20)
# ---------------------------------------------------------------------------


class TestLedgerSurfaces:
    def test_peek_view_never_mutates(self, tmp_path):
        ledger_path = tmp_path / "dedupe.jsonl"
        ledger = JsonlPingDedupeLedger(path=ledger_path)
        view = PeekOnlyPingDedupeLedgerView(ledger)
        now = _z(datetime.now(timezone.utc))
        outcome = view.check_and_reserve(key=KEY, now_utc=now, ttl_seconds=TTL)
        assert outcome.allowed
        assert _ledger_lines(ledger_path) == 0
        # The real commit still writes exactly once and then suppresses.
        assert ledger.commit_confirmed_send(
            key=KEY, now_utc=now, ttl_seconds=TTL).allowed
        assert _ledger_lines(ledger_path) == 1
        assert not view.check_and_reserve(
            key=KEY, now_utc=now, ttl_seconds=TTL).allowed
        second = ledger.commit_confirmed_send(
            key=KEY, now_utc=now, ttl_seconds=TTL)
        assert second.verdict == "DEDUPE_SUPPRESSED_DUPLICATE"
        assert _ledger_lines(ledger_path) == 1

    def test_runner_failure_continues_unknown_stops_sustained_breaks(self):
        from PHX2.free_tier_producer.compat.production_live_runner import (
            ProductionBounds,
            STOP_DELIVERY_UNKNOWN,
            STOP_TRANSPORT_ERROR,
            run_production_live_watch,
        )
        from PHX2.free_tier_producer.compat import (
            production_live_axiom_gate as axiomgate,
        )

        def _run(outcome, reason, *, max_ticks, transport_failures_bound=5):
            watch = Watchlist(max_size=8)
            watch.seed({"token_mint": fst.MINT, "candidate_id": "r1"},
                       seeded_at_utc="2026-07-18T00:00:00Z")
            mono = {"t": 0.0}

            def stub_engine(cands, **kw):
                rec = {"token_mint": fst.MINT, "reason": reason,
                       "delivery_state": reason,
                       "delivery_failure_reason": "FAKE_TRANSIENT_FAILURE",
                       "delivery_retry_count": 1,
                       "market_context": {}}
                return {
                    "per_candidate": [rec],
                    "sent_attempt": {
                        "send_result": SimpleNamespace(
                            dispatch_forwarded=True, transport_attempted=True,
                            transport_ok=False,
                            transport_status="FAKE_TRANSIENT_FAILURE",
                            cap_consumed=True, decision="FORWARDED",
                            reason="FORWARDED"),
                        "delivery": {"delivery_state": reason},
                    },
                    "eligible_candidate": {"token_mint": fst.MINT,
                                           "candidate_id": "r1"},
                    "outcome": outcome,
                }

            return run_production_live_watch(
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
                now_iso_fn=lambda: _z(datetime.now(timezone.utc)),
                now_seconds=make_constant_clock(fst.Decimal(0)),
                sleep_fn=lambda s: mono.__setitem__("t", mono["t"] + s),
                monotonic_fn=lambda: mono["t"],
                bounds=ProductionBounds(
                    recheck_interval_seconds=1.0,
                    max_candidate_age_seconds=99_999_999,
                    max_rechecks_per_candidate=999999,
                    max_runtime_seconds=999999.0,
                    min_seconds_between_sends=0.0,
                    max_total_ticks=max_ticks,
                    max_consecutive_transport_failures=transport_failures_bound,
                ),
                run_cap1_candidates_fn=stub_engine,
                ledger_line_count_fn=lambda: 0,
            ), watch

        # Explicit retryable failure: the run CONTINUES (stops on tick budget),
        # nothing counts as a send, the ledger stays consistent at delta 0, and
        # the watch entry stays active.
        result, watch = _run("ONE_SEND_FAILED_RETRYABLE",
                             "DELIVERY_FAILED_RETRYABLE", max_ticks=3)
        assert result["stop_reason"] == "TICK_BUDGET"
        assert result["sends"] == 0
        assert result["ledger_consistent"] is True
        assert result["reserve_count"] == 0
        assert all(rec.get("ledger_reserved") is False
                   for rec in result["send_records"])
        assert all(rec.get("sent_ok") is False
                   for rec in result["send_records"])
        entry = watch.get(fst.MINT)
        assert entry.is_active()
        assert entry.delivery_state == "DELIVERY_FAILED_RETRYABLE"

        # Sustained explicit failure trips the bounded transport breaker.
        result, _watch = _run("ONE_SEND_FAILED_RETRYABLE",
                              "DELIVERY_FAILED_RETRYABLE", max_ticks=99,
                              transport_failures_bound=2)
        assert result["stop_reason"] == STOP_TRANSPORT_ERROR
        assert result["sends"] == 0

        # Ambiguous outcome stops immediately for operator reconciliation and
        # the watch shows the observable DELIVERY_UNKNOWN state.
        result, watch = _run("ONE_SEND_UNKNOWN", "DELIVERY_UNKNOWN",
                             max_ticks=99)
        assert result["stop_reason"] == STOP_DELIVERY_UNKNOWN
        assert result["sends"] == 0
        entry = watch.get(fst.MINT)
        assert entry.status == "DELIVERY_UNKNOWN"
        assert not entry.is_active()

    def test_real_production_ledgers_unchanged_by_offline_suite(self, tmp_path):
        active = ps.DEFAULT_ACTIVE_LEDGER
        frozen = ps.DEFAULT_FROZEN_LEDGER
        if not (active.is_file() and frozen.is_file()):
            pytest.skip("real operator ledgers not present on this machine")
        before_active = hashlib.sha256(active.read_bytes()).hexdigest()
        before_frozen = hashlib.sha256(frozen.read_bytes()).hexdigest()
        anchor = _anchor()
        _run_candidate(
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            private_transport=FailedTransport(), anchor=anchor,
            journal=DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl"))
        _run_candidate(
            ledger=JsonlPingDedupeLedger(path=tmp_path / "dedupe.jsonl"),
            private_transport=SuccessTransport(), anchor=anchor,
            journal=DeliveryAttemptJournal(path=tmp_path / "outbox.jsonl"))
        assert hashlib.sha256(
            active.read_bytes()).hexdigest() == before_active
        assert hashlib.sha256(
            frozen.read_bytes()).hexdigest() == before_frozen
