"""Risk-aware paper protection tests.

Covers the producer->paper risk contract: snapshot normalization of risk tags,
the engine's RISK_HIGH entry gate (recorded skips, no fake trades), the
HIGH_RISK_OBSERVER bucket routing, BALA_PLAN's medium-risk conservatism, the
paper-rug-history escalation, reporting fields, and the producer-internal
input-file exclusion (polling_seen.jsonl).
"""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.paper_trading.config import (
    PaperConfig,
    PROFILE_FIXED_USD,
    SizingProfileConfig,
    STRATEGY_BALA_PLAN,
    STRATEGY_CONFIG_PLAN,
    STRATEGY_HIGH_RISK_OBSERVER,
    StrategyConfig,
    default_config,
    default_strategy_params,
    load_config_dict,
)
from PHX2.paper_trading.engine import PaperTradingEngine
from PHX2.paper_trading.ledger import FILLS_FILE, POSITIONS_FILE, read_jsonl
from PHX2.paper_trading.models import (
    CandidateSnapshot,
    SKIP_STATUSES,
    STATUS_OPEN,
    STATUS_RUGGED,
    STATUS_SKIPPED_HIGH_RISK,
)
from PHX2.paper_trading.pricing import (
    EXCLUDED_INPUT_BASENAMES,
    discover_input_files,
    normalize_record,
)
from PHX2.paper_trading.reporting import build_ranking, summarize_strategy
from PHX2.paper_trading.risk import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE,
    SKIP_HIGH_RISK_SCAM_BUNDLE,
    SKIP_HIGH_RISK_TOO_HOT,
    high_risk_skip_reason,
    parse_risk_label,
    parse_risk_reasons,
)

MINT_A = "A" * 40 + "pump"
MINT_B = "B" * 40 + "pump"


def snap(mint=MINT_A, ts=1_000.0, price=0.0001, mc=100_000.0, lp=50_000.0,
         risk_label=None, risk_reasons=None):
    return CandidateSnapshot(
        ts_epoch=ts, mint=mint, price_usd=price, market_cap_usd=mc,
        liquidity_usd=lp, risk_label=risk_label,
        risk_reasons=list(risk_reasons or []))


def config_with(tmp_path, strategies) -> PaperConfig:
    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path)
    cfg.run.run_id = "t"
    cfg.run.heartbeat_every_seconds = 0
    cfg.run.equity_curve_bucket_seconds = 0
    cfg.sizing_profiles = {"p": SizingProfileConfig(
        profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
        max_buy_pct_of_liquidity=None, max_abs_notional_usd=None)}
    cfg.strategies = strategies
    return cfg


def one_config_plan(tmp_path, **strategy_kwargs) -> PaperConfig:
    return config_with(tmp_path, [StrategyConfig(
        name="s1", strategy_type=STRATEGY_CONFIG_PLAN, sizing_profile="p",
        params=default_strategy_params(STRATEGY_CONFIG_PLAN),
        **strategy_kwargs)])


def run_engine(cfg, snapshots):
    engine = PaperTradingEngine(cfg, quiet=True)
    for snapshot in snapshots:
        engine.process_snapshot(snapshot)
    engine.close()
    return engine


def final_positions(run_dir) -> dict:
    latest = {}
    for record in read_jsonl(str(Path(run_dir) / POSITIONS_FILE)):
        latest[record["paper_trade_id"]] = record
    return latest


# ---------------------------------------------------------------------------
# Contract parsing + snapshot normalization
# ---------------------------------------------------------------------------


