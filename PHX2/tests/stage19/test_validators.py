"""Stage 19 validator tests.

Covers all five validators:
  * validate_operator_id           -- E14
  * validate_run_timestamp         -- E19
  * validate_output_dir            -- E15
  * validate_against_review_matrix -- E10, E11
  * validate_no_duplicates         -- E12
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage19 import validators
from PHX2.stage19.errors import Stage19ValidationError
from PHX2.stage19.readers import OperatorInputRow, ReviewMatrixRecord


# ===========================================================================
# validate_operator_id
# ===========================================================================


class TestValidateOperatorIdAccept:
    @pytest.mark.parametrize(
        "good",
        [
            "maq",
            "maq ops",
            "op-1",
            "OPERATOR_2",
            "a" * 64,  # exactly at cap
            "user.name",
            "user@hostlikename",  # @ is ASCII printable
        ],
    )
    def test_accepts_valid_id(self, good: str) -> None:
        assert validators.validate_operator_id(good) == good

    def test_strips_outer_whitespace(self) -> None:
        assert validators.validate_operator_id(" maq ") == "maq"

    def test_strips_tabs_at_edges_then_validates_remainder(self) -> None:
        # Outer whitespace strip removes leading/trailing tabs;
        # internal tab would still fail E14 if present, but here
        # all tabs are stripped.
        assert validators.validate_operator_id("\t maq \t") == "maq"


class TestValidateOperatorIdRejectE14:
    def test_empty_string_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("")
        assert excinfo.value.code == "E14"

    def test_whitespace_only_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("   ")
        assert excinfo.value.code == "E14"

    def test_too_long_65_chars_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("a" * 65)
        assert excinfo.value.code == "E14"

    def test_comma_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op,name")
        assert excinfo.value.code == "E14"

    def test_single_quote_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op'name")
        assert excinfo.value.code == "E14"

    def test_double_quote_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id('op"name')
        assert excinfo.value.code == "E14"

    def test_newline_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op\nname")
        assert excinfo.value.code == "E14"

    def test_carriage_return_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op\rname")
        assert excinfo.value.code == "E14"

    def test_tab_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op\tname")
        assert excinfo.value.code == "E14"

    def test_non_ascii_e_acute_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("café")
        assert excinfo.value.code == "E14"

    def test_del_chr127_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op" + chr(127))
        assert excinfo.value.code == "E14"

    def test_other_control_char_chr1_raises_e14(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_operator_id("op" + chr(1))
        assert excinfo.value.code == "E14"


# ===========================================================================
# validate_run_timestamp
# ===========================================================================


class TestValidateRunTimestamp:
    def test_accepts_canonical_form(self) -> None:
        assert (
            validators.validate_run_timestamp("2026-05-14T05:00:00Z")
            == "2026-05-14T05:00:00Z"
        )

    def test_returns_input_unchanged(self) -> None:
        # Different timestamp, same format
        assert (
            validators.validate_run_timestamp("2025-01-01T00:00:00Z")
            == "2025-01-01T00:00:00Z"
        )

    def test_no_z_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("2026-05-14T05:00:00")
        assert excinfo.value.code == "E19"

    def test_space_instead_of_t_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("2026-05-14 05:00:00Z")
        assert excinfo.value.code == "E19"

    def test_fractional_seconds_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("2026-05-14T05:00:00.123Z")
        assert excinfo.value.code == "E19"

    def test_tz_offset_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("2026-05-14T05:00:00+00:00")
        assert excinfo.value.code == "E19"

    def test_empty_string_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("")
        assert excinfo.value.code == "E19"

    def test_non_numeric_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("YYYY-MM-DDTHH:MM:SSZ")
        assert excinfo.value.code == "E19"

    def test_malformed_date_raises_e19(self) -> None:
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_run_timestamp("2026-13-99T05:00:00Z")
        assert excinfo.value.code == "E19"


# ===========================================================================
# validate_output_dir
# ===========================================================================


class TestValidateOutputDir:
    def test_accepts_non_existent_path(self, tmp_path: Path) -> None:
        validators.validate_output_dir(tmp_path / "does_not_exist")
        # No exception = pass

    def test_accepts_existing_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        validators.validate_output_dir(empty)
        # No exception = pass

    def test_rejects_non_empty_directory_e15(self, tmp_path: Path) -> None:
        d = tmp_path / "non_empty"
        d.mkdir()
        (d / "preexisting.txt").write_text("hi")
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_output_dir(d)
        assert excinfo.value.code == "E15"

    def test_rejects_existing_file_path_e15(self, tmp_path: Path) -> None:
        f = tmp_path / "regular.txt"
        f.write_text("hi")
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_output_dir(f)
        assert excinfo.value.code == "E15"


# ===========================================================================
# validate_against_review_matrix
# ===========================================================================


def _make_input_row(
    *,
    stage18_run_id: str = "0123456789abcdef",
    policy_hash: str = "abc123def456",
    rule_id: str = "rule_minimal",
    window_seconds: int = 3600,
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "ok",
) -> OperatorInputRow:
    return OperatorInputRow(
        stage18_run_id=stage18_run_id,
        policy_hash=policy_hash,
        rule_id=rule_id,
        window_seconds=window_seconds,
        review_label=review_label,
        review_notes=review_notes,
    )


def _make_review_matrix_index(
    keys: list[tuple[str, str, int]] | None = None,
) -> dict[tuple[str, str, int], ReviewMatrixRecord]:
    if keys is None:
        keys = [("abc123def456", "rule_minimal", 3600)]
    return {
        k: ReviewMatrixRecord(
            policy_hash=k[0],
            rule_id=k[1],
            window_seconds=k[2],
            stage18_classification="PROMISING_REVIEW",
            stage17_label_preserved="PROMISING",
        )
        for k in keys
    }


class TestValidateAgainstReviewMatrix:
    def test_happy_path_no_error(self) -> None:
        rows = [_make_input_row()]
        idx = _make_review_matrix_index()
        validators.validate_against_review_matrix(
            rows, idx, "0123456789abcdef"
        )

    def test_run_id_mismatch_raises_e10(self) -> None:
        rows = [_make_input_row(stage18_run_id="WRONG_RUN_ID")]
        idx = _make_review_matrix_index()
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_against_review_matrix(
                rows, idx, "0123456789abcdef"
            )
        assert excinfo.value.code == "E10"

    def test_identity_not_in_matrix_raises_e11(self) -> None:
        rows = [_make_input_row(rule_id="MISSING_RULE")]
        idx = _make_review_matrix_index()
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_against_review_matrix(
                rows, idx, "0123456789abcdef"
            )
        assert excinfo.value.code == "E11"

    def test_first_failing_row_index_in_detail(self) -> None:
        rows = [
            _make_input_row(),
            _make_input_row(rule_id="MISSING_RULE"),  # row 2
            _make_input_row(stage18_run_id="WRONG"),  # row 3 (would be E10)
        ]
        idx = _make_review_matrix_index()
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_against_review_matrix(
                rows, idx, "0123456789abcdef"
            )
        assert excinfo.value.code == "E11"  # row 2 is the first failure
        assert "row 2" in excinfo.value.detail

    def test_e10_includes_row_index_in_detail(self) -> None:
        rows = [
            _make_input_row(),
            _make_input_row(stage18_run_id="WRONG"),  # row 2
        ]
        idx = _make_review_matrix_index()
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_against_review_matrix(
                rows, idx, "0123456789abcdef"
            )
        assert excinfo.value.code == "E10"
        assert "row 2" in excinfo.value.detail


# ===========================================================================
# validate_no_duplicates
# ===========================================================================


class TestValidateNoDuplicates:
    def test_happy_path_no_error(self) -> None:
        rows = [
            _make_input_row(rule_id="rule_a"),
            _make_input_row(rule_id="rule_b"),
            _make_input_row(rule_id="rule_c"),
        ]
        validators.validate_no_duplicates(rows, "alice")

    def test_duplicate_identity_raises_e12(self) -> None:
        rows = [
            _make_input_row(),
            _make_input_row(),  # exact same identity
        ]
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_no_duplicates(rows, "alice")
        assert excinfo.value.code == "E12"

    def test_duplicate_detail_includes_both_row_indices(self) -> None:
        rows = [
            _make_input_row(),  # row 1
            _make_input_row(rule_id="rule_other"),  # row 2 (different)
            _make_input_row(),  # row 3 (duplicate of row 1)
        ]
        with pytest.raises(Stage19ValidationError) as excinfo:
            validators.validate_no_duplicates(rows, "alice")
        assert excinfo.value.code == "E12"
        assert "1" in excinfo.value.detail
        assert "3" in excinfo.value.detail

    def test_empty_input_no_error(self) -> None:
        validators.validate_no_duplicates([], "alice")

    def test_different_window_seconds_not_duplicate(self) -> None:
        rows = [
            _make_input_row(window_seconds=60),
            _make_input_row(window_seconds=3600),
            _make_input_row(window_seconds=86400),
        ]
        validators.validate_no_duplicates(rows, "alice")

    def test_different_stage18_run_id_not_duplicate(self) -> None:
        rows = [
            _make_input_row(stage18_run_id="run_a"),
            _make_input_row(stage18_run_id="run_b"),
        ]
        validators.validate_no_duplicates(rows, "alice")
