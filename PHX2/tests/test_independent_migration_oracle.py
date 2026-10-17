"""Raw-JSON oracle recognition is independent and identity-compatible."""

from __future__ import annotations

from decimal import Decimal

import pytest

from PHX2.free_tier_producer.liquidity_integrity import b58encode
from PHX2.free_tier_producer.migration_admission import (
    PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    evaluate_migration_admission,
)
from PHX2.free_tier_producer.migration_census import (
    canonical_migration_identity,
)
from PHX2.scripts.independent_migration_oracle import (
    _recognize_transaction,
)
from PHX2.tests.test_migration_admission import (
    SIGNATURE_BYTES,
    build_pool_creation_update,
)

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58(raw: bytes) -> str:
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big")
    chars = []
    while number:
        number, remainder = divmod(number, 58)
        chars.append(_B58[remainder])
    return "1" * zeros + "".join(reversed(chars))


def _instruction(value) -> dict:
    result = {
        "programIdIndex": int(value.program_id_index),
        "accounts": list(bytes(value.accounts)),
        "data": _b58(bytes(value.data)),
    }
    stack = getattr(value, "stack_height", None)
    if stack is not None:
        result["stackHeight"] = int(stack)
    return result


def _raw_transaction(update) -> dict:
    wrapper = update.transaction
    tx_info = wrapper.transaction
    message = tx_info.transaction.message
    meta = tx_info.meta
    static_keys = [b58encode(bytes(value)) for value in message.account_keys]
    writable = [
        b58encode(bytes(value))
        for value in meta.loaded_writable_addresses
    ]

    def _balance(value) -> dict:
        return {
            "accountIndex": int(value.account_index),
            "mint": value.mint,
            "owner": value.owner,
            "uiTokenAmount": {
                "amount": value.ui_token_amount.amount,
                "decimals": int(value.ui_token_amount.decimals),
            },
        }

    return {
        "transaction": {
            "signatures": [_b58(SIGNATURE_BYTES)],
            "message": {
                "accountKeys": static_keys,
                "instructions": [
                    _instruction(value) for value in message.instructions
                ],
            },
        },
        "meta": {
            "err": None,
            "loadedAddresses": {
                "writable": writable,
                "readonly": [],
            },
            "innerInstructions": [
                {
                    "index": int(group.index),
                    "instructions": [
                        _instruction(value)
                        for value in group.instructions
                    ],
                }
                for group in meta.inner_instructions
            ],
            "preTokenBalances": [
                _balance(value) for value in meta.pre_token_balances
            ],
            "postTokenBalances": [
                _balance(value) for value in meta.post_token_balances
            ],
        },
    }


@pytest.mark.parametrize(
    ("discriminator", "version"),
    [
        (PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR, "migrate"),
        (PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR, "migrate_v2"),
    ],
)
def test_independent_raw_oracle_matches_canonical_identity(
    discriminator, version
):
    update = build_pool_creation_update(
        migrate_discriminator=discriminator
    )
    decision = evaluate_migration_admission(update)
    assert decision is not None and decision.admitted and decision.proof
    rows = _recognize_transaction(
        tx_json=_raw_transaction(update),
        slot=int(update.transaction.slot),
        block_time=1_700_000_000,
        min_quote_deposit_sol=Decimal("50"),
    )
    assert len(rows) == 1
    assert rows[0]["migration_version"] == version
    assert rows[0]["census_identity"] == canonical_migration_identity(
        decision.proof
    )


@pytest.mark.parametrize("shape", ["DIRECT", "CPI_NO_PUMPFUN"])
def test_independent_raw_oracle_rejects_noncanonical_shapes(shape):
    update = build_pool_creation_update(shape=shape)
    assert _recognize_transaction(
        tx_json=_raw_transaction(update),
        slot=int(update.transaction.slot),
        block_time=1_700_000_000,
        min_quote_deposit_sol=Decimal("50"),
    ) == []
