"""Stage 13 loader / validator unit tests.

Covers spec items L11 (input hashing), L12 (schema-version mismatch
hard fail), L13 (confidence flag detection), and the column-presence
validation for each of the four required Stage 12 cohort CSVs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage13.loader import (
    EXPECTED_STAGE12_SCHEMA_VERSION,
    Stage13IncompatibleStage12,
    Stage13MissingColumn,
    Stage13MissingInput,
    hash_stage12_inputs,
    load_stage12_csvs,
    load_stage12_manifest,
)
from PHX2.tests.fixtures.stage13.stage12_fixture_writer import (
    BaselineRow,
    FilterByTierRow,
    FilterOverallRow,
    PrimitiveBucketRow,
    write_stage12_run,
)


def _minimal_baseline_rows() -> list[BaselineRow]:
    return [
        BaselineRow(tier_index=1, tier_name="T1", n_complete=100, hit_2x_24h_rate=0.20),
        BaselineRow(tier_index=2, tier_name="T2", n_complete=80, hit_2x_24h_rate=0.18),
        BaselineRow(tier_index=3, tier_name="T3", n_complete=60, hit_2x_24h_rate=0.15),
    ]


def _minimal_filter_overall_rows() -> list[FilterOverallRow]:
    return [
        FilterOverallRow(
            filter_label="scam_likely", n_complete=120, hit_2x_24h_rate=0.05
        ),
    ]


def _minimal_filter_by_tier_rows() -> list[FilterByTierRow]:
    return [
        FilterByTierRow(
            tier_index=1, tier_name="T1", filter_label="scam_likely",
            n_complete=50, hit_2x_24h_rate=0.04,
        ),
        FilterByTierRow(
            tier_index=2, tier_name="T2", filter_label="scam_likely",
            n_complete=40, hit_2x_24h_rate=0.05,
        ),
    ]


def _write_valid_run(tmp_path: Path) -> Path:
    return write_stage12_run(
        tmp_path / "stage12_valid",
        baseline_rows=_minimal_baseline_rows(),
        filter_overall_rows=_minimal_filter_overall_rows(),
        filter_by_tier_rows=_minimal_filter_by_tier_rows(),
    )


def test_load_manifest_happy_path(tmp_path: Path) -> None:
    run = _write_valid_run(tmp_path)
    manifest = load_stage12_manifest(run)
    assert manifest.schema_version == EXPECTED_STAGE12_SCHEMA_VERSION
    assert manifest.stage == "decision_outcome_analysis"
    assert manifest.data_window_start is not None
    assert manifest.data_window_end is not None
    assert manifest.manifest_hash.startswith("sha256:")


def test_load_manifest_missing_file_raises(tmp_path: Path) -> None:
    (tmp_path / "stage12_empty").mkdir()
    with pytest.raises(Stage13MissingInput):
        load_stage12_manifest(tmp_path / "stage12_empty")


def test_load_manifest_schema_version_mismatch_raises(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "stage12_bad_schema",
        baseline_rows=_minimal_baseline_rows(),
        filter_overall_rows=_minimal_filter_overall_rows(),
        filter_by_tier_rows=_minimal_filter_by_tier_rows(),
        schema_version="999",
    )
    with pytest.raises(Stage13IncompatibleStage12):
        load_stage12_manifest(run)


def test_load_csvs_happy_path(tmp_path: Path) -> None:
    run = _write_valid_run(tmp_path)
    bundle = load_stage12_csvs(run)
    assert len(bundle.tier_baseline) == 3
    assert bundle.tier_baseline[0]["tier_name"] == "T1"
    assert bundle.tier_baseline[0]["n_complete"] == 100
    assert bundle.tier_baseline[0]["hit_2x_24h_rate"] == 0.20
    # Severity column not present in the canonical Stage 12 schema.
    assert bundle.severity_column is None


def test_load_csvs_missing_required_column_raises(tmp_path: Path) -> None:
    run = _write_valid_run(tmp_path)
    bad = run / "cohort_tier_baseline.csv"
    text = bad.read_text(encoding="utf-8").splitlines()
    # Drop the n_complete column from the header.
    header = text[0].split(",")
    keep_idx = [i for i, col in enumerate(header) if col != "n_complete"]
    new_lines = []
    for line in text:
        cells = line.split(",")
        new_lines.append(",".join(cells[i] for i in keep_idx))
    bad.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    with pytest.raises(Stage13MissingColumn):
        load_stage12_csvs(run)


def test_load_csvs_missing_required_file_raises(tmp_path: Path) -> None:
    run = _write_valid_run(tmp_path)
    (run / "cohort_filter_label_overall.csv").unlink()
    with pytest.raises(Stage13MissingInput):
        load_stage12_csvs(run)


def test_input_hashes_match_filesystem(tmp_path: Path) -> None:
    run = _write_valid_run(tmp_path)
    hashes = hash_stage12_inputs(run)
    # All four required files hash.
    assert set(hashes.keys()) == {
        "cohort_tier_baseline.csv",
        "cohort_filter_label_overall.csv",
        "cohort_filter_label_by_tier.csv",
        "cohort_primitive_bucket_by_tier.csv",
    }
    # Re-hashing returns the same digests (determinism).
    second = hash_stage12_inputs(run)
    assert hashes == second


def test_severity_column_detected_when_present(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "stage12_with_share",
        baseline_rows=[
            BaselineRow(
                tier_index=1,
                tier_name="T1",
                n_complete=100,
                extra_columns={"decision_share": 0.40},
            ),
        ],
        filter_overall_rows=_minimal_filter_overall_rows(),
        filter_by_tier_rows=_minimal_filter_by_tier_rows(),
        extra_columns=("decision_share",),
    )
    bundle = load_stage12_csvs(run)
    assert bundle.severity_column == "decision_share"


def test_empty_but_schema_valid_csvs_load_cleanly(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "stage12_empty_rows",
        baseline_rows=[],
        filter_overall_rows=[],
        filter_by_tier_rows=[],
        primitive_bucket_rows=[],
    )
    bundle = load_stage12_csvs(run)
    assert bundle.tier_baseline == []
    assert bundle.filter_label_overall == []
    assert bundle.filter_label_by_tier == []
    assert bundle.primitive_bucket_by_tier == []
    # Hashes still populated even for empty CSVs.
    assert set(bundle.input_hashes.keys()) == {
        "cohort_tier_baseline.csv",
        "cohort_filter_label_overall.csv",
        "cohort_filter_label_by_tier.csv",
        "cohort_primitive_bucket_by_tier.csv",
    }


def test_numeric_coercion(tmp_path: Path) -> None:
    run = _write_valid_run(tmp_path)
    bundle = load_stage12_csvs(run)
    row = bundle.tier_baseline[0]
    # Integer fields parsed as int, not str.
    assert isinstance(row["n_complete"], int)
    assert isinstance(row["tier_index"], int)
    # Rate fields parsed as float.
    assert isinstance(row["hit_2x_24h_rate"], float)
    # NULL columns (e.g. median_max_return_24h) parsed as None.
    assert row["median_max_return_24h"] is None
