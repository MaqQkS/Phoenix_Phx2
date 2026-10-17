"""PHX2 gRPC recovery-boundary integrity -- a provider that IGNORES ``from_slot``.

The commit-``7b43f62`` reconnect suite drives a faithful ``FakeYellowstone``
that always honours ``from_slot`` and always replays contiguously from the
requested boundary.  Under that provider the N/N+4 gap genuinely closes.

This module drives the case that suite cannot express: a provider that accepts
the subscription, **ignores the requested resume position**, and begins
delivering beyond the boundary.  Against such a provider the pre-fix cursor
advanced its authoritative resume position across a range it had never
observed, a second reconnect re-certified the moved position, and the skipped
slots became permanently unrecoverable -- across process restart.

Every test is offline and deterministic: no socket, no provider, no credential,
no real ledger.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import grpc
import pytest

from PHX2.free_tier_producer import paid_grpc_source as source_module
from PHX2.free_tier_producer import paid_provider as provider_module
from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer.paid_grpc_source import (
    PaidCreatePoolYellowstoneSource,
    build_transaction_skip_identity,
)
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
)
from PHX2.free_tier_producer.stream_cursor import GrpcStreamCursorStore

from PHX2.tests.test_grpc_reconnect_gap_recovery import (
    _Disconnect,
    _identity_digest,
    _runtime,
    _store,
    _update,
    install_fake_provider,
)

# Two unrelated slot bases: the defect must be reproduced independently of any
# particular numeric neighbourhood.
BASE_A = 1_000_000
BASE_B = 340_000_000


# ---------------------------------------------------------------------------
# a provider that ignores the requested resume position
# ---------------------------------------------------------------------------

class IgnoresFromSlotYellowstone:
    """Accepts ``from_slot``, records it, then serves a scripted slot list.

    This is the honest model of a provider whose replay is unavailable,
    truncated, or simply not implemented: the subscription succeeds, data
    flows, and nothing in the transport tells the client that the requested
    range was skipped.
    """

    def __init__(self, scripts):
        # scripts: list per subscribe call of [(slot, update), ...]
        self.scripts = [list(script) for script in scripts]
        self.requests = []
        self.delivered = []
        self.subscribe_calls = 0
        self.concurrent_streams = 0
        self.max_concurrent_streams = 0
        self._lock = threading.Lock()

    def subscribe(self, request):
        from_slot = None
        if request is not None and hasattr(request, "HasField"):
            try:
                if request.HasField("from_slot"):
                    from_slot = int(request.from_slot)
            except (TypeError, ValueError):
                from_slot = None
        with self._lock:
            self.subscribe_calls += 1
            call = self.subscribe_calls
            self.requests.append(from_slot)
        script = self.scripts[call - 1] if call <= len(self.scripts) else []
        return _ScriptStream(self, script)


class _ScriptStream:
    def __init__(self, server, script):
        self._server = server
        self._items = list(script)
        self._cancelled = False
        with server._lock:
            server.concurrent_streams += 1
            server.max_concurrent_streams = max(
                server.max_concurrent_streams, server.concurrent_streams)
        self._open = True

    def _close(self):
        if self._open:
            self._open = False
            with self._server._lock:
                self._server.concurrent_streams -= 1

    def __iter__(self):
        return self

    def __next__(self):
        if self._cancelled or not self._items:
            self._close()
            raise StopIteration
        slot, update = self._items.pop(0)
        self._server.delivered.append(slot)
        return update

    def cancel(self):
        self._cancelled = True
        self._close()


def _drive_source(server, monkeypatch, *, cursor, from_slot, generation=1,
                  max_events=8):
    """Run exactly one subscription attempt against the scripted provider."""

    install_fake_provider(monkeypatch, server)
    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(),
        max_messages_to_scan=None,
        from_slot=from_slot,
        cursor=cursor,
        stream_generation=generation,
    )
    list(source.iter_events(max_events=max_events))
    return source


def _commit(cursor, slot, seed=0):
    """Commit one deterministically-classified event at ``slot``."""

    identity = build_transaction_skip_identity(slot, f"sig{seed}", None)
    cursor.commit_event(slot=slot, identity=identity, signature=f"sig{seed}",
                        replayed=False)
    return identity


# ===========================================================================
# 1-2. the boundary must survive an unproven overlap and a second reconnect
# ===========================================================================

@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_unproven_overlap_does_not_advance_safe_resume_boundary(
        monkeypatch, tmp_path, base):
    """N committed, provider ignores from_slot=N and returns only N+4.

    The high-water position may move.  The authoritative resume boundary must
    not: nothing has proven that N+1..N+3 were ever covered.
    """

    cursor = _store(tmp_path)
    _commit(cursor, base)
    assert cursor.resume_from_slot() == base

    cursor.mark_disconnect()
    assert cursor.state.recovery_from_slot == base
    assert cursor.state.recovery_required is True

    server = IgnoresFromSlotYellowstone([[(base + 4, _update(base + 4, 4))]])
    source = _drive_source(server, monkeypatch, cursor=cursor,
                           from_slot=cursor.resume_from_slot())

    assert server.requests == [base]
    assert source.overlap_observed is False
    assert source.highest_slot_observed == base + 4

    # The decisive assertion: the safe resume position has NOT moved.
    assert cursor.safe_resume_slot() == base
    assert cursor.resume_from_slot() == base
    assert cursor.state.recovery_required is True
    assert cursor.state.recovery_from_slot == base


@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_second_reconnect_cannot_recertify_moved_boundary(
        monkeypatch, tmp_path, base):
    """A second disconnect must not re-anchor recovery on the moved position."""

    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()

    server = IgnoresFromSlotYellowstone([
        [(base + 4, _update(base + 4, 4))],
        [(base + 5, _update(base + 5, 5))],
    ])
    _drive_source(server, monkeypatch, cursor=cursor,
                  from_slot=cursor.resume_from_slot())

    # Second disconnect inside the SAME unresolved episode.
    cursor.mark_disconnect()
    assert cursor.state.recovery_from_slot == base, (
        "the earliest unresolved boundary must be preserved")

    second_request = cursor.resume_from_slot()
    assert second_request == base, "the second reconnect must re-request N"

    _drive_source(server, monkeypatch, cursor=cursor,
                  from_slot=second_request, generation=2)
    assert server.requests == [base, base]
    assert cursor.state.recovery_required is True
    assert cursor.safe_resume_slot() == base


@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_missing_range_remains_recoverable_after_restart(
        monkeypatch, tmp_path, base):
    """Reconstructed from disk, the store still owes the original range."""

    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()
    server = IgnoresFromSlotYellowstone([[(base + 4, _update(base + 4, 4))]])
    _drive_source(server, monkeypatch, cursor=cursor,
                  from_slot=cursor.resume_from_slot())

    # Full process restart: a brand-new store reading only the persisted file.
    reloaded = GrpcStreamCursorStore(
        primary_path=tmp_path / sc.CURSOR_PRIMARY_BASENAME,
        subscription_identity_digest=_identity_digest(),
    )
    result = reloaded.load()
    assert result.checkpoint_quarantined is False

    assert reloaded.resume_from_slot() == base
    assert reloaded.safe_resume_slot() == base
    assert reloaded.state.recovery_required is True
    assert reloaded.state.recovery_from_slot == base
    for missing in (base + 1, base + 2, base + 3):
        assert reloaded.slot_is_inside_recovery_responsibility(missing) is True


@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_recovery_closes_only_after_original_boundary_overlap(
        monkeypatch, tmp_path, base):
    """A correct replay from N -- and only that -- closes the episode."""

    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()

    unsafe = IgnoresFromSlotYellowstone([[(base + 4, _update(base + 4, 4))]])
    _drive_source(unsafe, monkeypatch, cursor=cursor,
                  from_slot=cursor.resume_from_slot())
    assert cursor.state.recovery_required is True

    # Now a provider that honours the position: full replay from N.
    good = IgnoresFromSlotYellowstone([[
        (base + offset, _update(base + offset, offset)) for offset in range(5)
    ]])
    requested = cursor.resume_from_slot()
    assert requested == base
    source = _drive_source(good, monkeypatch, cursor=cursor,
                           from_slot=requested, generation=3)

    assert source.overlap_observed is True
    assert source.overlap_proof_slot == base
    # N was already durable: suppressed, not reprocessed.
    assert source.replay_duplicates_suppressed == 1
    # N+1..N+4 processed exactly once each.
    assert source.cursor_commits == 4

    closed = cursor.mark_gap_closed(
        requested_from_slot=requested,
        proven_boundary_slot=source.overlap_proof_slot,
        recovery_generation=source.recovery_generation,
    )
    assert closed is True
    assert cursor.state.recovery_required is False
    assert cursor.safe_resume_slot() == base + 4
    assert cursor.state.last_proven_replay_boundary_slot == base


def test_mark_gap_closed_refuses_a_boundary_it_did_not_prove(tmp_path):
    """Closing must be bound to the episode's own boundary and generation."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()
    generation = cursor.state.recovery_generation

    # Proof at a LATER slot than the episode boundary: self-certifying, refused.
    assert cursor.mark_gap_closed(
        requested_from_slot=BASE_A + 4, proven_boundary_slot=BASE_A + 4,
        recovery_generation=generation) is False
    assert cursor.state.recovery_required is True

    # Correct boundary but a stale generation: superseded, refused.
    assert cursor.mark_gap_closed(
        requested_from_slot=BASE_A, proven_boundary_slot=BASE_A,
        recovery_generation=generation - 1) is False
    assert cursor.state.recovery_required is True

    # Correct boundary and generation: accepted.
    assert cursor.mark_gap_closed(
        requested_from_slot=BASE_A, proven_boundary_slot=BASE_A,
        recovery_generation=generation) is True
    assert cursor.state.recovery_required is False


