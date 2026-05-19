"""Stage 22.3 InMemoryRawCaptureWriter semantic tests.

Pins the per-implementation semantics for the no-I/O capture
writer:

  * Empty writer yields empty snapshots across all three
    record-family accessors.
  * Each Protocol method appends exactly one record to the
    chronological stream.
  * ``captured_all`` preserves cross-family insertion order.
  * Snapshots are defensive copies -- mutating a returned dict
    (including its ``payload_summary`` inner dict) does not
    affect writer state.
  * Sanitiser violations raise ``Stage22CaptureContractError``
    and do not mutate state.
  * Strict-int discipline rejects bool for int-only fields.
  * Closed-set discipline rejects out-of-vocabulary values.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage22.constants import (
    CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
    CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
    CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
    MALFORMED_REASON_SHAPE_ERROR,
    PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
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
)
from PHX2.stage22.raw_capture import InMemoryRawCaptureWriter


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _key(
    *,
    provider_id: str = "helius",
    chain: str = "solana_mainnet",
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
) -> IngestEventKey:
    return IngestEventKey(
        provider_id=provider_id,
        chain=chain,
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
    )


def _event(
    *,
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
    mint: str = "mint-aaa",
    event_type: str = "fake_swap",
    slot: int = 100,
    signature: str = "sig-aaaa",
    payload_summary: Mapping[str, object] | None = None,
) -> NormalizedLiveEvent:
    # Do NOT copy payload_summary here -- some tests rely on the
    # raw caller dict flowing through to verify writer-side copy
    # behaviour. The writer's internal sanitiser builds its own
    # fresh dict.
    return NormalizedLiveEvent(
        event_id=event_id,
        provider_event_id=provider_event_id,
        provider_name="stage21_fake_provider",
        source_kind="stage21_fake_source",
        chain="solana_mainnet",
        mint=mint,
        event_type=event_type,
        observed_at_utc="2026-05-18T00:00:00Z",
        slot=slot,
        signature=signature,
        raw_event_hash=raw_event_hash,
        normalized_schema_version="stage21_v0_normalized_event",
        payload_summary=payload_summary if payload_summary is not None else {},
    )


def _envelope(
    *,
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
    received_at_utc: str = "2026-05-18T00:00:01Z",
    provider_attempt_index: int = 0,
    payload_summary: Mapping[str, object] | None = None,
    slot: int = 100,
) -> IngestEventEnvelope:
    event = _event(
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
        payload_summary=payload_summary,
        slot=slot,
    )
    key = _key(
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
    )
    return IngestEventEnvelope(
        event=event,
        ingest_key=key,
        received_at_utc=received_at_utc,
        provider_attempt_index=provider_attempt_index,
    )


def _malformed_record(
    *,
    provider_event_id: str = "prov-bad",
    reason: str = MALFORMED_REASON_SHAPE_ERROR,
    failed_at_utc: str = "2026-05-18T00:00:02Z",
    raw_event_hash: str = "b" * 64,
) -> MalformedEventRecord:
    return MalformedEventRecord(
        provider_id="helius",
        provider_event_id=provider_event_id,
        reason=reason,
        failed_at_utc=failed_at_utc,
        raw_event_hash=raw_event_hash,
    )


def _provider_failure_record(
    *,
    failure_label: str = PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    status_class: str = STATUS_CLASS_TIMEOUT,
    upstream_error_type: str = UPSTREAM_ERROR_TYPE_TIMEOUT,
    provider_attempt_index: int = 0,
    observed_at_utc: str = "2026-05-18T00:00:03Z",
) -> ProviderFailureRecord:
    return ProviderFailureRecord(
        provider_id="helius",
        failure_label=failure_label,
        status_class=status_class,
        upstream_error_type=upstream_error_type,
        provider_attempt_index=provider_attempt_index,
        observed_at_utc=observed_at_utc,
    )


# ---------------------------------------------------------------------------
# Empty / construction
# ---------------------------------------------------------------------------


def test_empty_writer_has_empty_captured_all_snapshot() -> None:
    writer = InMemoryRawCaptureWriter()
    assert writer.captured_all() == ()


def test_empty_writer_has_empty_normalized_event_snapshot() -> None:
    writer = InMemoryRawCaptureWriter()
    assert writer.captured_normalized_events() == ()


def test_empty_writer_has_empty_malformed_event_snapshot() -> None:
    writer = InMemoryRawCaptureWriter()
    assert writer.captured_malformed_events() == ()


def test_empty_writer_has_empty_provider_failure_snapshot() -> None:
    writer = InMemoryRawCaptureWriter()
    assert writer.captured_provider_failures() == ()


# ---------------------------------------------------------------------------
# Single-record capture
# ---------------------------------------------------------------------------


def test_capture_normalized_event_appends_exactly_one_record() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    snapshot = writer.captured_normalized_events()
    assert len(snapshot) == 1
    record = snapshot[0]
    assert record["record_type"] == CAPTURE_RECORD_TYPE_NORMALIZED_EVENT
    assert record["schema_version"] == STAGE22_CAPTURE_RECORD_SCHEMA_VERSION


def test_capture_malformed_appends_exactly_one_record() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture_malformed(record=_malformed_record())
    snapshot = writer.captured_malformed_events()
    assert len(snapshot) == 1
    record = snapshot[0]
    assert record["record_type"] == CAPTURE_RECORD_TYPE_MALFORMED_EVENT


def test_capture_provider_failure_appends_exactly_one_record() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture_provider_failure(record=_provider_failure_record())
    snapshot = writer.captured_provider_failures()
    assert len(snapshot) == 1
    record = snapshot[0]
    assert record["record_type"] == CAPTURE_RECORD_TYPE_PROVIDER_FAILURE


def test_normalized_event_record_carries_full_field_set() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    record = writer.captured_normalized_events()[0]
    expected_fields = {
        "schema_version",
        "record_type",
        "provider_id",
        "chain",
        "event_id",
        "provider_event_id",
        "raw_event_hash",
        "received_at_utc",
        "provider_attempt_index",
        "event_type",
        "source_kind",
        "mint",
        "slot",
        "signature",
        "payload_summary",
    }
    assert set(record.keys()) == expected_fields


def test_malformed_event_record_carries_full_field_set() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture_malformed(record=_malformed_record())
    record = writer.captured_malformed_events()[0]
    expected_fields = {
        "schema_version",
        "record_type",
        "provider_id",
        "provider_event_id",
        "reason",
        "failed_at_utc",
        "raw_event_hash",
    }
    assert set(record.keys()) == expected_fields


def test_provider_failure_record_carries_full_field_set() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture_provider_failure(record=_provider_failure_record())
    record = writer.captured_provider_failures()[0]
    expected_fields = {
        "schema_version",
        "record_type",
        "provider_id",
        "failure_label",
        "status_class",
        "upstream_error_type",
        "provider_attempt_index",
        "observed_at_utc",
    }
    assert set(record.keys()) == expected_fields


# ---------------------------------------------------------------------------
# Chronological order across record families
# ---------------------------------------------------------------------------


def test_captured_all_preserves_cross_family_insertion_order() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    writer.capture_provider_failure(record=_provider_failure_record())
    writer.capture_malformed(record=_malformed_record())
    writer.capture(envelope=_envelope(event_id="evt_aaaa" + "0" * 20))

    all_records = writer.captured_all()
    types = [r["record_type"] for r in all_records]
    assert types == [
        CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
        CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
        CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
        CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
    ]


def test_per_family_snapshots_filter_only_their_record_type() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    writer.capture_provider_failure(record=_provider_failure_record())
    writer.capture_malformed(record=_malformed_record())
    writer.capture_provider_failure(record=_provider_failure_record())

    assert len(writer.captured_normalized_events()) == 1
    assert len(writer.captured_malformed_events()) == 1
    assert len(writer.captured_provider_failures()) == 2


# ---------------------------------------------------------------------------
# Defensive copy: snapshots cannot mutate writer state
# ---------------------------------------------------------------------------


def test_mutating_snapshot_does_not_affect_writer_state() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    first = writer.captured_normalized_events()
    first[0]["event_type"] = "mutated"
    second = writer.captured_normalized_events()
    assert second[0]["event_type"] == "fake_swap"


def test_mutating_snapshot_payload_summary_does_not_affect_writer_state() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope(payload_summary={"amount": 42}))
    first = writer.captured_normalized_events()
    first[0]["payload_summary"]["amount"] = 999
    second = writer.captured_normalized_events()
    assert second[0]["payload_summary"]["amount"] == 42


def test_captured_all_returns_independent_copies_per_call() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    snap_a = writer.captured_all()
    snap_b = writer.captured_all()
    assert snap_a[0] is not snap_b[0]


# ---------------------------------------------------------------------------
# Keyword-only signature discipline
# ---------------------------------------------------------------------------


def test_capture_is_keyword_only() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(TypeError):
        writer.capture(_envelope())  # type: ignore[misc]


def test_capture_malformed_is_keyword_only() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(TypeError):
        writer.capture_malformed(_malformed_record())  # type: ignore[misc]


def test_capture_provider_failure_is_keyword_only() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(TypeError):
        writer.capture_provider_failure(_provider_failure_record())  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sanitiser rejection -- payload_summary
# ---------------------------------------------------------------------------


def test_capture_rejects_payload_summary_with_bytes_value() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"blob": b"raw bytes"})
        )


def test_capture_rejects_payload_summary_with_nested_dict_value() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"nested": {"inner": 1}})
        )


def test_capture_rejects_payload_summary_with_list_value() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"items": [1, 2, 3]})
        )


def test_capture_rejects_payload_summary_with_tuple_value() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"items": (1, 2, 3)})
        )


def test_capture_rejects_payload_summary_with_set_value() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"items": {1, 2, 3}})
        )


def test_capture_rejects_payload_summary_exceeding_max_keys() -> None:
    writer = InMemoryRawCaptureWriter()
    payload = {f"field_{i:02d}": i for i in range(17)}
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=_envelope(payload_summary=payload))


def test_capture_rejects_payload_summary_key_with_uppercase() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"Authorization": "x"})
        )


def test_capture_rejects_payload_summary_key_starting_with_digit() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"3rd_field": 1})
        )


def test_capture_rejects_payload_summary_key_with_secret_substring() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"api_key": "x"})
        )


def test_capture_rejects_payload_summary_value_with_url_prefix() -> None:
    writer = InMemoryRawCaptureWriter()
    url_value = "h" + "ttps://attacker.invalid/path"
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"url_like": url_value})
        )


def test_capture_rejects_payload_summary_value_exceeding_max_string_len() -> None:
    writer = InMemoryRawCaptureWriter()
    long_str = "a" * 513
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"big": long_str})
        )


def test_capture_rejects_payload_summary_value_with_long_hex_run() -> None:
    writer = InMemoryRawCaptureWriter()
    long_hex = "a" * 40 + " trailing"
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"sigish": long_hex})
        )


def test_capture_rejects_payload_summary_value_with_long_tokenish_run() -> None:
    writer = InMemoryRawCaptureWriter()
    # 32 chars of mixed letters + digits.
    long_token = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"tokenish": long_token})
        )


def test_capture_accepts_payload_summary_with_safe_primitive_values() -> None:
    writer = InMemoryRawCaptureWriter()
    payload = {
        "amount": 42,
        "is_swap": True,
        "ratio": 1.5,
        "note": "ok",
        "missing": None,
    }
    writer.capture(envelope=_envelope(payload_summary=payload))
    record = writer.captured_normalized_events()[0]
    assert record["payload_summary"] == payload


# ---------------------------------------------------------------------------
# Strict-int discipline
# ---------------------------------------------------------------------------


def test_capture_rejects_envelope_provider_attempt_index_bool() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _envelope()._replace(provider_attempt_index=True)  # type: ignore[arg-type]
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad)


def test_capture_rejects_envelope_provider_attempt_index_negative() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _envelope()._replace(provider_attempt_index=-1)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad)


def test_capture_rejects_event_slot_bool() -> None:
    writer = InMemoryRawCaptureWriter()
    bad_envelope = _envelope()._replace(event=_event(slot=True))  # type: ignore[arg-type]
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad_envelope)


def test_capture_rejects_event_slot_negative() -> None:
    writer = InMemoryRawCaptureWriter()
    bad_envelope = _envelope()._replace(event=_event(slot=-1))
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad_envelope)


def test_capture_provider_failure_rejects_provider_attempt_index_bool() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record()._replace(provider_attempt_index=True)  # type: ignore[arg-type]
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_capture_provider_failure_rejects_provider_attempt_index_negative() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record()._replace(provider_attempt_index=-1)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


# ---------------------------------------------------------------------------
# Closed-set rejection
# ---------------------------------------------------------------------------


def test_capture_malformed_rejects_reason_outside_closed_set() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _malformed_record(reason="not_a_real_reason")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_malformed(record=bad)


def test_capture_provider_failure_rejects_failure_label_outside_closed_set() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record(failure_label="not_a_real_label")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_capture_provider_failure_rejects_status_class_outside_closed_set() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record(status_class="not_a_status")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_capture_provider_failure_rejects_status_class_success() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record(status_class=STATUS_CLASS_SUCCESS)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_capture_provider_failure_rejects_upstream_error_type_outside_closed_set() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record(upstream_error_type="not_a_type")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_capture_provider_failure_rejects_upstream_error_type_empty() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record(
        upstream_error_type=UPSTREAM_ERROR_TYPE_NONE
    )
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


# ---------------------------------------------------------------------------
# Non-empty / type discipline for top-level fields
# ---------------------------------------------------------------------------


def test_capture_rejects_envelope_received_at_utc_empty() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _envelope()._replace(received_at_utc="")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad)


def test_capture_malformed_rejects_failed_at_utc_empty() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _malformed_record(failed_at_utc="")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_malformed(record=bad)


def test_capture_provider_failure_rejects_observed_at_utc_empty() -> None:
    writer = InMemoryRawCaptureWriter()
    bad = _provider_failure_record(observed_at_utc="")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


def test_capture_malformed_allows_empty_provider_event_id() -> None:
    """Per Stage 22.1 convention, provider_event_id may be the empty
    string on a malformed event when the envelope is too malformed
    to extract it.
    """
    writer = InMemoryRawCaptureWriter()
    writer.capture_malformed(
        record=_malformed_record(provider_event_id="")
    )
    record = writer.captured_malformed_events()[0]
    assert record["provider_event_id"] == ""


def test_capture_allows_empty_provider_event_id_on_envelope() -> None:
    """The envelope's ingest_key may carry empty provider_event_id as
    an audit-only field; the writer accepts it.
    """
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope(provider_event_id=""))
    record = writer.captured_normalized_events()[0]
    assert record["provider_event_id"] == ""


# ---------------------------------------------------------------------------
# Rejection state preservation
# ---------------------------------------------------------------------------


def test_rejected_capture_leaves_in_memory_state_unchanged() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope())
    assert len(writer.captured_all()) == 1
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"api_key": "x"})
        )
    assert len(writer.captured_all()) == 1


def test_rejected_malformed_capture_leaves_state_unchanged() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture_malformed(record=_malformed_record())
    assert len(writer.captured_all()) == 1
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_malformed(
            record=_malformed_record(reason="not_a_real_reason")
        )
    assert len(writer.captured_all()) == 1


def test_rejected_provider_failure_capture_leaves_state_unchanged() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture_provider_failure(record=_provider_failure_record())
    assert len(writer.captured_all()) == 1
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(
            record=_provider_failure_record(failure_label="not_a_real_label")
        )
    assert len(writer.captured_all()) == 1


# ---------------------------------------------------------------------------
# Payload_summary copy independence at write time
# ---------------------------------------------------------------------------


def test_mutating_caller_payload_after_capture_does_not_affect_writer_state() -> None:
    writer = InMemoryRawCaptureWriter()
    caller_payload: dict[str, object] = {"amount": 42}
    writer.capture(envelope=_envelope(payload_summary=caller_payload))
    caller_payload["amount"] = 999
    record = writer.captured_normalized_events()[0]
    assert record["payload_summary"]["amount"] == 42


def test_writer_does_not_mutate_caller_payload_summary_dict() -> None:
    writer = InMemoryRawCaptureWriter()
    caller_payload: dict[str, object] = {"amount": 42, "is_buy": True}
    expected_snapshot = dict(caller_payload)
    writer.capture(envelope=_envelope(payload_summary=caller_payload))
    assert caller_payload == expected_snapshot


# ---------------------------------------------------------------------------
# Mapping / MappingProxyType acceptance (audit fix 1)
# ---------------------------------------------------------------------------


def test_capture_accepts_mapping_proxy_type_payload_summary() -> None:
    from types import MappingProxyType

    writer = InMemoryRawCaptureWriter()
    proxy = MappingProxyType({"amount": 42, "is_buy": True})
    writer.capture(envelope=_envelope(payload_summary=proxy))
    record = writer.captured_normalized_events()[0]
    # payload_summary in the snapshot is a plain dict (copied
    # out of the MappingProxyType for safe JSON serialisation).
    assert isinstance(record["payload_summary"], dict)
    assert record["payload_summary"] == {"amount": 42, "is_buy": True}


def test_in_memory_writer_accepts_real_stage21_normalize_fake_event_payload() -> None:
    """End-to-end Stage 21 → Stage 22.3 acceptance.

    Stage 21's ``normalize_fake_event`` produces a
    ``NormalizedLiveEvent`` whose ``payload_summary`` is a
    frozen ``MappingProxyType``. The writer MUST accept it
    without rejecting on the mapping type.
    """
    from types import MappingProxyType

    from PHX2.stage21.normalized_events import normalize_fake_event
    from PHX2.stage21.ping_payloads import (
        STAGE21_FAKE_CHAIN_NAME,
        STAGE21_FAKE_PROVIDER_NAME,
    )

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
    # Confirm Stage 21 produces the frozen mapping type.
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

    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=envelope)

    records = writer.captured_normalized_events()
    assert len(records) == 1
    record = records[0]
    assert record["chain"] == event.chain
    assert record["event_id"] == event.event_id
    assert record["raw_event_hash"] == event.raw_event_hash
    # payload_summary copied into a plain dict.
    assert isinstance(record["payload_summary"], dict)
    assert record["payload_summary"] == {"amount": 42, "is_buy": True}


# ---------------------------------------------------------------------------
# Non-finite float rejection (audit fix 2)
# ---------------------------------------------------------------------------


def test_capture_rejects_nan_in_payload_summary() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("nan")})
        )


def test_capture_rejects_positive_infinity_in_payload_summary() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("inf")})
        )


def test_capture_rejects_negative_infinity_in_payload_summary() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("-inf")})
        )


def test_capture_accepts_finite_float_in_payload_summary() -> None:
    writer = InMemoryRawCaptureWriter()
    writer.capture(envelope=_envelope(payload_summary={"ratio": 1.5}))
    record = writer.captured_normalized_events()[0]
    assert record["payload_summary"] == {"ratio": 1.5}


# ---------------------------------------------------------------------------
# Additional sanitiser tests (audit-recommended expansion)
# ---------------------------------------------------------------------------


def test_capture_rejects_payload_summary_with_non_string_key() -> None:
    writer = InMemoryRawCaptureWriter()
    bad_payload: dict[object, object] = {1: "value"}
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=_envelope(payload_summary=bad_payload))  # type: ignore[arg-type]


def test_capture_rejects_payload_summary_with_empty_key() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=_envelope(payload_summary={"": 1}))


def test_capture_rejects_payload_summary_with_key_longer_than_max() -> None:
    writer = InMemoryRawCaptureWriter()
    long_key = "k" + "x" * 64  # length 65, max is 64
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=_envelope(payload_summary={long_key: 1}))


def test_capture_rejects_payload_summary_with_hyphenated_key() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"some-field": 1})
        )


def test_capture_rejects_payload_summary_with_dotted_key() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"some.field": 1})
        )


def test_capture_rejects_payload_summary_with_custom_object_value() -> None:
    class _Custom:
        pass

    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"obj": _Custom()})
        )


def test_capture_rejects_payload_summary_with_frozenset_value() -> None:
    writer = InMemoryRawCaptureWriter()
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"items": frozenset({1, 2})})
        )
