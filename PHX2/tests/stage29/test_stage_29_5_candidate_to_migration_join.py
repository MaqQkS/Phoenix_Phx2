"""Stage 29.5 candidate-to-migration join tests.

Pins all 6 ``migration_join_status`` branches:

  * ``NO_MATCH``           -- no record matches the candidate
                              axes.
  * ``JOINED``             -- one record matches, axes complete,
                              timestamp inside the window.
  * ``JOINED`` (multi)     -- multiple records that AGREE on
                              core axes collapse to JOINED with
                              ``matched_evidence_count = N``.
  * ``MULTIPLE_MATCHES``   -- multiple records that DISAGREE on
                              core axes.
  * ``SOURCE_INVALID``     -- a matched record has incomplete
                              required axes.
  * ``TIME_WINDOW_INVALID``-- matched record's timestamp falls
                              outside the caller window.
  * ``PAIR_MISMATCH``      -- matched record's
                              ``pool_program_id`` disagrees with
                              the caller-supplied expected
                              PumpSwap program id.

Plus determinism and time-window semantics.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes,
    join_candidate_to_migration_evidence,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_PAIR_MISMATCH,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_CONFLICTING,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_STALE,
    Stage29_5MigrationEvidenceRecord,
)


# ---------------------------------------------------------------------------
# Fake fixtures
# ---------------------------------------------------------------------------


_SAFE_MINT_A: str = "A" * 44
_SAFE_MINT_B: str = "B" * 44
_SAFE_POOL_A: str = "P" * 44
_SAFE_POOL_B: str = "Q" * 44
_PUMPSWAP_PROGRAM_ID: str = (
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)
_OTHER_PROGRAM_ID: str = "X" * 44
_SAFE_QUOTE: str = "S" * 44
_TIMESTAMP_INSIDE: str = "2026-05-25T10:00:00+00:00"
_TIMESTAMP_BEFORE_WINDOW: str = (
    "2026-05-24T23:59:59+00:00"
)
_TIMESTAMP_AFTER_WINDOW: str = (
    "2026-05-26T00:00:01+00:00"
)
_WINDOW_START: str = "2026-05-25T00:00:00+00:00"
_WINDOW_END: str = "2026-05-26T00:00:00+00:00"
_OBSERVED_AT: str = "2026-05-25T12:00:00+00:00"
_OBSERVED_AT_LATER: str = "2026-05-25T13:00:00+00:00"


def _fixed_clock() -> str:
    return _OBSERVED_AT


def _evidence_present(
    *,
    base_mint: str = _SAFE_MINT_A,
    pool_account: str = _SAFE_POOL_A,
    pool_program_id: str = _PUMPSWAP_PROGRAM_ID,
    quote_mint: str = _SAFE_QUOTE,
    timestamp: str = _TIMESTAMP_INSIDE,
    slot: int = 123456,
    signature: str = "synth-sig-A",
    source: str = MIGRATION_SOURCE_HELIUS_WS,
    observed_at_utc: str = _OBSERVED_AT,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=source,
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
        migration_timestamp_utc=timestamp,
        migration_slot=slot,
        migration_signature=signature,
        observed_at_utc=observed_at_utc,
        source_event_ref="synth-ref-A",
    )


def _evidence_invalid_axes(
    *,
    base_mint: str = _SAFE_MINT_A,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=base_mint,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )


# ---------------------------------------------------------------------------
# Stage29_5CandidateAxes
# ---------------------------------------------------------------------------


def test_candidate_axes_constructed_with_all_axes():
    axes = Stage29_5CandidateAxes(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
    )
    assert axes.base_mint == _SAFE_MINT_A


def test_candidate_axes_rejects_unsafe_base_mint():
    with pytest.raises(ValueError):
        Stage29_5CandidateAxes(base_mint="short")


def test_candidate_axes_rejects_unsafe_optional_axis():
    with pytest.raises(ValueError):
        Stage29_5CandidateAxes(
            base_mint=_SAFE_MINT_A,
            pool_account="short",
        )


def test_candidate_axes_immutable():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    with pytest.raises(AttributeError):
        axes.base_mint = _SAFE_MINT_B  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NO_MATCH
# ---------------------------------------------------------------------------


def test_no_records_yields_no_match():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )
    assert record.matched_evidence_count == 0
    assert record.matched_evidence == ()


def test_unrelated_records_yields_no_match():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    other = _evidence_present(base_mint=_SAFE_MINT_B)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(other,),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )


# ---------------------------------------------------------------------------
# JOINED (single match, no window)
# ---------------------------------------------------------------------------


def test_single_match_no_window_joined():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(_evidence_present(),),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )
    assert record.matched_evidence_count == 1


def test_single_match_within_window_joined():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(_evidence_present(),),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


def test_candidate_with_full_axes_joins_matching_record():
    axes = Stage29_5CandidateAxes(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(_evidence_present(),),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


# ---------------------------------------------------------------------------
# JOINED (multiple matches that agree)
# ---------------------------------------------------------------------------


def test_multiple_matches_that_agree_collapse_to_joined():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev1 = _evidence_present(
        observed_at_utc=_OBSERVED_AT
    )
    ev2 = _evidence_present(
        observed_at_utc=_OBSERVED_AT_LATER,
        signature="synth-sig-B",
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )
    assert record.matched_evidence_count == 2


# ---------------------------------------------------------------------------
# MULTIPLE_MATCHES (matches that disagree)
# ---------------------------------------------------------------------------


def test_matches_disagree_on_timestamp_yields_multiple_matches():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev1 = _evidence_present(
        timestamp="2026-05-25T10:00:00+00:00"
    )
    ev2 = _evidence_present(
        timestamp="2026-05-25T11:00:00+00:00",
        signature="synth-sig-B",
        observed_at_utc=_OBSERVED_AT_LATER,
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )


def test_matches_disagree_on_slot_yields_multiple_matches():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev1 = _evidence_present(slot=1)
    ev2 = _evidence_present(
        slot=2,
        signature="synth-sig-B",
        observed_at_utc=_OBSERVED_AT_LATER,
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )


def test_matches_disagree_on_source_yields_multiple_matches():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev1 = _evidence_present(source=MIGRATION_SOURCE_HELIUS_WS)
    ev2 = _evidence_present(
        source=(
            MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
        ),
        signature="synth-sig-B",
        observed_at_utc=_OBSERVED_AT_LATER,
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )


# ---------------------------------------------------------------------------
# SOURCE_INVALID
# ---------------------------------------------------------------------------


def test_invalid_evidence_yields_source_invalid():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(_evidence_invalid_axes(),),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )


def test_invalid_with_present_present_does_not_promote_to_joined():
    """Stage 29.5.1 remediation: pre-remediation this join used
    to silently promote PRESENT + INVALID to JOINED on the
    grounds that at least one match was complete. The Codex
    audit demanded that an INVALID matched record never be
    hidden by a co-matched PRESENT record, so the join now
    routes to SOURCE_INVALID.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(
            _evidence_invalid_axes(),
            _evidence_present(),
        ),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )


