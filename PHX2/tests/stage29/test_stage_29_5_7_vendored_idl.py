"""Stage 29.5.7 vendored-IDL provenance pins.

Proves the Stage 29.5.7 migration-event identity is REAL -- the ``create_pool``
instruction + ``CreatePoolEvent`` discriminators and the ``create_pool`` account
layout this slice pins are read byte-for-byte from the vendored Pump AMM Anchor
IDL at ``PHX2/proto/stage29_1/source/pump_amm.json`` (the same IDL the Stage 29.1
vendored-IDL test pins by SHA-256). This is the machine-checked evidence that the
migration event the normalizer detects is the actual on-chain Pump.fun ->
PumpSwap migration event, not a fabricated constant.
"""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    CREATE_POOL_ACCOUNT_INDEX_BASE_MINT,
    CREATE_POOL_ACCOUNT_INDEX_POOL,
    CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT,
    PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR,
)


_PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_IDL_PATH: Path = (
    _PHX2_ROOT / "proto" / "stage29_1" / "source" / "pump_amm.json"
)


def _load_idl() -> dict:
    return json.loads(_IDL_PATH.read_text(encoding="utf-8"))


def _find_named(items: list, name: str) -> dict:
    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    raise AssertionError(f"no IDL entry named {name!r}")


def test_idl_file_exists() -> None:
    assert _IDL_PATH.is_file(), f"vendored IDL missing at {_IDL_PATH}"


def test_idl_program_address_is_pumpswap() -> None:
    idl = _load_idl()
    assert idl.get("address") == PUMPSWAP_PROGRAM_ID


def test_create_pool_instruction_discriminator_matches_idl() -> None:
    idl = _load_idl()
    create_pool = _find_named(idl["instructions"], "create_pool")
    assert (
        tuple(create_pool["discriminator"])
        == PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR
    )


def test_create_pool_event_discriminator_matches_idl() -> None:
    idl = _load_idl()
    event = _find_named(idl["events"], "CreatePoolEvent")
    assert (
        tuple(event["discriminator"])
        == PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR
    )


def test_create_pool_account_layout_matches_idl() -> None:
    idl = _load_idl()
    create_pool = _find_named(idl["instructions"], "create_pool")
    accounts = create_pool["accounts"]
    assert (
        accounts[CREATE_POOL_ACCOUNT_INDEX_POOL]["name"] == "pool"
    )
    assert (
        accounts[CREATE_POOL_ACCOUNT_INDEX_BASE_MINT]["name"] == "base_mint"
    )
    assert (
        accounts[CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT]["name"] == "quote_mint"
    )


def test_buy_and_sell_share_create_pool_layout_but_differ_by_discriminator() -> None:
    # The ROOT CAUSE the discriminator gate fixes, proved against the vendored IDL:
    # ``buy`` / ``sell`` carry the SAME pool@0 / base_mint@3 / quote_mint@4 account
    # layout as ``create_pool``, so the account layout ALONE cannot distinguish a
    # migration from an ordinary swap -- ONLY the instruction discriminator can.
    idl = _load_idl()
    for name in ("buy", "sell"):
        ins = _find_named(idl["instructions"], name)
        accounts = ins["accounts"]
        assert accounts[CREATE_POOL_ACCOUNT_INDEX_POOL]["name"] == "pool"
        assert (
            accounts[CREATE_POOL_ACCOUNT_INDEX_BASE_MINT]["name"] == "base_mint"
        )
        assert (
            accounts[CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT]["name"] == "quote_mint"
        )
        # ...yet the discriminator DIFFERS from create_pool (the binding gate).
        assert (
            tuple(ins["discriminator"])
            != PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR
        )


def test_create_pool_event_carries_migration_axes() -> None:
    # The CreatePoolEvent struct carries the base_mint / quote_mint / pool the
    # migration evidence binds -- confirming the event is the pool-creation event.
    idl = _load_idl()
    type_defs = idl.get("types", [])
    event_type = _find_named(type_defs, "CreatePoolEvent")
    field_names = {
        f["name"] for f in event_type["type"]["fields"]
    }
    assert {"base_mint", "quote_mint", "pool", "timestamp"} <= field_names
