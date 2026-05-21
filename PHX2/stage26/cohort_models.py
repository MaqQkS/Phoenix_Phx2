"""Stage 26.3 immutable calibration-cohort record contracts.

Every model is a ``typing.NamedTuple`` -- instances are tuples,
immutable, deterministically ordered, structurally hashable when
their fields are hashable. The shape mirrors Stage 26.1 / 26.2's
record style.

Model rules (locked, per Stage 26.0 spec-lock §10 and the Stage 26.3
charter):

  * Models carry no policy fields, no threshold fields, no approval
    fields, no dispatch fields, no enforcement fields. Those
    vocabularies belong to Stage 26.4+ and are forbidden in Stage
    26.3.
  * ``measurement_truth_class`` is the verbatim Stage 25 token --
    Stage 26.3 NEVER upgrades, renames, or collapses it.
  * The cohort builder NEVER recomputes Stage 26.2 denominator /
    outcome / reason / eligibility-flag decisions. Cohort members
    carry those Stage 26.2 fields verbatim.
  * The Stage 25 manifest hash is carried verbatim through every
    member / summary / result so downstream Stage 26.x consumers
    can pin the upstream Stage 25 artifact set without re-reading
    the manifest.

Record kinds:

  * ``Stage26CohortKey``           -- (dimensions, values) pair
                                      identifying a cohort.
  * ``Stage26CohortMember``        -- one row's projection into a
                                      cohort.
  * ``Stage26CohortSummary``       -- per-cohort count summary.
  * ``Stage26CohortBuildRequest``  -- explicit, immutable bundle of
                                      cohort-build inputs (mostly a
                                      documentation surface; the
                                      builder accepts the inputs
                                      directly).
  * ``Stage26CohortBuildResult``   -- top-level immutable bundle the
                                      builder returns.
"""

from __future__ import annotations

from typing import NamedTuple

from PHX2.stage26.eligibility_models import (
    Stage26EligibilityResult,
)
from PHX2.stage26.models import Stage25ArtifactReference


class Stage26CohortKey(NamedTuple):
    """A cohort's locked identifying key.

    ``dimensions`` is the Stage 26.3 cohort-dimension token tuple
    the builder grouped by; ``values`` is the per-dimension value
    string drawn from the corresponding Stage 26.2 row field. Stage
    26.3 enforces ``len(dimensions) == len(values)`` at construction
    time via the cohort builder; callers MUST NOT construct keys
    with mismatched lengths.

    The key is structurally hashable because both fields are tuples
    of strings; Stage 26.3 uses the key as a stable dict-key /
    sort-key.
    """

    dimensions: tuple[str, ...]
    values: tuple[str, ...]


class Stage26CohortMember(NamedTuple):
    """One row's projection into a cohort.

    Fields are carried verbatim from the source Stage 26.2
    ``Stage26EligibilityRow``; Stage 26.3 NEVER mutates, upgrades,
    or recomputes any of them. ``row_status`` is the Stage 26.3
    per-row inclusion outcome (``INCLUDED_IN_COHORT`` for every row
    the builder accepted; ``EXCLUDED_INVALID_INPUT`` is reserved for
    rows whose Stage 26 closed-set tokens are outside the locked
    vocabulary).
    """

    row_id: str
    source_row_id: str
    measurement_truth_class: str
    denominator_status: str
    outcome_eligibility_status: str
    primary_denominator_reason: str
    eligible_for_threshold_calibration: bool
    eligible_for_primary_metrics: bool
    eligible_for_observability_metrics: bool
    source_artifact_kind: str
    stage25_manifest_hash: str
    row_status: str


