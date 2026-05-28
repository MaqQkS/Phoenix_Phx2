"""Stage 30.3 compact candidate projection tests.

Pins the round-trip Stage 30.3 entry -> Stage 30.1 tier decision
-> Stage 30.2 compact ping input contract via synthetic Stage
27.4 ATH / migration records.

Discipline: no env reads, no network, no provider calls, no
operator-channel send. Stdlib + pytest only.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_NO_MIGRATION_EVENT,
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_SOURCE_UNKNOWN,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
    MigrationContextRecord,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_OK,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    ATH_UNIT_SOL,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    AthContextRecord,
)
from PHX2.stage30.compact_ping_models import CompactPingInputRecord
from PHX2.stage30.stage30_3_compact_candidate_projection import (
    build_compact_ping_input_record,
    project_recorded_entry_to_tier_decision_record,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    Stage30_3RecordedCandidateContext,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    Stage30_1TierDecisionError,
    TIER_REASON_NA_MIGRATION_MISSING,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_NOT_APPLICABLE,
    TIER_TOKEN_TIER_UNKNOWN,
)


_SAFE_MINT: str = "So11111111111111111111111111111111111111112"
_SAFE_TS: str = "2026-05-27T12:00:00Z"
_MIG_TS: str = "2026-05-27T00:00:00Z"


def _make_ath(**overrides: Any) -> AthContextRecord:
    defaults: dict = {
        "token_mint": _SAFE_MINT,
        "pair_type": "PUMPSWAP_AMM",
        "quote_asset": "SOL",
        "ath_value": "1.0",
        "ath_unit": ATH_UNIT_SOL,
        "ath_source": "synthetic_test",
        "ath_observed_at_utc": _MIG_TS,
        "ath_since_migration_status": (
            ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        "drawdown_from_ath": "0.55",
        "drawdown_unit": ATH_UNIT_SOL,
        "drawdown_basis": DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        "ath_status": ATH_STATUS_PRESENT,
        "ath_reason": ATH_REASON_OK,
        "schema_version": STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    }
    defaults.update(overrides)
    return AthContextRecord(**defaults)


def _make_migration(**overrides: Any) -> MigrationContextRecord:
    defaults: dict = {
        "token_mint": _SAFE_MINT,
        "pair_type": "PUMPSWAP_AMM",
        "quote_asset": "SOL",
        "migration_event_id": "evt-001",
        "migration_timestamp_utc": _MIG_TS,
        "migration_source": MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        "migration_status": MIGRATION_STATUS_PRESENT,
        "migration_reason": MIGRATION_REASON_OK,
        "age_since_migration_seconds": 60,
        "observed_at_utc": _SAFE_TS,
        "source_event_ref": "evt-ref-001",
        "raw_capture_ref": None,
        "schema_version": STAGE27_4_MIGRATION_SCHEMA_VERSION,
    }
    defaults.update(overrides)
    return MigrationContextRecord(**defaults)


def _make_entry(
    *,
    ath_record: Optional[object] = None,
    migration_record: Optional[object] = None,
    price_status: Optional[str] = "PRESENT",
    age: Optional[int] = 60,
) -> Stage30_3RecordedCandidateContext:
    return Stage30_3RecordedCandidateContext(
        candidate_id="cand-001",
        mint=_SAFE_MINT,
        ath_record=ath_record,
        migration_record=migration_record,
        price_status=price_status,
        age_since_migration_seconds=age,
        recorded_at_utc=_SAFE_TS,
    )


# ---------------------------------------------------------------------------
# project_recorded_entry_to_tier_decision_record happy path
# ---------------------------------------------------------------------------


def test_full_entry_projects_to_tier_1() -> None:
    entry = _make_entry(
        ath_record=_make_ath(drawdown_from_ath="0.55"),
        migration_record=_make_migration(),
    )
    decision = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    assert decision.tier_token == TIER_TOKEN_TIER_1
    assert decision.tier_reason == TIER_REASON_TIER_1_IN_BAND
    assert decision.basis == BASIS_PRICE
    assert decision.session_id == "sess-001"
    assert decision.ping_id == "cand-001"
    assert decision.candidate_id == "cand-001"
    assert decision.mint == _SAFE_MINT
    assert (
        decision.schema_version
        == STAGE30_1_TIER_DECISION_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# project_recorded_entry_to_tier_decision_record degraded paths
# ---------------------------------------------------------------------------


def test_missing_migration_projects_to_tier_not_applicable() -> None:
    entry = _make_entry(
        ath_record=_make_ath(drawdown_from_ath="0.55"),
        migration_record=None,
    )
    decision = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    assert decision.tier_token == TIER_TOKEN_TIER_NOT_APPLICABLE
    assert decision.tier_reason == TIER_REASON_NA_MIGRATION_MISSING


def test_missing_ath_projects_to_tier_unknown_ath_not_present() -> None:
    entry = _make_entry(
        ath_record=None,
        migration_record=_make_migration(),
    )
    decision = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    assert decision.tier_token == TIER_TOKEN_TIER_UNKNOWN
    assert (
        decision.tier_reason == TIER_REASON_UNKNOWN_ATH_NOT_PRESENT
    )


# ---------------------------------------------------------------------------
# project_recorded_entry_to_tier_decision_record raises on bad basis
# ---------------------------------------------------------------------------


def test_invalid_basis_raises_tier_decision_error() -> None:
    entry = _make_entry(
        ath_record=_make_ath(drawdown_from_ath="0.55"),
        migration_record=_make_migration(),
    )
    with pytest.raises(Stage30_1TierDecisionError) as excinfo:
        project_recorded_entry_to_tier_decision_record(
            entry=entry,
            basis="not-a-valid-basis",
            created_at_utc=_SAFE_TS,
            session_id="sess-001",
        )
    assert excinfo.value.reason == "BASIS_INVALID"


# ---------------------------------------------------------------------------
# build_compact_ping_input_record sets display fields to None
# ---------------------------------------------------------------------------


def test_compact_input_record_display_slots_are_none() -> None:
    entry = _make_entry(
        ath_record=_make_ath(drawdown_from_ath="0.55"),
        migration_record=_make_migration(),
        age=42,
        price_status="STALE",
    )
    decision = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    input_record = build_compact_ping_input_record(
        tier_decision=decision,
        entry=entry,
        session_id="sess-001",
        created_at_utc=_SAFE_TS,
    )
    assert isinstance(input_record, CompactPingInputRecord)
    assert input_record.tier_decision is decision
    assert input_record.mint == _SAFE_MINT
    assert input_record.symbol is None
    assert input_record.current_mc_text is None
    assert input_record.ath_mc_text is None
    assert input_record.migration_mc_text is None
    assert input_record.lp_text is None
    assert input_record.net_flow_text is None
    assert input_record.age_since_migration_seconds == 42
    assert input_record.price_status == "STALE"
    assert input_record.session_id == "sess-001"
    assert input_record.ping_id == "cand-001"
    assert input_record.candidate_id == "cand-001"
    assert input_record.created_at_utc == _SAFE_TS


def test_renderer_emits_unknown_for_missing_display_slots() -> None:
    # Round-trip: project + build + render -> the Stage 30.2
    # renderer emits ``Unknown`` for every missing MC / LP / Net
    # slot.
    from PHX2.stage30.compact_ping_renderer import (
        render_compact_ping,
    )

    entry = _make_entry(
        ath_record=_make_ath(drawdown_from_ath="0.55"),
        migration_record=_make_migration(),
        age=42,
        price_status="PRESENT",
    )
    decision = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    input_record = build_compact_ping_input_record(
        tier_decision=decision,
        entry=entry,
        session_id="sess-001",
        created_at_utc=_SAFE_TS,
    )
    snapshot = render_compact_ping(input_record)
    assert snapshot.current_mc_display == "Unknown"
    assert snapshot.ath_mc_display == "Unknown"
    assert snapshot.migration_mc_display == "Unknown"
    assert snapshot.lp_display == "Unknown"
    assert snapshot.net_flow_display == "Unknown"


# ---------------------------------------------------------------------------
# Determinism: identical projections produce byte-identical records
# ---------------------------------------------------------------------------


def test_identical_projections_are_byte_identical() -> None:
    entry = _make_entry(
        ath_record=_make_ath(drawdown_from_ath="0.55"),
        migration_record=_make_migration(),
    )
    decision_a = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    decision_b = project_recorded_entry_to_tier_decision_record(
        entry=entry,
        basis=BASIS_PRICE,
        created_at_utc=_SAFE_TS,
        session_id="sess-001",
    )
    assert decision_a == decision_b

    input_a = build_compact_ping_input_record(
        tier_decision=decision_a,
        entry=entry,
        session_id="sess-001",
        created_at_utc=_SAFE_TS,
    )
    input_b = build_compact_ping_input_record(
        tier_decision=decision_b,
        entry=entry,
        session_id="sess-001",
        created_at_utc=_SAFE_TS,
    )
    assert input_a == input_b
