"""Stage 30.11.2 offline fake runtime gate proof tests.

Pins the deterministic five-candidate fake runtime gate proof:

  * the rolled-up baseline summary counts (seen 5 / bridged 2 / gate_passed 1 /
    dispatch attempted+accepted 1 / suppressed_by_bridge 3 / suppressed_by_gate
    1 / invalid 1) and that they match the manifest expected constants,
  * the per-candidate runtime decisions (one dispatched, one gate-suppressed,
    three bridge-suppressed),
  * that the injected recording sink is called ONLY for the single dip,
  * determinism (repeat runs are byte-identical), and
  * the cap / wall-clock scenarios stop the run deterministically
    (max_dispatches=1 after the first pass, max_candidates=2 after two
    candidates, max_runtime_seconds via an injected fake clock).

Fake / offline only; no live call, no provider, no Discord, no env read, no
real dispatch reservation, no wall-clock read.
"""

from __future__ import annotations

from decimal import Decimal

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE,
    STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    default_runtime_gate_candidate_stream,
    default_runtime_gate_config,
    make_sequence_clock,
    run_stage30_11_2_fake_runtime_gate_proof,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11RuntimeGateConfig,
)


# ---------------------------------------------------------------------------
# 1. Scenario stream shape
# ---------------------------------------------------------------------------


def test_default_stream_is_five_candidates() -> None:
    stream = default_runtime_gate_candidate_stream()
    assert len(stream) == 5
    ids = [c.candidate_id for c in stream]
    assert ids == [
        "cand-tier1",
        "cand-unknown",
        "cand-no-ath",
        "cand-no-migration",
        "",
    ]


def test_default_config_is_permissive() -> None:
    cfg = default_runtime_gate_config()
    assert cfg.max_runtime_seconds == Decimal("3600")
    assert cfg.max_candidates == 100
    assert cfg.max_dispatches == 100


# ---------------------------------------------------------------------------
# 2. Baseline summary counts
# ---------------------------------------------------------------------------


def test_baseline_summary_counts() -> None:
    outcomes, summary, _sink = run_stage30_11_2_fake_runtime_gate_proof()
    assert summary.candidates_seen == 5
    assert summary.bridged == 2
    assert summary.gate_passed == 1
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 1
    assert summary.suppressed_by_bridge == 3
    assert summary.suppressed_by_gate == 1
    assert summary.invalid_inputs == 1
    assert summary.stopped_by_candidate_cap == 0
    assert summary.stopped_by_dispatch_cap == 0
    assert summary.stopped_by_runtime_seconds == 0
    assert len(outcomes) == 5
    # The bridged / suppressed partition holds, and the gate split holds.
    assert summary.bridged + summary.suppressed_by_bridge == (
        summary.candidates_seen
    )
    assert summary.gate_passed + summary.suppressed_by_gate == summary.bridged


def test_baseline_summary_counts_match_manifest_expected() -> None:
    _outcomes, summary, _sink = run_stage30_11_2_fake_runtime_gate_proof()
    assert summary.candidates_seen == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_CANDIDATES_SEEN
    )
    assert summary.bridged == STAGE30_11_2_FAKE_PROOF_EXPECTED_BRIDGED
    assert summary.gate_passed == STAGE30_11_2_FAKE_PROOF_EXPECTED_GATE_PASSED
    assert summary.dispatch_attempted == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ATTEMPTED
    )
    assert summary.dispatch_accepted == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_DISPATCH_ACCEPTED
    )
    assert summary.suppressed_by_bridge == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_BRIDGE
    )
    assert summary.suppressed_by_gate == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_SUPPRESSED_BY_GATE
    )
    assert summary.invalid_inputs == (
        STAGE30_11_2_FAKE_PROOF_EXPECTED_INVALID_INPUTS
    )


# ---------------------------------------------------------------------------
# 3. Per-candidate decisions + sink only called for the dip
# ---------------------------------------------------------------------------


def test_per_candidate_runtime_decisions() -> None:
    outcomes, _summary, _sink = run_stage30_11_2_fake_runtime_gate_proof()
    assert [o.runtime_decision for o in outcomes] == [
        "DISPATCHED_AFTER_DIP_GATE_PASS",
        "SUPPRESSED_BY_DIP_GATE",
        "SUPPRESSED_BY_BRIDGE",
        "SUPPRESSED_BY_BRIDGE",
        "SUPPRESSED_BY_BRIDGE",
    ]
    # Only the first outcome attempted a dispatch.
    attempted = [o.dispatch_attempted for o in outcomes]
    assert attempted == [True, False, False, False, False]


def test_sink_called_only_for_the_dip() -> None:
    _outcomes, _summary, sink = run_stage30_11_2_fake_runtime_gate_proof()
    assert sink.attempted == 1
    assert sink.accepted == 1
    assert sink.candidate_ids == ["cand-tier1"]
    assert sink.token_mints == ["mint-tier1"]


def test_rejecting_sink_attempts_but_does_not_accept() -> None:
    _outcomes, summary, sink = run_stage30_11_2_fake_runtime_gate_proof(
        accept=False
    )
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 0
    assert sink.attempted == 1
    assert sink.accepted == 0


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


def test_proof_is_deterministic() -> None:
    outcomes_a, summary_a, _a = run_stage30_11_2_fake_runtime_gate_proof()
    outcomes_b, summary_b, _b = run_stage30_11_2_fake_runtime_gate_proof()
    assert outcomes_a == outcomes_b
    assert summary_a == summary_b


# ---------------------------------------------------------------------------
# 5. Cap scenarios
# ---------------------------------------------------------------------------


def _config(*, max_runtime_seconds=Decimal("3600"), max_candidates=100, max_dispatches=100):
    return Stage30_11RuntimeGateConfig(
        max_runtime_seconds=max_runtime_seconds,
        max_candidates=max_candidates,
        max_dispatches=max_dispatches,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_max_dispatches_one_stops_after_first_pass() -> None:
    outcomes, summary, sink = run_stage30_11_2_fake_runtime_gate_proof(
        config=_config(max_dispatches=1)
    )
    assert outcomes[0].runtime_decision == "DISPATCHED_AFTER_DIP_GATE_PASS"
    assert outcomes[-1].runtime_decision == "STOPPED_BY_DISPATCH_CAP"
    assert summary.stopped_by_dispatch_cap == 1
    assert summary.candidates_seen == 1
    assert summary.dispatch_attempted == 1
    assert sink.attempted == 1


def test_max_candidates_two_stops_after_two() -> None:
    outcomes, summary, _sink = run_stage30_11_2_fake_runtime_gate_proof(
        config=_config(max_candidates=2)
    )
    assert outcomes[-1].runtime_decision == "STOPPED_BY_CANDIDATE_CAP"
    assert summary.stopped_by_candidate_cap == 1
    assert summary.candidates_seen == 2


def test_max_runtime_seconds_stops_via_injected_clock() -> None:
    clock = make_sequence_clock(
        (Decimal(0), Decimal(0), Decimal(0), Decimal(100))
    )
    outcomes, summary, _sink = run_stage30_11_2_fake_runtime_gate_proof(
        config=_config(max_runtime_seconds=Decimal("60")),
        now_seconds=clock,
    )
    assert outcomes[-1].runtime_decision == "STOPPED_BY_RUNTIME_SECONDS"
    assert summary.stopped_by_runtime_seconds == 1
    assert summary.candidates_seen == 2
    # Exactly one stop axis is set across the whole summary.
    assert (
        summary.stopped_by_candidate_cap
        + summary.stopped_by_dispatch_cap
        + summary.stopped_by_runtime_seconds
        == 1
    )
