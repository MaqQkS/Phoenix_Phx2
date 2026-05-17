"""Stage 20.4 Phase 6 -- E2046 overwrite refusal.

Locked invariants:

  * The orchestrator predicts the target run_dir as
    ``<output_root>/stage20_closure_runs/<run_id>/``.

  * If that directory ALREADY exists at orchestrator entry, the
    run exits 1 with an E2046 stderr line and writes NOTHING.

  * The pre-existing directory's contents must remain untouched.

  * No new directories or files appear under output_root beyond
    the pre-populated run_dir.

  * The same guard fires under both the manual ``run_closure`` API
    and the ``main(argv)`` CLI wrapper.

This is the strictest interpretation: even directories whose name
follows the locked run-id template are refused.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import run_orchestrator as ro
from PHX2.stage20.closure.clock_helper import FrozenClock
from PHX2.stage20.closure.input_loader import (
    compute_config_sha8,
    load_input_config,
)


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"

_FROZEN_DT = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)
_EXPECTED_UTC_COMPACT = "20260516T123456Z"


def _frozen() -> FrozenClock:
    return FrozenClock(_FROZEN_DT)


def _build_clean_layout(tmp_path: Path) -> dict:
    s2 = tmp_path / "stage20_2"
    s3 = tmp_path / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)
    repo = tmp_path / "repo"
    (repo / "PHX2" / "stage20" / "closure").mkdir(parents=True)
    output_root = tmp_path / "out"
    output_root.mkdir()
    return {
        "s2": s2, "s3": s3,
        "repo": repo, "output_root": output_root,
    }


def _write_config(tmp_path: Path, layout: dict) -> Path:
    cfg = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(layout["s2"]),
        "stage20_3_run_dir": str(layout["s3"]),
        "repo_root": str(layout["repo"]),
        "output_root": str(layout["output_root"]),
        "operator_test_results": {
            "test_command": "pytest -q",
            "run1_passed": 4,
            "run1_failed": 0,
            "run1_errors": 0,
            "run2_passed": 4,
            "run2_failed": 0,
            "run2_errors": 0,
        },
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


def _predicted_run_dir(config_path: Path, clock: FrozenClock) -> Path:
    """Derive the run dir the orchestrator will target, WITHOUT
    invoking the orchestrator (so we can pre-populate it)."""
    loaded = load_input_config(config_path, clock=clock)
    config = loaded.config
    config_sha8 = compute_config_sha8(config)
    utc_compact = config.generated_at_utc.replace("-", "").replace(":", "")
    run_id = f"stage20_4_{utc_compact}_{config_sha8}"
    return config.output_root / "stage20_closure_runs" / run_id


# ---------------------------------------------------------------------------
# Setup: build a layout and PRE-POPULATE the predicted run_dir
# ---------------------------------------------------------------------------


@pytest.fixture
def prepopulated_layout(tmp_path: Path):
    layout = _build_clean_layout(tmp_path)
    config_path = _write_config(tmp_path, layout)
    predicted = _predicted_run_dir(config_path, _frozen())
    predicted.mkdir(parents=True, exist_ok=False)
    # Plant sentinel content so we can verify non-mutation.
    sentinel_path = predicted / "sentinel.txt"
    sentinel_path.write_text(
        "I MUST NOT BE TOUCHED", encoding="utf-8",
    )
    return {
        "config_path": config_path,
        "output_root": layout["output_root"],
        "predicted_run_dir": predicted,
        "sentinel_path": sentinel_path,
    }


# ---------------------------------------------------------------------------
# E2046 exit code + stderr message
# ---------------------------------------------------------------------------


def test_overwrite_refusal_returns_exit_one(prepopulated_layout, capsys):
    exit_code = ro.run_closure(
        prepopulated_layout["config_path"], clock=_frozen(),
    )
    assert exit_code == 1


def test_overwrite_refusal_emits_e2046_on_stderr(
    prepopulated_layout, capsys,
):
    ro.run_closure(prepopulated_layout["config_path"], clock=_frozen())
    err = capsys.readouterr().err
    assert "E2046" in err


def test_overwrite_refusal_stderr_mentions_target_path(
    prepopulated_layout, capsys,
):
    ro.run_closure(prepopulated_layout["config_path"], clock=_frozen())
    err = capsys.readouterr().err
    assert prepopulated_layout["predicted_run_dir"].name in err


# ---------------------------------------------------------------------------
# Pre-populated directory's contents remain untouched
# ---------------------------------------------------------------------------


def test_overwrite_refusal_does_not_mutate_pre_populated_run_dir(
    prepopulated_layout,
):
    pre = prepopulated_layout["sentinel_path"].read_text(encoding="utf-8")
    ro.run_closure(prepopulated_layout["config_path"], clock=_frozen())
    post = prepopulated_layout["sentinel_path"].read_text(encoding="utf-8")
    assert pre == post == "I MUST NOT BE TOUCHED"


def test_overwrite_refusal_does_not_add_files_to_pre_populated_dir(
    prepopulated_layout,
):
    pre_contents = sorted(
        p.name for p in prepopulated_layout["predicted_run_dir"].iterdir()
    )
    ro.run_closure(prepopulated_layout["config_path"], clock=_frozen())
    post_contents = sorted(
        p.name for p in prepopulated_layout["predicted_run_dir"].iterdir()
    )
    assert pre_contents == post_contents == ["sentinel.txt"]


# ---------------------------------------------------------------------------
# No new run directories appear under output_root beyond the planted one
# ---------------------------------------------------------------------------


def test_overwrite_refusal_does_not_create_new_run_directories(
    prepopulated_layout,
):
    closure_runs = (
        prepopulated_layout["output_root"] / "stage20_closure_runs"
    )
    pre = sorted(p.name for p in closure_runs.iterdir())
    ro.run_closure(prepopulated_layout["config_path"], clock=_frozen())
    post = sorted(p.name for p in closure_runs.iterdir())
    assert pre == post


# ---------------------------------------------------------------------------
# Second-run-after-clean-first-run is also refused (live overwrite scenario)
# ---------------------------------------------------------------------------


def test_run_then_rerun_same_config_same_clock_refuses_with_e2046(
    tmp_path: Path, capsys,
):
    """Real-world overwrite: a successful first run leaves a populated
    run_dir on disk. Re-running with the SAME config + SAME clock must
    refuse with E2046 and not mutate the first run's artifacts."""
    layout = _build_clean_layout(tmp_path)
    config_path = _write_config(tmp_path, layout)

    # First run: must succeed.
    exit_a = ro.run_closure(config_path, clock=_frozen())
    assert exit_a == 0

    # Capture all bytes from the first run for the non-mutation check.
    predicted = _predicted_run_dir(config_path, _frozen())
    pre_bytes = {
        p.name: p.read_bytes()
        for p in predicted.iterdir()
        if p.is_file()
    }
    capsys.readouterr()  # drain stderr from the first run

    # Second run: same config, same clock -> E2046.
    exit_b = ro.run_closure(config_path, clock=_frozen())
    assert exit_b == 1
    err = capsys.readouterr().err
    assert "E2046" in err

    # First run's contents remain byte-identical.
    post_bytes = {
        p.name: p.read_bytes()
        for p in predicted.iterdir()
        if p.is_file()
    }
    assert pre_bytes == post_bytes


