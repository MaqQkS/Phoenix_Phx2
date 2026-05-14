"""Stage 18 deterministic output writers.

Each writer produces a single artifact under the run output
directory via the same atomic pattern: write to ``<path>.tmp``,
then ``os.replace`` onto the final name. No randomness, no
wall-clock content in report bodies. Two runs against the same
classified set produce byte-identical files (manifest volatile
fields excepted; see ``manifest.py``).

Output artifacts:

  * ``classification_summary.csv`` -- 6 rows in severity order
  * ``review_matrix.csv``           -- one row per classified slice
  * ``data_quality_blockers.csv``   -- subset where classification
                                       == DATA_BLOCKED_REVIEW
  * ``rule_review_cards.md``        -- markdown per-rule cards
  * ``README.md``                   -- static template
  * ``stage18_run.log``             -- deterministic step log

(``manifest.json`` is built and written by ``manifest.py``.)

Float formatting policy: ``f"{value:.6f}"`` for non-None, empty
string for None. CSV joining goes through ``csv.writer`` with
``QUOTE_MINIMAL`` so cells containing commas, quotes, or newlines
are correctly escaped.
"""

from __future__ import annotations

import csv
import io
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Optional, Sequence

from PHX2.stage18.classifier import ClassificationResult
from PHX2.stage18.constants import (
    REVIEW_LABEL_DATA_BLOCKED,
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_WEAK,
    STAGE18_VERSION,
    TIER_COVERAGE_MULTI_TIER,
)
from PHX2.stage18.errors import Stage18Error


# ---------------------------------------------------------------------------
# Locked column tuples for Stage 18 outputs
# ---------------------------------------------------------------------------


CLASSIFICATION_SUMMARY_COLUMNS: tuple[str, ...] = (
    "classification",
    "n_review_rows",
    "n_unique_rules",
    "n_policy_hashes",
)


REVIEW_MATRIX_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "window_seconds",
    "window_label",
    "classification",
    "stage17_label_preserved",
    "insufficient_sample_reason",
    "data_block_reason",
    "gate_trips_all",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "n_with_complete_outcome",
    "delta_hit_2x_rate",
    "unevaluable_rate",
    "incomplete_outcome_ratio",
    "tier_coverage",
)


DATA_QUALITY_BLOCKERS_COLUMNS: tuple[str, ...] = (
    "policy_hash",
    "rule_id",
    "window_seconds",
    "data_block_reason",
    "gate_trips_all",
    "stage17_label_preserved",
    "n_in_scope",
    "n_matched",
    "n_not_matched",
    "unevaluable_rate",
    "incomplete_outcome_ratio",
)


# ---------------------------------------------------------------------------
# Severity order (used by classification_summary.csv and the card writer)
# ---------------------------------------------------------------------------


SEVERITY_ORDER: tuple[str, ...] = (
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_DATA_BLOCKED,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_WEAK,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
)


# ---------------------------------------------------------------------------
# Card-classification explanations (neutral, observe-only language)
# ---------------------------------------------------------------------------


_CLASSIFICATION_EXPLANATIONS: Mapping[str, str] = {
    REVIEW_LABEL_PROMISING: (
        "Rule-matched decisions are associated with better outcomes "
        "than not-matched. Deserves human review. Does not imply promotion."
    ),
    REVIEW_LABEL_HARMFUL: (
        "Rule-matched decisions are associated with worse outcomes "
        "than not-matched. Deserves human review. Does not imply rule "
        "removal."
    ),
    REVIEW_LABEL_WEAK: (
        "Rule-matched and not-matched outcomes show no clear separation. "
        "No further action implied."
    ),
    REVIEW_LABEL_MIXED_BY_TIER: (
        "Per-tier deltas disagree in sign. Aggregate label is not "
        "meaningful; consult per-tier evidence."
    ),
    REVIEW_LABEL_INSUFFICIENT_SAMPLE: (
        "Insufficient sample to support confident review at Stage 18 "
        "thresholds. Stage 17's original label preserved in evidence."
    ),
    REVIEW_LABEL_DATA_BLOCKED: (
        "Data quality insufficient for confident review. Stage 17's "
        "original label preserved in evidence."
    ),
}