class TestRiskContract:
    def test_parse_label_validates(self):
        assert parse_risk_label("RISK_HIGH") == RISK_HIGH
        assert parse_risk_label(" risk_low ") == RISK_LOW
        assert parse_risk_label("HIGH") is None
        assert parse_risk_label(7) is None
        assert parse_risk_label(None) is None

    def test_malformed_never_becomes_high(self):
        # Absence / garbage must resolve to UNKNOWN (None), never to danger.
        for bad in (None, "", "RISK_EXTREME", 1, ["RISK_HIGH"], {}):
            assert parse_risk_label(bad) is None

    def test_reason_parse_bounded_and_deduped(self):
        reasons = parse_risk_reasons(
            ["LP_THIN", "LP_THIN", 5, "", "MARKET_STALE"])
        assert reasons == ["LP_THIN", "MARKET_STALE"]

    def test_skip_reason_categories(self):
        assert high_risk_skip_reason(["LIQUIDITY_COLLAPSE"]) == \
            SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE
        assert high_risk_skip_reason(["POOL_TOO_HOT"]) == \
            SKIP_HIGH_RISK_TOO_HOT
        assert high_risk_skip_reason(["PRICE_SPIKE_DUMP"]) == \
            SKIP_HIGH_RISK_SCAM_BUNDLE
        assert high_risk_skip_reason([]) == SKIP_HIGH_RISK_SCAM_BUNDLE

    def test_normalize_record_extracts_risk(self):
        record = {
            "token_mint": MINT_A,
            "observed_at_utc": "2026-07-11T00:00:00Z",
            "market_context": {"current_price": "0.0001"},
            "risk_label": "RISK_HIGH",
            "risk_reasons": ["LIQUIDITY_COLLAPSE", "LP_THIN"],
        }
        s = normalize_record(record)
        assert s is not None
        assert s.risk_label == RISK_HIGH
        assert s.risk_reasons == ["LIQUIDITY_COLLAPSE", "LP_THIN"]
        assert s.to_record()["risk_label"] == RISK_HIGH

    def test_normalize_record_missing_risk_is_unknown(self):
        record = {"token_mint": MINT_A,
                  "observed_at_utc": "2026-07-11T00:00:00Z",
                  "current_price": 0.1}
        s = normalize_record(record)
        assert s is not None
        assert s.risk_label is None      # UNKNOWN, not HIGH
        assert s.risk_reasons == []


# ---------------------------------------------------------------------------
# Engine gate
# ---------------------------------------------------------------------------


class TestHighRiskEntryGate:
    def test_high_risk_skips_default_strategy(self, tmp_path):
        cfg = one_config_plan(tmp_path)
        engine = run_engine(cfg, [snap(
            risk_label=RISK_HIGH, risk_reasons=["LIQUIDITY_COLLAPSE"])])
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_SKIPPED_HIGH_RISK
        assert record["reason_closed"] == SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE
        assert record["risk_label_at_entry"] == RISK_HIGH
        assert "LIQUIDITY_COLLAPSE" in record["risk_reasons_at_entry"]
        # No fake trades: a risk skip never produces a fill or PnL.
        fills = read_jsonl(str(Path(engine.run_dir) / FILLS_FILE))
        assert fills == []
        assert record["realized_pnl_usd"] == 0.0
        assert STATUS_SKIPPED_HIGH_RISK in SKIP_STATUSES

    def test_high_risk_skip_emits_event(self, tmp_path):
        cfg = one_config_plan(tmp_path)
        engine = run_engine(cfg, [snap(
            risk_label=RISK_HIGH, risk_reasons=["POOL_TOO_HOT"])])
        events = read_jsonl(str(Path(engine.run_dir) / "paper_events.jsonl"))
        skip_events = [e for e in events
                       if e.get("event") == "ENTRY_SKIPPED_HIGH_RISK"]
        assert len(skip_events) == 1
        assert skip_events[0]["reason"] == SKIP_HIGH_RISK_TOO_HOT
        assert skip_events[0]["risk_label"] == RISK_HIGH

    def test_unknown_and_low_do_not_block(self, tmp_path):
        cfg = one_config_plan(tmp_path)
        engine = run_engine(cfg, [
            snap(mint=MINT_A),                       # no risk tag => UNKNOWN
            snap(mint=MINT_B, risk_label=RISK_LOW),
        ])
        records = final_positions(engine.run_dir).values()
        assert {r["mint"] for r in records} == {MINT_A, MINT_B}
        assert all(r["status"] == STATUS_OPEN for r in records)

    def test_allow_high_risk_flag_lets_entry_through(self, tmp_path):
        cfg = one_config_plan(tmp_path, allow_high_risk=True)
        engine = run_engine(cfg, [snap(
            risk_label=RISK_HIGH, risk_reasons=["PRICE_SPIKE_DUMP"])])
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_OPEN
        assert record["risk_label_at_entry"] == RISK_HIGH

    def test_risk_label_sticks_from_earlier_snapshot(self, tmp_path):
        # Tag arrives on a candidate record; the entry moment (a tail record
        # without risk fields) must still see the last known label.
        cfg = one_config_plan(tmp_path)
        engine = run_engine(cfg, [
            snap(ts=0.0, price=None, risk_label=RISK_HIGH,
                 risk_reasons=["LIQUIDITY_COLLAPSE"]),   # price-less tag record
            snap(ts=60.0),                               # priced, no tag
        ])
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_SKIPPED_HIGH_RISK

    def test_paper_rug_history_escalates(self, tmp_path):
        # Strategy A watches the mint rug; strategy B (fresh, never traded it)
        # is then refused with PAPER_RUG_HISTORY.
        strategies = [
            StrategyConfig(name="a", strategy_type=STRATEGY_CONFIG_PLAN,
                           sizing_profile="p",
                           params=default_strategy_params(STRATEGY_CONFIG_PLAN)),
            StrategyConfig(name="b", strategy_type=STRATEGY_CONFIG_PLAN,
                           sizing_profile="p",
                           params={**default_strategy_params(STRATEGY_CONFIG_PLAN),
                                   "min_entry_liquidity_usd": 60_000.0}),
        ]
        cfg = config_with(tmp_path, strategies)
        engine = run_engine(cfg, [
            snap(ts=0.0, lp=50_000.0),           # A enters; B blocked by LP floor
            snap(ts=60.0, lp=1_000.0),           # LP collapse => A rugged
            snap(ts=120.0, lp=80_000.0, price=0.00009),  # B would enter now
        ])
        records = list(final_positions(engine.run_dir).values())
        a_rec = next(r for r in records if r["strategy_name"] == "a")
        b_rec = next(r for r in records if r["strategy_name"] == "b")
        assert a_rec["status"] == STATUS_RUGGED
        assert b_rec["status"] == STATUS_SKIPPED_HIGH_RISK
        assert "PAPER_RUG_HISTORY" in b_rec["risk_reasons_at_entry"]