def test_mark_disconnect_preserves_earliest_unresolved_boundary(tmp_path):
    """Repeated disconnects in one episode never replace the original boundary."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()
    first_generation = cursor.state.recovery_generation
    assert cursor.state.recovery_from_slot == BASE_A

    for offset in (2, 4, 9):
        _commit(cursor, BASE_A + offset, seed=offset)
        cursor.mark_disconnect()
        assert cursor.state.recovery_from_slot == BASE_A
        assert cursor.state.recovery_generation == first_generation

    assert cursor.state.last_durable_slot == BASE_A + 9
    assert cursor.safe_resume_slot() == BASE_A


def test_resume_prefers_recovery_boundary_over_high_water(tmp_path):
    """While recovery is unresolved the boundary wins over the high-water mark."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()
    _commit(cursor, BASE_A + 7, seed=7)

    assert cursor.state.last_durable_slot == BASE_A + 7
    assert cursor.resume_from_slot() == BASE_A
    assert cursor.safe_resume_slot() == BASE_A

    cursor.mark_gap_closed(
        requested_from_slot=BASE_A, proven_boundary_slot=BASE_A,
        recovery_generation=cursor.state.recovery_generation)
    # Only once the episode is proven closed may the high-water mark be used.
    assert cursor.resume_from_slot() == BASE_A + 7


