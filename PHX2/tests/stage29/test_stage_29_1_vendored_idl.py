"""Stage 29.1 vendored Pump AMM IDL pins.

Pins:

  * ``PHX2/proto/stage29_1/source/pump_amm.json`` exists at
    the locked relative path.
  * Its SHA-256 matches the constant
    ``VENDORED_PUMP_AMM_IDL_SHA256``.
  * Its byte length matches the constant
    ``VENDORED_PUMP_AMM_IDL_BYTE_LENGTH``.
  * Its parsed JSON's ``address`` field equals
    ``PUMPSWAP_PROGRAM_ID`` byte-for-byte.
  * Its parsed JSON's ``events`` list contains a ``BuyEvent``
    entry whose ``discriminator`` equals
    ``PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES`` byte-for-byte,
    and a ``SellEvent`` entry whose ``discriminator`` equals
    ``PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES`` byte-for-byte.
  * The Pump.fun bonding-curve program id (``6EF8rrec...``)
    does NOT appear anywhere in the IDL (the vendored IDL is
    PumpSwap AMM only; bonding-curve coverage is deferred).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_PROGRAM_ID,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
    VENDORED_PUMP_AMM_IDL_BYTE_LENGTH,
    VENDORED_PUMP_AMM_IDL_RELATIVE_PATH,
    VENDORED_PUMP_AMM_IDL_SHA256,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
VENDORED_IDL_PATH: Path = (
    PHX2_ROOT / VENDORED_PUMP_AMM_IDL_RELATIVE_PATH
)


def _read_raw() -> bytes:
    return VENDORED_IDL_PATH.read_bytes()


def test_vendored_idl_file_exists():
    assert VENDORED_IDL_PATH.is_file(), (
        f"Stage 29.1 requires vendored Pump AMM IDL at "
        f"{VENDORED_IDL_PATH!s}"
    )


def test_vendored_idl_byte_length_matches_pin():
    raw = _read_raw()
    assert len(raw) == VENDORED_PUMP_AMM_IDL_BYTE_LENGTH


def test_vendored_idl_sha256_matches_pin():
    raw = _read_raw()
    assert (
        hashlib.sha256(raw).hexdigest()
        == VENDORED_PUMP_AMM_IDL_SHA256
    )


def test_vendored_idl_address_matches_program_id_constant():
    data = json.loads(_read_raw().decode("utf-8"))
    assert data["address"] == PUMPSWAP_PROGRAM_ID


def test_vendored_idl_metadata_name_is_pump_amm():
    data = json.loads(_read_raw().decode("utf-8"))
    assert data["metadata"]["name"] == "pump_amm"


def test_vendored_idl_has_buy_event_with_matching_discriminator():
    data = json.loads(_read_raw().decode("utf-8"))
    events = {ev["name"]: ev for ev in data.get("events", [])}
    assert "BuyEvent" in events, "vendored IDL missing BuyEvent"
    disc = bytes(events["BuyEvent"]["discriminator"])
    assert disc == PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES


def test_vendored_idl_has_sell_event_with_matching_discriminator():
    data = json.loads(_read_raw().decode("utf-8"))
    events = {ev["name"]: ev for ev in data.get("events", [])}
    assert "SellEvent" in events, "vendored IDL missing SellEvent"
    disc = bytes(events["SellEvent"]["discriminator"])
    assert disc == PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES


def test_vendored_idl_does_not_carry_pump_fun_bonding_curve_program():
    # Pump.fun bonding-curve coverage is deferred to a future
    # Stage 29.1 follow-up; the vendored IDL at Stage 29.1 is
    # PumpSwap AMM only and must not surface the bonding-curve
    # program id as a string anywhere.
    raw_text = _read_raw().decode("utf-8")
    assert (
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
        not in raw_text
    )


def test_vendored_idl_path_under_proto_stage29_1_source():
    # Sanity: the vendored file lives under the locked
    # Stage 29.1 vendored-source directory, not under a
    # different vendored-source surface (e.g. Stage 28.11's).
    parts = VENDORED_IDL_PATH.parts
    assert parts[-3:] == (
        "stage29_1", "source", "pump_amm.json",
    )
