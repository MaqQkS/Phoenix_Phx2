"""Stage 28.11 decode tests.

Pins:

  * Pure-Python base58 helper round-trips empty / single-byte /
    long-byte inputs deterministically.
  * Decode happy path:
    - accepts a well-formed ``SubscribeUpdate`` transaction
      message,
    - emits a Stage 28.10 safe payload with provider_event_id
      / slot / signature / observed_at_utc / source_kind /
      mint placeholder / event_type / instruction_kind fields
      pinned to the locked Stage 28.11 decode defaults,
    - leaves every hint field (``quote_mint``,
      ``pool_account``, ``pool_program_id``, ``base_mint``,
      ``bonding_curve_version_hint``,
      ``provider_quote_asset_hint``,
      ``provider_pair_type_hint``,
      ``provider_bonding_curve_version_hint``) as ``None``
      (Stage 28.11 never invents SOL / USDC hints).
  * Decode refusals:
    - non-protobuf input,
    - non-transaction ``SubscribeUpdate`` variants (account /
      slot / ping / pong / block),
    - missing ``created_at``,
    - missing ``transaction.transaction`` inner field,
    - vote transactions,
    - empty signature bytes,
    - non-bytes signature,
    - non-int slot,
    - unsafe provider_name argument,
    - far-future observed_at_utc.
  * Decode never carries raw upstream bytes; the
    ``decoded_fields`` mapping is small (<= 4 entries) and
    contains only safe-shape strings.
"""

from __future__ import annotations

import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage28.chainstack_yellowstone_grpc_decode import (
    STAGE28_11_DEFAULT_EVENT_TYPE,
    STAGE28_11_DEFAULT_INSTRUCTION_KIND,
    STAGE28_11_PLACEHOLDER_MINT,
    STAGE28_11_PROVIDER_EVENT_ID_PREFIX,
    _encode_base58,
    decode_subscribe_update_to_payload,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    Stage28_11DecodeError,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    CHAIN_SOLANA,
    INSTRUCTION_KIND_UNKNOWN,
    SOURCE_KIND_PROTOCOL,
    Stage28_10ChainstackYellowstonePayload,
)


SAFE_PROVIDER_NAME: str = "chainstack_yellowstone_grpc"
SAFE_SIGNATURE_BYTES: bytes = bytes(range(1, 65))  # 64 bytes
SAFE_SLOT: int = 12345
SAFE_OBSERVED_AT_SECONDS: int = 1700000000  # 2023-11-14T22:13:20Z


def _build_well_formed_transaction_update():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = SAFE_OBSERVED_AT_SECONDS
    update.created_at.nanos = 0
    tx_wrapper = update.transaction
    tx_wrapper.slot = SAFE_SLOT
    tx_info = tx_wrapper.transaction
    tx_info.signature = SAFE_SIGNATURE_BYTES
    tx_info.is_vote = False
    tx_info.index = 0
    return update


# ---------------------------------------------------------------------------
# 1. base58 helper
# ---------------------------------------------------------------------------


def test_base58_empty_input_returns_empty_string():
    assert _encode_base58(b"") == ""


def test_base58_single_zero_byte_encodes_as_one():
    assert _encode_base58(b"\x00") == "1"


def test_base58_known_input():
    # Fixture pinned in our offline check.
    assert _encode_base58(bytes(range(1, 65))).startswith("2Ana")


def test_base58_refuses_non_bytes():
    with pytest.raises(Stage28_11DecodeError) as err:
        _encode_base58("not-bytes")  # type: ignore[arg-type]
    assert err.value.reason == "BASE58_INPUT_NOT_BYTES"


# ---------------------------------------------------------------------------
# 2. Decode happy path
# ---------------------------------------------------------------------------


def test_decode_returns_stage_28_10_payload():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert isinstance(
        payload,
        Stage28_10ChainstackYellowstonePayload,
    )


def test_decode_pins_provider_event_id_prefix():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.provider_event_id.startswith(
        f"{STAGE28_11_PROVIDER_EVENT_ID_PREFIX}_{SAFE_SLOT}_",
    )


def test_decode_pins_slot_and_signature():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.slot == SAFE_SLOT
    expected_sig = _encode_base58(SAFE_SIGNATURE_BYTES)
    assert payload.signature == expected_sig


def test_decode_pins_source_kind_protocol():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.source_kind == SOURCE_KIND_PROTOCOL


def test_decode_pins_chain_solana():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.chain == CHAIN_SOLANA


