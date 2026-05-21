"""Stage 25.1 input reader tests.

Pins:

  * Valid Stage 25-shaped migration-observation / price-observation
    JSONL fixtures project into the corresponding observation
    records.
  * Required fields (``token_mint`` / ``provider_id``) absent on a
    row raise ``Stage25InputError``.
  * Optional closed-set tokens default to the locked
    ``UNKNOWN_SOURCE`` / ``ABSENT`` / ``UNKNOWN_QUOTE`` tokens.
  * Optional fields absent on the row are tracked in
    ``input_missing_fields``.
  * Malformed JSONL raises ``Stage25InputError``.
  * Empty file returns the empty tuple.
  * Missing file raises.
  * Directory path raises.
  * Unknown ``input_kind`` raises.
  * Calling the migration reader with a price ``input_kind`` raises.
  * Calling the price reader with a migration ``input_kind`` raises.
  * Non-object row raises.
  * Intra-file blank line raises.
  * Secret-bearing field names raise (top-level and nested).
  * URL-shape values raise.
  * Long-hex credential-shape values raise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage25.constants import (
    DEFAULT_SCHEMA_VERSION,
    INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL,
    INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL,
    QUOTE_DENOMINATION_UNKNOWN_QUOTE,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    SOURCE_FAMILY_UNKNOWN_SOURCE,
    SOURCE_STATUS_ABSENT,
)
from PHX2.stage25.errors import Stage25InputError
from PHX2.stage25.input_reader import (
    read_stage25_migration_observations_jsonl,
    read_stage25_price_observations_jsonl,
    stage25_input_default_schema_version,
)
from PHX2.tests.stage25.fixtures.builders import (
    make_migration_observation_row,
    make_migration_row_with_long_hex_credential,
    make_migration_row_with_nested_secret_key,
    make_migration_row_with_secret_field_name,
    make_migration_row_with_url_value,
    make_price_observation_row,
    make_price_row_with_secret_field_name,
    make_price_row_with_url_value,
)


def _write_jsonl(*, path: Path, rows: list[dict[str, object]]) -> None:
    body = "\n".join(json.dumps(row) for row in rows)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# schema-version helper
# ---------------------------------------------------------------------------


def test_default_schema_version_matches_constants():
    assert stage25_input_default_schema_version() == DEFAULT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Migration reader happy path
# ---------------------------------------------------------------------------


def test_reads_valid_migration_jsonl_fixture(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    rows = [
        make_migration_observation_row(
            token_mint="MintAaa11111111111111111111111111111111111",
            slot=100,
        ),
        make_migration_observation_row(
            token_mint="MintBbb22222222222222222222222222222222222",
            slot=101,
        ),
    ]
    _write_jsonl(path=path, rows=rows)

    observations = read_stage25_migration_observations_jsonl(
        path=path,
        input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
    )

    assert len(observations) == 2
    assert observations[0].token_mint == "MintAaa11111111111111111111111111111111111"
    assert observations[0].slot == 100
    assert observations[1].slot == 101


def test_migration_empty_file_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    observations = read_stage25_migration_observations_jsonl(
        path=path, input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL
    )
    assert observations == ()


def test_migration_only_newlines_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "newlines.jsonl"
    path.write_text("\n\n\n", encoding="utf-8")
    observations = read_stage25_migration_observations_jsonl(
        path=path, input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL
    )
    assert observations == ()


def test_migration_observation_hash_is_populated(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(path=path, rows=[make_migration_observation_row()])
    observations = read_stage25_migration_observations_jsonl(
        path=path, input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL
    )
    record = observations[0]
    assert isinstance(record.observation_hash, str)
    assert len(record.observation_hash) == 64


def test_synthetic_migration_input_kind_is_accepted(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(path=path, rows=[make_migration_observation_row()])
    observations = read_stage25_migration_observations_jsonl(
        path=path,
        input_kind=INPUT_KIND_SYNTHETIC_MIGRATION_OBSERVATIONS_JSONL,
    )
    assert len(observations) == 1


# ---------------------------------------------------------------------------
# Price reader happy path
# ---------------------------------------------------------------------------


def test_reads_valid_price_jsonl_fixture(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    rows = [
        make_price_observation_row(slot=200, price=111),
        make_price_observation_row(slot=201, price=222),
    ]
    _write_jsonl(path=path, rows=rows)

    observations = read_stage25_price_observations_jsonl(
        path=path,
        input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
    )

    assert len(observations) == 2
    assert observations[0].slot == 200
    assert observations[0].price == 111
    assert observations[1].price == 222


def test_price_empty_file_returns_empty_tuple(tmp_path: Path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    observations = read_stage25_price_observations_jsonl(
        path=path, input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL
    )
    assert observations == ()


def test_synthetic_price_input_kind_is_accepted(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(path=path, rows=[make_price_observation_row()])
    observations = read_stage25_price_observations_jsonl(
        path=path,
        input_kind=INPUT_KIND_SYNTHETIC_PRICE_OBSERVATIONS_JSONL,
    )
    assert len(observations) == 1


def test_price_observation_with_null_price_projects_to_none(tmp_path: Path):
    """A non-PRESENT source may legitimately project a ``None`` price.

    PRESENT + ``None`` is a contract violation (see
    ``test_price_observation_present_with_null_price_raises``);
    this test pins the negative-status path.
    """
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[
            make_price_observation_row(
                price=None, source_status=SOURCE_STATUS_ABSENT
            )
        ],
    )
    observations = read_stage25_price_observations_jsonl(
        path=path, input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL
    )
    assert observations[0].price is None
    assert observations[0].source_status == SOURCE_STATUS_ABSENT


# ---------------------------------------------------------------------------
# Default-token behavior for absent closed-set fields
# ---------------------------------------------------------------------------


def test_migration_row_without_source_family_defaults_to_unknown_source(
    tmp_path: Path,
):
    path = tmp_path / "migration.jsonl"
    minimal_row: dict[str, object] = {
        "token_mint": "MintMin111111111111111111111111111111111111",
        "provider_id": "provider",
    }
    _write_jsonl(path=path, rows=[minimal_row])
    observations = read_stage25_migration_observations_jsonl(
        path=path, input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL
    )
    record = observations[0]
    assert record.source_family == SOURCE_FAMILY_UNKNOWN_SOURCE
    assert record.source_status == SOURCE_STATUS_ABSENT
    assert record.slot == -1
    assert record.block_time == -1


def test_price_row_without_quote_defaults_to_unknown_quote(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    minimal_row: dict[str, object] = {
        "token_mint": "MintMin111111111111111111111111111111111111",
        "provider_id": "provider",
    }
    _write_jsonl(path=path, rows=[minimal_row])
    observations = read_stage25_price_observations_jsonl(
        path=path, input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL
    )
    record = observations[0]
    assert record.quote_denomination == QUOTE_DENOMINATION_UNKNOWN_QUOTE
    assert record.price is None


# ---------------------------------------------------------------------------
# Missing-field tracking
# ---------------------------------------------------------------------------


def test_missing_fields_lists_absent_concepts(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    minimal_row: dict[str, object] = {
        "token_mint": "MintMin111111111111111111111111111111111111",
        "provider_id": "provider",
    }
    _write_jsonl(path=path, rows=[minimal_row])
    observations = read_stage25_migration_observations_jsonl(
        path=path, input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL
    )
    missing = set(observations[0].input_missing_fields)
    assert "source_family" in missing
    assert "source_status" in missing
    assert "slot" in missing
    assert "block_time" in missing
    assert "observed_at_utc" in missing
    assert "evidence" in missing


# ---------------------------------------------------------------------------
# Required-field enforcement
# ---------------------------------------------------------------------------


def test_migration_row_without_token_mint_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    bad_row: dict[str, object] = dict(make_migration_observation_row())
    del bad_row["token_mint"]
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_migration_row_without_provider_id_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    bad_row: dict[str, object] = dict(make_migration_observation_row())
    del bad_row["provider_id"]
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_price_row_without_token_mint_raises(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    bad_row: dict[str, object] = dict(make_price_observation_row())
    del bad_row["token_mint"]
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


# ---------------------------------------------------------------------------
# Input-kind validation
# ---------------------------------------------------------------------------


def test_unknown_input_kind_raises_migration_reader(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(path=path, rows=[make_migration_observation_row()])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path, input_kind="not_a_real_kind"
        )


def test_unknown_input_kind_raises_price_reader(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(path=path, rows=[make_price_observation_row()])
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path, input_kind="not_a_real_kind"
        )


def test_migration_reader_rejects_price_input_kind(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(path=path, rows=[make_migration_observation_row()])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_price_reader_rejects_migration_input_kind(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(path=path, rows=[make_price_observation_row()])
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


# ---------------------------------------------------------------------------
# Path / file boundary
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=tmp_path / "nope.jsonl",
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_directory_path_raises(tmp_path: Path):
    directory = tmp_path / "subdir"
    directory.mkdir()
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=directory,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------


def test_malformed_json_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    path.write_text("not-json-at-all\n", encoding="utf-8")
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_non_object_row_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_intra_file_blank_line_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    body = (
        json.dumps(make_migration_observation_row(slot=10))
        + "\n\n"
        + json.dumps(make_migration_observation_row(slot=11))
        + "\n"
    )
    path.write_text(body, encoding="utf-8")
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


# ---------------------------------------------------------------------------
# Redaction discipline
# ---------------------------------------------------------------------------


def test_top_level_secret_field_name_raises_migration(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(
        path=path, rows=[make_migration_row_with_secret_field_name()]
    )
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_top_level_secret_field_name_raises_price(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path, rows=[make_price_row_with_secret_field_name()]
    )
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_url_shape_value_raises_migration(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(path=path, rows=[make_migration_row_with_url_value()])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_url_shape_value_raises_price(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(path=path, rows=[make_price_row_with_url_value()])
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_long_hex_credential_value_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(
        path=path, rows=[make_migration_row_with_long_hex_credential()]
    )
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_nested_secret_key_in_evidence_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(
        path=path, rows=[make_migration_row_with_nested_secret_key()]
    )
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


# ---------------------------------------------------------------------------
# Type-level field shape checks
# ---------------------------------------------------------------------------


def test_non_int_slot_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    bad_row: dict[str, object] = dict(make_migration_observation_row())
    bad_row["slot"] = "not-an-int"
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_non_object_evidence_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    bad_row: dict[str, object] = dict(make_migration_observation_row())
    bad_row["evidence"] = ["not", "an", "object"]
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_negative_price_raises(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    bad_row: dict[str, object] = dict(make_price_observation_row())
    bad_row["price"] = -100
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_bool_price_raises(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    bad_row: dict[str, object] = dict(make_price_observation_row())
    bad_row["price"] = True
    _write_jsonl(path=path, rows=[bad_row])
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


# ---------------------------------------------------------------------------
# Model-validator-backed reader rejections (no validation bypass)
# ---------------------------------------------------------------------------
#
# The Stage 25.1 reader projects raw row dicts and then delegates
# every observation construction to the validating model helpers
# (``build_migration_observation`` / ``build_price_observation``).
# A row that passes shape projection but violates a closed-set /
# price / sentinel invariant raises ``Stage25InputError`` at the
# reader boundary because the reader catches ``Stage25ContractError``
# from the model layer and re-raises it. The following tests pin
# that the reader does NOT bypass validation.


def test_price_observation_present_with_null_price_raises(tmp_path: Path):
    """PRESENT means the source observed the price; ``None`` is illegal.

    The row passes raw projection (``price`` is None, which is a
    legal optional int). The model validator rejects it because
    PRESENT requires a non-negative int. The reader must re-raise
    as ``Stage25InputError``.
    """
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[make_price_observation_row(price=None)],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_price_observation_zero_without_explicit_reason_raises(tmp_path: Path):
    """price=0 requires the explicit ``PRICE_OBSERVED_ZERO`` reason."""
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[make_price_observation_row(price=0)],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_price_observation_zero_with_explicit_reason_is_accepted(tmp_path: Path):
    """price=0 with the explicit reason code projects cleanly."""
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[
            make_price_observation_row(
                price=0,
                reason_codes=(REASON_CODE_PRICE_OBSERVED_ZERO,),
            )
        ],
    )
    observations = read_stage25_price_observations_jsonl(
        path=path,
        input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
    )
    assert observations[0].price == 0
    assert REASON_CODE_PRICE_OBSERVED_ZERO in observations[0].reason_codes


def test_price_observation_unknown_source_status_raises(tmp_path: Path):
    """The model validator's closed-set check rejects unknown source_status."""
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[make_price_observation_row(source_status="BOGUS_STATUS")],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_price_observation_unknown_source_family_raises(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[make_price_observation_row(source_family="BOGUS_FAMILY")],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_price_observation_unknown_quote_denomination_raises(tmp_path: Path):
    path = tmp_path / "price.jsonl"
    _write_jsonl(
        path=path,
        rows=[
            make_price_observation_row(quote_denomination="BOGUS_QUOTE")
        ],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_price_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_PRICE_OBSERVATIONS_JSONL,
        )


def test_migration_observation_unknown_source_status_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(
        path=path,
        rows=[
            make_migration_observation_row(source_status="BOGUS_STATUS")
        ],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )


def test_migration_observation_unknown_source_family_raises(tmp_path: Path):
    path = tmp_path / "migration.jsonl"
    _write_jsonl(
        path=path,
        rows=[
            make_migration_observation_row(source_family="BOGUS_FAMILY")
        ],
    )
    with pytest.raises(Stage25InputError):
        read_stage25_migration_observations_jsonl(
            path=path,
            input_kind=INPUT_KIND_MIGRATION_OBSERVATIONS_JSONL,
        )
