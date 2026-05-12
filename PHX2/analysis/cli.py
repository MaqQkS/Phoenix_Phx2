"""Stage 12 command-line entrypoint.

Invocation:

  python -m PHX2.analysis.cli --db <path> [options]

The CLI is a thin wrapper. It:

  1. Parses arguments.
  2. Opens the PHX2 SQLite DB read-only via sqlite3 URI mode=ro.
     This is L2 operational enforcement -- any rogue write attempt
     fails at the driver layer.
  3. Constructs the SubstrateReaders bundle.
  4. Constructs RunParams.
  5. Calls run(readers, params) to obtain a RunResult.
  6. Creates the immutable per-run directory and writes the seven
     output files via writers.py.
  7. Prints the run-directory path to stdout.

NO core analysis logic lives in this module -- arg parsing and I/O
wiring only. All cohort math, joins, sort, manifest assembly happen
inside ``decision_outcome_analysis.run``.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PHX2.analysis.decision_outcome_analysis import (
    COHORT_FILTER_LABEL_BY_TIER_FILENAME,
    COHORT_FILTER_LABEL_OVERALL_FILENAME,
    COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
    COHORT_TIER_BASELINE_FILENAME,
    LONG_CSV_FILENAME,
    RunParams,
    RunResult,
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


DEFAULT_OUTPUT_DIR = Path("PHX2/analysis/output")
MANIFEST_FILENAME = "manifest.json"
README_FILENAME = "README.md"


def _parse_iso8601(value: str) -> datetime:
    """argparse type-coercer for ISO 8601 timestamps.

    Accepts the trailing ``Z`` UTC marker (``2026-01-15T12:00:00Z``)
    as well as offsets (``2026-01-15T12:00:00+00:00``). Naive
    timestamps are coerced to UTC.
    """

    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"not a valid ISO 8601 timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="PHX2.analysis.cli",
        description=(
            "Stage 12 decision_outcome_analysis runner. Reads the PHX2 "
            "SQLite DB read-only and writes a fresh, immutable run "
            "directory of cohort summary CSVs + manifest.json + README.md."
        ),
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="Path to the PHX2 SQLite database (opened read-only).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Output root. Each run lands at "
            "<output-dir>/decision_outcome_analysis/<run_id>/. "
            "Default: PHX2/analysis/output/"
        ),
    )
    parser.add_argument(
        "--decision-time-range-start",
        type=_parse_iso8601,
        default=None,
        help=(
            "Inclusive lower bound on alert_decisions.evaluated_at "
            "(ISO 8601, e.g. 2026-01-15T00:00:00Z)."
        ),
    )
    parser.add_argument(
        "--decision-time-range-end",
        type=_parse_iso8601,
        default=None,
        help=(
            "Inclusive upper bound on alert_decisions.evaluated_at "
            "(ISO 8601)."
        ),
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help=(
            "Override the run_id. If omitted, auto-generated per §5.1 "
            "as YYYYMMDDTHHMMSSZ_<6-char-random-hex>."
        ),
    )
    parser.add_argument(
        "--as-of",
        type=_parse_iso8601,
        default=None,
        help=(
            "Override the as-of timestamp used for deterministic "
            "censoring replay (S0-1 fallback). Defaults to None; "
            "censoring is derived from outcome_windows.data_status."
        ),
    )
    return parser


def _capture_git_fingerprint() -> tuple[str | None, bool | None]:
    """Capture the current git commit + dirty flag via subprocess.

    Best-effort: returns ``(None, None)`` when git is unavailable, the
    cwd is not a repo, or the subprocess fails for any reason. This is
    the only environmental side-effect a Stage 12 invocation performs
    by design (m-3 remediation: orchestrator stays pure; CLI owns
    environmental I/O).
    """

    try:
        commit_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return (None, None)

    commit = commit_proc.stdout.strip() or None
    dirty = bool(status_proc.stdout.strip())
    return (commit, dirty)


def _open_readonly_connection(db_path: Path) -> sqlite3.Connection:
    """L2 operational enforcement: open the PHX2 DB via URI mode=ro.

    Any write attempt against this connection fails with
    ``sqlite3.OperationalError: attempt to write a readonly database``.
    """

    uri = f"file:{db_path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _write_outputs(result: RunResult, run_dir: Path) -> None:
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


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)

    db_path: Path = args.db
    if not db_path.exists():
        print(
            f"error: --db path does not exist: {db_path}",
            file=sys.stderr,
        )
        return 2

    output_dir: Path = args.output_dir

    # Capture git fingerprint at the CLI boundary (m-3 remediation:
    # subprocess is a CLI responsibility, never the orchestrator's).
    git_commit, git_dirty = _capture_git_fingerprint()

    connection = _open_readonly_connection(db_path)
    try:
        readers = SubstrateReaders(
            alert_decisions=AlertDecisionsReader(connection),
            filter_evaluations=FilterEvaluationsReader(connection),
            decision_score_features=DecisionScoreFeaturesReader(connection),
            outcome_windows=OutcomeWindowsReader(connection),
            token_identity=TokenIdentityReader(connection),
        )
        params = RunParams(
            output_root=output_dir,
            included_decision_statuses=("would_alert",),
            decision_time_range_start=args.decision_time_range_start,
            decision_time_range_end=args.decision_time_range_end,
            run_id=args.run_id,
            created_at=datetime.now(timezone.utc),
            as_of_time=args.as_of,
            git_commit=git_commit,
            git_dirty=git_dirty,
        )
        result = run(readers, params)
    finally:
        connection.close()

    run_dir = create_run_directory(output_dir, result.run_id)
    _write_outputs(result, run_dir)

    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
