"""Stage 19 constants module contract tests.

Locked-value, locked-shape, and locked-vocabulary checks for
``PHX2.stage19.constants``. The locked tuples (LABELS,
OPERATOR_INPUT_COLUMNS, LEDGER_COLUMNS, SUMMARY_COLUMNS, and the
Stage 18 review_matrix expected columns) are independently
re-stated as test-local constants so a typo in
``PHX2.stage19.constants`` is caught here rather than silently
mirrored.
"""

from __future__ import annotations

from PHX2.stage19 import constants as C


# ---------------------------------------------------------------------------
# Independent re-statement of the locked tuples
# ---------------------------------------------------------------------------


_EXPECTED_LABELS: tuple[str, ...] = (
    "REVIEW_PROMISING_CONFIRMED",
    "REVIEW_HARMFUL_CONFIRMED",
    "REVIEW_REJECTED",
    "WATCHLIST",
    "NEEDS_MORE_DATA",
    "INCONCLUSIVE",
)


_EXPECTED_OPERATOR_INPUT_COLUMNS: tuple[str, ...] = (
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "review_label",
    "review_notes",
)


_EXPECTED_LEDGER_COLUMNS: tuple[str, ...] = (
    "stage19_run_id",
    "ledger_row_id",
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "operator_id",
    "review_sequence",
    "review_label",
    "review_notes",
    "review_timestamp_utc",
    "stage18_classification",
    "stage17_label_preserved",
)


_EXPECTED_SUMMARY_COLUMNS: tuple[str, ...] = (
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "operator_id",
    "current_review_sequence",
    "current_review_label",
    "current_review_notes",
    "current_review_timestamp_utc",
    "stage18_classification",
    "stage17_label_preserved",
)


_EXPECTED_STAGE18_REVIEW_MATRIX_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "window_seconds",
    "window_label",
    "classification",
    "stage17_label_preserved",
    "insufficient_sample_reason",
    "data_block_reason",
    "gate_trips_all",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "n_with_complete_outcome",
    "delta_hit_2x_rate",
    "unevaluable_rate",
    "incomplete_outcome_ratio",
    "tier_coverage",
)


# ---------------------------------------------------------------------------
# LABELS -- review-judgment vocabulary (locked, six labels)
# ---------------------------------------------------------------------------


def test_labels_match_locked_six_tuple_in_order() -> None:
    assert C.LABELS == _EXPECTED_LABELS


def test_labels_count_is_six() -> None:
    assert len(C.LABELS) == 6


def test_labels_is_tuple() -> None:
    assert isinstance(C.LABELS, tuple)


def test_labels_has_no_duplicates() -> None:
    assert len(set(C.LABELS)) == len(C.LABELS)


def test_labels_entries_are_uppercase_bare_strings() -> None:
    for value in C.LABELS:
        assert isinstance(value, str) and value
        assert value == value.upper()
        assert " " not in value
        assert "\t" not in value


# ---------------------------------------------------------------------------
# Forbidden vocabulary: ensure obsolete decision-style names DO NOT
# appear at module level
# ---------------------------------------------------------------------------


def test_no_legacy_decision_vocabulary_exposed() -> None:
    """Operator-mandated negative check: AGREE, DISAGREE, DEFER, and
    decision-flavored constant/aggregate names from earlier drafts
    must NOT exist at the module level. The locked vocabulary is
    LABELS + review_label."""

    forbidden_names = {
        "AGREE",
        "DISAGREE",
        "DEFER",
        "DECISION_AGREE",
        "DECISION_DISAGREE",
        "DECISION_DEFER",
        "DECISION_NEEDS_MORE_DATA",
        "ALL_OPERATOR_DECISIONS",
        "DECISIONS",
        "REVIEW_LABELS",  # unused alias
        "OPERATOR_DECISION",
    }
    public_names = {n for n in dir(C) if not n.startswith("_")}
    leakage = forbidden_names & public_names
    assert leakage == set(), (
        f"forbidden legacy decision names exposed: {sorted(leakage)}"
    )


def test_no_legacy_label_strings_appear_inside_labels() -> None:
    """The locked LABELS tuple must not contain any of the obsolete
    decision-style values (AGREE/DISAGREE/DEFER)."""

    forbidden_values = {"AGREE", "DISAGREE", "DEFER"}
    leakage = forbidden_values & set(C.LABELS)
    assert leakage == set(), (
        f"forbidden legacy label strings inside LABELS: {sorted(leakage)}"
    )


