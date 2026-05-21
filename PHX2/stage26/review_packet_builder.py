"""Stage 26.6 operator review packet builder.

The builder is pure, deterministic, and read-only against Stage
26.5 ``Stage26PolicyCandidateBuildResult`` inputs. It NEVER:

  * reads a Stage 25 artifact file,
  * reimplements the Stage 26.1 / 26.2 / 26.3 / 26.4 / 26.5
    surfaces,
  * mutates a Stage 25 / Stage 26.x record,
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

  * ``default_review_packet_config()``
        Return the locked default ``Stage26ReviewPacketConfig``
        (deterministic, review-only knobs only).

  * ``build_approval_handoff()``
        Return the locked default ``Stage26ApprovalHandoff`` record
        (PENDING_OPERATOR_REVIEW, no actor / timestamp / notes
        populated, every safety lock False).

  * ``build_review_candidate_from_policy_candidate(candidate,
    config)``
        Convert a single Stage 26.5 ``Stage26PolicyCandidate`` into
        a Stage 26.6 ``Stage26ReviewCandidate``. Preserves policy
        candidate evidence verbatim; raises
        ``Stage26ReviewPacketError`` on safety-lock violations.

  * ``summarize_review_candidates(candidates, *, ...)``
        Build a ``Stage26ReviewSummary`` over a candidate tuple.

  * ``build_review_packet(build_result, config)``
        High-level orchestrator. Walks every Stage 26.5 candidate
        in the input build result, validates manifest-hash
        discipline, emits one Stage 26.6 review candidate per
        upstream candidate, sorts the output deterministically, and
        returns an immutable ``Stage26ReviewPacketBuildResult``.

Determinism contract:

  * Identical (``build_result``, ``config``) inputs ALWAYS produce
    equal ``Stage26ReviewPacketBuildResult`` instances.
  * Review candidates are ordered ascending by
    ``(cohort_key_values, candidate_kind,
       source_threshold_candidate_id)`` lexicographically.
  * Every emitted review candidate carries ``review_only=True``,
    ``candidate_only=True``, ``observe_only=True``,
    ``operator_approved=False``, ``runtime_consumable=False``,
    ``enforcement_enabled=False``.
  * The packet's approval-handoff record ALWAYS carries
    ``approval_required=True``,
    ``approval_status=PENDING_OPERATOR_REVIEW``,
    ``approval_actor=None``, ``approval_timestamp_utc=None``,
    ``approval_notes=None``, ``operator_approved=False``,
    ``runtime_consumable=False``, ``enforcement_enabled=False``.
"""

from __future__ import annotations

import hashlib

from PHX2.stage26.errors import Stage26ReviewPacketError
from PHX2.stage26.policy_candidate_constants import (
    POLICY_CANDIDATE_KINDS,
    POLICY_CANDIDATE_READINESSES,
    POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
    POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
    POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW,
    POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW,
    POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
    POLICY_CANDIDATE_STATUSES,
    POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE,
)
from PHX2.stage26.policy_candidate_models import (
    Stage26PolicyCandidate,
    Stage26PolicyCandidateBuildResult,
)
from PHX2.stage26.review_packet_constants import (
    APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW,
    DEFAULT_INCLUDE_BLOCKED_CANDIDATES,
    REVIEW_CANDIDATE_STATUSES,
    REVIEW_CANDIDATE_STATUS_BLOCKED_POLICY_CANDIDATE_LEAK,
    REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW,
    REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE,
    REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS,
    REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW,
    REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW,
    REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW,
    REVIEW_PACKET_STATUS_REVIEW_ONLY_PACKET,
    STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION,
    STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION,
    STAGE26_REVIEW_PACKET_VERSION,
    STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
    STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK,
    STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
    STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
    STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH,
    STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK,
    STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND,
)
from PHX2.stage26.review_packet_models import (
    Stage26ApprovalHandoff,
    Stage26ReviewCandidate,
    Stage26ReviewPacket,
    Stage26ReviewPacketBuildResult,
    Stage26ReviewPacketConfig,
    Stage26ReviewSummary,
)


# ---------------------------------------------------------------------------
# Default config + handoff
# ---------------------------------------------------------------------------


