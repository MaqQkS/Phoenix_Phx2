"""Stage 29.5.7 composition: raw envelope -> Stage 30.11.9 -> 30.11.8 -> 30.11.7.

The OFFLINE PROOF TARGET. Composes the committed Stage 30.11.9 evidence-source
mapper/adapter, the committed Stage 30.11.8 confirmation, and the committed Stage
30.11.7 enrichment around the Stage 29.5.7 producer output -- this wiring lives in
a TEST (never a Stage 29.5.7 production module), so the Stage 29.5.7 slice imports
no Stage 30 module.

Proves the chain the Codex audit demanded:

    raw Helius migration envelope
      -> normalize_helius_raw_migration_envelope            (Stage 29.5.7)
      -> PRESENT Stage29_5MigrationEvidenceRecord
      -> project_migration_evidence_to_sanitized_summary    (Stage 29.5.7)
      -> build_evidence_record_from_sanitized_projection    (Stage 30.11.9)
      -> Stage30_11_9MigrationEvidenceSourceAdapter         (Stage 30.11.9)
      -> resolve_candidate_migration / build_migration_resolver (Stage 30.11.8) -> confirmed=True
      -> enrich_harvested_candidate (Stage 30.11.7): MIGRATION cleared
          * green ATH resolver  -> ENRICHED
          * missing ATH resolver -> REJECTED at ATH (no transport)
"""

from __future__ import annotations

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_normalizer import (
    normalize_helius_raw_migration_envelope,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
    Stage29_5_7LiveMigrationEvidenceProducer,
    project_migration_evidence_to_sanitized_summary,
)
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
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_evidence_record_from_sanitized_projection,
    build_migration_evidence_source,
)
from PHX2.tests.stage29._stage_29_5_7_helius_fixtures import (
    BASE_MINT,
    DEFAULT_ANCHOR_UTC,
    OBSERVED_AT_UTC,
    make_migration_envelope,
    make_swap_with_stray_create_pool_log_envelope,
)


_CREATED = "2026-05-27T00:10:00Z"


def _base(token_mint: str = BASE_MINT) -> dict:
    return {
        "candidate_id": "cand-mig",
        "token_mint": token_mint,
        "pair_type": "PUMP_AMM",
        "source_ref": "evt-mig",
        "created_at_utc": "2026-05-27T00:00:00Z",
    }


def _market(base: object) -> object:
    return {"present": True, "current_market_cap_usd": "42000.00"}


def _tier(base: object) -> object:
    return {"tier_hint": "Tier 1"}


def _ath_present(base: object) -> object:
    return {
        "present": True,
        "fresh": True,
        "post_migration_ath_verified": True,
        "drawdown_from_ath": "-25",
    }


def _ath_missing(base: object) -> object:
    return None


def _source_from_envelope(envelope: object):
    """Run the FULL Stage 29.5.7 producer path on a raw envelope and return a
    committed Stage 30.11.9 evidence source over the projected summary.
    """
    result = normalize_helius_raw_migration_envelope(
        envelope, OBSERVED_AT_UTC
    )
    assert result.evidence_record is not None
    summary = project_migration_evidence_to_sanitized_summary(
        result.evidence_record
    )
    assert summary is not None
    s30_record = build_evidence_record_from_sanitized_projection(
        token_mint=summary.token_mint,
        measurement_status=summary.measurement_status,
        migration_event_time_utc=summary.migration_event_time_utc,
        warnings=summary.warnings,
        redaction_status=summary.redaction_status,
        source_ref=summary.source_ref,
    )
    assert s30_record is not None

    def provider(token_mint: object) -> object:
        return [s30_record] if token_mint == summary.token_mint else []

    return build_migration_evidence_source(provider), summary


def _enrich(base: dict, *, migration_resolver, ath_resolver):
    return enrich_harvested_candidate(
        base,
        market_context_resolver=_market,
        tier_resolver=_tier,
        migration_resolver=migration_resolver,
        ath_resolver=ath_resolver,
        created_at_utc=_CREATED,
    )


# ---------------------------------------------------------------------------
# 1. Producer output is a COMPLETE / SAFE / trailing-Z / empty-warnings summary
# ---------------------------------------------------------------------------


def test_producer_summary_is_complete_safe_trailing_z_empty_warnings() -> None:
    _source, summary = _source_from_envelope(make_migration_envelope())
    assert summary.token_mint == BASE_MINT
    assert summary.measurement_status == "COMPLETE"
    assert summary.redaction_status == "SAFE"
    assert summary.warnings == ()
    assert summary.migration_event_time_utc == DEFAULT_ANCHOR_UTC
    assert summary.migration_event_time_utc.endswith("Z")
    assert "+00:00" not in summary.migration_event_time_utc


# ---------------------------------------------------------------------------
# 2/3. Same-mint binding + Stage 30.11.8 confirmation
# ---------------------------------------------------------------------------


def test_real_migration_confirms_under_stage_30_11_8() -> None:
    source, _summary = _source_from_envelope(make_migration_envelope())
    resolver = build_migration_resolver(source)
    res = resolver(_base())
    assert res.confirmed is True
    assert res.reason == CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT
    assert res.token_mint == BASE_MINT
    assert res.migration_event_time_utc == DEFAULT_ANCHOR_UTC


