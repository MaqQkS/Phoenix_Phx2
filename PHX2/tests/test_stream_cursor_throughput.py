"""Durable gRPC stream-cursor throughput under a sustained firehose.

PHX2 durable-cursor throughput remediation.

The certified final Step-6 live acceptance (report sha 4f8160f8...) recorded a
BLOCKING finding: the durable safe-resume cursor could not keep pace with the
confirmed chain head under a sustained ~108 tx/s firehose. Root cause: the
cursor persisted a full authenticated checkpoint generation SYNCHRONOUSLY on
the single gRPC consumption thread for EVERY matched event (writes_per_event ==
1.0). Each write is a ~117 KB serialize + 2 fsyncs + dir fsync + THREE full
readback re-validations + a full-document copyfile; at the effective per-write
cost under real contention the consumer sustains only ~59 tx/s, so total lag
grows ~1.15 slots/s and a sub-second restart faces a ~1461-slot gap that RPC
backfill cannot close inside the 1800 s bound.

The fix keeps every fail-closed durability guarantee but bounds persistence
frequency: the in-memory position advances on every event (so intra-session
reconnect dedupe is unchanged), while the durable checkpoint is written on a
small bounded batch (count OR elapsed time), with a FORCED synchronous flush on
every effectful/critical transition (admitted migration, disconnect, recovery
state change, terminal transition, cooperative shutdown). The batch window
therefore only ever contains deterministic rejections, whose reserve/fee
re-ingestion after a crash-replay is idempotent (reserve is last-value snapshot;
fee has an internal (signature, event_index) dedupe; both indices are in-memory
and rebuilt from the replay), so no durable side effect is doubled.

Every test here is offline: temporary cursors, an injected monotonic clock, no
channel, no network, no credential, no send, no real ledger.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pytest

from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer import checkpoint_envelope as cpe


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwx"


def _sig(i: int) -> str:
    base = "5" + "".join(_ALPHABET[(i >> (b * 3)) % 54] for b in range(29))
    return (base * 3)[:88]


def _addr(i: int, salt: int) -> str:
    base = "".join(_ALPHABET[((i * 7 + salt * 13) >> (b * 2)) % 54] for b in range(22))
    return (base * 2)[:44]


def _identity(slot: int, i: int, *, migration: Optional[str] = None) -> str:
    return sc.build_stream_event_identity(
        slot=slot, signature=_sig(i), transaction_index=i % 64,
        outer_instruction_index=i % 8, flattened_instruction_index=i % 12,
        migration_version=migration, mint=_addr(i, 1), pool=_addr(i, 2))


class _Clock:
    """Deterministic injectable monotonic clock (seconds)."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


def _digest() -> str:
    return cpe.sha256_hex_text("throughput-test-subscription-identity")


def _make_store(tmp_path: Path, *, batch_events: int = 1, batch_seconds: float = 0.0,
                clock: Optional[_Clock] = None,
                recent_limit: int = sc.DEFAULT_RECENT_IDENTITY_LIMIT,
                boundary_limit: int = sc.DEFAULT_BOUNDARY_IDENTITY_LIMIT,
                name: str = sc.CURSOR_PRIMARY_BASENAME) -> sc.GrpcStreamCursorStore:
    kwargs = dict(
        primary_path=tmp_path / name,
        subscription_identity_digest=_digest(),
        recent_identity_limit=recent_limit,
        boundary_identity_limit=boundary_limit,
        persist_batch_max_events=batch_events,
        persist_batch_max_seconds=batch_seconds,
    )
    if clock is not None:
        kwargs["monotonic_fn"] = clock
    store = sc.GrpcStreamCursorStore(**kwargs)
    store.load()
    return store


def _drive(store: sc.GrpcStreamCursorStore, *, n: int, start_slot: int = 5_000_000,
           tx_per_slot: int = 43, start_i: int = 0,
           clock: Optional[_Clock] = None,
           per_event_seconds: float = 0.0) -> Tuple[int, int]:
    """Commit ``n`` rejection-class events; return (last_slot, next_i)."""
    slot = start_slot
    gi = start_i
    for k in range(n):
        if k % tx_per_slot == 0:
            slot += 1
        store.commit_event(slot=slot, identity=_identity(slot, gi), signature=_sig(gi))
        if clock is not None and per_event_seconds:
            clock.advance(per_event_seconds)
        gi += 1
    return slot, gi


