"""Strategy behavior tests: entries, exits, determinism, validation."""

from __future__ import annotations

import random

import pytest

from PHX2.paper_trading.config import (
    ConfigError,
    STRATEGY_BALA_PLAN,
    STRATEGY_CONFIG_PLAN,
    STRATEGY_MONKEY_HOLD,
    STRATEGY_MONKEY_RANDOM,
    STRATEGY_THREE_X,
    StrategyConfig,
    default_config,
    default_strategy_params,
    load_config_dict,
)
from PHX2.paper_trading.models import CandidateSnapshot, PaperPosition
from PHX2.paper_trading.strategy import (
    EXIT_PARTIAL,
    StrategyContext,
    build_strategy,
)


def snap(mint="M" * 44, ts=1_000.0, price=0.0001, mc=100_000.0,
         lp=50_000.0, tier=None, dd=None, ath=None, score=None):
    return CandidateSnapshot(ts_epoch=ts, mint=mint, price_usd=price,
                             market_cap_usd=mc, liquidity_usd=lp, tier=tier,
                             drawdown_pct=dd, ath_market_cap_usd=ath,
                             score=score)


def ctx(seed=7, now=1_000.0):
    return StrategyContext(rng=random.Random(seed), now_epoch=now)


def make(strategy_type, name="s1", **params):
    merged = dict(default_strategy_params(strategy_type))
    merged.update(params)
    return build_strategy(StrategyConfig(name=name,
                                         strategy_type=strategy_type,
                                         params=merged))


def bala_position(strat, entry_snap, context, engineless_size=100.0):
    """Build an open position the way the engine would (leg + state seed)."""
    intent = strat.wants_entry(entry_snap, context)
    assert intent is not None
    position = PaperPosition(paper_trade_id="t", strategy_name=strat.name,
                             run_id="r", mint=entry_snap.mint,
                             entry_liquidity=entry_snap.liquidity_usd,
                             entry_market_cap=entry_snap.market_cap_usd,
                             opened_at_epoch=entry_snap.ts_epoch,
                             plan=intent.plan)
    position.strategy_state.update(intent.state_seed)
    tokens = engineless_size / entry_snap.price_usd
    position.apply_buy_leg(intent.leg, entry_snap.ts_epoch, tokens,
                           engineless_size, entry_snap.price_usd,
                           engineless_size / tokens,
                           liquidity=entry_snap.liquidity_usd)
    position.mark_price(entry_snap.price_usd, entry_snap.ts_epoch)
    strat.on_position_opened(position)
    return position, intent


