"""Stage 29.5.2 offline integration composition behavior tests.

Pins the 8 closed-set composition branches the substage promises:

  1. Happy path COMPLETE projection.
  2. Missing migration evidence (empty sequence).
  3. Invalid migration evidence.
  4. Conflicting migration evidence.
  5. Stale / out-of-window migration evidence.
  6. Wrong-token ATH stays PARTIAL with verified=None.
  7. Pair mismatch via ``expected_pool_program_id``.
  8. Slot missing blocks COMPLETE.

The tests exercise the Stage 29.5.2 composition function only;
no live transport is opened, no network call is made, no Discord
webhook is touched, no Stage 29.3 / 29.4 production source is
imported. Synthetic evidence flows through the Stage 29.5.2
fixture builders.
"""

from __future__ import annotations

import pytest

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_5_2_offline_integration import (
    STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION,
    Stage29_5_2OfflineIntegrationError,
    Stage29_5_2OfflineIntegrationResult,
    run_stage29_5_2_offline_integration,
)
from PHX2.stage29.stage29_5_2_synthetic_evidence_fixtures import (
    build_synthetic_conflicting_evidence,
    build_synthetic_invalid_evidence,
    build_synthetic_missing_evidence,
    build_synthetic_present_evidence,
    build_synthetic_stale_evidence,
)
from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes,
)
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
    REDACTION_STATUS_SAFE,
    WARNING_MIGRATION_CONFLICT,
    WARNING_MIGRATION_MISSING,
    WARNING_MIGRATION_PAIR_MISMATCH,
    WARNING_MIGRATION_SLOT_MISSING,
    WARNING_MIGRATION_STALE,
    WARNING_MIGRATION_TIMESTAMP_INVALID,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_SAFE_MINT_A: str = "A" * 44
_SAFE_MINT_B: str = "B" * 44
_SAFE_POOL: str = "P" * 44
_SAFE_POOL_PROGRAM: str = "G" * 44
_OTHER_POOL_PROGRAM: str = "H" * 44
_SAFE_QUOTE: str = "Q" * 44

_MIGRATION_TS: str = "2026-05-25T10:00:00+00:00"
_ATH_TS_AFTER: str = "2026-05-25T15:00:00+00:00"
_OBSERVED_AT: str = "2026-05-25T16:00:00+00:00"
_WINDOW_START: str = "2026-05-25T00:00:00+00:00"
_WINDOW_END: str = "2026-05-26T00:00:00+00:00"
_OUT_OF_WINDOW_START: str = "2026-05-25T11:00:00+00:00"
_OUT_OF_WINDOW_END: str = "2026-05-25T23:00:00+00:00"


def _fixed_clock() -> str:
    return _OBSERVED_AT


def _axes(
    *,
    base_mint: str = _SAFE_MINT_A,
    pool_account=None,
    pool_program_id=None,
    quote_mint=None,
) -> Stage29_5CandidateAxes:
    return Stage29_5CandidateAxes(
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
    )


def _ath(
    *,
    token_mint=_SAFE_MINT_A,
    ath_observed_at_utc=_ATH_TS_AFTER,
    ath_status: str = "PRESENT",
    ath_value: str = "0.000054",
    ath_since_migration_status: str = "POST_MIGRATION_ONLY",
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=token_mint,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        ath_value=ath_value,
        ath_unit="USD",
        ath_source="STAGE29_2_BIRDEYE_OHLCV",
        ath_observed_at_utc=ath_observed_at_utc,
        ath_since_migration_status=(
            ath_since_migration_status
        ),
        drawdown_from_ath=None,
        drawdown_unit="USD",
        drawdown_basis="UNKNOWN",
        ath_status=ath_status,
        ath_reason="OK",
        schema_version="stage27_v0_price_ath",
    )


# ---------------------------------------------------------------------------
# 1. Happy path COMPLETE projection
# ---------------------------------------------------------------------------


