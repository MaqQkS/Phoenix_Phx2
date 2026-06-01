"""Stage 30.9.3 fake dip-filtered live gate integration proof tests.

Pins the two controlled scenarios (a dip present -> ``DISPATCHED_OK``; no dip
present -> ``NO_DIP_FOUND_BUT_SAFE``) plus the full nine-candidate
classification, using fakes / offline candidates + an in-memory recording sink
ONLY. Proves: a valid dip passes and calls the sink exactly once under the
controlled cap; non-dip and invalid candidates skip BEFORE dispatch and never
call the sink; the dispatch cap of 1 stops after the first passed candidate;
and no candidate is ever a dispatch failure / transport veto / ``PAYLOAD_REFUSED``
use. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from PHX2.stage30.stage30_9_3_fake_live_gate_integration_proof import (
    Stage30_9_3RecordingDispatchSink,
    default_live_gate_scenario_stream,
    no_dip_live_gate_scenario_stream,
    run_stage30_9_3_dip_present_controlled_proof,
    run_stage30_9_3_fake_live_gate_integration_proof,
    run_stage30_9_3_full_gate_classification_proof,
    run_stage30_9_3_no_dip_controlled_proof,
)


# ---------------------------------------------------------------------------
# Deterministic scenario streams
# ---------------------------------------------------------------------------


def test_default_stream_is_nine_candidates_three_dips_first() -> None:
    stream = default_live_gate_scenario_stream()
    assert len(stream) == 9
    # First three are eligible Tier 1/2/3 dips.
    assert [c.tier_token for c in stream[:3]] == ["Tier 1", "Tier 2", "Tier 3"]
    assert stream[-1].candidate_id == ""  # invalid candidate last


def test_no_dip_stream_is_six_candidates_no_dip() -> None:
    from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
        evaluate_dip_filtered_live_gate,
    )

    stream = no_dip_live_gate_scenario_stream()
    assert len(stream) == 6
    # No candidate in the no-dip stream is gate-eligible (none passes).
    assert all(
        evaluate_dip_filtered_live_gate(c).gate_decision != "PASS_TO_DISPATCH"
        for c in stream
    )


def test_streams_are_deterministic() -> None:
    assert default_live_gate_scenario_stream() == (
        default_live_gate_scenario_stream()
    )
    assert no_dip_live_gate_scenario_stream() == (
        no_dip_live_gate_scenario_stream()
    )


# ---------------------------------------------------------------------------
# Full classification (caps high enough to evaluate every candidate)
# ---------------------------------------------------------------------------


def test_full_classification_three_pass_five_skip_one_invalid() -> None:
    decisions, result, call_count = (
        run_stage30_9_3_full_gate_classification_proof()
    )
    assert result.candidates_seen == 9
    assert result.candidates_evaluated == 9
    assert result.candidates_passed_gate == 3
    assert result.candidates_skipped_before_dispatch == 5
    assert result.invalid_inputs == 1
    assert result.dispatch_attempts_reserved == 3
    assert result.would_send_private_discord_count == 3
    assert call_count == 3
    # Exactly the three passes are dispatched.
    passes = [
        d for d in decisions if d.gate_decision == "PASS_TO_DISPATCH"
    ]
    assert len(passes) == 3
    assert all(d.dispatch_reservation_allowed is True for d in passes)
    # Transport-safety negatives are always zero.
    assert result.dispatch_failures_recorded == 0
    assert result.transport_veto_count == 0
    assert result.payload_refused_count == 0


def test_full_classification_decisions_are_nine_with_safe_flags() -> None:
    decisions, _result, _cc = run_stage30_9_3_full_gate_classification_proof()
    assert len(decisions) == 9
    for d in decisions:
        assert d.dispatch_failure_recorded is False
        assert d.transport_veto_used is False
        assert d.payload_refused_used is False
        # Reservation is the exact complement of suppression.
        assert d.dispatch_reservation_allowed == (
            not d.suppressed_before_dispatch_reservation
        )


# ---------------------------------------------------------------------------
# Controlled DISPATCHED_OK (dip present, max_dispatches=1)
# ---------------------------------------------------------------------------


def test_dip_present_controlled_dispatches_exactly_once() -> None:
    decisions, result, call_count = (
        run_stage30_9_3_dip_present_controlled_proof()
    )
    assert call_count == 1
    assert result.dispatch_attempts_reserved == 1
    assert result.would_send_private_discord_count == 1
    assert result.candidates_passed_gate == 1
    # The run stops after the first eligible dip.
    assert result.candidates_seen == 1
    assert result.candidates_evaluated == 1
    assert len(decisions) == 1
    assert decisions[0].gate_decision == "PASS_TO_DISPATCH"
    assert result.dispatch_failures_recorded == 0
    assert result.transport_veto_count == 0
    assert result.payload_refused_count == 0


# ---------------------------------------------------------------------------
# Controlled NO_DIP_FOUND_BUT_SAFE (no dip present)
# ---------------------------------------------------------------------------


def test_no_dip_controlled_zero_dispatch_safe() -> None:
    decisions, result, call_count = run_stage30_9_3_no_dip_controlled_proof()
    assert call_count == 0
    assert result.dispatch_attempts_reserved == 0
    assert result.would_send_private_discord_count == 0
    assert result.candidates_passed_gate == 0
    assert result.candidates_skipped_before_dispatch == 5
    assert result.invalid_inputs == 1
    assert result.candidates_seen == 6
    assert result.dispatch_failures_recorded == 0
    assert result.transport_veto_count == 0
    assert result.payload_refused_count == 0
    # No PASS decision exists in a no-dip run.
    assert all(d.gate_decision != "PASS_TO_DISPATCH" for d in decisions)


# ---------------------------------------------------------------------------
# Recording sink only ever sees PASS decisions
# ---------------------------------------------------------------------------


def test_recording_sink_only_receives_pass_decisions() -> None:
    sink = Stage30_9_3RecordingDispatchSink()
    from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator import (
        run_dip_filtered_live_gate_integration,
    )

    _decisions, result = run_dip_filtered_live_gate_integration(
        live_inputs=default_live_gate_scenario_stream(),
        dispatch_sink=sink,
        max_candidates_evaluated=16,
        max_dispatches=9,
        max_private_discord_sends=9,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert sink.call_count == 3
    assert result.candidates_passed_gate == 3
    for d in sink.calls:
        assert d.gate_decision == "PASS_TO_DISPATCH"
        assert d.dispatch_reservation_allowed is True


def test_generic_runner_honors_custom_caps() -> None:
    decisions, result, call_count = (
        run_stage30_9_3_fake_live_gate_integration_proof(
            live_inputs=default_live_gate_scenario_stream(),
            max_candidates_evaluated=16,
            max_dispatches=2,
            max_private_discord_sends=2,
        )
    )
    # With max_dispatches=2 and three dips first, exactly two are dispatched
    # before the cap stops the run.
    assert call_count == 2
    assert result.dispatch_attempts_reserved == 2
    assert result.candidates_passed_gate == 2
    assert result.candidates_seen == 2
    assert len(decisions) == 2
