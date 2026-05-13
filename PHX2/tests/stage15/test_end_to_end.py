"""Stage 15 PHASE 7/8 end-to-end smoke test.

Single happy-path run through the full CLI + every output file. Acts
as a tripwire test: any future regression that breaks the wiring
between loaders / reconciler / writer / markdown will surface here
before more targeted tests have a chance to fire.
"""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.scripts.run_stage15_operator_approval import (
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


def test_end_to_end_realistic_mixed_run(tmp_path: Path) -> None:
    """One run, several rules, each in a different bucket. Verify:

      * exit 0
      * every output file exists and parses
      * manifest accounts for every Stage 14 rule
      * policy draft carries only approved rules
      * per-rule safety flags are all locked down
    """

    rule_specs = (
        {
            "rule_id": "rule_approve_clean",
            "tier_scope": "T2",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "CLEAN",
            "threshold_version": "thresholds_v0_observe_only",
            "warning_flags": "",
        },
        {
            "rule_id": "rule_approve_flagged",
            "tier_scope": "T1",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "SCAM_LIKELY",
            "threshold_version": "thresholds_v0_observe_only",
            "warning_flags": "small_n_rule;excessive_block_rate",
        },
        {
            "rule_id": "rule_reject",
            "tier_scope": "T3",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "MAYBE",
            "threshold_version": "thresholds_v0_observe_only",
            "warning_flags": "",
        },
        {
            "rule_id": "rule_hold",
            "tier_scope": "T2",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "CLEAN",
            "threshold_version": "thresholds_v0_observe_only",
            "warning_flags": "",
        },
        {
            "rule_id": "rule_needs_more",
            "tier_scope": "T2",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "MAYBE",
            "threshold_version": "thresholds_v0_observe_only",
            "warning_flags": "high_winners_blocked_rate",
        },
        {
            "rule_id": "rule_unreviewed",
            "tier_scope": "T1",
            "filter_name": "fee_gate",
            "filter_version": "fee_gate_v1_no_bribes",
            "filter_label": "EDGE",
            "threshold_version": "thresholds_v0_observe_only",
            "warning_flags": "",
        },
    )
    stage14 = make_stage14_run(tmp_path / "s14", rules=rule_specs)
    op_csv = tmp_path / "op.csv"
    make_operator_csv(
        op_csv,
        rows=(
            approve_row("rule_approve_clean"),
            approve_row(
                "rule_approve_flagged",
                reason="reviewed under observe-only program",
                override=True,
            ),
            reject_row("rule_reject", reason="confirmed false positive"),
            hold_row("rule_hold", reason="revisit after next data drop"),
            needs_more_data_row("rule_needs_more"),
            # rule_unreviewed has no operator row
        ),
    )

    out = tmp_path / "out"
    rc = cli_main(
        [
            "--stage14-run-path",
            str(stage14),
            "--operator-review",
            str(op_csv),
            "--output-dir",
            str(out),
            "--reviewer",
            DEFAULT_REVIEWER,
        ]
    )
    assert rc == EXIT_OK

    # Every artifact exists.
    for filename in (
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
    ):
        assert (out / filename).exists(), f"missing artifact: {filename}"

    # Manifest accounting.
    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "APPROVED_DRAFT_WRITTEN"
    assert manifest["stage14_rule_count"] == 6
    assert manifest["approved_rule_count"] == 2
    assert manifest["rejected_rule_count"] == 1
    assert manifest["held_rule_count"] == 1
    assert manifest["needs_more_data_count"] == 1
    assert manifest["unreviewed_rule_count"] == 1
    assert manifest["validation_error_count"] == 0
    assert manifest["accounting_total"] == 6
    assert manifest["warning_flag_source"] == "stage14_impact_csv"
    assert manifest["safe_for_observe_only_wiring"] is True
    assert manifest["hard_block_allowed"] is False
    assert manifest["enforcement_mode"] == "NONE"

    # Policy draft.
    draft = json.loads(
        (out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8")
    )
    assert draft["rule_count_approved"] == 2
    rule_ids_in_draft = {r["rule_id"] for r in draft["rules"]}
    assert rule_ids_in_draft == {"rule_approve_clean", "rule_approve_flagged"}
    for rule in draft["rules"]:
        assert rule["hard_block_allowed"] is False
        assert rule["intended_action_if_wired"] == "LOG_WOULD_BLOCK"
        assert rule["operator_decision"] == "APPROVE_OBSERVE_ONLY"

    # Markdown carries all sections.
    md = (out / MARKDOWN_FILENAME).read_text(encoding="utf-8")
    for section in (
        "# Stage 15 Operator Approval Review",
        "## Run Metadata",
        "## Decision Summary",
        "## Warning Flag Source",
        "## Safety Surface",
    ):
        assert section in md
