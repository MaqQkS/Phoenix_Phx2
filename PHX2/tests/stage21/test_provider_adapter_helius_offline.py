"""Stage 21.3B Helius provider adapter offline tests.

These tests exercise the adapter with an injected fake client
that returns deterministic in-memory responses. No network call
happens. No live test marker is used.
"""

from __future__ import annotations

from typing import Mapping, Sequence
from types import MappingProxyType

import pytest

from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage21.ping_payloads import NORMALIZED_EVENT_SCHEMA_VERSION
from PHX2.stage21.provider_adapter_helius import (
    HELIUS_ADAPTER_LOCKED_VALUES,
    HELIUS_CHAIN_NAME,
    HELIUS_INSTRUCTION_KIND_PLACEHOLDER,
    HELIUS_PROVIDER_NAME,
    HELIUS_SOURCE_KIND,
    HeliusAdapterError,
    HeliusClientFetchError,
    HeliusClientResponseFieldTypeError,
    HeliusClientResponseFieldValueError,
    HeliusClientResponseShapeError,
    HeliusProviderAdapter,
    REQUIRED_CLIENT_RESPONSE_KEYS,
)
from PHX2.stage21.provider_event_decoder import (
    ProviderPayloadSuspiciousContentError,
    ProviderPayloadUnsupportedInstructionError,
)


# 88-char base58 string approximating a real Solana transaction
# signature, mirroring the Stage 21.3A decoder fixture. Chosen so
# no forbidden substring trips the decoder's suspicious-content
# scan.
SAMPLE_SOLANA_SIGNATURE: str = (
    "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJ"
    "Lgp8uirBgmQpjKhoR4tjF3ZpRzrFmBs6JKDsGY9CRtRZ"
)


# ---------------------------------------------------------------------------
# Offline fake client (Stage 21.3B test scaffold, NOT a production client)
# ---------------------------------------------------------------------------


class _RecordingFakeHeliusClient:
    """Deterministic in-memory fake client.

    Returns the responses provided at construction. Records every
    call so the tests can verify cursor / max_results are
    forwarded unchanged. Performs no network work and holds no
    credentials.
    """

    def __init__(self, responses: Sequence[Mapping[str, object]]) -> None:
        self._responses: tuple[Mapping[str, object], ...] = tuple(responses)
        self.calls: list[tuple[object, int]] = []

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append((cursor, max_results))
        if max_results and max_results > 0:
            return self._responses[:max_results]
        return self._responses


class _ReturnsNonSequenceFakeClient:
    """Fake client that returns a non-Sequence value -- contract violation."""

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> object:
        return 42  # type: ignore[return-value]


class _ReturnsBytesFakeClient:
    """Fake client returning a ``bytes`` value (Sequence-like but invalid)."""

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> object:
        return b"not-a-sequence-of-mappings"  # type: ignore[return-value]


class _ReturnsStringFakeClient:
    """Fake client returning a ``str`` value (Sequence-like but invalid)."""

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> object:
        return "not-a-sequence-of-mappings"  # type: ignore[return-value]


def _valid_response(index: int = 0) -> dict[str, object]:
    """Return a valid 7-key Helius client response."""
    return {
        "provider_event_id": f"helius-evt-{index:04d}",
        "signature": SAMPLE_SOLANA_SIGNATURE,
        "slot": 250_000_000 + index,
        "observed_at_utc": "2026-05-17T12:00:00Z",
        "event_type": "stage21_3b_test_event_type",
        "mint": "stage21_3b_test_mint",
        "decoded_fields": {
            "amount_in": 100,
            "amount_out": 200,
            "pool_id": "stage21_3b_test_pool",
        },
    }


def _build_adapter(
    responses: Sequence[Mapping[str, object]],
) -> tuple[HeliusProviderAdapter, _RecordingFakeHeliusClient]:
    client = _RecordingFakeHeliusClient(responses)
    return HeliusProviderAdapter(client), client


