"""Stage 26.4 threshold candidate generator.

The generator is pure, deterministic, and read-only against Stage
26.3 ``Stage26CohortBuildResult`` / ``Stage26CohortSummary`` inputs.
It NEVER:

  * reads a Stage 25 artifact file,
  * reimplements the Stage 26.1 readers,
  * reimplements the Stage 26.2 denominator classifier,
  * reimplements the Stage 26.3 cohort builder,
  * mutates a Stage 25 / Stage 26.1 / Stage 26.2 / Stage 26.3 record,
  * upgrades a non-``MEASURED`` truth class into ``MEASURED``,
  * builds policy candidate artifacts,
  * builds operator review packets,
  * writes artifacts,
  * defines a CLI entrypoint,
  * reads the process environment,
  * opens a network / DB / messaging connection,
  * dispatches / sends / routes anything,
  * enforces any decision.

Public entrypoints:

  * ``build_threshold_evidence_summary(cohort_summary)``
        Project a Stage 26.3 ``Stage26CohortSummary`` into a Stage
        26.4 ``Stage26ThresholdEvidenceSummary``. The projection
        preserves every count verbatim and adds deterministic
        safe-zero-denominator rate fields.

  * ``evaluate_threshold_candidate(...)``
        Evaluate a single ``Stage26ThresholdCandidate`` for one
        cohort + one ``THRESHOLD_CANDIDATE_KINDS`` token under the
        supplied ``Stage26ThresholdCandidateConfig``.

  * ``generate_threshold_candidates(cohort_result, config)``
        High-level orchestrator. Walks each cohort summary in the
        Stage 26.3 build result, validates count shape + manifest
        hash discipline, emits one candidate per (cohort, kind) pair,
        and returns an immutable ``Stage26ThresholdCandidateSet``.

Determinism contract:

  * Identical (``cohort_result``, ``config``) inputs ALWAYS produce
    equal ``Stage26ThresholdCandidateSet`` instances.
  * Candidates are ordered ascending by ``(cohort_key.values,
    candidate_kind)`` lexicographically.
  * Rate fields are computed with safe-zero-denominator handling so
    an empty cohort produces ``0.0`` rates rather than raising.
  * Every emitted candidate carries ``candidate_only=True``,
    ``operator_approved=False``, and ``runtime_consumable=False``.
"""

from __future__ import annotations

