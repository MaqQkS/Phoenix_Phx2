"""Stage 24.1 input reader tests.

Pins:

  * Valid Stage 24-shaped decoded-tx JSONL fixtures project into
    ``Stage24ExecutionInput`` records.
  * Preserved fields are projected verbatim when present.
  * List fields are converted to tuples for NamedTuple
    immutability.
  * Optional fields absent on the row are tracked in
    ``missing_fields``.
  * Malformed JSONL raises ``Stage24InputError``.
  * Empty file returns the empty tuple.
  * Missing file raises ``Stage24InputError``.
  * Directory path raises ``Stage24InputError``.
  * Unknown ``input_kind`` raises ``Stage24InputError``.
  * Non-object row (JSON array / scalar) raises.
  * Secret-bearing field names raise (top-level and nested).
  * URL-shape values raise.
  * Long-hex credential-shape values raise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage24.constants import (
    DEFAULT_SCHEMA_VERSION,
    INPUT_KIND_DECODED_TX_JSONL,
    INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL,
)
from PHX2.stage24.errors import Stage24InputError
from PHX2.stage24.input_reader import read_stage24_tx_jsonl
from PHX2.tests.stage24.fixtures.builders import (
    make_decoded_tx_row,
    make_row_with_long_hex_credential,
    make_row_with_nested_secret_key,
    make_row_with_secret_field_name,
    make_row_with_url_value,
)


def _write_jsonl(*, path: Path, rows: list[dict[str, object]]) -> None:
    body = "\n".join(json.dumps(row) for row in rows)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_reads_valid_jsonl_fixture(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    rows = [
        make_decoded_tx_row(signature="sig_aaa", slot=100),
        make_decoded_tx_row(signature="sig_bbb", slot=101),
    ]
    _write_jsonl(path=path, rows=rows)

    inputs = read_stage24_tx_jsonl(
        path=path,
        input_kind=INPUT_KIND_DECODED_TX_JSONL,
    )

    assert len(inputs) == 2
    assert inputs[0].signature == "sig_aaa"
    assert inputs[0].slot == 100
    assert inputs[0].schema_version == DEFAULT_SCHEMA_VERSION
    assert inputs[0].input_kind == INPUT_KIND_DECODED_TX_JSONL
    assert inputs[1].signature == "sig_bbb"
    assert inputs[1].slot == 101


def test_empty_file_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    inputs = read_stage24_tx_jsonl(
        path=path,
        input_kind=INPUT_KIND_DECODED_TX_JSONL,
    )
    assert inputs == ()


def test_only_newlines_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "newlines.jsonl"
    path.write_text("\n\n\n", encoding="utf-8")
    inputs = read_stage24_tx_jsonl(
        path=path,
        input_kind=INPUT_KIND_DECODED_TX_JSONL,
    )
    assert inputs == ()


def test_list_fields_are_converted_to_tuples(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    rows = [
        make_decoded_tx_row(
            signature="sig_lists_001",
            account_keys=(
                "AccountA1111111111111111111111111111111111",
                "AccountB2222222222222222222222222222222222",
            ),
            pre_balances=(100, 200, 300),
            post_balances=(99, 199, 299),
            log_messages=("Program log: a", "Program log: b"),
        ),
    ]
    _write_jsonl(path=path, rows=rows)

    inputs = read_stage24_tx_jsonl(
        path=path,
        input_kind=INPUT_KIND_DECODED_TX_JSONL,
    )

    record = inputs[0]
    assert isinstance(record.account_keys, tuple)
    assert isinstance(record.pre_balances, tuple)
    assert isinstance(record.post_balances, tuple)
    assert isinstance(record.log_messages, tuple)
    assert isinstance(record.top_level_instructions, tuple)
    assert record.pre_balances == (100, 200, 300)
    assert record.post_balances == (99, 199, 299)


def test_payload_hash_is_populated_and_nonempty(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(path=path, rows=[make_decoded_tx_row()])
    inputs = read_stage24_tx_jsonl(
        path=path, input_kind=INPUT_KIND_DECODED_TX_JSONL
    )
    record = inputs[0]
    assert isinstance(record.payload_hash, str)
    # SHA-256 hex digest length is exactly 64.
    assert len(record.payload_hash) == 64


def test_input_id_derives_from_signature_when_present(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(
        path=path,
        rows=[make_decoded_tx_row(signature="sig_input_id_001")],
    )
    inputs = read_stage24_tx_jsonl(
        path=path, input_kind=INPUT_KIND_DECODED_TX_JSONL
    )
    assert inputs[0].input_id == "sig_input_id_001"


# ---------------------------------------------------------------------------
# Missing-fields tracking
# ---------------------------------------------------------------------------


def test_missing_fields_lists_absent_concepts(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    minimal_row: dict[str, object] = {
        "provider_id": "fake_provider",
        "signature": "sig_minimal_001",
    }
    _write_jsonl(path=path, rows=[minimal_row])
    inputs = read_stage24_tx_jsonl(
        path=path, input_kind=INPUT_KIND_DECODED_TX_JSONL
    )
    missing = set(inputs[0].missing_fields)
    # The minimal row omitted slot / slot_unix_time / observed_at_utc
    # / log_messages / meta and most balance / instruction lists.
    assert "slot" in missing
    assert "slot_unix_time" in missing
    assert "observed_at_utc" in missing
    assert "log_messages" in missing
    assert "meta" in missing
    assert "top_level_instructions" in missing


# ---------------------------------------------------------------------------
# Input-kind validation
# ---------------------------------------------------------------------------


def test_unknown_input_kind_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(path=path, rows=[make_decoded_tx_row()])
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(path=path, input_kind="not_a_real_kind")


def test_synthetic_input_kind_is_accepted(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(path=path, rows=[make_decoded_tx_row()])
    inputs = read_stage24_tx_jsonl(
        path=path, input_kind=INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL
    )
    assert len(inputs) == 1
    assert inputs[0].input_kind == INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL


# ---------------------------------------------------------------------------
# Path / file boundary
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=tmp_path / "nope.jsonl",
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_directory_path_raises(tmp_path: Path):
    directory = tmp_path / "subdir"
    directory.mkdir()
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=directory,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------


def test_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    path.write_text("not-json-not-at-all\n", encoding="utf-8")
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_non_object_row_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_intra_file_blank_line_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    body = (
        json.dumps(make_decoded_tx_row(signature="sig_a"))
        + "\n\n"
        + json.dumps(make_decoded_tx_row(signature="sig_b"))
        + "\n"
    )
    path.write_text(body, encoding="utf-8")
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


# ---------------------------------------------------------------------------
# Redaction discipline
# ---------------------------------------------------------------------------


def test_top_level_secret_field_name_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(path=path, rows=[make_row_with_secret_field_name()])
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_url_shape_value_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(path=path, rows=[make_row_with_url_value()])
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_long_hex_credential_value_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(
        path=path, rows=[make_row_with_long_hex_credential()]
    )
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_nested_secret_key_in_meta_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    _write_jsonl(
        path=path, rows=[make_row_with_nested_secret_key()]
    )
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


# ---------------------------------------------------------------------------
# Type-level field shape checks
# ---------------------------------------------------------------------------


def test_non_int_slot_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    bad_row: dict[str, object] = dict(make_decoded_tx_row())
    bad_row["slot"] = "not-an-int"
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_non_list_account_keys_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    bad_row: dict[str, object] = dict(make_decoded_tx_row())
    bad_row["account_keys"] = "not-a-list"
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )


def test_non_object_meta_raises(tmp_path: Path):
    path = tmp_path / "decoded.jsonl"
    bad_row: dict[str, object] = dict(make_decoded_tx_row())
    bad_row["meta"] = ["not", "an", "object"]
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage24InputError):
        read_stage24_tx_jsonl(
            path=path,
            input_kind=INPUT_KIND_DECODED_TX_JSONL,
        )
