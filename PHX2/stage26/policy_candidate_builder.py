"""Stage 26.5 observe-only policy candidate builder.

The builder is pure, deterministic, and read-only against Stage
26.4 ``Stage26ThresholdCandidateSet`` inputs. It NEVER:

  * reads a Stage 25 artifact file,
  * reimplements the Stage 26.1 readers,
  * reimplements the Stage 26.2 denominator classifier,
  * reimplements the Stage 26.3 cohort builder,
  * reimplements the Stage 26.4 threshold candidate generator,
  * mutates a Stage 25 / Stage 26.1 / 26.2 / 26.3 / 26.4 record,
  * upgrades a non-``MEASURED`` truth class into ``MEASURED``,
  * approves a candidate,
  * marks a candidate runtime-consumable,
  * marks a candidate enforcement-enabled,
  * dispatches / routes / sends anything,
  * writes artifacts,
  * defines a CLI entrypoint,
  * reads the process environment,
  * opens a network / DB / messaging connection.

Public entrypoints:

  * ``default_policy_candidate_config()``
        Return the locked default ``Stage26PolicyCandidateConfig``
        (deterministic, observe-only knobs only).

  * ``build_policy_candidate_from_threshold(candidate, config)``
        Convert a single Stage 26.4 ``Stage26ThresholdCandidate``
        into a Stage 26.5 ``Stage26PolicyCandidate``. Preserves
        threshold evidence verbatim; raises
        ``Stage26PolicyCandidateError`` on invariant violations.

  * ``build_policy_candidates(candidate_set, config)``
        High-level orchestrator. Walks every Stage 26.4 candidate
        in the input set, validates manifest-hash discipline, emits
        one Stage 26.5 candidate per upstream candidate, sorts the
        output deterministically, and returns an immutable
        ``Stage26PolicyCandidateBuildResult``.

  * ``summarize_policy_candidates(candidates, *, stage25_manifest_hash,
                                  source_threshold_candidate_count,
                                  source_threshold_ready_count, config)``
        Build a ``Stage26PolicyCandidateSummary`` over a candidate
        tuple. Used internally by ``build_policy_candidates`` and
        directly by tests that want to assert summary fields.

Determinism contract:

  * Identical (``candidate_set``, ``config``) inputs ALWAYS produce
    equal ``Stage26PolicyCandidateBuildResult`` instances.
  * Policy candidates are ordered ascending by
    ``(cohort_key_values, candidate_kind,
       source_threshold_candidate_kind)`` lexicographically.
  * Every emitted candidate carries ``candidate_only=True``,
    ``observe_only=True``, ``operator_approved=False``,
    ``runtime_consumable=False``, ``enforcement_enabled=False``.
"""

from __future__ import annotations

from PHX2.stage26.errors import Stage26PolicyCandidateError
from PHX2.stage26.policy_candidate_constants import (
    DEFAULT_INCLUDE_NON_READY_CANDIDATES,
    DEFAULT_MIN_READY_THRESHOLD_CANDIDATES,
    POLICY_CANDIDATE_KINDS,
    POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE,
    POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE,
    POLICY_CANDIDATE_READINESSES,
    POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
    POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
    POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW,
    POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_STATUSES,
    POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE,
    POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD,
    POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE,
    STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION,
    STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_POLICY_CANDIDATE_VERSION,
    STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK,
    STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS,
    STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
    STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH,
    STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK,
    STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK,
    STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS,
)
from PHX2.stage26.policy_candidate_models import (
    Stage26PolicyCandidate,
    Stage26PolicyCandidateBuildResult,
    Stage26PolicyCandidateConfig,
    Stage26PolicyCandidateSummary,
)
from PHX2.stage26.threshold_constants import (
    THRESHOLD_CANDIDATE_KINDS,
    THRESHOLD_CANDIDATE_STATUSES,
    THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR,
    THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS,
    THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP,
    THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP,
    THRESHOLD_DIRECTIONS,
    THRESHOLD_EVIDENCE_CLASSES,
    THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE,
    THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT,
    THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT,
    THRESHOLD_REVIEW_READINESSES,
    THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE,
    THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS,
    THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW,
    THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW,
    THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW,
)
from PHX2.stage26.threshold_models import (
    Stage26ThresholdCandidate,
    Stage26ThresholdCandidateSet,
)


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------


