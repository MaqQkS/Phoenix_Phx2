"""Pure analytical metric helpers for Stage 12.

All functions in this module are pure: no I/O, no DB, no globals. The
helpers are exercised directly by unit tests (Wilson CI, confidence
flag) and through the pipeline orchestrator (compute_cohort_rates).

The cohort-builder helper emits the canonical schema tail shared by
the four cohort CSVs (tier baseline, filter label overall, filter
label by tier, primitive bucket by tier). Callers provide the
grouping keys; this module appends the n_*, hit_*, median_*, and
confidence_flag columns per spec §5.7.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd


WILSON_Z_95 = 1.959963984540054
"""95% confidence-level z-score for the Wilson score interval.

Computed once to match the spec's fixed constant; do NOT recompute via
scipy.stats.norm.ppf at call time -- the deterministic literal is what
TEST 5 asserts against.
"""


CONFIDENCE_FLAG_CAVEAT_THRESHOLD = 10
CONFIDENCE_FLAG_STANDARD_THRESHOLD = 30


COHORT_TAIL_COLUMNS: tuple[str, ...] = (
    "n_decisions",
    "n_with_outcome_window",
    "n_complete",
    "n_censored",
    "n_no_outcome",
    "hit_2x_24h_count",
    "hit_2x_24h_rate",
    "hit_2x_24h_ci_low",
    "hit_2x_24h_ci_high",
    "hit_3x_24h_count",
    "hit_3x_24h_rate",
    "hit_3x_24h_ci_low",
    "hit_3x_24h_ci_high",
    "hit_5x_24h_count",
    "hit_5x_24h_rate",
    "hit_5x_24h_ci_low",
    "hit_5x_24h_ci_high",
    "median_max_return_24h",
    "median_max_drawdown_24h",
    "confidence_flag",
)
"""Canonical n_*, hit_*, median_*, confidence_flag tail (spec §5.7).

