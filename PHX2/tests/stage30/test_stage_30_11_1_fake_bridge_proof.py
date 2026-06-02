"""Stage 30.11.1 offline fake bridge proof tests.

Pins the deterministic five-candidate fake bridge proof:

  * the rolled-up summary counts (seen 5 / bridged 2 / skipped-missing-context
    2 / invalid 1) and that they match the manifest expected constants,
  * the per-candidate bridge decisions (two bridged, two skipped, one invalid),
  * determinism (repeat runs are byte-identical), and
  * the optional compatibility proof: each bridged input is gate-ready (the
    committed Stage 30.9.3 gate rules a PASS for the dip and a SKIP for the
    non-dip) WITHOUT reserving a dispatch or sending Discord.

Fake / offline only; no live call, no provider, no Discord, no env read, no
dispatch reservation.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS,
    STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT,
)
from PHX2.stage30.stage30_11_1_fake_bridge_proof import (
    default_bridge_scenario_stream,
    run_stage30_11_1_bridge_then_gate_compatibility_proof,
    run_stage30_11_1_fake_bridge_proof,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
)


# ---------------------------------------------------------------------------
# 1. Scenario stream shape
# ---------------------------------------------------------------------------


def test_default_stream_is_five_candidates() -> None:
    stream = default_bridge_scenario_stream()
    assert len(stream) == 5
    # Distinct candidate ids except the deliberately-blank invalid one.
    ids = [c.candidate_id for c in stream]
    assert ids == [
        "cand-tier1",
        "cand-unknown",
        "cand-no-ath",
        "cand-no-migration",
        "",
    ]


# ---------------------------------------------------------------------------
# 2. Summary counts
# ---------------------------------------------------------------------------


def test_summary_counts() -> None:
    results, summary = run_stage30_11_1_fake_bridge_proof()
    assert summary.candidates_seen == 5
    assert summary.bridged == 2
    assert summary.skipped_missing_context == 2
    assert summary.invalid_inputs == 1
    # The counts partition the candidate stream exactly.
    assert (
        summary.bridged
        + summary.skipped_missing_context
        + summary.invalid_inputs
        == summary.candidates_seen
    )
    assert len(results) == 5


def test_summary_counts_match_manifest_expected() -> None:
    _results, summary = run_stage30_11_1_fake_bridge_proof()
    assert summary.candidates_seen == (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert summary.bridged == STAGE30_11_1_FAKE_PROOF_EXPECTED_BRIDGED
    assert summary.skipped_missing_context == (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_SKIPPED_MISSING_CONTEXT
    )
    assert summary.invalid_inputs == (
        STAGE30_11_1_FAKE_PROOF_EXPECTED_INVALID_INPUTS
    )


# ---------------------------------------------------------------------------
# 3. Per-candidate decisions
# ---------------------------------------------------------------------------


def test_per_candidate_decisions() -> None:
    results, _summary = run_stage30_11_1_fake_bridge_proof()
    decisions = [r.bridge_decision for r in results]
    assert decisions == [
        BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
        BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
        BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
        BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
        BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    ]
    # Only the two bridged results carry a gate input.
    have_input = [r.live_gate_input is not None for r in results]
    assert have_input == [True, True, False, False, False]


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


def test_proof_is_deterministic() -> None:
    results_a, summary_a = run_stage30_11_1_fake_bridge_proof()
    results_b, summary_b = run_stage30_11_1_fake_bridge_proof()
    assert summary_a == summary_b
    assert results_a == results_b


# ---------------------------------------------------------------------------
# 5. Compatibility with the committed Stage 30.9.3 gate (no dispatch)
# ---------------------------------------------------------------------------


def test_compatibility_proof_gate_decisions() -> None:
    pairs, summary = run_stage30_11_1_bridge_then_gate_compatibility_proof()
    assert summary.candidates_seen == 5
    # Each bridged input is gate-compatible; skipped / invalid carry no gate.
    gate_decisions = [
        None if dec is None else dec.gate_decision for _res, dec in pairs
    ]
    assert gate_decisions == [
        "PASS_TO_DISPATCH",      # Tier 1 dip
        "SKIP_BEFORE_DISPATCH",  # Tier Unknown non-dip (decided at the gate)
        None,                    # missing ATH -> not bridged, no gate
        None,                    # missing migration -> not bridged, no gate
        None,                    # invalid -> not bridged, no gate
    ]


def test_compatibility_proof_never_records_dispatch_failure_or_veto() -> None:
    pairs, _summary = run_stage30_11_1_bridge_then_gate_compatibility_proof()
    for _res, dec in pairs:
        if dec is None:
            continue
        # The gate rules a verdict only; it reserves no real dispatch and uses
        # no transport veto / PAYLOAD_REFUSED for any candidate.
        assert dec.dispatch_failure_recorded is False
        assert dec.transport_veto_used is False
        assert dec.payload_refused_used is False


def test_only_the_dip_would_reserve_a_dispatch() -> None:
    pairs, _summary = run_stage30_11_1_bridge_then_gate_compatibility_proof()
    reservation_allowed = [
        None if dec is None else dec.dispatch_reservation_allowed
        for _res, dec in pairs
    ]
    # Exactly one candidate (the Tier 1 dip) would be allowed to reserve a
    # dispatch downstream; the bridge / proof themselves reserve nothing.
    assert reservation_allowed == [True, False, None, None, None]
