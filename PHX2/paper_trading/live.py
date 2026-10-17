"""The live active paper trading loop.

Drives a :class:`PaperTradingEngine` from a snapshot source (by default the
tailing JSONL reader over growing PHX2 artifact directories):

    poll -> normalize new records -> update every strategy ->
    re-audit / DCA / exit open positions -> checkpoint input offsets ->
    refresh dashboard artifacts -> heartbeat -> sleep -> repeat

The loop is a plain function with injectable clock/sleep/stop hooks so
tests can run it deterministically, and the console script stays a thin
argparse wrapper. The snapshot source is an injectable adapter: anything
with ``poll() -> (snapshots, errors)`` (and optionally ``offsets`` /
``set_offsets`` for checkpointing) can feed the engine, so a future
free-tier enrichment source can be attached without touching the engine.

Restart safety: every poll atomically commits full engine state and source
identity/offsets to paper_state.json. JSONL ledgers and monitor files are
recoverable projections. A failed batch restores the source checkpoint;
restarts also retain strategy state, random state and delivery outcomes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PHX2.paper_trading.engine import PaperTradingEngine
from PHX2.paper_trading.ledger import CHECKPOINTS_FILE
from PHX2.paper_trading.models import parse_utc, utc_iso


@dataclass
class LiveLoopResult:
    """What one run of the live loop did (for logs and tests)."""

    polls: int = 0
    snapshots_processed: int = 0
    input_errors: int = 0
    stop_reason: str = "UNKNOWN"
    heartbeats: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


def load_checkpoints(run_dir: str) -> Dict[str, Any]:
    """Read the run's input checkpoint file ({} when absent/corrupt)."""
    path = Path(run_dir) / CHECKPOINTS_FILE
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_checkpoints(engine: PaperTradingEngine,
                     source: Any) -> None:
    """Persist the source's per-file offsets + engine event clock."""
    offsets = getattr(source, "offsets", None)
    if offsets is None:
        return
    if not engine._batch_active:
        engine.begin_batch()
    engine.commit_batch(_source_checkpoint(source))
    _write_checkpoint_view(engine, offsets)


def _write_checkpoint_view(engine, offsets):
    engine.ledger.write_json_atomic(CHECKPOINTS_FILE, {
        "artifact": "input_checkpoints",
        "run_id": engine.run_id,
        "offsets": offsets,
        "last_event_ts_utc": utc_iso(engine.now_epoch),
    })


def restore_checkpoints(engine: PaperTradingEngine, source: Any) -> int:
    """Apply saved offsets + event clock to a resumed run.

    Returns the number of restored file offsets.
    """
    if engine._state_generation > 0:
        _restore_source(source, engine.durable_source_checkpoint)
        return len(engine.durable_source_offsets)
    payload = load_checkpoints(engine.run_dir)
    offsets = payload.get("offsets")
    restored = 0
    if isinstance(offsets, dict) and hasattr(source, "set_offsets"):
        source.set_offsets(offsets)
        restored = len(offsets)
    last_ts = parse_utc(payload.get("last_event_ts_utc"))
    if last_ts is not None and (engine.now_epoch is None
                                or last_ts > engine.now_epoch):
        engine.now_epoch = last_ts
    return restored


def _source_checkpoint(source):
    if hasattr(source, "checkpoint_state"):
        return source.checkpoint_state()
    return {"offsets": getattr(source, "offsets", {})}


def _restore_source(source, checkpoint):
    if hasattr(source, "restore_checkpoint"):
        source.restore_checkpoint(checkpoint)
    elif hasattr(source, "set_offsets"):
        source.set_offsets(checkpoint.get("offsets", {}))


def _poll_commit(engine, source, result, *, idle=True, after_commit=None):
    previous = _source_checkpoint(source)
    generation = engine._state_generation
    engine.begin_batch()
    try:
        snapshots, errors = source.poll()
        if errors:
            engine.record_input_errors(errors)
        for snapshot in snapshots:
            engine.process_snapshot(snapshot)
        if not snapshots and idle and engine.wall_clock is not None:
            engine.process_idle_tick(engine.wall_clock())
        engine.commit_batch(_source_checkpoint(source))
    except BaseException:
        engine.rollback_batch()
        _restore_source(source, engine.durable_source_checkpoint
                        if engine._state_generation != generation else previous)
        raise
    result.snapshots_processed += len(snapshots)
    result.input_errors += len(errors)
    _write_checkpoint_view(engine, getattr(source, "offsets", {}))
    if after_commit is not None:
        after_commit(engine)
    return bool(snapshots)


