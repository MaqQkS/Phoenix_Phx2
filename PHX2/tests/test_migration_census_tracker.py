"""Deterministic acceptance tests for migration census reconciliation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from PHX2.free_tier_producer.migration_admission import (
    evaluate_migration_admission,
)
from PHX2.free_tier_producer.migration_census import (
    DISCOVERY_SOURCE_BOTH,
    DISCOVERY_SOURCE_LIVE_GRPC,
    DISCOVERY_SOURCE_RPC_RECONCILIATION,
    OUTCOME_EXPIRED,
    OUTCOME_PENDING_WITH_DEADLINE,
    OUTCOME_REACHED_1_20X,
    MigrationCensusStore,
)
from PHX2.free_tier_producer.migration_reconciliation import (
    plan_reconciliation_chunks,
)
from PHX2.free_tier_producer.phx1_structural_parity import (
    PARITY_DEGRADED_DATA,
    PHX1_COMMIT,
    PHX1_REPOSITORY,
    RESULT_HARD_BLOCK,
    evaluate_structural_filters,
    parity_matrix,
)
from PHX2.free_tier_producer.transport_watermark import (
    TransportWatermarkStore,
)
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    STAGE29_3_SLOT_FILTER_NAME,
    STAGE29_3_TRANSACTION_FILTER_NAME,
    build_pumpswap_subscribe_request,
)
from PHX2.tests.test_migration_admission import build_pool_creation_update


def _proof():
    decision = evaluate_migration_admission(build_pool_creation_update())
    assert decision is not None and decision.admitted and decision.proof
    return decision.proof


def _observe(
    store: MigrationCensusStore,
    proof,
    *,
    slot: int,
    effective: int,
    raw: int | None = None,
    virtual: int = 100,
):
    raw_value = effective - virtual if raw is None else raw
    return store.observe_canonical_reserve(
        mint=proof.candidate_mint,
        pool=proof.pool,
        slot=slot,
        observed_at_utc=f"2026-07-25T00:00:{slot % 60:02d}Z",
        raw_quote_reserves=raw_value,
        virtual_quote_reserves=virtual,
        effective_quote_reserves_value=effective,
        base_reserves=1000,
        base_supply=1_000_000,
        base_decimals=0,
        quote_decimals=0,
        source_evidence_digest=f"{slot:064x}",
    )


def test_subscription_carries_transaction_and_same_connection_slot_filters():
    request = build_pumpswap_subscribe_request()
    assert STAGE29_3_TRANSACTION_FILTER_NAME in request.transactions
    assert STAGE29_3_SLOT_FILTER_NAME in request.slots
    assert request.slots[
        STAGE29_3_SLOT_FILTER_NAME
    ].filter_by_commitment is True


def test_transport_watermark_advances_independently_and_restores(tmp_path):
    state = tmp_path / "state"
    store = TransportWatermarkStore(state_dir=state)
    assert store.load().checkpoint_files_found is False
    assert store.observe_confirmed_slot(
        101, observed_at_utc="2026-07-25T00:00:00Z"
    )
    assert store.observe_confirmed_slot(
        105, observed_at_utc="2026-07-25T00:00:01Z"
    )
    restored = TransportWatermarkStore(state_dir=state)
    restored.load()
    assert restored.snapshot()["first_confirmed_slot"] == 101
    assert restored.snapshot()["latest_confirmed_slot"] == 105
    assert restored.snapshot()["observed_updates"] == 2


def test_live_and_rpc_union_is_one_census_identity(tmp_path):
    proof = _proof()
    store = MigrationCensusStore(
        state_dir=tmp_path / "state", artifact_dir=tmp_path / "artifacts"
    )
    store.load()
    first = store.register_migration(
        proof, discovery_source=DISCOVERY_SOURCE_LIVE_GRPC
    )
    second = store.register_migration(
        proof,
        discovery_source=DISCOVERY_SOURCE_RPC_RECONCILIATION,
        reconciliation_range=(10, 20),
    )
    assert first["inserted"] is True
    assert second["inserted"] is False
    assert second["source_upgraded"] is True
    assert len(store.records()) == 1
    assert store.records()[0]["discovery_source"] == DISCOVERY_SOURCE_BOTH
    assert store.summary()["duplicate_migrations_suppressed"] == 1


def test_virtual_reserves_and_exact_decimal_threshold_without_market_provider(
    tmp_path,
):
    proof = _proof()
    store = MigrationCensusStore(state_dir=tmp_path)
    store.load()
    store.register_migration(
        proof, discovery_source=DISCOVERY_SOURCE_LIVE_GRPC
    )
    baseline_slot = proof.migration_slot + 1
    baseline = _observe(
        store, proof, slot=baseline_slot, raw=900, virtual=100, effective=1000
    )
    below = _observe(store, proof, slot=baseline_slot + 1, effective=1199)
    exact = _observe(store, proof, slot=baseline_slot + 2, effective=1200)
    tracker = store.get_tracker_by_mint(proof.candidate_mint)
    census = store.get_by_mint(proof.candidate_mint)
    assert baseline["baseline_created"] is True
    assert below["crossed"] is False
    assert exact["crossed"] is True
    assert tracker["outcome"] == OUTCOME_REACHED_1_20X
    assert Decimal(tracker["activation_target_market_cap"]) == Decimal(
        tracker["migration_baseline"]
    ) * Decimal("1.20")
    assert tracker["first_crossing_slot"] == baseline_slot + 2
    assert tracker["crossing_proof"]["market_cap_usd"] is None
    assert census["raw_quote_reserves"] == "900"
    assert census["virtual_quote_reserves"] == "100"
    assert census["effective_quote_reserves"] == "1000"


def test_bounded_end_is_pending_and_exact_deadline_expires(tmp_path):
    proof = _proof()
    store = MigrationCensusStore(
        state_dir=tmp_path, watch_expiry_seconds=3600
    )
    store.load()
    store.register_migration(
        proof,
        discovery_source=DISCOVERY_SOURCE_LIVE_GRPC,
        migration_block_time=1_700_000_000,
    )
    _observe(store, proof, slot=proof.migration_slot + 1, effective=1000)
    assert (
        store.get_tracker_by_mint(proof.candidate_mint)["outcome"]
        == OUTCOME_PENDING_WITH_DEADLINE
    )
    assert store.expire_due(now_utc="2023-11-14T23:13:19Z") == 0
    assert store.expire_due(now_utc="2023-11-14T23:13:20Z") == 1
    assert (
        store.get_tracker_by_mint(proof.candidate_mint)["outcome"]
        == OUTCOME_EXPIRED
    )


def test_census_and_tracker_restart_restore(tmp_path):
    proof = _proof()
    state = tmp_path / "state"
    store = MigrationCensusStore(state_dir=state)
    store.load()
    store.register_migration(
        proof, discovery_source=DISCOVERY_SOURCE_LIVE_GRPC
    )
    _observe(store, proof, slot=proof.migration_slot + 1, effective=1000)
    restored = MigrationCensusStore(state_dir=state)
    load = restored.load()
    assert not load.checkpoint_quarantined
    assert len(restored.records()) == 1
    assert (
        restored.get_tracker_by_mint(proof.candidate_mint)[
            "migration_baseline"
        ]
        is not None
    )


def test_trusted_routing_decimal_text_payload_is_accepted(tmp_path):
    proof = _proof()
    store = MigrationCensusStore(state_dir=tmp_path)
    store.load()
    store.register_migration(
        proof, discovery_source=DISCOVERY_SOURCE_LIVE_GRPC
    )
    result = store.observe_canonical_reserve(
        mint=proof.candidate_mint,
        pool=proof.pool,
        slot=proof.migration_slot + 1,
        observed_at_utc="2026-07-25T00:00:01Z",
        raw_quote_reserves="900",
        virtual_quote_reserves="100",
        effective_quote_reserves_value="1000",
        base_reserves="1000",
        base_supply="1000000",
        base_decimals=0,
        quote_decimals=0,
        source_evidence_digest="1" * 64,
    )
    assert result["accepted"] is True
    assert result["baseline_created"] is True
    tracker = store.get_tracker_by_mint(proof.candidate_mint)
    assert tracker["observations"] == 1
    assert tracker["baseline_reserves"]["effective_quote_reserves"] == "1000"

def test_exact_reserve_replay_heals_without_double_counting(tmp_path):
    proof = _proof()
    store = MigrationCensusStore(
        state_dir=tmp_path / "state",
        artifact_dir=tmp_path / "artifacts",
    )
    store.load()
    store.register_migration(
        proof, discovery_source=DISCOVERY_SOURCE_LIVE_GRPC
    )
    slot = proof.migration_slot + 1
    first = _observe(store, proof, slot=slot, effective=1000)
    duplicate = _observe(store, proof, slot=slot, effective=1000)
    tracker = store.get_tracker_by_mint(proof.candidate_mint)
    assert first["accepted"] is True
    assert duplicate == {
        "accepted": False,
        "reason": "DUPLICATE_RESERVE_OBSERVATION",
        "outcome": OUTCOME_PENDING_WITH_DEADLINE,
    }
    assert tracker["observations"] == 1
    restored = MigrationCensusStore(state_dir=tmp_path / "state")
    restored.load()
    assert (
        restored.get_tracker_by_mint(proof.candidate_mint)["observations"]
        == 1
    )


def test_authenticated_census_write_retries_transient_failure(
    tmp_path, monkeypatch
):
    from PHX2.free_tier_producer import checkpoint_envelope

    real_write = checkpoint_envelope.write_checkpoint_generation
    attempts = {"count": 0}

    def fail_once(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("transient local contention")
        return real_write(**kwargs)

    monkeypatch.setattr(
        checkpoint_envelope, "write_checkpoint_generation", fail_once
    )
    monkeypatch.setattr(
        checkpoint_envelope.time, "sleep", lambda _delay: None
    )
    store = MigrationCensusStore(state_dir=tmp_path)
    store.load()
    result = store.register_migration(
        _proof(), discovery_source=DISCOVERY_SOURCE_LIVE_GRPC
    )
    assert result["inserted"] is True
    assert attempts["count"] == 2

def test_large_range_is_split_into_bounded_resumable_chunks():
    assert plan_reconciliation_chunks(
        start_slot=100, end_slot=4999, chunk_slots=1800
    ) == ((100, 1899), (1900, 3699), (3700, 4999))


def test_parity_matrix_is_attributable_and_missing_hard_input_blocks():
    matrix = parity_matrix()
    assert matrix["authoritative_phx1_source"]["repository_path"] == PHX1_REPOSITORY
    assert matrix["authoritative_phx1_source"]["commit"] == PHX1_COMMIT
    assert all(row["phx1_repository_commit"] == PHX1_COMMIT for row in matrix["rows"])
    ghost = next(
        row for row in matrix["rows"] if row["phx1_filter_name"] == "holder_ghost_v2"
    )
    assert ghost["parity_status"] == PARITY_DEGRADED_DATA
    result = evaluate_structural_filters(
        migration_proof=_proof(),
        fee_snapshot=None,
        liquidity_usd="13000",
        inspection_evidence={
            "buy_usd": "5000",
            "sell_usd": "1000",
            "event_count": 4,
        },
        market_observation_age_seconds="1",
        ath_drawdown_consistent=True,
    )
    fee = next(
        row for row in result["results"] if row["filter_name"] == "fee_gate_no_data"
    )
    assert fee["result"] == RESULT_HARD_BLOCK
    assert fee["reason_token"] == "PHX1_FEE_GATE_NO_DATA"
    assert result["final_structural_gate"] == "HARD_BLOCK"


@pytest.mark.parametrize("shape", ["DIRECT", "CPI_NO_PUMPFUN"])
def test_direct_or_noncanonical_pool_never_has_an_admitted_proof(shape):
    decision = evaluate_migration_admission(
        build_pool_creation_update(shape=shape)
    )
    assert decision is not None
    assert decision.admitted is False
    assert decision.proof is None
