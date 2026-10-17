"""Net principal recovery, adverse fills, and runner-state regressions."""

from pathlib import Path

import pytest

from PHX2.paper_trading.config import (
    END_OF_STREAM_LEAVE_OPEN, PaperConfig, PROFILE_FIXED_USD,
    SizingProfileConfig, STRATEGY_BALA_PLAN, STRATEGY_THREE_X,
    StrategyConfig, default_config, default_strategy_params, load_config,
)
from PHX2.paper_trading.engine import PaperTradingEngine
from PHX2.paper_trading.ledger import FILLS_FILE, read_jsonl
from PHX2.paper_trading.models import CandidateSnapshot
from PHX2.paper_trading.strategy import AddIntent


def config(tmp_path, strategy_type=STRATEGY_BALA_PLAN):
    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path)
    cfg.run.run_id = "recovery"
    cfg.run.end_of_stream_policy = END_OF_STREAM_LEAVE_OPEN
    cfg.run.heartbeat_every_seconds = 0
    cfg.sizing_profiles = {"p": SizingProfileConfig(
        profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
        max_buy_pct_of_liquidity=None)}
    params = default_strategy_params(strategy_type)
    params["runner_trailing_stop_pct"] = 0.30
    if strategy_type == STRATEGY_BALA_PLAN:
        params.update(initials_recovery_multiple=1.35, take_profit_pct=None,
                      enable_scout_entry=False, dca_1_pct_of_max_position=1.0,
                      max_dca_count=0, max_hold_seconds=None)
    else:
        params["recover_multiple"] = 1.35
    cfg.strategies = [StrategyConfig("bala", strategy_type,
                                     sizing_profile="p", params=params)]
    return cfg


def snap(price=1.0, ts=0.0, score=None, lp=50_000.0):
    return CandidateSnapshot(ts_epoch=ts, mint="OFFLINE_TEST_MINT",
                             price_usd=price, market_cap_usd=40_000.0 * price,
                             liquidity_usd=lp, tier=2, drawdown_pct=70.0,
                             score=score)


def open_position(cfg, score=None, lp=50_000.0):
    engine = PaperTradingEngine(cfg, quiet=True)
    engine.process_snapshot(snap(score=score, lp=lp))
    return engine, engine.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]


def fills(engine):
    return read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))


@pytest.mark.parametrize("strategy_type", [STRATEGY_BALA_PLAN, STRATEGY_THREE_X])
@pytest.mark.parametrize("impact_rate,lp", [(0.0, 50_000), (30.0, 50_000),
                                          (3000.0, 2000)])
def test_135x_recovers_full_net_cost_and_leaves_runner(
        tmp_path, strategy_type, impact_rate, lp):
    cfg = config(tmp_path, strategy_type)
    cfg.market_sim.impact_bps_per_pct_of_lp = impact_rate
    engine, pos = open_position(cfg, lp=lp)
    try:
        original_tokens = pos.tokens_open
        engine.process_snapshot(snap(1.349, 60, lp=lp))
        assert len(fills(engine)) == 1
        engine.process_snapshot(snap(1.35, 120, lp=lp))
        recovery = fills(engine)[1]
        assert recovery["notional_usd"] >= pos.cost_basis_usd
        assert recovery["notional_usd"] == pytest.approx(100.0, abs=1e-6)
        assert recovery["fee_usd"] > 0
        assert 0 < pos.tokens_open < original_tokens
        assert pos.strategy_state["initial_recovered"] is True
        assert pos.strategy_state["recovery_status"] == "RECOVERED"
        assert pos.plan.trailing_stop_pct == 0.30
        engine.process_snapshot(snap(1.4, 180, lp=lp))
        assert len(fills(engine)) == 2  # no second recovery
    finally:
        engine.close()


def test_dca_cost_and_buy_fees_are_all_recovered(tmp_path):
    engine, pos = open_position(config(tmp_path))
    try:
        engine._add_leg(engine.runtimes[0], pos, snap(0.8, 60),
                        AddIntent("DCA_2", 50.0))
        assert pos.cost_basis_usd == 150.0
        assert len(pos.legs) == 2
        engine.process_snapshot(snap(pos.entry_price * 1.35, 120))
        assert fills(engine)[-1]["notional_usd"] >= 150.0
        assert pos.strategy_state["initial_cost_usd"] == 150.0
        assert pos.tokens_open > 0
    finally:
        engine.close()


