"""Stage 19 errors module contract tests.

Locks the closed E01..E19 code set, the snake_case ``CODE_NAMES``
mapping, the ``MESSAGE_TEMPLATES`` mapping, and the
``Stage19ValidationError`` exception's ``.code`` / ``.detail``
contract. The locked code-to-name mapping is independently
re-stated below so a typo in ``PHX2.stage19.errors`` is caught
here.
"""

from __future__ import annotations

import re

import pytest

from PHX2.stage19 import errors as E


# ---------------------------------------------------------------------------
# Independent re-statement of the closed E-code set + locked names
# ---------------------------------------------------------------------------


_EXPECTED_E_CODES: tuple[str, ...] = (
    "E01",
    "E02",
    "E03",
    "E04",
    "E05",
    "E06",
    "E07",
    "E08",
    "E09",
    "E10",
    "E11",
    "E12",
    "E13",
    "E14",
    "E15",
    "E16",
    "E17",
    "E18",
    "E19",
    "E20",
    "E21",
)


_EXPECTED_CODE_NAMES: dict[str, str] = {
    "E01": "missing_stage18_dir",
    "E02": "missing_stage18_manifest",
    "E03": "missing_stage18_review_matrix",
    "E04": "bad_stage18_manifest_json",
    "E05": "unexpected_stage18_schema_version",
    "E06": "missing_operator_input",
    "E07": "bad_operator_input_csv_header",
    "E08": "bad_operator_input_csv_row",
    "E09": "bad_operator_input_label",
    "E10": "stage18_run_id_mismatch",
    "E11": "stage18_row_identity_not_in_review_matrix",
    "E12": "duplicate_identity_in_operator_input",
    "E13": "bad_review_notes",
    "E14": "bad_operator_id",
    "E15": "output_dir_non_empty",
    "E16": "prior_ledger_dir_missing_files",
    "E17": "prior_ledger_schema_version_mismatch",
    "E18": "prior_ledger_bad_row",
    "E19": "bad_run_timestamp_format",
    "E20": "bad_stage18_review_matrix_header",
    "E21": "bad_stage18_review_matrix_row",
}


# Per-code expected substrings that must appear in MESSAGE_TEMPLATES
# (consistency-with-meaning check; not full string equality).
_EXPECTED_MESSAGE_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "E01": ("Stage 18 input directory",),
    "E02": ("manifest.json", "missing"),
    "E03": ("review_matrix.csv", "missing"),
    "E04": ("manifest.json", "malformed"),
    "E05": ("schema_version",),
    "E06": ("operator_review_input.csv", "missing"),
    "E07": ("operator input CSV header", "OPERATOR_INPUT_COLUMNS"),
    "E08": ("operator input CSV row", "malformed"),
    "E09": ("review_label", "LABELS"),
    "E10": ("stage18_run_id", "run_id"),
    "E11": ("policy_hash", "review_matrix"),
    "E12": ("duplicate", "operator_id"),
    "E13": ("review_notes", "2000"),
    "E14": ("--operator-id",),
    "E15": ("--output-dir",),
    "E16": ("--prior-ledger-dir", "operator_review_ledger.csv"),
    "E17": ("stage19_schema_version", "stage19_ledger_v1"),
    "E18": ("prior ledger CSV row", "malformed"),
    "E19": ("--run-timestamp", "YYYY-MM-DDTHH:MM:SSZ"),
    "E20": (
        "Stage 18 review_matrix.csv header",
        "STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS",
    ),
    "E21": ("Stage 18 review_matrix.csv row", "malformed"),
}


_E_CODE_PATTERN = re.compile(r"^E\d{2}$")


# ---------------------------------------------------------------------------
# E_CODES tuple shape
# ---------------------------------------------------------------------------


def test_e_codes_count_is_21() -> None:
    assert len(E.E_CODES) == 21


def test_e_codes_match_expected_sequence() -> None:
    assert E.E_CODES == _EXPECTED_E_CODES


def test_e_codes_are_unique() -> None:
    assert len(set(E.E_CODES)) == len(E.E_CODES)


def test_each_code_matches_e_two_digit_pattern() -> None:
    for code in E.E_CODES:
        assert _E_CODE_PATTERN.match(code), code


def test_e_codes_is_tuple_of_strings() -> None:
    assert isinstance(E.E_CODES, tuple)
    for code in E.E_CODES:
        assert isinstance(code, str)


# ---------------------------------------------------------------------------
# ALL_CODES frozenset
# ---------------------------------------------------------------------------


def test_all_codes_is_frozenset() -> None:
    assert isinstance(E.ALL_CODES, frozenset)


def test_all_codes_matches_e_codes_set() -> None:
    assert E.ALL_CODES == frozenset(E.E_CODES)


def test_all_codes_size_matches_e_codes() -> None:
    assert len(E.ALL_CODES) == len(E.E_CODES)


# ---------------------------------------------------------------------------
# CODE_NAMES mapping (snake_case names per code)
# ---------------------------------------------------------------------------


def test_code_names_keys_match_e_codes_exactly() -> None:
    assert set(E.CODE_NAMES.keys()) == set(E.E_CODES)


