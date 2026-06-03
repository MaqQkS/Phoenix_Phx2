"""Stage 30.11.7 candidate dip-enrichment adapter tests.

Proves the Stage 30.11.7 enrichment adapter:

  * HAPPY PATH -- a harvested base + good injected resolvers enrich into a valid
    Stage 30.11.5-shaped flat enriched candidate that passes the committed Stage
    30.11.5 assembler + Stage 30.11.1 bridge + Stage 30.10.1 dip gate (-> ELIGIBLE);
  * FAIL CLOSED, per dimension -- a missing / unavailable market context, a
    malformed / non-positive cap, a missing tier, a missing / UNKNOWN migration, and
    a missing / stale / pre-migration / malformed-drawdown ATH each fail closed to
    the correct reason + dimension, carry NO enriched candidate, and (via the
    committed gate) reach NO dip;
  * NON-DIP -- a present-but-non-dip tier (``Tier Unknown``) enriches cleanly yet the
    committed dip gate suppresses it (the gate decides eligibility, not the
    enrichment);
  * NO FABRICATION -- a ``None`` / raising resolver fails closed (never a PRESENT
    default); each context status is ``PRESENT`` ONLY when the resolver confirmed it;
  * BOUNDED -- the bounded helper fails closed on an out-of-cap budget and stops at
    the cap, with a correct rolled-up summary.

Pure / offline. No live call, no provider, no Discord, no env read. The committed
surfaces are imported by this TEST (a test file is not boundary-scanned); the Stage
30.11.7 PRODUCTION adapter imports only its own models sibling.
"""

from __future__ import annotations

from decimal import Decimal

from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
    Stage30_11_7CandidateEnrichmentError,
    enrich_candidate_source,
    enrich_harvested_candidate,
    is_within_enrich_cap,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    ENRICH_DECISION_REJECTED,
    ENRICH_DIMENSION_ATH,
    ENRICH_DIMENSION_MARKET_CONTEXT,
    ENRICH_DIMENSION_MIGRATION,
    ENRICH_DIMENSION_TIER,
    ENRICH_REASON_INVALID_DRAWDOWN,
    ENRICH_REASON_INVALID_MARKET_CAP,
    ENRICH_REASON_MISSING_ATH,
    ENRICH_REASON_MISSING_MARKET_CONTEXT,
    ENRICH_REASON_MISSING_MIGRATION_EVIDENCE,
    ENRICH_REASON_MISSING_TIER,
    ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ENRICH_REASON_READY_FOR_LIVE_RUNNER,
    ENRICH_REASON_STALE_ATH,
    ENRICH_REASON_UNCONFIRMED_MIGRATION,
    Stage30_11_7AthResolution,
    Stage30_11_7MarketContextResolution,
    Stage30_11_7MigrationResolution,
    Stage30_11_7TierResolution,
)


_CREATED_AT = "2026-01-01T00:00:00Z"


def _base(**overrides):
    base = {
        "candidate_id": "cand-x",
        "token_mint": "mint-x",
        "pair_type": "SOL",
        "source_ref": "ref-x",
        "created_at_utc": _CREATED_AT,
    }
    base.update(overrides)
    return base


# ---- Good resolvers (a usable signal for every dimension) ----


def _good_mc(base):
    return Stage30_11_7MarketContextResolution(
        present=True, current_market_cap_usd="12345.67", source_ref="mc"
    )


def _good_tier(base, *, tier="Tier 1"):
    return Stage30_11_7TierResolution(tier_hint=tier)


def _good_mig(base):
    return Stage30_11_7MigrationResolution(confirmed=True, source_ref="mig")


def _good_ath(base):
    return Stage30_11_7AthResolution(
        present=True,
        fresh=True,
        post_migration_ath_verified=True,
        drawdown_from_ath="0.55",
        source_ref="ath",
    )


