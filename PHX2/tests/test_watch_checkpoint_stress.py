"""Watch-checkpoint persistence stress: the 7a538f8 fix, re-proven at scale.

The 2026-07-30 canary died with ``WATCH_CHECKPOINT_STRUCTURAL_FAILURE`` /
``CHECKPOINT_NUMERIC_INVALID``: ``project_closed_tier`` returns the drawdown
``"0"`` whenever a mint's current market cap equals its own ATH -- true for
EVERY mint on the tick that first establishes its ATH from a spot observation
-- and the field was validated as STRICTLY positive.  Structural failures are
never retried, so the durable checkpoint simply stopped being written (17
attempted, 2 succeeded, 15 consecutive structural failures) and the watchdog
integrity-locked the circuit.

The fix landed at 7a538f8.  This module re-proves it under the load the
discovery-policy prerequisite names: the exact preserved invalid record, zero
drawdown, pending AND complete ATH records, mixed LIVE_HELIUS and DEX
provenance, at least 100 write/restore cycles, and corrupt NaN / Infinity /
negative controls that must still fail closed.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_HELIUS,
    DISCOVERY_PROVENANCE_LIVE,
    WatchEntry,
    Watchlist,
    canonicalize_watch_checkpoint_records,
    describe_checkpoint_records,
    validate_watch_checkpoint_record,
)
from PHX2.free_tier_producer.market_scheduler import project_closed_tier


#: The preserved mint and the spot market cap that first established its ATH.
WEN_MINT = "DKDjfsrv2bhBQVuT7ePDZDup2KJbQwNvNPBWtNjVpump"
SPOT_MARKET_CAP = "46686.30495467755"
MIGRATION_UTC = "2026-07-30T22:13:40Z"

#: At least this many durable write/restore cycles must all succeed.
STRESS_CYCLES = 100


def _entry(mint: str, *, candidate_id: str) -> WatchEntry:
    """A plain live-provenance watch row (the checkpoint defect is orthogonal
    to activation state, so the fixture carries no activation proof)."""

    return WatchEntry(
        token_mint=mint, candidate_id=candidate_id,
        migration_time_utc=MIGRATION_UTC,
        source_ref="helius:%s" % candidate_id,
        seeded_at_utc="2026-07-30T22:20:55Z")


def _mint(prefix: str, index: int) -> str:
    return "%s%spump" % (prefix, str(index).rjust(44 - len(prefix) - 4, "0"))


def _dex_candidate(mint: str, *, index: int) -> dict:
    """A REAL restart-backfill candidate: the only way a DEX-provenance watch
    row carries the backfill evidence and 1.39 multiplier the checkpoint
    validator requires."""

    import time

    from PHX2.free_tier_producer.dexscreener_restart_backfill import (
        build_backfill_candidate,
    )

    now = time.time()
    candidate, reason = build_backfill_candidate(
        pair={
            "chainId": "solana", "dexId": "pumpswap",
            "pairAddress": "pair-%d" % index,
            "pairCreatedAt": int((now - 60) * 1000),
            "baseToken": {"address": mint, "symbol": "T%d" % index,
                          "name": "Token %d" % index},
            "priceUsd": "0.0001", "marketCap": "100000",
            "liquidity": {"usd": "5000"},
            "volume": {"m5": "1", "h1": "10", "h6": "20", "h24": "30"},
        },
        sol_price_usd=Decimal("150"), sol_fallback_used=False,
        sweep_id="dex_sweep_stress", epoch_id="epoch-stress",
        discovery_utc="2026-07-30T22:20:55Z", now_epoch=now)
    assert reason == "ACCEPTED", reason
    return candidate


def _mixed_population(watchlist: Watchlist) -> int:
    """Pending AND complete ATH rows, mixed live and DEX provenance.

    Returns the expected record count.  DEX rows are seeded through the REAL
    admission path so their backfill evidence is genuine.
    """

    # 1. The exact preserved record: zero drawdown, no tier.
    wen = _entry(WEN_MINT, candidate_id="live_wen")
    assert wen.set_market_tier_projection(tier=None, drawdown_pct="0")
    watchlist._entries[WEN_MINT] = wen

    # 2. DEX-provenance rows, ATH hydration still PENDING.
    for index in range(6):
        mint = _mint("Pend", index)
        entry = watchlist.seed(_dex_candidate(mint, index=index),
                               seeded_at_utc="2026-07-30T22:20:55Z")
        assert entry is not None, mint
        assert entry.discovery_provenance == DISCOVERY_PROVENANCE_DEX
        entry.set_market_tier_projection(tier=None, drawdown_pct="0")

    # 3. Live-provenance rows with a real tier from a complete ATH.
    tier, drawdown = project_closed_tier(
        ath_market_cap_usd="67087.57", current_market_cap_usd="19900")
    assert tier == "Tier 2"
    for index in range(6):
        mint = _mint("Live", index)
        entry = _entry(mint, candidate_id="live_%d" % index)
        assert entry.discovery_provenance in (
            DISCOVERY_PROVENANCE_LIVE, DISCOVERY_PROVENANCE_HELIUS)
        entry.set_market_tier_projection(tier=tier, drawdown_pct=drawdown)
        watchlist._entries[mint] = entry

    return 13


def _watchlist(tmp_path: Path, suffix: str = "") -> Watchlist:
    return Watchlist(
        max_size=64,
        terminal_history_path=tmp_path / ("terminal%s.jsonl" % suffix))


# ---------------------------------------------------------------------------
# the exact preserved record
# ---------------------------------------------------------------------------


def test_the_exact_preserved_invalid_record_now_validates() -> None:
    tier, drawdown = project_closed_tier(
        ath_market_cap_usd=SPOT_MARKET_CAP,
        current_market_cap_usd=SPOT_MARKET_CAP)
    assert (tier, drawdown) == (None, "0")     # the exact rejected raw value

    record = {
        key: value for key, value
        in _entry(WEN_MINT, candidate_id="live_wen").__dict__.items()
        if not key.startswith("_")}
    record["market_latest_tier"] = None
    record["market_latest_drawdown_pct"] = drawdown
    ok, reason = validate_watch_checkpoint_record(record)
    assert (ok, reason) == (True, "")
    canonical, conflicts = canonicalize_watch_checkpoint_records([record])
    assert conflicts == []
    assert describe_checkpoint_records(canonical) is None


def test_zero_drawdown_is_legitimate_for_every_mint_on_its_first_ath(
        tmp_path: Path) -> None:
    watchlist = _watchlist(tmp_path)
    for index in range(11):        # the failing write's 11 records
        mint = _mint("Zero", index)
        entry = _entry(mint, candidate_id="zero_%d" % index)
        assert entry.set_market_tier_projection(tier=None, drawdown_pct="0")
        watchlist._entries[mint] = entry
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)
    summary = watchlist.checkpoint_summary()
    assert summary["checkpoint_structural_failed_total"] == 0
    assert summary["checkpoint_write_succeeded_total"] == 1


# ---------------------------------------------------------------------------
# the stress cycle
# ---------------------------------------------------------------------------


def test_one_hundred_write_restore_cycles_all_succeed(tmp_path: Path) -> None:
    """>=100 durable cycles over the mixed population, zero valid failures."""

    path = tmp_path / "watch_state.jsonl"
    watchlist = _watchlist(tmp_path)
    expected_count = _mixed_population(watchlist)

    restored_counts = []
    for cycle in range(STRESS_CYCLES):
        watchlist.persist(path)
        restored = Watchlist.load(
            path, max_size=64,
            terminal_history_path=tmp_path / "terminal_restore.jsonl")
        assert restored.checkpoint.checkpoint_quarantined is False, cycle
        restored_counts.append(len(restored.active_entries()))

    summary = watchlist.checkpoint_summary()
    assert summary["checkpoint_write_attempted_total"] == STRESS_CYCLES
    assert summary["checkpoint_write_succeeded_total"] == STRESS_CYCLES
    assert summary["checkpoint_structural_failed_total"] == 0
    assert summary["checkpoint_write_permanent_failed_total"] == 0
    # Record count matches on every restore, not just the last one.
    assert set(restored_counts) == {expected_count}


def test_the_restored_population_is_faithful(tmp_path: Path) -> None:
    path = tmp_path / "watch_state.jsonl"
    watchlist = _watchlist(tmp_path)
    _mixed_population(watchlist)
    watchlist.persist(path)

    restored = Watchlist.load(
        path, max_size=64,
        terminal_history_path=tmp_path / "terminal_restore.jsonl")
    assert restored.get(WEN_MINT).market_latest_drawdown_pct == "0"
    assert restored.get(WEN_MINT).market_latest_tier is None
    live = restored.get(_mint("Live", 0))
    assert live is not None
    assert live.market_latest_tier == "Tier 2"
    assert Decimal(live.market_latest_drawdown_pct) > Decimal("70")
    pending = restored.get(_mint("Pend", 0))
    assert pending is not None
    assert pending.market_latest_drawdown_pct == "0"


def test_no_circuit_open_condition_is_generated_by_valid_records(
        tmp_path: Path) -> None:
    """A structural failure is what integrity-locks the circuit. There is none."""

    path = tmp_path / "watch_state.jsonl"
    watchlist = _watchlist(tmp_path)
    _mixed_population(watchlist)
    for _ in range(STRESS_CYCLES):
        watchlist.persist(path)
    summary = watchlist.checkpoint_summary()
    assert summary["checkpoint_structural_failed_total"] == 0
    assert summary["checkpoint_consecutive_failures"] == 0
    assert summary["checkpoint_last_failure_category"] in (None, "")
    assert summary["checkpoint_last_failure_detail"] in (None, "")
    assert summary["checkpoint_write_permanent_failed_total"] == 0
    assert not summary["checkpoint_persist_refused"]
    assert summary["checkpoint_quarantined"] is False


# ---------------------------------------------------------------------------
# negative controls: corruption still fails closed
# ---------------------------------------------------------------------------


def test_corrupt_numeric_controls_still_fail_closed() -> None:
    from PHX2.free_tier_producer.compat.build30_watchlist import (
        _WATCH_DECIMAL_FIELDS,
        _WATCH_NONNEGATIVE_DECIMAL_FIELDS,
    )

    base = {
        key: value for key, value
        in _entry(WEN_MINT, candidate_id="live_wen").__dict__.items()
        if not key.startswith("_")}
    for field_name in _WATCH_DECIMAL_FIELDS + _WATCH_NONNEGATIVE_DECIMAL_FIELDS:
        for bad in ("NaN", "Infinity", "-Infinity", "-1", "-0.5", 1.5,
                    Decimal("1")):
            record = dict(base)
            record[field_name] = bad
            ok, reason = validate_watch_checkpoint_record(record)
            assert ok is False, (field_name, bad)
            assert reason == cpe.QUARANTINE_NUMERIC_INVALID


def test_zero_is_accepted_only_where_it_is_legitimate() -> None:
    from PHX2.free_tier_producer.compat.build30_watchlist import (
        _WATCH_DECIMAL_FIELDS,
        _WATCH_NONNEGATIVE_DECIMAL_FIELDS,
    )

    base = {
        key: value for key, value
        in _entry(WEN_MINT, candidate_id="live_wen").__dict__.items()
        if not key.startswith("_")}
    for field_name in _WATCH_NONNEGATIVE_DECIMAL_FIELDS:
        record = dict(base)
        record[field_name] = "0"
        ok, _reason = validate_watch_checkpoint_record(record)
        assert ok is True, field_name
    for field_name in _WATCH_DECIMAL_FIELDS:
        record = dict(base)
        record[field_name] = "0"
        ok, reason = validate_watch_checkpoint_record(record)
        assert ok is False, field_name
        assert reason == cpe.QUARANTINE_NUMERIC_INVALID


def test_a_corrupt_checkpoint_file_quarantines_rather_than_loading(
        tmp_path: Path) -> None:
    path = tmp_path / "watch_state.jsonl"
    watchlist = _watchlist(tmp_path)
    entry = _entry(WEN_MINT, candidate_id="live_wen")
    entry.set_market_tier_projection(tier=None, drawdown_pct="0")
    watchlist._entries[WEN_MINT] = entry
    watchlist.persist(path)

    # The file is an authenticated envelope header followed by one record per
    # line.  Poison the RECORD (a non-finite decimal) and leave the header's
    # digest untouched: the load must refuse rather than admit the record.
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2
    record = json.loads(lines[1])
    record["market_latest_drawdown_pct"] = "NaN"
    lines[1] = json.dumps(record, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    backup = path.with_name(path.name + ".bak")
    if backup.exists():
        backup.unlink()

    restored = Watchlist.load(
        path, max_size=64,
        terminal_history_path=tmp_path / "terminal_restore.jsonl")
    assert restored.checkpoint.checkpoint_quarantined is True
    assert restored.active_entries() == []


def test_every_persisted_numeric_value_is_json_finite(tmp_path: Path) -> None:
    path = tmp_path / "watch_state.jsonl"
    watchlist = _watchlist(tmp_path)
    _mixed_population(watchlist)
    watchlist.persist(path)
    text = path.read_text(encoding="utf-8")
    for token in ("NaN", "Infinity", "-Infinity"):
        assert token not in text
    for line in text.splitlines():
        if line.strip():
            json.loads(line)          # strict: rejects NaN/Infinity literals