# ---------------------------------------------------------------------------
# Locked adapter constants
# ---------------------------------------------------------------------------


def test_helius_provider_name_is_locked_to_helius():
    assert HELIUS_PROVIDER_NAME == "helius"


def test_helius_chain_name_is_locked_to_solana_mainnet():
    assert HELIUS_CHAIN_NAME == "solana_mainnet"


def test_helius_source_kind_is_locked_to_helius_grpc_compatible():
    assert HELIUS_SOURCE_KIND == "helius_grpc_compatible"


def test_helius_instruction_kind_placeholder_locked_to_reserved_for_21_3b():
    # Stage 21.3B keeps the decoder vocabulary at the Stage 21.3A
    # placeholder. Real instruction kinds land in Stage 21.4+.
    assert HELIUS_INSTRUCTION_KIND_PLACEHOLDER == "reserved_for_21_3b"


def test_helius_adapter_locked_values_set_size_is_exactly_four():
    assert len(HELIUS_ADAPTER_LOCKED_VALUES) == 4
    assert set(HELIUS_ADAPTER_LOCKED_VALUES) == {
        HELIUS_PROVIDER_NAME,
        HELIUS_CHAIN_NAME,
        HELIUS_SOURCE_KIND,
        HELIUS_INSTRUCTION_KIND_PLACEHOLDER,
    }


def test_required_client_response_keys_are_the_seven_locked_strings():
    assert REQUIRED_CLIENT_RESPONSE_KEYS == (
        "provider_event_id",
        "signature",
        "slot",
        "observed_at_utc",
        "event_type",
        "mint",
        "decoded_fields",
    )


def test_required_client_response_keys_do_not_include_adapter_locked_fields():
    # The four adapter-locked enrichment fields MUST NOT be
    # required of the client -- the adapter is the authority on
    # them and the client cannot influence them.
    for adapter_locked_key in (
        "provider_name",
        "chain",
        "source_kind",
        "instruction_kind",
    ):
        assert adapter_locked_key not in REQUIRED_CLIENT_RESPONSE_KEYS, (
            f"Adapter-locked field {adapter_locked_key!r} must not be "
            "required of the injected client"
        )


# ---------------------------------------------------------------------------
# Happy path: raw payloads
# ---------------------------------------------------------------------------


def test_fetch_raw_payloads_returns_tuple_of_mappings():
    adapter, _ = _build_adapter([_valid_response(0), _valid_response(1)])
    payloads = adapter.fetch_raw_payloads()
    assert isinstance(payloads, tuple)
    assert len(payloads) == 2
    for payload in payloads:
        assert isinstance(payload, Mapping)


def test_fetch_raw_payloads_has_all_eleven_decoder_keys():
    adapter, _ = _build_adapter([_valid_response(0)])
    payload = adapter.fetch_raw_payloads()[0]
    expected_keys = {
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
    }
    assert set(payload.keys()) == expected_keys


def test_fetch_raw_payloads_enriches_with_adapter_locked_values():
    adapter, _ = _build_adapter([_valid_response(0)])
    payload = adapter.fetch_raw_payloads()[0]
    assert payload["provider_name"] == HELIUS_PROVIDER_NAME
    assert payload["chain"] == HELIUS_CHAIN_NAME
    assert payload["source_kind"] == HELIUS_SOURCE_KIND
    assert payload["instruction_kind"] == HELIUS_INSTRUCTION_KIND_PLACEHOLDER


def test_fetch_raw_payloads_passes_through_caller_supplied_fields():
    adapter, _ = _build_adapter([_valid_response(7)])
    payload = adapter.fetch_raw_payloads()[0]
    assert payload["provider_event_id"] == "helius-evt-0007"
    assert payload["signature"] == SAMPLE_SOLANA_SIGNATURE
    assert payload["slot"] == 250_000_007
    assert payload["observed_at_utc"] == "2026-05-17T12:00:00Z"
    assert payload["event_type"] == "stage21_3b_test_event_type"
    assert payload["mint"] == "stage21_3b_test_mint"
    assert payload["decoded_fields"] == {
        "amount_in": 100,
        "amount_out": 200,
        "pool_id": "stage21_3b_test_pool",
    }


