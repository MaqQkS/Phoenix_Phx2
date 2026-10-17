"""Per-strategy performance summaries + strategy comparison artifacts.

Everything works over final position records (the dict shape written to the
positions ledger) plus per-strategy equity series, so the same code powers
the end-of-run summary, the periodic snapshot, and a future dashboard
"Paper Trading" tab. All output is plain JSON-ready data.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

from PHX2.paper_trading.models import (
    CLOSED_STATUSES,
    SCHEMA_VERSION,
    SKIP_STATUSES,
    STATUS_DATA_LOST,
    STATUS_OPEN,
    STATUS_RUGGED,
    STATUS_SKIPPED_HIGH_RISK,
    STATUS_SKIPPED_MIN_NOTIONAL,
    STATUS_SKIPPED_PRICE_MISSING,
)

MC_BANDS = (
    ("MC_LT_15K", 0.0, 15_000.0),
    ("MC_15K_50K", 15_000.0, 50_000.0),
    ("MC_50K_150K", 50_000.0, 150_000.0),
    ("MC_GTE_150K", 150_000.0, float("inf")),
)

LP_BANDS = (
    ("LP_LT_5K", 0.0, 5_000.0),
    ("LP_5K_25K", 5_000.0, 25_000.0),
    ("LP_25K_100K", 25_000.0, 100_000.0),
    ("LP_GTE_100K", 100_000.0, float("inf")),
)

HOLD_BANDS = (
    ("HOLD_LT_10M", 0.0, 600.0),
    ("HOLD_10M_1H", 600.0, 3600.0),
    ("HOLD_1H_6H", 3600.0, 21_600.0),
    ("HOLD_GTE_6H", 21_600.0, float("inf")),
)


def _band_label(value: Optional[float],
                bands: Sequence[Any]) -> str:
    if value is None:
        return "UNKNOWN"
    for label, low, high in bands:
        if low <= value < high:
            return label
    return "UNKNOWN"


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return None if value is None else round(value, digits)


def _trade_brief(rec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "paper_trade_id": rec.get("paper_trade_id"),
        "mint": rec.get("mint"),
        "status": rec.get("status"),
        "realized_pnl_usd": rec.get("realized_pnl_usd"),
        "unrealized_pnl_usd": rec.get("unrealized_pnl_usd"),
        "realized_pnl_pct": rec.get("realized_pnl_pct"),
        "reason_closed": rec.get("reason_closed"),
        "tier": rec.get("tier"),
    }


def _group_perf(records: List[Dict[str, Any]],
                label_fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        label = label_fn(rec)
        group = groups.setdefault(label, {
            "trades": 0, "wins": 0,
            "realized_pnl_usd": 0.0, "cost_usd": 0.0,
        })
        pnl = float(rec.get("realized_pnl_usd") or 0.0)
        group["trades"] += 1
        group["wins"] += 1 if pnl > 0 else 0
        group["realized_pnl_usd"] += pnl
        group["cost_usd"] += float(rec.get("virtual_usd_size") or 0.0)
    for group in groups.values():
        group["win_rate_pct"] = _round(
            group["wins"] / group["trades"] * 100.0) if group["trades"] else None
        group["realized_pnl_pct"] = _round(
            group["realized_pnl_usd"] / group["cost_usd"] * 100.0
            if group["cost_usd"] > 0 else None)
        group["realized_pnl_usd"] = _round(group["realized_pnl_usd"], 6)
        group["cost_usd"] = _round(group["cost_usd"], 6)
    return dict(sorted(groups.items()))


def equity_max_drawdown_pct(equity_series: Sequence[float]) -> Optional[float]:
    """Max peak-to-trough drawdown (percent) of an equity value series."""
    peak: Optional[float] = None
    max_dd = 0.0
    for value in equity_series:
        if peak is None or value > peak:
            peak = value
        if peak and peak > 0:
            max_dd = max(max_dd, (peak - value) / peak * 100.0)
    return _round(max_dd) if peak is not None else None


def summarize_strategy(strategy_name: str,
                       records: List[Dict[str, Any]],
                       equity_series: Optional[Sequence[float]] = None,
                       starting_bankroll_usd: Optional[float] = None,
                       sol_price_usd: Optional[float] = None) -> Dict[str, Any]:
    """Metrics for one strategy over its final position records."""
    open_recs = [r for r in records if r.get("status") == STATUS_OPEN]
    closed_recs = [r for r in records if r.get("status") in CLOSED_STATUSES]
    skipped_recs = [r for r in records if r.get("status") in SKIP_STATUSES]

    realized_total = sum(float(r.get("realized_pnl_usd") or 0.0)
                         for r in records)
    unrealized_total = sum(float(r.get("unrealized_pnl_usd") or 0.0)
                           for r in open_recs)
    cost_deployed = sum(float(r.get("virtual_usd_size") or 0.0)
                        for r in records
                        if r.get("status") not in SKIP_STATUSES)
    total_pnl = realized_total + unrealized_total

    wins = [r for r in closed_recs
            if float(r.get("realized_pnl_usd") or 0.0) > 0]
    losses = [r for r in closed_recs
              if float(r.get("realized_pnl_usd") or 0.0) <= 0]
    returns_pct = [float(r["realized_pnl_pct"]) for r in closed_recs
                   if r.get("realized_pnl_pct") is not None]

    best = max(closed_recs,
               key=lambda r: float(r.get("realized_pnl_usd") or 0.0),
               default=None)
    worst = min(closed_recs,
                key=lambda r: float(r.get("realized_pnl_usd") or 0.0),
                default=None)

    def _avg(recs: List[Dict[str, Any]]) -> Optional[float]:
        if not recs:
            return None
        return _round(sum(float(r.get("realized_pnl_usd") or 0.0)
                          for r in recs) / len(recs), 6)

    skip_reasons: Dict[str, int] = {}
    for rec in skipped_recs:
        reason = rec.get("reason_closed") or rec.get("status") or "UNKNOWN"
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    summary: Dict[str, Any] = {
        "strategy_name": strategy_name,
        "total_paper_trades": len(records) - len(skipped_recs),
        "open_trades": len(open_recs),
        "closed_trades": len(closed_recs),
        "skipped_trades": len(skipped_recs),
        "win_rate_pct": _round(len(wins) / len(closed_recs) * 100.0)
        if closed_recs else None,
        "average_win_usd": _avg(wins),
        "average_loss_usd": _avg(losses),
        "realized_pnl_usd": _round(realized_total, 6),
        "unrealized_pnl_usd": _round(unrealized_total, 6),
        "total_pnl_usd": _round(total_pnl, 6),
        "total_pnl_sol": _round(total_pnl / sol_price_usd, 9)
        if sol_price_usd else None,
        "total_pnl_pct": _round(total_pnl / cost_deployed * 100.0)
        if cost_deployed > 0 else None,
        "cost_deployed_usd": _round(cost_deployed, 6),
        "starting_bankroll_usd": starting_bankroll_usd,
        "ending_equity_usd": _round(
            starting_bankroll_usd + total_pnl, 6)
        if starting_bankroll_usd is not None else None,
        "best_trade": _trade_brief(best) if best else None,
        "worst_trade": _trade_brief(worst) if worst else None,
        "median_return_pct": _round(statistics.median(returns_pct))
        if returns_pct else None,
        "max_drawdown_pct": equity_max_drawdown_pct(equity_series or []),
        "rugged_trades": sum(1 for r in closed_recs
                             if r.get("status") == STATUS_RUGGED),
        "data_lost_trades": sum(1 for r in closed_recs
                                if r.get("status") == STATUS_DATA_LOST),
        "skipped_price_missing": sum(
            1 for r in skipped_recs
            if r.get("status") == STATUS_SKIPPED_PRICE_MISSING),
        "skipped_liquidity_cap": skip_reasons.get("NO_LIQUIDITY_DATA", 0),
        "skipped_min_notional": sum(
            1 for r in skipped_recs
            if r.get("status") == STATUS_SKIPPED_MIN_NOTIONAL),
        # Risk-aware protection: entries this strategy refused because the risk
        # layer said RISK_HIGH. These rows carry no fills/PnL, so every PnL figure
        # above already EXCLUDES the high-risk cohort.
        "high_risk_skips": sum(
            1 for r in skipped_recs
            if r.get("status") == STATUS_SKIPPED_HIGH_RISK),
        "high_risk_skip_reasons": dict(sorted(
            (reason, count) for reason, count in skip_reasons.items()
            if str(reason).startswith("HIGH_RISK_"))),
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "performance_by_risk_label": _group_perf(
            closed_recs,
            lambda r: str(r.get("risk_label_at_entry") or "RISK_UNKNOWN")),
        "performance_by_tier": _group_perf(
            closed_recs,
            lambda r: f"TIER_{r['tier']}" if r.get("tier") is not None
            else "TIER_UNKNOWN"),
        "performance_by_mc_band": _group_perf(
            closed_recs,
            lambda r: _band_label(r.get("entry_market_cap"), MC_BANDS)),
        "performance_by_lp_band": _group_perf(
            closed_recs,
            lambda r: _band_label(r.get("entry_liquidity"), LP_BANDS)),
        "performance_by_hold_time": _group_perf(
            closed_recs,
            lambda r: _band_label(r.get("hold_seconds"), HOLD_BANDS)),
    }
    return summary


def build_run_summary(run_id: str,
                      config_digest: str,
                      records_by_strategy: Dict[str, List[Dict[str, Any]]],
                      equity_by_strategy: Dict[str, List[float]],
                      starting_bankroll_usd: Optional[float] = None,
                      sol_price_usd: Optional[float] = None,
                      as_of_utc: Optional[str] = None,
                      mode: str = "REPLAY") -> Dict[str, Any]:
    """Full run summary: per-strategy metrics + ranking. Dashboard-ready."""
    strategies = {
        name: summarize_strategy(
            name, records, equity_by_strategy.get(name),
            starting_bankroll_usd, sol_price_usd)
        for name, records in sorted(records_by_strategy.items())
    }
    ranking = build_ranking(strategies)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": "paper_summary",
        "run_id": run_id,
        "mode": mode,
        "config_digest": config_digest,
        "as_of_utc": as_of_utc,
        "sol_price_usd": sol_price_usd,
        "strategies": strategies,
        "strategy_ranking": ranking,
    }


def build_ranking(strategies: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for name, summary in strategies.items():
        rows.append({
            "strategy_name": name,
            "total_pnl_usd": summary.get("total_pnl_usd") or 0.0,
            "total_pnl_pct": summary.get("total_pnl_pct"),
            "win_rate_pct": summary.get("win_rate_pct"),
            "closed_trades": summary.get("closed_trades", 0),
            "open_trades": summary.get("open_trades", 0),
            "skipped_trades": summary.get("skipped_trades", 0),
            "max_drawdown_pct": summary.get("max_drawdown_pct"),
            "rugged_trades": summary.get("rugged_trades", 0),
            "data_lost_trades": summary.get("data_lost_trades", 0),
            "high_risk_skips": summary.get("high_risk_skips", 0),
        })
    rows.sort(key=lambda r: (-(r["total_pnl_usd"] or 0.0), r["strategy_name"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def build_comparison(run_id: str,
                     strategies: Dict[str, Dict[str, Any]],
                     as_of_utc: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": "strategy_comparison",
        "run_id": run_id,
        "as_of_utc": as_of_utc,
        "ranking": build_ranking(strategies),
    }


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value}{suffix}"


def comparison_markdown(comparison: Dict[str, Any]) -> str:
    """Human-readable strategy ranking table."""
    lines = [
        f"# PHX2 paper trading strategy comparison",
        "",
        f"Run: `{comparison.get('run_id')}`"
        + (f" - as of {comparison['as_of_utc']}"
           if comparison.get("as_of_utc") else ""),
        "",
        "| # | Strategy | Total PnL USD | PnL % | Win rate | Closed | Open "
        "| Skipped | Max DD % | Rugs | Data lost |",
        "|---|----------|---------------|-------|----------|--------|------"
        "|---------|----------|------|-----------|",
    ]
    for row in comparison.get("ranking", []):
        lines.append(
            "| {rank} | {name} | {pnl} | {pct} | {wr} | {closed} | {open} "
            "| {skipped} | {dd} | {rugs} | {lost} |".format(
                rank=row.get("rank"),
                name=row.get("strategy_name"),
                pnl=_fmt(row.get("total_pnl_usd")),
                pct=_fmt(row.get("total_pnl_pct"), "%"),
                wr=_fmt(row.get("win_rate_pct"), "%"),
                closed=row.get("closed_trades", 0),
                open=row.get("open_trades", 0),
                skipped=row.get("skipped_trades", 0),
                dd=_fmt(row.get("max_drawdown_pct"), "%"),
                rugs=row.get("rugged_trades", 0),
                lost=row.get("data_lost_trades", 0),
            ))
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MC_BANDS",
    "LP_BANDS",
    "HOLD_BANDS",
    "equity_max_drawdown_pct",
    "summarize_strategy",
    "build_run_summary",
    "build_ranking",
    "build_comparison",
    "comparison_markdown",
]