def _enrich(base, *, mc=_good_mc, tier=_good_tier, mig=_good_mig, ath=_good_ath):
    return enrich_harvested_candidate(
        base,
        market_context_resolver=mc,
        tier_resolver=tier,
        migration_resolver=mig,
        ath_resolver=ath,
        created_at_utc=_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# 1. Happy path -> ENRICHED + passes the committed projection / bridge / dip gate
# ---------------------------------------------------------------------------


def test_happy_path_enriches_a_dip_candidate() -> None:
    result = _enrich(_base())
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enrichment_reason == ENRICH_REASON_READY_FOR_LIVE_RUNNER
    assert result.rejected_dimension == ""
    c = result.enriched_candidate
    assert c is not None
    # Identity carried verbatim from the base.
    assert c.candidate_id == "cand-x"
    assert c.token_mint == "mint-x"
    assert c.pair_type == "SOL"
    assert c.source_ref == "ref-x"
    assert c.created_at_utc == _CREATED_AT
    # Tier carried VERBATIM (no parallel tier model).
    assert c.tier_hint == "Tier 1"
    # Confirmed verdicts mapped to the gate's PRESENT token.
    assert c.migration_status == "PRESENT"
    assert c.ath_status == "PRESENT"
    assert c.market_context_status == "PRESENT"
    assert c.post_migration_ath_verified is True
    # Magnitudes are finite Decimals (cap strictly positive).
    assert c.current_market_cap_usd == Decimal("12345.67")
    assert c.drawdown_from_ath == Decimal("0.55")
    assert isinstance(c.current_market_cap_usd, Decimal)
    assert isinstance(c.drawdown_from_ath, Decimal)


def test_enriched_candidate_passes_committed_assembler_bridge_and_gate() -> None:
    from PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier import (
        classify_tier_dip_eligibility,
    )
    from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
        DECISION_ELIGIBLE_DIP,
        Stage30_10DipEligibilityInput,
    )
    from PHX2.stage30.stage30_11_1_live_candidate_bridge import (
        build_stage30_9_3_live_gate_input_from_candidate,
    )
    from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
        BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    )
    from PHX2.stage30.stage30_11_5_live_candidate_snapshot_assembler import (
        assemble_stage30_11_5_live_candidate_snapshot,
    )
    from PHX2.stage30.stage30_11_5_live_wiring_models import (
        ASSEMBLY_DECISION_ASSEMBLED,
    )

    c = _enrich(_base()).enriched_candidate
    assert c is not None

    # Projection / assembly acceptance.
    assembly = assemble_stage30_11_5_live_candidate_snapshot(
        c, created_at_utc=_CREATED_AT
    )
    assert assembly.assembly_decision == ASSEMBLY_DECISION_ASSEMBLED
    assert assembly.snapshot is not None

    # Bridge acceptance.
    bridge = build_stage30_9_3_live_gate_input_from_candidate(
        assembly.snapshot, created_at_utc=_CREATED_AT
    )
    assert bridge.bridge_decision == BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    assert bridge.live_gate_input is not None

    # Dip-gate acceptance (the committed Stage 30.10.1 classifier).
    gate_input = Stage30_10DipEligibilityInput(
        candidate_id=c.candidate_id,
        token_mint=c.token_mint,
        tier_token=c.tier_hint,
        drawdown_from_ath=c.drawdown_from_ath,
        migration_status=c.migration_status,
        ath_status=c.ath_status,
        market_context_status=c.market_context_status,
        current_market_cap_usd=c.current_market_cap_usd,
        post_migration_ath_verified=c.post_migration_ath_verified,
        created_at_utc=c.created_at_utc,
    )
    verdict = classify_tier_dip_eligibility(gate_input)
    assert verdict.decision == DECISION_ELIGIBLE_DIP
    assert verdict.send_allowed is True


# ---------------------------------------------------------------------------
# 2. Missing / invalid market context -> fail closed (MARKET_CONTEXT)
# ---------------------------------------------------------------------------


def test_missing_market_context_fails_closed() -> None:
    result = _enrich(_base(), mc=lambda base: None)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_MISSING_MARKET_CONTEXT
    assert result.rejected_dimension == ENRICH_DIMENSION_MARKET_CONTEXT
    assert result.enriched_candidate is None
    # Identity is still echoed on the reject.
    assert result.candidate_id == "cand-x"
    assert result.token_mint == "mint-x"


def test_market_context_not_present_fails_closed() -> None:
    mc = lambda base: Stage30_11_7MarketContextResolution(
        present=False, current_market_cap_usd="123"
    )
    result = _enrich(_base(), mc=mc)
    assert result.enrichment_reason == ENRICH_REASON_MISSING_MARKET_CONTEXT
    assert result.enriched_candidate is None


