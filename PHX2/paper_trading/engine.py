"""The PHX2 paper trading engine.

Consumes a time-ordered stream of :class:`CandidateSnapshot` and runs every
enabled strategy over it with virtual positions:

* entries go through the sizing module (liquidity-punishing fills),
* the engine enforces each position's generic exit plan (take profit, stop
  loss, trailing stop, max hold, random close) plus rug and data-lost
  handling from the market-sim config,
* strategies add their special management (3x initial recovery, 5x trim),
* every transition is appended to the paper ledgers and summarized into
  dashboard-ready artifacts.

Replay mode is event-time driven end to end: the wall clock is never read,
so the same inputs + config + seed reproduce byte-identical ledgers. Live
paper mode feeds the same engine from a tailing snapshot source.
"""

from __future__ import annotations

import json
import random
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from PHX2.paper_trading.config import (
    END_OF_STREAM_CLOSE,
    PaperConfig,
    RUG_ACTION_FREEZE,
    StrategyConfig,
)
from PHX2.paper_trading.ledger import (
    OPEN_POSITIONS_FILE,
    COMPARISON_JSON_FILE,
    COMPARISON_MD_FILE,
    HEARTBEAT_FILE,
    LIVE_MONITOR_FILE,
    RUN_CONFIG_ECHO_FILE,
    SUMMARY_FILE,
    PaperLedger,
    load_last_positions,
    reset_run_dir,
    run_dir_has_artifacts,
)
from PHX2.paper_trading.models import (
    CandidateSnapshot,
    ExitPlan,
    LEG_FINAL,
    LEG_PARTIAL_SELL,
    LEG_RUNNER_CLOSE,
    PaperFill,
    PaperPosition,
    SIDE_BUY,
    SIDE_SELL,
    STATUS_CLOSED,
    STATUS_DATA_LOST,
    STATUS_EXPIRED,
    STATUS_OPEN,
    STATUS_RUGGED,
    STATUS_SKIPPED_LIQUIDITY_CAP,
    STATUS_SKIPPED_MIN_NOTIONAL,
    STATUS_SKIPPED_PRICE_MISSING,
    STATUS_SKIPPED_SIZING,
    STATUS_STOPPED,
    STATUS_TAKE_PROFIT,
    parse_utc,
    utc_iso,
)
from PHX2.paper_trading.reporting import (
    build_comparison,
    build_run_summary,
    comparison_markdown,
)
from PHX2.paper_trading.sizing import (
    SKIP_MIN_NOTIONAL_NOT_MET,
    SKIP_NO_ENTRY_PRICE,
    SKIP_NO_LIQUIDITY_DATA,
    compute_sizing,
    effective_sell_price,
    simulate_impact_bps,
)
from PHX2.paper_trading.strategy import (
    AddIntent,
    EXIT_FULL,
    EntryIntent,
    ExitIntent,
    StrategyContext,
    build_strategy,
)

MODE_REPLAY = "REPLAY"
MODE_LIVE_PAPER = "LIVE_PAPER"


class ReplayRunDirError(RuntimeError):
    """Raised when a replay targets a run directory that already holds
    paper artifacts (appending would duplicate ledger rows and break
    reproducibility). Pass overwrite (CLI: --overwrite-run) to reset it."""


def resolve_run_id(config: PaperConfig, mode: str) -> str:
    """The run id an engine will use for this config + mode."""
    if config.run.run_id:
        return config.run.run_id
    prefix = "replay" if mode == MODE_REPLAY else "live"
    return f"{prefix}_{config.config_digest()}_s{config.run.random_seed}"

_SKIP_STATUS_BY_REASON = {
    SKIP_NO_ENTRY_PRICE: STATUS_SKIPPED_PRICE_MISSING,
    SKIP_NO_LIQUIDITY_DATA: STATUS_SKIPPED_LIQUIDITY_CAP,
    SKIP_MIN_NOTIONAL_NOT_MET: STATUS_SKIPPED_MIN_NOTIONAL,
}


class _MintState:
    __slots__ = ("last_price", "last_price_epoch", "last_mc", "last_lp",
                 "peak_mc", "first_seen_epoch", "symbol")

    def __init__(self) -> None:
        self.last_price: Optional[float] = None
        self.last_price_epoch: Optional[float] = None
        self.last_mc: Optional[float] = None
        self.last_lp: Optional[float] = None
        self.peak_mc: Optional[float] = None
        self.first_seen_epoch: Optional[float] = None
        self.symbol: Optional[str] = None


class _StrategyRuntime:
    """Engine-side state for one strategy instance."""

    def __init__(self, cfg: StrategyConfig, seed: int,
                 profile_name: str) -> None:
        self.cfg = cfg
        self.strategy = build_strategy(cfg)
        self.rng = random.Random(f"{seed}:{cfg.name}")
        self.profile_name = profile_name
        self.open_by_mint: Dict[str, PaperPosition] = {}
        self.traded_mints: Set[str] = set()
        self.trade_seq = 0
        self.realized_pnl_usd = 0.0
        self.equity_series: List[float] = []
        self.last_opened: Optional[str] = None
        self.last_closed: Optional[str] = None
        self.last_dca: Optional[str] = None

    def next_trade_id(self, mint: str) -> str:
        self.trade_seq += 1
        return f"{self.cfg.name}-{self.trade_seq:05d}-{mint[:8]}"

    def unrealized_pnl_usd(self) -> float:
        return sum(p.unrealized_pnl_usd for p in self.open_by_mint.values())


