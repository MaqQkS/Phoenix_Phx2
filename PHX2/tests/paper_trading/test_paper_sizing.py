"""Sizing module tests: curve bands, caps, realism guarantees."""

from __future__ import annotations

import pytest

from PHX2.paper_trading.config import (
    MarketSimConfig,
    SizingProfileConfig,
    PROFILE_FIXED_SOL,
    PROFILE_FIXED_USD,
    PROFILE_HYBRID_REALISTIC,
    PROFILE_LIQUIDITY_CAPPED,
    PROFILE_MARKET_CAP_CURVE,
    PROFILE_TOKEN_TARGET_CURVE,
    PROFILE_VOLUME_CAPPED,
)
from PHX2.paper_trading.models import CandidateSnapshot
from PHX2.paper_trading.sizing import (
    CAP_BAND_MAX_NOTIONAL,
    CAP_LIQUIDITY,
    CAP_MAX_ABS_NOTIONAL,
    CAP_MC_FROM_FALLBACK_SUPPLY,
    CAP_VOLUME,
    SKIP_MIN_NOTIONAL_NOT_MET,
    SKIP_NO_ENTRY_PRICE,
    SKIP_NO_LIQUIDITY_DATA,
    SKIP_NO_MARKET_CAP,
    SKIP_NO_SOL_PRICE,
    SKIP_NO_VOLUME_DATA,
    compute_sizing,
    simulate_impact_bps,
)

SIM = MarketSimConfig()


def snap(price=0.0001, mc=100_000.0, lp=50_000.0, volume=None):
    return CandidateSnapshot(ts_epoch=1_000.0, mint="M" * 44,
                             price_usd=price, market_cap_usd=mc,
                             liquidity_usd=lp, volume_usd=volume)


def hybrid(**overrides) -> SizingProfileConfig:
    profile = SizingProfileConfig(profile=PROFILE_HYBRID_REALISTIC,
                                  fallback_supply=1_000_000_000)
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


class TestHybridCurve:
    def test_below_15k_mc_targets_7m_to_10m_tokens(self):
        # price such that the token-target notional stays under all caps
        decision = compute_sizing(
            hybrid(), snap(price=0.00001, mc=10_000.0, lp=100_000.0), SIM)
        assert decision.skipped_reason is None
        assert 7_000_000 <= decision.target_token_amount <= 10_000_000
        # midpoint default: 8.5M tokens * 0.00001 = $85, under the $150 cap
        assert decision.final_size_usd == pytest.approx(85.0)
        assert decision.final_size_usd <= 150.0

    def test_below_15k_max_notional_150(self):
        # expensive-per-token so the token target would cost more than $150
        decision = compute_sizing(
            hybrid(), snap(price=0.001, mc=14_000.0, lp=1_000_000.0), SIM)
        assert decision.final_size_usd == pytest.approx(150.0)
        assert CAP_BAND_MAX_NOTIONAL in decision.cap_reasons

    def test_50k_150k_band_targets_1m_to_3m_tokens(self):
        decision = compute_sizing(
            hybrid(), snap(price=0.0001, mc=100_000.0, lp=1_000_000.0), SIM)
        assert 1_000_000 <= decision.target_token_amount <= 3_000_000
        # 2M tokens * 0.0001 = $200, under the $250 band cap
        assert decision.final_size_usd == pytest.approx(200.0)

    def test_no_unrealistic_1k_buy_into_tiny_liquidity(self):
        # Even a config asking for $1k can never exceed 0.5% of LP.
        profile = hybrid()
        profile.curve = [{"mc_max_usd": None, "notional_usd": 1_000.0,
                          "max_notional_usd": 1_000.0}]
        profile.max_abs_notional_usd = 1_000.0
        decision = compute_sizing(
            profile, snap(price=0.00003, mc=30_000.0, lp=8_000.0), SIM)
        assert decision.final_size_usd == pytest.approx(8_000.0 * 0.005)
        assert CAP_LIQUIDITY in decision.cap_reasons
        assert decision.final_size_usd <= 8_000.0 * 0.005

    def test_hybrid_requires_liquidity_data(self):
        decision = compute_sizing(hybrid(), snap(lp=None), SIM)
        assert decision.skipped_reason == SKIP_NO_LIQUIDITY_DATA
        assert decision.is_skip

    def test_hybrid_chooses_smallest_cap(self):
        # token target ~$850 vs band max $150 vs LP cap $100 vs abs $500
        decision = compute_sizing(
            hybrid(), snap(price=0.0001, mc=10_000.0, lp=20_000.0), SIM)
        assert decision.final_size_usd == pytest.approx(100.0)  # LP cap wins
        assert CAP_LIQUIDITY in decision.cap_reasons
        assert CAP_BAND_MAX_NOTIONAL in decision.cap_reasons

    def test_volume_cap_applies_when_volume_present(self):
        decision = compute_sizing(
            hybrid(), snap(price=0.0001, mc=100_000.0, lp=1_000_000.0,
                           volume=500.0), SIM)
        # 10% of $500 volume = $50 beats the $200 token-target notional
        assert decision.final_size_usd == pytest.approx(50.0)
        assert CAP_VOLUME in decision.cap_reasons

    def test_missing_mc_uses_fallback_supply_when_allowed(self):
        decision = compute_sizing(
            hybrid(), snap(price=0.00002, mc=None, lp=100_000.0), SIM)
        assert decision.skipped_reason is None
        assert CAP_MC_FROM_FALLBACK_SUPPLY in decision.cap_reasons
        # estimated mc = 0.00002 * 1B = $20k -> 15k-50k band
        assert 2_000_000 <= decision.target_token_amount <= 5_000_000

    def test_missing_mc_skips_without_fallback_supply(self):
        profile = hybrid(fallback_supply=None)
        decision = compute_sizing(
            profile, snap(price=0.00002, mc=None, lp=100_000.0), SIM)
        assert decision.skipped_reason == SKIP_NO_MARKET_CAP

    def test_min_notional_skip(self):
        # tiny LP -> LP cap $2.50 < $10 min notional
        decision = compute_sizing(
            hybrid(), snap(price=0.00003, mc=30_000.0, lp=500.0), SIM)
        assert decision.skipped_reason == SKIP_MIN_NOTIONAL_NOT_MET
        assert decision.final_size_usd == 0.0

    def test_missing_price_skips(self):
        decision = compute_sizing(hybrid(), snap(price=None), SIM)
        assert decision.skipped_reason == SKIP_NO_ENTRY_PRICE


