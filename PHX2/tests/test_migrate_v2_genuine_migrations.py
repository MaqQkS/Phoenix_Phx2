"""The four genuine migrate_v2 migrations the 2026-07-18 run wrongly rejected.

Run phx2_live_20260718T080944Z (bounded acceptance retry) observed four genuine
pump.fun migrations — every one rejected CPI_UNPROVEN because live pump.fun had
moved from ``migrate`` to ``migrate_v2`` while admission pinned only the v1
discriminator.  Each fixture below reconstructs one of those transactions from
the preserved run artifacts using the REAL public on-chain addresses (pool,
migration authority, base mint, vaults, deposits, signature, slot); the
recorded liquidity events independently proved ``pool_pda_valid`` and both
vault derivations for these exact addresses, so an admission pass here binds
the new discriminator set to reality, not merely to synthetic keys.

Everything below is public chain data from a preserved local artifact; no
secrets and no network access.
"""

import struct
from types import SimpleNamespace

from PHX2.free_tier_producer.liquidity_integrity import (
    CREATE_POOL_DISCRIMINATOR,
    b58encode,
    derive_associated_token_address,
    derive_pool_address,
)
from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_VERSION_V2,
    POOL_CREATION_MIGRATION_CPI,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_PROGRAM_ID,
    evaluate_migration_admission,
    validate_migration_proof,
)
from PHX2.free_tier_producer.paid_grpc_source import _base58_decode
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID


WSOL = "So11111111111111111111111111111111111111112"
SYSTEM = "11111111111111111111111111111111"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
POOL_INDEX = 0
BASE_DECIMALS = 6

# Synthetic stand-ins for the create_pool accounts admission never verifies
# (LP mint, user token accounts, event authority).  Locally derived keys only.
LP_MINT_STAND_IN = b58encode(bytes(range(32, 64)))
USER_BASE_STAND_IN = b58encode(bytes(range(64, 96)))
USER_QUOTE_STAND_IN = b58encode(bytes(range(96, 128)))
USER_LP_STAND_IN = b58encode(bytes(range(128, 160)))
EVENT_AUTHORITY_STAND_IN = b58encode(bytes(range(160, 192)))

# (mint, pool, authority/creator, base_vault, quote_vault, fee_payer,
#  base_raw, quote_raw, slot, signature) — verbatim from the preserved
# migration_rejections.jsonl + liquidity_events.jsonl of the 07-18 run.
GENUINE_MIGRATIONS = (
    ("4omdB4PmH1hP15jUpLcQX8aUqYmoPzWgQk8L6UZipump",
     "BdTePYQ4Y53i5Mowjt36SU8FcRv3q2bC47L4ewbnbG9W",
     "4x2daMTGvetP4Jvw2JYPKEUCmnbwomYkpEDst7he15Lg",
     "C9xwkTQuTZToB826g1aMicbAFod3XJ2YyXPt3Xwdw8fm",
     "9Rxi7cGFcHN7vn76pFT29XAN7qR2h7xAdmKF9FLDTGzU",
     "9C4nRvhhVquCKATjDCx5FKvNS9PNgNqgyWy9AcoDjYv5",
     206_900_000_000_000, 84_990_362_268, 433651818,
     "4XwYAo7HLMyuvEvbtiJZivXTp3L1EAhZqz6j5aQGqAKEGTKgav1uCECcEK9tx9uyEDcqHCUZviV28gDGqSAcFnVN"),
    ("HLmz1postTUtuCo9CuBTm1QPbsRLxbJkpB4cF4Mspump",
     "AW2Jc3UcqMoNsMV7UvKgwR9ZgCVqsk1PhKDZB4hhHsNF",
     "5fdrSdADX8gTWAL4KejDmnmUUiwq4xWRSTw9uFZuLL3c",
     "DScbip7d7s12JoVvz68xVpuioyQj55mhU3EP2XeTqxuK",
     "89GffqwCVauHDem8yA9jUY8YvEC8Zvtqpqj2HWLDPNJo",
     "9C4nRvhhVquCKATjDCx5FKvNS9PNgNqgyWy9AcoDjYv5",
     206_900_000_000_000, 84_990_359_779, 433654487,
     "4zNdm6vphdwo6WX8uqVKaDtky4LNqk94VAikEFEq9wVVLHLq6sUPwLfM7J8Et7XnsQikqKQoK52EtCPbrEyrCXFR"),
    ("HhAjJiomnhsAcbHNyxzZUY6ZXHnwKi5sYgwBzxqrpump",
     "AtmAxQ6YFgzGpn1jjKSGeGfAihS5usRiyL8v3S1cUyvU",
     "5SA8GbSjXg8Ys6m5Ytp9LrEMtNNKFpRuRjLp357g7Qbn",
     "26LdFCmGrPqRbaDPTmjh8yQ7uKZrW4oPDNWCzqvKXKGV",
     "EXtdfoSFaUADxqRWRgACMS7hy64ZhboF88fonWegX3Nr",
     "9C4nRvhhVquCKATjDCx5FKvNS9PNgNqgyWy9AcoDjYv5",
     206_900_000_000_000, 84_990_359_936, 433657854,
     "YSgx3W6yZ94YXYQWcCzHvfhKoZTt859xRcx3gWX4yF93cGMfSm3KtQ8TW8rQeAoLi9VdzZGSpcWbDVBeHuTnNZh"),
    ("2RCf4yRGZpjALcHYo7WsH8kTkRcS6rs2tmTnqhYopump",
     "5k1yCtqguqZBLPEm1C3fL3pEwXUC9YNxjgeVM3MzYgdu",
     "59da77sQS4nQp9CNKd1v4shWxPnyeYDUTsxh62vqaZtr",
     "2E1Ma4w8JbeioX4nfVsHrV4ARX5NmDnqHPKcDrQfb8ib",
     "DJnzbgnQ8AbpzkFGkhXvwrkixdjHZkta8G3PhTFySE2L",
     "9C4nRvhhVquCKATjDCx5FKvNS9PNgNqgyWy9AcoDjYv5",
     206_900_000_000_000, 84_990_359_375, 433663296,
     "JWsN4nMzUDrgumTnykCTZz9WXUmuJ9PSzezcQGWczshfVt21YeyVLT9X2AgxhYHKeT83E8oHjuhaJR23tuyRkC5"),
)