def test_adapter_overrides_client_attempt_to_forge_provider_name():
    # A malicious or malformed client supplies provider_name in
    # the response; the adapter must ignore it and emit the
    # adapter-locked HELIUS_PROVIDER_NAME instead. The contract
    # protects downstream consumers from a forged provider_name.
    response = _valid_response(0)
    response["provider_name"] = "fake_alternative_provider"
    response["chain"] = "fake_alternative_chain"
    response["source_kind"] = "fake_alternative_source_kind"
    response["instruction_kind"] = "fake_alternative_instruction_kind"
    adapter, _ = _build_adapter([response])
    payload = adapter.fetch_raw_payloads()[0]
    assert payload["provider_name"] == HELIUS_PROVIDER_NAME
    assert payload["chain"] == HELIUS_CHAIN_NAME
    assert payload["source_kind"] == HELIUS_SOURCE_KIND
    assert payload["instruction_kind"] == HELIUS_INSTRUCTION_KIND_PLACEHOLDER


def test_fetch_raw_payloads_is_deterministic_for_identical_input():
    adapter_a, _ = _build_adapter([_valid_response(0), _valid_response(1)])
    adapter_b, _ = _build_adapter([_valid_response(0), _valid_response(1)])
    assert adapter_a.fetch_raw_payloads() == adapter_b.fetch_raw_payloads()


def test_fetch_raw_payloads_empty_responses_returns_empty_tuple():
    adapter, _ = _build_adapter([])
    assert adapter.fetch_raw_payloads() == ()


# ---------------------------------------------------------------------------
# Happy path: normalized events (end-to-end through decode_provider_event)
# ---------------------------------------------------------------------------


def test_fetch_normalized_events_returns_tuple_of_normalized_live_events():
    adapter, _ = _build_adapter([_valid_response(0), _valid_response(1)])
    events = adapter.fetch_normalized_events()
    assert isinstance(events, tuple)
    assert len(events) == 2
    for event in events:
        assert isinstance(event, NormalizedLiveEvent)


def test_fetch_normalized_events_carries_adapter_locked_values():
    adapter, _ = _build_adapter([_valid_response(0)])
    event = adapter.fetch_normalized_events()[0]
    assert event.provider_name == HELIUS_PROVIDER_NAME
    assert event.chain == HELIUS_CHAIN_NAME
    assert event.source_kind == HELIUS_SOURCE_KIND
    assert event.normalized_schema_version == NORMALIZED_EVENT_SCHEMA_VERSION


def test_fetch_normalized_events_derives_deterministic_event_id_and_hash():
    adapter_a, _ = _build_adapter([_valid_response(0)])
    adapter_b, _ = _build_adapter([_valid_response(0)])
    event_a = adapter_a.fetch_normalized_events()[0]
    event_b = adapter_b.fetch_normalized_events()[0]
    assert event_a.event_id == event_b.event_id
    assert event_a.raw_event_hash == event_b.raw_event_hash
    assert event_a.event_id.startswith("evt_")


def test_fetch_normalized_events_distinct_inputs_yield_distinct_ids():
    adapter, _ = _build_adapter([_valid_response(0), _valid_response(1)])
    events = adapter.fetch_normalized_events()
    assert events[0].event_id != events[1].event_id
    assert events[0].raw_event_hash != events[1].raw_event_hash


# ---------------------------------------------------------------------------
# Cursor / max_results forwarding
# ---------------------------------------------------------------------------


def test_cursor_and_max_results_are_forwarded_to_client():
    adapter, client = _build_adapter([_valid_response(i) for i in range(5)])
    adapter.fetch_raw_payloads(cursor="cursor-token-abc", max_results=2)
    assert client.calls == [("cursor-token-abc", 2)]