# ---------------------------------------------------------------------------
# TIME_WINDOW_INVALID
# ---------------------------------------------------------------------------


def test_match_before_window_yields_time_window_invalid():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(
        timestamp=_TIMESTAMP_BEFORE_WINDOW
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )


def test_match_at_window_end_excluded_yields_time_window_invalid():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(timestamp=_WINDOW_END)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    # half-open window: end is exclusive.
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )


def test_match_at_window_start_inclusive_yields_joined():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(timestamp=_WINDOW_START)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


def test_match_after_window_yields_time_window_invalid():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(timestamp=_TIMESTAMP_AFTER_WINDOW)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )


def test_open_window_admits_any_timestamp():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(timestamp=_TIMESTAMP_AFTER_WINDOW)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


# ---------------------------------------------------------------------------
# PAIR_MISMATCH
# ---------------------------------------------------------------------------


def test_program_id_disagree_yields_pair_mismatch():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(
        pool_program_id=_OTHER_PROGRAM_ID
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
        expected_pool_program_id=_PUMPSWAP_PROGRAM_ID,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_PAIR_MISMATCH
    )


def test_program_id_agree_yields_joined():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev = _evidence_present(
        pool_program_id=_PUMPSWAP_PROGRAM_ID
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
        expected_pool_program_id=_PUMPSWAP_PROGRAM_ID,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


def test_candidate_pool_program_id_disagree_filtered_out_yields_no_match():
    axes = Stage29_5CandidateAxes(
        base_mint=_SAFE_MINT_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
    )
    ev = _evidence_present(
        pool_program_id=_OTHER_PROGRAM_ID
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev,),
        clock=_fixed_clock,
    )
    # The candidate supplied pool_program_id; the filter step
    # excluded the unmatching record so the verdict is NO_MATCH.
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )


