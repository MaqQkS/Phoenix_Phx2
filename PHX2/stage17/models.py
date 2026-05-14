"""Stage 17 frozen dataclasses: read shapes, metric outputs, run report."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Read shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationRow:
    """One row from observe_only_policy_evaluations joined to an in-scope alert_decisions row.

    "In scope" means the alert_decisions row has decision_type =
    'would_alert' AND would_alert = 1. Fields are projected to the
    minimum set Stage 17 needs; everything else is excluded from the
    join.
    """

    id: int
    alert_decision_id: int
    tier_name_snapshot: Optional[str]
    policy_hash: str
    rule_id: str
    evaluation_status: str
    matched: int
    would_have_blocked: int
    unevaluable_reason: Optional[str]
    evaluated_at_utc: str


@dataclass(frozen=True)
class OutcomeRow:
    """One row from outcome_windows for an in-scope alert_decision_id."""

    alert_decision_id: int
    window_seconds: int
    max_return_multiple: Optional[float]
    max_drawdown_from_peak_pct: Optional[float]
    time_to_max_return_seconds: Optional[float]
    hit_2x: Optional[int]
    hit_3x: Optional[int]
    hit_5x: Optional[int]
    data_status: str


# ---------------------------------------------------------------------------
# Slice key
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JoinedSliceKey:
    """Unit of analysis for the headline report."""

    policy_hash: str
    rule_id: str
    tier_name_snapshot: Optional[str]
    window_seconds: int


# ---------------------------------------------------------------------------
# Metric outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadlineMetricRow:
    """One row per (policy_hash, rule_id, tier_name_snapshot, window_seconds) slice.

    Field order matches the locked headline column order in the README
    and is asserted by the writer tests.
    """

    policy_hash: str
    rule_id: str
    tier_name_snapshot: Optional[str]
    window_seconds: int
    window_label: str
    n_in_scope: int
    n_matched: int
    n_not_matched: int
    n_unevaluable: int
    n_with_outcome: int
    n_with_complete_outcome: int
    n_outcome_present_but_incomplete: int
    n_matched_with_complete_outcome: int
    n_not_matched_with_complete_outcome: int
    min_n_active: int
    meets_min_n_matched: bool
    meets_min_n_not_matched: bool
    max_return_multiple_p25_matched: Optional[float]
    max_return_multiple_p50_matched: Optional[float]
    max_return_multiple_p75_matched: Optional[float]
    max_return_multiple_p25_not_matched: Optional[float]
    max_return_multiple_p50_not_matched: Optional[float]
    max_return_multiple_p75_not_matched: Optional[float]
    max_drawdown_from_peak_pct_p25_matched: Optional[float]
    max_drawdown_from_peak_pct_p50_matched: Optional[float]
    max_drawdown_from_peak_pct_p75_matched: Optional[float]
    max_drawdown_from_peak_pct_p25_not_matched: Optional[float]
    max_drawdown_from_peak_pct_p50_not_matched: Optional[float]
    max_drawdown_from_peak_pct_p75_not_matched: Optional[float]
    time_to_max_return_seconds_p50_matched: Optional[float]
    time_to_max_return_seconds_p50_not_matched: Optional[float]
    hit_2x_rate_matched: Optional[float]
    hit_2x_rate_not_matched: Optional[float]
    hit_3x_rate_matched: Optional[float]
    hit_3x_rate_not_matched: Optional[float]
    hit_5x_rate_matched: Optional[float]
    hit_5x_rate_not_matched: Optional[float]
    delta_hit_2x_rate: Optional[float]
    delta_hit_3x_rate: Optional[float]
    delta_hit_5x_rate: Optional[float]
    delta_max_return_multiple_p50: Optional[float]
    delta_max_drawdown_from_peak_pct_p50: Optional[float]
    descriptive_label: str


@dataclass(frozen=True)
class CoarseMetricRow:
    """Aggregated-over-tiers summary row."""

    policy_hash: str
    rule_id: str
    window_seconds: int
    window_label: str
    n_in_scope: int
    n_matched: int
    n_not_matched: int
    n_with_complete_outcome: int
    hit_2x_rate_matched: Optional[float]
    hit_2x_rate_not_matched: Optional[float]
    delta_hit_2x_rate: Optional[float]
    descriptive_label: str


@dataclass(frozen=True)
class UnevaluableBreakdownRow:
    """One row per (policy_hash, rule_id, unevaluable_reason)."""

    policy_hash: str
    rule_id: str
    unevaluable_reason: Optional[str]
    n: int


@dataclass(frozen=True)
class DataQualityRow:
    """Diagnostic row. ``scope_level`` is 'global' or 'slice'.

    Global rows leave the slice-identifier fields empty.
    """

    scope_level: str
    policy_hash: Optional[str]
    rule_id: Optional[str]
    window_seconds: Optional[int]
    metric_name: str
    metric_value: int


# ---------------------------------------------------------------------------
# Run report (manifest contents + per-CSV row counts)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunReport:
    """Run-level summary built by the CLI and serialized into manifest.json."""

    schema_version: str
    run_id: str
    run_started_utc: str
    run_finished_utc: str
    db_path: str
    output_dir: str
    min_n_active: int
    policy_hashes_analyzed: Tuple[str, ...]
    git_commit: str
    source_table_row_counts: dict
    output_row_counts: dict
    schema_migrations_seen: Tuple[str, ...]
    orphan_counts: dict