from PHX2.stage26.cohort_constants import (
    COHORT_STATUSES,
    COHORT_STATUS_VALID_COHORT,
)
from PHX2.stage26.cohort_models import (
    Stage26CohortBuildResult,
    Stage26CohortSummary,
)
from PHX2.stage26.errors import Stage26ThresholdError
from PHX2.stage26.threshold_constants import (
    STAGE26_CANDIDATE_GENERATION_VERSION,
    STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION,
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
    THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
    THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
    THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
    THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
    THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
    THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
)
from PHX2.stage26.threshold_models import (
    Stage26ThresholdCandidate,
    Stage26ThresholdCandidateConfig,
    Stage26ThresholdCandidateSet,
    Stage26ThresholdEvidenceSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_rate(numerator: int, denominator: int) -> float:
    """Return ``numerator / denominator`` with safe zero-denominator.

    An empty cohort (``row_count == 0``) yields a rate of ``0.0``
    rather than raising. The convention is deterministic across
    repeated calls and across cohorts that happen to be empty.
    """
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _candidate_id(values: tuple[str, ...], candidate_kind: str) -> str:
    """Build the locked deterministic candidate ID for a (cohort, kind)."""
    values_joined = "|".join(values)
    return f"{values_joined}#{candidate_kind}"


def _validate_count_shape(summary: Stage26CohortSummary) -> None:
    """Defensive validation that the cohort summary's counts are shapely.

    Stage 26.3 already produces shapely summaries; the check is a
    safety net against caller-constructed invalid input.
    """
    integer_fields: tuple[tuple[str, int], ...] = (
        ("row_count", summary.row_count),
        ("measured_count", summary.measured_count),
        ("partial_count", summary.partial_count),
        ("source_conflict_count", summary.source_conflict_count),
        ("ambiguous_count", summary.ambiguous_count),
        ("window_ineligible_count", summary.window_ineligible_count),
        ("missing_count", summary.missing_count),
        ("unsupported_count", summary.unsupported_count),
        ("rejected_count", summary.rejected_count),
        ("not_applicable_count", summary.not_applicable_count),
        (
            "primary_measured_denominator_count",
            summary.primary_measured_denominator_count,
        ),
        (
            "observability_denominator_count",
            summary.observability_denominator_count,
        ),
        (
            "coverage_gap_denominator_count",
            summary.coverage_gap_denominator_count,
        ),
        (
            "scope_gap_denominator_count",
            summary.scope_gap_denominator_count,
        ),
        (
            "rejection_denominator_count",
            summary.rejection_denominator_count,
        ),
        (
            "threshold_calibration_eligible_count",
            summary.threshold_calibration_eligible_count,
        ),
    )
    for name, value in integer_fields:
        if not isinstance(value, int) or value < 0:
            raise Stage26ThresholdError(
                (
                    f"cohort summary count {name!r} must be a non-"
                    f"negative integer; got {value!r}"
                ),
                error_code=STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
            )
    truth_sum = (
        summary.measured_count
        + summary.partial_count
        + summary.source_conflict_count
        + summary.ambiguous_count
        + summary.missing_count
        + summary.unsupported_count
        + summary.rejected_count
        + summary.not_applicable_count
    )
    if truth_sum != summary.row_count:
        raise Stage26ThresholdError(
            (
                f"cohort summary truth-class counts {truth_sum} must "
                f"sum to row_count {summary.row_count}"
            ),
            error_code=STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
        )
    denom_sum = (
        summary.primary_measured_denominator_count
        + summary.observability_denominator_count
        + summary.coverage_gap_denominator_count
        + summary.scope_gap_denominator_count
        + summary.rejection_denominator_count
    )
    if denom_sum != summary.row_count:
        raise Stage26ThresholdError(
            (
                f"cohort summary denominator-status counts {denom_sum} "
                f"must sum to row_count {summary.row_count}"
            ),
            error_code=STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
        )
    if summary.threshold_calibration_eligible_count > summary.row_count:
        raise Stage26ThresholdError(
            (
                "cohort summary threshold_calibration_eligible_count "
                f"{summary.threshold_calibration_eligible_count} must "
                f"not exceed row_count {summary.row_count}"
            ),
            error_code=STG26_CAL_THRESHOLD_INVALID_COUNT_SHAPE,
        )
    if (
        summary.primary_measured_denominator_count
        != summary.measured_count
    ):
        raise Stage26ThresholdError(
            (
                "cohort summary primary_measured_denominator_count "
                f"{summary.primary_measured_denominator_count} must "
                f"equal measured_count {summary.measured_count}; a "
                "non-MEASURED row is being upgraded into the primary "
                "measured denominator"
            ),
            error_code=STG26_CAL_THRESHOLD_NON_MEASURED_PRIMARY,
        )


# ---------------------------------------------------------------------------
# Evidence summary projection
# ---------------------------------------------------------------------------


def build_threshold_evidence_summary(
    cohort_summary: Stage26CohortSummary,
) -> Stage26ThresholdEvidenceSummary:
    """Project a Stage 26.3 cohort summary into a Stage 26.4 evidence summary.

    Counts are carried verbatim; rate fields are deterministic safe-
    zero-denominator divisions. Stage 26.4 NEVER recomputes Stage
    26.2 denominator decisions or Stage 26.3 cohort groupings -- it
    projects the cohort summary into the evidence shape candidate
    evaluators consume.
    """
    row_count = cohort_summary.row_count
    coverage_gap_rate = _safe_rate(
        cohort_summary.coverage_gap_denominator_count, row_count
    )
    scope_gap_rate = _safe_rate(
        cohort_summary.scope_gap_denominator_count, row_count
    )
    rejection_rate = _safe_rate(
        cohort_summary.rejection_denominator_count, row_count
    )
    source_conflict_rate = _safe_rate(
        cohort_summary.source_conflict_count, row_count
    )
    ambiguous_rate = _safe_rate(
        cohort_summary.ambiguous_count, row_count
    )
    observability_rate = _safe_rate(
        cohort_summary.observability_denominator_count, row_count
    )
    return Stage26ThresholdEvidenceSummary(
        cohort_key=cohort_summary.cohort_key,
        row_count=row_count,
        primary_measured_denominator_count=(
            cohort_summary.primary_measured_denominator_count
        ),
        threshold_calibration_eligible_count=(
            cohort_summary.threshold_calibration_eligible_count
        ),
        measured_count=cohort_summary.measured_count,
        partial_count=cohort_summary.partial_count,
        source_conflict_count=cohort_summary.source_conflict_count,
        ambiguous_count=cohort_summary.ambiguous_count,
        window_ineligible_count=cohort_summary.window_ineligible_count,
        missing_count=cohort_summary.missing_count,
        unsupported_count=cohort_summary.unsupported_count,
        rejected_count=cohort_summary.rejected_count,
        coverage_gap_rate=coverage_gap_rate,
        scope_gap_rate=scope_gap_rate,
        rejection_rate=rejection_rate,
        source_conflict_rate=source_conflict_rate,
        ambiguous_rate=ambiguous_rate,
        observability_rate=observability_rate,
        stage25_manifest_hash=cohort_summary.stage25_manifest_hash,
    )


# ---------------------------------------------------------------------------
# Per-kind axis projection
# ---------------------------------------------------------------------------


def _kind_axis(
    candidate_kind: str,
    evidence_summary: Stage26ThresholdEvidenceSummary,
    config: Stage26ThresholdCandidateConfig,
) -> tuple[str, float, float, str]:
    """Return (direction, threshold_value, observed_value, evidence_class).

    The evidence_class returned here is the kind's NATURAL class
    assuming a valid cohort; the candidate evaluator may override it
    to ``INVALID_INPUT_CAVEAT`` for invalid cohort inputs.
    """
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT:
        return (
            THRESHOLD_DIRECTION_MINIMUM,
            float(config.min_primary_measured_count),
            float(evidence_summary.primary_measured_denominator_count),
            THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
        )
    if (
        candidate_kind
        == THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT
    ):
        return (
            THRESHOLD_DIRECTION_MINIMUM,
            float(config.min_threshold_eligible_count),
            float(evidence_summary.threshold_calibration_eligible_count),
            THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE:
        return (
            THRESHOLD_DIRECTION_MAXIMUM,
            float(config.max_coverage_gap_rate),
            evidence_summary.coverage_gap_rate,
            THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE:
        return (
            THRESHOLD_DIRECTION_MAXIMUM,
            float(config.max_scope_gap_rate),
            evidence_summary.scope_gap_rate,
            THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE:
        return (
            THRESHOLD_DIRECTION_MAXIMUM,
            float(config.max_rejection_rate),
            evidence_summary.rejection_rate,
            THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
        )
    if (
        candidate_kind
        == THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE
    ):
        return (
            THRESHOLD_DIRECTION_MAXIMUM,
            float(config.max_source_conflict_rate),
            evidence_summary.source_conflict_rate,
            THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE:
        return (
            THRESHOLD_DIRECTION_MAXIMUM,
            float(config.max_ambiguous_rate),
            evidence_summary.ambiguous_rate,
            THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE:
        return (
            THRESHOLD_DIRECTION_MINIMUM,
            float(config.min_observability_rate),
            evidence_summary.observability_rate,
            THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
        )
    raise Stage26ThresholdError(
        (
            f"candidate kind {candidate_kind!r} is not a member of the "
            "locked Stage 26.4 THRESHOLD_CANDIDATE_KINDS closed set"
        ),
        error_code=STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
    )


def _kind_decision(
    candidate_kind: str,
    threshold_value: float,
    observed_value: float,
    evidence_class: str,
) -> tuple[str, str, str, str]:
    """Return (candidate_status, evidence_class, review_readiness, reason).

    The evidence_class is returned alongside the decision so the
    caller does not need to special-case kinds whose evidence class
    is the same regardless of observed vs threshold (the spec
    treats high source-conflict / ambiguous / observability rates as
    observability CAVEATS, not failures).
    """
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MIN_PRIMARY_MEASURED_COUNT:
        if observed_value < threshold_value:
            return (
                THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
                evidence_class,
                THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
                (
                    f"primary_measured_denominator_count "
                    f"{int(observed_value)} below "
                    f"min_primary_measured_count {int(threshold_value)}"
                ),
            )
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"primary_measured_denominator_count "
                f"{int(observed_value)} clears "
                f"min_primary_measured_count {int(threshold_value)}"
            ),
        )
    if (
        candidate_kind
        == THRESHOLD_CANDIDATE_KIND_MIN_THRESHOLD_ELIGIBLE_COUNT
    ):
        if observed_value < threshold_value:
            return (
                THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
                evidence_class,
                THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
                (
                    f"threshold_calibration_eligible_count "
                    f"{int(observed_value)} below "
                    f"min_threshold_eligible_count "
                    f"{int(threshold_value)}"
                ),
            )
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"threshold_calibration_eligible_count "
                f"{int(observed_value)} clears "
                f"min_threshold_eligible_count {int(threshold_value)}"
            ),
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_COVERAGE_GAP_RATE:
        if observed_value > threshold_value:
            return (
                THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
                evidence_class,
                THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
                (
                    f"coverage_gap_rate {observed_value} exceeds "
                    f"max_coverage_gap_rate {threshold_value}"
                ),
            )
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"coverage_gap_rate {observed_value} clears "
                f"max_coverage_gap_rate {threshold_value}"
            ),
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_SCOPE_GAP_RATE:
        if observed_value > threshold_value:
            return (
                THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
                evidence_class,
                THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
                (
                    f"scope_gap_rate {observed_value} exceeds "
                    f"max_scope_gap_rate {threshold_value}"
                ),
            )
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"scope_gap_rate {observed_value} clears "
                f"max_scope_gap_rate {threshold_value}"
            ),
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_REJECTION_RATE:
        if observed_value > threshold_value:
            return (
                THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
                evidence_class,
                THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
                (
                    f"rejection_rate {observed_value} exceeds "
                    f"max_rejection_rate {threshold_value}"
                ),
            )
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"rejection_rate {observed_value} clears "
                f"max_rejection_rate {threshold_value}"
            ),
        )
    if (
        candidate_kind
        == THRESHOLD_CANDIDATE_KIND_MAX_SOURCE_CONFLICT_RATE
    ):
        # High source-conflict rate is an observability caveat, not a
        # failure: the cohort is still a candidate but the caveat is
        # recorded so the Stage 26.5 review surface sees it.
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"source_conflict_rate {observed_value} (threshold "
                f"{threshold_value}); recorded as observability caveat"
            ),
        )
    if candidate_kind == THRESHOLD_CANDIDATE_KIND_MAX_AMBIGUOUS_RATE:
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"ambiguous_rate {observed_value} (threshold "
                f"{threshold_value}); recorded as observability caveat"
            ),
        )
    if (
        candidate_kind
        == THRESHOLD_CANDIDATE_KIND_MIN_OBSERVABILITY_RATE
    ):
        return (
            THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
            evidence_class,
            THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
            (
                f"observability_rate {observed_value} (threshold "
                f"{threshold_value}); recorded as observability caveat"
            ),
        )
    raise Stage26ThresholdError(
        (
            f"candidate kind {candidate_kind!r} is not a member of the "
            "locked Stage 26.4 THRESHOLD_CANDIDATE_KINDS closed set"
        ),
        error_code=STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
    )