# ---------------------------------------------------------------------------
# Wildcard semantics
# ---------------------------------------------------------------------------


def test_candidate_with_only_base_mint_matches_full_record():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(_evidence_present(),),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


def test_candidate_pool_account_must_match_when_supplied():
    axes = Stage29_5CandidateAxes(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_B,
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(_evidence_present(),),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_inputs_yield_same_output():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev1 = _evidence_present(observed_at_utc=_OBSERVED_AT)
    ev2 = _evidence_present(
        observed_at_utc=_OBSERVED_AT_LATER,
        signature="synth-sig-B",
    )
    a = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),
        clock=_fixed_clock,
    )
    b = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),
        clock=_fixed_clock,
    )
    assert a == b


def test_matched_evidence_sorted_deterministically():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    ev1 = _evidence_present(
        observed_at_utc=_OBSERVED_AT_LATER,
        signature="synth-sig-B",
    )
    ev2 = _evidence_present(
        observed_at_utc=_OBSERVED_AT, signature="synth-sig-A"
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(ev1, ev2),  # swapped on input
        clock=_fixed_clock,
    )
    # output is sorted by observed_at_utc ascending
    assert (
        record.matched_evidence[0].observed_at_utc
        == _OBSERVED_AT
    )
    assert (
        record.matched_evidence[1].observed_at_utc
        == _OBSERVED_AT_LATER
    )


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_join_rejects_non_axes_argument():
    with pytest.raises(ValueError):
        join_candidate_to_migration_evidence(
            candidate_axes="not-axes",  # type: ignore[arg-type]
            evidence_records=(),
            clock=_fixed_clock,
        )


def test_join_rejects_non_callable_clock():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    with pytest.raises(ValueError):
        join_candidate_to_migration_evidence(
            candidate_axes=axes,
            evidence_records=(),
            clock="not-callable",  # type: ignore[arg-type]
        )


def test_join_rejects_bad_window_start():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    with pytest.raises(ValueError):
        join_candidate_to_migration_evidence(
            candidate_axes=axes,
            evidence_records=(),
            clock=_fixed_clock,
            time_window_start_utc="2026-05-25",
        )


def test_join_rejects_non_record_in_evidence():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    with pytest.raises(ValueError):
        join_candidate_to_migration_evidence(
            candidate_axes=axes,
            evidence_records=("not-a-record",),  # type: ignore[arg-type]
            clock=_fixed_clock,
        )


def test_join_rejects_bad_clock_output():
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)

    def bad_clock() -> str:
        return "2026-05-25"

    with pytest.raises(ValueError):
        join_candidate_to_migration_evidence(
            candidate_axes=axes,
            evidence_records=(),
            clock=bad_clock,
        )


