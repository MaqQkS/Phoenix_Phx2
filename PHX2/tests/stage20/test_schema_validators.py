"""Tests for Stage 20 schema column validators (20.1.C).

Covers ``validate_stage18_review_matrix_columns`` (E2008),
``validate_stage19_ledger_columns`` (E2009), and the
``read_stage19_ledger_rows`` helper used by downstream taxonomy
checks.
"""

from __future__ import annotations

from PHX2.stage20.constants import EligibilityErrorCode
from PHX2.stage20.input_validators import (
    read_stage19_ledger_rows,
    validate_stage18_review_matrix_columns,
    validate_stage19_ledger_columns,
)
from PHX2.tests.stage20.fixtures.stage18_outputs import (
    write_minimal_stage18_dir,
    write_review_matrix,
)
from PHX2.tests.stage20.fixtures.stage19_outputs import (
    make_ledger_row,
    write_ledger,
    write_minimal_stage19_dir,
)


def test_valid_review_matrix_passes_column_check(tmp_path):
    s18 = tmp_path / "stage18"
    write_minimal_stage18_dir(s18)

    errors = validate_stage18_review_matrix_columns(s18 / "review_matrix.csv")
    assert errors == []


def test_review_matrix_missing_required_column_triggers_e2008(tmp_path):
    s18 = tmp_path / "stage18"
    s18.mkdir()
    # Header omits the required 'classification' column.
    short_columns = (
        "policy_hash",
        "rule_id",
        "window_seconds",
        "window_label",
        "stage17_label_preserved",
    )
    write_review_matrix(
        s18 / "review_matrix.csv", rows=(), columns=short_columns
    )

    errors = validate_stage18_review_matrix_columns(s18 / "review_matrix.csv")
    assert EligibilityErrorCode.E2008 in errors


def test_review_matrix_missing_file_triggers_e2008(tmp_path):
    errors = validate_stage18_review_matrix_columns(
        tmp_path / "nonexistent.csv"
    )
    assert EligibilityErrorCode.E2008 in errors


def test_valid_ledger_passes_column_check(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    errors = validate_stage19_ledger_columns(
        s19 / "operator_review_ledger.csv"
    )
    assert errors == []


def test_ledger_missing_required_column_triggers_e2009(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    short_columns = (
        "stage19_run_id",
        "ledger_row_id",
        "stage18_run_id",
    )
    write_ledger(
        s19 / "operator_review_ledger.csv", rows=(), columns=short_columns
    )

    errors = validate_stage19_ledger_columns(
        s19 / "operator_review_ledger.csv"
    )
    assert EligibilityErrorCode.E2009 in errors


def test_read_stage19_ledger_rows_returns_empty_for_header_only(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    write_ledger(s19 / "operator_review_ledger.csv", rows=())

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    assert rows == []


def test_read_stage19_ledger_rows_returns_dict_per_data_row(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    row = make_ledger_row(ledger_row_id="1111111111111111")
    write_ledger(s19 / "operator_review_ledger.csv", rows=[row])

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    assert len(rows) == 1
    assert rows[0]["ledger_row_id"] == "1111111111111111"
    assert rows[0]["review_label"] == "REVIEW_PROMISING_CONFIRMED"