class Stage26CohortSummary(NamedTuple):
    """Per-cohort count summary.

    Every count field is a non-negative integer; the truth-class
    counts and the denominator-status counts each sum to
    ``row_count`` for ``VALID_COHORT`` cohorts. Stage 26.3 emits the
    distinct truth-class and denominator-status fields side-by-side
    so the Stage 26.4+ threshold candidate generator can read the
    cohort summary without having to re-derive Stage 26.2 splits.

    ``window_ineligible_count`` counts members whose
    ``primary_denominator_reason`` equals the locked Stage 26.2
    ``NOT_MEASURED_WINDOW_INELIGIBLE`` reason token. Stage 26.2 does
    not currently emit that token (window-ineligibility flows
    through ``MISSING`` / ``REJECTED`` per Stage 26.0 spec-lock §10);
    the field is present so a future Stage 26.x sub-stage can
    surface the distinction without breaking the cohort-summary
    schema.

    ``cohort_status`` is a locked ``COHORT_STATUSES`` token;
    ``VALID_COHORT`` is the normal outcome for every non-empty
    cohort assembled from valid Stage 26.2 rows.
    """

    cohort_key: Stage26CohortKey
    row_count: int
    measured_count: int
    partial_count: int
    source_conflict_count: int
    ambiguous_count: int
    window_ineligible_count: int
    missing_count: int
    unsupported_count: int
    rejected_count: int
    not_applicable_count: int
    primary_measured_denominator_count: int
    observability_denominator_count: int
    coverage_gap_denominator_count: int
    scope_gap_denominator_count: int
    rejection_denominator_count: int
    threshold_calibration_eligible_count: int
    primary_metrics_eligible_count: int
    observability_metrics_eligible_count: int
    stage25_manifest_hash: str
    cohort_status: str


class Stage26CohortBuildRequest(NamedTuple):
    """Explicit, immutable bundle of cohort-build inputs.

    Stage 26.3's cohort builder also accepts the inputs directly
    (``build_cohorts(eligibility_result, dimensions)``). The request
    record exists primarily as a typed, structurally hashable carrier
    so callers that want to record the exact inputs they handed the
    builder can do so without constructing an ad-hoc tuple. Stage
    26.3 does NOT mutate the request after the builder accepts it.
    """

    eligibility_result: Stage26EligibilityResult
    dimensions: tuple[str, ...]


class Stage26CohortBuildResult(NamedTuple):
    """Top-level immutable bundle returned by the cohort builder.

    Fields:

      * ``stage26_cohort_version``                -- locked Stage 26.3
        cohort version axis.
      * ``deterministic_ordering_version``        -- the deterministic
        cohort-summary ordering version. Bumping the ordering
        convention (e.g. changing the lex sort on cohort keys)
        requires bumping this axis.
      * ``stage25_manifest_hash``                 -- the live Stage 25
        manifest sha256 carried verbatim from the eligibility
        bundle pin.
      * ``stage25_manifest_pin``                  -- the full Stage 25
        manifest pin (basename + sha256) carried verbatim.
      * ``cohort_dimensions``                     -- the dimensions
        tuple the builder grouped by.
      * ``cohort_summaries``                      -- tuple of per-
        cohort summaries, sorted lexicographically by
        ``cohort_key.values``.
      * ``cohort_members``                        -- tuple of per-
        cohort member tuples, parallel to ``cohort_summaries``. Each
        inner tuple preserves the Stage 26.2 row order verbatim;
        Stage 26.3 NEVER re-sorts members.
      * ``total_input_rows``                      -- the number of
        Stage 26.2 rows the builder received.
      * ``total_cohorted_rows``                   -- the number of
        rows actually included in a cohort. Equals
        ``total_input_rows`` for valid input.
      * ``total_invalid_rows``                    -- the number of
        rows the builder marked
        ``EXCLUDED_INVALID_INPUT``; always ``0`` for valid Stage
        26.2 output.
    """

    stage26_cohort_version: str
    deterministic_ordering_version: str
    stage25_manifest_hash: str
    stage25_manifest_pin: Stage25ArtifactReference
    cohort_dimensions: tuple[str, ...]
    cohort_summaries: tuple[Stage26CohortSummary, ...]
    cohort_members: tuple[tuple[Stage26CohortMember, ...], ...]
    total_input_rows: int
    total_cohorted_rows: int
    total_invalid_rows: int


__all__ = [
    "Stage26CohortBuildRequest",
    "Stage26CohortBuildResult",
    "Stage26CohortKey",
    "Stage26CohortMember",
    "Stage26CohortSummary",
]
