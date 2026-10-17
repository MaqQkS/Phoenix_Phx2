"""Explicit routing policy for authoritative PHX1 structural/scam blocks.

The original PHX1 calculation is immutable.  This module only decides whether
an already-computed hard-block reason remains enforced or is carried forward as
a visible manual-review warning.  Unknown reasons fail closed as safety
reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


PHX1_STRUCTURAL_POLICY_VERSION = "PHX2_PHX1_STRUCTURAL_POLICY_V1"
PHX1_STRUCTURAL_POLICY_ENFORCE = "ENFORCE"
PHX1_STRUCTURAL_POLICY_SHADOW = "SHADOW"
PHX1_STRUCTURAL_POLICY_MODES = (
    PHX1_STRUCTURAL_POLICY_ENFORCE,
    PHX1_STRUCTURAL_POLICY_SHADOW,
)
PHX1_STRUCTURAL_POLICY_CLI_VALUES = ("enforce", "shadow")

ORIGINAL_STRUCTURAL_PASS = "PASS"
ORIGINAL_STRUCTURAL_HARD_BLOCK = "HARD_BLOCK"
EFFECTIVE_POLICY_PASS = "PASS"
EFFECTIVE_POLICY_HARD_BLOCK = "HARD_BLOCK"
EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING = "ALLOW_WITH_SHADOW_WARNING"
SAFETY_GATE_PASS = "PASS"
SAFETY_GATE_HARD_BLOCK = "HARD_BLOCK"
ORGANICITY_UNVERIFIED = "UNVERIFIED"

# These tokens were classified from their producing functions and actual
# downstream effects, not from their names.  Every token is a conservative
# PHX1 fee/structure screen.  Corruption, identity, proof-consistency, final
# market freshness, liquidity-loss, and delivery reasons are intentionally
# absent.  An absent/unknown token therefore remains enforced.
SHADOWABLE_STRUCTURAL_REASON_TOKENS = frozenset({
    "PHX1_FEE_GATE_SCAM_LIKELY",
    "PHX1_FEE_GATE_DATA_STALE",
    "PHX1_FEE_GATE_INSUFFICIENT_SAMPLE",
    "PHX1_FEE_GATE_PROOF_MISSING",
    "PHX1_FEE_GATE_PAIR_UNCALIBRATED",
    "PHX1_FEE_GATE_NO_DATA",
    "PHX2_FEE_LIFECYCLE_IMMATURE",
    "PHX2_FEE_LIFECYCLE_PROVISIONAL",
    "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE",
    "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK",
    "PHX1_GHOST_BLOCK",
})


def normalize_phx1_structural_policy(value: object = None) -> str:
    """Normalize only the two documented spellings; mixed-case aliases fail."""

    if value is None:
        return PHX1_STRUCTURAL_POLICY_ENFORCE
    if value == "enforce" or value == PHX1_STRUCTURAL_POLICY_ENFORCE:
        return PHX1_STRUCTURAL_POLICY_ENFORCE
    if value == "shadow" or value == PHX1_STRUCTURAL_POLICY_SHADOW:
        return PHX1_STRUCTURAL_POLICY_SHADOW
    raise ValueError("PHX1_STRUCTURAL_POLICY_INVALID")


def _unique_reasons(values: Iterable[object]) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(
        str(value) for value in values
        if isinstance(value, str) and value
    ))


@dataclass(frozen=True)
class Phx1StructuralPolicyDecision:
    policy_version: str
    policy_mode: str
    original_phx1_structural_verdict: str
    effective_phx1_policy_verdict: str
    original_hard_block_reason_tokens: Tuple[str, ...]
    shadow_warning_reason_tokens: Tuple[str, ...]
    non_shadowable_safety_reason_tokens: Tuple[str, ...]
    non_shadowable_safety_gate_result: str
    final_candidate_eligibility: bool
    manual_review_required: bool
    organicity_status: str
    policy_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_mode": self.policy_mode,
            "original_phx1_structural_verdict": (
                self.original_phx1_structural_verdict),
            "effective_phx1_policy_verdict": (
                self.effective_phx1_policy_verdict),
            "original_hard_block_reason_tokens": list(
                self.original_hard_block_reason_tokens),
            "shadow_warning_reason_tokens": list(
                self.shadow_warning_reason_tokens),
            "non_shadowable_safety_reason_tokens": list(
                self.non_shadowable_safety_reason_tokens),
            "non_shadowable_safety_gate_result": (
                self.non_shadowable_safety_gate_result),
            "final_candidate_eligibility": self.final_candidate_eligibility,
            "manual_review_required": self.manual_review_required,
            "organicity_status": self.organicity_status,
            "policy_digest": self.policy_digest,
        }


def _policy_digest(decision: Phx1StructuralPolicyDecision) -> str:
    payload = decision.to_dict()
    payload.pop("policy_digest", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def route_phx1_structural_reasons(
    reasons: Iterable[object],
    *,
    policy_mode: object = PHX1_STRUCTURAL_POLICY_ENFORCE,
) -> Phx1StructuralPolicyDecision:
    """Route exact original reasons while treating every unknown as safety."""

    mode = normalize_phx1_structural_policy(policy_mode)
    original = _unique_reasons(reasons)
    shadowable = tuple(
        reason for reason in original
        if reason in SHADOWABLE_STRUCTURAL_REASON_TOKENS
    )
    safety = tuple(
        reason for reason in original
        if reason not in SHADOWABLE_STRUCTURAL_REASON_TOKENS
    )
    original_verdict = (
        ORIGINAL_STRUCTURAL_HARD_BLOCK
        if shadowable else ORIGINAL_STRUCTURAL_PASS
    )
    if safety:
        effective = EFFECTIVE_POLICY_HARD_BLOCK
    elif shadowable and mode == PHX1_STRUCTURAL_POLICY_SHADOW:
        effective = EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING
    elif shadowable:
        effective = EFFECTIVE_POLICY_HARD_BLOCK
    else:
        effective = EFFECTIVE_POLICY_PASS
    manual_review = (
        effective == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING)
    decision = Phx1StructuralPolicyDecision(
        policy_version=PHX1_STRUCTURAL_POLICY_VERSION,
        policy_mode=mode,
        original_phx1_structural_verdict=original_verdict,
        effective_phx1_policy_verdict=effective,
        original_hard_block_reason_tokens=original,
        shadow_warning_reason_tokens=(shadowable if manual_review else ()),
        non_shadowable_safety_reason_tokens=safety,
        non_shadowable_safety_gate_result=(
            SAFETY_GATE_HARD_BLOCK if safety else SAFETY_GATE_PASS),
        final_candidate_eligibility=(
            effective != EFFECTIVE_POLICY_HARD_BLOCK),
        manual_review_required=manual_review,
        organicity_status=ORGANICITY_UNVERIFIED,
    )
    return replace(decision, policy_digest=_policy_digest(decision))


def validate_phx1_structural_policy_decision(
    decision: object,
) -> Tuple[bool, Optional[str]]:
    if not isinstance(decision, Phx1StructuralPolicyDecision):
        return False, "PHX1_STRUCTURAL_POLICY_PROOF_MISSING"
    try:
        expected = route_phx1_structural_reasons(
            decision.original_hard_block_reason_tokens,
            policy_mode=decision.policy_mode,
        )
    except ValueError:
        return False, "PHX1_STRUCTURAL_POLICY_PROOF_INCONSISTENT"
    if decision != expected:
        return False, "PHX1_STRUCTURAL_POLICY_PROOF_INCONSISTENT"
    return True, None


def policy_metadata_for_filter_results(
    results: Sequence[Mapping[str, Any]],
    *,
    policy_mode: object = PHX1_STRUCTURAL_POLICY_ENFORCE,
) -> dict[str, Any]:
    """Build additive policy metadata without changing frozen filter results."""

    hard_reasons = [
        str(item.get("reason_token"))
        for item in results
        if item.get("result") == ORIGINAL_STRUCTURAL_HARD_BLOCK
        and isinstance(item.get("reason_token"), str)
        and item.get("reason_token")
    ]
    routed = route_phx1_structural_reasons(
        hard_reasons, policy_mode=policy_mode)
    return routed.to_dict()


def build_shadow_candidate_artifact(
    *,
    decision: object,
    candidate: Mapping[str, Any],
    record: Mapping[str, Any],
    entry: object,
    observed_at_utc: str,
    fee_gate_lifecycle: object = None,
) -> Optional[dict[str, Any]]:
    """Project a redaction-safe manual-review row for a shadow-routed candidate."""

    if hasattr(decision, "to_dict"):
        try:
            policy = decision.to_dict()
        except Exception:
            return None
    elif isinstance(decision, Mapping):
        policy = dict(decision)
    else:
        return None
    if not policy.get("manual_review_required") \
            or policy.get("effective_phx1_policy_verdict") \
            != EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING:
        return None

    activation = record.get("activation")
    activation = activation if isinstance(activation, Mapping) else {}
    market = record.get("market_context")
    market = market if isinstance(market, Mapping) else {}
    reserve = market.get("pumpswap_reserve")
    reserve = reserve if isinstance(reserve, Mapping) else {}
    lifecycle = (
        dict(fee_gate_lifecycle)
        if isinstance(fee_gate_lifecycle, Mapping) else {}
    )
    reason = str(record.get("reason") or "PENDING")
    compose_reason = str(record.get("compose_reason") or "")
    return {
        "kind": "PHX2_PHX1_SHADOW_CANDIDATE",
        "token_mint": str(
            record.get("token_mint")
            or candidate.get("token_mint")
            or getattr(entry, "token_mint", "")
        ),
        "candidate_id": (
            candidate.get("candidate_id")
            or getattr(entry, "candidate_id", None)
        ),
        "tier": (
            record.get("compose_tier")
            or candidate.get("tier")
            or getattr(entry, "market_latest_tier", None)
        ),
        "migration_slot": (
            candidate.get("migration_slot")
            or getattr(entry, "migration_slot", None)
        ),
        "migration_time_utc": (
            candidate.get("migration_time_utc")
            or getattr(entry, "migration_time_utc", None)
        ),
        "crossing_slot": (
            activation.get("activation_crossing_slot")
            or activation.get("first_crossing_slot")
        ),
        "crossing_time_utc": (
            activation.get("activated_at_utc")
            or activation.get("first_crossing_timestamp")
        ),
        "policy_mode": policy.get("phx1_structural_policy"),
        "original_phx1_structural_verdict": policy.get(
            "original_phx1_structural_verdict"),
        "shadow_warning_reason_tokens": list(
            policy.get("shadow_warning_reason_tokens") or ()),
        "effective_phx1_policy_verdict": policy.get(
            "effective_phx1_policy_verdict"),
        "non_shadowable_safety_gate_result": policy.get(
            "non_shadowable_safety_gate_result"),
        "final_disposition": reason,
        "alert_composed": bool(
            record.get("compose_attempted")
            or record.get("compose_decision")
        ),
        "deduplicated": "DEDUPE" in (reason + " " + compose_reason),
        "source_freshness_state": (
            market.get("source_freshness_state")
            or market.get("market_state")
            or "NOT_REACHED_PRE_RESERVE"
        ),
        "reserve_freshness_state": (
            reserve.get("freshness_status")
            or reserve.get("reserve_state")
            or "NOT_AVAILABLE"
        ),
        "market_freshness_state": (
            market.get("market_context_freshness_status")
            or market.get("market_state")
            or "NOT_AVAILABLE"
        ),
        "fee_evidence_state": (
            lifecycle.get("lifecycle_state") or "NOT_AVAILABLE"),
        "phx1_policy_digest": policy.get("phx1_policy_digest"),
        "manual_review_required": True,
        "organicity_status": ORGANICITY_UNVERIFIED,
        "operator_label": None,
        "later_outcome": None,
        "observed_at_utc": observed_at_utc,
    }


__all__ = (
    "PHX1_STRUCTURAL_POLICY_VERSION",
    "PHX1_STRUCTURAL_POLICY_ENFORCE",
    "PHX1_STRUCTURAL_POLICY_SHADOW",
    "PHX1_STRUCTURAL_POLICY_MODES",
    "PHX1_STRUCTURAL_POLICY_CLI_VALUES",
    "ORIGINAL_STRUCTURAL_PASS",
    "ORIGINAL_STRUCTURAL_HARD_BLOCK",
    "EFFECTIVE_POLICY_PASS",
    "EFFECTIVE_POLICY_HARD_BLOCK",
    "EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING",
    "SAFETY_GATE_PASS",
    "SAFETY_GATE_HARD_BLOCK",
    "ORGANICITY_UNVERIFIED",
    "SHADOWABLE_STRUCTURAL_REASON_TOKENS",
    "Phx1StructuralPolicyDecision",
    "normalize_phx1_structural_policy",
    "route_phx1_structural_reasons",
    "validate_phx1_structural_policy_decision",
    "policy_metadata_for_filter_results",
    "build_shadow_candidate_artifact",
)