def test_high_quality_never_retrims_or_switches_to_25_percent(tmp_path):
    engine, pos = open_position(config(tmp_path), score=0.95)
    try:
        # A resumed legacy HQ plan must not override the new recovery policy.
        pos.plan.hold_to_multiple = 5.0
        pos.plan.trim_fraction = 0.5
        engine.process_snapshot(snap(1.35, 60))
        engine.process_snapshot(snap(5.0, 120))
        assert len(fills(engine)) == 2
        assert not pos.strategy_state.get("trimmed")
        assert pos.plan.trailing_stop_pct == 0.30
        engine.process_snapshot(snap(3.6, 180))  # 28% down: still open
        assert pos.is_open
        engine.process_snapshot(snap(3.5, 240))  # 30% down: close runner
        assert not pos.is_open
        assert fills(engine)[-1]["leg"] == "RUNNER_CLOSE"
        assert pos.reason_closed == "TRAILING_STOP_0.30"
    finally:
        engine.close()


def test_insufficient_net_proceeds_defers_without_selling(tmp_path):
    cfg = config(tmp_path)
    cfg.market_sim.fee_bps = 1000
    cfg.market_sim.base_slippage_bps = 1000
    engine, pos = open_position(cfg)
    try:
        before = pos.tokens_open
        engine.process_snapshot(snap(1.35, 60))
        assert len(fills(engine)) == 1
        assert pos.tokens_open == before
        assert not pos.strategy_state.get("initial_recovered")
        assert pos.strategy_state["recovery_status"] == "INSUFFICIENT_NET_PROCEEDS"
        assert pos.plan.trailing_stop_pct is None
        engine.process_snapshot(snap(2.0, 120))
        assert pos.strategy_state["initial_recovered"] is True
    finally:
        engine.close()


@pytest.mark.parametrize("lp", [None, 0.0])
def test_missing_or_dead_liquidity_cannot_confirm_recovery(tmp_path, lp):
    engine, pos = open_position(config(tmp_path))
    try:
        pos.latest_liquidity = lp
        assert engine._recovery_tokens(pos, 1.35, 100) is None
        assert not pos.strategy_state.get("initial_recovered")
    finally:
        engine.close()


def test_recovery_takes_priority_over_a_new_dca_leg(tmp_path, monkeypatch):
    engine, pos = open_position(config(tmp_path))
    try:
        monkeypatch.setattr(engine.runtimes[0].strategy, "_maybe_dca",
                            lambda *args: [AddIntent("DCA_2", 50.0)])
        engine.process_snapshot(snap(1.35, 60))
        assert pos.cost_basis_usd == 100.0
        assert [f["leg"] for f in fills(engine)] == ["DCA_1", "INITIALS_RECOVERY"]
    finally:
        engine.close()


@pytest.mark.parametrize("target", [0.001, 1.0])
def test_solver_handles_large_impact_before_and_after_cap(tmp_path, target):
    engine, pos = open_position(config(tmp_path))
    try:
        pos.latest_liquidity = 1.0
        engine.sim.impact_bps_per_pct_of_lp = 10_000
        engine.sim.max_impact_bps = 8000
        tokens = engine._recovery_tokens(pos, 1.35, target)
        assert 0 < tokens < pos.tokens_open
        assert engine._sell_tokens(pos, 1.35, tokens, 1.0)[0] >= target
        assert engine._sell_tokens(pos, 1.35, tokens * 0.999, 1.0)[0] < target
    finally:
        engine.close()


@pytest.mark.parametrize("exit_kind,reason", [
    ("stop", "STOP_LOSS_-0.30"), ("rug", "LIQUIDITY_COLLAPSE"),
    ("time", "MAX_HOLD_EXPIRED"), ("data", "DATA_LOST"),
])
def test_other_exits_remain_active_after_recovery(tmp_path, exit_kind, reason):
    cfg = config(tmp_path)
    if exit_kind == "time":
        cfg.strategies[0].params["max_hold_seconds"] = 100
    if exit_kind == "data":
        cfg.market_sim.data_lost_after_seconds = 100
    engine, pos = open_position(cfg)
    try:
        engine.process_snapshot(snap(1.35, 60))
        if exit_kind == "stop":
            next_snapshot = snap(0.65, 120)
        elif exit_kind == "rug":
            next_snapshot = snap(1.35, 120, lp=5000)
        elif exit_kind == "data":
            next_snapshot = snap(1.35, 200)
            next_snapshot.mint = "DIFFERENT_MINT"
        else:
            next_snapshot = snap(1.35, 120)
        engine.process_snapshot(next_snapshot)
        assert not pos.is_open
        assert reason in pos.reason_closed
    finally:
        engine.close()


