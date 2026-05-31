"""Stage 30.10.3 offline fake gate artifact proof tests.

Proves the offline artifact-integration proof composes the Stage 30.10.2 fake
gate scenario -> the real gate -> the Stage 30.10.3 projector -> an in-memory
artifact sink, with fakes only:

  * the default nine-candidate scenario yields exactly nine artifact records;
  * exactly three records would attempt a dispatch reservation;
  * exactly six records are suppressed BEFORE dispatch reservation;
  * zero records are dispatch failures / transport vetoes / PAYLOAD_REFUSED;
  * the passed / skipped / invalid counts match the Stage 30.10.2 fake gate
    proof;
  * every skipped / passed / invalid record preserves its eligibility + gate
    reason;
  * the in-memory sink retains all nine records (no filesystem write); and
  * the proof is deterministic.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

from PHX2.stage30.stage30_10_2_fake_gate_proof import (
    default_pre_dispatch_gate_scenario,
    run_stage30_10_2_fake_gate_proof,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    Stage30_10PreDispatchGateScenario,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
    Stage30_10GateArtifactBatch,
    Stage30_10GateArtifactRecord,
    Stage30_10GateArtifactSinkResult,
)
from PHX2.stage30.stage30_10_3_fake_artifact_proof import (
    Stage30_10InMemoryGateArtifactSink,
    build_fake_gate_records,
    run_stage30_10_3_fake_artifact_proof,
    run_stage30_10_3_fake_artifact_proof_into_sink,
)


# ---------------------------------------------------------------------------
# 1. The proof builds nine artifact records from the nine-candidate scenario
# ---------------------------------------------------------------------------


def test_proof_builds_nine_artifact_records() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    assert isinstance(batch, Stage30_10GateArtifactBatch)
    assert len(batch.records) == 9
    assert batch.candidates_seen == 9
    assert all(
        isinstance(r, Stage30_10GateArtifactRecord) for r in batch.records
    )


def test_build_fake_gate_records_matches_scenario_length() -> None:
    scenario = default_pre_dispatch_gate_scenario()
    gate_records = build_fake_gate_records(scenario)
    assert len(gate_records) == len(scenario.gate_inputs) == 9


# ---------------------------------------------------------------------------
# 2. The expected artifact batch counts
# ---------------------------------------------------------------------------


def test_batch_expected_counts() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    assert batch.candidates_seen == 9
    assert batch.candidates_passed == 3
    assert batch.candidates_skipped == 5
    assert batch.invalid_inputs == 1
    assert batch.dispatch_attempts_reserved == 3
    assert batch.dispatch_attempts_suppressed_before_reservation == 6
    assert batch.dispatch_failures_recorded == 0
    assert batch.transport_veto_count == 0
    assert batch.payload_refused_count == 0


def test_exactly_three_records_would_attempt_reservation() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    would_attempt = [
        r for r in batch.records
        if r.dispatch_reservation_would_be_attempted
    ]
    assert len(would_attempt) == 3
    # The three that would reserve are exactly the eligible dips.
    assert [r.candidate_id for r in would_attempt] == [
        "cand-tier1",
        "cand-tier2",
        "cand-tier3",
    ]
    for r in would_attempt:
        assert r.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
        assert r.suppressed_before_dispatch_reservation is False


def test_exactly_six_records_suppressed_before_reservation() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    suppressed = [
        r for r in batch.records
        if r.suppressed_before_dispatch_reservation
    ]
    assert len(suppressed) == 6
    for r in suppressed:
        assert r.dispatch_reservation_would_be_attempted is False
        assert r.gate_decision in (
            GATE_DECISION_SKIP_BEFORE_DISPATCH,
            GATE_DECISION_INVALID_INPUT,
        )


def test_zero_failures_vetoes_or_refusals_in_any_record() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    for r in batch.records:
        assert r.dispatch_failure_recorded is False
        assert r.transport_veto_used is False
        assert r.payload_refused_used is False
    assert batch.dispatch_failures_recorded == 0
    assert batch.transport_veto_count == 0
    assert batch.payload_refused_count == 0


# ---------------------------------------------------------------------------
# 3. The counts match the Stage 30.10.2 fake gate proof
# ---------------------------------------------------------------------------


def test_counts_match_stage_30_10_2_fake_gate_proof() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    gate_summary = run_stage30_10_2_fake_gate_proof()
    assert batch.candidates_seen == gate_summary.candidates_seen
    assert batch.candidates_passed == gate_summary.candidates_passed
    assert batch.candidates_skipped == gate_summary.candidates_skipped
    assert batch.invalid_inputs == gate_summary.invalid_inputs
    assert (
        batch.dispatch_attempts_reserved
        == gate_summary.dispatch_attempts_reserved
    )
    assert (
        batch.dispatch_attempts_suppressed_before_reservation
        == gate_summary.dispatch_attempts_suppressed_before_reservation
    )


# ---------------------------------------------------------------------------
# 4. Reasons preserved on every record
# ---------------------------------------------------------------------------


def test_every_record_preserves_eligibility_and_gate_reason() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    for r in batch.records:
        # Each record carries a non-empty eligibility + gate decision / reason
        # (the "why" is preserved for passed, skipped, and invalid alike).
        assert r.eligibility_decision != ""
        assert r.eligibility_reason != ""
        assert r.gate_decision != ""
        assert r.gate_reason != ""


def test_passed_records_carry_eligible_dip_reasons() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    for r in batch.records:
        if r.gate_decision == GATE_DECISION_PASS_TO_DISPATCH:
            assert r.eligibility_decision == "ELIGIBLE_DIP"
            assert r.eligibility_reason == "TIER_ALLOWED"
            assert r.gate_reason == "ELIGIBLE_DIP"
            assert r.send_allowed is True


def test_skipped_records_carry_not_dip_reason() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    skip_records = [
        r for r in batch.records
        if r.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    ]
    assert len(skip_records) == 5
    for r in skip_records:
        assert r.gate_reason == "NOT_DIP"
        assert r.send_allowed is False
        # The classifier's specific skip reason is preserved verbatim.
        assert r.eligibility_reason in (
            "TIER_UNKNOWN",
            "TIER_NOT_APPLICABLE",
            "MISSING_ATH",
            "MISSING_MIGRATION",
            "MISSING_DRAWDOWN",
        )


def test_invalid_record_carries_invalid_gate_reason() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    invalid_records = [
        r for r in batch.records
        if r.gate_decision == GATE_DECISION_INVALID_INPUT
    ]
    assert len(invalid_records) == 1
    rec = invalid_records[0]
    assert rec.gate_reason == "INVALID_GATE_INPUT"
    assert rec.eligibility_decision == "INVALID_INPUT"
    assert rec.send_allowed is False


# ---------------------------------------------------------------------------
# 5. proof_id + created_at + schema carried consistently
# ---------------------------------------------------------------------------


def test_proof_id_and_created_at_are_consistent() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    assert batch.proof_id == "stage30_10_3_fake_gate_artifact_proof"
    assert batch.created_at_utc == "2026-01-01T00:00:00Z"
    for r in batch.records:
        assert r.proof_id == batch.proof_id
        assert r.created_at_utc == batch.created_at_utc


def test_caller_can_inject_proof_id_and_clock() -> None:
    batch = run_stage30_10_3_fake_artifact_proof(
        proof_id="custom-proof", created_at_utc="2026-05-31T00:00:00Z"
    )
    assert batch.proof_id == "custom-proof"
    assert batch.created_at_utc == "2026-05-31T00:00:00Z"
    for r in batch.records:
        assert r.proof_id == "custom-proof"
        assert r.created_at_utc == "2026-05-31T00:00:00Z"


# ---------------------------------------------------------------------------
# 6. In-memory sink retains all records (no filesystem write)
# ---------------------------------------------------------------------------


def test_proof_into_sink_retains_all_records() -> None:
    batch, sink_result = run_stage30_10_3_fake_artifact_proof_into_sink()
    assert isinstance(sink_result, Stage30_10GateArtifactSinkResult)
    assert sink_result.records_written == 9
    assert sink_result.batch_written is True
    assert sink_result.artifact_schema_version == (
        STAGE30_10_3_ARTIFACT_SCHEMA_VERSION
    )
    assert sink_result.proof_id == batch.proof_id
    assert sink_result.created_at_utc == batch.created_at_utc


def test_in_memory_sink_unit_write() -> None:
    batch = run_stage30_10_3_fake_artifact_proof()
    sink = Stage30_10InMemoryGateArtifactSink()
    result = sink.write(batch)
    assert result.records_written == 9
    assert result.batch_written is True
    assert sink.batch_count == 1
    assert len(sink.records) == 9
    # A second write accumulates in memory only.
    sink.write(batch)
    assert sink.batch_count == 2
    assert len(sink.records) == 18


# ---------------------------------------------------------------------------
# 7. Custom scenario + empty scenario
# ---------------------------------------------------------------------------


def test_empty_scenario_yields_empty_batch() -> None:
    empty = Stage30_10PreDispatchGateScenario(
        name="empty",
        gate_inputs=(),
        created_at_utc="2026-02-02T00:00:00Z",
    )
    batch = run_stage30_10_3_fake_artifact_proof(empty)
    assert batch.candidates_seen == 0
    assert batch.records == ()
    assert batch.dispatch_attempts_reserved == 0
    assert batch.dispatch_attempts_suppressed_before_reservation == 0
    assert batch.dispatch_failures_recorded == 0
    assert batch.transport_veto_count == 0
    assert batch.payload_refused_count == 0


# ---------------------------------------------------------------------------
# 8. The proof is deterministic
# ---------------------------------------------------------------------------


def test_proof_is_deterministic() -> None:
    assert (
        run_stage30_10_3_fake_artifact_proof()
        == run_stage30_10_3_fake_artifact_proof()
    )


def test_proof_into_sink_is_deterministic() -> None:
    first_batch, first_sink = run_stage30_10_3_fake_artifact_proof_into_sink()
    second_batch, second_sink = run_stage30_10_3_fake_artifact_proof_into_sink()
    assert first_batch == second_batch
    assert first_sink == second_sink