class PaperTradingEngine:
    """Runs all enabled strategies over one snapshot stream."""

    def __init__(self, config: PaperConfig,
                 run_dir: Optional[str] = None,
                 mode: str = MODE_REPLAY,
                 resume: bool = False,
                 quiet: bool = False,
                 echo: Callable[[str], None] = print,
                 wall_clock: Optional[Callable[[], float]] = None) -> None:
        self.config = config
        self.mode = mode
        self.quiet = quiet
        self.echo = echo
        # Live mode injects a wall clock for heartbeat stamps; replay keeps
        # it None so every artifact timestamp stays event-time (and runs
        # stay byte-reproducible).
        self.wall_clock = wall_clock
        self._started_wall = wall_clock() if wall_clock else None
        self.watch_inputs: List[str] = []
        self.sim = config.market_sim
        self.sol_price_usd = config.run.sol_price_usd

        digest = config.config_digest()
        self.run_id = resolve_run_id(config, mode)
        base_dir = run_dir or str(
            Path(config.run.output_root) / self.run_id)
        self.ledger = PaperLedger(base_dir)
        self.run_dir = str(self.ledger.run_dir)

        self.runtimes: List[_StrategyRuntime] = []
        for strat_cfg in config.enabled_strategies():
            self.runtimes.append(_StrategyRuntime(
                strat_cfg, config.run.random_seed, strat_cfg.sizing_profile))

        self.market: Dict[str, _MintState] = {}
        self.now_epoch: Optional[float] = None
        self.snapshots_processed = 0
        self.last_snapshot: Optional[CandidateSnapshot] = None
        self.last_error: Optional[str] = None
        self.last_skip: Optional[str] = None
        self.recent_events: deque = deque(
            maxlen=max(1, int(config.run.recent_events_window)))
        self._next_heartbeat_epoch: Optional[float] = None
        self._next_equity_epoch: Optional[float] = None
        # Final (or latest) position record per trade id, for reporting.
        self._final_records: Dict[str, Dict[str, Any]] = {}

        self.ledger.write_json_atomic(RUN_CONFIG_ECHO_FILE, {
            "run_id": self.run_id,
            "mode": self.mode,
            "config": config.to_dict(),
            "config_digest": digest,
        })
        if resume:
            self._resume_from_ledger()

    # ------------------------------------------------------------------
    # Resume
    # ------------------------------------------------------------------

    def _load_open_positions_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Freshest OPEN-position records from paper_open_positions.json.

        The positions ledger appends rows only on transitions, so after an
        abrupt stop its last OPEN row may hold a stale trailing peak. The
        monitor snapshot is rewritten on every data poll / heartbeat and
        carries full state (peak_price / post_trim_peak_price included)."""
        path = Path(self.run_dir) / OPEN_POSITIONS_FILE
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for record in payload.get("open_positions", []) or []:
            trade_id = record.get("paper_trade_id")
            if isinstance(trade_id, str) and trade_id:
                out[trade_id] = record
        return out

    def _resume_from_ledger(self) -> None:
        latest = load_last_positions(self.run_dir)
        snapshot_open = self._load_open_positions_snapshot()
        by_name = {rt.cfg.name: rt for rt in self.runtimes}
        restored_open = 0
        for trade_id, record in latest.items():
            if record.get("status") == STATUS_OPEN and trade_id in snapshot_open:
                fresher = snapshot_open[trade_id]
                ledger_ts = parse_utc(record.get("latest_price_at_utc"))
                snap_ts = parse_utc(fresher.get("latest_price_at_utc"))
                if ledger_ts is None or (snap_ts is not None
                                         and snap_ts >= ledger_ts):
                    record = fresher
            runtime = by_name.get(record.get("strategy_name"))
            if runtime is None:
                continue
            self._final_records[record["paper_trade_id"]] = record
            runtime.trade_seq += 1
            mint = record.get("mint")
            if isinstance(mint, str) and mint:
                runtime.traded_mints.add(mint)
            runtime.realized_pnl_usd += float(
                record.get("realized_pnl_usd") or 0.0)
            if record.get("status") == STATUS_OPEN:
                position = PaperPosition.from_record(record)
                runtime.open_by_mint[position.mint] = position
                restored_open += 1
        if restored_open:
            self._emit_event({
                "event": "RESUMED_OPEN_POSITIONS",
                "count": restored_open,
            }, ts_epoch=None)

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------

    def _emit_event(self, payload: Dict[str, Any],
                    ts_epoch: Optional[float]) -> None:
        record = dict(payload)
        record["run_id"] = self.run_id
        record["ts_utc"] = utc_iso(ts_epoch if ts_epoch is not None
                                   else self.now_epoch)
        self.ledger.append_event(record)
        self.recent_events.append(record)

    def _record_position(self, position: PaperPosition) -> None:
        record = position.to_record()
        self._final_records[position.paper_trade_id] = record
        self.ledger.append_position(record)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def process_snapshot(self, snapshot: CandidateSnapshot) -> None:
        """Advance the engine by one normalized market observation."""
        self.snapshots_processed += 1
        self.last_snapshot = snapshot
        if self.now_epoch is None or snapshot.ts_epoch > self.now_epoch:
            self.now_epoch = snapshot.ts_epoch
        self._update_market(snapshot)

        for runtime in self.runtimes:
            position = runtime.open_by_mint.get(snapshot.mint)
            if position is not None:
                self._update_open_position(runtime, position, snapshot)
            else:
                self._consider_entry(runtime, snapshot)

        self._check_time_exits()
        self._maybe_equity_points()
        self._maybe_heartbeat()

    def process_idle_tick(self, now_epoch: float) -> None:
        """Advance the engine clock without a snapshot (live mode).

        Lets time-based exits (max hold, data-lost) and heartbeats fire
        while the input feed is quiet. Replay never needs this: there the
        stream itself is the clock.
        """
        if self.now_epoch is None or now_epoch > self.now_epoch:
            self.now_epoch = now_epoch
        self._check_time_exits()
        self._maybe_equity_points()
        self._maybe_heartbeat()

    def _update_market(self, snapshot: CandidateSnapshot) -> None:
        state = self.market.get(snapshot.mint)
        if state is None:
            state = _MintState()
            state.first_seen_epoch = snapshot.ts_epoch
            self.market[snapshot.mint] = state
        if snapshot.symbol:
            state.symbol = snapshot.symbol
        if snapshot.has_price:
            state.last_price = snapshot.price_usd
            state.last_price_epoch = snapshot.ts_epoch
        if snapshot.market_cap_usd is not None:
            state.last_mc = snapshot.market_cap_usd
            if state.peak_mc is None or snapshot.market_cap_usd > state.peak_mc:
                state.peak_mc = snapshot.market_cap_usd
        if snapshot.liquidity_usd is not None:
            state.last_lp = snapshot.liquidity_usd

    def _context(self, runtime: _StrategyRuntime) -> StrategyContext:
        market = self.market
        profile = self.config.sizing_profiles[runtime.profile_name]
        sim = self.sim
        sol_price = self.sol_price_usd

        def observed_peak_mc(mint: str) -> Optional[float]:
            state = market.get(mint)
            return state.peak_mc if state else None

        def first_seen(mint: str) -> Optional[float]:
            state = market.get(mint)
            return state.first_seen_epoch if state else None

        def sizing_preview(snapshot: CandidateSnapshot):
            return compute_sizing(profile, snapshot, sim, sol_price)

        return StrategyContext(
            rng=runtime.rng,
            now_epoch=self.now_epoch or 0.0,
            sol_price_usd=self.sol_price_usd,
            observed_peak_mc=observed_peak_mc,
            first_seen_epoch=first_seen,
            sizing_preview=sizing_preview,
        )

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------

    def _consider_entry(self, runtime: _StrategyRuntime,
                        snapshot: CandidateSnapshot) -> None:
        if snapshot.mint in runtime.traded_mints and \
                not runtime.cfg.allow_reentry:
            return
        try:
            intent = runtime.strategy.wants_entry(
                snapshot, self._context(runtime))
        except Exception as exc:  # a broken strategy must not kill the run
            self._note_error(f"{runtime.cfg.name}.wants_entry: {exc}",
                             snapshot)
            return
        if intent is None:
            return
        if len(runtime.open_by_mint) >= runtime.cfg.max_open_positions:
            self._emit_event({
                "event": "ENTRY_SKIPPED_MAX_OPEN",
                "strategy_name": runtime.cfg.name,
                "mint": snapshot.mint,
                "max_open_positions": runtime.cfg.max_open_positions,
            }, snapshot.ts_epoch)
            return

        profile = self.config.sizing_profiles[runtime.profile_name]
        decision = compute_sizing(profile, snapshot, self.sim,
                                  self.sol_price_usd)

        # Fractional first legs (scout / DCA_1 ladders) re-run the leg
        # budget through the same cap chain so the fill simulation matches
        # the actual leg size.
        fraction = float(getattr(intent, "size_fraction", 1.0) or 1.0)
        is_fractional = fraction < 1.0 or intent.max_total_usd is not None
        if not decision.is_skip and is_fractional:
            leg_usd = decision.final_size_usd * min(max(fraction, 0.0), 1.0)
            if intent.max_total_usd is not None:
                leg_usd = min(leg_usd, float(intent.max_total_usd))
            decision = compute_sizing(profile, snapshot, self.sim,
                                      self.sol_price_usd,
                                      requested_usd_override=leg_usd)

        if decision.is_skip:
            skip_reason = decision.skipped_reason or "ZERO_SIZE"
            self.last_skip = (f"{runtime.cfg.name} {snapshot.mint[:8]}.. "
                              f"{skip_reason}")
            if is_fractional:
                # A leg that is currently too small / unsizable is not a
                # terminal verdict on the mint: the machine keeps watching
                # and may enter on a later, healthier snapshot.
                self._emit_event({
                    "event": "ENTRY_LEG_SKIPPED",
                    "strategy_name": runtime.cfg.name,
                    "mint": snapshot.mint,
                    "leg": intent.leg,
                    "reason": skip_reason,
                    "sizing": decision.to_record(),
                }, snapshot.ts_epoch)
                return
            runtime.traded_mints.add(snapshot.mint)
            trade_id = runtime.next_trade_id(snapshot.mint)
            status = _SKIP_STATUS_BY_REASON.get(skip_reason,
                                                STATUS_SKIPPED_SIZING)
            position = self._new_position(runtime, snapshot, trade_id, intent)
            position.status = status
            position.reason_closed = skip_reason
            position.cap_reasons = list(decision.cap_reasons)
            position.closed_at_epoch = snapshot.ts_epoch
            self._notify_terminal(runtime, position)
            self._record_position(position)
            self._emit_event({
                "event": "ENTRY_SKIPPED",
                "strategy_name": runtime.cfg.name,
                "mint": snapshot.mint,
                "paper_trade_id": trade_id,
                "status": status,
                "reason": skip_reason,
                "sizing": decision.to_record(),
            }, snapshot.ts_epoch)
            return

        runtime.traded_mints.add(snapshot.mint)
        trade_id = runtime.next_trade_id(snapshot.mint)
        position = self._new_position(runtime, snapshot, trade_id, intent)
        position.opened_at_epoch = snapshot.ts_epoch
        position.entry_market_cap = decision.entry_market_cap
        position.entry_liquidity = decision.entry_liquidity
        position.target_token_amount = decision.target_token_amount
        position.simulated_slippage_bps = decision.simulated_slippage_bps
        position.simulated_market_impact_bps = decision.simulated_market_impact_bps
        position.simulated_fee_bps = decision.simulated_fee_bps
        position.cap_reasons = list(decision.cap_reasons)
        position.strategy_state.update(
            getattr(intent, "state_seed", None) or {})
        eff_price = (decision.final_size_usd
                     / decision.estimated_tokens_received
                     if decision.estimated_tokens_received > 0
                     else snapshot.price_usd)
        position.apply_buy_leg(
            leg=intent.leg,
            ts_epoch=snapshot.ts_epoch,
            tokens=decision.estimated_tokens_received,
            cost_usd=decision.final_size_usd,
            price_raw=snapshot.price_usd,
            price_effective=eff_price,
            liquidity=snapshot.liquidity_usd,
            market_cap=snapshot.market_cap_usd,
            reason=intent.reason,
        )
        position.virtual_sol_size = decision.final_size_sol
        position.peak_price = snapshot.price_usd
        position.mark_price(snapshot.price_usd, snapshot.ts_epoch,
                            snapshot.market_cap_usd, snapshot.liquidity_usd)

        fee_usd = decision.final_size_usd * self.sim.fee_bps / 10_000.0
        fill = PaperFill(
            fill_id=f"{trade_id}-F{1:03d}",
            paper_trade_id=trade_id,
            strategy_name=runtime.cfg.name,
            run_id=self.run_id,
            mint=snapshot.mint,
            side=SIDE_BUY,
            ts_epoch=snapshot.ts_epoch,
            price_raw=snapshot.price_usd,
            price_effective=eff_price,
            tokens=decision.estimated_tokens_received,
            notional_usd=decision.final_size_usd,
            fee_usd=fee_usd,
            slippage_bps=decision.simulated_slippage_bps,
            impact_bps=decision.simulated_market_impact_bps,
            reason=intent.reason,
            leg=intent.leg,
        )
        position.strategy_state["fill_count"] = 1
        runtime.open_by_mint[snapshot.mint] = position
        runtime.last_opened = (
            f"{snapshot.mint[:8]}.. {intent.leg} {intent.reason} "
            f"${decision.final_size_usd:,.2f}")
        self.ledger.append_fill(fill.to_record())
        self._record_position(position)
        try:
            runtime.strategy.on_position_opened(position)
        except Exception as exc:
            self._note_error(
                f"{runtime.cfg.name}.on_position_opened: {exc}", snapshot)
        self._emit_event({
            "event": "POSITION_OPENED",
            "strategy_name": runtime.cfg.name,
            "mint": snapshot.mint,
            "paper_trade_id": trade_id,
            "leg": intent.leg,
            "reason": intent.reason,
            "size_usd": round(decision.final_size_usd, 6),
            "tokens": decision.estimated_tokens_received,
            "cap_reasons": list(decision.cap_reasons),
        }, snapshot.ts_epoch)

    def _new_position(self, runtime: _StrategyRuntime,
                      snapshot: CandidateSnapshot, trade_id: str,
                      intent: Any) -> PaperPosition:
        return PaperPosition(
            paper_trade_id=trade_id,
            strategy_name=runtime.cfg.name,
            run_id=self.run_id,
            mint=snapshot.mint,
            token_symbol=snapshot.symbol or (
                self.market.get(snapshot.mint).symbol
                if snapshot.mint in self.market else None),
            source_candidate_id=snapshot.candidate_id,
            source_kind=snapshot.source_kind,
            reason_opened=intent.reason,
            tier=snapshot.tier,
            entry_drawdown_pct=snapshot.drawdown_pct,
            score=snapshot.score,
            plan=intent.plan or ExitPlan(),
        )

    # ------------------------------------------------------------------
    # Open-position management
    # ------------------------------------------------------------------

    def _update_open_position(self, runtime: _StrategyRuntime,
                              position: PaperPosition,
                              snapshot: CandidateSnapshot) -> None:
        if snapshot.liquidity_usd is not None:
            position.latest_liquidity = snapshot.liquidity_usd
        if snapshot.market_cap_usd is not None:
            position.latest_market_cap = snapshot.market_cap_usd
        if not snapshot.has_price:
            return
        position.mark_price(snapshot.price_usd, snapshot.ts_epoch,
                            snapshot.market_cap_usd, snapshot.liquidity_usd)

        # Strategy-specific management first (DCA ladder, 3x recovery,
        # 5x trim); each new snapshot is a re-audit opportunity.
        prev_dca_skip = position.strategy_state.get("last_dca_skip")
        try:
            intents = runtime.strategy.manage(
                position, snapshot, self._context(runtime))
        except Exception as exc:
            self._note_error(f"{runtime.cfg.name}.manage: {exc}", snapshot)
            intents = []
        new_dca_skip = position.strategy_state.get("last_dca_skip")
        if new_dca_skip and new_dca_skip != prev_dca_skip:
            # Surface strategy-level DCA vetoes on the console monitor.
            self.last_skip = (f"{runtime.cfg.name} {position.mint[:8]}.. "
                              f"DCA {new_dca_skip}")
        for intent in intents:
            if isinstance(intent, AddIntent):
                self._add_leg(runtime, position, snapshot, intent)
            else:
                self._apply_exit_intent(runtime, position, snapshot, intent)
                if not position.is_open:
                    return

        self._standard_exit_checks(runtime, position, snapshot)

    def _add_leg(self, runtime: _StrategyRuntime, position: PaperPosition,
                 snapshot: CandidateSnapshot, intent: AddIntent) -> None:
        """Add a DCA buy leg to an open position (strategy-requested)."""
        if not snapshot.has_price or intent.size_usd is None:
            return
        profile = self.config.sizing_profiles[runtime.profile_name]
        budget = float(intent.size_usd)
        if intent.max_total_usd is not None:
            budget = min(budget,
                         float(intent.max_total_usd)
                         - position.virtual_usd_size)
        decision = compute_sizing(profile, snapshot, self.sim,
                                  self.sol_price_usd,
                                  requested_usd_override=budget)
        if not decision.is_skip and intent.max_total_tokens is not None:
            remaining_tokens = (float(intent.max_total_tokens)
                                - position.estimated_tokens_received)
            if remaining_tokens <= 0:
                decision.skipped_reason = "DCA_MAX_EXPOSURE_TOKENS"
            elif decision.estimated_tokens_received > remaining_tokens:
                scale = remaining_tokens / decision.estimated_tokens_received
                decision = compute_sizing(
                    profile, snapshot, self.sim, self.sol_price_usd,
                    requested_usd_override=decision.final_size_usd * scale)
        if decision.is_skip:
            reason = decision.skipped_reason or "ZERO_SIZE"
            position.strategy_state["last_dca_skip"] = reason
            self.last_skip = (f"{runtime.cfg.name} {position.mint[:8]}.. "
                              f"DCA {reason}")
            self._emit_event({
                "event": "DCA_SKIPPED",
                "strategy_name": runtime.cfg.name,
                "mint": position.mint,
                "paper_trade_id": position.paper_trade_id,
                "leg": intent.leg,
                "reason": reason,
                "sizing": decision.to_record(),
            }, snapshot.ts_epoch)
            return

        eff_price = (decision.final_size_usd
                     / decision.estimated_tokens_received
                     if decision.estimated_tokens_received > 0
                     else snapshot.price_usd)
        position.apply_buy_leg(
            leg=intent.leg,
            ts_epoch=snapshot.ts_epoch,
            tokens=decision.estimated_tokens_received,
            cost_usd=decision.final_size_usd,
            price_raw=snapshot.price_usd,
            price_effective=eff_price,
            liquidity=snapshot.liquidity_usd,
            market_cap=snapshot.market_cap_usd,
            reason=intent.reason,
        )
        for cap_reason in decision.cap_reasons:
            if cap_reason not in position.cap_reasons:
                position.cap_reasons.append(cap_reason)
        position.strategy_state.update(intent.state_seed or {})
        if self.sol_price_usd:
            position.virtual_sol_size = (
                position.virtual_usd_size / self.sol_price_usd)
        position.refresh_unrealized(snapshot.price_usd)

        fill_no = int(position.strategy_state.get("fill_count", 1)) + 1
        position.strategy_state["fill_count"] = fill_no
        fee_usd = decision.final_size_usd * self.sim.fee_bps / 10_000.0
        fill = PaperFill(
            fill_id=f"{position.paper_trade_id}-F{fill_no:03d}",
            paper_trade_id=position.paper_trade_id,
            strategy_name=runtime.cfg.name,
            run_id=self.run_id,
            mint=position.mint,
            side=SIDE_BUY,
            ts_epoch=snapshot.ts_epoch,
            price_raw=snapshot.price_usd,
            price_effective=eff_price,
            tokens=decision.estimated_tokens_received,
            notional_usd=decision.final_size_usd,
            fee_usd=fee_usd,
            slippage_bps=decision.simulated_slippage_bps,
            impact_bps=decision.simulated_market_impact_bps,
            reason=intent.reason,
            leg=intent.leg,
        )
        runtime.last_dca = (
            f"{position.mint[:8]}.. {intent.leg} "
            f"${decision.final_size_usd:,.2f} ({intent.reason})")
        self.ledger.append_fill(fill.to_record())
        self._record_position(position)
        self._emit_event({
            "event": "POSITION_DCA",
            "strategy_name": runtime.cfg.name,
            "mint": position.mint,
            "paper_trade_id": position.paper_trade_id,
            "leg": intent.leg,
            "reason": intent.reason,
            "size_usd": round(decision.final_size_usd, 6),
            "tokens": decision.estimated_tokens_received,
            "total_position_usd": round(position.virtual_usd_size, 6),
            "blended_entry_price": position.entry_price,
            "cap_reasons": list(decision.cap_reasons),
        }, snapshot.ts_epoch)
        self._equity_point(runtime, snapshot.ts_epoch)

    def _apply_exit_intent(self, runtime: _StrategyRuntime,
                           position: PaperPosition,
                           snapshot: CandidateSnapshot,
                           intent: ExitIntent) -> None:
        price = snapshot.price_usd
        if price is None or position.tokens_open <= 0:
            return
        if intent.kind == EXIT_FULL:
            self._close_position(
                runtime, position, price, snapshot.ts_epoch,
                status=intent.status or STATUS_CLOSED,
                reason=intent.reason,
                liquidity=position.latest_liquidity,
                leg=intent.leg)
            return
        tokens = 0.0
        if intent.recover_usd is not None and intent.recover_usd > 0:
            impact = simulate_impact_bps(
                min(intent.recover_usd, position.tokens_open * price),
                position.latest_liquidity, self.sim)
            sell_price = effective_sell_price(
                price, self.sim.base_slippage_bps, impact)
            net_per_token = sell_price * (1.0 - self.sim.fee_bps / 10_000.0)
            if net_per_token > 0:
                tokens = intent.recover_usd / net_per_token
        elif intent.fraction is not None and intent.fraction > 0:
            tokens = position.tokens_open * min(1.0, float(intent.fraction))
        tokens = min(tokens, position.tokens_open)
        if tokens <= 0:
            return
        if tokens >= position.tokens_open * 0.9999:
            self._close_position(
                runtime, position, price, snapshot.ts_epoch,
                status=intent.status or STATUS_CLOSED,
                reason=intent.reason,
                liquidity=position.latest_liquidity,
                leg=intent.leg)
            return
        self._partial_exit(runtime, position, price, snapshot.ts_epoch,
                           tokens, intent.reason,
                           leg=intent.leg or LEG_PARTIAL_SELL)

    def _standard_exit_checks(self, runtime: _StrategyRuntime,
                              position: PaperPosition,
                              snapshot: CandidateSnapshot) -> None:
        price = snapshot.price_usd
        entry = position.entry_price
        if price is None or not entry or not position.is_open:
            return
        plan = position.plan
        ret = price / entry - 1.0
        eps = 1e-9  # tolerate float noise on threshold comparisons

        # 1. Rug detection (liquidity collapse or catastrophic price drop).
        lp_now = (snapshot.liquidity_usd
                  if snapshot.liquidity_usd is not None
                  else position.latest_liquidity)
        rugged = False
        rug_reason = ""
        if (lp_now is not None and position.entry_liquidity
                and position.entry_liquidity > 0
                and lp_now < position.entry_liquidity
                * self.sim.rug_lp_collapse_ratio):
            rugged, rug_reason = True, "LIQUIDITY_COLLAPSE"
        elif ret <= self.sim.rug_price_drop_pct:
            rugged, rug_reason = True, "PRICE_COLLAPSE"
        if rugged:
            if self.sim.rug_action == RUG_ACTION_FREEZE:
                self._freeze_rugged(runtime, position, snapshot.ts_epoch,
                                    rug_reason)
            else:
                self._close_position(
                    runtime, position, price, snapshot.ts_epoch,
                    status=STATUS_RUGGED, reason=rug_reason,
                    liquidity=lp_now)
            return

        # 2. Stop loss.
        if plan.stop_loss_pct is not None and ret <= plan.stop_loss_pct + eps:
            self._close_position(
                runtime, position, price, snapshot.ts_epoch,
                status=STATUS_STOPPED,
                reason=f"STOP_LOSS_{plan.stop_loss_pct:+.2f}",
                liquidity=lp_now)
            return

        # 3. Take profit.
        if plan.take_profit_pct is not None and \
                ret >= plan.take_profit_pct - eps:
            self._close_position(
                runtime, position, price, snapshot.ts_epoch,
                status=STATUS_TAKE_PROFIT,
                reason=f"TAKE_PROFIT_{plan.take_profit_pct:+.2f}",
                liquidity=lp_now)
            return

        # 4. Trailing stop (from post-trim peak when a trim happened).
        if plan.trailing_stop_pct is not None:
            ref_peak = (position.post_trim_peak_price
                        if position.post_trim_peak_price is not None
                        else position.peak_price)
            if ref_peak and price <= ref_peak * (1.0 - plan.trailing_stop_pct):
                self._close_position(
                    runtime, position, price, snapshot.ts_epoch,
                    status=STATUS_STOPPED,
                    reason=f"TRAILING_STOP_{plan.trailing_stop_pct:.2f}",
                    liquidity=lp_now)
                return

        # 5. Random close (monkey baseline behavior).
        if plan.random_close_prob:
            if runtime.rng.random() < float(plan.random_close_prob):
                self._close_position(
                    runtime, position, price, snapshot.ts_epoch,
                    status=STATUS_CLOSED, reason="RANDOM_CLOSE",
                    liquidity=lp_now)

    def _check_time_exits(self) -> None:
        if self.now_epoch is None:
            return
        for runtime in self.runtimes:
            for position in list(runtime.open_by_mint.values()):
                plan = position.plan
                opened = (position.opened_at_epoch
                          if position.opened_at_epoch is not None
                          else self.now_epoch)
                if (plan.max_hold_seconds is not None
                        and self.now_epoch - opened >= plan.max_hold_seconds):
                    price = (position.latest_price
                             if position.latest_price is not None
                             else position.entry_price)
                    self._close_position(
                        runtime, position, price, self.now_epoch,
                        status=STATUS_EXPIRED, reason="MAX_HOLD_EXPIRED",
                        liquidity=position.latest_liquidity)
                    continue
                last_data = (position.latest_price_epoch
                             if position.latest_price_epoch is not None
                             else opened)
                if self.now_epoch - last_data >= self.sim.data_lost_after_seconds:
                    self._close_data_lost(runtime, position)

    # ------------------------------------------------------------------
    # Exits / accounting
    # ------------------------------------------------------------------

    def _sell_tokens(self, position: PaperPosition, price_raw: float,
                     tokens: float, liquidity: Optional[float],
                     value_ratio: float = 1.0
                     ) -> Tuple[float, float, float, float]:
        """Simulate selling; returns (proceeds, fee, eff_price, impact)."""
        notional_estimate = tokens * price_raw
        impact = simulate_impact_bps(notional_estimate, liquidity, self.sim)
        eff_price = effective_sell_price(
            price_raw, self.sim.base_slippage_bps, impact) * value_ratio
        gross = tokens * eff_price
        fee = gross * self.sim.fee_bps / 10_000.0
        return gross - fee, fee, eff_price, impact

    def _partial_exit(self, runtime: _StrategyRuntime,
                      position: PaperPosition, price_raw: float,
                      ts_epoch: float, tokens: float, reason: str,
                      leg: str = LEG_PARTIAL_SELL) -> None:
        proceeds, fee, eff_price, impact = self._sell_tokens(
            position, price_raw, tokens, position.latest_liquidity)
        avg_cost = position.avg_cost_per_token or 0.0
        pnl_delta = proceeds - tokens * avg_cost
        position.realized_pnl_usd += pnl_delta
        runtime.realized_pnl_usd += pnl_delta
        position.tokens_open -= tokens
        position.refresh_unrealized(price_raw)
        if self.sol_price_usd:
            position.realized_pnl_sol = (
                position.realized_pnl_usd / self.sol_price_usd)
        fill_no = int(position.strategy_state.get("fill_count", 1)) + 1
        position.strategy_state["fill_count"] = fill_no
        fill = PaperFill(
            fill_id=f"{position.paper_trade_id}-F{fill_no:03d}",
            paper_trade_id=position.paper_trade_id,
            strategy_name=runtime.cfg.name,
            run_id=self.run_id,
            mint=position.mint,
            side=SIDE_SELL,
            ts_epoch=ts_epoch,
            price_raw=price_raw,
            price_effective=eff_price,
            tokens=tokens,
            notional_usd=proceeds,
            fee_usd=fee,
            slippage_bps=self.sim.base_slippage_bps,
            impact_bps=impact,
            reason=reason,
            leg=leg,
        )
        self.ledger.append_fill(fill.to_record())
        self._record_position(position)
        self._emit_event({
            "event": "PARTIAL_EXIT",
            "strategy_name": runtime.cfg.name,
            "mint": position.mint,
            "paper_trade_id": position.paper_trade_id,
            "reason": reason,
            "tokens_sold": tokens,
            "proceeds_usd": round(proceeds, 6),
            "realized_pnl_usd": round(position.realized_pnl_usd, 6),
        }, ts_epoch)
        self._equity_point(runtime, ts_epoch)

    def _close_position(self, runtime: _StrategyRuntime,
                        position: PaperPosition,
                        price_raw: Optional[float], ts_epoch: float,
                        status: str, reason: str,
                        liquidity: Optional[float],
                        value_ratio: float = 1.0,
                        leg: Optional[str] = None) -> None:
        if leg is None:
            runner = position.strategy_state.get("runner_status")
            leg = (LEG_RUNNER_CLOSE if runner == "RUNNER_ACTIVE"
                   else LEG_FINAL)
        tokens = position.tokens_open
        eff_price = None
        if price_raw is not None and tokens > 0:
            proceeds, fee, eff_price, impact = self._sell_tokens(
                position, price_raw, tokens, liquidity, value_ratio)
            avg_cost = position.avg_cost_per_token or 0.0
            pnl_delta = proceeds - tokens * avg_cost
            position.realized_pnl_usd += pnl_delta
            runtime.realized_pnl_usd += pnl_delta
            fill_no = int(position.strategy_state.get("fill_count", 1)) + 1
            position.strategy_state["fill_count"] = fill_no
            fill = PaperFill(
                fill_id=f"{position.paper_trade_id}-F{fill_no:03d}",
                paper_trade_id=position.paper_trade_id,
                strategy_name=runtime.cfg.name,
                run_id=self.run_id,
                mint=position.mint,
                side=SIDE_SELL,
                ts_epoch=ts_epoch,
                price_raw=price_raw,
                price_effective=eff_price,
                tokens=tokens,
                notional_usd=proceeds,
                fee_usd=fee,
                slippage_bps=self.sim.base_slippage_bps,
                impact_bps=impact,
                reason=reason,
                leg=leg,
            )
            self.ledger.append_fill(fill.to_record())
        position.tokens_open = 0.0
        position.status = status
        position.reason_closed = reason
        position.closed_at_epoch = ts_epoch
        position.exit_price = price_raw
        position.exit_market_cap = position.latest_market_cap
        if position.cost_basis_usd > 0:
            position.realized_pnl_pct = (
                position.realized_pnl_usd / position.cost_basis_usd * 100.0)
        if self.sol_price_usd:
            position.realized_pnl_sol = (
                position.realized_pnl_usd / self.sol_price_usd)
        position.unrealized_pnl_usd = 0.0
        position.unrealized_pnl_pct = None
        runtime.open_by_mint.pop(position.mint, None)
        runtime.last_closed = (
            f"{position.mint[:8]}.. {status} "
            f"{position.realized_pnl_usd:+,.2f} USD ({reason})")
        self._notify_terminal(runtime, position)
        record = position.to_record()
        self._final_records[position.paper_trade_id] = record
        self.ledger.append_position(record)
        self.ledger.append_closed_position(record)
        self._emit_event({
            "event": "POSITION_CLOSED",
            "strategy_name": runtime.cfg.name,
            "mint": position.mint,
            "paper_trade_id": position.paper_trade_id,
            "status": status,
            "reason": reason,
            "leg": leg,
            "realized_pnl_usd": round(position.realized_pnl_usd, 6),
            "realized_pnl_pct": (round(position.realized_pnl_pct, 4)
                                 if position.realized_pnl_pct is not None
                                 else None),
        }, ts_epoch)
        self._equity_point(runtime, ts_epoch)

    def _notify_terminal(self, runtime: _StrategyRuntime,
                         position: PaperPosition) -> None:
        try:
            runtime.strategy.on_position_terminal(position)
        except Exception as exc:
            self._note_error(
                f"{runtime.cfg.name}.on_position_terminal: {exc}", None)

    def _freeze_rugged(self, runtime: _StrategyRuntime,
                       position: PaperPosition, ts_epoch: float,
                       reason: str) -> None:
        """RUG_ACTION_FREEZE: terminal RUGGED with tokens marked worthless."""
        avg_cost = position.avg_cost_per_token or 0.0
        loss = -(avg_cost * position.tokens_open)
        position.realized_pnl_usd += loss
        runtime.realized_pnl_usd += loss
        position.tokens_open = 0.0
        position.status = STATUS_RUGGED
        position.reason_closed = f"{reason}_FROZEN"
        position.closed_at_epoch = ts_epoch
        position.exit_price = None
        if position.cost_basis_usd > 0:
            position.realized_pnl_pct = (
                position.realized_pnl_usd / position.cost_basis_usd * 100.0)
        if self.sol_price_usd:
            position.realized_pnl_sol = (
                position.realized_pnl_usd / self.sol_price_usd)
        position.unrealized_pnl_usd = 0.0
        position.unrealized_pnl_pct = None
        runtime.open_by_mint.pop(position.mint, None)
        runtime.last_closed = (
            f"{position.mint[:8]}.. RUGGED_FROZEN "
            f"{position.realized_pnl_usd:+,.2f} USD")
        self._notify_terminal(runtime, position)
        record = position.to_record()
        self._final_records[position.paper_trade_id] = record
        self.ledger.append_position(record)
        self.ledger.append_closed_position(record)
        self._emit_event({
            "event": "POSITION_CLOSED",
            "strategy_name": runtime.cfg.name,
            "mint": position.mint,
            "paper_trade_id": position.paper_trade_id,
            "status": STATUS_RUGGED,
            "reason": position.reason_closed,
            "realized_pnl_usd": round(position.realized_pnl_usd, 6),
        }, ts_epoch)
        self._equity_point(runtime, ts_epoch)

    def _close_data_lost(self, runtime: _StrategyRuntime,
                         position: PaperPosition) -> None:
        """No fresh market data for too long: punitive haircut close."""
        price = (position.latest_price
                 if position.latest_price is not None
                 else position.entry_price)
        self._emit_event({
            "event": "DATA_LOST",
            "strategy_name": runtime.cfg.name,
            "mint": position.mint,
            "paper_trade_id": position.paper_trade_id,
            "stale_seconds": self.sim.data_lost_after_seconds,
        }, self.now_epoch)
        self._close_position(
            runtime, position, price, self.now_epoch or 0.0,
            status=STATUS_DATA_LOST,
            reason=(f"DATA_LOST_HAIRCUT_"
                    f"{self.sim.data_lost_value_ratio:.2f}"),
            liquidity=position.latest_liquidity,
            value_ratio=self.sim.data_lost_value_ratio)

    def _note_error(self, message: str,
                    snapshot: Optional[CandidateSnapshot]) -> None:
        self.last_error = message
        self.ledger.append_error({
            "kind": "STRATEGY_ERROR",
            "run_id": self.run_id,
            "ts_utc": utc_iso(self.now_epoch),
            "mint": snapshot.mint if snapshot else None,
            "error": message,
        })

    # ------------------------------------------------------------------
    # Equity curve / heartbeat / console
    # ------------------------------------------------------------------

    def _equity_point(self, runtime: _StrategyRuntime,
                      ts_epoch: Optional[float]) -> None:
        for position in runtime.open_by_mint.values():
            position.refresh_unrealized()
        unrealized = runtime.unrealized_pnl_usd()
        equity = (self.config.run.starting_bankroll_usd
                  + runtime.realized_pnl_usd + unrealized)
        runtime.equity_series.append(equity)
        self.ledger.append_equity_point({
            "ts_utc": utc_iso(ts_epoch if ts_epoch is not None
                              else self.now_epoch),
            "run_id": self.run_id,
            "strategy_name": runtime.cfg.name,
            "realized_pnl_usd": round(runtime.realized_pnl_usd, 6),
            "unrealized_pnl_usd": round(unrealized, 6),
            "equity_usd": round(equity, 6),
            "open_positions": len(runtime.open_by_mint),
        })

    def _maybe_equity_points(self) -> None:
        if self.now_epoch is None:
            return
        bucket = self.config.run.equity_curve_bucket_seconds
        if bucket <= 0:
            return
        if self._next_equity_epoch is None:
            self._next_equity_epoch = self.now_epoch + bucket
            return
        if self.now_epoch >= self._next_equity_epoch:
            for runtime in self.runtimes:
                self._equity_point(runtime, self.now_epoch)
            while self._next_equity_epoch <= self.now_epoch:
                self._next_equity_epoch += bucket

    def _maybe_heartbeat(self) -> None:
        if self.now_epoch is None:
            return
        interval = self.config.run.heartbeat_every_seconds
        if interval <= 0:
            return
        if self._next_heartbeat_epoch is None:
            self._next_heartbeat_epoch = self.now_epoch + interval
            return
        if self.now_epoch < self._next_heartbeat_epoch:
            return
        while self._next_heartbeat_epoch <= self.now_epoch:
            self._next_heartbeat_epoch += interval
        self.heartbeat()

    def _heartbeat_stamp_utc(self) -> Optional[str]:
        """Wall-clock stamp in live mode; event time in replay."""
        if self.wall_clock is not None:
            return utc_iso(self.wall_clock())
        return utc_iso(self.now_epoch)

    def heartbeat(self) -> None:
        """Refresh monitor artifacts and (unless quiet) print the console
        summary Bala watches."""
        self._emit_event({"event": "HEARTBEAT",
                          "snapshots_processed": self.snapshots_processed},
                         self.now_epoch)
        self._write_monitor_snapshots()
        if not self.quiet:
            self.echo(self.console_summary())

    def _best_worst_open(self):
        best = worst = None
        for runtime in self.runtimes:
            for position in runtime.open_by_mint.values():
                pct = position.unrealized_pnl_pct
                if pct is None:
                    continue
                if best is None or pct > (best[1].unrealized_pnl_pct
                                          or float("-inf")):
                    best = (runtime.cfg.name, position)
                if worst is None or pct < (worst[1].unrealized_pnl_pct
                                           or float("inf")):
                    worst = (runtime.cfg.name, position)
        return best, worst

    def write_monitor_artifacts(self) -> None:
        """Public alias: refresh the monitor/heartbeat artifacts silently."""
        self._write_monitor_snapshots()

    def _write_monitor_snapshots(self) -> None:
        open_positions = []
        for runtime in self.runtimes:
            for position in runtime.open_by_mint.values():
                position.refresh_unrealized()
                open_positions.append(position.to_record())
        open_positions.sort(key=lambda r: (r["strategy_name"],
                                           r["paper_trade_id"]))
        self.ledger.write_json_atomic(OPEN_POSITIONS_FILE, {
            "run_id": self.run_id,
            "as_of_utc": utc_iso(self.now_epoch),
            "open_positions": open_positions,
        })
        self.ledger.write_recent_events(list(self.recent_events))

        heartbeat_utc = self._heartbeat_stamp_utc()
        self.ledger.write_json_atomic(HEARTBEAT_FILE, {
            "artifact": "heartbeat",
            "run_id": self.run_id,
            "mode": self.mode,
            "heartbeat_utc": heartbeat_utc,
            "last_event_utc": utc_iso(self.now_epoch),
            "snapshots_processed": self.snapshots_processed,
            "open_positions_total": len(open_positions),
            "watch_inputs": list(self.watch_inputs),
            "uptime_seconds": (round(self.wall_clock()
                                     - self._started_wall, 3)
                               if self.wall_clock is not None
                               and self._started_wall is not None else None),
        })

        best, worst = self._best_worst_open()

        def _brief(entry) -> Optional[Dict[str, Any]]:
            if entry is None:
                return None
            name, position = entry
            return {
                "strategy_name": name,
                "mint": position.mint,
                "unrealized_pnl_pct": position.unrealized_pnl_pct,
                "unrealized_pnl_usd": round(position.unrealized_pnl_usd, 6),
            }

        per_strategy = {}
        for runtime in self.runtimes:
            closed = sum(
                1 for r in self._final_records.values()
                if r.get("strategy_name") == runtime.cfg.name
                and r.get("status") not in (STATUS_OPEN,)
                and not str(r.get("status", "")).startswith("SKIPPED"))
            try:
                machine = runtime.strategy.monitor_snapshot()
            except Exception:
                machine = {}
            per_strategy[runtime.cfg.name] = {
                "open_positions": len(runtime.open_by_mint),
                "unrealized_pnl_usd": round(runtime.unrealized_pnl_usd(), 6),
                "realized_pnl_usd": round(runtime.realized_pnl_usd, 6),
                "closed_trades": closed,
                "last_opened": runtime.last_opened,
                "last_closed": runtime.last_closed,
                "last_dca": runtime.last_dca,
                "machine": machine,
            }
        self.ledger.write_json_atomic(LIVE_MONITOR_FILE, {
            "artifact": "live_monitor",
            "run_id": self.run_id,
            "mode": self.mode,
            "heartbeat_utc": heartbeat_utc,
            "as_of_utc": utc_iso(self.now_epoch),
            "watch_inputs": list(self.watch_inputs),
            "snapshots_processed": self.snapshots_processed,
            "last_record": (self.last_snapshot.to_record()
                            if self.last_snapshot is not None else None),
            "strategies": per_strategy,
            "best_open": _brief(best),
            "worst_open": _brief(worst),
            "last_skip": self.last_skip,
            "last_error": self.last_error,
        })

    def console_summary(self) -> str:
        """The watchable console block."""
        lines: List[str] = []
        stamp = self._heartbeat_stamp_utc()
        live_note = " ACTIVE" if self.mode == MODE_LIVE_PAPER else ""
        lines.append(
            f"[paper {self.mode}{live_note}] heartbeat {stamp} | "
            f"event-time {utc_iso(self.now_epoch)} | "
            f"snapshots={self.snapshots_processed} | run={self.run_id}")
        if self.watch_inputs:
            lines.append("  watching  : " + "; ".join(self.watch_inputs))
        last = self.last_snapshot
        if last is not None:
            lines.append(
                f"  last candidate: {last.mint[:12]}.. "
                f"price={last.price_usd if last.price_usd is not None else 'n/a'} "
                f"mc={last.market_cap_usd if last.market_cap_usd is not None else 'n/a'}")
        for runtime in self.runtimes:
            unrealized = runtime.unrealized_pnl_usd()
            closed = sum(1 for r in self._final_records.values()
                         if r.get("strategy_name") == runtime.cfg.name
                         and r.get("status") not in (STATUS_OPEN,)
                         and not str(r.get("status", "")).startswith("SKIPPED"))
            lines.append(
                f"  {runtime.cfg.name:<24} open={len(runtime.open_by_mint):>3} "
                f"unreal={unrealized:+10.2f} USD "
                f"realized={runtime.realized_pnl_usd:+10.2f} USD closed={closed}")
            if runtime.last_opened:
                lines.append(f"      last open : {runtime.last_opened}")
            if runtime.last_dca:
                lines.append(f"      last DCA  : {runtime.last_dca}")
            if runtime.last_closed:
                lines.append(f"      last close: {runtime.last_closed}")
            try:
                machine = runtime.strategy.monitor_snapshot()
            except Exception:
                machine = {}
            counts = machine.get("machine_counts")
            if counts:
                rendered = " ".join(f"{state}={count}"
                                    for state, count in counts.items())
                lines.append(f"      machine   : {rendered}")
        best, worst = self._best_worst_open()
        if best is not None:
            lines.append(
                f"  best open : {best[0]} {best[1].mint[:8]}.. "
                f"{best[1].unrealized_pnl_pct:+.1f}%")
        if worst is not None:
            lines.append(
                f"  worst open: {worst[0]} {worst[1].mint[:8]}.. "
                f"{worst[1].unrealized_pnl_pct:+.1f}%")
        lines.append(f"  last skip : {self.last_skip or 'none'}")
        lines.append(f"  last error: {self.last_error or 'none'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Finalization / summary artifacts
    # ------------------------------------------------------------------

    def record_input_errors(self, errors: Iterable[Dict[str, Any]]) -> None:
        for error in errors:
            record = dict(error)
            record["run_id"] = self.run_id
            self.ledger.append_error(record)
            self.last_error = record.get("error", self.last_error)

    def finalize(self) -> Dict[str, Any]:
        """End of stream: settle positions per policy, write all artifacts."""
        if self.config.run.end_of_stream_policy == END_OF_STREAM_CLOSE:
            for runtime in self.runtimes:
                for position in list(runtime.open_by_mint.values()):
                    price = (position.latest_price
                             if position.latest_price is not None
                             else position.entry_price)
                    close_ts = (self.now_epoch
                                if self.now_epoch is not None
                                else (position.opened_at_epoch
                                      if position.opened_at_epoch is not None
                                      else 0.0))
                    self._close_position(
                        runtime, position, price, close_ts,
                        status=STATUS_CLOSED, reason="END_OF_STREAM",
                        liquidity=position.latest_liquidity)
        else:
            for runtime in self.runtimes:
                for position in runtime.open_by_mint.values():
                    position.refresh_unrealized()
                    self._record_position(position)
        for runtime in self.runtimes:
            self._equity_point(runtime, self.now_epoch)
        summary = self.write_summary_artifacts()
        self._write_monitor_snapshots()
        if not self.quiet:
            self.echo(self.console_summary())
        return summary

    def write_summary_artifacts(self) -> Dict[str, Any]:
        records_by_strategy: Dict[str, List[Dict[str, Any]]] = {
            rt.cfg.name: [] for rt in self.runtimes}
        for record in self._final_records.values():
            name = record.get("strategy_name")
            if name in records_by_strategy:
                records_by_strategy[name].append(record)
        for records in records_by_strategy.values():
            records.sort(key=lambda r: r.get("paper_trade_id", ""))
        equity_by_strategy = {rt.cfg.name: rt.equity_series
                              for rt in self.runtimes}
        summary = build_run_summary(
            run_id=self.run_id,
            config_digest=self.config.config_digest(),
            records_by_strategy=records_by_strategy,
            equity_by_strategy=equity_by_strategy,
            starting_bankroll_usd=self.config.run.starting_bankroll_usd,
            sol_price_usd=self.sol_price_usd,
            as_of_utc=utc_iso(self.now_epoch),
            mode=self.mode,
        )
        comparison = build_comparison(self.run_id, summary["strategies"],
                                      utc_iso(self.now_epoch))
        self.ledger.write_json_atomic(SUMMARY_FILE, summary)
        self.ledger.write_json_atomic(COMPARISON_JSON_FILE, comparison)
        self.ledger.write_text_atomic(COMPARISON_MD_FILE,
                                      comparison_markdown(comparison))
        return summary

    def close(self) -> None:
        self.ledger.close()


def run_replay(config: PaperConfig,
               snapshots: List[CandidateSnapshot],
               input_errors: Optional[List[Dict[str, Any]]] = None,
               run_dir: Optional[str] = None,
               quiet: bool = False,
               echo: Callable[[str], None] = print,
               overwrite_run: bool = False) -> Dict[str, Any]:
    """Run a full replay and return the summary.

    Fails closed (:class:`ReplayRunDirError`) when the target run directory
    already contains paper artifacts: appending a second replay would
    duplicate ledger rows and break byte-reproducibility. Pass
    ``overwrite_run=True`` (CLI: ``--overwrite-run``) to reset the known
    artifact files in that one directory and re-run fresh. Live mode is
    unaffected -- it constructs the engine directly and stays append/resume.
    """
    target_dir = run_dir or str(
        Path(config.run.output_root) / resolve_run_id(config, MODE_REPLAY))
    if run_dir_has_artifacts(target_dir):
        if overwrite_run:
            reset_run_dir(target_dir)
        else:
            raise ReplayRunDirError(
                f"replay run dir already contains paper artifacts: "
                f"{target_dir}. Re-running would append duplicate ledger "
                f"rows. Use --overwrite-run to reset this run directory, "
                f"or pick a new --run-id.")
    engine = PaperTradingEngine(config, run_dir=run_dir, mode=MODE_REPLAY,
                                quiet=quiet, echo=echo)
    try:
        if input_errors:
            engine.record_input_errors(input_errors)
        limit = config.run.max_snapshots
        for index, snapshot in enumerate(snapshots):
            if limit is not None and index >= limit:
                break
            engine.process_snapshot(snapshot)
        summary = engine.finalize()
    finally:
        engine.close()
    return summary


__all__ = [
    "MODE_REPLAY",
    "MODE_LIVE_PAPER",
    "ReplayRunDirError",
    "resolve_run_id",
    "PaperTradingEngine",
    "run_replay",
]
