"""MONKEY_HOLD: the naive hold baseline.

Enters candidates with a trivial rule (every priced candidate, or a random
subset) and just holds for a fixed configured time, or until the engine's
data-lost / rug handling ends the position. No take profit or stop loss
unless explicitly configured. Tests whether simply holding beats the
active-exit strategies over the same stream.
"""

from __future__ import annotations

from typing import Optional, Set

from PHX2.paper_trading.config import STRATEGY_MONKEY_HOLD
from PHX2.paper_trading.models import CandidateSnapshot, ExitPlan
from PHX2.paper_trading.strategy import (
    EntryIntent,
    PaperStrategy,
    StrategyContext,
)

ENTRY_MODE_ALL = "ALL"
ENTRY_MODE_RANDOM = "RANDOM"


class MonkeyHoldStrategy(PaperStrategy):
    strategy_type = STRATEGY_MONKEY_HOLD

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        self._rolled_mints: Set[str] = set()

    def validate_params(self) -> None:
        mode = self.params.get("entry_mode", ENTRY_MODE_ALL)
        if mode not in (ENTRY_MODE_ALL, ENTRY_MODE_RANDOM):
            raise ValueError(
                f"strategy '{self.name}': entry_mode must be "
                f"{ENTRY_MODE_ALL} or {ENTRY_MODE_RANDOM}")
        hold = self._num(self.params.get("hold_seconds"))
        if hold is None or hold <= 0:
            raise ValueError(
                f"strategy '{self.name}': hold_seconds must be positive")
        prob = self._num(self.params.get("entry_probability"))
        if mode == ENTRY_MODE_RANDOM and (prob is None
                                          or not (0.0 <= prob <= 1.0)):
            raise ValueError(
                f"strategy '{self.name}': entry_probability must be in [0, 1]"
                " when entry_mode is RANDOM")

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        if not snapshot.has_price:
            return None
        if self.params.get("entry_mode", ENTRY_MODE_ALL) == ENTRY_MODE_RANDOM:
            if snapshot.mint in self._rolled_mints:
                return None
            self._rolled_mints.add(snapshot.mint)
            if ctx.rng.random() >= float(self.params["entry_probability"]):
                return None
            reason = "MONKEY_HOLD_RANDOM_ENTRY"
        else:
            reason = "MONKEY_HOLD_ENTER_ALL"
        plan = ExitPlan(
            take_profit_pct=self._num(self.params.get("take_profit_pct")),
            stop_loss_pct=self._num(self.params.get("stop_loss_pct")),
            max_hold_seconds=float(self.params["hold_seconds"]),
        )
        return EntryIntent(reason=reason, plan=plan)


__all__ = ["MonkeyHoldStrategy"]
