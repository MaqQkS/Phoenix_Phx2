"""Stage 26.6 immutable operator review packet record contracts.

Every model is a ``typing.NamedTuple`` -- instances are tuples,
immutable, deterministically ordered, structurally hashable when
their fields are hashable. The shape mirrors Stage 26.1 / 26.2 /
26.3 / 26.4 / 26.5's record style.

Model rules (locked, per Stage 26.0 spec-lock and the Stage 26.6
charter):

  * Models carry no operator approval actor populated, no approval
    timestamp populated, no enforcement action, no dispatch field,
    no subscriber / public / private routing field. Those
    vocabularies belong to Stage 29+ and are forbidden in Stage 26.6.
  * Every ``Stage26ReviewCandidate`` carries ``review_only = True``,
    ``candidate_only = True``, ``observe_only = True``,
    ``operator_approved = False``, ``runtime_consumable = False``,
    and ``enforcement_enabled = False`` verbatim. The Stage 26.6
    builder NEVER constructs a review candidate with any of those
    fields flipped.
  * Every ``Stage26ApprovalHandoff`` carries ``approval_required =
    True``, ``approval_status = PENDING_OPERATOR_REVIEW``,
    ``approval_actor = None``, ``approval_timestamp_utc = None``,
    ``approval_notes = None``, ``operator_approved = False``,
    ``runtime_consumable = False``, ``enforcement_enabled = False``
    verbatim. Stage 26.6 NEVER populates the actor / timestamp /
    notes; those are forward-pointing placeholders for a future
    operator decision surface.
  * The Stage 25 manifest hash and the Stage 26.5 policy candidate /
    Stage 26.4 threshold candidate version axes are carried verbatim
    through every review candidate / summary / build result so
    downstream consumers can pin the upstream artifact set and the
    exact generators that produced each candidate's source evidence.
  * The source Stage 26.5 ``Stage26PolicyCandidate`` evidence is
    preserved verbatim on every review candidate; Stage 26.6 NEVER
    reinterprets a Stage 26.5 status / readiness / kind / rate.

Record kinds:

  * ``Stage26ReviewPacketConfig``        -- builder knobs.
  * ``Stage26ApprovalHandoff``           -- placeholder approval
                                            handoff record.
  * ``Stage26ReviewCandidate``           -- one review candidate.
  * ``Stage26ReviewSummary``             -- per-build summary.
  * ``Stage26ReviewPacket``              -- the packet body (review
                                            candidates + summary +
                                            handoff).
  * ``Stage26ReviewPacketBuildResult``   -- top-level immutable
                                            bundle the builder
                                            returns.
  * ``Stage26ReviewArtifactReference``   -- one per-artifact on-disk
                                            reference.
  * ``Stage26ReviewArtifactSet``         -- top-level immutable
                                            bundle the writer
                                            returns.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


class Stage26ReviewPacketConfig(NamedTuple):
    """Stage 26.6 builder knobs.

    Every field is an observe-only builder gate, NOT an approval
    decision. Bumping a field does not "approve" anything; it only
    controls which Stage 26.5 candidates the Stage 26.6 builder
    emits as review candidate records.

    Fields:

      * ``include_blocked_candidates``    -- when ``True`` (the
        default) the builder emits one Stage 26.6 review candidate
        per Stage 26.5 candidate regardless of upstream status,
        mapping blocked upstream candidates onto an explicit
        ``NEEDS_*`` / ``INVALID_FOR_OPERATOR_REVIEW`` status. When
        ``False`` the builder skips upstream candidates whose
        Stage 26.5 status is not ``OBSERVE_ONLY_CANDIDATE`` so the
        operator review surface is narrower.
      * ``artifact_schema_version``       -- the locked Stage 26.6
        artifact-schema version axis.
      * ``review_packet_version``         -- the Stage 26.6 review
        packet generation version axis.
      * ``deterministic_ordering_version`` -- the Stage 26.6
        deterministic-ordering version axis.
    """

    include_blocked_candidates: bool
    artifact_schema_version: str
    review_packet_version: str
    deterministic_ordering_version: str


class Stage26ApprovalHandoff(NamedTuple):
    """Stage 26.6 placeholder approval-handoff record.

    Stage 26.6 ALWAYS emits this record with the fields locked to
    placeholder values:

      * ``approval_required = True``
      * ``approval_status   = PENDING_OPERATOR_REVIEW``
      * ``approval_actor    = None``
      * ``approval_timestamp_utc = None``
      * ``approval_notes    = None``
      * ``operator_approved = False``
      * ``runtime_consumable = False``
      * ``enforcement_enabled = False``

    Stage 26.6 NEVER populates the actor / timestamp / notes;
    Stage 26.6 NEVER flips any of the three safety locks. The record
    is forward-pointing -- a later, explicitly-authorized stage (per
    the Stage 26.0 spec-lock §11 roadmap, Stage 29) MAY consume the
    handoff record and produce an operator decision; Stage 26.6
    itself never grants approval.
    """

    approval_required: bool
    approval_status: str
    approval_actor: Optional[str]
    approval_timestamp_utc: Optional[str]
    approval_notes: Optional[str]
    operator_approved: bool
    runtime_consumable: bool
    enforcement_enabled: bool


class Stage26ReviewCandidate(NamedTuple):
    """One Stage 26.6 review candidate record.

    Locked field semantics:

      * ``review_candidate_id``               -- deterministic ID
        ``f"OPERATOR_REVIEW_CANDIDATE#{source_policy_candidate_id}"``.
      * ``source_policy_candidate_id``        -- the Stage 26.5
        ``Stage26PolicyCandidate.policy_candidate_id`` verbatim.
      * ``source_threshold_candidate_id``     -- the Stage 26.4
        ``Stage26ThresholdCandidate.candidate_id`` verbatim
        (carried through Stage 26.5).
      * ``candidate_kind``                    -- the Stage 26.5
        ``POLICY_CANDIDATE_KINDS`` token verbatim.
      * ``policy_candidate_status``           -- the Stage 26.5
        ``POLICY_CANDIDATE_STATUSES`` token verbatim.
      * ``policy_candidate_readiness``        -- the Stage 26.5
        ``POLICY_CANDIDATE_READINESSES`` token verbatim.
      * ``review_candidate_status``           -- locked
        ``REVIEW_CANDIDATE_STATUSES`` token derived from the upstream
        readiness.
      * ``cohort_key_dimensions``             -- the source Stage
        26.3 cohort key's ``dimensions`` tuple, verbatim.
      * ``cohort_key_values``                 -- the source Stage
        26.3 cohort key's ``values`` tuple, verbatim.
      * ``threshold_direction``               -- the Stage 26.4
        ``THRESHOLD_DIRECTIONS`` token verbatim.
      * ``threshold_value``                   -- the Stage 26.4
        candidate's gate value verbatim.
      * ``observed_value``                    -- the cohort's observed
        value verbatim.
      * ``evidence_class``                    -- the Stage 26.4
        ``THRESHOLD_EVIDENCE_CLASSES`` token verbatim.
      * ``caveat_summary``                    -- short diagnostic
        string describing the upstream evidence caveat / readiness
        outcome for the operator review surface.
      * ``handoff``                           -- the
        ``Stage26ApprovalHandoff`` placeholder record carried on
        every review candidate so a downstream reviewer can read
        each candidate's approval-handoff fields without re-deriving
        them.
      * ``review_only`` / ``candidate_only`` / ``observe_only``      --
        ALWAYS ``True``.
      * ``operator_approved`` / ``runtime_consumable`` /
        ``enforcement_enabled``                                       --
        ALWAYS ``False``.
      * ``stage25_manifest_hash``             -- the Stage 25
        manifest sha256 carried verbatim from the Stage 26.5 source
        candidate.
      * ``stage26_policy_candidate_version``  -- the Stage 26.5
        candidate-generation version axis carried verbatim from the
        upstream candidate.
      * ``stage26_review_packet_version``     -- the Stage 26.6
        review packet version axis (the locked
        ``STAGE26_REVIEW_PACKET_VERSION`` constant).
    """

    review_candidate_id: str
    source_policy_candidate_id: str
    source_threshold_candidate_id: str
    candidate_kind: str
    policy_candidate_status: str
    policy_candidate_readiness: str
    review_candidate_status: str
    cohort_key_dimensions: tuple[str, ...]
    cohort_key_values: tuple[str, ...]
    threshold_direction: str
    threshold_value: float
    observed_value: float
    evidence_class: str
    caveat_summary: str
    handoff: Stage26ApprovalHandoff
    review_only: bool
    candidate_only: bool
    observe_only: bool
    operator_approved: bool
    runtime_consumable: bool
    enforcement_enabled: bool
    stage25_manifest_hash: str
    stage26_policy_candidate_version: str
    stage26_review_packet_version: str


class Stage26ReviewSummary(NamedTuple):
    """Stage 26.6 per-build summary.

    Counts mirror the closed-set tuples declared in
    ``review_packet_constants``; every locked review-candidate
    status has a dedicated count so downstream consumers do not
    need to special-case absent buckets.
    """

    stage25_manifest_hash: str
    total_review_candidates: int
    ready_for_operator_review_count: int
    needs_more_measured_rows_count: int
    needs_better_coverage_count: int
    needs_scope_review_count: int
    needs_rejection_review_count: int
    invalid_for_operator_review_count: int
    blocked_leak_count: int
    review_only_count: int
    candidate_only_count: int
    observe_only_count: int
    operator_approved_count: int
    runtime_consumable_count: int
    enforcement_enabled_count: int
    operator_approved_false_count: int
    runtime_consumable_false_count: int
    enforcement_enabled_false_count: int
    source_policy_candidate_count: int
    source_policy_ready_count: int
    deterministic_ordering_version: str
    review_packet_version: str
    artifact_schema_version: str


class Stage26ReviewPacket(NamedTuple):
    """Stage 26.6 operator review packet body.

    Fields:

      * ``packet_id``                          -- deterministic ID
        ``f"OPERATOR_REVIEW_PACKET#{stage25_manifest_hash}"``.
      * ``stage25_manifest_hash``              -- the Stage 25
        manifest sha256 carried verbatim from the Stage 26.5 build
        result.
      * ``review_packet_version``              -- the locked Stage
        26.6 review-packet version axis.
      * ``packet_status``                      -- locked
        ``REVIEW_PACKET_STATUSES`` token. Stage 26.6 emits
        ``REVIEW_ONLY_PACKET`` for a clean build; the ``BLOCKED_*``
        tokens are reserved for builds that hit a safety-lock or
        redaction failure.
      * ``review_candidates``                  -- tuple of per-
        candidate ``Stage26ReviewCandidate`` records, ordered
        ascending by ``(cohort_key_values, candidate_kind,
        source_threshold_candidate_id)``.
      * ``review_summary``                     -- the per-build
        ``Stage26ReviewSummary`` record.
      * ``approval_handoff``                   -- the packet-level
        ``Stage26ApprovalHandoff`` placeholder record.
      * ``approval_handoff_status``            -- the packet-level
        approval-handoff status (always
        ``PENDING_OPERATOR_REVIEW`` in Stage 26.6).
      * ``review_only`` / ``operator_approved`` /
        ``runtime_consumable`` / ``enforcement_enabled``                --
        packet-level safety locks; ALWAYS ``True`` for
        ``review_only`` and ALWAYS ``False`` for the other three.
      * ``source_policy_candidate_build_hash`` -- a deterministic
        stable hash of the upstream Stage 26.5 build result's
        provenance fields (Stage 25 manifest hash + Stage 26.4 /
        26.5 version axes). NOT a cryptographic commitment; the
        Stage 26.5 build itself is unchanged.
      * ``deterministic_ordering_version``     -- the locked Stage
        26.6 deterministic-ordering version axis.
    """

    packet_id: str
    stage25_manifest_hash: str
    review_packet_version: str
    packet_status: str
    review_candidates: tuple[Stage26ReviewCandidate, ...]
    review_summary: Stage26ReviewSummary
    approval_handoff: Stage26ApprovalHandoff
    approval_handoff_status: str
    review_only: bool
    operator_approved: bool
    runtime_consumable: bool
    enforcement_enabled: bool
    source_policy_candidate_build_hash: str
    deterministic_ordering_version: str


class Stage26ReviewPacketBuildResult(NamedTuple):
    """Top-level immutable bundle the Stage 26.6 builder returns.

    Fields:

      * ``stage26_review_packet_version``                -- locked
        Stage 26.6 version axis.
      * ``deterministic_ordering_version``               -- the Stage
        26.6 deterministic-ordering version axis.
      * ``review_packet_version``                        -- the Stage
        26.6 review-packet-generation version axis.
      * ``artifact_schema_version``                      -- the Stage
        26.6 artifact-schema version axis.
      * ``stage25_manifest_hash``                        -- the live
        Stage 25 manifest sha256 carried verbatim from the Stage
        26.5 source build result.
      * ``stage26_policy_candidate_version``             -- the Stage
        26.5 candidate-generation version axis carried verbatim from
        the upstream build result.
      * ``stage26_threshold_generation_version``         -- the Stage
        26.4 candidate-generation version axis carried verbatim from
        the upstream build result.
      * ``config``                                       -- the Stage
        26.6 builder config the builder was invoked with.
      * ``review_packet``                                -- the
        ``Stage26ReviewPacket`` body.
      * ``source_policy_candidate_set_size``             -- the
        number of Stage 26.5 candidates the builder consumed.
    """

    stage26_review_packet_version: str
    deterministic_ordering_version: str
    review_packet_version: str
    artifact_schema_version: str
    stage25_manifest_hash: str
    stage26_policy_candidate_version: str
    stage26_threshold_generation_version: str
    config: Stage26ReviewPacketConfig
    review_packet: Stage26ReviewPacket
    source_policy_candidate_set_size: int


class Stage26ReviewArtifactReference(NamedTuple):
    """One per-artifact on-disk reference the Stage 26.6 writer emits.

    Mirrors the Stage 25 / Stage 26.5 manifest-entry shape but stays
    in Stage 26.6 vocabulary: every reference records the artifact's
    locked artifact kind, basename, sha256, byte_count, row_count,
    and the redaction_confirmed flag the writer's redaction sweep
    set.

    The manifest's self-entry carries the locked Stage 26.6 sentinel
    values for sha256 / byte_count / row_count so callers can
    identify the manifest's own entry without reading the bytes.
    """

    artifact_kind: str
    basename: str
    sha256: str
    byte_count: int
    row_count: int
    redaction_confirmed: bool


class Stage26ReviewArtifactSet(NamedTuple):
    """Top-level immutable bundle the Stage 26.6 writer returns.

    Fields:

      * ``output_dir``           -- the caller-supplied output
        directory the writer wrote into.
      * ``packet_path``          -- the on-disk path of the packet
        JSON artifact.
      * ``candidate_rows_path``  -- the on-disk path of the
        candidate rows JSONL artifact.
      * ``summary_path``         -- the on-disk path of the summary
        JSON artifact.
      * ``manifest_path``        -- the on-disk path of the
        manifest JSON artifact.
      * ``artifact_references``  -- tuple of one
        ``Stage26ReviewArtifactReference`` per artifact, sorted
        ascending by ``basename``.
      * ``manifest_hash``        -- the sha256 of the manifest
        bytes that were actually written. Distinct from the
        self-entry sentinel inside the manifest body.
      * ``redaction_confirmed``  -- True iff every artifact's
        ``redaction_confirmed`` flag is True (the writer refuses to
        promote any artifact whose redaction sweep failed).
    """

    output_dir: str
    packet_path: str
    candidate_rows_path: str
    summary_path: str
    manifest_path: str
    artifact_references: tuple[
        Stage26ReviewArtifactReference, ...
    ]
    manifest_hash: str
    redaction_confirmed: bool


__all__ = [
    "Stage26ApprovalHandoff",
    "Stage26ReviewArtifactReference",
    "Stage26ReviewArtifactSet",
    "Stage26ReviewCandidate",
    "Stage26ReviewPacket",
    "Stage26ReviewPacketBuildResult",
    "Stage26ReviewPacketConfig",
    "Stage26ReviewSummary",
]