def test_join_skips_records_with_none_base_mint():
    """Evidence whose ``base_mint`` is None can never match a
    candidate (which always supplies a non-None base_mint), so
    a MISSING evidence record is silently filtered out.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    missing = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    record = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(missing,),
        clock=_fixed_clock,
    )
    assert (
        record.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    )


# ---------------------------------------------------------------------------
# Stage 29.5.1 remediation: stricter join semantics
# ---------------------------------------------------------------------------


def _evidence_stale(
    *,
    base_mint: str = _SAFE_MINT_A,
    pool_account: str = _SAFE_POOL_A,
    pool_program_id: str = _PUMPSWAP_PROGRAM_ID,
    quote_mint: str = _SAFE_QUOTE,
    timestamp: str = _TIMESTAMP_INSIDE,
    slot: int = 999,
    signature: str = "synth-sig-stale",
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_STALE,
        migration_source=(
            MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
        ),
        base_mint=base_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        quote_mint=quote_mint,
        migration_timestamp_utc=timestamp,
        migration_slot=slot,
        migration_signature=signature,
        observed_at_utc=_OBSERVED_AT_LATER,
        source_event_ref="synth-ref-stale",
    )


def test_base_mint_only_candidate_does_not_join_multiple_pool_or_quote_matches():
    """Stage 29.5.1 remediation: base-mint-only candidate must
    NOT silently JOIN against two records that disagree on the
    pool / quote / pool_program lanes; the join routes to
    PAIR_MISMATCH so a downstream private ping never claims
    POST_MIGRATION_ATH_VERIFIED on ambiguous evidence.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record_a = _evidence_present(pool_account=_SAFE_POOL_A)
    record_b = _evidence_present(
        pool_account=_SAFE_POOL_B,
        signature="synth-sig-B",
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(record_a, record_b),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_PAIR_MISMATCH
    )
    # The matched evidence list still carries both records for
    # the downstream audit projection.
    assert result.matched_evidence_count == 2


def test_candidate_quote_or_pool_axis_disagreement_yields_pair_mismatch():
    """Stage 29.5.1 remediation: a pair of matched records that
    disagree on any one of pool_account / pool_program_id /
    quote_mint routes to PAIR_MISMATCH (axis-by-axis).
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    # quote_mint axis disagreement
    quote_a = _evidence_present(quote_mint=_SAFE_QUOTE)
    quote_b = _evidence_present(
        quote_mint="Z" * 44, signature="synth-sig-q-B"
    )
    r_quote = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(quote_a, quote_b),
        clock=_fixed_clock,
    )
    assert (
        r_quote.migration_join_status
        == MIGRATION_JOIN_STATUS_PAIR_MISMATCH
    )
    # pool_account axis disagreement
    pool_a = _evidence_present(pool_account=_SAFE_POOL_A)
    pool_b = _evidence_present(
        pool_account=_SAFE_POOL_B,
        signature="synth-sig-p-B",
    )
    r_pool = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(pool_a, pool_b),
        clock=_fixed_clock,
    )
    assert (
        r_pool.migration_join_status
        == MIGRATION_JOIN_STATUS_PAIR_MISMATCH
    )
    # pool_program_id axis disagreement
    program_a = _evidence_present(
        pool_program_id=_PUMPSWAP_PROGRAM_ID
    )
    program_b = _evidence_present(
        pool_program_id=_OTHER_PROGRAM_ID,
        signature="synth-sig-prog-B",
    )
    r_program = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(program_a, program_b),
        clock=_fixed_clock,
    )
    assert (
        r_program.migration_join_status
        == MIGRATION_JOIN_STATUS_PAIR_MISMATCH
    )


def test_present_plus_invalid_matching_evidence_does_not_join():
    """Stage 29.5.1 remediation: one PRESENT record with full
    axes does NOT hide a co-matched INVALID record. The join
    routes to SOURCE_INVALID so the projection emits
    INVALID_MIGRATION + WARNING_MIGRATION_TIMESTAMP_INVALID +
    WARNING_POST_MIGRATION_ATH_UNVERIFIED.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    valid = _evidence_present()
    invalid = _evidence_invalid_axes()
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(valid, invalid),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )
    assert result.matched_evidence_count == 2


