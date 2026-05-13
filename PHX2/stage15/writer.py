"""Stage 15 artifact writer.

Owns:

  * non-draft CSV outputs (operator_review_decisions.csv,
    rejected_rules.csv, held_rules.csv, needs_more_data_rules.csv,
    unreviewed_rules.csv, approval_validation_errors.csv)
  * approved_observe_only_policy_draft.json (clean run only)
  * stage15_run.log (structured plain text with run lifecycle events)
  * manifest.json (written last, atomic; never emitted on load-time
    failure)

Write order discipline:

  1. Emit all non-manifest files.
  2. SHA-256 hash every emitted file.
  3. Atomic-write manifest.json last (write to .tmp then rename).

The manifest is the run's commit point. If Stage 15 crashes before the
manifest lands, the run is invalid by definition (callers check for
manifest existence as a freshness probe).

Determinism: JSON uses ``sort_keys=True`` + ``indent=2`` + trailing
newline. CSVs use stable row ordering (Stage 14 rule order for
unreviewed/rejected/held/needs_more_data; operator CSV order for
operator_review_decisions; Stage 14 rule order for the policy draft).
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from PHX2.stage15.hashing import sha256_bytes, sha256_file
from PHX2.stage15.loaders import (
    ImpactSummary,
    OperatorReview,
    Stage14Artifact,
)
from PHX2.stage15.reconciler import (
    FinalBucket,
    ReconciledRule,
    ReconciliationResult,
    ValidationFailure,
)
from PHX2.stage15.safety_gate import (
    DRAFT_APPROVAL_STATUS,
    DRAFT_SCHEMA_VERSION,
    MANIFEST_APPROVED,
    MANIFEST_SCHEMA_VERSION,
    MANIFEST_VALIDATION_FAILED,
    RULE_HARD_BLOCK_ALLOWED,
    RULE_INTENDED_ACTION,
    assert_draft_safety_invariants,
)


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------

POLICY_DRAFT_FILENAME = "approved_observe_only_policy_draft.json"
OPERATOR_DECISIONS_FILENAME = "operator_review_decisions.csv"
REJECTED_FILENAME = "rejected_rules.csv"
HELD_FILENAME = "held_rules.csv"
NEEDS_MORE_DATA_FILENAME = "needs_more_data_rules.csv"
UNREVIEWED_FILENAME = "unreviewed_rules.csv"
APPROVAL_ERRORS_FILENAME = "approval_validation_errors.csv"
MARKDOWN_FILENAME = "stage15_operator_approval_review.md"
RUN_LOG_FILENAME = "stage15_run.log"
MANIFEST_FILENAME = "manifest.json"


# CSV column orderings (locked for determinism / external consumers).

OPERATOR_DECISIONS_COLUMNS: tuple[str, ...] = (
    "rule_id",
    "operator_decision",
    "operator_reason",
    "reviewer",
    "reviewed_at_utc",
    "override_warning_flags",
    "notes",
    "final_bucket",
)

BUCKET_CSV_COLUMNS: tuple[str, ...] = (
    "rule_id",
    "operator_reason",
    "reviewer",
    "reviewed_at_utc",
    "notes",
    "warning_flags",
)

UNREVIEWED_COLUMNS: tuple[str, ...] = (
    "rule_id",
    "predicate_summary",
    "warning_flags",
)

VALIDATION_ERRORS_COLUMNS: tuple[str, ...] = (
    "rule_id",
    "operator_decision",
    "error_code",
    "error_message",
    "source_csv_row_number",
)


@dataclass
class WriteOutcome:
    """What the writer produced.

    ``draft_written`` is True only on a clean run with zero approval-
    time errors. ``output_files`` maps every emitted file (including
    the manifest at the end) to its sha256 hash.
    """

    draft_written: bool
    output_files: dict[str, str]
    manifest_path: Path
    approval_status: str


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def write_outputs(
    *,
    output_dir: Path,
    stage14: Stage14Artifact,
    impact: ImpactSummary,
    operator_review: OperatorReview,
    reconciliation: ReconciliationResult,
    markdown_body: str,
    log_lines: list[str],
    reviewer_arg: str,
    git_commit: str,
    now_utc: datetime,
) -> WriteOutcome:
    """Write every Stage 15 output.

    The manifest is written last atomically; ``log_lines`` are extended
    in-place with write-event entries before the run.log is finalized.
    Callers should keep their own copy of ``log_lines`` only if they
    plan to inspect it after this function returns.
    """

    output_dir.mkdir(parents=True, exist_ok=True)

    # Tier discrimination is driven by the reconciliation result, not a
    # separate flag. If there are no validation failures, we write the
    # draft and mark APPROVED_DRAFT_WRITTEN; otherwise we suppress the
    # draft and mark VALIDATION_FAILED.
    draft_written = len(reconciliation.validation_failures) == 0
    approval_status = (
        MANIFEST_APPROVED if draft_written else MANIFEST_VALIDATION_FAILED
    )

    # Collect file hashes as we write. The policy draft slot is always
    # present in the manifest dict (per spec), but its value is null
    # when no draft was emitted.
    file_hashes: dict[str, str | None] = {
        POLICY_DRAFT_FILENAME: None,
    }

    _append_log(
        log_lines,
        now_utc,
        f"write_outputs begin draft_written={draft_written} "
        f"approval_status={approval_status}",
    )

    # 1. Per-bucket and operator-review CSV outputs (always written).
    _write_operator_decisions_csv(output_dir, reconciliation, file_hashes)
    _write_bucket_csv(
        output_dir, REJECTED_FILENAME, reconciliation.rejected, file_hashes
    )
    _write_bucket_csv(
        output_dir, HELD_FILENAME, reconciliation.held, file_hashes
    )
    _write_bucket_csv(
        output_dir,
        NEEDS_MORE_DATA_FILENAME,
        reconciliation.needs_more_data,
        file_hashes,
    )
    _write_unreviewed_csv(output_dir, reconciliation, file_hashes)
    _write_validation_errors_csv(output_dir, reconciliation, file_hashes)

    # 2. Policy draft (only on clean run).
    if draft_written:
        _write_policy_draft(
            output_dir=output_dir,
            stage14=stage14,
            impact=impact,
            operator_review=operator_review,
            reconciliation=reconciliation,
            reviewer_arg=reviewer_arg,
            git_commit=git_commit,
            now_utc=now_utc,
            file_hashes=file_hashes,
        )

    # 3. Markdown review document.
    _write_markdown(output_dir, markdown_body, file_hashes)

    # 4. Run log (finalize after every other artifact is hashed; the
    # log itself is not included in its own hash because it would be
    # self-referential).
    _append_log(
        log_lines,
        now_utc,
        f"manifest write_pending output_files={sorted(file_hashes.keys())!r}",
    )
    _write_run_log(output_dir, log_lines, file_hashes)

    # 5. Manifest written last (atomic).
    manifest_path = _write_manifest(
        output_dir=output_dir,
        stage14=stage14,
        impact=impact,
        operator_review=operator_review,
        reconciliation=reconciliation,
        reviewer_arg=reviewer_arg,
        git_commit=git_commit,
        now_utc=now_utc,
        approval_status=approval_status,
        draft_written=draft_written,
        file_hashes=file_hashes,
    )

    return WriteOutcome(
        draft_written=draft_written,
        output_files={k: v for k, v in file_hashes.items() if v is not None},
        manifest_path=manifest_path,
        approval_status=approval_status,
    )


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _write_csv(
    path: Path,
    columns: tuple[str, ...],
    rows: Iterable[Mapping[str, Any]],
) -> bytes:
    """Render a CSV to bytes with stable LF line endings and write it.

    Returns the written byte string so the caller can hash without
    re-reading from disk.
    """

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=list(columns), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    data = buf.getvalue().encode("utf-8")
    path.write_bytes(data)
    return data


def _write_operator_decisions_csv(
    output_dir: Path,
    reconciliation: ReconciliationResult,
    file_hashes: dict[str, str | None],
) -> None:
    """operator_review_decisions.csv preserves operator CSV order."""

    rows = []
    for reconciled in reconciliation.operator_row_results:
        op = reconciled.operator_row
        assert op is not None  # operator_row_results only contains reviewed rules
        rows.append(
            {
                "rule_id": op.rule_id,
                "operator_decision": op.operator_decision,
                "operator_reason": op.operator_reason,
                "reviewer": op.reviewer,
                "reviewed_at_utc": op.reviewed_at_utc_raw,
                "override_warning_flags": (
                    "true" if op.override_warning_flags else "false"
                ),
                "notes": op.notes,
                "final_bucket": reconciled.final_bucket.value,
            }
        )
    data = _write_csv(
        output_dir / OPERATOR_DECISIONS_FILENAME,
        OPERATOR_DECISIONS_COLUMNS,
        rows,
    )
    file_hashes[OPERATOR_DECISIONS_FILENAME] = sha256_bytes(data)


def _write_bucket_csv(
    output_dir: Path,
    filename: str,
    rules: tuple[ReconciledRule, ...],
    file_hashes: dict[str, str | None],
) -> None:
    """rejected/held/needs_more_data CSVs preserve Stage 14 rule order
    (because ReconciliationResult.rules is Stage-14-ordered)."""

    rows = []
    for r in rules:
        op = r.operator_row
        assert op is not None  # bucket-CSV rules always have operator rows
        rows.append(
            {
                "rule_id": r.rule.rule_id,
                "operator_reason": op.operator_reason,
                "reviewer": op.reviewer,
                "reviewed_at_utc": op.reviewed_at_utc_raw,
                "notes": op.notes,
                "warning_flags": ";".join(r.warning_flags),
            }
        )
    data = _write_csv(output_dir / filename, BUCKET_CSV_COLUMNS, rows)
    file_hashes[filename] = sha256_bytes(data)


def _write_unreviewed_csv(
    output_dir: Path,
    reconciliation: ReconciliationResult,
    file_hashes: dict[str, str | None],
) -> None:
    """Unreviewed rules ordered by Stage 14 rule order."""

    rows = []
    for r in reconciliation.unreviewed:
        rows.append(
            {
                "rule_id": r.rule.rule_id,
                "predicate_summary": predicate_summary(r.rule.predicate),
                "warning_flags": ";".join(r.warning_flags),
            }
        )
    data = _write_csv(output_dir / UNREVIEWED_FILENAME, UNREVIEWED_COLUMNS, rows)
    file_hashes[UNREVIEWED_FILENAME] = sha256_bytes(data)


def _write_validation_errors_csv(
    output_dir: Path,
    reconciliation: ReconciliationResult,
    file_hashes: dict[str, str | None],
) -> None:
    """approval_validation_errors.csv preserves operator CSV row order."""

    rows = []
    for failure in reconciliation.validation_failures:
        rows.append(
            {
                "rule_id": failure.rule_id,
                "operator_decision": failure.operator_decision,
                "error_code": failure.error_code,
                "error_message": failure.error_message,
                "source_csv_row_number": str(failure.source_csv_row_number),
            }
        )
    data = _write_csv(
        output_dir / APPROVAL_ERRORS_FILENAME,
        VALIDATION_ERRORS_COLUMNS,
        rows,
    )
    file_hashes[APPROVAL_ERRORS_FILENAME] = sha256_bytes(data)


def predicate_summary(predicate: Mapping[str, Any]) -> str:
    """tier|filter_name|filter_version|filter_label summary string.

    Matches the spec example: ``T2|fee_gate|fee_gate_v1_no_bribes|SCAM_LIKELY``.
    """

    return (
        f"{predicate.get('tier_scope', '?')}|"
        f"{predicate.get('filter_name', '?')}|"
        f"{predicate.get('filter_version', '?')}|"
        f"{predicate.get('filter_label', '?')}"
    )


# ---------------------------------------------------------------------------
# JSON writers
# ---------------------------------------------------------------------------


def _write_policy_draft(
    *,
    output_dir: Path,
    stage14: Stage14Artifact,
    impact: ImpactSummary,
    operator_review: OperatorReview,
    reconciliation: ReconciliationResult,
    reviewer_arg: str,
    git_commit: str,
    now_utc: datetime,
    file_hashes: dict[str, str | None],
) -> None:
    """Emit approved_observe_only_policy_draft.json.

    Defensive: invokes assert_draft_safety_invariants() before
    serialization so a regression in this function (or in
    safety_gate.py constants) surfaces as a hard test failure rather
    than producing an unsafe artifact.
    """

    approved = reconciliation.approved
    earliest, latest = _approval_timestamp_range(approved)

    rules_payload: list[dict[str, Any]] = []
    for r in approved:
        op = r.operator_row
        assert op is not None  # APPROVED rules always have operator rows
        raw_rule = r.rule.raw
        rules_payload.append(
            {
                "rule_id": r.rule.rule_id,
                "predicate": {
                    "tier_scope": r.rule.predicate.get("tier_scope"),
                    "filter_name": r.rule.predicate.get("filter_name"),
                    "filter_version": r.rule.predicate.get("filter_version"),
                    "filter_label": r.rule.predicate.get("filter_label"),
                    "threshold_version": r.rule.predicate.get("threshold_version"),
                },
                "stage14_simulated_action": r.rule.simulated_action,
                "intended_action_if_wired": RULE_INTENDED_ACTION,
                "hard_block_allowed": RULE_HARD_BLOCK_ALLOWED,
                "operator_decision": op.operator_decision,
                "operator_reason": op.operator_reason,
                "reviewed_at_utc": op.reviewed_at_utc_raw,
                "warning_flags": list(r.warning_flags),
                "override_warning_flags": bool(op.override_warning_flags),
                "source_stage14_rule_hash": _stage14_rule_hash(raw_rule),
            }
        )

    draft: dict[str, Any] = {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "stage": 15,
        "approval_status": DRAFT_APPROVAL_STATUS,

        "enforcement_mode": "NONE",
        "intended_action_set": ["LOG_WOULD_BLOCK"],

        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "safe_for_observe_only_wiring": True,
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,

        "approved_by_human": True,
        "reviewer": reviewer_arg,
        "reviewed_at_utc_range": {
            "earliest": earliest,
            "latest": latest,
        },

        "source_stage14_run_path": str(stage14.run_path.resolve()),
        "source_stage14_manifest_hash": stage14.manifest_hash,
        "source_stage14_rules_hash": stage14.rules_hash,
        "source_stage14_impact_csv_hash": impact.csv_hash,
        "source_stage14_run_id": stage14.stage14_run_id,
        "source_stage13_schema_version": stage14.stage13_schema_version,
        "source_stage13_manifest_hash": stage14.stage13_manifest_hash,
        "source_stage12_manifest_hash": stage14.stage12_manifest_hash,
        "source_operator_review_hash": operator_review.csv_hash,

        "warning_flag_source": "stage14_impact_csv",

        "created_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "git_commit": git_commit,

        "rule_count_approved": len(rules_payload),
        "rules": rules_payload,
    }

    assert_draft_safety_invariants(draft)

    data = _json_bytes(draft)
    (output_dir / POLICY_DRAFT_FILENAME).write_bytes(data)
    file_hashes[POLICY_DRAFT_FILENAME] = sha256_bytes(data)


def _stage14_rule_hash(raw_rule: Mapping[str, Any]) -> str:
    """Return the Stage 14 rule's stable hash.

    Stage 14 may or may not expose a ``source_stage14_rule_hash`` field
    per rule. When present, pass it through verbatim. When absent,
    derive a content-stable hash over the rule's canonical identity
    tuple so Stage 15 still has a per-rule fingerprint for lineage.
    """

    explicit = raw_rule.get("source_stage14_rule_hash") or raw_rule.get(
        "stage14_rule_hash"
    )
    if isinstance(explicit, str) and explicit.strip():
        return explicit

    canonical = "|".join(
        [
            str(raw_rule.get("rule_id", "")),
            str(raw_rule.get("policy_surface", "")),
            str(raw_rule.get("tier_scope", "")),
            str(raw_rule.get("filter_name", "")),
            str(raw_rule.get("filter_version", "")),
            str(raw_rule.get("filter_label", "")),
            str(raw_rule.get("threshold_version", "")),
            str(raw_rule.get("simulated_action", "")),
            str(raw_rule.get("direction", "")),
        ]
    )
    return sha256_bytes(canonical.encode("utf-8"))


def _approval_timestamp_range(
    approved: tuple[ReconciledRule, ...]
) -> tuple[str | None, str | None]:
    """Earliest/latest reviewed_at_utc across approved rules.

    Returns (None, None) when no approved rules exist. Each value is
    rendered as ISO-8601 UTC matching the operator CSV's original raw
    string (rather than re-serializing the parsed datetime) so the
    output is byte-stable across implementations.
    """

    if not approved:
        return None, None
    times = [
        (r.operator_row.reviewed_at_utc, r.operator_row.reviewed_at_utc_raw)
        for r in approved
        if r.operator_row is not None
    ]
    if not times:
        return None, None
    earliest = min(times, key=lambda t: t[0])[1]
    latest = max(times, key=lambda t: t[0])[1]
    return earliest, latest


def _json_bytes(payload: Any) -> bytes:
    """Stable JSON serialization: sort_keys + indent=2 + trailing newline."""

    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------


def _write_markdown(
    output_dir: Path,
    body: str,
    file_hashes: dict[str, str | None],
) -> None:
    """Markdown is generated by markdown.py and passed in as a string."""

    data = body.encode("utf-8")
    (output_dir / MARKDOWN_FILENAME).write_bytes(data)
    file_hashes[MARKDOWN_FILENAME] = sha256_bytes(data)


# ---------------------------------------------------------------------------
# Run log writer
# ---------------------------------------------------------------------------


def _write_run_log(
    output_dir: Path,
    log_lines: list[str],
    file_hashes: dict[str, str | None],
) -> None:
    text = "\n".join(log_lines)
    if not text.endswith("\n"):
        text += "\n"
    data = text.encode("utf-8")
    (output_dir / RUN_LOG_FILENAME).write_bytes(data)
    file_hashes[RUN_LOG_FILENAME] = sha256_bytes(data)


def _append_log(
    log_lines: list[str],
    now_utc: datetime,
    event: str,
) -> None:
    """Append a timestamped lifecycle event to the run log buffer."""

    iso_now = datetime.now(timezone.utc).isoformat()
    log_lines.append(f"{iso_now} {event}")


# ---------------------------------------------------------------------------
# Manifest writer (atomic, written last)
# ---------------------------------------------------------------------------


def _write_manifest(
    *,
    output_dir: Path,
    stage14: Stage14Artifact,
    impact: ImpactSummary,
    operator_review: OperatorReview,
    reconciliation: ReconciliationResult,
    reviewer_arg: str,
    git_commit: str,
    now_utc: datetime,
    approval_status: str,
    draft_written: bool,
    file_hashes: dict[str, str | None],
) -> Path:
    """Write manifest.json atomically as the last step.

    Atomicity: serialize to bytes, write to a temp file in the same
    directory, then os.replace() to the final name. Means a crash
    mid-write leaves either no manifest or the complete final one.
    """

    approved = reconciliation.approved
    earliest, latest = _approval_timestamp_range(approved)

    manifest: dict[str, Any] = {
        "stage15_schema_version": MANIFEST_SCHEMA_VERSION,
        "stage": 15,
        "approval_status": approval_status,

        "source_stage14_run_path": str(stage14.run_path.resolve()),
        "source_stage14_manifest_hash": stage14.manifest_hash,
        "source_stage14_rules_hash": stage14.rules_hash,
        "source_stage14_impact_csv_hash": impact.csv_hash,
        "source_stage14_run_id": stage14.stage14_run_id,
        "source_stage14_schema_version": stage14.stage14_schema_version,
        "source_stage13_schema_version": stage14.stage13_schema_version,
        "source_stage13_manifest_hash": stage14.stage13_manifest_hash,
        "source_stage12_manifest_hash": stage14.stage12_manifest_hash,
        "source_operator_review_path": str(operator_review.path.resolve()),
        "source_operator_review_hash": operator_review.csv_hash,

        "warning_flag_source": "stage14_impact_csv",

        "reviewer": reviewer_arg,
        "reviewed_at_utc_range": {
            "earliest": earliest,
            "latest": latest,
        },

        "stage14_rule_count": len(stage14.rules),
        "approved_rule_count": len(reconciliation.approved),
        "rejected_rule_count": len(reconciliation.rejected),
        "held_rule_count": len(reconciliation.held),
        "needs_more_data_count": len(reconciliation.needs_more_data),
        "unreviewed_rule_count": len(reconciliation.unreviewed),
        "validation_error_count": len(reconciliation.validation_errors),
        "accounting_total": (
            len(reconciliation.approved)
            + len(reconciliation.rejected)
            + len(reconciliation.held)
            + len(reconciliation.needs_more_data)
            + len(reconciliation.unreviewed)
            + len(reconciliation.validation_errors)
        ),

        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "safe_for_observe_only_wiring": bool(draft_written),
        "enforcement_mode": "NONE",
        "runtime_consumable_scope": "none",

        "output_files": {
            POLICY_DRAFT_FILENAME: file_hashes.get(POLICY_DRAFT_FILENAME),
            OPERATOR_DECISIONS_FILENAME: file_hashes.get(OPERATOR_DECISIONS_FILENAME),
            REJECTED_FILENAME: file_hashes.get(REJECTED_FILENAME),
            HELD_FILENAME: file_hashes.get(HELD_FILENAME),
            NEEDS_MORE_DATA_FILENAME: file_hashes.get(NEEDS_MORE_DATA_FILENAME),
            UNREVIEWED_FILENAME: file_hashes.get(UNREVIEWED_FILENAME),
            APPROVAL_ERRORS_FILENAME: file_hashes.get(APPROVAL_ERRORS_FILENAME),
            MARKDOWN_FILENAME: file_hashes.get(MARKDOWN_FILENAME),
            RUN_LOG_FILENAME: file_hashes.get(RUN_LOG_FILENAME),
        },

        "created_at_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "git_commit": git_commit,
    }

    data = _json_bytes(manifest)
    manifest_path = output_dir / MANIFEST_FILENAME
    tmp_path = output_dir / (MANIFEST_FILENAME + ".tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, manifest_path)
    file_hashes[MANIFEST_FILENAME] = sha256_bytes(data)
    return manifest_path
