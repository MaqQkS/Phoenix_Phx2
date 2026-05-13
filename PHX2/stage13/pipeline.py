"""Stage 13 pipeline orchestrator.

Pure-ish ``run(...)`` that loads, classifies, and writes a Stage 13 run.
The function is deterministic given pinned ``now_utc`` and pinned
thresholds (spec L14): the output directory's name, the manifest
timestamp, and every artifact's bytes are reproducible.

The orchestrator does NOT shell out for the git fingerprint -- the CLI
captures the git commit (subprocess at the I/O boundary) and passes it
through here. This mirrors Stage 12's m-3 remediation pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PHX2.stage13.builder import build_recommendations
from PHX2.stage13.loader import (
    Stage12Manifest,
    load_stage12_csvs,
    load_stage12_manifest,
)
from PHX2.stage13.types import SCAM_ADJACENT_LABELS, EvidenceThresholds
from PHX2.stage13.writer import (
    CANDIDATE_CSV_FILENAME,
    compute_recommendation_set_version,
    write_candidate_csv,
    write_evidence_summary_csv,
    write_insufficient_evidence_csv,
    write_manifest,
    write_markdown,
)


STAGE13_VERSION = "0.1.0"
STAGE13_SCHEMA_VERSION = "1.1"
"""Schema 1.1 (Stage 13.1 patch): candidate_recommendations.csv adds
filter_name / filter_version / filter_label / threshold_version columns
populated for the filter_label_blocking surface and left empty for
primitive_bucket_cohort rows. cohort_id, classification logic, and the
``safe_for_live_policy_consumption=false`` invariant are unchanged."""
PRIMARY_OUTCOME_METRIC = "hit_2x_24h"
SAFE_FOR_LIVE_POLICY_CONSUMPTION = False
"""Spec L11: hardcoded false in every Stage 13 manifest. Stage 14 must
refuse to proceed if this flag is missing or true."""

DATA_STALENESS_THRESHOLD_DAYS = 30


@dataclass(frozen=True)
class Stage13RunResult:
    """Result of one Stage 13 run."""

    output_dir: Path
    manifest: dict[str, Any]
    candidate_csv: Path
    evidence_summary_csv: Path
    insufficient_evidence_csv: Path
    markdown: Path


def _format_run_timestamp(now_utc: datetime) -> str:
    """Render UTC timestamp as ``YYYYMMDDTHHMMSSZ`` (deterministic).

    Mirrors Stage 12's run-ID timestamp format but without the random
    hex suffix -- Stage 13 collisions on a single-second boundary are
    handled at directory-creation time by mkdir(exist_ok=False).
    """

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    utc = now_utc.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def _create_run_dir(output_root: Path, now_utc: datetime) -> Path:
    """Materialize the Stage 13 run directory.

    Returns ``<output_root>/<UTC_timestamp>/``. Raises FileExistsError
    if a same-second run already exists -- Stage 13 never overwrites.
    """

    timestamp = _format_run_timestamp(now_utc)
    run_dir = Path(output_root) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _parse_iso(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _compute_data_staleness(
    stage12_manifest: Stage12Manifest,
    now_utc: datetime,
) -> bool:
    """True iff now_utc - data_window_end > 30 days. False otherwise.

    When data_window_end is missing or unparseable, returns False
    (staleness cannot be evaluated; surfaced as a methodology note in
    the markdown).
    """

    end_ts = _parse_iso(stage12_manifest.data_window_end)
    if end_ts is None:
        return False
    delta = now_utc - end_ts
    return delta > timedelta(days=DATA_STALENESS_THRESHOLD_DAYS)


def _build_manifest_dict(
    *,
    stage12_manifest: Stage12Manifest,
    stage12_run_path: Path,
    stage12_input_hashes: dict[str, str],
    thresholds: EvidenceThresholds,
    severity_available: bool,
    now_utc: datetime,
    recommendation_set_version: str,
    git_commit: str | None,
) -> dict[str, Any]:
    return {
        "stage13_version": STAGE13_VERSION,
        "stage13_schema_version": STAGE13_SCHEMA_VERSION,
        "run_timestamp_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "safe_for_live_policy_consumption": SAFE_FOR_LIVE_POLICY_CONSUMPTION,
        "stage12_run_path": str(Path(stage12_run_path).resolve()),
        "stage12_manifest_hash": stage12_manifest.manifest_hash,
        "stage12_input_hashes": stage12_input_hashes,
        "primary_outcome_metric": PRIMARY_OUTCOME_METRIC,
        "evidence_thresholds": thresholds.to_manifest_dict(),
        "loosen_direction_policy": "capped_at_hold_observe_only_v0",
        "data_window_start": stage12_manifest.data_window_start,
        "data_window_end": stage12_manifest.data_window_end,
        "data_staleness_warning": _compute_data_staleness(
            stage12_manifest, now_utc
        ),
        "severity_available": severity_available,
        "scam_adjacent_labels": list(SCAM_ADJACENT_LABELS),
        "recommendation_set_version": recommendation_set_version,
        "git_commit": git_commit,
    }


def run(
    *,
    stage12_run_path: Path,
    output_root: Path,
    now_utc: datetime | None = None,
    thresholds: EvidenceThresholds | None = None,
    git_commit: str | None = None,
) -> Stage13RunResult:
    """End-to-end Stage 13 run.

    Inputs:
      stage12_run_path: directory holding the four Stage 12 cohort CSVs
        + manifest.json.
      output_root: directory where the dated Stage 13 run directory
        will be created.
      now_utc: pinned UTC timestamp for determinism in tests. Defaults
        to ``datetime.now(timezone.utc)`` only when None.
      thresholds: optional override for the locked default thresholds.
      git_commit: optional git SHA captured by the CLI. Pass None to
        leave the manifest's ``git_commit`` as null.

    Stage 13 opens no DB connection. The orchestrator's transitive
    imports never reference sqlite3, statsmodels, or PHX2.analysis
    runtime modules.

    Returns ``Stage13RunResult`` describing the produced artifacts.
    """

    stage12_run_path = Path(stage12_run_path)
    output_root = Path(output_root)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if thresholds is None:
        thresholds = EvidenceThresholds()

    stage12_manifest = load_stage12_manifest(stage12_run_path)
    csv_bundle = load_stage12_csvs(stage12_run_path)

    recommendations = build_recommendations(csv_bundle, thresholds)

    run_dir = _create_run_dir(output_root, now_utc)

    candidate_path = write_candidate_csv(run_dir, recommendations)
    evidence_path = write_evidence_summary_csv(run_dir, recommendations)
    insufficient_path = write_insufficient_evidence_csv(run_dir, recommendations)

    recommendation_set_version = compute_recommendation_set_version(candidate_path)

    manifest_dict = _build_manifest_dict(
        stage12_manifest=stage12_manifest,
        stage12_run_path=stage12_run_path,
        stage12_input_hashes=csv_bundle.input_hashes,
        thresholds=thresholds,
        severity_available=csv_bundle.severity_column is not None,
        now_utc=now_utc,
        recommendation_set_version=recommendation_set_version,
        git_commit=git_commit,
    )

    write_manifest(run_dir, manifest_dict)
    markdown_path = write_markdown(run_dir, recommendations, manifest_dict)

    return Stage13RunResult(
        output_dir=run_dir,
        manifest=manifest_dict,
        candidate_csv=candidate_path,
        evidence_summary_csv=evidence_path,
        insufficient_evidence_csv=insufficient_path,
        markdown=markdown_path,
    )