# ---------------------------------------------------------------------------
# ClassifiedRow -- one classified slice, fully populated for writers
# ---------------------------------------------------------------------------


class ClassifiedRow(NamedTuple):
    """Pairs the input coarse row with its classifier output and
    the per-slice / per-rule evidence consumed by the rule-card
    writer.

    Built by the CLI orchestration layer; consumed by every Stage
    18 writer in this module.
    """

    coarse_row: Mapping[str, str]
    classification: ClassificationResult
    headline_rows_for_slice: tuple[Mapping[str, str], ...]
    unevaluable_breakdown_for_rule: tuple[Mapping[str, str], ...]


# ---------------------------------------------------------------------------
# Atomic write + formatting helpers (module-private)
# ---------------------------------------------------------------------------


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via a ``.tmp`` sibling."""

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
        raise Stage18Error("B06", f"{path.name}: {exc}") from exc


def _format_float(value: Optional[float]) -> str:
    """Stage 18 standard float cell: 6 decimals or empty string."""

    if value is None:
        return ""
    return f"{value:.6f}"


def _csv_line(cells: Sequence[Any]) -> str:
    """Render one CSV record (no trailing newline)."""

    buf = io.StringIO()
    writer = csv.writer(
        buf, lineterminator="", quoting=csv.QUOTE_MINIMAL
    )
    writer.writerow([str(c) for c in cells])
    return buf.getvalue()


def _write_csv(
    path: Path,
    columns: Sequence[str],
    data_rows: Iterable[Sequence[Any]],
) -> int:
    """Write a deterministic CSV (LF newlines, header always present)."""

    lines: list[str] = [_csv_line(columns)]
    count = 0
    for row in data_rows:
        lines.append(_csv_line(row))
        count += 1
    content = "\n".join(lines) + "\n"
    _atomic_write_text(path, content)
    return count


def _slice_sort_key(row: ClassifiedRow) -> tuple:
    """(policy_hash, rule_id, window_seconds) -- numeric window."""

    return (
        row.coarse_row["policy_hash"],
        row.coarse_row["rule_id"],
        int(row.coarse_row["window_seconds"]),
    )


# ---------------------------------------------------------------------------
# Public writer: classification_summary.csv
# ---------------------------------------------------------------------------


def write_classification_summary(
    rows: Sequence[ClassifiedRow], output_path: Path
) -> int:
    """Emit exactly six rows -- one per review label -- in severity
    order, including zero-count buckets.

    Definitions:
      n_review_rows   = count of (policy_hash, rule_id, window_seconds)
                        rows in this bucket.
      n_unique_rules  = count of distinct rule_id values in this bucket.
      n_policy_hashes = count of distinct policy_hash values in this
                        bucket.
    """

    by_bucket: dict[str, list[ClassifiedRow]] = defaultdict(list)
    for row in rows:
        by_bucket[row.classification.classification].append(row)

    data_rows: list[list[Any]] = []
    for label in SEVERITY_ORDER:
        bucket = by_bucket.get(label, [])
        n_review = len(bucket)
        n_unique_rules = len({r.coarse_row["rule_id"] for r in bucket})
        n_policy_hashes = len({r.coarse_row["policy_hash"] for r in bucket})
        data_rows.append([label, n_review, n_unique_rules, n_policy_hashes])

    return _write_csv(output_path, CLASSIFICATION_SUMMARY_COLUMNS, data_rows)


# ---------------------------------------------------------------------------
# Public writer: review_matrix.csv
# ---------------------------------------------------------------------------


def write_review_matrix(
    rows: Sequence[ClassifiedRow], output_path: Path
) -> int:
    """One row per ClassifiedRow, sorted by
    (policy_hash, rule_id, numeric window_seconds)."""

    sorted_rows = sorted(rows, key=_slice_sort_key)
    data_rows: list[list[Any]] = []
    # ``data_block_reason`` is emitted verbatim from the classifier:
    # plain "G4" / "G5" / "G6" for standard data-quality trips,
    # or "G5:complete_outcome_zero" for the G5 zero-denominator
    # sub-case. ``gate_trips_all`` uses plain gate IDs only. See
    # PHX2.stage18.classifier.ClassificationResult for the full
    # convention.
    for r in sorted_rows:
        cr = r.coarse_row
        result = r.classification
        data_rows.append([
            cr["policy_hash"],
            cr["rule_id"],
            cr["window_seconds"],
            cr["window_label"],
            result.classification,
            result.stage17_label_preserved,
            result.insufficient_sample_reason,
            result.data_block_reason,
            result.gate_trips_all,
            cr["n_in_scope"],
            cr["n_matched"],
            cr["n_not_matched"],
            cr["n_with_complete_outcome"],
            cr["delta_hit_2x_rate"],  # Stage 17 already formatted
            _format_float(result.unevaluable_rate),
            _format_float(result.incomplete_outcome_ratio),
            result.tier_coverage,
        ])
    return _write_csv(output_path, REVIEW_MATRIX_COLUMNS, data_rows)


# ---------------------------------------------------------------------------
# Public writer: data_quality_blockers.csv
# ---------------------------------------------------------------------------


def write_data_quality_blockers(
    rows: Sequence[ClassifiedRow], output_path: Path
) -> int:
    """Subset of ``review_matrix`` limited to rows whose
    classification is ``DATA_BLOCKED_REVIEW`` (i.e. G4/G5/G6 fired
    and no earlier sample gate stole the bucket).

    Header-only output is valid when no rows blocked.
    """

    blocked = [
        r for r in rows
        if r.classification.classification == REVIEW_LABEL_DATA_BLOCKED
    ]
    sorted_rows = sorted(blocked, key=_slice_sort_key)
    data_rows: list[list[Any]] = []
    # ``data_block_reason`` is emitted verbatim from the classifier:
    # plain "G4" / "G5" / "G6" for standard data-quality trips,
    # or "G5:complete_outcome_zero" for the G5 zero-denominator
    # sub-case. ``gate_trips_all`` uses plain gate IDs only. See
    # PHX2.stage18.classifier.ClassificationResult for the full
    # convention.
    for r in sorted_rows:
        cr = r.coarse_row
        result = r.classification
        data_rows.append([
            cr["policy_hash"],
            cr["rule_id"],
            cr["window_seconds"],
            result.data_block_reason,
            result.gate_trips_all,
            result.stage17_label_preserved,
            cr["n_in_scope"],
            cr["n_matched"],
            cr["n_not_matched"],
            _format_float(result.unevaluable_rate),
            _format_float(result.incomplete_outcome_ratio),
        ])
    return _write_csv(output_path, DATA_QUALITY_BLOCKERS_COLUMNS, data_rows)


# ---------------------------------------------------------------------------
# Public writer: rule_review_cards.md
# ---------------------------------------------------------------------------


def write_rule_review_cards(
    rows: Sequence[ClassifiedRow],
    output_path: Path,
    *,
    stage17_run_id: str,
) -> int:
    """Render the markdown per-rule cards, sections in severity
    order; within each section sorted by
    (policy_hash, rule_id, numeric window_seconds).

    Returns the count of rendered cards (across all buckets).
    """

    by_bucket: dict[str, list[ClassifiedRow]] = defaultdict(list)
    for r in rows:
        by_bucket[r.classification.classification].append(r)

    counts_str = " ".join(
        f"{label}={len(by_bucket.get(label, []))}"
        for label in SEVERITY_ORDER
    )

    lines: list[str] = []
    lines.append("# Stage 18 rule review cards")
    lines.append("")
    lines.append(f"stage18_version: {STAGE18_VERSION}")
    lines.append(f"stage17_run_id: {stage17_run_id}")
    lines.append(f"bucket_counts: {counts_str}")
    lines.append("")

    n_cards = 0
    for bucket_label in SEVERITY_ORDER:
        lines.append(f"## {bucket_label}")
        lines.append("")
        bucket = sorted(by_bucket.get(bucket_label, []), key=_slice_sort_key)
        if not bucket:
            lines.append("(no rules in this bucket)")
            lines.append("")
            continue
        for r in bucket:
            _render_one_card(r, lines, stage17_run_id)
            lines.append("")
            n_cards += 1

    while lines and lines[-1] == "":
        lines.pop()
    content = "\n".join(lines) + "\n"
    _atomic_write_text(output_path, content)
    return n_cards


def _render_one_card(
    r: ClassifiedRow,
    lines: list[str],
    stage17_run_id: str,
) -> None:
    cr = r.coarse_row
    result = r.classification

    policy_hash = cr["policy_hash"]
    rule_id = cr["rule_id"]
    window_label = cr["window_label"]

    lines.append(
        f"### {rule_id} @ {window_label} ({policy_hash[:12]})"
    )
    lines.append("")
    lines.append(
        f"Classification: {result.classification} -- "
        f"{_CLASSIFICATION_EXPLANATIONS[result.classification]}"
    )
    lines.append(
        f"Stage 17 original label: {result.stage17_label_preserved}"
    )
    lines.append("")
    lines.append("Sample evidence:")
    lines.append(f"- n_in_scope: {cr['n_in_scope']}")
    lines.append(f"- n_matched: {cr['n_matched']}")
    lines.append(f"- n_not_matched: {cr['n_not_matched']}")
    lines.append(
        f"- n_with_complete_outcome: {cr['n_with_complete_outcome']}"
    )
    lines.append(
        f"- unevaluable_rate: "
        f"{_format_float(result.unevaluable_rate) or 'N/A'}"
    )
    lines.append(
        f"- incomplete_outcome_ratio: "
        f"{_format_float(result.incomplete_outcome_ratio) or 'N/A'}"
    )
    lines.append("")
    lines.append("Outcome evidence:")
    lines.append(
        f"- hit_2x_rate_matched: "
        f"{cr.get('hit_2x_rate_matched', '') or 'N/A'}"
    )
    lines.append(
        f"- hit_2x_rate_not_matched: "
        f"{cr.get('hit_2x_rate_not_matched', '') or 'N/A'}"
    )
    lines.append(
        f"- delta_hit_2x_rate: "
        f"{cr.get('delta_hit_2x_rate', '') or 'N/A'}"
    )
    lines.append("")
    lines.append(f"Tier coverage: {result.tier_coverage}")

    if result.tier_coverage == TIER_COVERAGE_MULTI_TIER:
        lines.append("")
        lines.append("Per-tier evidence:")
        lines.append(
            "| tier | n_matched | n_not_matched | "
            "hit_2x_rate_matched | hit_2x_rate_not_matched | "
            "delta_hit_2x_rate |"
        )
        lines.append(
            "|------|-----------|---------------|"
            "---------------------|"
            "-------------------------|"
            "-------------------|"
        )
        sorted_headlines = sorted(
            r.headline_rows_for_slice,
            key=lambda h: h.get("tier_name_snapshot", "") or "",
        )
        for h in sorted_headlines:
            tier = h.get("tier_name_snapshot", "") or "(null)"
            lines.append(
                f"| {tier} | "
                f"{h.get('n_matched', '')} | "
                f"{h.get('n_not_matched', '')} | "
                f"{h.get('hit_2x_rate_matched', '') or 'N/A'} | "
                f"{h.get('hit_2x_rate_not_matched', '') or 'N/A'} | "
                f"{h.get('delta_hit_2x_rate', '') or 'N/A'} |"
            )

    if r.unevaluable_breakdown_for_rule:
        lines.append("")
        lines.append("Unevaluable reason breakdown:")
        sorted_unev = sorted(
            r.unevaluable_breakdown_for_rule,
            key=lambda u: u.get("unevaluable_reason", "") or "",
        )
        for u in sorted_unev:
            reason = u.get("unevaluable_reason", "") or "(null)"
            n_cell = u.get("n", "0")
            lines.append(f"- {reason}: {n_cell}")

    # Per-bucket gate reason lines.
    if (
        result.classification == REVIEW_LABEL_INSUFFICIENT_SAMPLE
        and result.insufficient_sample_reason
    ):
        lines.append("")
        lines.append(
            f"insufficient_sample_reason: "
            f"{result.insufficient_sample_reason}"
        )

    if result.data_block_reason:
        lines.append("")
        lines.append(f"data_block_reason: {result.data_block_reason}")

    lines.append("")
    lines.append(f"Source: Stage 17 run_id={stage17_run_id}")


# ---------------------------------------------------------------------------
# Public writer: README.md
# ---------------------------------------------------------------------------


_README_TEMPLATE = """# Stage 18 -- Observe-only Operator Review Packet

