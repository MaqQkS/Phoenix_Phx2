"""Stage 30.11.7 offline fake enrichment proof + end-to-end runner tests.

Proves the deterministic Stage 30.11.7 fake enrichment scenario AND the full
end-to-end: the enriched ``candidate_source`` fed through the committed Stage
30.11.5 bounded runner drives EXACTLY one fake transport attempt -- for the Tier 1
dip ONLY -- with the Tier Unknown non-dip suppressed by the committed dip gate and
the four fail-closed bases never enriching (so none reaches the transport), and the
old ungated dispatch path never invoked.

The committed Stage 30.11.5 runner is composed HERE (in this TEST), NOT by a Stage
30.11.7 production module -- a test file is not boundary-scanned, so this keeps the
Stage 30.11.7 production slice a clean leaf that imports no Stage 30.11.5 / Stage
30.11.6 module (the committed Stage 30.11.5 / Stage 30.11.6 leaf boundary tests stay
green).

Pure / offline. No live call, no provider, no Discord, no env read, no wall clock
(every clock is injected).
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    run_stage30_11_5_fake_live_wiring_proof,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
    ENRICH_DIMENSION_ATH,
    ENRICH_DIMENSION_MARKET_CONTEXT,
    ENRICH_DIMENSION_MIGRATION,
    ENRICH_DIMENSION_TIER,
    STAGE30_11_7_EXPECTED_BASES_SEEN,
    STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_7_EXPECTED_ENRICHED,
    STAGE30_11_7_EXPECTED_REJECTED_ATH,
    STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT,
    STAGE30_11_7_EXPECTED_REJECTED_MIGRATION,
    STAGE30_11_7_EXPECTED_REJECTED_TIER,
    STAGE30_11_7_EXPECTED_RUNNER_BRIDGED,
    STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN,
    STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED,
    STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS,
)
from PHX2.stage30.stage30_11_7_fake_enrichment_proof import (
    default_fake_enrichment_source,
    run_stage30_11_7_fake_enrichment,
)


# ---------------------------------------------------------------------------
# 1. The deterministic enrichment scenario
# ---------------------------------------------------------------------------


def test_enrichment_summary_matches_expected_baseline() -> None:
    run = run_stage30_11_7_fake_enrichment()
    s = run.summary
    assert s.bases_seen == STAGE30_11_7_EXPECTED_BASES_SEEN == 6
    assert s.enriched == STAGE30_11_7_EXPECTED_ENRICHED == 2
    assert s.rejected_market_context == (
        STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT
    )
    assert s.rejected_tier == STAGE30_11_7_EXPECTED_REJECTED_TIER
    assert s.rejected_migration == STAGE30_11_7_EXPECTED_REJECTED_MIGRATION
    assert s.rejected_ath == STAGE30_11_7_EXPECTED_REJECTED_ATH


def test_enriched_candidate_source_is_nondip_then_dip() -> None:
    run = run_stage30_11_7_fake_enrichment()
    ids = [c.candidate_id for c in run.candidate_source]
    # The non-dip precedes the dip so the committed runner SEES + gate-skips the
    # non-dip BEFORE the dip reaches the single-send dispatch cap.
    assert ids == ["stage30_11_7_cand_nondip", STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID]
    assert len(run.candidate_source) == 2


def test_per_base_enrichment_decisions() -> None:
    run = run_stage30_11_7_fake_enrichment()
    by_id = {o.candidate_id: o for o in run.outcomes}
    assert by_id["stage30_11_7_cand_dip"].enrichment_decision == (
        ENRICH_DECISION_ENRICHED
    )
    assert by_id["stage30_11_7_cand_nondip"].enrichment_decision == (
        ENRICH_DECISION_ENRICHED
    )
    # The four fail-closed bases never enrich (each names its dimension).
    assert by_id["stage30_11_7_cand_no_mc"].rejected_dimension == (
        ENRICH_DIMENSION_MARKET_CONTEXT
    )
    assert by_id["stage30_11_7_cand_no_tier"].rejected_dimension == (
        ENRICH_DIMENSION_TIER
    )
    assert by_id["stage30_11_7_cand_unk_mig"].rejected_dimension == (
        ENRICH_DIMENSION_MIGRATION
    )
    assert by_id["stage30_11_7_cand_stale_ath"].rejected_dimension == (
        ENRICH_DIMENSION_ATH
    )
    for cid in (
        "stage30_11_7_cand_no_mc",
        "stage30_11_7_cand_no_tier",
        "stage30_11_7_cand_unk_mig",
        "stage30_11_7_cand_stale_ath",
    ):
        assert by_id[cid].enrichment_decision == ENRICH_DECISION_REJECTED
        assert by_id[cid].enriched_candidate is None


def test_default_source_has_six_bases() -> None:
    assert len(default_fake_enrichment_source()) == 6


def test_enriched_candidates_pass_committed_stage_30_11_6_projection() -> None:
    # The enrichment does NOT bypass the committed Stage 30.11.6 projection: each
    # enriched candidate is ACCEPTED by it (PROJECTED_LIVE_CANDIDATE), so the
    # enrichment composes WITH the committed harvest / projection (it fills the dip
    # fields the harvest's flattener lacks), never around it.
    from PHX2.stage30.stage30_11_6_candidate_source_models import (
        PROJECTION_DECISION_PROJECTED,
    )
    from PHX2.stage30.stage30_11_6_stage29_projection_adapter import (
        project_harvested_candidate,
    )

    run = run_stage30_11_7_fake_enrichment()
    assert run.candidate_source  # non-empty
    for c in run.candidate_source:
        projected = project_harvested_candidate(
            c, created_at_utc="2026-01-01T00:00:00Z"
        )
        assert projected.projection_decision == PROJECTION_DECISION_PROJECTED
        assert projected.projection is not None


# ---------------------------------------------------------------------------
# 2. End-to-end: enriched candidate_source -> committed runner -> ONE transport
# ---------------------------------------------------------------------------


def _run_end_to_end():
    run = run_stage30_11_7_fake_enrichment()
    result, client = run_stage30_11_5_fake_live_wiring_proof(
        candidate_source=run.candidate_source
    )
    return run, result, client


def test_exactly_one_pass_dip_reaches_the_fake_transport() -> None:
    _, result, client = _run_end_to_end()
    sm = result.summary
    assert sm.candidates_seen == STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN
    assert sm.bridged == STAGE30_11_7_EXPECTED_RUNNER_BRIDGED
    assert sm.gate_passed == STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED
    # Exactly one fake transport attempt + accept -- for the dip ONLY.
    assert client.attempted == STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert client.accepted == STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert client.candidate_ids == [STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID]
    assert client.token_mints == [STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT]


def test_non_dip_is_bridged_but_gate_suppressed_no_transport() -> None:
    _, result, client = _run_end_to_end()
    sm = result.summary
    # The non-dip reaches the gate (bridged) but is suppressed there -- never the
    # transport. Exactly one candidate is suppressed by the gate (the non-dip).
    assert sm.suppressed_by_gate == 1
    assert "stage30_11_7_cand_nondip" not in client.candidate_ids


def test_no_dispatch_failure_or_transport_veto() -> None:
    _, result, client = _run_end_to_end()
    sm = result.summary
    # A non-dip skip is a clean no-send, never a dispatch failure / transport veto.
    assert sm.suppressed_by_bridge == 0
    assert client.rejected == 0


def test_fail_closed_bases_never_reach_the_transport() -> None:
    _, _, client = _run_end_to_end()
    for cid in (
        "stage30_11_7_cand_no_mc",
        "stage30_11_7_cand_no_tier",
        "stage30_11_7_cand_unk_mig",
        "stage30_11_7_cand_stale_ath",
    ):
        assert cid not in client.candidate_ids
