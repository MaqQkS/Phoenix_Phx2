"""Stage 26.5 immutable observe-only policy candidate record contracts.

Every model is a ``typing.NamedTuple`` -- instances are tuples,
immutable, deterministically ordered, structurally hashable when
their fields are hashable. The shape mirrors Stage 26.1 / 26.2 /
26.3 / 26.4's record style.

Model rules (locked, per Stage 26.0 spec-lock and the Stage 26.5
charter):

  * Models carry no operator approval actor, no approval timestamp,
    no operator review packet field, no enforcement action, no
    dispatch field, no subscriber / public / private routing field.
    Those vocabularies belong to Stage 26.6+ / Stage 29+ and are
    forbidden in Stage 26.5.
  * Every ``Stage26PolicyCandidate`` carries ``candidate_only =
    True``, ``observe_only = True``, ``operator_approved = False``,
    ``runtime_consumable = False``, and ``enforcement_enabled =
    False`` verbatim. The Stage 26.5 builder NEVER constructs a
    candidate with any of those fields flipped.
  * The Stage 25 manifest hash and the Stage 26.4 generation /
    ordering version axes are carried verbatim through every
    candidate / summary / build result so downstream consumers can
    pin the upstream Stage 25 artifact set and the exact Stage 26.4
    generator that produced each candidate's source evidence.
  * The source Stage 26.4 ``Stage26ThresholdCandidate`` evidence is
    preserved verbatim on every candidate; Stage 26.5 NEVER
    reinterprets a Stage 26.4 count, rate, or status token.

Record kinds:

  * ``Stage26PolicyCandidateConfig``     -- builder knobs.
  * ``Stage26PolicyCandidate``           -- one observe-only
                                            candidate record.
  * ``Stage26PolicyCandidateSummary``    -- per-build summary.
  * ``Stage26PolicyCandidateBuildResult`` -- top-level immutable
                                              bundle the builder
                                              returns.
  * ``Stage26PolicyCandidateArtifactReference`` -- one per-artifact
                                                    on-disk reference.
  * ``Stage26PolicyCandidateArtifactSet`` -- top-level immutable
                                              bundle the writer
                                              returns.
"""

from __future__ import annotations

from typing import NamedTuple

from PHX2.stage26.threshold_models import Stage26ThresholdCandidate


class Stage26PolicyCandidateConfig(NamedTuple):
    """Stage 26.5 builder knobs.

    Every field is an observe-only builder gate, NOT a policy
    decision. Bumping a field does not "approve" anything; it only
    controls which Stage 26.4 candidates the Stage 26.5 builder
    emits as observe-only policy candidate records.

    Fields:

      * ``min_ready_threshold_candidates`` -- informational lower
        bound on how many ``READY_FOR_POLICY_CANDIDATE_REVIEW``
        Stage 26.4 candidates the upstream set carries. The builder
        records the value on every emitted candidate's reason
        string when the bound is not met, but does NOT drop input
        candidates based on it.
      * ``include_non_ready_candidates``   -- when ``True`` (the
        default) the builder emits one Stage 26.5 candidate per
        Stage 26.4 candidate regardless of readiness, mapping
        non-``READY_FOR_POLICY_CANDIDATE_REVIEW`` upstream
        candidates onto an explicit ``BLOCKED_INSUFFICIENT_EVIDENCE``
        status. When ``False`` the builder still emits one record
        per upstream candidate, but caveat lanes are normalized
        onto the blocked status so the operator review surface is
        narrower.
      * ``artifact_schema_version``        -- the locked Stage 26.5
        artifact-schema version axis. Bumping the JSONL row /
        summary / manifest body shape requires bumping this axis.
      * ``candidate_generation_version``   -- the Stage 26.5
        candidate-generation version axis bumped on every builder
        behavior change.
      * ``deterministic_ordering_version`` -- the Stage 26.5
        deterministic-ordering version axis bumped when the
        candidate-ordering convention changes.
    """

    min_ready_threshold_candidates: int
    include_non_ready_candidates: bool
    artifact_schema_version: str
    candidate_generation_version: str
    deterministic_ordering_version: str


