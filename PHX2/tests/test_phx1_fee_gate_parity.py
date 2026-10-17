import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from PHX2.free_tier_producer.phx1_fee_gate import (
    BLOCK_DATA_INVALID,
    BLOCK_DATA_STALE,
    BLOCK_PAIR_UNCALIBRATED,
    BLOCK_PROOF_INCONSISTENT,
    BLOCK_PROOF_MISSING,
    BLOCK_SCAM_LIKELY,
    FEE_GATE_UNKNOWN,
    FeeEvent,
    FeeEvidenceIndex,
    PHX1_FEE_GATE_NORMAL,
    PHX1_FEE_GATE_SCAM_LIKELY,
    PHX1_FEE_GATE_SUSPICIOUS,
    fee_gate_block_reason,
    score_phx1_fees,
    seal_fee_snapshot,
    validate_fee_snapshot,
    JITO_TIP_ACCOUNTS,
)
from PHX2.free_tier_producer.liquidity_integrity import b58decode
from PHX2.stage29.pumpswap_program_constants import USDC_MINT


FIXTURE = Path(__file__).with_name("fixtures") / "phx1_fee_gate_golden.json"
MINT = "FeeGate11111111111111111111111111111111pump"
WSOL = "So11111111111111111111111111111111111111112"


@pytest.mark.parametrize("row", json.loads(FIXTURE.read_text(encoding="utf-8")))
def test_real_phx1_golden_rows_match_label_flags_score_and_hard_block(row):
    result = score_phx1_fees(
        total_fee=row["total_fee_sol"],
        lp_fee=row["lp_sol"],
        protocol_fee=row["protocol_sol"],
        creator_fee=row["creator_sol"],
        bribes=row["bribes_sol"],
        transaction_count=row["transaction_count"],
        event_count=row["event_count"],
    )
    assert result.score == row["score"]
    assert list(result.flags) == row["flags"]
    assert result.label == row["label"]
    assert (result.label == PHX1_FEE_GATE_SCAM_LIKELY) is row["hard_block"]


def test_exact_phx1_epsilon_boundary_is_preserved_with_decimal():
    exact = score_phx1_fees(
        total_fee="1", lp_fee="0.5", protocol_fee="0.4", creator_fee="0.1",
        bribes="0.0281", transaction_count=500, event_count=500)
    assert exact.label == PHX1_FEE_GATE_SUSPICIOUS
    assert exact.flags == ("bribes_starved",)


def test_binary_floats_are_rejected_for_exact_decisions():
    with pytest.raises(ValueError, match="binary_float_rejected"):
        score_phx1_fees(
            total_fee=1.0, lp_fee="0.5", protocol_fee="0.4", creator_fee="0.1",
            bribes="0.1", transaction_count=500, event_count=500)


def _event(*, signature="sig1", timestamp=1000, quote=WSOL, priority=100_000_000,
           creator=100_000_000, lp=800_000_000, protocol=100_000_000):
    return FeeEvent(
        candidate_mint=MINT, quote_mint=quote, pair_type="PUMPSWAP_SOL",
        quote_asset="SOL" if quote == WSOL else "USDC", unit="SOL" if quote == WSOL else "USDC",
        transaction_signature=signature, event_index=0, event_timestamp_epoch=timestamp,
        observed_at_utc="1970-01-01T00:16:40Z", side="BUY",
        lp_fee_base_units=lp, protocol_fee_base_units=protocol,
        creator_fee_base_units=creator, base_fee_base_units=5_000,
        priority_fee_base_units=priority, jito_tip_base_units=0)


def test_missing_fee_proof_fails_closed_and_never_becomes_pass():
    snap = FeeEvidenceIndex().snapshot(MINT, now_epoch=1000)
    assert snap.fee_gate_label == FEE_GATE_UNKNOWN
    assert snap.hard_block and not snap.fee_gate_eligible
    assert fee_gate_block_reason(snap) == BLOCK_PROOF_MISSING


