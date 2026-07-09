"""BALA_PLAN: Bala's active Tier/DCA state machine.

Not a one-entry/one-exit rule: each mint moves through an explicit state
machine driven by the PHX2 tier-dip observations that arrive over time.

    DISCOVERED -> AUDIT_TIER_1 -> WATCHING -> PAPER_SCOUT_OPEN
        -> PAPER_DCA_1_OPEN -> PAPER_DCA_2_OPEN -> POSITION_ACTIVE
        -> INITIALS_RECOVERED -> RUNNER_ACTIVE
        -> CLOSED / SKIPPED / DATA_LOST / RUGGED

Tier semantics (dip bands are config, defaults Tier 1 50-60%, Tier 2
62-80%, Tier 3 82-95% drawdown from the anchored ATH):

* Tier 1 = audit/watch zone. Run the audit over the available fields
  (liquidity, market cap, volume, age from migration evidence, prior
  ATH/drawdown). Never a full-size paper buy; optionally a tiny scout
  (``enable_scout_entry`` + ``scout_entry_pct_of_max_position``),
  otherwise mark WATCHING and wait.
* Tier 2 = first meaningful DCA (DCA_1), sized as
  ``dca_1_pct_of_max_position`` of the sizing profile's capped max for the
  mint's market-cap band. Only if the audit is (still) valid.
* Tier 3 = second DCA (DCA_2) only while the coin is still healthy: audit
  re-passes, liquidity has not collapsed, data is fresh, exposure caps and
  the DCA time gate hold. Never averages down into obvious death.

After entries the engine manages TP/SL/trailing/max-hold/rug/data-lost
from the exit plan; this strategy adds the optional 3x initials recovery
(sell back the initial cost, ride the runner with a trailing stop) and the
high-quality 5x trim path.

Per-mint machine state lives in ``self._tracks`` (recomputable from the
stream); position-bound state (``bala_state``, ``dca_count``, ...) lives
in ``position.strategy_state`` so it persists in the ledger and survives a
live-mode restart.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PHX2.paper_trading.config import STRATEGY_BALA_PLAN
from PHX2.paper_trading.models import (
    CandidateSnapshot,
    ExitPlan,
    LEG_DCA_1,
    LEG_DCA_2,
    LEG_INITIALS_RECOVERY,
    LEG_SCOUT,
    PaperPosition,
    STATUS_DATA_LOST,
    STATUS_RUGGED,
    SKIP_STATUSES,
)
from PHX2.paper_trading.strategy import (
    AddIntent,
    EXIT_PARTIAL,
    EntryIntent,
    ExitIntent,
    PaperStrategy,
    StrategyContext,
)

# Machine states
STATE_DISCOVERED = "DISCOVERED"
STATE_AUDIT_TIER_1 = "AUDIT_TIER_1"
STATE_WATCHING = "WATCHING"
STATE_PAPER_SCOUT_OPEN = "PAPER_SCOUT_OPEN"
STATE_PAPER_DCA_1_OPEN = "PAPER_DCA_1_OPEN"
STATE_PAPER_DCA_2_OPEN = "PAPER_DCA_2_OPEN"
STATE_POSITION_ACTIVE = "POSITION_ACTIVE"
STATE_INITIALS_RECOVERED = "INITIALS_RECOVERED"
STATE_RUNNER_ACTIVE = "RUNNER_ACTIVE"
STATE_CLOSED = "CLOSED"
STATE_SKIPPED = "SKIPPED"
STATE_DATA_LOST = "DATA_LOST"
STATE_RUGGED = "RUGGED"

BALA_STATES = (
    STATE_DISCOVERED, STATE_AUDIT_TIER_1, STATE_WATCHING,
    STATE_PAPER_SCOUT_OPEN, STATE_PAPER_DCA_1_OPEN, STATE_PAPER_DCA_2_OPEN,
    STATE_POSITION_ACTIVE, STATE_INITIALS_RECOVERED, STATE_RUNNER_ACTIVE,
    STATE_CLOSED, STATE_SKIPPED, STATE_DATA_LOST, STATE_RUGGED,
)

_EPS = 1e-9


class _MintTrack:
    """Pre-position per-mint machine state (recomputable from the stream)."""

    __slots__ = ("state", "first_seen_epoch", "audit_ok", "audit_reasons",
                 "audit_ts_epoch", "note")

    def __init__(self, first_seen_epoch: float) -> None:
        self.state: str = STATE_DISCOVERED
        self.first_seen_epoch: float = first_seen_epoch
        self.audit_ok: Optional[bool] = None
        self.audit_reasons: List[str] = []
        self.audit_ts_epoch: Optional[float] = None
        self.note: str = ""


class BalaPlanStrategy(PaperStrategy):
    strategy_type = STRATEGY_BALA_PLAN

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        self._tracks: Dict[str, _MintTrack] = {}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_params(self) -> None:
        bands = self.params.get("tier_dip_bands")
        if not isinstance(bands, dict) or not bands:
            raise ValueError(
                f"strategy '{self.name}': tier_dip_bands must be a non-empty "
                "object of tier -> [low_pct, high_pct]")
        for tier, band in bands.items():
            if (not isinstance(band, (list, tuple)) or len(band) != 2
                    or self._num(band[0]) is None
                    or self._num(band[1]) is None
                    or float(band[0]) >= float(band[1])):
                raise ValueError(
                    f"strategy '{self.name}': tier_dip_bands[{tier!r}] must "
                    "be [low_pct, high_pct] with low < high")
        sl = self._num(self.params.get("stop_loss_pct"))
        if sl is not None and sl >= 0:
            raise ValueError(
                f"strategy '{self.name}': stop_loss_pct must be negative")
        for key in ("scout_entry_pct_of_max_position",
                    "dca_1_pct_of_max_position",
                    "dca_2_pct_of_max_position"):
            value = self._num(self.params.get(key))
            if value is None or not (0.0 < value <= 1.0):
                raise ValueError(
                    f"strategy '{self.name}': {key} must be in (0, 1]")
        max_dca = self.params.get("max_dca_count")
        if not isinstance(max_dca, int) or max_dca < 0:
            raise ValueError(
                f"strategy '{self.name}': max_dca_count must be an int >= 0")
        audit = self.params.get("audit")
        if not isinstance(audit, dict):
            raise ValueError(
                f"strategy '{self.name}': audit must be an object")
        mult = self._num(self.params.get("initials_recovery_multiple"))
        if mult is not None and mult <= 1.0:
            raise ValueError(
                f"strategy '{self.name}': initials_recovery_multiple must "
                "be > 1")

    # ------------------------------------------------------------------
    # Tier / dip resolution
    # ------------------------------------------------------------------

    def _bands(self) -> Dict[int, Tuple[float, float]]:
        return {
            int(tier): (float(band[0]), float(band[1]))
            for tier, band in self.params["tier_dip_bands"].items()
        }

    def _resolve_drawdown(self, snapshot: CandidateSnapshot) -> Optional[float]:
        if snapshot.drawdown_pct is not None:
            return float(snapshot.drawdown_pct)
        if (snapshot.ath_market_cap_usd and snapshot.market_cap_usd
                and snapshot.ath_market_cap_usd > 0):
            return (1.0 - snapshot.market_cap_usd
                    / snapshot.ath_market_cap_usd) * 100.0
        return None

    def _resolve_tier(self, snapshot: CandidateSnapshot,
                      drawdown_pct: Optional[float]) -> Optional[int]:
        if snapshot.tier is not None:
            return int(snapshot.tier)
        if self.params.get("derive_tier_from_drawdown") and \
                drawdown_pct is not None:
            for tier, (low, high) in sorted(self._bands().items()):
                if low <= drawdown_pct <= high:
                    return tier
        return None

    def _in_band(self, tier: Optional[int],
                 drawdown_pct: Optional[float]) -> bool:
        if tier is None or drawdown_pct is None:
            return False
        band = self._bands().get(tier)
        return band is not None and band[0] <= drawdown_pct <= band[1]

    def _is_high_quality(self, snapshot: CandidateSnapshot,
                         tier: Optional[int]) -> bool:
        min_score = self._num(self.params.get("high_quality_min_score"))
        if (min_score is not None and snapshot.score is not None
                and snapshot.score >= min_score):
            return True
        hq_tiers = self.params.get("high_quality_tiers") or []
        return tier is not None and int(tier) in [int(t) for t in hq_tiers]

    # ------------------------------------------------------------------
    # Tier 1 audit
    # ------------------------------------------------------------------

    def run_audit(self, snapshot: CandidateSnapshot,
                  ctx: StrategyContext) -> Tuple[bool, List[str]]:
        """Audit over the available fields; a configured rule with missing
        data fails closed. Returns (passed, fail_reasons)."""
        rules = self.params.get("audit") or {}
        failures: List[str] = []

        def _rule(name: str) -> Optional[float]:
            return self._num(rules.get(name))

        min_lp = _rule("min_liquidity_usd")
        if min_lp is not None and (snapshot.liquidity_usd is None
                                   or snapshot.liquidity_usd < min_lp):
            failures.append("AUDIT_LIQUIDITY_LOW")
        min_mc = _rule("min_market_cap_usd")
        if min_mc is not None and (snapshot.market_cap_usd is None
                                   or snapshot.market_cap_usd < min_mc):
            failures.append("AUDIT_MC_LOW")
        max_mc = _rule("max_market_cap_usd")
        if max_mc is not None and (snapshot.market_cap_usd is None
                                   or snapshot.market_cap_usd > max_mc):
            failures.append("AUDIT_MC_HIGH")
        min_vol = _rule("min_volume_usd")
        if min_vol is not None and (snapshot.volume_usd is None
                                    or snapshot.volume_usd < min_vol):
            failures.append("AUDIT_VOLUME_LOW")
        min_age = _rule("min_age_seconds")
        max_age = _rule("max_age_seconds")
        if min_age is not None or max_age is not None:
            if snapshot.migration_ts_epoch is None:
                failures.append("AUDIT_AGE_UNKNOWN")
            else:
                age = ctx.now_epoch - snapshot.migration_ts_epoch
                if min_age is not None and age < min_age:
                    failures.append("AUDIT_TOO_YOUNG")
                if max_age is not None and age > max_age:
                    failures.append("AUDIT_TOO_OLD")
        max_dd = _rule("max_drawdown_pct")
        if max_dd is not None:
            drawdown = self._resolve_drawdown(snapshot)
            if drawdown is None or drawdown > max_dd:
                failures.append("AUDIT_DRAWDOWN_TERMINAL")
        min_ath = _rule("min_ath_market_cap_usd")
        if min_ath is not None and (snapshot.ath_market_cap_usd is None
                                    or snapshot.ath_market_cap_usd < min_ath):
            failures.append("AUDIT_ATH_TOO_SMALL")
        if rules.get("require_migration_evidence") and \
                snapshot.migration_ts_epoch is None:
            failures.append("AUDIT_NO_MIGRATION_EVIDENCE")
        return (not failures, failures)

    def _ensure_audit(self, track: _MintTrack, snapshot: CandidateSnapshot,
                      ctx: StrategyContext, force: bool = False) -> bool:
        ttl = self._num((self.params.get("audit") or {})
                        .get("audit_ttl_seconds")) or 0.0
        fresh = (track.audit_ts_epoch is not None
                 and ctx.now_epoch - track.audit_ts_epoch <= ttl)
        if force or not fresh or track.audit_ok is None:
            ok, reasons = self.run_audit(snapshot, ctx)
            track.audit_ok = ok
            track.audit_reasons = reasons
            track.audit_ts_epoch = ctx.now_epoch
        return bool(track.audit_ok)

    # ------------------------------------------------------------------
    # Machine helpers
    # ------------------------------------------------------------------

    def _track_for(self, mint: str, now_epoch: float) -> _MintTrack:
        track = self._tracks.get(mint)
        if track is None:
            track = _MintTrack(now_epoch)
            self._tracks[mint] = track
        return track

    def _max_position_usd(self, snapshot: CandidateSnapshot,
                          ctx: StrategyContext) -> Optional[float]:
        """Max safe total position for this mint right now: the sizing
        profile's capped size, further capped by max_total_position_usd."""
        preview = ctx.sizing_preview(snapshot)
        profile_max = None
        if preview is not None and not preview.is_skip:
            profile_max = float(preview.final_size_usd)
        config_max = self._num(self.params.get("max_total_position_usd"))
        if profile_max is None:
            return config_max
        if config_max is None:
            return profile_max
        return min(profile_max, config_max)

    def _build_plan(self, high_quality: bool) -> ExitPlan:
        if high_quality:
            return ExitPlan(
                take_profit_pct=None,
                stop_loss_pct=self._num(self.params.get("stop_loss_pct")),
                trailing_stop_pct=None,  # trailing starts after the 5x trim
                max_hold_seconds=self._num(
                    self.params.get("max_hold_seconds")),
                hold_to_multiple=self._num(
                    self.params.get("high_quality_hold_multiple")),
                trim_fraction=self._num(
                    self.params.get("high_quality_trim_fraction")),
            )
        take_profit = self._num(self.params.get("take_profit_pct"))
        if self._num(self.params.get("initials_recovery_multiple")) is not None:
            # The 3x recovery leg is the profit event; no flat TP before it.
            take_profit = None
        return ExitPlan(
            take_profit_pct=take_profit,
            stop_loss_pct=self._num(self.params.get("stop_loss_pct")),
            trailing_stop_pct=self._num(self.params.get("trailing_stop_pct")),
            max_hold_seconds=self._num(self.params.get("max_hold_seconds")),
        )

    # ------------------------------------------------------------------
    # Entry: DISCOVERED / AUDIT_TIER_1 / WATCHING / first buy leg
    # ------------------------------------------------------------------

    def wants_entry(self, snapshot: CandidateSnapshot,
                    ctx: StrategyContext) -> Optional[EntryIntent]:
        track = self._track_for(snapshot.mint, ctx.now_epoch)
        if track.state in (STATE_CLOSED, STATE_SKIPPED, STATE_DATA_LOST,
                           STATE_RUGGED):
            return None
        if not snapshot.has_price:
            return None
        if not self.passes_entry_filters(snapshot, check_tiers=False):
            return None
        drawdown = self._resolve_drawdown(snapshot)
        tier = self._resolve_tier(snapshot, drawdown)
        if tier is None:
            return None  # a dip moment needs a tier (real or derived)
        allowed = [int(t) for t in self.params.get("allowed_tiers") or []]
        if allowed and tier not in allowed:
            return None
        if not self._in_band(tier, drawdown):
            return None

        # A tier-dip moment: audit gates everything.
        if tier == 1:
            track.state = STATE_AUDIT_TIER_1
        audit_ok = self._ensure_audit(track, snapshot, ctx)
        if not audit_ok:
            track.note = ",".join(track.audit_reasons)
            return None

        high_quality = self._is_high_quality(snapshot, tier)
        plan = self._build_plan(high_quality)
        hq_suffix = "_HQ" if high_quality else ""
        max_total = self._num(self.params.get("max_total_position_usd"))

        if tier == 1:
            if not self.params.get("enable_scout_entry"):
                track.state = STATE_WATCHING
                track.note = "TIER1_WATCHING_FOR_T2_T3"
                return None
            # State flips to PAPER_SCOUT_OPEN via on_position_opened once
            # the engine actually fills the scout (sizing may shrink or
            # skip it, in which case we stay WATCHING).
            track.state = STATE_WATCHING
            return EntryIntent(
                reason=f"BALA_T1_SCOUT_DIP_{drawdown:.1f}PCT{hq_suffix}",
                plan=plan,
                leg=LEG_SCOUT,
                size_fraction=float(
                    self.params["scout_entry_pct_of_max_position"]),
                max_total_usd=max_total,
                state_seed={
                    "bala_state": STATE_PAPER_SCOUT_OPEN,
                    "dca_count": 0,
                    "last_dca_ts_epoch": ctx.now_epoch,
                    "hq": high_quality,
                },
            )

        if tier == 3 and not self.params.get("allow_tier3_initial_entry",
                                             True):
            track.state = STATE_WATCHING
            track.note = "TIER3_SEEN_NO_INITIAL_ENTRY"
            return None

        # Tier 2 (or allowed tier 3 first sight): first meaningful DCA.
        # Track state syncs via on_position_opened when the fill lands.
        return EntryIntent(
            reason=f"BALA_T{tier}_DCA1_DIP_{drawdown:.1f}PCT{hq_suffix}",
            plan=plan,
            leg=LEG_DCA_1,
            size_fraction=float(self.params["dca_1_pct_of_max_position"]),
            max_total_usd=max_total,
            state_seed={
                "bala_state": STATE_PAPER_DCA_1_OPEN,
                "dca_count": 1,
                "last_dca_ts_epoch": ctx.now_epoch,
                "hq": high_quality,
            },
        )

    # ------------------------------------------------------------------
    # Open-position management: DCA ladder + recovery/trim
    # ------------------------------------------------------------------

    def manage(self, position: PaperPosition, snapshot: CandidateSnapshot,
               ctx: StrategyContext) -> List[Any]:
        state = position.strategy_state
        state.setdefault("bala_state", STATE_POSITION_ACTIVE)
        state.setdefault("dca_count", 0)

        # Settle transient states.
        if state["bala_state"] == STATE_INITIALS_RECOVERED:
            state["bala_state"] = STATE_RUNNER_ACTIVE
        elif (state["bala_state"] in (STATE_PAPER_DCA_1_OPEN,
                                      STATE_PAPER_DCA_2_OPEN,
                                      STATE_PAPER_SCOUT_OPEN)
              and int(state.get("dca_count", 0))
              >= int(self.params.get("max_dca_count", 0))):
            state["bala_state"] = STATE_POSITION_ACTIVE
        # Keep the per-mint track in sync for the live monitor.
        track = self._tracks.get(position.mint)
        if track is not None:
            track.state = state["bala_state"]

        if not snapshot.has_price or not position.entry_price:
            return []
        intents: List[Any] = []
        intents.extend(self._maybe_dca(position, snapshot, ctx))
        intents.extend(self._maybe_initials_recovery(position, snapshot, ctx))
        intents.extend(self._maybe_hq_trim(position, snapshot, ctx))
        return intents

    def _dca_skip(self, position: PaperPosition, reason: str) -> List[Any]:
        position.strategy_state["last_dca_skip"] = reason
        return []

    def _maybe_dca(self, position: PaperPosition,
                   snapshot: CandidateSnapshot,
                   ctx: StrategyContext) -> List[Any]:
        params = self.params
        state = position.strategy_state
        dca_count = int(state.get("dca_count", 0))
        if dca_count >= int(params.get("max_dca_count", 0)):
            return []
        if state.get("initial_recovered") or state.get("trimmed"):
            return []  # never DCA after the profit machinery fired

        drawdown = self._resolve_drawdown(snapshot)
        tier = self._resolve_tier(snapshot, drawdown)
        if tier is None or not self._in_band(tier, drawdown):
            return []
        allowed = [int(t) for t in params.get("allowed_tiers") or []]
        if allowed and tier not in allowed:
            return []

        # Ladder rung: DCA_1 needs tier >= 2; DCA_2 needs tier 3.
        if not position.has_leg(LEG_DCA_1):
            if tier < 2:
                return []
            leg = LEG_DCA_1
            leg_pct = float(params["dca_1_pct_of_max_position"])
            next_state = STATE_PAPER_DCA_1_OPEN
        else:
            if tier != 3 or position.has_leg(LEG_DCA_2):
                return []
            leg = LEG_DCA_2
            leg_pct = float(params["dca_2_pct_of_max_position"])
            next_state = STATE_PAPER_DCA_2_OPEN

        # --- Health gates: do not average down into obvious death. ---
        min_gap = self._num(params.get("min_time_between_dca_seconds"))
        last_dca_ts = self._num(state.get("last_dca_ts_epoch"))
        if (min_gap is not None and last_dca_ts is not None
                and ctx.now_epoch - last_dca_ts < min_gap):
            return self._dca_skip(position, "DCA_TIME_GATE")

        if params.get("require_reaudit_before_dca", True):
            track = self._track_for(position.mint, ctx.now_epoch)
            if not self._ensure_audit(track, snapshot, ctx, force=True):
                return self._dca_skip(
                    position, "REAUDIT_FAILED:" + ",".join(
                        track.audit_reasons))

        lp_down_max = self._num(
            params.get("do_not_dca_if_liquidity_down_pct_exceeds"))
        if lp_down_max is not None and position.entry_liquidity:
            lp_now = (snapshot.liquidity_usd
                      if snapshot.liquidity_usd is not None
                      else position.latest_liquidity)
            if lp_now is None:
                return self._dca_skip(position, "DCA_LIQUIDITY_UNKNOWN")
            down_pct = (1.0 - lp_now / position.entry_liquidity) * 100.0
            if down_pct > lp_down_max:
                return self._dca_skip(position, "DCA_LIQUIDITY_DOWN")

        if params.get("do_not_dca_if_volume_dead") and \
                (snapshot.volume_usd is None or snapshot.volume_usd <= 0):
            return self._dca_skip(position, "DCA_VOLUME_DEAD")

        stale_max = self._num(
            params.get("do_not_dca_if_price_data_stale_seconds"))
        if (stale_max is not None
                and position.last_price_gap_seconds is not None
                and position.last_price_gap_seconds > stale_max):
            return self._dca_skip(position, "DCA_PRICE_DATA_WAS_STALE")

        mc_floor = self._num(
            params.get("do_not_dca_if_market_cap_below_usd"))
        if mc_floor is not None:
            if snapshot.market_cap_usd is None:
                return self._dca_skip(position, "DCA_MC_UNKNOWN")
            if snapshot.market_cap_usd < mc_floor:
                return self._dca_skip(position, "DCA_MC_BELOW_FLOOR")

        max_total_usd = self._num(params.get("max_total_position_usd"))
        max_total_tokens = self._num(params.get("max_total_tokens"))
        if max_total_usd is not None and \
                position.virtual_usd_size >= max_total_usd - _EPS:
            return self._dca_skip(position, "DCA_MAX_EXPOSURE_USD")
        if max_total_tokens is not None and \
                position.estimated_tokens_received >= max_total_tokens - _EPS:
            return self._dca_skip(position, "DCA_MAX_EXPOSURE_TOKENS")

        max_position = self._max_position_usd(snapshot, ctx)
        if max_position is None or max_position <= 0:
            return self._dca_skip(position, "DCA_SIZING_UNAVAILABLE")
        budget = max_position * leg_pct
        if max_total_usd is not None:
            budget = min(budget,
                         max_total_usd - position.virtual_usd_size)
        if budget <= 0:
            return self._dca_skip(position, "DCA_BUDGET_EXHAUSTED")

        state["last_dca_skip"] = None
        return [AddIntent(
            leg=leg,
            size_usd=budget,
            reason=f"BALA_T{tier}_{leg}_DIP_{drawdown:.1f}PCT",
            max_total_usd=max_total_usd,
            max_total_tokens=max_total_tokens,
            state_seed={
                "bala_state": next_state,
                "dca_count": dca_count + 1,
                "last_dca_ts_epoch": ctx.now_epoch,
            },
        )]

    def _maybe_initials_recovery(self, position: PaperPosition,
                                 snapshot: CandidateSnapshot,
                                 ctx: StrategyContext) -> List[Any]:
        mult = self._num(self.params.get("initials_recovery_multiple"))
        if mult is None or position.strategy_state.get("initial_recovered"):
            return []
        multiple = snapshot.price_usd / position.entry_price
        if multiple < mult * (1.0 - _EPS):
            return []
        state = position.strategy_state
        state["initial_recovered"] = True
        state["recovered_at_multiple"] = round(multiple, 4)
        state["initial_cost_usd"] = round(position.cost_basis_usd, 6)
        state["bala_state"] = STATE_INITIALS_RECOVERED
        state["runner_status"] = STATE_RUNNER_ACTIVE
        position.plan.trailing_stop_pct = self._num(
            self.params.get("runner_trailing_stop_pct"))
        position.post_trim_peak_price = snapshot.price_usd
        return [ExitIntent(
            kind=EXIT_PARTIAL,
            recover_usd=position.cost_basis_usd,
            leg=LEG_INITIALS_RECOVERY,
            reason=f"BALA_INITIALS_RECOVERED_AT_{mult:g}X",
        )]

    def _maybe_hq_trim(self, position: PaperPosition,
                       snapshot: CandidateSnapshot,
                       ctx: StrategyContext) -> List[Any]:
        plan = position.plan
        if (plan.hold_to_multiple is None or plan.trim_fraction is None
                or position.strategy_state.get("trimmed")):
            return []
        multiple = snapshot.price_usd / position.entry_price
        if multiple < float(plan.hold_to_multiple) * (1.0 - _EPS):
            return []
        state = position.strategy_state
        state["trimmed"] = True
        state["trimmed_at_multiple"] = round(multiple, 4)
        state["bala_state"] = STATE_RUNNER_ACTIVE
        state["runner_status"] = STATE_RUNNER_ACTIVE
        plan.trailing_stop_pct = self._num(
            self.params.get("high_quality_trailing_stop_pct"))
        position.post_trim_peak_price = snapshot.price_usd
        return [ExitIntent(
            kind=EXIT_PARTIAL,
            fraction=float(plan.trim_fraction),
            reason=f"HQ_TRIM_AT_{plan.hold_to_multiple:g}X",
        )]

    # ------------------------------------------------------------------
    # Terminal sync + monitor
    # ------------------------------------------------------------------

    _TERMINAL_STATE_BY_STATUS = {
        STATUS_RUGGED: STATE_RUGGED,
        STATUS_DATA_LOST: STATE_DATA_LOST,
    }

    def on_position_opened(self, position: PaperPosition) -> None:
        track = self._track_for(position.mint,
                                position.opened_at_epoch or 0.0)
        track.state = position.strategy_state.get(
            "bala_state", STATE_POSITION_ACTIVE)

    def on_position_terminal(self, position: PaperPosition) -> None:
        track = self._tracks.get(position.mint)
        if track is None:
            track = self._track_for(position.mint,
                                    position.closed_at_epoch or 0.0)
        if position.status in SKIP_STATUSES:
            track.state = STATE_SKIPPED
        else:
            track.state = self._TERMINAL_STATE_BY_STATUS.get(
                position.status, STATE_CLOSED)
        position.strategy_state["bala_state"] = track.state

    def monitor_snapshot(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for track in self._tracks.values():
            counts[track.state] = counts.get(track.state, 0) + 1
        watching = sorted(
            mint for mint, track in self._tracks.items()
            if track.state == STATE_WATCHING)[:8]
        return {
            "machine_counts": dict(sorted(counts.items())),
            "watching_sample": watching,
        }


__all__ = [
    "BalaPlanStrategy",
    "BALA_STATES",
    "STATE_DISCOVERED",
    "STATE_AUDIT_TIER_1",
    "STATE_WATCHING",
    "STATE_PAPER_SCOUT_OPEN",
    "STATE_PAPER_DCA_1_OPEN",
    "STATE_PAPER_DCA_2_OPEN",
    "STATE_POSITION_ACTIVE",
    "STATE_INITIALS_RECOVERED",
    "STATE_RUNNER_ACTIVE",
    "STATE_CLOSED",
    "STATE_SKIPPED",
    "STATE_DATA_LOST",
    "STATE_RUGGED",
]
