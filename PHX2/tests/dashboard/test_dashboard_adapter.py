"""Tests for the read-only PHX2 dashboard artifact adapter.

Covers: per-file parsing (producer + paper), missing-file tolerance,
malformed-JSONL tolerance, stale-heartbeat detection, and the
no-secret / no-env-display guarantees.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PHX2.dashboard import adapter

NOW = datetime(2026, 7, 9, 23, 0, 0, tzinfo=timezone.utc)

FAKE_WEBHOOK = "https://discord.com/api/webhooks/1234567890/FAKE_TEST_TOKEN_abcdef"
FAKE_KEYED_URL = "wss://example-rpc.test/?api-key=deadbeef-0000-1111-2222-333344445555"


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _credit_budget(**over):
    base = {
        "429_count": 0,
        "budget_stop_reason": None,
        "budget_stop_requested": False,
        "candidate_count": 2,
        "caps": {
            "max_429_total": 5,
            "max_candidates_total": 50,
            "max_gettransaction_total": 200,
            "max_market_requests_total": 300,
            "max_seed_windows": 10,
            "max_sends_per_run": 3,
            "max_ws_notifications_total": 120000,
        },
        "gettransaction_fetches": 4,
        "kind": "FREE_TIER_CREDIT_BUDGET",
        "market_requests": 1,
        "private_ping_count": 0,
        "rpc_errors_total": 0,
        "seed_windows": 5,
        "send_attempts": 0,
        "sent_ok_count": 0,
        "windows_blocked_by_budget": 0,
        "would_ping_count": 0,
        "ws_error_windows": 0,
        "ws_notifications_seen": 100000,
    }
    base.update(over)
    return base


def make_producer_dir(tmp_path: Path, *, hb_age_s=60.0, stop_reason=None,
                      budget_over=None, extra=None) -> Path:
    """Write a realistic minimal producer artifact dir (modeled on the real run)."""
    root = tmp_path / "producer"
    root.mkdir(parents=True, exist_ok=True)
    hb_ts = _iso(NOW - timedelta(seconds=hb_age_s))
    budget = _credit_budget(**(budget_over or {}))

    _write_json(root / "producer_summary.json", {
        "kind": "FREE_TIER_PRODUCER_SUMMARY",
        "mode": "FREE_TIER_PRIVATE_DISCORD",
        "outcome": "ZERO_SEND",
        "final": stop_reason is not None,
        "stop_reason": stop_reason,
        "error_count": 0,
        "credit_budget": budget,
        "ledger_delta_total": 0,
        "private_discord_enabled": True,
        "public_or_subscriber_routing": False,
        "wallet_signing_or_trading": False,
        "real_send_performed": False,
        "reseeds": 5,
        "ticks": 20,
        "updated_at_utc": hb_ts,
        "would_ping_count": 0,
        "watchlist_summary": {"by_status": {"DROPPED_NON_PUMP": 2, "WATCHING": 1}, "total": 3},
        "baseline_before": "e3b0c44298fc1c14:0:0",
        "baseline_after": "e3b0c44298fc1c14:0:0",
    })
    _write_json(root / "producer_heartbeat.json", {
        "kind": "PRODUCTION_LIVE_HEARTBEAT",
        "producer_mode": "FREE_TIER_PRIVATE_DISCORD",
        "private_discord_enabled": True,
        "tick": 20,
        "ts_utc": hb_ts,
        "stop_reason": stop_reason,
        "interrupted": False,
        "credit_budget": budget,
        "dedupe_suppressed_total": 0,
        "dropped_non_pump_total": 2,
        "error_count": 0,
        "market_calls_total": 1,
        "market_transport_stats": {
            "cache_hits": 1, "http_429": 0, "http_calls_total": 1,
            "http_errors": 0, "malformed_bodies": 0, "ohlcv_calls": 0,
            "pairs_calls": 1, "capped": 0, "fallback_used": 0,
        },
        "pricing_tail": {"tracked": 0},
        "reseeds_total": 5,
        "sends_total": 0,
        "watchlist_active": 1,
        "watchlist_by_status": {"DROPPED_NON_PUMP": 2, "WATCHING": 1},
        "watchlist_total": 3,
        "axiom_pass_total": 0,
        "axiom_fail_total": 1,
        "non_pump_guard_dropped_total": 2,
    })
    _write_jsonl(root / "heartbeat.jsonl", [
        {"kind": "PRODUCTION_LIVE_HEARTBEAT", "tick": 1,
         "ts_utc": _iso(NOW - timedelta(minutes=30)),
         "no_send_reasons": {"NO_SEND_MARKET_UNAVAILABLE": 1}},
        {"kind": "PRODUCTION_LIVE_HEARTBEAT", "tick": 20, "ts_utc": hb_ts,
         "no_send_reasons": {"NO_SEND_MARKET_UNAVAILABLE": 1}},
    ])
    _write_jsonl(root / "discovery_windows.jsonl", [
        {"kind": "FREE_TIER_DISCOVERY_WINDOW", "accepted_candidates": 0,
         "candidates": 0, "notifications_seen": 20000, "gettransaction_fetches": 0,
         "dup_signatures_skipped": 3, "null_fetches": 1, "rpc_errors": 0,
         "ws_error": False, "window_ended_at_utc": _iso(NOW - timedelta(minutes=25))},
        {"kind": "FREE_TIER_DISCOVERY_WINDOW", "accepted_candidates": 1,
         "candidates": 1, "notifications_seen": 20000, "gettransaction_fetches": 1,
         "dup_signatures_skipped": 0, "null_fetches": 0, "rpc_errors": 0,
         "ws_error": False, "window_ended_at_utc": _iso(NOW - timedelta(minutes=5))},
    ])
    _write_jsonl(root / "watch_state.jsonl", [
        {"candidate_id": "cap1_AAA", "status": "DROPPED_NON_PUMP",
         "last_reason": "DROPPED_NON_PUMP", "token_mint": "A" * 44,
         "seeded_at_utc": _iso(NOW - timedelta(minutes=40)),
         "migration_time_utc": _iso(NOW - timedelta(minutes=41)),
         "recheck_count": 0, "source_ref": "helius:sig:abc:slot:1"},
        {"candidate_id": "cap1_BBB", "status": "WATCHING",
         "last_reason": "NO_SEND_MARKET_UNAVAILABLE",
         "token_mint": "B" * 40 + "pump",
         "seeded_at_utc": _iso(NOW - timedelta(minutes=20)),
         "last_observed_at_utc": _iso(NOW - timedelta(minutes=19)),
         "migration_time_utc": _iso(NOW - timedelta(minutes=21)),
         "recheck_count": 1, "source_ref": "helius:sig:def:slot:2"},
    ])
    cand = {
        "candidate_id": "cap1_BBB",
        "kind": "BUILD30_CANDIDATE_RECHECK",
        "token_mint": "B" * 40 + "pump",
        "observed_at_utc": _iso(NOW - timedelta(minutes=19)),
        "migration_time_utc": _iso(NOW - timedelta(minutes=21)),
        "recheck_index": 1,
        "rejection_reason": "MARKET_UNAVAILABLE",
        "rejection_reason_raw": "NO_SEND_MARKET_UNAVAILABLE",
        "transport_attempted": False,
        "ledger_touched": False,
        "market_attempt_summary": {
            "basis": "REAL_MARKET_INCOMPLETE",
            "mc_present": False, "price_present": False, "lp_present": False,
            "current_market_cap_usd": None, "current_price": None,
            "liquidity_usd": None, "market_context_fetched_at_utc": None,
            "attempts": [{"basis": "REAL_MARKET_INCOMPLETE", "mc_value": "27044.08",
                          "price_value": "0.00002704", "lp_value": None}],
        },
        "lp_verify": {"lp_verify_status": "LP_VERIFY_UNKNOWN",
                      "lp_verify_reason": "INSUFFICIENT_EVENTS"},
    }
    _write_jsonl(root / "candidates" / "cap1_BBB.jsonl", [cand])
    _write_json(root / "redaction_scan.json", {
        "kind": "BUILD29_CAP1_REDACTION_SCAN",
        "redaction_status": "REDACTED",
        "total_unsafe_hits": 0,
        "positive_control_ok": True,
        "per_file_hits": {"watch_state.jsonl": []},
    })
    if extra:
        extra(root)
    return root


def make_paper_dir(tmp_path: Path, *, hb_age_s=60.0, extra=None) -> Path:
    root = tmp_path / "paper"
    root.mkdir(parents=True, exist_ok=True)
    hb_ts = _iso(NOW - timedelta(seconds=hb_age_s))

    def strat(name, **over):
        base = {
            "strategy_name": name, "closed_trades": 0, "open_trades": 0,
            "realized_pnl_usd": 0, "unrealized_pnl_usd": 0,
            "total_pnl_usd": 0, "total_pnl_pct": None, "win_rate_pct": None,
            "best_trade": None, "worst_trade": None, "skip_reasons": {},
            "skipped_trades": 0, "rugged_trades": 0, "data_lost_trades": 0,
            "max_drawdown_pct": 0.0, "starting_bankroll_usd": 1000.0,
            "ending_equity_usd": 1000.0,
        }
        base.update(over)
        return base

    _write_json(root / "heartbeat.json", {
        "artifact": "heartbeat", "heartbeat_utc": hb_ts, "mode": "LIVE_PAPER",
        "open_positions_total": 0, "run_id": "paper_run_x",
        "snapshots_processed": 4, "uptime_seconds": 2401.0,
        "watch_inputs": [r"C:\some\producer\out"],
    })
    _write_json(root / "live_monitor.json", {
        "artifact": "live_monitor", "as_of_utc": hb_ts,
        "last_error": "Expecting value: line 1 column 1 (char 0)",
        "last_skip": "monkey_hold BBB.. NO_LIQUIDITY_DATA",
        "run_id": "paper_run_x", "snapshots_processed": 4,
        "strategies": {
            "bala_plan": {"machine": {"machine_counts": {"DISCOVERED": 3}},
                          "open_positions": 0, "realized_pnl_usd": 0.0,
                          "unrealized_pnl_usd": 0},
        },
    })
    _write_json(root / "paper_summary.json", {
        "artifact": "paper_summary", "as_of_utc": hb_ts, "mode": "LIVE_PAPER",
        "run_id": "paper_run_x", "config_digest": "47fa1dc25522",
        "sol_price_usd": None,
        "strategies": {
            "bala_plan": strat("bala_plan"),
            "monkey_hold": strat("monkey_hold", skipped_trades=1,
                                 skip_reasons={"NO_LIQUIDITY_DATA": 1}),
        },
        "strategy_ranking": [
            {"rank": 1, "strategy_name": "bala_plan", "total_pnl_usd": 0.0,
             "total_pnl_pct": None, "win_rate_pct": None, "open_trades": 0,
             "closed_trades": 0, "skipped_trades": 0, "rugged_trades": 0,
             "data_lost_trades": 0, "max_drawdown_pct": 0.0},
            {"rank": 2, "strategy_name": "monkey_hold", "total_pnl_usd": 0.0,
             "total_pnl_pct": None, "win_rate_pct": None, "open_trades": 0,
             "closed_trades": 0, "skipped_trades": 1, "rugged_trades": 0,
             "data_lost_trades": 0, "max_drawdown_pct": 0.0},
        ],
    })
    _write_json(root / "strategy_comparison.json", {
        "artifact": "strategy_comparison", "as_of_utc": hb_ts,
        "run_id": "paper_run_x",
        "ranking": [{"rank": 1, "strategy_name": "bala_plan", "total_pnl_usd": 0.0,
                     "win_rate_pct": None, "open_trades": 0, "closed_trades": 0,
                     "skipped_trades": 0, "rugged_trades": 0,
                     "data_lost_trades": 0, "max_drawdown_pct": 0.0}],
    })
    _write_json(root / "paper_open_positions.json", {
        "as_of_utc": hb_ts, "run_id": "paper_run_x",
        "open_positions": [{
            "paper_trade_id": "bala_plan-00002-CCC", "strategy_name": "bala_plan",
            "mint": "C" * 44, "token_symbol": None,
            "opened_at_utc": _iso(NOW - timedelta(minutes=10)),
            "virtual_usd_size": 50.0, "entry_price": 0.001, "latest_price": 0.0012,
            "unrealized_pnl_usd": 10.0, "unrealized_pnl_pct": 20.0,
        }],
    })
    _write_jsonl(root / "paper_closed_positions.jsonl", [{
        "paper_trade_id": "bala_plan-00001-DDD", "strategy_name": "bala_plan",
        "mint": "D" * 44, "status": "CLOSED_TP",
        "closed_at_utc": _iso(NOW - timedelta(minutes=6)),
        "hold_seconds": 900.0, "realized_pnl_usd": 25.0, "realized_pnl_pct": 50.0,
        "max_up_pct": 60.0, "max_drawdown_pct": 5.0,
        "reason_closed": "TAKE_PROFIT", "tier": 2,
    }])
    _write_jsonl(root / "paper_positions.jsonl", [{
        "paper_trade_id": "monkey_hold-00001-BBB", "strategy_name": "monkey_hold",
        "mint": "B" * 40 + "pump", "status": "SKIPPED_LIQUIDITY_CAP",
        "closed_at_utc": _iso(NOW - timedelta(minutes=19)),
        "reason_closed": "NO_LIQUIDITY_DATA", "realized_pnl_usd": 0.0,
    }])
    _write_jsonl(root / "paper_equity_curve.jsonl", [
        {"strategy_name": "bala_plan", "equity_usd": 1000.0, "open_positions": 0,
         "realized_pnl_usd": 0.0, "unrealized_pnl_usd": 0, "ts_utc": hb_ts},
        {"strategy_name": "monkey_hold", "equity_usd": 1000.0, "open_positions": 0,
         "realized_pnl_usd": 0.0, "unrealized_pnl_usd": 0, "ts_utc": hb_ts},
    ])
    _write_jsonl(root / "paper_recent_events.jsonl", [
        {"event": "HEARTBEAT", "run_id": "paper_run_x",
         "snapshots_processed": 4, "ts_utc": hb_ts},
    ])
    _write_jsonl(root / "paper_errors.jsonl", [
        {"error": "Expecting value: line 1 column 1 (char 0)",
         "file": "C:\\x\\heartbeat.jsonl", "kind": "PARSE_ERROR", "line": 1,
         "run_id": "paper_run_x"},
    ])
    if extra:
        extra(root)
    return root


def build(tmp_path, *, producer_kw=None, paper_kw=None, ledger_path=None):
    producer = make_producer_dir(tmp_path, **(producer_kw or {}))
    paper = make_paper_dir(tmp_path, **(paper_kw or {}))
    return adapter.build_bundle(producer, paper, ledger_path=ledger_path, now=NOW)


# ─── producer artifact parsing ───────────────────────────────────────────────

def test_producer_summary_parsing_maps_discord_block(tmp_path):
    bundle = build(tmp_path, producer_kw={"stop_reason": "MAX_RUNTIME"})
    dis = bundle["paper"]["discord"]
    assert dis["enabled"] == "YES"
    assert dis["last_ping_result"] == "NO_ELIGIBLE_CANDIDATE"
    assert dis["private_ping_count"] == 0
    assert dis["would_ping_count"] == 0
    assert dis["max_sends_per_run"] == 3
    assert dis["ledger_delta_total"] == 0
    assert dis["public_or_subscriber_routing"] is False


def test_discord_risk_gate_block_counters_and_blocked_candidates(tmp_path):
    # Producer risk gate blocked 2 HIGH + 1 weak-MEDIUM candidate from private Discord dispatch;
    # the dashboard must surface the counters, the mapped reasons, the blocked-candidate rows,
    # and the "Discord blocked" vs "Paper skipped" distinction.
    producer = tmp_path / "prod_block"
    producer.mkdir()
    paper = tmp_path / "paper_block"
    paper.mkdir()
    _write_json(producer / "producer_heartbeat.json", {
        "private_discord_enabled": True,
        "discovery_mode": "HYBRID",
        "risk_summary": {"by_label": {"RISK_HIGH": 2, "RISK_MEDIUM": 1,
                                      "RISK_LOW": 0, "RISK_UNKNOWN": 0}},
        "risk_discord_block": {
            "kind": "FREE_TIER_DISCORD_BLOCK_SUMMARY",
            "high_risk_discord_block_count": 2,
            "medium_risk_structure_block_count": 1,
            "high_risk_blocked_mints": ["AhotPoolMint1111111111111111111111111pump",
                                        "BcollapseMint111111111111111111111111pump"],
            "medium_risk_blocked_mints": ["CweakMint11111111111111111111111111111pump"],
            "high_risk_block_reason_counts": {"HIGH_RISK_TOO_HOT": 1,
                                              "HIGH_RISK_LIQUIDITY_COLLAPSE": 1},
            "medium_risk_block_reason_counts": {"MEDIUM_RISK_LP_TOO_LOW": 1},
        },
    })
    _write_jsonl(producer / "discord_blocks.jsonl", [
        {"kind": "FREE_TIER_DISCORD_BLOCK",
         "token_mint": "AhotPoolMint1111111111111111111111111pump",
         "terminal_decision": "SKIPPED_HIGH_RISK_DISCORD", "mapped_reason": "HIGH_RISK_TOO_HOT",
         "risk_label": "RISK_HIGH", "risk_reasons": ["POOL_TOO_HOT"],
         "market_context": {"liquidity_usd": "21000", "current_market_cap_usd": "70000"},
         "blocked_at_utc": "2026-07-12T01:17:45Z"},
        {"kind": "FREE_TIER_DISCORD_BLOCK",
         "token_mint": "CweakMint11111111111111111111111111111pump",
         "terminal_decision": "SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE",
         "mapped_reason": "MEDIUM_RISK_LP_TOO_LOW", "risk_label": "RISK_MEDIUM",
         "risk_reasons": ["LP_THIN"],
         "market_context": {"liquidity_usd": "8000", "current_market_cap_usd": "45000"},
         "blocked_at_utc": "2026-07-12T01:18:00Z"},
    ])
    bundle = adapter.build_bundle(str(producer), str(paper), now=NOW)
    rp = bundle["paper"]["trading"]["risk_protection"]
    assert rp["discord_high_risk_block_count"] == 2
    assert rp["discord_medium_structure_block_count"] == 1
    assert rp["discord_high_risk_block_reasons"]["HIGH_RISK_TOO_HOT"] == 1
    assert rp["discord_high_risk_block_reasons"]["HIGH_RISK_LIQUIDITY_COLLAPSE"] == 1
    assert rp["discord_medium_block_reasons"]["MEDIUM_RISK_LP_TOO_LOW"] == 1
    rows = rp["discord_blocked_candidates"]
    assert len(rows) == 2
    assert any(r["terminal_decision"] == "SKIPPED_HIGH_RISK_DISCORD"
               and r["mapped_reason"] == "HIGH_RISK_TOO_HOT"
               and r["risk_label"] == "RISK_HIGH" for r in rows)
    assert any(r["terminal_decision"] == "SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE" for r in rows)
    # "Discord blocked" vs "Paper skipped" distinction is surfaced
    assert "Discord blocked" in rp["discord_vs_paper_note"]
    assert "Paper skipped" in rp["discord_vs_paper_note"]
    # counters also appear on the Discord card
    dis = bundle["paper"]["discord"]
    assert dis["high_risk_discord_block_count"] == 2
    assert dis["medium_risk_structure_block_count"] == 1


def test_producer_heartbeat_parsing_maps_discovery_counters(tmp_path):
    bundle = build(tmp_path)
    dv = bundle["paper"]["discovery"]
    assert dv["ws_notifications_seen"] == 100000
    assert dv["seed_windows"] == 5
    assert dv["candidate_count"] == 2
    assert dv["watch_total"] == 3
    assert dv["watch_by_status"] == {"DROPPED_NON_PUMP": 2, "WATCHING": 1}
    assert dv["gettransaction_fetches"] == 4
    assert dv["rpc_429_count"] == 0
    assert dv["market_http_429"] == 0
    assert dv["budget_stop_reason"] is None
    assert dv["axiom_fail_total"] == 1
    assert dv["remaining"]["ws_notifications"] == 20000
    assert dv["remaining"]["sends"] == 3
    assert dv["non_pump_guard_dropped"] == 2  # pre-watchlist strict suffix guard


def test_heartbeat_jsonl_no_send_reasons_are_summed(tmp_path):
    bundle = build(tmp_path)
    dv = bundle["paper"]["discovery"]
    assert dv["no_send_reasons"] == {"NO_SEND_MARKET_UNAVAILABLE": 2}
    assert bundle["paper"]["discord"]["last_no_ping_reason"].startswith(
        "NO_SEND_MARKET_UNAVAILABLE")


def test_discovery_windows_jsonl_parsing(tmp_path):
    bundle = build(tmp_path)
    dv = bundle["paper"]["discovery"]
    assert dv["windows_recorded"] == 2
    assert dv["dup_signatures_skipped"] == 3
    assert dv["null_fetches"] == 1


def test_watch_state_and_candidate_parsing(tmp_path):
    bundle = build(tmp_path)
    queue = bundle["candidates"]["queue"]
    assert len(queue) == 2
    by_id = {c["id"]: c for c in queue}
    watching = by_id["cap1_BBB"]
    assert watching["stage"] == "WAITING_FOR_PRICE"
    assert watching["filters"] == "MARKET_UNAVAILABLE"
    assert watching["mcap"] == "$27.0K"  # from last market attempt mc_value
    assert watching["recheckCount"] == 1
    dropped = by_id["cap1_AAA"]
    assert dropped["stage"] == "DEAD"
    assert "Non-pump" in dropped["blocker"]


def test_market_indexing_state_is_visible_and_remains_scheduled():
    producer = {
        "watch": {
            "paid-1": {
                "candidate_id": "paid-1", "status": "WATCHING",
                "last_reason": "NO_SEND_MARKET_INDEXING",
                "market_state": "MARKET_INDEXING",
                "market_reason_code": "MARKET_CAP_MISSING",
                "next_market_refresh_at_utc": _iso(NOW + timedelta(seconds=20)),
                "market_attempt_count": 2,
                "token_mint": "B" * 40 + "pump",
                "seeded_at_utc": _iso(NOW - timedelta(minutes=2)),
            },
        },
        "candidates": {
            "paid-1": {"last": {
                "rejection_reason": "MARKET_INDEXING",
                "rejection_reason_raw": "NO_SEND_MARKET_INDEXING",
                "market_attempt_summary": {"market_state": "MARKET_INDEXING"},
            }},
        },
    }
    row = adapter.build_candidate_rows(producer, NOW)[0]
    assert row["stage"] == "WAITING_FOR_PRICE"
    assert row["marketState"] == "MARKET_INDEXING"
    assert row["marketReasonCode"] == "MARKET_CAP_MISSING"
    assert row["marketAttemptCount"] == 2
    assert "Refresh remains scheduled" in row["nextCondition"]


def test_effective_reserve_discrepancy_telemetry_is_visible_but_not_routing_authority():
    mint = "B" * 40 + "pump"
    producer = {
        "watch": {
            "paid-1": {
                "candidate_id": "paid-1", "status": "WATCHING",
                "token_mint": mint,
                "seeded_at_utc": _iso(NOW - timedelta(minutes=2)),
            },
        },
        "candidates": {
            "paid-1": {"last": {
                "market_attempt_summary": {
                    "pumpswap_reserve": {
                        "reserve_validation_status": "VALID",
                        "comparison_status": "PRICE_DISCREPANCY",
                        "reserve_trusted_for_routing": False,
                        "effective_reserve_price_usd": "0.0002",
                        "effective_reserve_market_cap_usd": "200000",
                        "effective_reserve_liquidity_usd": "40000",
                        "effective_reserve_ath_price_usd": "0.0003",
                        "effective_reserve_drawdown_pct": "33.333",
                        "price_discrepancy_pct": "25",
                        "reserve_artifact": {
                            "raw_quote_reserves": "100",
                            "virtual_quote_reserves": "25",
                            "effective_quote_reserves": "125",
                            "base_reserves": "1000",
                            "reserve_source": "PUMPSWAP_BUY_EVENT",
                            "observation_timestamp": "2026-07-15T12:00:00Z",
                            "decoder_layout_version": "PUMPSWAP_BUY_EVENT_VIRTUAL_QUOTE_I128_V2",
                        },
                    },
                },
            }},
        },
    }
    row = adapter.build_candidate_rows(producer, NOW)[0]
    assert row["reserveComparisonStatus"] == "PRICE_DISCREPANCY"
    assert row["rawQuoteReserves"] == "100"
    assert row["virtualQuoteReserves"] == "25"
    assert row["effectiveQuoteReserves"] == "125"
    assert row["reservePriceDiscrepancyPct"] == "25"
    assert row["reserveTrustedForRouting"] is False


def test_decisions_built_from_rechecks_drops_and_seeds(tmp_path):
    bundle = build(tmp_path)
    decisions = bundle["decisions"]["decisions"]
    kinds = {(d["decision"], d["reason"]) for d in decisions}
    assert ("SKIP", "MARKET_UNAVAILABLE") in kinds
    assert ("SKIP", "NON_PUMP") in kinds
    assert ("CANDIDATE", "SEEDED_PUMP_MIGRATION") in kinds
    skip = next(d for d in decisions if d["reason"] == "MARKET_UNAVAILABLE")
    assert skip["knew"], "knew[] must carry the reasoning snapshot"
    assert skip["dataQuality"] in ("PARTIAL", "MISSING_LP")


def test_would_and_sent_ping_records_parsed_when_present(tmp_path):
    def extra(root):
        _write_jsonl(root / "would_ping_records.jsonl", [
            {"token_mint": "E" * 44, "reason": "DIP_GATE_PASS",
             "observed_at_utc": _iso(NOW - timedelta(minutes=3))},
        ])
        _write_jsonl(root / "sent_ping_records.jsonl", [
            {"token_mint": "F" * 44, "result": "SENT_OK",
             "sent_at_utc": _iso(NOW - timedelta(minutes=2))},
        ])
    bundle = build(tmp_path, producer_kw={"extra": extra})
    decisions = bundle["decisions"]["decisions"]
    assert any(d["decision"] == "WOULD_ALERT" for d in decisions)
    assert any(d["decision"] == "SENT" for d in decisions)
    dis = bundle["paper"]["discord"]
    assert dis["last_would_ping"] != "—"
    assert dis["last_sent_ping"] != "—"
    tables = bundle["paper"]["tables"]
    assert len(tables["would_pings"]) == 1
    assert len(tables["sent_pings"]) == 1
    assert tables["sent_pings"][0]["result"] == "SENT_OK"


def test_producer_errors_jsonl_parsed_when_present(tmp_path):
    def extra(root):
        _write_jsonl(root / "errors.jsonl", [
            {"kind": "WS_ERROR", "error": "connection reset"},
        ])
    bundle = build(tmp_path, producer_kw={"extra": extra})
    errors = bundle["paper"]["tables"]["errors"]
    assert any(e["source"] == "producer" and e["kind"] == "WS_ERROR" for e in errors)


# ─── paper artifact parsing ──────────────────────────────────────────────────

def test_paper_summary_parsing_totals_and_skips(tmp_path):
    bundle = build(tmp_path)
    tr = bundle["paper"]["trading"]
    assert tr["open_positions"] == 0
    assert tr["closed_positions"] == 0
    assert tr["skip_reasons"] == {"NO_LIQUIDITY_DATA": 1}
    assert tr["last_skip"].endswith("NO_LIQUIDITY_DATA")
    assert tr["config_digest"] == "47fa1dc25522"
    assert tr["bala_machine"] == {"DISCOVERED": 3}


def test_strategy_comparison_ranking_rows(tmp_path):
    bundle = build(tmp_path)
    rows = bundle["paper"]["trading"]["strategies"]
    assert [r["name"] for r in rows] == ["bala_plan", "monkey_hold"]
    assert rows[0]["rank"] == 1
    assert rows[1]["skipped"] == 1
    assert rows[0]["equity"] == "$1,000.00"


def test_paper_open_positions_parsing(tmp_path):
    bundle = build(tmp_path)
    rows = bundle["paper"]["tables"]["open_positions"]
    assert len(rows) == 1
    assert rows[0]["strategy"] == "bala_plan"
    assert rows[0]["unrealized"] == "$10.00"


def test_paper_closed_positions_jsonl_to_outcomes(tmp_path):
    bundle = build(tmp_path)
    outcomes = bundle["outcomes"]["outcomes"]
    assert len(outcomes) == 1
    out = outcomes[0]
    assert out["status"] == "HIT"          # realized_pnl_pct > 0
    assert out["decision"] == "PAPER_TRADE"
    assert out["reason"] == "TAKE_PROFIT"
    closed_rows = bundle["paper"]["tables"]["closed_positions"]
    assert closed_rows and closed_rows[0]["pnl_usd"] == "$25.00"


def test_paper_equity_curve_summary(tmp_path):
    bundle = build(tmp_path)
    eq = bundle["paper"]["trading"]["equity_summary"]
    assert {e["strategy"] for e in eq} == {"bala_plan", "monkey_hold"}
    assert all(e["points"] == 1 for e in eq)


def test_paper_recent_events_and_errors_tables(tmp_path):
    bundle = build(tmp_path)
    tables = bundle["paper"]["tables"]
    assert any(e["event"] == "HEARTBEAT" for e in tables["events"])
    assert any(e["source"] == "paper" and e["kind"] == "PARSE_ERROR"
               for e in tables["errors"])
    assert any(s["reason"] == "NO_LIQUIDITY_DATA" for s in tables["skips"])


# ─── tolerance: missing files, malformed lines ───────────────────────────────

def test_missing_everything_does_not_crash(tmp_path):
    empty_a = tmp_path / "no_producer"
    empty_b = tmp_path / "no_paper"
    bundle = adapter.build_bundle(empty_a, empty_b, now=NOW)
    assert bundle["paper"]["system"]["producer"]["status"] == "UNKNOWN"
    assert bundle["paper"]["system"]["paper"]["status"] == "UNKNOWN"
    assert bundle["candidates"]["queue"] == []
    assert bundle["decisions"]["decisions"] == []
    assert bundle["outcomes"]["outcomes"] == []
    assert bundle["live"]["liveFeed"] == []
    assert bundle["paper"]["discord"]["enabled"] == "UNKNOWN"
    # file inventory reports absence rather than crashing
    assert bundle["meta"]["producer_files"]["producer_summary.json"]["present"] is False


def test_malformed_jsonl_lines_are_skipped_and_counted(tmp_path):
    def extra(root):
        path = root / "watch_state.jsonl"
        good = path.read_text(encoding="utf-8")
        path.write_text("{not valid json}\n" + good + "ALSO NOT JSON\n",
                        encoding="utf-8")
    bundle = build(tmp_path, producer_kw={"extra": extra})
    # both good rows survive, two bad lines counted
    assert len(bundle["candidates"]["queue"]) == 2
    assert bundle["meta"]["skipped_lines"]["producer"]["watch_state.jsonl"] == 2


def test_read_json_missing_and_malformed(tmp_path):
    obj, err = adapter.read_json(tmp_path / "nope.json")
    assert obj is None and err == "MISSING"
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    obj, err = adapter.read_json(bad)
    assert obj is None and err and err.startswith("UNREADABLE")


def test_read_jsonl_missing_returns_empty(tmp_path):
    records, skipped, err = adapter.read_jsonl(tmp_path / "nope.jsonl")
    assert records == [] and skipped == 0 and err == "MISSING"


# ─── stale heartbeat detection ───────────────────────────────────────────────

def test_status_running_when_fresh(tmp_path):
    bundle = build(tmp_path, producer_kw={"hb_age_s": 30.0},
                   paper_kw={"hb_age_s": 30.0})
    assert bundle["paper"]["system"]["producer"]["status"] == "RUNNING"
    assert bundle["paper"]["system"]["paper"]["status"] == "RUNNING"


def test_status_stale_when_heartbeat_old(tmp_path):
    bundle = build(tmp_path, producer_kw={"hb_age_s": 3600.0},
                   paper_kw={"hb_age_s": 3600.0})
    assert bundle["paper"]["system"]["producer"]["status"] == "STALE"
    assert bundle["paper"]["system"]["paper"]["status"] == "STALE"


def test_status_stopped_when_stop_reason_present(tmp_path):
    bundle = build(tmp_path, producer_kw={"stop_reason": "MAX_RUNTIME",
                                          "hb_age_s": 30.0})
    prod = bundle["paper"]["system"]["producer"]
    assert prod["status"] == "STOPPED"
    assert prod["stop_reason"] == "MAX_RUNTIME"


def test_compute_status_unit():
    assert adapter.compute_status(None)[0] == "UNKNOWN"
    assert adapter.compute_status(10.0)[0] == "RUNNING"
    assert adapter.compute_status(10_000.0)[0] == "STALE"
    assert adapter.compute_status(10.0, stop_reason="MAX_RUNTIME")[0] == "STOPPED"


# ─── secrets / redaction ─────────────────────────────────────────────────────

def test_redact_text_patterns():
    assert "REDACTED_WEBHOOK" in adapter.redact_text(FAKE_WEBHOOK)
    assert "deadbeef" not in adapter.redact_text(FAKE_KEYED_URL)
    assert "[REDACTED]" in adapter.redact_text("api_key=super_secret_value")
    assert "hunter2" not in adapter.redact_text("Authorization: Bearer hunter2aaaa")


def test_secret_named_keys_are_redacted_in_bundle(tmp_path):
    def extra(root):
        _write_jsonl(root / "errors.jsonl", [
            {"kind": "CONFIG_ECHO", "webhook_url": FAKE_WEBHOOK,
             "api_key": "sk-fake-123456", "detail": f"failed POST {FAKE_WEBHOOK}"},
        ])
    bundle = build(tmp_path, producer_kw={"extra": extra})
    text = json.dumps(bundle)
    assert "discord.com/api/webhooks" not in text
    assert "sk-fake-123456" not in text
    assert "FAKE_TEST_TOKEN" not in text
    assert "[REDACTED" in text


def test_env_files_are_never_read(tmp_path):
    secret = "SUPER_SECRET_ENV_VALUE_a1b2c3"

    def extra(root):
        (root / ".env").write_text(f"PHX2_WEBHOOK_URL={secret}\n", encoding="utf-8")
        (root / "phx2.env").write_text(f"API_KEY={secret}\n", encoding="utf-8")
    bundle = build(tmp_path, producer_kw={"extra": extra})
    text = json.dumps(bundle)
    assert secret not in text
    # .env is not even in the file inventory (not allowlisted)
    assert ".env" not in bundle["meta"]["producer_files"]


def test_bundle_contains_no_keyed_urls_from_artifacts(tmp_path):
    def extra(root):
        # a hostile artifact line that embeds a keyed URL in a normal field
        _write_jsonl(root / "errors.jsonl", [
            {"kind": "WS_ERROR", "error": f"connect failed to {FAKE_KEYED_URL}"},
        ])
    bundle = build(tmp_path, producer_kw={"extra": extra})
    assert "deadbeef-0000" not in json.dumps(bundle)


def test_ledger_line_count_only(tmp_path):
    ledger = tmp_path / "ping_dedupe.jsonl"
    ledger.write_text('{"mint": "M1"}\n{"mint": "M2"}\n', encoding="utf-8")
    before = ledger.read_bytes()
    bundle = build(tmp_path, ledger_path=str(ledger))
    assert bundle["paper"]["discord"]["ledger_lines"] == 2
    # adapter must not mutate the ledger
    assert ledger.read_bytes() == before
    # ledger contents are not leaked into the bundle
    assert "M1" not in json.dumps(bundle["paper"]["discord"])


# ─── page bundles hold together ──────────────────────────────────────────────

def test_live_page_contract_shape(tmp_path):
    bundle = build(tmp_path, producer_kw={"stop_reason": "MAX_RUNTIME"})
    live = bundle["live"]
    for key in ("bot", "db", "provider", "priceApi", "discord", "lastEvent",
                "lastWrite", "queue", "dedupe", "rawCap"):
        item = live["feedStatus"][key]
        assert set(item) >= {"label", "value", "tone"}
    assert isinstance(live["delta"], list) and live["delta"]
    assert live["dexTrending"] == []
    assert "STOPPED" in live["feedStatus"]["bot"]["value"]


def test_runs_page_has_producer_and_paper_runs(tmp_path):
    bundle = build(tmp_path, producer_kw={"stop_reason": "MAX_RUNTIME"})
    runs = bundle["runs"]["runs"]
    assert len(runs) == 2
    producer_run = runs[0]
    assert producer_run["stage"] == "Producer"
    assert producer_run["status"] == "PASS"
    assert producer_run["artifactsList"], "real artifact list expected"
    names = {a["name"] for a in producer_run["artifactsList"]}
    assert "producer_summary.json" in names
    stage_status = {s["id"]: s["statusLabel"] for s in bundle["runs"]["stages"]}
    assert stage_status["PROD"] == "Stopped"


# ─── polish pass: full CA / copyability ──────────────────────────────────────

FULL_MINT_B = "B" * 40 + "pump"


def test_full_ca_preserved_in_adapter_output(tmp_path):
    def extra(root):
        _write_jsonl(root / "would_ping_records.jsonl", [
            {"token_mint": "E" * 44, "reason": "DIP_GATE_PASS",
             "observed_at_utc": _iso(NOW - timedelta(minutes=3))},
        ])
        _write_jsonl(root / "sent_ping_records.jsonl", [
            {"token_mint": "F" * 44, "result": "SENT_OK",
             "sent_at_utc": _iso(NOW - timedelta(minutes=2))},
        ])
    bundle = build(tmp_path, producer_kw={"extra": extra})

    # candidates page rows carry the exact full mint
    watching = next(c for c in bundle["candidates"]["queue"] if c["id"] == "cap1_BBB")
    assert watching["mint"] == FULL_MINT_B
    # live feed rows
    feed = bundle["live"]["liveFeed"]
    assert any(r.get("mint") == FULL_MINT_B for r in feed)
    # decisions ledger rows + live strip
    assert all("mint" in d for d in bundle["decisions"]["decisions"])
    assert any(d["mint"] == FULL_MINT_B for d in bundle["decisions"]["decisions"])
    assert any(s.get("mint") for s in bundle["live"]["decisions"])
    # outcomes rows
    assert all(o.get("mint") for o in bundle["outcomes"]["outcomes"])
    # paper tables
    tables = bundle["paper"]["tables"]
    assert any(c.get("mint") == FULL_MINT_B for c in tables["candidates"])
    assert tables["would_pings"][0]["mint"] == "E" * 44
    assert tables["sent_pings"][0]["mint"] == "F" * 44
    assert tables["open_positions"][0]["mint"] == "C" * 44
    assert tables["closed_positions"][0]["mint"] == "D" * 44
    assert tables["skips"][0]["mint"] == FULL_MINT_B


def test_short_display_always_has_full_copy_value(tmp_path):
    """Any row that displays a shortened mint must carry the full value."""
    bundle = build(tmp_path)
    rows = (bundle["candidates"]["queue"] + bundle["live"]["liveFeed"]
            + bundle["decisions"]["decisions"] + bundle["outcomes"]["outcomes"]
            + bundle["paper"]["tables"]["candidates"])
    shortened = [r for r in rows if "…" in str(r.get("tokenSub", ""))]
    assert shortened, "fixture should produce shortened displays"
    for row in shortened:
        assert row.get("mint"), f"shortened row without full mint: {row.get('tokenSub')}"
        assert "…" not in row["mint"]


def test_missing_ca_does_not_crash(tmp_path):
    def extra(root):
        _write_jsonl(root / "watch_state.jsonl", [
            {"candidate_id": "cap1_NOMINT", "status": "WATCHING",
             "last_reason": None, "token_mint": None,
             "seeded_at_utc": _iso(NOW - timedelta(minutes=5)),
             "migration_time_utc": _iso(NOW - timedelta(minutes=6)),
             "recheck_count": 0, "source_ref": "helius:sig:x:slot:9"},
        ])
    bundle = build(tmp_path, producer_kw={"extra": extra})
    row = next(c for c in bundle["candidates"]["queue"] if c["id"] == "cap1_NOMINT")
    assert row["token"] == "—" and row["mint"] is None  # renders, no crash


# ─── polish pass: $1,000 strategy baseline ───────────────────────────────────

def test_strategy_defaults_to_1000_starting_equity(tmp_path):
    def extra(root):
        _write_json(root / "paper_summary.json", {
            "artifact": "paper_summary", "run_id": "paper_run_x",
            "as_of_utc": _iso(NOW - timedelta(seconds=30)),
            "strategies": {
                "bare_plan": {"strategy_name": "bare_plan",
                              "realized_pnl_usd": 25.0, "unrealized_pnl_usd": 5.0},
            },
            "strategy_ranking": [
                {"rank": 1, "strategy_name": "bare_plan", "total_pnl_usd": None,
                 "total_pnl_pct": None, "win_rate_pct": None},
            ],
        })
    bundle = build(tmp_path, paper_kw={"extra": extra})
    row = bundle["paper"]["trading"]["strategies"][0]
    assert row["starting"] == "$1,000.00"        # default baseline
    assert row["equity"] == "$1,030.00"          # 1000 + 25 + 5
    assert row["realized"] == "$25.00"
    assert row["unrealized"] == "$5.00"
    assert row["total"] == "$30.00"
    assert row["return_pct"] == "+3.0%"


def test_strategy_uses_artifact_starting_equity_when_present(tmp_path):
    bundle = build(tmp_path)
    rows = bundle["paper"]["trading"]["strategies"]
    for row in rows:
        assert row["starting"] == "$1,000.00"    # from starting_bankroll_usd
        assert row["equity"] == "$1,000.00"      # from ending_equity_usd
        assert row["total"] == "$0.00"
        assert row["return_pct"] == "0.0%"


# ─── polish pass: entries / exits detail ─────────────────────────────────────

def test_open_entries_fields(tmp_path):
    bundle = build(tmp_path)
    row = bundle["paper"]["tables"]["open_positions"][0]
    assert row["opened_abs"] != "—"
    assert row["cost"] == "$50.00"
    assert row["value"] == "$60.00"              # cost + unrealized
    assert row["unrealized"] == "$10.00"
    assert row["state"]                          # SCOUT/DCA/leg or open reason
    assert row["mint"] == "C" * 44


def test_closed_exits_fields(tmp_path):
    bundle = build(tmp_path)
    row = bundle["paper"]["tables"]["closed_positions"][0]
    assert row["reason"] == "TAKE_PROFIT"
    assert row["pnl_usd"] == "$25.00"
    assert row["pnl_pct"] == "+50.0%"
    assert row["closed_abs"] != "—"
    assert "entry_price" in row and "exit_price" in row and "tokens" in row


# ─── polish pass: no continuous animations in the shell ──────────────────────

STATIC_DIR = Path(adapter.__file__).resolve().parent / "static"


def test_no_banner_animation_classes_remain():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for needle in ("emberRiseFull", "emberRise", "phoenixSweep", "phoenixBob",
                   "pulseRing", "topbar-embers", "infinite"):
        assert needle not in html, f"continuous-animation artifact remains: {needle}"
    # only the one-shot drawer entrance animations may remain
    remaining = [line for line in html.splitlines() if "animation:" in line]
    assert all(("cdSlideIn" in line or "cdFadeIn" in line) for line in remaining)

    app = (STATIC_DIR / "app.jsx").read_text(encoding="utf-8")
    for needle in ("<TopBarEmbers", "phoenix-fly", "<Embers"):
        assert needle not in app, f"animated banner component still rendered: {needle}"


def test_copy_ca_component_exists_and_pages_use_it():
    data_adapter = (STATIC_DIR / "data-adapter.jsx").read_text(encoding="utf-8")
    assert "function CopyCA" in data_adapter
    assert "Copy CA" in data_adapter and "Copied" in data_adapter
    for page in ("live-page.jsx", "paper-page.jsx", "candidates-page.jsx",
                 "decisions-page.jsx", "outcomes-page.jsx"):
        text = (STATIC_DIR / page).read_text(encoding="utf-8")
        assert "CopyCA" in text, f"{page} missing CopyCA usage"


def test_no_eligible_candidate_acceptance_values(tmp_path):
    """The acceptance snapshot: armed run, discord on, zero sends."""
    bundle = build(tmp_path, producer_kw={"stop_reason": "MAX_RUNTIME"})
    dis = bundle["paper"]["discord"]
    dv = bundle["paper"]["discovery"]
    assert dis["enabled"] == "YES"
    assert dis["last_ping_result"] == "NO_ELIGIBLE_CANDIDATE"
    assert dis["private_ping_count"] == 0 and dis["would_ping_count"] == 0
    assert dv["rpc_429_count"] == 0 and dv["market_http_429"] == 0
    assert dv["watch_total"] == 3
    skips = bundle["paper"]["trading"]["skip_reasons"]
    assert skips.get("NO_LIQUIDITY_DATA") == 1


# ─── 2026-07-10: discovery mode, polling counters, raw-WS semantics, freshness ─

POLLING_BLOCK = {
    "poll_count": 12, "polls_blocked_by_budget": 0, "pools_listed": 240,
    "pools_new": 9, "signatures_seen": 8100, "signatures_new": 9,
    "transactions_fetched": 9, "create_pool_candidates": 4,
    "pump_suffix_accepted": 3, "non_pump_guard_dropped": 1,
    "pools_skipped_too_hot": 2, "polling_errors": 1, "polling_429": 0,
}

FRESHNESS_BLOCK = {
    "market_data_fresh_count": 2, "market_data_stale_count": 1,
    "market_unavailable_count": 1,
    "last_successful_market_refresh_at": "2026-07-09T22:58:30Z",
    "last_market_error": "FETCH_MISS",
    "refresh_success_total": 40, "refresh_miss_total": 6,
    "fresh_within_seconds": 300.0,
    "per_mint": [
        {"token_mint": "B" * 40 + "pump", "origin": "WATCHLIST", "status": "FRESH",
         "last_success_age_s": 30.0, "records": 20, "misses": 1},
        {"token_mint": "E" * 40 + "pump", "origin": "WOULD_PING", "status": "UNAVAILABLE",
         "last_success_age_s": None, "records": 0, "misses": 6},
    ],
}


def _new_semantics_heartbeat(root, *, discovery_mode="POLLING", budget_over=None):
    """Overwrite producer_heartbeat.json with the 2026-07-10 producer fields."""
    hb_ts = _iso(NOW - timedelta(seconds=60))
    budget = _credit_budget(**(budget_over or {}))
    budget["polling"] = dict(POLLING_BLOCK)
    budget["raw_ws_notifications_seen"] = budget["ws_notifications_seen"]
    budget["raw_ws_notifications_are_not_helius_credits"] = True
    budget["raw_ws_cap_note"] = "raw WS notifications are not Helius dashboard credits"
    _write_json(root / "producer_heartbeat.json", {
        "kind": "PRODUCTION_LIVE_HEARTBEAT",
        "producer_mode": "FREE_TIER_PRIVATE_DISCORD",
        "private_discord_enabled": True,
        "discovery_mode": discovery_mode,
        "raw_ws_cap_note": "raw WS notifications are not Helius dashboard credits",
        "tick": 21, "ts_utc": hb_ts, "stop_reason": None, "interrupted": False,
        "credit_budget": budget,
        "market_freshness": dict(FRESHNESS_BLOCK),
        "market_scheduler": {
            "queue": 7, "in_flight": 2, "workers": 2,
            "oldest_deadline_age_seconds": 3.5, "slo_breached": False,
            "price_batches": 0, "overview_calls": 11,
            "requests_avoided_by_grpc": 19, "late_results_rejected": 1,
        },
        "pricing_tail": {"tracked": 4, "tracked_by_origin": {"WATCHLIST": 3,
                                                             "WOULD_PING": 1}},
        "market_transport_stats": {
            "cache_hits": 1, "http_429": 0, "http_calls_total": 9, "http_errors": 0,
            "malformed_bodies": 0, "ohlcv_calls": 0, "pairs_calls": 9, "capped": 0,
            "fallback_used": 0,
        },
        "reseeds_total": 12, "sends_total": 0,
        "watchlist_active": 1, "watchlist_total": 3,
        "watchlist_by_status": {"DROPPED_NON_PUMP": 2, "WATCHING": 1},
        "dropped_non_pump_total": 2, "non_pump_guard_dropped_total": 2,
        "dedupe_suppressed_total": 0, "error_count": 0, "market_calls_total": 9,
    })


def test_discovery_mode_and_polling_counters_surfaced(tmp_path):
    bundle = build(tmp_path, producer_kw={"extra": _new_semantics_heartbeat})
    dv = bundle["paper"]["discovery"]
    assert dv["discovery_mode"] == "POLLING"
    for key, want in (("poll_count", 12), ("signatures_seen", 8100),
                      ("signatures_new", 9), ("transactions_fetched", 9),
                      ("create_pool_candidates", 4), ("pump_suffix_accepted", 3),
                      ("non_pump_guard_dropped", 1), ("polling_errors", 1),
                      ("polling_429", 0)):
        assert dv["polling"][key] == want, (key, dv["polling"])
    live = bundle["live"]
    assert "POLLING" in live["feedStatus"]["provider"]["label"]
    assert "12" in live["feedStatus"]["provider"]["value"]
    labels = {d["label"]: d["value"] for d in live["delta"]}
    assert labels.get("Discovery Mode") == "POLLING"
    assert bundle["paper"]["system"]["producer"]["discovery_mode"] == "POLLING"
    # runs page shows the polling source, not the WS-only wording
    producer_run = bundle["runs"]["runs"][0]
    assert "polling" in producer_run["inputs"].lower()
    assert "polls" in producer_run["rows"]


def test_ws_mode_is_default_for_legacy_artifacts(tmp_path):
    bundle = build(tmp_path)     # fixture writes no discovery_mode anywhere
    assert bundle["paper"]["discovery"]["discovery_mode"] == "WS"
    assert "WS" in bundle["live"]["feedStatus"]["provider"]["label"]


def test_raw_ws_cap_reads_new_key_and_carries_not_credits_note(tmp_path):
    def extra(root):
        _new_semantics_heartbeat(
            root, discovery_mode="HYBRID",
            budget_over={"caps": {
                "max_429_total": 8, "max_candidates_total": 400,
                "max_gettransaction_total": 1024, "max_market_requests_total": 20000,
                "max_seed_windows": 40, "max_sends_per_run": 12,
                "max_raw_ws_notifications_total": 2000000,   # NEW canonical key only
                "max_ws_notifications_total": 2000000,
            }, "ws_notifications_seen": 250000})
    bundle = build(tmp_path, producer_kw={"extra": extra})
    dv = bundle["paper"]["discovery"]
    assert dv["ws_notifications_cap"] == 2000000
    assert dv["ws_notifications_seen"] == 250000
    assert dv["raw_ws_notifications_seen"] == 250000
    assert dv["remaining"]["ws_notifications"] == 2000000 - 250000
    assert "not Helius credits" in dv["raw_ws_note"]
    assert "HYBRID" in bundle["live"]["feedStatus"]["provider"]["label"]
    labels = {d["label"] for d in bundle["live"]["delta"]}
    assert "Raw WS Msgs (not credits)" in labels


def test_raw_ws_cap_falls_back_to_legacy_key(tmp_path):
    # The default fixture writes ONLY the legacy max_ws_notifications_total key.
    bundle = build(tmp_path)
    dv = bundle["paper"]["discovery"]
    assert dv["ws_notifications_cap"] == 120000
    assert dv["remaining"]["ws_notifications"] == 120000 - 100000


def test_market_freshness_surfaced(tmp_path):
    bundle = build(tmp_path, producer_kw={"extra": _new_semantics_heartbeat})
    fresh = bundle["paper"]["discovery"]["market_freshness"]
    assert fresh["market_data_fresh_count"] == 2
    assert fresh["market_data_stale_count"] == 1
    assert fresh["market_unavailable_count"] == 1
    assert fresh["last_successful_market_refresh_at"] == "2026-07-09T22:58:30Z"
    assert fresh["last_market_error"] == "FETCH_MISS"
    assert len(fresh["per_mint"]) == 2
    row = fresh["per_mint"][0]
    assert row["mint"] == "B" * 40 + "pump" and row["status"] == "FRESH"
    assert row["origin"] == "WATCHLIST"
    # stale/unavailable market data is VISIBLE (warn tone), never silent
    live_fresh = bundle["live"]["systemHealth"]["priceFresh"]
    assert "Market" in live_fresh["label"]
    assert live_fresh["tone"] == "warn"
    cand_summary = {r["label"]: r for r in bundle["candidates"]["summary"]}
    assert "Market Fresh · Stale · Unavail" in cand_summary
    assert cand_summary["Market Fresh · Stale · Unavail"]["tone"] == "warn"


def test_market_scheduler_status_is_surfaced_without_confusing_discovery_queue(tmp_path):
    bundle = build(tmp_path, producer_kw={"extra": _new_semantics_heartbeat})
    scheduler = bundle["paper"]["discovery"]["market_scheduler"]
    assert scheduler == {
        "queue": 7, "in_flight": 2, "workers": 2,
        "oldest_deadline_age_seconds": 3.5, "slo_breached": False,
        "price_batches": 0, "overview_calls": 11,
        "requests_avoided_by_grpc": 19, "late_results_rejected": 1,
    }
    assert bundle["paper"]["discovery"]["watch_total"] == 3
    assert scheduler["queue"] == 7


def test_new_blocks_still_redact_secrets(tmp_path):
    def extra(root):
        _new_semantics_heartbeat(root)
        # hostile: a keyed URL smuggled into a freshness/polling-adjacent field
        obj = json.loads((root / "producer_heartbeat.json").read_text(encoding="utf-8"))
        obj["market_freshness"]["last_market_error"] = f"boom {FAKE_KEYED_URL}"
        obj["credit_budget"]["polling"]["note"] = FAKE_WEBHOOK
        _write_json(root / "producer_heartbeat.json", obj)
    bundle = build(tmp_path, producer_kw={"extra": extra})
    text = json.dumps(bundle)
    assert "deadbeef-0000" not in text
    assert "FAKE_TEST_TOKEN" not in text


def test_paid_provider_telemetry_is_visible_and_redaction_safe(tmp_path):
    def extra(root):
        _new_semantics_heartbeat(root, discovery_mode="PAID_WITH_FALLBACK")
        obj = json.loads((root / "producer_heartbeat.json").read_text(encoding="utf-8"))
        obj["provider_telemetry"] = {
            "provider_mode": "PAID_WITH_FALLBACK",
            "provider": "PAID_GRPC_PRIMARY",
            "status": "CONNECTED",
            "active_streams": 1,
            "max_active_streams": 1,
            "stream_capacity": 1,
            "events_received": 42,
            "reconnects": 2,
            "last_message_age_s": 0.8,
            "fallback_active": False,
            "note": FAKE_KEYED_URL,
            "dedupe": {"duplicate_events_dropped": 3, "duplicate_mints_dropped": 4},
        }
        obj["market_transport_stats"].update({"provider": "PAID_MARKET_PRIMARY", "retries": 2})
        obj["market_freshness"]["per_mint"][0].update({
            "market_provider": "PAID_MARKET_PRIMARY",
            "ath_price_usd": "12.5",
            "ath_observed_at_utc": "2026-07-09T22:59:10Z",
            "ath_observation_type": "CURRENT_PRICE",
        })
        _write_json(root / "producer_heartbeat.json", obj)

    bundle = build(tmp_path, producer_kw={"extra": extra})
    provider = bundle["paper"]["discovery"]["provider_telemetry"]
    assert provider["active_streams"] == provider["max_active_streams"] == 1
    live = bundle["live"]
    assert "PAID_WITH_FALLBACK" in live["feedStatus"]["provider"]["label"]
    assert live["providerTelemetry"]["stream_capacity"] == 1
    labels = {row["label"]: row["value"] for row in live["delta"]}
    assert labels["gRPC Stream Status"] == "CONNECTED"
    assert labels["gRPC Active · Max"] == "1 · 1"
    fresh = bundle["paper"]["discovery"]["market_freshness"]["per_mint"][0]
    assert fresh["ath_price_usd"] == "12.5"
    assert "deadbeef-0000" not in json.dumps(bundle)


def test_dashboard_server_host_gate_is_loopback_only():
    from PHX2.dashboard.server import is_loopback_host

    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("::1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.50")


# ─── 2026-07-10: manual Helius credit panel (operator-entered; never auto-read) ──

def _panel(tmp_path, helius_credits, *, producer_kw=None, paper_kw=None):
    producer = make_producer_dir(tmp_path, **(producer_kw or {}))
    paper = make_paper_dir(tmp_path, **(paper_kw or {}))
    return adapter.build_bundle(producer, paper, now=NOW, helius_credits=helius_credits)


def test_credit_panel_present_and_manual_by_default(tmp_path):
    bundle = _panel(tmp_path, None)
    assert "credit_panel" in bundle
    assert "credit_panel" in bundle["paper"]     # also on the paper page (next to discovery)
    cp = bundle["credit_panel"]
    assert cp["manual_entry"] is True and cp["auto_read"] is False
    assert cp["entry_provided"] is False
    assert cp["entry_hint"]                       # a how-to hint is shown when nothing entered
    assert "not Helius credits" in cp["raw_ws_note"]
    # nothing derived until the operator enters before/after
    assert cp["credits_per_hour"] is None and cp["credits_per_ping"] is None
    assert cp["credits_used"] is None and cp["days_to_exhaust"] is None


def test_credit_panel_manual_entry_derives_burn(tmp_path):
    # The real live_private_02 numbers: 14k -> 94k over a 2h (7200s) run with 4 sent pings.
    cp = _panel(
        tmp_path,
        {"before": 14000, "after": 94000, "window_seconds": 7200,
         "as_of_utc": "2026-07-10T21:50:00Z"},
        producer_kw={"budget_over": {"sent_ok_count": 4}},
    )["credit_panel"]
    assert cp["entry_provided"] is True
    assert cp["credits_used"] == 80000
    assert cp["credits_per_hour"] == 40000.0
    assert cp["credits_per_day"] == 960000.0
    assert cp["credits_per_ping"] == 20000.0      # 80000 / 4 sent pings
    assert cp["days_to_exhaust"] == 0.94          # (1_000_000 - 94000) / 960000
    assert cp["sent_pings"] == 4


def test_credit_panel_observed_counters_surfaced(tmp_path):
    bundle = _panel(tmp_path, None, producer_kw={"extra": _new_semantics_heartbeat})
    cp = bundle["credit_panel"]
    assert cp["discovery_mode"] == "POLLING"
    assert cp["polling_tx_count"] == 9            # POLLING_BLOCK.transactions_fetched
    assert cp["market_http_calls"] == 9
    # raw WS msgs are shown for correlation but explicitly labelled NOT credits
    assert cp["raw_ws_msg_count"] == 100000
    assert cp["auto_read"] is False


def test_credit_panel_zero_pings_no_div_by_zero(tmp_path):
    cp = _panel(tmp_path, {"before": 100, "after": 500, "window_seconds": 3600})["credit_panel"]
    assert cp["credits_per_hour"] == 400.0
    assert cp["credits_per_ping"] is None         # 0 sent pings => no per-ping figure


def test_credit_panel_never_exposes_secret_from_config(tmp_path):
    # A hostile value smuggled into the operator-entered config must still be redacted, and unknown
    # keys (api_key/note) are ignored entirely — the panel only reads numeric credit fields.
    cp_input = {"before": 1, "after": 2, "window_seconds": 60,
                "as_of_utc": f"see {FAKE_KEYED_URL}", "note": FAKE_WEBHOOK,
                "api_key": "deadbeef-should-never-surface"}
    bundle = _panel(tmp_path, cp_input)
    text = json.dumps(bundle)
    assert "deadbeef" not in text                 # neither the keyed URL nor the api_key value
    assert "FAKE_TEST_TOKEN" not in text
    assert bundle["credit_panel"]["credits_used"] == 1   # numeric fields still computed


# ─── scam/bundle risk layer surfaces (2026-07-11) ────────────────────────────

RISK_SUMMARY_BLOCK = {
    "kind": "FREE_TIER_RISK_SUMMARY",
    "tracked_mints": 3, "assessed_mints": 3,
    "by_label": {"RISK_LOW": 1, "RISK_MEDIUM": 1, "RISK_HIGH": 1,
                 "RISK_UNKNOWN": 0},
    "reason_counts": {"LIQUIDITY_COLLAPSE": 1, "LP_THIN": 1},
    "high_risk_mints": ["E" * 40 + "pump"],
    "holder_scan_enabled": False,
    "note": "cheap free-tier heuristic",
}


def _risky_producer(root: Path):
    """Overlay risk fields onto the standard fake producer dir."""
    hb_path = root / "producer_heartbeat.json"
    hb = json.loads(hb_path.read_text(encoding="utf-8"))
    hb["risk_summary"] = RISK_SUMMARY_BLOCK
    _write_json(hb_path, hb)
    cand = {
        "candidate_id": "cap1_BBB", "kind": "BUILD30_CANDIDATE_RECHECK",
        "token_mint": "B" * 40 + "pump",
        "observed_at_utc": _iso(NOW - timedelta(minutes=2)),
        "rejection_reason": "MARKET_UNAVAILABLE",
        "market_attempt_summary": {"basis": "REAL_MARKET_INCOMPLETE",
                                   "mc_present": True, "price_present": True,
                                   "lp_present": False, "attempts": []},
        "risk_label": "RISK_HIGH",
        "risk_reasons": ["LIQUIDITY_COLLAPSE", "MARKET_STALE"],
        "risk_line": "Risk: HIGH — liquidity collapse / market stale",
    }
    _write_jsonl(root / "candidates" / "cap1_BBB.jsonl", [cand])
    _write_jsonl(root / "would_ping_records.jsonl", [{
        "kind": "FREE_TIER_WOULD_PING", "token_mint": "B" * 40 + "pump",
        "observed_at_utc": _iso(NOW - timedelta(minutes=1)),
        "risk_label": "RISK_MEDIUM", "risk_reasons": ["LP_THIN"],
        "risk_line": "Risk: MEDIUM — thin LP",
    }])


def _risky_paper(root: Path):
    """Overlay high-risk skip + observer strategy onto the fake paper dir."""
    sm_path = root / "paper_summary.json"
    sm = json.loads(sm_path.read_text(encoding="utf-8"))
    sm["strategies"]["bala_plan"]["high_risk_skips"] = 2
    sm["strategies"]["bala_plan"]["high_risk_skip_reasons"] = {
        "HIGH_RISK_SCAM_BUNDLE": 1, "HIGH_RISK_LIQUIDITY_COLLAPSE": 1}
    sm["strategies"]["high_risk_observer"] = {
        "strategy_name": "high_risk_observer", "closed_trades": 1,
        "open_trades": 1, "realized_pnl_usd": -12.5, "unrealized_pnl_usd": 3.0,
        "total_pnl_usd": -9.5, "total_pnl_pct": None, "win_rate_pct": 0.0,
        "best_trade": None, "worst_trade": None, "skip_reasons": {},
        "skipped_trades": 0, "rugged_trades": 1, "data_lost_trades": 0,
        "max_drawdown_pct": 40.0, "high_risk_skips": 0,
        "starting_bankroll_usd": 1000.0, "ending_equity_usd": 990.5,
    }
    for row in sm["strategy_ranking"]:
        row["high_risk_skips"] = 2 if row["strategy_name"] == "bala_plan" else 0
    _write_json(sm_path, sm)
    mon_path = root / "live_monitor.json"
    mon = json.loads(mon_path.read_text(encoding="utf-8"))
    mon["strategies"]["bala_plan"]["machine"]["risk_medium_skips"] = 3
    mon["strategies"]["high_risk_observer"] = {
        "machine": {"high_risk_entries": 2, "non_high_risk_passed_over": 5}}
    _write_json(mon_path, mon)
    _write_jsonl(root / "paper_positions.jsonl", [{
        "paper_trade_id": "bala_plan-00009-EEE", "strategy_name": "bala_plan",
        "mint": "E" * 40 + "pump", "status": "SKIPPED_HIGH_RISK",
        "closed_at_utc": _iso(NOW - timedelta(minutes=3)),
        "reason_closed": "HIGH_RISK_LIQUIDITY_COLLAPSE",
        "risk_label_at_entry": "RISK_HIGH",
        "risk_reasons_at_entry": ["LIQUIDITY_COLLAPSE"],
        "realized_pnl_usd": 0.0,
    }])


def _risk_bundle(tmp_path):
    return build(tmp_path, producer_kw={"extra": _risky_producer},
                 paper_kw={"extra": _risky_paper})


def test_candidate_rows_carry_risk_label_and_reasons(tmp_path):
    bundle = _risk_bundle(tmp_path)
    rows = bundle["candidates"]["queue"]
    risky = next(r for r in rows if r["mint"] == "B" * 40 + "pump")
    assert risky["risk"] == "HIGH"
    assert risky["riskLabel"] == "RISK_HIGH"
    assert risky["riskTone"] == "bad"
    assert "LIQUIDITY_COLLAPSE" in risky["riskReasons"]
    assert "Risk assessment: HIGH" in risky["explanation"]


def test_candidate_rows_without_risk_default_unknown_not_high(tmp_path):
    bundle = build(tmp_path)      # legacy artifacts: no risk fields anywhere
    for row in bundle["candidates"]["queue"]:
        assert row["risk"] == "?"
        assert row["riskTone"] == "muted"
        assert row["riskReasons"] == []


def test_risk_summary_metric_on_candidates_and_live_pages(tmp_path):
    bundle = _risk_bundle(tmp_path)
    cand_metric = next(m for m in bundle["candidates"]["summary"]
                       if m["label"].startswith("Risk"))
    assert cand_metric["value"] == "1 · 1 · 1 · 0"
    assert cand_metric["tone"] == "bad"           # one HIGH present
    live_metric = next(d for d in bundle["live"]["delta"]
                       if d["label"].startswith("Risk"))
    assert live_metric["value"] == "1 · 1 · 1 · 0"


def test_risk_protection_block_totals_and_observer(tmp_path):
    bundle = _risk_bundle(tmp_path)
    rp = bundle["paper"]["trading"]["risk_protection"]
    assert rp["producer_by_label"] == {"HIGH": 1, "MEDIUM": 1, "LOW": 1,
                                       "UNKNOWN": 0}
    assert rp["high_risk_skips_total"] == 2
    assert rp["high_risk_skips_by_strategy"] == {"bala_plan": 2}
    assert rp["high_risk_skip_reasons"] == {
        "HIGH_RISK_LIQUIDITY_COLLAPSE": 1, "HIGH_RISK_SCAM_BUNDLE": 1}
    assert rp["observer"]["name"] == "high_risk_observer"
    assert rp["observer"]["high_risk_entries"] == 2
    assert rp["bala_risk_medium_skips"] == 3
    assert rp["holder_scan_enabled"] is False


def test_risk_protection_defaults_when_absent(tmp_path):
    bundle = build(tmp_path)      # no risk artifacts at all
    rp = bundle["paper"]["trading"]["risk_protection"]
    assert rp["producer_by_label"] == {"HIGH": 0, "MEDIUM": 0, "LOW": 0,
                                       "UNKNOWN": 0}
    assert rp["high_risk_skips_total"] == 0
    assert rp["observer"] is None


def test_strategy_rows_and_skip_table_carry_risk(tmp_path):
    bundle = _risk_bundle(tmp_path)
    strategies = bundle["paper"]["trading"]["strategies"]
    bala_row = next(s for s in strategies if s["name"] == "bala_plan")
    assert bala_row["high_risk_skips"] == 2
    skips = bundle["paper"]["tables"]["skips"]
    hr = next(s for s in skips
              if s["reason"] == "HIGH_RISK_LIQUIDITY_COLLAPSE")
    assert hr["risk"] == "HIGH"
    assert hr["high_risk_skip"] is True
    would = bundle["paper"]["tables"]["would_pings"]
    assert any(w["risk"] == "MEDIUM" for w in would)


def test_risk_surfaces_still_redaction_safe(tmp_path):
    bundle = _risk_bundle(tmp_path)
    text = json.dumps(bundle)
    assert "FAKE_TEST_TOKEN" not in text
    assert "api-key" not in text.lower().replace("api_key", "")
