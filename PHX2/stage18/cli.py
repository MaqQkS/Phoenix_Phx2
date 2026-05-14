"""Stage 18 CLI entry: parses args, orchestrates the read-only
review build, writes the seven output artifacts, prints a single
summary line to stdout, and returns an exit code from the locked
class (0/2/3/4/5).

The CLI is the only Stage 18 module that owns orchestration glue
(slice-matching, per-row dispatch into ``classify_row``,
artifact-write ordering). Every operation inside is composed of
pure helpers from ``readers``, ``classifier``, ``metrics``,
``writers``, ``manifest``, and ``_git``.

Exit-code class:
  0  clean run.
  2  CLI argument error (argparse default).
  3  input contract violation (B01, B02, B03, B07, B08).
  4  output dir / write failure (B04, B05, B06).
  5  unexpected programmer error (B10 + unhandled exceptions).
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PHX2.stage18._git import get_git_commit
from PHX2.stage18.classifier import classify_row, validate_stage17_labels
from PHX2.stage18.constants import (
    REVIEW_LABEL_DATA_BLOCKED,
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_WEAK,
)
from PHX2.stage18.errors import MESSAGE_TEMPLATES, Stage18Error
from PHX2.stage18.manifest import build_manifest, compute_run_id, write_manifest
from PHX2.stage18.readers import Stage17InputBundle, load_stage17_input_dir
from PHX2.stage18.writers import (
    ClassifiedRow,
    make_log_event,
    write_classification_summary,
    write_data_quality_blockers,
    write_log,
    write_readme,
    write_review_matrix,
    write_rule_review_cards,
)


# Locked exit-code class (mirrors Stage 17's pattern).
EXIT_OK = 0
EXIT_CLI_ARG_ERROR = 2
EXIT_INPUT_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_UNEXPECTED = 5


_INPUT_ERROR_CODES: frozenset[str] = frozenset({"B01", "B02", "B03", "B07", "B08"})
_RUNTIME_ERROR_CODES: frozenset[str] = frozenset({"B04", "B05", "B06"})


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_stage18_review",
        description=(
            "Stage 18: deterministic, reports-only operator review "
            "packet builder. Reads a completed Stage 17 output "
            "directory and writes a non-actioning review packet "
            "(CSV + Markdown + manifest + log) to --output-dir."
        ),
    )
    parser.add_argument(
        "--stage17-input-dir",
        required=True,
        type=Path,
        help="Path to a completed Stage 17 output directory (read-only).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help=(
            "Fresh output directory. Stage 18 refuses to reuse, "
            "clean, or overwrite an existing directory; the caller "
            "must provide a new path."
        ),
    )
    parser.add_argument(
        "--policy-hash",
        required=False,
        action="append",
        default=None,
        help=(
            "Restrict output rows to one or more policy_hash "
            "values. May be passed multiple times. Filters at "
            "row level; manifest still embeds the full upstream "
            "Stage 17 manifest verbatim."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the stdout summary line on success.",
    )
    return parser


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _stdout(message: str) -> None:
    print(message)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exit_code_for(code: str) -> int:
    if code in _INPUT_ERROR_CODES:
        return EXIT_INPUT_ERROR
    if code in _RUNTIME_ERROR_CODES:
        return EXIT_RUNTIME_ERROR
    return EXIT_UNEXPECTED


def _classify_all_rows(
    bundle: Stage17InputBundle,
    policy_hash_filter: Optional[frozenset[str]],
) -> list[ClassifiedRow]:
    """Dispatch ``classify_row`` over every coarse row in
    ``bundle``, building the ``ClassifiedRow`` objects the writers
    consume.

    Slice matching is by exact equality on
    (policy_hash, rule_id, window_seconds) -- the same string
    triple Stage 17 used to group its outputs.
    """

    classified: list[ClassifiedRow] = []
    for coarse_row in bundle.coarse_rows:
        ph = coarse_row["policy_hash"]
        if policy_hash_filter is not None and ph not in policy_hash_filter:
            continue
        rid = coarse_row["rule_id"]
        ws = coarse_row["window_seconds"]

        headlines = tuple(
            r for r in bundle.headline_rows
            if r["policy_hash"] == ph
            and r["rule_id"] == rid
            and r["window_seconds"] == ws
        )
        dq = tuple(
            r for r in bundle.data_quality_rows
            if r["policy_hash"] == ph
            and r["rule_id"] == rid
            and r["window_seconds"] == ws
        )
        unev = tuple(
            r for r in bundle.unevaluable_rows
            if r["policy_hash"] == ph and r["rule_id"] == rid
        )

        result = classify_row(
            coarse_row=coarse_row,
            headline_rows_for_slice=headlines,
            data_quality_rows_for_slice=dq,
        )
        classified.append(ClassifiedRow(
            coarse_row=coarse_row,
            classification=result,
            headline_rows_for_slice=headlines,
            unevaluable_breakdown_for_rule=unev,
        ))
    return classified


def _classification_counts(rows: list[ClassifiedRow]) -> dict[str, int]:
    """Tally rows per review label. All six buckets always
    present, with zero counts when unhit."""

    counts: dict[str, int] = {
        REVIEW_LABEL_HARMFUL: 0,
        REVIEW_LABEL_PROMISING: 0,
        REVIEW_LABEL_DATA_BLOCKED: 0,
        REVIEW_LABEL_MIXED_BY_TIER: 0,
        REVIEW_LABEL_WEAK: 0,
        REVIEW_LABEL_INSUFFICIENT_SAMPLE: 0,
    }
    for r in rows:
        counts[r.classification.classification] += 1
    return counts


def main(argv: Optional[list[str]] = None) -> int:
    """Stage 18 CLI entry point. Returns the locked exit code."""

    args = make_parser().parse_args(argv)
    stage17_input_dir: Path = args.stage17_input_dir
    output_dir: Path = args.output_dir

    # --- Quick input-dir existence check (B01) before we create
    #     anything on disk -----------------------------------------
    if not stage17_input_dir.exists() or not stage17_input_dir.is_dir():
        _stderr(
            f"error: [B01] {MESSAGE_TEMPLATES['B01']}: "
            f"--stage17-input-dir does not exist or is not a "
            f"directory: {stage17_input_dir}"
        )
        return EXIT_INPUT_ERROR

    # --- Resolve both paths now so the output_dir invariant checks
    #     below operate on absolute, symlink-resolved paths.
    #     ``Path.resolve()`` succeeds for not-yet-existent paths
    #     (output_dir), returning the absolute form. -----------------
    stage17_input_dir = stage17_input_dir.resolve()
    output_dir = output_dir.resolve()

    # --- Reject output_dir == stage17_input_dir (B05) -------------
    if output_dir == stage17_input_dir:
        _stderr(
            f"error: [B05] {MESSAGE_TEMPLATES['B05']}: "
            f"--output-dir must not equal --stage17-input-dir: "
            f"{output_dir}"
        )
        return EXIT_RUNTIME_ERROR

    # --- Reject output_dir inside stage17_input_dir (B05) ---------
    # Keeping the input directory strictly read-only is the whole
    # point of Stage 18. A nested output dir would otherwise blur
    # the "Stage 17 input is untouched" invariant the non-mutation
    # tests enforce.
    try:
        output_dir.relative_to(stage17_input_dir)
        output_inside_input = True
    except ValueError:
        output_inside_input = False
    if output_inside_input:
        _stderr(
            f"error: [B05] {MESSAGE_TEMPLATES['B05']}: "
            f"--output-dir must not be inside --stage17-input-dir: "
            f"{output_dir}"
        )
        return EXIT_RUNTIME_ERROR

    # --- Reject output_dir whose parent does not exist (B05) ------
    # Stage 18 refuses to silently create intermediate directories
    # outside ``--output-dir``; using ``mkdir(parents=False)`` below
    # would already error, but checking explicitly gives a clearer
    # message and keeps the rejection sequence linear.
    if not output_dir.parent.exists():
        _stderr(
            f"error: [B05] {MESSAGE_TEMPLATES['B05']}: "
            f"parent of --output-dir does not exist: "
            f"{output_dir.parent}"
        )
        return EXIT_RUNTIME_ERROR

    # --- Early B04 check: output_dir must not already exist ------
    # Caught here before any bundle I/O so we don't load Stage 17
    # input just to abandon it. The ``exist_ok=False`` on the
    # later mkdir guards against the race window between this
    # check and the actual provisioning.
    if output_dir.exists():
        _stderr(
            f"error: [B04] {MESSAGE_TEMPLATES['B04']}: {output_dir}"
        )
        return EXIT_RUNTIME_ERROR

    # --- Load Stage 17 inputs BEFORE output_dir is provisioned ---
    # Pre-mkdir loading enforces the non-mutation contract on
    # every input-contract failure: if any required artifact is
    # missing or any CSV/JSON is malformed, ``output_dir`` is
    # never created and no stage18_run.log is left behind. The
    # trade-off is that B01 / B02 / B07 / B08 errors from the
    # reader no longer leave a diagnostic log on disk -- the
    # error message on stderr carries the full closed-set code
    # and detail, which is the only diagnostic Stage 18 emits on
    # input-contract failures.
    try:
        bundle = load_stage17_input_dir(stage17_input_dir)
    except Stage18Error as exc:
        _stderr(f"error: {exc}")
        return _exit_code_for(exc.code)

    # --- Validate Stage 17 descriptive_label cells (B03) ---------
    # Bulk validation across both coarse and headline rows, also
    # BEFORE ``output_dir`` is provisioned. An unknown label
    # anywhere in the input fails the run without leaving any
    # on-disk artifact (no review CSVs, no log). The
    # ``classify_row`` per-row check below is preserved as
    # defence in depth for direct callers that bypass this bulk
    # validator.
    try:
        validate_stage17_labels(
            bundle.coarse_rows, bundle.headline_rows
        )
    except Stage18Error as exc:
        _stderr(f"error: {exc}")
        return _exit_code_for(exc.code)

    # --- Provision output dir (B04 race / B05) -------------------
    # ``parents=False`` keeps Stage 18 honest: every write lands
    # under the caller-supplied path, never in a directory Stage
    # 18 created on its behalf above ``--output-dir``. The
    # ``exist_ok=False`` here guards against a race where another
    # process created ``output_dir`` between the early check
    # above and this call.
    try:
        output_dir.mkdir(parents=False, exist_ok=False)
    except FileExistsError:
        _stderr(
            f"error: [B04] {MESSAGE_TEMPLATES['B04']}: {output_dir}"
        )
        return EXIT_RUNTIME_ERROR
    except OSError as exc:
        _stderr(
            f"error: [B05] {MESSAGE_TEMPLATES['B05']}: {exc}"
        )
        return EXIT_RUNTIME_ERROR

    log_path = output_dir / "stage18_run.log"
    log_events: list[str] = [make_log_event("start")]

    def _try_write_log() -> None:
        try:
            write_log(log_events, log_path)
        except Stage18Error:
            pass

    run_started_utc = _utc_now_iso()

    # ``inputs_loaded`` is logged here (rather than next to the
    # load call) because the log file does not exist until after
    # the mkdir above.
    log_events.append(make_log_event(
        "inputs_loaded",
        headline=len(bundle.headline_rows),
        coarse=len(bundle.coarse_rows),
        unevaluable=len(bundle.unevaluable_rows),
        data_quality=len(bundle.data_quality_rows),
    ))

    try:
        # --- Classify rows (may raise B03 defensively) -------------
        # Build a sorted, deduplicated filter list once; both the
        # classifier dispatch and the manifest / run_id derivation
        # see the same shape.
        policy_hash_filter_list: list[str] = sorted(
            set(args.policy_hash or [])
        )
        policy_hash_filter: Optional[frozenset[str]] = (
            frozenset(policy_hash_filter_list)
            if policy_hash_filter_list
            else None
        )

        try:
            classified = _classify_all_rows(bundle, policy_hash_filter)
        except Stage18Error as exc:
            _stderr(f"error: {exc}")
            log_events.append(
                make_log_event("classify_error", code=exc.code)
            )
            _try_write_log()
            return _exit_code_for(exc.code)

        counts = _classification_counts(classified)

        log_events.append(make_log_event(
            "gates_evaluated",
            n_insufficient=counts[REVIEW_LABEL_INSUFFICIENT_SAMPLE],
            n_blocked=counts[REVIEW_LABEL_DATA_BLOCKED],
        ))
        log_events.append(make_log_event(
            "classification_complete",
            harmful=counts[REVIEW_LABEL_HARMFUL],
            promising=counts[REVIEW_LABEL_PROMISING],
            blocked=counts[REVIEW_LABEL_DATA_BLOCKED],
            mixed=counts[REVIEW_LABEL_MIXED_BY_TIER],
            weak=counts[REVIEW_LABEL_WEAK],
            insufficient=counts[REVIEW_LABEL_INSUFFICIENT_SAMPLE],
        ))

        # --- Write CSVs + markdown cards (B06) ---------------------
        try:
            n_review = write_review_matrix(
                classified, output_dir / "review_matrix.csv"
            )
            log_events.append(make_log_event(
                "review_matrix_written", rows=n_review
            ))

            n_blockers = write_data_quality_blockers(
                classified, output_dir / "data_quality_blockers.csv"
            )
            log_events.append(make_log_event(
                "data_quality_blockers_written", rows=n_blockers
            ))

            n_summary = write_classification_summary(
                classified, output_dir / "classification_summary.csv"
            )
            log_events.append(make_log_event(
                "classification_summary_written", rows=n_summary
            ))

            stage17_run_id = bundle.manifest.get("run_id", "unknown")
            n_cards = write_rule_review_cards(
                classified,
                output_dir / "rule_review_cards.md",
                stage17_run_id=stage17_run_id,
            )
            log_events.append(make_log_event(
                "rule_review_cards_written", cards=n_cards
            ))
        except Stage18Error as exc:
            _stderr(f"error: {exc}")
            log_events.append(
                make_log_event("artifact_write_error", code=exc.code)
            )
            _try_write_log()
            return _exit_code_for(exc.code)

        # --- Manifest + README ------------------------------------
        output_row_counts = {
            "classification_summary.csv": n_summary,
            "review_matrix.csv": n_review,
            "data_quality_blockers.csv": n_blockers,
            "rule_review_cards.md": n_cards,
        }
        run_id = compute_run_id(
            stage17_run_id=stage17_run_id,
            stage17_input_basename=stage17_input_dir.name,
            input_row_counts=bundle.input_row_counts,
            policy_hash_filter=policy_hash_filter_list,
        )
        git_commit = get_git_commit()
        run_finished_utc = _utc_now_iso()

        manifest = build_manifest(
            run_id=run_id,
            run_started_utc=run_started_utc,
            run_finished_utc=run_finished_utc,
            stage17_input_dir=str(stage17_input_dir),
            output_dir=str(output_dir),
            stage17_manifest=bundle.manifest,
            input_row_counts=bundle.input_row_counts,
            output_row_counts=output_row_counts,
            classification_counts=counts,
            git_commit=git_commit,
            policy_hash_filter=policy_hash_filter_list,
        )

        try:
            write_manifest(manifest, output_dir / "manifest.json")
            log_events.append(make_log_event("manifest_written"))
            write_readme(output_dir / "README.md")
        except Stage18Error as exc:
            _stderr(f"error: {exc}")
            log_events.append(
                make_log_event("manifest_or_readme_error", code=exc.code)
            )
            _try_write_log()
            return _exit_code_for(exc.code)

        log_events.append(make_log_event("done"))
        try:
            write_log(log_events, log_path)
        except Stage18Error as exc:
            _stderr(f"error: {exc}")
            return _exit_code_for(exc.code)

        # --- Stdout summary line ----------------------------------
        if not args.quiet:
            _stdout(
                f"stage18 run_id={run_id} "
                f"harmful={counts[REVIEW_LABEL_HARMFUL]} "
                f"promising={counts[REVIEW_LABEL_PROMISING]} "
                f"blocked={counts[REVIEW_LABEL_DATA_BLOCKED]} "
                f"mixed={counts[REVIEW_LABEL_MIXED_BY_TIER]} "
                f"weak={counts[REVIEW_LABEL_WEAK]} "
                f"insufficient={counts[REVIEW_LABEL_INSUFFICIENT_SAMPLE]}"
            )
        return EXIT_OK

    except Stage18Error as exc:
        _stderr(f"error: {exc}")
        log_events.append(
            make_log_event("unhandled_stage18_error", code=exc.code)
        )
        _try_write_log()
        return _exit_code_for(exc.code)

    except Exception as exc:  # noqa: BLE001 -- outermost CLI boundary
        _stderr(
            f"error: unexpected stage18 failure: "
            f"{type(exc).__name__}: {exc}"
        )
        traceback.print_exc(file=sys.stderr)
        log_events.append(
            make_log_event("unexpected", error_type=type(exc).__name__)
        )
        _try_write_log()
        return EXIT_UNEXPECTED


__all__ = [
    "EXIT_CLI_ARG_ERROR",
    "EXIT_INPUT_ERROR",
    "EXIT_OK",
    "EXIT_RUNTIME_ERROR",
    "EXIT_UNEXPECTED",
    "main",
    "make_parser",
]
