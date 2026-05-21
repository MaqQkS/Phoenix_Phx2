"""Stage 26.4 immutable threshold candidate record contracts.

Every model is a ``typing.NamedTuple`` -- instances are tuples,
immutable, deterministically ordered, structurally hashable when
their fields are hashable. The shape mirrors Stage 26.1 / 26.2 /
26.3's record style.

Model rules (locked, per Stage 26.0 spec-lock §4 / §10 and the
Stage 26.4 charter):

  * Models carry no policy rule ID, no approval actor, no approval
    timestamp, no enforcement action, no alert action, no dispatch
    field, no subscriber / public routing field. Those vocabularies
    belong to Stage 26.5+ / Stage 29+ and are forbidden in Stage
    26.4.
  * Every ``Stage26ThresholdCandidate`` carries ``candidate_only =
    True``, ``operator_approved = False``, and ``runtime_consumable
    = False`` verbatim. The Stage 26.4 generator NEVER constructs a
    candidate with any of those fields flipped; the model declares
    them as ordinary ``bool`` fields so the values are pinned in
    the on-the-wire tuple shape rather than relying on an external
    invariant.
  * The Stage 25 manifest hash is carried verbatim through every
    candidate / summary / set so downstream Stage 26.x consumers can
    pin the upstream Stage 25 artifact set without re-reading the
    manifest.
  * The generator preserves Stage 26.3 cohort counts exactly. Stage
    26.4 NEVER recomputes Stage 26.2 denominator decisions or Stage
    26.3 cohort groupings; it consumes the Stage 26.3
    ``Stage26CohortSummary`` count fields verbatim.

Record kinds:

  * ``Stage26ThresholdCandidateConfig``  -- candidate-generation
                                            knobs (deterministic, not
                                            a policy).
  * ``Stage26ThresholdEvidenceSummary``  -- per-cohort observable
                                            summary the candidate
                                            generator builds from a
                                            Stage 26.3 cohort summary.
  * ``Stage26ThresholdCandidate``        -- one candidate proposal.
  * ``Stage26ThresholdCandidateSet``     -- top-level immutable
                                            bundle the generator
                                            returns.
"""

from __future__ import annotations

from typing import NamedTuple

from PHX2.stage26.cohort_models import Stage26CohortKey


class Stage26ThresholdCandidateConfig(NamedTuple):
    """Candidate-generation knobs.

    Every field is a candidate-generation gate, NOT a policy
    decision. Bumping a field does not "approve" a rule; it only
    controls which cohorts a candidate clears for downstream review.
    The default values declared in ``threshold_constants`` are
    permissive on the caveat-rate axes (so the operator opts into
    stricter rates explicitly) and require at least one MEASURED row
    on the measured-denominator axes (so empty cohorts do not
    silently clear the gate).
    """

    min_total_rows: int
    min_primary_measured_count: int
    min_threshold_eligible_count: int
    max_coverage_gap_rate: float
    max_scope_gap_rate: float
    max_rejection_rate: float
    max_source_conflict_rate: float
    max_ambiguous_rate: float
    min_observability_rate: float
    candidate_generation_version: str


class Stage26ThresholdEvidenceSummary(NamedTuple):
    """Per-cohort evidence summary the candidate generator builds.

    Fields are projected verbatim from the source Stage 26.3
    ``Stage26CohortSummary``; the rate fields are deterministic
    safe-zero-denominator divisions of the source counts.

    The summary is the candidate-generator's read-only view of the
    cohort; Stage 26.4 NEVER mutates the source cohort summary, and
    every rate is computed identically across repeated builds.
    """

    cohort_key: Stage26CohortKey
    row_count: int
    primary_measured_denominator_count: int
    threshold_calibration_eligible_count: int
    measured_count: int
    partial_count: int
    source_conflict_count: int
    ambiguous_count: int
    window_ineligible_count: int
    missing_count: int
    unsupported_count: int
    rejected_count: int
    coverage_gap_rate: float
    scope_gap_rate: float
    rejection_rate: float
    source_conflict_rate: float
    ambiguous_rate: float
    observability_rate: float
    stage25_manifest_hash: str


