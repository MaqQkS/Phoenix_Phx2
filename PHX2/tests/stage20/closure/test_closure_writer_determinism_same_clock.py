"""Stage 20.4 Phase 6 -- same-clock determinism harness.

Locked invariants:

  * Two orchestrator runs with the same config + same injected clock
    + two DISTINCT tmp ``output_root`` parents must produce
    byte-identical content for every one of the 8 closure artifacts.

  * The two runs must write to two SEPARATE output_root parents so
    E2046 (overwrite refusal) is not exercised here. (E2046 itself
    is covered by test_run_orchestrator_refuses_overwrite.py.)

  * The 8 artifact filenames are the locked set in
    ``CLOSURE_OUTPUT_ARTIFACT_FILENAMES``.

Implementation note (locked):

  * Both runs use the SAME JSON config file content. The orchestrator
    exposes an ``output_root_override`` keyword argument as a test-only
    seam: when supplied, it redirects the actual write location while
    leaving ``inputs.output_root`` (and thus the manifest, lineage
    files, etc.) unchanged. This keeps the manifest byte-identical
    across the two runs while still satisfying "two separate tmp
    output_roots".

  * The override does NOT alter run_id derivation; config_sha8 still
    comes from the loaded ClosureInputConfig (which records the
    config's declared output_root). Both runs therefore share a
    run_id and write byte-identical artifact content to two distinct
    on-disk locations.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import run_orchestrator as ro
from PHX2.stage20.closure.clock_helper import FrozenClock
from PHX2.stage20.closure.constants import (
    CLOSURE_OUTPUT_ARTIFACT_FILENAMES,
)


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"

_FROZEN_DT = datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc)


def _frozen() -> FrozenClock:
    return FrozenClock(_FROZEN_DT)


def _build_layout(
    parent: Path,
    *,
    declared_output_root: Path,
) -> dict:
    """Build a closure-input tree under ``parent`` whose config
    declares ``declared_output_root`` (which will then be ignored
    in favor of the override path)."""
    s2 = parent / "stage20_2"
    s3 = parent / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)
    repo = parent / "repo"
    (repo / "PHX2" / "stage20" / "closure").mkdir(parents=True)
    return {
        "s2": s2, "s3": s3,
        "repo": repo,
        "declared_output_root": declared_output_root,
    }


def _write_config(parent: Path, layout: dict) -> Path:
    cfg = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(layout["s2"]),
        "stage20_3_run_dir": str(layout["s3"]),
        "repo_root": str(layout["repo"]),
        "output_root": str(layout["declared_output_root"]),
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
    p = parent / "config.json"
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


def _locate_run_dir(output_root: Path) -> Path:
    closure_runs = output_root / "stage20_closure_runs"
    assert closure_runs.exists()
    children = sorted(closure_runs.iterdir())
    assert len(children) == 1
    return children[0]


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def two_runs(tmp_path: Path) -> dict:
    """Run the orchestrator twice over byte-identical input layouts
    with the same clock, against two separate output_roots.

    Returns a dict carrying both run directories and the file byte
    payloads so individual tests below can do per-artifact equality
    assertions.
    """
    # Build TWO completely separate input trees under two separate
    # parents so neither run can possibly see the other's outputs.
    parent_a = tmp_path / "tree_a"
    parent_b = tmp_path / "tree_b"
    parent_a.mkdir()
    parent_b.mkdir()

    # Two distinct override output_roots.
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()

    # Both configs declare the SAME ``output_root`` field (a third,
    # never-actually-used path) so compute_config_sha8 yields the
    # SAME digest for both runs. The override redirects actual writes.
    declared_root = tmp_path / "declared_output_root"
    declared_root.mkdir()

    layout_a = _build_layout(parent_a, declared_output_root=declared_root)
    layout_b = _build_layout(parent_b, declared_output_root=declared_root)

    # Critical: the loaded ClosureInputConfig is sensitive to
    # ``stage20_2_run_dir`` / ``stage20_3_run_dir`` / ``repo_root``
    # path strings. To make BOTH runs see the same config_sha8 (and
    # therefore produce byte-identical artifacts), we point both
    # configs at the same physical s2/s3/repo paths. We use tree_a's
    # paths as the canonical source for both configs.
    config_dict = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(layout_a["s2"]),
        "stage20_3_run_dir": str(layout_a["s3"]),
        "repo_root": str(layout_a["repo"]),
        "output_root": str(declared_root),
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
    cfg_path_a = parent_a / "config.json"
    cfg_path_b = parent_b / "config.json"
    cfg_path_a.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")
    cfg_path_b.write_text(json.dumps(config_dict, indent=2), encoding="utf-8")

    rc_a = ro.run_closure(
        cfg_path_a, clock=_frozen(), output_root_override=out_a,
    )
    rc_b = ro.run_closure(
        cfg_path_b, clock=_frozen(), output_root_override=out_b,
    )
    assert rc_a == 0, f"first run unexpectedly returned {rc_a}"
    assert rc_b == 0, f"second run unexpectedly returned {rc_b}"

    run_a = _locate_run_dir(out_a)
    run_b = _locate_run_dir(out_b)

    return {
        "out_a": out_a,
        "out_b": out_b,
        "run_a": run_a,
        "run_b": run_b,
        "bytes_a": {
            name: (run_a / name).read_bytes()
            for name in CLOSURE_OUTPUT_ARTIFACT_FILENAMES
        },
        "bytes_b": {
            name: (run_b / name).read_bytes()
            for name in CLOSURE_OUTPUT_ARTIFACT_FILENAMES
        },
    }


# ---------------------------------------------------------------------------
# Same-clock determinism: every artifact byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", list(CLOSURE_OUTPUT_ARTIFACT_FILENAMES))
def test_same_clock_each_artifact_is_byte_identical(two_runs, filename):
    a = two_runs["bytes_a"][filename]
    b = two_runs["bytes_b"][filename]
    assert a == b, (
        f"same-clock determinism failed: {filename} differs across "
        f"two runs (sha256_a={_sha256(a)} sha256_b={_sha256(b)})"
    )


def test_same_clock_run_ids_are_identical(two_runs):
    """Both runs must select the same run_id because compute_config_sha8
    of identical configs is identical and the clock is the same."""
    assert two_runs["run_a"].name == two_runs["run_b"].name


def test_same_clock_run_dirs_live_in_distinct_output_roots(two_runs):
    """Sanity: the two run dirs occupy two distinct output_root
    parents (we did not bypass E2046 by overwriting in place)."""
    assert two_runs["run_a"].parent.parent != two_runs["run_b"].parent.parent


def test_same_clock_full_sha256_set_matches(two_runs):
    a_hashes = {
        name: _sha256(two_runs["bytes_a"][name])
        for name in CLOSURE_OUTPUT_ARTIFACT_FILENAMES
    }
    b_hashes = {
        name: _sha256(two_runs["bytes_b"][name])
        for name in CLOSURE_OUTPUT_ARTIFACT_FILENAMES
    }
    assert a_hashes == b_hashes


# ---------------------------------------------------------------------------
# E2046 is NOT weakened: same output_root + same clock still refuses
# ---------------------------------------------------------------------------


def test_e2046_still_fires_when_same_output_root_reused(tmp_path: Path):
    """Defense: confirm the determinism harness does not weaken the
    overwrite guard. Reusing one output_root for two runs (no
    override, no cleanup) still trips E2046 on the second invocation."""
    parent = tmp_path / "tree"
    parent.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    layout = _build_layout(parent, declared_output_root=out)
    cfg_path = _write_config(parent, layout)

    rc1 = ro.run_closure(cfg_path, clock=_frozen())
    rc2 = ro.run_closure(cfg_path, clock=_frozen())
    assert rc1 == 0
    assert rc2 == 1  # E2046 -> exit 1
