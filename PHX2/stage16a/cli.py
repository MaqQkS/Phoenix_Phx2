"""Stage 16A CLI entry: parses args, dispatches the three-tier exit pipeline, and never opens a DB or network connection.

Three-tier exit discipline (mirrors Stage 15):

  Tier A -- output-dir cannot be created / is non-empty:
    stderr only, exit ``EXIT_OUTPUT_DIR_FAIL``, NO files written.
  Tier B -- output-dir initialized, load-time validation fails (L01-L20
            on Stage 15 input, or L22 git_commit unobtainable):
    ``stage16a_run.log`` written, NO manifest, NO runtime policy file,
    exit ``EXIT_LOAD_TIME_FAIL``.
  Tier C -- clean run:
    all three files written, manifest written LAST atomically,
    exit ``EXIT_OK``.

Manifest atomicity: serialize to bytes, write to ``<name>.tmp`` in the
output dir, then ``os.replace`` to the final name. A crash mid-write
leaves either no manifest or the complete final one -- callers can use
manifest existence as a freshness probe.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.hashing import sha256_bytes
from PHX2.stage16a.runtime_policy_builder import (
    RuntimePolicyBuilder,
    STAGE15_LINEAGE_PASSTHROUGH_FIELDS,
)
from PHX2.stage16a.safety import EXPECTED_STAGE15_SAFETY_SURFACE
from PHX2.stage16a.stage15_loader import (
    Stage15ApprovedDraftLoader,
    capture_git_commit,
    initialize_output_dir,
)


# Exit codes (mirror Stage 15 convention).
EXIT_OK = 0
EXIT_OUTPUT_DIR_FAIL = 2     # Tier A
EXIT_LOAD_TIME_FAIL = 3      # Tier B
EXIT_UNEXPECTED = 5          # Programmer error (uncaught exception)


RUN_LOG_FILENAME = "stage16a_run.log"
MANIFEST_FILENAME = "stage16a_manifest.json"
RUNTIME_POLICY_FILENAME = "observe_only_runtime_policy.json"


MANIFEST_SCHEMA_VERSION = "stage16a_manifest_v0"
RUN_STATUS_OK = "RUNTIME_POLICY_WRITTEN"


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_stage16a",
        description=(
            "Stage 16A: build an observe-only runtime policy artifact from a "
            "Stage 15 approved draft. Artifact-only. No DB. No live wiring. "
            "No alert-flow integration."
        ),
    )
    parser.add_argument(
        "--stage15-run-path",
        required=True,
        type=Path,
        help="Path to a Stage 15 approved-draft run directory.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help=(
            "Path to a new (or empty) Stage 16A output directory. Created "
            "if it does not exist. Must be empty if it already exists."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Stage 16A CLI entry point.

    Returns an exit code. Tests call ``main([...])`` directly. ``SystemExit``
    from argparse (``--help`` / bad args) is allowed to propagate so the
    standard argparse error-printing/exit-code semantics are preserved.
    """

    output_dir: Path | None = None
    log_lines: list[str] = []
    now_utc: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)

    try:
        now_utc = datetime.now(timezone.utc)
        args = make_parser().parse_args(argv)
        stage15_path: Path = args.stage15_run_path.resolve()
        output_dir = args.output_dir.resolve()

        _log(log_lines, f"stage16a start stage15_run_path={stage15_path} output_dir={output_dir}")

        # ----- Tier A: output-dir initialization -----
        try:
            initialize_output_dir(output_dir)
        except Stage16AError as exc:
            # L21 -- Tier A: stderr only, no log, no manifest.
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_OUTPUT_DIR_FAIL
        except OSError as exc:
            print(
                f"error: --output-dir could not be initialized: {exc}",
                file=sys.stderr,
            )
            return EXIT_OUTPUT_DIR_FAIL

        _log(log_lines, f"output_dir initialized at {output_dir}")

        # ----- Tier B: git_commit (L22) -----
        try:
            git_commit = capture_git_commit()
        except Stage16AError as exc:
            _log(log_lines, f"L22 git_commit unobtainable: {exc}")
            _emit_load_time_log(output_dir, log_lines)
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_LOAD_TIME_FAIL

        _log(log_lines, f"git_commit={git_commit}")

        # ----- Tier B: load-time validation (L01-L20) -----
        try:
            draft = Stage15ApprovedDraftLoader().load(stage15_path)
        except Stage16AError as exc:
            _log(log_lines, f"load-time validation failed: {exc}")
            _emit_load_time_log(output_dir, log_lines)
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_LOAD_TIME_FAIL

        _log(
            log_lines,
            f"stage15 draft loaded manifest_hash={draft.manifest_hash} "
            f"draft_hash={draft.draft_hash} "
            f"approved_rule_count={len(draft.draft['rules'])}",
        )

        # ----- Tier C: build + write -----
        try:
            body = RuntimePolicyBuilder().build(
                draft, now_utc=now_utc, git_commit=git_commit
            )
        except Exception as exc:  # noqa: BLE001 -- inner boundary
            return _handle_unexpected(
                exc, output_dir, log_lines, phase="build",
            )

        try:
            policy_path = output_dir / RUNTIME_POLICY_FILENAME
            policy_bytes = _json_bytes(body)
            policy_path.write_bytes(policy_bytes)
            policy_file_hash = sha256_bytes(policy_bytes)
            _log(log_lines, f"wrote {RUNTIME_POLICY_FILENAME} hash={policy_file_hash}")
        except Exception as exc:  # noqa: BLE001
            return _handle_unexpected(
                exc, output_dir, log_lines, phase="write_policy",
            )

        try:
            # Finalize the log buffer and write it BEFORE the manifest so
            # the manifest references the final log hash. The log doesn't
            # reference itself in its own bytes.
            _log(log_lines, "manifest_write_pending")
            log_path = output_dir / RUN_LOG_FILENAME
            log_bytes = _log_bytes(log_lines)
            log_path.write_bytes(log_bytes)
            log_hash = sha256_bytes(log_bytes)

            manifest = _build_manifest(
                draft=draft,
                body=body,
                now_utc=now_utc,
                git_commit=git_commit,
                policy_file_hash=policy_file_hash,
                log_hash=log_hash,
            )
            manifest_path = output_dir / MANIFEST_FILENAME
            tmp_path = output_dir / (MANIFEST_FILENAME + ".tmp")
            tmp_path.write_bytes(_json_bytes(manifest))
            os.replace(tmp_path, manifest_path)
        except Exception as exc:  # noqa: BLE001
            return _handle_unexpected(
                exc, output_dir, log_lines, phase="write_manifest",
            )

        return EXIT_OK

    except SystemExit:
        # argparse --help and bad-args paths exit via SystemExit. Let
        # them propagate so argparse's error semantics are preserved.
        raise
    except Exception as exc:  # noqa: BLE001 -- outermost boundary
        return _handle_outermost(exc, output_dir, log_lines)


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def _build_manifest(
    *,
    draft,
    body: Mapping[str, Any],
    now_utc: datetime,
    git_commit: str,
    policy_file_hash: str,
    log_hash: str,
) -> dict[str, Any]:
    # Stage 15 lineage passthrough block.
    stage15_lineage: dict[str, Any] = {}
    for fld in STAGE15_LINEAGE_PASSTHROUGH_FIELDS:
        stage15_lineage[fld] = draft.manifest.get(fld, "")

    # Stage 15 input safety surface -- the 7 named keys from
    # EXPECTED_STAGE15_SAFETY_SURFACE, mirrored verbatim from the Stage 15
    # manifest. Future Stage 15 extras are deliberately not carried here.
    s15_safety_surface: dict[str, Any] = {
        fld: draft.manifest.get(fld) for fld in EXPECTED_STAGE15_SAFETY_SURFACE
    }

    return {
        "stage16a_schema_version": MANIFEST_SCHEMA_VERSION,
        "stage": 16,
        "substage": "16A",
        "run_status": RUN_STATUS_OK,
        "generated_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "source_stage15_run_path": str(draft.run_path.resolve()),
        "source_stage15_manifest_hash": draft.manifest_hash,
        "source_stage15_policy_draft_hash": draft.draft_hash,
        "stage15_lineage_passthrough": stage15_lineage,
        "input_stage15_approved_rule_count": len(draft.draft.get("rules", [])),
        "output_runtime_rule_count": body["rule_count"],
        "output_runtime_policy_hash": body["policy_hash"],
        "safety_surface_input_stage15": s15_safety_surface,
        "safety_surface_output_runtime": dict(body["safety_surface"]),
        "output_files": {
            RUNTIME_POLICY_FILENAME: policy_file_hash,
            RUN_LOG_FILENAME: log_hash,
        },
    }