class Stage26ThresholdCandidate(NamedTuple):
    """One Stage 26.4 candidate proposal.

    A candidate proposal records:

      * ``candidate_id``        -- deterministic ID
        ``f"{values_joined}#{candidate_kind}"`` where ``values_joined``
        is the source cohort key's value tuple joined by ``"|"``.
      * ``cohort_key``          -- the Stage 26.3 cohort key verbatim.
      * ``candidate_kind``      -- locked
        ``THRESHOLD_CANDIDATE_KINDS`` token.
      * ``threshold_direction`` -- locked ``THRESHOLD_DIRECTIONS``
        token (``MINIMUM`` / ``MAXIMUM``).
      * ``threshold_value``     -- the gate value from the
        ``Stage26ThresholdCandidateConfig`` axis the candidate kind
        reads.
      * ``observed_value``      -- the cohort's observed value on the
        candidate kind's axis (count for ``MIN_*_COUNT`` kinds, rate
        for ``MAX_*_RATE`` / ``MIN_*_RATE`` kinds).
      * ``candidate_status``    -- locked
        ``THRESHOLD_CANDIDATE_STATUSES`` token.
      * ``evidence_class``      -- locked
        ``THRESHOLD_EVIDENCE_CLASSES`` token. Stage 26.4 distinguishes
        primary-measured evidence from observability / coverage /
        scope / rejection / invalid-input caveats.
      * ``review_readiness``    -- locked
        ``THRESHOLD_REVIEW_READINESSES`` token. ``READY_FOR_POLICY_
        CANDIDATE_REVIEW`` means the cohort cleared Stage 26.4's
        measured-denominator + caveat-rate gates; it does NOT mean
        the candidate is approved or runtime-consumable.
      * ``reason``              -- short diagnostic string describing
        why the candidate landed in its status / readiness state.
      * ``evidence_summary``    -- the source
        ``Stage26ThresholdEvidenceSummary`` (carrying every cohort
        count + rate field).
      * ``candidate_only``      -- ALWAYS ``True`` -- the field is
        the on-the-wire mark that the record is candidate evidence
        only, not a policy rule.
      * ``operator_approved``   -- ALWAYS ``False`` -- the field is
        the on-the-wire mark that the record is NOT operator-
        approved. Stage 26.4 NEVER flips this to ``True``; operator
        approval is Stage 26.6's locked scope.
      * ``runtime_consumable``  -- ALWAYS ``False`` -- the field is
        the on-the-wire mark that the record MUST NOT feed any live
        decision path. Live enforcement wiring is Stage 29's locked
        scope.
      * ``stage25_manifest_hash`` -- the Stage 25 manifest sha256
        carried verbatim from the source cohort summary.
      * ``generation_version``  -- the candidate-generation version
        axis bumped on every generator behavior change.
    """

    candidate_id: str
    cohort_key: Stage26CohortKey
    candidate_kind: str
    threshold_direction: str
    threshold_value: float
    observed_value: float
    candidate_status: str
    evidence_class: str
    review_readiness: str
    reason: str
    evidence_summary: Stage26ThresholdEvidenceSummary
    candidate_only: bool
    operator_approved: bool
    runtime_consumable: bool
    stage25_manifest_hash: str
    generation_version: str


class Stage26ThresholdCandidateSet(NamedTuple):
    """Top-level immutable bundle the generator returns.

    Fields:

      * ``stage26_threshold_version``         -- locked Stage 26.4
        threshold version axis.
      * ``deterministic_ordering_version``    -- the deterministic
        candidate-ordering convention. Bumping the ordering (e.g.
        changing the lex sort) requires bumping this axis.
      * ``generation_version``                -- the candidate-
        generation logic version axis bumped on every generator
        behavior change.
      * ``stage25_manifest_hash``             -- the live Stage 25
        manifest sha256 carried verbatim from the cohort build
        result.
      * ``config``                            -- the candidate-
        generation config the generator was invoked with.
      * ``candidates``                        -- tuple of per-
        candidate records, ordered ascending by ``(cohort_key.values,
        candidate_kind)``.
      * ``total_candidates``                  -- the number of
        candidate records the generator emitted. Equals
        ``len(candidates)``.
      * ``ready_for_review_count``            -- number of candidates
        with ``review_readiness ==
        READY_FOR_POLICY_CANDIDATE_REVIEW``.
      * ``insufficient_measured_count``       -- number of candidates
        with ``candidate_status`` in
        ``{INSUFFICIENT_MEASURED_DENOMINATOR,
           INSUFFICIENT_TOTAL_ROWS}``.
      * ``suppressed_count``                  -- number of candidates
        with ``candidate_status`` in
        ``{SUPPRESSED_BY_COVERAGE_GAP, SUPPRESSED_BY_SCOPE_GAP,
           SUPPRESSED_BY_REJECTION_GAP}``.
      * ``invalid_cohort_count``              -- number of candidates
        with ``candidate_status == INVALID_COHORT_INPUT``.
    """

    stage26_threshold_version: str
    deterministic_ordering_version: str
    generation_version: str
    stage25_manifest_hash: str
    config: Stage26ThresholdCandidateConfig
    candidates: tuple[Stage26ThresholdCandidate, ...]
    total_candidates: int
    ready_for_review_count: int
    insufficient_measured_count: int
    suppressed_count: int
    invalid_cohort_count: int


__all__ = [
    "Stage26ThresholdCandidate",
    "Stage26ThresholdCandidateConfig",
    "Stage26ThresholdCandidateSet",
    "Stage26ThresholdEvidenceSummary",
]
