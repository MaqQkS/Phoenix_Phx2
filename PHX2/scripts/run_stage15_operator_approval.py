"""Stage 15 operator-approval CLI.

Invocation:

  python PHX2/scripts/run_stage15_operator_approval.py \\
      --stage14-run-path <path to Stage 14 run dir> \\
      --operator-review <path to operator_rule_review.csv> \\
      --output-dir <path to new Stage 15 output dir> \\
      --reviewer <reviewer name>

Three-tier exit discipline (see PHX2.stage15.errors):

  Tier 1: output-dir cannot be initialized
    -> stderr only, no manifest, no log, exit 2

  Tier 2: load-time validation L01-L26
    -> stage15_run.log only (if writable), no manifest, exit 3

  Tier 3: approval-time validation A01-A04
    -> non-draft outputs + manifest with approval_status="VALIDATION_FAILED",
       exit 4

  Clean run: all outputs + manifest "APPROVED_DRAFT_WRITTEN", exit 0

No DB. No network. No live config. No Discord/Telegram/gRPC/API. The
only subprocess invocation is ``git rev-parse HEAD`` to capture the
running PHX2 working-tree commit (CLI-level side effect; the pipeline
modules stay subprocess-free).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__":
    # Direct-script invocation puts only the script's own directory on
    # sys.path. Insert the repo root (two parents up: PHX2/scripts/ ->
    # PHX2 -> repo root) so the ``PHX2`` package resolves.
    _repo_root = str(Path(__file__).resolve().parents[2])
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

from PHX2.stage15.errors import (
    Stage15ApprovalTimeError,
    Stage15LoadTimeError,
    Stage15OutputDirError,
)
from PHX2.stage15.loaders import (
    initialize_output_dir,
    load_impact_summary,
    load_operator_review,
    load_stage14_artifact,
)
from PHX2.stage15.markdown import render_markdown
from PHX2.stage15.reconciler import reconcile
from PHX2.stage15.writer import RUN_LOG_FILENAME, write_outputs


# Exit codes
EXIT_OK = 0
EXIT_OUTPUT_DIR_FAIL = 2     # Tier 1
EXIT_LOAD_TIME_FAIL = 3       # Tier 2
EXIT_APPROVAL_TIME_FAIL = 4   # Tier 3
EXIT_UNEXPECTED = 5           # Programmer error (uncaught exception)


def make_parser() -> argparse.ArgumentParser:
    """Build the Stage 15 CLI argparse parser.

    All four flags are required. Paths are accepted as relative or
    absolute and resolved to absolute paths before any I/O.
    """

    parser = argparse.ArgumentParser(
        prog="run_stage15_operator_approval",
        description=(
            "Stage 15 operator approval layer. Reads a Stage 14 run "
            "directory and an operator review CSV, validates the operator's "
            "decisions against Stage 14-authored warning flags, and emits an "
            "auditable approval draft. Stage 15 is not runtime-consumable "
            "and produces no live policy. Opens no DB connection; makes no "
            "network call; mutates no Stage 14 artifacts."
        ),
    )
    parser.add_argument(
        "--stage14-run-path",
        required=True,
        type=Path,
        help="Path to a Stage 14 run directory.",
    )
    parser.add_argument(
        "--operator-review",
        required=True,
        type=Path,
        help="Path to operator_rule_review.csv.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help=(
            "Path to a new (or empty) Stage 15 output directory. Created "
            "if it does not exist. Must be empty if it already exists."
        ),
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        type=str,
        help=(
            "Reviewer name. Must exactly match every reviewer column "
            "value in --operator-review."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Stage 15 CLI entry point.

    Returns an exit code; the runtime wraps this in SystemExit at
    module level. Tests can call ``main([...])`` directly without
    triggering process exit.

    The outermost ``try / except Exception`` is the global CLI boundary:
    any uncaught Exception (including a programmer bug inside a helper
    such as ``_capture_git_commit``) is mapped to ``EXIT_UNEXPECTED``
    rather than allowed to escape raw. ``SystemExit`` is intentionally
    *not* caught -- argparse's ``--help`` and bad-args paths still exit
    via the standard argparse mechanism.
    """

    # Pre-initialize state that ``_handle_outermost_unexpected`` may
    # consult. ``output_dir`` stays ``None`` until path resolution
    # succeeds, so the outermost handler can distinguish the "before
    # output-dir initialization" case (stderr only, no log write) from
    # the "after output-dir initialization" case (best-effort log).
    output_dir: Path | None = None
    log_lines: list[str] = []
    # Epoch fallback for ``now_utc`` so the outermost handler can still
    # timestamp its log entries even if ``datetime.now`` itself ever
    # raised before we replaced it with the real wall clock.
    now_utc: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)

    try:
        now_utc = datetime.now(timezone.utc)
        args = make_parser().parse_args(argv)

        stage14_path: Path = args.stage14_run_path.resolve()
        operator_path: Path = args.operator_review.resolve()
        output_dir = args.output_dir.resolve()
        reviewer_arg: str = args.reviewer

        argv_for_log = [
            "--stage14-run-path",
            str(stage14_path),
            "--operator-review",
            str(operator_path),
            "--output-dir",
            str(output_dir),
            "--reviewer",
            reviewer_arg,
        ]
        _log(log_lines, now_utc, f"stage15 start argv={argv_for_log!r}")

        # ----- Tier 1: output-dir initialization -----
        try:
            initialize_output_dir(output_dir)
        except Stage15LoadTimeError as exc:
            # initialize_output_dir raises Stage15LoadTimeError with code L24.
            # But per spec, output-dir failure is Tier 1: stderr only, no log.
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_OUTPUT_DIR_FAIL
        except Stage15OutputDirError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_OUTPUT_DIR_FAIL
        except OSError as exc:
            print(
                f"error: --output-dir could not be initialized: {exc}",
                file=sys.stderr,
            )
            return EXIT_OUTPUT_DIR_FAIL

        _log(log_lines, now_utc, f"output_dir initialized at {output_dir}")

        # ----- L25: git commit -----
        # The helper catches the documented subprocess/OS error classes
        # internally and returns None for those (the normal L25 path).
        # An unexpected exception inside the helper itself (e.g., a
        # programmer bug in ``_phx2_repo_root``) propagates and is caught
        # by the outermost boundary as EXIT_UNEXPECTED -- distinct from
        # the normal L25 -> EXIT_LOAD_TIME_FAIL surface.
        git_commit = _capture_git_commit()
        if git_commit is None:
            # Tier 2: write log only, no manifest.
            _log(log_lines, now_utc, "error L25: git_commit unobtainable")
            _emit_load_time_log(output_dir, log_lines)
            print(
                "error: [L25] git_commit for running PHX2 working tree is "
                "unobtainable",
                file=sys.stderr,
            )
            return EXIT_LOAD_TIME_FAIL
        _log(log_lines, now_utc, f"git_commit={git_commit}")

        # ----- Tier 2: load-time validation -----
        try:
            stage14 = load_stage14_artifact(stage14_path)
            _log(
                log_lines,
                now_utc,
                f"stage14 loaded run_path={stage14.run_path} "
                f"rule_count={len(stage14.rules)} "
                f"manifest_hash={stage14.manifest_hash} "
                f"rules_hash={stage14.rules_hash}",
            )

            stage14_rule_ids = tuple(r.rule_id for r in stage14.rules)
            impact = load_impact_summary(stage14_path, stage14_rule_ids)
            _log(
                log_lines,
                now_utc,
                f"impact loaded csv_hash={impact.csv_hash} "
                f"warning_flag_source=stage14_impact_csv "
                f"extra_impact_rule_ids={list(impact.extra_rule_ids)!r}",
            )

            operator_review = load_operator_review(
                operator_path,
                reviewer_arg=reviewer_arg,
                stage14_rule_ids=stage14_rule_ids,
                now_utc=now_utc,
            )
            _log(
                log_lines,
                now_utc,
                f"operator review loaded csv_hash={operator_review.csv_hash} "
                f"operator_row_count={len(operator_review.rows)}",
            )
        except Stage15LoadTimeError as exc:
            _log(log_lines, now_utc, f"load-time validation failed: {exc}")
            _emit_load_time_log(output_dir, log_lines)
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_LOAD_TIME_FAIL
        except Exception as exc:  # noqa: BLE001 -- CLI inner boundary
            return _handle_unexpected_exception(
                exc, output_dir=output_dir, log_lines=log_lines, now_utc=now_utc,
                phase="load",
            )

        # ----- Post-load pipeline: reconciliation -> markdown -> write -----
        # Any uncaught exception from this point is a programmer error,
        # not a Stage15-typed error. The catch-all maps it to
        # EXIT_UNEXPECTED and never writes a manifest, so the freshness
        # probe ("manifest exists") still discriminates valid runs.
        try:
            reconciliation = reconcile(
                stage14_rules=stage14.rules,
                operator_rows=operator_review.rows,
                warning_flags_by_rule=impact.warning_flags_by_rule,
            )
            _log(
                log_lines,
                now_utc,
                f"reconciliation complete "
                f"approved={len(reconciliation.approved)} "
                f"rejected={len(reconciliation.rejected)} "
                f"held={len(reconciliation.held)} "
                f"needs_more_data={len(reconciliation.needs_more_data)} "
                f"unreviewed={len(reconciliation.unreviewed)} "
                f"validation_errors={len(reconciliation.validation_errors)}",
            )

            if reconciliation.validation_failures:
                for failure in reconciliation.validation_failures:
                    _log(
                        log_lines,
                        now_utc,
                        f"approval-time error rule_id={failure.rule_id} "
                        f"code={failure.error_code} row={failure.source_csv_row_number} "
                        f"message={failure.error_message!r}",
                    )

            approval_status_preview = (
                "APPROVED_DRAFT_WRITTEN"
                if not reconciliation.validation_failures
                else "VALIDATION_FAILED"
            )
            markdown_body = render_markdown(
                output_dir=output_dir,
                stage14=stage14,
                impact=impact,
                operator_review=operator_review,
                reconciliation=reconciliation,
                reviewer_arg=reviewer_arg,
                git_commit=git_commit,
                now_utc=now_utc,
                approval_status=approval_status_preview,
            )

            outcome = write_outputs(
                output_dir=output_dir,
                stage14=stage14,
                impact=impact,
                operator_review=operator_review,
                reconciliation=reconciliation,
                markdown_body=markdown_body,
                log_lines=log_lines,
                reviewer_arg=reviewer_arg,
                git_commit=git_commit,
                now_utc=now_utc,
            )
        except Exception as exc:  # noqa: BLE001 -- CLI inner boundary
            return _handle_unexpected_exception(
                exc, output_dir=output_dir, log_lines=log_lines, now_utc=now_utc,
                phase="write",
            )

        if outcome.draft_written:
            return EXIT_OK
        return EXIT_APPROVAL_TIME_FAIL
    except SystemExit:
        # argparse's --help and bad-args paths exit via SystemExit
        # (a BaseException, not an Exception). Let it propagate so the
        # standard argparse error-printing/exit-code semantics are
        # preserved; tests that pass an empty argv expect SystemExit(2).
        raise
    except Exception as exc:  # noqa: BLE001 -- CLI OUTERMOST boundary
        # True outermost CLI boundary. Anything not caught by an inner
        # handler lands here -- e.g., a programmer bug in
        # ``_capture_git_commit`` that raises raw instead of returning
        # None, a bug in ``_log`` that fires before output-dir init, or
        # a Path.resolve() failure on a hostile filesystem. Map to
        # EXIT_UNEXPECTED so no raw exception ever escapes cli_main.
        return _handle_outermost_unexpected(
            exc,
            output_dir=output_dir,
            log_lines=log_lines,
            now_utc=now_utc,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _phx2_repo_root() -> Path:
    """Return the PHX2 repo root.

    The CLI script lives at ``PHX2/scripts/run_stage15_operator_approval.py``,
    so ``parents[2]`` of this file is the repo root irrespective of the
    process cwd. We use this anchor for both ``sys.path`` boot (when run
    as a script) and for ``git rev-parse`` so the L25 check always
    reports the PHX2 commit instead of whatever git happens to be
    discoverable from the caller's cwd.
    """

    return Path(__file__).resolve().parents[2]


def _capture_git_commit() -> str | None:
    """Capture the current git HEAD SHA via subprocess.

    Best-effort: returns None on any subprocess failure (missing git,
    not in a repo, timeout, etc.). Cwd is pinned to the PHX2 repo root
    so invocation from another directory still captures the PHX2 commit
    (the spec's L25 contract) rather than silently picking up an
    unrelated git repository or failing because the caller's cwd isn't
    a repo at all.
    """

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_phx2_repo_root()),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
    sha = proc.stdout.strip()
    return sha or None


