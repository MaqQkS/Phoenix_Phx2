"""Stage 28.11 Chainstack Yellowstone gRPC decode boundary.

This module projects an upstream Yellowstone protobuf
``SubscribeUpdate`` message into the safe Stage 28.10
``Stage28_10ChainstackYellowstonePayload`` record so the
existing Stage 28.10 event source / hint-aware candidate
assembler chain can drain real provider-backed events through
the same Protocol boundary the Stage 28.10 fake client already
satisfies.

This module IS allowed to import the generated Yellowstone
``geyser_pb2`` / ``solana_storage_pb2`` modules under
``PHX2.proto.stage28_11._generated`` (the Stage 28.11 boundary
scan whitelists this module as one of the few allowed to depend
on the generated protobuf stubs). It does NOT import:

  * the live gRPC channel layer (``grpc``) -- the decoder is
    pure with respect to a caller-supplied protobuf message,
  * Stage 21-27 production code,
  * any network / RPC / messaging / DB / scheduler library,
  * ``os`` / the process environment.

Discipline:

  * No env reads.
  * No network.
  * No sleep / no scheduling.
  * No top-level I/O at import time.
  * Decoded payloads carry only the Stage 28.10 safe-shape
    record fields; upstream bytes (raw transaction blobs, raw
    metadata) never appear on the output.
  * Hint fields stay ``None`` when the upstream message does
    not expose them (no SOL / USDC invention; the Stage 27
    chain owns the actual pair / pool / bonding-curve
    classification).
  * Errors raise ``Stage28_11DecodeError`` carrying a closed-
    set reason token; raw library tracebacks / raw upstream
    field values never leak through the exception.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11DecodeError,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    CHAIN_SOLANA,
    EVENT_TYPE_SWAP,
    INSTRUCTION_KIND_UNKNOWN,
    SOURCE_KIND_PROTOCOL,
    Stage28_10ChainstackYellowstoneError,
    Stage28_10ChainstackYellowstonePayload,
    build_chainstack_yellowstone_payload,
    is_safe_payload_string,
    is_safe_provider_label,
)
from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)


# ---------------------------------------------------------------------------
# Stage 28.11 decode-time defaults
# ---------------------------------------------------------------------------


# Locked safe-shape placeholder mint used when the upstream
# Yellowstone transaction update does not expose the base-token
# mint to the Stage 28.11 dry-run decoder. The Stage 28.10
# candidate assembler treats the placeholder mint as an UNKNOWN
# pair under the existing UNKNOWN / DISAGREE / USDC observe-only
# suppression rules. Stage 28.11 NEVER invents a SOL mint.
STAGE28_11_PLACEHOLDER_MINT: str = "stage28_11_unknown_mint"


# Locked Stage 28.11 decoder prefix used to derive the
# ``provider_event_id`` value from the upstream slot + signature
# pair. Keeps the decoded id safe-shape (the Stage 28.10
# ``is_safe_payload_string`` allowlist accepts ``yellowstone_``).
STAGE28_11_PROVIDER_EVENT_ID_PREFIX: str = "yellowstone"


# Locked Stage 28.11 decoder default for the ``event_type``
# field. The Stage 28.10 payload contract pins the closed-set
# ``EVENT_TYPE_*`` vocabulary; Stage 28.11 decodes every upstream
# transaction update as ``swap`` until a future substage adds
# instruction-level classification. The default is conservative
# (the Stage 28.10 candidate assembler routes UNKNOWN-pair
# candidates to observe-only suppression regardless).
STAGE28_11_DEFAULT_EVENT_TYPE: str = EVENT_TYPE_SWAP


# Locked Stage 28.11 decoder default for the ``instruction_kind``
# field. Closed-set ``INSTRUCTION_KIND_UNKNOWN`` keeps the
# decoder honest: Stage 28.11 does NOT parse Solana instructions
# itself, so it must report ``UNKNOWN`` here.
STAGE28_11_DEFAULT_INSTRUCTION_KIND: str = INSTRUCTION_KIND_UNKNOWN


# Cap on the decoded-fields snapshot the decoder emits. The
# Stage 28.10 payload contract permits up to 16 entries; Stage
# 28.11 stays well below.
_DECODED_FIELDS_MAX_KEYS: int = 4


# ---------------------------------------------------------------------------
# Pure-Python base58 encoder
# ---------------------------------------------------------------------------


# Standard base58 alphabet (matches the Solana / Bitcoin
# alphabet). The encoder is local to Stage 28.11 to avoid a
# third-party base58 dependency.
_BASE58_ALPHABET: str = (
    "123456789"
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)


def _encode_base58(raw: bytes) -> str:
    """Encode ``raw`` bytes as a base58 string.

    Pure / deterministic. No external library. Used only to
    convert a Solana transaction signature (``bytes``) into the
    base58 string form the Stage 28.10 payload's ``signature``
    field expects.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise Stage28_11DecodeError("BASE58_INPUT_NOT_BYTES")
    if len(raw) == 0:
        return ""
    leading_zeros = 0
    for byte in raw:
        if byte == 0:
            leading_zeros += 1
        else:
            break
    n = int.from_bytes(bytes(raw), byteorder="big")
    out_chars: list[str] = []
    while n > 0:
        n, rem = divmod(n, 58)
        out_chars.append(_BASE58_ALPHABET[rem])
    out_chars.append(_BASE58_ALPHABET[0] * leading_zeros)
    return "".join(reversed(out_chars))


