"""Live ACTIVE paper trading over growing PHX2 artifact directories.

Watches one or more directories that a PHX2 discovery/recheck process is
appending JSONL records to, and actively paper-trades the stream: new
candidates are audited and entered per strategy, open positions are
re-priced and re-audited on every new record, the BALA_PLAN Tier/DCA
ladder adds legs when a coin moves Tier 1 -> 2 -> 3 while still healthy,
and TP/SL/trailing/max-hold/rug/data-lost exits fire as conditions
trigger. Dashboard artifacts (paper_summary.json, live_monitor.json,
heartbeat.json, ...) refresh continuously.

    # active watch (default), Ctrl+C to stop gracefully:
    python -m PHX2.scripts.phx2_live_paper_trade \
        --config C:\\Users\\BalaC\\phx2_paper_trading\\paper_config.json \
        --inputs <growing artifact dir> --run-id live_paper_01

    # safe bounded live test:
    ... --max-runtime-seconds 120
    # single backlog pass (tests):
    ... --once

Restart-safe: with a stable --run-id, open positions reload from the run's
ledger and input byte offsets reload from input_checkpoints.json, so a
restart continues managing the same book without reprocessing records.

This stage starts no ping runtime and opens no network connection: input
files are read-only and only paper ledgers are written. The snapshot
source is an injectable adapter (see PHX2.paper_trading.live), so a
future free-tier enrichment source can be attached without engine changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct file invocation support
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PHX2.paper_trading.config import (
    ConfigError,
    END_OF_STREAM_LEAVE_OPEN,
    default_config,
    load_config,
)
from PHX2.paper_trading.engine import MODE_LIVE_PAPER, PaperTradingEngine
from PHX2.paper_trading.live import restore_checkpoints, run_live_loop
from PHX2.paper_trading.pricing import TailingSnapshotSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phx2_live_paper_trade",
        description="Actively paper trade a growing PHX2 artifact stream "
                    "(simulation only; input files are read-only).")
    parser.add_argument("--config", help="paper trading config JSON path")
    parser.add_argument("--inputs", nargs="+", required=True,
                        help="directories/files/globs to watch")
    parser.add_argument("--run-id", default="live_paper",
                        help="stable run id (enables restart resume)")
    parser.add_argument("--out-root", help="override run.output_root")
    parser.add_argument("--seed", type=int, help="override run.random_seed")
    parser.add_argument("--poll-seconds", type=float, default=5.0,
                        help="input poll interval (default 5s)")
    parser.add_argument("--max-runtime-seconds", type=float, default=None,
                        help="stop after this many seconds (safe test runs)")
    parser.add_argument("--once", action="store_true",
                        help="process the current backlog once and exit")
    parser.add_argument("--heartbeat-seconds", type=float, default=60.0,
                        help="console/artifact heartbeat interval")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv=None) -> int:
    import time

    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config) if args.config else default_config()
    except ConfigError as exc:
        print("CONFIG INVALID:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    if args.out_root:
        config.run.output_root = args.out_root
    if args.seed is not None:
        config.run.random_seed = args.seed
    config.run.run_id = args.run_id
    # Live paper never force-closes at shutdown; positions stay OPEN and
    # resume management on the next start.
    config.run.end_of_stream_policy = END_OF_STREAM_LEAVE_OPEN

    engine = PaperTradingEngine(config, mode=MODE_LIVE_PAPER, resume=True,
                                quiet=args.quiet, wall_clock=time.time)
    engine.watch_inputs = [str(p) for p in args.inputs]
    source = TailingSnapshotSource(args.inputs)
    restored = restore_checkpoints(engine, source)

    print(f"live active paper trading: run_dir={engine.run_dir}")
    print(f"  watching {len(args.inputs)} input path(s), "
          f"poll every {args.poll_seconds:g}s"
          + (f", max runtime {args.max_runtime_seconds:g}s"
             if args.max_runtime_seconds else "")
          + (f", resumed {restored} input checkpoint(s)" if restored else "")
          + " -- Ctrl+C stops gracefully")

    result = run_live_loop(
        engine, source,
        poll_seconds=args.poll_seconds,
        max_runtime_seconds=args.max_runtime_seconds,
        once=args.once,
        wall_heartbeat_seconds=args.heartbeat_seconds,
    )
    engine.finalize()
    engine.close()
    print(f"live loop stopped: {result.stop_reason} "
          f"(polls={result.polls}, snapshots={result.snapshots_processed}, "
          f"input_errors={result.input_errors})")
    print(f"artifacts: {engine.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
