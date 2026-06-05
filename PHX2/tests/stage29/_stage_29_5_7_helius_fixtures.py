"""Stage 29.5.7 test-only raw Helius envelope fixtures.

FIXTURES ONLY. This module is imported EXCLUSIVELY by the Stage 29.5.7 test
surface; no Stage 29.5.7 production module imports it (pinned by
``test_stage_29_5_7_fake_evidence_proof.py``). It builds realistic raw Helius
confirmed-transaction envelopes (the ``encoding=json`` Solana JSON-RPC shape) for
the happy path + every reject path, using public-chain-shaped placeholder
account keys (safe-shape printable strings of length 32..64) and the real
PumpSwap program id + wrapped-SOL / USDC quote mints.

The ``create_pool`` migration is modeled as a CPI inner instruction (the real
Pump.fun migration shape) by default, with a direct top-level variant available.
The outer migrate program is a NON-Pump.fun placeholder (the boundary forbids the
Pump.fun bonding-curve program-id literal); the detection never needs it.
"""

from __future__ import annotations

from typing import List, Optional

from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    USDC_MINT,
    WRAPPED_SOL_MINT,
)


# ---------------------------------------------------------------------------
# Safe-shape placeholder account keys (length 32..64, printable, no whitespace)
# ---------------------------------------------------------------------------


POOL: str = "Po" + "o" * 42
GLOBAL_CONFIG: str = "Gg" + "g" * 42
CREATOR: str = "Cr" + "e" * 42
USER: str = "Us" + "r" * 42
BASE_MINT: str = "Bm" + "k" * 42
QUOTE_MINT_SOL: str = WRAPPED_SOL_MINT
QUOTE_MINT_USDC: str = USDC_MINT
OUTER_MIGRATE_PROGRAM: str = "OuterMigrateProgram" + "1" * 25
OTHER_PROGRAM: str = "SomeOtherProgram" + "2" * 28
SIGNATURE: str = "Sig" + "Z" * 85

DEFAULT_SLOT: int = 333444555
# Unix UTC seconds for 2024-05-27T00:00:00Z (a clean instant for the anchor).
DEFAULT_BLOCK_TIME: int = 1716768000
DEFAULT_ANCHOR_UTC: str = "2024-05-27T00:00:00Z"

OBSERVED_AT_UTC: str = "2026-05-27T00:05:00Z"


# ---------------------------------------------------------------------------
# Anchor instruction discriminators + base58 instruction-data builder
# ---------------------------------------------------------------------------
#
# Mirrored BY VALUE from the vendored Pump AMM IDL
# (``PHX2/proto/stage29_1/source/pump_amm.json``). create_pool is pinned
# byte-for-byte by ``test_stage_29_5_7_vendored_idl.py``. Buy / Sell share
# create_pool's EXACT pool@0 / base@3 / quote@4 account layout but carry DIFFERENT
# discriminators -- which is exactly why the normalizer must gate on the
# discriminator, not the account layout. These fixtures base58-encode the
# instruction ``data`` (8-byte discriminator + a small placeholder arg payload) so
# the normalizer's hand-rolled decoder recovers the discriminator.

CREATE_POOL_DISCRIMINATOR: tuple = (233, 146, 209, 142, 207, 104, 64, 188)
BUY_DISCRIMINATOR: tuple = (102, 6, 61, 18, 1, 218, 235, 234)
SELL_DISCRIMINATOR: tuple = (51, 230, 133, 164, 1, 127, 131, 173)

_BASE58_ALPHABET: str = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)


def _base58_encode(raw: bytes) -> str:
    """Encode raw bytes into a base58 (Bitcoin-alphabet) string (test-only)."""
    n = int.from_bytes(raw, "big") if raw else 0
    chars: List[str] = []
    while n > 0:
        n, rem = divmod(n, 58)
        chars.append(_BASE58_ALPHABET[rem])
    leading = 0
    for b in raw:
        if b == 0:
            leading += 1
        else:
            break
    return "1" * leading + "".join(reversed(chars))


def encode_instruction_data(discriminator: object) -> str:
    """Build a realistic base58 instruction-data string: the 8-byte Anchor
    discriminator followed by a small non-zero placeholder arg payload (the
    normalizer reads only the leading 8 bytes).
    """
    raw = bytes(tuple(discriminator)) + bytes((1, 2, 3, 4, 5, 6, 7, 8))
    return _base58_encode(raw)


# ---------------------------------------------------------------------------
# Log builders
# ---------------------------------------------------------------------------


def _create_pool_logs(*, via_cpi: bool) -> List[str]:
    if via_cpi:
        return [
            f"Program {OUTER_MIGRATE_PROGRAM} invoke [1]",
            "Program log: Instruction: Migrate",
            f"Program {PUMPSWAP_PROGRAM_ID} invoke [2]",
            "Program log: Instruction: CreatePool",
            f"Program {PUMPSWAP_PROGRAM_ID} success",
            f"Program {OUTER_MIGRATE_PROGRAM} success",
        ]
    return [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
        "Program log: Instruction: CreatePool",
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]


