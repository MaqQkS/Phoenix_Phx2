"""Stage 30.11.1 live-candidate assembly bridge models unit tests.

Pins the three frozen Stage 30.11.1 bridge models (the Stage 30.11-owned
already-assembled live candidate snapshot, the per-candidate bridge result, the
rolled-up proof summary): their field names + order, their immutability, their
field-name helpers, the closed-set bridge decision / reason vocabularies, the
context-present + safe-shape helpers, the minor version, and the bridge schema
version. Also proves the bridge result EMBEDS the committed Stage 30.9.3 live
gate input (the permitted Stage 30.11 scope expansion). Fake / offline only; no
live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_INVALID_FIELD_SHAPE,
    BRIDGE_REASON_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_READY_FOR_DIP_GATE,
    LIVE_CONTEXT_STATUS_PRESENT,
    STAGE30_11_1_BRIDGE_DECISIONS,
    STAGE30_11_1_BRIDGE_PASS_DECISION,
    STAGE30_11_1_BRIDGE_REASONS,
    STAGE30_11_1_BRIDGE_SCHEMA_VERSION,
    STAGE30_11_1_MINOR_VERSION,
    Stage30_11BridgeProofSummary,
    Stage30_11BridgeResult,
    Stage30_11LiveCandidateSnapshot,
    bridge_proof_summary_field_names,
    bridge_result_field_names,
    candidate_snapshot_field_names,
    is_bridge_decision,
    is_bridge_reason,
    is_context_present,
    is_nonblank_str,
)


def _snapshot() -> Stage30_11LiveCandidateSnapshot:
    return Stage30_11LiveCandidateSnapshot(
        candidate_id="cand-1",
        token_mint="mint-1",
        pair_type="SOL",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        source_ref="ref-cand-1",
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _gate_input() -> Stage30_9_3LiveGateInput:
    return Stage30_9_3LiveGateInput(
        candidate_id="cand-1",
        token_mint="mint-1",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref="ref-cand-1",
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _result() -> Stage30_11BridgeResult:
    return Stage30_11BridgeResult(
        candidate_id="cand-1",
        token_mint="mint-1",
        bridge_decision=BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
        bridge_reason=BRIDGE_REASON_READY_FOR_DIP_GATE,
        live_gate_input=_gate_input(),
        created_at_utc="2026-01-02T00:00:00Z",
    )


def _summary() -> Stage30_11BridgeProofSummary:
    return Stage30_11BridgeProofSummary(
        candidates_seen=5,
        bridged=2,
        skipped_missing_context=2,
        invalid_inputs=1,
        created_at_utc="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_11_1_MINOR_VERSION == "30.11.1"


def test_bridge_schema_version_pinned() -> None:
    assert STAGE30_11_1_BRIDGE_SCHEMA_VERSION == (
        "stage30_11_1_v0_live_candidate_bridge"
    )


# ---------------------------------------------------------------------------
# Closed-set decisions + reasons
# ---------------------------------------------------------------------------


def test_bridge_decisions_are_the_closed_set() -> None:
    assert STAGE30_11_1_BRIDGE_DECISIONS == (
        "BRIDGED_TO_LIVE_GATE_INPUT",
        "SKIPPED_MISSING_REQUIRED_CONTEXT",
        "INVALID_BRIDGE_INPUT",
    )
    assert STAGE30_11_1_BRIDGE_PASS_DECISION == "BRIDGED_TO_LIVE_GATE_INPUT"
    # The three token constants equal the closed-set values verbatim.
    assert BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT == (
        "BRIDGED_TO_LIVE_GATE_INPUT"
    )
    assert BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT == (
        "SKIPPED_MISSING_REQUIRED_CONTEXT"
    )
    assert BRIDGE_DECISION_INVALID_BRIDGE_INPUT == "INVALID_BRIDGE_INPUT"


def test_bridge_reasons_are_the_closed_set() -> None:
    assert STAGE30_11_1_BRIDGE_REASONS == (
        "READY_FOR_DIP_GATE",
        "MISSING_REQUIRED_CONTEXT",
        "INVALID_FIELD_SHAPE",
    )
    assert BRIDGE_REASON_READY_FOR_DIP_GATE == "READY_FOR_DIP_GATE"
    assert BRIDGE_REASON_MISSING_REQUIRED_CONTEXT == "MISSING_REQUIRED_CONTEXT"
    assert BRIDGE_REASON_INVALID_FIELD_SHAPE == "INVALID_FIELD_SHAPE"


def test_is_bridge_decision_is_total_and_closed() -> None:
    for decision in STAGE30_11_1_BRIDGE_DECISIONS:
        assert is_bridge_decision(decision)
    for bad in ("PASS_TO_DISPATCH", "", "bridged", None, 7, object()):
        assert not is_bridge_decision(bad)


def test_is_bridge_reason_is_total_and_closed() -> None:
    for reason in STAGE30_11_1_BRIDGE_REASONS:
        assert is_bridge_reason(reason)
    for bad in ("ELIGIBLE_DIP", "", "ready", None, 7, object()):
        assert not is_bridge_reason(bad)


# ---------------------------------------------------------------------------
# Context-present + safe-shape helpers
# ---------------------------------------------------------------------------


def test_present_token_pinned() -> None:
    assert LIVE_CONTEXT_STATUS_PRESENT == "PRESENT"


def test_is_context_present_only_for_exact_present_token() -> None:
    assert is_context_present("PRESENT")
    for bad in ("present", "STALE", "MISSING", "", None, 0, object()):
        assert not is_context_present(bad)


def test_is_nonblank_str_rejects_blank_and_non_str() -> None:
    assert is_nonblank_str("cand-1")
    for bad in ("", "   ", "\t\n", None, 0, 7, object()):
        assert not is_nonblank_str(bad)


# ---------------------------------------------------------------------------
# Field names (order matters)
# ---------------------------------------------------------------------------


def test_candidate_snapshot_field_names() -> None:
    assert candidate_snapshot_field_names() == (
        "candidate_id",
        "token_mint",
        "pair_type",
        "tier_hint",
        "drawdown_from_ath",
        "migration_status",
        "ath_status",
        "market_context_status",
        "current_market_cap_usd",
        "post_migration_ath_verified",
        "source_ref",
        "created_at_utc",
    )


def test_bridge_result_field_names() -> None:
    assert bridge_result_field_names() == (
        "candidate_id",
        "token_mint",
        "bridge_decision",
        "bridge_reason",
        "live_gate_input",
        "created_at_utc",
    )


def test_bridge_proof_summary_field_names() -> None:
    assert bridge_proof_summary_field_names() == (
        "candidates_seen",
        "bridged",
        "skipped_missing_context",
        "invalid_inputs",
        "created_at_utc",
    )


# ---------------------------------------------------------------------------
# Construction echoes + optional None + embedded gate input
# ---------------------------------------------------------------------------


def test_snapshot_echoes_fields() -> None:
    snap = _snapshot()
    assert snap.candidate_id == "cand-1"
    assert snap.token_mint == "mint-1"
    assert snap.pair_type == "SOL"
    assert snap.tier_hint == "Tier 1"
    assert snap.drawdown_from_ath == Decimal("0.55")
    assert snap.current_market_cap_usd == Decimal("12345.67")
    assert snap.post_migration_ath_verified is True
    assert snap.source_ref == "ref-cand-1"
    assert snap.created_at_utc == "2026-01-01T00:00:00Z"


def test_snapshot_allows_optional_none_values() -> None:
    snap = Stage30_11LiveCandidateSnapshot(
        candidate_id="c",
        token_mint="m",
        pair_type=None,
        tier_hint=None,
        drawdown_from_ath=None,
        migration_status=None,
        ath_status=None,
        market_context_status=None,
        current_market_cap_usd=None,
        post_migration_ath_verified=None,
        source_ref=None,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert snap.pair_type is None
    assert snap.tier_hint is None
    assert snap.drawdown_from_ath is None
    assert snap.source_ref is None


def test_bridge_result_embeds_committed_gate_input() -> None:
    res = _result()
    assert isinstance(res.live_gate_input, Stage30_9_3LiveGateInput)
    assert res.live_gate_input.candidate_id == "cand-1"
    assert res.bridge_decision == BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    assert res.bridge_reason == BRIDGE_REASON_READY_FOR_DIP_GATE
    # The bridge-run timestamp is independent of the embedded gate input's
    # assembled-context timestamp.
    assert res.created_at_utc == "2026-01-02T00:00:00Z"
    assert res.live_gate_input.created_at_utc == "2026-01-01T00:00:00Z"


def test_bridge_result_allows_none_gate_input() -> None:
    res = Stage30_11BridgeResult(
        candidate_id="c",
        token_mint="m",
        bridge_decision=BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
        bridge_reason=BRIDGE_REASON_MISSING_REQUIRED_CONTEXT,
        live_gate_input=None,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert res.live_gate_input is None


def test_summary_echoes_counts() -> None:
    summary = _summary()
    assert summary.candidates_seen == 5
    assert summary.bridged == 2
    assert summary.skipped_missing_context == 2
    assert summary.invalid_inputs == 1


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", [_snapshot(), _result(), _summary()])
def test_models_are_frozen(model: object) -> None:
    # A frozen dataclass raises FrozenInstanceError on any attribute set.
    with pytest.raises(FrozenInstanceError):
        setattr(model, "candidate_id", "mutated")
