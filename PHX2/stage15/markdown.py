"""Stage 15 markdown summary generator.

Renders ``stage15_operator_approval_review.md`` for the run directory.

The markdown is the human-readable surface; the JSON manifest and the
per-bucket CSVs are the machine-readable ones. The spec mandates a
specific structure (Run Metadata, Decision Summary, Warning Flag Source,
Notable Counts, per-bucket tables, Stage 14 Context References,
Safety Surface), so this generator deliberately favors explicit section
ordering over clever abstractions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

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
    MANIFEST_APPROVED,
    MANIFEST_VALIDATION_FAILED,
)
from PHX2.stage15.writer import predicate_summary


def render_markdown(
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
) -> str:
    """Return the markdown body as a single UTF-8 string.

    The writer turns this into bytes and writes it to disk; this
    function never touches the filesystem.
    """

    lines: list[str] = []
    add = lines.append

    total = len(stage14.rules)
    counts = _counts(reconciliation)

    add("# Stage 15 Operator Approval Review")
    add("")

    # ----------------- Run Metadata -----------------
    add("## Run Metadata")
    add(f"- Stage 15 run dir: `{output_dir.resolve()}`")
    add(f"- Stage 14 source run path: `{stage14.run_path.resolve()}`")
    add(f"- Stage 14 manifest hash: `{stage14.manifest_hash}`")
    add(f"- Stage 14 rules hash: `{stage14.rules_hash}`")
    add(f"- Stage 14 impact CSV hash: `{impact.csv_hash}`")
    add(f"- Stage 13 schema version: `{stage14.stage13_schema_version}`")
    add(f"- Stage 12 manifest hash: `{stage14.stage12_manifest_hash}`")
    add(f"- Reviewer: `{reviewer_arg}`")
    add(f"- Created at UTC: `{now_utc.astimezone(timezone.utc).isoformat()}`")
    add(f"- Git commit: `{git_commit}`")
    add(f"- Final status: `{approval_status}`")
    add("")

    # ----------------- Decision Summary -----------------
    add("## Decision Summary")
    add(f"- Total Stage 14 rules: {total}")
    add(f"- Approved: {counts['approved']}")
    add(f"- Rejected: {counts['rejected']}")
    add(f"- Held: {counts['held']}")
    add(f"- Needs more data: {counts['needs_more_data']}")
    add(f"- Unreviewed: {counts['unreviewed']}")
    add(f"- Validation errors: {counts['validation_errors']}")
    add(
        "- Accounting check: "
        f"{counts['approved']} + {counts['rejected']} + {counts['held']} + "
        f"{counts['needs_more_data']} + {counts['unreviewed']} + "
        f"{counts['validation_errors']} = "
        f"{counts['accounting_total']} (Stage 14 rule count: {total})"
    )
    add("")

    # ----------------- Warning Flag Source -----------------
    add("## Warning Flag Source")
    add("- warning_flag_source: `stage14_impact_csv`")
    add(
        "- Note: Stage 15 reads warning_flags from Stage 14's "
        "`impact_summary_by_rule.csv`."
    )
    add(
        "- Note: Stage 15 does not derive, recompute, or interpret "
        "warning flags."
    )
    add(
        "- Note: Any non-empty warning_flags list triggers override "
        "requirements for APPROVE_OBSERVE_ONLY."
    )
    add("")

    # ----------------- Notable Counts and Callouts -----------------
    add("## Notable Counts and Callouts")
    if total > 0 and counts["approved"] == total:
        add("- **All Stage 14 rules approved. Confirm this is intentional.**")
    if counts["unreviewed"] > 0:
        add(
            f"- Unreviewed rule count: {counts['unreviewed']}. Operator may "
            f"want to circle back."
        )
    if counts["validation_errors"] > 0:
        add(
            "- **Validation errors prevented policy draft. See "
            "`approval_validation_errors.csv`.**"
        )
    override_rules = [
        r
        for r in reconciliation.approved
        if r.operator_row is not None and r.operator_row.override_warning_flags
    ]
    if override_rules:
        ids = ", ".join(f"`{r.rule.rule_id}`" for r in override_rules)
        add(
            f"- Approved rules with `override_warning_flags=true`: "
            f"{len(override_rules)} ({ids})"
        )
    if not (
        (total > 0 and counts["approved"] == total)
        or counts["unreviewed"] > 0
        or counts["validation_errors"] > 0
        or override_rules
    ):
        add("- No callouts.")
    add("")

    # ----------------- Per-bucket tables -----------------
    _render_approved_table(add, reconciliation.approved, impact.row_by_rule)
    _render_bucket_table(add, "Rejected Rules", reconciliation.rejected)
    _render_bucket_table(add, "Held Rules", reconciliation.held)
    _render_bucket_table(
        add, "Needs More Data Rules", reconciliation.needs_more_data
    )
    _render_unreviewed_table(add, reconciliation.unreviewed)
    _render_validation_errors_table(add, reconciliation.validation_failures)

    # ----------------- Stage 14 Context References -----------------
    add("## Stage 14 Context References")
    stage14_run = stage14.run_path
    context_files = [
        "stage14_shadow_policy_review.md",
        "impact_summary_by_rule.csv",
        "would_have_blocked_winners.csv",
        "saved_noise_simulated.csv",
    ]
    for name in context_files:
        candidate = stage14_run / name
        suffix = "" if candidate.exists() else " *(not present in source run)*"
        add(f"- `{name}`{suffix}")
    add("")
    add(
        "Note: These context files were not used to derive new Stage 15 "
        "policy logic. warning_flags came directly from Stage 14 "
        "`impact_summary_by_rule.csv`."
    )
    add("")

    # ----------------- Safety Surface -----------------
    add("## Safety Surface")
    add("- runtime_consumable: false")
    add("- observe_only_runtime_consumable: false")
    add("- hard_block_allowed: false")
    add("- safe_for_live_enforcement: false")
    add("- safe_for_hard_blocking: false")
    safe_observe = "true" if approval_status == MANIFEST_APPROVED else "false"
    add(
        f"- safe_for_observe_only_wiring: {safe_observe} "
        f"(true only if draft written)"
    )
    add("- enforcement_mode: NONE")
    add("")
    add(
        "Final note: This artifact is NOT consumed by runtime. Stage 16 "
        "must produce a derivative observe-only runtime artifact."
    )
    add("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def _render_approved_table(
    add,
    approved: tuple[ReconciledRule, ...],
    impact_rows: Mapping[str, Mapping[str, str]],
) -> None:
    add("## Approved Rules")
    if not approved:
        add("_No approved rules._")
        add("")
        return
    add(
        "| rule_id | predicate | warning_flags | override_used | "
        "operator_reason | Stage 14 impact |"
    )
    add("| --- | --- | --- | --- | --- | --- |")
    for r in approved:
        op = r.operator_row
        impact_row = impact_rows.get(r.rule.rule_id, {})
        impact_snippet = _impact_snippet(impact_row)
        reason_snippet = _snippet(op.operator_reason if op else "")
        flags = ";".join(r.warning_flags) if r.warning_flags else ""
        override_used = (
            "true"
            if op and op.override_warning_flags
            else "false"
        )
        add(
            f"| `{r.rule.rule_id}` | `{predicate_summary(r.rule.predicate)}` | "
            f"`{flags}` | {override_used} | {reason_snippet} | "
            f"{impact_snippet} |"
        )
    add("")


def _render_bucket_table(
    add,
    title: str,
    bucket: tuple[ReconciledRule, ...],
) -> None:
    add(f"## {title}")
    if not bucket:
        add(f"_No {title.lower()}._")
        add("")
        return
    add("| rule_id | predicate | operator_reason | reviewed_at_utc | notes |")
    add("| --- | --- | --- | --- | --- |")
    for r in bucket:
        op = r.operator_row
        add(
            f"| `{r.rule.rule_id}` | `{predicate_summary(r.rule.predicate)}` | "
            f"{_snippet(op.operator_reason if op else '')} | "
            f"`{op.reviewed_at_utc_raw if op else ''}` | "
            f"{_snippet(op.notes if op else '')} |"
        )
    add("")


def _render_unreviewed_table(
    add,
    unreviewed: tuple[ReconciledRule, ...],
) -> None:
    add("## Unreviewed Rules")
    if not unreviewed:
        add("_No unreviewed rules._")
        add("")
        return
    add("| rule_id | predicate_summary | warning_flags |")
    add("| --- | --- | --- |")
    for r in unreviewed:
        flags = ";".join(r.warning_flags) if r.warning_flags else ""
        add(
            f"| `{r.rule.rule_id}` | `{predicate_summary(r.rule.predicate)}` | "
            f"`{flags}` |"
        )
    add("")


def _render_validation_errors_table(
    add,
    failures: tuple[ValidationFailure, ...],
) -> None:
    add("## Validation Errors")
    if not failures:
        add("_No validation errors._")
        add("")
        return
    add(
        "| rule_id | operator_decision | error_code | error_message | "
        "source_csv_row_number |"
    )
    add("| --- | --- | --- | --- | --- |")
    for f in failures:
        add(
            f"| `{f.rule_id}` | {f.operator_decision} | {f.error_code} | "
            f"{_snippet(f.error_message)} | {f.source_csv_row_number} |"
        )
    add("")


def _snippet(text: str, *, max_len: int = 120) -> str:
    """Markdown-safe single-line snippet of an operator reason / note."""

    if text is None:
        return ""
    flat = " ".join(text.split())
    if len(flat) > max_len:
        flat = flat[: max_len - 1] + "..."
    # Escape pipes so they don't break the table.
    return flat.replace("|", "\\|")


def _impact_snippet(row: Mapping[str, str]) -> str:
    """Compact Stage 14 impact summary cell for the approved-rules table."""

    if not row:
        return ""
    parts = []
    for key in (
        "n_matched",
        "n_simulated_blocks",
        "n_blocked_winners_2x",
    ):
        if key in row:
            parts.append(f"{key}={row[key]}")
    return ", ".join(parts)


def _counts(reconciliation: ReconciliationResult) -> dict[str, int]:
    counts = {
        "approved": len(reconciliation.approved),
        "rejected": len(reconciliation.rejected),
        "held": len(reconciliation.held),
        "needs_more_data": len(reconciliation.needs_more_data),
        "unreviewed": len(reconciliation.unreviewed),
        "validation_errors": len(reconciliation.validation_errors),
    }
    counts["accounting_total"] = sum(counts.values())
    return counts
