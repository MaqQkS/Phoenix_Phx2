"""Stage 30.11.6 offline fake candidate source / harvest proof tests.

Proves the composed offline end-to-end run: a deterministic five-event fake source
is harvested (three harvested projections; one failed assembly; one rejected
projection), and the harvested candidate source drives the committed Stage 30.11.5
bounded runner so EXACTLY one PASS dip reaches the injected recording fake
transport client -- for the Tier 1 dip (``stage30_11_6_cand_000002`` /
``mint-tier1``) ONLY -- while the non-dip is suppressed by the committed dip gate,
the bridge-suppressed by the committed bridge, and the failed-assembly /
rejected-projection events never become candidates. The old ungated dispatch path
is never invoked (the fake assembler's dispatch tripwire records zero calls), and
the bounds hold (max_dispatches <= 1, max_candidates <= 10).

Fake / offline only. No live call, no provider, no Discord, no env read, no real
transport.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_6_candidate_source_models import (
    STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_6_EXPECTED_EVENTS_SEEN,
    STAGE30_11_6_EXPECTED_HARVESTED,
    STAGE30_11_6_EXPECTED_RUNNER_BRIDGED,
    STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN,
    STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED,
    STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED,
    STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED,
    STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED,
    STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED,
    STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS,
    HARVEST_DECISION_HARVESTED,
    HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
    HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
)
from PHX2.stage30.stage30_11_6_fake_candidate_source_proof import (
    default_fake_harvest_source,
    run_stage30_11_6_fake_candidate_source_proof,
    run_stage30_11_6_fake_harvest,
)


# ---------------------------------------------------------------------------
# 1. Default source shape
# ---------------------------------------------------------------------------


def test_default_source_is_five_events() -> None:
    source = default_fake_harvest_source()
    assert len(source) == STAGE30_11_6_EXPECTED_EVENTS_SEEN == 5
    mints = [e.token_mint for e in source]
    assert mints == [
        "mint-unknown",
        "mint-no-ath",
        "mint-tier1",
        "mint-fail",
        "mint-bad",
    ]


# ---------------------------------------------------------------------------
# 2. Harvest pass baseline
# ---------------------------------------------------------------------------


def test_harvest_baseline() -> None:
    harvest_result, assembler = run_stage30_11_6_fake_harvest()
    s = harvest_result.summary
    assert s.events_seen == STAGE30_11_6_EXPECTED_EVENTS_SEEN
    assert s.harvested == STAGE30_11_6_EXPECTED_HARVESTED
    assert s.skipped_assembly_failed == (
        STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED
    )
    assert s.skipped_projection_rejected == (
        STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED
    )
    # Three harvested projections; the dip is the third (index 2).
    assert len(harvest_result.candidate_source) == 3
    ids = [p.candidate_id for p in harvest_result.candidate_source]
    assert ids[2] == STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID
    mints = [p.token_mint for p in harvest_result.candidate_source]
    assert mints == ["mint-unknown", "mint-no-ath", "mint-tier1"]
    # The five events drove the assembler exactly five times; NO dispatch.
    assert assembler.assemble_calls == 5
    assert assembler.dispatch_tripwire_calls == 0


def test_harvest_outcome_decisions() -> None:
    harvest_result, _ = run_stage30_11_6_fake_harvest()
    decisions = [o.harvest_decision for o in harvest_result.outcomes]
    assert decisions == [
        HARVEST_DECISION_HARVESTED,
        HARVEST_DECISION_HARVESTED,
        HARVEST_DECISION_HARVESTED,
        HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
        HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
    ]


# ---------------------------------------------------------------------------
# 3. End-to-end: harvested source -> committed Stage 30.11.5 runner
# ---------------------------------------------------------------------------


def test_end_to_end_runner_baseline() -> None:
    harvest_result, runner_result, client, assembler = (
        run_stage30_11_6_fake_candidate_source_proof()
    )
    rs = runner_result.summary
    # The runner sees ONLY the three harvested projections.
    assert rs.source_items_seen == STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN
    assert rs.candidates_seen == STAGE30_11_6_EXPECTED_RUNNER_CANDIDATES_SEEN
    assert rs.bridged == STAGE30_11_6_EXPECTED_RUNNER_BRIDGED
    assert rs.gate_passed == STAGE30_11_6_EXPECTED_RUNNER_GATE_PASSED
    assert rs.dispatch_attempted == (
        STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ATTEMPTED
    )
    assert rs.dispatch_accepted == (
        STAGE30_11_6_EXPECTED_RUNNER_DISPATCH_ACCEPTED
    )
    # Bounds held.
    assert rs.stopped_by_candidate_cap == 0
    assert rs.stopped_by_dispatch_cap == 0
    assert rs.stopped_by_runtime_seconds == 0


def test_transport_reaches_the_dip_only() -> None:
    _, _, client, _ = run_stage30_11_6_fake_candidate_source_proof()
    assert client.attempted == STAGE30_11_6_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert client.accepted == STAGE30_11_6_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert client.rejected == 0
    assert client.candidate_ids == [STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID]
    assert client.token_mints == [STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT]
    # The recorded body is a safe display string (no transport scheme).
    assert len(client.bodies) == 1
    assert "://" not in client.bodies[0]


def test_old_ungated_dispatch_is_not_called() -> None:
    # The injected fake assembler exposes a dispatch tripwire (the committed Stage
    # 28.6 transport method name); the harvest path drives ONLY `assemble`, so the
    # tripwire stays at zero -- proving the old ungated dispatch surface is never
    # reached. The ONLY transport in the whole proof is the committed Stage 30.11.5
    # dip-gated fake client, reached once for the dip.
    _, _, client, assembler = run_stage30_11_6_fake_candidate_source_proof()
    assert assembler.dispatch_tripwire_calls == 0
    assert assembler.assemble_calls == 5
    assert client.attempted == 1


# ---------------------------------------------------------------------------
# 4. Determinism
# ---------------------------------------------------------------------------


def test_proof_is_deterministic() -> None:
    h1, r1, c1, _ = run_stage30_11_6_fake_candidate_source_proof()
    h2, r2, c2, _ = run_stage30_11_6_fake_candidate_source_proof()
    assert h1.summary == h2.summary
    assert r1.summary == r2.summary
    assert c1.candidate_ids == c2.candidate_ids == [
        STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID
    ]
