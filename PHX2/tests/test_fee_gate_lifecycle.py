"""Deterministic Fee Gate lifecycle tests (stale recovery + durable locks).

Covers the 2026-07-17 lifecycle correction: stale/immature evidence must not
permanently poison a candidate; durable scam locks require fresh mature
structural confirmation across distinct evidence versions; Telegram compose
still fails closed at the send boundary.  No test opens a network connection,
sends Telegram/Discord, or touches the real ledgers — every store path is a
pytest tmp_path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.dashboard.adapter import build_candidate_rows
from PHX2.delivery.telegram_adapter import TelegramDeliveryAdapter
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.fee_gate_lifecycle import (
    FEE_GATE_LIFECYCLE_VERSION,
    LIFECYCLE_BLOCK_DURABLE_LOCK,
    LIFECYCLE_BLOCK_EVIDENCE_UNBOUND,
    LIFECYCLE_BLOCK_IMMATURE,
    LIFECYCLE_BLOCK_PROVISIONAL,
    LIFECYCLE_BLOCK_STALE,
    LIFECYCLE_BLOCK_STATE_INVALID,
    LIFECYCLE_DURABLE_SCAM_LOCKED,
    LIFECYCLE_FRESH_CONFIRMED,
    LIFECYCLE_FRESH_PROVISIONAL,
    LIFECYCLE_IMMATURE,
    LIFECYCLE_TEMPORARILY_STALE,
    MATURITY_CONFIRMED,
    MATURITY_IMMATURE,
    SEVERE_PROOF_LP_REMOVAL_COMPOSITE,
    FeeGateLifecycleConfig,
    FeeGateLifecycleIndex,
    build_fee_gate_lifecycle_config,
    evidence_identity_digest,
    make_fee_gate_send_time_gate,
)
from PHX2.free_tier_producer.phx1_fee_gate import (
    BLOCK_DATA_STALE,
    BLOCK_PROOF_MISSING,
    BLOCK_SCAM_LIKELY,
    FEE_GATE_UNKNOWN,
    PHX1_FEE_GATE_NORMAL,
    PHX1_FEE_GATE_SCAM_LIKELY,
    REASON_BRIBES_STARVED,
    REASON_CREATOR_DOMINANCE,
    REASON_STICKY_LOCK,
    REASON_THIN_SAMPLE,
    build_fee_snapshot,
    validate_fee_snapshot,
)
from PHX2.free_tier_producer.scam_policy import (
    POLICY_ALLOW,
    POLICY_HARD_BLOCK,
    SecurityDecisionIndex,
    evaluate_delivery_safety,
)
from PHX2.paper_trading.pricing import normalize_record
from PHX2.tests.test_composite_scam_policy import MINT, WSOL


BASE = 1_700_000_000


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(
        int(epoch), timezone.utc).isoformat().replace("+00:00", "Z")


def _state(*, events, txs, first_epoch, last_epoch,
           lp=600_000_000, protocol=200_000_000, creator=200_000_000,
           priority=100_000_000):
    return {
        "quote_mint": WSOL, "quote_asset": "SOL", "pair_type": "TOKEN_SOL",
        "unit": "SOL",
        "lp": lp, "protocol": protocol, "creator": creator,
        "base": 5_000_000, "priority": priority, "jito": 0,
        "events": events, "signatures": {f"sig-{i}" for i in range(txs)},
        "first": _iso(first_epoch), "last": _iso(last_epoch),
        "last_epoch": last_epoch,
        "recent": (), "tx_ante": (),
    }


def _healthy_mature_state(*, first_epoch=BASE, last_epoch=BASE + 380):
    # 600 tx / 600 events over >300s with bribes >=8% -> Normal, no thin_sample.
    return _state(events=600, txs=600, first_epoch=first_epoch,
                  last_epoch=last_epoch)


def _scam_mature_state(*, events=30, txs=30, first_epoch=BASE,
                       last_epoch=BASE + 380, scale=1):
    # creator-dominant + bribes-starved -> SCAM Likely with structural reasons
    # (bribes_starved, creator_dom_hi) plus the still-visible thin_sample.
    return _state(events=events, txs=txs, first_epoch=first_epoch,
                  last_epoch=last_epoch,
                  lp=100_000_000 * scale, protocol=100_000_000 * scale,
                  creator=800_000_000 * scale, priority=10_000_000 * scale)


def _scam_thin_immature_state(*, first_epoch, last_epoch):
    # bribes_starved + thin_sample only (score 4) on a tiny brand-new sample.
    return _state(events=3, txs=3, first_epoch=first_epoch,
                  last_epoch=last_epoch, priority=10_000_000)


def _snap(state, *, now_epoch, mint=MINT):
    return build_fee_snapshot(mint, state=state, now_epoch=now_epoch)


def _stale_snap(state, *, now_epoch, mint=MINT):
    snapshot = build_fee_snapshot(mint, state=state, now_epoch=now_epoch)
    assert snapshot.fee_gate_label == FEE_GATE_UNKNOWN
    assert BLOCK_DATA_STALE in snapshot.fee_gate_reasons
    return snapshot


class FakeFeeIndex:
    """Deterministic FeeEvidenceIndex stand-in for the send-time gate."""

    def __init__(self, state):
        self.state = state

    def snapshot(self, mint, *, now_epoch, max_age_seconds):
        return build_fee_snapshot(
            str(mint), state=self.state, now_epoch=now_epoch,
            max_age_seconds=max_age_seconds)


# ---------------------------------------------------------------------------
# 1. genuine migration with a thin sample
# ---------------------------------------------------------------------------

def test_genuine_thin_start_is_immature_without_lock_or_send_authorization():
    index = FeeGateLifecycleIndex()
    now = BASE + 40
    snapshot = _snap(_state(events=3, txs=3, first_epoch=BASE + 20,
                            last_epoch=BASE + 30), now_epoch=now)
    assert REASON_THIN_SAMPLE in snapshot.fee_gate_reasons   # stays visible
    view = index.observe(snapshot, now_epoch=now)
    assert view.lifecycle_state == LIFECYCLE_IMMATURE
    assert view.maturity == MATURITY_IMMATURE
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_IMMATURE,)
    assert view.artifact["durable_scam_locked"] is False
    assert view.effective_snapshot is snapshot   # no sticky rewrite
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_HARD_BLOCK
    assert LIFECYCLE_BLOCK_IMMATURE in decision.final_block_reasons
    assert not decision.telegram_transport_allowed


def test_fresh_provisional_between_floors_blocks_send_but_shows_verdict():
    index = FeeGateLifecycleIndex()
    now = BASE + 130
    view = index.observe(
        _snap(_state(events=8, txs=8, first_epoch=BASE, last_epoch=BASE + 120),
              now_epoch=now),
        now_epoch=now)
    assert view.lifecycle_state == LIFECYCLE_FRESH_PROVISIONAL
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_PROVISIONAL,)
    assert view.current_verdict != FEE_GATE_UNKNOWN


# ---------------------------------------------------------------------------
# 2. bribes_starved + thin_sample during immature evidence cannot sticky lock
# ---------------------------------------------------------------------------

def test_immature_bribes_starved_thin_sample_scam_cannot_sticky_lock():
    index = FeeGateLifecycleIndex()
    now = BASE + 40
    snapshot = _snap(_scam_thin_immature_state(
        first_epoch=BASE + 20, last_epoch=BASE + 30), now_epoch=now)
    assert snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    assert set(snapshot.fee_gate_reasons) >= {
        REASON_BRIBES_STARVED, REASON_THIN_SAMPLE}
    view = index.observe(snapshot, now_epoch=now)
    # Provisional block today (the snapshot itself is a SCAM hard block)...
    assert view.effective_snapshot.hard_block is True
    assert view.lifecycle_state == LIFECYCLE_IMMATURE
    # ...but immature evidence never confirms or locks.
    assert view.artifact["provisional_scam_count"] == 0
    assert view.artifact["durable_scam_locked"] is False
    assert index.is_durably_locked(MINT) is False


def test_early_immature_scam_no_longer_poisons_later_healthy_evidence():
    """The exact prior defect: worst-score memory made this permanent."""

    index = FeeGateLifecycleIndex()
    index.observe(
        _snap(_scam_thin_immature_state(first_epoch=BASE + 20,
                                        last_epoch=BASE + 30),
              now_epoch=BASE + 40),
        now_epoch=BASE + 40)
    now = BASE + 400
    healthy = _snap(_healthy_mature_state(), now_epoch=now)
    view = index.observe(healthy, now_epoch=now)
    assert view.lifecycle_state == LIFECYCLE_FRESH_CONFIRMED
    assert view.send_block_reasons == ()
    assert view.effective_snapshot.fee_gate_label == PHX1_FEE_GATE_NORMAL
    assert REASON_STICKY_LOCK not in view.effective_snapshot.fee_gate_reasons
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_ALLOW


# ---------------------------------------------------------------------------
# 3. provisional scam recovers when healthier fresh evidence arrives
# ---------------------------------------------------------------------------

def test_provisional_scam_recovers_and_candidate_becomes_send_eligible():
    index = FeeGateLifecycleIndex()
    now = BASE + 400
    scam = _snap(_scam_mature_state(), now_epoch=now)
    assert scam.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    view = index.observe(scam, now_epoch=now)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False

    later = now + 60
    healthy = _snap(_healthy_mature_state(last_epoch=now + 50), now_epoch=later)
    view = index.observe(healthy, now_epoch=later)
    assert view.lifecycle_state == LIFECYCLE_FRESH_CONFIRMED
    assert view.artifact["provisional_scam_count"] == 0
    assert index.stats()["fee_gate_provisional_scam_recovered"] == 1
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_ALLOW


# ---------------------------------------------------------------------------
# 4. stale evidence: compose blocked, candidate state preserved
# ---------------------------------------------------------------------------

def test_stale_evidence_blocks_compose_but_preserves_last_fresh_state():
    index = FeeGateLifecycleIndex()
    state = _healthy_mature_state()
    index.observe(_snap(state, now_epoch=BASE + 400), now_epoch=BASE + 400)

    stale_now = BASE + 380 + 301   # last event + >300s
    stale = _stale_snap(state, now_epoch=stale_now)
    view = index.observe(stale, now_epoch=stale_now)
    assert view.lifecycle_state == LIFECYCLE_TEMPORARILY_STALE
    # The last fresh verdict is preserved, not overwritten by the stale tick.
    assert view.artifact["last_fresh_verdict"] == PHX1_FEE_GATE_NORMAL
    assert view.artifact["last_fresh_maturity"] == MATURITY_CONFIRMED
    assert view.artifact["stale_since_epoch"] == stale_now
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_STALE,)
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_HARD_BLOCK
    assert BLOCK_DATA_STALE in decision.final_block_reasons
    assert LIFECYCLE_BLOCK_STALE in decision.final_block_reasons
    assert not decision.compose_allowed
    assert not decision.reservation_allowed
    assert not decision.ledger_mutation_allowed
    assert not decision.telegram_transport_allowed


# ---------------------------------------------------------------------------
# 5. fresh evidence after stale recovers the same candidate
# ---------------------------------------------------------------------------

def test_fresh_evidence_after_stale_recovers_the_same_candidate():
    index = FeeGateLifecycleIndex()
    state = _healthy_mature_state()
    index.observe(_snap(state, now_epoch=BASE + 400), now_epoch=BASE + 400)
    stale_now = BASE + 700
    index.observe(_stale_snap(state, now_epoch=stale_now), now_epoch=stale_now)
    assert index.stats()["fee_gate_temporarily_stale"] == 1

    recovered_state = _healthy_mature_state(last_epoch=BASE + 720)
    view = index.observe(
        _snap(recovered_state, now_epoch=BASE + 730), now_epoch=BASE + 730)
    assert view.lifecycle_state == LIFECYCLE_FRESH_CONFIRMED
    assert view.send_block_reasons == ()
    assert view.artifact["stale_since_epoch"] is None
    stats = index.stats()
    # Stale history stays observable through the counters.
    assert stats["fee_gate_recovered_from_stale"] == 1
    assert stats["fee_gate_temporarily_stale"] == 1


# ---------------------------------------------------------------------------
# 6. mature confirmed scam -> durable lock -> restart persistence
# ---------------------------------------------------------------------------

def test_mature_confirmed_scam_locks_durably_and_survives_restart(tmp_path):
    path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=path)
    first = _snap(_scam_mature_state(), now_epoch=BASE + 400)
    view = index.observe(first, now_epoch=BASE + 400)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False

    second = _snap(_scam_mature_state(events=40, txs=40, last_epoch=BASE + 500,
                                      scale=2),
                   now_epoch=BASE + 520)
    assert second.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    assert evidence_identity_digest(second) != evidence_identity_digest(first)
    view = index.observe(second, now_epoch=BASE + 520)
    assert view.artifact["provisional_scam_count"] == 2
    assert view.artifact["durable_scam_locked"] is True
    assert view.lifecycle_state == LIFECYCLE_DURABLE_SCAM_LOCKED
    assert LIFECYCLE_BLOCK_DURABLE_LOCK in view.artifact["durable_lock_reasons"]
    assert BLOCK_SCAM_LIKELY in view.artifact["durable_lock_reasons"]
    stamped = view.effective_snapshot
    assert stamped.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    assert REASON_STICKY_LOCK in stamped.fee_gate_reasons
    assert stamped.hard_block is True
    assert validate_fee_snapshot(stamped) == (True, None)

    restarted = FeeGateLifecycleIndex(path=path)
    assert restarted.is_durably_locked(MINT) is True
    stats = restarted.stats()
    assert stats["fee_lifecycle_restored_locks"] == 1
    assert stats["fee_lifecycle_load_dropped"] == 0


# ---------------------------------------------------------------------------
# 7. re-evaluating the identical frozen snapshot cannot double count
# ---------------------------------------------------------------------------

def test_identical_frozen_evidence_cannot_increment_confirmation_twice():
    index = FeeGateLifecycleIndex()
    state = _scam_mature_state()
    first_eval = _snap(state, now_epoch=BASE + 400)
    index.observe(first_eval, now_epoch=BASE + 400)
    # Same frozen evidence, later evaluation instant: sealed digest differs but
    # the evidence identity is unchanged -> no second confirmation, no lock.
    second_eval = _snap(state, now_epoch=BASE + 450)
    assert second_eval.proof_digest != first_eval.proof_digest
    assert evidence_identity_digest(second_eval) == evidence_identity_digest(first_eval)
    view = index.observe(second_eval, now_epoch=BASE + 450)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False
    view = index.observe(first_eval, now_epoch=BASE + 460)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False


# ---------------------------------------------------------------------------
# 8. stale ticks cannot count toward confirmation or create a lock
# ---------------------------------------------------------------------------

def test_stale_ticks_cannot_confirm_or_lock():
    index = FeeGateLifecycleIndex()
    state = _scam_mature_state()
    index.observe(_snap(state, now_epoch=BASE + 400), now_epoch=BASE + 400)
    for offset in (800, 1200, 1600, 2000):
        view = index.observe(
            _stale_snap(state, now_epoch=BASE + offset), now_epoch=BASE + offset)
        assert view.lifecycle_state == LIFECYCLE_TEMPORARILY_STALE
        assert view.artifact["provisional_scam_count"] == 1
        assert view.artifact["durable_scam_locked"] is False
    assert index.stats()["fee_gate_temporarily_stale"] == 4


def test_missing_evidence_warmup_never_locks():
    index = FeeGateLifecycleIndex()
    for offset in (10, 20, 30):
        missing = build_fee_snapshot(MINT, state=None, now_epoch=BASE + offset)
        assert BLOCK_PROOF_MISSING in missing.fee_gate_reasons
        view = index.observe(missing, now_epoch=BASE + offset)
        assert view.lifecycle_state == LIFECYCLE_IMMATURE
        assert view.artifact["durable_scam_locked"] is False
        assert view.artifact["provisional_scam_count"] == 0


# ---------------------------------------------------------------------------
# 9. durable lock is immune to favorable evidence and survives restart
# ---------------------------------------------------------------------------

def _lock_mint(index):
    index.observe(_snap(_scam_mature_state(), now_epoch=BASE + 400),
                  now_epoch=BASE + 400)
    view = index.observe(
        _snap(_scam_mature_state(events=40, txs=40, last_epoch=BASE + 500,
                                 scale=2),
              now_epoch=BASE + 520),
        now_epoch=BASE + 520)
    assert view.artifact["durable_scam_locked"] is True
    return view


def test_durable_lock_cannot_be_cleared_by_favorable_evidence_or_restart(tmp_path):
    path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=path)
    _lock_mint(index)

    favorable = _snap(_healthy_mature_state(last_epoch=BASE + 900),
                      now_epoch=BASE + 950)
    view = index.observe(favorable, now_epoch=BASE + 950)
    assert view.lifecycle_state == LIFECYCLE_DURABLE_SCAM_LOCKED
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_DURABLE_LOCK,)
    assert view.effective_snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    # Favorable MC / ATH / liquidity / activation / tier live in OTHER gates;
    # the composite still hard-blocks on the lifecycle + stamped fee snapshot
    # even with a fully passing LP family.
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_HARD_BLOCK
    assert LIFECYCLE_BLOCK_DURABLE_LOCK in decision.final_block_reasons
    assert BLOCK_SCAM_LIKELY in decision.final_block_reasons

    restarted = FeeGateLifecycleIndex(path=path)
    assert restarted.is_durably_locked(MINT) is True
    view = restarted.observe(favorable, now_epoch=BASE + 960)
    assert view.lifecycle_state == LIFECYCLE_DURABLE_SCAM_LOCKED
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_DURABLE_LOCK,)


def test_staleness_never_clears_a_durable_lock():
    index = FeeGateLifecycleIndex()
    _lock_mint(index)
    view = index.observe(
        _stale_snap(_scam_mature_state(events=40, txs=40, last_epoch=BASE + 500,
                                       scale=2),
                    now_epoch=BASE + 2000),
        now_epoch=BASE + 2000)
    assert view.lifecycle_state == LIFECYCLE_DURABLE_SCAM_LOCKED
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_DURABLE_LOCK,)


# ---------------------------------------------------------------------------
# 10. severe single structural proof policy
# ---------------------------------------------------------------------------

def test_single_snapshot_cannot_lock_without_severe_proof_by_default():
    index = FeeGateLifecycleIndex()
    view = index.observe(_snap(_scam_mature_state(), now_epoch=BASE + 400),
                         now_epoch=BASE + 400)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False


def test_lp_removal_composite_severe_proof_locks_on_one_mature_snapshot():
    index = FeeGateLifecycleIndex()
    view = index.observe(
        _snap(_scam_mature_state(), now_epoch=BASE + 400),
        now_epoch=BASE + 400, severe_structural_proof=True)
    assert view.artifact["durable_scam_locked"] is True
    assert SEVERE_PROOF_LP_REMOVAL_COMPOSITE in view.artifact["durable_lock_reasons"]


def test_configured_severe_reason_locks_on_one_mature_snapshot():
    config = FeeGateLifecycleConfig(
        severe_single_snapshot_reasons=(REASON_CREATOR_DOMINANCE,))
    index = FeeGateLifecycleIndex(config=config)
    view = index.observe(_snap(_scam_mature_state(), now_epoch=BASE + 400),
                         now_epoch=BASE + 400)
    assert view.artifact["durable_scam_locked"] is True


def test_severe_proof_with_immature_evidence_still_cannot_lock():
    index = FeeGateLifecycleIndex()
    view = index.observe(
        _snap(_scam_thin_immature_state(first_epoch=BASE + 20,
                                        last_epoch=BASE + 30),
              now_epoch=BASE + 40),
        now_epoch=BASE + 40, severe_structural_proof=True)
    assert view.artifact["durable_scam_locked"] is False
    assert view.artifact["provisional_scam_count"] == 0


def test_config_rejects_sample_scarcity_as_structural_or_severe():
    with pytest.raises(ValueError):
        FeeGateLifecycleConfig(structural_scam_reasons=(REASON_THIN_SAMPLE,))
    with pytest.raises(ValueError):
        FeeGateLifecycleConfig(
            severe_single_snapshot_reasons=(REASON_THIN_SAMPLE,))
    with pytest.raises(ValueError):
        FeeGateLifecycleConfig(scam_confirmations_required=1)


def test_env_config_overrides_parse_and_malformed_values_refuse():
    config = build_fee_gate_lifecycle_config({
        "PHX2_FEE_LIFECYCLE_CONFIRMED_MIN_TRANSACTIONS": "30",
        "PHX2_FEE_LIFECYCLE_SCAM_CONFIRMATIONS": "3",
    }, freshness_max_age_seconds="300")
    assert config.confirmed_min_transaction_count == 30
    assert config.scam_confirmations_required == 3
    assert config.freshness_max_age_seconds == Decimal("300")
    for bad in ("abc", "-3", "1.5", "1e3"):
        with pytest.raises(ValueError):
            build_fee_gate_lifecycle_config(
                {"PHX2_FEE_LIFECYCLE_CONFIRMED_MIN_EVENTS": bad})
    with pytest.raises(ValueError):
        build_fee_gate_lifecycle_config(
            {"PHX2_FEE_LIFECYCLE_SCAM_CONFIRMATIONS": "1"})


# ---------------------------------------------------------------------------
# 11. compose-time race: activation fresh, fee gate stale before compose
# ---------------------------------------------------------------------------

class NeverTouchedLedger:
    def __getattr__(self, name):
        raise AssertionError(f"ledger_must_not_be_touched:{name}")


class AllPresentSidecar:
    def __init__(self, fetched_at_utc):
        self.fetched_at_utc = fetched_at_utc

    def resolve(self, mint, **kwargs):
        return {
            "all_present": True, "basis": "PRICE", "market_state": "READY",
            "market_reason_code": None, "next_market_refresh_at_utc": None,
            "market_attempt_count": 1, "market_state_transitions": [],
            "endpoint_attempts": {}, "attempts": [],
            "current_price": "0.0001", "current_market_cap_usd": "100000",
            "liquidity_usd": "50000",
            "market_context_fetched_at_utc": self.fetched_at_utc,
            "provider_timestamp_utc": self.fetched_at_utc,
            "pumpswap_reserve": {}, "central_ath": {},
        }


def test_compose_time_race_stale_fee_gate_blocks_with_zero_mutation():
    bind_epoch = BASE + 400
    race_epoch = BASE + 700   # evidence aged out between activation and compose
    state = _healthy_mature_state()

    lifecycle_index = FeeGateLifecycleIndex()
    security_index = SecurityDecisionIndex()
    bound_view = lifecycle_index.observe(
        _snap(state, now_epoch=bind_epoch), now_epoch=bind_epoch)
    assert bound_view.send_block_reasons == ()
    decision = evaluate_delivery_safety(
        fee_snapshot=bound_view.effective_snapshot,
        existing_block_reasons=bound_view.send_block_reasons)
    assert decision.verdict == POLICY_ALLOW
    security_index.bind(decision)

    send_gate = make_fee_gate_send_time_gate(
        fee_index=FakeFeeIndex(state), lifecycle_index=lifecycle_index,
        security_index=security_index, max_age_seconds="300",
        now_epoch_fn=lambda: race_epoch)

    def pre_reserve_gate(mint, ctx):
        reason = security_index.proof_gate(mint)
        if reason:
            return reason
        return send_gate(mint)

    def activation_gate(cand, ctx):
        return {"activation": {"activation_proven": True,
                               "activation_state": "ACTIVE_DIP_WATCH"},
                "eligible": True, "reason": None}

    result = producer_session.sess.run_cap1_candidates(
        [{"token_mint": MINT, "candidate_id": "candidate-1",
          "migration_time_utc": _iso(BASE), "security_decision": decision}],
        sidecar=AllPresentSidecar(_iso(race_epoch)),
        ath_transport=None, ath_endpoint_secret=None,
        now_utc=None, now_seconds=None, now_iso_fn=lambda: _iso(race_epoch),
        sleep_fn=lambda _: None, ledger=NeverTouchedLedger(),
        guard=None, authorization=None, created_at_utc=_iso(race_epoch),
        pre_reserve_gate_fn=pre_reserve_gate,
        activation_gate_fn=activation_gate,
    )
    record = result["per_candidate"][0]
    assert result["outcome"] == "ZERO_SEND"
    assert result["sent_attempt"] is None
    assert record["reason"] == LIFECYCLE_BLOCK_STALE
    assert "compose_decision" not in record
    stats = lifecycle_index.stats()
    assert stats["fee_gate_send_time_stale_blocks"] == 1
    # The candidate is merely blocked for now, not forgotten: the lifecycle
    # still tracks it as TEMPORARILY_STALE with its last fresh verdict.
    artifact = lifecycle_index.artifact_for(MINT)
    assert artifact["lifecycle_state"] == LIFECYCLE_TEMPORARILY_STALE
    assert artifact["last_fresh_verdict"] == PHX1_FEE_GATE_NORMAL


def test_send_time_gate_blocks_unbound_scam_or_aged_bound_evidence():
    state = _healthy_mature_state()
    lifecycle_index = FeeGateLifecycleIndex()
    security_index = SecurityDecisionIndex()
    now = BASE + 400
    gate = make_fee_gate_send_time_gate(
        fee_index=FakeFeeIndex(state), lifecycle_index=lifecycle_index,
        security_index=security_index, max_age_seconds="300",
        now_epoch_fn=lambda: now)
    # Fresh confirmed evidence but NO bound decision -> fail closed.
    assert gate(MINT) == LIFECYCLE_BLOCK_EVIDENCE_UNBOUND

    view = lifecycle_index.observe(_snap(state, now_epoch=now), now_epoch=now)
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    security_index.bind(decision)
    assert gate(MINT) is None

    # Bound evidence aged out at the boundary even though current evidence is
    # fresh (a rebound would be required before any send).
    aged_bound = SimpleNamespace(fee_snapshot=SimpleNamespace(
        candidate_mint=MINT, fee_gate_label=PHX1_FEE_GATE_NORMAL,
        last_observed_at_utc=_iso(BASE + 40)))
    reason = lifecycle_index.send_time_block_reason(
        view=lifecycle_index.observe(_snap(state, now_epoch=now), now_epoch=now),
        bound_decision=aged_bound, now_epoch=now)
    assert reason == LIFECYCLE_BLOCK_STALE

    scam_state = _scam_mature_state(events=40, txs=40, last_epoch=BASE + 390,
                                    scale=2)
    scam_gate = make_fee_gate_send_time_gate(
        fee_index=FakeFeeIndex(scam_state), lifecycle_index=lifecycle_index,
        security_index=security_index, max_age_seconds="300",
        now_epoch_fn=lambda: now)
    assert scam_gate(MINT) == BLOCK_SCAM_LIKELY
    assert lifecycle_index.stats()["fee_gate_send_time_scam_blocks"] >= 1


# ---------------------------------------------------------------------------
# 12. cross-consumer lifecycle/evidence version consistency
# ---------------------------------------------------------------------------

def test_all_consumers_reference_the_same_lifecycle_and_evidence_version():
    lifecycle_index = FeeGateLifecycleIndex()
    security_index = SecurityDecisionIndex()
    now = BASE + 400
    view = lifecycle_index.observe(
        _snap(_healthy_mature_state(), now_epoch=now), now_epoch=now)
    decision = evaluate_delivery_safety(
        fee_snapshot=view.effective_snapshot,
        existing_block_reasons=view.send_block_reasons)
    assert decision.verdict == POLICY_ALLOW
    security_index.bind(decision)
    lifecycle = lifecycle_index.artifact_for(MINT)
    fee_digest = decision.fee_snapshot.proof_digest

    # security index <-> lifecycle evidence version
    assert security_index.get(MINT).fee_snapshot.proof_digest == fee_digest
    assert lifecycle["evidence_proof_digest"] == fee_digest
    assert lifecycle["lifecycle_version"] == FEE_GATE_LIFECYCLE_VERSION

    # candidate/watchlist artifact (session enrichment shape)
    at = _iso(now)
    candidate = producer_session.artifacts.build_candidate_recheck_record(
        rec={
            "token_mint": MINT, "reason": "NO_SEND_NOT_DISPATCHABLE",
            "compose_attempted": False, "reservation_attempted": False,
            "market_context": {
                "current_price": "0.0001", "current_market_cap_usd": "100000",
                "liquidity_usd": "50000", "market_context_fetched_at_utc": at,
            },
        },
        entry=SimpleNamespace(candidate_id="candidate-1",
                              migration_time_utc=at, source_ref="migration"),
        cycle=1, observed_at_utc=at, ledger_touched=False,
        transport_attempted=False, security=decision,
    )
    candidate = {**candidate, "fee_gate_lifecycle": lifecycle}
    assert candidate["fee_gate"]["proof_digest"] == fee_digest
    assert candidate["fee_gate_lifecycle"]["evidence_proof_digest"] == fee_digest

    # dashboard
    producer = {
        "watch": {"candidate-1": {
            "candidate_id": "candidate-1", "token_mint": MINT,
            "status": "ACTIVE_DIP_WATCH", "activation_proven": True,
            "seeded_at_utc": at, "last_observed_at_utc": at,
        }},
        "candidates": {"candidate-1": {"last": candidate}},
        "ath_state": {},
    }
    row = build_candidate_rows(
        producer, datetime.fromtimestamp(now, timezone.utc))[0]
    assert row["feeLifecycleState"] == LIFECYCLE_FRESH_CONFIRMED
    assert row["feeLifecycleEvidenceDigest"] == fee_digest
    assert row["feeLifecycleDurableLock"] is False
    assert row["feeGateLabel"] == decision.fee_snapshot.fee_gate_label

    # paper
    paper = normalize_record(candidate)
    assert paper is not None
    assert paper.fee_gate["proof_digest"] == fee_digest

    # telegram composer artifact
    composed = []
    adapter = TelegramDeliveryAdapter(
        transport=SimpleNamespace(send_html=None, close=lambda: None),
        compose_sink=composed.append, console_sink=None)
    adapter.bind_delivery(
        body="body", mint=MINT,
        composed_snapshot=SimpleNamespace(
            token_mint=MINT, tier_token="Tier 2",
            current_market_cap_usd="100000"),
        delivery_context={
            "candidate": {"migration_time_utc": _iso(BASE),
                          "fee_gate_lifecycle": lifecycle},
            "market_context": {"current_market_cap_usd": "100000",
                               "liquidity_usd": "50000"},
            "activation": {"activation_state": "ACTIVE_DIP_WATCH",
                           "migration_market_cap_usd": "32000"},
            "security_decision": decision,
        },
        created_at_utc=_iso(now))
    assert adapter.last_compose_artifact is not None
    proofs = adapter.last_compose_artifact["source_proofs"]
    assert proofs["fee_gate_digest"] == fee_digest
    assert proofs["fee_gate_lifecycle_evidence_digest"] == fee_digest
    assert proofs["fee_gate_lifecycle_state"] == LIFECYCLE_FRESH_CONFIRMED
    assert proofs["fee_gate_lifecycle_version"] == FEE_GATE_LIFECYCLE_VERSION
    assert proofs["security_decision_digest"] == decision.proof_digest
    assert len(composed) == 1


# ---------------------------------------------------------------------------
# 13. fake dust / direct pools never enter the lifecycle
# ---------------------------------------------------------------------------

def test_unadmitted_mints_never_enter_the_lifecycle(tmp_path):
    """Migration admission rejects fake dust and direct pools before they are
    ever seeded/tracked (see test_migration_admission.py), so the session
    never calls observe() for them: the lifecycle holds no state and persists
    nothing for an unobserved mint."""

    path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=path)
    dust_mint = "FakeDustDirectPool111111111111111111111pump"
    assert index.artifact_for(dust_mint) is None
    assert index.is_durably_locked(dust_mint) is False
    assert index.stats()["fee_lifecycle_mints_tracked"] == 0
    assert not path.exists()


# ---------------------------------------------------------------------------
# restart validation: malformed persisted state fails closed
# ---------------------------------------------------------------------------

def test_restart_fails_closed_for_malformed_or_mismatched_state(tmp_path):
    path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=path)
    index.observe(_snap(_healthy_mature_state(), now_epoch=BASE + 400),
                  now_epoch=BASE + 400)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    tampered = json.loads(lines[-1])
    tampered["candidate_mint"] = "TamperedMint111111111111111111111111111pump"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(tampered, sort_keys=True) + "\n")

    restarted = FeeGateLifecycleIndex(path=path)
    stats = restarted.stats()
    assert stats["fee_lifecycle_load_dropped"] == 1        # digest mismatch
    assert stats["fee_lifecycle_state_invalid_mints"] == 1
    assert stats["fee_lifecycle_restored_records"] == 1    # valid line kept
    # The tampered mint is permanently send-blocked for this session.
    view = restarted.observe(
        _snap(_healthy_mature_state(),
              now_epoch=BASE + 400,
              mint="TamperedMint111111111111111111111111111pump"),
        now_epoch=BASE + 400)
    assert view.send_block_reasons == (LIFECYCLE_BLOCK_STATE_INVALID,)
    # The untampered mint still works normally.
    view = restarted.observe(
        _snap(_healthy_mature_state(), now_epoch=BASE + 400),
        now_epoch=BASE + 400)
    assert view.send_block_reasons == ()


def test_restart_cannot_recount_persisted_evidence_or_convert_stale(tmp_path):
    path = tmp_path / "fee_gate_lifecycle.jsonl"
    index = FeeGateLifecycleIndex(path=path)
    state = _scam_mature_state()
    index.observe(_snap(state, now_epoch=BASE + 400), now_epoch=BASE + 400)

    restarted = FeeGateLifecycleIndex(path=path)
    # Same persisted evidence identity re-observed after restart: still 1.
    view = restarted.observe(_snap(state, now_epoch=BASE + 450),
                             now_epoch=BASE + 450)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False
    # Stale data cannot become a new confirmation after restart either.
    view = restarted.observe(_stale_snap(state, now_epoch=BASE + 1000),
                             now_epoch=BASE + 1000)
    assert view.artifact["provisional_scam_count"] == 1
    assert view.artifact["durable_scam_locked"] is False
    # A genuinely NEW distinct mature scam snapshot may finish the confirmation
    # across the restart boundary.
    view = restarted.observe(
        _snap(_scam_mature_state(events=40, txs=40, last_epoch=BASE + 990,
                                 scale=2),
              now_epoch=BASE + 1000),
        now_epoch=BASE + 1000)
    assert view.artifact["provisional_scam_count"] == 2
    assert view.artifact["durable_scam_locked"] is True


# ---------------------------------------------------------------------------
# observability: closed counter set
# ---------------------------------------------------------------------------

def test_stats_expose_the_closed_lifecycle_counter_set():
    stats = FeeGateLifecycleIndex().stats()
    for name in (
        "fee_gate_immature", "fee_gate_fresh_provisional",
        "fee_gate_fresh_confirmed", "fee_gate_temporarily_stale",
        "fee_gate_durable_scam_locked", "fee_gate_recovered_from_stale",
        "fee_gate_provisional_scam_recovered",
        "fee_gate_send_time_stale_blocks", "fee_gate_send_time_scam_blocks",
    ):
        assert stats[name] == 0
    assert stats["lifecycle_version"] == FEE_GATE_LIFECYCLE_VERSION
    assert set(stats["fee_lifecycle_mints_by_state"]) == {
        LIFECYCLE_IMMATURE, LIFECYCLE_FRESH_PROVISIONAL,
        LIFECYCLE_FRESH_CONFIRMED, LIFECYCLE_TEMPORARILY_STALE,
        LIFECYCLE_DURABLE_SCAM_LOCKED,
    }
