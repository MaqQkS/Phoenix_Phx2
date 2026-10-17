"""CPI-aware pool-authority semantics (Part 2 of the admission repair).

The investigated defect: ``pool_authority_valid`` required the pool creator to
be a transaction-header signer, which is impossible for genuine pump.fun
migrations (the pool is created via ``invoke_signed`` by the migration
authority PDA), so every real migration was hard-blocked with
INVALID_POOL_AUTHORITY while direct signer-created (scam-shaped) pools were
the only ones able to prove canonical.  These tests pin the corrected,
context-aware rule at both the pure-decoder and the Yellowstone-adapter level.
"""

import struct
from types import SimpleNamespace

from PHX2.free_tier_producer.liquidity_integrity import (
    ADD_LIQUIDITY,
    CREATE_POOL,
    CREATE_POOL_DISCRIMINATOR,
    CREATION_CONTEXT_CPI,
    CREATION_CONTEXT_MIGRATION_CPI,
    CREATION_CONTEXT_TOP_LEVEL,
    DEPOSIT_DISCRIMINATOR,
    INVALID_POOL_AUTHORITY,
    WITHDRAW_DISCRIMINATOR,
    REMOVE_LIQUIDITY,
    b58encode,
    decode_pumpswap_instruction,
    derive_associated_token_address,
    derive_pool_address,
)
from PHX2.free_tier_producer.liquidity_verifier import decode_liquidity_update
from PHX2.free_tier_producer.migration_admission import (
    PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_PROGRAM_ID,
)
from PHX2.free_tier_producer.paid_grpc_source import _base58_decode
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID


WSOL = "So11111111111111111111111111111111111111112"
SYSTEM = "11111111111111111111111111111111"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
BASE = b58encode(bytes(range(1, 33)))
CREATOR = b58encode(bytes(range(33, 65)))        # PDA authority, NOT a signer
CRANKER = b58encode(bytes(range(65, 97)))        # fee payer + sole signer
ROUTER = b58encode(bytes(range(97, 129)))
OTHER = b58encode(bytes(range(129, 161)))
AT = "2026-07-16T12:00:00Z"
POOL_INDEX = 7


def _canonical_layout():
    pool = derive_pool_address(
        index=POOL_INDEX, creator=CREATOR, base_mint=BASE, quote_mint=WSOL)
    base_vault = derive_associated_token_address(
        owner=pool, token_program=TOKEN_PROGRAM, mint=BASE,
        associated_program=ATA_PROGRAM)
    quote_vault = derive_associated_token_address(
        owner=pool, token_program=TOKEN_PROGRAM, mint=WSOL,
        associated_program=ATA_PROGRAM)
    accounts = [
        pool, OTHER, CREATOR, BASE, WSOL, OTHER, OTHER, OTHER, OTHER,
        base_vault, quote_vault, SYSTEM, TOKEN_2022, TOKEN_PROGRAM,
        TOKEN_PROGRAM, ATA_PROGRAM, OTHER, PUMPSWAP_PROGRAM_ID,
    ]
    return pool, base_vault, quote_vault, accounts


def _decode_create(*, signer_keys, creation_context=None, migration_cpi_proven=False,
                   corrupt_pool=False):
    pool, base_vault, quote_vault, accounts = _canonical_layout()
    if corrupt_pool:
        accounts[0] = OTHER
        pool = OTHER
    return decode_pumpswap_instruction(
        program_id=PUMPSWAP_PROGRAM_ID,
        data=bytes(CREATE_POOL_DISCRIMINATOR) + struct.pack(
            "<HQQ", POOL_INDEX, 500_000, 85_000_000_000),
        accounts=accounts,
        signer_keys=signer_keys,
        fee_payer=CRANKER,
        transaction_signature="create_sig",
        event_index=0,
        slot=100,
        timestamp_utc=AT,
        vault_owner_by_address={base_vault: pool, quote_vault: pool},
        reserve_delta_by_address={base_vault: 500_000, quote_vault: 85_000_000_000},
        creation_context=creation_context,
        migration_cpi_proven=migration_cpi_proven,
    )


