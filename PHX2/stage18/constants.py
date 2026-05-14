"""Stage 18 locked constants.

All thresholds, schema versions, file names, and CSV column tuples
that govern the Stage 18 review-packet build live here. The Stage
17 column tuples are duplicated verbatim from Stage 17's writer so
Stage 18 can validate input shape without importing
``PHX2.stage17``; this matches the locked import-boundary policy.

Determinism contract: every value here that contributes to the
run-id input set (gates, versions, accepted Stage 17 schema
version) is captured into the run manifest. Changes to any such
constant change ``run_id``.

The five Stage 17 ``descriptive_label`` literals listed at the
bottom of this module are the entire accepted set. Any other
literal seen in a coarse-summary or headline-metrics row is a
fatal B03 violation in the classifier (Phase 18.2).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 18 gate thresholds (see classifier.py in Phase 18.2)
# ---------------------------------------------------------------------------


MIN_EVALUABLE_COUNT: int = 30
MIN_RULE_POSITIVE_COUNT: int = 10
MIN_RULE_NEGATIVE_COUNT: int = 10
MAX_UNEVALUABLE_RATE: float = 0.25
MAX_INCOMPLETE_OUTCOME_RATIO: float = 0.50


# ---------------------------------------------------------------------------
# Stage 18 versions
# ---------------------------------------------------------------------------


STAGE18_VERSION: str = "stage18_review_v0_observe_only"
MANIFEST_SCHEMA_VERSION: str = "stage18_run_manifest_v0"

# Stage 17's manifest schema_version that Stage 18 accepts on input.
STAGE17_MANIFEST_SCHEMA_VERSION: str = "stage17_run_manifest_v0"


# ---------------------------------------------------------------------------
# Required input artifacts (Stage 17 output dir)
# ---------------------------------------------------------------------------


HEADLINE_FILENAME: str = "headline_metrics.csv"
COARSE_FILENAME: str = "coarse_summary.csv"
UNEVALUABLE_BREAKDOWN_FILENAME: str = "unevaluable_breakdown.csv"
DATA_QUALITY_FILENAME: str = "data_quality_report.csv"
MANIFEST_FILENAME: str = "manifest.json"

REQUIRED_INPUT_FILES: tuple[str, ...] = (
    HEADLINE_FILENAME,
    COARSE_FILENAME,
    UNEVALUABLE_BREAKDOWN_FILENAME,
    DATA_QUALITY_FILENAME,
    MANIFEST_FILENAME,
)


# ---------------------------------------------------------------------------
# Stage 17 CSV column tuples (locked, duplicated from Stage 17's writer)
# ---------------------------------------------------------------------------
#
# These tuples are the contract between Stage 17 outputs and Stage
# 18 inputs. They are intentionally hand-duplicated rather than
# imported across the stage boundary so:
#
#   * Stage 18 satisfies its hard import-boundary policy
#     (stdlib + PHX2.stage18 only).
#   * A drift in the upstream writer produces a B01 in Stage 18
#     (header mismatch) rather than a silent re-aliasing.
#
# HEADLINE_COLUMNS contains 43 columns (the Stage 18 spec's prose
# count of "44" is a one-off cosmetic typo in the spec; the actual
# Stage 17 writer emits 43 columns).


HEADLINE_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "tier_name_snapshot",
    "window_seconds",
    "window_label",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "n_unevaluable",
    "n_with_outcome",
    "n_with_complete_outcome",
    "n_outcome_present_but_incomplete",
    "n_matched_with_complete_outcome",
    "n_not_matched_with_complete_outcome",
    "min_n_active",
    "meets_min_n_matched",
    "meets_min_n_not_matched",
    "max_return_multiple_p25_matched",
    "max_return_multiple_p50_matched",
    "max_return_multiple_p75_matched",
    "max_return_multiple_p25_not_matched",
    "max_return_multiple_p50_not_matched",
    "max_return_multiple_p75_not_matched",
    "max_drawdown_from_peak_pct_p25_matched",
    "max_drawdown_from_peak_pct_p50_matched",
    "max_drawdown_from_peak_pct_p75_matched",
    "max_drawdown_from_peak_pct_p25_not_matched",
    "max_drawdown_from_peak_pct_p50_not_matched",
    "max_drawdown_from_peak_pct_p75_not_matched",
    "time_to_max_return_seconds_p50_matched",
    "time_to_max_return_seconds_p50_not_matched",
    "hit_2x_rate_matched",
    "hit_2x_rate_not_matched",
    "hit_3x_rate_matched",
    "hit_3x_rate_not_matched",
    "hit_5x_rate_matched",
    "hit_5x_rate_not_matched",
    "delta_hit_2x_rate",
    "delta_hit_3x_rate",
    "delta_hit_5x_rate",
    "delta_max_return_multiple_p50",
    "delta_max_drawdown_from_peak_pct_p50",
    "descriptive_label",
)


COARSE_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "window_seconds",
    "window_label",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "n_with_complete_outcome",
    "hit_2x_rate_matched",
    "hit_2x_rate_not_matched",
    "delta_hit_2x_rate",
    "descriptive_label",
)


UNEVALUABLE_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "unevaluable_reason",
    "n",
)


DATA_QUALITY_COLUMNS: tuple[str, ...] = (
    "scope_level",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "metric_name",
    "metric_value",
)


# ---------------------------------------------------------------------------
# Stage 17 descriptive_label values accepted on input
# ---------------------------------------------------------------------------


STAGE17_LABEL_PROMISING: str = "PROMISING"
STAGE17_LABEL_WEAK: str = "WEAK"
STAGE17_LABEL_HARMFUL: str = "HARMFUL"
STAGE17_LABEL_INSUFFICIENT_SAMPLE: str = "INSUFFICIENT_SAMPLE"
STAGE17_LABEL_MIXED_BY_TIER: str = "MIXED_BY_TIER"


ACCEPTED_STAGE17_LABELS: frozenset[str] = frozenset({
    STAGE17_LABEL_PROMISING,
    STAGE17_LABEL_WEAK,
    STAGE17_LABEL_HARMFUL,
    STAGE17_LABEL_INSUFFICIENT_SAMPLE,
    STAGE17_LABEL_MIXED_BY_TIER,
})


# ---------------------------------------------------------------------------
# Stage 18 review-label vocabulary (six-bucket taxonomy)
# ---------------------------------------------------------------------------
#
# These are the exact string literals Stage 18 emits in the
# ``classification`` column of every output row. They wrap the
# Stage 17 descriptive_label values (Group A), and on override
# they replace them while preserving the original Stage 17 label
# in the ``stage17_label_preserved`` field (Groups B / C). Defined
# centrally so the classifier (Phase 18.2) and the writers
# (Phase 18.3) share one source of truth.


REVIEW_LABEL_PROMISING: str = "PROMISING_REVIEW"
REVIEW_LABEL_WEAK: str = "WEAK_REVIEW"
REVIEW_LABEL_HARMFUL: str = "HARMFUL_REVIEW"
REVIEW_LABEL_MIXED_BY_TIER: str = "MIXED_BY_TIER_REVIEW"
REVIEW_LABEL_INSUFFICIENT_SAMPLE: str = "INSUFFICIENT_SAMPLE_REVIEW"
REVIEW_LABEL_DATA_BLOCKED: str = "DATA_BLOCKED_REVIEW"


ALL_REVIEW_LABELS: frozenset[str] = frozenset({
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_WEAK,
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
    REVIEW_LABEL_DATA_BLOCKED,
})


# ---------------------------------------------------------------------------
# Tier-coverage flag values (non-blocking diagnostic on every row)
# ---------------------------------------------------------------------------


TIER_COVERAGE_NO_HEADLINE_ROWS: str = "no_headline_rows"
TIER_COVERAGE_SINGLE_TIER_ONLY: str = "single_tier_only"
TIER_COVERAGE_MULTI_TIER: str = "multi_tier"


ALL_TIER_COVERAGE_VALUES: frozenset[str] = frozenset({
    TIER_COVERAGE_NO_HEADLINE_ROWS,
    TIER_COVERAGE_SINGLE_TIER_ONLY,
    TIER_COVERAGE_MULTI_TIER,
})


__all__ = [
    "ACCEPTED_STAGE17_LABELS",
    "ALL_REVIEW_LABELS",
    "ALL_TIER_COVERAGE_VALUES",
    "COARSE_COLUMNS",
    "COARSE_FILENAME",
    "DATA_QUALITY_COLUMNS",
    "DATA_QUALITY_FILENAME",
    "HEADLINE_COLUMNS",
    "HEADLINE_FILENAME",
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_INCOMPLETE_OUTCOME_RATIO",
    "MAX_UNEVALUABLE_RATE",
    "MIN_EVALUABLE_COUNT",
    "MIN_RULE_NEGATIVE_COUNT",
    "MIN_RULE_POSITIVE_COUNT",
    "REQUIRED_INPUT_FILES",
    "REVIEW_LABEL_DATA_BLOCKED",
    "REVIEW_LABEL_HARMFUL",
    "REVIEW_LABEL_INSUFFICIENT_SAMPLE",
    "REVIEW_LABEL_MIXED_BY_TIER",
    "REVIEW_LABEL_PROMISING",
    "REVIEW_LABEL_WEAK",
    "STAGE17_LABEL_HARMFUL",
    "STAGE17_LABEL_INSUFFICIENT_SAMPLE",
    "STAGE17_LABEL_MIXED_BY_TIER",
    "STAGE17_LABEL_PROMISING",
    "STAGE17_LABEL_WEAK",
    "STAGE17_MANIFEST_SCHEMA_VERSION",
    "STAGE18_VERSION",
    "TIER_COVERAGE_MULTI_TIER",
    "TIER_COVERAGE_NO_HEADLINE_ROWS",
    "TIER_COVERAGE_SINGLE_TIER_ONLY",
    "UNEVALUABLE_BREAKDOWN_FILENAME",
    "UNEVALUABLE_COLUMNS",
]
