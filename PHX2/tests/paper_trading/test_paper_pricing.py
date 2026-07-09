"""Normalizer tests over the real PHX2 artifact record shapes."""

from __future__ import annotations

import json

import pytest

from PHX2.paper_trading.models import (
    parse_money_text,
    parse_pct_text,
    parse_tier,
    parse_utc,
)
from PHX2.paper_trading.pricing import load_snapshots, normalize_record

# Mirrors the real BUILD30_CANDIDATE_RECHECK shape from the production
# out/ artifacts (values shortened; structure identical).
BUILD30_RECORD = {
    "kind": "BUILD30_CANDIDATE_RECHECK",
    "candidate_id": "cap1_FUgkEDtJ",
    "token_mint": "F" * 40 + "pump",
    "observed_at_utc": "2026-06-26T08:19:16Z",
    "migration_time_utc": "2026-06-26T08:02:26Z",
    "recheck_index": 18,
    "compose_tier": "Tier 2",
    "compose_drawdown_pct": "67.15%",
    "compose_anchored_ath_mc": "$25.6k",
    "compose_decision": "NO_SEND_DISPATCHED",
    "market_attempt_summary": {
        "attempts": [{
            "all_present": True,
            "attempt_at_utc": "2026-06-26T08:19:15Z",
            "lp_value": "5859.308625941959",
            "mc_value": "8418.864888513863",
            "price_value": "0.000008418864888549567",
        }],
        "basis": "REAL_MARKET_PRESENT",
        "current_market_cap_usd": "8418.864888513863",
        "current_price": "0.000008418864888549567",
        "liquidity_usd": "5859.308625941959",
        "market_context_fetched_at_utc": "2026-06-26T08:19:15Z",
        "mc_present": True, "price_present": True, "lp_present": True,
    },
}


class TestNormalizeRecord:
    def test_build30_record_full(self):
        snap = normalize_record(BUILD30_RECORD, "f.jsonl", 3)
        assert snap is not None
        assert snap.mint.endswith("pump")
        assert snap.candidate_id == "cap1_FUgkEDtJ"
        assert snap.price_usd == pytest.approx(8.418864888549567e-06)
        assert snap.market_cap_usd == pytest.approx(8418.864888513863)
        assert snap.liquidity_usd == pytest.approx(5859.308625941959)
        assert snap.tier == 2
        assert snap.drawdown_pct == pytest.approx(67.15)
        assert snap.ath_market_cap_usd == pytest.approx(25_600.0)
        assert snap.ts_epoch == parse_utc("2026-06-26T08:19:16Z")
        assert snap.migration_ts_epoch == parse_utc("2026-06-26T08:02:26Z")
        assert snap.source_kind == "BUILD30_CANDIDATE_RECHECK"
        assert snap.source_file == "f.jsonl" and snap.source_line == 3
        # supply implied by mc/price is ~1B (real pump supply)
        assert snap.derived_supply() == pytest.approx(1e9, rel=1e-6)

    def test_falls_back_to_last_attempt_values(self):
        record = json.loads(json.dumps(BUILD30_RECORD))
        summary = record["market_attempt_summary"]
        summary["current_price"] = None
        summary["current_market_cap_usd"] = None
        summary["liquidity_usd"] = None
        snap = normalize_record(record)
        assert snap.price_usd == pytest.approx(8.418864888549567e-06)
        assert snap.market_cap_usd == pytest.approx(8418.864888513863)
        assert snap.liquidity_usd == pytest.approx(5859.308625941959)

    def test_watch_state_record_priceless(self):
        record = {"candidate_id": "cap1_CT5h", "token_mint": "C" * 44,
                  "seeded_at_utc": "2026-06-26T06:25:36Z",
                  "status": "SEEDED", "symbol_or_name": "WEN"}
        snap = normalize_record(record)
        assert snap is not None
        assert snap.price_usd is None and not snap.has_price
        assert snap.symbol == "WEN"

    def test_unusable_records_return_none(self):
        assert normalize_record({"no": "mint"}) is None
        assert normalize_record({"token_mint": "X" * 44}) is None  # no ts
        assert normalize_record(["not", "a", "dict"]) is None
        assert normalize_record(None) is None

    def test_nonpositive_prices_rejected(self):
        record = {"token_mint": "X" * 44, "observed_at_utc":
                  "2026-06-26T08:00:00Z", "current_price": "0"}
        snap = normalize_record(record)
        assert snap is not None and snap.price_usd is None


class TestLoaders:
    def test_load_snapshots_sorted_and_errors_captured(self, tmp_path):
        file_a = tmp_path / "a.jsonl"
        file_b = tmp_path / "b.jsonl"
        rec1 = {"token_mint": "M1" + "x" * 42,
                "observed_at_utc": "2026-06-26T08:10:00Z",
                "current_price": "0.1"}
        rec2 = {"token_mint": "M2" + "x" * 42,
                "observed_at_utc": "2026-06-26T08:00:00Z",
                "current_price": "0.2"}
        file_a.write_text(json.dumps(rec1) + "\n", encoding="utf-8")
        file_b.write_text(json.dumps(rec2) + "\nnot json{{{\n",
                          encoding="utf-8")
        snaps, errors = load_snapshots([str(tmp_path)])
        assert [s.mint[:2] for s in snaps] == ["M2", "M1"]  # time order
        assert len(errors) == 1 and errors[0]["kind"] == "PARSE_ERROR"

    def test_directory_and_file_inputs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        target = sub / "x.jsonl"
        target.write_text(json.dumps({
            "token_mint": "Z" * 44,
            "observed_at_utc": "2026-06-26T08:00:00Z"}) + "\n",
            encoding="utf-8")
        by_dir, _ = load_snapshots([str(tmp_path)])
        by_file, _ = load_snapshots([str(target)])
        assert len(by_dir) == len(by_file) == 1


class TestParsers:
    def test_parse_tier(self):
        assert parse_tier("Tier 2") == 2
        assert parse_tier("tier 3") == 3
        assert parse_tier(1) == 1
        assert parse_tier("Tier Unknown") is None
        assert parse_tier(None) is None
        assert parse_tier(True) is None

    def test_parse_pct_text(self):
        assert parse_pct_text("67.15%") == pytest.approx(67.15)
        assert parse_pct_text(42.5) == pytest.approx(42.5)
        assert parse_pct_text("bad") is None

    def test_parse_money_text(self):
        assert parse_money_text("$25.6k") == pytest.approx(25_600.0)
        assert parse_money_text("$1.2M") == pytest.approx(1_200_000.0)
        assert parse_money_text("$950") == pytest.approx(950.0)
        assert parse_money_text(123.0) == pytest.approx(123.0)
        assert parse_money_text("$") is None

    def test_parse_utc(self):
        assert parse_utc("2026-06-26T08:19:16Z") is not None
        assert parse_utc("2026-06-26T08:19:16+00:00") == \
            parse_utc("2026-06-26T08:19:16Z")
        assert parse_utc("nope") is None
        assert parse_utc(None) is None
