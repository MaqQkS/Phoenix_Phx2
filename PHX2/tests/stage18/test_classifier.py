"""Phase 18.2 classifier tests.

Pure-function tests for ``classify_row``. Each test builds
in-memory dicts and asserts on the returned
``ClassificationResult``. No disk I/O, no fixtures, no Stage 17
imports.
"""

from __future__ import annotations

import pytest

from PHX2.stage18.classifier import classify_row
from PHX2.stage18.constants import (
    REVIEW_LABEL_DATA_BLOCKED,
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_WEAK,
    TIER_COVERAGE_MULTI_TIER,
    TIER_COVERAGE_NO_HEADLINE_ROWS,
    TIER_COVERAGE_SINGLE_TIER_ONLY,
)
from PHX2.stage18.errors import Stage18Error


# ---------------------------------------------------------------------------
# Local minimal builders (only the columns the classifier actually reads)
# ---------------------------------------------------------------------------


def _coarse(
    *,
    n_in_scope: int = 100,
    n_matched: int = 40,
    n_not_matched: int = 60,
    n_with_complete_outcome: int = 100,
    descriptive_label: str = "PROMISING",
) -> dict:
    return {
        "policy_hash": "abc123def456",
        "rule_id": "rule_x",
        "window_seconds": "3600",
        "window_label": "1h",
        "n_in_scope": str(n_in_scope),
        "n_matched": str(n_matched),
        "n_not_matched": str(n_not_matched),
        "n_with_complete_outcome": str(n_with_complete_outcome),
        "hit_2x_rate_matched": "0.200000",
        "hit_2x_rate_not_matched": "0.100000",
        "delta_hit_2x_rate": "0.100000",
        "descriptive_label": descriptive_label,
    }


def _headline(
    *,
    n_in_scope: int = 100,
    n_unevaluable: int = 0,
    tier: str = "T1",
) -> dict:
    return {
        "tier_name_snapshot": tier,
        "n_in_scope": str(n_in_scope),
        "n_unevaluable": str(n_unevaluable),
    }


def _dq_row(*, metric_value: int = 0) -> dict:
    return {
        "scope_level": "slice",
        "metric_name": "n_outcome_present_but_incomplete",
        "metric_value": str(metric_value),
    }


# ---------------------------------------------------------------------------
# Group A happy paths (no gates trip)
# ---------------------------------------------------------------------------


def test_promising_review_happy_path() -> None:
    result = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_PROMISING
    assert result.stage17_label_preserved == "PROMISING"
    assert result.insufficient_sample_reason == ""
    assert result.data_block_reason == ""
    assert result.gate_trips_all == ""
    assert result.tier_coverage == TIER_COVERAGE_SINGLE_TIER_ONLY