class TestOtherProfiles:
    def test_fixed_usd(self):
        profile = SizingProfileConfig(profile=PROFILE_FIXED_USD,
                                      fixed_usd_size=100.0)
        decision = compute_sizing(profile, snap(lp=1_000_000.0), SIM)
        assert decision.final_size_usd == pytest.approx(100.0)
        assert decision.estimated_tokens_received > 0

    def test_fixed_usd_still_liquidity_capped(self):
        profile = SizingProfileConfig(profile=PROFILE_FIXED_USD,
                                      fixed_usd_size=1_000.0,
                                      max_abs_notional_usd=None)
        decision = compute_sizing(profile, snap(lp=8_000.0), SIM)
        assert decision.final_size_usd == pytest.approx(40.0)  # 0.5% of 8k
        assert CAP_LIQUIDITY in decision.cap_reasons

    def test_fixed_sol_requires_sol_price(self):
        profile = SizingProfileConfig(profile=PROFILE_FIXED_SOL,
                                      fixed_sol_size=0.5)
        decision = compute_sizing(profile, snap(), SIM, sol_price_usd=None)
        assert decision.skipped_reason == SKIP_NO_SOL_PRICE
        decision = compute_sizing(profile, snap(lp=1_000_000.0), SIM,
                                  sol_price_usd=200.0)
        assert decision.requested_size_usd == pytest.approx(100.0)
        assert decision.final_size_sol is not None

    def test_market_cap_curve_bands(self):
        from PHX2.paper_trading.config import DEFAULT_MC_NOTIONAL_CURVE
        profile = SizingProfileConfig(profile=PROFILE_MARKET_CAP_CURVE,
                                      curve=list(DEFAULT_MC_NOTIONAL_CURVE))
        lo = compute_sizing(profile, snap(mc=10_000.0, lp=1_000_000.0), SIM)
        mid = compute_sizing(profile, snap(mc=100_000.0, lp=1_000_000.0), SIM)
        top = compute_sizing(profile, snap(mc=500_000.0, lp=1_000_000.0), SIM)
        assert lo.final_size_usd == pytest.approx(75.0)
        assert mid.final_size_usd == pytest.approx(150.0)
        assert top.final_size_usd == pytest.approx(200.0)

    def test_token_target_curve(self):
        profile = SizingProfileConfig(profile=PROFILE_TOKEN_TARGET_CURVE,
                                      fallback_supply=None)
        decision = compute_sizing(
            profile, snap(price=0.00001, mc=10_000.0, lp=1_000_000.0), SIM)
        assert decision.target_token_amount == pytest.approx(8_500_000.0)

    def test_liquidity_capped_profile_requires_lp(self):
        profile = SizingProfileConfig(profile=PROFILE_LIQUIDITY_CAPPED)
        decision = compute_sizing(profile, snap(lp=None), SIM)
        assert decision.skipped_reason == SKIP_NO_LIQUIDITY_DATA

    def test_volume_capped_profile_requires_volume(self):
        profile = SizingProfileConfig(profile=PROFILE_VOLUME_CAPPED,
                                      fixed_usd_size=100.0)
        decision = compute_sizing(profile, snap(volume=None), SIM)
        assert decision.skipped_reason == SKIP_NO_VOLUME_DATA
        decision = compute_sizing(profile, snap(volume=300.0), SIM)
        assert decision.final_size_usd == pytest.approx(30.0)
        assert CAP_VOLUME in decision.cap_reasons

    def test_max_abs_notional_cap(self):
        profile = SizingProfileConfig(profile=PROFILE_FIXED_USD,
                                      fixed_usd_size=900.0,
                                      max_abs_notional_usd=300.0,
                                      max_buy_pct_of_liquidity=None)
        decision = compute_sizing(profile, snap(lp=1_000_000.0), SIM)
        assert decision.final_size_usd == pytest.approx(300.0)
        assert CAP_MAX_ABS_NOTIONAL in decision.cap_reasons


class TestImpactModel:
    def test_impact_scales_with_size_relative_to_lp(self):
        small = simulate_impact_bps(50.0, 100_000.0, SIM)
        large = simulate_impact_bps(500.0, 10_000.0, SIM)
        assert small < large
        assert small == pytest.approx(30.0 * 0.05)

    def test_impact_capped_and_worst_case_when_lp_unknown(self):
        assert simulate_impact_bps(10_000.0, 1_000.0, SIM) == SIM.max_impact_bps
        assert simulate_impact_bps(100.0, None, SIM) == SIM.max_impact_bps

    def test_fill_price_worse_than_raw_price(self):
        decision = compute_sizing(hybrid(), snap(lp=50_000.0), SIM)
        raw_tokens = decision.final_size_usd / 0.0001
        assert decision.estimated_tokens_received < raw_tokens
