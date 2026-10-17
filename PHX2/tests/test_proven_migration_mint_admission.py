"""Offline exact-identity regressions for the recorded 2026-08-03 suffix drops.

Only the two public mint addresses are taken from the prior proof artifact.
Transactions, pool/vault addresses and signatures are locally reconstructed
fixtures; no historical transaction or successful live run is claimed here.
"""
from dataclasses import replace
import json
import socket
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import authoritative_supply, phx1_fee_gate
from PHX2.free_tier_producer import helius_source, migration_admission as admission
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.compat.build30_watchlist import (
    Watchlist, WATCH_PENDING_BASELINE, WATCH_DROPPED_NON_PUMP,
    validate_watch_checkpoint_record,
)
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe, SingleGrpcPumpSwapDiscovery, event_to_candidate,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveIndex, _token_balance_context,
)
from PHX2.free_tier_producer.source_continuity import SourceContinuityTracker
from PHX2.tests.test_migration_admission import build_pool_creation_update
from PHX2.tests.test_helius_developer_shadow_probe import _update_to_helius
from PHX2.tests.test_helius_shadow_source import _config

MINTS = (
    "2TQJeFeMD2YfAroNGPBpQxsZTxW1gGqPNPvYde65PUMP",
    "HhUUZpAUB5wfs6ovnxtbiXjFC4XkbAiqyAZhkU9ydk7h",
)
NOW = "2026-08-03T17:13:55Z"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("network is forbidden in admission regressions")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def _decision(mint, **kwargs):
    return admission.evaluate_migration_admission(build_pool_creation_update(
        base_mint=mint,
        migrate_discriminator=admission.PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
        **kwargs), observed_at_utc=NOW)


def _event(decision):
    return helius_source.project_admitted_helius_migration(
        decision=decision, signature=decision.transaction_signature,
        slot=decision.slot, observed_at_utc=NOW, raw_event_hash="offline",
        source_identity=helius_source.HELIUS_SOURCE_IDENTITY)


def _candidate(mint):
    decision = _decision(mint)
    assert decision.admitted and decision.proof.mint_suffix_consistent is False
    candidate = event_to_candidate(_event(decision), migration_proof=decision.proof)
    assert candidate is not None
    return candidate, decision.proof


@pytest.mark.parametrize("mint", MINTS)
def test_structural_proof_flows_exactly_through_queue_watch_and_restart(tmp_path, mint):
    decision = _decision(mint)
    store = admission.MigrationProofStore(tmp_path / "migration_proofs.jsonl")
    assert store.seal_and_store(decision.proof)
    restored_proof = admission.MigrationProofStore(tmp_path / "migration_proofs.jsonl").get(mint)
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: pytest.fail("no live source"),
        dedupe=ProviderCandidateDedupe())
    owner._handle_event(_event(decision), migration_proof=restored_proof,
                        event_slot=decision.slot)
    candidates = owner.drain()
    assert [candidate["token_mint"] for candidate in candidates] == [mint]
    candidate = candidates[0]
    assert admission.candidate_migration_is_admitted(candidate)
    from PHX2.free_tier_producer.free_tier_session import guard_pump_suffix_candidates
    accepted, dropped = guard_pump_suffix_candidates(candidates)
    assert accepted == candidates and dropped == []
    watches = Watchlist(max_size=2)
    entry = watches.seed(candidate, seeded_at_utc=NOW)
    assert entry.status == WATCH_PENDING_BASELINE
    checkpoint = tmp_path / "watch_state.jsonl"
    watches.persist(checkpoint)
    restored = Watchlist.load(checkpoint, max_size=2).get(mint)
    assert restored is not None and restored.token_mint == mint
    assert restored.migration_proof == candidate["migration_proof"]
    assert admission.candidate_migration_is_admitted(restored.to_candidate())
    assert owner.drain() == []


@pytest.mark.parametrize("mint", MINTS)
@pytest.mark.parametrize("changes", [
    {"shape": "DIRECT"}, {"shape": "CPI_NO_PUMPFUN"},
    {"corrupt_pool": True}, {"corrupt_vault": True}, {"failed": True},
    {"quote_deposit_raw": 1}, {"short_accounts": True},
])
def test_invalid_structural_evidence_never_projects(mint, changes):
    decision = _decision(mint, **changes)
    assert not decision.admitted and decision.proof is None
    assert _event(decision) is None


