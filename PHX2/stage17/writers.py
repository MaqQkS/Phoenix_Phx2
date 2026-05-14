"""Stage 17 deterministic file writers.

Each writer produces a single artifact under the run output directory
via the same atomic pattern: write to ``<path>.tmp``, then
``os.replace`` onto the final name. No randomness, no wall-clock
content in report bodies. The log writer in particular emits a small
fixed set of step lines so two runs against the same DB produce
byte-identical files.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterable, Optional, Sequence

from PHX2.stage17.errors import Stage17Error
from PHX2.stage17.models import (
    CoarseMetricRow,
    DataQualityRow,
    HeadlineMetricRow,
    RunReport,
    UnevaluableBreakdownRow,
)


# ---------------------------------------------------------------------------
# Locked CSV column orders
# ---------------------------------------------------------------------------


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


# Field-formatting policy: REAL = 6-decimal fixed-point or empty, INTEGER
# = decimal or empty, BOOLEAN = '1'/'0', TEXT = string or empty.
_REAL_FIELDS: frozenset[str] = frozenset({
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
})

_BOOLEAN_FIELDS: frozenset[str] = frozenset({
    "meets_min_n_matched",
    "meets_min_n_not_matched",
})


# ---------------------------------------------------------------------------
# Field formatting
# ---------------------------------------------------------------------------


def _format_cell(column: str, value) -> str:
    if value is None:
        return ""
    if column in _REAL_FIELDS:
        return f"{float(value):.6f}"
    if column in _BOOLEAN_FIELDS:
        return "1" if value else "0"
    if isinstance(value, bool):  # defensive: bool is int subclass.
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


# ---------------------------------------------------------------------------
# Atomic-write helper
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, content: str, *, error_code: str) -> None:
    """Write ``content`` to ``path`` atomically via a .tmp sibling.

    Both the temp file and the final file are written with UTF-8
    encoding and LF line terminators. On any OS-level failure the
    Stage17Error code passed by the caller surfaces.
    """

    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8", newline="")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise Stage17Error(error_code, f"{path.name}: {exc}") from exc


def _row_to_dict(row, columns: Sequence[str]) -> dict:
    return {col: getattr(row, col) for col in columns}


def _write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Iterable[object],
    *,
    error_code: str,
) -> int:
    """Generic CSV writer. Returns the row count actually written."""

    lines: list[str] = []
    header_line = ",".join(columns)
    lines.append(header_line)
    count = 0
    for row in rows:
        record = _row_to_dict(row, columns)
        cells = [_format_cell(col, record[col]) for col in columns]
        lines.append(_csv_join(cells))
        count += 1

    content = "\n".join(lines) + "\n" if lines else ""
    _atomic_write_text(path, content, error_code=error_code)
    return count


def _csv_join(cells: Sequence[str]) -> str:
    """Join cells using csv.writer semantics with QUOTE_MINIMAL and LF.

    Going through ``csv.writer`` (rather than a hand-rolled comma
    join) gives us correct quoting for any cell that happens to
    contain commas, quotes, or newlines. The output is captured into
    a single string so the surrounding writer can compose the full
    file content before calling the atomic-write helper.
    """

    import io

    buf = io.StringIO()
    writer = csv.writer(
        buf,
        lineterminator="",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(list(cells))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public writers: CSVs
# ---------------------------------------------------------------------------


def write_headline_csv(
    rows: Iterable[HeadlineMetricRow], output_path: Path
) -> int:
    return _write_csv(
        output_path, HEADLINE_COLUMNS, rows, error_code="A06"
    )


def write_coarse_summary_csv(
    rows: Iterable[CoarseMetricRow], output_path: Path
) -> int:
    return _write_csv(
        output_path, COARSE_COLUMNS, rows, error_code="A06"
    )


def write_unevaluable_breakdown_csv(
    rows: Iterable[UnevaluableBreakdownRow], output_path: Path
) -> int:
    return _write_csv(
        output_path, UNEVALUABLE_COLUMNS, rows, error_code="A06"
    )


def write_data_quality_csv(
    rows: Iterable[DataQualityRow], output_path: Path
) -> int:
    return _write_csv(
        output_path, DATA_QUALITY_COLUMNS, rows, error_code="A06"
    )


# ---------------------------------------------------------------------------
# Public writer: README.md
# ---------------------------------------------------------------------------


_README_TEMPLATE = """# Stage 17 -- Observe-only Policy Outcome Analysis

This directory holds one Stage 17 run. Stage 17 is a read-only analysis
sidecar: it joins ``observe_only_policy_evaluations`` (Stage 16B) to
``alert_decisions`` and ``outcome_windows`` (Stage 9) and asks one
question: for each approved would-block rule, would the rule have
blocked alerts that were winners or alerts that were losers?

Stage 17 writes zero rows to any database, owns no tables, runs no
migrations, and never participates in the live alert flow.

## Maturity model

Each headline row applies a two-tier maturity model at the
``(alert_decision_id, window_seconds)`` granularity:

