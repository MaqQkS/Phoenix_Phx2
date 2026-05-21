"""Stage 26.2 denominator / outcome-eligibility classifier.

The classifier is pure, deterministic, and read-only against Stage
26.1 input records. It NEVER:

  * reads a Stage 25 artifact file,
  * mutates a Stage 25 or Stage 26.1 record,
  * joins rows across artifacts (no by-mint joins),
  * dedupes or groups rows,
  * builds calibration cohorts,
  * generates thresholds,
  * generates policy candidates,
  * writes artifacts,
  * defines a CLI entrypoint,
  * reads the process environment,
  * opens a network / DB / messaging connection,
  * upgrades a non-MEASURED row into MEASURED,
  * synthesizes measured peak / ATH / migration fields,
  * coerces ``None`` / ``null`` into ``0`` or the empty string.

Public entrypoints:

  * ``classify_measurement_truth_class(truth_class)``
        Returns the locked ``Stage26EligibilityDecision`` for a
        single Stage 25 measurement-status token. Raises
        ``Stage26EligibilityError`` on unknown / non-string input.

  * ``build_eligibility_row(...)``
        Builds a single ``Stage26EligibilityRow`` from a Stage 26.1
        measurement-shape input row.

  * ``build_eligibility_result(calibration_input_set)``
        Walks the Stage 26.1 calibration-input bundle's
        measurement-shape artifacts (migration measurements + ATH
        measurements) in their on-disk row order and emits an
        immutable ``Stage26EligibilityResult``.

  * ``summarize_eligibility(rows)``
        Builds a ``Stage26EligibilitySummary`` over a row tuple.

Eligibility-row construction discipline:

  * Stage 26.2 reads Stage 26.1 records only -- it NEVER reaches
    back into Stage 25 production modules or on-disk artifacts.
  * The Stage 25 manifest hash is taken verbatim from the input
    bundle's ``stage25_manifest_pin.artifact_sha256``.
  * Per-row ``source_row_id`` is the source row's
    ``measurement_hash`` (the locked Stage 25 row-identity hash).
  * Per-row ``row_id`` is the deterministic
    ``f"{source_artifact_kind}#{index}"`` slot index; Stage 26.2
    NEVER reorders rows.
"""

from __future__ import annotations

from typing import Union

from PHX2.stage26.constants import (
    CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
    CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
    MEASUREMENT_TRUTH_CLASSES,
    STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS,
)
from PHX2.stage26.eligibility_constants import (
    CALIBRATION_ELIGIBILITY_KINDS,
    DENOMINATOR_STATUSES,
    ELIGIBILITY_DECISION_BY_TRUTH_CLASS,
    OUTCOME_ELIGIBILITY_STATUSES,
    PRIMARY_DENOMINATOR_REASONS,
    STAGE26_ELIGIBILITY_VERSION,
)
from PHX2.stage26.eligibility_models import (
    Stage26EligibilityDecision,
    Stage26EligibilityResult,
    Stage26EligibilityRow,
    Stage26EligibilitySummary,
)
from PHX2.stage26.errors import Stage26EligibilityError
from PHX2.stage26.models import (
    ATHMeasurementInput,
    MigrationMeasurementInput,
    Stage26CalibrationInputSet,
)


# Union of Stage 26.1 measurement-shape input rows the classifier
# accepts on the per-row entrypoint. Other Stage 26.1 record kinds
# (migration observations, price-window observations, ATH candidates,
# source reconciliations, measurement rejections) do not carry a
# Stage 25 measurement-status token and are NOT eligibility inputs;
# the classifier rejects them at the caller boundary by typing.
MeasurementShapeInputRow = Union[
    MigrationMeasurementInput, ATHMeasurementInput
]


def classify_measurement_truth_class(
    measurement_truth_class: str,
) -> Stage26EligibilityDecision:
    """Return the locked eligibility decision for a Stage 25 truth class.

    The mapping is the immutable
    ``ELIGIBILITY_DECISION_BY_TRUTH_CLASS`` tuple-of-tuples in
    ``eligibility_constants``. Stage 26.2 NEVER upgrades a truth
    class; if the supplied string is not a member of the locked
    ``MEASUREMENT_TRUTH_CLASSES`` set, the classifier raises a typed
    ``Stage26EligibilityError`` with error code
    ``STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS``.
    """
    if not isinstance(measurement_truth_class, str):
        raise Stage26EligibilityError(
            f"measurement_truth_class must be a string, got "
            f"{type(measurement_truth_class).__name__}",
            error_code=STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS,
        )
    for entry in ELIGIBILITY_DECISION_BY_TRUTH_CLASS:
        if entry[0] == measurement_truth_class:
            return Stage26EligibilityDecision(
                denominator_status=entry[1],
                outcome_eligibility_status=entry[2],
                primary_denominator_reason=entry[3],
                calibration_eligibility_kind=entry[4],
                eligible_for_threshold_calibration=entry[5],
                eligible_for_primary_metrics=entry[6],
                eligible_for_observability_metrics=entry[7],
            )
    raise Stage26EligibilityError(
        (
            f"measurement_truth_class {measurement_truth_class!r} is "
            "not a member of the locked Stage 26.1 "
            "MEASUREMENT_TRUTH_CLASSES closed set"
        ),
        error_code=STG26_CAL_ELIGIBILITY_UNKNOWN_TRUTH_CLASS,
    )


