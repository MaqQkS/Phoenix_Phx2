"""Stage 30.11.9 offline fake migration evidence-source proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.9 mint-keyed
evidence-source adapter returns a bound sanitized record for EXACTLY the mints that
have one redaction-safe matching record -- and fails closed (returns ``None``) for
every absent / wrong-mint / conflicting / source-erroring / blank mint -- using a
fake / offline INJECTED record provider ONLY:

    a deterministic SEVEN-mint probe set
      -> the Stage 30.11.9 mint-keyed evidence source (over the injected fake per-mint
         record provider)
        -> exactly TWO mints return a bound record (``mint-present`` -- one matching
           record; ``mint-dup`` -- a value-identical duplicate that collapses to one)
        -> the other five return ``None`` (an absent mint, a provider that yields only
           a wrong-mint record, a provider that yields two DISTINCT conflicting records
           for the mint, a provider that raises, and a blank mint)
      -> the rolled-up source tally (seven probed, two evidence-returned, five
         no-evidence)

So a baseline run probes seven mints and binds evidence for exactly two, proving the
source binds STRICTLY by mint (no cross-mint inheritance), collapses value-identical
duplicates, and fails closed on a missing / conflicting / raising / blank lookup. This
helper produces ONLY the per-probe outcomes + the source tally; it CONSTRUCTS no Stage
30.11.8 confirmation / Stage 30.11.7 enrichment / runner / transport / dispatch sink,
so it can never reach a send surface. The committed composition -- a bound record
clearing the Stage 30.11.8 confirmation + Stage 30.11.7 MIGRATION dimension, and a
confirmed migration plus a missing ATH still failing before transport -- is proven by
the Stage 30.11.9 composition TEST (which feeds this slice's source into the committed
Stage 30.11.8 + Stage 30.11.7 adapters); keeping that composition in the test keeps
THIS production slice a clean leaf that imports no Stage 30.11.8 / Stage 30.11.7
module.

It is NOT a live runner driver, NOT a live provider run, NOT a private send, NOT a
real dispatch reservation, NOT a real transport, NOT a real evidence reader, and NOT a
new readiness gate. It CONSTRUCTS no filesystem I/O, reads no environment, opens no
network connection, reads no wall clock (every timestamp is injected / record-carried),
runs no daemon / ``while`` loop, and touches no private / live provider / real
transport path. The real provider binding + the controlled live ceremony remain a
SEPARATE, explicitly operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports only the Stage 30.11.9 evidence-source models + adapter siblings. No other
    PHX2 module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / live runner / provider / real
    transport / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 / Stage 30.11.8 import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` / compression,
    NO ``time`` / wall clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_migration_evidence_source,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT,
    Stage30_11_9EvidenceSourceProbeOutcome,
    Stage30_11_9EvidenceSourceRunResult,
    Stage30_11_9EvidenceSourceSummary,
    Stage30_11_9MigrationEvidenceRecord,
    is_nonblank_str,
)


# The deterministic caller-injected timestamp for the default scenario (never a
# wall-clock read). The anchor is a trailing-Z migration-event time the proof's
# confirmable records carry (so the records double as confirmable inputs for the
# composition test); ``_DEFAULT_CREATED_AT`` stamps the rolled-up summary.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"
_VALID_ANCHOR: str = "2026-05-27T00:00:00Z"


# Proof-local Stage 29.5 measurement / redaction tokens (mirrored BY VALUE; never an
# import). Used only to shape deterministic records; the Stage 30.11.8 confirmation
# (not this proof) interprets them.
_MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
_MEASUREMENT_STATUS_INVALID_MIGRATION: str = "INVALID_MIGRATION"
_REDACTION_STATUS_SAFE: str = "SAFE"


# The deterministic probe mints. ``mint-present`` + ``mint-dup`` bind evidence; the
# other five fail closed (absent / wrong-mint / conflicting / raising / blank).
_MINT_DUP: str = "mint-dup"
_MINT_ABSENT: str = "mint-absent"
_MINT_WRONG: str = "mint-wrong"
_MINT_CONFLICT: str = "mint-conflict"
_MINT_RAISES: str = "mint-raises"
_MINT_BLANK: str = ""


# ---------------------------------------------------------------------------
# Proof-local fake per-mint record provider (the injected provider protocol)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_9FakeRecordProvider:
    """A proof-local fake per-mint migration evidence record provider.

    Implements the injected provider protocol the evidence-source adapter consumes:
    ``provider(token_mint) -> records`` returning that mint's sanitized record(s). Holds
    an in-memory mint -> records map plus a set of mints for which the provider
    deliberately RAISES (to exercise the source-error fail-closed path). A mint absent
    from the map returns ``()`` (no records); a non-string mint returns ``()``. Pure;
    no I/O, no env, no network, no provider call.
    """

    by_mint: Dict[str, Tuple[Stage30_11_9MigrationEvidenceRecord, ...]]
    raise_for: Tuple[str, ...] = ()

    def __call__(
        self, token_mint: object
    ) -> Tuple[Stage30_11_9MigrationEvidenceRecord, ...]:
        """Return the records bound to ``token_mint``, raising for a configured mint.

        Pure / total apart from the deliberate configured raise. A non-string mint
        returns ``()``.
        """
        if isinstance(token_mint, str) and token_mint in self.raise_for:
            raise RuntimeError(
                "stage30_11_9 fake provider deliberate failure"
            )
        if not isinstance(token_mint, str):
            return ()
        return self.by_mint.get(token_mint, ())


# ---------------------------------------------------------------------------
# Deterministic seven-mint probe set + fake provider
# ---------------------------------------------------------------------------


def default_fake_probe_mints() -> Tuple[str, ...]:
    """Build the deterministic seven-mint default probe set.

    Two mints that bind evidence FIRST (``mint-present`` -- one matching record;
    ``mint-dup`` -- a value-identical duplicate), then five that each fail closed on a
    DISTINCT cause: a mint with no records, a mint whose provider yields only a
    wrong-mint record, a mint whose provider yields two DISTINCT conflicting records, a
    mint whose provider raises, and a blank mint. Pure; no I/O, no clock, no env.
    """
    return (
        STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT,
        _MINT_DUP,
        _MINT_ABSENT,
        _MINT_WRONG,
        _MINT_CONFLICT,
        _MINT_RAISES,
        _MINT_BLANK,
    )


def default_fake_record_provider() -> Stage30_11_9FakeRecordProvider:
    """Build the deterministic fake per-mint record provider for the default probe set.

    ``mint-present`` -> one bound, redaction-safe, COMPLETE, valid trailing-Z record.
    ``mint-dup`` -> the SAME record twice (a value-identical duplicate that the source
    collapses to one). ``mint-wrong`` -> a single record bound to a DIFFERENT mint (the
    source refuses to inherit it). ``mint-conflict`` -> two DISTINCT records bound to
    the mint (an ambiguous set the source fails closed on). ``mint-raises`` -> a
    configured deliberate raise. ``mint-absent`` / the blank mint are deliberately
    ABSENT. Pure; no I/O, no clock, no env.
    """
    present_record = Stage30_11_9MigrationEvidenceRecord(
        token_mint=STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT,
        measurement_status=_MEASUREMENT_STATUS_COMPLETE,
        migration_event_time_utc=_VALID_ANCHOR,
        warnings=(),
        redaction_status=_REDACTION_STATUS_SAFE,
        source_ref="mig-ref-present",
    )
    dup_record = Stage30_11_9MigrationEvidenceRecord(
        token_mint=_MINT_DUP,
        measurement_status=_MEASUREMENT_STATUS_COMPLETE,
        migration_event_time_utc=_VALID_ANCHOR,
        warnings=(),
        redaction_status=_REDACTION_STATUS_SAFE,
        source_ref="mig-ref-dup",
    )
    # A record bound to a DIFFERENT mint than ``mint-wrong`` -> never inherited.
    wrong_record = Stage30_11_9MigrationEvidenceRecord(
        token_mint="some-other-mint",
        measurement_status=_MEASUREMENT_STATUS_COMPLETE,
        migration_event_time_utc=_VALID_ANCHOR,
        warnings=(),
        redaction_status=_REDACTION_STATUS_SAFE,
        source_ref="mig-ref-wrong",
    )
    # Two DISTINCT records bound to ``mint-conflict`` -> ambiguous -> fail closed.
    conflict_record_a = Stage30_11_9MigrationEvidenceRecord(
        token_mint=_MINT_CONFLICT,
        measurement_status=_MEASUREMENT_STATUS_COMPLETE,
        migration_event_time_utc=_VALID_ANCHOR,
        warnings=(),
        redaction_status=_REDACTION_STATUS_SAFE,
        source_ref="mig-ref-conflict-a",
    )
    conflict_record_b = Stage30_11_9MigrationEvidenceRecord(
        token_mint=_MINT_CONFLICT,
        measurement_status=_MEASUREMENT_STATUS_INVALID_MIGRATION,
        migration_event_time_utc=None,
        warnings=(),
        redaction_status=_REDACTION_STATUS_SAFE,
        source_ref="mig-ref-conflict-b",
    )
    by_mint: Dict[str, Tuple[Stage30_11_9MigrationEvidenceRecord, ...]] = {
        STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT: (present_record,),
        _MINT_DUP: (dup_record, dup_record),
        _MINT_WRONG: (wrong_record,),
        _MINT_CONFLICT: (conflict_record_a, conflict_record_b),
    }
    return Stage30_11_9FakeRecordProvider(
        by_mint=by_mint,
        raise_for=(_MINT_RAISES,),
    )


# ---------------------------------------------------------------------------
# Public proof entry point
# ---------------------------------------------------------------------------


def run_stage30_11_9_fake_evidence_source(
    *,
    probe_mints: Optional[Tuple[str, ...]] = None,
    record_provider: Optional[Stage30_11_9FakeRecordProvider] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_11_9EvidenceSourceRunResult:
    """Probe ONLY the Stage 30.11.9 mint-keyed source over the deterministic fake
    provider and return the ``Stage30_11_9EvidenceSourceRunResult``.

    With every argument defaulted, the deterministic seven-mint default probe set is
    looked up against the deterministic fake provider via the mint-keyed source. Pure /
    deterministic apart from the fake provider's (pure, save the configured raise)
    behavior; reads no clock, no env, no network; reserves no dispatch, sends no
    private message, writes no file, runs no daemon / ``while`` loop. Each outcome
    records only the probed mint + whether the source bound a record; the source
    decides nothing about the migration verdict (the Stage 30.11.8 confirmation does).
    """
    effective_mints = (
        default_fake_probe_mints() if probe_mints is None else probe_mints
    )
    effective_provider = (
        default_fake_record_provider()
        if record_provider is None
        else record_provider
    )
    source = build_migration_evidence_source(effective_provider)

    outcomes = tuple(
        Stage30_11_9EvidenceSourceProbeOutcome(
            token_mint=mint if is_nonblank_str(mint) else "",
            evidence_present=(
                source.lookup_migration_evidence(mint) is not None
            ),
        )
        for mint in effective_mints
    )
    evidence_returned = sum(
        1 for outcome in outcomes if outcome.evidence_present
    )
    no_evidence = len(outcomes) - evidence_returned

    summary = Stage30_11_9EvidenceSourceSummary(
        probes_seen=len(outcomes),
        evidence_returned=evidence_returned,
        no_evidence=no_evidence,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_9EvidenceSourceRunResult(
        outcomes=outcomes,
        summary=summary,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_9FakeRecordProvider",
    "default_fake_probe_mints",
    "default_fake_record_provider",
    "run_stage30_11_9_fake_evidence_source",
)
