"""Stage 29.5.7 model-layer tests: helpers, vocab, dataclasses."""

from __future__ import annotations

from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    CREATE_POOL_ACCOUNT_INDEX_BASE_MINT,
    CREATE_POOL_ACCOUNT_INDEX_POOL,
    CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT,
    NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
    REJECT_REASON_NONE,
    STAGE29_5_7_FAIL_CLOSED_REJECT_REASONS,
    STAGE29_5_7_MEASUREMENT_STATUS_COMPLETE,
    STAGE29_5_7_NORMALIZATION_OUTCOME_VALUES,
    STAGE29_5_7_REDACTION_STATUS_SAFE,
    STAGE29_5_7_REJECT_REASON_VALUES,
    Stage29_5_7MigrationNormalizationResult,
    Stage29_5_7SanitizedMigrationEvidenceSummary,
    build_source_ref,
    epoch_seconds_to_trailing_z_utc,
    is_nonblank_str,
    is_nonneg_int,
    is_stage29_5_7_normalization_outcome_value,
    is_stage29_5_7_reject_reason_value,
    is_trailing_z_utc_shape,
    normalization_result_field_names,
    sanitized_summary_field_names,
)


# ---------------------------------------------------------------------------
# epoch -> trailing-Z formatter
# ---------------------------------------------------------------------------


def test_epoch_zero_is_unix_epoch() -> None:
    assert epoch_seconds_to_trailing_z_utc(0) == "1970-01-01T00:00:00Z"


def test_epoch_known_instant() -> None:
    assert (
        epoch_seconds_to_trailing_z_utc(1716768000)
        == "2024-05-27T00:00:00Z"
    )


def test_epoch_hms_components() -> None:
    # 1716768000 + 1h 1m 1s
    assert (
        epoch_seconds_to_trailing_z_utc(1716768000 + 3661)
        == "2024-05-27T01:01:01Z"
    )


def test_epoch_always_trailing_z_never_offset() -> None:
    out = epoch_seconds_to_trailing_z_utc(1716768000)
    assert out is not None
    assert out.endswith("Z")
    assert "+00:00" not in out
    assert is_trailing_z_utc_shape(out)


def test_epoch_rejects_bool_negative_and_nonint() -> None:
    assert epoch_seconds_to_trailing_z_utc(True) is None
    assert epoch_seconds_to_trailing_z_utc(False) is None
    assert epoch_seconds_to_trailing_z_utc(-1) is None
    assert epoch_seconds_to_trailing_z_utc("1716768000") is None
    assert epoch_seconds_to_trailing_z_utc(1716768000.0) is None
    assert epoch_seconds_to_trailing_z_utc(None) is None


def test_epoch_leap_day() -> None:
    # 2024-02-29 is a real leap day.
    # 1709164800 == 2024-02-29T00:00:00Z
    assert (
        epoch_seconds_to_trailing_z_utc(1709164800)
        == "2024-02-29T00:00:00Z"
    )


# ---------------------------------------------------------------------------
# trailing-Z shape predicate
# ---------------------------------------------------------------------------


def test_trailing_z_shape_accepts_z() -> None:
    assert is_trailing_z_utc_shape("2024-05-27T00:00:00Z")
    assert is_trailing_z_utc_shape("2024-05-27T00:00:00.123Z")
    assert is_trailing_z_utc_shape("2024-02-29T23:59:59Z")


def test_trailing_z_shape_rejects_offset_and_naive() -> None:
    assert not is_trailing_z_utc_shape("2024-05-27T00:00:00+00:00")
    assert not is_trailing_z_utc_shape("2024-05-27T00:00:00")
    assert not is_trailing_z_utc_shape("2024-05-27 00:00:00Z")


