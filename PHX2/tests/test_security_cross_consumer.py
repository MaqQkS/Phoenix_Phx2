from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from PHX2.dashboard.adapter import build_candidate_rows
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.scam_policy import (
    LP_INTEGRITY_MODE_TWO_STREAM,
    evaluate_delivery_safety,
    format_security_lines,
)
from PHX2.observability import operator_console as console_module
from PHX2.paper_trading.config import (
    PROFILE_FIXED_USD,
    STRATEGY_CONFIG_PLAN,
    PaperConfig,
    SizingProfileConfig,
    StrategyConfig,
    default_strategy_params,
)
from PHX2.paper_trading.engine import PaperTradingEngine
from PHX2.paper_trading.ledger import OPEN_POSITIONS_FILE, read_jsonl
from PHX2.paper_trading.models import CandidateSnapshot
from PHX2.paper_trading.pricing import normalize_record
from PHX2.tests.test_composite_scam_policy import (
    AT,
    MINT,
    PHX1_FEE_GATE_SCAM_LIKELY,
    REMOVE_LIQUIDITY,
    _event,
    _fee,
    _lp,
)


def _blocked_decision():
    # Historical two-stream decision (explicit non-default mode): every
    # consumer must still render archived fee + LP reason families.
    removal = _event(REMOVE_LIQUIDITY, signature="remove", slot=101)
    return evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        lp_snapshot=_lp(removal),
        lp_integrity_mode=LP_INTEGRITY_MODE_TWO_STREAM,
    )


def _candidate_artifact(decision):
    return producer_session.artifacts.build_candidate_recheck_record(
        rec={
            "token_mint": MINT,
            "reason": "+".join(decision.final_block_reasons),
            "compose_attempted": False,
            "reservation_attempted": False,
            "market_context": {
                "current_price": "0.0001",
                "current_market_cap_usd": "100000",
                "liquidity_usd": "50000",
                "market_context_fetched_at_utc": AT,
            },
        },
        entry=SimpleNamespace(
            candidate_id="candidate-1", migration_time_utc=AT, source_ref="migration"),
        cycle=1, observed_at_utc=AT, ledger_touched=False,
        transport_attempted=False, security=decision,
    )


def test_candidate_send_paper_dashboard_and_ping_share_one_sealed_decision():
    decision = _blocked_decision()
    sealed = decision.to_dict()
    candidate = _candidate_artifact(decision)
    send = producer_session.artifacts.build_send_attempt_record(
        token_mint=MINT, candidate_id="candidate-1", tick=1,
        observed_at_utc=AT, ledger_reserved=False, cycle_delta=0,
        send_result=None, security=sealed,
        market_context={
            "current_price": "0.0001", "current_market_cap_usd": "100000",
            "liquidity_usd": "50000",
        },
    )
    paper = normalize_record(candidate)
    assert paper is not None
    producer = {
        "watch": {"candidate-1": {
            "candidate_id": "candidate-1", "token_mint": MINT,
            "status": "ACTIVE_DIP_WATCH", "activation_proven": True,
            "seeded_at_utc": AT, "last_observed_at_utc": AT,
        }},
        "candidates": {"candidate-1": {"last": candidate}},
        "ath_state": {},
    }
    dashboard = build_candidate_rows(
        producer, datetime.fromtimestamp(1000, timezone.utc))[0]

    assert candidate["fee_gate"] == send["fee_gate"] == sealed["fee_snapshot"]
    assert candidate["lp_integrity"] == send["lp_integrity"] == sealed["lp_snapshot"]
    assert candidate["scam_policy"] == send["scam_policy"] == sealed
    assert paper.fee_gate == sealed["fee_snapshot"]
    assert paper.lp_integrity == sealed["lp_snapshot"]
    assert paper.scam_policy == sealed
    assert dashboard["feeGateLabel"] == sealed["fee_snapshot"]["fee_gate_label"]
    assert dashboard["feeGateReasons"] == sealed["fee_snapshot"]["fee_gate_reasons"]
    assert dashboard["lpIntegrity"] == sealed["lp_snapshot"]["lp_integrity"]
    assert dashboard["lpIntegrityReasons"] == sealed["lp_snapshot"]["lp_integrity_reasons"]
    assert dashboard["compositeVerdict"] == sealed["verdict"]
    assert dashboard["compositeBlockReasons"] == sealed["final_block_reasons"]
    lines = format_security_lines(decision)
    assert "Fee Gate: SCAM Likely" in lines
    assert any(line.startswith("Participation: total=") for line in lines)
    assert any(line.startswith("Ante:") for line in lines)
    assert "LP Integrity: FAIL" in lines
    assert "Composite verdict: HARD_BLOCK" in lines


