"""Strategy interface for the PHX2 paper trading engine.

A strategy answers two questions over the shared candidate stream:

* ``wants_entry(snapshot, ctx)`` -- should we open a virtual position now?
  Returns an :class:`EntryIntent` (reason + exit plan) or ``None``.
* ``manage(position, snapshot, ctx)`` -- strategy-specific management of an
  open position on a fresh price update (e.g. the 3x initial-recovery trim).
  Returns a list of :class:`ExitIntent`.

The engine enforces the *generic* exit rules from each position's
:class:`~PHX2.paper_trading.models.ExitPlan` (take profit, stop loss,
trailing stop, max hold, random close, rug and data-lost handling), so most
strategies only decide entries and special partial exits.

Determinism: strategies must draw randomness ONLY from ``ctx.rng`` (a
per-strategy ``random.Random`` seeded from the run's ``random_seed``) and
must never read the wall clock; ``ctx.now_epoch`` is event time.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from PHX2.paper_trading.config import StrategyConfig
from PHX2.paper_trading.models import CandidateSnapshot, ExitPlan, PaperPosition


@dataclass
class EntryIntent:
    """A strategy's request to open a position for the current snapshot.

    ``leg`` labels the first buy leg (ENTRY / SCOUT / DCA_1). A
    ``size_fraction`` below 1.0 scales the sizing profile's capped size
    (e.g. a 10% scout); ``max_total_usd`` hard-caps this first leg.
    ``state_seed`` is merged into the new position's ``strategy_state`` so
    a Tier/DCA state machine can stamp its state at open time.
    """

    reason: str
    plan: ExitPlan = field(default_factory=ExitPlan)
    leg: str = "ENTRY"
    size_fraction: float = 1.0
    max_total_usd: Optional[float] = None
    state_seed: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AddIntent:
    """A strategy's request to add a buy leg (DCA) to an OPEN position.

    ``size_usd`` is the leg budget the strategy computed; the engine still
    runs it through the sizing cap chain (liquidity / volume / abs caps,
    min notional, slippage + impact), so a DCA can be shrunk or skipped by
    market reality. ``max_total_usd`` caps the position's total virtual
    cost after the add.
    """

    leg: str
    size_usd: float
    reason: str = "DCA"
    max_total_usd: Optional[float] = None
    max_total_tokens: Optional[float] = None
    state_seed: Dict[str, Any] = field(default_factory=dict)


EXIT_FULL = "FULL"
EXIT_PARTIAL = "PARTIAL"


@dataclass
class ExitIntent:
    """A strategy's request to (partially) close an open position.

    ``fraction`` sells that fraction of the currently open tokens;
    ``recover_usd`` sells just enough tokens to realize that many USD of
    proceeds (used by the 3x initial-recovery trim). Exactly one of the two
    should be set for PARTIAL; FULL ignores both. ``leg`` labels the sell
    fill (PARTIAL_SELL / INITIALS_RECOVERY / ...); None lets the engine
    pick a default.
    """

    kind: str = EXIT_FULL
    fraction: Optional[float] = None
    recover_usd: Optional[float] = None
    status: Optional[str] = None  # engine default: CLOSED
    reason: str = "STRATEGY_EXIT"
    leg: Optional[str] = None


@dataclass
class StrategyContext:
    """Read-only per-event context handed to strategies."""

    rng: random.Random
    now_epoch: float
    sol_price_usd: Optional[float] = None
    # Engine-provided lookups over the replayed stream so far.
    observed_peak_mc: Callable[[str], Optional[float]] = lambda mint: None
    first_seen_epoch: Callable[[str], Optional[float]] = lambda mint: None
    # Preview of the strategy's own sizing profile against a snapshot
    # (a SizingDecision, or None when unavailable). Lets a DCA ladder
    # derive per-leg budgets from the profile's capped max position.
    sizing_preview: Callable[[CandidateSnapshot], Any] = lambda snapshot: None


class PaperStrategy:
    """Base class. Subclasses set ``strategy_type`` and implement hooks."""

    strategy_type: str = "BASE"

    def __init__(self, cfg: StrategyConfig) -> None:
        self.cfg = cfg
        self.name = cfg.name
        self.params: Dict[str, Any] = dict(cfg.params)
        self.validate_params()

    # -- hooks -----------------------------------------------------------

    def validate_params(self) -> None:
        """Raise ValueError on unusable params. Overridden as needed."""

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        raise NotImplementedError

    def manage(self, position: PaperPosition, snapshot: CandidateSnapshot,
               ctx: StrategyContext) -> List[Any]:
        """Return AddIntent / ExitIntent objects for an open position on a
        fresh price update. Default: no strategy-specific management."""
        return []

    def monitor_snapshot(self) -> Dict[str, Any]:
        """Small JSON-safe view of strategy-internal state (e.g. Tier/DCA
        machine counts) for the live monitor artifacts. Default: empty."""
        return {}

    def on_position_opened(self, position: PaperPosition) -> None:
        """Called by the engine right after an entry fill lands. Default:
        no-op."""

    def on_position_terminal(self, position: PaperPosition) -> None:
        """Called by the engine when a position of this strategy reaches a
        terminal status (closed / rugged / data-lost / skipped), so state
        machines can sync their per-mint state. Default: no-op."""

    # -- shared helpers ---------------------------------------------------

    @staticmethod
    def _num(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def passes_entry_filters(self, snapshot: CandidateSnapshot,
                             check_tiers: bool = True) -> bool:
        """Common optional entry filters; a configured filter with missing
        data fails closed (no entry on unknown market state).

        ``check_tiers=False`` lets a strategy that derives its own tier
        (BALA_PLAN) enforce the tier rule itself after derivation."""
        p = self.params
        min_mc = self._num(p.get("min_entry_market_cap_usd"))
        max_mc = self._num(p.get("max_entry_market_cap_usd"))
        min_lp = self._num(p.get("min_entry_liquidity_usd"))
        min_vol = self._num(p.get("min_entry_volume_usd"))
        if min_mc is not None and (snapshot.market_cap_usd is None
                                   or snapshot.market_cap_usd < min_mc):
            return False
        if max_mc is not None and (snapshot.market_cap_usd is None
                                   or snapshot.market_cap_usd > max_mc):
            return False
        if min_lp is not None and (snapshot.liquidity_usd is None
                                   or snapshot.liquidity_usd < min_lp):
            return False
        if min_vol is not None and (snapshot.volume_usd is None
                                    or snapshot.volume_usd < min_vol):
            return False
        if check_tiers:
            allowed_tiers = p.get("allowed_tiers")
            if allowed_tiers is not None:
                if snapshot.tier is None or snapshot.tier not in [
                        int(t) for t in allowed_tiers]:
                    return False
        return True


def build_strategy(cfg: StrategyConfig) -> PaperStrategy:
    """Instantiate the strategy implementation for a StrategyConfig."""
    # Imported here to avoid import cycles at module load.
    from PHX2.paper_trading.strategies.bala_plan import BalaPlanStrategy
    from PHX2.paper_trading.strategies.config_plan import ConfigPlanStrategy
    from PHX2.paper_trading.strategies.monkey_random import MonkeyRandomStrategy
    from PHX2.paper_trading.strategies.monkey_hold import MonkeyHoldStrategy
    from PHX2.paper_trading.strategies.three_x_initials_runner import (
        ThreeXInitialsRunnerStrategy,
    )

    registry = {
        BalaPlanStrategy.strategy_type: BalaPlanStrategy,
        ConfigPlanStrategy.strategy_type: ConfigPlanStrategy,
        MonkeyRandomStrategy.strategy_type: MonkeyRandomStrategy,
        MonkeyHoldStrategy.strategy_type: MonkeyHoldStrategy,
        ThreeXInitialsRunnerStrategy.strategy_type: ThreeXInitialsRunnerStrategy,
    }
    impl = registry.get(cfg.strategy_type)
    if impl is None:
        raise ValueError(
            f"strategy '{cfg.name}': no implementation for type "
            f"'{cfg.strategy_type}'")
    return impl(cfg)


__all__ = [
    "EntryIntent",
    "AddIntent",
    "ExitIntent",
    "EXIT_FULL",
    "EXIT_PARTIAL",
    "StrategyContext",
    "PaperStrategy",
    "build_strategy",
]