def worse_fill_after_quote(engine, monkeypatch, fee_bps):
    original = engine._recovery_tokens

    def quote_then_change_fee(*args):
        tokens = original(*args)
        engine.sim.fee_bps = fee_bps
        monkeypatch.setattr(engine, "_recovery_tokens", original)
        return tokens

    monkeypatch.setattr(engine, "_recovery_tokens", quote_then_change_fee)


def test_short_net_fill_retries_only_shortfall_after_restart(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    engine, pos = open_position(cfg)
    worse_fill_after_quote(engine, monkeypatch, 600)
    engine.process_snapshot(snap(1.35, 60))
    assert 0 < pos.strategy_state["initial_recovery_proceeds_usd"] < 100
    assert pos.strategy_state["recovery_status"] == "SHORTFALL"
    assert not pos.strategy_state.get("initial_recovered")
    assert pos.plan.trailing_stop_pct is None
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    try:
        pos = resumed.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]
        resumed.process_snapshot(snap(1.4, 120))
        sales = [f for f in fills(resumed) if f["side"] == "SELL"]
        assert len(sales) == 2
        assert sales[1]["notional_usd"] < 10
        assert sum(f["notional_usd"] for f in sales) == pytest.approx(100, abs=1e-6)
        assert pos.strategy_state["initial_recovered"] is True
        assert pos.tokens_open > 0
    finally:
        resumed.close()


def test_zero_net_fill_does_not_change_tokens_or_arm_runner(tmp_path, monkeypatch):
    engine, pos = open_position(config(tmp_path))
    try:
        before = pos.tokens_open
        worse_fill_after_quote(engine, monkeypatch, 10_000)
        engine.process_snapshot(snap(1.35, 60))
        assert pos.tokens_open == before
        assert len(fills(engine)) == 1
        assert pos.strategy_state["recovery_status"] == "INVALID_RECOVERY_FILL"
        assert not pos.strategy_state.get("initial_recovered")
        assert pos.plan.trailing_stop_pct is None
    finally:
        engine.close()


def test_failed_fill_append_does_not_mark_recovered(tmp_path, monkeypatch):
    engine, pos = open_position(config(tmp_path))
    try:
        before = pos.tokens_open

        def fail(_):
            raise OSError("injected fill write failure")

        monkeypatch.setattr(engine.ledger, "append_fill", fail)
        with pytest.raises(OSError, match="injected fill write failure"):
            engine.process_snapshot(snap(1.35, 60))
        assert pos.tokens_open == before
        assert not pos.strategy_state.get("initial_recovered")
        assert pos.plan.trailing_stop_pct is None
    finally:
        engine.close()


def test_confirmed_runner_and_peak_survive_restart(tmp_path):
    cfg = config(tmp_path)
    engine, pos = open_position(cfg, score=0.95)
    engine.process_snapshot(snap(1.35, 60))
    engine.process_snapshot(snap(5.0, 120))
    engine.write_monitor_artifacts()
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    try:
        pos = resumed.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]
        assert pos.strategy_state["initial_recovery_proceeds_usd"] >= 100
        assert pos.post_trim_peak_price == 5.0
        assert pos.plan.trailing_stop_pct == 0.30
        resumed.process_snapshot(snap(3.6, 180))
        assert pos.is_open
        resumed.process_snapshot(snap(3.5, 240))
        assert not pos.is_open
        assert len(fills(resumed)) == 3
    finally:
        resumed.close()


def test_generated_and_checked_in_examples_enable_135x():
    example = Path(__file__).parents[2] / "paper_trading" / "example_config.json"
    for cfg in (default_config(), load_config(str(example))):
        bala = next(s for s in cfg.strategies if s.strategy_type == STRATEGY_BALA_PLAN)
        assert bala.params["initials_recovery_multiple"] == 1.35
        assert bala.params["take_profit_pct"] is None
        assert bala.params["runner_trailing_stop_pct"] == 0.30