def default_review_packet_config() -> Stage26ReviewPacketConfig:
    """Return the locked default Stage 26.6 builder config.

    Defaults:

      * ``include_blocked_candidates``     -- True (every Stage 26.5
        upstream candidate round-trips through the review surface so
        the operator can see WHY a candidate did not clear).
      * ``artifact_schema_version`` /
        ``review_packet_version`` /
        ``deterministic_ordering_version`` -- the locked Stage 26.6
        version axes declared in ``review_packet_constants``.
    """
    return Stage26ReviewPacketConfig(
        include_blocked_candidates=DEFAULT_INCLUDE_BLOCKED_CANDIDATES,
        artifact_schema_version=(
            STAGE26_REVIEW_PACKET_ARTIFACT_SCHEMA_VERSION
        ),
        review_packet_version=STAGE26_REVIEW_PACKET_VERSION,
        deterministic_ordering_version=(
            STAGE26_REVIEW_PACKET_DETERMINISTIC_ORDERING_VERSION
        ),
    )


def build_approval_handoff() -> Stage26ApprovalHandoff:
    """Return the locked default ``Stage26ApprovalHandoff`` record.

    Stage 26.6 ALWAYS emits this exact record:

      * ``approval_required = True``
      * ``approval_status = PENDING_OPERATOR_REVIEW``
      * ``approval_actor = None``
      * ``approval_timestamp_utc = None``
      * ``approval_notes = None``
      * ``operator_approved = False``
      * ``runtime_consumable = False``
      * ``enforcement_enabled = False``

    Stage 26.6 NEVER populates the actor / timestamp / notes;
    Stage 26.6 NEVER flips any safety lock to True.
    """
    return Stage26ApprovalHandoff(
        approval_required=True,
        approval_status=APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW,
        approval_actor=None,
        approval_timestamp_utc=None,
        approval_notes=None,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
    )


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


_POLICY_READINESS_TO_REVIEW_STATUS: tuple[tuple[str, str], ...] = (
    (
        POLICY_CANDIDATE_READINESS_READY_FOR_OPERATOR_REVIEW,
        REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW,
    ),
    (
        POLICY_CANDIDATE_READINESS_NEEDS_MORE_MEASURED_ROWS,
        REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS,
    ),
    (
        POLICY_CANDIDATE_READINESS_NEEDS_BETTER_COVERAGE,
        REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE,
    ),
    (
        POLICY_CANDIDATE_READINESS_NEEDS_SCOPE_REVIEW,
        REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW,
    ),
    (
        POLICY_CANDIDATE_READINESS_NEEDS_REJECTION_REVIEW,
        REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW,
    ),
    (
        POLICY_CANDIDATE_READINESS_INVALID_FOR_OPERATOR_REVIEW,
        REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW,
    ),
)


def _review_status_for_policy_readiness(readiness: str) -> str:
    """Map a Stage 26.5 readiness onto the Stage 26.6 review status.

    The mapping is one-to-one across the locked readiness vocabulary
    so a downstream reviewer can read the Stage 26.6 status without
    re-deriving the upstream readiness. Unknown tokens raise
    ``Stage26ReviewPacketError`` -- Stage 26.6 refuses to invent a
    fallback status.
    """
    for policy_readiness, review_status in (
        _POLICY_READINESS_TO_REVIEW_STATUS
    ):
        if readiness == policy_readiness:
            return review_status
    raise Stage26ReviewPacketError(
        (
            f"policy candidate readiness {readiness!r} is not a "
            "member of the locked Stage 26.5 "
            "POLICY_CANDIDATE_READINESSES closed set"
        ),
        error_code=STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
    )


# ---------------------------------------------------------------------------
# Defensive shape + safety-lock validation
# ---------------------------------------------------------------------------


