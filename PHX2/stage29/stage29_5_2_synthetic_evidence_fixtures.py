"""Stage 29.5.2 synthetic migration evidence fixture builders.

Pure builders that emit Stage 29.5 migration evidence records
tagged ``migration_source=SYNTHETIC_TEST_ONLY`` (the closed-set
Stage 29.5 token reserved for synthetic test fixtures). The
Stage 29.5 boundary scan forbids the bare
``"SYNTHETIC_TEST_ONLY"`` literal in the Stage 29.5 Helius WS
adapter and Stage 29.5 artifact reader production sources; this
file lives outside the Stage 29.5 production inventory and
concentrates the synthetic token in one auditable place so the
adapter / reader production sources stay free of it.

The fixtures here are referenced ONLY by the Stage 29.5.2 test
surface. No Stage 29.3 / 29.4 / 29.5 production code imports
this module. The Stage 29.5.2 composition module imports the
Stage 29.5 record class directly and never imports these
builders.

Discipline:

  * Pure functions. No env reads. No outbound network. No file
    I/O. No top-level Call. No PHX1 import. No Stage 28 import.
    No Stage 29.1 / 29.2 / 29.3 / 29.4 import.
  * Imports only stdlib (``typing``) plus the Stage 29.5 models
    module.
  * Every builder returns an immutable
    ``Stage29_5MigrationEvidenceRecord`` instance with
    ``migration_source=MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY``
    (PRESENT / INVALID / STALE / CONFLICTING variants) or
    ``MIGRATION_SOURCE_UNKNOWN_STAGE29_5`` (MISSING variant; the
    Stage 29.5 dataclass validator requires MISSING to carry
    source=UNKNOWN).
  * Builders accept simple primitive args and never invent a
    timestamp / slot / pool / mint -- the caller supplies every
    safe-shape axis.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_CONFLICTING,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_STALE,
    Stage29_5MigrationEvidenceRecord,
)


# ---------------------------------------------------------------------------
# PRESENT (happy path; matches the Stage 29.5 join's PRESENT
# requirement: quartet + migration_timestamp_utc + source!=UNKNOWN)
# ---------------------------------------------------------------------------


def build_synthetic_present_evidence(
    *,
    base_mint: str,
    pool_account: str,
    pool_program_id: str,
    quote_mint: str,
    migration_timestamp_utc: str,
    observed_at_utc: str,
    migration_slot: Optional[int] = None,
    migration_signature: Optional[str] = None,
    source_event_ref: Optional[str] = None,
) -> Stage29_5MigrationEvidenceRecord:
    """Return a PRESENT synthetic migration evidence record.

    The Stage 29.5 dataclass validator requires the full quartet
    (``base_mint`` / ``pool_account`` / ``pool_program_id`` /
    ``quote_mint``) and a populated
    ``migration_timestamp_utc`` when the status is PRESENT.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
        migration_timestamp_utc=migration_timestamp_utc,
        migration_slot=migration_slot,
        migration_signature=migration_signature,
        observed_at_utc=observed_at_utc,
        source_event_ref=source_event_ref,
    )


# ---------------------------------------------------------------------------
# MISSING (every optional axis None; source=UNKNOWN per Stage 29.5
# validator)
# ---------------------------------------------------------------------------


def build_synthetic_missing_evidence(
    *,
    observed_at_utc: str,
) -> Stage29_5MigrationEvidenceRecord:
    """Return a MISSING synthetic migration evidence record.

    The Stage 29.5 validator requires every optional axis to be
    ``None`` and ``migration_source=UNKNOWN`` when the status is
    MISSING; the source is therefore the UNKNOWN token rather
    than the synthetic token.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
    )


# ---------------------------------------------------------------------------
# INVALID (synthetic; carries the quartet so the join's
# axis-matcher accepts it, but status=INVALID routes the join
# verdict to SOURCE_INVALID)
# ---------------------------------------------------------------------------


def build_synthetic_invalid_evidence(
    *,
    base_mint: str,
    pool_account: str,
    pool_program_id: str,
    quote_mint: str,
    observed_at_utc: str,
    migration_timestamp_utc: Optional[str] = None,
) -> Stage29_5MigrationEvidenceRecord:
    """Return an INVALID synthetic migration evidence record.

    The Stage 29.5 validator allows INVALID with any combination
    of optional axes; this builder carries the quartet so the
    join's axis filter matches it, and exercises the
    SOURCE_INVALID guard in the join.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
        migration_timestamp_utc=migration_timestamp_utc,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
    )


# ---------------------------------------------------------------------------
# STALE (synthetic; the join routes any matched STALE record to
# TIME_WINDOW_INVALID and the projection then routes that to
# PARTIAL_MIGRATION_PRESENT + WARNING_MIGRATION_STALE)
# ---------------------------------------------------------------------------


def build_synthetic_stale_evidence(
    *,
    base_mint: str,
    pool_account: str,
    pool_program_id: str,
    quote_mint: str,
    migration_timestamp_utc: str,
    observed_at_utc: str,
) -> Stage29_5MigrationEvidenceRecord:
    """Return a STALE synthetic migration evidence record.

    A STALE record carries the quartet + a migration_timestamp_utc
    (so the join's axis matcher accepts it) but the status=STALE
    routes the verdict to TIME_WINDOW_INVALID via the Stage 29.5
    join's STALE guard. The projection then emits PARTIAL +
    WARNING_MIGRATION_STALE.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_STALE,
        migration_source=MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
        migration_timestamp_utc=migration_timestamp_utc,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
    )


# ---------------------------------------------------------------------------
# CONFLICTING (synthetic; the join's SOURCE_INVALID guard
# routes any matched CONFLICTING record into INVALID_MIGRATION via
# the projection)
# ---------------------------------------------------------------------------


def build_synthetic_conflicting_evidence(
    *,
    base_mint: str,
    pool_account: str,
    pool_program_id: str,
    quote_mint: str,
    observed_at_utc: str,
    migration_timestamp_utc: Optional[str] = None,
) -> Stage29_5MigrationEvidenceRecord:
    """Return a CONFLICTING synthetic migration evidence record.

    Status=CONFLICTING is admitted by the Stage 29.5 dataclass
    validator without the quartet (only PRESENT requires it).
    This builder carries the quartet anyway so the join's axis
    filter matches the record and exercises the SOURCE_INVALID
    guard for CONFLICTING.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_CONFLICTING,
        migration_source=MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
        migration_timestamp_utc=migration_timestamp_utc,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
    )


__all__ = (
    "build_synthetic_present_evidence",
    "build_synthetic_missing_evidence",
    "build_synthetic_invalid_evidence",
    "build_synthetic_stale_evidence",
    "build_synthetic_conflicting_evidence",
)