# ---------------------------------------------------------------------------
# Observer bucket
# ---------------------------------------------------------------------------


class TestHighRiskObserver:
    def observer_cfg(self, tmp_path, extra=None):
        strategies = [StrategyConfig(
            name="obs", strategy_type=STRATEGY_HIGH_RISK_OBSERVER,
            sizing_profile="p", allow_high_risk=True,
            params={**default_strategy_params(STRATEGY_HIGH_RISK_OBSERVER),
                    **(extra or {})})]
        return config_with(tmp_path, strategies)

    def test_observer_enters_only_high_risk(self, tmp_path):
        cfg = self.observer_cfg(tmp_path)
        engine = run_engine(cfg, [
            snap(mint=MINT_A, risk_label=RISK_HIGH,
                 risk_reasons=["PRICE_SPIKE_DUMP"]),
            snap(mint=MINT_B, risk_label=RISK_LOW),
        ])
        records = list(final_positions(engine.run_dir).values())
        assert len(records) == 1
        rec = records[0]
        assert rec["mint"] == MINT_A
        assert rec["status"] == STATUS_OPEN
        assert rec["reason_opened"].startswith("HIGH_RISK_OBSERVER_")
        assert rec["risk_label_at_entry"] == RISK_HIGH

    def test_observer_type_defaults_allow_high_risk_from_json(self):
        raw = default_config().to_dict()
        cfg = load_config_dict(raw)
        obs = next(s for s in cfg.strategies
                   if s.strategy_type == STRATEGY_HIGH_RISK_OBSERVER)
        assert obs.allow_high_risk is True

    def test_default_config_routes_high_risk_to_observer_only(self, tmp_path):
        # Full default-strategy fleet: a HIGH candidate lands ONLY in the
        # observer bucket; every other strategy records a HIGH_RISK skip or
        # ignores it — none opens a position for it.
        cfg = default_config()
        cfg.run.output_root = str(tmp_path)
        cfg.run.run_id = "t"
        cfg.run.heartbeat_every_seconds = 0
        cfg.run.equity_curve_bucket_seconds = 0
        engine = run_engine(cfg, [snap(
            risk_label=RISK_HIGH, risk_reasons=["LIQUIDITY_COLLAPSE"],
            mc=10_000.0)])
        records = list(final_positions(engine.run_dir).values())
        opened = [r for r in records if r["status"] == STATUS_OPEN]
        assert [r["strategy_name"] for r in opened] == ["high_risk_observer"]
        skipped = [r for r in records
                   if r["status"] == STATUS_SKIPPED_HIGH_RISK]
        assert skipped, "at least one default strategy recorded the refusal"
        assert all(r["strategy_name"] != "high_risk_observer"
                   for r in skipped)


# ---------------------------------------------------------------------------
# BALA_PLAN conservatism
# ---------------------------------------------------------------------------


def bala_cfg(tmp_path, extra_params=None):
    params = dict(default_strategy_params(STRATEGY_BALA_PLAN))
    params.update(extra_params or {})
    return config_with(tmp_path, [StrategyConfig(
        name="bala_plan", strategy_type=STRATEGY_BALA_PLAN,
        sizing_profile="p", params=params)])


def bala_dip_snap(**kw):
    """A Tier-2 dip moment (drawdown 70% via ath/mc) bala would normally buy."""
    defaults = dict(mint=MINT_A, ts=1_000.0, price=0.0001, mc=30_000.0,
                    lp=50_000.0)
    defaults.update(kw)
    s = snap(**defaults)
    s.ath_market_cap_usd = defaults["mc"] / 0.30   # 70% drawdown from ATH
    return s


