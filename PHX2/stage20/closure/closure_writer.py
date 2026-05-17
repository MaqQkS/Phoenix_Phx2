"""Stage 20.4 closure writer.

Writes the deterministic eight-file closure packet to a target
run directory. The run directory must already exist; the caller
(orchestrator in Phase 6) handles directory creation and the
E2046 overwrite guard.

The eight artifacts, in deterministic write order:

  1. stage20_closure_manifest.json
  2. stage20_closure_checklist.csv
  3. codebase_audit_report.json
  4. stage20_2_lineage.json
  5. stage20_3_lineage.json
  6. stage20_4_run.log
  7. stage21_handoff.md
  8. README.md

Serialization rules (locked):

  * JSON: ``json.dumps(data, sort_keys=True, indent=2,
    ensure_ascii=False) + "\\n"``. UTF-8 encoded; no BOM.
  * CSV:  ``csv.writer(f, lineterminator="\\n",
    quoting=csv.QUOTE_MINIMAL)`` with the explicit column tuple
    ``CHECKLIST_CSV_COLUMNS``. Header always written.
  * Markdown: pre-rendered text from handoff_writer; written as
    UTF-8 bytes verbatim.
  * Run log: JSON-lines. Each line is
    ``json.dumps(event, sort_keys=True, ensure_ascii=False)``
    followed by ``"\\n"``. The full event sequence is written in
    a single ``path.write_bytes`` call (no post-hash appends).

What this module does NOT do:

  * Does NOT create the run directory itself.
  * Does NOT compute audit / validation / checklist results.
  * Does NOT render markdown templates (handoff_writer owns that).
  * Does NOT invoke git, subprocess, sqlite3, or read env vars.
  * Does NOT mutate Stage 20.2 / Stage 20.3 run dirs (only
    writes to the closure run dir supplied as ``run_dir``).

Phoenix1 departure note: this module imports no Phoenix1 code.

Boundary discipline: imports only stdlib + closure subtree.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from PHX2.stage20.closure.constants import (
    CHECKLIST_CSV_COLUMNS,
    CLOSURE_CHECKLIST_FILENAME,
    CLOSURE_MANIFEST_FILENAME,
    CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
    CLOSURE_README_FILENAME,
    CLOSURE_RUN_LOG_FILENAME,
    CODEBASE_AUDIT_REPORT_FILENAME,
    HANDOFF_CONTRACT_VERSION,
    LIVE_DISPATCH_READY,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE20_2_LINEAGE_FILENAME,
    STAGE20_3_LINEAGE_FILENAME,
    STAGE20_4_MINOR_VERSION,
    STAGE21_HANDOFF_FILENAME,
)
from PHX2.stage20.closure.models import (
    ArtifactValidationResult,
    CodebaseAuditResult,
    ClosurePacket,
)
from PHX2.stage20.closure.checklist_builder import checklist_counts


# ---------------------------------------------------------------------------
# Dict conversion helpers (public for orchestrator + tests)
# ---------------------------------------------------------------------------


def packet_to_manifest_dict(packet: ClosurePacket) -> dict:
    """Convert a ``ClosurePacket`` to a JSON-serializable dict.

    The dict is the wire-format of the closure manifest. Keys are
    explicit; sort_keys=True at serialization time produces the
    canonical on-disk order.
    """

    return {
        "stage20_4_minor_version": STAGE20_4_MINOR_VERSION,
        "run_id": packet.run_id,
        "closure_status": packet.closure_status,
        "safe_for_live_dispatch": SAFE_FOR_LIVE_DISPATCH,
        "live_dispatch_ready": LIVE_DISPATCH_READY,
        "handoff_contract_version": packet.handoff_contract_version,
        "generated_at_utc": packet.inputs.generated_at_utc,
        "inputs": _inputs_to_dict(packet.inputs),
        "codebase_audit_summary": audit_summary_dict(
            packet.codebase_audit,
        ),
        "artifact_validation_summary": artifact_validation_summary_dict(
            packet.artifact_validation,
        ),
        "checklist_counts": checklist_counts(packet.checklist),
        "errors": list(packet.errors),
        "warnings": list(packet.warnings),
    }


def _inputs_to_dict(inputs) -> dict:
    op = inputs.operator_test_results
    return {
        "stage20_1_commit_sha": inputs.stage20_1_commit_sha,
        "stage20_2_commit_sha": inputs.stage20_2_commit_sha,
        "stage20_3_commit_sha": inputs.stage20_3_commit_sha,
        "stage20_2_run_dir": str(inputs.stage20_2_run_dir),
        "stage20_3_run_dir": str(inputs.stage20_3_run_dir),
        "repo_root": str(inputs.repo_root),
        "output_root": str(inputs.output_root),
        "operator_test_results": {
            "test_command": op.test_command,
            "run1_passed": op.run1_passed,
            "run1_failed": op.run1_failed,
            "run1_errors": op.run1_errors,
            "run2_passed": op.run2_passed,
            "run2_failed": op.run2_failed,
            "run2_errors": op.run2_errors,
            "both_runs_match": op.both_runs_match,
            "all_green": op.all_green,
        },
    }


def audit_summary_dict(audit: CodebaseAuditResult) -> dict:
    """Compact summary block for the closure manifest's audit field."""
    return {
        "inner_files_scanned_count": len(audit.inner_files_scanned),
        "outer_files_scanned_count": len(audit.outer_files_scanned),
        "forbidden_network_imports_count": len(
            audit.forbidden_network_imports,
        ),
        "forbidden_phoenix1_imports_count": len(
            audit.forbidden_phoenix1_imports,
        ),
        "cross_stage_violations_count": len(audit.cross_stage_violations),
        "env_reads_in_closure_count": len(audit.env_reads_in_closure),
        "subprocess_uses_in_closure_count": len(
            audit.subprocess_uses_in_closure,
        ),
        "sqlite_imports_in_closure_count": len(
            audit.sqlite_imports_in_closure,
        ),
        "blocking_token_hits_count": len(audit.blocking_token_hits),
        "warning_token_hits_count": len(audit.warning_token_hits),
        "passed": audit.passed,
    }