def test_operator_decision_substring_absent_from_constant_names() -> None:
    """No public constant name should contain the legacy
    ``operator_decision`` substring."""

    leakage = [
        n for n in dir(C)
        if not n.startswith("_") and "operator_decision" in n.lower()
    ]
    assert leakage == [], leakage


# ---------------------------------------------------------------------------
# OPERATOR_INPUT_COLUMNS -- six columns; operator_id is NOT a CSV column
# ---------------------------------------------------------------------------


def test_operator_input_columns_match_locked_six_tuple_in_order() -> None:
    assert C.OPERATOR_INPUT_COLUMNS == _EXPECTED_OPERATOR_INPUT_COLUMNS


def test_operator_input_columns_count_is_six() -> None:
    assert len(C.OPERATOR_INPUT_COLUMNS) == 6


def test_operator_input_columns_is_tuple() -> None:
    assert isinstance(C.OPERATOR_INPUT_COLUMNS, tuple)


def test_operator_input_columns_has_no_duplicates() -> None:
    cols = C.OPERATOR_INPUT_COLUMNS
    assert len(set(cols)) == len(cols)


def test_operator_id_not_in_operator_input_columns() -> None:
    """operator_id is a CLI scalar (--operator-id), not a CSV column."""

    assert "operator_id" not in C.OPERATOR_INPUT_COLUMNS


def test_review_label_in_operator_input_columns() -> None:
    """The human-judgment column is named ``review_label``
    (not ``operator_decision``)."""

    assert "review_label" in C.OPERATOR_INPUT_COLUMNS


def test_operator_decision_not_in_operator_input_columns() -> None:
    assert "operator_decision" not in C.OPERATOR_INPUT_COLUMNS


# ---------------------------------------------------------------------------
# LEDGER_COLUMNS -- thirteen columns in exact order
# ---------------------------------------------------------------------------


def test_ledger_columns_match_locked_thirteen_tuple_in_order() -> None:
    assert C.LEDGER_COLUMNS == _EXPECTED_LEDGER_COLUMNS


def test_ledger_columns_count_is_thirteen() -> None:
    assert len(C.LEDGER_COLUMNS) == 13


def test_ledger_columns_is_tuple_of_unique_strings() -> None:
    assert isinstance(C.LEDGER_COLUMNS, tuple)
    cols = C.LEDGER_COLUMNS
    assert len(set(cols)) == len(cols)
    for col in cols:
        assert isinstance(col, str) and col


def test_ledger_columns_includes_stage19_run_id() -> None:
    assert "stage19_run_id" in C.LEDGER_COLUMNS


def test_ledger_columns_includes_ledger_row_id() -> None:
    assert "ledger_row_id" in C.LEDGER_COLUMNS


def test_ledger_columns_includes_review_sequence() -> None:
    assert "review_sequence" in C.LEDGER_COLUMNS


def test_ledger_columns_includes_review_timestamp_utc() -> None:
    assert "review_timestamp_utc" in C.LEDGER_COLUMNS


def test_ledger_columns_does_not_include_operator_decision() -> None:
    assert "operator_decision" not in C.LEDGER_COLUMNS


def test_ledger_columns_includes_stage18_classification_rename() -> None:
    """The ledger uses the namespaced ``stage18_classification`` rename
    (Stage 18's source column is plain ``classification``)."""

    assert "stage18_classification" in C.LEDGER_COLUMNS
    assert "classification" not in C.LEDGER_COLUMNS


def test_ledger_columns_preserves_stage17_label_passthrough() -> None:
    assert "stage17_label_preserved" in C.LEDGER_COLUMNS


# ---------------------------------------------------------------------------
# SUMMARY_COLUMNS -- eleven columns; MAX(review_sequence) selection
# ---------------------------------------------------------------------------


def test_summary_columns_match_locked_eleven_tuple_in_order() -> None:
    assert C.SUMMARY_COLUMNS == _EXPECTED_SUMMARY_COLUMNS


def test_summary_columns_count_is_eleven() -> None:
    assert len(C.SUMMARY_COLUMNS) == 11


def test_summary_columns_is_tuple_of_unique_strings() -> None:
    assert isinstance(C.SUMMARY_COLUMNS, tuple)
    cols = C.SUMMARY_COLUMNS
    assert len(set(cols)) == len(cols)
    for col in cols:
        assert isinstance(col, str) and col


def test_summary_columns_uses_current_prefix_for_review_fields() -> None:
    """The summary's review fields are prefixed ``current_`` to mark
    them as the MAX(review_sequence) snapshot, distinct from the
    ledger's per-version fields."""

    for prefixed in (
        "current_review_sequence",
        "current_review_label",
        "current_review_notes",
        "current_review_timestamp_utc",
    ):
        assert prefixed in C.SUMMARY_COLUMNS


