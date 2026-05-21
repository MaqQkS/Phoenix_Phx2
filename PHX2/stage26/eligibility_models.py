"""Stage 26.2 immutable eligibility record contracts.

Every model is a ``typing.NamedTuple`` -- instances are tuples,
immutable, deterministically ordered, structurally hashable when
their fields are hashable. The shape mirrors Stage 26.1's Stage 25
record style.

Model rules (locked, per Stage 26.0 spec-lock §10 and the Stage 26.2
charter):

  * Models carry no policy fields, no threshold fields, no approval
    fields, no dispatch fields, no cohort fields. Those vocabularies
    belong to Stage 26.3+ and are forbidden in Stage 26.2.
  * ``measurement_truth_class`` is the verbatim Stage 25 token --
    Stage 26.2 NEVER upgrades, renames, or collapses it.
  * The eligibility decision is fully determined by
    ``measurement_truth_class`` per the locked
    ``ELIGIBILITY_DECISION_BY_TRUTH_CLASS`` mapping in
    ``eligibility_constants``.
  * The Stage 25 manifest hash is carried verbatim through every row
    / summary / result so downstream Stage 26.x consumers can pin
    the upstream Stage 25 artifact set without re-reading the
    manifest. The hash is the live sha256 of the Stage 25 manifest
    bytes as recorded on the Stage 26.1 ``Stage26CalibrationInputSet``.

Record kinds:

  * ``Stage26EligibilityDecision``  -- denominator + outcome + reason
                                       + flag tuple, keyed by truth
                                       class.
  * ``Stage26EligibilityRow``       -- one per Stage 26.1
                                       measurement-shape input row.
  * ``Stage26EligibilitySummary``   -- per-bucket counts.
  * ``Stage26EligibilityResult``    -- rows + summary + version axis
                                       + Stage 25 manifest pin.
"""

from __future__ import annotations

from typing import NamedTuple

from PHX2.stage26.models import Stage25ArtifactReference


class Stage26EligibilityDecision(NamedTuple):
    """The locked eligibility decision derived from a truth class.

    A pure projection of the truth-class column of the
    ``ELIGIBILITY_DECISION_BY_TRUTH_CLASS`` mapping. The classifier
    constructs this record by looking up the truth class; the record
    is then either inlined onto a ``Stage26EligibilityRow`` or
    returned to callers that want the raw decision.
    """

    denominator_status: str
    outcome_eligibility_status: str
    primary_denominator_reason: str
    calibration_eligibility_kind: str
    eligible_for_threshold_calibration: bool
    eligible_for_primary_metrics: bool
    eligible_for_observability_metrics: bool