class TestBalaPlanMachine:
    def test_tier1_is_watch_only_by_default(self):
        strat = make(STRATEGY_BALA_PLAN)
        assert strat.wants_entry(snap(tier=1, dd=55.0), ctx()) is None
        track = strat._tracks[snap().mint]
        assert track.state == "WATCHING"

    def test_tier1_scout_when_enabled(self):
        strat = make(STRATEGY_BALA_PLAN, enable_scout_entry=True)
        intent = strat.wants_entry(snap(tier=1, dd=55.0), ctx())
        assert intent is not None
        assert intent.leg == "SCOUT"
        assert intent.size_fraction == pytest.approx(0.10)
        assert intent.state_seed["bala_state"] == "PAPER_SCOUT_OPEN"
        assert intent.state_seed["dca_count"] == 0

    def test_tier2_is_first_meaningful_dca(self):
        strat = make(STRATEGY_BALA_PLAN)
        intent = strat.wants_entry(snap(tier=2, dd=70.0), ctx())
        assert intent is not None
        assert "T2" in intent.reason
        assert intent.leg == "DCA_1"
        assert intent.size_fraction == pytest.approx(0.50)
        assert intent.state_seed["bala_state"] == "PAPER_DCA_1_OPEN"
        assert intent.state_seed["dca_count"] == 1
        assert intent.plan.take_profit_pct == pytest.approx(0.35)
        assert intent.plan.stop_loss_pct == pytest.approx(-0.30)
        assert intent.plan.max_hold_seconds == pytest.approx(21_600.0)

    def test_tier3_initial_entry_config(self):
        strat = make(STRATEGY_BALA_PLAN)
        assert strat.wants_entry(snap(tier=3, dd=85.0), ctx()) is not None
        strat = make(STRATEGY_BALA_PLAN, allow_tier3_initial_entry=False)
        assert strat.wants_entry(snap(tier=3, dd=85.0), ctx()) is None
        assert strat._tracks[snap().mint].state == "WATCHING"

    def test_audit_blocks_entry(self):
        strat = make(STRATEGY_BALA_PLAN, min_entry_liquidity_usd=None,
                     audit={"min_liquidity_usd": 5_000.0})
        assert strat.wants_entry(snap(tier=2, dd=70.0, lp=3_000.0),
                                 ctx()) is None
        track = strat._tracks[snap().mint]
        assert "AUDIT_LIQUIDITY_LOW" in track.audit_reasons

    def test_audit_age_rule_fails_closed_without_evidence(self):
        strat = make(STRATEGY_BALA_PLAN, audit={"max_age_seconds": 3_600.0})
        context = ctx(now=1_000.0)
        ok, reasons = strat.run_audit(snap(tier=2, dd=70.0), context)
        assert not ok and "AUDIT_AGE_UNKNOWN" in reasons
        aged = snap(tier=2, dd=70.0)
        aged.migration_ts_epoch = 1_000.0 - 7_200.0
        ok, reasons = strat.run_audit(aged, context)
        assert not ok and "AUDIT_TOO_OLD" in reasons

    def test_rejects_dip_outside_band(self):
        strat = make(STRATEGY_BALA_PLAN)
        assert strat.wants_entry(snap(tier=2, dd=50.0), ctx()) is None
        assert strat.wants_entry(snap(tier=2, dd=85.0), ctx()) is None

    def test_rejects_missing_price_and_low_liquidity(self):
        strat = make(STRATEGY_BALA_PLAN)
        assert strat.wants_entry(snap(price=None, tier=2, dd=70.0),
                                 ctx()) is None
        assert strat.wants_entry(snap(lp=100.0, tier=2, dd=70.0),
                                 ctx()) is None

    def test_requires_tier_by_default(self):
        strat = make(STRATEGY_BALA_PLAN, derive_tier_from_drawdown=False)
        assert strat.wants_entry(snap(tier=None, dd=70.0), ctx()) is None

    def test_derives_tier_from_drawdown(self):
        strat = make(STRATEGY_BALA_PLAN)
        intent = strat.wants_entry(snap(tier=None, dd=70.0), ctx())
        assert intent is not None and intent.leg == "DCA_1"

    def test_drawdown_computed_from_ath_when_missing(self):
        strat = make(STRATEGY_BALA_PLAN)
        # mc 30k vs ath 100k -> 70% drawdown -> tier 2 band
        intent = strat.wants_entry(
            snap(tier=2, dd=None, mc=30_000.0, ath=100_000.0), ctx())
        assert intent is not None

    def test_allowed_tiers_filter(self):
        strat = make(STRATEGY_BALA_PLAN, allowed_tiers=[1])
        assert strat.wants_entry(snap(tier=2, dd=70.0), ctx()) is None

    def test_entry_mc_filter(self):
        strat = make(STRATEGY_BALA_PLAN, max_entry_market_cap_usd=50_000.0)
        assert strat.wants_entry(snap(tier=2, dd=70.0, mc=100_000.0),
                                 ctx()) is None

    def test_invalid_config_raises(self):
        with pytest.raises(ValueError, match="tier_dip_bands"):
            make(STRATEGY_BALA_PLAN, tier_dip_bands={"1": [60.0, 50.0]})
        with pytest.raises(ValueError, match="stop_loss_pct"):
            make(STRATEGY_BALA_PLAN, stop_loss_pct=0.3)
        with pytest.raises(ValueError, match="dca_1_pct_of_max_position"):
            make(STRATEGY_BALA_PLAN, dca_1_pct_of_max_position=1.5)
        with pytest.raises(ValueError, match="max_dca_count"):
            make(STRATEGY_BALA_PLAN, max_dca_count=-1)
        with pytest.raises(ValueError, match="initials_recovery_multiple"):
            make(STRATEGY_BALA_PLAN, initials_recovery_multiple=0.5)