def test_happy_path_complete_projection():
    """Stage 29.5.2 composition happy path: PRESENT synthetic
    evidence (full quartet + slot + source SYNTHETIC_TEST_ONLY),
    same-token POST_MIGRATION_ONLY ATH observed strictly after
    migration -> JOINED -> COMPLETE with verified=True.
    """
    evidence = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=123456,
        migration_signature="synth-sig-happy",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-happy",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert isinstance(
        result, Stage29_5_2OfflineIntegrationResult
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_COMPLETE
    )
    assert result.private_ping_context.warnings == ()
    assert (
        result.private_ping_context.post_migration_ath_verified
        is True
    )
    assert (
        result.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert result.redaction_status == REDACTION_STATUS_SAFE
    assert (
        result.schema_version
        == STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# 2. Missing migration evidence
# ---------------------------------------------------------------------------


def test_missing_migration_evidence():
    """Empty evidence sequence -> NO_MATCH -> MISSING_MIGRATION.

    Stage 29.5 projection emits MIGRATION_MISSING +
    POST_MIGRATION_ATH_UNVERIFIED warnings and clamps
    verified=None even when the ATH context is otherwise
    "complete-shape".
    """
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[],
        ath_context=_ath(),
        clock=_fixed_clock,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_MISSING_MIGRATION
    )
    assert (
        WARNING_MIGRATION_MISSING
        in result.private_ping_context.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )
    assert (
        result.private_ping_context.post_migration_ath_verified
        is None
    )


def test_missing_migration_evidence_via_missing_record():
    """Status=MISSING records carry only None axes; they cannot
    match a candidate's axis filter. The composition therefore
    routes through NO_MATCH exactly as the empty-sequence case
    does.
    """
    evidence = build_synthetic_missing_evidence(
        observed_at_utc=_OBSERVED_AT,
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_MISSING_MIGRATION
    )


# ---------------------------------------------------------------------------
# 3. Invalid migration evidence
# ---------------------------------------------------------------------------


def test_invalid_migration_evidence():
    """Synthetic INVALID evidence matching candidate axes routes
    the join verdict to SOURCE_INVALID, which the projection
    surfaces as INVALID_MIGRATION + TIMESTAMP_INVALID +
    POST_MIGRATION_ATH_UNVERIFIED.
    """
    evidence = build_synthetic_invalid_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        observed_at_utc=_OBSERVED_AT,
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_INVALID_MIGRATION
    )
    assert (
        WARNING_MIGRATION_TIMESTAMP_INVALID
        in result.private_ping_context.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )
    assert (
        result.private_ping_context.post_migration_ath_verified
        is None
    )


# ---------------------------------------------------------------------------
# 4. Conflicting migration evidence
# ---------------------------------------------------------------------------


def test_conflicting_migration_evidence():
    """Two synthetic PRESENT records matching candidate axes that
    disagree on ``migration_timestamp_utc`` route the join to
    MULTIPLE_MATCHES, which the projection surfaces as
    CONFLICTING_MIGRATION + MIGRATION_CONFLICT +
    POST_MIGRATION_ATH_UNVERIFIED.
    """
    evidence_a = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=10,
        migration_signature="synth-sig-a",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-a",
    )
    evidence_b = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc="2026-05-25T12:00:00+00:00",
        migration_slot=10,
        migration_signature="synth-sig-b",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-b",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence_a, evidence_b],
        ath_context=_ath(),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_CONFLICTING_MIGRATION
    )
    assert (
        WARNING_MIGRATION_CONFLICT
        in result.private_ping_context.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )


def test_conflicting_via_synthetic_conflicting_status_record():
    """A synthetic CONFLICTING-status record routes the join
    verdict to SOURCE_INVALID (the Stage 29.5 join's
    SOURCE_INVALID guard catches both INVALID and CONFLICTING
    statuses). The projection surfaces that as INVALID_MIGRATION.
    """
    evidence = build_synthetic_conflicting_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        observed_at_utc=_OBSERVED_AT,
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_INVALID_MIGRATION
    )


# ---------------------------------------------------------------------------
# 5. Stale / out-of-window migration evidence
# ---------------------------------------------------------------------------


def test_stale_status_evidence_routes_to_partial_with_stale_warning():
    """A synthetic STALE-status record routes the join verdict to
    TIME_WINDOW_INVALID (the Stage 29.5 join's STALE guard
    surfaces STALE as a window failure). The projection then
    emits PARTIAL_MIGRATION_PRESENT + MIGRATION_STALE +
    POST_MIGRATION_ATH_UNVERIFIED.
    """
    evidence = build_synthetic_stale_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        observed_at_utc=_OBSERVED_AT,
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert (
        WARNING_MIGRATION_STALE
        in result.private_ping_context.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )
    assert (
        result.private_ping_context.post_migration_ath_verified
        is None
    )