def test_stale_fee_evidence_fails_closed():
    index = FeeEvidenceIndex()
    assert index.record(_event())
    snap = index.snapshot(MINT, now_epoch=1301, max_age_seconds="300")
    assert snap.fee_gate_label == FEE_GATE_UNKNOWN
    assert fee_gate_block_reason(snap) == BLOCK_DATA_STALE


def test_sol_and_usdc_are_separate_calibration_universes():
    index = FeeEvidenceIndex()
    assert index.record(_event(quote=USDC_MINT))
    snap = index.snapshot(MINT, now_epoch=1000)
    assert snap.fee_gate_label == FEE_GATE_UNKNOWN
    assert fee_gate_block_reason(snap) == BLOCK_PAIR_UNCALIBRATED


def test_valid_snapshot_has_exact_equation_recent_and_ante_fields():
    index = FeeEvidenceIndex()
    assert index.record(_event())
    snap = index.snapshot(MINT, now_epoch=1000)
    valid, reason = validate_fee_snapshot(snap)
    assert valid and reason is None
    assert Decimal(snap.total_fees) == (
        Decimal(snap.lp_fees) + Decimal(snap.protocol_fees) + Decimal(snap.creator_fees))
    assert snap.recent_transaction_count == snap.recent_swap_count == 1
    assert snap.ante_last20_median is not None


def test_forged_label_or_digest_fails_closed():
    index = FeeEvidenceIndex()
    index.record(_event())
    snap = index.snapshot(MINT, now_epoch=1000)
    forged = replace(snap, fee_gate_label=PHX1_FEE_GATE_NORMAL)
    assert validate_fee_snapshot(forged) == (False, BLOCK_PROOF_INCONSISTENT)
    assert fee_gate_block_reason(forged) == BLOCK_PROOF_INCONSISTENT
    resealed = seal_fee_snapshot(replace(
        snap, fee_gate_label=PHX1_FEE_GATE_NORMAL, fee_gate_score=0,
        fee_gate_reasons=(), fee_gate_eligible=True, hard_block=False,
        proof_digest=""))
    assert validate_fee_snapshot(resealed) == (False, BLOCK_PROOF_INCONSISTENT)


def test_scam_likely_is_independent_hard_block_while_suspicious_is_not():
    scam = score_phx1_fees(
        total_fee="1", lp_fee="0.1", protocol_fee="0.1", creator_fee="0.8",
        bribes="0.01", transaction_count=1000, event_count=1000)
    suspicious = score_phx1_fees(
        total_fee="1", lp_fee="0.19", protocol_fee="0.1", creator_fee="0.71",
        bribes="0.03", transaction_count=1000, event_count=1000)
    assert scam.label == PHX1_FEE_GATE_SCAM_LIKELY
    assert suspicious.label == PHX1_FEE_GATE_SUSPICIOUS


def test_thin_sample_is_score_feature_not_missing_data():
    result = score_phx1_fees(
        total_fee="1", lp_fee="0.6", protocol_fee="0.2", creator_fee="0.2",
        bribes="0.1", transaction_count=499, event_count=499)
    assert result.label == "Elevated"
    assert result.flags == ("thin_sample",)


def test_jito_tip_accounts_are_complete_valid_pubkeys():
    assert len(JITO_TIP_ACCOUNTS) == 8
    assert all(len(b58decode(account)) == 32 for account in JITO_TIP_ACCOUNTS)


def test_malformed_negative_component_does_not_score():
    with pytest.raises(ValueError, match="negative_fee_component"):
        score_phx1_fees(
            total_fee="1", lp_fee="-1", protocol_fee="1", creator_fee="1",
            bribes="0.1", transaction_count=500, event_count=500)


def test_zero_fee_events_are_insufficient_and_fail_closed():
    index = FeeEvidenceIndex()
    assert index.record(_event(priority=0, creator=0, lp=0, protocol=0))
    snapshot = index.snapshot(MINT, now_epoch=1000)
    assert snapshot.fee_gate_label == FEE_GATE_UNKNOWN
    assert snapshot.hard_block and not snapshot.fee_gate_eligible