def test_present_plus_conflicting_matching_evidence_does_not_join():
    """A CONFLICTING matched record also blocks JOINED — routes
    to SOURCE_INVALID alongside the INVALID case.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    valid = _evidence_present()
    conflicting = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_CONFLICTING,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT_LATER,
        source_event_ref=None,
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(valid, conflicting),
        clock=_fixed_clock,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )


def test_present_plus_stale_matching_evidence_preserves_stale_warning():
    """Stage 29.5.1 remediation: PRESENT + STALE matched
    evidence routes to TIME_WINDOW_INVALID so the projection
    preserves the WARNING_MIGRATION_STALE signal rather than
    silently dropping the stale record and JOIN-ing.
    """
    from PHX2.stage29.stage29_5_migration_models import (
        WARNING_MIGRATION_STALE,
        WARNING_POST_MIGRATION_ATH_UNVERIFIED,
    )
    from PHX2.stage29.stage29_5_private_ping_context_projection import (
        project_private_ping_migration_context,
    )

    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    valid = _evidence_present()
    stale = _evidence_stale()
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(valid, stale),
        clock=_fixed_clock,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )
    # Verify the downstream projection preserves the STALE
    # warning (the audit specifically calls out that stale +
    # present must not be hidden by the present record).
    ctx = project_private_ping_migration_context(
        join_record=result,
        ath_context=None,
        clock=_fixed_clock,
    )
    assert WARNING_MIGRATION_STALE in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )


def test_multi_records_conflicting_timestamp_does_not_join():
    """Two PRESENT records with full quartets that share
    everything except ``migration_timestamp_utc`` route to
    MULTIPLE_MATCHES, not JOINED.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    record_a = _evidence_present(timestamp=_TIMESTAMP_INSIDE)
    record_b = _evidence_present(
        timestamp="2026-05-25T11:00:00+00:00",
        signature="synth-sig-ts-B",
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(record_a, record_b),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )


def test_multi_records_conflicting_slot_does_not_join():
    """Two PRESENT records that disagree on migration_slot route
    to MULTIPLE_MATCHES.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    a = _evidence_present(slot=111)
    b = _evidence_present(slot=222, signature="synth-sig-s-B")
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(a, b),
        clock=_fixed_clock,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )


def test_multi_records_conflicting_source_does_not_join():
    """Two PRESENT records that disagree on migration_source
    route to MULTIPLE_MATCHES.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    a = _evidence_present(source=MIGRATION_SOURCE_HELIUS_WS)
    b = _evidence_present(
        source=MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        signature="synth-sig-src-B",
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(a, b),
        clock=_fixed_clock,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
    )


