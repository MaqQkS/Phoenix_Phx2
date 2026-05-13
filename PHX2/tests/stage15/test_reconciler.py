"""Stage 15 PHASE 3 reconciler + safety gate tests.

Exercises A01-A04 per-row gating, bucket assignment, and the accounting
invariant (every Stage 14 rule lands in exactly one of APPROVED /
REJECTED / HELD / NEEDS_MORE_DATA / UNREVIEWED / VALIDATION_ERROR, and
the bucket counts sum to the Stage 14 rule count).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from PHX2.stage15.loaders import OperatorRow, Stage14Rule
from PHX2.stage15.reconciler import (
    FinalBucket,
    ReconciliationResult,
    reconcile,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _rule(rule_id: str, **predicate_overrides) -> Stage14Rule:
    """Build a Stage 14 rule with sensible defaults for predicate fields."""

    predicate = {
        "tier_scope": "T2",
        "filter_name": "fee_gate",
        "filter_version": "v1",
        "filter_label": "x",
        "threshold_version": "v1",
    }
    predicate.update(predicate_overrides)
    return Stage14Rule(
        rule_id=rule_id,
        predicate=predicate,
        simulated_action="SIMULATED_BLOCK",
        raw={"rule_id": rule_id, **predicate, "simulated_action": "SIMULATED_BLOCK"},
    )


def _op(
    rule_id: str,
    decision: str,
    *,
    reason: str = "",
    override: bool = False,
    notes: str = "",
    row: int = 2,
) -> OperatorRow:
    ts_raw = "2026-05-12T12:00:00+00:00"
    ts = datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc)
    return OperatorRow(
        rule_id=rule_id,
        operator_decision=decision,
        operator_reason=reason,
        reviewer="Maq",
        reviewed_at_utc=ts,
        reviewed_at_utc_raw=ts_raw,
        override_warning_flags=override,
        notes=notes,
        source_csv_row_number=row,
    )


# ---------------------------------------------------------------------------
# Bucket assignment
# ---------------------------------------------------------------------------


def test_approve_unflagged_no_reason_becomes_APPROVED() -> None:
    """APPROVE_OBSERVE_ONLY + no flags + no reason -> APPROVED.

    operator_reason is optional when the rule isn't warning-flagged.
    """

    rules = (_rule("r1"),)
    ops = (_op("r1", "APPROVE_OBSERVE_ONLY"),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    assert [r.final_bucket for r in result.rules] == [FinalBucket.APPROVED]
    assert result.validation_failures == ()


def test_approve_flagged_with_override_and_reason_becomes_APPROVED() -> None:
    rules = (_rule("r1"),)
    ops = (
        _op("r1", "APPROVE_OBSERVE_ONLY", reason="ok under observe-only", override=True),
    )
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ("small_n_rule",)},
    )
    assert result.rules[0].final_bucket is FinalBucket.APPROVED


def test_approve_flagged_without_override_raises_A01() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "APPROVE_OBSERVE_ONLY", reason="ok", override=False),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ("small_n_rule",)},
    )
    assert result.rules[0].final_bucket is FinalBucket.VALIDATION_ERROR
    codes = [f.error_code for f in result.validation_failures]
    assert "A01" in codes


def test_approve_flagged_without_reason_raises_A02() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "APPROVE_OBSERVE_ONLY", reason="", override=True),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ("small_n_rule",)},
    )
    assert result.rules[0].final_bucket is FinalBucket.VALIDATION_ERROR
    codes = [f.error_code for f in result.validation_failures]
    assert "A02" in codes


def test_approve_flagged_without_override_or_reason_raises_both() -> None:
    """A row may emit multiple failures simultaneously."""

    rules = (_rule("r1"),)
    ops = (_op("r1", "APPROVE_OBSERVE_ONLY", reason="", override=False),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ("small_n_rule",)},
    )
    codes = sorted(f.error_code for f in result.validation_failures)
    assert codes == ["A01", "A02"]
    assert result.rules[0].final_bucket is FinalBucket.VALIDATION_ERROR


def test_reject_with_reason_becomes_REJECTED() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "REJECT", reason="don't want"),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    assert result.rules[0].final_bucket is FinalBucket.REJECTED


def test_reject_without_reason_raises_A03() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "REJECT", reason=""),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    codes = [f.error_code for f in result.validation_failures]
    assert codes == ["A03"]
    assert result.rules[0].final_bucket is FinalBucket.VALIDATION_ERROR


def test_hold_with_reason_becomes_HELD() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "HOLD", reason="circle back later"),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    assert result.rules[0].final_bucket is FinalBucket.HELD


def test_hold_without_reason_raises_A04() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "HOLD", reason=""),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    codes = [f.error_code for f in result.validation_failures]
    assert codes == ["A04"]
    assert result.rules[0].final_bucket is FinalBucket.VALIDATION_ERROR


def test_needs_more_data_without_reason_becomes_NEEDS_MORE_DATA() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "NEEDS_MORE_DATA", reason=""),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    assert result.rules[0].final_bucket is FinalBucket.NEEDS_MORE_DATA
    assert result.validation_failures == ()


def test_needs_more_data_with_reason_still_works() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "NEEDS_MORE_DATA", reason="awaiting more data"),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    assert result.rules[0].final_bucket is FinalBucket.NEEDS_MORE_DATA


def test_no_operator_row_becomes_UNREVIEWED() -> None:
    rules = (_rule("r1"), _rule("r2"))
    ops = (_op("r1", "APPROVE_OBSERVE_ONLY"),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": (), "r2": ()},
    )
    by_id = {r.rule.rule_id: r.final_bucket for r in result.rules}
    assert by_id == {"r1": FinalBucket.APPROVED, "r2": FinalBucket.UNREVIEWED}


def test_override_true_on_unflagged_rule_is_allowed() -> None:
    """override_warning_flags=true on a rule with empty warning_flags
    is informational, not an error. Spec: 'allowed, log visible info,
    no error'."""

    rules = (_rule("r1"),)
    ops = (
        _op(
            "r1",
            "APPROVE_OBSERVE_ONLY",
            reason="defensive override",
            override=True,
        ),
    )
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    assert result.rules[0].final_bucket is FinalBucket.APPROVED
    assert result.validation_failures == ()