def test_code_names_values_match_locked_snake_case_names() -> None:
    for code, expected_name in _EXPECTED_CODE_NAMES.items():
        assert E.CODE_NAMES[code] == expected_name, code


def test_code_names_values_are_unique() -> None:
    """Two different codes may not share the same snake_case name."""

    values = list(E.CODE_NAMES.values())
    assert len(set(values)) == len(values)


def test_code_names_values_are_snake_case_lowercase_strings() -> None:
    for code, name in E.CODE_NAMES.items():
        assert isinstance(name, str), code
        assert name, code
        assert name == name.lower(), code
        assert " " not in name, code
        assert "-" not in name, code


# ---------------------------------------------------------------------------
# MESSAGE_TEMPLATES mapping
# ---------------------------------------------------------------------------


def test_message_templates_keys_match_e_codes_exactly() -> None:
    assert set(E.MESSAGE_TEMPLATES.keys()) == set(E.E_CODES)


def test_message_templates_values_are_non_empty_strings() -> None:
    for code, template in E.MESSAGE_TEMPLATES.items():
        assert isinstance(template, str), code
        assert template, code


def test_message_templates_no_extra_or_missing_keys() -> None:
    extras = set(E.MESSAGE_TEMPLATES.keys()) - set(E.E_CODES)
    missing = set(E.E_CODES) - set(E.MESSAGE_TEMPLATES.keys())
    assert extras == set()
    assert missing == set()


@pytest.mark.parametrize(
    ("code", "substrings"), list(_EXPECTED_MESSAGE_SUBSTRINGS.items())
)
def test_message_template_contains_expected_substrings(
    code: str, substrings: tuple[str, ...]
) -> None:
    """Each code's message must contain key terms that identify the
    locked meaning (consistency check; not full string equality)."""

    template = E.MESSAGE_TEMPLATES[code]
    for needle in substrings:
        assert needle in template, (
            f"{code} template {template!r} missing substring {needle!r}"
        )


# ---------------------------------------------------------------------------
# Stage19ValidationError construction and formatting
# ---------------------------------------------------------------------------


def test_stage19_validation_error_is_exception_subclass() -> None:
    assert issubclass(E.Stage19ValidationError, Exception)


def test_stage19_validation_error_class_name_is_locked() -> None:
    """The single-class design is intentional -- no per-code subclass.
    The class name itself is part of the locked surface."""

    assert E.Stage19ValidationError.__name__ == "Stage19ValidationError"


def test_stage19_validation_error_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="closed set"):
        E.Stage19ValidationError("E99")


def test_stage19_validation_error_rejects_lowercase_code() -> None:
    with pytest.raises(ValueError, match="closed set"):
        E.Stage19ValidationError("e01")


def test_stage19_validation_error_rejects_unprefixed_code() -> None:
    with pytest.raises(ValueError, match="closed set"):
        E.Stage19ValidationError("01")


def test_stage19_validation_error_carries_code_attribute() -> None:
    err = E.Stage19ValidationError("E01")
    assert err.code == "E01"


def test_stage19_validation_error_carries_default_empty_detail() -> None:
    err = E.Stage19ValidationError("E01")
    assert err.detail == ""


def test_stage19_validation_error_carries_custom_detail() -> None:
    err = E.Stage19ValidationError("E08", detail="row 3 column count")
    assert err.detail == "row 3 column count"


def test_stage19_validation_error_message_formatting_no_detail() -> None:
    err = E.Stage19ValidationError("E01")
    assert str(err) == f"[E01] {E.MESSAGE_TEMPLATES['E01']}"


def test_stage19_validation_error_message_formatting_with_detail() -> None:
    err = E.Stage19ValidationError("E08", detail="row 3 column count")
    expected = f"[E08] {E.MESSAGE_TEMPLATES['E08']}: row 3 column count"
    assert str(err) == expected


@pytest.mark.parametrize("code", _EXPECTED_E_CODES)
def test_each_code_can_be_raised_and_caught(code: str) -> None:
    with pytest.raises(E.Stage19ValidationError) as excinfo:
        raise E.Stage19ValidationError(code, detail="ctx")
    assert excinfo.value.code == code
    assert excinfo.value.detail == "ctx"
    assert f"[{code}]" in str(excinfo.value)


@pytest.mark.parametrize("code", _EXPECTED_E_CODES)
def test_each_code_has_template_substring_in_message(code: str) -> None:
    err = E.Stage19ValidationError(code)
    assert E.MESSAGE_TEMPLATES[code] in str(err)


# ---------------------------------------------------------------------------
# Module surface (__all__)
# ---------------------------------------------------------------------------


def test_module_all_exports_expected_names() -> None:
    expected = {
        "ALL_CODES",
        "CODE_NAMES",
        "E_CODES",
        "MESSAGE_TEMPLATES",
        "Stage19ValidationError",
    }
    assert set(E.__all__) == expected


def test_no_legacy_stage19_error_class_exposed() -> None:
    """The single locked class is ``Stage19ValidationError``. The
    earlier-draft name ``Stage19Error`` must not be exposed."""

    assert "Stage19Error" not in dir(E)
