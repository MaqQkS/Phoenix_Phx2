"""Stage 22.3 JsonlRawCaptureWriter tests.

Pins JSONL-specific semantics on top of the shared capture
contract:

  * File-format invariants: sorted keys, compact separators,
    newline-terminated, no timestamps as separate top-level
    fields beyond the caller-supplied ``*_at_utc`` fields, no
    secret-bearing top-level field names, exact per-record-type
    schema.
  * Replay validation across construction boundaries.
  * Hard contract violations on every documented failure mode.
  * Path discipline: ``..`` rejected, missing parent rejected,
    non-Path argument rejected, non-file path rejected, no
    ``mkdir`` performed.
  * Write-failure behaviour: OSError during any capture method
    raises Stage22CaptureContractError; on-disk state remains
    byte-identical.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Mapping

import pytest

from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage22.constants import (
    CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS,
    CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS,
    CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS,
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
from PHX2.stage22.raw_capture import JsonlRawCaptureWriter


# ---------------------------------------------------------------------------
# Builders (duplicated from test_raw_capture_in_memory for test isolation)
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


def _good_normalized_event_dict() -> dict[str, object]:
    """Build a canonical-shape normalized_event dict matching the
    locked field set, suitable for direct injection into a JSONL
    line during replay-tests.
    """
    return {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
        "provider_id": "helius",
        "chain": "solana_mainnet",
        "event_id": "evt_0123456789abcdef01234567",
        "provider_event_id": "prov-abc",
        "raw_event_hash": "a" * 64,
        "received_at_utc": "2026-05-18T00:00:01Z",
        "provider_attempt_index": 0,
        "event_type": "fake_swap",
        "source_kind": "stage21_fake_source",
        "mint": "mint-aaa",
        "slot": 100,
        "signature": "sig-aaaa",
        "payload_summary": {},
    }


def _good_malformed_event_dict() -> dict[str, object]:
    return {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
        "provider_id": "helius",
        "provider_event_id": "prov-bad",
        "reason": MALFORMED_REASON_SHAPE_ERROR,
        "failed_at_utc": "2026-05-18T00:00:02Z",
        "raw_event_hash": "b" * 64,
    }


def _good_provider_failure_dict() -> dict[str, object]:
    return {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
        "provider_id": "helius",
        "failure_label": PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
        "status_class": STATUS_CLASS_TIMEOUT,
        "upstream_error_type": UPSTREAM_ERROR_TYPE_TIMEOUT,
        "provider_attempt_index": 0,
        "observed_at_utc": "2026-05-18T00:00:03Z",
    }


def _to_line(record: dict[str, object]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"


# ---------------------------------------------------------------------------
# Core capture semantics
# ---------------------------------------------------------------------------


def test_capture_writes_exactly_one_normalized_event_record(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["record_type"] == CAPTURE_RECORD_TYPE_NORMALIZED_EVENT


def test_capture_malformed_writes_exactly_one_malformed_record(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture_malformed(record=_malformed_record())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["record_type"] == CAPTURE_RECORD_TYPE_MALFORMED_EVENT


def test_capture_provider_failure_writes_exactly_one_provider_failure_record(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture_provider_failure(record=_provider_failure_record())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["record_type"] == CAPTURE_RECORD_TYPE_PROVIDER_FAILURE


def test_three_captures_produce_three_lines_in_chronological_order(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    writer.capture_provider_failure(record=_provider_failure_record())
    writer.capture_malformed(record=_malformed_record())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    types = [json.loads(line)["record_type"] for line in lines]
    assert types == [
        CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
        CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
        CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
    ]


# ---------------------------------------------------------------------------
# File-format invariants
# ---------------------------------------------------------------------------


def test_emitted_record_has_sorted_keys_and_compact_separators(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    raw = p.read_text(encoding="utf-8")
    line = raw.splitlines()[0]
    record = json.loads(line)
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    assert line == canonical
    assert ": " not in raw
    assert ", " not in raw


def test_emitted_lines_are_newline_terminated(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    writer.capture_malformed(record=_malformed_record())
    raw = p.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw.count("\n") == 2


def test_emitted_normalized_event_record_carries_locked_field_set(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert set(record.keys()) == set(
        CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS
    )


def test_emitted_malformed_event_record_carries_locked_field_set(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture_malformed(record=_malformed_record())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert set(record.keys()) == set(
        CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS
    )


def test_emitted_provider_failure_record_carries_locked_field_set(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture_provider_failure(record=_provider_failure_record())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert set(record.keys()) == set(
        CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS
    )


def test_emitted_record_uses_locked_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert record["schema_version"] == STAGE22_CAPTURE_RECORD_SCHEMA_VERSION


def test_emitted_record_has_no_unexpected_timestamp_fields(
    tmp_path: Path,
) -> None:
    """Capture record carries only the caller-supplied timestamp
    field for its record_type; no writer-generated timestamp
    leaks in.
    """
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    writer.capture_malformed(record=_malformed_record())
    writer.capture_provider_failure(record=_provider_failure_record())
    raw = p.read_text(encoding="utf-8")
    for line in raw.splitlines():
        record = json.loads(line)
        forbidden = (
            "timestamp",
            "ts",
            "epoch",
            "time",
            "datetime",
            "at_utc",
            "now",
        )
        for f in forbidden:
            assert f not in record


def test_emitted_record_has_no_secret_bearing_top_level_field_names(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    writer.capture_malformed(record=_malformed_record())
    writer.capture_provider_failure(record=_provider_failure_record())
    forbidden_substrings = (
        "api_key",
        "apikey",
        "webhook",
        "rpc_url",
        "raw_response",
        "response_body",
        "exception_message",
        "exception_repr",
        "exception_args",
        "authorization",
        "bearer",
        "password",
        "secret",
        "credential",
        "private_key",
    )
    raw = p.read_text(encoding="utf-8")
    for line in raw.splitlines():
        record = json.loads(line)
        for field in record.keys():
            lower = field.lower()
            for bad in forbidden_substrings:
                assert bad not in lower


# ---------------------------------------------------------------------------
# Replay reconstruction (constructor accepts a valid file and continues to write)
# ---------------------------------------------------------------------------


def test_replay_accepts_valid_pre_existing_file(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    first = JsonlRawCaptureWriter(path=p)
    first.capture(envelope=_envelope())
    first.capture_malformed(record=_malformed_record())
    first.capture_provider_failure(record=_provider_failure_record())
    # Construct a second writer over the same file; replay
    # validates each line but does not raise.
    second = JsonlRawCaptureWriter(path=p)
    # The second writer can continue to append.
    second.capture(envelope=_envelope(event_id="evt_aaaa" + "0" * 20))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4


def test_two_writers_at_different_paths_have_independent_files(
    tmp_path: Path,
) -> None:
    a = JsonlRawCaptureWriter(path=tmp_path / "a.jsonl")
    b = JsonlRawCaptureWriter(path=tmp_path / "b.jsonl")
    a.capture(envelope=_envelope())
    a_text = (tmp_path / "a.jsonl").read_text(encoding="utf-8")
    b_text_before = (
        (tmp_path / "b.jsonl").read_text(encoding="utf-8")
        if (tmp_path / "b.jsonl").exists()
        else ""
    )
    _ = b
    assert a_text != ""
    assert b_text_before == ""


# ---------------------------------------------------------------------------
# File-presence behaviour at construction
# ---------------------------------------------------------------------------


def test_missing_file_with_existing_parent_yields_empty_state(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    assert not p.exists()
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    assert p.exists()


def test_empty_file_yields_empty_state(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text("", encoding="utf-8")
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_missing_parent_raises_at_construction(tmp_path: Path) -> None:
    p = tmp_path / "missing_dir" / "capture.jsonl"
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_constructor_does_not_create_missing_parent(tmp_path: Path) -> None:
    p = tmp_path / "missing_dir" / "capture.jsonl"
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)
    assert not (tmp_path / "missing_dir").exists()


def test_path_traversal_with_dotdot_segment_rejected(tmp_path: Path) -> None:
    p = tmp_path / ".." / "capture.jsonl"
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_non_pathlib_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=str(tmp_path / "capture.jsonl"))  # type: ignore[arg-type]


def test_path_pointing_at_existing_directory_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=tmp_path)


def test_constructor_is_keyword_only(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        JsonlRawCaptureWriter(tmp_path / "capture.jsonl")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Replay-time contract violations
# ---------------------------------------------------------------------------


def test_replay_rejects_malformed_json_line(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text("this is not json\n", encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_json_array_instead_of_object(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text("[1,2,3]\n", encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_unknown_schema_version(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["schema_version"] = "stage22_v999_unknown"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_unknown_record_type(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["record_type"] = "delivered"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_blank_line(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text("\n", encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


# ---------------------------------------------------------------------------
# Per-record-type missing-required-field rejection
# ---------------------------------------------------------------------------


def test_replay_rejects_missing_field_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    del bad["mint"]
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_missing_field_in_malformed_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_malformed_event_dict()
    del bad["reason"]
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_missing_field_in_provider_failure(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    del bad["status_class"]
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


# ---------------------------------------------------------------------------
# Per-record-type extra-field rejection (Stage 22.2 audit lesson)
# ---------------------------------------------------------------------------


_AUDIT_EXTRA_FIELD_LEAK_SHAPES: tuple[tuple[str, str], ...] = (
    ("raw_response_body", "would-be raw provider response body"),
    ("headers", "would-be Authorization header value"),
    ("webhook_url", "would-be webhook target placeholder"),
    ("cursor", "cursor-token-abc"),
    ("transport_body", "would-be transport request body"),
    ("exception_message", "would-be exception message"),
    ("recipient", "would-be channel id"),
    ("authorization", "would-be Bearer token"),
    ("bearer", "would-be Bearer token"),
)


@pytest.mark.parametrize(
    "extra_field,extra_value", _AUDIT_EXTRA_FIELD_LEAK_SHAPES
)
def test_replay_rejects_extra_field_on_normalized_event(
    tmp_path: Path,
    extra_field: str,
    extra_value: str,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad[extra_field] = extra_value
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


@pytest.mark.parametrize(
    "extra_field,extra_value", _AUDIT_EXTRA_FIELD_LEAK_SHAPES
)
def test_replay_rejects_extra_field_on_malformed_event(
    tmp_path: Path,
    extra_field: str,
    extra_value: str,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_malformed_event_dict()
    bad[extra_field] = extra_value
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


@pytest.mark.parametrize(
    "extra_field,extra_value", _AUDIT_EXTRA_FIELD_LEAK_SHAPES
)
def test_replay_rejects_extra_field_on_provider_failure(
    tmp_path: Path,
    extra_field: str,
    extra_value: str,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad[extra_field] = extra_value
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


# ---------------------------------------------------------------------------
# Wrong-type / negative / empty rejection per record_type
# ---------------------------------------------------------------------------


def test_replay_rejects_non_string_string_field_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["mint"] = 42
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_non_int_slot_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["slot"] = "100"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_bool_slot_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["slot"] = True
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_negative_slot_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["slot"] = -1
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_bool_provider_attempt_index_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["provider_attempt_index"] = False
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_empty_mint_in_normalized_event(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["mint"] = ""
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_allows_empty_provider_event_id_in_normalized_event(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    rec = _good_normalized_event_dict()
    rec["provider_event_id"] = ""
    p.write_text(_to_line(rec), encoding="utf-8")
    # Does not raise.
    JsonlRawCaptureWriter(path=p)


def test_replay_rejects_non_object_payload_summary(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["payload_summary"] = "not a dict"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_unsafe_payload_summary_value(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["payload_summary"] = {"api_key": "x"}
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_unsupported_payload_summary_value_type(
    tmp_path: Path,
) -> None:
    """A JSON array nested inside payload_summary deserialises as a
    Python list, which the sanitiser rejects.
    """
    p = tmp_path / "capture.jsonl"
    bad = _good_normalized_event_dict()
    bad["payload_summary"] = {"items": [1, 2, 3]}
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_reason_outside_closed_set(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_malformed_event_dict()
    bad["reason"] = "not_a_real_reason"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_failure_label_outside_closed_set(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["failure_label"] = "not_a_real_label"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_status_class_outside_closed_set(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["status_class"] = "not_a_status"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_status_class_success_on_provider_failure(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["status_class"] = STATUS_CLASS_SUCCESS
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_upstream_error_type_outside_closed_set(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["upstream_error_type"] = "not_a_type"
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_empty_upstream_error_type_on_provider_failure(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["upstream_error_type"] = UPSTREAM_ERROR_TYPE_NONE
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_bool_provider_attempt_index_on_provider_failure(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["provider_attempt_index"] = True
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_negative_provider_attempt_index_on_provider_failure(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    bad = _good_provider_failure_dict()
    bad["provider_attempt_index"] = -1
    p.write_text(_to_line(bad), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


# ---------------------------------------------------------------------------
# Write-time sanitiser rejection (mirrors in-memory tests but via JSONL writer)
# ---------------------------------------------------------------------------


def test_capture_rejects_bytes_in_payload_summary(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"blob": b"raw bytes"})
        )


def test_capture_rejects_nested_dict_in_payload_summary(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"nested": {"a": 1}})
        )


def test_capture_rejects_secret_key_in_payload_summary(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"api_key": "x"})
        )


def test_capture_rejects_url_substring_in_payload_summary_value(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    url_like = "h" + "ttps://attacker.invalid/path"
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"url_like": url_like})
        )


# ---------------------------------------------------------------------------
# Failed writes do not corrupt the file
# ---------------------------------------------------------------------------


def test_failed_capture_does_not_append_a_line(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    text_before = p.read_text(encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"api_key": "x"})
        )
    text_after = p.read_text(encoding="utf-8")
    assert text_after == text_before


# ---------------------------------------------------------------------------
# Write-failure behaviour
# ---------------------------------------------------------------------------


def test_write_failure_during_capture_raises_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=_envelope())


def test_write_failure_during_capture_malformed_raises_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_malformed(record=_malformed_record())


def test_write_failure_during_capture_provider_failure_raises_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=_provider_failure_record())


def test_write_failure_leaves_file_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=_envelope())
    bytes_before = p.read_bytes()

    real_open = builtins.open

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated write failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=_envelope())

    monkeypatch.setattr(builtins, "open", real_open)
    bytes_after = p.read_bytes()
    assert bytes_after == bytes_before


# ---------------------------------------------------------------------------
# Keyword-only signature discipline
# ---------------------------------------------------------------------------


def test_capture_is_keyword_only(tmp_path: Path) -> None:
    writer = JsonlRawCaptureWriter(path=tmp_path / "capture.jsonl")
    with pytest.raises(TypeError):
        writer.capture(_envelope())  # type: ignore[misc]


def test_capture_malformed_is_keyword_only(tmp_path: Path) -> None:
    writer = JsonlRawCaptureWriter(path=tmp_path / "capture.jsonl")
    with pytest.raises(TypeError):
        writer.capture_malformed(_malformed_record())  # type: ignore[misc]


def test_capture_provider_failure_is_keyword_only(tmp_path: Path) -> None:
    writer = JsonlRawCaptureWriter(path=tmp_path / "capture.jsonl")
    with pytest.raises(TypeError):
        writer.capture_provider_failure(_provider_failure_record())  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Roundtrip / replay across reload
# ---------------------------------------------------------------------------


def test_normalized_event_record_round_trips_back_through_replay(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    first = JsonlRawCaptureWriter(path=p)
    first.capture(
        envelope=_envelope(payload_summary={"amount": 7, "is_buy": True})
    )
    # Reload triggers replay; if any rule is wrong it would
    # raise here.
    second = JsonlRawCaptureWriter(path=p)
    second.capture(envelope=_envelope(event_id="evt_aaaa" + "0" * 20))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first_record = json.loads(lines[0])
    assert first_record["payload_summary"] == {"amount": 7, "is_buy": True}


def test_mixed_record_type_file_survives_replay(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    first = JsonlRawCaptureWriter(path=p)
    first.capture(envelope=_envelope())
    first.capture_provider_failure(record=_provider_failure_record())
    first.capture_malformed(record=_malformed_record())
    # No raise on second construction.
    JsonlRawCaptureWriter(path=p)


# ---------------------------------------------------------------------------
# Non-empty / type discipline on top-level capture inputs
# ---------------------------------------------------------------------------


def test_capture_rejects_envelope_received_at_utc_empty(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    bad = _envelope()._replace(received_at_utc="")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(envelope=bad)


def test_capture_malformed_rejects_failed_at_utc_empty(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    bad = _malformed_record(failed_at_utc="")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_malformed(record=bad)


def test_capture_provider_failure_rejects_observed_at_utc_empty(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    bad = _provider_failure_record(observed_at_utc="")
    with pytest.raises(Stage22CaptureContractError):
        writer.capture_provider_failure(record=bad)


# ---------------------------------------------------------------------------
# Mapping / MappingProxyType acceptance + real Stage 21 roundtrip (audit fix 1)
# ---------------------------------------------------------------------------


def test_jsonl_writer_accepts_mapping_proxy_type_payload_summary(
    tmp_path: Path,
) -> None:
    from types import MappingProxyType

    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    proxy = MappingProxyType({"amount": 42, "is_buy": True})
    writer.capture(envelope=_envelope(payload_summary=proxy))
    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(record["payload_summary"], dict)
    assert record["payload_summary"] == {"amount": 42, "is_buy": True}


def test_jsonl_writer_accepts_real_stage21_normalize_fake_event_payload(
    tmp_path: Path,
) -> None:
    """End-to-end Stage 21 → Stage 22.3 acceptance, JSONL side."""
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

    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    writer.capture(envelope=envelope)

    record = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert record["chain"] == event.chain
    assert record["event_id"] == event.event_id
    assert record["raw_event_hash"] == event.raw_event_hash
    assert isinstance(record["payload_summary"], dict)
    assert record["payload_summary"] == {"amount": 42, "is_buy": True}

    # And the file replays cleanly across reload.
    JsonlRawCaptureWriter(path=p)


# ---------------------------------------------------------------------------
# Non-finite float rejection on write + replay (audit fix 2)
# ---------------------------------------------------------------------------


def test_capture_rejects_nan_in_payload_summary(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("nan")})
        )


def test_capture_rejects_positive_infinity_in_payload_summary(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("inf")})
        )


def test_capture_rejects_negative_infinity_in_payload_summary(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    writer = JsonlRawCaptureWriter(path=p)
    with pytest.raises(Stage22CaptureContractError):
        writer.capture(
            envelope=_envelope(payload_summary={"ratio": float("-inf")})
        )


def _line_with_non_finite_payload(literal_token: str) -> str:
    """Build a JSONL line whose payload_summary contains a literal
    JavaScript-style non-finite float token (NaN / Infinity /
    -Infinity) that Python ``json.loads`` accepts by default.
    Used to force the replay path to encounter a non-finite
    float without depending on ``allow_nan=True`` serialisation.
    """
    rec = _good_normalized_event_dict()
    # Build the line manually so we can inject the bare token.
    # First, serialise everything EXCEPT payload_summary, then
    # patch the substring.
    placeholder = "__NON_FINITE_PLACEHOLDER__"
    rec["payload_summary"] = {"ratio": placeholder}
    line = json.dumps(rec, sort_keys=True, separators=(",", ":"))
    line = line.replace(f'"{placeholder}"', literal_token)
    return line + "\n"


def test_replay_rejects_payload_summary_with_nan(tmp_path: Path) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text(_line_with_non_finite_payload("NaN"), encoding="utf-8")
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_payload_summary_with_positive_infinity(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text(
        _line_with_non_finite_payload("Infinity"), encoding="utf-8"
    )
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_replay_rejects_payload_summary_with_negative_infinity(
    tmp_path: Path,
) -> None:
    p = tmp_path / "capture.jsonl"
    p.write_text(
        _line_with_non_finite_payload("-Infinity"), encoding="utf-8"
    )
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_serialization_uses_allow_nan_false(tmp_path: Path) -> None:
    """If a non-finite float ever reached the serialiser, it would
    raise ``ValueError`` (allow_nan=False), proving the serialiser
    cannot emit a JS-style token. We capture-then-introspect the
    writer's serialise helper via a direct call to confirm.
    """
    from PHX2.stage22.raw_capture import _serialize_record

    bad_record: dict[str, object] = {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
        "ratio": float("inf"),
    }
    with pytest.raises(ValueError):
        _serialize_record(record=bad_record)


# ---------------------------------------------------------------------------
# Replay OSError wrapping (audit fix 3)
# ---------------------------------------------------------------------------


def test_constructor_replay_open_failure_raises_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = tmp_path / "capture.jsonl"
    # Create a valid existing file so the constructor's
    # path-existence check passes and we reach the replay open().
    p.write_text(
        _to_line(_good_normalized_event_dict()),
        encoding="utf-8",
    )

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated replay read failure")

    monkeypatch.setattr(builtins, "open", boom)
    with pytest.raises(Stage22CaptureContractError):
        JsonlRawCaptureWriter(path=p)


def test_constructor_replay_open_failure_does_not_leak_raw_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative-shape assertion: the constructor must NOT propagate
    OSError to the caller. Stage22CaptureContractError is the
    only contract violation exception type.
    """
    p = tmp_path / "capture.jsonl"
    p.write_text(
        _to_line(_good_normalized_event_dict()),
        encoding="utf-8",
    )

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("simulated replay read failure")

    monkeypatch.setattr(builtins, "open", boom)
    try:
        JsonlRawCaptureWriter(path=p)
    except Stage22CaptureContractError:
        pass  # expected
    except OSError as raw:
        pytest.fail(
            f"raw OSError leaked from constructor: {raw!r}"
        )
    else:
        pytest.fail("constructor unexpectedly succeeded")
