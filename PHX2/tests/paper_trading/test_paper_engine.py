"""Engine tests: exit paths, skips, dup prevention, determinism, restart."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.paper_trading.config import (
    END_OF_STREAM_LEAVE_OPEN,
    PaperConfig,
    PROFILE_FIXED_USD,
    RUG_ACTION_FREEZE,
    SizingProfileConfig,
    STRATEGY_CONFIG_PLAN,
    StrategyConfig,
    default_config,
    default_strategy_params,
)
from PHX2.paper_trading.engine import PaperTradingEngine, run_replay
from PHX2.paper_trading.ledger import (
    EQUITY_FILE,
    FILLS_FILE,
    OPEN_POSITIONS_FILE,
    POSITIONS_FILE,
    SUMMARY_FILE,
    read_jsonl,
)
from PHX2.paper_trading.models import (
    CandidateSnapshot,
    STATUS_CLOSED,
    STATUS_DATA_LOST,
    STATUS_EXPIRED,
    STATUS_OPEN,
    STATUS_RUGGED,
    STATUS_SKIPPED_PRICE_MISSING,
    STATUS_STOPPED,
    STATUS_TAKE_PROFIT,
)

MINT_A = "A" * 40 + "pump"
MINT_B = "B" * 40 + "pump"


def snap(mint=MINT_A, ts=1_000.0, price=0.0001, mc=100_000.0, lp=50_000.0):
    return CandidateSnapshot(ts_epoch=ts, mint=mint, price_usd=price,
                             market_cap_usd=mc, liquidity_usd=lp)


def one_strategy_config(tmp_path, params=None, sim=None, run=None,
                        **strategy_kwargs) -> PaperConfig:
    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path)
    cfg.run.run_id = "t"
    cfg.run.heartbeat_every_seconds = 0
    cfg.run.equity_curve_bucket_seconds = 0
    for key, value in (run or {}).items():
        setattr(cfg.run, key, value)
    for key, value in (sim or {}).items():
        setattr(cfg.market_sim, key, value)
    cfg.sizing_profiles = {"p": SizingProfileConfig(
        profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
        max_buy_pct_of_liquidity=None, max_abs_notional_usd=None)}
    merged = dict(default_strategy_params(STRATEGY_CONFIG_PLAN))
    merged.update(params or {})
    cfg.strategies = [StrategyConfig(
        name="s1", strategy_type=STRATEGY_CONFIG_PLAN, sizing_profile="p",
        params=merged, **strategy_kwargs)]
    return cfg


def run_engine(cfg, snapshots, finalize=True):
    engine = PaperTradingEngine(cfg, quiet=True)
    for snapshot in snapshots:
        engine.process_snapshot(snapshot)
    summary = engine.finalize() if finalize else None
    engine.close()
    return engine, summary


def final_positions(run_dir) -> dict:
    latest = {}
    for record in read_jsonl(str(Path(run_dir) / POSITIONS_FILE)):
        latest[record["paper_trade_id"]] = record
    return latest


class TestExitPaths:
    def test_take_profit_close(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, price=0.0001),
            snap(ts=60.0, price=0.00016),
        ], finalize=False)
        positions = final_positions(engine.run_dir)
        assert len(positions) == 1
        record = next(iter(positions.values()))
        assert record["status"] == STATUS_TAKE_PROFIT
        assert record["realized_pnl_usd"] > 0
        fills = read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))
        assert [f["side"] for f in fills] == ["BUY", "SELL"]

    def test_stop_loss_close(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"stop_loss_pct": -0.3})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, price=0.0001),
            snap(ts=60.0, price=0.00006),
        ], finalize=False)
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_STOPPED
        assert record["reason_closed"].startswith("STOP_LOSS")
        assert record["realized_pnl_usd"] < 0

    def test_trailing_stop_close(self, tmp_path):
        cfg = one_strategy_config(tmp_path,
                                  params={"trailing_stop_pct": 0.2})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, price=0.0001),
            snap(ts=60.0, price=0.0002),
            snap(ts=120.0, price=0.00015),  # -25% off the peak
        ], finalize=False)
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_STOPPED
        assert record["reason_closed"].startswith("TRAILING_STOP")
        assert record["realized_pnl_usd"] > 0  # still above entry

    def test_max_hold_expiry(self, tmp_path):
        cfg = one_strategy_config(tmp_path,
                                  params={"max_hold_seconds": 600.0})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0),
            snap(mint=MINT_B, ts=700.0),  # advances event time past hold
        ], finalize=False)
        record = [r for r in final_positions(engine.run_dir).values()
                  if r["mint"] == MINT_A][0]
        assert record["status"] == STATUS_EXPIRED
        assert record["reason_closed"] == "MAX_HOLD_EXPIRED"

    def test_data_lost_haircut(self, tmp_path):
        cfg = one_strategy_config(
            tmp_path, sim={"data_lost_after_seconds": 1_800.0,
                           "data_lost_value_ratio": 0.25})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0),
            snap(mint=MINT_B, ts=2_000.0),
        ], finalize=False)
        record = [r for r in final_positions(engine.run_dir).values()
                  if r["mint"] == MINT_A][0]
        assert record["status"] == STATUS_DATA_LOST
        # haircut to 25% of last value makes this a deep loss
        assert record["realized_pnl_usd"] < -60.0

    def test_rug_on_liquidity_collapse(self, tmp_path):
        cfg = one_strategy_config(tmp_path)
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, lp=10_000.0),
            snap(ts=60.0, price=0.00009, lp=1_500.0),  # < 20% of entry LP
        ], finalize=False)
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_RUGGED
        assert record["reason_closed"] == "LIQUIDITY_COLLAPSE"

    def test_rug_on_price_collapse(self, tmp_path):
        cfg = one_strategy_config(tmp_path)
        engine, _ = run_engine(cfg, [
            snap(ts=0.0),
            snap(ts=60.0, price=0.000004),  # -96%
        ], finalize=False)
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_RUGGED
        assert record["reason_closed"] == "PRICE_COLLAPSE"

    def test_rug_freeze_action_realizes_full_loss(self, tmp_path):
        cfg = one_strategy_config(tmp_path,
                                  sim={"rug_action": RUG_ACTION_FREEZE})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, lp=10_000.0),
            snap(ts=60.0, price=0.00009, lp=1_500.0),
        ], finalize=False)
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_RUGGED
        assert record["reason_closed"].endswith("_FROZEN")
        assert record["exit_price"] is None
        assert record["realized_pnl_usd"] == pytest.approx(-100.0)

    def test_missing_price_entry_becomes_skip_row(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"require_price": False})
        engine, _ = run_engine(cfg, [snap(ts=0.0, price=None)],
                               finalize=False)
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_SKIPPED_PRICE_MISSING
        fills = read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))
        assert fills == []

    def test_end_of_stream_close_policy(self, tmp_path):
        cfg = one_strategy_config(tmp_path)
        engine, summary = run_engine(cfg, [snap(ts=0.0)])
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_CLOSED
        assert record["reason_closed"] == "END_OF_STREAM"
        assert summary["strategies"]["s1"]["closed_trades"] == 1

    def test_leave_open_policy(self, tmp_path):
        cfg = one_strategy_config(
            tmp_path, run={"end_of_stream_policy": END_OF_STREAM_LEAVE_OPEN})
        engine, summary = run_engine(cfg, [snap(ts=0.0)])
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_OPEN
        assert summary["strategies"]["s1"]["open_trades"] == 1
        open_snapshot = json.loads(
            (Path(engine.run_dir) / OPEN_POSITIONS_FILE).read_text())
        assert len(open_snapshot["open_positions"]) == 1


class TestEntryDiscipline:
    def test_duplicate_mint_prevention(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5})
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, price=0.0001),
            snap(ts=60.0, price=0.00016),  # take profit close
            snap(ts=120.0, price=0.0001),  # would qualify again
        ], finalize=False)
        positions = final_positions(engine.run_dir)
        assert len(positions) == 1  # no re-entry after close

    def test_reentry_allowed_when_configured(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5},
                                  allow_reentry=True)
        engine, _ = run_engine(cfg, [
            snap(ts=0.0, price=0.0001),
            snap(ts=60.0, price=0.00016),
            snap(ts=120.0, price=0.0001),
        ], finalize=False)
        assert len(final_positions(engine.run_dir)) == 2

    def test_max_open_positions(self, tmp_path):
        cfg = one_strategy_config(tmp_path, max_open_positions=1)
        engine, _ = run_engine(cfg, [
            snap(mint=MINT_A, ts=0.0),
            snap(mint=MINT_B, ts=10.0),
        ], finalize=False)
        positions = final_positions(engine.run_dir)
        assert len(positions) == 1
        events = read_jsonl(str(Path(engine.run_dir) / "paper_events.jsonl"))
        assert any(e.get("event") == "ENTRY_SKIPPED_MAX_OPEN" for e in events)


class TestReproducibilityAndRestart:
    def _stream(self):
        out = []
        for i in range(40):
            mint = f"MINT{i:03d}" + "z" * 33 + "pump"
            out.append(snap(mint=mint, ts=float(i * 30)))
            out.append(snap(mint=mint, ts=float(i * 30 + 600),
                            price=0.0001 * (1.0 + (i % 7 - 3) / 10.0)))
        return sorted(out, key=lambda s: s.sort_key())

    def test_replay_reproducible_with_same_seed(self, tmp_path):
        results = []
        for run_dir in ("r1", "r2"):
            cfg = default_config()
            cfg.run.output_root = str(tmp_path / run_dir)
            cfg.run.run_id = "same"
            cfg.run.random_seed = 99
            cfg.run.heartbeat_every_seconds = 0
            run_replay(cfg, self._stream(), quiet=True)
            results.append(tmp_path / run_dir / "same")
        for name in (POSITIONS_FILE, FILLS_FILE, EQUITY_FILE, SUMMARY_FILE):
            first = (results[0] / name).read_bytes()
            second = (results[1] / name).read_bytes()
            assert first == second, f"{name} differs between identical runs"

    def test_different_seed_changes_monkey_behavior(self, tmp_path):
        outcomes = []
        for seed in (1, 2):
            cfg = default_config()
            cfg.run.output_root = str(tmp_path / f"seed{seed}")
            cfg.run.run_id = "run"
            cfg.run.random_seed = seed
            cfg.run.heartbeat_every_seconds = 0
            summary = run_replay(cfg, self._stream(), quiet=True)
            outcomes.append(
                summary["strategies"]["monkey_random"]["total_paper_trades"])
        assert outcomes[0] != outcomes[1]

    def test_restart_reloads_open_positions(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5})
        engine1 = PaperTradingEngine(cfg, quiet=True)
        engine1.process_snapshot(snap(ts=0.0, price=0.0001))
        run_dir = engine1.run_dir
        assert len(engine1.runtimes[0].open_by_mint) == 1
        engine1.close()  # simulated stop without finalize

        engine2 = PaperTradingEngine(cfg, quiet=True, resume=True)
        runtime = engine2.runtimes[0]
        assert len(runtime.open_by_mint) == 1
        restored = runtime.open_by_mint[MINT_A]
        assert restored.status == STATUS_OPEN
        assert restored.virtual_usd_size == pytest.approx(100.0)
        engine2.process_snapshot(snap(ts=60.0, price=0.00016))
        assert runtime.open_by_mint == {}
        engine2.close()

        latest = final_positions(run_dir)
        assert len(latest) == 1
        assert next(iter(latest.values()))["status"] == STATUS_TAKE_PROFIT
        # append-only: the earlier OPEN row is still the first line
        rows = read_jsonl(str(Path(run_dir) / POSITIONS_FILE))
        assert rows[0]["status"] == STATUS_OPEN
        assert rows[-1]["status"] == STATUS_TAKE_PROFIT

    def test_restart_blocks_duplicate_mint(self, tmp_path):
        cfg = one_strategy_config(tmp_path)
        engine1 = PaperTradingEngine(cfg, quiet=True)
        engine1.process_snapshot(snap(ts=0.0))
        engine1.close()
        engine2 = PaperTradingEngine(cfg, quiet=True, resume=True)
        engine2.process_snapshot(snap(ts=30.0))
        assert len(engine2.runtimes[0].open_by_mint) == 1
        assert engine2.runtimes[0].trade_seq == 1
        engine2.close()


class TestDcaLegsThroughEngine:
    """Full-engine Tier/DCA ladder: legs, blended entry, fill ledger."""

    def _bala_config(self, tmp_path, **param_overrides):
        from PHX2.paper_trading.config import (
            PROFILE_HYBRID_REALISTIC, STRATEGY_BALA_PLAN)
        cfg = PaperConfig()
        cfg.run.output_root = str(tmp_path)
        cfg.run.run_id = "t"
        cfg.run.heartbeat_every_seconds = 0
        cfg.run.equity_curve_bucket_seconds = 0
        cfg.sizing_profiles = {"p": SizingProfileConfig(
            profile=PROFILE_HYBRID_REALISTIC,
            fallback_supply=1_000_000_000)}
        params = dict(default_strategy_params(STRATEGY_BALA_PLAN))
        params["enable_scout_entry"] = True
        params["min_time_between_dca_seconds"] = 60.0
        params.update(param_overrides)
        cfg.strategies = [StrategyConfig(
            name="bala", strategy_type=STRATEGY_BALA_PLAN,
            sizing_profile="p", params=params)]
        return cfg

    def _tier_snap(self, ts, price, mc, lp, tier, dd):
        return CandidateSnapshot(ts_epoch=ts, mint=MINT_A, price_usd=price,
                                 market_cap_usd=mc, liquidity_usd=lp,
                                 tier=tier, drawdown_pct=dd)

    def test_scout_dca1_dca2_ladder_with_blended_entry(self, tmp_path):
        cfg = self._bala_config(tmp_path)
        engine = PaperTradingEngine(cfg, quiet=True)
        engine.process_snapshot(
            self._tier_snap(0.0, 0.0001, 40_000, 30_000, 1, 55.0))
        runtime = engine.runtimes[0]
        position = runtime.open_by_mint[MINT_A]
        assert [l["leg"] for l in position.legs] == ["SCOUT"]
        assert position.strategy_state["bala_state"] == "PAPER_SCOUT_OPEN"
        scout_cost = position.virtual_usd_size

        engine.process_snapshot(
            self._tier_snap(120.0, 0.00008, 32_000, 28_000, 2, 70.0))
        assert [l["leg"] for l in position.legs] == ["SCOUT", "DCA_1"]
        assert position.strategy_state["dca_count"] == 1
        after_dca1 = position.virtual_usd_size
        assert after_dca1 > scout_cost

        engine.process_snapshot(
            self._tier_snap(300.0, 0.00006, 24_000, 26_000, 3, 85.0))
        assert [l["leg"] for l in position.legs] == \
            ["SCOUT", "DCA_1", "DCA_2"]
        assert position.strategy_state["bala_state"] == "PAPER_DCA_2_OPEN"
        assert position.virtual_usd_size > after_dca1

        # blended raw entry = token-weighted average of the three legs
        raw_weight = sum(l["tokens"] * l["price_raw"] for l in position.legs)
        total_tokens = sum(l["tokens"] for l in position.legs)
        assert position.entry_price == pytest.approx(
            raw_weight / total_tokens)
        assert position.entry_price_effective == pytest.approx(
            position.virtual_usd_size / position.estimated_tokens_received)

        fills = read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))
        assert [(f["leg"], f["side"]) for f in fills] == [
            ("SCOUT", "BUY"), ("DCA_1", "BUY"), ("DCA_2", "BUY")]
        events = read_jsonl(str(Path(engine.run_dir) / "paper_events.jsonl"))
        assert sum(1 for e in events if e.get("event") == "POSITION_DCA") == 2
        engine.close()

    def test_dca_skip_event_when_gate_fails(self, tmp_path):
        cfg = self._bala_config(
            tmp_path, min_time_between_dca_seconds=10_000.0)
        engine = PaperTradingEngine(cfg, quiet=True)
        engine.process_snapshot(
            self._tier_snap(0.0, 0.0001, 40_000, 30_000, 1, 55.0))
        engine.process_snapshot(
            self._tier_snap(120.0, 0.00008, 32_000, 28_000, 2, 70.0))
        position = engine.runtimes[0].open_by_mint[MINT_A]
        assert [l["leg"] for l in position.legs] == ["SCOUT"]
        assert position.strategy_state["last_dca_skip"] == "DCA_TIME_GATE"
        engine.close()

    def test_initials_recovery_and_runner_close_legs(self, tmp_path):
        cfg = self._bala_config(tmp_path, enable_scout_entry=False,
                                initials_recovery_multiple=3.0,
                                max_hold_seconds=None)
        engine = PaperTradingEngine(cfg, quiet=True)
        engine.process_snapshot(
            self._tier_snap(0.0, 0.0001, 40_000, 50_000, 2, 70.0))
        position = engine.runtimes[0].open_by_mint[MINT_A]
        cost = position.virtual_usd_size
        # 3x: initials recovery partial fires
        engine.process_snapshot(
            self._tier_snap(600.0, 0.0003, 120_000, 60_000, None, None))
        assert position.strategy_state["initial_recovered"] is True
        assert position.realized_pnl_usd > 0
        assert position.tokens_open < position.estimated_tokens_received
        # runner trails: peak then -35% off the post-recovery peak closes
        engine.process_snapshot(
            self._tier_snap(1_200.0, 0.0004, 160_000, 60_000, None, None))
        engine.process_snapshot(
            self._tier_snap(1_800.0, 0.00025, 100_000, 60_000, None, None))
        assert MINT_A not in engine.runtimes[0].open_by_mint
        fills = read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))
        legs = [f["leg"] for f in fills]
        assert legs == ["DCA_1", "INITIALS_RECOVERY", "RUNNER_CLOSE"]
        # recovery leg realized ~ the initial cost back
        recovery = fills[1]
        assert recovery["notional_usd"] == pytest.approx(cost, rel=0.01)
        record = final_positions(engine.run_dir)[position.paper_trade_id]
        assert record["strategy_state"]["bala_state"] in (
            "CLOSED", "RUNNER_ACTIVE")
        assert record["status"] == STATUS_STOPPED
        engine.close()


class TestPeakPersistence:
    """Codex HIGH finding: trailing-stop peak state must survive restarts."""

    def _position(self):
        from PHX2.paper_trading.models import ExitPlan, PaperPosition
        pos = PaperPosition(paper_trade_id="t1", strategy_name="s1",
                            run_id="r", mint=MINT_A,
                            entry_price=0.0001,
                            plan=ExitPlan(trailing_stop_pct=0.30))
        pos.apply_buy_leg("DCA_1", 0.0, 1_000_000.0, 100.0, 0.0001,
                          0.0001, liquidity=50_000.0)
        pos.mark_price(0.0003, 60.0)
        pos.mark_price(0.0004, 120.0)  # peak 4x
        pos.post_trim_peak_price = 0.0004
        return pos

    def test_peak_fields_survive_serialization(self):
        from PHX2.paper_trading.models import PaperPosition
        pos = self._position()
        record = pos.to_record()
        assert record["peak_price"] == pytest.approx(0.0004)
        assert record["post_trim_peak_price"] == pytest.approx(0.0004)
        assert record["last_price_gap_seconds"] == pytest.approx(60.0)
        restored = PaperPosition.from_record(record)
        assert restored.peak_price == pytest.approx(0.0004)
        assert restored.post_trim_peak_price == pytest.approx(0.0004)
        assert restored.last_price_gap_seconds == pytest.approx(60.0)

    def test_old_records_without_peak_fields_load_safely(self):
        from PHX2.paper_trading.models import PaperPosition
        record = self._position().to_record()
        for legacy_missing in ("peak_price", "post_trim_peak_price",
                               "last_price_gap_seconds"):
            record.pop(legacy_missing)
        restored = PaperPosition.from_record(record)
        # conservative fallback: highest provably-seen price
        assert restored.peak_price == pytest.approx(0.0004)  # latest_price
        assert restored.post_trim_peak_price is None
        assert restored.last_price_gap_seconds is None
        record["latest_price"] = None
        restored = PaperPosition.from_record(record)
        assert restored.peak_price == pytest.approx(0.0001)  # entry price

    def _runner_config(self, tmp_path):
        from PHX2.paper_trading.config import (
            PROFILE_HYBRID_REALISTIC, STRATEGY_BALA_PLAN)
        cfg = PaperConfig()
        cfg.run.output_root = str(tmp_path)
        cfg.run.run_id = "t"
        cfg.run.heartbeat_every_seconds = 0
        cfg.run.equity_curve_bucket_seconds = 0
        cfg.sizing_profiles = {"p": SizingProfileConfig(
            profile=PROFILE_HYBRID_REALISTIC,
            fallback_supply=1_000_000_000)}
        params = dict(default_strategy_params(STRATEGY_BALA_PLAN))
        params["initials_recovery_multiple"] = 3.0
        params["max_hold_seconds"] = None
        cfg.strategies = [StrategyConfig(
            name="bala", strategy_type=STRATEGY_BALA_PLAN,
            sizing_profile="p", params=params)]
        return cfg

    def _tier_snap(self, ts, price, mc, lp, tier=None, dd=None):
        return CandidateSnapshot(ts_epoch=ts, mint=MINT_A, price_usd=price,
                                 market_cap_usd=mc, liquidity_usd=lp,
                                 tier=tier, drawdown_pct=dd)

    def test_runner_trailing_survives_restart(self, tmp_path):
        """Audit scenario: recovery at 3x, peak 4x, restart, price 2.5x.

        30% trailing off the 4x peak must close below 2.8x; a restart must
        not forget the 4x peak."""
        cfg = self._runner_config(tmp_path)
        engine1 = PaperTradingEngine(cfg, quiet=True)
        engine1.process_snapshot(
            self._tier_snap(0.0, 0.0001, 40_000, 50_000, 2, 70.0))
        engine1.process_snapshot(          # 3x: initials recovery + trail
            self._tier_snap(600.0, 0.0003, 120_000, 60_000))
        engine1.process_snapshot(          # 4x peak
            self._tier_snap(1_200.0, 0.0004, 160_000, 60_000))
        position1 = engine1.runtimes[0].open_by_mint[MINT_A]
        assert position1.strategy_state["initial_recovered"] is True
        assert position1.post_trim_peak_price == pytest.approx(0.0004)
        # abrupt stop: monitor snapshot was refreshed (as the live loop
        # does on every data poll), but no finalize/close transition
        engine1.write_monitor_artifacts()
        engine1.close()

        engine2 = PaperTradingEngine(cfg, quiet=True, resume=True)
        position2 = engine2.runtimes[0].open_by_mint[MINT_A]
        # runner state NOT reset by the restart
        assert position2.strategy_state["initial_recovered"] is True
        assert position2.plan.trailing_stop_pct == pytest.approx(0.30)
        assert position2.post_trim_peak_price == pytest.approx(0.0004)
        assert position2.peak_price == pytest.approx(0.0004)

        # 2.5x < 2.8x (= 4x * 0.7): the trailing stop must fire
        engine2.process_snapshot(
            self._tier_snap(1_800.0, 0.00025, 100_000, 60_000))
        assert engine2.runtimes[0].open_by_mint == {}
        record = final_positions(engine2.run_dir)[position2.paper_trade_id]
        assert record["status"] == STATUS_STOPPED
        assert record["reason_closed"].startswith("TRAILING_STOP")
        fills = read_jsonl(str(Path(engine2.run_dir) / FILLS_FILE))
        assert fills[-1]["leg"] == "RUNNER_CLOSE"
        engine2.close()

    def test_restart_from_transition_row_alone_keeps_ledger_peak(
            self, tmp_path):
        """Even without a fresh monitor snapshot, the ledger row written at
        the recovery transition carries its peak (post-fix) and restores."""
        cfg = self._runner_config(tmp_path)
        engine1 = PaperTradingEngine(cfg, quiet=True)
        engine1.process_snapshot(
            self._tier_snap(0.0, 0.0001, 40_000, 50_000, 2, 70.0))
        engine1.process_snapshot(
            self._tier_snap(600.0, 0.0003, 120_000, 60_000))
        engine1.close()  # crash right after the recovery transition row

        engine2 = PaperTradingEngine(cfg, quiet=True, resume=True)
        position = engine2.runtimes[0].open_by_mint[MINT_A]
        assert position.strategy_state["initial_recovered"] is True
        assert position.post_trim_peak_price == pytest.approx(0.0003)
        assert position.plan.trailing_stop_pct == pytest.approx(0.30)
        engine2.close()


class TestReplayRunDirGuard:
    """Codex MEDIUM finding: replay must not append into a used run dir."""

    def _snaps(self):
        return [snap(ts=0.0, price=0.0001), snap(ts=60.0, price=0.00016)]

    def test_fresh_run_dir_succeeds(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5})
        summary = run_replay(cfg, self._snaps(), quiet=True)
        assert summary["strategies"]["s1"]["closed_trades"] == 1

    def test_second_replay_same_run_dir_refuses_by_default(self, tmp_path):
        from PHX2.paper_trading.engine import ReplayRunDirError
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5})
        run_replay(cfg, self._snaps(), quiet=True)
        with pytest.raises(ReplayRunDirError, match="--overwrite-run"):
            run_replay(cfg, self._snaps(), quiet=True)
        # the refused attempt appended nothing: still OPEN row + close row
        rows = read_jsonl(str(tmp_path / "t" / POSITIONS_FILE))
        assert len(rows) == 2

    def test_overwrite_run_resets_and_is_deterministic(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5})
        run_replay(cfg, self._snaps(), quiet=True)
        run_dir = tmp_path / "t"
        first_positions = (run_dir / POSITIONS_FILE).read_bytes()
        first_fills = (run_dir / FILLS_FILE).read_bytes()
        run_replay(cfg, self._snaps(), quiet=True, overwrite_run=True)
        assert (run_dir / POSITIONS_FILE).read_bytes() == first_positions
        assert (run_dir / FILLS_FILE).read_bytes() == first_fills

    def test_live_engine_not_blocked_by_replay_guard(self, tmp_path):
        from PHX2.paper_trading.engine import MODE_LIVE_PAPER
        cfg = one_strategy_config(tmp_path)
        engine1 = PaperTradingEngine(cfg, mode=MODE_LIVE_PAPER, quiet=True)
        engine1.process_snapshot(snap(ts=0.0))
        engine1.close()
        # resume over the same (artifact-bearing) dir stays allowed
        engine2 = PaperTradingEngine(cfg, mode=MODE_LIVE_PAPER, quiet=True,
                                     resume=True)
        assert len(engine2.runtimes[0].open_by_mint) == 1
        engine2.close()

    def test_replay_cli_flag(self, tmp_path):
        import json as _json
        from PHX2.scripts.phx2_replay_paper_trade import main as replay_main
        feed = tmp_path / "in.jsonl"
        feed.write_text(_json.dumps({
            "token_mint": "C" * 40 + "pump",
            "observed_at_utc": "2026-07-01T00:00:00Z",
            "current_price": "0.0001",
            "current_market_cap_usd": "100000",
            "liquidity_usd": "50000"}) + "\n", encoding="utf-8")
        args = ["--inputs", str(feed), "--out-root", str(tmp_path / "out"),
                "--run-id", "cli", "--quiet"]
        assert replay_main(args) == 0
        assert replay_main(args) == 3  # refused: run dir already used
        assert replay_main(args + ["--overwrite-run"]) == 0


class TestArtifacts:
    def test_equity_curve_and_summary_written(self, tmp_path):
        cfg = one_strategy_config(tmp_path, params={"take_profit_pct": 0.5},
                                  run={"equity_curve_bucket_seconds": 60.0})
        engine, summary = run_engine(cfg, [
            snap(ts=0.0, price=0.0001),
            snap(ts=200.0, price=0.00016),
        ])
        equity_rows = read_jsonl(str(Path(engine.run_dir) / EQUITY_FILE))
        assert equity_rows, "equity curve must have rows"
        assert {"equity_usd", "realized_pnl_usd", "unrealized_pnl_usd",
                "open_positions", "strategy_name"} <= set(equity_rows[0])
        payload = json.loads((Path(engine.run_dir) / SUMMARY_FILE).read_text())
        assert payload["schema_version"] == "phx2_paper_v1"
        assert payload["strategy_ranking"]
        assert summary["strategies"]["s1"]["total_pnl_usd"] > 0