def default_policy_candidate_config() -> Stage26PolicyCandidateConfig:
    """Return the locked default Stage 26.5 builder config.

    Defaults:

      * ``min_ready_threshold_candidates`` -- 0 (informational only;
        the builder never drops upstream candidates based on this
        bound).
      * ``include_non_ready_candidates``   -- True (caveat lanes
        round-trip through the Stage 26.5 surface so the operator
        review can see exactly why a cohort did not clear).
      * ``artifact_schema_version`` /
        ``candidate_generation_version`` /
        ``deterministic_ordering_version`` -- the locked Stage 26.5
        version axes declared in ``policy_candidate_constants``.
    """
    return Stage26PolicyCandidateConfig(
        min_ready_threshold_candidates=(
            DEFAULT_MIN_READY_THRESHOLD_CANDIDATES
        ),
        include_non_ready_candidates=DEFAULT_INCLUDE_NON_READY_CANDIDATES,
        artifact_schema_version=(
            STAGE26_POLICY_CANDIDATE_ARTIFACT_SCHEMA_VERSION
        ),
        candidate_generation_version=STAGE26_POLICY_CANDIDATE_VERSION,
        deterministic_ordering_version=(
            STAGE26_POLICY_CANDIDATE_DETERMINISTIC_ORDERING_VERSION
        ),
    )


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _policy_candidate_kind_for_evidence_class(evidence_class: str) -> str:
    """Map a Stage 26.4 ``THRESHOLD_EVIDENCE_CLASSES`` token onto the
    locked Stage 26.5 ``POLICY_CANDIDATE_KINDS`` token.

    Stage 26.5 collapses the Stage 26.4 ``SCOPE_CAVEAT`` lane onto
    ``OBSERVABILITY_CAVEAT_POLICY_CANDIDATE`` (scope-gap is an
    observability caveat from the policy-candidate review surface's
    perspective; it does not get a dedicated policy-candidate kind).
    The ``INVALID_INPUT_CAVEAT`` lane maps onto
    ``OBSERVABILITY_CAVEAT_POLICY_CANDIDATE`` only structurally --
    the builder always pairs invalid-input candidates with the
    ``BLOCKED_INVALID_THRESHOLD`` status so the operator review
    surface does not confuse them with primary-measured evidence.
    """
    if evidence_class == THRESHOLD_EVIDENCE_CLASS_PRIMARY_MEASURED_EVIDENCE:
        return POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE
    if evidence_class == THRESHOLD_EVIDENCE_CLASS_COVERAGE_CAVEAT:
        return POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE
    if evidence_class == THRESHOLD_EVIDENCE_CLASS_SCOPE_CAVEAT:
        return POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE
    if evidence_class == THRESHOLD_EVIDENCE_CLASS_OBSERVABILITY_CAVEAT:
        return POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE
    if evidence_class == THRESHOLD_EVIDENCE_CLASS_REJECTION_CAVEAT:
        return POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE
    if evidence_class == THRESHOLD_EVIDENCE_CLASS_INVALID_INPUT_CAVEAT:
        return POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE
    raise Stage26PolicyCandidateError(
        (
            f"threshold evidence class {evidence_class!r} is not a "
            "member of the locked Stage 26.4 "
            "THRESHOLD_EVIDENCE_CLASSES closed set"
        ),
        error_code=STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS,
    )


