"""Observe-only Global Fee Support v1 classification.

``fee_support_per_10k = global_fees_paid_sol / (market_cap_usd / 10000)`` —
all-time SOL fees normalized per $10k of current market cap, computed with
Decimal arithmetic from the SAME canonical inputs the Telegram compose
already holds (the exact-mint Global Fees snapshot and the compose-fresh
market context).  The classification is a pure derived label:

  * below 1.0 SOL per $10k MC  -> ``MANIPULATED``
  * 1.0 through below 2.0      -> ``WEAK``
  * 2.0 or greater             -> ``SUPPORTED``
  * any rejected input         -> ``UNAVAILABLE``

Observe-only discipline (identical to the Global Fees telemetry it rides):
never an eligibility, tier, fee-gate, scam, structural, risk, cooldown,
dedupe, dispatch, metadata-wait, or candidate-lifetime input; a rejected
classification never delays or blocks a send.  Telegram shows the
``(Manipulated)`` suffix ONLY for a conclusive ``MANIPULATED`` result on an
already-rendered Global Fees line; ``WEAK`` and ``SUPPORTED`` stay
artifact-only during v1.  Token age is recorded in the artifact (no
speculative age grace exists in v1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Dict, Mapping, Optional

from PHX2.free_tier_producer.global_fees import (
    GLOBAL_FEES_INTERVAL_ALLTIME,
    GLOBAL_FEES_SCHEMA_VERSION,
    GLOBAL_FEES_STATUS_STALE,
    GLOBAL_FEES_STATUS_VALID,
)


GLOBAL_FEE_SUPPORT_RULE_VERSION = "GLOBAL_FEE_SUPPORT_V1"

# ---- closed classification set --------------------------------------------

FEE_SUPPORT_MANIPULATED = "MANIPULATED"
FEE_SUPPORT_WEAK = "WEAK"
FEE_SUPPORT_SUPPORTED = "SUPPORTED"
FEE_SUPPORT_UNAVAILABLE = "UNAVAILABLE"
FEE_SUPPORT_CLASSIFICATIONS = (
    FEE_SUPPORT_MANIPULATED,
    FEE_SUPPORT_WEAK,
    FEE_SUPPORT_SUPPORTED,
    FEE_SUPPORT_UNAVAILABLE,
)

# ---- v1 thresholds (SOL per $10k market cap) ------------------------------

FEE_SUPPORT_THRESHOLD_MANIPULATED_PER_10K_SOL = Decimal("1.0")
FEE_SUPPORT_THRESHOLD_SUPPORTED_PER_10K_SOL = Decimal("2.0")

# ---- closed calculation statuses ------------------------------------------

FEE_SUPPORT_CALCULATED = "CALCULATED"
FEE_SUPPORT_REJECTED = "REJECTED"

# ---- closed rejection reasons ---------------------------------------------

REASON_FEES_SNAPSHOT_MISSING = "GLOBAL_FEES_SNAPSHOT_MISSING"
REASON_FEES_MINT_MISMATCH = "GLOBAL_FEES_MINT_MISMATCH"
REASON_FEES_UNIT_CONTRACT_UNPROVEN = "GLOBAL_FEES_UNIT_CONTRACT_UNPROVEN"
REASON_FEES_INTERVAL_UNSUPPORTED = "GLOBAL_FEES_INTERVAL_UNSUPPORTED"
REASON_FEES_UNAVAILABLE = "GLOBAL_FEES_UNAVAILABLE"
REASON_FEES_STALE = "GLOBAL_FEES_STALE"
REASON_FEES_VALUE_INVALID = "GLOBAL_FEES_VALUE_INVALID"
REASON_FEES_OBSERVATION_STALE = "GLOBAL_FEES_OBSERVATION_STALE"
REASON_MARKET_CAP_UNAVAILABLE = "MARKET_CAP_UNAVAILABLE"
REASON_MARKET_CAP_NOT_POSITIVE = "MARKET_CAP_NOT_POSITIVE"
REASON_MARKET_CAP_OBSERVATION_STALE = "MARKET_CAP_OBSERVATION_STALE"
REASON_INPUT_OBSERVATION_SKEW_EXCEEDED = "INPUT_OBSERVATION_SKEW_EXCEEDED"

FEE_SUPPORT_REJECTION_REASONS = (
    REASON_FEES_SNAPSHOT_MISSING,
    REASON_FEES_MINT_MISMATCH,
    REASON_FEES_UNIT_CONTRACT_UNPROVEN,
    REASON_FEES_INTERVAL_UNSUPPORTED,
    REASON_FEES_UNAVAILABLE,
    REASON_FEES_STALE,
    REASON_FEES_VALUE_INVALID,
    REASON_FEES_OBSERVATION_STALE,
    REASON_MARKET_CAP_UNAVAILABLE,
    REASON_MARKET_CAP_NOT_POSITIVE,
    REASON_MARKET_CAP_OBSERVATION_STALE,
    REASON_INPUT_OBSERVATION_SKEW_EXCEEDED,
)

#: Both inputs must be at least this fresh at compose time, mirroring the
#: existing ≤300s market-context / Global Fees display freshness contracts.
FEE_SUPPORT_INPUT_MAX_AGE_SECONDS = 300.0
#: Small negative tolerance mirroring the reserve-display future-skew guard.
FEE_SUPPORT_MAX_FUTURE_SKEW_SECONDS = 5.0
#: Approved tolerance for the fees-vs-market-cap observation mismatch.
FEE_SUPPORT_INPUT_MAX_MUTUAL_SKEW_SECONDS = 300.0

#: The only operator label v1 may ever render (appended by the adapter to an
#: already-valid Global Fees line).
FEE_SUPPORT_TELEGRAM_LABEL_MANIPULATED = "Manipulated"


def _parse_decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _parse_utc_epoch(value: object) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).timestamp()


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class GlobalFeeSupportEvaluation:
    """One immutable evaluation of the v1 rule for one exact mint."""

    token_mint: str
    mint_match: bool
    classification: str
    calculation_status: str
    failure_reason: Optional[str]
    global_fees_paid_sol: Optional[str]
    market_cap_usd: Optional[str]
    fee_support_per_10k_sol: Optional[str]
    global_fees_observed_at_utc: Optional[str]
    market_cap_observed_at_utc: Optional[str]
    input_age_seconds: Optional[float]
    token_age_seconds: Optional[float]

    def to_artifact(
        self,
        *,
        rendered_label: Optional[str] = None,
        rendered_in_telegram: bool = False,
    ) -> Dict[str, Any]:
        """Full artifact block: every formula input, both observation
        timestamps, the exact classification, and what Telegram actually
        rendered.  The raw Global Fees observation is never overwritten —
        this block is additive alongside it."""

        return {
            "rule_version": GLOBAL_FEE_SUPPORT_RULE_VERSION,
            "token_mint": self.token_mint,
            "mint_match": self.mint_match,
            "classification": self.classification,
            "calculation_status": self.calculation_status,
            "failure_reason": self.failure_reason,
            "global_fees_paid_sol": self.global_fees_paid_sol,
            "market_cap_usd": self.market_cap_usd,
            "fee_support_per_10k_sol": self.fee_support_per_10k_sol,
            "threshold_manipulated_per_10k_sol": _decimal_text(
                FEE_SUPPORT_THRESHOLD_MANIPULATED_PER_10K_SOL),
            "threshold_supported_per_10k_sol": _decimal_text(
                FEE_SUPPORT_THRESHOLD_SUPPORTED_PER_10K_SOL),
            "global_fees_observed_at_utc": self.global_fees_observed_at_utc,
            "market_cap_observed_at_utc": self.market_cap_observed_at_utc,
            "input_age_seconds": self.input_age_seconds,
            "token_age_seconds": self.token_age_seconds,
            "rendered_label": rendered_label,
            "rendered_in_telegram": bool(rendered_in_telegram),
            "observe_only": True,
        }


def _rejected(
    *,
    mint: str,
    mint_match: bool,
    reason: str,
    fees_text: Optional[str] = None,
    market_cap_text: Optional[str] = None,
    fees_observed_at: Optional[str] = None,
    market_cap_observed_at: Optional[str] = None,
    token_age_seconds: Optional[float] = None,
) -> GlobalFeeSupportEvaluation:
    return GlobalFeeSupportEvaluation(
        token_mint=mint,
        mint_match=mint_match,
        classification=FEE_SUPPORT_UNAVAILABLE,
        calculation_status=FEE_SUPPORT_REJECTED,
        failure_reason=reason,
        global_fees_paid_sol=fees_text,
        market_cap_usd=market_cap_text,
        fee_support_per_10k_sol=None,
        global_fees_observed_at_utc=fees_observed_at,
        market_cap_observed_at_utc=market_cap_observed_at,
        input_age_seconds=None,
        token_age_seconds=token_age_seconds,
    )


def classify_fee_support_per_10k(value: Decimal) -> str:
    """Closed-set threshold classification (exact-boundary semantics:
    exactly 1.0 is WEAK, exactly 2.0 is SUPPORTED)."""

    if value < FEE_SUPPORT_THRESHOLD_MANIPULATED_PER_10K_SOL:
        return FEE_SUPPORT_MANIPULATED
    if value < FEE_SUPPORT_THRESHOLD_SUPPORTED_PER_10K_SOL:
        return FEE_SUPPORT_WEAK
    return FEE_SUPPORT_SUPPORTED


def evaluate_global_fee_support(
    *,
    mint: str,
    global_fees_snapshot: object,
    market_cap_usd: object,
    market_cap_observed_at_utc: object,
    now_utc: object,
    token_age_seconds: Optional[float] = None,
) -> GlobalFeeSupportEvaluation:
    """Pure, total v1 evaluation; a bad input rejects, never raises.

    Required for a CALCULATED result: an exact-mint Global Fees snapshot in
    the proven schema (unit contract-proven SOL), status ``VALID``, interval
    ``alltime``, finite non-negative value, fees observation fresh at compose
    time; a finite strictly-positive market cap whose observation is equally
    fresh; and a fees-vs-market-cap observation skew inside the approved
    tolerance.  The ratio is exact Decimal division — never clamped, never
    maxed.
    """

    mint_text = mint if isinstance(mint, str) else ""
    snapshot = (global_fees_snapshot
                if isinstance(global_fees_snapshot, Mapping) else None)
    if snapshot is None:
        return _rejected(mint=mint_text, mint_match=False,
                         reason=REASON_FEES_SNAPSHOT_MISSING,
                         token_age_seconds=token_age_seconds)
    mint_match = bool(mint_text) and snapshot.get("token_mint") == mint_text
    fees_observed_at = snapshot.get("global_fees_observed_at_utc")
    fees_observed_at = (fees_observed_at
                        if isinstance(fees_observed_at, str) else None)
    fees_text_raw = snapshot.get("global_fees_paid_sol")
    fees_text = fees_text_raw if isinstance(fees_text_raw, str) else None

    def _reject(reason: str, *, market_cap_text: Optional[str] = None,
                market_cap_observed: Optional[str] = None):
        return _rejected(
            mint=mint_text, mint_match=mint_match, reason=reason,
            fees_text=fees_text, market_cap_text=market_cap_text,
            fees_observed_at=fees_observed_at,
            market_cap_observed_at=market_cap_observed,
            token_age_seconds=token_age_seconds)

    if not mint_match:
        return _reject(REASON_FEES_MINT_MISMATCH)
    if snapshot.get("schema_version") != GLOBAL_FEES_SCHEMA_VERSION:
        # The SOL unit is proven by the snapshot schema contract; an unknown
        # schema means the unit is unproven, never guessed.
        return _reject(REASON_FEES_UNIT_CONTRACT_UNPROVEN)
    if snapshot.get("global_fees_interval") != GLOBAL_FEES_INTERVAL_ALLTIME:
        return _reject(REASON_FEES_INTERVAL_UNSUPPORTED)
    status = snapshot.get("global_fees_status")
    if status == GLOBAL_FEES_STATUS_STALE:
        return _reject(REASON_FEES_STALE)
    if status != GLOBAL_FEES_STATUS_VALID:
        return _reject(REASON_FEES_UNAVAILABLE)
    fees_value = _parse_decimal(fees_text_raw)
    if fees_value is None or fees_value < 0:
        return _reject(REASON_FEES_VALUE_INVALID)

    now_epoch = _parse_utc_epoch(now_utc)
    fees_epoch = _parse_utc_epoch(fees_observed_at)
    if now_epoch is None or fees_epoch is None:
        return _reject(REASON_FEES_OBSERVATION_STALE)
    fees_age = now_epoch - fees_epoch
    if not (-FEE_SUPPORT_MAX_FUTURE_SKEW_SECONDS
            <= fees_age <= FEE_SUPPORT_INPUT_MAX_AGE_SECONDS):
        return _reject(REASON_FEES_OBSERVATION_STALE)

    market_cap_value = _parse_decimal(market_cap_usd)
    market_cap_text = _decimal_text(market_cap_value)
    market_cap_observed = (market_cap_observed_at_utc
                           if isinstance(market_cap_observed_at_utc, str)
                           else None)
    if market_cap_value is None:
        return _reject(REASON_MARKET_CAP_UNAVAILABLE,
                       market_cap_observed=market_cap_observed)
    if market_cap_value <= 0:
        return _reject(REASON_MARKET_CAP_NOT_POSITIVE,
                       market_cap_text=market_cap_text,
                       market_cap_observed=market_cap_observed)
    market_cap_epoch = _parse_utc_epoch(market_cap_observed)
    if market_cap_epoch is None:
        return _reject(REASON_MARKET_CAP_OBSERVATION_STALE,
                       market_cap_text=market_cap_text,
                       market_cap_observed=market_cap_observed)
    market_cap_age = now_epoch - market_cap_epoch
    if not (-FEE_SUPPORT_MAX_FUTURE_SKEW_SECONDS
            <= market_cap_age <= FEE_SUPPORT_INPUT_MAX_AGE_SECONDS):
        return _reject(REASON_MARKET_CAP_OBSERVATION_STALE,
                       market_cap_text=market_cap_text,
                       market_cap_observed=market_cap_observed)
    if abs(fees_epoch - market_cap_epoch) \
            > FEE_SUPPORT_INPUT_MAX_MUTUAL_SKEW_SECONDS:
        return _reject(REASON_INPUT_OBSERVATION_SKEW_EXCEEDED,
                       market_cap_text=market_cap_text,
                       market_cap_observed=market_cap_observed)

    with localcontext() as context:
        context.prec = 34
        fee_support = (fees_value * Decimal(10000)) / market_cap_value
    return GlobalFeeSupportEvaluation(
        token_mint=mint_text,
        mint_match=True,
        classification=classify_fee_support_per_10k(fee_support),
        calculation_status=FEE_SUPPORT_CALCULATED,
        failure_reason=None,
        global_fees_paid_sol=fees_text,
        market_cap_usd=market_cap_text,
        fee_support_per_10k_sol=_decimal_text(fee_support),
        global_fees_observed_at_utc=fees_observed_at,
        market_cap_observed_at_utc=market_cap_observed,
        input_age_seconds=round(max(fees_age, market_cap_age), 3),
        token_age_seconds=token_age_seconds,
    )


__all__ = (
    "GLOBAL_FEE_SUPPORT_RULE_VERSION",
    "FEE_SUPPORT_MANIPULATED",
    "FEE_SUPPORT_WEAK",
    "FEE_SUPPORT_SUPPORTED",
    "FEE_SUPPORT_UNAVAILABLE",
    "FEE_SUPPORT_CLASSIFICATIONS",
    "FEE_SUPPORT_THRESHOLD_MANIPULATED_PER_10K_SOL",
    "FEE_SUPPORT_THRESHOLD_SUPPORTED_PER_10K_SOL",
    "FEE_SUPPORT_CALCULATED",
    "FEE_SUPPORT_REJECTED",
    "FEE_SUPPORT_REJECTION_REASONS",
    "REASON_FEES_SNAPSHOT_MISSING",
    "REASON_FEES_MINT_MISMATCH",
    "REASON_FEES_UNIT_CONTRACT_UNPROVEN",
    "REASON_FEES_INTERVAL_UNSUPPORTED",
    "REASON_FEES_UNAVAILABLE",
    "REASON_FEES_STALE",
    "REASON_FEES_VALUE_INVALID",
    "REASON_FEES_OBSERVATION_STALE",
    "REASON_MARKET_CAP_UNAVAILABLE",
    "REASON_MARKET_CAP_NOT_POSITIVE",
    "REASON_MARKET_CAP_OBSERVATION_STALE",
    "REASON_INPUT_OBSERVATION_SKEW_EXCEEDED",
    "FEE_SUPPORT_INPUT_MAX_AGE_SECONDS",
    "FEE_SUPPORT_MAX_FUTURE_SKEW_SECONDS",
    "FEE_SUPPORT_INPUT_MAX_MUTUAL_SKEW_SECONDS",
    "FEE_SUPPORT_TELEGRAM_LABEL_MANIPULATED",
    "GlobalFeeSupportEvaluation",
    "classify_fee_support_per_10k",
    "evaluate_global_fee_support",
)