def test_summary_columns_does_not_use_unprefixed_review_fields() -> None:
    """The non-current ``review_label`` / ``review_notes`` /
    ``review_timestamp_utc`` / ``review_sequence`` belong to the
    ledger, not the summary."""

    for unprefixed in (
        "review_label",
        "review_notes",
        "review_timestamp_utc",
        "review_sequence",
    ):
        assert unprefixed not in C.SUMMARY_COLUMNS


# ---------------------------------------------------------------------------
# Stage 19 versions
# ---------------------------------------------------------------------------


def test_stage19_schema_version_is_stage19_ledger_v1() -> None:
    assert C.STAGE19_SCHEMA_VERSION == "stage19_ledger_v1"


def test_stage19_version_is_locked_semver_string() -> None:
    assert C.STAGE19_VERSION == "0.1.0"


def test_no_legacy_manifest_schema_version_constant_exposed() -> None:
    """The legacy ``MANIFEST_SCHEMA_VERSION`` constant from a prior
    draft must NOT exist; the Stage 19 ledger schema lives in
    ``STAGE19_SCHEMA_VERSION``."""

    assert "MANIFEST_SCHEMA_VERSION" not in dir(C)


# ---------------------------------------------------------------------------
# Length caps
# ---------------------------------------------------------------------------


def test_max_review_notes_length_is_2000() -> None:
    assert C.MAX_REVIEW_NOTES_LENGTH == 2000


def test_max_operator_id_length_is_64() -> None:
    assert C.MAX_OPERATOR_ID_LENGTH == 64


def test_length_caps_are_positive_ints() -> None:
    for cap in (C.MAX_REVIEW_NOTES_LENGTH, C.MAX_OPERATOR_ID_LENGTH):
        assert isinstance(cap, int)
        assert not isinstance(cap, bool)
        assert cap > 0


# ---------------------------------------------------------------------------
# Stage 18 pinned constants
# ---------------------------------------------------------------------------


def test_stage18_review_matrix_expected_columns_match_locked_17_tuple() -> None:
    assert (
        C.STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS
        == _EXPECTED_STAGE18_REVIEW_MATRIX_COLUMNS
    )


def test_stage18_review_matrix_expected_columns_count_is_17() -> None:
    assert len(C.STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS) == 17


def test_stage18_review_matrix_expected_columns_is_tuple_of_strings() -> None:
    assert isinstance(C.STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS, tuple)
    for col in C.STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS:
        assert isinstance(col, str) and col


def test_stage18_review_matrix_expected_columns_has_no_duplicates() -> None:
    cols = C.STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS
    assert len(set(cols)) == len(cols)


def test_stage18_manifest_run_id_key_is_run_id() -> None:
    assert C.STAGE18_MANIFEST_RUN_ID_KEY == "run_id"


def test_stage18_expected_manifest_schema_version_is_v0() -> None:
    assert (
        C.STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION
        == "stage18_run_manifest_v0"
    )


# ---------------------------------------------------------------------------
# Filename constants
# ---------------------------------------------------------------------------


def test_operator_input_filename_is_locked_string() -> None:
    assert C.OPERATOR_INPUT_FILENAME == "operator_review_input.csv"


def test_ledger_filename_is_locked_string() -> None:
    assert C.LEDGER_FILENAME == "operator_review_ledger.csv"


def test_summary_filename_is_locked_string() -> None:
    assert C.SUMMARY_FILENAME == "operator_review_summary.csv"


def test_manifest_filename_is_locked_string() -> None:
    assert C.MANIFEST_FILENAME == "manifest.json"


def test_readme_filename_is_locked_string() -> None:
    assert C.README_FILENAME == "README.md"


def test_run_log_filename_is_locked_string() -> None:
    assert C.RUN_LOG_FILENAME == "stage19_run.log"


def test_stage18_input_filename_constants_match_required_tuple() -> None:
    assert C.STAGE18_MANIFEST_FILENAME == "manifest.json"
    assert C.STAGE18_REVIEW_MATRIX_FILENAME == "review_matrix.csv"
    assert C.REQUIRED_STAGE18_INPUT_FILES == (
        "manifest.json",
        "review_matrix.csv",
    )


# ---------------------------------------------------------------------------
# v0 simplification: no cross_operator_latest_summary
# ---------------------------------------------------------------------------


