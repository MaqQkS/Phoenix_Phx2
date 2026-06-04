"""Stage 30.11.9 composition tests (source -> Stage 30.11.8 confirmation -> Stage
30.11.7 enrichment).

These tests compose the committed Stage 30.11.8 confirmation adapter and the committed
Stage 30.11.7 enrichment adapter around the Stage 30.11.9 source -- this lives in a
TEST (never a Stage 30.11.9 production module), so the Stage 30.11.9 production slice
stays a clean leaf that imports neither.

Proves:
  * a Stage 30.11.9 source over a confirming record drives a Stage 30.11.8
    ``confirmed=True`` resolution and clears the Stage 30.11.7 MIGRATION dimension;
  * a confirmed migration with a MISSING ATH still fails closed at the ATH dimension --
    so a confirmed migration ALONE never reaches transport (no enriched candidate);
  * a missing / wrong-mint / offset-anchor reading fails closed at MIGRATION.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
    enrich_harvested_candidate,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
    ENRICH_DIMENSION_ATH,
    ENRICH_DIMENSION_MIGRATION,
    ENRICH_REASON_MISSING_ATH,
    ENRICH_REASON_READY_FOR_LIVE_RUNNER,
    ENRICH_REASON_UNCONFIRMED_MIGRATION,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_adapter import (
    build_migration_resolver,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
    CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE,
    CONFIRM_REASON_STALE_MIGRATION_EVIDENCE,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_evidence_record_from_sanitized_projection,
    build_migration_evidence_source,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    Stage30_11_9MigrationEvidenceRecord,
)


_BASE = {
    "candidate_id": "cand-live",
    "token_mint": "mint-live",
    "pair_type": "PUMP_AMM",
    "source_ref": "evt-live",
    "created_at_utc": "2026-05-27T00:00:00Z",
}
_CREATED = "2026-05-27T00:05:00Z"
_VALID_ANCHOR = "2026-05-27T00:00:00Z"


def _market(base: object) -> object:
    return {"present": True, "current_market_cap_usd": "12345.67"}


def _tier(base: object) -> object:
    return {"tier_hint": "Tier 1"}


def _ath_present(base: object) -> object:
    return {
        "present": True,
        "fresh": True,
        "post_migration_ath_verified": True,
        "drawdown_from_ath": "-30",
    }


def _ath_missing(base: object) -> object:
    return None


def _confirming_source(*, mint: str = "mint-live", anchor: str = _VALID_ANCHOR):
    record = build_evidence_record_from_sanitized_projection(
        token_mint=mint,
        measurement_status="COMPLETE",
        migration_event_time_utc=anchor,
        warnings=(),
        redaction_status="SAFE",
        source_ref="mig-ref",
    )

    def provider(token_mint: object) -> object:
        return [record] if token_mint == mint else []

    return build_migration_evidence_source(provider)


def _enrich(*, migration_resolver: object, ath_resolver: object, base: object = None):
    return enrich_harvested_candidate(
        _BASE if base is None else base,
        market_context_resolver=_market,
        tier_resolver=_tier,
        migration_resolver=migration_resolver,
        ath_resolver=ath_resolver,
        created_at_utc=_CREATED,
    )


# ---------------------------------------------------------------------------
# 1. Source -> Stage 30.11.8 confirmation
# ---------------------------------------------------------------------------


def test_source_drives_a_confirmed_resolution() -> None:
    resolver = build_migration_resolver(_confirming_source())
    res = resolver(_BASE)
    assert res.confirmed is True
    assert res.reason == CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT
    assert res.token_mint == "mint-live"
    assert res.migration_event_time_utc == _VALID_ANCHOR
    assert res.source_ref == "mig-ref"


# ---------------------------------------------------------------------------
# 2. Confirmed migration clears MIGRATION; full pass when ATH present
# ---------------------------------------------------------------------------


def test_confirmed_plus_present_ath_enriches() -> None:
    resolver = build_migration_resolver(_confirming_source())
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enrichment_reason == ENRICH_REASON_READY_FOR_LIVE_RUNNER
    assert result.enriched_candidate is not None
    assert result.enriched_candidate.token_mint == "mint-live"


# ---------------------------------------------------------------------------
# 3. Transport safety: confirmed migration + MISSING ATH still fails closed
# ---------------------------------------------------------------------------


def test_confirmed_migration_but_missing_ath_blocks_transport() -> None:
    resolver = build_migration_resolver(_confirming_source())
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_missing)
    # MIGRATION cleared (we reached the ATH dimension), but no enriched candidate ->
    # nothing can reach transport.
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH
    assert result.enriched_candidate is None


# ---------------------------------------------------------------------------
# 4. Missing / wrong-mint / offset-anchor readings fail closed at MIGRATION
# ---------------------------------------------------------------------------


def test_missing_evidence_fails_closed_at_migration() -> None:
    empty_source = build_migration_evidence_source(lambda mint: [])
    resolver = build_migration_resolver(empty_source)
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
    assert result.enrichment_reason == ENRICH_REASON_UNCONFIRMED_MIGRATION


def test_other_mint_candidate_gets_no_evidence() -> None:
    resolver = build_migration_resolver(_confirming_source(mint="mint-live"))
    other_base = dict(_BASE, token_mint="mint-other")
    res = resolver(other_base)
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE


def test_offset_anchor_record_is_rejected_by_confirmation() -> None:
    # The source carries the offset-form anchor VERBATIM; the Stage 30.11.8
    # confirmation (Z-only) rejects it -> fails closed at MIGRATION.
    resolver = build_migration_resolver(
        _confirming_source(anchor="2026-05-27T00:00:00+00:00")
    )
    res = resolver(_BASE)
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_ANCHOR
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION


# ---------------------------------------------------------------------------
# 5. Stale warnings (Codex repro) fail closed end-to-end
# ---------------------------------------------------------------------------


def _source_with_record(record: object, *, mint: str = "mint-live"):
    def provider(token_mint: object) -> object:
        return [record] if token_mint == mint else []

    return build_migration_evidence_source(provider)


def test_malformed_stale_warnings_fail_closed_end_to_end() -> None:
    # The Codex repro, end-to-end: an OTHERWISE-confirmable record whose warnings is
    # the bare string "MIGRATION_STALE" (malformed) is REJECTED by the Stage 30.11.9
    # source (None), so Stage 30.11.8 reports MISSING_MIGRATION_EVIDENCE (confirmed
    # False) and Stage 30.11.7 fails closed at MIGRATION. The malformed stale field is
    # NEVER silently emptied into confirmable clean evidence.
    rec = Stage30_11_9MigrationEvidenceRecord(
        token_mint="mint-live",
        measurement_status="COMPLETE",
        migration_event_time_utc=_VALID_ANCHOR,
        warnings="MIGRATION_STALE",  # type: ignore[arg-type]
        redaction_status="SAFE",
        source_ref="mig-ref",
    )
    resolver = build_migration_resolver(_source_with_record(rec))
    res = resolver(_BASE)
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION


def test_wellformed_stale_warnings_block_at_confirmation_end_to_end() -> None:
    # A WELL-FORMED stale warnings (a tuple of strings) is ROUTED by the Stage 30.11.9
    # source and BLOCKED by the Stage 30.11.8 confirmation as stale (confirmed False,
    # STALE_MIGRATION_EVIDENCE); Stage 30.11.7 fails closed at MIGRATION. Staleness is
    # the confirmation's decision, not the source's.
    rec = build_evidence_record_from_sanitized_projection(
        token_mint="mint-live",
        measurement_status="COMPLETE",
        migration_event_time_utc=_VALID_ANCHOR,
        warnings=("MIGRATION_STALE",),
        redaction_status="SAFE",
        source_ref="mig-ref",
    )
    assert rec is not None
    resolver = build_migration_resolver(_source_with_record(rec))
    res = resolver(_BASE)
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_STALE_MIGRATION_EVIDENCE
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION


def test_missing_warnings_fail_closed_end_to_end() -> None:
    # The Codex re-audit repro, end-to-end: an OTHERWISE-confirmable record built
    # WITHOUT a warnings field (model default None = MISSING) is REJECTED by the Stage
    # 30.11.9 source (None), so Stage 30.11.8 reports MISSING_MIGRATION_EVIDENCE
    # (confirmed False) and Stage 30.11.7 fails closed at MIGRATION. A missing field is
    # NEVER silently treated as a clean empty "no warnings".
    rec = Stage30_11_9MigrationEvidenceRecord(
        token_mint="mint-live",
        measurement_status="COMPLETE",
        migration_event_time_utc=_VALID_ANCHOR,
        redaction_status="SAFE",
        source_ref="mig-ref",
    )  # warnings omitted -> None (the fail-closed default)
    assert rec.warnings is None
    resolver = build_migration_resolver(_source_with_record(rec))
    res = resolver(_BASE)
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE
    result = _enrich(migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
