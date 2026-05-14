"""Stage 17 descriptive-label rule.

The locked label rule applied to a single headline-row context:

  INSUFFICIENT_SAMPLE: meets_min_n_matched is False
                        OR meets_min_n_not_matched is False.
  HARMFUL: delta_hit_2x_rate > 0.0
  WEAK: -0.05 <= delta_hit_2x_rate <= 0.0
  PROMISING: delta_hit_2x_rate < -0.05

The MIXED_BY_TIER coarse-summary label is computed by the metrics
module, not here; it is a cross-row signal that the per-row labeler
cannot see.
"""

from __future__ import annotations

from typing import Protocol


class _HeadlineRowLike(Protocol):
    meets_min_n_matched: bool
    meets_min_n_not_matched: bool
    delta_hit_2x_rate: float | None


INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
HARMFUL = "HARMFUL"
WEAK = "WEAK"
PROMISING = "PROMISING"


_WEAK_LOWER_BOUND = -0.05


def descriptive_label(row: _HeadlineRowLike) -> str:
    """Return the descriptive label for ``row``.

    The function is pure and does not look at any column beyond the
    three listed on the Protocol.
    """

    if not row.meets_min_n_matched or not row.meets_min_n_not_matched:
        return INSUFFICIENT_SAMPLE
    delta = row.delta_hit_2x_rate
    if delta is None:
        return INSUFFICIENT_SAMPLE
    if delta > 0.0:
        return HARMFUL
    if _WEAK_LOWER_BOUND <= delta <= 0.0:
        return WEAK
    return PROMISING


def label_from_delta(
    delta_hit_2x_rate: float | None,
    meets_min_n_matched: bool,
    meets_min_n_not_matched: bool,
) -> str:
    """Standalone variant used by the coarse-summary aggregation.

    The coarse summary aggregates over tiers and does not always have
    a HeadlineMetricRow on hand; this entry point lets the metrics
    module reuse the same rule without constructing a temporary row.
    """

    if not meets_min_n_matched or not meets_min_n_not_matched:
        return INSUFFICIENT_SAMPLE
    if delta_hit_2x_rate is None:
        return INSUFFICIENT_SAMPLE
    if delta_hit_2x_rate > 0.0:
        return HARMFUL
    if _WEAK_LOWER_BOUND <= delta_hit_2x_rate <= 0.0:
        return WEAK
    return PROMISING
