"""Stage 22.4 real-decoder integration test for ``handle_provider_batch``.

This is the ONE Stage 22.4 test file permitted to import the
Stage 21.3A ``decode_provider_event`` real decoder. Every
other Stage 22.4 test uses an injected fake decoder. The
22.4 boundary test (``test_stage_22_4_boundaries.py``) pins
this single-file allowlist by inspecting the AST of every
``test_failure_handling*`` file under
``PHX2/tests/stage22/``.

Pins:

  * A real Stage 21.3A good payload decodes through
    ``handle_provider_batch`` and captures one
    ``normalized_event`` record.
  * A real ``ProviderPayloadShapeError`` payload maps to
    ``decode_shape_error``.
  * A real ``ProviderPayloadFieldTypeError`` payload maps to
    ``decode_field_type_error``.
  * A real ``ProviderPayloadFieldValueError`` payload maps to
    ``decode_field_value_error``.
  * A real ``ProviderPayloadUnsupportedInstructionError``
    payload maps to ``decode_unsupported_instruction``.
  * A real ``ProviderPayloadSuspiciousContentError`` payload
    maps to ``decode_suspicious_content``.
  * A mixed real good + poison batch isolates the failure --
    the good event survives and is captured.
  * A real ``MappingProxyType`` ``payload_summary`` (the
    Stage 21.3A decoder freezes it) flows through capture
    successfully.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage21.provider_event_decoder import (
    ProviderPayloadError,
    ProviderPayloadFieldTypeError,
    ProviderPayloadFieldValueError,
    ProviderPayloadShapeError,
    ProviderPayloadSuspiciousContentError,
    ProviderPayloadUnsupportedInstructionError,
    decode_provider_event,
)
from PHX2.stage22.constants import (
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_OK,
    MALFORMED_EVENT_REASONS,
    MALFORMED_REASON_FIELD_TYPE_ERROR,
    MALFORMED_REASON_FIELD_VALUE_ERROR,
    MALFORMED_REASON_SHAPE_ERROR,
    MALFORMED_REASON_SUSPICIOUS_CONTENT,
    MALFORMED_REASON_UNEXPECTED_ERROR,
    MALFORMED_REASON_UNSUPPORTED_INSTRUCTION,
    STATUS_CLASS_SUCCESS,
    UPSTREAM_ERROR_TYPE_NONE,
)
from PHX2.stage22.failure_handling import handle_provider_batch
from PHX2.stage22.ingest_contracts import ProviderFetchOutcome
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


_PROVIDER_ID: str = "stage21_fake_provider"
_CHAIN: str = "solana_mainnet"


# ---------------------------------------------------------------------------
# Decode-error classifier mapping the Stage 21.3A error hierarchy
# ---------------------------------------------------------------------------


def _classify_real_decode_error(exc: BaseException) -> str:
    """Map a ``ProviderPayloadError`` subclass to a closed-set
    Stage 22 malformed reason token.

    Any non-``ProviderPayloadError`` exception maps to
    ``decode_unexpected_error``.
    """
    if isinstance(exc, ProviderPayloadShapeError):
        return MALFORMED_REASON_SHAPE_ERROR
    if isinstance(exc, ProviderPayloadFieldTypeError):
        return MALFORMED_REASON_FIELD_TYPE_ERROR
    if isinstance(exc, ProviderPayloadFieldValueError):
        return MALFORMED_REASON_FIELD_VALUE_ERROR
    if isinstance(exc, ProviderPayloadUnsupportedInstructionError):
        return MALFORMED_REASON_UNSUPPORTED_INSTRUCTION
    if isinstance(exc, ProviderPayloadSuspiciousContentError):
        return MALFORMED_REASON_SUSPICIOUS_CONTENT
    if isinstance(exc, ProviderPayloadError):
        return MALFORMED_REASON_UNEXPECTED_ERROR
    return MALFORMED_REASON_UNEXPECTED_ERROR


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _good_payload(
    *,
    provider_event_id: str = "pe-real-1",
    mint: str = "mint_real_aaa",
    slot: int = 1234,
    signature: str = "sig_real_aaaa",
    event_type: str = "real_swap",
    decoded_fields: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "provider_event_id": provider_event_id,
        "provider_name": _PROVIDER_ID,
        "source_kind": "stage21_3a_real_source",
        "chain": _CHAIN,
        "mint": mint,
        "event_type": event_type,
        "observed_at_utc": "2026-05-19T00:00:00Z",
        "slot": slot,
        "signature": signature,
        "instruction_kind": "reserved_for_21_3b",
        "decoded_fields": (
            decoded_fields
            if decoded_fields is not None
            else {"flavor": "vanilla"}
        ),
    }


def _ok_outcome(
    *,
    responses: tuple[Mapping[str, object], ...],
    provider_attempt_index: int = 0,
) -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=True,
        responses=responses,
        status_class=STATUS_CLASS_SUCCESS,
        upstream_error_type=UPSTREAM_ERROR_TYPE_NONE,
        provider_attempt_index=provider_attempt_index,
    )


def _run_with_real_decoder(
    responses: tuple[Mapping[str, object], ...],
    *,
    writer: InMemoryRawCaptureWriter | None = None,
):
    actual_writer = writer if writer is not None else InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id=_PROVIDER_ID,
        chain=_CHAIN,
        fetch_outcome=_ok_outcome(responses=responses),
        observed_at_utc="2026-05-19T00:00:00Z",
        received_at_utc="2026-05-19T00:00:01Z",
        failed_at_utc="2026-05-19T00:00:02Z",
        decode_event_fn=decode_provider_event,
        classify_decode_error_fn=_classify_real_decode_error,
        raw_capture_writer=actual_writer,
    )
    return result, actual_writer


# ---------------------------------------------------------------------------
# Sanity: the Stage 21.3A error hierarchy is reachable from this file
# ---------------------------------------------------------------------------


def test_classifier_covers_every_stage21_3a_error_class() -> None:
    """Every Stage 21.3A ProviderPayloadError subclass must map to
    a closed-set Stage 22 reason. Sanity-check by raising each
    one and routing it through the classifier.
    """
    pairs = (
        (ProviderPayloadShapeError, MALFORMED_REASON_SHAPE_ERROR),
        (ProviderPayloadFieldTypeError, MALFORMED_REASON_FIELD_TYPE_ERROR),
        (ProviderPayloadFieldValueError, MALFORMED_REASON_FIELD_VALUE_ERROR),
        (
            ProviderPayloadUnsupportedInstructionError,
            MALFORMED_REASON_UNSUPPORTED_INSTRUCTION,
        ),
        (
            ProviderPayloadSuspiciousContentError,
            MALFORMED_REASON_SUSPICIOUS_CONTENT,
        ),
    )
    for exc_cls, expected_reason in pairs:
        assert _classify_real_decode_error(exc_cls("test")) == expected_reason
        assert expected_reason in MALFORMED_EVENT_REASONS


# ---------------------------------------------------------------------------
# Real good payload through the helper
# ---------------------------------------------------------------------------


def test_real_good_payload_decodes_and_captures_normalized_event() -> None:
    result, writer = _run_with_real_decoder(
        responses=(_good_payload(),),
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 1
    assert result.events_normalized == 1
    assert result.events_malformed == 0
    captured = writer.captured_normalized_events()
    assert len(captured) == 1
    record = captured[0]
    # The captured normalized_event carries the Stage 21.3A
    # derived event_id (always "evt_<24 hex>").
    assert record["event_id"].startswith("evt_")
    assert len(record["event_id"]) == 4 + 24
    assert record["chain"] == _CHAIN
    assert record["provider_id"] == _PROVIDER_ID


# ---------------------------------------------------------------------------
# Real shape error
# ---------------------------------------------------------------------------


def test_real_shape_error_maps_to_decode_shape_error() -> None:
    # Missing required key "provider_event_id" -> ShapeError
    bad_payload = _good_payload()
    del bad_payload["provider_event_id"]
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_SHAPE_ERROR


def test_real_non_mapping_payload_maps_to_decode_shape_error() -> None:
    # The Stage 21.3A decoder rejects non-Mapping inputs with a
    # ShapeError. The Stage 22.4 helper passes the raw payload
    # through; the captured record's raw_event_hash falls back
    # to the deterministic structural projection because a
    # non-Mapping cannot be safely canonicalised in the same
    # shape (the projection treats primitives as a JSON-safe
    # value but the helper accepts only Mapping payloads
    # through the decode_event_fn shape -- so we pass a
    # Mapping that is rejected by required-key check).
    # Here we use an empty-Mapping payload (still a Mapping,
    # so the helper accepts it) which fails on the required-
    # key check.
    bad_payload: Mapping[str, object] = {}
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_SHAPE_ERROR


# ---------------------------------------------------------------------------
# Real field-type / field-value errors
# ---------------------------------------------------------------------------


def test_real_field_type_error_maps_to_decode_field_type_error() -> None:
    bad_payload = _good_payload()
    bad_payload["slot"] = "not_an_int"  # slot must be int
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_FIELD_TYPE_ERROR


def test_real_field_value_error_maps_to_decode_field_value_error() -> None:
    bad_payload = _good_payload()
    bad_payload["mint"] = ""  # empty -> FieldValueError
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_FIELD_VALUE_ERROR


# ---------------------------------------------------------------------------
# Real unsupported instruction
# ---------------------------------------------------------------------------


def test_real_unsupported_instruction_maps_to_decode_unsupported_instruction() -> None:
    bad_payload = _good_payload()
    bad_payload["instruction_kind"] = "not_in_supported_set"
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_UNSUPPORTED_INSTRUCTION


# ---------------------------------------------------------------------------
# Real suspicious content
# ---------------------------------------------------------------------------


def test_real_suspicious_content_maps_to_decode_suspicious_content() -> None:
    bad_payload = _good_payload()
    # Stage 21.3A FORBIDDEN_SUBSTRINGS includes "secret" --
    # placing it inside a scanned top-level string trips the
    # SuspiciousContentError.
    bad_payload["mint"] = "mint_with_secret_inside"
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_SUSPICIOUS_CONTENT


def test_real_suspicious_content_in_decoded_fields_maps_to_suspicious() -> None:
    bad_payload = _good_payload(
        decoded_fields={"raw_blob": "value_with_webhook_inside"},
    )
    result, writer = _run_with_real_decoder(responses=(bad_payload,))
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    assert malformed[0]["reason"] == MALFORMED_REASON_SUSPICIOUS_CONTENT


# ---------------------------------------------------------------------------
# Mixed real good + poison batch isolates failure
# ---------------------------------------------------------------------------


def test_real_mixed_good_and_poison_isolates_failure() -> None:
    good = _good_payload(
        provider_event_id="pe-mix-1",
        mint="mint_mix_1",
        slot=1001,
        signature="sig_mix_1",
    )
    # Poison: missing required key.
    poison = _good_payload(provider_event_id="pe-mix-poison")
    del poison["signature"]
    # Another good with distinct id.
    good_after = _good_payload(
        provider_event_id="pe-mix-2",
        mint="mint_mix_2",
        slot=1002,
        signature="sig_mix_2",
    )
    result, writer = _run_with_real_decoder(
        responses=(good, poison, good_after),
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 3
    assert result.events_normalized == 2
    assert result.events_malformed == 1
    captured = writer.captured_normalized_events()
    assert len(captured) == 2
    captured_pe_ids = [r["provider_event_id"] for r in captured]
    assert "pe-mix-1" in captured_pe_ids
    assert "pe-mix-2" in captured_pe_ids
    # The malformed record carries the poison provider_event_id
    # because it is a safe non-empty string.
    assert (
        writer.captured_malformed_events()[0]["provider_event_id"]
        == "pe-mix-poison"
    )


# ---------------------------------------------------------------------------
# MappingProxyType payload_summary flows through capture
# ---------------------------------------------------------------------------


def test_real_mapping_proxy_payload_summary_flows_through_capture() -> None:
    # The Stage 21.3A decoder freezes decoded_fields into a
    # MappingProxyType inside the NormalizedLiveEvent's
    # payload_summary. The Stage 22.3 raw capture writer must
    # accept it and serialise it.
    decoded = {"top_field": "scalar_value", "count": 7}
    payload = _good_payload(decoded_fields=decoded)
    result, writer = _run_with_real_decoder(responses=(payload,))
    assert result.events_normalized == 1
    record = writer.captured_normalized_events()[0]
    captured_summary = record["payload_summary"]
    assert isinstance(captured_summary, dict)
    assert captured_summary["top_field"] == "scalar_value"
    assert captured_summary["count"] == 7


def test_real_decoder_returns_frozen_payload_summary() -> None:
    """Defense-in-depth: confirm the Stage 21.3A decoder really
    does freeze payload_summary into a MappingProxyType.
    """
    payload = _good_payload(decoded_fields={"v": "x"})
    event = decode_provider_event(payload)
    assert isinstance(event.payload_summary, MappingProxyType)
