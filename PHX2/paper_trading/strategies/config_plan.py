"""CONFIG_PLAN: a fully config-driven strategy.

Lets Bala test a new plan without code edits: every entry filter and exit
rule comes from the strategy's ``params`` block. An instance with no entry
filters configured enters every priced candidate, so a plan should normally
set at least one filter.

Supported params (all optional unless noted):

* entry: ``require_price`` (default true), ``min/max_entry_market_cap_usd``,
  ``min_entry_liquidity_usd``, ``min_entry_volume_usd``, ``allowed_tiers``
  (list, None = any), ``entry_dip_band_pct`` ([low, high] percent drawdown).
* exit: ``take_profit_pct``, ``stop_loss_pct`` (negative),
  ``trailing_stop_pct``, ``max_hold_seconds``.
"""

from __future__ import annotations

from typing import Optional

from PHX2.paper_trading.config import STRATEGY_CONFIG_PLAN
from PHX2.paper_trading.models import CandidateSnapshot, ExitPlan
from PHX2.paper_trading.strategy import (
    EntryIntent,
    PaperStrategy,
    StrategyContext,
)


class ConfigPlanStrategy(PaperStrategy):
    strategy_type = STRATEGY_CONFIG_PLAN

    def validate_params(self) -> None:
        p = self.params
        band = p.get("entry_dip_band_pct")
        if band is not None:
            if (not isinstance(band, (list, tuple)) or len(band) != 2
                    or self._num(band[0]) is None
                    or self._num(band[1]) is None
                    or float(band[0]) >= float(band[1])):
                raise ValueError(
                    f"strategy '{self.name}': entry_dip_band_pct must be "
                    "[low_pct, high_pct] with low < high")
        tp = self._num(p.get("take_profit_pct"))
        if tp is not None and tp <= 0:
            raise ValueError(
                f"strategy '{self.name}': take_profit_pct must be positive")
        sl = self._num(p.get("stop_loss_pct"))
        if sl is not None and sl >= 0:
            raise ValueError(
                f"strategy '{self.name}': stop_loss_pct must be negative")
        trail = self._num(p.get("trailing_stop_pct"))
        if trail is not None and not (0.0 < trail < 1.0):
            raise ValueError(
                f"strategy '{self.name}': trailing_stop_pct must be in (0, 1)")
        hold = self._num(p.get("max_hold_seconds"))
        if hold is not None and hold <= 0:
            raise ValueError(
                f"strategy '{self.name}': max_hold_seconds must be positive")
        tiers = p.get("allowed_tiers")
        if tiers is not None and not isinstance(tiers, (list, tuple)):
            raise ValueError(
                f"strategy '{self.name}': allowed_tiers must be a list or null")

    def _dip_ok(self, snapshot: CandidateSnapshot) -> bool:
        band = self.params.get("entry_dip_band_pct")
        if band is None:
            return True
        drawdown: Optional[float] = snapshot.drawdown_pct
        if drawdown is None and (snapshot.ath_market_cap_usd
                                 and snapshot.market_cap_usd):
            drawdown = (1.0 - snapshot.market_cap_usd
                        / snapshot.ath_market_cap_usd) * 100.0
        if drawdown is None:
            return False
        return float(band[0]) <= drawdown <= float(band[1])

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        if self.params.get("require_price", True) and not snapshot.has_price:
            return None
        if not self.passes_entry_filters(snapshot):
            return None
        if not self._dip_ok(snapshot):
            return None
        plan = ExitPlan(
            take_profit_pct=self._num(self.params.get("take_profit_pct")),
            stop_loss_pct=self._num(self.params.get("stop_loss_pct")),
            trailing_stop_pct=self._num(self.params.get("trailing_stop_pct")),
            max_hold_seconds=self._num(self.params.get("max_hold_seconds")),
        )
        return EntryIntent(reason="CONFIG_PLAN_FILTERS_PASSED", plan=plan)


__all__ = ["ConfigPlanStrategy"]