def test_weak_review_happy_path() -> None:
    result = classify_row(
        coarse_row=_coarse(descriptive_label="WEAK"),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_WEAK
    assert result.stage17_label_preserved == "WEAK"
    assert result.gate_trips_all == ""


def test_harmful_review_happy_path() -> None:
    result = classify_row(
        coarse_row=_coarse(descriptive_label="HARMFUL"),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_HARMFUL
    assert result.stage17_label_preserved == "HARMFUL"
    assert result.gate_trips_all == ""


def test_mixed_by_tier_review_happy_path() -> None:
    """MIXED_BY_TIER from Stage 17 maps to MIXED_BY_TIER_REVIEW.

    Use multi-tier headlines since MIXED_BY_TIER is by
    construction a multi-tier signal.
    """

    result = classify_row(
        coarse_row=_coarse(descriptive_label="MIXED_BY_TIER"),
        headline_rows_for_slice=[
            _headline(tier="T1"),
            _headline(tier="T2"),
        ],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_MIXED_BY_TIER
    assert result.stage17_label_preserved == "MIXED_BY_TIER"
    assert result.gate_trips_all == ""
    assert result.tier_coverage == TIER_COVERAGE_MULTI_TIER


# ---------------------------------------------------------------------------
# INSUFFICIENT_SAMPLE_REVIEW (Group B)
# ---------------------------------------------------------------------------


def test_insufficient_sample_review_from_stage17_label() -> None:
    """Stage 17 was already INSUFFICIENT_SAMPLE; Stage 18 gates
    pass; classification mirrors the label with no Stage 18 gate
    reason."""

    result = classify_row(
        coarse_row=_coarse(descriptive_label="INSUFFICIENT_SAMPLE"),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.insufficient_sample_reason == ""
    assert result.gate_trips_all == ""
    assert result.stage17_label_preserved == "INSUFFICIENT_SAMPLE"


def test_insufficient_sample_review_from_g1() -> None:
    result = classify_row(
        coarse_row=_coarse(
            n_matched=5,  # < MIN_RULE_POSITIVE_COUNT (10)
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.insufficient_sample_reason == "G1"
    assert result.data_block_reason == ""
    assert result.gate_trips_all == "G1"
    assert result.stage17_label_preserved == "PROMISING"  # Preserved


def test_insufficient_sample_review_from_g2() -> None:
    result = classify_row(
        coarse_row=_coarse(
            n_not_matched=5,  # < MIN_RULE_NEGATIVE_COUNT (10)
            descriptive_label="HARMFUL",
        ),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.insufficient_sample_reason == "G2"
    assert result.gate_trips_all == "G2"
    assert result.stage17_label_preserved == "HARMFUL"


def test_insufficient_sample_review_from_g3() -> None:
    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=20,  # < MIN_EVALUABLE_COUNT (30)
            n_matched=10,
            n_not_matched=10,
            n_with_complete_outcome=20,
            descriptive_label="WEAK",
        ),
        headline_rows_for_slice=[_headline(n_in_scope=20)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.insufficient_sample_reason == "G3"
    assert result.gate_trips_all == "G3"
    assert result.stage17_label_preserved == "WEAK"


# ---------------------------------------------------------------------------
# DATA_BLOCKED_REVIEW (Group C)
# ---------------------------------------------------------------------------


def test_data_blocked_review_from_g4() -> None:
    result = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        # 30/100 = 0.30 > MAX_UNEVALUABLE_RATE (0.25)
        headline_rows_for_slice=[_headline(n_in_scope=100, n_unevaluable=30)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.data_block_reason == "G4"
    assert result.gate_trips_all == "G4"
    assert result.stage17_label_preserved == "PROMISING"
    assert result.unevaluable_rate == pytest.approx(0.30)


def test_data_blocked_review_from_g5_ratio() -> None:
    result = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[_headline()],
        # 60/100 = 0.60 > MAX_INCOMPLETE_OUTCOME_RATIO (0.50)
        data_quality_rows_for_slice=[_dq_row(metric_value=60)],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.data_block_reason == "G5"
    assert result.gate_trips_all == "G5"
    assert result.incomplete_outcome_ratio == pytest.approx(0.60)


def test_data_blocked_review_from_g5_complete_outcome_zero() -> None:
    """When n_with_complete_outcome is zero the ratio is
    undefined; G5 trips with the ``complete_outcome_zero``
    sub-reason."""

    result = classify_row(
        coarse_row=_coarse(
            n_with_complete_outcome=0,  # zero denominator
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.data_block_reason == "G5:complete_outcome_zero"
    assert "G5" in result.gate_trips_all
    assert result.incomplete_outcome_ratio is None


def test_data_blocked_review_from_g6_headline_rows_missing() -> None:
    result = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[],  # triggers G6
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.data_block_reason == "G6"
    assert "G6" in result.gate_trips_all
    assert result.tier_coverage == TIER_COVERAGE_NO_HEADLINE_ROWS
    assert result.unevaluable_rate is None  # No headline rows
    assert result.stage17_label_preserved == "PROMISING"


# ---------------------------------------------------------------------------
# Sample-gate precedence
# ---------------------------------------------------------------------------


def test_sample_gate_precedence_g1_and_g4() -> None:
    """G1 (sample) + G4 (data quality) both trip; the classifier
    picks INSUFFICIENT_SAMPLE_REVIEW, clears data_block_reason,
    and retains both gates in gate_trips_all."""

    result = classify_row(
        coarse_row=_coarse(
            n_matched=5,  # G1
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[
            _headline(n_in_scope=100, n_unevaluable=30),  # G4: 0.30 > 0.25
        ],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.insufficient_sample_reason == "G1"
    assert result.data_block_reason == ""  # cleared
    assert result.gate_trips_all == "G1;G4"  # both, in eval order
    assert result.stage17_label_preserved == "PROMISING"


# ---------------------------------------------------------------------------
# B03 -- unknown Stage 17 label
# ---------------------------------------------------------------------------


def test_unknown_stage17_label_raises_b03() -> None:
    with pytest.raises(Stage18Error) as exc_info:
        classify_row(
            coarse_row=_coarse(descriptive_label="BANANA"),
            headline_rows_for_slice=[_headline()],
            data_quality_rows_for_slice=[],
        )
    assert exc_info.value.code == "B03"
    assert "BANANA" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------


def test_n_matched_at_10_passes_g1() -> None:
    """Boundary: n_matched == MIN_RULE_POSITIVE_COUNT (10) is the
    smallest value that does NOT trip G1."""

    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=30,
            n_matched=10,
            n_not_matched=20,
            n_with_complete_outcome=30,
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[_headline(n_in_scope=30)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_PROMISING
    assert "G1" not in result.gate_trips_all


def test_n_matched_at_9_trips_g1() -> None:
    """Boundary: n_matched == 9 is just below threshold and
    trips G1."""

    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=30,
            n_matched=9,
            n_not_matched=21,
            n_with_complete_outcome=30,
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[_headline(n_in_scope=30)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.insufficient_sample_reason == "G1"


def test_unevaluable_rate_at_threshold_passes_g4() -> None:
    """unevaluable_rate == MAX_UNEVALUABLE_RATE (0.25) is the
    largest value that does NOT trip G4 (strict ``>``)."""

    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=100, n_matched=20, n_not_matched=55,
            n_with_complete_outcome=75,
            descriptive_label="PROMISING",
        ),
        # 25/100 = 0.25 exactly
        headline_rows_for_slice=[_headline(n_in_scope=100, n_unevaluable=25)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_PROMISING
    assert "G4" not in result.gate_trips_all
    assert result.unevaluable_rate == 0.25


def test_unevaluable_rate_just_above_threshold_trips_g4() -> None:
    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=100, n_matched=20, n_not_matched=54,
            n_with_complete_outcome=74,
            descriptive_label="PROMISING",
        ),
        # 26/100 = 0.26
        headline_rows_for_slice=[_headline(n_in_scope=100, n_unevaluable=26)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.data_block_reason == "G4"
    assert result.unevaluable_rate == pytest.approx(0.26)


def test_incomplete_outcome_ratio_at_threshold_passes_g5() -> None:
    """incomplete_outcome_ratio == 0.50 is the largest value that
    does NOT trip G5 (strict ``>``)."""

    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=100, n_matched=20, n_not_matched=80,
            n_with_complete_outcome=100,
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[_headline()],
        # 50/100 = 0.50 exactly
        data_quality_rows_for_slice=[_dq_row(metric_value=50)],
    )
    assert result.classification == REVIEW_LABEL_PROMISING
    assert "G5" not in result.gate_trips_all
    assert result.incomplete_outcome_ratio == 0.50


def test_incomplete_outcome_ratio_just_above_threshold_trips_g5() -> None:
    result = classify_row(
        coarse_row=_coarse(
            n_in_scope=100, n_matched=20, n_not_matched=80,
            n_with_complete_outcome=100,
            descriptive_label="PROMISING",
        ),
        headline_rows_for_slice=[_headline()],
        # 51/100 = 0.51
        data_quality_rows_for_slice=[_dq_row(metric_value=51)],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.data_block_reason == "G5"
    assert result.incomplete_outcome_ratio == pytest.approx(0.51)


# ---------------------------------------------------------------------------
# Cross-cutting checks
# ---------------------------------------------------------------------------


def test_stage17_label_preserved_on_every_classification_path() -> None:
    """stage17_label_preserved is populated on every code path:
    Group A direct mapping, Group B sample override, Group C
    data-quality override."""

    # Group A: each accepted Stage 17 label maps to its own _REVIEW.
    group_a_labels = (
        "PROMISING", "WEAK", "HARMFUL", "MIXED_BY_TIER", "INSUFFICIENT_SAMPLE",
    )
    for label in group_a_labels:
        headlines = (
            [_headline(tier="T1"), _headline(tier="T2")]
            if label == "MIXED_BY_TIER"
            else [_headline()]
        )
        result = classify_row(
            coarse_row=_coarse(descriptive_label=label),
            headline_rows_for_slice=headlines,
            data_quality_rows_for_slice=[],
        )
        assert result.stage17_label_preserved == label, (
            f"Group A label {label!r} not preserved verbatim"
        )

    # Group B: sample-gate override preserves the would-be label.
    result = classify_row(
        coarse_row=_coarse(n_matched=2, descriptive_label="HARMFUL"),
        headline_rows_for_slice=[_headline()],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
    assert result.stage17_label_preserved == "HARMFUL"

    # Group C: data-quality override preserves the would-be label.
    result = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[_headline(n_in_scope=100, n_unevaluable=30)],
        data_quality_rows_for_slice=[],
    )
    assert result.classification == REVIEW_LABEL_DATA_BLOCKED
    assert result.stage17_label_preserved == "PROMISING"


def test_tier_coverage_propagated_to_classifier_output() -> None:
    """The classifier exposes tier_coverage as a first-class field
    so Phase 18.3 writers do not need to recompute it. All three
    locked values must round-trip through the classifier
    unchanged."""

    # multi_tier
    multi = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[
            _headline(tier="T1"),
            _headline(tier="T2"),
        ],
        data_quality_rows_for_slice=[],
    )
    assert multi.tier_coverage == TIER_COVERAGE_MULTI_TIER

    # single_tier_only
    single = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[_headline(tier="T1")],
        data_quality_rows_for_slice=[],
    )
    assert single.tier_coverage == TIER_COVERAGE_SINGLE_TIER_ONLY

    # no_headline_rows -- co-occurs with DATA_BLOCKED_REVIEW (G6),
    # but tier_coverage is independent of the classification bucket.
    none = classify_row(
        coarse_row=_coarse(descriptive_label="PROMISING"),
        headline_rows_for_slice=[],
        data_quality_rows_for_slice=[],
    )
    assert none.tier_coverage == TIER_COVERAGE_NO_HEADLINE_ROWS
