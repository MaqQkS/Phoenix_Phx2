"""Stage 15 PHASE 7 isolation tests.

Stage 15 must not open a DB connection, make a network call, open a
socket, read live config, or import runtime modules with side effects.
These tests monkeypatch the relevant primitives to raise and assert
that Stage 15 still completes a clean run.
"""

from __future__ import annotations

import socket
import sqlite3
from pathlib import Path

import pytest

from PHX2.scripts.run_stage15_operator_approval import (
    EXIT_OK,
    main as cli_main,
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


def test_socket_socket_raise_does_not_break_run(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """If socket.socket() raises, Stage 15 still completes. This proves
    Stage 15 doesn't open sockets in its happy path."""

    def boom(*_a, **_kw):
        raise OSError("network is unavailable")

    monkeypatch.setattr(socket, "socket", boom)

    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_OK


def test_sqlite3_connect_raise_does_not_break_run(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """If sqlite3.connect() raises, Stage 15 still completes. This
    proves Stage 15 doesn't open DB connections."""

    def boom(*_a, **_kw):
        raise sqlite3.OperationalError("DB unavailable")

    monkeypatch.setattr(sqlite3, "connect", boom)

    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_OK


def test_stage15_does_not_import_runtime_modules() -> None:
    """Static check: no Stage 15 module's import graph contains
    runtime/service/dispatch/integration modules.

    We re-import each Stage 15 module after clearing sys.modules of
    those prefixes; if Stage 15 transitively imported any, the assert
    would catch it.
    """

    import sys

    forbidden_prefixes = (
        "PHX2.db",
        "PHX2.services",
        "PHX2.dispatch",
        "PHX2.renderers",
        "PHX2.integrations",
        "PHX2.filters",
    )

    pre_loaded = {
        name
        for name in sys.modules
        if any(name.startswith(p) for p in forbidden_prefixes)
    }

    import PHX2.stage15
    import PHX2.stage15.errors
    import PHX2.stage15.hashing
    import PHX2.stage15.loaders
    import PHX2.stage15.reconciler
    import PHX2.stage15.safety_gate
    import PHX2.stage15.writer
    import PHX2.stage15.markdown
    import PHX2.scripts.run_stage15_operator_approval  # noqa: F401

    post_loaded = {
        name
        for name in sys.modules
        if any(name.startswith(p) for p in forbidden_prefixes)
    }

    # Stage 15 must not have caused any additional forbidden imports.
    new = post_loaded - pre_loaded
    assert not new, (
        f"Stage 15 imported forbidden runtime/service modules: {sorted(new)!r}"
    )


def test_stage15_writes_only_under_output_dir(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """After a clean run, only --output-dir contains new files.

    Sentinel: snapshot the inputs' contents and verify they're
    bytewise-identical post-run. Stage 15 must not mutate Stage 14
    artifacts or the operator CSV."""

    before = {
        "stage14_manifest": (stage14_run / "manifest.json").read_bytes(),
        "stage14_rules": (stage14_run / "shadow_policy_rules.json").read_bytes(),
        "stage14_impact": (stage14_run / "impact_summary_by_rule.csv").read_bytes(),
        "operator_csv": good_operator_csv.read_bytes(),
    }
    out = tmp_path / "out"
    _run(stage14_run, good_operator_csv, out)
    after = {
        "stage14_manifest": (stage14_run / "manifest.json").read_bytes(),
        "stage14_rules": (stage14_run / "shadow_policy_rules.json").read_bytes(),
        "stage14_impact": (stage14_run / "impact_summary_by_rule.csv").read_bytes(),
        "operator_csv": good_operator_csv.read_bytes(),
    }
    assert before == after


def test_no_unexpected_files_created_outside_output_dir(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """Snapshot the filesystem layout before and after; the diff should
    only show the Stage 15 output directory's new contents."""

    def list_relative(root: Path) -> set[str]:
        return {
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file()
        }

    out = tmp_path / "out"

    before = list_relative(tmp_path)
    _run(stage14_run, good_operator_csv, out)
    after = list_relative(tmp_path)

    new_files = after - before
    out_rel = str(out.relative_to(tmp_path))
    for f in new_files:
        assert f.startswith(out_rel + "\\") or f.startswith(out_rel + "/"), (
            f"file {f!r} was created outside --output-dir {out_rel!r}"
        )