def test_invalid_or_nonpositive_market_cap_fails_closed() -> None:
    for bad_cap in ("abc", "0", "-5", "NaN", "Infinity", None, True):
        mc = lambda base, _c=bad_cap: Stage30_11_7MarketContextResolution(
            present=True, current_market_cap_usd=_c
        )
        result = _enrich(_base(), mc=mc)
        assert result.enrichment_decision == ENRICH_DECISION_REJECTED, bad_cap
        assert result.enrichment_reason == ENRICH_REASON_INVALID_MARKET_CAP, (
            bad_cap
        )
        assert result.rejected_dimension == ENRICH_DIMENSION_MARKET_CONTEXT
        assert result.enriched_candidate is None


# ---------------------------------------------------------------------------
# 3. Missing tier -> fail closed (TIER)
# ---------------------------------------------------------------------------


def test_missing_tier_fails_closed() -> None:
    for bad_tier in (None, "", "   ", 5):
        tier = lambda base, _t=bad_tier: Stage30_11_7TierResolution(
            tier_hint=_t
        )
        result = _enrich(_base(), tier=tier)
        assert result.enrichment_decision == ENRICH_DECISION_REJECTED, bad_tier
        assert result.enrichment_reason == ENRICH_REASON_MISSING_TIER
        assert result.rejected_dimension == ENRICH_DIMENSION_TIER
        assert result.enriched_candidate is None


def test_none_tier_resolution_fails_closed() -> None:
    result = _enrich(_base(), tier=lambda base: None)
    assert result.enrichment_reason == ENRICH_REASON_MISSING_TIER
    assert result.enriched_candidate is None


# ---------------------------------------------------------------------------
# 4. Missing / UNKNOWN migration -> fail closed (MIGRATION)
# ---------------------------------------------------------------------------


def test_missing_migration_evidence_fails_closed() -> None:
    result = _enrich(_base(), mig=lambda base: None)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_MISSING_MIGRATION_EVIDENCE
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
    assert result.enriched_candidate is None


def test_unknown_unconfirmed_migration_fails_closed() -> None:
    # An UNKNOWN / unconfirmed migration verdict can NEVER become eligible.
    for verdict in (False, None, 0, "PRESENT"):
        mig = lambda base, _v=verdict: Stage30_11_7MigrationResolution(
            confirmed=_v
        )
        result = _enrich(_base(), mig=mig)
        assert result.enrichment_decision == ENRICH_DECISION_REJECTED, verdict
        assert result.enrichment_reason == ENRICH_REASON_UNCONFIRMED_MIGRATION
        assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
        assert result.enriched_candidate is None


# ---------------------------------------------------------------------------
# 5. Missing / stale / pre-migration / invalid-drawdown ATH -> fail closed (ATH)
# ---------------------------------------------------------------------------


def test_missing_ath_fails_closed() -> None:
    assert (
        _enrich(_base(), ath=lambda base: None).enrichment_reason
        == ENRICH_REASON_MISSING_ATH
    )
    ath = lambda base: Stage30_11_7AthResolution(
        present=False, fresh=True, post_migration_ath_verified=True,
        drawdown_from_ath="0.5",
    )
    result = _enrich(_base(), ath=ath)
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enriched_candidate is None


def test_stale_ath_fails_closed() -> None:
    ath = lambda base: Stage30_11_7AthResolution(
        present=True, fresh=False, post_migration_ath_verified=True,
        drawdown_from_ath="0.5",
    )
    result = _enrich(_base(), ath=ath)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_STALE_ATH
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enriched_candidate is None


def test_pre_migration_ath_fails_closed() -> None:
    for flag in (False, None, "PRESENT"):
        ath = lambda base, _f=flag: Stage30_11_7AthResolution(
            present=True, fresh=True, post_migration_ath_verified=_f,
            drawdown_from_ath="0.5",
        )
        result = _enrich(_base(), ath=ath)
        assert result.enrichment_reason == (
            ENRICH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED
        ), flag
        assert result.rejected_dimension == ENRICH_DIMENSION_ATH
        assert result.enriched_candidate is None


