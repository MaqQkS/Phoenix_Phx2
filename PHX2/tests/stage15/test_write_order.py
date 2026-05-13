"""Stage 15 PHASE 6 write-order tests.

Manifest must be the *last* file written. If Stage 15 crashes before
the manifest lands, the run is invalid by definition. Callers check
for manifest existence as a freshness probe.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from PHX2.scripts.run_stage15_operator_approval import (
    EXIT_OK,
    EXIT_UNEXPECTED,
    main as cli_main,
)
from PHX2.stage15.writer import (
    MANIFEST_FILENAME,
    MARKDOWN_FILENAME,
    OPERATOR_DECISIONS_FILENAME,
    POLICY_DRAFT_FILENAME,
    RUN_LOG_FILENAME,
)
from PHX2.tests.stage15.fixtures.builders import DEFAULT_REVIEWER


def _run(stage14: Path, operator: Path, output: Path) -> int:
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


def test_manifest_mtime_is_last(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """manifest.json mtime must be >= every other emitted file's mtime."""

    out = tmp_path / "out"
    _run(stage14_run, good_operator_csv, out)

    manifest_path = out / MANIFEST_FILENAME
    manifest_mtime = manifest_path.stat().st_mtime_ns

    others = [
        out / POLICY_DRAFT_FILENAME,
        out / OPERATOR_DECISIONS_FILENAME,
        out / MARKDOWN_FILENAME,
        out / RUN_LOG_FILENAME,
    ]
    for other in others:
        other_mtime = other.stat().st_mtime_ns
        assert manifest_mtime >= other_mtime, (
            f"manifest must be the last file written; "
            f"{other.name} mtime ({other_mtime}) > manifest mtime "
            f"({manifest_mtime})"
        )


def test_crash_before_manifest_leaves_no_manifest(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """Simulate an unexpected crash between writing other artifacts and
    writing the manifest.

    The CLI boundary catches the exception, maps it to EXIT_UNEXPECTED,
    and refuses to write a manifest. The "manifest exists" freshness
    probe still correctly identifies the run as invalid. Other partial
    artifacts may exist in the output dir, but no untyped exception
    leaks out of cli_main.
    """

    out = tmp_path / "out"

    import PHX2.stage15.writer as writer_module

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated crash before manifest write")

    with mock.patch.object(writer_module, "_write_manifest", side_effect=boom):
        rc = _run(stage14_run, good_operator_csv, out)

    assert rc == EXIT_UNEXPECTED
    assert rc != EXIT_OK
    assert not (out / MANIFEST_FILENAME).exists()
    # The run.log gets re-emitted with the traceback by the CLI's
    # exception handler, so it should exist and reference the crash.
    assert (out / RUN_LOG_FILENAME).exists()
    log_text = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
    assert "unexpected_exception" in log_text
    assert "RuntimeError" in log_text
    assert "simulated crash" in log_text


def test_manifest_atomic_write_uses_tmp_path(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """The manifest is written via .tmp + os.replace. After the run
    completes, the .tmp must NOT linger."""

    out = tmp_path / "out"
    _run(stage14_run, good_operator_csv, out)
    assert not (out / (MANIFEST_FILENAME + ".tmp")).exists()
    assert (out / MANIFEST_FILENAME).exists()


def test_load_time_failure_has_no_manifest_or_partial_outputs(
    tmp_path,
    stage14_run,
) -> None:
    """Tier 2: only the log may exist."""

    from PHX2.tests.stage15.fixtures.builders import make_operator_csv, approve_row

    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=(approve_row("unknown_rule_id"),))  # L23
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc != 0
    assert not (out / MANIFEST_FILENAME).exists()
    assert not (out / POLICY_DRAFT_FILENAME).exists()
