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
    # bounded main pass plus final catch-up (tests):
    ... --once

Restart-safe: with a stable --run-id, positions, strategy state, input
checkpoints and the notification outbox reload from canonical paper_state.json.
Legacy ledgers without canonical state require a reviewed migration.

Input files are read-only. Paper fills are simulated locally. Notifications
remain outbox-only unless explicitly armed with a reviewed code identity,
separate paper credentials, destination confirmation and a bounded message
budget. This script starts no discovery runtime or live trading execution.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
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
from PHX2.paper_trading.state import PaperRunLease


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
    parser.add_argument("--stop-file", type=Path,
                        help="cooperative supervisor stop seam")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--reviewed-head")
    parser.add_argument("--reviewed-source-digest")
    parser.add_argument("--enable-paper-telegram", action="store_true")
    parser.add_argument("--confirm-paper-destination")
    parser.add_argument("--paper-destination-sha256")
    parser.add_argument("--max-paper-messages", type=int, default=0)
    parser.add_argument("--producer-streams-only", action="store_true", default=True,
                        help="required production stream allowlist (always enabled)")
    parser.add_argument("--allow-input-rollover", action="store_true",
                        help="allow adding producer roots on resume; all prior roots must remain")
    return parser


def paper_transport(args, environ):
    """Construct delivery only after explicit arming, with separate paper credentials."""
    if not args.enable_paper_telegram:
        if args.max_paper_messages != 0:
            raise ValueError("PAPER_MESSAGE_BUDGET_WITHOUT_ARMING")
        return None
    if (args.confirm_paper_destination != "PHX2_PAPER_CANARY"
            or not 1 <= args.max_paper_messages <= 20):
        raise ValueError("PAPER_TELEGRAM_ARMING_REQUIRED")
    chat = environ.get("PHX2_PAPER_TELEGRAM_CHAT_ID", "").strip()
    digest = hashlib.sha256(chat.encode("utf-8")).hexdigest()
    if not chat or args.paper_destination_sha256 != digest:
        raise ValueError("PAPER_DESTINATION_CONFIRMATION_REQUIRED")
    from dataclasses import replace
    from PHX2.delivery.telegram_config import TelegramConfig
    from PHX2.delivery.telegram_transport import TelegramTransport
    config = TelegramConfig.from_mapping({
        "PHX2_DELIVERY_TRANSPORT": "telegram", "PHX2_TELEGRAM_ENABLED": "true",
        "PHX2_DISCORD_ENABLED": "false", "PHX2_TELEGRAM_PARSE_MODE": "HTML",
        "PHX2_TELEGRAM_DISABLE_LINK_PREVIEW": "true",
        "PHX2_TELEGRAM_BOT_TOKEN": environ.get("PHX2_PAPER_TELEGRAM_BOT_TOKEN", ""),
        "PHX2_TELEGRAM_CHAT_ID": chat,
    })
    return TelegramTransport(replace(config, destination_alias="PHX2_PAPER_CANARY:" + digest),
                             max_retries=0)


def main(argv=None) -> int:
    import time

    args = build_parser().parse_args(argv)
    from PHX2.scripts.phx2_paper_preflight import _safe_path, _overlaps, code_identity
    try:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.run_id):
            raise ValueError("PAPER_RUN_ID_INVALID")
        if any(not math.isfinite(value) or value <= 0 for value in (
                args.poll_seconds, args.heartbeat_seconds)):
            raise ValueError("PAPER_LOOP_BOUNDS_INVALID")
        if not args.once and (args.max_runtime_seconds is None
                or not math.isfinite(args.max_runtime_seconds) or args.max_runtime_seconds <= 0):
            raise ValueError("BOUNDED_PAPER_RUNTIME_REQUIRED")
        if not args.once or args.enable_paper_telegram:
            identity = code_identity(Path(__file__).resolve().parents[2])
            if (args.reviewed_head != identity["head"]
                    or args.reviewed_source_digest != identity["source_sha256"]):
                raise ValueError("PAPER_REVIEWED_CODE_PIN_REQUIRED")
        for path in args.inputs:
            _safe_path(path)
        if args.config:
            _safe_path(args.config, existing=True)
        if args.out_root:
            _safe_path(args.out_root)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
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

    try:
        run_dir = _safe_path(str(Path(config.run.output_root) / config.run.run_id))
        if any(_overlaps(run_dir, _safe_path(path)) for path in args.inputs):
            raise ValueError("PAPER_INPUT_OUTPUT_OVERLAP")
        transport = paper_transport(args, os.environ)
        with PaperRunLease(run_dir):
            return _run(args, config, transport)
    except (ValueError, RuntimeError) as exc:
        print(type(exc).__name__ + ": PAPER_RUN_REFUSED", file=sys.stderr)
        return 2
    finally:
        if "transport" in locals() and transport is not None:
            transport.close()


def _run(args, config, transport=None):
    import time
    started = time.monotonic()
    engine = PaperTradingEngine(config, mode=MODE_LIVE_PAPER, resume=True,
                                quiet=args.quiet, wall_clock=time.time)
    engine.watch_inputs = [str(p) for p in args.inputs]
    try:
        source = TailingSnapshotSource(args.inputs, producer_streams_only=True,
                                      allow_input_rollover=args.allow_input_rollover)
        restored = restore_checkpoints(engine, source)
    except BaseException:
        engine.close()
        raise

    print(f"live active paper trading: run_dir={engine.run_dir}")
    print(f"  watching {len(args.inputs)} input path(s), "
          f"poll every {args.poll_seconds:g}s"
          + (f", max runtime {args.max_runtime_seconds:g}s"
             if args.max_runtime_seconds else "")
          + (f", resumed {restored} input checkpoint(s)" if restored else "")
          + " -- Ctrl+C stops gracefully")

    sent = 0
    def delivery_stopped():
        return ((args.stop_file is not None and args.stop_file.exists())
                or (args.max_runtime_seconds is not None
                    and time.monotonic() - started >= args.max_runtime_seconds))
    def after_commit(current):
        nonlocal sent
        if delivery_stopped():
            return
        if transport is not None and sent < args.max_paper_messages:
            sent += current.notification_outbox.dispatch_pending(transport,
                authorized=True, destination_alias=transport._config.destination_alias,
                max_messages=args.max_paper_messages - sent,
                should_stop=delivery_stopped)
    try:
        result = run_live_loop(
            engine, source, poll_seconds=args.poll_seconds,
            max_runtime_seconds=args.max_runtime_seconds, once=args.once,
            should_stop=((lambda: args.stop_file.exists())
                         if args.stop_file is not None else (lambda: False)),
            wall_heartbeat_seconds=args.heartbeat_seconds, after_commit=after_commit,
        )
        engine.finalize()
    finally:
        engine.close()
    print(f"live loop stopped: {result.stop_reason} "
          f"(polls={result.polls}, snapshots={result.snapshots_processed}, "
          f"input_errors={result.input_errors})")
    print(f"artifacts: {engine.run_dir}")
    return 2 if any(key.endswith("_error") for key in result.details) else 0


if __name__ == "__main__":
    raise SystemExit(main())