# ---------------------------------------------------------------------------
# 1. sustained firehose batches cursor writes (throughput)
# ---------------------------------------------------------------------------

def test_firehose_batches_cursor_writes(tmp_path, monkeypatch):
    """A batched store performs far fewer than one disk write per event."""
    writes = {"n": 0}
    real = cpe.write_checkpoint_generation

    def counting(**kwargs):
        writes["n"] += 1
        return real(**kwargs)

    monkeypatch.setattr(cpe, "write_checkpoint_generation", counting)
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=32, batch_seconds=0.5, clock=clock)
    n = 20_000
    _drive(store, n=n, clock=clock, per_event_seconds=1.0 / 108.0)
    store.flush_if_pending()
    writes_per_event = writes["n"] / float(n)
    # Count-driven flushing alone caps this near 1/32; the time flush at 0.5 s
    # adds a few. Comfortably < 1/10.
    assert writes_per_event < 0.1, writes_per_event


def test_amortized_write_cost_keeps_pace_with_firehose(tmp_path, monkeypatch):
    """Amortized cursor write-time per event stays inside the inflow budget.

    This is the exact physics the pre-fix design violated: at writes_per_event
    == 1.0 and the measured per-write cost, amortized write-time per event
    exceeds the 108 tx/s inter-event interval, so the consumer cannot keep pace.
    """
    writes = {"n": 0}
    real = cpe.write_checkpoint_generation

    def counting(**kwargs):
        writes["n"] += 1
        return real(**kwargs)

    monkeypatch.setattr(cpe, "write_checkpoint_generation", counting)
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=32, batch_seconds=0.5, clock=clock)
    n = 12_000
    _drive(store, n=n, clock=clock, per_event_seconds=1.0 / 108.0)
    store.flush_if_pending()
    writes_per_event = writes["n"] / float(n)
    measured_per_write_ms = 17.0     # effective cost under real contention
    inflow_interval_ms = 1000.0 / 108.0
    amortized = writes_per_event * measured_per_write_ms
    assert amortized < 0.5 * inflow_interval_ms, (amortized, inflow_interval_ms)


def test_durable_lag_bounded_by_batch_window(tmp_path):
    """In-memory processed minus on-disk durable never exceeds the batch bound."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=32, batch_seconds=1000.0, clock=clock)
    # No time-based flush (huge seconds); only the count trigger fires.
    max_seen = 0
    slot = 6_000_000
    for k in range(500):
        if k % 43 == 0:
            slot += 1
        store.commit_event(slot=slot, identity=_identity(slot, k), signature=_sig(k))
        lag = int(store.state.last_durable_slot) - int(store.last_flushed_slot)
        max_seen = max(max_seen, lag)
    # 32 events span at most ceil(32/43)+1 boundary slots.
    assert max_seen <= 2, max_seen
    assert store.pending_commit_events <= 32


# ---------------------------------------------------------------------------
# 2. crash / restart safety across the batch window
# ---------------------------------------------------------------------------

def test_multiple_identities_one_slot_survive_restart(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=8, batch_seconds=1000.0, clock=clock)
    ids = [_identity(700, i) for i in range(4)]
    for ident in ids:
        store.commit_event(slot=700, identity=ident, signature=_sig(0))
    store.flush_if_pending()
    restarted = _make_store(tmp_path, batch_events=8, batch_seconds=1000.0)
    assert restarted.resume_from_slot() == 700
    for ident in ids:
        assert restarted.is_duplicate(ident), ident


def test_crash_before_flush_durable_is_last_flushed(tmp_path):
    """Un-flushed commits are lost from disk; the durable position is the last
    flushed slot and replay from there is inclusive."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=100, batch_seconds=1000.0, clock=clock)
    _drive(store, n=10, start_slot=800, tx_per_slot=1)   # 10 slots, no flush yet
    processed = int(store.state.last_durable_slot)
    store.flush_if_pending()                              # explicit flush point
    flushed_slot = int(store.last_flushed_slot)
    assert flushed_slot == processed
    # Now advance further WITHOUT flushing, then simulate a crash (drop store).
    _drive(store, n=5, start_slot=processed + 1, tx_per_slot=1, start_i=100)
    assert int(store.state.last_durable_slot) > flushed_slot   # in-memory ahead
    # A crashed process loses in-memory state; a fresh store loads only disk.
    restarted = _make_store(tmp_path, batch_events=100, batch_seconds=1000.0)
    assert restarted.resume_from_slot() == flushed_slot        # conservative