@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_provider_ignoring_from_slot_never_loses_slots(
        monkeypatch, tmp_path, base):
    """End-to-end: no slot is ever placed outside recovery responsibility."""

    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()

    requests = []
    for generation in (1, 2, 3):
        requested = cursor.resume_from_slot()
        requests.append(requested)
        server = IgnoresFromSlotYellowstone([[
            (base + 4 + generation, _update(base + 4 + generation, generation))]])
        _drive_source(server, monkeypatch, cursor=cursor,
                      from_slot=requested, generation=generation)
        cursor.mark_disconnect()

    assert requests == [base, base, base], (
        "every reconnect must keep requesting the unproven boundary")
    for missing in (base + 1, base + 2, base + 3):
        assert cursor.slot_is_inside_recovery_responsibility(missing) is True
    assert cursor.state.recovery_required is True


# ===========================================================================
# 3. same-slot siblings and persistence ordering
# ===========================================================================

def test_same_slot_unprocessed_sibling_survives_restart(tmp_path):
    """One boundary-slot identity was durable; its sibling was not."""

    cursor = _store(tmp_path)
    handled = build_transaction_skip_identity(BASE_A, "sig_handled", 0)
    sibling = build_transaction_skip_identity(BASE_A, "sig_sibling", 1)
    cursor.commit_event(slot=BASE_A, identity=handled, signature="sig_handled")

    reloaded = GrpcStreamCursorStore(
        primary_path=tmp_path / sc.CURSOR_PRIMARY_BASENAME,
        subscription_identity_digest=_identity_digest(),
    )
    reloaded.load()

    assert reloaded.is_duplicate(handled) is True
    assert reloaded.is_duplicate(sibling) is False
    assert reloaded.resume_from_slot() == BASE_A

    reloaded.commit_event(slot=BASE_A, identity=sibling, signature="sig_sibling")
    assert reloaded.is_duplicate(sibling) is True
    assert reloaded.state.last_durable_slot == BASE_A