def test_proven_migration_cpi_authority_is_valid_without_header_signature():
    event = _decode_create(
        signer_keys=(CRANKER,),
        creation_context=CREATION_CONTEXT_MIGRATION_CPI,
        migration_cpi_proven=True)
    assert event.kind == CREATE_POOL
    assert event.pool_authority_valid is True
    assert event.canonical_semantics_valid is True
    assert INVALID_POOL_AUTHORITY not in event.malformed_reasons
    assert event.creation_context == CREATION_CONTEXT_MIGRATION_CPI
    assert event.migration_cpi_proven is True


def test_migration_cpi_authority_still_requires_canonical_pda():
    event = _decode_create(
        signer_keys=(CRANKER,),
        creation_context=CREATION_CONTEXT_MIGRATION_CPI,
        migration_cpi_proven=True,
        corrupt_pool=True)
    assert event.pool_pda_valid is False
    assert event.pool_authority_valid is False
    assert not event.canonical_semantics_valid


def test_direct_creation_keeps_the_header_signer_requirement():
    unsigned = _decode_create(signer_keys=(CRANKER,))
    signed = _decode_create(signer_keys=(CREATOR,))
    assert unsigned.pool_authority_valid is False
    assert INVALID_POOL_AUTHORITY in unsigned.malformed_reasons
    assert signed.pool_authority_valid is True
    assert signed.canonical_semantics_valid is True


def test_unproven_cpi_context_does_not_relax_the_signer_rule():
    event = _decode_create(
        signer_keys=(CRANKER,),
        creation_context=CREATION_CONTEXT_CPI,
        migration_cpi_proven=False)
    assert event.pool_authority_valid is False
    assert INVALID_POOL_AUTHORITY in event.malformed_reasons


def test_liquidity_add_remove_signer_rule_is_untouched_by_migration_flags():
    pool, base_vault, quote_vault, _ = _canonical_layout()
    accounts = [pool, OTHER, CREATOR, BASE, WSOL, OTHER, OTHER, OTHER, OTHER,
                base_vault, quote_vault, TOKEN_PROGRAM, TOKEN_2022, OTHER,
                PUMPSWAP_PROGRAM_ID]
    common = dict(
        program_id=PUMPSWAP_PROGRAM_ID, accounts=accounts,
        signer_keys=(CRANKER,), fee_payer=CRANKER, event_index=0, slot=101,
        timestamp_utc=AT,
        vault_owner_by_address={base_vault: pool, quote_vault: pool},
        creation_context=CREATION_CONTEXT_MIGRATION_CPI,
        migration_cpi_proven=True,
    )
    add = decode_pumpswap_instruction(
        data=bytes(DEPOSIT_DISCRIMINATOR) + struct.pack("<QQQ", 1, 2, 3),
        transaction_signature="add",
        reserve_delta_by_address={base_vault: 2, quote_vault: 3}, **common)
    remove = decode_pumpswap_instruction(
        data=bytes(WITHDRAW_DISCRIMINATOR) + struct.pack("<QQQ", 1, 2, 3),
        transaction_signature="remove",
        reserve_delta_by_address={base_vault: -2, quote_vault: -3}, **common)
    assert add.kind == ADD_LIQUIDITY and add.pool_authority_valid is False
    assert remove.kind == REMOVE_LIQUIDITY and remove.pool_authority_valid is False


# ---------------------------------------------------------------------------
# Yellowstone adapter: CPI context detection end to end
# ---------------------------------------------------------------------------