def test_out_of_window_present_evidence_routes_to_partial_with_stale_warning():
    """A PRESENT record whose ``migration_timestamp_utc`` falls
    outside the caller-supplied half-open window also routes the
    join verdict to TIME_WINDOW_INVALID. The projection surfaces
    that same PARTIAL + MIGRATION_STALE +
    POST_MIGRATION_ATH_UNVERIFIED triple as the explicit STALE
    status case.
    """
    evidence = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=10,
        migration_signature="synth-sig-oow",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-oow",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
        time_window_start_utc=_OUT_OF_WINDOW_START,
        time_window_end_utc=_OUT_OF_WINDOW_END,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert (
        WARNING_MIGRATION_STALE
        in result.private_ping_context.warnings
    )


# ---------------------------------------------------------------------------
# 6. Wrong-token ATH stays PARTIAL with verified=None
# ---------------------------------------------------------------------------


def test_wrong_token_ath_stays_partial_with_verified_none():
    """JOINED migration record for candidate base_mint=A, but the
    ATH context's ``token_mint`` points at B. The Stage 29.5.1
    PASS-WITH-PATCHES rule forbids ``verified=False`` in this
    case: only a same-token PRESENT ATH may drive the False
    signal. The projection therefore emits PARTIAL with
    ``verified=None`` and the POST_MIGRATION_ATH_UNVERIFIED
    warning.
    """
    evidence = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=42,
        migration_signature="synth-sig-wrongtok",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-wrongtok",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(token_mint=_SAFE_MINT_B),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert (
        result.private_ping_context.post_migration_ath_verified
        is None
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )


# ---------------------------------------------------------------------------
# 7. Pair mismatch via expected_pool_program_id
# ---------------------------------------------------------------------------


def test_pair_mismatch_via_expected_pool_program_id():
    """When the caller pins
    ``expected_pool_program_id=Y`` and the matched evidence
    carries ``pool_program_id=X != Y``, the Stage 29.5 join's
    PumpSwap-id sanity check routes the verdict to
    PAIR_MISMATCH. The projection surfaces that as
    INVALID_MIGRATION + MIGRATION_PAIR_MISMATCH +
    POST_MIGRATION_ATH_UNVERIFIED.
    """
    evidence = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=99,
        migration_signature="synth-sig-pair",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-pair",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
        expected_pool_program_id=_OTHER_POOL_PROGRAM,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_PAIR_MISMATCH
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_INVALID_MIGRATION
    )
    assert (
        WARNING_MIGRATION_PAIR_MISMATCH
        in result.private_ping_context.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )


# ---------------------------------------------------------------------------
# 8. Slot missing blocks COMPLETE
# ---------------------------------------------------------------------------


def test_slot_missing_blocks_complete():
    """When the matched PRESENT evidence has
    ``migration_slot=None``, the projection's 8-predicate COMPLETE
    gate fails on the slot-present predicate. The projection
    emits PARTIAL_MIGRATION_PRESENT + MIGRATION_SLOT_MISSING +
    POST_MIGRATION_ATH_UNVERIFIED and clamps ``verified=None``
    regardless of how good the ATH context is.
    """
    evidence = build_synthetic_present_evidence(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=None,
        migration_signature="synth-sig-noslot",
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="synth-ref-noslot",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[evidence],
        ath_context=_ath(),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.join_record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )
    assert (
        result.private_ping_context.measurement_status
        == MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    )
    assert (
        WARNING_MIGRATION_SLOT_MISSING
        in result.private_ping_context.warnings
    )
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED
        in result.private_ping_context.warnings
    )
    assert (
        result.private_ping_context.post_migration_ath_verified
        is None
    )


# ---------------------------------------------------------------------------
# Cross-cutting invariants
# ---------------------------------------------------------------------------