class Stage26PolicyCandidate(NamedTuple):
    """One Stage 26.5 observe-only policy candidate record.

    Locked field semantics:

      * ``policy_candidate_id``           -- deterministic ID
        ``f"{candidate_kind}#{source_threshold_candidate_id}"``.
      * ``candidate_kind``                -- locked
        ``POLICY_CANDIDATE_KINDS`` token.
      * ``candidate_status``              -- locked
        ``POLICY_CANDIDATE_STATUSES`` token. Stage 26.5 builder
        NEVER emits a status outside the closed set.
      * ``readiness``                     -- locked
        ``POLICY_CANDIDATE_READINESSES`` token.
      * ``source_threshold_candidate_id`` -- the Stage 26.4
        ``Stage26ThresholdCandidate.candidate_id`` verbatim.
      * ``source_threshold_candidate_kind`` -- the Stage 26.4
        ``THRESHOLD_CANDIDATE_KINDS`` token verbatim.
      * ``cohort_key_dimensions``         -- the source Stage 26.3
        cohort key's ``dimensions`` tuple, verbatim.
      * ``cohort_key_values``             -- the source Stage 26.3
        cohort key's ``values`` tuple, verbatim.
      * ``threshold_direction``           -- the Stage 26.4
        ``THRESHOLD_DIRECTIONS`` token verbatim.
      * ``threshold_value``               -- the Stage 26.4
        candidate's gate value verbatim.
      * ``observed_value``                -- the cohort's observed
        value on the candidate kind's axis verbatim.
      * ``evidence_class``                -- the Stage 26.4
        ``THRESHOLD_EVIDENCE_CLASSES`` token verbatim.
      * ``source_threshold_candidate_status`` -- the Stage 26.4
        ``THRESHOLD_CANDIDATE_STATUSES`` token verbatim.
      * ``source_threshold_review_readiness`` -- the Stage 26.4
        ``THRESHOLD_REVIEW_READINESSES`` token verbatim.
      * ``primary_measured_denominator_count`` -- the Stage 26.4
        evidence summary's primary measured count verbatim.
      * ``threshold_calibration_eligible_count`` -- the Stage 26.4
        evidence summary's threshold-calibration eligible count
        verbatim.
      * ``row_count``                     -- the Stage 26.4 evidence
        summary's cohort row count verbatim.
      * ``coverage_gap_rate``             -- verbatim from Stage 26.4.
      * ``scope_gap_rate``                -- verbatim from Stage 26.4.
      * ``rejection_rate``                -- verbatim from Stage 26.4.
      * ``source_conflict_rate``          -- verbatim from Stage 26.4.
      * ``ambiguous_rate``                -- verbatim from Stage 26.4.
      * ``observability_rate``            -- verbatim from Stage 26.4.
      * ``reason``                        -- short diagnostic string
        describing why the candidate landed in its status /
        readiness state.
      * ``candidate_only``                -- ALWAYS ``True``.
      * ``observe_only``                  -- ALWAYS ``True``.
      * ``operator_approved``             -- ALWAYS ``False``. Stage
        26.5 builder NEVER flips this to ``True``; operator
        approval is Stage 26.6's locked scope.
      * ``runtime_consumable``            -- ALWAYS ``False``. Stage
        26.5 builder NEVER flips this to ``True``; runtime
        enforcement wiring is Stage 29's locked scope.
      * ``enforcement_enabled``           -- ALWAYS ``False``. Stage
        26.5 builder NEVER flips this to ``True``; live enforcement
        wiring is Stage 29's locked scope.
      * ``stage25_manifest_hash``         -- the Stage 25 manifest
        sha256 carried verbatim from the Stage 26.4 source set.
      * ``stage26_threshold_generation_version`` -- the Stage 26.4
        candidate-generation version axis carried verbatim from the
        upstream set.
      * ``stage26_policy_candidate_version`` -- the Stage 26.5
        candidate-generation version axis (the locked
        ``STAGE26_POLICY_CANDIDATE_VERSION`` constant).
    """

    policy_candidate_id: str
    candidate_kind: str
    candidate_status: str
    readiness: str
    source_threshold_candidate_id: str
    source_threshold_candidate_kind: str
    cohort_key_dimensions: tuple[str, ...]
    cohort_key_values: tuple[str, ...]
    threshold_direction: str
    threshold_value: float
    observed_value: float
    evidence_class: str
    source_threshold_candidate_status: str
    source_threshold_review_readiness: str
    primary_measured_denominator_count: int
    threshold_calibration_eligible_count: int
    row_count: int
    coverage_gap_rate: float
    scope_gap_rate: float
    rejection_rate: float
    source_conflict_rate: float
    ambiguous_rate: float
    observability_rate: float
    reason: str
    candidate_only: bool
    observe_only: bool
    operator_approved: bool
    runtime_consumable: bool
    enforcement_enabled: bool
    stage25_manifest_hash: str
    stage26_threshold_generation_version: str
    stage26_policy_candidate_version: str