def _build_real_migrate_v2_update(mint, pool, creator, base_vault, quote_vault,
                                  fee_payer, base_raw, quote_raw, slot,
                                  signature):
    """One SubscribeUpdate reproducing the real migrate_v2 transaction shape:
    a top-level pump.fun ``migrate_v2`` instruction whose CPI executes the
    IDL-pinned PumpSwap ``create_pool`` with the recorded real accounts."""

    accounts = [
        pool, fee_payer, creator, mint, WSOL,
        LP_MINT_STAND_IN, USER_BASE_STAND_IN, USER_QUOTE_STAND_IN,
        USER_LP_STAND_IN,
        base_vault, quote_vault, SYSTEM, TOKEN_2022, TOKEN_2022, TOKEN_PROGRAM,
        ATA_PROGRAM, EVENT_AUTHORITY_STAND_IN,
        PUMPSWAP_PROGRAM_ID,
    ]
    key_texts = [fee_payer]
    for value in [*accounts, PUMPSWAP_PROGRAM_ID, PUMPFUN_PROGRAM_ID]:
        if value not in key_texts:
            key_texts.append(value)
    key_index = {value: position for position, value in enumerate(key_texts)}

    create_pool_data = bytes(CREATE_POOL_DISCRIMINATOR) + struct.pack(
        "<HQQ", POOL_INDEX, base_raw, quote_raw)
    migrate_v2_data = bytes(PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR)

    top_level = [SimpleNamespace(
        program_id_index=key_index[PUMPFUN_PROGRAM_ID],
        accounts=b"", data=migrate_v2_data)]
    inner = [SimpleNamespace(
        program_id_index=key_index[PUMPSWAP_PROGRAM_ID],
        accounts=bytes(key_index[value] for value in accounts),
        data=create_pool_data, stack_height=2)]

    def _balance(address, amount, decimals, balance_mint):
        return SimpleNamespace(
            account_index=key_index[address], owner=pool, mint=balance_mint,
            ui_token_amount=SimpleNamespace(amount=str(amount), decimals=decimals))

    message = SimpleNamespace(
        account_keys=[_base58_decode(value) for value in key_texts],
        instructions=top_level,
        header=SimpleNamespace(num_required_signatures=1),
    )
    meta = SimpleNamespace(
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        inner_instructions=[SimpleNamespace(index=0, instructions=inner)],
        pre_token_balances=[],
        post_token_balances=[
            _balance(base_vault, base_raw, BASE_DECIMALS, mint),
            _balance(quote_vault, quote_raw, 9, WSOL),
        ],
    )
    tx_info = SimpleNamespace(
        signature=_base58_decode(signature),
        transaction=SimpleNamespace(message=message),
        meta=meta,
    )
    update = SimpleNamespace(
        transaction=SimpleNamespace(slot=slot, transaction=tx_info))
    update.HasField = lambda name: name == "transaction"
    return update


def test_recorded_real_addresses_still_satisfy_canonical_derivations():
    """The preserved evidence itself: every real pool is the canonical PDA of
    (index 0, recorded authority, mints), and both real vaults are the exact
    associated-token derivations (Token-2022 base, classic-token WSOL quote)."""
    for (mint, pool, creator, base_vault, quote_vault,
         _fee_payer, _base_raw, _quote_raw, _slot, _signature) in GENUINE_MIGRATIONS:
        assert derive_pool_address(
            index=POOL_INDEX, creator=creator, base_mint=mint,
            quote_mint=WSOL) == pool
        assert derive_associated_token_address(
            owner=pool, token_program=TOKEN_2022, mint=mint,
            associated_program=ATA_PROGRAM) == base_vault
        assert derive_associated_token_address(
            owner=pool, token_program=TOKEN_PROGRAM, mint=WSOL,
            associated_program=ATA_PROGRAM) == quote_vault


def test_all_four_genuine_migrations_admit_under_migrate_v2_semantics():
    for row in GENUINE_MIGRATIONS:
        (mint, pool, _creator, _base_vault, _quote_vault,
         _fee_payer, _base_raw, quote_raw, slot, signature) = row
        decision = evaluate_migration_admission(
            _build_real_migrate_v2_update(*row))
        assert decision is not None, mint
        assert decision.admitted, (mint, decision.reason_codes)
        assert decision.classification == POOL_CREATION_MIGRATION_CPI
        assert decision.migration_version == MIGRATION_VERSION_V2
        assert decision.candidate_mint == mint
        assert decision.pool == pool
        assert decision.quote_mint == WSOL
        assert decision.transaction_signature == signature
        assert decision.slot == slot
        assert decision.deposit_bucket == "GE_50_SOL"
        proof = decision.proof
        valid, reason = validate_migration_proof(proof)
        assert valid, (mint, reason)
        assert proof.migration_instruction_version == MIGRATION_VERSION_V2
        assert proof.quote_deposit_raw == quote_raw
        assert proof.mint_suffix_consistent is True
