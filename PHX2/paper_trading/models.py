"""Core datatypes for the PHX2 paper trading engine.

Pure stdlib. All records are plain dataclasses with ``to_record()`` dict
projections so ledgers can be written as JSONL with stable key ordering.
Timestamps are epoch seconds internally and ISO-8601 UTC text in artifacts;
in replay mode every timestamp comes from the replayed records (event time),
never from the wall clock, so identical inputs produce identical artifacts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "phx2_paper_v1"

# ---------------------------------------------------------------------------
# Position statuses
# ---------------------------------------------------------------------------

STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"
STATUS_EXPIRED = "EXPIRED"
STATUS_STOPPED = "STOPPED"
STATUS_TAKE_PROFIT = "TAKE_PROFIT"
STATUS_RUGGED = "RUGGED"
STATUS_DATA_LOST = "DATA_LOST"
STATUS_SKIPPED_PRICE_MISSING = "SKIPPED_PRICE_MISSING"
STATUS_SKIPPED_LIQUIDITY_CAP = "SKIPPED_LIQUIDITY_CAP"
STATUS_SKIPPED_MIN_NOTIONAL = "SKIPPED_MIN_NOTIONAL"
STATUS_SKIPPED_SIZING = "SKIPPED_SIZING"
STATUS_SKIPPED_HIGH_RISK = "SKIPPED_HIGH_RISK"

CLOSED_STATUSES = (
    STATUS_CLOSED,
    STATUS_EXPIRED,
    STATUS_STOPPED,
    STATUS_TAKE_PROFIT,
    STATUS_RUGGED,
    STATUS_DATA_LOST,
)

SKIP_STATUSES = (
    STATUS_SKIPPED_PRICE_MISSING,
    STATUS_SKIPPED_LIQUIDITY_CAP,
    STATUS_SKIPPED_MIN_NOTIONAL,
    STATUS_SKIPPED_SIZING,
    STATUS_SKIPPED_HIGH_RISK,
)

TERMINAL_STATUSES = CLOSED_STATUSES + SKIP_STATUSES


# ---------------------------------------------------------------------------
# Parsing helpers (tolerant of PHX2 artifact string encodings)
# ---------------------------------------------------------------------------


def parse_utc(value: Any) -> Optional[float]:
    """Parse an ISO-8601 UTC string (or epoch number) to epoch seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(float(value)) else None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def utc_iso(epoch: Optional[float]) -> Optional[str]:
    """Render epoch seconds as ISO-8601 UTC text (second precision)."""
    if epoch is None:
        return None
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_number(value: Any) -> Optional[float]:
    """Parse a finite float from PHX2 decimal-text or numeric fields."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        out = float(value)
        return out if math.isfinite(out) else None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            out = float(text)
        except ValueError:
            return None
        return out if math.isfinite(out) else None
    return None


def parse_pct_text(value: Any) -> Optional[float]:
    """Parse ``"67.15%"`` (or a plain number) into 67.15."""
    if isinstance(value, str) and value.strip().endswith("%"):
        return parse_number(value.strip()[:-1])
    return parse_number(value)


_MONEY_SUFFIXES = {"k": 1e3, "m": 1e6, "b": 1e9}


def parse_money_text(value: Any) -> Optional[float]:
    """Parse ``"$25.6k"`` style display money into 25600.0."""
    if not isinstance(value, str):
        return parse_number(value)
    text = value.strip().lstrip("$").replace(",", "")
    if not text:
        return None
    mult = 1.0
    if text[-1].lower() in _MONEY_SUFFIXES:
        mult = _MONEY_SUFFIXES[text[-1].lower()]
        text = text[:-1]
    base = parse_number(text)
    return base * mult if base is not None else None


def parse_tier(value: Any) -> Optional[int]:
    """Parse ``"Tier 2"`` / ``2`` / ``"2"`` into an int tier, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        return int(value) if value > 0 and float(value).is_integer() else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text.startswith("tier"):
            text = text[4:].strip()
        if text.isdigit():
            tier = int(text)
            return tier if tier > 0 else None
    return None


# ---------------------------------------------------------------------------
# Candidate snapshot: one normalized market observation for one mint
# ---------------------------------------------------------------------------