def test_cursor_defaults_to_none_and_max_results_defaults_to_zero():
    adapter, client = _build_adapter([_valid_response(0)])
    adapter.fetch_raw_payloads()
    assert client.calls == [(None, 0)]


def test_max_results_truncates_via_client():
    adapter, _ = _build_adapter([_valid_response(i) for i in range(5)])
    payloads = adapter.fetch_raw_payloads(max_results=3)
    assert len(payloads) == 3


def test_fetch_normalized_events_forwards_cursor_and_max_results():
    adapter, client = _build_adapter([_valid_response(i) for i in range(5)])
    adapter.fetch_normalized_events(cursor="cur", max_results=4)
    assert client.calls == [("cur", 4)]


# ---------------------------------------------------------------------------
# Shape / type / value failures
# ---------------------------------------------------------------------------


def test_non_sequence_response_raises_shape_error():
    adapter = HeliusProviderAdapter(_ReturnsNonSequenceFakeClient())
    with pytest.raises(HeliusClientResponseShapeError):
        adapter.fetch_raw_payloads()


def test_bytes_response_is_rejected_as_non_sequence_of_mappings():
    adapter = HeliusProviderAdapter(_ReturnsBytesFakeClient())
    with pytest.raises(HeliusClientResponseShapeError):
        adapter.fetch_raw_payloads()


def test_string_response_is_rejected_as_non_sequence_of_mappings():
    adapter = HeliusProviderAdapter(_ReturnsStringFakeClient())
    with pytest.raises(HeliusClientResponseShapeError):
        adapter.fetch_raw_payloads()


def test_non_mapping_response_element_raises_shape_error():
    adapter, _ = _build_adapter([["not", "a", "mapping"]])  # type: ignore[list-item]
    with pytest.raises(HeliusClientResponseShapeError):
        adapter.fetch_raw_payloads()


@pytest.mark.parametrize("missing_key", REQUIRED_CLIENT_RESPONSE_KEYS)
def test_missing_required_key_raises_shape_error(missing_key: str):
    response = _valid_response(0)
    del response[missing_key]
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseShapeError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert missing_key in message


@pytest.mark.parametrize(
    "key",
    [
        "provider_event_id",
        "signature",
        "observed_at_utc",
        "event_type",
        "mint",
    ],
)
def test_string_field_with_wrong_type_raises_field_type_error(key: str):
    response = _valid_response(0)
    response[key] = 123  # not a str
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldTypeError):
        adapter.fetch_raw_payloads()


@pytest.mark.parametrize(
    "key",
    [
        "provider_event_id",
        "signature",
        "observed_at_utc",
        "event_type",
        "mint",
    ],
)
def test_string_field_with_empty_value_raises_field_value_error(key: str):
    response = _valid_response(0)
    response[key] = ""
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldValueError):
        adapter.fetch_raw_payloads()


def test_slot_with_wrong_type_raises_field_type_error():
    response = _valid_response(0)
    response["slot"] = "not-an-int"
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldTypeError):
        adapter.fetch_raw_payloads()


def test_slot_boolean_is_rejected_as_wrong_type():
    response = _valid_response(0)
    response["slot"] = True
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldTypeError):
        adapter.fetch_raw_payloads()


def test_negative_slot_raises_field_value_error():
    response = _valid_response(0)
    response["slot"] = -1
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldValueError):
        adapter.fetch_raw_payloads()


def test_zero_slot_is_accepted_as_non_negative():
    response = _valid_response(0)
    response["slot"] = 0
    adapter, _ = _build_adapter([response])
    payload = adapter.fetch_raw_payloads()[0]
    assert payload["slot"] == 0


def test_non_mapping_decoded_fields_raises_field_type_error():
    response = _valid_response(0)
    response["decoded_fields"] = ["not", "a", "mapping"]
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldTypeError):
        adapter.fetch_raw_payloads()


