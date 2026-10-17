"""Persist frozen PHX1 structural results for every 1.20x crossing.

The evaluator consumes only authenticated census state and sealed migration
proofs.  Evidence that was not captured by those sources remains explicitly
unavailable and follows the authoritative PHX1 missing-data behavior; this
tool never manufactures a passing fee, market, inspection, ATH, or Ghost row.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from PHX2.free_tier_producer.migration_admission import (  # noqa: E402
    MigrationProofStore,
)
from PHX2.free_tier_producer.migration_census import (  # noqa: E402
    OUTCOME_REACHED_1_20X,
    MigrationCensusStore,
)
from PHX2.free_tier_producer.phx1_structural_parity import (  # noqa: E402
    evaluate_structural_filters,
    write_parity_matrix,
)
from PHX2.free_tier_producer.phx1_structural_policy import (  # noqa: E402
    PHX1_STRUCTURAL_POLICY_CLI_VALUES,
)


def run(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    artifact_dir = Path(args.artifact_dir)
    proof_path = Path(args.proof_store)
    census = MigrationCensusStore(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        watch_expiry_seconds=int(args.watch_expiry_seconds),
    )
    load = census.load()
    if load.checkpoint_quarantined:
        print("REFUSED:AUTHENTICATED_CENSUS_QUARANTINED")
        return 2
    proofs = MigrationProofStore(proof_path)
    if proofs.stats()["proof_load_dropped"]:
        print("REFUSED:SEALED_PROOF_STORE_LOAD_DROPPED")
        return 2

    evaluated = 0
    for tracker in census.tracker_records():
        if tracker["outcome"] != OUTCOME_REACHED_1_20X:
            continue
        proof = proofs.get(str(tracker["mint"]))
        if proof is None:
            print("REFUSED:CROSSING_PROOF_MISSING")
            return 2
        result = evaluate_structural_filters(
            migration_proof=proof,
            fee_snapshot=None,
            liquidity_usd=None,
            inspection_evidence=None,
            market_observation_age_seconds=None,
            duplicate_application_count=1,
            ath_drawdown_consistent=None,
            holder_ghost_evidence=None,
        )
        census.record_filter_results(
            census_identity=str(tracker["census_identity"]),
            results=result["results"],
            final_verdict=str(result["final_structural_gate"]),
            evaluated_at_utc=str(
                tracker.get("first_crossing_timestamp")
                or tracker.get("baseline_timestamp")
                or "1970-01-01T00:00:00Z"
            ),
            phx1_structural_policy=getattr(args, "phx1_structural_policy", "enforce"),
        )
        evaluated += 1

    write_parity_matrix(artifact_dir / "phx1_filter_parity_matrix.json")
    summary = census.summary()
    pending = int(
        summary["crossing_candidates_pending_filter_evaluation"]
    )
    print(
        f"PHX1_CROSSING_EVALUATION evaluated={evaluated} "
        f"pending={pending} census={summary['census_records']}"
    )
    return 0 if pending == 0 else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--proof-store", required=True)
    parser.add_argument("--watch-expiry-seconds", type=int, default=3600)
    parser.add_argument(
        "--phx1-structural-policy",
        choices=list(PHX1_STRUCTURAL_POLICY_CLI_VALUES),
        default="enforce",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
