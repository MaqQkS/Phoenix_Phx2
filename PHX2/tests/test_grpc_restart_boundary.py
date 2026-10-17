"""Restart-time gRPC recovery boundary, exact overlap proof, terminal retention.

The 2026-07-20 post-fix re-audit recorded that commit ``5dbd1fa`` closed only
the *steady-state* form of the reconnect defect.  Three blocking holes remained,
and each is pinned here:

``R1`` GRPC_RECOVERY_BOUNDARY_NOT_PINNED_AFTER_RESTART
    The repaired boundary is preserved only while a recovery episode is already
    open.  On the FIRST attempt after a restart or clean shutdown nothing is
    pinned before the provider misbehaves, so ``mark_recovery_failed`` raises
    the gap flag with no boundary and the following ``mark_disconnect`` pins the
    already-advanced high-water mark.  N+1..N+3 are abandoned permanently, and
    the wrong state survives another restart.

``R2`` OVERLAP_PROOF_ACCEPTS_ANY_SLOT_AT_OR_BELOW_BOUNDARY
    The proof guard rejected only slots ABOVE the boundary, so a proto3-default
    ``slot`` of 0 -- or any lagging live event below the boundary -- closed the
    episode and opened the send gate with zero replay coverage.

``R3`` TERMINAL_RETENTION_CURSOR_STARTS_AT_LIVE_HEAD_ON_RESTART
    ``resume_from_slot()`` answers ``None`` for a terminal cursor, and ``None``
    is also the "subscribe at the live head" signal.  The owner built the source
    before it ever consulted terminal state, so a dead replay position became a
    silent tip subscription on restart.

Every test here is offline: scripted in-process providers, temporary cursors,
no channel, no network, no credential and no send.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import paid_grpc_source as source_module
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

from PHX2.tests.test_grpc_recovery_boundary import (
    IgnoresFromSlotYellowstone,
)
from PHX2.tests.test_grpc_reconnect_gap_recovery import (
    _identity_digest,
    _runtime,
    _store,
    _update,
    install_fake_provider,
)

# Two unrelated slot neighbourhoods: the defect must not depend on either.
BASE_A = 1_000_000
BASE_B = 317_402_991


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _commit(cursor, slot, seed=0):
    """Commit one deterministically classified event at ``slot``."""

    identity = build_transaction_skip_identity(slot, f"sig{seed}", None)
    cursor.commit_event(slot=slot, identity=identity, signature=f"sig{seed}",
                        replayed=False)
    return identity


def _reload(tmp_path):
    """Reconstruct the store from disk exactly as a restarted process would."""

    store = GrpcStreamCursorStore(
        primary_path=tmp_path / sc.CURSOR_PRIMARY_BASENAME,
        subscription_identity_digest=_identity_digest(),
    )
    store.load()
    return store


def _source_factory(server, monkeypatch):
    """A cursor-aware factory building the real source over a scripted server."""

    install_fake_provider(monkeypatch, server)

    def factory(**kwargs):
        return PaidCreatePoolYellowstoneSource(
            runtime_config=_runtime(),
            max_messages_to_scan=None,
            from_slot=kwargs.get("from_slot"),
            cursor=kwargs.get("cursor"),
            stream_generation=kwargs.get("stream_generation", 1),
        )

    return factory


def _run_owner_until(owner, predicate, *, timeout=8.0):
    """Start the owner, stop it as soon as ``predicate()`` holds."""

    owner.start()
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.01)
    owner.stop()
    thread = getattr(owner, "_thread", None)
    if thread is not None:
        thread.join(timeout=timeout)


# ===========================================================================
# R1. the boundary must be pinned BEFORE the first attempt, not after it
# ===========================================================================

@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_first_recovery_attempt_after_restart_pins_pre_attempt_boundary(
        monkeypatch, tmp_path, base):
    """No episode open, provider ignores from_slot: N must still be preserved.

    This is the exact R1 sequence.  A clean shutdown leaves
    ``recovery_required=False`` and no boundary, so the restarted process has
    nothing pinned when the provider begins beyond the requested position.
    """

    cursor = _store(tmp_path)
    _commit(cursor, base)
    assert cursor.state.recovery_required is False
    assert cursor.state.recovery_from_slot is None

    restarted = _reload(tmp_path)
    assert restarted.resume_from_slot() == base
    assert restarted.state.recovery_required is False

    # One attempt: request N, receive only N+4, then fail.
    server = IgnoresFromSlotYellowstone([[(base + 4, _update(base + 4, 4))]])
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=_source_factory(server, monkeypatch),
        dedupe=ProviderCandidateDedupe(),
        require_cursor_aware_factory=True,
        reconnect_backoff_seconds=0.0,
        cursor_store=restarted,
    )
    _run_owner_until(owner, lambda: len(server.requests) >= 2)

    # The high-water mark may legitimately have moved to N+4 ...
    assert restarted.state.last_durable_slot == base + 4
    # ... but the authoritative boundary is the position that was safe BEFORE
    # the attempt started, and nothing has proven N+1..N+3 were delivered.
    assert restarted.state.recovery_required is True
    assert restarted.state.recovery_from_slot == base
    assert restarted.safe_resume_slot() == base
    assert restarted.resume_from_slot() == base
    # The second subscription must re-ask for the SAME unproven position.
    assert server.requests[:2] == [base, base]

    # And the correct state must survive another full restart.
    again = _reload(tmp_path)
    assert again.state.recovery_from_slot == base
    assert again.resume_from_slot() == base
    authorized, reason = sc.source_health_authorizes_send(again.snapshot())
    assert authorized is False
    assert reason == sc.REASON_GAP_UNRECOVERABLE


def test_clean_shutdown_during_unproven_attempt_preserves_boundary(
        monkeypatch, tmp_path):
    """An operator stop mid-attempt must not bank the unproven position.

    ``mark_disconnect`` is deliberately skipped on a cooperative shutdown, so
    the boundary has to have been pinned before the attempt -- not derived from
    it afterwards.
    """

    base = BASE_A
    cursor = _store(tmp_path)
    _commit(cursor, base)

    restarted = _reload(tmp_path)
    server = IgnoresFromSlotYellowstone([[(base + 4, _update(base + 4, 4))]])
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=_source_factory(server, monkeypatch),
        dedupe=ProviderCandidateDedupe(),
        require_cursor_aware_factory=True,
        reconnect_backoff_seconds=0.0,
        cursor_store=restarted,
    )
    # Stop as soon as the first attempt has consumed its scripted event: the
    # shutdown lands while the attempt is still unproven.
    _run_owner_until(owner, lambda: server.delivered and len(server.requests) >= 1)

    after_restart = _reload(tmp_path)
    assert after_restart.safe_resume_slot() == base
    assert after_restart.resume_from_slot() == base
    assert after_restart.state.recovery_required is True
    assert after_restart.state.recovery_from_slot == base
    # The missing range is still owed, not silently abandoned.
    assert after_restart.slot_is_inside_recovery_responsibility(base + 1) is True
    assert after_restart.slot_is_inside_recovery_responsibility(base + 3) is True


def test_repeated_failed_attempts_do_not_replace_original_boundary(tmp_path):
    """Nine failures with ever-higher high-water marks keep the FIRST boundary."""

    base = BASE_A
    cursor = _store(tmp_path)
    _commit(cursor, base)

    # First attempt after restart: request N, the provider serves N+4 only.
    cursor.begin_stream_attempt(requested_from_slot=base)
    _commit(cursor, base + 4, seed=4)
    cursor.mark_recovery_failed(reason=sc.REASON_REPLAY_UNAVAILABLE)
    cursor.mark_disconnect()
    assert cursor.state.recovery_from_slot == base
    original_generation = cursor.state.recovery_generation

    for step in range(1, 10):
        cursor.begin_stream_attempt(requested_from_slot=cursor.safe_resume_slot())
        _commit(cursor, base + 4 + step * 7, seed=100 + step)
        cursor.mark_recovery_failed(reason=sc.REASON_REPLAY_UNAVAILABLE)
        cursor.mark_disconnect()
        assert cursor.state.recovery_from_slot == base, (
            f"boundary moved on repeat attempt {step}")
        assert cursor.safe_resume_slot() == base
        assert cursor.state.recovery_generation == original_generation

    assert _reload(tmp_path).safe_resume_slot() == base


def test_failed_attempt_boundary_is_durable_before_events_are_processed(tmp_path):
    """A pre-attempt boundary that cannot be persisted must stop the attempt.

    An event may only advance the authoritative high-water mark once the
    position it is advancing away from has been durably recorded.
    """

    cursor = _store(tmp_path)
    _commit(cursor, BASE_A)

    def _fail(*_args, **_kwargs):
        raise sc.StreamCursorWriteError("STREAM_CURSOR_WRITE_FAILED")

    original = cursor._persist_locked
    cursor._persist_locked = _fail  # type: ignore[assignment]
    try:
        with pytest.raises(sc.StreamCursorWriteError):
            cursor.begin_stream_attempt(requested_from_slot=BASE_A)
    finally:
        cursor._persist_locked = original  # type: ignore[assignment]

    # The durable document is untouched and still names the safe position.
    assert _reload(tmp_path).safe_resume_slot() == BASE_A


# ===========================================================================
# R2. overlap proof must be EXACT equality, bound to this attempt
# ===========================================================================

@pytest.mark.parametrize("base", [BASE_A, BASE_B])
def test_overlap_requires_exact_expected_boundary(tmp_path, base):
    """Only a replay observation at exactly N proves the boundary was honoured."""

    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()
    assert cursor.state.recovery_from_slot == base
    generation = cursor.state.recovery_generation
    cursor.begin_stream_attempt(requested_from_slot=base)

    # A lower slot proves the provider never reached the requested boundary;
    # a higher slot proves nothing about the range in between.
    for wrong in (base - 1, base - 100, 0, base + 1, base + 4):
        assert cursor.mark_overlap_proven(
            requested_from_slot=base, proven_boundary_slot=wrong,
            recovery_generation=generation) is False, (
            f"slot {wrong} must not prove boundary {base}")
        assert cursor.state.recovery_required is True
        assert cursor.state.recovery_from_slot == base

    # An absent / malformed position is not proof either.
    for malformed in (None, True, False, 1.5, "5", object()):
        assert cursor.mark_overlap_proven(
            requested_from_slot=base, proven_boundary_slot=malformed,
            recovery_generation=generation) is False
        assert cursor.state.recovery_required is True

    # Proof from another attempt generation, or for a from_slot that was never
    # requested, is refused even at the exact boundary slot.
    assert cursor.mark_overlap_proven(
        requested_from_slot=base, proven_boundary_slot=base,
        recovery_generation=generation + 5) is False
    assert cursor.mark_overlap_proven(
        requested_from_slot=base + 4, proven_boundary_slot=base + 4,
        recovery_generation=generation) is False
    assert cursor.state.recovery_required is True

    # Exactly N, bound to the live generation and the actual request: proof.
    assert cursor.mark_overlap_proven(
        requested_from_slot=base, proven_boundary_slot=base,
        recovery_generation=generation) is True
    assert cursor.state.recovery_required is False
    assert cursor.state.recovery_status == sc.RECOVERY_CLOSED
    assert cursor.state.last_proven_replay_boundary_slot == base
    assert cursor.state.overlap_proven_generation == generation


def test_proto3_default_slot_zero_cannot_close_recovery(monkeypatch, tmp_path):
    """An update whose slot never left the proto3 default is not proof.

    ``slot`` is a plain ``uint64`` with no presence, so an omitted value decodes
    as 0.  Accepting it closed the episode and opened the send gate against a
    boundary the provider had never served.
    """

    base = BASE_A
    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()
    generation = cursor.state.recovery_generation
    cursor.begin_stream_attempt(requested_from_slot=base)

    assert cursor.mark_overlap_proven(
        requested_from_slot=base, proven_boundary_slot=0,
        recovery_generation=generation) is False
    assert cursor.mark_gap_closed(
        requested_from_slot=base, proven_boundary_slot=0,
        recovery_generation=generation) is False
    assert cursor.state.recovery_required is True
    assert cursor.state.recovery_from_slot == base

    authorized, reason = sc.source_health_authorizes_send(cursor.snapshot())
    assert authorized is False
    assert reason == sc.REASON_GAP_UNRECOVERABLE

    # End to end through the real source: a slot-0 update must not self-certify.
    server = IgnoresFromSlotYellowstone([[(0, _update(0, 0))]])
    install_fake_provider(monkeypatch, server)
    source = PaidCreatePoolYellowstoneSource(
        runtime_config=_runtime(),
        max_messages_to_scan=None,
        from_slot=base,
        cursor=cursor,
        stream_generation=1,
    )
    list(source.iter_events(max_events=4))
    assert source.overlap_proof_accepted is False
    assert cursor.state.recovery_required is True
    assert cursor.safe_resume_slot() == base


# ===========================================================================
# R3. a terminal retention cursor must never build a live-head subscription
# ===========================================================================

def test_terminal_retention_restart_builds_no_source(tmp_path):
    """Restarting onto a terminal cursor constructs nothing at all."""

    base = BASE_A
    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.mark_disconnect()
    cursor.mark_replay_retention_exceeded(first_available=base + 500)
    assert cursor.state.recovery_terminal is True

    restarted = _reload(tmp_path)
    assert restarted.state.recovery_terminal is True

    factory_calls = []
    subscribe_requests = []
    channel_calls = []

    def _counting_factory(**kwargs):
        factory_calls.append(kwargs)
        raise AssertionError(
            "a terminal replay-retention cursor must build no source")

    class _Recorder:
        def __enter__(self):
            channel_calls.append(1)
            return object()

        def __exit__(self, *_exc):
            return False

    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=_counting_factory,
        dedupe=ProviderCandidateDedupe(),
        require_cursor_aware_factory=True,
        reconnect_backoff_seconds=0.0,
        cursor_store=restarted,
    )
    owner.start()
    thread = getattr(owner, "_thread", None)
    if thread is not None:
        thread.join(timeout=8.0)
        assert not thread.is_alive(), "a terminal cursor must stop the owner"
    owner.stop()

    assert factory_calls == [], "source factory must never be called"
    assert subscribe_requests == [], "no SubscribeRequest may be constructed"
    assert channel_calls == [], "no channel may be opened"

    snapshot = owner.snapshot()
    assert snapshot["terminal_recovery"] is True
    # The safe position and the terminal evidence are both preserved.
    assert restarted.state.last_durable_slot == base
    assert restarted.safe_resume_slot() == base
    assert restarted.state.replay_first_available_slot == base + 500
    authorized, reason = sc.source_health_authorizes_send(restarted.snapshot())
    assert authorized is False
    assert reason == sc.REASON_REPLAY_POSITION_TOO_OLD

    # A terminal cursor is never deleted or rewritten into a fresh install.
    assert (tmp_path / sc.CURSOR_PRIMARY_BASENAME).exists()
    assert _reload(tmp_path).state.recovery_terminal is True


def test_terminal_resume_is_not_ambiguous_none(tmp_path):
    """Terminal and "genuinely new" must not share one ``None`` answer."""

    base = BASE_A
    terminal = _store(tmp_path)
    _commit(terminal, base)
    terminal.mark_disconnect()
    terminal.mark_replay_retention_exceeded(first_available=base + 500)

    decision = terminal.resume_decision()
    assert decision.action == sc.RESUME_ACTION_REFUSE_TERMINAL
    assert decision.builds_source is False
    assert decision.from_slot is None
    assert decision.reason == sc.REASON_REPLAY_POSITION_TOO_OLD

    # A genuinely new subscription is a DIFFERENT, explicitly bootstrapping
    # decision -- distinguishable without inspecting any other field.
    fresh = _store(tmp_path / "fresh")
    fresh_decision = fresh.resume_decision()
    assert fresh_decision.action == sc.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD
    assert fresh_decision.builds_source is True
    assert fresh_decision.from_slot is None

    # And an ordinary resume names its position.
    ordinary = _store(tmp_path / "ordinary")
    _commit(ordinary, base)
    ordinary_decision = ordinary.resume_decision()
    assert ordinary_decision.action == sc.RESUME_ACTION_SUBSCRIBE_FROM_SLOT
    assert ordinary_decision.builds_source is True
    assert ordinary_decision.from_slot == base

    assert (sc.RESUME_ACTION_REFUSE_TERMINAL
            != sc.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD)


def test_quarantined_cursor_also_refuses_to_build_a_source(tmp_path):
    """A cursor that may not be trusted is not a licence to start at the tip."""

    base = BASE_A
    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor._quarantined = True
    cursor._quarantine_reason = "CHECKPOINT_RECORD_DIGEST_INVALID"

    decision = cursor.resume_decision()
    assert decision.builds_source is False
    assert decision.action == sc.RESUME_ACTION_REFUSE_TERMINAL
    assert decision.from_slot is None
    assert cursor.is_terminal() is True


def test_recovery_snapshot_reports_the_pinned_attempt_boundary(tmp_path):
    """Observability must expose the pinned boundary, redaction-safe."""

    base = BASE_A
    cursor = _store(tmp_path)
    _commit(cursor, base)
    cursor.begin_stream_attempt(requested_from_slot=base)
    _commit(cursor, base + 4, seed=4)
    cursor.mark_recovery_failed(reason=sc.REASON_REPLAY_UNAVAILABLE)

    snapshot = cursor.snapshot()
    assert snapshot["grpc_gap_from_slot"] == base
    assert snapshot["grpc_cursor_safe_resume_slot"] == base
    assert snapshot["grpc_cursor_last_durable_slot"] == base + 4
    assert snapshot["grpc_attempt_pinned_boundary_slot"] == base
    assert snapshot["grpc_attempt_requested_from_slot"] == base
    # Redaction: values are redaction-safe scalars only -- ints, floats
    # (checkpoint latency / pending-age / batch-window config), bools, None or
    # closed-set strings. No object, path or raw error text can leak.
    for key, value in snapshot.items():
        assert isinstance(value, (int, float, bool, type(None), str)), key
        if isinstance(value, str):
            assert ":\\" not in value and "//" not in value, key
