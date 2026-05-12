"""Stage 12 metrics unit tests (TEST 5, TEST 11 + cohort-builder smoke)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from PHX2.analysis.metrics import (
    COHORT_TAIL_COLUMNS,
    WILSON_Z_95,
    compute_cohort_rates,
    confidence_flag,
    wilson_ci,
)


# ---------------------------------------------------------------------------
# TEST 5 -- Wilson CI
# ---------------------------------------------------------------------------


def _assert_ci_approx(
    actual: tuple[float | None, float | None],
    expected: tuple[float | None, float | None],
    tol: float = 5e-4,
) -> None:
    actual_low, actual_high = actual
    exp_low, exp_high = expected
    if exp_low is None:
        assert actual_low is None
    else:
        assert actual_low is not None
        assert math.isclose(actual_low, exp_low, abs_tol=tol), (
            f"lower {actual_low!r} != {exp_low!r} (tol={tol})"
        )
    if exp_high is None:
        assert actual_high is None
    else:
        assert actual_high is not None
        assert math.isclose(actual_high, exp_high, abs_tol=tol), (
            f"upper {actual_high!r} != {exp_high!r} (tol={tol})"
        )


def test_wilson_z_constant_is_locked() -> None:
    # TEST 5 prerequisite: the z-score literal MUST match the spec value
    # exactly. Re-deriving via scipy or any other path is forbidden.
    assert WILSON_Z_95 == 1.959963984540054


def test_wilson_ci_n_zero_returns_pair_of_none() -> None:
    assert wilson_ci(0, 0) == (None, None)


def test_wilson_ci_k_zero_n_ten() -> None:
    # p=0, n=10. Wilson lower clipped to 0; upper around 0.27753.
    _assert_ci_approx(wilson_ci(0, 10), (0.0, 0.2775))


def test_wilson_ci_k_five_n_ten() -> None:
    # p=0.5, n=10. Symmetric around 0.5: (0.23660, 0.76340).
    _assert_ci_approx(wilson_ci(5, 10), (0.2366, 0.7634))


def test_wilson_ci_k_ten_n_ten() -> None:
    # p=1, n=10. Wilson upper clipped to 1; lower around 0.72247.
    _assert_ci_approx(wilson_ci(10, 10), (0.7225, 1.0))


def test_wilson_ci_k_one_n_one() -> None:
    # p=1, n=1. Lower around 0.20654; upper clipped to 1.
    _assert_ci_approx(wilson_ci(1, 1), (0.2065, 1.0))


def test_wilson_ci_rejects_out_of_range_k() -> None:
    with pytest.raises(ValueError):
        wilson_ci(-1, 10)
    with pytest.raises(ValueError):
        wilson_ci(11, 10)


# ---------------------------------------------------------------------------
# TEST 11 -- confidence_flag boundary test
# ---------------------------------------------------------------------------


def test_confidence_flag_low_confidence_below_ten() -> None:
    assert confidence_flag(0) == "low_confidence"
    assert confidence_flag(9) == "low_confidence"


def test_confidence_flag_caveat_at_ten_through_twentynine() -> None:
    assert confidence_flag(10) == "caveat"
    assert confidence_flag(29) == "caveat"


def test_confidence_flag_standard_at_thirty_and_above() -> None:
    assert confidence_flag(30) == "standard"
    assert confidence_flag(100) == "standard"


# ---------------------------------------------------------------------------
# compute_cohort_rates -- smoke coverage (full pipeline test in Phase 4)
# ---------------------------------------------------------------------------


def _make_long_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Coerce nullable boolean / float dtypes the pipeline will use.
    for col in (
        "has_primary_outcome",
        "outcome_censored_24h",
        "no_outcome_24h",
        "has_outcome_window_24h",
        "primary_outcome_hit_2x_24h",
        "primary_outcome_hit_3x_24h",
        "primary_outcome_hit_5x_24h",
    ):
        if col in df.columns:
            df[col] = df[col].astype("boolean")
    for col in (
        "outcome_24h_max_return_multiple",
        "outcome_24h_max_drawdown_from_peak_pct",
    ):
        if col in df.columns:
            df[col] = df[col].astype("Float64")
    return df


def test_compute_cohort_rates_empty_input_returns_empty_canonical_schema() -> None:
    df = _make_long_df([
        {
            "alert_decision_id": 1,
            "tier_index": 2,
            "has_primary_outcome": True,
            "outcome_censored_24h": False,
            "no_outcome_24h": False,
            "has_outcome_window_24h": True,
            "primary_outcome_hit_2x_24h": True,
            "primary_outcome_hit_3x_24h": False,
            "primary_outcome_hit_5x_24h": False,
            "outcome_24h_max_return_multiple": 2.5,
            "outcome_24h_max_drawdown_from_peak_pct": -10.0,
        },
    ]).iloc[0:0]  # drop all rows but keep schema
    out = compute_cohort_rates(df, ["tier_index"])
    assert list(out.columns) == ["tier_index", *COHORT_TAIL_COLUMNS]
    assert len(out) == 0


def test_compute_cohort_rates_two_decision_test3_fixture() -> None:
    # Spec TEST 3 expected shape:
    # n_decisions=2, n_complete=1, n_censored=1, hit_2x_24h_count=1,
    # hit_2x_24h_rate=1.0. The third bucket added per operator
    # clarification: n_no_outcome=0.
    df = _make_long_df([
        {
            "alert_decision_id": 100,
            "tier_index": 1,
            "has_primary_outcome": True,
            "outcome_censored_24h": False,
            "no_outcome_24h": False,
            "has_outcome_window_24h": True,
            "primary_outcome_hit_2x_24h": True,
            "primary_outcome_hit_3x_24h": False,
            "primary_outcome_hit_5x_24h": False,
            "outcome_24h_max_return_multiple": 2.5,
            "outcome_24h_max_drawdown_from_peak_pct": -10.0,
        },
        {
            "alert_decision_id": 101,
            "tier_index": 1,
            "has_primary_outcome": False,
            "outcome_censored_24h": True,
            "no_outcome_24h": False,
            "has_outcome_window_24h": True,
            "primary_outcome_hit_2x_24h": None,
            "primary_outcome_hit_3x_24h": None,
            "primary_outcome_hit_5x_24h": None,
            "outcome_24h_max_return_multiple": None,
            "outcome_24h_max_drawdown_from_peak_pct": None,
        },
    ])
    out = compute_cohort_rates(df, ["tier_index"])
    assert len(out) == 1
    row = out.iloc[0]
    assert int(row["tier_index"]) == 1
    assert int(row["n_decisions"]) == 2
    assert int(row["n_with_outcome_window"]) == 2
    assert int(row["n_complete"]) == 1
    assert int(row["n_censored"]) == 1
    assert int(row["n_no_outcome"]) == 0
    assert int(row["hit_2x_24h_count"]) == 1
    assert row["hit_2x_24h_rate"] == 1.0
    assert row["hit_2x_24h_ci_low"] is not None
    assert row["hit_2x_24h_ci_high"] == 1.0
    # n_complete=1 -> "low_confidence"
    assert row["confidence_flag"] == "low_confidence"
    # Medians over the single complete row.
    assert float(row["median_max_return_24h"]) == 2.5
    assert float(row["median_max_drawdown_24h"]) == -10.0


def test_compute_cohort_rates_no_outcome_bucket_distinct_from_censored() -> None:
    df = _make_long_df([
        {
            "alert_decision_id": 200,
            "tier_index": 2,
            "has_primary_outcome": False,
            "outcome_censored_24h": False,
            "no_outcome_24h": True,
            "has_outcome_window_24h": False,
            "primary_outcome_hit_2x_24h": None,
            "primary_outcome_hit_3x_24h": None,
            "primary_outcome_hit_5x_24h": None,
            "outcome_24h_max_return_multiple": None,
            "outcome_24h_max_drawdown_from_peak_pct": None,
        },
    ])
    out = compute_cohort_rates(df, ["tier_index"])
    row = out.iloc[0]
    assert int(row["n_decisions"]) == 1
    assert int(row["n_with_outcome_window"]) == 0
    assert int(row["n_complete"]) == 0
    assert int(row["n_censored"]) == 0
    assert int(row["n_no_outcome"]) == 1
    assert row["hit_2x_24h_rate"] is None
    assert row["hit_2x_24h_ci_low"] is None
    assert row["hit_2x_24h_ci_high"] is None
    assert row["median_max_return_24h"] is None
    assert row["confidence_flag"] == "low_confidence"


def test_compute_cohort_rates_deduplicates_decisions_within_group() -> None:
    # One decision with two filter-eval rows; cohort counts it ONCE.
    df = _make_long_df([
        {
            "alert_decision_id": 300,
            "tier_index": 3,
            "has_primary_outcome": True,
            "outcome_censored_24h": False,
            "no_outcome_24h": False,
            "has_outcome_window_24h": True,
            "primary_outcome_hit_2x_24h": True,
            "primary_outcome_hit_3x_24h": True,
            "primary_outcome_hit_5x_24h": False,
            "outcome_24h_max_return_multiple": 3.2,
            "outcome_24h_max_drawdown_from_peak_pct": -5.0,
        },
        {
            "alert_decision_id": 300,
            "tier_index": 3,
            "has_primary_outcome": True,
            "outcome_censored_24h": False,
            "no_outcome_24h": False,
            "has_outcome_window_24h": True,
            "primary_outcome_hit_2x_24h": True,
            "primary_outcome_hit_3x_24h": True,
            "primary_outcome_hit_5x_24h": False,
            "outcome_24h_max_return_multiple": 3.2,
            "outcome_24h_max_drawdown_from_peak_pct": -5.0,
        },
    ])
    out = compute_cohort_rates(df, ["tier_index"])
    assert len(out) == 1
    row = out.iloc[0]
    assert int(row["n_decisions"]) == 1
    assert int(row["n_complete"]) == 1
    assert int(row["hit_2x_24h_count"]) == 1


def test_compute_cohort_rates_rejects_missing_required_columns() -> None:
    bad = pd.DataFrame([{"alert_decision_id": 1}])
    with pytest.raises(ValueError, match="missing required columns"):
        compute_cohort_rates(bad, ["alert_decision_id"])
