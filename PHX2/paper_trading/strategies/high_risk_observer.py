"""HIGH_RISK_OBSERVER: the separated degen/scam study bucket.

Enters ONLY candidates the risk layer currently labels RISK_HIGH — exactly the coins every
default strategy refuses — so the clean strategies' results (BALA_PLAN / CONFIG_PLAN /
THREE_X / monkeys) stay unpolluted while the high-risk cohort is still measured end to end
(how fast they die, whether any survive, what the realized wreckage looks like).

Simulation-only like every paper strategy: virtual fills only, no signing or trading surface
of any kind. The engine's high-risk entry gate does not apply to this bucket (its
StrategyConfig defaults ``allow_high_risk`` to True by type); everything else — sizing
punishment, rug/data-lost handling, TP/SL/max-hold — is the standard engine machinery.
"""

from __future__ import annotations

from typing import Dict, Optional

from PHX2.paper_trading.config import STRATEGY_HIGH_RISK_OBSERVER
from PHX2.paper_trading.models import CandidateSnapshot, ExitPlan
from PHX2.paper_trading.risk import RISK_HIGH
from PHX2.paper_trading.strategy import (
    EntryIntent,
    PaperStrategy,
    StrategyContext,
)


class HighRiskObserverStrategy(PaperStrategy):
    strategy_type = STRATEGY_HIGH_RISK_OBSERVER

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        self._entries = 0
        self._not_high_risk_passes = 0

    def validate_params(self) -> None:
        sl = self._num(self.params.get("stop_loss_pct"))
        if sl is not None and sl >= 0:
            raise ValueError(
                f"strategy '{self.name}': stop_loss_pct must be negative")

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        if self.params.get("require_price", True) and not snapshot.has_price:
            return None
        label, reasons = self.snapshot_risk(snapshot, ctx)
        if self.params.get("only_high_risk", True) and label != RISK_HIGH:
            # LOW/MEDIUM/UNKNOWN stay with the clean strategies; this bucket
            # must never dilute itself with ordinary candidates.
            self._not_high_risk_passes += 1
            return None
        self._entries += 1
        primary = reasons[0] if reasons else "UNSPECIFIED"
        plan = ExitPlan(
            take_profit_pct=self._num(self.params.get("take_profit_pct")),
            stop_loss_pct=self._num(self.params.get("stop_loss_pct")),
            trailing_stop_pct=self._num(self.params.get("trailing_stop_pct")),
            max_hold_seconds=self._num(self.params.get("max_hold_seconds")),
        )
        return EntryIntent(
            reason=f"HIGH_RISK_OBSERVER_{primary}",
            plan=plan,
        )

    def monitor_snapshot(self) -> Dict[str, int]:
        return {
            "high_risk_entries": self._entries,
            "non_high_risk_passed_over": self._not_high_risk_passes,
        }


__all__ = ["HighRiskObserverStrategy"]
