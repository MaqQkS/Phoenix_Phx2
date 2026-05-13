"""Synthetic Stage 13 + Stage 12 run-directory builders for Stage 14 tests.

The two writers in this module produce schema-correct, byte-stable
fixtures that mirror what a real Stage 13 / Stage 12 run would emit.
Stage 14 tests construct combinations of these to exercise specific
edge cases (winners blocked, saved noise, no-outcome decisions,
multi-rule matches, override hash mismatch, etc.).

Both writers use only the stdlib so they remain importable inside the
``PHX2.stage14`` test environment without dragging pandas in.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Stage 13 candidate CSV
# ---------------------------------------------------------------------------


# Matches PHX2.stage13.writer.CSV_COLUMNS exactly.
STAGE13_CANDIDATE_CSV_COLUMNS: tuple[str, ...] = (
    "policy_surface",
    "cohort_id",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
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


@dataclass
class Stage13CandidateRow:
    """One row of a synthetic Stage 13 candidate_recommendations.csv.

    Defaults yield a v0-eligible filter_label_blocking ADVANCE tighten
    candidate; tests override the fields they want to flip into an
    excluded shape.
    """

    policy_surface: str = "filter_label_blocking"
    cohort_id: str = "fee_gate_v1@v1[threshold=v1]:scam_likely"
    filter_name: str = "fee_gate_v1"
    filter_version: str = "v1"
    filter_label: str = "scam_likely"
    threshold_version: str = "v1"
    tier_scope: str = "T1"
    action_class: str = "ADVANCE_AS_CANDIDATE"
    direction: str = "tighten"
    evidence_class: str = "strong"
    policy_severity: str = "unknown"
    review_priority: str = "urgent"
    n_complete: int = 50
    n_censored: int = 5
    cohort_rate: float = 0.05
    baseline_rate: float = 0.20
    lift_absolute: float = -0.15
    lift_relative: float = -0.75
    wilson_ci_low: float = 0.02
    wilson_ci_high: float = 0.10
    ci_excludes_baseline: bool = True
    censoring_rate: float = 0.10
    censoring_warning_flag: bool = False
    watchlist_flag: bool = True
    tier_evidence_support: str = ""
    cross_tier_disagreement: bool = False
    loosen_capped_flag: bool = False
    confidence_ceiling_applied: bool = False
    notes: str = ""


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _write_csv(
    path: Path, header: Sequence[str], rows: Sequence[dict[str, Any]]
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join(_format_cell(row.get(col)) for col in header) + "\n")


def write_stage13_candidate_csv(
    run_path: Path, rows: list[Stage13CandidateRow]
) -> Path:
    """Write a Stage 13 candidate_recommendations.csv with the locked schema."""

    run_path = Path(run_path)
    csv_path = run_path / "candidate_recommendations.csv"
    rendered: list[dict[str, Any]] = []
    for r in rows:
        rendered.append({col: getattr(r, col) for col in STAGE13_CANDIDATE_CSV_COLUMNS})
    _write_csv(csv_path, STAGE13_CANDIDATE_CSV_COLUMNS, rendered)
    return csv_path


def write_stage13_manifest(
    run_path: Path,
    *,
    stage12_run_path: Path,
    stage12_manifest_hash: str,
    safe_for_live: bool = False,
    schema_version: str = "1.1",
    recommendation_set_version: str = "sha256:deadbeef",
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write a Stage 13 manifest.json with the L11 invariant.

    Defaults to a well-formed manifest; ``safe_for_live=True`` (or any
    non-False value via ``extra``) exercises the Stage 14 loader's
    invariant-violation path.
    """

    run_path = Path(run_path)
    manifest_path = run_path / "manifest.json"
    payload: dict[str, Any] = {
        "stage13_version": "0.1.0",
        "stage13_schema_version": schema_version,
        "run_timestamp_utc": "2026-05-01T00:00:00+00:00",
        "safe_for_live_policy_consumption": safe_for_live,
        "stage12_run_path": str(Path(stage12_run_path).resolve()),
        "stage12_manifest_hash": stage12_manifest_hash,
        "stage12_input_hashes": {},
        "primary_outcome_metric": "hit_2x_24h",
        "evidence_thresholds": {},
        "loosen_direction_policy": "capped_at_hold_observe_only_v0",
        "data_window_start": "2026-04-01T00:00:00+00:00",
        "data_window_end": "2026-05-01T00:00:00+00:00",
        "data_staleness_warning": False,
        "severity_available": False,
        "scam_adjacent_labels": [],
        "recommendation_set_version": recommendation_set_version,
        "git_commit": None,
    }
    if extra:
        payload.update(extra)
    with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return manifest_path


