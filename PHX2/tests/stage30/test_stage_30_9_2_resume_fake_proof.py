"""Stage 30.9.2_RESUME offline dip-filtered resume fake proof tests.

Proves the resume fake proof composes the committed Stage 30.10.2 fake gate
scenario -> the real gate -> the Stage 30.10.3 projector -> the Stage 30.9.2
resume records + summary, with fakes only:

  * the default nine-candidate scenario yields exactly nine candidate proof
    records;
  * exactly three records would proceed toward the private compact dispatch;
  * exactly six records are suppressed BEFORE dispatch reservation;
  * exactly one record is an invalid input;
  * zero records are dispatch failures / transport vetoes / PAYLOAD_REFUSED;
  * the summary counts match the Stage 30.10.3 artifact batch / Stage 30.10.2
    fake gate proof;
  * every record preserves its eligibility + gate reason and the source
    artifact schema version;
  * the live / provider / Discord gating flags are all False; and
  * the proof is deterministic.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

from PHX2.stage30.stage30_10_2_fake_gate_proof import (
    run_stage30_10_2_fake_gate_proof,
)
from PHX2.stage30.stage30_10_3_fake_artifact_proof import (
    run_stage30_10_3_fake_artifact_proof,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
)
from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models import (
    STAGE30_9_2_RESUME_ID,
    Stage30_9_2DipFilteredCandidateProofRecord,
    Stage30_9_2DipFilteredResumeProofSummary,
)
from PHX2.stage30.stage30_9_2_resume_fake_proof import (
    build_dip_filtered_resume_proof_records,
    run_stage30_9_2_resume_fake_proof,
    run_stage30_9_2_resume_fake_proof_with_records,
)


# ---------------------------------------------------------------------------
# 1. The proof builds nine candidate proof records
# ---------------------------------------------------------------------------


def test_proof_builds_nine_candidate_proof_records() -> None:
    records, summary = run_stage30_9_2_resume_fake_proof_with_records()
    assert isinstance(summary, Stage30_9_2DipFilteredResumeProofSummary)
    assert len(records) == 9
    assert summary.candidates_seen == 9
    assert all(
        isinstance(r, Stage30_9_2DipFilteredCandidateProofRecord)
        for r in records
    )


def test_build_records_helper_matches_with_records_entrypoint() -> None:
    records_only = build_dip_filtered_resume_proof_records()
    records, _summary = run_stage30_9_2_resume_fake_proof_with_records()
    assert records_only == records


# ---------------------------------------------------------------------------
# 2. The expected resume proof counts
# ---------------------------------------------------------------------------


def test_summary_expected_counts() -> None:
    summary = run_stage30_9_2_resume_fake_proof()
    assert summary.resume_id == STAGE30_9_2_RESUME_ID == "30.9.2_RESUME"
    assert summary.candidates_seen == 9
    assert summary.candidates_passed == 3
    assert summary.candidates_skipped == 5
    assert summary.invalid_inputs == 1
    assert summary.dispatch_attempts_reserved == 3
    assert summary.dispatch_attempts_suppressed_before_reservation == 6
    assert summary.dispatch_failures_recorded == 0
    assert summary.transport_veto_count == 0
    assert summary.payload_refused_count == 0


def test_summary_gating_flags_are_all_false() -> None:
    summary = run_stage30_9_2_resume_fake_proof()
    assert summary.live_allowed is False
    assert summary.provider_call_allowed is False
    assert summary.discord_send_allowed is False


def test_exactly_three_records_would_proceed_to_dispatch() -> None:
    records = build_dip_filtered_resume_proof_records()
    would = [r for r in records if r.dispatch_reservation_would_be_attempted]
    assert len(would) == 3
    assert [r.candidate_id for r in would] == [
        "cand-tier1",
        "cand-tier2",
        "cand-tier3",
    ]
    for r in would:
        assert r.gate_decision == "PASS_TO_DISPATCH"
        assert r.suppressed_before_dispatch_reservation is False


def test_exactly_six_records_suppressed_before_reservation() -> None:
    records = build_dip_filtered_resume_proof_records()
    suppressed = [
        r for r in records if r.suppressed_before_dispatch_reservation
    ]
    assert len(suppressed) == 6
    for r in suppressed:
        assert r.dispatch_reservation_would_be_attempted is False
        assert r.gate_decision in (
            "SKIP_BEFORE_DISPATCH",
            "INVALID_INPUT",
        )


def test_zero_failures_vetoes_or_refusals_in_any_record() -> None:
    records, summary = run_stage30_9_2_resume_fake_proof_with_records()
    for r in records:
        assert r.dispatch_failure_recorded is False
        assert r.transport_veto_used is False
        assert r.payload_refused_used is False
    assert summary.dispatch_failures_recorded == 0
    assert summary.transport_veto_count == 0
    assert summary.payload_refused_count == 0


# ---------------------------------------------------------------------------
# 3. The counts match the committed Stage 30.10 gate-stack proofs
# ---------------------------------------------------------------------------


def test_counts_match_stage_30_10_3_artifact_batch() -> None:
    summary = run_stage30_9_2_resume_fake_proof()
    batch = run_stage30_10_3_fake_artifact_proof()
    assert summary.candidates_seen == batch.candidates_seen
    assert summary.candidates_passed == batch.candidates_passed
    assert summary.candidates_skipped == batch.candidates_skipped
    assert summary.invalid_inputs == batch.invalid_inputs
    assert (
        summary.dispatch_attempts_reserved == batch.dispatch_attempts_reserved
    )
    assert (
        summary.dispatch_attempts_suppressed_before_reservation
        == batch.dispatch_attempts_suppressed_before_reservation
    )
    assert summary.dispatch_failures_recorded == batch.dispatch_failures_recorded
    assert summary.transport_veto_count == batch.transport_veto_count
    assert summary.payload_refused_count == batch.payload_refused_count


def test_counts_match_stage_30_10_2_fake_gate_proof() -> None:
    summary = run_stage30_9_2_resume_fake_proof()
    gate_summary = run_stage30_10_2_fake_gate_proof()
    assert summary.candidates_seen == gate_summary.candidates_seen
    assert summary.candidates_passed == gate_summary.candidates_passed
    assert summary.candidates_skipped == gate_summary.candidates_skipped
    assert summary.invalid_inputs == gate_summary.invalid_inputs
    assert (
        summary.dispatch_attempts_reserved
        == gate_summary.dispatch_attempts_reserved
    )
    assert (
        summary.dispatch_attempts_suppressed_before_reservation
        == gate_summary.dispatch_attempts_suppressed_before_reservation
    )


# ---------------------------------------------------------------------------
# 4. Reasons + artifact schema preserved on every record
# ---------------------------------------------------------------------------


def test_every_record_preserves_eligibility_and_gate_reason() -> None:
    records = build_dip_filtered_resume_proof_records()
    for r in records:
        assert r.eligibility_decision != ""
        assert r.eligibility_reason != ""
        assert r.gate_decision != ""
        assert r.gate_reason != ""


def test_every_record_preserves_source_artifact_schema_version() -> None:
    records = build_dip_filtered_resume_proof_records()
    for r in records:
        assert r.artifact_schema_version == STAGE30_10_3_ARTIFACT_SCHEMA_VERSION
        assert r.artifact_schema_version == "stage30_10_v0_gate_artifact"


def test_passed_records_carry_eligible_dip_reasons() -> None:
    records = build_dip_filtered_resume_proof_records()
    for r in records:
        if r.gate_decision == "PASS_TO_DISPATCH":
            assert r.eligibility_decision == "ELIGIBLE_DIP"
            assert r.eligibility_reason == "TIER_ALLOWED"
            assert r.gate_reason == "ELIGIBLE_DIP"


def test_skipped_records_carry_not_dip_reason() -> None:
    records = build_dip_filtered_resume_proof_records()
    skipped = [r for r in records if r.gate_decision == "SKIP_BEFORE_DISPATCH"]
    assert len(skipped) == 5
    for r in skipped:
        assert r.gate_reason == "NOT_DIP"
        assert r.eligibility_reason in (
            "TIER_UNKNOWN",
            "TIER_NOT_APPLICABLE",
            "MISSING_ATH",
            "MISSING_MIGRATION",
            "MISSING_DRAWDOWN",
        )


def test_invalid_record_carries_invalid_gate_reason() -> None:
    records = build_dip_filtered_resume_proof_records()
    invalid = [r for r in records if r.gate_decision == "INVALID_INPUT"]
    assert len(invalid) == 1
    rec = invalid[0]
    assert rec.gate_reason == "INVALID_GATE_INPUT"
    assert rec.eligibility_decision == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# 5. created_at carried consistently + caller-injectable
# ---------------------------------------------------------------------------


def test_created_at_consistent_across_summary_and_records() -> None:
    records, summary = run_stage30_9_2_resume_fake_proof_with_records()
    assert summary.created_at_utc == "2026-01-01T00:00:00Z"
    for r in records:
        assert r.created_at_utc == summary.created_at_utc


def test_caller_can_inject_clock() -> None:
    records, summary = run_stage30_9_2_resume_fake_proof_with_records(
        created_at_utc="2026-05-31T00:00:00Z"
    )
    assert summary.created_at_utc == "2026-05-31T00:00:00Z"
    for r in records:
        assert r.created_at_utc == "2026-05-31T00:00:00Z"


# ---------------------------------------------------------------------------
# 6. The proof is deterministic
# ---------------------------------------------------------------------------


def test_summary_is_deterministic() -> None:
    assert (
        run_stage30_9_2_resume_fake_proof()
        == run_stage30_9_2_resume_fake_proof()
    )


def test_proof_with_records_is_deterministic() -> None:
    first = run_stage30_9_2_resume_fake_proof_with_records()
    second = run_stage30_9_2_resume_fake_proof_with_records()
    assert first == second
