"""Helpers that write Stage 17 output directories used by Stage 18 tests.

The helpers in this module write byte-faithful Stage 17 output
files into a caller-supplied directory. They are used by the Stage
18 reader and contract tests to construct a minimal valid input
directory and to mutate specific files for negative-path tests.

These helpers do **not** import ``PHX2.stage17`` and they
intentionally do not import from ``PHX2.stage18.constants`` either:
the column tuples are duplicated locally so a typo in
``PHX2.stage18.constants`` is caught by these tests rather than
silently mirrored. Test fixtures are an independent source of
truth for the Stage 17 contract Stage 18 must accept.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Locked Stage 17 column tuples (duplicated independently of
# PHX2.stage18.constants so this module is a second source of truth).
# ---------------------------------------------------------------------------


_HEADLINE_COLUMNS: tuple[str, ...] = (
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


_COARSE_COLUMNS: tuple[str, ...] = (
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


_UNEVALUABLE_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "unevaluable_reason",
    "n",
)


_DATA_QUALITY_COLUMNS: tuple[str, ...] = (
    "scope_level",
    "policy_hash",
    "rule_id",
    "window_seconds",
    "metric_name",
    "metric_value",
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def write_minimal_valid_stage17_output(target_dir: Path) -> Path:
    """Write a minimal but contract-valid Stage 17 output directory.

    Produces:
      * ``headline_metrics.csv``  -- one tier-1 row for a synthetic
                                      ``rule_minimal``.
      * ``coarse_summary.csv``    -- one matching coarse row.
      * ``unevaluable_breakdown.csv`` -- header only (zero rows).
      * ``data_quality_report.csv``   -- four global rows.
      * ``manifest.json``         -- valid Stage 17 manifest.

    Returns ``target_dir`` for chaining convenience.
    """

    target_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        target_dir / "headline_metrics.csv",
        _HEADLINE_COLUMNS,
        [_minimal_headline_row()],
    )
    _write_csv(
        target_dir / "coarse_summary.csv",
        _COARSE_COLUMNS,
        [_minimal_coarse_row()],
    )
    _write_csv(
        target_dir / "unevaluable_breakdown.csv",
        _UNEVALUABLE_COLUMNS,
        [],
    )
    _write_csv(
        target_dir / "data_quality_report.csv",
        _DATA_QUALITY_COLUMNS,
        _minimal_data_quality_rows(),
    )
    write_minimal_manifest(target_dir / "manifest.json")
    return target_dir


def write_minimal_manifest(path: Path) -> None:
    """Write a Stage 17-shaped manifest with valid schema_version."""

    payload = {
        "schema_version": "stage17_run_manifest_v0",
        "run_id": "0123456789abcdef",
        "run_started_utc": "2026-05-13T00:00:00+00:00",
        "run_finished_utc": "2026-05-13T00:00:01+00:00",
        "db_path": "/tmp/stage17.db",
        "output_dir": "/tmp/stage17_run",
        "min_n_active": 5,
        "policy_hashes_analyzed": ["abc123def456"],
        "git_commit": "unknown",
        "source_table_row_counts": {
            "observe_only_policy_evaluations": 1,
            "alert_decisions": 1,
            "alert_decisions_would_alert": 1,
            "outcome_windows": 1,
            "outcome_windows_complete": 1,
        },
        "output_row_counts": {
            "headline_metrics.csv": 1,
            "coarse_summary.csv": 1,
            "unevaluable_breakdown.csv": 0,
            "data_quality_report.csv": 4,
        },
        "schema_migrations_seen": [],
        "orphan_counts": {
            "orphan_evaluations": 0,
            "orphan_outcomes": 0,
        },
    }
    text = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    path.write_text(text, encoding="utf-8", newline="")


def write_csv_with_header(path: Path, header: Sequence[str]) -> None:
    """Write a header-only CSV (used for negative-path tests).

    No data rows; used both to build the legitimate
    header-only ``unevaluable_breakdown.csv`` shape and to inject
    a deliberately-wrong header into a required CSV.
    """

    line = ",".join(header) + "\n"
    path.write_text(line, encoding="utf-8", newline="")


def write_truncated_csv_row(
    path: Path, header: Sequence[str], short_row: Sequence[str]
) -> None:
    """Write a CSV with a too-short data row (B07 trigger)."""

    lines = [",".join(header), ",".join(short_row)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# Row builders (kept module-private; tests should reach for the public
# write_minimal_valid_stage17_output entry point instead)
# ---------------------------------------------------------------------------


def _minimal_headline_row() -> Sequence[str]:
    """Produce one valid headline row.

    Values resemble a HARMFUL rule (positive ``delta_hit_2x_rate``)
    so the row could later feed Group A classification tests
    without further mutation. All numeric cells are formatted as
    Stage 17 would (``f"{value:.6f}"`` for REAL fields, decimal
    integer for INTEGER fields, ``"1"``/``"0"`` for BOOLEAN
    fields).
    """

    return [
        "abc123def456",          # policy_hash
        "rule_minimal",          # rule_id
        "T1",                    # tier_name_snapshot
        "3600",                  # window_seconds
        "1h",                    # window_label
        "100",                   # n_in_scope
        "40",                    # n_matched
        "60",                    # n_not_matched
        "0",                     # n_unevaluable
        "100",                   # n_with_outcome
        "100",                   # n_with_complete_outcome
        "0",                     # n_outcome_present_but_incomplete
        "40",                    # n_matched_with_complete_outcome
        "60",                    # n_not_matched_with_complete_outcome
        "5",                     # min_n_active
        "1",                     # meets_min_n_matched
        "1",                     # meets_min_n_not_matched
        "0.500000",              # max_return_multiple_p25_matched
        "1.000000",              # max_return_multiple_p50_matched
        "2.000000",              # max_return_multiple_p75_matched
        "0.250000",              # max_return_multiple_p25_not_matched
        "0.500000",              # max_return_multiple_p50_not_matched
        "1.000000",              # max_return_multiple_p75_not_matched
        "0.100000",              # max_drawdown_from_peak_pct_p25_matched
        "0.200000",              # max_drawdown_from_peak_pct_p50_matched
        "0.300000",              # max_drawdown_from_peak_pct_p75_matched
        "0.400000",              # max_drawdown_from_peak_pct_p25_not_matched
        "0.500000",              # max_drawdown_from_peak_pct_p50_not_matched
        "0.600000",              # max_drawdown_from_peak_pct_p75_not_matched
        "120.000000",            # time_to_max_return_seconds_p50_matched
        "300.000000",            # time_to_max_return_seconds_p50_not_matched
        "0.200000",              # hit_2x_rate_matched
        "0.100000",              # hit_2x_rate_not_matched
        "0.050000",              # hit_3x_rate_matched
        "0.020000",              # hit_3x_rate_not_matched
        "0.010000",              # hit_5x_rate_matched
        "0.005000",              # hit_5x_rate_not_matched
        "0.100000",              # delta_hit_2x_rate
        "0.030000",              # delta_hit_3x_rate
        "0.005000",              # delta_hit_5x_rate
        "0.500000",              # delta_max_return_multiple_p50
        "-0.300000",             # delta_max_drawdown_from_peak_pct_p50
        "HARMFUL",               # descriptive_label (positive delta -> HARMFUL)
    ]


def _minimal_coarse_row() -> Sequence[str]:
    return [
        "abc123def456",   # policy_hash
        "rule_minimal",   # rule_id
        "3600",           # window_seconds
        "1h",             # window_label
        "100",            # n_in_scope
        "40",             # n_matched
        "60",             # n_not_matched
        "100",            # n_with_complete_outcome
        "0.200000",       # hit_2x_rate_matched
        "0.100000",       # hit_2x_rate_not_matched
        "0.100000",       # delta_hit_2x_rate
        "HARMFUL",        # descriptive_label
    ]


def _minimal_data_quality_rows() -> list[Sequence[str]]:
    return [
        ["global", "", "", "", "orphan_evaluations", "0"],
        ["global", "", "", "", "orphan_outcomes", "0"],
        ["global", "", "", "", "total_evaluations", "100"],
        ["global", "", "", "", "total_outcomes", "100"],
    ]


def _write_csv(
    path: Path, columns: Sequence[str], rows: Iterable[Sequence[str]]
) -> None:
    """Hand-write a CSV using Stage 17's conventions (LF, trailing LF).

    Uses bare ``,``-joining rather than ``csv.writer`` because every
    fixture cell is a simple string with no commas, quotes, or
    newlines. The reader still parses these via ``csv.reader``, so
    the round-trip is identical to one produced by ``csv.writer``
    with ``QUOTE_MINIMAL``.
    """

    parts = [",".join(columns)]
    for row in rows:
        parts.append(",".join(row))
    text = "\n".join(parts) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


__all__ = [
    "write_csv_with_header",
    "write_minimal_manifest",
    "write_minimal_valid_stage17_output",
    "write_truncated_csv_row",
]