def artifact_validation_summary_dict(
    validation: ArtifactValidationResult,
) -> dict:
    """Compact summary block for the closure manifest's artifacts field."""
    return {
        "stage20_2_manifest_valid": validation.stage20_2_manifest_valid,
        "stage20_2_safe_for_live_dispatch_false": (
            validation.stage20_2_safe_for_live_dispatch_false
        ),
        "stage20_3_manifest_valid": validation.stage20_3_manifest_valid,
        "stage20_3_safe_for_live_dispatch_false": (
            validation.stage20_3_safe_for_live_dispatch_false
        ),
        "stage20_3_live_dispatch_ready_false": (
            validation.stage20_3_live_dispatch_ready_false
        ),
        "stage20_3_filter_registry_empty": (
            validation.stage20_3_filter_registry_empty
        ),
        "stage20_3_filter_results_empty": (
            validation.stage20_3_filter_results_empty
        ),
        "lineage_crosscheck_passed": validation.lineage_crosscheck_passed,
        "passed": validation.passed,
    }


def audit_to_report_dict(audit: CodebaseAuditResult) -> dict:
    """Detailed audit report dict (full hit lists; written to
    codebase_audit_report.json)."""

    return {
        "inner_files_scanned": list(audit.inner_files_scanned),
        "outer_files_scanned": list(audit.outer_files_scanned),
        "forbidden_network_imports": [
            _import_hit_dict(h) for h in audit.forbidden_network_imports
        ],
        "forbidden_phoenix1_imports": [
            _import_hit_dict(h) for h in audit.forbidden_phoenix1_imports
        ],
        "cross_stage_violations": [
            _import_hit_dict(h) for h in audit.cross_stage_violations
        ],
        "env_reads_in_closure": [
            _import_hit_dict(h) for h in audit.env_reads_in_closure
        ],
        "subprocess_uses_in_closure": [
            _import_hit_dict(h)
            for h in audit.subprocess_uses_in_closure
        ],
        "sqlite_imports_in_closure": [
            _import_hit_dict(h) for h in audit.sqlite_imports_in_closure
        ],
        "blocking_token_hits": [
            _token_hit_dict(h) for h in audit.blocking_token_hits
        ],
        "warning_token_hits": [
            _token_hit_dict(h) for h in audit.warning_token_hits
        ],
        "passed": audit.passed,
    }


