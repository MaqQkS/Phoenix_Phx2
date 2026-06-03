"""Stage 30.11.7 offline fake candidate dip-enrichment proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.7 enrichment
bridge fills the missing Stage 30 dip fields onto a harvested / flat base candidate
-- and fails closed on every missing / unavailable / unconfirmed / stale / malformed
dimension -- using fakes / offline INJECTED resolvers ONLY:

    a deterministic SIX-base fake source
      -> the Stage 30.11.7 enrichment bridge (injected fake market context / tier /
         migration / ATH resolvers)
        -> one Tier 1 dip base + one Tier Unknown non-dip base enrich cleanly into a
           Stage 30.11.5-shaped flat enriched candidate
        -> one base whose market context resolver returns no context ->
           REJECTED_ENRICHMENT / MISSING_MARKET_CONTEXT (no candidate)
        -> one base whose tier resolver returns no tier ->
           REJECTED_ENRICHMENT / MISSING_TIER (no candidate)
        -> one base whose migration resolver returns an UNKNOWN (unconfirmed)
           verdict -> REJECTED_ENRICHMENT / UNCONFIRMED_MIGRATION (no candidate)
        -> one base whose ATH resolver returns a STALE ATH ->
           REJECTED_ENRICHMENT / STALE_ATH (no candidate)
      -> the enriched ``candidate_source`` (two enriched candidates)

So a baseline run sees six bases and enriches exactly two (the Tier 1 dip + the
Tier Unknown non-dip), failing closed on the missing-market-context / missing-tier /
unconfirmed-migration / stale-ATH bases. This helper produces ONLY the enriched
``candidate_source`` + the enrichment tally; it CONSTRUCTS no runner / transport /
dispatch sink, so it can never reach a send surface. The committed Stage 30.11.5
bounded runner is composed -- and the "exactly one PASS dip reaches the fake
transport" end-to-end assertion proven -- by the Stage 30.11.7 TEST (which feeds
this enriched ``candidate_source`` through the committed Stage 30.11.5 fake live
wiring proof); keeping the runner composition in the test keeps THIS production
slice a clean leaf that imports no Stage 30.11.5 / Stage 30.11.6 module.

It is NOT a live runner driver, NOT a live provider run, NOT a Discord send, NOT a
real dispatch reservation, NOT a real transport, NOT a real resolver, and NOT a new
readiness gate. It CONSTRUCTS no filesystem I/O, reads no environment, opens no
network connection, reads no wall clock (every clock is injected), runs no daemon /
``while`` loop, and touches no Discord / live provider / real transport path. The
real resolver binding + the controlled live ceremony remain a SEPARATE, explicitly
operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports only the Stage 30.11.7 enrichment-adapter + models siblings. No other
    PHX2 module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / live runner / provider / real
    transport / Stage 30.11.5 / Stage 30.11.6 import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` / compression,
    NO ``time`` / wall clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
    enrich_candidate_source,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT,
    Stage30_11_7AthResolution,
    Stage30_11_7EnrichmentRunResult,
    Stage30_11_7MarketContextResolution,
    Stage30_11_7MigrationResolution,
    Stage30_11_7TierResolution,
)


# The deterministic caller-injected timestamp for the default scenario (never a
# wall-clock read). Matches the Stage 30.11.5 fake-proof clock so the composed
# end-to-end proof (run by the Stage 30.11.7 test) is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# Closed-set fake enrichment scenarios (proof-local; never a production token).
# Each names the SINGLE dimension whose injected resolver fails closed for that
# base (or a clean dip / non-dip enrichment). A base's non-failing dimensions
# always resolve to a usable signal, so the reject is attributed to the named
# dimension and never to an earlier one.
_SCENARIO_DIP: str = "DIP"
_SCENARIO_NON_DIP: str = "NON_DIP"
_SCENARIO_MISSING_MC: str = "MISSING_MC"
_SCENARIO_MISSING_TIER: str = "MISSING_TIER"
_SCENARIO_UNKNOWN_MIGRATION: str = "UNKNOWN_MIGRATION"
_SCENARIO_STALE_ATH: str = "STALE_ATH"


# A non-dip tier token: a present, well-shaped tier the enrichment carries verbatim
# (so the base enriches cleanly) but the committed Stage 30.10.1 dip gate normalizes
# to TIER_UNKNOWN and SKIPS (so the gate -- NOT the enrichment -- suppresses it).
_NON_DIP_TIER_HINT: str = "Tier Unknown"
_DIP_TIER_HINT: str = "Tier 1"


# ---------------------------------------------------------------------------
# Fake base candidate (proof-local harvested / flat identity shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_7FakeBaseCandidate:
    """A proof-local fake harvested / flat base candidate.

    Stands in for the Stage 30.11.6 harvested candidate IDENTITY the real live
    chain produces (a ``candidate_id`` / ``token_mint`` / ``pair_type`` /
    ``source_ref`` / ``created_at_utc``) plus a closed-set ``scenario`` + a
    ``tier_hint`` the fake resolvers read to decide what to return. Carries NO dip
    fields itself (the enrichment resolves them via the injected resolvers); carries
    no raw payload, no host, no transport destination.
    """

    candidate_id: str
    token_mint: str
    pair_type: str
    source_ref: str
    created_at_utc: str
    tier_hint: str
    scenario: str


# ---------------------------------------------------------------------------
# Injected fake resolvers (read the base scenario; return a usable / failing
# resolution per dimension)
# ---------------------------------------------------------------------------


def fake_market_context_resolver(
    base: object,
) -> Optional[Stage30_11_7MarketContextResolution]:
    """Fake market context resolver: a present context with a positive cap, EXCEPT
    for the missing-market-context scenario (returns ``None`` -> the enrichment
    fails closed to MISSING_MARKET_CONTEXT). Pure; no I/O, no env, no provider call.
    """
    if isinstance(base, Stage30_11_7FakeBaseCandidate) and (
        base.scenario == _SCENARIO_MISSING_MC
    ):
        return None
    return Stage30_11_7MarketContextResolution(
        present=True,
        current_market_cap_usd="12345.67",
        source_ref="mc-ref",
    )


def fake_tier_resolver(
    base: object,
) -> Optional[Stage30_11_7TierResolution]:
    """Fake tier resolver: the base's tier token carried verbatim, EXCEPT for the
    missing-tier scenario (returns ``None`` -> the enrichment fails closed to
    MISSING_TIER). Pure; no I/O, no env, no provider call.
    """
    if isinstance(base, Stage30_11_7FakeBaseCandidate) and (
        base.scenario == _SCENARIO_MISSING_TIER
    ):
        return None
    tier_hint = (
        base.tier_hint
        if isinstance(base, Stage30_11_7FakeBaseCandidate)
        else None
    )
    return Stage30_11_7TierResolution(tier_hint=tier_hint)


def fake_migration_resolver(
    base: object,
) -> Optional[Stage30_11_7MigrationResolution]:
    """Fake migration resolver: a CONFIRMED migration, EXCEPT for the
    unknown-migration scenario (returns an UNKNOWN / unconfirmed verdict ->
    the enrichment fails closed to UNCONFIRMED_MIGRATION). Pure; no I/O.
    """
    if isinstance(base, Stage30_11_7FakeBaseCandidate) and (
        base.scenario == _SCENARIO_UNKNOWN_MIGRATION
    ):
        return Stage30_11_7MigrationResolution(confirmed=False)
    return Stage30_11_7MigrationResolution(
        confirmed=True, source_ref="mig-ref"
    )


def fake_ath_resolver(
    base: object,
) -> Optional[Stage30_11_7AthResolution]:
    """Fake ATH resolver: a present, fresh, post-migration-verified ATH with a
    finite drawdown, EXCEPT for the stale-ATH scenario (returns a present-but-stale
    ATH -> the enrichment fails closed to STALE_ATH). Pure; no I/O.
    """
    if isinstance(base, Stage30_11_7FakeBaseCandidate) and (
        base.scenario == _SCENARIO_STALE_ATH
    ):
        return Stage30_11_7AthResolution(
            present=True,
            fresh=False,
            post_migration_ath_verified=True,
            drawdown_from_ath="0.55",
        )
    return Stage30_11_7AthResolution(
        present=True,
        fresh=True,
        post_migration_ath_verified=True,
        drawdown_from_ath="0.55",
        source_ref="ath-ref",
    )


# ---------------------------------------------------------------------------
# Deterministic six-base fake source
# ---------------------------------------------------------------------------


def _base(
    candidate_id: str, token_mint: str, tier_hint: str, scenario: str
) -> Stage30_11_7FakeBaseCandidate:
    """Build one proof-local fake base candidate. Pure; no I/O, no clock, no env."""
    return Stage30_11_7FakeBaseCandidate(
        candidate_id=candidate_id,
        token_mint=token_mint,
        pair_type="SOL",
        source_ref="ref-" + candidate_id,
        created_at_utc=_DEFAULT_CREATED_AT,
        tier_hint=tier_hint,
        scenario=scenario,
    )


def default_fake_enrichment_source() -> Tuple[
    Stage30_11_7FakeBaseCandidate, ...
]:
    """Build the deterministic six-base default fake source.

    One Tier Unknown non-dip base FIRST (it enriches cleanly, then the committed dip
    gate suppresses it -- so when the committed runner evaluates the enriched
    ``candidate_source`` the non-dip is SEEN + bridged + gate-skipped BEFORE the dip
    reaches the single-send dispatch cap, proving a non-dip reaches the gate but not
    the transport), then one Tier 1 dip base (its carried-verbatim identity is the
    expected dip ``stage30_11_7_cand_dip`` / ``mint-dip``), then one
    missing-market-context base, one missing-tier base, one unknown-migration base,
    and one stale-ATH base. Pure; no I/O, no clock, no env.
    """
    return (
        _base(
            "stage30_11_7_cand_nondip",
            "mint-nondip",
            _NON_DIP_TIER_HINT,
            _SCENARIO_NON_DIP,
        ),
        _base(
            STAGE30_11_7_EXPECTED_DIP_CANDIDATE_ID,
            STAGE30_11_7_EXPECTED_DIP_TOKEN_MINT,
            _DIP_TIER_HINT,
            _SCENARIO_DIP,
        ),
        _base(
            "stage30_11_7_cand_no_mc",
            "mint-no-mc",
            _DIP_TIER_HINT,
            _SCENARIO_MISSING_MC,
        ),
        _base(
            "stage30_11_7_cand_no_tier",
            "mint-no-tier",
            _DIP_TIER_HINT,
            _SCENARIO_MISSING_TIER,
        ),
        _base(
            "stage30_11_7_cand_unk_mig",
            "mint-unk-mig",
            _DIP_TIER_HINT,
            _SCENARIO_UNKNOWN_MIGRATION,
        ),
        _base(
            "stage30_11_7_cand_stale_ath",
            "mint-stale-ath",
            _DIP_TIER_HINT,
            _SCENARIO_STALE_ATH,
        ),
    )


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_7_fake_enrichment(
    *,
    bases: Optional[Tuple[Stage30_11_7FakeBaseCandidate, ...]] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_11_7EnrichmentRunResult:
    """Run ONLY the Stage 30.11.7 enrichment pass over the deterministic fake source
    and return the ``Stage30_11_7EnrichmentRunResult``.

    With every argument defaulted, the deterministic six-base default fake source is
    enriched through the bounded enrichment helper with the fake market context /
    tier / migration / ATH resolvers and the default enrichment cap. Pure /
    deterministic apart from the fake resolvers' (pure) behavior; reads no clock, no
    env, no network; reserves no dispatch, sends no Discord, writes no file. The
    enriched ``candidate_source`` is the INPUT the committed Stage 30.11.5 bounded
    runner consumes; the Stage 30.11.7 test feeds it through the committed Stage
    30.11.5 fake live wiring proof to prove EXACTLY one PASS dip reaches the fake
    transport.
    """
    effective_bases = (
        default_fake_enrichment_source() if bases is None else bases
    )
    return enrich_candidate_source(
        effective_bases,
        market_context_resolver=fake_market_context_resolver,
        tier_resolver=fake_tier_resolver,
        migration_resolver=fake_migration_resolver,
        ath_resolver=fake_ath_resolver,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_7FakeBaseCandidate",
    "fake_market_context_resolver",
    "fake_tier_resolver",
    "fake_migration_resolver",
    "fake_ath_resolver",
    "default_fake_enrichment_source",
    "run_stage30_11_7_fake_enrichment",
)
