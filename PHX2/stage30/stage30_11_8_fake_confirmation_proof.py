"""Stage 30.11.8 offline fake migration-confirmation proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.8
confirmation adapter maps real-shaped migration evidence onto a ``confirmed``
verdict -- and fails closed, with a PRECISE reason, on every missing / mismatched /
unsafe / unknown / partial / no-migration / contradictory / invalid / stale /
mis-anchored reading -- using a fake / offline INJECTED evidence source ONLY:

    a deterministic ELEVEN-base fake source (one bound, redaction-safe, on-chain
    ``COMPLETE``, fresh, valid-anchor evidence + ten distinct fail-closed readings)
      -> the Stage 30.11.8 confirmation resolver (over the injected fake per-mint
         evidence source)
        -> exactly ONE base confirms (``mint-confirmed`` -> CONFIRMED_MIGRATION /
           CONFIRMED_ON_CHAIN_EVENT, with the bound migration anchor + provenance)
        -> the other ten fail closed on ten DISTINCT reasons (a missing evidence, a
           mismatched mint, an unsafe redaction, an unknown status, a partial
           reading, an evidence-reports-no-migration reading, a conflicting reading,
           an invalid reading, a stale reading, a malformed anchor)
      -> the rolled-up confirmation tally (eleven seen, one confirmed, ten
         unconfirmed)

So a baseline run sees eleven bases and confirms exactly one, proving the
confirmation requires real, bound, redaction-safe, on-chain, fresh, valid-anchor
evidence and NEVER collapses a contradictory / invalid reading into a silent
unknown. This helper produces ONLY the per-candidate resolutions + the confirmation
tally; it CONSTRUCTS no Stage 30.11.7 enrichment / runner / transport / dispatch
sink, so it can never reach a send surface. The committed Stage 30.11.7 enrichment
composition -- a confirmed verdict clearing the MIGRATION dimension, an UNKNOWN
verdict still failing it, and a confirmed verdict plus a missing ATH still failing
before transport -- is proven by the Stage 30.11.8 TEST (which feeds this slice's
resolver into the committed Stage 30.11.7 adapter); keeping that composition in the
test keeps THIS production slice a clean leaf that imports no Stage 30.11.5 / Stage
30.11.6 / Stage 30.11.7 module.

It is NOT a live runner driver, NOT a live provider run, NOT a Discord send, NOT a
real dispatch reservation, NOT a real transport, NOT a real evidence source, and
NOT a new readiness gate. It CONSTRUCTS no filesystem I/O, reads no environment,
opens no network connection, reads no wall clock (every timestamp is injected /
evidence-carried), runs no daemon / ``while`` loop, and touches no Discord / live
provider / real transport path. The real evidence-source binding + the controlled
live ceremony remain a SEPARATE, explicitly operator-authorized step this slice
does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports only the Stage 30.11.8 confirmation-adapter + models siblings. No other
    PHX2 module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / live runner / provider / real
    transport / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` / compression,
    NO ``time`` / wall clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PHX2.stage30.stage30_11_8_migration_confirmation_adapter import (
    build_migration_resolver,
)
from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT,
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE30_11_8_MIGRATION_WARNING_STALE,
    STAGE30_11_8_REDACTION_STATUS_SAFE,
    Stage30_11_8ConfirmationRunResult,
    Stage30_11_8ConfirmationSummary,
    Stage30_11_8MigrationEvidence,
)


# The deterministic caller-injected timestamps for the default scenario (never a
# wall-clock read). The anchor is the bound migration-event time the confirmed
# evidence carries; ``_DEFAULT_CREATED_AT`` stamps the rolled-up summary.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"
_VALID_ANCHOR: str = "2026-05-27T00:00:00Z"
_BAD_ANCHOR: str = "BAD-ANCHOR"


# A redaction token that is present but NOT safe (so a COMPLETE reading carrying it
# fails closed to REDACTION_UNSAFE). Proof-local; never a production token.
_UNSAFE_REDACTION: str = "REDACTED"


# ---------------------------------------------------------------------------
# Proof-local fake base candidate (harvested / flat identity shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_8FakeBaseCandidate:
    """A proof-local fake harvested / flat base candidate.

    Stands in for the harvested candidate IDENTITY the real live chain produces:
    only the ``token_mint`` the confirmation reads to look up that mint's evidence.
    Carries no migration evidence itself (the confirmation resolves it via the
    injected source); carries no raw payload, no host, no transport destination.
    """

    token_mint: str


# ---------------------------------------------------------------------------
# Proof-local fake per-mint evidence source (the injected source protocol)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_8FakeEvidenceSource:
    """A proof-local fake per-mint migration evidence source.

    Implements the injected evidence-source protocol the confirmation adapter
    consumes: ``lookup_migration_evidence(token_mint) -> evidence | None``. Holds an
    in-memory mint -> sanitized-evidence map; a mint absent from the map returns
    ``None`` (so the confirmation fails closed to MISSING_MIGRATION_EVIDENCE). Pure;
    no I/O, no env, no network, no provider call.
    """

    by_mint: Dict[str, Stage30_11_8MigrationEvidence]

    def lookup_migration_evidence(
        self, token_mint: object
    ) -> Optional[Stage30_11_8MigrationEvidence]:
        """Return the sanitized evidence bound to ``token_mint``, or ``None`` if
        the mint is unknown / not a string. Pure / total; never raises.
        """
        if not isinstance(token_mint, str):
            return None
        return self.by_mint.get(token_mint)


# ---------------------------------------------------------------------------
# Deterministic eleven-base fake source + evidence map
# ---------------------------------------------------------------------------


def default_fake_confirmation_bases() -> Tuple[
    Stage30_11_8FakeBaseCandidate, ...
]:
    """Build the deterministic eleven-base default fake candidate stream.

    One confirmable base FIRST (``mint-confirmed`` -- its carried-verbatim identity
    is the expected confirmed mint), then ten bases that each fail closed on a
    DISTINCT reason: a mint with no evidence, a mint whose evidence is bound to a
    different mint, an unsafe-redaction reading, an unknown-status reading, a partial
    reading, an evidence-reports-no-migration reading, a conflicting reading, an
    invalid reading, a stale reading, and a malformed-anchor reading. Pure; no I/O,
    no clock, no env.
    """
    return (
        Stage30_11_8FakeBaseCandidate(STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT),
        Stage30_11_8FakeBaseCandidate("mint-missing"),
        Stage30_11_8FakeBaseCandidate("mint-mismatch"),
        Stage30_11_8FakeBaseCandidate("mint-unsafe"),
        Stage30_11_8FakeBaseCandidate("mint-unknown"),
        Stage30_11_8FakeBaseCandidate("mint-partial"),
        Stage30_11_8FakeBaseCandidate("mint-noevent"),
        Stage30_11_8FakeBaseCandidate("mint-conflict"),
        Stage30_11_8FakeBaseCandidate("mint-invalid"),
        Stage30_11_8FakeBaseCandidate("mint-stale"),
        Stage30_11_8FakeBaseCandidate("mint-badanchor"),
    )


def default_fake_evidence_source() -> Stage30_11_8FakeEvidenceSource:
    """Build the deterministic fake per-mint evidence source for the default stream.

    The map binds each non-missing mint to a sanitized evidence reading that exercises
    exactly one confirmation outcome. ``mint-missing`` is deliberately ABSENT (so the
    source returns ``None``). ``mint-mismatch`` is bound to evidence carrying a
    DIFFERENT ``token_mint`` (so the confirmation refuses to inherit it). Pure; no
    I/O, no clock, no env.
    """
    by_mint: Dict[str, Stage30_11_8MigrationEvidence] = {
        # The ONE confirmable reading: bound, redaction-safe, on-chain COMPLETE,
        # fresh (no stale warning), with a valid ISO-8601 UTC migration anchor.
        STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT: Stage30_11_8MigrationEvidence(
            token_mint=STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT,
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
            migration_event_time_utc=_VALID_ANCHOR,
            warnings=(),
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
            source_ref="mig-ref-confirmed",
        ),
        # Bound to a DIFFERENT mint -> EVIDENCE_MINT_MISMATCH (never inherited).
        "mint-mismatch": Stage30_11_8MigrationEvidence(
            token_mint="some-other-mint",
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
            migration_event_time_utc=_VALID_ANCHOR,
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # COMPLETE but NOT redaction-safe -> REDACTION_UNSAFE (redaction dominates).
        "mint-unsafe": Stage30_11_8MigrationEvidence(
            token_mint="mint-unsafe",
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
            migration_event_time_utc=_VALID_ANCHOR,
            redaction_status=_UNSAFE_REDACTION,
        ),
        # Unrecognized / missing measurement status -> UNKNOWN_MIGRATION.
        "mint-unknown": Stage30_11_8MigrationEvidence(
            token_mint="mint-unknown",
            measurement_status=None,
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # Partial reading -> PARTIAL_MIGRATION_UNVERIFIED.
        "mint-partial": Stage30_11_8MigrationEvidence(
            token_mint="mint-partial",
            measurement_status=(
                STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
            ),
            migration_event_time_utc=_VALID_ANCHOR,
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # Evidence reports no migration -> EVIDENCE_REPORTS_NO_MIGRATION.
        "mint-noevent": Stage30_11_8MigrationEvidence(
            token_mint="mint-noevent",
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION,
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # Conflicting reading -> CONTRADICTORY_MIGRATION_EVIDENCE.
        "mint-conflict": Stage30_11_8MigrationEvidence(
            token_mint="mint-conflict",
            measurement_status=(
                STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION
            ),
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # Invalid reading -> INVALID_MIGRATION_EVIDENCE.
        "mint-invalid": Stage30_11_8MigrationEvidence(
            token_mint="mint-invalid",
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION,
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # COMPLETE but stale -> STALE_MIGRATION_EVIDENCE.
        "mint-stale": Stage30_11_8MigrationEvidence(
            token_mint="mint-stale",
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
            migration_event_time_utc=_VALID_ANCHOR,
            warnings=(STAGE30_11_8_MIGRATION_WARNING_STALE,),
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
        # COMPLETE + safe + fresh but a malformed anchor -> INVALID_MIGRATION_ANCHOR.
        "mint-badanchor": Stage30_11_8MigrationEvidence(
            token_mint="mint-badanchor",
            measurement_status=STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
            migration_event_time_utc=_BAD_ANCHOR,
            redaction_status=STAGE30_11_8_REDACTION_STATUS_SAFE,
        ),
    }
    return Stage30_11_8FakeEvidenceSource(by_mint=by_mint)


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_8_fake_confirmation(
    *,
    bases: Optional[Tuple[Stage30_11_8FakeBaseCandidate, ...]] = None,
    evidence_source: Optional[Stage30_11_8FakeEvidenceSource] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_11_8ConfirmationRunResult:
    """Run ONLY the Stage 30.11.8 confirmation resolver over the deterministic fake
    source and return the ``Stage30_11_8ConfirmationRunResult``.

    With every argument defaulted, the deterministic eleven-base default stream is
    resolved against the deterministic fake per-mint evidence source via the
    confirmation resolver. Pure / deterministic apart from the fake source's (pure)
    behavior; reads no clock, no env, no network; reserves no dispatch, sends no
    Discord, writes no file, runs no daemon / ``while`` loop. The single confirmed
    resolution carries the bound migration anchor + provenance for the later ATH /
    drawdown step; the ten fail-closed resolutions carry neither.
    """
    effective_bases = (
        default_fake_confirmation_bases() if bases is None else bases
    )
    effective_source = (
        default_fake_evidence_source()
        if evidence_source is None
        else evidence_source
    )
    resolver = build_migration_resolver(effective_source)

    outcomes = tuple(resolver(base) for base in effective_bases)
    confirmed = sum(1 for outcome in outcomes if outcome.confirmed is True)
    unconfirmed = len(outcomes) - confirmed

    summary = Stage30_11_8ConfirmationSummary(
        bases_seen=len(outcomes),
        confirmed=confirmed,
        unconfirmed=unconfirmed,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_8ConfirmationRunResult(
        outcomes=outcomes,
        summary=summary,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_8FakeBaseCandidate",
    "Stage30_11_8FakeEvidenceSource",
    "default_fake_confirmation_bases",
    "default_fake_evidence_source",
    "run_stage30_11_8_fake_confirmation",
)
