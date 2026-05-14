"""Stage 17 writer-layer tests.

Tests verify the locked column orders, NULL/REAL/BOOLEAN formatting,
atomic-write contract, and the README/log content requirements.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PHX2.stage17.models import (
    CoarseMetricRow,
    DataQualityRow,
    HeadlineMetricRow,
    RunReport,
    UnevaluableBreakdownRow,
)
from PHX2.stage17.writers import (
    COARSE_COLUMNS,
    DATA_QUALITY_COLUMNS,
    HEADLINE_COLUMNS,
    UNEVALUABLE_COLUMNS,
    make_log_event,
    write_coarse_summary_csv,
    write_data_quality_csv,
    write_headline_csv,
    write_log,
    write_readme,
    write_unevaluable_breakdown_csv,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal row instances
# ---------------------------------------------------------------------------


def _headline(
    *,
    policy_hash: str = "ph_a",
    rule_id: str = "r1",
    tier: str | None = "tier_a",
    ws: int = 300,
    label: str = "WEAK",
    null_rates: bool = False,
) -> HeadlineMetricRow:
    fill: dict[str, float | None] = {
        "max_return_multiple_p25_matched": None if null_rates else 1.234567,
        "max_return_multiple_p50_matched": None if null_rates else 2.0,
        "max_return_multiple_p75_matched": None if null_rates else 3.0,
        "max_return_multiple_p25_not_matched": None if null_rates else 1.0,
        "max_return_multiple_p50_not_matched": None if null_rates else 2.0,
        "max_return_multiple_p75_not_matched": None if null_rates else 3.0,
        "max_drawdown_from_peak_pct_p25_matched": None if null_rates else -10.0,
        "max_drawdown_from_peak_pct_p50_matched": None if null_rates else -5.0,
        "max_drawdown_from_peak_pct_p75_matched": None if null_rates else -1.0,
        "max_drawdown_from_peak_pct_p25_not_matched": None if null_rates else -10.0,
        "max_drawdown_from_peak_pct_p50_not_matched": None if null_rates else -5.0,
        "max_drawdown_from_peak_pct_p75_not_matched": None if null_rates else -1.0,
        "time_to_max_return_seconds_p50_matched": None if null_rates else 60.0,
        "time_to_max_return_seconds_p50_not_matched": None if null_rates else 60.0,
        "hit_2x_rate_matched": None if null_rates else 0.5,
        "hit_2x_rate_not_matched": None if null_rates else 0.4,
        "hit_3x_rate_matched": None if null_rates else 0.2,
        "hit_3x_rate_not_matched": None if null_rates else 0.1,
        "hit_5x_rate_matched": None if null_rates else 0.0,
        "hit_5x_rate_not_matched": None if null_rates else 0.0,
        "delta_hit_2x_rate": None if null_rates else 0.1,
        "delta_hit_3x_rate": None if null_rates else 0.1,
        "delta_hit_5x_rate": None if null_rates else 0.0,
        "delta_max_return_multiple_p50": None if null_rates else 0.0,
        "delta_max_drawdown_from_peak_pct_p50": None if null_rates else 0.0,
    }
    return HeadlineMetricRow(
        policy_hash=policy_hash,
        rule_id=rule_id,
        tier_name_snapshot=tier,
        window_seconds=ws,
        window_label="5m",
        n_in_scope=10,
        n_matched=5,
        n_not_matched=5,
        n_unevaluable=0,
        n_with_outcome=10,
        n_with_complete_outcome=10,
        n_outcome_present_but_incomplete=0,
        n_matched_with_complete_outcome=5,
        n_not_matched_with_complete_outcome=5,
        min_n_active=5,
        meets_min_n_matched=not null_rates,
        meets_min_n_not_matched=not null_rates,
        descriptive_label=label,
        **fill,
    )


# ---------------------------------------------------------------------------
# Header / column order
# ---------------------------------------------------------------------------


def test_headline_csv_header_matches_locked_column_order(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    write_headline_csv([], path)
    header_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert header_line.split(",") == list(HEADLINE_COLUMNS)


def test_coarse_csv_header_matches_locked_column_order(tmp_path: Path) -> None:
    path = tmp_path / "c.csv"
    write_coarse_summary_csv([], path)
    header_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert header_line.split(",") == list(COARSE_COLUMNS)


def test_unevaluable_csv_header_matches_locked_column_order(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    write_unevaluable_breakdown_csv([], path)
    header_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert header_line.split(",") == list(UNEVALUABLE_COLUMNS)


def test_data_quality_csv_header_matches_locked_column_order(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    write_data_quality_csv([], path)
    header_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert header_line.split(",") == list(DATA_QUALITY_COLUMNS)


def test_headline_csv_dataclass_field_order_matches_column_order() -> None:
    """The dataclass field order must match the locked CSV column order.

    Tests rely on this so they can build rows positionally.
    """

    import dataclasses

    field_names = tuple(f.name for f in dataclasses.fields(HeadlineMetricRow))
    assert field_names == HEADLINE_COLUMNS


# ---------------------------------------------------------------------------
# REAL field formatting (6 decimals or empty)
# ---------------------------------------------------------------------------


def test_real_field_formatting_uses_six_decimals(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    write_headline_csv([_headline()], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # header + 1 row
    row = lines[1].split(",")
    # max_return_multiple_p25_matched is at index 17 in HEADLINE_COLUMNS.
    idx = HEADLINE_COLUMNS.index("max_return_multiple_p25_matched")
    assert row[idx] == "1.234567"


def test_real_field_null_renders_as_empty_string(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    write_headline_csv([_headline(null_rates=True)], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    row = lines[1].split(",")
    idx = HEADLINE_COLUMNS.index("hit_2x_rate_matched")
    assert row[idx] == ""


def test_boolean_field_renders_as_one_or_zero(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    write_headline_csv([_headline()], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    row = lines[1].split(",")
    idx_m = HEADLINE_COLUMNS.index("meets_min_n_matched")
    idx_n = HEADLINE_COLUMNS.index("meets_min_n_not_matched")
    assert row[idx_m] == "1"
    assert row[idx_n] == "1"


def test_text_field_null_renders_as_empty_string(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    write_headline_csv([_headline(tier=None)], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    row = lines[1].split(",")
    idx = HEADLINE_COLUMNS.index("tier_name_snapshot")
    assert row[idx] == ""


# ---------------------------------------------------------------------------
# Atomic-write contract
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_file(tmp_path: Path) -> None:
    path = tmp_path / "h.csv"
    write_headline_csv([_headline()], path)
    siblings = list(tmp_path.iterdir())
    tmp_files = [p for p in siblings if p.name.endswith(".tmp")]
    assert tmp_files == []


# ---------------------------------------------------------------------------
# Data quality writer: scope_level ordering
# ---------------------------------------------------------------------------


def test_data_quality_writes_global_before_slice(tmp_path: Path) -> None:
    rows = [
        DataQualityRow("global", None, None, None, "orphan_evaluations", 0),
        DataQualityRow("global", None, None, None, "orphan_outcomes", 0),
        DataQualityRow("slice", "ph_a", "r1", 300, "n_outcome_present_but_incomplete", 2),
    ]
    path = tmp_path / "d.csv"
    write_data_quality_csv(rows, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    body = lines[1:]
    scope_levels = [line.split(",")[0] for line in body]
    assert scope_levels == ["global", "global", "slice"]


# ---------------------------------------------------------------------------
# README content checks
# ---------------------------------------------------------------------------


def _sample_run_report() -> RunReport:
    return RunReport(
        schema_version="stage17_run_manifest_v0",
        run_id="abcdef0123456789",
        run_started_utc="2026-05-13T12:00:00+00:00",
        run_finished_utc="2026-05-13T12:00:05+00:00",
        db_path="/tmp/phx2.db",
        output_dir="/tmp/out",
        min_n_active=5,
        policy_hashes_analyzed=("ph_a", "ph_b"),
        git_commit="c0ffee",
        source_table_row_counts={
            "observe_only_policy_evaluations": 10,
            "alert_decisions": 50,
            "alert_decisions_would_alert": 25,
            "outcome_windows": 30,
            "outcome_windows_complete": 20,
        },
        output_row_counts={
            "headline_metrics.csv": 4,
            "coarse_summary.csv": 2,
            "unevaluable_breakdown.csv": 1,
            "data_quality_report.csv": 5,
        },
        schema_migrations_seen=("stage_4", "stage_16b"),
        orphan_counts={"orphan_evaluations": 0, "orphan_outcomes": 0},
    )


def test_readme_contains_required_sections(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    write_readme(_sample_run_report(), path)
    body = path.read_text(encoding="utf-8")
    assert "Maturity model" in body
    assert "MIN_N behavior" in body
    assert "Matched vs. not_matched" in body
    assert "Artifacts in this directory" in body
    assert "NULL semantics below MIN_N" in body


def test_readme_lists_four_csv_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    write_readme(_sample_run_report(), path)
    body = path.read_text(encoding="utf-8")
    for csv_name in (
        "headline_metrics.csv",
        "coarse_summary.csv",
        "unevaluable_breakdown.csv",
        "data_quality_report.csv",
    ):
        assert csv_name in body


def test_readme_pins_min_n_and_run_id(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    write_readme(_sample_run_report(), path)
    body = path.read_text(encoding="utf-8")
    assert "abcdef0123456789" in body
    assert "min_n_active" in body
    assert "5" in body


# ---------------------------------------------------------------------------
# Log writer
# ---------------------------------------------------------------------------


def test_log_writer_produces_deterministic_lines(tmp_path: Path) -> None:
    events = [
        make_log_event("parse_args", status="ok"),
        make_log_event("open_db_readonly", status="ok"),
        make_log_event("fetch_evaluation_rows", policy_hash_index=0, rows=42),
        make_log_event("write_headline_csv", rows=15),
        make_log_event("run_complete"),
    ]
    path = tmp_path / "stage17_run.log"
    write_log(events, path)
    body = path.read_text(encoding="utf-8")
    expected = (
        "step=parse_args status=ok\n"
        "step=open_db_readonly status=ok\n"
        "step=fetch_evaluation_rows policy_hash_index=0 rows=42\n"
        "step=write_headline_csv rows=15\n"
        "step=run_complete\n"
    )
    assert body == expected


def test_log_writer_emits_only_step_lines(tmp_path: Path) -> None:
    events = [make_log_event("parse_args", status="ok")]
    path = tmp_path / "stage17_run.log"
    write_log(events, path)
    body = path.read_text(encoding="utf-8")
    # No timestamp, no absolute path, no temp dir markers.
    assert body.startswith("step=")
    forbidden_substrings = (
        "20T",  # ISO datetime fragments leak this when wall-clock leaks.
        "Z\n",
        "/tmp/",
        "C:\\",
        "TempDir",
        "tmp_path",
    )
    for s in forbidden_substrings:
        assert s not in body, f"log body leaked {s!r}: {body!r}"


def test_log_writer_is_byte_identical_across_calls(tmp_path: Path) -> None:
    events = [
        make_log_event("parse_args", status="ok"),
        make_log_event("run_complete"),
    ]
    p1 = tmp_path / "a.log"
    p2 = tmp_path / "b.log"
    write_log(events, p1)
    write_log(events, p2)
    assert p1.read_bytes() == p2.read_bytes()


# ---------------------------------------------------------------------------
# Coarse / unevaluable smoke
# ---------------------------------------------------------------------------


def test_coarse_csv_writes_row_count(tmp_path: Path) -> None:
    rows: Iterable[CoarseMetricRow] = [
        CoarseMetricRow(
            policy_hash="ph_a",
            rule_id="r1",
            window_seconds=300,
            window_label="5m",
            n_in_scope=10,
            n_matched=5,
            n_not_matched=5,
            n_with_complete_outcome=10,
            hit_2x_rate_matched=0.5,
            hit_2x_rate_not_matched=0.4,
            delta_hit_2x_rate=0.1,
            descriptive_label="WEAK",
        ),
    ]
    path = tmp_path / "c.csv"
    n = write_coarse_summary_csv(rows, path)
    assert n == 1


def test_unevaluable_csv_writes_row_count(tmp_path: Path) -> None:
    rows = [
        UnevaluableBreakdownRow("ph_a", "r1", "missing_input", 3),
        UnevaluableBreakdownRow("ph_b", "r2", "bad_thresholds", 1),
    ]
    path = tmp_path / "u.csv"
    n = write_unevaluable_breakdown_csv(rows, path)
    assert n == 2
