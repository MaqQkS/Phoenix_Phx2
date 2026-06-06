"""Stage 30.11.10 offline fake ATH-resolver proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.10 ATH-resolver
adapter maps a committed-shape ATH reading onto the Stage 30.11.7 ATH resolver contract
for EXACTLY a for-this-mint, ATH-present, post-migration-verified, drawdown-bearing
reading -- and fails closed (with a precise reason) for every blank-mint / missing-anchor
/ unavailable-source / source-error / cross-mint / not-present / pre-migration /
missing-drawdown reading -- using a fake / offline INJECTED migration resolver + ATH
context source ONLY:

    a deterministic NINE-base scenario
      -> the Stage 30.11.10 ATH resolver (over the injected fake migration resolver +
         fake per-mint ATH context source)
        -> exactly ONE base resolves (``mint-resolved`` -- a PRESENT,
           post-migration-verified reading carrying a drawdown)
        -> the other eight fail closed on eight DISTINCT reasons (a blank mint, a
           missing migration anchor, an unavailable ATH source, a raising ATH source, a
           cross-mint reading, a not-present ATH, a pre-migration ATH, a present ATH with
           no drawdown)
      -> the rolled-up resolver tally (nine seen, one resolved, eight unresolved)

So a baseline run drives nine bases and resolves exactly one, proving the resolver maps
ONLY a real post-migration ATH with a drawdown, carries the committed drawdown VERBATIM
(never recomputes it), binds STRICTLY by mint (no cross-mint inheritance), and fails
closed on every missing / stale / pre-migration / malformed reading. This helper produces
ONLY the per-candidate resolutions + the resolver tally; it CONSTRUCTS no Stage 30.11.7
enrichment / runner / transport / dispatch sink, so it can never reach a send surface.
The committed composition -- a resolved ATH clearing the Stage 30.11.7 ATH dimension end
to end, and a missing / pre-migration reading still failing before transport -- is proven
by the Stage 30.11.10 composition TEST (which feeds this slice's resolver into the
committed Stage 30.11.7 adapter); keeping that composition in the test keeps THIS
production slice a clean leaf that imports no Stage 30.11.7 / Stage 30.11.8 / Stage
30.11.9 module.

It is NOT a live runner driver, NOT a live provider run, NOT a live send, NOT a real
dispatch reservation, NOT a real transport, NOT a real ATH reader, and NOT a new
readiness gate. It CONSTRUCTS no filesystem I/O, reads no environment, opens no network
connection, reads no wall clock (every timestamp is injected / reading-carried), runs no
daemon / ``while`` loop, and touches no live provider / real transport path. The real ATH
reader binding (the committed Stage 27.4 / Stage 29.2 brain) + the controlled live
ceremony remain a SEPARATE, explicitly operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports only the Stage 30.11.10 ATH-resolver models + adapter siblings. No other
    PHX2 module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / live runner / provider / real
    transport / Stage 30.7 display bridge / Stage 30.11.5 / Stage 30.11.6 / Stage
    30.11.7 / Stage 30.11.8 / Stage 30.11.9 import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` / compression, NO
    ``time`` / wall clock / random, NO ``decimal`` (the drawdown is carried VERBATIM),
    NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PHX2.stage30.stage30_11_10_ath_resolver_adapter import build_ath_resolver
from PHX2.stage30.stage30_11_10_ath_resolver_models import (
    ATH_DECISION_RESOLVED,
    STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    STAGE30_11_10_ATH_STATUS_PRESENT,
    STAGE30_11_10_ATH_STATUS_UNAVAILABLE,
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE30_11_10_DRAWDOWN_BASIS_NOT_APPLICABLE,
    STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT,
    Stage30_11_10AthContextRecord,
    Stage30_11_10AthResolverRunResult,
    Stage30_11_10AthResolverSummary,
)


# The deterministic caller-injected timestamp for the default scenario (never a
# wall-clock read). The anchor is a trailing-Z migration-event time the fake migration
# resolver hands back as the confirmed anchor; ``_DEFAULT_CREATED_AT`` stamps the
# rolled-up summary.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"
_VALID_ANCHOR: str = "2026-05-27T00:00:00Z"


# A neutral safe-to-display source label the fake readings carry (never a host /
# transport destination / secret).
_SOURCE_LABEL: str = "ath-src"


# The deterministic scenario mints. ``mint-resolved`` resolves; the other eight fail
# closed on eight DISTINCT reasons.
_MINT_BLANK: str = ""
_MINT_NO_ANCHOR: str = "mint-no-anchor"
_MINT_SOURCE_UNAVAILABLE: str = "mint-unavailable"
_MINT_SOURCE_ERROR: str = "mint-source-error"
_MINT_CROSS: str = "mint-cross"
_MINT_NOT_PRESENT: str = "mint-not-present"
_MINT_PRE_MIGRATION: str = "mint-pre-migration"
_MINT_MISSING_DRAWDOWN: str = "mint-missing-drawdown"


# ---------------------------------------------------------------------------
# Pure field reader (the fakes read a base / record duck-typed)
# ---------------------------------------------------------------------------


def _read(source: object, key: str) -> object:
    """Read field ``key`` from ``source`` (mapping ``.get`` or ``getattr``). Pure /
    total; never raises.
    """
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


# ---------------------------------------------------------------------------
# Proof-local fake migration resolution + resolver (the injected migration seam)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeMigrationResolution:
    """A proof-local fake migration resolution (the Stage 30.11.8-style shape the ATH
    resolver reads duck-typed): ``confirmed`` + the confirmed ``migration_event_time_utc``
    anchor.
    """

    confirmed: bool
    migration_event_time_utc: Optional[str]
    token_mint: str = ""
    source_ref: Optional[str] = None


@dataclass(frozen=True)
class Stage30_11_10FakeMigrationResolver:
    """A proof-local fake migration resolver.

    Implements the injected migration-resolver seam the ATH resolver consumes:
    ``resolver(base) -> resolution``. Confirms EVERY mint with ``valid_anchor`` EXCEPT a
    configured set of ``unconfirmed_mints`` (which return ``confirmed=False`` with no
    anchor -- the audit's "missing migration anchor"). Pure; no I/O, no env, no network.
    """

    valid_anchor: str
    unconfirmed_mints: Tuple[str, ...] = ()

    def __call__(self, base: object) -> _FakeMigrationResolution:
        mint = _read(base, "token_mint")
        if (
            not isinstance(mint, str)
            or mint.strip() == ""
            or mint in self.unconfirmed_mints
        ):
            return _FakeMigrationResolution(
                confirmed=False,
                migration_event_time_utc=None,
                token_mint=mint if isinstance(mint, str) else "",
            )
        return _FakeMigrationResolution(
            confirmed=True,
            migration_event_time_utc=self.valid_anchor,
            token_mint=mint,
            source_ref="mig-ref",
        )


# ---------------------------------------------------------------------------
# Proof-local fake per-mint ATH context source (the injected ATH-reader seam)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_10FakeAthContextSource:
    """A proof-local fake per-mint ATH context source.

    Implements the injected ATH-source seam the ATH resolver consumes:
    ``read_ath_context(token_mint, *, migration_event_time_utc) -> reading | None``,
    returning that mint's committed-shape ATH reading. Holds an in-memory mint -> reading
    map plus a set of mints for which the source deliberately RAISES (to exercise the
    source-error fail-closed path). A mint absent from the map returns ``None`` (no
    reading -> the source-unavailable fail-closed path); a non-string mint returns
    ``None``. The confirmed anchor is accepted and required to be a non-blank string (the
    seam threads it for the real out-of-repo reader; the fake just asserts it arrived).
    Pure; no I/O, no env, no network, no provider call.
    """

    by_mint: Dict[str, Stage30_11_10AthContextRecord]
    raise_for: Tuple[str, ...] = ()

    def read_ath_context(
        self, token_mint: object, *, migration_event_time_utc: object
    ) -> Optional[Stage30_11_10AthContextRecord]:
        """Return the reading bound to ``token_mint``, raising for a configured mint.

        Pure / total apart from the deliberate configured raise. A non-string mint, a
        blank anchor, or an absent mint returns ``None``.
        """
        if isinstance(token_mint, str) and token_mint in self.raise_for:
            raise RuntimeError(
                "stage30_11_10 fake ath source deliberate failure"
            )
        if not isinstance(token_mint, str):
            return None
        if (
            not isinstance(migration_event_time_utc, str)
            or migration_event_time_utc.strip() == ""
        ):
            # The seam contract guarantees a confirmed anchor; a blank one fails closed.
            return None
        return self.by_mint.get(token_mint)


# ---------------------------------------------------------------------------
# Deterministic nine-base scenario + fake dependencies
# ---------------------------------------------------------------------------


def default_fake_bases() -> Tuple[Dict[str, str], ...]:
    """Build the deterministic nine-base default scenario.

    One base resolves (``mint-resolved``), then eight that each fail closed on a DISTINCT
    cause: a blank mint, a mint with no confirmed migration anchor, a mint whose source
    returns no reading, a mint whose source raises, a mint whose reading is bound to a
    DIFFERENT mint, a mint whose ATH is not PRESENT, a mint whose ATH is pre-migration,
    and a mint whose present post-migration ATH carries no drawdown. Pure; no I/O, no
    clock, no env.
    """
    return (
        {"token_mint": STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT},
        {"token_mint": _MINT_BLANK},
        {"token_mint": _MINT_NO_ANCHOR},
        {"token_mint": _MINT_SOURCE_UNAVAILABLE},
        {"token_mint": _MINT_SOURCE_ERROR},
        {"token_mint": _MINT_CROSS},
        {"token_mint": _MINT_NOT_PRESENT},
        {"token_mint": _MINT_PRE_MIGRATION},
        {"token_mint": _MINT_MISSING_DRAWDOWN},
    )


def default_fake_migration_resolver() -> Stage30_11_10FakeMigrationResolver:
    """Build the deterministic fake migration resolver for the default scenario.

    Confirms every mint with the valid trailing-Z anchor EXCEPT ``mint-no-anchor`` (which
    fails closed to no confirmed anchor). Pure; no I/O, no clock, no env.
    """
    return Stage30_11_10FakeMigrationResolver(
        valid_anchor=_VALID_ANCHOR,
        unconfirmed_mints=(_MINT_NO_ANCHOR,),
    )


def default_fake_ath_context_source() -> Stage30_11_10FakeAthContextSource:
    """Build the deterministic fake per-mint ATH context source for the default scenario.

    ``mint-resolved`` -> a PRESENT, post-migration-only, ``FROM_POST_MIGRATION_ATH``
    reading carrying a drawdown. ``mint-cross`` -> a present reading bound to a DIFFERENT
    mint (the resolver refuses to inherit it). ``mint-not-present`` -> an UNAVAILABLE ATH.
    ``mint-pre-migration`` -> a present ATH with a ``NOT_APPLICABLE`` (pre-migration)
    drawdown basis. ``mint-missing-drawdown`` -> a present, post-migration ATH whose
    drawdown is ``None``. ``mint-source-error`` -> a configured deliberate raise.
    ``mint-unavailable`` is deliberately ABSENT (-> the source returns ``None``). Pure; no
    I/O, no clock, no env.
    """
    resolved_reading = Stage30_11_10AthContextRecord(
        token_mint=STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT,
        ath_status=STAGE30_11_10_ATH_STATUS_PRESENT,
        ath_since_migration_status=(
            STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_basis=STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        drawdown_from_ath="0.55",
        ath_source=_SOURCE_LABEL,
    )
    # A reading bound to a DIFFERENT mint than ``mint-cross`` -> never inherited.
    cross_reading = Stage30_11_10AthContextRecord(
        token_mint="mint-cross-other",
        ath_status=STAGE30_11_10_ATH_STATUS_PRESENT,
        ath_since_migration_status=(
            STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_basis=STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        drawdown_from_ath="0.40",
        ath_source=_SOURCE_LABEL,
    )
    not_present_reading = Stage30_11_10AthContextRecord(
        token_mint=_MINT_NOT_PRESENT,
        ath_status=STAGE30_11_10_ATH_STATUS_UNAVAILABLE,
        ath_since_migration_status=None,
        drawdown_basis=STAGE30_11_10_DRAWDOWN_BASIS_NOT_APPLICABLE,
        drawdown_from_ath=None,
        ath_source=_SOURCE_LABEL,
    )
    pre_migration_reading = Stage30_11_10AthContextRecord(
        token_mint=_MINT_PRE_MIGRATION,
        ath_status=STAGE30_11_10_ATH_STATUS_PRESENT,
        ath_since_migration_status=(
            STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
        ),
        drawdown_basis=STAGE30_11_10_DRAWDOWN_BASIS_NOT_APPLICABLE,
        drawdown_from_ath=None,
        ath_source=_SOURCE_LABEL,
    )
    missing_drawdown_reading = Stage30_11_10AthContextRecord(
        token_mint=_MINT_MISSING_DRAWDOWN,
        ath_status=STAGE30_11_10_ATH_STATUS_PRESENT,
        ath_since_migration_status=(
            STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_basis=STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        drawdown_from_ath=None,
        ath_source=_SOURCE_LABEL,
    )
    by_mint: Dict[str, Stage30_11_10AthContextRecord] = {
        STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT: resolved_reading,
        _MINT_CROSS: cross_reading,
        _MINT_NOT_PRESENT: not_present_reading,
        _MINT_PRE_MIGRATION: pre_migration_reading,
        _MINT_MISSING_DRAWDOWN: missing_drawdown_reading,
    }
    return Stage30_11_10FakeAthContextSource(
        by_mint=by_mint,
        raise_for=(_MINT_SOURCE_ERROR,),
    )


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_10_fake_ath_resolver(
    *,
    bases: Optional[Tuple[Dict[str, str], ...]] = None,
    migration_resolver: Optional[Stage30_11_10FakeMigrationResolver] = None,
    ath_context_source: Optional[Stage30_11_10FakeAthContextSource] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_11_10AthResolverRunResult:
    """Drive ONLY the Stage 30.11.10 ATH resolver over the deterministic fake scenario
    and return the ``Stage30_11_10AthResolverRunResult``.

    With every argument defaulted, the deterministic nine-base default scenario is
    resolved against the deterministic fake migration resolver + fake ATH context source.
    Pure / deterministic apart from the fakes' (pure, save the configured raise) behavior;
    reads no clock, no env, no network; reserves no dispatch, sends no live message,
    writes no file, runs no daemon / ``while`` loop. Each outcome is the per-candidate
    resolution; the resolver decides nothing about dip eligibility (the committed Stage
    30.9.3 / 30.10.1 dip gate does, LATER).
    """
    effective_bases = default_fake_bases() if bases is None else bases
    effective_migration = (
        default_fake_migration_resolver()
        if migration_resolver is None
        else migration_resolver
    )
    effective_source = (
        default_fake_ath_context_source()
        if ath_context_source is None
        else ath_context_source
    )
    resolver = build_ath_resolver(
        migration_resolver=effective_migration,
        ath_context_source=effective_source,
    )

    outcomes = tuple(resolver(base) for base in effective_bases)
    resolved = sum(
        1 for outcome in outcomes if outcome.decision == ATH_DECISION_RESOLVED
    )
    unresolved = len(outcomes) - resolved

    summary = Stage30_11_10AthResolverSummary(
        bases_seen=len(outcomes),
        resolved=resolved,
        unresolved=unresolved,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_10AthResolverRunResult(
        outcomes=outcomes,
        summary=summary,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_10FakeMigrationResolver",
    "Stage30_11_10FakeAthContextSource",
    "default_fake_bases",
    "default_fake_migration_resolver",
    "default_fake_ath_context_source",
    "run_stage30_11_10_fake_ath_resolver",
)