def test_error_hierarchy_is_module_local():
    # The whole hierarchy roots at HeliusAdapterError; the shape /
    # type / value subclasses all derive from it. The decoder
    # errors are intentionally distinct -- the adapter does not
    # extend ProviderPayloadError.
    assert issubclass(HeliusClientResponseShapeError, HeliusAdapterError)
    assert issubclass(HeliusClientResponseFieldTypeError, HeliusAdapterError)
    assert issubclass(HeliusClientResponseFieldValueError, HeliusAdapterError)
    assert issubclass(HeliusAdapterError, Exception)


# ---------------------------------------------------------------------------
# Secret-leak / no-raw-value-in-errors invariants
# ---------------------------------------------------------------------------


def test_field_type_error_does_not_echo_raw_value():
    response = _valid_response(0)
    leaky_raw_value = "secret-value-not-an-int"
    response["slot"] = leaky_raw_value  # str instead of int
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldTypeError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert leaky_raw_value not in message
    assert "slot" in message
    assert "str" in message


def test_field_value_error_does_not_echo_raw_value():
    response = _valid_response(0)
    response["mint"] = ""
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldValueError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert "mint" in message


@pytest.mark.parametrize(
    "leaky_value",
    [
        "secret-value-for-error",
        "credential-dump-here",
        "api_key_leak_attempt",
    ],
)
def test_string_field_wrong_type_error_redacts_leaky_payload_values(
    leaky_value: str,
):
    # Even when the offending value is a non-str (so it can't
    # match the field-value-error path), tests should pin the
    # broader rule: error messages name the field and type, not
    # the raw value.
    response = _valid_response(0)
    response["mint"] = {"key": leaky_value}  # wrong type for mint
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldTypeError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert leaky_value not in message


def test_repr_does_not_echo_client_repr_or_credentials():
    class _ClientWithSensitiveRepr:
        def __repr__(self) -> str:
            return "<Client api_key='SUPER_SECRET_KEY_VALUE'>"

        def fetch_raw_responses(
            self,
            *,
            cursor: object = None,
            max_results: int = 0,
        ) -> Sequence[Mapping[str, object]]:
            return ()

    adapter = HeliusProviderAdapter(_ClientWithSensitiveRepr())
    rendered = repr(adapter)
    assert "SUPER_SECRET_KEY_VALUE" not in rendered
    assert "api_key" not in rendered
    # The adapter's repr surfaces the class name and the client's
    # TYPE name only -- never the client's repr.
    assert "HeliusProviderAdapter" in rendered
    assert "_ClientWithSensitiveRepr" in rendered


