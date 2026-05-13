"""Stage 15 reconciler + safety gate.

Joins Stage 14 rules to operator-review rows and assigns every Stage 14
rule to exactly one final bucket:

  APPROVED          -- APPROVE_OBSERVE_ONLY + safety gate passed
  REJECTED          -- REJECT + non-empty operator_reason
  HELD              -- HOLD + non-empty operator_reason
  NEEDS_MORE_DATA   -- NEEDS_MORE_DATA (reason optional)
  UNREVIEWED        -- no operator row exists
  VALIDATION_ERROR  -- operator row exists but failed an A01-A04 gate

The reconciler does NOT raise on approval-time errors. It records them
as ``ValidationFailure`` objects and lets the writer decide what to do
with them (Tier 3: write non-draft outputs + manifest VALIDATION_FAILED).

Accounting invariant: every Stage 14 rule lands in exactly one bucket.
Stage 15 tests assert APPROVED + REJECTED + HELD + NEEDS_MORE_DATA +
UNREVIEWED + VALIDATION_ERROR == stage14_rule_count.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from PHX2.stage15.loaders import (
    OperatorRow,
    Stage14Rule,
)


class FinalBucket(str, Enum):
    """Closed set of final rule states. Strings so they serialize
    cleanly to CSV and JSON without explicit conversion."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HELD = "HELD"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"
    UNREVIEWED = "UNREVIEWED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


@dataclass(frozen=True)
class ValidationFailure:
    """One A01-A04 approval-time error tied to a specific operator row.

    ``source_csv_row_number`` is 1-indexed including the header row,
    matching the OperatorRow value.
    """

    rule_id: str
    operator_decision: str
    error_code: str
    error_message: str
    source_csv_row_number: int


@dataclass(frozen=True)
class ReconciledRule:
    """One reconciled Stage 14 rule with its final bucket assignment.

    ``operator_row`` is None for UNREVIEWED rules. ``failures`` is
    non-empty only when ``final_bucket == VALIDATION_ERROR``.
    """

    rule: Stage14Rule
    warning_flags: tuple[str, ...]
    operator_row: OperatorRow | None
    final_bucket: FinalBucket
    failures: tuple[ValidationFailure, ...]


@dataclass(frozen=True)
class ReconciliationResult:
    """Collected output of the reconciler.

    ``rules`` preserves the Stage 14 rule ordering from
    shadow_policy_rules.json (deterministic). ``operator_row_results``
    is in operator CSV order; it mirrors what operator_review_decisions.csv
    will look like and includes rows that landed in VALIDATION_ERROR.
    ``validation_failures`` is the flat list for approval_validation_errors.csv.
    """

    rules: tuple[ReconciledRule, ...]
    operator_row_results: tuple[ReconciledRule, ...]
    validation_failures: tuple[ValidationFailure, ...]

    @property
    def approved(self) -> tuple[ReconciledRule, ...]:
        return tuple(r for r in self.rules if r.final_bucket is FinalBucket.APPROVED)

    @property
    def rejected(self) -> tuple[ReconciledRule, ...]:
        return tuple(r for r in self.rules if r.final_bucket is FinalBucket.REJECTED)

    @property
    def held(self) -> tuple[ReconciledRule, ...]:
        return tuple(r for r in self.rules if r.final_bucket is FinalBucket.HELD)

    @property
    def needs_more_data(self) -> tuple[ReconciledRule, ...]:
        return tuple(
            r for r in self.rules if r.final_bucket is FinalBucket.NEEDS_MORE_DATA
        )

    @property
    def unreviewed(self) -> tuple[ReconciledRule, ...]:
        return tuple(r for r in self.rules if r.final_bucket is FinalBucket.UNREVIEWED)

    @property
    def validation_errors(self) -> tuple[ReconciledRule, ...]:
        return tuple(
            r for r in self.rules if r.final_bucket is FinalBucket.VALIDATION_ERROR
        )


