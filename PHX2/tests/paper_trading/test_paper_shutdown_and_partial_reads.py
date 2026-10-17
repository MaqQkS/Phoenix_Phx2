"""Shutdown final-flush + partial-read tolerance tests.

Covers two live-loop fixes observed on a 2h free-tier run:

PROBLEM 1 -- the final ``paper_summary.json`` must be flushed AFTER the engine
has caught up and must reflect the SAME settled open-position marks as
``live_monitor.json`` / ``paper_open_positions.json`` (they had drifted: the
summary carried stale entry-time marks while the monitor showed the fresh,
worse unrealized PnL). Verified on both a normal stop and a KeyboardInterrupt.

PROBLEM 2 -- the tailing JSONL reader must not log persistent PARSE_ERRORs for
a partial trailing line. The real cause was CRLF byte-accounting: a text-mode
read translated ``\\r\\n`` -> ``\\n`` and the offset under-counted one byte per
line ending, drifting the next seek into mid-line bytes ("Expecting value" /
"Extra data"). Fixed by tracking exact raw-byte offsets; a genuinely malformed
COMPLETE line still errors.

Also re-confirms the risk gate: a RISK_HIGH candidate is entered only by the
high_risk_observer strategy and skipped (HIGH_RISK_*) by the normal fleet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.paper_trading.config import (
    END_OF_STREAM_LEAVE_OPEN,
    PaperConfig,
    PROFILE_FIXED_USD,
    STRATEGY_CONFIG_PLAN,
    SizingProfileConfig,
    StrategyConfig,
    default_config,
    default_strategy_params,
)
from PHX2.paper_trading.engine import MODE_LIVE_PAPER, PaperTradingEngine
from PHX2.paper_trading.ledger import (
    ERRORS_FILE,
    LIVE_MONITOR_FILE,
    OPEN_POSITIONS_FILE,
    POSITIONS_FILE,
    SUMMARY_FILE,
    read_jsonl,
)
from PHX2.paper_trading.live import run_live_loop
from PHX2.paper_trading.models import (
    CandidateSnapshot,
    STATUS_OPEN,
    STATUS_SKIPPED_HIGH_RISK,
    utc_iso,
)
from PHX2.paper_trading.pricing import TailingSnapshotSource, load_snapshots
from PHX2.paper_trading.risk import RISK_HIGH

MINT = "S" * 40 + "pump"
BASE_TS = 1_750_000_000.0


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _record_text(ts_epoch: float, price: float, mc: float = 100_000.0,
                 lp: float = 50_000.0, mint: str = MINT) -> str:
    return json.dumps({
        "token_mint": mint,
        "observed_at_utc": utc_iso(ts_epoch),
        "current_price": str(price),
        "current_market_cap_usd": str(mc),
        "liquidity_usd": str(lp),
    })


def append_line(path: Path, text: str, newline: str = "\n") -> None:
    with path.open("ab") as handle:
        handle.write((text + newline).encode("utf-8"))


def append_raw(path: Path, text: str) -> None:
    """Append bytes with NO line terminator (a mid-write partial fragment)."""
    with path.open("ab") as handle:
        handle.write(text.encode("utf-8"))


def no_exit_live_config(tmp_path) -> PaperConfig:
    """Single CONFIG_PLAN strategy with no TP/SL/trailing/max-hold, so an open
    position survives price moves and its mark can be checked at shutdown."""
    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path / "out")
    cfg.run.run_id = "flush_t"
    cfg.run.heartbeat_every_seconds = 0
    cfg.run.equity_curve_bucket_seconds = 0
    cfg.run.end_of_stream_policy = END_OF_STREAM_LEAVE_OPEN
    cfg.sizing_profiles = {"p": SizingProfileConfig(
        profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
        max_buy_pct_of_liquidity=None, max_abs_notional_usd=None)}
    cfg.strategies = [StrategyConfig(
        name="config_plan", strategy_type=STRATEGY_CONFIG_PLAN,
        sizing_profile="p",
        params=default_strategy_params(STRATEGY_CONFIG_PLAN))]
    return cfg


def make_live_engine(cfg, clock) -> PaperTradingEngine:
    return PaperTradingEngine(cfg, mode=MODE_LIVE_PAPER, resume=True,
                              quiet=True, wall_clock=lambda: BASE_TS + clock.t)


def single_offset(source: TailingSnapshotSource) -> int:
    values = list(source.offsets.values())
    assert len(values) == 1
    return values[0]


# ---------------------------------------------------------------------------
# PROBLEM 1 -- final summary reflects settled open-position marks
# ---------------------------------------------------------------------------


class TestFinalSummaryFlush:
    def _seed_open_position_with_moved_mark(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "candidates.jsonl"
        append_line(stream, _record_text(BASE_TS, 0.0001))          # entry
        append_line(stream, _record_text(BASE_TS + 30.0, 0.00008))  # -20% mark
        return feed

    def _assert_summary_matches_open_marks(self, engine):
        run_dir = Path(engine.run_dir)
        summary = json.loads((run_dir / SUMMARY_FILE).read_text())
        openpos = json.loads((run_dir / OPEN_POSITIONS_FILE).read_text())
        monitor = json.loads((run_dir / LIVE_MONITOR_FILE).read_text())

        assert len(openpos["open_positions"]) == 1
        op_unreal = openpos["open_positions"][0]["unrealized_pnl_usd"]
        # The mark must reflect the -20% move, NOT the ~flat entry mark; if the
        # summary were stale it would show the entry value (~0).
        assert op_unreal < -1.0

        summ_unreal = summary["strategies"]["config_plan"]["unrealized_pnl_usd"]
        mon_unreal = monitor["strategies"]["config_plan"]["unrealized_pnl_usd"]
        assert summ_unreal == pytest.approx(op_unreal, abs=1e-6)
        assert summ_unreal == pytest.approx(mon_unreal, abs=1e-6)
        # Written on the same settled beat -> identical event-time stamps.
        assert summary["as_of_utc"] == monitor["as_of_utc"] == openpos["as_of_utc"]

    def test_final_summary_matches_marks_on_normal_stop(self, tmp_path):
        feed = self._seed_open_position_with_moved_mark(tmp_path)
        clock = FakeClock()
        engine = make_live_engine(no_exit_live_config(tmp_path), clock)
        source = TailingSnapshotSource([str(feed)])
        result = run_live_loop(engine, source, poll_seconds=1.0, once=True,
                               clock=clock, sleep=clock.sleep,
                               wall_heartbeat_seconds=1e9)
        engine.close()
        assert result.stop_reason == "ONCE_COMPLETE"
        self._assert_summary_matches_open_marks(engine)

    def test_final_summary_matches_marks_on_max_runtime(self, tmp_path):
        feed = self._seed_open_position_with_moved_mark(tmp_path)
        clock = FakeClock()
        engine = make_live_engine(no_exit_live_config(tmp_path), clock)
        source = TailingSnapshotSource([str(feed)])
        result = run_live_loop(engine, source, poll_seconds=5.0,
                               max_runtime_seconds=12.0, clock=clock,
                               sleep=clock.sleep, wall_heartbeat_seconds=1e9)
        engine.close()
        assert result.stop_reason == "MAX_RUNTIME"
        self._assert_summary_matches_open_marks(engine)

    def test_final_summary_matches_marks_on_keyboardinterrupt(self, tmp_path):
        feed = self._seed_open_position_with_moved_mark(tmp_path)
        clock = FakeClock()
        engine = make_live_engine(no_exit_live_config(tmp_path), clock)
        source = TailingSnapshotSource([str(feed)])

        def interrupt(_seconds):
            raise KeyboardInterrupt

        result = run_live_loop(engine, source, poll_seconds=1.0, clock=clock,
                               sleep=interrupt, wall_heartbeat_seconds=1e9)
        engine.close()
        assert result.stop_reason == "INTERRUPTED"
        self._assert_summary_matches_open_marks(engine)

    def test_final_flush_survives_a_broken_summary_write(self, tmp_path):
        # Totality: a failure in the FINAL flush must be recorded, not crash
        # shutdown. The in-loop write succeeds; only the final-settle write
        # (after the loop breaks) raises.
        feed = self._seed_open_position_with_moved_mark(tmp_path)
        clock = FakeClock()
        engine = make_live_engine(no_exit_live_config(tmp_path), clock)
        source = TailingSnapshotSource([str(feed)])

        real_write = engine.write_summary_artifacts
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                return real_write()             # in-loop write succeeds
            raise RuntimeError("disk full")     # final-settle write fails

        engine.write_summary_artifacts = flaky  # type: ignore[assignment]
        result = run_live_loop(engine, source, poll_seconds=1.0, once=True,
                               clock=clock, sleep=clock.sleep,
                               wall_heartbeat_seconds=1e9)
        engine.close()
        # Loop still returned cleanly and recorded the flush failure.
        assert result.stop_reason == "ONCE_COMPLETE"
        assert "final_flush_error" in result.details


# ---------------------------------------------------------------------------
# PROBLEM 2 -- CRLF tailing: partial trailing line tolerated, offsets exact
# ---------------------------------------------------------------------------


class TestPartialTrailingReads:
    def test_crlf_offsets_are_exact_no_lag(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "watch_state.jsonl"
        for i in range(5):
            append_line(stream, _record_text(BASE_TS + i, 0.0001),
                        newline="\r\n")
        source = TailingSnapshotSource([str(feed)])
        snaps, errors = source.poll()
        assert errors == []
        assert len(snaps) == 5
        # Exact raw-byte accounting: the offset equals the full CRLF byte size.
        # The old text-mode reader under-counted 1 byte per CRLF (lag of 5),
        # which is exactly what drifted later seeks into mid-line PARSE_ERRORs.
        assert single_offset(source) == stream.stat().st_size

    def test_crlf_partial_trailing_line_no_error_then_processed(self, tmp_path):
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "watch_state.jsonl"
        for i in range(3):
            append_line(stream, _record_text(BASE_TS + i, 0.0001),
                        newline="\r\n")
        full = _record_text(BASE_TS + 3, 0.0002)
        append_raw(stream, full[:20])  # truncated trailing fragment, no CRLF

        source = TailingSnapshotSource([str(feed)])
        snaps, errors = source.poll()
        assert errors == []            # the partial tail is NOT an error row
        assert len(snaps) == 3         # only the complete records consumed
        # The partial bytes were left unconsumed for a later poll.
        assert single_offset(source) < stream.stat().st_size

        # Complete the truncated line, then append one more full record.
        append_line(stream, full[20:], newline="\r\n")
        append_line(stream, _record_text(BASE_TS + 4, 0.0003), newline="\r\n")
        snaps2, errors2 = source.poll()
        assert errors2 == []
        assert len(snaps2) == 2        # the completed record + the new one
        assert single_offset(source) == stream.stat().st_size

    def test_malformed_complete_crlf_line_still_errors(self, tmp_path):
        # A newline-terminated line that is invalid JSON is a genuinely
        # malformed COMPLETE line and must still produce a PARSE_ERROR.
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "pricing_tail.jsonl"
        append_line(stream, _record_text(BASE_TS, 0.0001), newline="\r\n")
        append_line(stream, "not valid json {{{", newline="\r\n")
        source = TailingSnapshotSource([str(feed)])
        snaps, errors = source.poll()
        assert len(snaps) == 1
        assert len(errors) == 1
        assert errors[0]["kind"] == "PARSE_ERROR"

    def test_live_loop_over_crlf_feed_logs_no_parse_errors(self, tmp_path):
        # End-to-end: drive the live loop over a CRLF feed that the "producer"
        # keeps extending with a partial trailing write before every poll.
        feed = tmp_path / "feed"
        feed.mkdir()
        stream = feed / "pricing_tail.jsonl"
        clock = FakeClock()
        engine = make_live_engine(no_exit_live_config(tmp_path), clock)
        source = TailingSnapshotSource([str(feed)])

        for poll_i in range(6):
            for j in range(4):
                append_line(stream,
                            _record_text(BASE_TS + poll_i * 10 + j, 0.0001),
                            newline="\r\n")
            frag = _record_text(BASE_TS + poll_i * 10 + 9, 0.0002)
            append_raw(stream, frag[:12])          # partial write before poll
            run_live_loop(engine, source, poll_seconds=1.0, once=True,
                          clock=clock, sleep=clock.sleep,
                          wall_heartbeat_seconds=1e9)
            append_line(stream, frag[12:], newline="\r\n")  # complete it

        engine.close()
        errors = read_jsonl(str(Path(engine.run_dir) / ERRORS_FILE))
        parse_errors = [e for e in errors if e.get("kind") == "PARSE_ERROR"]
        assert parse_errors == [], f"unexpected PARSE_ERRORs: {parse_errors[:3]}"

    def test_load_snapshots_partial_trailing_line_skipped(self, tmp_path):
        f = tmp_path / "a.jsonl"
        good = _record_text(BASE_TS, 0.1)
        full = _record_text(BASE_TS + 1, 0.2)
        with f.open("wb") as handle:
            handle.write((good + "\r\n").encode("utf-8"))
            handle.write(full[:15].encode("utf-8"))   # unterminated partial

        snaps, errors = load_snapshots([str(f)])
        assert errors == []            # partial trailing line is not an error
        assert len(snaps) == 1

        append_line(f, full[15:], newline="\r\n")      # complete the record
        snaps2, errors2 = load_snapshots([str(f)])
        assert errors2 == []
        assert len(snaps2) == 2

    def test_load_snapshots_malformed_complete_line_still_errors(self, tmp_path):
        f = tmp_path / "b.jsonl"
        f.write_text(_record_text(BASE_TS, 0.1) + "\ngarbage{{{\n",
                     encoding="utf-8")
        snaps, errors = load_snapshots([str(f)])
        assert len(snaps) == 1
        assert len(errors) == 1 and errors[0]["kind"] == "PARSE_ERROR"


# ---------------------------------------------------------------------------
# Risk gate re-confirmation (PROBLEM-adjacent regression guard)
# ---------------------------------------------------------------------------


class TestRiskGateStillHolds:
    def test_high_risk_entered_only_by_observer_normal_fleet_skips(self, tmp_path):
        cfg = default_config()
        cfg.run.output_root = str(tmp_path)
        cfg.run.run_id = "risk_t"
        cfg.run.heartbeat_every_seconds = 0
        cfg.run.equity_curve_bucket_seconds = 0
        engine = PaperTradingEngine(cfg, quiet=True)
        engine.process_snapshot(CandidateSnapshot(
            ts_epoch=1_000.0, mint="R" * 40 + "pump", price_usd=0.0001,
            market_cap_usd=10_000.0, liquidity_usd=50_000.0,
            risk_label=RISK_HIGH, risk_reasons=["LIQUIDITY_COLLAPSE"]))
        engine.close()

        latest = {}
        for rec in read_jsonl(str(Path(engine.run_dir) / POSITIONS_FILE)):
            latest[rec["paper_trade_id"]] = rec
        records = list(latest.values())

        opened = [r for r in records if r["status"] == STATUS_OPEN]
        assert [r["strategy_name"] for r in opened] == ["high_risk_observer"]

        # config_plan always engages a priced candidate -> deterministic skip.
        config_plan = [r for r in records if r["strategy_name"] == "config_plan"]
        assert config_plan
        assert config_plan[0]["status"] == STATUS_SKIPPED_HIGH_RISK
        assert str(config_plan[0]["reason_closed"]).startswith("HIGH_RISK_")

        # Every recorded HIGH_RISK skip belongs to a NON-observer strategy.
        skipped = [r for r in records
                   if r["status"] == STATUS_SKIPPED_HIGH_RISK]
        assert skipped
        assert all(r["strategy_name"] != "high_risk_observer" for r in skipped)
