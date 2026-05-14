"""Stage 17 descriptive-label rule tests.

Each test exercises one edge in the locked label rule. The standalone
``label_from_delta`` helper is the surface under test; the
``descriptive_label`` wrapper is exercised via metrics tests.
"""

from __future__ import annotations

from PHX2.stage17.labels import (
    HARMFUL,
    INSUFFICIENT_SAMPLE,
    PROMISING,
    WEAK,
    label_from_delta,
)


def test_insufficient_when_matched_side_fails_min_n() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=-0.1,
        meets_min_n_matched=False,
        meets_min_n_not_matched=True,
    )
    assert label == INSUFFICIENT_SAMPLE


def test_insufficient_when_not_matched_side_fails_min_n() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=-0.1,
        meets_min_n_matched=True,
        meets_min_n_not_matched=False,
    )
    assert label == INSUFFICIENT_SAMPLE


def test_insufficient_when_delta_is_none() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=None,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == INSUFFICIENT_SAMPLE


def test_harmful_just_above_zero() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=0.000001,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == HARMFUL


def test_weak_at_zero_exactly() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=0.0,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == WEAK


def test_weak_at_negative_005_exactly() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=-0.05,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == WEAK


def test_promising_just_below_negative_005() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=-0.0500001,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == PROMISING


def test_harmful_above_zero_inclusive_check() -> None:
    """HARMFUL boundary is strictly > 0; verify a clearly-positive value."""

    label = label_from_delta(
        delta_hit_2x_rate=0.25,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == HARMFUL


def test_promising_well_below_threshold() -> None:
    label = label_from_delta(
        delta_hit_2x_rate=-0.5,
        meets_min_n_matched=True,
        meets_min_n_not_matched=True,
    )
    assert label == PROMISING