def write_stage13_run(
    run_path: Path,
    *,
    candidate_rows: list[Stage13CandidateRow],
    stage12_run_path: Path,
    stage12_manifest_hash: str,
    safe_for_live: bool = False,
    schema_version: str = "1.1",
    recommendation_set_version: str = "sha256:deadbeef",
) -> Path:
    """Materialize a Stage 13 run directory on disk.

    Returns the run-directory path. The two files (candidate CSV and
    manifest.json) are written into ``run_path``, which is created
    if it does not exist.
    """

    run_path = Path(run_path)
    run_path.mkdir(parents=True, exist_ok=True)
    write_stage13_candidate_csv(run_path, candidate_rows)
    write_stage13_manifest(
        run_path,
        stage12_run_path=stage12_run_path,
        stage12_manifest_hash=stage12_manifest_hash,
        safe_for_live=safe_for_live,
        schema_version=schema_version,
        recommendation_set_version=recommendation_set_version,
    )
    return run_path


# ---------------------------------------------------------------------------
# Stage 12 long CSV
# ---------------------------------------------------------------------------


STAGE12_LONG_CSV_COLUMNS: tuple[str, ...] = (
    "alert_decision_id",
    "token_address",
    "tier_index",
    "tier_name",
    "decision_type",
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
    "has_outcome_window_24h",
    "outcome_censored_24h",
    "no_outcome_24h",
    "has_primary_outcome",
    "primary_outcome_hit_2x_24h",
    "primary_outcome_hit_3x_24h",
    "primary_outcome_hit_5x_24h",
)


@dataclass
class Stage12LongRow:
    """One row of a synthetic Stage 12 decision_filter_outcome_long.csv.

    A real Stage 12 row carries many more columns (filter_score,
    filter_reason, per-window outcome metrics, etc.); the fixture
    writer emits only the subset Stage 14 actually reads plus the
    nullable boolean outcome flags. This keeps fixtures small and
    matches Stage 14's "extra columns tolerated" loader contract.
    """

    alert_decision_id: str
    token_address: str = "Tok0000000000000000000000000000000000000000"
    tier_index: int | None = 1
    tier_name: str | None = "T1"
    decision_type: str | None = "would_alert"
    filter_name: str | None = "fee_gate_v1"
    filter_version: str | None = "v1"
    threshold_version: str | None = "v1"
    filter_label: str | None = "scam_likely"
    has_outcome_window_24h: bool | None = True
    outcome_censored_24h: bool | None = False
    no_outcome_24h: bool | None = False
    has_primary_outcome: bool | None = True
    primary_outcome_hit_2x_24h: bool | None = False
    primary_outcome_hit_3x_24h: bool | None = False
    primary_outcome_hit_5x_24h: bool | None = False


def _format_long_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def write_stage12_long_csv(
    run_path: Path, rows: list[Stage12LongRow]
) -> Path:
    """Write decision_filter_outcome_long.csv with the documented columns."""

    run_path = Path(run_path)
    csv_path = run_path / "decision_filter_outcome_long.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(STAGE12_LONG_CSV_COLUMNS) + "\n")
        for row in rows:
            cells = [
                _format_long_cell(getattr(row, col))
                for col in STAGE12_LONG_CSV_COLUMNS
            ]
            handle.write(",".join(cells) + "\n")
    return csv_path