# ---------------------------------------------------------------------------
# Candidate evaluation
# ---------------------------------------------------------------------------


def evaluate_threshold_candidate(
    *,
    evidence_summary: Stage26ThresholdEvidenceSummary,
    candidate_kind: str,
    config: Stage26ThresholdCandidateConfig,
    cohort_status: str = COHORT_STATUS_VALID_COHORT,
) -> Stage26ThresholdCandidate:
    """Evaluate a single Stage 26.4 candidate proposal.

    Stage 26.4 NEVER produces a candidate with
    ``operator_approved=True`` or ``runtime_consumable=True``. The
    candidate fields are pinned at construction; the evaluator
    additionally validates the returned candidate against the same
    invariant as a defensive policy-leak check.
    """
    if candidate_kind not in THRESHOLD_CANDIDATE_KINDS:
        raise Stage26ThresholdError(
            (
                f"candidate kind {candidate_kind!r} is not a member of "
                "the locked Stage 26.4 THRESHOLD_CANDIDATE_KINDS closed "
                "set"
            ),
            error_code=STG26_CAL_THRESHOLD_UNKNOWN_CANDIDATE_KIND,
        )
    if cohort_status not in COHORT_STATUSES:
        raise Stage26ThresholdError(
            (
                f"cohort_status {cohort_status!r} is not a member of "
                "the locked Stage 26.3 COHORT_STATUSES closed set"
            ),
            error_code=STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS,
        )

    direction, threshold_value, observed_value, kind_evidence_class = (
        _kind_axis(candidate_kind, evidence_summary, config)
    )
    if direction not in THRESHOLD_DIRECTIONS:
        raise Stage26ThresholdError(
            (
                f"threshold direction {direction!r} is not a member of "
                "the locked Stage 26.4 THRESHOLD_DIRECTIONS closed set"
            ),
            error_code=STG26_CAL_THRESHOLD_INVALID_DIRECTION,
        )

    candidate_id = _candidate_id(
        evidence_summary.cohort_key.values, candidate_kind
    )

    if cohort_status != COHORT_STATUS_VALID_COHORT:
        candidate = Stage26ThresholdCandidate(
            candidate_id=candidate_id,
            cohort_key=evidence_summary.cohort_key,
            candidate_kind=candidate_kind,
            threshold_direction=direction,
            threshold_value=threshold_value,
            observed_value=observed_value,
            candidate_status=(
                THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT
            ),
            evidence_class=THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
            review_readiness=(
                THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW
            ),
            reason=(
                f"cohort_status {cohort_status!r} is not VALID_COHORT; "
                "candidate marked invalid for review"
            ),
            evidence_summary=evidence_summary,
            candidate_only=True,
            operator_approved=False,
            runtime_consumable=False,
            stage25_manifest_hash=evidence_summary.stage25_manifest_hash,
            generation_version=config.candidate_generation_version,
        )
        _check_policy_leak(candidate)
        return candidate

    if evidence_summary.row_count < config.min_total_rows:
        candidate = Stage26ThresholdCandidate(
            candidate_id=candidate_id,
            cohort_key=evidence_summary.cohort_key,
            candidate_kind=candidate_kind,
            threshold_direction=direction,
            threshold_value=threshold_value,
            observed_value=observed_value,
            candidate_status=(
                THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS
            ),
            evidence_class=kind_evidence_class,
            review_readiness=(
                THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS
            ),
            reason=(
                f"cohort row_count {evidence_summary.row_count} below "
                f"min_total_rows {config.min_total_rows}"
            ),
            evidence_summary=evidence_summary,
            candidate_only=True,
            operator_approved=False,
            runtime_consumable=False,
            stage25_manifest_hash=evidence_summary.stage25_manifest_hash,
            generation_version=config.candidate_generation_version,
        )
        _check_policy_leak(candidate)
        return candidate

    status, evidence_class, readiness, reason = _kind_decision(
        candidate_kind,
        threshold_value,
        observed_value,
        kind_evidence_class,
    )

    candidate = Stage26ThresholdCandidate(
        candidate_id=candidate_id,
        cohort_key=evidence_summary.cohort_key,
        candidate_kind=candidate_kind,
        threshold_direction=direction,
        threshold_value=threshold_value,
        observed_value=observed_value,
        candidate_status=status,
        evidence_class=evidence_class,
        review_readiness=readiness,
        reason=reason,
        evidence_summary=evidence_summary,
        candidate_only=True,
        operator_approved=False,
        runtime_consumable=False,
        stage25_manifest_hash=evidence_summary.stage25_manifest_hash,
        generation_version=config.candidate_generation_version,
    )
    _check_policy_leak(candidate)
    return candidate