class Stage26PolicyCandidateSummary(NamedTuple):
    """Stage 26.5 per-build summary.

    Counts mirror the closed-set tuples declared in
    ``policy_candidate_constants``; every locked status / readiness
    token has a dedicated count so downstream consumers do not need
    to special-case absent buckets.
    """

    stage25_manifest_hash: str
    total_policy_candidates: int
    ready_for_operator_review_count: int
    needs_more_measured_rows_count: int
    needs_better_coverage_count: int
    needs_scope_review_count: int
    needs_rejection_review_count: int
    invalid_for_operator_review_count: int
    observe_only_candidate_count: int
    blocked_insufficient_evidence_count: int
    blocked_invalid_threshold_count: int
    blocked_policy_leak_count: int
    blocked_runtime_consumable_count: int
    blocked_approval_leak_count: int
    threshold_policy_candidate_kind_count: int
    coverage_caveat_policy_candidate_kind_count: int
    observability_caveat_policy_candidate_kind_count: int
    rejection_caveat_policy_candidate_kind_count: int
    candidate_only_true_count: int
    observe_only_true_count: int
    operator_approved_false_count: int
    runtime_consumable_false_count: int
    enforcement_enabled_false_count: int
    operator_approved_count: int
    runtime_consumable_count: int
    enforcement_enabled_count: int
    source_threshold_candidate_count: int
    source_threshold_ready_count: int
    deterministic_ordering_version: str
    candidate_generation_version: str
    artifact_schema_version: str


class Stage26PolicyCandidateBuildResult(NamedTuple):
    """Top-level immutable bundle the Stage 26.5 builder returns.

    Fields:

      * ``stage26_policy_candidate_version`` -- locked Stage 26.5
        version axis.
      * ``deterministic_ordering_version``   -- the Stage 26.5
        deterministic-ordering version axis.
      * ``candidate_generation_version``     -- the Stage 26.5
        candidate-generation version axis.
      * ``artifact_schema_version``          -- the Stage 26.5
        artifact-schema version axis.
      * ``stage25_manifest_hash``            -- the live Stage 25
        manifest sha256 carried verbatim from the Stage 26.4 source
        set.
      * ``stage26_threshold_generation_version`` -- the Stage 26.4
        candidate-generation version axis carried verbatim from the
        upstream set.
      * ``stage26_threshold_deterministic_ordering_version`` -- the
        Stage 26.4 deterministic-ordering version axis carried
        verbatim from the upstream set.
      * ``stage26_threshold_version``        -- the Stage 26.4
        ``STAGE26_THRESHOLD_VERSION`` axis carried verbatim.
      * ``config``                           -- the Stage 26.5
        builder config the builder was invoked with.
      * ``policy_candidates``                -- tuple of per-
        candidate records, ordered ascending by
        ``(cohort_key_values, candidate_kind,
           source_threshold_candidate_kind)``.
      * ``summary``                          -- the per-build
        summary record.
      * ``source_threshold_candidate_set_size`` -- the number of
        Stage 26.4 candidates the builder consumed.
    """

    stage26_policy_candidate_version: str
    deterministic_ordering_version: str
    candidate_generation_version: str
    artifact_schema_version: str
    stage25_manifest_hash: str
    stage26_threshold_generation_version: str
    stage26_threshold_deterministic_ordering_version: str
    stage26_threshold_version: str
    config: Stage26PolicyCandidateConfig
    policy_candidates: tuple[Stage26PolicyCandidate, ...]
    summary: Stage26PolicyCandidateSummary
    source_threshold_candidate_set_size: int


