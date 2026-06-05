"""Stage 29.5.7 producer + projection tests."""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
    STAGE29_5_7_PRODUCER_DEFAULT_MAX_ENVELOPES_TO_SCAN,
    STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN,
    Stage29_5_7LiveMigrationEvidenceProducer,
    project_migration_evidence_to_sanitized_summary,
)
from PHX2.tests.stage29._stage_29_5_7_helius_fixtures import (
    BASE_MINT,
    DEFAULT_ANCHOR_UTC,
    OBSERVED_AT_UTC,
    make_migration_envelope,
    make_swap_envelope,
    make_wrong_program_envelope,
)


def _clock() -> str:
    return OBSERVED_AT_UTC


# ---------------------------------------------------------------------------
# Projection: PRESENT -> COMPLETE / SAFE / () / verbatim anchor
# ---------------------------------------------------------------------------


def test_projection_maps_present_to_complete_safe_summary() -> None:
    record = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source="HELIUS_WS",
        base_mint=BASE_MINT,
        pool_account="Po" + "o" * 42,
        pool_program_id="Pg" + "p" * 42,
        quote_mint="Qm" + "q" * 42,
        migration_timestamp_utc="2024-05-27T00:00:00Z",
        migration_slot=7,
        migration_signature="sig",
        observed_at_utc=OBSERVED_AT_UTC,
        source_event_ref="ref",
    )
    summary = project_migration_evidence_to_sanitized_summary(record)
    assert summary is not None
    assert summary.token_mint == BASE_MINT
    assert summary.measurement_status == "COMPLETE"
    assert summary.redaction_status == "SAFE"
    assert summary.warnings == ()
    assert summary.migration_event_time_utc == "2024-05-27T00:00:00Z"
    assert summary.source_ref == "ref"


def test_projection_fails_closed_on_non_record() -> None:
    assert project_migration_evidence_to_sanitized_summary(None) is None
    assert project_migration_evidence_to_sanitized_summary({"x": 1}) is None


def test_projection_fails_closed_on_missing_axes() -> None:
    # A PRESENT record missing the slot / signature / source_ref must not map to a
    # COMPLETE summary.
    record = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source="HELIUS_WS",
        base_mint=BASE_MINT,
        pool_account="Po" + "o" * 42,
        pool_program_id="Pg" + "p" * 42,
        quote_mint="Qm" + "q" * 42,
        migration_timestamp_utc="2024-05-27T00:00:00Z",
        migration_slot=None,  # missing slot
        migration_signature=None,
        observed_at_utc=OBSERVED_AT_UTC,
        source_event_ref=None,
    )
    assert project_migration_evidence_to_sanitized_summary(record) is None


def test_projection_fails_closed_on_missing_status() -> None:
    missing = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source="UNKNOWN",
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=OBSERVED_AT_UTC,
        source_event_ref=None,
    )
    assert project_migration_evidence_to_sanitized_summary(missing) is None


# ---------------------------------------------------------------------------
# Bounded producer
# ---------------------------------------------------------------------------


def test_producer_tallies_proven_and_rejected() -> None:
    producer = Stage29_5_7LiveMigrationEvidenceProducer(clock=_clock)
    envelopes = [
        make_migration_envelope(),
        make_swap_envelope(),
        make_migration_envelope(base_mint="Bb" + "n" * 42),
        make_wrong_program_envelope(),
        "not even json",
    ]
    result = producer.produce_migration_evidence(envelopes, "2026-05-27T01:00:00Z")
    assert result.summary.envelopes_seen == 5
    assert result.summary.migrations_proven == 2
    assert result.summary.rejected == 3
    assert len(result.evidence_records) == 2
    assert len(result.sanitized_summaries) == 2
    for summary in result.sanitized_summaries:
        assert summary.measurement_status == "COMPLETE"
        assert summary.redaction_status == "SAFE"
        assert summary.warnings == ()
        assert summary.migration_event_time_utc == DEFAULT_ANCHOR_UTC


def test_producer_respects_scan_bound() -> None:
    producer = Stage29_5_7LiveMigrationEvidenceProducer(
        clock=_clock, max_envelopes_to_scan=2
    )
    envelopes = [make_migration_envelope() for _ in range(5)]
    result = producer.produce_migration_evidence(envelopes, "2026-05-27T01:00:00Z")
    assert result.summary.envelopes_seen == 2
    assert result.summary.migrations_proven == 2


def test_producer_default_and_hard_bounds() -> None:
    assert STAGE29_5_7_PRODUCER_DEFAULT_MAX_ENVELOPES_TO_SCAN == 64
    assert STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN == 1024


def test_producer_rejects_bad_clock() -> None:
    with pytest.raises(ValueError):
        Stage29_5_7LiveMigrationEvidenceProducer(clock="not callable")


def test_producer_rejects_bad_bound() -> None:
    for bad in (0, -1, 1025, True, "5", 1.0):
        with pytest.raises(ValueError):
            Stage29_5_7LiveMigrationEvidenceProducer(
                clock=_clock, max_envelopes_to_scan=bad
            )


def test_producer_empty_batch() -> None:
    producer = Stage29_5_7LiveMigrationEvidenceProducer(clock=_clock)
    result = producer.produce_migration_evidence([], "2026-05-27T01:00:00Z")
    assert result.summary.envelopes_seen == 0
    assert result.evidence_records == ()
    assert result.sanitized_summaries == ()


def test_producer_never_emits_synthetic_source() -> None:
    # The production path tags evidence HELIUS_WS, never the synthetic test token.
    producer = Stage29_5_7LiveMigrationEvidenceProducer(clock=_clock)
    result = producer.produce_migration_evidence(
        [make_migration_envelope()], "2026-05-27T01:00:00Z"
    )
    for record in result.evidence_records:
        assert record.migration_source != MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
        assert record.migration_source == "HELIUS_WS"