def test_window_compare_uses_parsed_datetime_not_string():
    """Stage 29.5.1 remediation: the half-open
    ``[time_window_start_utc, time_window_end_utc)`` window
    compares parsed UTC datetimes — a record with a Z-suffix
    timestamp matches against a window expressed in +00:00 (and
    vice versa) so long as the wall-clock instant agrees.
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    # Record timestamp uses Z suffix; window uses +00:00 form.
    # Lexicographic compare would treat "Z" > "+" so the
    # pre-remediation join would have treated this as
    # out-of-window when the start bound is set to the same
    # instant in +00:00 form.
    record_z = _evidence_present(
        timestamp="2026-05-25T10:00:00Z",
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(record_z,),
        clock=_fixed_clock,
        time_window_start_utc="2026-05-25T00:00:00+00:00",
        time_window_end_utc="2026-05-26T00:00:00+00:00",
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_JOINED
    )


# ---------------------------------------------------------------------------
# Stage 29.5.1 second remediation: window-blocking + strict matcher
# ---------------------------------------------------------------------------


def test_in_window_present_plus_out_of_window_present_does_not_join():
    """Stage 29.5.1 second remediation: any matched PRESENT
    record outside the caller-supplied time window blocks
    JOINED. Pre-second-remediation, an in-window record could
    silently win and the out-of-window record was dropped.
    """
    from PHX2.stage29.stage29_5_migration_models import (
        WARNING_MIGRATION_STALE,
        WARNING_POST_MIGRATION_ATH_UNVERIFIED,
    )
    from PHX2.stage29.stage29_5_private_ping_context_projection import (
        project_private_ping_migration_context,
    )

    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    in_window = _evidence_present(
        timestamp=_TIMESTAMP_INSIDE,
    )
    out_of_window = _evidence_present(
        timestamp=_TIMESTAMP_AFTER_WINDOW,
        signature="synth-sig-out",
        observed_at_utc=_OBSERVED_AT_LATER,
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(in_window, out_of_window),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )
    # Both records carried on matched_evidence — the
    # out-of-window record must not be silently dropped.
    assert result.matched_evidence_count == 2
    # Downstream projection preserves the STALE + UNVERIFIED
    # warning pair.
    ctx = project_private_ping_migration_context(
        join_record=result,
        ath_context=None,
        clock=_fixed_clock,
    )
    assert WARNING_MIGRATION_STALE in ctx.warnings
    assert (
        WARNING_POST_MIGRATION_ATH_UNVERIFIED in ctx.warnings
    )


def test_only_out_of_window_present_still_yields_time_window_invalid():
    """Defensive companion: when there is NO in-window record
    and only an out-of-window record, the result is still
    TIME_WINDOW_INVALID (unchanged from the first remediation;
    pinned here to lock the contract end-to-end).
    """
    axes = Stage29_5CandidateAxes(base_mint=_SAFE_MINT_A)
    out_of_window = _evidence_present(
        timestamp=_TIMESTAMP_BEFORE_WINDOW,
    )
    result = join_candidate_to_migration_evidence(
        candidate_axes=axes,
        evidence_records=(out_of_window,),
        clock=_fixed_clock,
        time_window_start_utc=_WINDOW_START,
        time_window_end_utc=_WINDOW_END,
    )
    assert (
        result.migration_join_status
        == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    )


def test_candidate_supplied_axis_requires_record_axis_present():
    """Stage 29.5.1 second remediation: when the candidate
    supplies a non-None pool_account / pool_program_id /
    quote_mint, the evidence record MUST supply the same
    non-None value. Evidence-side ``None`` no longer
    wildcards a candidate-supplied axis.
    """
    full_axes = Stage29_5CandidateAxes(
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
    )
    # Case 1: record has correct pool_program_id but pool_account
    # is None. PRESENT dataclass requires the full quartet, so
    # build with INVALID + partial axes (which the dataclass
    # admits) to test the matcher in isolation from the
    # downstream PRESENT-status guards.
    rec_invalid_pool_account = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=None,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    result_no_pool = join_candidate_to_migration_evidence(
        candidate_axes=full_axes,
        evidence_records=(rec_invalid_pool_account,),
        clock=_fixed_clock,
    )
    assert (
        result_no_pool.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    ), (
        "candidate-supplied pool_account axis must require "
        "non-None evidence pool_account"
    )

    # Case 2: record has correct pool_account but
    # pool_program_id is None.
    rec_invalid_program = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=None,
        quote_mint=_SAFE_QUOTE,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    result_no_program = join_candidate_to_migration_evidence(
        candidate_axes=full_axes,
        evidence_records=(rec_invalid_program,),
        clock=_fixed_clock,
    )
    assert (
        result_no_program.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    ), (
        "candidate-supplied pool_program_id axis must require "
        "non-None evidence pool_program_id"
    )

    # Case 3: record has correct pool axes but quote_mint is None.
    rec_invalid_quote = Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_SAFE_MINT_A,
        pool_account=_SAFE_POOL_A,
        pool_program_id=_PUMPSWAP_PROGRAM_ID,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )
    result_no_quote = join_candidate_to_migration_evidence(
        candidate_axes=full_axes,
        evidence_records=(rec_invalid_quote,),
        clock=_fixed_clock,
    )
    assert (
        result_no_quote.migration_join_status
        == MIGRATION_JOIN_STATUS_NO_MATCH
    ), (
        "candidate-supplied quote_mint axis must require "
        "non-None evidence quote_mint"
    )

    # Defensive sanity: when ALL axes match including None
    # equivalents (candidate supplies only base_mint), the join
    # behaves the same as before — the wildcard is candidate-side
    # only.
    base_only_axes = Stage29_5CandidateAxes(
        base_mint=_SAFE_MINT_A,
    )
    result_base_only = join_candidate_to_migration_evidence(
        candidate_axes=base_only_axes,
        evidence_records=(rec_invalid_pool_account,),
        clock=_fixed_clock,
    )
    # rec_invalid_pool_account has migration_status=INVALID, so
    # the join routes to SOURCE_INVALID once the base_mint match
    # admits it.
    assert (
        result_base_only.migration_join_status
        == MIGRATION_JOIN_STATUS_SOURCE_INVALID
    )
