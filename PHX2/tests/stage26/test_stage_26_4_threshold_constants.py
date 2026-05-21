"""Stage 26.4 threshold-constants tests.

Pins the locked Stage 26.4 closed sets and typed-error code tokens in
``PHX2/stage26/threshold_constants.py``.
"""

from __future__ import annotations

from PHX2.stage26.threshold_constants import (
    DEFAULT_MAX_AMBIGUOUS_RATE,
    DEFAULT_MAX_COVERAGE_GAP_RATE,
    DEFAULT_MAX_REJECTION_RATE,
    DEFAULT_MAX_SCOPE_GAP_RATE,
    DEFAULT_MAX_SOURCE_CONFLICT_RATE,
    DEFAULT_MIN_OBSERVABILITY_RATE,
    DEFAULT_MIN_PRIMARY_MEASURED_COUNT,
    DEFAULT_MIN_THRESHOLD_ELIGIBLE_COUNT,
    DEFAULT_MIN_TOTAL_ROWS,
    STAGE26_CANDIDATE_GENERATION_VERSION,
    STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_THRESHOLD_ERROR_CODES,
    STAGE26_THRESHOLD_VERSION,
    STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS,
    STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
    STG26_CAL_THRESHOLD_INVALID_DIRECTION,
    STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH,
    STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY,
    STG26_CAL_THRESHOLD_POLICY_LEAK,
    STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
    THRESHOLD_CANDIDATE_KINDS,
    THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE,
    THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE,
    THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT,
    THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT,
    THRESHOLD_CANDIDATE_STATUSES,
    THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
    THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
    THRESHOLD_DIRECTIONS,
    THRESHOLD_DIRECTION_MAXIMUM,
    THRESHOLD_DIRECTION_MINIMUM,
    THRESHOLD_EVIDENCE_CLASSES,
    THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
    THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
    THRESHOLD_REVIEW_READINESSES,
    THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
    THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
    THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
    THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
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


def test_threshold_candidate_kinds_closed_set_shape():
    _assert_closed_set(THRESHOLD_CANDIDATE_KINDS)


def test_threshold_candidate_statuses_closed_set_shape():
    _assert_closed_set(THRESHOLD_CANDIDATE_STATUSES)


def test_threshold_evidence_classes_closed_set_shape():
    _assert_closed_set(THRESHOLD_EVIDENCE_CLASSES)


def test_threshold_directions_closed_set_shape():
    _assert_closed_set(THRESHOLD_DIRECTIONS)


def test_threshold_review_readinesses_closed_set_shape():
    _assert_closed_set(THRESHOLD_REVIEW_READINESSES)


def test_stage26_threshold_error_codes_closed_set_shape():
    _assert_closed_set(STAGE26_THRESHOLD_ERROR_CODES)


# ---------------------------------------------------------------------------
# Closed-set membership
# ---------------------------------------------------------------------------


def test_threshold_candidate_kinds_lock_membership():
    assert set(THRESHOLD_CANDIDATE_KINDS) == {
        THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT,
        THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT,
        THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE,
        THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE,
        THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE,
        THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE,
        THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE,
        THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE,
    }


def test_threshold_candidate_statuses_lock_membership():
    assert set(THRESHOLD_CANDIDATE_STATUSES) == {
        THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
        THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
        THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
        THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT,
        THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
        THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
        THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
    }


def test_threshold_evidence_classes_lock_membership():
    assert set(THRESHOLD_EVIDENCE_CLASSES) == {
        THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
        THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
        THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
        THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
        THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
        THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
    }


def test_threshold_directions_lock_membership():
    assert set(THRESHOLD_DIRECTIONS) == {
        THRESHOLD_DIRECTION_MINIMUM,
        THRESHOLD_DIRECTION_MAXIMUM,
    }


def test_threshold_review_readinesses_lock_membership():
    assert set(THRESHOLD_REVIEW_READINESSES) == {
        THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
        THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
        THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
        THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
        THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
        THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW,
    }


def test_threshold_error_codes_lock_membership():
    assert set(STAGE26_THRESHOLD_ERROR_CODES) == {
        STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
        STG26_CAL_THRESHOLD_INVALID_DIRECTION,
        STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS,
        STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH,
        STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY,
        STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
        STG26_CAL_THRESHOLD_POLICY_LEAK,
    }


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_stage26_threshold_version_axis():
    assert STAGE26_THRESHOLD_VERSION == "stage26_threshold_v0"


def test_stage26_threshold_deterministic_ordering_version_axis():
    assert (
        STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
        == "stage26_threshold_ordering_v0"
    )


def test_stage26_candidate_generation_version_axis():
    assert (
        STAGE26_CANDIDATE_GENERATION_VERSION
        == "stage26_threshold_generation_v0"
    )


# ---------------------------------------------------------------------------
# Error code prefix discipline
# ---------------------------------------------------------------------------


def test_threshold_error_codes_carry_stage26_prefix():
    for code in STAGE26_THRESHOLD_ERROR_CODES:
        assert code.startswith("STG26_CAL_"), (
            f"{code!r} must carry the Stage 26 STG26_CAL_ prefix"
        )
        assert "THRESHOLD" in code, (
            f"{code!r} must mention THRESHOLD to disambiguate from "
            "Stage 26.1 / 26.2 / 26.3 codes"
        )


# ---------------------------------------------------------------------------
# Default candidate-generation knobs
# ---------------------------------------------------------------------------


def test_default_knobs_are_deterministic_non_policy_values():
    # Counts are non-negative integers.
    assert isinstance(DEFAULT_MIN_TOTAL_ROWS, int)
    assert DEFAULT_MIN_TOTAL_ROWS >= 0
    assert isinstance(DEFAULT_MIN_PRIMARY_MEASURED_COUNT, int)
    assert DEFAULT_MIN_PRIMARY_MEASURED_COUNT >= 0
    assert isinstance(DEFAULT_MIN_THRESHOLD_ELIGIBLE_COUNT, int)
    assert DEFAULT_MIN_THRESHOLD_ELIGIBLE_COUNT >= 0
    # Rates are floats in [0.0, 1.0].
    for rate in (
        DEFAULT_MAX_COVERAGE_GAP_RATE,
        DEFAULT_MAX_SCOPE_GAP_RATE,
        DEFAULT_MAX_REJECTION_RATE,
        DEFAULT_MAX_SOURCE_CONFLICT_RATE,
        DEFAULT_MAX_AMBIGUOUS_RATE,
        DEFAULT_MIN_OBSERVABILITY_RATE,
    ):
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 1.0


def test_default_knobs_are_conservative_on_caveat_rates():
    # The MAX_* rate defaults are permissive (no suppression by
    # default) so the operator opts into stricter rates explicitly.
    assert DEFAULT_MAX_COVERAGE_GAP_RATE == 1.0
    assert DEFAULT_MAX_SCOPE_GAP_RATE == 1.0
    assert DEFAULT_MAX_REJECTION_RATE == 1.0
    assert DEFAULT_MAX_SOURCE_CONFLICT_RATE == 1.0
    assert DEFAULT_MAX_AMBIGUOUS_RATE == 1.0
    # MIN_* observability rate defaults to 0.0 so empty cohorts do
    # not appear failed on the observability axis by default.
    assert DEFAULT_MIN_OBSERVABILITY_RATE == 0.0


# ---------------------------------------------------------------------------
# Stage 26.4 must not introduce Stage 26.5+ vocabulary
# ---------------------------------------------------------------------------


def test_threshold_constants_carry_no_policy_artifact_or_approval_vocabulary():
    """The threshold constants module must not introduce Stage 26.5+
    policy / approval / enforcement / dispatch vocabulary beyond the
    explicit forward-pointing readiness token
    ``READY_FOR_POLICY_CANDIDATE_REVIEW``.
    """
    import PHX2.stage26.threshold_constants as threshold_constants

    forbidden_substrings = (
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
    names = dir(threshold_constants)
    for name in names:
        lower = name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lower, (
                f"threshold_constants exposes Stage 26.5+ vocabulary "
                f"in {name!r} (forbidden substring {forbidden!r})"
            )
