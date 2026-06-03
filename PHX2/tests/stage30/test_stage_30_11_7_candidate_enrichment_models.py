"""Stage 30.11.7 candidate dip-enrichment models tests.

Pins the Stage 30.11.7 model layer: the minor + schema version, the enrichment
decision / reason / dimension closed sets + membership helpers + pass tokens, the
four fail-closed-by-default resolver-result carriers, the Stage 30.11.5-shaped flat
enriched candidate (its field names cross-checked against the committed Stage
30.11.6 projection field names BY VALUE), the enrichment result / summary /
run-result shapes, the field-name helpers, the hard cap + default, the PRESENT
token, the expected proof baseline, and the no-secret-field-name guard.

Pure / offline. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from decimal import Decimal

import PHX2.stage30.stage30_11_7_candidate_enrichment_models as M
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
    ENRICH_DIMENSION_ATH,
    ENRICH_DIMENSION_MARKET_CONTEXT,
    ENRICH_DIMENSION_MIGRATION,
    ENRICH_DIMENSION_NONE,
    ENRICH_DIMENSION_TIER,
    ENRICH_REASON_READY_FOR_LIVE_RUNNER,
    STAGE30_11_7_CONTEXT_STATUS_PRESENT,
    STAGE30_11_7_DEFAULT_MAX_ENRICH,
    STAGE30_11_7_ENRICHED_FIELDS,
    STAGE30_11_7_ENRICHMENT_DECISIONS,
    STAGE30_11_7_ENRICHMENT_DIMENSIONS,
    STAGE30_11_7_ENRICHMENT_PASS_DECISION,
    STAGE30_11_7_ENRICHMENT_PASS_REASON,
    STAGE30_11_7_ENRICHMENT_REASONS,
    STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION,
    STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_7_EXPECTED_ENRICHED,
    STAGE30_11_7_MAX_ENRICH_HARD_CAP,
    STAGE30_11_7_MINOR_VERSION,
    STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS,
    STAGE30_11_7_REQUIRED_ENRICHED_FIELDS,
    Stage30_11_7AthResolution,
    Stage30_11_7EnrichedCandidate,
    Stage30_11_7EnrichmentResult,
    Stage30_11_7EnrichmentRunResult,
    Stage30_11_7EnrichmentSummary,
    Stage30_11_7MarketContextResolution,
    Stage30_11_7MigrationResolution,
    Stage30_11_7TierResolution,
    ath_resolution_field_names,
    enriched_candidate_field_names,
    enrichment_result_field_names,
    enrichment_run_result_field_names,
    enrichment_summary_field_names,
    is_enrichment_decision,
    is_enrichment_dimension,
    is_enrichment_reason,
    is_nonblank_str,
    market_context_resolution_field_names,
    migration_resolution_field_names,
    tier_resolution_field_names,
)


# ---------------------------------------------------------------------------
# 1. Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_and_schema_version_pinned() -> None:
    assert STAGE30_11_7_MINOR_VERSION == "30.11.7"
    assert STAGE30_11_7_ENRICHMENT_SCHEMA_VERSION == (
        "stage30_11_7_v0_candidate_enrichment"
    )
    assert M.STAGE30_11_7_SOURCE_STAGE == "30.11.7"


# ---------------------------------------------------------------------------
# 2. Decisions / reasons / dimensions closed sets
# ---------------------------------------------------------------------------


def test_enrichment_decisions_closed_set() -> None:
    assert STAGE30_11_7_ENRICHMENT_DECISIONS == (
        "ENRICHED_DIP_CANDIDATE",
        "REJECTED_ENRICHMENT",
    )
    assert STAGE30_11_7_ENRICHMENT_PASS_DECISION == ENRICH_DECISION_ENRICHED
    assert ENRICH_DECISION_ENRICHED == "ENRICHED_DIP_CANDIDATE"
    assert ENRICH_DECISION_REJECTED == "REJECTED_ENRICHMENT"
    for d in STAGE30_11_7_ENRICHMENT_DECISIONS:
        assert is_enrichment_decision(d)
    assert not is_enrichment_decision("nope")
    assert not is_enrichment_decision(None)


def test_enrichment_reasons_closed_set() -> None:
    assert STAGE30_11_7_ENRICHMENT_REASONS == (
        "READY_FOR_LIVE_RUNNER",
        "MISSING_MARKET_CONTEXT",
        "INVALID_MARKET_CAP",
        "MISSING_TIER",
        "MISSING_MIGRATION_EVIDENCE",
        "UNCONFIRMED_MIGRATION",
        "MISSING_ATH",
        "STALE_ATH",
        "PRE_MIGRATION_ATH_NOT_VERIFIED",
        "INVALID_DRAWDOWN",
    )
    assert STAGE30_11_7_ENRICHMENT_PASS_REASON == (
        ENRICH_REASON_READY_FOR_LIVE_RUNNER
    )
    for r in STAGE30_11_7_ENRICHMENT_REASONS:
        assert is_enrichment_reason(r)
    assert not is_enrichment_reason("nope")
    # The only reason that accompanies an enriched decision is READY.
    assert STAGE30_11_7_ENRICHMENT_PASS_REASON == "READY_FOR_LIVE_RUNNER"


def test_enrichment_dimensions_closed_set() -> None:
    assert STAGE30_11_7_ENRICHMENT_DIMENSIONS == (
        "MARKET_CONTEXT",
        "TIER",
        "MIGRATION",
        "ATH",
    )
    assert ENRICH_DIMENSION_NONE == ""
    for d in STAGE30_11_7_ENRICHMENT_DIMENSIONS:
        assert is_enrichment_dimension(d)
    # The empty enriched sentinel is NOT a dimension.
    assert not is_enrichment_dimension(ENRICH_DIMENSION_NONE)
    assert not is_enrichment_dimension("nope")
    assert ENRICH_DIMENSION_MARKET_CONTEXT == "MARKET_CONTEXT"
    assert ENRICH_DIMENSION_TIER == "TIER"
    assert ENRICH_DIMENSION_MIGRATION == "MIGRATION"
    assert ENRICH_DIMENSION_ATH == "ATH"


# ---------------------------------------------------------------------------
# 3. Enriched-candidate field names mirror the committed Stage 30.11.6 projection
# ---------------------------------------------------------------------------


def test_enriched_field_names_match_models_and_stage_30_11_6() -> None:
    from PHX2.stage30.stage30_11_6_candidate_source_models import (
        STAGE30_11_6_PROJECTION_FIELDS,
    )

    assert enriched_candidate_field_names() == STAGE30_11_7_ENRICHED_FIELDS
    # The enriched candidate IS the committed Stage 30.11.5 / 30.11.6 flat
    # projection shape BY VALUE, so the committed runner reads it directly.
    assert STAGE30_11_7_ENRICHED_FIELDS == STAGE30_11_6_PROJECTION_FIELDS
    assert "tier_hint" in STAGE30_11_7_ENRICHED_FIELDS
    assert "current_market_cap_usd" in STAGE30_11_7_ENRICHED_FIELDS


def test_required_and_optional_enriched_fields() -> None:
    assert len(STAGE30_11_7_REQUIRED_ENRICHED_FIELDS) == 10
    assert STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS == (
        "post_migration_ath_verified",
        "source_ref",
    )
    # Required + optional partition the full field set (order-independent).
    assert set(STAGE30_11_7_REQUIRED_ENRICHED_FIELDS) | set(
        STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS
    ) == set(STAGE30_11_7_ENRICHED_FIELDS)
    assert not (
        set(STAGE30_11_7_REQUIRED_ENRICHED_FIELDS)
        & set(STAGE30_11_7_OPTIONAL_ENRICHED_FIELDS)
    )


# ---------------------------------------------------------------------------
# 4. Model + resolver field-name helpers
# ---------------------------------------------------------------------------


def test_model_field_name_helpers() -> None:
    assert enrichment_result_field_names() == (
        "candidate_id",
        "token_mint",
        "enrichment_decision",
        "enrichment_reason",
        "rejected_dimension",
        "enriched_candidate",
        "created_at_utc",
    )
    assert enrichment_summary_field_names() == (
        "bases_seen",
        "enriched",
        "rejected_market_context",
        "rejected_tier",
        "rejected_migration",
        "rejected_ath",
        "created_at_utc",
    )
    assert enrichment_run_result_field_names() == (
        "outcomes",
        "candidate_source",
        "summary",
        "created_at_utc",
    )


def test_resolver_result_field_name_helpers() -> None:
    assert market_context_resolution_field_names() == (
        "present",
        "current_market_cap_usd",
        "source_ref",
    )
    assert tier_resolution_field_names() == ("tier_hint",)
    assert migration_resolution_field_names() == ("confirmed", "source_ref")
    assert ath_resolution_field_names() == (
        "present",
        "fresh",
        "post_migration_ath_verified",
        "drawdown_from_ath",
        "source_ref",
    )


# ---------------------------------------------------------------------------
# 5. Resolver carriers default to fail-closed values
# ---------------------------------------------------------------------------


def test_resolver_carriers_default_fail_closed() -> None:
    mc = Stage30_11_7MarketContextResolution()
    assert mc.present is False
    assert mc.current_market_cap_usd is None
    assert mc.source_ref is None

    tier = Stage30_11_7TierResolution()
    assert tier.tier_hint is None

    mig = Stage30_11_7MigrationResolution()
    assert mig.confirmed is False
    assert mig.source_ref is None

    ath = Stage30_11_7AthResolution()
    assert ath.present is False
    assert ath.fresh is False
    assert ath.post_migration_ath_verified is None
    assert ath.drawdown_from_ath is None
    assert ath.source_ref is None


# ---------------------------------------------------------------------------
# 6. PRESENT token + hard cap + default + expected baseline
# ---------------------------------------------------------------------------


def test_present_token_cap_and_default() -> None:
    assert STAGE30_11_7_CONTEXT_STATUS_PRESENT == "PRESENT"
    assert STAGE30_11_7_MAX_ENRICH_HARD_CAP == 10
    assert STAGE30_11_7_DEFAULT_MAX_ENRICH == 10
    assert (
        STAGE30_11_7_DEFAULT_MAX_ENRICH <= STAGE30_11_7_MAX_ENRICH_HARD_CAP
    )


def test_expected_baseline_pinned() -> None:
    assert M.STAGE30_11_7_EXPECTED_BASES_SEEN == 6
    assert STAGE30_11_7_EXPECTED_ENRICHED == 2
    assert M.STAGE30_11_7_EXPECTED_REJECTED_MARKET_CONTEXT == 1
    assert M.STAGE30_11_7_EXPECTED_REJECTED_TIER == 1
    assert M.STAGE30_11_7_EXPECTED_REJECTED_MIGRATION == 1
    assert M.STAGE30_11_7_EXPECTED_REJECTED_ATH == 1
    assert M.STAGE30_11_7_EXPECTED_RUNNER_CANDIDATES_SEEN == 2
    assert M.STAGE30_11_7_EXPECTED_RUNNER_BRIDGED == 2
    assert M.STAGE30_11_7_EXPECTED_RUNNER_GATE_PASSED == 1
    assert M.STAGE30_11_7_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert M.STAGE30_11_7_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID == "stage30_11_7_cand_dip"
    assert STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT == "mint-dip"


# ---------------------------------------------------------------------------
# 7. Models are immutable + carry only safe scalars
# ---------------------------------------------------------------------------


def test_enriched_candidate_is_immutable() -> None:
    enriched = Stage30_11_7EnrichedCandidate(
        candidate_id="c",
        token_mint="m",
        pair_type="SOL",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.5"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("1000"),
        post_migration_ath_verified=True,
        source_ref=None,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    try:
        enriched.tier_hint = "Tier 2"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("Stage30_11_7EnrichedCandidate must be frozen")


def test_result_summary_run_result_construct() -> None:
    enriched = Stage30_11_7EnrichedCandidate(
        candidate_id="c",
        token_mint="m",
        pair_type="SOL",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.5"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("1000"),
        post_migration_ath_verified=True,
        source_ref=None,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    result = Stage30_11_7EnrichmentResult(
        candidate_id="c",
        token_mint="m",
        enrichment_decision=ENRICH_DECISION_ENRICHED,
        enrichment_reason=ENRICH_REASON_READY_FOR_LIVE_RUNNER,
        rejected_dimension=ENRICH_DIMENSION_NONE,
        enriched_candidate=enriched,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    summary = Stage30_11_7EnrichmentSummary(
        bases_seen=1,
        enriched=1,
        rejected_market_context=0,
        rejected_tier=0,
        rejected_migration=0,
        rejected_ath=0,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    run = Stage30_11_7EnrichmentRunResult(
        outcomes=(result,),
        candidate_source=(enriched,),
        summary=summary,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert run.candidate_source[0] is enriched
    assert run.outcomes[0].enriched_candidate is enriched


# ---------------------------------------------------------------------------
# 8. No secret / payload field names anywhere
# ---------------------------------------------------------------------------


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        enriched_candidate_field_names()
        + enrichment_result_field_names()
        + enrichment_summary_field_names()
        + enrichment_run_result_field_names()
        + market_context_resolution_field_names()
        + tier_resolution_field_names()
        + migration_resolution_field_names()
        + ath_resolution_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "web" + "hook",
            "api_key",
            "bearer",
            "authorization",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.7 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 9. is_nonblank_str helper
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("Tier 1")
    assert not is_nonblank_str("")
    assert not is_nonblank_str("   ")
    assert not is_nonblank_str(None)
    assert not is_nonblank_str(5)