def test_crash_during_flush_preserves_previous_generation(tmp_path, monkeypatch):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0, clock=clock)
    _drive(store, n=4, start_slot=900, tx_per_slot=1)   # count trigger flushes
    gen_before = store.generation
    good_slot = int(store.last_flushed_slot)
    assert gen_before >= 1

    def boom(**kwargs):
        raise cpe.CheckpointWriteError("CHECKPOINT_WRITE_FAILED:PermissionError")

    monkeypatch.setattr(cpe, "write_checkpoint_generation", boom)
    _drive(store, n=4, start_slot=good_slot + 1, tx_per_slot=1, start_i=50)
    ok = store.flush_if_pending()
    assert ok is False
    assert store.generation == gen_before          # no false advance
    assert store.cursor_durability_status == cpe.CHECKPOINT_DURABILITY_DEGRADED
    # The previous valid generation is intact on disk.
    restarted = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0)
    assert restarted.resume_from_slot() == good_slot


def test_crash_after_flush_durable_is_current(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0, clock=clock)
    last, _ = _drive(store, n=8, start_slot=1000, tx_per_slot=1)   # two flushes
    store.flush_if_pending()
    restarted = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0)
    assert restarted.resume_from_slot() == int(store.last_flushed_slot)
    assert restarted.resume_from_slot() == last


def test_restart_replays_post_checkpoint_events_via_dedupe(tmp_path):
    """After restart the flushed identities are recognised as duplicates so a
    replay does not re-run their side effects."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0, clock=clock)
    ids = [_identity(1200 + i, i) for i in range(4)]
    for i, ident in enumerate(ids):
        store.commit_event(slot=1200 + i, identity=ident, signature=_sig(i))
    store.flush_if_pending()
    restarted = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0)
    for ident in ids:
        assert restarted.is_duplicate(ident)


# ---------------------------------------------------------------------------
# 3. effectful path stays synchronous; dedupe never weakened
# ---------------------------------------------------------------------------

def test_admitted_migration_forces_synchronous_flush(tmp_path):
    """An admitted migration (detail_identity present) is flushed immediately,
    so the batch window only ever contains rejections."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0, clock=clock)
    _drive(store, n=5, start_slot=1300, tx_per_slot=1)   # rejections, deferred
    assert store.pending_commit_events > 0
    detail = _identity(1400, 999, migration="migrate_v2")
    skip = sc.build_stream_event_identity(slot=1400, signature=_sig(999),
                                          transaction_index=1)
    store.commit_event(slot=1400, identity=skip, signature=_sig(999),
                       detail_identity=detail)
    # The forced flush persisted everything up to and including the migration.
    assert store.pending_commit_events == 0
    assert int(store.last_flushed_slot) == 1400
    restarted = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0)
    assert restarted.resume_from_slot() == 1400
    assert restarted.is_duplicate(skip)