def test_cursor_write_failure_does_not_advance_in_memory_resume_position(
        monkeypatch, tmp_path):
    """A failed persist leaves BOTH durable and in-memory state at the old value."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    assert cursor.resume_from_slot() == BASE_A

    def _boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(sc._cpe, "write_checkpoint_generation", _boom)

    failing = build_transaction_skip_identity(BASE_A + 3, "sig_fail", None)
    with pytest.raises(sc.StreamCursorWriteError):
        cursor.commit_event(slot=BASE_A + 3, identity=failing,
                            signature="sig_fail")

    assert cursor.cursor_write_failed_total == 1
    # In-memory authoritative state must not be ahead of the last valid durable
    # generation.
    assert cursor.state.last_durable_slot == BASE_A
    assert cursor.resume_from_slot() == BASE_A
    assert cursor.safe_resume_slot() == BASE_A
    assert cursor.is_duplicate(failing) is False

    monkeypatch.undo()
    reloaded = GrpcStreamCursorStore(
        primary_path=tmp_path / sc.CURSOR_PRIMARY_BASENAME,
        subscription_identity_digest=_identity_digest(),
    )
    reloaded.load()
    assert reloaded.resume_from_slot() == BASE_A


# ===========================================================================
# 4. replay retention: terminal, and never a reconnect storm
# ===========================================================================

def test_replay_retention_exceeded_is_terminal_and_non_spinning(tmp_path):
    """A dead resume position stops safely rather than spinning on it."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()

    cursor.mark_replay_retention_exceeded(first_available=BASE_A + 500)

    assert cursor.state.recovery_terminal is True
    assert cursor.state.recovery_status == sc.RECOVERY_FAILED
    assert cursor.state.recovery_reason == sc.REASON_REPLAY_POSITION_TOO_OLD
    assert cursor.state.replay_first_available_slot == BASE_A + 500
    # No silent start at the live head, and no cursor deletion.
    assert cursor.resume_from_slot() is None
    assert cursor.state.last_durable_slot == BASE_A
    assert (tmp_path / sc.CURSOR_PRIMARY_BASENAME).exists()

    authorized, reason = sc.source_health_authorizes_send(cursor.snapshot())
    assert authorized is False
    assert reason == sc.REASON_REPLAY_POSITION_TOO_OLD

    reloaded = GrpcStreamCursorStore(
        primary_path=tmp_path / sc.CURSOR_PRIMARY_BASENAME,
        subscription_identity_digest=_identity_digest(),
    )
    reloaded.load()
    assert reloaded.state.recovery_terminal is True
    assert reloaded.resume_from_slot() is None


