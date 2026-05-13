"""Stage 15 PHASE 5 markdown summary tests.

The markdown surface is human-facing; the structure is mandated by spec.
These tests run the CLI end-to-end and inspect
``stage15_operator_approval_review.md`` for the required sections and
callouts.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.scripts.run_stage15_operator_approval import main as cli_main
from PHX2.stage15.writer import MARKDOWN_FILENAME
from PHX2.tests.stage15.fixtures.builders import (
    DEFAULT_REVIEWER,
    approve_row,
    make_operator_csv,
    make_stage14_run,
    reject_row,
)


def _run_cli(stage14, operator, output) -> int:
    return cli_main(
        [
            "--stage14-run-path",
            str(stage14),
            "--operator-review",
            str(operator),
            "--output-dir",
            str(output),
            "--reviewer",
            DEFAULT_REVIEWER,
        ]
    )


def _md(output: Path) -> str:
    return (output / MARKDOWN_FILENAME).read_text(encoding="utf-8")


def test_markdown_has_required_sections(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    _run_cli(stage14_run, good_operator_csv, out)
    md = _md(out)

    required = (
        "# Stage 15 Operator Approval Review",
        "## Run Metadata",
        "## Decision Summary",
        "## Warning Flag Source",
        "## Notable Counts and Callouts",
        "## Approved Rules",
        "## Rejected Rules",
        "## Held Rules",
        "## Needs More Data Rules",
        "## Unreviewed Rules",
        "## Validation Errors",
        "## Stage 14 Context References",
        "## Safety Surface",
    )
    for section in required:
        assert section in md, f"missing section {section!r}"


def test_markdown_warning_flag_source_note(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    _run_cli(stage14_run, good_operator_csv, out)
    md = _md(out)
    assert "warning_flag_source: `stage14_impact_csv`" in md
    assert "does not derive, recompute, or interpret" in md


def test_markdown_safety_surface_note(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    _run_cli(stage14_run, good_operator_csv, out)
    md = _md(out)
    assert "runtime_consumable: false" in md
    assert "observe_only_runtime_consumable: false" in md
    assert "hard_block_allowed: false" in md
    assert "enforcement_mode: NONE" in md
    assert "NOT consumed by runtime" in md
    assert "Stage 16 must produce a derivative observe-only" in md


def test_markdown_all_approved_callout(tmp_path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row("shadow_rule_default_aaaa", reason="ok", override=True),
            approve_row("shadow_rule_default_bbbb"),
        ),
    )
    out = tmp_path / "out"
    _run_cli(stage14, op_csv, out)
    md = _md(out)
    assert "All Stage 14 rules approved" in md
    assert "Confirm this is intentional" in md


def test_markdown_unreviewed_callout(tmp_path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=(approve_row("shadow_rule_default_bbbb"),))
    out = tmp_path / "out"
    _run_cli(stage14, op_csv, out)
    md = _md(out)
    assert "Unreviewed rule count" in md


def test_markdown_validation_failed_callout(tmp_path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa", reason="", override=False
            ),
        ),
    )
    out = tmp_path / "out"
    _run_cli(stage14, op_csv, out)
    md = _md(out)
    assert "Validation errors prevented policy draft" in md
    assert "approval_validation_errors.csv" in md


def test_markdown_override_callout(tmp_path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa",
                reason="override path exercised",
                override=True,
            ),
            approve_row("shadow_rule_default_bbbb"),
        ),
    )
    out = tmp_path / "out"
    _run_cli(stage14, op_csv, out)
    md = _md(out)
    assert "override_warning_flags=true" in md
    assert "shadow_rule_default_aaaa" in md


def test_markdown_final_status_reflects_clean_run(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    _run_cli(stage14_run, good_operator_csv, out)
    md = _md(out)
    assert "Final status: `APPROVED_DRAFT_WRITTEN`" in md


def test_markdown_final_status_reflects_validation_failure(tmp_path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa", reason="", override=False
            ),
        ),
    )
    out = tmp_path / "out"
    _run_cli(stage14, op_csv, out)
    md = _md(out)
    assert "Final status: `VALIDATION_FAILED`" in md
    assert "safe_for_observe_only_wiring: false" in md


def test_markdown_lists_stage14_context_files(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """Markdown enumerates the optional Stage 14 context file names
    and marks them as present/missing relative to the source run."""

    out = tmp_path / "out"
    _run_cli(stage14_run, good_operator_csv, out)
    md = _md(out)
    assert "stage14_shadow_policy_review.md" in md
    # The default fixture doesn't emit context files; markdown should
    # tag them as missing.
    assert "*(not present in source run)*" in md


def test_markdown_decision_summary_accounting(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    _run_cli(stage14_run, good_operator_csv, out)
    md = _md(out)
    assert "Total Stage 14 rules: 2" in md
    assert "Approved: 2" in md
    assert "Stage 14 rule count: 2" in md
