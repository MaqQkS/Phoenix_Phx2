"""Offline, paired +35% full-exit versus 1.35x principal-recovery replay.

Reads only existing candidate/pricing JSONL, without the final ATH checkpoint
overlay used by the general loader. Writes fresh paper ledgers and comparison
evidence. Synthetic scenarios are explicitly separate from historical inputs.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PHX2.paper_trading.config import (
    END_OF_STREAM_LEAVE_OPEN, PROFILE_FIXED_USD, STRATEGY_BALA_PLAN,
    SizingProfileConfig, load_config,
)
from PHX2.paper_trading.engine import PaperTradingEngine
from PHX2.paper_trading.ledger import FILLS_FILE, read_jsonl
from PHX2.paper_trading.models import CandidateSnapshot, parse_utc, utc_iso
from PHX2.paper_trading.pricing import normalize_record


def historical_inputs(root):
    paths = [root / "pricing_tail.jsonl"] + sorted((root / "candidates").glob("*.jsonl"))
    snapshots, manifest, ages = [], [], []
    counts = Counter()
    for path in paths:
        raw = path.read_bytes()
        manifest.append({"path": str(path), "bytes": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()})
        for line_number, line in enumerate(raw.splitlines(), 1):
            counts["rows"] += 1
            record = json.loads(line)  # fail instead of silently dropping bad input
            snapshot = normalize_record(record, str(path), line_number)
            if snapshot is None:
                counts["unusable_rows"] += 1
                continue
            snapshots.append(snapshot)
            counts["priced_rows"] += int(snapshot.has_price)
            counts["rows_with_tier"] += int(snapshot.tier is not None)
            counts["rows_with_ath_market_cap"] += int(snapshot.ath_market_cap_usd is not None)
            price_time = parse_utc(record.get("price_observed_at_utc"))
            if price_time is not None:
                ages.append(snapshot.ts_epoch - price_time)
    snapshots.sort(key=lambda s: (s.ts_epoch, s.source_file or "", s.source_line or 0))
    provenance = {"classification": "HISTORICAL_RECORDED_OBSERVATIONS",
                  "files": manifest, "counts": dict(counts),
                  "snapshots": len(snapshots), "mints": len({s.mint for s in snapshots}),
                  "start_utc": utc_iso(snapshots[0].ts_epoch) if snapshots else None,
                  "end_utc": utc_iso(snapshots[-1].ts_epoch) if snapshots else None,
                  "maximum_explicit_price_age_seconds": max(ages, default=None),
                  "final_ath_checkpoint_overlay": False,
                  "interpolation_or_generated_prices": False}
    return snapshots, provenance


def paired_config(base, policy, synthetic=False):
    cfg = deepcopy(base)
    bala = next(s for s in cfg.strategies if s.strategy_type == STRATEGY_BALA_PLAN)
    cfg.strategies = [bala]
    bala.enabled = True
    cfg.run.end_of_stream_policy = END_OF_STREAM_LEAVE_OPEN
    cfg.run.max_snapshots = None
    cfg.run.heartbeat_every_seconds = 0
    cfg.input_paths = []
    bala.params.update(initials_recovery_multiple=1.35, take_profit_pct=None,
                       trailing_stop_pct=None, runner_trailing_stop_pct=0.30)
    if policy == "old_full_exit":
        # This is the requested flat +35% comparator, not the old HQ 5x policy.
        bala.params.update(initials_recovery_multiple=None, take_profit_pct=0.35,
                           high_quality_min_score=None, high_quality_tiers=[])
    if synthetic:
        cfg.sizing_profiles = {"paired_fixed_100": SizingProfileConfig(
            profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
            max_buy_pct_of_liquidity=None)}
        bala.sizing_profile = "paired_fixed_100"
        bala.params.update(enable_scout_entry=False, max_dca_count=0,
                           dca_1_pct_of_max_position=1.0)
    return cfg


def run_pair(base, snapshots, root, synthetic=False):
    result = {}
    for policy in ("old_full_exit", "recover_and_ride"):
        cfg = paired_config(base, policy, synthetic)
        cfg.run.output_root = str(root)
        cfg.run.run_id = policy
        engine = PaperTradingEngine(cfg, quiet=True)
        try:
            for snapshot in snapshots:
                engine.process_snapshot(deepcopy(snapshot))
            summary = engine.finalize()["strategies"][cfg.strategies[0].name]
            runtime = engine.runtimes[0]
            open_net_pnl = sum(
                engine._sell_tokens(p, p.latest_price, p.tokens_open,
                                    p.latest_liquidity)[0]
                - p.tokens_open * p.avg_cost_per_token
                for p in runtime.open_by_mint.values())
            rows = read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))
            recoveries = [f for f in rows if f["leg"] == "INITIALS_RECOVERY"]
            result[policy] = {
                "summary": summary, "fills": len(rows),
                "buy_fills": sum(f["side"] == "BUY" for f in rows),
                "recovery_fills": len(recoveries),
                "recovery_net_proceeds_usd": sum(f["notional_usd"] for f in recoveries),
                "realized_pnl_usd": runtime.realized_pnl_usd,
                "open_positions": len(runtime.open_by_mint),
                "net_liquidation_pnl_usd": runtime.realized_pnl_usd + open_net_pnl,
                "sell_reasons": [f["reason"] for f in rows if f["side"] == "SELL"],
                "entry_diagnostics": runtime.strategy.monitor_snapshot(),
                "ledger_directory": str(engine.run_dir),
            }
        finally:
            engine.close()
    return result


SYNTHETIC_PATHS = {
    "run_up_then_retrace": [1.0, 1.35, 2.0, 3.0, 2.09],
    "reversal_after_recovery": [1.0, 1.35, 1.0, 0.94],
    "gap_down_after_recovery": [1.0, 1.35, 0.60],
    "stop_before_recovery": [1.0, 1.2, 0.69],
    "high_quality_5x_then_30_percent_trail": [1.0, 1.35, 5.0, 3.6, 3.5],
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-dir", type=Path, action="append", default=[])
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.run_dir and not args.synthetic:
        parser.error("provide historical --run-dir or --synthetic")
    if args.out.exists():
        parser.error("output must be a new directory; existing evidence is never overwritten")
    base = load_config(args.config)
    args.out.mkdir(parents=True)
    report = {
        "cost_model": base.market_sim.to_dict(),
        "config_sha256": hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
        "method": [
            "Identical observed stream, entry rules, sizing and costs in each pair.",
            "Old comparator always exits fully at +35%; its old HQ exception is disabled.",
            "Historical observations use ingestion time; stale marks and sparse coverage remain limitations.",
            "No final ATH overlay, interpolation, new market requests, or PHX1 data.",
            "End-of-stream leaves positions open; net liquidation is a model valuation, not a fill.",
            "Synthetic paths use fixed $100 entries, no DCA, $50,000 LP, score 0.95, and 60-second steps.",
            "This is a mechanics comparison, not evidence of profitability or future executable fills.",
        ],
        "cases": [],
    }
    for root in args.run_dir:
        snapshots, provenance = historical_inputs(root)
        report["cases"].append({"name": root.name, "provenance": provenance,
                                "results": run_pair(base, snapshots, args.out / root.name)})
    if args.synthetic:
        for name, multiples in SYNTHETIC_PATHS.items():
            snapshots = [CandidateSnapshot(
                ts_epoch=1_700_000_000 + index * 60, mint="SYNTHETIC_SCENARIO",
                price_usd=0.0001 * multiple, market_cap_usd=40_000 * multiple,
                liquidity_usd=50_000, tier=2, drawdown_pct=70, score=0.95,
                source_kind="SYNTHETIC_REGRESSION")
                for index, multiple in enumerate(multiples)]
            report["cases"].append({"name": name,
                "provenance": {"classification": "SYNTHETIC_REGRESSION", "price_multiples": multiples},
                "results": run_pair(base, snapshots, args.out / name, synthetic=True)})
    (args.out / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Offline paper exit comparison", "", *report["method"], "",
             "| Case | Evidence | Old net PnL | New net PnL | Buy fills old/new | Recovery fills | Open old/new |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for case in report["cases"]:
        old, new = (case["results"][p] for p in ("old_full_exit", "recover_and_ride"))
        lines.append(f"| {case['name']} | {case['provenance']['classification']} | "
                     f"${old['net_liquidation_pnl_usd']:.4f} | ${new['net_liquidation_pnl_usd']:.4f} | "
                     f"{old['buy_fills']}/{new['buy_fills']} | {new['recovery_fills']} | "
                     f"{old['open_positions']}/{new['open_positions']} |")
    (args.out / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
