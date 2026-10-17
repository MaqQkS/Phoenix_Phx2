"""Post-range reconciliation tracks frozen proofs without census expansion."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PHX2.free_tier_producer import migration_reconciliation as mr
from PHX2.free_tier_producer.migration_admission import MigrationProofStore
from PHX2.free_tier_producer.migration_census import MigrationCensusStore
from PHX2.free_tier_producer.pumpswap_reserves import PumpSwapReserveIndex
from PHX2.free_tier_producer.rpc_gap_recovery import (
    GAP_RECOVERY_MODE_RPC_BACKFILL,
    RpcGapRecoveryConfig,
)


class _OneBlockRpc:
    def __init__(self) -> None:
        self.calls: List[Tuple[str, object]] = []

    def __call__(
        self, method: str, params: List[Any], _timeout: float
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        self.calls.append((method, params[0] if params else None))
        if method == "getBlocks":
            return 200, {"result": [10]}
        if method == "getBlock":
            return 200, {
                "result": {
                    "blockHeight": 10,
                    "blockTime": 1_700_000_010,
                    "blockhash": "H10",
                    "parentSlot": 9,
                    "previousBlockhash": "H9",
                    "transactions": [{"meta": {"err": None}}],
                }
            }
        raise AssertionError(f"unexpected RPC method {method}")


def test_existing_census_only_skips_admission_but_ingests_reserves(
    tmp_path, monkeypatch
):
    state = tmp_path / "state"
    artifacts = tmp_path / "artifacts"
    census = MigrationCensusStore(state_dir=state, artifact_dir=artifacts)
    census.load()
    reconciliation = mr.MigrationReconciliationStore(
        state_dir=state, artifact_dir=artifacts
    )
    reconciliation.load()
    proof_store = MigrationProofStore(artifacts / "migration_proofs.jsonl")
    reserve_index = PumpSwapReserveIndex(
        proof_store=proof_store,
        canonical_observer_allow_historical=True,
    )
    observed = {"reserve_updates": 0}

    monkeypatch.setattr(
        mr, "rpc_transaction_mentions_program", lambda *_args: True
    )
    monkeypatch.setattr(
        mr,
        "build_subscribe_update_from_rpc_transaction",
        lambda **_kwargs: object(),
    )

    def admission_must_not_run(*_args, **_kwargs):
        raise AssertionError("tracker-only history admitted a new migration")

    monkeypatch.setattr(mr, "evaluate_migration_admission", admission_must_not_run)

    def ingest(_update, *, reserve_index):
        assert reserve_index is not None
        observed["reserve_updates"] += 1
        return 1

    monkeypatch.setattr(mr, "ingest_reserve_events_from_update", ingest)
    runner = mr.ConfirmedMigrationReconciler(
        config=RpcGapRecoveryConfig(
            mode=GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment="confirmed",
            rpc_request_spacing_seconds=0.0,
        ),
        reconciliation_store=reconciliation,
        census_store=census,
        proof_store=proof_store,
        reserve_index=reserve_index,
        rpc_post_fn=_OneBlockRpc(),
        sleep_fn=lambda _seconds: None,
        admit_new_migrations=False,
    )

    result = runner.reconcile_range(start_slot=10, end_slot=10)

    assert result["completion_status"] == "COMPLETE"
    assert result["reconciliation_watermark"] == 10
    assert result["canonical_migrations_found"] == 0
    assert result["chunks"][0]["admit_new_migrations"] is False
    assert observed["reserve_updates"] == 1
    assert census.summary()["census_records"] == 0