def _validate_policy_candidate_safety_locks(
    policy_candidate: Stage26PolicyCandidate,
) -> None:
    """Reject any Stage 26.5 candidate carrying a flipped safety flag.

    Stage 26.5 candidates ALWAYS carry ``candidate_only=True``,
    ``observe_only=True``, ``operator_approved=False``,
    ``runtime_consumable=False``, ``enforcement_enabled=False``.
    Stage 26.6 re-asserts these invariants at consumption time so a
    test fixture (or a future Stage 26.5 refactor) cannot smuggle a
    flipped flag through the review surface.
    """
    if policy_candidate.candidate_only is not True:
        raise Stage26ReviewPacketError(
            (
                f"policy candidate "
                f"{policy_candidate.policy_candidate_id!r} carries "
                f"candidate_only={policy_candidate.candidate_only!r}; "
                "Stage 26.6 refuses upstream candidates with flipped "
                "safety flags"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
        )
    if policy_candidate.observe_only is not True:
        raise Stage26ReviewPacketError(
            (
                f"policy candidate "
                f"{policy_candidate.policy_candidate_id!r} carries "
                f"observe_only={policy_candidate.observe_only!r}; "
                "Stage 26.6 refuses upstream candidates with flipped "
                "safety flags"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
        )
    if policy_candidate.operator_approved is not False:
        raise Stage26ReviewPacketError(
            (
                f"policy candidate "
                f"{policy_candidate.policy_candidate_id!r} carries "
                f"operator_approved="
                f"{policy_candidate.operator_approved!r}; Stage 26.6 "
                "refuses upstream candidates with flipped approval "
                "flags"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
        )
    if policy_candidate.runtime_consumable is not False:
        raise Stage26ReviewPacketError(
            (
                f"policy candidate "
                f"{policy_candidate.policy_candidate_id!r} carries "
                f"runtime_consumable="
                f"{policy_candidate.runtime_consumable!r}; Stage 26.6 "
                "refuses upstream candidates with flipped runtime "
                "flags"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK,
        )
    if policy_candidate.enforcement_enabled is not False:
        raise Stage26ReviewPacketError(
            (
                f"policy candidate "
                f"{policy_candidate.policy_candidate_id!r} carries "
                f"enforcement_enabled="
                f"{policy_candidate.enforcement_enabled!r}; Stage 26.6 "
                "refuses upstream candidates with flipped enforcement "
                "flags"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK,
        )


def _validate_policy_candidate_shape(
    policy_candidate: Stage26PolicyCandidate,
) -> None:
    """Defensive shape validation on a Stage 26.5 candidate.

    Confirms the upstream candidate carries locked-set tokens
    BEFORE Stage 26.6 mirrors them onto a review candidate.
    """
    if policy_candidate.candidate_kind not in POLICY_CANDIDATE_KINDS:
        raise Stage26ReviewPacketError(
            (
                "policy candidate_kind "
                f"{policy_candidate.candidate_kind!r} is not a "
                "member of the locked Stage 26.5 "
                "POLICY_CANDIDATE_KINDS closed set"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_UNKNOWN_CANDIDATE_KIND,
        )
    if (
        policy_candidate.candidate_status
        not in POLICY_CANDIDATE_STATUSES
    ):
        raise Stage26ReviewPacketError(
            (
                "policy candidate_status "
                f"{policy_candidate.candidate_status!r} is not a "
                "member of the locked Stage 26.5 "
                "POLICY_CANDIDATE_STATUSES closed set"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
        )
    if (
        policy_candidate.readiness
        not in POLICY_CANDIDATE_READINESSES
    ):
        raise Stage26ReviewPacketError(
            (
                "policy candidate readiness "
                f"{policy_candidate.readiness!r} is not a member of "
                "the locked Stage 26.5 "
                "POLICY_CANDIDATE_READINESSES closed set"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_INPUT,
        )


# ---------------------------------------------------------------------------
# Per-candidate review-candidate builder
# ---------------------------------------------------------------------------


def _review_candidate_id(source_policy_candidate_id: str) -> str:
    """Build the deterministic Stage 26.6 review_candidate_id."""
    return f"OPERATOR_REVIEW_CANDIDATE#{source_policy_candidate_id}"


def _build_caveat_summary(
    policy_candidate: Stage26PolicyCandidate,
    review_status: str,
) -> str:
    """Build a short diagnostic caveat summary for the operator surface.

    Stage 26.6 NEVER discards the Stage 26.5 reason; it surfaces the
    Stage 26.6 status and readiness mapping alongside the upstream
    Stage 26.5 status / readiness tokens and the upstream reason so a
    downstream reviewer can read the full chain without re-deriving
    it.
    """
    return (
        f"stage26_6_review_status={review_status}; "
        f"stage26_5_status={policy_candidate.candidate_status}; "
        f"stage26_5_readiness={policy_candidate.readiness}; "
        f"upstream_reason={policy_candidate.reason}"
    )


def build_review_candidate_from_policy_candidate(
    policy_candidate: Stage26PolicyCandidate,
    config: Stage26ReviewPacketConfig,
) -> Stage26ReviewCandidate:
    """Convert a Stage 26.5 candidate into a Stage 26.6 review candidate.

    The returned review candidate preserves Stage 26.5 evidence
    verbatim: cohort key, threshold direction, threshold value,
    observed value, evidence class, candidate kind, status,
    readiness, manifest hash, and version axes. The Stage 26.6
    review status is derived from the upstream readiness via the
    locked mapping helper above. Every safety lock and the packet-
    level approval handoff are pinned literally at construction
    time.

    Raises ``Stage26ReviewPacketError`` on any invariant violation
    (unknown upstream token, flipped upstream safety flag, leaked
    safety flag on the output candidate, status outside the locked
    closed set).
    """
    _validate_policy_candidate_safety_locks(policy_candidate)
    _validate_policy_candidate_shape(policy_candidate)

    review_status = _review_status_for_policy_readiness(
        policy_candidate.readiness
    )
    if review_status not in REVIEW_CANDIDATE_STATUSES:
        raise Stage26ReviewPacketError(
            (
                f"derived review_candidate_status {review_status!r} "
                "is not a member of the locked Stage 26.6 "
                "REVIEW_CANDIDATE_STATUSES closed set"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
        )

    caveat_summary = _build_caveat_summary(
        policy_candidate, review_status
    )

    candidate = Stage26ReviewCandidate(
        review_candidate_id=_review_candidate_id(
            policy_candidate.policy_candidate_id
        ),
        source_policy_candidate_id=(
            policy_candidate.policy_candidate_id
        ),
        source_threshold_candidate_id=(
            policy_candidate.source_threshold_candidate_id
        ),
        candidate_kind=policy_candidate.candidate_kind,
        policy_candidate_status=policy_candidate.candidate_status,
        policy_candidate_readiness=policy_candidate.readiness,
        review_candidate_status=review_status,
        cohort_key_dimensions=tuple(
            policy_candidate.cohort_key_dimensions
        ),
        cohort_key_values=tuple(policy_candidate.cohort_key_values),
        threshold_direction=policy_candidate.threshold_direction,
        threshold_value=policy_candidate.threshold_value,
        observed_value=policy_candidate.observed_value,
        evidence_class=policy_candidate.evidence_class,
        caveat_summary=caveat_summary,
        handoff=build_approval_handoff(),
        review_only=True,
        candidate_only=True,
        observe_only=True,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
        stage25_manifest_hash=policy_candidate.stage25_manifest_hash,
        stage26_policy_candidate_version=(
            policy_candidate.stage26_policy_candidate_version
        ),
        stage26_review_packet_version=STAGE26_REVIEW_PACKET_VERSION,
    )
    _check_review_candidate_leak(candidate)
    return candidate


# ---------------------------------------------------------------------------
# Defensive policy-leak check on output review candidates
# ---------------------------------------------------------------------------


def _check_review_candidate_leak(
    candidate: Stage26ReviewCandidate,
) -> None:
    """Defensive check that an emitted review candidate never leaks.

    Stage 26.6 review candidates ALWAYS carry ``review_only=True``,
    ``candidate_only=True``, ``observe_only=True``,
    ``operator_approved=False``, ``runtime_consumable=False``,
    ``enforcement_enabled=False``. The builder pins these literals
    at construction; the check is a safety net against a future
    refactor that accidentally flips a flag.
    """
    if candidate.review_only is not True:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries review_only={candidate.review_only!r}; "
                "Stage 26.6 review candidates must be review-only"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
        )
    if candidate.candidate_only is not True:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries candidate_only={candidate.candidate_only!r}; "
                "Stage 26.6 review candidates must be candidate-only"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
        )
    if candidate.observe_only is not True:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries observe_only={candidate.observe_only!r}; "
                "Stage 26.6 review candidates must be observe-only"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
        )
    if candidate.operator_approved is not False:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries operator_approved="
                f"{candidate.operator_approved!r}; Stage 26.6 review "
                "candidates must NEVER be operator-approved"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
        )
    if candidate.runtime_consumable is not False:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries runtime_consumable="
                f"{candidate.runtime_consumable!r}; Stage 26.6 review "
                "candidates must NEVER be runtime-consumable"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK,
        )
    if candidate.enforcement_enabled is not False:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries enforcement_enabled="
                f"{candidate.enforcement_enabled!r}; Stage 26.6 review "
                "candidates must NEVER be enforcement-enabled"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK,
        )
    handoff = candidate.handoff
    if handoff.approval_required is not True:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"carries approval_required="
                f"{handoff.approval_required!r}; Stage 26.6 review "
                "candidates require approval_required=True"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
        )
    if (
        handoff.approval_status
        != APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
    ):
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries approval_status="
                f"{handoff.approval_status!r}; Stage 26.6 only emits "
                "PENDING_OPERATOR_REVIEW"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_INVALID_STATUS,
        )
    if handoff.approval_actor is not None:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries approval_actor="
                f"{handoff.approval_actor!r}; Stage 26.6 never populates "
                "the actor"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
        )
    if handoff.approval_timestamp_utc is not None:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries approval_timestamp_utc="
                f"{handoff.approval_timestamp_utc!r}; Stage 26.6 never "
                "populates the timestamp"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
        )
    if handoff.approval_notes is not None:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries approval_notes="
                f"{handoff.approval_notes!r}; Stage 26.6 never populates "
                "the notes"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
        )
    if handoff.operator_approved is not False:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries operator_approved="
                f"{handoff.operator_approved!r}; Stage 26.6 handoff "
                "operator_approved must be False"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_APPROVAL_LEAK,
        )
    if handoff.runtime_consumable is not False:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries runtime_consumable="
                f"{handoff.runtime_consumable!r}; Stage 26.6 handoff "
                "runtime_consumable must be False"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_RUNTIME_LEAK,
        )
    if handoff.enforcement_enabled is not False:
        raise Stage26ReviewPacketError(
            (
                f"review candidate {candidate.review_candidate_id!r} "
                f"handoff carries enforcement_enabled="
                f"{handoff.enforcement_enabled!r}; Stage 26.6 handoff "
                "enforcement_enabled must be False"
            ),
            error_code=STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK,
        )


