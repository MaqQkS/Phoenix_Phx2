"""Stage 29.5 migration models focused tests.

Pins:

  * Closed-set vocabulary tuples + per-token string constants
    exposed verbatim.
  * Predicate helpers accept only their respective closed-set
    tokens and reject everything else.
  * Frozen dataclasses validate every closed-set field at
    ``__post_init__``.
  * ``Stage29_5MigrationEvidenceRecord`` validator rejects
    ``PRESENT``-without-required-axes and accepts ``MISSING``-
    with-all-None-axes.
  * ``Stage29_5MigrationJoinRecord`` validator enforces
    ``matched_evidence_count == len(matched_evidence)``.
  * ``Stage29_5PrivatePingMigrationContext`` validator enforces
    ``filter_enforcement_status == "NOT_ACTIVE_STAGE_29_PENDING"``
    verbatim.
  * ``Stage29_5MigrationEvidenceError`` carries a closed-set
    ``refusal_reason`` attribute and rejects non-closed-set
    tokens.
  * Safe-shape validators
    (``is_safe_mint_or_pool_string`` /
    ``is_safe_iso8601_utc_string``) enforce the documented
    invariants.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_PAIR_MISMATCH,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_CONFLICTING,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_STALE,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    REFUSAL_REASON_BUDGET_EXCEEDED,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    REFUSAL_REASON_MISSING_REQUIRED_AXIS,
    REFUSAL_REASON_NONE,
    REFUSAL_REASON_SOURCE_INVALID,
    REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED,
    REFUSAL_REASON_UNREADABLE_ARTIFACT,
    REFUSAL_REASON_UNSUPPORTED_KIND,
    STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES,
    STAGE29_5_MEASUREMENT_STATUS_VALUES,
    STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION,
    STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION,
    STAGE29_5_MIGRATION_JOIN_STATUS_VALUES,
    STAGE29_5_MIGRATION_SOURCE_VALUES,
    STAGE29_5_MIGRATION_STATUS_VALUES,
    STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION,
    STAGE29_5_REDACTION_STATUS_VALUES,
    STAGE29_5_REFUSAL_REASON_VALUES,
    STAGE29_5_WARNING_CODE_VALUES,
    Stage29_5MigrationEvidenceError,
    Stage29_5MigrationEvidenceRecord,
    Stage29_5MigrationJoinRecord,
    Stage29_5PrivatePingMigrationContext,
    WARNING_MIGRATION_CONFLICT,
    WARNING_MIGRATION_MISSING,
    WARNING_MIGRATION_PAIR_MISMATCH,
    WARNING_MIGRATION_SLOT_MISSING,
    WARNING_MIGRATION_SOURCE_UNKNOWN,
    WARNING_MIGRATION_STALE,
    WARNING_MIGRATION_TIMESTAMP_INVALID,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
    parse_safe_utc_datetime,
    is_stage29_5_measurement_status_value,
    is_stage29_5_migration_join_status_value,
    is_stage29_5_migration_source_value,
    is_stage29_5_migration_status_value,
    is_stage29_5_redaction_status_value,
    is_stage29_5_refusal_reason_value,
    is_stage29_5_warning_code_value,
)


# ---------------------------------------------------------------------------
# Fake fixtures (synthetic safe-shape values; never on-chain)
# ---------------------------------------------------------------------------


_SAFE_MINT_A: str = "M" * 44
_SAFE_MINT_B: str = "N" * 44
_SAFE_POOL_A: str = "P" * 44
_SAFE_POOL_PROGRAM: str = "G" * 44
_SAFE_QUOTE: str = "Q" * 44
_SAFE_TIMESTAMP_A: str = "2026-05-25T00:00:00+00:00"
_SAFE_TIMESTAMP_B: str = "2026-05-25T01:00:00+00:00"
_SAFE_OBSERVED_AT: str = "2026-05-25T02:00:00+00:00"


def _present_evidence(
    *,
    source: str = MIGRATION_SOURCE_HELIUS_WS,
    slot: int = 123456,
    signature: str = "synth-sig-A",
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=source,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_SAFE_TIMESTAMP_A,
        migration_slot=slot,
        migration_signature=signature,
        observed_at_utc=_SAFE_OBSERVED_AT,
        source_event_ref="synth-ref-A",
    )


def _missing_evidence() -> Stage29_5MigrationEvidenceRecord:
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
        observed_at_utc=_SAFE_OBSERVED_AT,
        source_event_ref=None,
    )


# ---------------------------------------------------------------------------
# Closed-set vocab tuples + tokens
# ---------------------------------------------------------------------------


def test_migration_status_values_tuple_locked():
    assert STAGE29_5_MIGRATION_STATUS_VALUES == (
        MIGRATION_STATUS_PRESENT,
        MIGRATION_STATUS_MISSING,
        MIGRATION_STATUS_CONFLICTING,
        MIGRATION_STATUS_INVALID,
        MIGRATION_STATUS_STALE,
    )


def test_migration_source_values_tuple_locked():
    assert STAGE29_5_MIGRATION_SOURCE_VALUES == (
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    )


def test_migration_join_status_values_tuple_locked():
    assert STAGE29_5_MIGRATION_JOIN_STATUS_VALUES == (
        MIGRATION_JOIN_STATUS_JOINED,
        MIGRATION_JOIN_STATUS_NO_MATCH,
        MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
        MIGRATION_JOIN_STATUS_SOURCE_INVALID,
        MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
        MIGRATION_JOIN_STATUS_PAIR_MISMATCH,
    )


def test_measurement_status_values_tuple_locked():
    assert STAGE29_5_MEASUREMENT_STATUS_VALUES == (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MEASUREMENT_STATUS_COMPLETE,
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    )


def test_warning_code_values_tuple_locked():
    assert STAGE29_5_WARNING_CODE_VALUES == (
        WARNING_MIGRATION_MISSING,
        WARNING_POST_MIGRATION_ATH_UNVERIFIED,
        WARNING_MIGRATION_SOURCE_UNKNOWN,
        WARNING_MIGRATION_CONFLICT,
        WARNING_MIGRATION_STALE,
        WARNING_MIGRATION_TIMESTAMP_INVALID,
        WARNING_MIGRATION_PAIR_MISMATCH,
        WARNING_MIGRATION_SLOT_MISSING,
    )


def test_redaction_status_values_tuple_locked():
    assert STAGE29_5_REDACTION_STATUS_VALUES == (
        REDACTION_STATUS_SAFE,
        REDACTION_STATUS_REDACTED,
    )


def test_filter_enforcement_status_values_locked_to_one_token():
    assert STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES == (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    )
    assert (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_refusal_reason_values_tuple_locked():
    assert STAGE29_5_REFUSAL_REASON_VALUES == (
        REFUSAL_REASON_NONE,
        REFUSAL_REASON_MALFORMED_PAYLOAD,
        REFUSAL_REASON_UNSUPPORTED_KIND,
        REFUSAL_REASON_MISSING_REQUIRED_AXIS,
        REFUSAL_REASON_UNREADABLE_ARTIFACT,
        REFUSAL_REASON_SOURCE_INVALID,
        REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED,
        REFUSAL_REASON_BUDGET_EXCEEDED,
    )


def test_schema_version_pins():
    assert (
        STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION
        == "stage29_5_v0_migration_evidence"
    )
    assert (
        STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION
        == "stage29_5_v0_migration_join"
    )
    assert (
        STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION
        == "stage29_5_v0_private_ping_context"
    )


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token", STAGE29_5_MIGRATION_STATUS_VALUES
)
def test_is_migration_status_value_accepts_closed_set(token):
    assert is_stage29_5_migration_status_value(token) is True


@pytest.mark.parametrize(
    "value",
    ["", "present", "MIGRATED", None, 0, 1.0, object()],
)
def test_is_migration_status_value_rejects_others(value):
    assert (
        is_stage29_5_migration_status_value(value) is False
    )


@pytest.mark.parametrize(
    "token", STAGE29_5_MIGRATION_SOURCE_VALUES
)
def test_is_migration_source_value_accepts_closed_set(token):
    assert is_stage29_5_migration_source_value(token) is True


@pytest.mark.parametrize(
    "value", ["helius_ws", "PUMP_FUN", None, 42]
)
def test_is_migration_source_value_rejects_others(value):
    assert (
        is_stage29_5_migration_source_value(value) is False
    )


@pytest.mark.parametrize(
    "token", STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
)
def test_is_migration_join_status_value_accepts_closed_set(token):
    assert (
        is_stage29_5_migration_join_status_value(token) is True
    )


@pytest.mark.parametrize(
    "value", ["joined", "AMBIGUOUS", None]
)
def test_is_migration_join_status_value_rejects_others(value):
    assert (
        is_stage29_5_migration_join_status_value(value)
        is False
    )


@pytest.mark.parametrize(
    "token", STAGE29_5_MEASUREMENT_STATUS_VALUES
)
def test_is_measurement_status_value_accepts_closed_set(token):
    assert (
        is_stage29_5_measurement_status_value(token) is True
    )


@pytest.mark.parametrize(
    "value", ["complete", "PARTIAL", None]
)
def test_is_measurement_status_value_rejects_others(value):
    assert (
        is_stage29_5_measurement_status_value(value) is False
    )


@pytest.mark.parametrize(
    "token", STAGE29_5_WARNING_CODE_VALUES
)
def test_is_warning_code_value_accepts_closed_set(token):
    assert is_stage29_5_warning_code_value(token) is True


@pytest.mark.parametrize(
    "value", ["migration_missing", "WARN", None]
)
def test_is_warning_code_value_rejects_others(value):
    assert is_stage29_5_warning_code_value(value) is False


@pytest.mark.parametrize(
    "token", STAGE29_5_REDACTION_STATUS_VALUES
)
def test_is_redaction_status_value_accepts_closed_set(token):
    assert is_stage29_5_redaction_status_value(token) is True


@pytest.mark.parametrize(
    "token", STAGE29_5_REFUSAL_REASON_VALUES
)
def test_is_refusal_reason_value_accepts_closed_set(token):
    assert is_stage29_5_refusal_reason_value(token) is True


# ---------------------------------------------------------------------------
# Safe-shape validators
# ---------------------------------------------------------------------------


def test_is_safe_mint_or_pool_string_accepts_32_chars():
    assert is_safe_mint_or_pool_string("X" * 32) is True


def test_is_safe_mint_or_pool_string_accepts_64_chars():
    assert is_safe_mint_or_pool_string("X" * 64) is True


def test_is_safe_mint_or_pool_string_rejects_31_chars():
    assert is_safe_mint_or_pool_string("X" * 31) is False


def test_is_safe_mint_or_pool_string_rejects_65_chars():
    assert is_safe_mint_or_pool_string("X" * 65) is False


def test_is_safe_mint_or_pool_string_rejects_whitespace():
    assert (
        is_safe_mint_or_pool_string("X" * 30 + " " + "X" * 14)
        is False
    )


def test_is_safe_mint_or_pool_string_rejects_non_string():
    assert is_safe_mint_or_pool_string(None) is False
    assert is_safe_mint_or_pool_string(12345) is False


def test_is_safe_iso8601_utc_string_accepts_zulu_suffix():
    assert (
        is_safe_iso8601_utc_string("2026-05-25T00:00:00Z")
        is True
    )


def test_is_safe_iso8601_utc_string_accepts_explicit_offset():
    assert (
        is_safe_iso8601_utc_string("2026-05-25T00:00:00+00:00")
        is True
    )


def test_is_safe_iso8601_utc_string_rejects_local_offset():
    assert (
        is_safe_iso8601_utc_string("2026-05-25T00:00:00-05:00")
        is False
    )


def test_is_safe_iso8601_utc_string_rejects_naive_string():
    assert (
        is_safe_iso8601_utc_string("2026-05-25T00:00:00")
        is False
    )


def test_is_safe_iso8601_utc_string_rejects_empty():
    assert is_safe_iso8601_utc_string("") is False


# ---------------------------------------------------------------------------
# Stage29_5MigrationEvidenceRecord
# ---------------------------------------------------------------------------


def test_present_evidence_round_trip():
    record = _present_evidence()
    assert (
        record.migration_status == MIGRATION_STATUS_PRESENT
    )
    assert (
        record.migration_source == MIGRATION_SOURCE_HELIUS_WS
    )
    assert record.base_mint == _SAFE_MINT_A
    assert (
        record.schema_version
        == STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION
    )


def test_missing_evidence_round_trip():
    record = _missing_evidence()
    assert (
        record.migration_status == MIGRATION_STATUS_MISSING
    )
    assert (
        record.migration_source
        == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    )
    assert record.base_mint is None
    assert record.migration_timestamp_utc is None
    assert record.migration_slot is None


def test_present_evidence_rejects_none_base_mint():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=None,
            pool_account=_SAFE_POOL_A,
            pool_program_id=_SAFE_POOL_PROGRAM,
            quote_mint=_SAFE_QUOTE,
            migration_timestamp_utc=_SAFE_TIMESTAMP_A,
            migration_slot=1,
            migration_signature="s",
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_present_evidence_rejects_none_timestamp():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=_SAFE_MINT_A,
            pool_account=_SAFE_POOL_A,
            pool_program_id=_SAFE_POOL_PROGRAM,
            quote_mint=_SAFE_QUOTE,
            migration_timestamp_utc=None,
            migration_slot=1,
            migration_signature="s",
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_present_evidence_rejects_unknown_source():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            base_mint=_SAFE_MINT_A,
            pool_account=_SAFE_POOL_A,
            pool_program_id=_SAFE_POOL_PROGRAM,
            quote_mint=_SAFE_QUOTE,
            migration_timestamp_utc=_SAFE_TIMESTAMP_A,
            migration_slot=1,
            migration_signature="s",
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_missing_evidence_rejects_populated_axis():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_MISSING,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            base_mint=_SAFE_MINT_A,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_signature=None,
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_missing_evidence_rejects_non_unknown_source():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_MISSING,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=None,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_signature=None,
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_evidence_rejects_bad_status_token():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status="REAL_BAD",
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=None,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_signature=None,
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_evidence_rejects_bad_source_token():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_INVALID,
            migration_source="DEXSCREENER",
            base_mint=None,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_signature=None,
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_evidence_rejects_negative_slot():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_INVALID,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=None,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=-1,
            migration_signature=None,
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_evidence_rejects_bool_slot():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_INVALID,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=None,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=True,
            migration_signature=None,
            observed_at_utc=_SAFE_OBSERVED_AT,
            source_event_ref=None,
        )


def test_evidence_rejects_unsafe_observed_at_utc():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_MISSING,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            base_mint=None,
            pool_account=None,
            pool_program_id=None,
            quote_mint=None,
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_signature=None,
            observed_at_utc="2026-05-25",
            source_event_ref=None,
        )


def test_evidence_frozen():
    record = _missing_evidence()
    with pytest.raises(Exception):
        record.migration_status = MIGRATION_STATUS_PRESENT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Stage29_5MigrationJoinRecord
# ---------------------------------------------------------------------------


def _empty_join() -> Stage29_5MigrationJoinRecord:
    return Stage29_5MigrationJoinRecord(
        migration_join_status=MIGRATION_JOIN_STATUS_NO_MATCH,
        candidate_base_mint=_SAFE_MINT_A,
        candidate_pool_account=None,
        candidate_pool_program_id=None,
        candidate_quote_mint=None,
        matched_evidence_count=0,
        matched_evidence=(),
        time_window_start_utc=None,
        time_window_end_utc=None,
        joined_at_utc=_SAFE_OBSERVED_AT,
    )


def test_empty_join_round_trip():
    j = _empty_join()
    assert (
        j.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )
    assert j.matched_evidence == ()
    assert j.matched_evidence_count == 0


def test_join_count_must_match_tuple_len():
    with pytest.raises(ValueError):
        Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_JOINED
            ),
            candidate_base_mint=_SAFE_MINT_A,
            candidate_pool_account=None,
            candidate_pool_program_id=None,
            candidate_quote_mint=None,
            matched_evidence_count=2,
            matched_evidence=(_present_evidence(),),
            time_window_start_utc=None,
            time_window_end_utc=None,
            joined_at_utc=_SAFE_OBSERVED_AT,
        )


def test_join_rejects_unsafe_candidate_base_mint():
    with pytest.raises(ValueError):
        Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_NO_MATCH
            ),
            candidate_base_mint="too_short",
            candidate_pool_account=None,
            candidate_pool_program_id=None,
            candidate_quote_mint=None,
            matched_evidence_count=0,
            matched_evidence=(),
            time_window_start_utc=None,
            time_window_end_utc=None,
            joined_at_utc=_SAFE_OBSERVED_AT,
        )


def test_join_rejects_bad_window_string():
    with pytest.raises(ValueError):
        Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_NO_MATCH
            ),
            candidate_base_mint=_SAFE_MINT_A,
            candidate_pool_account=None,
            candidate_pool_program_id=None,
            candidate_quote_mint=None,
            matched_evidence_count=0,
            matched_evidence=(),
            time_window_start_utc="2026-05-25",
            time_window_end_utc=None,
            joined_at_utc=_SAFE_OBSERVED_AT,
        )


def test_join_rejects_non_evidence_entry():
    with pytest.raises(ValueError):
        Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_JOINED
            ),
            candidate_base_mint=_SAFE_MINT_A,
            candidate_pool_account=None,
            candidate_pool_program_id=None,
            candidate_quote_mint=None,
            matched_evidence_count=1,
            matched_evidence=("not-a-record",),  # type: ignore[arg-type]
            time_window_start_utc=None,
            time_window_end_utc=None,
            joined_at_utc=_SAFE_OBSERVED_AT,
        )


def test_join_frozen():
    j = _empty_join()
    with pytest.raises(Exception):
        j.migration_join_status = (
            MIGRATION_JOIN_STATUS_JOINED  # type: ignore[misc]
        )


# ---------------------------------------------------------------------------
# Stage29_5PrivatePingMigrationContext
# ---------------------------------------------------------------------------


def _missing_context() -> (
    Stage29_5PrivatePingMigrationContext
):
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=(
            MEASUREMENT_STATUS_MISSING_MIGRATION
        ),
        warnings=(
            WARNING_MIGRATION_MISSING,
            WARNING_POST_MIGRATION_ATH_UNVERIFIED,
        ),
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_source=(
            MIGRATION_SOURCE_UNKNOWN_STAGE29_5
        ),
        post_migration_ath_verified=None,
        join_status_echoed=MIGRATION_JOIN_STATUS_NO_MATCH,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_SAFE_OBSERVED_AT,
    )


def test_missing_context_round_trip():
    ctx = _missing_context()
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_MISSING_MIGRATION
    )
    assert (
        ctx.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert ctx.redaction_status == REDACTION_STATUS_SAFE


def test_context_rejects_non_locked_enforcement_status():
    with pytest.raises(ValueError):
        Stage29_5PrivatePingMigrationContext(
            measurement_status=(
                MEASUREMENT_STATUS_MISSING_MIGRATION
            ),
            warnings=(),
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            post_migration_ath_verified=None,
            join_status_echoed=(
                MIGRATION_JOIN_STATUS_NO_MATCH
            ),
            redaction_status=REDACTION_STATUS_SAFE,
            filter_enforcement_status="ACTIVE",
            observed_at_utc=_SAFE_OBSERVED_AT,
        )


def test_context_rejects_duplicate_warning():
    with pytest.raises(ValueError):
        Stage29_5PrivatePingMigrationContext(
            measurement_status=(
                MEASUREMENT_STATUS_MISSING_MIGRATION
            ),
            warnings=(
                WARNING_MIGRATION_MISSING,
                WARNING_MIGRATION_MISSING,
            ),
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            post_migration_ath_verified=None,
            join_status_echoed=(
                MIGRATION_JOIN_STATUS_NO_MATCH
            ),
            redaction_status=REDACTION_STATUS_SAFE,
            filter_enforcement_status=(
                FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
            ),
            observed_at_utc=_SAFE_OBSERVED_AT,
        )


def test_context_rejects_bad_warning_token():
    with pytest.raises(ValueError):
        Stage29_5PrivatePingMigrationContext(
            measurement_status=(
                MEASUREMENT_STATUS_MISSING_MIGRATION
            ),
            warnings=("NOT_A_REAL_WARNING",),
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            post_migration_ath_verified=None,
            join_status_echoed=(
                MIGRATION_JOIN_STATUS_NO_MATCH
            ),
            redaction_status=REDACTION_STATUS_SAFE,
            filter_enforcement_status=(
                FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
            ),
            observed_at_utc=_SAFE_OBSERVED_AT,
        )


def test_context_rejects_non_bool_ath_verified():
    with pytest.raises(ValueError):
        Stage29_5PrivatePingMigrationContext(
            measurement_status=(
                MEASUREMENT_STATUS_MISSING_MIGRATION
            ),
            warnings=(),
            migration_timestamp_utc=None,
            migration_slot=None,
            migration_source=(
                MIGRATION_SOURCE_UNKNOWN_STAGE29_5
            ),
            post_migration_ath_verified="yes",  # type: ignore[arg-type]
            join_status_echoed=(
                MIGRATION_JOIN_STATUS_NO_MATCH
            ),
            redaction_status=REDACTION_STATUS_SAFE,
            filter_enforcement_status=(
                FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
            ),
            observed_at_utc=_SAFE_OBSERVED_AT,
        )


def test_context_frozen():
    ctx = _missing_context()
    with pytest.raises(Exception):
        ctx.measurement_status = (
            MEASUREMENT_STATUS_COMPLETE  # type: ignore[misc]
        )


# ---------------------------------------------------------------------------
# Stage29_5MigrationEvidenceError
# ---------------------------------------------------------------------------


def test_error_carries_closed_set_refusal_reason():
    err = Stage29_5MigrationEvidenceError(
        REFUSAL_REASON_MALFORMED_PAYLOAD,
        "bad bytes",
    )
    assert (
        err.refusal_reason == REFUSAL_REASON_MALFORMED_PAYLOAD
    )
    assert err.detail == "bad bytes"
    assert "MALFORMED_PAYLOAD" in str(err)


def test_error_rejects_bad_refusal_reason():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceError(
            "NOT_A_REASON", "detail"
        )


def test_error_rejects_non_string_detail():
    with pytest.raises(ValueError):
        Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD, 42  # type: ignore[arg-type]
        )


def test_error_with_empty_detail_carries_reason_in_str():
    err = Stage29_5MigrationEvidenceError(
        REFUSAL_REASON_NONE
    )
    assert err.refusal_reason == REFUSAL_REASON_NONE
    assert "NONE" in str(err)


# ---------------------------------------------------------------------------
# Stage 29.5.1 remediation: strict UTC datetime validation
# ---------------------------------------------------------------------------


# Bad ISO-8601 inputs the strict parser must reject. Each entry
# pins a distinct failure mode; all must yield
# ``is_safe_iso8601_utc_string == False`` AND raise ``ValueError``
# when used as ``observed_at_utc`` on an evidence record.
_MALFORMED_UTC_TIMESTAMPS: tuple[str, ...] = (
    "2026-13-01T00:00:00Z",         # month 13
    "2026-02-30T00:00:00Z",         # Feb 30 — invalid calendar
    "2026-05-25T25:00:00Z",         # hour 25
    "2026-05-25T00:60:00Z",         # minute 60
    "2026-05-25T00:00:00+05:00",    # non-UTC offset (positive)
    "2026-05-25T00:00:00-00:01",    # non-UTC offset (negative)
    " 2026-05-25T00:00:00Z",        # leading whitespace
    "2026-05-25T00:00:00Z ",        # trailing whitespace
    "2026-05-25 00:00:00Z",         # space separator instead of T
    "2026-05-25T00:00:00",          # no offset, no zulu
    "",                             # empty string
    "not-a-timestamp",              # garbage
)


_SAFE_OBSERVED_AT_VALID: str = (
    "2026-05-25T12:00:00+00:00"
)
_SAFE_MINT_FOR_TIMESTAMP_PIN: str = "Z" * 44
_SAFE_POOL_FOR_TIMESTAMP_PIN: str = "Y" * 44
_SAFE_PROGRAM_FOR_TIMESTAMP_PIN: str = "X" * 44
_SAFE_QUOTE_FOR_TIMESTAMP_PIN: str = "W" * 44


def test_malformed_utc_timestamp_rejected_for_evidence_and_windows():
    """Stage 29.5.1 remediation: every malformed ISO-8601 UTC
    string is rejected both by the boolean predicate and by the
    evidence-record dataclass validator.
    """
    for bad in _MALFORMED_UTC_TIMESTAMPS:
        assert not is_safe_iso8601_utc_string(bad), (
            f"is_safe_iso8601_utc_string({bad!r}) must be False"
        )
        with pytest.raises(ValueError):
            parse_safe_utc_datetime(bad)
        with pytest.raises(ValueError):
            Stage29_5MigrationEvidenceRecord(
                migration_status=MIGRATION_STATUS_MISSING,
                migration_source=(
                    MIGRATION_SOURCE_UNKNOWN_STAGE29_5
                ),
                base_mint=None,
                pool_account=None,
                pool_program_id=None,
                quote_mint=None,
                migration_timestamp_utc=None,
                migration_slot=None,
                migration_signature=None,
                observed_at_utc=bad,
                source_event_ref=None,
            )


def test_malformed_utc_timestamp_rejected_in_migration_timestamp():
    """Strict parsing also gates the optional
    ``migration_timestamp_utc`` axis when populated. A MISSING
    record cannot carry a malformed timestamp on any axis.
    """
    # Cannot use MIGRATION_STATUS_PRESENT (the dataclass requires
    # the full quartet on PRESENT); use INVALID with the full
    # quartet so we can populate migration_timestamp_utc and
    # observe the validator rejecting it.
    for bad in _MALFORMED_UTC_TIMESTAMPS:
        with pytest.raises(ValueError):
            Stage29_5MigrationEvidenceRecord(
                migration_status=MIGRATION_STATUS_INVALID,
                migration_source=MIGRATION_SOURCE_HELIUS_WS,
                base_mint=_SAFE_MINT_FOR_TIMESTAMP_PIN,
                pool_account=_SAFE_POOL_FOR_TIMESTAMP_PIN,
                pool_program_id=(
                    _SAFE_PROGRAM_FOR_TIMESTAMP_PIN
                ),
                quote_mint=_SAFE_QUOTE_FOR_TIMESTAMP_PIN,
                migration_timestamp_utc=bad,
                migration_slot=None,
                migration_signature=None,
                observed_at_utc=_SAFE_OBSERVED_AT_VALID,
                source_event_ref=None,
            )


def test_safe_iso8601_utc_string_accepts_canonical_utc():
    """Positive pin: canonical Z and +00:00 forms parse cleanly,
    and ``datetime.fromisoformat`` round-trips them.
    """
    accepted = (
        "2026-05-25T00:00:00Z",
        "2026-05-25T00:00:00+00:00",
        "2026-05-25T12:34:56Z",
        "2026-05-25T12:34:56.123456+00:00",
        "2026-12-31T23:59:59Z",
        "2024-02-29T00:00:00Z",  # leap day — valid
    )
    for good in accepted:
        assert is_safe_iso8601_utc_string(good), (
            f"is_safe_iso8601_utc_string({good!r}) must be True"
        )


def test_parse_safe_utc_datetime_returns_aware_zero_offset_datetime():
    """The new strict parser returns an aware ``datetime`` whose
    tzinfo is the canonical UTC zone.
    """
    from datetime import timedelta, timezone as _tz

    parsed_z = parse_safe_utc_datetime(
        "2026-05-25T12:00:00Z"
    )
    parsed_plus = parse_safe_utc_datetime(
        "2026-05-25T12:00:00+00:00"
    )
    assert parsed_z.tzinfo is not None
    assert parsed_plus.tzinfo is not None
    assert parsed_z.utcoffset() == timedelta(0)
    assert parsed_plus.utcoffset() == timedelta(0)
    # Both representations point at the same instant.
    assert parsed_z == parsed_plus
    # Canonical tz attribute is UTC.
    assert parsed_z.tzinfo == _tz.utc
    assert parsed_plus.tzinfo == _tz.utc


def test_parse_safe_utc_datetime_rejects_non_str():
    """Non-str inputs raise ``ValueError`` rather than silently
    coercing.
    """
    for bad in (None, 0, 1.5, [], {}, b"2026-05-25T00:00:00Z"):
        with pytest.raises(ValueError):
            parse_safe_utc_datetime(bad)  # type: ignore[arg-type]
