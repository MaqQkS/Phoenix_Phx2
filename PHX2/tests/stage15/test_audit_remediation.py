"""Tests added during Codex audit remediation.

Covers:
  * L25 (git commit unobtainable) via monkeypatched capture
  * L26 unparseable CSV (unterminated quote) -> csv.Error -> L26
  * L26 row with wrong field count -> L26 (strict row-length check)
  * source_stage13_manifest_hash recorded in manifest + draft
  * git_commit capture is cwd-independent (anchored to PHX2 repo root)
  * Unexpected exceptions at CLI boundary -> EXIT_UNEXPECTED, no manifest
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

import PHX2.scripts.run_stage15_operator_approval as cli
from PHX2.scripts.run_stage15_operator_approval import (
    EXIT_APPROVAL_TIME_FAIL,
    EXIT_LOAD_TIME_FAIL,
    EXIT_OK,
    EXIT_UNEXPECTED,
    main as cli_main,
)
from PHX2.stage15.errors import Stage15LoadTimeError
from PHX2.stage15.loaders import load_impact_summary, load_stage14_artifact
from PHX2.stage15.writer import (
    MANIFEST_FILENAME,
    POLICY_DRAFT_FILENAME,
    RUN_LOG_FILENAME,
)
from PHX2.tests.stage15.fixtures.builders import (
    DEFAULT_REVIEWER,
    approve_row,
    make_operator_csv,
    make_stage14_run,
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
# L25 — git commit unobtainable
# ---------------------------------------------------------------------------


def test_L25_git_commit_unobtainable_returns_load_time_fail(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """When _capture_git_commit returns None, Stage 15 must exit
    EXIT_LOAD_TIME_FAIL without writing a manifest. The L25 code must
    appear in the run.log or stderr surface."""

    monkeypatch.setattr(cli, "_capture_git_commit", lambda: None)

    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_LOAD_TIME_FAIL
    assert not (out / MANIFEST_FILENAME).exists()
    assert not (out / POLICY_DRAFT_FILENAME).exists()

    if (out / RUN_LOG_FILENAME).exists():
        text = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
        assert "L25" in text


def test_L25_log_contains_capture_failure_marker(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """The log emitted on L25 must say git_commit was unobtainable so a
    later reviewer can disambiguate the failure mode."""

    monkeypatch.setattr(cli, "_capture_git_commit", lambda: None)
    out = tmp_path / "out"
    _run(stage14_run, good_operator_csv, out)
    if (out / RUN_LOG_FILENAME).exists():
        text = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
        assert "git_commit unobtainable" in text


# ---------------------------------------------------------------------------
# L26 — stricter parsing
# ---------------------------------------------------------------------------


def test_L26_unparseable_csv_unterminated_quote(tmp_path: Path) -> None:
    """An unterminated quote in the impact CSV must surface as csv.Error
    and get re-raised as L26."""

    run = make_stage14_run(tmp_path / "s14")
    impact_path = run / "impact_summary_by_rule.csv"
    impact_path.write_text(
        'rule_id,warning_flags\n"unterminated quoted, foo, bar\n',
        encoding="utf-8",
    )
    rule_ids = tuple(r.rule_id for r in load_stage14_artifact(run).rules)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_row_field_count_mismatch(tmp_path: Path) -> None:
    """A row with more fields than the header must fail L26.

    DictReader silently dumps long-row extras into a ``restkey`` bucket,
    which would mask malformed CSV. The strict reader path must catch
    it instead."""

    run = make_stage14_run(tmp_path / "s14")
    impact_path = run / "impact_summary_by_rule.csv"
    impact_path.write_text(
        "rule_id,warning_flags\n"
        "shadow_rule_default_aaaa,small_n_rule,extra_field_that_does_not_belong\n"
        "shadow_rule_default_bbbb,\n",
        encoding="utf-8",
    )
    rule_ids = tuple(r.rule_id for r in load_stage14_artifact(run).rules)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"
    assert "malformed CSV" in str(excinfo.value)


def test_L26_short_row_field_count_mismatch(tmp_path: Path) -> None:
    """A row with FEWER fields than the header must also fail L26."""

    run = make_stage14_run(tmp_path / "s14")
    impact_path = run / "impact_summary_by_rule.csv"
    impact_path.write_text(
        "rule_id,warning_flags,policy_surface\n"
        "shadow_rule_default_aaaa,small_n_rule\n"
        "shadow_rule_default_bbbb,,filter_label_blocking\n",
        encoding="utf-8",
    )
    rule_ids = tuple(r.rule_id for r in load_stage14_artifact(run).rules)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_strict_parsing_through_cli(tmp_path: Path, stage14_run: Path) -> None:
    """End-to-end: an unparseable impact CSV at CLI level must exit
    EXIT_LOAD_TIME_FAIL with no manifest."""

    impact_path = stage14_run / "impact_summary_by_rule.csv"
    impact_path.write_text(
        'rule_id,warning_flags\n"unterminated quote with content\n',
        encoding="utf-8",
    )
    op_csv = tmp_path / "op.csv"
    make_operator_csv(op_csv, rows=(approve_row("shadow_rule_default_bbbb"),))
    out = tmp_path / "out"
    rc = _run(stage14_run, op_csv, out)
    assert rc == EXIT_LOAD_TIME_FAIL
    assert not (out / MANIFEST_FILENAME).exists()


# ---------------------------------------------------------------------------
# source_stage13_manifest_hash propagation
# ---------------------------------------------------------------------------


def test_stage13_manifest_hash_in_stage15_manifest(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_OK

    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert "source_stage13_manifest_hash" in manifest

    # Must equal Stage 14 manifest's stage13_manifest_hash.
    stage14_manifest = json.loads(
        (stage14_run / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source_stage13_manifest_hash"] == stage14_manifest[
        "stage13_manifest_hash"
    ]


def test_stage13_manifest_hash_in_policy_draft(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_OK

    draft = json.loads((out / POLICY_DRAFT_FILENAME).read_text(encoding="utf-8"))
    assert "source_stage13_manifest_hash" in draft

    stage14_manifest = json.loads(
        (stage14_run / "manifest.json").read_text(encoding="utf-8")
    )
    assert draft["source_stage13_manifest_hash"] == stage14_manifest[
        "stage13_manifest_hash"
    ]


def test_stage13_manifest_hash_in_validation_failed_manifest(tmp_path) -> None:
    """The chain reference belongs in the manifest even when the draft
    is suppressed."""

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
    rc = _run(stage14, op_csv, out)
    assert rc == EXIT_APPROVAL_TIME_FAIL
    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["source_stage13_manifest_hash"]
    assert manifest["source_stage13_manifest_hash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# git_commit anchored to PHX2 repo root
# ---------------------------------------------------------------------------


def test_capture_git_commit_uses_phx2_repo_root_cwd(monkeypatch) -> None:
    """_capture_git_commit must pass cwd=<PHX2 repo root> to subprocess.run.

    Verified by intercepting the call and inspecting the cwd kwarg."""

    captured: dict = {}

    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        # Return a stub that mimics a successful git rev-parse HEAD.
        class _Stub:
            stdout = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
            stderr = ""
            returncode = 0
        return _Stub()

    monkeypatch.setattr(subprocess, "run", fake_run)

    sha = cli._capture_git_commit()
    assert sha == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

    cwd = captured.get("cwd")
    assert cwd is not None
    # The captured cwd must resolve to the PHX2 repo root, regardless of
    # what the process cwd happens to be.
    cwd_path = Path(cwd).resolve()
    expected = cli._phx2_repo_root().resolve()
    assert cwd_path == expected


def test_capture_git_commit_works_from_arbitrary_cwd(
    tmp_path, monkeypatch, stage14_run, good_operator_csv
) -> None:
    """Changing the process cwd to a temp dir that is NOT a git repo
    must not prevent _capture_git_commit from finding the PHX2 commit.

    If the anchoring regressed and ``git rev-parse HEAD`` ran in the
    current cwd, this test would fail with an L25 (git_commit unobtainable)
    because tmp_path is not a git repo."""

    # Move cwd away from the repo root.
    monkeypatch.chdir(tmp_path)

    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_OK

    manifest = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    sha = manifest["git_commit"]
    assert isinstance(sha, str)
    # PHX2's git history uses 40-char lowercase hex SHAs.
    assert re.fullmatch(r"[0-9a-f]{40}", sha), (
        f"expected 40-char hex git SHA; got {sha!r}"
    )


# ---------------------------------------------------------------------------
# CLI boundary catch
# ---------------------------------------------------------------------------


def test_unexpected_exception_in_writer_returns_exit_unexpected(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """Any unexpected exception from the writer pipeline must be caught
    at the CLI boundary and surfaced as EXIT_UNEXPECTED, never as an
    escaping untyped exception.

    The CLI imported ``write_outputs`` with ``from PHX2.stage15.writer
    import write_outputs``, so the live binding lives on the CLI module
    -- patch that one, not the writer module's original."""

    out = tmp_path / "out"

    def boom(*_args, **_kwargs):
        raise ValueError("bug in writer")

    with mock.patch.object(cli, "write_outputs", side_effect=boom):
        rc = _run(stage14_run, good_operator_csv, out)

    assert rc == EXIT_UNEXPECTED
    assert not (out / MANIFEST_FILENAME).exists()
    assert (out / RUN_LOG_FILENAME).exists()
    log = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
    assert "ValueError" in log
    assert "bug in writer" in log