def test_trailing_z_shape_rejects_impossible_calendar() -> None:
    assert not is_trailing_z_utc_shape("2024-13-01T00:00:00Z")
    assert not is_trailing_z_utc_shape("2024-00-01T00:00:00Z")
    assert not is_trailing_z_utc_shape("2024-02-30T00:00:00Z")
    assert not is_trailing_z_utc_shape("2023-02-29T00:00:00Z")  # not a leap year
    assert not is_trailing_z_utc_shape("2024-05-27T24:00:00Z")
    assert not is_trailing_z_utc_shape("2024-05-27T00:60:00Z")
    assert not is_trailing_z_utc_shape("2024-05-27T00:00:60Z")


def test_trailing_z_shape_rejects_nonstring() -> None:
    assert not is_trailing_z_utc_shape(None)
    assert not is_trailing_z_utc_shape(1716768000)
    assert not is_trailing_z_utc_shape("")


# ---------------------------------------------------------------------------
# safe-shape helpers
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("x")
    assert not is_nonblank_str("")
    assert not is_nonblank_str("   ")
    assert not is_nonblank_str(None)
    assert not is_nonblank_str(5)


def test_is_nonneg_int() -> None:
    assert is_nonneg_int(0)
    assert is_nonneg_int(333444555)
    assert not is_nonneg_int(-1)
    assert not is_nonneg_int(True)
    assert not is_nonneg_int(False)
    assert not is_nonneg_int(1.0)
    assert not is_nonneg_int("5")


def test_build_source_ref() -> None:
    assert build_source_ref("abc", 42) == "helius:sig:abc:slot:42"


# ---------------------------------------------------------------------------
# closed-set vocab
# ---------------------------------------------------------------------------


def test_normalization_outcome_values() -> None:
    assert is_stage29_5_7_normalization_outcome_value(
        NORMALIZATION_OUTCOME_MIGRATION_PROVEN
    )
    assert not is_stage29_5_7_normalization_outcome_value("NOPE")
    assert len(STAGE29_5_7_NORMALIZATION_OUTCOME_VALUES) == 2


def test_reject_reason_values() -> None:
    assert is_stage29_5_7_reject_reason_value(REJECT_REASON_NONE)
    assert not is_stage29_5_7_reject_reason_value("NOPE")
    # NONE is the only non-fail-closed reason.
    assert REJECT_REASON_NONE not in STAGE29_5_7_FAIL_CLOSED_REJECT_REASONS
    assert (
        len(STAGE29_5_7_FAIL_CLOSED_REJECT_REASONS)
        == len(STAGE29_5_7_REJECT_REASON_VALUES) - 1
    )


def test_mirrored_output_tokens() -> None:
    assert STAGE29_5_7_MEASUREMENT_STATUS_COMPLETE == "COMPLETE"
    assert STAGE29_5_7_REDACTION_STATUS_SAFE == "SAFE"


def test_idl_account_positions() -> None:
    assert CREATE_POOL_ACCOUNT_INDEX_POOL == 0
    assert CREATE_POOL_ACCOUNT_INDEX_BASE_MINT == 3
    assert CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT == 4


# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


def test_sanitized_summary_fail_closed_defaults() -> None:
    summary = Stage29_5_7SanitizedMigrationEvidenceSummary()
    assert summary.token_mint is None
    assert summary.measurement_status is None
    assert summary.migration_event_time_utc is None
    assert summary.warnings is None  # fail-closed sentinel (missing != "no warnings")
    assert summary.redaction_status is None
    assert summary.source_ref is None


def test_sanitized_summary_field_names_mirror_stage_30_11_9_by_value() -> None:
    # The field NAMES must equal the Stage 30.11.9 evidence record field names so
    # the committed mapper/confirmation read it duck-typed.
    assert sanitized_summary_field_names() == (
        "token_mint",
        "measurement_status",
        "migration_event_time_utc",
        "warnings",
        "redaction_status",
        "source_ref",
    )


def test_normalization_result_shape() -> None:
    result = Stage29_5_7MigrationNormalizationResult(
        outcome=NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
        reject_reason=REJECT_REASON_NONE,
        evidence_record=None,
    )
    assert result.pumpswap_instruction_count == 0
    assert result.create_pool_match_count == 0
    assert "outcome" in normalization_result_field_names()
