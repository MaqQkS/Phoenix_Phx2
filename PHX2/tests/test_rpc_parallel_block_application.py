"""Parallel confirmed-RPC application: canonical order, bounds, fail-closed.

The worker pool is allowed to be fast and out of order. The authoritative
parent is not allowed to be either. These tests pin the seam between them:
results arrive in whatever order the pool produces, and application, duplicate
suppression, checkpoint advancement and cursor resolution still happen in
strictly ascending slot order, halting at the FIRST unresolved produced block.

Everything is offline. A fake pool stands in wherever a real worker process
would have to crash, hang or lie; the real spawn pool is exercised separately
in ``test_rpc_block_scan_prefilter.py``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from PHX2.free_tier_producer import rpc_block_scan as rbs
from PHX2.free_tier_producer import rpc_gap_recovery as rgr
from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer.paid_grpc_source import (
    build_transaction_skip_identity,
)
from PHX2.free_tier_producer.rpc_block_pool import (
    POOL_RESTARTS_EXHAUSTED,
    POOL_TIMEOUT,
    POOL_WORKER_FAILED,
    BlockScanPoolError,
    BoundedBlockScanPool,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID

PROGRAM_IDS = (PUMPSWAP_PROGRAM_ID,)
IDENTITY_DIGEST = sc.compute_subscription_identity_digest(
    source_kind=sc.STREAM_SOURCE_YELLOWSTONE,
    commitment="CONFIRMED",
    transaction_filter_name="phx2_pumpswap_transactions",
    account_include=[PUMPSWAP_PROGRAM_ID],
    program_id=PUMPSWAP_PROGRAM_ID,
    migration_versions_supported=("migrate", "migrate_v2"),
    decoder_schema_version=sc.STREAM_CURSOR_SCHEMA_V1,
)

BOUNDARY_SLOT = 100
BOUNDARY_SIG = "S1gBoundary"
PRODUCED = [101, 102, 103, 104, 105, 106, 107, 108]
OVERLAP_SLOT = PRODUCED[-1]
OVERLAP_SIG = "S1gTarget11"
OVERLAP_TX_INDEX = 1
BLOCK_TIME = 1_753_142_400
_B58_DIGITS = "ABCDEFGHJK"


@pytest.fixture(autouse=True)
def _no_network_no_delivery(monkeypatch):
    """No socket, no HTTP, no Telegram, no Discord may be constructed."""

    import socket
    import urllib.request

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("FORBIDDEN_TRANSPORT_CONSTRUCTION")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    yield


def b58_digits(value: int) -> str:
    """Base58 excludes 0, O, I and l: encode slot digits inside the alphabet."""

    return "".join(_B58_DIGITS[int(digit)] for digit in str(value))


def b58_hash(slot: int) -> str:
    return "Hb" + b58_digits(slot)


def make_tx(signature: str, *, relevant: bool = True) -> Dict[str, Any]:
    keys = ["FeePayer1111111111111111111111111111111111"]
    if relevant:
        keys.append(PUMPSWAP_PROGRAM_ID)
    return {
        "meta": {"err": None, "logMessages": [], "innerInstructions": [],
                 "preTokenBalances": [], "postTokenBalances": []},
        "transaction": {
            "message": {"accountKeys": keys, "instructions": []},
            "signatures": [signature],
        },
    }


def make_result(slot: int, parent_slot: int, previous_hash: str,
                txs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "blockHeight": slot - 10,
        "blockTime": BLOCK_TIME,
        "blockhash": b58_hash(slot),
        "parentSlot": parent_slot,
        "previousBlockhash": previous_hash,
        "transactions": txs,
    }


def build_chain(produced: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    blocks: Dict[int, Dict[str, Any]] = {}
    previous_slot = produced[0] - 1
    previous_hash = b58_hash(produced[0] - 1)
    for slot in produced:
        txs = [make_tx(f"S1gFizz{b58_digits(slot)}", relevant=False)]
        if slot == OVERLAP_SLOT:
            txs.append(make_tx(OVERLAP_SIG, relevant=True))
        else:
            txs.append(make_tx(f"S1gEvent{b58_digits(slot)}", relevant=True))
        blocks[slot] = make_result(slot, previous_slot, previous_hash, txs)
        previous_slot = slot
        previous_hash = b58_hash(slot)
    return blocks


class RawFixtureTransport:
    """Deterministic transport that can answer with UNDECODED bodies."""

    supports_raw_bodies = True

    def __init__(self, *, produced: Sequence[int],
                 blocks: Dict[int, Dict[str, Any]],
                 unavailable: Sequence[int] = ()) -> None:
        self.produced = list(produced)
        self.blocks = dict(blocks)
        self.unavailable = set(unavailable)
        self.block_requests: List[int] = []

    def __call__(self, method: str, params: List[Any], _timeout: float,
                 raw: bool = False) -> Tuple[int, Any]:
        if method == "getSlot":
            return 200, {"result": self.produced[-1] + 16}
        if method == "getBlocks":
            start, end = int(params[0]), int(params[1])
            return 200, {"result": [s for s in self.produced
                                    if start <= s <= end]}
        if method == "getBlock":
            slot = int(params[0])
            self.block_requests.append(slot)
            if slot in self.unavailable or slot not in self.blocks:
                body: Dict[str, Any] = {
                    "jsonrpc": "2.0", "id": 1,
                    "error": {"code": -32007, "message": "skipped"}}
            else:
                body = {"jsonrpc": "2.0", "id": 1,
                        "result": self.blocks[slot]}
            if raw:
                return 200, json.dumps(body, separators=(",", ":")).encode()
            return 200, body
        return 200, {"error": {"code": -32601, "message": "unknown"}}


class FakePool:
    """Pool stand-in with scriptable ordering and failures."""

    def __init__(self, *, batch_size: int = 2, capacity: int = 4,
                 reverse: bool = False, duplicate: bool = False,
                 corrupt: Optional[Any] = None,
                 fail_after_batches: Optional[int] = None,
                 fail_reason: str = POOL_WORKER_FAILED) -> None:
        self.batch_size = int(batch_size)
        self.capacity_batches = int(capacity)
        self.restarts = 0
        self._reverse = reverse
        self._duplicate = duplicate
        self._corrupt = corrupt
        self._fail_after = fail_after_batches
        self._fail_reason = fail_reason
        self._batches = 0
        self._pending: List[Dict[str, Any]] = []
        self.closed = False

    @property
    def outstanding_batches(self) -> int:
        return 1 if self._pending else 0

    def try_submit(self, tasks: Sequence[Tuple[int, bytes]]) -> bool:
        if self._pending:
            return False
        self._batches += 1
        if self._fail_after is not None and self._batches > self._fail_after:
            raise BlockScanPoolError(self._fail_reason)
        results = [rbs.scan_block_task({
            "slot": slot, "payload": payload,
            "program_ids": PROGRAM_IDS}) for slot, payload in tasks]
        if self._reverse:
            results.reverse()
        if self._duplicate and results:
            results.append(dict(results[0]))
        if self._corrupt is not None:
            results = [self._corrupt(result) for result in results]
        self._pending = results
        return True

    def poll(self, timeout: float = 0.0) -> List[Dict[str, Any]]:
        pending, self._pending = self._pending, []
        return pending

    def close(self) -> None:
        self.closed = True


def make_cursor(state_dir, *, boundary: int = BOUNDARY_SLOT):
    store = sc.build_cursor_store(
        state_dir=state_dir, subscription_identity_digest=IDENTITY_DIGEST)
    store.load()
    store.commit_event(
        slot=boundary,
        identity=sc.build_stream_event_identity(
            slot=boundary, signature=BOUNDARY_SIG, transaction_index=0),
        signature=BOUNDARY_SIG)
    store.mark_disconnect()
    store.begin_stream_attempt(requested_from_slot=boundary)
    store.mark_replay_retention_exceeded()
    assert store.is_terminal()
    return store


def make_config(**overrides: Any) -> rgr.RpcGapRecoveryConfig:
    base = dict(
        mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed",
        rpc_request_spacing_seconds=0.0001,
        max_commitment_wait_seconds=5.0,
        max_overlap_wait_seconds=5.0,
        rpc_apply_processes=4,
        rpc_apply_queue_bound=4,
        rpc_apply_batch_size=2,
    )
    base.update(overrides)
    return rgr.RpcGapRecoveryConfig(**base)


def make_coordinator(state_dir, *, transport,
                     config: Optional[rgr.RpcGapRecoveryConfig] = None,
                     **kwargs: Any) -> rgr.RpcGapBackfillCoordinator:
    config = config or make_config()
    recovery_store = rgr.RpcGapRecoveryStore(state_dir=state_dir)
    recovery_store.load()
    buffer = rgr.QuarantinedLiveBuffer(
        state_dir=state_dir, subscription_identity_digest=IDENTITY_DIGEST,
        max_events=config.max_quarantine_events,
        max_bytes=config.max_quarantine_bytes,
        max_age_seconds=config.max_quarantine_age_seconds)
    buffer.load()
    return rgr.RpcGapBackfillCoordinator(
        config=config, recovery_store=recovery_store,
        quarantine_buffer=buffer,
        subscription_identity_digest=IDENTITY_DIGEST,
        rpc_post_fn=transport, sleep_fn=lambda _s: None, **kwargs)


def open_episode(coordinator, cursor) -> None:
    ok, detail = coordinator.begin_or_resume_episode(
        cursor_store=cursor,
        entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE)
    assert ok, detail
    coordinator.begin_quarantine_segment()
    coordinator.note_observed_transaction(
        slot=OVERLAP_SLOT, signature=OVERLAP_SIG,
        transaction_index=OVERLAP_TX_INDEX,
        skip_identity=build_transaction_skip_identity(
            OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX),
        attempt_generation=int(cursor.state.attempt_generation))


def install_pool(coordinator, pool: Any) -> None:
    """Force the coordinator to use ``pool`` instead of building a real one."""

    original = rgr.BoundedBlockScanPool

    def _factory(**_kwargs: Any) -> Any:
        return pool

    coordinator._test_pool_factory = _factory  # documentation only
    rgr.BoundedBlockScanPool = _factory        # type: ignore[assignment]
    coordinator._restore_pool_factory = lambda: setattr(
        rgr, "BoundedBlockScanPool", original)


@pytest.fixture
def pool_factory(monkeypatch):
    """Yield a helper that swaps in a fake pool for one coordinator run."""

    def _install(pool: Any) -> None:
        monkeypatch.setattr(rgr, "BoundedBlockScanPool",
                            lambda **_kwargs: pool)

    return _install


# ---------------------------------------------------------------------------
# canonical order and contiguous commit
# ---------------------------------------------------------------------------

class TestCanonicalOrder:
    def test_out_of_order_completion_applies_in_ascending_slot_order(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        pool_factory(FakePool(reverse=True))
        open_episode(coordinator, cursor)
        applied: List[Tuple[int, int]] = []
        original = coordinator._process_bridged_update

        def _traced(**kwargs: Any) -> Any:
            applied.append((int(kwargs["slot"]),
                            int(kwargs["transaction_index"])))
            return original(**kwargs)

        coordinator._process_bridged_update = _traced
        assert coordinator.run_backfill()
        assert applied == sorted(applied)
        assert [slot for slot, _index in applied] == PRODUCED

    def test_duplicate_worker_result_is_absorbed_safely(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        pool_factory(FakePool(duplicate=True))
        open_episode(coordinator, cursor)
        applied: List[int] = []
        original = coordinator._process_bridged_update

        def _traced(**kwargs: Any) -> Any:
            applied.append(int(kwargs["slot"]))
            return original(**kwargs)

        coordinator._process_bridged_update = _traced
        assert coordinator.run_backfill()
        assert applied == PRODUCED
        assert coordinator.snapshot()["transactions_relevant"] == len(PRODUCED)

    def test_serial_and_pooled_paths_agree_exactly(self, tmp_path,
                                                   pool_factory) -> None:
        def _run(directory, pool: Optional[Any]) -> Dict[str, Any]:
            directory.mkdir(parents=True, exist_ok=True)
            cursor = make_cursor(directory)
            transport = RawFixtureTransport(
                produced=PRODUCED, blocks=build_chain(PRODUCED))
            processes = 1 if pool is None else 4
            coordinator = make_coordinator(
                directory, transport=transport,
                config=make_config(rpc_apply_processes=processes))
            if pool is not None:
                pool_factory(pool)
            open_episode(coordinator, cursor)
            trace: List[Any] = []
            original = coordinator._process_bridged_update

            def _traced(**kwargs: Any) -> Any:
                trace.append((int(kwargs["slot"]),
                              int(kwargs["transaction_index"]),
                              str(kwargs["signature"]),
                              kwargs["update"].SerializeToString()))
                return original(**kwargs)

            coordinator._process_bridged_update = _traced
            proven = coordinator.run_backfill()
            snapshot = coordinator.snapshot()
            return {
                "proven": proven, "trace": trace,
                "counters": {
                    key: snapshot[key] for key in (
                        "transactions_scanned", "transactions_relevant",
                        "transactions_rejected", "migration_events_recovered",
                        "reserve_events_recovered", "fee_events_recovered",
                        "duplicate_events_suppressed",
                        "produced_blocks_completed", "last_completed_slot",
                        "overlap_proof_state")},
            }

        serial = _run(tmp_path / "serial", None)
        pooled = _run(tmp_path / "pooled", FakePool(reverse=True))
        assert serial["proven"] and pooled["proven"]
        assert serial["trace"] == pooled["trace"]
        assert serial["counters"] == pooled["counters"]


class TestUnresolvedBlocksHaltAdvancement:
    def test_unavailable_produced_block_halts_at_the_previous_slot(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED),
            unavailable=[104])
        coordinator = make_coordinator(
            tmp_path, transport=transport,
            config=make_config(checkpoint_every_blocks=1))
        pool_factory(FakePool(reverse=True))
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
        # The contiguous prefix BELOW the unresolved block is committed; the
        # unresolved block is never crossed.
        assert coordinator.snapshot()["last_completed_slot"] == 103
        assert coordinator.snapshot()["overlap_proof_state"] != (
            rgr.OVERLAP_PROVEN)

    def test_wrong_block_identity_fails_closed(self, tmp_path,
                                               pool_factory) -> None:
        blocks = build_chain(PRODUCED)
        blocks[105]["previousBlockhash"] = b58_hash(999)
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(
            tmp_path, transport=transport,
            config=make_config(checkpoint_every_blocks=1))
        pool_factory(FakePool())
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
        assert coordinator.snapshot()["last_completed_slot"] == 104

    def test_wrong_parent_slot_fails_closed(self, tmp_path,
                                            pool_factory) -> None:
        blocks = build_chain(PRODUCED)
        blocks[105]["parentSlot"] = 42
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(
            tmp_path, transport=transport,
            config=make_config(checkpoint_every_blocks=1))
        pool_factory(FakePool())
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)

    @pytest.mark.parametrize("corrupt,reason", [
        (lambda r: {**r, "slot": int(r["slot"]) + 1000},
         rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE),
        (lambda r: {**r, "scan_version": 999},
         rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE),
        (lambda r: {**r, "blockhash": ""},
         rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE),
        (lambda r: {**r, "entries": list(reversed(r["entries"]))
                    + list(r["entries"])},
         rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE),
        (lambda r: {**r, "status": rbs.BLOCK_SCAN_UNAVAILABLE, "entries": []},
         rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE),
    ])
    def test_lying_worker_results_fail_closed(
            self, tmp_path, pool_factory, corrupt: Any, reason: str) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        pool_factory(FakePool(corrupt=corrupt))
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == reason
        assert not coordinator.is_proven()
        assert not cursor.state.overlap_proven_generation


class TestPoolFailureBehaviour:
    def test_pool_startup_failure_pauses_recovery_retryably(
            self, tmp_path, monkeypatch) -> None:
        def _explode(**_kwargs: Any) -> Any:
            raise BlockScanPoolError("RPC_APPLY_POOL_START_FAILED")

        monkeypatch.setattr(rgr, "BoundedBlockScanPool", _explode)
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.is_paused()
        assert coordinator.pause_reason() == (
            rgr.TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
        assert not coordinator.is_proven()

    def test_exhausted_worker_restarts_pause_retryably_with_prefix_intact(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(
            tmp_path, transport=transport,
            config=make_config(checkpoint_every_blocks=1))
        pool_factory(FakePool(
            fail_after_batches=2, fail_reason=POOL_RESTARTS_EXHAUSTED))
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.is_paused()
        assert coordinator.pause_reason() == (
            rgr.TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
        # Durable contiguous prefix survives; nothing beyond it is claimed.
        completed = coordinator.snapshot()["last_completed_slot"]
        assert completed is not None and completed < OVERLAP_SLOT
        assert coordinator.snapshot()["overlap_proof_state"] != (
            rgr.OVERLAP_PROVEN)
        assert not cursor.state.overlap_proven_generation

    def test_missing_worker_result_ends_the_pass_retryably(
            self, tmp_path, pool_factory) -> None:
        """A batch whose results never arrive must never stall the pass."""

        class SilentPool(FakePool):
            def poll(self, timeout: float = 0.0) -> List[Dict[str, Any]]:
                self._pending = []
                return []

        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(
            tmp_path, transport=transport,
            config=make_config(rpc_worker_timeout_seconds=1.0))
        pool_factory(SilentPool())
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.is_paused()
        assert coordinator.pause_reason() == (
            rgr.TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
        assert coordinator.snapshot()["last_completed_slot"] is None
        assert not cursor.state.overlap_proven_generation

    def test_transport_without_raw_bodies_refuses_to_run_the_serial_path(
            self, tmp_path) -> None:
        class DecodedOnlyTransport(RawFixtureTransport):
            supports_raw_bodies = False

        cursor = make_cursor(tmp_path)
        transport = DecodedOnlyTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        open_episode(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.is_paused()
        assert coordinator.pause_reason() == (
            rgr.TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
        assert transport.block_requests == []

    def test_worker_death_triggers_one_bounded_restart(self) -> None:
        pool = BoundedBlockScanPool(
            processes=1, queue_bound=2, batch_size=1,
            worker_timeout_seconds=30.0, program_ids=PROGRAM_IDS)
        try:
            pool._outstanding[999] = (pool._monotonic(), [(101, b"{}")])
            for process in pool._workers:
                process.terminate()
                process.join(timeout=5.0)
            pool.poll(timeout=0.05)
            assert pool.restarts == 1
            assert pool.worker_failures == 1
            assert pool.batches_retried == 1
            assert all(p.is_alive() for p in pool._workers)
        finally:
            pool.close()

    def test_task_timeout_triggers_a_bounded_restart(self) -> None:
        clock = {"now": 0.0}
        pool = BoundedBlockScanPool(
            processes=1, queue_bound=2, batch_size=1,
            worker_timeout_seconds=5.0, program_ids=PROGRAM_IDS,
            monotonic_fn=lambda: clock["now"])
        try:
            pool._outstanding[1] = (0.0, [(101, b"{}")])
            clock["now"] = 100.0
            pool.poll(timeout=0.0)
            assert pool.restarts == 1
            assert pool.batches_retried == 1
        finally:
            pool.close()

    def test_repeated_failures_exhaust_the_restart_budget(self) -> None:
        clock = {"now": 0.0}
        pool = BoundedBlockScanPool(
            processes=1, queue_bound=2, batch_size=1,
            worker_timeout_seconds=5.0, program_ids=PROGRAM_IDS,
            max_restarts=1, monotonic_fn=lambda: clock["now"])
        try:
            pool._outstanding[1] = (0.0, [(101, b"{}")])
            clock["now"] = 100.0
            pool.poll(timeout=0.0)
            assert pool.restarts == 1
            pool._outstanding[2] = (100.0, [(102, b"{}")])
            clock["now"] = 400.0
            with pytest.raises(BlockScanPoolError) as raised:
                pool.poll(timeout=0.0)
            assert raised.value.reason == POOL_RESTARTS_EXHAUSTED
        finally:
            pool.close()

    def test_queue_capacity_is_never_exceeded(self) -> None:
        pool = BoundedBlockScanPool(
            processes=1, queue_bound=2, batch_size=1,
            worker_timeout_seconds=30.0, program_ids=PROGRAM_IDS)
        try:
            pool._outstanding[1] = (pool._monotonic(), [])
            pool._outstanding[2] = (pool._monotonic(), [])
            assert pool.try_submit([(101, b"{}")]) is False
            assert pool.outstanding_batches == 2
        finally:
            pool._outstanding.clear()
            pool.close()


class TestInterruptionAndResume:
    def test_interruption_preserves_the_last_contiguous_checkpoint(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(
            tmp_path, transport=transport,
            config=make_config(checkpoint_every_blocks=1))
        pool_factory(FakePool())
        open_episode(coordinator, cursor)
        original = coordinator._process_bridged_update

        def _traced(**kwargs: Any) -> Any:
            if int(kwargs["slot"]) >= 104:
                coordinator.request_stop()
            return original(**kwargs)

        coordinator._process_bridged_update = _traced
        assert not coordinator.run_backfill()
        completed = coordinator.snapshot()["last_completed_slot"]
        assert completed is not None and 102 <= completed <= 104
        assert not coordinator.is_proven()
        assert not cursor.state.overlap_proven_generation

    def test_restart_resumes_after_the_last_contiguous_checkpoint(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        blocks = build_chain(PRODUCED)
        first = RawFixtureTransport(produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(
            tmp_path, transport=first,
            config=make_config(checkpoint_every_blocks=1))
        pool_factory(FakePool())
        open_episode(coordinator, cursor)
        original = coordinator._process_bridged_update

        def _traced(**kwargs: Any) -> Any:
            if int(kwargs["slot"]) >= 104:
                coordinator.request_stop()
            return original(**kwargs)

        coordinator._process_bridged_update = _traced
        assert not coordinator.run_backfill()
        completed = int(coordinator.snapshot()["last_completed_slot"])

        # A fresh process resumes from the durable prefix and only re-fetches
        # blocks ABOVE it.
        second = RawFixtureTransport(produced=PRODUCED, blocks=blocks)
        resumed = make_coordinator(
            tmp_path, transport=second,
            config=make_config(checkpoint_every_blocks=1))
        ok, detail = resumed.begin_or_resume_episode(cursor_store=cursor)
        assert ok, detail
        assert resumed.run_backfill()
        assert min(second.block_requests) > completed
        assert resumed.is_proven()

    def test_duplicate_migration_and_candidate_application_stays_zero(
            self, tmp_path, pool_factory) -> None:
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        pool_factory(FakePool(reverse=True))
        open_episode(coordinator, cursor)
        applied: List[Dict[str, Any]] = []
        assert coordinator.run_backfill(
            apply_candidate_fn=lambda candidate: (
                applied.append(dict(candidate)) or True))
        relevant = coordinator.snapshot()["transactions_relevant"]
        assert relevant == len(PRODUCED)
        identities = [
            build_transaction_skip_identity(slot, OVERLAP_SIG, 1)
            for slot in [OVERLAP_SLOT]]
        assert len(set(identities)) == len(identities)
        # A second pass over the very same blocks applies nothing twice.
        assert coordinator.run_backfill()
        assert coordinator.snapshot()["transactions_relevant"] == relevant


class TestClosedSetsAndIsolation:
    def test_pool_unavailability_is_a_legal_retryable_pause(self) -> None:
        assert rgr.TERMINAL_RPC_APPLY_POOL_UNAVAILABLE in (
            rgr.RECOVERY_TERMINAL_REASONS)
        assert rgr.PAUSE_RPC_APPLY_POOL_UNAVAILABLE in (
            rgr.RECOVERY_RETRYABLE_PAUSE_REASONS)

    def test_no_other_reason_became_retryable(self) -> None:
        assert set(rgr.RECOVERY_RETRYABLE_PAUSE_REASONS) == {
            rgr.TERMINAL_RPC_BACKFILL_TIMEOUT,
            rgr.TERMINAL_RPC_APPLY_POOL_UNAVAILABLE,
        }
        for reason in (rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT,
                       rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE,
                       rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE,
                       rgr.TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN,
                       rgr.TERMINAL_RECOVERY_STATE_QUARANTINED):
            assert reason not in rgr.RECOVERY_RETRYABLE_PAUSE_REASONS

    def test_recovery_path_constructs_no_delivery_transport(
            self, tmp_path, pool_factory, monkeypatch) -> None:
        import PHX2.free_tier_producer.free_tier_session as session

        for name in ("TelegramTransport", "PrivateDiscordTransport",
                     "build_telegram_transport", "post_private_discord"):
            if hasattr(session, name):
                monkeypatch.setattr(session, name, lambda *a, **k: (
                    _ for _ in ()).throw(
                        AssertionError("DELIVERY_CONSTRUCTED_IN_RECOVERY")))
        cursor = make_cursor(tmp_path)
        transport = RawFixtureTransport(
            produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, transport=transport)
        pool_factory(FakePool())
        open_episode(coordinator, cursor)
        assert coordinator.run_backfill()

    def test_canonical_entrypoints_are_windows_spawn_safe(self) -> None:
        """Spawn re-imports the main module in every worker.

        Without a ``__main__`` guard on the canonical entrypoints, starting the
        decode/scan pool would re-run the PRODUCER inside each worker.
        """

        import ast
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        entrypoints = [
            repo_root / "main.py",
            repo_root / "PHX2" / "main.py",
            repo_root / "PHX2" / "free_tier_producer" / "free_tier_session.py",
        ]
        for path in entrypoints:
            assert path.is_file(), path
            tree = ast.parse(path.read_text(encoding="utf-8"))
            guarded = any(
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name)
                and node.test.left.id == "__name__"
                for node in tree.body)
            assert guarded, f"{path} has no __main__ guard"

    def test_production_default_enables_the_pool(self) -> None:
        """The dataclass stays serial; PRODUCTION must not."""

        import argparse

        from PHX2.free_tier_producer import free_tier_session as session

        assert rgr.RpcGapRecoveryConfig(
            mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment="confirmed").rpc_apply_processes == 1
        built = session._gap_recovery_config_from_args(
            argparse.Namespace(grpc_gap_recovery="rpc_backfill",
                               rpc_recovery_commitment="confirmed"))
        assert built.rpc_apply_processes > 1
        assert rgr.validate_rpc_gap_recovery_config(built) == []

    def test_pool_settings_appear_in_the_redaction_safe_snapshot(self) -> None:
        snapshot = make_config().snapshot()
        assert snapshot["rpc_apply_processes"] == 4
        assert snapshot["rpc_apply_queue_bound"] == 4
        assert snapshot["rpc_apply_batch_size"] == 2
        for value in snapshot.values():
            assert not isinstance(value, (bytes, bytearray))
        blob = json.dumps(snapshot).lower()
        for token in ("://", "token", "secret", "bearer", "api_key",
                      "apikey", "password", "@"):
            assert token not in blob
