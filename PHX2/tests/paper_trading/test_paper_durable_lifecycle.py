"""Fault injection for paper-only state, source commits and notification retries."""
from __future__ import annotations

import json
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from PHX2.paper_trading.engine import MODE_LIVE_PAPER, PaperTradingEngine
from PHX2.paper_trading.ledger import FILLS_FILE, STATE_FILE
from PHX2.paper_trading.live import run_live_loop, restore_checkpoints
from PHX2.paper_trading.models import utc_iso
from PHX2.paper_trading.state import PaperRunLease
from PHX2.paper_trading.strategy import AddIntent
from PHX2.tests.paper_trading.test_paper_recovery import config, snap, open_position, fills


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("NETWORK_BLOCKED")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def strict(price=1.0, ts=0.0, quote=None, **extra):
    observation = snap(price, ts)
    observation.risk_label = "RISK_LOW"
    observation.extra = dict(contract_required=True, quote_usable=True,
                            quote_ttl_seconds=300,
                            quote_observed_epoch=ts if quote is None else quote,
                            exposure_eligible=True, activation_required=True,
                            activation_eligible=True, risk_assessed_epoch=ts,
                            security_assessed_epoch=ts, market_cap_observed_epoch=ts,
                            liquidity_observed_epoch=ts, liquidity_ttl_seconds=300)
    observation.extra.update(extra)
    return observation


def bound_entry(ts=600):
    """Engine-side fixture for a producer-validated, identity-bound activation."""
    observation = strict(ts=ts, pricing_coverage={"lease_until_utc": utc_iso(ts + 1800)})
    observation.candidate_id = "candidate-1"
    observation.migration_ts_epoch = ts - 10
    observation.scam_policy = {"verdict": "ALLOW"}
    observation.extra["activation"] = {
        "token_mint": observation.mint, "candidate_id": observation.candidate_id,
        "migration_time_utc": utc_iso(ts - 10), "activated_at_utc": utc_iso(ts),
        "activation_state": "ACTIVE_DIP_WATCH", "activation_proven": True,
        "activation_latched": True, "activation_proof_valid": True,
        "activation_proof_digest": "producer-validated-proof",
    }
    return observation


def continuation(position, ts=999):
    observation = strict(0.9, ts, exposure_eligible=False, activation_eligible=False,
        dca_exposure_eligible=True, activation={},
        pricing_coverage={"lease_until_utc": utc_iso(ts + 1800)})
    observation.candidate_id = position.source_candidate_id
    context = json.loads(json.dumps(position.strategy_state["paper_position_context"]))
    observation.extra["paper_position_context"] = context
    observation.migration_ts_epoch = 590
    observation.scam_policy = {"verdict": "ALLOW"}
    return observation