@pytest.mark.parametrize("field,value", [
    ("token_mint", MINTS[0].lower()), ("pair_address", MINTS[1]),
    ("migration_signature", "wrong"), ("migration_slot", 1),
    ("migration_slot", True),
])
def test_candidate_proof_cannot_bind_a_different_identity(field, value):
    candidate, _proof = _candidate(MINTS[0])
    candidate[field] = value
    assert not admission.candidate_migration_is_admitted(candidate)


@pytest.mark.parametrize("changes", [
    {"canonical_pda_valid": False}, {"canonical_pda_valid": 1},
    {"pool": MINTS[1]}, {"base_vault": MINTS[1]},
    {"quote_deposit_sol": "NaN"}, {"quote_deposit_raw": 1},
    {"min_quote_deposit_sol": "90"}, {"migration_slot": True},
    {"proof_source": "UNTRUSTED"},
])
def test_even_resealed_invalid_proof_fails_candidate_admission(changes):
    candidate, proof = _candidate(MINTS[0])
    candidate["migration_proof"] = admission.seal_migration_proof(
        replace(proof, **changes)).to_dict()
    assert not admission.candidate_migration_is_admitted(candidate)


def test_claimed_bad_proof_never_falls_back_to_legacy_suffix():
    candidate = {"token_mint": "legacy-fixturepump"}
    assert admission.candidate_migration_is_admitted(candidate)
    candidate["migration_proof"] = {}
    assert not admission.candidate_migration_is_admitted(candidate)
    entry = Watchlist(max_size=1).seed(candidate, seeded_at_utc=NOW)
    assert entry.status == WATCH_DROPPED_NON_PUMP


def test_same_pool_proof_from_different_signature_cannot_attach():
    decision = _decision(MINTS[0])
    other = admission.seal_migration_proof(replace(decision.proof,
        migration_signature="2" + decision.proof.migration_signature[1:]))
    assert event_to_candidate(_event(decision), migration_proof=other) is None


def test_attached_proof_never_normalizes_an_invalid_slot_type():
    candidate, proof = _candidate(MINTS[0])
    candidate["migration_slot"] = float(proof.migration_slot)
    assert not admission.attach_candidate_migration_proof(candidate, proof)


@pytest.mark.parametrize("mint", MINTS)
def test_active_compose_engine_reaches_market_only_for_admitted_identity(mint):
    from PHX2.free_tier_producer.compat.build29_cap1_session import run_cap1_candidates
    candidate, _proof = _candidate(mint)
    class MarketReached(Exception):
        pass
    class Sidecar:
        def resolve(self, observed_mint, **kwargs):
            assert observed_mint == mint
            raise MarketReached()
    arguments = dict(sidecar=Sidecar(), ath_transport=None,
        ath_endpoint_secret=None, now_utc=None, now_seconds=None,
        now_iso_fn=lambda: NOW, sleep_fn=lambda _seconds: None,
        ledger=None, guard=None, authorization=None, created_at_utc=NOW)
    with pytest.raises(MarketReached):
        run_cap1_candidates([candidate], **arguments)
    candidate["migration_proof"] = {}
    result = run_cap1_candidates([candidate], **arguments)
    assert result["per_candidate"][0]["reason"] == "NOT_PUMP_SUFFIX"


@pytest.mark.parametrize("mint", MINTS)
def test_unproven_suffixless_candidate_remains_closed(mint):
    candidate, _proof = _candidate(mint)
    del candidate["migration_proof"]
    assert not admission.candidate_migration_is_admitted(candidate)
    owner = SingleGrpcPumpSwapDiscovery(source_factory=lambda: None,
                                        dedupe=ProviderCandidateDedupe())
    assert not owner._admit_candidate(candidate)
    assert owner.drain() == []


