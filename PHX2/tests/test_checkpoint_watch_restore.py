"""PHX2-E2E-005 — watch checkpoint round trips, legacy activation migration,
per-candidate quarantine, and the preserved-run migration.

Covers the required current-schema restart preservation (delivery, capacity,
activation, market recovery), the deterministic/idempotent legacy migration
including the HmMN/Xw9 activation-loss shapes, ambiguous-evidence quarantine,
and the isolation guarantees for quarantined candidates.

Deterministic fixtures + temporary checkpoints only. No live run, no
provider/transport connection, no real ledger.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.compat.build30_watchlist import (
    ACTIVATION_KIND_LEGACY_MIGRATION,
    ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION,
    SEED_OUTCOME_CHECKPOINT_QUARANTINED,
    WATCH_ACTIVATED_WAITING,
    WATCH_ACTIVE_DIP,
    WATCH_DELIVERY_UNKNOWN,
    WATCH_PENDING_1_20X,
    WATCH_SENT_OK_COMMITTED,
    WATCH_LEGACY_SCHEMA_VERSION,
    WatchEntry,
    Watchlist,
    activation_proof_is_durable,
    activation_proof_is_eligible,
    verify_cross_checkpoint_consistency,
)

FIXTURES = Path(__file__).parent / "fixtures"
PRESERVED_WATCH = FIXTURES / "preserved_run_20260718T195225Z_watch_state.jsonl"

NOW = "2026-07-15T12:00:00Z"
DAY2 = "2026-07-16T12:00:00Z"
MINT = "WatchRestore00000000000000000000000000pump"
HMMN = "HmMNqFyy1rwSrGfASY1ajWktjjKmdtm4tLQn87rQpump"
XW9 = "Xw9hBXxn7TrGCjmnUyLYrbTxdeTNngxgXzowPNMpump"


def legacy_activated_record(mint: str = MINT, **overrides) -> dict:
    """Preserved-run shape: activated watch WITHOUT current proof fields."""

    record = {
        "token_mint": mint, "candidate_id": f"legacy_{mint[:6]}",
        "migration_time_utc": "2026-07-15T11:00:00Z", "source_ref": "proof",
        "seeded_at_utc": "2026-07-15T11:00:05Z", "status": "ACTIVE_DIP_WATCH",
        "recheck_count": 0, "last_reason": "ACTIVATION_THRESHOLD_REACHED",
        "last_observed_at_utc": None, "symbol_or_name": None,
        "market_state": None, "market_reason_code": None,
        "next_market_refresh_at_utc": None, "market_attempt_count": 0,
        "migration_market_cap_usd": "100",
        "migration_market_cap_source": "PAID_MARKET_PRIMARY_FALLBACK",
        "migration_market_cap_observed_at_utc": "2026-07-15T11:00:10Z",
        "migration_market_cap_price": "0.0000001",
        "migration_supply_at_observation": None,
        "migration_baseline_status": "CAPTURED",
        "activation_multiplier": "1.20",
        "activation_target_market_cap_usd": "120.00",
        "activated_at_utc": "2026-07-15T11:05:00Z",
        "activation_observation_source": "PAID_MARKET_PRIMARY",
        "activation_current_market_cap_usd": "130",
        "activation_observation_fresh": True,
        "activation_proven": True,
        "last_activation_progress_market_cap_usd": "100",
        "legacy_activation_unproven": False,
    }
    record.update(overrides)
    return record


def _write_legacy(tmp_path: Path, records) -> Path:
    state = tmp_path / "watch_state.jsonl"
    state.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8")
    return state


def _load(tmp_path: Path, state: Path, label: str = "h", **kwargs) -> Watchlist:
    return Watchlist.load(
        state, max_size=256,
        terminal_history_path=tmp_path / f"history_{label}.jsonl", **kwargs)


def _fresh_spot_tick(entry: WatchEntry, market_cap: str, at: str):
    return entry.observe_market(
        current_market_cap_usd=market_cap,
        current_price="0.0000001",
        current_supply=None,
        provider_timestamp_utc=at,
        observed_at_utc=at,
        observation_source="PAID_MARKET_PRIMARY",
        max_age_seconds=120.0,
    )


class _FlakyArchive:
    """Terminal archive whose first N appends fail (keeps terminal entries in
    the durable checkpoint for the SENT_OK_COMMITTED round-trip proof)."""

    def __init__(self, real, fail_appends: int) -> None:
        self._real = real
        self._fail = fail_appends

    def archive(self, record):
        if self._fail > 0:
            self._fail -= 1
            return False, "ARCHIVE_WRITE_FAILED:InjectedOSError"
        return self._real.archive(record)

    def __getattr__(self, name):
        return getattr(self._real, name)


# ---------------------------------------------------------------------------
# Current-schema restart preservation (required tests 30, 32-40)
# ---------------------------------------------------------------------------

def test_30_valid_current_watch_checkpoint_round_trips_exactly(tmp_path):
    watch = Watchlist(max_size=8, terminal_history_path=tmp_path / "h.jsonl")
    entry, _ = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "rt1",
         "migration_time_utc": NOW}, seeded_at_utc=NOW)
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)
    restored = _load(tmp_path, state)
    assert asdict(restored.get(MINT)) == asdict(entry)
    assert restored.checkpoint.checkpoint_records_validated == 1


def test_scheduler_field_freshness_metadata_round_trips_without_runtime_objects(tmp_path):
    watch = Watchlist(max_size=8, terminal_history_path=tmp_path / "h.jsonl")
    entry, _ = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "scheduler-checkpoint",
         "migration_time_utc": NOW}, seeded_at_utc=NOW)
    entry.market_observation_generation = 7
    entry.market_price_observed_at_utc = "2026-07-15T12:00:01Z"
    entry.market_price_source = "TRUSTED_PUMPSWAP_GRPC"
    entry.market_market_cap_observed_at_utc = "2026-07-15T12:00:01Z"
    entry.market_market_cap_source = "TRUSTED_PUMPSWAP_GRPC"
    entry.market_liquidity_observed_at_utc = "2026-07-15T12:00:02Z"
    entry.market_liquidity_source = "PAID_MARKET_SINGLE"
    entry.market_latest_tier = "Tier 1"
    entry.market_latest_drawdown_pct = "55.1"
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)
    restored = _load(tmp_path, state).get(MINT)
    assert restored is not None
    for name in (
        "market_observation_generation", "market_price_observed_at_utc",
        "market_price_source", "market_market_cap_observed_at_utc",
        "market_market_cap_source", "market_liquidity_observed_at_utc",
        "market_liquidity_source", "market_latest_tier",
        "market_latest_drawdown_pct",
    ):
        assert getattr(restored, name) == getattr(entry, name)
    raw = state.read_text(encoding="utf-8")
    assert "Thread" not in raw and "Future" not in raw and "executor" not in raw


def _activated_watchlist(tmp_path: Path):
    """Deterministic ACTIVE_DIP entry with a complete v2 proof (spot path)."""

    watch = Watchlist(max_size=8, terminal_history_path=tmp_path / "ha.jsonl")
    entry, _ = watch.seed_with_outcome({
        "token_mint": MINT, "candidate_id": "act1",
        "migration_time_utc": "2026-07-15T11:59:00Z",
        "migration_market_cap_usd": "100",
        "migration_market_cap_price": "0.0000001",
        "migration_supply_at_observation": "1000000000",
        "migration_market_cap_observed_at_utc": "2026-07-15T11:59:30Z",
        "migration_market_cap_source": "GRPC_EVENT",
    }, seeded_at_utc=NOW)
    assert entry.status == WATCH_PENDING_1_20X
    result = _fresh_spot_tick(entry, "130", "2026-07-15T12:10:00Z")
    assert result["just_activated"]
    assert entry.status == WATCH_ACTIVE_DIP
    return watch, entry


def test_32_33_34_activation_proof_and_crossing_digest_round_trip(tmp_path):
    watch, entry = _activated_watchlist(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)
    restored = _load(tmp_path, state).get(MINT)
    # 32/33: proof v2 fields round-trip exactly and stay durable
    for field in ("activation_proof_digest", "activation_proof_version",
                  "activation_evidence_digest",
                  "activation_observation_seal_digest",
                  "activation_crossing_tick_digest", "activated_at_utc"):
        assert getattr(restored, field) == getattr(entry, field)
    assert activation_proof_is_durable(restored)
    assert restored.status == WATCH_ACTIVE_DIP
    # 32: the ACTIVATED_WAITING form round-trips too
    entry.status = WATCH_ACTIVATED_WAITING
    watch.persist(state)
    waiting = _load(tmp_path, state, label="w").get(MINT)
    assert waiting.status == WATCH_ACTIVATED_WAITING
    assert activation_proof_is_durable(waiting)
    assert not activation_proof_is_eligible(waiting)


def test_35_36_market_recovery_backoff_and_probe_round_trip(tmp_path):
    watch = Watchlist(max_size=8, terminal_history_path=tmp_path / "h.jsonl")
    entry, _ = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "rec1"}, seeded_at_utc=NOW)
    entry.market_state = "MARKET_RECOVERY_BACKOFF"
    entry.market_reason_code = "MARKET_RECOVERY_BACKOFF_NOT_DUE"
    entry.next_market_refresh_at_utc = "2026-07-15T12:30:00Z"
    entry.market_attempt_count = 4
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)
    restored = _load(tmp_path, state).get(MINT)
    assert restored.market_state == "MARKET_RECOVERY_BACKOFF"
    assert restored.next_market_refresh_at_utc == "2026-07-15T12:30:00Z"
    assert restored.market_attempt_count == 4


def test_37_delivery_failed_retryable_round_trips(tmp_path):
    watch, entry = _activated_watchlist(tmp_path)
    watch.record_recheck(
        mint=MINT, reason="DELIVERY_FAILED_RETRYABLE",
        observed_at_utc="2026-07-15T12:20:00Z",
        delivery_failure_reason="TRANSPORT_HTTP_500",
        delivery_next_retry_at_utc="2026-07-15T12:25:00Z",
        delivery_attempt_id="attempt-1")
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)
    restored = _load(tmp_path, state).get(MINT)
    assert restored.delivery_state == "DELIVERY_FAILED_RETRYABLE"
    assert restored.delivery_retry_count == 1
    assert restored.delivery_next_retry_at_utc == "2026-07-15T12:25:00Z"
    assert restored.delivery_last_failure_reason == "TRANSPORT_HTTP_500"
    assert restored.status == WATCH_ACTIVE_DIP     # still active + retryable


def test_38_delivery_unknown_round_trips(tmp_path):
    watch, entry = _activated_watchlist(tmp_path)
    watch.record_recheck(
        mint=MINT, reason="DELIVERY_UNKNOWN",
        observed_at_utc="2026-07-15T12:20:00Z",
        delivery_failure_reason="TRANSPORT_TIMEOUT_AMBIGUOUS",
        delivery_attempt_id="attempt-2")
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)
    restored = _load(tmp_path, state)
    got = restored.get(MINT)
    assert got.status == WATCH_DELIVERY_UNKNOWN
    assert got.delivery_state == WATCH_DELIVERY_UNKNOWN
    assert got.delivery_attempt_id == "attempt-2"
    assert restored.active_count() == 1            # holds its slot
    assert restored.active_dip_entries() == []     # never scheduled


def test_39_40_sent_ok_committed_round_trip_and_terminal_separation(tmp_path):
    from PHX2.free_tier_producer.compat.watch_terminal_history import (
        TerminalHistoryArchive)
    real = TerminalHistoryArchive(tmp_path / "h.jsonl")
    watch = Watchlist(max_size=8, terminal_history=_FlakyArchive(real, 1))
    entry, _ = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "sent1"}, seeded_at_utc=NOW)
    watch.record_recheck(
        mint=MINT, reason="SENT_OK_COMMITTED",
        observed_at_utc="2026-07-15T12:20:00Z",
        delivery_receipt_digest="d" * 64,
        delivery_ledger_key="ledger-key-1",
        delivery_receipt_message_id=42)
    # archive append failed once: the terminal row survives in the checkpoint
    assert watch.get(MINT) is not None
    state = tmp_path / "watch_state.jsonl"
    watch.persist(state)   # persist retries the archive and releases the slot
    assert watch.get(MINT) is None
    restored = Watchlist.load(state, max_size=8, terminal_history=real)
    assert restored.active_count() == 0
    assert restored.terminal_history_count() == 1
    assert real.status_for_mint(MINT) == WATCH_SENT_OK_COMMITTED


# ---------------------------------------------------------------------------
# Legacy activation migration (required tests 41, 43-49, 51-55)
# ---------------------------------------------------------------------------

def test_41_44_legacy_active_checkpoint_migrates_without_losing_activation(
        tmp_path):
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    watch = _load(tmp_path, state, now_utc=DAY2)
    entry = watch.get(MINT)
    assert entry is not None
    assert entry.status == WATCH_ACTIVATED_WAITING            # 41: not lost
    assert entry.activation_proven is True
    assert entry.activation_evidence_kind == ACTIVATION_KIND_LEGACY_MIGRATION
    assert entry.activation_proof_version \
        == ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION          # 44: explicit
    assert entry.activation_migrated_from_schema == WATCH_LEGACY_SCHEMA_VERSION
    assert activation_proof_is_durable(entry)
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    assert watch.checkpoint.checkpoint_legacy_activation_migrated == 1


def test_43_migration_preserves_baseline_exactly(tmp_path):
    record = legacy_activated_record()
    state = _write_legacy(tmp_path, [record])
    entry = _load(tmp_path, state, now_utc=DAY2).get(MINT)
    assert entry.migration_market_cap_usd == record["migration_market_cap_usd"]
    assert entry.migration_market_cap_observed_at_utc \
        == record["migration_market_cap_observed_at_utc"]
    assert entry.activation_target_market_cap_usd \
        == record["activation_target_market_cap_usd"]
    assert entry.activation_evidence_market_cap_usd \
        == record["activation_current_market_cap_usd"]


def test_45_46_47_migration_tick_cannot_compose_reserve_or_send(tmp_path):
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    watch = _load(tmp_path, state, now_utc=DAY2)
    entry = watch.get(MINT)
    # activation_proof_is_eligible is the single gate the compose/reserve/send
    # path consumes (build29_cap1_compose_send guards on it before any
    # snapshot, dedupe reservation, or transport call).
    assert not activation_proof_is_eligible(entry)
    assert entry.activation_snapshot()["activation_eligible"] is False
    assert watch.active_dip_entries() == []


def test_48_later_genuine_fresh_tick_resumes_tier_evaluation(tmp_path):
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    watch = _load(tmp_path, state, now_utc=DAY2)
    entry = watch.get(MINT)
    result = _fresh_spot_tick(entry, "125", "2026-07-16T13:00:00Z")
    assert result["eligible"] is True
    assert entry.status == WATCH_ACTIVE_DIP
    assert activation_proof_is_eligible(entry)


def test_49_equal_reobservation_does_not_replay_the_migrated_crossing(
        tmp_path):
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    watch = _load(tmp_path, state, now_utc=DAY2)
    entry = watch.get(MINT)
    crossing = entry.activation_crossing_tick_digest
    proof = entry.activation_proof_digest
    result = _fresh_spot_tick(entry, "130", "2026-07-16T13:00:00Z")
    assert result["just_activated"] is False        # never a second crossing
    assert entry.activation_crossing_tick_digest == crossing
    assert entry.activation_proof_digest == proof
    again = _fresh_spot_tick(entry, "130", "2026-07-16T13:01:00Z")
    assert again["just_activated"] is False


def test_51_ambiguous_legacy_activation_quarantines_fixture_d(tmp_path):
    # FIXTURE D: one required authenticated legacy field removed.
    record = legacy_activated_record()
    del record["migration_market_cap_price"]
    state = _write_legacy(tmp_path, [record])
    watch = _load(tmp_path, state, now_utc=DAY2)
    assert watch.get(MINT) is None                  # no guessed proof
    quarantined = watch.quarantined_candidate_records()
    assert MINT in quarantined
    assert quarantined[MINT]["quarantine_reason"] \
        == cpe.QUARANTINE_ACTIVATION_MIGRATION_AMBIGUOUS
    assert watch.checkpoint.checkpoint_legacy_activation_quarantined == 1
    # the original evidence payload is preserved verbatim
    assert quarantined[MINT]["legacy_payload"]["activation_proven"] is True
    # equal/late re-observation cannot silently manufacture the activation:
    # the mint stays quarantined and unschedulable
    blocked, outcome = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "retry"}, seeded_at_utc=DAY2)
    assert blocked is None and outcome == SEED_OUTCOME_CHECKPOINT_QUARANTINED


@pytest.mark.parametrize("mutation, detail", [
    ({"activation_proven": False}, "not proven"),
    ({"activation_current_market_cap_usd": "110"}, "below target"),
    ({"activation_target_market_cap_usd": "121"}, "target mismatch"),
    ({"activated_at_utc": "2026-07-15T10:00:00Z"}, "before baseline"),
    ({"activation_observation_source": "UNKNOWN_SOURCE"}, "bad source"),
    ({"activation_proof_digest": "e" * 64}, "contradictory current proof"),
])
def test_51b_insufficient_legacy_evidence_never_migrates(
        tmp_path, mutation, detail):
    record = legacy_activated_record()
    record.update(mutation)
    state = _write_legacy(tmp_path, [record])
    watch = _load(tmp_path, state, now_utc=DAY2)
    entry = watch.get(MINT)
    if entry is not None:
        assert entry.status != WATCH_ACTIVATED_WAITING, detail
        assert not activation_proof_is_durable(entry), detail
    else:
        assert MINT in watch.quarantined_candidate_records(), detail
    assert watch.checkpoint.checkpoint_legacy_activation_migrated == 0


def test_52_unsupported_legacy_status_quarantines(tmp_path):
    record = legacy_activated_record(status="SOME_FUTURE_STATE")
    state = _write_legacy(tmp_path, [record])
    watch = _load(tmp_path, state, now_utc=DAY2)
    assert watch.get(MINT) is None
    assert watch.quarantined_candidate_records()[MINT]["quarantine_reason"] \
        == cpe.QUARANTINE_LEGACY_STATUS_UNSUPPORTED


def test_53_54_55_migration_is_deterministic_and_idempotent(tmp_path):
    records = [legacy_activated_record(),
               legacy_activated_record(HMMN, candidate_id="legacy_hm")]
    digests = []
    for run in ("a", "b"):
        sub = tmp_path / run
        sub.mkdir()
        state = _write_legacy(sub, records)
        watch = Watchlist.load(
            state, max_size=64, terminal_history_path=sub / "h.jsonl",
            now_utc=DAY2)
        assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
        header = json.loads(
            state.read_text(encoding="utf-8").splitlines()[0])
        digests.append(header["payload_digest"])
    # 53/55: two migrations of the same source with the same anchor produce
    # the SAME current payload digest (envelope header timestamps are
    # write-receipt metadata, deliberately outside the determinism contract)
    assert digests[0] == digests[1]
    # 54: re-loading the migrated checkpoint changes nothing (no second
    # migration, same installed payload digest)
    state = tmp_path / "a" / "watch_state.jsonl"
    before = json.loads(state.read_text(encoding="utf-8").splitlines()[0])
    again = Watchlist.load(
        state, max_size=64,
        terminal_history_path=tmp_path / "a" / "h2.jsonl", now_utc=DAY2)
    assert again.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK
    assert again.checkpoint.checkpoint_migrations_attempted == 0
    after = json.loads(state.read_text(encoding="utf-8").splitlines()[0])
    assert after["payload_digest"] == before["payload_digest"]


def test_56_partial_migration_write_leaves_legacy_source_intact(
        tmp_path, monkeypatch):
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    original = state.read_bytes()

    def failing_write(**_kwargs):
        raise cpe.CheckpointWriteError("CHECKPOINT_WRITE_FAILED:Injected")

    monkeypatch.setattr(cpe, "write_checkpoint_generation", failing_write)
    watch = _load(tmp_path, state, now_utc=DAY2)
    assert state.read_bytes() == original          # source retained
    assert watch.checkpoint_quarantined            # no partial activation
    assert watch.checkpoint.checkpoint_quarantine_reason \
        == cpe.QUARANTINE_MIGRATION_WRITE_FAILED
    assert watch.checkpoint.checkpoint_migrations_failed == 1
    assert watch.all_entries() == []


# ---------------------------------------------------------------------------
# Quarantined-candidate isolation (required tests 59-62)
# ---------------------------------------------------------------------------

def test_59_60_61_62_quarantined_candidates_receive_zero_production_work(
        tmp_path):
    record = legacy_activated_record()
    del record["migration_market_cap_price"]       # ambiguous -> quarantined
    healthy = legacy_activated_record(
        HMMN, candidate_id="legacy_ok")
    state = _write_legacy(tmp_path, [record, healthy])
    watch = _load(tmp_path, state, now_utc=DAY2)
    assert MINT in watch.quarantined_candidate_records()
    # 59: zero market calls — the quarantined mint is absent from EVERY
    # scheduling surface the production watch loop iterates.
    assert all(e.token_mint != MINT for e in watch.all_entries())
    assert all(e.token_mint != MINT for e in watch.tracked_entries())
    assert all(e.token_mint != MINT for e in watch.active_entries())
    # 60/61: zero compose attempts / delivery reservations — the compose path
    # takes candidates ONLY from active_dip_entries + the eligibility gate.
    assert all(e.token_mint != MINT for e in watch.active_dip_entries())
    # 62: zero successful-send ledger rows — nothing can even reserve, and
    # re-seeding is refused instead of resurrecting the candidate.
    blocked, outcome = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "z"}, seeded_at_utc=DAY2)
    assert blocked is None and outcome == SEED_OUTCOME_CHECKPOINT_QUARANTINED
    # quarantine survives restart inside the authenticated checkpoint
    reloaded = _load(tmp_path, state, label="r")
    assert MINT in reloaded.quarantined_candidate_records()
    assert all(e.token_mint != MINT for e in reloaded.all_entries())


def test_cross_checkpoint_consistency_quarantines_contradiction(tmp_path):
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    watch = _load(tmp_path, state, now_utc=DAY2)
    assert watch.get(MINT) is not None
    findings = verify_cross_checkpoint_consistency(
        watch, {MINT: {"token_mint": MINT, "ath_market_cap": "50"}},
        now_utc=DAY2)
    assert len(findings) == 1
    assert findings[0]["issue"] == "ACTIVATED_BUT_CENTRAL_ATH_BELOW_TARGET"
    assert watch.get(MINT) is None
    assert MINT in watch.quarantined_candidate_records()
    # consistent ATH state (>= target) quarantines nothing
    sub = tmp_path / "ok"
    sub.mkdir()
    state2 = _write_legacy(sub, [legacy_activated_record()])
    watch2 = Watchlist.load(state2, max_size=64,
                            terminal_history_path=sub / "h.jsonl",
                            now_utc=DAY2)
    assert verify_cross_checkpoint_consistency(
        watch2, {MINT: {"token_mint": MINT, "ath_market_cap": "130"}},
        now_utc=DAY2) == []
    assert watch2.get(MINT) is not None


def test_send_family_terminal_history_conflict_quarantines(tmp_path):
    from PHX2.free_tier_producer.compat.watch_terminal_history import (
        TerminalHistoryArchive, build_terminal_history_record)
    history_path = tmp_path / "history.jsonl"
    archive = TerminalHistoryArchive(history_path)
    ok, _ = archive.archive(build_terminal_history_record(
        token_mint=MINT, candidate_id="prior", terminal_status="SENT_OK_COMMITTED",
        terminal_reason="SENT_OK_COMMITTED", terminal_at_utc=NOW,
        seeded_at_utc=NOW))
    assert ok
    state = _write_legacy(tmp_path, [legacy_activated_record()])
    watch = Watchlist.load(state, max_size=64,
                           terminal_history_path=history_path, now_utc=DAY2)
    # a mint the history already recorded as SENT can never restore active
    assert watch.get(MINT) is None
    assert watch.quarantined_candidate_records()[MINT]["quarantine_reason"] \
        == cpe.QUARANTINE_GENERATION_CONFLICT


# ---------------------------------------------------------------------------
# FIXTURE C — exact preserved-run migration (HmMN + Xw9 activation loss)
# ---------------------------------------------------------------------------

def _preserved_expectations():
    return {
        HMMN: {"status": WATCH_ACTIVATED_WAITING, "migrated": True,
               "baseline": "56347.241540345196",
               "target": "67616.68984841423520",
               "evidence": "75834.48270377345"},
        XW9: {"status": WATCH_ACTIVATED_WAITING, "migrated": True,
              "baseline": "21292.360165645034",
              "target": "25550.83219877404080"},
        "41VHigULn7wAFsk8ZjuH7zQoAybuGrBAJGgjLsZcpump": {
            "status": WATCH_PENDING_1_20X, "migrated": False,
            "baseline": "32685.55146934647"},
        "9Gsj9bbmekAvDbaTX4EvEJu6opWTn66oFuDcybG3pump": {
            "status": WATCH_PENDING_1_20X, "migrated": False},
        "DiV3ikZtwdQCMY7j6ovNrDTJJJVHfW6amz7F6Emapump": {
            "status": WATCH_PENDING_1_20X, "migrated": False},
        "GgJq4UwLvsPrKxLV4xDKm3aJn9pvx7jXAVenKgePpump": {
            "status": "PENDING_BASELINE", "migrated": False},
    }


def test_fixture_c_preserved_run_watch_checkpoint_migrates(tmp_path):
    state = tmp_path / "watch_state.jsonl"
    state.write_bytes(PRESERVED_WATCH.read_bytes())
    watch = Watchlist.load(
        state, max_size=64, terminal_history_path=tmp_path / "h.jsonl",
        now_utc="2026-07-19T00:00:00Z")
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    assert watch.checkpoint.checkpoint_legacy_activation_migrated == 2
    assert watch.checkpoint.checkpoint_legacy_activation_quarantined == 0
    assert watch.quarantined_candidate_records() == {}
    for mint, expected in _preserved_expectations().items():
        entry = watch.get(mint)
        assert entry is not None, mint
        assert entry.status == expected["status"], mint
        if "baseline" in expected:
            assert entry.migration_market_cap_usd == expected["baseline"], mint
        if "target" in expected:
            assert entry.activation_target_market_cap_usd \
                == expected["target"], mint
        if expected["migrated"]:
            assert entry.activation_evidence_kind \
                == ACTIVATION_KIND_LEGACY_MIGRATION, mint
            assert activation_proof_is_durable(entry), mint
            assert not activation_proof_is_eligible(entry), mint
            if "evidence" in expected:
                assert entry.activation_evidence_market_cap_usd \
                    == expected["evidence"], mint
    # a later genuinely fresh HmMN tick resumes tier evaluation
    hmmn = watch.get(HMMN)
    result = _fresh_spot_tick(hmmn, "70000", "2026-07-19T01:00:00Z")
    assert result["eligible"] is True
    assert hmmn.status == WATCH_ACTIVE_DIP
    # migrated checkpoint restores exactly on the next restart
    reloaded = Watchlist.load(
        state, max_size=64, terminal_history_path=tmp_path / "h2.jsonl")
    assert reloaded.checkpoint.checkpoint_status \
        == cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK
    assert activation_proof_is_durable(reloaded.get(HMMN))


REAL_PRESERVED = Path(r"C:\tmp\phx2_live_20260718T195225Z\producer")


@pytest.mark.skipif(not REAL_PRESERVED.exists(),
                    reason="preserved live-run artifacts not present")
def test_fixture_c_real_preserved_artifacts_migrate_identically(tmp_path):
    state = tmp_path / "watch_state.jsonl"
    state.write_bytes((REAL_PRESERVED / "watch_state.jsonl").read_bytes())
    backup = tmp_path / "watch_state.jsonl.bak"
    backup.write_bytes((REAL_PRESERVED / "watch_state.jsonl.bak").read_bytes())
    watch = Watchlist.load(
        state, max_size=64, terminal_history_path=tmp_path / "h.jsonl",
        now_utc="2026-07-19T00:00:00Z")
    assert watch.checkpoint.checkpoint_status == cpe.CHECKPOINT_MIGRATED
    assert watch.checkpoint.checkpoint_legacy_activation_migrated == 2
    for mint, expected in _preserved_expectations().items():
        entry = watch.get(mint)
        assert entry is not None and entry.status == expected["status"], mint
    # the embedded fixture is the EXACT preserved artifact
    assert PRESERVED_WATCH.read_bytes() \
        == (REAL_PRESERVED / "watch_state.jsonl").read_bytes()