def write_stage12_manifest(
    run_path: Path,
    *,
    schema_version: str = "1",
    run_id: str = "20260501T000000Z_fix000",
) -> Path:
    run_path = Path(run_path)
    manifest_path = run_path / "manifest.json"
    payload = {
        "stage": "decision_outcome_analysis",
        "stage_version": "12.v0",
        "schema_version": schema_version,
        "run_id": run_id,
        "created_at": "2026-05-01T00:00:00+00:00",
        "research_only_warning": "RESEARCH ONLY.",
        "censoring_rule": "Per Stage 12 spec.",
        "parameters": {
            "included_decision_statuses": ["would_alert"],
            "decision_time_range_start": "2026-04-01T00:00:00+00:00",
            "decision_time_range_end": "2026-05-01T00:00:00+00:00",
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
    with open(manifest_path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return manifest_path


def write_stage12_run(
    run_path: Path,
    *,
    long_rows: list[Stage12LongRow],
    schema_version: str = "1",
    run_id: str = "20260501T000000Z_fix000",
) -> Path:
    """Materialize a Stage 12 run directory on disk and return its path."""

    run_path = Path(run_path)
    run_path.mkdir(parents=True, exist_ok=True)
    write_stage12_long_csv(run_path, long_rows)
    write_stage12_manifest(run_path, schema_version=schema_version, run_id=run_id)
    return run_path


# ---------------------------------------------------------------------------
# Combined helpers (most tests use these)
# ---------------------------------------------------------------------------


def sha256_of_file(path: Path) -> str:
    """Return ``sha256:<hex>`` of a file's contents.

    Tests use this to compute the Stage 12 manifest hash to embed in
    the Stage 13 manifest's ``stage12_manifest_hash`` field, matching
    the production format Stage 13 records.
    """

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(64 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


@dataclass
class FixtureBundle:
    """Both run directories returned by ``build_default_bundle``."""

    stage12_run_path: Path
    stage13_run_path: Path
    stage12_manifest_hash: str


def build_default_bundle(
    tmp_path: Path,
    *,
    candidate_rows: list[Stage13CandidateRow] | None = None,
    long_rows: list[Stage12LongRow] | None = None,
    safe_for_live: bool = False,
    schema_version_stage13: str = "1.1",
) -> FixtureBundle:
    """Build a paired Stage 12 + Stage 13 fixture under ``tmp_path``.

    Defaults:
      * One ADVANCE_AS_CANDIDATE Stage 13 row for the T1 fee_gate_v1
        scam_likely cohort.
      * Three Stage 12 long rows for distinct decisions that match
        that rule, with mixed outcomes (winner, loser, no_outcome).

    Tests override either list to exercise specific scenarios.
    """

    if candidate_rows is None:
        candidate_rows = [Stage13CandidateRow()]
    if long_rows is None:
        long_rows = [
            Stage12LongRow(
                alert_decision_id="dec_winner",
                primary_outcome_hit_2x_24h=True,
            ),
            Stage12LongRow(
                alert_decision_id="dec_loser",
                primary_outcome_hit_2x_24h=False,
            ),
            Stage12LongRow(
                alert_decision_id="dec_unknown",
                has_primary_outcome=False,
                primary_outcome_hit_2x_24h=None,
            ),
        ]

    stage12_path = write_stage12_run(
        tmp_path / "stage12_run", long_rows=long_rows
    )
    stage12_manifest_hash = sha256_of_file(stage12_path / "manifest.json")

    stage13_path = write_stage13_run(
        tmp_path / "stage13_run",
        candidate_rows=candidate_rows,
        stage12_run_path=stage12_path,
        stage12_manifest_hash=stage12_manifest_hash,
        safe_for_live=safe_for_live,
        schema_version=schema_version_stage13,
    )

    return FixtureBundle(
        stage12_run_path=stage12_path,
        stage13_run_path=stage13_path,
        stage12_manifest_hash=stage12_manifest_hash,
    )