The four cohort CSVs share these columns verbatim. Cohort-specific
identity / bucket columns are prepended by the pipeline.
"""


REQUIRED_INPUT_COLUMNS: tuple[str, ...] = (
    "alert_decision_id",
    "has_primary_outcome",
    "outcome_censored_24h",
    "no_outcome_24h",
    "has_outcome_window_24h",
    "primary_outcome_hit_2x_24h",
    "primary_outcome_hit_3x_24h",
    "primary_outcome_hit_5x_24h",
    "outcome_24h_max_return_multiple",
    "outcome_24h_max_drawdown_from_peak_pct",
)


def wilson_ci(
    k: int,
    n: int,
    z: float = WILSON_Z_95,
) -> tuple[float | None, float | None]:
    """Closed-form Wilson score interval for a binomial proportion.

    Returns ``(None, None)`` when ``n == 0`` (undefined proportion).
    Otherwise returns ``(lower, upper)`` clipped to ``[0, 1]``.

    Reference: Wilson, E.B. (1927). "Probable inference, the law of
    succession, and statistical inference." JASA 22:209-212.
    """

    if n == 0:
        return (None, None)
    if k < 0 or k > n:
        raise ValueError(f"k must satisfy 0 <= k <= n; got k={k}, n={n}")

    p_hat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = (
        z * math.sqrt(p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n))
    ) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def confidence_flag(n_complete: int) -> str:
    """Spec M4 confidence flag based on the complete-outcome count.

    Boundaries:
      n_complete <  10 -> "low_confidence"
      10 <= n     <  30 -> "caveat"
      n_complete >= 30 -> "standard"
    """

    if n_complete < CONFIDENCE_FLAG_CAVEAT_THRESHOLD:
        return "low_confidence"
    if n_complete < CONFIDENCE_FLAG_STANDARD_THRESHOLD:
        return "caveat"
    return "standard"


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_cohort_dataframe(group_keys: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=[*group_keys, *COHORT_TAIL_COLUMNS])


def compute_cohort_rates(
    df: pd.DataFrame,
    group_keys: Sequence[str],
) -> pd.DataFrame:
    """Compute the shared cohort schema for an arbitrary grouping.

    For each unique combination of ``group_keys`` values:
      1. Deduplicate to distinct ``alert_decision_id`` within the group.
         (Decision-level outcome attributes are constant across rows of
         the same decision in the long CSV; deduplicating gives the
         correct per-decision aggregates regardless of how many filter
         evaluations attach.)
      2. Count n_decisions, n_with_outcome_window, n_complete,
         n_censored, n_no_outcome (spec M3, M6).
      3. Count hit_2x/3x/5x within the complete subset; compute rates as
         count / n_complete (NULL when n_complete == 0).
      4. Compute Wilson 95% CIs on each rate.
      5. Compute median max_return_24h and median max_drawdown_24h over
         the complete subset.
      6. Emit confidence_flag from n_complete.

    Required columns in ``df``: see ``REQUIRED_INPUT_COLUMNS`` plus all
    columns named in ``group_keys``.

    Returns a DataFrame with one row per unique ``group_keys`` value
    and the canonical cohort tail columns.
    """

    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            "compute_cohort_rates: input is missing required columns "
            f"{missing!r}"
        )
    missing_groups = [col for col in group_keys if col not in df.columns]
    if missing_groups:
        raise ValueError(
            "compute_cohort_rates: group_keys reference missing columns "
            f"{missing_groups!r}"
        )

    if df.empty:
        return _empty_cohort_dataframe(group_keys)

    dedupe_keys = [*group_keys, "alert_decision_id"]
    decisions_in_group = df.drop_duplicates(subset=dedupe_keys)

    grouped = decisions_in_group.groupby(list(group_keys), dropna=False, sort=False)

    out_rows: list[dict[str, object]] = []
    for key_tuple, sub in grouped:
        if not isinstance(key_tuple, tuple):
            key_tuple = (key_tuple,)

        row: dict[str, object] = {}
        for col, val in zip(group_keys, key_tuple):
            row[col] = val

        n_decisions = int(len(sub))
        n_with_outcome_window = int(sub["has_outcome_window_24h"].fillna(False).sum())
        n_complete = int(sub["has_primary_outcome"].fillna(False).sum())
        n_censored = int(sub["outcome_censored_24h"].fillna(False).sum())
        n_no_outcome = int(sub["no_outcome_24h"].fillna(False).sum())

        complete_sub = sub[sub["has_primary_outcome"].fillna(False).astype(bool)]

        row["n_decisions"] = n_decisions
        row["n_with_outcome_window"] = n_with_outcome_window
        row["n_complete"] = n_complete
        row["n_censored"] = n_censored
        row["n_no_outcome"] = n_no_outcome

        for hit_name in ("hit_2x", "hit_3x", "hit_5x"):
            src_col = f"primary_outcome_{hit_name}_24h"
            count = int(complete_sub[src_col].fillna(False).sum()) if n_complete else 0
            if n_complete > 0:
                rate: float | None = count / n_complete
                ci_low, ci_high = wilson_ci(count, n_complete)
            else:
                rate, ci_low, ci_high = None, None, None
            row[f"{hit_name}_24h_count"] = count
            row[f"{hit_name}_24h_rate"] = rate
            row[f"{hit_name}_24h_ci_low"] = ci_low
            row[f"{hit_name}_24h_ci_high"] = ci_high

        if n_complete > 0:
            median_return = complete_sub["outcome_24h_max_return_multiple"].median(skipna=True)
            median_drawdown = complete_sub["outcome_24h_max_drawdown_from_peak_pct"].median(skipna=True)
            row["median_max_return_24h"] = _to_optional_float(median_return)
            row["median_max_drawdown_24h"] = _to_optional_float(median_drawdown)
        else:
            row["median_max_return_24h"] = None
            row["median_max_drawdown_24h"] = None

        row["confidence_flag"] = confidence_flag(n_complete)
        out_rows.append(row)

    if not out_rows:
        return _empty_cohort_dataframe(group_keys)

    out = pd.DataFrame(out_rows, columns=[*group_keys, *COHORT_TAIL_COLUMNS])
    return out
