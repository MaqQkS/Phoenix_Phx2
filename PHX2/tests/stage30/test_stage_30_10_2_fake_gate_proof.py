"""Stage 30.10.2 offline fake pre-dispatch gate proof tests.

Proves the offline candidate-stream proof shows the correct placement +
behavior with fakes only:

  * the default nine-candidate scenario yields the expected
    seen / passed / skipped / invalid tally;
  * ``dispatch_attempts_reserved`` equals ONLY the eligible-dip pass count;
  * ``dispatch_attempts_suppressed_before_reservation`` equals the non-dip
    skips plus the invalids;
  * every non-dip / invalid is suppressed BEFORE reservation; and
  * no candidate's gate record carries a transport / PAYLOAD_REFUSED path.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

from PHX2.stage30.stage30_10_2_fake_gate_proof import (
    default_pre_dispatch_gate_scenario,
    run_stage30_10_2_fake_gate_proof,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate import (
    evaluate_pre_dispatch_tier_dip_gate,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_INVALID_INPUT,
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    STAGE30_10_2_GATE_DECISIONS,
    STAGE30_10_2_GATE_REASONS,
    Stage30_10PreDispatchGateProofSummary,
)


# ---------------------------------------------------------------------------
# 1. Default scenario shape
# ---------------------------------------------------------------------------


def test_default_scenario_has_nine_candidates() -> None:
    scenario = default_pre_dispatch_gate_scenario()
    assert len(scenario.gate_inputs) == 9
    assert scenario.name == "default_pre_dispatch_gate_stream"
    assert scenario.created_at_utc == "2026-01-01T00:00:00Z"


def test_default_scenario_per_candidate_gate_decisions() -> None:
    scenario = default_pre_dispatch_gate_scenario()
    decisions = [
        evaluate_pre_dispatch_tier_dip_gate(gi).gate_decision
        for gi in scenario.gate_inputs
    ]
    assert decisions == [
        GATE_DECISION_PASS_TO_DISPATCH,       # 1. Tier 1 dip
        GATE_DECISION_PASS_TO_DISPATCH,       # 2. Tier 2 dip
        GATE_DECISION_PASS_TO_DISPATCH,       # 3. Tier 3 dip
        GATE_DECISION_SKIP_BEFORE_DISPATCH,   # 4. Tier Unknown
        GATE_DECISION_SKIP_BEFORE_DISPATCH,   # 5. Tier Not Applicable
        GATE_DECISION_SKIP_BEFORE_DISPATCH,   # 6. missing ATH
        GATE_DECISION_SKIP_BEFORE_DISPATCH,   # 7. missing migration
        GATE_DECISION_SKIP_BEFORE_DISPATCH,   # 8. malformed drawdown
        GATE_DECISION_INVALID_INPUT,          # 9. invalid candidate_id
    ]


# ---------------------------------------------------------------------------
# 2. Proof summary tally
# ---------------------------------------------------------------------------


def test_proof_summary_counts() -> None:
    summary = run_stage30_10_2_fake_gate_proof()
    assert isinstance(summary, Stage30_10PreDispatchGateProofSummary)
    assert summary.candidates_seen == 9
    assert summary.candidates_passed == 3
    assert summary.candidates_skipped == 5
    assert summary.invalid_inputs == 1
    assert summary.created_at_utc == "2026-01-01T00:00:00Z"


def test_reserved_equals_eligible_dips_only() -> None:
    summary = run_stage30_10_2_fake_gate_proof()
    # Only the three eligible dips are reserved for dispatch.
    assert summary.dispatch_attempts_reserved == 3
    assert summary.dispatch_attempts_reserved == summary.candidates_passed


def test_suppressed_before_reservation_equals_non_dips_plus_invalids() -> None:
    summary = run_stage30_10_2_fake_gate_proof()
    assert summary.dispatch_attempts_suppressed_before_reservation == 6
    assert (
        summary.dispatch_attempts_suppressed_before_reservation
        == summary.candidates_skipped + summary.invalid_inputs
    )


def test_counts_partition_candidates_seen() -> None:
    summary = run_stage30_10_2_fake_gate_proof()
    # Every candidate is exactly one of passed / skipped / invalid.
    assert (
        summary.candidates_passed
        + summary.candidates_skipped
        + summary.invalid_inputs
        == summary.candidates_seen
    )
    # Reserved + suppressed-before-reservation also partitions the stream.
    assert (
        summary.dispatch_attempts_reserved
        + summary.dispatch_attempts_suppressed_before_reservation
        == summary.candidates_seen
    )


def test_proof_is_deterministic() -> None:
    assert run_stage30_10_2_fake_gate_proof() == (
        run_stage30_10_2_fake_gate_proof()
    )


# ---------------------------------------------------------------------------
# 3. No transport / PAYLOAD_REFUSED / Discord / live-provider path
# ---------------------------------------------------------------------------


def test_no_candidate_record_carries_a_transport_or_payload_refused_path() -> None:
    scenario = default_pre_dispatch_gate_scenario()
    for gi in scenario.gate_inputs:
        rec = evaluate_pre_dispatch_tier_dip_gate(gi)
        # Closed-set tokens only.
        assert rec.gate_decision in STAGE30_10_2_GATE_DECISIONS
        assert rec.gate_reason in STAGE30_10_2_GATE_REASONS
        # No transport veto / PAYLOAD_REFUSED leaks into the gate tokens.
        assert "PAYLOAD_REFUSED" not in rec.gate_reason
        assert "REFUSED" not in rec.gate_reason
        assert "PAYLOAD_REFUSED" not in rec.gate_decision


def test_only_eligible_dips_would_be_reserved() -> None:
    scenario = default_pre_dispatch_gate_scenario()
    reserved_ids = [
        gi.candidate_id
        for gi in scenario.gate_inputs
        if evaluate_pre_dispatch_tier_dip_gate(gi).gate_decision
        == GATE_DECISION_PASS_TO_DISPATCH
    ]
    assert reserved_ids == ["cand-tier1", "cand-tier2", "cand-tier3"]


# ---------------------------------------------------------------------------
# 4. Custom empty scenario degrades cleanly (defensive)
# ---------------------------------------------------------------------------


def test_empty_scenario_yields_zero_counts() -> None:
    from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
        Stage30_10PreDispatchGateScenario,
    )

    empty = Stage30_10PreDispatchGateScenario(
        name="empty",
        gate_inputs=(),
        created_at_utc="2026-02-02T00:00:00Z",
    )
    summary = run_stage30_10_2_fake_gate_proof(empty)
    assert summary.candidates_seen == 0
    assert summary.candidates_passed == 0
    assert summary.candidates_skipped == 0
    assert summary.invalid_inputs == 0
    assert summary.dispatch_attempts_reserved == 0
    assert summary.dispatch_attempts_suppressed_before_reservation == 0
    assert summary.created_at_utc == "2026-02-02T00:00:00Z"
