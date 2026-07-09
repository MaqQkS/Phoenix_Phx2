"""THREE_X_INITIALS_RUNNER: the moonbag strategy.

Enters eligible candidates and holds toward ``recover_multiple`` (default
3x). At the multiple it sells just enough virtual tokens to recover the
initial cost basis; the remaining tokens ride as a runner with a
configurable trailing stop, runner max hold, and the engine's data-dead
handling. Realized PnL from the recovery leg and unrealized runner PnL are
tracked separately on the position (``strategy_state`` + the standard
realized/unrealized fields).
"""

from __future__ import annotations

from typing import List, Optional

from PHX2.paper_trading.config import STRATEGY_THREE_X
from PHX2.paper_trading.models import CandidateSnapshot, ExitPlan, PaperPosition
from PHX2.paper_trading.strategy import (
    EXIT_PARTIAL,
    EntryIntent,
    ExitIntent,
    PaperStrategy,
    StrategyContext,
)

RUNNER_WAITING = "WAITING_FOR_MULTIPLE"
RUNNER_ACTIVE = "RUNNER_ACTIVE"


class ThreeXInitialsRunnerStrategy(PaperStrategy):
    strategy_type = STRATEGY_THREE_X

    def validate_params(self) -> None:
        mult = self._num(self.params.get("recover_multiple"))
        if mult is None or mult <= 1.0:
            raise ValueError(
                f"strategy '{self.name}': recover_multiple must be > 1")
        trail = self._num(self.params.get("runner_trailing_stop_pct"))
        if trail is not None and not (0.0 < trail < 1.0):
            raise ValueError(
                f"strategy '{self.name}': runner_trailing_stop_pct must be "
                "in (0, 1)")
        sl = self._num(self.params.get("stop_loss_pct"))
        if sl is not None and sl >= 0:
            raise ValueError(
                f"strategy '{self.name}': stop_loss_pct must be negative")

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        if not snapshot.has_price:
            return None
        if not self.passes_entry_filters(snapshot):
            return None
        plan = ExitPlan(
            take_profit_pct=None,  # the recovery trim is the profit event
            stop_loss_pct=self._num(self.params.get("stop_loss_pct")),
            trailing_stop_pct=None,  # trailing starts once the runner exists
            max_hold_seconds=self._num(
                self.params.get("runner_max_hold_seconds")),
        )
        intent = EntryIntent(reason="THREE_X_ELIGIBLE_ENTRY", plan=plan)
        return intent

    def manage(self, position: PaperPosition, snapshot: CandidateSnapshot,
               ctx: StrategyContext) -> List[ExitIntent]:
        state = position.strategy_state
        state.setdefault("runner_status", RUNNER_WAITING)
        if state.get("initial_recovered"):
            return []
        if not snapshot.has_price or not position.entry_price:
            return []
        multiple = snapshot.price_usd / position.entry_price
        recover_multiple = float(self.params["recover_multiple"])
        if multiple < recover_multiple * (1.0 - 1e-9):  # float-noise tolerant
            return []
        state["initial_recovered"] = True
        state["runner_status"] = RUNNER_ACTIVE
        state["recovered_at_multiple"] = round(multiple, 4)
        state["initial_cost_usd"] = round(position.cost_basis_usd, 6)
        position.plan.trailing_stop_pct = self._num(
            self.params.get("runner_trailing_stop_pct"))
        position.post_trim_peak_price = snapshot.price_usd
        return [ExitIntent(
            kind=EXIT_PARTIAL,
            recover_usd=position.cost_basis_usd,
            reason=f"INITIALS_RECOVERED_AT_{recover_multiple:g}X",
        )]


__all__ = ["ThreeXInitialsRunnerStrategy", "RUNNER_WAITING", "RUNNER_ACTIVE"]