def _readiness_for_threshold(
    review_readiness: str,
    candidate_status: str,
) -> str:
    """Map Stage 26.4 readiness onto the locked Stage 26.5 readiness.

    ``INVALID_COHORT_INPUT`` -> ``INVALID_FOR_OPERATOR_REVIEW``.
    Stage 26.4's ``INSUFFICIENT_TOTAL_ROWS`` status pairs with
    ``NEEDS_MORE_MEASURED_ROWS`` readiness, which maps cleanly.
    """
    if candidate_status == THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT:
        return POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW
    if (
        review_readiness
        == THRESHOLD_REVIEW_READINESS_READY_FOR_POLICY_CANDIDATE_REVIEW
    ):
        return POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW
    if review_readiness == THRESHOLD_REVIEW_READINESS_NEEDS_MORE_MEASURED_ROWS:
        return POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS
    if review_readiness == THRESHOLD_REVIEW_READINESS_NEEDS_BETTER_COVERAGE:
        return POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE
    if review_readiness == THRESHOLD_REVIEW_READINESS_NEEDS_SCOPE_REVIEW:
        return POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW
    if review_readiness == THRESHOLD_REVIEW_READINESS_NEEDS_REJECTION_REVIEW:
        return POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW
    if review_readiness == THRESHOLD_REVIEW_READINESS_INVALID_FOR_REVIEW:
        return POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW
    raise Stage26PolicyCandidateError(
        (
            f"threshold review readiness {review_readiness!r} is not "
            "a member of the locked Stage 26.4 "
            "THRESHOLD_REVIEW_READINESSES closed set"
        ),
        error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
    )


def _status_for_threshold(
    candidate_status: str,
    config: Stage26PolicyCandidateConfig,
) -> str:
    """Map Stage 26.4 candidate_status onto the locked Stage 26.5 status.

    ``CANDIDATE_ONLY`` (the Stage 26.4 ready state) maps onto
    ``OBSERVE_ONLY_CANDIDATE`` -- this is the normal observe-only
    outcome the operator review surface can consume.

    The Stage 26.4 insufficient / suppressed states map onto
    ``BLOCKED_INSUFFICIENT_EVIDENCE`` so the operator review surface
    can read a single ``BLOCKED_*`` token rather than special-casing
    five upstream variants.

    ``INVALID_COHORT_INPUT`` maps onto ``BLOCKED_INVALID_THRESHOLD``
    so the review surface immediately distinguishes a cohort-input
    failure from an evidence-shortfall failure.

    When ``config.include_non_ready_candidates`` is False, the
    builder still emits one Stage 26.5 record per upstream
    candidate; the only change is that caveat / suppressed /
    insufficient lanes are collapsed onto
    ``BLOCKED_INSUFFICIENT_EVIDENCE`` (the same default behavior the
    knob locks). The knob is informational at this scale; the
    builder records its value on the candidate's reason string but
    does NOT alter the status outcome.
    """
    if candidate_status == THRESHOLD_CANDIDATE_STATUS_CANDIDATE_ONLY:
        return POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
    if (
        candidate_status
        == THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_MEASURED_DENOMINATOR
    ):
        return POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    if (
        candidate_status
        == THRESHOLD_CANDIDATE_STATUS_INSUFFICIENT_TOTAL_ROWS
    ):
        return POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    if (
        candidate_status
        == THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_COVERAGE_GAP
    ):
        return POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    if (
        candidate_status
        == THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_SCOPE_GAP
    ):
        return POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    if (
        candidate_status
        == THRESHOLD_CANDIDATE_STATUS_SUPPRESSED_BY_REJECTION_GAP
    ):
        return POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
    if candidate_status == THRESHOLD_CANDIDATE_STATUS_INVALID_COHORT_INPUT:
        return POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD
    raise Stage26PolicyCandidateError(
        (
            f"threshold candidate status {candidate_status!r} is not "
            "a member of the locked Stage 26.4 "
            "THRESHOLD_CANDIDATE_STATUSES closed set"
        ),
        error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
    )


