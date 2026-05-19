"""Stage 22.5 bounded private ingest runner -- dedupe + dispatch tests.

Pins the per-envelope dedupe semantics (Stage 22.2) and the
private transport interaction:

  * ``new`` -> dispatch; mark_dispatched on success.
  * ``new`` + refused -> no mark_dispatched.
  * ``duplicate_already_dispatched`` -> no dispatch.
  * ``duplicate_not_yet_dispatched`` -> dispatch; mark on success.
  * ``duplicate_not_yet_dispatched`` + refused -> no mark.
  * ``ledger_unavailable`` -> skip; no dispatch, no refusal count.
  * mark_dispatched failure -> propagates.
  * transport.dispatch raising -> propagates.
  * events_new counts only ``new``, not
    ``duplicate_not_yet_dispatched``.
  * dispatch order follows envelope order.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest
from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
    DEDUPE_OUTCOME_NEW,
    INGEST_OUTCOME_ALL_DUPLICATES,
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_TRANSPORT_REFUSED,
    MALFORMED_REASON_SHAPE_ERROR,
    STATUS_CLASS_SUCCESS,
    UPSTREAM_ERROR_TYPE_NONE,
)
from PHX2.stage22.errors import Stage22LedgerContractError
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


# ---------------------------------------------------------------------------
# Scripted dedupe ledger
# ---------------------------------------------------------------------------


class _ScriptedDedupeLedger:
    """In-memory ledger that returns a scripted outcome sequence.

    Each ``check_and_record`` call pops the next outcome token
    from ``outcomes`` and returns a ``DedupeOutcome`` with that
    token. ``mark_dispatched`` records every key it sees.
    """

    def __init__(self, outcomes: list[str]) -> None:
        self._outcomes = list(outcomes)
        self.checked: list[IngestEventKey] = []
        self.marked: list[IngestEventKey] = []

    def check_and_record(
        self,
        *,
        key: IngestEventKey,
    ) -> DedupeOutcome:
        self.checked.append(key)
        if not self._outcomes:
            raise AssertionError(
                "test fixture: ran out of scripted outcomes"
            )
        token = self._outcomes.pop(0)
        return DedupeOutcome(outcome=token, ingest_key=key)

    def mark_dispatched(
        self,
        *,
        key: IngestEventKey,
    ) -> None:
        self.marked.append(key)


class _ScriptedTransport:
    """Stage22PrivateTransport fake that returns scripted outcomes."""

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
            raise AssertionError(
                "test fixture: ran out of scripted dispatch outcomes"
            )
        return self._outcomes.pop(0)


class _AlwaysDispatchedTransport:
    def __init__(self) -> None:
        self.calls: list[IngestEventEnvelope] = []

    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        self.calls.append(envelope)
        return Stage22DispatchOutcome(dispatched=True, rejection_reason="")


def _ready() -> bool:
    return True


def _run(
    *,
    responses,
    decoder,
    dedupe_ledger,
    private_transport,
    max_dispatches=None,
    stop_after_first_dispatch=False,
):
    return run_bounded_private_ingest(
        provider_id=_PROVIDER_ID,
        chain=_CHAIN,
        observed_at_utc="2026-05-19T00:00:00Z",
        received_at_utc="2026-05-19T00:00:01Z",
        failed_at_utc="2026-05-19T00:00:02Z",
        readiness_check_fn=_ready,
        fetch_outcome_fn=lambda _i: _ok_fetch(responses=responses),
        decode_event_fn=decoder,
        classify_decode_error_fn=_classify_shape,
        raw_capture_writer=InMemoryRawCaptureWriter(),
        dedupe_ledger=dedupe_ledger,
        private_transport=private_transport,
        max_provider_attempts=1,
        max_events=None,
        max_dispatches=max_dispatches,
        stop_after_first_dispatch=stop_after_first_dispatch,
    )


# ---------------------------------------------------------------------------
# new -> dispatch + mark_dispatched
# ---------------------------------------------------------------------------


def test_new_event_dispatches_and_marks_dispatched_on_success():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedDedupeLedger([DEDUPE_OUTCOME_NEW])
    transport = _AlwaysDispatchedTransport()

    result = _run(
        responses=({"marker": "a"},),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_new == 1
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 0
    assert len(transport.calls) == 1
    assert len(ledger.marked) == 1
    assert ledger.marked[0].event_id == event.event_id


def test_new_event_refused_does_not_mark_dispatched():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedDedupeLedger([DEDUPE_OUTCOME_NEW])
    transport = _ScriptedTransport(
        [Stage22DispatchOutcome(dispatched=False, rejection_reason="r")]
    )

    result = _run(
        responses=({"marker": "a"},),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_TRANSPORT_REFUSED
    assert result.events_new == 1
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 1
    assert ledger.marked == []


# ---------------------------------------------------------------------------
# duplicate_already_dispatched -> no dispatch
# ---------------------------------------------------------------------------


def test_duplicate_already_dispatched_skips_transport_and_mark():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedDedupeLedger(
        [DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED]
    )

    class _NeverCalled:
        def dispatch(self, *, envelope):  # type: ignore[no-untyped-def]
            raise AssertionError("transport must not be called")

    result = _run(
        responses=({"marker": "a"},),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=_NeverCalled(),
    )
    assert result.outcome == INGEST_OUTCOME_ALL_DUPLICATES
    assert result.events_new == 0
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 0
    assert ledger.marked == []


# ---------------------------------------------------------------------------
# duplicate_not_yet_dispatched -> dispatch (not counted in events_new)
# ---------------------------------------------------------------------------


def test_duplicate_not_yet_dispatched_dispatches_but_does_not_count_as_new():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedDedupeLedger(
        [DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED]
    )
    transport = _AlwaysDispatchedTransport()

    result = _run(
        responses=({"marker": "a"},),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_new == 0
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 0
    assert len(transport.calls) == 1
    assert len(ledger.marked) == 1


def test_duplicate_not_yet_dispatched_refused_does_not_mark():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedDedupeLedger(
        [DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED]
    )
    transport = _ScriptedTransport(
        [Stage22DispatchOutcome(dispatched=False, rejection_reason="r")]
    )

    result = _run(
        responses=({"marker": "a"},),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_TRANSPORT_REFUSED
    assert result.events_new == 0
    assert result.events_dispatched == 0
    assert result.events_transport_refused == 1
    assert ledger.marked == []


# ---------------------------------------------------------------------------
# ledger_unavailable -> skip
# ---------------------------------------------------------------------------


def test_ledger_unavailable_skips_dispatch_and_does_not_count_as_refusal():
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
    ledger = _ScriptedDedupeLedger(
        [DEDUPE_OUTCOME_LEDGER_UNAVAILABLE, DEDUPE_OUTCOME_NEW]
    )
    transport = _AlwaysDispatchedTransport()

    result = _run(
        responses=({"marker": "a"}, {"marker": "b"}),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=transport,
    )
    assert result.outcome == INGEST_OUTCOME_OK
    assert result.events_normalized == 2
    # `a` was skipped (ledger_unavailable), `b` was new+dispatched.
    assert result.events_new == 1
    assert result.events_dispatched == 1
    assert result.events_transport_refused == 0
    assert [c.event for c in transport.calls] == [event_b]
    assert len(ledger.marked) == 1
    assert ledger.marked[0].event_id == event_b.event_id


# ---------------------------------------------------------------------------
# mark_dispatched failure propagates
# ---------------------------------------------------------------------------


def test_mark_dispatched_failure_propagates():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})

    class _LedgerWithBadMark:
        def __init__(self) -> None:
            self.checked: list[IngestEventKey] = []

        def check_and_record(
            self, *, key: IngestEventKey
        ) -> DedupeOutcome:
            self.checked.append(key)
            return DedupeOutcome(
                outcome=DEDUPE_OUTCOME_NEW, ingest_key=key
            )

        def mark_dispatched(
            self, *, key: IngestEventKey
        ) -> None:
            raise Stage22LedgerContractError(
                "synthetic mark_dispatched failure"
            )

    ledger = _LedgerWithBadMark()
    transport = _AlwaysDispatchedTransport()

    with pytest.raises(Stage22LedgerContractError):
        _run(
            responses=({"marker": "a"},),
            decoder=decoder,
            dedupe_ledger=ledger,
            private_transport=transport,
        )


# ---------------------------------------------------------------------------
# transport.dispatch raising propagates
# ---------------------------------------------------------------------------


def test_transport_dispatch_raising_propagates():
    event = _make_event(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    decoder = _decoder_from_marker({"a": event})
    ledger = _ScriptedDedupeLedger([DEDUPE_OUTCOME_NEW])

    class _BoomTransport:
        def dispatch(self, *, envelope):  # type: ignore[no-untyped-def]
            raise RuntimeError("synthetic transport failure")

    with pytest.raises(RuntimeError):
        _run(
            responses=({"marker": "a"},),
            decoder=decoder,
            dedupe_ledger=ledger,
            private_transport=_BoomTransport(),
        )


# ---------------------------------------------------------------------------
# Dispatch order follows envelope order
# ---------------------------------------------------------------------------


def test_dispatch_order_follows_envelope_order():
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
    ledger = _ScriptedDedupeLedger([DEDUPE_OUTCOME_NEW] * 4)
    transport = _AlwaysDispatchedTransport()

    result = _run(
        responses=tuple({"marker": str(idx)} for idx in range(4)),
        decoder=decoder,
        dedupe_ledger=ledger,
        private_transport=transport,
    )
    assert result.events_dispatched == 4
    assert [c.event for c in transport.calls] == events