# ---------------------------------------------------------------------------
# IO + logging helpers
# ---------------------------------------------------------------------------


def _json_bytes(payload: Any) -> bytes:
    """Pretty-printed sort_keys JSON + trailing newline (matches Stage 15's
    on-disk encoding for human readability)."""

    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _log(log_lines: list[str], event: str) -> None:
    iso = datetime.now(timezone.utc).isoformat()
    log_lines.append(f"{iso} {event}")


def _log_bytes(log_lines: list[str]) -> bytes:
    text = "\n".join(log_lines)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _emit_load_time_log(output_dir: Path, log_lines: list[str]) -> None:
    """Tier B: write stage16a_run.log directly, skipping every other artifact.

    Best-effort: if the disk write itself fails, swallow so the CLI can
    still surface the underlying load-time message via stderr.
    """

    try:
        (output_dir / RUN_LOG_FILENAME).write_bytes(_log_bytes(log_lines))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Unexpected exception handlers
# ---------------------------------------------------------------------------


def _handle_unexpected(
    exc: BaseException,
    output_dir: Path,
    log_lines: list[str],
    *,
    phase: str,
) -> int:
    """Programmer-error path: record the traceback to the log, no manifest."""

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    _log(log_lines, f"unexpected_exception phase={phase} type={type(exc).__name__} message={str(exc)!r}")
    for line in tb.splitlines():
        _log(log_lines, f"traceback {line}")
    _emit_load_time_log(output_dir, log_lines)
    print(
        f"error: unexpected Stage 16A failure during {phase}: "
        f"{type(exc).__name__}: {exc}",
        file=sys.stderr,
    )
    return EXIT_UNEXPECTED


def _handle_outermost(
    exc: BaseException,
    output_dir: Path | None,
    log_lines: list[str],
) -> int:
    """Outermost CLI exception handler. ``output_dir`` may be None if the
    failure happened before path resolution."""

    try:
        tb_text = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).strip()
    except Exception:  # noqa: BLE001
        tb_text = f"<traceback unavailable for {type(exc).__name__}: {exc}>"

    try:
        print(
            f"error: unexpected Stage 16A failure (outermost): "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        if tb_text:
            print(tb_text, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass

    if output_dir is not None:
        try:
            _log(
                log_lines,
                f"unexpected_exception phase=outermost type={type(exc).__name__} message={str(exc)!r}",
            )
            for line in tb_text.splitlines():
                _log(log_lines, f"traceback {line}")
            _emit_load_time_log(output_dir, log_lines)
        except Exception:  # noqa: BLE001
            pass

    return EXIT_UNEXPECTED
