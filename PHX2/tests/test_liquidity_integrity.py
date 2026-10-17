from dataclasses import replace
import struct
from types import SimpleNamespace

from PHX2.free_tier_producer.liquidity_integrity import (
    ADD_LIQUIDITY,
    BUY,
    CANONICAL_POOL_UNPROVEN,
    CREATE_POOL,
    CREATE_POOL_DISCRIMINATOR,
    DEPOSIT_DISCRIMINATOR,
    IMPOSSIBLE_RESERVE_RECONCILIATION,
    INVALID_POOL_AUTHORITY,
    INVALID_VAULT_OWNERSHIP,
    LP_INTEGRITY_FAIL,
    LP_INTEGRITY_PASS,
    LP_INTEGRITY_UNKNOWN,
    LP_INTEGRITY_WARN,
    LP_PROOF_INCONSISTENT,
    MULTIPLE_ADDS_NEAR_MIGRATION,
    PROVIDER_POOL_MISMATCH,
    REMOVE_LIQUIDITY,
    SECONDARY_POOL_MANIPULATION_PROVEN,
    SELL,
    UNEXPLAINED_LIQUIDITY_REMOVAL,
    WITHDRAW_DISCRIMINATOR,
    BUY_DISCRIMINATOR,
    SELL_DISCRIMINATOR,
    LiquidityEvent,
    LiquidityIntegrityConfig,
    LiquidityIntegrityIndex,
    MigrationLiquidityIdentity,
    b58decode,
    b58encode,
    classify_liquidity_integrity,
    decode_pumpswap_instruction,
    derive_associated_token_address,
    derive_pool_address,
    validate_lp_snapshot,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.free_tier_producer.liquidity_verifier import decode_liquidity_update


WSOL = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
BASE = b58encode(bytes(range(1, 33)))
CREATOR = b58encode(bytes(range(33, 65)))
OTHER = b58encode(bytes(range(65, 97)))
NOW = "2026-07-16T12:00:10Z"
AT = "2026-07-16T12:00:00Z"


def _create_instruction(*, quote_amount=1_000_000_000, corrupt_pool=False,
                        corrupt_vault=False, wrong_pair=False):
    index = 7
    quote = OTHER if wrong_pair else WSOL
    pool = derive_pool_address(index=index, creator=CREATOR, base_mint=BASE, quote_mint=quote)
    if corrupt_pool:
        pool = OTHER
    base_vault = derive_associated_token_address(
        owner=pool, token_program=TOKEN_PROGRAM, mint=BASE, associated_program=ATA_PROGRAM)
    quote_vault = derive_associated_token_address(
        owner=pool, token_program=TOKEN_PROGRAM, mint=quote, associated_program=ATA_PROGRAM)
    if corrupt_vault:
        base_vault = OTHER
    accounts = [
        pool, OTHER, CREATOR, BASE, quote, OTHER, OTHER, OTHER, OTHER,
        base_vault, quote_vault, "11111111111111111111111111111111",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", TOKEN_PROGRAM, TOKEN_PROGRAM,
        ATA_PROGRAM, OTHER, PUMPSWAP_PROGRAM_ID,
    ]
    data = CREATE_POOL_DISCRIMINATOR + struct.pack("<HQQ", index, 500_000, quote_amount)
    event = decode_pumpswap_instruction(
        program_id=PUMPSWAP_PROGRAM_ID,
        data=data,
        accounts=accounts,
        signer_keys=(CREATOR,),
        fee_payer=CREATOR,
        transaction_signature="create_sig",
        event_index=0,
        slot=100,
        timestamp_utc=AT,
        vault_owner_by_address={base_vault: pool, quote_vault: pool},
        reserve_delta_by_address={base_vault: 500_000, quote_vault: quote_amount},
    )
    return event


def _event(kind, *, sig, slot, pool, signer=CREATOR, base=BASE, quote=WSOL,
           base_delta=10, quote_delta=20, malformed=()):
    positive = kind != REMOVE_LIQUIDITY
    return LiquidityEvent(
        kind=kind, program_id=PUMPSWAP_PROGRAM_ID, discriminator_hex="00" * 8,
        pool=pool, base_mint=base, quote_mint=quote, pair=f"{base}/{quote}",
        base_vault="base_vault", quote_vault="quote_vault", pool_authority=pool,
        signer=signer, fee_payer=signer, authority=signer,
        transaction_signature=sig, event_index=0, slot=slot, timestamp_utc=AT,
        base_amount=abs(base_delta), quote_amount=abs(quote_delta),
        base_reserve_delta=(base_delta if positive else -abs(base_delta)),
        quote_reserve_delta=(quote_delta if positive else -abs(quote_delta)),
        pool_pda_valid=(True if kind == CREATE_POOL else None), mint_pair_valid=True,
        vault_derivation_valid=(True if kind == CREATE_POOL else None),
        vault_ownership_valid=True, pool_authority_valid=True,
        canonical_semantics_valid=(kind == CREATE_POOL),
        malformed_reasons=tuple(malformed))


def _identity(event, *, provider_pool=None):
    return MigrationLiquidityIdentity(
        candidate_mint=BASE, pool=event.pool, quote_mint=WSOL,
        migration_signature=event.transaction_signature, migration_slot=event.slot,
        migration_timestamp_utc=event.timestamp_utc,
        provider_pool=provider_pool if provider_pool is not None else event.pool)


def test_create_pool_is_proven_by_program_pda_vault_pair_and_reserve_deltas():
    event = _create_instruction(quote_amount=12_345)
    assert event.kind == CREATE_POOL
    assert event.quote_amount == 12_345
    assert event.canonical_semantics_valid
    assert event.pool_pda_valid and event.vault_derivation_valid


def test_84_like_amount_is_not_automatically_canonical():
    event = _create_instruction(quote_amount=84_990_000_000, corrupt_pool=True)
    assert event.quote_amount == 84_990_000_000
    assert not event.canonical_semantics_valid


def test_non_84_amount_remains_canonical_when_semantics_are_valid():
    assert _create_instruction(quote_amount=777).canonical_semantics_valid


def test_wrong_vault_and_wrong_pair_fail_closed():
    wrong_vault = _create_instruction(corrupt_vault=True)
    wrong_pair = _create_instruction(wrong_pair=True)
    assert INVALID_VAULT_OWNERSHIP in wrong_vault.malformed_reasons
    assert not wrong_pair.mint_pair_valid
    assert not wrong_vault.canonical_semantics_valid


def test_creator_signature_and_fixed_program_accounts_are_required_for_canonical_proof():
    valid = _create_instruction()
    accounts = [
        valid.pool, OTHER, CREATOR, BASE, WSOL, OTHER, OTHER, OTHER, OTHER,
        valid.base_vault, valid.quote_vault, "11111111111111111111111111111111",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", TOKEN_PROGRAM, TOKEN_PROGRAM,
        ATA_PROGRAM, OTHER, PUMPSWAP_PROGRAM_ID,
    ]
    kwargs = dict(
        program_id=PUMPSWAP_PROGRAM_ID,
        data=CREATE_POOL_DISCRIMINATOR + struct.pack("<HQQ", 7, 500_000, 1_000_000_000),
        accounts=accounts, fee_payer=CREATOR, transaction_signature="sig",
        event_index=0, slot=100, timestamp_utc=AT,
        vault_owner_by_address={valid.base_vault: valid.pool, valid.quote_vault: valid.pool},
        reserve_delta_by_address={valid.base_vault: 500_000, valid.quote_vault: 1_000_000_000},
    )
    unsigned = decode_pumpswap_instruction(signer_keys=(), **kwargs)
    bad_program_account = decode_pumpswap_instruction(
        signer_keys=(CREATOR,), **{**kwargs, "accounts": [*accounts[:17], OTHER]})
    assert not unsigned.pool_authority_valid and not unsigned.canonical_semantics_valid
    assert INVALID_POOL_AUTHORITY in unsigned.malformed_reasons
    assert "CREATE_POOL_FIXED_ACCOUNTS_INVALID" in bad_program_account.malformed_reasons
    assert not bad_program_account.canonical_semantics_valid


def test_buy_and_sell_can_never_be_confused_with_liquidity_changes():
    accounts = [OTHER] * 20
    buy = decode_pumpswap_instruction(
        program_id=PUMPSWAP_PROGRAM_ID, data=BUY_DISCRIMINATOR + b"\0" * 16,
        accounts=accounts, signer_keys=(), fee_payer=OTHER,
        transaction_signature="buy", event_index=0, slot=1, timestamp_utc=AT)
    sell = decode_pumpswap_instruction(
        program_id=PUMPSWAP_PROGRAM_ID, data=SELL_DISCRIMINATOR + b"\0" * 16,
        accounts=accounts, signer_keys=(), fee_payer=OTHER,
        transaction_signature="sell", event_index=0, slot=1, timestamp_utc=AT)
    assert buy.kind == BUY
    assert sell.kind == SELL
    assert buy.kind != ADD_LIQUIDITY and sell.kind != REMOVE_LIQUIDITY


def test_deposit_and_withdraw_decode_by_exact_discriminator():
    create = _create_instruction()
    accounts = [create.pool, OTHER, CREATOR, BASE, WSOL, OTHER, OTHER, OTHER, OTHER,
                "base_vault", "quote_vault", TOKEN_PROGRAM,
                "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", OTHER,
                PUMPSWAP_PROGRAM_ID]
    common = dict(
        program_id=PUMPSWAP_PROGRAM_ID, accounts=accounts, signer_keys=(CREATOR,),
        fee_payer=CREATOR, event_index=0, slot=101, timestamp_utc=AT,
        vault_owner_by_address={"base_vault": create.pool, "quote_vault": create.pool})
    add = decode_pumpswap_instruction(
        data=DEPOSIT_DISCRIMINATOR + struct.pack("<QQQ", 1, 2, 3),
        transaction_signature="add", reserve_delta_by_address={"base_vault": 2, "quote_vault": 3},
        **common)
    remove = decode_pumpswap_instruction(
        data=WITHDRAW_DISCRIMINATOR + struct.pack("<QQQ", 1, 2, 3),
        transaction_signature="remove", reserve_delta_by_address={"base_vault": -2, "quote_vault": -3},
        **common)
    assert add.kind == ADD_LIQUIDITY and add.base_amount == 2
    assert remove.kind == REMOVE_LIQUIDITY and remove.quote_amount == 3


def _yellowstone_create_update(*, discriminator=CREATE_POOL_DISCRIMINATOR):
    canonical = _create_instruction()
    account_values = [
        canonical.pool, OTHER, CREATOR, BASE, WSOL, OTHER, OTHER, OTHER, OTHER,
        canonical.base_vault, canonical.quote_vault,
        "11111111111111111111111111111111",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        TOKEN_PROGRAM, TOKEN_PROGRAM, ATA_PROGRAM, OTHER, PUMPSWAP_PROGRAM_ID,
    ]
    keys = []
    for value in [CREATOR, *account_values, PUMPSWAP_PROGRAM_ID]:
        if value not in keys:
            keys.append(value)
    account_indices = bytes(keys.index(value) for value in account_values)
    instruction = SimpleNamespace(
        program_id_index=keys.index(PUMPSWAP_PROGRAM_ID),
        accounts=account_indices,
        data=discriminator + struct.pack("<HQQ", 7, 500_000, 1_000_000_000),
    )
    message = SimpleNamespace(
        account_keys=[b58decode(value) for value in keys],
        instructions=[instruction], header=SimpleNamespace(num_required_signatures=1),
    )

    def balance(address, amount):
        return SimpleNamespace(
            account_index=keys.index(address), owner=canonical.pool,
            ui_token_amount=SimpleNamespace(amount=str(amount)))

    meta = SimpleNamespace(
        loaded_writable_addresses=[], loaded_readonly_addresses=[], inner_instructions=[],
        pre_token_balances=[balance(canonical.base_vault, 0), balance(canonical.quote_vault, 0)],
        post_token_balances=[
            balance(canonical.base_vault, 500_000),
            balance(canonical.quote_vault, 1_000_000_000),
        ],
    )
    info = SimpleNamespace(
        signature=bytes(range(64)), transaction=SimpleNamespace(message=message), meta=meta)
    return SimpleNamespace(transaction=SimpleNamespace(
        slot=100, transaction=info))


def test_yellowstone_adapter_yields_semantic_liquidity_but_drops_ordinary_swap():
    create_events = decode_liquidity_update(
        _yellowstone_create_update(), observed_at_utc=AT)
    buy_events = decode_liquidity_update(
        _yellowstone_create_update(discriminator=BUY_DISCRIMINATOR), observed_at_utc=AT)
    assert len(create_events) == 1
    assert create_events[0].kind == CREATE_POOL
    assert create_events[0].canonical_semantics_valid
    assert buy_events == ()


def test_pre_migration_add_is_retained_joined_and_proximity_only_warns():
    canonical = _create_instruction()
    prior = _event(ADD_LIQUIDITY, sig="prior", slot=98, pool=canonical.pool)
    index = LiquidityIntegrityIndex(LiquidityIntegrityConfig(max_buffer_events=8))
    assert index.record(prior)
    assert index.record(canonical)
    snapshot = index.snapshot(_identity(canonical), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_WARN
    assert snapshot.nearby_prior_add_count == 1
    assert MULTIPLE_ADDS_NEAR_MIGRATION in snapshot.lp_integrity_reasons
    assert not snapshot.hard_block


def test_normal_canonical_sequence_passes():
    canonical = _create_instruction()
    snapshot = classify_liquidity_integrity(
        _identity(canonical), (canonical,), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_PASS
    assert snapshot.canonical_pool_proven and snapshot.eligible


def test_missing_canonical_is_unknown_and_fail_closed():
    canonical = _create_instruction()
    snapshot = classify_liquidity_integrity(_identity(canonical), (), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_UNKNOWN
    assert CANONICAL_POOL_UNPROVEN in snapshot.lp_integrity_reasons
    assert snapshot.hard_block


def test_following_liquidity_removal_is_deterministic_fail():
    canonical = _create_instruction()
    removal = _event(REMOVE_LIQUIDITY, sig="remove", slot=101, pool=canonical.pool)
    snapshot = classify_liquidity_integrity(
        _identity(canonical), (canonical, removal), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert UNEXPLAINED_LIQUIDITY_REMOVAL in snapshot.lp_integrity_reasons


def test_impossible_reserve_direction_is_deterministic_fail():
    canonical = _create_instruction()
    malformed_add = replace(
        _event(ADD_LIQUIDITY, sig="bad-delta", slot=101, pool=canonical.pool),
        base_reserve_delta=-10)
    snapshot = classify_liquidity_integrity(
        _identity(canonical), (canonical, malformed_add), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert IMPOSSIBLE_RESERVE_RECONCILIATION in snapshot.lp_integrity_reasons


def test_slot_close_but_time_distant_add_is_not_a_proximity_warning():
    canonical = _create_instruction()
    distant = replace(
        _event(ADD_LIQUIDITY, sig="old", slot=99, pool=canonical.pool),
        timestamp_utc="2026-07-16T11:00:00Z")
    snapshot = classify_liquidity_integrity(
        _identity(canonical), (canonical, distant), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_PASS
    assert MULTIPLE_ADDS_NEAR_MIGRATION not in snapshot.lp_integrity_reasons


def test_secondary_pool_with_same_authority_and_add_is_proven_manipulation():
    canonical = _create_instruction()
    secondary = _event(ADD_LIQUIDITY, sig="secondary", slot=101, pool=OTHER)
    snapshot = classify_liquidity_integrity(
        _identity(canonical), (canonical, secondary), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert SECONDARY_POOL_MANIPULATION_PROVEN in snapshot.lp_integrity_reasons
    assert snapshot.secondary_pool_addresses == (OTHER,)


def test_provider_pool_mismatch_fails_and_retains_reason():
    canonical = _create_instruction()
    snapshot = classify_liquidity_integrity(
        _identity(canonical, provider_pool=OTHER), (canonical,), now_utc=NOW)
    assert snapshot.lp_integrity == LP_INTEGRITY_FAIL
    assert PROVIDER_POOL_MISMATCH in snapshot.lp_integrity_reasons


def test_bounded_eviction_dedupe_and_unrelated_mint_no_cross_join():
    canonical = _create_instruction()
    index = LiquidityIntegrityIndex(LiquidityIntegrityConfig(max_buffer_events=2))
    assert index.record(canonical)
    assert not index.record(canonical)
    index.record(_event(ADD_LIQUIDITY, sig="u1", slot=101, pool=OTHER, base=OTHER))
    index.record(_event(ADD_LIQUIDITY, sig="u2", slot=102, pool=OTHER, base=OTHER))
    assert index.stats()["verifier_buffer_events"] == 2
    assert all(event.base_mint != OTHER for event in index.events_for(_identity(canonical)))


def test_forged_lp_snapshot_proof_is_rejected():
    canonical = _create_instruction()
    snapshot = classify_liquidity_integrity(
        _identity(canonical), (canonical,), now_utc=NOW)
    forged = replace(snapshot, canonical_pool_proven=False)
    assert validate_lp_snapshot(forged) == (False, LP_PROOF_INCONSISTENT)
