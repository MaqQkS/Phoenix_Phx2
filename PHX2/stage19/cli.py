"""Stage 19 CLI orchestration.

Argparse-based entrypoint that wires together readers,
validators, ledger primitives, manifest assembly, and writers
into one Stage 19 run.

Output directory is created only after every read, validation,
and in-memory build step succeeds. If a write fails after the
output directory is created, ``shutil.rmtree(ignore_errors=True)``
removes the partial directory before the CLI returns.

Exit codes:
  * 0  -- success
  * 10 -- Stage19ValidationError (E01..E21)
  * 20 -- IO failure during writes
  * 99 -- unexpected internal error
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PHX2.stage19._git import get_git_commit
from PHX2.stage19.constants import (
    LABELS,
    LEDGER_FILENAME,
    MANIFEST_FILENAME,
    README_FILENAME,
    RUN_LOG_FILENAME,
    STAGE19_SCHEMA_VERSION,
    SUMMARY_FILENAME,
)
from PHX2.stage19.errors import Stage19ValidationError
from PHX2.stage19.ledger import (
    build_ledger_rows,
    compute_summary,
    merge_ledger,
)
from PHX2.stage19.manifest import (
    build_manifest,
    compute_file_sha256,
    compute_stage19_run_id,
    write_manifest_json,
)
from PHX2.stage19.readers import (
    read_operator_input,
    read_prior_ledger,
    read_stage18_manifest,
    read_stage18_review_matrix,
)
from PHX2.stage19.validators import (
    validate_against_review_matrix,
    validate_no_duplicates,
    validate_operator_id,
    validate_output_dir,
    validate_run_timestamp,
)
from PHX2.stage19.writers import (
    write_ledger_csv,
    write_readme_md,
    write_run_log,
    write_summary_csv,
)


_EXIT_OK: int = 0
_EXIT_VALIDATION: int = 10
_EXIT_IO: int = 20
_EXIT_INTERNAL: int = 99


_STAGE18_MANIFEST_FILENAME: str = "manifest.json"
_STAGE18_REVIEW_MATRIX_FILENAME: str = "review_matrix.csv"


def build_parser() -> argparse.ArgumentParser:
    """Build the Stage 19 argparse parser."""

    parser = argparse.ArgumentParser(
        prog="stage19",
        description=(
            "Stage 19: build the operator review ledger from a "
            "Stage 18 review packet plus an operator-supplied input "
            "CSV."
        ),
    )
    parser.add_argument(
        "--stage18-dir",
        type=Path,
        required=True,
        help="Path to the Stage 18 output directory (read-only).",
    )
    parser.add_argument(
        "--operator-input",
        type=Path,
        required=True,
        help="Path to the operator_review_input.csv file (read-only).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help=(
            "Directory to populate with this run's outputs. May be "
            "non-existent or existing-empty; never modified in-place "
            "if validation fails."
        ),
    )
    parser.add_argument(
        "--operator-id",
        type=str,
        required=True,
        help="The reviewing operator's id (single CLI scalar per run).",
    )
    parser.add_argument(
        "--prior-ledger-dir",
        type=Path,
        default=None,
        help=(
            "Optional: a prior Stage 19 output directory whose ledger "
            "rows should be preserved and extended."
        ),
    )
    parser.add_argument(
        "--run-timestamp",
        type=str,
        default=None,
        help=(
            "Optional ISO8601 Z timestamp (YYYY-MM-DDTHH:MM:SSZ) to use "
            "as run_timestamp_utc; defaults to wall-clock UTC at run "
            "start."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the stdout summary line on success.",
    )
    return parser


def _format_summary_line(
    stage19_run_id: str,
    new_count: int,
    total_count: int,
    label_counts: dict[str, int],
) -> str:
    """Render the one-line stdout summary in the locked format."""

    label_parts = [f"{label}:{label_counts.get(label, 0)}" for label in LABELS]
    return (
        f"stage19 run_id={stage19_run_id} "
        f"new_rows={new_count} total_rows={total_count} "
        f"labels=" + ",".join(label_parts)
    )


def _build_log_entries(
    manifest: dict, label_counts: dict[str, int]
) -> list[str]:
    """Render deterministic stage19_run.log entries from the manifest.

    Order is fixed; no per-entry wall-clock stamps. The run-level
    timestamp lives in manifest.run_timestamp_utc.
    """

    entries: list[str] = []
    entries.append(f"stage19_run_id={manifest['stage19_run_id']}")
    entries.append(f"run_timestamp_utc={manifest['run_timestamp_utc']}")
    entries.append(f"operator_id={manifest['operator_id']}")
    entries.append(f"stage18_input_dir={manifest['stage18_input_dir']}")
    entries.append(f"stage18_run_id={manifest['stage18_run_id']}")
    entries.append(
        f"stage18_manifest_sha256={manifest['stage18_manifest_sha256']}"
    )
    entries.append(
        f"stage18_review_matrix_sha256="
        f"{manifest['stage18_review_matrix_sha256']}"
    )
    entries.append(f"operator_input_path={manifest['operator_input_path']}")
    entries.append(
        f"operator_input_sha256={manifest['operator_input_sha256']}"
    )
    if manifest["prior_ledger_dir"] is not None:
        entries.append(f"prior_ledger_dir={manifest['prior_ledger_dir']}")
        entries.append(
            f"prior_ledger_sha256={manifest['prior_ledger_sha256']}"
        )
        entries.append(
            f"prior_ledger_schema_version="
            f"{manifest['prior_ledger_schema_version']}"
        )
    else:
        entries.append("prior_ledger_dir=none")
    entries.append(f"new_row_count={manifest['new_row_count']}")
    entries.append(f"prior_row_count={manifest['prior_row_count']}")
    entries.append(
        f"total_ledger_row_count={manifest['total_ledger_row_count']}"
    )
    label_parts = [
        f"{label}={label_counts.get(label, 0)}" for label in LABELS
    ]
    entries.append("label_counts=" + ",".join(label_parts))
    entries.append(f"git_commit={manifest['git_commit']}")
    return entries


def main(argv: list[str] | None = None) -> int:
    """Entry point for the Stage 19 CLI.

    Returns the exit code; does not call ``sys.exit`` so callers
    (including the script shim added in Phase 19.4a and pytest)
    can drive it programmatically.
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir_created = False
    try:
        operator_id = validate_operator_id(args.operator_id)

        if args.run_timestamp is not None:
            run_timestamp_utc = validate_run_timestamp(args.run_timestamp)
        else:
            run_timestamp_utc = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        validate_output_dir(args.output_dir)

        stage18_manifest = read_stage18_manifest(args.stage18_dir)
        review_matrix_index = read_stage18_review_matrix(args.stage18_dir)
        stage18_run_id = stage18_manifest.run_id

        stage18_manifest_sha256 = compute_file_sha256(
            args.stage18_dir / _STAGE18_MANIFEST_FILENAME
        )
        stage18_review_matrix_sha256 = compute_file_sha256(
            args.stage18_dir / _STAGE18_REVIEW_MATRIX_FILENAME
        )

        input_rows = read_operator_input(args.operator_input)
        operator_input_sha256 = compute_file_sha256(args.operator_input)

        validate_against_review_matrix(
            input_rows, review_matrix_index, stage18_run_id
        )
        validate_no_duplicates(input_rows, operator_id)

        if args.prior_ledger_dir is not None:
            prior_ledger_rows, prior_manifest_dict = read_prior_ledger(
                args.prior_ledger_dir
            )
            prior_ledger_sha256 = compute_file_sha256(
                args.prior_ledger_dir / LEDGER_FILENAME
            )
            prior_ledger_schema_version = prior_manifest_dict.get(
                "stage19_schema_version"
            )
        else:
            prior_ledger_rows = []
            prior_ledger_sha256 = None
            prior_ledger_schema_version = None

        stage18_input_basename = Path(args.stage18_dir).name
        stage19_run_id = compute_stage19_run_id(
            stage18_run_id=stage18_run_id,
            stage18_input_basename=stage18_input_basename,
            operator_id=operator_id,
            operator_input_sha256=operator_input_sha256,
            prior_ledger_sha256=prior_ledger_sha256,
            run_timestamp_utc=run_timestamp_utc,
            stage19_schema_version=STAGE19_SCHEMA_VERSION,
        )

        new_rows = build_ledger_rows(
            operator_input=input_rows,
            prior_ledger_rows=prior_ledger_rows,
            stage19_run_id=stage19_run_id,
            operator_id=operator_id,
            review_timestamp_utc=run_timestamp_utc,
            review_matrix_index=review_matrix_index,
        )
        full_ledger = merge_ledger(prior_ledger_rows, new_rows)
        summary_rows = compute_summary(full_ledger)

        label_counts: dict[str, int] = {label: 0 for label in LABELS}
        for r in new_rows:
            label_counts[r.review_label] = (
                label_counts.get(r.review_label, 0) + 1
            )

        git_commit = get_git_commit()
        manifest = build_manifest(
            stage19_run_id=stage19_run_id,
            run_timestamp_utc=run_timestamp_utc,
            operator_id=operator_id,
            stage18_input_dir=args.stage18_dir,
            stage18_run_id=stage18_run_id,
            stage18_manifest_sha256=stage18_manifest_sha256,
            stage18_review_matrix_sha256=stage18_review_matrix_sha256,
            operator_input_path=args.operator_input,
            operator_input_sha256=operator_input_sha256,
            prior_ledger_dir=args.prior_ledger_dir,
            prior_ledger_sha256=prior_ledger_sha256,
            prior_ledger_schema_version=prior_ledger_schema_version,
            new_row_count=len(new_rows),
            prior_row_count=len(prior_ledger_rows),
            total_ledger_row_count=len(full_ledger),
            label_counts=label_counts,
            git_commit=git_commit,
        )

        # Step 18: create the output directory (only after every
        # read, validation, hash, and in-memory build succeeded).
        # validate_output_dir accepted either non-existent (with
        # an existing parent directory) or existing-empty. Use
        # os.mkdir (not os.makedirs) so the parent-must-exist
        # invariant validated above is enforced at creation time
        # too -- no intermediate parents will be silently created.
        if not args.output_dir.exists():
            os.mkdir(args.output_dir)
        output_dir_created = True

        log_entries = _build_log_entries(manifest, label_counts)

        write_ledger_csv(args.output_dir / LEDGER_FILENAME, full_ledger)
        write_summary_csv(args.output_dir / SUMMARY_FILENAME, summary_rows)
        write_manifest_json(args.output_dir / MANIFEST_FILENAME, manifest)
        write_readme_md(args.output_dir / README_FILENAME, manifest)
        write_run_log(args.output_dir / RUN_LOG_FILENAME, log_entries)

        if not args.quiet:
            print(_format_summary_line(
                stage19_run_id, len(new_rows), len(full_ledger), label_counts
            ))

        return _EXIT_OK

    except Stage19ValidationError as exc:
        print(f"[stage19] ERROR {exc}", file=sys.stderr)
        if output_dir_created:
            shutil.rmtree(args.output_dir, ignore_errors=True)
        return _EXIT_VALIDATION
    except OSError as exc:
        print(
            f"[stage19] IO ERROR {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        if output_dir_created:
            shutil.rmtree(args.output_dir, ignore_errors=True)
        return _EXIT_IO
    except Exception:
        traceback.print_exc(file=sys.stderr)
        if output_dir_created:
            shutil.rmtree(args.output_dir, ignore_errors=True)
        return _EXIT_INTERNAL


__all__ = ["build_parser", "main"]
