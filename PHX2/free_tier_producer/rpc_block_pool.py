"""A bounded, Windows-spawn-safe process pool for pure block decode/scan.

The pool moves ONLY pure work off the authoritative process: JSON decode,
block structural parsing, transaction scanning and the mechanical projection
of relevant transactions.  It owns no durable state and can reach none --
workers receive bytes, a slot and immutable program identifiers, and return
plain data.

Every dimension is bounded on purpose: worker count, input queue depth, output
queue depth, batch size, per-batch timeout and the number of times the pool may
be rebuilt.  A pool that cannot be built or cannot be kept healthy inside those
bounds raises; the caller pauses recovery retryably with its durable
contiguous prefix intact rather than silently falling back to the known
diverging serial path.
"""

from __future__ import annotations

import multiprocessing
import os
import queue as _queue
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PHX2.free_tier_producer.rpc_block_scan import scan_block_task

#: Hard ceilings. A typo can slow a run down; it can never open an unbounded
#: number of processes or retain an unbounded number of block payloads.
RPC_APPLY_PROCESSES_MAX = 16
RPC_APPLY_QUEUE_BOUND_MAX = 64
RPC_APPLY_BATCH_SIZE_MAX = 64
RPC_WORKER_TIMEOUT_SECONDS_MAX = 600.0
#: How many times the pool may be rebuilt after a worker crash/hang before the
#: episode is declared unhealthy.
RPC_APPLY_MAX_POOL_RESTARTS = 3

POOL_START_FAILED = "RPC_APPLY_POOL_START_FAILED"
POOL_WORKER_FAILED = "RPC_APPLY_POOL_WORKER_FAILED"
POOL_TIMEOUT = "RPC_APPLY_POOL_TIMEOUT"
POOL_RESTARTS_EXHAUSTED = "RPC_APPLY_POOL_RESTARTS_EXHAUSTED"


