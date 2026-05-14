"""Stage 19 closed-set error codes (E01..E21) and exception type.

Mirrors the Stage 17 / Stage 18 error pattern: a flat closed set
of E-codes, each with a stable snake_case name and a fixed
message template, surfaced as a single
``Stage19ValidationError`` exception. Callers (CLI exit-code
dispatch, tests) match on ``.code`` rather than parsing the
formatted message string.

Code table (locked, source order):

  Stage 18 input contract (E01..E05)
    E01 missing_stage18_dir
        -- Stage 18 input directory missing or not a directory.
    E02 missing_stage18_manifest
        -- Stage 18 manifest.json missing.
    E03 missing_stage18_review_matrix
        -- Stage 18 review_matrix.csv missing.
    E04 bad_stage18_manifest_json
        -- Stage 18 manifest.json malformed or missing required
           keys.
    E05 unexpected_stage18_schema_version
        -- Stage 18 manifest schema_version is not the expected
           value.

  Operator-input contract (E06..E09)
    E06 missing_operator_input
        -- operator_review_input.csv missing.
    E07 bad_operator_input_csv_header
        -- operator input CSV header does not match
           OPERATOR_INPUT_COLUMNS.
    E08 bad_operator_input_csv_row
        -- operator input CSV row malformed, including wrong
           column count, empty required field, or unparseable /
           non-positive window_seconds.
    E09 bad_operator_input_label
        -- review_label not in LABELS.

  Cross-validation against Stage 18 (E10..E12)
    E10 stage18_run_id_mismatch
        -- operator input stage18_run_id does not equal Stage 18
           manifest run_id.
    E11 stage18_row_identity_not_in_review_matrix
        -- operator input (policy_hash, rule_id, window_seconds)
           not present in review_matrix.
    E12 duplicate_identity_in_operator_input
        -- same (stage18_run_id, policy_hash, rule_id,
           window_seconds) appears more than once for the given
           operator_id in one input.

  Per-field validation (E13..E14)
    E13 bad_review_notes
        -- review_notes exceeds 2000 chars or contains control
           characters except space.
    E14 bad_operator_id
        -- --operator-id fails validation.

  Output and prior-ledger (E15..E18)
    E15 output_dir_non_empty
        -- --output-dir exists and is not empty, or exists as a
           file rather than a directory.
    E16 prior_ledger_dir_missing_files
        -- --prior-ledger-dir missing operator_review_ledger.csv
           or manifest.json.
    E17 prior_ledger_schema_version_mismatch
        -- prior ledger manifest.json stage19_schema_version
           != "stage19_ledger_v1".
    E18 prior_ledger_bad_row
        -- prior ledger CSV row malformed.

  Run-level CLI scalar (E19)
    E19 bad_run_timestamp_format
        -- --run-timestamp not in "YYYY-MM-DDTHH:MM:SSZ" form.

  Stage 18 review_matrix structural validation (E20..E21,
  added in a Phase 19.1 amendment to close a coverage gap left
  between E03 (review_matrix.csv missing) and the cross-validation
  layer; E05 covers manifest schema mismatch and is intentionally
  not reused for review_matrix structural failures)
    E20 bad_stage18_review_matrix_header
        -- Stage 18 review_matrix.csv header does not match
           STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS.
    E21 bad_stage18_review_matrix_row
        -- Stage 18 review_matrix.csv row malformed, including
           wrong column count, unparseable/non-positive
           window_seconds, or invalid Stage 18 classification
           value.

Phase 19.1 defines the closed set; the readers/validators/ledger
(Phase 19.2) and the writers/manifest/CLI (Phase 19.3) raise
specific codes against the table above.

A single ``Stage19ValidationError`` carries the code in ``.code``
and an optional context string in ``.detail``. Subclassing per
code is intentionally avoided -- callers and tests match on
``.code`` exactly.
"""

from __future__ import annotations

from typing import Mapping


E_CODES: tuple[str, ...] = (
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


ALL_CODES: frozenset[str] = frozenset(E_CODES)


CODE_NAMES: Mapping[str, str] = {
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


MESSAGE_TEMPLATES: Mapping[str, str] = {
    "E01": "Stage 18 input directory missing or not a directory",
    "E02": "Stage 18 manifest.json missing",
    "E03": "Stage 18 review_matrix.csv missing",
    "E04": "Stage 18 manifest.json malformed or missing required keys",
    "E05": (
        "Stage 18 manifest schema_version is not the expected value"
    ),
    "E06": "operator_review_input.csv missing",
    "E07": (
        "operator input CSV header does not match OPERATOR_INPUT_COLUMNS"
    ),
    "E08": (
        "operator input CSV row malformed (column count, empty required "
        "field, or unparseable/non-positive window_seconds)"
    ),
    "E09": "review_label not in LABELS",
    "E10": (
        "operator input stage18_run_id does not equal Stage 18 manifest "
        "run_id"
    ),
    "E11": (
        "operator input (policy_hash, rule_id, window_seconds) not "
        "present in review_matrix"
    ),
    "E12": (
        "duplicate (stage18_run_id, policy_hash, rule_id, window_seconds) "
        "for the given operator_id in one input"
    ),
    "E13": (
        "review_notes exceeds 2000 chars or contains control characters "
        "other than space"
    ),
    "E14": "--operator-id fails validation",
    "E15": (
        "--output-dir exists and is not empty, exists as a file rather "
        "than a directory, or its parent directory does not exist or is "
        "not a directory"
    ),
    "E16": (
        "--prior-ledger-dir missing operator_review_ledger.csv or "
        "manifest.json"
    ),
    "E17": (
        "prior ledger manifest.json stage19_schema_version is not "
        "\"stage19_ledger_v1\""
    ),
    "E18": "prior ledger CSV row malformed",
    "E19": "--run-timestamp not in \"YYYY-MM-DDTHH:MM:SSZ\" form",
    "E20": (
        "Stage 18 review_matrix.csv header does not match "
        "STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS"
    ),
    "E21": (
        "Stage 18 review_matrix.csv row malformed (column count, "
        "unparseable/non-positive window_seconds, or invalid Stage 18 "
        "classification value)"
    ),
}


class Stage19ValidationError(Exception):
    """Raised on any Stage 19 closed-set validation failure.

    Carries an E01..E21 code in ``.code`` and an optional context
    string in ``.detail``. Callers (CLI exit-code dispatcher,
    tests) match on ``.code`` rather than inspecting the formatted
    message string. Subclassing per-code is intentionally avoided
    to keep the exception surface flat.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ALL_CODES:
            raise ValueError(
                f"Stage19ValidationError code {code!r} is not in the "
                f"closed set"
            )
        self.code = code
        self.detail = detail
        template = MESSAGE_TEMPLATES[code]
        if detail:
            message = f"[{code}] {template}: {detail}"
        else:
            message = f"[{code}] {template}"
        super().__init__(message)


__all__ = [
    "ALL_CODES",
    "CODE_NAMES",
    "E_CODES",
    "MESSAGE_TEMPLATES",
    "Stage19ValidationError",
]