# ---------------------------------------------------------------------------
# Manifest hash discipline
# ---------------------------------------------------------------------------


def _validate_single_manifest_hash(
    build_result: Stage26PolicyCandidateBuildResult,
) -> str:
    """Return the single Stage 25 manifest hash every input candidate must agree on."""
    pin_hash = build_result.stage25_manifest_hash
    for candidate in build_result.policy_candidates:
        if candidate.stage25_manifest_hash != pin_hash:
            raise Stage26ReviewPacketError(
                (
                    "Stage 26.6 review packet builder requires every "
                    "Stage 26.5 candidate to carry the build result's "
                    f"Stage 25 manifest hash {pin_hash!r}; candidate "
                    f"{candidate.policy_candidate_id!r} carries "
                    f"{candidate.stage25_manifest_hash!r}"
                ),
                error_code=STG26_CAL_REVIEW_PACKET_MIXED_MANIFEST_HASH,
            )
    return pin_hash


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def summarize_review_candidates(
    candidates: tuple[Stage26ReviewCandidate, ...],
    *,
    stage25_manifest_hash: str,
    source_policy_candidate_count: int,
    source_policy_ready_count: int,
    config: Stage26ReviewPacketConfig,
) -> Stage26ReviewSummary:
    """Build a deterministic per-build Stage 26.6 summary."""
    ready = 0
    needs_more_measured = 0
    needs_better_coverage = 0
    needs_scope = 0
    needs_rejection = 0
    invalid = 0
    blocked_leak = 0
    review_only_true = 0
    candidate_only_true = 0
    observe_only_true = 0
    operator_approved_true = 0
    runtime_consumable_true = 0
    enforcement_enabled_true = 0
    operator_approved_false = 0
    runtime_consumable_false = 0
    enforcement_enabled_false = 0
    for candidate in candidates:
        status = candidate.review_candidate_status
        if status == REVIEW_CANDIDATE_STATUS_READY_FOR_OPERATOR_REVIEW:
            ready = ready + 1
        elif status == REVIEW_CANDIDATE_STATUS_NEEDS_MORE_MEASURED_ROWS:
            needs_more_measured = needs_more_measured + 1
        elif status == REVIEW_CANDIDATE_STATUS_NEEDS_BETTER_COVERAGE:
            needs_better_coverage = needs_better_coverage + 1
        elif status == REVIEW_CANDIDATE_STATUS_NEEDS_SCOPE_REVIEW:
            needs_scope = needs_scope + 1
        elif status == REVIEW_CANDIDATE_STATUS_NEEDS_REJECTION_REVIEW:
            needs_rejection = needs_rejection + 1
        elif status == REVIEW_CANDIDATE_STATUS_INVALID_FOR_OPERATOR_REVIEW:
            invalid = invalid + 1
        elif (
            status
            == REVIEW_CANDIDATE_STATUS_BLOCKED_POLICY_CANDIDATE_LEAK
        ):
            blocked_leak = blocked_leak + 1
        if candidate.review_only is True:
            review_only_true = review_only_true + 1
        if candidate.candidate_only is True:
            candidate_only_true = candidate_only_true + 1
        if candidate.observe_only is True:
            observe_only_true = observe_only_true + 1
        if candidate.operator_approved is True:
            operator_approved_true = operator_approved_true + 1
        else:
            operator_approved_false = operator_approved_false + 1
        if candidate.runtime_consumable is True:
            runtime_consumable_true = runtime_consumable_true + 1
        else:
            runtime_consumable_false = runtime_consumable_false + 1
        if candidate.enforcement_enabled is True:
            enforcement_enabled_true = enforcement_enabled_true + 1
        else:
            enforcement_enabled_false = enforcement_enabled_false + 1
    return Stage26ReviewSummary(
        stage25_manifest_hash=stage25_manifest_hash,
        total_review_candidates=len(candidates),
        ready_for_operator_review_count=ready,
        needs_more_measured_rows_count=needs_more_measured,
        needs_better_coverage_count=needs_better_coverage,
        needs_scope_review_count=needs_scope,
        needs_rejection_review_count=needs_rejection,
        invalid_for_operator_review_count=invalid,
        blocked_leak_count=blocked_leak,
        review_only_count=review_only_true,
        candidate_only_count=candidate_only_true,
        observe_only_count=observe_only_true,
        operator_approved_count=operator_approved_true,
        runtime_consumable_count=runtime_consumable_true,
        enforcement_enabled_count=enforcement_enabled_true,
        operator_approved_false_count=operator_approved_false,
        runtime_consumable_false_count=runtime_consumable_false,
        enforcement_enabled_false_count=enforcement_enabled_false,
        source_policy_candidate_count=source_policy_candidate_count,
        source_policy_ready_count=source_policy_ready_count,
        deterministic_ordering_version=(
            config.deterministic_ordering_version
        ),
        review_packet_version=config.review_packet_version,
        artifact_schema_version=config.artifact_schema_version,
    )


