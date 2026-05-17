"""Stage 20.4 handoff doc -- manual tag recommendation tests.

The rendered handoff doc MUST:

  * Mention the exact ``git tag -a stage-20-closed -m "..."`` command.
  * State that Stage 20.4 will not create the tag itself.
  * NEVER mention "auto-tag" or "automatically create tag" anywhere.

This is a small dedicated test file (separate from the broader
``test_handoff_writer.py``) so that the manual-tag invariant is
easy to find and easy to flip into a regression-tracking signal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import handoff_writer as hw
from PHX2.stage20.closure.models import (
    ClosureInputConfig,
    OperatorTestResults,
)


def _make_inputs(tmp_path: Path) -> ClosureInputConfig:
    op = OperatorTestResults(
        test_command="pytest -q",
        run1_passed=1, run1_failed=0, run1_errors=0,
        run2_passed=1, run2_failed=0, run2_errors=0,
        both_runs_match=True, all_green=True,
    )
    return ClosureInputConfig(
        stage20_1_commit_sha="a" * 40,
        stage20_2_commit_sha="b" * 40,
        stage20_3_commit_sha="c" * 40,
        stage20_2_run_dir=tmp_path / "s2",
        stage20_3_run_dir=tmp_path / "s3",
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "out",
        operator_test_results=op,
        generated_at_utc="2026-05-16T12:34:56Z",
    )


def test_handoff_doc_contains_manual_tag_command(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert (
        'git tag -a stage-20-closed -m "PHX2 Stage 20 closed after '
        '20.4 audit"' in text
    )


def test_handoff_doc_states_stage20_4_will_not_create_tag(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert "Stage 20.4 will not create this tag." in text


def test_handoff_doc_says_operator_may_create_tag(tmp_path: Path):
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    assert "the operator MAY" in text
    assert "create the annotated tag manually" in text


@pytest.mark.parametrize("forbidden_phrase", [
    "auto-tag",
    "automatically create tag",
    "automatically creates tag",
    "auto tag",
    "auto-create tag",
])
def test_handoff_doc_does_not_mention_auto_tagging(
    tmp_path: Path, forbidden_phrase,
):
    """The handoff doc must NEVER mention any form of automatic
    tag creation. Stage 20.4 is strictly manual-tag-recommendation."""
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    # Case-insensitive substring check.
    assert forbidden_phrase.lower() not in text.lower(), (
        f"handoff doc contains forbidden phrase {forbidden_phrase!r}"
    )


def test_handoff_doc_template_file_does_not_mention_auto_tagging():
    """Direct template scan, independent of substitution -- the
    template file on disk must also be free of auto-tag phrasing."""
    template_path = (
        Path(hw.__file__).parent
        / "templates" / "stage21_handoff.md.tmpl"
    )
    text = template_path.read_text(encoding="utf-8")
    for forbidden in ("auto-tag", "automatically create tag"):
        assert forbidden.lower() not in text.lower(), forbidden


def test_handoff_doc_lists_manual_workflow_in_order(tmp_path: Path):
    """The numbered manual workflow steps must appear in order
    (1 Review, 2 Stage explicit paths, 3 Commit subject,
     4 Codex audit, 5 Manual tag option, 6 Do NOT push)."""
    inputs = _make_inputs(tmp_path)
    text = hw.render_handoff(inputs=inputs, run_id="run_abc")
    steps_in_order = [
        "1. Review stage21_handoff.md",
        "2. Stage explicit Stage 20.4 paths only",
        "3. Commit with subject:",
        "phx2 stage 20.4: closure audit + stage 21 handoff",
        "4. Run Codex read-only audit",
        "5. After Codex pass",
        "git tag -a stage-20-closed",
        "6. Do NOT push without explicit approval.",
    ]
    last_idx = -1
    for snippet in steps_in_order:
        idx = text.find(snippet)
        assert idx != -1, f"missing snippet: {snippet!r}"
        assert idx > last_idx, (
            f"snippet {snippet!r} appears out of order in handoff doc"
        )
        last_idx = idx