def test_in_memory_dedupe_updates_every_event_regardless_of_flush(tmp_path):
    """is_duplicate reflects EVERY processed event immediately, before any disk
    flush -- intra-session reconnect dedupe is unchanged by batching."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0, clock=clock)
    # Establish a durable position (the first-ever commit force-flushes).
    store.commit_event(slot=1499, identity=_identity(1499, 6), signature=_sig(6))
    assert store.pending_commit_events == 0
    ident = _identity(1500, 7)
    store.commit_event(slot=1500, identity=ident, signature=_sig(7))
    assert store.pending_commit_events == 1        # deferred, not yet flushed
    assert store.is_duplicate(ident)               # but already deduped in memory


def test_batch_disabled_default_flushes_every_event(tmp_path, monkeypatch):
    """The store default (no batch config) is byte-for-byte the pre-fix
    behaviour: one durable generation per event."""
    writes = {"n": 0}
    real = cpe.write_checkpoint_generation

    def counting(**kwargs):
        writes["n"] += 1
        return real(**kwargs)

    monkeypatch.setattr(cpe, "write_checkpoint_generation", counting)
    store = _make_store(tmp_path)   # defaults: batch_events=1, batch_seconds=0
    _drive(store, n=10, start_slot=1600, tx_per_slot=1)
    assert writes["n"] == 10
    assert store.pending_commit_events == 0
    assert int(store.last_flushed_slot) == int(store.state.last_durable_slot)


# ---------------------------------------------------------------------------
# 4. time-based flush, cooperative shutdown, observability
# ---------------------------------------------------------------------------

def test_time_based_flush_bounds_idle_durable_lag(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=100000, batch_seconds=0.5, clock=clock)
    # Establish a durable position (the first-ever commit force-flushes).
    store.commit_event(slot=1699, identity=_identity(1699, 9), signature=_sig(9))
    assert store.pending_commit_events == 0
    store.commit_event(slot=1700, identity=_identity(1700, 0), signature=_sig(0))
    assert store.pending_commit_events == 1
    clock.advance(0.6)   # exceed the time bound
    store.commit_event(slot=1701, identity=_identity(1701, 1), signature=_sig(1))
    assert store.pending_commit_events == 0                 # time flush fired
    assert int(store.last_flushed_slot) == 1701


def test_flush_if_pending_is_idempotent_and_bounded(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=100000, batch_seconds=1000.0, clock=clock)
    store.commit_event(slot=1799, identity=_identity(1799, 100), signature=_sig(100))
    _drive(store, n=7, start_slot=1800, tx_per_slot=1)
    assert store.pending_commit_events == 7
    assert store.flush_if_pending() is True
    assert store.pending_commit_events == 0
    assert store.flush_if_pending() is True     # nothing pending -> still True
    forced_before = store.cursor_checkpoint_forced_flush_total
    store.flush_if_pending()
    assert store.cursor_checkpoint_forced_flush_total == forced_before


def test_failed_cooperative_flush_is_observable(tmp_path, monkeypatch):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=100000, batch_seconds=1000.0, clock=clock)
    store.commit_event(slot=1899, identity=_identity(1899, 100), signature=_sig(100))
    _drive(store, n=3, start_slot=1900, tx_per_slot=1)

    def boom(**kwargs):
        raise cpe.CheckpointWriteError("CHECKPOINT_WRITE_FAILED:PermissionError")

    monkeypatch.setattr(cpe, "write_checkpoint_generation", boom)
    assert store.flush_if_pending() is False
    snap = store.snapshot()
    assert snap["grpc_cursor_durability_status"] == cpe.CHECKPOINT_DURABILITY_DEGRADED
    assert snap["grpc_cursor_checkpoint_failed_total"] >= 1
    assert snap["grpc_cursor_pending_commit_events"] >= 3
    assert snap["grpc_cursor_last_failure_category"] == cpe.CHECKPOINT_FAILURE_TRANSIENT


def test_snapshot_exposes_lag_decomposition_fields(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=8, batch_seconds=1000.0, clock=clock)
    _drive(store, n=5, start_slot=2000, tx_per_slot=1)
    snap = store.snapshot()
    for key in (
        "grpc_cursor_last_durable_slot",          # in-memory processed high-water
        "grpc_cursor_flushed_durable_slot",       # on-disk durable
        "grpc_cursor_durability_lag_slots",
        "grpc_cursor_pending_commit_events",
        "grpc_cursor_oldest_pending_age_ms",
        "grpc_cursor_checkpoint_attempted_total",
        "grpc_cursor_checkpoint_succeeded_total",
        "grpc_cursor_checkpoint_failed_total",
        "grpc_cursor_checkpoint_deferred_total",
        "grpc_cursor_checkpoint_forced_flush_total",
        "grpc_cursor_checkpoint_bytes",
        "grpc_cursor_checkpoint_latency_ms_p50",
        "grpc_cursor_checkpoint_latency_ms_p95",
        "grpc_cursor_checkpoint_latency_ms_p99",
        "grpc_cursor_durability_status",
        "grpc_cursor_persist_batch_max_events",
        "grpc_cursor_persist_batch_max_seconds",
    ):
        assert key in snap, key
    assert snap["grpc_cursor_durability_lag_slots"] >= 0
    assert snap["grpc_cursor_checkpoint_deferred_total"] >= 1   # 5 commits, batch 8


def test_healthy_status_after_successful_flush(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=2, batch_seconds=1000.0, clock=clock)
    _drive(store, n=2, start_slot=2100, tx_per_slot=1)
    assert store.cursor_durability_status == cpe.CHECKPOINT_DURABILITY_HEALTHY
    assert store.cursor_checkpoint_succeeded_total >= 1


# ---------------------------------------------------------------------------
# 5. conservatism, recovery integration, corruption unchanged
# ---------------------------------------------------------------------------

def test_from_slot_never_newer_than_flushed_after_restart(tmp_path):
    """The single most important invariant: a restart never resumes from a
    position newer than what was durably flushed."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=64, batch_seconds=1000.0, clock=clock)
    _drive(store, n=200, start_slot=2200, tx_per_slot=7)
    processed = int(store.state.last_durable_slot)
    flushed = int(store.last_flushed_slot)
    assert flushed <= processed
    restarted = _make_store(tmp_path, batch_events=64, batch_seconds=1000.0)
    resume = restarted.resume_from_slot()
    assert resume is not None and resume <= processed
    assert resume == flushed


