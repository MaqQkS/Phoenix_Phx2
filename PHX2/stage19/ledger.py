"""Stage 19 ledger primitives: row types, sequencing, merging,
and summary computation.

Defines:

  * LedgerRow            -- 13-field NamedTuple matching
                            LEDGER_COLUMNS order in
                            PHX2.stage19.constants.
  * SummaryRow           -- 11-field NamedTuple matching
                            SUMMARY_COLUMNS order in
                            PHX2.stage19.constants.
  * build_ledger_rows    -- assigns review_sequence per
                            (stage18_run_id, slice key,
                            operator_id) chain and computes a
                            deterministic ledger_row_id.
  * merge_ledger         -- combines prior + new rows in canonical
                            sort order with prior rows preserved
                            verbatim.
  * compute_summary      -- one row per (stage18_run_id, slice
                            key, operator_id) at
                            MAX(review_sequence).

The deterministic ledger_row_id is the first 16 hex chars of
SHA-256 over canonical JSON of:

    {"stage19_run_id": ..., "stage18_run_id": ...,
     "policy_hash": ..., "rule_id": ...,
     "window_seconds": <int>, "operator_id": ...,
     "review_sequence": <int>}

with ``sort_keys=True``, ``separators=(",", ":")``,
``ensure_ascii=False``.

Cross-operator reconciliation (consensus, voting, conflict
resolution) is intentionally NOT implemented in v0; that lives
in Stage 20+. The summary is per-operator only.

Type-import note: ``OperatorInputRow`` and ``ReviewMatrixIndex``
live in ``PHX2.stage19.readers`` and are imported here under
``TYPE_CHECKING`` only to avoid a runtime circular import
(``readers`` imports ``LedgerRow`` from this module for the
``read_prior_ledger`` return type).
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, NamedTuple, Sequence

if TYPE_CHECKING:
    from PHX2.stage19.readers import OperatorInputRow, ReviewMatrixIndex


class LedgerRow(NamedTuple):
    """One ledger row. Field order matches LEDGER_COLUMNS in
    PHX2.stage19.constants exactly."""

    stage19_run_id: str
    ledger_row_id: str
    stage18_run_id: str
    policy_hash: str
    rule_id: str
    window_seconds: int
    operator_id: str
    review_sequence: int
    review_label: str
    review_notes: str
    review_timestamp_utc: str
    stage18_classification: str
    stage17_label_preserved: str


class SummaryRow(NamedTuple):
    """One summary row. Field order matches SUMMARY_COLUMNS in
    PHX2.stage19.constants exactly."""

    stage18_run_id: str
    policy_hash: str
    rule_id: str
    window_seconds: int
    operator_id: str
    current_review_sequence: int
    current_review_label: str
    current_review_notes: str
    current_review_timestamp_utc: str
    stage18_classification: str
    stage17_label_preserved: str


def _compute_ledger_row_id(
    *,
    stage19_run_id: str,
    stage18_run_id: str,
    policy_hash: str,
    rule_id: str,
    window_seconds: int,
    operator_id: str,
    review_sequence: int,
) -> str:
    """Derive the 16-hex-char deterministic ledger_row_id."""

    canonical = json.dumps(
        {
            "stage19_run_id": stage19_run_id,
            "stage18_run_id": stage18_run_id,
            "policy_hash": policy_hash,
            "rule_id": rule_id,
            "window_seconds": window_seconds,
            "operator_id": operator_id,
            "review_sequence": review_sequence,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def _ledger_sort_key(row: LedgerRow) -> tuple:
    """Canonical D3 sort key:
    (stage18_run_id, policy_hash, rule_id, window_seconds as int,
     operator_id, review_sequence as int)."""

    return (
        row.stage18_run_id,
        row.policy_hash,
        row.rule_id,
        int(row.window_seconds),
        row.operator_id,
        int(row.review_sequence),
    )


def _summary_sort_key(row: SummaryRow) -> tuple:
    """Canonical D4 sort key:
    (stage18_run_id, policy_hash, rule_id, window_seconds as int,
     operator_id)."""

    return (
        row.stage18_run_id,
        row.policy_hash,
        row.rule_id,
        int(row.window_seconds),
        row.operator_id,
    )


def build_ledger_rows(
    operator_input: Sequence["OperatorInputRow"],
    prior_ledger_rows: Sequence[LedgerRow],
    stage19_run_id: str,
    operator_id: str,
    review_timestamp_utc: str,
    review_matrix_index: "ReviewMatrixIndex",
) -> list[LedgerRow]:
    """Assign review_sequence and ledger_row_id to each operator
    input row, and pull stage18_classification +
    stage17_label_preserved from the review_matrix index.

    review_sequence per operator-input row:
      * Find prior rows matching ``(stage18_run_id, policy_hash,
        rule_id, window_seconds, operator_id)``.
      * If matches exist: review_sequence = max(matches) + 1.
      * If no matches: review_sequence = 1.
      * If multiple new operator-input rows target the same
        (slice, operator) within this run, they receive
        sequential numbers in input order.

    ledger_row_id is the first 16 hex chars of SHA-256 over the
    canonical JSON of the seven canonical identity fields.

    review_timestamp_utc is set verbatim from the function
    argument on every produced row (one timestamp per Stage 19
    run).

    Returns NEW LedgerRow objects only (not including prior rows)
    in canonical D3 sort order.
    """

    max_seq: dict[tuple[str, str, str, int, str], int] = {}
    for prior in prior_ledger_rows:
        key = (
            prior.stage18_run_id,
            prior.policy_hash,
            prior.rule_id,
            int(prior.window_seconds),
            prior.operator_id,
        )
        cur = max_seq.get(key, 0)
        if int(prior.review_sequence) > cur:
            max_seq[key] = int(prior.review_sequence)

    new_rows: list[LedgerRow] = []
    for op_row in operator_input:
        key = (
            op_row.stage18_run_id,
            op_row.policy_hash,
            op_row.rule_id,
            int(op_row.window_seconds),
            operator_id,
        )
        next_seq = max_seq.get(key, 0) + 1
        max_seq[key] = next_seq

        review_record = review_matrix_index[
            (op_row.policy_hash, op_row.rule_id, int(op_row.window_seconds))
        ]

        ledger_row_id = _compute_ledger_row_id(
            stage19_run_id=stage19_run_id,
            stage18_run_id=op_row.stage18_run_id,
            policy_hash=op_row.policy_hash,
            rule_id=op_row.rule_id,
            window_seconds=int(op_row.window_seconds),
            operator_id=operator_id,
            review_sequence=next_seq,
        )

        new_rows.append(LedgerRow(
            stage19_run_id=stage19_run_id,
            ledger_row_id=ledger_row_id,
            stage18_run_id=op_row.stage18_run_id,
            policy_hash=op_row.policy_hash,
            rule_id=op_row.rule_id,
            window_seconds=int(op_row.window_seconds),
            operator_id=operator_id,
            review_sequence=next_seq,
            review_label=op_row.review_label,
            review_notes=op_row.review_notes,
            review_timestamp_utc=review_timestamp_utc,
            stage18_classification=review_record.stage18_classification,
            stage17_label_preserved=review_record.stage17_label_preserved,
        ))

    return sorted(new_rows, key=_ledger_sort_key)


def merge_ledger(
    prior_rows: Sequence[LedgerRow],
    new_rows: Sequence[LedgerRow],
) -> list[LedgerRow]:
    """Return prior + new rows sorted by canonical D3 order.

    Prior rows are preserved verbatim -- no field is mutated.
    The function does not deduplicate across prior and new rows
    (the caller is responsible for ensuring sequencing
    correctness; ``build_ledger_rows`` handles this for the
    write path).
    """

    return sorted(list(prior_rows) + list(new_rows), key=_ledger_sort_key)


def compute_summary(ledger_rows: Sequence[LedgerRow]) -> list[SummaryRow]:
    """Group ``ledger_rows`` by (stage18_run_id, policy_hash,
    rule_id, window_seconds, operator_id) and emit one
    SummaryRow per group at MAX(review_sequence). Returned rows
    are sorted by canonical D4 order.

    An empty ledger produces an empty summary.
    """

    groups: dict[tuple[str, str, str, int, str], LedgerRow] = {}
    for row in ledger_rows:
        key = (
            row.stage18_run_id,
            row.policy_hash,
            row.rule_id,
            int(row.window_seconds),
            row.operator_id,
        )
        prev = groups.get(key)
        if prev is None or int(row.review_sequence) > int(prev.review_sequence):
            groups[key] = row

    summaries: list[SummaryRow] = []
    for max_row in groups.values():
        summaries.append(SummaryRow(
            stage18_run_id=max_row.stage18_run_id,
            policy_hash=max_row.policy_hash,
            rule_id=max_row.rule_id,
            window_seconds=int(max_row.window_seconds),
            operator_id=max_row.operator_id,
            current_review_sequence=int(max_row.review_sequence),
            current_review_label=max_row.review_label,
            current_review_notes=max_row.review_notes,
            current_review_timestamp_utc=max_row.review_timestamp_utc,
            stage18_classification=max_row.stage18_classification,
            stage17_label_preserved=max_row.stage17_label_preserved,
        ))

    return sorted(summaries, key=_summary_sort_key)


__all__ = [
    "LedgerRow",
    "SummaryRow",
    "build_ledger_rows",
    "compute_summary",
    "merge_ledger",
]
