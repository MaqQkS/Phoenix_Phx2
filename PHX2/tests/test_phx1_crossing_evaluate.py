"""Crossed census records receive complete attributable PHX1 results."""

from __future__ import annotations

import argparse
import json

from PHX2.free_tier_producer.migration_admission import MigrationProofStore
from PHX2.free_tier_producer.migration_census import (
    DISCOVERY_SOURCE_RPC_RECONCILIATION,
    MigrationCensusStore,
)
from PHX2.scripts.phx1_crossing_evaluate import run
from PHX2.tests.test_migration_census_tracker import _observe, _proof


def test_crossing_evaluator_persists_every_filter_and_summary(tmp_path):
    state = tmp_path / "state"
    artifacts = tmp_path / "artifacts"
    proof_path = artifacts / "migration_proofs.jsonl"
    proof = _proof()
    proof_store = MigrationProofStore(proof_path)
    assert proof_store.seal_and_store(proof)
    census = MigrationCensusStore(state_dir=state, artifact_dir=artifacts)
    census.load()
    census.register_migration(
        proof, discovery_source=DISCOVERY_SOURCE_RPC_RECONCILIATION
    )
    _observe(
        census,
        proof,
        slot=proof.migration_slot + 1,
        raw=900,
        virtual=100,
        effective=1000,
    )
    _observe(
        census,
        proof,
        slot=proof.migration_slot + 2,
        effective=1200,
    )

    assert run(
        argparse.Namespace(
            state_dir=str(state),
            artifact_dir=str(artifacts),
            proof_store=str(proof_path),
            watch_expiry_seconds=3600,
        )
    ) == 0

    result_rows = [
        json.loads(line)
        for line in (
            artifacts / "phx1_filter_results.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(result_rows) == 1
    by_name = {
        row["filter_name"]: row
        for row in result_rows[0]["results"]
    }
    assert by_name["migration_proof"]["result"] == "PASS"
    assert by_name["fee_gate_no_data"]["result"] == "HARD_BLOCK"
    assert (
        by_name["fee_gate_no_data"]["reason_token"]
        == "PHX1_FEE_GATE_NO_DATA"
    )
    assert by_name["holder_ghost_v2"]["result"] == "DATA_UNAVAILABLE"
    summary = json.loads(
        (artifacts / "phx1_filter_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary == {
        "crossing_candidates": 1,
        "evaluated_result_sets": 1,
        "final_verdicts": {"HARD_BLOCK": 1},
        "effective_phx1_policy_verdicts": {"HARD_BLOCK": 1},
        "phx1_structural_policy_modes": {"ENFORCE": 1},
        "kind": "PHX2_CENSUS_PHX1_FILTER_SUMMARY",
        "pending_crossing_evaluations": 0,
    }
