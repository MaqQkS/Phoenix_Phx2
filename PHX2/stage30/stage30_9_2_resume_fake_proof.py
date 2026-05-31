"""Stage 30.9.2_RESUME offline dip-filtered resume fake proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.9.2_RESUME
dip-filtered live proof path is correctly dip-FILTERED, using fakes / offline
candidates only. It composes the committed Stage 30.10 dip-gate stack:

    the Stage 30.10.2 default nine-candidate fake gate scenario
      -> the Stage 30.10.2 pre-dispatch gate    (evaluated BEFORE reservation)
      -> the Stage 30.10.3 artifact projection   (records + rolled-up batch)
      -> the Stage 30.9.2 resume proof records + summary

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a
dispatch reservation / real send, NOT a transport-layer veto, and NOT a new
readiness gate. It CONSTRUCTS no filesystem I/O, opens no database, reads no
environment, opens no network connection, and touches no Discord / live
provider path. It only reuses the already-committed Stage 30.10.3 fake
artifact proof (which itself composes the Stage 30.10.2 fake gate scenario ->
the real gate -> the Stage 30.10.3 projector), projects each gate artifact
record into a Stage 30.9.2 dip-filtered candidate proof record, and tallies a
Stage 30.9.2 resume proof summary whose live / provider / Discord gating flags
come from the planning-only Stage 30.9.2 resume plan (all ``False``).

The proof reuses the SAME deterministic nine-candidate scenario, so the resume
proof tally matches the Stage 30.10.2 / 30.10.3 outcome exactly:

  1. Tier 1 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  2. Tier 2 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  3. Tier 3 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  4. Tier Unknown          -> SKIP_BEFORE_DISPATCH  (suppressed before)
  5. Tier Not Applicable   -> SKIP_BEFORE_DISPATCH  (suppressed before)
  6. missing ATH           -> SKIP_BEFORE_DISPATCH  (suppressed before)
  7. missing migration     -> SKIP_BEFORE_DISPATCH  (suppressed before)
  8. malformed drawdown    -> SKIP_BEFORE_DISPATCH  (suppressed before)
  9. invalid candidate_id  -> INVALID_INPUT         (suppressed before)

So the resume proof has nine candidate proof records, exactly three that would
proceed toward the private compact dispatch, exactly six suppressed BEFORE
reservation, and ZERO dispatch failures / transport vetoes / ``PAYLOAD_REFUSED``
uses -- and ``live_allowed`` / ``provider_call_allowed`` / ``discord_send_allowed``
are all ``False``. This proves the live proof will be dip-filtered before the
actual ceremony is ever operator-authorized.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.9.2 resume-models + resume-plan siblings + the
    Stage 30.10.3 fake-artifact-proof + gate-artifact-models siblings (to
    obtain the committed gate-stack proof + the artifact schema version). No
    other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator /
    Stage 28 suppression / live runner / provider / transport import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Tuple

from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models import (
    Stage30_9_2DipFilteredCandidateProofRecord,
    Stage30_9_2DipFilteredResumeProofSummary,
)
from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_plan import (
    STAGE30_9_2_DEFAULT_PLAN_CREATED_AT,
    build_dip_filtered_resume_plan,
)
from PHX2.stage30.stage30_10_3_fake_artifact_proof import (
    run_stage30_10_3_fake_artifact_proof,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
    Stage30_10GateArtifactBatch,
    Stage30_10GateArtifactRecord,
)


# The deterministic caller-injected clock for the default proof (never a
# wall-clock read). It matches the Stage 30.9.2 plan + Stage 30.10.3 fake
# proof clocks so the composed proof is fully deterministic.
_DEFAULT_CREATED_AT: str = STAGE30_9_2_DEFAULT_PLAN_CREATED_AT


# ---------------------------------------------------------------------------
# Pure projector: one gate artifact record -> one resume candidate record
# ---------------------------------------------------------------------------


def _project_artifact_record_to_candidate_proof_record(
    artifact_record: Stage30_10GateArtifactRecord,
) -> Stage30_9_2DipFilteredCandidateProofRecord:
    """Project ONE Stage 30.10.3 gate artifact record into a Stage 30.9.2
    dip-filtered candidate proof record.

    Pure / deterministic / no I/O. Echoes the artifact record's identity +
    eligibility / gate closed-set tokens + the five Stage 30.10.3 derived
    booleans, drops the Stage 30.10.3-internal ``proof_id`` / ``send_allowed``,
    and stamps the source ``artifact_schema_version``. ``created_at_utc`` is
    echoed from the artifact record (never a wall-clock read).
    """
    return Stage30_9_2DipFilteredCandidateProofRecord(
        candidate_id=artifact_record.candidate_id,
        token_mint=artifact_record.token_mint,
        eligibility_decision=artifact_record.eligibility_decision,
        eligibility_reason=artifact_record.eligibility_reason,
        gate_decision=artifact_record.gate_decision,
        gate_reason=artifact_record.gate_reason,
        artifact_schema_version=STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
        dispatch_reservation_would_be_attempted=(
            artifact_record.dispatch_reservation_would_be_attempted
        ),
        suppressed_before_dispatch_reservation=(
            artifact_record.suppressed_before_dispatch_reservation
        ),
        # A dip-filtered pre-dispatch skip is NEVER a dispatch failure, NEVER a
        # transport-layer veto, and NEVER a transport PAYLOAD_REFUSED veto.
        dispatch_failure_recorded=artifact_record.dispatch_failure_recorded,
        transport_veto_used=artifact_record.transport_veto_used,
        payload_refused_used=artifact_record.payload_refused_used,
        created_at_utc=artifact_record.created_at_utc,
    )


# ---------------------------------------------------------------------------
# Pure helpers: batch -> resume records / summary
# ---------------------------------------------------------------------------


def _candidate_proof_records_from_batch(
    batch: Stage30_10GateArtifactBatch,
) -> Tuple[Stage30_9_2DipFilteredCandidateProofRecord, ...]:
    """Project every Stage 30.10.3 artifact record in ``batch`` into a Stage
    30.9.2 dip-filtered candidate proof record (in batch order). Pure; no I/O.
    """
    return tuple(
        _project_artifact_record_to_candidate_proof_record(record)
        for record in batch.records
    )


def _resume_summary_from_batch(
    batch: Stage30_10GateArtifactBatch,
    *,
    resume_id: str,
    live_allowed: bool,
    provider_call_allowed: bool,
    discord_send_allowed: bool,
    created_at_utc: str,
) -> Stage30_9_2DipFilteredResumeProofSummary:
    """Tally a Stage 30.9.2 resume proof summary from a Stage 30.10.3 artifact
    ``batch`` plus the planning-only gating flags. Pure; no I/O.

    The dispatch / suppression / failure / veto / refusal counts come straight
    from the committed Stage 30.10.3 batch (so the resume tally provably
    matches the gate-stack proof); the live / provider / Discord flags come
    from the planning-only resume plan (all ``False``).
    """
    return Stage30_9_2DipFilteredResumeProofSummary(
        resume_id=resume_id,
        candidates_seen=batch.candidates_seen,
        candidates_passed=batch.candidates_passed,
        candidates_skipped=batch.candidates_skipped,
        invalid_inputs=batch.invalid_inputs,
        dispatch_attempts_reserved=batch.dispatch_attempts_reserved,
        dispatch_attempts_suppressed_before_reservation=(
            batch.dispatch_attempts_suppressed_before_reservation
        ),
        dispatch_failures_recorded=batch.dispatch_failures_recorded,
        transport_veto_count=batch.transport_veto_count,
        payload_refused_count=batch.payload_refused_count,
        live_allowed=live_allowed,
        provider_call_allowed=provider_call_allowed,
        discord_send_allowed=discord_send_allowed,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_stage30_9_2_resume_fake_proof_with_records(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Tuple[Stage30_9_2DipFilteredCandidateProofRecord, ...],
    Stage30_9_2DipFilteredResumeProofSummary,
]:
    """Run the offline dip-filtered resume fake proof and return
    ``(records, summary)``.

    Composes the committed Stage 30.10.3 fake artifact proof (the Stage
    30.10.2 nine-candidate scenario -> the real gate -> the Stage 30.10.3
    projector) into a tuple of Stage 30.9.2 dip-filtered candidate proof
    records plus a rolled-up resume summary. The summary's live / provider /
    Discord gating flags come from the planning-only Stage 30.9.2 resume plan
    (all ``False``). Pure / deterministic; reads no clock, no env, no network;
    never sends Discord, never calls a live provider, never performs a
    transport veto, never reserves a dispatch, never writes a file.
    """
    plan = build_dip_filtered_resume_plan(created_at_utc=created_at_utc)
    batch = run_stage30_10_3_fake_artifact_proof(created_at_utc=created_at_utc)
    records = _candidate_proof_records_from_batch(batch)
    summary = _resume_summary_from_batch(
        batch,
        resume_id=plan.resume_id,
        live_allowed=plan.live_allowed,
        provider_call_allowed=plan.provider_call_allowed,
        discord_send_allowed=plan.discord_send_allowed,
        created_at_utc=created_at_utc,
    )
    return records, summary


def run_stage30_9_2_resume_fake_proof(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_9_2DipFilteredResumeProofSummary:
    """Run the offline dip-filtered resume fake proof and return the summary.

    See ``run_stage30_9_2_resume_fake_proof_with_records`` for the full
    composition. Pure / deterministic; offline only.
    """
    _records, summary = run_stage30_9_2_resume_fake_proof_with_records(
        created_at_utc=created_at_utc,
    )
    return summary


def build_dip_filtered_resume_proof_records(
    *,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[Stage30_9_2DipFilteredCandidateProofRecord, ...]:
    """Build the offline dip-filtered resume proof's per-candidate records.

    See ``run_stage30_9_2_resume_fake_proof_with_records`` for the full
    composition. Pure / deterministic; offline only.
    """
    records, _summary = run_stage30_9_2_resume_fake_proof_with_records(
        created_at_utc=created_at_utc,
    )
    return records


__all__ = (
    "run_stage30_9_2_resume_fake_proof_with_records",
    "run_stage30_9_2_resume_fake_proof",
    "build_dip_filtered_resume_proof_records",
)
