"""Stage 13 artifact writer.

Renders the four CSVs + manifest + markdown into a Stage 13 run
directory. Determinism rules per spec §PHASE 4:

  * CSV column order exactly matches the locked schema.
  * Floats formatted with 3 decimal places.
  * Booleans written as "true"/"false".
  * NULLs written as empty strings.
  * Row order stable (sort by policy_surface, cohort_id, tier_scope,
    action_class).
  * JSON manifest: sorted keys, indent=2, trailing newline.
  * Markdown generated from sorted in-memory rows.

The writer uses ONLY the stdlib. No pandas dependency.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable

from PHX2.stage13.hashing import sha256_bytes
from PHX2.stage13.types import RecommendationRow


# ---------------------------------------------------------------------------
# Locked output schemas
# ---------------------------------------------------------------------------


CANDIDATE_CSV_FILENAME = "candidate_recommendations.csv"
EVIDENCE_SUMMARY_CSV_FILENAME = "evidence_summary.csv"
INSUFFICIENT_EVIDENCE_CSV_FILENAME = "insufficient_evidence_cohorts.csv"
MANIFEST_FILENAME = "manifest.json"
MARKDOWN_FILENAME = "stage13_policy_review.md"


CSV_COLUMNS: tuple[str, ...] = (
    "policy_surface",
    "cohort_id",
    "tier_scope",
    "action_class",
    "direction",
    "evidence_class",
    "policy_severity",
    "review_priority",
    "n_complete",
    "n_censored",
    "cohort_rate",
    "baseline_rate",
    "lift_absolute",
    "lift_relative",
    "wilson_ci_low",
    "wilson_ci_high",
    "ci_excludes_baseline",
    "censoring_rate",
    "censoring_warning_flag",
    "watchlist_flag",
    "tier_evidence_support",
    "cross_tier_disagreement",
    "loosen_capped_flag",
    "confidence_ceiling_applied",
    "notes",
)


_FLOAT_COLUMNS: frozenset[str] = frozenset({
    "cohort_rate",
    "baseline_rate",
    "lift_absolute",
    "lift_relative",
    "wilson_ci_low",
    "wilson_ci_high",
    "censoring_rate",
})


_BOOL_COLUMNS: frozenset[str] = frozenset({
    "ci_excludes_baseline",
    "censoring_warning_flag",
    "watchlist_flag",
    "cross_tier_disagreement",
    "loosen_capped_flag",
    "confidence_ceiling_applied",
})


_TIER_SCOPE_SORT_ORDER: dict[str, int] = {
    "overall": 0,
    "T1": 1,
    "T2": 2,
    "T3": 3,
}


_ACTION_SORT_ORDER: dict[str, int] = {
    "ADVANCE_AS_CANDIDATE": 0,
    "ANOMALY_FLAG": 1,
    "HOLD_OBSERVE_ONLY": 2,
    "NO_SIGNAL_FOUND": 3,
    "INSUFFICIENT_EVIDENCE": 4,
}


# ---------------------------------------------------------------------------
# Cell rendering helpers
# ---------------------------------------------------------------------------


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def _format_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _format_list(value: Iterable[str]) -> str:
    return ",".join(value)


def _format_notes(value: Iterable[str]) -> str:
    # Notes carry sentence fragments that may contain commas, so a
    # different separator is needed to keep CSV well-formed when
    # multiple notes are present. The CSV writer will quote on the
    # comma in a single note string anyway, so this is safe.
    return "; ".join(value)


def _row_to_csv_dict(row: RecommendationRow) -> dict[str, str]:
    """Render a RecommendationRow into a stringified dict.

    Every value goes through the appropriate formatter; the CSV writer
    quotes strings containing commas or quotes per RFC 4180 (csv.writer
    default).
    """

    out: dict[str, str] = {}
    for col in CSV_COLUMNS:
        if col == "tier_evidence_support":
            out[col] = _format_list(row.tier_evidence_support)
            continue
        if col == "notes":
            out[col] = _format_notes(row.notes)
            continue
        value: object = getattr(row, col)
        if col in _FLOAT_COLUMNS:
            out[col] = _format_float(value if isinstance(value, (int, float)) and not isinstance(value, bool) else None)
            continue
        if col in _BOOL_COLUMNS:
            out[col] = _format_bool(value if isinstance(value, bool) else None)
            continue
        if value is None:
            out[col] = ""
        else:
            out[col] = str(value)
    return out


# ---------------------------------------------------------------------------
# Row ordering
# ---------------------------------------------------------------------------


def _stable_sort_rows(rows: list[RecommendationRow]) -> list[RecommendationRow]:
    """Sort by (policy_surface, cohort_id, tier_scope, action_class).

    tier_scope sort places "overall" before T1, T2, T3 -- the natural
    review-reading order. action_class sort places ADVANCE_AS_CANDIDATE
    first to surface candidates above the fold.
    """

    return sorted(
        rows,
        key=lambda r: (
            r.policy_surface,
            r.cohort_id,
            _TIER_SCOPE_SORT_ORDER.get(r.tier_scope, 99),
            _ACTION_SORT_ORDER.get(r.action_class, 99),
        ),
    )


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[RecommendationRow]) -> bytes:
    """Render rows + header into bytes, write to disk, and return the
    rendered byte payload (used for hashing).

    Uses ``csv.writer`` with ``lineterminator="\n"`` for OS-independent
    byte stability.
    """

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        rendered = _row_to_csv_dict(row)
        writer.writerow([rendered[c] for c in CSV_COLUMNS])
    payload = buffer.getvalue().encode("utf-8")
    path.write_bytes(payload)
    return payload


def write_candidate_csv(out_dir: Path, rows: list[RecommendationRow]) -> Path:
    """Write candidate_recommendations.csv (excludes INSUFFICIENT_EVIDENCE).

    Returns the file path. The caller should call
    ``compute_recommendation_set_version`` against this file after the
    write to populate the manifest's ``recommendation_set_version``.
    """

    out_dir = Path(out_dir)
    filtered = [r for r in rows if r.action_class != "INSUFFICIENT_EVIDENCE"]
    sorted_rows = _stable_sort_rows(filtered)
    path = out_dir / CANDIDATE_CSV_FILENAME
    _write_csv(path, sorted_rows)
    return path


def write_evidence_summary_csv(
    out_dir: Path, rows: list[RecommendationRow]
) -> Path:
    """Write evidence_summary.csv (includes every classified row)."""

    out_dir = Path(out_dir)
    sorted_rows = _stable_sort_rows(rows)
    path = out_dir / EVIDENCE_SUMMARY_CSV_FILENAME
    _write_csv(path, sorted_rows)
    return path


def write_insufficient_evidence_csv(
    out_dir: Path, rows: list[RecommendationRow]
) -> Path:
    """Write insufficient_evidence_cohorts.csv (only INSUFFICIENT_EVIDENCE).

    Ordered by ``n_complete`` descending so reviewers see closest-to-
    qualifying cohorts first (spec §insufficient_evidence_cohorts.csv).
    """

    out_dir = Path(out_dir)
    filtered = [r for r in rows if r.action_class == "INSUFFICIENT_EVIDENCE"]
    sorted_rows = sorted(filtered, key=lambda r: -r.n_complete)
    path = out_dir / INSUFFICIENT_EVIDENCE_CSV_FILENAME
    _write_csv(path, sorted_rows)
    return path


def compute_recommendation_set_version(csv_path: Path) -> str:
    """Stable content-addressed identifier for the candidate CSV.

    Used by the manifest's ``recommendation_set_version`` field so
    Stage 14 can decide whether to re-replay a shadow policy.
    """

    payload = Path(csv_path).read_bytes()
    return sha256_bytes(payload)


# ---------------------------------------------------------------------------
# Manifest writer
# ---------------------------------------------------------------------------


def write_manifest(out_dir: Path, manifest_dict: dict[str, Any]) -> Path:
    """Write manifest.json with sorted keys, indent=2, trailing newline."""

    out_dir = Path(out_dir)
    path = out_dir / MANIFEST_FILENAME
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(manifest_dict, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return path


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------


_MARKDOWN_DISCLAIMER = (
    "> **No policy changes were made or recommended for automatic "
    "application. All findings are candidates for Stage 14 human "
    "review.**"
)


def _markdown_metadata_block(manifest_dict: dict[str, Any]) -> list[str]:
    lines = [
        f"- Stage 13 version: {manifest_dict.get('stage13_version', '?')}",
        f"- Stage 13 schema_version: {manifest_dict.get('stage13_schema_version', '?')}",
        f"- Run timestamp (UTC): {manifest_dict.get('run_timestamp_utc', '?')}",
        f"- Stage 12 run path: {manifest_dict.get('stage12_run_path', '?')}",
        f"- Stage 12 manifest hash: {manifest_dict.get('stage12_manifest_hash', '?')}",
        f"- Primary outcome metric: {manifest_dict.get('primary_outcome_metric', '?')}",
        f"- Data window: {manifest_dict.get('data_window_start') or 'unspecified'}"
        f" → {manifest_dict.get('data_window_end') or 'unspecified'}",
        f"- Data staleness warning: {manifest_dict.get('data_staleness_warning')}",
        f"- Severity available: {manifest_dict.get('severity_available')}",
        f"- safe_for_live_policy_consumption: "
        f"{manifest_dict.get('safe_for_live_policy_consumption')}",
        f"- Recommendation set version: "
        f"{manifest_dict.get('recommendation_set_version', '?')}",
        f"- Git commit: {manifest_dict.get('git_commit') or 'unavailable'}",
    ]
    return lines


def _markdown_table(rows: list[RecommendationRow]) -> list[str]:
    if not rows:
        return ["_No rows._", ""]
    headers = [
        "policy_surface",
        "cohort_id",
        "tier_scope",
        "evidence_class",
        "direction",
        "review_priority",
        "n_complete",
        "cohort_rate",
        "baseline_rate",
    ]
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append(
            "| "
            + " | ".join(
                [
                    r.policy_surface,
                    r.cohort_id,
                    r.tier_scope,
                    r.evidence_class,
                    r.direction,
                    r.review_priority,
                    str(r.n_complete),
                    _format_float(r.cohort_rate) or "",
                    _format_float(r.baseline_rate) or "",
                ]
            )
            + " |"
        )
    out.append("")
    return out


def write_markdown(
    out_dir: Path,
    rows: list[RecommendationRow],
    manifest_dict: dict[str, Any],
) -> Path:
    """Write stage13_policy_review.md.

    Section headers exactly match the locked spec. The body is a
    human-readable view of the CSVs and manifest; it carries no
    information not derivable from those artifacts.
    """

    out_dir = Path(out_dir)
    path = out_dir / MARKDOWN_FILENAME

    sorted_rows = _stable_sort_rows(rows)

    advance = [r for r in sorted_rows if r.action_class == "ADVANCE_AS_CANDIDATE"]
    anomalies = [r for r in sorted_rows if r.action_class == "ANOMALY_FLAG"]
    holds = [r for r in sorted_rows if r.action_class == "HOLD_OBSERVE_ONLY"]
    no_signal = [r for r in sorted_rows if r.action_class == "NO_SIGNAL_FOUND"]
    insufficient = sorted(
        [r for r in sorted_rows if r.action_class == "INSUFFICIENT_EVIDENCE"],
        key=lambda r: -r.n_complete,
    )
    disagreements = [r for r in sorted_rows if r.cross_tier_disagreement]

    timestamp = manifest_dict.get("run_timestamp_utc", "?")
    severity_available = manifest_dict.get("severity_available", False)
    scam_labels = manifest_dict.get("scam_adjacent_labels", [])

    lines: list[str] = []
    lines.append(f"# Stage 13 Policy Review — {timestamp}")
    lines.append("")
    lines.append(_MARKDOWN_DISCLAIMER)
    lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.extend(_markdown_metadata_block(manifest_dict))
    lines.append("")

    lines.append("## Strong candidates (ADVANCE_AS_CANDIDATE)")
    lines.append("")
    lines.extend(_markdown_table(advance))

    lines.append("## Anomalies flagged for manual inspection")
    lines.append("")
    lines.extend(_markdown_table(anomalies))

    lines.append("## Cohorts on hold for observation (HOLD_OBSERVE_ONLY)")
    lines.append("")
    lines.extend(_markdown_table(holds))

    lines.append("## Cohorts with no signal found")
    lines.append("")
    lines.extend(_markdown_table(no_signal))

    lines.append("## Insufficient evidence — top candidates for more data")
    lines.append("")
    lines.extend(_markdown_table(insufficient[:25]))

    lines.append("## Cross-tier disagreement summary")
    lines.append("")
    lines.extend(_markdown_table(disagreements))

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- Stage 13 reads only Stage 12's CSV outputs; no DB connection "
        "is opened."
    )
    lines.append(
        "- **The numeric values below (n-band boundaries, lift floors, "
        "Wilson alpha, censoring warn level) are Stage 13 "
        "evidence-review parameters used only to bucket cohorts for "
        "this policy-review run. They are NOT live alert-policy "
        "thresholds, NOT recommended threshold values, and NOT inputs "
        "for any future policy mutation. Stage 13 emits zero specific "
        "threshold values; cohort identity and direction only.**"
    )
    lines.append(
        "- Evidence class follows the n-band gate "
        "(n<10 insufficient, n<20 weak max, n<30 moderate max, n>=30 "
        "strong reachable). Lift floors of 0.05 (moderate) and 0.10 "
        "(strong) plus Wilson 95% CI exclusion of baseline gate the "
        "strong path; these floors are evidence-review boundaries, "
        "not policy thresholds."
    )
    lines.append(
        "- Loosen direction is capped at HOLD_OBSERVE_ONLY in v0; "
        "ADVANCE_AS_CANDIDATE is unreachable for loosen findings."
    )
    lines.append(
        "- Overall rows are subject to the per-tier override rule: at "
        "least one matching per-tier ADVANCE row is required."
    )
    lines.append(
        "- The n-band is the dominant gate: cohorts with n_complete < 10 "
        "remain INSUFFICIENT_EVIDENCE even when rates appear extreme. "
        "Anomaly observations on low-n rows are recorded as notes for "
        "reviewer transparency, not promoted to ANOMALY_FLAG."
    )
    if scam_labels:
        lines.append(
            f"- Scam-adjacent label list (review-priority escalator): "
            f"{', '.join(scam_labels)}."
        )
    lines.append("")

    lines.append("## Methodology gaps and known limitations")
    lines.append("")
    if not severity_available:
        lines.append(
            "- Stage 12's outputs in this run do not expose a "
            "decision-volume share column, so policy_severity is "
            "reported as 'unknown' for every cohort. Re-querying the "
            "Stage 12 DB is explicitly out of scope for Stage 13."
        )
    if manifest_dict.get("data_staleness_warning") is True:
        lines.append(
            "- The Stage 12 data window ended more than 30 days before "
            "this Stage 13 run; treat findings as historical."
        )
    if (
        not manifest_dict.get("data_window_end")
        or not manifest_dict.get("data_window_start")
    ):
        lines.append(
            "- The Stage 12 manifest did not bound the analysis window; "
            "Stage 13 cannot evaluate data staleness for this run."
        )
    lines.append("")

    lines.append("## Non-goals")
    lines.append("")
    lines.append(
        "- Stage 13 does not emit specific threshold values; it names "
        "cohorts and directions only."
    )
    lines.append(
        "- Stage 13 emits no crossed-feature rules. Every recommendation "
        "row is single-axis."
    )
    lines.append(
        "- Stage 13 makes no Stage 7 tier-policy surgery recommendations "
        "(no drawdown / min_pump_multiple / eligibility changes)."
    )
    lines.append(
        "- Stage 13 does not draft shadow policies or replay history. "
        "Those belong to Stage 14."
    )
    lines.append("")

    payload = "\n".join(lines)
    path.write_text(payload, encoding="utf-8", newline="")
    return path
