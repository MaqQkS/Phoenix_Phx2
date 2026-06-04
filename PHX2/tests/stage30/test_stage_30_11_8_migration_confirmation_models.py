"""Stage 30.11.8 narrow migration-confirmation bridge models tests.

Pins the Stage 30.11.8 model layer: the minor / schema versions, the Stage 29.5
measurement-status vocabulary mirrored BY VALUE, the warning / redaction tokens,
the closed-set confirmation decision / reason vocabularies + validators, the
evidence / resolution / summary / run-result field names + fail-closed defaults,
and the safe-shape (no secret / payload) field naming.

Pure / offline. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_8_migration_confirmation_models import (
    CONFIRM_DECISION_CONFIRMED,
    CONFIRM_DECISION_UNCONFIRMED,
    CONFIRM_REASON_BLANK_CANDIDATE_MINT,
    CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT,
    CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE,
    CONFIRM_REASON_INVALID_MIGRATION_ANCHOR,
    CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE,
    STAGE30_11_8_CONFIRMATION_DECISIONS,
    STAGE30_11_8_CONFIRMATION_PASS_DECISION,
    STAGE30_11_8_CONFIRMATION_PASS_REASON,
    STAGE30_11_8_CONFIRMATION_REASONS,
    STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION,
    STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS,
    STAGE30_11_8_EXPECTED_BASES_SEEN,
    STAGE30_11_8_EXPECTED_CONFIRMED,
    STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT,
    STAGE30_11_8_EXPECTED_UNCONFIRMED,
    STAGE30_11_8_FAIL_CLOSED_REASONS,
    STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE,
    STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE30_11_8_MIGRATION_WARNING_STALE,
    STAGE30_11_8_MINOR_VERSION,
    STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES,
    STAGE30_11_8_REDACTION_STATUS_SAFE,
    STAGE30_11_8_SOURCE_STAGE,
    Stage30_11_8ConfirmationRunResult,
    Stage30_11_8ConfirmationSummary,
    Stage30_11_8MigrationEvidence,
    Stage30_11_8MigrationResolution,
    confirmation_run_result_field_names,
    confirmation_summary_field_names,
    is_confirmation_decision,
    is_confirmation_reason,
    is_nonblank_str,
    is_recognized_measurement_status,
    migration_evidence_field_names,
    migration_resolution_field_names,
)


# ---------------------------------------------------------------------------
# 1. Minor + schema version + source stage
# ---------------------------------------------------------------------------


def test_minor_and_schema_version_pinned() -> None:
    assert STAGE30_11_8_MINOR_VERSION == "30.11.8"
    assert STAGE30_11_8_CONFIRMATION_SCHEMA_VERSION == (
        "stage30_11_8_v0_migration_confirmation"
    )
    assert STAGE30_11_8_SOURCE_STAGE == "30.11.8"


# ---------------------------------------------------------------------------
# 2. Measurement-status vocabulary (mirrored BY VALUE from Stage 29.5)
# ---------------------------------------------------------------------------


def test_measurement_status_vocabulary_pinned() -> None:
    assert STAGE30_11_8_MEASUREMENT_STATUS_COMPLETE == "COMPLETE"
    assert STAGE30_11_8_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT == (
        "PARTIAL_MIGRATION_PRESENT"
    )
    assert STAGE30_11_8_MEASUREMENT_STATUS_MISSING_MIGRATION == (
        "MISSING_MIGRATION"
    )
    assert STAGE30_11_8_MEASUREMENT_STATUS_INVALID_MIGRATION == (
        "INVALID_MIGRATION"
    )
    assert STAGE30_11_8_MEASUREMENT_STATUS_CONFLICTING_MIGRATION == (
        "CONFLICTING_MIGRATION"
    )
    assert STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES == (
        "COMPLETE",
        "PARTIAL_MIGRATION_PRESENT",
        "MISSING_MIGRATION",
        "INVALID_MIGRATION",
        "CONFLICTING_MIGRATION",
    )
    # COMPLETE is the ONLY confirming status.
    assert STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS == "COMPLETE"
    assert STAGE30_11_8_CONFIRMING_MEASUREMENT_STATUS in (
        STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES
    )


def test_warning_and_redaction_tokens_pinned() -> None:
    assert STAGE30_11_8_MIGRATION_WARNING_STALE == "MIGRATION_STALE"
    assert STAGE30_11_8_REDACTION_STATUS_SAFE == "SAFE"


def test_is_recognized_measurement_status() -> None:
    for value in STAGE30_11_8_RECOGNIZED_MEASUREMENT_STATUS_VALUES:
        assert is_recognized_measurement_status(value)
    for bad in (None, "", "BOGUS", "complete", 5, True):
        assert not is_recognized_measurement_status(bad)


# ---------------------------------------------------------------------------
# 3. Confirmation decisions + reasons (closed sets + validators)
# ---------------------------------------------------------------------------


def test_confirmation_decisions_pinned() -> None:
    assert STAGE30_11_8_CONFIRMATION_DECISIONS == (
        "CONFIRMED_MIGRATION",
        "UNCONFIRMED_MIGRATION",
    )
    assert CONFIRM_DECISION_CONFIRMED == "CONFIRMED_MIGRATION"
    assert CONFIRM_DECISION_UNCONFIRMED == "UNCONFIRMED_MIGRATION"
    assert STAGE30_11_8_CONFIRMATION_PASS_DECISION == "CONFIRMED_MIGRATION"
    for value in STAGE30_11_8_CONFIRMATION_DECISIONS:
        assert is_confirmation_decision(value)
    for bad in (None, "", "confirmed", 1):
        assert not is_confirmation_decision(bad)


def test_confirmation_reasons_pinned_and_precise() -> None:
    assert STAGE30_11_8_CONFIRMATION_REASONS == (
        "CONFIRMED_ON_CHAIN_EVENT",
        "BLANK_CANDIDATE_MINT",
        "MISSING_MIGRATION_EVIDENCE",
        "EVIDENCE_MINT_MISMATCH",
        "REDACTION_UNSAFE",
        "UNKNOWN_MIGRATION",
        "PARTIAL_MIGRATION_UNVERIFIED",
        "EVIDENCE_REPORTS_NO_MIGRATION",
        "CONTRADICTORY_MIGRATION_EVIDENCE",
        "INVALID_MIGRATION_EVIDENCE",
        "STALE_MIGRATION_EVIDENCE",
        "INVALID_MIGRATION_ANCHOR",
    )
    assert STAGE30_11_8_CONFIRMATION_PASS_REASON == "CONFIRMED_ON_CHAIN_EVENT"
    # Contradictory + invalid are DISTINCT first-class reasons (never collapsed).
    assert CONFIRM_REASON_CONTRADICTORY_MIGRATION_EVIDENCE != (
        CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE
    )
    assert CONFIRM_REASON_INVALID_MIGRATION_ANCHOR != (
        CONFIRM_REASON_INVALID_MIGRATION_EVIDENCE
    )
    for value in STAGE30_11_8_CONFIRMATION_REASONS:
        assert is_confirmation_reason(value)
    for bad in (None, "", "nope", 0):
        assert not is_confirmation_reason(bad)


def test_fail_closed_reasons_are_all_reasons_except_confirmed() -> None:
    assert CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT not in (
        STAGE30_11_8_FAIL_CLOSED_REASONS
    )
    assert CONFIRM_REASON_BLANK_CANDIDATE_MINT in (
        STAGE30_11_8_FAIL_CLOSED_REASONS
    )
    # Exactly the reasons minus the single confirmed reason.
    assert set(STAGE30_11_8_FAIL_CLOSED_REASONS) == (
        set(STAGE30_11_8_CONFIRMATION_REASONS)
        - {CONFIRM_REASON_CONFIRMED_ON_CHAIN_EVENT}
    )
    assert len(STAGE30_11_8_FAIL_CLOSED_REASONS) == 11


# ---------------------------------------------------------------------------
# 4. Field names mirror the dataclasses + match the Stage 30.11.7 result fields
# ---------------------------------------------------------------------------


def test_field_name_tuples_match_models() -> None:
    assert migration_evidence_field_names() == (
        "token_mint",
        "measurement_status",
        "migration_event_time_utc",
        "warnings",
        "redaction_status",
        "source_ref",
    )
    assert migration_resolution_field_names() == (
        "confirmed",
        "decision",
        "reason",
        "token_mint",
        "migration_event_time_utc",
        "source_ref",
    )
    assert confirmation_summary_field_names() == (
        "bases_seen",
        "confirmed",
        "unconfirmed",
        "created_at_utc",
    )
    assert confirmation_run_result_field_names() == (
        "outcomes",
        "summary",
        "created_at_utc",
    )


def test_resolution_exposes_stage_30_11_7_migration_resolver_fields() -> None:
    # The Stage 30.11.7 adapter reads ``confirmed`` (and the documented
    # ``source_ref``) duck-typed; both must be resolution field names BY VALUE.
    resolution_fields = migration_resolution_field_names()
    assert "confirmed" in resolution_fields
    assert "source_ref" in resolution_fields
    # The migration anchor is carried for the later ATH / drawdown step + audit.
    assert "migration_event_time_utc" in resolution_fields


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        migration_evidence_field_names()
        + migration_resolution_field_names()
        + confirmation_summary_field_names()
        + confirmation_run_result_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "web" + "hook",
            "api_key",
            "bearer",
            "authorization",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.8 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# 5. Fail-closed dataclass defaults + immutability
# ---------------------------------------------------------------------------


def test_evidence_defaults_are_fail_closed() -> None:
    ev = Stage30_11_8MigrationEvidence()
    assert ev.token_mint is None
    assert ev.measurement_status is None
    assert ev.migration_event_time_utc is None
    assert ev.warnings == ()
    assert ev.redaction_status is None
    assert ev.source_ref is None


def test_models_are_frozen() -> None:
    ev = Stage30_11_8MigrationEvidence(token_mint="m")
    res = Stage30_11_8MigrationResolution(
        confirmed=False,
        decision=CONFIRM_DECISION_UNCONFIRMED,
        reason=CONFIRM_REASON_BLANK_CANDIDATE_MINT,
        token_mint="",
        migration_event_time_utc=None,
        source_ref=None,
    )
    for obj, attr in ((ev, "token_mint"), (res, "confirmed")):
        try:
            setattr(obj, attr, "x")
        except Exception:
            pass
        else:
            raise AssertionError(f"{type(obj).__name__} must be frozen")


def test_summary_and_run_result_shapes() -> None:
    summary = Stage30_11_8ConfirmationSummary(
        bases_seen=11, confirmed=1, unconfirmed=10, created_at_utc="t"
    )
    run = Stage30_11_8ConfirmationRunResult(
        outcomes=(), summary=summary, created_at_utc="t"
    )
    assert run.summary.bases_seen == 11
    assert run.summary.confirmed == 1
    assert run.summary.unconfirmed == 10


# ---------------------------------------------------------------------------
# 6. Safe-shape helper + expected proof baseline
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("mint")
    for bad in (None, "", "   ", 5, True, b"x"):
        assert not is_nonblank_str(bad)


def test_expected_proof_baseline_pinned() -> None:
    assert STAGE30_11_8_EXPECTED_BASES_SEEN == 11
    assert STAGE30_11_8_EXPECTED_CONFIRMED == 1
    assert STAGE30_11_8_EXPECTED_UNCONFIRMED == 10
    assert STAGE30_11_8_EXPECTED_CONFIRMED_TOKEN_MINT == "mint-confirmed"
    assert STAGE30_11_8_EXPECTED_CONFIRMED + STAGE30_11_8_EXPECTED_UNCONFIRMED == (
        STAGE30_11_8_EXPECTED_BASES_SEEN
    )
