"""Stage 12 pipeline tests.

Phase 2 smoke + Phase 3 CLI smoke + Phase 4 locked tests
(TEST 1, 2, 3, 4, 6 pipeline parts, 7, 8, 12 + NULL-symbol regression).

TEST 5 (Wilson CI) and TEST 11 (confidence_flag boundaries) live in
test_analysis_metrics.py (Phase 1, unit-level).
TEST 9 (reproducibility byte-identity) lives in test_analysis_repro.py.
TEST 10 (read-isolation) lives in test_analysis_read_isolation.py.
TEST 6 unit parts (quartile edges, degeneracy) live in
test_analysis_buckets.py (Phase 1).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import PHX2

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
from PHX2.tests.fixtures.analysis_fixture_builder import (
    build_canonical_fixture,
    build_censoring_fixture,
    build_empty_substrate_fixture,
    build_join_cardinality_fixture,
    build_missing_data_fixture,
    build_null_symbol_fixture,
    build_smoke_fixture,
    build_time_range_fixture,
    open_readonly_connection,
)


MANIFEST_TOP_LEVEL_KEYS = {
    "stage",
    "stage_version",
    "schema_version",
    "run_id",
    "created_at",
    "research_only_warning",
    "censoring_rule",
    "parameters",
    "pre_join_row_counts",
    "post_join_row_counts",
    "primitives_analyzed",
    "primitives_skipped",
    "outputs",
    "environment",
    "git_commit",
    "git_dirty",
}


def test_phase2_pipeline_smoke(tmp_path: Path) -> None:
    """Single end-to-end smoke covering the Phase 2 contract.

    Decision 1001 has a filter eval + DSF row + COMPLETE 24h outcome.
    Decision 1002 has no filter eval, no DSF, and no outcome.
    The left-join pipeline must produce exactly 2 long rows; the
    manifest must carry all top-level keys; both decisions appear in
    cohort_tier_baseline; the L1 read-only contract is honored
    (full no-write verification lives in Phase 4 TEST 1).
    """

    fixture = build_smoke_fixture(tmp_path / "phx2_stage12_smoke.db")

    connection = open_readonly_connection(fixture)
    try:
        readers = SubstrateReaders(
            alert_decisions=AlertDecisionsReader(connection),
            filter_evaluations=FilterEvaluationsReader(connection),
            decision_score_features=DecisionScoreFeaturesReader(connection),
            outcome_windows=OutcomeWindowsReader(connection),
            token_identity=TokenIdentityReader(connection),
        )
        result = run(
            readers,
            RunParams(
                output_root=tmp_path / "output",
                run_id="20260101T000000Z_smoke0",
                created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                as_of_time=datetime(2026, 1, 3, 0, 0, 0, tzinfo=timezone.utc),
            ),
        )
    finally:
        connection.close()

    # RunResult is non-empty.
    assert result.run_id == "20260101T000000Z_smoke0"

    # long_df: one row per (decision, filter_eval); decision 1002 has
    # no filter eval so its left-joined row carries NULL filter fields.
    assert len(result.long_df) == 2
    ids = sorted(int(x) for x in result.long_df["alert_decision_id"].tolist())
    assert ids == [1001, 1002]

    # Manifest top-level shape (Phase 4 TEST 7 expands per-key
    # assertions; this is the structural smoke).
    assert MANIFEST_TOP_LEVEL_KEYS.issubset(set(result.manifest.keys()))

    # The five cohort outputs are registered.
    assert set(result.manifest["outputs"].keys()) >= {
        "long",
        "cohort_tier_baseline",
        "cohort_filter_label_overall",
        "cohort_filter_label_by_tier",
        "cohort_primitive_bucket_by_tier",
    }


# ---------------------------------------------------------------------------
# Phase 3 -- CLI integration smoke
# ---------------------------------------------------------------------------


CLI_EXPECTED_FILES = (
    "manifest.json",
    "README.md",
    "decision_filter_outcome_long.csv",
    "cohort_tier_baseline.csv",
    "cohort_filter_label_overall.csv",
    "cohort_filter_label_by_tier.csv",
    "cohort_primitive_bucket_by_tier.csv",
)


def test_phase3_cli_smoke(tmp_path: Path) -> None:
    """Invoke `python -m PHX2.analysis.cli` against the smoke fixture.

    Asserts:
      * exit code 0
      * run directory exists at
        <output-dir>/decision_outcome_analysis/<run_id>/
      * all seven output files are present
      * manifest.json validates as JSON and carries the override run_id
    """

    fixture_db = build_smoke_fixture(tmp_path / "smoke_cli.db")
    output_dir = tmp_path / "out"
    override_run_id = "20260101T000000Z_clismk"

    repo_root = Path(PHX2.__file__).parent.parent

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "PHX2.analysis.cli",
            "--db",
            str(fixture_db),
            "--output-dir",
            str(output_dir),
            "--run-id",
            override_run_id,
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
    )

    assert proc.returncode == 0, (
        f"CLI failed: rc={proc.returncode}\n"
        f"stderr={proc.stderr!r}\nstdout={proc.stdout!r}"
    )

    run_dir = output_dir / "decision_outcome_analysis" / override_run_id
    assert run_dir.exists(), f"missing run directory: {run_dir}"

    for filename in CLI_EXPECTED_FILES:
        path = run_dir / filename
        assert path.exists(), f"missing output file: {path}"
        # All files should have some content (manifest at minimum is
        # non-trivial JSON; CSVs at minimum have a header row).
        assert path.stat().st_size > 0, f"empty output file: {path}"

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == override_run_id
    assert manifest["stage"] == "decision_outcome_analysis"

    # CLI prints the run directory path on success.
    assert override_run_id in proc.stdout


# ---------------------------------------------------------------------------
# Phase 4 -- shared helpers
# ---------------------------------------------------------------------------


def _make_readers(connection: sqlite3.Connection) -> SubstrateReaders:
    return SubstrateReaders(
        alert_decisions=AlertDecisionsReader(connection),
        filter_evaluations=FilterEvaluationsReader(connection),
        decision_score_features=DecisionScoreFeaturesReader(connection),
        outcome_windows=OutcomeWindowsReader(connection),
        token_identity=TokenIdentityReader(connection),
    )


def _run_pipeline(
    db_path: Path,
    output_root: Path,
    *,
    run_id: str,
    created_at: datetime,
    as_of_time: datetime | None = None,
    decision_time_range_start: datetime | None = None,
    decision_time_range_end: datetime | None = None,
):
    connection = open_readonly_connection(db_path)
    try:
        readers = _make_readers(connection)
        params = RunParams(
            output_root=output_root,
            run_id=run_id,
            created_at=created_at,
            as_of_time=as_of_time,
            decision_time_range_start=decision_time_range_start,
            decision_time_range_end=decision_time_range_end,
        )
        return run(readers, params)
    finally:
        connection.close()


def _row_counts(db_path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    connection = sqlite3.connect(str(db_path))
    try:
        for table in (
            "alert_decisions",
            "filter_evaluations",
            "decision_score_features",
            "outcome_windows",
            "token_sequence_state",
            "schema_migrations",
        ):
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            out[table] = int(row[0])
    finally:
        connection.close()
    return out


FIXED_CREATED_AT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
FIXED_AS_OF = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# TEST 1 -- no-write
# ---------------------------------------------------------------------------


def test_test1_pipeline_writes_nothing_to_substrate(tmp_path: Path) -> None:
    """L1: row counts in all substrate tables unchanged across a run."""

    fixture = build_canonical_fixture(tmp_path / "t1.db")
    pre = _row_counts(fixture)
    _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t1____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    post = _row_counts(fixture)
    assert pre == post, (
        f"row counts changed across run: pre={pre} post={post}"
    )


def test_test1_readonly_uri_rejects_writes(tmp_path: Path) -> None:
    """The CLI-style mode=ro URI must refuse a direct INSERT.

    Defensive: confirms the operational enforcement boundary works on
    this platform. Without this we cannot trust that a connection
    obtained via ``open_readonly_connection`` is actually read-only.
    """

    fixture = build_smoke_fixture(tmp_path / "ro.db")
    connection = open_readonly_connection(fixture)
    try:
        import pytest

        with pytest.raises(sqlite3.OperationalError):
            connection.execute(
                "INSERT INTO alert_decisions ("
                "id, token_address, evaluated_at, decision_type, primary_reason, "
                "reasons_json, would_alert, blocked, skipped, ath_status, "
                "ath_confidence, filter_labels_json, tier_context_json, "
                "key_feature_snapshot_json, policy_version, created_at, "
                "data_status, missing_reasons_json"
                ") VALUES (?, ?, ?, ?, ?, '[]', 0, 0, 0, ?, ?, '{}', '{}', '{}', ?, ?, ?, '[]')",
                (
                    9999,
                    "TKN_RO",
                    "2026-01-01T00:00:00+00:00",
                    "skip",
                    "policy_disabled",
                    "unknown",
                    "unknown",
                    "test",
                    "2026-01-01T00:00:00+00:00",
                    "ok",
                ),
            )
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# TEST 2 -- join cardinality
# ---------------------------------------------------------------------------


def test_test2_join_cardinality(tmp_path: Path) -> None:
    """A (1 filter eval), B (2 filter evals), C (0 filter evals).

    Asserts: long_df has 4 rows; 3 distinct decisions; C row has
    filter_evaluation_present=False and all filter fields NULL.
    """

    fixture = build_join_cardinality_fixture(tmp_path / "t2.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t2____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    long_df = result.long_df
    assert len(long_df) == 4
    assert long_df["alert_decision_id"].nunique() == 3

    # Decision C: id 3003, no filter eval.
    c_row = long_df[long_df["alert_decision_id"] == 3003]
    assert len(c_row) == 1
    c = c_row.iloc[0]
    assert bool(c["filter_evaluation_present"]) is False
    assert pd.isna(c["filter_name"])
    assert pd.isna(c["filter_label"])
    assert pd.isna(c["filter_evaluation_id"])

    # Decision B: 2 filter evals.
    b_rows = long_df[long_df["alert_decision_id"] == 3002]
    assert len(b_rows) == 2


# ---------------------------------------------------------------------------
# TEST 3 -- censoring
# ---------------------------------------------------------------------------


def test_test3_censoring(tmp_path: Path) -> None:
    """A: COMPLETE 24h, hit_2x=True. B: 24h row data_status=NO_PRICE_DATA.

    Cohort T1 row must report n_decisions=2, n_complete=1, n_censored=1,
    n_no_outcome=0, hit_2x_24h_count=1, hit_2x_24h_rate=1.0.
    """

    fixture = build_censoring_fixture(tmp_path / "t3.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t3____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )

    long_df = result.long_df.set_index("alert_decision_id")
    # B (3102): censored
    b = long_df.loc[3102]
    assert bool(b["has_outcome_window_24h"]) is True
    assert bool(b["outcome_censored_24h"]) is True
    assert bool(b["no_outcome_24h"]) is False
    assert bool(b["has_primary_outcome"]) is False
    assert pd.isna(b["primary_outcome_hit_2x_24h"])

    # A (3101): complete, hit_2x=True
    a = long_df.loc[3101]
    assert bool(a["has_primary_outcome"]) is True
    assert bool(a["primary_outcome_hit_2x_24h"]) is True

    cohort = result.cohort_tier_baseline.set_index("tier_index")
    t1 = cohort.loc[1]
    assert int(t1["n_decisions"]) == 2
    assert int(t1["n_complete"]) == 1
    assert int(t1["n_censored"]) == 1
    assert int(t1["n_no_outcome"]) == 0
    assert int(t1["hit_2x_24h_count"]) == 1
    assert float(t1["hit_2x_24h_rate"]) == 1.0


# ---------------------------------------------------------------------------
# TEST 4 -- missing data
# ---------------------------------------------------------------------------


def test_test4_missing_data_decomposes_cleanly(tmp_path: Path) -> None:
    """Decisions with missing DSF / filter / outcome.

    Asserts: pipeline completes; all decisions appear in long_df;
    has_* flags reflect actual presence; cohort denominator
    decomposition n_decisions = n_complete + n_censored + n_no_outcome.
    """

    fixture = build_missing_data_fixture(tmp_path / "t4.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t4____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )

    long_df = result.long_df.set_index("alert_decision_id")
    assert set(long_df.index) == {3201, 3202, 3203, 3204}

    # 3201: full row
    assert bool(long_df.loc[3201, "filter_evaluation_present"]) is True
    assert bool(long_df.loc[3201, "decision_score_features_present"]) is True
    assert bool(long_df.loc[3201, "has_primary_outcome"]) is True

    # 3202: no DSF, has filter, has complete outcome
    assert bool(long_df.loc[3202, "filter_evaluation_present"]) is True
    assert bool(long_df.loc[3202, "decision_score_features_present"]) is False
    assert bool(long_df.loc[3202, "has_primary_outcome"]) is True

    # 3203: has DSF, no filter, has complete outcome
    assert bool(long_df.loc[3203, "filter_evaluation_present"]) is False
    assert bool(long_df.loc[3203, "decision_score_features_present"]) is True
    assert bool(long_df.loc[3203, "has_primary_outcome"]) is True

    # 3204: has DSF, has filter, no outcome
    assert bool(long_df.loc[3204, "has_outcome_window_24h"]) is False
    assert bool(long_df.loc[3204, "no_outcome_24h"]) is True
    assert bool(long_df.loc[3204, "has_primary_outcome"]) is False

    cohort = result.cohort_tier_baseline.set_index("tier_index")
    t1 = cohort.loc[1]
    n = int(t1["n_decisions"])
    decomp = (
        int(t1["n_complete"])
        + int(t1["n_censored"])
        + int(t1["n_no_outcome"])
    )
    assert n == decomp, (
        f"denominator decomposition failed: n_decisions={n} "
        f"!= n_complete+n_censored+n_no_outcome={decomp}"
    )


# ---------------------------------------------------------------------------
# TEST 6 (pipeline parts) -- bucket assignments propagate to cohort CSV
# and manifest.primitives_analyzed records the bucketing edges.
# Unit-level TEST 6 (quartile edges, degeneracy, missing routing) lives
# in test_analysis_buckets.py.
# ---------------------------------------------------------------------------


def test_test6_pipeline_bucket_assignments(tmp_path: Path) -> None:
    """Run pipeline against canonical fixture. Assert
    cohort_primitive_bucket_by_tier emits rows for at least one
    quartile primitive and the two v0 domain primitives, with
    bucket_low / bucket_high populated per §5.7 and the manifest
    edges recorded.
    """

    fixture = build_canonical_fixture(tmp_path / "t6.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t6____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    cohort = result.cohort_primitive_bucket_by_tier
    assert len(cohort) > 0

    primitive_names = set(cohort["primitive_name"].tolist())
    # The two v0 domain primitives must appear (non-degenerate
    # population in canonical fixture).
    assert "time_since_migration_seconds" in primitive_names
    assert "time_since_ath_seconds" in primitive_names

    # At least one quartile primitive must also appear (event_count_5m
    # has 30+ distinct values in canonical fixture).
    quartile_rows = cohort[cohort["bucket_method"] == "quartile"]
    assert not quartile_rows.empty
    quartile_names = set(quartile_rows["primitive_name"].tolist())
    # event_count_5m and several others should be quartile-bucketed.
    assert quartile_names, "no quartile-bucketed primitives surfaced"

    # bucket_low / bucket_high populated for non-missing buckets in
    # quartile primitives.
    non_missing = quartile_rows[quartile_rows["bucket_index"] != "missing"]
    assert non_missing["bucket_low"].notna().all()
    assert non_missing["bucket_high"].notna().all()

    # manifest.primitives_analyzed records the quartile edges.
    analyzed = result.manifest["primitives_analyzed"]
    quartile_analyzed = {
        name for name, info in analyzed.items() if info["method"] == "quartile"
    }
    assert quartile_analyzed
    # Each analyzed quartile primitive must have a non-null 3-edge list.
    for name in quartile_analyzed:
        edges = analyzed[name]["edges"]
        assert edges is not None and len(edges) == 3, (
            f"{name} edges malformed: {edges!r}"
        )

    # Domain-bucketed primitives have edges=None (domain buckets are
    # declared, not derived).
    for name in ("time_since_migration_seconds", "time_since_ath_seconds"):
        assert analyzed[name]["method"] == "domain"
        assert analyzed[name]["edges"] is None
        # All 5 domain buckets registered (missing is added only when
        # NULL values are present in the canonical fixture).
        assert len(analyzed[name]["buckets"]) >= 5


# ---------------------------------------------------------------------------
# TEST 7 -- manifest schema
# ---------------------------------------------------------------------------


def test_test7_manifest_top_level_keys_present(tmp_path: Path) -> None:
    """manifest.json carries every top-level key in §5.8."""

    fixture = build_canonical_fixture(tmp_path / "t7.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t7____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    assert MANIFEST_TOP_LEVEL_KEYS.issubset(set(result.manifest.keys()))


def test_test7_outputs_schema_matches_dataframe_columns(tmp_path: Path) -> None:
    """manifest.outputs[<csv>].schema lists exactly the DataFrame columns
    that ``writers.write_csv`` will emit, in the same order. This is
    the §8.7 contract: an analyst reading the manifest knows the CSV
    schema without opening the file.
    """

    fixture = build_canonical_fixture(tmp_path / "t7b.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t7b___",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    outputs = result.manifest["outputs"]

    df_by_key = {
        "long": result.long_df,
        "cohort_tier_baseline": result.cohort_tier_baseline,
        "cohort_filter_label_overall": result.cohort_filter_label_overall,
        "cohort_filter_label_by_tier": result.cohort_filter_label_by_tier,
        "cohort_primitive_bucket_by_tier": result.cohort_primitive_bucket_by_tier,
    }
    for key, df in df_by_key.items():
        assert outputs[key]["schema"] == list(df.columns), (
            f"schema mismatch for {key}"
        )
        assert outputs[key]["row_count"] == len(df)


# ---------------------------------------------------------------------------
# TEST 8 -- empty substrate
# ---------------------------------------------------------------------------


def test_test8_empty_substrate(tmp_path: Path) -> None:
    """Fixture with only SKIP/BLOCK decisions. WOULD_ALERT filter
    screens them out; pipeline still produces all five CSVs with
    headers only, and the README "no eligible decisions" path fires.
    """

    fixture = build_empty_substrate_fixture(tmp_path / "t8.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t8____",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    assert len(result.long_df) == 0
    assert len(result.cohort_tier_baseline) == 0
    assert len(result.cohort_filter_label_overall) == 0
    assert len(result.cohort_filter_label_by_tier) == 0
    assert len(result.cohort_primitive_bucket_by_tier) == 0
    assert result.manifest["post_join_row_counts"]["long_csv_rows"] == 0
    assert result.manifest["post_join_row_counts"]["eligible_decisions"] == 0


def test_test8_empty_substrate_cli_writes_all_files(tmp_path: Path) -> None:
    """CLI sub-process variant of TEST 8 -- verify the writers emit
    header-only files and README contains the no-eligible-decisions
    text per spec §5.9.
    """

    fixture = build_empty_substrate_fixture(tmp_path / "t8b.db")
    output_dir = tmp_path / "out"
    repo_root = Path(PHX2.__file__).parent.parent
    run_id = "20260101T000000Z_t8b___"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "PHX2.analysis.cli",
            "--db",
            str(fixture),
            "--output-dir",
            str(output_dir),
            "--run-id",
            run_id,
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
    )
    assert proc.returncode == 0, (
        f"CLI exited {proc.returncode}: stderr={proc.stderr}"
    )

    run_dir = output_dir / "decision_outcome_analysis" / run_id
    for filename in (
        "manifest.json",
        "README.md",
        "decision_filter_outcome_long.csv",
        "cohort_tier_baseline.csv",
        "cohort_filter_label_overall.csv",
        "cohort_filter_label_by_tier.csv",
        "cohort_primitive_bucket_by_tier.csv",
    ):
        path = run_dir / filename
        assert path.exists()
        assert path.stat().st_size > 0

    readme = (run_dir / "README.md").read_text(encoding="utf-8")
    assert "no eligible decisions" in readme.lower()


# ---------------------------------------------------------------------------
# TEST 12 -- decision-time-range filter
# ---------------------------------------------------------------------------


def test_test12_decision_time_range_lower_bound(tmp_path: Path) -> None:
    """Three decisions at t1, t2, t3. Filter with start=t2 must keep
    only decisions evaluated at >= t2 (inclusive lower bound)."""

    fixture = build_time_range_fixture(tmp_path / "t12.db")
    t2 = datetime(2026, 5, 1, 11, 0, 0, tzinfo=timezone.utc)
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_t12___",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
        decision_time_range_start=t2,
    )
    ids = sorted(int(x) for x in result.long_df["alert_decision_id"].tolist())
    # 3401 evaluated at t1 (10:00); 3402 at t2 (11:00); 3403 at t3 (12:00).
    assert ids == [3402, 3403]

    # Manifest records the parameter.
    assert (
        result.manifest["parameters"]["decision_time_range_start"]
        == "2026-05-01T11:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# NULL-symbol regression (operator-flagged at Phase 3/4 boundary)
# ---------------------------------------------------------------------------


def test_null_symbol_dsf_null_preserved_over_token_state_fallback(
    tmp_path: Path,
) -> None:
    """Two cases:

    Case A -- Decision 3501: DSF row exists, token_symbol IS NULL,
        token_sequence_state.symbol == "TESTSYM". Long-CSV symbol must
        be NULL (DSF's frozen value), NOT "TESTSYM" (post-decision
        fallback).
    Case B -- Decision 3502: NO DSF row, token_sequence_state.symbol
        == "FALLBACK". Long-CSV symbol must be "FALLBACK".
    """

    fixture = build_null_symbol_fixture(tmp_path / "tns.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_tns___",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )
    long_df = result.long_df.set_index("alert_decision_id")

    # Case A: DSF present with token_symbol=NULL -- symbol must be NULL.
    assert bool(long_df.loc[3501, "decision_score_features_present"]) is True
    assert pd.isna(long_df.loc[3501, "symbol"]), (
        f"Case A: expected NULL symbol, got {long_df.loc[3501, 'symbol']!r}"
    )

    # Case B: no DSF -- fall back to token_sequence_state.
    assert bool(long_df.loc[3502, "decision_score_features_present"]) is False
    assert long_df.loc[3502, "symbol"] == "FALLBACK"


# ---------------------------------------------------------------------------
# Remediation M-1 -- threshold_version partitions filter cohorts
# ---------------------------------------------------------------------------


def test_remediation_threshold_version_partitions_filter_cohorts(
    tmp_path: Path,
) -> None:
    """The canonical fixture's T2 block has decisions 2019, 2022, 2025 all
    on fee_gate / v1 / NORMAL. Decisions 2022 and 2025 carry
    threshold_version="v2"; 2019 carries threshold_version="v1".

    Before the M-1 fix, the cohort builders grouped only on
    (filter_name, filter_version, filter_label) and would have merged
    the three decisions into one T2 NORMAL row. After the fix, the
    grouping additionally partitions on threshold_version, producing
    two rows: v1 with 1 decision and v2 with 2 decisions.
    """

    fixture = build_canonical_fixture(tmp_path / "thrver.db")
    result = _run_pipeline(
        fixture,
        tmp_path / "out",
        run_id="20260101T000000Z_thrver",
        created_at=FIXED_CREATED_AT,
        as_of_time=FIXED_AS_OF,
    )

    # --- cohort_filter_label_by_tier: T2 NORMAL partitioned by threshold_version
    by_tier = result.cohort_filter_label_by_tier
    assert "threshold_version" in by_tier.columns, (
        "cohort_filter_label_by_tier must include threshold_version column"
    )
    t2_normal = by_tier[
        (by_tier["tier_index"] == 2)
        & (by_tier["filter_name"] == "fee_gate")
        & (by_tier["filter_version"] == "v1")
        & (by_tier["filter_label"] == "NORMAL")
    ]
    thr_versions = sorted(t2_normal["threshold_version"].tolist())
    assert thr_versions == ["v1", "v2"], (
        f"Expected two rows split by threshold_version, got {thr_versions!r}. "
        f"Found {len(t2_normal)} matching row(s)."
    )
    v1_row = t2_normal[t2_normal["threshold_version"] == "v1"].iloc[0]
    v2_row = t2_normal[t2_normal["threshold_version"] == "v2"].iloc[0]
    assert int(v1_row["n_decisions"]) == 1, (
        "v1 partition should have 1 decision (id 2019); "
        f"got {int(v1_row['n_decisions'])}"
    )
    assert int(v2_row["n_decisions"]) == 2, (
        "v2 partition should have 2 decisions (ids 2022, 2025); "
        f"got {int(v2_row['n_decisions'])}"
    )

    # --- cohort_filter_label_overall: same partition without tier dimension
    overall = result.cohort_filter_label_overall
    assert "threshold_version" in overall.columns, (
        "cohort_filter_label_overall must include threshold_version column"
    )
    normal_overall = overall[
        (overall["filter_name"] == "fee_gate")
        & (overall["filter_version"] == "v1")
        & (overall["filter_label"] == "NORMAL")
    ]
    overall_thr = sorted(normal_overall["threshold_version"].tolist())
    assert overall_thr == ["v1", "v2"], (
        f"cohort_filter_label_overall should have two NORMAL rows for "
        f"fee_gate v1 split by threshold_version; got {overall_thr!r}"
    )

    # --- manifest schemas advertise threshold_version
    overall_schema = result.manifest["outputs"]["cohort_filter_label_overall"]["schema"]
    by_tier_schema = result.manifest["outputs"]["cohort_filter_label_by_tier"]["schema"]
    assert "threshold_version" in overall_schema, (
        "manifest.outputs.cohort_filter_label_overall.schema missing "
        "threshold_version"
    )
    assert "threshold_version" in by_tier_schema, (
        "manifest.outputs.cohort_filter_label_by_tier.schema missing "
        "threshold_version"
    )

    # --- Sort order: threshold_version appears between filter_version and
    # filter_label in both schemas (per §5.2 amendment)
    fv_idx = overall_schema.index("filter_version")
    tv_idx = overall_schema.index("threshold_version")
    fl_idx = overall_schema.index("filter_label")
    assert fv_idx < tv_idx < fl_idx, (
        f"overall schema column order violates §5.2: "
        f"filter_version@{fv_idx}, threshold_version@{tv_idx}, filter_label@{fl_idx}"
    )


# ---------------------------------------------------------------------------
# Remediation m-3 -- run() must not invoke subprocess; git capture is CLI-only
# ---------------------------------------------------------------------------


def test_remediation_run_does_not_shell_out_to_git(tmp_path: Path) -> None:
    """The orchestrator must be subprocess-free.

    Three assertions:
      1. subprocess.run is never called during a pipeline run.
      2. git_commit / git_dirty values passed via RunParams flow through
         to manifest.git_commit / manifest.git_dirty.
      3. Passing None for both leaves both manifest fields as None.
    """

    import unittest.mock

    fixture = build_smoke_fixture(tmp_path / "m3.db")

    # --- Case A: RunParams carries explicit fingerprint values
    with unittest.mock.patch(
        "subprocess.run",
        side_effect=AssertionError(
            "run() invoked subprocess.run -- spec §6.2 purity violation"
        ),
    ) as mock_run:
        connection = open_readonly_connection(fixture)
        try:
            readers = _make_readers(connection)
            params = RunParams(
                output_root=tmp_path / "out_a",
                run_id="20260101T000000Z_m3a___",
                created_at=FIXED_CREATED_AT,
                as_of_time=FIXED_AS_OF,
                git_commit="abcdef1234567890",
                git_dirty=False,
            )
            result_a = run(readers, params)
        finally:
            connection.close()
        assert mock_run.call_count == 0, (
            f"subprocess.run called {mock_run.call_count} time(s) during run()"
        )

    assert result_a.manifest["git_commit"] == "abcdef1234567890"
    assert result_a.manifest["git_dirty"] is False

    # --- Case B: RunParams carries None for both fingerprint values
    with unittest.mock.patch(
        "subprocess.run",
        side_effect=AssertionError(
            "run() invoked subprocess.run -- spec §6.2 purity violation"
        ),
    ):
        connection = open_readonly_connection(fixture)
        try:
            readers = _make_readers(connection)
            params = RunParams(
                output_root=tmp_path / "out_b",
                run_id="20260101T000000Z_m3b___",
                created_at=FIXED_CREATED_AT,
                as_of_time=FIXED_AS_OF,
                git_commit=None,
                git_dirty=None,
            )
            result_b = run(readers, params)
        finally:
            connection.close()

    assert result_b.manifest["git_commit"] is None
    assert result_b.manifest["git_dirty"] is None


def test_remediation_orchestrator_does_not_import_subprocess() -> None:
    """The orchestrator's source must contain no live subprocess invocation.

    Docstring/comment references documenting the m-3 boundary are
    acceptable. ``import subprocess`` and ``subprocess.run`` calls are
    not.
    """

    src_path = (
        Path(PHX2.__file__).parent / "analysis" / "decision_outcome_analysis.py"
    )
    source = src_path.read_text(encoding="utf-8")

    # Strip comment lines + docstrings (cheap heuristic that suffices
    # here: every reference to subprocess in this module is inside a
    # comment beginning with "#" or inside a triple-quoted docstring;
    # if a live call appeared, this heuristic would still see it).
    code_lines = [
        line
        for line in source.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)

    # The pattern "subprocess.run(" or "import subprocess" must appear
    # zero times in code; if they appear elsewhere (e.g. comments) the
    # strip above removes them.
    assert "subprocess.run(" not in code, (
        "live subprocess.run( in decision_outcome_analysis.py"
    )
    # `import subprocess` at module top level — none expected.
    for line in code.splitlines():
        stripped = line.strip()
        assert stripped != "import subprocess", (
            f"live 'import subprocess' at line: {line!r}"
        )
        assert not stripped.startswith("from subprocess import"), (
            f"live 'from subprocess import ...' at line: {line!r}"
        )
