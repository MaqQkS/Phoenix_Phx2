"""Stage 15 PHASE 7 edge case tests.

Spec-mandated edge cases:
  * Stage 14 with zero rules
  * Operator CSV with zero rows (header only)
  * All rules approved
  * All rules rejected
  * BOM-prefixed operator CSV
  * Quoted commas/newlines in operator fields
  * Future timestamp +59m allowed / +61m rejected
  * override=true on unflagged rule
  * Unknown future warning flag passthrough
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from PHX2.scripts.run_stage15_operator_approval import (
    EXIT_LOAD_TIME_FAIL,
    EXIT_OK,
    main as cli_main,
)
from PHX2.stage15.writer import (
    APPROVAL_ERRORS_FILENAME,
    MANIFEST_FILENAME,
    POLICY_DRAFT_FILENAME,
    REJECTED_FILENAME,
    UNREVIEWED_FILENAME,
)
from PHX2.tests.stage15.fixtures.builders import (
    DEFAULT_REVIEWED_AT,
    DEFAULT_REVIEWER,
    approve_row,
    make_operator_csv,
    make_stage14_run,
    reject_row,
)


def _run(stage14, operator, output) -> int:
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


# ---------------------------------------------------------------------------
# Zero rules / zero operator rows
# ---------------------------------------------------------------------------


def test_stage14_with_zero_rules(tmp_path: Path) -> None:
    stage14 = make_stage14_run(tmp_path / "s14", rules=())
    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=())  # header only
    out = tmp_path / "out"
    rc = _run(stage14, op_csv, out)
    assert rc == EXIT_OK

    draft = json.loads((out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    assert draft["rules"] == []
    assert draft["rule_count_approved"] == 0

    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["stage14_rule_count"] == 0
    assert manifest["approved_rule_count"] == 0
    assert manifest["accounting_total"] == 0


def test_operator_csv_with_zero_rows(
    tmp_path: Path, stage14_run: Path
) -> None:
    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=())
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK

    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["unreviewed_rule_count"] == 2
    assert manifest["approved_rule_count"] == 0

    # Markdown should flag unreviewed.
    md = (out / "stage15_operator_approval_review.md").read_text(encoding="utf-8")
    assert "Unreviewed rule count: 2" in md


# ---------------------------------------------------------------------------
# All approved / all rejected
# ---------------------------------------------------------------------------


def test_all_rules_approved_emits_callout(
    tmp_path: Path, stage14_run: Path
) -> None:
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa", reason="ok", override=True
            ),
            approve_row("shadow_rule_default_bbbb"),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK

    md = (out / "stage15_operator_approval_review.md").read_text(encoding="utf-8")
    assert "All Stage 14 rules approved" in md
    assert "Confirm this is intentional" in md


def test_all_rules_rejected_emits_empty_draft(
    tmp_path: Path, stage14_run: Path
) -> None:
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            reject_row("shadow_rule_default_aaaa", reason="bad rule"),
            reject_row("shadow_rule_default_bbbb", reason="also bad"),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK

    draft = json.loads((out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    assert draft["rules"] == []
    rejected = (out / REJECTED_FILENAME).read_text(encoding="utf-8").splitlines()
    # Header + 2 rejected rules.
    assert len(rejected) == 3


# ---------------------------------------------------------------------------
# Encoding / quoting edge cases
# ---------------------------------------------------------------------------


def test_bom_operator_csv_handled(tmp_path: Path, stage14_run: Path) -> None:
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa", reason="ok", override=True
            ),
            approve_row("shadow_rule_default_bbbb"),
        ),
        bom=True,
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK


def test_quoted_commas_and_newlines_in_operator_fields(
    tmp_path: Path, stage14_run: Path
) -> None:
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa",
                reason="multi, line\nreason with commas",
                override=True,
                notes='notes with "quotes" and, commas',
            ),
            approve_row("shadow_rule_default_bbbb"),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK

    draft = json.loads((out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    aaaa = next(r for r in draft["rules"] if r["rule_id"] == "shadow_rule_default_aaaa")
    assert "multi, line" in aaaa["operator_reason"]
    assert "reason with commas" in aaaa["operator_reason"]


# ---------------------------------------------------------------------------
# Future-timestamp window (L20 boundary)
# ---------------------------------------------------------------------------


def test_future_timestamp_plus_59m_accepted(tmp_path: Path, stage14_run: Path) -> None:
    """L20 boundary: +59m from now should pass (tolerance is +1h)."""

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=59)).isoformat()
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row("shadow_rule_default_bbbb", reviewed_at=future),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK


def test_future_timestamp_plus_61m_rejected(tmp_path: Path, stage14_run: Path) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=61)).isoformat()
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row("shadow_rule_default_bbbb", reviewed_at=future),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_LOAD_TIME_FAIL


# ---------------------------------------------------------------------------
# Override on unflagged rule
# ---------------------------------------------------------------------------


def test_override_true_on_unflagged_rule_is_allowed(
    tmp_path: Path, stage14_run: Path
) -> None:
    """override=true on the unflagged default rule is informational,
    not an error. Approval still succeeds."""

    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa", reason="flagged", override=True
            ),
            approve_row(
                "shadow_rule_default_bbbb",
                reason="defensive override",
                override=True,
            ),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_OK

    draft = json.loads((out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    bbbb = next(r for r in draft["rules"] if r["rule_id"] == "shadow_rule_default_bbbb")
    assert bbbb["override_warning_flags"] is True
    assert bbbb["warning_flags"] == []


# ---------------------------------------------------------------------------
# Unknown / future warning flag passthrough
# ---------------------------------------------------------------------------


def test_unknown_future_warning_flag_passthrough(tmp_path: Path) -> None:
    stage14 = make_stage14_run(
        tmp_path / "s14",
        rules=(
            {
                "rule_id": "rule_future",
                "tier_scope": "T2",
                "filter_name": "fee_gate",
                "filter_version": "v1",
                "filter_label": "x",
                "threshold_version": "v1",
                "warning_flags": "future_flag_we_havent_invented_yet",
            },
        ),
    )
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row(
                "rule_future",
                reason="accepted unknown flag",
                override=True,
            ),
        ),
    )
    out = tmp_path / "out"
    rc = _run(stage14, op_csv, out)
    assert rc == EXIT_OK

    draft = json.loads((out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    assert draft["rules"][0]["warning_flags"] == [
        "future_flag_we_havent_invented_yet"
    ]


# ---------------------------------------------------------------------------
# Output dir non-empty rejection (Tier 1)
# ---------------------------------------------------------------------------


def test_output_dir_non_empty_rejected(
    tmp_path: Path, stage14_run: Path, good_operator_csv: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "leftover.txt").write_text("x", encoding="utf-8")
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc != EXIT_OK
    assert (out / "leftover.txt").read_text(encoding="utf-8") == "x"
    assert not (out / MANIFEST_FILENAME).exists()


# ---------------------------------------------------------------------------
# Predicate summary in approved-rules markdown matches spec format
# ---------------------------------------------------------------------------


def test_predicate_summary_spec_format(
    tmp_path: Path, stage14_run: Path, good_operator_csv: Path
) -> None:
    out = tmp_path / "out"
    _run(stage14_run, good_operator_csv, out)
    md = (out / "stage15_operator_approval_review.md").read_text(encoding="utf-8")
    # Spec example: T2|fee_gate|fee_gate_v1_no_bribes|SCAM_LIKELY
    assert "T2|fee_gate|fee_gate_v1_no_bribes|SCAM_LIKELY" in md
