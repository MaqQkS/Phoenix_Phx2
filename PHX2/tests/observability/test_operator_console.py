from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import pytest

from PHX2.observability import operator_console as oc


MINT = "ABCDEFGH1234567890pump"


def console(tmp_path, **kwargs):
    lines = []
    instance = oc.OperatorConsole(tmp_path, output=lines.append, **kwargs)
    return instance, lines


@pytest.mark.parametrize(
    ("record", "expected"),
    (
        ({"kind": "PHX2_SUPERVISOR_EVENT", "event": "SESSION_STARTING"}, "PHX2 production session"),
        ({"kind": "PHX2_SUPERVISOR_EVENT", "event": "SUPERVISOR_STARTED", "pid": 123}, "supervisor started pid=123"),
        ({"kind": "PHX2_SUPERVISOR_EVENT", "event": "CHILD_STARTED", "role": "PRODUCER", "pid": 124}, "producer started pid=124"),
        ({"kind": "PHX2_SUPERVISOR_EVENT", "event": "PAPER_CHILD_FAILED", "error_category": "PROCESS_EXIT", "restart_attempts": 1}, "PAPER_CHILD_FAILED"),
        ({"kind": "PHX2_SUPERVISOR_EVENT", "event": "PAPER_CHILD_RESTARTED", "pid": 125, "attempt": 1}, "paper restarted pid=125"),
        ({"kind": "PHX2_SUPERVISOR_EVENT", "event": "PAPER_DEGRADED", "restart_attempts": 3}, "PAPER_DEGRADED"),
        ({"kind": "PHX2_PROVIDER_HANDOFF", "event": "CANDIDATE_ACCEPTED", "token_mint": MINT, "queue_depth": 1}, "ACCEPTED"),
        ({"kind": "PHX2_PROVIDER_HANDOFF", "event": "DUPLICATE_EVENT", "token_mint": MINT, "reason": "DUPLICATE_EVENT"}, "DUPLICATE_EVENT"),
        ({"kind": "PHX2_PROVIDER_HANDOFF", "event": "DUPLICATE_MINT", "token_mint": MINT, "reason": "DUPLICATE_MINT"}, "DUPLICATE_MINT"),
        ({"kind": "PHX2_PROVIDER_HANDOFF", "event": "CANDIDATE_ENQUEUED", "token_mint": MINT, "queue_depth": 2}, "ENQUEUED"),
        ({"kind": "PHX2_PROVIDER_HANDOFF", "event": "CANDIDATE_DEQUEUED", "token_mint": MINT, "queue_depth": 1, "queue_age_seconds": 0.8}, "age=0.8s"),
        ({"kind": "PHX2_PROVIDER_HANDOFF", "event": "WATCHLIST_ACKNOWLEDGED", "token_mint": MINT, "state": "SEEDED"}, "downstream=WATCHLIST"),
        ({"kind": "PHX2_WATCHLIST_EVENT", "event": "THRESHOLD_REACHED", "token_mint": MINT, "multiplier": 1.21}, "move=1.21x"),
        ({"kind": "PHX2_WATCHLIST_EVENT", "event": "ACTIVATED_WAITING_FOR_FRESH_MARKET", "token_mint": MINT}, "current_market=REQUIRED"),
        ({"kind": "FREE_TIER_PRICING_TAIL", "token_mint": MINT, "market_state": "MARKET_READY", "current_market_cap_usd": 31420, "liquidity_usd": 8115, "current_price": "0.0001"}, "MC=$31,420"),
        ({"kind": "FREE_TIER_PRICING_TAIL", "token_mint": MINT, "market_state": "MARKET_INCOMPLETE", "market_reason_code": "PRICE_MISSING"}, "MARKET_INCOMPLETE"),
        ({"kind": "BUILD30_CANDIDATE_RECHECK", "token_mint": MINT, "risk_label": "RISK_HIGH", "risk_reasons": ["LP_THIN"], "compose_reason": "SKIPPED_HIGH_RISK_DISCORD"}, "label=RISK_HIGH"),
        ({"kind": "BUILD30_CANDIDATE_RECHECK", "token_mint": MINT, "central_ath": {"ath_market_cap": 42100, "ath_provider": "GRPC_EVENT"}}, "ATH=$42,100"),
        ({"kind": "FREE_TIER_PRIVATE_SEND_ATTEMPT", "token_mint": MINT, "sent_ok": True}, "SENT_OK"),
        ({"kind": "FREE_TIER_PRIVATE_SEND_ATTEMPT", "token_mint": MINT, "sent_ok": False, "exception_type": "TimeoutError"}, "DELIVERY_FAILURE"),
        ({"event": "POSITION_OPENED", "mint": MINT, "strategy_name": "BALA_PLAN"}, "POSITION_OPENED"),
        ({"token_mint": MINT, "status": "WATCHING"}, "CANDIDATE_VISIBLE"),
    ),
)
def test_record_rendering(tmp_path, record, expected):
    instance, lines = console(tmp_path)
    instance.render_record(record)
    assert any(expected in line for line in lines)


