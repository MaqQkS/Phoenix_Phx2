"""Stage 29.5 private ping migration context projection tests.

Pins all 5 ``measurement_status`` branches + the warning-code
rules:

  * NO_MATCH join => MISSING_MIGRATION measurement +
    (MIGRATION_MISSING, POST_MIGRATION_ATH_UNVERIFIED) warnings.
  * MULTIPLE_MATCHES => CONFLICTING_MIGRATION + (CONFLICT,
    UNVERIFIED).
  * SOURCE_INVALID => INVALID_MIGRATION + (TIMESTAMP_INVALID,
    UNVERIFIED).
  * PAIR_MISMATCH => INVALID_MIGRATION + (PAIR_MISMATCH,
    UNVERIFIED).
  * TIME_WINDOW_INVALID => PARTIAL_MIGRATION_PRESENT + (STALE,
    UNVERIFIED).
  * JOINED + slot present + ATH window post-migration =>
    COMPLETE + no warnings, post_migration_ath_verified=True.
  * JOINED + slot present + ATH window NOT post-migration =>
    PARTIAL_MIGRATION_PRESENT + (UNVERIFIED).
  * JOINED + slot missing => PARTIAL_MIGRATION_PRESENT +
    (SLOT_MISSING).
  * Unknown migration_source => warning MIGRATION_SOURCE_UNKNOWN
    appended.
  * filter_enforcement_status locked to
    NOT_ACTIVE_STAGE_29_PENDING verbatim.
"""

from __future__ import annotations

import pytest

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes,
    join_candidate_to_migration_evidence,
)
from PHX2.stage29.stage29_5_migration_models import (
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_PRESENT,
    REDACTION_STATUS_SAFE,
    Stage29_5MigrationEvidenceRecord,
    Stage29_5MigrationJoinRecord,
    WARNING_MIGRATION_CONFLICT,
    WARNING_MIGRATION_MISSING,
    WARNING_MIGRATION_PAIR_MISMATCH,
    WARNING_MIGRATION_SLOT_MISSING,
    WARNING_MIGRATION_SOURCE_UNKNOWN,
    WARNING_MIGRATION_STALE,
    WARNING_MIGRATION_TIMESTAMP_INVALID,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
)
from PHX2.stage29.stage29_5_private_ping_context_projection import (
    project_private_ping_migration_context,
)


# ---------------------------------------------------------------------------
# Fake fixtures
# ---------------------------------------------------------------------------


_SAFE_MINT_A: str = "A" * 44
_SAFE_POOL_A: str = "P" * 44
_PUMPSWAP_PROGRAM_ID: str = (
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)
_OTHER_PROGRAM_ID: str = "X" * 44
_SAFE_QUOTE: str = "S" * 44
_MIGRATION_TS: str = "2026-05-25T10:00:00+00:00"
_ATH_TS_AFTER: str = "2026-05-25T15:00:00+00:00"
_ATH_TS_BEFORE: str = "2026-05-25T09:00:00+00:00"
_WINDOW_START: str = "2026-05-25T00:00:00+00:00"
_WINDOW_END: str = "2026-05-26T00:00:00+00:00"
_OUT_OF_WINDOW_TS: str = "2026-05-26T01:00:00+00:00"
_OBSERVED_AT: str = "2026-05-25T16:00:00+00:00"


def _fixed_clock() -> str:
    return _OBSERVED_AT


def _present_evidence(
    *,
    slot=123456,
    source: str = MIGRATION_SOURCE_HELIUS_WS,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=source,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=slot,
        migration_signature="synth-sig-A",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-A",
    )


def _ath_context(
    ath_observed_at_utc: str | None,
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=_SAFE_MINT_A,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        ath_value="0.000054",
        ath_unit="USD",
        ath_source="STAGE29_2_BIRDEYE_OHLCV",
        ath_observed_at_utc=ath_observed_at_utc,
        ath_since_migration_status="UNKNOWN",
        drawdown_from_ath=None,
        drawdown_unit="USD",
        drawdown_basis="UNKNOWN",
        ath_status="PRESENT",
        ath_reason="OK",
        schema_version="stage27_v0_price_ath",
    )


