from __future__ import annotations

from dataclasses import replace

import pytest

from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.liquidity_integrity import (
    ADD_LIQUIDITY,
    CREATE_POOL,
    LP_INTEGRITY_FAIL,
    LP_INTEGRITY_PASS,
    LP_INTEGRITY_UNKNOWN,
    LP_INTEGRITY_WARN,
    REMOVE_LIQUIDITY,
    SECONDARY_POOL_MANIPULATION_PROVEN,
    UNEXPLAINED_LIQUIDITY_REMOVAL,
    LiquidityEvent,
    MigrationLiquidityIdentity,
    classify_liquidity_integrity,
    seal_lp_snapshot,
)
from PHX2.free_tier_producer.phx1_fee_gate import (
    BLOCK_PROOF_INCONSISTENT,
    BLOCK_SCAM_LIKELY,
    PHX1_FEE_GATE_NORMAL,
    PHX1_FEE_GATE_SCAM_LIKELY,
    PHX1_FEE_GATE_SUSPICIOUS,
    build_fee_snapshot,
)
from PHX2.free_tier_producer.scam_policy import (
    CANONICAL_POOL_PROOF_REQUIRED,
    LEGACY_LP_BLOCK_REASONS,
    LP_AND_FEE_COMPOSITE_BLOCK,
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    LP_INTEGRITY_MODE_TWO_STREAM,
    POLICY_ALLOW,
    POLICY_HARD_BLOCK,
    SECURITY_DECISION_PROOF_INCONSISTENT,
    delivery_block_reason,
    evaluate_delivery_safety,
    format_security_lines,
    validate_delivery_decision,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "ExVW9Wxpr4TnMchukxGwMYM4XYTr3yTKwpqDE35E9seW"
SECONDARY = "7w5J5iv7Y8DRjsXMvVC7bWvJeypLX3sVn9gZPVcspump"
WSOL = "So11111111111111111111111111111111111111112"
AT = "1970-01-01T00:16:40Z"


def _fee(label):
    components = {
        PHX1_FEE_GATE_NORMAL: (600_000_000, 200_000_000, 200_000_000, 100_000_000),
        PHX1_FEE_GATE_SUSPICIOUS: (190_000_000, 100_000_000, 710_000_000, 30_000_000),
        PHX1_FEE_GATE_SCAM_LIKELY: (100_000_000, 100_000_000, 800_000_000, 10_000_000),
    }[label]
    lp, protocol, creator, priority = components
    state = {
        "quote_mint": WSOL, "quote_asset": "SOL", "pair_type": "TOKEN_SOL", "unit": "SOL",
        "lp": lp, "protocol": protocol, "creator": creator,
        "base": 5_000_000, "priority": priority, "jito": 0,
        "events": 1000, "signatures": {f"sig-{i}" for i in range(1000)},
        "first": AT, "last": AT, "last_epoch": 1000,
        "recent": (), "tx_ante": (),
    }
    snapshot = build_fee_snapshot(MINT, state=state, now_epoch=1000)
    assert snapshot.fee_gate_label == label
    return snapshot


def _event(kind, *, signature, slot, pool=POOL):
    is_create = kind == CREATE_POOL
    is_remove = kind == REMOVE_LIQUIDITY
    return LiquidityEvent(
        kind=kind, program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
        discriminator_hex="00" * 8, pool=pool, base_mint=MINT, quote_mint=WSOL,
        pair=f"{MINT}/{WSOL}", base_vault="base-vault", quote_vault="quote-vault",
        pool_authority=pool, signer="signer", fee_payer="payer", authority="authority",
        transaction_signature=signature, event_index=0, slot=slot, timestamp_utc=AT,
        base_amount=10, quote_amount=20,
        base_reserve_delta=(-10 if is_remove else 10),
        quote_reserve_delta=(-20 if is_remove else 20),
        pool_pda_valid=(True if is_create else None), mint_pair_valid=True,
        vault_derivation_valid=(True if is_create else None), vault_ownership_valid=True,
        pool_authority_valid=True, canonical_semantics_valid=is_create,
        malformed_reasons=(),
    )


def _lp(*extras):
    canonical = _event(CREATE_POOL, signature="migration", slot=100)
    identity = MigrationLiquidityIdentity(
        candidate_mint=MINT, pool=POOL, quote_mint=WSOL,
        migration_signature="migration", migration_slot=100,
        migration_timestamp_utc=AT, provider_pool=POOL,
    )
    return classify_liquidity_integrity(identity, (canonical, *extras), now_utc=AT)


def _two_stream(fee_snapshot, lp_snapshot, **kwargs):
    return evaluate_delivery_safety(
        fee_snapshot=fee_snapshot, lp_snapshot=lp_snapshot,
        lp_integrity_mode=LP_INTEGRITY_MODE_TWO_STREAM, **kwargs)


# ---------------------------------------------------------------------------
# Single-stream production mode (the default)
# ---------------------------------------------------------------------------


def test_default_mode_is_single_stream_and_needs_no_lp_snapshot():
    decision = evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL))
    assert decision.lp_integrity_mode == LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM
    assert decision.lp_snapshot is None
    assert decision.verdict == POLICY_ALLOW
    assert decision.eligible
    valid, reason = validate_delivery_decision(decision)
    assert valid, reason
    assert delivery_block_reason(decision) is None


