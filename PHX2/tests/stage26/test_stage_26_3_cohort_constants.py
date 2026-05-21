"""Stage 26.3 cohort-constants tests.

Pins the locked Stage 26.3 closed sets and typed-error code tokens in
``PHX2/stage26/cohort_constants.py``.
"""

from __future__ import annotations

from PHX2.stage26.cohort_constants import (
    COHORT_BOOL_VALUE_FALSE,
    COHORT_BOOL_VALUE_TRUE,
    COHORT_DIMENSIONS,
    COHORT_DIMENSION_DENOMINATOR_STATUS,
    COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS,
    COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY,
    COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS,
    COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON,
    COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY,
    COHORT_DIMENSION_SOURCE_ARTIFACT_KIND,
    COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY,
    COHORT_ROW_STATUSES,
    COHORT_ROW_STATUS_EXCLUDED_INVALID_INPUT,
    COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    COHORT_STATUSES,
    COHORT_STATUS_EMPTY_COHORT,
    COHORT_STATUS_INVALID_COHORT_KEY,
    COHORT_STATUS_MIXED_DIMENSION_SHAPE,
    COHORT_STATUS_MIXED_MANIFEST_HASH,
    COHORT_STATUS_VALID_COHORT,
    STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_COHORT_ERROR_CODES,
    STAGE26_COHORT_VERSION,
    STG26_CAL_COHORT_EMPTY_INPUT,
    STG26_CAL_COHORT_INVALID_KEY,
    STG26_CAL_COHORT_MIXED_MANIFEST_HASH,
    STG26_CAL_COHORT_UNKNOWN_DIMENSION,
    STG26_CAL_COHORT_UNSUPPORTED_STATUS,
)


# ---------------------------------------------------------------------------
# Closed-set shape helpers
# ---------------------------------------------------------------------------


def _assert_closed_set(tokens: tuple[str, ...]) -> None:
    assert isinstance(tokens, tuple), "closed sets must be tuples"
    assert len(tokens) > 0, "closed sets must be non-empty"
    assert len(set(tokens)) == len(tokens), "no duplicate tokens"
    for token in tokens:
        assert isinstance(token, str)
        assert token != ""
        assert token == token.upper(), f"{token!r} must be uppercase"
        assert " " not in token


# ---------------------------------------------------------------------------
# Closed-set shape
# ---------------------------------------------------------------------------


def test_cohort_dimensions_closed_set_shape():
    _assert_closed_set(COHORT_DIMENSIONS)


def test_cohort_statuses_closed_set_shape():
    _assert_closed_set(COHORT_STATUSES)


def test_cohort_row_statuses_closed_set_shape():
    _assert_closed_set(COHORT_ROW_STATUSES)


def test_stage26_cohort_error_codes_closed_set_shape():
    _assert_closed_set(STAGE26_COHORT_ERROR_CODES)


# ---------------------------------------------------------------------------
# Closed-set membership
# ---------------------------------------------------------------------------


def test_cohort_dimensions_lock_membership():
    assert set(COHORT_DIMENSIONS) == {
        COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS,
        COHORT_DIMENSION_DENOMINATOR_STATUS,
        COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS,
        COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON,
        COHORT_DIMENSION_SOURCE_ARTIFACT_KIND,
        COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY,
        COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY,
        COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY,
    }


def test_cohort_statuses_lock_membership():
    assert set(COHORT_STATUSES) == {
        COHORT_STATUS_VALID_COHORT,
        COHORT_STATUS_EMPTY_COHORT,
        COHORT_STATUS_INVALID_COHORT_KEY,
        COHORT_STATUS_MIXED_MANIFEST_HASH,
        COHORT_STATUS_MIXED_DIMENSION_SHAPE,
    }


def test_cohort_row_statuses_lock_membership():
    assert set(COHORT_ROW_STATUSES) == {
        COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
        COHORT_ROW_STATUS_EXCLUDED_INVALID_INPUT,
    }


def test_cohort_error_codes_lock_membership():
    assert set(STAGE26_COHORT_ERROR_CODES) == {
        STG26_CAL_COHORT_UNKNOWN_DIMENSION,
        STG26_CAL_COHORT_EMPTY_INPUT,
        STG26_CAL_COHORT_MIXED_MANIFEST_HASH,
        STG26_CAL_COHORT_INVALID_KEY,
        STG26_CAL_COHORT_UNSUPPORTED_STATUS,
    }


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_stage26_cohort_version_axis():
    assert STAGE26_COHORT_VERSION == "stage26_cohort_v0"


def test_stage26_cohort_deterministic_ordering_version_axis():
    assert (
        STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION
        == "stage26_cohort_ordering_v0"
    )


# ---------------------------------------------------------------------------
# Bool value tokens
# ---------------------------------------------------------------------------


def test_cohort_bool_value_tokens_are_uppercase():
    assert COHORT_BOOL_VALUE_TRUE == "TRUE"
    assert COHORT_BOOL_VALUE_FALSE == "FALSE"


# ---------------------------------------------------------------------------
# Error code prefix discipline
# ---------------------------------------------------------------------------


def test_cohort_error_codes_carry_stage26_prefix():
    for code in STAGE26_COHORT_ERROR_CODES:
        assert code.startswith("STG26_CAL_"), (
            f"{code!r} must carry the Stage 26 STG26_CAL_ prefix"
        )
        assert "COHORT" in code, (
            f"{code!r} must mention COHORT to disambiguate from "
            "Stage 26.1 / 26.2 codes"
        )


# ---------------------------------------------------------------------------
# Stage 26.3 must not introduce Stage 26.4+ vocabulary
# ---------------------------------------------------------------------------


def test_cohort_constants_carry_no_threshold_or_policy_vocabulary():
    """The cohort constants module must not introduce Stage 26.4+
    vocabulary (threshold candidate / policy candidate / approval
    state / enforcement / dispatch).
    """
    import PHX2.stage26.cohort_constants as cohort_constants

    forbidden_substrings = (
        "threshold_candidate",
        "policy_candidate",
        "approval_state",
        "approved_by",
        "enforcement",
        "enforcer",
        "dispatcher",
        "telegram",
        "discord",
        "axiom",
        "jito",
        "compute_budget",
        "router_fee",
        "tweet",
        "twitter",
        "x_api",
        "subscriber_tier",
        "ratchet",
    )
    names = dir(cohort_constants)
    for name in names:
        lower = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lower, (
                f"cohort_constants exposes Stage 26.4+ vocabulary in "
                f"{name!r} (forbidden substring {forbidden!r})"
            )