def test_entry_activation_binding_is_immutable_and_survives_restart(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    engine = PaperTradingEngine(cfg, quiet=True)
    entry = bound_entry()
    engine.process_snapshot(entry)
    pos = engine.runtimes[0].open_by_mint[entry.mint]
    saved = json.loads(json.dumps(pos.strategy_state["paper_position_context"]))
    entry.extra["activation"]["activation_proof_digest"] = "later-input-mutation"
    monkeypatch.setattr(engine.runtimes[0].strategy, "manage", lambda *args: [
        AddIntent(leg="DCA_2", size_usd=10, state_seed={"paper_position_context": {"mint": "wrong"}})])
    engine.process_snapshot(continuation(pos))
    assert len(fills(engine)) == 2
    assert pos.strategy_state["paper_position_context"] == saved
    payload = json.loads((Path(engine.run_dir) / STATE_FILE).read_text())
    assert payload["open_mints"] == [{"mint": pos.mint, "candidate_id": pos.source_candidate_id,
                                       "paper_position_context": saved}]
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    pos = resumed.runtimes[0].open_by_mint[entry.mint]
    assert pos.strategy_state["paper_position_context"] == saved
    monkeypatch.setattr(resumed.runtimes[0].strategy, "manage", lambda *args: [
        AddIntent(leg="DCA_3", size_usd=10)])
    resumed.process_snapshot(continuation(pos, ts=1001))
    assert len(fills(resumed)) == 3
    assert pos.strategy_state["paper_position_context"] == saved
    resumed.close()


@pytest.mark.parametrize("defect", ["candidate", "mint", "migration", "proof", "unproven"])
def test_invalid_entry_proof_cannot_seed_continuation(tmp_path, defect):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    entry = bound_entry()
    if defect == "candidate":
        entry.extra["activation"]["candidate_id"] = "other"
    elif defect == "mint":
        entry.extra["activation"]["token_mint"] = "other"
    elif defect == "migration":
        entry.migration_ts_epoch -= 1
    elif defect == "proof":
        entry.extra["activation"]["activation_proof_valid"] = False
    else:
        entry.extra["activation"]["activation_proven"] = False
    engine.process_snapshot(entry)
    pos = engine.runtimes[0].open_by_mint[entry.mint]
    assert "paper_position_context" not in pos.strategy_state
    engine.close()


def test_continuation_is_only_for_existing_position(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    entry = bound_entry()
    context = engine._admitted_position_context(entry)
    observation = strict(ts=999, activation_eligible=False, exposure_eligible=False,
                         dca_exposure_eligible=True, paper_position_context=context)
    observation.candidate_id = entry.candidate_id
    observation.migration_ts_epoch = entry.migration_ts_epoch
    engine.process_snapshot(observation)
    assert not fills(engine)
    assert not engine.runtimes[0].open_by_mint
    engine.close()


def test_bala_ladder_continues_after_terminal_watch_without_new_activation(tmp_path):
    cfg = config(tmp_path)
    cfg.strategies[0].params.update(dca_1_pct_of_max_position=0.5,
                                   dca_2_pct_of_max_position=0.4, max_dca_count=2)
    engine = PaperTradingEngine(cfg, quiet=True)
    entry = bound_entry()
    engine.process_snapshot(entry)
    pos = engine.runtimes[0].open_by_mint[entry.mint]
    assert pos.virtual_usd_size == 50
    observation = continuation(pos, ts=800)
    observation.price_usd = 0.5
    observation.market_cap_usd = 20_000
    observation.ath_market_cap_usd = 40_000 / 0.3
    observation.tier = None  # production tail derives tier from the current dip
    observation.drawdown_pct = None
    engine.process_snapshot(observation)
    assert [fill["leg"] for fill in fills(engine)] == ["DCA_1", "DCA_2"]
    assert pos.virtual_usd_size == 90
    assert pos.strategy_state["dca_count"] == 2
    assert pos.is_open
    engine.close()


@pytest.mark.parametrize("second_candidate", ["candidate-1", "candidate-2"])
@pytest.mark.parametrize("include_first", [False, True])
def test_shared_mint_tail_matches_each_positions_own_context(
        tmp_path, monkeypatch, second_candidate, include_first):
    cfg = config(tmp_path)
    cfg.strategies[0].params.update(dca_1_pct_of_max_position=0.5,
                                   dca_2_pct_of_max_position=0.4, max_dca_count=2)
    other = deepcopy(cfg.strategies[0])
    other.name = "other_bala"
    cfg.strategies.append(other)
    engine = PaperTradingEngine(cfg, quiet=True)
    second_strategy = engine.runtimes[1].strategy
    wants_entry = second_strategy.wants_entry
    monkeypatch.setattr(second_strategy, "wants_entry", lambda observation, ctx:
                        wants_entry(observation, ctx) if observation.ts_epoch >= 650 else None)
    entry = bound_entry()
    engine.process_snapshot(entry)
    later_entry = bound_entry(ts=650)
    later_entry.candidate_id = second_candidate
    later_entry.extra["activation"]["candidate_id"] = second_candidate
    later_entry.extra["activation"]["activation_current_market_cap_usd"] = 40_000
    engine.process_snapshot(later_entry)
    positions = [runtime.open_by_mint[entry.mint] for runtime in engine.runtimes]
    contexts = [deepcopy(pos.strategy_state["paper_position_context"]) for pos in positions]
    assert contexts[0] != contexts[1]
    payload = json.loads((Path(engine.run_dir) / STATE_FILE).read_text())
    assert [row["paper_position_context"] for row in payload["open_mints"]] == contexts
    observation = continuation(positions[1], ts=800)
    observation.migration_ts_epoch = later_entry.migration_ts_epoch
    observation.extra["paper_position_contexts"] = contexts if include_first else contexts[1:]
    if include_first and second_candidate != "candidate-1":
        # A new active candidate may share the quote with an older position;
        # its entry eligibility must not hide that position's valid context.
        observation.extra.update(exposure_eligible=True, activation_eligible=True,
                                 activation=later_entry.extra["activation"])
    observation.price_usd = 0.5
    observation.market_cap_usd = 20_000
    observation.ath_market_cap_usd = 40_000 / 0.3
    observation.tier = observation.drawdown_pct = None
    engine.process_snapshot(observation)
    assert positions[0].virtual_usd_size == (90 if include_first else 50)
    assert positions[1].virtual_usd_size == 90
    engine.close()


@pytest.mark.parametrize("defect", ["candidate", "mint", "migration", "proof", "snapshot_migration",
                                   "snapshot_candidate", "missing_context"])
def test_continuation_requires_exact_existing_position_binding(tmp_path, monkeypatch, defect):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    entry = bound_entry()
    engine.process_snapshot(entry)
    pos = engine.runtimes[0].open_by_mint[entry.mint]
    monkeypatch.setattr(engine.runtimes[0].strategy, "manage", lambda *args: [
        AddIntent(leg="DCA_2", size_usd=10)])
    observation = continuation(pos)
    context = observation.extra["paper_position_context"]
    if defect == "candidate":
        context["candidate_id"] = "other"
    elif defect == "mint":
        context["mint"] = "other"
    elif defect == "migration":
        context["migration_time_utc"] = utc_iso(589)
    elif defect == "proof":
        context["activation"]["activation_proof_digest"] = "other"
    elif defect == "snapshot_migration":
        observation.migration_ts_epoch -= 1
    elif defect == "snapshot_candidate":
        observation.candidate_id = "other"
    else:
        observation.extra.pop("paper_position_context")
    engine.process_snapshot(observation)
    assert len(fills(engine)) == 1
    assert pos.strategy_state["last_dca_skip"] == "DCA_SECURITY_OR_CONTEXT_BLOCKED"
    engine.close()


@pytest.mark.parametrize("defect", ["risk_assessed_epoch", "security_assessed_epoch",
    "market_cap_observed_epoch", "liquidity_observed_epoch", "quote_observed_epoch",
    "coverage", "hard_block", "high_risk", "unknown_risk", "unknown_security", "none"])
def test_live_continuation_rechecks_current_evidence(tmp_path, monkeypatch, defect):
    clock = [600]
    engine = PaperTradingEngine(config(tmp_path), mode=MODE_LIVE_PAPER,
                                quiet=True, wall_clock=lambda: clock[0])
    entry = bound_entry()
    engine.process_snapshot(entry)
    pos = engine.runtimes[0].open_by_mint[entry.mint]
    monkeypatch.setattr(engine.runtimes[0].strategy, "manage", lambda *args: [
        AddIntent(leg="DCA_2", size_usd=10)])
    clock[0] = 1000
    observation = continuation(pos)
    if defect == "coverage":
        observation.extra["pricing_coverage"]["lease_until_utc"] = utc_iso(999)
    elif defect == "hard_block":
        observation.scam_policy["verdict"] = "HARD_BLOCK"
    elif defect == "high_risk":
        observation.risk_label = "RISK_HIGH"
    elif defect == "unknown_risk":
        observation.risk_label = None
    elif defect == "unknown_security":
        observation.scam_policy = {}
    elif defect != "none":
        observation.extra[defect] = 699  # current at row time, expired at live decision time
    engine.process_snapshot(observation)
    assert sum(fill["side"] == "BUY" for fill in fills(engine)) == (2 if defect == "none" else 1)
    engine.close()


def test_failed_state_commit_has_no_fill_or_notification(tmp_path, monkeypatch):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    original = engine.ledger.write_json_atomic
    def fail(name, payload):
        if name == STATE_FILE:
            raise OSError("INJECTED")
        return original(name, payload)
    monkeypatch.setattr(engine.ledger, "write_json_atomic", fail)
    with pytest.raises(OSError):
        engine.process_snapshot(snap())
    assert not engine.runtimes[0].open_by_mint
    assert not fills(engine)
    assert not engine.notification_events
    assert not engine._batch_active
    engine.close()


@pytest.mark.parametrize("partial", [False, True])
def test_crash_after_recovery_commit_replays_projection_once(tmp_path, monkeypatch, partial):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    def crash(payload):
        if partial:
            with (Path(engine.run_dir) / FILLS_FILE).open("ab") as handle:
                handle.write(b'{"torn":')
        raise OSError("CRASH_AFTER_REPLACE")
    monkeypatch.setattr(engine.ledger, "recover_projection", crash)
    with pytest.raises(OSError):
        engine.process_snapshot(snap(1.35, 60))
    with pytest.raises(RuntimeError, match="RESTART_REQUIRED"):
        engine.process_snapshot(snap(1.4, 90))
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    pos = resumed.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]
    assert pos.strategy_state["initial_recovered"] is True
    assert len(fills(resumed)) == 2
    assert len({row["fill_id"] for row in fills(resumed)}) == 2
    assert len(resumed.notification_events) == 2
    resumed.process_snapshot(snap(1.35, 60))
    assert len(fills(resumed)) == 2
    resumed.close()
    again = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert len(fills(again)) == 2
    again.close()


class Source:
    def __init__(self):
        self.offsets = {"feed": 0}
        self.polls = 0
    def checkpoint_state(self):
        return {"offsets": dict(self.offsets), "files": {"feed": "stable"}}
    def restore_checkpoint(self, state):
        self.offsets = dict(state["offsets"])
    def poll(self):
        self.polls += 1
        if self.offsets["feed"]:
            return [], []
        self.offsets["feed"] = 2
        return [snap(1, 0), snap(1.35, 60)], []


def test_failed_batch_restores_source_and_replays_all_once(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    engine = PaperTradingEngine(cfg, quiet=True)
    source = Source()
    original = engine.process_snapshot
    def crash(snapshot):
        if snapshot.ts_epoch == 60:
            raise OSError("SECOND_RECORD_FAILED")
        original(snapshot)
    monkeypatch.setattr(engine, "process_snapshot", crash)
    with pytest.raises(OSError):
        run_live_loop(engine, source, once=True)
    assert source.offsets == {"feed": 0}
    assert source.polls == 1  # no shutdown drain after a failed transaction
    assert not fills(engine)
    assert not engine.runtimes[0].open_by_mint
    monkeypatch.setattr(engine, "process_snapshot", original)
    run_live_loop(engine, source, once=True)
    assert len(fills(engine)) == 2
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    source2 = Source()
    assert restore_checkpoints(resumed, source2) == 1
    assert source2.offsets == {"feed": 2}
    assert resumed.durable_source_checkpoint["files"] == {"feed": "stable"}
    run_live_loop(resumed, source2, once=True)
    assert len(fills(resumed)) == 2
    resumed.close()


def test_runner_peak_committed_with_source_offsets(tmp_path):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    engine.begin_batch()
    engine.process_snapshot(snap(1.35, 60))
    engine.process_snapshot(snap(4.0, 120))
    engine.commit_batch({"offsets": {"feed": 99}, "files": {"id": "x"}})
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    pos = resumed.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]
    assert pos.post_trim_peak_price == 4
    assert resumed.durable_source_offsets == {"feed": 99}
    resumed.process_snapshot(snap(2.79, 180))
    assert not resumed.runtimes[0].open_by_mint
    assert len(fills(resumed)) == 3
    resumed.close()


def test_changed_config_rejected_before_artifact_write(tmp_path):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    engine.close()
    run_dir = Path(engine.run_dir)
    before = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.is_file()}
    cfg.market_sim.fee_bps += 1
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        PaperTradingEngine(cfg, quiet=True, resume=True)
    assert {p.name: p.read_bytes() for p in run_dir.iterdir() if p.is_file()} == before


