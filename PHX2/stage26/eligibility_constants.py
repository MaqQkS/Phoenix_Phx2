"""Stage 26.2 denominator / outcome-eligibility closed sets.

Stage 26.2 locks the closed-set vocabularies the denominator-honesty
surface depends on. Every token is uppercase ASCII; every aggregate
is an immutable ``tuple[str, ...]`` so the boundary scanner reads
it as structural data, not runtime-mutable state.

Closed sets declared here:

  * ``DENOMINATOR_STATUSES``          -- per-row denominator bucket.
  * ``OUTCOME_ELIGIBILITY_STATUSES``  -- per-row outcome bucket.
  * ``PRIMARY_DENOMINATOR_REASONS``   -- closed reason codes for why
                                         a row is or is not primary-
                                         denominator eligible.
  * ``CALIBRATION_ELIGIBILITY_KINDS`` -- coarser secondary slicing
                                         the eligibility decision
                                         record carries alongside
                                         the bool flags.
  * ``ELIGIBILITY_DECISION_BY_TRUTH_CLASS`` -- locked truth-class to
                                         eligibility-decision
                                         mapping. The mapping is
                                         declared as an immutable
                                         tuple-of-tuples so it can
                                         be statically read by both
                                         the classifier and the
                                         Stage 26.2 tests.

Stage 26.2 does NOT declare:

  * any cohort vocabulary              -- Stage 26.3.
  * any threshold vocabulary           -- Stage 26.4.
  * any policy-candidate vocabulary    -- Stage 26.5.
  * any approval-state vocabulary      -- Stage 26.6.
  * any enforcement / dispatch tokens  -- Stage 29+ (never in 26).

Stage 26.2 imports nothing from ``PHX2.stage25`` directly -- the
Stage 25 measurement-truth vocabulary continues to route through
``PHX2.stage26.constants.MEASUREMENT_TRUTH_CLASSES`` (which itself
flows through ``PHX2.stage26.stage25_schema_whitelist`` per Stage
26.0 spec-lock §8). Stage 26.2 NEVER renames or upgrades a Stage 25
truth class.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 26.2 version axis
# ---------------------------------------------------------------------------


STAGE26_ELIGIBILITY_VERSION: str = "stage26_eligibility_v0"


# ---------------------------------------------------------------------------
# DENOMINATOR_STATUSES -- per-row denominator bucket
# ---------------------------------------------------------------------------


DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR: str = (
    "PRIMARY_MEASURED_DENOMINATOR"
)
DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR: str = (
    "OBSERVABILITY_DENOMINATOR"
)
DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR: str = (
    "COVERAGE_GAP_DENOMINATOR"
)
DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR: str = (
    "SCOPE_GAP_DENOMINATOR"
)
DENOMINATOR_STATUS_REJECTION_DENOMINATOR: str = (
    "REJECTION_DENOMINATOR"
)
DENOMINATOR_STATUS_EXCLUDED_FROM_PRIMARY_DENOMINATOR: str = (
    "EXCLUDED_FROM_PRIMARY_DENOMINATOR"
)


DENOMINATOR_STATUSES: tuple[str, ...] = (
    DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR,
    DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
    DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR,
    DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR,
    DENOMINATOR_STATUS_REJECTION_DENOMINATOR,
    DENOMINATOR_STATUS_EXCLUDED_FROM_PRIMARY_DENOMINATOR,
)


# ---------------------------------------------------------------------------
# OUTCOME_ELIGIBILITY_STATUSES -- per-row outcome bucket
# ---------------------------------------------------------------------------


OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE: str = (
    "PRIMARY_OUTCOME_ELIGIBLE"
)
OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY: str = (
    "OBSERVABILITY_ONLY"
)
OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY: str = (
    "COVERAGE_GAP_ONLY"
)
OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY: str = "SCOPE_GAP_ONLY"
OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY: str = "REJECTION_ONLY"
OUTCOME_ELIGIBILITY_STATUS_INELIGIBLE_INVALID_INPUT: str = (
    "INELIGIBLE_INVALID_INPUT"
)


OUTCOME_ELIGIBILITY_STATUSES: tuple[str, ...] = (
    OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE,
    OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY,
    OUTCOME_ELIGIBILITY_STATUS_INELIGIBLE_INVALID_INPUT,
)


# ---------------------------------------------------------------------------
# PRIMARY_DENOMINATOR_REASONS -- closed reason codes
# ---------------------------------------------------------------------------


PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH: str = "MEASURED_TRUTH"
PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL: str = (
    "NOT_MEASURED_PARTIAL"
)
PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT: str = (
    "NOT_MEASURED_SOURCE_CONFLICT"
)
PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS: str = (
    "NOT_MEASURED_AMBIGUOUS"
)
PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_WINDOW_INELIGIBLE: str = (
    "NOT_MEASURED_WINDOW_INELIGIBLE"
)
PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT: str = (
    "MISSING_MEASUREMENT"
)
PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT: str = (
    "UNSUPPORTED_MEASUREMENT"
)
PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT: str = (
    "REJECTED_MEASUREMENT"
)
PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT: str = (
    "NOT_APPLICABLE_MEASUREMENT"
)
PRIMARY_DENOMINATOR_REASON_INVALID_INPUT_RECORD: str = (
    "INVALID_INPUT_RECORD"
)


PRIMARY_DENOMINATOR_REASONS: tuple[str, ...] = (
    PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS,
    PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_WINDOW_INELIGIBLE,
    PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT,
    PRIMARY_DENOMINATOR_REASON_INVALID_INPUT_RECORD,
)


# ---------------------------------------------------------------------------
# CALIBRATION_ELIGIBILITY_KINDS -- coarser secondary slice
# ---------------------------------------------------------------------------


CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE: str = (
    "THRESHOLD_CALIBRATION_ELIGIBLE"
)
CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY: str = (
    "OBSERVABILITY_CONTEXT_ONLY"
)
CALIBRATION_ELIGIBILITY_KIND_COVERAGE_CONTEXT_ONLY: str = (
    "COVERAGE_CONTEXT_ONLY"
)
CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY: str = (
    "SCOPE_CONTEXT_ONLY"
)
CALIBRATION_ELIGIBILITY_KIND_REJECTION_CONTEXT_ONLY: str = (
    "REJECTION_CONTEXT_ONLY"
)
CALIBRATION_ELIGIBILITY_KIND_INVALID_CONTEXT_ONLY: str = (
    "INVALID_CONTEXT_ONLY"
)


CALIBRATION_ELIGIBILITY_KINDS: tuple[str, ...] = (
    CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE,
    CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_COVERAGE_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_REJECTION_CONTEXT_ONLY,
    CALIBRATION_ELIGIBILITY_KIND_INVALID_CONTEXT_ONLY,
)


# ---------------------------------------------------------------------------
# Locked truth-class -> eligibility decision mapping
# ---------------------------------------------------------------------------
#
# Each entry is a tuple ordered:
#   (
#     measurement_truth_class,
#     denominator_status,
#     outcome_eligibility_status,
#     primary_denominator_reason,
#     calibration_eligibility_kind,
#     eligible_for_threshold_calibration,
#     eligible_for_primary_metrics,
#     eligible_for_observability_metrics,
#   )
#
# Stage 25's measurement-truth tokens (locked Stage 25 ``MEASUREMENT_
# STATUSES`` tuple) are repeated as string literals here so the
# mapping is self-evident at module read time. The Stage 26.2
# classifier test verifies the truth-class column matches the
# Stage 26.1 ``MEASUREMENT_TRUTH_CLASSES`` tuple exactly; if Stage 25
# ever extends its measurement-status vocabulary, the test fails and
# Stage 26.2 must extend this mapping in the same commit.
#
# WINDOW_INELIGIBLE is NOT a Stage 25 measurement-status token --
# Stage 25 expresses window-ineligibility through PRICE_WINDOW_KINDS
# and downstream MEASUREMENT_STATUS_REJECTED / _MISSING per Stage
# 26.0 spec-lock §10. The reason code
# NOT_MEASURED_WINDOW_INELIGIBLE is reserved in the closed reason set
# for a future Stage 26.x sub-stage that wants to surface that
# distinction without recomputing the measurement.


ELIGIBILITY_DECISION_BY_TRUTH_CLASS: tuple[
    tuple[str, str, str, str, str, bool, bool, bool], ...
] = (
    (
        "MEASURED",
        DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE,
        PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH,
        CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE,
        True,
        True,
        True,
    ),
    (
        "PARTIAL",
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL,
        CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY,
        False,
        False,
        True,
    ),
    (
        "UNSUPPORTED",
        DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY,
        PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT,
        CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY,
        False,
        False,
        False,
    ),
    (
        "AMBIGUOUS",
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS,
        CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY,
        False,
        False,
        True,
    ),
    (
        "SOURCE_CONFLICT",
        DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY,
        PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT,
        CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY,
        False,
        False,
        True,
    ),
    (
        "MISSING",
        DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY,
        PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT,
        CALIBRATION_ELIGIBILITY_KIND_COVERAGE_CONTEXT_ONLY,
        False,
        False,
        False,
    ),
    (
        "REJECTED",
        DENOMINATOR_STATUS_REJECTION_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY,
        PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT,
        CALIBRATION_ELIGIBILITY_KIND_REJECTION_CONTEXT_ONLY,
        False,
        False,
        False,
    ),
    (
        "NOT_APPLICABLE",
        DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR,
        OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY,
        PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT,
        CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY,
        False,
        False,
        False,
    ),
)


__all__ = [
    "CALIBRATION_ELIGIBILITY_KINDS",
    "CALIBRATION_ELIGIBILITY_KIND_COVERAGE_CONTEXT_ONLY",
    "CALIBRATION_ELIGIBILITY_KIND_INVALID_CONTEXT_ONLY",
    "CALIBRATION_ELIGIBILITY_KIND_OBSERVABILITY_CONTEXT_ONLY",
    "CALIBRATION_ELIGIBILITY_KIND_REJECTION_CONTEXT_ONLY",
    "CALIBRATION_ELIGIBILITY_KIND_SCOPE_CONTEXT_ONLY",
    "CALIBRATION_ELIGIBILITY_KIND_THRESHOLD_CALIBRATION_ELIGIBLE",
    "DENOMINATOR_STATUSES",
    "DENOMINATOR_STATUS_COVERAGE_GAP_DENOMINATOR",
    "DENOMINATOR_STATUS_EXCLUDED_FROM_PRIMARY_DENOMINATOR",
    "DENOMINATOR_STATUS_OBSERVABILITY_DENOMINATOR",
    "DENOMINATOR_STATUS_PRIMARY_MEASURED_DENOMINATOR",
    "DENOMINATOR_STATUS_REJECTION_DENOMINATOR",
    "DENOMINATOR_STATUS_SCOPE_GAP_DENOMINATOR",
    "ELIGIBILITY_DECISION_BY_TRUTH_CLASS",
    "OUTCOME_ELIGIBILITY_STATUSES",
    "OUTCOME_ELIGIBILITY_STATUS_COVERAGE_GAP_ONLY",
    "OUTCOME_ELIGIBILITY_STATUS_INELIGIBLE_INVALID_INPUT",
    "OUTCOME_ELIGIBILITY_STATUS_OBSERVABILITY_ONLY",
    "OUTCOME_ELIGIBILITY_STATUS_PRIMARY_OUTCOME_ELIGIBLE",
    "OUTCOME_ELIGIBILITY_STATUS_REJECTION_ONLY",
    "OUTCOME_ELIGIBILITY_STATUS_SCOPE_GAP_ONLY",
    "PRIMARY_DENOMINATOR_REASONS",
    "PRIMARY_DENOMINATOR_REASON_INVALID_INPUT_RECORD",
    "PRIMARY_DENOMINATOR_REASON_MEASURED_TRUTH",
    "PRIMARY_DENOMINATOR_REASON_MISSING_MEASUREMENT",
    "PRIMARY_DENOMINATOR_REASON_NOT_APPLICABLE_MEASUREMENT",
    "PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_AMBIGUOUS",
    "PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_PARTIAL",
    "PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_SOURCE_CONFLICT",
    "PRIMARY_DENOMINATOR_REASON_NOT_MEASURED_WINDOW_INELIGIBLE",
    "PRIMARY_DENOMINATOR_REASON_REJECTED_MEASUREMENT",
    "PRIMARY_DENOMINATOR_REASON_UNSUPPORTED_MEASUREMENT",
    "STAGE26_ELIGIBILITY_VERSION",
]