def _swap_logs() -> List[str]:
    return [
        f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
        "Program log: Instruction: Buy",
        f"Program {PUMPSWAP_PROGRAM_ID} success",
    ]


# ---------------------------------------------------------------------------
# Migration envelope builder (happy path + parametrized reject variants)
# ---------------------------------------------------------------------------


def make_migration_envelope(
    *,
    base_mint: str = BASE_MINT,
    quote_mint: str = QUOTE_MINT_SOL,
    pool: str = POOL,
    slot: Optional[object] = DEFAULT_SLOT,
    block_time: Optional[object] = DEFAULT_BLOCK_TIME,
    signature: Optional[str] = SIGNATURE,
    include_top_signature: bool = False,
    via_cpi: bool = True,
    include_initial_buy: bool = False,
    include_duplicate_create_pool: bool = False,
    create_pool_discriminator: Optional[object] = CREATE_POOL_DISCRIMINATOR,
    omit_create_pool_log: bool = False,
    drop_slot: bool = False,
    drop_block_time: bool = False,
) -> dict:
    """Build a realistic raw Helius confirmed-transaction migration envelope.

    The PumpSwap ``create_pool`` instruction (program at accountKeys index 5,
    accounts ``[pool, global_config, creator, base_mint, quote_mint]`` so
    ``pool``@0 / ``base_mint``@3 / ``quote_mint``@4) lives in a CPI inner
    instruction by default (the real Pump.fun migration shape), or top-level when
    ``via_cpi=False``. The create_pool instruction carries a base58 ``data`` blob
    whose leading discriminator is ``create_pool_discriminator`` (the real
    create_pool discriminator by default; pass ``BUY_DISCRIMINATOR`` to model a
    create_pool-shaped instruction with the WRONG discriminator, or ``None`` to
    OMIT the ``data`` field entirely). ``include_initial_buy`` adds a same-pool
    PumpSwap Buy (a DIFFERENT discriminator, so it is ignored by the gate).
    ``include_duplicate_create_pool`` adds a second create_pool instruction with
    the SAME quartet (exercising the value-identical-quartet collapse).
    """
    account_keys: List[str] = [
        pool,
        GLOBAL_CONFIG,
        CREATOR,
        base_mint,
        quote_mint,
        PUMPSWAP_PROGRAM_ID,
    ]
    create_pool_ins: dict = {"programIdIndex": 5, "accounts": [0, 1, 2, 3, 4]}
    if create_pool_discriminator is not None:
        create_pool_ins["data"] = encode_instruction_data(
            create_pool_discriminator
        )
    buy_ins: dict = {
        "programIdIndex": 5,
        "accounts": [0, 1, 2, 3, 4],
        "data": encode_instruction_data(BUY_DISCRIMINATOR),
    }
    dup_create_pool_ins: dict = {
        "programIdIndex": 5,
        "accounts": [0, 1, 2, 3, 4],
        "data": encode_instruction_data(CREATE_POOL_DISCRIMINATOR),
    }

    top_instructions: List[dict] = []
    inner_groups: List[dict] = []
    if via_cpi:
        account_keys = account_keys + [OUTER_MIGRATE_PROGRAM]
        top_instructions = [
            {"programIdIndex": 6, "accounts": [0, 1, 2, 3, 4, 5]}
        ]
        inner_list = [create_pool_ins]
        if include_initial_buy:
            inner_list.append(buy_ins)
        if include_duplicate_create_pool:
            inner_list.append(dup_create_pool_ins)
        inner_groups = [{"index": 0, "instructions": inner_list}]
    else:
        top_instructions = [create_pool_ins]
        if include_initial_buy:
            top_instructions.append(buy_ins)
        if include_duplicate_create_pool:
            top_instructions.append(dup_create_pool_ins)

    logs = _create_pool_logs(via_cpi=via_cpi)
    if omit_create_pool_log:
        logs = [line for line in logs if "CreatePool" not in line]

    meta: dict = {
        "err": None,
        "logMessages": logs,
        "innerInstructions": inner_groups,
    }
    message: dict = {
        "accountKeys": account_keys,
        "instructions": top_instructions,
    }
    transaction: dict = {
        "signatures": [signature] if signature is not None else [],
        "message": message,
    }
    envelope: dict = {
        "transaction": transaction,
        "meta": meta,
    }
    if not drop_slot:
        envelope["slot"] = slot
    if not drop_block_time:
        envelope["blockTime"] = block_time
    if include_top_signature and signature is not None:
        envelope["signature"] = signature
    return envelope


# ---------------------------------------------------------------------------
# Reject-path envelope builders
# ---------------------------------------------------------------------------


