"""Synthetic Stage 12 run-directory builder for Stage 13 tests.

Produces a minimal, schema-correct Stage 12 run on disk. The writer
mirrors Stage 12's CSV reproducibility kwargs (na_rep="", lineterminator
"\\n", float_format %.10g) so any byte-identity assertions made against
fixtures stay stable across Python/pandas patch releases.

The fixtures are deliberately minimal: 1-3 tiers, 1-2 filter labels,
0-1 primitive buckets. Tests construct cohorts by appending rows.

Stage 13 never writes back into these fixtures -- the loader is the
only consumer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


_COHORT_TAIL_COLUMNS: tuple[str, ...] = (
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


_BASELINE_GROUP_COLUMNS = ("tier_index", "tier_name")
_FILTER_OVERALL_GROUP_COLUMNS = (
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
)
_FILTER_BY_TIER_GROUP_COLUMNS = (
    "tier_index",
    "tier_name",
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
)
_PRIMITIVE_BUCKET_COLUMNS = (
    "tier_index",
    "tier_name",
    "primitive_name",
    "bucket_method",
    "bucket_index",
    "bucket_label",
    "bucket_low",
    "bucket_high",
    "bucket_order",
)


@dataclass
class CohortRow:
    """One Stage 12 cohort CSV row spec.

    Fields default to schema-valid placeholder values; tests override
    only what they need. ``extra_columns`` lets a test inject the
    optional severity-column without baking it into the dataclass.
    """

    n_complete: int = 50
    n_censored: int = 5
    hit_2x_24h_count: int = 10
    hit_2x_24h_rate: float | None = 0.20
    hit_2x_24h_ci_low: float | None = 0.10
    hit_2x_24h_ci_high: float | None = 0.30
    confidence_flag: str = "standard"
    extra_columns: dict[str, Any] = field(default_factory=dict)


@dataclass
class BaselineRow(CohortRow):
    tier_index: int | None = 1
    tier_name: str | None = "T1"


@dataclass
class FilterOverallRow(CohortRow):
    filter_name: str = "fee_gate_v1"
    filter_version: str = "v1"
    threshold_version: str = "v1"
    filter_label: str = "scam_likely"


@dataclass
class FilterByTierRow(CohortRow):
    tier_index: int | None = 1
    tier_name: str | None = "T1"
    filter_name: str = "fee_gate_v1"
    filter_version: str = "v1"
    threshold_version: str = "v1"
    filter_label: str = "scam_likely"


@dataclass
class PrimitiveBucketRow(CohortRow):
    tier_index: int | None = 1
    tier_name: str | None = "T1"
    primitive_name: str = "buy_pressure_5m"
    bucket_method: str = "quartile"
    bucket_index: int = 0
    bucket_label: str = "Q1"
    bucket_low: float | None = 0.0
    bucket_high: float | None = 0.25
    bucket_order: int = 0


def _format_value(value: Any) -> str:
    """Render a value for CSV exactly as Stage 12 does.

    Float formatting uses ``%.10g`` (Stage 12's writer kwargs). None is
    rendered as empty string. Bools become "True"/"False" verbatim.
    """

    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _write_csv(
    path: Path, header: Sequence[str], rows: Sequence[dict[str, Any]]
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(
                ",".join(_format_value(row.get(col)) for col in header) + "\n"
            )


def _cohort_tail_dict(row: CohortRow) -> dict[str, Any]:
    """Map a CohortRow to the canonical tail-column dict.

    The unspecified hit-3x / hit-5x / median / etc. columns are set to
    None (CSV NULL) so the row remains schema-valid without forcing
    every test to specify them.
    """

    base: dict[str, Any] = {
        "n_decisions": row.n_complete + row.n_censored,
        "n_with_outcome_window": row.n_complete + row.n_censored,
        "n_complete": row.n_complete,
        "n_censored": row.n_censored,
        "n_no_outcome": 0,
        "hit_2x_24h_count": row.hit_2x_24h_count,
        "hit_2x_24h_rate": row.hit_2x_24h_rate,
        "hit_2x_24h_ci_low": row.hit_2x_24h_ci_low,
        "hit_2x_24h_ci_high": row.hit_2x_24h_ci_high,
        "hit_3x_24h_count": 0,
        "hit_3x_24h_rate": None,
        "hit_3x_24h_ci_low": None,
        "hit_3x_24h_ci_high": None,
        "hit_5x_24h_count": 0,
        "hit_5x_24h_rate": None,
        "hit_5x_24h_ci_low": None,
        "hit_5x_24h_ci_high": None,
        "median_max_return_24h": None,
        "median_max_drawdown_24h": None,
        "confidence_flag": row.confidence_flag,
    }
    base.update(row.extra_columns)
    return base


def write_stage12_run(
    run_path: Path,
    *,
    baseline_rows: list[BaselineRow],
    filter_overall_rows: list[FilterOverallRow],
    filter_by_tier_rows: list[FilterByTierRow],
    primitive_bucket_rows: list[PrimitiveBucketRow] | None = None,
    schema_version: str = "1",
    run_id: str = "20260301T000000Z_fix001",
    data_window_start: str | None = "2026-01-01T00:00:00+00:00",
    data_window_end: str | None = "2026-02-01T00:00:00+00:00",
    extra_columns: tuple[str, ...] = (),
) -> Path:
    """Materialize a Stage 12-shaped run directory on disk.

    Returns the run-directory path. The four cohort CSVs, manifest.json,
    and an empty ``decision_filter_outcome_long.csv`` are written so
    Stage 13's loader sees a complete L3 inventory.

    ``extra_columns`` is a tuple of column names that every cohort
    CSV's header gets extended with. Each row's value comes from its
    ``extra_columns`` dict; missing keys yield empty cells.
    """

    run_path = Path(run_path)
    run_path.mkdir(parents=True, exist_ok=True)

    primitive_bucket_rows = primitive_bucket_rows or []

    # Build per-file rows + headers.
    baseline_dicts = [
        {
            "run_id": run_id,
            "tier_index": r.tier_index,
            "tier_name": r.tier_name,
            **_cohort_tail_dict(r),
        }
        for r in baseline_rows
    ]
    filter_overall_dicts = [
        {
            "run_id": run_id,
            "filter_name": r.filter_name,
            "filter_version": r.filter_version,
            "threshold_version": r.threshold_version,
            "filter_label": r.filter_label,
            **_cohort_tail_dict(r),
        }
        for r in filter_overall_rows
    ]
    filter_by_tier_dicts = [
        {
            "run_id": run_id,
            "tier_index": r.tier_index,
            "tier_name": r.tier_name,
            "filter_name": r.filter_name,
            "filter_version": r.filter_version,
            "threshold_version": r.threshold_version,
            "filter_label": r.filter_label,
            **_cohort_tail_dict(r),
        }
        for r in filter_by_tier_rows
    ]
    primitive_bucket_dicts = [
        {
            "run_id": run_id,
            "tier_index": r.tier_index,
            "tier_name": r.tier_name,
            "primitive_name": r.primitive_name,
            "bucket_method": r.bucket_method,
            "bucket_index": r.bucket_index,
            "bucket_label": r.bucket_label,
            "bucket_low": r.bucket_low,
            "bucket_high": r.bucket_high,
            "bucket_order": r.bucket_order,
            **_cohort_tail_dict(r),
        }
        for r in primitive_bucket_rows
    ]

    baseline_header = ("run_id", *_BASELINE_GROUP_COLUMNS, *_COHORT_TAIL_COLUMNS, *extra_columns)
    filter_overall_header = (
        "run_id", *_FILTER_OVERALL_GROUP_COLUMNS, *_COHORT_TAIL_COLUMNS, *extra_columns,
    )
    filter_by_tier_header = (
        "run_id", *_FILTER_BY_TIER_GROUP_COLUMNS, *_COHORT_TAIL_COLUMNS, *extra_columns,
    )
    primitive_bucket_header = (
        "run_id", *_PRIMITIVE_BUCKET_COLUMNS, *_COHORT_TAIL_COLUMNS, *extra_columns,
    )

    _write_csv(run_path / "cohort_tier_baseline.csv", baseline_header, baseline_dicts)
    _write_csv(
        run_path / "cohort_filter_label_overall.csv",
        filter_overall_header,
        filter_overall_dicts,
    )
    _write_csv(
        run_path / "cohort_filter_label_by_tier.csv",
        filter_by_tier_header,
        filter_by_tier_dicts,
    )
    _write_csv(
        run_path / "cohort_primitive_bucket_by_tier.csv",
        primitive_bucket_header,
        primitive_bucket_dicts,
    )
    # decision_filter_outcome_long is part of the Stage 12 emit set but
    # not consumed by Stage 13. Write an empty placeholder so any
    # downstream tooling that lists the run dir sees a complete set.
    _write_csv(run_path / "decision_filter_outcome_long.csv", ("alert_decision_id",), [])

    manifest = {
        "stage": "decision_outcome_analysis",
        "stage_version": "12.v0",
        "schema_version": schema_version,
        "run_id": run_id,
        "created_at": "2026-02-01T00:00:00+00:00",
        "research_only_warning": "RESEARCH ONLY.",
        "censoring_rule": "Per Stage 12 spec.",
        "parameters": {
            "included_decision_statuses": ["would_alert"],
            "decision_time_range_start": data_window_start,
            "decision_time_range_end": data_window_end,
            "as_of_time": None,
        },
        "pre_join_row_counts": {},
        "post_join_row_counts": {},
        "primitives_analyzed": {},
        "primitives_skipped": {},
        "outputs": {},
        "environment": {},
        "git_commit": None,
        "git_dirty": None,
    }
    with open(run_path / "manifest.json", "w", encoding="utf-8", newline="") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")

    return run_path
