"""Stage 15 PHASE 4 writer tests.

Drives the full CLI (load-time -> reconciliation -> write-time) and
asserts the three-tier exit discipline and output-schema invariants:

  * Clean run: all outputs + manifest APPROVED_DRAFT_WRITTEN + exit 0
  * Approval-time failure: non-draft outputs + manifest VALIDATION_FAILED
    + NO approved_observe_only_policy_draft.json + non-zero exit
  * Load-time failure: stage15_run.log only (if writable), no manifest,
    no draft, non-zero exit
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.scripts.run_stage15_operator_approval import (
    EXIT_APPROVAL_TIME_FAIL,
    EXIT_LOAD_TIME_FAIL,
    EXIT_OK,
    main as cli_main,
)
from PHX2.stage15.writer import (
    APPROVAL_ERRORS_FILENAME,
    HELD_FILENAME,
    MANIFEST_FILENAME,
    MARKDOWN_FILENAME,
    NEEDS_MORE_DATA_FILENAME,
    OPERATOR_DECISIONS_FILENAME,
    POLICY_DRAFT_FILENAME,
    REJECTED_FILENAME,
    RUN_LOG_FILENAME,
    UNREVIEWED_FILENAME,
)
from PHX2.tests.stage15.fixtures.builders import (
    DEFAULT_REVIEWER,
    approve_row,
    hold_row,
    make_operator_csv,
    make_stage14_run,
    needs_more_data_row,
    reject_row,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _run_cli(
    *,
    stage14_run: Path,
    operator_csv: Path,
    output_dir: Path,
    reviewer: str = DEFAULT_REVIEWER,
) -> int:
    return cli_main(
        [
            "--stage14-run-path",
            str(stage14_run),
            "--operator-review",
            str(operator_csv),
            "--output-dir",
            str(output_dir),
            "--reviewer",
            reviewer,
        ]
    )


def _all_files(output_dir: Path) -> set[str]:
    return {p.name for p in output_dir.iterdir() if p.is_file()}


# ---------------------------------------------------------------------------
# Clean-run output suite
# ---------------------------------------------------------------------------


def test_clean_run_emits_all_outputs(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    rc = _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    assert rc == EXIT_OK
    expected = {
        POLICY_DRAFT_FILENAME,
        OPERATOR_DECISIONS_FILENAME,
        REJECTED_FILENAME,
        HELD_FILENAME,
        NEEDS_MORE_DATA_FILENAME,
        UNREVIEWED_FILENAME,
        APPROVAL_ERRORS_FILENAME,
        MARKDOWN_FILENAME,
        RUN_LOG_FILENAME,
        MANIFEST_FILENAME,
    }
    assert expected.issubset(_all_files(output_dir))


def test_clean_run_manifest_status(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    manifest = json.loads((output_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "APPROVED_DRAFT_WRITTEN"
    assert manifest["safe_for_observe_only_wiring"] is True
    assert manifest["runtime_consumable"] is False
    assert manifest["observe_only_runtime_consumable"] is False
    assert manifest["hard_block_allowed"] is False
    assert manifest["safe_for_live_enforcement"] is False
    assert manifest["safe_for_hard_blocking"] is False
    assert manifest["enforcement_mode"] == "NONE"
    assert manifest["runtime_consumable_scope"] == "none"
    assert manifest["warning_flag_source"] == "stage14_impact_csv"


def test_clean_run_policy_draft_safety_flags(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    draft = json.loads(
        (output_dir / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8")
    )
    assert draft["schema_version"] == "stage15_approval_draft_v0"
    assert draft["approval_status"] == "OPERATOR_APPROVED_DRAFT"
    assert draft["enforcement_mode"] == "NONE"
    assert draft["intended_action_set"] == ["LOG_WOULD_BLOCK"]
    assert draft["runtime_consumable"] is False
    assert draft["observe_only_runtime_consumable"] is False
    assert draft["hard_block_allowed"] is False
    assert draft["safe_for_live_enforcement"] is False
    assert draft["safe_for_hard_blocking"] is False
    assert draft["safe_for_observe_only_wiring"] is True
    assert draft["warning_flag_source"] == "stage14_impact_csv"
    assert draft["approved_by_human"] is True
    assert draft["reviewer"] == DEFAULT_REVIEWER
    assert len(draft["rules"]) == draft["rule_count_approved"] == 2


def test_clean_run_per_rule_safety_flags(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    draft = json.loads(
        (output_dir / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8")
    )
    for rule in draft["rules"]:
        assert rule["hard_block_allowed"] is False
        assert rule["intended_action_if_wired"] == "LOG_WOULD_BLOCK"
        assert rule["operator_decision"] == "APPROVE_OBSERVE_ONLY"


def test_clean_run_accounting_invariant_in_manifest(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    manifest = json.loads((output_dir / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    total = (
        manifest["approved_rule_count"]
        + manifest["rejected_rule_count"]
        + manifest["held_rule_count"]
        + manifest["needs_more_data_count"]
        + manifest["unreviewed_rule_count"]
        + manifest["validation_error_count"]
    )
    assert total == manifest["accounting_total"]
    assert total == manifest["stage14_rule_count"]


def test_clean_run_empty_approval_errors_csv(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    rows = (output_dir / APPROVAL_ERRORS_FILENAME).read_text(encoding="utf-8").splitlines()
    # Header only.
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Mixed-bucket run
# ---------------------------------------------------------------------------


def test_mixed_buckets_emit_correct_csv_contents(tmp_path: Path) -> None:
    """One approved, one rejected, one held, one needs-more-data,
    one unreviewed -- exercises every bucket's CSV writer."""

    stage14 = make_stage14_run(
        tmp_path / "s14",
        rules=tuple(
            {
                "rule_id": f"rule_{i}",
                "tier_scope": "T2",
                "filter_name": "fee_gate",
                "filter_version": "v1",
                "filter_label": "x",
                "threshold_version": "v1",
                "warning_flags": "",
            }
            for i in range(5)
        ),
    )
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row("rule_0"),
            reject_row("rule_1", reason="don't want"),
            hold_row("rule_2", reason="defer"),
            needs_more_data_row("rule_3"),
            # rule_4 -> UNREVIEWED
        ),
    )
    out = tmp_path / "out"
    rc = _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    assert rc == EXIT_OK

    rejected = (out / REJECTED_FILENAME).read_text(encoding="utf-8").splitlines()
    assert any("rule_1" in line for line in rejected)
    held = (out / HELD_FILENAME).read_text(encoding="utf-8").splitlines()
    assert any("rule_2" in line for line in held)
    nmd = (out / NEEDS_MORE_DATA_FILENAME).read_text(encoding="utf-8").splitlines()
    assert any("rule_3" in line for line in nmd)
    unrev = (out / UNREVIEWED_FILENAME).read_text(encoding="utf-8").splitlines()
    assert any("rule_4" in line for line in unrev)


