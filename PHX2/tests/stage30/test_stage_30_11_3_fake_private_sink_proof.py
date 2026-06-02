"""Stage 30.11.3 fake private sink proof tests.

Pins the deterministic offline private sink proof: the direct three-call sink
proof (valid accept / blank-id invalid / valid reject -> the rolled-up summary)
and the runtime seam integration proof (the committed Stage 30.11.2 seam over a
dip / non-dip / bridge-skip stream with the Stage 30.11.3 private sink injected
-> the recording fake transport is attempted ONLY for the dip). Fakes / offline
only; no live call, no provider, no Discord, no env read, no network.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED,
    STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
    RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
)
from PHX2.stage30.stage30_11_3_fake_private_sink_proof import (
    DIRECT_PROOF_ACCEPT_CANDIDATE_ID,
    DIRECT_PROOF_REJECT_CANDIDATE_ID,
    Stage30_11RecordingFakePrivateTransport,
    run_stage30_11_3_direct_sink_proof,
    run_stage30_11_3_runtime_integration_proof,
)
from PHX2.stage30.stage30_11_3_private_sink_models import (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
)


# ---------------------------------------------------------------------------
# 1. Direct three-call sink proof
# ---------------------------------------------------------------------------


def test_direct_proof_result_decisions_in_order() -> None:
    results, _summary, _transport = run_stage30_11_3_direct_sink_proof()
    assert [r.sink_decision for r in results] == [
        PRIVATE_SINK_DECISION_ACCEPTED,
        PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
        PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
    ]


def test_direct_proof_summary_matches_expected_counts() -> None:
    _results, summary, _transport = run_stage30_11_3_direct_sink_proof()
    assert summary.requests_seen == STAGE30_11_3_FAKE_PROOF_EXPECTED_REQUESTS_SEEN
    assert summary.accepted == STAGE30_11_3_FAKE_PROOF_EXPECTED_ACCEPTED
    assert summary.rejected_invalid == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_REJECTED_INVALID
    )
    assert summary.transport_failed == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_FAILED
    )
    assert summary.transport_attempted == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ATTEMPTED
    )
    assert summary.transport_accepted == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_TRANSPORT_ACCEPTED
    )


def test_direct_proof_transport_recorded_only_the_two_valid_inputs() -> None:
    _results, _summary, transport = run_stage30_11_3_direct_sink_proof()
    # The blank-id invalid input never reached the transport.
    assert transport.attempted == 2
    assert transport.accepted == 1
    assert transport.rejected == 1
    assert transport.candidate_ids == [
        DIRECT_PROOF_ACCEPT_CANDIDATE_ID,
        DIRECT_PROOF_REJECT_CANDIDATE_ID,
    ]
    assert len(transport.compact_bodies) == 2


def test_direct_proof_is_deterministic() -> None:
    _r1, s1, _t1 = run_stage30_11_3_direct_sink_proof()
    _r2, s2, _t2 = run_stage30_11_3_direct_sink_proof()
    assert s1 == s2


# ---------------------------------------------------------------------------
# 2. Runtime seam integration proof
# ---------------------------------------------------------------------------


def test_runtime_integration_outcomes_are_dip_nondip_bridgeskip() -> None:
    outcomes, _summary, _transport = run_stage30_11_3_runtime_integration_proof()
    assert [o.runtime_decision for o in outcomes] == [
        RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
        RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
        RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    ]


def test_runtime_integration_transport_attempted_only_for_dip() -> None:
    outcomes, summary, transport = run_stage30_11_3_runtime_integration_proof()
    assert transport.attempted == (
        STAGE30_11_3_FAKE_PROOF_EXPECTED_RUNTIME_TRANSPORT_ATTEMPTS
    )
    assert transport.attempted == 1
    assert transport.accepted == 1
    # The single transport attempt is the dispatched dip candidate.
    dispatched = [
        o
        for o in outcomes
        if o.runtime_decision == RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS
    ]
    assert len(dispatched) == 1
    assert transport.candidate_ids == [dispatched[0].candidate_id]
    # The seam saw the dispatch as attempted + accepted (wrapper conversion).
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 1


def test_runtime_integration_nondip_and_bridgeskip_never_reach_transport() -> (
    None
):
    outcomes, _summary, transport = run_stage30_11_3_runtime_integration_proof()
    suppressed = [
        o
        for o in outcomes
        if o.runtime_decision
        in (
            RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
            RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
        )
    ]
    assert len(suppressed) == 2
    for outcome in suppressed:
        assert outcome.candidate_id not in transport.candidate_ids


def test_runtime_integration_accepts_injected_rejecting_transport() -> None:
    # An injected transport configured to reject the dip yields a recorded
    # attempt that is NOT accepted -- still exactly one attempt, for the dip.
    outcomes, _summary, _t = run_stage30_11_3_runtime_integration_proof()
    dip_id = [
        o.candidate_id
        for o in outcomes
        if o.runtime_decision == RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS
    ][0]
    rejecting = Stage30_11RecordingFakePrivateTransport(
        reject_candidate_ids=(dip_id,)
    )
    _outcomes2, _summary2, transport2 = (
        run_stage30_11_3_runtime_integration_proof(transport=rejecting)
    )
    assert transport2.attempted == 1
    assert transport2.accepted == 0
    assert transport2.rejected == 1
