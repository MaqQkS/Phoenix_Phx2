"""Stage 30.11.6 candidate-source models unit tests.

Pins the passive Stage 30.11.6 model layer: the minor version + schema identity,
the closed-set projection / harvest decision + reason vocabularies + their
membership helpers, the not-projected sentinel, the Stage 30.11.5-shaped flat
projection field names (cross-checked BY VALUE against the committed Stage 30.11.5
projection field names), the hard harvest cap + default + run-scoped candidate-id
prefix, the author-verified proof baseline counts, and the five frozen model
dataclasses (construction + immutability + field names).

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS,
    STAGE30_11_5_PROJECTION_FIELDS,
    STAGE30_11_5_REQUIRED_PROJECTION_FIELDS,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    HARVEST_DECISION_HARVESTED,
    HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
    HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
    HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY,
    HARVEST_REASON_PROJECTION_FAILED_CLOSED,
    HARVEST_REASON_READY_FOR_LIVE_RUNNER,
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
    PROJECTION_DECISION_REJECTED_MISSING_FIELD,
    PROJECTION_REASON_INVALID_FIELD_SHAPE,
    PROJECTION_REASON_MISSING_REQUIRED_FIELD,
    PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
    STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION,
    STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    STAGE30_11_6_DEFAULT_MAX_HARVEST,
    STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_6_EXPECTED_EVENTS_SEEN,
    STAGE30_11_6_EXPECTED_HARVESTED,
    STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED,
    STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED,
    STAGE30_11_6_HARVEST_DECISIONS,
    STAGE30_11_6_HARVEST_PASS_DECISION,
    STAGE30_11_6_HARVEST_PASS_REASON,
    STAGE30_11_6_HARVEST_REASONS,
    STAGE30_11_6_MAX_HARVEST_HARD_CAP,
    STAGE30_11_6_MINOR_VERSION,
    STAGE30_11_6_NOT_PROJECTED,
    STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS,
    STAGE30_11_6_PROJECTION_DECISIONS,
    STAGE30_11_6_PROJECTION_FIELDS,
    STAGE30_11_6_PROJECTION_PASS_DECISION,
    STAGE30_11_6_PROJECTION_PASS_REASON,
    STAGE30_11_6_PROJECTION_REASONS,
    STAGE30_11_6_REQUIRED_PROJECTION_FIELDS,
    STAGE30_11_6_SOURCE_STAGE,
    Stage30_11_6CandidateHarvestOutcome,
    Stage30_11_6CandidateProjection,
    Stage30_11_6CandidateProjectionResult,
    Stage30_11_6HarvestResult,
    Stage30_11_6HarvestSummary,
    candidate_harvest_outcome_field_names,
    candidate_projection_field_names,
    candidate_projection_result_field_names,
    harvest_result_field_names,
    harvest_summary_field_names,
    is_harvest_decision,
    is_harvest_reason,
    is_nonblank_str,
    is_projection_decision,
    is_projection_reason,
)


# ---------------------------------------------------------------------------
# 1. Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_and_schema_pinned() -> None:
    assert STAGE30_11_6_MINOR_VERSION == "30.11.6"
    assert STAGE30_11_6_CANDIDATE_SOURCE_SCHEMA_VERSION == (
        "stage30_11_6_v0_candidate_source"
    )
    assert STAGE30_11_6_SOURCE_STAGE == "30.11.6"


# ---------------------------------------------------------------------------
# 2. Projection field names mirror the committed Stage 30.11.5 names BY VALUE
# ---------------------------------------------------------------------------


def test_projection_fields_equal_committed_stage_30_11_5() -> None:
    assert STAGE30_11_6_PROJECTION_FIELDS == STAGE30_11_5_PROJECTION_FIELDS
    assert (
        STAGE30_11_6_REQUIRED_PROJECTION_FIELDS
        == STAGE30_11_5_REQUIRED_PROJECTION_FIELDS
    )
    assert (
        STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS
        == STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS
    )
    # The projection dataclass field names equal the projection field tuple.
    assert candidate_projection_field_names() == STAGE30_11_6_PROJECTION_FIELDS


def test_required_plus_optional_is_all_projection_fields() -> None:
    combined = set(STAGE30_11_6_REQUIRED_PROJECTION_FIELDS) | set(
        STAGE30_11_6_OPTIONAL_PROJECTION_FIELDS
    )
    assert combined == set(STAGE30_11_6_PROJECTION_FIELDS)
    assert len(STAGE30_11_6_PROJECTION_FIELDS) == 12


# ---------------------------------------------------------------------------
# 3. Closed-set vocabularies + membership helpers
# ---------------------------------------------------------------------------


def test_projection_decisions_closed_set() -> None:
    assert STAGE30_11_6_PROJECTION_DECISIONS == (
        "PROJECTED_LIVE_CANDIDATE",
        "REJECTED_MISSING_REQUIRED_FIELD",
        "REJECTED_INVALID_FIELD_SHAPE",
    )
    assert STAGE30_11_6_PROJECTION_PASS_DECISION == PROJECTION_DECISION_PROJECTED
    for token in STAGE30_11_6_PROJECTION_DECISIONS:
        assert is_projection_decision(token)
    assert not is_projection_decision("NOPE")
    assert not is_projection_decision(None)
    # The two reject decisions are distinct from the pass decision.
    assert PROJECTION_DECISION_REJECTED_MISSING_FIELD != (
        PROJECTION_DECISION_PROJECTED
    )
    assert PROJECTION_DECISION_REJECTED_INVALID_SHAPE != (
        PROJECTION_DECISION_PROJECTED
    )


def test_projection_reasons_closed_set() -> None:
    assert STAGE30_11_6_PROJECTION_REASONS == (
        "READY_FOR_LIVE_RUNNER",
        "MISSING_REQUIRED_CANDIDATE_FIELD",
        "INVALID_CANDIDATE_FIELD_SHAPE",
    )
    assert STAGE30_11_6_PROJECTION_PASS_REASON == (
        PROJECTION_REASON_READY_FOR_LIVE_RUNNER
    )
    for token in STAGE30_11_6_PROJECTION_REASONS:
        assert is_projection_reason(token)
    assert not is_projection_reason("NOPE")
    assert PROJECTION_REASON_MISSING_REQUIRED_FIELD in (
        STAGE30_11_6_PROJECTION_REASONS
    )
    assert PROJECTION_REASON_INVALID_FIELD_SHAPE in (
        STAGE30_11_6_PROJECTION_REASONS
    )


def test_harvest_decisions_closed_set() -> None:
    assert STAGE30_11_6_HARVEST_DECISIONS == (
        "HARVESTED_LIVE_CANDIDATE",
        "SKIPPED_ASSEMBLY_FAILED",
        "SKIPPED_PROJECTION_REJECTED",
    )
    assert STAGE30_11_6_HARVEST_PASS_DECISION == HARVEST_DECISION_HARVESTED
    for token in STAGE30_11_6_HARVEST_DECISIONS:
        assert is_harvest_decision(token)
    assert not is_harvest_decision("NOPE")
    assert HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED in (
        STAGE30_11_6_HARVEST_DECISIONS
    )
    assert HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED in (
        STAGE30_11_6_HARVEST_DECISIONS
    )


def test_harvest_reasons_closed_set() -> None:
    assert STAGE30_11_6_HARVEST_REASONS == (
        "HARVESTED_READY_FOR_LIVE_RUNNER",
        "ASSEMBLY_RAISED_OR_EMPTY",
        "PROJECTION_FAILED_CLOSED",
    )
    assert STAGE30_11_6_HARVEST_PASS_REASON == HARVEST_REASON_READY_FOR_LIVE_RUNNER
    for token in STAGE30_11_6_HARVEST_REASONS:
        assert is_harvest_reason(token)
    assert not is_harvest_reason("NOPE")
    assert HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY in STAGE30_11_6_HARVEST_REASONS
    assert HARVEST_REASON_PROJECTION_FAILED_CLOSED in STAGE30_11_6_HARVEST_REASONS


def test_not_projected_sentinel_is_outside_the_projection_vocabularies() -> None:
    assert STAGE30_11_6_NOT_PROJECTED == "NOT_PROJECTED"
    assert STAGE30_11_6_NOT_PROJECTED not in STAGE30_11_6_PROJECTION_DECISIONS
    assert STAGE30_11_6_NOT_PROJECTED not in STAGE30_11_6_PROJECTION_REASONS
    assert not is_projection_decision(STAGE30_11_6_NOT_PROJECTED)
    assert not is_projection_reason(STAGE30_11_6_NOT_PROJECTED)


# ---------------------------------------------------------------------------
# 4. Hard cap + default + prefix + proof baseline
# ---------------------------------------------------------------------------


def test_hard_cap_and_default_and_prefix() -> None:
    assert STAGE30_11_6_MAX_HARVEST_HARD_CAP == 10
    assert STAGE30_11_6_DEFAULT_MAX_HARVEST == 10
    assert STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX == "stage30_11_6_cand_"


def test_proof_baseline_counts() -> None:
    assert STAGE30_11_6_EXPECTED_EVENTS_SEEN == 5
    assert STAGE30_11_6_EXPECTED_HARVESTED == 3
    assert STAGE30_11_6_EXPECTED_SKIPPED_ASSEMBLY_FAILED == 1
    assert STAGE30_11_6_EXPECTED_SKIPPED_PROJECTION_REJECTED == 1
    # The dip candidate id is the run-scoped id the harvest stamps for event 2.
    assert STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID == "stage30_11_6_cand_000002"
    assert STAGE30_11_6_EXPECTED_DIP_CANDIDATE_ID == (
        STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX + "000002"
    )
    assert STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT == "mint-tier1"


# ---------------------------------------------------------------------------
# 5. is_nonblank_str helper
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("x")
    assert not is_nonblank_str("")
    assert not is_nonblank_str("   ")
    assert not is_nonblank_str(None)
    assert not is_nonblank_str(123)


# ---------------------------------------------------------------------------
# 6. Frozen model dataclasses
# ---------------------------------------------------------------------------


def _projection() -> Stage30_11_6CandidateProjection:
    return Stage30_11_6CandidateProjection(
        candidate_id="c",
        token_mint="m",
        pair_type="SOL",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        source_ref="ref-c",
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_candidate_projection_is_frozen_and_field_named() -> None:
    p = _projection()
    assert p.candidate_id == "c"
    assert p.drawdown_from_ath == Decimal("0.55")
    with pytest.raises(FrozenInstanceError):
        p.candidate_id = "z"  # type: ignore[misc]
    assert candidate_projection_field_names() == (
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


def test_projection_result_and_outcome_field_names() -> None:
    assert candidate_projection_result_field_names() == (
        "candidate_id",
        "token_mint",
        "projection_decision",
        "projection_reason",
        "rejected_field",
        "projection",
        "created_at_utc",
    )
    assert candidate_harvest_outcome_field_names() == (
        "candidate_id",
        "token_mint",
        "harvest_decision",
        "harvest_reason",
        "projection_decision",
        "projection_reason",
        "rejected_field",
        "created_at_utc",
    )


def test_harvest_summary_and_result_field_names() -> None:
    assert harvest_summary_field_names() == (
        "events_seen",
        "harvested",
        "skipped_assembly_failed",
        "skipped_projection_rejected",
        "created_at_utc",
    )
    assert harvest_result_field_names() == (
        "outcomes",
        "candidate_source",
        "summary",
        "created_at_utc",
    )


def test_projection_result_carries_optional_projection() -> None:
    projected = Stage30_11_6CandidateProjectionResult(
        candidate_id="c",
        token_mint="m",
        projection_decision=PROJECTION_DECISION_PROJECTED,
        projection_reason=PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
        rejected_field="",
        projection=_projection(),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert projected.projection is not None
    rejected = Stage30_11_6CandidateProjectionResult(
        candidate_id="c",
        token_mint="m",
        projection_decision=PROJECTION_DECISION_REJECTED_MISSING_FIELD,
        projection_reason=PROJECTION_REASON_MISSING_REQUIRED_FIELD,
        rejected_field="current_market_cap_usd",
        projection=None,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert rejected.projection is None


def test_harvest_result_and_summary_construct() -> None:
    summary = Stage30_11_6HarvestSummary(
        events_seen=5,
        harvested=3,
        skipped_assembly_failed=1,
        skipped_projection_rejected=1,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    outcome = Stage30_11_6CandidateHarvestOutcome(
        candidate_id="c",
        token_mint="m",
        harvest_decision=HARVEST_DECISION_HARVESTED,
        harvest_reason=HARVEST_REASON_READY_FOR_LIVE_RUNNER,
        projection_decision=PROJECTION_DECISION_PROJECTED,
        projection_reason=PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
        rejected_field="",
        created_at_utc="2026-01-01T00:00:00Z",
    )
    result = Stage30_11_6HarvestResult(
        outcomes=(outcome,),
        candidate_source=(_projection(),),
        summary=summary,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert result.summary.harvested == 3
    assert len(result.candidate_source) == 1
    assert len(result.outcomes) == 1
