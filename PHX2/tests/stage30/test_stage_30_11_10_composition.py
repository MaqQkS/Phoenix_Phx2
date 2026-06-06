"""Stage 30.11.10 composition tests (ATH resolver -> committed Stage 30.11.7 enrichment;
real Stage 27.4 read_ath_context -> resolver; real Stage 30.11.8/30.11.9 migration path).

These tests compose the committed Stage 30.11.7 enrichment adapter, the committed Stage
30.11.8 migration confirmation + Stage 30.11.9 evidence source, and the committed Stage
27.4 ``read_ath_context`` around the Stage 30.11.10 ATH resolver -- this lives in a TEST
(never a Stage 30.11.10 production module), so the Stage 30.11.10 production slice stays a
clean leaf that imports none of them.

Proves (mapping the ATH blocker audit's required behavior):
  * a confirmed migration + a real-shaped resolved ATH clears MIGRATION and ATH ->
    ENRICHED_DIP_CANDIDATE / READY_FOR_LIVE_RUNNER;
  * a missing / stale / source-erroring / cross-mint ATH still fails closed at the ATH
    dimension (MISSING_ATH) -- so a confirmed migration ALONE never reaches transport;
  * a pre-migration ATH fails closed at PRE_MIGRATION_ATH_NOT_VERIFIED;
  * a present + post-migration ATH with a missing / invalid (NaN / Inf / float / bool /
    garbage) drawdown fails closed at INVALID_DRAWDOWN;
  * the FULL real-data path -- migration confirmed through Stage 30.11.8 over a Stage
    30.11.9 source -> the Stage 30.11.10 ATH resolver -> the Stage 30.11.7 enrichment;
  * the GOLD-STANDARD -- the committed Stage 27.4 ``read_ath_context`` output maps through
    the resolver and enriches end to end.

Pure / offline. No live call, no provider, no private send, no env read.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
    enrich_harvested_candidate,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
    ENRICH_DIMENSION_ATH,
    ENRICH_REASON_INVALID_DRAWDOWN,
    ENRICH_REASON_MISSING_ATH,
    ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ENRICH_REASON_READY_FOR_LIVE_RUNNER,
    STAGE30_11_7_CONTEXT_STATUS_PRESENT,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_adapter import (
    build_migration_resolver,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_evidence_record_from_sanitized_projection,
    build_migration_evidence_source,
)
from PHX2.stage30.stage30_11_10_ath_resolver_adapter import build_ath_resolver
from PHX2.stage30.stage30_11_10_ath_resolver_models import (
    Stage30_11_10AthContextRecord,
)


_MINT = "mint-live"
_VALID_ANCHOR = "2026-05-27T00:00:00Z"
_CREATED = "2026-05-27T00:05:00Z"
_BASE = {
    "candidate_id": "cand-live",
    "token_mint": _MINT,
    "pair_type": "SOL",
    "source_ref": "evt-live",
    "created_at_utc": "2026-05-27T00:00:00Z",
}


def _market(base):
    return {"present": True, "current_market_cap_usd": "12345.67"}


def _tier(base):
    return {"tier_hint": "Tier 1"}


def _confirming_migration_resolver(*, mint=_MINT, anchor=_VALID_ANCHOR):
    """The REAL Stage 30.11.8 migration resolver over a REAL Stage 30.11.9 source
    confirming ``mint`` with a trailing-Z anchor.
    """
    record = build_evidence_record_from_sanitized_projection(
        token_mint=mint,
        measurement_status="COMPLETE",
        migration_event_time_utc=anchor,
        warnings=(),
        redaction_status="SAFE",
        source_ref="mig-ref",
    )

    def provider(token_mint):
        return [record] if token_mint == mint else []

    return build_migration_resolver(build_migration_evidence_source(provider))


class _DictAthSource:
    def __init__(self, mapping):
        self._mapping = mapping

    def read_ath_context(self, token_mint, *, migration_event_time_utc):
        return self._mapping.get(token_mint)


class _RaisingAthSource:
    def read_ath_context(self, token_mint, *, migration_event_time_utc):
        raise RuntimeError("ath source blew up")


def _reading(
    *,
    token_mint=_MINT,
    ath_status="PRESENT",
    ath_since="POST_MIGRATION_ONLY",
    drawdown_basis="FROM_POST_MIGRATION_ATH",
    drawdown_from_ath="0.55",
    ath_source="ath-src",
):
    return Stage30_11_10AthContextRecord(
        token_mint=token_mint,
        ath_status=ath_status,
        ath_since_migration_status=ath_since,
        drawdown_basis=drawdown_basis,
        drawdown_from_ath=drawdown_from_ath,
        ath_source=ath_source,
    )


def _enrich(ath_source, *, migration_resolver=None, base=None):
    """Enrich the base through the committed Stage 30.11.7 adapter, with the SAME
    confirmed Stage 30.11.8 migration resolver driving both the MIGRATION dimension and
    the Stage 30.11.10 ATH resolver's anchor, and the given ATH source.
    """
    if migration_resolver is None:
        migration_resolver = _confirming_migration_resolver()
    ath_resolver = build_ath_resolver(
        migration_resolver=migration_resolver, ath_context_source=ath_source
    )
    return enrich_harvested_candidate(
        _BASE if base is None else base,
        market_context_resolver=_market,
        tier_resolver=_tier,
        migration_resolver=migration_resolver,
        ath_resolver=ath_resolver,
        created_at_utc=_CREATED,
    )


# ---------------------------------------------------------------------------
# 1. Confirmed migration + resolved ATH clears MIGRATION and ATH (audit #2)
# ---------------------------------------------------------------------------


def test_confirmed_migration_plus_resolved_ath_enriches() -> None:
    result = _enrich(_DictAthSource({_MINT: _reading()}))
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enrichment_reason == ENRICH_REASON_READY_FOR_LIVE_RUNNER
    assert result.enriched_candidate is not None
    cand = result.enriched_candidate
    assert cand.token_mint == _MINT
    assert cand.migration_status == STAGE30_11_7_CONTEXT_STATUS_PRESENT
    assert cand.ath_status == STAGE30_11_7_CONTEXT_STATUS_PRESENT
    assert cand.post_migration_ath_verified is True
    # The committed drawdown survives the bridge (coerced to a finite Decimal by the
    # committed Stage 30.11.7 enrichment).
    assert str(cand.drawdown_from_ath) == "0.55"


# ---------------------------------------------------------------------------
# 2. Missing ATH (source returns None) still fails closed at ATH (audit #3)
# ---------------------------------------------------------------------------


def test_confirmed_migration_but_missing_ath_blocks_transport() -> None:
    result = _enrich(_DictAthSource({}))  # no reading for the mint
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH
    assert result.enriched_candidate is None


# ---------------------------------------------------------------------------
# 3. Stale / source-error / cross-mint ATH fail closed at ATH (audit #4, #8, #9)
# ---------------------------------------------------------------------------


def test_stale_ath_fails_closed_at_ath() -> None:
    result = _enrich(_DictAthSource({_MINT: _reading(ath_status="STALE")}))
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    # Stage 27.4 collapses staleness into a non-PRESENT status, so present=False ->
    # the committed adapter rejects at MISSING_ATH.
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH


def test_source_error_ath_fails_closed_at_ath() -> None:
    result = _enrich(_RaisingAthSource())
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH


def test_cross_mint_ath_is_not_returned_for_another_mint() -> None:
    # The source holds a fully-resolvable reading, but bound to a DIFFERENT mint -> the
    # resolver refuses to inherit it, so the candidate fails closed at ATH.
    source = _DictAthSource({_MINT: _reading(token_mint="mint-other")})
    result = _enrich(source)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH


# ---------------------------------------------------------------------------
# 4. Pre-migration ATH fails closed at PRE_MIGRATION_ATH_NOT_VERIFIED (audit #5)
# ---------------------------------------------------------------------------


def test_pre_migration_ath_fails_closed_pre_migration() -> None:
    # A present ATH whose drawdown basis is not FROM_POST_MIGRATION_ATH (a realistic
    # pre-migration reading: MAY_INCLUDE_PRE_MIGRATION + NOT_APPLICABLE basis).
    source = _DictAthSource(
        {
            _MINT: _reading(
                ath_since="MAY_INCLUDE_PRE_MIGRATION",
                drawdown_basis="NOT_APPLICABLE",
                drawdown_from_ath=None,
            )
        }
    )
    result = _enrich(source)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == (
        ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED
    )


# ---------------------------------------------------------------------------
# 4b. Inconsistent / missing post-migration window status fails closed at
#     PRE_MIGRATION_ATH_NOT_VERIFIED -- no ENRICHED_DIP_CANDIDATE reaches transport
#     (Codex Stage 30.11.10 patch: a duck-typed reading can carry a post-migration
#     basis without the POST_MIGRATION_ONLY window; the bridge must NOT trust it).
# ---------------------------------------------------------------------------


def test_inconsistent_post_migration_fields_reject_pre_migration() -> None:
    # Codex repro EXACTLY: ath_status=PRESENT, ath_since=MAY_INCLUDE_PRE_MIGRATION,
    # drawdown_basis=FROM_POST_MIGRATION_ATH, drawdown=finite. The Stage 30.11.10 bridge
    # must NOT set post_migration_ath_verified, so the committed Stage 30.11.7 enrichment
    # rejects at PRE_MIGRATION_ATH_NOT_VERIFIED and produces NO enriched candidate.
    source = _DictAthSource(
        {
            _MINT: _reading(
                ath_since="MAY_INCLUDE_PRE_MIGRATION",
                drawdown_basis="FROM_POST_MIGRATION_ATH",
                drawdown_from_ath="0.55",
            )
        }
    )
    result = _enrich(source)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == (
        ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED
    )
    assert result.enriched_candidate is None


def test_missing_window_status_rejects_pre_migration() -> None:
    # ath_since_migration_status missing (None) -- with an otherwise-perfect
    # FROM_POST_MIGRATION_ATH basis + finite drawdown -- still fails closed: the bridge
    # requires the window status outright, so Stage 30.11.7 rejects at PRE_MIGRATION.
    source = _DictAthSource(
        {
            _MINT: _reading(
                ath_since=None,
                drawdown_basis="FROM_POST_MIGRATION_ATH",
                drawdown_from_ath="0.55",
            )
        }
    )
    result = _enrich(source)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == (
        ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED
    )
    assert result.enriched_candidate is None


def test_honest_post_migration_only_output_still_enriches() -> None:
    # The HONEST Stage 27.4 shape (POST_MIGRATION_ONLY + FROM_POST_MIGRATION_ATH +
    # finite drawdown) still clears the ATH dimension end to end -> ENRICHED /
    # READY_FOR_LIVE_RUNNER with post_migration_ath_verified True.
    source = _DictAthSource(
        {
            _MINT: _reading(
                ath_since="POST_MIGRATION_ONLY",
                drawdown_basis="FROM_POST_MIGRATION_ATH",
                drawdown_from_ath="0.55",
            )
        }
    )
    result = _enrich(source)
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enrichment_reason == ENRICH_REASON_READY_FOR_LIVE_RUNNER
    assert result.enriched_candidate is not None
    assert result.enriched_candidate.post_migration_ath_verified is True
    assert str(result.enriched_candidate.drawdown_from_ath) == "0.55"


# ---------------------------------------------------------------------------
# 5. Missing / invalid drawdown fails closed at INVALID_DRAWDOWN (audit #6, #7)
# ---------------------------------------------------------------------------


def test_missing_drawdown_fails_closed_invalid_drawdown() -> None:
    source = _DictAthSource({_MINT: _reading(drawdown_from_ath=None)})
    result = _enrich(source)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enrichment_reason == ENRICH_REASON_INVALID_DRAWDOWN


def test_invalid_drawdown_values_fail_closed_invalid_drawdown() -> None:
    # The resolver carries the committed drawdown VERBATIM; the committed Stage 30.11.7
    # enrichment coerces it and rejects every non-finite / non-numeric magnitude.
    for bad in ("NaN", "Infinity", float("inf"), float("nan"), 3.5, True, "garbage"):
        source = _DictAthSource({_MINT: _reading(drawdown_from_ath=bad)})
        result = _enrich(source)
        assert result.enrichment_decision == ENRICH_DECISION_REJECTED, bad
        assert result.rejected_dimension == ENRICH_DIMENSION_ATH, bad
        assert result.enrichment_reason == ENRICH_REASON_INVALID_DRAWDOWN, bad


# ---------------------------------------------------------------------------
# 6. Full real-data migration path (audit #11): 30.11.9 -> 30.11.8 -> 30.11.10 -> 30.11.7
# ---------------------------------------------------------------------------


def test_real_migration_path_resolved_ath_enriches_and_missing_ath_rejects() -> None:
    migration_resolver = _confirming_migration_resolver()

    # Resolved ATH -> ENRICHED.
    enriched = _enrich(
        _DictAthSource({_MINT: _reading()}), migration_resolver=migration_resolver
    )
    assert enriched.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert enriched.enriched_candidate is not None

    # The missing-ATH variant over the SAME confirmed migration still rejects at ATH.
    rejected = _enrich(
        _DictAthSource({}), migration_resolver=migration_resolver
    )
    assert rejected.enrichment_decision == ENRICH_DECISION_REJECTED
    assert rejected.rejected_dimension == ENRICH_DIMENSION_ATH
    assert rejected.enrichment_reason == ENRICH_REASON_MISSING_ATH


def test_unconfirmed_migration_fails_before_ath_resolver_reads_a_thing() -> None:
    # An empty Stage 30.11.9 source -> Stage 30.11.8 reports UNCONFIRMED -> the MIGRATION
    # dimension fails closed BEFORE the ATH dimension (so even a perfect ATH never helps).
    empty_resolver = build_migration_resolver(
        build_migration_evidence_source(lambda mint: [])
    )
    result = _enrich(
        _DictAthSource({_MINT: _reading()}), migration_resolver=empty_resolver
    )
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    # The MIGRATION dimension (not ATH) is the one that fails.
    assert result.rejected_dimension != ENRICH_DIMENSION_ATH


# ---------------------------------------------------------------------------
# 7. GOLD STANDARD: the real committed Stage 27.4 read_ath_context maps through
# ---------------------------------------------------------------------------


def _real_stage_27_4_post_migration_record():
    """Drive the REAL committed Stage 27.4 ``read_ath_context`` (the committed drawdown
    brain) with its own injectable fakes to produce a real ``AthContextRecord`` whose
    ``drawdown_basis`` is ``FROM_POST_MIGRATION_ATH`` and whose drawdown is computed
    (100 - 40 = 60) -- exactly what the committed Stage 29.2 Birdeye ATH + current-price
    sources would feed at the live ceremony.
    """
    from PHX2.stage27 import price_ath_context_models as m27
    from PHX2.stage27 import price_ath_context_reader as reader
    from PHX2.stage27.pair_detection_constants import (
        BONDING_CURVE_VERSION_SOL_LEGACY,
        CALIBRATION_LANE_EXISTING_SOL_LANE,
        KNOWN_WRAPPED_SOL_MINT,
        LIVE_POLICY_LIVE_ALLOWED,
        PAIR_DETECTION_CONFIDENCE_HIGH,
        PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
        PAIR_DETECTION_STATUS_CONFIRMED,
        PAIR_TYPE_PUMP_SOL,
        QUOTE_ASSET_SOL,
    )
    from PHX2.stage27.provider_ingest_models import (
        COMPOSITION_REASON_OK,
        COMPOSITION_STATUS_COMPOSED,
        EVENT_KIND_SWAP,
        ProviderIngestOutputRecord,
        STAGE27_3_SCHEMA_VERSION,
    )

    ingest = ProviderIngestOutputRecord(
        provider_id="p",
        provider_event_id="pe",
        normalized_event_id="ne",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=_MINT,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        pair_quote_asset=QUOTE_ASSET_SOL,
        pair_pair_type=PAIR_TYPE_PUMP_SOL,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_SOL_LEGACY,
        pair_detection_status=PAIR_DETECTION_STATUS_CONFIRMED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
        pair_detection_reason=PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
        pair_live_policy=LIVE_POLICY_LIVE_ALLOWED,
        pair_calibration_lane=CALIBRATION_LANE_EXISTING_SOL_LANE,
        raw_capture_ref="r",
        source_summary="s",
        composition_status=COMPOSITION_STATUS_COMPOSED,
        composition_reason=COMPOSITION_REASON_OK,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )

    class _AthSnapshotSource:
        def read_ath_snapshot(self, token_mint, *, pair_quote_asset):
            return reader.AthSourceSnapshot(
                ath_value="100",
                ath_unit=m27.ATH_UNIT_USD,
                source_label="ath-src",
                ath_observed_at_utc="2026-05-22T11:00:00+00:00",
                window_starts_post_migration=True,
            )

    class _PresentMigration:
        # build_ath_context_record reads only ``.migration_status``.
        migration_status = "PRESENT"

    price = m27.PriceContextRecord(
        token_mint=_MINT,
        pair_type=PAIR_TYPE_PUMP_SOL,
        quote_asset=QUOTE_ASSET_SOL,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        price_value="40",
        price_unit=m27.PRICE_UNIT_USD,
        price_source="ath-src",
        fetched_at_utc="2026-05-22T11:59:50+00:00",
        observed_at_utc="2026-05-22T12:00:30+00:00",
        staleness_seconds=40,
        price_status=m27.PRICE_STATUS_PRESENT,
        price_reason=m27.PRICE_REASON_OK,
        schema_version=m27.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )
    return reader.read_ath_context(
        _AthSnapshotSource(),
        ingest,
        migration_record=_PresentMigration(),
        current_price_record=price,
    )


def test_real_stage_27_4_record_resolves_and_enriches() -> None:
    real_record = _real_stage_27_4_post_migration_record()
    # The committed brain produced a post-migration ATH with a computed drawdown.
    assert real_record.ath_status == "PRESENT"
    assert real_record.drawdown_basis == "FROM_POST_MIGRATION_ATH"
    assert real_record.drawdown_from_ath == "60"

    # The Stage 30.11.10 resolver reads the REAL record duck-typed and resolves it; the
    # committed Stage 30.11.7 enrichment then clears the ATH dimension end to end.
    result = _enrich(_DictAthSource({_MINT: real_record}))
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enriched_candidate is not None
    assert result.enriched_candidate.post_migration_ath_verified is True
    assert str(result.enriched_candidate.drawdown_from_ath) == "60"
