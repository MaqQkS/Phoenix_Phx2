"""Stage 30.11.8 narrow migration-confirmation adapter tests.

Proves the Stage 30.11.8 confirmation adapter:

  * CONFIRMS only real evidence -- a bound, redaction-safe, on-chain ``COMPLETE``,
    fresh, valid-ISO-8601-UTC-anchor reading for the candidate's OWN mint ->
    ``confirmed=True`` with the bound anchor + carried provenance;
  * FAILS CLOSED, with a PRECISE reason, on every blank-mint / missing / mismatched
    / unsafe / unknown / partial / no-migration / contradictory / invalid / stale /
    mis-anchored reading -- never fabricating, never inheriting another mint's
    evidence, never collapsing a contradictory / invalid reading into a silent
    unknown;
  * COMPOSES with the committed Stage 30.11.7 enrichment -- a confirmed verdict
    clears the MIGRATION dimension, an UNKNOWN verdict still fails it, and a
    confirmed verdict plus a missing ATH still fails BEFORE transport.

Pure / offline. No live call, no provider, no Discord, no env read. The committed
Stage 30.11.7 surfaces are imported by this TEST (a test file is not
boundary-scanned); the Stage 30.11.8 PRODUCTION adapter imports only its own models
sibling.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_8_migration_confirmation_adapter import (
    _is_valid_iso8601_utc,
    build_migration_resolver,
    resolve_candidate_migration,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_DECISION_CONFIRMED,
    CONFIRM_DECISION_UNCONFIRMED,
    CONFIRM_REASON_BLANK_CANDIDATE_MINT,
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
    CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE,
    CONFIRM_REASON_EVIDENCE_MINT_MISMATCH,
    CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION,
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
    CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE,
    CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE,
    CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED,
    CONFIRM_REASON_REDACTION_UNSAFE,
    CONFIRM_REASON_STALE_MIGRATION_EVIDENCE,
    CONFIRM_REASON_UNKNOWN_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE30_11_8_MIGRATION_WARNING_STALE,
    STAGE30_11_8_REDACTION_STATUS_SAFE,
    Stage30_11_8MigrationEvidence,
)


_VALID_ANCHOR = "2026-05-27T00:00:00Z"


# ---------------------------------------------------------------------------
# Local test doubles (the injected evidence source protocol)
# ---------------------------------------------------------------------------


class _DictSource:
    """A per-mint evidence source backed by an in-memory dict."""

    def __init__(self, mapping):
        self._mapping = mapping

    def lookup_migration_evidence(self, token_mint):
        return self._mapping.get(token_mint)


class _RaisingSource:
    def lookup_migration_evidence(self, token_mint):
        raise RuntimeError("source blew up")


class _NonConformingSource:
    # No callable ``lookup_migration_evidence`` attribute.
    lookup_migration_evidence = "not-callable"


def _ev(
    token_mint="mint-x",
    *,
    status=STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    anchor=_VALID_ANCHOR,
    warnings=(),
    redaction=STAGE30_11_8_REDACTION_STATUS_SAFE,
    source_ref="mig-ref",
):
    return Stage30_11_8MigrationEvidence(
        token_mint=token_mint,
        measurement_status=status,
        migration_event_time_utc=anchor,
        warnings=warnings,
        redaction_status=redaction,
        source_ref=source_ref,
    )


def _resolve(base_mint, evidence):
    """Resolve a base whose ``token_mint`` is ``base_mint`` against a source that
    binds ``base_mint`` to ``evidence`` (or holds nothing if ``evidence`` is None).
    """
    mapping = {} if evidence is None else {base_mint: evidence}
    base = {"candidate_id": "c", "token_mint": base_mint}
    return resolve_candidate_migration(base, _DictSource(mapping))


# ---------------------------------------------------------------------------
# 1. Confirmed happy path -> confirmed=True, anchor + provenance carried
# ---------------------------------------------------------------------------


def test_complete_safe_matching_mint_valid_anchor_confirms() -> None:
    res = _resolve("mint-x", _ev("mint-x"))
    assert res.confirmed is True
    assert res.decision == CONFIRM_DECISION_CONFIRMED
    assert res.reason == CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT
    assert res.token_mint == "mint-x"
    # The migration anchor + provenance are carried for the later ATH step + audit.
    assert res.migration_event_time_utc == _VALID_ANCHOR
    assert res.source_ref == "mig-ref"


def test_confirmation_rejects_offset_form_anchor() -> None:
    # Stage 30.11.8 requires a trailing UTC ``Z`` (a confirmation is a stronger claim
    # than the Stage 30.5 display-shape gate): the ``+00:00`` offset form is NOT a
    # valid migration anchor here and fails closed at the anchor check.
    res = _resolve("mint-x", _ev("mint-x", anchor="2026-05-27T00:00:00+00:00"))
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_ANCHOR


def test_confirmed_drops_non_string_source_ref() -> None:
    res = _resolve("mint-x", _ev("mint-x", source_ref=12345))
    assert res.confirmed is True
    assert res.source_ref is None


# ---------------------------------------------------------------------------
# 2. UNKNOWN / unrecognized measurement status -> unconfirmed
# ---------------------------------------------------------------------------


def test_unknown_or_unrecognized_status_is_unconfirmed() -> None:
    for status in (None, "BOGUS", "complete", 5, True):
        res = _resolve("mint-x", _ev("mint-x", status=status))
        assert res.confirmed is False, status
        assert res.decision == CONFIRM_DECISION_UNCONFIRMED
        assert res.reason == CONFIRM_REASON_UNKNOWN_MIGRATION, status
        # A fail-closed resolution carries NO anchor / provenance.
        assert res.migration_event_time_utc is None
        assert res.source_ref is None


# ---------------------------------------------------------------------------
# 3. Missing evidence (source miss / None / raising / non-conforming) -> closed
# ---------------------------------------------------------------------------


def test_missing_evidence_for_mint_is_unconfirmed() -> None:
    res = _resolve("mint-x", None)  # mint absent from the source map
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE
    assert res.token_mint == "mint-x"


def test_none_raising_or_nonconforming_source_is_unconfirmed() -> None:
    base = {"token_mint": "mint-x"}
    for source in (None, _RaisingSource(), _NonConformingSource(), object()):
        res = resolve_candidate_migration(base, source)
        assert res.confirmed is False
        assert res.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE


# ---------------------------------------------------------------------------
# 4. Conflicting evidence -> unconfirmed (CONTRADICTORY, not collapsed)
# ---------------------------------------------------------------------------


def test_conflicting_evidence_is_unconfirmed_contradictory() -> None:
    res = _resolve(
        "mint-x",
        _ev("mint-x", status=STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION),
    )
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE


# ---------------------------------------------------------------------------
# 5. Invalid / stale / mis-anchored / no-migration / partial -> unconfirmed
# ---------------------------------------------------------------------------


def test_invalid_evidence_is_unconfirmed_invalid() -> None:
    res = _resolve(
        "mint-x",
        _ev("mint-x", status=STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION),
    )
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE


def test_stale_complete_evidence_is_unconfirmed_stale() -> None:
    res = _resolve(
        "mint-x",
        _ev("mint-x", warnings=(STAGE30_11_8_MIGRATION_WARNING_STALE,)),
    )
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_STALE_MIGRATION_EVIDENCE


def test_missing_or_malformed_anchor_is_unconfirmed() -> None:
    # Structurally-invalid anchors (the pattern requires a trailing UTC ``Z``).
    for bad_anchor in (
        None,
        "",
        "   ",
        "not-a-date",
        "2026-05-27",
        "2026-05-27T00:00:00",
        "2026-05-27 00:00:00Z",
        "2026-05-27T00:00:00+05:00",
        12345,
    ):
        res = _resolve("mint-x", _ev("mint-x", anchor=bad_anchor))
        assert res.confirmed is False, bad_anchor
        assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_ANCHOR, bad_anchor


# ---------------------------------------------------------------------------
# 5b. Semantic anchor validation -- shape-valid but IMPOSSIBLE anchors fail closed
# ---------------------------------------------------------------------------
#
# Regression for the Codex finding: a regex-only shape check accepted ANY
# ``\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z`` string, so an IMPOSSIBLE instant (e.g.
# ``2026-99-99T99:99:99Z``) could become a CONFIRMED migration. The anchor check now
# ALSO validates the calendar / time semantically -- an impossible date / time fails
# closed to INVALID_MIGRATION_ANCHOR and can NEVER confirm.


# Shape-valid (matches the ISO-8601 UTC ``Z`` shape) but semantically IMPOSSIBLE.
_IMPOSSIBLE_ANCHORS = (
    "2026-99-99T99:99:99Z",  # the Codex counterexample
    "2026-13-01T00:00:00Z",  # month 13
    "2026-00-01T00:00:00Z",  # month 00
    "2026-01-32T00:00:00Z",  # day 32
    "2026-02-30T00:00:00Z",  # Feb 30 (never a real day)
    "2026-01-01T24:00:00Z",  # hour 24
    "2026-01-01T23:60:00Z",  # minute 60
    "2026-01-01T23:59:60Z",  # second 60 (leap second rejected)
    "2027-02-29T12:34:56Z",  # Feb 29 in a NON-leap year
)


# Wrong shape / non-UTC (no trailing ``Z``, naive, whitespace-padded, single-digit).
_WRONG_SHAPE_ANCHORS = (
    "2026-01-01T00:00:00+00:00",  # +00:00 offset form (UTC Z only here)
    "2026-01-01T00:00:00",  # naive (no zone)
    " 2026-01-01T00:00:00Z ",  # whitespace-padded
    "2026-1-1T00:00:00Z",  # single-digit month / day
)


# Strict-shape AND semantically valid -- these still confirm.
_VALID_ANCHORS = (
    "2026-01-01T00:00:00Z",
    "2028-02-29T12:34:56Z",  # Feb 29 in a leap year
)


def test_impossible_utc_shaped_anchor_fails_closed() -> None:
    for anchor in _IMPOSSIBLE_ANCHORS:
        res = _resolve("mint-x", _ev("mint-x", anchor=anchor))
        assert res.confirmed is False, anchor
        assert res.decision == CONFIRM_DECISION_UNCONFIRMED, anchor
        assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_ANCHOR, anchor
        # A fail-closed resolution carries NO anchor / provenance.
        assert res.migration_event_time_utc is None, anchor
        assert res.source_ref is None, anchor


def test_wrong_shape_or_non_utc_anchor_fails_closed() -> None:
    for anchor in _WRONG_SHAPE_ANCHORS:
        res = _resolve("mint-x", _ev("mint-x", anchor=anchor))
        assert res.confirmed is False, anchor
        assert res.reason == CONFIRM_REASON_INVALID_MIGRATION_ANCHOR, anchor


def test_valid_utc_anchors_still_confirm() -> None:
    for anchor in _VALID_ANCHORS:
        res = _resolve("mint-x", _ev("mint-x", anchor=anchor))
        assert res.confirmed is True, anchor
        assert res.reason == CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT, anchor
        # The valid anchor is carried verbatim for the later ATH / drawdown step.
        assert res.migration_event_time_utc == anchor, anchor


def test_is_valid_iso8601_utc_helper_semantics() -> None:
    # Direct coverage of the anchor validator: shape + calendar semantics, total /
    # fail-closed (never raises on a non-string / empty / padded input).
    for anchor in _VALID_ANCHORS:
        assert _is_valid_iso8601_utc(anchor) is True, anchor
    for anchor in _IMPOSSIBLE_ANCHORS + _WRONG_SHAPE_ANCHORS:
        assert _is_valid_iso8601_utc(anchor) is False, anchor
    for bad in (None, 12345, "", "   ", b"2026-01-01T00:00:00Z"):
        assert _is_valid_iso8601_utc(bad) is False, bad


def test_evidence_reports_no_migration_is_unconfirmed() -> None:
    res = _resolve(
        "mint-x",
        _ev("mint-x", status=STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION),
    )
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_EVIDENCE_REPORTS_NO_MIGRATION


def test_partial_evidence_is_unconfirmed_partial() -> None:
    res = _resolve(
        "mint-x",
        _ev(
            "mint-x",
            status=STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        ),
    )
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_PARTIAL_MIGRATION_UNVERIFIED


# ---------------------------------------------------------------------------
# 6. Unsafe / missing redaction -> unconfirmed (redaction dominates)
# ---------------------------------------------------------------------------


def test_unsafe_or_missing_redaction_is_unconfirmed() -> None:
    for redaction in (None, "", "REDACTED", "safe", "UNSAFE"):
        res = _resolve("mint-x", _ev("mint-x", redaction=redaction))
        assert res.confirmed is False, redaction
        assert res.reason == CONFIRM_REASON_REDACTION_UNSAFE, redaction


# ---------------------------------------------------------------------------
# 7. Candidate identity safety -- no cross-mint inheritance
# ---------------------------------------------------------------------------


def test_wrong_mint_does_not_inherit_another_mints_evidence() -> None:
    # The source holds CONFIRMED evidence bound to mint-a only.
    source = _DictSource({"mint-a": _ev("mint-a")})

    # mint-a confirms.
    res_a = resolve_candidate_migration({"token_mint": "mint-a"}, source)
    assert res_a.confirmed is True

    # mint-b has no evidence in the source -> MISSING (never inherits a's).
    res_b = resolve_candidate_migration({"token_mint": "mint-b"}, source)
    assert res_b.confirmed is False
    assert res_b.reason == CONFIRM_REASON_MISSING_MIGRATION_EVIDENCE


def test_evidence_bound_to_a_different_mint_is_mismatch() -> None:
    # A source hands mint-b an evidence object whose own token_mint is mint-a.
    source = _DictSource({"mint-b": _ev("mint-a")})
    res = resolve_candidate_migration({"token_mint": "mint-b"}, source)
    assert res.confirmed is False
    assert res.reason == CONFIRM_REASON_EVIDENCE_MINT_MISMATCH
    assert res.token_mint == "mint-b"


def test_blank_evidence_mint_is_mismatch() -> None:
    for ev_mint in (None, "", "   "):
        source = _DictSource({"mint-b": _ev(ev_mint)})
        res = resolve_candidate_migration({"token_mint": "mint-b"}, source)
        assert res.confirmed is False, ev_mint
        assert res.reason == CONFIRM_REASON_EVIDENCE_MINT_MISMATCH


# ---------------------------------------------------------------------------
# 8. Blank / missing base mint -> fail closed BEFORE any lookup
# ---------------------------------------------------------------------------


def test_blank_or_missing_base_mint_fails_closed() -> None:
    confirmed_source = _DictSource({"mint-x": _ev("mint-x")})
    for base in (
        {"token_mint": None},
        {"token_mint": ""},
        {"token_mint": "   "},
        {"token_mint": 12345},
        {},  # no token_mint key at all
    ):
        res = resolve_candidate_migration(base, confirmed_source)
        assert res.confirmed is False, base
        assert res.reason == CONFIRM_REASON_BLANK_CANDIDATE_MINT, base
        assert res.token_mint == ""


# ---------------------------------------------------------------------------
# 9. Precision: contradictory / invalid / unknown stay DISTINCT
# ---------------------------------------------------------------------------


def test_contradictory_invalid_unknown_are_distinct_reasons() -> None:
    reasons = {
        _resolve(
            "m",
            _ev(
                "m",
                status=STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
            ),
        ).reason,
        _resolve(
            "m",
            _ev("m", status=STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION),
        ).reason,
        _resolve("m", _ev("m", status="BOGUS")).reason,
    }
    assert reasons == {
        CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE,
        CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE,
        CONFIRM_REASON_UNKNOWN_MIGRATION,
    }


# ---------------------------------------------------------------------------
# 10. build_migration_resolver: a duck-typed Stage 30.11.7 migration resolver
# ---------------------------------------------------------------------------


def test_build_migration_resolver_returns_callable_keyed_by_base_mint() -> None:
    source = _DictSource({"mint-x": _ev("mint-x")})
    resolver = build_migration_resolver(source)
    assert callable(resolver)
    assert resolver({"token_mint": "mint-x"}).confirmed is True
    assert resolver({"token_mint": "mint-y"}).confirmed is False


def test_duck_typed_object_base_works() -> None:
    class _Obj:
        token_mint = "mint-x"

    source = _DictSource({"mint-x": _ev("mint-x")})
    res = resolve_candidate_migration(_Obj(), source)
    assert res.confirmed is True
    assert res.token_mint == "mint-x"


# ---------------------------------------------------------------------------
# 11. Composition with the committed Stage 30.11.7 enrichment
# ---------------------------------------------------------------------------


def _stage_30_11_7_good_resolvers():
    from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
        Stage30_11_7AthResolution,
        Stage30_11_7MarketContextResolution,
        Stage30_11_7TierResolution,
    )

    mc = lambda base: Stage30_11_7MarketContextResolution(
        present=True, current_market_cap_usd="12345.67"
    )
    tier = lambda base: Stage30_11_7TierResolution(tier_hint="Tier 1")
    ath = lambda base: Stage30_11_7AthResolution(
        present=True,
        fresh=True,
        post_migration_ath_verified=True,
        drawdown_from_ath="0.55",
    )
    return mc, tier, ath


def test_confirmed_migration_clears_stage_30_11_7_migration_dimension() -> None:
    from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
        enrich_harvested_candidate,
    )
    from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
        ENRICH_DECISION_ENRICHED,
        ENRICH_REASON_READY_FOR_LIVE_RUNNER,
        STAGE30_11_7_CONTEXT_STATUS_PRESENT,
    )

    mc, tier, ath = _stage_30_11_7_good_resolvers()
    migration_resolver = build_migration_resolver(
        _DictSource({"mint-confirmed": _ev("mint-confirmed")})
    )
    base = {
        "candidate_id": "cand-dip",
        "token_mint": "mint-confirmed",
        "pair_type": "SOL",
        "created_at_utc": "2026-01-01T00:00:00Z",
    }
    result = enrich_harvested_candidate(
        base,
        market_context_resolver=mc,
        tier_resolver=tier,
        migration_resolver=migration_resolver,
        ath_resolver=ath,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    # The MIGRATION dimension now CLEARS: the candidate enriches.
    assert result.enrichment_decision == ENRICH_DECISION_ENRICHED
    assert result.enrichment_reason == ENRICH_REASON_READY_FOR_LIVE_RUNNER
    assert result.enriched_candidate is not None
    assert result.enriched_candidate.migration_status == (
        STAGE30_11_7_CONTEXT_STATUS_PRESENT
    )


def test_unknown_migration_still_fails_stage_30_11_7_migration_dimension() -> None:
    from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
        enrich_harvested_candidate,
    )
    from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
        ENRICH_DECISION_REJECTED,
        ENRICH_DIMENSION_MIGRATION,
        ENRICH_REASON_UNCONFIRMED_MIGRATION,
    )

    mc, tier, ath = _stage_30_11_7_good_resolvers()
    # The source has only an UNKNOWN-status reading for the mint.
    migration_resolver = build_migration_resolver(
        _DictSource({"mint-unknown": _ev("mint-unknown", status=None)})
    )
    base = {
        "candidate_id": "cand-unk",
        "token_mint": "mint-unknown",
        "pair_type": "SOL",
        "created_at_utc": "2026-01-01T00:00:00Z",
    }
    result = enrich_harvested_candidate(
        base,
        market_context_resolver=mc,
        tier_resolver=tier,
        migration_resolver=migration_resolver,
        ath_resolver=ath,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    # The MIGRATION dimension still FAILS CLOSED.
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_UNCONFIRMED_MIGRATION
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
    assert result.enriched_candidate is None


def test_confirmed_migration_plus_missing_ath_still_fails_before_transport() -> None:
    from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
        enrich_harvested_candidate,
    )
    from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
        ENRICH_DECISION_REJECTED,
        ENRICH_DIMENSION_ATH,
        ENRICH_REASON_MISSING_ATH,
    )

    mc, tier, _ath = _stage_30_11_7_good_resolvers()
    migration_resolver = build_migration_resolver(
        _DictSource({"mint-confirmed": _ev("mint-confirmed")})
    )
    base = {
        "candidate_id": "cand-dip",
        "token_mint": "mint-confirmed",
        "pair_type": "SOL",
        "created_at_utc": "2026-01-01T00:00:00Z",
    }
    result = enrich_harvested_candidate(
        base,
        market_context_resolver=mc,
        tier_resolver=tier,
        migration_resolver=migration_resolver,
        ath_resolver=lambda base: None,  # ATH missing
        created_at_utc="2026-01-01T00:00:00Z",
    )
    # Migration confirmed, but the ATH / drawdown dimension blocks: no candidate is
    # built, so it can never reach the Stage 30.11.5 runner / transport.
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_MISSING_ATH
    assert result.rejected_dimension == ENRICH_DIMENSION_ATH
    assert result.enriched_candidate is None


def test_invalid_anchor_still_fails_stage_30_11_7_migration_dimension() -> None:
    # An impossible-anchor COMPLETE reading fed into the committed Stage 30.11.7
    # enrichment must STILL fail the MIGRATION dimension (UNCONFIRMED_MIGRATION): a
    # fake / impossible migration timestamp never passes migration.
    from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
        enrich_harvested_candidate,
    )
    from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
        ENRICH_DECISION_REJECTED,
        ENRICH_DIMENSION_MIGRATION,
        ENRICH_REASON_UNCONFIRMED_MIGRATION,
    )

    mc, tier, ath = _stage_30_11_7_good_resolvers()
    # A COMPLETE, redaction-safe, fresh reading whose ONLY defect is an impossible
    # UTC-shaped anchor -> the confirmation fails closed at the anchor check.
    migration_resolver = build_migration_resolver(
        _DictSource(
            {"mint-impossible": _ev("mint-impossible", anchor="2026-99-99T99:99:99Z")}
        )
    )
    base = {
        "candidate_id": "cand-bad-anchor",
        "token_mint": "mint-impossible",
        "pair_type": "SOL",
        "created_at_utc": "2026-01-01T00:00:00Z",
    }
    result = enrich_harvested_candidate(
        base,
        market_context_resolver=mc,
        tier_resolver=tier,
        migration_resolver=migration_resolver,
        ath_resolver=ath,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    # The MIGRATION dimension still FAILS CLOSED -- no enriched candidate is built, so
    # it can never reach the Stage 30.11.5 runner / transport.
    assert result.enrichment_decision == ENRICH_DECISION_REJECTED
    assert result.enrichment_reason == ENRICH_REASON_UNCONFIRMED_MIGRATION
    assert result.rejected_dimension == ENRICH_DIMENSION_MIGRATION
    assert result.enriched_candidate is None