def test_no_cross_operator_latest_summary_filename_constant() -> None:
    """v0 explicitly drops the cross-operator-latest summary
    artifact. No filename constant for it may exist."""

    public_names = {n for n in dir(C) if not n.startswith("_")}
    forbidden = {
        "CROSS_OPERATOR_LATEST_SUMMARY_FILENAME",
        "CROSS_OPERATOR_SUMMARY_FILENAME",
    }
    leakage = forbidden & public_names
    assert leakage == set(), (
        f"forbidden v0 names exposed: {sorted(leakage)}"
    )


def test_no_cross_operator_summary_columns_constant() -> None:
    public_names = {n for n in dir(C) if not n.startswith("_")}
    assert "CROSS_OPERATOR_SUMMARY_COLUMNS" not in public_names


def test_no_cross_operator_filename_string_anywhere_in_module() -> None:
    """Defense in depth: scan every public string-typed constant for
    the legacy cross-operator filename literal."""

    legacy = "cross_operator_latest_summary"
    for name in dir(C):
        if name.startswith("_"):
            continue
        value = getattr(C, name)
        if isinstance(value, str):
            assert legacy not in value, (
                f"{name} contains forbidden legacy literal: {value!r}"
            )


# ---------------------------------------------------------------------------
# Cross-tuple checks: shared keys must be identically named
# ---------------------------------------------------------------------------


_SHARED_SLICE_KEYS: tuple[str, ...] = (
    "stage18_run_id",
    "policy_hash",
    "rule_id",
    "window_seconds",
)


def test_slice_key_columns_present_in_all_three_tuples() -> None:
    """The four slice-key columns appear with the same names in
    OPERATOR_INPUT_COLUMNS, LEDGER_COLUMNS, and SUMMARY_COLUMNS."""

    for col in _SHARED_SLICE_KEYS:
        assert col in C.OPERATOR_INPUT_COLUMNS, col
        assert col in C.LEDGER_COLUMNS, col
        assert col in C.SUMMARY_COLUMNS, col


def test_operator_id_present_in_ledger_and_summary_only() -> None:
    """operator_id is a CLI scalar -- it appears in the ledger and
    summary outputs but NOT in the operator-input CSV."""

    assert "operator_id" not in C.OPERATOR_INPUT_COLUMNS
    assert "operator_id" in C.LEDGER_COLUMNS
    assert "operator_id" in C.SUMMARY_COLUMNS


def test_review_label_in_operator_input_and_ledger_same_name() -> None:
    """review_label flows from operator input row into ledger row
    under the same column name. (The summary uses
    ``current_review_label`` for the MAX-sequence snapshot.)"""

    assert "review_label" in C.OPERATOR_INPUT_COLUMNS
    assert "review_label" in C.LEDGER_COLUMNS


def test_review_notes_in_operator_input_and_ledger_same_name() -> None:
    """Mirrors review_label: same column name across operator input
    and ledger."""

    assert "review_notes" in C.OPERATOR_INPUT_COLUMNS
    assert "review_notes" in C.LEDGER_COLUMNS


def test_stage18_classification_in_ledger_and_summary_same_name() -> None:
    """The Stage 18 evidence columns (``stage18_classification``,
    ``stage17_label_preserved``) are passed through ledger to
    summary with identical names."""

    assert "stage18_classification" in C.LEDGER_COLUMNS
    assert "stage18_classification" in C.SUMMARY_COLUMNS
    assert "stage17_label_preserved" in C.LEDGER_COLUMNS
    assert "stage17_label_preserved" in C.SUMMARY_COLUMNS


# ---------------------------------------------------------------------------
# Module surface (__all__)
# ---------------------------------------------------------------------------


def test_module_all_exports_expected_names() -> None:
    expected = {
        "LABELS",
        "LEDGER_COLUMNS",
        "LEDGER_FILENAME",
        "MANIFEST_FILENAME",
        "MAX_OPERATOR_ID_LENGTH",
        "MAX_REVIEW_NOTES_LENGTH",
        "OPERATOR_INPUT_COLUMNS",
        "OPERATOR_INPUT_FILENAME",
        "README_FILENAME",
        "REQUIRED_STAGE18_INPUT_FILES",
        "RUN_LOG_FILENAME",
        "STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION",
        "STAGE18_MANIFEST_FILENAME",
        "STAGE18_MANIFEST_RUN_ID_KEY",
        "STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS",
        "STAGE18_REVIEW_MATRIX_FILENAME",
        "STAGE19_SCHEMA_VERSION",
        "STAGE19_VERSION",
        "SUMMARY_COLUMNS",
        "SUMMARY_FILENAME",
    }
    assert set(C.__all__) == expected
