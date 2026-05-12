"""Stage 13 command-line entrypoint.

Invocation:

  python -m PHX2.stage13.cli --stage12-run <path> [--output-root <path>]

The CLI is a thin wrapper. It:

  1. Parses arguments.
  2. Captures the current git fingerprint via subprocess (best-effort,
     CLI-only side-effect; the orchestrator stays free of subprocess).
  3. Calls ``pipeline.run`` with wall-clock UTC time.
  4. Prints the run-directory path to stdout.

No core analysis logic lives here. The orchestrator handles all
classification, hashing, and artifact writing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PHX2.stage13.pipeline import run as run_pipeline


DEFAULT_OUTPUT_ROOT = Path("PHX2/stage13_runs")


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
    """Build the Stage 13 CLI argparse parser.

    Exposes two flags:

      * ``--stage12-run`` (required): path to an existing Stage 12 run
        directory whose manifest + four cohort CSVs Stage 13 will read.
      * ``--output-root`` (optional): root under which the dated Stage 13
        run directory is created. Default: ``PHX2/stage13_runs/``.

    The parser is split out from ``main`` so tests can construct it
    without invoking the rest of the CLI.
    """

    parser = argparse.ArgumentParser(
        prog="PHX2.stage13.cli",
        description=(
            "Stage 13 policy_recommendation_builder runner. Reads a "
            "Stage 12 run directory's CSV outputs + manifest, "
            "classifies cohorts under the locked evidence/action gates, "
            "and writes a Stage 13 run directory of policy-review "
            "artifacts. Stage 13 opens no DB connection."
        ),
    )
    parser.add_argument(
        "--stage12-run",
        required=True,
        type=Path,
        help="Path to a Stage 12 run directory (must contain manifest.json "
             "plus the four cohort CSVs).",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=(
            "Stage 13 output root. Each run lands at "
            "<output-root>/<UTC_timestamp>/. Default: PHX2/stage13_runs/"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Stage 13 CLI entry point.

    Parses ``argv`` (or ``sys.argv[1:]`` when None), captures the
    current git commit via subprocess (CLI-level I/O; the pipeline
    orchestrator stays subprocess-free), invokes
    ``PHX2.stage13.pipeline.run`` with wall-clock UTC, and prints the
    produced Stage 13 run-directory path on stdout.

    Returns:
      0 on success, 2 if ``--stage12-run`` does not exist.
    """

    args = make_parser().parse_args(argv)

    stage12_run: Path = args.stage12_run
    if not stage12_run.exists():
        print(
            f"error: --stage12-run path does not exist: {stage12_run}",
            file=sys.stderr,
        )
        return 2

    git_commit = _capture_git_commit()
    now_utc = datetime.now(timezone.utc)

    result = run_pipeline(
        stage12_run_path=stage12_run,
        output_root=args.output_root,
        now_utc=now_utc,
        git_commit=git_commit,
    )

    print(str(result.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