def test_operator_review_decisions_csv_has_final_bucket_column(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    text = (output_dir / OPERATOR_DECISIONS_FILENAME).read_text(encoding="utf-8")
    header = text.splitlines()[0]
    assert "final_bucket" in header
    # rule_existed_in_stage14 must NOT appear (spec explicit prohibition).
    assert "rule_existed_in_stage14" not in header


def test_unreviewed_csv_has_predicate_summary(
    tmp_path: Path,
) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    # Provide only one of the two default rules so the other is UNREVIEWED.
    make_operator_csv(op_csv, rows=(approve_row("shadow_rule_default_bbbb"),))
    out = tmp_path / "out"
    _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    text = (out / UNREVIEWED_FILENAME).read_text(encoding="utf-8")
    # Format: tier_scope|filter_name|filter_version|filter_label
    assert "T2|fee_gate|fee_gate_v1_no_bribes|SCAM_LIKELY" in text


# ---------------------------------------------------------------------------
# Approval-time failure (Tier 3)
# ---------------------------------------------------------------------------


def test_validation_failure_suppresses_draft(tmp_path: Path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14")
    op_csv = tmp_path / "op.csv"
    # Rule aaaa is flagged; approve without override -> A01 + A02.
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa", reason="", override=False
            ),
            approve_row("shadow_rule_default_bbbb"),
        ),
    )
    out = tmp_path / "out"
    rc = _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    assert rc == EXIT_APPROVAL_TIME_FAIL

    # Manifest exists with VALIDATION_FAILED.
    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "VALIDATION_FAILED"
    assert manifest["safe_for_observe_only_wiring"] is False

    # Draft must NOT exist.
    assert not (out / POLICY_DRAFT_FILENAME).exists()

    # Non-draft outputs exist (markdown, run log, all bucket CSVs).
    for required in (
        OPERATOR_DECISIONS_FILENAME,
        REJECTED_FILENAME,
        HELD_FILENAME,
        NEEDS_MORE_DATA_FILENAME,
        UNREVIEWED_FILENAME,
        APPROVAL_ERRORS_FILENAME,
        MARKDOWN_FILENAME,
        RUN_LOG_FILENAME,
    ):
        assert (out / required).exists()


