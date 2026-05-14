"""Stage 18 derived-metric helpers (pure, no I/O).

Three pure functions produce the per-slice metrics the classifier
consumes. Inputs are CSV-derived row dicts (string-valued cells);
outputs are typed numerics or one of the three locked tier-coverage
literals. No file or DB access, no logging, no global state.

NULL conventions (mirror Stage 17's behavior):

  * ``compute_unevaluable_rate`` returns ``None`` whenever the
    derived rate is undefined (no headline rows, or the in-scope
    denominator is zero).
  * ``compute_incomplete_outcome_ratio`` returns ``None`` only
    when ``n_with_complete_outcome == 0``; any other path
    (including "no matching slice rows but denominator > 0")
    returns a numeric ratio (which may legitimately be 0.0).
  * ``compute_tier_coverage`` returns exactly one of the three
    locked literals from ``PHX2.stage18.constants``; NULL/empty
    ``tier_name_snapshot`` counts as a distinct tier value.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from PHX2.stage18.constants import (
    TIER_COVERAGE_MULTI_TIER,
    TIER_COVERAGE_NO_HEADLINE_ROWS,
    TIER_COVERAGE_SINGLE_TIER_ONLY,
)


def compute_unevaluable_rate(
    headline_rows: Sequence[Mapping[str, str]],
) -> Optional[float]:
    """Return ``sum(n_unevaluable) / sum(n_in_scope)`` over the
    given headline rows, or ``None`` if the rate is undefined.

    Both sums are taken across every tier-level headline row for
    a single (policy_hash, rule_id, window_seconds) slice. The
    callers in ``classifier.classify_row`` always pass the
    pre-filtered set; this function does no matching of its own.
    """

    if not headline_rows:
        return None
    total_unevaluable = sum(int(row["n_unevaluable"]) for row in headline_rows)
    total_in_scope = sum(int(row["n_in_scope"]) for row in headline_rows)
    if total_in_scope == 0:
        return None
    return total_unevaluable / total_in_scope


def compute_incomplete_outcome_ratio(
    data_quality_rows: Sequence[Mapping[str, str]],
    n_with_complete_outcome: int,
) -> Optional[float]:
    """Return the incomplete-outcome ratio for one slice.

    Filters ``data_quality_rows`` to rows with
    ``scope_level == "slice"`` AND
    ``metric_name == "n_outcome_present_but_incomplete"``; sums
    the matching ``metric_value`` cells; divides by
    ``n_with_complete_outcome``.

    Returns:
        ``None`` when ``n_with_complete_outcome == 0`` (the
        denominator is undefined; this is the dedicated G5
        ``complete_outcome_zero`` path).

        Otherwise a numeric ratio. With no matching slice rows
        the numerator is 0 and the function returns ``0.0``.

    Global-scope rows are always ignored, even when they happen
    to carry the same ``metric_name`` (the Stage 17 writer never
    does this, but Stage 18 defends against it anyway).
    """

    if n_with_complete_outcome == 0:
        return None
    total_incomplete = 0
    for row in data_quality_rows:
        if (
            row.get("scope_level") == "slice"
            and row.get("metric_name") == "n_outcome_present_but_incomplete"
        ):
            total_incomplete += int(row["metric_value"])
    return total_incomplete / n_with_complete_outcome


def compute_tier_coverage(
    headline_rows: Sequence[Mapping[str, str]],
) -> str:
    """Return the tier-coverage flag for one slice.

    Locked output values (all defined as constants in
    ``PHX2.stage18.constants``):
      * ``no_headline_rows`` if ``headline_rows`` is empty.
      * ``single_tier_only`` if exactly one distinct
        ``tier_name_snapshot`` value is present.
      * ``multi_tier`` if two or more distinct
        ``tier_name_snapshot`` values are present.

    Empty / NULL ``tier_name_snapshot`` counts as a distinct
    value: a slice with one NULL row and one ``"T2"`` row is
    ``multi_tier``, not ``single_tier_only``.
    """

    if not headline_rows:
        return TIER_COVERAGE_NO_HEADLINE_ROWS
    distinct_tiers = {row["tier_name_snapshot"] for row in headline_rows}
    if len(distinct_tiers) == 1:
        return TIER_COVERAGE_SINGLE_TIER_ONLY
    return TIER_COVERAGE_MULTI_TIER


__all__ = [
    "compute_incomplete_outcome_ratio",
    "compute_tier_coverage",
    "compute_unevaluable_rate",
]