def test_none_client_at_construction_raises_shape_error():
    with pytest.raises(HeliusClientResponseShapeError):
        HeliusProviderAdapter(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Interaction with decoder semantics
# ---------------------------------------------------------------------------


def test_normalized_events_respect_decoder_suspicious_content_scan():
    # The adapter passes mint / signature / etc. through to the
    # decoder, which runs the locked FORBIDDEN_SUBSTRINGS scan.
    # A client response with a URL-shaped value must trip the
    # decoder even though the adapter itself does not scan.
    response = _valid_response(0)
    response["mint"] = "value-with-webhook-injected"
    adapter, _ = _build_adapter([response])
    with pytest.raises(ProviderPayloadSuspiciousContentError):
        adapter.fetch_normalized_events()


def test_normalized_events_do_not_widen_decoder_instruction_kind_vocabulary():
    # The adapter's locked instruction_kind is the placeholder.
    # If a future change accidentally widens the decoder
    # vocabulary, this pin would still pass (the placeholder
    # remains supported); the failure mode is the inverse --
    # narrowing the placeholder would break this test. Both
    # directions are caught by the explicit constant lock above.
    adapter, _ = _build_adapter([_valid_response(0)])
    event = adapter.fetch_normalized_events()[0]
    # The decoder doesn't surface instruction_kind in
    # NormalizedLiveEvent; confirm the call succeeded (placeholder
    # accepted) and the raw payload still pins the placeholder.
    assert event.event_id.startswith("evt_")
    payload = adapter.fetch_raw_payloads()[0]
    assert payload["instruction_kind"] == "reserved_for_21_3b"


def test_adapter_with_forged_instruction_kind_in_client_response_uses_placeholder():
    # Even if a client tries to supply an instruction_kind, the
    # adapter ignores it and emits the placeholder. If the
    # ignored value would have tripped the decoder's
    # unsupported-instruction-kind path, the adapter still
    # succeeds because the placeholder is used.
    response = _valid_response(0)
    response["instruction_kind"] = "fake_pump_swap_kind_unknown"
    adapter, _ = _build_adapter([response])
    # Decoder accepts the placeholder; no
    # ProviderPayloadUnsupportedInstructionError raised.
    events = adapter.fetch_normalized_events()
    assert len(events) == 1


def test_adapter_does_not_raise_unsupported_instruction_kind_for_client_response():
    # The adapter never bypasses the placeholder, so
    # decode_provider_event should never see a non-placeholder
    # instruction_kind from the adapter path.
    response = _valid_response(0)
    adapter, _ = _build_adapter([response])
    try:
        adapter.fetch_normalized_events()
    except ProviderPayloadUnsupportedInstructionError as exc:  # pragma: no cover
        pytest.fail(
            "adapter unexpectedly produced an unsupported instruction "
            f"kind: {type(exc).__name__}"
        )


# ---------------------------------------------------------------------------
# Frozen / read-only response interoperability
# ---------------------------------------------------------------------------


def test_adapter_accepts_frozen_mappingproxy_response():
    # A client may legitimately return MappingProxyType-wrapped
    # responses (e.g. from a frozen cache); the adapter must
    # accept them transparently.
    raw = _valid_response(0)
    frozen_decoded = MappingProxyType(dict(raw["decoded_fields"]))  # type: ignore[arg-type]
    raw["decoded_fields"] = frozen_decoded
    frozen_response = MappingProxyType(raw)
    adapter, _ = _build_adapter([frozen_response])
    payload = adapter.fetch_raw_payloads()[0]
    assert payload["mint"] == "stage21_3b_test_mint"
    assert payload["decoded_fields"]["amount_in"] == 100


def test_adapter_accepts_tuple_of_responses():
    # The contract says Sequence; a tuple is the canonical
    # Sequence form returned by a frozen cache.
    responses = (_valid_response(0), _valid_response(1))
    adapter = HeliusProviderAdapter(_RecordingFakeHeliusClient(responses))
    payloads = adapter.fetch_raw_payloads()
    assert len(payloads) == 2


# ---------------------------------------------------------------------------
# Audit-21.3B Major remediation: client exception sanitization
# ---------------------------------------------------------------------------
#
# The injected client may raise an arbitrary Exception whose
# ``str`` / ``repr`` / ``args`` could carry a raw response body,
# URL, token, API key, or RPC URL. The adapter wraps the call
# and re-raises as ``HeliusClientFetchError`` with a sanitized
# message that contains ONLY the client exception's TYPE name.
# ``raise ... from None`` suppresses Python's exception-chaining
# display so the original exception's repr never reaches the
# traceback.


class _RaisingFakeClient:
    """Fake client that raises ``RuntimeError`` with a leaky message."""

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> Sequence[Mapping[str, object]]:
        raise RuntimeError("SECRET_RAW_BODY_TOKEN")


class _RaisingValueErrorFakeClient:
    """Fake client that raises ``ValueError`` with a URL-shaped leaky message."""

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> Sequence[Mapping[str, object]]:
        # Constructed piecewise so this test source itself has no
        # URL literal (matches the Stage 21 boundary rule).
        url_like = "http" + "://" + "leaky.invalid/SECRET_API_KEY_98765"
        raise ValueError(url_like)


class _RaisingCustomExceptionFakeClient:
    """Fake client raising a custom Exception subclass with leaky args."""

    class _CustomLeakyError(Exception):
        pass

    def fetch_raw_responses(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> Sequence[Mapping[str, object]]:
        raise self._CustomLeakyError(
            "SECRET_BEARER_TOKEN_ZZZZZ",
            "raw response body with credential",
        )


def test_client_runtime_error_wrapped_in_helius_client_fetch_error():
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    assert isinstance(exc_info.value, HeliusAdapterError)


def test_client_fetch_error_message_does_not_echo_raw_exception_message():
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert "SECRET_RAW_BODY_TOKEN" not in message


def test_client_fetch_error_message_contains_only_client_exception_type_name():
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert "RuntimeError" in message


def test_client_fetch_error_cause_is_none_via_from_none():
    # ``raise ... from None`` sets ``__cause__`` to None
    # explicitly. The Python traceback display uses this to
    # suppress chaining.
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    assert exc_info.value.__cause__ is None


def test_client_fetch_error_context_is_suppressed_via_from_none():
    # ``raise ... from None`` also sets
    # ``__suppress_context__`` to True so the implicit
    # ``__context__`` chain is hidden in traceback display.
    # This is the audit's "__context__ either None or not
    # user-visible" requirement.
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    assert exc_info.value.__suppress_context__ is True


def test_client_value_error_with_url_shaped_message_does_not_leak_url():
    adapter = HeliusProviderAdapter(_RaisingValueErrorFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert "leaky.invalid" not in message
    assert "SECRET_API_KEY_98765" not in message
    assert "://" not in message
    # The sanitized message still contains the client
    # exception type name.
    assert "ValueError" in message


def test_client_custom_exception_with_multi_arg_message_is_fully_redacted():
    adapter = HeliusProviderAdapter(_RaisingCustomExceptionFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert "SECRET_BEARER_TOKEN_ZZZZZ" not in message
    assert "raw response body" not in message
    assert "credential" not in message
    # Type name is exposed; nothing else.
    assert "_CustomLeakyError" in message


def test_client_fetch_error_repr_does_not_echo_original_exception():
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    rendered = repr(exc_info.value)
    assert "SECRET_RAW_BODY_TOKEN" not in rendered


def test_client_fetch_error_args_do_not_include_original_exception():
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_raw_payloads()
    for arg in exc_info.value.args:
        assert "SECRET_RAW_BODY_TOKEN" not in str(arg)


def test_fetch_normalized_events_also_wraps_client_exceptions():
    # ``fetch_normalized_events`` delegates to
    # ``fetch_raw_payloads``; the sanitization must apply on
    # both code paths.
    adapter = HeliusProviderAdapter(_RaisingFakeClient())
    with pytest.raises(HeliusClientFetchError) as exc_info:
        adapter.fetch_normalized_events()
    message = str(exc_info.value)
    assert "SECRET_RAW_BODY_TOKEN" not in message
    assert "RuntimeError" in message


def test_helius_client_fetch_error_is_helius_adapter_error_subclass():
    # The new error stays inside the module-local hierarchy
    # rooted at ``HeliusAdapterError``; it is not a
    # ``Stage21Error`` and not a subclass of the existing
    # response-shape / field-type / field-value errors.
    assert issubclass(HeliusClientFetchError, HeliusAdapterError)
    assert issubclass(HeliusClientFetchError, Exception)
    assert not issubclass(
        HeliusClientFetchError, HeliusClientResponseShapeError
    )
    assert not issubclass(
        HeliusClientFetchError, HeliusClientResponseFieldTypeError
    )
    assert not issubclass(
        HeliusClientFetchError, HeliusClientResponseFieldValueError
    )


def test_validation_errors_are_not_wrapped_in_client_fetch_error():
    # The Major remediation wrap covers ONLY the client call.
    # Validation errors raised on the data the client returned
    # (shape / type / value) must keep their specific error
    # types so callers can distinguish "client raised" from
    # "client returned a malformed response".
    response = _valid_response(0)
    response["mint"] = ""  # value-error path
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldValueError):
        adapter.fetch_raw_payloads()


# ---------------------------------------------------------------------------
# Audit-21.3B Minor 2: unknown extra client-response keys must not leak
# ---------------------------------------------------------------------------
#
# Unknown top-level keys in a client response are silently
# dropped at the adapter boundary (forward-compatibility with
# Helius response evolution). The test pins that the DROPPED
# keys and their VALUES never appear in:
#   * the returned raw payload (top level or any nested value)
#   * the normalized event (top level or payload_summary)
#   * the normalized event's repr


def test_unknown_extra_client_response_keys_are_dropped_from_raw_payload():
    response = _valid_response(0)
    response["extra_secret"] = "SECRET_SHOULD_NOT_LEAK"
    response["raw_body"] = "RAW_BODY_SHOULD_NOT_LEAK"
    response["bearer_token"] = "BEARER_TOKEN_SHOULD_NOT_LEAK"
    adapter, _ = _build_adapter([response])
    payload = adapter.fetch_raw_payloads()[0]

    # Only the 11 decoder keys appear.
    assert set(payload.keys()) == {
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
    }
    assert "extra_secret" not in payload
    assert "raw_body" not in payload
    assert "bearer_token" not in payload


def test_unknown_extra_client_response_values_do_not_leak_into_raw_payload():
    response = _valid_response(0)
    response["extra_secret"] = "SECRET_SHOULD_NOT_LEAK"
    response["raw_body"] = "RAW_BODY_SHOULD_NOT_LEAK"
    adapter, _ = _build_adapter([response])
    payload = adapter.fetch_raw_payloads()[0]
    rendered = repr(payload)
    assert "SECRET_SHOULD_NOT_LEAK" not in rendered
    assert "RAW_BODY_SHOULD_NOT_LEAK" not in rendered


def test_unknown_extra_client_response_values_do_not_leak_into_normalized_event():
    response = _valid_response(0)
    response["extra_secret"] = "SECRET_SHOULD_NOT_LEAK"
    response["raw_body"] = "RAW_BODY_SHOULD_NOT_LEAK"
    adapter, _ = _build_adapter([response])
    event = adapter.fetch_normalized_events()[0]
    rendered = repr(event)
    assert "SECRET_SHOULD_NOT_LEAK" not in rendered
    assert "RAW_BODY_SHOULD_NOT_LEAK" not in rendered


def test_unknown_extra_client_response_values_do_not_leak_into_payload_summary():
    response = _valid_response(0)
    response["extra_secret"] = "SECRET_SHOULD_NOT_LEAK"
    response["raw_body"] = "RAW_BODY_SHOULD_NOT_LEAK"
    adapter, _ = _build_adapter([response])
    event = adapter.fetch_normalized_events()[0]
    rendered_summary = repr(event.payload_summary)
    assert "SECRET_SHOULD_NOT_LEAK" not in rendered_summary
    assert "RAW_BODY_SHOULD_NOT_LEAK" not in rendered_summary
    # And the locked decoded_fields contents are still intact.
    assert event.payload_summary["amount_in"] == 100
    assert event.payload_summary["amount_out"] == 200
    assert event.payload_summary["pool_id"] == "stage21_3b_test_pool"


def test_unknown_extra_keys_do_not_appear_in_exception_path():
    # If an unrelated required field violates its contract, the
    # raised exception must not echo the leaky extra keys or
    # values.
    response = _valid_response(0)
    response["extra_secret"] = "SECRET_SHOULD_NOT_LEAK"
    response["mint"] = ""  # triggers HeliusClientResponseFieldValueError
    adapter, _ = _build_adapter([response])
    with pytest.raises(HeliusClientResponseFieldValueError) as exc_info:
        adapter.fetch_raw_payloads()
    message = str(exc_info.value)
    assert "SECRET_SHOULD_NOT_LEAK" not in message
    assert "extra_secret" not in message
