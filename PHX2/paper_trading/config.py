"""Config model for the PHX2 paper trading engine.

JSON-file driven (stdlib only). Every tunable the strategies / sizing /
market simulation use lives here so plans can be changed without code edits.
``default_config()`` is the fully-populated baseline; ``load_config(path)``
merges a JSON file over those defaults and validates it.

No secrets belong in this config: it is thresholds, sizes and paths only.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_SCHEMA_VERSION = "phx2_paper_config_v1"

DEFAULT_OUTPUT_ROOT = "C:\\Users\\BalaC\\phx2_paper_trading"

# Sizing profile names
PROFILE_FIXED_SOL = "FIXED_SOL"
PROFILE_FIXED_USD = "FIXED_USD"
PROFILE_MARKET_CAP_CURVE = "MARKET_CAP_CURVE"
PROFILE_TOKEN_TARGET_CURVE = "TOKEN_TARGET_CURVE"
PROFILE_LIQUIDITY_CAPPED = "LIQUIDITY_CAPPED"
PROFILE_VOLUME_CAPPED = "VOLUME_CAPPED"
PROFILE_HYBRID_REALISTIC = "HYBRID_REALISTIC"

SIZING_PROFILES = (
    PROFILE_FIXED_SOL,
    PROFILE_FIXED_USD,
    PROFILE_MARKET_CAP_CURVE,
    PROFILE_TOKEN_TARGET_CURVE,
    PROFILE_LIQUIDITY_CAPPED,
    PROFILE_VOLUME_CAPPED,
    PROFILE_HYBRID_REALISTIC,
)

# Strategy type names
STRATEGY_BALA_PLAN = "BALA_PLAN"
STRATEGY_CONFIG_PLAN = "CONFIG_PLAN"
STRATEGY_MONKEY_RANDOM = "MONKEY_RANDOM"
STRATEGY_MONKEY_HOLD = "MONKEY_HOLD"
STRATEGY_THREE_X = "THREE_X_INITIALS_RUNNER"
STRATEGY_HIGH_RISK_OBSERVER = "HIGH_RISK_OBSERVER"

STRATEGY_TYPES = (
    STRATEGY_BALA_PLAN,
    STRATEGY_CONFIG_PLAN,
    STRATEGY_MONKEY_RANDOM,
    STRATEGY_MONKEY_HOLD,
    STRATEGY_THREE_X,
    STRATEGY_HIGH_RISK_OBSERVER,
)

END_OF_STREAM_CLOSE = "CLOSE_AT_LAST_PRICE"
END_OF_STREAM_LEAVE_OPEN = "LEAVE_OPEN"

RUG_ACTION_CLOSE = "CLOSE"
RUG_ACTION_FREEZE = "FREEZE"


class ConfigError(ValueError):
    """Raised on invalid paper trading config; carries all messages."""

    def __init__(self, problems: List[str]) -> None:
        self.problems = list(problems)
        super().__init__(
            "invalid paper trading config: " + "; ".join(self.problems)
        )


# ---------------------------------------------------------------------------
# Default HYBRID_REALISTIC market-cap curve (token targets + notional caps)
# ---------------------------------------------------------------------------
# Band selection: first band whose mc_max is None or >= entry market cap.
# Bands below $150k target a token amount; the top band sizes by notional.

DEFAULT_HYBRID_CURVE: List[Dict[str, Any]] = [
    {"mc_max_usd": 15_000, "token_target_min": 7_000_000,
     "token_target_max": 10_000_000, "max_notional_usd": 150.0},
    {"mc_max_usd": 50_000, "token_target_min": 2_000_000,
     "token_target_max": 5_000_000, "max_notional_usd": 150.0},
    {"mc_max_usd": 150_000, "token_target_min": 1_000_000,
     "token_target_max": 3_000_000, "max_notional_usd": 250.0},
    {"mc_max_usd": None, "notional_usd": 200.0, "max_notional_usd": 400.0},
]

# Simple notional-per-band curve for the plain MARKET_CAP_CURVE profile.
DEFAULT_MC_NOTIONAL_CURVE: List[Dict[str, Any]] = [
    {"mc_max_usd": 15_000, "notional_usd": 75.0},
    {"mc_max_usd": 50_000, "notional_usd": 100.0},
    {"mc_max_usd": 150_000, "notional_usd": 150.0},
    {"mc_max_usd": None, "notional_usd": 200.0},
]


@dataclass
class SizingProfileConfig:
    """Parameters for one named sizing profile."""

    profile: str = PROFILE_HYBRID_REALISTIC
    fixed_sol_size: float = 0.25
    fixed_usd_size: float = 100.0
    curve: List[Dict[str, Any]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_HYBRID_CURVE))
    token_target_fraction: float = 0.5  # where inside a band's token range to aim
    max_buy_pct_of_liquidity: Optional[float] = 0.5  # percent of LP
    max_buy_pct_of_recent_volume: Optional[float] = 10.0  # percent of volume
    max_abs_notional_usd: Optional[float] = 500.0
    min_abs_notional_usd: float = 10.0
    fallback_supply: Optional[float] = None  # must be set explicitly to enable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "fixed_sol_size": self.fixed_sol_size,
            "fixed_usd_size": self.fixed_usd_size,
            "curve": copy.deepcopy(self.curve),
            "token_target_fraction": self.token_target_fraction,
            "max_buy_pct_of_liquidity": self.max_buy_pct_of_liquidity,
            "max_buy_pct_of_recent_volume": self.max_buy_pct_of_recent_volume,
            "max_abs_notional_usd": self.max_abs_notional_usd,
            "min_abs_notional_usd": self.min_abs_notional_usd,
            "fallback_supply": self.fallback_supply,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], problems: List[str],
                  where: str) -> "SizingProfileConfig":
        cfg = cls()
        for key, value in raw.items():
            if not hasattr(cfg, key):
                problems.append(f"{where}: unknown sizing key '{key}'")
                continue
            setattr(cfg, key, value)
        if cfg.profile not in SIZING_PROFILES:
            problems.append(
                f"{where}: unknown sizing profile '{cfg.profile}' "
                f"(expected one of {', '.join(SIZING_PROFILES)})")
        if cfg.min_abs_notional_usd is None or cfg.min_abs_notional_usd < 0:
            problems.append(f"{where}: min_abs_notional_usd must be >= 0")
        if not isinstance(cfg.curve, list) or not cfg.curve:
            problems.append(f"{where}: curve must be a non-empty list")
        return cfg


@dataclass
class MarketSimConfig:
    """Fill realism + death handling for the paper market simulator."""

    base_slippage_bps: float = 150.0
    fee_bps: float = 100.0
    impact_bps_per_pct_of_lp: float = 30.0
    max_impact_bps: float = 800.0
    data_lost_after_seconds: float = 1800.0
    # Fraction of last-known open value credited when a position dies with
    # no market data (pessimistic on purpose: dead feeds are usually dead
    # tokens).
    data_lost_value_ratio: float = 0.25
    rug_lp_collapse_ratio: float = 0.2  # LP below 20% of entry LP => rug
    rug_price_drop_pct: float = -0.95  # -95% from entry classifies as rug
    rug_action: str = RUG_ACTION_CLOSE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_slippage_bps": self.base_slippage_bps,
            "fee_bps": self.fee_bps,
            "impact_bps_per_pct_of_lp": self.impact_bps_per_pct_of_lp,
            "max_impact_bps": self.max_impact_bps,
            "data_lost_after_seconds": self.data_lost_after_seconds,
            "data_lost_value_ratio": self.data_lost_value_ratio,
            "rug_lp_collapse_ratio": self.rug_lp_collapse_ratio,
            "rug_price_drop_pct": self.rug_price_drop_pct,
            "rug_action": self.rug_action,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any],
                  problems: List[str]) -> "MarketSimConfig":
        cfg = cls()
        for key, value in raw.items():
            if not hasattr(cfg, key):
                problems.append(f"market_sim: unknown key '{key}'")
                continue
            setattr(cfg, key, value)
        if cfg.rug_action not in (RUG_ACTION_CLOSE, RUG_ACTION_FREEZE):
            problems.append(
                f"market_sim: rug_action must be {RUG_ACTION_CLOSE} or "
                f"{RUG_ACTION_FREEZE}")
        if not (0.0 <= cfg.data_lost_value_ratio <= 1.0):
            problems.append(
                "market_sim: data_lost_value_ratio must be in [0, 1]")
        return cfg


# Param keys whose dict values are fixed-schema blocks (deep-merged with
# unknown-subkey validation). Open-ended dicts like tier_dip_bands are
# replaced wholesale instead.
_DEEP_MERGE_PARAM_KEYS = {"audit"}


@dataclass
class StrategyConfig:
    """One strategy instance: type + engine limits + free-form params."""

    name: str
    strategy_type: str
    enabled: bool = True
    sizing_profile: str = "default_hybrid"
    max_open_positions: int = 25
    allow_reentry: bool = False
    # Risk-aware paper protection (default OFF): a strategy only receives RISK_HIGH
    # candidates when it explicitly opts in (the HIGH_RISK_OBSERVER bucket does).
    allow_high_risk: bool = False
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "strategy_type": self.strategy_type,
            "enabled": self.enabled,
            "sizing_profile": self.sizing_profile,
            "max_open_positions": self.max_open_positions,
            "allow_reentry": self.allow_reentry,
            "allow_high_risk": self.allow_high_risk,
            "params": copy.deepcopy(self.params),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], problems: List[str],
                  index: int) -> Optional["StrategyConfig"]:
        where = f"strategies[{index}]"
        name = raw.get("name")
        stype = raw.get("strategy_type")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{where}: missing strategy 'name'")
            return None
        if stype not in STRATEGY_TYPES:
            problems.append(
                f"{where} ({name}): unknown strategy_type '{stype}' "
                f"(expected one of {', '.join(STRATEGY_TYPES)})")
            return None
        cfg = cls(name=name.strip(), strategy_type=stype)
        if stype == STRATEGY_HIGH_RISK_OBSERVER:
            # The observer bucket exists to absorb RISK_HIGH candidates; opt-in by type.
            cfg.allow_high_risk = True
        for key in ("enabled", "sizing_profile", "max_open_positions",
                    "allow_reentry", "allow_high_risk"):
            if key in raw:
                setattr(cfg, key, raw[key])
        params = raw.get("params", {})
        if not isinstance(params, dict):
            problems.append(f"{where} ({name}): params must be an object")
            params = {}
        cfg.params = copy.deepcopy(default_strategy_params(stype))
        for key, value in params.items():
            if key not in cfg.params:
                problems.append(
                    f"{where} ({name}): unknown param '{key}' for {stype}")
                continue
            default_value = cfg.params[key]
            if key in _DEEP_MERGE_PARAM_KEYS and \
                    isinstance(default_value, dict) and isinstance(value, dict):
                # Deep-merge fixed-schema blocks (e.g. the bala audit
                # rules) so a partial override keeps the other defaults.
                for sub_key, sub_value in value.items():
                    if sub_key not in default_value:
                        problems.append(
                            f"{where} ({name}): unknown param "
                            f"'{key}.{sub_key}' for {stype}")
                        continue
                    default_value[sub_key] = sub_value
            else:
                cfg.params[key] = value
        if not isinstance(cfg.max_open_positions, int) or cfg.max_open_positions < 1:
            problems.append(
                f"{where} ({name}): max_open_positions must be an int >= 1")
        return cfg


@dataclass
class RunConfig:
    """Run-level settings shared by all strategies."""

    output_root: str = DEFAULT_OUTPUT_ROOT
    run_id: Optional[str] = None  # default: derived from config hash + seed
    random_seed: int = 1337
    starting_bankroll_usd: float = 1000.0
    sol_price_usd: Optional[float] = None  # set to fill *_sol fields
    heartbeat_every_seconds: float = 300.0  # event-time in replay
    equity_curve_bucket_seconds: float = 60.0
    end_of_stream_policy: str = END_OF_STREAM_CLOSE
    recent_events_window: int = 50
    max_snapshots: Optional[int] = None  # debug limiter

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_root": self.output_root,
            "run_id": self.run_id,
            "random_seed": self.random_seed,
            "starting_bankroll_usd": self.starting_bankroll_usd,
            "sol_price_usd": self.sol_price_usd,
            "heartbeat_every_seconds": self.heartbeat_every_seconds,
            "equity_curve_bucket_seconds": self.equity_curve_bucket_seconds,
            "end_of_stream_policy": self.end_of_stream_policy,
            "recent_events_window": self.recent_events_window,
            "max_snapshots": self.max_snapshots,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any],
                  problems: List[str]) -> "RunConfig":
        cfg = cls()
        for key, value in raw.items():
            if not hasattr(cfg, key):
                problems.append(f"run: unknown key '{key}'")
                continue
            setattr(cfg, key, value)
        if cfg.end_of_stream_policy not in (END_OF_STREAM_CLOSE,
                                            END_OF_STREAM_LEAVE_OPEN):
            problems.append(
                "run: end_of_stream_policy must be "
                f"{END_OF_STREAM_CLOSE} or {END_OF_STREAM_LEAVE_OPEN}")
        if not isinstance(cfg.random_seed, int):
            problems.append("run: random_seed must be an int")
        return cfg


@dataclass
class PaperConfig:
    """Root config object."""

    run: RunConfig = field(default_factory=RunConfig)
    market_sim: MarketSimConfig = field(default_factory=MarketSimConfig)
    sizing_profiles: Dict[str, SizingProfileConfig] = field(default_factory=dict)
    strategies: List[StrategyConfig] = field(default_factory=list)
    input_paths: List[str] = field(default_factory=list)

    def enabled_strategies(self) -> List[StrategyConfig]:
        return [s for s in self.strategies if s.enabled]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "run": self.run.to_dict(),
            "market_sim": self.market_sim.to_dict(),
            "sizing_profiles": {
                name: prof.to_dict()
                for name, prof in sorted(self.sizing_profiles.items())
            },
            "strategies": [s.to_dict() for s in self.strategies],
            "input_paths": list(self.input_paths),
        }

    def config_digest(self) -> str:
        """Digest of the *behavioral* config: where artifacts land
        (output_root/run_id) does not change what a run does."""
        import hashlib
        payload = self.to_dict()
        payload["run"] = {k: v for k, v in payload["run"].items()
                          if k not in ("output_root", "run_id")}
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Per-strategy default params
# ---------------------------------------------------------------------------


def default_strategy_params(strategy_type: str) -> Dict[str, Any]:
    """Default params for a strategy type (all config-overridable)."""
    if strategy_type == STRATEGY_BALA_PLAN:
        return {
            # PHX2 tier dip bands (percent drawdown from anchored ATH).
            # Tier 1 = audit/watch zone, Tier 2 = DCA_1, Tier 3 = DCA_2.
            "tier_dip_bands": {
                "1": [50.0, 60.0],
                "2": [62.0, 80.0],
                "3": [82.0, 95.0],
            },
            "allowed_tiers": [1, 2, 3],
            "require_tier": True,
            "derive_tier_from_drawdown": True,
            "min_entry_market_cap_usd": None,
            "max_entry_market_cap_usd": None,
            "min_entry_liquidity_usd": 2000.0,
            "min_entry_volume_usd": None,
            # --- Tier 1 audit rules (fail closed when a configured rule
            # has no data). Age rules need migration evidence timestamps.
            "audit": {
                "min_liquidity_usd": 2000.0,
                "min_market_cap_usd": None,
                "max_market_cap_usd": None,
                "min_volume_usd": None,
                "min_age_seconds": None,
                "max_age_seconds": None,
                "max_drawdown_pct": 97.0,
                "min_ath_market_cap_usd": None,
                "require_migration_evidence": False,
                "audit_ttl_seconds": 600.0,
            },
            # --- Scout / DCA ladder (fractions of the max position size
            # the sizing profile allows for the mint's MC band).
            "enable_scout_entry": False,
            "scout_entry_pct_of_max_position": 0.10,
            "dca_1_pct_of_max_position": 0.50,
            "dca_2_pct_of_max_position": 0.40,
            "max_total_position_usd": None,  # None: sizing-profile cap only
            "max_total_tokens": None,
            "min_time_between_dca_seconds": 120.0,
            "require_reaudit_before_dca": True,
            "max_dca_count": 2,
            "allow_tier3_initial_entry": True,
            # --- DCA health gates ("do not average down into death").
            "do_not_dca_if_liquidity_down_pct_exceeds": 40.0,
            "do_not_dca_if_volume_dead": False,
            "do_not_dca_if_price_data_stale_seconds": 900.0,
            "do_not_dca_if_market_cap_below_usd": 3000.0,
            # --- Risk-aware entry conservatism (RISK_HIGH is already refused by the
            # engine gate: bala never sets allow_high_risk). RISK_MEDIUM is allowed
            # ONLY when LP/MC clear these floors and no market-quality risk reason
            # (stale / refresh-failing / incomplete / LP-missing) is present.
            "risk_medium_min_liquidity_usd": 10000.0,
            "risk_medium_min_market_cap_usd": 30000.0,
            "risk_medium_require_fresh_market": True,
            # --- Exit management.
            "take_profit_pct": 0.35,
            "stop_loss_pct": -0.30,
            "trailing_stop_pct": None,
            "max_hold_seconds": 21600.0,
            # Optional initials recovery (sell back initial cost, ride
            # the rest as a runner). None disables.
            "initials_recovery_multiple": None,
            "runner_trailing_stop_pct": 0.30,
            # High-quality path: hold toward 5x, trim, then trail.
            "high_quality_min_score": 0.8,
            "high_quality_tiers": [],
            "high_quality_hold_multiple": 5.0,
            "high_quality_trim_fraction": 0.5,
            "high_quality_trailing_stop_pct": 0.25,
        }
    if strategy_type == STRATEGY_CONFIG_PLAN:
        return {
            "require_price": True,
            "min_entry_market_cap_usd": None,
            "max_entry_market_cap_usd": None,
            "min_entry_liquidity_usd": None,
            "min_entry_volume_usd": None,
            "allowed_tiers": None,  # None = any (including unknown)
            "entry_dip_band_pct": None,  # [lo, hi] percent drawdown
            "take_profit_pct": None,
            "stop_loss_pct": None,
            "trailing_stop_pct": None,
            "max_hold_seconds": None,
        }
    if strategy_type == STRATEGY_MONKEY_RANDOM:
        return {
            "entry_probability": 0.15,
            "require_price": True,
            "take_profit_pct_range": [0.20, 3.00],
            "stop_loss_pct_range": [-0.80, -0.20],
            "hold_seconds_range": [600.0, 21600.0],
            "random_close_prob": 0.01,
        }
    if strategy_type == STRATEGY_MONKEY_HOLD:
        return {
            "entry_mode": "ALL",  # ALL or RANDOM
            "entry_probability": 0.5,
            "hold_seconds": 14400.0,
            "take_profit_pct": None,
            "stop_loss_pct": None,
        }
    if strategy_type == STRATEGY_THREE_X:
        return {
            "recover_multiple": 3.0,
            "runner_trailing_stop_pct": 0.30,
            "runner_max_hold_seconds": 86400.0,
            "stop_loss_pct": None,
            "min_entry_liquidity_usd": 2000.0,
            "min_entry_market_cap_usd": None,
            "max_entry_market_cap_usd": None,
            "allowed_tiers": None,
        }
    if strategy_type == STRATEGY_HIGH_RISK_OBSERVER:
        return {
            # The degen/scam study bucket: enters ONLY RISK_HIGH candidates (the ones
            # every default strategy skips), so clean-strategy results stay unpolluted
            # while the wreckage is still measured. Tight plan: small notional profile
            # is the operator's choice; exits are fast by default.
            "require_price": True,
            "only_high_risk": True,
            "take_profit_pct": 0.50,
            "stop_loss_pct": -0.60,
            "max_hold_seconds": 3600.0,
            "trailing_stop_pct": None,
        }
    raise ValueError(f"unknown strategy type: {strategy_type}")


# ---------------------------------------------------------------------------
# Default / example config
# ---------------------------------------------------------------------------


def default_config() -> PaperConfig:
    """The fully-populated baseline config with all five strategies."""
    cfg = PaperConfig()
    cfg.sizing_profiles = {
        "default_hybrid": SizingProfileConfig(
            profile=PROFILE_HYBRID_REALISTIC,
            fallback_supply=1_000_000_000,
        ),
        "fixed_usd_100": SizingProfileConfig(
            profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
            curve=copy.deepcopy(DEFAULT_MC_NOTIONAL_CURVE),
        ),
    }
    cfg.strategies = [
        StrategyConfig(name="bala_plan", strategy_type=STRATEGY_BALA_PLAN,
                       sizing_profile="default_hybrid",
                       params={**default_strategy_params(STRATEGY_BALA_PLAN),
                               "initials_recovery_multiple": 1.35,
                               "take_profit_pct": None,
                               "runner_trailing_stop_pct": 0.30}),
        StrategyConfig(name="config_plan", strategy_type=STRATEGY_CONFIG_PLAN,
                       sizing_profile="default_hybrid",
                       params={**default_strategy_params(STRATEGY_CONFIG_PLAN),
                               "min_entry_liquidity_usd": 2000.0,
                               "take_profit_pct": 0.5,
                               "stop_loss_pct": -0.35,
                               "max_hold_seconds": 21600.0}),
        StrategyConfig(name="monkey_random",
                       strategy_type=STRATEGY_MONKEY_RANDOM,
                       sizing_profile="default_hybrid",
                       params=default_strategy_params(STRATEGY_MONKEY_RANDOM)),
        StrategyConfig(name="monkey_hold", strategy_type=STRATEGY_MONKEY_HOLD,
                       sizing_profile="default_hybrid",
                       params=default_strategy_params(STRATEGY_MONKEY_HOLD)),
        StrategyConfig(name="three_x_runner", strategy_type=STRATEGY_THREE_X,
                       sizing_profile="default_hybrid",
                       params=default_strategy_params(STRATEGY_THREE_X)),
        StrategyConfig(name="high_risk_observer",
                       strategy_type=STRATEGY_HIGH_RISK_OBSERVER,
                       sizing_profile="default_hybrid",
                       allow_high_risk=True,
                       params=default_strategy_params(
                           STRATEGY_HIGH_RISK_OBSERVER)),
    ]
    return cfg


def load_config_dict(raw: Dict[str, Any]) -> PaperConfig:
    """Build + validate a PaperConfig from a parsed JSON object."""
    problems: List[str] = []
    if not isinstance(raw, dict):
        raise ConfigError(["config root must be a JSON object"])
    known_root = {"schema_version", "run", "market_sim", "sizing_profiles",
                  "strategies", "input_paths"}
    for key in raw:
        if key not in known_root:
            problems.append(f"unknown top-level key '{key}'")

    cfg = PaperConfig()
    cfg.run = RunConfig.from_dict(raw.get("run", {}) or {}, problems)
    cfg.market_sim = MarketSimConfig.from_dict(
        raw.get("market_sim", {}) or {}, problems)

    profiles_raw = raw.get("sizing_profiles")
    if profiles_raw is None:
        cfg.sizing_profiles = default_config().sizing_profiles
    elif not isinstance(profiles_raw, dict) or not profiles_raw:
        problems.append("sizing_profiles must be a non-empty object")
    else:
        for name, prof_raw in profiles_raw.items():
            if not isinstance(prof_raw, dict):
                problems.append(f"sizing_profiles.{name} must be an object")
                continue
            cfg.sizing_profiles[name] = SizingProfileConfig.from_dict(
                prof_raw, problems, f"sizing_profiles.{name}")

    strategies_raw = raw.get("strategies")
    if strategies_raw is None:
        cfg.strategies = default_config().strategies
    elif not isinstance(strategies_raw, list) or not strategies_raw:
        problems.append("strategies must be a non-empty list")
    else:
        seen_names = set()
        for i, strat_raw in enumerate(strategies_raw):
            if not isinstance(strat_raw, dict):
                problems.append(f"strategies[{i}] must be an object")
                continue
            strat = StrategyConfig.from_dict(strat_raw, problems, i)
            if strat is None:
                continue
            if strat.name in seen_names:
                problems.append(
                    f"strategies[{i}]: duplicate strategy name '{strat.name}'")
                continue
            seen_names.add(strat.name)
            cfg.strategies.append(strat)

    paths_raw = raw.get("input_paths", [])
    if paths_raw and not isinstance(paths_raw, list):
        problems.append("input_paths must be a list of paths")
    else:
        cfg.input_paths = [str(p) for p in (paths_raw or [])]

    for strat in cfg.strategies:
        if strat.sizing_profile not in cfg.sizing_profiles:
            problems.append(
                f"strategy '{strat.name}': sizing_profile "
                f"'{strat.sizing_profile}' is not defined in sizing_profiles")

    if problems:
        raise ConfigError(problems)
    return cfg


def load_config(path: str) -> PaperConfig:
    """Load + validate a JSON config file; defaults fill anything omitted."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError([f"config file is not valid JSON: {exc}"]) from exc
    return load_config_dict(raw)


