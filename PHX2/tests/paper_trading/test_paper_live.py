"""Live active paper loop tests: tailing, dedupe, restart, artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.paper_trading.config import (
    END_OF_STREAM_LEAVE_OPEN,
    PaperConfig,
    PROFILE_FIXED_USD,
    SizingProfileConfig,
    STRATEGY_CONFIG_PLAN,
    StrategyConfig,
    default_strategy_params,
)
from PHX2.paper_trading.engine import MODE_LIVE_PAPER, PaperTradingEngine
from PHX2.paper_trading.ledger import (
    CHECKPOINTS_FILE,
    HEARTBEAT_FILE,
    LIVE_MONITOR_FILE,
    SUMMARY_FILE,
    read_jsonl,
)
from PHX2.paper_trading.live import (
    load_checkpoints,
    restore_checkpoints,
    run_live_loop,
)
from PHX2.paper_trading.models import (
    STATUS_DATA_LOST,
    STATUS_OPEN,
    STATUS_TAKE_PROFIT,
    utc_iso,
)
from PHX2.paper_trading.pricing import TailingSnapshotSource

MINT = "L" * 40 + "pump"
BASE_TS = 1_750_000_000.0  # arbitrary fixed epoch


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def write_record(path: Path, ts_epoch: float, price: float,
                 mc: float = 100_000.0, lp: float = 50_000.0,
                 mint: str = MINT) -> None:
    record = {
        "token_mint": mint,
        "observed_at_utc": utc_iso(ts_epoch),
        "current_price": str(price),
        "current_market_cap_usd": str(mc),
        "liquidity_usd": str(lp),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record) + "\n")


def live_config(tmp_path, take_profit=0.5, sim=None) -> PaperConfig:
    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path / "out")
    cfg.run.run_id = "live_t"
    cfg.run.heartbeat_every_seconds = 0
    cfg.run.equity_curve_bucket_seconds = 0
    cfg.run.end_of_stream_policy = END_OF_STREAM_LEAVE_OPEN
    for key, value in (sim or {}).items():
        setattr(cfg.market_sim, key, value)
    cfg.sizing_profiles = {"p": SizingProfileConfig(
        profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
        max_buy_pct_of_liquidity=None, max_abs_notional_usd=None)}
    params = dict(default_strategy_params(STRATEGY_CONFIG_PLAN))
    params["take_profit_pct"] = take_profit
    cfg.strategies = [StrategyConfig(
        name="s1", strategy_type=STRATEGY_CONFIG_PLAN,
        sizing_profile="p", params=params)]
    return cfg


def make_engine(cfg, wall_clock=None, resume=True) -> PaperTradingEngine:
    return PaperTradingEngine(cfg, mode=MODE_LIVE_PAPER, resume=resume,
                              quiet=True, wall_clock=wall_clock)


def run_once(engine, source, clock) -> "object":
    return run_live_loop(engine, source, poll_seconds=1.0, once=True,
                         clock=clock, sleep=clock.sleep,
                         wall_heartbeat_seconds=1e9)


class TestLiveLoop:
    def test_processes_backlog_then_appended_records(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "candidates.jsonl"
        write_record(stream, BASE_TS, 0.0001)

        cfg = live_config(tmp_path)
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        engine.watch_inputs = [str(feed)]
        source = TailingSnapshotSource([str(feed)])

        result = run_once(engine, source, clock)
        assert result.snapshots_processed == 1
        assert result.stop_reason == "ONCE_COMPLETE"
        runtime = engine.runtimes[0]
        assert len(runtime.open_by_mint) == 1  # actively holding

        # New record arrives: position is re-priced and takes profit.
        write_record(stream, BASE_TS + 60.0, 0.00016)
        result = run_once(engine, source, clock)
        assert result.snapshots_processed == 1
        assert runtime.open_by_mint == {}
        closed = read_jsonl(str(Path(engine.run_dir)
                                / "paper_closed_positions.jsonl"))
        assert closed and closed[-1]["status"] == STATUS_TAKE_PROFIT
        engine.close()

    def test_does_not_reprocess_duplicates_within_a_run(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        write_record(feed / "a.jsonl", BASE_TS, 0.0001)
        cfg = live_config(tmp_path)
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        source = TailingSnapshotSource([str(feed)])
        assert run_once(engine, source, clock).snapshots_processed == 1
        # same file, no growth: nothing new to process
        assert run_once(engine, source, clock).snapshots_processed == 0
        engine.close()

    def test_restart_resumes_positions_and_offsets(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "a.jsonl"
        write_record(stream, BASE_TS, 0.0001)
        cfg = live_config(tmp_path)

        clock1 = FakeClock()
        engine1 = make_engine(cfg, wall_clock=lambda: BASE_TS + clock1.t)
        source1 = TailingSnapshotSource([str(feed)])
        run_once(engine1, source1, clock1)
        run_dir = engine1.run_dir
        assert len(engine1.runtimes[0].open_by_mint) == 1
        engine1.close()  # simulated stop

        checkpoints = load_checkpoints(run_dir)
        assert checkpoints["offsets"], "offsets must be checkpointed"
        offset = next(iter(checkpoints["offsets"].values()))
        assert offset == stream.stat().st_size

        # Restart: open position reloads, offsets reload, no reprocessing.
        clock2 = FakeClock(10.0)
        engine2 = make_engine(cfg, wall_clock=lambda: BASE_TS + clock2.t)
        source2 = TailingSnapshotSource([str(feed)])
        restored = restore_checkpoints(engine2, source2)
        assert restored == 1
        runtime = engine2.runtimes[0]
        assert len(runtime.open_by_mint) == 1
        assert runtime.open_by_mint[MINT].status == STATUS_OPEN
        assert run_once(engine2, source2, clock2).snapshots_processed == 0

        # The reloaded position is still actively managed: profit closes it.
        write_record(stream, BASE_TS + 120.0, 0.00016)
        assert run_once(engine2, source2, clock2).snapshots_processed == 1
        assert runtime.open_by_mint == {}
        engine2.close()

    def test_idle_tick_fires_data_lost_when_feed_dies(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        write_record(feed / "a.jsonl", BASE_TS, 0.0001)
        cfg = live_config(tmp_path,
                          sim={"data_lost_after_seconds": 1_800.0,
                               "data_lost_value_ratio": 0.25})
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        source = TailingSnapshotSource([str(feed)])
        run_once(engine, source, clock)
        assert len(engine.runtimes[0].open_by_mint) == 1

        # Feed goes dark; wall time advances past the data-lost horizon.
        clock.t = 2_000.0
        run_once(engine, source, clock)
        assert engine.runtimes[0].open_by_mint == {}
        closed = read_jsonl(str(Path(engine.run_dir)
                                / "paper_closed_positions.jsonl"))
        assert closed[-1]["status"] == STATUS_DATA_LOST
        engine.close()

    def test_graceful_stop_and_interrupt(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        cfg = live_config(tmp_path)
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        source = TailingSnapshotSource([str(feed)])

        result = run_live_loop(engine, source, poll_seconds=1.0,
                               clock=clock, sleep=clock.sleep,
                               should_stop=lambda: True,
                               wall_heartbeat_seconds=1e9)
        assert result.stop_reason == "STOP_REQUESTED"
        assert (Path(engine.run_dir) / HEARTBEAT_FILE).exists()
        assert (Path(engine.run_dir) / CHECKPOINTS_FILE).exists()

        def interrupting_sleep(seconds):
            raise KeyboardInterrupt

        result = run_live_loop(engine, source, poll_seconds=1.0,
                               clock=clock, sleep=interrupting_sleep,
                               wall_heartbeat_seconds=1e9)
        assert result.stop_reason == "INTERRUPTED"
        engine.close()

    def test_max_runtime_stops_loop(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        cfg = live_config(tmp_path)
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        source = TailingSnapshotSource([str(feed)])
        result = run_live_loop(engine, source, poll_seconds=5.0,
                               max_runtime_seconds=12.0,
                               clock=clock, sleep=clock.sleep,
                               wall_heartbeat_seconds=1e9)
        assert result.stop_reason == "MAX_RUNTIME"
        assert result.polls >= 2
        engine.close()

    def test_heartbeat_and_live_monitor_artifacts(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        write_record(feed / "a.jsonl", BASE_TS, 0.0001)
        cfg = live_config(tmp_path)
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        engine.watch_inputs = [str(feed)]
        source = TailingSnapshotSource([str(feed)])
        run_once(engine, source, clock)

        heartbeat = json.loads(
            (Path(engine.run_dir) / HEARTBEAT_FILE).read_text())
        assert heartbeat["run_id"] == engine.run_id
        assert heartbeat["mode"] == MODE_LIVE_PAPER
        assert heartbeat["watch_inputs"] == [str(feed)]
        assert heartbeat["snapshots_processed"] == 1
        assert heartbeat["heartbeat_utc"] is not None
        assert heartbeat["uptime_seconds"] is not None

        monitor = json.loads(
            (Path(engine.run_dir) / LIVE_MONITOR_FILE).read_text())
        assert monitor["strategies"]["s1"]["open_positions"] == 1
        assert monitor["last_record"]["mint"] == MINT
        assert monitor["watch_inputs"] == [str(feed)]
        assert "best_open" in monitor and "last_skip" in monitor
        engine.close()

    def test_dashboard_artifacts_update_during_live(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "a.jsonl"
        write_record(stream, BASE_TS, 0.0001)
        cfg = live_config(tmp_path)
        clock = FakeClock()
        engine = make_engine(cfg, wall_clock=lambda: BASE_TS + clock.t)
        source = TailingSnapshotSource([str(feed)])
        run_once(engine, source, clock)
        summary_path = Path(engine.run_dir) / SUMMARY_FILE
        first = json.loads(summary_path.read_text())
        assert first["strategies"]["s1"]["open_trades"] == 1

        write_record(stream, BASE_TS + 60.0, 0.00016)  # take profit
        run_once(engine, source, clock)
        second = json.loads(summary_path.read_text())
        assert second["strategies"]["s1"]["open_trades"] == 0
        assert second["strategies"]["s1"]["closed_trades"] == 1
        engine.close()