class TestBalaPlanDca:
    def _ctx_with_sizing(self, seed=7, now=1_000.0, max_size=150.0):
        from PHX2.paper_trading.models import SizingDecision
        context = ctx(seed=seed, now=now)
        decision = SizingDecision(profile="HYBRID_REALISTIC",
                                  final_size_usd=max_size,
                                  estimated_tokens_received=1.0)
        context.sizing_preview = lambda snapshot: decision
        return context

    def _scout_position(self, strat, context):
        entry = snap(tier=1, dd=55.0)
        position, intent = bala_position(strat, entry, context,
                                         engineless_size=15.0)
        assert intent.leg == "SCOUT"
        return position

    def test_tier2_triggers_dca1_from_scout(self):
        strat = make(STRATEGY_BALA_PLAN, enable_scout_entry=True,
                     min_time_between_dca_seconds=None)
        context = self._ctx_with_sizing()
        position = self._scout_position(strat, context)
        intents = strat.manage(position, snap(ts=1_200.0, tier=2, dd=70.0),
                               self._ctx_with_sizing(now=1_200.0))
        assert len(intents) == 1
        add = intents[0]
        assert add.leg == "DCA_1"
        assert add.size_usd == pytest.approx(150.0 * 0.5)
        assert add.state_seed["bala_state"] == "PAPER_DCA_1_OPEN"
        assert add.state_seed["dca_count"] == 1

    def test_tier3_triggers_dca2_only_after_dca1(self):
        strat = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None)
        context = self._ctx_with_sizing()
        entry = snap(tier=2, dd=70.0)
        position, intent = bala_position(strat, entry, context)
        assert intent.leg == "DCA_1"
        intents = strat.manage(position, snap(ts=2_000.0, tier=3, dd=85.0),
                               self._ctx_with_sizing(now=2_000.0))
        assert len(intents) == 1
        assert intents[0].leg == "DCA_2"
        assert intents[0].size_usd == pytest.approx(150.0 * 0.4)
        assert intents[0].state_seed["bala_state"] == "PAPER_DCA_2_OPEN"
        # a second tier-3 dip does not add a third leg
        position.strategy_state.update(intents[0].state_seed)
        position.apply_buy_leg("DCA_2", 2_000.0, 100.0, 60.0, 0.0001,
                               0.0001)
        again = strat.manage(position, snap(ts=3_000.0, tier=3, dd=85.0),
                             self._ctx_with_sizing(now=3_000.0))
        assert again == []

    def test_dca_time_gate(self):
        strat = make(STRATEGY_BALA_PLAN, enable_scout_entry=True,
                     min_time_between_dca_seconds=600.0)
        context = self._ctx_with_sizing()
        position = self._scout_position(strat, context)
        intents = strat.manage(position, snap(ts=1_060.0, tier=2, dd=70.0),
                               self._ctx_with_sizing(now=1_060.0))
        assert intents == []
        assert position.strategy_state["last_dca_skip"] == "DCA_TIME_GATE"

    def test_dca_blocked_on_liquidity_collapse(self):
        strat = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None,
                     do_not_dca_if_liquidity_down_pct_exceeds=40.0)
        context = self._ctx_with_sizing()
        position, _ = bala_position(strat, snap(tier=2, dd=70.0), context)
        dip = snap(ts=2_000.0, tier=3, dd=85.0, lp=20_000.0)  # -60% LP
        intents = strat.manage(position, dip,
                               self._ctx_with_sizing(now=2_000.0))
        assert intents == []
        assert position.strategy_state["last_dca_skip"] == \
            "DCA_LIQUIDITY_DOWN"

    def test_dca_blocked_on_mc_floor_and_volume_dead(self):
        strat = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None,
                     do_not_dca_if_market_cap_below_usd=30_000.0)
        context = self._ctx_with_sizing()
        position, _ = bala_position(strat, snap(tier=2, dd=70.0), context)
        low_mc = snap(ts=2_000.0, tier=3, dd=85.0, mc=10_000.0)
        assert strat.manage(position, low_mc,
                            self._ctx_with_sizing(now=2_000.0)) == []
        assert position.strategy_state["last_dca_skip"] == \
            "DCA_MC_BELOW_FLOOR"

        strat2 = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None,
                      do_not_dca_if_volume_dead=True)
        position2, _ = bala_position(strat2, snap(tier=2, dd=70.0), context)
        no_vol = snap(ts=2_000.0, tier=3, dd=85.0)
        assert strat2.manage(position2, no_vol,
                             self._ctx_with_sizing(now=2_000.0)) == []
        assert position2.strategy_state["last_dca_skip"] == \
            "DCA_VOLUME_DEAD"

    def test_dca_blocked_on_stale_price_data(self):
        strat = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None,
                     do_not_dca_if_price_data_stale_seconds=600.0)
        context = self._ctx_with_sizing()
        position, _ = bala_position(strat, snap(tier=2, dd=70.0), context)
        # data went dark for 2000s before this dip snapshot
        position.mark_price(0.00009, 3_000.0)
        dip = snap(ts=3_000.0, tier=3, dd=85.0)
        assert strat.manage(position, dip,
                            self._ctx_with_sizing(now=3_000.0)) == []
        assert position.strategy_state["last_dca_skip"] == \
            "DCA_PRICE_DATA_WAS_STALE"

    def test_dca_blocked_on_max_exposure(self):
        strat = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None,
                     max_total_position_usd=90.0)
        context = self._ctx_with_sizing()
        position, _ = bala_position(strat, snap(tier=2, dd=70.0), context)
        # position already carries $100 > $90 cap
        dip = snap(ts=2_000.0, tier=3, dd=85.0)
        assert strat.manage(position, dip,
                            self._ctx_with_sizing(now=2_000.0)) == []
        assert position.strategy_state["last_dca_skip"] == \
            "DCA_MAX_EXPOSURE_USD"

    def test_reaudit_failure_blocks_dca(self):
        strat = make(STRATEGY_BALA_PLAN, min_time_between_dca_seconds=None,
                     min_entry_liquidity_usd=None,
                     audit={"min_liquidity_usd": 5_000.0})
        context = self._ctx_with_sizing()
        healthy = snap(tier=2, dd=70.0, lp=50_000.0)
        position, _ = bala_position(strat, healthy, context)
        sick = snap(ts=2_000.0, tier=3, dd=85.0, lp=4_000.0)
        # LP down 92% would also trip the LP gate; disable it to isolate.
        strat.params["do_not_dca_if_liquidity_down_pct_exceeds"] = None
        assert strat.manage(position, sick,
                            self._ctx_with_sizing(now=2_000.0)) == []
        assert position.strategy_state["last_dca_skip"].startswith(
            "REAUDIT_FAILED")