def build_eligibility_row(
    *,
    input_row: MeasurementShapeInputRow,
    source_artifact_kind: str,
    row_index: int,
    stage25_manifest_hash: str,
) -> Stage26EligibilityRow:
    """Build a single ``Stage26EligibilityRow`` from a measurement input.

    ``input_row`` is a Stage 26.1 measurement-shape NamedTuple
    (``MigrationMeasurementInput`` or ``ATHMeasurementInput``); both
    expose ``measurement_status`` / ``token_mint`` / ``measurement_
    hash`` fields. The classifier preserves the measurement-status
    string verbatim on the output row.
    """
    truth_class = input_row.measurement_status
    decision = classify_measurement_truth_class(truth_class)
    row_id = f"{source_artifact_kind}#{row_index}"
    return Stage26EligibilityRow(
        row_id=row_id,
        source_row_id=input_row.measurement_hash,
        mint=input_row.token_mint,
        measurement_truth_class=truth_class,
        denominator_status=decision.denominator_status,
        outcome_eligibility_status=decision.outcome_eligibility_status,
        primary_denominator_reason=decision.primary_denominator_reason,
        calibration_eligibility_kind=decision.calibration_eligibility_kind,
        eligible_for_threshold_calibration=(
            decision.eligible_for_threshold_calibration
        ),
        eligible_for_primary_metrics=(
            decision.eligible_for_primary_metrics
        ),
        eligible_for_observability_metrics=(
            decision.eligible_for_observability_metrics
        ),
        source_artifact_kind=source_artifact_kind,
        stage25_manifest_hash=stage25_manifest_hash,
    )


def _counts_by_key(
    rows: tuple[Stage26EligibilityRow, ...],
    *,
    accessor,
    locked_keys: tuple[str, ...],
) -> tuple[tuple[str, int], ...]:
    """Build a sorted tuple-of-pairs count map.

    Every key in ``locked_keys`` is emitted even when its count is
    zero. Any row value outside ``locked_keys`` (which the classifier
    should never produce, but a future refactor might) appears with
    its own count entry. Resulting tuple is sorted ascending by key
    so the summary is deterministic across runs.
    """
    counts: dict[str, int] = {key: 0 for key in locked_keys}
    for row in rows:
        value = accessor(row)
        if value in counts:
            counts[value] = counts[value] + 1
        else:
            counts[value] = 1
    return tuple(sorted(counts.items()))


def summarize_eligibility(
    rows: tuple[Stage26EligibilityRow, ...],
) -> Stage26EligibilitySummary:
    """Build a ``Stage26EligibilitySummary`` over the row tuple.

    The summary's per-bucket count tuples include every locked
    closed-set token (zero counts included) so downstream consumers
    do not need to special-case absent buckets. The total
    ``row_count`` equals the sum of every per-bucket count.
    """
    return Stage26EligibilitySummary(
        row_count=len(rows),
        counts_by_denominator_status=_counts_by_key(
            rows,
            accessor=lambda row: row.denominator_status,
            locked_keys=DENOMINATOR_STATUSES,
        ),
        counts_by_outcome_eligibility_status=_counts_by_key(
            rows,
            accessor=lambda row: row.outcome_eligibility_status,
            locked_keys=OUTCOME_ELIGIBILITY_STATUSES,
        ),
        counts_by_primary_denominator_reason=_counts_by_key(
            rows,
            accessor=lambda row: row.primary_denominator_reason,
            locked_keys=PRIMARY_DENOMINATOR_REASONS,
        ),
        counts_by_calibration_eligibility_kind=_counts_by_key(
            rows,
            accessor=lambda row: row.calibration_eligibility_kind,
            locked_keys=CALIBRATION_ELIGIBILITY_KINDS,
        ),
        counts_by_measurement_truth_class=_counts_by_key(
            rows,
            accessor=lambda row: row.measurement_truth_class,
            locked_keys=MEASUREMENT_TRUTH_CLASSES,
        ),
        counts_by_source_artifact_kind=_counts_by_key(
            rows,
            accessor=lambda row: row.source_artifact_kind,
            locked_keys=(
                CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
                CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
            ),
        ),
    )


def build_eligibility_result(
    calibration_input_set: Stage26CalibrationInputSet,
) -> Stage26EligibilityResult:
    """Build a Stage 26.2 eligibility bundle from a Stage 26.1 input set.

    Walks the calibration-input bundle's measurement-shape Stage 25
    artifacts in their on-disk row order:

      1. ``migration_measurements`` (one row per Stage 25 row, in
         Stage 25 manifest declaration order),
      2. ``ath_measurements`` (likewise).

    Stage 26.2 NEVER re-sorts, dedupes, joins, or groups rows. The
    Stage 25 manifest pin is carried verbatim onto the result.
    """
    artifact_set = calibration_input_set.reader_result.artifact_set
    manifest_hash = (
        calibration_input_set.stage25_manifest_pin.artifact_sha256
    )

    rows: list[Stage26EligibilityRow] = []
    for index, migration_row in enumerate(
        artifact_set.migration_measurements
    ):
        rows.append(
            build_eligibility_row(
                input_row=migration_row,
                source_artifact_kind=(
                    CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT
                ),
                row_index=index,
                stage25_manifest_hash=manifest_hash,
            )
        )
    for index, ath_row in enumerate(artifact_set.ath_measurements):
        rows.append(
            build_eligibility_row(
                input_row=ath_row,
                source_artifact_kind=(
                    CALIBRATION_INPUT_KIND_ATH_MEASUREMENT
                ),
                row_index=index,
                stage25_manifest_hash=manifest_hash,
            )
        )

    row_tuple = tuple(rows)
    summary = summarize_eligibility(row_tuple)
    return Stage26EligibilityResult(
        stage26_eligibility_version=STAGE26_ELIGIBILITY_VERSION,
        stage25_manifest_pin=(
            calibration_input_set.stage25_manifest_pin
        ),
        rows=row_tuple,
        summary=summary,
    )


__all__ = [
    "MeasurementShapeInputRow",
    "build_eligibility_result",
    "build_eligibility_row",
    "classify_measurement_truth_class",
    "summarize_eligibility",
]
