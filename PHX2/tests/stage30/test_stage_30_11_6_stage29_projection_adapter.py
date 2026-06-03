"""Stage 30.11.6 harvested-candidate -> Stage 30.11.5 projection adapter tests.

Proves the fail-closed projection: a complete flat field set (a dict OR an
attribute-bearing object) projects into a Stage 30.11.5-shaped flat projection
with finite-coerced decimals; a missing required field fails closed to
REJECTED_MISSING_REQUIRED_FIELD naming that field; a present-but-blank / wrong-
typed required field, a non-finite-coercible decimal, or a malformed optional
fails closed to REJECTED_INVALID_FIELD_SHAPE; candidate identity is echoed even on
a reject; a degraded context token is carried VERBATIM (never forced to the
bridge's PRESENT value); and the projection never fabricates a missing field.

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

from PHX2.stage30.stage30_11_6_candidate_source_models import (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
    PROJECTION_DECISION_REJECTED_MISSING_FIELD,
    PROJECTION_REASON_INVALID_FIELD_SHAPE,
    PROJECTION_REASON_MISSING_REQUIRED_FIELD,
    PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
    STAGE30_11_6_REQUIRED_PROJECTION_FIELDS,
)
from PHX2.stage30.stage30_11_6_stage29_projection_adapter import (
    project_harvested_candidate,
)


_CREATED_AT = "2026-01-01T00:00:00Z"


def _complete_fields(**overrides: object) -> Dict[str, object]:
    fields: Dict[str, object] = {
        "candidate_id": "cand-1",
        "token_mint": "mint-1",
        "pair_type": "SOL",
        "tier_hint": "Tier 1",
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        "current_market_cap_usd": "12345.67",
        "post_migration_ath_verified": True,
        "source_ref": "ref-cand-1",
        "created_at_utc": _CREATED_AT,
    }
    fields.update(overrides)
    return fields


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_complete_dict_projects() -> None:
    result = project_harvested_candidate(
        _complete_fields(), created_at_utc=_CREATED_AT
    )
    assert result.projection_decision == PROJECTION_DECISION_PROJECTED
    assert result.projection_reason == PROJECTION_REASON_READY_FOR_LIVE_RUNNER
    assert result.rejected_field == ""
    assert result.candidate_id == "cand-1"
    assert result.token_mint == "mint-1"
    p = result.projection
    assert p is not None
    # Decimals are coerced to finite Decimal magnitudes.
    assert p.drawdown_from_ath == Decimal("0.55")
    assert p.current_market_cap_usd == Decimal("12345.67")
    assert p.pair_type == "SOL"
    assert p.tier_hint == "Tier 1"
    assert p.post_migration_ath_verified is True
    assert p.source_ref == "ref-cand-1"
    assert p.created_at_utc == _CREATED_AT


def test_attribute_object_input_projects() -> None:
    @dataclass(frozen=True)
    class _Flat:
        candidate_id: str
        token_mint: str
        pair_type: str
        tier_hint: str
        drawdown_from_ath: str
        migration_status: str
        ath_status: str
        market_context_status: str
        current_market_cap_usd: str
        post_migration_ath_verified: Optional[bool]
        source_ref: Optional[str]
        created_at_utc: str

    obj = _Flat(
        candidate_id="cand-2",
        token_mint="mint-2",
        pair_type="SOL",
        tier_hint="Tier 2",
        drawdown_from_ath="0.40",
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd="999",
        post_migration_ath_verified=None,
        source_ref=None,
        created_at_utc=_CREATED_AT,
    )
    result = project_harvested_candidate(obj, created_at_utc=_CREATED_AT)
    assert result.projection_decision == PROJECTION_DECISION_PROJECTED
    p = result.projection
    assert p is not None
    assert p.candidate_id == "cand-2"
    assert p.post_migration_ath_verified is None
    assert p.source_ref is None
    assert p.current_market_cap_usd == Decimal("999")


def test_int_decimal_coerces() -> None:
    result = project_harvested_candidate(
        _complete_fields(current_market_cap_usd=12345, drawdown_from_ath=1),
        created_at_utc=_CREATED_AT,
    )
    assert result.projection_decision == PROJECTION_DECISION_PROJECTED
    assert result.projection is not None
    assert result.projection.current_market_cap_usd == Decimal(12345)


# ---------------------------------------------------------------------------
# 2. Missing required fields fail closed (naming the FIRST offender)
# ---------------------------------------------------------------------------


def test_each_required_field_missing_fails_closed() -> None:
    for field in STAGE30_11_6_REQUIRED_PROJECTION_FIELDS:
        fields = _complete_fields()
        del fields[field]
        result = project_harvested_candidate(fields, created_at_utc=_CREATED_AT)
        assert result.projection_decision == (
            PROJECTION_DECISION_REJECTED_MISSING_FIELD
        ), f"missing {field!r} must be MISSING"
        assert result.projection_reason == (
            PROJECTION_REASON_MISSING_REQUIRED_FIELD
        )
        assert result.rejected_field == field
        assert result.projection is None


def test_missing_market_cap_does_not_become_eligible() -> None:
    # The canonical "malformed candidate does not reach the runner" case: a missing
    # required market-cap field fails closed -> no projection.
    fields = _complete_fields()
    del fields["current_market_cap_usd"]
    result = project_harvested_candidate(fields, created_at_utc=_CREATED_AT)
    assert result.projection is None
    assert result.rejected_field == "current_market_cap_usd"


# ---------------------------------------------------------------------------
# 3. Malformed shapes fail closed
# ---------------------------------------------------------------------------


def test_blank_required_string_fails_closed() -> None:
    result = project_harvested_candidate(
        _complete_fields(tier_hint="   "), created_at_utc=_CREATED_AT
    )
    assert result.projection_decision == (
        PROJECTION_DECISION_REJECTED_INVALID_SHAPE
    )
    assert result.projection_reason == PROJECTION_REASON_INVALID_FIELD_SHAPE
    assert result.rejected_field == "tier_hint"
    assert result.projection is None


def test_non_string_required_field_fails_closed() -> None:
    result = project_harvested_candidate(
        _complete_fields(candidate_id=123), created_at_utc=_CREATED_AT
    )
    assert result.projection_decision == (
        PROJECTION_DECISION_REJECTED_INVALID_SHAPE
    )
    assert result.rejected_field == "candidate_id"


def test_non_finite_decimal_fails_closed() -> None:
    for bad in ("not-a-number", "NaN", "Infinity", "", "   "):
        result = project_harvested_candidate(
            _complete_fields(drawdown_from_ath=bad), created_at_utc=_CREATED_AT
        )
        assert result.projection_decision == (
            PROJECTION_DECISION_REJECTED_INVALID_SHAPE
        ), f"{bad!r} must be INVALID"
        assert result.rejected_field == "drawdown_from_ath"
        assert result.projection is None


def test_bool_is_not_a_decimal() -> None:
    result = project_harvested_candidate(
        _complete_fields(current_market_cap_usd=True), created_at_utc=_CREATED_AT
    )
    assert result.projection_decision == (
        PROJECTION_DECISION_REJECTED_INVALID_SHAPE
    )
    assert result.rejected_field == "current_market_cap_usd"


def test_malformed_optionals_fail_closed() -> None:
    bad_verified = project_harvested_candidate(
        _complete_fields(post_migration_ath_verified="yes"),
        created_at_utc=_CREATED_AT,
    )
    assert bad_verified.projection_decision == (
        PROJECTION_DECISION_REJECTED_INVALID_SHAPE
    )
    assert bad_verified.rejected_field == "post_migration_ath_verified"

    bad_ref = project_harvested_candidate(
        _complete_fields(source_ref=123), created_at_utc=_CREATED_AT
    )
    assert bad_ref.projection_decision == (
        PROJECTION_DECISION_REJECTED_INVALID_SHAPE
    )
    assert bad_ref.rejected_field == "source_ref"


# ---------------------------------------------------------------------------
# 4. No fabrication / identity preserved / non-mapping input
# ---------------------------------------------------------------------------


def test_degraded_context_carried_verbatim_not_forced_to_present() -> None:
    # An unknown pair / a degraded ATH context is carried VERBATIM (the projection
    # never forces it to the bridge's PRESENT value); it still PROJECTS (the
    # committed bridge / dip gate decide eligibility LATER), so it never becomes
    # dip-eligible at the projection step.
    result = project_harvested_candidate(
        _complete_fields(ath_status="DEGRADED", pair_type="UNKNOWN"),
        created_at_utc=_CREATED_AT,
    )
    assert result.projection_decision == PROJECTION_DECISION_PROJECTED
    assert result.projection is not None
    assert result.projection.ath_status == "DEGRADED"
    assert result.projection.pair_type == "UNKNOWN"


def test_identity_echoed_even_on_reject() -> None:
    fields = _complete_fields()
    del fields["pair_type"]
    result = project_harvested_candidate(fields, created_at_utc=_CREATED_AT)
    assert result.projection is None
    # candidate_id / token_mint are still readable, so they are echoed.
    assert result.candidate_id == "cand-1"
    assert result.token_mint == "mint-1"


def test_non_mapping_input_fails_closed() -> None:
    for bad in (None, 42, "a string", object()):
        result = project_harvested_candidate(bad, created_at_utc=_CREATED_AT)
        assert result.projection_decision == (
            PROJECTION_DECISION_REJECTED_MISSING_FIELD
        )
        assert result.rejected_field == "candidate_id"
        assert result.projection is None
        assert result.candidate_id == ""
        assert result.token_mint == ""


def test_result_created_at_is_the_injected_stamp() -> None:
    # The result timestamp is the injected run stamp; the projection carries the
    # harvested created_at_utc (which may differ).
    result = project_harvested_candidate(
        _complete_fields(created_at_utc="2025-12-31T00:00:00Z"),
        created_at_utc=_CREATED_AT,
    )
    assert result.created_at_utc == _CREATED_AT
    assert result.projection is not None
    assert result.projection.created_at_utc == "2025-12-31T00:00:00Z"
