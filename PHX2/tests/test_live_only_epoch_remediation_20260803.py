"""Offline regression gate for the accepted per-process live-only policy."""

from __future__ import annotations

import json
from decimal import Decimal

from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_HELIUS,
    SEED_OUTCOME_ADMITTED,
    SEED_OUTCOME_DIAGNOSTIC_ONLY,
    SEED_OUTCOME_PRE_BOUNDARY,
    Watchlist,
)
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    DEX_ELIGIBILITY_MODE,
    PRE_BOUNDARY_NOT_ELIGIBLE,
    build_backfill_candidate,
)
from PHX2.free_tier_producer.live_epoch import (
    EPOCH_EVENT_ADMITTED,
    LiveEpochManager,
)


NOW = "2026-08-03T04:00:00Z"
OLD_EPOCH = "epoch-a"
NEW_EPOCH = "epoch-b"
BOUNDARY = 436_887_781
LIVE_MINT = "LiveOnlyBoundary000000000000000000000pump"
DEX_MINT = "LiveOnlyDexDiagnostic000000000000000pump"


def _live_candidate(*, slot: int, epoch: str = NEW_EPOCH, mint: str = LIVE_MINT):
    return {
        "token_mint": mint,
        "candidate_id": f"helius-{slot}",
        "discovery_provenance": DISCOVERY_PROVENANCE_HELIUS,
        "live_epoch_id": epoch,
        "migration_slot": slot,
        "migration_time_utc": NOW,
        "source_ref": f"proof-{slot}",
    }


def _dex_candidate(now_epoch: float):
    candidate, reason = build_backfill_candidate(
        pair={
            "chainId": "solana",
            "dexId": "pumpswap",
            "pairAddress": "diagnostic-pair",
            "pairCreatedAt": int((now_epoch - 60) * 1000),
            "baseToken": {
                "address": DEX_MINT,
                "symbol": "DIAG",
                "name": "Diagnostic",
            },
            "priceUsd": "0.0001",
            "marketCap": "100000",
            "liquidity": {"usd": "5000"},
            "volume": {"m5": "1", "h1": "2", "h6": "3", "h24": "4"},
        },
        sol_price_usd=Decimal("150"),
        sol_fallback_used=False,
        sweep_id="diagnostic-sweep",
        epoch_id=NEW_EPOCH,
        discovery_utc=NOW,
        now_epoch=now_epoch,
    )
    assert reason == "ACCEPTED"
    assert candidate is not None
    return candidate