def make_swap_envelope() -> dict:
    """A PumpSwap Buy swap: PumpSwap invoked + ``Instruction: Buy`` log, but NO
    ``CreatePool`` -- an ordinary swap that must NOT be treated as a migration.
    """
    account_keys = [
        POOL,
        USER,
        GLOBAL_CONFIG,
        BASE_MINT,
        QUOTE_MINT_SOL,
        PUMPSWAP_PROGRAM_ID,
    ]
    # NOTE: the Buy accounts are create_pool-SHAPED (pool@0, base@3, quote@4); only
    # the Buy discriminator in ``data`` distinguishes it from a migration.
    buy_ins = {
        "programIdIndex": 5,
        "accounts": [0, 1, 2, 3, 4],
        "data": encode_instruction_data(BUY_DISCRIMINATOR),
    }
    return {
        "slot": DEFAULT_SLOT,
        "blockTime": DEFAULT_BLOCK_TIME,
        "transaction": {
            "signatures": [SIGNATURE],
            "message": {
                "accountKeys": account_keys,
                "instructions": [buy_ins],
            },
        },
        "meta": {
            "err": None,
            "logMessages": _swap_logs(),
            "innerInstructions": [],
        },
    }


def make_swap_with_stray_create_pool_log_envelope() -> dict:
    """The Codex repro: an ordinary PumpSwap Buy swap (Buy discriminator, but the
    SAME pool@0 / base@3 / quote@4 account layout as create_pool) with a stray,
    UNRELATED ``Program log: Instruction: CreatePool`` line spliced into the logs.

    It MUST fail closed -- the buy instruction's discriminator is not create_pool,
    so the loose tx-level log can no longer manufacture migration evidence.
    """
    env = make_swap_envelope()
    logs = list(env["meta"]["logMessages"])
    # Splice a stray CreatePool marker in, as if emitted by an unrelated program.
    logs.insert(2, "Program log: Instruction: CreatePool")
    env["meta"]["logMessages"] = logs
    return env


def make_sell_with_create_pool_layout_and_log_envelope() -> dict:
    """A PumpSwap Sell whose accounts are create_pool-SHAPED (pool@0, base@3,
    quote@4) AND which carries a stray ``Instruction: CreatePool`` log -- but the
    instruction discriminator is Sell, so it must NOT prove a migration.
    """
    account_keys = [
        POOL,
        USER,
        GLOBAL_CONFIG,
        BASE_MINT,
        QUOTE_MINT_SOL,
        PUMPSWAP_PROGRAM_ID,
    ]
    sell_ins = {
        "programIdIndex": 5,
        "accounts": [0, 1, 2, 3, 4],
        "data": encode_instruction_data(SELL_DISCRIMINATOR),
    }
    return {
        "slot": DEFAULT_SLOT,
        "blockTime": DEFAULT_BLOCK_TIME,
        "transaction": {
            "signatures": [SIGNATURE],
            "message": {
                "accountKeys": account_keys,
                "instructions": [sell_ins],
            },
        },
        "meta": {
            "err": None,
            "logMessages": [
                f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
                "Program log: Instruction: Sell",
                "Program log: Instruction: CreatePool",  # stray, unrelated marker
                f"Program {PUMPSWAP_PROGRAM_ID} success",
            ],
            "innerInstructions": [],
        },
    }


def make_wrong_program_envelope() -> dict:
    """A successful transaction that never invokes the PumpSwap program."""
    account_keys = [POOL, USER, BASE_MINT, QUOTE_MINT_SOL, OTHER_PROGRAM]
    other_ins = {"programIdIndex": 4, "accounts": [0, 1, 2, 3]}
    return {
        "slot": DEFAULT_SLOT,
        "blockTime": DEFAULT_BLOCK_TIME,
        "transaction": {
            "signatures": [SIGNATURE],
            "message": {
                "accountKeys": account_keys,
                "instructions": [other_ins],
            },
        },
        "meta": {
            "err": None,
            "logMessages": [
                f"Program {OTHER_PROGRAM} invoke [1]",
                "Program log: Instruction: DoSomething",
                f"Program {OTHER_PROGRAM} success",
            ],
            "innerInstructions": [],
        },
    }


def make_failed_migration_envelope() -> dict:
    """An otherwise-migration envelope whose transaction FAILED (``meta.err``)."""
    env = make_migration_envelope()
    env["meta"]["err"] = {"InstructionError": [1, {"Custom": 6001}]}
    return env


def make_vote_migration_envelope() -> dict:
    """An otherwise-migration envelope flagged as a vote transaction."""
    env = make_migration_envelope()
    env["isVote"] = True
    return env


def make_quartet_unresolved_envelope() -> dict:
    """A CreatePool-logged envelope whose ``create_pool`` instruction's index-4
    account is NOT a known quote mint -- the quartet cannot resolve.
    """
    # quote_mint slot holds a non-known mint, so the create_pool shape filter
    # rejects it (index-4 must be wrapped-SOL / USDC).
    return make_migration_envelope(quote_mint="Nq" + "x" * 42)


def make_missing_signature_envelope() -> dict:
    """A migration envelope with no transaction signature."""
    return make_migration_envelope(signature=None)


def make_missing_slot_envelope() -> dict:
    """A migration envelope with a non-int (missing) slot."""
    return make_migration_envelope(drop_slot=True)


def make_missing_block_time_envelope() -> dict:
    """A migration envelope with a non-int (missing) blockTime."""
    return make_migration_envelope(drop_block_time=True)
