"""Central composite delivery-safety policy.

Single-stream production (the default, ``LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM``)
authorizes sends from the PHX1 Fee Gate family plus caller-supplied independent
block reasons only.  No LP Integrity verdict exists, is required, or may block:
there is no verifier stream, no canonical-pool snapshot requirement, and no
rolling liquidity evidence in the decision.  Legacy LP reason codes arriving
from old artifacts are stripped (never enforced) and surfaced observably as
``LEGACY_LP_STATE_IGNORED_SINGLE_STREAM``.

The historical two-stream composite (fee + LP Integrity) remains available
ONLY behind the explicit non-default ``LP_INTEGRITY_MODE_TWO_STREAM`` for
offline analysis and historical parity tests; production must not select it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import threading
from typing import Any, Dict, Iterable, Optional, Tuple

from PHX2.free_tier_producer.liquidity_integrity import (
    LP_INTEGRITY_FAIL,
    LP_INTEGRITY_FAIL_REASON,
    LP_INTEGRITY_UNKNOWN_REASON,
    LpIntegritySnapshot,
    format_lp_integrity_lines,
    lp_integrity_block_reason,
    validate_lp_snapshot,
)
from PHX2.free_tier_producer.phx1_fee_gate import (
    BLOCK_SCAM_LIKELY,
    FEE_GATE_UNKNOWN,
    PHX1_FEE_GATE_SCAM_LIKELY,
    FeeGateSnapshot,
    fee_gate_block_reason,
    format_fee_gate_lines,
    validate_fee_snapshot,
)
from PHX2.free_tier_producer.phx1_structural_policy import (
    EFFECTIVE_POLICY_HARD_BLOCK,
    PHX1_STRUCTURAL_POLICY_ENFORCE,
    PHX1_STRUCTURAL_POLICY_VERSION,
    route_phx1_structural_reasons,
)


POLICY_VERSION = "PHX2_COMPOSITE_SCAM_POLICY_V2"
POLICY_ALLOW = "ALLOW"
POLICY_HARD_BLOCK = "HARD_BLOCK"
LP_AND_FEE_COMPOSITE_BLOCK = "LP_AND_FEE_COMPOSITE_BLOCK"
CANONICAL_POOL_PROOF_REQUIRED = "CANONICAL_POOL_PROOF_REQUIRED"
SECURITY_DECISION_PROOF_MISSING = "SECURITY_DECISION_PROOF_MISSING"
SECURITY_DECISION_PROOF_INCONSISTENT = "SECURITY_DECISION_PROOF_INCONSISTENT"

# Runtime LP-integrity modes.  Single-stream (verifier removed) is the ONE
# production default; two-stream survives only for offline/historical use.
LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM = "DISABLED_SINGLE_STREAM"
LP_INTEGRITY_MODE_TWO_STREAM = "TWO_STREAM"
LP_INTEGRITY_MODES = (
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    LP_INTEGRITY_MODE_TWO_STREAM,
)

# Observable marker for legacy LP state that was seen and deliberately not
# enforced in single-stream mode.
LEGACY_LP_STATE_IGNORED_SINGLE_STREAM = "LEGACY_LP_STATE_IGNORED_SINGLE_STREAM"

# Every historical LP-family block reason.  In single-stream mode none of
# these may ever appear in ``final_block_reasons`` — not from fresh
# evaluation and not restored from old artifacts.
LEGACY_LP_BLOCK_REASONS = frozenset({
    LP_INTEGRITY_FAIL_REASON,
    LP_INTEGRITY_UNKNOWN_REASON,
    CANONICAL_POOL_PROOF_REQUIRED,
    "CANONICAL_POOL_UNPROVEN",
    "INVALID_POOL_AUTHORITY",
    "VERIFIER_EVIDENCE_STALE",
    "LIQUIDITY_VERIFICATION_INCOMPLETE",
    LP_AND_FEE_COMPOSITE_BLOCK,
    "LP_INTEGRITY_PROOF_MISSING",
    "LP_INTEGRITY_PROOF_INCONSISTENT",
})


@dataclass(frozen=True)
class DeliverySafetyDecision:
    policy_version: str
    candidate_mint: str
    fee_snapshot: FeeGateSnapshot
    lp_snapshot: Optional[LpIntegritySnapshot]
    lp_integrity_mode: str
    existing_block_reasons: Tuple[str, ...]
    fee_reason_family: Tuple[str, ...]
    lp_reason_family: Tuple[str, ...]
    original_filter_results: Tuple[
        Tuple[str, str, Tuple[str, ...]], ...]
    phx1_structural_policy: str
    phx1_policy_version: str
    original_phx1_structural_verdict: str
    effective_phx1_policy_verdict: str
    original_hard_block_reason_tokens: Tuple[str, ...]
    shadow_warning_reason_tokens: Tuple[str, ...]
    non_shadowable_safety_reason_tokens: Tuple[str, ...]
    non_shadowable_safety_gate_result: str
    final_candidate_eligibility: bool
    manual_review_required: bool
    organicity_status: str
    phx1_policy_digest: str
    final_block_reasons: Tuple[str, ...]
    legacy_lp_reasons_ignored: Tuple[str, ...]
    verdict: str
    eligible: bool
    compose_allowed: bool
    reservation_allowed: bool
    ledger_mutation_allowed: bool
    transport_allowed: bool
    telegram_transport_allowed: bool
    discord_transport_allowed: bool
    proof_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "candidate_mint": self.candidate_mint,
            "fee_snapshot": self.fee_snapshot.to_dict(),
            "lp_snapshot": (
                self.lp_snapshot.to_dict() if self.lp_snapshot is not None else None),
            "lp_integrity_mode": self.lp_integrity_mode,
            "existing_block_reasons": list(self.existing_block_reasons),
            "fee_reason_family": list(self.fee_reason_family),
            "lp_reason_family": list(self.lp_reason_family),
            "original_filter_results": [
                {
                    "filter_name": name,
                    "original_verdict": verdict,
                    "reason_tokens": list(reasons),
                }
                for name, verdict, reasons in self.original_filter_results
            ],
            "phx1_structural_policy": self.phx1_structural_policy,
            "phx1_policy_version": self.phx1_policy_version,
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
            "phx1_policy_digest": self.phx1_policy_digest,
            "final_block_reasons": list(self.final_block_reasons),
            "legacy_lp_reasons_ignored": list(self.legacy_lp_reasons_ignored),
            "verdict": self.verdict,
            "eligible": self.eligible,
            "compose_allowed": self.compose_allowed,
            "reservation_allowed": self.reservation_allowed,
            "ledger_mutation_allowed": self.ledger_mutation_allowed,
            "transport_allowed": self.transport_allowed,
            "telegram_transport_allowed": self.telegram_transport_allowed,
            "discord_transport_allowed": self.discord_transport_allowed,
            "proof_digest": self.proof_digest,
        }


def _digest(decision: DeliverySafetyDecision) -> str:
    payload = decision.to_dict()
    payload.pop("proof_digest", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seal_delivery_decision(decision: DeliverySafetyDecision) -> DeliverySafetyDecision:
    return replace(decision, proof_digest=_digest(replace(decision, proof_digest="")))


def evaluate_delivery_safety(
    *,
    fee_snapshot: FeeGateSnapshot,
    lp_snapshot: Optional[LpIntegritySnapshot] = None,
    existing_block_reasons: Iterable[str] = (),
    lp_integrity_mode: str = LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    phx1_structural_policy: str = PHX1_STRUCTURAL_POLICY_ENFORCE,
) -> DeliverySafetyDecision:
    """Combine independent reason families without allowing one to override another.

    Default mode is single-stream: no LP snapshot exists and none may be
    supplied — passing one raises instead of silently reviving the removed
    verifier semantics, and no synthetic LP verdict is ever fabricated.
    """

    if lp_integrity_mode not in LP_INTEGRITY_MODES:
        raise ValueError("LP_INTEGRITY_MODE_INVALID")
    single_stream = lp_integrity_mode == LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM
    if single_stream and lp_snapshot is not None:
        raise ValueError("LP_SNAPSHOT_FORBIDDEN_IN_SINGLE_STREAM_MODE")
    if not single_stream and lp_snapshot is None:
        raise ValueError("LP_SNAPSHOT_REQUIRED_IN_TWO_STREAM_MODE")

    mint = getattr(fee_snapshot, "candidate_mint", "")
    supplied = tuple(dict.fromkeys(
        str(value) for value in existing_block_reasons if value))
    legacy_ignored: Tuple[str, ...] = ()
    if single_stream:
        # Legacy LP reason codes (for example restored from a two-stream-era
        # artifact) are observably ignored, never enforced.
        legacy_ignored = tuple(
            value for value in supplied if value in LEGACY_LP_BLOCK_REASONS)
        existing = tuple(
            value for value in supplied if value not in LEGACY_LP_BLOCK_REASONS)
    else:
        existing = supplied
    fee_reasons = tuple(getattr(fee_snapshot, "fee_gate_reasons", ()) or ())
    lp_reasons = tuple(getattr(lp_snapshot, "lp_integrity_reasons", ()) or ())
    blocks = list(existing)
    filter_results = [
        ("upstream_gate", POLICY_HARD_BLOCK, (reason,))
        for reason in existing
    ]
    fee_valid, fee_invalid_reason = validate_fee_snapshot(fee_snapshot)
    if not mint:
        blocks.append(SECURITY_DECISION_PROOF_INCONSISTENT)
    if not fee_valid:
        fee_block = fee_invalid_reason or SECURITY_DECISION_PROOF_INCONSISTENT
        blocks.append(fee_block)
        filter_results.append(
            ("phx1_fee_gate", POLICY_HARD_BLOCK, (fee_block,)))
    else:
        reason = fee_gate_block_reason(fee_snapshot)
        if reason:
            blocks.append(reason)
        filter_results.append((
            "phx1_fee_gate",
            POLICY_HARD_BLOCK if reason else "PASS",
            tuple(dict.fromkeys((*fee_reasons, *((reason,) if reason else ())))),
        ))
    if not single_stream:
        lp_valid, lp_invalid_reason = validate_lp_snapshot(lp_snapshot)
        identity_consistent = bool(
            mint and mint == getattr(lp_snapshot, "candidate_mint", None))
        if not identity_consistent:
            blocks.append(SECURITY_DECISION_PROOF_INCONSISTENT)
        if not lp_valid:
            lp_block = lp_invalid_reason or SECURITY_DECISION_PROOF_INCONSISTENT
            blocks.append(lp_block)
            filter_results.append(
                ("lp_integrity", POLICY_HARD_BLOCK, (lp_block,)))
        else:
            reason = lp_integrity_block_reason(lp_snapshot)
            if reason:
                blocks.append(reason)
            if not lp_snapshot.canonical_pool_proven:
                blocks.append(CANONICAL_POOL_PROOF_REQUIRED)
            filter_results.append((
                "lp_integrity",
                POLICY_HARD_BLOCK
                if reason or not lp_snapshot.canonical_pool_proven
                else "PASS",
                tuple(dict.fromkeys((
                    *lp_reasons,
                    *((reason,) if reason else ()),
                    *((CANONICAL_POOL_PROOF_REQUIRED,)
                      if not lp_snapshot.canonical_pool_proven else ()),
                ))),
            ))
        if (getattr(fee_snapshot, "fee_gate_label", None) == PHX1_FEE_GATE_SCAM_LIKELY
                and getattr(lp_snapshot, "lp_integrity", None) == LP_INTEGRITY_FAIL):
            blocks.append(LP_AND_FEE_COMPOSITE_BLOCK)
            filter_results.append((
                "historical_fee_lp_composite",
                POLICY_HARD_BLOCK,
                (LP_AND_FEE_COMPOSITE_BLOCK,),
            ))
    # SUSPICIOUS is deliberately not a standalone block.  No numeric or
    # identity-based WARN composite is activated without a separately approved policy.
    blocks = list(dict.fromkeys(blocks))
    routed = route_phx1_structural_reasons(
        blocks, policy_mode=phx1_structural_policy)
    effective_blocks = (
        tuple(blocks)
        if routed.policy_mode == PHX1_STRUCTURAL_POLICY_ENFORCE
        else routed.non_shadowable_safety_reason_tokens
    )
    allowed = routed.final_candidate_eligibility
    return seal_delivery_decision(DeliverySafetyDecision(
        policy_version=POLICY_VERSION,
        candidate_mint=mint,
        fee_snapshot=fee_snapshot,
        lp_snapshot=lp_snapshot,
        lp_integrity_mode=lp_integrity_mode,
        existing_block_reasons=existing,
        fee_reason_family=fee_reasons,
        lp_reason_family=lp_reasons,
        original_filter_results=tuple(filter_results),
        phx1_structural_policy=routed.policy_mode,
        phx1_policy_version=PHX1_STRUCTURAL_POLICY_VERSION,
        original_phx1_structural_verdict=(
            routed.original_phx1_structural_verdict),
        effective_phx1_policy_verdict=(
            routed.effective_phx1_policy_verdict),
        original_hard_block_reason_tokens=(
            routed.original_hard_block_reason_tokens),
        shadow_warning_reason_tokens=(
            routed.shadow_warning_reason_tokens),
        non_shadowable_safety_reason_tokens=(
            routed.non_shadowable_safety_reason_tokens),
        non_shadowable_safety_gate_result=(
            routed.non_shadowable_safety_gate_result),
        final_candidate_eligibility=(
            routed.final_candidate_eligibility),
        manual_review_required=routed.manual_review_required,
        organicity_status=routed.organicity_status,
        phx1_policy_digest=routed.policy_digest,
        final_block_reasons=tuple(effective_blocks),
        legacy_lp_reasons_ignored=legacy_ignored,
        verdict=POLICY_ALLOW if allowed else POLICY_HARD_BLOCK,
        eligible=allowed,
        compose_allowed=allowed,
        reservation_allowed=allowed,
        ledger_mutation_allowed=allowed,
        transport_allowed=allowed,
        telegram_transport_allowed=allowed,
        discord_transport_allowed=False,
    ))


def validate_delivery_decision(decision: object) -> Tuple[bool, Optional[str]]:
    if not isinstance(decision, DeliverySafetyDecision):
        return False, SECURITY_DECISION_PROOF_MISSING
    if decision.policy_version != POLICY_VERSION:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if decision.lp_integrity_mode not in LP_INTEGRITY_MODES:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if not decision.proof_digest or decision.proof_digest != _digest(decision):
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    try:
        routed = route_phx1_structural_reasons(
            decision.original_hard_block_reason_tokens,
            policy_mode=decision.phx1_structural_policy,
        )
    except ValueError:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if (
        decision.phx1_policy_version != PHX1_STRUCTURAL_POLICY_VERSION
        or decision.original_phx1_structural_verdict
        != routed.original_phx1_structural_verdict
        or decision.effective_phx1_policy_verdict
        != routed.effective_phx1_policy_verdict
        or decision.shadow_warning_reason_tokens
        != routed.shadow_warning_reason_tokens
        or decision.non_shadowable_safety_reason_tokens
        != routed.non_shadowable_safety_reason_tokens
        or decision.non_shadowable_safety_gate_result
        != routed.non_shadowable_safety_gate_result
        or decision.final_candidate_eligibility
        != routed.final_candidate_eligibility
        or decision.manual_review_required != routed.manual_review_required
        or decision.organicity_status != routed.organicity_status
        or decision.phx1_policy_digest != routed.policy_digest
    ):
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    expected_effective_blocks = (
        decision.original_hard_block_reason_tokens
        if decision.phx1_structural_policy == PHX1_STRUCTURAL_POLICY_ENFORCE
        else decision.non_shadowable_safety_reason_tokens
    )
    if decision.final_block_reasons != expected_effective_blocks:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    fee_valid, _ = validate_fee_snapshot(decision.fee_snapshot)
    if not fee_valid:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if not decision.candidate_mint \
            or decision.candidate_mint != decision.fee_snapshot.candidate_mint:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if decision.lp_integrity_mode == LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM:
        # Single-stream: no LP snapshot may exist and no LP-family reason may
        # block — including LP_AND_FEE_COMPOSITE_BLOCK.
        if decision.lp_snapshot is not None:
            return False, SECURITY_DECISION_PROOF_INCONSISTENT
        if any(reason in LEGACY_LP_BLOCK_REASONS
               for reason in decision.final_block_reasons):
            return False, SECURITY_DECISION_PROOF_INCONSISTENT
    else:
        if decision.lp_snapshot is None:
            return False, SECURITY_DECISION_PROOF_MISSING
        lp_valid, _ = validate_lp_snapshot(decision.lp_snapshot)
        if not lp_valid:
            return False, SECURITY_DECISION_PROOF_INCONSISTENT
        if decision.candidate_mint != decision.lp_snapshot.candidate_mint:
            return False, SECURITY_DECISION_PROOF_INCONSISTENT
    flags = (
        decision.eligible,
        decision.compose_allowed,
        decision.reservation_allowed,
        decision.ledger_mutation_allowed,
        decision.transport_allowed,
        decision.telegram_transport_allowed,
    )
    if decision.verdict == POLICY_ALLOW and (not all(flags) or decision.final_block_reasons):
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if decision.verdict == POLICY_HARD_BLOCK and (any(flags) or not decision.final_block_reasons):
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if decision.final_candidate_eligibility != decision.eligible:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if (
        decision.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    ) != (decision.verdict == POLICY_HARD_BLOCK):
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    if decision.discord_transport_allowed:
        return False, SECURITY_DECISION_PROOF_INCONSISTENT
    return True, None


def delivery_block_reason(decision: object) -> Optional[str]:
    valid, reason = validate_delivery_decision(decision)
    if not valid:
        return reason or SECURITY_DECISION_PROOF_INCONSISTENT
    assert isinstance(decision, DeliverySafetyDecision)
    if not decision.eligible:
        return "+".join(decision.final_block_reasons)
    return None


LP_INTEGRITY_DISPLAY_DISABLED = "DISABLED"


def format_security_lines(decision: DeliverySafetyDecision) -> Tuple[str, ...]:
    if decision.lp_snapshot is None:
        # Never display PASS for a verdict that was not computed.
        lp_lines: Tuple[str, ...] = (
            f"LP Integrity: {LP_INTEGRITY_DISPLAY_DISABLED}",)
    else:
        lp_lines = format_lp_integrity_lines(decision.lp_snapshot)
    return (
        *format_fee_gate_lines(decision.fee_snapshot),
        *lp_lines,
        f"Composite verdict: {decision.verdict}",
    )


class SecurityDecisionIndex:
    """Mint-bound immutable decisions shared by every downstream consumer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_mint: Dict[str, DeliverySafetyDecision] = {}

    def bind(self, decision: DeliverySafetyDecision) -> None:
        valid, reason = validate_delivery_decision(decision)
        if not valid:
            raise ValueError(reason or SECURITY_DECISION_PROOF_INCONSISTENT)
        with self._lock:
            self._by_mint[decision.candidate_mint] = decision

    def get(self, mint: str) -> Optional[DeliverySafetyDecision]:
        with self._lock:
            return self._by_mint.get(str(mint))

    def proof_gate(self, mint: str) -> Optional[str]:
        return delivery_block_reason(self.get(mint))

    def line(self, mint: str) -> Optional[str]:
        decision = self.get(mint)
        if decision is None:
            return None
        return "\n".join(format_security_lines(decision))

    def summary(self) -> Dict[str, int]:
        with self._lock:
            values = tuple(self._by_mint.values())
        counts = {
            "lp_pass": 0, "lp_warn": 0, "lp_fail": 0, "lp_unknown": 0,
            "lp_disabled": 0,
            "fee_scam_likely": 0, "fee_suspicious": 0, "fee_pass": 0, "fee_unknown": 0,
            "blocked_fee_scam_likely": 0, "blocked_lp_integrity": 0, "blocked_composite": 0,
            "legacy_lp_reasons_ignored": 0,
            "phx1_policy_enforce": 0, "phx1_policy_shadow": 0,
            "phx1_shadow_warning_allowed": 0,
            "phx1_non_shadowable_safety_blocked": 0,
        }
        for decision in values:
            counts[
                "phx1_policy_shadow"
                if decision.phx1_structural_policy != PHX1_STRUCTURAL_POLICY_ENFORCE
                else "phx1_policy_enforce"
            ] += 1
            if decision.manual_review_required:
                counts["phx1_shadow_warning_allowed"] += 1
            if decision.non_shadowable_safety_reason_tokens:
                counts["phx1_non_shadowable_safety_blocked"] += 1
            if decision.lp_snapshot is None:
                counts["lp_disabled"] += 1
            else:
                lp_key = "lp_" + decision.lp_snapshot.lp_integrity.lower()
                if lp_key in counts:
                    counts[lp_key] += 1
            label = decision.fee_snapshot.fee_gate_label
            if label == PHX1_FEE_GATE_SCAM_LIKELY:
                counts["fee_scam_likely"] += 1
            elif label == "Suspicious":
                counts["fee_suspicious"] += 1
            elif label == FEE_GATE_UNKNOWN:
                counts["fee_unknown"] += 1
            else:
                counts["fee_pass"] += 1
            if BLOCK_SCAM_LIKELY in decision.final_block_reasons:
                counts["blocked_fee_scam_likely"] += 1
            if any(reason in decision.final_block_reasons
                   for reason in (LP_INTEGRITY_FAIL_REASON, LP_INTEGRITY_UNKNOWN_REASON)):
                counts["blocked_lp_integrity"] += 1
            if LP_AND_FEE_COMPOSITE_BLOCK in decision.final_block_reasons:
                counts["blocked_composite"] += 1
            if decision.legacy_lp_reasons_ignored:
                counts["legacy_lp_reasons_ignored"] += 1
        return counts


__all__ = (
    "POLICY_VERSION", "POLICY_ALLOW", "POLICY_HARD_BLOCK",
    "LP_AND_FEE_COMPOSITE_BLOCK", "CANONICAL_POOL_PROOF_REQUIRED",
    "SECURITY_DECISION_PROOF_MISSING", "SECURITY_DECISION_PROOF_INCONSISTENT",
    "LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM", "LP_INTEGRITY_MODE_TWO_STREAM",
    "LP_INTEGRITY_MODES", "LEGACY_LP_STATE_IGNORED_SINGLE_STREAM",
    "LEGACY_LP_BLOCK_REASONS", "LP_INTEGRITY_DISPLAY_DISABLED",
    "DeliverySafetyDecision", "SecurityDecisionIndex", "evaluate_delivery_safety",
    "seal_delivery_decision", "validate_delivery_decision", "delivery_block_reason",
    "format_security_lines",
)
