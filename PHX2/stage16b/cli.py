"""Stage 16B CLI entry: parses CLI args, runs the one-shot observer, prints a single summary line to stdout, exits with the locked exit-code class (0/2/3/4/5)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.observe_only_policy_evaluator import ObserveOnlyPolicyEvaluator
from PHX2.stage16a.observe_only_policy_loader import ObserveOnlyPolicyLoader
from PHX2.stage16b.decision_context_assembler import DecisionContextAssembler
from PHX2.stage16b.errors import MESSAGE_TEMPLATES, Stage16BError
from PHX2.stage16b.models import ObserverRunReport
from PHX2.stage16b.observer import ObserveOnlyObserverService
from PHX2.stage16b.repository import ObserveOnlyEvaluationRepository


# Locked exit-code class (per STEP 0 V11 and Phase 1 approval):
#   0  clean run (including empty policy and limit=0)
#   2  CLI argument error (argparse default for missing/invalid args)
#   3  load / schema validation error
#         (M01 table absent, M02 alert_decisions absent,
#          M03 filter_evaluations absent, M04 Stage 16A R-code load
#          failure / unsafe policy, M07 invalid CLI argument semantics,
#          M08 negative --limit, file-not-found pre-checks)
#   4  runtime observer error (M05 assembler crash, M06 repository insert
#      failure, observer policy_hash mismatch RuntimeError)
#   5  unexpected / programmer error (uncaught at top level)
EXIT_OK = 0
EXIT_CLI_ARG_ERROR = 2
EXIT_LOAD_ERROR = 3
EXIT_RUNTIME_ERROR = 4
EXIT_UNEXPECTED = 5


def make_parser() -> argparse.ArgumentParser:
    """Build the Stage 16B observer CLI argparse parser.

    All three flags are required. ``--limit`` is parsed as an ``int``
    here; ``main()`` layers the non-negative check (M08) on top.
    """

    parser = argparse.ArgumentParser(
        prog="run_stage16b_observer_once",
        description=(
            "Stage 16B: one-shot sidecar observer. Evaluates already-committed "
            "WOULD_ALERT alert decisions against a Stage 16A observe-only "
            "runtime policy and writes append-only telemetry to "
            "observe_only_policy_evaluations. No daemon. No enforcement. "
            "No alert-flow integration."
        ),
    )
    parser.add_argument(
        "--runtime-policy-path",
        required=True,
        type=Path,
        help="Path to a Stage 16A observe_only_runtime_policy.json artifact.",
    )
    parser.add_argument(
        "--db-path",
        required=True,
        type=Path,
        help="Path to the PHX2 SQLite database.",
    )
    parser.add_argument(
        "--limit",
        required=True,
        type=int,
        help=(
            "Max number of un-evaluated WOULD_ALERT decisions to process "
            "this run (>= 0; 0 is valid and writes zero rows)."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _stdout(message: str) -> None:
    print(message)


def _table_exists(connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_summary(report: ObserverRunReport) -> str:
    """Single-line stdout summary emitted on clean runs.

    Format is locked by ``test_cli_clean_run_summary_line_format``:

      stage16b observer:
        policy_hash=<hash> rules=<n>
        evaluated=<n> inserted=<n> ignored=<n>
        matched=<n> not_matched=<n> unevaluable=<n>
        skipped=<n> duration=<seconds>s

    Emitted as a single line (no embedded newlines).
    """

    return (
        f"stage16b observer: "
        f"policy_hash={report.policy_hash} "
        f"rules={report.policy_rule_count} "
        f"evaluated={report.alert_decisions_evaluated} "
        f"inserted={report.rows_inserted} "
        f"ignored={report.rows_ignored_duplicates} "
        f"matched={report.matched_count} "
        f"not_matched={report.not_matched_count} "
        f"unevaluable={report.unevaluable_count} "
        f"skipped={report.decisions_skipped_not_found} "
        f"duration={report.evaluation_duration_seconds:.3f}s"
    )


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """Stage 16B CLI entry point.

    Returns the exit code per the locked class. ``SystemExit(2)`` from
    argparse (``--help``, missing/unknown arg, bad ``int`` for ``--limit``)
    is allowed to propagate so the standard argparse error-printing /
    exit-code semantics are preserved -- tests catch via
    ``pytest.raises(SystemExit)``.
    """

    args = make_parser().parse_args(argv)

    runtime_policy_path: Path = args.runtime_policy_path
    db_path: Path = args.db_path
    limit: int = args.limit

    # M08: --limit must be non-negative.
    if limit < 0:
        _stderr(f"error: [M08] {MESSAGE_TEMPLATES['M08']}: got {limit}")
        return EXIT_LOAD_ERROR

    # Pre-validate file existence so we never silently create a fresh
    # SQLite DB (which sqlite3.connect would otherwise do for a missing
    # path) and never run the loader on a missing artifact.
    if not db_path.is_file():
        _stderr(
            f"error: --db-path does not exist or is not a file: {db_path}"
        )
        return EXIT_LOAD_ERROR

    if not runtime_policy_path.is_file():
        _stderr(
            f"error: --runtime-policy-path does not exist or is not a file: "
            f"{runtime_policy_path}"
        )
        return EXIT_LOAD_ERROR

    # Open DB connection. Stage 16B uses a raw ``sqlite3.Connection`` and
    # never imports ``PHX2.db.connection``: the audit found that
    # ``PHX2.db.connection`` transitively loads ``PHX2.config.settings``
    # and ``PHX2.models.enums``, widening Stage 16B's sidecar import
    # boundary beyond the locked surface. ``row_factory = sqlite3.Row``
    # is set so PRAGMA queries (used by both Stage 16B and the
    # PHX2.db.migrations chain) can index rows by column name.
    try:
        resolved_db_path = db_path.expanduser().resolve()
        connection = sqlite3.connect(str(resolved_db_path))
        connection.row_factory = sqlite3.Row
    except Exception as exc:  # noqa: BLE001 -- top-level boundary
        _stderr(f"error: could not open PHX2 DB at {db_path}: {exc}")
        return EXIT_LOAD_ERROR

    try:
        # Verify required tables exist BEFORE building the observer.
        # A missing table is a load-tier failure (exit 3) and never
        # produces any DB writes because we have not yet wired the
        # repository.
        for table_name, code in (
            ("observe_only_policy_evaluations", "M01"),
            ("alert_decisions", "M02"),
            ("filter_evaluations", "M03"),
        ):
            if not _table_exists(connection, table_name):
                _stderr(f"error: [{code}] {MESSAGE_TEMPLATES[code]}")
                return EXIT_LOAD_ERROR

        # Wire the observer dependencies. The real Stage 16A loader and
        # evaluator are used here; tests of pipeline behavior under stubs
        # are in Phase 6.
        observer = ObserveOnlyObserverService(
            policy_loader=ObserveOnlyPolicyLoader(),
            evaluator_factory=ObserveOnlyPolicyEvaluator,
            assembler=DecisionContextAssembler(connection),
            repository=ObserveOnlyEvaluationRepository(connection),
            clock=_utc_now_iso,
        )

        try:
            report = observer.run_once(runtime_policy_path, limit=limit)
        except Stage16AError as exc:
            # R01-R08 surface here through the loader call inside run_once.
            _stderr(f"error: [M04] {MESSAGE_TEMPLATES['M04']}: {exc}")
            return EXIT_LOAD_ERROR
        except sqlite3.Error as exc:
            # Repository INSERT failure or other DB error during the run.
            _stderr(
                f"error: [M06] {MESSAGE_TEMPLATES['M06']}: "
                f"{type(exc).__name__}: {exc}"
            )
            return EXIT_RUNTIME_ERROR
        except RuntimeError as exc:
            # Observer-internal RuntimeError (e.g., policy_hash mismatch).
            _stderr(f"error: stage16b observer runtime error: {exc}")
            return EXIT_RUNTIME_ERROR
        except Stage16BError as exc:
            # Future-proofing: if any Stage 16B layer raises a Stage16BError
            # mid-run, route by code class.
            if exc.code in ("M01", "M02", "M03", "M04", "M07", "M08"):
                _stderr(f"error: {exc}")
                return EXIT_LOAD_ERROR
            _stderr(f"error: {exc}")
            return EXIT_RUNTIME_ERROR

        _stdout(_format_summary(report))
        return EXIT_OK

    except Exception as exc:  # noqa: BLE001 -- outermost boundary
        # Unexpected / programmer error.
        _stderr(
            f"error: unexpected stage16b failure: "
            f"{type(exc).__name__}: {exc}"
        )
        traceback.print_exc(file=sys.stderr)
        return EXIT_UNEXPECTED

    finally:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 -- best-effort cleanup
            pass
