"""Stage 29.1 PumpSwap program constants pins.

Pins:

  * The PumpSwap program id constant equals the value the
    Stage 29.1 vendored IDL records under its top-line
    ``address`` field byte-for-byte (cross-checked by
    ``test_stage_29_1_vendored_idl.py``).
  * WSOL / USDC mint constants match the canonical mainnet
    SPL mint strings.
  * Known-quote-mint lookup tables map to the closed-set
    Stage 28.10 hint tokens.
  * SPL Token / Token-2022 program ids match the canonical
    mainnet program strings.
  * PumpSwap Anchor BuyEvent / SellEvent event discriminators
    are exactly 8 bytes each and match the values surfaced in
    the vendored IDL ``events`` section
    (cross-checked by ``test_stage_29_1_vendored_idl.py``).
  * The vendored-IDL provenance pins (sha256 / byte length /
    relative path / provenance string) are well-shaped.
"""

from __future__ import annotations

from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT,
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_EVENT_DISCRIMINATORS,
    PUMPSWAP_PROGRAM_ID,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
    SPL_TOKEN_2022_PROGRAM_ID,
    SPL_TOKEN_PROGRAM_ID,
    SPL_TOKEN_PROGRAM_IDS,
    STAGE29_1_MINOR_VERSION,
    STAGE29_1_SCHEMA_VERSION,
    USDC_MINT,
    VENDORED_PUMP_AMM_IDL_BYTE_LENGTH,
    VENDORED_PUMP_AMM_IDL_PROVENANCE,
    VENDORED_PUMP_AMM_IDL_RELATIVE_PATH,
    VENDORED_PUMP_AMM_IDL_SHA256,
    WRAPPED_SOL_MINT,
    is_spl_token_program_id,
)


def test_minor_version():
    assert STAGE29_1_MINOR_VERSION == "29.1"


def test_schema_version():
    assert (
        STAGE29_1_SCHEMA_VERSION
        == "stage29_1_pumpswap_hint_extractor_v0"
    )


def test_pumpswap_program_id_exact_value():
    assert PUMPSWAP_PROGRAM_ID == (
        "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
    )


def test_wrapped_sol_mint_exact_value():
    assert WRAPPED_SOL_MINT == (
        "So11111111111111111111111111111111111111112"
    )


def test_usdc_mint_exact_value():
    assert USDC_MINT == (
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    )


def test_known_quote_mint_to_pair_type_hint_mapping():
    assert (
        KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT[
            WRAPPED_SOL_MINT
        ]
        == "PUMP_SOL"
    )
    assert (
        KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT[USDC_MINT]
        == "PUMP_USDC"
    )
    assert (
        len(KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT) == 2
    )


def test_known_quote_mint_to_quote_asset_hint_mapping():
    assert (
        KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT[
            WRAPPED_SOL_MINT
        ]
        == "SOL"
    )
    assert (
        KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT[USDC_MINT]
        == "USDC"
    )
    assert (
        len(KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT) == 2
    )


def test_spl_token_program_ids_exact_values():
    assert SPL_TOKEN_PROGRAM_ID == (
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    )
    assert SPL_TOKEN_2022_PROGRAM_ID == (
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    )
    assert SPL_TOKEN_PROGRAM_IDS == (
        SPL_TOKEN_PROGRAM_ID,
        SPL_TOKEN_2022_PROGRAM_ID,
    )


def test_is_spl_token_program_id_positive():
    assert is_spl_token_program_id(SPL_TOKEN_PROGRAM_ID)
    assert is_spl_token_program_id(SPL_TOKEN_2022_PROGRAM_ID)


def test_is_spl_token_program_id_rejects_other_ids():
    assert not is_spl_token_program_id(PUMPSWAP_PROGRAM_ID)
    assert not is_spl_token_program_id(WRAPPED_SOL_MINT)
    assert not is_spl_token_program_id(USDC_MINT)
    assert not is_spl_token_program_id("")
    assert not is_spl_token_program_id(None)
    assert not is_spl_token_program_id(123)
    assert not is_spl_token_program_id(b"bytes-not-string")


def test_pumpswap_buy_event_discriminator_exact_bytes():
    assert PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES == bytes(
        (103, 244, 82, 31, 44, 245, 119, 119),
    )
    assert len(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES) == 8


def test_pumpswap_sell_event_discriminator_exact_bytes():
    assert PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES == bytes(
        (62, 47, 55, 10, 165, 3, 220, 42),
    )
    assert len(PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES) == 8


def test_event_discriminators_tuple_membership():
    assert PUMPSWAP_EVENT_DISCRIMINATORS == (
        PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
        PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
    )


def test_vendored_idl_relative_path_exact():
    assert VENDORED_PUMP_AMM_IDL_RELATIVE_PATH == (
        "proto/stage29_1/source/pump_amm.json"
    )


def test_vendored_idl_sha256_well_shaped():
    assert isinstance(VENDORED_PUMP_AMM_IDL_SHA256, str)
    assert len(VENDORED_PUMP_AMM_IDL_SHA256) == 64
    for ch in VENDORED_PUMP_AMM_IDL_SHA256:
        assert ch in "0123456789abcdef"


def test_vendored_idl_byte_length_well_shaped():
    assert isinstance(VENDORED_PUMP_AMM_IDL_BYTE_LENGTH, int)
    assert VENDORED_PUMP_AMM_IDL_BYTE_LENGTH > 0


def test_vendored_idl_provenance_carries_program_id():
    assert PUMPSWAP_PROGRAM_ID in (
        VENDORED_PUMP_AMM_IDL_PROVENANCE
    )