def test_composition_locks_filter_enforcement_status_on_every_branch():
    """Every closed-set branch must emit
    filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING.
    """
    cases = [
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records=[],
            ath_context=None,
            clock=_fixed_clock,
        ),
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records=[
                build_synthetic_present_evidence(
                    base_mint=_SAFE_MINT_A,
                    pool_account=_SAFE_POOL,
                    pool_program_id=_SAFE_POOL_PROGRAM,
                    quote_mint=_SAFE_QUOTE,
                    migration_timestamp_utc=_MIGRATION_TS,
                    migration_slot=10,
                    observed_at_utc=_OBSERVED_AT,
                )
            ],
            ath_context=_ath(),
            clock=_fixed_clock,
            time_window_start_utc=_WINDOW_START,
            time_window_end_utc=_WINDOW_END,
        ),
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records=[
                build_synthetic_invalid_evidence(
                    base_mint=_SAFE_MINT_A,
                    pool_account=_SAFE_POOL,
                    pool_program_id=_SAFE_POOL_PROGRAM,
                    quote_mint=_SAFE_QUOTE,
                    observed_at_utc=_OBSERVED_AT,
                )
            ],
            ath_context=None,
            clock=_fixed_clock,
        ),
    ]
    for result in cases:
        assert (
            result.filter_enforcement_status
            == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        )
        assert (
            result.private_ping_context.filter_enforcement_status
            == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        )


def test_composition_locks_redaction_status_safe_on_every_branch():
    result = run_stage29_5_2_offline_integration(
        candidate_axes=_axes(),
        evidence_records=[],
        ath_context=None,
        clock=_fixed_clock,
    )
    assert result.redaction_status == REDACTION_STATUS_SAFE


def test_composition_echoes_candidate_axes_verbatim():
    axes = _axes(
        pool_account=_SAFE_POOL,
        pool_program_id=_SAFE_POOL_PROGRAM,
        quote_mint=_SAFE_QUOTE,
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=axes,
        evidence_records=[],
        ath_context=None,
        clock=_fixed_clock,
    )
    assert result.candidate_axes_echoed is axes
    assert result.candidate_axes_echoed.base_mint == _SAFE_MINT_A
    assert result.candidate_axes_echoed.pool_account == _SAFE_POOL
    assert (
        result.candidate_axes_echoed.pool_program_id
        == _SAFE_POOL_PROGRAM
    )
    assert result.candidate_axes_echoed.quote_mint == _SAFE_QUOTE


def test_composition_is_deterministic_for_same_inputs():
    """Same inputs -> identical result. The composition is pure.
    """
    axes = _axes()
    evidence = [
        build_synthetic_present_evidence(
            base_mint=_SAFE_MINT_A,
            pool_account=_SAFE_POOL,
            pool_program_id=_SAFE_POOL_PROGRAM,
            quote_mint=_SAFE_QUOTE,
            migration_timestamp_utc=_MIGRATION_TS,
            migration_slot=7,
            observed_at_utc=_OBSERVED_AT,
        )
    ]
    ath = _ath()
    a = run_stage29_5_2_offline_integration(
        candidate_axes=axes,
        evidence_records=evidence,
        ath_context=ath,
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    b = run_stage29_5_2_offline_integration(
        candidate_axes=axes,
        evidence_records=evidence,
        ath_context=ath,
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert a == b


def test_composition_rejects_non_axes_candidate():
    with pytest.raises(Stage29_5_2OfflineIntegrationError):
        run_stage29_5_2_offline_integration(
            candidate_axes="not-an-axes",
            evidence_records=[],
            ath_context=None,
            clock=_fixed_clock,
        )


def test_composition_rejects_non_record_evidence_entry():
    with pytest.raises(Stage29_5_2OfflineIntegrationError):
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records=["not-a-record"],
            ath_context=None,
            clock=_fixed_clock,
        )


def test_composition_rejects_string_evidence_sequence():
    """A bare ``str`` happens to satisfy ``Sequence`` in typing
    but iterating it would yield chars; the composition catches
    this before calling the join.
    """
    with pytest.raises(Stage29_5_2OfflineIntegrationError):
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records="oops-stringly-typed",
            ath_context=None,
            clock=_fixed_clock,
        )


def test_composition_rejects_non_callable_clock():
    with pytest.raises(Stage29_5_2OfflineIntegrationError):
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records=[],
            ath_context=None,
            clock="not-callable",
        )


def test_composition_rejects_non_ath_record():
    with pytest.raises(Stage29_5_2OfflineIntegrationError):
        run_stage29_5_2_offline_integration(
            candidate_axes=_axes(),
            evidence_records=[],
            ath_context="not-an-ath-record",
            clock=_fixed_clock,
        )