def _import_hit_dict(hit) -> dict:
    return {
        "file": hit.file,
        "line": hit.line,
        "module": hit.module,
        "reason": hit.reason,
    }


def _token_hit_dict(hit) -> dict:
    return {
        "file": hit.file,
        "line": hit.line,
        "token": hit.token,
        "context": hit.context,
        "severity": hit.severity,
    }


def _artifact_hash_dict(h) -> dict:
    return {
        "path": h.relative_path,
        "sha256": h.sha256,
        "bytes": h.bytes,
    }


def stage20_2_lineage_dict(
    inputs,
    validation: ArtifactValidationResult,
) -> dict:
    """Build the stage20_2_lineage.json content.

    Records the actual Stage 20.2 artifact hashes Stage 20.4
    computed, plus the per-file presence map and the safety-flag
    sub-state. The orchestrator passes this dict to write_lineage.
    """

    return {
        "stage20_2_run_dir": str(inputs.stage20_2_run_dir),
        "manifest_valid": validation.stage20_2_manifest_valid,
        "safe_for_live_dispatch_false": (
            validation.stage20_2_safe_for_live_dispatch_false
        ),
        "artifacts_present": dict(validation.stage20_2_artifacts_present),
        "artifact_hashes": [
            _artifact_hash_dict(h)
            for h in validation.stage20_2_artifact_hashes
        ],
    }


def stage20_3_lineage_dict(
    inputs,
    validation: ArtifactValidationResult,
    recorded_stage20_2_lineage_block: dict | None,
) -> dict:
    """Build the stage20_3_lineage.json content.

    Records:
      * The actual Stage 20.3 artifact hashes Stage 20.4 computed.
      * Stage 20.3's own ``stage20_2_lineage`` block (the lineage
        Stage 20.3 recorded at its closure time; pulled out of the
        Stage 20.3 manifest by the orchestrator).
      * The result of the crosscheck (lineage_crosscheck_passed).
    """

    return {
        "stage20_3_run_dir": str(inputs.stage20_3_run_dir),
        "manifest_valid": validation.stage20_3_manifest_valid,
        "safe_for_live_dispatch_false": (
            validation.stage20_3_safe_for_live_dispatch_false
        ),
        "live_dispatch_ready_false": (
            validation.stage20_3_live_dispatch_ready_false
        ),
        "filter_registry_empty": validation.stage20_3_filter_registry_empty,
        "filter_results_empty": validation.stage20_3_filter_results_empty,
        "artifacts_present": dict(validation.stage20_3_artifacts_present),
        "artifact_hashes": [
            _artifact_hash_dict(h)
            for h in validation.stage20_3_artifact_hashes
        ],
        "stage20_3_recorded_stage20_2_lineage": (
            recorded_stage20_2_lineage_block
            if recorded_stage20_2_lineage_block is not None
            else {}
        ),
        "lineage_crosscheck_passed": validation.lineage_crosscheck_passed,
    }


# ---------------------------------------------------------------------------
# Low-level writers (locked serialization formats)
# ---------------------------------------------------------------------------