def test_grpc_connected_and_aggregate_status_rendering(tmp_path):
    instance, lines = console(tmp_path)
    instance.render_record(
        {
            "kind": "PRODUCTION_LIVE_HEARTBEAT",
            "provider_telemetry": {
                "status": "CONNECTED",
                "active_streams": 1,
                "max_active_streams": 1,
                "connect_attempts": 1,
                "source_updates_scanned": 122440,
            },
            "watchlist_active": 3,
            "market_calls_total": 9,
            "credit_budget": {"sent_ok_count": 1},
        }
    )
    text = "\n".join(lines)
    assert "CONNECTED stream=1 max=1 attempt=1" in text
    assert "updates=122440" in text


def test_reconnect_and_fixed_safe_error_rendering(tmp_path):
    instance, lines = console(tmp_path)
    instance.render_record(
        {"kind": "PRODUCTION_LIVE_HEARTBEAT", "provider_telemetry": {"status": "CONNECTED", "reconnects": 0}}
    )
    instance.render_record(
        {
            "kind": "PRODUCTION_LIVE_HEARTBEAT",
            "provider_telemetry": {
                "status": "RECONNECTING",
                "reconnects": 1,
                "last_reconnect_reason": "WATCHDOG_STALE",
                "stream_attempts": [{"sanitized_error_category": "TRANSPORT_UNAVAILABLE", "grpc_status_code": "UNAVAILABLE"}],
            },
        }
    )
    text = "\n".join(lines)
    assert "RECONNECT count=1 reason=WATCHDOG_STALE" in text
    assert "category=TRANSPORT_UNAVAILABLE code=UNAVAILABLE" in text


def test_partial_jsonl_is_retried_after_newline(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"kind":"X"}')
    cursor = oc.JsonlCursor()
    assert cursor.read(path) == []
    with path.open("ab") as handle:
        handle.write(b"\n")
    assert cursor.read(path) == [{"kind": "X"}]