def test_restart_epoch_b_archives_epoch_a_without_rebinding(tmp_path):
    state = tmp_path / "watch_state.jsonl"
    history = tmp_path / "watch_terminal_history.jsonl"
    old = Watchlist(max_size=8, terminal_history_path=history)
    entry, outcome = old.seed_with_outcome(
        _live_candidate(slot=BOUNDARY - 10, epoch=OLD_EPOCH),
        seeded_at_utc=NOW,
    )
    assert outcome == SEED_OUTCOME_ADMITTED
    original_slot = entry.migration_slot
    old.persist(state)

    restored = Watchlist.load(
        state, max_size=8, terminal_history_path=history, now_utc=NOW)
    assert restored.active_count() == 1
    assert restored.rebind_restored_live_entries(
        NEW_EPOCH, rebound_at_utc=NOW) == 0
    assert restored.get(LIVE_MINT).migration_slot == original_slot

    assert restored.begin_live_only_epoch(
        NEW_EPOCH, first_eligible_slot=BOUNDARY, opened_at_utc=NOW) == 1
    assert restored.active_count() == 0
    summary = restored.summary()
    assert summary["historical_candidates_eligible"] == 0
    assert summary["restored_diagnostic_records"] == 1
    assert summary["pre_boundary_candidates_ignored"] == 1
    # The authenticated checkpoint itself remains readable evidence; opening
    # the new domain never rewrites the old epoch or migration slot.
    durable = Watchlist.load(
        state, max_size=8, terminal_history_path=tmp_path / "durable.jsonl",
        now_utc=NOW,
    )
    assert durable.get(LIVE_MINT).live_epoch_id == OLD_EPOCH
    assert durable.get(LIVE_MINT).migration_slot == original_slot
    terminal_rows = [
        json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert terminal_rows[-1]["terminal_reason"] == PRE_BOUNDARY_NOT_ELIGIBLE


def test_boundary_minus_one_is_terminal_and_exact_boundary_is_admitted(tmp_path):
    watch = Watchlist(
        max_size=8, terminal_history_path=tmp_path / "history.jsonl")
    watch.begin_live_only_epoch(
        NEW_EPOCH, first_eligible_slot=BOUNDARY, opened_at_utc=NOW)

    rejected, reason = watch.seed_with_outcome(
        _live_candidate(slot=BOUNDARY - 1), seeded_at_utc=NOW)
    assert rejected is None
    assert reason == SEED_OUTCOME_PRE_BOUNDARY

    admitted, reason = watch.seed_with_outcome(
        _live_candidate(slot=BOUNDARY), seeded_at_utc=NOW)
    assert admitted is not None
    assert admitted.migration_slot == BOUNDARY
    assert reason == SEED_OUTCOME_ADMITTED
    assert watch.summary()["post_boundary_candidates_admitted"] == 1
    assert watch.summary()["historical_candidates_eligible"] == 0


def test_wrong_epoch_or_missing_authenticated_slot_cannot_be_rebound(tmp_path):
    watch = Watchlist(
        max_size=8, terminal_history_path=tmp_path / "history.jsonl")
    watch.begin_live_only_epoch(
        NEW_EPOCH, first_eligible_slot=BOUNDARY, opened_at_utc=NOW)
    wrong_epoch, reason = watch.seed_with_outcome(
        _live_candidate(slot=BOUNDARY + 1, epoch=OLD_EPOCH),
        seeded_at_utc=NOW,
    )
    assert wrong_epoch is None and reason == SEED_OUTCOME_PRE_BOUNDARY
    missing = _live_candidate(slot=BOUNDARY + 2)
    missing["migration_slot"] = None
    no_slot, reason = watch.seed_with_outcome(missing, seeded_at_utc=NOW)
    assert no_slot is None and reason == SEED_OUTCOME_PRE_BOUNDARY


def test_dex_pre_boundary_row_is_diagnostic_only_and_does_not_consume_mint(tmp_path):
    watch = Watchlist(
        max_size=8, terminal_history_path=tmp_path / "history.jsonl")
    watch.begin_live_only_epoch(
        NEW_EPOCH, first_eligible_slot=BOUNDARY, opened_at_utc=NOW)
    dex = _dex_candidate(1_785_726_000.0)
    assert dex["eligibility_mode"] == DEX_ELIGIBILITY_MODE
    assert dex["terminal_classification"] == PRE_BOUNDARY_NOT_ELIGIBLE

    entry, reason = watch.seed_with_outcome(dex, seeded_at_utc=NOW)
    assert entry is None and reason == SEED_OUTCOME_DIAGNOSTIC_ONLY
    assert watch.get(DEX_MINT) is None
    summary = watch.summary()
    assert summary["dex_diagnostic_records"] == 1
    assert summary["dex_backfill_candidates"] == 0
    assert summary["historical_candidates_eligible"] == 0

    # Diagnostic DEX history does not consume dedupe or prevent a later
    # authenticated current-epoch Helius proof for the same mint.
    live, reason = watch.seed_with_outcome(
        _live_candidate(slot=BOUNDARY, mint=DEX_MINT), seeded_at_utc=NOW)
    assert live is not None and reason == SEED_OUTCOME_ADMITTED


def test_live_epoch_manager_authenticates_h_plus_one_for_watch_admission(tmp_path):
    manager = LiveEpochManager(
        state_dir=tmp_path / "epoch",
        now_fn=lambda: NOW,
        id_fn=lambda: NEW_EPOCH,
    )
    assert manager.observe_confirmed_slot(
        BOUNDARY - 1, observed_at_utc=NOW)
    assert manager.admit_event(BOUNDARY - 1)[1] \
        == PRE_BOUNDARY_NOT_ELIGIBLE
    admitted, reason, epoch_id = manager.admit_event(BOUNDARY)
    assert admitted is True and reason == EPOCH_EVENT_ADMITTED

    watch = Watchlist(
        max_size=8, terminal_history_path=tmp_path / "history.jsonl")
    watch.begin_live_only_epoch(
        epoch_id,
        first_eligible_slot=manager.snapshot()["epoch_start_slot"],
        opened_at_utc=NOW,
    )
    entry, outcome = watch.seed_with_outcome(
        _live_candidate(slot=BOUNDARY, epoch=epoch_id), seeded_at_utc=NOW)
    assert entry is not None and outcome == SEED_OUTCOME_ADMITTED
