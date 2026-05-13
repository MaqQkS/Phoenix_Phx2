"""Stage 15 PHASE 6 determinism tests.

Two runs with identical inputs must produce byte-identical outputs
except for:
  * created_at_utc fields
  * wall-clock timestamps in stage15_run.log
  * hashes that transitively depend on timestamp-containing files
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PHX2.scripts.run_stage15_operator_approval import main as cli_main
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
from PHX2.tests.stage15.fixtures.builders import DEFAULT_REVIEWER


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


# Patterns whose values are expected to differ between runs (timestamps
# or timestamp-derived hashes). These are stripped before diffing.
_TIMESTAMP_PATTERNS = (
    re.compile(r'"created_at_utc"\s*:\s*"[^"]*"'),
    re.compile(r'"run_timestamp_utc"\s*:\s*"[^"]*"'),
    # The whole `output_files` hash bundle (because run.log differs).
    re.compile(r'"output_files"\s*:\s*\{[^}]*\}', re.DOTALL),
)


def _mask_json(text: str) -> str:
    out = text
    for pat in _TIMESTAMP_PATTERNS:
        out = pat.sub('"<MASKED>"', out)
    return out


def _mask_markdown(text: str) -> str:
    """Mask timestamps + the run-dir path. The Stage 15 run dir is
    expected to differ between runs by construction (each test uses
    out_a / out_b), so it doesn't count as a determinism violation.
    """

    masked = re.sub(
        r"Created at UTC: `[^`]*`",
        "Created at UTC: `<MASKED>`",
        text,
    )
    masked = re.sub(
        r"Stage 15 run dir: `[^`]*`",
        "Stage 15 run dir: `<MASKED>`",
        masked,
    )
    return masked


def _mask_run_log(text: str) -> str:
    # Every line begins with an ISO timestamp; strip it.
    return re.sub(
        r"^\d{4}-\d{2}-\d{2}T[\d:.+\-Z]+\s",
        "<TS> ",
        text,
        flags=re.MULTILINE,
    )


def test_two_runs_produce_byte_identical_outputs_after_masking(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    _run(stage14_run, good_operator_csv, out_a)
    _run(stage14_run, good_operator_csv, out_b)

    def normalize_paths(text: str) -> str:
        """Strip per-run output-dir paths so the rest of the content
        can be compared byte-for-byte. Handles both raw paths (used in
        markdown / manifest fields) and Python-repr paths with escaped
        backslashes (used in the argv line of stage15_run.log)."""

        normalized = text
        for path in (out_a, out_b):
            raw = str(path)
            normalized = normalized.replace(raw, "<OUT>")
            # repr() doubles backslashes on Windows; replace that form too.
            escaped = raw.replace("\\", "\\\\")
            if escaped != raw:
                normalized = normalized.replace(escaped, "<OUT>")
        return normalized

    # Files where exact equality should hold (no timestamps).
    exact_equal_files = (
        OPERATOR_DECISIONS_FILENAME,
        REJECTED_FILENAME,
        HELD_FILENAME,
        NEEDS_MORE_DATA_FILENAME,
        UNREVIEWED_FILENAME,
        APPROVAL_ERRORS_FILENAME,
    )
    for filename in exact_equal_files:
        a_bytes = (out_a / filename).read_bytes()
        b_bytes = (out_b / filename).read_bytes()
        assert a_bytes == b_bytes, (
            f"{filename} differs between runs; CSV outputs must be byte-stable"
        )

    # Policy draft: equality after masking created_at_utc.
    a_draft = _mask_json((out_a / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    b_draft = _mask_json((out_b / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    assert a_draft == b_draft

    # Manifest: equality after masking timestamps + output_files hashes
    # and normalizing the per-run output-dir path that appears in
    # source_*_path fields when the input lives under tmp_path.
    a_man = _mask_json(
        normalize_paths((out_a / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    )
    b_man = _mask_json(
        normalize_paths((out_b / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    )
    assert a_man == b_man

    # Markdown: equality after masking timestamps + output-dir path.
    a_md = _mask_markdown(
        normalize_paths((out_a / MARKDOWN_FILENAME).read_text(encoding="utf-8"))
    )
    b_md = _mask_markdown(
        normalize_paths((out_b / MARKDOWN_FILENAME).read_text(encoding="utf-8"))
    )
    assert a_md == b_md

    # Run log: equality after masking per-line timestamps + output-dir path.
    a_log = _mask_run_log(
        normalize_paths((out_a / RUN_LOG_FILENAME).read_text(encoding="utf-8"))
    )
    b_log = _mask_run_log(
        normalize_paths((out_b / RUN_LOG_FILENAME).read_text(encoding="utf-8"))
    )
    assert a_log == b_log


def test_rule_ordering_stable_across_runs(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """The order of rules in the policy draft must match across runs."""

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    _run(stage14_run, good_operator_csv, out_a)
    _run(stage14_run, good_operator_csv, out_b)
    a = json.loads((out_a / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    b = json.loads((out_b / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    assert [r["rule_id"] for r in a["rules"]] == [r["rule_id"] for r in b["rules"]]


def test_csv_row_order_stable(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    _run(stage14_run, good_operator_csv, out_a)
    _run(stage14_run, good_operator_csv, out_b)
    a_rows = (out_a / OPERATOR_DECISIONS_FILENAME).read_text(encoding="utf-8").splitlines()
    b_rows = (out_b / OPERATOR_DECISIONS_FILENAME).read_text(encoding="utf-8").splitlines()
    assert a_rows == b_rows