def test_run_then_rerun_does_not_add_sibling_run_dirs(
    tmp_path: Path,
):
    """After the refused second run, ``stage20_closure_runs/`` still
    holds exactly ONE directory (the original first run)."""
    layout = _build_clean_layout(tmp_path)
    config_path = _write_config(tmp_path, layout)
    ro.run_closure(config_path, clock=_frozen())

    closure_runs = layout["output_root"] / "stage20_closure_runs"
    pre = sorted(p.name for p in closure_runs.iterdir())
    assert len(pre) == 1

    ro.run_closure(config_path, clock=_frozen())  # refused
    post = sorted(p.name for p in closure_runs.iterdir())
    assert pre == post


# ---------------------------------------------------------------------------
# CLI main(argv) also refuses
# ---------------------------------------------------------------------------


def test_main_cli_refuses_overwrite(
    prepopulated_layout, capsys, monkeypatch,
):
    """The same guard applies when entering through the CLI shim
    rather than the programmatic run_closure(). We patch default_clock
    so main()'s injected clock matches the test's frozen clock."""
    from PHX2.stage20.closure import clock_helper as ch
    monkeypatch.setattr(ch, "default_clock", _frozen)
    monkeypatch.setattr(ro, "default_clock", _frozen)

    exit_code = ro.main([str(prepopulated_layout["config_path"])])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "E2046" in err


# ---------------------------------------------------------------------------
# Pre-populated run_dir need not be in the locked run-id format; any
# pre-existing dir at the exact target path is refused.
# ---------------------------------------------------------------------------


def test_predicted_run_dir_uses_locked_run_id_format(
    prepopulated_layout,
):
    """Defense in depth: confirm the test setup actually targets the
    locked run-id format."""
    name = prepopulated_layout["predicted_run_dir"].name
    parts = name.split("_")
    assert parts[:2] == ["stage20", "4"]
    assert parts[2] == _EXPECTED_UTC_COMPACT
    assert len(parts[3]) == 8