def _axes() -> Stage29_5CandidateAxes:
    return Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)


def _join(
    *records: Stage29_5MigrationEvidenceRecord,
    expected_pool_program_id: str | None = None,
    window_start_utc: str | None = None,
    window_end_utc: str | None = None,
) -> Stage29_5MigrationJoinRecord:
    return join_candidate_to_migration_evidence(
        candidate_axes=_axes(),
        evidence_records=records,
        clock=_fixed_clock,
        time_window_start_utc=window_start_utc,
        time_window_end_utc=window_end_utc,
        expected_pool_program_id=expected_pool_program_id,
    )


# ---------------------------------------------------------------------------
# NO_MATCH branch
# ---------------------------------------------------------------------------


def test_no_match_yields_missing_migration():
    join = _join()
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_MISSING_MIGRATION
    )
    assert WARNING_MIGRATION_MISSING in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is None
    assert (
        ctx.migration_source
        == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    )
    # unknown source layered in => MIGRATION_SOURCE_UNKNOWN
    assert (
        WARNING_MIGRATION_SOURCE_UNKNOWN in ctx.warnings
    )


# ---------------------------------------------------------------------------
# JOINED + COMPLETE branch
# ---------------------------------------------------------------------------


def test_joined_with_slot_and_ath_post_migration_yields_complete():
    join = _join(_present_evidence())
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert ctx.measurement_status == MEASUREMENT_STATUS_COMPLETE
    assert ctx.warnings == ()
    assert ctx.post_migration_ath_verified is True
    assert ctx.migration_source == MIGRATION_SOURCE_HELIUS_WS
    assert (
        ctx.join_status_echoed == MIGRATION_JOIN_STATUS_JOINED
    )


def test_joined_with_slot_and_ath_before_migration_yields_partial():
    join = _join(_present_evidence())
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_BEFORE),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is False


def test_joined_with_slot_and_no_ath_context_yields_partial():
    join = _join(_present_evidence())
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=None,
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is None


def test_joined_with_slot_missing_yields_partial_with_slot_warning():
    join = _join(_present_evidence(slot=None))
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert WARNING_MIGRATION_SLOT_MISSING in ctx.warnings
    # ATH after migration but slot missing => verified=True
    assert ctx.post_migration_ath_verified is True


def test_joined_with_slot_missing_and_ath_before_yields_two_warnings():
    join = _join(_present_evidence(slot=None))
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_BEFORE),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert WARNING_MIGRATION_SLOT_MISSING in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )


# ---------------------------------------------------------------------------
# MULTIPLE_MATCHES branch
# ---------------------------------------------------------------------------


def test_multiple_matches_yields_conflicting_migration():
    e1 = _present_evidence(slot=1)
    e2 = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=2,  # disagrees with e1
        migration_signature="synth-sig-B",
        observed_at_utc="2026-05-25T16:30:00+00:00",
        source_event_ref="synth-ref-B",
    )
    join = _join(e1, e2)
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_CONFLICTING_MIGRATION
    )
    assert WARNING_MIGRATION_CONFLICT in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is None


# ---------------------------------------------------------------------------
# SOURCE_INVALID branch
# ---------------------------------------------------------------------------


def test_source_invalid_yields_invalid_migration():
    invalid = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    join = _join(invalid)
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_INVALID_MIGRATION
    )
    assert (
        WARNING_MIGRATION_TIMESTAMP_INVALID in ctx.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is None


# ---------------------------------------------------------------------------
# PAIR_MISMATCH branch
# ---------------------------------------------------------------------------


def test_pair_mismatch_yields_invalid_migration():
    ev = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_OTHER_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=1,
        migration_signature="synth-sig-A",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    join = _join(
        ev, expected_pool_program_id=_PUMPSWAP_PROGRAM_ID
    )
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_INVALID_MIGRATION
    )
    assert WARNING_MIGRATION_PAIR_MISMATCH in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is None


# ---------------------------------------------------------------------------
# TIME_WINDOW_INVALID branch
# ---------------------------------------------------------------------------