# ---------------------------------------------------------------------------
# Upstream-shape helpers
# ---------------------------------------------------------------------------


def _has_field(message: object, name: str) -> bool:
    """Return ``True`` iff a protobuf-shaped ``message`` reports
    ``HasField(name)`` truthy. Tolerant of non-protobuf inputs
    so the decoder can refuse them deterministically."""
    has_field = getattr(message, "HasField", None)
    if not callable(has_field):
        return False
    try:
        return bool(has_field(name))
    except Exception:
        return False


def _timestamp_to_iso_utc(ts: Any) -> str:
    """Project a protobuf ``Timestamp`` value into an ISO-8601
    UTC string that passes the Stage 28.10 ``is_safe_iso_utc``
    validator.

    Raises ``Stage28_11DecodeError`` when the upstream value
    cannot be projected (out-of-range seconds, missing
    attribute).
    """
    seconds = getattr(ts, "seconds", None)
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise Stage28_11DecodeError(
            "OBSERVED_AT_SECONDS_NOT_INT",
        )
    if seconds < 0:
        raise Stage28_11DecodeError(
            "OBSERVED_AT_SECONDS_NEGATIVE",
        )
    if seconds > 253402300799:
        # Year 9999-12-31. Refuse pathological far-future
        # timestamps deterministically.
        raise Stage28_11DecodeError(
            "OBSERVED_AT_SECONDS_FAR_FUTURE",
        )
    try:
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise Stage28_11DecodeError(
            "OBSERVED_AT_FROM_TIMESTAMP_FAILED",
        )
    # ``datetime.isoformat()`` for a tz-aware UTC datetime
    # emits "YYYY-MM-DDTHH:MM:SS+00:00" -- 25 ASCII chars, in
    # the Stage 28.10 ``is_safe_iso_utc`` allowed alphabet
    # ``[0-9-T:.+Z]``, length 20-40.
    return dt.isoformat()


def _validate_signature_safe_shape(value: str) -> None:
    """Pin the base58-encoded signature passes the Stage 28.10
    safe-payload-string discipline.

    Stage 28.10 ``is_safe_payload_string`` rejects values that
    look private-key-like (WIF prefix ``5K`` / ``5J`` / ``5H`` /
    ``5L``, long pure-hex, JSON-array, base64-padded). A small
    fraction of legitimate base58 signatures starting with the
    WIF prefixes are conservatively rejected here.
    """
    if not is_safe_payload_string(value):
        # Distinguish WIF-prefix vs other unsafe shapes for
        # better operator diagnostics.
        if len(value) >= 2 and value[:2] in (
            "5K", "5J", "5H", "5L",
        ):
            raise Stage28_11DecodeError(
                "SIGNATURE_WIF_PREFIX_UNSAFE",
            )
        raise Stage28_11DecodeError("SIGNATURE_UNSAFE_SHAPE")


# ---------------------------------------------------------------------------
# Top-level decode entry point
# ---------------------------------------------------------------------------


