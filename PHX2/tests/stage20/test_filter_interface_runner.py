"""Stage 20.3 Phase 5 tests -- end-to-end runner.

Exercises run_stage20_3 against the synthetic Stage 20.2 fixture.
Covers determinism, Stage 20.2 immutability, error propagation,
and clock injection.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
from datetime import datetime, timezone

import pytest

from PHX2.stage20 import filter_interface_runner
from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.filter_interface_runner import (
    Stage20ThreeRunResult,
    run_stage20_3,
)

from PHX2.tests.stage20.fixtures_stage20_2_synthetic import (
    OMIT_SAFE_FOR_LIVE_DISPATCH,
    build_synthetic_stage20_2_run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frozen_2026_05_15() -> FrozenClock:
    return FrozenClock(
        datetime(2026, 5, 15, 12, 34, 56, tzinfo=timezone.utc)
    )


def _frozen_at(year=2026, month=5, day=15, hour=12, minute=34, second=56):
    return FrozenClock(
        datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    )


def _forbidden_fim_token() -> str:
    return "filter_" + "interface_" + "manifest"


def _file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# R1-R5: End-to-end
# ---------------------------------------------------------------------------


def test_r1_run_produces_all_five_artifacts(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    for fn in (
        "stage20_3_manifest.json",
        "filter_interface_registry.csv",
        "filter_interface_results.csv",
        "stage20_3_run.log",
        "README.md",
    ):
        assert (result.stage20_3_run_dir / fn).is_file(), (
            f"missing artifact: {fn}"
        )


def test_r2_result_locked_fields_all_zero_or_false(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert result.registered_filter_count == 0
    assert result.evaluated_filter_count == 0
    assert result.candidate_mutation_count == 0
    assert result.blocking_filter_count == 0
    assert result.safe_for_live_dispatch is False
    assert result.live_dispatch_ready is False


def test_r3_run_dir_path_is_under_stage20_3_subdir(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert result.stage20_3_run_dir.parent.name == "stage20_3"
    assert result.stage20_3_run_dir.parent.parent == run_dir
    assert result.stage20_3_run_dir.name == result.stage20_3_run_id


def test_r4_non_manifest_artifact_hashes_in_manifest_match_disk(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    import json
    manifest = json.loads(
        (result.stage20_3_run_dir / "stage20_3_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    pairs = [
        ("filter_interface_registry_csv_sha256",
         result.stage20_3_run_dir / "filter_interface_registry.csv"),
        ("filter_interface_results_csv_sha256",
         result.stage20_3_run_dir / "filter_interface_results.csv"),
        ("stage20_3_run_log_sha256",
         result.stage20_3_run_dir / "stage20_3_run.log"),
        ("readme_md_sha256",
         result.stage20_3_run_dir / "README.md"),
    ]
    for key, path in pairs:
        assert manifest[key] == _file_sha(path)


def test_r5_lineage_block_carries_reverified_hashes(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    import json
    manifest = json.loads(
        (result.stage20_3_run_dir / "stage20_3_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    lin = manifest["stage20_2_lineage"]
    # Recompute every Stage 20.2 sibling hash and compare.
    assert lin["manifest_json_sha256"] == _file_sha(
        run_dir / "manifest.json"
    )
    assert lin["preview_candidates_csv_sha256"] == _file_sha(
        run_dir / "preview_candidates.csv"
    )
    assert lin["alert_eligibility_decisions_csv_sha256"] == _file_sha(
        run_dir / "alert_eligibility_decisions.csv"
    )
    assert lin["readme_md_sha256"] == _file_sha(run_dir / "README.md")
    assert lin["stage20_run_log_sha256"] == _file_sha(
        run_dir / "stage20_run.log"
    )


# ---------------------------------------------------------------------------
# IM1-IM4: Stage 20.2 immutability
# ---------------------------------------------------------------------------


_SIBLINGS = (
    "manifest.json",
    "preview_candidates.csv",
    "alert_eligibility_decisions.csv",
    "README.md",
    "stage20_run.log",
)


def test_im1_sibling_sha256_identical_before_and_after(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    pre = {fn: _file_sha(run_dir / fn) for fn in _SIBLINGS}
    run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    post = {fn: _file_sha(run_dir / fn) for fn in _SIBLINGS}
    assert pre == post


def test_im2_sibling_mtime_identical_before_and_after(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    pre = {fn: (run_dir / fn).stat().st_mtime_ns for fn in _SIBLINGS}
    run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    post = {fn: (run_dir / fn).stat().st_mtime_ns for fn in _SIBLINGS}
    assert pre == post


def test_im3_sibling_bytes_identical_before_and_after(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    pre = {fn: (run_dir / fn).read_bytes() for fn in _SIBLINGS}
    run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    post = {fn: (run_dir / fn).read_bytes() for fn in _SIBLINGS}
    assert pre == post


def test_im4_stage20_2_run_dir_only_adds_stage20_3_subdirectory(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    before = sorted([p.name for p in run_dir.iterdir()])
    run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    after = sorted([p.name for p in run_dir.iterdir()])
    # Only "stage20_3" is newly added.
    assert set(after) - set(before) == {"stage20_3"}


# ---------------------------------------------------------------------------
# D1-D4: Determinism
# ---------------------------------------------------------------------------


def test_d1_second_run_on_same_dir_refuses_overwrite(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert exc_info.value.code == "E2027"
    assert "already exists" in (exc_info.value.detail or "")


def test_d2_run_id_unchanged_with_different_clock_same_inputs(tmp_path):
    # Two separate tmp_paths so the run-dir collision check doesn't fire.
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    run_a = build_synthetic_stage20_2_run(dir_a, candidate_count=2)
    run_b = build_synthetic_stage20_2_run(dir_b, candidate_count=2)
    res_a = run_stage20_3(run_a, clock=_frozen_at(2026, 5, 15))
    res_b = run_stage20_3(run_b, clock=_frozen_at(2027, 6, 16))
    assert res_a.stage20_3_run_id == res_b.stage20_3_run_id


def test_d3_two_independent_tmp_paths_produce_byte_identical_artifacts(
    tmp_path,
):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    run_a = build_synthetic_stage20_2_run(dir_a, candidate_count=3)
    run_b = build_synthetic_stage20_2_run(dir_b, candidate_count=3)
    res_a = run_stage20_3(run_a, clock=_frozen_2026_05_15())
    res_b = run_stage20_3(run_b, clock=_frozen_2026_05_15())
    for fn in (
        "stage20_3_manifest.json",
        "filter_interface_registry.csv",
        "filter_interface_results.csv",
        "stage20_3_run.log",
        "README.md",
    ):
        assert _file_sha(res_a.stage20_3_run_dir / fn) == _file_sha(
            res_b.stage20_3_run_dir / fn
        ), f"artifact {fn} bytes differ between independent tmp_paths"


def test_d4_different_fixtures_produce_different_run_ids(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    run_a = build_synthetic_stage20_2_run(dir_a, candidate_count=1)
    run_b = build_synthetic_stage20_2_run(dir_b, candidate_count=2)
    res_a = run_stage20_3(run_a, clock=_frozen_2026_05_15())
    res_b = run_stage20_3(run_b, clock=_frozen_2026_05_15())
    assert res_a.stage20_3_run_id != res_b.stage20_3_run_id


# ---------------------------------------------------------------------------
# N1-N5: Negative paths
# ---------------------------------------------------------------------------


def test_n1_bad_manifest_missing_key_raises_e2027(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, omit_keys=("warnings",),
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert exc_info.value.code == "E2027"


def test_n2_safe_for_live_dispatch_true_raises_e2027(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, safe_for_live_dispatch_override=True,
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert exc_info.value.code == "E2027"


def test_n3_sibling_hash_mismatch_raises_e2027(tmp_path):
    run_dir = build_synthetic_stage20_2_run(
        tmp_path, corrupt_file_hash="README.md",
    )
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert exc_info.value.code == "E2027"


def test_n4_nonexistent_stage20_2_run_dir(tmp_path):
    bogus = tmp_path / "does_not_exist"
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(bogus, clock=_frozen_2026_05_15())
    assert exc_info.value.code == "E2027"


def test_n5_pre_created_stage20_3_run_dir_raises_e2027(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    # Mimic the derived id so the collision check fires.
    from PHX2.stage20.filter_interface_input import (
        load_and_validate_stage20_2_run,
    )
    from PHX2.stage20.stage20_3_manifest import derive_stage20_3_run_id
    inputs = load_and_validate_stage20_2_run(run_dir)
    rid = derive_stage20_3_run_id(
        inputs.stage20_run_id, inputs.manifest_json_sha256,
    )
    (run_dir / "stage20_3" / rid).mkdir(parents=True)
    with pytest.raises(Stage20ValidationError) as exc_info:
        run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert exc_info.value.code == "E2027"
    assert "already exists" in (exc_info.value.detail or "")


# ---------------------------------------------------------------------------
# E1: Edge - zero-candidate fixture
# ---------------------------------------------------------------------------


def test_e1_zero_candidate_fixture_still_runs(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path, candidate_count=0)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    assert result.registered_filter_count == 0
    assert result.evaluated_filter_count == 0
    assert result.candidate_mutation_count == 0


# ---------------------------------------------------------------------------
# C1-C2: Clock injection
# ---------------------------------------------------------------------------


def test_c1_clock_required_as_keyword(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    with pytest.raises(TypeError):
        # No clock argument supplied at all.
        run_stage20_3(run_dir)


def test_c2_generated_at_utc_matches_frozenclock_with_z_suffix(tmp_path):
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    clock = _frozen_at(2026, 5, 15, 12, 34, 56)
    result = run_stage20_3(run_dir, clock=clock)
    import json
    manifest = json.loads(
        (result.stage20_3_run_dir / "stage20_3_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["generated_at_utc"] == "2026-05-15T12:34:56Z"


# ---------------------------------------------------------------------------
# B1-B2: Boundary discipline (AST)
# ---------------------------------------------------------------------------


def _imported_modules(module) -> set[str]:
    src = pathlib.Path(module.__file__).resolve().read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.add(node.module)
    return imports


_FORBIDDEN_NETWORK_LIBS = (
    "sqlite3", "requests", "httpx", "aiohttp", "websockets",
    "grpc", "grpclib", "kafka", "redis", "boto3", "paramiko",
    "smtplib", "discord", "telegram", "dotenv", "dynaconf", "hydra",
)


def test_b1_runner_no_forbidden_network_or_provider_imports():
    imports = _imported_modules(filter_interface_runner)
    for forbidden in _FORBIDDEN_NETWORK_LIBS:
        for imp in imports:
            assert imp != forbidden and not imp.startswith(forbidden + "."), (
                f"forbidden import {imp!r} in runner"
            )


_FORBIDDEN_STAGE20_2_INTERNAL = (
    "PHX2.stage20.runner",
    "PHX2.stage20.manifest_assembler",
    "PHX2.stage20.builder",
    "PHX2.stage20.artifact_writers",
    "PHX2.stage20.input_validators",
)


def test_b2_runner_no_imports_from_stage20_2_internal_modules():
    imports = _imported_modules(filter_interface_runner)
    for forbidden in _FORBIDDEN_STAGE20_2_INTERNAL:
        assert forbidden not in imports, (
            f"forbidden 20.2-internal import: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# T1-T2: Token discipline
# ---------------------------------------------------------------------------


def test_t1_forbidden_token_absent_from_runner_module_source():
    src = pathlib.Path(
        filter_interface_runner.__file__
    ).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


def test_t2_forbidden_token_absent_from_this_test_file():
    src = pathlib.Path(__file__).resolve().read_bytes()
    assert _forbidden_fim_token().encode("utf-8") not in src


# ---------------------------------------------------------------------------
# Bonus: locked log-event sequence
# ---------------------------------------------------------------------------


def test_log_events_sequence_seven_events_in_locked_order(tmp_path):
    import json
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    lines = (
        result.stage20_3_run_dir / "stage20_3_run.log"
    ).read_text(encoding="utf-8").splitlines()
    events = [json.loads(line)["event"] for line in lines]
    assert events == [
        "run_started",
        "stage20_2_inputs_loaded",
        "registry_initialized",
        "evaluation_completed",
        "artifacts_written",
        "manifest_written",
        "run_completed",
    ]


def test_log_manifest_written_event_detail_is_locked_literal(tmp_path):
    import json
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    lines = (
        result.stage20_3_run_dir / "stage20_3_run.log"
    ).read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    manifest_ev = [e for e in parsed if e["event"] == "manifest_written"][0]
    assert manifest_ev["detail"] == {
        "path": "stage20_3_manifest.json",
        "planned": True,
    }


def test_log_all_events_share_single_ts_utc(tmp_path):
    import json
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    lines = (
        result.stage20_3_run_dir / "stage20_3_run.log"
    ).read_text(encoding="utf-8").splitlines()
    ts_set = {json.loads(line)["ts_utc"] for line in lines}
    assert len(ts_set) == 1


# ---------------------------------------------------------------------------
# M1 regression: lock the run_started detail shape post follow-on fix.
#
# Pre-fix history (not allowed to regress):
#   - first emission used {"stage20_2_run_dir": str(<absolute path>)}
#   - second emission used {"stage20_2_run_dir_name": <basename>}
# Final approved shape: {"stage20_3_run_id": <id>} -- one key only,
# symmetric with run_completed.{stage20_3_run_id, ok}.
# ---------------------------------------------------------------------------


def test_run_started_event_detail_locks_stage20_3_run_id(tmp_path):
    import json
    run_dir = build_synthetic_stage20_2_run(tmp_path)
    result = run_stage20_3(run_dir, clock=_frozen_2026_05_15())
    log_path = result.stage20_3_run_dir / "stage20_3_run.log"
    log_bytes = log_path.read_bytes()
    parsed = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]

    # (1) First event: run_started with exactly the locked detail.
    first = parsed[0]
    assert first["event"] == "run_started"
    assert first["detail"] == {"stage20_3_run_id": result.stage20_3_run_id}
    assert len(first["detail"]) == 1
    assert "stage20_2_run_dir_name" not in first["detail"]
    assert "stage20_2_run_dir" not in first["detail"]

    # (2) Every event carries top-level stage20_3_run_id matching the
    # returned run id.
    for ev in parsed:
        assert "stage20_3_run_id" in ev
        assert ev["stage20_3_run_id"] == result.stage20_3_run_id

    # (3) Last event: run_completed with the locked 2-key detail.
    last = parsed[-1]
    assert last["event"] == "run_completed"
    assert last["detail"] == {
        "stage20_3_run_id": result.stage20_3_run_id,
        "ok": True,
    }
    assert len(last["detail"]) == 2

    # (4) Raw log bytes carry no parent-dir field name or absolute
    # path. Catches a regression even if a future event dict reorder
    # or shape change slipped past the structural asserts above.
    assert b"stage20_2_run_dir_name" not in log_bytes
    assert b"stage20_2_run_dir" not in log_bytes
    assert str(run_dir).encode("utf-8") not in log_bytes
