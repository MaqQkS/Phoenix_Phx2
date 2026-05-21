"""Stage 26.3 calibration cohort closed sets.

Stage 26.3 declares the closed-set vocabularies the calibration
cohort builder consumes. Every token is uppercase ASCII; every
aggregate is an immutable ``tuple[str, ...]`` so the boundary
scanner reads it as structural data rather than runtime-mutable
state.

Closed sets declared here:

  * ``COHORT_DIMENSIONS``         -- the set of dimensions the
                                     builder may group rows by.
                                     Every dimension corresponds to
                                     a Stage 26.2
                                     ``Stage26EligibilityRow`` field
                                     the builder may read; no other
                                     row field is permitted as a
                                     grouping key.
  * ``COHORT_STATUSES``           -- the per-cohort outcome states
                                     ``Stage26CohortSummary.cohort_status``
                                     may carry.
  * ``COHORT_ROW_STATUSES``       -- per-row inclusion outcomes the
                                     builder records on each cohort
                                     member. Stage 26.3 NEVER labels
                                     a non-``MEASURED`` truth-class
                                     row as a failure -- the only
                                     "excluded" row status is
                                     ``EXCLUDED_INVALID_INPUT`` and
                                     it ONLY applies to rows whose
                                     denominator / outcome / truth-
                                     class tokens are outside the
                                     locked Stage 26.2 closed sets.
  * ``STAGE26_COHORT_ERROR_CODES`` -- the typed-error code tokens the
                                      Stage 26.3 cohort builder may
                                      raise. Codes inherit the
                                      Stage 26 ``STG26_CAL_`` prefix
                                      so callers can dispatch on the
                                      Stage 26 error code namespace.

Stage 26.3 does NOT declare:

  * any threshold candidate vocabulary -- Stage 26.4.
  * any policy candidate vocabulary    -- Stage 26.5.
  * any approval-state vocabulary      -- Stage 26.6.
  * any enforcement / dispatch tokens  -- Stage 29+ (never in 26).

Stage 26.3 imports nothing from ``PHX2.stage25`` directly -- Stage 25
vocabulary continues to route through
``PHX2.stage26.constants.MEASUREMENT_TRUTH_CLASSES`` (which itself
flows through ``PHX2.stage26.stage25_schema_whitelist`` per Stage
26.0 spec-lock §8). Stage 26.3 NEVER renames or upgrades a Stage 25
truth class.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 26.3 version axis
# ---------------------------------------------------------------------------


STAGE26_COHORT_VERSION: str = "stage26_cohort_v0"


# Deterministic-ordering version. Bumping the deterministic ordering
# convention used by the cohort builder (e.g. the lexicographic sort
# on cohort keys) requires bumping this axis so downstream Stage 26.x
# consumers can pin the exact ordering they consumed.
STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION: str = (
    "stage26_cohort_ordering_v0"
)


# ---------------------------------------------------------------------------
# COHORT_DIMENSIONS -- locked grouping dimensions
# ---------------------------------------------------------------------------


COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS: str = "MEASUREMENT_TRUTH_CLASS"
COHORT_DIMENSION_DENOMINATOR_STATUS: str = "DENOMINATOR_STATUS"
COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS: str = (
    "OUTCOME_ELIGIBILITY_STATUS"
)
COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON: str = (
    "PRIMARY_DENOMINATOR_REASON"
)
COHORT_DIMENSION_SOURCE_ARTIFACT_KIND: str = "SOURCE_ARTIFACT_KIND"
COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY: str = (
    "THRESHOLD_CALIBRATION_ELIGIBILITY"
)
COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY: str = (
    "PRIMARY_METRICS_ELIGIBILITY"
)
COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY: str = (
    "OBSERVABILITY_METRICS_ELIGIBILITY"
)


COHORT_DIMENSIONS: tuple[str, ...] = (
    COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS,
    COHORT_DIMENSION_DENOMINATOR_STATUS,
    COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS,
    COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON,
    COHORT_DIMENSION_SOURCE_ARTIFACT_KIND,
    COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY,
    COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY,
    COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY,
)


# Canonical string encoding the cohort builder uses for boolean
# eligibility-flag values when they appear in a cohort key. Stage
# 26.3 uses uppercase ``TRUE`` / ``FALSE`` so the cohort-key values
# tuple is a uniform tuple of uppercase ASCII strings; Python's
# default ``str(True)`` would emit ``"True"`` / ``"False"`` which
# would mix case with the other uppercase tokens.
COHORT_BOOL_VALUE_TRUE: str = "TRUE"
COHORT_BOOL_VALUE_FALSE: str = "FALSE"


# ---------------------------------------------------------------------------
# COHORT_STATUSES -- per-cohort outcome states
# ---------------------------------------------------------------------------


COHORT_STATUS_VALID_COHORT: str = "VALID_COHORT"
COHORT_STATUS_EMPTY_COHORT: str = "EMPTY_COHORT"
COHORT_STATUS_INVALID_COHORT_KEY: str = "INVALID_COHORT_KEY"
COHORT_STATUS_MIXED_MANIFEST_HASH: str = "MIXED_MANIFEST_HASH"
COHORT_STATUS_MIXED_DIMENSION_SHAPE: str = "MIXED_DIMENSION_SHAPE"


COHORT_STATUSES: tuple[str, ...] = (
    COHORT_STATUS_VALID_COHORT,
    COHORT_STATUS_EMPTY_COHORT,
    COHORT_STATUS_INVALID_COHORT_KEY,
    COHORT_STATUS_MIXED_MANIFEST_HASH,
    COHORT_STATUS_MIXED_DIMENSION_SHAPE,
)


# ---------------------------------------------------------------------------
# COHORT_ROW_STATUSES -- per-row inclusion outcomes
# ---------------------------------------------------------------------------


COHORT_ROW_STATUS_INCLUDED_IN_COHORT: str = "INCLUDED_IN_COHORT"
COHORT_ROW_STATUS_EXCLUDED_INVALID_INPUT: str = (
    "EXCLUDED_INVALID_INPUT"
)


COHORT_ROW_STATUSES: tuple[str, ...] = (
    COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    COHORT_ROW_STATUS_EXCLUDED_INVALID_INPUT,
)


# ---------------------------------------------------------------------------
# STAGE26_COHORT_ERROR_CODES -- typed-error code tokens
# ---------------------------------------------------------------------------


STG26_CAL_COHORT_UNKNOWN_DIMENSION: str = (
    "STG26_CAL_COHORT_UNKNOWN_DIMENSION"
)
STG26_CAL_COHORT_EMPTY_INPUT: str = "STG26_CAL_COHORT_EMPTY_INPUT"
STG26_CAL_COHORT_MIXED_MANIFEST_HASH: str = (
    "STG26_CAL_COHORT_MIXED_MANIFEST_HASH"
)
STG26_CAL_COHORT_INVALID_KEY: str = "STG26_CAL_COHORT_INVALID_KEY"
STG26_CAL_COHORT_UNSUPPORTED_STATUS: str = (
    "STG26_CAL_COHORT_UNSUPPORTED_STATUS"
)


STAGE26_COHORT_ERROR_CODES: tuple[str, ...] = (
    STG26_CAL_COHORT_UNKNOWN_DIMENSION,
    STG26_CAL_COHORT_EMPTY_INPUT,
    STG26_CAL_COHORT_MIXED_MANIFEST_HASH,
    STG26_CAL_COHORT_INVALID_KEY,
    STG26_CAL_COHORT_UNSUPPORTED_STATUS,
)


__all__ = [
    "COHORT_BOOL_VALUE_FALSE",
    "COHORT_BOOL_VALUE_TRUE",
    "COHORT_DIMENSIONS",
    "COHORT_DIMENSION_DENOMINATOR_STATUS",
    "COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS",
    "COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY",
    "COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS",
    "COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON",
    "COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY",
    "COHORT_DIMENSION_SOURCE_ARTIFACT_KIND",
    "COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY",
    "COHORT_ROW_STATUSES",
    "COHORT_ROW_STATUS_EXCLUDED_INVALID_INPUT",
    "COHORT_ROW_STATUS_INCLUDED_IN_COHORT",
    "COHORT_STATUSES",
    "COHORT_STATUS_EMPTY_COHORT",
    "COHORT_STATUS_INVALID_COHORT_KEY",
    "COHORT_STATUS_MIXED_DIMENSION_SHAPE",
    "COHORT_STATUS_MIXED_MANIFEST_HASH",
    "COHORT_STATUS_VALID_COHORT",
    "STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION",
    "STAGE26_COHORT_ERROR_CODES",
    "STAGE26_COHORT_VERSION",
    "STG26_CAL_COHORT_EMPTY_INPUT",
    "STG26_CAL_COHORT_INVALID_KEY",
    "STG26_CAL_COHORT_MIXED_MANIFEST_HASH",
    "STG26_CAL_COHORT_UNKNOWN_DIMENSION",
    "STG26_CAL_COHORT_UNSUPPORTED_STATUS",
]