class Stage26EligibilityRow(NamedTuple):
    """One Stage 26.2 eligibility row.

    Built from a single Stage 26.1 measurement-shape input row
    (``MigrationMeasurementInput`` or ``ATHMeasurementInput``). The
    field ordering pins Stage 26.2's locked emission shape.

    Field semantics:

      * ``row_id``                              -- deterministic Stage
        26.2 row identifier: ``f"{source_artifact_kind}#{index}"``.
        The index preserves Stage 25's on-disk row order; Stage 26.2
        NEVER re-sorts rows.
      * ``source_row_id``                       -- the Stage 25
        ``measurement_hash`` of the source row. Stage 26.2 records
        the hash verbatim so callers can pin the row back to its
        Stage 25 evidence without re-reading the JSONL artifact.
      * ``mint``                                -- the source row's
        ``token_mint``, verbatim. Stage 26.2 NEVER joins rows by mint
        -- the field is recorded only so downstream Stage 26.x
        sub-stages can identify the row's subject.
      * ``measurement_truth_class``             -- the Stage 25
        measurement-status token, verbatim. Stage 26.2 NEVER
        rewrites, upgrades, or normalizes this string.
      * ``denominator_status``                  -- locked
        ``DENOMINATOR_STATUSES`` token derived from the truth class.
      * ``outcome_eligibility_status``          -- locked
        ``OUTCOME_ELIGIBILITY_STATUSES`` token derived from the
        truth class.
      * ``primary_denominator_reason``          -- locked
        ``PRIMARY_DENOMINATOR_REASONS`` token derived from the truth
        class. Non-``MEASURED`` rows ALWAYS carry an explicit reason
        token; ``MEASURED`` rows carry ``MEASURED_TRUTH``.
      * ``calibration_eligibility_kind``        -- locked
        ``CALIBRATION_ELIGIBILITY_KINDS`` token; coarser secondary
        slice.
      * ``eligible_for_threshold_calibration``  -- True iff
        ``measurement_truth_class == "MEASURED"``. Non-``MEASURED``
        rows are never threshold-calibration eligible.
      * ``eligible_for_primary_metrics``        -- True iff the row
        contributes to the primary-measured denominator and the
        primary-outcome numerator.
      * ``eligible_for_observability_metrics`` -- True iff the row
        contributes to the broader observability surface. PARTIAL /
        SOURCE_CONFLICT / AMBIGUOUS / (future) WINDOW_INELIGIBLE
        rows are observability-eligible; coverage / scope / rejection
        / not-applicable rows are not.
      * ``source_artifact_kind``                -- the Stage 26.1
        ``CALIBRATION_INPUT_KIND_*`` token identifying which Stage
        25 artifact the row came from.
      * ``stage25_manifest_hash``               -- the live sha256
        of the Stage 25 manifest bytes recorded on the Stage 26.1
        ``Stage26CalibrationInputSet.stage25_manifest_pin``.
    """

    row_id: str
    source_row_id: str
    mint: str
    measurement_truth_class: str
    denominator_status: str
    outcome_eligibility_status: str
    primary_denominator_reason: str
    calibration_eligibility_kind: str
    eligible_for_threshold_calibration: bool
    eligible_for_primary_metrics: bool
    eligible_for_observability_metrics: bool
    source_artifact_kind: str
    stage25_manifest_hash: str


class Stage26EligibilitySummary(NamedTuple):
    """Per-bucket counts over a Stage 26.2 eligibility row tuple.

    Each count map is a deterministic tuple-of-pairs (sorted by key
    ascending). Stage 26.2 emits structured immutable summary data
    -- no ``dict`` is exposed at the top level so downstream code
    cannot accidentally mutate the counts.

    The pairs are emitted for EVERY locked closed-set token (zero
    counts included) so downstream consumers do not need to special-
    case absent buckets. The total ``row_count`` field equals the
    sum of every per-bucket count tuple.
    """

    row_count: int
    counts_by_denominator_status: tuple[tuple[str, int], ...]
    counts_by_outcome_eligibility_status: tuple[tuple[str, int], ...]
    counts_by_primary_denominator_reason: tuple[tuple[str, int], ...]
    counts_by_calibration_eligibility_kind: tuple[tuple[str, int], ...]
    counts_by_measurement_truth_class: tuple[tuple[str, int], ...]
    counts_by_source_artifact_kind: tuple[tuple[str, int], ...]


class Stage26EligibilityResult(NamedTuple):
    """The Stage 26.2 high-level eligibility bundle.

    Carries:

      * ``stage26_eligibility_version`` -- locked Stage 26.2 version
        axis. Bumping the eligibility row / summary shape requires
        bumping this axis.
      * ``stage25_manifest_pin``        -- the Stage 25 manifest
        pin Stage 26.2 consumed. Identical to the pin on the input
        ``Stage26CalibrationInputSet``; recorded here so Stage 26.x
        callers can pin the upstream Stage 25 artifact set without
        walking back into the calibration-input bundle.
      * ``rows``                        -- ordered tuple of
        ``Stage26EligibilityRow``. Order preserves Stage 25's
        on-disk row order: migration-measurement rows first (in
        manifest declaration order), then ATH-measurement rows.
        Stage 26.2 NEVER re-sorts.
      * ``summary``                     -- per-bucket counts over
        ``rows``.
    """

    stage26_eligibility_version: str
    stage25_manifest_pin: Stage25ArtifactReference
    rows: tuple[Stage26EligibilityRow, ...]
    summary: Stage26EligibilitySummary


__all__ = [
    "Stage26EligibilityDecision",
    "Stage26EligibilityResult",
    "Stage26EligibilityRow",
    "Stage26EligibilitySummary",
]
