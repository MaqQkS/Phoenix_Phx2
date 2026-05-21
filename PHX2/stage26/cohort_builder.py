"""Stage 26.3 calibration cohort builder.

The builder is pure, deterministic, and read-only against Stage 26.2
``Stage26EligibilityRow`` inputs. It NEVER:

  * reads a Stage 25 artifact file,
  * mutates a Stage 25 / Stage 26.1 / Stage 26.2 record,
  * joins rows across artifacts (no by-mint joins, no by-token-mint
    dedupe),
  * recomputes Stage 26.2 denominator / outcome / reason / flag
    decisions,
  * upgrades a non-MEASURED truth class into MEASURED,
  * generates threshold candidates,
  * generates policy candidates,
  * builds review packets,
  * writes artifacts,
  * defines a CLI entrypoint,
  * reads the process environment,
  * opens a network / DB / messaging connection.

Public entrypoints:

  * ``build_cohort_key(row, dimensions)``
        Build the locked ``Stage26CohortKey`` for ``row`` under the
        supplied ``dimensions`` tuple. Raises ``Stage26CohortError``
        with code ``STG26_CAL_COHORT_UNKNOWN_DIMENSION`` for unknown
        dimensions and ``STG26_CAL_COHORT_EMPTY_INPUT`` for empty
        dimensions.

  * ``build_cohort_member(row)``
        Project a Stage 26.2 eligibility row into a
        ``Stage26CohortMember`` with row_status
        ``INCLUDED_IN_COHORT``. Stage 26.3 NEVER reclassifies the
        row; it copies the Stage 26.2 fields verbatim.

  * ``summarize_cohort(key, members, stage25_manifest_hash)``
        Build a ``Stage26CohortSummary`` over a member tuple. The
        summary's count fields preserve the Stage 26.2 truth-class
        and denominator-status splits verbatim; Stage 26.3 NEVER
        collapses or aggregates two Stage 26.2 categories.

  * ``build_cohorts(eligibility_result, dimensions)``
        Walk every Stage 26.2 eligibility row, group rows by the
        supplied dimensions, and emit an immutable
        ``Stage26CohortBuildResult`` with deterministic ordering.

Determinism contract:

  * Identical (``eligibility_result``, ``dimensions``) inputs ALWAYS
    produce equal ``Stage26CohortBuildResult`` instances.
  * Cohort members preserve Stage 26.2 row order (which itself
    preserves Stage 25's on-disk row order).
  * Cohort summaries are ordered ascending by ``cohort_key.values``
    (lexicographic on the value tuple).
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
    COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    COHORT_STATUS_VALID_COHORT,
    STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_COHORT_VERSION,
    STG26_CAL_COHORT_EMPTY_INPUT,
    STG26_CAL_COHORT_MIXED_MANIFEST_HASH,
    STG26_CAL_COHORT_UNKNOWN_DIMENSION,
)
from PHX2.stage26.cohort_models import (
    Stage26CohortBuildResult,
    Stage26CohortKey,
    Stage26CohortMember,
    Stage26CohortSummary,
)
from PHX2.stage26.eligibility_models import (
    Stage26EligibilityResult,
    Stage26EligibilityRow,
)
from PHX2.stage26.errors import Stage26CohortError


def _bool_value_token(flag: bool) -> str:
    if flag:
        return COHORT_BOOL_VALUE_TRUE
    return COHORT_BOOL_VALUE_FALSE


def _value_for_dimension(
    row: Stage26EligibilityRow, dimension: str
) -> str:
    """Return the cohort-key value string for ``row`` on ``dimension``.

    Stage 26.3 reads Stage 26.2 row fields verbatim. The mapping is
    exhaustive over ``COHORT_DIMENSIONS``; an unknown dimension
    token is rejected upstream of this helper by
    ``_validate_dimensions``.
    """
    if dimension == COHORT_DIMENSION_MEASUREMENT_TRUTH_CLASS:
        return row.measurement_truth_class
    if dimension == COHORT_DIMENSION_DENOMINATOR_STATUS:
        return row.denominator_status
    if dimension == COHORT_DIMENSION_OUTCOME_ELIGIBILITY_STATUS:
        return row.outcome_eligibility_status
    if dimension == COHORT_DIMENSION_PRIMARY_DENOMINATOR_REASON:
        return row.primary_denominator_reason
    if dimension == COHORT_DIMENSION_SOURCE_ARTIFACT_KIND:
        return row.source_artifact_kind
    if dimension == COHORT_DIMENSION_THRESHOLD_CALIBRATION_ELIGIBILITY:
        return _bool_value_token(row.eligible_for_threshold_calibration)
    if dimension == COHORT_DIMENSION_PRIMARY_METRICS_ELIGIBILITY:
        return _bool_value_token(row.eligible_for_primary_metrics)
    if dimension == COHORT_DIMENSION_OBSERVABILITY_METRICS_ELIGIBILITY:
        return _bool_value_token(row.eligible_for_observability_metrics)
    # Defensive: unreachable when ``dimension`` has been validated
    # against ``COHORT_DIMENSIONS``. Raised here as a safety net.
    raise Stage26CohortError(
        f"unknown cohort dimension {dimension!r}",
        error_code=STG26_CAL_COHORT_UNKNOWN_DIMENSION,
    )


def _validate_dimensions(dimensions: tuple[str, ...]) -> None:
    if not isinstance(dimensions, tuple):
        raise Stage26CohortError(
            (
                "cohort dimensions must be a tuple of strings, got "
                f"{type(dimensions).__name__}"
            ),
            error_code=STG26_CAL_COHORT_UNKNOWN_DIMENSION,
        )
    if len(dimensions) == 0:
        raise Stage26CohortError(
            (
                "cohort dimensions tuple must declare at least one "
                "dimension; Stage 26.3 refuses implicit grouping"
            ),
            error_code=STG26_CAL_COHORT_EMPTY_INPUT,
        )
    known = set(COHORT_DIMENSIONS)
    for dim in dimensions:
        if not isinstance(dim, str):
            raise Stage26CohortError(
                (
                    "cohort dimension tokens must be strings, got "
                    f"{type(dim).__name__}"
                ),
                error_code=STG26_CAL_COHORT_UNKNOWN_DIMENSION,
            )
        if dim not in known:
            raise Stage26CohortError(
                (
                    f"cohort dimension {dim!r} is not a member of the "
                    "locked Stage 26.3 COHORT_DIMENSIONS closed set"
                ),
                error_code=STG26_CAL_COHORT_UNKNOWN_DIMENSION,
            )


def build_cohort_key(
    row: Stage26EligibilityRow,
    dimensions: tuple[str, ...],
) -> Stage26CohortKey:
    """Build the locked cohort key for ``row`` on ``dimensions``.

    Stage 26.3 NEVER reorders dimensions; the resulting key carries
    them in caller order. Stage 26.3 NEVER mutates ``row``.
    """
    _validate_dimensions(dimensions)
    values = tuple(
        _value_for_dimension(row, dim) for dim in dimensions
    )
    return Stage26CohortKey(
        dimensions=tuple(dimensions),
        values=values,
    )


def build_cohort_member(
    row: Stage26EligibilityRow,
) -> Stage26CohortMember:
    """Project a Stage 26.2 eligibility row into a cohort member.

    Stage 26.3 NEVER recomputes Stage 26.2's per-row decision. The
    member carries the Stage 26.2 fields verbatim plus the Stage
    26.3 ``row_status`` token ``INCLUDED_IN_COHORT``.
    """
    return Stage26CohortMember(
        row_id=row.row_id,
        source_row_id=row.source_row_id,
        measurement_truth_class=row.measurement_truth_class,
        denominator_status=row.denominator_status,
        outcome_eligibility_status=row.outcome_eligibility_status,
        primary_denominator_reason=row.primary_denominator_reason,
        eligible_for_threshold_calibration=(
            row.eligible_for_threshold_calibration
        ),
        eligible_for_primary_metrics=row.eligible_for_primary_metrics,
        eligible_for_observability_metrics=(
            row.eligible_for_observability_metrics
        ),
        source_artifact_kind=row.source_artifact_kind,
        stage25_manifest_hash=row.stage25_manifest_hash,
        row_status=COHORT_ROW_STATUS_INCLUDED_IN_COHORT,
    )


def summarize_cohort(
    key: Stage26CohortKey,
    members: tuple[Stage26CohortMember, ...],
    stage25_manifest_hash: str,
) -> Stage26CohortSummary:
    """Build a ``Stage26CohortSummary`` over a cohort's members.

    Stage 26.3 preserves Stage 26.2's truth-class and denominator-
    status splits verbatim -- the summary exposes counts side-by-
    side, never collapsed. The summary's
    ``stage25_manifest_hash`` is the caller-supplied hash; Stage
    26.3 NEVER derives the hash from the members themselves (it
    would mask a mixed-manifest cohort).
    """
    measured = 0
    partial = 0
    source_conflict = 0
    ambiguous = 0
    window_ineligible = 0
    missing = 0
    unsupported = 0
    rejected = 0
    not_applicable = 0
    primary_measured_denominator = 0
    observability_denominator = 0
    coverage_gap_denominator = 0
    scope_gap_denominator = 0
    rejection_denominator = 0
    threshold_calibration_eligible = 0
    primary_metrics_eligible = 0
    observability_metrics_eligible = 0
    for member in members:
        truth = member.measurement_truth_class
        if truth == "MEASURED":
            measured = measured + 1
        elif truth == "PARTIAL":
            partial = partial + 1
        elif truth == "SOURCE_CONFLICT":
            source_conflict = source_conflict + 1
        elif truth == "AMBIGUOUS":
            ambiguous = ambiguous + 1
        elif truth == "MISSING":
            missing = missing + 1
        elif truth == "UNSUPPORTED":
            unsupported = unsupported + 1
        elif truth == "REJECTED":
            rejected = rejected + 1
        elif truth == "NOT_APPLICABLE":
            not_applicable = not_applicable + 1
        reason = member.primary_denominator_reason
        if reason == "NOT_MEASURED_WINDOW_INELIGIBLE":
            window_ineligible = window_ineligible + 1
        denom = member.denominator_status
        if denom == "PRIMARY_MEASURED_DENOMINATOR":
            primary_measured_denominator = (
                primary_measured_denominator + 1
            )
        elif denom == "OBSERVABILITY_DENOMINATOR":
            observability_denominator = observability_denominator + 1
        elif denom == "COVERAGE_GAP_DENOMINATOR":
            coverage_gap_denominator = coverage_gap_denominator + 1
        elif denom == "SCOPE_GAP_DENOMINATOR":
            scope_gap_denominator = scope_gap_denominator + 1
        elif denom == "REJECTION_DENOMINATOR":
            rejection_denominator = rejection_denominator + 1
        if member.eligible_for_threshold_calibration:
            threshold_calibration_eligible = (
                threshold_calibration_eligible + 1
            )
        if member.eligible_for_primary_metrics:
            primary_metrics_eligible = primary_metrics_eligible + 1
        if member.eligible_for_observability_metrics:
            observability_metrics_eligible = (
                observability_metrics_eligible + 1
            )
    return Stage26CohortSummary(
        cohort_key=key,
        row_count=len(members),
        measured_count=measured,
        partial_count=partial,
        source_conflict_count=source_conflict,
        ambiguous_count=ambiguous,
        window_ineligible_count=window_ineligible,
        missing_count=missing,
        unsupported_count=unsupported,
        rejected_count=rejected,
        not_applicable_count=not_applicable,
        primary_measured_denominator_count=(
            primary_measured_denominator
        ),
        observability_denominator_count=observability_denominator,
        coverage_gap_denominator_count=coverage_gap_denominator,
        scope_gap_denominator_count=scope_gap_denominator,
        rejection_denominator_count=rejection_denominator,
        threshold_calibration_eligible_count=(
            threshold_calibration_eligible
        ),
        primary_metrics_eligible_count=primary_metrics_eligible,
        observability_metrics_eligible_count=(
            observability_metrics_eligible
        ),
        stage25_manifest_hash=stage25_manifest_hash,
        cohort_status=COHORT_STATUS_VALID_COHORT,
    )


def _validate_single_manifest_hash(
    eligibility_result: Stage26EligibilityResult,
) -> str:
    """Return the single Stage 25 manifest hash every row must agree on.

    The pin on the eligibility bundle is the authoritative hash;
    every row's ``stage25_manifest_hash`` must equal it. Any mismatch
    raises ``Stage26CohortError`` with code
    ``STG26_CAL_COHORT_MIXED_MANIFEST_HASH``.
    """
    pin_hash = (
        eligibility_result.stage25_manifest_pin.artifact_sha256
    )
    for row in eligibility_result.rows:
        if row.stage25_manifest_hash != pin_hash:
            raise Stage26CohortError(
                (
                    "Stage 26.3 cohort builder requires every "
                    "Stage 26.2 row to carry the bundle's Stage 25 "
                    f"manifest hash {pin_hash!r}; row "
                    f"{row.row_id!r} carries "
                    f"{row.stage25_manifest_hash!r}"
                ),
                error_code=STG26_CAL_COHORT_MIXED_MANIFEST_HASH,
            )
    return pin_hash


def build_cohorts(
    eligibility_result: Stage26EligibilityResult,
    dimensions: tuple[str, ...],
) -> Stage26CohortBuildResult:
    """Build deterministic calibration cohorts from a Stage 26.2 bundle.

    The builder walks the eligibility bundle's rows in their on-disk
    (Stage 25 manifest declaration) order, projects each row into a
    cohort member, groups members by ``Stage26CohortKey`` under
    ``dimensions``, and emits an immutable ``Stage26CohortBuildResult``.

    Determinism:

      * Cohort members within a cohort preserve Stage 26.2 row order
        verbatim.
      * Cohort summaries (and the parallel cohort_members tuple) are
        ordered ascending by ``cohort_key.values`` (lexicographic on
        the value tuple).
      * Identical inputs always produce equal results.

    Validation:

      * Unknown / empty dimensions -> ``Stage26CohortError``.
      * Mixed manifest hash across rows -> ``Stage26CohortError``.

    Stage 26.3 NEVER joins, dedupes, or upgrades rows; every input
    row produces exactly one cohort member.
    """
    _validate_dimensions(dimensions)
    manifest_hash = _validate_single_manifest_hash(eligibility_result)

    # Group rows by cohort key, preserving row order.
    members_by_key: dict[
        Stage26CohortKey, list[Stage26CohortMember]
    ] = {}
    key_first_index: dict[Stage26CohortKey, int] = {}
    for index, row in enumerate(eligibility_result.rows):
        key = build_cohort_key(row, dimensions)
        member = build_cohort_member(row)
        if key not in members_by_key:
            members_by_key[key] = []
            key_first_index[key] = index
        members_by_key[key].append(member)

    sorted_keys = sorted(
        members_by_key.keys(),
        key=lambda candidate: candidate.values,
    )
    summaries: list[Stage26CohortSummary] = []
    cohort_member_groups: list[tuple[Stage26CohortMember, ...]] = []
    for key in sorted_keys:
        member_tuple = tuple(members_by_key[key])
        summary = summarize_cohort(
            key=key,
            members=member_tuple,
            stage25_manifest_hash=manifest_hash,
        )
        summaries.append(summary)
        cohort_member_groups.append(member_tuple)

    total_input_rows = len(eligibility_result.rows)
    total_cohorted_rows = sum(s.row_count for s in summaries)
    total_invalid_rows = total_input_rows - total_cohorted_rows
    return Stage26CohortBuildResult(
        stage26_cohort_version=STAGE26_COHORT_VERSION,
        deterministic_ordering_version=(
            STAGE26_COHORT_DETERMINISTIC_ORDERING_VERSION
        ),
        stage25_manifest_hash=manifest_hash,
        stage25_manifest_pin=(
            eligibility_result.stage25_manifest_pin
        ),
        cohort_dimensions=tuple(dimensions),
        cohort_summaries=tuple(summaries),
        cohort_members=tuple(cohort_member_groups),
        total_input_rows=total_input_rows,
        total_cohorted_rows=total_cohorted_rows,
        total_invalid_rows=total_invalid_rows,
    )


__all__ = [
    "build_cohort_key",
    "build_cohort_member",
    "build_cohorts",
    "summarize_cohort",
]