* **Tier 1 ("elapsed")** -- an ``outcome_windows`` row exists for the
  decision at that window.
* **Tier 2 ("analyzable")** -- the row additionally has
  ``data_status = 'COMPLETE'``.

Percentile, hit-rate, and drawdown metrics are computed **only on the
Tier-2 subset**. The Tier-1-minus-Tier-2 count is surfaced as a
diagnostic via ``n_outcome_present_but_incomplete``.

## MIN_N behavior

The run uses ``min_n_active = {min_n}``. When either
``n_matched_with_complete_outcome`` or
``n_not_matched_with_complete_outcome`` is below MIN_N, the
corresponding rate, percentile, and delta columns are rendered as
**NULL (empty string)**, never as 0. The two
``meets_min_n_matched`` / ``meets_min_n_not_matched`` boolean columns
make this gating visible per row.

## Matched vs. not_matched

For each (policy_hash, rule_id, tier_name_snapshot, window_seconds)
slice the report compares:

* **matched** -- the rule's "would-have-blocked" side: evaluations
  where ``evaluation_status = 'MATCHED'`` (the rule fired and would
  have blocked the alert if approved for enforcement).
* **not_matched** -- the rule's "would-have-passed" side: evaluations
  where ``evaluation_status = 'NOT_MATCHED'`` (the rule did not fire
  on these alerts).

``UNEVALUABLE`` rows are excluded from rate and percentile inputs but
contribute to ``n_in_scope`` and ``n_unevaluable`` (they get their own
``unevaluable_breakdown.csv`` for cause analysis).

## Artifacts in this directory

* ``headline_metrics.csv`` -- one row per (policy_hash, rule_id,
  tier_name_snapshot, window_seconds) slice. Percentiles, hit-rates,
  deltas, and a descriptive_label per row.
* ``coarse_summary.csv`` -- aggregated over tiers; one row per
  (policy_hash, rule_id, window_seconds). Surfaces a ``MIXED_BY_TIER``
  label when per-tier deltas disagree in sign.
* ``unevaluable_breakdown.csv`` -- one row per (policy_hash, rule_id,
  unevaluable_reason); count of UNEVALUABLE evaluations.
* ``data_quality_report.csv`` -- diagnostic. Global-scope rows for
  total / orphan counts, then slice-scope rows for any
  ``(policy_hash, rule_id, window_seconds)`` with
  ``n_outcome_present_but_incomplete > 0``.

Plus the run manifest (``manifest.json``) and the deterministic run
log (``stage17_run.log``).

## NULL semantics below MIN_N

Per the locked spec, any rate / percentile / delta cell beneath the
MIN_N gate renders as an empty string in the CSVs. Stage 17 never
substitutes 0 for missing data: a 0 in a rate column means "0 hits
out of >= MIN_N eligible decisions", while an empty cell means "we
do not have enough data to answer".

## Run summary

* run_id: ``{run_id}``
* min_n_active: ``{min_n}``
* policy_hashes_analyzed: ``{policy_hashes}``
* git_commit: ``{git_commit}``
"""


def write_readme(report: RunReport, output_path: Path) -> None:
    """Render the deterministic README from the run report.

    The README references the run id, MIN_N, the sorted list of
    policy hashes, and the git commit. All four fields are inputs to
    the manifest determinism contract -- two runs against the same DB
    produce byte-identical READMEs.
    """

    policy_hashes = ", ".join(report.policy_hashes_analyzed) or "(none)"
    body = _README_TEMPLATE.format(
        min_n=report.min_n_active,
        run_id=report.run_id,
        policy_hashes=policy_hashes,
        git_commit=report.git_commit,
    )
    _atomic_write_text(output_path, body, error_code="A07")


# ---------------------------------------------------------------------------
# Public writer: deterministic run log
# ---------------------------------------------------------------------------


def write_log(events: Iterable[str], output_path: Path) -> None:
    """Write a deterministic, wall-clock-free log.

    Each event is a pre-formatted line. The writer does not append
    timestamps, paths, or any other run-specific content; callers
    must ensure the events themselves contain only deterministic
    fields (step names, row counts, policy-hash indexes).
    """

    content = "\n".join(events)
    if events:
        content += "\n"
    _atomic_write_text(output_path, content, error_code="A08")


def make_log_event(step: str, **fields: object) -> str:
    """Compose a deterministic log line.

    Format: ``step=<step> key=value key=value ...`` with keys emitted
    in the order the caller passed them. Values are stringified via
    ``str()``; callers must therefore pass only stable types
    (int / str / bool) and never floats or wall-clock timestamps.
    """

    parts = [f"step={step}"]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    return " ".join(parts)


__all__ = [
    "COARSE_COLUMNS",
    "DATA_QUALITY_COLUMNS",
    "HEADLINE_COLUMNS",
    "UNEVALUABLE_COLUMNS",
    "make_log_event",
    "write_coarse_summary_csv",
    "write_data_quality_csv",
    "write_headline_csv",
    "write_log",
    "write_readme",
    "write_unevaluable_breakdown_csv",
]