class TestBalaPlanExits:
    def test_high_quality_score_rides_to_5x_then_trims(self):
        strat = make(STRATEGY_BALA_PLAN)
        entry_snap = snap(tier=2, dd=70.0, score=0.9)
        context = ctx()
        position, intent = bala_position(strat, entry_snap, context)
        assert intent.reason.endswith("_HQ")
        assert intent.plan.take_profit_pct is None
        assert intent.plan.hold_to_multiple == pytest.approx(5.0)
        # below 5x: no trim
        assert strat.manage(position, snap(price=0.0004), ctx()) == []
        # at 5x: partial trim + trailing armed
        intents = strat.manage(position, snap(price=0.0005), ctx())
        assert len(intents) == 1
        assert intents[0].kind == EXIT_PARTIAL
        assert intents[0].fraction == pytest.approx(0.5)
        assert position.plan.trailing_stop_pct == pytest.approx(0.25)
        assert position.strategy_state["trimmed"] is True
        assert position.strategy_state["bala_state"] == "RUNNER_ACTIVE"
        # no double trim
        assert strat.manage(position, snap(price=0.0006), ctx()) == []

    def test_initials_recovery_at_3x_then_runner(self):
        strat = make(STRATEGY_BALA_PLAN, initials_recovery_multiple=3.0)
        position, intent = bala_position(strat, snap(tier=2, dd=70.0), ctx())
        assert intent.plan.take_profit_pct is None  # recovery is the TP
        assert strat.manage(position, snap(price=0.0002), ctx()) == []
        intents = strat.manage(position, snap(price=0.0003), ctx())
        assert len(intents) == 1
        assert intents[0].kind == EXIT_PARTIAL
        assert intents[0].recover_usd == pytest.approx(100.0)
        assert intents[0].leg == "INITIALS_RECOVERY"
        state = position.strategy_state
        assert not state.get("initial_recovered")
        assert position.plan.trailing_stop_pct is None
        strat.on_initials_recovered(position, 0.0003)
        assert state["initial_recovered"] is True
        assert state["bala_state"] == "INITIALS_RECOVERED"
        assert position.plan.trailing_stop_pct == pytest.approx(0.30)
        # next tick settles to RUNNER_ACTIVE and never re-fires
        assert strat.manage(position, snap(price=0.0004), ctx()) == []
        assert state["bala_state"] == "RUNNER_ACTIVE"

    def test_terminal_sync_updates_track(self):
        strat = make(STRATEGY_BALA_PLAN)
        position, _ = bala_position(strat, snap(tier=2, dd=70.0), ctx())
        position.status = "RUGGED"
        strat.on_position_terminal(position)
        assert strat._tracks[position.mint].state == "RUGGED"
        assert position.strategy_state["bala_state"] == "RUGGED"


