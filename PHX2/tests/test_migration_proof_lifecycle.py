"""Immutable migration proof vs live LP monitoring (Part 3).

The sealed proof is historical fact: it must survive restart, the 300s
verifier-staleness window, and rolling-buffer eviction.  The verifier stream
stays responsible for ongoing monitoring, and contradictory LIVE evidence
(removals, impossible reconciliation, provider mismatch, secondary-pool
manipulation) must still hard-block.
"""

from dataclasses import replace

from PHX2.free_tier_producer.liquidity_integrity import (
    ADD_LIQUIDITY,
    CANONICAL_POOL_UNPROVEN,
    CANONICAL_SOURCE_SEALED_PROOF,
    CANONICAL_SOURCE_STREAM,
    CREATE_POOL,
    LP_INTEGRITY_FAIL,
    LP_INTEGRITY_PASS,
    LP_INTEGRITY_UNKNOWN,
    LP_INTEGRITY_WARN,
    REMOVE_LIQUIDITY,
    UNEXPLAINED_LIQUIDITY_REMOVAL,
    VERIFIER_EVIDENCE_STALE,
    LiquidityEvent,
    LiquidityIntegrityConfig,
    LiquidityIntegrityIndex,
    MigrationLiquidityIdentity,
    b58encode,
    classify_liquidity_integrity,
    validate_lp_snapshot,
)
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_PROOF_SOURCE,
    MIGRATION_PROOF_VERSION,
    PUMPFUN_PROGRAM_ID,
    MigrationProofSnapshot,
    migration_proof_matches_identity,
    seal_migration_proof,
)
from PHX2.free_tier_producer.scam_policy import (
    CANONICAL_POOL_PROOF_REQUIRED,
    LP_INTEGRITY_UNKNOWN_REASON,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID


WSOL = "So11111111111111111111111111111111111111112"
BASE = b58encode(bytes(range(1, 33)))
POOL = b58encode(bytes(range(33, 65)))
OTHER = b58encode(bytes(range(65, 97)))
SIGNATURE = "migration_sig"
AT = "2026-07-16T12:00:00Z"
SOON = "2026-07-16T12:00:10Z"
TWO_HOURS_LATER = "2026-07-16T14:00:10Z"
SLOT = 100


def _proof(*, mint=BASE, pool=POOL, quote=WSOL, signature=SIGNATURE):
    return seal_migration_proof(MigrationProofSnapshot(
        proof_version=MIGRATION_PROOF_VERSION,
        proof_source=MIGRATION_PROOF_SOURCE,
        candidate_mint=mint,
        pool=pool,
        base_mint=mint,
        quote_mint=quote,
        base_vault="base_vault",
        quote_vault="quote_vault",
        migration_authority="migration_authority",
        migration_signature=signature,
        migration_slot=SLOT,
        outer_instruction_index=0,
        inner_instruction_index=0,
        flattened_instruction_index=1,
        pumpfun_program_id=PUMPFUN_PROGRAM_ID,
        pumpswap_program_id=PUMPSWAP_PROGRAM_ID,
        canonical_pda_valid=True,
        pool_creation_index_arg=0,
        vault_derivation_valid=True,
        vault_ownership_valid=True,
        quote_deposit_raw=85_000_000_000,
        quote_deposit_decimals=9,
        quote_deposit_sol="85",
        base_deposit_raw=206_900_000_000_000,
        base_deposit_decimals=6,
        min_quote_deposit_sol="50",
        mint_suffix_consistent=True,
        observed_at_utc=AT,
    ))


def _identity():
    return MigrationLiquidityIdentity(
        candidate_mint=BASE, pool=POOL, quote_mint=WSOL,
        migration_signature=SIGNATURE, migration_slot=SLOT,
        migration_timestamp_utc=AT, provider_pool=POOL)


def _event(kind, *, sig, slot, pool=POOL, base=BASE, timestamp=AT,
           context="MIGRATION_CPI", proven=True):
    positive = kind != REMOVE_LIQUIDITY
    return LiquidityEvent(
        kind=kind, program_id=PUMPSWAP_PROGRAM_ID, discriminator_hex="00" * 8,
        pool=pool, base_mint=base, quote_mint=WSOL, pair=f"{base}/{WSOL}",
        base_vault="base_vault", quote_vault="quote_vault", pool_authority=pool,
        signer="sig_signer", fee_payer="sig_signer", authority="sig_signer",
        transaction_signature=sig, event_index=0, slot=slot, timestamp_utc=timestamp,
        base_amount=10, quote_amount=20,
        base_reserve_delta=(10 if positive else -10),
        quote_reserve_delta=(20 if positive else -20),
        pool_pda_valid=(True if kind == CREATE_POOL else None), mint_pair_valid=True,
        vault_derivation_valid=(True if kind == CREATE_POOL else None),
        vault_ownership_valid=True, pool_authority_valid=True,
        canonical_semantics_valid=(kind == CREATE_POOL),
        creation_context=(context if kind == CREATE_POOL else None),
        migration_cpi_proven=(proven if kind == CREATE_POOL else False))


def test_sealed_proof_keeps_canonical_proven_with_no_live_events():
    snapshot = classify_liquidity_integrity(
        _identity(), (), now_utc=SOON, sealed_proof=_proof())
    assert snapshot.canonical_pool_proven is True
    assert snapshot.canonical_pool_source == CANONICAL_SOURCE_SEALED_PROOF
    assert snapshot.canonical_migration_liquidity_signature == SIGNATURE
    assert CANONICAL_POOL_UNPROVEN not in snapshot.lp_integrity_reasons
    assert snapshot.lp_integrity == LP_INTEGRITY_WARN
    assert snapshot.eligible and not snapshot.hard_block
    assert snapshot.sealed_migration_proof_digest
    assert validate_lp_snapshot(snapshot) == (True, None)


def test_proof_survives_the_300s_staleness_window():
    create = _event(CREATE_POOL, sig=SIGNATURE, slot=SLOT)
    with_proof = classify_liquidity_integrity(
        _identity(), (create,), now_utc=TWO_HOURS_LATER, sealed_proof=_proof())
    without_proof = classify_liquidity_integrity(
        _identity(), (create,), now_utc=TWO_HOURS_LATER)
    assert VERIFIER_EVIDENCE_STALE not in with_proof.lp_integrity_reasons
    assert with_proof.lp_integrity == LP_INTEGRITY_PASS
    assert with_proof.evidence_freshness == "STALE"      # true age still shown
    # Legacy behavior without a sealed proof stays fail-closed.
    assert VERIFIER_EVIDENCE_STALE in without_proof.lp_integrity_reasons
    assert without_proof.lp_integrity == LP_INTEGRITY_UNKNOWN
    assert without_proof.hard_block


def test_proof_survives_rolling_buffer_eviction():
    index = LiquidityIntegrityIndex(LiquidityIntegrityConfig(max_buffer_events=2))
    assert index.register_migration_proof(_proof())
    create = _event(CREATE_POOL, sig=SIGNATURE, slot=SLOT)
    assert index.record(create)
    for position in range(3):        # unrelated churn evicts the create event
        index.record(_event(ADD_LIQUIDITY, sig=f"noise{position}",
                            slot=SLOT + 1 + position, pool=OTHER, base=OTHER))
    assert all(event.transaction_signature != SIGNATURE
               for event in index.events_for(_identity()))
    snapshot = index.snapshot(_identity(), now_utc=SOON)
    assert snapshot.canonical_pool_proven is True
    assert snapshot.canonical_pool_source == CANONICAL_SOURCE_SEALED_PROOF
    assert not snapshot.hard_block


def test_live_lp_removal_still_hard_blocks_despite_the_proof():
    removal = _event(REMOVE_LIQUIDITY, sig="pull", slot=SLOT + 5, timestamp=SOON)
    snapshot = classify_liquidity_integrity(
        _identity(), (removal,), now_utc=SOON, sealed_proof=_proof())
    assert snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert UNEXPLAINED_LIQUIDITY_REMOVAL in snapshot.lp_integrity_reasons
    assert snapshot.hard_block


def test_live_canonical_event_takes_precedence_over_the_proof():
    create = _event(CREATE_POOL, sig=SIGNATURE, slot=SLOT)
    snapshot = classify_liquidity_integrity(
        _identity(), (create,), now_utc=SOON, sealed_proof=_proof())
    assert snapshot.canonical_pool_source == CANONICAL_SOURCE_STREAM
    assert snapshot.sealed_migration_proof_digest      # linkage still recorded
    assert snapshot.lp_integrity == LP_INTEGRITY_PASS


def test_mismatched_or_tampered_proof_fails_closed():
    wrong_pool = _proof(pool=OTHER)
    assert not migration_proof_matches_identity(wrong_pool, _identity())
    snapshot = classify_liquidity_integrity(
        _identity(), (), now_utc=SOON, sealed_proof=wrong_pool)
    assert snapshot.canonical_pool_proven is False
    assert CANONICAL_POOL_UNPROVEN in snapshot.lp_integrity_reasons
    tampered = replace(_proof(), quote_deposit_raw=1)
    snapshot = classify_liquidity_integrity(
        _identity(), (), now_utc=SOON, sealed_proof=tampered)
    assert snapshot.canonical_pool_proven is False


def test_register_migration_proof_restores_identity_after_restart():
    index = LiquidityIntegrityIndex()
    assert index.identity_for(BASE) is None
    assert index.register_migration_proof(_proof())
    identity = index.identity_for(BASE)
    assert identity is not None
    assert identity.pool == POOL
    assert identity.migration_signature == SIGNATURE
    assert index.stats()["verifier_sealed_migration_proofs"] == 1
    # First proof wins; a conflicting later proof never rebinds the mint.
    assert not index.register_migration_proof(_proof(signature="other_sig"))
    assert index.identity_for(BASE).migration_signature == SIGNATURE


def test_composite_policy_drops_lp_blocks_for_proof_backed_candidates():
    from PHX2.free_tier_producer.phx1_fee_gate import FeeEvidenceIndex
    from PHX2.free_tier_producer.scam_policy import (
        LP_INTEGRITY_MODE_TWO_STREAM,
        evaluate_delivery_safety,
    )
    from decimal import Decimal

    snapshot = classify_liquidity_integrity(
        _identity(), (), now_utc=SOON, sealed_proof=_proof())
    fee_snapshot = FeeEvidenceIndex().snapshot(
        BASE, now_epoch=1_800_000_000, max_age_seconds=Decimal(300))
    # Historical two-stream composite (explicit non-default mode): the sealed
    # proof already satisfied the canonical requirement there.  Single-stream
    # production never evaluates these LP blocks at all.
    decision = evaluate_delivery_safety(
        fee_snapshot=fee_snapshot, lp_snapshot=snapshot,
        lp_integrity_mode=LP_INTEGRITY_MODE_TWO_STREAM)
    assert CANONICAL_POOL_PROOF_REQUIRED not in decision.final_block_reasons
    assert LP_INTEGRITY_UNKNOWN_REASON not in decision.final_block_reasons
    single_stream = evaluate_delivery_safety(fee_snapshot=fee_snapshot)
    assert CANONICAL_POOL_PROOF_REQUIRED not in single_stream.final_block_reasons
    assert LP_INTEGRITY_UNKNOWN_REASON not in single_stream.final_block_reasons