def write_example_config(path: str) -> str:
    """Write the fully-populated example config JSON; returns the path."""
    cfg = default_config()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(cfg.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return str(out)


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_HYBRID_CURVE",
    "DEFAULT_MC_NOTIONAL_CURVE",
    "PROFILE_FIXED_SOL",
    "PROFILE_FIXED_USD",
    "PROFILE_MARKET_CAP_CURVE",
    "PROFILE_TOKEN_TARGET_CURVE",
    "PROFILE_LIQUIDITY_CAPPED",
    "PROFILE_VOLUME_CAPPED",
    "PROFILE_HYBRID_REALISTIC",
    "SIZING_PROFILES",
    "STRATEGY_BALA_PLAN",
    "STRATEGY_CONFIG_PLAN",
    "STRATEGY_MONKEY_RANDOM",
    "STRATEGY_MONKEY_HOLD",
    "STRATEGY_THREE_X",
    "STRATEGY_HIGH_RISK_OBSERVER",
    "STRATEGY_TYPES",
    "END_OF_STREAM_CLOSE",
    "END_OF_STREAM_LEAVE_OPEN",
    "RUG_ACTION_CLOSE",
    "RUG_ACTION_FREEZE",
    "ConfigError",
    "SizingProfileConfig",
    "MarketSimConfig",
    "StrategyConfig",
    "RunConfig",
    "PaperConfig",
    "default_strategy_params",
    "default_config",
    "load_config_dict",
    "load_config",
    "write_example_config",
]