def test_full_strategy_rng_risk_and_rug_state_survive_restart(tmp_path):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    engine.begin_batch()
    engine.runtimes[0].rng.random()
    market = engine.market["OFFLINE_TEST_MINT"]
    market.rug_seen = True
    market.risk_label = "RISK_HIGH"
    engine.commit_batch()
    before = engine._export_state()
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert resumed._export_state() == before
    resumed.close()


def test_stale_missing_and_duplicate_quote_do_not_refresh_or_sell(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    engine.process_snapshot(strict(ts=100))
    pos = engine.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]
    for quote in (strict(3.0, 110, quote=100),
                  strict(3.0, 120, quote=110, quote_usable=False),
                  strict(3.0, 130, quote=140)):
        engine.process_snapshot(quote)
    assert pos.latest_price_epoch == 100
    assert pos.latest_price == 1
    assert len(fills(engine)) == 1
    # A valid late-arriving quote keeps its own timestamp, not receive time.
    engine.process_snapshot(strict(1.1, 140, quote=135))
    assert pos.latest_price_epoch == 135
    engine.process_snapshot(strict(0.1, 125))
    assert pos.latest_price == 1.1
    engine.close()


def test_strict_missing_context_cannot_enter_but_fresh_exit_allowed(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    engine.process_snapshot(strict(exposure_eligible=False))
    assert not fills(engine)
    engine.process_snapshot(strict(ts=10))
    quote = strict(1.35, 20, exposure_eligible=False)
    quote.risk_label = None
    engine.process_snapshot(quote)
    assert engine.market[quote.mint].risk_label is None
    assert len(fills(engine)) == 2
    assert engine.runtimes[0].open_by_mint[quote.mint].strategy_state["initial_recovered"]
    engine.close()


@pytest.mark.parametrize("block", ["context", "hard_block", "high_risk"])
def test_dca_cannot_bypass_current_security(tmp_path, monkeypatch, block):
    engine, pos = open_position(config(tmp_path))
    monkeypatch.setattr(engine.runtimes[0].strategy, "manage", lambda *args: [
        AddIntent(leg="DCA_2", size_usd=10)])
    observation = strict(0.9, 60)
    if block == "context":
        observation.extra["exposure_eligible"] = False
    elif block == "hard_block":
        observation.scam_policy = {"verdict": "HARD_BLOCK"}
    else:
        observation.risk_label = "RISK_HIGH"
    engine.process_snapshot(observation)
    assert len(fills(engine)) == 1
    assert pos.strategy_state["last_dca_skip"] == "DCA_SECURITY_OR_CONTEXT_BLOCKED"
    engine.close()


def test_record_digest_is_durable_and_bounded(tmp_path):
    cfg = config(tmp_path)
    engine = PaperTradingEngine(cfg, quiet=True)
    observation = strict(source_record_digest="same-event")
    engine.process_snapshot(observation)
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    resumed.process_snapshot(observation)
    assert resumed.snapshots_processed == 1
    assert resumed._seen_record_digests.maxlen == 8192
    resumed.close()


class FakeTransport:
    def __init__(self, category="SENT_OK", crash=None):
        self.category, self.crash, self.calls = category, crash, []
    def send_html(self, text):
        self.calls.append(text)
        if self.crash:
            raise self.crash
        return {"transport_status": self.category, "ok": self.category == "SENT_OK",
                "message_id": len(self.calls) if self.category == "SENT_OK" else None}


def dispatch(engine, transport, **kwargs):
    return engine.notification_outbox.dispatch_pending(
        transport, authorized=True, destination_alias="OFFLINE_TEST", **kwargs)


def test_three_distinct_paper_notifications_and_confirmed_dedupe(tmp_path):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    engine.process_snapshot(snap(1.35, 60))
    engine.process_snapshot(snap(2, 120))
    engine.process_snapshot(snap(1.39, 180))
    assert {e["transition"] for e in engine.notification_events.values()} == {
        "ENTRY", "STAKE_RECOVERED", "FINAL_EXIT"}
    sender = FakeTransport()
    assert dispatch(engine, sender, max_messages=3) == 3
    assert all("PHOENIX PAPER" in text and "Simulation only" in text for text in sender.calls)
    assert "Unknown / unverified" in sender.calls[0]
    assert "Runner trail: 30%" in sender.calls[1]
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert dispatch(resumed, sender, max_messages=3) == 0
    assert len(sender.calls) == 3
    resumed.close()


def test_delivery_requires_explicit_arming(tmp_path):
    engine, _ = open_position(config(tmp_path))
    sender = FakeTransport()
    with pytest.raises(ValueError, match="NOT_ARMED"):
        engine.notification_outbox.dispatch_pending(sender)
    assert not sender.calls
    engine.close()


def test_stop_after_first_notification_suppresses_second_send(tmp_path):
    engine, _ = open_position(config(tmp_path))
    engine.process_snapshot(snap(1.35, 60))
    sender = FakeTransport()
    assert dispatch(engine, sender, max_messages=2,
                    should_stop=lambda: bool(sender.calls)) == 1
    events = list(engine.notification_events.values())
    assert events[0]["status"] == "SENT"
    assert events[1]["status"] == "PENDING"
    assert events[1]["attempts"] == 0
    assert len(sender.calls) == 1
    engine.close()


@pytest.mark.parametrize("when", ["before_commit", "after_commit"])
def test_stop_before_transport_keeps_unsent_event_pending(tmp_path, when):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    sender = FakeTransport()
    def should_stop():
        return when == "before_commit" or any(
            event["status"] == "IN_FLIGHT" for event in engine.notification_events.values())
    assert dispatch(engine, sender, should_stop=should_stop) == 0
    assert not sender.calls
    event = next(iter(engine.notification_events.values()))
    assert event["status"] == "PENDING"
    assert event["attempts"] == 0
    assert event["destination_alias"] is None
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert next(iter(resumed.notification_events.values()))["status"] == "PENDING"
    assert dispatch(resumed, sender) == 1
    resumed.close()


@pytest.mark.parametrize("category", ["TIMEOUT", "NETWORK_ERROR", "MALFORMED_RESPONSE", "UNKNOWN_FAILURE"])
def test_ambiguous_delivery_never_auto_retries(tmp_path, category):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    sender = FakeTransport(category)
    dispatch(engine, sender)
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert dispatch(resumed, sender, now_epoch=10000) == 0
    assert len(sender.calls) == 1
    assert next(iter(resumed.notification_events.values()))["status"] == "UNKNOWN"
    resumed.close()


def test_explicit_rejection_is_bounded_and_destination_bound(tmp_path):
    engine, _ = open_position(config(tmp_path))
    sender = FakeTransport("MESSAGE_REJECTED")
    assert dispatch(engine, sender, now_epoch=0) == 1
    assert dispatch(engine, sender, now_epoch=1) == 0
    with pytest.raises(ValueError, match="DESTINATION_CHANGED"):
        engine.notification_outbox.dispatch_pending(sender, authorized=True,
            destination_alias="DIFFERENT", now_epoch=100)
    assert dispatch(engine, sender, now_epoch=100) == 1
    assert dispatch(engine, sender, now_epoch=200) == 1
    assert dispatch(engine, sender, now_epoch=10000) == 0
    assert len(sender.calls) == 3
    assert next(iter(engine.notification_events.values()))["status"] == "REJECTED"
    engine.close()


def test_process_crash_during_send_becomes_unknown_on_restart(tmp_path):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    sender = FakeTransport(crash=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        dispatch(engine, sender)
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert next(iter(resumed.notification_events.values()))["status"] == "UNKNOWN"
    assert dispatch(resumed, FakeTransport(), now_epoch=10000) == 0
    resumed.close()


def test_lease_rejects_competing_owner_and_releases(tmp_path):
    with PaperRunLease(tmp_path):
        with pytest.raises(RuntimeError, match="ALREADY_OWNED"):
            with PaperRunLease(tmp_path):
                pass
    with PaperRunLease(tmp_path):
        pass


def test_state_feedback_contains_open_mints_and_heartbeat(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), quiet=True, wall_clock=lambda: 1000)
    observation = snap()
    observation.candidate_id = "candidate-1"
    engine.process_snapshot(observation)
    payload = json.loads((Path(engine.run_dir) / STATE_FILE).read_text())
    assert payload["open_mints"] == [{"mint": observation.mint, "candidate_id": "candidate-1"}]
    assert payload["heartbeat_utc"] == "1970-01-01T00:16:40Z"
    engine.close()


def test_after_commit_runs_outside_transaction_and_not_for_failed_batch(tmp_path, monkeypatch):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    source = Source()
    calls = []
    def callback(owner):
        assert owner is engine and not owner._batch_active
        state = json.loads((Path(owner.run_dir) / STATE_FILE).read_text())
        assert state["source_checkpoint"]["offsets"] == source.offsets
        calls.append(owner._state_generation)
    run_live_loop(engine, source, once=True, after_commit=callback)
    assert len(calls) == 2  # data batch plus final catch-up batch
    calls.clear()
    monkeypatch.setattr(source, "poll", lambda: (_ for _ in ()).throw(OSError("FAILED")))
    with pytest.raises(OSError):
        run_live_loop(engine, source, once=True, after_commit=callback)
    assert not calls
    engine.close()


def test_no_transport_call_if_inflight_commit_fails(tmp_path, monkeypatch):
    engine, _ = open_position(config(tmp_path))
    original = engine.ledger.write_json_atomic
    def fail(name, payload):
        if name == STATE_FILE:
            raise OSError("INFLIGHT_COMMIT_FAILED")
        return original(name, payload)
    monkeypatch.setattr(engine.ledger, "write_json_atomic", fail)
    sender = FakeTransport()
    with pytest.raises(OSError):
        dispatch(engine, sender)
    assert not sender.calls
    assert next(iter(engine.notification_events.values()))["status"] == "PENDING"
    assert not engine._batch_active
    engine.close()


def test_receipt_commit_crash_holds_unknown_after_restart(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    engine, _ = open_position(cfg)
    original = engine.ledger.write_json_atomic
    def fail(name, payload):
        if name == STATE_FILE and any(
                event["status"] == "SENT" for event in payload["engine"]["notification_events"].values()):
            raise OSError("RECEIPT_COMMIT_FAILED")
        return original(name, payload)
    monkeypatch.setattr(engine.ledger, "write_json_atomic", fail)
    sender = FakeTransport()
    with pytest.raises(OSError):
        dispatch(engine, sender)
    assert len(sender.calls) == 1
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert next(iter(resumed.notification_events.values()))["status"] == "UNKNOWN"
    assert dispatch(resumed, sender, now_epoch=10000) == 0
    resumed.close()


def test_live_legacy_ledger_requires_explicit_migration(tmp_path):
    cfg = config(tmp_path)
    directory = tmp_path / cfg.run.run_id
    directory.mkdir()
    ledger = directory / FILLS_FILE
    ledger.write_text('{"fill_id":"legacy"}\n')
    before = ledger.read_bytes()
    with pytest.raises(ValueError, match="LEGACY_STATE_REQUIRES_REVIEWED_MIGRATION"):
        PaperTradingEngine(cfg, mode=MODE_LIVE_PAPER, quiet=True, resume=True)
    assert ledger.read_bytes() == before


def test_declined_random_roll_is_persisted(tmp_path):
    from PHX2.paper_trading.config import STRATEGY_MONKEY_RANDOM, default_strategy_params
    cfg = config(tmp_path)
    cfg.strategies[0].strategy_type = STRATEGY_MONKEY_RANDOM
    cfg.strategies[0].params = default_strategy_params(STRATEGY_MONKEY_RANDOM)
    cfg.strategies[0].params["entry_probability"] = 0.0
    engine = PaperTradingEngine(cfg, quiet=True)
    engine.process_snapshot(snap())
    rng_state = engine.runtimes[0].rng.getstate()
    engine.close()
    resumed = PaperTradingEngine(cfg, quiet=True, resume=True)
    assert "OFFLINE_TEST_MINT" in resumed.runtimes[0].strategy._rolled_mints
    resumed.process_snapshot(snap(1.1, 60))
    assert resumed.runtimes[0].rng.getstate() == rng_state
    assert not fills(resumed)
    resumed.close()


def test_same_quote_tail_then_eligible_candidate_can_enter_once(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    engine.process_snapshot(strict(ts=100, exposure_eligible=False))
    assert not fills(engine)
    engine.process_snapshot(strict(ts=105, quote=100))
    pos = engine.runtimes[0].open_by_mint["OFFLINE_TEST_MINT"]
    assert pos.latest_price_epoch == 100
    assert pos.opened_at_epoch == 105
    assert len(fills(engine)) == 1
    engine.process_snapshot(strict(ts=110, quote=100))
    assert len(fills(engine)) == 1
    assert pos.latest_price_epoch == 100
    engine.close()


def test_live_wall_clock_blocks_historical_backlog_entry(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), mode=MODE_LIVE_PAPER,
                                quiet=True, wall_clock=lambda: 1000)
    engine.process_snapshot(strict(ts=100, quote_ttl_seconds=300,
        pricing_coverage={"lease_until_utc": "1970-01-01T00:30:00Z"}))
    assert not fills(engine)
    engine.close()


def test_live_expired_coverage_blocks_entry_but_not_fresh_exit(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), mode=MODE_LIVE_PAPER,
                                quiet=True, wall_clock=lambda: 1000)
    expired = {"lease_until_utc": "1970-01-01T00:16:35Z"}
    valid = {"lease_until_utc": "1970-01-01T00:30:00Z"}
    engine.process_snapshot(strict(ts=990, quote_ttl_seconds=300, pricing_coverage=expired))
    assert not fills(engine)
    engine.process_snapshot(strict(ts=991, quote=990, quote_ttl_seconds=300,
                                   pricing_coverage=valid))
    assert len(fills(engine)) == 1
    engine.process_snapshot(strict(1.35, 995, quote_ttl_seconds=300,
                                   pricing_coverage=expired))
    assert len(fills(engine)) == 2
    engine.close()


@pytest.mark.parametrize("field", ["risk_assessed_epoch", "security_assessed_epoch",
                                   "market_cap_observed_epoch", "liquidity_observed_epoch"])
def test_live_stale_assessment_blocks_new_exposure(tmp_path, field):
    engine = PaperTradingEngine(config(tmp_path), mode=MODE_LIVE_PAPER,
                                quiet=True, wall_clock=lambda: 1000)
    observation = strict(ts=990, quote_ttl_seconds=300,
        pricing_coverage={"lease_until_utc": "1970-01-01T00:30:00Z"})
    observation.extra[field] = 690
    engine.process_snapshot(observation)
    assert not fills(engine)
    engine.close()


@pytest.mark.parametrize("stop_kind", ["before_poll", "during_poll", "runtime"])
def test_no_delivery_after_stop_or_runtime_limit(tmp_path, stop_kind):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    source = Source()
    calls = []
    stop = {"value": stop_kind == "before_poll"}
    clock = {"now": 0.0}
    original = source.poll
    def poll():
        value = original()
        if stop_kind == "during_poll":
            stop["value"] = True
        elif stop_kind == "runtime":
            clock["now"] = 2.0
        return value
    source.poll = poll
    result = run_live_loop(engine, source, should_stop=lambda: stop["value"],
        clock=lambda: clock["now"], max_runtime_seconds=1, after_commit=lambda owner: calls.append(1))
    assert result.stop_reason in ("STOP_REQUESTED", "MAX_RUNTIME")
    assert not calls
    engine.close()


def test_state_limit_rolls_back_before_new_coverage_pin(tmp_path, monkeypatch):
    from PHX2.paper_trading import ledger
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    monkeypatch.setattr(ledger, "MAX_STATE_BYTES", 100)
    with pytest.raises(ValueError, match="RETENTION_LIMIT"):
        engine.process_snapshot(snap())
    assert not fills(engine)
    assert not engine.runtimes[0].open_by_mint
    assert not (Path(engine.run_dir) / STATE_FILE).exists()
    engine.close()


def test_same_quote_new_liquidity_collapse_still_protectively_closes(tmp_path):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    engine.process_snapshot(strict(ts=100))
    observation = strict(ts=110, quote=100)
    observation.liquidity_usd = 10
    engine.process_snapshot(observation)
    assert not engine.runtimes[0].open_by_mint
    closed = next(iter(engine._final_records.values()))
    assert closed["status"] == "RUGGED"
    assert "LIQUIDITY_COLLAPSE" in closed["reason_closed"]
    assert [event["transition"] for event in engine.notification_events.values()] == ["ENTRY", "FINAL_EXIT"]
    engine.close()


@pytest.mark.parametrize("lp_time", [-500, 120])
def test_same_quote_stale_or_future_liquidity_cannot_fake_collapse(tmp_path, lp_time):
    engine = PaperTradingEngine(config(tmp_path), quiet=True)
    engine.process_snapshot(strict(ts=100))
    observation = strict(ts=110, quote=100)
    observation.liquidity_usd = 10
    observation.extra["liquidity_observed_epoch"] = lp_time
    engine.process_snapshot(observation)
    pos = engine.runtimes[0].open_by_mint[observation.mint]
    assert pos.latest_liquidity == 50_000
    assert len(fills(engine)) == 1
    engine.close()
