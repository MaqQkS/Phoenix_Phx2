"""Stage 30.11.4 offline end-to-end proof tests.

Pins the deterministic offline end-to-end proof that COMPOSES the committed
chain (Stage 30.11.2 default stream -> committed runtime seam -> committed Stage
30.9.3 dip gate -> committed Stage 30.11.3 private sink -> INJECTED recording
fake transport):

  * the baseline composed run PASSES: five candidates seen, two bridged, one
    gate pass, one sink attempt + accept, one fake transport attempt + accept --
    for the Tier 1 dip ONLY; every non-dip / bridge-skip / invalid candidate is
    suppressed cleanly BEFORE the sink and never reaches the transport;
  * the negative proofs FAIL closed: a rejecting transport records a sink failure
    (UNEXPECTED_E2E_COUNTS), an extra / wrong transport attempt is
    UNEXPECTED_TRANSPORT_ATTEMPT, unexpected counts are UNEXPECTED_E2E_COUNTS,
    and a blank timestamp is INVALID_PROOF_INPUT.

Fakes / offline only; no live call, no provider, no Discord, no env read, no
network, no real transport.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES,
    STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_4_EXPECTED_GATE_PASSES,
    STAGE30_11_4_EXPECTED_GATE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_SINK_ACCEPTS,
    STAGE30_11_4_EXPECTED_SINK_ATTEMPTS,
    STAGE30_11_4_EXPECTED_SINK_FAILURES,
    STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
    RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
)
from PHX2.stage30.stage30_11_3_fake_private_sink_proof import (
    Stage30_11RecordingFakePrivateTransport,
)
from PHX2.stage30.stage30_11_4_offline_e2e_proof import (
    decide_stage30_11_4_offline_e2e_proof,
    run_stage30_11_4_offline_e2e_proof,
)
from PHX2.stage30.stage30_11_4_offline_e2e_proof_models import (
    OFFLINE_E2E_PROOF_FAILED,
    OFFLINE_E2E_PROOF_PASSED,
    PROOF_REASON_INVALID_PROOF_INPUT,
    PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    PROOF_REASON_UNEXPECTED_E2E_COUNTS,
    PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    Stage30_11OfflineE2EProofResult,
)


_CREATED_AT: str = "2026-01-01T00:00:00Z"


def _baseline_decide_kwargs() -> dict:
    """The exact baseline counts the composed default run produces (a passing
    proof). The negative-count tests perturb exactly one field.
    """
    return dict(
        candidates_seen=5,
        bridge_successes=2,
        bridge_suppressed=3,
        gate_passes=1,
        gate_suppressed=1,
        sink_attempts=1,
        sink_accepts=1,
        sink_failures=0,
        transport_attempts=1,
        transport_accepts=1,
        runtime_stopped_by_candidate_cap=0,
        runtime_stopped_by_dispatch_cap=0,
        runtime_stopped_by_runtime_seconds=0,
        transport_candidate_ids=("cand-tier1",),
        transport_token_mints=("mint-tier1",),
        created_at_utc=_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# 1. Baseline composed run PASSES with the expected counts
# ---------------------------------------------------------------------------


def test_baseline_run_passes() -> None:
    result = run_stage30_11_4_offline_e2e_proof()
    assert isinstance(result, Stage30_11OfflineE2EProofResult)
    assert result.proof_decision == OFFLINE_E2E_PROOF_PASSED
    assert result.proof_reason == PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY


def test_baseline_summary_matches_expected_counts() -> None:
    summary = run_stage30_11_4_offline_e2e_proof().summary
    assert summary.candidates_seen == STAGE30_11_4_EXPECTED_CANDIDATES_SEEN
    assert summary.bridge_successes == STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES
    assert summary.bridge_suppressed == STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED
    assert summary.gate_passes == STAGE30_11_4_EXPECTED_GATE_PASSES
    assert summary.gate_suppressed == STAGE30_11_4_EXPECTED_GATE_SUPPRESSED
    assert summary.sink_attempts == STAGE30_11_4_EXPECTED_SINK_ATTEMPTS
    assert summary.sink_accepts == STAGE30_11_4_EXPECTED_SINK_ACCEPTS
    assert summary.sink_failures == STAGE30_11_4_EXPECTED_SINK_FAILURES
    assert summary.transport_attempts == (
        STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS
    )
    assert summary.transport_accepts == STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS
    # No cap / wall-clock bound is tripped in the baseline run.
    assert summary.runtime_stopped_by_candidate_cap == 0
    assert summary.runtime_stopped_by_dispatch_cap == 0
    assert summary.runtime_stopped_by_runtime_seconds == 0


def test_baseline_transport_reached_only_the_dip() -> None:
    result = run_stage30_11_4_offline_e2e_proof()
    assert result.transport_candidate_ids == (
        STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    )
    assert result.transport_token_mints == (
        STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,
    )


def test_baseline_runtime_outcomes_are_dip_nondip_bridgeskips() -> None:
    result = run_stage30_11_4_offline_e2e_proof()
    assert [o.runtime_decision for o in result.runtime_outcomes] == [
        RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
        RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
        RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
        RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
        RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    ]


def test_baseline_no_suppressed_candidate_reached_the_transport() -> None:
    result = run_stage30_11_4_offline_e2e_proof()
    dispatched = [
        o
        for o in result.runtime_outcomes
        if o.runtime_decision == RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS
    ]
    assert len(dispatched) == 1
    assert result.transport_candidate_ids == (dispatched[0].candidate_id,)
    suppressed = [
        o
        for o in result.runtime_outcomes
        if o.runtime_decision
        in (
            RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
            RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
        )
    ]
    assert len(suppressed) == 4
    for outcome in suppressed:
        assert outcome.candidate_id not in result.transport_candidate_ids


def test_baseline_run_is_deterministic() -> None:
    a = run_stage30_11_4_offline_e2e_proof()
    b = run_stage30_11_4_offline_e2e_proof()
    assert a.summary == b.summary
    assert a.proof_decision == b.proof_decision
    assert a.transport_candidate_ids == b.transport_candidate_ids


# ---------------------------------------------------------------------------
# 2. Negative proof: a rejecting transport records a sink failure -> FAILED
# ---------------------------------------------------------------------------


def test_rejecting_transport_fails_and_records_sink_failure() -> None:
    rejecting = Stage30_11RecordingFakePrivateTransport(
        created_at_utc=_CREATED_AT,
        reject_candidate_ids=(STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,),
    )
    result = run_stage30_11_4_offline_e2e_proof(transport=rejecting)
    assert result.proof_decision == OFFLINE_E2E_PROOF_FAILED
    assert result.proof_reason == PROOF_REASON_UNEXPECTED_E2E_COUNTS
    # The dip DID reach the transport (one attempt for the dip), but it was
    # rejected -- so the sink records a failure and nothing accepted.
    assert result.summary.transport_attempts == 1
    assert result.summary.transport_accepts == 0
    assert result.summary.sink_attempts == 1
    assert result.summary.sink_accepts == 0
    assert result.summary.sink_failures == 1
    assert result.transport_candidate_ids == (
        STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    )


# ---------------------------------------------------------------------------
# 3. Negative proof: a blank timestamp -> INVALID_PROOF_INPUT (no chain run)
# ---------------------------------------------------------------------------


def test_blank_timestamp_is_invalid_proof_input() -> None:
    result = run_stage30_11_4_offline_e2e_proof(created_at_utc="")
    assert result.proof_decision == OFFLINE_E2E_PROOF_FAILED
    assert result.proof_reason == PROOF_REASON_INVALID_PROOF_INPUT
    # Nothing was bridged / gated / dispatched; no transport was reached.
    assert result.runtime_outcomes == ()
    assert result.transport_candidate_ids == ()
    assert result.transport_token_mints == ()
    assert result.summary.candidates_seen == 0
    assert result.summary.transport_attempts == 0


# ---------------------------------------------------------------------------
# 4. Pure decision function: baseline + each closed-set failure reason
# ---------------------------------------------------------------------------


def test_decide_baseline_passes() -> None:
    assert decide_stage30_11_4_offline_e2e_proof(**_baseline_decide_kwargs()) == (
        OFFLINE_E2E_PROOF_PASSED,
        PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    )


def test_decide_extra_transport_attempt_for_nondip_fails() -> None:
    kwargs = _baseline_decide_kwargs()
    kwargs["transport_attempts"] = 2
    kwargs["transport_candidate_ids"] = ("cand-tier1", "cand-unknown")
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    )


def test_decide_transport_attempt_for_wrong_candidate_fails() -> None:
    kwargs = _baseline_decide_kwargs()
    # Exactly one attempt, but for a candidate id that is NOT the expected dip.
    kwargs["transport_candidate_ids"] = ("cand-unknown",)
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    )


def test_decide_transport_attempt_for_wrong_token_mint_fails() -> None:
    kwargs = _baseline_decide_kwargs()
    # The expected candidate id reached the transport, but with the WRONG token
    # mint -- the dip identity is pinned on the token-mint axis too, so this is
    # an UNEXPECTED_TRANSPORT_ATTEMPT, not merely a count mismatch.
    kwargs["transport_candidate_ids"] = ("cand-tier1",)
    kwargs["transport_token_mints"] = ("mint-wrong",)
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    )


def test_decide_unexpected_counts_fail() -> None:
    for field, bad in (
        ("bridge_successes", 3),
        ("gate_passes", 0),
        ("gate_suppressed", 2),
        ("sink_accepts", 0),
        ("sink_failures", 1),
        ("transport_accepts", 0),
        ("runtime_stopped_by_candidate_cap", 1),
        ("runtime_stopped_by_dispatch_cap", 1),
        ("runtime_stopped_by_runtime_seconds", 1),
    ):
        kwargs = _baseline_decide_kwargs()
        kwargs[field] = bad
        assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
            OFFLINE_E2E_PROOF_FAILED,
            PROOF_REASON_UNEXPECTED_E2E_COUNTS,
        ), f"perturbing {field}={bad} must fail with UNEXPECTED_E2E_COUNTS"


def test_decide_exact_candidate_count_enforced() -> None:
    # The pass decision pins ``candidates_seen`` to EXACTLY the baseline (5) --
    # never a mere minimum. Both too-few (4) and too-many (6) fail, and the exact
    # baseline (5) passes.
    for bad in (0, 3, 4, 6, 7):
        kwargs = _baseline_decide_kwargs()
        kwargs["candidates_seen"] = bad
        assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
            OFFLINE_E2E_PROOF_FAILED,
            PROOF_REASON_UNEXPECTED_E2E_COUNTS,
        ), f"candidates_seen={bad} must fail with UNEXPECTED_E2E_COUNTS"
    exact = _baseline_decide_kwargs()
    exact["candidates_seen"] = STAGE30_11_4_EXPECTED_CANDIDATES_SEEN
    assert exact["candidates_seen"] == 5
    assert decide_stage30_11_4_offline_e2e_proof(**exact) == (
        OFFLINE_E2E_PROOF_PASSED,
        PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    )


def test_decide_invalid_input_fails_closed() -> None:
    # Blank timestamp.
    kwargs = _baseline_decide_kwargs()
    kwargs["created_at_utc"] = ""
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_INVALID_PROOF_INPUT,
    )
    # Malformed count (negative).
    kwargs = _baseline_decide_kwargs()
    kwargs["sink_attempts"] = -1
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_INVALID_PROOF_INPUT,
    )
    # Malformed transport candidate-id sequence (non-str element).
    kwargs = _baseline_decide_kwargs()
    kwargs["transport_candidate_ids"] = ("cand-tier1", 5)
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_INVALID_PROOF_INPUT,
    )
    # Malformed transport token-mint sequence (non-str element).
    kwargs = _baseline_decide_kwargs()
    kwargs["transport_token_mints"] = ("mint-tier1", 5)
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_INVALID_PROOF_INPUT,
    )


def test_decide_invalid_input_takes_priority_over_transport_check() -> None:
    # A blank timestamp fails closed as INVALID_PROOF_INPUT even when the
    # transport counts would otherwise be an UNEXPECTED_TRANSPORT_ATTEMPT.
    kwargs = _baseline_decide_kwargs()
    kwargs["created_at_utc"] = ""
    kwargs["transport_attempts"] = 9
    kwargs["transport_candidate_ids"] = ("cand-unknown",)
    assert decide_stage30_11_4_offline_e2e_proof(**kwargs) == (
        OFFLINE_E2E_PROOF_FAILED,
        PROOF_REASON_INVALID_PROOF_INPUT,
    )


# ---------------------------------------------------------------------------
# 5. The composed run agrees with the pure decision over the same counts
# ---------------------------------------------------------------------------


def test_run_and_decide_agree_on_the_baseline() -> None:
    result = run_stage30_11_4_offline_e2e_proof()
    s = result.summary
    decision, reason = decide_stage30_11_4_offline_e2e_proof(
        candidates_seen=s.candidates_seen,
        bridge_successes=s.bridge_successes,
        bridge_suppressed=s.bridge_suppressed,
        gate_passes=s.gate_passes,
        gate_suppressed=s.gate_suppressed,
        sink_attempts=s.sink_attempts,
        sink_accepts=s.sink_accepts,
        sink_failures=s.sink_failures,
        transport_attempts=s.transport_attempts,
        transport_accepts=s.transport_accepts,
        runtime_stopped_by_candidate_cap=s.runtime_stopped_by_candidate_cap,
        runtime_stopped_by_dispatch_cap=s.runtime_stopped_by_dispatch_cap,
        runtime_stopped_by_runtime_seconds=s.runtime_stopped_by_runtime_seconds,
        transport_candidate_ids=result.transport_candidate_ids,
        transport_token_mints=result.transport_token_mints,
        created_at_utc=result.created_at_utc,
    )
    assert (decision, reason) == (result.proof_decision, result.proof_reason)
