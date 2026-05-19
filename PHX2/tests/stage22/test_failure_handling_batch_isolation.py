"""Stage 22.4 batch-isolation tests for ``handle_provider_batch``.

Pins the per-batch outcome rules and the cross-event
poison-isolation property of the Stage 22.4 helper:

  * Outcomes for ok=True:
      - zero responses                -> provider_returned_zero
      - all responses decode well     -> ok
      - mixed good + malformed        -> ok
      - all responses malformed       -> all_malformed
  * Per-event isolation:
      - a poisoned response at index 0 does not block later
        good responses;
      - a poisoned response in the middle does not block later
        good responses;
      - a poisoned response at the end preserves earlier good
        responses;
      - multiple malformed responses each capture exactly one
        MalformedEventRecord.
  * Envelope ordering preserves input order.
  * Writer captured counts match the result's per-record-family
    counts.
  * ``events_received == len(fetch_outcome.responses)``.
  * ``provider_attempt_index`` flows from
    ``fetch_outcome.provider_attempt_index`` into every
    captured envelope and into the result record.
  * A capture-writer failure mid-batch aborts the batch
    immediately; later events are NOT processed.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.constants import (
    CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
    CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
    MALFORMED_REASON_SHAPE_ERROR,
    STATUS_CLASS_SUCCESS,
    UPSTREAM_ERROR_TYPE_NONE,
)
from PHX2.stage22.errors import Stage22CaptureContractError
from PHX2.stage22.failure_handling import handle_provider_batch
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    NormalizedLiveEvent,
    ProviderFetchOutcome,
)
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


_CHAIN: str = "solana_mainnet"
_PROVIDER_ID: str = "helius"


class _FakeDecodeError(Exception):
    """Used by the fake decoder to simulate a decode failure."""


def _make_good_event(
    *,
    event_id: str,
    provider_event_id: str,
    raw_event_hash: str,
    mint: str = "mint_aaa",
    slot: int = 100,
    signature: str = "sig_aaaa",
    event_type: str = "fake_swap",
) -> NormalizedLiveEvent:
    return NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name="stage21_fake_provider",
        source_kind="stage21_fake_source",
        chain=_CHAIN,
        mint=mint,
        event_type=event_type,
        observed_at_utc="2026-05-19T00:00:00Z",
        slot=slot,
        signature=signature,
        raw_event_hash=raw_event_hash,
        normalized_schema_version="stage21_v0_normalized_event",
        payload_summary={},
    )


def _good_decoder_for(payload_to_event: dict[str, NormalizedLiveEvent]):
    """Build a decoder that maps a payload's ``marker`` field to a
    pre-built NormalizedLiveEvent, and raises on missing keys.
    """
    def _decode(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        marker = raw.get("marker")
        if not isinstance(marker, str):
            raise _FakeDecodeError("missing marker")
        if marker not in payload_to_event:
            raise _FakeDecodeError("marker not registered")
        return payload_to_event[marker]
    return _decode


def _always_raise_decoder(_raw: Mapping[str, object]) -> NormalizedLiveEvent:
    raise _FakeDecodeError("always fail")


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


class _OneShotFailingCaptureWriter:
    """RawCaptureWriter that succeeds on every method until a
    nominated call index, then raises Stage22CaptureContractError.
    """

    def __init__(self, *, fail_on_call: int) -> None:
        self._inner = InMemoryRawCaptureWriter()
        self._call_count = 0
        self._fail_on_call = fail_on_call

    def _next(self) -> bool:
        result = self._call_count == self._fail_on_call
        self._call_count += 1
        return result

    def capture(self, *, envelope: IngestEventEnvelope) -> None:
        if self._next():
            raise Stage22CaptureContractError(
                "synthetic failure on capture"
            )
        self._inner.capture(envelope=envelope)

    def capture_malformed(self, *, record) -> None:  # type: ignore[no-untyped-def]
        if self._next():
            raise Stage22CaptureContractError(
                "synthetic failure on capture_malformed"
            )
        self._inner.capture_malformed(record=record)

    def capture_provider_failure(self, *, record) -> None:  # type: ignore[no-untyped-def]
        if self._next():
            raise Stage22CaptureContractError(
                "synthetic failure on capture_provider_failure"
            )
        self._inner.capture_provider_failure(record=record)

    @property
    def inner(self) -> InMemoryRawCaptureWriter:
        return self._inner


def _run(
    *,
    responses: tuple[Mapping[str, object], ...],
    decoder,
    classifier=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
    provider_attempt_index: int = 0,
    writer: InMemoryRawCaptureWriter | None = None,
):
    actual_writer = writer if writer is not None else InMemoryRawCaptureWriter()
    result = handle_provider_batch(
        provider_id=_PROVIDER_ID,
        chain=_CHAIN,
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
# Outcomes for ok=True
# ---------------------------------------------------------------------------


def test_zero_responses_returns_provider_returned_zero() -> None:
    result, writer = _run(responses=(), decoder=_always_raise_decoder)
    assert result.outcome == INGEST_OUTCOME_PROVIDER_RETURNED_ZERO
    assert result.events_received == 0
    assert result.events_normalized == 0
    assert result.events_malformed == 0
    assert result.provider_failures == 0
    assert result.last_failure_label == ""
    assert result.envelopes == ()
    assert writer.captured_all() == ()


def test_all_good_responses_returns_ok() -> None:
    good_event = _make_good_event(
        event_id="evt_" + "a" * 24,
        provider_event_id="pe-good-1",
        raw_event_hash="a" * 64,
    )
    decoder = _good_decoder_for({"g1": good_event})
    result, writer = _run(
        responses=({"marker": "g1"},),
        decoder=decoder,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 1
    assert result.events_normalized == 1
    assert result.events_malformed == 0
    assert len(writer.captured_normalized_events()) == 1


def test_mixed_good_and_malformed_returns_ok() -> None:
    good_event = _make_good_event(
        event_id="evt_" + "b" * 24,
        provider_event_id="pe-good-2",
        raw_event_hash="b" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good_event
        raise _FakeDecodeError("bad")

    result, writer = _run(
        responses=(
            {"kind": "good"},
            {"kind": "bad"},
            {"kind": "good"},
        ),
        decoder=_decoder,
    )
    # Two good events would conflict on duplicate event_id at
    # the capture writer (writer enforces non-empty unique
    # event_id but does NOT enforce uniqueness across records).
    # The InMemoryRawCaptureWriter accepts duplicate event_ids
    # without complaint -- it is an append-only stream.
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 3
    assert result.events_normalized == 2
    assert result.events_malformed == 1
    assert len(writer.captured_normalized_events()) == 2
    assert len(writer.captured_malformed_events()) == 1


def test_all_malformed_returns_all_malformed() -> None:
    result, writer = _run(
        responses=({"a": 1}, {"b": 2}),
        decoder=_always_raise_decoder,
    )
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    assert result.events_received == 2
    assert result.events_normalized == 0
    assert result.events_malformed == 2
    assert result.provider_failures == 0
    assert result.envelopes == ()
    assert len(writer.captured_malformed_events()) == 2
    assert writer.captured_normalized_events() == ()


# ---------------------------------------------------------------------------
# Per-event isolation
# ---------------------------------------------------------------------------


def test_poison_at_index_zero_does_not_block_later_good_events() -> None:
    good_event = _make_good_event(
        event_id="evt_" + "c" * 24,
        provider_event_id="pe-good-c",
        raw_event_hash="c" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good_event
        raise _FakeDecodeError("bad")

    result, writer = _run(
        responses=({"kind": "bad"}, {"kind": "good"}),
        decoder=_decoder,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_normalized == 1
    assert result.events_malformed == 1


def test_poison_in_the_middle_does_not_block_later_good_events() -> None:
    good_event = _make_good_event(
        event_id="evt_" + "d" * 24,
        provider_event_id="pe-good-d",
        raw_event_hash="d" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good_event
        raise _FakeDecodeError("bad")

    result, writer = _run(
        responses=(
            {"kind": "good"},
            {"kind": "bad"},
            {"kind": "good"},
            {"kind": "good"},
        ),
        decoder=_decoder,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 4
    assert result.events_normalized == 3
    assert result.events_malformed == 1


def test_poison_at_end_preserves_earlier_good_events() -> None:
    good_event = _make_good_event(
        event_id="evt_" + "e" * 24,
        provider_event_id="pe-good-e",
        raw_event_hash="e" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good_event
        raise _FakeDecodeError("bad")

    result, writer = _run(
        responses=(
            {"kind": "good"},
            {"kind": "good"},
            {"kind": "bad"},
        ),
        decoder=_decoder,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 3
    assert result.events_normalized == 2
    assert result.events_malformed == 1


def test_multiple_malformed_events_captured_separately() -> None:
    result, writer = _run(
        responses=({"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}),
        decoder=_always_raise_decoder,
    )
    assert result.events_malformed == 4
    malformed = writer.captured_malformed_events()
    assert len(malformed) == 4
    hashes = [r["raw_event_hash"] for r in malformed]
    assert len(set(hashes)) == 4, (
        "each distinct malformed payload should produce a distinct "
        "raw_event_hash on the content path"
    )


# ---------------------------------------------------------------------------
# Envelope ordering preserves input order
# ---------------------------------------------------------------------------


def test_envelopes_preserve_input_order() -> None:
    event_a = _make_good_event(
        event_id="evt_" + "a" * 24,
        provider_event_id="pe-a",
        raw_event_hash="a" * 64,
        mint="mint_a",
    )
    event_b = _make_good_event(
        event_id="evt_" + "b" * 24,
        provider_event_id="pe-b",
        raw_event_hash="b" * 64,
        mint="mint_b",
    )
    event_c = _make_good_event(
        event_id="evt_" + "c" * 24,
        provider_event_id="pe-c",
        raw_event_hash="c" * 64,
        mint="mint_c",
    )
    by_marker = {"a": event_a, "b": event_b, "c": event_c}
    decoder = _good_decoder_for(by_marker)

    result, _ = _run(
        responses=(
            {"marker": "a"},
            {"marker": "b"},
            {"marker": "c"},
        ),
        decoder=decoder,
    )
    assert tuple(env.event.provider_event_id for env in result.envelopes) == (
        "pe-a",
        "pe-b",
        "pe-c",
    )


def test_envelopes_preserve_order_when_interleaved_with_malformed() -> None:
    event_x = _make_good_event(
        event_id="evt_" + "x" * 24,
        provider_event_id="pe-x",
        raw_event_hash="x" * 64,
        mint="mint_x",
    )
    event_y = _make_good_event(
        event_id="evt_" + "y" * 24,
        provider_event_id="pe-y",
        raw_event_hash="y" * 64,
        mint="mint_y",
    )
    by_marker = {"x": event_x, "y": event_y}
    decoder = _good_decoder_for(by_marker)

    result, _ = _run(
        responses=(
            {"marker": "x"},
            {"marker": "missing"},  # decoder fails because marker not in map
            {"marker": "y"},
        ),
        decoder=decoder,
    )
    assert result.events_normalized == 2
    assert tuple(env.event.provider_event_id for env in result.envelopes) == (
        "pe-x",
        "pe-y",
    )


# ---------------------------------------------------------------------------
# Writer captured counts match the result counts
# ---------------------------------------------------------------------------


def test_writer_captured_counts_match_result_counts() -> None:
    good = _make_good_event(
        event_id="evt_" + "g" * 24,
        provider_event_id="pe-g",
        raw_event_hash="g" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good
        raise _FakeDecodeError("bad")

    result, writer = _run(
        responses=(
            {"kind": "good"},
            {"kind": "bad"},
            {"kind": "bad"},
            {"kind": "good"},
            {"kind": "good"},
        ),
        decoder=_decoder,
    )
    assert len(writer.captured_normalized_events()) == result.events_normalized
    assert len(writer.captured_malformed_events()) == result.events_malformed
    assert writer.captured_provider_failures() == ()


# ---------------------------------------------------------------------------
# events_received reflects fetch_outcome.responses length
# ---------------------------------------------------------------------------


def test_events_received_equals_responses_length_when_all_good() -> None:
    good = _make_good_event(
        event_id="evt_" + "h" * 24,
        provider_event_id="pe-h",
        raw_event_hash="h" * 64,
    )
    decoder = _good_decoder_for({"h": good})
    result, _ = _run(
        responses=tuple({"marker": "h"} for _ in range(5)),
        decoder=decoder,
    )
    assert result.events_received == 5


def test_events_received_equals_responses_length_when_all_bad() -> None:
    result, _ = _run(
        responses=tuple({"i": i} for i in range(7)),
        decoder=_always_raise_decoder,
    )
    assert result.events_received == 7


# ---------------------------------------------------------------------------
# provider_attempt_index flows into envelopes and result
# ---------------------------------------------------------------------------


def test_provider_attempt_index_flows_into_envelopes() -> None:
    good = _make_good_event(
        event_id="evt_" + "i" * 24,
        provider_event_id="pe-i",
        raw_event_hash="i" * 64,
    )
    decoder = _good_decoder_for({"i": good})
    result, _ = _run(
        responses=({"marker": "i"},),
        decoder=decoder,
        provider_attempt_index=4,
    )
    assert result.provider_attempt_index == 4
    assert result.envelopes[0].provider_attempt_index == 4


def test_provider_attempt_index_flows_into_result_on_zero_path() -> None:
    result, _ = _run(
        responses=(),
        decoder=_always_raise_decoder,
        provider_attempt_index=9,
    )
    assert result.provider_attempt_index == 9


# ---------------------------------------------------------------------------
# Capture failure mid-batch aborts and stops later processing
# ---------------------------------------------------------------------------


def test_capture_failure_mid_batch_aborts_and_stops_processing() -> None:
    """The third capture call (index=2) is the malformed capture
    for the second response. Synthetic failure there must abort
    the batch immediately; the third response must NOT be
    processed.
    """
    good = _make_good_event(
        event_id="evt_" + "j" * 24,
        provider_event_id="pe-j",
        raw_event_hash="j" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good
        raise _FakeDecodeError("bad")

    seen_indexes: list[int] = []

    def _tracking_decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        seen_indexes.append(int(raw["i"]))  # type: ignore[arg-type]
        return _decoder(raw)

    writer = _OneShotFailingCaptureWriter(fail_on_call=1)
    with pytest.raises(Stage22CaptureContractError):
        handle_provider_batch(
            provider_id=_PROVIDER_ID,
            chain=_CHAIN,
            fetch_outcome=_ok_outcome(
                responses=(
                    {"i": 0, "kind": "good"},
                    {"i": 1, "kind": "bad"},
                    {"i": 2, "kind": "good"},
                ),
            ),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_tracking_decoder,
            classify_decode_error_fn=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
            raw_capture_writer=writer,
        )
    # Decoder saw indexes 0 and 1 only -- index 2 was never
    # processed because the failed malformed capture aborted.
    assert seen_indexes == [0, 1]
    # The good envelope captured before the failure remains.
    assert len(writer.inner.captured_normalized_events()) == 1
    assert writer.inner.captured_normalized_events()[0]["event_id"] == (
        "evt_" + "j" * 24
    )


def test_capture_failure_on_first_good_event_aborts_immediately() -> None:
    good = _make_good_event(
        event_id="evt_" + "k" * 24,
        provider_event_id="pe-k",
        raw_event_hash="k" * 64,
    )
    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        return good

    writer = _OneShotFailingCaptureWriter(fail_on_call=0)
    with pytest.raises(Stage22CaptureContractError):
        handle_provider_batch(
            provider_id=_PROVIDER_ID,
            chain=_CHAIN,
            fetch_outcome=_ok_outcome(
                responses=({"kind": "good"}, {"kind": "good"}),
            ),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_decoder,
            classify_decode_error_fn=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
            raw_capture_writer=writer,
        )
    # No good event survived the abort.
    assert writer.inner.captured_normalized_events() == ()


# ---------------------------------------------------------------------------
# Chain mismatch is a contract violation
# ---------------------------------------------------------------------------


def test_decoded_event_chain_mismatch_raises_contract_error() -> None:
    """The decoder returns a NormalizedLiveEvent whose chain
    does not match the caller-supplied chain. The helper must
    raise Stage22BatchHandlingContractError.
    """
    from PHX2.stage22.errors import Stage22BatchHandlingContractError

    wrong_chain_event = NormalizedLiveEvent(
        event_id="evt_" + "z" * 24,
        provider_event_id="pe-z",
        provider_name="stage21_fake_provider",
        source_kind="stage21_fake_source",
        chain="ethereum_mainnet",  # different from caller chain
        mint="mint_z",
        event_type="fake_swap",
        observed_at_utc="2026-05-19T00:00:00Z",
        slot=1,
        signature="sig_z",
        raw_event_hash="z" * 64,
        normalized_schema_version="stage21_v0_normalized_event",
        payload_summary={},
    )

    def _decoder(_raw: Mapping[str, object]) -> NormalizedLiveEvent:
        return wrong_chain_event

    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22BatchHandlingContractError):
        handle_provider_batch(
            provider_id=_PROVIDER_ID,
            chain=_CHAIN,  # solana_mainnet
            fetch_outcome=_ok_outcome(responses=({"k": "v"},)),
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            decode_event_fn=_decoder,
            classify_decode_error_fn=_classify_to(MALFORMED_REASON_SHAPE_ERROR),
            raw_capture_writer=writer,
        )


# ---------------------------------------------------------------------------
# Ingest key shape on the envelope
# ---------------------------------------------------------------------------


def test_envelope_ingest_key_uses_caller_provider_id_and_chain() -> None:
    good = _make_good_event(
        event_id="evt_" + "m" * 24,
        provider_event_id="pe-m",
        raw_event_hash="m" * 64,
    )
    decoder = _good_decoder_for({"m": good})
    result, _ = _run(
        responses=({"marker": "m"},),
        decoder=decoder,
    )
    envelope = result.envelopes[0]
    assert envelope.ingest_key.provider_id == _PROVIDER_ID
    assert envelope.ingest_key.chain == _CHAIN
    assert envelope.ingest_key.event_id == "evt_" + "m" * 24
    assert envelope.ingest_key.provider_event_id == "pe-m"
    assert envelope.ingest_key.raw_event_hash == "m" * 64


# ---------------------------------------------------------------------------
# Audit regression: lone Unicode surrogate must not kill the batch
# ---------------------------------------------------------------------------


def test_lone_surrogate_payload_does_not_kill_batch() -> None:
    """Regression for a Stage 22.4 targeted audit finding.

    A malformed payload whose canonical JSON contains a lone
    surrogate string (e.g. ``"\\ud800"``) used to crash
    ``_derive_malformed_raw_event_hash`` with
    ``UnicodeEncodeError``. The crash propagated above the
    ``capture_malformed`` call and killed the surrounding
    batch, violating the Stage 22.4 isolation guarantee that
    one bad event must not abort sibling events.

    The fix routes lone surrogates (and any other JSON-text
    that fails strict UTF-8 encoding) into the deterministic
    structural-fallback hash. The malformed event is captured
    cleanly and the following good event is still processed.
    """
    good = _make_good_event(
        event_id="evt_" + "s" * 24,
        provider_event_id="pe-good-after-surrogate",
        raw_event_hash="s" * 64,
        mint="mint_s",
        slot=5151,
        signature="sig_s",
    )

    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good
        raise _FakeDecodeError("decode failed on surrogate payload")

    surrogate_payload: Mapping[str, object] = {"bad": "\ud800"}
    good_payload: Mapping[str, object] = {"kind": "good"}

    result, writer = _run(
        responses=(surrogate_payload, good_payload),
        decoder=_decoder,
    )

    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 2
    assert result.events_malformed == 1
    assert result.events_normalized == 1

    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    raw_hash = malformed[0]["raw_event_hash"]
    assert isinstance(raw_hash, str)
    assert len(raw_hash) == 64
    for ch in raw_hash:
        assert ch in "0123456789abcdef", (
            f"raw_event_hash {raw_hash!r} is not lowercase hex"
        )

    # No raw surrogate payload value is stored in the captured
    # malformed record. The structural fallback projects only
    # provenance (provider_id / provider_attempt_index /
    # batch_index); the literal surrogate character never
    # reaches the captured record.
    for value in malformed[0].values():
        text = str(value)
        assert "\ud800" not in text, (
            "raw surrogate character leaked into captured "
            "malformed record"
        )

    # The good event after the surrogate was processed and
    # captured cleanly.
    normalized = writer.captured_normalized_events()
    assert len(normalized) == 1
    assert normalized[0]["provider_event_id"] == "pe-good-after-surrogate"


def test_surrogate_provider_event_id_does_not_block_following_good_event() -> None:
    """Audit regression for the second-round Stage 22.4 finding.

    A malformed payload whose ``provider_event_id`` field is a
    lone surrogate used to flow into the captured record's
    ``provider_event_id`` slot verbatim, violating the
    "no raw surrogate stored" rule. The fix makes
    ``_extract_safe_provider_event_id`` reject UTF-8-hostile
    strings, so the captured ``provider_event_id`` becomes the
    empty string while batch isolation continues to hold: the
    surrogate event is captured exactly once and the following
    good event is still processed.
    """
    good = _make_good_event(
        event_id="evt_" + "u" * 24,
        provider_event_id="pe-good-after-pe-surrogate",
        raw_event_hash="u" * 64,
        mint="mint_u",
        slot=6262,
        signature="sig_u",
    )

    def _decoder(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        if raw.get("kind") == "good":
            return good
        raise _FakeDecodeError(
            "decode failed on payload with surrogate provider_event_id"
        )

    surrogate_pe_payload: Mapping[str, object] = {
        "provider_event_id": "\ud800",
        "kind": "bad",
    }
    good_payload: Mapping[str, object] = {"kind": "good"}

    result, writer = _run(
        responses=(surrogate_pe_payload, good_payload),
        decoder=_decoder,
    )

    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 2
    assert result.events_malformed == 1
    assert result.events_normalized == 1

    malformed = writer.captured_malformed_events()
    assert len(malformed) == 1
    record = malformed[0]
    assert record["provider_event_id"] == ""
    raw_hash = record["raw_event_hash"]
    assert isinstance(raw_hash, str)
    assert len(raw_hash) == 64
    for ch in raw_hash:
        assert ch in "0123456789abcdef"
    for value in record.values():
        assert "\ud800" not in str(value), (
            "surrogate leaked into captured malformed record"
        )

    normalized = writer.captured_normalized_events()
    assert len(normalized) == 1
    assert normalized[0]["provider_event_id"] == "pe-good-after-pe-surrogate"
