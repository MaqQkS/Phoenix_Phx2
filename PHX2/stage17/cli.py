"""Stage 17 CLI entry: parses CLI args, runs the read-only analysis, prints a single summary line to stdout, and exits with the locked exit-code class (0/2/3/4/5)."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PHX2.stage17.errors import MESSAGE_TEMPLATES, Stage17Error
from PHX2.stage17.manifest import build_manifest, compute_run_id, write_manifest
from PHX2.stage17.metrics import (
    compute_coarse_summary,
    compute_data_quality,
    compute_headline_metrics,
    compute_unevaluable_breakdown,
)
from PHX2.stage17.models import RunReport
from PHX2.stage17.readers import (
    count_alert_decisions_in_scope,
    count_orphan_evaluations,
    count_orphan_outcomes,
    count_outcome_windows_complete,
    count_table,
    fetch_evaluation_rows,
    fetch_outcome_rows_for_decisions,
    list_distinct_policy_hashes,
    list_schema_migrations,
    open_db_readonly,
    verify_required_tables,
)
from PHX2.stage17.writers import (
    make_log_event,
    write_coarse_summary_csv,
    write_data_quality_csv,
    write_headline_csv,
    write_log,
    write_readme,
    write_unevaluable_breakdown_csv,
)


# Locked exit-code class (matches Stage 16B):
#   0  clean run (including empty DB).
#   2  CLI argument error (argparse defaults to this on missing/unknown).
#   3  DB connectivity / required table missing / read failure (A01..A03).
#   4  runtime error during analysis or output-dir collision (A04..A08).
#   5  unexpected programmer error not classified above (A10).
EXIT_OK = 0
EXIT_CLI_ARG_ERROR = 2
EXIT_LOAD_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_UNEXPECTED = 5


_DEFAULT_MIN_N = 5


_ARTIFACT_NAMES = (
    "headline_metrics.csv",
    "coarse_summary.csv",
    "unevaluable_breakdown.csv",
    "data_quality_report.csv",
    "manifest.json",
    "README.md",
    "stage17_run.log",
)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_stage17_analysis",
        description=(
            "Stage 17: read-only analysis sidecar. Joins "
            "observe_only_policy_evaluations (Stage 16B) to "
            "alert_decisions and outcome_windows (Stage 9) and emits "
            "deterministic CSV/Markdown reports answering whether "
            "approved observe-only would-block rules would have blocked "
            "alerts that were winners or losers."
        ),
    )
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="Path to the PHX2 SQLite database (opened read-only).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help=(
            "Fresh output directory. Stage 17 refuses to reuse, clean, or "
            "overwrite an existing directory; callers must provide a new "
            "path."
        ),
    )
    parser.add_argument(
        "--min-n",
        required=False,
        type=int,
        default=_DEFAULT_MIN_N,
        help=(
            f"MIN_N threshold for rate/percentile/delta gating "
            f"(default: {_DEFAULT_MIN_N})."
        ),
    )
    parser.add_argument(
        "--policy-hash",
        required=False,
        action="append",
        default=None,
        help=(
            "Restrict the analysis to one or more policy_hash values. "
            "May be passed multiple times. If omitted, every distinct "
            "policy_hash in observe_only_policy_evaluations is analyzed."
        ),
    )
    return parser


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _stdout(message: str) -> None:
    print(message)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_git_commit() -> str:
    """Capture HEAD via ``git rev-parse``; return 'unknown' on failure.

    Mirrors the Stage 16A pattern but downgrades the L22-equivalent
    failure to a non-fatal "unknown" record. Stage 17 reports are
    self-contained: a missing commit must not block report
    generation.
    """

    repo_root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return "unknown"
    sha = proc.stdout.strip()
    return sha if sha else "unknown"


def _format_summary(
    *,
    run_id: str,
    output_dir: Path,
    headline_rows: int,
    min_n: int,
    policy_hashes_count: int,
) -> str:
    """Single-line stdout summary on clean runs (locked format)."""

    return (
        f"stage17_run "
        f"run_id={run_id} "
        f"output_dir={output_dir} "
        f"headline_rows={headline_rows} "
        f"min_n={min_n} "
        f"policy_hashes={policy_hashes_count}"
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Stage 17 CLI entry point. Returns the exit code per the locked class."""

    args = make_parser().parse_args(argv)

    db_path: Path = args.db_path
    output_dir: Path = args.output_dir
    min_n: int = args.min_n
    policy_hash_filters: Optional[list[str]] = args.policy_hash

    if min_n < 0:
        _stderr(f"error: --min-n must be non-negative; got {min_n}")
        return EXIT_LOAD_ERROR

    if not db_path.is_file():
        _stderr(
            f"error: [A01] {MESSAGE_TEMPLATES['A01']}: "
            f"--db-path does not exist or is not a file: {db_path}"
        )
        return EXIT_LOAD_ERROR

    # ---- Provision output dir up front so log writes can land. --------
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        _stderr(
            f"error: [A04] {MESSAGE_TEMPLATES['A04']}: "
            f"output dir already exists: {output_dir}"
        )
        return EXIT_RUNTIME_ERROR
    except OSError as exc:
        _stderr(f"error: [A04] {MESSAGE_TEMPLATES['A04']}: {exc}")
        return EXIT_RUNTIME_ERROR

    log_path = output_dir / "stage17_run.log"
    log_events: list[str] = []

    def _log(step: str, **fields: object) -> None:
        log_events.append(make_log_event(step, **fields))

    _log("parse_args", status="ok")

    # ---- Open DB read-only and verify required tables. ----------------
    connection: Optional[sqlite3.Connection] = None
    try:
        try:
            connection = open_db_readonly(db_path)
            _log("open_db_readonly", status="ok")
            verify_required_tables(connection)
            _log("verify_required_tables", status="ok")
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            _log("verify_required_tables", status="error", code=exc.code)
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_LOAD_ERROR

        # ---- Resolve policy_hash list. -----------------------------------
        try:
            if policy_hash_filters:
                policy_hashes = tuple(sorted(set(policy_hash_filters)))
            else:
                policy_hashes = list_distinct_policy_hashes(connection)
            _log("list_distinct_policy_hashes", count=len(policy_hashes))
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            _log("list_distinct_policy_hashes", status="error", code=exc.code)
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_LOAD_ERROR

        # ---- Fetch evaluation + outcome rows for each policy_hash. -------
        run_started_utc = _utc_now_iso()
        all_evaluations = []
        all_outcomes = []
        try:
            for idx, ph in enumerate(policy_hashes):
                evals = fetch_evaluation_rows(connection, ph)
                _log(
                    "fetch_evaluation_rows",
                    policy_hash_index=idx,
                    rows=len(evals),
                )
                decision_ids = tuple({e.alert_decision_id for e in evals})
                outs = fetch_outcome_rows_for_decisions(connection, decision_ids)
                _log(
                    "fetch_outcome_rows_for_decisions",
                    policy_hash_index=idx,
                    rows=len(outs),
                )
                all_evaluations.extend(evals)
                all_outcomes.extend(outs)
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            _log("fetch_rows", status="error", code=exc.code)
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_LOAD_ERROR

        # ---- Orphan counts + manifest support reads (global). ------------
        try:
            orphan_eval = count_orphan_evaluations(connection)
            orphan_outcome = count_orphan_outcomes(connection)
            n_evaluations_total = count_table(
                connection, "observe_only_policy_evaluations"
            )
            n_alert_decisions_total = count_table(connection, "alert_decisions")
            n_alert_decisions_would_alert = count_alert_decisions_in_scope(
                connection
            )
            n_outcome_windows_total = count_table(connection, "outcome_windows")
            n_outcome_windows_complete = count_outcome_windows_complete(connection)
            schema_migrations = list_schema_migrations(connection)
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            _log("manifest_support_reads", status="error", code=exc.code)
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_LOAD_ERROR

        _log(
            "manifest_support_reads",
            orphan_eval=orphan_eval,
            orphan_outcome=orphan_outcome,
        )

        # ---- Compute metrics. --------------------------------------------
        try:
            headline_rows = compute_headline_metrics(
                all_evaluations, all_outcomes, min_n=min_n
            )
            coarse_rows = compute_coarse_summary(headline_rows)
            unevaluable_rows = compute_unevaluable_breakdown(all_evaluations)
            data_quality_rows = compute_data_quality(
                all_evaluations,
                all_outcomes,
                orphan_eval_count=orphan_eval,
                orphan_outcome_count=orphan_outcome,
            )
        except Exception as exc:  # noqa: BLE001 -- analysis boundary
            _stderr(f"error: stage17 metric computation failed: {exc}")
            _log("compute_metrics", status="error")
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_RUNTIME_ERROR

        _log("compute_headline_metrics", rows=len(headline_rows))
        _log("compute_coarse_summary", rows=len(coarse_rows))
        _log("compute_unevaluable_breakdown", rows=len(unevaluable_rows))
        _log("compute_data_quality", rows=len(data_quality_rows))

        # ---- Source-table row counts dict for manifest. ------------------
        source_row_counts = {
            "observe_only_policy_evaluations": n_evaluations_total,
            "alert_decisions": n_alert_decisions_total,
            "alert_decisions_would_alert": n_alert_decisions_would_alert,
            "outcome_windows": n_outcome_windows_total,
            "outcome_windows_complete": n_outcome_windows_complete,
        }

        # ---- Compute run id (deterministic from inputs). -----------------
        run_id = compute_run_id(
            db_basename=db_path.name,
            min_n=min_n,
            policy_hashes=policy_hashes,
            source_table_row_counts=source_row_counts,
        )
        _log("compute_run_id", run_id=run_id)

        # ---- Capture git commit (non-fatal). -----------------------------
        git_commit = _capture_git_commit()
        if git_commit == "unknown":
            _log("capture_git_commit", status="unknown")
        else:
            _log("capture_git_commit", status="ok")

        # ---- Write CSVs. --------------------------------------------------
        try:
            n_headline = write_headline_csv(
                headline_rows, output_dir / "headline_metrics.csv"
            )
            _log("write_headline_csv", rows=n_headline)
            n_coarse = write_coarse_summary_csv(
                coarse_rows, output_dir / "coarse_summary.csv"
            )
            _log("write_coarse_summary_csv", rows=n_coarse)
            n_unev = write_unevaluable_breakdown_csv(
                unevaluable_rows, output_dir / "unevaluable_breakdown.csv"
            )
            _log("write_unevaluable_breakdown_csv", rows=n_unev)
            n_dq = write_data_quality_csv(
                data_quality_rows, output_dir / "data_quality_report.csv"
            )
            _log("write_data_quality_csv", rows=n_dq)
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            _log("write_csv", status="error", code=exc.code)
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_RUNTIME_ERROR

        # ---- Compose RunReport, write manifest + README + log. -----------
        run_finished_utc = _utc_now_iso()
        report = RunReport(
            schema_version="stage17_run_manifest_v0",
            run_id=run_id,
            run_started_utc=run_started_utc,
            run_finished_utc=run_finished_utc,
            db_path=str(db_path.resolve()),
            output_dir=str(output_dir.resolve()),
            min_n_active=min_n,
            policy_hashes_analyzed=tuple(policy_hashes),
            git_commit=git_commit,
            source_table_row_counts=source_row_counts,
            output_row_counts={
                "headline_metrics.csv": n_headline,
                "coarse_summary.csv": n_coarse,
                "unevaluable_breakdown.csv": n_unev,
                "data_quality_report.csv": n_dq,
            },
            schema_migrations_seen=tuple(schema_migrations),
            orphan_counts={
                "orphan_evaluations": orphan_eval,
                "orphan_outcomes": orphan_outcome,
            },
        )

        manifest = build_manifest(
            run_id=report.run_id,
            run_started_utc=report.run_started_utc,
            run_finished_utc=report.run_finished_utc,
            db_path=report.db_path,
            output_dir=report.output_dir,
            min_n_active=report.min_n_active,
            policy_hashes_analyzed=report.policy_hashes_analyzed,
            git_commit=report.git_commit,
            source_table_row_counts=report.source_table_row_counts,
            output_row_counts=report.output_row_counts,
            schema_migrations_seen=report.schema_migrations_seen,
            orphan_counts=report.orphan_counts,
        )

        try:
            write_manifest(manifest, output_dir / "manifest.json")
            _log("write_manifest", status="ok")
            write_readme(report, output_dir / "README.md")
            _log("write_readme", status="ok")
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            _log("write_artifact", status="error", code=exc.code)
            try:
                write_log(log_events, log_path)
            except Stage17Error:
                pass
            return EXIT_RUNTIME_ERROR

        _log("run_complete")
        try:
            write_log(log_events, log_path)
        except Stage17Error as exc:
            _stderr(f"error: {exc}")
            return EXIT_RUNTIME_ERROR

        _stdout(
            _format_summary(
                run_id=run_id,
                output_dir=output_dir,
                headline_rows=len(headline_rows),
                min_n=min_n,
                policy_hashes_count=len(policy_hashes),
            )
        )
        return EXIT_OK

    except Stage17Error as exc:
        _stderr(f"error: {exc}")
        try:
            log_events.append(make_log_event("unhandled_stage17_error", code=exc.code))
            write_log(log_events, log_path)
        except Stage17Error:
            pass
        if exc.code in ("A01", "A02", "A03"):
            return EXIT_LOAD_ERROR
        if exc.code in ("A04", "A05", "A06", "A07", "A08"):
            return EXIT_RUNTIME_ERROR
        return EXIT_UNEXPECTED

    except Exception as exc:  # noqa: BLE001 -- outermost boundary
        _stderr(
            f"error: unexpected stage17 failure: "
            f"{type(exc).__name__}: {exc}"
        )
        traceback.print_exc(file=sys.stderr)
        try:
            log_events.append(make_log_event("unexpected", error_type=type(exc).__name__))
            write_log(log_events, log_path)
        except Stage17Error:
            pass
        return EXIT_UNEXPECTED

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 -- best-effort cleanup
                pass
