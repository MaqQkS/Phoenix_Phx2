"""Tests for Stage 20 label-taxonomy validators (20.1.C).

Covers:
  * validate_stage19_operator_labels  (E2005, E2007)
  * validate_stage19_ledger_row_id_uniqueness  (E2006, renamed)
  * verify_eligibility_taxonomy_completeness  (E2010)
"""

from __future__ import annotations

from PHX2.stage20.constants import EligibilityErrorCode
from PHX2.stage20.input_validators import (
    read_stage19_ledger_rows,
    validate_stage19_ledger_row_id_uniqueness,
    validate_stage19_operator_labels,
    verify_eligibility_taxonomy_completeness,
)
from PHX2.tests.stage20.fixtures.stage18_outputs import (
    write_minimal_stage18_dir,
)
from PHX2.tests.stage20.fixtures.stage19_outputs import (
    make_ledger_row,
    write_ledger,
    write_minimal_stage19_dir,
)


def test_valid_labels_pass(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    errors = validate_stage19_operator_labels(rows)
    assert errors == []


def test_unknown_label_triggers_e2005(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    bad_row = make_ledger_row(
        ledger_row_id="aaaa111122223333",
        review_label="MAYBE_PROMISING",  # not in mapping
    )
    write_ledger(s19 / "operator_review_ledger.csv", rows=[bad_row])

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    errors = validate_stage19_operator_labels(rows)
    assert EligibilityErrorCode.E2005 in errors


def test_empty_label_triggers_e2007(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    bad_row = make_ledger_row(
        ledger_row_id="bbbb111122223333",
        review_label="",
    )
    write_ledger(s19 / "operator_review_ledger.csv", rows=[bad_row])

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    errors = validate_stage19_operator_labels(rows)
    assert EligibilityErrorCode.E2007 in errors


def test_duplicate_ledger_row_id_triggers_e2006(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    duplicate_id = "abc1234567890def"
    row1 = make_ledger_row(ledger_row_id=duplicate_id, review_sequence="1")
    row2 = make_ledger_row(
        ledger_row_id=duplicate_id,
        review_sequence="2",
        review_label="WATCHLIST",
    )
    write_ledger(s19 / "operator_review_ledger.csv", rows=[row1, row2])

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    errors = validate_stage19_ledger_row_id_uniqueness(rows)
    assert EligibilityErrorCode.E2006 in errors


def test_unique_ledger_row_ids_pass(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()
    row1 = make_ledger_row(ledger_row_id="aaaaaaaaaaaaaaaa")
    row2 = make_ledger_row(
        ledger_row_id="bbbbbbbbbbbbbbbb", review_sequence="2"
    )
    write_ledger(s19 / "operator_review_ledger.csv", rows=[row1, row2])

    rows = read_stage19_ledger_rows(s19 / "operator_review_ledger.csv")
    errors = validate_stage19_ledger_row_id_uniqueness(rows)
    assert errors == []


def test_taxonomy_completeness_passes_on_locked_mapping():
    errors = verify_eligibility_taxonomy_completeness()
    assert errors == []