def test_retention_precheck_marks_terminal_before_a_reconnect_storm(tmp_path):
    """``first_available`` newer than the boundary is a terminal pre-check."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()

    verdict = sc.evaluate_replay_retention(
        safe_resume_slot=cursor.safe_resume_slot(),
        first_available_slot=BASE_A + 1)
    assert verdict.retention_exceeded is True
    assert verdict.reason == sc.REASON_REPLAY_POSITION_TOO_OLD

    ok = sc.evaluate_replay_retention(
        safe_resume_slot=cursor.safe_resume_slot(),
        first_available_slot=BASE_A)
    assert ok.retention_exceeded is False

    unknown = sc.evaluate_replay_retention(
        safe_resume_slot=cursor.safe_resume_slot(), first_available_slot=None)
    assert unknown.retention_exceeded is False
    assert unknown.coverage_proven is False
    assert unknown.reason == sc.REASON_REPLAY_UNAVAILABLE


def test_terminal_recovery_stops_the_owner_instead_of_reconnecting():
    """A terminal source state must not drive an unbounded reconnect loop."""

    attempts = []

    class _TerminalSource:
        replay_requested = True
        replay_position_rejected = True
        first_slot_observed = None
        last_refusal_reason = "STREAM_ERROR:OUT_OF_RANGE"

        def __init__(self):
            attempts.append(1)

        def iter_events(self, *, max_events):
            return iter(())

        def close(self):
            pass

    class _Cursor:
        def __init__(self):
            self.terminal = False
            self.state = SimpleNamespace(recovery_generation=1)

        def resume_from_slot(self):
            return None if self.terminal else BASE_A

        def safe_resume_slot(self):
            return BASE_A

        def mark_recovery_started(self, **_kw):
            pass

        def mark_recovery_failed(self, **_kw):
            pass

        def mark_replay_retention_exceeded(self, **_kw):
            self.terminal = True

        def mark_gap_closed(self, **_kw):
            return False

        def mark_disconnect(self, **_kw):
            pass

        def is_terminal(self):
            return self.terminal

        def snapshot(self):
            return {}

    cursor = _Cursor()
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda **_kw: _TerminalSource(),
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0.0,
        cursor_store=cursor,
    )
    owner.start()
    owner._thread.join(timeout=5.0)

    assert cursor.terminal is True
    assert len(attempts) == 1, "a dead replay position must not be retried"
    assert owner.snapshot()["terminal_recovery"] is True


def test_replay_info_precheck_refuses_before_subscribing(monkeypatch, tmp_path):
    """The retention floor is queried BEFORE the subscription is opened."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()

    server = IgnoresFromSlotYellowstone([[(BASE_A, _update(BASE_A, 0))]])
    install_fake_provider(monkeypatch, server)

    class _ReplayInfoStub:
        def __init__(self, _channel):
            pass

        def SubscribeReplayInfo(self, _request):
            return SimpleNamespace(
                first_available=BASE_A + 900,
                HasField=lambda name: name == "first_available")

        def Subscribe(self, request_iterator, **_kw):
            return server.subscribe(next(iter(request_iterator)))

    monkeypatch.setattr(source_module.geyser_pb2_grpc, "GeyserStub",
                        _ReplayInfoStub)

    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(), max_messages_to_scan=None,
        from_slot=cursor.resume_from_slot(), cursor=cursor,
        recovery_generation=cursor.state.recovery_generation)
    assert list(source.iter_events(max_events=8)) == []

    assert server.subscribe_calls == 0, "no subscription may be opened"
    assert source.replay_position_rejected is True
    assert source.replay_first_available == BASE_A + 900
    assert source.replay_retention_reason == sc.REASON_REPLAY_POSITION_TOO_OLD
    # The cursor is untouched by the source itself: the owner marks terminal.
    assert cursor.state.last_durable_slot == BASE_A