@dataclass
class CandidateSnapshot:
    """One normalized observation of one candidate mint at one event time."""

    ts_epoch: float
    mint: str
    candidate_id: Optional[str] = None
    symbol: Optional[str] = None
    price_usd: Optional[float] = None
    market_cap_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    volume_usd: Optional[float] = None
    supply: Optional[float] = None
    tier: Optional[int] = None
    drawdown_pct: Optional[float] = None  # PHX2 dip drawdown, 0-100 scale
    ath_market_cap_usd: Optional[float] = None
    score: Optional[float] = None
    migration_ts_epoch: Optional[float] = None
    source_kind: Optional[str] = None
    source_file: Optional[str] = None
    source_line: int = 0
    # Producer risk tagging (free-tier scam/bundle heuristic). None/[] when the
    # record predates the risk layer or carried no assessment (== UNKNOWN).
    risk_label: Optional[str] = None
    risk_reasons: List[str] = field(default_factory=list)
    fee_gate: Dict[str, Any] = field(default_factory=dict)
    lp_integrity: Dict[str, Any] = field(default_factory=dict)
    scam_policy: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_price(self) -> bool:
        return self.price_usd is not None and self.price_usd > 0.0

    def derived_supply(self, fallback_supply: Optional[float] = None) -> Optional[float]:
        """Real supply implied by mc/price when both exist, else fallback."""
        if self.supply is not None and self.supply > 0:
            return self.supply
        if (
            self.market_cap_usd is not None
            and self.price_usd is not None
            and self.price_usd > 0
        ):
            return self.market_cap_usd / self.price_usd
        return fallback_supply

    def sort_key(self):
        return (self.ts_epoch, self.source_file or "", self.source_line)

    def to_record(self) -> Dict[str, Any]:
        return {
            "ts_utc": utc_iso(self.ts_epoch),
            "mint": self.mint,
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "price_usd": self.price_usd,
            "market_cap_usd": self.market_cap_usd,
            "liquidity_usd": self.liquidity_usd,
            "volume_usd": self.volume_usd,
            "tier": self.tier,
            "drawdown_pct": self.drawdown_pct,
            "ath_market_cap_usd": self.ath_market_cap_usd,
            "score": self.score,
            "source_kind": self.source_kind,
            "risk_label": self.risk_label,
            "risk_reasons": list(self.risk_reasons),
            "fee_gate": dict(self.fee_gate),
            "lp_integrity": dict(self.lp_integrity),
            "scam_policy": dict(self.scam_policy),
        }


# ---------------------------------------------------------------------------
# Sizing decision
# ---------------------------------------------------------------------------


@dataclass
class SizingDecision:
    """Result of the sizing module for one intended entry."""

    profile: str
    requested_size_usd: float = 0.0
    requested_size_sol: Optional[float] = None
    final_size_usd: float = 0.0
    final_size_sol: Optional[float] = None
    target_token_amount: Optional[float] = None
    estimated_tokens_received: float = 0.0
    entry_market_cap: Optional[float] = None
    entry_liquidity: Optional[float] = None
    cap_reasons: List[str] = field(default_factory=list)
    simulated_slippage_bps: float = 0.0
    simulated_market_impact_bps: float = 0.0
    simulated_fee_bps: float = 0.0
    skipped_reason: Optional[str] = None

    @property
    def is_skip(self) -> bool:
        return self.skipped_reason is not None or self.final_size_usd <= 0.0

    def to_record(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "requested_size_usd": round(self.requested_size_usd, 6),
            "requested_size_sol": self.requested_size_sol,
            "final_size_usd": round(self.final_size_usd, 6),
            "final_size_sol": self.final_size_sol,
            "target_token_amount": self.target_token_amount,
            "estimated_tokens_received": self.estimated_tokens_received,
            "entry_market_cap": self.entry_market_cap,
            "entry_liquidity": self.entry_liquidity,
            "cap_reasons": list(self.cap_reasons),
            "simulated_slippage_bps": self.simulated_slippage_bps,
            "simulated_market_impact_bps": self.simulated_market_impact_bps,
            "simulated_fee_bps": self.simulated_fee_bps,
            "skipped_reason": self.skipped_reason,
        }


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------

