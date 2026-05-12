"""Stage 12 TEST 9 -- byte-level reproducibility.

Run the pipeline twice against the same fixture DB with a fixed
``run_id``, ``created_at``, and ``as_of_time`` (all volatile fields
controlled via RunParams), write all five CSVs in both runs, and
assert:

  * Each CSV file is byte-identical between the two runs.
  * The manifest dict is deep-equal between the two runs.

This file is intentionally isolated so byte-identity diffing logic is
contained. The Phase 5 final verification rerun pytest twice and
checks pass-count parity; this test asserts the stronger property
that the output artifacts themselves are byte-identical.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PHX2.analysis.cli import (
    COHORT_FILTER_LABEL_BY_TIER_FILENAME,
    COHORT_FILTER_LABEL_OVERALL_FILENAME,
    COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
    COHORT_TIER_BASELINE_FILENAME,
    LONG_CSV_FILENAME,
    MANIFEST_FILENAME,
    README_FILENAME,
)
from PHX2.analysis.decision_outcome_analysis import (
    RunParams,
    SubstrateReaders,
    run,
)
from PHX2.analysis.readers import (
    AlertDecisionsReader,
    DecisionScoreFeaturesReader,
    FilterEvaluationsReader,
    OutcomeWindowsReader,
    TokenIdentityReader,
)
from PHX2.analysis.writers import (
    create_run_directory,
    write_csv,
    write_manifest,
    write_readme,
)
from PHX2.tests.fixtures.analysis_fixture_builder import (
    build_canonical_fixture,
    open_readonly_connection,
)


REPRO_RUN_ID = "20260101T000000Z_repro0"
REPRO_CREATED_AT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
REPRO_AS_OF = datetime(2026, 1, 10, 0, 0, 0, tzinfo=timezone.utc)


CSV_FILES = (
    LONG_CSV_FILENAME,
    COHORT_TIER_BASELINE_FILENAME,
    COHORT_FILTER_LABEL_OVERALL_FILENAME,
    COHORT_FILTER_LABEL_BY_TIER_FILENAME,
    COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
)


def _run_and_write(db_path: Path, output_root: Path) -> Path:
    """Run the pipeline once and write all seven files. Returns the
    run directory path.
    """

    connection = open_readonly_connection(db_path)
    try:
        readers = SubstrateReaders(
            alert_decisions=AlertDecisionsReader(connection),
            filter_evaluations=FilterEvaluationsReader(connection),
            decision_score_features=DecisionScoreFeaturesReader(connection),
            outcome_windows=OutcomeWindowsReader(connection),
            token_identity=TokenIdentityReader(connection),
        )
        params = RunParams(
            output_root=output_root,
            run_id=REPRO_RUN_ID,
            created_at=REPRO_CREATED_AT,
            as_of_time=REPRO_AS_OF,
        )
        result = run(readers, params)
    finally:
        connection.close()

    run_dir = create_run_directory(output_root, result.run_id)
    write_csv(result.long_df, run_dir / LONG_CSV_FILENAME)
    write_csv(result.cohort_tier_baseline, run_dir / COHORT_TIER_BASELINE_FILENAME)
    write_csv(
        result.cohort_filter_label_overall,
        run_dir / COHORT_FILTER_LABEL_OVERALL_FILENAME,
    )
    write_csv(
        result.cohort_filter_label_by_tier,
        run_dir / COHORT_FILTER_LABEL_BY_TIER_FILENAME,
    )
    write_csv(
        result.cohort_primitive_bucket_by_tier,
        run_dir / COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
    )
    write_manifest(result.manifest, run_dir / MANIFEST_FILENAME)
    write_readme(result.readme_context, run_dir / README_FILENAME)
    return run_dir


def test_test9_csv_byte_identity_across_runs(tmp_path: Path) -> None:
    """Two identical-input runs produce byte-identical CSV files."""

    fixture = build_canonical_fixture(tmp_path / "repro.db")
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    run1_dir = _run_and_write(fixture, out1)
    run2_dir = _run_and_write(fixture, out2)

    for filename in CSV_FILES:
        bytes1 = (run1_dir / filename).read_bytes()
        bytes2 = (run2_dir / filename).read_bytes()
        assert bytes1 == bytes2, (
            f"CSV byte-identity failed for {filename}: "
            f"run1 {len(bytes1)}B vs run2 {len(bytes2)}B"
        )


def test_test9_manifest_deep_equality_across_runs(tmp_path: Path) -> None:
    """Two identical-input runs produce a manifest dict that deep-equals.

    All volatile fields (run_id, created_at) are controlled via
    RunParams. git_commit / git_dirty / environment are constants for
    a given HEAD + interpreter, so they should match across two
    same-process runs.
    """

    fixture = build_canonical_fixture(tmp_path / "repro_manifest.db")
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    run1_dir = _run_and_write(fixture, out1)
    run2_dir = _run_and_write(fixture, out2)

    manifest1 = json.loads((run1_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    manifest2 = json.loads((run2_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest1 == manifest2, "manifest dicts diverge across runs"


def test_test9_readme_byte_identity(tmp_path: Path) -> None:
    """README content is byte-identical across runs.

    Less critical than the CSVs (README is human-readable, not machine
    input), but a divergence here suggests nondeterminism in the
    README template -- worth catching.
    """

    fixture = build_canonical_fixture(tmp_path / "repro_readme.db")
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    run1_dir = _run_and_write(fixture, out1)
    run2_dir = _run_and_write(fixture, out2)

    assert (run1_dir / README_FILENAME).read_bytes() == (
        run2_dir / README_FILENAME
    ).read_bytes()