def test_disconnect_forces_flush_and_pins_boundary(tmp_path):
    """A recovery transition flushes pending commits and pins the boundary,
    exactly as before batching (recovery mutators are never deferred)."""
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0, clock=clock)
    _drive(store, n=6, start_slot=2300, tx_per_slot=1)
    assert store.pending_commit_events > 0
    store.mark_disconnect(reason=sc.REASON_PROVIDER_DISCONNECT)
    assert store.pending_commit_events == 0            # forced durable
    assert store.state.recovery_required is True
    restarted = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0)
    assert restarted.state.recovery_required is True


def test_terminal_transition_is_never_deferred(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0, clock=clock)
    _drive(store, n=3, start_slot=2400, tx_per_slot=1)
    # The real terminal-retention path is reached only after a disconnect has
    # opened a recovery episode (a terminal cursor with a position but no
    # boundary is an invalid cross-field state). The disconnect flushes the
    # pending batch; the terminal transition then persists synchronously too.
    store.mark_disconnect(reason=sc.REASON_PROVIDER_DISCONNECT)
    assert store.pending_commit_events == 0
    store.mark_replay_retention_exceeded(first_available=2_999_999)
    assert store.pending_commit_events == 0
    restarted = _make_store(tmp_path, batch_events=1000, batch_seconds=1000.0)
    assert restarted.is_terminal() is True
    assert restarted.resume_from_slot() is None


def test_batched_primary_and_backup_remain_valid(tmp_path):
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0, clock=clock)
    _drive(store, n=16, start_slot=2500, tx_per_slot=1)   # four flushes
    store.flush_if_pending()
    result = _make_store(tmp_path, batch_events=4, batch_seconds=1000.0).load_result
    assert result.checkpoint_status in (
        cpe.CHECKPOINT_PRIMARY_OK, cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK)
    assert result.checkpoint_quarantined is False


def test_concurrent_commit_and_flush_do_not_corrupt(tmp_path):
    """The store's RLock serialises a commit thread and a flush thread; the
    reloaded cursor is always a valid generation (no torn write, no deadlock)."""
    import threading
    clock = _Clock()
    store = _make_store(tmp_path, batch_events=16, batch_seconds=1000.0, clock=clock)
    stop = threading.Event()

    def flusher():
        while not stop.is_set():
            store.flush_if_pending()

    t = threading.Thread(target=flusher, daemon=True)
    t.start()
    try:
        _drive(store, n=2000, start_slot=2600, tx_per_slot=11)
    finally:
        stop.set()
        t.join(timeout=5.0)
    store.flush_if_pending()
    assert not t.is_alive()
    reloaded = _make_store(tmp_path, batch_events=16, batch_seconds=1000.0)
    assert reloaded.quarantined is False
    assert reloaded.resume_from_slot() == int(store.last_flushed_slot)