# ---------------------------------------------------------------------------
# Provenance hash
# ---------------------------------------------------------------------------


def _source_policy_candidate_build_hash(
    build_result: Stage26PolicyCandidateBuildResult,
) -> str:
    """Return a deterministic provenance hash for the upstream build.

    The hash is sha256 of a canonical ``str`` joining the upstream
    Stage 25 manifest hash, the Stage 26.4 / 26.5 version axes, and
    the Stage 26.5 candidate count. The hash is NOT a cryptographic
    commitment to the upstream bytes (Stage 26.5's own manifest hash
    serves that purpose); it is a stable identifier the Stage 26.6
    packet records so a downstream reviewer can verify they are
    looking at the expected upstream build.
    """
    payload = "|".join(
        (
            build_result.stage25_manifest_hash,
            build_result.stage26_threshold_generation_version,
            build_result.stage26_threshold_deterministic_ordering_version,
            build_result.stage26_threshold_version,
            build_result.candidate_generation_version,
            build_result.deterministic_ordering_version,
            build_result.artifact_schema_version,
            str(build_result.source_threshold_candidate_set_size),
            str(len(build_result.policy_candidates)),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _packet_id(stage25_manifest_hash: str) -> str:
    return f"OPERATOR_REVIEW_PACKET#{stage25_manifest_hash}"


def _filter_blocked_candidates(
    policy_candidates: tuple[Stage26PolicyCandidate, ...],
    *,
    include_blocked_candidates: bool,
) -> tuple[Stage26PolicyCandidate, ...]:
    """Honor the ``include_blocked_candidates`` config knob.

    When the knob is False the builder narrows the review surface to
    upstream candidates whose Stage 26.5 status is
    ``OBSERVE_ONLY_CANDIDATE`` (the normal observe-only outcome).
    When True (the default) every upstream candidate round-trips
    through the review surface so the operator can see why a
    candidate did not clear.
    """
    if include_blocked_candidates:
        return policy_candidates
    return tuple(
        candidate
        for candidate in policy_candidates
        if candidate.candidate_status
        == POLICY_CANDIDATE_STATUS_OBSERVE_ONLY_CANDIDATE
    )


def build_review_packet(
    build_result: Stage26PolicyCandidateBuildResult,
    config: Stage26ReviewPacketConfig,
) -> Stage26ReviewPacketBuildResult:
    """Build a deterministic Stage 26.6 operator review packet bundle.

    Walks each Stage 26.5 ``Stage26PolicyCandidate`` in the input
    build result, validates manifest-hash discipline + per-candidate
    safety locks, emits one Stage 26.6
    ``Stage26ReviewCandidate`` per upstream candidate (subject to the
    ``include_blocked_candidates`` knob), sorts the output
    deterministically by ``(cohort_key_values, candidate_kind,
       source_threshold_candidate_id)``, and returns an immutable
    ``Stage26ReviewPacketBuildResult``.

    Identical inputs ALWAYS produce equal results. Stage 26.6
    NEVER:

      * writes a file,
      * mutates the input build result,
      * approves any candidate,
      * marks any candidate runtime-consumable,
      * marks any candidate enforcement-enabled,
      * dispatches or routes anything.
    """
    pin_hash = _validate_single_manifest_hash(build_result)
    filtered = _filter_blocked_candidates(
        build_result.policy_candidates,
        include_blocked_candidates=config.include_blocked_candidates,
    )

    review_candidates_list: list[Stage26ReviewCandidate] = []
    for policy_candidate in filtered:
        review_candidate = build_review_candidate_from_policy_candidate(
            policy_candidate, config
        )
        review_candidates_list.append(review_candidate)

    review_candidates_list.sort(
        key=lambda entry: (
            entry.cohort_key_values,
            entry.candidate_kind,
            entry.source_threshold_candidate_id,
        )
    )
    review_candidates = tuple(review_candidates_list)

    summary = summarize_review_candidates(
        review_candidates,
        stage25_manifest_hash=pin_hash,
        source_policy_candidate_count=len(
            build_result.policy_candidates
        ),
        source_policy_ready_count=(
            build_result.summary.ready_for_operator_review_count
        ),
        config=config,
    )

    handoff = build_approval_handoff()
    build_hash = _source_policy_candidate_build_hash(build_result)

    review_packet = Stage26ReviewPacket(
        packet_id=_packet_id(pin_hash),
        stage25_manifest_hash=pin_hash,
        review_packet_version=STAGE26_REVIEW_PACKET_VERSION,
        packet_status=REVIEW_PACKET_STATUS_REVIEW_ONLY_PACKET,
        review_candidates=review_candidates,
        review_summary=summary,
        approval_handoff=handoff,
        approval_handoff_status=(
            APPROVAL_HANDOFF_STATUS_PENDING_OPERATOR_REVIEW
        ),
        review_only=True,
        operator_approved=False,
        runtime_consumable=False,
        enforcement_enabled=False,
        source_policy_candidate_build_hash=build_hash,
        deterministic_ordering_version=(
            config.deterministic_ordering_version
        ),
    )

    return Stage26ReviewPacketBuildResult(
        stage26_review_packet_version=STAGE26_REVIEW_PACKET_VERSION,
        deterministic_ordering_version=(
            config.deterministic_ordering_version
        ),
        review_packet_version=config.review_packet_version,
        artifact_schema_version=config.artifact_schema_version,
        stage25_manifest_hash=pin_hash,
        stage26_policy_candidate_version=(
            build_result.stage26_policy_candidate_version
        ),
        stage26_threshold_generation_version=(
            build_result.stage26_threshold_generation_version
        ),
        config=config,
        review_packet=review_packet,
        source_policy_candidate_set_size=len(
            build_result.policy_candidates
        ),
    )


__all__ = [
    "build_approval_handoff",
    "build_review_candidate_from_policy_candidate",
    "build_review_packet",
    "default_review_packet_config",
    "summarize_review_candidates",
]