def run_live_loop(engine: PaperTradingEngine,
                  source: Any,
                  poll_seconds: float = 5.0,
                  max_runtime_seconds: Optional[float] = None,
                  once: bool = False,
                  clock: Callable[[], float] = None,
                  sleep: Callable[[float], None] = None,
                  should_stop: Callable[[], bool] = lambda: False,
                  wall_heartbeat_seconds: float = 60.0,
                  after_commit: Optional[Callable[[PaperTradingEngine], None]] = None) -> LiveLoopResult:
    """Run the active live paper loop until stopped.

    * ``once`` processes one bounded poll plus a bounded final catch-up.
    * ``max_runtime_seconds`` stops cooperatively between bounded batches.
    * ``should_stop`` is checked every cycle (graceful shutdown hook).
    * KeyboardInterrupt (Ctrl+C) exits gracefully: checkpoints and
      artifacts are written before returning.
    """
    import time as _time
    clock = clock or _time.monotonic
    sleep = sleep or _time.sleep

    result = LiveLoopResult()
    started = clock()
    last_artifact_refresh = started
    failed = False
    def deliver_after_commit(owner):
        if (after_commit is not None
                and result.stop_reason not in ("STOP_REQUESTED", "INTERRUPTED", "MAX_RUNTIME")
                and not should_stop()
                and (max_runtime_seconds is None or clock() - started < max_runtime_seconds)):
            after_commit(owner)
    try:
        while True:
            if should_stop():
                result.stop_reason = "STOP_REQUESTED"
                break
            if (max_runtime_seconds is not None
                    and clock() - started >= max_runtime_seconds):
                result.stop_reason = "MAX_RUNTIME"
                break
            result.polls += 1
            if _poll_commit(engine, source, result, after_commit=deliver_after_commit):
                engine.write_summary_artifacts()
                # Refresh the open-positions snapshot on every data poll so
                # a crash-restart resumes with fresh trailing-peak state.
                engine.write_monitor_artifacts()

            now = clock()
            if now - last_artifact_refresh >= wall_heartbeat_seconds:
                engine.heartbeat()
                result.heartbeats += 1
                last_artifact_refresh = now

            if once:
                result.stop_reason = "ONCE_COMPLETE"
                break
            if should_stop():
                result.stop_reason = "STOP_REQUESTED"
                break
            if (max_runtime_seconds is not None
                    and now - started >= max_runtime_seconds):
                result.stop_reason = "MAX_RUNTIME"
                break
            sleep(max(0.2, float(poll_seconds)))
    except KeyboardInterrupt:
        result.stop_reason = "INTERRUPTED"
    except BaseException:
        failed = True
        result.stop_reason = "FAILED"
        raise
    finally:
        # Final flush without console echo (the caller's finalize() prints
        # the closing summary once). Runs on EVERY exit path: once-complete,
        # stop-requested, max-runtime, and KeyboardInterrupt.
        if not failed:
            _final_settle(engine, source, result, after_commit=deliver_after_commit)
    return result


def _final_settle(engine: PaperTradingEngine, source: Any,
                  result: LiveLoopResult, after_commit=None) -> None:
    """Flush a final summary + monitor after one bounded catch-up poll.

    First consumes one bounded batch since the loop's last poll, then rewrites
    ``paper_summary.json`` / ``strategy_comparison.*`` and
    ``live_monitor.json`` / ``paper_open_positions.json`` from the same
    settled open-position marks. Total + idempotent: every step is guarded so
    a flush failure can never crash shutdown (the reason is recorded on
    ``result.details`` instead).
    """
    # 1. Consume one bounded catch-up batch. Larger backlogs remain at the
    #    durable checkpoint for the next authorized run.
    try:
        _poll_commit(engine, source, result, idle=False, after_commit=after_commit)
    except Exception as exc:  # a bad final poll must not abort shutdown
        result.details["final_catch_up_error"] = type(exc).__name__
    # 2. Persist offsets, then flush a consistent final summary + monitor.
    try:
        _write_checkpoint_view(engine, engine.durable_source_offsets)
    except Exception as exc:
        result.details["final_checkpoint_error"] = repr(exc)
    try:
        engine.write_summary_artifacts()
        engine.write_monitor_artifacts()
    except Exception as exc:
        result.details["final_flush_error"] = repr(exc)


__all__ = [
    "LiveLoopResult",
    "load_checkpoints",
    "save_checkpoints",
    "restore_checkpoints",
    "run_live_loop",
]