def reconcile(
    *,
    stage14_rules: tuple[Stage14Rule, ...],
    operator_rows: tuple[OperatorRow, ...],
    warning_flags_by_rule: Mapping[str, tuple[str, ...]],
) -> ReconciliationResult:
    """Reconcile Stage 14 rules with operator decisions and apply the
    safety gate (A01-A04).

    Output preserves Stage 14 rule ordering. Operator-row results
    preserve operator CSV ordering for downstream CSV emission.
    """

    operator_row_by_rule: dict[str, OperatorRow] = {}
    for row in operator_rows:
        # Duplicate operator rule_ids are rejected at load-time (L22),
        # so this mapping is guaranteed 1:1 by construction.
        operator_row_by_rule[row.rule_id] = row

    rule_results: list[ReconciledRule] = []
    operator_row_results_by_rule: dict[str, ReconciledRule] = {}
    all_failures: list[ValidationFailure] = []

    for rule in stage14_rules:
        flags = tuple(warning_flags_by_rule.get(rule.rule_id, ()))
        operator_row = operator_row_by_rule.get(rule.rule_id)

        if operator_row is None:
            reconciled = ReconciledRule(
                rule=rule,
                warning_flags=flags,
                operator_row=None,
                final_bucket=FinalBucket.UNREVIEWED,
                failures=(),
            )
            rule_results.append(reconciled)
            continue

        bucket, failures = _classify(operator_row, flags)
        reconciled = ReconciledRule(
            rule=rule,
            warning_flags=flags,
            operator_row=operator_row,
            final_bucket=bucket,
            failures=failures,
        )
        rule_results.append(reconciled)
        operator_row_results_by_rule[rule.rule_id] = reconciled
        all_failures.extend(failures)

    # Preserve operator CSV order for operator_row_results.
    ordered_operator_results = tuple(
        operator_row_results_by_rule[row.rule_id]
        for row in operator_rows
        if row.rule_id in operator_row_results_by_rule
    )

    return ReconciliationResult(
        rules=tuple(rule_results),
        operator_row_results=ordered_operator_results,
        validation_failures=tuple(all_failures),
    )


def _classify(
    operator_row: OperatorRow,
    warning_flags: tuple[str, ...],
) -> tuple[FinalBucket, tuple[ValidationFailure, ...]]:
    """Apply A01-A04 to a single operator row.

    Returns the assigned FinalBucket and any per-row validation
    failures. If any failure is recorded, the bucket becomes
    VALIDATION_ERROR regardless of the operator's stated decision.
    """

    decision = operator_row.operator_decision
    reason_non_empty = bool((operator_row.operator_reason or "").strip())
    has_flags = bool(warning_flags)

    failures: list[ValidationFailure] = []

    if decision == "APPROVE_OBSERVE_ONLY":
        if has_flags and not operator_row.override_warning_flags:
            failures.append(
                ValidationFailure(
                    rule_id=operator_row.rule_id,
                    operator_decision=decision,
                    error_code="A01",
                    error_message=(
                        "APPROVE_OBSERVE_ONLY on a warning-flagged rule "
                        "requires override_warning_flags=true"
                    ),
                    source_csv_row_number=operator_row.source_csv_row_number,
                )
            )
        if has_flags and not reason_non_empty:
            failures.append(
                ValidationFailure(
                    rule_id=operator_row.rule_id,
                    operator_decision=decision,
                    error_code="A02",
                    error_message=(
                        "APPROVE_OBSERVE_ONLY on a warning-flagged rule "
                        "requires non-empty operator_reason"
                    ),
                    source_csv_row_number=operator_row.source_csv_row_number,
                )
            )
        if failures:
            return FinalBucket.VALIDATION_ERROR, tuple(failures)
        return FinalBucket.APPROVED, ()

    if decision == "REJECT":
        if not reason_non_empty:
            failures.append(
                ValidationFailure(
                    rule_id=operator_row.rule_id,
                    operator_decision=decision,
                    error_code="A03",
                    error_message="REJECT requires non-empty operator_reason",
                    source_csv_row_number=operator_row.source_csv_row_number,
                )
            )
            return FinalBucket.VALIDATION_ERROR, tuple(failures)
        return FinalBucket.REJECTED, ()

    if decision == "HOLD":
        if not reason_non_empty:
            failures.append(
                ValidationFailure(
                    rule_id=operator_row.rule_id,
                    operator_decision=decision,
                    error_code="A04",
                    error_message="HOLD requires non-empty operator_reason",
                    source_csv_row_number=operator_row.source_csv_row_number,
                )
            )
            return FinalBucket.VALIDATION_ERROR, tuple(failures)
        return FinalBucket.HELD, ()

    if decision == "NEEDS_MORE_DATA":
        # operator_reason optional but recommended; no A-code applies.
        return FinalBucket.NEEDS_MORE_DATA, ()

    # Unreachable: L17 already rejects unknown decisions.
    raise AssertionError(
        f"reconciler reached unreachable branch for decision {decision!r}; "
        f"L17 should have rejected this at load time"
    )
