"""Phase 18.2 metrics tests.

Pure-function tests for ``compute_unevaluable_rate``,
``compute_incomplete_outcome_ratio``, and
``compute_tier_coverage``. Inputs are constructed inline as
small in-memory dicts -- no disk fixtures, no Stage 17 imports.
"""

from __future__ import annotations

import pytest

from PHX2.stage18.constants import (
    TIER_COVERAGE_MULTI_TIER,
    TIER_COVERAGE_NO_HEADLINE_ROWS,
    TIER_COVERAGE_SINGLE_TIER_ONLY,
)
from PHX2.stage18.metrics import (
    compute_incomplete_outcome_ratio,
    compute_tier_coverage,
    compute_unevaluable_rate,
)


# ---------------------------------------------------------------------------
# Local builders (only the fields each function reads)
# ---------------------------------------------------------------------------


def _headline(
    *,
    n_in_scope: int,
    n_unevaluable: int,
    tier: str = "T1",
) -> dict:
    return {
        "tier_name_snapshot": tier,
        "n_in_scope": str(n_in_scope),
        "n_unevaluable": str(n_unevaluable),
    }


def _dq_row(
    *,
    metric_name: str = "n_outcome_present_but_incomplete",
    metric_value: int = 0,
    scope_level: str = "slice",
) -> dict:
    return {
        "scope_level": scope_level,
        "metric_name": metric_name,
        "metric_value": str(metric_value),
    }


# ---------------------------------------------------------------------------
# compute_unevaluable_rate
# ---------------------------------------------------------------------------


def test_unevaluable_rate_multi_tier_summed() -> None:
    """Sum n_unevaluable / sum n_in_scope across tiers."""

    rows = [
        _headline(n_in_scope=100, n_unevaluable=10, tier="T1"),
        _headline(n_in_scope=200, n_unevaluable=40, tier="T2"),
    ]
    # (10 + 40) / (100 + 200) = 50 / 300
    assert compute_unevaluable_rate(rows) == pytest.approx(50 / 300)


def test_unevaluable_rate_single_tier_sum() -> None:
    rows = [_headline(n_in_scope=100, n_unevaluable=25, tier="T1")]
    assert compute_unevaluable_rate(rows) == 0.25


def test_unevaluable_rate_no_headline_rows_returns_none() -> None:
    assert compute_unevaluable_rate([]) is None


def test_unevaluable_rate_zero_denominator_returns_none() -> None:
    rows = [
        _headline(n_in_scope=0, n_unevaluable=0, tier="T1"),
        _headline(n_in_scope=0, n_unevaluable=0, tier="T2"),
    ]
    assert compute_unevaluable_rate(rows) is None


# ---------------------------------------------------------------------------
# compute_incomplete_outcome_ratio
# ---------------------------------------------------------------------------


def test_incomplete_ratio_one_matching_slice_row() -> None:
    rows = [_dq_row(metric_value=10)]
    assert compute_incomplete_outcome_ratio(rows, 100) == 0.10


def test_incomplete_ratio_multiple_matching_slice_rows_summed() -> None:
    rows = [
        _dq_row(metric_value=5),
        _dq_row(metric_value=15),
    ]
    # (5 + 15) / 100 = 0.20
    assert compute_incomplete_outcome_ratio(rows, 100) == 0.20


def test_incomplete_ratio_ignores_global_rows() -> None:
    """Global-scope rows are filtered out even when they carry
    the same metric_name."""

    rows = [
        _dq_row(metric_value=5, scope_level="slice"),
        _dq_row(metric_value=999, scope_level="global"),
        _dq_row(
            metric_value=12,
            scope_level="global",
            metric_name="orphan_evaluations",
        ),
    ]
    # Only the single slice row contributes (5); 999 and 12 ignored.
    assert compute_incomplete_outcome_ratio(rows, 100) == 0.05


def test_incomplete_ratio_no_matching_slice_rows_returns_zero() -> None:
    """No matching slice rows but denominator > 0 -> 0.0."""

    rows = [
        _dq_row(
            metric_value=99,
            scope_level="global",
            metric_name="orphan_evaluations",
        ),
    ]
    assert compute_incomplete_outcome_ratio(rows, 100) == 0.0


def test_incomplete_ratio_zero_n_with_complete_outcome_returns_none() -> None:
    rows = [_dq_row(metric_value=10)]
    assert compute_incomplete_outcome_ratio(rows, 0) is None


# ---------------------------------------------------------------------------
# compute_tier_coverage
# ---------------------------------------------------------------------------


def test_tier_coverage_zero_rows_returns_no_headline_rows() -> None:
    assert compute_tier_coverage([]) == TIER_COVERAGE_NO_HEADLINE_ROWS


def test_tier_coverage_one_tier_returns_single_tier_only() -> None:
    rows = [
        _headline(n_in_scope=100, n_unevaluable=0, tier="T1"),
        _headline(n_in_scope=50, n_unevaluable=0, tier="T1"),
    ]
    assert compute_tier_coverage(rows) == TIER_COVERAGE_SINGLE_TIER_ONLY


def test_tier_coverage_two_or_more_tiers_returns_multi_tier() -> None:
    rows = [
        _headline(n_in_scope=100, n_unevaluable=0, tier="T1"),
        _headline(n_in_scope=50, n_unevaluable=0, tier="T2"),
        _headline(n_in_scope=10, n_unevaluable=0, tier="T3"),
    ]
    assert compute_tier_coverage(rows) == TIER_COVERAGE_MULTI_TIER


def test_tier_coverage_null_tier_distinct_from_named_tier() -> None:
    """An empty / NULL tier_name_snapshot counts as its own
    distinct value, so a NULL + named-tier pair is multi_tier."""

    rows = [
        _headline(n_in_scope=100, n_unevaluable=0, tier=""),
        _headline(n_in_scope=50, n_unevaluable=0, tier="T2"),
    ]
    assert compute_tier_coverage(rows) == TIER_COVERAGE_MULTI_TIER
