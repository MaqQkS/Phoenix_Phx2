"""Stage 20.2 constants — drift guards and additive-lock assertions.

Asserts every Stage 20.2 constant the prompt or operator pinned has
the expected value. These tests catch silent value drift in
``PHX2/stage20/constants.py``. They do not duplicate the Stage 20.1
test_constants.py coverage; they extend it for the new 20.2 surface.

Operator decisions baked in (per Phase A approval):

  * B1-a -- Do not introduce a Stage-18-side run-id constant. Stage
    20.2's manifest assembler reads stage18_run_id from Stage 19's
    manifest using the existing ``STAGE19_MANIFEST_KEY_STAGE18_RUN_ID``.

  * B2-c -- Keep ``STAGE20_VERSION`` at "stage20_v0_observe_only".
    Add a new minor-version axis ``STAGE20_MINOR_VERSION = "20.2"``.
    Both are emitted on the manifest and mixed into ID derivations.

  * B3-a -- Keep ``CONSUMER_CONTRACT_VERSION`` at
    "stage20_to_stage21_v0" (no rename).
"""

from __future__ import annotations

import re

from PHX2.stage20 import constants


# ---------------------------------------------------------------------------
# Drift guards (operator-locked values)
# ---------------------------------------------------------------------------


def test_stage20_version_preserved_at_20_1_lock():
    """Operator decision B2-c: keep existing 20.1 value, do not rename."""

    assert constants.STAGE20_VERSION == "stage20_v0_observe_only"


def test_stage20_minor_version_is_20_2():
    """Operator decision B2-c: new minor axis introduced at 20.2."""

    assert constants.STAGE20_MINOR_VERSION == "20.2"


def test_consumer_contract_version_preserved_at_20_1_lock():
    """Operator decision B3-a: keep existing 20.1 value, do not rename."""

    assert constants.CONSUMER_CONTRACT_VERSION == "stage20_to_stage21_v0"


def test_mapping_version_is_v0():
    assert constants.MAPPING_VERSION == "v0"


def test_stage19_manifest_key_stage18_run_id_is_stable():
    """Drift guard per operator decision B1-a.

    Stage 20.2 reads stage18_run_id from Stage 19's manifest using
    this key (Stage 19 namespaces it as ``stage18_run_id`` even
    though Stage 18's own manifest uses the un-namespaced key
    ``run_id``). Renaming or revaluing this constant breaks 20.2's
    manifest assembly.
    """

    assert constants.STAGE19_MANIFEST_KEY_STAGE18_RUN_ID == "stage18_run_id"


def test_no_stage18_manifest_key_stage18_run_id_constant_added():
    """Negative drift guard per operator decision B1-a.

    The prompt's Hard Constraint #11 pre-approved a constant
    ``STAGE18_MANIFEST_KEY_STAGE18_RUN_ID`` with value
    ``"stage18_run_id"``. Operator decision B1-a rejected that
    addition because Stage 18's manifest actually uses the
    un-namespaced key ``"run_id"`` -- the pre-approved value was
    factually wrong. This test asserts the constant was NOT added.
    """

    assert not hasattr(constants, "STAGE18_MANIFEST_KEY_STAGE18_RUN_ID")


# ---------------------------------------------------------------------------
# CSV column tuple locks
# ---------------------------------------------------------------------------


def test_preview_candidates_csv_columns_locked_order():
    expected = (
        "candidate_id",
        "stage20_run_id",
        "stage18_run_id",
        "stage19_run_id",
        "source_ledger_row_id",
        "policy_hash",
        "rule_id",
        "window_seconds",
        "operator_id",
        "review_timestamp_utc",
        "review_label",
        "preview_state",
        "mapping_version",
        "tier_hint",
        "review_age_days",
        "review_stale",
        "multiple_operators_for_slice",
        "notes",
    )
    assert constants.PREVIEW_CANDIDATES_CSV_COLUMNS == expected
    assert len(constants.PREVIEW_CANDIDATES_CSV_COLUMNS) == 18