def write_json(path: Path, data: dict) -> None:
    """Write ``data`` to ``path`` as canonical JSON.

    Locked: sort_keys=True, indent=2, ensure_ascii=False, trailing
    newline, UTF-8 encoded, no BOM. Uses a single
    ``path.write_bytes`` call (no post-write appends).
    """

    blob = json.dumps(
        data,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    path.write_bytes(blob.encode("utf-8"))


def write_checklist_csv(path: Path, checklist: tuple) -> None:
    """Write the 28-row checklist as canonical CSV.

    Locked: explicit ``CHECKLIST_CSV_COLUMNS`` header, csv.writer
    with ``lineterminator="\\n"``, ``QUOTE_MINIMAL``.
    """

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(
            f, lineterminator="\n", quoting=csv.QUOTE_MINIMAL,
        )
        writer.writerow(list(CHECKLIST_CSV_COLUMNS))
        for item in checklist:
            writer.writerow([
                item.code,
                item.description,
                item.status,
                item.severity,
                item.detail,
            ])


def write_run_log(path: Path, events: tuple) -> None:
    """Write the run log as JSON Lines.

    Each event is serialized with ``sort_keys=True,
    ensure_ascii=False`` and joined with ``"\\n"``. The full text
    is written in a single ``path.write_bytes`` call. UTF-8, no
    BOM, no post-write appends.
    """

    lines = []
    for event in events:
        lines.append(json.dumps(
            event,
            sort_keys=True,
            ensure_ascii=False,
        ))
    text = "\n".join(lines) + ("\n" if lines else "")
    path.write_bytes(text.encode("utf-8"))


def write_markdown(path: Path, text: str) -> None:
    """Write pre-rendered markdown to ``path`` as UTF-8 bytes."""

    path.write_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def write_closure_packet(
    *,
    run_dir: Path,
    packet: ClosurePacket,
    audit: CodebaseAuditResult,
    artifact_validation: ArtifactValidationResult,
    stage20_3_recorded_stage20_2_lineage: dict | None,
    log_events: tuple,
    handoff_md: str,
    readme_md: str,
) -> tuple:
    """Write all 8 closure artifacts into ``run_dir``.

    ``run_dir`` must exist (the orchestrator creates it). Returns
    a tuple of the 8 written paths in the locked write order. The
    caller may use the returned tuple to verify all expected
    artifacts landed on disk.
    """

    # 1. stage20_closure_manifest.json
    manifest_path = run_dir / CLOSURE_MANIFEST_FILENAME
    write_json(manifest_path, packet_to_manifest_dict(packet))

    # 2. stage20_closure_checklist.csv
    checklist_path = run_dir / CLOSURE_CHECKLIST_FILENAME
    write_checklist_csv(checklist_path, packet.checklist)

    # 3. codebase_audit_report.json
    audit_report_path = run_dir / CODEBASE_AUDIT_REPORT_FILENAME
    write_json(audit_report_path, audit_to_report_dict(audit))

    # 4. stage20_2_lineage.json
    s2_lineage_path = run_dir / STAGE20_2_LINEAGE_FILENAME
    write_json(
        s2_lineage_path,
        stage20_2_lineage_dict(packet.inputs, artifact_validation),
    )

    # 5. stage20_3_lineage.json
    s3_lineage_path = run_dir / STAGE20_3_LINEAGE_FILENAME
    write_json(
        s3_lineage_path,
        stage20_3_lineage_dict(
            packet.inputs,
            artifact_validation,
            stage20_3_recorded_stage20_2_lineage,
        ),
    )

    # 6. stage20_4_run.log
    log_path = run_dir / CLOSURE_RUN_LOG_FILENAME
    write_run_log(log_path, log_events)

    # 7. stage21_handoff.md
    handoff_path = run_dir / STAGE21_HANDOFF_FILENAME
    write_markdown(handoff_path, handoff_md)

    # 8. README.md
    readme_path = run_dir / CLOSURE_README_FILENAME
    write_markdown(readme_path, readme_md)

    return (
        manifest_path,
        checklist_path,
        audit_report_path,
        s2_lineage_path,
        s3_lineage_path,
        log_path,
        handoff_path,
        readme_path,
    )


__all__ = [
    "artifact_validation_summary_dict",
    "audit_summary_dict",
    "audit_to_report_dict",
    "packet_to_manifest_dict",
    "stage20_2_lineage_dict",
    "stage20_3_lineage_dict",
    "write_checklist_csv",
    "write_closure_packet",
    "write_json",
    "write_markdown",
    "write_run_log",
]