This directory holds one Stage 18 run output. Stage 18 is a
read-only, deterministic, file-only sidecar that consumes a Stage
17 output directory and produces a non-actioning operator review
packet.

## What Stage 18 is

Stage 18 reads ``coarse_summary.csv`` from a completed Stage 17
run, classifies each (policy_hash, rule_id, window_seconds) row
into one of six review buckets, and writes seven output artifacts
to ``--output-dir``. Stage 18 itself performs no DB I/O, no
migrations, no enforcement, no promotion, no scoring, no
scheduler, no dispatch (Discord/Telegram/API), and no policy
mutation.

## Artifacts in this directory

* ``classification_summary.csv`` -- aggregate counts per bucket,
  in severity order. Six rows always emitted (zero-count buckets
  included).
* ``review_matrix.csv`` -- one row per coarse_summary input row.
  17 columns covering policy_hash, rule_id, window, classification,
  gate-trip diagnostics, sample evidence, and derived metrics.
* ``data_quality_blockers.csv`` -- subset of review_matrix
  limited to rows classified as DATA_BLOCKED_REVIEW (G4/G5/G6
  only).
* ``rule_review_cards.md`` -- markdown rendering of every
  classified rule, grouped by severity bucket and sorted within
  each bucket.
* ``manifest.json`` -- run-level metadata. Embeds the upstream
  Stage 17 manifest verbatim, the gate threshold set, input and
  output row counts, classification counts, and the git commit
  (or "unknown" if it could not be captured).
