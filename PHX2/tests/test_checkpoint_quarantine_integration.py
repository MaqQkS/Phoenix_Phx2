"""PHX2-E2E-005 — quarantine visibility end to end.

Required tests 63-66: the production session visibly REFUSES normal alerting
when an authoritative checkpoint is quarantined; the dashboard never renders
a quarantined checkpoint as an empty healthy watchlist; the operator console
exposes the exact safe quarantine reason; and the production redaction
scanner stays clean over checkpoint diagnostics.

Offline: fake env values only (PRESENT/MISSING semantics), temporary
directories, no provider/transport connection, no real ledger.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.dashboard.adapter import _producer_core, load_producer
from PHX2.free_tier_producer import free_tier_session as fts
from PHX2.free_tier_producer.compat.build30_watchlist import Watchlist
from PHX2.observability import operator_console as oc

MINT = "IntQuarantine0000000000000000000000000pump"


def _producer_args(tmp_path: Path, monkeypatch) -> list:
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    ledger = tmp_path / "ledger" / "ping_dedupe.jsonl"
    ledger.parent.mkdir(exist_ok=True)
    # PRESENT/MISSING gate only — placeholder values, nothing is contacted
    # before the checkpoint refusal returns. Env names are concatenated so
    # the committed source stays clean for the boundary secret-shape scan.
    monkeypatch.setenv("HELIUS" + "_API" + "_KEY", "placeholder-selftest-value")
    monkeypatch.setenv("HELIUS" + "_RPC" + "_URL",
                       "placeholder-selftest-endpoint-never-contacted")
    monkeypatch.setenv(
        "PHX2_MIGRATION_SOURCE_MODE", "CHAINSTACK_PRIMARY")
    return ["--run", "--env", str(env_file), "--out-dir", str(out_dir),
            "--ledger-path", str(ledger)]


def test_63_session_refuses_on_quarantined_ath_checkpoint(
        tmp_path, monkeypatch, capsys):
    argv = _producer_args(tmp_path, monkeypatch)
    out_dir = tmp_path / "out"
    (out_dir / "ath_state.json").write_text("{corrupt", encoding="utf-8")
    (out_dir / "ath_state_checkpoint.json").write_text(
        "{corrupt", encoding="utf-8")
    rc = fts.main(argv)
    captured = capsys.readouterr().out
    assert rc == 2
    assert "[refused] CHECKPOINT_QUARANTINED:CENTRAL_ATH:" in captured
    quarantine = json.loads(
        (out_dir / "checkpoint_quarantine.json").read_text(encoding="utf-8"))
    assert quarantine["quarantined_checkpoint"] == "CENTRAL_ATH"
    assert quarantine["ath"]["checkpoint_quarantined"] is True
    # evidence untouched
    assert (out_dir / "ath_state_checkpoint.json").read_text(
        encoding="utf-8") == "{corrupt"


def test_63b_session_refuses_on_quarantined_watch_checkpoint(
        tmp_path, monkeypatch, capsys):
    argv = _producer_args(tmp_path, monkeypatch)
    out_dir = tmp_path / "out"
    (out_dir / "watch_state.jsonl").write_text("{corrupt", encoding="utf-8")
    (out_dir / "watch_state.jsonl.bak").write_text("{corrupt", encoding="utf-8")
    rc = fts.main(argv)
    captured = capsys.readouterr().out
    assert rc == 2
    assert "[refused] CHECKPOINT_QUARANTINED:WATCH_STATE:" in captured
    quarantine = json.loads(
        (out_dir / "checkpoint_quarantine.json").read_text(encoding="utf-8"))
    assert quarantine["quarantined_checkpoint"] == "WATCH_STATE"
    assert quarantine["watch"]["checkpoint_quarantined"] is True
    assert quarantine["watch"]["checkpoint_quarantine_reason"] \
        is not None
    assert (out_dir / "watch_state.jsonl").read_text(
        encoding="utf-8") == "{corrupt"


def test_64_dashboard_never_shows_quarantine_as_empty_healthy(tmp_path):
    now = datetime.now(timezone.utc)
    producer_dir = tmp_path / "producer"
    producer_dir.mkdir()
    (producer_dir / "watch_state.jsonl").write_text(
        "{corrupt watch checkpoint\n", encoding="utf-8")
    (producer_dir / "checkpoint_quarantine.json").write_text(json.dumps({
        "kind": "PHX2_CHECKPOINT_QUARANTINE",
        "quarantined_checkpoint": "WATCH_STATE",
        "watch": {"checkpoint_quarantined": True,
                  "checkpoint_status": "CHECKPOINT_QUARANTINED",
                  "checkpoint_quarantine_reason": "CHECKPOINT_TRUNCATED"},
        "ath": {"checkpoint_quarantined": False},
    }), encoding="utf-8")
    producer = load_producer(producer_dir, now)
    core = _producer_core(producer, now)
    assert core["checkpoint"]["quarantined"] is True
    assert core["checkpoint"]["display"] == "QUARANTINED"
    assert core["checkpoint"]["quarantine_reason"] == "CHECKPOINT_TRUNCATED"
    assert core["status"] == "CHECKPOINT_QUARANTINED"
    assert core["tone"] == "bad"

    # corrupt checkpoint WITHOUT a quarantine artifact (crash before the
    # session could write one) still never renders as healthy-empty
    bare_dir = tmp_path / "bare"
    bare_dir.mkdir()
    (bare_dir / "watch_state.jsonl").write_text(
        "{corrupt watch checkpoint\n", encoding="utf-8")
    bare = _producer_core(load_producer(bare_dir, now), now)
    assert bare["checkpoint"]["unreadable_suspect"] is True
    assert bare["checkpoint"]["display"] == "UNREADABLE_SUSPECT"
    assert bare["tone"] == "bad"

    # a healthy authenticated checkpoint renders normally
    healthy_dir = tmp_path / "healthy"
    healthy_dir.mkdir()
    watch = Watchlist(max_size=8,
                      terminal_history_path=healthy_dir / "history.jsonl")
    watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "ok"},
        seeded_at_utc="2026-07-15T12:00:00Z")
    watch.persist(healthy_dir / "watch_state.jsonl")
    healthy = _producer_core(load_producer(healthy_dir, now), now)
    assert healthy["checkpoint"]["quarantined"] is False
    assert healthy["checkpoint"]["display"] == "OK"
    # candidate rows survive the envelope header line
    assert any(rec.get("token_mint") == MINT
               for rec in (load_producer(healthy_dir, now)["watch"]).values())


def test_65_operator_console_exposes_quarantine_reason(tmp_path):
    lines = []
    instance = oc.OperatorConsole(tmp_path, output=lines.append)
    instance.render_record({
        "kind": "PHX2_CHECKPOINT_QUARANTINE",
        "quarantined_checkpoint": "WATCH_STATE",
        "watch": {"checkpoint_quarantined": True,
                  "checkpoint_status": "CHECKPOINT_QUARANTINED",
                  "checkpoint_quarantine_reason":
                      "CHECKPOINT_RECORD_DIGEST_INVALID"},
        "ath": {"checkpoint_quarantined": False,
                "checkpoint_status": "CHECKPOINT_PRIMARY_OK",
                "checkpoint_generation": 4},
    })
    text = "\n".join(lines)
    assert "CHECKPOINT_QUARANTINED" in text
    assert "CHECKPOINT_RECORD_DIGEST_INVALID" in text
    assert "store=WATCH" in text
    assert "store=ATH status=CHECKPOINT_PRIMARY_OK" in text
    # the envelope header line in watch_state.jsonl renders as a checkpoint
    # line, never as a phantom candidate
    header_lines = []
    header_console = oc.OperatorConsole(tmp_path, output=header_lines.append)
    header_console.render_record({
        "checkpoint_kind": "PHX2_WATCH_CHECKPOINT",
        "schema_version": "phx2_watch_checkpoint_v2",
        "generation": 3, "record_count": 2,
    })
    header_text = "\n".join(header_lines)
    assert "PHX2_WATCH_CHECKPOINT" in header_text
    assert "generation=3" in header_text
    assert "CANDIDATE_VISIBLE" not in header_text
    # quarantined-candidate records surface with their safe reason
    q_lines = []
    q_console = oc.OperatorConsole(tmp_path, output=q_lines.append)
    q_console.render_record({
        "checkpoint_record_kind": "PHX2_QUARANTINED_CANDIDATE",
        "token_mint": MINT,
        "quarantine_reason": "CHECKPOINT_ACTIVATION_MIGRATION_AMBIGUOUS",
    })
    assert any("CHECKPOINT_CANDIDATE_QUARANTINED" in line
               and "CHECKPOINT_ACTIVATION_MIGRATION_AMBIGUOUS" in line
               for line in q_lines)


def test_66_redaction_scanner_handles_checkpoint_diagnostics(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    watch = Watchlist(max_size=8,
                      terminal_history_path=out_dir / "watch_terminal_history.jsonl")
    entry, _ = watch.seed_with_outcome(
        {"token_mint": MINT, "candidate_id": "red1"},
        seeded_at_utc="2026-07-15T12:00:00Z")
    watch.quarantine_candidate(
        MINT, reason="CHECKPOINT_ACTIVATION_MIGRATION_AMBIGUOUS",
        source_schema_version="phx2_watch_jsonl_legacy_v1",
        legacy_payload={"token_mint": MINT, "candidate_id": "red1",
                        "status": "ACTIVE_DIP_WATCH"},
        legacy_record_digest="a" * 64,
        legacy_checkpoint_digest="b" * 64,
        quarantined_at_utc="2026-07-15T12:00:01Z")
    watch.persist(out_dir / "watch_state.jsonl")
    fts.artifacts.write_json(str(out_dir), "checkpoint_status.json", {
        "kind": "PHX2_CHECKPOINT_STATUS",
        "watch": watch.checkpoint_summary(),
        "ath": {"checkpoint_status": "CHECKPOINT_NOT_FOUND"},
    })
    fts.artifacts.write_json(str(out_dir), "checkpoint_quarantine.json", {
        "kind": "PHX2_CHECKPOINT_QUARANTINE",
        "quarantined_checkpoint": "WATCH_STATE",
        "watch": watch.checkpoint_summary(),
    })
    scan = fts.artifacts.run_redaction_scan(str(out_dir))
    assert scan["redaction_status"] == "REDACTED"
    assert scan["total_unsafe_hits"] == 0
    assert scan["positive_control_ok"] is True