def test_validation_failure_csv_carries_error_rows(tmp_path: Path) -> None:
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
    _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    text = (out / APPROVAL_ERRORS_FILENAME).read_text(encoding="utf-8")
    lines = text.splitlines()
    assert "A01" in text
    assert "A02" in text
    # Header + at least the two A-codes.
    assert len(lines) >= 3


def test_validation_failure_manifest_lists_validation_error_count(
    tmp_path: Path,
) -> None:
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
    _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["validation_error_count"] == 1


# ---------------------------------------------------------------------------
# Load-time failure (Tier 2)
# ---------------------------------------------------------------------------


def test_load_time_failure_writes_no_manifest(tmp_path: Path) -> None:
    """L05: Stage 14 manifest with safe_for_live_policy_consumption=true
    fails L05 -> Tier 2: log only, no manifest."""

    stage14 = make_stage14_run(tmp_path / "s14", safe_for_live=True)
    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=(approve_row("shadow_rule_default_bbbb"),))
    out = tmp_path / "out"
    rc = _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    assert rc == EXIT_LOAD_TIME_FAIL
    assert not (out / MANIFEST_FILENAME).exists()
    assert not (out / POLICY_DRAFT_FILENAME).exists()
    # Log may exist (best-effort).
    if (out / RUN_LOG_FILENAME).exists():
        text = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
        assert "L05" in text or "load-time" in text


def test_load_time_failure_emits_no_csv_outputs(tmp_path: Path) -> None:
    """A load-time failure must not emit any bucket CSV or draft."""

    stage14 = make_stage14_run(tmp_path / "s14", runtime_consumable=True)
    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=(approve_row("shadow_rule_default_bbbb"),))
    out = tmp_path / "out"
    _run_cli(stage14_run=stage14, operator_csv=op_csv, output_dir=out)
    forbidden = {
        POLICY_DRAFT_FILENAME,
        OPERATOR_DECISIONS_FILENAME,
        REJECTED_FILENAME,
        HELD_FILENAME,
        NEEDS_MORE_DATA_FILENAME,
        UNREVIEWED_FILENAME,
        APPROVAL_ERRORS_FILENAME,
        MARKDOWN_FILENAME,
        MANIFEST_FILENAME,
    }
    actual = _all_files(out)
    overlap = forbidden & actual
    assert overlap == set(), f"Tier 2 should emit log only; found {overlap!r}"


# ---------------------------------------------------------------------------
# Output-dir failure (Tier 1)
# ---------------------------------------------------------------------------


def test_output_dir_non_empty_exits_nonzero(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "leftover.txt").write_text("x", encoding="utf-8")
    rc = _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=out,
    )
    assert rc != EXIT_OK
    assert not (out / MANIFEST_FILENAME).exists()
    # leftover file stayed put (no destructive cleanup).
    assert (out / "leftover.txt").exists()


# ---------------------------------------------------------------------------
# Spec-prohibited output values
# ---------------------------------------------------------------------------


def test_no_alternate_action_values_appear_in_draft(
    tmp_path: Path,
    stage14_run: Path,
    good_operator_csv: Path,
) -> None:
    output_dir = tmp_path / "stage15_out"
    _run_cli(
        stage14_run=stage14_run,
        operator_csv=good_operator_csv,
        output_dir=output_dir,
    )
    text = (output_dir / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8")
    for forbidden in (
        '"HARD_BLOCK"',
        '"SOFT_BLOCK"',
        '"ENFORCE"',
        '"runtime_consumable": true',
        '"hard_block_allowed": true',
        '"safe_for_live_enforcement": true',
        '"safe_for_hard_blocking": true',
        '"observe_only_runtime_consumable": true',
    ):
        assert forbidden not in text, f"forbidden token {forbidden!r} in draft"
