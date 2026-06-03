"""Stage 30.11.5 live-candidate snapshot assembler tests.

Proves the assembler converts an existing flat safe-scalar candidate projection
(a MAPPING / dict OR an attribute-bearing object) into a committed Stage 30.11.1
``Stage30_11LiveCandidateSnapshot``: it builds the snapshot for a well-shaped
projection, fails closed (no snapshot) on a missing required pair / price / ATH /
migration / drawdown / tier field, fails closed on a malformed present field
(blank id, non-coercible drawdown / market-cap, non-bool verified flag), coerces
decimal strings / ints to a finite ``Decimal``, fabricates no dip (a
present-but-degraded context is carried verbatim, NEVER forced to ``PRESENT``),
maps optional fields to ``None`` when absent, and produces a snapshot that is
gate-ready through the committed Stage 30.11.1 bridge -> Stage 30.9.3 dip gate.

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Dict

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
    evaluate_dip_filtered_live_gate,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_PASS_TO_DISPATCH,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge import (
    build_stage30_9_3_live_gate_input_from_candidate,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
    Stage30_11LiveCandidateSnapshot,
)
from PHX2.stage30.stage30_11_5_live_candidate_snapshot_assembler import (
    assemble_stage30_11_5_live_candidate_snapshot,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    ASSEMBLY_DECISION_ASSEMBLED,
    ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
    ASSEMBLY_DECISION_REJECTED_MISSING_FIELD,
    ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
    ASSEMBLY_REASON_MISSING_REQUIRED_FIELD,
    ASSEMBLY_REASON_READY_FOR_BRIDGE,
    STAGE30_11_5_REQUIRED_PROJECTION_FIELDS,
)


_CREATED_AT = "2026-01-01T00:00:00Z"


def _dip_projection() -> Dict[str, object]:
    return {
        "candidate_id": "cand-tier1",
        "token_mint": "mint-tier1",
        "pair_type": "SOL",
        "tier_hint": "Tier 1",
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        "current_market_cap_usd": "12345.67",
        "post_migration_ath_verified": True,
        "source_ref": "ref-cand-tier1",
        "created_at_utc": _CREATED_AT,
    }


def _assemble(candidate: object):
    return assemble_stage30_11_5_live_candidate_snapshot(
        candidate, created_at_utc=_CREATED_AT
    )


# ---------------------------------------------------------------------------
# Happy path: dict + object
# ---------------------------------------------------------------------------


def test_well_shaped_dict_projection_assembles_a_snapshot() -> None:
    result = _assemble(_dip_projection())
    assert result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    assert result.assembly_reason == ASSEMBLY_REASON_READY_FOR_BRIDGE
    assert result.rejected_field == ""
    assert result.candidate_id == "cand-tier1"
    assert result.token_mint == "mint-tier1"
    assert result.created_at_utc == _CREATED_AT
    snap = result.snapshot
    assert isinstance(snap, Stage30_11LiveCandidateSnapshot)
    assert snap.candidate_id == "cand-tier1"
    assert snap.token_mint == "mint-tier1"
    assert snap.pair_type == "SOL"
    assert snap.tier_hint == "Tier 1"
    assert snap.drawdown_from_ath == Decimal("0.55")
    assert snap.current_market_cap_usd == Decimal("12345.67")
    assert snap.migration_status == "PRESENT"
    assert snap.ath_status == "PRESENT"
    assert snap.market_context_status == "PRESENT"
    assert snap.post_migration_ath_verified is True
    assert snap.source_ref == "ref-cand-tier1"
    # The snapshot carries the projection's OWN created_at, not the result stamp.
    assert snap.created_at_utc == _CREATED_AT


def test_attribute_object_projection_assembles_a_snapshot() -> None:
    # The assembler accepts an attribute-bearing object too (not just a dict).
    obj = SimpleNamespace(**_dip_projection())
    result = _assemble(obj)
    assert result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    assert result.snapshot is not None
    assert result.snapshot.candidate_id == "cand-tier1"


def test_decimal_coercion_accepts_int_and_decimal() -> None:
    projection = _dip_projection()
    projection["drawdown_from_ath"] = Decimal("0.4")
    projection["current_market_cap_usd"] = 50000
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    assert result.snapshot.drawdown_from_ath == Decimal("0.4")
    assert result.snapshot.current_market_cap_usd == Decimal(50000)


def test_optional_fields_absent_map_to_none() -> None:
    projection = _dip_projection()
    del projection["post_migration_ath_verified"]
    del projection["source_ref"]
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    assert result.snapshot.post_migration_ath_verified is None
    assert result.snapshot.source_ref is None


# ---------------------------------------------------------------------------
# Fail closed on a missing required field
# ---------------------------------------------------------------------------


def test_each_missing_required_field_fails_closed() -> None:
    for field in STAGE30_11_5_REQUIRED_PROJECTION_FIELDS:
        projection = _dip_projection()
        del projection[field]
        result = _assemble(projection)
        assert result.assembly_decision == (
            ASSEMBLY_DECISION_REJECTED_MISSING_FIELD
        ), f"{field} absent must reject"
        assert result.assembly_reason == ASSEMBLY_REASON_MISSING_REQUIRED_FIELD
        assert result.rejected_field == field
        assert result.snapshot is None


def test_none_required_field_fails_closed_as_missing() -> None:
    projection = _dip_projection()
    projection["current_market_cap_usd"] = None
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_REJECTED_MISSING_FIELD
    assert result.rejected_field == "current_market_cap_usd"
    assert result.snapshot is None


def test_completely_unusable_candidate_fails_closed() -> None:
    for candidate in (None, 7, "not-a-projection", []):
        result = _assemble(candidate)
        assert result.assembly_decision == (
            ASSEMBLY_DECISION_REJECTED_MISSING_FIELD
        )
        assert result.snapshot is None
        assert result.candidate_id == ""
        assert result.token_mint == ""


# ---------------------------------------------------------------------------
# Fail closed on a malformed present field
# ---------------------------------------------------------------------------


def test_blank_id_fails_closed_as_invalid() -> None:
    projection = _dip_projection()
    projection["candidate_id"] = "   "
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE
    assert result.assembly_reason == ASSEMBLY_REASON_INVALID_FIELD_SHAPE
    assert result.rejected_field == "candidate_id"
    assert result.snapshot is None


def test_non_string_status_fails_closed_as_invalid() -> None:
    projection = _dip_projection()
    projection["ath_status"] = 123
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE
    assert result.rejected_field == "ath_status"
    assert result.snapshot is None


def test_non_coercible_drawdown_fails_closed_as_invalid() -> None:
    for bad in ("not-a-number", "NaN", "Infinity", True, 1.5):
        projection = _dip_projection()
        projection["drawdown_from_ath"] = bad
        result = _assemble(projection)
        assert result.assembly_decision == (
            ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE
        ), f"drawdown {bad!r} must be invalid"
        assert result.rejected_field == "drawdown_from_ath"
        assert result.snapshot is None


def test_non_coercible_market_cap_fails_closed_as_invalid() -> None:
    projection = _dip_projection()
    projection["current_market_cap_usd"] = "abc"
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE
    assert result.rejected_field == "current_market_cap_usd"
    assert result.snapshot is None


def test_non_bool_verified_flag_fails_closed_as_invalid() -> None:
    projection = _dip_projection()
    projection["post_migration_ath_verified"] = "yes"
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE
    assert result.rejected_field == "post_migration_ath_verified"
    assert result.snapshot is None


def test_non_string_source_ref_fails_closed_as_invalid() -> None:
    projection = _dip_projection()
    projection["source_ref"] = 999
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE
    assert result.rejected_field == "source_ref"
    assert result.snapshot is None


# ---------------------------------------------------------------------------
# Never fabricates a dip / never bypasses the bridge
# ---------------------------------------------------------------------------


def test_degraded_context_is_carried_verbatim_not_forced_present() -> None:
    # A present-but-not-PRESENT ATH context assembles (the field is present) but
    # is carried VERBATIM -- the assembler never forces it to the bridge's
    # PRESENT value.
    projection = _dip_projection()
    projection["ath_status"] = "DEGRADED"
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    assert result.snapshot.ath_status == "DEGRADED"
    # And the committed Stage 30.11.1 bridge then suppresses it (the assembler
    # never bypasses the bridge).
    bridge_result = build_stage30_9_3_live_gate_input_from_candidate(
        result.snapshot, created_at_utc=_CREATED_AT
    )
    assert bridge_result.bridge_decision == (
        BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT
    )


def test_assembled_dip_snapshot_is_bridge_and_gate_ready() -> None:
    result = _assemble(_dip_projection())
    bridge_result = build_stage30_9_3_live_gate_input_from_candidate(
        result.snapshot, created_at_utc=_CREATED_AT
    )
    assert bridge_result.bridge_decision == (
        BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    )
    gate_decision = evaluate_dip_filtered_live_gate(
        bridge_result.live_gate_input
    )
    assert gate_decision.gate_decision == GATE_DECISION_PASS_TO_DISPATCH


def test_non_dip_snapshot_bridges_but_gate_skips() -> None:
    projection = _dip_projection()
    projection["tier_hint"] = "Tier Unknown"
    result = _assemble(projection)
    assert result.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    bridge_result = build_stage30_9_3_live_gate_input_from_candidate(
        result.snapshot, created_at_utc=_CREATED_AT
    )
    assert bridge_result.bridge_decision == (
        BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    )
    gate_decision = evaluate_dip_filtered_live_gate(
        bridge_result.live_gate_input
    )
    # The non-dip decision is the GATE's, made LATER -- not the assembler's.
    assert gate_decision.gate_decision != GATE_DECISION_PASS_TO_DISPATCH
