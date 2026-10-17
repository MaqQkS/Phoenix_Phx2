"""Offline trust-chain tests for gRPC-first PumpSwap price/MC routing."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_PROOF_SOURCE,
    MIGRATION_PROOF_VERSION,
    PUMPFUN_PROGRAM_ID,
    MigrationProofSnapshot,
    MigrationProofStore,
    seal_migration_proof,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveArtifact,
    PumpSwapReserveError,
    PumpSwapReserveIndex,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID,
    USDC_MINT,
)


NOW = 1_784_112_000.0
AT = datetime.fromtimestamp(NOW, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "canonical-pumpswap-pool"
BASE_VAULT = "canonical-base-vault"
QUOTE_VAULT = "canonical-quote-vault"


def _proof(*, mint=MINT, pool=POOL):
    return seal_migration_proof(MigrationProofSnapshot(
        proof_version=MIGRATION_PROOF_VERSION,
        proof_source=MIGRATION_PROOF_SOURCE,
        candidate_mint=mint,
        pool=pool,
        base_mint=mint,
        quote_mint=USDC_MINT,
        base_vault=BASE_VAULT,
        quote_vault=QUOTE_VAULT,
        migration_authority="migration-authority",
        migration_signature="migration-signature",
        migration_slot=100,
        outer_instruction_index=0,
        inner_instruction_index=1,
        flattened_instruction_index=1,
        pumpfun_program_id=PUMPFUN_PROGRAM_ID,
        pumpswap_program_id=PUMPSWAP_PROGRAM_ID,
        canonical_pda_valid=True,
        pool_creation_index_arg=0,
        vault_derivation_valid=True,
        vault_ownership_valid=True,
        quote_deposit_raw=85_000_000,
        quote_deposit_decimals=6,
        quote_deposit_sol="85",
        base_deposit_raw=1_000_000_000_000_000,
        base_deposit_decimals=6,
        min_quote_deposit_sol="50",
        mint_suffix_consistent=True,
        observed_at_utc=AT,
    ))


def _artifact(*, mint=MINT, pool=POOL, at=AT, raw=2_000_000,
              virtual=0, effective=None):
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw,
        virtual_quote_reserves=virtual,
        effective_quote_reserves=(raw + virtual if effective is None else effective),
        base_reserves=1_000_000,
        reserve_source="PUMPSWAP_BUY_EVENT",
        observation_timestamp=at,
        decoder_layout_version="OFFLINE_STRICT_FIXTURE",
        pool_address=pool,
        base_mint=mint,
        quote_mint=USDC_MINT,
        base_decimals=6,
        quote_decimals=6,
        event_side="BUY",
        event_timestamp=int(NOW),
        base_supply=1_000_000_000_000_000,
    )


def _index(*, proof=None, max_age=15.0):
    store = MigrationProofStore()
    assert store.seal_and_store(proof or _proof())
    index = PumpSwapReserveIndex(
        proof_store=store, now_fn=lambda: NOW,
        routing_max_age_seconds=max_age,
    )
    assert index.register_pool(
        pool_address=POOL, base_mint=MINT, quote_mint=USDC_MINT)
    return index


def _record(index, *, artifact=None, succeeded=True, proven=True, mint=MINT,
            slot=101, outer_instruction=2, inner_instruction=0,
            flattened_instruction=7, event=0):
    return index.record(
        base_mint=mint,
        artifact=artifact or _artifact(),
        transaction_signature="swap-signature",
        event_index=event,
        slot=slot,
        outer_instruction_index=outer_instruction,
        inner_instruction_index=inner_instruction,
        flattened_instruction_index=flattened_instruction,
        transaction_succeeded=succeeded,
        source_event_proven=proven,
        ingestion_timestamp=NOW,
    )


def test_exact_sealed_pool_vault_supply_and_reserves_route_current_price_and_mc():
    index = _index()
    emitted = []
    index.add_routing_observer(emitted.append)
    assert _record(index)
    assert len(emitted) == 1
    payload = emitted[0]
    assert payload["reserve_trusted_for_routing"] is True
    assert payload["pool_address"] == POOL
    assert payload["base_vault"] == BASE_VAULT
    assert payload["quote_vault"] == QUOTE_VAULT
    assert payload["outer_instruction_index"] == 2
    assert payload["inner_instruction_index"] == 0
    assert payload["flattened_instruction_index"] == 7
    assert payload["current_price"] == "2"
    assert payload["current_market_cap_usd"] == "2000000000"
    assert len(payload["source_evidence_digest"]) == 64
    assert len(payload["observation_seal_digest"]) == 64


def test_comparison_only_unproven_and_failed_events_never_route():
    for succeeded, proven in ((False, True), (True, False), (False, False)):
        index = _index()
        emitted = []
        index.add_routing_observer(emitted.append)
        assert _record(index, succeeded=succeeded, proven=proven)
        assert emitted == []
        assert index.latest_routing_observation(MINT) is None


def test_wrong_pool_wrong_mint_and_pool_replacement_fail_closed():
    wrong_pool = _index()
    assert not _record(wrong_pool, artifact=_artifact(pool="replacement-pool"))
    assert wrong_pool.latest_routing_observation(MINT) is None

    wrong_mint = _index()
    assert not _record(
        wrong_mint, mint=MINT, artifact=_artifact(mint="wrong-mint-pump"))
    assert wrong_mint.latest_routing_observation(MINT) is None

    conflict = _index()
    assert not conflict.register_pool(
        pool_address="replacement-pool", base_mint=MINT, quote_mint=USDC_MINT)
    assert _record(conflict)
    assert conflict.latest_routing_observation(MINT) is None


def test_historical_confirmed_reserve_tracks_without_live_market_routing():
    old_at = datetime.fromtimestamp(
        NOW - 3600, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    store = MigrationProofStore()
    assert store.seal_and_store(_proof())
    index = PumpSwapReserveIndex(
        proof_store=store,
        now_fn=lambda: NOW,
        routing_max_age_seconds=15.0,
        canonical_observer_allow_historical=True,
    )
    assert index.register_pool(
        pool_address=POOL, base_mint=MINT, quote_mint=USDC_MINT
    )
    canonical = []
    routed = []
    index.add_canonical_reserve_observer(
        lambda payload: canonical.append(payload) or True
    )
    index.add_routing_observer(routed.append)
    assert _record(index, artifact=_artifact(at=old_at))
    assert len(canonical) == 1
    assert canonical[0]["slot"] == 101
    assert routed == []
    assert index.latest_routing_observation(MINT) is None

def test_stale_event_missing_identity_and_tampered_proof_never_route():
    stale_at = datetime.fromtimestamp(
        NOW - 16, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = _index()
    assert _record(stale, artifact=_artifact(at=stale_at))
    assert stale.latest_routing_observation(MINT) is None

    missing_identity = _index()
    assert _record(missing_identity, slot=None)
    assert missing_identity.latest_routing_observation(MINT) is None

    approximate_log_position = _index()
    assert _record(
        approximate_log_position, outer_instruction=None,
        inner_instruction=None, flattened_instruction=7)
    assert approximate_log_position.latest_routing_observation(MINT) is None

    store = MigrationProofStore()
    assert not store.seal_and_store(replace(_proof(), proof_digest="0" * 64))
    index = PumpSwapReserveIndex(proof_store=store, now_fn=lambda: NOW)
    assert index.register_pool(
        pool_address=POOL, base_mint=MINT, quote_mint=USDC_MINT)
    assert _record(index)
    assert index.latest_routing_observation(MINT) is None


def test_newer_reserve_wins_and_old_event_cannot_replace_it():
    index = _index()
    emitted = []
    index.add_routing_observer(emitted.append)
    assert _record(index, artifact=_artifact(raw=3_000_000), event=2)
    assert emitted[-1]["current_price"] == "3"
    older = datetime.fromtimestamp(
        NOW - 1, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _record(index, artifact=_artifact(at=older, raw=1_000_000), event=1)
    assert index.latest_routing_observation(MINT)["current_price"] == "3"

    # Event timestamps have second precision; exact transaction identity still
    # orders multiple valid observations inside that second.
    assert _record(index, artifact=_artifact(raw=4_000_000), slot=102, event=0)
    assert index.latest_routing_observation(MINT)["current_price"] == "4"
    assert _record(index, artifact=_artifact(raw=2_000_000), slot=101, event=9)
    assert index.latest_routing_observation(MINT)["current_price"] == "4"


def test_nonfinite_or_incoherent_reserves_cannot_form_a_routing_artifact():
    for raw, virtual, effective in (
        (float("nan"), 0, 1),
        (float("inf"), 0, 1),
        (2_000_000, 1, 2_000_000),
    ):
        with pytest.raises(PumpSwapReserveError):
            _artifact(raw=raw, virtual=virtual, effective=effective)
