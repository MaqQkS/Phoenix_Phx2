"""Stage 14 command-line entrypoint.

Invocation:

  python -m PHX2.stage14.cli --stage13-run <path> \\
      [--stage12-run <path>] [--output-root <path>]

The CLI is a thin wrapper. It:

  1. Parses arguments.
  2. Captures the current git fingerprint via subprocess (best-effort,
     CLI-only side-effect; the orchestrator stays free of subprocess).
  3. Calls ``pipeline.run`` with wall-clock UTC time.
  4. Prints the run-directory path to stdout.

Exit codes:
  0 -- success
  2 -- required path does not exist
  3 -- loader / translator invariant violation (validation error)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PHX2.stage14.loader import (
    Stage14IncompatibleStage12,
    Stage14IncompatibleStage13,
    Stage14MissingColumn,
    Stage14MissingInput,
    Stage14ValidationError,
)
from PHX2.stage14.pipeline import run as run_pipeline


DEFAULT_OUTPUT_ROOT = Path("PHX2/stage14_runs")


def _capture_git_commit() -> str | None:
    """Capture the current git HEAD SHA. Returns None on any failure."""

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    sha = proc.stdout.strip()
    return sha or None


def make_parser() -> argparse.ArgumentParser:
    """Build the Stage 14 CLI argparse parser.

    Three flags:
      * ``--stage13-run`` (required): path to a Stage 13 run directory
        whose candidate_recommendations.csv + manifest.json Stage 14
        consumes.
      * ``--stage12-run`` (optional): override for the Stage 12 path.
        Defaults to Stage 13's recorded ``stage12_run_path``. When
        provided, the override's manifest hash must match Stage 13's
        recorded ``stage12_manifest_hash``.
      * ``--output-root`` (optional): root under which the dated Stage
        14 run directory is created. Default: ``PHX2/stage14_runs/``.
    """

    parser = argparse.ArgumentParser(
        prog="PHX2.stage14.cli",
        description=(
            "Stage 14 offline historical shadow-policy replay runner. "
            "Reads a Stage 13 run directory's candidate CSV + manifest "
            "and a Stage 12 run directory's decision_filter_outcome_long "
            "CSV + manifest. Produces a Stage 14 run directory of "
            "replay diagnostics. Opens no DB connection; makes no "
            "network call; mutates no Stage 12 / Stage 13 artifacts."
        ),
    )
    parser.add_argument(
        "--stage13-run",
        required=True,
        type=Path,
        help=(
            "Path to a Stage 13 run directory. Must contain "
            "manifest.json and candidate_recommendations.csv."
        ),
    )
    parser.add_argument(
        "--stage12-run",
        type=Path,
        default=None,
        help=(
            "Optional override for the Stage 12 run path. Defaults to "
            "the path recorded in Stage 13's manifest. When provided, "
            "the override's manifest hash must match Stage 13's "
            "recorded stage12_manifest_hash."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=(
            "Stage 14 output root. Each run lands at "
            "<output-root>/<UTC_timestamp>/. Default: PHX2/stage14_runs/"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Stage 14 CLI entry point.

    Parses ``argv`` (or ``sys.argv[1:]`` when None), captures the
    current git commit via subprocess (CLI-level I/O; the pipeline
    orchestrator stays subprocess-free), invokes
    ``PHX2.stage14.pipeline.run`` with wall-clock UTC, and prints the
    produced Stage 14 run-directory path on stdout.
    """

    args = make_parser().parse_args(argv)

    stage13_run: Path = args.stage13_run
    if not stage13_run.exists():
        print(
            f"error: --stage13-run path does not exist: {stage13_run}",
            file=sys.stderr,
        )
        return 2

    if args.stage12_run is not None and not args.stage12_run.exists():
        print(
            f"error: --stage12-run path does not exist: {args.stage12_run}",
            file=sys.stderr,
        )
        return 2

    git_commit = _capture_git_commit()
    now_utc = datetime.now(timezone.utc)

    try:
        result = run_pipeline(
            stage13_run_path=stage13_run,
            output_root=args.output_root,
            stage12_run_path=args.stage12_run,
            now_utc=now_utc,
            git_commit=git_commit,
        )
    except (
        Stage14MissingInput,
        Stage14MissingColumn,
        Stage14IncompatibleStage13,
        Stage14IncompatibleStage12,
        Stage14ValidationError,
    ) as exc:
        print(f"error: Stage 14 validation failed: {exc}", file=sys.stderr)
        return 3

    print(str(result.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
