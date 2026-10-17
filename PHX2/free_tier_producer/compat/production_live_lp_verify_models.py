"""production_live_lp_verify_models.py — data model for the OBSERVE-ONLY LP (liquidity-pool) verifier.

PHX2 "second Yellowstone stream" concept: a SEPARATE Chainstack Yellowstone stream dedicated ONLY to
liquidity-pool verification (real reserve movement vs wash/fake volume). This file is the pure,
stdlib-only model — closed-set status/reason/wash vocabularies + frozen, construction-validated input
and output records. It performs NO I/O, imports NO Axiom code, opens NO transport, and is NOT wired into
the live send path. It is the fake/replay-first foundation proven by production_live_lp_verify_selftest.py.

Design notes:
  * SOL amounts are carried as integer LAMPORTS internally (exact) and rendered as Decimal TEXT for
    display/artifacts (redaction-safe, no binary float). Token amounts are integer BASE UNITS.
  * ``LP_FLOOR_USD_DEFAULT`` MIRRORS the existing PHX2 floor production_live_runner.MIN_LIQUIDITY_USD
    (Decimal("4500")). It is NOT modified there; the selftest asserts the two stay equal so a future
    drift fails a test rather than silently diverging. This module never changes eligibility / the floor.
  * Closed sets are validated at construction (ValueError) — a bad status/reason/wash/kind can never be
    built, mirroring the Stage 30 frozen-dataclass house style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveArtifact,
    effective_quote_reserves,
)

# --------------------------------------------------------------------------- closed-set vocabularies

LP_VERIFY_PASS = "LP_VERIFY_PASS"
LP_VERIFY_WARN = "LP_VERIFY_WARN"
LP_VERIFY_FAIL = "LP_VERIFY_FAIL"
LP_VERIFY_UNKNOWN = "LP_VERIFY_UNKNOWN"
LP_VERIFY_STATUSES = frozenset({LP_VERIFY_PASS, LP_VERIFY_WARN, LP_VERIFY_FAIL, LP_VERIFY_UNKNOWN})

REAL_RESERVE_MOVEMENT = "REAL_RESERVE_MOVEMENT"
LOW_RESERVE_MOVEMENT_VS_VOLUME = "LOW_RESERVE_MOVEMENT_VS_VOLUME"
LP_REMOVED_OR_DRAINING = "LP_REMOVED_OR_DRAINING"
POOL_NOT_FOUND = "POOL_NOT_FOUND"
INSUFFICIENT_EVENTS = "INSUFFICIENT_EVENTS"
UNSTABLE_POOL_STATE = "UNSTABLE_POOL_STATE"
WASH_PATTERN_SUSPECTED = "WASH_PATTERN_SUSPECTED"
LP_VERIFY_REASONS = frozenset({
    REAL_RESERVE_MOVEMENT, LOW_RESERVE_MOVEMENT_VS_VOLUME, LP_REMOVED_OR_DRAINING, POOL_NOT_FOUND,
    INSUFFICIENT_EVENTS, UNSTABLE_POOL_STATE, WASH_PATTERN_SUSPECTED})

WASH_RISK_LOW = "LOW"
WASH_RISK_MEDIUM = "MEDIUM"
WASH_RISK_HIGH = "HIGH"
WASH_RISK_UNKNOWN = "UNKNOWN"
WASH_RISKS = frozenset({WASH_RISK_LOW, WASH_RISK_MEDIUM, WASH_RISK_HIGH, WASH_RISK_UNKNOWN})

SWAP_BUY = "BUY"     # SOL flows INTO the pool (token bought) -> pool SOL reserve +
SWAP_SELL = "SELL"   # SOL flows OUT of the pool (token sold)  -> pool SOL reserve -
SWAP_SIDES = frozenset({SWAP_BUY, SWAP_SELL})

LP_EVENT_ADD = "ADD"
LP_EVENT_REMOVE = "REMOVE"
LP_EVENT_KINDS = frozenset({LP_EVENT_ADD, LP_EVENT_REMOVE})

# Mirrors production_live_runner.MIN_LIQUIDITY_USD (the existing PHX2 pre-reserve LP floor). Kept in sync;
# never written back. The selftest asserts equality so drift is caught.
LP_FLOOR_USD_DEFAULT = Decimal("4500")

RESULT_KIND = "PRODUCTION_LIVE_LP_VERIFY_RESULT"


def _int_no_bool(name: str, v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"{name}_must_be_int")
    return v


def _finite_number(name: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name}_must_be_number")
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise ValueError(f"{name}_must_be_finite")
    return f


# --------------------------------------------------------------------------- input event records


@dataclass(frozen=True)
class LpSwapEvent:
    """One pool swap. ``sol_delta_lamports`` is the SIGNED change to the pool's SOL reserve (+ buy /
    - sell); ``token_delta_base_units`` is the signed token-reserve change (typically opposite sign)."""
    timestamp_s: float
    side: str
    sol_delta_lamports: int
    token_delta_base_units: int

    def __post_init__(self) -> None:
        _finite_number("timestamp_s", self.timestamp_s)
        if self.side not in SWAP_SIDES:
            raise ValueError(f"bad_swap_side:{self.side}")
        _int_no_bool("sol_delta_lamports", self.sol_delta_lamports)
        _int_no_bool("token_delta_base_units", self.token_delta_base_units)


@dataclass(frozen=True)
class LpReserveSnapshot:
    """A point-in-time validated PumpSwap effective-reserve snapshot."""
    timestamp_s: float
    raw_quote_reserves: int
    virtual_quote_reserves: int
    effective_quote_reserves: int
    base_reserves: int
    reserve_source: str
    observation_timestamp: str
    decoder_layout_version: str

    def __post_init__(self) -> None:
        _finite_number("timestamp_s", self.timestamp_s)
        expected = effective_quote_reserves(
            self.raw_quote_reserves, self.virtual_quote_reserves)
        if self.effective_quote_reserves != expected:
            raise ValueError("effective_quote_reserve_mismatch")
        if _int_no_bool("base_reserves", self.base_reserves) <= 0:
            raise ValueError("base_reserves_not_positive")
        if not isinstance(self.reserve_source, str) or not self.reserve_source:
            raise ValueError("reserve_source_required")
        if not isinstance(self.observation_timestamp, str) or not self.observation_timestamp:
            raise ValueError("observation_timestamp_required")
        if not isinstance(self.decoder_layout_version, str) or not self.decoder_layout_version:
            raise ValueError("decoder_layout_version_required")

    @classmethod
    def from_artifact(cls, *, timestamp_s: float,
                      artifact: PumpSwapReserveArtifact) -> "LpReserveSnapshot":
        if not isinstance(artifact, PumpSwapReserveArtifact):
            raise ValueError("validated_reserve_artifact_required")
        return cls(
            timestamp_s=timestamp_s,
            raw_quote_reserves=artifact.raw_quote_reserves,
            virtual_quote_reserves=artifact.virtual_quote_reserves,
            effective_quote_reserves=artifact.effective_quote_reserves,
            base_reserves=artifact.base_reserves,
            reserve_source=artifact.reserve_source,
            observation_timestamp=artifact.observation_timestamp,
            decoder_layout_version=artifact.decoder_layout_version,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_quote_reserves": str(self.raw_quote_reserves),
            "virtual_quote_reserves": str(self.virtual_quote_reserves),
            "effective_quote_reserves": str(self.effective_quote_reserves),
            "base_reserves": str(self.base_reserves),
            "reserve_source": self.reserve_source,
            "observation_timestamp": self.observation_timestamp,
            "decoder_layout_version": self.decoder_layout_version,
            "reserve_validation_status": "VALID",
        }


@dataclass(frozen=True)
class LpLiquidityEvent:
    """A liquidity ADD/REMOVE (magnitudes are non-negative)."""
    timestamp_s: float
    kind: str
    sol_amount_lamports: int
    token_amount_base_units: int

    def __post_init__(self) -> None:
        _finite_number("timestamp_s", self.timestamp_s)
        if self.kind not in LP_EVENT_KINDS:
            raise ValueError(f"bad_liquidity_kind:{self.kind}")
        if _int_no_bool("sol_amount_lamports", self.sol_amount_lamports) < 0:
            raise ValueError("liquidity_sol_negative")
        if _int_no_bool("token_amount_base_units", self.token_amount_base_units) < 0:
            raise ValueError("liquidity_token_negative")


@dataclass(frozen=True)
class LpMigrationEvidence:
    """Lightweight migration evidence (display/provenance only; never echoed as a secret)."""
    migration_time_utc: Optional[str] = None
    migration_slot: Optional[int] = None
    source_ref: Optional[str] = None


@dataclass(frozen=True)
class LpVerifyInput:
    """The full LP-verifier input bundle. Collections are tuples (frozen-safe); the verifier tolerates
    lists too. ``current_liquidity_usd`` is the OPTIONAL static LP value used only for the observe-only
    floor comparison (never to alter the runner's real floor gate)."""
    candidate_mint: str
    pool_address: Optional[str] = None
    pool_protocol: Optional[str] = None
    migration: Optional[LpMigrationEvidence] = None
    swaps: Tuple[LpSwapEvent, ...] = ()
    reserve_snapshots: Tuple[LpReserveSnapshot, ...] = ()
    liquidity_events: Tuple[LpLiquidityEvent, ...] = ()
    current_liquidity_usd: Optional[Decimal] = None
    lp_floor_usd: Decimal = LP_FLOOR_USD_DEFAULT

    def __post_init__(self) -> None:
        if not (isinstance(self.candidate_mint, str) and self.candidate_mint):
            raise ValueError("candidate_mint_required")
        if not isinstance(self.lp_floor_usd, Decimal):
            raise ValueError("lp_floor_usd_must_be_decimal")


# --------------------------------------------------------------------------- config


@dataclass(frozen=True)
class LpVerifyConfig:
    """Tunable, validated thresholds. Defaults are conservative + observe-only. ``observe_only`` is hard-
    locked True for this stage (the verifier NEVER blocks a send here)."""
    min_events: int = 3
    high_gross_sol_lamports: int = 2_000_000_000          # >= 2 SOL gross => "high volume"
    wash_reserve_ratio_warn: Decimal = Decimal("0.15")    # ratio < warn  => low movement vs volume
    wash_reserve_ratio_fail: Decimal = Decimal("0.05")    # ratio < fail (+ high gross) => wash FAIL
    real_movement_ratio_min: Decimal = Decimal("0.25")    # ratio >= this (+ above floor + stable) => PASS
    drain_fraction_fail: Decimal = Decimal("0.50")        # reserve drop >= 50% from peak => drain FAIL
    stability_unstable_max: Decimal = Decimal("0.40")     # stability score < this => UNSTABLE
    observe_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.min_events, int) or isinstance(self.min_events, bool) or self.min_events < 1:
            raise ValueError("min_events_must_be_positive_int")
        if not isinstance(self.high_gross_sol_lamports, int) or self.high_gross_sol_lamports < 0:
            raise ValueError("high_gross_must_be_nonneg_int")
        for nm in ("wash_reserve_ratio_warn", "wash_reserve_ratio_fail", "real_movement_ratio_min",
                   "drain_fraction_fail", "stability_unstable_max"):
            v = getattr(self, nm)
            if not isinstance(v, Decimal) or not v.is_finite() or v < 0:
                raise ValueError(f"{nm}_must_be_finite_nonneg_decimal")
        if self.observe_only is not True:
            raise ValueError("observe_only_must_be_true_this_stage")


