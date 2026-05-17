"""Stage 20.4 closure run orchestrator.

CLI entry point that wires every Phase 1-5 component together
into the locked 17-event closure pipeline, then writes the
deterministic eight-file closure packet to
``<output_root>/stage20_closure_runs/<run_id>/``.

CLI:

    python -m PHX2.stage20.closure.run_orchestrator <path_to_config.json>

Exactly one positional argument: the JSON config file path.

Exit codes (locked):

  * 0  -- closure_status = ``closed_pending_operator_review`` and
          all eight artifacts were written.
  * 1  -- pre-run-dir validation failure (E2030 / E2031 / E2043 /
          E2044 / E2045) OR pre-run-dir E2046 (target run dir
          already exists) OR post-run-dir failure where
          closure_status = ``closure_blocked`` and the full eight-
          artifact blocked packet was written.
  * 2  -- CLI usage error (wrong arg count) OR ``InputFormatError``
          (config file missing / unreadable / malformed JSON / root
          not an object / missing required top-level key /
          operator_test_results not a JSON object / output_root
          precondition failure).

Failure-mode partition (locked):

  * Pre-run-dir failures (exit 1 or 2): the orchestrator MUST NOT
    create ``<output_root>/stage20_closure_runs/<run_id>/`` and MUST
    NOT write any artifact. The existing-run-dir check (E2046) runs
    BEFORE ``mkdir``.

  * Post-run-dir failures (exit 1, closure_status = closure_blocked):
    once the run directory exists, all subsequent E20xx conditions
    (audit failures, artifact validation failures, lineage hash
    mismatches, operator-test-results inconsistencies recorded by
    earlier phases but ignored here because input_validation already
    fired) MUST produce the full eight-artifact closure_blocked
    packet. The orchestrator never partially writes.

Determinism contract:

  * Same config + same clock + (possibly different) output_root ->
    byte-identical artifact contents. The orchestrator records
    ``inputs.output_root`` (the loaded config's path) in the closure
    manifest, NOT the effective write location. The
    ``output_root_override`` keyword argument is a test-only seam.

  * Different clocks against the same config alter only the
    ``run_id`` / ``generated_at_utc`` / timestamp fields in the four
    timestamp-bearing artifacts (manifest, run log, handoff,
    README). The four stable artifacts (codebase audit report,
    Stage 20.2 lineage, Stage 20.3 lineage, checklist CSV) remain
    byte-identical.

What this module does NOT do (locked):

  * Does NOT invoke git, subprocess, sqlite3, or network clients.
  * Does NOT read environment variables.
  * Does NOT import Phoenix1 code.
  * Does NOT mutate Stage 20.2 / Stage 20.3 artifacts.
  * Does NOT implement any Stage 21 surface.
  * Does NOT create the ``stage-20-closed`` git tag.
  * Does NOT push to remote.

Phoenix1 departure note: this module imports no Phoenix1 code.

Boundary discipline: imports only stdlib + the closure subtree.
The orchestrator is the single integration point with Phase 1-5
modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from PHX2.stage20.closure import artifact_validator as av
from PHX2.stage20.closure.checklist_builder import build_checklist
from PHX2.stage20.closure.clock_helper import Clock, default_clock
from PHX2.stage20.closure.closure_writer import write_closure_packet
from PHX2.stage20.closure.codebase_auditor import audit_codebase
from PHX2.stage20.closure.constants import (
    CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
    CLOSURE_OUTPUT_DIR_NAME,
    CLOSURE_STATUS_BLOCKED,
    CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW,
    HANDOFF_CONTRACT_VERSION,
    LIVE_DISPATCH_READY,
    RUN_ID_TEMPLATE,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE20_2_REQUIRED_ARTIFACT_FILENAMES,
    STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE,
    STAGE20_3_REQUIRED_ARTIFACT_FILENAMES,
)
from PHX2.stage20.closure.handoff_writer import render_handoff, render_readme
from PHX2.stage20.closure.input_loader import (
    InputFormatError,
    compute_config_sha8,
    load_input_config,
)
from PHX2.stage20.closure.models import (
    ArtifactValidationResult,
    ClosurePacket,
)


__all__ = [
    "main",
    "run_closure",
]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _format_utc_compact(generated_at_utc: str) -> str:
    """Convert ``YYYY-MM-DDTHH:MM:SSZ`` -> ``YYYYMMDDTHHMMSSZ``.

    Pure string transform on the locked ISO-Z format produced by
    ``clock_helper.format_utc_iso_z`` (no datetime parsing needed).
    Replaces the two separator classes (``-`` and ``:``) only; the
    ``T`` and ``Z`` letters carry through unchanged.
    """

    return generated_at_utc.replace("-", "").replace(":", "")


def _detect_prior_closure_runs(
    closure_runs_root: Path,
    current_run_id: str,
) -> bool:
    """Return True iff one or more existing closure run directories
    (other than ``current_run_id``) exist under ``closure_runs_root``.

    Defensive: filters by the locked ``stage20_4_`` prefix so an
    unrelated sibling directory under ``output_root/stage20_closure_runs/``
    does not falsely trip W2024.
    """

    if not closure_runs_root.exists() or not closure_runs_root.is_dir():
        return False
    for child in closure_runs_root.iterdir():
        if not child.is_dir():
            continue
        if child.name == current_run_id:
            continue
        if child.name.startswith("stage20_4_"):
            return True
    return False


def _import_hit_to_record(hit, code: str) -> dict:
    return {
        "code": code,
        "detail": (
            f"{hit.reason} import {hit.module!r} at "
            f"{hit.file}:{hit.line}"
        ),
    }


def _token_hit_to_record(hit, code: str) -> dict:
    return {
        "code": code,
        "detail": (
            f"token {hit.token!r} at {hit.file}:{hit.line} "
            f"(context: {hit.context!r})"
        ),
    }


def _error_record(code: str, detail: str) -> dict:
    return {"code": code, "detail": detail}


def _collect_audit_errors(audit) -> tuple[dict, ...]:
    """Encode every CodebaseAuditResult error condition as records.

    Maps:
      * forbidden_network_imports -> E2037 (env reads use the same
        E2037 code per the locked C.5 mapping).
      * forbidden_phoenix1_imports -> E2038.
      * cross_stage_violations -> E2039.
      * env_reads_in_closure -> E2037.
      * subprocess_uses_in_closure -> E2037.
      * sqlite_imports_in_closure -> E2037.
      * blocking_token_hits -> E2040.
    """

    out: list[dict] = []
    for hit in audit.forbidden_network_imports:
        out.append(_import_hit_to_record(hit, "E2037"))
    for hit in audit.forbidden_phoenix1_imports:
        out.append(_import_hit_to_record(hit, "E2038"))
    for hit in audit.cross_stage_violations:
        out.append(_import_hit_to_record(hit, "E2039"))
    for hit in audit.env_reads_in_closure:
        out.append(_import_hit_to_record(hit, "E2037"))
    for hit in audit.subprocess_uses_in_closure:
        out.append(_import_hit_to_record(hit, "E2037"))
    for hit in audit.sqlite_imports_in_closure:
        out.append(_import_hit_to_record(hit, "E2037"))
    for hit in audit.blocking_token_hits:
        out.append(_token_hit_to_record(hit, "E2040"))
    return tuple(out)


def _collect_audit_warnings(audit) -> tuple[dict, ...]:
    out: list[dict] = []
    for hit in audit.warning_token_hits:
        out.append(_token_hit_to_record(hit, "W2025"))
    return tuple(out)


def _validation_records(records, target_class: str) -> tuple[dict, ...]:
    """Convert NamedTuple (code, detail) records to dicts."""
    return tuple(
        _error_record(r.code, r.detail) for r in records
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_closure(
    config_path: Path,
    *,
    clock: Clock | None = None,
    output_root_override: Path | None = None,
) -> int:
    """Run the Stage 20.4 closure pipeline.

    Args:
        config_path: path to the JSON config file (Phase 2 schema).
        clock: injected Clock. Defaults to ``default_clock()``.
        output_root_override: test-only seam. When provided, the
            orchestrator writes artifacts under
            ``<override>/stage20_closure_runs/<run_id>/`` instead of
            ``<config.output_root>/stage20_closure_runs/<run_id>/``.
            The closure manifest still records the config's
            ``output_root`` so artifact contents remain byte-
            identical across overrides.

    Returns:
        Exit code (0, 1, or 2; see module docstring).
    """

    if clock is None:
        clock = default_clock()

    # ----- Pre-run-dir Step 1: load + parse config ------------------
    try:
        loaded = load_input_config(config_path, clock=clock)
    except InputFormatError as exc:
        sys.stderr.write(f"InputFormatError: {exc}\n")
        return 2

    config = loaded.config
    input_validation_errors = loaded.validation_errors

    # ----- Pre-run-dir Step 2: E20xx pre-run-dir validation ---------
    if input_validation_errors:
        sys.stderr.write(
            "Stage 20.4 pre-run-dir validation failed; refusing to "
            "create run directory.\n"
        )
        for err in input_validation_errors:
            sys.stderr.write(f"  {err.code}: {err.detail}\n")
        return 1

    # ----- Pre-run-dir Step 3: derive run_id and run_dir ------------
    config_sha8 = compute_config_sha8(config)
    utc_compact = _format_utc_compact(config.generated_at_utc)
    run_id = RUN_ID_TEMPLATE.format(
        utc_compact=utc_compact, config_sha8=config_sha8,
    )

    effective_output_root = (
        output_root_override
        if output_root_override is not None
        else config.output_root
    )
    closure_runs_root = effective_output_root / CLOSURE_OUTPUT_DIR_NAME
    run_dir = closure_runs_root / run_id

    # ----- Pre-run-dir Step 4: E2046 existing-run-dir check ---------
    if run_dir.exists():
        sys.stderr.write(
            f"E2046: Stage 20.4 run directory already exists; refusing "
            f"to overwrite: {run_dir}\n"
        )
        return 1

    # ----- Pre-run-dir Step 5: W2024 prior-closure-run detection ----
    prior_closure_run_detected = _detect_prior_closure_runs(
        closure_runs_root, run_id,
    )

    # ----- Pre-run-dir Step 6: create run_dir -----------------------
    # parents=True so output_root/stage20_closure_runs/ is created
    # the first time this output_root is used. exist_ok=False so the
    # E2046 check above is the single source of truth for overwrite
    # refusal.
    run_dir.mkdir(parents=True, exist_ok=False)

    # ===================================================================
    # POST-RUN-DIR STAGE: every failure from here on writes the full
    # 8-artifact closure_blocked packet and exits 1.
    # ===================================================================

    ts = config.generated_at_utc
    log_events: list[dict] = []

    # ----- Event: input_loaded --------------------------------------
    log_events.append({
        "event": "input_loaded",
        "ts": ts,
        "run_id": run_id,
        "stage20_1_commit_sha": config.stage20_1_commit_sha,
        "stage20_2_commit_sha": config.stage20_2_commit_sha,
        "stage20_3_commit_sha": config.stage20_3_commit_sha,
    })

    # ----- Codebase audit (inner + outer + tokens) ------------------
    log_events.append({
        "event": "codebase_audit_inner_started",
        "ts": ts, "run_id": run_id,
    })
    audit = audit_codebase(config.repo_root)
    log_events.append({
        "event": "codebase_audit_inner_completed",
        "ts": ts, "run_id": run_id,
        "inner_files_scanned": len(audit.inner_files_scanned),
    })
    log_events.append({
        "event": "codebase_audit_outer_started",
        "ts": ts, "run_id": run_id,
    })
    log_events.append({
        "event": "codebase_audit_outer_completed",
        "ts": ts, "run_id": run_id,
        "outer_files_scanned": len(audit.outer_files_scanned),
    })
    log_events.append({
        "event": "forbidden_token_scan_started",
        "ts": ts, "run_id": run_id,
    })
    log_events.append({
        "event": "forbidden_token_scan_completed",
        "ts": ts, "run_id": run_id,
        "blocking_hits": len(audit.blocking_token_hits),
        "warning_hits": len(audit.warning_token_hits),
    })

    # ----- Artifact validation (Stage 20.2 + Stage 20.3 + lineage) --
    log_events.append({
        "event": "artifact_validation_stage20_2_started",
        "ts": ts, "run_id": run_id,
    })
    s2 = av.validate_stage20_2(config.stage20_2_run_dir)
    log_events.append({
        "event": "artifact_validation_stage20_2_completed",
        "ts": ts, "run_id": run_id,
        "manifest_valid": s2.manifest_valid,
        "errors": len(s2.errors),
    })
    log_events.append({
        "event": "artifact_validation_stage20_3_started",
        "ts": ts, "run_id": run_id,
    })
    s3 = av.validate_stage20_3(config.stage20_3_run_dir)
    log_events.append({
        "event": "artifact_validation_stage20_3_completed",
        "ts": ts, "run_id": run_id,
        "manifest_valid": s3.manifest_valid,
        "errors": len(s3.errors),
    })
    log_events.append({
        "event": "lineage_crosscheck_started",
        "ts": ts, "run_id": run_id,
    })
    lineage = av.crosscheck_stage20_2_lineage(
        s3.manifest_data, config.stage20_2_run_dir,
    )
    log_events.append({
        "event": "lineage_crosscheck_completed",
        "ts": ts, "run_id": run_id,
        "passed": lineage.passed,
    })

    # Synthesize the same ArtifactValidationResult that
    # validate_artifacts would produce, plus the merged error/warning
    # tuples. This lets the orchestrator emit the lineage_crosscheck
    # event between sub-results without duplicating av.validate_artifacts.
    s2_all_required_present = all(
        s2.artifacts_present.get(f, False)
        for f in STAGE20_2_REQUIRED_ARTIFACT_FILENAMES
    )
    s3_all_required_present = all(
        s3.artifacts_present.get(f, False)
        for f in STAGE20_3_REQUIRED_ARTIFACT_FILENAMES
    )
    validation_passed = (
        s2.manifest_valid
        and s2.safe_for_live_dispatch_false
        and s2_all_required_present
        and s3.manifest_valid
        and s3.safe_for_live_dispatch_false
        and s3.live_dispatch_ready_false
        and s3_all_required_present
        and s3.filter_registry_empty
        and s3.filter_results_empty
        and lineage.passed
    )
    artifact_validation = ArtifactValidationResult(
        stage20_2_manifest_valid=s2.manifest_valid,
        stage20_2_artifacts_present=dict(s2.artifacts_present),
        stage20_2_artifact_hashes=s2.artifact_hashes,
        stage20_2_safe_for_live_dispatch_false=(
            s2.safe_for_live_dispatch_false
        ),
        stage20_3_manifest_valid=s3.manifest_valid,
        stage20_3_artifacts_present=dict(s3.artifacts_present),
        stage20_3_artifact_hashes=s3.artifact_hashes,
        stage20_3_safe_for_live_dispatch_false=(
            s3.safe_for_live_dispatch_false
        ),
        stage20_3_live_dispatch_ready_false=s3.live_dispatch_ready_false,
        stage20_3_filter_registry_empty=s3.filter_registry_empty,
        stage20_3_filter_results_empty=s3.filter_results_empty,
        lineage_crosscheck_passed=lineage.passed,
        passed=validation_passed,
    )

    artifact_errors = s2.errors + s3.errors + lineage.errors
    artifact_warnings = s2.warnings + s3.warnings

    # ----- Event: operator_test_results_validated -------------------
    # Pre-run-dir validation already accepted (validation_errors empty),
    # so this is a record event only.
    log_events.append({
        "event": "operator_test_results_validated",
        "ts": ts, "run_id": run_id,
        "all_green": config.operator_test_results.all_green,
        "both_runs_match": config.operator_test_results.both_runs_match,
    })

    # ----- Build checklist ------------------------------------------
    checklist = build_checklist(
        inputs=config,
        input_validation_errors=(),
        audit=audit,
        artifacts=artifact_validation,
        artifact_warnings=artifact_warnings,
        run_dir_was_fresh=True,
        prior_closure_run_detected=prior_closure_run_detected,
    )
    log_events.append({
        "event": "checklist_built",
        "ts": ts, "run_id": run_id,
        "total": len(checklist),
    })

    # ----- Decide closure_status ------------------------------------
    closure_passed = (
        audit.passed
        and artifact_validation.passed
        and config.operator_test_results.all_green
    )
    closure_status = (
        CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW
        if closure_passed
        else CLOSURE_STATUS_BLOCKED
    )
    log_events.append({
        "event": "closure_status_decided",
        "ts": ts, "run_id": run_id,
        "status": closure_status,
    })

    # ----- Compose packet errors/warnings ---------------------------
    packet_errors = (
        _collect_audit_errors(audit)
        + _validation_records(artifact_errors, "artifact")
    )
    packet_warnings = list(_collect_audit_warnings(audit))
    for w in artifact_warnings:
        packet_warnings.append(_error_record(w.code, w.detail))
    if prior_closure_run_detected:
        packet_warnings.append(_error_record(
            "W2024",
            f"prior closure run directory detected in "
            f"{closure_runs_root}",
        ))

    # ----- Build packet ---------------------------------------------
    packet = ClosurePacket(
        inputs=config,
        codebase_audit=audit,
        artifact_validation=artifact_validation,
        checklist=checklist,
        warnings=tuple(packet_warnings),
        errors=tuple(packet_errors),
        safe_for_live_dispatch=SAFE_FOR_LIVE_DISPATCH,
        live_dispatch_ready=LIVE_DISPATCH_READY,
        handoff_contract_version=HANDOFF_CONTRACT_VERSION,
        closure_status=closure_status,
        run_id=run_id,
    )

    # ----- Render handoff + README ----------------------------------
    handoff_md = render_handoff(inputs=config, run_id=run_id)
    readme_md = render_readme(
        inputs=config, run_id=run_id, closure_status=closure_status,
    )

    # ----- Extract Stage 20.3's recorded Stage 20.2 lineage block ---
    recorded_stage20_2_lineage_block: dict | None = None
    if isinstance(s3.manifest_data, dict):
        block = s3.manifest_data.get(
            STAGE20_3_MANIFEST_FIELD_STAGE20_2_LINEAGE,
        )
        if isinstance(block, dict):
            recorded_stage20_2_lineage_block = block

    # ----- Final event: artifacts_written ---------------------------
    log_events.append({
        "event": "artifacts_written",
        "ts": ts, "run_id": run_id,
        "artifacts": list(CLOSURE_OUTPUT_ARTIFACT_FILENAMES),
    })

    # ----- Write all 8 artifacts ------------------------------------
    write_closure_packet(
        run_dir=run_dir,
        packet=packet,
        audit=audit,
        artifact_validation=artifact_validation,
        stage20_3_recorded_stage20_2_lineage=recorded_stage20_2_lineage_block,
        log_events=tuple(log_events),
        handoff_md=handoff_md,
        readme_md=readme_md,
    )

    return 0 if closure_passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Parses argv (exactly one positional config-path arg), dispatches
    to :func:`run_closure`, and returns the resulting exit code.
    Wrong arg count prints usage to stderr and returns 2.
    """

    if argv is None:
        argv = sys.argv[1:]

    if len(argv) != 1:
        sys.stderr.write(
            "Usage: python -m PHX2.stage20.closure.run_orchestrator "
            "<path_to_config.json>\n"
        )
        return 2

    return run_closure(Path(argv[0]))


if __name__ == "__main__":  # pragma: no cover - exercised via -m
    raise SystemExit(main())
