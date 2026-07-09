"""MONKEY_RANDOM: the dumb-randomness baseline.

Rolls once per mint (on its first priced sighting) and enters with
``entry_probability``. Exits are random too: a per-position random take
profit, stop loss and hold time drawn from configured ranges, plus a small
per-update random close probability. All randomness comes from the
per-strategy seeded RNG, so a run is reproducible for a given
``random_seed`` and identical over the same candidate stream.

If PHX2's real strategies cannot beat this monkey, they are not strategies.
"""

from __future__ import annotations

from typing import Optional, Set

from PHX2.paper_trading.config import STRATEGY_MONKEY_RANDOM
from PHX2.paper_trading.models import CandidateSnapshot, ExitPlan
from PHX2.paper_trading.strategy import (
    EntryIntent,
    PaperStrategy,
    StrategyContext,
)


def _range_ok(value: object) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in value)
            and float(value[0]) <= float(value[1]))


class MonkeyRandomStrategy(PaperStrategy):
    strategy_type = STRATEGY_MONKEY_RANDOM

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        self._rolled_mints: Set[str] = set()

    def validate_params(self) -> None:
        p = self.params
        prob = self._num(p.get("entry_probability"))
        if prob is None or not (0.0 <= prob <= 1.0):
            raise ValueError(
                f"strategy '{self.name}': entry_probability must be in [0, 1]")
        for key in ("take_profit_pct_range", "stop_loss_pct_range",
                    "hold_seconds_range"):
            if not _range_ok(p.get(key)):
                raise ValueError(
                    f"strategy '{self.name}': {key} must be [low, high] "
                    "with low <= high")
        close_prob = self._num(p.get("random_close_prob"))
        if close_prob is not None and not (0.0 <= close_prob <= 1.0):
            raise ValueError(
                f"strategy '{self.name}': random_close_prob must be in [0, 1]")

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        if self.params.get("require_price", True) and not snapshot.has_price:
            return None
        if snapshot.mint in self._rolled_mints:
            return None
        # One roll per mint, ever: a declined mint stays declined so the
        # monkey's entry rate really is entry_probability per candidate.
        self._rolled_mints.add(snapshot.mint)
        if ctx.rng.random() >= float(self.params["entry_probability"]):
            return None
        tp_lo, tp_hi = self.params["take_profit_pct_range"]
        sl_lo, sl_hi = self.params["stop_loss_pct_range"]
        hold_lo, hold_hi = self.params["hold_seconds_range"]
        plan = ExitPlan(
            take_profit_pct=ctx.rng.uniform(float(tp_lo), float(tp_hi)),
            stop_loss_pct=ctx.rng.uniform(float(sl_lo), float(sl_hi)),
            max_hold_seconds=ctx.rng.uniform(float(hold_lo), float(hold_hi)),
            random_close_prob=self._num(self.params.get("random_close_prob")),
        )
        return EntryIntent(reason="MONKEY_RANDOM_ROLL_HIT", plan=plan)


__all__ = ["MonkeyRandomStrategy"]