def decode_subscribe_update_to_payload(
    update: object,
    *,
    provider_name: str,
) -> Stage28_10ChainstackYellowstonePayload:
    """Decode one Yellowstone ``SubscribeUpdate`` message into a
    Stage 28.10 ``Stage28_10ChainstackYellowstonePayload``.

    Pure / deterministic. The decoder:

      * refuses any input that is not a ``SubscribeUpdate``
        protobuf shape (not a generated message, missing
        ``HasField``, missing ``transaction`` field),
      * extracts the ``transaction.slot``,
        ``transaction.transaction.signature`` (base58),
        ``transaction.transaction.is_vote``, and
        ``transaction.transaction.index`` fields,
      * extracts the ``created_at`` Timestamp and projects it
        onto an ISO-8601 UTC string,
      * leaves ``mint`` at a locked Stage 28.11 placeholder
        because Stage 28.11 does NOT parse Solana instructions
        and so cannot resolve the base-token mint itself,
      * leaves every hint field (``quote_mint``,
        ``pool_account``, ``pool_program_id``, ``base_mint``,
        ``bonding_curve_version_hint``,
        ``provider_quote_asset_hint``,
        ``provider_pair_type_hint``,
        ``provider_bonding_curve_version_hint``) as ``None``
        because Stage 28.11 has no hint evidence (no SOL / USDC
        invention),
      * builds the safe payload via the Stage 28.10
        ``build_chainstack_yellowstone_payload`` factory which
        runs full validation.

    The decoder rejects vote transactions (Yellowstone often
    multiplexes vote transactions in the stream; Stage 28.11's
    dry-run targets a non-vote tx for inspection).

    Raises ``Stage28_11DecodeError`` (carrying a closed-set
    reason token) on any malformed input or unsafe upstream
    value. The raised exception never carries a raw upstream
    field value.
    """
    if not isinstance(provider_name, str):
        raise Stage28_11DecodeError(
            "PROVIDER_NAME_NOT_STRING",
        )
    if not is_safe_provider_label(provider_name):
        raise Stage28_11DecodeError(
            "PROVIDER_NAME_UNSAFE",
        )
    if not isinstance(update, _geyser_pb2.SubscribeUpdate):
        raise Stage28_11DecodeError(
            "UPDATE_NOT_SUBSCRIBE_UPDATE",
        )
    if not _has_field(update, "transaction"):
        raise Stage28_11DecodeError(
            "UPDATE_NOT_A_TRANSACTION",
        )
    if not _has_field(update, "created_at"):
        raise Stage28_11DecodeError(
            "UPDATE_MISSING_CREATED_AT",
        )

    observed_at_utc = _timestamp_to_iso_utc(update.created_at)

    tx_wrapper = update.transaction
    slot = getattr(tx_wrapper, "slot", None)
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise Stage28_11DecodeError(
            "TRANSACTION_SLOT_NOT_INT",
        )
    if slot < 0:
        raise Stage28_11DecodeError(
            "TRANSACTION_SLOT_NEGATIVE",
        )

    if not _has_field(tx_wrapper, "transaction"):
        raise Stage28_11DecodeError(
            "TRANSACTION_INFO_MISSING",
        )
    tx_info = tx_wrapper.transaction

    signature_bytes = getattr(tx_info, "signature", None)
    if not isinstance(signature_bytes, (bytes, bytearray)):
        raise Stage28_11DecodeError(
            "SIGNATURE_NOT_BYTES",
        )
    if len(signature_bytes) == 0:
        raise Stage28_11DecodeError(
            "SIGNATURE_EMPTY",
        )

    is_vote = bool(getattr(tx_info, "is_vote", False))
    if is_vote:
        raise Stage28_11DecodeError(
            "TRANSACTION_IS_VOTE_SKIPPED",
        )

    signature_b58 = _encode_base58(bytes(signature_bytes))
    if signature_b58 == "":
        raise Stage28_11DecodeError(
            "SIGNATURE_BASE58_EMPTY",
        )
    _validate_signature_safe_shape(signature_b58)

    transaction_index = getattr(tx_info, "index", 0)
    if (
        isinstance(transaction_index, bool)
        or not isinstance(transaction_index, int)
        or transaction_index < 0
    ):
        # Defensive: the upstream protobuf default is 0, but if
        # we get something weird, refuse rather than coerce
        # silently.
        raise Stage28_11DecodeError(
            "TRANSACTION_INDEX_UNSAFE",
        )

    signature_short = signature_b58[:16]
    provider_event_id = (
        f"{STAGE28_11_PROVIDER_EVENT_ID_PREFIX}"
        f"_{slot}_{signature_short}"
    )
    if not is_safe_payload_string(provider_event_id):
        raise Stage28_11DecodeError(
            "PROVIDER_EVENT_ID_UNSAFE",
        )

    decoded_fields = {
        "is_vote": "false",
        "transaction_index": str(transaction_index),
    }

    try:
        payload = build_chainstack_yellowstone_payload(
            provider_event_id=provider_event_id,
            provider_name=provider_name,
            source_kind=SOURCE_KIND_PROTOCOL,
            mint=STAGE28_11_PLACEHOLDER_MINT,
            event_type=STAGE28_11_DEFAULT_EVENT_TYPE,
            observed_at_utc=observed_at_utc,
            slot=slot,
            signature=signature_b58,
            instruction_kind=STAGE28_11_DEFAULT_INSTRUCTION_KIND,
            decoded_fields=decoded_fields,
            chain=CHAIN_SOLANA,
            quote_mint=None,
            pool_account=None,
            pool_program_id=None,
            base_mint=None,
            bonding_curve_version_hint=None,
            provider_quote_asset_hint=None,
            provider_pair_type_hint=None,
            provider_bonding_curve_version_hint=None,
        )
    except Stage28_10ChainstackYellowstoneError as err:
        # The Stage 28.10 factory rejected the projected fields
        # (e.g. a base58 signature unexpectedly tripped the
        # private-key-like guard). Re-wrap with a Stage 28.11
        # closed-set reason; the Stage 28.10 reason token is
        # safe to forward (closed-set), but we keep the Stage
        # 28.11 wrapper to mark the layer.
        raise Stage28_11DecodeError(
            f"STAGE_28_10_FACTORY_REJECTED:"
            f"{type(err).__name__}",
        )

    return payload


__all__ = (
    "STAGE28_11_PLACEHOLDER_MINT",
    "STAGE28_11_PROVIDER_EVENT_ID_PREFIX",
    "STAGE28_11_DEFAULT_EVENT_TYPE",
    "STAGE28_11_DEFAULT_INSTRUCTION_KIND",
    "decode_subscribe_update_to_payload",
)