def _handle_unexpected_exception(
    exc: BaseException,
    *,
    output_dir: Path,
    log_lines: list[str],
    now_utc: datetime,
    phase: str,
) -> int:
    """Record an unexpected exception and return EXIT_UNEXPECTED.

    Writes the traceback to ``stage15_run.log`` on a best-effort basis so
    the run dir carries forensic detail, even though no manifest is
    emitted (the run is invalid by definition).
    """

    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tb_text = "".join(tb).strip()
    _log(
        log_lines,
        now_utc,
        f"unexpected_exception phase={phase} type={type(exc).__name__} "
        f"message={str(exc)!r}",
    )
    for tb_line in tb_text.splitlines():
        _log(log_lines, now_utc, f"traceback {tb_line}")
    _emit_load_time_log(output_dir, log_lines)
    print(
        f"error: unexpected Stage 15 failure during {phase}: "
        f"{type(exc).__name__}: {exc}",
        file=sys.stderr,
    )
    return EXIT_UNEXPECTED


def _handle_outermost_unexpected(
    exc: BaseException,
    *,
    output_dir: Path | None,
    log_lines: list[str],
    now_utc: datetime,
) -> int:
    """Outermost CLI exception handler.

    Differs from ``_handle_unexpected_exception`` in two ways:

      1. ``output_dir`` may be ``None`` when this fires very early
         (before path resolution completes). In that case we skip the
         log write and surface the failure on stderr only.
      2. We are absolutely the last line of defence -- any helper here
         that could itself raise (logging, file write, traceback
         formatting) is wrapped in a defensive try so the function
         always returns ``EXIT_UNEXPECTED`` rather than re-propagating.

    Traceback content is printed to stderr in all cases so an operator
    running interactively sees the failure even if the log dir doesn't
    exist or isn't writable.
    """

    # 1. Compute traceback text -- defensive; ``format_exception`` itself
    # could in principle raise on an exotic exception with broken
    # ``__traceback__``. We fall back to a minimal description rather
    # than re-raise.
    try:
        tb_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).strip()
    except Exception:  # noqa: BLE001 -- last-line-of-defence
        tb_text = f"<traceback unavailable for {type(exc).__name__}: {exc}>"

    # 2. stderr first -- always works (modulo a totally broken sys.stderr).
    try:
        print(
            f"error: unexpected Stage 15 failure (outermost): "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        if tb_text:
            print(tb_text, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass

    # 3. Best-effort log write when the output dir context exists.
    # If ``output_dir`` is None, we have no place to write the log -- the
    # stderr surface above is the only forensic trail. Otherwise, try
    # the same lifecycle log channel as the inner unexpected handler.
    if output_dir is not None:
        try:
            _log(
                log_lines,
                now_utc,
                f"unexpected_exception phase=outermost "
                f"type={type(exc).__name__} message={str(exc)!r}",
            )
            for tb_line in tb_text.splitlines():
                _log(log_lines, now_utc, f"traceback {tb_line}")
            _emit_load_time_log(output_dir, log_lines)
        except Exception:  # noqa: BLE001
            # Best-effort -- swallow any further failure so the CLI can
            # still return its controlled exit code.
            pass

    return EXIT_UNEXPECTED


def _log(log_lines: list[str], _now: datetime, event: str) -> None:
    """Append a timestamped line to the in-memory log buffer.

    The actual log file is written by the writer module on a clean run
    (with the full output set). For load-time failures we emit the
    log directly via ``_emit_load_time_log``.
    """

    iso_now = datetime.now(timezone.utc).isoformat()
    log_lines.append(f"{iso_now} {event}")


def _emit_load_time_log(output_dir: Path, log_lines: list[str]) -> None:
    """Tier 2: write stage15_run.log directly, skipping other artifacts.

    Best-effort: if writing the log itself fails (disk full, permission
    error), we swallow the error so the CLI can still surface the
    underlying load-time validation message via stderr.
    """

    try:
        text = "\n".join(log_lines)
        if not text.endswith("\n"):
            text += "\n"
        (output_dir / RUN_LOG_FILENAME).write_bytes(text.encode("utf-8"))
    except OSError:
        # Tier 2 says "if possible". A best-effort write is the
        # contract; we don't escalate to Tier 1 just because the log
        # couldn't land.
        pass


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
