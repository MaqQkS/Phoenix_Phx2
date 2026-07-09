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

Restart safety: input byte offsets are checkpointed to the run directory
after every poll, and open positions reload from the positions ledger, so
a restarted run continues managing its book without reprocessing records.
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


def run_live_loop(engine: PaperTradingEngine,
                  source: Any,
                  poll_seconds: float = 5.0,
                  max_runtime_seconds: Optional[float] = None,
                  once: bool = False,
                  clock: Callable[[], float] = None,
                  sleep: Callable[[float], None] = None,
                  should_stop: Callable[[], bool] = lambda: False,
                  wall_heartbeat_seconds: float = 60.0) -> LiveLoopResult:
    """Run the active live paper loop until stopped.

    * ``once`` processes the current backlog in a single poll and returns.
    * ``max_runtime_seconds`` bounds the run (safe short live tests).
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
    try:
        while True:
            result.polls += 1
            snapshots, errors = source.poll()
            if errors:
                engine.record_input_errors(errors)
                result.input_errors += len(errors)
            for snapshot in snapshots:
                engine.process_snapshot(snapshot)
            result.snapshots_processed += len(snapshots)

            if snapshots:
                save_checkpoints(engine, source)
                engine.write_summary_artifacts()
                # Refresh the open-positions snapshot on every data poll so
                # a crash-restart resumes with fresh trailing-peak state.
                engine.write_monitor_artifacts()
            else:
                # No new records: advance the engine clock from the wall so
                # max-hold / data-lost exits and heartbeats still fire.
                if engine.wall_clock is not None:
                    engine.process_idle_tick(engine.wall_clock())

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
    finally:
        # Final flush without console echo (the caller's finalize() prints
        # the closing summary once).
        save_checkpoints(engine, source)
        engine.write_summary_artifacts()
        engine.write_monitor_artifacts()
    return result


__all__ = [
    "LiveLoopResult",
    "load_checkpoints",
    "save_checkpoints",
    "restore_checkpoints",
    "run_live_loop",
]
