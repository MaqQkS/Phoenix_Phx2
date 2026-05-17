"""Stage 20.4 Phase 6 -- post-run-dir blocked-packet paths.

Locked invariants:

  * Once the run directory exists, all subsequent E20xx failures
    must produce the full 8-artifact closure_blocked packet (no
    partial writes).
  * Exit code is 1 (blocked), distinct from clean (0) and from
    pre-run-dir (also 1, but no run dir exists).
  * Manifest.closure_status = ``closure_blocked``.
  * Safety flags remain hardcoded False.
  * Handoff doc + README are rendered as usual; templates have no
    'closure_blocked'-specific branches.

Planted post-run-dir failures (one per category):

  * E2036 -- lineage hash mismatch (mutated Stage 20.3 manifest).
  * E2033 -- Stage 20.3 manifest unparseable.
  * E2034 -- Stage 20.2 required artifact missing.
  * E2047 -- Stage 20.3 filter_interface_registry.csv has data rows.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import run_orchestrator as ro
from PHX2.stage20.closure.clock_helper import FrozenClock
from PHX2.stage20.closure.constants import (
    CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
    CLOSURE_STATUS_BLOCKED,
    HANDOFF_CONTRACT_VERSION,
)


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"


def _frozen() -> FrozenClock:
    return FrozenClock(datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc))


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
        "repo": repo,
        "output_root": output_root,
    }


def _write_clean_config(tmp_path: Path, layout: dict) -> Path:
    cfg = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(layout["s2"]),
        "stage20_3_run_dir": str(layout["s3"]),
        "repo_root": str(layout["repo"]),
        "output_root": str(layout["output_root"]),
        "operator_test_results": {
            "test_command": "pytest PHX2/tests/stage20/ -q",
            "run1_passed": 7,
            "run1_failed": 0,
            "run1_errors": 0,
            "run2_passed": 7,
            "run2_failed": 0,
            "run2_errors": 0,
        },
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


def _locate_run_dir(output_root: Path) -> Path:
    closure_runs = output_root / "stage20_closure_runs"
    assert closure_runs.exists()
    children = sorted(closure_runs.iterdir())
    assert len(children) == 1
    return children[0]


# ---------------------------------------------------------------------------
# E2036 -- lineage hash mismatch (post-run-dir)
# ---------------------------------------------------------------------------


@pytest.fixture
def e2036_layout(tmp_path: Path) -> dict:
    layout = _build_clean_layout(tmp_path)
    # Mutate Stage 20.3's recorded Stage 20.2 lineage so the
    # crosscheck fails post-run-dir with E2036.
    s3_manifest_path = layout["s3"] / "stage20_3_manifest.json"
    data = json.loads(s3_manifest_path.read_text(encoding="utf-8"))
    data["stage20_2_lineage"]["manifest_json_sha256"] = "0" * 64
    s3_manifest_path.write_text(
        json.dumps(data), encoding="utf-8",
    )
    layout["config_path"] = _write_clean_config(tmp_path, layout)
    return layout


def test_e2036_lineage_mismatch_returns_exit_one(e2036_layout):
    exit_code = ro.run_closure(
        e2036_layout["config_path"], clock=_frozen(),
    )
    assert exit_code == 1


def test_e2036_creates_run_dir(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    assert run_dir.is_dir()


def test_e2036_writes_all_eight_artifacts(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    for filename in CLOSURE_OUTPUT_ARTIFACT_FILENAMES:
        p = run_dir / filename
        assert p.is_file(), f"missing artifact: {filename}"
        assert p.stat().st_size > 0


def test_e2036_manifest_records_closure_blocked_status(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    manifest = json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert manifest["closure_status"] == CLOSURE_STATUS_BLOCKED


def test_e2036_manifest_records_safety_flags_false(e2036_layout):
    """Locked: even on closure_blocked, both safety flags remain
    hardcoded False."""
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    manifest = json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert manifest["safe_for_live_dispatch"] is False
    assert manifest["live_dispatch_ready"] is False


def test_e2036_manifest_errors_block_contains_e2036(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    manifest = json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    codes = [e["code"] for e in manifest["errors"]]
    assert "E2036" in codes


def test_e2036_lineage_file_records_failed_crosscheck(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    s3_lineage = json.loads(
        (run_dir / "stage20_3_lineage.json").read_text(encoding="utf-8")
    )
    assert s3_lineage["lineage_crosscheck_passed"] is False


def test_e2036_run_log_records_closure_blocked_decision(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    log_text = (run_dir / "stage20_4_run.log").read_text(
        encoding="utf-8",
    )
    events = [json.loads(line) for line in log_text.splitlines() if line]
    status_event = next(
        e for e in events if e["event"] == "closure_status_decided"
    )
    assert status_event["status"] == CLOSURE_STATUS_BLOCKED


def test_e2036_readme_records_closure_blocked_status(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    text = (run_dir / "README.md").read_text(encoding="utf-8")
    assert f"closure_status: {CLOSURE_STATUS_BLOCKED}" in text


def test_e2036_handoff_still_carries_contract_version(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    text = (run_dir / "stage21_handoff.md").read_text(encoding="utf-8")
    assert HANDOFF_CONTRACT_VERSION in text


def test_e2036_does_not_mutate_stage20_2_inputs(e2036_layout):
    s2 = e2036_layout["s2"]
    pre = {p.name: p.read_bytes() for p in s2.iterdir() if p.is_file()}
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    post = {p.name: p.read_bytes() for p in s2.iterdir() if p.is_file()}
    assert pre == post


# ---------------------------------------------------------------------------
# E2033 -- Stage 20.3 manifest unparseable
# ---------------------------------------------------------------------------


def test_e2033_unparseable_s3_manifest_produces_blocked_packet(
    tmp_path: Path,
):
    layout = _build_clean_layout(tmp_path)
    (layout["s3"] / "stage20_3_manifest.json").write_text(
        "this is not json", encoding="utf-8",
    )
    config_path = _write_clean_config(tmp_path, layout)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    run_dir = _locate_run_dir(layout["output_root"])
    for filename in CLOSURE_OUTPUT_ARTIFACT_FILENAMES:
        assert (run_dir / filename).is_file()
    manifest = json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert manifest["closure_status"] == CLOSURE_STATUS_BLOCKED
    codes = [e["code"] for e in manifest["errors"]]
    assert "E2033" in codes


# ---------------------------------------------------------------------------
# E2034 -- Stage 20.2 required artifact missing
# ---------------------------------------------------------------------------


def test_e2034_missing_s2_artifact_produces_blocked_packet(
    tmp_path: Path,
):
    layout = _build_clean_layout(tmp_path)
    # Remove the Stage 20.2 preview_candidates.csv (required).
    (layout["s2"] / "preview_candidates.csv").unlink()
    config_path = _write_clean_config(tmp_path, layout)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    run_dir = _locate_run_dir(layout["output_root"])
    for filename in CLOSURE_OUTPUT_ARTIFACT_FILENAMES:
        assert (run_dir / filename).is_file()
    manifest = json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert manifest["closure_status"] == CLOSURE_STATUS_BLOCKED
    codes = [e["code"] for e in manifest["errors"]]
    assert "E2034" in codes


# ---------------------------------------------------------------------------
# E2047 -- Stage 20.3 filter_interface_registry.csv has data rows
# ---------------------------------------------------------------------------


def test_e2047_non_header_only_registry_produces_blocked_packet(
    tmp_path: Path,
):
    layout = _build_clean_layout(tmp_path)
    # Add a data row to the registry CSV (must be header-only).
    registry = layout["s3"] / "filter_interface_registry.csv"
    existing = registry.read_text(encoding="utf-8")
    registry.write_text(
        existing + "fake_filter,fake,v1,t1,allow,c1\n", encoding="utf-8",
    )
    config_path = _write_clean_config(tmp_path, layout)

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    run_dir = _locate_run_dir(layout["output_root"])
    for filename in CLOSURE_OUTPUT_ARTIFACT_FILENAMES:
        assert (run_dir / filename).is_file()
    manifest = json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert manifest["closure_status"] == CLOSURE_STATUS_BLOCKED
    codes = [e["code"] for e in manifest["errors"]]
    assert "E2047" in codes


# ---------------------------------------------------------------------------
# Checklist row C20_4_16 reports lineage failure under E2036 path
# ---------------------------------------------------------------------------


def test_e2036_checklist_records_lineage_failure(e2036_layout):
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    run_dir = _locate_run_dir(e2036_layout["output_root"])
    import csv
    import io
    text = (run_dir / "stage20_closure_checklist.csv").read_text(
        encoding="utf-8",
    )
    rows = list(csv.reader(io.StringIO(text)))
    header, *data = rows
    code_idx = header.index("code")
    status_idx = header.index("status")
    row16 = next(r for r in data if r[code_idx] == "C20_4_16")
    assert row16[status_idx] == "fail"


# ---------------------------------------------------------------------------
# Closure blocked path does not mutate Stage 20.3 inputs either
# ---------------------------------------------------------------------------


def test_e2036_does_not_mutate_stage20_3_inputs(e2036_layout):
    s3 = e2036_layout["s3"]
    pre = {p.name: p.read_bytes() for p in s3.iterdir() if p.is_file()}
    ro.run_closure(e2036_layout["config_path"], clock=_frozen())
    post = {p.name: p.read_bytes() for p in s3.iterdir() if p.is_file()}
    assert pre == post
