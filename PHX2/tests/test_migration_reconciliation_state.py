"""Authenticated reconciliation progress and fail-closed chunk tests."""

from __future__ import annotations

from PHX2.free_tier_producer.migration_reconciliation import (
    CHUNK_COMPLETE,
    MIGRATION_RECONCILIATION_RECORD_KIND,
    MigrationReconciliationStore,
    reconciliation_range_identity,
    validate_reconciliation_state,
)


def _chunk(start: int, end: int) -> dict:
    return {
        "range_start": start,
        "range_end": end,
        "completion_status": CHUNK_COMPLETE,
        "unresolved_blocks": 0,
        "produced_blocks": end - start + 1,
        "completed_blocks": end - start + 1,
        "explicitly_unavailable_blocks": 0,
        "canonical_migrations_found": 0,
        "duplicate_migrations_suppressed": 0,
        "rpc_request_count": 1,
        "rpc_retry_count": 0,
        "rpc_rate_limit_count": 0,
        "rpc_timeout_count": 0,
        "rpc_error_count": 0,
        "reconciliation_watermark_before": start - 1,
        "reconciliation_watermark_after": end,
        "checkpoint_generation_before": 0,
        "checkpoint_generation_after": None,
    }


def test_interrupted_reconciliation_restores_last_completed_chunk(tmp_path):
    state = tmp_path / "state"
    store = MigrationReconciliationStore(
        state_dir=state, artifact_dir=tmp_path / "artifacts"
    )
    store.load()
    record = store.ensure_range(
        start_slot=100, end_slot=4999, commitment="confirmed"
    )
    identity = record["range_identity"]
    store.commit_chunk(range_identity=identity, chunk=_chunk(100, 1899))
    store.note_unresolved(
        range_identity=identity, reason="RECONCILIATION_INTERRUPTED"
    )

    restored = MigrationReconciliationStore(state_dir=state)
    load = restored.load()
    assert not load.checkpoint_quarantined
    current = restored.range_record(identity)
    assert current["reconciliation_watermark"] == 1899
    assert len(current["chunks"]) == 1
    assert current["completion_status"] == "UNRESOLVED"


def test_missing_produced_block_cannot_advance_reconciliation_watermark(
    tmp_path,
):
    store = MigrationReconciliationStore(state_dir=tmp_path)
    store.load()
    record = store.ensure_range(
        start_slot=200, end_slot=300, commitment="confirmed"
    )
    identity = record["range_identity"]
    store.note_unresolved(
        range_identity=identity, reason="RPC_BACKFILL_BLOCK_UNAVAILABLE"
    )
    current = store.range_record(identity)
    assert current["reconciliation_watermark"] == 199
    assert current["chunks"] == []
    assert current["completion_status"] == "UNRESOLVED"


def test_malformed_chunk_is_invalid_not_an_uncaught_exception():
    identity = reconciliation_range_identity(1, 2, "confirmed")
    valid, reason = validate_reconciliation_state(
        {
            "record_kind": MIGRATION_RECONCILIATION_RECORD_KIND,
            "ranges": [
                {
                    "range_identity": identity,
                    "range_start": 1,
                    "range_end": 2,
                    "reconciliation_watermark": 2,
                    "chunks": [
                        {
                            "range_start": None,
                            "range_end": 2,
                            "completion_status": CHUNK_COMPLETE,
                        }
                    ],
                }
            ],
        }
    )
    assert valid is False
    assert reason