def test_single_stream_scam_likely_is_still_a_hard_block():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY))
    assert decision.verdict == POLICY_HARD_BLOCK
    assert BLOCK_SCAM_LIKELY in decision.final_block_reasons
    assert not decision.compose_allowed
    assert not decision.transport_allowed
    assert not decision.telegram_transport_allowed
    assert not decision.discord_transport_allowed


def test_single_stream_keeps_independent_existing_blockers():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL),
        existing_block_reasons=("RISK_HIGH",))
    assert decision.verdict == POLICY_HARD_BLOCK
    assert "RISK_HIGH" in decision.final_block_reasons


@pytest.mark.parametrize("legacy_reason", sorted(LEGACY_LP_BLOCK_REASONS))
def test_single_stream_ignores_every_legacy_lp_reason_code(legacy_reason):
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL),
        existing_block_reasons=(legacy_reason,))
    assert decision.verdict == POLICY_ALLOW
    assert decision.eligible
    assert legacy_reason not in decision.final_block_reasons
    assert legacy_reason in decision.legacy_lp_reasons_ignored
    valid, reason = validate_delivery_decision(decision)
    assert valid, reason


def test_single_stream_never_produces_the_lp_and_fee_composite_block():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        existing_block_reasons=(LP_AND_FEE_COMPOSITE_BLOCK, "RISK_HIGH"))
    assert LP_AND_FEE_COMPOSITE_BLOCK not in decision.final_block_reasons
    assert LP_AND_FEE_COMPOSITE_BLOCK in decision.legacy_lp_reasons_ignored
    assert BLOCK_SCAM_LIKELY in decision.final_block_reasons
    assert "RISK_HIGH" in decision.final_block_reasons


def test_single_stream_refuses_a_supplied_lp_snapshot():
    with pytest.raises(ValueError):
        evaluate_delivery_safety(
            fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL), lp_snapshot=_lp())


def test_single_stream_decision_with_forged_lp_reason_fails_validation():
    good = evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL))
    forged = replace(
        good, final_block_reasons=("LP_INTEGRITY_FAIL",), verdict=POLICY_HARD_BLOCK,
        eligible=False, compose_allowed=False, reservation_allowed=False,
        ledger_mutation_allowed=False, transport_allowed=False,
        telegram_transport_allowed=False)
    from PHX2.free_tier_producer.scam_policy import seal_delivery_decision
    forged = seal_delivery_decision(forged)
    assert validate_delivery_decision(forged) == (
        False, SECURITY_DECISION_PROOF_INCONSISTENT)


def test_single_stream_display_shows_disabled_never_pass():
    decision = evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL))
    lines = format_security_lines(decision)
    assert "LP Integrity: DISABLED" in lines
    assert not any("LP Integrity: PASS" in line for line in lines)


# ---------------------------------------------------------------------------
# Historical two-stream mode (explicit, non-default; offline analysis only)
# ---------------------------------------------------------------------------


