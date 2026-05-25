"""Stage 29.1 PumpSwap program constants.

Stage 29.1 ships hint-extraction support for the post-migration
PumpSwap AMM path only. The pre-migration Pump.fun bonding-curve
program (``6EF8rrec...``) is **deliberately not** referenced
anywhere in Stage 29.1; bonding-curve coverage is deferred to a
future explicitly-authorized substage that lands the bonding-curve
Anchor IDL first.

The PumpSwap program id and the Anchor BuyEvent / SellEvent event
discriminators below are public-chain artifacts of the Pump AMM
Anchor program (program address ``pAMMBay...``). They are pinned
here as Python literals; the authoritative provenance is the
vendored Anchor IDL at
``PHX2/proto/stage29_1/source/pump_amm.json``. The Stage 29.1
vendored-IDL test (``test_stage_29_1_vendored_idl.py``) reads
that file at test time and pins:

  * the IDL ``address`` field equals ``PUMPSWAP_PROGRAM_ID``
    byte-for-byte,
  * the IDL ``events`` BuyEvent / SellEvent discriminators equal
    the constants below byte-for-byte,
  * the vendored IDL file SHA-256 matches the pinned hash.

This module imports ONLY stdlib (``typing``). It does NOT import:

  * Stage 21-28 production code,
  * ``grpc`` / ``grpcio`` / ``protobuf`` / generated stubs,
  * any network / RPC / messaging / DB / scheduler / wallet /
    trading / Discord / Telegram / X / dotenv / keyring library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads.
  * No network.
  * No top-level I/O at import time.
  * No fabrication of SOL / USDC / mint / pool / program-id
    values; these constants are facts about a public Solana
    program, never substituted for missing evidence elsewhere in
    Stage 29.1.
  * No Pump.fun bonding-curve program id ships here at Stage
    29.1.
"""

from __future__ import annotations

from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 29.1 version axes
# ---------------------------------------------------------------------------


STAGE29_1_MINOR_VERSION: str = "29.1"
STAGE29_1_SCHEMA_VERSION: str = (
    "stage29_1_pumpswap_hint_extractor_v0"
)


# ---------------------------------------------------------------------------
# PumpSwap AMM program id (post-migration)
# ---------------------------------------------------------------------------


# Pump AMM (PumpSwap) Anchor program. Authoritative provenance:
# the ``address`` field of the vendored Anchor IDL at
# ``PHX2/proto/stage29_1/source/pump_amm.json``. The
# Stage 29.1 vendored-IDL test pins they match byte-for-byte.
PUMPSWAP_PROGRAM_ID: str = (
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)


# ---------------------------------------------------------------------------
# Known SPL mint constants (used ONLY for explicit-evidence matching)
# ---------------------------------------------------------------------------


# Canonical wrapped-SOL SPL mint. Stage 29.1 NEVER injects this
# value into a hint slot in the absence of evidence; it is used
# only to RECOGNIZE the value when it appears on a real
# TokenBalance.mint field on the upstream protobuf message.
WRAPPED_SOL_MINT: str = (
    "So11111111111111111111111111111111111111112"
)


# Canonical mainnet USDC SPL mint. Same discipline: never
# fabricated.
USDC_MINT: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


# Known quote-mint -> closed-set provider-pair-type-hint /
# bonding-curve-version-hint mapping. The closed-set hint token
# values are pinned here as plain string literals (matching the
# Stage 28.10 ``PAIR_TYPE_HINT_*`` /
# ``BONDING_CURVE_VERSION_HINT_*`` closed sets by string equality);
# Stage 29.1 must NOT import the Stage 28.10 constants here -- the
# Stage 29.1 import discipline forbids any sibling import from this
# constants module (it is leaf data only). The Stage 28.10
# hint-aware candidate assembler reads the hint slot's string by
# value, so equality is the contract.
KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT: Mapping[str, str] = {
    WRAPPED_SOL_MINT: "PUMP_SOL",
    USDC_MINT: "PUMP_USDC",
}


KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT: Mapping[str, str] = {
    WRAPPED_SOL_MINT: "SOL",
    USDC_MINT: "USDC",
}


