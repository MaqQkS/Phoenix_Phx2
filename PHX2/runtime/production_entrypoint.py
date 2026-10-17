"""Command-line surface for ``python main.py``."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .production_supervisor import (
    DEFAULT_HOURS,
    ProductionConfig,
    ProductionPaths,
    ProductionRefusal,
    ProductionSupervisor,
    fresh_run_dir,
    read_status,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="PHX2 Telegram production pipeline",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help="bounded production duration (default: 24 hours)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="read current production status without starting or modifying anything",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="use or inspect an explicit existing run directory",
    )
    return parser


def _value(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    return str(value)


def print_status(status: Mapping[str, Any]) -> None:
    print(f"PHX2_ACTIVE={_value(status.get('active'))}")
    print(f"LOCK_STATE={_value(status.get('lock_state'))}")
    print(f"RUN_DIR={_value(status.get('run_dir'))}")
    print(f"SUPERVISOR_PID={_value(status.get('supervisor_pid'))}")
    processes = status.get("processes")
    processes = processes if isinstance(processes, dict) else {}
    for role in ("producer", "paper", "dashboard"):
        entry = processes.get(role)
        entry = entry if isinstance(entry, dict) else {}
        print(
            f"{role.upper()}_PID={_value(entry.get('pid'))} "
            f"STATE={_value(entry.get('state'))}"
        )
    print(f"PAPER_STATUS={_value(status.get('paper_status'))}")
    print(
        "PAPER_RESTARTS="
        f"{_value(status.get('paper_restart_attempts'))}/"
        f"{_value(status.get('paper_restart_limit'))} "
        f"LAST_EXIT={_value(status.get('paper_last_exit_code'))}"
    )
    console = status.get("operator_console")
    console = console if isinstance(console, dict) else {}
    print(
        f"OPERATOR_CONSOLE_PID={_value(console.get('pid'))} "
        f"STATE={_value(console.get('state'))}"
    )
    for key in (
        "delivery_transport",
        "telegram_configured",
        "telegram_attempts",
        "telegram_sent_ok",
        "telegram_failures",
        "discord_attempts",
        "primary_stream_status",
        "verifier_stream_status",
        "lp_integrity_mode",
        "grpc_status",
        "active_streams",
        "max_active_streams",
        "accepted_candidates",
        "queue_depth",
        "watchlist_count",
        "watchlist_active_capacity",
        "watchlist_terminal_history",
        "watchlist_capacity_rejections",
        "market_calls",
        "market_scheduler",
        "send_attempts",
        "sent_ok_count",
        "fee_gate_counts",
        "lp_integrity_counts",
        "composite_blocks",
        "latest_heartbeat_age_s",
        "stop_reason",
    ):
        print(f"{key.upper()}={_value(status.get(key))}")


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    paths: Optional[ProductionPaths] = None,
    supervisor_type: type[ProductionSupervisor] = ProductionSupervisor,
) -> int:
    args = build_parser().parse_args(argv)
    production_paths = paths or ProductionPaths()
    if args.status:
        try:
            print_status(
                read_status(production_paths, run_dir=args.run_dir)
            )
        except ProductionRefusal as exc:
            print(f"[REFUSED] {exc.reason}")
            return 2
        return 0
    run_dir = args.run_dir or fresh_run_dir(production_paths.runtime_root)
    config = ProductionConfig(
        run_dir=run_dir.resolve(),
        hours=float(args.hours),
        paths=production_paths,
    )
    try:
        result = supervisor_type(config).run()
    except ProductionRefusal as exc:
        print(f"[REFUSED] {exc.reason}")
        return 2
    print(f"[FINAL] stop_reason={result.stop_reason}")
    print(f"[FINAL] run={result.run_dir}")
    print(
        "[FINAL] "
        f"sent_ok={result.sent_ok_count} "
        f"active_streams={result.active_streams} "
        f"max_active_streams={result.max_active_streams} "
        f"forced_terminations={result.forced_termination_count}"
    )
    return int(result.exit_code)


__all__ = ("build_parser", "main", "print_status")
