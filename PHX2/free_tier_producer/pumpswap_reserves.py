"""PumpSwap virtual-quote reserve decoding and reserve-derived analytics.

This module is the sole owner of the PumpSwap effective quote-reserve formula::

    effective_quote_reserves = raw_quote_vault_balance + virtual_quote_reserves

All binary decoders are exact-layout decoders.  A missing virtual reserve is
accepted only for a byte-for-byte legacy layout; malformed or future-unknown
lengths fail closed instead of being treated as legacy.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_PROGRAM_ID,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES,
    USDC_MINT,
)


I128_MIN = -(1 << 127)
I128_MAX = (1 << 127) - 1
U64_MAX = (1 << 64) - 1

PUMPSWAP_POOL_ACCOUNT_DISCRIMINATOR = bytes((241, 154, 109, 4, 17, 177, 109, 188))
POOL_LEGACY_LENGTH = 245
POOL_VIRTUAL_QUOTE_LENGTH = 261

POOL_LAYOUT_LEGACY = "PUMPSWAP_POOL_LEGACY_V1"
POOL_LAYOUT_VIRTUAL = "PUMPSWAP_POOL_VIRTUAL_QUOTE_I128_V2"
BUY_LAYOUT_LEGACY = "PUMPSWAP_BUY_EVENT_LEGACY_CASHBACK_V1"
BUY_LAYOUT_VIRTUAL = "PUMPSWAP_BUY_EVENT_VIRTUAL_QUOTE_I128_V2"
BUY_LAYOUT_BOOST = "PUMPSWAP_BUY_EVENT_BOOST_V3"
SELL_LAYOUT_LEGACY = "PUMPSWAP_SELL_EVENT_LEGACY_CASHBACK_V1"
SELL_LAYOUT_VIRTUAL = "PUMPSWAP_SELL_EVENT_VIRTUAL_QUOTE_I128_V2"
SELL_LAYOUT_BOOST = "PUMPSWAP_SELL_EVENT_BOOST_V3"

RESERVE_SOURCE_POOL_ACCOUNT = "PUMPSWAP_POOL_ACCOUNT_PLUS_RAW_VAULTS"
RESERVE_SOURCE_BUY_EVENT = "PUMPSWAP_BUY_EVENT"
RESERVE_SOURCE_SELL_EVENT = "PUMPSWAP_SELL_EVENT"
RESERVE_VALID = "VALID"
RESERVE_UNAVAILABLE = "UNAVAILABLE"
RESERVE_COMPARISON_VALID = "VALID_COMPARISON"
RESERVE_COMPARISON_DISCREPANCY = "PRICE_DISCREPANCY"
RESERVE_COMPARISON_UNAVAILABLE = "COMPARISON_UNAVAILABLE"
RESERVE_ROUTING_SCHEMA_VERSION = "phx2_trusted_reserve_market_v1"
RESERVE_ROUTING_SEAL_VERSION = "phx2_trusted_reserve_seal_v1"

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class PumpSwapReserveError(ValueError):
    """Closed-set-safe reserve decode/validation error."""


def _int_no_bool(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PumpSwapReserveError(f"{name}_must_be_int")
    return value


def _u64(name: str, value: object) -> int:
    number = _int_no_bool(name, value)
    if not (0 <= number <= U64_MAX):
        raise PumpSwapReserveError(f"{name}_outside_u64")
    return number


def _i128(name: str, value: object) -> int:
    number = _int_no_bool(name, value)
    if not (I128_MIN <= number <= I128_MAX):
        raise PumpSwapReserveError(f"{name}_outside_i128")
    return number


def effective_quote_reserves(
    raw_quote_vault_balance: object,
    virtual_quote_reserves: object,
) -> int:
    """Return the only valid PumpSwap quote reserve, failing closed on overflow.

    ``raw_quote_vault_balance`` is an SPL-token raw amount (u64).  PumpSwap's
    virtual component is signed i128.  The resulting effective reserve must fit
    signed i128 and be strictly positive.
    """

    raw = _u64("raw_quote_vault_balance", raw_quote_vault_balance)
    virtual = _i128("virtual_quote_reserves", virtual_quote_reserves)
    effective = raw + virtual
    if not (I128_MIN <= effective <= I128_MAX):
        raise PumpSwapReserveError("effective_quote_reserves_i128_overflow")
    if effective <= 0:
        raise PumpSwapReserveError("effective_quote_reserves_not_positive")
    return effective


def _base58_encode(raw: bytes) -> str:
    if len(raw) != 32:
        raise PumpSwapReserveError("pubkey_length_invalid")
    return _base58_encode_bytes(raw)


def _base58_encode_bytes(raw: bytes) -> str:
    if not isinstance(raw, bytes) or not raw:
        raise PumpSwapReserveError("base58_payload_invalid")
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big", signed=False)
    chars = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_BASE58_ALPHABET[rem])
    return "1" * zeros + "".join(reversed(chars))


def _decimal_text(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, "f")


def _positive_decimal(name: str, value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PumpSwapReserveError(f"{name}_invalid")
    if not number.is_finite() or number <= 0:
        raise PumpSwapReserveError(f"{name}_not_positive_finite")
    return number


def _optional_decimals(name: str, value: object) -> Optional[int]:
    if value is None:
        return None
    number = _int_no_bool(name, value)
    if not (0 <= number <= 255):
        raise PumpSwapReserveError(f"{name}_invalid")
    return number


@dataclass(frozen=True)
class PumpSwapReserveArtifact:
    """Validated internal reserve contract used by every downstream formula."""

    raw_quote_reserves: int
    virtual_quote_reserves: int
    effective_quote_reserves: int
    base_reserves: int
    reserve_source: str
    observation_timestamp: str
    decoder_layout_version: str
    pool_address: Optional[str] = None
    base_mint: Optional[str] = None
    quote_mint: Optional[str] = None
    base_decimals: Optional[int] = None
    quote_decimals: Optional[int] = None
    event_side: Optional[str] = None
    event_timestamp: Optional[int] = None
    base_supply: Optional[int] = None
    quote_amount_raw: Optional[int] = None
    quote_amount_basis: Optional[str] = None

    def __post_init__(self) -> None:
        expected = effective_quote_reserves(
            self.raw_quote_reserves, self.virtual_quote_reserves)
        if _i128("effective_quote_reserves", self.effective_quote_reserves) != expected:
            raise PumpSwapReserveError("effective_quote_reserves_mismatch")
        _u64("base_reserves", self.base_reserves)
        if self.base_reserves <= 0:
            raise PumpSwapReserveError("base_reserves_not_positive")
        if not isinstance(self.reserve_source, str) or not self.reserve_source:
            raise PumpSwapReserveError("reserve_source_required")
        if not isinstance(self.observation_timestamp, str) or not self.observation_timestamp:
            raise PumpSwapReserveError("observation_timestamp_required")
        if not isinstance(self.decoder_layout_version, str) or not self.decoder_layout_version:
            raise PumpSwapReserveError("decoder_layout_version_required")
        _optional_decimals("base_decimals", self.base_decimals)
        _optional_decimals("quote_decimals", self.quote_decimals)
        if self.event_timestamp is not None:
            _int_no_bool("event_timestamp", self.event_timestamp)
        if self.base_supply is not None:
            _u64("base_supply", self.base_supply)
        if self.quote_amount_raw is not None:
            if _u64("quote_amount_raw", self.quote_amount_raw) <= 0:
                raise PumpSwapReserveError("quote_amount_raw_not_positive")
            if self.event_side not in ("BUY", "SELL"):
                raise PumpSwapReserveError("quote_amount_event_side_required")
            expected_basis = (
                "QUOTE_AMOUNT_IN" if self.event_side == "BUY"
                else "QUOTE_AMOUNT_OUT")
            if self.quote_amount_basis != expected_basis:
                raise PumpSwapReserveError("quote_amount_basis_invalid")

    def to_dict(self) -> Dict[str, Any]:
        # Raw amounts are emitted as decimal text so JavaScript/dashboard readers
        # cannot silently lose precision above 2**53.
        return {
            "raw_quote_reserves": str(self.raw_quote_reserves),
            "virtual_quote_reserves": str(self.virtual_quote_reserves),
            "effective_quote_reserves": str(self.effective_quote_reserves),
            "base_reserves": str(self.base_reserves),
            "reserve_source": self.reserve_source,
            "observation_timestamp": self.observation_timestamp,
            "decoder_layout_version": self.decoder_layout_version,
            "pool_address": self.pool_address,
            "base_mint": self.base_mint,
            "quote_mint": self.quote_mint,
            "base_decimals": self.base_decimals,
            "quote_decimals": self.quote_decimals,
            "event_side": self.event_side,
            "event_timestamp": self.event_timestamp,
            "base_supply": (None if self.base_supply is None else str(self.base_supply)),
            "quote_amount_raw": (
                None if self.quote_amount_raw is None
                else str(self.quote_amount_raw)),
            "quote_amount_basis": self.quote_amount_basis,
            "reserve_validation_status": RESERVE_VALID,
        }


@dataclass(frozen=True)
class TrustedReserveMarketObservation:
    """Fully-bound reserve observation eligible for current price/MC routing.

    Construction is internal to :class:`PumpSwapReserveIndex`; decoded reserve
    telemetry alone is intentionally insufficient.  The sealed migration proof
    supplies the canonical pool and vault identity, while the transaction event
    supplies exact signature/slot/instruction identity and succeeded status.
    """

    mint: str
    pool_address: str
    base_vault: str
    quote_vault: str
    quote_mint: str
    base_decimals: int
    quote_decimals: int
    base_supply: int
    raw_quote_reserves: int
    virtual_quote_reserves: int
    effective_quote_reserves: int
    base_reserves: int
    transaction_signature: str
    slot: int
    outer_instruction_index: int
    inner_instruction_index: Optional[int]
    flattened_instruction_index: int
    event_index: int
    source_timestamp: str
    ingestion_timestamp: str
    migration_proof_digest: str
    source_evidence_digest: str
    observation_seal_digest: str
    transaction_succeeded: bool
    source_event_proven: bool
    reserve_trusted_for_routing: bool
    event_side: Optional[str] = None
    quote_amount_raw: Optional[int] = None
    quote_amount_basis: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": RESERVE_ROUTING_SCHEMA_VERSION,
            "mint": self.mint,
            "pool_address": self.pool_address,
            "base_vault": self.base_vault,
            "quote_vault": self.quote_vault,
            "quote_mint": self.quote_mint,
            "base_decimals": self.base_decimals,
            "quote_decimals": self.quote_decimals,
            "base_supply": str(self.base_supply),
            "raw_quote_reserves": str(self.raw_quote_reserves),
            "virtual_quote_reserves": str(self.virtual_quote_reserves),
            "effective_quote_reserves": str(self.effective_quote_reserves),
            "base_reserves": str(self.base_reserves),
            "transaction_signature": self.transaction_signature,
            "slot": self.slot,
            "outer_instruction_index": self.outer_instruction_index,
            "inner_instruction_index": self.inner_instruction_index,
            "flattened_instruction_index": self.flattened_instruction_index,
            "event_index": self.event_index,
            "source_timestamp": self.source_timestamp,
            "ingestion_timestamp": self.ingestion_timestamp,
            "migration_proof_digest": self.migration_proof_digest,
            "source_evidence_digest": self.source_evidence_digest,
            "observation_seal_version": RESERVE_ROUTING_SEAL_VERSION,
            "observation_seal_digest": self.observation_seal_digest,
            "transaction_succeeded": self.transaction_succeeded,
            "source_event_proven": self.source_event_proven,
            "event_side": self.event_side,
            "quote_amount_raw": (
                None if self.quote_amount_raw is None
                else str(self.quote_amount_raw)),
            "quote_amount_basis": self.quote_amount_basis,
            "pool_replacement_conflict": False,
            "reserve_trusted_for_routing": self.reserve_trusted_for_routing,
        }


class _Reader:
    def __init__(self, data: bytes, offset: int = 0) -> None:
        if not isinstance(data, bytes):
            raise PumpSwapReserveError("binary_payload_must_be_bytes")
        self.data = data
        self.offset = offset

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise PumpSwapReserveError("binary_payload_truncated")
        out = self.data[self.offset:self.offset + size]
        self.offset += size
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def boolean(self) -> bool:
        value = self.u8()
        if value not in (0, 1):
            raise PumpSwapReserveError("borsh_bool_invalid")
        return bool(value)

    def u16(self) -> int:
        return int.from_bytes(self.take(2), "little", signed=False)

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "little", signed=False)

    def u64(self) -> int:
        return int.from_bytes(self.take(8), "little", signed=False)

    def i64(self) -> int:
        return int.from_bytes(self.take(8), "little", signed=True)

    def i128(self) -> int:
        return int.from_bytes(self.take(16), "little", signed=True)

    def pubkey(self) -> str:
        return _base58_encode(self.take(32))

    def skip_pubkey(self) -> None:
        """Advance past a 32-byte pubkey the caller discards.

        Equivalent to ``pubkey()`` for cursor advancement and truncation
        checking, without the base58 encode of a value that is thrown away.
        """
        self.take(32)

    def string(self) -> str:
        size = self.u32()
        if size > 256 or size > self.remaining:
            raise PumpSwapReserveError("borsh_string_length_invalid")
        try:
            return self.take(size).decode("utf-8")
        except UnicodeDecodeError:
            raise PumpSwapReserveError("borsh_string_utf8_invalid")


def _event_observation_timestamp(event_timestamp: int, observed_at_utc: Optional[str]) -> str:
    if isinstance(observed_at_utc, str) and observed_at_utc:
        return observed_at_utc
    try:
        return datetime.fromtimestamp(event_timestamp, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        raise PumpSwapReserveError("event_timestamp_invalid")


def _parse_observation_epoch(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number and number not in (
            float("inf"), float("-inf")) else None
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).timestamp()


def decode_pool_account(
    data: bytes,
    *,
    raw_quote_vault_balance: object,
    raw_base_vault_balance: object,
    observation_timestamp: str,
    pool_address: Optional[str] = None,
    base_decimals: Optional[int] = None,
    quote_decimals: Optional[int] = None,
) -> PumpSwapReserveArtifact:
    """Decode an exact legacy/new PumpSwap Pool account plus its raw vaults."""

    if not isinstance(data, bytes):
        raise PumpSwapReserveError("pool_account_must_be_bytes")
    if len(data) not in (POOL_LEGACY_LENGTH, POOL_VIRTUAL_QUOTE_LENGTH):
        raise PumpSwapReserveError("pool_account_length_unknown")
    reader = _Reader(data)
    if reader.take(8) != PUMPSWAP_POOL_ACCOUNT_DISCRIMINATOR:
        raise PumpSwapReserveError("pool_account_discriminator_mismatch")
    reader.u8()  # pool_bump
    reader.u16()  # index
    reader.pubkey()  # creator
    base_mint = reader.pubkey()
    quote_mint = reader.pubkey()
    reader.pubkey()  # lp_mint
    reader.pubkey()  # pool_base_token_account
    reader.pubkey()  # pool_quote_token_account
    reader.u64()  # lp_supply
    reader.pubkey()  # coin_creator
    reader.boolean()  # is_mayhem_mode
    reader.boolean()  # is_cashback_coin
    if len(data) == POOL_LEGACY_LENGTH:
        virtual = 0
        layout = POOL_LAYOUT_LEGACY
    else:
        virtual = reader.i128()
        layout = POOL_LAYOUT_VIRTUAL
    if reader.remaining != 0:
        raise PumpSwapReserveError("pool_account_trailing_bytes")
    raw_quote = _u64("raw_quote_vault_balance", raw_quote_vault_balance)
    base = _u64("raw_base_vault_balance", raw_base_vault_balance)
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw_quote,
        virtual_quote_reserves=virtual,
        effective_quote_reserves=effective_quote_reserves(raw_quote, virtual),
        base_reserves=base,
        reserve_source=RESERVE_SOURCE_POOL_ACCOUNT,
        observation_timestamp=observation_timestamp,
        decoder_layout_version=layout,
        pool_address=pool_address,
        base_mint=base_mint,
        quote_mint=quote_mint,
        base_decimals=base_decimals,
        quote_decimals=quote_decimals,
    )


def _decode_event_tail(reader: _Reader, *, side: str) -> Tuple[int, str, Optional[int]]:
    remaining = reader.remaining
    if remaining == 0:
        virtual = 0
        layout = BUY_LAYOUT_LEGACY if side == "BUY" else SELL_LAYOUT_LEGACY
        base_supply = None
    elif remaining == 16:
        virtual = reader.i128()
        layout = BUY_LAYOUT_VIRTUAL if side == "BUY" else SELL_LAYOUT_VIRTUAL
        base_supply = None
    elif remaining == 41:
        # Current published boost-era layout: two existing buyback u64 fields,
        # then virtual i128, can_boost bool, and base_supply u64.
        reader.u64()
        reader.u64()
        virtual = reader.i128()
        reader.boolean()
        base_supply = reader.u64()
        layout = BUY_LAYOUT_BOOST if side == "BUY" else SELL_LAYOUT_BOOST
    else:
        raise PumpSwapReserveError("event_suffix_length_unknown")
    if reader.remaining != 0:
        raise PumpSwapReserveError("event_trailing_bytes")
    return virtual, layout, base_supply


def decode_buy_event(
    data: bytes,
    *,
    observed_at_utc: Optional[str] = None,
    base_mint: Optional[str] = None,
    quote_mint: Optional[str] = None,
    base_decimals: Optional[int] = None,
    quote_decimals: Optional[int] = None,
) -> PumpSwapReserveArtifact:
    """Decode exact legacy, virtual-i128, or published boost BuyEvent layouts."""

    reader = _Reader(data)
    if reader.take(8) != PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES:
        raise PumpSwapReserveError("buy_event_discriminator_mismatch")
    event_timestamp = reader.i64()
    reader.u64()  # base_amount_out
    reader.u64()  # max_quote_amount_in
    reader.u64()  # user_base_token_reserves
    reader.u64()  # user_quote_token_reserves
    base_reserves = reader.u64()
    raw_quote_reserves = reader.u64()
    quote_amount_raw = reader.u64()  # actual quote_amount_in
    for _ in range(6):
        reader.u64()
    pool = reader.pubkey()
    for _ in range(6):
        reader.skip_pubkey()  # six discarded pubkeys: advance, do not base58
    reader.u64()  # coin_creator_fee_basis_points
    reader.u64()  # coin_creator_fee
    reader.boolean()  # track_volume
    reader.u64()  # total_unclaimed_tokens
    reader.u64()  # total_claimed_tokens
    reader.u64()  # current_sol_volume
    reader.i64()  # last_update_timestamp
    reader.u64()  # min_base_amount_out
    reader.string()  # ix_name
    reader.u64()  # cashback_fee_basis_points
    reader.u64()  # cashback
    virtual, layout, base_supply = _decode_event_tail(reader, side="BUY")
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw_quote_reserves,
        virtual_quote_reserves=virtual,
        effective_quote_reserves=effective_quote_reserves(raw_quote_reserves, virtual),
        base_reserves=base_reserves,
        reserve_source=RESERVE_SOURCE_BUY_EVENT,
        observation_timestamp=_event_observation_timestamp(event_timestamp, observed_at_utc),
        decoder_layout_version=layout,
        pool_address=pool,
        base_mint=base_mint,
        quote_mint=quote_mint,
        base_decimals=base_decimals,
        quote_decimals=quote_decimals,
        event_side="BUY",
        event_timestamp=event_timestamp,
        base_supply=base_supply,
        quote_amount_raw=quote_amount_raw,
        quote_amount_basis="QUOTE_AMOUNT_IN",
    )


def decode_sell_event(
    data: bytes,
    *,
    observed_at_utc: Optional[str] = None,
    base_mint: Optional[str] = None,
    quote_mint: Optional[str] = None,
    base_decimals: Optional[int] = None,
    quote_decimals: Optional[int] = None,
) -> PumpSwapReserveArtifact:
    """Decode exact legacy, virtual-i128, or published boost SellEvent layouts."""

    reader = _Reader(data)
    if reader.take(8) != PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES:
        raise PumpSwapReserveError("sell_event_discriminator_mismatch")
    event_timestamp = reader.i64()
    reader.u64()  # base_amount_in
    reader.u64()  # min_quote_amount_out
    reader.u64()  # user_base_token_reserves
    reader.u64()  # user_quote_token_reserves
    base_reserves = reader.u64()
    raw_quote_reserves = reader.u64()
    quote_amount_raw = reader.u64()  # actual quote_amount_out
    for _ in range(6):
        reader.u64()
    pool = reader.pubkey()
    for _ in range(6):
        reader.skip_pubkey()  # six discarded pubkeys: advance, do not base58
    reader.u64()  # coin_creator_fee_basis_points
    reader.u64()  # coin_creator_fee
    reader.u64()  # cashback_fee_basis_points
    reader.u64()  # cashback
    virtual, layout, base_supply = _decode_event_tail(reader, side="SELL")
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw_quote_reserves,
        virtual_quote_reserves=virtual,
        effective_quote_reserves=effective_quote_reserves(raw_quote_reserves, virtual),
        base_reserves=base_reserves,
        reserve_source=RESERVE_SOURCE_SELL_EVENT,
        observation_timestamp=_event_observation_timestamp(event_timestamp, observed_at_utc),
        decoder_layout_version=layout,
        pool_address=pool,
        base_mint=base_mint,
        quote_mint=quote_mint,
        base_decimals=base_decimals,
        quote_decimals=quote_decimals,
        event_side="SELL",
        event_timestamp=event_timestamp,
        base_supply=base_supply,
        quote_amount_raw=quote_amount_raw,
        quote_amount_basis="QUOTE_AMOUNT_OUT",
    )


def reserve_price_quote_units(artifact: PumpSwapReserveArtifact) -> Decimal:
    """Effective-reserve-derived price in whole quote tokens per base token."""

    if not isinstance(artifact, PumpSwapReserveArtifact):
        raise PumpSwapReserveError("validated_reserve_artifact_required")
    if artifact.base_decimals is None or artifact.quote_decimals is None:
        raise PumpSwapReserveError("reserve_decimals_required")
    scale = Decimal(10) ** Decimal(artifact.base_decimals - artifact.quote_decimals)
    return (Decimal(artifact.effective_quote_reserves) / Decimal(artifact.base_reserves)) * scale


def reserve_price_usd(
    artifact: PumpSwapReserveArtifact, *, quote_price_usd: object
) -> Decimal:
    return reserve_price_quote_units(artifact) * _positive_decimal(
        "quote_price_usd", quote_price_usd)


def reserve_market_cap_usd(
    artifact: PumpSwapReserveArtifact,
    *,
    quote_price_usd: object,
    base_supply: Optional[object] = None,
) -> Decimal:
    supply_raw = artifact.base_supply if base_supply is None else base_supply
    supply = _u64("base_supply", supply_raw)
    if artifact.base_decimals is None:
        raise PumpSwapReserveError("base_decimals_required")
    return reserve_price_usd(artifact, quote_price_usd=quote_price_usd) * (
        Decimal(supply) / (Decimal(10) ** artifact.base_decimals))


def reserve_liquidity_usd(
    artifact: PumpSwapReserveArtifact, *, quote_price_usd: object
) -> Decimal:
    """Two-sided effective-reserve liquidity, using effective quote reserves."""

    if not isinstance(artifact, PumpSwapReserveArtifact):
        raise PumpSwapReserveError("validated_reserve_artifact_required")
    if artifact.quote_decimals is None:
        raise PumpSwapReserveError("quote_decimals_required")
    quote_tokens = Decimal(artifact.effective_quote_reserves) / (
        Decimal(10) ** artifact.quote_decimals)
    return Decimal(2) * quote_tokens * _positive_decimal(
        "quote_price_usd", quote_price_usd)


def actual_quote_liquidity_usd(
    artifact: PumpSwapReserveArtifact, *, quote_price_usd: object
) -> Decimal:
    """Withdrawable quote-vault value; virtual reserves are excluded."""

    if not isinstance(artifact, PumpSwapReserveArtifact):
        raise PumpSwapReserveError("validated_reserve_artifact_required")
    if artifact.quote_decimals is None:
        raise PumpSwapReserveError("quote_decimals_required")
    quote_tokens = Decimal(artifact.raw_quote_reserves) / (
        Decimal(10) ** artifact.quote_decimals)
    return quote_tokens * _positive_decimal(
        "quote_price_usd", quote_price_usd)


def actual_token_liquidity_usd(
    artifact: PumpSwapReserveArtifact, *, base_price_usd: object
) -> Decimal:
    """Actual base-token vault balance valued at the accepted current price."""

    if not isinstance(artifact, PumpSwapReserveArtifact):
        raise PumpSwapReserveError("validated_reserve_artifact_required")
    if artifact.base_decimals is None:
        raise PumpSwapReserveError("base_decimals_required")
    base_tokens = Decimal(artifact.base_reserves) / (
        Decimal(10) ** artifact.base_decimals)
    return base_tokens * _positive_decimal(
        "base_price_usd", base_price_usd)


def actual_pool_tvl_usd(
    artifact: PumpSwapReserveArtifact,
    *,
    quote_price_usd: object,
    base_price_usd: object,
) -> Decimal:
    """Total actual TVL: real quote side plus the real token-vault side."""

    return (
        actual_quote_liquidity_usd(
            artifact, quote_price_usd=quote_price_usd)
        + actual_token_liquidity_usd(
            artifact, base_price_usd=base_price_usd)
    )


def buy_quote_input_raw(
    artifact: PumpSwapReserveArtifact, *, base_amount_out_raw: object
) -> Decimal:
    """Fee-free constant-product buy quote reconstruction from effective reserves."""

    amount = _u64("base_amount_out_raw", base_amount_out_raw)
    if amount <= 0 or amount >= artifact.base_reserves:
        raise PumpSwapReserveError("base_amount_out_impossible")
    return (Decimal(artifact.effective_quote_reserves) * Decimal(amount)) / Decimal(
        artifact.base_reserves - amount)


def sell_quote_output_raw(
    artifact: PumpSwapReserveArtifact, *, base_amount_in_raw: object
) -> Decimal:
    """Fee-free constant-product sell quote reconstruction from effective reserves."""

    amount = _u64("base_amount_in_raw", base_amount_in_raw)
    if amount <= 0:
        raise PumpSwapReserveError("base_amount_in_not_positive")
    return (Decimal(artifact.effective_quote_reserves) * Decimal(amount)) / Decimal(
        artifact.base_reserves + amount)


def reserve_price_drawdown_pct(*, current_price: object, ath_price: object) -> Decimal:
    current = _positive_decimal("current_price", current_price)
    ath = _positive_decimal("ath_price", ath_price)
    if current >= ath:
        return Decimal(0)
    return ((ath - current) / ath) * Decimal(100)


class PumpSwapReserveIndex:
    """Thread-safe in-memory index fed by the already-owned gRPC stream."""

    def __init__(self, *, ath_store: Any = None, proof_store: Any = None,
                 now_fn: Callable[[], float] = time.time,
                 routing_max_age_seconds: float = 15.0,
                 quote_price_max_age_seconds: float = 30.0,
                 canonical_observer_allow_historical: bool = False) -> None:
        self._lock = threading.Lock()
        self._by_mint: Dict[str, PumpSwapReserveArtifact] = {}
        self._pool_to_mint: Dict[str, str] = {}
        self._mint_to_pool: Dict[str, str] = {}
        self._pool_quote_mint: Dict[str, str] = {}
        self._quote_prices: Dict[str, Decimal] = {USDC_MINT: Decimal(1)}
        self._quote_price_timestamps: Dict[str, float] = {USDC_MINT: float(now_fn())}
        self._pool_conflicts: set[str] = set()
        self._routing_by_mint: Dict[str, TrustedReserveMarketObservation] = {}
        self._routing_observers: List[Callable[[Dict[str, Any]], None]] = []
        # Provider-independent canonical reserve observers receive the sealed
        # trusted routing payload before quote-price enrichment. Returning
        # false is a required-state persistence failure.
        self._canonical_reserve_observers: List[
            Callable[[Dict[str, Any]], bool]
        ] = []
        self._required_observer_failed = False
        self._last_required_observer_failure_reason: Optional[str] = None
        self._quote_request_observers: List[Callable[[str], None]] = []
        self._ath_price: Dict[str, Decimal] = {}
        self._ath_market_cap: Dict[str, Decimal] = {}
        self._decoded = 0
        self._rejected = 0
        self._routing_accepted = 0
        self._routing_rejected = 0
        # Duck-typed to avoid a circular import: ath_state owns reserve math
        # through this module, while the reserve index merely forwards already
        # validated events into the one central state owner.
        self._ath_store = ath_store
        self._proof_store = proof_store
        self._now = now_fn
        self._routing_max_age = max(1.0, float(routing_max_age_seconds))
        self._canonical_observer_allow_historical = bool(
            canonical_observer_allow_historical
        )
        self._quote_price_max_age = max(1.0, float(quote_price_max_age_seconds))

    def bind_proof_store(self, proof_store: Any) -> None:
        """Bind the existing sealed migration-proof owner before stream start."""

        with self._lock:
            self._proof_store = proof_store

    def add_routing_observer(self, observer: Callable[[Dict[str, Any]], None]) -> bool:
        if not callable(observer):
            return False
        with self._lock:
            if observer not in self._routing_observers:
                self._routing_observers.append(observer)
        return True

    def add_canonical_reserve_observer(
        self, observer: Callable[[Dict[str, Any]], bool]
    ) -> bool:
        if not callable(observer):
            return False
        with self._lock:
            if observer not in self._canonical_reserve_observers:
                self._canonical_reserve_observers.append(observer)
        return True

    def consume_required_observer_failure(self) -> bool:
        with self._lock:
            failed = bool(self._required_observer_failed)
            self._required_observer_failed = False
            return failed

    def last_required_observer_failure_reason(self) -> Optional[str]:
        with self._lock:
            return self._last_required_observer_failure_reason

    def add_quote_request_observer(self, observer: Callable[[str], None]) -> bool:
        if not callable(observer):
            return False
        with self._lock:
            if observer not in self._quote_request_observers:
                self._quote_request_observers.append(observer)
        return True

    def _migration_identity_allowed(self, mint: str, pool: object, quote: object) -> bool:
        """Keep legacy indexing; new suffixless keys require sealed pool binding."""
        if mint.endswith("pump"):
            return True
        from PHX2.free_tier_producer.migration_admission import candidate_migration_proof
        try:
            raw = getattr(self._proof_store, "get", lambda _mint: None)(mint)
            proof = candidate_migration_proof(raw)
        except Exception:
            return False
        return bool(proof is not None and proof.candidate_mint == mint
                    and proof.pool == pool and proof.quote_mint == quote)

    def register_pool(self, *, pool_address: object, base_mint: object,
                      quote_mint: object, creation_timestamp: object = None) -> bool:
        from PHX2.free_tier_producer.migration_admission import is_supported_mint_identity
        # Discovery owns admission; indexing preserves the exact proven key.
        if not is_supported_mint_identity(base_mint):
            return False
        if not isinstance(pool_address, str) or not pool_address:
            return False
        if not isinstance(quote_mint, str) or not quote_mint:
            return False
        if not self._migration_identity_allowed(base_mint, pool_address, quote_mint):
            return False
        with self._lock:
            existing_pool = self._mint_to_pool.get(base_mint)
            existing_mint = self._pool_to_mint.get(pool_address)
            if ((existing_pool is not None and existing_pool != pool_address)
                    or (existing_mint is not None and existing_mint != base_mint)):
                self._pool_conflicts.add(base_mint)
                self._rejected += 1
                return False
            # First canonical binding wins. Re-observation of the same binding
            # is idempotent; replacement can never silently redirect routing.
            self._pool_to_mint[pool_address] = base_mint
            self._mint_to_pool[base_mint] = pool_address
            self._pool_quote_mint[pool_address] = quote_mint
        register = getattr(self._ath_store, "register_pool", None)
        if callable(register):
            try:
                if not register(
                    mint=base_mint,
                    pool_address=pool_address,
                    quote_mint=quote_mint,
                    creation_timestamp=creation_timestamp,
                ):
                    return False
            except Exception:
                return False
        return True

    def record(
        self,
        *,
        base_mint: object,
        artifact: object,
        transaction_signature: object = None,
        event_index: object = None,
        slot: object = None,
        outer_instruction_index: object = None,
        inner_instruction_index: object = None,
        flattened_instruction_index: object = None,
        transaction_succeeded: bool = False,
        source_event_proven: bool = False,
        ingestion_timestamp: object = None,
    ) -> bool:
        from PHX2.free_tier_producer.migration_admission import is_supported_mint_identity
        if not is_supported_mint_identity(base_mint):
            with self._lock:
                self._rejected += 1
            return False
        if not isinstance(artifact, PumpSwapReserveArtifact):
            with self._lock:
                self._rejected += 1
            return False
        if artifact.base_mint not in (None, base_mint):
            with self._lock:
                self._rejected += 1
                self._routing_rejected += 1
            return False
        if not self._migration_identity_allowed(base_mint, artifact.pool_address, artifact.quote_mint):
            with self._lock:
                self._rejected += 1
            return False
        with self._lock:
            canonical_pool = self._mint_to_pool.get(base_mint)
            pool_conflict = base_mint in self._pool_conflicts
        if (canonical_pool is not None
                and artifact.pool_address != canonical_pool):
            with self._lock:
                self._rejected += 1
                self._routing_rejected += 1
            return False
        with self._lock:
            self._by_mint[base_mint] = artifact
            if artifact.pool_address:
                if artifact.quote_mint:
                    self._pool_quote_mint[artifact.pool_address] = artifact.quote_mint
            self._decoded += 1
            quote_price = (
                self._quote_prices.get(artifact.quote_mint)
                if artifact.quote_mint else None
            )
        observe = getattr(self._ath_store, "observe_event", None)
        if callable(observe):
            try:
                if not observe(
                    mint=base_mint,
                    artifact=artifact,
                    transaction_signature=transaction_signature,
                    event_index=event_index,
                    quote_price_usd=quote_price,
                    last_updated_at=artifact.observation_timestamp,
                ):
                    # A duplicate central event is still a successfully decoded
                    # reserve update.  It must not be counted twice as a central
                    # observation, but keeping the latest reserve artifact is
                    # harmless and preserves existing telemetry behavior.
                    pass
            except Exception:
                # Central ATH is fail-closed; reserve telemetry remains useful.
                pass
        routing = self._build_trusted_routing_observation(
            base_mint=base_mint,
            artifact=artifact,
            transaction_signature=transaction_signature,
            event_index=event_index,
            slot=slot,
            outer_instruction_index=outer_instruction_index,
            inner_instruction_index=inner_instruction_index,
            flattened_instruction_index=flattened_instruction_index,
            transaction_succeeded=transaction_succeeded,
            source_event_proven=source_event_proven,
            ingestion_timestamp=ingestion_timestamp,
            pool_conflict=pool_conflict,
        )
        if routing is not None:
            if not self._emit_canonical_reserve(routing):
                return False
            source_epoch = _parse_observation_epoch(
                routing.source_timestamp
            )
            ingestion_epoch = _parse_observation_epoch(
                routing.ingestion_timestamp
            )
            historical_canonical_only = (
                source_epoch is not None
                and ingestion_epoch is not None
                and ingestion_epoch - source_epoch > self._routing_max_age
            )
            if not historical_canonical_only:
                with self._lock:
                    previous = self._routing_by_mint.get(base_mint)
                    previous_epoch = (
                        _parse_observation_epoch(previous.source_timestamp)
                        if previous is not None else None)
                    routing_epoch = _parse_observation_epoch(
                        routing.source_timestamp
                    )
                    previous_order = (
                        previous.slot, previous.outer_instruction_index,
                        -1 if previous.inner_instruction_index is None
                        else previous.inner_instruction_index,
                        previous.flattened_instruction_index,
                        previous.event_index,
                    ) if previous is not None else ()
                    routing_order = (
                        routing.slot, routing.outer_instruction_index,
                        -1 if routing.inner_instruction_index is None
                        else routing.inner_instruction_index,
                        routing.flattened_instruction_index,
                        routing.event_index,
                    )
                    if (
                        previous is None
                        or previous_epoch is None
                        or (
                            routing_epoch is not None
                            and (
                                routing_epoch > previous_epoch
                                or (
                                    routing_epoch == previous_epoch
                                    and routing_order > previous_order
                                )
                            )
                        )
                    ):
                        self._routing_by_mint[base_mint] = routing
                        self._routing_accepted += 1
                if not self._emit_routing_if_priced(base_mint):
                    self._request_quote_price(routing.quote_mint)
        elif self._proof_store is not None:
            with self._lock:
                self._routing_rejected += 1
        return True

    def _emit_canonical_reserve(
        self, routing: TrustedReserveMarketObservation
    ) -> bool:
        with self._lock:
            observers = list(self._canonical_reserve_observers)
        payload = routing.to_dict()
        for observer in observers:
            try:
                if not bool(observer(dict(payload))):
                    with self._lock:
                        self._required_observer_failed = True
                        self._last_required_observer_failure_reason = (
                            "OBSERVER_RETURNED_FALSE"
                        )
                    return False
            except Exception as exc:
                detail = str(exc)
                if (
                    not detail
                    or len(detail) > 120
                    or detail.upper() != detail
                    or not all(
                        char.isalnum() or char in "_:-" for char in detail
                    )
                ):
                    detail = type(exc).__name__
                with self._lock:
                    self._required_observer_failed = True
                    self._last_required_observer_failure_reason = detail
                return False
        return True

    def _build_trusted_routing_observation(
        self, *, base_mint: str, artifact: PumpSwapReserveArtifact,
        transaction_signature: object, event_index: object, slot: object,
        outer_instruction_index: object, inner_instruction_index: object,
        flattened_instruction_index: object, transaction_succeeded: bool,
        source_event_proven: bool, ingestion_timestamp: object,
        pool_conflict: bool,
    ) -> Optional[TrustedReserveMarketObservation]:
        proof_store = self._proof_store
        proof = getattr(proof_store, "get", lambda _mint: None)(base_mint)
        if proof is None or pool_conflict:
            return None
        # Local import avoids a module-level cycle with migration admission.
        try:
            from PHX2.free_tier_producer.migration_admission import validate_migration_proof
            proof_valid, _reason = validate_migration_proof(proof)
        except Exception:
            return None
        if not proof_valid:
            return None
        if not (transaction_succeeded is True and source_event_proven is True):
            return None
        if not (isinstance(transaction_signature, str) and transaction_signature
                and isinstance(event_index, int) and not isinstance(event_index, bool)
                and event_index >= 0
                and isinstance(slot, int) and not isinstance(slot, bool) and slot >= 0
                and isinstance(outer_instruction_index, int)
                and not isinstance(outer_instruction_index, bool)
                and outer_instruction_index >= 0
                and (inner_instruction_index is None
                     or (isinstance(inner_instruction_index, int)
                         and not isinstance(inner_instruction_index, bool)
                         and inner_instruction_index >= 0))
                and isinstance(flattened_instruction_index, int)
                and not isinstance(flattened_instruction_index, bool)
                and flattened_instruction_index >= 0):
            return None
        if not (artifact.pool_address == getattr(proof, "pool", None)
                and artifact.base_mint == getattr(proof, "base_mint", None)
                and artifact.quote_mint == getattr(proof, "quote_mint", None)
                and base_mint == getattr(proof, "candidate_mint", None)
                and getattr(proof, "vault_derivation_valid", False) is True
                and getattr(proof, "vault_ownership_valid", False) is True
                and isinstance(getattr(proof, "base_vault", None), str)
                and isinstance(getattr(proof, "quote_vault", None), str)):
            return None
        if not (artifact.base_decimals is not None
                and artifact.quote_decimals is not None
                and artifact.base_supply is not None and artifact.base_supply > 0
                and artifact.quote_decimals == getattr(proof, "quote_deposit_decimals", None)
                and (getattr(proof, "base_deposit_decimals", None) is None
                     or artifact.base_decimals == getattr(proof, "base_deposit_decimals"))):
            return None
        source_epoch = _parse_observation_epoch(artifact.observation_timestamp)
        ingested_epoch = (_parse_observation_epoch(ingestion_timestamp)
                          if isinstance(ingestion_timestamp, str)
                          else (float(ingestion_timestamp)
                                if isinstance(ingestion_timestamp, (int, float))
                                and not isinstance(ingestion_timestamp, bool) else self._now()))
        if source_epoch is None or ingested_epoch is None:
            return None
        if source_epoch > ingested_epoch + 2.0:
            return None
        if (
            not self._canonical_observer_allow_historical
            and ingested_epoch - source_epoch > self._routing_max_age
        ):
            return None
        ingestion_iso = datetime.fromtimestamp(
            ingested_epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        evidence_payload = {
            "schema_version": RESERVE_ROUTING_SCHEMA_VERSION,
            "mint": base_mint,
            "pool_address": artifact.pool_address,
            "base_vault": proof.base_vault,
            "quote_vault": proof.quote_vault,
            "quote_mint": artifact.quote_mint,
            "base_decimals": artifact.base_decimals,
            "quote_decimals": artifact.quote_decimals,
            "base_supply": str(artifact.base_supply),
            "raw_quote_reserves": str(artifact.raw_quote_reserves),
            "virtual_quote_reserves": str(artifact.virtual_quote_reserves),
            "effective_quote_reserves": str(artifact.effective_quote_reserves),
            "base_reserves": str(artifact.base_reserves),
            "event_side": artifact.event_side,
            "quote_amount_raw": (
                None if artifact.quote_amount_raw is None
                else str(artifact.quote_amount_raw)),
            "quote_amount_basis": artifact.quote_amount_basis,
            "transaction_signature": transaction_signature,
            "slot": slot,
            "outer_instruction_index": outer_instruction_index,
            "inner_instruction_index": inner_instruction_index,
            "flattened_instruction_index": flattened_instruction_index,
            "event_index": event_index,
            "source_timestamp": artifact.observation_timestamp,
            "migration_proof_digest": proof.proof_digest,
            "transaction_succeeded": True,
            "source_event_proven": True,
        }
        evidence_digest = hashlib.sha256(json.dumps(
            evidence_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        seal_digest = hashlib.sha256(json.dumps({
            "seal_version": RESERVE_ROUTING_SEAL_VERSION,
            "source_evidence_digest": evidence_digest,
            "ingestion_timestamp": ingestion_iso,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return TrustedReserveMarketObservation(
            mint=base_mint,
            pool_address=str(artifact.pool_address),
            base_vault=proof.base_vault,
            quote_vault=proof.quote_vault,
            quote_mint=str(artifact.quote_mint),
            base_decimals=int(artifact.base_decimals),
            quote_decimals=int(artifact.quote_decimals),
            base_supply=int(artifact.base_supply),
            raw_quote_reserves=artifact.raw_quote_reserves,
            virtual_quote_reserves=artifact.virtual_quote_reserves,
            effective_quote_reserves=artifact.effective_quote_reserves,
            base_reserves=artifact.base_reserves,
            transaction_signature=transaction_signature,
            slot=slot,
            outer_instruction_index=outer_instruction_index,
            inner_instruction_index=inner_instruction_index,
            flattened_instruction_index=flattened_instruction_index,
            event_index=event_index,
            source_timestamp=artifact.observation_timestamp,
            ingestion_timestamp=ingestion_iso,
            migration_proof_digest=proof.proof_digest,
            source_evidence_digest=evidence_digest,
            observation_seal_digest=seal_digest,
            transaction_succeeded=True,
            source_event_proven=True,
            reserve_trusted_for_routing=True,
            event_side=artifact.event_side,
            quote_amount_raw=artifact.quote_amount_raw,
            quote_amount_basis=artifact.quote_amount_basis,
        )

    def latest(self, mint: object) -> Optional[PumpSwapReserveArtifact]:
        if not isinstance(mint, str):
            return None
        with self._lock:
            return self._by_mint.get(mint)

    def quote_mint_for(self, mint: object) -> Optional[str]:
        artifact = self.latest(mint)
        return artifact.quote_mint if artifact is not None else None

    def cache_quote_price(self, quote_mint: object, price_usd: object,
                          *, observed_at: object = None) -> bool:
        if not isinstance(quote_mint, str) or not quote_mint:
            return False
        try:
            price = _positive_decimal("quote_price_usd", price_usd)
        except PumpSwapReserveError:
            return False
        observed_epoch = _parse_observation_epoch(observed_at)
        if observed_epoch is None:
            observed_epoch = float(self._now())
        with self._lock:
            self._quote_prices[quote_mint] = price
            self._quote_price_timestamps[quote_mint] = observed_epoch
        observe_quote = getattr(self._ath_store, "observe_quote_price", None)
        if callable(observe_quote):
            try:
                observe_quote(quote_mint, price)
            except Exception:
                return False
        # A reserve event may have arrived before the shared quote price. A
        # later valid quote-price update makes that same sealed event routable
        # without another base-mint price request.
        with self._lock:
            pending_mints = [
                mint for mint, routing in self._routing_by_mint.items()
                if routing.quote_mint == quote_mint]
        for mint in pending_mints:
            self._emit_routing_if_priced(mint)
        return True

    def quote_price_snapshot(
        self, quote_mint: object, *, now_epoch: Optional[float] = None,
    ) -> Optional[Dict[str, str]]:
        """Return a fresh, already-owned USD quote without doing network I/O."""

        if not isinstance(quote_mint, str) or not quote_mint:
            return None
        now = float(self._now() if now_epoch is None else now_epoch)
        with self._lock:
            price = self._quote_prices.get(quote_mint)
            observed = self._quote_price_timestamps.get(quote_mint)
        if price is None or observed is None:
            return None
        if quote_mint != USDC_MINT and now - observed > self._quote_price_max_age:
            return None
        return {
            "quote_mint": quote_mint,
            "price_usd": _decimal_text(price) or "",
            "observed_at_utc": datetime.fromtimestamp(
                observed, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def latest_routing_observation(
        self, mint: object, *, now_epoch: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(mint, str):
            return None
        now = float(self._now() if now_epoch is None else now_epoch)
        with self._lock:
            routing = self._routing_by_mint.get(mint)
            if routing is None or mint in self._pool_conflicts:
                return None
            quote_price = self._quote_prices.get(routing.quote_mint)
            quote_at = self._quote_price_timestamps.get(routing.quote_mint)
        source_epoch = _parse_observation_epoch(routing.source_timestamp)
        quote_stale = bool(
            routing.quote_mint != USDC_MINT
            and (quote_at is None or now - quote_at > self._quote_price_max_age))
        if (source_epoch is None or now - source_epoch > self._routing_max_age
                or quote_price is None or quote_at is None or quote_stale):
            return None
        try:
            artifact = PumpSwapReserveArtifact(
                raw_quote_reserves=routing.raw_quote_reserves,
                virtual_quote_reserves=routing.virtual_quote_reserves,
                effective_quote_reserves=routing.effective_quote_reserves,
                base_reserves=routing.base_reserves,
                reserve_source=RESERVE_SOURCE_BUY_EVENT,
                observation_timestamp=routing.source_timestamp,
                decoder_layout_version="TRUSTED_ROUTING_REHYDRATED",
                pool_address=routing.pool_address,
                base_mint=routing.mint,
                quote_mint=routing.quote_mint,
                base_decimals=routing.base_decimals,
                quote_decimals=routing.quote_decimals,
                base_supply=routing.base_supply,
                event_side=routing.event_side,
                quote_amount_raw=routing.quote_amount_raw,
                quote_amount_basis=routing.quote_amount_basis,
            )
            price = reserve_price_usd(artifact, quote_price_usd=quote_price)
            market_cap = reserve_market_cap_usd(
                artifact, quote_price_usd=quote_price)
        except PumpSwapReserveError:
            return None
        return {
            **routing.to_dict(),
            "current_price": _decimal_text(price),
            "current_market_cap_usd": _decimal_text(market_cap),
            "quote_price_usd": _decimal_text(quote_price),
            "quote_price_observed_at_utc": datetime.fromtimestamp(
                quote_at, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _emit_routing_if_priced(self, mint: str) -> bool:
        payload = self.latest_routing_observation(mint)
        if payload is None:
            return False
        with self._lock:
            observers = list(self._routing_observers)
        emitted = False
        for observer in observers:
            try:
                observer(dict(payload))
                emitted = True
            except Exception:
                continue
        return emitted

    def _request_quote_price(self, quote_mint: str) -> None:
        if quote_mint == USDC_MINT:
            return
        with self._lock:
            observers = list(self._quote_request_observers)
        for observer in observers:
            try:
                observer(quote_mint)
            except Exception:
                continue

    def compare_market(
        self,
        mint: object,
        *,
        birdeye_price_usd: object,
        quote_price_usd: object = None,
        discrepancy_warn_pct: object = Decimal("20"),
    ) -> Dict[str, Any]:
        artifact = self.latest(mint)
        if artifact is None:
            return {
                "reserve_validation_status": RESERVE_UNAVAILABLE,
                "comparison_status": RESERVE_COMPARISON_UNAVAILABLE,
                "reserve_trusted_for_routing": False,
            }
        telemetry: Dict[str, Any] = {
            "reserve_validation_status": RESERVE_VALID,
            "comparison_status": RESERVE_COMPARISON_UNAVAILABLE,
            "reserve_trusted_for_routing": False,
            "reserve_artifact": artifact.to_dict(),
        }
        try:
            birdeye = _positive_decimal("birdeye_price_usd", birdeye_price_usd)
            quote_price_supplied = quote_price_usd is not None
            quote_price_at = None
            if artifact.quote_mint:
                with self._lock:
                    quote_price_at = self._quote_price_timestamps.get(
                        artifact.quote_mint)
                    if quote_price_usd is None:
                        quote_price_usd = self._quote_prices.get(
                            artifact.quote_mint)
            quote_price = _positive_decimal("quote_price_usd", quote_price_usd)
            warn = _positive_decimal("discrepancy_warn_pct", discrepancy_warn_pct)
            if artifact.quote_mint and quote_price_supplied:
                quote_price_at = None
                self.cache_quote_price(artifact.quote_mint, quote_price)
                if quote_price_at is None:
                    with self._lock:
                        quote_price_at = self._quote_price_timestamps.get(
                            artifact.quote_mint)
            reserve_price = reserve_price_usd(artifact, quote_price_usd=quote_price)
            liquidity = reserve_liquidity_usd(artifact, quote_price_usd=quote_price)
            actual_quote_liquidity = actual_quote_liquidity_usd(
                artifact, quote_price_usd=quote_price)
            actual_token_liquidity = actual_token_liquidity_usd(
                artifact, base_price_usd=birdeye)
            actual_tvl = actual_quote_liquidity + actual_token_liquidity
            market_cap: Optional[Decimal] = None
            if artifact.base_supply is not None:
                market_cap = reserve_market_cap_usd(
                    artifact, quote_price_usd=quote_price)
            discrepancy = (abs(birdeye - reserve_price) / birdeye) * Decimal(100)
            central_snapshot = getattr(self._ath_store, "snapshot", None)
            central = None
            if callable(central_snapshot):
                try:
                    central = central_snapshot(mint)
                except Exception:
                    central = None
            if isinstance(central, dict):
                ath_price = _positive_decimal(
                    "central_ath_price", central.get("ath_price"))
                raw_ath_mc = central.get("ath_market_cap")
                ath_mc = (
                    _positive_decimal("central_ath_market_cap", raw_ath_mc)
                    if raw_ath_mc is not None else None
                )
            else:
                # Legacy reserve-only callers have no central store.  Preserve
                # their observe-only telemetry without affecting paid runtime.
                with self._lock:
                    prior_ath = self._ath_price.get(str(mint))
                    ath_price = reserve_price if prior_ath is None else max(prior_ath, reserve_price)
                    self._ath_price[str(mint)] = ath_price
                    ath_mc = None
                    if market_cap is not None:
                        prior_ath_mc = self._ath_market_cap.get(str(mint))
                        ath_mc = market_cap if prior_ath_mc is None else max(prior_ath_mc, market_cap)
                        self._ath_market_cap[str(mint)] = ath_mc
            telemetry.update({
                "comparison_status": (
                    RESERVE_COMPARISON_DISCREPANCY
                    if discrepancy >= warn else RESERVE_COMPARISON_VALID
                ),
                # Artifact keys must stay provider-neutral: the production
                # redaction contract rejects vendor names in durable output.
                "reference_price_usd": _decimal_text(birdeye),
                "effective_reserve_price_usd": _decimal_text(reserve_price),
                "effective_reserve_market_cap_usd": _decimal_text(market_cap),
                "effective_reserve_liquidity_usd": _decimal_text(liquidity),
                "actual_quote_liquidity_usd": _decimal_text(
                    actual_quote_liquidity),
                "actual_token_liquidity_usd": _decimal_text(
                    actual_token_liquidity),
                "actual_pool_tvl_usd": _decimal_text(actual_tvl),
                "actual_liquidity_definition": (
                    "REAL_QUOTE_VAULT_PLUS_REAL_BASE_VAULT_AT_ACCEPTED_CURRENT_PRICE"),
                "quote_side_liquidity_definition": "REAL_QUOTE_VAULT_ONLY",
                "quote_price_usd": _decimal_text(quote_price),
                "quote_price_observed_at_utc": (
                    datetime.fromtimestamp(
                        quote_price_at, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if quote_price_at is not None else None),
                "effective_reserve_ath_price_usd": _decimal_text(ath_price),
                "effective_reserve_ath_market_cap_usd": _decimal_text(ath_mc),
                "effective_reserve_drawdown_pct": _decimal_text(
                    reserve_price_drawdown_pct(current_price=reserve_price, ath_price=ath_price)),
                "price_discrepancy_pct": _decimal_text(discrepancy),
                "discrepancy_warn_pct": _decimal_text(warn),
            })
        except PumpSwapReserveError:
            # Malformed/missing provider or decimal context never promotes the
            # on-chain value to a trusted market input.
            pass
        return telemetry

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "reserve_events_decoded": self._decoded,
                "reserve_events_rejected": self._rejected,
                "reserve_mints_indexed": len(self._by_mint),
                "reserve_pools_indexed": len(self._pool_to_mint),
                "reserve_routing_observations": self._routing_accepted,
                "reserve_routing_rejected": self._routing_rejected,
                "reserve_pool_conflicts": len(self._pool_conflicts),
            }


def _unwrap_transaction_meta(update: object) -> Optional[Any]:
    try:
        return update.transaction.transaction.meta
    except Exception:
        return None


def _unwrap_transaction_message(update: object) -> Optional[Any]:
    try:
        return update.transaction.transaction.transaction.message
    except Exception:
        return None


@dataclass(frozen=True)
class _ExactInstructionIdentity:
    outer_index: int
    inner_index: Optional[int]
    flattened_index: int


def _pumpswap_instruction_identities(
    message: object, meta: object,
) -> Optional[List[_ExactInstructionIdentity]]:
    """Return exact PumpSwap instruction sites in runtime invocation order.

    ``flattened_index`` deliberately matches the existing migration-proof
    convention: all top-level instruction positions first, followed by each
    serialized inner instruction.  The returned list itself follows runtime
    order so PumpSwap ``invoke`` log frames can be bound one-for-one.
    Ambiguous/duplicate inner groups fail closed.
    """

    try:
        from PHX2.free_tier_producer.migration_admission import (
            _collect_account_keys,
            _program_key_matches,
            PUMPSWAP_PROGRAM_ID_BYTES,
        )
        top = list(getattr(message, "instructions", ()) or ())
        keys = _collect_account_keys(message, meta)
    except Exception:
        return None

    groups: Dict[int, List[Tuple[int, int, Any]]] = {}
    flattened = len(top)
    for group in list(getattr(meta, "inner_instructions", ()) or ()):
        try:
            outer_index = int(getattr(group, "index"))
            instructions = list(getattr(group, "instructions", ()) or ())
        except Exception:
            return None
        if (outer_index in groups or outer_index < 0
                or outer_index >= len(top)):
            return None
        group_entries: List[Tuple[int, int, Any]] = []
        for inner_index, instruction in enumerate(instructions):
            group_entries.append((inner_index, flattened, instruction))
            flattened += 1
        groups[outer_index] = group_entries

    identities: List[_ExactInstructionIdentity] = []
    for outer_index, instruction in enumerate(top):
        try:
            program_index = int(instruction.program_id_index)
        except Exception:
            return None
        if _program_key_matches(keys, program_index, PUMPSWAP_PROGRAM_ID_BYTES):
            identities.append(_ExactInstructionIdentity(
                outer_index=outer_index,
                inner_index=None,
                flattened_index=outer_index,
            ))
        for inner_index, flattened_index, inner in groups.get(outer_index, ()):
            try:
                program_index = int(inner.program_id_index)
            except Exception:
                return None
            if _program_key_matches(keys, program_index, PUMPSWAP_PROGRAM_ID_BYTES):
                identities.append(_ExactInstructionIdentity(
                    outer_index=outer_index,
                    inner_index=inner_index,
                    flattened_index=flattened_index,
                ))
    return identities


def _transaction_signature(update: object) -> Optional[str]:
    try:
        raw = bytes(update.transaction.transaction.signature)
        return _base58_encode_bytes(raw) if len(raw) == 64 else None
    except Exception:
        return None


def _token_balance_context(meta: object) -> Tuple[Optional[str], Optional[str], Dict[str, int]]:
    mints: Dict[str, int] = {}
    for attr in ("pre_token_balances", "post_token_balances"):
        for balance in list(getattr(meta, attr, ()) or ()):
            mint = getattr(balance, "mint", None)
            decimals = getattr(getattr(balance, "ui_token_amount", None), "decimals", None)
            if isinstance(mint, str) and mint and isinstance(decimals, int) and not isinstance(decimals, bool):
                mints[mint] = decimals
    # A unique non-quote balance is the only safe fallback. Multiple token
    # mints are ambiguous; instruction-bound routing remains authoritative.
    base = [mint for mint in mints if mint not in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT]
    quote = [mint for mint in mints if mint in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT]
    return (
        base[0] if len(base) == 1 else None,
        quote[0] if len(quote) == 1 else None,
        mints,
    )


def _program_data_payloads(logs: Iterable[object]) -> Iterable[bytes]:
    prefix = "Program data: "
    for value in logs:
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        try:
            yield base64.b64decode(value[len(prefix):], validate=True)
        except (ValueError, TypeError):
            continue


def _program_data_payloads_with_context(
    logs: Iterable[object], *, message: object, meta: object,
) -> Iterable[Tuple[bytes, Optional[_ExactInstructionIdentity], bool]]:
    """Yield payload, exact instruction identity, and active-PumpSwap proof.

    Bare program-data lines remain useful comparison telemetry but can never
    become trusted routing observations.
    """

    expected = _pumpswap_instruction_identities(message, meta)
    stack: List[Tuple[str, Optional[_ExactInstructionIdentity]]] = []
    parsed: List[Tuple[bytes, Optional[_ExactInstructionIdentity], bool]] = []
    pumpswap_invocations = 0
    data_prefix = "Program data: "
    invoke_marker = " invoke ["
    for value in logs:
        if not isinstance(value, str):
            continue
        if value.startswith("Program ") and invoke_marker in value:
            program = value[len("Program "):value.index(invoke_marker)]
            identity = None
            if program == PUMPSWAP_PROGRAM_ID:
                if expected is not None and pumpswap_invocations < len(expected):
                    identity = expected[pumpswap_invocations]
                pumpswap_invocations += 1
            stack.append((program, identity))
            continue
        if value.startswith("Program ") and (
                value.endswith(" success") or " failed:" in value):
            program = value[len("Program "):].split(" ", 1)[0]
            if stack and stack[-1][0] == program:
                stack.pop()
            else:
                matching = [index for index, frame in enumerate(stack)
                            if frame[0] == program]
                if matching:
                    del stack[matching[-1]:]
            continue
        if not value.startswith(data_prefix):
            continue
        try:
            payload = base64.b64decode(value[len(data_prefix):], validate=True)
        except (ValueError, TypeError):
            continue
        identity = stack[-1][1] if stack and stack[-1][0] == PUMPSWAP_PROGRAM_ID else None
        parsed.append((payload, identity, identity is not None))

    identity_set_complete = bool(
        expected is not None and pumpswap_invocations == len(expected))
    for payload, identity, proven in parsed:
        yield payload, identity, bool(proven and identity_set_complete)


def ingest_reserve_events_from_update(
    update: object, *, reserve_index: PumpSwapReserveIndex
) -> int:
    """Decode Buy/Sell reserve events from the existing transaction stream.

    This function opens no subscription and performs no I/O.  It is called for
    updates already received by ``PaidCreatePoolYellowstoneSource``.
    """

    if not isinstance(reserve_index, PumpSwapReserveIndex):
        return 0
    meta = _unwrap_transaction_meta(update)
    message = _unwrap_transaction_message(update)
    if meta is None:
        return 0
    # Trusted reserve routing shares the ONE fail-closed execution-status
    # boundary with migration admission (PHX2-E2E-007): only a canonically
    # successful transaction is treated as succeeded, so a failed, malformed,
    # unsupported or otherwise indeterminate error representation can never open
    # the trusted price/market-cap routing path.  No looser parser is duplicated
    # here.
    from PHX2.free_tier_producer.migration_admission import _transaction_failed
    transaction_succeeded = not _transaction_failed(meta)
    base_mint, quote_mint, decimals = _token_balance_context(meta)
    # The PHX2 pump filter is applied before reserve indexing/enrichment.
    if base_mint is None or quote_mint is None:
        return 0
    signature = _transaction_signature(update)
    if signature is None:
        # Legacy/offline reserve-only callers have no transaction signature in
        # their tiny fake update.  The central ATH path is stricter because its
        # durable dedupe key cannot be fabricated.
        if getattr(reserve_index, "_ath_store", None) is not None:
            return 0
        signature = "OFFLINE_RESERVE_ONLY_NO_SIGNATURE"
    count = 0
    event_index = 0
    try:
        slot = int(update.transaction.slot)
    except (TypeError, ValueError, AttributeError):
        slot = None
    ingested_at = time.time()
    for payload, instruction_identity, source_event_proven in (
            _program_data_payloads_with_context(
                list(getattr(meta, "log_messages", ()) or ()),
                message=message, meta=meta)):
        try:
            kwargs = {
                "base_mint": base_mint,
                "quote_mint": quote_mint,
                "base_decimals": decimals.get(base_mint),
                "quote_decimals": decimals.get(quote_mint),
            }
            if payload.startswith(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES):
                artifact = decode_buy_event(payload, **kwargs)
            elif payload.startswith(PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES):
                artifact = decode_sell_event(payload, **kwargs)
            else:
                continue
            current_event_index = event_index
            event_index += 1
            if reserve_index.record(
                base_mint=base_mint,
                artifact=artifact,
                transaction_signature=signature,
                event_index=current_event_index,
                slot=slot,
                outer_instruction_index=(
                    instruction_identity.outer_index
                    if instruction_identity is not None else None),
                inner_instruction_index=(
                    instruction_identity.inner_index
                    if instruction_identity is not None else None),
                flattened_instruction_index=(
                    instruction_identity.flattened_index
                    if instruction_identity is not None else None),
                transaction_succeeded=transaction_succeeded,
                source_event_proven=source_event_proven,
                ingestion_timestamp=ingested_at,
            ):
                count += 1
        except PumpSwapReserveError:
            # Preserve discriminator ordering even when a matching event fails
            # layout validation, so a later valid event gets a stable key.
            if (payload.startswith(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES)
                    or payload.startswith(PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES)):
                event_index += 1
            continue
    return count


__all__ = (
    "I128_MIN", "I128_MAX", "U64_MAX", "POOL_LEGACY_LENGTH",
    "POOL_VIRTUAL_QUOTE_LENGTH", "POOL_LAYOUT_LEGACY", "POOL_LAYOUT_VIRTUAL",
    "BUY_LAYOUT_LEGACY", "BUY_LAYOUT_VIRTUAL", "BUY_LAYOUT_BOOST",
    "SELL_LAYOUT_LEGACY", "SELL_LAYOUT_VIRTUAL", "SELL_LAYOUT_BOOST",
    "RESERVE_VALID", "RESERVE_ROUTING_SCHEMA_VERSION", "RESERVE_ROUTING_SEAL_VERSION",
    "PumpSwapReserveError", "PumpSwapReserveArtifact", "TrustedReserveMarketObservation",
    "PumpSwapReserveIndex", "effective_quote_reserves", "decode_pool_account",
    "decode_buy_event", "decode_sell_event", "reserve_price_quote_units",
    "reserve_price_usd", "reserve_market_cap_usd", "reserve_liquidity_usd",
    "actual_quote_liquidity_usd", "actual_token_liquidity_usd",
    "actual_pool_tvl_usd",
    "buy_quote_input_raw", "sell_quote_output_raw", "reserve_price_drawdown_pct",
    "ingest_reserve_events_from_update",
)