def test_offsets_prevent_duplicate_output(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event":"ONE"}\n', encoding="utf-8")
    cursor = oc.JsonlCursor()
    assert len(cursor.read(path)) == 1
    assert cursor.read(path) == []
    assert cursor.offsets[path] == path.stat().st_size


def test_missing_artifact_is_tolerated(tmp_path):
    assert oc.JsonlCursor().read(tmp_path / "missing.jsonl") == []
    assert oc.JsonSnapshotCursor().read(tmp_path / "missing.json") is None


def test_file_replacement_replays_only_new_records(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event":"ONE"}\n', encoding="utf-8")
    cursor = oc.JsonlCursor()
    assert [r["event"] for r in cursor.read(path)] == ["ONE"]
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text('{"event":"ONE"}\n{"event":"TWO"}\n', encoding="utf-8")
    replacement.replace(path)
    assert [r["event"] for r in cursor.read(path)] == ["TWO"]


def test_secret_bearing_values_are_never_rendered(tmp_path):
    instance, lines = console(tmp_path)
    secret = "https://endpoint.invalid/?x-token=SECRET"
    instance.render_record(
        {"kind": "PHX2_PROVIDER_HANDOFF", "event": "CANDIDATE_REJECTED", "token_mint": MINT, "reason": secret, "endpoint": secret}
    )
    text = "\n".join(lines)
    assert "SECRET" not in text
    assert "endpoint.invalid" not in text


def test_pipeline_handoff_stall_warning(tmp_path):
    now = {"value": 0.0}
    instance, lines = console(
        tmp_path,
        clock=lambda: now["value"],
        stall_after_seconds=10,
    )
    heartbeat = {
        "kind": "PRODUCTION_LIVE_HEARTBEAT",
        "provider_telemetry": {"status": "CONNECTED", "candidates_accepted": 2, "queue_depth": 2, "active_streams": 1, "max_active_streams": 1},
        "watchlist_active": 0,
        "market_calls_total": 0,
    }
    instance.render_record(heartbeat)
    now["value"] = 11.0
    instance.render_record(heartbeat)
    assert any("PIPELINE_HANDOFF_STALL" in line for line in lines)


def test_queue_growth_warning(tmp_path):
    instance, lines = console(tmp_path)
    for depth in (1, 2, 3):
        instance.render_record(
            {"kind": "PRODUCTION_LIVE_HEARTBEAT", "provider_telemetry": {"status": "CONNECTED", "queue_depth": depth, "active_streams": 1, "max_active_streams": 1}}
        )
    assert any("QUEUE_GROWTH" in line for line in lines)


def test_market_scheduler_status_surface_is_explicit_and_redaction_safe(tmp_path):
    instance, lines = console(tmp_path)
    instance.render_record({
        "kind": "PRODUCTION_LIVE_HEARTBEAT",
        "provider_telemetry": {
            "status": "CONNECTED", "active_streams": 1,
            "max_active_streams": 1, "queue_depth": 99,
        },
        "market_scheduler": {
            "queue": 7, "in_flight": 2,
            "oldest_deadline_age_seconds": 3.5, "slo_breached": False,
            "price_batches": 0, "overview_calls": 11,
            "requests_avoided_by_grpc": 19, "late_results_rejected": 1,
        },
    })
    text = "\n".join(lines)
    assert "SCHEDULER queue=7 in_flight=2" in text
    assert "overview_calls=11 avoided_by_grpc=19 late_rejected=1" in text
    assert "queue=99" in text  # discovery queue remains a distinct surface


def test_active_stream_greater_than_one_warning(tmp_path):
    instance, lines = console(tmp_path)
    instance.render_record(
        {"kind": "PRODUCTION_LIVE_HEARTBEAT", "provider_telemetry": {"status": "CONNECTED", "active_streams": 2, "max_active_streams": 2}}
    )
    assert any("ACTIVE_STREAMS_EXCEEDED" in line for line in lines)


@pytest.mark.parametrize(
    ("sent", "delta", "code"),
    ((1, 0, "DELIVERY_WITHOUT_LEDGER_DELTA"), (0, 1, "LEDGER_DELTA_WITHOUT_SENT_OK")),
)
def test_ledger_sent_ok_mismatch_warning(tmp_path, sent, delta, code):
    instance, lines = console(tmp_path)
    instance._monitor({"sent_ok_count": sent, "active_ledger_delta": delta})
    assert any(code in line for line in lines)


@pytest.mark.parametrize(
    ("paper_ath", "paper_provider", "code"),
    (("101", "GRPC_EVENT", "ATH_NUMERIC_DISAGREEMENT"), ("100", "OTHER", "ATH_PROVENANCE_DISAGREEMENT")),
)
def test_ath_disagreement_warning(tmp_path, paper_ath, paper_provider, code):
    instance, lines = console(tmp_path)
    instance._latest_producer_ath[MINT] = ("100", "GRPC_EVENT")
    instance._paper_status({"token_mint": MINT, "ath_market_cap": paper_ath, "ath_provider": paper_provider})
    assert any(code in line for line in lines)


def test_stale_heartbeat_warning(tmp_path):
    instance, lines = console(tmp_path, stale_heartbeat_seconds=1)
    path = instance.producer_dir / "producer_heartbeat.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (instance.clock() - 5, instance.clock() - 5))
    instance.poll_once()
    assert any("STALE_HEARTBEAT" in line for line in lines)


def test_manual_ctrl_c_stops_only_console(tmp_path, monkeypatch, capsys):
    stop_file = tmp_path / "control" / "STOP_REQUESTED"

    def interrupt(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(oc.OperatorConsole, "run", interrupt)
    assert oc.main(["--run-dir", str(tmp_path)]) == 0
    assert not stop_file.exists()
    assert "production unchanged" in capsys.readouterr().out


def test_console_import_boundary_has_no_network_or_mutation_clients():
    path = Path(oc.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
    forbidden = ("grpc", "requests", "urllib", "socket", "discord", "paid_provider", "ledger", "paper_trading", "dashboard")
    assert not any(name.startswith(forbidden) for name in imports)


def test_polling_console_does_not_write_any_file(tmp_path):
    event = tmp_path / "producer" / "provider_handoff.jsonl"
    event.parent.mkdir(parents=True)
    event.write_text(json.dumps({"kind": "PHX2_PROVIDER_HANDOFF", "event": "CANDIDATE_ENQUEUED", "token_mint": MINT}) + "\n", encoding="utf-8")
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()}
    instance, _ = console(tmp_path)
    instance.poll_once()
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
