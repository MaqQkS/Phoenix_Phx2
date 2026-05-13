"""Stage 13 writer determinism + content tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage13.types import RecommendationRow
from PHX2.stage13.writer import (
    CANDIDATE_CSV_FILENAME,
    CSV_COLUMNS,
    EVIDENCE_SUMMARY_CSV_FILENAME,
    INSUFFICIENT_EVIDENCE_CSV_FILENAME,
    MANIFEST_FILENAME,
    MARKDOWN_FILENAME,
    compute_recommendation_set_version,
    write_candidate_csv,
    write_evidence_summary_csv,
    write_insufficient_evidence_csv,
    write_manifest,
    write_markdown,
)


def _sample_row(
    *,
    cohort_id: str = "fee_gate_v1@v1[threshold=v1]:scam_likely",
    tier_scope: str = "T1",
    action: str = "ADVANCE_AS_CANDIDATE",
    evidence: str = "strong",
    direction: str = "tighten",
    priority: str = "urgent",
    n_complete: int = 50,
) -> RecommendationRow:
    return RecommendationRow(
        policy_surface="filter_label_blocking",  # type: ignore[arg-type]
        cohort_id=cohort_id,
        tier_scope=tier_scope,  # type: ignore[arg-type]
        action_class=action,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        evidence_class=evidence,  # type: ignore[arg-type]
        policy_severity="unknown",
        review_priority=priority,  # type: ignore[arg-type]
        n_complete=n_complete,
        n_censored=5,
        cohort_rate=0.05,
        baseline_rate=0.20,
        lift_absolute=-0.15,
        lift_relative=-0.75,
        wilson_ci_low=0.02,
        wilson_ci_high=0.10,
        ci_excludes_baseline=True,
        censoring_rate=0.10,
        censoring_warning_flag=False,
        watchlist_flag=True,
        tier_evidence_support=[],
        cross_tier_disagreement=False,
        loosen_capped_flag=False,
        confidence_ceiling_applied=False,
        notes=[],
    )


def test_candidate_csv_excludes_insufficient_evidence(tmp_path: Path) -> None:
    rows = [
        _sample_row(action="ADVANCE_AS_CANDIDATE"),
        _sample_row(cohort_id="other", action="INSUFFICIENT_EVIDENCE",
                    evidence="insufficient", direction="none", priority="low",
                    n_complete=5),
    ]
    path = write_candidate_csv(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    assert "other" not in body
    assert "scam_likely" in body


def test_evidence_summary_includes_every_row(tmp_path: Path) -> None:
    rows = [
        _sample_row(action="ADVANCE_AS_CANDIDATE"),
        _sample_row(cohort_id="x", action="INSUFFICIENT_EVIDENCE",
                    evidence="insufficient", direction="none", priority="low",
                    n_complete=5),
    ]
    path = write_evidence_summary_csv(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    assert "scam_likely" in body
    assert "x" in body


def test_insufficient_only_csv_contains_insufficient_rows_only(tmp_path: Path) -> None:
    rows = [
        _sample_row(action="ADVANCE_AS_CANDIDATE"),
        _sample_row(cohort_id="x", action="INSUFFICIENT_EVIDENCE",
                    evidence="insufficient", direction="none", priority="low",
                    n_complete=7),
        _sample_row(cohort_id="y", action="INSUFFICIENT_EVIDENCE",
                    evidence="insufficient", direction="none", priority="low",
                    n_complete=9),
    ]
    path = write_insufficient_evidence_csv(tmp_path, rows)
    body = path.read_text(encoding="utf-8").splitlines()
    # Header + 2 data rows.
    assert len(body) == 3
    # First data row should be the one with higher n_complete (=9).
    assert "y" in body[1]
    assert "x" in body[2]


def test_csv_header_matches_locked_schema(tmp_path: Path) -> None:
    path = write_candidate_csv(tmp_path, [_sample_row()])
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(CSV_COLUMNS)


def test_csv_byte_identity_across_writes(tmp_path: Path) -> None:
    rows = [
        _sample_row(),
        _sample_row(cohort_id="other", tier_scope="T2"),
    ]
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
    p1 = write_candidate_csv(tmp_path / "a", rows)
    p2 = write_candidate_csv(tmp_path / "b", rows)
    assert p1.read_bytes() == p2.read_bytes()


def test_manifest_json_deterministic_across_writes(tmp_path: Path) -> None:
    manifest = {
        "stage13_version": "0.1.0",
        "stage13_schema_version": "1.0",
        "safe_for_live_policy_consumption": False,
        "stage12_input_hashes": {"x.csv": "sha256:abc"},
        "z_key": "last",
        "a_key": "first",
    }
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    p1 = write_manifest(tmp_path / "a", manifest)
    p2 = write_manifest(tmp_path / "b", manifest)
    assert p1.read_bytes() == p2.read_bytes()
    # Keys sorted; reload to verify shape.
    reloaded = json.loads(p1.read_text(encoding="utf-8"))
    assert list(reloaded.keys()) == sorted(manifest.keys())


def test_markdown_contains_required_sections(tmp_path: Path) -> None:
    manifest = {
        "stage13_version": "0.1.0",
        "stage13_schema_version": "1.0",
        "run_timestamp_utc": "2026-05-12T12:00:00+00:00",
        "safe_for_live_policy_consumption": False,
        "stage12_run_path": "/runs/x",
        "stage12_manifest_hash": "sha256:xyz",
        "primary_outcome_metric": "hit_2x_24h",
        "data_window_start": "2026-01-01T00:00:00+00:00",
        "data_window_end": "2026-02-01T00:00:00+00:00",
        "data_staleness_warning": False,
        "severity_available": False,
        "scam_adjacent_labels": ["fee_gate_v1.scam_likely"],
        "recommendation_set_version": "sha256:abc",
        "git_commit": "abc123",
    }
    path = write_markdown(tmp_path, [_sample_row()], manifest)
    body = path.read_text(encoding="utf-8")
    for header in (
        "# Stage 13 Policy Review",
        "## Run metadata",
        "## Strong candidates (ADVANCE_AS_CANDIDATE)",
        "## Anomalies flagged for manual inspection",
        "## Cohorts on hold for observation (HOLD_OBSERVE_ONLY)",
        "## Cohorts with no signal found",
        "## Insufficient evidence — top candidates for more data",
        "## Cross-tier disagreement summary",
        "## Methodology",
        "## Methodology gaps and known limitations",
        "## Non-goals",
    ):
        assert header in body, f"missing section header: {header!r}"
    # Disclaimer about no automatic policy changes must be present.
    assert "No policy changes were made or recommended" in body


def test_markdown_empty_rows_does_not_crash(tmp_path: Path) -> None:
    manifest = {
        "stage13_version": "0.1.0",
        "run_timestamp_utc": "2026-05-12T12:00:00+00:00",
        "safe_for_live_policy_consumption": False,
        "severity_available": False,
        "scam_adjacent_labels": [],
    }
    path = write_markdown(tmp_path, [], manifest)
    body = path.read_text(encoding="utf-8")
    assert "No rows" in body


def test_recommendation_set_version_stable_across_writes(tmp_path: Path) -> None:
    rows = [_sample_row()]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    p1 = write_candidate_csv(tmp_path / "a", rows)
    p2 = write_candidate_csv(tmp_path / "b", rows)
    v1 = compute_recommendation_set_version(p1)
    v2 = compute_recommendation_set_version(p2)
    assert v1 == v2


def test_float_formatting_three_decimal_places(tmp_path: Path) -> None:
    rows = [_sample_row()]
    path = write_candidate_csv(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    # cohort_rate is 0.05 -> "0.050", baseline_rate 0.20 -> "0.200".
    assert "0.050" in body
    assert "0.200" in body


def test_bool_formatting_lowercase(tmp_path: Path) -> None:
    rows = [_sample_row()]
    path = write_candidate_csv(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    # ci_excludes_baseline=True, censoring_warning_flag=False
    assert "true" in body.lower()
    assert "false" in body.lower()


def test_null_formatting_empty_string(tmp_path: Path) -> None:
    row = _sample_row()
    row.cohort_rate = None
    row.lift_absolute = None
    path = write_candidate_csv(tmp_path, [row])
    body = path.read_text(encoding="utf-8").splitlines()[1]
    # Find cohort_rate column index
    idx = list(CSV_COLUMNS).index("cohort_rate")
    cells = body.split(",")
    # cohort_rate cell should be empty.
    assert cells[idx] == ""


# ---------------------------------------------------------------------------
# Schema 1.1: filter-identity columns appear in the locked CSV schema and
# are rendered correctly for populated and None values.
# ---------------------------------------------------------------------------


def test_filter_identity_columns_present_in_locked_schema() -> None:
    for column in ("filter_name", "filter_version", "filter_label", "threshold_version"):
        assert column in CSV_COLUMNS


def test_filter_identity_columns_rendered_when_populated(tmp_path: Path) -> None:
    row = _sample_row()
    row.filter_name = "fee_gate_v1"
    row.filter_version = "v1"
    row.filter_label = "scam_likely"
    row.threshold_version = "v1"
    path = write_candidate_csv(tmp_path, [row])
    cells = path.read_text(encoding="utf-8").splitlines()[1].split(",")
    assert cells[CSV_COLUMNS.index("filter_name")] == "fee_gate_v1"
    assert cells[CSV_COLUMNS.index("filter_version")] == "v1"
    assert cells[CSV_COLUMNS.index("filter_label")] == "scam_likely"
    assert cells[CSV_COLUMNS.index("threshold_version")] == "v1"


def test_filter_identity_columns_render_empty_when_none(tmp_path: Path) -> None:
    # A primitive cohort row leaves all four identity fields None; the
    # CSV must show empty cells (NOT the literal string "None") so a
    # downstream consumer can detect missing-vs-present cleanly.
    row = _sample_row()
    row.filter_name = None
    row.filter_version = None
    row.filter_label = None
    row.threshold_version = None
    path = write_candidate_csv(tmp_path, [row])
    cells = path.read_text(encoding="utf-8").splitlines()[1].split(",")
    for column in ("filter_name", "filter_version", "filter_label", "threshold_version"):
        assert cells[CSV_COLUMNS.index(column)] == ""