def _check_policy_leak(candidate: Stage26ThresholdCandidate) -> None:
    """Defensive check that the candidate never carries a leaked flag.

    Stage 26.4 candidates ALWAYS carry ``candidate_only=True``,
    ``operator_approved=False``, ``runtime_consumable=False``. The
    evaluator pins these literally at construction; the check is a
    safety net against a future refactor that accidentally flips a
    flag.
    """
    if candidate.candidate_only is not True:
        raise Stage26ThresholdError(
            (
                f"candidate {candidate.candidate_id!r} carries "
                f"candidate_only={candidate.candidate_only!r}; Stage "
                "26.4 candidates must be candidate-only"
            ),
            error_code=STG26_CAL_THRESHOLD_POLICY_LEAK,
        )
    if candidate.operator_approved is not False:
        raise Stage26ThresholdError(
            (
                f"candidate {candidate.candidate_id!r} carries "
                f"operator_approved={candidate.operator_approved!r}; "
                "Stage 26.4 candidates must NEVER be operator-approved"
            ),
            error_code=STG26_CAL_THRESHOLD_POLICY_LEAK,
        )
    if candidate.runtime_consumable is not False:
        raise Stage26ThresholdError(
            (
                f"candidate {candidate.candidate_id!r} carries "
                f"runtime_consumable={candidate.runtime_consumable!r}; "
                "Stage 26.4 candidates must NEVER be runtime-consumable"
            ),
            error_code=STG26_CAL_THRESHOLD_POLICY_LEAK,
        )


