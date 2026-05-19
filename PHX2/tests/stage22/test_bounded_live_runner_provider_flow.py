"""Stage 22.5 bounded private ingest runner -- provider-flow tests.

Covers the readiness gate, the provider-fetch path, the
empty-response path, the all-malformed path, the mixed
good+malformed path, and the all-good path. Also pins the
capture-failure / fetch-callable-raising propagation rules.

Every test uses in-memory fakes for the provider fetch /
decoder / classifier / capture writer / dedupe ledger /
private transport collaborators. No Stage 21 module is
imported.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest
from PHX2.stage22.constants import (
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_PROVIDER_FAILED,
    INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
    INGEST_OUTCOME_READINESS_NOT_READY,
    MALFORMED_REASON_SHAPE_ERROR,
    PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_TIMEOUT,
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_TIMEOUT,
)
from PHX2.stage22.dedupe_ledger import InMemoryDedupeLedger
from PHX2.stage22.errors import Stage22CaptureContractError
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    NormalizedLiveEvent,
    ProviderFetchOutcome,
    Stage22DispatchOutcome,
)
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


# ---------------------------------------------------------------------------
# Test fixtures and doubles
# ---------------------------------------------------------------------------


_CHAIN: str = "solana_mainnet"
_PROVIDER_ID: str = "helius"


class _FakeDecodeError(Exception):
    """Marker exception raised by the fake decoder."""


def _make_event(
    *,
    event_id: str,
    provider_event_id: str = "prov-001",
    raw_event_hash: str = "0" * 64,
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


def _decoder_from_marker(
    mapping: dict[str, NormalizedLiveEvent],
):
    def _decode(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        marker = raw.get("marker")
        if not isinstance(marker, str) or marker not in mapping:
            raise _FakeDecodeError("missing or unknown marker")
        return mapping[marker]
    return _decode


def _classify_shape(_exc: BaseException) -> str:
    return MALFORMED_REASON_SHAPE_ERROR


class _RecordingTransport:
    """Stage22PrivateTransport fake that always accepts."""

    def __init__(self) -> None:
        self.calls: list[IngestEventEnvelope] = []

    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        self.calls.append(envelope)
        return Stage22DispatchOutcome(dispatched=True, rejection_reason="")


class _NeverCalledTransport:
    """Stage22PrivateTransport fake that explodes on call."""

    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        raise AssertionError(
            "transport.dispatch must not be called in this scenario"
        )


def _ok_fetch(
    *,
    responses: tuple[Mapping[str, object], ...],
    attempt_index: int = 0,
) -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=True,
        responses=responses,
        status_class=STATUS_CLASS_SUCCESS,
        upstream_error_type=UPSTREAM_ERROR_TYPE_NONE,
        provider_attempt_index=attempt_index,
    )


def _failed_fetch(
    *,
    attempt_index: int = 0,
) -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=False,
        responses=(),
        status_class=STATUS_CLASS_TIMEOUT,
        upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
        provider_attempt_index=attempt_index,
    )


def _ready() -> bool:
    return True


def _not_ready() -> bool:
    return False


def _run(
    *,
    fetch_outcome_fn,
    decode_event_fn,
    classify_decode_error_fn=_classify_shape,
    raw_capture_writer=None,
    dedupe_ledger=None,
    private_transport=None,
    readiness_check_fn=_ready,
    max_events=None,
    max_dispatches=None,
    stop_after_first_dispatch=False,
):
    return run_bounded_private_ingest(
        provider_id=_PROVIDER_ID,
        chain=_CHAIN,
        observed_at_utc="2026-05-19T00:00:00Z",
        received_at_utc="2026-05-19T00:00:01Z",
        failed_at_utc="2026-05-19T00:00:02Z",
        readiness_check_fn=readiness_check_fn,
        fetch_outcome_fn=fetch_outcome_fn,
        decode_event_fn=decode_event_fn,
        classify_decode_error_fn=classify_decode_error_fn,
        raw_capture_writer=(
            raw_capture_writer or InMemoryRawCaptureWriter()
        ),
        dedupe_ledger=dedupe_ledger or InMemoryDedupeLedger(),
        private_transport=private_transport or _RecordingTransport(),
        max_provider_attempts=1,
        max_events=max_events,
        max_dispatches=max_dispatches,
        stop_after_first_dispatch=stop_after_first_dispatch,
    )


# ---------------------------------------------------------------------------
# Readiness gate
# ---------------------------------------------------------------------------


def test_readiness_not_ready_returns_before_provider_fetch():
    fetch_calls: list[int] = []

    def _fetch(attempt: int) -> ProviderFetchOutcome:
        fetch_calls.append(attempt)
        return _ok_fetch(responses=())

    result = _run(
        fetch_outcome_fn=_fetch,
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalledTransport(),
        readiness_check_fn=_not_ready,
    )
    assert result.outcome == INGEST_OUTCOME_READINESS_NOT_READY
    assert fetch_calls == []
    assert result.events_received == 0
    assert result.events_normalized == 0
    assert result.events_malformed == 0
    assert result.events_new == 0
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 0
    assert result.provider_attempts == 0
    assert result.last_failure_label == ""
    assert result.provider_id == _PROVIDER_ID


# ---------------------------------------------------------------------------
# Provider failure path
# ---------------------------------------------------------------------------


def test_provider_failed_outcome_zeroes_event_counters_and_records_label():
    transport = _NeverCalledTransport()
    writer = InMemoryRawCaptureWriter()

    result = _run(
        fetch_outcome_fn=lambda attempt: _failed_fetch(
            attempt_index=attempt
        ),
        decode_event_fn=_decoder_from_marker({}),
        raw_capture_writer=writer,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_PROVIDER_FAILED
    assert result.events_received == 0
    assert result.events_normalized == 0
    assert result.events_malformed == 0
    assert result.events_new == 0
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 0
    assert result.provider_attempts == 1
    assert (
        result.last_failure_label == PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT
    )
    assert result.provider_id == _PROVIDER_ID
    # The Stage 22.4 batch helper should have captured one
    # ProviderFailureRecord; the runner should not have dispatched.
    failures = writer.captured_provider_failures()
    assert len(failures) == 1
    assert writer.captured_normalized_events() == ()


def test_fetch_outcome_fn_raising_propagates_unchanged():
    class _Boom(Exception):
        pass

    def _boom(_attempt: int) -> ProviderFetchOutcome:
        raise _Boom("fetch failure")

    with pytest.raises(_Boom):
        _run(
            fetch_outcome_fn=_boom,
            decode_event_fn=_decoder_from_marker({}),
            private_transport=_NeverCalledTransport(),
        )


# ---------------------------------------------------------------------------
# Provider returned zero
# ---------------------------------------------------------------------------


def test_provider_returned_zero_outcome_zeroes_dispatch_counters():
    writer = InMemoryRawCaptureWriter()
    result = _run(
        fetch_outcome_fn=lambda attempt: _ok_fetch(
            responses=(),
            attempt_index=attempt,
        ),
        decode_event_fn=_decoder_from_marker({}),
        raw_capture_writer=writer,
        private_transport=_NeverCalledTransport(),
    )
    assert result.outcome == INGEST_OUTCOME_PROVIDER_RETURNED_ZERO
    assert result.events_received == 0
    assert result.events_normalized == 0
    assert result.events_malformed == 0
    assert result.events_new == 0
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 0
    assert result.provider_attempts == 1
    assert result.last_failure_label == ""
    assert result.provider_id == _PROVIDER_ID
    assert writer.captured_normalized_events() == ()


# ---------------------------------------------------------------------------
# all_malformed
# ---------------------------------------------------------------------------


def test_all_malformed_path_returns_all_malformed_outcome():
    writer = InMemoryRawCaptureWriter()
    result = _run(
        fetch_outcome_fn=lambda attempt: _ok_fetch(
            responses=(
                {"marker": "missing-1"},
                {"marker": "missing-2"},
            ),
            attempt_index=attempt,
        ),
        decode_event_fn=_decoder_from_marker({}),
        raw_capture_writer=writer,
        private_transport=_NeverCalledTransport(),
    )
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED
    assert result.events_received == 2
    assert result.events_normalized == 0
    assert result.events_malformed == 2
    assert result.events_new == 0
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 0
    assert result.provider_attempts == 1
    assert result.last_failure_label == ""
    assert len(writer.captured_malformed_events()) == 2


# ---------------------------------------------------------------------------
# Mixed good + malformed
# ---------------------------------------------------------------------------


def test_mixed_good_and_malformed_returns_ok_and_dispatches_good_only():
    good_event = _make_event(event_id="evt_good_aaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"good": good_event})
    writer = InMemoryRawCaptureWriter()
    transport = _RecordingTransport()

    result = _run(
        fetch_outcome_fn=lambda attempt: _ok_fetch(
            responses=(
                {"marker": "good"},
                {"marker": "missing"},
            ),
            attempt_index=attempt,
        ),
        decode_event_fn=decoder,
        raw_capture_writer=writer,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 2
    assert result.events_normalized == 1
    assert result.events_malformed == 1
    assert result.events_new == 1
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 0
    assert result.provider_attempts == 1
    assert result.last_failure_label == ""
    # Only the good event should reach transport.dispatch.
    assert len(transport.calls) == 1
    assert transport.calls[0].event is good_event


# ---------------------------------------------------------------------------
# All good
# ---------------------------------------------------------------------------


def test_all_good_path_returns_ok_and_dispatches_each_event():
    good_a = _make_event(
        event_id="evt_aaa_aaaaaaaaaaaaaaaaaaaa",
        raw_event_hash="a" * 64,
    )
    good_b = _make_event(
        event_id="evt_bbb_bbbbbbbbbbbbbbbbbbbb",
        raw_event_hash="b" * 64,
        provider_event_id="prov-002",
    )
    decoder = _decoder_from_marker({"a": good_a, "b": good_b})
    transport = _RecordingTransport()

    result = _run(
        fetch_outcome_fn=lambda attempt: _ok_fetch(
            responses=(
                {"marker": "a"},
                {"marker": "b"},
            ),
            attempt_index=attempt,
        ),
        decode_event_fn=decoder,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_received == 2
    assert result.events_normalized == 2
    assert result.events_malformed == 0
    assert result.events_new == 2
    assert result.events_dispatched == 2
    assert result.events_transport_refused == 0
    assert result.provider_attempts == 1
    # The transport sees events in input order.
    assert [c.event for c in transport.calls] == [good_a, good_b]


# ---------------------------------------------------------------------------
# Capture failure propagates
# ---------------------------------------------------------------------------


class _CapturePoisonWriter:
    """Capture writer that explodes on the first malformed
    capture call.
    """

    def __init__(self) -> None:
        self._inner = InMemoryRawCaptureWriter()

    def capture(self, *, envelope) -> None:  # type: ignore[no-untyped-def]
        self._inner.capture(envelope=envelope)

    def capture_malformed(self, *, record) -> None:  # type: ignore[no-untyped-def]
        raise Stage22CaptureContractError(
            "synthetic capture_malformed failure"
        )

    def capture_provider_failure(
        self, *, record
    ) -> None:  # type: ignore[no-untyped-def]
        self._inner.capture_provider_failure(record=record)


def test_capture_failure_propagates_and_does_not_return_a_result():
    transport = _NeverCalledTransport()
    with pytest.raises(Stage22CaptureContractError):
        _run(
            fetch_outcome_fn=lambda attempt: _ok_fetch(
                responses=({"marker": "missing"},),
                attempt_index=attempt,
            ),
            decode_event_fn=_decoder_from_marker({}),
            raw_capture_writer=_CapturePoisonWriter(),
            private_transport=transport,
        )