def _yellowstone_cpi_update(*, shape="MIGRATION", stack_heights=True):
    pool, base_vault, quote_vault, accounts = _canonical_layout()
    key_texts = [CRANKER]
    for value in [*accounts, PUMPSWAP_PROGRAM_ID, PUMPFUN_PROGRAM_ID, ROUTER]:
        if value not in key_texts:
            key_texts.append(value)
    key_index = {value: position for position, value in enumerate(key_texts)}
    create_data = bytes(CREATE_POOL_DISCRIMINATOR) + struct.pack(
        "<HQQ", POOL_INDEX, 500_000, 85_000_000_000)
    create_accounts = bytes(key_index[value] for value in accounts)

    def _instruction(program, data, accounts_bytes=b"", stack_height=None):
        namespace = SimpleNamespace(
            program_id_index=key_index[program], accounts=accounts_bytes, data=data)
        if stack_height is not None:
            namespace.stack_height = stack_height
        return namespace

    migrate_data = bytes(PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR)
    inner = []
    if shape == "MIGRATION":
        top_level = [_instruction(PUMPFUN_PROGRAM_ID, migrate_data)]
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_data, create_accounts,
            stack_height=2 if stack_heights else None))
    elif shape == "CPI_NO_PUMPFUN":
        top_level = [_instruction(ROUTER, b"\x01router")]
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_data, create_accounts,
            stack_height=2 if stack_heights else None))
    elif shape == "WRAPPED":
        top_level = [_instruction(ROUTER, b"\x01router")]
        inner.append(_instruction(
            PUMPFUN_PROGRAM_ID, migrate_data,
            stack_height=2 if stack_heights else None))
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_data, create_accounts,
            stack_height=3 if stack_heights else None))
    else:
        top_level = [_instruction(PUMPSWAP_PROGRAM_ID, create_data, create_accounts)]

    message = SimpleNamespace(
        account_keys=[_base58_decode(value) for value in key_texts],
        instructions=top_level,
        header=SimpleNamespace(num_required_signatures=1),
    )

    def _balance(address, amount):
        return SimpleNamespace(
            account_index=key_index[address], owner=pool,
            ui_token_amount=SimpleNamespace(amount=str(amount)))

    meta = SimpleNamespace(
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        inner_instructions=([SimpleNamespace(index=0, instructions=inner)]
                            if inner else []),
        pre_token_balances=[_balance(base_vault, 0), _balance(quote_vault, 0)],
        post_token_balances=[
            _balance(base_vault, 500_000),
            _balance(quote_vault, 85_000_000_000),
        ],
    )
    info = SimpleNamespace(
        signature=bytes(range(64)),
        transaction=SimpleNamespace(message=message), meta=meta)
    return SimpleNamespace(transaction=SimpleNamespace(slot=100, transaction=info))


def test_adapter_marks_migration_cpi_create_as_canonical_without_signer():
    events = decode_liquidity_update(_yellowstone_cpi_update(), observed_at_utc=AT)
    assert len(events) == 1
    event = events[0]
    assert event.kind == CREATE_POOL
    assert event.creation_context == CREATION_CONTEXT_MIGRATION_CPI
    assert event.migration_cpi_proven is True
    assert event.pool_authority_valid is True
    assert event.canonical_semantics_valid is True
    assert event.malformed_reasons == ()
    assert event.signer is None                      # authority is NOT a signer


def test_adapter_keeps_unproven_cpi_create_fail_closed():
    events = decode_liquidity_update(
        _yellowstone_cpi_update(shape="CPI_NO_PUMPFUN"), observed_at_utc=AT)
    assert len(events) == 1
    event = events[0]
    assert event.creation_context == CREATION_CONTEXT_CPI
    assert event.migration_cpi_proven is False
    assert event.pool_authority_valid is False
    assert INVALID_POOL_AUTHORITY in event.malformed_reasons


def test_adapter_proves_wrapped_migration_only_with_stack_heights():
    proven = decode_liquidity_update(
        _yellowstone_cpi_update(shape="WRAPPED"), observed_at_utc=AT)
    unproven = decode_liquidity_update(
        _yellowstone_cpi_update(shape="WRAPPED", stack_heights=False),
        observed_at_utc=AT)
    assert proven[0].migration_cpi_proven is True
    assert proven[0].canonical_semantics_valid is True
    assert unproven[0].migration_cpi_proven is False
    assert unproven[0].canonical_semantics_valid is False


def test_adapter_top_level_create_context_is_direct():
    events = decode_liquidity_update(
        _yellowstone_cpi_update(shape="DIRECT"), observed_at_utc=AT)
    assert len(events) == 1
    assert events[0].creation_context == CREATION_CONTEXT_TOP_LEVEL
    assert events[0].migration_cpi_proven is False
