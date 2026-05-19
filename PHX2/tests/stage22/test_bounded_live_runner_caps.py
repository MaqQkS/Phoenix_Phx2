"""Stage 22.5 bounded private ingest runner -- cap and validation tests.

Pins the bounded behaviour:

  * ``max_events`` truncates the fetch response BEFORE the
    Stage 22.4 helper runs (so ``events_received`` reflects only
    events actually processed).
  * ``max_events`` None means no truncation.
  * ``max_events <= 0`` raises ``Stage22RunnerError``.
  * ``max_events`` rejects ``bool`` (strict int rule).
  * ``max_dispatches`` counts successful dispatches only.
  * Refused dispatches do not consume ``max_dispatches``.
  * ``max_dispatches <= 0`` raises ``Stage22RunnerError``.
  * ``stop_after_first_dispatch`` breaks after first successful
    dispatch but NOT after a refused dispatch.
  * ``max_provider_attempts != 1`` raises ``Stage22RunnerError``.
  * Missing / empty / None core arguments raise
    ``Stage22RunnerError``.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest
from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_NEW,
    INGEST_OUTCOME_OK,
    MALFORMED_REASON_SHAPE_ERROR,
    STATUS_CLASS_SUCCESS,
    UPSTREAM_ERROR_TYPE_NONE,
)
from PHX2.stage22.dedupe_ledger import InMemoryDedupeLedger
from PHX2.stage22.errors import Stage22RunnerError
from PHX2.stage22.ingest_contracts import (
    DedupeOutcome,
    IngestEventEnvelope,
    IngestEventKey,
    NormalizedLiveEvent,
    ProviderFetchOutcome,
    Stage22DispatchOutcome,
)
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


_CHAIN: str = "solana_mainnet"
_PROVIDER_ID: str = "helius"


def _make_event(
    *,
    event_id: str,
    provider_event_id: str = "prov",
    raw_event_hash: str = "0" * 64,
    mint: str = "mint_aaa",
    slot: int = 100,
    signature: str = "sig",
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


def _decoder_from_marker(mapping: dict[str, NormalizedLiveEvent]):
    def _decode(raw: Mapping[str, object]) -> NormalizedLiveEvent:
        marker = raw.get("marker")
        if not isinstance(marker, str) or marker not in mapping:
            raise AssertionError("test fixture: unexpected payload")
        return mapping[marker]
    return _decode


def _classify_shape(_exc: BaseException) -> str:
    return MALFORMED_REASON_SHAPE_ERROR


def _ok_fetch(
    *,
    responses: tuple[Mapping[str, object], ...],
) -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=True,
        responses=responses,
        status_class=STATUS_CLASS_SUCCESS,
        upstream_error_type=UPSTREAM_ERROR_TYPE_NONE,
        provider_attempt_index=0,
    )


def _ready() -> bool:
    return True


class _AlwaysDispatched:
    def __init__(self) -> None:
        self.calls: list[IngestEventEnvelope] = []

    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        self.calls.append(envelope)
        return Stage22DispatchOutcome(dispatched=True, rejection_reason="")


class _ScriptedTransport:
    def __init__(self, outcomes: list[Stage22DispatchOutcome]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[IngestEventEnvelope] = []

    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        self.calls.append(envelope)
        if not self._outcomes:
            raise AssertionError("ran out of scripted outcomes")
        return self._outcomes.pop(0)


_BASE_KWARGS = {
    "provider_id": _PROVIDER_ID,
    "chain": _CHAIN,
    "observed_at_utc": "2026-05-19T00:00:00Z",
    "received_at_utc": "2026-05-19T00:00:01Z",
    "failed_at_utc": "2026-05-19T00:00:02Z",
    "readiness_check_fn": _ready,
    "classify_decode_error_fn": _classify_shape,
}


def _run(
    *,
    fetch_outcome_fn,
    decode_event_fn,
    raw_capture_writer=None,
    dedupe_ledger=None,
    private_transport=None,
    max_provider_attempts: int = 1,
    max_events=None,
    max_dispatches=None,
    stop_after_first_dispatch: bool = False,
):
    return run_bounded_private_ingest(
        **_BASE_KWARGS,
        fetch_outcome_fn=fetch_outcome_fn,
        decode_event_fn=decode_event_fn,
        raw_capture_writer=(
            raw_capture_writer or InMemoryRawCaptureWriter()
        ),
        dedupe_ledger=dedupe_ledger or InMemoryDedupeLedger(),
        private_transport=private_transport or _AlwaysDispatched(),
        max_provider_attempts=max_provider_attempts,
        max_events=max_events,
        max_dispatches=max_dispatches,
        stop_after_first_dispatch=stop_after_first_dispatch,
    )


# ---------------------------------------------------------------------------
# max_events
# ---------------------------------------------------------------------------


def test_max_events_truncates_responses_before_helper_runs():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(5)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(5)}
    )
    transport = _AlwaysDispatched()

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(5)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        max_events=2,
    )
    # events_received is the post-truncation count.
    assert result.events_received == 2
    assert result.events_normalized == 2
    assert result.events_dispatched == 2
    # The transport sees only the first two truncated events.
    assert [c.event for c in transport.calls] == events[:2]


def test_max_events_none_does_not_truncate():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(3)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(3)}
    )
    transport = _AlwaysDispatched()

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(3)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        max_events=None,
    )
    assert result.events_received == 3
    assert result.events_dispatched == 3


def test_max_events_zero_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_events=0,
        )


def test_max_events_negative_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_events=-1,
        )


def test_max_events_bool_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_events=True,
        )


def test_max_events_equal_to_response_count_does_not_truncate():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(2)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(2)}
    )
    transport = _AlwaysDispatched()

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(2)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        max_events=2,
    )
    assert result.events_received == 2
    assert result.events_dispatched == 2


# ---------------------------------------------------------------------------
# max_dispatches
# ---------------------------------------------------------------------------


def test_max_dispatches_counts_successful_dispatches_only():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(4)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(4)}
    )
    transport = _AlwaysDispatched()

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(4)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        max_dispatches=2,
    )
    assert result.events_dispatched == 2
    # Only the first two envelopes reached the transport.
    assert [c.event for c in transport.calls] == events[:2]


def test_max_dispatches_does_not_count_refused_dispatches_against_cap():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(3)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(3)}
    )
    # The middle envelope is refused; the cap is 1 so only one
    # *successful* dispatch is allowed.
    transport = _ScriptedTransport(
        [
            Stage22DispatchOutcome(dispatched=False, rejection_reason="r"),
            Stage22DispatchOutcome(dispatched=True, rejection_reason=""),
            Stage22DispatchOutcome(dispatched=True, rejection_reason=""),
        ]
    )

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(3)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        max_dispatches=1,
    )
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 1
    # The third envelope must NOT have been dispatched because
    # the cap was met after envelope 1 succeeded.
    assert len(transport.calls) == 2


def test_max_dispatches_zero_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_dispatches=0,
        )


def test_max_dispatches_negative_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_dispatches=-3,
        )


def test_max_dispatches_bool_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_dispatches=False,
        )


# ---------------------------------------------------------------------------
# stop_after_first_dispatch
# ---------------------------------------------------------------------------


def test_stop_after_first_dispatch_breaks_after_first_success():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(3)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(3)}
    )
    transport = _AlwaysDispatched()

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(3)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        stop_after_first_dispatch=True,
    )
    assert result.events_dispatched == 1
    assert len(transport.calls) == 1


def test_stop_after_first_dispatch_does_not_break_after_refusal():
    events = [
        _make_event(
            event_id=f"evt_{idx:024d}",
            raw_event_hash=str(idx) * 64,
            provider_event_id=f"prov-{idx}",
        )
        for idx in range(3)
    ]
    decoder = _decoder_from_marker(
        {str(idx): events[idx] for idx in range(3)}
    )
    # First two refused, third dispatched.
    transport = _ScriptedTransport(
        [
            Stage22DispatchOutcome(dispatched=False, rejection_reason="r"),
            Stage22DispatchOutcome(dispatched=False, rejection_reason="r"),
            Stage22DispatchOutcome(dispatched=True, rejection_reason=""),
        ]
    )

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=tuple({"marker": str(idx)} for idx in range(3)),
        ),
        decode_event_fn=decoder,
        private_transport=transport,
        stop_after_first_dispatch=True,
    )
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 2
    # All three envelopes were attempted.
    assert len(transport.calls) == 3


# ---------------------------------------------------------------------------
# max_provider_attempts
# ---------------------------------------------------------------------------


def test_max_provider_attempts_zero_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_provider_attempts=0,
        )


def test_max_provider_attempts_two_raises_runner_error_in_22_5():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_provider_attempts=2,
        )


def test_max_provider_attempts_bool_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        _run(
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            max_provider_attempts=True,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Missing / None argument validation
# ---------------------------------------------------------------------------


def test_none_readiness_check_fn_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        run_bounded_private_ingest(
            provider_id=_PROVIDER_ID,
            chain=_CHAIN,
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            readiness_check_fn=None,  # type: ignore[arg-type]
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            classify_decode_error_fn=_classify_shape,
            raw_capture_writer=InMemoryRawCaptureWriter(),
            dedupe_ledger=InMemoryDedupeLedger(),
            private_transport=_AlwaysDispatched(),
        )


def test_none_raw_capture_writer_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        run_bounded_private_ingest(
            provider_id=_PROVIDER_ID,
            chain=_CHAIN,
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            readiness_check_fn=_ready,
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            classify_decode_error_fn=_classify_shape,
            raw_capture_writer=None,  # type: ignore[arg-type]
            dedupe_ledger=InMemoryDedupeLedger(),
            private_transport=_AlwaysDispatched(),
        )


def test_empty_provider_id_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        run_bounded_private_ingest(
            provider_id="",
            chain=_CHAIN,
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            readiness_check_fn=_ready,
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            classify_decode_error_fn=_classify_shape,
            raw_capture_writer=InMemoryRawCaptureWriter(),
            dedupe_ledger=InMemoryDedupeLedger(),
            private_transport=_AlwaysDispatched(),
        )


def test_empty_chain_raises_runner_error():
    with pytest.raises(Stage22RunnerError):
        run_bounded_private_ingest(
            provider_id=_PROVIDER_ID,
            chain="",
            observed_at_utc="2026-05-19T00:00:00Z",
            received_at_utc="2026-05-19T00:00:01Z",
            failed_at_utc="2026-05-19T00:00:02Z",
            readiness_check_fn=_ready,
            fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
            decode_event_fn=_decoder_from_marker({}),
            classify_decode_error_fn=_classify_shape,
            raw_capture_writer=InMemoryRawCaptureWriter(),
            dedupe_ledger=InMemoryDedupeLedger(),
            private_transport=_AlwaysDispatched(),
        )
