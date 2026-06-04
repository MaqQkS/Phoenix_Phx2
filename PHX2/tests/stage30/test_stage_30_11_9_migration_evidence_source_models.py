"""Stage 30.11.9 evidence-source models tests.

Pins the passive model layer: the sanitized per-mint evidence record (its field names
EQUAL the Stage 30.11.8 migration evidence field names BY VALUE, every field defaults
to a fail-closed value), the source summary / per-probe outcome / run-result shapes,
the ``is_nonblank_str`` helper, the schema / minor version, and the expected proof
counts.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION,
    STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED,
    STAGE30_11_9_EXPECTED_NO_EVIDENCE,
    STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT,
    STAGE30_11_9_EXPECTED_PROBES_SEEN,
    STAGE30_11_9_MINOR_VERSION,
    STAGE30_11_9_SOURCE_STAGE,
    Stage30_11_9EvidenceSourceProbeOutcome,
    Stage30_11_9EvidenceSourceRunResult,
    Stage30_11_9EvidenceSourceSummary,
    Stage30_11_9MigrationEvidenceRecord,
    evidence_source_probe_outcome_field_names,
    evidence_source_run_result_field_names,
    evidence_source_summary_field_names,
    is_nonblank_str,
    migration_evidence_record_field_names,
)


# The Stage 30.11.8 migration evidence field names this slice mirrors BY VALUE.
_STAGE30_11_8_EVIDENCE_FIELDS = (
    "token_mint",
    "measurement_status",
    "migration_event_time_utc",
    "warnings",
    "redaction_status",
    "source_ref",
)


def test_minor_and_schema_version_pinned() -> None:
    assert STAGE30_11_9_MINOR_VERSION == "30.11.9"
    assert STAGE30_11_9_SOURCE_STAGE == "30.11.9"
    assert STAGE30_11_9_EVIDENCE_SOURCE_SCHEMA_VERSION == (
        "stage30_11_9_v0_migration_evidence_source"
    )


def test_record_field_names_mirror_stage_30_11_8_evidence_by_value() -> None:
    assert migration_evidence_record_field_names() == _STAGE30_11_8_EVIDENCE_FIELDS


def test_bare_record_is_fail_closed_by_default() -> None:
    record = Stage30_11_9MigrationEvidenceRecord()
    assert record.token_mint is None
    assert record.measurement_status is None
    assert record.migration_event_time_utc is None
    # ``warnings`` defaults to None (the FAIL-CLOSED sentinel for a MISSING field),
    # NOT () -- an omitted warnings is malformed evidence the router refuses, never
    # silently "no warnings".
    assert record.warnings is None
    assert record.redaction_status is None
    assert record.source_ref is None


def test_explicit_empty_warnings_is_distinct_from_the_missing_default() -> None:
    # Explicit empty is "source says no warnings" (allowed); the default None is
    # "source did not provide warnings" (malformed / fail closed). They must differ.
    assert Stage30_11_9MigrationEvidenceRecord(warnings=()).warnings == ()
    assert Stage30_11_9MigrationEvidenceRecord().warnings is None
    assert Stage30_11_9MigrationEvidenceRecord(warnings=()).warnings is not None


def test_record_is_frozen() -> None:
    record = Stage30_11_9MigrationEvidenceRecord(token_mint="mint-x")
    with pytest.raises(FrozenInstanceError):
        record.token_mint = "mint-y"  # type: ignore[misc]


def test_record_carries_values_verbatim() -> None:
    record = Stage30_11_9MigrationEvidenceRecord(
        token_mint="mint-x",
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-05-27T00:00:00Z",
        warnings=("MIGRATION_STALE",),
        redaction_status="SAFE",
        source_ref="ref-x",
    )
    assert record.token_mint == "mint-x"
    assert record.measurement_status == "COMPLETE"
    assert record.migration_event_time_utc == "2026-05-27T00:00:00Z"
    assert record.warnings == ("MIGRATION_STALE",)
    assert record.redaction_status == "SAFE"
    assert record.source_ref == "ref-x"


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("mint-x") is True
    assert is_nonblank_str("  x  ") is True
    assert is_nonblank_str("") is False
    assert is_nonblank_str("   ") is False
    assert is_nonblank_str(None) is False
    assert is_nonblank_str(123) is False
    assert is_nonblank_str(b"mint") is False


def test_summary_and_outcome_and_run_result_field_names() -> None:
    assert evidence_source_summary_field_names() == (
        "probes_seen",
        "evidence_returned",
        "no_evidence",
        "created_at_utc",
    )
    assert evidence_source_probe_outcome_field_names() == (
        "token_mint",
        "evidence_present",
    )
    assert evidence_source_run_result_field_names() == (
        "outcomes",
        "summary",
        "created_at_utc",
    )


def test_summary_and_run_result_construct() -> None:
    summary = Stage30_11_9EvidenceSourceSummary(
        probes_seen=7,
        evidence_returned=2,
        no_evidence=5,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    outcome = Stage30_11_9EvidenceSourceProbeOutcome(
        token_mint="mint-present", evidence_present=True
    )
    run = Stage30_11_9EvidenceSourceRunResult(
        outcomes=(outcome,),
        summary=summary,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    assert run.summary.probes_seen == 7
    assert run.outcomes[0].evidence_present is True


def test_expected_proof_counts_pinned() -> None:
    assert STAGE30_11_9_EXPECTED_PROBES_SEEN == 7
    assert STAGE30_11_9_EXPECTED_EVIDENCE_RETURNED == 2
    assert STAGE30_11_9_EXPECTED_NO_EVIDENCE == 5
    assert STAGE30_11_9_EXPECTED_PRESENT_TOKEN_MINT == "mint-present"
