"""Stage 26.4 threshold candidate closed sets.

Stage 26.4 declares the closed-set vocabularies the threshold
candidate generator consumes and emits. Every token is uppercase
ASCII; every aggregate is an immutable ``tuple[str, ...]`` so the
boundary scanner reads it as structural data rather than runtime-
mutable state.

Stage 26.4 produces **candidate evidence proposals only**. A Stage
26.4 candidate is not a policy rule, is not approved, and is not
runtime-consumable. The closed sets declared here pin that
discipline at the vocabulary layer:

  * ``THRESHOLD_CANDIDATE_KINDS``    -- the per-cohort candidate
                                        dimensions the generator may
                                        propose. Every kind reads a
                                        Stage 26.3 cohort-summary
                                        count or rate field; Stage
                                        26.4 NEVER invents a new
                                        market-feature dimension.
  * ``THRESHOLD_CANDIDATE_STATUSES`` -- per-candidate outcome state.
                                        ``CANDIDATE_ONLY`` is the
                                        normal non-suppressed outcome;
                                        the ``INSUFFICIENT_*`` /
                                        ``SUPPRESSED_*`` /
                                        ``INVALID_*`` states record
                                        why a candidate is not yet
                                        suitable for downstream
                                        review.
  * ``THRESHOLD_EVIDENCE_CLASSES``   -- per-candidate evidence class.
                                        Stage 26.4 distinguishes
                                        primary-measured evidence
                                        from observability / coverage
                                        / scope / rejection / invalid-
                                        input caveats so the Stage
                                        26.5+ review surface can read
                                        the caveat shape directly.
  * ``THRESHOLD_DIRECTIONS``         -- ``MINIMUM`` / ``MAXIMUM``
                                        direction of the candidate
                                        threshold.
  * ``THRESHOLD_REVIEW_READINESSES`` -- per-candidate readiness for
                                        Stage 26.5 review. Stage 26.4
                                        produces candidates only;
                                        ``READY_FOR_POLICY_CANDIDATE_
                                        REVIEW`` simply means the
                                        cohort cleared the Stage 26.4
                                        measured-denominator and
                                        caveat-rate gates, not that
                                        any policy is approved.
  * ``STAGE26_THRESHOLD_ERROR_CODES`` -- the typed-error code tokens
                                         the Stage 26.4 generator may
                                         raise. Codes inherit the
                                         Stage 26 ``STG26_CAL_`` prefix
                                         so callers can dispatch on
                                         the Stage 26 error code
                                         namespace.

Stage 26.4 does NOT declare:

  * any policy candidate vocabulary   -- Stage 26.5.
  * any approval-state vocabulary     -- Stage 26.6.
  * any operator review packet field  -- Stage 26.6.
  * any enforcement / dispatch tokens -- Stage 29+ (never in 26).

Stage 26.4 imports nothing from ``PHX2.stage25`` directly -- Stage 25
vocabulary continues to route through
``PHX2.stage26.constants.MEASUREMENT_TRUTH_CLASSES`` (which itself
flows through ``PHX2.stage26.stage25_schema_whitelist`` per Stage
26.0 spec-lock §8). Stage 26.4 NEVER renames or upgrades a Stage 25
truth class.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 26.4 version axes
# ---------------------------------------------------------------------------


STAGE26_THRESHOLD_VERSION: str = "stage26_threshold_v0"


# Deterministic-ordering version. Bumping the deterministic ordering
# convention used by the threshold generator (lexicographic sort on
# (cohort_key.values, candidate_kind)) requires bumping this axis so
# downstream Stage 26.x consumers can pin the exact ordering they
# consumed.
STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION: str = (
    "stage26_threshold_ordering_v0"
)


# Candidate-generation version. Bumping the candidate-generation
# logic (e.g. adding a new kind, changing the suppression rules,
# changing how rates are derived) requires bumping this axis so a
# Stage 26.5 review packet can pin the exact generator that produced
# the candidate.
STAGE26_CANDIDATE_GENERATION_VERSION: str = (
    "stage26_threshold_generation_v0"
)


# ---------------------------------------------------------------------------
# THRESHOLD_CANDIDATE_KINDS -- locked candidate dimensions
# ---------------------------------------------------------------------------


THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT: str = (
    "MIN_PRIMARY_MEASURED_COUNT"
)
THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT: str = (
    "MIN_THRESHOLD_ELIGIBLE_COUNT"
)
THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE: str = (
    "MAX_COVERAGE_GAP_RATE"
)
THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE: str = (
    "MAX_SCOPE_GAP_RATE"
)
THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE: str = (
    "MAX_REJECTION_RATE"
)
THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE: str = (
    "MAX_SOURCE_CONFLICT_RATE"
)
THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE: str = (
    "MAX_AMBIGUOUS_RATE"
)
THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE: str = (
    "MIN_OBSERVABILITY_RATE"
)


THRESHOLD_CANDIDATE_KINDS: tuple[str, ...] = (
    THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT,
    THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT,
    THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE,
    THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE,
    THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE,
)


# ---------------------------------------------------------------------------
# THRESHOLD_CANDIDATE_STATUSES -- per-candidate outcome states
# ---------------------------------------------------------------------------


THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY: str = "CANDIDATE_ONLY"
THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR: str = (
    "INSUFFICIENT_MEASURED_DENOMINATOR"
)
THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS: str = (
    "INSUFFICIENT_TOTAL_ROWS"
)
THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT: str = (
    "INVALID_COHORT_INPUT"
)
THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP: str = (
    "SUPPRESSED_BY_COVERAGE_GAP"
)
THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP: str = (
    "SUPPRESSED_BY_SCOPE_GAP"
)
THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP: str = (
    "SUPPRESSED_BY_REJECTION_GAP"
)


THRESHOLD_CANDIDATE_STATUSES: tuple[str, ...] = (
    THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
    THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
)


# ---------------------------------------------------------------------------
# THRESHOLD_EVIDENCE_CLASSES -- per-candidate evidence class
# ---------------------------------------------------------------------------


THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE: str = (
    "PRIMARY_MEASURED_EVIDENCE"
)
THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT: str = (
    "OBSERVABILITY_CAVEAT"
)
THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT: str = "COVERAGE_CAVEAT"
THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT: str = "SCOPE_CAVEAT"
THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT: str = "REJECTION_CAVEAT"
THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT: str = (
    "INVALID_INPUT_CAVEAT"
)


THRESHOLD_EVIDENCE_CLASSES: tuple[str, ...] = (
    THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
    THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
)


# ---------------------------------------------------------------------------
# THRESHOLD_DIRECTIONS -- direction of the candidate threshold
# ---------------------------------------------------------------------------


THRESHOLD_DIRECTION_MINIMUM: str = "MINIMUM"
THRESHOLD_DIRECTION_MAXIMUM: str = "MAXIMUM"


THRESHOLD_DIRECTIONS: tuple[str, ...] = (
    THRESHOLD_DIRECTION_MINIMUM,
    THRESHOLD_DIRECTION_MAXIMUM,
)


# ---------------------------------------------------------------------------
# THRESHOLD_REVIEW_READINESSES -- readiness for downstream review
# ---------------------------------------------------------------------------


THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW: str = (
    "READY_FOR_POLICY_CANDIDATE_REVIEW"
)
THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS: str = (
    "NEEDS_MORE_MEASURED_ROWS"
)
THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE: str = (
    "NEEDS_BETTER_COVERAGE"
)
THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW: str = (
    "NEEDS_SCOPE_REVIEW"
)
THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW: str = (
    "NEEDS_REJECTION_REVIEW"
)
THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW: str = (
    "INVALID_FOR_REVIEW"
)


THRESHOLD_REVIEW_READINESSES: tuple[str, ...] = (
    THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
    THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
    THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
    THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW,
)


# ---------------------------------------------------------------------------
# STAGE26_THRESHOLD_ERROR_CODES -- typed-error code tokens
# ---------------------------------------------------------------------------


STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND: str = (
    "STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND"
)
STG26_CAL_THRESHOLD_INVALID_DIRECTION: str = (
    "STG26_CAL_THRESHOLD_INVALID_DIRECTION"
)
STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS: str = (
    "STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS"
)
STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH: str = (
    "STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH"
)
STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY: str = (
    "STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY"
)
STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE: str = (
    "STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE"
)
STG26_CAL_THRESHOLD_POLICY_LEAK: str = (
    "STG26_CAL_THRESHOLD_POLICY_LEAK"
)


STAGE26_THRESHOLD_ERROR_CODES: tuple[str, ...] = (
    STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
    STG26_CAL_THRESHOLD_INVALID_DIRECTION,
    STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS,
    STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH,
    STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY,
    STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
    STG26_CAL_THRESHOLD_POLICY_LEAK,
)


# ---------------------------------------------------------------------------
# Default candidate-generation knobs
# ---------------------------------------------------------------------------
#
# The defaults are conservative: Stage 26.4 requires at least one
# MEASURED row before any candidate clears its measured-denominator
# gate, and the caveat-rate gates default to ``1.0`` (i.e. permissive,
# never suppressed by default) so the operator opts into stricter
# rates explicitly. ``min_total_rows`` defaults to ``1`` so the
# generator surfaces an INSUFFICIENT_TOTAL_ROWS candidate on an empty
# cohort instead of silently dropping it. None of these constants
# are policy decisions; they are candidate-generation defaults the
# generator's tests rely on for deterministic behavior.


DEFAULT_MIN_TOTAL_ROWS: int = 1
DEFAULT_MIN_PRIMARY_MEASURED_COUNT: int = 1
DEFAULT_MIN_THRESHOLD_ELIGIBLE_COUNT: int = 1
DEFAULT_MAX_COVERAGE_GAP_RATE: float = 1.0
DEFAULT_MAX_SCOPE_GAP_RATE: float = 1.0
DEFAULT_MAX_REJECTION_RATE: float = 1.0
DEFAULT_MAX_SOURCE_CONFLICT_RATE: float = 1.0
DEFAULT_MAX_AMBIGUOUS_RATE: float = 1.0
DEFAULT_MIN_OBSERVABILITY_RATE: float = 0.0


__all__ = [
    "DEFAULT_MAX_AMBIGUOUS_RATE",
    "DEFAULT_MAX_COVERAGE_GAP_RATE",
    "DEFAULT_MAX_REJECTION_RATE",
    "DEFAULT_MAX_SCOPE_GAP_RATE",
    "DEFAULT_MAX_SOURCE_CONFLICT_RATE",
    "DEFAULT_MIN_OBSERVABILITY_RATE",
    "DEFAULT_MIN_PRIMARY_MEASURED_COUNT",
    "DEFAULT_MIN_THRESHOLD_ELIGIBLE_COUNT",
    "DEFAULT_MIN_TOTAL_ROWS",
    "STAGE26_CANDIDATE_GENERATION_VERSION",
    "STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION",
    "STAGE26_THRESHOLD_ERROR_CODES",
    "STAGE26_THRESHOLD_VERSION",
    "STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS",
    "STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE",
    "STG26_CAL_THRESHOLD_INVALID_DIRECTION",
    "STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH",
    "STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY",
    "STG26_CAL_THRESHOLD_POLICY_LEAK",
    "STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND",
    "THRESHOLD_CANDIDATE_KINDS",
    "THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE",
    "THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE",
    "THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE",
    "THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE",
    "THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE",
    "THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE",
    "THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT",
    "THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT",
    "THRESHOLD_CANDIDATE_STATUSES",
    "THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY",
    "THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR",
    "THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS",
    "THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT",
    "THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP",
    "THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP",
    "THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP",
    "THRESHOLD_DIRECTIONS",
    "THRESHOLD_DIRECTION_MAXIMUM",
    "THRESHOLD_DIRECTION_MINIMUM",
    "THRESHOLD_EVIDENCE_CLASSES",
    "THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT",
    "THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT",
    "THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT",
    "THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE",
    "THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT",
    "THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT",
    "THRESHOLD_REVIEW_READINESSES",
    "THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW",
    "THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE",
    "THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS",
    "THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW",
    "THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW",
    "THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW",
]