class Stage26PolicyCandidateArtifactReference(NamedTuple):
    """One per-artifact on-disk reference the Stage 26.5 writer emits.

    Mirrors the Stage 25 manifest-entry shape but stays in Stage
    26.5 vocabulary: every reference records the artifact's locked
    artifact kind, basename, sha256, byte_count, row_count, and the
    redaction_confirmed flag the writer's redaction sweep set.

    The manifest's self-entry carries the locked Stage 26.5
    sentinel values for sha256 / byte_count / row_count so callers
    can identify the manifest's own entry without reading the
    bytes.
    """

    artifact_kind: str
    basename: str
    sha256: str
    byte_count: int
    row_count: int
    redaction_confirmed: bool


class Stage26PolicyCandidateArtifactSet(NamedTuple):
    """Top-level immutable bundle the Stage 26.5 writer returns.

    Fields:

      * ``output_dir``           -- the caller-supplied output
        directory the writer wrote into.
      * ``rows_path``            -- the on-disk path of the rows
        JSONL artifact.
      * ``summary_path``         -- the on-disk path of the summary
        JSON artifact.
      * ``manifest_path``        -- the on-disk path of the
        manifest JSON artifact.
      * ``artifact_references``  -- tuple of one
        ``Stage26PolicyCandidateArtifactReference`` per artifact,
        sorted ascending by ``basename``.
      * ``manifest_hash``        -- the sha256 of the manifest
        bytes that were actually written. Distinct from the
        self-entry sentinel inside the manifest body.
      * ``redaction_confirmed``  -- True iff every artifact's
        ``redaction_confirmed`` flag is True (the writer refuses to
        promote any artifact whose redaction sweep failed).
    """

    output_dir: str
    rows_path: str
    summary_path: str
    manifest_path: str
    artifact_references: tuple[
        Stage26PolicyCandidateArtifactReference, ...
    ]
    manifest_hash: str
    redaction_confirmed: bool


def preserve_threshold_evidence(
    threshold_candidate: Stage26ThresholdCandidate,
) -> tuple[float, ...]:
    """Return a deterministic tuple of the evidence rate fields the
    Stage 26.5 builder copies onto each emitted policy candidate.

    Stage 26.5 NEVER recomputes a Stage 26.4 rate; it preserves the
    upstream values verbatim. The helper exists primarily for the
    builder's defensive equality checks and the unit tests'
    "preserve evidence" assertions.
    """
    summary = threshold_candidate.evidence_summary
    return (
        summary.coverage_gap_rate,
        summary.scope_gap_rate,
        summary.rejection_rate,
        summary.source_conflict_rate,
        summary.ambiguous_rate,
        summary.observability_rate,
    )


__all__ = [
    "Stage26PolicyCandidate",
    "Stage26PolicyCandidateArtifactReference",
    "Stage26PolicyCandidateArtifactSet",
    "Stage26PolicyCandidateBuildResult",
    "Stage26PolicyCandidateConfig",
    "Stage26PolicyCandidateSummary",
    "preserve_threshold_evidence",
]