def test_paper_displays_security_block_but_cannot_open_a_simulated_position(tmp_path):
    decision = _blocked_decision()
    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path)
    cfg.run.run_id = "security-block"
    cfg.run.heartbeat_every_seconds = 0
    cfg.run.equity_curve_bucket_seconds = 0
    cfg.sizing_profiles = {"p": SizingProfileConfig(
        profile=PROFILE_FIXED_USD, fixed_usd_size=100.0,
        max_buy_pct_of_liquidity=None, max_abs_notional_usd=None)}
    cfg.strategies = [StrategyConfig(
        name="s1", strategy_type=STRATEGY_CONFIG_PLAN, sizing_profile="p",
        params=default_strategy_params(STRATEGY_CONFIG_PLAN))]
    engine = PaperTradingEngine(cfg, quiet=True)
    engine.process_snapshot(CandidateSnapshot(
        ts_epoch=1000, mint=MINT, price_usd=0.0001,
        market_cap_usd=100000, liquidity_usd=50000,
        fee_gate=decision.fee_snapshot.to_dict(),
        lp_integrity=decision.lp_snapshot.to_dict(),
        scam_policy=decision.to_dict(),
    ))
    engine.close()
    assert read_jsonl(str(Path(engine.run_dir) / OPEN_POSITIONS_FILE)) == []
    events = read_jsonl(str(Path(engine.run_dir) / "paper_events.jsonl"))
    skipped = [row for row in events if row.get("event") == "ENTRY_SKIPPED_SECURITY_POLICY"]
    assert len(skipped) == 1
    assert skipped[0]["fee_gate"] == decision.fee_snapshot.to_dict()
    assert skipped[0]["lp_integrity"] == decision.lp_snapshot.to_dict()


def test_console_renders_full_ca_and_all_reason_families_by_default(monkeypatch, tmp_path):
    decision = _blocked_decision()
    output = []
    monkeypatch.setattr(console_module, "_SHORT_DISPLAY", False)
    console = console_module.OperatorConsole(tmp_path, output=output.append)
    console.render_record({
        "kind": "PHX2_SECURITY_DECISION", "token_mint": MINT,
        "decision": decision.to_dict(),
    })
    rendered = "\n".join(output)
    assert MINT in rendered
    assert "PHX1_FEE_GATE_SCAM_LIKELY" in rendered
    assert "UNEXPLAINED_LIQUIDITY_REMOVAL" in rendered
    assert "source=PHX1_FEE_GATE" in rendered
    assert "source=LP_INTEGRITY" in rendered
    assert "source=LP_AND_FEE_COMPOSITE" in rendered
    assert console_module.abbreviate_mint(MINT) == MINT
    assert console_module.abbreviate_mint(MINT, short=True) != MINT


def test_console_is_read_only_and_has_no_network_or_mutation_imports():
    source = Path(console_module.__file__).read_text(encoding="utf-8")
    forbidden_imports = (
        "import grpc", "import requests", "import aiohttp", "import websockets",
        "import urllib", "import subprocess", "import socket",
    )
    assert not any(needle in source for needle in forbidden_imports)
    assert "ledger.append" not in source
    assert "send_one_audited_post" not in source
    assert "DiscordWebhook" not in source
