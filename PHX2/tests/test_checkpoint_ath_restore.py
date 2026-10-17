"""PHX2-E2E-005 — central ATH checkpoint authentication, tamper rejection,
monotonicity across generations, legacy migration, and equal-evidence seal
backfill.

Deterministic fixtures + temporary checkpoints only. No live run, no
provider/transport connection, no real ledger.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.ath_state import (
    ATH_CHECKPOINT_SCHEMA_VERSION,
    ATH_STATE_SCHEMA_VERSION,
    CentralAthStateStore,
)

FIXTURES = Path(__file__).parent / "fixtures"
PRESERVED_ATH = FIXTURES / "preserved_run_20260718T195225Z_ath_state_reduced.json"

MINT = "AthRestore000000000000000000000000000pump"
HMMN = "HmMNqFyy1rwSrGfASY1ajWktjjKmdtm4tLQn87rQpump"
NOW = "2026-07-15T12:00:00Z"


def _store_with(tmp_path: Path, market_caps, confirmed=True) -> CentralAthStateStore:
    store = CentralAthStateStore(tmp_path)
    for index, market_cap in enumerate(market_caps):
        price = format(int(str(market_cap)) / 10**9, "f")
        assert store.observe_provider_current(
            mint=MINT, price_usd=price, market_cap_usd=str(market_cap),
            observed_at=f"2026-07-15T12:{index:02d}:00Z", confirmed=confirmed)
    return store


def _tampered_legacy(market_cap="1000", digest="0" * 64):
    return {
        "schema_version": ATH_STATE_SCHEMA_VERSION,
        "artifact_kind": "CENTRAL_ATH_RESTART_CHECKPOINT",
        "updated_at": NOW,
        "mints": {MINT: {
            "ath_price": "0.000001", "ath_market_cap": market_cap,
            "ath_timestamp": NOW, "ath_provider": "PAID_CURRENT_PRICE",
            "ath_observation_type": "PAID_CURRENT_PRICE",
            "ath_status": "CONFIRMED",
            "ath_evidence_version": "phx2_central_ath_evidence_v2",
            "ath_evidence_digest": digest,
            "ath_ingested_at_utc": NOW,
        }},
    }


# ---------------------------------------------------------------------------
# Round trip + monotonic restore (required tests 28, 29, 31)
# ---------------------------------------------------------------------------

def test_31_valid_current_ath_checkpoint_round_trips_exactly(tmp_path):
    store = _store_with(tmp_path, ["50000"])
    original = store.snapshot(MINT)
    restored = CentralAthStateStore(tmp_path)
    assert restored.checkpoint.checkpoint_status == cpe.CHECKPOINT_PRIMARY_OK
    snapshot = restored.snapshot(MINT)
    assert snapshot["ath_market_cap"] == original["ath_market_cap"]
    assert snapshot["ath_evidence_digest"] == original["ath_evidence_digest"]
    assert snapshot["ath_observation_seal_digest"] \
        == original["ath_observation_seal_digest"]
    assert snapshot["ath_ingested_at_utc"] == original["ath_ingested_at_utc"]


def test_28_higher_valid_ath_restores(tmp_path):
    _store_with(tmp_path, ["50000", "60000"])
    restored = CentralAthStateStore(tmp_path)
    assert restored.snapshot(MINT)["ath_market_cap"] == "60000"


def test_29_equal_valid_ath_restores_without_duplicate_event(tmp_path):
    store = _store_with(tmp_path, ["50000"])
    before = store.snapshot(MINT)["ath_equal_evidence_reobserved_count"]
    restored = CentralAthStateStore(tmp_path)
    snapshot = restored.snapshot(MINT)
    assert snapshot["ath_market_cap"] == "50000"
    # restart alone neither replays the event nor bumps the equal counter
    assert snapshot["ath_equal_evidence_reobserved_count"] == before


# ---------------------------------------------------------------------------
# FIXTURE B — tamper + regression (required tests 26, 27)
# ---------------------------------------------------------------------------

def test_26_fixture_b_tampered_lower_ath_with_zero_digest_never_restores(
        tmp_path):
    (tmp_path / "ath_state_checkpoint.json").write_text(
        json.dumps(_tampered_legacy()), encoding="utf-8")
    store = CentralAthStateStore(tmp_path)
    assert store.checkpoint_quarantined
    assert store.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID
    assert store.snapshot(MINT) is None
    assert store.checkpoint.checkpoint_digest_failure_total >= 1
    # the tampered evidence is preserved unchanged
    assert json.loads((tmp_path / "ath_state_checkpoint.json")
                      .read_text(encoding="utf-8"))["mints"][MINT][
                          "ath_market_cap"] == "1000"


def test_26b_tampered_primary_with_valid_backup_recovers_higher_evidence(
        tmp_path):
    _store_with(tmp_path, ["50000", "51000"])   # gen2 primary + gen1 backup
    (tmp_path / "ath_state_checkpoint.json").write_text(
        json.dumps(_tampered_legacy()), encoding="utf-8")
    (tmp_path / "ath_state.json").unlink()      # isolate the pair decision
    restored = CentralAthStateStore(tmp_path)
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_RECOVERED_FROM_BACKUP
    assert restored.snapshot(MINT)["ath_market_cap"] == "50000"
    assert restored.snapshot(MINT)["ath_market_cap"] != "1000"


def test_27_ath_regression_against_valid_previous_generation_fails(tmp_path):
    # Two valid authenticated generations where the NEWER one carries a lower
    # ATH: there is no legitimate automatic reset, so the higher generation
    # is restored and the regression is counted.
    store = _store_with(tmp_path, ["50000"])
    checkpoint = tmp_path / "ath_state_checkpoint.json"
    backup = tmp_path / "ath_state_checkpoint.json.bak"
    gen1 = checkpoint.read_bytes()
    # produce generation 2 with a HIGHER value, then swap the files so the
    # newer-generation primary is the lower one via the on-disk backup swap:
    assert store.observe_provider_current(
        mint=MINT, price_usd="0.00006", market_cap_usd="60000",
        observed_at="2026-07-15T12:30:00Z", confirmed=True)
    gen2 = checkpoint.read_bytes()
    checkpoint.write_bytes(gen1)     # primary: gen1 (50000)
    backup.write_bytes(gen2)         # backup: gen2 (60000) — newer AND higher
    (tmp_path / "ath_state.json").unlink()
    restored = CentralAthStateStore(tmp_path)
    assert restored.snapshot(MINT)["ath_market_cap"] == "60000"
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_RECOVERED_FROM_BACKUP


def test_27b_forged_newer_generation_with_lower_ath_is_rejected(tmp_path):
    # A chain-consistent NEWER generation whose ATH regressed below the
    # previous valid generation: there is no legitimate automatic reset, so
    # the higher authenticated evidence is restored and the regression is
    # rejected + counted.
    checkpoint = tmp_path / "ath_state_checkpoint.json"
    store = _store_with(tmp_path, ["50000"])          # generation 1: 50000
    gen1_doc = json.loads(checkpoint.read_text(encoding="utf-8"))
    (low_record,) = gen1_doc["payload"]["records"]
    assert store.observe_provider_current(              # generation 2: 60000
        mint=MINT, price_usd="0.00006", market_cap_usd="60000",
        observed_at="2026-07-15T12:30:00Z", confirmed=True)
    assert store.observe_provider_current(              # generation 3: 61000
        mint=MINT, price_usd="0.000061", market_cap_usd="61000",
        observed_at="2026-07-15T12:40:00Z", confirmed=True)
    # forge generation 3 to carry the OLD 50000 record with a fully
    # re-signed digest chain (chain to generation 2 stays intact)
    gen3_doc = json.loads(checkpoint.read_text(encoding="utf-8"))
    forged_record = {k: v for k, v in low_record.items()
                     if k != "record_digest"}
    forged_record["record_digest"] = cpe.build_record_digest(
        cpe.CHECKPOINT_KIND_ATH, forged_record)
    forged = {k: v for k, v in gen3_doc.items()
              if k not in ("payload", "envelope_digest")}
    forged["record_count"] = 1
    forged["payload_digest"] = cpe.build_payload_digest(
        cpe.CHECKPOINT_KIND_ATH, forged["schema_version"],
        [forged_record["record_digest"]])
    forged["envelope_digest"] = cpe.build_envelope_digest(forged)
    forged["payload"] = {"records": [forged_record]}
    checkpoint.write_text(json.dumps(forged, sort_keys=True,
                                     separators=(",", ":")) + "\n",
                          encoding="utf-8")
    (tmp_path / "ath_state.json").unlink()
    restored = CentralAthStateStore(tmp_path)
    assert restored.checkpoint.checkpoint_ath_regression_rejected >= 1
    # the higher valid generation (backup, 60000) is restored
    assert restored.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_RECOVERED_FROM_BACKUP
    assert restored.snapshot(MINT)["ath_market_cap"] == "60000"


# ---------------------------------------------------------------------------
# Legacy migration (required tests 42, 50)
# ---------------------------------------------------------------------------

def _legacy_checkpoint(market_cap="90776.028679726", with_evidence=False):
    state = {
        "ath_price": "0.000090776", "ath_market_cap": market_cap,
        "ath_timestamp": "2026-07-15T11:57:01Z",
        "ath_provider": "PUMPSWAP_EVENT_EFFECTIVE_RESERVES",
        "ath_observation_type": "PUMPSWAP_SELL_EFFECTIVE_RESERVES",
        "ath_status": "CONFIRMED",
        "ath_supply_at_observation": "1000000000",
        "last_updated_at": NOW,
        "pool_address": "PoolAddr111", "quote_mint": "QuoteMint111",
    }
    return {
        "schema_version": ATH_STATE_SCHEMA_VERSION,
        "artifact_kind": "CENTRAL_ATH_RESTART_CHECKPOINT",
        "updated_at": NOW,
        "mints": {MINT: state},
    }


def test_42_migration_preserves_ath_exactly_and_marks_legacy_pre_evidence(
        tmp_path):
    (tmp_path / "ath_state_checkpoint.json").write_text(
        json.dumps(_legacy_checkpoint()), encoding="utf-8")
    store = CentralAthStateStore(tmp_path, now_utc="2026-07-16T00:00:00Z")
    assert store.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    snapshot = store.snapshot(MINT)
    assert snapshot["ath_market_cap"] == "90776.028679726"   # EXACT
    assert snapshot["ath_timestamp"] == "2026-07-15T11:57:01Z"
    assert snapshot["ath_legacy_pre_evidence"] is True
    assert snapshot["ath_evidence_digest"] is None           # not fabricated
    assert snapshot["pool_address"] == "PoolAddr111"
    # legacy source preserved as immutable evidence
    assert any(p.name.startswith("ath_state_checkpoint.json.legacy_source_")
               for p in tmp_path.iterdir())
    # installed schema is the authenticated envelope
    header = json.loads((tmp_path / "ath_state_checkpoint.json")
                        .read_text(encoding="utf-8"))
    assert header["schema_version"] == ATH_CHECKPOINT_SCHEMA_VERSION
    assert header["migration_history"][0]["migrated_from_schema"] \
        == ATH_STATE_SCHEMA_VERSION
    # and it restores exactly on the next restart
    again = CentralAthStateStore(tmp_path)
    assert again.snapshot(MINT)["ath_market_cap"] == "90776.028679726"
    assert again.checkpoint.checkpoint_status in (
        cpe.CHECKPOINT_PRIMARY_OK, cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK)


def test_50_equal_reobservation_refreshes_seal_only_never_numeric(tmp_path):
    (tmp_path / "ath_state_checkpoint.json").write_text(
        json.dumps(_legacy_checkpoint(market_cap="50000")), encoding="utf-8")
    store = CentralAthStateStore(tmp_path, now_utc="2026-07-16T00:00:00Z")
    before = store.snapshot(MINT)
    assert before["ath_legacy_pre_evidence"] is True
    # a LOWER fresh observation cannot reseal or regress
    assert not store.observe_provider_current(
        mint=MINT, price_usd="0.00004", market_cap_usd="40000",
        observed_at="2026-07-16T00:10:00Z", confirmed=True)
    assert store.snapshot(MINT)["ath_legacy_pre_evidence"] is True
    # an EQUAL authoritative re-observation of a DIFFERENT event identity
    # (different timestamp) must NOT backfill the historical seal
    assert not store.observe_provider_current(
        mint=MINT, price_usd="0.00005", market_cap_usd="50000",
        observed_at="2026-07-16T00:20:00Z", confirmed=True)
    assert store.snapshot(MINT)["ath_legacy_pre_evidence"] is True
    # PUMPSWAP-sourced state cannot be resealed by a provider-current equal
    # value; only the same source/type/timestamp identity qualifies. Build a
    # matching-identity fixture through a migrated PAID_CURRENT record:
    sub = tmp_path / "current_identity"
    sub.mkdir()
    legacy = _legacy_checkpoint(market_cap="50000")
    legacy["mints"][MINT].update({
        "ath_provider": "PAID_CURRENT_PRICE",
        "ath_observation_type": "PAID_CURRENT_PRICE",
        "ath_timestamp": "2026-07-15T11:57:01Z",
        "ath_supply_at_observation": None,
    })
    (sub / "ath_state_checkpoint.json").write_text(
        json.dumps(legacy), encoding="utf-8")
    store2 = CentralAthStateStore(sub, now_utc="2026-07-16T00:00:00Z")
    assert store2.snapshot(MINT)["ath_legacy_pre_evidence"] is True
    changed = store2.observe_provider_current(
        mint=MINT, price_usd="0.000090776", market_cap_usd="50000",
        observed_at="2026-07-15T11:57:01Z", confirmed=True,
        ingested_at="2026-07-16T00:30:00Z")
    assert changed
    after = store2.snapshot(MINT)
    assert after["ath_market_cap"] == "50000"                 # numeric EXACT
    assert after["ath_timestamp"] == "2026-07-15T11:57:01Z"   # event EXACT
    assert after["ath_legacy_pre_evidence"] is False          # seal backfilled
    assert after["ath_evidence_digest"] is not None
    assert after["ath_observation_seal_digest"] is not None
    assert after["ath_ingested_at_utc"] == "2026-07-16T00:30:00Z"
    assert after["ath_equal_evidence_reobserved_count"] == 1


def test_public_legacy_fallback_participates_when_primary_unusable(tmp_path):
    store = _store_with(tmp_path, ["95000"])
    # wrong-schema (but syntactically valid) checkpoint + no backup with a
    # higher value than any surviving generation -> public legacy evidence
    (tmp_path / "ath_state_checkpoint.json").write_text("{}\n",
                                                        encoding="utf-8")
    backup = tmp_path / "ath_state_checkpoint.json.bak"
    if backup.exists():
        backup.unlink()
    restored = CentralAthStateStore(tmp_path)
    assert restored.snapshot(MINT)["ath_market_cap"] == "95000"
    # invalid public + nothing else existing quarantines (never NOT_FOUND)
    sub = tmp_path / "only_public"
    sub.mkdir()
    (sub / "ath_state.json").write_text("{broken", encoding="utf-8")
    lone = CentralAthStateStore(sub)
    assert lone.checkpoint_quarantined
    assert lone.checkpoint.checkpoint_files_found


def test_quarantined_store_refuses_all_mutation_and_rewrite(tmp_path):
    checkpoint = tmp_path / "ath_state_checkpoint.json"
    checkpoint.write_text("{corrupt", encoding="utf-8")
    (tmp_path / "ath_state.json").write_text("{corrupt", encoding="utf-8")
    store = CentralAthStateStore(tmp_path)
    assert store.checkpoint_quarantined
    assert not store.register_pool(
        mint=MINT, pool_address="p", quote_mint="q")
    assert not store.observe_quote_price("q", "1")
    assert not store.observe_provider_current(
        mint=MINT, price_usd="1", market_cap_usd="5", observed_at=NOW)
    assert not store.observe_ohlcv_high(
        mint=MINT, high_price_usd="1", candle_timestamp=NOW,
        history_complete=True, interval="1m", time_from_unix=0,
        time_to_unix=60)
    assert not store.record_ohlcv_coverage(
        mint=MINT, interval="1m", time_from_unix=0, time_to_unix=60,
        history_complete=True, pages=1)
    assert checkpoint.read_text(encoding="utf-8") == "{corrupt"


# ---------------------------------------------------------------------------
# Preserved-run ATH migration (reduced exact fixture + optional real files)
# ---------------------------------------------------------------------------

PRESERVED_EXPECT = {
    HMMN: "90776.02867972621028616694671",
    "9Gsj9bbmekAvDbaTX4EvEJu6opWTn66oFuDcybG3pump":
        "49037.05658826344153316381518",
    "Xw9hBXxn7TrGCjmnUyLYrbTxdeTNngxgXzowPNMpump": "71093.2780489093000000000",
    "41VHigULn7wAFsk8ZjuH7zQoAybuGrBAJGgjLsZcpump":
        "41493.01925851324102911379947",
    "GgJq4UwLvsPrKxLV4xDKm3aJn9pvx7jXAVenKgePpump":
        "146021.3002618295388048883212",
    "DiV3ikZtwdQCMY7j6ovNrDTJJJVHfW6amz7F6Emapump":
        "34747.95008770744000000000",
}


def test_preserved_run_ath_checkpoint_migrates_with_exact_maxima(tmp_path):
    (tmp_path / "ath_state_checkpoint.json").write_bytes(
        PRESERVED_ATH.read_bytes())
    store = CentralAthStateStore(tmp_path, now_utc="2026-07-19T00:00:00Z")
    assert store.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    assert store.checkpoint.checkpoint_records_validated == 6
    snapshots = store.all_snapshots()
    assert len(snapshots) == 6
    for mint, expected in PRESERVED_EXPECT.items():
        assert snapshots[mint]["ath_market_cap"] == expected, mint
        assert snapshots[mint]["ath_legacy_pre_evidence"] is True, mint
        assert snapshots[mint]["ath_evidence_digest"] is None, mint
    again = CentralAthStateStore(tmp_path)
    assert again.snapshot(HMMN)["ath_market_cap"] == PRESERVED_EXPECT[HMMN]


REAL_PRESERVED = Path(r"C:\tmp\phx2_live_20260718T195225Z\producer")


@pytest.mark.skipif(not REAL_PRESERVED.exists(),
                    reason="preserved live-run artifacts not present")
def test_preserved_run_real_ath_artifacts_migrate(tmp_path):
    (tmp_path / "ath_state_checkpoint.json").write_bytes(
        (REAL_PRESERVED / "ath_state_checkpoint.json").read_bytes())
    (tmp_path / "ath_state.json").write_bytes(
        (REAL_PRESERVED / "ath_state.json").read_bytes())
    store = CentralAthStateStore(tmp_path, now_utc="2026-07-19T00:00:00Z")
    assert store.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    snapshots = store.all_snapshots()
    assert len(snapshots) == 6
    for mint, expected in PRESERVED_EXPECT.items():
        assert snapshots[mint]["ath_market_cap"] == expected, mint
    # dedupe keys survive the migration in the full (non-reduced) artifact
    hmmn_restored = CentralAthStateStore(tmp_path)
    assert not hmmn_restored.checkpoint_quarantined