class TestConfigPlan:
    def test_config_validation_rejects_bad_params(self):
        with pytest.raises(ValueError, match="entry_dip_band_pct"):
            make(STRATEGY_CONFIG_PLAN, entry_dip_band_pct=[80.0, 60.0])
        with pytest.raises(ValueError, match="take_profit_pct"):
            make(STRATEGY_CONFIG_PLAN, take_profit_pct=-0.5)
        with pytest.raises(ValueError, match="stop_loss_pct"):
            make(STRATEGY_CONFIG_PLAN, stop_loss_pct=0.5)
        with pytest.raises(ValueError, match="trailing_stop_pct"):
            make(STRATEGY_CONFIG_PLAN, trailing_stop_pct=1.5)
        with pytest.raises(ValueError, match="max_hold_seconds"):
            make(STRATEGY_CONFIG_PLAN, max_hold_seconds=-10)

    def test_unknown_param_rejected_at_config_load(self):
        raw = default_config().to_dict()
        raw["strategies"][1]["params"]["not_a_real_knob"] = 1
        with pytest.raises(ConfigError, match="not_a_real_knob"):
            load_config_dict(raw)

    def test_unknown_strategy_type_rejected(self):
        raw = default_config().to_dict()
        raw["strategies"][0]["strategy_type"] = "MYSTERY"
        with pytest.raises(ConfigError, match="MYSTERY"):
            load_config_dict(raw)

    def test_filters_and_plan_from_config(self):
        strat = make(STRATEGY_CONFIG_PLAN, min_entry_liquidity_usd=10_000.0,
                     entry_dip_band_pct=[60.0, 90.0], take_profit_pct=0.5,
                     stop_loss_pct=-0.4, max_hold_seconds=3_600.0)
        assert strat.wants_entry(snap(lp=5_000.0, dd=70.0), ctx()) is None
        assert strat.wants_entry(snap(dd=50.0), ctx()) is None
        intent = strat.wants_entry(snap(dd=70.0), ctx())
        assert intent is not None
        assert intent.plan.take_profit_pct == pytest.approx(0.5)
        assert intent.plan.stop_loss_pct == pytest.approx(-0.4)
        assert intent.plan.max_hold_seconds == pytest.approx(3_600.0)

    def test_no_filters_enters_any_priced_candidate(self):
        strat = make(STRATEGY_CONFIG_PLAN)
        assert strat.wants_entry(snap(), ctx()) is not None
        assert strat.wants_entry(snap(price=None), ctx()) is None