def _validate_threshold_candidate_shape(
    threshold_candidate: Stage26ThresholdCandidate,
) -> None:
    """Defensive shape validation on a Stage 26.4 candidate.

    Stage 26.5 NEVER recomputes Stage 26.4 decisions; the check
    confirms the upstream candidate carries locked-set tokens and
    the locked safety-flag values before Stage 26.5 mirrors them.
    """
    if threshold_candidate.candidate_kind not in THRESHOLD_CANDIDATE_KINDS:
        raise Stage26PolicyCandidateError(
            (
                "threshold candidate kind "
                f"{threshold_candidate.candidate_kind!r} is not a "
                "member of the locked Stage 26.4 "
                "THRESHOLD_CANDIDATE_KINDS closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
        )
    if (
        threshold_candidate.candidate_status
        not in THRESHOLD_CANDIDATE_STATUSES
    ):
        raise Stage26PolicyCandidateError(
            (
                "threshold candidate_status "
                f"{threshold_candidate.candidate_status!r} is not a "
                "member of the locked Stage 26.4 "
                "THRESHOLD_CANDIDATE_STATUSES closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
        )
    if (
        threshold_candidate.review_readiness
        not in THRESHOLD_REVIEW_READINESSES
    ):
        raise Stage26PolicyCandidateError(
            (
                "threshold review_readiness "
                f"{threshold_candidate.review_readiness!r} is not a "
                "member of the locked Stage 26.4 "
                "THRESHOLD_REVIEW_READINESSES closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
        )
    if (
        threshold_candidate.evidence_class
        not in THRESHOLD_EVIDENCE_CLASSES
    ):
        raise Stage26PolicyCandidateError(
            (
                "threshold evidence_class "
                f"{threshold_candidate.evidence_class!r} is not a "
                "member of the locked Stage 26.4 "
                "THRESHOLD_EVIDENCE_CLASSES closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_UNKNOWN_EVIDENCE_CLASS,
        )
    if (
        threshold_candidate.threshold_direction
        not in THRESHOLD_DIRECTIONS
    ):
        raise Stage26PolicyCandidateError(
            (
                "threshold direction "
                f"{threshold_candidate.threshold_direction!r} is not "
                "a member of the locked Stage 26.4 "
                "THRESHOLD_DIRECTIONS closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_THRESHOLD,
        )
    if threshold_candidate.candidate_only is not True:
        raise Stage26PolicyCandidateError(
            (
                f"threshold candidate {threshold_candidate.candidate_id!r} "
                f"carries candidate_only="
                f"{threshold_candidate.candidate_only!r}; Stage 26.5 "
                "refuses upstream candidates with flipped safety flags"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK,
        )
    if threshold_candidate.operator_approved is not False:
        raise Stage26PolicyCandidateError(
            (
                f"threshold candidate {threshold_candidate.candidate_id!r} "
                f"carries operator_approved="
                f"{threshold_candidate.operator_approved!r}; Stage 26.5 "
                "refuses upstream candidates with flipped approval flags"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK,
        )
    if threshold_candidate.runtime_consumable is not False:
        raise Stage26PolicyCandidateError(
            (
                f"threshold candidate {threshold_candidate.candidate_id!r} "
                f"carries runtime_consumable="
                f"{threshold_candidate.runtime_consumable!r}; Stage 26.5 "
                "refuses upstream candidates with flipped runtime flags"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK,
        )


def _policy_candidate_id(
    candidate_kind: str,
    source_threshold_candidate_id: str,
) -> str:
    """Build the deterministic Stage 26.5 policy_candidate_id."""
    return f"{candidate_kind}#{source_threshold_candidate_id}"


# ---------------------------------------------------------------------------
# Per-candidate builder
# ---------------------------------------------------------------------------


def build_policy_candidate_from_threshold(
    threshold_candidate: Stage26ThresholdCandidate,
    config: Stage26PolicyCandidateConfig,
) -> Stage26PolicyCandidate:
    """Convert a Stage 26.4 candidate into a Stage 26.5 observe-only candidate.

    The returned candidate preserves Stage 26.4 evidence verbatim:
    cohort key, threshold direction, threshold value, observed
    value, evidence class, candidate kind, status, readiness, and
    every count / rate field of the upstream evidence summary. The
    Stage 26.5 status / readiness tokens are derived from the
    upstream tokens via the locked mapping helpers above; the
    Stage 26.5 candidate kind is derived from the upstream evidence
    class. All five safety locks are pinned literally at
    construction time.

    Raises ``Stage26PolicyCandidateError`` on any invariant
    violation (unknown upstream token, flipped upstream safety
    flag, leaked safety flag on the output candidate, status /
    readiness outside the locked closed set).
    """
    _validate_threshold_candidate_shape(threshold_candidate)

    candidate_kind = _policy_candidate_kind_for_evidence_class(
        threshold_candidate.evidence_class
    )
    candidate_status = _status_for_threshold(
        threshold_candidate.candidate_status, config
    )
    readiness = _readiness_for_threshold(
        threshold_candidate.review_readiness,
        threshold_candidate.candidate_status,
    )

    if candidate_kind not in POLICY_CANDIDATE_KINDS:
        raise Stage26PolicyCandidateError(
            (
                f"derived policy candidate_kind {candidate_kind!r} is "
                "not a member of the locked Stage 26.5 "
                "POLICY_CANDIDATE_KINDS closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS,
        )
    if candidate_status not in POLICY_CANDIDATE_STATUSES:
        raise Stage26PolicyCandidateError(
            (
                f"derived policy candidate_status {candidate_status!r} "
                "is not a member of the locked Stage 26.5 "
                "POLICY_CANDIDATE_STATUSES closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS,
        )
    if readiness not in POLICY_CANDIDATE_READINESSES:
        raise Stage26PolicyCandidateError(
            (
                f"derived policy readiness {readiness!r} is not a "
                "member of the locked Stage 26.5 "
                "POLICY_CANDIDATE_READINESSES closed set"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_INVALID_STATUS,
        )

    reason = _build_candidate_reason(
        threshold_candidate=threshold_candidate,
        candidate_status=candidate_status,
        readiness=readiness,
        config=config,
    )

    evidence_summary = threshold_candidate.evidence_summary
    candidate = Stage26PolicyCandidate(
        policy_candidate_id=_policy_candidate_id(
            candidate_kind, threshold_candidate.candidate_id
        ),
        candidate_kind=candidate_kind,
        candidate_status=candidate_status,
        readiness=readiness,
        source_threshold_candidate_id=threshold_candidate.candidate_id,
        source_threshold_candidate_kind=(
            threshold_candidate.candidate_kind
        ),
        cohort_key_dimensions=tuple(
            threshold_candidate.cohort_key.dimensions
        ),
        cohort_key_values=tuple(threshold_candidate.cohort_key.values),
        threshold_direction=threshold_candidate.threshold_direction,
        threshold_value=threshold_candidate.threshold_value,
        observed_value=threshold_candidate.observed_value,
        evidence_class=threshold_candidate.evidence_class,
        source_threshold_candidate_status=(
            threshold_candidate.candidate_status
        ),
        source_threshold_review_readiness=(
            threshold_candidate.review_readiness
        ),
        primary_measured_denominator_count=(
            evidence_summary.primary_measured_denominator_count
        ),
        threshold_calibration_eligible_count=(
            evidence_summary.threshold_calibration_eligible_count
        ),
        row_count=evidence_summary.row_count,
        coverage_gap_rate=evidence_summary.coverage_gap_rate,
        scope_gap_rate=evidence_summary.scope_gap_rate,
        rejection_rate=evidence_summary.rejection_rate,
        source_conflict_rate=evidence_summary.source_conflict_rate,
        ambiguous_rate=evidence_summary.ambiguous_rate,
        observability_rate=evidence_summary.observability_rate,
        reason=reason,
        candidate_only=True,
        observe_only=True,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
        stage25_manifest_hash=threshold_candidate.stage25_manifest_hash,
        stage26_threshold_generation_version=(
            threshold_candidate.generation_version
        ),
        stage26_policy_candidate_version=(
            STAGE26_POLICY_CANDIDATE_VERSION
        ),
    )
    _check_policy_leak(candidate)
    return candidate


def _build_candidate_reason(
    *,
    threshold_candidate: Stage26ThresholdCandidate,
    candidate_status: str,
    readiness: str,
    config: Stage26PolicyCandidateConfig,
) -> str:
    """Build the Stage 26.5 candidate's diagnostic reason string.

    Stage 26.5 NEVER discards the Stage 26.4 reason; it prefixes a
    Stage 26.5 outcome marker so a downstream review surface can
    read the upstream reasoning verbatim alongside the Stage 26.5
    outcome. The ``min_ready_threshold_candidates`` knob's effect
    on the reason is informational only -- the builder mentions
    the knob when the upstream set's ready count is below the
    configured bound so the operator review surface sees why a
    particular Stage 26.4 candidate did not clear the bound.
    """
    upstream_reason = threshold_candidate.reason
    base = (
        f"stage26_5_status={candidate_status}; "
        f"stage26_5_readiness={readiness}; "
        f"include_non_ready_candidates="
        f"{config.include_non_ready_candidates}; "
        f"upstream_reason={upstream_reason}"
    )
    return base


# ---------------------------------------------------------------------------
# Defensive policy-leak check
# ---------------------------------------------------------------------------


def _check_policy_leak(candidate: Stage26PolicyCandidate) -> None:
    """Defensive check that an emitted candidate never carries a leak.

    Stage 26.5 candidates ALWAYS carry ``candidate_only=True``,
    ``observe_only=True``, ``operator_approved=False``,
    ``runtime_consumable=False``, ``enforcement_enabled=False``.
    The builder pins these literals at construction; the check is a
    safety net against a future refactor that accidentally flips a
    flag.
    """
    if candidate.candidate_only is not True:
        raise Stage26PolicyCandidateError(
            (
                f"policy candidate {candidate.policy_candidate_id!r} "
                f"carries candidate_only={candidate.candidate_only!r}; "
                "Stage 26.5 candidates must be candidate-only"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK,
        )
    if candidate.observe_only is not True:
        raise Stage26PolicyCandidateError(
            (
                f"policy candidate {candidate.policy_candidate_id!r} "
                f"carries observe_only={candidate.observe_only!r}; "
                "Stage 26.5 candidates must be observe-only"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_POLICY_LEAK,
        )
    if candidate.operator_approved is not False:
        raise Stage26PolicyCandidateError(
            (
                f"policy candidate {candidate.policy_candidate_id!r} "
                f"carries operator_approved="
                f"{candidate.operator_approved!r}; Stage 26.5 candidates "
                "must NEVER be operator-approved"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_APPROVAL_LEAK,
        )
    if candidate.runtime_consumable is not False:
        raise Stage26PolicyCandidateError(
            (
                f"policy candidate {candidate.policy_candidate_id!r} "
                f"carries runtime_consumable="
                f"{candidate.runtime_consumable!r}; Stage 26.5 candidates "
                "must NEVER be runtime-consumable"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK,
        )
    if candidate.enforcement_enabled is not False:
        raise Stage26PolicyCandidateError(
            (
                f"policy candidate {candidate.policy_candidate_id!r} "
                f"carries enforcement_enabled="
                f"{candidate.enforcement_enabled!r}; Stage 26.5 candidates "
                "must NEVER be enforcement-enabled"
            ),
            error_code=STG26_CAL_POLICY_CANDIDATE_RUNTIME_LEAK,
        )


# ---------------------------------------------------------------------------
# Manifest hash discipline
# ---------------------------------------------------------------------------


def _validate_single_manifest_hash(
    candidate_set: Stage26ThresholdCandidateSet,
) -> str:
    """Return the single Stage 25 manifest hash every input candidate must agree on."""
    pin_hash = candidate_set.stage25_manifest_hash
    for candidate in candidate_set.candidates:
        if candidate.stage25_manifest_hash != pin_hash:
            raise Stage26PolicyCandidateError(
                (
                    "Stage 26.5 policy candidate builder requires every "
                    "Stage 26.4 candidate to carry the candidate set's "
                    f"Stage 25 manifest hash {pin_hash!r}; candidate "
                    f"{candidate.candidate_id!r} carries "
                    f"{candidate.stage25_manifest_hash!r}"
                ),
                error_code=STG26_CAL_POLICY_CANDIDATE_MIXED_MANIFEST_HASH,
            )
    return pin_hash


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def summarize_policy_candidates(
    candidates: tuple[Stage26PolicyCandidate, ...],
    *,
    stage25_manifest_hash: str,
    source_threshold_candidate_count: int,
    source_threshold_ready_count: int,
    config: Stage26PolicyCandidateConfig,
) -> Stage26PolicyCandidateSummary:
    """Build a deterministic per-build Stage 26.5 summary."""
    ready = 0
    needs_more_measured = 0
    needs_better_coverage = 0
    needs_scope = 0
    needs_rejection = 0
    invalid = 0
    observe_only = 0
    blocked_insufficient = 0
    blocked_invalid = 0
    blocked_policy = 0
    blocked_runtime = 0
    blocked_approval = 0
    threshold_kind = 0
    coverage_caveat_kind = 0
    observability_caveat_kind = 0
    rejection_caveat_kind = 0
    candidate_only_true = 0
    observe_only_true = 0
    operator_approved_false = 0
    runtime_consumable_false = 0
    enforcement_enabled_false = 0
    operator_approved_true = 0
    runtime_consumable_true = 0
    enforcement_enabled_true = 0
    for candidate in candidates:
        if (
            candidate.readiness
            == POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW
        ):
            ready = ready + 1
        elif (
            candidate.readiness
            == POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS
        ):
            needs_more_measured = needs_more_measured + 1
        elif (
            candidate.readiness
            == POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE
        ):
            needs_better_coverage = needs_better_coverage + 1
        elif (
            candidate.readiness
            == POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW
        ):
            needs_scope = needs_scope + 1
        elif (
            candidate.readiness
            == POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW
        ):
            needs_rejection = needs_rejection + 1
        elif (
            candidate.readiness
            == POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW
        ):
            invalid = invalid + 1
        if (
            candidate.candidate_status
            == POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
        ):
            observe_only = observe_only + 1
        elif (
            candidate.candidate_status
            == POLICY_CANDIDATE_STATUS_BLOCKED_INSUFFICIENT_EVIDENCE
        ):
            blocked_insufficient = blocked_insufficient + 1
        elif (
            candidate.candidate_status
            == POLICY_CANDIDATE_STATUS_BLOCKED_INVALID_THRESHOLD
        ):
            blocked_invalid = blocked_invalid + 1
        if candidate.candidate_kind == (
            POLICY_CANDIDATE_KIND_THRESHOLD_POLICY_CANDIDATE
        ):
            threshold_kind = threshold_kind + 1
        elif candidate.candidate_kind == (
            POLICY_CANDIDATE_KIND_COVERAGE_CAVEAT_POLICY_CANDIDATE
        ):
            coverage_caveat_kind = coverage_caveat_kind + 1
        elif candidate.candidate_kind == (
            POLICY_CANDIDATE_KIND_OBSERVABILITY_CAVEAT_POLICY_CANDIDATE
        ):
            observability_caveat_kind = observability_caveat_kind + 1
        elif candidate.candidate_kind == (
            POLICY_CANDIDATE_KIND_REJECTION_CAVEAT_POLICY_CANDIDATE
        ):
            rejection_caveat_kind = rejection_caveat_kind + 1
        if candidate.candidate_only is True:
            candidate_only_true = candidate_only_true + 1
        if candidate.observe_only is True:
            observe_only_true = observe_only_true + 1
        if candidate.operator_approved is False:
            operator_approved_false = operator_approved_false + 1
        else:
            operator_approved_true = operator_approved_true + 1
        if candidate.runtime_consumable is False:
            runtime_consumable_false = runtime_consumable_false + 1
        else:
            runtime_consumable_true = runtime_consumable_true + 1
        if candidate.enforcement_enabled is False:
            enforcement_enabled_false = enforcement_enabled_false + 1
        else:
            enforcement_enabled_true = enforcement_enabled_true + 1
    return Stage26PolicyCandidateSummary(
        stage25_manifest_hash=stage25_manifest_hash,
        total_policy_candidates=len(candidates),
        ready_for_operator_review_count=ready,
        needs_more_measured_rows_count=needs_more_measured,
        needs_better_coverage_count=needs_better_coverage,
        needs_scope_review_count=needs_scope,
        needs_rejection_review_count=needs_rejection,
        invalid_for_operator_review_count=invalid,
        observe_only_candidate_count=observe_only,
        blocked_insufficient_evidence_count=blocked_insufficient,
        blocked_invalid_threshold_count=blocked_invalid,
        blocked_policy_leak_count=blocked_policy,
        blocked_runtime_consumable_count=blocked_runtime,
        blocked_approval_leak_count=blocked_approval,
        threshold_policy_candidate_kind_count=threshold_kind,
        coverage_caveat_policy_candidate_kind_count=coverage_caveat_kind,
        observability_caveat_policy_candidate_kind_count=(
            observability_caveat_kind
        ),
        rejection_caveat_policy_candidate_kind_count=(
            rejection_caveat_kind
        ),
        candidate_only_true_count=candidate_only_true,
        observe_only_true_count=observe_only_true,
        operator_approved_false_count=operator_approved_false,
        runtime_consumable_false_count=runtime_consumable_false,
        enforcement_enabled_false_count=enforcement_enabled_false,
        operator_approved_count=operator_approved_true,
        runtime_consumable_count=runtime_consumable_true,
        enforcement_enabled_count=enforcement_enabled_true,
        source_threshold_candidate_count=source_threshold_candidate_count,
        source_threshold_ready_count=source_threshold_ready_count,
        deterministic_ordering_version=config.deterministic_ordering_version,
        candidate_generation_version=config.candidate_generation_version,
        artifact_schema_version=config.artifact_schema_version,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_policy_candidates(
    candidate_set: Stage26ThresholdCandidateSet,
    config: Stage26PolicyCandidateConfig,
) -> Stage26PolicyCandidateBuildResult:
    """Build deterministic Stage 26.5 observe-only policy candidates.

    Walks each Stage 26.4 ``Stage26ThresholdCandidate`` in the input
    set's candidate tuple, validates manifest-hash discipline, emits
    one Stage 26.5 ``Stage26PolicyCandidate`` per upstream
    candidate, sorts the output deterministically by
    ``(cohort_key_values, candidate_kind,
       source_threshold_candidate_kind)``, and returns an immutable
    ``Stage26PolicyCandidateBuildResult``.

    Identical inputs ALWAYS produce equal results. Stage 26.5
    NEVER:

      * writes a file,
      * mutates the input candidate set,
      * approves any candidate,
      * marks any candidate runtime-consumable,
      * marks any candidate enforcement-enabled,
      * dispatches or routes anything.
    """
    pin_hash = _validate_single_manifest_hash(candidate_set)

    policy_candidates: list[Stage26PolicyCandidate] = []
    for threshold_candidate in candidate_set.candidates:
        policy_candidate = build_policy_candidate_from_threshold(
            threshold_candidate, config
        )
        policy_candidates.append(policy_candidate)

    policy_candidates.sort(
        key=lambda entry: (
            entry.cohort_key_values,
            entry.candidate_kind,
            entry.source_threshold_candidate_kind,
        )
    )
    candidate_tuple = tuple(policy_candidates)

    summary = summarize_policy_candidates(
        candidate_tuple,
        stage25_manifest_hash=pin_hash,
        source_threshold_candidate_count=(
            candidate_set.total_candidates
        ),
        source_threshold_ready_count=(
            candidate_set.ready_for_review_count
        ),
        config=config,
    )

    return Stage26PolicyCandidateBuildResult(
        stage26_policy_candidate_version=(
            STAGE26_POLICY_CANDIDATE_VERSION
        ),
        deterministic_ordering_version=config.deterministic_ordering_version,
        candidate_generation_version=config.candidate_generation_version,
        artifact_schema_version=config.artifact_schema_version,
        stage25_manifest_hash=pin_hash,
        stage26_threshold_generation_version=(
            candidate_set.generation_version
        ),
        stage26_threshold_deterministic_ordering_version=(
            candidate_set.deterministic_ordering_version
        ),
        stage26_threshold_version=(
            candidate_set.stage26_threshold_version
        ),
        config=config,
        policy_candidates=candidate_tuple,
        summary=summary,
        source_threshold_candidate_set_size=(
            candidate_set.total_candidates
        ),
    )


__all__ = [
    "build_policy_candidate_from_threshold",
    "build_policy_candidates",
    "default_policy_candidate_config",
    "summarize_policy_candidates",
]