SIDE_BUY = "BUY"
SIDE_SELL = "SELL"

# Fill-leg labels: every fill is tagged with which leg of the position plan
# it belongs to, so scout / DCA / recovery legs are separately auditable.
LEG_ENTRY = "ENTRY"
LEG_SCOUT = "SCOUT"
LEG_DCA_1 = "DCA_1"
LEG_DCA_2 = "DCA_2"
LEG_PARTIAL_SELL = "PARTIAL_SELL"
LEG_INITIALS_RECOVERY = "INITIALS_RECOVERY"
LEG_RUNNER_CLOSE = "RUNNER_CLOSE"
LEG_FINAL = "FINAL"


@dataclass
class PaperFill:
    """One simulated fill (entry leg, DCA leg, partial or final exit)."""

    fill_id: str
    paper_trade_id: str
    strategy_name: str
    run_id: str
    mint: str
    side: str
    ts_epoch: float
    price_raw: float
    price_effective: float
    tokens: float
    notional_usd: float
    fee_usd: float
    slippage_bps: float
    impact_bps: float
    reason: str
    leg: str = LEG_ENTRY

    def to_record(self) -> Dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "paper_trade_id": self.paper_trade_id,
            "strategy_name": self.strategy_name,
            "run_id": self.run_id,
            "mint": self.mint,
            "side": self.side,
            "leg": self.leg,
            "ts_utc": utc_iso(self.ts_epoch),
            "price_raw": self.price_raw,
            "price_effective": self.price_effective,
            "tokens": self.tokens,
            "notional_usd": round(self.notional_usd, 6),
            "fee_usd": round(self.fee_usd, 6),
            "slippage_bps": self.slippage_bps,
            "impact_bps": self.impact_bps,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Exit plan: engine-enforced standard exit rules for one open position
# ---------------------------------------------------------------------------


@dataclass
class ExitPlan:
    """Per-position exit parameters the engine enforces generically.

    Percentages are fractional (0.35 == +35%). ``None`` disables a rule.
    """

    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None  # negative, e.g. -0.30
    trailing_stop_pct: Optional[float] = None  # fraction off the peak
    max_hold_seconds: Optional[float] = None
    hold_to_multiple: Optional[float] = None  # e.g. 5.0 => trim at 5x
    trim_fraction: Optional[float] = None  # fraction sold at hold_to_multiple
    random_close_prob: Optional[float] = None  # per price update

    def to_record(self) -> Dict[str, Any]:
        return {
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "max_hold_seconds": self.max_hold_seconds,
            "hold_to_multiple": self.hold_to_multiple,
            "trim_fraction": self.trim_fraction,
            "random_close_prob": self.random_close_prob,
        }


# ---------------------------------------------------------------------------
# Paper position
# ---------------------------------------------------------------------------