# ---------------------------------------------------------------------------
# SPL Token program ids (used to filter TokenBalance entries)
# ---------------------------------------------------------------------------


SPL_TOKEN_PROGRAM_ID: str = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
)


SPL_TOKEN_2022_PROGRAM_ID: str = (
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
)


SPL_TOKEN_PROGRAM_IDS: tuple[str, ...] = (
    SPL_TOKEN_PROGRAM_ID,
    SPL_TOKEN_2022_PROGRAM_ID,
)


def is_spl_token_program_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is the classic SPL Token
    program id or the SPL Token-2022 program id.

    Pure / deterministic. Used by the Stage 29.1 hint extractor to
    filter the ``TokenBalance`` entries it considers; entries
    owned by any other program (mock token programs, future
    extensions, malformed entries) are ignored.
    """
    return (
        isinstance(value, str) and value in SPL_TOKEN_PROGRAM_IDS
    )


# ---------------------------------------------------------------------------
# PumpSwap Anchor event discriminators
# ---------------------------------------------------------------------------


# Anchor event discriminator for the PumpSwap ``BuyEvent`` event.
# 8 bytes; matches the ``events`` entry in the vendored
# ``pump_amm.json`` IDL byte-for-byte (see
# ``test_stage_29_1_vendored_idl.py``). Used only for OPTIONAL
# event-log confirmation that a tx is a PumpSwap swap; not used
# for pool / mint / quote extraction. Pool / mint / quote
# extraction uses the token-balance evidence rule documented in
# ``pumpswap_hint_extractor.py``.
PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES: bytes = bytes(
    (103, 244, 82, 31, 44, 245, 119, 119),
)


# Anchor event discriminator for the PumpSwap ``SellEvent`` event.
PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES: bytes = bytes(
    (62, 47, 55, 10, 165, 3, 220, 42),
)


PUMPSWAP_EVENT_DISCRIMINATORS: tuple[bytes, ...] = (
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
)


# ---------------------------------------------------------------------------
# Vendored IDL provenance (pinned for ``test_stage_29_1_vendored_idl.py``)
# ---------------------------------------------------------------------------


# SHA-256 of the vendored ``PHX2/proto/stage29_1/source/pump_amm.json``
# byte-for-byte. Test pins this matches the file on disk.
VENDORED_PUMP_AMM_IDL_SHA256: str = (
    "da268f6f26a1e89fa83ec47f1db7dbff8ce16f96564a683fad00353e1bf19443"
)


VENDORED_PUMP_AMM_IDL_BYTE_LENGTH: int = 136802


VENDORED_PUMP_AMM_IDL_RELATIVE_PATH: str = (
    "proto/stage29_1/source/pump_amm.json"
)


# Provenance description: the IDL is a vendored copy of the
# public Pump AMM Anchor IDL (the same JSON used by any
# Anchor-IDL consumer; see ``anchor idl fetch
# pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`` against any
# mainnet RPC). It is NOT a PHX1 artifact; PHX1 happens to vendor
# the same public IDL.
VENDORED_PUMP_AMM_IDL_PROVENANCE: str = (
    "public Pump AMM Anchor IDL "
    "(program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA); "
    "vendored copy under PHX2/proto/stage29_1/source/."
)


__all__ = (
    "STAGE29_1_MINOR_VERSION",
    "STAGE29_1_SCHEMA_VERSION",
    "PUMPSWAP_PROGRAM_ID",
    "WRAPPED_SOL_MINT",
    "USDC_MINT",
    "KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT",
    "KNOWN_QUOTE_MINT_TO_PROVIDER_QUOTE_ASSET_HINT",
    "SPL_TOKEN_PROGRAM_ID",
    "SPL_TOKEN_2022_PROGRAM_ID",
    "SPL_TOKEN_PROGRAM_IDS",
    "is_spl_token_program_id",
    "PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES",
    "PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES",
    "PUMPSWAP_EVENT_DISCRIMINATORS",
    "VENDORED_PUMP_AMM_IDL_SHA256",
    "VENDORED_PUMP_AMM_IDL_BYTE_LENGTH",
    "VENDORED_PUMP_AMM_IDL_RELATIVE_PATH",
    "VENDORED_PUMP_AMM_IDL_PROVENANCE",
)
