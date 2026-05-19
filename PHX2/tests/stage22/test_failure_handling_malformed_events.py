"""Stage 22.4 malformed-event tests for ``handle_provider_batch``.

Pins the per-event decode-failure path of the Stage 22.4 batch
isolation helper:

  * Every token in ``MALFORMED_EVENT_REASONS`` is reachable via
    a fake decoder + fake classifier pair.
  * ``provider_event_id`` is lifted from the raw payload ONLY
    when it is a safe non-empty string; every other case
    produces the empty string.
  * ``raw_event_hash`` is derived deterministically:
      - identical malformed payloads produce identical hashes;
      - different payloads produce different hashes (content
        path);
      - unencodable payloads fall back to a deterministic
        structural projection of
        ``(provider_id, provider_attempt_index, batch_index)``;
      - the helper NEVER lifts a payload-supplied
        ``raw_event_hash`` value.
  * The captured ``raw_event_hash`` is always 64-char lowercase
    hex (sha256).
  * Exactly one ``MalformedEventRecord`` is captured per failed
    decode.
  * ``classify_decode_error_fn`` returning a token outside
    ``MALFORMED_EVENT_REASONS`` raises
    ``Stage22BatchHandlingContractError``.
  * ``classify_decode_error_fn`` itself raising maps to
    ``MALFORMED_REASON_UNEXPECTED_ERROR``.
  * ``decode_event_fn`` returning ``None`` (or any
    non-NormalizedLiveEvent value) raises
    ``Stage22BatchHandlingContractError``.
  * Raw exception material does not reach the captured record.
  * Raw payload values do not reach the captured record except
    via the vetted ``provider_event_id`` and the derived
    ``raw_event_hash``.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.constants import (
    CAPTURE_LONG_HEX_RUN_MIN_LEN,
    CAPTURE_LONG_TOKENISH_MIN_LEN,
    CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN,
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
from PHX2.stage22.errors import Stage22BatchHandlingContractError
from PHX2.stage22.failure_handling import (
    _derive_malformed_raw_event_hash,
    _extract_safe_provider_event_id,
    handle_provider_batch,
)
from PHX2.stage22.ingest_contracts import ProviderFetchOutcome
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeDecodeError(Exception):
    """Module-private exception used by the fake decoder."""


def _always_raise_decoder(_raw: Mapping[str, object]) -> object:
    raise _FakeDecodeError("simulated decode failure")


def _classify_to(reason: str):
    def _classify(_exc: BaseException) -> str:
        return reason
    return _classify


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


def _run_with_decoder(
    *,
    responses: tuple[Mapping[str, object], ...],
    decoder,
    classifier,
    provider_attempt_index: int = 0,
    provider_id: str = "helius",
    chain: str = "solana_mainnet",
    writer: InMemoryRawCaptureWriter | None = None,
):
    actual_writer = writer if writer is not None else InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id=provider_id,
        chain=chain,
        fetch_outcome=_ok_outcome(
            responses=responses,
            provider_attempt_index=provider_attempt_index,
        ),
        observed_at_utc="2026-05-19T00:00:00Z",
        received_at_utc="2026-05-19T00:00:01Z",
        failed_at_utc="2026-05-19T00:00:02Z",
        decode_event_fn=decoder,
        classify_decode_error_fn=classifier,
        raw_capture_writer=actual_writer,
    )
    return result, actual_writer


# ---------------------------------------------------------------------------
# Every MALFORMED_EVENT_REASONS token is reachable
# ---------------------------------------------------------------------------


def test_every_malformed_event_reason_is_reachable_through_helper() -> None:
    for reason in MALFORMED_EVENT_REASONS:
        result, writer = _run_with_decoder(
            responses=({"k": "v"},),
            decoder=_always_raise_decoder,
            classifier=_classify_to(reason),
        )
        malformed = writer.captured_malformed_events()
        assert len(malformed) == 1
        assert malformed[0]["reason"] == reason
        assert result.events_malformed == 1
        assert result.events_normalized == 0


# ---------------------------------------------------------------------------
# Safe provider_event_id extraction
# ---------------------------------------------------------------------------


def test_safe_provider_event_id_is_lifted_from_payload() -> None:
    payload = {"provider_event_id": "pe-12345-abc"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == "pe-12345-abc"


def test_missing_provider_event_id_becomes_empty_string() -> None:
    payload = {"some_other_key": "value"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_non_string_provider_event_id_becomes_empty_string() -> None:
    payload = {"provider_event_id": 12345}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_empty_provider_event_id_becomes_empty_string() -> None:
    payload = {"provider_event_id": ""}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_overlong_provider_event_id_becomes_empty_string() -> None:
    too_long = "a" * (CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN + 1)
    payload = {"provider_event_id": too_long}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_url_shaped_provider_event_id_becomes_empty_string() -> None:
    payload = {
        "provider_event_id": "h" + "ttps://attacker.invalid/abc",
    }
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_secret_substring_in_provider_event_id_becomes_empty_string() -> None:
    payload = {"provider_event_id": "my-api_key-12345"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_long_hex_run_in_provider_event_id_becomes_empty_string() -> None:
    long_hex_value = "x_" + ("a" * CAPTURE_LONG_HEX_RUN_MIN_LEN)
    payload = {"provider_event_id": long_hex_value}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_long_tokenish_run_in_provider_event_id_becomes_empty_string() -> None:
    # Build a token-shape string >= CAPTURE_LONG_TOKENISH_MIN_LEN
    # with mixed letters and digits at >= 80% alphanumeric.
    tokenish = "Abc123Def456Ghi789Jkl012Mno345Pq"
    assert len(tokenish) >= CAPTURE_LONG_TOKENISH_MIN_LEN
    payload = {"provider_event_id": tokenish}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


# ---------------------------------------------------------------------------
# Deterministic raw_event_hash derivation
# ---------------------------------------------------------------------------


def test_same_payload_produces_same_raw_event_hash() -> None:
    payload_a = {"foo": "bar", "n": 42}
    payload_b = {"n": 42, "foo": "bar"}  # same content, different key order
    _, writer_a = _run_with_decoder(
        responses=(payload_a,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    _, writer_b = _run_with_decoder(
        responses=(payload_b,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a == hash_b


def test_different_payload_produces_different_raw_event_hash_on_content_path() -> None:
    payload_a = {"foo": "bar"}
    payload_b = {"foo": "baz"}
    _, writer_a = _run_with_decoder(
        responses=(payload_a,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    _, writer_b = _run_with_decoder(
        responses=(payload_b,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a != hash_b


def test_raw_event_hash_is_64_char_lowercase_hex() -> None:
    payload = {"foo": "bar"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    raw_hash = writer.captured_malformed_events()[0]["raw_event_hash"]
    assert isinstance(raw_hash, str)
    assert len(raw_hash) == 64
    for ch in raw_hash:
        assert ch in "0123456789abcdef", (
            f"raw_event_hash {raw_hash!r} is not lowercase hex"
        )


def test_raw_event_hash_is_never_empty() -> None:
    payload: Mapping[str, object] = {}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    raw_hash = writer.captured_malformed_events()[0]["raw_event_hash"]
    assert raw_hash != ""


def test_raw_event_hash_does_not_trust_payload_supplied_value() -> None:
    """An attacker-supplied ``raw_event_hash`` field on the
    malformed payload must NOT be lifted to the captured
    record's ``raw_event_hash``.
    """
    attacker_hash = "f" * 64
    payload = {"raw_event_hash": attacker_hash, "data": "x"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    assert record["raw_event_hash"] != attacker_hash


def test_unencodable_payload_falls_back_to_deterministic_hash() -> None:
    """A payload containing bytes cannot be safely canonicalised;
    the helper falls back to a deterministic structural hash.
    """
    payload = {"data": b"non-encodable bytes"}
    _, writer_a = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    _, writer_b = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a == hash_b


def test_unencodable_payload_with_different_content_uses_same_fallback_at_same_batch_index() -> None:
    """The structural fallback depends only on provider_id,
    provider_attempt_index, and batch_index. Two different
    unencodable payloads at the same call site hash to the
    same value.
    """
    payload_a = {"x": b"bytes_a"}
    payload_b = {"y": b"bytes_b", "other": object()}
    _, writer_a = _run_with_decoder(
        responses=(payload_a,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    _, writer_b = _run_with_decoder(
        responses=(payload_b,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a == hash_b


def test_fallback_hash_changes_with_provider_attempt_index() -> None:
    payload = {"data": b"unencodable"}
    _, writer_a = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
        provider_attempt_index=0,
    )
    _, writer_b = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
        provider_attempt_index=1,
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a != hash_b


def test_fallback_hash_changes_with_provider_id() -> None:
    payload = {"data": b"unencodable"}
    _, writer_a = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
        provider_id="provider_a",
    )
    _, writer_b = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
        provider_id="provider_b",
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a != hash_b


def test_fallback_hash_changes_with_batch_index() -> None:
    bad = {"data": b"unencodable"}
    _, writer = _run_with_decoder(
        responses=(bad, bad),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 2
    assert malformed[0]["raw_event_hash"] != malformed[1]["raw_event_hash"]


def test_payload_with_non_finite_float_uses_fallback() -> None:
    inf = float("inf")
    nan = float("nan")
    payload_inf = {"v": inf}
    payload_nan = {"v": nan}
    _, writer_inf = _run_with_decoder(
        responses=(payload_inf,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    _, writer_nan = _run_with_decoder(
        responses=(payload_nan,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    # Both fell back to the same structural projection.
    assert (
        writer_inf.captured_malformed_events()[0]["raw_event_hash"]
        == writer_nan.captured_malformed_events()[0]["raw_event_hash"]
    )


def test_payload_with_non_string_mapping_key_uses_fallback() -> None:
    payload_bad_key: dict[object, object] = {123: "value"}
    payload_other: dict[object, object] = {456: "different value"}
    _, writer_a = _run_with_decoder(
        responses=(payload_bad_key,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    _, writer_b = _run_with_decoder(
        responses=(payload_other,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    hash_a = writer_a.captured_malformed_events()[0]["raw_event_hash"]
    hash_b = writer_b.captured_malformed_events()[0]["raw_event_hash"]
    assert hash_a == hash_b


# ---------------------------------------------------------------------------
# One MalformedEventRecord per failed decode
# ---------------------------------------------------------------------------


def test_each_malformed_response_captures_exactly_one_record() -> None:
    responses = ({"a": 1}, {"b": 2}, {"c": 3})
    _, writer = _run_with_decoder(
        responses=responses,
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    assert len(writer.captured_malformed_events()) == 3


# ---------------------------------------------------------------------------
# Classifier returning out-of-set token is a contract violation
# ---------------------------------------------------------------------------


def test_out_of_set_classifier_return_raises_contract_error() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_ok_outcome(responses=({"k": "v"},)),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_always_raise_decoder,
            classify_decode_error_fn=_classify_to("not_a_valid_reason"),
            raw_capture_writer=writer,
        )
    # No malformed record captured -- the helper raised before
    # the capture call.
    assert writer.captured_malformed_events() == ()


def test_non_string_classifier_return_raises_contract_error() -> None:
    writer = InMemoryRawCaptureWriter()

    def _classify_non_string(_exc: BaseException):  # type: ignore[no-untyped-def]
        return 42  # int, not a string

    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_ok_outcome(responses=({"k": "v"},)),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_always_raise_decoder,
            classify_decode_error_fn=_classify_non_string,
            raw_capture_writer=writer,
        )


# ---------------------------------------------------------------------------
# Classifier raising maps to decode_unexpected_error
# ---------------------------------------------------------------------------


def test_raising_classifier_maps_to_decode_unexpected_error() -> None:
    def _raising_classify(_exc: BaseException) -> str:
        raise ValueError("classifier blew up")

    _, writer = _run_with_decoder(
        responses=({"k": "v"},),
        decoder=_always_raise_decoder,
        classifier=_raising_classify,
    )
    record = writer.captured_malformed_events()[0]
    assert record["reason"] == MALFORMED_REASON_UNEXPECTED_ERROR


# ---------------------------------------------------------------------------
# Decoder returning a non-NormalizedLiveEvent is a contract violation
# ---------------------------------------------------------------------------


def test_decoder_returning_none_raises_contract_error() -> None:
    def _none_decoder(_raw: Mapping[str, object]):  # type: ignore[no-untyped-def]
        return None

    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_ok_outcome(responses=({"k": "v"},)),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_none_decoder,
            classify_decode_error_fn=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
            raw_capture_writer=writer,
        )


def test_decoder_returning_dict_raises_contract_error() -> None:
    def _dict_decoder(_raw: Mapping[str, object]):  # type: ignore[no-untyped-def]
        return {"not": "a NormalizedLiveEvent"}

    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id="helius",
            chain="solana_mainnet",
            fetch_outcome=_ok_outcome(responses=({"k": "v"},)),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_dict_decoder,
            classify_decode_error_fn=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
            raw_capture_writer=writer,
        )


# ---------------------------------------------------------------------------
# No raw exception material reaches the captured record
# ---------------------------------------------------------------------------


def test_malformed_record_carries_no_exception_message() -> None:
    """``_FakeDecodeError("simulated decode failure")`` is raised
    by the decoder; the captured record must not echo the
    exception string anywhere.
    """
    payload = {"k": "v"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    for value in record.values():
        text = str(value)
        assert "simulated decode failure" not in text
        assert "_FakeDecodeError" not in text
        assert "Traceback" not in text


def test_malformed_record_carries_no_raw_payload_values() -> None:
    """A payload value that is not the vetted provider_event_id
    must NOT appear verbatim in the captured record.
    """
    secret_token = "secret_token_value_zzz"
    payload = {
        "provider_event_id": "safe-id-1",
        "data": secret_token,
        "another": "another_marker_value",
    }
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    record = writer.captured_malformed_events()[0]
    # provider_event_id is lifted (safe shape).
    assert record["provider_event_id"] == "safe-id-1"
    # No other raw payload value appears.
    for field, value in record.items():
        if field == "provider_event_id":
            continue
        text = str(value)
        assert secret_token not in text
        assert "another_marker_value" not in text


# ---------------------------------------------------------------------------
# Parametrised: each MALFORMED_EVENT_REASONS token round-trips cleanly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        MALFORMED_REASON_SHAPE_ERROR,
        MALFORMED_REASON_FIELD_TYPE_ERROR,
        MALFORMED_REASON_FIELD_VALUE_ERROR,
        MALFORMED_REASON_UNSUPPORTED_INSTRUCTION,
        MALFORMED_REASON_SUSPICIOUS_CONTENT,
        MALFORMED_REASON_UNEXPECTED_ERROR,
    ],
)
def test_each_individual_malformed_reason_token(reason: str) -> None:
    payload = {"k": "v"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(reason),
    )
    record = writer.captured_malformed_events()[0]
    assert record["reason"] == reason
    assert record["reason"] in MALFORMED_EVENT_REASONS


# ---------------------------------------------------------------------------
# Audit regression: lone Unicode surrogate at the helper level
# ---------------------------------------------------------------------------


def test_derive_malformed_raw_event_hash_handles_lone_surrogate() -> None:
    """Regression for a Stage 22.4 targeted audit finding.

    A payload value containing a lone surrogate
    (``"\\ud800"``) passes ``json.dumps(ensure_ascii=False)``
    but the subsequent ``str.encode("utf-8")`` raises
    ``UnicodeEncodeError``. The helper must catch that case
    and route to the deterministic structural fallback rather
    than letting the exception propagate. The returned hash
    must remain a valid sha256 hex.
    """
    payload = {"bad": "\ud800"}
    raw_hash = _derive_malformed_raw_event_hash(
        raw_payload=payload,
        provider_id="helius",
        provider_attempt_index=0,
        batch_index=0,
    )
    assert isinstance(raw_hash, str)
    assert raw_hash != ""
    assert len(raw_hash) == 64
    for ch in raw_hash:
        assert ch in "0123456789abcdef", (
            f"raw_event_hash {raw_hash!r} is not lowercase hex"
        )


def test_derive_malformed_raw_event_hash_surrogate_uses_deterministic_fallback() -> None:
    """Two different surrogate-bearing payloads at the same call
    site fall back to the same structural hash (deterministic
    fallback projected from provenance only).
    """
    payload_a = {"bad": "\ud800"}
    payload_b = {"different": "\udfff", "more": "\ud83d"}
    hash_a = _derive_malformed_raw_event_hash(
        raw_payload=payload_a,
        provider_id="helius",
        provider_attempt_index=2,
        batch_index=5,
    )
    hash_b = _derive_malformed_raw_event_hash(
        raw_payload=payload_b,
        provider_id="helius",
        provider_attempt_index=2,
        batch_index=5,
    )
    assert hash_a == hash_b


def test_derive_malformed_raw_event_hash_surrogate_fallback_changes_with_provenance() -> None:
    """The surrogate fallback changes when the provenance tuple
    changes, so two surrogate-bearing payloads at different
    batch positions still hash to distinct values.
    """
    payload = {"bad": "\ud800"}
    hash_a = _derive_malformed_raw_event_hash(
        raw_payload=payload,
        provider_id="helius",
        provider_attempt_index=0,
        batch_index=0,
    )
    hash_b = _derive_malformed_raw_event_hash(
        raw_payload=payload,
        provider_id="helius",
        provider_attempt_index=0,
        batch_index=1,
    )
    assert hash_a != hash_b


def test_capture_path_handles_surrogate_payload_through_helper() -> None:
    """End-to-end: a single surrogate-bearing payload through
    ``handle_provider_batch`` is captured as one malformed
    event with a valid sha256 hex hash; no raw surrogate value
    appears in the captured record.
    """
    payload = {"bad": "\ud800"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    record = malformed[0]
    raw_hash = record["raw_event_hash"]
    assert isinstance(raw_hash, str)
    assert len(raw_hash) == 64
    for ch in raw_hash:
        assert ch in "0123456789abcdef"
    for value in record.values():
        assert "\ud800" not in str(value)


# ---------------------------------------------------------------------------
# Audit regression: lone surrogate inside payload-supplied provider_event_id
# ---------------------------------------------------------------------------


def test_extract_safe_provider_event_id_rejects_lone_surrogate() -> None:
    """Direct helper-level: a payload-supplied
    ``provider_event_id`` that contains a lone surrogate is
    not UTF-8 encodable and must be rejected.
    """
    assert _extract_safe_provider_event_id(
        {"provider_event_id": "\ud800"}
    ) == ""


def test_extract_safe_provider_event_id_rejects_mixed_surrogate_prefix() -> None:
    """Even a surrogate buried inside an otherwise-safe-looking
    string makes the whole value codec-hostile.
    """
    assert _extract_safe_provider_event_id(
        {"provider_event_id": "pe-prefix-\ud800-suffix"}
    ) == ""


def test_extract_safe_provider_event_id_still_accepts_safe_values() -> None:
    """The new UTF-8 safety check must not regress safe values:
    ASCII, non-ASCII Unicode that round-trips through UTF-8,
    and short alphanumeric identifiers remain accepted.
    """
    assert _extract_safe_provider_event_id(
        {"provider_event_id": "pe-12345"}
    ) == "pe-12345"
    # A legitimate non-ASCII char that round-trips through UTF-8
    # (here a Greek alpha) remains accepted.
    assert _extract_safe_provider_event_id(
        {"provider_event_id": "pe-α-1"}
    ) == "pe-α-1"


def test_surrogate_provider_event_id_captures_empty_string_in_record() -> None:
    """End-to-end: a malformed payload with
    ``{"provider_event_id": "\\ud800"}`` is captured exactly
    once; the captured record's ``provider_event_id`` is the
    empty string, the ``raw_event_hash`` is a valid sha256
    hex, and no surrogate character appears in any captured
    field.
    """
    payload = {"provider_event_id": "\ud800"}
    _, writer = _run_with_decoder(
        responses=(payload,),
        decoder=_always_raise_decoder,
        classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    )
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    record = malformed[0]
    assert record["provider_event_id"] == ""
    raw_hash = record["raw_event_hash"]
    assert isinstance(raw_hash, str)
    assert raw_hash != ""
    assert len(raw_hash) == 64
    for ch in raw_hash:
        assert ch in "0123456789abcdef"
    for value in record.values():
        assert "\ud800" not in str(value), (
            f"surrogate leaked into captured field value {value!r}"
        )
