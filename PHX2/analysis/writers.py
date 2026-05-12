"""Stage 12 file writers (CSV / JSON / README).

CSV writes use fixed pandas to_csv arguments
(``index=False``, ``lineterminator="\\n"``, ``float_format="%.10g"``,
``na_rep=""``) to enable byte-level reproducibility (TEST 9).

JSON writes use ``indent=2, sort_keys=True, ensure_ascii=False`` for
the same reason.

The README is a small template. The pipeline supplies a context dict
covering: run_id, created_at, parameters, output filenames, primitive
list, censoring rule, environment, git fingerprint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


CSV_WRITE_KWARGS: dict[str, Any] = {
    "index": False,
    "lineterminator": "\n",
    "float_format": "%.10g",
    "na_rep": "",
    "encoding": "utf-8",
}


def create_run_directory(output_root: Path, run_id: str) -> Path:
    """Create the immutable per-run directory.

    Layout: ``<output_root>/decision_outcome_analysis/<run_id>/``.

    Uses ``mkdir(parents=True, exist_ok=False)``. Collision on an
    existing run_id is a hard error — Stage 12 never overwrites a
    prior run's artifacts.
    """

    output_root = Path(output_root)
    run_dir = output_root / "decision_outcome_analysis" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a DataFrame with the canonical reproducibility kwargs."""

    df.to_csv(path, **CSV_WRITE_KWARGS)


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Write the manifest JSON deterministically."""

    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def write_readme(context: dict[str, Any], path: Path) -> None:
    """Write a human-readable README summarizing the run."""

    lines: list[str] = []
    lines.append("[RESEARCH ONLY — STAGE 12 EXPLORATORY ANALYSIS]")
    lines.append("=" * 72)
    lines.append("")
    lines.append(context.get("research_only_warning", ""))
    lines.append("")
    lines.append(f"Run ID:        {context['run_id']}")
    lines.append(f"Created at:    {context['created_at']}")
    lines.append(f"Stage:         {context['stage']} v{context['stage_version']}")
    if context.get("git_commit"):
        dirty_suffix = " (dirty)" if context.get("git_dirty") else ""
        lines.append(f"Git commit:    {context['git_commit']}{dirty_suffix}")
    env = context.get("environment") or {}
    if env.get("python_version"):
        lines.append(f"Python:        {env['python_version']}")
    if env.get("platform"):
        lines.append(f"Platform:      {env['platform']}")
    lines.append("")

    lines.append("Parameters")
    lines.append("-" * 72)
    params = context.get("parameters") or {}
    if not params:
        lines.append("  (none)")
    else:
        for key in sorted(params):
            lines.append(f"  {key}: {params[key]}")
    lines.append("")

    lines.append("Censoring rule")
    lines.append("-" * 72)
    lines.append(context.get("censoring_rule", ""))
    lines.append("")

    lines.append("Outputs")
    lines.append("-" * 72)
    outputs = context.get("outputs") or {}
    if not outputs:
        lines.append("  (none)")
    else:
        for key in sorted(outputs):
            desc = outputs[key]
            lines.append(
                f"  {desc['filename']} — {desc['row_count']} row(s); "
                f"{len(desc['schema'])} columns"
            )
    lines.append("")

    pre = context.get("pre_join_row_counts") or {}
    post = context.get("post_join_row_counts") or {}
    if pre or post:
        lines.append("Row counts")
        lines.append("-" * 72)
        for key in sorted(pre):
            lines.append(f"  pre-join.{key}: {pre[key]}")
        for key in sorted(post):
            lines.append(f"  post-join.{key}: {post[key]}")
        lines.append("")

    primitives = context.get("primitives_analyzed") or {}
    primitives_skipped = context.get("primitives_skipped") or {}
    if primitives or primitives_skipped:
        lines.append("Primitives")
        lines.append("-" * 72)
        for name in sorted(primitives):
            info = primitives[name]
            edges = info.get("edges")
            edges_str = (
                f" edges={edges}"
                if edges is not None
                else ""
            )
            lines.append(
                f"  {name}: method={info.get('method')} "
                f"distinct={info.get('distinct_value_count')}{edges_str}"
            )
        for name in sorted(primitives_skipped):
            info = primitives_skipped[name]
            lines.append(
                f"  {name}: SKIPPED ({info.get('skip_reason')}) "
                f"distinct={info.get('distinct_value_count')}"
            )
        lines.append("")

    if (
        context.get("post_join_row_counts", {}).get("long_csv_rows", 1) == 0
    ):
        lines.append(
            "No eligible decisions in scope. Output CSVs contain headers only."
        )
        lines.append("")

    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(lines))
        if not lines or lines[-1] != "":
            handle.write("\n")