@pytest.mark.parametrize("mint", MINTS)
def test_market_storage_and_token_context_keep_exact_case(tmp_path, mint):
    candidate, proof = _candidate(mint)
    ath = CentralAthStateStore(tmp_path)
    assert ath.register_pool(mint=mint, pool_address=proof.pool,
                             quote_mint=proof.quote_mint, creation_timestamp=NOW)
    assert ath.observe_provider_current(mint=mint, price_usd="1", market_cap_usd="1000",
                                       observed_at=NOW, ingested_at=NOW)
    assert ath.snapshot(mint)["token_mint"] == mint
    assert CentralAthStateStore(tmp_path).snapshot(mint) is not None
    assert authoritative_supply._canonical_mint(mint) == mint
    reserves = PumpSwapReserveIndex()
    proof_store = admission.MigrationProofStore()
    assert proof_store.seal_and_store(proof)
    reserves.bind_proof_store(proof_store)
    assert reserves.register_pool(pool_address=proof.pool, base_mint=mint,
                                  quote_mint=proof.quote_mint, creation_timestamp=NOW)
    balances = [SimpleNamespace(mint=address,
                 ui_token_amount=SimpleNamespace(decimals=6))
                 for address in (mint, proof.quote_mint)]
    meta = SimpleNamespace(pre_token_balances=[], post_token_balances=balances)
    assert _token_balance_context(meta)[:2] == (mint, proof.quote_mint)
    assert phx1_fee_gate._token_context(meta) == (mint, proof.quote_mint)
    balances.append(SimpleNamespace(mint=MINTS[1] if mint == MINTS[0] else MINTS[0],
                     ui_token_amount=SimpleNamespace(decimals=6)))
    assert _token_balance_context(meta)[0] is None
    assert phx1_fee_gate._token_context(meta)[0] is None


def test_proof_persistence_failure_is_retryable_and_not_published(tmp_path, monkeypatch):
    proof = _decision(MINTS[0]).proof
    store = admission.MigrationProofStore(tmp_path / "proofs.jsonl")
    original = admission.os.fsync
    monkeypatch.setattr(admission.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("offline fault")))
    with pytest.raises(OSError):
        store.seal_and_store(proof)
    assert store.get(MINTS[0]) is None
    assert store.stats()["proof_persist_errors"] == 1
    monkeypatch.setattr(admission.os, "fsync", original)
    assert store.seal_and_store(proof)
    assert admission.MigrationProofStore(tmp_path / "proofs.jsonl").get(MINTS[0]) == proof


def test_partial_proof_append_does_not_poison_retry(tmp_path):
    path = tmp_path / "proofs.jsonl"
    first = _decision(MINTS[0]).proof
    second = _decision(MINTS[1]).proof
    store = admission.MigrationProofStore(path)
    assert store.seal_and_store(first)
    with path.open("ab") as handle:
        handle.write(b'{"proof_version":')
    resumed = admission.MigrationProofStore(path)
    assert resumed.seal_and_store(second)
    loaded = admission.MigrationProofStore(path)
    assert loaded.get(MINTS[0]) == first and loaded.get(MINTS[1]) == second


def test_helius_proof_commit_failure_does_not_ack_or_dedupe(tmp_path, monkeypatch):
    store = admission.MigrationProofStore(tmp_path / "proofs.jsonl")
    continuity = SourceContinuityTracker()
    source = helius_source.HeliusEnhancedWssSource(
        config=_config(), proof_store=store, continuity=continuity, now_fn=lambda: NOW)
    update = build_pool_creation_update(base_mint=MINTS[0])
    raw = json.dumps({"jsonrpc": "2.0", "method": "transactionNotification",
        "params": {"subscription": 77, "result": _update_to_helius(update)}})
    original = store.seal_and_store
    monkeypatch.setattr(store, "seal_and_store", lambda *_: (_ for _ in ()).throw(OSError("offline fault")))
    with pytest.raises(helius_source.HeliusSourceProtocolError, match="PROOF_COMMIT_FAILED"):
        source._decode_notification(raw, subscription_id=77)
    assert continuity.snapshot()["last_processed_slot"] is None
    assert not source._seen
    monkeypatch.setattr(store, "seal_and_store", original)
    event = source._decode_notification(raw, subscription_id=77)
    assert event is not None and event.base_mint == MINTS[0]
    assert source.last_event_migration_proof.candidate_mint == MINTS[0]