def test_invalid_drawdown_fails_closed() -> None:
    for bad in ("abc", "NaN", "Infinity", None, True):
        ath = lambda base, _d=bad: Stage30_11_7AthResolution(
            present=True, fresh=True, post_migration_ath_verified=True,
            drawdown_from_ath=_d,
        )
        result = _enrich(_base(), ath=ath)
        assert result.enrichment_reason == ENRICH_REASON_INVALID_DRAWDOWN, bad
        assert result.rejected_dimension == ENRICH_DIMENSION_ATH
        assert result.enriched_candidate is None


def test_signed_or_zero_drawdown_is_accepted() -> None:
    # A finite signed / zero drawdown is structurally valid (the committed dip gate
    # requires only a finite Decimal); eligibility hinges on the tier.
    for ok in ("0", "-0.3", "0.0"):
        ath = lambda base, _d=ok: Stage30_11_7AthResolution(
            present=True, fresh=True, post_migration_ath_verified=True,
            drawdown_from_ath=_d,
        )
        result = _enrich(_base(), ath=ath)
        assert result.enrichment_decision == ENRICH_DECISION_ENRICHED, ok
        assert result.enriched_candidate.drawdown_from_ath == Decimal(ok)


# ---------------------------------------------------------------------------
# 6. Non-dip enriches cleanly; the committed gate (not the enrichment) suppresses
# ---------------------------------------------------------------------------


def test_non_dip_tier_enriches_but_gate_suppresses() -> None:
    from PHX2.stage30.stage30_10_1_tier_dip_eligibility_classifier import (
        classify_tier_dip_eligibility,
    )
    from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
        DECISION_SKIPPED_TIER_UNKNOWN,
        Stage30_10DipEligibilityInput,
    )

    result = _enrich(
        _base(), tier=lambda base: _good_tier(base, tier="Tier Unknown")
    )
    # The enrichment ACCEPTS the present non-dip tier (carried verbatim).
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    c = result.enriched_candidate
    assert c.tier_hint == "Tier Unknown"
    assert c.migration_status == "PRESENT"

    # The committed dip gate -- NOT the enrichment -- suppresses it.
    verdict = classify_tier_dip_eligibility(
        Stage30_10DipEligibilityInput(
            candidate_id=c.candidate_id,
            token_mint=c.token_mint,
            tier_token=c.tier_hint,
            drawdown_from_ath=c.drawdown_from_ath,
            migration_status=c.migration_status,
            ath_status=c.ath_status,
            market_context_status=c.market_context_status,
            current_market_cap_usd=c.current_market_cap_usd,
            post_migration_ath_verified=c.post_migration_ath_verified,
            created_at_utc=c.created_at_utc,
        )
    )
    assert verdict.decision == DECISION_SKIPPED_TIER_UNKNOWN
    assert verdict.send_allowed is False


# ---------------------------------------------------------------------------
# 7. No fabrication: raising resolver fails closed; precedence; duck-typed base
# ---------------------------------------------------------------------------


def test_raising_resolver_fails_closed_not_fabricated() -> None:
    def boom(base):
        raise RuntimeError("resolver blew up")

    # A raising market-context resolver fails closed to MISSING_MARKET_CONTEXT --
    # never a fabricated PRESENT default.
    result = _enrich(_base(), mc=boom)
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_MISSING_MARKET_CONTEXT
    assert result.enriched_candidate is None

    # A raising ATH resolver fails closed to MISSING_ATH.
    result = _enrich(_base(), ath=boom)
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH
    assert result.enriched_candidate is None


def test_first_failing_dimension_wins_precedence() -> None:
    # Market context is checked first: a missing MC + a missing tier names MC.
    result = _enrich(_base(), mc=lambda base: None, tier=lambda base: None)
    assert result.rejected_dimension == ENRICH_DIMENSION_MARKET_CONTEXT
    # Tier before migration.
    result = _enrich(
        _base(), tier=lambda base: None, mig=lambda base: None
    )
    assert result.rejected_dimension == ENRICH_DIMENSION_TIER
    # Migration before ATH.
    result = _enrich(
        _base(), mig=lambda base: None, ath=lambda base: None
    )
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION


def test_duck_typed_base_object_works() -> None:
    class _Obj:
        candidate_id = "cand-obj"
        token_mint = "mint-obj"
        pair_type = "SOL"
        source_ref = "ref-obj"
        created_at_utc = _CREATED_AT

    result = _enrich(_Obj())
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enriched_candidate.candidate_id == "cand-obj"
    assert result.enriched_candidate.source_ref == "ref-obj"


def test_non_string_source_ref_becomes_none() -> None:
    result = _enrich(_base(source_ref=12345))
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enriched_candidate.source_ref is None


# ---------------------------------------------------------------------------
# 8. Bounded enrichment helper: cap guard + summary + candidate_source
# ---------------------------------------------------------------------------


def test_is_within_enrich_cap() -> None:
    assert is_within_enrich_cap(1)
    assert is_within_enrich_cap(10)
    assert not is_within_enrich_cap(0)
    assert not is_within_enrich_cap(11)
    assert not is_within_enrich_cap(True)
    assert not is_within_enrich_cap("5")
    assert not is_within_enrich_cap(None)


def test_bounded_enrich_raises_on_out_of_cap_budget() -> None:
    for bad in (0, 11, True, "5", None):
        try:
            enrich_candidate_source(
                [_base()],
                market_context_resolver=_good_mc,
                tier_resolver=_good_tier,
                migration_resolver=_good_mig,
                ath_resolver=_good_ath,
                created_at_utc=_CREATED_AT,
                max_enrich=bad,
            )
        except Stage30_11_7CandidateEnrichmentError as exc:
            assert exc.reason == "INVALID_MAX_ENRICH"
        else:
            raise AssertionError(f"expected raise for max_enrich={bad!r}")


def test_bounded_enrich_summary_and_candidate_source() -> None:
    bases = [
        _base(candidate_id="a", token_mint="ma"),  # enriched
        _base(candidate_id="b", token_mint="mb"),  # enriched
    ]
    run = enrich_candidate_source(
        bases,
        market_context_resolver=_good_mc,
        tier_resolver=_good_tier,
        migration_resolver=_good_mig,
        ath_resolver=_good_ath,
        created_at_utc=_CREATED_AT,
    )
    assert run.summary.bases_seen == 2
    assert run.summary.enriched == 2
    assert len(run.candidate_source) == 2
    assert [c.candidate_id for c in run.candidate_source] == ["a", "b"]


def test_bounded_enrich_tallies_each_rejected_dimension() -> None:
    bases = [
        _base(candidate_id="ok"),  # enriched
        _base(candidate_id="no-mc"),
        _base(candidate_id="no-tier"),
        _base(candidate_id="unk-mig"),
        _base(candidate_id="stale-ath"),
    ]

    def mc(base):
        return None if base["candidate_id"] == "no-mc" else _good_mc(base)

    def tier(base):
        return None if base["candidate_id"] == "no-tier" else _good_tier(base)

    def mig(base):
        if base["candidate_id"] == "unk-mig":
            return Stage30_11_7MigrationResolution(confirmed=False)
        return _good_mig(base)

    def ath(base):
        if base["candidate_id"] == "stale-ath":
            return Stage30_11_7AthResolution(
                present=True, fresh=False,
                post_migration_ath_verified=True, drawdown_from_ath="0.5",
            )
        return _good_ath(base)

    run = enrich_candidate_source(
        bases,
        market_context_resolver=mc,
        tier_resolver=tier,
        migration_resolver=mig,
        ath_resolver=ath,
        created_at_utc=_CREATED_AT,
    )
    s = run.summary
    assert s.bases_seen == 5
    assert s.enriched == 1
    assert s.rejected_market_context == 1
    assert s.rejected_tier == 1
    assert s.rejected_migration == 1
    assert s.rejected_ath == 1
    assert len(run.candidate_source) == 1
    assert run.candidate_source[0].candidate_id == "ok"


def test_bounded_enrich_stops_at_cap() -> None:
    bases = [_base(candidate_id=f"c{i}") for i in range(10)]
    run = enrich_candidate_source(
        bases,
        market_context_resolver=_good_mc,
        tier_resolver=_good_tier,
        migration_resolver=_good_mig,
        ath_resolver=_good_ath,
        created_at_utc=_CREATED_AT,
        max_enrich=3,
    )
    assert run.summary.bases_seen == 3
    assert run.summary.enriched == 3
    assert len(run.candidate_source) == 3
