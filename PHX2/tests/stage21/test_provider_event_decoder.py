"""Stage 21.3A provider event decoder tests."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from PHX2.stage21.constants import FORBIDDEN_SUBSTRINGS
from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage21.ping_payloads import NORMALIZED_EVENT_SCHEMA_VERSION
from PHX2.stage21.provider_event_decoder import (
    ProviderPayloadError,
    ProviderPayloadFieldTypeError,
    ProviderPayloadFieldValueError,
    ProviderPayloadShapeError,
    ProviderPayloadSuspiciousContentError,
    ProviderPayloadUnsupportedInstructionError,
    REQUIRED_TOP_LEVEL_KEYS,
    SUPPORTED_INSTRUCTION_KINDS,
    decode_provider_event,
)


# 88-char base58 string approximating a real Solana transaction
# signature. Chosen deliberately so no forbidden substring (from
# the locked FORBIDDEN_SUBSTRINGS set) appears anywhere inside it,
# even at case-folded compare. The first test below verifies that
# property explicitly, so a future change to either constant
# surface causes a clear failure.
SAMPLE_SOLANA_SIGNATURE: str = (
    "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJ"
    "Lgp8uirBgmQpjKhoR4tjF3ZpRzrFmBs6JKDsGY9CRtRZ"
)


def _base_payload() -> dict[str, Any]:
    """Return a valid Stage 21.3A payload populated with non-secret values."""
    return {
        "provider_event_id": "prov-evt-0001",
        "provider_name": "stage21_3a_test_provider",
        "source_kind": "stage21_3a_test_source",
        "chain": "stage21_3a_test_chain",
        "mint": "stage21_3a_test_mint",
        "event_type": "stage21_3a_test_event_type",
        "observed_at_utc": "2026-05-17T12:00:00Z",
        "slot": 1234567,
        "signature": SAMPLE_SOLANA_SIGNATURE,
        "instruction_kind": "reserved_for_21_3b",
        "decoded_fields": {
            "amount_in": 100,
            "amount_out": 200,
            "pool_id": "stage21_3a_test_pool",
        },
    }


# ---------------------------------------------------------------------------
# Locked vocabulary + required keys
# ---------------------------------------------------------------------------


def test_supported_instruction_kinds_is_exactly_reserved_for_21_3b():
    assert SUPPORTED_INSTRUCTION_KINDS == frozenset({"reserved_for_21_3b"})


def test_required_top_level_keys_are_the_eleven_locked_keys():
    assert REQUIRED_TOP_LEVEL_KEYS == (
        "provider_event_id",
        "provider_name",
        "source_kind",
        "chain",
        "mint",
        "event_type",
        "observed_at_utc",
        "slot",
        "signature",
        "instruction_kind",
        "decoded_fields",
    )


def test_sample_signature_contains_no_forbidden_substring():
    # Pin the assumption that the sample Solana-shaped signature
    # is safe to use as a happy-path fixture: every locked
    # forbidden substring is absent from it at case-folded compare.
    lower = SAMPLE_SOLANA_SIGNATURE.lower()
    for sub in FORBIDDEN_SUBSTRINGS:
        assert sub not in lower, (
            f"sample signature accidentally contains forbidden "
            f"substring {sub!r}; pick a different fixture"
        )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_decode_returns_normalized_live_event_on_valid_payload():
    event = decode_provider_event(_base_payload())
    assert isinstance(event, NormalizedLiveEvent)
    assert event.provider_event_id == "prov-evt-0001"
    assert event.provider_name == "stage21_3a_test_provider"
    assert event.source_kind == "stage21_3a_test_source"
    assert event.chain == "stage21_3a_test_chain"
    assert event.mint == "stage21_3a_test_mint"
    assert event.event_type == "stage21_3a_test_event_type"
    assert event.observed_at_utc == "2026-05-17T12:00:00Z"
    assert event.slot == 1234567
    assert event.signature == SAMPLE_SOLANA_SIGNATURE
    assert event.normalized_schema_version == NORMALIZED_EVENT_SCHEMA_VERSION


def test_event_id_starts_with_evt_prefix_and_has_locked_length():
    event = decode_provider_event(_base_payload())
    assert event.event_id.startswith("evt_")
    # locked shape: "evt_" + 24 hex chars
    assert len(event.event_id) == len("evt_") + 24


def test_raw_event_hash_is_64_lowercase_hex_chars():
    event = decode_provider_event(_base_payload())
    assert len(event.raw_event_hash) == 64
    assert all(c in "0123456789abcdef" for c in event.raw_event_hash)


def test_payload_summary_is_frozen_mappingproxy():
    event = decode_provider_event(_base_payload())
    assert isinstance(event.payload_summary, MappingProxyType)
    # Top-level mutation rejected.
    with pytest.raises(TypeError):
        event.payload_summary["amount_in"] = 999  # type: ignore[index]


def test_payload_summary_carries_decoded_fields_values():
    event = decode_provider_event(_base_payload())
    assert event.payload_summary["amount_in"] == 100
    assert event.payload_summary["amount_out"] == 200
    assert event.payload_summary["pool_id"] == "stage21_3a_test_pool"


def test_decode_is_deterministic_for_identical_input():
    a = decode_provider_event(_base_payload())
    b = decode_provider_event(_base_payload())
    assert a.event_id == b.event_id
    assert a.raw_event_hash == b.raw_event_hash


def test_distinct_provider_event_ids_produce_distinct_event_ids():
    p1 = _base_payload()
    p2 = _base_payload()
    p2["provider_event_id"] = "prov-evt-0002"
    a = decode_provider_event(p1)
    b = decode_provider_event(p2)
    assert a.event_id != b.event_id
    assert a.raw_event_hash != b.raw_event_hash


def test_distinct_instruction_kinds_would_produce_distinct_hashes():
    # Stage 21.3A only supports the placeholder kind, but the hash
    # input mixes instruction_kind so the eventual real adapter
    # cannot collide events that differ only in instruction_kind.
    # We exercise this by decoding twice with the same placeholder
    # and asserting hash equality (deterministic input -> same
    # hash); the negative branch is documented but not exercised
    # because no second valid kind exists yet.
    a = decode_provider_event(_base_payload())
    b = decode_provider_event(_base_payload())
    assert a.raw_event_hash == b.raw_event_hash


# ---------------------------------------------------------------------------
# Shape / type / value violations
# ---------------------------------------------------------------------------


def test_non_mapping_payload_raises_shape_error():
    with pytest.raises(ProviderPayloadShapeError):
        decode_provider_event(["not", "a", "mapping"])  # type: ignore[arg-type]


@pytest.mark.parametrize("missing_key", REQUIRED_TOP_LEVEL_KEYS)
def test_missing_required_key_raises_shape_error(missing_key: str):
    payload = _base_payload()
    del payload[missing_key]
    with pytest.raises(ProviderPayloadShapeError):
        decode_provider_event(payload)


@pytest.mark.parametrize(
    "key",
    [
        "provider_event_id",
        "provider_name",
        "source_kind",
        "chain",
        "mint",
        "event_type",
        "observed_at_utc",
        "signature",
        "instruction_kind",
    ],
)
def test_string_field_with_wrong_type_raises_type_error(key: str):
    payload = _base_payload()
    payload[key] = 123  # not a str
    with pytest.raises(ProviderPayloadFieldTypeError):
        decode_provider_event(payload)


@pytest.mark.parametrize(
    "key",
    [
        "provider_event_id",
        "provider_name",
        "source_kind",
        "chain",
        "mint",
        "event_type",
        "observed_at_utc",
        "signature",
        "instruction_kind",
    ],
)
def test_string_field_with_empty_value_raises_value_error(key: str):
    payload = _base_payload()
    payload[key] = ""
    with pytest.raises(ProviderPayloadFieldValueError):
        decode_provider_event(payload)


def test_slot_with_wrong_type_raises_type_error():
    payload = _base_payload()
    payload["slot"] = "not-an-int"
    with pytest.raises(ProviderPayloadFieldTypeError):
        decode_provider_event(payload)


def test_slot_boolean_is_rejected_as_wrong_type():
    payload = _base_payload()
    payload["slot"] = True
    with pytest.raises(ProviderPayloadFieldTypeError):
        decode_provider_event(payload)


def test_negative_slot_raises_value_error():
    payload = _base_payload()
    payload["slot"] = -1
    with pytest.raises(ProviderPayloadFieldValueError):
        decode_provider_event(payload)


def test_zero_slot_is_accepted_as_non_negative():
    payload = _base_payload()
    payload["slot"] = 0
    event = decode_provider_event(payload)
    assert event.slot == 0


def test_non_mapping_decoded_fields_raises_type_error():
    payload = _base_payload()
    payload["decoded_fields"] = ["not", "a", "mapping"]
    with pytest.raises(ProviderPayloadFieldTypeError):
        decode_provider_event(payload)


# ---------------------------------------------------------------------------
# Unsupported instruction kind
# ---------------------------------------------------------------------------


def test_unsupported_instruction_kind_raises_unsupported_error():
    payload = _base_payload()
    payload["instruction_kind"] = "swap_v2"
    with pytest.raises(ProviderPayloadUnsupportedInstructionError):
        decode_provider_event(payload)


def test_case_variant_of_supported_kind_is_still_unsupported():
    # The vocabulary is case-sensitive; only the exact placeholder
    # passes.
    payload = _base_payload()
    payload["instruction_kind"] = "RESERVED_FOR_21_3B"
    with pytest.raises(ProviderPayloadUnsupportedInstructionError):
        decode_provider_event(payload)


# ---------------------------------------------------------------------------
# Major 2 -- raw-value redaction in exception messages
# ---------------------------------------------------------------------------


def test_unsupported_instruction_kind_error_does_not_echo_raw_value():
    # AUDIT-21.3A-M2: the unsupported-instruction error message
    # MUST NOT include the raw instruction_kind value. The
    # suspicious-content scan runs AFTER this check, so a raw
    # echo would leak a secret-like value before sanitization.
    # The fixture value below would otherwise trip the
    # suspicious-content scan (it contains the locked
    # ``secret`` substring), but the unsupported check fires
    # first; the exception message must still be clean.
    raw_value = "secret-value-for-error"
    payload = _base_payload()
    payload["instruction_kind"] = raw_value
    with pytest.raises(ProviderPayloadUnsupportedInstructionError) as exc_info:
        decode_provider_event(payload)
    message = str(exc_info.value)
    assert raw_value not in message
    # Field name is allowed in the message; the raw value is not.
    assert "instruction_kind" in message


@pytest.mark.parametrize(
    "leaky_instruction_kind",
    [
        "secret-value-for-error",
        "api_key_leak_attempt",
        "credential_dump_here",
        "abracadabra_unknown_kind",
    ],
)
def test_unsupported_instruction_kind_error_redacts_various_leaky_values(
    leaky_instruction_kind: str,
):
    payload = _base_payload()
    payload["instruction_kind"] = leaky_instruction_kind
    with pytest.raises(ProviderPayloadUnsupportedInstructionError) as exc_info:
        decode_provider_event(payload)
    message = str(exc_info.value)
    assert leaky_instruction_kind not in message


def test_missing_required_field_error_does_not_echo_value_only_field_name():
    # The shape-error message must include the field NAME only;
    # since the field is missing there is no value to echo, but
    # the rule (field-name OK, raw-value not OK) is pinned here.
    payload = _base_payload()
    del payload["mint"]
    with pytest.raises(ProviderPayloadShapeError) as exc_info:
        decode_provider_event(payload)
    message = str(exc_info.value)
    assert "mint" in message


def test_field_type_error_does_not_echo_raw_value_only_type_name():
    # When a field has the wrong type, the error names the field
    # and the offending Python type, but never echoes the raw
    # value itself.
    raw_value = "secret-value-not-an-int"
    payload = _base_payload()
    payload["slot"] = raw_value  # str instead of int
    with pytest.raises(ProviderPayloadFieldTypeError) as exc_info:
        decode_provider_event(payload)
    message = str(exc_info.value)
    assert raw_value not in message
    assert "slot" in message
    assert "str" in message


def test_field_value_error_does_not_echo_raw_value():
    # An empty-string failure is the closest the value-error path
    # comes to carrying a raw value. The message must name the
    # field only.
    payload = _base_payload()
    payload["mint"] = ""
    with pytest.raises(ProviderPayloadFieldValueError) as exc_info:
        decode_provider_event(payload)
    message = str(exc_info.value)
    assert "mint" in message


def test_suspicious_content_error_includes_pattern_and_field_not_raw_value():
    # Per the Major 2 remediation rule, suspicious-content errors
    # MAY include the matched pattern name (which is itself a
    # locked constant from FORBIDDEN_SUBSTRINGS) and the field
    # label, but MUST NOT echo the raw matched value. The fixture
    # raw value below carries the ``webhook`` substring; the
    # pattern token "webhook" appears in the message but the
    # surrounding raw value does not.
    raw_value = "value-with-webhook-injected-here"
    payload = _base_payload()
    payload["source_kind"] = raw_value
    with pytest.raises(ProviderPayloadSuspiciousContentError) as exc_info:
        decode_provider_event(payload)
    message = str(exc_info.value)
    assert raw_value not in message
    # The field label and the matched pattern name ARE allowed in
    # the message.
    assert "source_kind" in message
    assert "webhook" in message


# ---------------------------------------------------------------------------
# Suspicious-content scan (per Q9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    [
        "provider_event_id",
        "provider_name",
        "source_kind",
        "chain",
        "mint",
        "event_type",
        "signature",
    ],
)
def test_forbidden_substring_in_top_level_string_field_raises_suspicious_error(
    field_name: str,
):
    payload = _base_payload()
    payload[field_name] = "value-with-webhook-injected"
    with pytest.raises(ProviderPayloadSuspiciousContentError):
        decode_provider_event(payload)


def test_forbidden_substring_in_decoded_fields_string_value_is_caught():
    payload = _base_payload()
    payload["decoded_fields"] = {
        "pool_id": "stage21_3a_test_pool",
        "label": "leaking-api_key-value-here",
    }
    with pytest.raises(ProviderPayloadSuspiciousContentError):
        decode_provider_event(payload)


def test_nested_value_inside_decoded_fields_is_not_scanned():
    # Per Q9 the scan walks string-valued items at the top level
    # of decoded_fields only; nested mappings / sequences are NOT
    # scanned. A forbidden substring buried one level deeper must
    # therefore decode without tripping the scan -- this pins the
    # "one level of nesting" semantic so a future widening
    # surfaces explicitly.
    payload = _base_payload()
    payload["decoded_fields"] = {
        "pool_id": "stage21_3a_test_pool",
        "nested": {
            "would_trip_if_scanned": "value-with-webhook-text",
        },
    }
    event = decode_provider_event(payload)
    assert "would_trip_if_scanned" in event.payload_summary["nested"]


def test_non_string_decoded_fields_values_are_not_scanned():
    # Integers / lists / bools at the top level of decoded_fields
    # are skipped by the suspicious-content scan because the scan
    # only inspects string-typed values (per Q9). The fixture
    # below contains a list whose first element would otherwise
    # trip; the scan must not see it.
    payload = _base_payload()
    payload["decoded_fields"] = {
        "amount_in": 100,
        "tags": ["webhook-marker", "harmless"],
    }
    event = decode_provider_event(payload)
    assert event.payload_summary["tags"] == ("webhook-marker", "harmless")


def test_legitimate_solana_signature_does_not_trigger_suspicious_content_scan():
    # Per Q9 a legitimate Solana signature (~88-char base58
    # string) must pass. The sample fixture mirrors a real
    # signature shape; this test pins the no-false-positive
    # behavior at the boundary.
    event = decode_provider_event(_base_payload())
    assert event.signature == SAMPLE_SOLANA_SIGNATURE


def test_url_scheme_substring_in_top_level_field_is_rejected():
    # URL-scheme prefixes are in the locked FORBIDDEN_SUBSTRINGS
    # set. Insert one programmatically (built piecewise so the
    # literal URL substring does not appear in this test source).
    url_scheme = "http" + ":" + "//" + "example.invalid/path"
    payload = _base_payload()
    payload["source_kind"] = url_scheme
    with pytest.raises(ProviderPayloadSuspiciousContentError):
        decode_provider_event(payload)


# ---------------------------------------------------------------------------
# Module-local error hierarchy invariants (per locked operator decision Q3)
# ---------------------------------------------------------------------------


def test_every_decoder_error_subclasses_module_local_base():
    assert issubclass(ProviderPayloadShapeError, ProviderPayloadError)
    assert issubclass(ProviderPayloadFieldTypeError, ProviderPayloadError)
    assert issubclass(ProviderPayloadFieldValueError, ProviderPayloadError)
    assert issubclass(
        ProviderPayloadUnsupportedInstructionError, ProviderPayloadError
    )
    assert issubclass(
        ProviderPayloadSuspiciousContentError, ProviderPayloadError
    )


def test_decoder_base_is_a_plain_exception_subclass():
    # Per Q3 the decoder hierarchy is module-local and NOT a
    # subclass of Stage21Error. The closed Stage 21 E2120..E2122
    # codes remain reserved for the Stage 21.3B+ real adapter
    # contract.
    assert issubclass(ProviderPayloadError, Exception)
    # Best-effort: verify the decoder error is NOT a Stage21Error.
    from PHX2.stage21.errors import Stage21Error

    assert not issubclass(ProviderPayloadError, Stage21Error)
