"""Stage 19 reader tests.

Covers all four readers:
  * read_stage18_manifest        -- E01, E02, E04, E05 + happy
  * read_stage18_review_matrix   -- E01, E03, E20, E21 + happy
  * read_operator_input          -- E06, E07, E08, E09, E13 + happy
  * read_prior_ledger            -- E16, E17, E18 + happy
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage19 import readers
from PHX2.stage19.constants import (
    LEDGER_COLUMNS,
    OPERATOR_INPUT_COLUMNS,
    STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS,
)
from PHX2.stage19.errors import Stage19ValidationError
from PHX2.stage19.ledger import LedgerRow
from PHX2.tests.stage19.fixtures import operator_inputs, stage18_outputs


# ===========================================================================
# Helpers
# ===========================================================================


def _ledger_csv(path: Path, rows: list[tuple[str, ...]]) -> None:
    """Write a Stage 19 ledger CSV with the locked 13-column header."""

    parts = [",".join(LEDGER_COLUMNS)]
    for row in rows:
        parts.append(",".join(row))
    path.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="")


def _ledger_csv_custom_header(
    path: Path, header: tuple[str, ...], rows: list[tuple[str, ...]]
) -> None:
    parts = [",".join(header)]
    for row in rows:
        parts.append(",".join(row))
    path.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="")


def _make_ledger_row(
    *,
    stage19_run_id: str = "stage19_run_aaaa",
    ledger_row_id: str = "0123456789abcdef",
    stage18_run_id: str = "0123456789abcdef",
    policy_hash: str = "abc123def456",
    rule_id: str = "rule_minimal",
    window_seconds: str = "3600",
    operator_id: str = "alice",
    review_sequence: str = "1",
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "concur",
    review_timestamp_utc: str = "2026-05-14T05:00:00Z",
    stage18_classification: str = "PROMISING_REVIEW",
    stage17_label_preserved: str = "PROMISING",
) -> tuple[str, ...]:
    return (
        stage19_run_id,
        ledger_row_id,
        stage18_run_id,
        policy_hash,
        rule_id,
        window_seconds,
        operator_id,
        review_sequence,
        review_label,
        review_notes,
        review_timestamp_utc,
        stage18_classification,
        stage17_label_preserved,
    )


def _write_prior_ledger_dir(
    target_dir: Path,
    *,
    rows: list[tuple[str, ...]] | None = None,
    schema_version: str = "stage19_ledger_v1",
    omit_ledger: bool = False,
    omit_manifest: bool = False,
    bad_manifest_json: bool = False,
    custom_ledger_header: tuple[str, ...] | None = None,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    if not omit_manifest:
        if bad_manifest_json:
            (target_dir / "manifest.json").write_text(
                "not valid json {{{", encoding="utf-8"
            )
        else:
            payload = {
                "stage19_schema_version": schema_version,
                "stage19_version": "0.1.0",
                "stage19_run_id": "stage19_run_aaaa",
            }
            (target_dir / "manifest.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
    if not omit_ledger:
        ledger_rows = rows if rows is not None else [_make_ledger_row()]
        if custom_ledger_header is not None:
            _ledger_csv_custom_header(
                target_dir / "operator_review_ledger.csv",
                custom_ledger_header,
                ledger_rows,
            )
        else:
            _ledger_csv(target_dir / "operator_review_ledger.csv", ledger_rows)
    return target_dir


# ===========================================================================
# read_stage18_manifest
# ===========================================================================


class TestReadStage18ManifestHappy:
    def test_well_formed_manifest_parses(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(d)
        result = readers.read_stage18_manifest(d)
        assert result.schema_version == "stage18_run_manifest_v0"
        assert result.run_id == "0123456789abcdef"

    def test_manifest_with_extra_keys_parses(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(
            d / "manifest.json",
            extra_fields={"some_other_field": "value", "nested": {"k": 1}},
        )
        result = readers.read_stage18_manifest(d)
        assert result.run_id == "0123456789abcdef"

    def test_manifest_returns_typed_namedtuple(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(d)
        result = readers.read_stage18_manifest(d)
        assert isinstance(result, readers.Stage18ManifestData)
        assert hasattr(result, "schema_version")
        assert hasattr(result, "run_id")


class TestReadStage18ManifestE01:
    def test_non_existent_dir_raises_e01(self, tmp_path: Path) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(tmp_path / "missing_dir")
        assert excinfo.value.code == "E01"

    def test_file_path_instead_of_dir_raises_e01(self, tmp_path: Path) -> None:
        f = tmp_path / "regular.txt"
        f.write_text("hi")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(f)
        assert excinfo.value.code == "E01"


class TestReadStage18ManifestE02:
    def test_dir_exists_but_manifest_absent_raises_e02(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18_no_manifest"
        d.mkdir()
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E02"

    def test_manifest_is_directory_raises_e02(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        (d / "manifest.json").mkdir()
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E02"


class TestReadStage18ManifestE04:
    def test_malformed_json_raises_e04(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(
            d / "manifest.json", raw_text="not valid json {{{ "
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E04"

    def test_manifest_is_json_array_not_object_raises_e04(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(
            d / "manifest.json", raw_text='["not", "an", "object"]'
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E04"

    def test_missing_schema_version_raises_e04(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        # Build a manifest then strip schema_version
        stage18_outputs.write_manifest(d / "manifest.json")
        payload = json.loads((d / "manifest.json").read_text())
        del payload["schema_version"]
        (d / "manifest.json").write_text(json.dumps(payload))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E04"

    def test_missing_run_id_raises_e04(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json", omit_run_id=True)
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E04"

    def test_run_id_not_a_string_raises_e04(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        payload = json.loads((d / "manifest.json").read_text())
        payload["run_id"] = 12345  # int instead of str
        (d / "manifest.json").write_text(json.dumps(payload))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E04"


class TestReadStage18ManifestE05:
    def test_wrong_schema_version_v1_raises_e05(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(
            d / "manifest.json", schema_version="stage18_run_manifest_v1"
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E05"

    def test_completely_unrelated_schema_version_raises_e05(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(
            d / "manifest.json", schema_version="something_else_v0"
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_manifest(d)
        assert excinfo.value.code == "E05"


# ===========================================================================
# read_stage18_review_matrix
# ===========================================================================


class TestReadStage18ReviewMatrixHappy:
    def test_well_formed_review_matrix_parses(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(d)
        index = readers.read_stage18_review_matrix(d)
        assert len(index) == 1
        key = ("abc123def456", "rule_minimal", 3600)
        assert key in index
        record = index[key]
        assert record.stage18_classification == "HARMFUL_REVIEW"
        assert record.stage17_label_preserved == "HARMFUL"
        assert record.window_seconds == 3600
        assert isinstance(record.window_seconds, int)

    def test_review_matrix_index_keyed_by_int_window(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        stage18_outputs.write_minimal_valid_stage18_output(d)
        index = readers.read_stage18_review_matrix(d)
        # The window_seconds component of the key is an int, not str
        for key in index.keys():
            assert isinstance(key[2], int)

    def test_three_rows_parse_into_three_records(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        rows = [
            stage18_outputs.make_review_row(
                policy_hash="hash_a",
                rule_id="rule_a",
                window_seconds="60",
                classification="PROMISING_REVIEW",
                stage17_label_preserved="PROMISING",
            ),
            stage18_outputs.make_review_row(
                policy_hash="hash_a",
                rule_id="rule_b",
                window_seconds="3600",
                classification="WEAK_REVIEW",
                stage17_label_preserved="WEAK",
            ),
            stage18_outputs.make_review_row(
                policy_hash="hash_c",
                rule_id="rule_c",
                window_seconds="86400",
                classification="HARMFUL_REVIEW",
                stage17_label_preserved="HARMFUL",
            ),
        ]
        stage18_outputs.write_review_matrix(d / "review_matrix.csv", rows)
        index = readers.read_stage18_review_matrix(d)
        assert len(index) == 3
        assert ("hash_a", "rule_a", 60) in index
        assert ("hash_a", "rule_b", 3600) in index
        assert ("hash_c", "rule_c", 86400) in index

    def test_duplicate_key_later_row_wins(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        first = stage18_outputs.make_review_row(
            classification="WEAK_REVIEW", stage17_label_preserved="WEAK"
        )
        second = stage18_outputs.make_review_row(
            classification="HARMFUL_REVIEW", stage17_label_preserved="HARMFUL"
        )
        # Same slice key (default), different classification
        stage18_outputs.write_review_matrix(
            d / "review_matrix.csv", [first, second]
        )
        index = readers.read_stage18_review_matrix(d)
        key = ("abc123def456", "rule_minimal", 3600)
        assert index[key].stage18_classification == "HARMFUL_REVIEW"


class TestReadStage18ReviewMatrixE01:
    def test_non_existent_dir_raises_e01(self, tmp_path: Path) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(tmp_path / "missing")
        assert excinfo.value.code == "E01"

    def test_file_path_instead_of_dir_raises_e01(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hi")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(f)
        assert excinfo.value.code == "E01"


class TestReadStage18ReviewMatrixE03:
    def test_dir_exists_manifest_present_review_matrix_absent_raises_e03(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E03"


class TestReadStage18ReviewMatrixE20:
    def test_header_missing_tier_coverage_raises_e20(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        bad_header = tuple(
            c for c in STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS
            if c != "tier_coverage"
        )
        stage18_outputs.write_review_matrix_with_header(
            d / "review_matrix.csv", bad_header
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E20"

    def test_header_columns_in_wrong_order_raises_e20(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        bad_header = (
            "rule_id",
            "policy_hash",
        ) + STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS[2:]
        stage18_outputs.write_review_matrix_with_header(
            d / "review_matrix.csv", bad_header
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E20"

    def test_header_has_extra_column_raises_e20(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        bad_header = STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS + ("extra_col",)
        stage18_outputs.write_review_matrix_with_header(
            d / "review_matrix.csv", bad_header
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E20"

    def test_empty_review_matrix_file_raises_e20(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        (d / "review_matrix.csv").write_text("", encoding="utf-8")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E20"


class TestReadStage18ReviewMatrixE21:
    def test_row_wrong_column_count_raises_e21(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        # Build a CSV with the correct header but a too-short row.
        header = ",".join(STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS)
        short_row = ",".join(["only", "three", "cells"])
        (d / "review_matrix.csv").write_text(
            f"{header}\n{short_row}\n", encoding="utf-8"
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E21"

    def test_window_seconds_unparseable_raises_e21(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        bad_row = stage18_outputs.make_review_row(window_seconds="abc")
        stage18_outputs.write_review_matrix(d / "review_matrix.csv", [bad_row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E21"

    def test_window_seconds_zero_raises_e21(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        bad_row = stage18_outputs.make_review_row(window_seconds="0")
        stage18_outputs.write_review_matrix(d / "review_matrix.csv", [bad_row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E21"

    def test_classification_invalid_raises_e21(self, tmp_path: Path) -> None:
        d = tmp_path / "s18"
        d.mkdir()
        stage18_outputs.write_manifest(d / "manifest.json")
        bad_row = stage18_outputs.make_review_row(
            classification="INVALID_REVIEW"
        )
        stage18_outputs.write_review_matrix(d / "review_matrix.csv", [bad_row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_stage18_review_matrix(d)
        assert excinfo.value.code == "E21"


# ===========================================================================
# read_operator_input
# ===========================================================================


class TestReadOperatorInputHappy:
    def test_minimal_valid_input_returns_one_row(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        operator_inputs.write_minimal_valid_operator_input(path)
        rows = readers.read_operator_input(path)
        assert len(rows) == 1
        assert rows[0].review_label == "REVIEW_PROMISING_CONFIRMED"
        assert isinstance(rows[0].window_seconds, int)
        assert rows[0].window_seconds == 3600

    def test_three_rows_returns_three_records(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        rows_input = [
            operator_inputs.make_operator_row(rule_id="rule_a"),
            operator_inputs.make_operator_row(
                rule_id="rule_b", review_label="WATCHLIST"
            ),
            operator_inputs.make_operator_row(
                rule_id="rule_c", review_label="INCONCLUSIVE"
            ),
        ]
        operator_inputs.write_minimal_valid_operator_input(path, rows=rows_input)
        rows = readers.read_operator_input(path)
        assert len(rows) == 3
        assert [r.rule_id for r in rows] == ["rule_a", "rule_b", "rule_c"]

    def test_header_only_returns_empty_list(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        operator_inputs.write_header_only_operator_input(path)
        rows = readers.read_operator_input(path)
        assert rows == []

    def test_id_fields_stripped(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(
            stage18_run_id="  0123456789abcdef  ",
            policy_hash="  abc123def456  ",
            rule_id="  rule_minimal  ",
            window_seconds="  3600  ",
        )
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        rows = readers.read_operator_input(path)
        assert rows[0].stage18_run_id == "0123456789abcdef"
        assert rows[0].policy_hash == "abc123def456"
        assert rows[0].rule_id == "rule_minimal"

    def test_review_notes_leading_trailing_whitespace_preserved(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(
            review_notes="  notes with leading/trailing space  "
        )
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        rows = readers.read_operator_input(path)
        assert rows[0].review_notes == "  notes with leading/trailing space  "

    def test_review_notes_with_commas_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        # Use header-only write then csv module via minimal writer
        # The fixture uses naive ',' join, so we hit that limitation with commas;
        # use Python csv module directly for this test.
        import csv as csvmod
        notes_with_commas = "first, second, third"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes_with_commas,
            ))
        rows = readers.read_operator_input(path)
        assert rows[0].review_notes == notes_with_commas

    def test_review_notes_with_double_quotes_round_trips(
        self, tmp_path: Path
    ) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = 'they said "go" and i said "no"'
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        rows = readers.read_operator_input(path)
        assert rows[0].review_notes == notes

    def test_review_notes_with_utf8_non_ascii_round_trips(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "op.csv"
        notes = "café — déjà vu — naïve"
        row = operator_inputs.make_operator_row(review_notes=notes)
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        rows = readers.read_operator_input(path)
        assert rows[0].review_notes == notes


class TestReadOperatorInputE06:
    def test_missing_file_raises_e06(self, tmp_path: Path) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(tmp_path / "missing.csv")
        assert excinfo.value.code == "E06"


class TestReadOperatorInputE07:
    def test_extra_column_raises_e07(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        operator_inputs.write_operator_input_with_header(
            path, OPERATOR_INPUT_COLUMNS + ("extra",)
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E07"

    def test_missing_column_raises_e07(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        operator_inputs.write_operator_input_with_header(
            path, OPERATOR_INPUT_COLUMNS[:-1]
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E07"

    def test_wrong_order_raises_e07(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        # Swap policy_hash and rule_id positions
        bad_header = (
            "stage18_run_id",
            "rule_id",
            "policy_hash",
            "window_seconds",
            "review_label",
            "review_notes",
        )
        operator_inputs.write_operator_input_with_header(path, bad_header)
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E07"

    def test_renamed_column_raises_e07(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        bad_header = tuple(
            "operator_decision" if c == "review_label" else c
            for c in OPERATOR_INPUT_COLUMNS
        )
        operator_inputs.write_operator_input_with_header(path, bad_header)
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E07"


class TestReadOperatorInputE08:
    def test_short_row_raises_e08(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        operator_inputs.write_operator_input_with_short_row(
            path, ("just", "two")
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E08"

    def test_empty_policy_hash_raises_e08(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(policy_hash="")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E08"

    def test_window_seconds_abc_raises_e08(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(window_seconds="abc")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E08"

    def test_window_seconds_zero_raises_e08(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(window_seconds="0")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E08"

    def test_window_seconds_negative_raises_e08(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(window_seconds="-5")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E08"

    def test_empty_run_id_after_strip_raises_e08(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(stage18_run_id="   ")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E08"


class TestReadOperatorInputE09:
    def test_legacy_agree_label_raises_e09(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(review_label="AGREE")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E09"

    def test_empty_label_raises_e09(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(review_label="")
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E09"

    def test_lowercase_label_raises_e09(self, tmp_path: Path) -> None:
        path = tmp_path / "op.csv"
        row = operator_inputs.make_operator_row(
            review_label="review_promising_confirmed"
        )
        operator_inputs.write_minimal_valid_operator_input(path, rows=[row])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E09"


class TestReadOperatorInputE13:
    def test_oversize_notes_raises_e13(self, tmp_path: Path) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = operator_inputs.make_oversize_review_notes(length=2001)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E13"

    def test_notes_with_tab_raises_e13(self, tmp_path: Path) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = "tab here:\there"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E13"

    def test_notes_with_newline_raises_e13(self, tmp_path: Path) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = "line one\nline two"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E13"

    def test_notes_with_carriage_return_raises_e13(
        self, tmp_path: Path
    ) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = "line one\rline two"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E13"

    def test_notes_with_null_byte_raises_e13(self, tmp_path: Path) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = "null:\x00here"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E13"

    def test_notes_with_del_raises_e13(self, tmp_path: Path) -> None:
        import csv as csvmod
        path = tmp_path / "op.csv"
        notes = "del:\x7fhere"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csvmod.writer(f)
            writer.writerow(OPERATOR_INPUT_COLUMNS)
            writer.writerow((
                "0123456789abcdef",
                "abc123def456",
                "rule_minimal",
                "3600",
                "REVIEW_PROMISING_CONFIRMED",
                notes,
            ))
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_operator_input(path)
        assert excinfo.value.code == "E13"


# ===========================================================================
# read_prior_ledger
# ===========================================================================


class TestReadPriorLedgerHappy:
    def test_one_row_parses_successfully(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d)
        rows, manifest = readers.read_prior_ledger(d)
        assert len(rows) == 1
        assert isinstance(rows[0], LedgerRow)
        assert manifest["stage19_schema_version"] == "stage19_ledger_v1"

    def test_five_rows_parse_in_source_order(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        rows_in = [
            _make_ledger_row(rule_id=f"rule_{i}", review_sequence=str(i + 1))
            for i in range(5)
        ]
        _write_prior_ledger_dir(d, rows=rows_in)
        rows, _ = readers.read_prior_ledger(d)
        assert len(rows) == 5

    def test_review_sequence_returned_as_int(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(
            d, rows=[_make_ledger_row(review_sequence="42")]
        )
        rows, _ = readers.read_prior_ledger(d)
        assert isinstance(rows[0].review_sequence, int)
        assert rows[0].review_sequence == 42

    def test_window_seconds_returned_as_int(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(
            d, rows=[_make_ledger_row(window_seconds="86400")]
        )
        rows, _ = readers.read_prior_ledger(d)
        assert isinstance(rows[0].window_seconds, int)
        assert rows[0].window_seconds == 86400

    def test_manifest_dict_returned_intact(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d)
        _, manifest = readers.read_prior_ledger(d)
        assert "stage19_run_id" in manifest
        assert manifest["stage19_run_id"] == "stage19_run_aaaa"

    def test_returns_tuple_of_list_and_dict(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d)
        result = readers.read_prior_ledger(d)
        assert isinstance(result, tuple)
        assert len(result) == 2
        rows, manifest = result
        assert isinstance(rows, list)
        assert isinstance(manifest, dict)


class TestReadPriorLedgerE16:
    def test_missing_ledger_csv_raises_e16(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d, omit_ledger=True)
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E16"

    def test_missing_manifest_raises_e16(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d, omit_manifest=True)
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E16"

    def test_missing_both_raises_e16(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        d.mkdir()
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E16"

    def test_non_existent_path_raises_e16(self, tmp_path: Path) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(tmp_path / "missing")
        assert excinfo.value.code == "E16"

    def test_path_is_file_raises_e16(self, tmp_path: Path) -> None:
        f = tmp_path / "regular.txt"
        f.write_text("hi")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(f)
        assert excinfo.value.code == "E16"


class TestReadPriorLedgerE17:
    def test_schema_v0_raises_e17(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d, schema_version="stage19_ledger_v0")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E17"

    def test_schema_v2_raises_e17(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d, schema_version="stage19_ledger_v2")
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E17"

    def test_bad_manifest_json_raises_e17(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(d, bad_manifest_json=True)
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E17"


class TestReadPriorLedgerE18:
    def test_bad_header_raises_e18(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        _write_prior_ledger_dir(
            d,
            custom_ledger_header=("only", "two", "columns"),
            rows=[],
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"

    def test_wrong_column_count_raises_e18(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        d.mkdir()
        # Valid manifest
        _write_prior_ledger_dir(d, omit_ledger=True)
        # Custom-write a ledger with a too-short row
        header = ",".join(LEDGER_COLUMNS)
        short_row = ",".join(["a", "b", "c"])
        (d / "operator_review_ledger.csv").write_text(
            f"{header}\n{short_row}\n", encoding="utf-8"
        )
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"

    def test_unparseable_review_sequence_raises_e18(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "prior"
        bad = _make_ledger_row(review_sequence="abc")
        _write_prior_ledger_dir(d, rows=[bad])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"

    def test_invalid_review_label_raises_e18(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        bad = _make_ledger_row(review_label="NOT_A_REAL_LABEL")
        _write_prior_ledger_dir(d, rows=[bad])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"

    def test_bad_timestamp_format_raises_e18(self, tmp_path: Path) -> None:
        d = tmp_path / "prior"
        bad = _make_ledger_row(review_timestamp_utc="2026-05-14 05:00:00")
        _write_prior_ledger_dir(d, rows=[bad])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"

    def test_non_positive_window_seconds_raises_e18(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "prior"
        bad = _make_ledger_row(window_seconds="0")
        _write_prior_ledger_dir(d, rows=[bad])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"

    def test_non_positive_review_sequence_raises_e18(
        self, tmp_path: Path
    ) -> None:
        d = tmp_path / "prior"
        bad = _make_ledger_row(review_sequence="0")
        _write_prior_ledger_dir(d, rows=[bad])
        with pytest.raises(Stage19ValidationError) as excinfo:
            readers.read_prior_ledger(d)
        assert excinfo.value.code == "E18"