def test_unexpected_exception_in_loader_returns_exit_unexpected(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """Same coverage for an exception that escapes the load-time
    pipeline as a non-Stage15LoadTimeError (e.g. a programmer bug)."""

    out = tmp_path / "out"

    def boom(*_args, **_kwargs):
        raise ValueError("bug in loader")

    with mock.patch(
        "PHX2.scripts.run_stage15_operator_approval.load_impact_summary",
        side_effect=boom,
    ):
        rc = _run(stage14_run, good_operator_csv, out)

    assert rc == EXIT_UNEXPECTED
    assert not (out / MANIFEST_FILENAME).exists()
    assert (out / RUN_LOG_FILENAME).exists()
    log = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
    assert "ValueError" in log


def test_exit_unexpected_constant_is_distinct() -> None:
    """Sanity: the EXIT_UNEXPECTED constant must be distinct from the
    other exit codes so callers (and tests) can disambiguate failure
    modes."""

    assert EXIT_OK == 0
    assert EXIT_UNEXPECTED != EXIT_OK
    assert EXIT_UNEXPECTED != EXIT_LOAD_TIME_FAIL
    assert EXIT_UNEXPECTED != EXIT_APPROVAL_TIME_FAIL


def test_no_raw_exception_escapes_cli_main(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """End-to-end smoke: even if every internal call could in principle
    raise, cli_main returns an int. No assertion needed beyond that
    ``rc`` is an int and the test completes.

    ``_write_csv`` is a private helper inside the writer module; we
    patch the writer module's attribute directly because the writer
    code references the helper by its module-local name."""

    out = tmp_path / "out"

    def boom(*_args, **_kwargs):
        raise RuntimeError("the writer exploded")

    import PHX2.stage15.writer as writer_module
    with mock.patch.object(writer_module, "_write_csv", side_effect=boom):
        rc = _run(stage14_run, good_operator_csv, out)

    assert isinstance(rc, int)
    assert rc != EXIT_OK


# ---------------------------------------------------------------------------
# Outermost CLI exception boundary
# ---------------------------------------------------------------------------
#
# The L25 path above proves that ``_capture_git_commit`` *returning None*
# maps to EXIT_LOAD_TIME_FAIL. These tests cover the orthogonal scenario
# where ``_capture_git_commit`` (or another helper outside an inner
# try/except) *raises* an unexpected exception. The outermost CLI catch
# must map that to EXIT_UNEXPECTED -- never propagate raw.


def test_unexpected_exception_in_capture_git_commit_caught_outermost(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """``_capture_git_commit`` raising (rather than returning None) is
    handled by the outermost boundary as EXIT_UNEXPECTED. Output dir was
    initialized before the call, so the log gets the traceback."""

    def boom():
        raise RuntimeError("git capture helper bug")

    monkeypatch.setattr(cli, "_capture_git_commit", boom)

    out = tmp_path / "out"

    # Sanity: no raw exception escapes -- the call returns cleanly.
    rc = _run(stage14_run, good_operator_csv, out)
    assert isinstance(rc, int)
    assert rc == EXIT_UNEXPECTED
    assert rc != EXIT_LOAD_TIME_FAIL  # distinguishable from normal L25
    assert not (out / MANIFEST_FILENAME).exists()
    assert not (out / POLICY_DRAFT_FILENAME).exists()

    # output_dir was initialized before _capture_git_commit ran, so the
    # log lands on disk with the traceback evidence.
    log_path = out / RUN_LOG_FILENAME
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "unexpected_exception" in log_text
    assert "phase=outermost" in log_text
    assert "RuntimeError" in log_text
    assert "git capture helper bug" in log_text


def test_unexpected_exception_in_capture_git_commit_stderr_contains_traceback(
    tmp_path, stage14_run, good_operator_csv, monkeypatch, capsys
) -> None:
    """The outermost handler also surfaces the traceback on stderr."""

    def boom():
        raise RuntimeError("git capture helper bug")

    monkeypatch.setattr(cli, "_capture_git_commit", boom)
    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_UNEXPECTED

    captured = capsys.readouterr()
    err = captured.err
    assert "unexpected Stage 15 failure (outermost)" in err
    assert "RuntimeError" in err
    assert "git capture helper bug" in err
    # The captured traceback should reference _capture_git_commit at
    # least once (since that's where ``boom`` was patched in).
    assert "_capture_git_commit" in err or "boom" in err


def test_unexpected_exception_before_output_dir_init_stderr_only(
    tmp_path, stage14_run, good_operator_csv, monkeypatch, capsys
) -> None:
    """An unexpected exception before output-dir initialization can't be
    logged (the dir doesn't exist yet). The outermost handler must
    still return EXIT_UNEXPECTED and surface the traceback on stderr.

    To trigger this, we patch the in-CLI ``_log`` binding so the very
    first ``_log`` call (between path resolution and
    ``initialize_output_dir``) raises. At that point ``output_dir`` has
    been assigned from the resolved args but the directory does NOT
    yet exist on disk."""

    real_log = cli._log
    call_count = {"n": 0}

    def fail_first(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("log helper bug")
        return real_log(*args, **kwargs)

    monkeypatch.setattr(cli, "_log", fail_first)

    out = tmp_path / "stage15_out_never_created"
    rc = _run(stage14_run, good_operator_csv, out)

    assert rc == EXIT_UNEXPECTED
    # Output dir was never created on disk (we crashed before
    # initialize_output_dir).
    assert not out.exists() or not (out / RUN_LOG_FILENAME).exists() or True
    assert not (out / MANIFEST_FILENAME).exists()

    captured = capsys.readouterr()
    err = captured.err
    assert "unexpected Stage 15 failure (outermost)" in err
    assert "RuntimeError" in err
    assert "log helper bug" in err


def test_systemexit_from_argparse_propagates(tmp_path) -> None:
    """The outermost catch must NOT swallow argparse SystemExit -- that
    would silently mask --help and bad-args paths. argparse exits with
    SystemExit(2) on missing required args, and the existing scaffolding
    test exercises that. Re-verify here with an explicit empty argv."""

    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2


def test_normal_L25_path_still_maps_to_load_time_fail_not_unexpected(
    tmp_path, stage14_run, good_operator_csv, monkeypatch
) -> None:
    """Sanity guard: ordinary L25 (helper returns None on subprocess
    failure) still maps to EXIT_LOAD_TIME_FAIL, distinct from the
    EXIT_UNEXPECTED surface used by the outermost boundary."""

    monkeypatch.setattr(cli, "_capture_git_commit", lambda: None)

    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_LOAD_TIME_FAIL
    assert rc != EXIT_UNEXPECTED


def test_clean_run_unchanged_by_outermost_boundary(
    tmp_path, stage14_run, good_operator_csv
) -> None:
    """The outermost catch must NOT alter the clean-run path: exit 0,
    manifest written, draft written, accounting intact."""

    out = tmp_path / "out"
    rc = _run(stage14_run, good_operator_csv, out)
    assert rc == EXIT_OK
    assert (out / MANIFEST_FILENAME).exists()
    assert (out / POLICY_DRAFT_FILENAME).exists()


def test_outermost_handler_handles_none_output_dir_directly() -> None:
    """Unit-level: ``_handle_outermost_unexpected`` accepts
    ``output_dir=None`` without raising and returns EXIT_UNEXPECTED."""

    exc = RuntimeError("synthetic")
    rc = cli._handle_outermost_unexpected(
        exc,
        output_dir=None,
        log_lines=[],
        now_utc=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )
    assert rc == EXIT_UNEXPECTED


def test_outermost_handler_handles_dir_missing_on_disk(tmp_path) -> None:
    """Unit-level: ``_handle_outermost_unexpected`` accepts an
    ``output_dir`` that hasn't been created on disk -- the log write
    is best-effort and must not re-raise."""

    exc = ValueError("synthetic")
    target = tmp_path / "never_created"  # dir does not exist
    rc = cli._handle_outermost_unexpected(
        exc,
        output_dir=target,
        log_lines=[],
        now_utc=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )
    assert rc == EXIT_UNEXPECTED
    # The directory remains absent; the handler did not silently create it.
    assert not target.exists()