def test_evidence_binds_to_the_exact_harvested_mint_only() -> None:
    source, _summary = _source_from_envelope(make_migration_envelope())
    resolver = build_migration_resolver(source)
    # A candidate for a DIFFERENT mint gets no evidence (no cross-mint inherit).
    res = resolver(_base(token_mint="Zz" + "z" * 42))
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE


# ---------------------------------------------------------------------------
# 4. Stage 30.11.7 clears MIGRATION; full pass with green ATH
# ---------------------------------------------------------------------------


def test_confirmed_migration_plus_green_ath_enriches() -> None:
    source, _summary = _source_from_envelope(make_migration_envelope())
    resolver = build_migration_resolver(source)
    result = _enrich(_base(), migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enrichment_reason == ENRICH_REASON_READY_FOR_LIVE_RUNNER
    assert result.enriched_candidate is not None
    assert result.enriched_candidate.token_mint == BASE_MINT


def test_confirmed_migration_missing_ath_blocks_transport() -> None:
    source, _summary = _source_from_envelope(make_migration_envelope())
    resolver = build_migration_resolver(source)
    result = _enrich(_base(), migration_resolver=resolver, ath_resolver=_ath_missing)
    # MIGRATION cleared (we reached the ATH dimension), but no enriched candidate
    # -> nothing reaches transport.
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH
    assert result.enriched_candidate is None


# ---------------------------------------------------------------------------
# 5. A no-migration envelope yields NO evidence -> fails closed at MIGRATION
# ---------------------------------------------------------------------------


def test_no_evidence_source_fails_closed_at_migration() -> None:
    empty_source = build_migration_evidence_source(lambda mint: [])
    resolver = build_migration_resolver(empty_source)
    result = _enrich(_base(), migration_resolver=resolver, ath_resolver=_ath_present)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
    assert result.enrichment_reason == ENRICH_REASON_UNCONFIRMED_MIGRATION


# ---------------------------------------------------------------------------
# 6. Codex audit regression END-TO-END: an ordinary swap + stray CreatePool log
#    yields NO evidence through the producer, so Stage 30.11.8 cannot confirm and
#    Stage 30.11.7 fails closed at MIGRATION. The MIGRATION dimension clears ONLY
#    for a real create_pool instruction (proved by the positive tests above).
# ---------------------------------------------------------------------------


def test_swap_with_stray_create_pool_log_cannot_confirm_or_clear_migration() -> None:
    producer = Stage29_5_7LiveMigrationEvidenceProducer(
        clock=lambda: OBSERVED_AT_UTC
    )
    run = producer.produce_migration_evidence(
        [make_swap_with_stray_create_pool_log_envelope()], _CREATED
    )
    # The producer proves ZERO migrations and emits ZERO sanitized summaries.
    assert run.summary.migrations_proven == 0
    assert run.sanitized_summaries == ()

    # With no evidence, a Stage 30.11.9 source confirms nothing under 30.11.8.
    empty_source = build_migration_evidence_source(lambda mint: [])
    resolver = build_migration_resolver(empty_source)
    res = resolver(_base())
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE

    # Stage 30.11.7 fails closed at MIGRATION (never reaches ATH / transport).
    enriched = _enrich(
        _base(), migration_resolver=resolver, ath_resolver=_ath_present
    )
    assert enriched.enrichment_decision == ENRICH_DECISION_REJECTED
    assert enriched.rejected_dimension == ENRICH_DIMENSION_MIGRATION
    assert enriched.enrichment_reason == ENRICH_REASON_UNCONFIRMED_MIGRATION


# ---------------------------------------------------------------------------
# 11. Non-Z anchor: the projection carries it VERBATIM and Stage 30.11.8 rejects
#     it (the producer never emits +00:00; a hand-built offset record fails
#     closed downstream rather than being normalized into a passing anchor).
# ---------------------------------------------------------------------------


def test_offset_anchor_record_is_carried_verbatim_and_rejected() -> None:
    offset_record = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=BASE_MINT,
        pool_account="Po" + "o" * 42,
        pool_program_id="Pg" + "p" * 42,
        quote_mint="Qm" + "q" * 42,
        migration_timestamp_utc="2024-05-27T00:00:00+00:00",
        migration_slot=1,
        migration_signature="sig",
        observed_at_utc=OBSERVED_AT_UTC,
        source_event_ref="ref",
    )
    summary = project_migration_evidence_to_sanitized_summary(offset_record)
    assert summary is not None
    # Carried VERBATIM -- NOT reformatted to a trailing-Z form.
    assert summary.migration_event_time_utc == "2024-05-27T00:00:00+00:00"
    s30_record = build_evidence_record_from_sanitized_projection(
        token_mint=summary.token_mint,
        measurement_status=summary.measurement_status,
        migration_event_time_utc=summary.migration_event_time_utc,
        warnings=summary.warnings,
        redaction_status=summary.redaction_status,
        source_ref=summary.source_ref,
    )
    assert s30_record is not None

    def provider(token_mint: object) -> object:
        return [s30_record] if token_mint == BASE_MINT else []

    resolver = build_migration_resolver(
        build_migration_evidence_source(provider)
    )
    res = resolver(_base())
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_ANCHOR
