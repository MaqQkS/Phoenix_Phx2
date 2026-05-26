"""Stage 29.5 candidate-to-migration join layer.

The join layer is the sole authority that decides
``migration_join_status`` from a set of upstream Stage 29.5
migration evidence records, a candidate's pair axes, and a
caller-supplied time window. Both the Stage 29.5 Helius WS
adapter and the Stage 29.5 artifact reader produce evidence
records; the join layer makes one verdict per candidate per
call.

Join semantics:

  1. **Exact-match filter.** Filter the evidence sequence to
     records that match the candidate's axes on every axis the
     candidate supplied. The ``base_mint`` axis is always
     supplied; the three other axes
     (``pool_account``, ``pool_program_id``, ``quote_mint``)
     are optional and wildcarded when ``None``.
  2. **PumpSwap-id sanity check.** When the candidate did not
     supply ``pool_program_id`` AND the matched evidence's
     ``pool_program_id`` is non-None but disagrees with the
     candidate's ``base_mint``-implied PumpSwap context, the
     match is downgraded to ``PAIR_MISMATCH``. This rule is
     opt-in via the ``expected_pool_program_id`` constructor
     parameter.
  3. **Required-axis check.** A surviving record must carry
     ``migration_status=PRESENT`` with the quartet +
     ``migration_timestamp_utc`` populated. Otherwise the join
     emits ``SOURCE_INVALID``.
  4. **Time-window check.** A surviving record's
     ``migration_timestamp_utc`` must fall inside the
     caller-supplied half-open window
     ``[time_window_start_utc, time_window_end_utc)``. Either
     bound may be ``None`` (no lower / upper bound). When the
     window is closed and the timestamp falls outside, the join
     emits ``TIME_WINDOW_INVALID``.
  5. **Multiplicity check.** If two or more surviving records
     agree on ``(migration_timestamp_utc, migration_slot,
     migration_source)``, the join emits ``JOINED`` with all
     matching records carried on
     ``matched_evidence``. If they disagree on any of those
     three axes, the join emits ``MULTIPLE_MATCHES``.

The join function is pure: same inputs => same output. The
function never mutates its inputs and never raises.

Discipline:

  * No env reads.
  * No network. No file I/O.
  * No third-party runtime dependency. Imports only stdlib
    (``typing``) plus the Stage 29.5 models module.
  * No top-level Call.
  * No PHX1 import.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_PAIR_MISMATCH,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_STATUS_CONFLICTING,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_STALE,
    Stage29_5MigrationEvidenceRecord,
    Stage29_5MigrationJoinRecord,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
    parse_safe_utc_datetime,
)


# ---------------------------------------------------------------------------
# Candidate axes input record
# ---------------------------------------------------------------------------


class Stage29_5CandidateAxes:
    """Immutable container for the candidate's pair axes.

    Validated in ``__init__``. The candidate always supplies a
    safe-shape ``base_mint``; the three other axes may be
    ``None`` and are wildcarded by the join filter.
    """

    __slots__ = (
        "base_mint",
        "pool_account",
        "pool_program_id",
        "quote_mint",
    )

    def __init__(
        self,
        base_mint: str,
        pool_account: Optional[str] = None,
        pool_program_id: Optional[str] = None,
        quote_mint: Optional[str] = None,
    ) -> None:
        if not is_safe_mint_or_pool_string(base_mint):
            raise ValueError(
                "Stage29_5CandidateAxes.base_mint must be a "
                "safe-shape printable string of length 32..64; "
                f"got {base_mint!r}"
            )
        for axis_name, axis_value in (
            ("pool_account", pool_account),
            ("pool_program_id", pool_program_id),
            ("quote_mint", quote_mint),
        ):
            if axis_value is not None and not (
                is_safe_mint_or_pool_string(axis_value)
            ):
                raise ValueError(
                    f"Stage29_5CandidateAxes.{axis_name} must "
                    "be a safe-shape printable string of "
                    f"length 32..64 when populated; got "
                    f"{axis_value!r}"
                )
        object.__setattr__(self, "base_mint", base_mint)
        object.__setattr__(
            self, "pool_account", pool_account
        )
        object.__setattr__(
            self, "pool_program_id", pool_program_id
        )
        object.__setattr__(self, "quote_mint", quote_mint)

    def __setattr__(self, key: str, value: object) -> None:
        raise AttributeError(
            "Stage29_5CandidateAxes is immutable"
        )


# ---------------------------------------------------------------------------
# Join function
# ---------------------------------------------------------------------------


def _record_matches_candidate(
    record: Stage29_5MigrationEvidenceRecord,
    axes: Stage29_5CandidateAxes,
) -> bool:
    """Stage 29.5.1 second remediation: tighter axis matcher.

    Match rules:

      * ``base_mint`` is always required to be supplied by both
        the candidate and the evidence record. They must equal.
      * For each of ``pool_account`` / ``pool_program_id`` /
        ``quote_mint``: if the candidate supplies a non-None
        value, the evidence record MUST supply the same non-None
        value. Evidence-side ``None`` no longer satisfies a
        candidate-supplied axis (the wildcard is candidate-side
        only). If the candidate supplies ``None`` on an axis,
        that axis is wildcarded for the match.

    The pre-second-remediation matcher let evidence-side ``None``
    silently satisfy any candidate-supplied axis, which created
    a route for evidence with incomplete provenance to anchor a
    JOINED verdict. The audit demanded this be closed.
    """
    if record.base_mint is None:
        return False
    if record.base_mint != axes.base_mint:
        return False
    for cand_value, rec_value in (
        (axes.pool_account, record.pool_account),
        (axes.pool_program_id, record.pool_program_id),
        (axes.quote_mint, record.quote_mint),
    ):
        if cand_value is None:
            continue
        if rec_value is None:
            return False
        if rec_value != cand_value:
            return False
    return True


def _timestamp_in_window(
    timestamp_utc: str,
    start_utc: Optional[str],
    end_utc: Optional[str],
) -> bool:
    """Stage 29.5.1 remediation: parse all three timestamps as
    strict UTC datetimes via :func:`parse_safe_utc_datetime` and
    compare aware ``datetime`` objects. A raw lexicographic
    string compare is no longer used.

    Any parse failure (malformed calendar / clock / non-UTC
    offset / whitespace) returns False — the join layer treats
    an un-parseable timestamp as out-of-window.
    """
    try:
        ts = parse_safe_utc_datetime(timestamp_utc)
    except ValueError:
        return False
    if start_utc is not None:
        try:
            start = parse_safe_utc_datetime(start_utc)
        except ValueError:
            return False
        if ts < start:
            return False
    if end_utc is not None:
        try:
            end = parse_safe_utc_datetime(end_utc)
        except ValueError:
            return False
        if ts >= end:
            return False
    return True


def _records_agree_on_core(
    records: Sequence[Stage29_5MigrationEvidenceRecord],
) -> bool:
    """Stage 29.5.1 remediation: widened core-agreement check.

    Two matched evidence records "agree on core" iff they share
    the same values on ALL of:

      * ``migration_status``
      * ``migration_timestamp_utc``
      * ``migration_slot``
      * ``migration_source``
      * ``pool_account``
      * ``pool_program_id``
      * ``quote_mint``

    The base_mint axis is already proven equal by the upstream
    axis filter.

    Pre-remediation this helper only compared the first three
    axes, which let two matched records with disagreeing
    pool_account / quote_mint / pool_program_id silently JOIN —
    Codex flagged that as the primary join-strictness defect.
    The pool / quote / pool_program disagreement now also routes
    to PAIR_MISMATCH at a separate guard upstream; the widened
    check here remains the last-line MULTIPLE_MATCHES
    determinator.
    """
    if not records:
        return True
    first = records[0]
    for r in records[1:]:
        if r.migration_status != first.migration_status:
            return False
        if (
            r.migration_timestamp_utc
            != first.migration_timestamp_utc
        ):
            return False
        if r.migration_slot != first.migration_slot:
            return False
        if r.migration_source != first.migration_source:
            return False
        if r.pool_account != first.pool_account:
            return False
        if r.pool_program_id != first.pool_program_id:
            return False
        if r.quote_mint != first.quote_mint:
            return False
    return True


def _records_disagree_on_pair_axes(
    records: Sequence[Stage29_5MigrationEvidenceRecord],
) -> bool:
    """Stage 29.5.1 remediation: return True iff at least two
    matched records carry CONFLICTING non-None values on any of
    ``pool_account`` / ``pool_program_id`` / ``quote_mint``.

    A pair "disagrees" on an axis iff BOTH records have non-None
    values for that axis AND those values differ. ``None`` on
    either side is a wildcard, not a disagreement (the axis was
    simply not populated by that source).
    """
    seen_pool_account: Optional[str] = None
    seen_pool_program_id: Optional[str] = None
    seen_quote_mint: Optional[str] = None
    for r in records:
        if r.pool_account is not None:
            if (
                seen_pool_account is not None
                and r.pool_account != seen_pool_account
            ):
                return True
            seen_pool_account = r.pool_account
        if r.pool_program_id is not None:
            if (
                seen_pool_program_id is not None
                and r.pool_program_id != seen_pool_program_id
            ):
                return True
            seen_pool_program_id = r.pool_program_id
        if r.quote_mint is not None:
            if (
                seen_quote_mint is not None
                and r.quote_mint != seen_quote_mint
            ):
                return True
            seen_quote_mint = r.quote_mint
    return False


def join_candidate_to_migration_evidence(
    candidate_axes: Stage29_5CandidateAxes,
    evidence_records: Sequence[
        Stage29_5MigrationEvidenceRecord
    ],
    clock: Callable[[], str],
    time_window_start_utc: Optional[str] = None,
    time_window_end_utc: Optional[str] = None,
    expected_pool_program_id: Optional[str] = None,
) -> Stage29_5MigrationJoinRecord:
    """Pure join function — see module docstring for semantics.

    Returns a :class:`Stage29_5MigrationJoinRecord` carrying the
    closed-set ``migration_join_status`` token, the candidate
    axes echoed for audit, the matched evidence in deterministic
    order (sorted by ``observed_at_utc`` ascending then by
    ``migration_signature`` ascending where present), the caller-
    supplied time window, and the clock-injected
    ``joined_at_utc``.
    """
    if not isinstance(candidate_axes, Stage29_5CandidateAxes):
        raise ValueError(
            "candidate_axes must be a Stage29_5CandidateAxes "
            "instance"
        )
    if not callable(clock):
        raise ValueError("clock must be callable")
    if (
        time_window_start_utc is not None
        and not is_safe_iso8601_utc_string(
            time_window_start_utc
        )
    ):
        raise ValueError(
            "time_window_start_utc must be UTC-shaped ISO-8601 "
            "when populated"
        )
    if (
        time_window_end_utc is not None
        and not is_safe_iso8601_utc_string(
            time_window_end_utc
        )
    ):
        raise ValueError(
            "time_window_end_utc must be UTC-shaped ISO-8601 "
            "when populated"
        )
    if (
        expected_pool_program_id is not None
        and not is_safe_mint_or_pool_string(
            expected_pool_program_id
        )
    ):
        raise ValueError(
            "expected_pool_program_id must be a safe-shape "
            "printable string of length 32..64 when populated"
        )
    joined_at_utc = clock()
    if not is_safe_iso8601_utc_string(joined_at_utc):
        raise ValueError(
            "clock returned a non-UTC-shaped string"
        )
    matched_axis_records: list = []
    for record in evidence_records:
        if not isinstance(
            record, Stage29_5MigrationEvidenceRecord
        ):
            raise ValueError(
                "evidence_records entries must each be "
                "Stage29_5MigrationEvidenceRecord instances"
            )
        if _record_matches_candidate(record, candidate_axes):
            matched_axis_records.append(record)
    if not matched_axis_records:
        return Stage29_5MigrationJoinRecord(
            migration_join_status=MIGRATION_JOIN_STATUS_NO_MATCH,
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=0,
            matched_evidence=(),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    if expected_pool_program_id is not None:
        for r in matched_axis_records:
            if r.pool_program_id is None:
                continue
            if (
                r.pool_program_id
                != expected_pool_program_id
            ):
                return Stage29_5MigrationJoinRecord(
                    migration_join_status=(
                        MIGRATION_JOIN_STATUS_PAIR_MISMATCH
                    ),
                    candidate_base_mint=(
                        candidate_axes.base_mint
                    ),
                    candidate_pool_account=(
                        candidate_axes.pool_account
                    ),
                    candidate_pool_program_id=(
                        candidate_axes.pool_program_id
                    ),
                    candidate_quote_mint=(
                        candidate_axes.quote_mint
                    ),
                    matched_evidence_count=len(
                        matched_axis_records
                    ),
                    matched_evidence=tuple(
                        _deterministic_sort(
                            matched_axis_records
                        )
                    ),
                    time_window_start_utc=(
                        time_window_start_utc
                    ),
                    time_window_end_utc=time_window_end_utc,
                    joined_at_utc=joined_at_utc,
                )
    # Stage 29.5.1 remediation guard A: pairwise pool / quote /
    # pool_program_id axis disagreement among matched records
    # routes to PAIR_MISMATCH so a base-mint-only candidate cannot
    # silently JOIN against two records that disagree on the
    # quote / pool lanes.
    if _records_disagree_on_pair_axes(matched_axis_records):
        return Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_PAIR_MISMATCH
            ),
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=len(matched_axis_records),
            matched_evidence=tuple(
                _deterministic_sort(matched_axis_records)
            ),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    # Stage 29.5.1 remediation guard B: any INVALID or
    # CONFLICTING matched record routes the verdict to
    # SOURCE_INVALID so one valid PRESENT record cannot hide a
    # co-matched INVALID record.
    statuses_present_set = {
        r.migration_status for r in matched_axis_records
    }
    if (
        MIGRATION_STATUS_INVALID in statuses_present_set
        or MIGRATION_STATUS_CONFLICTING
        in statuses_present_set
    ):
        return Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_SOURCE_INVALID
            ),
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=len(matched_axis_records),
            matched_evidence=tuple(
                _deterministic_sort(matched_axis_records)
            ),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    # Stage 29.5.1 remediation guard C: any STALE matched record
    # routes the verdict to TIME_WINDOW_INVALID so the projection
    # preserves the WARNING_MIGRATION_STALE signal rather than
    # silently dropping the stale record.
    if MIGRATION_STATUS_STALE in statuses_present_set:
        return Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
            ),
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=len(matched_axis_records),
            matched_evidence=tuple(
                _deterministic_sort(matched_axis_records)
            ),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    invalid_records = [
        r
        for r in matched_axis_records
        if (
            r.migration_status != MIGRATION_STATUS_PRESENT
            or r.migration_timestamp_utc is None
            or r.base_mint is None
            or r.pool_account is None
            or r.pool_program_id is None
            or r.quote_mint is None
        )
    ]
    if invalid_records and not (
        any(
            r.migration_status == MIGRATION_STATUS_PRESENT
            and r.migration_timestamp_utc is not None
            and r.base_mint is not None
            and r.pool_account is not None
            and r.pool_program_id is not None
            and r.quote_mint is not None
            for r in matched_axis_records
        )
    ):
        return Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_SOURCE_INVALID
            ),
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=len(
                matched_axis_records
            ),
            matched_evidence=tuple(
                _deterministic_sort(matched_axis_records)
            ),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    present_records = [
        r
        for r in matched_axis_records
        if (
            r.migration_status == MIGRATION_STATUS_PRESENT
            and r.migration_timestamp_utc is not None
        )
    ]
    out_of_window_records = [
        r
        for r in present_records
        if not _timestamp_in_window(
            r.migration_timestamp_utc,
            time_window_start_utc,
            time_window_end_utc,
        )
    ]
    in_window_records = [
        r
        for r in present_records
        if _timestamp_in_window(
            r.migration_timestamp_utc,
            time_window_start_utc,
            time_window_end_utc,
        )
    ]
    # Stage 29.5.1 second remediation: ANY matched PRESENT
    # record outside the caller-supplied time window blocks
    # JOINED. The pre-remediation partition let an in-window
    # record hide a co-matched stale out-of-window record; the
    # audit demanded that out-of-window matched evidence must
    # not be silently dropped when an in-window record exists.
    if out_of_window_records:
        return Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
            ),
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=len(
                matched_axis_records
            ),
            matched_evidence=tuple(
                _deterministic_sort(matched_axis_records)
            ),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    if not _records_agree_on_core(in_window_records):
        return Stage29_5MigrationJoinRecord(
            migration_join_status=(
                MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES
            ),
            candidate_base_mint=candidate_axes.base_mint,
            candidate_pool_account=candidate_axes.pool_account,
            candidate_pool_program_id=(
                candidate_axes.pool_program_id
            ),
            candidate_quote_mint=candidate_axes.quote_mint,
            matched_evidence_count=len(in_window_records),
            matched_evidence=tuple(
                _deterministic_sort(in_window_records)
            ),
            time_window_start_utc=time_window_start_utc,
            time_window_end_utc=time_window_end_utc,
            joined_at_utc=joined_at_utc,
        )
    return Stage29_5MigrationJoinRecord(
        migration_join_status=MIGRATION_JOIN_STATUS_JOINED,
        candidate_base_mint=candidate_axes.base_mint,
        candidate_pool_account=candidate_axes.pool_account,
        candidate_pool_program_id=(
            candidate_axes.pool_program_id
        ),
        candidate_quote_mint=candidate_axes.quote_mint,
        matched_evidence_count=len(in_window_records),
        matched_evidence=tuple(
            _deterministic_sort(in_window_records)
        ),
        time_window_start_utc=time_window_start_utc,
        time_window_end_utc=time_window_end_utc,
        joined_at_utc=joined_at_utc,
    )


def _deterministic_sort(
    records: Sequence[Stage29_5MigrationEvidenceRecord],
) -> Tuple[Stage29_5MigrationEvidenceRecord, ...]:
    def _key(
        r: Stage29_5MigrationEvidenceRecord,
    ) -> Tuple[str, str]:
        return (
            r.observed_at_utc,
            r.migration_signature or "",
        )

    return tuple(sorted(records, key=_key))


__all__ = (
    "Stage29_5CandidateAxes",
    "join_candidate_to_migration_evidence",
)
