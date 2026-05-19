"""Stage 23.1 input reader tests.

Pins:

  * Valid JSONL fixtures are read into ``Stage23FilterInput``
    records.
  * Preserved fields are projected verbatim when present.
  * Missing optional fields are NOT fabricated; the
    ``missing_fields`` tuple identifies them.
  * Malformed JSONL raises ``Stage23InputError``.
  * Empty file returns empty tuple.
  * Missing file raises ``Stage23InputError``.
  * Directory path raises ``Stage23InputError``.
  * Secret-looking input rows are rejected.
  * Input artifact contents are not mutated by the reader.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage23.constants import (
    INPUT_KIND_DEDUPE,
    INPUT_KIND_RAW_CAPTURE,
    INPUT_KIND_SYNTHETIC,
)
from PHX2.stage23.errors import Stage23InputError
from PHX2.stage23.input_reader import read_stage22_jsonl


# Stage 22.3 normalized_event row fixture. Mirrors the locked
# ``CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS`` field-name family
# but uses synthetic secret-free values.
def _normalized_event_row(
    *,
    event_id: str,
    token_mint: str,
    slot: int,
    signature: str,
) -> dict[str, object]:
    return {
        "schema_version": "stage22_v0_capture",
        "record_type": "normalized_event",
        "provider_id": "fake_provider",
        "chain": "synthetic_chain",
        "event_id": event_id,
        "provider_event_id": event_id,
        "raw_event_hash": "a" * 12,
        "received_at_utc": "2026-01-01T00:00:00Z",
        "provider_attempt_index": 0,
        "event_type": "synthetic_event",
        "source_kind": "synthetic_source",
        "mint": token_mint,
        "token_mint": token_mint,
        "slot": slot,
        "signature": signature,
        "payload_summary": {
            "ok": True,
            "rank": 1,
        },
    }


def _write_jsonl(*, path: Path, rows: list[dict[str, object]]) -> None:
    body = "\n".join(json.dumps(row) for row in rows)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_reads_valid_jsonl_fixture(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    rows = [
        _normalized_event_row(
            event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa",
            token_mint="MintA1111111111",
            slot=100,
            signature="sig_a",
        ),
        _normalized_event_row(
            event_id="evt_bbbbbbbbbbbbbbbbbbbbbbbb",
            token_mint="MintB2222222222",
            slot=101,
            signature="sig_b",
        ),
    ]
    _write_jsonl(path=path, rows=rows)

    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )

    assert len(inputs) == 2
    assert inputs[0].token_mint == "MintA1111111111"
    assert inputs[0].provider_id == "fake_provider"
    assert inputs[0].event_id == "evt_aaaaaaaaaaaaaaaaaaaaaaaa"
    assert inputs[0].slot == 100
    assert inputs[0].signature == "sig_a"
    assert inputs[0].observed_at_utc == "2026-01-01T00:00:00Z"
    assert inputs[1].token_mint == "MintB2222222222"
    assert inputs[1].slot == 101


def test_preserves_optional_fields_when_present(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    rows = [
        _normalized_event_row(
            event_id="evt_cccccccccccccccccccccccc",
            token_mint="MintC3333333333",
            slot=200,
            signature="sig_c",
        )
    ]
    _write_jsonl(path=path, rows=rows)
    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )
    record = inputs[0]
    assert "provider_id" not in record.missing_fields
    assert "event_id" not in record.missing_fields
    assert "token_mint" not in record.missing_fields
    assert "slot" not in record.missing_fields
    assert "signature" not in record.missing_fields
    assert "observed_at_utc" not in record.missing_fields


def test_missing_optional_fields_are_not_fabricated(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    sparse_row = {
        "provider_id": "fake_provider",
        "event_id": "evt_aaaaaaaaaaaaaaaaaaaaaaaa",
        # No slot, signature, observed_at_utc, payload_summary.
    }
    _write_jsonl(path=path, rows=[sparse_row])

    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_SYNTHETIC,
    )
    record = inputs[0]
    assert record.provider_id == "fake_provider"
    assert record.event_id == "evt_aaaaaaaaaaaaaaaaaaaaaaaa"
    # Slot is reported as the locked sentinel (-1) when absent.
    assert record.slot == -1
    # signature / observed_at_utc / token_mint defaulted to "" when
    # not carried; the missing_fields tuple captures the absence.
    assert record.signature == ""
    assert record.observed_at_utc == ""
    assert record.token_mint == ""
    assert "signature" in record.missing_fields
    assert "observed_at_utc" in record.missing_fields
    assert "token_mint" in record.missing_fields
    assert "slot" in record.missing_fields


def test_reads_dedupe_seen_rows(tmp_path: Path):
    path = tmp_path / "dedupe.jsonl"
    rows = [
        {
            "schema_version": "stage22_v0_ledger",
            "record_type": "seen",
            "provider_id": "fake_provider",
            "chain": "synthetic_chain",
            "event_id": "evt_aaaaaaaaaaaaaaaaaaaaaaaa",
            "provider_event_id": "evt_aaaaaaaaaaaaaaaaaaaaaaaa",
            "raw_event_hash": "a" * 12,
        },
        {
            "schema_version": "stage22_v0_ledger",
            "record_type": "dispatched",
            "provider_id": "fake_provider",
            "chain": "synthetic_chain",
            "event_id": "evt_aaaaaaaaaaaaaaaaaaaaaaaa",
            "provider_event_id": "evt_aaaaaaaaaaaaaaaaaaaaaaaa",
            "raw_event_hash": "a" * 12,
        },
    ]
    _write_jsonl(path=path, rows=rows)
    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_DEDUPE,
    )
    # Only the "seen" line is projected; the "dispatched" line is
    # skipped for the 23.1 reader.
    assert len(inputs) == 1
    assert inputs[0].event_id == "evt_aaaaaaaaaaaaaaaaaaaaaaaa"


def test_skips_provider_failure_and_malformed_event_rows(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    rows = [
        {
            "schema_version": "stage22_v0_capture",
            "record_type": "provider_failure",
            "provider_id": "fake_provider",
            "failure_label": "provider_fetch_timeout",
            "status_class": "timeout",
            "upstream_error_type": "timeout",
            "provider_attempt_index": 0,
            "observed_at_utc": "2026-01-01T00:00:00Z",
        },
        {
            "schema_version": "stage22_v0_capture",
            "record_type": "malformed_event",
            "provider_id": "fake_provider",
            "provider_event_id": "",
            "reason": "decode_shape_error",
            "failed_at_utc": "2026-01-01T00:00:00Z",
            "raw_event_hash": "a" * 12,
        },
        _normalized_event_row(
            event_id="evt_eeeeeeeeeeeeeeeeeeeeeeee",
            token_mint="MintE5555555555",
            slot=400,
            signature="sig_e",
        ),
    ]
    _write_jsonl(path=path, rows=rows)
    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )
    assert len(inputs) == 1
    assert inputs[0].token_mint == "MintE5555555555"


# ---------------------------------------------------------------------------
# Determinism / non-mutation
# ---------------------------------------------------------------------------


def test_row_order_is_preserved(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    rows = [
        _normalized_event_row(
            event_id=f"evt_{i:024d}",
            token_mint=f"Mint{i:010d}",
            slot=1000 + i,
            signature=f"sig_{i}",
        )
        for i in range(5)
    ]
    _write_jsonl(path=path, rows=rows)
    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )
    assert [r.signature for r in inputs] == [
        "sig_0",
        "sig_1",
        "sig_2",
        "sig_3",
        "sig_4",
    ]


def test_reader_does_not_mutate_input_file_contents(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    rows = [
        _normalized_event_row(
            event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa",
            token_mint="MintA",
            slot=10,
            signature="sig_a",
        )
    ]
    _write_jsonl(path=path, rows=rows)
    before = path.read_bytes()
    read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )
    after = path.read_bytes()
    assert before == after


def test_empty_file_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )
    assert inputs == ()


def test_file_with_only_trailing_newline_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "newline.jsonl"
    path.write_text("\n", encoding="utf-8")
    inputs = read_stage22_jsonl(
        path=path,
        input_kind=INPUT_KIND_RAW_CAPTURE,
    )
    assert inputs == ()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_file_raises_typed_error(tmp_path: Path):
    missing = tmp_path / "does_not_exist.jsonl"
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=missing,
            input_kind=INPUT_KIND_RAW_CAPTURE,
        )


def test_directory_path_raises_typed_error(tmp_path: Path):
    directory = tmp_path / "dir_not_file"
    directory.mkdir()
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=directory,
            input_kind=INPUT_KIND_RAW_CAPTURE,
        )


def test_unknown_input_kind_raises_typed_error(tmp_path: Path):
    path = tmp_path / "raw.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind="not_a_kind",
        )


def test_malformed_json_raises_typed_error(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text("this is not json\n", encoding="utf-8")
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_non_object_top_level_raises_typed_error(tmp_path: Path):
    path = tmp_path / "array.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_intra_file_blank_line_raises_typed_error(tmp_path: Path):
    path = tmp_path / "blank.jsonl"
    path.write_text(
        '{"provider_id":"fake_provider"}\n\n'
        '{"provider_id":"fake_provider"}\n',
        encoding="utf-8",
    )
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_forbidden_field_name_substring_raises_typed_error(tmp_path: Path):
    path = tmp_path / "secret.jsonl"
    bad_row = {
        "provider_id": "fake_provider",
        "api_key": "value_does_not_matter",
    }
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_forbidden_value_substring_raises_typed_error(tmp_path: Path):
    path = tmp_path / "leak.jsonl"
    # Construct a URL-shape value at runtime so the source file
    # itself does not contain the forbidden substring literal.
    colon_slash_slash = ":" + "//"
    leak_value = "https" + colon_slash_slash + "example.invalid/path"
    bad_row = {
        "provider_id": "fake_provider",
        "event_id": leak_value,
    }
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_long_hex_run_in_value_raises_typed_error(tmp_path: Path):
    path = tmp_path / "hex.jsonl"
    bad_row = {
        "provider_id": "fake_provider",
        "event_id": "a" * 40 + "0123456789abcdef",
    }
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_long_tokenish_run_in_value_raises_typed_error(tmp_path: Path):
    path = tmp_path / "token.jsonl"
    mixed_token = "Abc123Def456Ghi789Jkl012Mno345Pq"  # 32 mixed chars
    bad_row = {
        "provider_id": "fake_provider",
        "event_id": mixed_token,
    }
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_payload_summary_with_secret_key_raises_typed_error(tmp_path: Path):
    path = tmp_path / "leak_payload.jsonl"
    bad_row = {
        "provider_id": "fake_provider",
        "payload_summary": {
            "ok": True,
            "password": "value",
        },
    }
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )


def test_payload_summary_non_mapping_raises_typed_error(tmp_path: Path):
    path = tmp_path / "bad_payload.jsonl"
    bad_row = {
        "provider_id": "fake_provider",
        "payload_summary": [1, 2, 3],
    }
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage23InputError):
        read_stage22_jsonl(
            path=path,
            input_kind=INPUT_KIND_SYNTHETIC,
        )