* ``README.md`` -- this file.
* ``stage18_run.log`` -- deterministic step log.

## What each classification means

* PROMISING_REVIEW -- Rule-matched decisions are associated with
  better outcomes than not-matched. Deserves human review. Does
  not imply promotion.
* HARMFUL_REVIEW -- Rule-matched decisions are associated with
  worse outcomes than not-matched. Deserves human review. Does
  not imply rule removal.
* WEAK_REVIEW -- Rule-matched and not-matched outcomes show no
  clear separation. No further action implied.
* MIXED_BY_TIER_REVIEW -- Per-tier deltas disagree in sign. The
  aggregate label is not meaningful; consult per-tier evidence
  in the card.
* INSUFFICIENT_SAMPLE_REVIEW -- Either Stage 17 already marked
  the row INSUFFICIENT_SAMPLE, or one of Stage 18's sample gates
  (G1/G2/G3) tripped. Stage 17's original label is preserved in
  evidence.
* DATA_BLOCKED_REVIEW -- One of Stage 18's data-quality gates
  (G4/G5/G6) tripped. Stage 17's original label is preserved in
  evidence.

## What Stage 18 does NOT do

* No DB reads or writes
* No migrations or schema changes
* No mutation of any Stage 16A / 16B / 17 source table
* No mutation of any file under ``--stage17-input-dir``
* No imports of PHX2.stage17, PHX2.stage16a, PHX2.stage16b,
  PHX2.services, PHX2.dispatch, or PHX2.integrations
