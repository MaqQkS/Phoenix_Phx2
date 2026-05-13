"""Phase 8: Stage 16A CLI three-tier exit discipline."""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.stage16a.cli import (
    EXIT_LOAD_TIME_FAIL,
    EXIT_OK,
    EXIT_OUTPUT_DIR_FAIL,
    MANIFEST_FILENAME,
    RUN_LOG_FILENAME,
    RUNTIME_POLICY_FILENAME,
    main as cli_main,
)
from PHX2.tests.stage16a.fixtures.builders import build_stage15_run_dir


def _run(s15: Path, out: Path) -> int:
    return cli_main(
        [
            "--stage15-run-path", str(s15),
            "--output-dir", str(out),
        ]
    )


# ---------------------------------------------------------------------------
# Tier A: output-dir cannot be initialized / is non-empty
# ---------------------------------------------------------------------------


def test_tier_a_output_dir_non_empty(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    out.mkdir()
    (out / "stray.txt").write_text("blocking")

    rc = _run(s15, out)
    assert rc == EXIT_OUTPUT_DIR_FAIL
    # No new files added by Stage 16A.
    contents = {p.name for p in out.iterdir()}
    assert contents == {"stray.txt"}
    assert not (out / MANIFEST_FILENAME).exists()
    assert not (out / RUNTIME_POLICY_FILENAME).exists()
    assert not (out / RUN_LOG_FILENAME).exists()


def test_tier_a_output_path_is_a_file(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out_file"
    out.write_text("stray")

    rc = _run(s15, out)
    assert rc == EXIT_OUTPUT_DIR_FAIL


# ---------------------------------------------------------------------------
# Tier B: load-time validation fails
# ---------------------------------------------------------------------------


def test_tier_b_corrupt_stage15_manifest(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(
        tmp_path / "s15",
        corrupt_manifest_bytes=b"{not valid json,,",
    )
    out = tmp_path / "out"
    rc = _run(s15, out)
    assert rc == EXIT_LOAD_TIME_FAIL
    # stage16a_run.log MUST exist; manifest + runtime policy MUST NOT.
    assert (out / RUN_LOG_FILENAME).exists()
    assert not (out / MANIFEST_FILENAME).exists()
    assert not (out / RUNTIME_POLICY_FILENAME).exists()


def test_tier_b_stage15_run_path_missing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    rc = _run(tmp_path / "nonexistent", out)
    assert rc == EXIT_LOAD_TIME_FAIL
    assert (out / RUN_LOG_FILENAME).exists()
    assert not (out / MANIFEST_FILENAME).exists()


def test_tier_b_wrong_approval_status(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"approval_status": "VALIDATION_FAILED"},
    )
    out = tmp_path / "out"
    rc = _run(s15, out)
    assert rc == EXIT_LOAD_TIME_FAIL
    assert (out / RUN_LOG_FILENAME).exists()
    assert not (out / MANIFEST_FILENAME).exists()


def test_tier_b_log_contains_error_detail(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"approval_status": "VALIDATION_FAILED"},
    )
    out = tmp_path / "out"
    _run(s15, out)
    log_text = (out / RUN_LOG_FILENAME).read_text(encoding="utf-8")
    assert "L04" in log_text
    assert "load-time validation failed" in log_text


# ---------------------------------------------------------------------------
# Tier C: clean run
# ---------------------------------------------------------------------------


def test_tier_c_clean_run_writes_three_files(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    rc = _run(s15, out)
    assert rc == EXIT_OK
    assert (out / MANIFEST_FILENAME).is_file()
    assert (out / RUNTIME_POLICY_FILENAME).is_file()
    assert (out / RUN_LOG_FILENAME).is_file()


def test_tier_c_runtime_policy_body_is_observe_only(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    _run(s15, out)
    body = json.loads(
        (out / RUNTIME_POLICY_FILENAME).read_text(encoding="utf-8")
    )
    assert body["schema_version"] == "observe_only_runtime_policy_v0"
    assert body["safety_surface"]["enforcement_mode"] == "OBSERVE_ONLY"
    assert body["safety_surface"]["hard_block_allowed"] is False
    assert body["policy_hash"].startswith("sha256:")


def test_tier_c_manifest_records_run_status(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    _run(s15, out)
    m = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert m["stage16a_schema_version"] == "stage16a_manifest_v0"
    assert m["stage"] == 16
    assert m["substage"] == "16A"
    assert m["run_status"] == "RUNTIME_POLICY_WRITTEN"


def test_tier_c_no_tmp_manifest_left_over(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    _run(s15, out)
    # Atomic rename should clean the .tmp file.
    assert not (out / (MANIFEST_FILENAME + ".tmp")).exists()


def test_tier_c_empty_rules_still_clean(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15", rules=())
    out = tmp_path / "out"
    rc = _run(s15, out)
    assert rc == EXIT_OK
    body = json.loads(
        (out / RUNTIME_POLICY_FILENAME).read_text(encoding="utf-8")
    )
    assert body["rule_count"] == 0
    assert body["rules"] == []


# ---------------------------------------------------------------------------
# argparse smoke (re-verifies Phase 1 behaviour with the full pipeline)
# ---------------------------------------------------------------------------


def test_no_args_exits_non_zero() -> None:
    import pytest
    with pytest.raises(SystemExit) as info:
        cli_main([])
    assert info.value.code is not None and info.value.code != 0
