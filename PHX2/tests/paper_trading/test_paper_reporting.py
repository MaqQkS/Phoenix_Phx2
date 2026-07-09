"""Reporting tests: metrics math, ranking, markdown, dashboard schema."""

from __future__ import annotations

import pytest

from PHX2.paper_trading.reporting import (
    build_comparison,
    build_run_summary,
    comparison_markdown,
    equity_max_drawdown_pct,
    summarize_strategy,
)


def rec(pnl, status="CLOSED", pct=None, mc=None, lp=None, hold=None,
        tier=None, size=100.0, unrealized=0.0, reason=None):
    return {
        "paper_trade_id": f"t{pnl}",
        "mint": "M" * 44,
        "status": status,
        "realized_pnl_usd": pnl,
        "unrealized_pnl_usd": unrealized,
        "realized_pnl_pct": pct,
        "entry_market_cap": mc,
        "entry_liquidity": lp,
        "hold_seconds": hold,
        "tier": tier,
        "virtual_usd_size": size,
        "reason_closed": reason,
    }


class TestSummarizeStrategy:
    def make_records(self):
        return [
            rec(100.0, pct=100.0, mc=10_000.0, lp=3_000.0, hold=300.0,
                tier=1),
            rec(-50.0, pct=-50.0, mc=100_000.0, lp=30_000.0, hold=7_200.0,
                tier=2),
            rec(25.0, status="RUGGED", pct=25.0, mc=40_000.0, lp=10_000.0,
                hold=4_000.0, tier=2),
            rec(-80.0, status="DATA_LOST", pct=-80.0, mc=20_000.0,
                lp=6_000.0, hold=30_000.0),
            rec(0.0, status="OPEN", unrealized=10.0, mc=60_000.0,
                lp=50_000.0),
            rec(0.0, status="SKIPPED_PRICE_MISSING", size=0.0,
                reason="NO_ENTRY_PRICE"),
            rec(0.0, status="SKIPPED_MIN_NOTIONAL", size=0.0,
                reason="MIN_NOTIONAL_NOT_MET"),
            rec(0.0, status="SKIPPED_LIQUIDITY_CAP", size=0.0,
                reason="NO_LIQUIDITY_DATA"),
        ]

    def test_counts_and_totals(self):
        summary = summarize_strategy("s1", self.make_records(),
                                     starting_bankroll_usd=1_000.0)
        assert summary["total_paper_trades"] == 5
        assert summary["open_trades"] == 1
        assert summary["closed_trades"] == 4
        assert summary["skipped_trades"] == 3
        assert summary["realized_pnl_usd"] == pytest.approx(-5.0)
        assert summary["unrealized_pnl_usd"] == pytest.approx(10.0)
        assert summary["total_pnl_usd"] == pytest.approx(5.0)
        assert summary["ending_equity_usd"] == pytest.approx(1_005.0)
        # 5 non-skip records with size 100 each
        assert summary["cost_deployed_usd"] == pytest.approx(500.0)
        assert summary["total_pnl_pct"] == pytest.approx(1.0)

    def test_win_loss_stats(self):
        summary = summarize_strategy("s1", self.make_records())
        assert summary["win_rate_pct"] == pytest.approx(50.0)
        assert summary["average_win_usd"] == pytest.approx(62.5)
        assert summary["average_loss_usd"] == pytest.approx(-65.0)
        assert summary["best_trade"]["realized_pnl_usd"] == 100.0
        assert summary["worst_trade"]["realized_pnl_usd"] == -80.0
        assert summary["median_return_pct"] == pytest.approx(-12.5)

    def test_death_and_skip_counters(self):
        summary = summarize_strategy("s1", self.make_records())
        assert summary["rugged_trades"] == 1
        assert summary["data_lost_trades"] == 1
        assert summary["skipped_price_missing"] == 1
        assert summary["skipped_min_notional"] == 1
        assert summary["skipped_liquidity_cap"] == 1
        assert summary["skip_reasons"]["NO_ENTRY_PRICE"] == 1

    def test_band_groupings(self):
        summary = summarize_strategy("s1", self.make_records())
        by_tier = summary["performance_by_tier"]
        assert by_tier["TIER_1"]["trades"] == 1
        assert by_tier["TIER_2"]["trades"] == 2
        assert by_tier["TIER_UNKNOWN"]["trades"] == 1
        by_mc = summary["performance_by_mc_band"]
        assert by_mc["MC_LT_15K"]["trades"] == 1
        assert by_mc["MC_15K_50K"]["trades"] == 2
        assert by_mc["MC_50K_150K"]["trades"] == 1
        by_lp = summary["performance_by_lp_band"]
        assert by_lp["LP_LT_5K"]["trades"] == 1
        by_hold = summary["performance_by_hold_time"]
        assert by_hold["HOLD_LT_10M"]["trades"] == 1
        assert by_hold["HOLD_GTE_6H"]["trades"] == 1

    def test_sol_conversion(self):
        summary = summarize_strategy("s1", self.make_records(),
                                     sol_price_usd=200.0)
        assert summary["total_pnl_sol"] == pytest.approx(5.0 / 200.0)


class TestDrawdownAndRanking:
    def test_equity_max_drawdown(self):
        assert equity_max_drawdown_pct([1000, 1100, 900, 1050]) == \
            pytest.approx((1100 - 900) / 1100 * 100.0, abs=1e-4)
        assert equity_max_drawdown_pct([]) is None
        assert equity_max_drawdown_pct([1000, 1100]) == pytest.approx(0.0)

    def test_ranking_and_markdown(self):
        records = {
            "alpha": [rec(50.0, pct=50.0)],
            "beta": [rec(200.0, pct=200.0)],
            "gamma": [rec(-30.0, pct=-30.0)],
        }
        summary = build_run_summary(
            run_id="r1", config_digest="d", mode="REPLAY",
            records_by_strategy=records,
            equity_by_strategy={k: [1000.0] for k in records})
        ranking = summary["strategy_ranking"]
        assert [row["strategy_name"] for row in ranking] == \
            ["beta", "alpha", "gamma"]
        assert ranking[0]["rank"] == 1

        comparison = build_comparison("r1", summary["strategies"])
        markdown = comparison_markdown(comparison)
        assert "| 1 | beta |" in markdown
        assert "strategy comparison" in markdown.lower()

    def test_dashboard_schema_keys(self):
        summary = build_run_summary(
            run_id="r1", config_digest="d",
            records_by_strategy={"s": [rec(10.0, pct=10.0)]},
            equity_by_strategy={"s": [1000.0, 1010.0]},
            starting_bankroll_usd=1_000.0, as_of_utc="2026-07-01T00:00:00Z")
        assert summary["schema_version"] == "phx2_paper_v1"
        assert summary["artifact"] == "paper_summary"
        for key in ("run_id", "mode", "config_digest", "as_of_utc",
                    "strategies", "strategy_ranking"):
            assert key in summary
        strat = summary["strategies"]["s"]
        for key in ("total_pnl_usd", "win_rate_pct", "max_drawdown_pct",
                    "performance_by_tier", "performance_by_mc_band",
                    "performance_by_lp_band", "performance_by_hold_time",
                    "best_trade", "worst_trade", "skip_reasons"):
            assert key in strat