* No network calls
* No Discord / Telegram / webhook dispatch
* No scheduler, daemon, watcher, or auto-rerun
* No dashboard, UI, HTML output, or web server
* No model training, scoring, or inferential statistics
* No ranking of rules within a bucket
* No re-labeling of rules using Stage 18's own thresholds
  (Stage 18 wraps Stage 17 labels; it does not replace them)

## Where the numbers come from

Every metric in this packet derives from the Stage 17 artifacts:

* ``n_in_scope``, ``n_matched``, ``n_not_matched``,
  ``n_with_complete_outcome``, ``delta_hit_2x_rate``,
  ``descriptive_label`` -- ``coarse_summary.csv``
* ``unevaluable_rate`` -- sum of ``n_unevaluable`` divided by sum
  of ``n_in_scope`` across matching headline rows in
  ``headline_metrics.csv``
* ``incomplete_outcome_ratio`` -- sum of ``metric_value`` on
  slice-scope rows with metric_name
  ``n_outcome_present_but_incomplete`` in
  ``data_quality_report.csv``, divided by the coarse
  ``n_with_complete_outcome``
* ``tier_coverage`` -- count of distinct ``tier_name_snapshot``
  values in ``headline_metrics.csv`` for the slice

## Operator workflow

1. Read ``classification_summary.csv`` first to see the bucket
   counts at a glance.
