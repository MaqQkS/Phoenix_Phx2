"""Single-stream PHX1-parity production proofs.

Covers the simplification-specific requirements not already proven elsewhere:
the verifier cannot stop production because none exists; the ordinary
$4,500 market liquidity floor still blocks; an eligible single-stream
candidate reaches compose/reservation offline with a fake transport; the
real ping ledgers stay untouched; status surfaces one stream + verifier
DISABLED + LP_INTEGRITY_MODE; legacy LP artifacts (locks, proofs, reason
codes) cannot poison a new run; paper and dashboard tolerate LP Integrity
DISABLED; and restart preserves core migration/fee/watch state.

No test opens a network connection or sends anything.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from PHX2.dashboard.adapter import build_candidate_rows
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.compat.production_live_runner import (
    liquidity_floor_block_reason,
)
from PHX2.free_tier_producer.fee_gate_lifecycle import (
    FeeGateLifecycleIndex,
    LEGACY_LP_STATE_IGNORED_SINGLE_STREAM,
    LIFECYCLE_DURABLE_SCAM_LOCKED,
    SEVERE_PROOF_LP_REMOVAL_COMPOSITE,
)
from PHX2.free_tier_producer.migration_admission import (
    MigrationProofStore,
    evaluate_migration_admission,
)
from PHX2.free_tier_producer.scam_policy import (
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    POLICY_ALLOW,
    evaluate_delivery_safety,
)
from PHX2.paper_trading.config import (
    PROFILE_FIXED_USD,
    STRATEGY_CONFIG_PLAN,
    PaperConfig,
    SizingProfileConfig,
    StrategyConfig,
    default_strategy_params,
)
from PHX2.paper_trading.engine import PaperTradingEngine
from PHX2.paper_trading.ledger import read_jsonl
from PHX2.paper_trading.models import CandidateSnapshot
from PHX2.paper_trading.pricing import normalize_record
from PHX2.runtime import production_supervisor as ps
from PHX2.runtime.production_entrypoint import print_status
from PHX2.tests.test_composite_scam_policy import (
    MINT,
    PHX1_FEE_GATE_NORMAL,
    _fee,
)
from PHX2.tests.test_fee_gate_lifecycle import (
    BASE,
    _healthy_mature_state,
    _scam_mature_state,
    _snap,
)
from PHX2.tests.test_migration_admission import build_pool_creation_update


NOW = "2026-07-15T12:00:00Z"


def _allow_decision():
    decision = evaluate_delivery_safety(fee_snapshot=_fee(PHX1_FEE_GATE_NORMAL))
    assert decision.verdict == POLICY_ALLOW
    assert decision.lp_integrity_mode == LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM
    return decision


# ---------------------------------------------------------------------------
# Verifier failure cannot stop production (no verifier exists)
# ---------------------------------------------------------------------------


def test_verifier_failure_state_cannot_produce_a_production_stop_reason():
    """The only automatic-stop authority over the paid stream owner is
    ``paid_provider_safety_error`` plus the topology caps.  Feed it snapshots
    poisoned with every verifier failure shape the old two-stream world could
    produce: none stops production, because no verifier field participates."""
    healthy_primary = {
        "status": "CONNECTED", "max_active_streams": 1, "reconnects": 0,
        "handoff_artifact_errors": 0,
    }
    for poisoned in (
        {"verifier": {"status": "AUTH_FAILED", "terminal_auth_failure": True}},
        {"verifier_stream_status": "AUTH_FAILED"},
        {"verifier_active_streams": 0, "verifier_max_active_streams": 0,
         "verifier": {"stream_errors": 99, "reconnects": 99}},
        {"verifier": {"status": "STOPPED"}},
    ):
        snapshot = {**healthy_primary, **poisoned}
        assert producer_session.paid_provider_safety_error(
            snapshot, max_reconnects=5) is None


def test_session_topology_constants_pin_single_stream():
    assert producer_session.PRIMARY_STREAM_MAX == 1
    assert producer_session.VERIFIER_STREAM_MAX == 0
    assert producer_session.MAX_ACTIVE_STREAMS == 1
    assert producer_session.LP_INTEGRITY_MODE == "DISABLED_SINGLE_STREAM"
    assert ps.PRIMARY_MAX_GRPC_STREAMS == 1
    assert ps.VERIFIER_MAX_GRPC_STREAMS == 0
    assert ps.MAX_GRPC_STREAMS == 1
    assert ps.LP_INTEGRITY_MODE == "DISABLED_SINGLE_STREAM"


# ---------------------------------------------------------------------------
# Ordinary market liquidity-dollar floor is preserved ($4,500)
# ---------------------------------------------------------------------------


def test_liquidity_floor_4500_still_blocks_and_fails_closed():
    floor = Decimal("4500")
    below = liquidity_floor_block_reason(
        MINT, {"liquidity_usd": "4499.99"}, min_liquidity_usd=floor)
    assert below is not None and below.startswith("LIQUIDITY_USD_BELOW_MIN")
    assert liquidity_floor_block_reason(
        MINT, {"liquidity_usd": "4500"}, min_liquidity_usd=floor) is None
    # Stale/missing/malformed liquidity fails closed at compose time.
    for bad in ({}, {"liquidity_usd": None}, {"liquidity_usd": "NaN"},
                {"liquidity_usd": "-1"}, {"liquidity_usd": "abc"}):
        assert liquidity_floor_block_reason(
            MINT, bad, min_liquidity_usd=floor) is not None


class _Sidecar:
    def __init__(self, liquidity_usd):
        self.liquidity_usd = liquidity_usd

    def resolve(self, mint, **kwargs):
        return {
            "current_price": "0.001",
            "current_market_cap_usd": "45000",
            "liquidity_usd": self.liquidity_usd,
            "market_context_fetched_at_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "all_present": True,
            "basis": "REAL_MARKET_PRESENT",
            "attempts": [],
        }


class _LowRisk:
    def observe_market_sample(self, mint, market):
        return None

    def assess(self, mint):
        return {"risk_label": "RISK_LOW", "risk_reasons": []}


class _NoErrors:
    count = 0

    def log(self, *args, **kwargs):
        self.count += 1


def _eligible_activation_gate(cand, ctx):
    return {"activation": {"activation_proven": True,
                           "activation_state": "ACTIVE_DIP_WATCH"},
            "eligible": True, "reason": None}


def _run_single_stream_candidate(tmp_path, monkeypatch, *, liquidity_usd,
                                 floor_counts=None):
    compose_calls = {"count": 0}

    def compose_stub(*args, **kwargs):
        compose_calls["count"] += 1
        # The security decision travels bound into the composer seam.
        assert kwargs["security_decision"] is not None
        assert kwargs["security_decision"].lp_snapshot is None
        return {
            "compose_decision": "NO_SEND_DISPATCHED",
            "compose_reason": "DISPATCHABLE",
            "eligible": True,
            "send_result": object(),
            "delivery": {"delivery_state": "SENT_OK_COMMITTED",
                         "attempt_id": "stub-attempt", "message_id": None,
                         "ledger_committed": True},
        }

    monkeypatch.setattr(
        producer_session.sess.cs, "compose_and_maybe_send", compose_stub)

    counts = floor_counts if floor_counts is not None else {
        "liquidity_floor_pass": 0, "liquidity_floor_fail": 0}

    def counted_floor(mint, ctx):
        reason = liquidity_floor_block_reason(
            mint, ctx, min_liquidity_usd=Decimal("4500"))
        counts["liquidity_floor_fail" if reason else "liquidity_floor_pass"] += 1
        return reason

    gate = producer_session.make_discord_risk_gate(
        risk_engine=_LowRisk(),
        discord_block_ledger=producer_session.DiscordBlockLedger(),
        discord_blocks_path=tmp_path / "blocks.jsonl",
        min_liquidity_usd=Decimal("4500"),
        mode="PAID_PRIMARY_TELEGRAM",
        errors=_NoErrors(),
        floor_fn=counted_floor,
    )
    decision = _allow_decision()
    result = producer_session.sess.run_cap1_candidates(
        [{
            "token_mint": MINT,
            "candidate_id": "single-stream-candidate",
            "migration_time_utc": NOW,
            "source_ref": "paid-grpc",
            "symbol_or_name": None,
            "security_decision": decision,
        }],
        sidecar=_Sidecar(liquidity_usd),
        ath_transport=object(),
        ath_endpoint_secret=object(),
        now_utc=datetime.now(timezone.utc),
        now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        sleep_fn=lambda _seconds: None,
        ledger=object(),
        guard=object(),        # fake transport seam: nothing real constructed
        authorization=object(),
        created_at_utc=NOW,
        pre_reserve_gate_fn=gate,
        activation_gate_fn=_eligible_activation_gate,
    )
    return result, compose_calls["count"], counts


def test_below_floor_candidate_never_reaches_compose_or_reservation(
        tmp_path, monkeypatch):
    result, compose_calls, counts = _run_single_stream_candidate(
        tmp_path, monkeypatch, liquidity_usd="4499.99")
    record = result["per_candidate"][0]
    assert result["outcome"] == "ZERO_SEND"
    assert result["sent_attempt"] is None
    assert compose_calls == 0
    assert record["reason"].startswith("LIQUIDITY_USD_BELOW_MIN")
    assert counts == {"liquidity_floor_pass": 0, "liquidity_floor_fail": 1}


def test_eligible_single_stream_candidate_reaches_compose_and_reservation_offline(
        tmp_path, monkeypatch):
    """Required proof: with the PHX1 filters green (security ALLOW without
    any LP verdict, risk low, floor pass, activation eligible) the candidate
    reaches the compose/reservation seam — entirely offline over fake
    transport objects; nothing network-capable exists in the harness."""
    result, compose_calls, counts = _run_single_stream_candidate(
        tmp_path, monkeypatch, liquidity_usd="15000")
    record = result["per_candidate"][0]
    assert result["outcome"] == "ONE_SEND_COMMITTED"
    assert record["reason"] == "SENT_OK_COMMITTED"
    assert compose_calls == 1
    assert counts == {"liquidity_floor_pass": 1, "liquidity_floor_fail": 0}


def test_real_ping_ledgers_are_never_touched_by_the_offline_suite(
        tmp_path, monkeypatch):
    active = ps.DEFAULT_ACTIVE_LEDGER
    frozen = ps.DEFAULT_FROZEN_LEDGER
    if not (active.is_file() and frozen.is_file()):
        pytest.skip("real operator ledgers not present on this machine")
    before_active = hashlib.sha256(active.read_bytes()).hexdigest()
    before_frozen = ps.ledger_baseline(frozen)
    assert before_frozen.as_tuple() == ps.EXPECTED_FROZEN_LEDGER
    _run_single_stream_candidate(tmp_path, monkeypatch, liquidity_usd="15000")
    assert hashlib.sha256(active.read_bytes()).hexdigest() == before_active
    assert ps.ledger_baseline(frozen) == before_frozen


# ---------------------------------------------------------------------------
# Status: one stream, verifier DISABLED, LP_INTEGRITY_MODE surfaced
# ---------------------------------------------------------------------------


def test_print_status_shows_single_stream_topology(capsys):
    print_status({
        "active": True,
        "lock_state": "ACTIVE",
        "run_dir": "X",
        "supervisor_pid": 1,
        "processes": {},
        "operator_console": {},
        "primary_stream_status": "CONNECTED",
        "verifier_stream_status": "DISABLED",
        "lp_integrity_mode": "DISABLED_SINGLE_STREAM",
        "grpc_status": "CONNECTED",
        "active_streams": 1,
        "max_active_streams": 1,
    })
    out = capsys.readouterr().out
    assert "PRIMARY_STREAM_STATUS=CONNECTED" in out
    assert "VERIFIER_STREAM_STATUS=DISABLED" in out
    assert "LP_INTEGRITY_MODE=DISABLED_SINGLE_STREAM" in out
    assert "ACTIVE_STREAMS=1" in out
    assert "MAX_ACTIVE_STREAMS=1" in out
    assert "GRPC_STATUS=CONNECTED" in out


# ---------------------------------------------------------------------------
# Legacy LP artifact state cannot poison a new single-stream candidate
# ---------------------------------------------------------------------------


def _persisted_lifecycle_file(tmp_path, *, severe_lp_lock):
    path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=path)
    if severe_lp_lock:
        # One mature structural SCAM observation + the historical LP-removal
        # severe proof: locks with provisional_scam_count == 1 (< required 2).
        view = index.observe(
            _snap(_scam_mature_state(), now_epoch=BASE + 400),
            now_epoch=BASE + 400, severe_structural_proof=True)
        assert view.artifact["durable_scam_locked"] is True
        assert SEVERE_PROOF_LP_REMOVAL_COMPOSITE in view.artifact[
            "durable_lock_reasons"]
        assert view.artifact["provisional_scam_count"] == 1
    else:
        # Two distinct mature structural confirmations + LP severe proof on
        # the second: the lock is independently fee-justified.
        index.observe(_snap(_scam_mature_state(), now_epoch=BASE + 400),
                      now_epoch=BASE + 400)
        view = index.observe(
            _snap(_scam_mature_state(events=40, txs=40, last_epoch=BASE + 500,
                                     scale=2),
                  now_epoch=BASE + 520),
            now_epoch=BASE + 520, severe_structural_proof=True)
        assert view.artifact["durable_scam_locked"] is True
        assert view.artifact["provisional_scam_count"] == 2
    return path


def test_restored_lp_only_durable_lock_is_ignored_with_observable_marker(tmp_path):
    path = _persisted_lifecycle_file(tmp_path, severe_lp_lock=True)
    restarted = FeeGateLifecycleIndex(path=path)
    assert restarted.is_durably_locked(MINT) is False
    stats = restarted.stats()
    assert stats["fee_lifecycle_legacy_lp_locks_ignored"] == 1
    assert stats["fee_lifecycle_restored_locks"] == 0
    # The candidate is fail-closed (stale until fresh evidence), NOT locked:
    # a fresh healthy mature observation recovers send eligibility.
    now = BASE + 1000
    view = restarted.observe(
        _snap(_healthy_mature_state(last_epoch=now - 20), now_epoch=now),
        now_epoch=now)
    assert view.lifecycle_state != LIFECYCLE_DURABLE_SCAM_LOCKED
    assert view.send_block_reasons == ()
    assert view.artifact["legacy_lp_state"] == LEGACY_LP_STATE_IGNORED_SINGLE_STREAM
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_ALLOW


def test_restored_fee_justified_lock_survives_with_lp_token_stripped(tmp_path):
    path = _persisted_lifecycle_file(tmp_path, severe_lp_lock=False)
    restarted = FeeGateLifecycleIndex(path=path)
    assert restarted.is_durably_locked(MINT) is True
    stats = restarted.stats()
    assert stats["fee_lifecycle_legacy_lp_locks_ignored"] == 0
    assert stats["fee_lifecycle_restored_locks"] == 1
    view = restarted.observe(
        _snap(_healthy_mature_state(last_epoch=BASE + 900), now_epoch=BASE + 950),
        now_epoch=BASE + 950)
    assert view.lifecycle_state == LIFECYCLE_DURABLE_SCAM_LOCKED
    assert SEVERE_PROOF_LP_REMOVAL_COMPOSITE not in view.artifact[
        "durable_lock_reasons"]


def test_old_schema_migration_proofs_are_dropped_not_trusted(tmp_path):
    proof = evaluate_migration_admission(build_pool_creation_update()).proof
    legacy_payload = proof.to_dict()
    # A pre-migrate_v2 (V1-schema) line: no instruction-version field and a
    # digest sealed over the old field set.
    legacy_payload.pop("migration_instruction_version")
    legacy_payload["proof_version"] = "PHX2_MIGRATION_PROOF_V1"
    path = tmp_path / "migration_proofs.jsonl"
    path.write_text(json.dumps(legacy_payload, sort_keys=True) + "\n",
                    encoding="utf-8")
    store = MigrationProofStore(path)
    assert store.all_proofs() == ()
    assert store.stats()["proof_load_dropped"] == 1
    # A NEW sealed proof still round-trips the same file (restart-safe).
    assert store.seal_and_store(proof)
    restored = MigrationProofStore(path)
    assert restored.get(proof.candidate_mint).proof_digest == proof.proof_digest
    assert restored.stats()["proof_load_dropped"] == 1


# ---------------------------------------------------------------------------
# Dashboard and paper tolerate LP Integrity DISABLED
# ---------------------------------------------------------------------------


def _disabled_candidate_record(decision):
    return producer_session.artifacts.build_candidate_recheck_record(
        rec={
            "token_mint": MINT,
            "reason": "SEND_ATTEMPTED",
            "compose_attempted": True,
            "reservation_attempted": True,
            "market_context": {
                "current_price": "0.0001",
                "current_market_cap_usd": "100000",
                "liquidity_usd": "50000",
                "market_context_fetched_at_utc": NOW,
            },
        },
        entry=None, cycle=1, observed_at_utc=NOW, ledger_touched=False,
        transport_attempted=False, security=decision,
    )


def test_dashboard_and_paper_tolerate_lp_integrity_disabled(tmp_path):
    decision = _allow_decision()
    sealed = decision.to_dict()
    assert sealed["lp_snapshot"] is None
    candidate = _disabled_candidate_record(decision)
    # The runner-enriched shape for single-stream candidates.
    candidate["lp_integrity"] = {
        "lp_integrity": "DISABLED",
        "lp_integrity_mode": decision.lp_integrity_mode,
    }
    candidate["scam_policy"] = sealed
    candidate["fee_gate"] = sealed["fee_snapshot"]

    paper = normalize_record(candidate)
    assert paper is not None
    assert paper.lp_integrity.get("lp_integrity") == "DISABLED"

    producer = {
        "watch": {"candidate-1": {
            "candidate_id": "candidate-1", "token_mint": MINT,
            "status": "ACTIVE_DIP_WATCH", "activation_proven": True,
            "seeded_at_utc": NOW, "last_observed_at_utc": NOW,
        }},
        "candidates": {"candidate-1": {"last": candidate}},
        "ath_state": {},
    }
    row = build_candidate_rows(
        producer, datetime.fromtimestamp(1_800_000_000, timezone.utc))[0]
    assert row["lpIntegrity"] == "DISABLED"
    assert row["lpIntegrity"] != "PASS"
    assert row["compositeVerdict"] == "ALLOW"

    cfg = PaperConfig()
    cfg.run.output_root = str(tmp_path)
    cfg.run.run_id = "lp-disabled"
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
        fee_gate=sealed["fee_snapshot"],
        lp_integrity={"lp_integrity": "DISABLED",
                      "lp_integrity_mode": decision.lp_integrity_mode},
        scam_policy=sealed,
    ))
    engine.close()
    events = read_jsonl(str(Path(engine.run_dir) / "paper_events.jsonl"))
    assert not any(
        row.get("event") == "ENTRY_SKIPPED_SECURITY_POLICY" for row in events)


# ---------------------------------------------------------------------------
# Restart preserves core migration/fee/watch state (single-stream artifacts)
# ---------------------------------------------------------------------------


def test_restart_preserves_migration_proof_fee_lifecycle_and_dedupe_state(tmp_path):
    # Migration admission proof: sealed under the new schema, reload-verified.
    decision = evaluate_migration_admission(build_pool_creation_update())
    proof_path = tmp_path / "migration_proofs.jsonl"
    assert MigrationProofStore(proof_path).seal_and_store(decision.proof)
    restored_store = MigrationProofStore(proof_path)
    restored = restored_store.get(decision.proof.candidate_mint)
    assert restored is not None
    assert restored.migration_instruction_version == "migrate"
    assert restored.proof_digest == decision.proof.proof_digest

    # Fee Gate lifecycle: a healthy confirmed record restores as-is.
    lifecycle_path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=lifecycle_path)
    index.observe(_snap(_healthy_mature_state(), now_epoch=BASE + 400),
                  now_epoch=BASE + 400)
    restarted = FeeGateLifecycleIndex(path=lifecycle_path)
    assert restarted.stats()["fee_lifecycle_restored_records"] == 1
    assert restarted.stats()["fee_lifecycle_legacy_lp_locks_ignored"] == 0

    # Dedupe ledger: an appended reservation line survives restart untouched.
    from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import JsonlPingDedupeLedger
    ledger_path = tmp_path / "ping_dedupe.jsonl"
    ledger_path.write_text("", encoding="utf-8")
    JsonlPingDedupeLedger(path=ledger_path)
    line = json.dumps({"kind": "test", "token_mint": MINT}) + "\n"
    ledger_path.write_text(line, encoding="utf-8")
    reloaded = JsonlPingDedupeLedger(path=ledger_path)
    assert reloaded is not None
    assert ledger_path.read_text(encoding="utf-8") == line


def test_forged_single_stream_decision_with_lp_snapshot_fails_validation():
    from PHX2.free_tier_producer.scam_policy import (
        seal_delivery_decision,
        validate_delivery_decision,
    )
    from PHX2.tests.test_composite_scam_policy import _lp

    good = _allow_decision()
    forged = seal_delivery_decision(replace(good, lp_snapshot=_lp()))
    valid, _reason = validate_delivery_decision(forged)
    assert valid is False
