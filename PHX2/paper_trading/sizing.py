"""Position sizing for the PHX2 paper trading engine.

Turns "the strategy wants in" into a realistic virtual fill size. The point
is to punish bad liquidity: a $1k buy into a $15k market-cap coin should
never happen in serious paper results. Profiles:

* ``FIXED_SOL`` / ``FIXED_USD``      -- controlled-test sizes (still capped).
* ``MARKET_CAP_CURVE``               -- notional by entry market-cap band.
* ``TOKEN_TARGET_CURVE``             -- token amount by market-cap band.
* ``LIQUIDITY_CAPPED``               -- never exceeds a % of pool liquidity.
* ``VOLUME_CAPPED``                  -- never exceeds a % of recent volume.
* ``HYBRID_REALISTIC``               -- token target + notional cap + LP cap
                                        + volume cap + abs caps + impact;
                                        the default for serious runs.

Every decision records the caps applied (``cap_reasons``) and the simulated
slippage / market-impact / fee so the ledgers show *why* a fill was small
or skipped.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
from PHX2.paper_trading.models import CandidateSnapshot, SizingDecision

# Skip reason tokens
SKIP_NO_ENTRY_PRICE = "NO_ENTRY_PRICE"
SKIP_NO_MARKET_CAP = "NO_MARKET_CAP"
SKIP_NO_LIQUIDITY_DATA = "NO_LIQUIDITY_DATA"
SKIP_NO_VOLUME_DATA = "NO_VOLUME_DATA"
SKIP_NO_SOL_PRICE = "NO_SOL_PRICE"
SKIP_MIN_NOTIONAL_NOT_MET = "MIN_NOTIONAL_NOT_MET"
SKIP_NO_SUPPLY = "NO_SUPPLY"

# Cap reason tokens
CAP_LIQUIDITY = "LIQUIDITY_CAP_APPLIED"
CAP_VOLUME = "VOLUME_CAP_APPLIED"
CAP_MAX_ABS_NOTIONAL = "MAX_ABS_NOTIONAL_CAP_APPLIED"
CAP_BAND_MAX_NOTIONAL = "BAND_MAX_NOTIONAL_CAP_APPLIED"
CAP_LIQUIDITY_UNKNOWN = "LIQUIDITY_UNKNOWN_NO_CAP"
CAP_VOLUME_UNKNOWN = "VOLUME_UNKNOWN_NO_CAP"
CAP_MC_FROM_FALLBACK_SUPPLY = "MC_ESTIMATED_FROM_FALLBACK_SUPPLY"

# Profiles that refuse to size without liquidity data.
_LP_REQUIRED_PROFILES = (PROFILE_LIQUIDITY_CAPPED, PROFILE_HYBRID_REALISTIC)


def simulate_impact_bps(notional_usd: float, liquidity_usd: Optional[float],
                        sim: MarketSimConfig) -> float:
    """Linear market-impact estimate in bps, capped at max_impact_bps.

    ``impact = impact_bps_per_pct_of_lp * (notional / LP * 100)``.
    Unknown or dead liquidity is treated as worst case (max impact).
    """
    if notional_usd <= 0:
        return 0.0
    if liquidity_usd is None or liquidity_usd <= 0:
        return float(sim.max_impact_bps)
    pct_of_lp = notional_usd / liquidity_usd * 100.0
    impact = sim.impact_bps_per_pct_of_lp * pct_of_lp
    return float(min(impact, sim.max_impact_bps))


def effective_buy_price(price: float, slippage_bps: float,
                        impact_bps: float) -> float:
    return price * (1.0 + (slippage_bps + impact_bps) / 10_000.0)


def effective_sell_price(price: float, slippage_bps: float,
                         impact_bps: float) -> float:
    return max(0.0, price * (1.0 - (slippage_bps + impact_bps) / 10_000.0))


def _select_band(curve: List[Dict[str, Any]],
                 market_cap: float) -> Tuple[Dict[str, Any], str]:
    """Pick the first band whose mc_max_usd is None or >= market cap."""
    chosen = curve[-1]
    for band in curve:
        mc_max = band.get("mc_max_usd")
        if mc_max is None or market_cap <= float(mc_max):
            chosen = band
            break
    mc_max = chosen.get("mc_max_usd")
    label = ("BAND_MC_TOP" if mc_max is None
             else f"BAND_MC_LE_{int(mc_max)}")
    return chosen, label


def _band_token_target(band: Dict[str, Any],
                       fraction: float) -> Optional[float]:
    lo = band.get("token_target_min")
    hi = band.get("token_target_max")
    if lo is None and hi is None:
        return None
    lo = float(lo if lo is not None else hi)
    hi = float(hi if hi is not None else lo)
    fraction = min(max(fraction, 0.0), 1.0)
    return lo + (hi - lo) * fraction


def compute_sizing(profile: SizingProfileConfig,
                   snapshot: CandidateSnapshot,
                   sim: MarketSimConfig,
                   sol_price_usd: Optional[float] = None,
                   requested_usd_override: Optional[float] = None
                   ) -> SizingDecision:
    """Size one intended buy. Never raises; skips carry a reason token.

    ``requested_usd_override`` bypasses the profile's own notional logic and
    runs the caller's USD amount (e.g. one DCA leg budget) through the same
    cap chain and fill simulation, so add-legs obey identical realism rules.
    """
    decision = SizingDecision(
        profile=profile.profile,
        entry_market_cap=snapshot.market_cap_usd,
        entry_liquidity=snapshot.liquidity_usd,
        simulated_fee_bps=float(sim.fee_bps),
        simulated_slippage_bps=float(sim.base_slippage_bps),
    )

    if not snapshot.has_price:
        decision.skipped_reason = SKIP_NO_ENTRY_PRICE
        return decision
    price = float(snapshot.price_usd)

    market_cap = snapshot.market_cap_usd
    if market_cap is None and requested_usd_override is None and \
            profile.profile in (
            PROFILE_MARKET_CAP_CURVE, PROFILE_TOKEN_TARGET_CURVE,
            PROFILE_HYBRID_REALISTIC):
        # Estimate MC from price * fallback supply only when explicitly
        # allowed; otherwise curve profiles cannot band the entry.
        if profile.fallback_supply is not None and profile.fallback_supply > 0:
            market_cap = price * float(profile.fallback_supply)
            decision.cap_reasons.append(CAP_MC_FROM_FALLBACK_SUPPLY)
            decision.entry_market_cap = market_cap
        else:
            decision.skipped_reason = SKIP_NO_MARKET_CAP
            return decision

    liquidity = snapshot.liquidity_usd
    if (liquidity is None or liquidity <= 0) and \
            profile.profile in _LP_REQUIRED_PROFILES:
        decision.skipped_reason = SKIP_NO_LIQUIDITY_DATA
        return decision

    # ------------------------------------------------------------------
    # Requested notional per profile (or the caller's override)
    # ------------------------------------------------------------------
    requested: Optional[float] = None
    band_max_notional: Optional[float] = None

    if requested_usd_override is not None:
        if requested_usd_override <= 0:
            decision.skipped_reason = SKIP_MIN_NOTIONAL_NOT_MET
            return decision
        requested = float(requested_usd_override)

    elif profile.profile == PROFILE_FIXED_SOL:
        if sol_price_usd is None or sol_price_usd <= 0:
            decision.skipped_reason = SKIP_NO_SOL_PRICE
            return decision
        decision.requested_size_sol = float(profile.fixed_sol_size)
        requested = float(profile.fixed_sol_size) * float(sol_price_usd)

    elif profile.profile in (PROFILE_FIXED_USD, PROFILE_LIQUIDITY_CAPPED,
                             PROFILE_VOLUME_CAPPED):
        requested = float(profile.fixed_usd_size)

    elif profile.profile == PROFILE_MARKET_CAP_CURVE:
        band, label = _select_band(profile.curve, float(market_cap))
        decision.cap_reasons.append(label)
        requested = float(band.get("notional_usd")
                          or band.get("fixed_usd")
                          or profile.fixed_usd_size)
        if band.get("max_notional_usd") is not None:
            band_max_notional = float(band["max_notional_usd"])

    elif profile.profile in (PROFILE_TOKEN_TARGET_CURVE,
                             PROFILE_HYBRID_REALISTIC):
        band, label = _select_band(profile.curve, float(market_cap))
        decision.cap_reasons.append(label)
        target_tokens = _band_token_target(band, profile.token_target_fraction)
        if target_tokens is not None:
            decision.target_token_amount = target_tokens
            requested = target_tokens * price
        else:
            # Top band: plain notional sizing (config USD, or SOL if given).
            band_notional = band.get("notional_usd") or band.get("fixed_usd")
            if band_notional is None and band.get("fixed_sol") is not None:
                if sol_price_usd is None or sol_price_usd <= 0:
                    decision.skipped_reason = SKIP_NO_SOL_PRICE
                    return decision
                band_notional = float(band["fixed_sol"]) * float(sol_price_usd)
            requested = float(band_notional
                              if band_notional is not None
                              else profile.fixed_usd_size)
        if band.get("max_notional_usd") is not None:
            band_max_notional = float(band["max_notional_usd"])

    if requested is None or requested <= 0:
        decision.skipped_reason = SKIP_NO_SUPPLY
        return decision
    decision.requested_size_usd = requested

    # ------------------------------------------------------------------
    # Cap chain: band max -> liquidity -> volume -> abs max
    # ------------------------------------------------------------------
    final = requested

    if band_max_notional is not None and final > band_max_notional:
        final = band_max_notional
        decision.cap_reasons.append(CAP_BAND_MAX_NOTIONAL)

    if profile.max_buy_pct_of_liquidity is not None:
        if liquidity is not None and liquidity > 0:
            lp_cap = liquidity * float(profile.max_buy_pct_of_liquidity) / 100.0
            if final > lp_cap:
                final = lp_cap
                decision.cap_reasons.append(CAP_LIQUIDITY)
        else:
            decision.cap_reasons.append(CAP_LIQUIDITY_UNKNOWN)

    if profile.max_buy_pct_of_recent_volume is not None:
        volume = snapshot.volume_usd
        if volume is not None and volume > 0:
            vol_cap = volume * float(profile.max_buy_pct_of_recent_volume) / 100.0
            if final > vol_cap:
                final = vol_cap
                decision.cap_reasons.append(CAP_VOLUME)
        elif profile.profile == PROFILE_VOLUME_CAPPED:
            decision.skipped_reason = SKIP_NO_VOLUME_DATA
            return decision
        else:
            decision.cap_reasons.append(CAP_VOLUME_UNKNOWN)

    if profile.max_abs_notional_usd is not None and \
            final > float(profile.max_abs_notional_usd):
        final = float(profile.max_abs_notional_usd)
        decision.cap_reasons.append(CAP_MAX_ABS_NOTIONAL)

    if final < float(profile.min_abs_notional_usd):
        decision.final_size_usd = 0.0
        decision.skipped_reason = SKIP_MIN_NOTIONAL_NOT_MET
        return decision

    # ------------------------------------------------------------------
    # Fill simulation: fee + slippage + market impact
    # ------------------------------------------------------------------
    impact_bps = simulate_impact_bps(final, liquidity, sim)
    decision.simulated_market_impact_bps = impact_bps
    fill_price = effective_buy_price(price, sim.base_slippage_bps, impact_bps)
    fee_usd = final * sim.fee_bps / 10_000.0
    tokens = max(0.0, (final - fee_usd) / fill_price) if fill_price > 0 else 0.0

    decision.final_size_usd = final
    decision.estimated_tokens_received = tokens
    if sol_price_usd is not None and sol_price_usd > 0:
        decision.requested_size_sol = (decision.requested_size_sol
                                       if decision.requested_size_sol is not None
                                       else requested / float(sol_price_usd))
        decision.final_size_sol = final / float(sol_price_usd)
    return decision


__all__ = [
    "SKIP_NO_ENTRY_PRICE",
    "SKIP_NO_MARKET_CAP",
    "SKIP_NO_LIQUIDITY_DATA",
    "SKIP_NO_VOLUME_DATA",
    "SKIP_NO_SOL_PRICE",
    "SKIP_MIN_NOTIONAL_NOT_MET",
    "SKIP_NO_SUPPLY",
    "CAP_LIQUIDITY",
    "CAP_VOLUME",
    "CAP_MAX_ABS_NOTIONAL",
    "CAP_BAND_MAX_NOTIONAL",
    "CAP_LIQUIDITY_UNKNOWN",
    "CAP_VOLUME_UNKNOWN",
    "CAP_MC_FROM_FALLBACK_SUPPLY",
    "simulate_impact_bps",
    "effective_buy_price",
    "effective_sell_price",
    "compute_sizing",
]