2. Open ``rule_review_cards.md`` and read the ``HARMFUL_REVIEW``
   and ``PROMISING_REVIEW`` sections.
3. Check the ``DATA_BLOCKED_REVIEW`` section for upstream data
   pipeline issues.
4. Use ``review_matrix.csv`` for filtering or querying across
   the full classified set.
5. Use ``data_quality_blockers.csv`` for data-pipeline triage
   when several rules land in the DATA_BLOCKED bucket.

## This is observe-only

Do not enforce, promote, or tune based on this packet alone. The
classification labels are explicitly framed as "deserves human
review" rather than as actioning decisions; the operator's job
is to read the evidence, not to apply it directly.
"""


def write_readme(output_path: Path) -> None:
    """Write the static Stage 18 README. Content is deterministic:
    no timestamps, no absolute paths, no run-specific values."""

    _atomic_write_text(output_path, _README_TEMPLATE)


# ---------------------------------------------------------------------------
# Public writer: stage18_run.log
# ---------------------------------------------------------------------------


def make_log_event(step: str, **fields: object) -> str:
    """Compose a deterministic log line.

    Format: ``step=<step> key=value key=value ...``. Callers must
    pass only stable types (int / str / bool) -- no floats and no
    wall-clock timestamps; this helper does not police that rule,
    it just composes the line.
    """

    parts = [f"step={step}"]
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    return " ".join(parts)


def write_log(events: Sequence[str], output_path: Path) -> None:
    """Write a deterministic, wall-clock-free log."""

    content = "\n".join(events)
    if events:
        content += "\n"
    _atomic_write_text(output_path, content)


__all__ = [
    "CLASSIFICATION_SUMMARY_COLUMNS",
    "ClassifiedRow",
    "DATA_QUALITY_BLOCKERS_COLUMNS",
    "REVIEW_MATRIX_COLUMNS",
    "SEVERITY_ORDER",
    "make_log_event",
    "write_classification_summary",
    "write_data_quality_blockers",
    "write_log",
    "write_readme",
    "write_review_matrix",
    "write_rule_review_cards",
]