# --------------------------------------------------------------------------- output record


@dataclass(frozen=True)
class LpVerifyResult:
    lp_verify_status: str
    lp_verify_reason: str
    wash_risk: str
    pool_delta_sol: str
    pool_delta_token: str
    observed_swap_count: int
    net_sol_flow: str
    gross_sol_flow: str
    reserve_movement_ratio: str
    lp_stability_score: str
    evidence_window_seconds: float
    pool_found: bool
    observe_only: bool
    lp_floor_usd: str
    candidate_mint: str
    pool_protocol: Optional[str] = None
    pumpswap_reserve: Optional[Dict[str, Any]] = None
    notes: Tuple[str, ...] = ()
    kind: str = RESULT_KIND

    def __post_init__(self) -> None:
        if self.lp_verify_status not in LP_VERIFY_STATUSES:
            raise ValueError(f"bad_status:{self.lp_verify_status}")
        if self.lp_verify_reason not in LP_VERIFY_REASONS:
            raise ValueError(f"bad_reason:{self.lp_verify_reason}")
        if self.wash_risk not in WASH_RISKS:
            raise ValueError(f"bad_wash_risk:{self.wash_risk}")
        if self.observe_only is not True:
            raise ValueError("observe_only_must_be_true_this_stage")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "lp_verify_status": self.lp_verify_status,
            "lp_verify_reason": self.lp_verify_reason,
            "wash_risk": self.wash_risk,
            "pool_delta_sol": self.pool_delta_sol,
            "pool_delta_token": self.pool_delta_token,
            "observed_swap_count": self.observed_swap_count,
            "net_sol_flow": self.net_sol_flow,
            "gross_sol_flow": self.gross_sol_flow,
            "reserve_movement_ratio": self.reserve_movement_ratio,
            "lp_stability_score": self.lp_stability_score,
            "evidence_window_seconds": self.evidence_window_seconds,
            "pool_found": self.pool_found,
            "observe_only": self.observe_only,
            "lp_floor_usd": self.lp_floor_usd,
            "candidate_mint": self.candidate_mint,
            "pool_protocol": self.pool_protocol,
            "pumpswap_reserve": self.pumpswap_reserve,
            "notes": list(self.notes),
        }


__all__ = (
    "LP_VERIFY_PASS", "LP_VERIFY_WARN", "LP_VERIFY_FAIL", "LP_VERIFY_UNKNOWN", "LP_VERIFY_STATUSES",
    "REAL_RESERVE_MOVEMENT", "LOW_RESERVE_MOVEMENT_VS_VOLUME", "LP_REMOVED_OR_DRAINING", "POOL_NOT_FOUND",
    "INSUFFICIENT_EVENTS", "UNSTABLE_POOL_STATE", "WASH_PATTERN_SUSPECTED", "LP_VERIFY_REASONS",
    "WASH_RISK_LOW", "WASH_RISK_MEDIUM", "WASH_RISK_HIGH", "WASH_RISK_UNKNOWN", "WASH_RISKS",
    "SWAP_BUY", "SWAP_SELL", "SWAP_SIDES", "LP_EVENT_ADD", "LP_EVENT_REMOVE", "LP_EVENT_KINDS",
    "LP_FLOOR_USD_DEFAULT", "RESULT_KIND",
    "LpSwapEvent", "LpReserveSnapshot", "LpLiquidityEvent", "LpMigrationEvidence", "LpVerifyInput",
    "LpVerifyConfig", "LpVerifyResult",
)
