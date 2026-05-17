"""Stage 20.4 Phase 6 -- clean end-to-end orchestrator run.

Clean closure inputs (Stage 20.2 + Stage 20.3 fixtures, valid commit
SHAs, green operator_test_results, empty closure_runs_root). The
orchestrator must:

  * Exit 0.
  * Create ``<output_root>/stage20_closure_runs/<run_id>/``.
  * Write all 8 artifacts with the locked filenames.
  * Set closure_status = ``closed_pending_operator_review``.
  * Embed the locked safety flags (both False) in the manifest.
  * Embed the locked handoff contract version in the manifest +
    handoff doc + README.
  * Produce a 17-event run log in the locked order.
  * Refuse a second invocation against the same output_root +
    config + clock with E2046 (verified indirectly via the
    refuses-overwrite test; here we just confirm the happy path).
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import run_orchestrator as ro
from PHX2.stage20.closure.clock_helper import FrozenClock
from PHX2.stage20.closure.constants import (
    CHECKLIST_CSV_COLUMNS,
    CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
    CLOSURE_RUN_LOG_EVENT_SEQUENCE,
    CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW,
    HANDOFF_CONTRACT_VERSION,
    STAGE20_4_MINOR_VERSION,
)


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"

_FROZEN_DT = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)
_EXPECTED_ISO = "2026-05-16T12:34:56Z"
_EXPECTED_UTC_COMPACT = "20260516T123456Z"


def _frozen_clock() -> FrozenClock:
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

    config = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(s2),
        "stage20_3_run_dir": str(s3),
        "repo_root": str(repo),
        "output_root": str(output_root),
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
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    return {
        "config_path": config_path,
        "output_root": output_root,
        "stage20_2_run_dir": s2,
        "stage20_3_run_dir": s3,
        "repo_root": repo,
    }


@pytest.fixture
def clean_layout(tmp_path: Path) -> dict:
    return _build_clean_layout(tmp_path)


def _locate_run_dir(output_root: Path) -> Path:
    closure_runs = output_root / "stage20_closure_runs"
    assert closure_runs.exists(), (
        f"expected closure_runs root at {closure_runs}"
    )
    children = sorted(closure_runs.iterdir())
    assert len(children) == 1, (
        f"expected exactly one run directory; got "
        f"{[c.name for c in children]}"
    )
    return children[0]


# ---------------------------------------------------------------------------
# Exit code + artifact set
# ---------------------------------------------------------------------------


def test_clean_run_returns_exit_code_zero(clean_layout):
    exit_code = ro.run_closure(
        clean_layout["config_path"], clock=_frozen_clock(),
    )
    assert exit_code == 0


def test_clean_run_creates_closure_runs_root(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    closure_runs = (
        clean_layout["output_root"] / "stage20_closure_runs"
    )
    assert closure_runs.exists() and closure_runs.is_dir()


def test_clean_run_creates_run_dir(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    assert run_dir.is_dir()
    assert run_dir.name.startswith("stage20_4_")


def test_clean_run_id_format_matches_locked_template(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    # stage20_4_<YYYYMMDDTHHMMSSZ>_<config_sha8>
    parts = run_dir.name.split("_")
    assert parts[:2] == ["stage20", "4"]
    assert parts[2] == _EXPECTED_UTC_COMPACT
    assert len(parts[3]) == 8
    assert all(ch in "0123456789abcdef" for ch in parts[3])


def test_clean_run_writes_all_eight_artifacts(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    for filename in CLOSURE_OUTPUT_ARTIFACT_FILENAMES:
        p = run_dir / filename
        assert p.is_file(), f"missing artifact: {filename}"
        assert p.stat().st_size > 0, f"empty artifact: {filename}"


def test_clean_run_writes_exactly_eight_artifacts_no_extras(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    children = sorted(p.name for p in run_dir.iterdir())
    assert children == sorted(CLOSURE_OUTPUT_ARTIFACT_FILENAMES)


# ---------------------------------------------------------------------------
# Closure manifest content (closure_status + safety flags + handoff)
# ---------------------------------------------------------------------------


def _read_manifest(run_dir: Path) -> dict:
    return json.loads(
        (run_dir / "stage20_closure_manifest.json").read_text(
            encoding="utf-8",
        )
    )


def test_clean_run_manifest_closure_status_is_closed(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    manifest = _read_manifest(run_dir)
    assert (
        manifest["closure_status"]
        == CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW
    )


def test_clean_run_manifest_safety_flags_both_false(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    manifest = _read_manifest(run_dir)
    assert manifest["safe_for_live_dispatch"] is False
    assert manifest["live_dispatch_ready"] is False


def test_clean_run_manifest_handoff_contract_version_present(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    manifest = _read_manifest(run_dir)
    assert (
        manifest["handoff_contract_version"]
        == HANDOFF_CONTRACT_VERSION
    )


def test_clean_run_manifest_generated_at_utc_matches_clock(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    manifest = _read_manifest(run_dir)
    assert manifest["generated_at_utc"] == _EXPECTED_ISO


def test_clean_run_manifest_records_commit_shas(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    manifest = _read_manifest(run_dir)
    inputs_block = manifest["inputs"]
    assert inputs_block["stage20_1_commit_sha"] == _VALID_SHA_20_1
    assert inputs_block["stage20_2_commit_sha"] == _VALID_SHA_20_2
    assert inputs_block["stage20_3_commit_sha"] == _VALID_SHA_20_3


def test_clean_run_manifest_records_run_id(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    manifest = _read_manifest(run_dir)
    assert manifest["run_id"] == run_dir.name


# ---------------------------------------------------------------------------
# Checklist + run log + handoff + README
# ---------------------------------------------------------------------------


def test_clean_run_checklist_csv_header_matches_locked_columns(
    clean_layout,
):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    text = (run_dir / "stage20_closure_checklist.csv").read_text(
        encoding="utf-8",
    )
    rows = list(csv.reader(io.StringIO(text)))
    assert tuple(rows[0]) == CHECKLIST_CSV_COLUMNS


def test_clean_run_checklist_has_28_rows_plus_header(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    text = (run_dir / "stage20_closure_checklist.csv").read_text(
        encoding="utf-8",
    )
    rows = list(csv.reader(io.StringIO(text)))
    # Header + 28 checklist items.
    assert len(rows) == 29


def test_clean_run_log_events_in_locked_order(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    log_text = (run_dir / "stage20_4_run.log").read_text(
        encoding="utf-8",
    )
    events = [json.loads(line) for line in log_text.splitlines() if line]
    actual = [e["event"] for e in events]
    assert tuple(actual) == CLOSURE_RUN_LOG_EVENT_SEQUENCE


def test_clean_run_log_events_share_generated_at_utc(clean_layout):
    """Locked: every event carries the same ``ts`` (the
    orchestrator-captured generated_at_utc)."""
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    log_text = (run_dir / "stage20_4_run.log").read_text(
        encoding="utf-8",
    )
    events = [json.loads(line) for line in log_text.splitlines() if line]
    tstamps = {e["ts"] for e in events}
    assert tstamps == {_EXPECTED_ISO}


def test_clean_run_handoff_md_mentions_contract_and_run_id(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    text = (run_dir / "stage21_handoff.md").read_text(encoding="utf-8")
    assert HANDOFF_CONTRACT_VERSION in text
    assert run_dir.name in text
    # Sanity: locked manual-tag recommendation survived templating.
    assert "git tag -a stage-20-closed" in text


def test_clean_run_readme_records_closure_status(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    text = (run_dir / "README.md").read_text(encoding="utf-8")
    assert (
        f"closure_status: "
        f"{CLOSURE_STATUS_CLOSED_PENDING_OPERATOR_REVIEW}"
        in text
    )
    assert f"Stage 20.4 minor version: {STAGE20_4_MINOR_VERSION}" in text


def test_clean_run_audit_report_has_passed_true(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    data = json.loads(
        (run_dir / "codebase_audit_report.json").read_text(
            encoding="utf-8",
        )
    )
    assert data["passed"] is True


def test_clean_run_lineage_files_record_passed_crosscheck(clean_layout):
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    run_dir = _locate_run_dir(clean_layout["output_root"])
    s3 = json.loads(
        (run_dir / "stage20_3_lineage.json").read_text(encoding="utf-8")
    )
    assert s3["lineage_crosscheck_passed"] is True


# ---------------------------------------------------------------------------
# Stage 20.2 + Stage 20.3 run dirs are not mutated by the run
# ---------------------------------------------------------------------------


def test_clean_run_does_not_mutate_stage20_2_inputs(clean_layout):
    s2 = clean_layout["stage20_2_run_dir"]
    pre = {
        p.name: p.read_bytes()
        for p in s2.iterdir()
        if p.is_file()
    }
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    post = {
        p.name: p.read_bytes()
        for p in s2.iterdir()
        if p.is_file()
    }
    assert pre == post


def test_clean_run_does_not_mutate_stage20_3_inputs(clean_layout):
    s3 = clean_layout["stage20_3_run_dir"]
    pre = {
        p.name: p.read_bytes()
        for p in s3.iterdir()
        if p.is_file()
    }
    ro.run_closure(clean_layout["config_path"], clock=_frozen_clock())
    post = {
        p.name: p.read_bytes()
        for p in s3.iterdir()
        if p.is_file()
    }
    assert pre == post


# ---------------------------------------------------------------------------
# CLI entry: main(argv) returns same exit code
# ---------------------------------------------------------------------------


def test_main_with_valid_config_returns_zero(clean_layout, monkeypatch):
    """The CLI ``main()`` wrapper accepts a single positional arg
    and forwards to run_closure (which uses the default clock).
    Patch default_clock to the frozen clock for determinism."""
    from PHX2.stage20.closure import clock_helper as ch
    monkeypatch.setattr(ch, "default_clock", _frozen_clock)
    # The orchestrator imports default_clock at module-load time
    # via ``from clock_helper import default_clock`` -- patch that
    # binding too.
    monkeypatch.setattr(ro, "default_clock", _frozen_clock)

    exit_code = ro.main([str(clean_layout["config_path"])])
    assert exit_code == 0


def test_main_with_zero_args_returns_two(capsys):
    exit_code = ro.main([])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Usage:" in err


def test_main_with_two_args_returns_two(tmp_path: Path, capsys):
    exit_code = ro.main([str(tmp_path), str(tmp_path)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "Usage:" in err


def test_main_with_missing_config_file_returns_two(
    tmp_path: Path, capsys,
):
    """The InputFormatError path (config file missing) maps to
    exit code 2 -- distinct from pre-run-dir E20xx (exit code 1)."""
    missing = tmp_path / "does_not_exist.json"
    exit_code = ro.main([str(missing)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "InputFormatError" in err
