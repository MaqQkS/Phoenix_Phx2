"""Stage 13 pipeline end-to-end tests.

Spins up a synthetic Stage 12 run directory, calls
``PHX2.stage13.pipeline.run`` with a pinned ``now_utc``, and asserts
on:

  * All five output artifacts created.
  * Reruns with the same inputs produce byte-identical outputs.
  * Empty inputs produce headers-only CSVs and a non-crashing markdown.
  * Manifest carries the locked invariants (safe_for_live=false,
    stage12_input_hashes populated, etc.).
  * Data staleness warning toggles correctly.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PHX2.stage13.pipeline import (
    SAFE_FOR_LIVE_POLICY_CONSUMPTION,
    STAGE13_SCHEMA_VERSION,
    STAGE13_VERSION,
    run,
)
from PHX2.tests.fixtures.stage13.stage12_fixture_writer import (
    BaselineRow,
    FilterByTierRow,
    FilterOverallRow,
    write_stage12_run,
)


_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)


def _build_stage12_run(tmp_path: Path) -> Path:
    return write_stage12_run(
        tmp_path / "stage12_run",
        baseline_rows=[
            BaselineRow(
                tier_index=1, tier_name="T1", n_complete=200,
                hit_2x_24h_count=40, hit_2x_24h_rate=0.20,
                hit_2x_24h_ci_low=0.15, hit_2x_24h_ci_high=0.26,
            ),
            BaselineRow(
                tier_index=2, tier_name="T2", n_complete=150,
                hit_2x_24h_count=30, hit_2x_24h_rate=0.20,
                hit_2x_24h_ci_low=0.14, hit_2x_24h_ci_high=0.27,
            ),
            BaselineRow(
                tier_index=3, tier_name="T3", n_complete=100,
                hit_2x_24h_count=20, hit_2x_24h_rate=0.20,
                hit_2x_24h_ci_low=0.13, hit_2x_24h_ci_high=0.28,
            ),
        ],
        filter_overall_rows=[
            FilterOverallRow(
                filter_label="scam_likely",
                n_complete=300, n_censored=15,
                hit_2x_24h_count=15, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.03, hit_2x_24h_ci_high=0.08,
            ),
        ],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=120, hit_2x_24h_count=6, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.10,
            ),
            FilterByTierRow(
                tier_index=2, tier_name="T2", filter_label="scam_likely",
                n_complete=100, hit_2x_24h_count=5, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.11,
            ),
            FilterByTierRow(
                tier_index=3, tier_name="T3", filter_label="scam_likely",
                n_complete=80, hit_2x_24h_count=4, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.12,
            ),
        ],
        data_window_start="2026-04-01T00:00:00+00:00",
        data_window_end="2026-05-01T00:00:00+00:00",
    )


def test_end_to_end_run_produces_five_artifacts(tmp_path: Path) -> None:
    stage12 = _build_stage12_run(tmp_path)
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
    )
    assert (result.output_dir / "manifest.json").exists()
    assert (result.output_dir / "candidate_recommendations.csv").exists()
    assert (result.output_dir / "evidence_summary.csv").exists()
    assert (result.output_dir / "insufficient_evidence_cohorts.csv").exists()
    assert (result.output_dir / "stage13_policy_review.md").exists()


def test_safe_for_live_is_literal_false(tmp_path: Path) -> None:
    stage12 = _build_stage12_run(tmp_path)
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
    )
    # The in-memory manifest carries the Python ``False`` literal.
    assert result.manifest["safe_for_live_policy_consumption"] is False
    # The on-disk manifest must round-trip to a JSON boolean ``false``
    # (not the string "false"). ``json.loads`` distinguishes the two.
    on_disk = json.loads(
        (result.output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk["safe_for_live_policy_consumption"] is False
    # Module constant is also a Python boolean, not a truthy string.
    assert SAFE_FOR_LIVE_POLICY_CONSUMPTION is False


def test_manifest_contains_input_hashes_and_versions(tmp_path: Path) -> None:
    stage12 = _build_stage12_run(tmp_path)
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
        git_commit="deadbeef",
    )
    m = result.manifest
    assert m["stage13_version"] == STAGE13_VERSION
    assert m["stage13_schema_version"] == STAGE13_SCHEMA_VERSION
    assert m["stage12_manifest_hash"].startswith("sha256:")
    assert set(m["stage12_input_hashes"].keys()) == {
        "cohort_tier_baseline.csv",
        "cohort_filter_label_overall.csv",
        "cohort_filter_label_by_tier.csv",
        "cohort_primitive_bucket_by_tier.csv",
    }
    for value in m["stage12_input_hashes"].values():
        assert value.startswith("sha256:")
    assert m["recommendation_set_version"].startswith("sha256:")
    assert m["git_commit"] == "deadbeef"
    assert m["primary_outcome_metric"] == "hit_2x_24h"
    assert m["loosen_direction_policy"] == "capped_at_hold_observe_only_v0"


def test_byte_identical_rerun_with_pinned_now_utc(tmp_path: Path) -> None:
    stage12 = _build_stage12_run(tmp_path)

    out_root_a = tmp_path / "runs_a"
    out_root_b = tmp_path / "runs_b"

    r1 = run(stage12_run_path=stage12, output_root=out_root_a, now_utc=_NOW)
    r2 = run(stage12_run_path=stage12, output_root=out_root_b, now_utc=_NOW)

    for filename in (
        "candidate_recommendations.csv",
        "evidence_summary.csv",
        "insufficient_evidence_cohorts.csv",
        "stage13_policy_review.md",
    ):
        assert (r1.output_dir / filename).read_bytes() == (
            r2.output_dir / filename
        ).read_bytes(), f"{filename} differs across reruns"

    # Manifest may legitimately differ on resolved stage12_run_path
    # because tmp_path is per-test. So compare the parts that should be
    # byte-stable.
    m1 = json.loads((r1.output_dir / "manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((r2.output_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in (
        "stage13_version",
        "stage13_schema_version",
        "run_timestamp_utc",
        "safe_for_live_policy_consumption",
        "stage12_input_hashes",
        "primary_outcome_metric",
        "recommendation_set_version",
        "loosen_direction_policy",
        "data_window_start",
        "data_window_end",
    ):
        assert m1[key] == m2[key], f"manifest field {key!r} differs across reruns"


def test_empty_stage12_run_produces_headers_only_csvs(tmp_path: Path) -> None:
    stage12 = write_stage12_run(
        tmp_path / "stage12_empty",
        baseline_rows=[],
        filter_overall_rows=[],
        filter_by_tier_rows=[],
    )
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
    )
    candidate = (result.output_dir / "candidate_recommendations.csv").read_text(
        encoding="utf-8"
    )
    # Headers-only: exactly one line.
    assert candidate.count("\n") == 1
    # Manifest still populated.
    assert set(result.manifest["stage12_input_hashes"].keys()) == {
        "cohort_tier_baseline.csv",
        "cohort_filter_label_overall.csv",
        "cohort_filter_label_by_tier.csv",
        "cohort_primitive_bucket_by_tier.csv",
    }
    # Markdown indicates no cohorts.
    md = (result.output_dir / "stage13_policy_review.md").read_text(
        encoding="utf-8"
    )
    assert "No rows" in md


def test_data_staleness_true_when_window_end_old(tmp_path: Path) -> None:
    stage12 = write_stage12_run(
        tmp_path / "stage12_stale",
        baseline_rows=[
            BaselineRow(tier_index=1, tier_name="T1", n_complete=100),
        ],
        filter_overall_rows=[],
        filter_by_tier_rows=[],
        data_window_start="2025-01-01T00:00:00+00:00",
        data_window_end="2025-01-15T00:00:00+00:00",
    )
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
    )
    assert result.manifest["data_staleness_warning"] is True


def test_data_staleness_false_when_window_end_recent(tmp_path: Path) -> None:
    recent_end = (_NOW - timedelta(days=5)).isoformat()
    stage12 = write_stage12_run(
        tmp_path / "stage12_fresh",
        baseline_rows=[
            BaselineRow(tier_index=1, tier_name="T1", n_complete=100),
        ],
        filter_overall_rows=[],
        filter_by_tier_rows=[],
        data_window_start="2026-04-01T00:00:00+00:00",
        data_window_end=recent_end,
    )
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
    )
    assert result.manifest["data_staleness_warning"] is False


def test_insufficient_excluded_from_candidate_csv(tmp_path: Path) -> None:
    stage12 = write_stage12_run(
        tmp_path / "stage12_run",
        baseline_rows=[
            BaselineRow(
                tier_index=1, tier_name="T1", n_complete=200,
                hit_2x_24h_count=40, hit_2x_24h_rate=0.20,
                hit_2x_24h_ci_low=0.15, hit_2x_24h_ci_high=0.26,
            ),
        ],
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="small_cohort",
                n_complete=5, hit_2x_24h_count=1, hit_2x_24h_rate=0.20,
                hit_2x_24h_ci_low=0.05, hit_2x_24h_ci_high=0.55,
                confidence_flag="low_confidence",
            ),
        ],
    )
    result = run(
        stage12_run_path=stage12,
        output_root=tmp_path / "stage13_runs",
        now_utc=_NOW,
    )
    candidate = (result.candidate_csv).read_text(encoding="utf-8")
    insufficient = (result.insufficient_evidence_csv).read_text(encoding="utf-8")
    summary = (result.evidence_summary_csv).read_text(encoding="utf-8")
    assert "small_cohort" not in candidate
    assert "small_cohort" in insufficient
    assert "small_cohort" in summary