# ---------------------------------------------------------------------------
# Manifest hash discipline
# ---------------------------------------------------------------------------


def _validate_single_manifest_hash(
    cohort_result: Stage26CohortBuildResult,
) -> str:
    """Return the single Stage 25 manifest hash every cohort summary must agree on.

    The pin on the cohort-build result is the authoritative hash;
    every cohort summary's ``stage25_manifest_hash`` must equal it.
    Any mismatch raises ``Stage26ThresholdError`` with code
    ``STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH``.
    """
    pin_hash = cohort_result.stage25_manifest_hash
    for summary in cohort_result.cohort_summaries:
        if summary.stage25_manifest_hash != pin_hash:
            raise Stage26ThresholdError(
                (
                    "Stage 26.4 threshold generator requires every "
                    "cohort summary to carry the cohort-build "
                    f"result's Stage 25 manifest hash {pin_hash!r}; "
                    f"cohort {summary.cohort_key.values!r} carries "
                    f"{summary.stage25_manifest_hash!r}"
                ),
                error_code=STG26_CAL_THRESHOLD_MIXED_MANIFEST_HASH,
            )
    return pin_hash


# ---------------------------------------------------------------------------
# High-level orchestrator
# ---------------------------------------------------------------------------


def generate_threshold_candidates(
    cohort_result: Stage26CohortBuildResult,
    config: Stage26ThresholdCandidateConfig,
) -> Stage26ThresholdCandidateSet:
    """Generate deterministic threshold candidate proposals.

    Walks each Stage 26.3 cohort summary in declaration order,
    validates count shape + manifest hash discipline, emits one
    candidate per (cohort, ``THRESHOLD_CANDIDATE_KINDS`` token) pair,
    sorts the candidates ascending by
    ``(cohort_key.values, candidate_kind)``, and returns an immutable
    ``Stage26ThresholdCandidateSet``.

    Identical inputs ALWAYS produce equal results. Stage 26.4
    NEVER:

      * writes a file,
      * mutates the input cohort result,
      * rebuilds cohorts from raw Stage 26.2 rows,
      * upgrades a non-``MEASURED`` truth class into MEASURED,
      * approves any candidate,
      * marks any candidate runtime-consumable.
    """
    pin_hash = _validate_single_manifest_hash(cohort_result)

    candidates: list[Stage26ThresholdCandidate] = []
    for cohort_summary in cohort_result.cohort_summaries:
        if cohort_summary.cohort_status not in COHORT_STATUSES:
            raise Stage26ThresholdError(
                (
                    f"cohort summary cohort_status "
                    f"{cohort_summary.cohort_status!r} is not a "
                    "member of the locked Stage 26.3 COHORT_STATUSES "
                    "closed set"
                ),
                error_code=STG26_CAL_THRESHOLD_INVALID_COHORT_STATUS,
            )
        _validate_count_shape(cohort_summary)
        evidence_summary = build_threshold_evidence_summary(
            cohort_summary
        )
        for candidate_kind in THRESHOLD_CANDIDATE_KINDS:
            candidate = evaluate_threshold_candidate(
                evidence_summary=evidence_summary,
                candidate_kind=candidate_kind,
                config=config,
                cohort_status=cohort_summary.cohort_status,
            )
            candidates.append(candidate)

    candidates.sort(
        key=lambda entry: (entry.cohort_key.values, entry.candidate_kind)
    )
    candidate_tuple = tuple(candidates)

    total = len(candidate_tuple)
    ready = sum(
        1
        for candidate in candidate_tuple
        if candidate.review_readiness
        == THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
    )
    insufficient_status_tokens = frozenset(
        {
            (
                THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR
            ),
            THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
        }
    )
    insufficient = sum(
        1
        for candidate in candidate_tuple
        if candidate.candidate_status in insufficient_status_tokens
    )
    suppressed_status_tokens = frozenset(
        {
            THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
            THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
            THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
        }
    )
    suppressed = sum(
        1
        for candidate in candidate_tuple
        if candidate.candidate_status in suppressed_status_tokens
    )
    invalid = sum(
        1
        for candidate in candidate_tuple
        if candidate.candidate_status
        == THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT
    )

    return Stage26ThresholdCandidateSet(
        stage26_threshold_version=STAGE26_THRESHOLD_VERSION,
        deterministic_ordering_version=(
            STAGE26_THRESHOLD_DETERMINISTIC_ORDERING_VERSION
        ),
        generation_version=STAGE26_CANDIDATE_GENERATION_VERSION,
        stage25_manifest_hash=pin_hash,
        config=config,
        candidates=candidate_tuple,
        total_candidates=total,
        ready_for_review_count=ready,
        insufficient_measured_count=insufficient,
        suppressed_count=suppressed,
        invalid_cohort_count=invalid,
    )


__all__ = [
    "build_threshold_evidence_summary",
    "evaluate_threshold_candidate",
    "generate_threshold_candidates",
]