def test_scam_likely_and_lp_pass_is_an_independent_fee_hard_block():
    decision = _two_stream(_fee(PHX1_FEE_GATE_SCAM_LIKELY), _lp())
    assert decision.fee_snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    assert decision.lp_snapshot.lp_integrity == LP_INTEGRITY_PASS
    assert decision.verdict == POLICY_HARD_BLOCK
    assert BLOCK_SCAM_LIKELY in decision.final_block_reasons
    assert not decision.compose_allowed
    assert not decision.transport_allowed
    assert not decision.telegram_transport_allowed
    assert not decision.discord_transport_allowed


def test_lp_fail_and_fee_pass_is_an_independent_lp_hard_block():
    removal = _event(REMOVE_LIQUIDITY, signature="remove", slot=101)
    decision = _two_stream(_fee(PHX1_FEE_GATE_NORMAL), _lp(removal))
    assert decision.lp_snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert UNEXPLAINED_LIQUIDITY_REMOVAL in decision.lp_reason_family
    assert "LP_INTEGRITY_FAIL" in decision.final_block_reasons
    assert decision.verdict == POLICY_HARD_BLOCK


def test_scam_and_lp_fail_retain_both_reason_families_and_composite_code():
    removal = _event(REMOVE_LIQUIDITY, signature="remove", slot=101)
    decision = _two_stream(
        _fee(PHX1_FEE_GATE_SCAM_LIKELY), _lp(removal),
        existing_block_reasons=("RISK_HIGH",))
    assert BLOCK_SCAM_LIKELY in decision.final_block_reasons
    assert "LP_INTEGRITY_FAIL" in decision.final_block_reasons
    assert LP_AND_FEE_COMPOSITE_BLOCK in decision.final_block_reasons
    assert "RISK_HIGH" in decision.final_block_reasons
    assert "bribes_starved" in decision.fee_reason_family
    assert UNEXPLAINED_LIQUIDITY_REMOVAL in decision.lp_reason_family


def test_suspicious_and_proximity_warn_preserve_phx1_nonblocking_behavior():
    prior = _event(ADD_LIQUIDITY, signature="prior", slot=99)
    decision = _two_stream(_fee(PHX1_FEE_GATE_SUSPICIOUS), _lp(prior))
    assert decision.fee_snapshot.fee_gate_label == PHX1_FEE_GATE_SUSPICIOUS
    assert decision.lp_snapshot.lp_integrity == LP_INTEGRITY_WARN
    assert decision.verdict == POLICY_ALLOW
    assert decision.eligible


def test_suspicious_with_proven_severe_secondary_manipulation_blocks_via_lp():
    secondary = _event(ADD_LIQUIDITY, signature="secondary", slot=101, pool=SECONDARY)
    decision = _two_stream(_fee(PHX1_FEE_GATE_SUSPICIOUS), _lp(secondary))
    assert SECONDARY_POOL_MANIPULATION_PROVEN in decision.lp_reason_family
    assert decision.lp_snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert decision.verdict == POLICY_HARD_BLOCK


def test_unknown_canonical_and_missing_verifier_evidence_fail_closed():
    identity = MigrationLiquidityIdentity(
        candidate_mint=MINT, pool=POOL, quote_mint=WSOL,
        migration_signature="migration", migration_slot=100,
        migration_timestamp_utc=AT, provider_pool=POOL)
    unknown = classify_liquidity_integrity(identity, (), now_utc=AT)
    decision = _two_stream(_fee(PHX1_FEE_GATE_NORMAL), unknown)
    assert unknown.lp_integrity == LP_INTEGRITY_UNKNOWN
    assert CANONICAL_POOL_PROOF_REQUIRED in decision.final_block_reasons
    assert decision.verdict == POLICY_HARD_BLOCK


def test_two_stream_mode_requires_an_lp_snapshot():
    with pytest.raises(ValueError):
        evaluate_delivery_safety(
            fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL),
            lp_integrity_mode=LP_INTEGRITY_MODE_TWO_STREAM)


def test_forged_fee_or_composite_proof_fails_closed():
    good = _two_stream(_fee(PHX1_FEE_GATE_NORMAL), _lp())
    forged_fee = replace(good.fee_snapshot, fee_gate_label=PHX1_FEE_GATE_SCAM_LIKELY)
    decision = _two_stream(forged_fee, good.lp_snapshot)
    assert BLOCK_PROOF_INCONSISTENT in decision.final_block_reasons
    forged_decision = replace(good, eligible=False)
    assert validate_delivery_decision(forged_decision) == (
        False, SECURITY_DECISION_PROOF_INCONSISTENT)
    assert delivery_block_reason(forged_decision) == SECURITY_DECISION_PROOF_INCONSISTENT


