"""Phase 3 tests: Stage 16B dataclasses are frozen and accept the locked field set."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from PHX2.stage16b.models import ObserveOnlyEvaluationRow, ObserverRunReport


# ---------------------------------------------------------------------------
# ObserveOnlyEvaluationRow
# ---------------------------------------------------------------------------


def _make_row(**overrides) -> ObserveOnlyEvaluationRow:
    base = {
        "alert_decision_id": 1,
        "tier_name_snapshot": "T1",
        "policy_hash": "sha256:" + "a" * 64,
        "rule_id": "rule_a",
        "evaluation_status": "NOT_MATCHED",
        "matched": 0,
        "would_have_blocked": 0,
        "unevaluable_reason": None,
        "predicate_snapshot_json": "{}",
        "evaluated_at_utc": "2026-05-13T12:00:00+00:00",
    }
    base.update(overrides)
    return ObserveOnlyEvaluationRow(**base)


def test_row_dataclass_is_frozen() -> None:
    row = _make_row()
    with pytest.raises(FrozenInstanceError):
        row.alert_decision_id = 2  # type: ignore[misc]


def test_row_construction_with_optional_none() -> None:
    row = _make_row(tier_name_snapshot=None, unevaluable_reason=None)
    assert row.tier_name_snapshot is None
    assert row.unevaluable_reason is None


def test_row_construction_full_fields() -> None:
    row = _make_row(
        alert_decision_id=42,
        tier_name_snapshot="T2",
        policy_hash="sha256:" + "b" * 64,
        rule_id="rule_b",
        evaluation_status="MATCHED",
        matched=1,
        would_have_blocked=1,
        unevaluable_reason=None,
        predicate_snapshot_json='{"filter_name":"fee_gate"}',
        evaluated_at_utc="2026-05-13T12:30:00+00:00",
    )
    assert row.alert_decision_id == 42
    assert row.tier_name_snapshot == "T2"
    assert row.policy_hash == "sha256:" + "b" * 64
    assert row.rule_id == "rule_b"
    assert row.evaluation_status == "MATCHED"
    assert row.matched == 1
    assert row.would_have_blocked == 1
    assert row.unevaluable_reason is None
    assert row.predicate_snapshot_json == '{"filter_name":"fee_gate"}'
    assert row.evaluated_at_utc == "2026-05-13T12:30:00+00:00"


def test_row_construction_unevaluable_carries_reason() -> None:
    row = _make_row(
        evaluation_status="UNEVALUABLE",
        matched=0,
        would_have_blocked=0,
        unevaluable_reason="tier_name_missing_on_decision",
    )
    assert row.evaluation_status == "UNEVALUABLE"
    assert row.unevaluable_reason == "tier_name_missing_on_decision"


def test_row_does_not_expose_created_at_utc() -> None:
    """``created_at_utc`` is stamped by the repository at insert time.

    The dataclass deliberately does NOT carry it -- callers cannot
    construct rows that pre-bind a creation timestamp.
    """

    row = _make_row()
    assert not hasattr(row, "created_at_utc")


# ---------------------------------------------------------------------------
# ObserverRunReport
# ---------------------------------------------------------------------------


def _make_report(**overrides) -> ObserverRunReport:
    base = {
        "policy_hash": "sha256:" + "c" * 64,
        "policy_rule_count": 2,
        "alert_decisions_evaluated": 3,
        "rows_inserted": 6,
        "rows_ignored_duplicates": 0,
        "decisions_skipped_not_found": 0,
        "matched_count": 1,
        "not_matched_count": 4,
        "unevaluable_count": 1,
        "evaluation_duration_seconds": 0.25,
    }
    base.update(overrides)
    return ObserverRunReport(**base)


def test_report_dataclass_is_frozen() -> None:
    report = _make_report()
    with pytest.raises(FrozenInstanceError):
        report.rows_inserted = 7  # type: ignore[misc]


def test_report_construction_full_fields() -> None:
    report = _make_report(
        policy_hash="sha256:" + "d" * 64,
        policy_rule_count=5,
        alert_decisions_evaluated=10,
        rows_inserted=50,
        rows_ignored_duplicates=2,
        decisions_skipped_not_found=1,
        matched_count=7,
        not_matched_count=40,
        unevaluable_count=3,
        evaluation_duration_seconds=1.875,
    )
    assert report.policy_hash == "sha256:" + "d" * 64
    assert report.policy_rule_count == 5
    assert report.alert_decisions_evaluated == 10
    assert report.rows_inserted == 50
    assert report.rows_ignored_duplicates == 2
    assert report.decisions_skipped_not_found == 1
    assert report.matched_count == 7
    assert report.not_matched_count == 40
    assert report.unevaluable_count == 3
    assert report.evaluation_duration_seconds == 1.875


def test_report_construction_zero_counters() -> None:
    """Empty-policy / limit=0 run produces a clean zero report."""

    report = _make_report(
        policy_rule_count=0,
        alert_decisions_evaluated=0,
        rows_inserted=0,
        rows_ignored_duplicates=0,
        decisions_skipped_not_found=0,
        matched_count=0,
        not_matched_count=0,
        unevaluable_count=0,
        evaluation_duration_seconds=0.0,
    )
    assert report.policy_rule_count == 0
    assert report.alert_decisions_evaluated == 0
    assert report.rows_inserted == 0
    assert report.evaluation_duration_seconds == 0.0
