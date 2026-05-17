"""Stage 20.4 Phase 6 -- pre-run-dir failure paths.

Locked invariants:

  * Pre-run-dir validation failures (E2030 / E2031 / E2043 / E2044 /
    E2045) exit 1 and DO NOT create
    ``<output_root>/stage20_closure_runs/<run_id>/``.

  * InputFormatError (file missing / malformed JSON / output_root
    precondition) exits 2 and DOES NOT create the output directory.

  * Pre-run-dir failures print a structured error block to stderr
    listing every accumulated E20xx code + detail.

  * ``output_root/stage20_closure_runs/`` is NOT created on any
    pre-run-dir failure (the orchestrator only mkdirs after every
    pre-run-dir check passes).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import run_orchestrator as ro
from PHX2.stage20.closure.clock_helper import FrozenClock


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"


def _frozen() -> FrozenClock:
    return FrozenClock(datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc))


def _base_layout(tmp_path: Path) -> dict:
    s2 = tmp_path / "stage20_2"
    s3 = tmp_path / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)
    repo = tmp_path / "repo"
    (repo / "PHX2").mkdir(parents=True)
    output_root = tmp_path / "out"
    output_root.mkdir()
    return {
        "s2": s2,
        "s3": s3,
        "repo": repo,
        "output_root": output_root,
    }


def _write_config(tmp_path: Path, config: dict, name: str = "config.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return p


def _base_config(layout: dict) -> dict:
    return {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(layout["s2"]),
        "stage20_3_run_dir": str(layout["s3"]),
        "repo_root": str(layout["repo"]),
        "output_root": str(layout["output_root"]),
        "operator_test_results": {
            "test_command": "pytest -q",
            "run1_passed": 5,
            "run1_failed": 0,
            "run1_errors": 0,
            "run2_passed": 5,
            "run2_failed": 0,
            "run2_errors": 0,
        },
    }


def _assert_no_output_dir_created(output_root: Path) -> None:
    closure_runs = output_root / "stage20_closure_runs"
    assert not closure_runs.exists(), (
        f"orchestrator created closure_runs dir on pre-run-dir "
        f"failure: {closure_runs}"
    )


# ---------------------------------------------------------------------------
# E2030 -- stage20_2_run_dir missing
# ---------------------------------------------------------------------------


def test_e2030_missing_stage20_2_run_dir_exits_one(
    tmp_path: Path, capsys,
):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_2_run_dir"] = str(tmp_path / "definitely_not_present")
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2030" in err
    _assert_no_output_dir_created(layout["output_root"])


# ---------------------------------------------------------------------------
# E2031 -- stage20_3_run_dir missing
# ---------------------------------------------------------------------------


def test_e2031_missing_stage20_3_run_dir_exits_one(
    tmp_path: Path, capsys,
):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_3_run_dir"] = str(tmp_path / "no_such_dir")
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2031" in err
    _assert_no_output_dir_created(layout["output_root"])


# ---------------------------------------------------------------------------
# E2043 -- operator_test_results inconsistent / red
# ---------------------------------------------------------------------------


def test_e2043_red_run1_results_exits_one(tmp_path: Path, capsys):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["operator_test_results"]["run1_failed"] = 2
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2043" in err
    _assert_no_output_dir_created(layout["output_root"])


def test_e2043_run_count_mismatch_exits_one(tmp_path: Path, capsys):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["operator_test_results"]["run1_passed"] = 5
    cfg["operator_test_results"]["run2_passed"] = 7
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2043" in err
    _assert_no_output_dir_created(layout["output_root"])


def test_e2043_both_runs_zero_pass_exits_one(tmp_path: Path, capsys):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["operator_test_results"]["run1_passed"] = 0
    cfg["operator_test_results"]["run2_passed"] = 0
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2043" in err
    _assert_no_output_dir_created(layout["output_root"])


# ---------------------------------------------------------------------------
# E2044 -- commit SHA format invalid
# ---------------------------------------------------------------------------


def test_e2044_bad_commit_sha_format_exits_one(tmp_path: Path, capsys):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_2_commit_sha"] = "NOT_A_VALID_SHA"
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2044" in err
    assert "stage20_2_commit_sha" in err
    _assert_no_output_dir_created(layout["output_root"])


def test_e2044_short_sha_exits_one(tmp_path: Path, capsys):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_3_commit_sha"] = "abcd1234"  # 8 chars, not 40
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2044" in err
    _assert_no_output_dir_created(layout["output_root"])


# ---------------------------------------------------------------------------
# E2045 -- repo_root not a PHX2 repo root
# ---------------------------------------------------------------------------


def test_e2045_repo_root_missing_phx2_subdir_exits_one(
    tmp_path: Path, capsys,
):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    bad_repo = tmp_path / "bad_repo"
    bad_repo.mkdir()
    # No PHX2/ subdirectory -> E2045.
    cfg["repo_root"] = str(bad_repo)
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2045" in err
    _assert_no_output_dir_created(layout["output_root"])


# ---------------------------------------------------------------------------
# Multiple pre-run-dir errors accumulate
# ---------------------------------------------------------------------------


def test_multiple_pre_run_dir_errors_all_reported(
    tmp_path: Path, capsys,
):
    """Pre-run-dir validation does NOT short-circuit. All accumulated
    E20xx errors should appear in stderr."""
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_2_commit_sha"] = "NOT_A_SHA"
    cfg["stage20_2_run_dir"] = str(tmp_path / "missing_s2")
    cfg["operator_test_results"]["run1_failed"] = 3
    config_path = _write_config(tmp_path, cfg)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2030" in err
    assert "E2043" in err
    assert "E2044" in err
    _assert_no_output_dir_created(layout["output_root"])


# ---------------------------------------------------------------------------
# InputFormatError -- exit code 2, no output dir
# ---------------------------------------------------------------------------


def test_input_format_error_missing_config_exits_two(
    tmp_path: Path, capsys,
):
    missing = tmp_path / "does_not_exist.json"
    exit_code = ro.run_closure(missing, clock=_frozen())
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "InputFormatError" in err


def test_input_format_error_malformed_json_exits_two(
    tmp_path: Path, capsys,
):
    p = tmp_path / "config.json"
    p.write_text("this is not json", encoding="utf-8")
    exit_code = ro.run_closure(p, clock=_frozen())
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "InputFormatError" in err


def test_input_format_error_missing_required_key_exits_two(
    tmp_path: Path, capsys,
):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg.pop("operator_test_results")
    config_path = _write_config(tmp_path, cfg)
    exit_code = ro.run_closure(config_path, clock=_frozen())
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "InputFormatError" in err


def test_input_format_error_does_not_create_output_dir(
    tmp_path: Path,
):
    layout = _base_layout(tmp_path)
    out = layout["output_root"]
    pre_listing = sorted(p.name for p in out.iterdir())
    missing = tmp_path / "missing.json"
    ro.run_closure(missing, clock=_frozen())
    post_listing = sorted(p.name for p in out.iterdir())
    assert pre_listing == post_listing


def test_pre_run_dir_failure_does_not_create_closure_runs_subdir(
    tmp_path: Path,
):
    """Even though ``<output_root>`` exists (writable), the
    ``stage20_closure_runs`` SUBDIR must not appear on a pre-run-dir
    failure path."""
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_2_run_dir"] = str(tmp_path / "no_dir")
    config_path = _write_config(tmp_path, cfg)
    ro.run_closure(config_path, clock=_frozen())
    closure_runs = layout["output_root"] / "stage20_closure_runs"
    assert not closure_runs.exists()


def test_input_format_error_with_invalid_output_root_exits_two(
    tmp_path: Path, capsys,
):
    """output_root preconditions live in InputFormatError (exit 2),
    not in E20xx (exit 1)."""
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["output_root"] = str(tmp_path / "missing_output_root")
    config_path = _write_config(tmp_path, cfg)
    exit_code = ro.run_closure(config_path, clock=_frozen())
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "InputFormatError" in err


# ---------------------------------------------------------------------------
# Stderr format: each pre-run-dir error gets one line with code + detail
# ---------------------------------------------------------------------------


def test_pre_run_dir_stderr_lists_every_error_code(
    tmp_path: Path, capsys,
):
    layout = _base_layout(tmp_path)
    cfg = _base_config(layout)
    cfg["stage20_1_commit_sha"] = "bad"
    cfg["stage20_3_commit_sha"] = "bad"
    config_path = _write_config(tmp_path, cfg)

    ro.run_closure(config_path, clock=_frozen())
    err = capsys.readouterr().err
    # Both bad SHAs should appear with E2044 code.
    assert err.count("E2044") >= 2
    assert "stage20_1_commit_sha" in err
    assert "stage20_3_commit_sha" in err