def test_alert_eligibility_decisions_csv_columns_locked_order():
    expected = (
        "decision_id",
        "candidate_id",
        "stage20_run_id",
        "decision_step_index",
        "decision_step_name",
        "decision_step_state",
        "decision_step_terminating",
        "decision_outcome",
        "evidence_code",
        "evidence_detail",
    )
    assert constants.ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS == expected
    assert len(constants.ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS) == 10


# ---------------------------------------------------------------------------
# Decision-step vocabulary locks
# ---------------------------------------------------------------------------


def test_decision_step_names_4_is_locked_chain():
    assert constants.DECISION_STEP_NAMES_4 == (
        "slice_resolved",
        "mapping_applied",
        "staleness_evaluated",
        "terminal",
    )


def test_decision_step_names_2_is_locked_chain():
    assert constants.DECISION_STEP_NAMES_2 == (
        "mapping_applied",
        "terminal",
    )


def test_decision_step_states_locked():
    assert constants.DECISION_STEP_STATES == (
        "entered",
        "passed",
        "failed",
        "terminal",
    )


# ---------------------------------------------------------------------------
# Manifest key-group locks
# ---------------------------------------------------------------------------


def test_manifest_required_input_hash_keys():
    assert constants.MANIFEST_REQUIRED_INPUT_HASH_KEYS == (
        "stage18_manifest_sha256",
        "stage18_review_matrix_sha256",
        "stage19_ledger_sha256",
        "stage19_manifest_sha256",
    )


def test_manifest_required_output_hash_keys():
    assert constants.MANIFEST_REQUIRED_OUTPUT_HASH_KEYS == (
        "preview_candidates_csv_sha256",
        "alert_eligibility_decisions_csv_sha256",
        "readme_md_sha256",
        "stage20_run_log_sha256",
    )


def test_manifest_warning_keys():
    assert constants.MANIFEST_WARNING_KEYS == (
        "W2001_run_median_staleness_exceeded",
        "W2002_preview_eligible_count_zero",
        "W2003_tier_hint_missing_count",
        "W2004_multiple_operators_per_review_slice_count",
        "W2005_stage18_evidence_missing_for_review_count",
        "W2006_candidate_review_stale_count",
        "W2007_eligibility_mapping_drift_detected",
    )


def test_preview_state_count_keys():
    assert constants.PREVIEW_STATE_COUNT_KEYS == (
        "PREVIEW_ELIGIBLE",
        "PREVIEW_OBSERVE_ONLY",
        "PREVIEW_NEEDS_MORE_DATA",
        "PREVIEW_EXCLUDED",
    )


def test_stage20_run_log_event_sequence_locked():
    assert constants.STAGE20_RUN_LOG_EVENT_SEQUENCE == (
        "run_started",
        "inputs_validated",
        "slices_resolved",
        "candidates_built",
        "decisions_built",
        "warnings_emitted",
        "artifacts_written",
        "manifest_written",
        "run_completed",
    )
    assert len(constants.STAGE20_RUN_LOG_EVENT_SEQUENCE) == 9


# ---------------------------------------------------------------------------
# Forbidden symbols (must remain absent)
#
# The forbidden code is constructed via string concatenation so this
# test source does not itself contain the literal token -- Phase D's
# grep ``grep -rn "<token>" PHX2/`` would otherwise pick up these
# tests as false positives.
# ---------------------------------------------------------------------------


def _forbidden_extra_e_code() -> str:
    # Build "E" + "2026" at runtime; never as a contiguous source literal.
    return "E" + str(2026)


def test_forbidden_extra_e_code_absent_from_error_code_enum():
    """The extra E-code reserved-out by Hard Constraint #6 must never
    enter the EligibilityErrorCode enum under any name.
    """

    forbidden = _forbidden_extra_e_code()
    values = {m.value for m in constants.EligibilityErrorCode}
    assert forbidden not in values
    names = {m.name for m in constants.EligibilityErrorCode}
    assert forbidden not in names


def test_forbidden_extra_e_code_string_absent_from_constants_source():
    """Belt-and-braces: the forbidden token must not appear as a
    literal anywhere in constants.py.
    """

    import pathlib

    src = pathlib.Path(constants.__file__).read_text(encoding="utf-8")
    forbidden = _forbidden_extra_e_code()
    pattern = re.compile(r"\b" + re.escape(forbidden) + r"\b")
    assert pattern.search(src) is None