def test_whitespace_only_reason_treated_as_empty() -> None:
    rules = (_rule("r1"),)
    ops = (_op("r1", "REJECT", reason="   "),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ()},
    )
    codes = [f.error_code for f in result.validation_failures]
    assert codes == ["A03"]


# ---------------------------------------------------------------------------
# Accounting invariant
# ---------------------------------------------------------------------------


def test_accounting_invariant_mixed_buckets() -> None:
    """A non-trivial mix touches every bucket and sums to N."""

    rules = tuple(_rule(f"r{i}") for i in range(1, 8))
    ops = (
        _op("r1", "APPROVE_OBSERVE_ONLY"),                                  # APPROVED
        _op("r2", "APPROVE_OBSERVE_ONLY", reason="ok", override=True),      # APPROVED (flagged)
        _op("r3", "REJECT", reason="no"),                                   # REJECTED
        _op("r4", "HOLD", reason="later"),                                  # HELD
        _op("r5", "NEEDS_MORE_DATA"),                                       # NEEDS_MORE_DATA
        _op("r6", "APPROVE_OBSERVE_ONLY", reason="", override=False),       # VALIDATION_ERROR (flagged)
        # r7 has no operator row -> UNREVIEWED
    )
    flags = {f"r{i}": () for i in range(1, 8)}
    flags["r2"] = ("small_n_rule",)
    flags["r6"] = ("small_n_rule",)

    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule=flags,
    )

    counts = {
        "approved": len(result.approved),
        "rejected": len(result.rejected),
        "held": len(result.held),
        "needs_more_data": len(result.needs_more_data),
        "unreviewed": len(result.unreviewed),
        "validation_error": len(result.validation_errors),
    }
    total = sum(counts.values())
    assert total == len(rules)
    assert counts == {
        "approved": 2,
        "rejected": 1,
        "held": 1,
        "needs_more_data": 1,
        "unreviewed": 1,
        "validation_error": 1,
    }


def test_rule_ordering_preserved_from_stage14() -> None:
    """ReconciliationResult.rules preserves Stage 14 rule ordering even
    when operator CSV uses a different order."""

    rules = (_rule("rA"), _rule("rB"), _rule("rC"))
    ops = (
        _op("rC", "APPROVE_OBSERVE_ONLY"),
        _op("rA", "APPROVE_OBSERVE_ONLY"),
    )
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"rA": (), "rB": (), "rC": ()},
    )
    assert [r.rule.rule_id for r in result.rules] == ["rA", "rB", "rC"]


def test_operator_row_results_preserve_operator_csv_ordering() -> None:
    rules = (_rule("rA"), _rule("rB"))
    ops = (
        _op("rB", "REJECT", reason="b first", row=2),
        _op("rA", "APPROVE_OBSERVE_ONLY", row=3),
    )
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"rA": (), "rB": ()},
    )
    assert [r.rule.rule_id for r in result.operator_row_results] == ["rB", "rA"]


def test_zero_stage14_rules_zero_operator_rows() -> None:
    result = reconcile(
        stage14_rules=(),
        operator_rows=(),
        warning_flags_by_rule={},
    )
    assert result.rules == ()
    assert result.validation_failures == ()
    assert result.operator_row_results == ()


def test_validation_failures_count_matches_per_row_failures() -> None:
    """A double-failure row contributes two validation_failures entries
    but is counted once in VALIDATION_ERROR bucket."""

    rules = (_rule("r1"),)
    ops = (_op("r1", "APPROVE_OBSERVE_ONLY", reason="", override=False),)
    result = reconcile(
        stage14_rules=rules,
        operator_rows=ops,
        warning_flags_by_rule={"r1": ("small_n_rule",)},
    )
    assert len(result.validation_failures) == 2
    assert len(result.validation_errors) == 1