def test_unavailable_replay_info_does_not_claim_coverage(monkeypatch, tmp_path):
    """A missing or malformed replay-info answer is never proof of coverage."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()

    server = IgnoresFromSlotYellowstone([[(BASE_A, _update(BASE_A, 0))]])
    install_fake_provider(monkeypatch, server)

    class _NoReplayInfoStub:
        def __init__(self, _channel):
            pass

        def SubscribeReplayInfo(self, _request):
            raise grpc.RpcError("unimplemented")

        def Subscribe(self, request_iterator, **_kw):
            return server.subscribe(next(iter(request_iterator)))

    monkeypatch.setattr(source_module.geyser_pb2_grpc, "GeyserStub",
                        _NoReplayInfoStub)

    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(), max_messages_to_scan=None,
        from_slot=cursor.resume_from_slot(), cursor=cursor,
        recovery_generation=cursor.state.recovery_generation)
    list(source.iter_events(max_events=8))

    assert source.replay_first_available is None
    assert source.replay_retention_reason == sc.REASON_REPLAY_UNAVAILABLE
    assert source.replay_position_rejected is False    # unknown != too old
    assert server.subscribe_calls == 1                 # it still tries


def test_retention_refusal_displays_replay_unavailable_not_a_blip():
    """The terminal reason must not hide behind DISCONNECTED_RETRYING."""

    display = provider_module._display_status(
        status=provider_module.STREAM_STATUS_STOPPED,
        transport_connected=False,      # a refusal never connects
        live_healthy=False,
        gap_unresolved=True,
        cursor_quarantined=False,
        recovery_reason=sc.REASON_REPLAY_POSITION_TOO_OLD,
        stopped=True,                   # and the owner stops
    )
    assert display == sc.DISPLAY_REPLAY_UNAVAILABLE


# ===========================================================================
# 5. source health gates outbound authorization
# ===========================================================================

@pytest.mark.parametrize("state", [
    sc.STATE_STARTING,
    sc.STATE_CURSOR_LOADING,
    sc.STATE_REPLAY_REQUIRED,
    sc.STATE_REPLAYING,
    sc.STATE_CATCHING_UP,
    sc.STATE_GAP_UNRESOLVED,
    sc.STATE_CURSOR_QUARANTINED,
    sc.STATE_REPLAY_RETENTION_EXCEEDED,
    sc.STATE_DISCONNECTED,
    sc.STATE_RECONNECTING,
    sc.STATE_SUBSCRIPTION_IDENTITY_MISMATCH,
])
def test_every_unhealthy_source_state_blocks_send_authorization(state):
    authorized, reason = sc.source_health_authorizes_send(
        {"stream_state": state, "live_healthy": False})
    assert authorized is False
    assert reason != sc.REASON_NONE


def test_only_proven_live_healthy_authorizes_send():
    authorized, reason = sc.source_health_authorizes_send(
        {"stream_state": sc.STATE_LIVE_HEALTHY, "live_healthy": True})
    assert authorized is True
    assert reason == sc.REASON_NONE

    # live_healthy alone, without the proven state, is not enough.
    blocked, _ = sc.source_health_authorizes_send(
        {"stream_state": sc.STATE_GAP_UNRESOLVED, "live_healthy": True})
    assert blocked is False


def test_gap_unresolved_blocks_compose_and_delivery(tmp_path):
    """Discovery may rebuild state while degraded; dispatch may not proceed."""

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()

    snapshot = {
        "stream_state": sc.STATE_GAP_UNRESOLVED,
        "live_healthy": False,
        "gap_unresolved": True,
    }
    authorized, reason = sc.source_health_authorizes_send(snapshot)
    assert authorized is False
    assert reason == sc.REASON_GAP_UNRECOVERABLE

    # Ingestion-side work is explicitly NOT blocked by the same predicate.
    assert sc.source_health_permits_ingestion(snapshot) is True


# ===========================================================================
# 6. replayed events keep their chain event time
# ===========================================================================

def test_replay_preserves_chain_event_time():
    """A provider-stamped event time survives decoding at a much later moment."""

    from PHX2.proto.stage28_11._generated import geyser_pb2

    update = geyser_pb2.SubscribeUpdate()
    update.transaction.slot = BASE_A
    update.created_at.seconds = 1_750_000_000
    update.created_at.nanos = 0

    event_time, source = source_module.extract_provider_event_time(update)
    assert source == source_module.EVENT_TIME_SOURCE_PROVIDER_CREATED_AT
    assert event_time == "2025-06-15T15:06:40Z"     # 1_750_000_000 epoch UTC

    # Decoding the same update again must yield the same event time.
    again, _ = source_module.extract_provider_event_time(update)
    assert again == event_time


def test_missing_chain_time_fails_age_sensitive_logic_closed():
    """No provider time on a REPLAYED event -> unknown, never wall-clock."""

    from PHX2.proto.stage28_11._generated import geyser_pb2

    update = geyser_pb2.SubscribeUpdate()
    update.transaction.slot = BASE_A
    assert update.HasField("created_at") is False

    event_time, source = source_module.extract_provider_event_time(update)
    assert event_time is None
    assert source == source_module.EVENT_TIME_SOURCE_UNKNOWN

    replayed = provider_module.resolve_migration_event_time(
        provider_event_time_utc=None,
        provider_event_time_source=source_module.EVENT_TIME_SOURCE_UNKNOWN,
        local_observed_at_utc="2026-07-20T03:45:00Z",
        replayed=True,
    )
    assert replayed.authoritative is False
    assert replayed.source == provider_module.MIGRATION_TIME_SOURCE_UNKNOWN
    assert replayed.migration_time_utc != "2026-07-20T03:45:00Z"
    assert replayed.migration_time_utc is None

    # A LIVE tip delivery may use local receipt time: it is within milliseconds
    # of the event and is not a fabricated age.
    live = provider_module.resolve_migration_event_time(
        provider_event_time_utc=None,
        provider_event_time_source=source_module.EVENT_TIME_SOURCE_UNKNOWN,
        local_observed_at_utc="2026-07-20T03:45:00Z",
        replayed=False,
    )
    assert live.authoritative is True
    assert live.source == provider_module.MIGRATION_TIME_SOURCE_LOCAL_RECEIPT_LIVE
    assert live.migration_time_utc == "2026-07-20T03:45:00Z"


def test_candidate_carries_separate_chain_and_receipt_times():
    """``migration_time_utc`` is chain time; receipt time is a distinct field."""

    event = SimpleNamespace(
        base_mint="A" * 40 + "pump", mint="A" * 40 + "pump",
        pool_account="P" * 43, pool_program_id="G" * 43, quote_mint="Q" * 43,
        event_id="evt-1", provider_event_id="prov-1",
        observed_at_utc="2026-07-20T03:45:00Z",
        provider_event_time_utc="2026-06-15T14:26:40Z",
        provider_event_time_source=source_module.EVENT_TIME_SOURCE_PROVIDER_CREATED_AT,
        raw_event_hash="hash-1",
    )
    candidate = provider_module.event_to_candidate(event, replayed=True)
    assert candidate is not None
    assert candidate["migration_time_utc"] == "2026-06-15T14:26:40Z"
    assert candidate["local_observed_at_utc"] == "2026-07-20T03:45:00Z"
    assert candidate["migration_time_source"] == (
        provider_module.MIGRATION_TIME_SOURCE_PROVIDER_EVENT_TIME)
    assert candidate["migration_time_authoritative"] is True


def test_replayed_candidate_without_chain_time_is_not_authoritative():
    event = SimpleNamespace(
        base_mint="B" * 40 + "pump", mint="B" * 40 + "pump",
        pool_account="P" * 43, pool_program_id="G" * 43, quote_mint="Q" * 43,
        event_id="evt-2", provider_event_id="prov-2",
        observed_at_utc="2026-07-20T03:45:00Z",
        provider_event_time_utc=None,
        provider_event_time_source=source_module.EVENT_TIME_SOURCE_UNKNOWN,
        raw_event_hash="hash-2",
    )
    candidate = provider_module.event_to_candidate(event, replayed=True)
    assert candidate is not None
    assert candidate["migration_time_authoritative"] is False
    assert candidate["migration_time_source"] == (
        provider_module.MIGRATION_TIME_SOURCE_UNKNOWN)
    assert candidate["local_observed_at_utc"] == "2026-07-20T03:45:00Z"


# ===========================================================================
# 7. the production factory contract cannot silently degrade
# ===========================================================================

def test_production_source_factory_cannot_fallback_to_zero_arg():
    """A legacy zero-argument factory must fail closed in production mode."""

    def _legacy_factory():
        return SimpleNamespace()

    with pytest.raises(provider_module.SourceFactoryContractError) as excinfo:
        SingleGrpcPumpSwapDiscovery(
            source_factory=_legacy_factory,
            dedupe=ProviderCandidateDedupe(),
            cursor_store=SimpleNamespace(),
            require_cursor_aware_factory=True,
        )
    assert "FACTORY" in str(excinfo.value)


def test_typeerror_from_inside_the_factory_is_not_a_legacy_signature():
    """An exception raised INSIDE a cursor-aware factory must not degrade it."""

    calls = []

    def _cursor_aware(*, from_slot=None, cursor=None,
                      downstream_durable_fn=None, stream_generation=0):
        calls.append(from_slot)
        raise TypeError("an internal bug, not a signature mismatch")

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=_cursor_aware,
        dedupe=ProviderCandidateDedupe(),
        cursor_store=SimpleNamespace(),
        require_cursor_aware_factory=True,
    )
    with pytest.raises(TypeError):
        owner._build_source(BASE_A, 1)
    assert calls == [BASE_A], "the factory must be called exactly once"


def test_cursor_aware_factory_is_accepted_and_receives_the_resume_position():
    seen = {}

    def _cursor_aware(*, from_slot=None, cursor=None,
                      downstream_durable_fn=None, stream_generation=0):
        seen.update(from_slot=from_slot, stream_generation=stream_generation)
        return SimpleNamespace()

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=_cursor_aware,
        dedupe=ProviderCandidateDedupe(),
        cursor_store=SimpleNamespace(),
        require_cursor_aware_factory=True,
    )
    owner._build_source(BASE_B, 4)
    assert seen == {"from_slot": BASE_B, "stream_generation": 4}


def test_explicit_test_only_adapter_keeps_legacy_factories_usable():
    """Compatibility exists, but only behind an unmistakable test-only name."""

    def _legacy_factory():
        return SimpleNamespace(marker="legacy")

    adapted = provider_module.adapt_zero_argument_factory_TEST_ONLY(
        _legacy_factory)
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=adapted,
        dedupe=ProviderCandidateDedupe(),
        cursor_store=SimpleNamespace(),
        require_cursor_aware_factory=True,
    )
    assert owner._build_source(BASE_A, 1).marker == "legacy"


# ===========================================================================
# 8. observability stays redaction-safe
# ===========================================================================

def test_recovery_observability_surface_is_complete_and_safe(tmp_path):
    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)
    cursor.mark_disconnect()
    snapshot = cursor.snapshot()

    for key in (
        "grpc_cursor_last_durable_slot",
        "grpc_cursor_safe_resume_slot",
        "grpc_cursor_last_proven_replay_boundary_slot",
        "grpc_gap_from_slot",
        "grpc_recovery_generation",
        "grpc_cursor_generation",
        "grpc_gap_unresolved",
        "grpc_recovery_terminal",
        "grpc_replay_first_available_slot",
        "grpc_cursor_write_failed_total",
        "grpc_cursor_readback_failed_total",
    ):
        assert key in snapshot, key

    assert "last_contiguous_slot" not in snapshot
    rendered = repr(snapshot).lower()
    for needle in ("http", "://", "token", "authorization", "password",
                   "api_key", "traceback"):
        assert needle not in rendered
