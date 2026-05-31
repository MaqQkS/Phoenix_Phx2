"""Stage 30.10.3 gate artifact projector tests.

Proves the pure projector maps Stage 30.10.2 gate records onto Stage 30.10.3
artifact records / a batch with the correct, fail-closed audit semantics:

  * ``PASS_TO_DISPATCH`` -> would attempt dispatch reservation;
  * ``SKIP_BEFORE_DISPATCH`` -> suppressed before reservation;
  * ``INVALID_INPUT`` -> suppressed before reservation;
  * an unknown / unrecognized gate decision -> fails closed (suppressed,
    never attempted);
  * NO record is ever a dispatch failure / transport veto / PAYLOAD_REFUSED;
  * the batch counts are derived from the records (they always match); and
  * an empty batch is valid (all-zero).

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    GATE_REASON_ELIGIBLE_DIP,
    GATE_REASON_INVALID_GATE_INPUT,
    GATE_REASON_NOT_DIP,
    Stage30_10PreDispatchGateRecord,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    Stage30_10GateArtifactBatch,
    Stage30_10GateArtifactRecord,
)
from PHX2.stage30.stage30_10_3_gate_artifact_projector import (
    project_gate_record_to_artifact_record,
    project_gate_records_to_artifact_batch,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"
_PROOF_ID = "proof-test"


def _gate_record(**overrides) -> Stage30_10PreDispatchGateRecord:
    base = dict(
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_decision="ELIGIBLE_DIP",
        eligibility_reason="TIER_ALLOWED",
        send_allowed=True,
        gate_decision=GATE_DECISION_PASS_TO_DISPATCH,
        gate_reason=GATE_REASON_ELIGIBLE_DIP,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10PreDispatchGateRecord(**base)


def _project_one(gate_record) -> Stage30_10GateArtifactRecord:
    return project_gate_record_to_artifact_record(
        proof_id=_PROOF_ID,
        gate_record=gate_record,
        created_at_utc=_SAFE_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# 1. PASS_TO_DISPATCH -> would attempt dispatch reservation
# ---------------------------------------------------------------------------


def test_pass_to_dispatch_would_attempt_reservation() -> None:
    rec = _project_one(
        _gate_record(
            gate_decision=GATE_DECISION_PASS_TO_DISPATCH,
            gate_reason=GATE_REASON_ELIGIBLE_DIP,
            send_allowed=True,
        )
    )
    assert rec.dispatch_reservation_would_be_attempted is True
    assert rec.suppressed_before_dispatch_reservation is False
    assert rec.dispatch_failure_recorded is False
    assert rec.transport_veto_used is False
    assert rec.payload_refused_used is False
    # Identity + closed-set tokens echoed verbatim.
    assert rec.proof_id == _PROOF_ID
    assert rec.candidate_id == "cand-1"
    assert rec.token_mint == "mint-1"
    assert rec.eligibility_decision == "ELIGIBLE_DIP"
    assert rec.eligibility_reason == "TIER_ALLOWED"
    assert rec.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    assert rec.gate_reason == GATE_REASON_ELIGIBLE_DIP
    assert rec.send_allowed is True
    assert rec.created_at_utc == _SAFE_CREATED_AT


# ---------------------------------------------------------------------------
# 2. SKIP_BEFORE_DISPATCH -> suppressed before reservation
# ---------------------------------------------------------------------------


def test_skip_before_dispatch_suppressed_before_reservation() -> None:
    rec = _project_one(
        _gate_record(
            eligibility_decision="SKIPPED_TIER_UNKNOWN",
            eligibility_reason="TIER_UNKNOWN",
            send_allowed=False,
            gate_decision=GATE_DECISION_SKIP_BEFORE_DISPATCH,
            gate_reason=GATE_REASON_NOT_DIP,
        )
    )
    assert rec.dispatch_reservation_would_be_attempted is False
    assert rec.suppressed_before_dispatch_reservation is True
    assert rec.dispatch_failure_recorded is False
    assert rec.transport_veto_used is False
    assert rec.payload_refused_used is False
    # The eligibility + gate reason are preserved on the artifact.
    assert rec.eligibility_decision == "SKIPPED_TIER_UNKNOWN"
    assert rec.eligibility_reason == "TIER_UNKNOWN"
    assert rec.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    assert rec.gate_reason == GATE_REASON_NOT_DIP


# ---------------------------------------------------------------------------
# 3. INVALID_INPUT -> suppressed before reservation
# ---------------------------------------------------------------------------


def test_invalid_input_suppressed_before_reservation() -> None:
    rec = _project_one(
        _gate_record(
            eligibility_decision="INVALID_INPUT",
            eligibility_reason="INVALID_CANDIDATE_ID",
            send_allowed=False,
            gate_decision=GATE_DECISION_INVALID_INPUT,
            gate_reason=GATE_REASON_INVALID_GATE_INPUT,
        )
    )
    assert rec.dispatch_reservation_would_be_attempted is False
    assert rec.suppressed_before_dispatch_reservation is True
    assert rec.dispatch_failure_recorded is False
    assert rec.transport_veto_used is False
    assert rec.payload_refused_used is False
    assert rec.gate_decision == GATE_DECISION_INVALID_INPUT
    assert rec.gate_reason == GATE_REASON_INVALID_GATE_INPUT


# ---------------------------------------------------------------------------
# 4. Skipped / invalid records are never dispatch failures / vetoes / refusals
# ---------------------------------------------------------------------------


def test_skipped_and_invalid_are_never_failures_vetoes_or_refusals() -> None:
    for gate_decision, gate_reason in (
        (GATE_DECISION_SKIP_BEFORE_DISPATCH, GATE_REASON_NOT_DIP),
        (GATE_DECISION_INVALID_INPUT, GATE_REASON_INVALID_GATE_INPUT),
    ):
        rec = _project_one(
            _gate_record(
                send_allowed=False,
                gate_decision=gate_decision,
                gate_reason=gate_reason,
            )
        )
        assert rec.dispatch_failure_recorded is False
        assert rec.transport_veto_used is False
        assert rec.payload_refused_used is False


# ---------------------------------------------------------------------------
# 5. Unknown / unrecognized gate decision fails closed
# ---------------------------------------------------------------------------


def test_unknown_gate_decision_fails_closed() -> None:
    rec = _project_one(
        _gate_record(
            send_allowed=False,
            gate_decision="SOME_UNRECOGNIZED_DECISION",
            gate_reason="SOME_UNRECOGNIZED_REASON",
        )
    )
    # Fail closed: never attempt dispatch reservation; suppressed before.
    assert rec.dispatch_reservation_would_be_attempted is False
    assert rec.suppressed_before_dispatch_reservation is True
    assert rec.dispatch_failure_recorded is False
    assert rec.transport_veto_used is False
    assert rec.payload_refused_used is False


def test_unknown_gate_decision_even_with_send_allowed_true_fails_closed() -> (
    None
):
    # A malformed gate record that (wrongly) carries send_allowed=True but a
    # non-PASS decision must still never attempt a dispatch reservation: the
    # would-attempt flag is gated strictly on the PASS_TO_DISPATCH decision.
    rec = _project_one(
        _gate_record(
            send_allowed=True,
            gate_decision="NOT_A_REAL_DECISION",
            gate_reason="NOT_A_REAL_REASON",
        )
    )
    assert rec.dispatch_reservation_would_be_attempted is False
    assert rec.suppressed_before_dispatch_reservation is True


# ---------------------------------------------------------------------------
# 6. would_attempt and suppressed are exact complements
# ---------------------------------------------------------------------------


def test_would_attempt_and_suppressed_are_complements() -> None:
    for gate_decision in (
        GATE_DECISION_PASS_TO_DISPATCH,
        GATE_DECISION_SKIP_BEFORE_DISPATCH,
        GATE_DECISION_INVALID_INPUT,
        "UNKNOWN_DECISION",
    ):
        rec = _project_one(_gate_record(gate_decision=gate_decision))
        assert (
            rec.dispatch_reservation_would_be_attempted
            != rec.suppressed_before_dispatch_reservation
        )


# ---------------------------------------------------------------------------
# 7. Batch counts match record counts
# ---------------------------------------------------------------------------


def _mixed_gate_records():
    return (
        _gate_record(
            candidate_id="c-pass",
            gate_decision=GATE_DECISION_PASS_TO_DISPATCH,
            gate_reason=GATE_REASON_ELIGIBLE_DIP,
            send_allowed=True,
        ),
        _gate_record(
            candidate_id="c-skip",
            send_allowed=False,
            gate_decision=GATE_DECISION_SKIP_BEFORE_DISPATCH,
            gate_reason=GATE_REASON_NOT_DIP,
        ),
        _gate_record(
            candidate_id="c-invalid",
            send_allowed=False,
            gate_decision=GATE_DECISION_INVALID_INPUT,
            gate_reason=GATE_REASON_INVALID_GATE_INPUT,
        ),
    )


def test_batch_counts_match_records() -> None:
    batch = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID,
        gate_records=_mixed_gate_records(),
        created_at_utc=_SAFE_CREATED_AT,
    )
    assert isinstance(batch, Stage30_10GateArtifactBatch)
    assert batch.proof_id == _PROOF_ID
    assert batch.created_at_utc == _SAFE_CREATED_AT
    assert len(batch.records) == 3
    assert batch.candidates_seen == 3
    assert batch.candidates_passed == 1
    assert batch.candidates_skipped == 1
    assert batch.invalid_inputs == 1
    assert batch.dispatch_attempts_reserved == 1
    assert batch.dispatch_attempts_suppressed_before_reservation == 2
    assert batch.dispatch_failures_recorded == 0
    assert batch.transport_veto_count == 0
    assert batch.payload_refused_count == 0


def test_batch_counts_are_derived_from_record_flags() -> None:
    batch = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID,
        gate_records=_mixed_gate_records(),
        created_at_utc=_SAFE_CREATED_AT,
    )
    # Recompute every batch count straight from the per-record flags.
    reserved = sum(
        1 for r in batch.records
        if r.dispatch_reservation_would_be_attempted
    )
    suppressed = sum(
        1 for r in batch.records
        if r.suppressed_before_dispatch_reservation
    )
    failures = sum(1 for r in batch.records if r.dispatch_failure_recorded)
    veto = sum(1 for r in batch.records if r.transport_veto_used)
    refused = sum(1 for r in batch.records if r.payload_refused_used)
    assert batch.dispatch_attempts_reserved == reserved
    assert batch.dispatch_attempts_suppressed_before_reservation == suppressed
    assert batch.dispatch_failures_recorded == failures
    assert batch.transport_veto_count == veto
    assert batch.payload_refused_count == refused


def test_batch_partitions_candidates_seen() -> None:
    batch = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID,
        gate_records=_mixed_gate_records(),
        created_at_utc=_SAFE_CREATED_AT,
    )
    assert (
        batch.candidates_passed
        + batch.candidates_skipped
        + batch.invalid_inputs
        == batch.candidates_seen
    )
    assert (
        batch.dispatch_attempts_reserved
        + batch.dispatch_attempts_suppressed_before_reservation
        == batch.candidates_seen
    )


def test_unknown_decision_buckets_into_invalid_inputs() -> None:
    batch = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID,
        gate_records=(
            _gate_record(gate_decision="WEIRD_UNKNOWN_DECISION"),
        ),
        created_at_utc=_SAFE_CREATED_AT,
    )
    assert batch.candidates_seen == 1
    assert batch.candidates_passed == 0
    assert batch.candidates_skipped == 0
    assert batch.invalid_inputs == 1
    assert batch.dispatch_attempts_reserved == 0
    assert batch.dispatch_attempts_suppressed_before_reservation == 1


# ---------------------------------------------------------------------------
# 8. Empty batch is valid (all-zero)
# ---------------------------------------------------------------------------


def test_empty_batch_is_all_zero() -> None:
    batch = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID,
        gate_records=(),
        created_at_utc=_SAFE_CREATED_AT,
    )
    assert batch.records == ()
    assert batch.candidates_seen == 0
    assert batch.candidates_passed == 0
    assert batch.candidates_skipped == 0
    assert batch.invalid_inputs == 0
    assert batch.dispatch_attempts_reserved == 0
    assert batch.dispatch_attempts_suppressed_before_reservation == 0
    assert batch.dispatch_failures_recorded == 0
    assert batch.transport_veto_count == 0
    assert batch.payload_refused_count == 0
    assert batch.proof_id == _PROOF_ID
    assert batch.created_at_utc == _SAFE_CREATED_AT


# ---------------------------------------------------------------------------
# 9. Projector is pure / deterministic
# ---------------------------------------------------------------------------


def test_projector_is_deterministic() -> None:
    records = _mixed_gate_records()
    first = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID, gate_records=records, created_at_utc=_SAFE_CREATED_AT
    )
    second = project_gate_records_to_artifact_batch(
        proof_id=_PROOF_ID, gate_records=records, created_at_utc=_SAFE_CREATED_AT
    )
    assert first == second