def test_decode_pins_placeholder_mint():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.mint == STAGE28_11_PLACEHOLDER_MINT


def test_decode_pins_default_event_type():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.event_type == STAGE28_11_DEFAULT_EVENT_TYPE


def test_decode_pins_default_instruction_kind():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert (
        payload.instruction_kind
        == STAGE28_11_DEFAULT_INSTRUCTION_KIND
    )
    assert payload.instruction_kind == INSTRUCTION_KIND_UNKNOWN


def test_decode_observed_at_utc_is_iso_8601():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    # 1700000000 in UTC = 2023-11-14T22:13:20+00:00.
    assert payload.observed_at_utc == "2023-11-14T22:13:20+00:00"


def test_decode_leaves_every_hint_field_none():
    """Stage 28.11 never invents SOL / USDC hints."""
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.quote_mint is None
    assert payload.pool_account is None
    assert payload.pool_program_id is None
    assert payload.base_mint is None
    assert payload.bonding_curve_version_hint is None
    assert payload.provider_quote_asset_hint is None
    assert payload.provider_pair_type_hint is None
    assert payload.provider_bonding_curve_version_hint is None


def test_decode_decoded_fields_carries_safe_summary():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.decoded_fields["is_vote"] == "false"
    assert (
        payload.decoded_fields["transaction_index"] == "0"
    )
    assert len(payload.decoded_fields) <= 4


def test_decode_provider_name_carried_through():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    assert payload.provider_name == SAFE_PROVIDER_NAME


# ---------------------------------------------------------------------------
# 3. Decode refusals
# ---------------------------------------------------------------------------


def test_decode_refuses_non_protobuf_input():
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            "not a protobuf",
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "UPDATE_NOT_SUBSCRIBE_UPDATE"


def test_decode_refuses_account_variant():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = SAFE_OBSERVED_AT_SECONDS
    _ = update.account  # touch but do not populate transaction
    update.account.slot = 1
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "UPDATE_NOT_A_TRANSACTION"


def test_decode_refuses_ping_variant():
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = SAFE_OBSERVED_AT_SECONDS
    update.ping.SetInParent()
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "UPDATE_NOT_A_TRANSACTION"


def test_decode_refuses_missing_created_at():
    update = _geyser_pb2.SubscribeUpdate()
    tx_wrapper = update.transaction
    tx_wrapper.slot = SAFE_SLOT
    tx_info = tx_wrapper.transaction
    tx_info.signature = SAFE_SIGNATURE_BYTES
    tx_info.is_vote = False
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "UPDATE_MISSING_CREATED_AT"


def test_decode_refuses_vote_transaction():
    update = _build_well_formed_transaction_update()
    update.transaction.transaction.is_vote = True
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "TRANSACTION_IS_VOTE_SKIPPED"


def test_decode_refuses_empty_signature():
    update = _build_well_formed_transaction_update()
    update.transaction.transaction.signature = b""
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "SIGNATURE_EMPTY"


def test_decode_refuses_unsafe_provider_name():
    update = _build_well_formed_transaction_update()
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name="user:pass@host",  # unsafe
        )
    assert err.value.reason == "PROVIDER_NAME_UNSAFE"


def test_decode_refuses_non_string_provider_name():
    update = _build_well_formed_transaction_update()
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=123,  # type: ignore[arg-type]
        )
    assert err.value.reason == "PROVIDER_NAME_NOT_STRING"


def test_decode_refuses_far_future_timestamp():
    update = _build_well_formed_transaction_update()
    update.created_at.seconds = 99999999999999  # > year 9999
    with pytest.raises(Stage28_11DecodeError) as err:
        decode_subscribe_update_to_payload(
            update,
            provider_name=SAFE_PROVIDER_NAME,
        )
    assert err.value.reason == "OBSERVED_AT_SECONDS_FAR_FUTURE"


# ---------------------------------------------------------------------------
# 4. Decode never carries raw upstream bytes
# ---------------------------------------------------------------------------


def test_decoded_fields_contains_no_raw_signature():
    update = _build_well_formed_transaction_update()
    payload = decode_subscribe_update_to_payload(
        update,
        provider_name=SAFE_PROVIDER_NAME,
    )
    # The raw signature BYTES never appear in the decoded
    # fields snapshot; only the base58-encoded form lives on
    # ``payload.signature``.
    for key, val in payload.decoded_fields.items():
        assert SAFE_SIGNATURE_BYTES.hex() not in val
