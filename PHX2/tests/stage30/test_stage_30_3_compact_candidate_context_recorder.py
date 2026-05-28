"""Stage 30.3 compact candidate context recorder tests.

Pure offline tests over the recorder construction contract, the
single-/multi-call ordering, the duck-typed projection of the
inner record, and the migration-timestamp-to-age derivation.

Discipline: no env reads, no network, no provider calls, no
operator-channel send. Stdlib + pytest only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from PHX2.stage30.stage30_3_compact_candidate_context_recorder import (
    Stage30_3CompactCandidateContextRecorder,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    Stage30_3CompactRuntimeError,
    Stage30_3RecordedCandidateContext,
)


# ---------------------------------------------------------------------------
# Fake clock + fake inner assembler
# ---------------------------------------------------------------------------


class _SequentialFakeClock:
    """Returns successive ISO-8601 UTC strings from a fixed list.

    Raises ``AssertionError`` if asked beyond the list. Used to
    pin the recorder's monotonic clock semantics.
    """

    def __init__(self, *, stamps: List[str]) -> None:
        self._stamps = list(stamps)
        self._index = 0

    def now_utc_iso(self) -> str:
        if self._index >= len(self._stamps):
            raise AssertionError(
                "clock.now_utc_iso() called more times than "
                "stamps supplied"
            )
        value = self._stamps[self._index]
        self._index += 1
        return value


class _RecordingFakeAssembler:
    """Inner assembler that returns scripted records and records
    every received candidate_id for assertions.
    """

    def __init__(self, *, scripted_records: List[Any]) -> None:
        self._scripted = list(scripted_records)
        self._index = 0
        self.received_candidate_ids: List[str] = []
        self.received_events: List[Any] = []

    def assemble(self, normalized_event: object, *, candidate_id: str) -> object:
        self.received_events.append(normalized_event)
        self.received_candidate_ids.append(candidate_id)
        record = self._scripted[self._index]
        self._index += 1
        return record


class _RaisingFakeAssembler:
    """Inner assembler that always raises a scripted exception."""

    def __init__(self, *, exc: BaseException) -> None:
        self._exc = exc
        self.calls: int = 0

    def assemble(self, normalized_event: object, *, candidate_id: str) -> object:
        self.calls += 1
        raise self._exc


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_rejects_inner_assembler_without_assemble() -> None:
    bad_inner = SimpleNamespace()  # no assemble attr
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactCandidateContextRecorder(
            inner_assembler=bad_inner, clock=clock
        )
    assert excinfo.value.reason == "INNER_ASSEMBLER_INVALID"


def test_construction_rejects_clock_without_now_utc_iso() -> None:
    inner = _RecordingFakeAssembler(scripted_records=[])
    bad_clock = SimpleNamespace()  # no now_utc_iso attr
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactCandidateContextRecorder(
            inner_assembler=inner, clock=bad_clock
        )
    assert excinfo.value.reason == "CLOCK_INVALID"


def test_construction_rejects_assemble_non_callable() -> None:
    bad_inner = SimpleNamespace(assemble="not callable")
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactCandidateContextRecorder(
            inner_assembler=bad_inner, clock=clock
        )
    assert excinfo.value.reason == "INNER_ASSEMBLER_INVALID"


def test_construction_rejects_clock_now_non_callable() -> None:
    inner = _RecordingFakeAssembler(scripted_records=[])
    bad_clock = SimpleNamespace(now_utc_iso="not callable")
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactCandidateContextRecorder(
            inner_assembler=inner, clock=bad_clock
        )
    assert excinfo.value.reason == "CLOCK_INVALID"


def test_recorded_entries_starts_empty() -> None:
    inner = _RecordingFakeAssembler(scripted_records=[])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    assert recorder.recorded_entries == ()
    assert isinstance(recorder.recorded_entries, tuple)


# ---------------------------------------------------------------------------
# Single + multi-call assemble
# ---------------------------------------------------------------------------


def test_single_assemble_records_exactly_one_entry() -> None:
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintAAA"),
        measurement_context=None,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    returned = recorder.assemble("event-1", candidate_id="cand-001")
    assert returned is inner_record
    assert len(recorder.recorded_entries) == 1
    entry = recorder.recorded_entries[0]
    assert isinstance(entry, Stage30_3RecordedCandidateContext)
    assert entry.candidate_id == "cand-001"
    assert entry.mint == "MintAAA"
    assert entry.recorded_at_utc == "2026-05-27T00:00:00Z"


def test_three_assemble_calls_produce_three_entries_in_order() -> None:
    records = [
        SimpleNamespace(
            ingest_output=SimpleNamespace(token_mint=f"Mint{i}"),
            measurement_context=None,
            rendered_ping=None,
        )
        for i in range(3)
    ]
    inner = _RecordingFakeAssembler(scripted_records=records)
    stamps = [
        "2026-05-27T00:00:00Z",
        "2026-05-27T00:00:01Z",
        "2026-05-27T00:00:02Z",
    ]
    clock = _SequentialFakeClock(stamps=stamps)
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    for i in range(3):
        recorder.assemble(f"event-{i}", candidate_id=f"cand-{i}")
    entries = recorder.recorded_entries
    assert len(entries) == 3
    for i, entry in enumerate(entries):
        assert entry.candidate_id == f"cand-{i}"
        assert entry.mint == f"Mint{i}"
        assert entry.recorded_at_utc == stamps[i]
    # Monotonic ordering preserved.
    assert (
        entries[0].recorded_at_utc
        < entries[1].recorded_at_utc
        < entries[2].recorded_at_utc
    )


# ---------------------------------------------------------------------------
# Inner-assembler exception propagation
# ---------------------------------------------------------------------------


def test_inner_assembler_exception_propagates() -> None:
    inner = _RaisingFakeAssembler(exc=RuntimeError("inner exploded"))
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    with pytest.raises(RuntimeError) as excinfo:
        recorder.assemble("event-1", candidate_id="cand-001")
    assert "inner exploded" in str(excinfo.value)
    assert recorder.recorded_entries == ()


# ---------------------------------------------------------------------------
# Inner record returned verbatim (identity check)
# ---------------------------------------------------------------------------


def test_inner_record_returned_verbatim() -> None:
    sentinel = object()  # arbitrary opaque object
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintBBB"),
        measurement_context=None,
        rendered_ping=None,
        sentinel=sentinel,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    returned = recorder.assemble("event-1", candidate_id="cand-001")
    assert returned is inner_record
    assert returned.sentinel is sentinel


# ---------------------------------------------------------------------------
# measurement_context=None -> ath/migration/age all None
# ---------------------------------------------------------------------------


def test_measurement_context_none_yields_all_nones() -> None:
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintCCC"),
        measurement_context=None,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.ath_record is None
    assert entry.migration_record is None
    assert entry.age_since_migration_seconds is None
    assert entry.price_status is None


# ---------------------------------------------------------------------------
# Age derivation from migration timestamp + clock
# ---------------------------------------------------------------------------


def test_age_seconds_derived_from_migration_timestamp() -> None:
    migration = SimpleNamespace(
        migration_timestamp_utc="2026-05-27T00:00:00Z",
    )
    measurement = SimpleNamespace(
        ath_context=SimpleNamespace(),
        migration_context=migration,
    )
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintDDD"),
        measurement_context=measurement,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:30Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.age_since_migration_seconds == 30


def test_age_seconds_floors_negative_skew_at_zero() -> None:
    migration = SimpleNamespace(
        migration_timestamp_utc="2026-05-27T00:00:30Z",
    )
    measurement = SimpleNamespace(
        ath_context=SimpleNamespace(),
        migration_context=migration,
    )
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintEEE"),
        measurement_context=measurement,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    # Clock is BEFORE migration ts -> negative delta -> floor to 0.
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.age_since_migration_seconds == 0


def test_age_seconds_none_when_migration_timestamp_missing() -> None:
    migration = SimpleNamespace(
        migration_timestamp_utc=None,
    )
    measurement = SimpleNamespace(
        ath_context=SimpleNamespace(),
        migration_context=migration,
    )
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintFFF"),
        measurement_context=measurement,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.age_since_migration_seconds is None


def test_age_seconds_none_when_migration_timestamp_unparseable() -> None:
    migration = SimpleNamespace(
        migration_timestamp_utc="not-an-iso-string",
    )
    measurement = SimpleNamespace(
        ath_context=SimpleNamespace(),
        migration_context=migration,
    )
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintGGG"),
        measurement_context=measurement,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.age_since_migration_seconds is None


# ---------------------------------------------------------------------------
# price_status extraction
# ---------------------------------------------------------------------------


def test_price_status_extracted_from_rendered_ping() -> None:
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintHHH"),
        measurement_context=None,
        rendered_ping=SimpleNamespace(price_status="STALE"),
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.price_status == "STALE"


def test_price_status_non_string_falls_back_to_none() -> None:
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint="MintIII"),
        measurement_context=None,
        rendered_ping=SimpleNamespace(price_status=123),
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.price_status is None


# ---------------------------------------------------------------------------
# mint non-string falls back to None
# ---------------------------------------------------------------------------


def test_mint_non_string_falls_back_to_none() -> None:
    inner_record = SimpleNamespace(
        ingest_output=SimpleNamespace(token_mint=12345),
        measurement_context=None,
        rendered_ping=None,
    )
    inner = _RecordingFakeAssembler(scripted_records=[inner_record])
    clock = _SequentialFakeClock(stamps=["2026-05-27T00:00:00Z"])
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner, clock=clock
    )
    recorder.assemble("event-1", candidate_id="cand-001")
    entry = recorder.recorded_entries[0]
    assert entry.mint is None