class BlockScanPoolError(RuntimeError):
    """The pool could not do its work inside its configured bounds."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = str(reason)


def default_apply_processes(cpu_count: Optional[int] = None) -> int:
    """Conservative default derived from local CPU count."""

    cores = cpu_count if isinstance(cpu_count, int) and cpu_count > 0 else (
        os.cpu_count() or 2)
    return max(2, min(8, cores - 2))


def scan_worker_loop(task_queue: Any, result_queue: Any,
                     program_ids: Sequence[str]) -> None:
    """Worker entrypoint. Top level and pickle-safe for ``spawn``.

    Pure: it reads batches of ``(batch_id, [(slot, payload), ...])``, scans
    them and writes ``(batch_id, [result, ...])``.  It opens no ledger, no
    checkpoint, no transport and no delivery channel, and it never returns a
    live object.
    """

    ids = tuple(str(value) for value in program_ids)
    while True:
        try:
            item = task_queue.get()
        except (EOFError, OSError):
            return
        if item is None:
            return
        batch_id, tasks = item
        results = []
        for slot, payload in tasks:
            results.append(scan_block_task({
                "slot": slot, "payload": payload, "program_ids": ids}))
        try:
            result_queue.put((batch_id, results))
        except (EOFError, OSError):
            return


class BoundedBlockScanPool:
    """Bounded worker pool with explicit queues, timeouts and restarts."""

    def __init__(self, *, processes: int, queue_bound: int, batch_size: int,
                 worker_timeout_seconds: float,
                 program_ids: Sequence[str],
                 max_restarts: int = RPC_APPLY_MAX_POOL_RESTARTS,
                 monotonic_fn: Any = time.monotonic) -> None:
        if not isinstance(processes, int) or isinstance(processes, bool) \
                or processes < 1 or processes > RPC_APPLY_PROCESSES_MAX:
            raise BlockScanPoolError(POOL_START_FAILED)
        if not isinstance(queue_bound, int) or isinstance(queue_bound, bool) \
                or queue_bound < 1 or queue_bound > RPC_APPLY_QUEUE_BOUND_MAX:
            raise BlockScanPoolError(POOL_START_FAILED)
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) \
                or batch_size < 1 or batch_size > RPC_APPLY_BATCH_SIZE_MAX:
            raise BlockScanPoolError(POOL_START_FAILED)
        if isinstance(worker_timeout_seconds, bool) \
                or not isinstance(worker_timeout_seconds, (int, float)) \
                or worker_timeout_seconds <= 0 \
                or worker_timeout_seconds > RPC_WORKER_TIMEOUT_SECONDS_MAX:
            raise BlockScanPoolError(POOL_START_FAILED)
        self._processes = int(processes)
        self._queue_bound = int(queue_bound)
        self.batch_size = int(batch_size)
        self._timeout = float(worker_timeout_seconds)
        self._program_ids = tuple(str(value) for value in program_ids)
        self._max_restarts = max(0, int(max_restarts))
        self._monotonic = monotonic_fn
        self._ctx = multiprocessing.get_context("spawn")
        self._workers: List[Any] = []
        self._task_queue: Any = None
        self._result_queue: Any = None
        #: batch_id -> (submitted_monotonic, tasks). Bounded by construction:
        #: the caller may never have more than ``queue_bound`` batches out.
        self._outstanding: Dict[int, Tuple[float, List[Tuple[int, bytes]]]] = {}
        self._next_batch_id = 1
        self.restarts = 0
        self.worker_failures = 0
        self.batches_retried = 0
        self._closed = False
        self._start()

    # -- lifecycle --------------------------------------------------------

    def _start(self) -> None:
        try:
            self._task_queue = self._ctx.Queue(maxsize=self._queue_bound)
            self._result_queue = self._ctx.Queue(maxsize=self._queue_bound)
            workers = []
            for _ in range(self._processes):
                process = self._ctx.Process(
                    target=scan_worker_loop,
                    args=(self._task_queue, self._result_queue,
                          self._program_ids),
                    daemon=True)
                process.start()
                workers.append(process)
            self._workers = workers
        except Exception:
            self._hard_stop()
            raise BlockScanPoolError(POOL_START_FAILED)

    def _hard_stop(self) -> None:
        for process in self._workers:
            try:
                if process.is_alive():
                    process.terminate()
            except Exception:
                pass
        for process in self._workers:
            try:
                process.join(timeout=5.0)
            except Exception:
                pass
        self._workers = []
        for name in ("_task_queue", "_result_queue"):
            handle = getattr(self, name, None)
            if handle is None:
                continue
            try:
                handle.close()
                handle.join_thread()
            except Exception:
                pass
            setattr(self, name, None)

    def close(self) -> None:
        """Deterministic shutdown: sentinels, bounded join, then terminate."""

        if self._closed:
            return
        self._closed = True
        for _ in self._workers:
            try:
                self._task_queue.put_nowait(None)
            except Exception:
                break
        deadline = self._monotonic() + 5.0
        for process in self._workers:
            remaining = max(0.0, deadline - self._monotonic())
            try:
                process.join(timeout=remaining)
            except Exception:
                pass
        self._hard_stop()

    def __enter__(self) -> "BoundedBlockScanPool":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # -- health -----------------------------------------------------------

    @property
    def outstanding_batches(self) -> int:
        return len(self._outstanding)

    @property
    def capacity_batches(self) -> int:
        return self._queue_bound

    def _restart(self, reason: str) -> None:
        """Rebuild the pool and re-submit every outstanding batch. Bounded."""

        if self.restarts >= self._max_restarts:
            self._hard_stop()
            raise BlockScanPoolError(POOL_RESTARTS_EXHAUSTED)
        self.restarts += 1
        self.worker_failures += 1
        pending = dict(self._outstanding)
        self._closed = False
        self._hard_stop()
        self._start()
        self._outstanding = {}
        now = self._monotonic()
        for batch_id, (_submitted, tasks) in sorted(pending.items()):
            self._outstanding[batch_id] = (now, tasks)
            self.batches_retried += 1
            try:
                self._task_queue.put((batch_id, tasks), timeout=self._timeout)
            except Exception:
                self._hard_stop()
                raise BlockScanPoolError(reason)

    def _check_health(self) -> None:
        if not self._outstanding:
            return
        if any(not process.is_alive() for process in self._workers):
            self._restart(POOL_WORKER_FAILED)
            return
        now = self._monotonic()
        oldest = min(submitted for submitted, _tasks
                     in self._outstanding.values())
        if now - oldest > self._timeout:
            self._restart(POOL_TIMEOUT)

    # -- work -------------------------------------------------------------

    def try_submit(self, tasks: Sequence[Tuple[int, bytes]]) -> bool:
        """Enqueue one batch without blocking. False when the queue is full."""

        if self._closed or not tasks:
            return False
        if len(self._outstanding) >= self._queue_bound:
            return False
        batch_id = self._next_batch_id
        payload = list(tasks)
        try:
            self._task_queue.put_nowait((batch_id, payload))
        except _queue.Full:
            return False
        except Exception:
            raise BlockScanPoolError(POOL_WORKER_FAILED)
        self._next_batch_id += 1
        self._outstanding[batch_id] = (self._monotonic(), payload)
        return True

    def poll(self, timeout: float = 0.05) -> List[Dict[str, Any]]:
        """Collect one completed batch, or ``[]``. Never blocks unbounded."""

        if not self._outstanding:
            return []
        try:
            batch_id, results = self._result_queue.get(
                timeout=max(0.0, float(timeout)))
        except _queue.Empty:
            self._check_health()
            return []
        except (EOFError, OSError):
            self._restart(POOL_WORKER_FAILED)
            return []
        self._outstanding.pop(batch_id, None)
        return list(results)


__all__ = (
    "RPC_APPLY_PROCESSES_MAX", "RPC_APPLY_QUEUE_BOUND_MAX",
    "RPC_APPLY_BATCH_SIZE_MAX", "RPC_WORKER_TIMEOUT_SECONDS_MAX",
    "RPC_APPLY_MAX_POOL_RESTARTS", "POOL_START_FAILED", "POOL_WORKER_FAILED",
    "POOL_TIMEOUT", "POOL_RESTARTS_EXHAUSTED", "BlockScanPoolError",
    "BoundedBlockScanPool", "default_apply_processes", "scan_worker_loop",
)
