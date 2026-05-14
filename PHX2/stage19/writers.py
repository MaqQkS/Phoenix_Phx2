"""Stage 19 deterministic atomic writers.

Each writer:
  * builds the full file content as a single string in memory
  * writes to ``<path>.tmp``
  * ``os.replace``s the temp file onto the final name

Writers assume input rows are already sorted in canonical order;
sorting is the caller's responsibility (Phase 19.2's
``build_ledger_rows``, ``merge_ledger``, and ``compute_summary``
emit pre-sorted rows).

CSV output uses ``newline=""`` and ``\\n`` line endings (matching
Stage 18's CSV write convention). Markdown and log output use
``\\n`` line endings.

Manifest writing lives in ``PHX2.stage19.manifest`` so the
manifest's serialization (sort_keys=True, etc.) and run_id
derivation can stay together in one module.
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any, Sequence

from PHX2.stage19.constants import (
    LABELS,
    LEDGER_COLUMNS,
    SUMMARY_COLUMNS,
)
from PHX2.stage19.ledger import LedgerRow, SummaryRow


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via a ``.tmp`` sibling.

    On OSError the ``.tmp`` file is best-effort removed before
    the exception propagates.
    """

    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8", newline="")
        os.replace(tmp, path)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def _csv_content(
    columns: Sequence[str], rows: Sequence[Sequence[Any]]
) -> str:
    """Render a deterministic CSV (LF newlines, header first,
    QUOTE_MINIMAL)."""

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([str(c) for c in row])
    return buf.getvalue()


def write_ledger_csv(path: Path, rows: Sequence[LedgerRow]) -> None:
    """Write the operator review ledger CSV at ``path``.

    Header is LEDGER_COLUMNS in locked order. Integer fields
    (window_seconds, review_sequence) are emitted as decimal
    strings. Empty ``rows`` produces a header-only CSV.

    The caller is responsible for canonical D3 sort order; rows
    are written in the order received.
    """

    data_rows: list[list[Any]] = []
    for r in rows:
        data_rows.append([
            r.stage19_run_id,
            r.ledger_row_id,
            r.stage18_run_id,
            r.policy_hash,
            r.rule_id,
            int(r.window_seconds),
            r.operator_id,
            int(r.review_sequence),
            r.review_label,
            r.review_notes,
            r.review_timestamp_utc,
            r.stage18_classification,
            r.stage17_label_preserved,
        ])
    _atomic_write_text(path, _csv_content(LEDGER_COLUMNS, data_rows))


def write_summary_csv(path: Path, rows: Sequence[SummaryRow]) -> None:
    """Write the operator review summary CSV at ``path``.

    Header is SUMMARY_COLUMNS in locked order. Empty ``rows``
    produces a header-only CSV. The caller is responsible for
    canonical D4 sort order.
    """

    data_rows: list[list[Any]] = []
    for r in rows:
        data_rows.append([
            r.stage18_run_id,
            r.policy_hash,
            r.rule_id,
            int(r.window_seconds),
            r.operator_id,
            int(r.current_review_sequence),
            r.current_review_label,
            r.current_review_notes,
            r.current_review_timestamp_utc,
            r.stage18_classification,
            r.stage17_label_preserved,
        ])
    _atomic_write_text(path, _csv_content(SUMMARY_COLUMNS, data_rows))


def write_readme_md(path: Path, manifest: dict) -> None:
    """Write a deterministic markdown README derived purely from
    the manifest dict.

    Sections: explicit non-actioning reminder, run metadata,
    inputs, row counts, label counts table (in LABELS order),
    schema versions.

    Content is fully deterministic: any timestamp displayed
    comes from ``manifest["run_timestamp_utc"]``; the writer
    never reads wall-clock time.
    """

    lines: list[str] = []
    lines.append("# Stage 19 -- Operator Review Ledger Run")
    lines.append("")
    lines.append(
        "**Stage 19 review labels are review judgments only, not "
        "activation commands.** Stage 19 records human review "
        "decisions; it does not change live behavior."
    )
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.append(f"- stage19_run_id: `{manifest['stage19_run_id']}`")
    lines.append(f"- run_timestamp_utc: `{manifest['run_timestamp_utc']}`")
    lines.append(f"- operator_id: `{manifest['operator_id']}`")
    lines.append(f"- git_commit: `{manifest['git_commit']}`")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- stage18_input_dir: `{manifest['stage18_input_dir']}`")
    lines.append(f"- stage18_run_id: `{manifest['stage18_run_id']}`")
    prior_ledger_display = (
        manifest["prior_ledger_dir"]
        if manifest["prior_ledger_dir"] is not None
        else "none"
    )
    lines.append(f"- prior_ledger_dir: `{prior_ledger_display}`")
    lines.append("")
    lines.append("## Row counts")
    lines.append("")
    lines.append(f"- new_row_count: {manifest['new_row_count']}")
    lines.append(f"- prior_row_count: {manifest['prior_row_count']}")
    lines.append(
        f"- total_ledger_row_count: {manifest['total_ledger_row_count']}"
    )
    lines.append("")
    lines.append("## Label counts (this run only)")
    lines.append("")
    lines.append("| label | count |")
    lines.append("|-------|-------|")
    label_counts = manifest["label_counts"]
    for label in LABELS:
        lines.append(f"| {label} | {label_counts.get(label, 0)} |")
    lines.append("")
    lines.append("## Schema versions")
    lines.append("")
    lines.append(
        f"- stage19_schema_version: `{manifest['stage19_schema_version']}`"
    )
    lines.append(f"- stage19_version: `{manifest['stage19_version']}`")
    if manifest.get("prior_ledger_schema_version") is not None:
        lines.append(
            f"- prior_ledger_schema_version: "
            f"`{manifest['prior_ledger_schema_version']}`"
        )
    lines.append("")
    content = "\n".join(lines) + "\n"
    _atomic_write_text(path, content)


def write_run_log(path: Path, log_entries: Sequence[str]) -> None:
    """Write the deterministic Stage 19 run log at ``path``.

    Each entry is written on its own line in the order supplied.
    The writer adds no wall-clock timestamps; entries are
    pre-rendered by the CLI so the output is fully deterministic
    for identical inputs (the run-level timestamp lives in the
    manifest, not in per-line stamps).

    An empty entries sequence produces an empty file (no header).
    """

    content = "\n".join(log_entries)
    if log_entries:
        content += "\n"
    _atomic_write_text(path, content)


__all__ = [
    "write_ledger_csv",
    "write_readme_md",
    "write_run_log",
    "write_summary_csv",
]