def test_cross_mint_fee_and_lp_evidence_cannot_be_rebound_into_one_decision():
    fee = _fee(PHX1_FEE_GATE_NORMAL)
    mismatched_lp = seal_lp_snapshot(replace(
        _lp(), candidate_mint="DifferentMint111111111111111111111111111pump",
        proof_digest=""))
    decision = _two_stream(fee, mismatched_lp)
    assert SECURITY_DECISION_PROOF_INCONSISTENT in decision.final_block_reasons
    assert decision.verdict == POLICY_HARD_BLOCK


# ---------------------------------------------------------------------------
# Engine enforcement (both modes stop before market/compose/reserve/transport)
# ---------------------------------------------------------------------------


class NeverSidecar:
    def resolve(self, *args, **kwargs):
        raise AssertionError("blocked_candidate_must_not_reach_market_or_delivery")


def _assert_blocked_before_everything(decision):
    result = producer_session.sess.run_cap1_candidates(
        [{"token_mint": MINT, "security_decision": decision}],
        sidecar=NeverSidecar(), ath_transport=None, ath_endpoint_secret=None,
        now_utc=None, now_seconds=None, now_iso_fn=lambda: AT,
        sleep_fn=lambda _: None, ledger=object(), guard=object(), authorization=object(),
        created_at_utc=AT,
    )
    record = result["per_candidate"][0]
    assert result["sent_attempt"] is None and result["eligible_candidate"] is None
    assert record["compose_attempted"] is False
    assert record["reservation_attempted"] is False
    assert record["active_ledger_mutated"] is False
    assert record["discord_transport_attempted"] is False
    assert record["telegram_transport_attempted"] is False
    assert record["delivery_transport_attempted"] is False


def test_blocked_candidate_stops_before_market_tier_compose_reserve_ledger_and_transport():
    _assert_blocked_before_everything(
        evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY)))


@pytest.mark.parametrize("blocked_kind", ("LP_FAIL", "COMPOSITE"))
def test_legacy_lp_and_composite_blocks_stop_before_telegram_compose_or_attempt(blocked_kind):
    removal = _event(REMOVE_LIQUIDITY, signature="remove", slot=101)
    fee_label = (
        PHX1_FEE_GATE_SCAM_LIKELY
        if blocked_kind == "COMPOSITE"
        else PHX1_FEE_GATE_NORMAL
    )
    _assert_blocked_before_everything(
        _two_stream(_fee(fee_label), _lp(removal)))


def test_second_pre_reservation_enforcement_location_rejects_same_blocked_proof():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY))
    result = producer_session.cs.compose_and_maybe_send(
        object(), ath_transport=None, ath_endpoint_secret=None,
        now_utc=None, now_seconds=None, ledger=object(), guard=object(),
        authorization=object(), created_at_utc=AT,
        activation_proof={"eligible": True}, security_decision=decision)
    assert result["compose_decision"] is None
    assert result["eligible"] is False
    assert result["send_result"] is None
    assert BLOCK_SCAM_LIKELY in result["compose_reason"]


def test_mismatched_display_security_snapshot_blocks_before_compose_and_reserve(monkeypatch):
    allowed = evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL))
    different = evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_SUSPICIOUS))
    monkeypatch.setattr(
        producer_session.cs, "compose_no_send_dispatch_deduped",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("mismatched security reached composer")),
    )
    result = producer_session.cs.compose_and_maybe_send(
        object(), ath_transport=None, ath_endpoint_secret=None,
        now_utc=None, now_seconds=None, ledger=object(), guard=object(),
        authorization=object(), created_at_utc=AT,
        activation_proof={"eligible": True}, security_decision=allowed,
        delivery_context={"security_decision": different},
    )
    assert result["compose_reason"] == SECURITY_DECISION_PROOF_INCONSISTENT
    assert result["deduped"] is None and result["send_result"] is None
    assert result["eligible"] is False
