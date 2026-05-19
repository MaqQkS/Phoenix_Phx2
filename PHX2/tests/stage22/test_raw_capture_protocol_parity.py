"""Stage 22.3 RawCaptureWriter Protocol parity tests.

Parameterises the shared semantic suite over both Stage 22.3
capture writer implementations (``InMemoryRawCaptureWriter`` and
``JsonlRawCaptureWriter``) so any behavioural drift between them
fails here. The Stage 22.1 ``RawCaptureWriter`` Protocol is the
contract surface both implementations satisfy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping

import pytest

from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage22.constants import (
    CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
    CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
    CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
    MALFORMED_REASON_SHAPE_ERROR,
    PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_TIMEOUT,
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_TIMEOUT,
)
from PHX2.stage22.errors import Stage22CaptureContractError
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    IngestEventKey,
    MalformedEventRecord,
    ProviderFailureRecord,
    RawCaptureWriter,
)
from PHX2.stage22.raw_capture import (
    InMemoryRawCaptureWriter,
    JsonlRawCaptureWriter,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _key(
    *,
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
) -> IngestEventKey:
    return IngestEventKey(
        provider_id="helius",
        chain="solana_mainnet",
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
    )


def _event(
    *,
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
    payload_summary: Mapping[str, object] | None = None,
    slot: int = 100,
) -> NormalizedLiveEvent:
    return NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name="stage21_fake_provider",
        source_kind="stage21_fake_source",
        chain="solana_mainnet",
        mint="mint-aaa",
        event_type="fake_swap",
        observed_at_utc="2026-05-18T00:00:00Z",
        slot=slot,
        signature="sig-aaaa",
        raw_event_hash=raw_event_hash,
        normalized_schema_version="stage21_v0_normalized_event",
        payload_summary=payload_summary if payload_summary is not None else {},
    )


def _envelope(
    *,
    event_id: str = "evt_0123456789abcdef01234567",
    payload_summary: Mapping[str, object] | None = None,
) -> IngestEventEnvelope:
    event = _event(event_id=event_id, payload_summary=payload_summary)
    key = _key(event_id=event_id)
    return IngestEventEnvelope(
        event=event,
        ingest_key=key,
        received_at_utc="2026-05-18T00:00:01Z",
        provider_attempt_index=0,
    )


def _malformed_record(
    *,
    reason: str = MALFORMED_REASON_SHAPE_ERROR,
) -> MalformedEventRecord:
    return MalformedEventRecord(
        provider_id="helius",
        provider_event_id="prov-bad",
        reason=reason,
        failed_at_utc="2026-05-18T00:00:02Z",
        raw_event_hash="b" * 64,
    )


def _provider_failure_record(
    *,
    failure_label: str = PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    status_class: str = STATUS_CLASS_TIMEOUT,
    upstream_error_type: str = UPSTREAM_ERROR_TYPE_TIMEOUT,
) -> ProviderFailureRecord:
    return ProviderFailureRecord(
        provider_id="helius",
        failure_label=failure_label,
        status_class=status_class,
        upstream_error_type=upstream_error_type,
        provider_attempt_index=0,
        observed_at_utc="2026-05-18T00:00:03Z",
    )


# ---------------------------------------------------------------------------
# Parameterised fixture
# ---------------------------------------------------------------------------


SnapshotFn = Callable[[], tuple[dict[str, object], ...]]


@pytest.fixture(params=["in_memory", "jsonl"])
def writer_and_snapshot(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> tuple[RawCaptureWriter, SnapshotFn]:
    """Build one of each Stage 22.3 capture writer implementation.

    Returns ``(writer, snapshot_fn)`` where ``snapshot_fn()``
    returns the in-memory / JSONL-decoded list of records in
    chronological order as a tuple of plain dicts. Both
    implementations structurally satisfy the Stage 22.1
    ``RawCaptureWriter`` Protocol; the return-type annotation
    pins that statically.
    """
    if request.param == "in_memory":
        writer = InMemoryRawCaptureWriter()

        def in_memory_snapshot() -> tuple[dict[str, object], ...]:
            return writer.captured_all()

        return writer, in_memory_snapshot
    p = tmp_path / "capture.jsonl"
    jsonl_writer = JsonlRawCaptureWriter(path=p)

    def jsonl_snapshot() -> tuple[dict[str, object], ...]:
        if not p.exists():
            return ()
        lines = p.read_text(encoding="utf-8").splitlines()
        return tuple(json.loads(line) for line in lines)

    return jsonl_writer, jsonl_snapshot


# ---------------------------------------------------------------------------
# Accept-path parity
# ---------------------------------------------------------------------------


def test_capture_normalized_event_accepted_by_both(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, snapshot = writer_and_snapshot
    writer.capture(envelope=_envelope())
    records = snapshot()
    assert len(records) == 1
    assert records[0]["record_type"] == CAPTURE_RECORD_TYPE_NORMALIZED_EVENT


def test_capture_malformed_accepted_by_both(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, snapshot = writer_and_snapshot
    writer.capture_malformed(record=_malformed_record())
    records = snapshot()
    assert len(records) == 1
    assert records[0]["record_type"] == CAPTURE_RECORD_TYPE_MALFORMED_EVENT


def test_capture_provider_failure_accepted_by_both(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, snapshot = writer_and_snapshot
    writer.capture_provider_failure(record=_provider_failure_record())
    records = snapshot()
    assert len(records) == 1
    assert records[0]["record_type"] == CAPTURE_RECORD_TYPE_PROVIDER_FAILURE


def test_all_three_record_families_in_one_writer(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, snapshot = writer_and_snapshot
    writer.capture(envelope=_envelope())
    writer.capture_malformed(record=_malformed_record())
    writer.capture_provider_failure(record=_provider_failure_record())
    records = snapshot()
    assert len(records) == 3
    types = [r["record_type"] for r in records]
    assert types == [
        CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
        CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
        CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
    ]


def test_safe_payload_summary_primitives_accepted_by_both(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, snapshot = writer_and_snapshot
    payload = {
        "amount": 42,
        "is_swap": True,
        "ratio": 1.5,
        "note": "ok",
        "missing": None,
    }
    writer.capture(envelope=_envelope(payload_summary=payload))
    records = snapshot()
    assert len(records) == 1
    assert records[0]["payload_summary"] == payload


# ---------------------------------------------------------------------------
# Reject-path parity
# ---------------------------------------------------------------------------


def test_both_writers_reject_bytes_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"blob": b"raw bytes"})
        )


def test_both_writers_reject_nested_dict_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"nested": {"a": 1}})
        )


def test_both_writers_reject_list_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"items": [1, 2, 3]})
        )


def test_both_writers_reject_secret_bearing_key_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"api_key": "x"})
        )


def test_both_writers_reject_malformed_reason_outside_closed_set(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    bad = _malformed_record(reason="not_a_real_reason")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_malformed(record=bad)


def test_both_writers_reject_failure_label_outside_closed_set(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    bad = _provider_failure_record(failure_label="not_a_real_label")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_both_writers_reject_status_class_success_on_provider_failure(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    bad = _provider_failure_record(status_class=STATUS_CLASS_SUCCESS)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_both_writers_reject_empty_upstream_error_type_on_provider_failure(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    bad = _provider_failure_record(
        upstream_error_type=UPSTREAM_ERROR_TYPE_NONE
    )
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_both_writers_reject_bool_for_envelope_provider_attempt_index(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    bad = _envelope()._replace(provider_attempt_index=True)  # type: ignore[arg-type]
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad)


def test_both_writers_reject_negative_event_slot(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    bad = _envelope()._replace(event=_event(slot=-5))
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad)


# ---------------------------------------------------------------------------
# Structural Protocol shape
# ---------------------------------------------------------------------------


def test_in_memory_writer_satisfies_raw_capture_writer_protocol() -> None:
    """Structural check: assignment to a Protocol-typed variable
    succeeds. The Protocol is not enforced at runtime by Python,
    but mypy / pyright will reject a mismatched shape, and this
    test pins the runtime assignment as a deliberate contract
    statement.
    """
    writer: RawCaptureWriter = InMemoryRawCaptureWriter()
    _ = writer


def test_jsonl_writer_satisfies_raw_capture_writer_protocol(
    tmp_path: Path,
) -> None:
    writer: RawCaptureWriter = JsonlRawCaptureWriter(
        path=tmp_path / "capture.jsonl"
    )
    _ = writer


def test_both_writers_have_capture_method() -> None:
    assert hasattr(InMemoryRawCaptureWriter, "capture")
    assert hasattr(JsonlRawCaptureWriter, "capture")


def test_both_writers_have_capture_malformed_method() -> None:
    assert hasattr(InMemoryRawCaptureWriter, "capture_malformed")
    assert hasattr(JsonlRawCaptureWriter, "capture_malformed")


def test_both_writers_have_capture_provider_failure_method() -> None:
    assert hasattr(InMemoryRawCaptureWriter, "capture_provider_failure")
    assert hasattr(JsonlRawCaptureWriter, "capture_provider_failure")


# ---------------------------------------------------------------------------
# Real Stage 21 payload acceptance parity (audit fix 1)
# ---------------------------------------------------------------------------


def test_both_writers_accept_real_stage21_normalize_fake_event_payload(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    from types import MappingProxyType

    from PHX2.stage21.normalized_events import normalize_fake_event
    from PHX2.stage21.ping_payloads import (
        STAGE21_FAKE_CHAIN_NAME,
        STAGE21_FAKE_PROVIDER_NAME,
    )

    writer, snapshot = writer_and_snapshot

    event = normalize_fake_event(
        provider_event_id="prov_abc",
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        source_kind="stage21_fake_source",
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint="mintaaa",
        event_type="fake_swap",
        observed_at_utc="2026-05-18T00:00:00Z",
        slot=100,
        signature="sigaaaa",
        raw_payload={"amount": 42, "is_buy": True},
    )
    assert isinstance(event.payload_summary, MappingProxyType)

    ingest_key = IngestEventKey(
        provider_id="helius",
        chain=event.chain,
        event_id=event.event_id,
        provider_event_id=event.provider_event_id,
        raw_event_hash=event.raw_event_hash,
    )
    envelope = IngestEventEnvelope(
        event=event,
        ingest_key=ingest_key,
        received_at_utc="2026-05-18T00:00:01Z",
        provider_attempt_index=0,
    )

    writer.capture(envelope=envelope)

    records = snapshot()
    assert len(records) == 1
    record = records[0]
    assert isinstance(record["payload_summary"], dict)
    assert record["payload_summary"] == {"amount": 42, "is_buy": True}


# ---------------------------------------------------------------------------
# Non-finite float rejection parity (audit fix 2)
# ---------------------------------------------------------------------------


def test_both_writers_reject_nan_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("nan")})
        )


def test_both_writers_reject_positive_infinity_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("inf")})
        )


def test_both_writers_reject_negative_infinity_in_payload_summary(
    writer_and_snapshot: tuple[RawCaptureWriter, SnapshotFn],
) -> None:
    writer, _ = writer_and_snapshot
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("-inf")})
        )