@dataclass
class PaperPosition:
    """One virtual position (or a terminal skip record with no fills)."""

    paper_trade_id: str
    strategy_name: str
    run_id: str
    mint: str
    status: str = STATUS_OPEN
    token_symbol: Optional[str] = None
    source_candidate_id: Optional[str] = None
    source_kind: Optional[str] = None
    opened_at_epoch: Optional[float] = None
    closed_at_epoch: Optional[float] = None

    entry_price: Optional[float] = None  # raw market price at entry
    entry_price_effective: Optional[float] = None  # incl slippage/impact/fees
    entry_market_cap: Optional[float] = None
    entry_liquidity: Optional[float] = None
    latest_price: Optional[float] = None
    latest_market_cap: Optional[float] = None
    latest_liquidity: Optional[float] = None
    latest_price_epoch: Optional[float] = None
    exit_price: Optional[float] = None
    exit_market_cap: Optional[float] = None
    # Shared producer ATH checkpoint, copied verbatim into the paper position
    # so paper artifacts can be compared numerically with alert/dashboard.
    ath_market_cap_usd: Optional[float] = None
    ath_price_usd: Optional[float] = None
    ath_observed_at_utc: Optional[str] = None
    ath_provider: Optional[str] = None
    ath_observation_type: Optional[str] = None
    ath_status: Optional[str] = None
    migration_market_cap_usd: Optional[str] = None
    migration_market_cap_source: Optional[str] = None
    migration_baseline_status: Optional[str] = None
    activation_multiplier: Optional[str] = None
    activation_target_market_cap_usd: Optional[str] = None
    activation_state: Optional[str] = None
    activated_at_utc: Optional[str] = None
    activation_observation_source: Optional[str] = None
    activation_current_market_cap_usd: Optional[str] = None

    virtual_sol_size: Optional[float] = None
    virtual_usd_size: float = 0.0
    target_token_amount: Optional[float] = None
    estimated_tokens_received: float = 0.0
    tokens_open: float = 0.0
    simulated_slippage_bps: float = 0.0
    simulated_market_impact_bps: float = 0.0
    simulated_fee_bps: float = 0.0
    cap_reasons: List[str] = field(default_factory=list)

    # Seconds between the two most recent price updates (None until the
    # second update). Lets strategies veto DCA after a data blackout.
    last_price_gap_seconds: Optional[float] = None

    realized_pnl_usd: float = 0.0
    realized_pnl_sol: Optional[float] = None
    unrealized_pnl_usd: float = 0.0
    unrealized_pnl_sol: Optional[float] = None
    realized_pnl_pct: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    max_up_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    peak_price: Optional[float] = None
    post_trim_peak_price: Optional[float] = None

    reason_opened: Optional[str] = None
    reason_closed: Optional[str] = None
    tier: Optional[int] = None
    entry_drawdown_pct: Optional[float] = None
    score: Optional[float] = None
    # Risk view at entry/skip time (producer scam/bundle heuristic; None == UNKNOWN).
    risk_label_at_entry: Optional[str] = None
    risk_reasons_at_entry: List[str] = field(default_factory=list)

    plan: ExitPlan = field(default_factory=ExitPlan)
    # Strategy-private state (e.g. Tier/DCA machine state); JSON-safe.
    strategy_state: Dict[str, Any] = field(default_factory=dict)
    # Buy-leg history (scout / DCA legs); the blended entry derives from it.
    legs: List[Dict[str, Any]] = field(default_factory=list)

    # -- accounting -----------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.status == STATUS_OPEN

    @property
    def cost_basis_usd(self) -> float:
        """Total virtual USD spent to open (fees included)."""
        return self.virtual_usd_size

    @property
    def avg_cost_per_token(self) -> Optional[float]:
        if self.estimated_tokens_received <= 0:
            return None
        return self.virtual_usd_size / self.estimated_tokens_received

    def hold_seconds(self, now_epoch: Optional[float] = None) -> Optional[float]:
        if self.opened_at_epoch is None:
            return None
        end = self.closed_at_epoch if self.closed_at_epoch is not None else now_epoch
        if end is None:
            return None
        return max(0.0, end - self.opened_at_epoch)

    def apply_buy_leg(self, leg: str, ts_epoch: float, tokens: float,
                      cost_usd: float, price_raw: float,
                      price_effective: float,
                      liquidity: Optional[float] = None,
                      market_cap: Optional[float] = None,
                      reason: Optional[str] = None) -> None:
        """Add a buy leg (scout / DCA) and re-blend the average entry.

        ``entry_price`` becomes the token-weighted average raw entry price
        across all buy legs; ``entry_price_effective`` becomes the blended
        cost basis per token (fees/slippage/impact included).
        """
        self.legs.append({
            "leg": leg,
            "ts_utc": utc_iso(ts_epoch),
            "tokens": tokens,
            "cost_usd": round(cost_usd, 6),
            "price_raw": price_raw,
            "price_effective": price_effective,
            "liquidity_usd": liquidity,
            "market_cap_usd": market_cap,
            "reason": reason,
        })
        self.estimated_tokens_received += tokens
        self.tokens_open += tokens
        self.virtual_usd_size += cost_usd
        raw_weight = sum(entry["tokens"] * entry["price_raw"]
                         for entry in self.legs)
        total_tokens = sum(entry["tokens"] for entry in self.legs)
        if total_tokens > 0:
            self.entry_price = raw_weight / total_tokens
        if self.estimated_tokens_received > 0:
            self.entry_price_effective = (
                self.virtual_usd_size / self.estimated_tokens_received)

    @property
    def buy_leg_count(self) -> int:
        return len(self.legs)

    def has_leg(self, leg: str) -> bool:
        return any(entry.get("leg") == leg for entry in self.legs)

    def mark_price(self, price: float, ts_epoch: float,
                   market_cap: Optional[float] = None,
                   liquidity: Optional[float] = None) -> None:
        """Update latest market view + running peak / excursion stats."""
        if self.latest_price_epoch is not None:
            self.last_price_gap_seconds = max(
                0.0, ts_epoch - self.latest_price_epoch)
        self.latest_price = price
        self.latest_price_epoch = ts_epoch
        if market_cap is not None:
            self.latest_market_cap = market_cap
        if liquidity is not None:
            self.latest_liquidity = liquidity
        if self.entry_price and self.entry_price > 0:
            up_pct = (price / self.entry_price - 1.0) * 100.0
            self.max_up_pct = max(self.max_up_pct, up_pct)
        if self.peak_price is None or price > self.peak_price:
            self.peak_price = price
        if self.post_trim_peak_price is not None:
            self.post_trim_peak_price = max(self.post_trim_peak_price, price)
        if self.peak_price and self.peak_price > 0:
            dd_pct = (1.0 - price / self.peak_price) * 100.0
            self.max_drawdown_pct = max(self.max_drawdown_pct, dd_pct)
        self.refresh_unrealized(price)

    def refresh_unrealized(self, price: Optional[float] = None) -> None:
        mark = price if price is not None else self.latest_price
        avg_cost = self.avg_cost_per_token
        if not self.is_open or mark is None or avg_cost is None or self.tokens_open <= 0:
            if not self.is_open or self.tokens_open <= 0:
                self.unrealized_pnl_usd = 0.0
                self.unrealized_pnl_pct = None
            return
        self.unrealized_pnl_usd = (mark - avg_cost) * self.tokens_open
        open_cost = avg_cost * self.tokens_open
        self.unrealized_pnl_pct = (
            (self.unrealized_pnl_usd / open_cost) * 100.0 if open_cost > 0 else None
        )

    def open_position_value_usd(self, price: Optional[float] = None) -> float:
        mark = price if price is not None else self.latest_price
        if mark is None or self.tokens_open <= 0:
            return 0.0
        return mark * self.tokens_open

    def to_record(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "paper_trade_id": self.paper_trade_id,
            "strategy_name": self.strategy_name,
            "run_id": self.run_id,
            "mint": self.mint,
            "token_symbol": self.token_symbol,
            "source_candidate_id": self.source_candidate_id,
            "source_kind": self.source_kind,
            "status": self.status,
            "opened_at_utc": utc_iso(self.opened_at_epoch),
            "closed_at_utc": utc_iso(self.closed_at_epoch),
            "entry_price": self.entry_price,
            "entry_price_effective": self.entry_price_effective,
            "entry_market_cap": self.entry_market_cap,
            "entry_liquidity": self.entry_liquidity,
            "latest_price": self.latest_price,
            "latest_market_cap": self.latest_market_cap,
            "latest_liquidity": self.latest_liquidity,
            "latest_price_at_utc": utc_iso(self.latest_price_epoch),
            "exit_price": self.exit_price,
            "exit_market_cap": self.exit_market_cap,
            "ath_market_cap_usd": self.ath_market_cap_usd,
            "ath_price_usd": self.ath_price_usd,
            "ath_observed_at_utc": self.ath_observed_at_utc,
            "ath_provider": self.ath_provider,
            "ath_observation_type": self.ath_observation_type,
            "ath_status": self.ath_status,
            "migration_market_cap_usd": self.migration_market_cap_usd,
            "migration_market_cap_source": self.migration_market_cap_source,
            "migration_baseline_status": self.migration_baseline_status,
            "activation_multiplier": self.activation_multiplier,
            "activation_target_market_cap_usd": self.activation_target_market_cap_usd,
            "activation_state": self.activation_state,
            "activated_at_utc": self.activated_at_utc,
            "activation_observation_source": self.activation_observation_source,
            "activation_current_market_cap_usd": self.activation_current_market_cap_usd,
            "virtual_sol_size": self.virtual_sol_size,
            "virtual_usd_size": round(self.virtual_usd_size, 6),
            "target_token_amount": self.target_token_amount,
            "estimated_tokens_received": self.estimated_tokens_received,
            "tokens_open": self.tokens_open,
            "simulated_slippage_bps": self.simulated_slippage_bps,
            "simulated_market_impact_bps": self.simulated_market_impact_bps,
            "simulated_fee_bps": self.simulated_fee_bps,
            "cap_reasons": list(self.cap_reasons),
            "realized_pnl_usd": round(self.realized_pnl_usd, 6),
            "realized_pnl_sol": self.realized_pnl_sol,
            "unrealized_pnl_usd": round(self.unrealized_pnl_usd, 6),
            "unrealized_pnl_sol": self.unrealized_pnl_sol,
            "realized_pnl_pct": self.realized_pnl_pct,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "max_up_pct": round(self.max_up_pct, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            # Trailing-stop reference state: must survive a restart, or a
            # runner that peaked at 4x would trail off a stale peak.
            "peak_price": self.peak_price,
            "post_trim_peak_price": self.post_trim_peak_price,
            "last_price_gap_seconds": self.last_price_gap_seconds,
            "reason_opened": self.reason_opened,
            "reason_closed": self.reason_closed,
            "tier": self.tier,
            "entry_drawdown_pct": self.entry_drawdown_pct,
            "score": self.score,
            "risk_label_at_entry": self.risk_label_at_entry,
            "risk_reasons_at_entry": list(self.risk_reasons_at_entry),
            "hold_seconds": self.hold_seconds(),
            "exit_plan": self.plan.to_record(),
            "strategy_state": dict(self.strategy_state),
            "legs": [dict(entry) for entry in self.legs],
        }

    @classmethod
    def from_record(cls, rec: Dict[str, Any]) -> "PaperPosition":
        """Rebuild a position from a ledger record (restart reload)."""
        plan_rec = rec.get("exit_plan") or {}
        pos = cls(
            paper_trade_id=rec["paper_trade_id"],
            strategy_name=rec["strategy_name"],
            run_id=rec.get("run_id", ""),
            mint=rec["mint"],
            status=rec.get("status", STATUS_OPEN),
            token_symbol=rec.get("token_symbol"),
            source_candidate_id=rec.get("source_candidate_id"),
            source_kind=rec.get("source_kind"),
            opened_at_epoch=parse_utc(rec.get("opened_at_utc")),
            closed_at_epoch=parse_utc(rec.get("closed_at_utc")),
            entry_price=rec.get("entry_price"),
            entry_price_effective=rec.get("entry_price_effective"),
            entry_market_cap=rec.get("entry_market_cap"),
            entry_liquidity=rec.get("entry_liquidity"),
            latest_price=rec.get("latest_price"),
            latest_market_cap=rec.get("latest_market_cap"),
            latest_liquidity=rec.get("latest_liquidity"),
            latest_price_epoch=parse_utc(rec.get("latest_price_at_utc")),
            exit_price=rec.get("exit_price"),
            exit_market_cap=rec.get("exit_market_cap"),
            ath_market_cap_usd=rec.get("ath_market_cap_usd"),
            ath_price_usd=rec.get("ath_price_usd"),
            ath_observed_at_utc=rec.get("ath_observed_at_utc"),
            ath_provider=rec.get("ath_provider"),
            ath_observation_type=rec.get("ath_observation_type"),
            ath_status=rec.get("ath_status"),
            migration_market_cap_usd=rec.get("migration_market_cap_usd"),
            migration_market_cap_source=rec.get("migration_market_cap_source"),
            migration_baseline_status=rec.get("migration_baseline_status"),
            activation_multiplier=rec.get("activation_multiplier"),
            activation_target_market_cap_usd=rec.get(
                "activation_target_market_cap_usd"),
            activation_state=rec.get("activation_state"),
            activated_at_utc=rec.get("activated_at_utc"),
            activation_observation_source=rec.get("activation_observation_source"),
            activation_current_market_cap_usd=rec.get(
                "activation_current_market_cap_usd"),
            virtual_sol_size=rec.get("virtual_sol_size"),
            virtual_usd_size=rec.get("virtual_usd_size", 0.0),
            target_token_amount=rec.get("target_token_amount"),
            estimated_tokens_received=rec.get("estimated_tokens_received", 0.0),
            tokens_open=rec.get("tokens_open", 0.0),
            simulated_slippage_bps=rec.get("simulated_slippage_bps", 0.0),
            simulated_market_impact_bps=rec.get("simulated_market_impact_bps", 0.0),
            simulated_fee_bps=rec.get("simulated_fee_bps", 0.0),
            cap_reasons=list(rec.get("cap_reasons") or []),
            realized_pnl_usd=rec.get("realized_pnl_usd", 0.0),
            realized_pnl_sol=rec.get("realized_pnl_sol"),
            unrealized_pnl_usd=rec.get("unrealized_pnl_usd", 0.0),
            unrealized_pnl_sol=rec.get("unrealized_pnl_sol"),
            realized_pnl_pct=rec.get("realized_pnl_pct"),
            unrealized_pnl_pct=rec.get("unrealized_pnl_pct"),
            max_up_pct=rec.get("max_up_pct", 0.0),
            max_drawdown_pct=rec.get("max_drawdown_pct", 0.0),
            reason_opened=rec.get("reason_opened"),
            reason_closed=rec.get("reason_closed"),
            tier=rec.get("tier"),
            entry_drawdown_pct=rec.get("entry_drawdown_pct"),
            score=rec.get("score"),
            risk_label_at_entry=rec.get("risk_label_at_entry"),
            risk_reasons_at_entry=list(rec.get("risk_reasons_at_entry") or []),
            plan=ExitPlan(
                take_profit_pct=plan_rec.get("take_profit_pct"),
                stop_loss_pct=plan_rec.get("stop_loss_pct"),
                trailing_stop_pct=plan_rec.get("trailing_stop_pct"),
                max_hold_seconds=plan_rec.get("max_hold_seconds"),
                hold_to_multiple=plan_rec.get("hold_to_multiple"),
                trim_fraction=plan_rec.get("trim_fraction"),
                random_close_prob=plan_rec.get("random_close_prob"),
            ),
            strategy_state=dict(rec.get("strategy_state") or {}),
            legs=[dict(entry) for entry in (rec.get("legs") or [])],
        )
        pos.peak_price = rec.get("peak_price")
        pos.post_trim_peak_price = rec.get("post_trim_peak_price")
        pos.last_price_gap_seconds = rec.get("last_price_gap_seconds")
        if pos.peak_price is None:
            # Backward compat for records written before peak persistence:
            # fall back to the highest price we can still prove was seen.
            known = [p for p in (pos.entry_price, pos.latest_price)
                     if p is not None and p > 0]
            pos.peak_price = max(known) if known else None
        return pos


__all__ = [
    "SCHEMA_VERSION",
    "STATUS_OPEN",
    "STATUS_CLOSED",
    "STATUS_EXPIRED",
    "STATUS_STOPPED",
    "STATUS_TAKE_PROFIT",
    "STATUS_RUGGED",
    "STATUS_DATA_LOST",
    "STATUS_SKIPPED_PRICE_MISSING",
    "STATUS_SKIPPED_LIQUIDITY_CAP",
    "STATUS_SKIPPED_MIN_NOTIONAL",
    "STATUS_SKIPPED_SIZING",
    "STATUS_SKIPPED_HIGH_RISK",
    "CLOSED_STATUSES",
    "SKIP_STATUSES",
    "TERMINAL_STATUSES",
    "SIDE_BUY",
    "SIDE_SELL",
    "LEG_ENTRY",
    "LEG_SCOUT",
    "LEG_DCA_1",
    "LEG_DCA_2",
    "LEG_PARTIAL_SELL",
    "LEG_INITIALS_RECOVERY",
    "LEG_RUNNER_CLOSE",
    "LEG_FINAL",
    "parse_utc",
    "utc_iso",
    "parse_number",
    "parse_pct_text",
    "parse_money_text",
    "parse_tier",
    "CandidateSnapshot",
    "SizingDecision",
    "PaperFill",
    "ExitPlan",
    "PaperPosition",
]
