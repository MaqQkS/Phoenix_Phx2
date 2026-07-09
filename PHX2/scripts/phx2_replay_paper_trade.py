"""Replay PHX2 candidate/ping artifact JSONL through the paper trading engine.

Examples (from the repo root, using the repo .venv python):

    # Write the editable example config once:
    python -m PHX2.scripts.phx2_replay_paper_trade \
        --write-example-config C:\\Users\\BalaC\\phx2_paper_trading\\paper_config.json

    # Replay a production run's candidate artifacts with all strategies:
    python -m PHX2.scripts.phx2_replay_paper_trade \
        --config C:\\Users\\BalaC\\phx2_paper_trading\\paper_config.json \
        --inputs C:\\Users\\BalaC\\phx2_production_private_live\\out\\prod_live_pressure_24h_01

Reads artifact JSONL only; writes paper ledgers under the configured output
root. Reproducible: same inputs + config + seed produce identical ledgers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct file invocation support
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PHX2.paper_trading.config import (
    ConfigError,
    default_config,
    load_config,
    write_example_config,
)
from PHX2.paper_trading.engine import ReplayRunDirError, run_replay
from PHX2.paper_trading.pricing import load_snapshots
from PHX2.paper_trading.reporting import comparison_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phx2_replay_paper_trade",
        description="Replay PHX2 artifact JSONL through the paper trading "
                    "engine (simulation only; writes paper ledgers).")
    parser.add_argument("--config", help="paper trading config JSON path "
                                         "(defaults to built-in defaults)")
    parser.add_argument("--inputs", nargs="+", default=None,
                        help="JSONL files, directories, or globs to replay "
                             "(overrides config input_paths)")
    parser.add_argument("--out-root", help="override run.output_root")
    parser.add_argument("--run-id", help="override run.run_id")
    parser.add_argument("--seed", type=int, help="override run.random_seed")
    parser.add_argument("--sol-price-usd", type=float,
                        help="override run.sol_price_usd for *_sol fields")
    parser.add_argument("--strategies", nargs="+", default=None,
                        help="only run these strategy names")
    parser.add_argument("--limit", type=int, default=None,
                        help="process at most N snapshots (debug)")
    parser.add_argument("--overwrite-run", action="store_true",
                        help="reset an existing replay run directory before "
                             "running (default: refuse to append into a run "
                             "dir that already holds paper artifacts)")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress heartbeat console output")
    parser.add_argument("--write-example-config", metavar="PATH",
                        help="write the example config JSON to PATH and exit")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_example_config:
        path = write_example_config(args.write_example_config)
        print(f"example config written: {path}")
        return 0

    try:
        config = load_config(args.config) if args.config else default_config()
    except ConfigError as exc:
        print("CONFIG INVALID:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2

    if args.out_root:
        config.run.output_root = args.out_root
    if args.run_id:
        config.run.run_id = args.run_id
    if args.seed is not None:
        config.run.random_seed = args.seed
    if args.sol_price_usd is not None:
        config.run.sol_price_usd = args.sol_price_usd
    if args.limit is not None:
        config.run.max_snapshots = args.limit
    if args.strategies:
        wanted = set(args.strategies)
        known = {s.name for s in config.strategies}
        unknown = wanted - known
        if unknown:
            print(f"unknown strategy names: {sorted(unknown)} "
                  f"(config has: {sorted(known)})", file=sys.stderr)
            return 2
        for strat in config.strategies:
            strat.enabled = strat.enabled and strat.name in wanted

    inputs = args.inputs or config.input_paths
    if not inputs:
        print("no inputs: pass --inputs or set input_paths in the config",
              file=sys.stderr)
        return 2

    snapshots, errors = load_snapshots(inputs)
    print(f"loaded {len(snapshots)} snapshots "
          f"({len(errors)} input errors) from {len(inputs)} input path(s)")
    if not snapshots:
        print("nothing to replay", file=sys.stderr)
        return 1

    try:
        summary = run_replay(config, snapshots, input_errors=errors,
                             quiet=args.quiet,
                             overwrite_run=args.overwrite_run)
    except ReplayRunDirError as exc:
        print(f"REPLAY REFUSED: {exc}", file=sys.stderr)
        return 3

    run_dir = (Path(config.run.output_root)
               / (config.run.run_id or summary["run_id"]))
    print()
    print(comparison_markdown({
        "run_id": summary["run_id"],
        "as_of_utc": summary.get("as_of_utc"),
        "ranking": summary.get("strategy_ranking", []),
    }))
    print(f"artifacts: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