class TestMonkeyRandom:
    def _decisions(self, seed, n=60):
        strat = make(STRATEGY_MONKEY_RANDOM)
        context = ctx(seed=seed)
        out = []
        for i in range(n):
            mint = f"MINT{i:04d}" + "x" * 36
            intent = strat.wants_entry(snap(mint=mint, ts=1_000.0 + i),
                                       context)
            out.append(None if intent is None else
                       (round(intent.plan.take_profit_pct, 9),
                        round(intent.plan.stop_loss_pct, 9),
                        round(intent.plan.max_hold_seconds, 6)))
        return out

    def test_deterministic_with_same_seed(self):
        assert self._decisions(seed=42) == self._decisions(seed=42)

    def test_different_seed_differs(self):
        assert self._decisions(seed=42) != self._decisions(seed=43)

    def test_some_entries_and_some_passes(self):
        decisions = self._decisions(seed=42)
        entered = [d for d in decisions if d is not None]
        assert 0 < len(entered) < len(decisions)

    def test_one_roll_per_mint(self):
        strat = make(STRATEGY_MONKEY_RANDOM, entry_probability=1.0)
        context = ctx()
        first = strat.wants_entry(snap(), context)
        assert first is not None
        assert strat.wants_entry(snap(ts=2_000.0), context) is None

    def test_validation(self):
        with pytest.raises(ValueError, match="entry_probability"):
            make(STRATEGY_MONKEY_RANDOM, entry_probability=1.5)
        with pytest.raises(ValueError, match="hold_seconds_range"):
            make(STRATEGY_MONKEY_RANDOM, hold_seconds_range=[100.0, 10.0])


class TestMonkeyHold:
    def test_enter_all_with_fixed_hold(self):
        strat = make(STRATEGY_MONKEY_HOLD, hold_seconds=7_200.0)
        intent = strat.wants_entry(snap(), ctx())
        assert intent is not None
        assert intent.plan.max_hold_seconds == pytest.approx(7_200.0)
        assert intent.plan.take_profit_pct is None
        assert intent.plan.stop_loss_pct is None

    def test_random_entry_mode_deterministic(self):
        def entered(seed):
            strat = make(STRATEGY_MONKEY_HOLD, entry_mode="RANDOM",
                         entry_probability=0.5)
            context = ctx(seed=seed)
            return [strat.wants_entry(
                snap(mint=f"MINT{i:04d}" + "y" * 36), context) is not None
                for i in range(40)]
        assert entered(1) == entered(1)
        assert any(entered(1)) and not all(entered(1))

    def test_validation(self):
        with pytest.raises(ValueError, match="hold_seconds"):
            make(STRATEGY_MONKEY_HOLD, hold_seconds=0)
        with pytest.raises(ValueError, match="entry_mode"):
            make(STRATEGY_MONKEY_HOLD, entry_mode="SOMETIMES")


class TestThreeXRunner:
    def _position(self, plan):
        return PaperPosition(paper_trade_id="t", strategy_name="s1",
                             run_id="r", mint="M" * 44, entry_price=0.0001,
                             estimated_tokens_received=1_000_000.0,
                             tokens_open=1_000_000.0, virtual_usd_size=100.0,
                             plan=plan)

    def test_recovers_initial_at_3x_and_rides_runner(self):
        strat = make(STRATEGY_THREE_X)
        intent = strat.wants_entry(snap(), ctx())
        assert intent is not None
        assert intent.plan.take_profit_pct is None
        position = self._position(intent.plan)

        assert strat.manage(position, snap(price=0.0002), ctx()) == []
        intents = strat.manage(position, snap(price=0.0003), ctx())
        assert len(intents) == 1
        assert intents[0].kind == EXIT_PARTIAL
        assert intents[0].recover_usd == pytest.approx(100.0)
        state = position.strategy_state
        assert not state.get("initial_recovered")
        assert position.plan.trailing_stop_pct is None
        strat.on_initials_recovered(position, 0.0003)
        assert state["initial_recovered"] is True
        assert state["runner_status"] == "RUNNER_ACTIVE"
        assert position.plan.trailing_stop_pct == pytest.approx(0.30)
        # recovery fires once
        assert strat.manage(position, snap(price=0.0004), ctx()) == []

    def test_runner_status_starts_waiting(self):
        strat = make(STRATEGY_THREE_X)
        position = self._position(strat.wants_entry(snap(), ctx()).plan)
        strat.manage(position, snap(price=0.00015), ctx())
        assert position.strategy_state["runner_status"] == \
            "WAITING_FOR_MULTIPLE"

    def test_validation(self):
        with pytest.raises(ValueError, match="recover_multiple"):
            make(STRATEGY_THREE_X, recover_multiple=0.5)
        with pytest.raises(ValueError, match="runner_trailing_stop_pct"):
            make(STRATEGY_THREE_X, runner_trailing_stop_pct=2.0)