def test_time_window_invalid_yields_partial_with_stale_warning():
    ev = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_OUT_OF_WINDOW_TS,
        migration_slot=1,
        migration_signature="synth-sig-A",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    join = _join(
        ev,
        window_start_utc=_WINDOW_START,
        window_end_utc=_WINDOW_END,
    )
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert WARNING_MIGRATION_STALE in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )
    assert ctx.post_migration_ath_verified is None


# ---------------------------------------------------------------------------
# Source warning rules
# ---------------------------------------------------------------------------


def test_unknown_source_appends_source_unknown_warning():
    # NO_MATCH inherently carries the UNKNOWN source. Test that
    # the warning is appended even on a JOINED record when the
    # primary evidence carries UNKNOWN — which the
    # Stage29_5MigrationEvidenceRecord validator rejects for
    # PRESENT. So this scenario requires us to construct a
    # JOINED with all-invalid evidence... not possible. Instead
    # verify on NO_MATCH which always sets UNKNOWN source.
    join = _join()
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        WARNING_MIGRATION_SOURCE_UNKNOWN in ctx.warnings
    )


def test_known_source_does_not_append_source_unknown_warning():
    join = _join(_present_evidence())
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        WARNING_MIGRATION_SOURCE_UNKNOWN
        not in ctx.warnings
    )


def test_artifact_source_carries_artifact_source_token():
    join = _join(
        _present_evidence(
            source=MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
        )
    )
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.migration_source
        == MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
    )


# ---------------------------------------------------------------------------
# Field locks
# ---------------------------------------------------------------------------


def test_projection_always_locks_filter_enforcement_status():
    join = _join(_present_evidence())
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert (
        ctx.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_projection_always_locks_redaction_status_safe():
    join = _join(_present_evidence())
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert ctx.redaction_status == REDACTION_STATUS_SAFE


def test_projection_echoes_join_status():
    join = _join()
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=None,
        clock=_fixed_clock,
    )
    assert (
        ctx.join_status_echoed
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )


def test_projection_observed_at_uses_injected_clock():
    join = _join()

    def custom_clock() -> str:
        return "2026-05-25T20:00:00+00:00"

    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=None,
        clock=custom_clock,
    )
    assert (
        ctx.observed_at_utc == "2026-05-25T20:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_projection_rejects_non_join_record():
    with pytest.raises(ValueError):
        project_private_ping_migration_context(
            join_record="not-a-record",  # type: ignore[arg-type]
            ath_context=None,
            clock=_fixed_clock,
        )


def test_projection_rejects_non_ath_record():
    join = _join()
    with pytest.raises(ValueError):
        project_private_ping_migration_context(
            join_record=join,
            ath_context="not-ath",  # type: ignore[arg-type]
            clock=_fixed_clock,
        )


def test_projection_rejects_non_callable_clock():
    join = _join()
    with pytest.raises(ValueError):
        project_private_ping_migration_context(
            join_record=join,
            ath_context=None,
            clock="not-callable",  # type: ignore[arg-type]
        )


def test_projection_rejects_bad_clock_output():
    join = _join()

    def bad_clock() -> str:
        return "2026-05-25"

    with pytest.raises(ValueError):
        project_private_ping_migration_context(
            join_record=join,
            ath_context=None,
            clock=bad_clock,
        )


def test_projection_deterministic_for_same_input():
    join = _join(_present_evidence())
    a = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    b = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_AFTER),
        clock=_fixed_clock,
    )
    assert a == b


def test_projection_warnings_are_deterministic_dedup_ordered():
    """When two branches independently request
    POST_MIGRATION_ATH_UNVERIFIED, the warning appears once.
    """
    join = _join(_present_evidence(slot=None))
    ctx = project_private_ping_migration_context(
        join_record=join,
        ath_context=_ath_context(_ATH_TS_BEFORE),
        clock=_fixed_clock,
    )
    # SLOT_MISSING + POST_MIGRATION_ATH_UNVERIFIED (each once)
    count_unverified = sum(
        1
        for w in ctx.warnings
        if w == WARNING_POST_MIGRATION_ATH_UNVERIFIED
    )
    assert count_unverified == 1
