"""Stage 22.5 bounded private ingest runner -- outcome-priority tests.

Pins the runner's outcome priority (the order in which
``Stage22IngestResult.outcome`` is decided):

  1. ``readiness_not_ready`` (before any provider fetch).
  2. ``provider_failed`` (fetch returned ok=False).
  3. ``provider_returned_zero`` (ok=True, zero responses).
  4. ``all_malformed`` (responses non-empty, none normalized).
  5. ``ok`` (at least one event dispatched).
  6. ``transport_refused`` (no dispatch, at least one refusal).
  7. ``all_duplicates`` (no dispatch, no refusal, normalized > 0
     because every envelope was a duplicate already dispatched or
     a ledger_unavailable skip).

Also pins the negative invariant: Stage 22.5 never emits
``max_attempts_exhausted`` and rejects
``max_provider_attempts != 1`` with ``Stage22RunnerError``.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest
from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_NEW,
    INGEST_OUTCOME_ALL_DUPLICATES,
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_MAX_ATTEMPTS_EXHAUSTED,
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_PROVIDER_FAILED,
    INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
    INGEST_OUTCOME_READINESS_NOT_READY,
    INGEST_OUTCOME_TRANSPORT_REFUSED,
    MALFORMED_REASON_SHAPE_ERROR,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_TIMEOUT,
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_TIMEOUT,
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
) -> NormalizedLiveEvent:
    return NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name="stage21_fake_provider",
        source_kind="stage21_fake_source",
        chain=_CHAIN,
        mint="mint_aaa",
        event_type="fake_swap",
        observed_at_utc="2026-05-19T00:00:00Z",
        slot=100,
        signature="sig",
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


def _failed_fetch() -> ProviderFetchOutcome:
    return ProviderFetchOutcome(
        ok=False,
        responses=(),
        status_class=STATUS_CLASS_TIMEOUT,
        upstream_error_type=UPSTREAM_ERROR_TYPE_TIMEOUT,
        provider_attempt_index=0,
    )


def _ready() -> bool:
    return True


def _not_ready() -> bool:
    return False


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


class _AlwaysRefused:
    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        return Stage22DispatchOutcome(
            dispatched=False, rejection_reason="r"
        )


class _NeverCalled:
    def dispatch(self, *, envelope):  # type: ignore[no-untyped-def]
        raise AssertionError("transport must not be called")


class _ScriptedLedger:
    def __init__(self, outcomes: list[str]) -> None:
        self._outcomes = list(outcomes)
        self.marked: list[IngestEventKey] = []

    def check_and_record(
        self,
        *,
        key: IngestEventKey,
    ) -> DedupeOutcome:
        return DedupeOutcome(outcome=self._outcomes.pop(0), ingest_key=key)

    def mark_dispatched(
        self,
        *,
        key: IngestEventKey,
    ) -> None:
        self.marked.append(key)


def _run(
    *,
    fetch_outcome_fn,
    decode_event_fn,
    raw_capture_writer=None,
    dedupe_ledger=None,
    private_transport=None,
    readiness_check_fn=_ready,
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
        classify_decode_error_fn=_classify_shape,
        raw_capture_writer=(
            raw_capture_writer or InMemoryRawCaptureWriter()
        ),
        dedupe_ledger=dedupe_ledger or InMemoryDedupeLedger(),
        private_transport=private_transport or _AlwaysDispatched(),
        max_provider_attempts=1,
    )


# ---------------------------------------------------------------------------
# Individual outcomes
# ---------------------------------------------------------------------------


def test_outcome_ok_when_at_least_one_event_dispatched():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=({"marker": "a"},)
        ),
        decode_event_fn=decoder,
    )
    assert result.outcome == INGEST_OUTCOME_OK


def test_outcome_readiness_not_ready_when_gate_returns_false():
    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalled(),
        readiness_check_fn=_not_ready,
    )
    assert result.outcome == INGEST_OUTCOME_READINESS_NOT_READY


def test_outcome_provider_failed_when_fetch_outcome_ok_false():
    result = _run(
        fetch_outcome_fn=lambda _i: _failed_fetch(),
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_PROVIDER_FAILED


def test_outcome_provider_returned_zero_when_responses_is_empty():
    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(responses=()),
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_PROVIDER_RETURNED_ZERO


def test_outcome_all_malformed_when_every_response_is_bad():
    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=(
                {"marker": "missing-1"},
                {"marker": "missing-2"},
            )
        ),
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED


def test_outcome_all_duplicates_when_every_event_is_already_dispatched():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedLedger(
        [DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED]
    )

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=({"marker": "a"},)
        ),
        decode_event_fn=decoder,
        dedupe_ledger=ledger,
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_ALL_DUPLICATES


def test_outcome_transport_refused_when_no_dispatch_and_at_least_one_refusal():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedLedger([DEDUPE_OUTCOME_NEW])

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=({"marker": "a"},)
        ),
        decode_event_fn=decoder,
        dedupe_ledger=ledger,
        private_transport=_AlwaysRefused(),
    )
    assert result.outcome == INGEST_OUTCOME_TRANSPORT_REFUSED


# ---------------------------------------------------------------------------
# Stage 22.5 does NOT emit max_attempts_exhausted
# ---------------------------------------------------------------------------


def test_max_attempts_exhausted_is_locked_constant_but_runner_never_emits_it():
    """The constant exists (Stage 22.1 locked the eight-token
    set), but the Stage 22.5 runner never emits it because
    ``max_provider_attempts`` is pinned to ``1``.
    """
    assert INGEST_OUTCOME_MAX_ATTEMPTS_EXHAUSTED == "max_attempts_exhausted"


def test_runner_rejects_max_provider_attempts_above_one_with_runner_error():
    """The 22.5 runner pins ``max_provider_attempts == 1``; any
    other value is a runner-input contract violation.
    """
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
            raw_capture_writer=InMemoryRawCaptureWriter(),
            dedupe_ledger=InMemoryDedupeLedger(),
            private_transport=_AlwaysDispatched(),
            max_provider_attempts=3,
        )


# ---------------------------------------------------------------------------
# Outcome priority: readiness beats every later check
# ---------------------------------------------------------------------------


def test_readiness_not_ready_beats_provider_failed():
    """If the readiness gate fails, the runner must NOT call the
    fetch callable and must return ``readiness_not_ready`` even
    though the (un-called) fetch would have failed.
    """
    fetch_calls: list[int] = []

    def _fetch(attempt: int) -> ProviderFetchOutcome:
        fetch_calls.append(attempt)
        return _failed_fetch()

    result = _run(
        fetch_outcome_fn=_fetch,
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalled(),
        readiness_check_fn=_not_ready,
    )
    assert result.outcome == INGEST_OUTCOME_READINESS_NOT_READY
    assert fetch_calls == []


# ---------------------------------------------------------------------------
# Outcome priority: ok beats transport_refused
# ---------------------------------------------------------------------------


def test_ok_beats_transport_refused_when_at_least_one_event_dispatched():
    event_a = _make_event(
        event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa",
        raw_event_hash="a" * 64,
    )
    event_b = _make_event(
        event_id="evt_bbbbbbbbbbbbbbbbbbbbbbbb",
        raw_event_hash="b" * 64,
        provider_event_id="prov-b",
    )
    decoder = _decoder_from_marker({"a": event_a, "b": event_b})
    ledger = _ScriptedLedger([DEDUPE_OUTCOME_NEW, DEDUPE_OUTCOME_NEW])

    class _MixedTransport:
        def __init__(self) -> None:
            self._next: list[Stage22DispatchOutcome] = [
                Stage22DispatchOutcome(
                    dispatched=True, rejection_reason=""
                ),
                Stage22DispatchOutcome(
                    dispatched=False, rejection_reason="r"
                ),
            ]
            self.calls: list[IngestEventEnvelope] = []

        def dispatch(
            self,
            *,
            envelope: IngestEventEnvelope,
        ) -> Stage22DispatchOutcome:
            self.calls.append(envelope)
            return self._next.pop(0)

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=(
                {"marker": "a"},
                {"marker": "b"},
            )
        ),
        decode_event_fn=decoder,
        dedupe_ledger=ledger,
        private_transport=_MixedTransport(),
    )
    # One dispatched + one refused -> outcome is ``ok``, NOT
    # ``transport_refused``.
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 1


# ---------------------------------------------------------------------------
# all_malformed beats all_duplicates priority
# ---------------------------------------------------------------------------


def test_all_malformed_beats_all_duplicates_when_no_event_normalized():
    """If zero events are normalized but responses were received,
    the outcome is ``all_malformed`` -- not ``all_duplicates``.
    The dedupe ledger is never even consulted.
    """
    ledger = _ScriptedLedger([])  # never called

    result = _run(
        fetch_outcome_fn=lambda _i: _ok_fetch(
            responses=({"marker": "missing"},)
        ),
        decode_event_fn=_decoder_from_marker({}),
        dedupe_ledger=ledger,
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_ALL_MALFORMED


# ---------------------------------------------------------------------------
# Outcome priority: provider_failed beats provider_returned_zero
# ---------------------------------------------------------------------------


def test_provider_failed_beats_provider_returned_zero():
    """Both shapes carry zero events; ``provider_failed`` wins
    because the fetch itself failed.
    """
    result = _run(
        fetch_outcome_fn=lambda _i: _failed_fetch(),
        decode_event_fn=_decoder_from_marker({}),
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_PROVIDER_FAILED
    assert result.outcome != INGEST_OUTCOME_PROVIDER_RETURNED_ZERO