class TestBalaPlanRiskConservatism:
    def test_bala_never_opens_high_risk(self, tmp_path):
        cfg = bala_cfg(tmp_path)
        engine = run_engine(cfg, [bala_dip_snap(
            risk_label=RISK_HIGH, risk_reasons=["PRICE_SPIKE_DUMP"])])
        record = next(iter(final_positions(engine.run_dir).values()))
        assert record["status"] == STATUS_SKIPPED_HIGH_RISK
        assert record["reason_closed"] == SKIP_HIGH_RISK_SCAM_BUNDLE

    def test_bala_medium_needs_strong_market(self, tmp_path):
        # MEDIUM + thin LP (below the 10k floor): refused, counted, no record
        # row (strategy-level veto happens before any intent).
        cfg = bala_cfg(tmp_path)
        engine = run_engine(cfg, [bala_dip_snap(
            lp=6_000.0, risk_label=RISK_MEDIUM, risk_reasons=["LP_THIN"])])
        assert final_positions(engine.run_dir) == {}
        machine = engine.runtimes[0].strategy.monitor_snapshot()
        assert machine["risk_medium_skips"] == 1
        assert "RISK_MEDIUM" in (machine["last_risk_skip"] or "")

    def test_bala_medium_strong_market_enters(self, tmp_path):
        cfg = bala_cfg(tmp_path)
        engine = run_engine(cfg, [bala_dip_snap(
            lp=25_000.0, mc=40_000.0,
            risk_label=RISK_MEDIUM, risk_reasons=["EARLY_VOLATILITY"])])
        records = list(final_positions(engine.run_dir).values())
        assert len(records) == 1
        assert records[0]["status"] == STATUS_OPEN
        assert records[0]["risk_label_at_entry"] == RISK_MEDIUM

    def test_bala_medium_stale_market_reason_blocks(self, tmp_path):
        # Strong LP/MC but a market-quality reason present => still refused.
        cfg = bala_cfg(tmp_path)
        engine = run_engine(cfg, [bala_dip_snap(
            lp=25_000.0, mc=40_000.0,
            risk_label=RISK_MEDIUM, risk_reasons=["MARKET_STALE"])])
        assert final_positions(engine.run_dir) == {}
        machine = engine.runtimes[0].strategy.monitor_snapshot()
        assert machine["risk_medium_skips"] == 1


# ---------------------------------------------------------------------------
# Reporting + inputs
# ---------------------------------------------------------------------------


class TestRiskReportingAndInputs:
    def test_summary_counts_high_risk_skips(self):
        records = [
            {"status": STATUS_SKIPPED_HIGH_RISK,
             "reason_closed": SKIP_HIGH_RISK_SCAM_BUNDLE},
            {"status": STATUS_SKIPPED_HIGH_RISK,
             "reason_closed": SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE},
            {"status": "CLOSED", "realized_pnl_usd": 5.0,
             "virtual_usd_size": 100.0, "risk_label_at_entry": "RISK_LOW"},
        ]
        summary = summarize_strategy("s1", records)
        assert summary["high_risk_skips"] == 2
        assert summary["high_risk_skip_reasons"] == {
            SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE: 1,
            SKIP_HIGH_RISK_SCAM_BUNDLE: 1,
        }
        assert "RISK_LOW" in summary["performance_by_risk_label"]
        # PnL totals exclude the skipped cohort by construction (skips carry
        # no cost/PnL).
        assert summary["total_pnl_usd"] == 5.0
        ranking = build_ranking({"s1": summary})
        assert ranking[0]["high_risk_skips"] == 2

    def test_polling_seen_excluded_from_dir_inputs(self, tmp_path):
        out = tmp_path / "run"
        out.mkdir()
        (out / "polling_seen.jsonl").write_text(
            json.dumps({"kind": "FREE_TIER_POLLING_SEEN", "pool": "x"}) + "\n",
            encoding="utf-8")
        (out / "pricing_tail.jsonl").write_text("{}\n", encoding="utf-8")
        found = discover_input_files([str(out)])
        names = {Path(p).name for p in found}
        assert "pricing_tail.jsonl" not in EXCLUDED_INPUT_BASENAMES
        assert names == {"pricing_tail.jsonl"}

    def test_polling_seen_kept_when_named_explicitly(self, tmp_path):
        target = tmp_path / "polling_seen.jsonl"
        target.write_text("{}\n", encoding="utf-8")
        found = discover_input_files([str(target)])
        assert [Path(p).name for p in found] == ["polling_seen.jsonl"]
